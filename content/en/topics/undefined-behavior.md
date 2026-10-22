---
title: "Undefined behavior: the standard's view and the compiler's view"
summary: The standard says UB is behavior for which it imposes no requirements; compilers read that as something they may assume never happens. This page uses real Clang -O2 output to show the consequences, how C++26 puts bounds on it, and how to detect and mitigate it.
tags: UB, optimization, sanitizers, hardening, erroneous behavior, topic
updated: 2026-10-19
---

!!! tldr
    - The standard imposes no requirements on UB; from that, the optimizer assumes a correct program never executes UB, and then deletes checks, folds comparisons and removes loops.
    - The effects of UB can reach code before it. C++26's observable checkpoints protect only observable behavior already produced before the checkpoint, not ordinary computation.
    - C++26's erroneous behavior (reading an uninitialized local variable) is defined, and the optimizer may not assume it doesn't happen; but at the time of writing Clang still treats it as UB by default.
    - Constant evaluation rejects core-language UB and serves as a compile-time detector; at run time use UBSan, ASan, TSan and TySan, and hardened modes turn library UB into a deterministic termination.
    - `[[assume]]` and `std::unreachable()` are UB that programmers write on purpose, to pass information to the optimizer.

## Two readings

```cpp
bool always(int x) { return x + 1 > x; }
```

Clang 23 at `-O2` compiles this function to `return true;`. When `x == INT_MAX`, `x + 1` overflows, and it seems the result should be false, yet the compiler didn't consider this case.

The reason lies in the definition of UB. **Undefined behavior** (UB) is behavior for which this document imposes no requirements ([[defns.undefined]]). That sentence has two readings:

- The standard's reading is passive: the standard doesn't specify anything here; the implementation may ignore it, do something documented in a platform-specific way, or terminate the program.
- The compiler's reading is active: a correct program never executes UB, so when optimizing it may assume UB doesn't happen and draw conclusions about the program from that.

`always` is a product of the second reading: if `x + 1` doesn't overflow, `x + 1 > x` holds; if it does, it's UB and returning anything conforms to the standard. Returning `true` is correct in both cases. Nearly every surprising UB phenomenon comes from reasoning like this.

## Where UB sits among the behavior categories

| Category | When it happens | The implementation's obligation | Example |
|---|---|---|---|
| Ill-formed | Compile time | At least one diagnostic | Type mismatch |
| Ill-formed, no diagnostic required (IFNDR) | Compile time, often across translation units | None; the program has no meaning at all | ODR violation |
| Implementation-defined | Run time | Choose one of the permitted behaviors and document it | `sizeof(int)` |
| Unspecified | Run time | Choose one of the permitted behaviors, no need to document | Order of evaluation of function arguments |
| Erroneous {{c++26}} | Run time | The behavior is defined; a diagnostic is recommended, and termination is allowed | Reading an uninitialized automatic variable |
| Undefined | Run time | None | Signed overflow, null pointer dereference |
| Runtime-undefined | Run time | Same as UB; whether it makes an expression non-constant during constant evaluation is implementation-defined | Violating `[[assume]]` |

The exact definitions are in [[intro.defs]], and how they translate into requirements on implementations is in [[intro.compliance]]. Regarding UB itself, three sources should be distinguished:

- **Explicit UB**: the standard says so with wording such as "the behavior is undefined". The informative Annex F [[ub]] compiles the explicit core-language UB into a table, each entry with a stable identifier; for example, a strict aliasing violation is `[ub:expr.basic.lvalue.strict.aliasing.violation]`.
- **Implicit UB**: situations for which the standard gives no definition at all are UB as well (Note 1 of the definition). This kind of UB isn't in the annex.
- **Library UB**: violating a library function's *Preconditions* is UB (¶3.4 of [[structure.specifications#3]]). An out-of-bounds `vector::operator[]`, or giving `std::sort` a comparator that isn't a strict weak ordering, belong here. Hardened modes mainly target these.

## How compilers exploit UB

The optimizer isn't exploiting the program's mistakes; it just uses the premise that the program has no UB when reasoning. Every example below is real output from `clang++ -std=c++2c -O2` (arm64).

### Signed overflow

