---
title: Auto-vectorization
summary: "When the compiler rewrites a loop into SIMD instructions: the trip count must be computable, iterations must be independent, and arrays must be provably non-overlapping; why floating-point sums need the programmer's permission to reorder; how to read Clang's vectorization remarks; and what restrict, pragmas, the unseq execution policy and std::simd each tell the compiler."
tags: performance, SIMD, vectorization, floating point, aliasing, restrict, Clang
updated: 2026-10-19
group: Compiler
---

!!! tldr
    - Auto-vectorization rewrites a loop so that each instruction processes 4 or 8 elements. On our test machine this made `saxpy` within L1 cache about 3.6 times faster; when the data is large enough to come from memory, only about 2 times.
    - The compiler acts only under three conditions: the trip count is computable on entry to the loop, iterations do not depend on each other, and the arrays read and written can be proven not to overlap. When the last cannot be proven, it inserts a run-time overlap check before the loop.
    - Floating-point addition is not associative, so per the standard `s += x[i]` must accumulate one by one, and the compiler cannot split it into several partial sums on its own. Splitting requires the programmer's permission: `std::reduce`, the `unseq` execution policy, `#pragma clang loop vectorize(enable)`, or `-ffast-math`. Integer sums need no permission.
    - Use `-Rpass=loop-vectorize`, `-Rpass-missed=loop-vectorize` and `-Rpass-analysis=loop-vectorize` to have Clang report whether each loop was vectorized and why not. Even when the remark says vectorized, look at the assembly; the floating-point sum on our test machine is an example.
    - `__restrict` is not standard C++. On macOS, after including system headers it is defined as an empty macro and does nothing; if you want it, write `__restrict__`.

## The same loop, 3.6 times faster

```cpp run title="saxpy.cpp" flags="-std=c++2c -O2" ok
#include <cstddef>
void saxpy(float a, const float* x, float* y, std::size_t n) {
  for (std::size_t i = 0; i < n; ++i) y[i] = a * x[i] + y[i];
}
```

**SIMD** (single instruction, multiple data) instructions apply the same operation to several elements in a vector register at once; each element's position is called a **lane**. arm64's NEON registers are 128 bits, holding 4 `float`s; x86-64's SSE is also 128 bits, while AVX2 is 256 bits, holding 8. The compiler rewriting an ordinary scalar loop into a loop using such instructions is called **auto-vectorization**.

Compiled on our test machine (Apple M2 Pro, Homebrew Clang 23, arm64) with `clang++ -std=c++2c -O2 -S`, compared with vectorization turned off (`-fno-vectorize -fno-slp-vectorize`), the two loop bodies are:

<div class="compare" markdown="1">

```text
; vectorization off: 2 elements per iteration
ldur   s1, [x10, #-4]
ldp    s2, s3, [x11, #-4]
fmadd  s1, s0, s1, s2
stur   s1, [x11, #-4]
ldr    s1, [x10], #8
fmadd  s1, s0, s1, s3
str    s1, [x11], #8
add    x8, x8, #2
cmp    x9, x8
b.ne   LBB0_4
```

```text
; -O2 default: 16 elements per iteration
ldp    q1, q2, [x10, #-32]
ldp    q3, q4, [x10], #64
ldp    q5, q6, [x11, #-32]
ldp    q7, q16, [x11]
fmla.4s v5, v1, v0[0]
fmla.4s v6, v2, v0[0]
fmla.4s v7, v3, v0[0]
fmla.4s v16, v4, v0[0]
stp    q5, q6, [x11, #-32]
stp    q7, q16, [x11], #64
subs   x12, x12, #16
b.ne   LBB0_10
```

</div>

The `s` registers on the left hold a single `float`, and `fmadd` is one multiply-add. The `q` registers on the right are 128 bits, and `fmla.4s` does 4 multiply-adds at once. The number of elements one instruction processes is the **vectorization width** (VF), 4 here. The loop body on the right also places 4 groups of vector operations together, which is called **interleaving**, with an interleave count of 4, so each iteration processes 16 elements. The remaining tail of fewer than 16 elements is handled by a 4-wide loop and a scalar loop afterwards; how to read the assembly is in [[perf/reading-assembly]].

Both versions use fused multiply-add (FMA) instructions, rounding `a * x[i] + y[i]` only once. Clang's default `-ffp-contract=on` allows this fusion within a single expression, and the result may differ from rounding separately; floating-point semantics are in [[topics/arithmetic]].

### Measurement

Timing uses this section's shared [[perf/measuring#harness|bench.hpp]]: each sample makes consecutive calls for about 1 ms, the median of 31 samples is taken, and `do_not_optimize` and `clobber_memory` are two lines of empty inline assembly that keep the optimizer from deleting the computation under test. Below, both versions are put in the same program and measured alternately, with vectorization turned off for the scalar version by a pragma (pragmas are covered later):

