---
title: What the compiler can and cannot do for you
summary: "The optimizer rewrites programs under the as-if rule and the assumption of no UB: what inlining, constant propagation, devirtualization, copy elision, dead store elimination and loop-invariant code motion each do; how aliasing, invisible functions, escaped addresses and volatile block them; and how to make Clang explain its decisions with -Rpass."
tags: performance, optimization, as-if, inlining, aliasing, devirtualization, Clang
updated: 2026-10-19
group: Compiler
---

!!! tldr
    - The standard only requires an implementation to emulate the observable behavior of the abstract machine (volatile accesses, data written to files, input and output on interactive devices); everything else may be rewritten. The absence of UB is the premise of the optimizer's reasoning.
    - Inlining is the gateway to other optimizations: only after a call is inlined can constants flow in and loops be vectorized. When the function body is in another translation unit, it cannot be inlined without LTO; the `inline` keyword is mainly about the ODR, and on Clang it only raises the inlining threshold from 225 to 325.
    - `final` and a known dynamic type can turn a virtual call into a direct call; the gain comes from the inlining and vectorization that follow, not from the indirect jump saved.
    - The optimizer's most common obstacle is aliasing: once memory is written through `char`, `unsigned char` or `std::byte`, the compiler must assume any object may have changed. An indexed loop writing a `std::vector<unsigned char>` was more than 30 times slower than a range-for on our test machine.
    - Use `-Rpass=…`, `-Rpass-missed=…` and `-Rpass-analysis=…` to make Clang report its inlining, hoisting and vectorization decisions and the reasons for failures, then check them against the assembly.

## A loop turned into a formula

```cpp godbolt title="asif.cpp" flags="-std=c++2c -O2" ok
int tri(int n) {
  int s = 0;
  for (int i = 0; i < n; ++i) s += i;
  return s;
}
int ten() {
  int a[] = {1, 2, 3, 4};
  int s = 0;
  for (int v : a) s += v;
  return s;
}
```

Output of `clang++ -std=c++2c -O2` (Homebrew Clang 23.1.3, arm64):

```asm title="AArch64"
__Z3trii:                    ; no loop: (n-1) + (n-1)(n-2)/2
  sub   w8, w0, #1
  sub   w9, w0, #2
  umull x9, w8, w9
  add   x8, x8, x9, lsr #1
  cmp   w0, #1
  csel  w0, wzr, w8, lt      ; 0 when n < 1
  ret
__Z3tenv:
  mov   w0, #10
  ret
```

The loop in `tri` is replaced by a summation formula; the array and loop in `ten` vanish, leaving only the constant 10. The program says loop, the machine runs no loop, and that is allowed.

