---
title: Implementation compliance and the abstract machine
summary: "What a compiler must do with a program: which errors it must report and which it may ignore; what the compiled program has to behave like (the abstract machine, observable behavior, the as-if rule); why undefined behavior can affect code before it, and how C++26 bounds that."
updated: 2026-10-18
---

!!! tldr
    - When a program violates an ordinary rule, the compiler only has to issue one diagnostic, and a warning counts. Only `#error`, a failed `static_assert`, and a contract check terminated during constant evaluation must make compilation fail.
    - Some rules are marked as requiring no diagnostic (for example the ODR across translation units). A program violating them may compile without a word, and its run-time behavior has no guarantees.
    - A compiled program only has to match the abstract machine in observable behavior: volatile accesses, data written to files, and the ordering of prompts on interactive devices. The optimizer may rewrite everything else; this is the as-if rule.
    - The optimizer may assume undefined behavior does not happen. Since C++26, output that precedes UB and is protected by an observable checkpoint must actually be produced.
    - Default modes such as `-std=gnu++2c` are usually not conforming modes. Extensions may not change the meaning of valid programs.

## The compiler only gave a warning: does that conform? [intro.compliance.general]

```cpp run error
void f(int n) {
  int a[n];      // error: C++ has no variable-length arrays (VLAs)
  (void)a;
}
int main() { f(3); }
```

In C++ an array bound must be a constant expression, so this code is not valid. But Clang 23 gives only a warning (`-Wvla-cxx-extension`) and then produces an executable as usual. That fully conforms to the standard. Explaining why needs a few terms first.

The standard specifies requirements on the **implementation**: the compiler, standard library and execution environment as a whole, see [[intro.scope]]. A program written according to all the syntax and semantic rules is **well-formed**; otherwise it is **ill-formed** ([[defns.well.formed]], [[defns.ill.formed]]). A **diagnostic message** is a kind of message output by the implementation, whose exact form the implementation decides; errors and warnings both count ([[defns.diagnostic]]).

### By default every rule must be diagnosed (¶1)

¶1 The standard calls all syntax and semantic rules, except two kinds, **diagnosable rules**. The two excluded kinds are rules explicitly marked "no diagnostic is required", and rules described as resulting in undefined behavior.

So the standard need not add "violations shall be diagnosed" after every rule. When you read a shall rule such as "*X* shall not be a reference type", as long as there is no "no diagnostic is required" nearby, a program that violates it is ill-formed, and the compiler must report it.

### Three possible outcomes for a program (¶2)

¶2 The standard often phrases requirements as requirements on programs, such as "a program shall contain exactly one `main`", because that is easier to understand. ¶2 specifies what such phrasing actually means, that is, what it requires of the implementation:

| The program | What the implementation must do |
|---|---|
| ¶2.1 violates no rule in Clauses 5–33 and Annex D | Accept and execute it correctly, unless it exceeds the implementation's resource limits |
| ¶2.2 violates a rule for which no diagnostic is required | Nothing at all |
| ¶2.3 otherwise violates a diagnosable rule (and a few other cases below) | Issue at least one diagnostic message |

Besides violating a diagnosable rule, ¶2.3 lists three more cases that must be diagnosed: the source file contains a `#warning` directive; it uses a construct marked conditionally-supported that this implementation does not support; and one kind of C++26 contract violation during constant evaluation (see below).

Executing correctly does not mean nothing can go wrong. Footnote 3 explains that a well-formed program can still have undefined behavior for some inputs, for instance when the user enters 0 as a divisor. Well-formedness is a static property of the program, unrelated to run-time data.

!!! note "Errors during template argument deduction"
    Note 1 to ¶2 points out that during template argument deduction and substitution, certain errors that would otherwise need a diagnostic are handled differently ([[temp.deduct]]). This is SFINAE: a substitution failure just discards that candidate function and is not an error.

### A diagnostic is not a rejection (¶2.4–¶2.6)