```cpp title="saxpy_bench.cpp" ok
#include "bench.hpp"
#include <cstddef>
#include <cstdlib>
#include <vector>

[[gnu::noinline]] void saxpy(float a, const float* x,
                             float* y, std::size_t n) {
  for (std::size_t i = 0; i < n; ++i) y[i] = a * x[i] + y[i];
}
[[gnu::noinline]] void saxpy_scalar(float a, const float* x,
                                    float* y, std::size_t n) {
#pragma clang loop vectorize(disable) interleave(disable)
  for (std::size_t i = 0; i < n; ++i) y[i] = a * x[i] + y[i];
}

int main(int argc, char** argv) {
  bench::prefer_performance_cores();
  std::size_t n = argc > 1 ? std::strtoul(argv[1], nullptr, 10) : 4096;
  std::vector<float> x(n, 1.0f), y(n, 0.0f);
  float a = 1.0f;
  bench::compare(                                   // A: scalar, B: vector
      [&] { bench::do_not_optimize(a);
            saxpy_scalar(a, x.data(), y.data(), n);
            bench::clobber_memory(); },
      [&] { bench::do_not_optimize(a);
            saxpy(a, x.data(), y.data(), n);
            bench::clobber_memory(); });
}
```

```bash
clang++ -std=c++2c -O2 saxpy_bench.cpp -o saxpy_bench
./saxpy_bench && ./saxpy_bench 16777216
```

| n | Both arrays together | Scalar | Vector | Ratio |
|---|---|---|---|---|
| 4096 | 32 KiB, in L1 | about 880 ns | about 242 ns | about 3.6x |
| 16777216 | 128 MiB, in memory | about 4.7–5.3 ms | about 2.6 ms | about 2x |

These are observations on our test machine; the ratio is stable across runs, while absolute times fluctuate when the machine is busy; another CPU or compiler will give different numbers. When the data fits in L1, the bottleneck is instruction throughput, and vectorization cuts the instruction count to about a quarter. When the data has to come from memory, the bottleneck becomes memory bandwidth, and the instructions saved by vectorization buy only part of the gain; see [[perf/memory-hierarchy]].

### The same loop on x86-64

Our test machine has no x86 CPU, so below we look only at code generation, without measurements. Cross-compiling with `--target=x86_64-linux-gnu -S` (there are no Linux headers on our test machine, so `#include <cstddef>` was replaced by a single line `namespace std { using size_t = decltype(sizeof 0); }`):

| Option | Main instructions in the loop body | Width × interleave |
|---|---|---|
| Default (the x86-64 baseline has only SSE2) | `movups`, `mulps`, `addps` | 4 × 2 |
| `-mavx2` | `vmulps`, `vaddps`, `ymm` registers | 8 × 4 |
| `-march=x86-64-v3` | `vfmadd213ps`, `ymm` registers | 8 × 4 |

`-mavx2` only enables AVX2, not the FMA instruction set, so multiply and add are still two instructions; `-march=x86-64-v3` includes both AVX2 and FMA. The result of vectorization depends on the target instruction set, and the compiled program runs only on CPUs supporting those instructions.

## Reading vectorization remarks

Clang's loop vectorizer can report its decision for each loop:

| Option | Reports |
|---|---|
| `-Rpass=loop-vectorize` | Loops vectorized successfully, with width and interleave count |
| `-Rpass-missed=loop-vectorize` | Loops not vectorized |
| `-Rpass-analysis=loop-vectorize` | The specific reason a loop was not vectorized |

For `saxpy.cpp`, the output on our test machine:

```text
saxpy.cpp:3:3: remark: vectorized loop (vectorization width: 4, interleaved count: 4) [-Rpass=loop-vectorize]
```

The remarks are not a complete list. The `my_strlen` loop in the next section is not vectorized, yet none of the three options print anything for it. More importantly, a remark saying a loop was vectorized does not mean the loop got faster: the floating-point sum loop on our test machine gets the same `vectorized loop` remark, yet runs at the same speed as the scalar version, for reasons explained in the floating-point section below. To confirm the effect, look at the assembly and then measure.

## What vectorization needs

### The trip count is known before the loop starts

```cpp run title="countable.cpp" flags="-std=c++2c -O2" ok
#include <cstddef>
std::size_t my_strlen(const char* p) {
  std::size_t n = 0;
  while (p[n] != '\0') ++n;      // the count depends on the data read
  return n;
}
std::size_t find_first(const int* x, std::size_t n, int v) {
  for (std::size_t i = 0; i < n; ++i)
    if (x[i] == v) return i;     // bounded, but may exit early
  return n;
}
```

A vectorized loop processes VF elements at a time, so the compiler has to compute the total count before entering the loop to arrange the main loop and the tail. The count of `my_strlen` depends on the data read; such a loop is called uncountable, and Clang on our test machine does not vectorize it, nor print a remark. Another problem is that reading 16 bytes at a time might read past the end of the string into an inaccessible page; hand-vectorized `strlen` implementations rely on aligned reads to avoid crossing pages, and compilers generally don't do this kind of reasoning.

`find_first` has the upper bound `n` but may return midway. LLVM has recently started supporting such early-exit loops; the remark on our test machine is `the cost-model indicates that vectorization is not beneficial`, meaning it could, but considers it not worthwhile.

### No dependences between iterations

```cpp run title="prefix.cpp" flags="-std=c++2c -O2" ok
#include <cstddef>
void prefix(float* a, std::size_t n) {
  for (std::size_t i = 1; i < n; ++i) a[i] += a[i - 1];
}
```