¶1 The basis is [[intro.abstract#1]]:

!!! std
    conforming implementations are required to emulate (only) the observable behavior of the abstract machine

The standard describes a program's semantics in terms of an [[g:abstract-machine]]. Implementations need not mirror its structure; they only need to produce the same [[g:observable-behavior]]. [[intro.abstract#8]] lists everything that counts as observable behavior: accesses through volatile glvalues, data handed to the host environment to be written to files, and input and output on interactive devices. How many times a loop ran, whether a variable lives in a register or in memory, whether a function was called — none of these are on the list. This is the [[g:as-if-rule]], named after the footnote there: an implementation may disregard the rules as long as the result is as if they had been obeyed.

The as-if rule governs defined executions. The formula for `tri` holds only if `s += i` and `++i` do not overflow; signed overflow is UB, and the compiler need not consider it. [[intro.abstract#6]] says that once an execution contains an undefined operation, the implementation is no longer constrained. So the optimizer always reasons on the premise that the program has no UB; [[topics/undefined-behavior]] collects examples of this reasoning deleting null checks and rewriting loops.

The same reasoning applies to heap allocation:

```cpp godbolt title="alloc.cpp" flags="-std=c++2c -O2" ok
#include <vector>
int vsum() {
  std::vector<int> v{1, 2, 3};
  return v[0] + v[1] + v[2];
}
```

Clang 23 with libc++ compiles `vsum` to `mov w0, #6`, calling neither `operator new` nor `operator delete`. [[expr.new#14]] allows implementations to omit calls to replaceable global allocation functions, and [[allocator.members#5]] says it is unspecified when and how often `std::allocator::allocate` calls `::operator new`.

## Optimization levels

The same function differs a lot across `-O` levels:

```cpp godbolt title="levels.cpp" flags="-std=c++2c -O2" ok
int sum(const int* a, int n) {
  int s = 0;
  for (int i = 0; i < n; ++i) s += a[i];
  return s;
}
```

<div class="compare" markdown="1">

```asm title="-O0 loop body"
LBB0_2:
  ldr  x8, [sp, #24]    ; load a from the stack
  ldrsw x9, [sp, #12]   ; load i
  ldr  w9, [x8, x9, lsl #2]
  ldr  w8, [sp, #16]    ; load s
  add  w8, w8, w9
  str  w8, [sp, #16]    ; store s back
  b    LBB0_3
LBB0_3:
  ldr  w8, [sp, #12]    ; load i
  add  w8, w8, #1
  str  w8, [sp, #12]    ; store i back
  b    LBB0_1
```

```asm title="-O2 main loop"
LBB0_7:                 ; 16 ints per iteration
  ldp   q4, q5, [x8, #-32]
  ldp   q6, q7, [x8], #64
  add.4s v0, v4, v0
  add.4s v1, v5, v1
  add.4s v2, v6, v2
  add.4s v3, v7, v3
  subs  x12, x12, #16
  b.ne  LBB0_7
```

</div>

`-O0` keeps every variable on the stack, loading it from memory on each use and storing it back after modifying it, so a debugger can inspect it at any time. `-O1` puts the variables in registers; the loop body is down to four instructions, one element at a time. `-O2` **vectorizes** the loop (one instruction processes several elements) and unrolls it four times, handling 16 `int`s per iteration, with loops before and after for the leftovers; the whole function is 62 lines.

The times below are for one call of `sum` on 4096 `int`s. `levels.cpp` was compiled separately at each level, while the measurement harness was always compiled with `-O2` and linked in. Measured on an Apple M2 Pro; the table gives the range over several runs (each run taking a median):

| Level | Assembly lines | Loop shape | Per call |
|---|---|---|---|
| `-O0` | 25 | All variables on the stack | 3.8–9.0 µs |
| `-O1` | 13 | Scalar, 1 at a time | 1.26–1.9 µs |
| `-O2` | 62 | Vectorized, unrolled ×4, 16 at a time | 148–151 ns |
| `-O3` | 62 | Identical to `-O2` | 148–151 ns |
| `-Os` | 12 | Scalar, 1 at a time | 1.28–1.8 µs |
| `-Oz` | 9 | Scalar | not measured |

`-O1` and `-Os` do not vectorize, and Clang explains why (the next section introduces these reports):

```text
-O1: remark: loop not vectorized: only vectorizing loops that explicitly request it [-Rpass-missed=loop-vectorize]
-Os: remark: the cost-model indicates that vectorization is not beneficial [-Rpass-missed=loop-vectorize]
```

For this function `-O3` is byte-for-byte identical to `-O2`. Comparing the two pipelines of LLVM 23 with `opt -passes='default<O3>' -print-pipeline-passes`, `-O3` adds only a few passes such as `callsite-splitting`, `argpromotion` and `chr`, unrolls loops more aggressively, and enables non-trivial loop unswitching only at `-O3`; the inlining threshold also rises from 225 to 250 (see below). Whether `-O3` is faster has to be measured, not assumed.

The ranges are this wide because the machine was heavily loaded during measurement. The vectorized version took 148–151 ns every time, while the scalar versions varied by up to 2x between runs; even taking the best run, `-O2` is more than 8 times faster than `-O1`.

These numbers only describe this machine, this compiler and this function. With another compiler the division of labor between levels differs; on another machine the speedup from vectorization differs.

<details class="fine" markdown="1"><summary>Measurement harness</summary>

All timings on this page use the header below; measurement methods are discussed fully in [[perf/measuring]].

```cpp title="bench.h" ok
#include <algorithm>
#include <chrono>
#include <cstdio>
#include <vector>

// make the compiler believe v is read, so the code computing v cannot be deleted
template<class T> void escape(T const& v) {
  asm volatile("" : : "r,m"(v) : "memory");
}
// make the compiler believe any memory may have been read or written
inline void clobber() { asm volatile("" : : : "memory"); }

// run f for reps rounds of iters calls each; return the median nanoseconds per call
template<class F> double bench(F f, int iters, int reps = 21) {
  using clk = std::chrono::steady_clock;
  for (int i = 0; i < iters; ++i) f();                 // warm-up
  std::vector<double> ns;
  for (int r = 0; r < reps; ++r) {
    auto t0 = clk::now();
    for (int i = 0; i < iters; ++i) f();
    auto t1 = clk::now();
    ns.push_back(std::chrono::duration<double, std::nano>(t1 - t0).count() / iters);
  }
  std::nth_element(ns.begin(), ns.begin() + reps / 2, ns.end());
  return ns[reps / 2];
}
```

The as-if rule applies to measurement code too: if nobody uses the result of `sum`, the compiler may delete the call entirely. `escape` is an empty inline asm statement that declares it reads `v` and may read or write any memory (`"memory"`); the compiler does not analyze the asm's contents, so it has to keep the computation of `v`. `clobber` makes the compiler believe memory has changed, so it cannot carry the previous round's result over to the next. Inline assembly is a conditionally-supported construct with implementation-defined meaning ([[dcl.asm]]); this idiom only works with GCC and Clang.

The function under test is placed in a separate translation unit so it cannot be inlined into the timing loop and then hoisted out of it. Other compile jobs were running on the machine during measurement, and medians of the same program differed by up to 2x across runs, so the text only gives ranges and only draws conclusions from differences of several times; the assembly and optimization reports are unaffected by load and are the main evidence.
</details>

## Making Clang explain its decisions

Clang's **optimization remarks** say what each optimization pass did and did not do. The three kinds of flags each take a pass name (a regular expression):

| Flag | Reports | Pass names used on this page |
|---|---|---|
| `-Rpass=…` | What succeeded | `inline`, `licm`, `loop-vectorize` |
| `-Rpass-missed=…` | What was attempted but failed | Same |
| `-Rpass-analysis=…` | The specific reason for the failure | `loop-vectorize` |

Remarks go to standard error like warnings, with source locations. `-fsave-optimization-record` saves all remarks to a YAML file, which suits large projects. Function names in remarks are mangled; `_Z3mixj` is `mix(unsigned int)`, which `llvm-cxxfilt` can demangle; see [[perf/reading-assembly]].

A remark saying something was done does not mean the benefit is visible in the assembly, and a remark saying it was not done may reflect the right choice. So remarks are a tool for finding leads; conclusions still come back to the assembly and measurements.

## Inlining

### No body, no inlining

<div class="compare" markdown="1">

```cpp title="xtu.cpp"
int add3(int x);   // defined in add3.cpp
void bump(int* a, int n) {
  for (int i = 0; i < n; ++i)
    a[i] = add3(a[i]);
}
```

```cpp title="stu.cpp"
int add3(int x) { return x + 3; }
void bump(int* a, int n) {
  for (int i = 0; i < n; ++i)
    a[i] = add3(a[i]);
}
```

</div>

On the left, `add3` is in another translation unit; when compiling `xtu.cpp` the compiler sees only the declaration, so the loop calls it once per element:

```asm title="xtu.cpp, -O2"
LBB0_2:
  ldr   w0, [x19]
  bl    __Z4add3i          ; one call per element
  str   w0, [x19], #4
  subs  x20, x20, #1
  b.ne  LBB0_2
```

On the right, `add3` is **inlined** (the function body is copied to the call site, replacing the call), leaving only an addition in the loop, which is then vectorized: the main loop adds 3 to 16 `int`s at a time (`movi.4s v0, #3` plus four `add.4s`).

Calling `bump` once on 4096 elements on our test machine: across translation units 3.8–8.6 µs, in the same translation unit 0.20–0.30 µs, across translation units but compiled and linked with `-flto` 0.20–0.28 µs, a difference of more than 20x. What is saved is not just the call instruction; more importantly, inlining makes vectorization possible.

Inlining across translation units requires **link-time optimization** (LTO): the compiler stores the intermediate representation in the object files, and at link time the whole program is optimized again as one unit. Cost and usage are in [[perf/lto-pgo]]. Functions in headers can be inlined because every translation unit has their definition.

### Cost and threshold

When the body is visible, whether to inline is decided heuristically: the compiler estimates the **cost** of the inlined code and compares it with a **threshold**. `mix` below consists of 28 groups of statements of the same form:

```cpp title="mix.cpp"
unsigned mix(unsigned x) {
  x ^= x >> 3; x *= 3;
  x ^= x >> 4; x *= 5;
  // …28 groups of statements of the same form
  return x;
}
unsigned caller(unsigned a) { return mix(a) + mix(a + 1); }
```

Compiled with `clang++ -std=c++2c -O2 -S -Rpass=inline -Rpass-missed=inline mix.cpp`, Clang 23 reports (the two call sites report the same; only one is shown):

```text
mix.cpp:32:38: remark: '_Z3mixj' not inlined into '_Z6callerj' because too costly to inline (cost=385, threshold=337) [-Rpass-missed=inline]
```

Adding `inline` in front of `mix`, the same command gives:

```text
mix.cpp:32:38: remark: '_Z3mixj' inlined into '_Z6callerj' with (cost=385, threshold=487) at callsite caller:0:38; [-Rpass=inline]
```

The threshold varies with level and keyword. Compiling `mix` at each level, the thresholds in the remarks are:

| | `-O1`, `-O2` | `-O3` | `-Os` | `-Oz` |
|---|---|---|---|---|
| Without `inline` | 337 | 375 | 75 | 5 |
| With `inline` | 487 | 487 | 487 | not measured |

LLVM's base threshold is 225 (250 at `-O3`, 50 at `-Os`), and 325 for functions with an inline hint; `mix` has a single basic block and gets a 50% bonus, hence 337, 375, 75 and 487 in the remarks. Two more observations:

- A `static` function called only once is almost always inlined. Making `mix` `static` and calling it once, the remark becomes `cost=-14615`: the size saved by deleting the function itself counts as a large bonus.
- Clang only gives the hint to functions explicitly declared `inline`. A member function defined inside a class definition is implicitly an inline function, but in our tests its threshold was still 337, not raised.

### The `inline` keyword does not mean inlining

¶3 [[dcl.inline#3]] says the `inline` specifier indicates to the implementation that inline substitution at the call site is to be preferred, but the implementation need not perform it. The keyword's truly binding effect is in the note in ¶2: an [[g:inline-function]] may be defined in multiple translation units as long as the definitions are the same ([[basic.def.odr]]). So its purpose is to let function definitions go in headers, not to order the compiler to inline.

The relationship between the two is indirect: only when the function is defined in a header can every translation unit see its body, making inlining possible. Whether it is actually inlined is decided by the cost model; on Clang, `inline` merely raises the threshold.

When you need to force it, GCC and Clang provide two extension attributes:

```cpp godbolt title="attrs.cpp" flags="-std=c++2c -O2" ok
[[gnu::always_inline]] inline int sq(int x) { return x * x; }
[[gnu::noinline]] int cube(int x) { return x * x * x; }
int f(int x) { return sq(x) + cube(x); }
```

```text
attrs.cpp:3:23: remark: '_Z2sqi' inlined into '_Z1fi' with (cost=always): always inline attribute at callsite f:0:23; [-Rpass=inline]
attrs.cpp:3:31: remark: '_Z4cubei' not inlined into '_Z1fi' because it should never be inlined (cost=never): noinline function attribute [-Rpass-missed=inline]
```

`always_inline` inlines even at `-O0` (the first remark appears at `-O0` too), and `noinline` never inlines at any level. `noinline` is commonly used to move cold paths and error handling out of hot functions, or to isolate the function under test in a benchmark; overusing `always_inline` bloats code and can strain the instruction cache, so let measurement decide.

## Constant propagation and folding

```cpp godbolt title="cprop.cpp" flags="-std=c++2c -O2" ok
int divide(int x, int d) { return x / d; }
int quarter(int x) { return divide(x, 4); }
int by_runtime(int x, int d) { return divide(x, d); }
```

```asm title="AArch64"
__Z7quarteri:              ; division by 4 becomes a shift
  add   w8, w0, #3
  cmp   w0, #0
  csel  w8, w8, w0, mi     ; add 3 to negatives first, to truncate toward zero
  asr   w0, w8, #2
  ret
__Z10by_runtimeii:
  sdiv  w0, w0, w1         ; divisor unknown: must use the divide instruction
  ret
```

**Constant propagation** substitutes known constants where they are used, and **constant folding** computes the values of constant expressions at compile time. Once `quarter` inlines `divide`, the divisor becomes the constant 4 and the division is replaced by a shift; signed division truncates toward zero ([[expr.mul]]), so negative numbers get 3 added before the right shift. The divisor in `by_runtime` is a run-time value, so only `sdiv` will do.

`ten` and `vsum` at the start are also results of folding. These are liberties the optimizer takes, not guarantees: the same code runs its loop as usual at `-O0`. When you need the result guaranteed at compile time, use a `constexpr` variable or a `consteval` function; see [[perf/compile-time-work]].

## Devirtualization

A virtual call first loads the object's vptr, then loads the function address from the vtable, and finally makes an indirect call; what the assembly looks like is in [[perf/reading-assembly]]. If the compiler can determine the object's [[g:dynamic-type]], it can replace the virtual call with a direct call and then inline it. This is called **devirtualization**. Three common cases:

- The object is right there: `Square q(x); const Shape& s = q; s.area();` compiles to a single `fmul` on our test machine.
- The static type is a `final` class, or the called virtual function is declared `final`: no derived class can override it.
- The whole program is visible: with LTO plus `-fwhole-program-vtables`, Clang can confirm that a virtual function has only one overrider; see [[perf/lto-pgo]].

Devirtualization by itself saves only two loads and an indirect jump. Comparing `final` and non-`final` classes in a loop:

```cpp title="dv.h" ok
struct Shape {
  virtual ~Shape() = default;
  virtual int area() const = 0;
};
struct Sq : Shape {            // not final
  int side = 3;
  int area() const override { return side * side; }
};
struct SqF final : Shape {     // final
  int side = 3;
  int area() const override { return side * side; }
};
```

```cpp title="dv.cpp" ok
#include "dv.h"
long total(const Sq* p, int n) {
  long s = 0;
  for (int i = 0; i < n; ++i) s += p[i].area();
  return s;
}
long total(const SqF* p, int n) {
  long s = 0;
  for (int i = 0; i < n; ++i) s += p[i].area();
  return s;
}
```

The `Sq` version's loop loads the vptr, loads the slot and does a `blr` every iteration; the `SqF` version inlines `area` and is then vectorized, reading 16 objects at once with `ld4.4s`. With 4096 objects each, measured one after another in the same process, the `Sq` version took 3.8–9.0 µs and the `SqF` version 0.87–2.2 µs; in every run `SqF` was more than 3 times faster.

Switch `int` to `double`, and the two versions can no longer be told apart: over several runs on our test machine, sometimes `Sq` was faster and sometimes `SqF`, with differences within noise (both between 3.8 and 8.5 µs). The `SqF` version's `area` is still inlined, and the loads and multiplications are vectorized, but the additions remain one-by-one scalar `fadd d0, d0, …`. Floating-point addition is not associative, so the compiler cannot split `s += …` into several parallel accumulators ([[expr.pre]]); both versions are bound by the dependency chain of sequential additions, which masks the cost of the indirect call. So what devirtualization is worth depends on what optimizations it enables afterwards.

## Copy elision

```cpp godbolt title="nrvo.cpp" flags="-std=c++2c -O2" ok
struct Big {
  Big();
  Big(Big&&);
  ~Big();
  char buf[256];
};
void fill(Big&);

Big one() {
  Big a;
  fill(a);
  return a;          // a is built directly in the return value's place
}
Big two(bool c) {
  Big a, b;
  fill(a); fill(b);
  if (c) return a;
  return b;
}
```

<div class="compare" markdown="1">

```asm title="one, -O2"
  mov  x19, x8   ; x8: address of the return value
  mov  x0, x8
  bl   __ZN3BigC1Ev   ; construct there
  mov  x0, x19
  bl   __Z4fillR3Big
  ret               ; no move
```

```asm title="two, -O2 (excerpt)"
  add  x0, sp, #264
  bl   __ZN3BigC1Ev   ; a on the stack
  add  x0, sp, #8
  bl   __ZN3BigC1Ev   ; b on the stack
  ...
  csel x1, x8, x21, ne
  mov  x0, x19
  bl   __ZN3BigC1EOS_ ; move construction
  add  x0, sp, #8
  bl   __ZN3BigD1Ev
  add  x0, sp, #264
  bl   __ZN3BigD1Ev
```

</div>

Returning a prvalue (`return Big();`) involves no copy at all; since C++17 this is a language rule, not an optimization. When returning a named local variable, [[class.copy.elision#1]] ¶1.1 allows that variable to be constructed directly in the place of the return value; this is called NRVO (named return value optimization). It is permitted, not required: `one` has only one candidate and Clang does it; `two` has two candidates, and which one is returned is known only at run time, so Clang 23 puts both in its own stack frame, calls the move constructor once on return, and then destroys both objects.

Restructuring to have a single returned variable (decide first which object to write into, and `return` it at the end), or having each branch return a prvalue, avoids this move. Which forms incur an extra move or copy is covered in [[topics/special-members-and-elision]] and [[perf/copies-and-moves]].

## Dead store elimination

```cpp godbolt title="dse.cpp" flags="-std=c++2c -O2" ok
#include <cstring>
void opaque();
void twice(int* p) {
  *p = 1;            // overwritten by the next store: deleted
  *p = 2;
}
void with_call(int* p) {
  *p = 1;            // opaque() may read *p: kept
  opaque();
  *p = 2;
}
void read_password(char*);
void check(const char*);
void login() {
  char pw[64];
  read_password(pw);
  check(pw);
  std::memset(pw, 0, sizeof pw);   // nobody reads pw afterwards: deleted
}
```

A store that is overwritten before it is read, or whose object is never read again, is a **dead store**, and deleting it does not change observable behavior. At `-O2` on our test machine, `twice` is left with a single `str` storing 2; `with_call` keeps both stores, because the compiler cannot see the body of `opaque`, which might read `*p`.

The result for `login` is the most surprising: the `memset` is deleted entirely, and the password on the stack stays in memory as-is after the function returns. The lifetime of `pw` ends right after the `memset`, so zeroing it has no effect on observable behavior. To keep the zeroing, you have to make the compiler believe someone will read it:

```cpp
std::memset(pw, 0, sizeof pw);
asm volatile("" : : "r"(pw) : "memory");   // pretend to read the memory pw points to
```

With this line added, the output contains `movi.2d v0, #0` and two `stp q0, q0` zeroing 64 bytes. Other options are the platform function `memset_s` (C11 Annex K, optional), `explicit_bzero` (BSD, glibc), and C23's `memset_explicit`; what they have in common is a promise not to be removed as dead stores.

## Loop-invariant code motion

```cpp godbolt title="licm.cpp" flags="-std=c++2c -O2" ok
#include <cstddef>
#include <cstring>
std::size_t count_a(const char* s) {
  std::size_t c = 0;
  for (std::size_t i = 0; i < std::strlen(s); ++i)
    if (s[i] == 'a') ++c;
  return c;
}
void upper(char* s) {
  for (std::size_t i = 0; i < std::strlen(s); ++i)
    if (s[i] >= 'a' && s[i] <= 'z') s[i] -= 32;
}
```

**Loop-invariant code motion** (LICM) moves computations whose result is the same in every iteration to before the loop. The loop in `count_a` only reads `s`, so `strlen(s)` is the same every time, and Clang hoists it out of the loop:

```text
licm.cpp:5:31: remark: hoisting call [-Rpass=licm]
```

There is no such remark for `upper`, and `bl _strlen` stays in the loop in the assembly. The loop writes `s[i]`, and a write could change the string's length (for example by writing a `'\0'`); the compiler will not try to prove that `s[i] - 32` is never 0, so it recomputes the length every iteration and the whole function becomes O(n²).

Hoisting by hand fixes it:

```cpp
void upper_fixed(char* s) {
  const std::size_t n = std::strlen(s);
  for (std::size_t i = 0; i < n; ++i)
    if (s[i] >= 'a' && s[i] <= 'z') s[i] -= 32;
}
```

The two are not exactly equivalent: if the loop really wrote a `'\0'`, `upper` would stop early and `upper_fixed` would not. That is exactly why the compiler cannot make this rewrite for you. For 1024 characters on our test machine, `upper` takes 23–80 µs per call and `upper_fixed` 0.34–0.51 µs, two orders of magnitude apart, and the gap grows with the string's length.

## What stops the optimizer

All the optimizations above first have to answer the same question: could this memory write change that value? When the compiler cannot answer, it has to be conservative.

### Aliasing: `char` can overwrite anything

```cpp godbolt title="alias.cpp" flags="-std=c++2c -O2" ok
#include <cstddef>
#include <vector>
void idx(std::vector<unsigned char>& v, unsigned char k) {
  for (std::size_t i = 0; i < v.size(); ++i) v[i] += k;
}
void rng(std::vector<unsigned char>& v, unsigned char k) {
  for (auto& x : v) x += k;
}
```

```asm title="idx, -O2"
LBB0_2:
  ldrb  w10, [x8, x9]
  add   w10, w10, w1
  strb  w10, [x8, x9]      ; write one byte
  add   x9, x9, #1
  ldp   x8, x10, [x0]      ; reload v's begin and end
  sub   x10, x10, x8
  cmp   x9, x10
  b.lo  LBB0_2
```

For every byte it writes, `idx` reloads the `begin` and `end` pointers from the `v` object (libc++'s `vector` stores three pointers), and it is not vectorized. `rng` is vectorized, processing 64 bytes at a time:

```text
alias.cpp:4:3: remark: loop not vectorized [-Rpass-missed=loop-vectorize]
alias.cpp:7:3: remark: vectorized loop (vectorization width: 16, interleaved count: 4) [-Rpass=loop-vectorize]
```

The reason is in [[basic.lval#11]]. An object may only be accessed through a glvalue of a type similar to its own, with the exception of `char`, `unsigned char` and `std::byte`, which may access any object (see [[topics/type-punning]]). So in **type-based alias analysis**, an `unsigned char` write may overwrite any object, including `v`'s own `end` pointer. `rng` copied `begin()` and `end()` into local iterators before the loop starts; the addresses of local variables never leaked, so byte writes cannot change them.

Replace `unsigned char` with `int`, and since an `int` write cannot overwrite a pointer object, `idx` vectorizes too. With 4096 elements each, measured on our test machine:

| Function | Default | `-fno-strict-aliasing` |
|---|---|---|
| `idx`, `vector<unsigned char>` | 1.7–5.9 µs | 2.0–5.8 µs |
| `rng`, `vector<unsigned char>` | 50–120 ns | 50–51 ns |
| `idx`, `vector<int>` | 0.20–0.37 µs | 2.1–6.9 µs |

`-Rpass-missed=licm` shows the reason directly; the remarks point at the line in libc++ where `size()` reads the two pointers:

```text
.../include/c++/v1/__vector/layout.h:425:33: remark: failed to move load with loop-invariant address because the loop may invalidate its value [-Rpass-missed=licm]
.../include/c++/v1/__vector/layout.h:425:42: remark: failed to move load with loop-invariant address because the loop may invalidate its value [-Rpass-missed=licm]
```

This has nothing to do with the target architecture. Hand-write a `struct Bytes { unsigned char* data; std::size_t size; };`, write the loop condition as `i < b.size`, compile with `--target=x86_64-linux-gnu`, and every iteration of the loop likewise has two reloads, `movq (%rdi), %rcx` and `cmpq 8(%rdi), %rax`.

The fix is always to put values that would be reread into local variables: use a range-for or iterators, or first write `auto* p = v.data(); auto n = v.size();`.

Two more observations on our test machine that do not correspond exactly to the standard's wording:

- The same loop over `std::vector<signed char>` is not vectorized either. `signed char` is not on the standard's exemption list, but Clang treats it like `char`, as a type that may access any object; this is a more conservative implementation choice. `int8_t` is `signed char` here.
- The loop over `std::vector<char8_t>` is vectorized. `char8_t` is a distinct type not on the exemption list, so Clang need not be conservative about it.

### Pointers of the same type: `__restrict`

```cpp godbolt title="restrict.cpp" flags="-std=c++2c -O2" ok
void scale(int* out, const int* in, const int* k, int n) {
  for (int i = 0; i < n; ++i) out[i] = in[i] * *k;
}
void scale_r(int* __restrict out, const int* in, const int* k, int n) {
  for (int i = 0; i < n; ++i) out[i] = in[i] * *k;
}
```

`out` may point to `*k`, so after writing `out[i]`, `*k` may have changed. Clang's approach is to generate two versions: before the loop, a few `cmp`/`ccmp` instructions check whether the range of `out` overlaps `in` and `k`; if not, the vectorized version runs and `*k` is read only once; if so, the scalar version runs and every iteration executes `ldr w12, [x2]` to reload `*k`. The `__restrict` in `scale_r` promises that the memory `out` points to is accessed only through `out`, and both the check and the scalar version disappear.

`__restrict` comes from C's `restrict`; it is not in the C++ standard, but GCC, Clang and MSVC all support it as an extension. If the promise does not hold, the compiler treats it as undefined behavior by its own definition. The check is done once per call, and its cost is negligible for long loops; the more effective tool is often the one from the previous section: read `*k` into a local variable first. The relationship between run-time alias checks and vectorization is covered in [[perf/vectorization]].

### Invisible functions and escaped addresses

```cpp godbolt title="escape.cpp" flags="-std=c++2c -O2" ok
void tick();                      // definition not visible
void watch(const int*);           // definition not visible

int count_private(int n) {
  int c = 0;
  for (int i = 0; i < n; ++i) { ++c; tick(); }
  return c;
}
int count_escaped(int n) {
  int c = 0;
  watch(&c);                      // c's address has been handed out
  for (int i = 0; i < n; ++i) { ++c; tick(); }
  return c;
}
```

<div class="compare" markdown="1">

```asm title="count_private"
LBB0_2:
  bl    __Z4tickv
  subs  w20, w20, #1
  b.ne  LBB0_2
  mov   x0, x19   ; the result is just n
```

```asm title="count_escaped"
LBB1_1:
  ldr   w8, [sp, #12]   ; load c
  add   w8, w8, #1
  str   w8, [sp, #12]   ; store c back
  bl    __Z4tickv
  subs  w19, w19, #1
  b.ne  LBB1_1
```

</div>

When the compiler cannot see a function's body, it has to assume the function does anything it is entitled to do. `c` in `count_private` never leaves the function, `tick` cannot touch it, and so `c` is computed as `n`. `count_escaped` hands the address of `c` to `watch`, which might store the pointer so that `tick` can then read and write `c` through it; the parameter being `const int*` does not rule this out, because `c` itself is not a const object, and modifying it after a `const_cast` is valid. So before each call to `tick`, `c` must be written back to memory, and read again afterwards.

This state is called address **escape**. Common sources: passing the address of or a reference to a local variable to an invisible function, storing it in a global variable, or capturing it by reference in a lambda that is handed to a `std::function`. Limit the scope of escapes, or make the called functions visible (same translation unit, header, LTO), and the optimizer gets room to reason.

### volatile

```cpp godbolt title="volatile.cpp" flags="-std=c++2c -O2" ok
int with_volatile(int n) {
  volatile int s = 0;
  for (int i = 0; i < n; ++i) s = s + i;   // read and write memory every time
  return s;
}
```

Without `volatile`, this is `tri` from the start of the page and is folded into a formula; with it, every iteration of the loop has an `ldr` and a `str`, none of which can be skipped. [[intro.abstract#8]] ¶8.1 says accesses through volatile glvalues are evaluated strictly according to the rules of the abstract machine; they are observable behavior in themselves. The note in [[dcl.type.cv#6]] explains the intent: the object's value may change in ways undetectable by the implementation, for example a memory-mapped hardware register.

volatile provides no synchronization between threads; data shared between threads should use atomic types, see [[topics/memory-model]]. In benchmarks, writing the result to a volatile variable is another way to keep a computation from being deleted, at the cost of one extra memory write each time.

### Exceptions: mostly not an obstacle

A call that may throw does not slow down the normal path. For a function that holds an RAII object and calls an invisible function in a loop, on our test machine the loop's instructions are identical with and without `-fno-exceptions`, differing only in register allocation; the extra landing pad is placed after the `ret`, where normal execution never goes. The same is true of `one` in `nrvo.cpp` above. Detailed assembly is in [[perf/reading-assembly]], and the implementation mechanism in [[toolchain/exception-implementation]].

The constraint exceptions impose is the same as that of an invisible function: the call might not return, so externally visible writes before the call cannot be postponed until after it. That constraint already exists when the function body is invisible; exceptions add little to it.

### The cost of `-fno-strict-aliasing` and `-fwrapv`

Both flags turn a kind of UB into defined behavior and are conforming extensions ([[intro.compliance.general#11]]); the cost is one less premise for the optimizer:

- `-fno-strict-aliasing` turns off type-based alias analysis, so a write of any type may overwrite any object. In the table above, `idx` on `vector<int>` degrades to match `unsigned char` as a result, from about 0.2 µs to 2–7 µs. Old code relying on pointer type punning uses it as a safety net; new code should follow [[topics/type-punning]].
- `-fwrapv` makes signed integers wrap in two's complement. The compiler can no longer assume a subscript like `r * stride + c` does not wrap; on our test machine it generated an extra wrap check before a two-dimensional summation loop, and vectorization still succeeded. For a 64×64 array, the measured difference was within noise (default 0.47–0.87 µs, `-fwrapv` 0.47–0.58 µs, with a best result of 0.47 µs for both). Its effect on comparisons like `x + 1 > x` is in [[topics/undefined-behavior]].

So the cost of `-fwrapv` is usually small, while `-fno-strict-aliasing` can be significant in pointer-heavy loops. Measure both on your own code before deciding.

## `-ffast-math`

Earlier, the additions in the `double` version of `total` could only be done in order because floating-point addition is not associative. `-ffast-math` turns on a group of options including `-fassociative-math`, allowing the compiler to reassociate. With it, Clang 23's main loop for the `SqF` version becomes four-way `fmla.2d` vector multiply-adds, each lane accumulating separately, with the four combined after the loop; rounding of the result may therefore differ from sequential addition. It also assumes there are no NaNs or infinities, which breaks code that checks for NaN, see [[topics/arithmetic]]; vectorization itself is in [[perf/vectorization]].

## Questions

!!! question "1"
    The benchmark below, at `-O2`, measures a time almost independent of the iteration count. What happened? How do you fix it?
    ```cpp
    int square(int x) { return x * x; }
    // in the same file
    auto t0 = clk::now();
    for (int i = 0; i < 1'000'000; ++i) { int r = square(i); }
    auto t1 = clk::now();
    ```

<details markdown="1">
<summary>Answer</summary>

`square` is in the same translation unit; once inlined, `r` is never used and computing it has no observable behavior. Under the as-if rule ([[intro.abstract#1]]) the whole loop can be deleted, and what is measured is just the gap between two clock reads. In the code Clang 23 generates, there are no instructions between the two `bl …steady_clock3nowEv`. Note that `i * i` overflows for larger `i`, which is UB, and the compiler need not keep code for it either.

The fix is to make it impossible for the compiler to prove that nobody uses the result: pass `r` to this page's `escape`, or write it to a volatile variable; and put the function under test in another translation unit, or mark it `[[gnu::noinline]]`, so it cannot be optimized away along with the loop. Measurement methods are in [[perf/measuring]].
</details>

!!! question "2"
    For `for (std::size_t i = 0; i < v.size(); ++i) v[i] = …;` on `std::vector<std::byte>` and on `std::vector<char8_t>`, which loop has to reload `v.size()` every iteration?

<details markdown="1">
<summary>Answer</summary>

The `std::byte` one. [[basic.lval#11]] ¶11.3 allows any object to be accessed through a glvalue of type `char`, `unsigned char` or `std::byte`, so a `std::byte` write might overwrite the `vector`'s internal pointers, and the compiler cannot hoist `size()` out of the loop. `char8_t` is a distinct type not on the list, and its writes cannot change pointer objects. Clang 23's remarks: the `char8_t` loop gets `vectorized loop (vectorization width: 16, interleaved count: 4)`, the `std::byte` loop `loop not vectorized`.
</details>

!!! question "3"
    If `[[gnu::always_inline]]` is put on a function that is defined only in a `.cpp` file, with only a declaration in the header, will calls to it from other translation units be inlined?

<details markdown="1">
<summary>Answer</summary>

No. Inlining needs the function body; when compiling other translation units the compiler sees only the declaration, so the attribute has nothing to act on, and only calls within the translation unit containing the definition are inlined. To make it inlinable everywhere, put the definition in the header together with `inline` (the note in [[dcl.inline#2]] allows inline functions to be defined in multiple translation units), or use LTO.
</details>

## Summary

| Optimization | What it does | Common obstacles |
|---|---|---|
| Inlining | Copies the function body to the call site, paving the way for other optimizations | Body in another translation unit; cost above the threshold |
| Constant propagation and folding | Computes at compile time whatever can be computed | Values come from run time or memory |
| Devirtualization | Turns virtual calls into direct calls, then inlines | Dynamic type unknown; neither class nor function is `final` |
| NRVO | Builds the named return variable directly in the return value's place | Multiple candidate variables; `return std::move(x)` |
| Dead store elimination | Deletes writes nobody reads | Invisible calls in between; zeroing you need kept gets deleted |
| Loop-invariant code motion | Moves invariant computations out of loops | Writes in the loop that may alias |
| Vectorization | One instruction processes several elements | Aliasing; floating-point associativity; `-O1`, `-Os` |

| Obstacle | Compiler's assumption | Remedy |
|---|---|---|
| Writes through `char`, `unsigned char`, `std::byte` | May overwrite any object | Put values that are read repeatedly into local variables |
| Pointers of the same type | May overlap | Local variables; `__restrict` (extension) |
| Invisible functions | May read or write any reachable memory | Make the body visible; LTO |
| Escaped addresses | May change after every call | Don't hand out the addresses of local variables |
| volatile | Every access is observable behavior | Use only for hardware, signal handling and the like |