Back to the opening question. For a program that violates a diagnosable rule, the standard only requires at least one diagnostic; it does not require compilation to fail. As we'll see when discussing extensions, the standard also explicitly allows an implementation to go on compiling such a program after diagnosing it. Clang gives a warning for the VLA and then produces an executable, satisfying both obligations.

The standard requires rejection in only three cases, all of them ways for the programmer to ask for compilation to fail:

- ¶2.4 the program contains an `#error` directive;
- ¶2.5 it has a failed `static_assert` ([[dcl.pre]]);
- ¶2.6 {{c++26}} a contract assertion evaluated with a terminating semantic is violated during constant evaluation (see below).

<div class="compare" markdown="1">

```cpp run ok
#warning "this header is deprecated"
// must be diagnosed (¶2.3.2),
// but the program is well-formed and may be accepted
int main() {}
```

```cpp run error
static_assert(sizeof(int) == 2,
              "need a 16-bit int");
// shall not be accepted (¶2.5)
int main() {}
```

</div>

So compiling successfully never proves code valid. If you want every diagnosable violation to fail compilation, use `-pedantic-errors` with Clang and GCC, and `/permissive-` with MSVC.

!!! note "`static_assert(false)` in a template"
    A `static_assert` evaluated in a template definition does not count as failed; it fails only if it evaluates to `false` at instantiation ([[dcl.pre#13]]). [[temp.res.general#6]] also ignores failed `static_assert`s when deciding whether a template can produce a valid specialization. C++23's [[P2593]] introduced both points, so you can now write `static_assert(false, ...)` directly in a template that should never be instantiated:

    ```cpp run ok
    template<class T>
    void f() {
      static_assert(false, "f should not be instantiated");   // OK: f is never instantiated
    }
    int main() {}
    ```

### Rules that need no diagnostic (IFNDR)

Some rules are hard or even impossible for a compiler to check. The most typical is the ODR: the definitions of the same inline function in every translation unit (a separately compiled source file together with the headers it includes) must be identical. The compiler sees one translation unit at a time and cannot see the conflict.

```cpp title="a.cpp"
inline int answer() { return 42; }
int from_a() { return answer(); }
```

```cpp title="b.cpp" ifndr
#include <cstdio>
inline int answer() { return 0; }   // differs from the definition in a.cpp: violates the ODR
int from_a();
int main() { std::printf("%d %d\n", from_a(), answer()); }
```

With Clang 23, neither compiling nor linking gives any message. At `-O0` it prints `42 42`, at `-O2` it prints `42 0`, and with the two files swapped on the command line, `-O0` prints `0 0`.

Such rules are marked "no diagnostic is required" in the text, and a program violating them is called **ill-formed, no diagnostic required**, or **IFNDR** for short. Under ¶2.2, the standard places no requirements on such a program: the compiler may report an error or not, and the generated program may do anything. Annex G [[ifndr]] collects all such rules.

!!! lawyer "IFNDR takes precedence over everything"
    ¶2.3 begins with "Otherwise", so it applies only when ¶2.2 does not. So if a program has both an IFNDR violation and a type error, ¶2.2 applies, and the standard doesn't even require a diagnostic for the type error. Real compilers still report it, of course, but that is a matter of quality of implementation, not conformance.

### Contract violations during constant evaluation (¶2.3.4, ¶2.6) {{c++26}}

C++26 introduced **contract assertions**: `pre` and `post` written on function declarations, and the statement `contract_assert` ([[basic.contract]]). Each evaluation of a contract assertion uses one of four semantics: ignore, observe, enforce and quick-enforce. The last three check the condition and are called checking semantics; enforce and quick-enforce terminate the program on violation and are called terminating semantics. Which one is used is up to the implementation, usually controlled by compiler options ([[basic.contract.eval]]).

When a contract is violated during constant evaluation, the outcome depends on the semantic of that evaluation:

```cpp
constexpr int half(int n) pre(n % 2 == 0) { return n / 2; }
constexpr int a = half(4);   // OK
constexpr int b = half(3);   // contract violation:
                             //   enforce / quick-enforce → shall not be accepted (¶2.6)
                             //   observe → must be diagnosed (¶2.3.4), may be accepted, b == 1
                             //   ignore  → not checked, b == 1
```

The intent of observe is to report and then continue, so at compile time it shows up as a required diagnostic, usually a warning, rather than a hard error. At the time of writing Clang 23 does not support the contract syntax yet; this code was analyzed from the standard's wording and not verified by compiling it.

### shall, should, may and can in the standard

When reading the text, keep these words apart. The standard uses them according to ISO drafting rules:

| Word | Meaning | Effect |
|---|---|---|
| shall / shall not | Requirement / prohibition | For programs: a violation is ill-formed (unless marked no diagnostic required, or resulting in UB); for implementations: a conformance requirement |
| should / should not | Recommendation | Does not affect conformance; common in *Recommended practice* paragraphs |
| may / need not | Permission | Grants freedom to the implementation |
| can / cannot | Possibility, capability | States a fact; common in notes; not a requirement |

Notes, examples and footnotes are only informative and cannot by themselves serve as normative grounds. The library clauses have a finer set of terms, such as *Mandates* (ill-formed if not met), *Constraints* (does not participate in overload resolution if not met) and *Preconditions* (UB if violated), defined in [[structure.specifications]].

## The abstract machine and the as-if rule [intro.abstract]

### Generated code need not follow the source

```cpp run ok
int sum_to(int n) {
  int s = 0;
  for (int i = 1; i <= n; ++i) s += i;
  return s;
}
```

When Clang 23 compiles this function at `-O2`, the generated code has no loop; it computes n(n+1)/2 directly with multiplication and shifts. The source says to loop n times, yet the compiler doesn't loop. This is allowed, and the reason is in [intro.abstract].

¶1 The semantic descriptions in the standard define a **parameterized nondeterministic abstract machine**. The standard does not require implementations to mirror the structure of the abstract machine; an implementation need only emulate the abstract machine's observable behavior, and only its observable behavior.

Footnote 5 names this principle the **as-if rule**: an implementation may disregard any requirement of the standard as long as the result is as if the requirement had been obeyed, as far as can be determined from the program's observable behavior. For example, a subexpression whose value is not used and that has no side effects affecting observable behavior need not be evaluated. The loop in `sum_to` and the closed-form formula are indistinguishable in observable behavior, so one can replace the other.

!!! tip "Judge UB by the abstract machine, not the assembly"
    Descriptions in the standard like "A is evaluated before B", "the object is created here" or "this value is read" all refer to the abstract machine. The generated machine code is answerable only for observable behavior. So arguments like "there is no memory read in the assembly, therefore it isn't UB" or "there is a load instruction here, therefore an access happened" don't hold.

### Three kinds of freedom in the abstract machine (¶2–¶4)

The standard does not specify one fixed machine; it leaves three kinds of freedom.

¶2 The first is parameters. Some aspects are decided by the implementation and are called **implementation-defined behavior**, such as `sizeof(int)`; others are properties of the implementation, such as padding in class types. The implementation must document its choices for implementation-defined behavior. Fixing these parameters gives the abstract machine that corresponds to this implementation, which the standard calls the **corresponding instance**.

¶3 The second is nondeterminism. Some aspects are **unspecified behavior**; the standard usually gives a set of allowed outcomes, the implementation may pick any of them each time, and it need not document the choice. An example is whether `a()` or `b()` is evaluated first in `f(a(), b())` ([[expr.call]]). So the same program with the same input can have more than one possible execution even on the same abstract machine.

¶4 The third is **undefined behavior** (UB), such as attempting to modify a const object. The standard imposes no requirements on such operations ([[defns.undefined]]).

### Observable behavior (¶8)

¶8 A program's **observable behavior** consists of only three things:

- ¶8.1 accesses through volatile glvalues are evaluated strictly according to the rules of the abstract machine;
- ¶8.2 data delivered to the host environment to be written into files;
- ¶8.3 input and output on interactive devices: prompting output must actually be delivered before the program waits for input. What counts as an interactive device is implementation-defined.

The contents of memory, execution time and how many times a function is called are not among them. So the as-if rule allows changing all of them arbitrarily, and almost every optimization (inlining, constant propagation, dead-code elimination, loop transformations) relies on it. It is also why abstractions like iterators, smart pointers and lambdas can vanish completely after optimization.

volatile is the only means at the language level to require the compiler to keep every memory access; it is used mainly for memory-mapped hardware registers:

<div class="compare" markdown="1">

```cpp run ok
int plain;
void store_plain() {
  plain = 1;
  plain = 2;   // may be merged into a single write of 2
}
```

```cpp run ok
volatile int reg;
void store_volatile() {
  reg = 1;
  reg = 2;     // must be two writes, in this order
}
```

</div>

At `-O2`, Clang 23 generates one store for the left and two for the right. volatile has nothing to do with multithreading: it provides no atomicity and establishes no ordering between threads; use `std::atomic` for inter-thread communication ([[atomics]]).

What ¶8.3 guarantees is prompt first, then wait. In `std::cout << "Password: "; std::cin >> pw;`, the prompt is always shown before waiting for input. The standard library achieves this by tying `cin` to `cout`: `cout` is flushed before reading from `cin` ([[istream.sentry]]).

## Undefined behavior and time travel [intro.abstract]

### The optimizer may assume UB does not happen

```cpp run ub
int g(int x) {
  int y = x + 1;           // signed overflow when x == INT_MAX: UB
  if (y < x) return -1;    // can only be true if overflow happened
  return y;
}
```

At `-O2`, Clang 23 compiles `g` into a single add; the overflow check is deleted entirely. The reasoning: the implementation is answerable only for executions without UB, and in an execution without UB, `y < x` is always false. The correct approach is to check `x == INT_MAX` before the addition, or to use saturating addition, `std::saturating_add` ([[numeric.sat]]).

### UB can affect code before it

In C++23 and earlier, [intro.abstract] said: if a possible execution contains an undefined operation, the standard places no requirement on the implementation executing that program, not even with regard to operations preceding the first undefined operation. This is what is commonly called UB time travel.

```cpp run ub
#include <cstdio>
int read(int* p) {
  std::puts("about to read");
  return *p;                 // p is null: UB
}
int main(int argc, char**) {
  int* p = argc > 5 ? new int(1) : nullptr;
  return read(p);
}
```

In our tests, with output redirected to a file, the program ended with SIGSEGV and the file was empty. When redirected to a file, stdout is fully buffered; `puts` only put the string into the program's internal buffer, and the buffer was not flushed when the process crashed. Under the C++23 wording, even if the data had been written out, the standard would not guarantee it appears, because operations before the UB are not protected either. A compiler may also infer from UB that must happen later that some branch is never taken, and delete the output in that branch.

### Observable checkpoints (¶5–¶6) {{c++26}}

C++26 put a boundary on time travel through [[P1494]].

¶5 Certain events in program execution are called **observable checkpoints**. Note 1 gives two examples: a call to `std::observable_checkpoint()` ([[utility.undefined]]), and certain points in the evaluation of contract assertions.

¶6 The **defined prefix** of an execution consists of the operations *O* such that for every undefined operation *U* there is a checkpoint *C* where *O* happens before *C* and *C* happens before *U*. In other words, an operation is in the defined prefix as long as a checkpoint separates it from every later UB.

!!! std
    A conforming implementation executing a well-formed program shall produce the observable behavior of the defined prefix of one of the possible executions of the corresponding instance of the abstract machine with the same program and the same input.

When an implementation executes a well-formed program, it must produce the observable behavior of the defined prefix of one possible execution of the corresponding instance with the same program and the same input. If the chosen execution contains an undefined operation, the implementation may produce arbitrary additional observable behavior after that point.

Look at this sentence in two cases:

- For an execution without UB, all operations are in the defined prefix, and the implementation must produce the observable behavior of the whole execution. This is the ordinary as-if rule.
- For an execution with UB, the observable behavior that precedes the last checkpoint before the UB must actually be produced; the part after the checkpoint and before the UB is still unprotected.

Data races ([[intro.races]]) are a special case. Note 2 explains that the UB they produce occurs on all participating threads.

The following events are checkpoints:

| Checkpoint | Source |
|---|---|
| Calling `std::observable_checkpoint()` | [[utility.undefined]] |
| Before a contract assertion is evaluated with a checking semantic, and after a contract-violation handler returns normally | [[basic.contract.eval]] ¶6, ¶15 |
| The return of a C stdio function call that delivers data to the host environment to be written to a file | [[cstdio.syn]] ¶2 |
| After `basic_filebuf::overflow` writes data out; after `std::print` writes directly to a terminal | [[filebuf.virtuals]], [[print.fun]] |

Delivering to the host environment means the data has actually left the program. `puts` returns after putting the data into a buffer; that is not delivery, so this return is not a checkpoint. In the example above, if you add `std::fflush(stdout);` after `puts`, the return of `fflush` is a checkpoint, "about to read" must appear in the output, and the compiler can no longer delete or delay it on account of the later UB.

`std::observable_checkpoint()` itself does not flush any buffer; it only guarantees that observable behavior that has already happened before it is not invalidated by later UB. At the time of writing, Clang 23 with libc++ does not provide this function yet.

!!! warning "A volatile access is observable behavior, but not a checkpoint"
    If a volatile write is immediately followed by UB with no checkpoint in between, that write is not in the defined prefix and is just as unprotected.

### Erroneous behavior (¶6–¶7) {{c++26}}

C++26 also introduced **erroneous behavior** (EB): behavior the standard considers incorrect but still defines ([[defns.erroneous]]). The typical example is reading an uninitialized automatic variable, which in C++26 reads an erroneous value instead of being UB ([[basic.indet]]).

The last sentence of ¶6 says that when execution reaches erroneous behavior, the implementation may issue a diagnostic, and may also terminate the program. ¶7 recommends that implementations issue a diagnostic when such an operation is executed. Note 3 adds that an implementation may also diagnose at compile time, if it determines under its own assumptions that erroneous behavior is reachable, at the cost of possible false positives.

| | UB | EB |
|---|---|---|
| Behavior afterwards | Anything | Continues as defined, or diagnoses, or terminates |
| Observable behavior before it | Only what precedes a checkpoint is protected | All protected; EB is not an undefined operation |
| Can the optimizer assume it doesn't happen | Yes | No |

## Kinds of implementation [intro.compliance.general]

### Hosted and freestanding (¶7)

¶7 Implementations are either **hosted implementations** or **freestanding implementations**. A freestanding implementation is one in which execution may take place without the benefit of an operating system, common in kernel and embedded development.

- A hosted implementation supports all the facilities described by the standard.
- A freestanding implementation supports the whole language of Clauses 5–15, but of the standard library only the subset listed in [[compliance]] is required. Exceptions, RTTI and virtual functions must all be supported at the language level. The `-fno-exceptions` and `-fno-rtti` commonly used in embedded toolchains are non-conforming dialects.
- In a freestanding implementation, how a program starts and terminates, and whether `main` is required, are implementation-defined ([[basic.start.main]]).
- The macro `__STDC_HOSTED__` is 1 in a hosted implementation and 0 otherwise ([[cpp.predefined]]). Clang defaults to 1, and gives 0 with `-ffreestanding`.

### Hardened implementations (¶8) {{c++26}}

¶8 Whether an implementation is a **hardened implementation** is implementation-defined. In a hardened implementation, violating a hardened precondition of a standard library function results in a contract violation rather than UB.

```cpp run ub
#include <span>
#include <cstdio>
int main(int argc, char**) {
  int a[3] = {1, 2, 3};
  std::span<int> s(a);
  std::printf("%d\n", s[argc + 5]);   // violates the hardened precondition idx < size()
}
```

The hardened precondition of `std::span::operator[]` is `idx < size()` ([[span.elem]]). Under [[structure.specifications]] ¶3.5, a hardened implementation checks this condition with a terminating semantic before the function produces any other side effects; in a non-hardened implementation, violating it is UB.

Compiled with the default libc++ configuration in our tests, the program printed a garbage value. With `-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_FAST`, the program traps at the out-of-bounds access and terminates. The corresponding switch for libstdc++ is `-D_GLIBCXX_ASSERTIONS`. Hardening turns the most common class of memory-safety vulnerability, out-of-bounds access, from UB into guaranteed termination ([[P3471]]).

### Extensions (¶11)

¶11 An implementation may provide extensions, including additional library functions, provided they do not alter the behavior of any well-formed program. For a program that uses an extension and is ill-formed according to the standard, the implementation must issue a diagnostic; after diagnosing, it may compile and execute it as usual.

Conforming extensions usually use reserved names. Identifiers beginning with a double underscore, or with an underscore followed by an uppercase letter, are reserved to the implementation ([[lex.name]]); a well-formed program does not declare them, so extensions like `__builtin_expect` and `__int128` cannot conflict with any well-formed program. The VLA at the start is of another kind: it makes a piece of ill-formed code usable while issuing a diagnostic, so it conforms as well.

The two examples below each violate one of the two conditions in this paragraph:

<div class="compare" markdown="1">

```cpp run error
// GNU statement expression, not valid C++
int f() {
  return ({ int t = 1; t + 1; });
}
```

```cpp run ok
// well-formed: typeof is an ordinary identifier in C++
int typeof = 1;
int main() { return typeof; }
```

</div>

For the code on the left, Clang 23 gives no diagnostic by default; only with `-pedantic` is there a `-Wgnu-statement-expression` warning, so without `-pedantic` a required diagnostic is missing. The code on the right compiles normally with `-std=c++2c` but fails with `-std=gnu++2c`, because GNU mode treats `typeof` as a keyword, changing the meaning of a well-formed program.

So what conforms is usually a compiler plus a particular set of options, such as `-std=c++2c -pedantic-errors`, not the compiler's default mode.

Options like `-fwrapv` (signed overflow wraps as two's complement) and `-fno-strict-aliasing` define behavior for situations that were undefined and do not affect any well-formed program, so they are conforming extensions. Sanitizers that report and terminate when execution hits UB also conform, because after UB the implementation may do anything.

## Who provides the standard library (¶3–¶6) [intro.compliance.general]

¶3 For classes and class templates, the library clauses give only partial definitions; the private members are filled in by the implementation. libstdc++'s `std::vector` has `_M_impl`, libc++'s has `__begin_`; these are implementation details that programs cannot rely on.

¶4 For functions, objects and values, the library clauses give declarations, and the implementation provides definitions consistent with the descriptions. The signatures in the specification are descriptive; implementations may add default arguments or extra overloads ([[member.functions]], [[global.functions]]). This is also why taking the address of most standard library functions is unspecified or even ill-formed ([[namespace.std]]).

¶5 A translation unit uses names from the library by `#include`-ing a standard library header or `import`-ing the corresponding header unit ([[using.headers]]). Since C++23 you can also `import std;` ([[std.modules]]).

¶6 The templates, classes, functions and objects in the library have external linkage, and the implementation provides their definitions as needed at link time ([[lex.phases]]).

<details class="fine" markdown="1"><summary>Remaining wording</summary>

¶9 *Recommended practice*: implementations are encouraged to document the limits on the size and complexity of programs they can handle. Annex B [[implimits]] lists some quantities that may be limited and recommended minimums, such as 256 levels of nested compound statements. None of these are requirements; ¶2.1 already allows an implementation to reject a program for exceeding its limits.

¶10 An implementation may use a later version of Unicode than the one referenced in [[intro.refs]]; the version is implementation-defined. This affects which characters are allowed in identifiers ([[lex.name]]) and `std::format`'s width estimation.

¶12 Each implementation must provide documentation that lists all the conditionally-supported constructs it does not support and defines all locale-specific characteristics. Footnote 4 adds that this documentation also defines implementation-defined behavior. In practice the GCC manual has a dedicated C++ Implementation-Defined Behavior chapter, but no mainstream implementation lists all implementation-defined behavior completely.

</details>

## History

!!! history
    - Since C++98 the standard has had the as-if rule (as a footnote) and the three categories of implementation-defined, unspecified and undefined behavior, largely following the framework of the C standard. The abstract machine was originally described at the start of [intro.execution], and later became its own subclause [intro.abstract]; [intro.execution] itself moved to [[basic.exec]] in Clause 6.
    - Since C++11, conditionally-supported has been a formal category of construct.
    - C++23 standardized `#warning` and listed it in ¶2.3.2.
    - C++26 added erroneous behavior ([[P2795]]), contract assertions and their diagnostic requirements during constant evaluation ([[P2900]]), hardened implementations ([[P3471]]), and observable checkpoints and the defined prefix ([[P1494]]). The last of these replaced the wording that UB imposes no requirements even on the operations before it.

## Common misconceptions

!!! pitfall "If it compiles, the program is valid"
    The converse doesn't hold either. A well-formed program may get warnings, or even be rejected for exceeding implementation limits; an ill-formed program may be accepted after a diagnostic, and an IFNDR program may pass without any message at all.

!!! pitfall "After C++26, UB no longer time-travels"
    Time travel is only restricted. The defined prefix protects only the observable behavior before a checkpoint; output after the checkpoint and before the UB, such as data still in a buffer or a volatile write, is still unprotected. And a checkpoint protects only observable behavior, not program state.

!!! pitfall "Program exit is observable behavior"
    Program termination and the exit code are not among the three items of ¶8. The return value of `main` is handed to the host environment through `exit` ([[support.start.term]]). The difference between an infinite loop with no side effects and a program that returns immediately is handled by the forward progress guarantees of [[intro.progress]], not by ¶8.

## Questions

!!! question "Question 1"
    When the program below runs, `p` is null. Under C++26, is "start" guaranteed to be printed when stdout is a terminal (line-buffered)? What about when it is redirected to a file?
    ```cpp
    std::puts("start");
    *p = 0;
    ```

<details markdown="1">
<summary>Answer</summary>

When line-buffered, `puts` delivers the data to the host environment after outputting the whole line, and this return is an observable checkpoint ([[cstdio.syn]] ¶2), so "start" is in the defined prefix and must appear.

When redirected to a file, stdout is fully buffered; `puts` only puts the data into the buffer, its return is not a checkpoint, and "start" is not guaranteed to appear. To get the guarantee in both cases, add `std::fflush(stdout)` after `puts`. (When stdout is flushed is determined by the C standard and the implementation; the above assumes typical POSIX behavior.)
</details>

!!! question "Question 2"
    GCC's and Clang's `-std=gnu++2c` treats `typeof` as a keyword; Clang accepts GNU statement expressions by default without a diagnostic. Which part of ¶11 does each violate?

<details markdown="1">
<summary>Answer</summary>

The former violates the condition that extensions must not alter the behavior of well-formed programs: `int typeof = 1;` is well-formed C++, yet in GNU mode it becomes an error. The latter violates the requirement to diagnose ill-formed programs that use an extension. Both show that a compiler's default mode is usually not a conforming mode.
</details>
