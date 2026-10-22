---
title: Branches and branch prediction
summary: "What conditional branches and indirect calls really cost on a modern CPU: how branch prediction works, how many nanoseconds a misprediction is worth, when the compiler removes a branch on its own, when branchless code wins and when it loses, and what likely/unlikely, PGO, virtual calls, switch and std::unreachable change in the assembly and in measurements."
tags: performance, branch prediction, assembly, likely, PGO, virtual functions, switch
updated: 2026-10-19
group: Code
---

!!! tldr
    - A branch itself is nearly free; what costs is a misprediction. On our test machine one mispredicted conditional branch loses about 5 ns, roughly fifteen to twenty cycles.
    - The classic sorted-array-sum example becomes a `csel` at Clang 23's `-O1` and is vectorized at `-O2`, so sorting no longer makes a difference. Only branches the compiler cannot remove (such as a conditional memory write) expose the cost of misprediction.
    - Branchless code trades a control dependency for a data dependency and computes both sides. It wins when the branch is hard to predict and loses when the branch is predictable and one side is expensive; we measured a 5x difference.
    - `[[likely]]`/`[[unlikely]]` only change branch weights and thus the layout of code blocks; they do not change the predictor. A correct guess was 1.7x faster in our tests, a wrong one 2x slower. PGO replaces guesses with real execution counts, but it slows things down just the same when the training data is unrepresentative.
    - Virtual calls and dense `switch` statements are both indirect jumps: with a fixed target they cost about as much as a direct call; with a random target each one costs several nanoseconds more. `std::unreachable()` can remove the range check in front of a jump table; we could not measure a difference.

!!! note "Test setup and method"
    All numbers come from an Apple M2 Pro (arm64, macOS) with Homebrew Clang 23.1.3 and libc++, using `clang++ -std=c++2c -O2` unless stated otherwise. The data is one observation on this machine; with another CPU or compiler version, the numbers and even the conclusions may change. The machine was heavily loaded during measurement, so absolute numbers may be inflated, and misprediction-heavy tests fluctuate particularly; the text gives ranges over several runs. Ratios measured one after another in the same process are more reliable than absolute values, and conclusions about what the compiler did are based on the assembly.

    Timing uses the tiny tool below: warm up once, repeat several times, take the median. `escape` uses an empty inline asm statement to pretend it reads the result; the compiler cannot see what the asm does, so it has to actually compute the result. The principle and a more complete version are in [[perf/measuring]].

    ```cpp title="bench.h"
    #pragma once
    #include <algorithm>
    #include <chrono>
    #include <cstdio>
    #include <vector>

    template <class T>
    inline void escape(T const& v) {
      asm volatile("" : : "r"(&v) : "memory");
    }

    template <class F>
    double bench_ns(F f, int reps = 15) {
      using clk = std::chrono::steady_clock;
      f();                       // warm-up
      std::vector<double> t;
      for (int i = 0; i < reps; ++i) {
        auto a = clk::now();
        f();
        auto b = clk::now();
        t.push_back(std::chrono::duration<double, std::nano>(b - a).count());
      }
      std::sort(t.begin(), t.end());
      return t[t.size() / 2];    // median
    }
    ```

## Why is a sorted array faster?

```cpp title="sum.cpp" ok
#include "bench.h"
#include <random>

long sum_big(const std::vector<int>& v) {
  long s = 0;
  for (int x : v)
    if (x >= 128) s += x;
  return s;
}

int main() {
  std::vector<int> v(1 << 20);
  std::mt19937 rng(42);
  for (int& x : v) x = rng() % 256;
  auto run = [&](const char* name) {
    double ns = bench_ns([&] { long s = sum_big(v); escape(s); });
    std::printf("%-9s %6.2f ns/elem\n", name, ns / v.size());
  };
  run("random");
  std::sort(v.begin(), v.end());
  run("sorted");
}
```

This is a widely circulated example: the same data sums faster after sorting. Compiled at different optimization levels on our test machine, the results are:

| Optimization level | Random order | Sorted |
|---|---|---|
| `-O0` | 8.65 ns/element | 4.78 ns/element |
| `-O1` | 0.34 | 0.39 |
| `-O2` | 0.08 | 0.08 |
| `-O3` | 0.08 | 0.08 |