Iteration `i` reads the value written by iteration `i - 1`; this is called a **loop-carried dependence**. With 4 lanes computing at once, the last 3 lanes would all read stale values, and the result would be wrong. The remark on our test machine:

```text
prefix.cpp:3:44: remark: loop not vectorized: unsafe dependent memory operations in loop. Use #pragma clang loop distribute(enable) to allow loop distribution to attempt to isolate the offending operations into a separate loop
Backward loop carried data dependence. Memory location is the same as accessed at prefix.cpp:3:47 [-Rpass-analysis=loop-vectorize]
prefix.cpp:3:3: remark: loop not vectorized [-Rpass-missed=loop-vectorize]
```

The `s += x[i]` in a sum is also a loop-carried dependence, just on a variable rather than in memory. This form is called a **reduction**; the compiler recognizes it and replaces the single accumulator with several partial sums, but only if the order of additions may be regrouped, which is covered in its own section later.

Calling a function whose definition is not visible inside the loop body also blocks vectorization, with the remark `call instruction cannot be vectorized`. The compiler doesn't know what the function does, let alone how to turn it into a version that handles 4 arguments at a time. Functions that can be inlined don't have this problem; see [[perf/compiler-optimizations]].

### Arrays provably don't overlap

`saxpy`'s `x` and `y` are two pointers, and the caller is perfectly free to point them at adjacent positions in the same array. For example, with `saxpy(a, y, y + 1, n)`, `y[i]` is the `x[i+1]` the next iteration reads, and executing in order gives a different result from executing in groups of 4.

When compiling `saxpy` the compiler cannot see the caller, so it generates two versions and checks at the entry. This is the start of the `saxpy` assembly above:

```text
	cmp	x2, #4                ; n < 4: go straight to the scalar loop
	b.lo	LBB0_3
	lsl	x8, x2, #2            ; x8 = n * 4, the array's size in bytes
	add	x9, x0, x8            ; x9 = x + n
	add	x8, x1, x8            ; x8 = y + n
	cmp	x0, x8                ; x < y + n
	ccmp	x1, x9, #2, lo        ; and y < x + n ?
	b.hs	LBB0_7                ; ranges don't overlap: go to the vector loop
LBB0_3:                               ; overlap: scalar loop
```

This is called a **runtime alias check**: if the two ranges `[x, x+n)` and `[y, y+n)` don't intersect, the vector version runs; otherwise the scalar version. The check is done only once before the loop, and its cost is negligible. The cost shows up when the check fails, for example with an in-place update `saxpy(a, y, y, n)`:

| Call | Median on our test machine |
|---|---|
| `saxpy(1.0f, x, y, 4096)`, no overlap | about 241 ns |
| `saxpy(1.0f, y, y, 4096)`, in place | about 1265 ns |

An in-place update could actually be vectorized safely, since each iteration reads and writes only the same position. But the check only looks at whether the ranges intersect and doesn't distinguish this case, so it falls through to the scalar loop.

### Pointers of different types: strict aliasing

```cpp run title="tbaa.cpp" flags="-std=c++2c -O2" ok
#include <cstddef>
void to_float(float* y, const int* x, std::size_t n) {
  for (std::size_t i = 0; i < n; ++i) y[i] = float(x[i]);
}
```

The `-O2` assembly on our test machine has no overlap check at all; the loop converts 4 elements at a time with `scvtf.4s`. With `-fno-strict-aliasing`, the entry gains a `sub x8, x1, x0` and `cmn x8, #64` comparison, that is, a run-time check.