```cpp
bool always(int x)    { return x + 1 > x; }      // signed: overflow is UB
bool wraps(unsigned x){ return x + 1 > x; }      // unsigned: wraps modulo 2ⁿ, defined
int count(int n) {
  int c = 0;
  for (int i = 0; i <= n; ++i) ++c;
  return c;
}
```

```text
__Z6alwaysi:                 ; x + 1 > x is always true
	mov	w0, #1
	ret
__Z5wrapsj:                  ; false only when x == UINT_MAX
	cmn	w0, #1
	cset	w0, ne
	ret
__Z5counti:                  ; no loop: computes max(n, -1) + 1 directly
	orr	w8, w0, w0, asr #31
	add	w0, w8, #1
	ret
```

`count` is more representative. The compiler assumes `i` doesn't overflow, so it concludes the loop always terminates and runs exactly `n + 1` times, and the whole loop is replaced by a formula. When `n == INT_MAX`, `++i` would overflow; that input isn't something the compiler considers.

In real code, the biggest payoff from this rule comes from `int` loop variables on 64-bit platforms. Since they don't wrap, the compiler can promote them to 64-bit address offsets instead of sign-extending on every iteration.

`-fwrapv` makes signed arithmetic wrap as two's complement, turning this UB into defined behavior; it is a conforming extension ([[intro.compliance.general#11]]). Compiled with it, `always` goes back to an `x != INT_MAX` comparison.

### Null checks deleted

```cpp
int read(int* p) {
  int v = *p;            // if p is null: UB
  if (p == nullptr)      // compiler: it was already dereferenced above, so p can't be null
    return -1;
  return v;
}
```

```text
__Z4readPi:                              ; -O2
	ldr	w0, [x0]
	ret
__Z4readPi:                              ; -O2 -fno-delete-null-pointer-checks
	cbz	x0, LBB0_2
	ldr	w0, [x0]
	ret
LBB0_2:
	mov	w0, #-1
	ret
```

The null check is deleted entirely. The Linux kernel has had a vulnerability with this pattern: dereference first, check for null later; the check was optimized away, and in the kernel address 0 may be mapped, so the dereference doesn't crash. The kernel has since been compiled with `-fno-delete-null-pointer-checks`.

### Infinite loops without side effects