Only `-O0` reproduces the effect. The loop bodies generated at each level show why (`clang++ -std=c++2c -O1 -S`, loop only):

<div class="compare" markdown="1">

```asm
; -O0: a real conditional branch
  ldr   w8, [sp, #4]
  subs  w8, w8, #128
  b.ge  LBB0_3     ; jump if x >= 128
  b     LBB0_4
LBB0_3:
  ldrsw x9, [sp, #4]
  ldur  x8, [x29, #-16]
  add   x8, x8, x9
  stur  x8, [x29, #-16]
```

```asm
; -O1: no conditional jump
LBB0_2:
  ldr   w10, [x8], #4
  cmp   w10, #127
  csel  w10, w10, wzr, gt
  add   x0, x0, x10
  cmp   x8, x9
  b.ne  LBB0_2     ; only the loop back-edge remains
```

</div>

`-O1` replaced the `if` with `csel` (conditional select): compare first, then pick one of two registers based on the result, `x` when `x > 127`, otherwise the zero register `wzr`, and add unconditionally. The x86-64 equivalent is `cmov`; compiling the same function with `--target=x86_64-linux-gnu -O1` shows `cmovlel`. `-O2` goes further: NEON compares 4 elements at once (`cmgt.4s`), uses the result as a mask ANDed with the original values, and accumulates; the whole loop again has no data-dependent jump. Vectorization details are in [[perf/vectorization]].

