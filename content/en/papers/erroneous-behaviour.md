---
title: Erroneous behavior and uninitialized reads (P2795)
summary: How C++26 deals with reading uninitialized local variables, a common security hole. Why zero-initializing everything was not adopted and a new category of behavior, erroneous behavior, was added instead, so that uninitialized automatic variables hold an erroneous value chosen by the implementation, with [[indeterminate]] as the escape hatch for performance-sensitive code; and how far Clang 23 is from these semantics today.
tags: erroneous behavior, uninitialized, UB, security, proposal, C++26
group: C++26
updated: 2026-10-19
---

!!! tldr
    - In C++23, reading an uninitialized local variable is undefined behavior. It lets the optimizer rewrite the program freely, and it also reads out whatever data is left on the stack (such as a key left by a previous call) as-is.
    - [[P2723R1]] proposed zero-initializing all automatic variables. That closes the hole, but turns `int x;` into a valid way of writing 0, so tools could no longer report a forgotten initialization as an error; it was not adopted.
    - [[P2795R5]] adds **erroneous behavior**: the behavior is defined, but the standard deems it an error, recommends that implementations diagnose it, and allows them to terminate the program. An uninitialized automatic variable holds an erroneous value chosen by the implementation, and reading it is erroneous behavior.
    - Heap memory and variables marked `[[indeterminate]]` still have indeterminate values, and reading them is still UB; when the erroneous value is not valid for the type (such as `bool`), reading it is still UB too.
    - Clang 23 does not implement these semantics yet under `-std=c++2c` and still optimizes as if it were UB by default; `-ftrivial-auto-var-init=pattern` or `=zero` give equivalent behavior, and `[[indeterminate]]` is not recognized yet.

## What one line of `int x;` can leak

In the program below, `report` forgets to initialize its buffer, and `login` has just put a key in the same stack space:

```cpp title="stack-leak.cpp" run eb
#include <cstdio>
#include <cstring>

[[gnu::noinline]] void login() {
  char key[16];
  std::strcpy(key, "hunter2-secret");
  asm volatile("" : : "r"(key) : "memory");
}

[[gnu::noinline]] void report() {
  char msg[16];                 // forgot to initialize
  std::printf("%.15s\n", msg);  // reads uninitialized bytes
}

int main() {
  login();
  report();
}
```

The `asm volatile` line is only there so the writes in `login` are not optimized away. Compiled with Clang 23 and `-std=c++2c -O2`, the program prints `hunter2-secret`; `-Wall -Wextra` gives no warning at all, and `-fsanitize=address,undefined` reports nothing either. What `report` reads are the bytes `login` left on the stack.

In C++23 this read is [[g:undefined-behavior|undefined behavior]] (UB): the standard places no requirements on the entire execution. In practice two kinds of things happen:

- Data leaks. As in the example above, whatever is in the stack slot or register the variable occupies gets read out. [[P2723R1]] cites more than 1100 use-of-uninitialized-value security bugs in Chrome, and statistics that about 12% of exploitable bugs in Android fall into this category.
- The optimizer rewrites the program. The compiler may assume the read does not happen and delete branches or merge paths on that basis. [[topics/undefined-behavior]] shows, with an example `if (b) x = 1; return x;`, how Clang makes the function return 1 whatever `b` is.

The problem is big enough that many projects long ago worked around the standard on their own: Clang and GCC provide `-ftrivial-auto-var-init=zero` or `=pattern`, which automatically fill automatic variables that have no initializer, and Microsoft uses a similar mechanism inside Windows. According to P2723R1, such options have been implemented since 2018 and deployed in major operating systems and browsers.

## The design space

An option only takes effect in projects that turn it on, and code relying on it is still UB as far as the standard is concerned. What the committee had to decide was how the language itself should specify this read. [[P2754R0]] collected the approaches that came up in discussion into a table, evaluated from three angles: whether the approach can be written into the standard consistently (viability), whether existing code compiles and runs as before (compatibility), and whether a declaration without an initializer can still express the author's intent (expressiveness):

| Approach | Viability | Compatibility | Expressiveness |
|---|---|---|---|
| Zero-initialize everything | Viable | Compatible | Worse |
| Zero-initialize, error when a read can be proven | Unclear | Compatible for correct code | Unchanged |
| Require initialization in source | Viable | Incompatible | Better |
| Require initialization, or an explicit marker for deferred initialization | Viable | Incompatible | Better |
| Fill a default value, but reading is still UB | Not viable | Compatible | Unchanged |
| Fill a default value, reading is erroneous behavior | Viable | Compatible | Unchanged |
| Abolish default initialization, keep only value initialization | Unclear | Unclear | Unclear |

