---
title: Moving work to compile time
summary: When lookup tables, constant parameters and branches are worth computing at compile time, where the results end up in the binary, how much run time they save, and how much more you pay in compile time and size.
tags: performance, constexpr, consteval, constinit, lookup tables, templates, compile time, embed
updated: 2026-10-19
group: Code
---

!!! tldr
    - A lookup table built at compile time lives in the read-only data segment: it costs nothing at startup and needs no check on first use. But the lookup itself is as fast as with a table built at run time; what you save is only the one-time cost of building it.
    - `constexpr` only means a function *can* be evaluated at compile time; to guarantee it, catch the result in a `constexpr` variable, `constinit`, or a `consteval` function. Small computations without `constexpr` are usually folded by the optimizer anyway.
    - Turning a small run-time integer into a template argument (dispatching to a few instances with a `switch` if needed) made 3×3 to 8×8 matrix multiplication 2.4 to 3 times faster on our test machine; `if constexpr` can remove a flag test from a loop entirely.
    - The cost is compile time and size: Clang 23's constant evaluator takes 2.5 seconds of CPU time to build a 65536-entry sine table, while the same data written as literals takes 0.09 seconds; every additional template instance adds another copy to the code segment.
    - Embed large binary data with `#embed`: on our test machine, compiling 1 MiB of data dropped from 0.51 seconds to 0.04 seconds.

All numbers on this page are measured on our test machine: Apple M2 Pro, macOS, Homebrew Clang 23.1.3 + libc++, arm64, `-O2`. The machine was heavily loaded during measurement, so we only compare results measured one after another in the same program, and compile times are the minimum user CPU time of 5 runs. Another machine or compiler will change the numbers; what matters is the method and the direction of the conclusions. How to set up measurements is in [[perf/measuring]]; how to read assembly is in [[perf/reading-assembly]].

## A small measuring tool

All run-time numbers below come from the same timing function:

```cpp title="bench.h" ok
#include <algorithm>
#include <chrono>
#include <vector>

// make the compiler believe v is read, so the computation cannot be deleted
template <class T> inline void escape(T const& v) {
  asm volatile("" : : "r"(&v) : "memory");
}

template <class F>
double bench_ns(F f, int reps = 51, long iters = 1000) {
  for (long i = 0; i < iters; ++i) f();     // warm-up
  std::vector<double> t;
  for (int r = 0; r < reps; ++r) {
    auto t0 = std::chrono::steady_clock::now();
    for (long i = 0; i < iters; ++i) f();
    auto t1 = std::chrono::steady_clock::now();
    t.push_back(std::chrono::duration<double, std::nano>(
                    t1 - t0).count() / iters);
  }
  std::nth_element(t.begin(), t.begin() + reps / 2, t.end());
  return t[reps / 2];                        // median
}
```