The compiler is entitled to rewrite this under the as-if rule ([[g:as-if-rule]]): an implementation only needs to emulate the observable behavior of the abstract machine ([[intro.abstract#1]]). Here `x` was read unconditionally anyway, and adding zero is observably the same as not adding, so whether a branch exists is outside what the standard specifies.

## What the branch predictor does

A CPU splits an instruction into stages such as fetch, decode, execute and write-back, and processes dozens to hundreds of instructions at once like an assembly line. At a conditional jump, whether to jump is known only once the comparison finishes, but the pipeline cannot stop and wait, or every branch would idle for a dozen or more cycles.

So the CPU guesses a direction first and keeps fetching and executing along the guessed path. This is called **speculative execution**. The component that guesses is the **branch predictor**. It records each branch's recent history and the directions other branches took before reaching this one, and uses these patterns to predict the next outcome. For indirect jumps (jumps whose target address is in a register, such as virtual calls), it also has to predict which address to go to.

A correct guess makes the branch nearly free. A wrong one is a **branch misprediction**: all speculatively executed results are discarded and fetching restarts from the correct address, losing roughly the depth of the pipeline in time. With ordered data, `x >= 128` is a long run of false followed by a long run of true, and the predictor is right almost every time; with random data, it can only be right about half the time.

## Keeping the branch: conditional memory writes

To observe the cost of misprediction we need a branch the compiler cannot remove. Change the sum into a filter that writes only the elements meeting the condition to an output array:

```cpp title="filter.cpp" godbolt flags="-std=c++2c -O2" ok
long filter_big(const int* in, long n, int* out) {
  long k = 0;
  for (long i = 0; i < n; ++i)
    if (in[i] >= 128) out[k++] = in[i];
  return k;
}
```

`-O2` unrolls the loop 8 times, but each element still has a conditional jump that skips the `str`:

```asm
LBB0_6:
  ldur  w13, [x12, #-16]
  cmp   w13, #128
  b.lt  LBB0_8          ; skip the write if less than 128
  str   w13, [x2, x0, lsl #2]
  add   x0, x0, #1
LBB0_8:
  ldur  w13, [x12, #-12]
  ...
```

The compiler cannot turn this into an unconditional write. When the condition is false, the abstract machine does not write `out[k]` at all; `out` might only be big enough for the elements that meet the condition, or another thread might be reading that location. A note in [[intro.races#19]] says explicitly that introducing writes the abstract machine would not perform is generally not allowed, because it may create a data race that did not exist.

Scanning a 1M-element array with this function, controlling the probability p that the condition holds:

| p (condition true) | 0% | 1% | 5% | 10% | 25% | 50% | 75% | 90% | 99% | 100% | Sorted |
|---|---|---|---|---|---|---|---|---|---|---|---|
| With branch (ns/element) | 0.31 | 0.36 | 0.56 | 0.81 | 1.59 | 3.03 | 1.75 | 0.76 | 0.33 | 0.31 | 0.31 |

The curve is symmetric around its peak at 50%, and sorted data is as fast as p = 0%. At 50% there is roughly one misprediction every two elements, about 2.7 ns/element more than the fully predictable case, which works out to about 5.4 ns per misprediction; at the M2 Pro performance cores' roughly 3.5 GHz that is about 19 cycles. This is an estimate derived from timing, not a hardware counter reading; for how to read counters see [[perf/profiling]].

## Branchless code

### Conditional select: turning the condition into data

Since the compiler cannot write unconditionally for us, we can do it by hand: write unconditionally, advance conditionally:

<div class="compare" markdown="1">

```cpp
// with a branch
for (long i = 0; i < n; ++i)
  if (in[i] >= 128)
    out[k++] = in[i];
```

```cpp
// branchless: out must have at least n elements
for (long i = 0; i < n; ++i) {
  out[k] = in[i];          // always write
  k += (in[i] >= 128);     // the condition only decides the index
}
```

</div>

The version on the right changes the program's semantics: it writes positions past `out[k]`, so the caller must guarantee that `out` has room for `n` elements. That is exactly the step the compiler cannot take on its own. The generated code uses `cinc` (conditional increment) instead of a jump:

```asm
LBB1_3:
  ldur  w12, [x11, #-4]
  str   w12, [x2, x8, lsl #2]   ; unconditional write
  cmp   w12, #127
  cinc  x8, x8, gt              ; k + 1 when the condition holds
  ...
```

The branchless version runs at about 0.31 ns/element for every p, matching the best case of the branchy version. There is nothing to predict, so there is no misprediction.

### Arithmetic masks and lookup tables

Two other common techniques: build an all-zeros or all-ones **mask** from the comparison result and select the result with bitwise AND; or precompute a chain of `if`s into a table, so that run time does a single indexed access.

```cpp
unsigned m = -(unsigned)(x >= 1000);     // 0xFFFFFFFF if true, otherwise 0
r = (a & m) | (b & ~m);                  // a if true, otherwise b
```

Tables suit cases where the input is sorted into a few classes. The example below classifies characters as digit, uppercase, lowercase or other:

```cpp title="lut.cpp" ok
#include "bench.h"
#include <array>
#include <random>

constexpr int cls_if(unsigned char c) {
  if (c >= '0' && c <= '9') return 1;
  if (c >= 'A' && c <= 'Z') return 2;
  if (c >= 'a' && c <= 'z') return 3;
  return 0;
}

constexpr auto table = [] {         // 256 entries computed at compile time
  std::array<unsigned char, 256> t{};
  for (int c = 0; c < 256; ++c) t[c] = cls_if(c);
  return t;
}();

[[gnu::noinline]] long sum_if(const unsigned char* s, long n) {
  long r = 0;
  for (long i = 0; i < n; ++i) r += cls_if(s[i]);
  return r;
}
[[gnu::noinline]] long sum_lut(const unsigned char* s, long n) {
  long r = 0;
  for (long i = 0; i < n; ++i) r += table[s[i]];
  return r;
}

int main() {
  const long n = 1 << 20;
  std::vector<unsigned char> s(n);
  std::mt19937 rng(7);
  const char* alpha = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                      "abcdefghijklmnopqrstuvwxyz +-*/.,";
  for (auto& c : s) c = alpha[rng() % 68];
  double a = bench_ns([&] { long r = sum_if(s.data(), n); escape(r); });
  double b = bench_ns([&] { long r = sum_lut(s.data(), n); escape(r); });
  std::sort(s.begin(), s.end());
  double c = bench_ns([&] { long r = sum_if(s.data(), n); escape(r); });
  std::printf("random: if %.3f  lut %.3f   sorted: if %.3f ns/byte\n",
              a / n, b / n, c / n);
}
```

At `-O2`, `cls_if` is still two conditional jumps plus a `csel`. Results on our test machine: on random text the `if` chain takes 3.33 ns/byte and the table 0.22 ns/byte; after sorting the text, the `if` chain drops to 0.53 ns/byte. The table is 15x faster, the sorted `if` chain 6x faster, and nearly the whole gap comes from mispredictions. Tables require the table to be small enough to stay in L1 cache; here it is only 256 bytes. A bigger table may trade mispredictions for cache misses; see [[perf/memory-hierarchy]].

### When branchless is slower

Branchless code computes both paths and throws away one result. If one path is expensive and rarely taken, a branch lets the CPU skip it, but branchless code pays for it every time. `slow` below does three divisions by a divisor known only at run time:

```cpp title="lose.cpp" ok
#include "bench.h"
#include <random>

inline unsigned slow(unsigned x, unsigned d) {  // run-time divisor: real divide instructions
  return x / d / d / d;
}

[[gnu::noinline]] unsigned long sum_branchy(const unsigned* v, long n, unsigned d) {
  unsigned long s = 0;
  for (long i = 0; i < n; ++i)
    s += v[i] >= 1000 ? slow(v[i], d) : v[i];
  return s;
}

[[gnu::noinline]] unsigned long sum_mask(const unsigned* v, long n, unsigned d) {
  unsigned long s = 0;
  for (long i = 0; i < n; ++i) {
    unsigned x = v[i];
    unsigned m = -(unsigned)(x >= 1000);    // all ones or all zeros
    s += (slow(x, d) & m) | (x & ~m);       // compute both sides
  }
  return s;
}

int main() {
  const long n = 1 << 20;
  volatile unsigned vd = 3; unsigned d = vd;
  std::vector<unsigned> v(n);
  std::mt19937 rng(1);
  for (int pct : {1, 50}) {
    for (auto& x : v) x = (int)(rng() % 100) < pct ? 5000 + rng() % 1000 : rng() % 1000;
    double a = bench_ns([&] { auto s = sum_branchy(v.data(), n, d); escape(s); });
    double b = bench_ns([&] { auto s = sum_mask(v.data(), n, d); escape(s); });
    std::printf("slow path %2d%%: branchy %.3f  mask %.3f ns/elem\n", pct, a / n, b / n);
  }
}
```

| Fraction taking the slow path | With branch | Mask |
|---|---|---|
| 1% | 0.36 ns/element | 1.85 ns/element |
| 50% | 2.92 | 1.85 |

The divisor is read through a `volatile` so the compiler cannot replace division by a constant with multiplication. When the slow path is only 1%, the branch is nearly always predicted correctly and the branchy version is 5x faster than the mask; at 50%, mispredictions dominate and the mask wins. Incidentally, the compiler recognized the intent of the mask version: the loop in `sum_mask` has 12 `udiv`s plus 4 `csel`s, while `sum_branchy` keeps its conditional jump and is not turned branchless on the compiler's own initiative.

So branchless code is not a universal optimization. It suits cases where both sides are cheap and the condition is hard to predict; when the branch is predictable, or one side is clearly more expensive, keeping the branch is better. The compiler chooses between the two based on its cost model and on branch probabilities, which are the topic of the next section.

## `[[likely]]` and `[[unlikely]]` {{c++20}}

!!! std "[dcl.attr.likelihood]/2 (note)"
    The use of the likely attribute is intended to allow implementations to optimize for the case where paths of execution including it are arbitrarily more likely than any alternative path of execution that does not include such an attribute.

These two attributes go on a statement or label ([[dcl.attr.likelihood#1]]) and tell the compiler that this path is much more or much less common than the others. The sentence above comes from a note and has no normative force: the standard does not require implementations to do anything with it, and ignoring the attributes entirely is conforming. Syntax and placement rules are in [[dcl.attr.likelihood]].

### What it changes in the assembly

```cpp title="process.cpp" godbolt flags="-std=c++2c -O2" ok
void log_error(int);
int process(int x) {
  if (x < 0) [[likely]] {     // deliberately marked wrong, to see what happens
    log_error(x);
    return -1;
  }
  return x * 3 + 1;
}
```

`-O2` output without and with the attribute:

<div class="compare" markdown="1">

```asm
; no attribute
  tbnz  w0, #31, LBB0_2  ; jump only if negative
  add   w8, w0, w0, lsl #1
  add   w0, w8, #1
  ret
LBB0_2:
  stp   x29, x30, [sp, #-16]!
  mov   x29, sp
  bl    __Z9log_errori
  mov   w0, #-1
  ldp   x29, x30, [sp], #16
  ret
```

```asm
; [[likely]] on the error path
  tbz   w0, #31, LBB0_2  ; jump only if non-negative
  stp   x29, x30, [sp, #-16]!
  mov   x29, sp
  bl    __Z9log_errori
  mov   w0, #-1
  ldp   x29, x30, [sp], #16
  ret
LBB0_2:
  add   w8, w0, w0, lsl #1
  add   w0, w8, #1
  ret
```

</div>

The instructions are identical; only the two blocks swap places. The block considered common follows the test directly and is reached without a jump. Without the attribute, Clang already treats the side that calls `log_error` as the cold path; changing `[[likely]]` to `[[unlikely]]` gives output identical, character for character, to the version without the attribute.

LLVM IR (`-S -emit-llvm`) shows what the attribute turns into:

```text
br i1 %2, label %3, label %4, !prof !10
!10 = !{!"branch_weights", !"expected", i32 2000, i32 1}
```

This is a branch weight, 2000 to 1. The `__builtin_expect(x < 0, 1)` that GCC and Clang have had for a long time produces the same metadata. So `[[likely]]` does not control the hardware directly, and the predictors of modern CPUs do not read compiler hints. What it affects is the compiler's decisions: how blocks are laid out, whether to inline, whether to use `csel`, how loops are unrolled.

### Measured: right guess and wrong guess

Adding the attributes to the filter loop from the previous section, and running each of the three versions:

| p (condition true) | No attribute | `[[likely]]` | `[[unlikely]]` |
|---|---|---|---|
| 1% | 0.36 ns/element | 0.39 | 0.21 |
| 50% | 2.9 | 2.9 | 3.0–3.9 |
| 99% | 0.31 | 0.31 | 0.70 |

(Over several runs, `[[likely]]` occasionally reached 0.6 at 99%, and `[[unlikely]]` fluctuated considerably at 50%.)

The `[[likely]]` output is the same as without the attribute, so no difference can be measured. `[[unlikely]]` moves all eight `str`s out of the loop body: the body becomes eight comparisons, each with a rarely taken `b.ge`, and the writes are placed after the loop, jumping back when done.

```asm
LBB2_5:                     ; loop body, straight-line when the condition is false
  ldur  w13, [x12, #-16]
  cmp   w13, #128
  b.ge  LBB2_14             ; rarely taken
LBB2_6:
  ldur  w13, [x12, #-12]
  ...
LBB2_14:                    ; cold path: write, then jump back
  str   w13, [x2, x0, lsl #2]
  add   x0, x0, #1
  b     LBB2_6
```

At p = 1% this layout is 1.7x faster than the default; at p = 99% nearly every element has to jump out and back, and it is more than 2x slower. The branches are predicted correctly in both cases; the difference comes from the jumps themselves: the front end can handle only a limited number of taken jumps per cycle, and with small p the default layout executes a `b.lt` per element to skip the write. This explanation is derived from the assembly and timing, not quoted from Apple microarchitecture documentation.

!!! pitfall "A hint only helps when you really know the distribution"
    Note 2 in [[dcl.attr.likelihood#2]] also warns that excessive use of these attributes can hurt performance. A wrong hint does not produce wrong results; it only slows down the common path. On our test machine the cost of a wrong guess (2x) is larger than the gain from a right one (1.7x). Save them for truly cold paths: error handling, assertion failures, one-time initialization.

## PGO: measured probabilities instead of guesses

**Profile-guided optimization** (PGO) first builds an instrumented version, runs it on representative input, records how many times each branch actually went each way, and feeds these counts back to the compiler. What it produces is exactly the kind of branch weight `[[likely]]` tries to express, except that it comes from measurement.

```bash
clang++ -std=c++2c -O2 -fprofile-instr-generate pgo.cpp -o pgo_gen
LLVM_PROFILE_FILE=p1.profraw ./pgo_gen 1          # train on p = 1% data
llvm-profdata merge -o p1.profdata p1.profraw
clang++ -std=c++2c -O2 -fprofile-instr-use=p1.profdata pgo.cpp -o pgo_use1
```

`pgo.cpp` is the filter function above plus a `main` that reads p from the command line. Training on p = 1% and on p = 99%, then measuring on both kinds of data:

| Build | Run on p = 1% | Run on p = 99% |
|---|---|---|
| Plain `-O2` | 0.36 ns/element | 0.31 |
| Trained on p = 1% | 0.21 | 0.62 |
| Trained on p = 99% | 0.36 | 0.31 |

The loop trained on p = 1% has the same layout as the hand-written `[[unlikely]]`, with the same gain; training on p = 99% gives the default. The benefit of PGO is that it needs no source changes, and its hints do not go stale as the code evolves. The cost is just as clear: when the training data does not match the real workload, it slows the program down like a misplaced `[[unlikely]]`. The full LTO and PGO workflow is in [[perf/lto-pgo]].

## Indirect branches: virtual function calls

A virtual call first loads the vptr from the object, then loads the function address from the vtable, and finally jumps to the address in a register (`blr` on arm64). The exact layout is in [[toolchain/object-layout-and-vtables]]. The target of this jump must be predicted too: a call site that always calls the same final overrider is **monomorphic**; one whose target varies among several is **polymorphic**.

```cpp title="virt.cpp" ok
#include "bench.h"
#include <new>
#include <random>

struct Shape {
  virtual ~Shape() = default;
  virtual unsigned long f(unsigned long x) const = 0;
};
struct A : Shape { unsigned long f(unsigned long x) const override { return x + 1; } };
struct B : Shape { unsigned long f(unsigned long x) const override { return x ^ 3; } };
struct C : Shape { unsigned long f(unsigned long x) const override { return x * 5; } };
struct D : Shape { unsigned long f(unsigned long x) const override { return x - 7; } };

[[gnu::noinline]] unsigned long run(Shape* const* v, long n) {
  unsigned long s = 0;
  for (long i = 0; i < n; ++i) s += v[i]->f(s);
  return s;
}

struct alignas(16) Slot { std::byte b[16]; };

int main() {
  const int n = 1 << 20;
  std::vector<Slot> pool(n);       // objects laid out contiguously: same access pattern for every order
  std::vector<Shape*> v(n);
  std::mt19937 rng(3);
  auto measure = [&](const char* name, int kinds, bool sorted) {
    std::vector<int> types(n);
    for (int& t : types) t = rng() % kinds;
    if (sorted) std::sort(types.begin(), types.end());
    for (int i = 0; i < n; ++i) {
      void* p = &pool[i];
      switch (types[i]) {
      case 0: v[i] = new (p) A; break;
      case 1: v[i] = new (p) B; break;
      case 2: v[i] = new (p) C; break;
      default: v[i] = new (p) D; break;
      }
    }
    double ns = bench_ns([&] { auto s = run(v.data(), n); escape(s); }, 31);
    std::printf("%-18s %.3f ns/call\n", name, ns / n);
  };   // the destructors have no side effects; we don't call them and simply reuse the storage
  measure("1 type", 1, false);
  measure("2 types, shuffled", 2, false);
  measure("4 types, sorted", 4, true);
  measure("4 types, shuffled", 4, false);
}
```

The objects all live in one contiguous block and are constructed in traversal order, so the memory access pattern is identical in every case and the only difference is the order of call targets. Results over five runs on our test machine:

| Types at the call site | ns/call |
|---|---|
| 1 | 0.92–0.97 |
| 4, sorted by type | 0.92–1.7 (mostly about 0.93) |
| 2, shuffled | 4.7–4.9 |
| 4, shuffled | 6.3–9.4 |

Once sorted by type, calls over four types are as fast as with a single type: within each run the target does not change, and the predictor learns quickly. After shuffling, about half the calls mispredict the target with two types, and about three quarters with four, adding roughly 4 ns and over 6 ns per call respectively.

So a virtual call is slow mainly not because of the two loads, but because the target at a polymorphic call site is hard to predict and because the indirect call gets in the way of inlining. Storing objects grouped by type (one container per type, or sorting by type first) is often a better deal than removing virtual functions. For when the compiler can turn a virtual call into a direct one (devirtualization), see [[perf/compiler-optimizations]].

## `switch`: jump tables and comparison chains

There are two common implementations of `switch`. With dense case values, the compiler builds a **jump table**, uses the condition value as an index to fetch the target address, and makes one indirect jump; with sparse or few case values, it compiles to a sequence of comparisons and conditional jumps, usually arranged as a binary search.

```cpp title="dispatch.cpp" godbolt flags="-std=c++2c -O2" ok
void f0(), f1(), f2(), f3(), f4(), f5(),
     f6(), f7(), f8(), f9(), f10(), f11();

void dispatch(unsigned op) {
  switch (op) {
  case 0: f0(); break;
  case 1: f1(); break;
  case 2: f2(); break;
  case 3: f3(); break;
  case 4: f4(); break;
  case 5: f5(); break;
  case 6: f6(); break;
  case 7: f7(); break;
  case 8: f8(); break;
  case 9: f9(); break;
  case 10: f10(); break;
  case 11: f11(); break;
  }
}
```

```asm
__Z8dispatchj:
  cmp   w0, #11
  b.hi  LBB0_14             ; op > 11: no case matches, return directly
  mov   w8, w0
  adrp  x9, LJTI0_0@PAGE
  add   x9, x9, LJTI0_0@PAGEOFF
  adr   x10, LBB0_2
  ldrb  w11, [x9, x8]       ; the table stores one-byte offsets
  add   x10, x10, x11, lsl #2
  br    x10                 ; indirect jump
```

Whether to use a jump table is decided by the target's cost model, not by a language rule. What we observed: for `switch` statements of this shape (case i calls a distinct function fi), Clang 23 on arm64 uses a jump table from 10 cases on and generates a comparison tree for 9 or fewer; with `--target=x86_64-linux-gnu` it already uses a jump table at 4 cases. Also, if each case just returns a value that varies linearly with the case value, the compiler replaces the `switch` with arithmetic, and neither structure appears.

The jump table's `br` is an indirect branch like a virtual call, and its cost depends on whether the target is predictable. Below is a small interpreter loop with 12 cases, each doing one integer operation:

| Instruction sequence | ns/instruction |
|---|---|
| Always the same op | 0.61 |
| Cycling 0, 1, …, 11 | 1.43 |
| Random | 7–17 (large fluctuations) |

For a regular sequence, even if the target changes every time, the predictor can learn it from history (the ops also have different latencies, so the difference between the first two rows is not all due to prediction). A random sequence can mispredict on every instruction and is an order of magnitude slower than the predictable cases.

### Removing the range check with `std::unreachable` {{c++23}}

The first two lines of the assembly above are a range check: when `op` is not between 0 and 11, the standard requires nothing to be executed ([[stmt.switch#5]]), so there must be a comparison before the table lookup. If you know for certain that `op` will not be out of range, you can tell the compiler:

```cpp
  case 11: f11(); break;
  default: std::unreachable();   // <utility>
  }
```

The precondition of `std::unreachable()` is "false is true", which can never be satisfied, so calling it is undefined behavior ([[utility.undefined#1]]). The compiler can therefore assume `default` is never reached; the `cmp` and `b.hi` instructions disappear and execution starts directly at the table lookup. On x86-64, `cmpl $11` and `ja` disappear likewise.

Adding it to the interpreter loop above makes no measurable difference for any of the three sequences: in the predictable cases 0.613 vs 0.613 and 1.430 vs 1.431 ns/instruction; in the random case both fluctuate over the same wide range. A deleted comparison and a branch that is always predicted correctly cost almost nothing to begin with.

!!! pitfall "What gets deleted is the check, not the bug"
    If `op` can actually be out of range, the version with `std::unreachable()` reads the jump table with an out-of-range index and jumps to an arbitrary address. The original code simply did nothing. Use it only when the value range is genuinely guaranteed elsewhere (for example, just validated, or a `switch` that covers every enumerator); in debug builds you can substitute an assertion first. More optimizations bought with UB are in [[topics/undefined-behavior]].

## `&&` vs `&`

`&&` specifies short-circuit evaluation: if the first operand is false, the second is not evaluated ([[expr.log.and#1]]). If the second operand reads memory, the compiler usually has to keep a branch, because it does not know whether reading that memory is safe when the first condition is false. `&` has no such restriction; both sides are always evaluated.

<div class="compare" markdown="1">

```cpp
for (long i = 0; i < n; ++i)
  if (a[i] > 0 && b[i] > 0) ++c;
```

```cpp
for (long i = 0; i < n; ++i)
  if ((a[i] > 0) & (b[i] > 0)) ++c;
```

</div>

The loop on the left has a `b.lt` per element and reads `b[i]` only after the condition holds. The one on the right is vectorized, and Clang also merges the two comparisons into one: `a > 0 && b > 0` is equivalent to `min(a, b) > 0`, so it generates `smin.4s` plus `cmgt.4s`. With each condition true with probability p:

| p | `&&` | `&` |
|---|---|---|
| 50% | 2.94 ns/element | 0.156 ns/element |
| 99% | 0.40–0.54 | 0.157 |

At p = 50% the difference comes mainly from mispredictions; at p = 99% the branch is nearly always predicted correctly, yet `&` is still more than 2.5x faster, because it lets the whole loop be vectorized.

This does not mean every `&&` should become `&`. When the second operand guards an access that could fail (`p && p->x`, `i < n && v[i]`), short-circuiting is part of correctness; when the second operand is expensive and the first is often false, short-circuiting is also faster. The cases worth switching are those where both sides are cheap and safe and the result is hard to predict, or where you want the loop to be vectorized.

## Summary

| Technique | What it changes | Observed on our test machine |
|---|---|---|
| Automatic if-conversion by the compiler | Simple conditional assignments become `csel`/`cmov` or vector masks | Sorted-array sum unaffected by sorting at `-O1` and above |
| Hand-written branchless code (conditional select, masks) | Control dependency becomes data dependency; both sides computed | Steady 0.31 ns/element when unpredictable; 5x slower when one side is expensive and rare |
| Lookup table | A chain of comparisons becomes one load | Character classification 15x faster; the table must fit in L1 |
| `[[likely]]`/`[[unlikely]]`, `__builtin_expect` | Branch weights, which affect block layout | No change when matching the default; right guess 1.7x faster, wrong guess 2x slower |
| PGO | Measured branch counts instead of guesses | Same effect as hand-written hints; equally slower with the wrong training data |
| Virtual calls grouped by type | Makes indirect-jump targets predictable | About 6–9 ns/call for 4 random types, about 0.93 after sorting |
| `std::unreachable()` as `default` | Removes the range check before the jump table | No measurable difference; UB if the value is out of range |
| `&` instead of `&&` | Both sides evaluated, vectorization allowed | 19x faster when unpredictable, still 2.5x faster when predictable |

## Questions

!!! question "1"
    Compiled with `-O2`, `sum_big` from the start of this page shows no difference between sorted and unsorted data. Without changing the function's semantics and without adding compiler options, what one-line change makes sorting matter again?

<details markdown="1">
<summary>Answer</summary>

Put an operation on the conditional path that the compiler cannot execute unconditionally, for example a call to an external function, a conditional memory write, or a read that might fail. The filter function on this page is the second kind: `out[k++] = x` can only execute when the condition holds, because introducing a write the abstract machine would not perform may create a data race ([[intro.races#19]]) and may go out of bounds. With such an operation in the function, the branch stays, and so does the difference between sorted and unsorted data: 0.31 vs 3.03 ns/element on our test machine.
</details>

!!! question "2"
    What is the difference between `if (x < 0) [[unlikely]] return handle(x);` and `if (__builtin_expect(x < 0, 0)) return handle(x);`? Which one is standard C++? May the compiler ignore them completely?

<details markdown="1">
<summary>Answer</summary>

The former is a standard C++20 attribute ([[dcl.attr.likelihood]]); the latter is a GCC and Clang extension. On Clang 23 both produce the same `branch_weights` metadata (1 to 2000) and the same assembly. The passage describing the optimization intent is a note with no normative force, so an implementation that ignores them entirely is still conforming; per the expectation in the note, such an implementation should make `__has_cpp_attribute(likely)` evaluate to 0.
</details>

!!! question "3"
    Given `enum class Op : unsigned char { /* 12 enumerators */ };` and a `switch` that lists all 12 enumerators with no `default`, what could adding `default: std::unreachable();` gain? When would it make the program go wrong?

<details markdown="1">
<summary>Answer</summary>

`Op` has a fixed underlying type, so its values can be any value of `unsigned char` ([[dcl.enum#8]]), and `static_cast<Op>(200)` is valid. So even with every enumerator listed, the compiler still has to handle the no-match case ([[stmt.switch#5]]: no statement is executed), and a range check is needed before the jump table. With `std::unreachable()`, the compiler may assume the condition value is always one of the cases and delete that check; in the comparison-tree form it may also save the last comparison. If some code constructs a value outside the enumerators via `static_cast` or deserialization and passes it in, what used to be a harmless no-op becomes undefined behavior ([[utility.undefined#1]]); in practice it may read the jump table with an out-of-range index and jump to an arbitrary address.
</details>