[[intro.progress#1]] allows implementations to assume every thread eventually does one of the following: terminates, calls `std::this_thread::yield`, calls a library I/O function, performs a volatile access, performs an atomic or synchronization operation, or continues executing a trivial infinite loop (see below). A loop that does nothing and never terminates violates this assumption, and the compiler may assume it doesn't run forever:

```cpp run title="fermat.cpp" ub
#include <cstdio>
bool fermat(unsigned limit) {        // search [1, limit] for a counterexample to a³ + b³ == c³
  for (unsigned a = 1;; a = a % limit + 1)
    for (unsigned b = 1; b <= limit; ++b)
      for (unsigned c = 1; c <= limit; ++c)
        if (a*a*a + b*b*b == c*c*c) return true;
}
int main() {
  if (fermat(1000)) std::puts("Fermat disproved!");
  else std::puts("Fermat holds");
}
```

```text
$ clang++ -std=c++2c -O2 fermat.cpp && ./a.out
Fermat disproved!
```

`fermat` is compiled to `mov w0, #1; ret`. The reasoning: the loop's only exit is `return true`; the loop has no observable side effects, so by [[intro.progress#1]] it must terminate; so the function must return `true`. In fact, sums of cubes up to 1000 don't exceed 32 bits, so there are no spurious solutions from wraparound, and this loop never terminates.

#### Trivial infinite loops {{c++26}}

Intentional infinite loops like `while (true);` are common in embedded and operating system code, for example to wait here for a watchdog or an interrupt. [[P2809R3]] defines a **trivial infinite loop** in [[stmt.iter.general#3]]: the loop body is empty (`;` or `{}`), and the controlling expression is a constant expression that evaluates to `true`. Its body is treated as replaced by a call to `std::this_thread::yield`, and executing it counts as making progress (¶1.6 of [[intro.progress#1]]), so it is no longer UB.

```cpp
void spin()       { while (true) ; }                  // trivial infinite loop: defined in C++26
void spin2(int n) { while (n) ; }                     // condition not a constant expression: still UB when n != 0
void spin3()      { for (int i = 1; i > 0; ) { } }    // same: not a trivial infinite loop
```

Results with Clang 23, identical for `-std=c++23` and `-std=c++2c`:

```text
__Z4spinv:       LBB0_1: b LBB0_1      ; kept as a real infinite loop
__Z5spin2i:      ret                   ; loop deleted: returns directly when n != 0
__Z5spin3v:      brk #0x1              ; concludes UB is certain, emits a trap instruction
```

Clang kept empty loops with constant conditions even before P2809, so `spin` is an infinite loop in every language mode; here the standard is catching up with practice. `spin3` is proven never to terminate and to have no side effects, so this path is unreachable, and on Darwin a `brk` trap instruction is emitted.

### Calling a function that is never called

```cpp run title="never-called.cpp" ub
#include <cstdio>
static void (*action)() = nullptr;
static void format_disk() { std::puts("formatting disk..."); }
void never_called() { action = format_disk; }
int main() { action(); }          // calling a null function pointer: UB
```

```text
$ clang++ -std=c++2c -O0 never-called.cpp && ./a.out ; echo $?
139                                  # SIGSEGV
$ clang++ -std=c++2c -O2 never-called.cpp && ./a.out
formatting disk...
```

`action` has internal linkage and can only ever be assigned `nullptr` or `format_disk`. Calling a null pointer is UB, so in every defined execution, `action` in `main` can only be `format_disk`. So the optimizer turns the indirect call into a direct call, and a function that is never called gets executed.

## UB affects code before it

The effects of UB don't only reach code after it. C++23's [intro.abstract] states that if an execution contains an undefined operation, the standard places no requirement on the implementation executing that program, not even on operations preceding the first undefined operation. This is often called **time travel**: from the fact that UB would happen later, the compiler infers that this path isn't taken, and changes earlier behavior accordingly.

```cpp run title="time-travel.cpp" ub
#include <cstdio>
[[gnu::noinline]] int div_report(int a, int b, bool& was_zero) {
  was_zero = (b == 0);   // record first
  return a / b;          // then divide: UB when b == 0
}
int main(int argc, char**) {
  bool z;
  int q = div_report(7, argc - 1, z);   // run without arguments: b == 0
  std::printf("q=%d was_zero=%d\n", q, z);
}
```

```text
-O0                          q=0 was_zero=1
-O2                          q=0 was_zero=0
-O2 -fsanitize=undefined     time-travel.cpp:4:12: runtime error: division by zero
                             q=0 was_zero=1
```

At `-O2`, `div_report` compiles to:

```text
	strb	wzr, [x2]        ; was_zero = false, unconditionally
	sdiv	w0, w0, w1
	ret
```

The UB after the division rewrote the result of the assignment before it: since `a / b` is executed, `b` can't be 0, so `b == 0` is false. ARM64's `sdiv` gives 0 for division by zero without trapping, so the program doesn't crash; it just quietly gives a wrong answer.

### Observable checkpoints {{c++26}}

[[P1494]] introduced **observable checkpoints** ([[intro.abstract#5]]) and the **defined prefix** of an execution ([[intro.abstract#6]]). An operation is in the defined prefix as long as a checkpoint separates it from every later undefined operation, and the implementation must faithfully produce the observable behavior in the defined prefix. Calling `std::observable_checkpoint()` and actually delivering data to the host environment (for example, `fflush` returning) are checkpoints. The full rules and the details about buffers are in [[intro.compliance]].

Applied to the example above:

- `was_zero = …` is a write to ordinary memory, not observable behavior. Observable behavior consists only of volatile accesses, data delivered to files, and I/O on interactive devices ([[intro.abstract#8]]). So even in C++26 the `-O2` result conforms completely to the standard.
- If there were a `std::printf` before the UB followed by `std::fflush(stdout)`, that output would have to appear; the compiler couldn't erase it on the grounds that UB happens later.

!!! impl
    At the time of writing, the libc++ that ships with Clang 23 doesn't provide `std::observable_checkpoint` yet. In practice, Clang already doesn't time-travel across external calls that might not return (such as `fprintf`): replace `was_zero = …` in the example with `if (b == 0) std::fprintf(stderr, …);`, and that output is still kept at `-O2`. Checkpoints turn this restraint in practice into a guarantee of the standard.

## Erroneous behavior {{c++26}}

[[P2795R5]] introduced **erroneous behavior** (EB, [[defns.erroneous]]): behavior the standard deems incorrect but still defines, recommending that implementations diagnose it. Its main application in the core language is uninitialized automatic variables ([[basic.indet]]): their bytes have an **erroneous value**, determined by the implementation and independent of the program's state, and reading it is erroneous behavior rather than UB.

| | UB | EB |
|---|---|---|
| Program behavior | No requirements at all | Defined; the erroneous value is read |
| May the implementation diagnose? | Yes | Yes, and it's recommended (false positives allowed) |
| May the implementation terminate? | Yes | Yes |
| May the optimizer assume it doesn't happen? | Yes | No |
| Earlier observable behavior | Only what's before a checkpoint is protected | All of it is protected |
| During constant evaluation | Makes the expression non-constant | Likewise makes the expression non-constant (¶2.8 of [[expr.const.core#2]]) |

One exception: if the erroneous value isn't valid for the type (for example, certain bit patterns of `bool`), the lvalue-to-rvalue conversion is still UB ([[basic.indet#1]] Note 1).

The key difference is whether the optimizer may assume it doesn't happen. Look at what Clang 23 does with this function:

```cpp eb
int f(bool b) {
  int x;            // C++26: x has an erroneous value
  if (b) x = 1;
  return x;         // when b is false: erroneous behavior (C++23: UB)
}
```

```text
-std=c++2c -O2                                 mov w0, #1 ; ret      returns 1 regardless of b
-std=c++2c -O2 -ftrivial-auto-var-init=pattern b ? 1 : 0xAAAAAAAA
-std=c++2c -O2 -ftrivial-auto-var-init=zero    b ? 1 : 0
```

In the default configuration, Clang still optimizes reading an uninitialized variable as UB: the value read on the `b == false` path can be anything, so it picks 1 to merge the two paths. This example alone is debatable: a fixed 1 might count as an implementation-chosen value "independent of the program's state" ([[basic.indet#1]]). Clearer evidence is that `int x; return x;` directly returns whatever is left in a register, and that stale data left on the stack can be read out (see [[papers/erroneous-behaviour]]), all of which depends on the program's state. So at the time of writing, Clang 23 doesn't yet implement the semantics of EB under `-std=c++2c`; it is `-ftrivial-auto-var-init=pattern` or `zero` that produces the behavior EB intends. The compile-time `-Wsometimes-uninitialized` warning has long existed, and is exactly one form of the recommended diagnostic.

If you know for certain that a large buffer will be filled before it is read and want to avoid the cost of initializing it, C++26's `[[indeterminate]]` ([[dcl.attr.indet]]) opts out of EB. The annotated variable goes back to the old semantics: its value is indeterminate, and reading it is UB.

## UB written on purpose

UB can also be used to pass information to the compiler. C++23 provides two standardized tools:

```cpp ok
#include <utility>
int half(int x)     { return x / 2; }
int half_pos(int x) { [[assume(x >= 0)]]; return x / 2; }   // assumption false: runtime-undefined
int pick(int k) {
  switch (k) {
    case 0: return 10;
    case 1: return 20;
    default: std::unreachable();                             // UB if reached
  }
}
```

```text
__Z4halfi:        add w8, w0, w0, lsr #31 ; asr w0, w8, #1    ; correction for rounding negatives toward zero
__Z8half_posi:    lsr w0, w0, #1                              ; correction omitted
__Z4picki:        cmp w0, #0 ; csel w0, w9(10), w8(20), eq    ; no bounds check, no jump table
```

The `E` in `[[assume(E)]]` ([[dcl.attr.assume]]) isn't evaluated; if it would evaluate to `false` at that point, the behavior is runtime-undefined. The precondition of `std::unreachable()` ([[utility.undefined]]) is that false is true, so calling it is UB. Both translate "I guarantee this won't happen" into a premise the compiler can use. When the guarantee doesn't hold, it's UB you wrote with your own hands.

## Detection and mitigation

### Constant evaluation: a compile-time detector

The constant evaluator executes strictly by the rules of the abstract machine. ¶2.8 of [[expr.const.core#2]] says that if an evaluation would perform undefined or erroneous behavior as specified in chapters 4 through 15, the expression is not a core constant expression. Where a constant expression is required (`static_assert`, `constexpr` variables, template arguments), this means the compiler must report an error:

```cpp run title="consteval-ub.cpp" error
#include <climits>
constexpr int add(int a, int b) { return a + b; }
constexpr int at(const int* p, int i) { return p[i]; }
constexpr int sum4() {
  int a[4] = {1, 2, 3, 4};
  int s = 0;
  for (int i = 0; i <= 4; ++i) s += a[i];   // off-by-one error
  return s;
}
constexpr const int& dangle() { int x = 1; return x; }
constexpr int arr[3] = {1, 2, 3};
static_assert(add(INT_MAX, 1) > 0);
static_assert(at(arr, 3) == 0);
static_assert(sum4() == 10);
static_assert(dangle() == 1);
```

Clang 23's diagnostics (excerpt):

```text
note: value 2147483648 is outside the range of representable values of type 'int'
note: read of dereferenced one-past-the-end pointer is not allowed in a constant expression
note: read of dereferenced one-past-the-end pointer is not allowed in a constant expression
note: read of object outside its lifetime is not allowed in a constant expression
```

Write core algorithms as `constexpr` and run a few test cases at compile time with `static_assert`, and all core-language UB on the paths actually executed will be caught. There are three limitations:

- Library UB isn't necessarily caught: when a library precondition is violated, whether the expression is a core constant expression is unspecified ([[expr.const.core#4]]).
- Whether runtime-undefined behavior (such as violating `[[assume]]`) is diagnosed is implementation-defined ([[expr.const.core#3]]).
- `reinterpret_cast`, `memcpy` and inline assembly can't appear in constant evaluation at all, so UB involving them (such as strict aliasing) can't be detected this way; see [[topics/type-punning]].

### At run time: sanitizers

| Tool | Flag | Detects | Available on macOS arm64 | Typical overhead |
|---|---|---|---|---|
| UBSan | `-fsanitize=undefined` | Signed overflow, out-of-range shifts, null pointers, misalignment, out-of-bounds on statically sized arrays, `unreachable`, invalid `enum`/`bool` values, and more (vptr type errors need `-fsanitize=vptr` in addition; `undefined` doesn't include it here) | Yes | Low |
| ASan | `-fsanitize=address` | Heap, stack and global out-of-bounds, use-after-free, use-after-scope, use-after-return, double free | Yes | About 2× |
| MSan | `-fsanitize=memory` | Reads of uninitialized memory | No, only Linux and some other platforms | About 3× |
| TSan | `-fsanitize=thread` | Data races ([[intro.races#17]]) | Yes | 5–15× |
| TySan | `-fsanitize=type` | Strict aliasing violations ([[basic.lval#11]]) | Yes | High |

For MSan, Clang 23 reports "unsupported option '-fsanitize=memory' for target 'arm64-apple-darwin25.5.0'".

UBSan's output (`-O0 -fsanitize=undefined`):

```text
ub1.cpp:6:27: runtime error: signed integer overflow: 2147483647 + 1 cannot be represented in type 'int'
ub1.cpp:7:25: runtime error: shift exponent 32 is too large for 32-bit type 'int'
ub1.cpp:8:23: runtime error: index 4 out of bounds for type 'int[4]'
```

TSan on a program where two threads increment without a lock:

```text
WARNING: ThreadSanitizer: data race (pid=8655)
  Write of size 4 at 0x0001044b8090 by thread T1:
    #0 ... std::__1::__thread_proxy<...main::$_0...>(void*) ...
  Previous write of size 4 at 0x0001044b8090 by main thread:
    #0 main ...
  Location is global 'counter' at 0x0001044b8090 (race+0x10000c090)
```

The various ASan reports are in [[topics/dangling-references]]. Things to watch for when using them:

- ASan can't be combined with TSan, nor ASan with MSan (Clang: `'-fsanitize=address' not allowed with '-fsanitize=thread'`); UBSan can be combined with any of them.
- Sanitizers are dynamic tools and can only find UB that actually executes; coverage depends on the tests.
- Instrumentation changes optimization. The time travel example above prints `was_zero=1` under UBSan: it not only reports the UB but also changes the program's behavior. So no problems with sanitizers on doesn't prove there are none with them off.
- `-fsanitize-trap=undefined` makes UBSan execute a trap instruction directly when it detects a problem, with no runtime library needed; it can serve as minimal hardening in production.

### Hardening: turning library UB into deterministic termination

C++26 recognizes a form of implementation: the **hardened implementation** ([[intro.compliance.general#8]], [[P3471]]). Standard library functions can specify hardened preconditions, and in a hardened implementation violating them causes a contract violation and termination rather than UB (¶3.5 of [[structure.specifications#3]]). `vector::operator[]`, `span::operator[]`, `optional::operator*`, `string_view::front()` and others have such preconditions.

```cpp run title="hardening.cpp" ub
#include <cstdio>
#include <vector>
int main(int argc, char**) {
  std::vector<int> v{1, 2, 3};
  std::printf("%d\n", v[argc + 2]);    // out of bounds: violates operator[]'s hardened precondition
}
```

libc++ selects the hardening level with the macro `_LIBCPP_HARDENING_MODE`:

| Value | Meaning (according to the libc++ header comments) | Result for the example |
|---|---|---|
| `_LIBCPP_HARDENING_MODE_NONE` (default) | All run-time hardening checks off | Prints 0, a garbage value was read |
| `_LIBCPP_HARDENING_MODE_FAST` | Only security-critical, constant-time, very low-overhead checks | Exit code 133 (SIGTRAP) |
| `_LIBCPP_HARDENING_MODE_EXTENSIVE` | A superset of FAST, adding low-overhead checks against common logic errors | Exit code 133 (SIGTRAP) |
| `_LIBCPP_HARDENING_MODE_DEBUG` | All checks, including internal assertions; may be expensive, meant for testing | Prints the message below, exit code 134 (SIGABRT) |

```text
vector.h:414: libc++ Hardening assertion __n < size() failed: vector[] index out of bounds
```

What happens after a failed check is determined by the assertion semantic, which corresponds to the evaluation semantics of C++26 contracts: `_LIBCPP_ASSERTION_SEMANTIC_IGNORE`, `_OBSERVE`, `_QUICK_ENFORCE` (trap), `_ENFORCE` (log, then terminate). When not specified explicitly, FAST and EXTENSIVE use quick-enforce and DEBUG uses enforce, which is the difference between SIGTRAP and SIGABRT above. The header comments say that user selection of the assertion semantic is currently an experimental feature, and that the ignore semantic doesn't constitute a conforming hardened implementation.

The corresponding switch in libstdc++ is `-D_GLIBCXX_ASSERTIONS`.

## Questions

!!! question "Question 1"
    Why can an `unsigned` loop variable sometimes make a loop slower?

<details markdown="1">
<summary>Answer</summary>

Unsigned wraparound is defined. For a loop like `for (unsigned i = start; i != end; ++i) a[i] = …;`, the compiler must consider the possibility of `i` wrapping from `UINT_MAX` to 0; on a 64-bit platform it can't simply promote `i` to a 64-bit address offset, and it has a hard time computing the trip count. Overflow of a signed `int` is UB, so there's no such concern. This is the most frequently cited example of UB enabling performance. In practice, using `std::size_t`, which is as wide as a pointer, as the index avoids both problems.
</details>

!!! question "Question 2"
    Now that C++26 has introduced observable checkpoints, does time travel no longer exist?

<details markdown="1">
<summary>Answer</summary>

It still exists. The defined prefix protects only observable behavior, and only the part separated from the UB by a checkpoint. The `div_report` example above can still print `was_zero=0` under C++26: the write to `was_zero` isn't observable behavior, and the `printf` that reads it comes after the UB. Checkpoints only stop output already delivered to the outside world from being erased; they don't stop the compiler from rewriting earlier computation based on later UB.
</details>

!!! question "Question 3"
    If a `constexpr` function runs through successfully in a `static_assert`, does that show it has no UB at run time?

<details markdown="1">
<summary>Answer</summary>

It only shows there is no core-language UB or erroneous behavior for that set of arguments on that execution path (¶2.8 of [[expr.const.core#2]]). Other arguments may take other paths; violations of library preconditions aren't guaranteed to be diagnosed ([[expr.const.core#4]]); and `if consteval` or `std::is_constant_evaluated()` branches may execute entirely different code at run time. It's a strong unit test, not a proof.
</details>