`escape` is an empty inline asm statement. It declares that it reads the address of `v` and may read or write any memory (`"memory"`); the optimizer cannot see through it, so it has to actually compute `v`. Without it, nobody uses the measured result, and under the as-if rule ([[g:as-if-rule]], [[intro.abstract#1]]) the whole computation could be deleted. Each measurement is repeated for 51 rounds and the median taken; each round is short, and rounds interrupted by the system scheduler fall at the extremes without affecting the median.

## Three ways to build a lookup table

A table-driven CRC-32 needs a 256-entry table. The table can be built at three points in time:

```cpp
using Table = std::array<std::uint32_t, 256>;

constexpr Table make_table() {
  Table t{};
  for (std::uint32_t i = 0; i < 256; ++i) {
    std::uint32_t c = i;
    for (int k = 0; k < 8; ++k)
      c = (c & 1) ? 0xEDB88320u ^ (c >> 1) : c >> 1;
    t[i] = c;
  }
  return t;
}
Table make_table_rt();    // same body, without constexpr

constexpr Table kTable = make_table();   // A: at compile time
Table gTable = make_table_rt();          // B: at startup
const Table& lazy_table() {              // C: on first use
  static const Table t = make_table_rt();
  return t;
}
```

A is a `constexpr` variable; its initializer must be a constant expression and is [[g:manifestly-constant-evaluated]] ([[expr.const.defns#1]]), so the compiler has no choice but to compute the table during translation. B is **dynamic initialization**: the initializer is not a constant expression and is executed by startup code before `main` ([[basic.start.static#2]]). C is a block-scope static variable, initialized the first time execution reaches its declaration; after that, every call first has to check whether it has been initialized.

### Where the table ends up

After compiling, `nm -m` shows which segment each of the three variables is in:

```text
$ clang++ -std=c++2c -O2 crc.cpp -o crc && nm -m crc | grep -i table
0000000100007660 (__TEXT,__const) non-external __ZL6kTable
000000010000c080 (__DATA,__common) external _gTable
000000010000c480 (__DATA,__bss) non-external __ZZ10lazy_tablevE1t
000000010000c880 (__DATA,__bss) non-external __ZGVZ10lazy_tablevE1t
```

`kTable` is in `__TEXT,__const`, that is, read-only data: the 1024 bytes are written as-is into the executable and mapped straight into memory at load time. `gTable` and C's table are in zero-initialized writable segments, take no space in the file, and are filled in by code at run time. The last line, `__ZGV…`, is C's guard variable, recording whether the table has been built. On Linux, the ELF equivalents are `.rodata` and `.bss`; compiling with `--target=x86_64-linux-gnu`, `llvm-objdump -t` shows `kTable` in `.rodata`.

B's table-building code lives in the function `__GLOBAL__sub_I_crc.cpp`, whose address is registered in the `__mod_init_func` section; `dyld` calls these one by one before `main`. Every call to C first executes these two instructions:

```text
ldaprb  w8, [x8]          ; load the guard variable (acquire semantics)
tbz     w8, #0, LBB4_2    ; if not initialized, jump to build the table
```

### The measured difference

| Measurement (our test machine, `-O2`, median) | A compile time | B startup | C first use |
|---|---|---|---|
| CRC-32, 16 bytes | 12.2 ns | 12.2 ns | 12.7 ns |
| CRC-32, 4096 bytes | 9.96 µs | 9.96 µs | 9.97 µs |
| 4096-entry sine table, single lookup | 0.92 ns | 0.92 ns | 0.92 ns |
| 4096-entry sine table, building once (`std::sin`) | 0 | 16.5 µs | 16.5 µs |

Lookup speed does not differ. The three tables have the same contents, and once warm they are all in L1 cache; C's extra guard check is a load that is almost always cached plus a branch that is always predicted correctly, visible only as about 0.5 ns on very short inputs like 16 bytes.

What you save is building the table. 4096 calls to `std::sin` take 16.5 µs on our test machine; B pays this once per process start, C once on the first call. For a long-running service this is negligible; for a command-line tool started tens of thousands of times a day, or a program with dozens of such tables, it is part of startup time.

!!! note "The optimizer replaced the CRC loop"
    The build time of the CRC table itself could not be measured: at `-O2`, Clang 23 recognized the inner loop that computes CRC bit by bit and replaced it with a lookup into a 256-entry table the compiler generated itself (`l_.crctable` in the assembly, produced by the LoopIdiomRecognize pass). So B's startup code is reduced to a vectorized lookup loop, and building the table once takes less than 0.1 µs. This is a Clang implementation detail and may not happen with another compiler or version. The sine table uses `std::sin`, which the optimizer cannot replace, so its build time is real.

### Another benefit of read-only tables

Pages in the read-only data segment are mapped in from the executable on demand by the operating system, and multiple processes running the same program share the same physical memory. B's and C's tables are private pages written by each process. In addition, A has no initialization-order problem: constant initialization happens before any dynamic initialization ([[basic.start.static#2]]), so when another global variable's initializer reads `kTable`, it already has its final value. The order of dynamic initialization like B's across translation units is unspecified, which is the [[g:static-initialization-order-fiasco]].

The cost is a bigger file: a `constexpr` table of 4096 `double`s grows `__TEXT,__const` by 32 KB, while B's table of the same size only occupies the zero-initialized segment and takes no file space.

## The optimizer folds even without constexpr

`constexpr` is not a prerequisite for compile-time computation. None of the functions below are `constexpr`:

```cpp ok
int sum_to(int n) {
  int s = 0;
  for (int i = 0; i < n; ++i) s += i * i;
  return s;
}
int use() { return sum_to(100); }

double poly(double x) { return 1 + x * (2 + x * 3); }
double use2() { return poly(0.5); }
```

At `-O2`, the assembly for `use` is two `mov`s that assemble the constant 328350, and `use2` is a single `fmov d0, #2.75`; the function calls and the loop are gone. The same holds on x86-64 (`movl $328350, %eax`). The optimizer inlined the functions and propagated the constants through the intermediate representation. The as-if rule allows this; see [[perf/compiler-optimizations]].

The standard also explicitly allows an implementation to turn dynamic initialization into static initialization, as long as neither the result nor any side effect can tell the difference ([[basic.start.static#3]]). Whether it actually happens is up to the compiler, though. The `gTable` in the previous section could perfectly well be computed at compile time, yet Clang 23 still generated startup code. The optimizer's folding works within a budget, and unrolling, inlining and propagation stop beyond a certain size. Small expressions can be left to the optimizer; for large tables and results you need guaranteed, lock them in with language rules.

## Guaranteeing compile time with consteval and constinit

A `constexpr` function only means it can be called in a constant expression; when the call occurs in a run-time context, the compiler may generate an ordinary call. This is discussed fully in the [[topics/compile-time-programming]] topic. What matters for performance is unoptimized debug builds:

```cpp ok
#include <cstdint>
#include <string_view>

constexpr std::uint32_t crc_of(std::string_view s) {
  std::uint32_t c = 0xFFFFFFFFu;
  for (unsigned char ch : s) {
    c ^= ch;
    for (int k = 0; k < 8; ++k)
      c = (c & 1) ? 0xEDB88320u ^ (c >> 1) : c >> 1;
  }
  return ~c;
}
consteval std::uint32_t crc_ce(std::string_view s) {
  return crc_of(s);
}

bool is_len_a(std::uint32_t h) { return h == crc_of("Content-Length"); }
bool is_len_b(std::uint32_t h) { return h == crc_ce("Content-Length"); }
```

At `-O2` both functions compare against the constant `0xd87452f2`. At `-O0`, `is_len_a` really constructs a `string_view` and calls `crc_of`, computing all 14 characters bit by bit; `is_len_b` is still just one comparison. Every call to a `consteval` function is an **immediate invocation**, which is manifestly constant-evaluated regardless of the optimization level.

For variables with static storage duration there is one more option:

```cpp
constexpr Table t1 = make_table();     // read-only, compile time
constinit Table t2 = make_table();     // writable, compile time
```

`constinit` requires the variable to have static initialization, otherwise the program is ill-formed ([[dcl.constinit#2]]), but does not make the variable `const`. On our test machine `t2` lands in the writable `__DATA,__data` segment (`.data` on ELF); the file likewise stores the 1 KB initial value, and no code runs at startup. If `make_table()` is replaced with the non-`constexpr` `make_table_rt()`, both the `constexpr` and the `constinit` versions fail to compile instead of quietly degrading to building the table at startup.

### Non-static constexpr local variables

```cpp
void consume(const Table&);   // another translation unit

void by_ref() {
  constexpr Table t = make_table();
  consume(t);
}
void by_ref_static() {
  static constexpr Table t = make_table();
  consume(t);
}
```

The two functions differ only by a `static`. In the assembly for `by_ref`, every call allocates 1024 bytes on the stack, `memcpy`s the table from read-only constants, and passes out the stack address. On our test machine `by_ref` takes 13.5 ns per call, `by_ref_static` 0.92 ns.

The reason is that `t` in `by_ref` is an object with automatic storage duration, and each call creates a new object. If `consume` called `by_ref` recursively, two `t`s would be alive at the same time, and by [[intro.object#10]] they must have different addresses, so the compiler cannot make both point to the same read-only data. When the address does not escape (for example, only `t[i]` is used to read values), Clang can see that nobody observes the address, reads the read-only constant directly, and makes no copy. Write `constexpr` local tables whose reference or pointer is passed out as `static constexpr`.

## Bringing constants into hot code: template arguments

Compile time can do more than compute data. Turn a small run-time integer into a template argument, and the compiler can generate code for that specific value.

```cpp
void mul_rt(const float* a, const float* b, float* c, int n) {
  for (int i = 0; i < n; ++i)
    for (int j = 0; j < n; ++j) {
      float s = 0;
      for (int k = 0; k < n; ++k)
        s += a[i * n + k] * b[k * n + j];
      c[i * n + j] = s;
    }
}

template <int N>
void mul_ct(const float* a, const float* b, float* c) {
  /* the same triple loop, with n replaced by N */
}

void mul_dispatch(const float* a, const float* b, float* c, int n) {
  switch (n) {
    case 2: return mul_ct<2>(a, b, c);
    case 3: return mul_ct<3>(a, b, c);
    case 4: return mul_ct<4>(a, b, c);
    case 8: return mul_ct<8>(a, b, c);
    default: return mul_rt(a, b, c, n);
  }
}
```

`n` is known only at run time (in the test it is derived from `argc`); `mul_dispatch` uses a `switch` to dispatch common sizes to dedicated instances and sends the rest to the general version.

| `n` (our test machine, `-O2`) | `mul_rt` | `mul_dispatch` | Ratio |
|---|---|---|---|
| 3 | 15.0 ns | 5.0 ns | 3.0 |
| 4 | 30.7 ns | 10.4 ns | 2.9 |
| 8 | 201 ns | 83.3 ns | 2.4 |

The assembly explains the difference. The innermost loop of `mul_rt` has three useful instructions (two loads, one `fmadd`) plus three loop-control instructions, and each dot product is one chain of dependent `fmadd`s. In `mul_ct<4>` the `j` and `k` loops are fully unrolled, all addresses are a register plus an immediate offset, and the `fmadd` chains of the four dot products are independent in straight-line code, so out-of-order execution can advance them simultaneously. `mul_ct<8>` is the same, with 64 unrolled `fmadd`s inside.

The `switch` itself costs one comparison and a jump. This kind of dispatch only pays off when the distribution of `n` is concentrated on a few values; each `case` instantiates its own copy of the code, see the section on size below.

### if constexpr removes the test from the loop

```cpp ok
#include <cstddef>

void scale_rt(float* p, std::size_t n, float k, bool clamp) {
  for (std::size_t i = 0; i < n; ++i) {
    float v = p[i] * k;
    if (clamp) v = v > 1.0f ? 1.0f : v;
    p[i] = v;
  }
}
template <bool Clamp>
void scale_ct(float* p, std::size_t n, float k) {
  for (std::size_t i = 0; i < n; ++i) {
    float v = p[i] * k;
    if constexpr (Clamp) v = v > 1.0f ? 1.0f : v;
    p[i] = v;
  }
}
```

The condition of `if constexpr` is a constant, and the branch not taken is a **discarded statement** ([[stmt.if#2]]) that is not instantiated when the template is instantiated. `scale_ct<false>` contains no comparison at all.

`clamp` in `scale_rt` is invariant in the loop, so the compiler could split the loop into two copies (called loop unswitching). Clang 23 does not do this at `-O2`; instead it turns the test into a bitwise select that stays inside the vectorized loop body, recomputing the mask on every iteration. Processing 4096 `float`s:

| Our test machine, `-O2` | `scale_rt` | `scale_ct` |
|---|---|---|
| No clamping | 487 ns | 197 ns |
| Clamping | 487 ns | 264 ns |

Gains like this depend on whether the compiler is willing to split the loop itself, and the conclusion may differ with another compiler or optimization level. The way to confirm is always to read the assembly.

## Fixed size: std::array vs std::vector

When the size is known at compile time, `std::array<float, 16>` is a 64-byte object placed directly on the stack; `std::vector<float>(16)` is three pointers in 24 bytes, with the elements on the heap.

```cpp
float sum(const float* p, int n);   // not inlined

float with_vector(const float* in) {
  std::vector<float> t(16);
  for (int i = 0; i < 16; ++i) t[i] = in[i] * in[i];
  return sum(t.data(), 16);
}
float with_array(const float* in) {
  std::array<float, 16> t;
  for (int i = 0; i < 16; ++i) t[i] = in[i] * in[i];
  return sum(t.data(), 16);
}
```

On our test machine `with_vector` takes 26.7 ns per call and `with_array` 3.37 ns; nearly all of the difference is `operator new` and `operator delete` (`bl __Znwm` and `bl __ZdlPvm` in the assembly).

But if `sum` is replaced by summing directly inside the function, the buffer's address no longer escapes and both versions take 2.33 ns: Clang deleted the heap allocation. The standard allows implementations to omit calls to replaceable global allocation functions ([[expr.new#14]]), but when it happens is up to the compiler and cannot be relied on. The cost of allocation is in [[perf/allocation]]; choosing containers is in [[perf/choosing-containers]].

## Cost one: compile time

The overhead of compile-time computation moves from run time to every compilation. Clang's constant evaluator is an interpreter, much slower than compiled machine code. Increasing the number of entries in the sine table:

```cpp
// sintab.h: sin via Taylor series, 19 iterations per entry
constexpr double csin(double x);
template <std::size_t N>
constexpr std::array<double, N> make_sin_table();

// big.cpp
constexpr auto kSin = make_sin_table<TABN>();
```

At N = 16384, compilation fails with default settings:

```text
error: constexpr variable 'kSin' must be initialized by a constant expression
note: constexpr evaluation hit maximum step limit; possible infinite loop?
```

When constant evaluation exceeds an implementation limit, the expression is not a core constant expression ([[expr.const.core#2.7]]), so the initialization of the `constexpr` variable is ill-formed. The standard's annex [[implimits]] only gives recommended minimums, such as 1 048 576 full-expressions evaluated within one core constant expression; the annex is not normative, and the actual limits are up to the implementation. On our test machine, Clang 23's default limit behaves exactly like an explicit `-fconstexpr-steps=1048576`, and a simple accumulation loop counts roughly one step per iteration. Raise the limit with `-fconstexpr-steps=<n>` (Clang); GCC's corresponding options are `-fconstexpr-ops-limit` and `-fconstexpr-loop-limit`.

Compile times with the limit lifted (user CPU seconds, minimum of 5; an empty file including only `<array>` takes 0.06 seconds):

| Table entries | Constant evaluator | Experimental bytecode evaluator | Written as literals |
|---|---|---|---|
| 1024 | 0.09 | 0.08 | |
| 4096 | 0.19 | 0.15 | |
| 16384 | 0.65 | 0.47 | |
| 65536 | 2.54 | 1.69 | 0.09 |

The last column is a version where Python precomputes 65536 `double`s that are `#include`d into an initializer list; it compiles in only 0.09 seconds, and the resulting object file is the same size as the `constexpr` version (512 KB of data in both). The middle column is Clang's `-fexperimental-new-constant-interpreter`, which produces object files byte-for-byte identical to the default evaluator, but the option is still experimental.

To see where the time goes, use `-ftime-trace`. It writes a JSON file in Chrome trace format next to the output file, which you can drop into `chrome://tracing` or Perfetto, or just read the summary events whose names start with `Total`. The summary at N = 16384 on our test machine:

```text
1190.5 ms  Total ExecuteCompiler
1183.6 ms  Total Frontend
1121.2 ms  Total EvaluateAsInitializer      ← kSin's initializer
   3.9 ms  Total Backend
```

Nearly all the time goes to the front end evaluating `kSin`'s initializer; optimization and code generation take only a few milliseconds.

This cost is paid in every translation unit that includes the code. When the table's definition sits in a header included by dozens of `.cpp` files, it is better to move the table into one `.cpp` and only declare it in the header. For tables of more than a few thousand entries with nontrivial computation, generating literals with a build script is usually the better deal.

## Cost two: code size

Every template argument generates a separate function. Using `std::integer_sequence` to instantiate `mul_ct<1>` through `mul_ct<MAXN>` at once and put them in a table of function pointers:

```cpp
using Fn = void (*)(const float*, const float*, float*);
template <int... I>
constexpr std::array<Fn, sizeof...(I)>
make_dispatch(std::integer_sequence<int, I...>) {
  return {&mul_ct<I + 1>...};
}
constexpr auto kDispatch =
    make_dispatch(std::make_integer_sequence<int, MAXN>{});
```

Reading the object file's `__text` section with `size -m`:

| `MAXN` | `__text` (bytes) | Compile (user seconds) |
|---|---|---|
| 1 | 260 | 0.07 |
| 8 | 2 940 | 0.09 |
| 16 | 5 136 | 0.12 |
| 32 | 10 756 | 0.15 |
| 64 | 13 828 | 0.19 |

Instances for small sizes are fully unrolled and run to several hundred bytes each; at larger sizes the compiler stops fully unrolling and each instance adds less. Size by itself does not equal slowness, but if a hot path calls many instances in turn, they crowd each other out of the instruction cache. Generate instances only for values that are genuinely common, and leave the rest to the general version.

## Large data: #embed {{c++26}}

To turn a binary file into an array, the traditional approach is to generate a huge initializer list with a tool like `xxd -i`. C++26's `#embed` ([[P1967R14]]) lets the preprocessor read the file directly:

<div class="compare" markdown="1">

```cpp
constexpr unsigned char kBlob[] = {
#include "blob.inc"   // 0x3a, 0x91, …
};
```

```cpp
constexpr unsigned char kBlob[] = {
#embed "blob.bin"
};
```

</div>

Per the standard, `#embed` is replaced by a comma-separated list of integer literals of type `int` ([[cpp.embed#11]]), semantically the same as the left side. The difference is in the implementation: the compiler does not actually have to generate and parse millions of tokens. For 1 MiB of random data on our test machine, the text file on the left is 6 MB and compiles in 0.51 seconds of user time with 250 MB peak memory; the right side takes 0.04 seconds and 124 MB. The two object files are the same size.

Clang 23 accepts `#embed` under `-std=c++2c`, but with `-pedantic` it warns `#embed is a Clang extension`, and it does not define the feature-test macro `__cpp_pp_embed` (which the current draft specifies as `202606L`). In other words, at the time of writing Clang 23 provides it as an extension and has not yet fully implemented it as a C++26 feature.

## How to choose

| Situation | Approach |
|---|---|
| Small table, simple algorithm | `constexpr` variable (namespace scope, or a `static constexpr` local) |
| Must be computed at compile time but modified afterwards | `constinit` |
| A function must never run at run time | `consteval` |
| Very large table or heavy computation | Generate literals at build time, or embed a data file with `#embed` |
| Depends on information only available at run time (CPU features, configuration) | Build the table at startup, or on first use |
| A parameter of a hot function takes only a few values | Template argument + `switch` dispatch, keeping a general version |
| A loop-invariant boolean switch inside a loop | Template parameter + `if constexpr`; first check the assembly to confirm the compiler didn't split the loop itself |

## Common pitfalls

!!! pitfall "Assuming a constexpr function always runs at compile time"
    In `int x = f(42);`, even if `f` is `constexpr`, this call may run at run time, especially in an `-O0` debug build. To guarantee compile time, catch the result in a `constexpr` or `constinit` variable, or declare the function `consteval`.

!!! pitfall "Assuming compile-time tables are faster to look up"
    Once a table is in cache, reading any copy is equally fast. Building a table at compile time saves the one-time build, the first-use check and the initialization-order problem, not the time of each lookup.

!!! pitfall "Large constexpr local arrays"
    A non-`static` `constexpr` local array, once its address is passed out, is copied onto the stack on every call. Add `static`.

!!! pitfall "constexpr tables in widely included headers"
    Every translation unit evaluates them again. 0.6 seconds in one `.cpp`, multiplied by dozens of translation units, is a big chunk of build time.

## Questions

!!! question "1. Read-only or writable"
    What is the difference between `constinit const Table t = make_table();` and `constexpr Table t = make_table();`? At namespace scope, which one can be used in constant expressions?

<details markdown="1">
<summary>Answer</summary>

Both require constant initialization, both variables are `const`, and both go into read-only data. The difference is whether they can be used in constant expressions: a `constexpr` variable is always usable in constant expressions; a `constinit const` variable is a `const` object of class type rather than of integral or enumeration type, and is not `constexpr`, so it cannot be used in constant expressions; for example, `static_assert(t[0] == 0)` is rejected. There is no difference in run-time performance. See [[dcl.constinit]] and [[expr.const.init]].
</details>

!!! question "2. Was the startup table optimized away?"
    `Table gTable = make_table_rt();` is dynamic initialization. Could the compiler generate no startup code at all and write the table straight into the data segment? Does the standard allow it?

<details markdown="1">
<summary>Answer</summary>

Yes, it is allowed. [[basic.start.static#3]] allows an implementation to perform dynamic initialization as static initialization, as long as this does not change the values other static variables see before initialization and the resulting value is the same as with dynamic initialization. Clang 23 does not do this at `-O2` on our test machine and still generates `__GLOBAL__sub_I_crc.cpp`. So this is only permitted, not guaranteed; if you need a guarantee, use `constexpr` or `constinit`.
</details>

!!! question "3. Why not instantiate every size?"
    `mul_dispatch` generates dedicated versions only for 2, 3, 4 and 8. Since `mul_ct<N>` is nearly 3 times faster, why not instantiate all of 1 to 64?

<details markdown="1">
<summary>Answer</summary>

Every instance is separate code. On our test machine, instantiating 1 to 64 grows the code segment from 260 bytes to about 13.8 KB, and compile time increases too. More importantly, if the run-time size distribution is spread out, many instances get called in turn and push each other out of the instruction cache, and dispatch may change from one comparison into a table lookup plus an indirect call. Generate instances only for sizes that measurement shows to be genuinely frequent.
</details>

<details class="fine" markdown="1"><summary>Measurement commands</summary>

Run-time measurement: `clang++ -std=c++2c -O2 -Wall -Wextra -pedantic x.cpp -o x && ./x`; each program is run 5 times and the median of the best run is taken. Compile time: the `user` column of `/usr/bin/time -p clang++ -std=c++2c -O2 -c x.cpp -o /dev/null`, minimum of 5. Segments and symbols: `nm -m`, `size -m` (macOS), `llvm-objdump -t` (ELF). Assembly: `clang++ -std=c++2c -O2 -S`, with `--target=x86_64-linux-gnu` for x86-64. Tracing constant evaluation: `-ftime-trace`.

`std::sin` is already a `constexpr` function in the current draft (C++26, [[P1383R2]]), but the libc++ on our test machine does not implement it yet, so the sine table uses a hand-written Taylor series `csin`; its maximum difference from `std::sin` over the 4096 sample points is 7×10⁻¹⁶.
</details>