The expressiveness column needs explaining. Today `int x;` has only two possible meanings: the author forgot to initialize it (a bug), or the author intends to write it later (it will be written before any read). Readers and tools can reason on that basis: any read before a write is definitely wrong. An approach that gives `int x;` a third valid meaning makes expressiveness worse.

### Zero-initialize everything (P2723)

[[P2723R1]]'s approach is the most direct: zero-initialize all objects of automatic storage duration, including padding bytes; dynamic storage duration is unchanged. It gives three reasons: this is exactly the behavior of `-ftrivial-auto-var-init=zero`, already deployed at scale; the performance impact the author reports is within 0.5%; and objects of static and thread storage duration are already zero-initialized first ([[basic.start.static]]), so automatic storage duration would become consistent with them.

It was not adopted, for reasons already stated in the paper's own caveats section:

<div class="compare" markdown="1">

```cpp title="P2723: value 0, defined behavior"
void f(int);

void g() {
  int x;   // same as int x = 0;
  f(x);    // maybe intentional, maybe a bug
}
```

```cpp title="P2795: erroneous value, erroneous behavior"
void f(int);

void g() {
  int x;   // erroneous value chosen by the implementation
  f(x);    // definitely a bug, can be reported
}
```

</div>

- It hides bugs. Once zero-initialization is a language guarantee, people will rely on it on purpose. From then on, reading 0 after `int x;` may be a bug or may be the 0 the author wanted; static analysis, MemorySanitizer and Valgrind can no longer tell the difference and have to give up reporting it. As P2723 puts it, the security problem is eliminated, but the correctness problem can no longer be diagnosed.
- Zero is not necessarily safe. The paper gives a Linux example: `task->uid` being 0 means root, and reading an uninitialized 0 there once caused a CVE. For some enumerations, 0 is not a valid enumerator at all.
- An `int` has no natural default value. The author of P2795 points out that it is natural for `std::vector<int> v;` to give an empty container, because empty is a reasonable initial state for a container; but no number is more suitable than any other for an `int`. If you want 0, write `int x = 0;`.

P2723 also discussed using a repeated byte pattern like `0xAA` instead: a pointer read out would immediately cause an access fault, and a floating-point value would be a NaN with payload, which makes tracking things down easier. The cost is about 1.5% in size and performance on some workloads (the figure the paper cites), and a very large integer used as a size might defeat bounds checks. This shows that choosing the value is itself a trade-off, and different builds may need different values.

### Keep it UB

Don't change the standard and let vendors keep providing compiler options. P2723 points out that implementers generally dislike this route: an option that everyone turns on and everyone relies on effectively splits off a dialect of the language.

Another variant: specify that the variable is filled with a default value, but reading it is still UB. P2754 judges this not viable. UB means the standard imposes no requirements; specifying what value is filled in while saying the read has no requirements makes the first half non-binding: a compiler that skips the fill for optimization still conforms.

### Make it ill-formed

Require every automatic variable to have an initializer, or, like C# and Swift, require the compiler to prove the variable is assigned before every read (definite initialization). This gives the best expressiveness, but neither path works:

- A large amount of existing correct code declares first and writes through a pointer later (such as `int n; read_size(&n);`), and all of it would have to change. P2754 also worries that people would use scripts to add `= 0` to every variable, wiping out the original authors' intent once again.
- Proving assignment before every read needs a data-flow analysis. If the analysis is too simple, it rejects a lot of correct code; if it is clever enough, the standard would have to specify a complex algorithm that keeps improving, or else different compilers would accept different programs.

"Zero-initialize, error when a read can be proven" has the same problem: whether a program is well-formed would depend on the compiler's analysis capabilities.

### Keep only value initialization

Abolish default initialization entirely and make `T x;` always value-initialize. This would simplify the initialization rules as a side effect, but P2723 points out that it would either call constructors and thus change the behavior of existing class types, or still do nothing for `int`; P2754 also considers it too far-reaching to be done in the short term.

### A new category of behavior