The reason is in [[basic.lval#11]]: accessing an object of one type through a glvalue of another type is undefined behavior, except for the corresponding signed/unsigned types, `char`, `unsigned char` and `std::byte`. `y[i]` is a `float` lvalue and `x[i]` an `int` lvalue. If they accessed the same memory, the program would already have UB, so the compiler may assume they don't overlap. This rule is called **strict aliasing**; its other consequences are in [[topics/type-punning]]. When the two pointers have the same type (both `float*`), this rule doesn't help.

## restrict: C has it, C++ doesn't

C99 offers another way: qualify a pointer with `restrict`, and the programmer promises that within that pointer's scope, objects accessed through it will not be accessed by any other route. Breaking the promise is undefined behavior. The C standard library's `memcpy` declares its two parameters this way, which is why the two memory blocks must not overlap; see [[library.c]].

C++ has no `restrict`. GCC and Clang provide the extensions `__restrict` and `__restrict__` in C++, borrowing C's semantics; MSVC provides `__restrict`. None of them are portable, and the standard says nothing about them.

```cpp run title="restrict.cpp" flags="-std=c++2c -O2" ok
#include <cstddef>
void saxpy_r(float a, const float* __restrict__ x,
             float* __restrict__ y, std::size_t n) {
  for (std::size_t i = 0; i < n; ++i) y[i] = a * x[i] + y[i];
}
```

On our test machine, this function's assembly lacks the `cmp x0, x8` / `ccmp` check and picks the vector loop based on `n` alone; the vector loop itself is instruction-for-instruction identical to `saxpy`'s. In measurements, both take about 242 ns on non-overlapping input, since the check was only a few instructions to begin with. The value of `__restrict__` lies in removing the scalar fallback path, shrinking the code, and helping in cases where no check is possible and the compiler would otherwise give up. If the caller passes overlapping arrays, the promise is broken, the compiler no longer checks, and the result is wrong.

!!! pitfall "`__restrict` does nothing on macOS"
    On our test machine, write the same function but spell it `__restrict` and include `<vector>` or `<cstdio>`, and the generated LLVM IR has no `noalias` attribute on the parameters, and the overlap check is still in the assembly. The reason is that the macOS SDK's `<sys/cdefs.h>` does `#define __restrict` (defining it as empty) when `__STDC_VERSION__ < 199901`, and when compiling C++ `__STDC_VERSION__` is not defined, so the condition is true. Including only `<cstddef>` doesn't pull in this header, so `__restrict` works again, which makes the problem hard to notice. Looking at the preprocessed output with `clang++ -E` reveals it. `__restrict__` is not defined as a macro and is unaffected.

Clang also has a form that applies only to a single loop: `#pragma clang loop vectorize(assume_safety)` tells the vectorizer there are no dependences between memory accesses in this loop. Adding it to `saxpy` on our test machine likewise removes the overlap check. Like `__restrict__`, it is a promise by the programmer, and if the promise doesn't hold, the result is wrong.

## Floating-point reductions: reordering needs permission

```cpp run title="sum.cpp" flags="-std=c++2c -O2" ok
#include <cstddef>
float sumf(const float* x, std::size_t n) {
  float s = 0;
  for (std::size_t i = 0; i < n; ++i) s += x[i];
  return s;
}
int sumi(const int* x, std::size_t n) {
  int s = 0;
  for (std::size_t i = 0; i < n; ++i) s += x[i];
  return s;
}
```

The two functions differ only in a type. At `-O2` on our test machine, `sumi`'s loop body is 4 `add.4s`, accumulating separately in 4 vector registers that are combined at the end; `sumf`'s loop body instead extracts elements from vector registers one by one and adds them with 16 scalar `fadd s0, s0, …` in turn onto the same `s0`:

```text
	ldp	q1, q2, [x10, #-32]
	mov	s3, v1[3]
	mov	s4, v1[2]
	mov	s5, v1[1]
	...
	fadd	s0, s0, s1
	fadd	s0, s0, s5
	fadd	s0, s0, s4
	fadd	s0, s0, s3
	...                         ; 16 fadds in all, all writing s0
```

The loads use vector instructions, but the additions are still one after another, each waiting for the previous result. This is the situation mentioned in the previous section: the remark is `vectorized loop (vectorization width: 4, interleaved count: 4)`, yet the speed doesn't change. LLVM calls this an in-order reduction. Cross-compiling the same code with `--target=x86_64-linux-gnu -mavx2`, Clang doesn't vectorize at all, and the remark says:

```text
sum.cpp:4:41: remark: loop not vectorized: cannot prove it is safe to reorder floating-point operations; allow reordering by specifying '#pragma clang loop vectorize(enable)' before the loop or by providing the compiler option '-ffast-math' [-Rpass-analysis=loop-vectorize]
```

### Why reordering isn't allowed

A vectorized sum uses 4 partial sums: `s0` accumulates elements 0, 4, 8…, `s1` elements 1, 5, 9…, and they are added at the end. This amounts to changing `((x0 + x1) + x2) + x3 …` into a different order of additions.

The standard prescribes the original order. Each iteration's `s += x[i]` is a full-expression, and its side effects are sequenced before the next full-expression ([[intro.execution#9]]). Note 6 (¶5) of [[expr.pre]] explains that an implementation may regroup operators according to mathematical rules only where the operators really are associative and commutative. Floating-point addition rounds at every step and is not associative. [[expr.pre#6]] allows floating-point intermediate results to be represented with greater precision (`FLT_EVAL_METHOD` reports this; it is 0 on our test machine), but that only relaxes precision, not order.

The as-if rule ([[g:as-if-rule]], [[intro.abstract#6]]) only allows transformations that don't change [[g:observable-behavior]]. Reordering the additions changes the result: summing `x[i] = 1.0f / (i + 1)` (4096 terms) on our test machine, sequential accumulation gives `8.89510822`, and the version with 16 partial sums gives `8.89510441`. If the program prints this result, the result is part of its observable behavior, so the compiler cannot reorder on its own. Incidentally, accumulating these 4096 `float`s exactly in `double` gives about `8.89510396`, so the partial-sum version is actually closer; reordering doesn't necessarily make the result worse, just different.

Integers don't have this problem. Unsigned integer arithmetic is modulo 2<sup>N</sup>, and addition is associative; signed integer overflow is UB ([[expr.pre#4]]), so the compiler may assume there is no overflow, and without overflow addition is also associative. The second half of note 6 in [[expr.pre]] also says that on machines where overflow produces no exception and results are reversible, integer expressions may be regrouped. So `sumi` needs no permission.

### How to grant permission

| Form | Scope | Standard? |
|---|---|---|
| `-ffast-math` | Whole translation unit | Compiler option |
| `-fassociative-math -fno-signed-zeros` | Whole translation unit | Compiler option |
| `#pragma clang fp reassociate(on)` | The enclosing compound statement | Clang extension |
| `#pragma clang loop vectorize(enable)` | The next loop | Clang extension |
| `#pragma omp simd reduction(+ : s)` with `-fopenmp-simd` | The next loop | OpenMP |
| `std::reduce(first, last, init)` | This call | Standard, C++17 |
| `std::reduce(std::execution::unseq, …)` | This call | Standard, C++20 |

`-ffast-math` turns on far more than reordering. On our test machine, `clang++ -### -ffast-math` shows it also passes options such as `-menable-no-nans`, `-menable-no-infs`, `-freciprocal-math` and `-ffp-contract=fast`; the first two let the compiler assume there are no NaNs or infinities, and checks like `std::isnan(x)` may be optimized into the constant `false`. It applies to the whole translation unit, including included headers. When you only want to relax a single loop, use one of the narrower forms.

Adding `-fassociative-math` alone has no effect on our test machine: there is no `-mreassociate` in the `-###` output, and `sumf` still accumulates in order. It takes effect only together with `-fno-signed-zeros`.

The return value of `std::reduce` is specified as *GENERALIZED_SUM* ([[reduce#7]]). By [[numerics.defns#2]], it may permute the elements arbitrarily and parenthesize arbitrarily, which is exactly the permission vectorization needs. This permission also holds for the overload without an execution policy, and the note in [[reduce#9]] specifically points out that floating-point addition may therefore give nondeterministic results. But the standard only permits this, and implementations need not take advantage of it: the libc++ `std::reduce(first, last, init)` on our test machine is an ordinary loop, with the same result and speed as the hand-written loop.

### Measurements on our test machine

```cpp title="sum_bench.cpp" ok
#include "bench.hpp"
#include <cstddef>
#include <cstdio>
#include <execution>
#include <numeric>
#include <vector>

[[gnu::noinline]] float sum(const float* x, std::size_t n) {
  float s = 0;
  for (std::size_t i = 0; i < n; ++i) s += x[i];
  return s;
}
[[gnu::noinline]] float sum_pragma(const float* x, std::size_t n) {
  float s = 0;
#pragma clang loop vectorize(enable)
  for (std::size_t i = 0; i < n; ++i) s += x[i];
  return s;
}
[[gnu::noinline]] float sum_reduce(const float* x, std::size_t n) {
  return std::reduce(x, x + n, 0.0f);
}
[[gnu::noinline]] float sum_unseq(const float* x, std::size_t n) {
  return std::reduce(std::execution::unseq, x, x + n, 0.0f);
}
[[gnu::noinline]] int sum_int(const int* x, std::size_t n) {
  int s = 0;
  for (std::size_t i = 0; i < n; ++i) s += x[i];
  return s;
}

int main() {
  bench::prefer_performance_cores();
  const std::size_t n = 4096;
  std::vector<float> xf(n);
  std::vector<int> xi(n);
  for (std::size_t i = 0; i < n; ++i) {
    xf[i] = 1.0f / float(i + 1);
    xi[i] = int(i);
  }
  auto test = [&](const char* name, auto f, auto* p) {
    bench::run(name, [&] {
      bench::do_not_optimize(p);
      auto r = f(p, n);
      bench::do_not_optimize(r);
    });
    std::printf("  result %.9g\n", double(f(p, n)));
  };
  test("loop", sum, xf.data());
  test("pragma", sum_pragma, xf.data());
  test("reduce", sum_reduce, xf.data());
  test("reduce(unseq)", sum_unseq, xf.data());
  test("int loop", sum_int, xi.data());
}
```

```bash
clang++ -std=c++2c -O2 -fexperimental-library sum_bench.cpp -o sum_bench && ./sum_bench
clang++ -std=c++2c -O2 -fexperimental-library -ffast-math sum_bench.cpp -o sum_fm && ./sum_fm
```

| Version (4096 elements) | Default options | `-ffast-math` | Result |
|---|---|---|---|
| Hand-written loop | about 3.6–3.8 µs | about 211 ns | `8.89510822` / `8.89510441` |
| `vectorize(enable)` | about 213 ns | about 212 ns | `8.89510441` |
| `std::reduce` | about 3.6 µs | about 212 ns | `8.89510822` / `8.89510441` |
| `std::reduce(unseq, …)` | about 213 ns | about 212 ns | `8.89510441` |
| `int` hand-written loop | about 148 ns | about 148 ns | — |

The in-order floating-point sum adds only about 1.1 elements per nanosecond. A floating-point addition on the M2 has a latency of several cycles, each one waits for the previous, and the speed is determined by this dependency chain. With permission, the same loop is about 17 times faster.

### Interleave count

Another reason the `vectorize(enable)` version is fast is interleaving. `#pragma clang loop interleave_count(N)` specifies the interleave count, that is, how many vector registers accumulate separately:

```cpp title="interleave_bench.cpp (excerpt)" ok
#include <cstddef>
[[gnu::noinline]] float ic8(const float* x, std::size_t n) {
  float s = 0;
#pragma clang loop vectorize(enable) interleave_count(8)
  for (std::size_t i = 0; i < n; ++i) s += x[i];
  return s;
}
```

| `interleave_count` | Median on our test machine (4096 `float`s) |
|---|---|
| 1 | about 886 ns |
| 2 | about 414 ns |
| 4 (the value Clang chooses by default) | about 213 ns |
| 8 | about 116 ns |

With an interleave count of 1, all the additions go onto one vector accumulator, which is back to a single dependency chain, just adding 4 elements per link. The more accumulators, the more additions can be in the pipeline at once. At this data size on our test machine, 8 accumulators are about 1.8 times faster again than the compiler's default of 4; when the data isn't in L1, the bottleneck shifts to memory and the gap may not remain. The optimal interleave count and width depend on the specific CPU, which is exactly why the compiler leaves them to its cost model by default.

## Conditions: masks and selects

```cpp run title="cond.cpp" flags="-std=c++2c -O2" ok
#include <cstddef>
void relu(float* y, const float* x, std::size_t n) {
  for (std::size_t i = 0; i < n; ++i)
    y[i] = x[i] > 0 ? x[i] : 0.0f;
}
void store_if(float* y, const float* x, std::size_t n) {
  for (std::size_t i = 0; i < n; ++i)
    if (x[i] > 0) y[i] = x[i];
}
```

A vectorized loop has no per-element branches. `relu` is rewritten into a comparison and a select: `fcmgt.4s` generates an all-ones or all-zeros **mask** for each of 4 lanes, then `and.16b` zeroes the lanes that fail the condition, processing 16 elements per iteration without a single jump. On x86 with `-mavx2` it uses `vmaxps` directly.

`store_if` is different: when the condition is false, the original program does not write `y[i]` at all. The compiler cannot turn this into unconditionally writing back the old value, because another thread might be writing that location, and a write out of nowhere would create a data race the original program didn't have. Note 19 (¶19) of [[intro.races]] says that introducing writes the abstract machine would not perform is generally not allowed. x86 AVX2 has masked store instructions, and cross-compiling with `-mavx2` on our test machine gives `vcmpltps` plus `vmaskmovps`. NEON has no such instruction; Clang reports the loop as vectorized, but what it actually generates for each lane is one `fcmp`, one conditional jump and one single-lane store `st1.s { v3 }[1]`.

| Median on our test machine (4096 `float`s) | All positive | Random signs |
|---|---|---|
| `relu`: select | about 200 ns | about 240 ns |
| `store_if`: conditional store | about 1.3 µs | about 1.65 µs |
| `y[i] = x[i] > 0 ? x[i] : y[i]` | about 1.5 µs | about 2.7 µs |

The last row explicitly writes back the old value, so by its semantics it writes every time and could seemingly become an unconditional select plus store. Yet Clang on our test machine does not vectorize it, reporting `the cost-model indicates that vectorization is not beneficial`, and the generated scalar loop reads and writes `y[i]` only when the condition holds. This shows that after rewriting you have to check the remarks and assembly again; you cannot assume the compiler will generate code according to your intent. It is slower with random signs because the remaining branch is unpredictable; see [[perf/branches]].

## gather: reading by index

```cpp run title="gather.cpp" flags="-std=c++2c -O2" ok
#include <cstddef>
int sum_idx(const int* a, const int* idx, std::size_t n) {
  int s = 0;
  for (std::size_t i = 0; i < n; ++i) s += a[idx[i]];
  return s;
}
```

The 4 elements of `a[idx[i]]` are not adjacent, which requires a **gather** (reading separately at a set of indices and packing the results into one vector). NEON has no gather instruction; Clang on our test machine reports `the cost-model indicates that vectorization is not beneficial` and produces only a 4-way interleaved scalar loop.

On x86 it depends on `-march`. Cross-compiling on our test machine, `-mavx2`, `-march=haswell` and `-march=x86-64-v3` do not use AVX2's `vpgatherdd` but insert elements into a vector one by one with `vpinsrd`; `-march=skylake`, `-march=icelake-server` and `-march=znver4` use `vpgatherdd`. Gather instructions vary greatly in speed across microarchitectures, and the compiler's cost model decides whether to use them based on the target CPU.

| Median on our test machine (4096 `int`s, all in L1) | |
|---|---|
| `a[i]` | about 148 ns |
| `a[idx[i]]`, `idx` sequential | about 666 ns |
| `a[idx[i]]`, `idx` shuffled | about 666 ns |

With sequential indices, `a[idx[i]]` actually reads consecutive elements too, but the compiler cannot see that at compile time and treats it as a gather anyway, 4.5 times slower. With all the data in L1, shuffled indices are no slower; when the data is large enough to come from memory, shuffled access also meets cache misses. Turning indirect access into contiguous access (for example by first reordering the data by index) is usually more effective than relying on gather.

## Alignment

Early SIMD instructions required addresses aligned to the vector width, and unaligned loads either faulted or were much slower, hence the circulating advice to align arrays before vectorizing. In the assembly above, x86 uses `movups` and `vmovups`, which don't require alignment, and arm64's `ldp q` doesn't require 16-byte alignment either. The compiler generated no extra code for alignment.

On our test machine we placed the `x` and `y` arrays in 64-byte-aligned buffers, offsetting their starts by 0 to 32 bytes, and measured `saxpy`:

```cpp title="align_bench.cpp" ok
#include "bench.hpp"
#include <algorithm>
#include <cstddef>
#include <cstdio>
#include <cstdlib>
#include <new>

[[gnu::noinline]] void saxpy(float a, const float* x,
                             float* y, std::size_t n) {
  for (std::size_t i = 0; i < n; ++i) y[i] = a * x[i] + y[i];
}

int main(int argc, char** argv) {
  bench::prefer_performance_cores();
  std::size_t n = argc > 1 ? std::strtoul(argv[1], nullptr, 10) : 4096;
  std::size_t bytes = n * sizeof(float) + 64;
  // two 64-byte-aligned buffers, with 64 extra bytes for offsetting the start
  auto* bx = static_cast<char*>(std::aligned_alloc(64, bytes));
  auto* by = static_cast<char*>(std::aligned_alloc(64, bytes));
  for (int off : {0, 4, 8, 16, 32}) {
    float* x = new (bx + off) float[n];   // create a float array at the offset
    float* y = new (by + off) float[n];
    std::fill(x, x + n, 1.0f);
    std::fill(y, y + n, 0.0f);
    char name[32];
    std::snprintf(name, sizeof name, "offset %2d", off);
    bench::run(name, [&] {
      bench::do_not_optimize(x);
      saxpy(1.0f, x, y, n);
      bench::clobber_memory();
    });
  }
  std::free(bx);
  std::free(by);
}
```

| Start offset (bytes) | n = 4096, in L1 | n = 16777216, in memory |
|---|---|---|
| 0 | about 242 ns | about 2.2–2.5 ms |
| 4 | about 329 ns | about 2.2–2.5 ms |
| 8 | about 329 ns | about 2.2–2.5 ms |
| 16 | about 242 ns | about 2.2–3.1 ms |
| 32 | about 242 ns | about 2.2–3.1 ms |

With the data in L1, arrays whose start is not a multiple of 16 are about 36% slower: a 16-byte load sometimes straddles a 64-byte cache line boundary and has to access two cache lines. 16-byte alignment is enough; aligning further to 32 or 64 bytes changes nothing. With the data in memory, the minimum for every offset is around 2.2 ms, and the differences in medians are within the noise of this busy machine, with no visible effect.

Memory returned by `new` is at least 16-byte aligned on our test machine, and the data of a `std::vector<float>` generally already satisfies this. Where misalignment really occurs is subarrays sliced out of the middle of a large buffer. Whether it is worth handling, measure once at your own data size.

## Stating intent in the code

### Clang's loop pragmas

`#pragma clang loop` is written before a loop and affects only that loop:

| Form | Effect |
|---|---|
| `vectorize(enable)` / `vectorize(disable)` | Request or forbid vectorization; `enable` also allows reordering floating-point reductions |
| `vectorize_width(N)` | Specify the width |
| `interleave_count(N)` / `interleave(disable)` | Specify the interleave count or forbid interleaving |
| `vectorize(assume_safety)` | Assume no dependences between memory accesses, skip the overlap check |

`vectorize(enable)` does not make the compiler generate wrong code. Adding it to `prefix`, our test machine still gets the `unsafe dependent memory operations` analysis remark, plus a warning:

```text
prefix.cpp:4:3: warning: loop not vectorized: the optimizer was unable to perform the requested transformation; the transformation might be disabled or specified as part of an unsupported transformation ordering [-Wpass-failed=transform-warning]
```

So it is good for checking whether a hot loop really is vectorized: when it can't be, the compiler warns. `assume_safety` is different; it hands safety over to the programmer.

### The `unseq` execution policy

C++17 merged the parallel algorithms of the Parallelism TS into the standard ([[P0024R2]]), and C++20 added `std::execution::unseq`, which vectorizes without spawning threads ([[P1001R2]]). The meaning of the policies is in [[execpol]]. Per [[algorithms.parallel.exec#5]], when an algorithm is invoked with `unseq`, the functions called on elements may execute unordered and interleaved on the calling thread, which is exactly the permission SIMD needs. The price is that these functions must not call [[g:vectorization-unsafe]] standard library functions (such as locking), or the behavior is undefined.

!!! impl "libc++ (LLVM 23)"
    - Execution policies are an experimental feature requiring `-fexperimental-library`; without it, `std::execution::unseq` does not exist, and with it, `__cpp_lib_execution` and `__cpp_lib_parallel_algorithm` are still not defined. The full implementation status is at the end of the [[algorithms.parallel]] page.
    - The `unseq` version of `reduce` contains no hand-written SIMD code; instead it puts `#pragma clang loop vectorize(enable) interleave(enable)` before an ordinary loop (`_PSTL_PRAGMA_SIMD_REDUCTION`, defined in `__configuration/pstl.h`). On our test machine it gives the same result and speed as the hand-written `vectorize(enable)` loop above.

`par_unseq` additionally allows multithreaded execution. Whether multithreading pays off depends on data size and thread scheduling, and must be measured separately.

### `std::simd` {{c++26}}

C++26 adds `<simd>` ([[simd]], [[P1928R15]]), letting programmers write data-parallel types directly instead of relying on the compiler to recognize loops. `std::simd::vec<float>` is a vector of `float` with a width chosen for the target platform; arithmetic operates lane by lane, and the result of `std::simd::reduce` is likewise defined as *GENERALIZED_SUM* ([[simd.reductions#3]]), so the reordering is written into the interface.

Clang 23 + libc++ on our test machine has no `<simd>` header; the code below is written against the current draft and has not been compiled, so it carries no verdict marker:

```cpp title="simd-sum.cpp"
#include <cstddef>
#include <simd>

float sum(const float* x, std::size_t n) {
  namespace sd = std::simd;
  using V = sd::vec<float>;
  constexpr std::size_t w = V::size();
  V acc(0.0f);
  std::size_t i = 0;
  for (; i + w <= n; i += w)
    acc += sd::unchecked_load<V>(x + i, w);
  acc += sd::partial_load<V>(x + i, n - i);  // the tail; missing lanes are filled with 0
  return sd::reduce(acc);
}
```

`unchecked_load` requires at least `w` elements in the range; `partial_load` reads only the elements that actually exist, and the remaining lanes take `T()` ([[simd.loadstore#9]]). This style writes the vector width, tail handling and summation order into the code, at the cost of being longer than a `for` loop. Whether it is worth it compared with auto-vectorization has to wait for implementations, to be compared on specific loops.

## Questions

!!! question "1"
    Change `sumf`'s accumulator to `double s = 0;`, with `s += x[i];` in the loop and `return float(s);` at the end. Can the compiler vectorize it without any permission?

<details markdown="1">
<summary>Answer</summary>

No. Higher precision does not change the problem: `double` addition also rounds and is likewise not associative, so reordering may still change the result, which the as-if rule does not allow ([[intro.abstract#6]]). [[expr.pre#6]] allows implementations to evaluate floating-point expressions with greater precision, but only while keeping the original order of operations. Accumulating in `double` reduces error; vectorization still needs permission.
</details>

!!! question "2"
    The loop body of `void scale(float* y, const float* x, std::size_t n, const float* k)` is `y[i] = x[i] * *k;`. Why might the compiler have to reload `*k` on every iteration? How does the vectorized version handle it?

<details markdown="1">
<summary>Answer</summary>

`k` and `y` have the same type, and `k` may point to some element of `y`; after writing `y[i]`, the value of `*k` may have changed, and strict aliasing ([[basic.lval#11]]) doesn't help. The scalar version therefore has to reload it on every iteration. The vectorized version includes `k` in the run-time check: only after confirming that `*k` is not within `y`'s range does it read `*k` once and broadcast it to all lanes. The `-O2` assembly on our test machine does exactly this: there are two `cmp`/`ccmp` groups at the entry, the scalar fallback loop executes `ldr s1, [x3]` on every iteration, and the vector loop reads it only once beforehand. Writing `float kv = *k;` to copy it into a local variable first puts the read-once intent into the code, and `k` no longer needs checking.
</details>

!!! question "3"
    Why does using `std::reduce(v.begin(), v.end(), 0.0f)` instead of `std::accumulate` not get faster with libc++ on our test machine? Does the standard allow it to be faster?

<details markdown="1">
<summary>Answer</summary>

It does. The return value of `reduce` is *GENERALIZED_SUM* ([[reduce#7]]), which may be reordered and parenthesized arbitrarily ([[numerics.defns#2]]), so an implementation is entirely free to use partial sums. But the no-policy version in libc++ on our test machine is an ordinary loop; the compiler cannot see the permission the standard grants and has to accumulate in order. To get vectorization on our test machine, you need `std::execution::unseq` (libc++ passes the permission to the compiler via a pragma) or one of the other forms in the table above.
</details>

## Summary

| Question | Conclusion | Basis |
|---|---|---|
| How much does vectorization bring? | `saxpy` about 3.6x within L1 on our test machine, about 2x in memory | Measurements on our test machine |
| What conditions are needed? | Countable loop, no loop-carried dependences, provable non-overlap | Compiler remarks |
| Pointers of the same type | Run-time overlap check inserted; scalar loop on overlap | Assembly on our test machine |
| Pointers of different types | Assumed non-overlapping by strict aliasing, no check | [[basic.lval#11]] |
| `restrict` | C has it; C++ has only compiler extensions; `__restrict` is macro'd away on macOS | C99, `<sys/cdefs.h>` |
| Floating-point sums | Cannot be reordered on the compiler's own initiative; needs permission | [[intro.execution#9]], [[expr.pre]] note 6, [[intro.abstract#6]] |
| The standard's permission | *GENERALIZED_SUM* of `std::reduce`, the `unseq` policy | [[reduce#7]], [[algorithms.parallel.exec#5]] |
| Integer sums | Need no permission | [[expr.pre#4]] |
| Conditional stores | Cannot become unconditional stores; per-lane branches on NEON | [[intro.races]] note 19 |
| Alignment | 16-byte alignment matters within L1 on our test machine; larger alignment and in-memory data show no visible effect | Measurements on our test machine |