The remaining row is the approach of [[P2795R5]]: the implementation fills the variable's bytes with some value, and reading it is a new kind of behavior, neither UB nor ordinary well-defined behavior. P2723 itself recorded this idea in section 4.14, calling it a new "word of power". In P2754's table it is the only approach that is viable and compatible without losing expressiveness.

## The final design

### Erroneous behavior

[[defns.erroneous]] defines the new category:

!!! std
    erroneous behavior: well-defined behavior that the implementation is recommended to diagnose
    
    Erroneous behavior is well-defined behavior that implementations are recommended to diagnose.

The note under the definition says erroneous behavior is always the consequence of incorrect program code. [[intro.abstract#6]] specifies what implementations may do: when execution reaches an operation specified as erroneous behavior, the implementation may issue a diagnostic and may terminate the program. The recommended practice in [[intro.abstract#7]] is to issue a diagnostic when it is executed, with a note allowing diagnostics to have false positives. Footnote 3 of [[intro.compliance.general#2]] adds correspondingly that a correct execution can contain erroneous behavior, depending on the data being processed.

The difference between [[g:erroneous-behavior|erroneous behavior]] and UB lies in what happens after execution reaches it:

- After UB the standard imposes no requirements, and the optimizer may assume it does not happen;
- After erroneous behavior the program must continue as specified (here, reading out that erroneous value), unless the implementation chooses to diagnose and terminate.

Both mean the code is wrong. So tools can treat them the same way: sanitizers still report, compilers still warn; and in a production build with no tools involved, the program's behavior is deterministic.

### The implementation chooses the erroneous value

[[basic.indet#1]] ¶1.2 specifies that when storage for an object of automatic storage duration is obtained, its bytes have [[g:erroneous-value|erroneous values]], each value determined by the implementation independently of the state of the program. The phrase about independence from program state rules out simply reusing data left on the stack: the key-leaking program above can no longer print `hunter2-secret` in C++26.

The standard does not say the value is 0. P2795's reason is to allow implementations to use different poison values in different build modes: an easily recognized pattern for debugging, 0 for production. A value fixed at 0 would be more predictable, but also easier for programmers to rely on deliberately. The byte-level details (which bits of the value representation are erroneous, the exception for copying `unsigned char`) are in [[basic.indet]].

### Back and forth on scope

Over P2795's revisions, the scope changed once. R3 narrowed it to non-static local variables, because function parameters and temporaries had no good syntax for opting out. EWG then asked for all objects of automatic storage duration to be treated alike, to keep the mental model simple and extend the security benefit to every case, so R4 went back to all objects of automatic storage duration, including parameters and temporaries. Temporaries have no way to opt out; the paper considers that they can rarely be observed, and the optimizer can usually eliminate redundant writes.

### Cases that are still UB

P2795 only changed the initial value of objects of automatic storage duration; everything else is as before:

| Case | Consequence of reading in C++26 | Basis |
|---|---|---|
| Dynamic storage duration (`new int`, `malloc`) | UB | [[basic.indet#1]] ¶1.1 |
| Variable or parameter marked `[[indeterminate]]` | UB | [[basic.indet#1]] ¶1.1 |
| Erroneous value not valid for the type (such as a `bool` reading `0xAA`) | UB | [[conv.lval#3]] ¶3.3 |
| Copying an indeterminate value into an initialized variable and reading that | UB | The value is still indeterminate |
| Placement new of a default-initialized `char` on a local array | The existing contents are not overwritten | Only the initial value when storage is obtained is affected |

The third row is the easiest to overlook. Whether the function below is erroneous behavior or UB depends on the value the implementation chose:

```cpp title="bool-flag.cpp" run
#include <cstdio>
[[gnu::noinline]] bool flag() {
  bool b;      // erroneous value, possibly not a valid bool
  return b;    // valid value: erroneous behavior; invalid: UB
}
int main() { std::printf("%d\n", flag() ? 1 : 0); }
```

Compiled and run with Clang 23 and `-O0 -fsanitize=undefined -ftrivial-auto-var-init=pattern`, UBSan reports load of value 170, which is not a valid value for type 'bool'; 170 is `0xAA`. With `=zero` there is no report and it prints 0. Pointers are similar: even if an uninitialized pointer has a definite erroneous value, dereferencing it is still UB.

### `[[indeterminate]]`: the opt-out

There was no way to opt out before R2; the core group asked for one: for code that is already correct, filling has only costs and no benefit, especially for large buffers. A marked object goes back to C++23 semantics: its initial value is an [[g:indeterminate-value|indeterminate value]], reading it is UB, and the compiler can optimize on that basis as before.

```cpp title="indeterminate.cpp" run ok
#include <cstddef>
#include <iostream>

void compute(int* a, int* b, std::size_t n) {
  *a = 0;
  for (std::size_t i = 0; i < n; ++i) b[i] = int(i);
}

int main() {
  int x [[indeterminate]];         // applies only to x
  std::cin >> x;                   // x is set to 0 if extraction fails

  [[indeterminate]] int a, b[10];  // applies to a and b
  compute(&a, b, 10);
  return a + b[9] - 9 + x * 0;
}
```

This example is adapted from P2795. Written at the start of a declaration the attribute applies to all declarators; written after a declarator's name it applies only to that one. [[dcl.attr.indet#1]] only allows it on definitions of block variables with automatic storage duration and on function parameters; ¶2 requires the attribute on a parameter to appear on the function's first declaration, and if one translation unit's first declaration has it and another's doesn't, the program is ill-formed, no diagnostic required.

There were three candidate syntaxes for opting out: an attribute `int x [[foo]];`, a keyword `int x = noinit;`, and a library type `int x = std::uninitialized;`. According to P2795's record, neither of the first two reached consensus in committee polls, and the library type got only weak support. The paper still chose the attribute, on the grounds that the other two are entirely new mechanisms with no implementation experience, while attributes are a mature mechanism, and code using one compiles in any version since C++11 (Clang also long had `[[clang::uninitialized]]` with the same function). An attribute can also be ignored: a program that is correct with the attribute is still correct without it; the attribute only makes code less forgiving.

The choice of name was influenced by a pitfall P2795 calls the **accidental self-documentation trap**: if the opt-out syntax looks like it is documenting a deliberate lack of initialization, teams whose coding standards require every variable to have an initializer will treat it as the proper way to write things:

```cpp
int x;            // the old C++23 way
int x = noinit;   // hypothetical syntax: looks like a more proper way of saying the same thing
```

The second line actually turns the safety mechanism off. So `[[uninitialized]]` (the name proposed by [[P0632R0]]), `noinit` and `for_overwrite` were all rejected, and `not_zeroed` would imply that the erroneous value is 0. In the end `indeterminate` was chosen: it matches the term used in the core wording, and it is unfamiliar enough that users need to look up what it means first.

P2795 provides no feature-test macro, on the grounds that it adds no user-facing feature; when needed, check for the attribute with `__has_cpp_attribute(indeterminate)`. This attribute value was initially left out and later added to the table in [[cpp.cond]] by [[CWG3020]], with the value `202403L`.

## Wording

The subclauses changed by P2795R5 are listed below, with ¶ numbers as in the current draft:

| Subclause | Change |
|---|---|
| [[defns.erroneous]] | New term "erroneous behavior"; the note in [defns.undefined] used to say erroneous construct and erroneous data, changed to incorrect and invalid to free up the word |
| [[intro.compliance.general#2]] footnote 3 | A correct execution can contain UB and erroneous behavior |
| [[intro.abstract#6]], ¶7 | Erroneous behavior allows diagnosis and termination; diagnosis is recommended; false positives allowed |
| [[basic.indet]] | Title changed to indeterminate and erroneous values; ¶1 distinguishes the two kinds of initial value, ¶2 makes reading an erroneous value erroneous behavior and extends the exceptions for `unsigned char` and `std::byte` to erroneous values |
| [[conv.lval#3]] ¶3.3 | Still UB when the value representation is not valid for the type |
| [[expr.const.core#2]] ¶2.8, [[expr.const.const#4]] | Erroneous behavior cannot occur in constant evaluation, and the result of a constant expression cannot contain erroneous values |
| [[dcl.attr.indet]] | New `[[indeterminate]]` |
| [[bit.cast#3]] | Erroneous bits in the source map to the result; when the destination is `unsigned char` or `std::byte` they are passed through as-is, otherwise it is erroneous behavior and the result is copied bitwise but no longer contains erroneous values |
| Note in [[class.base.init#9]] | Members not initialized by a constructor have indeterminate or erroneous values |

The constant-evaluation part already works as expected with Clang 23:

```cpp title="constexpr-read.cpp" error
constexpr int f() {
  int x;
  return x;   // reads an erroneous value during constant evaluation
}
constexpr int v = f();  // error: not a constant expression
```

Clang reports read of uninitialized object is not allowed in a constant expression. This already held in C++23: reading an indeterminate value is UB, which likewise cannot appear in constant evaluation.

This change has no Annex C entry. It turns UB into defined behavior and does not change the meaning of any correct program; the entry in [[diff.cpp23]] related to erroneous behavior is a different matter: calling `realloc` with a non-null pointer and size 0 is also specified as erroneous behavior ([[c.malloc]]).

### A later fix: erroneous values propagate (P3684)

The original [intro.abstract] in P2795R5 allowed the implementation to terminate the program at an unspecified time after erroneous behavior occurred. This left room for implementations like MemorySanitizer: it instruments machine code, and often does not report the read itself but only the branch that depends on the value, which may be far from the read.

[[P3684R1]] points out the cost of that wording: once a program has executed erroneous behavior, it may be terminated at any moment afterwards, even while it is doing something completely unrelated. That makes programs hard to reason about, and gets in the way of extending erroneous behavior to other situations, for example unifying it with the semantics of contract violations (for contracts see [[papers/contracts]]). Its fix is to make erroneous values sticky, replacing delayed termination with propagation:

- [[intro.abstract#6]] drops the part about some unspecified later time; the implementation may diagnose or terminate only at the operation that executes erroneous behavior;
- [[basic.indet#2]] gains a new opening sentence: for a built-in operator producing a prvalue, if any operand that is evaluated and is not a discarded-value expression produces an erroneous value, the result is also an erroneous value; and the result of reading an erroneous value changes from not being an erroneous value to being that same erroneous value.

```cpp title="propagate.cpp" eb
int g(bool c) {
  int x;                // erroneous value
  int y = x * 0;        // erroneous behavior; y is erroneous too
  bool t = c && x > 0;  // x > 0 is not evaluated when c is false
  return t ? 1 : y;     // returning y: erroneous behavior
}
```

`x * 0` is mathematically independent of `x`, but P3684 still makes the result erroneous: enumerating in the standard all the cases like multiplying by 0 or taking modulo 1, where the result does not depend on an operand, would be too complicated, and floating-point NaN and integer trap representations would break that kind of reasoning anyway. Implementations may be more lenient on their own; MemorySanitizer in fact treats the result of multiplying by 0 as a clean value. Operands of short-circuit operators that are not evaluated do not take part in propagation. With this, when MemorySanitizer reports at a downstream branch, that branch is itself using an erroneous value, so it counts as terminating where the erroneous behavior happens. P3684R1 was merged as the resolution of national body comments on C++26, and [[basic.indet#2]] in the current draft already has the fixed wording.

## Costs and current status

### Performance

The cost of filling depends on how big the object is and whether the fill can be proven redundant. For scalars and small objects that are then fully assigned, the optimizer can usually eliminate the fill, or it costs only one or two extra instructions; the cost is most visible when only a small part of a large buffer is used. The function below was measured with Clang 23:

```cpp
[[gnu::noinline]] int work() {
  char buf[4096];   // only the first 16 bytes are used
  fill(buf, 16);    // fill and sum are defined in another translation unit
  return sum(buf, 16);
}
```

| Compiler options (`-O2`) | Per call |
|---|---|
| No fill (`=uninitialized`, the default) | About 4.6–5.0 ns |
| `-ftrivial-auto-var-init=zero` | About 54–83 ns |
| `-ftrivial-auto-var-init=pattern` | About 55–90 ns |
| `=pattern`, `buf` marked `[[clang::uninitialized]]` | About 4.7–5.9 ns |
| `=pattern`, buffer reduced to 16 bytes | About 4.8–5.1 ns |

The data comes from Clang 23 on an Apple M2 Pro, taking the fastest of 7 rounds for each configuration, repeated 3 times. The machine was under heavy load during measurement (load average over 100), so the absolute values are noisy and only the orders of magnitude should be read: filling 4 KB made this function about ten times slower, opting out with the annotation fully restored it, and with a small buffer there was no visible difference. In the assembly under `=pattern`, `work` has an extra call to `memset`, which disappears with the annotation.

This does not contradict the overall overhead of under 0.5% on large codebases that P2723 reports: most functions do not have large stack buffers. The few hot functions are exactly what `[[indeterminate]]` is for.

### Implementation status in Clang 23

At the time of writing, Clang's C++ status page marks both P2795R5 and P3684R1 as not implemented. Measurements with Clang 23.1.3:

| Check | Result |
|---|---|
| `-std=c++2c -O2`, `int x; if (c) x = 42; return x;` | Returns 42 regardless of `c`, same as `-std=c++23` |
| `-std=c++2c -O2`, `int x; return x;` | Does not write the return register, returning whatever was left in it before the call |
| The key-leaking program above, default options | Prints `hunter2-secret` |
| Same program, `-ftrivial-auto-var-init=zero` / `=pattern` | Prints an empty string / 15 `0xAA` bytes |
| `-fsanitize=address,undefined` | Does not detect uninitialized reads |
| `-fsanitize=memory` | Not supported on the arm64 macOS target |
| `[[indeterminate]]` | Warns unknown attribute and ignores it; `__has_cpp_attribute(indeterminate)` is 0 |
| `[[clang::uninitialized]]` | Opts a variable out under `-ftrivial-auto-var-init`, with the same effect `[[indeterminate]]` intends |
| Reading an uninitialized variable in constant evaluation | Error |

On its own, the row returning 42 could still be argued over: is 42 the value the implementation chose? But returning register leftovers and leaking the key clearly depend on program state, violating [[basic.indet#1]] ¶1.2. So Clang 23 with default options does not yet conform to C++26 on this point. To get the C++26 guarantee you currently have to add `-ftrivial-auto-var-init=zero` or `=pattern` explicitly; P2795 itself lists these two options as existing implementations, except that they don't diagnose. `-Wuninitialized` only catches obvious cases within a single function and does not report examples like the one above that read an array through `printf`. GCC and MSVC were not tested.

### How to write code today

- Write initializers. `int x = 0;` says you need 0; in C++26 `int x;` is still a variable waiting to be written, and reading it before writing is still a bug, only with bounded consequences.
- Use `-ftrivial-auto-var-init=pattern` in test builds so erroneous values are easy to spot; on platforms where MemorySanitizer is available, use it to find reads. Until C++26 semantics are supported, consider `=zero` or `=pattern` for production builds.
- Only add `[[indeterminate]]` (for now together with `[[clang::uninitialized]]` on Clang) when you are sure a large buffer will be completely written first and profiling shows the fill is a hot spot.
- For `bool`, enumerations and pointers, erroneous values give no sense of safety: invalid bit patterns are still UB, and dereferencing a null or pattern pointer is still UB.

For when the various forms of initialization leave an object uninitialized, see [[topics/initialization]]; for a full comparison of UB, erroneous behavior and the other categories of behavior, see [[topics/undefined-behavior]]; for how the library handles out-of-bounds and similar errors with hardened preconditions, see [[papers/library-hardening]].

## Questions

!!! question "1. Do parameters have erroneous values too?"
    ```cpp
    struct T { T() {} int x; };
    int h(T t) { return t.x; }
    int main() { return h(T()); }
    ```
    In C++26, what is the behavior of `return t.x;`? What if the parameter is written `T t [[indeterminate]]`?

<details markdown="1">
<summary>Answer</summary>

`T`'s default constructor is user-provided but does not initialize `x`, so `x` keeps the initial value it had when storage was obtained (the note in [[class.base.init#9]]). The parameter `t` has automatic storage duration, so by [[basic.indet#1]] ¶1.2 its bytes have erroneous values, and reading `t.x` is erroneous behavior. With `[[indeterminate]]`, ¶1.1 applies instead: the bytes have indeterminate values and reading is UB. This is exactly the example in [[dcl.attr.indet#3]]. P2795 excluded parameters for a while in R3 and restored them in R4.

</details>

!!! question "2. Why doesn't `new int` get an erroneous value too?"
    Neither P2795 nor P2723 changed the initial value of objects of dynamic storage duration. From the implementation's point of view, where is the difficulty?

<details markdown="1">
<summary>Answer</summary>

Filling automatic variables happens inside a function, where the compiler can see later writes and eliminate most redundant fills. Heap allocation would require the allocator to fill every block, which the compiler can hardly prove redundant, and large allocations are often going to be completely overwritten anyway, a cost that is hard to eliminate. P2723 says in its caveats that automatic initialization of heap memory is still a newer area of research and deployment, with different codebases making different trade-offs and no accepted approach. So in C++26 the value of `new int` is still indeterminate, and reading it is still UB ([[basic.indet#1]] ¶1.1).

</details>
