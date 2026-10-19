---
title: 自动向量化
summary: 编译器什么时候会把循环改写成 SIMD 指令：循环次数可数、迭代之间没有依赖、能证明数组不重叠；浮点求和为什么必须由程序员允许重排；怎样读 Clang 的向量化报告；restrict、pragma、执行策略 unseq 和 std::simd 各自向编译器交代了什么。
status: draft
order: 35
group: 编译器
since: c++17
papers: P0024R2, P1001R2, P1928R15
related: intro.abstract, intro.execution, intro.races, expr.pre, basic.lval, numerics.defns, reduce, algorithms.parallel, execpol, simd, topics/arithmetic, topics/type-punning, topics/undefined-behavior, perf/measuring, perf/reading-assembly, perf/compiler-optimizations, perf/memory-hierarchy, perf/branches
tags: 性能, SIMD, 向量化, 浮点, 别名, restrict, Clang
updated: 2026-10-19
---

!!! tldr
    - 自动向量化把一个循环改写成每条指令处理 4 个或 8 个元素的形式。本机 L1 缓存内的 `saxpy` 因此快了约 3.6 倍；数据大到要从内存读取时只快约 2 倍。
    - 编译器只在三个条件下动手：进入循环时就能算出迭代次数，迭代之间没有依赖，能证明读写的数组不重叠。最后一条证明不了时，它会在循环前插入一次运行时重叠检查。
    - 浮点加法不满足结合律，按标准 `s += x[i]` 必须逐个累加，编译器不能自己把它拆成几路部分和。要拆分，得由程序员给出许可：`std::reduce`、执行策略 `unseq`、`#pragma clang loop vectorize(enable)` 或 `-ffast-math`。整数求和不需要许可。
    - 用 `-Rpass=loop-vectorize`、`-Rpass-missed=loop-vectorize`、`-Rpass-analysis=loop-vectorize` 让 Clang 报告每个循环向量化了没有、为什么没有。报告说已经向量化，也要看汇编，本机的浮点求和就是例子。
    - `__restrict` 不是标准 C++。在 macOS 上包含系统头文件之后，它被宏定义成空，什么作用都没有；要用就写 `__restrict__`。

## 同一个循环，快 3.6 倍

```cpp run title="saxpy.cpp" flags="-std=c++2c -O2" ok
#include <cstddef>
void saxpy(float a, const float* x, float* y, std::size_t n) {
  for (std::size_t i = 0; i < n; ++i) y[i] = a * x[i] + y[i];
}
```

**SIMD**（single instruction, multiple data）指令一次对一个向量寄存器里的几个元素做同样的运算，每个元素占的位置叫一个**通道**（lane）。arm64 的 NEON 寄存器是 128 位，装 4 个 `float`；x86-64 的 SSE 也是 128 位，AVX2 是 256 位，装 8 个。编译器把普通的标量循环改写成使用这类指令的循环，叫做**自动向量化**（auto-vectorization）。

在本机（Apple M2 Pro，Homebrew Clang 23，arm64）用 `clang++ -std=c++2c -O2 -S` 编译，对比关掉向量化（`-fno-vectorize -fno-slp-vectorize`）的结果，两个循环体如下：

<div class="compare" markdown="1">

```text
; 关掉向量化：每次 2 个元素
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
; -O2 默认：每次 16 个元素
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

左边的 `s` 寄存器是单个 `float`，`fmadd` 是一次乘加。右边的 `q` 寄存器是 128 位，`fmla.4s` 一次做 4 个乘加。一条指令处理的元素个数叫**向量化宽度**（vectorization width，VF），这里是 4。右边的循环体还把 4 组向量操作排在一起，这叫**交错**（interleave），交错数是 4，所以每次迭代处理 16 个元素。剩下不足 16 个的尾部由后面的一个 4 宽循环和一个标量循环处理，读汇编的方法见 [[perf/reading-assembly|读汇编]]。

两个版本都用了乘加融合（FMA）指令，把 `a * x[i] + y[i]` 只舍入一次。Clang 默认 `-ffp-contract=on`，允许在同一个表达式里这样融合，结果可能和分别舍入不同，浮点语义见 [[topics/arithmetic|整数与浮点运算的陷阱]]。

### 测量

计时用本节共用的 [[perf/measuring#harness|bench.hpp]]：每个样本连续调用约 1 ms，取 31 个样本的中位数，`do_not_optimize` 和 `clobber_memory` 是两行空的内联汇编，让优化器不能删除被测的计算。下面把两个版本放在同一个程序里交替测量，标量版用 pragma 关掉向量化（pragma 后文再讲）：

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
  bench::compare(                                   // A：标量，B：向量
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

| n | 两个数组共 | 标量 | 向量 | 比值 |
|---|---|---|---|---|
| 4096 | 32 KiB，在 L1 里 | 约 880 ns | 约 242 ns | 约 3.6 倍 |
| 16777216 | 128 MiB，在内存里 | 约 4.7–5.3 ms | 约 2.6 ms | 约 2 倍 |

这是本机的观察，几次运行之间比值稳定，绝对时间在机器繁忙时会波动；换一种 CPU 或编译器，数字会不同。数据放得下 L1 时，瓶颈是指令吞吐，向量化把指令数降到约四分之一。数据要从内存读取时，瓶颈变成内存带宽，向量化省下的指令只能换来一部分收益，见 [[perf/memory-hierarchy|内存层次]]。

### x86-64 上的同一个循环

本机没有 x86 CPU，下面只看代码生成，没有测量。用 `--target=x86_64-linux-gnu -S` 交叉编译（本机没有 Linux 的头文件，所以把 `#include <cstddef>` 换成了一行 `namespace std { using size_t = decltype(sizeof 0); }`）：

| 选项 | 循环体的主要指令 | 宽度 × 交错 |
|---|---|---|
| 默认（x86-64 基线只有 SSE2） | `movups`、`mulps`、`addps` | 4 × 2 |
| `-mavx2` | `vmulps`、`vaddps`，`ymm` 寄存器 | 8 × 4 |
| `-march=x86-64-v3` | `vfmadd213ps`，`ymm` 寄存器 | 8 × 4 |

`-mavx2` 只打开 AVX2，不包括 FMA 指令集，所以乘和加仍是两条指令；`-march=x86-64-v3` 同时包含 AVX2 和 FMA。向量化的结果取决于目标指令集，编译出的程序也只能在支持这些指令的 CPU 上运行。

## 读向量化报告

Clang 的循环向量化器可以报告它对每个循环的决定：

| 选项 | 报告什么 |
|---|---|
| `-Rpass=loop-vectorize` | 向量化成功的循环，以及宽度和交错数 |
| `-Rpass-missed=loop-vectorize` | 没有向量化的循环 |
| `-Rpass-analysis=loop-vectorize` | 没有向量化的具体原因 |

对 `saxpy.cpp`，本机输出：

```text
saxpy.cpp:3:3: remark: vectorized loop (vectorization width: 4, interleaved count: 4) [-Rpass=loop-vectorize]
```

报告不是完整的清单。下一节的 `my_strlen` 循环没有向量化，但三个选项都没有输出任何内容。更重要的是，报告说向量化了，不等于循环变快了：本机的浮点求和循环得到同样的 `vectorized loop` 报告，速度却和标量版本一样，原因在后面的浮点一节。确认效果要看汇编，再测时间。

## 向量化需要什么

### 循环开始前就知道迭代次数

```cpp run title="countable.cpp" flags="-std=c++2c -O2" ok
#include <cstddef>
std::size_t my_strlen(const char* p) {
  std::size_t n = 0;
  while (p[n] != '\0') ++n;      // 次数取决于读到的数据
  return n;
}
std::size_t find_first(const int* x, std::size_t n, int v) {
  for (std::size_t i = 0; i < n; ++i)
    if (x[i] == v) return i;     // 有上界，但可能提前退出
  return n;
}
```

向量化后的循环一次处理 VF 个元素，所以编译器要在进入循环前算出总次数，才能安排主循环和尾部。`my_strlen` 的次数取决于读到的数据，这样的循环叫不可数循环，本机 Clang 没有向量化它，也没有输出报告。另一个问题是，一次读 16 个字节可能读到字符串末尾之后、跨进一个不可访问的页；手写的向量化 `strlen` 靠对齐读取保证不跨页，编译器一般不做这种推理。

`find_first` 有上界 `n`，但中途可能返回。LLVM 近年开始支持这类提前退出的循环，本机得到的报告是 `the cost-model indicates that vectorization is not beneficial`，也就是能做但认为不划算。

### 迭代之间没有依赖

```cpp run title="prefix.cpp" flags="-std=c++2c -O2" ok
#include <cstddef>
void prefix(float* a, std::size_t n) {
  for (std::size_t i = 1; i < n; ++i) a[i] += a[i - 1];
}
```

第 `i` 次迭代要读第 `i - 1` 次写进去的值，这叫**循环携带依赖**（loop-carried dependence）。4 个通道同时计算时，后 3 个通道读到的都是旧值，结果就错了。本机报告：

```text
prefix.cpp:3:44: remark: loop not vectorized: unsafe dependent memory operations in loop. Use #pragma clang loop distribute(enable) to allow loop distribution to attempt to isolate the offending operations into a separate loop
Backward loop carried data dependence. Memory location is the same as accessed at prefix.cpp:3:47 [-Rpass-analysis=loop-vectorize]
prefix.cpp:3:3: remark: loop not vectorized [-Rpass-missed=loop-vectorize]
```

求和里的 `s += x[i]` 也是循环携带依赖，只是依赖在一个变量上而不是在内存里。这种形式叫**归约**（reduction），编译器能识别它，用几个部分和代替一个累加器，但前提是可以重新组合加法的顺序，后文专门讲。

循环体里调用一个看不到定义的函数，也会挡住向量化，报告是 `call instruction cannot be vectorized`。编译器不知道这个函数做了什么，更不可能把它改成一次处理 4 个参数的版本。能内联的函数没有这个问题，见 [[perf/compiler-optimizations|编译器优化]]。

### 能证明数组不重叠

`saxpy` 的 `x` 和 `y` 是两个指针，调用方完全可以让它们指向同一个数组里相邻的位置。比如 `saxpy(a, y, y + 1, n)` 时，`y[i]` 就是下一次迭代要读的 `x[i+1]`，按顺序执行和 4 个一组执行的结果不同。

编译器在编译 `saxpy` 时看不到调用方，所以它生成两个版本，并在入口处检查。这是上面 `saxpy` 汇编的开头：

```text
	cmp	x2, #4                ; n < 4：直接走标量循环
	b.lo	LBB0_3
	lsl	x8, x2, #2            ; x8 = n * 4，数组的字节数
	add	x9, x0, x8            ; x9 = x + n
	add	x8, x1, x8            ; x8 = y + n
	cmp	x0, x8                ; x < y + n
	ccmp	x1, x9, #2, lo        ; 并且 y < x + n ?
	b.hs	LBB0_7                ; 两段不重叠：去向量循环
LBB0_3:                               ; 重叠：标量循环
```

这叫**运行时别名检查**（runtime alias check）：两个区间 `[x, x+n)` 和 `[y, y+n)` 不相交就走向量版本，否则走标量版本。检查只在循环前做一次，代价可以忽略。代价出现在检查不通过的时候，例如原地更新 `saxpy(a, y, y, n)`：

| 调用 | 本机中位数 |
|---|---|
| `saxpy(1.0f, x, y, 4096)`，不重叠 | 约 241 ns |
| `saxpy(1.0f, y, y, 4096)`，原地 | 约 1265 ns |

原地更新其实可以安全地向量化，因为每次迭代只读写同一个位置。但检查只看区间是否相交，不区分这种情况，于是落到了标量循环。

### 类型不同的指针：严格别名

```cpp run title="tbaa.cpp" flags="-std=c++2c -O2" ok
#include <cstddef>
void to_float(float* y, const int* x, std::size_t n) {
  for (std::size_t i = 0; i < n; ++i) y[i] = float(x[i]);
}
```

本机 `-O2` 的汇编里没有任何重叠检查，循环直接用 `scvtf.4s` 每次转换 4 个元素。加上 `-fno-strict-aliasing` 之后，入口处多出 `sub x8, x1, x0` 和 `cmn x8, #64` 一组比较，也就是一次运行时检查。

原因在 [[basic.lval#11]]：通过一个类型的 glvalue 访问另一种类型的对象，除了有符号与无符号的对应类型、`char`、`unsigned char`、`std::byte` 这几个例外，都是未定义行为。`y[i]` 是 `float` 左值，`x[i]` 是 `int` 左值。如果它们访问的是同一块内存，程序已经有 UB，所以编译器可以假设两者不重叠。这条规则叫**严格别名**（strict aliasing），它带来的其他后果见 [[topics/type-punning|类型双关]]。两个指针类型相同（都是 `float*`）时，这条规则帮不上忙。

## restrict：C 有，C++ 没有

C99 给出了另一种办法：用 `restrict` 修饰指针，程序员承诺在这个指针的作用域里，通过它访问的对象不会再通过别的途径访问。违反承诺是未定义行为。C 标准库的 `memcpy` 就这样声明两个形参，所以要求两块内存不重叠，见 [[library.c]]。

C++ 没有 `restrict`。GCC 和 Clang 在 C++ 中提供扩展 `__restrict` 和 `__restrict__`，语义借用 C 的规则；MSVC 提供 `__restrict`。它们都不可移植，标准对它们没有任何规定。

```cpp run title="restrict.cpp" flags="-std=c++2c -O2" ok
#include <cstddef>
void saxpy_r(float a, const float* __restrict__ x,
             float* __restrict__ y, std::size_t n) {
  for (std::size_t i = 0; i < n; ++i) y[i] = a * x[i] + y[i];
}
```

本机这个函数的汇编没有 `cmp x0, x8` / `ccmp` 那组检查，直接根据 `n` 选择向量循环；向量循环本身和 `saxpy` 逐条相同。测量上，两者在不重叠的输入上都是约 242 ns，因为检查本来就只有几条指令。`__restrict__` 的价值在于去掉标量回退路径、缩小代码，以及帮助那些检查不出来、只能放弃的情况。如果调用方传入重叠的数组，就违反了承诺，编译器不会再检查，结果是错的。

!!! pitfall "macOS 上的 `__restrict` 什么都不做"
    在本机先写同样的函数，但用 `__restrict` 拼写并包含 `<vector>` 或 `<cstdio>`，生成的 LLVM IR 里形参没有 `noalias` 属性，汇编里的重叠检查也还在。原因是 macOS SDK 的 `<sys/cdefs.h>` 在 `__STDC_VERSION__ < 199901` 时执行 `#define __restrict`（定义为空），而 C++ 编译时 `__STDC_VERSION__` 没有定义，条件为真。只包含 `<cstddef>` 时不会引入这个头文件，`__restrict` 又有效，所以很难察觉。用 `clang++ -E` 看预处理结果就能发现。`__restrict__` 没有被定义成宏，不受影响。

Clang 还有一个只作用于单个循环的写法：`#pragma clang loop vectorize(assume_safety)` 告诉向量化器这个循环里的内存访问之间没有依赖。本机给 `saxpy` 加上它之后，重叠检查同样消失。它和 `__restrict__` 一样是程序员的承诺，承诺不成立时结果是错的。

## 浮点归约：需要许可才能重排

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

两个函数只差一个类型。本机 `-O2` 下，`sumi` 的循环体是 4 条 `add.4s`，用 4 个向量寄存器各自累加，最后再合起来；`sumf` 的循环体却是从向量寄存器里把元素一个个取出来，再用 16 条标量 `fadd s0, s0, …` 依次加到同一个 `s0` 上：

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
	...                         ; 共 16 条 fadd，都写 s0
```

读入用了向量指令，加法仍是一条接一条，每一条都要等上一条的结果。这就是上一节说的情况：报告是 `vectorized loop (vectorization width: 4, interleaved count: 4)`，速度却没有变化。LLVM 把这叫做按顺序的归约。同样的代码用 `--target=x86_64-linux-gnu -mavx2` 交叉编译，Clang 干脆不向量化，报告说：

```text
sum.cpp:4:41: remark: loop not vectorized: cannot prove it is safe to reorder floating-point operations; allow reordering by specifying '#pragma clang loop vectorize(enable)' before the loop or by providing the compiler option '-ffast-math' [-Rpass-analysis=loop-vectorize]
```

### 为什么不能重排

向量化的求和要用 4 个部分和：`s0` 累加第 0、4、8… 个元素，`s1` 累加第 1、5、9… 个，最后相加。这等于把 `((x0 + x1) + x2) + x3 …` 改成另一种加法顺序。

标准规定了原来的顺序。每次迭代的 `s += x[i]` 是一个完整表达式，它的副作用先于下一个完整表达式（[[intro.execution#9]]）。[[expr.pre]] 的注 6（¶5）说明，实现只有在运算真正满足结合律、交换律时才能按数学规则重新组合。浮点加法每一步都要舍入，不满足结合律。[[expr.pre#6]] 允许浮点中间结果用更高的精度表示（`FLT_EVAL_METHOD` 报告这一点，本机是 0），但那只放宽了精度，没有放宽顺序。

as-if 规则（[[g:as-if-rule|as-if rule]]，[[intro.abstract#6]]）只允许不改变[[g:observable-behavior|可观察行为]]的变换。重排加法会改变结果：本机对 `x[i] = 1.0f / (i + 1)`（4096 项）求和，按顺序累加得到 `8.89510822`，16 个部分和的版本得到 `8.89510441`。程序打印这个结果，结果就成了可观察行为的一部分，所以编译器不能自行重排。顺便一提，用 `double` 精确累加这 4096 个 `float` 得到约 `8.89510396`，部分和的版本反而更接近，重排不一定让结果更差，只是不同。

整数没有这个问题。无符号整数的运算按模 2<sup>N</sup> 进行，加法满足结合律；有符号整数溢出是 UB（[[expr.pre#4]]），编译器可以假设没有溢出，而在不溢出时加法同样满足结合律。[[expr.pre]] 注 6 后半段也说，在溢出不产生异常、结果可逆的机器上，整数表达式可以重新组合。所以 `sumi` 不需要任何许可。

### 怎样给出许可

| 写法 | 范围 | 是否标准 |
|---|---|---|
| `-ffast-math` | 整个翻译单元 | 编译器选项 |
| `-fassociative-math -fno-signed-zeros` | 整个翻译单元 | 编译器选项 |
| `#pragma clang fp reassociate(on)` | 所在的复合语句 | Clang 扩展 |
| `#pragma clang loop vectorize(enable)` | 下一个循环 | Clang 扩展 |
| `#pragma omp simd reduction(+ : s)` 加 `-fopenmp-simd` | 下一个循环 | OpenMP |
| `std::reduce(first, last, init)` | 这次调用 | 标准，C++17 |
| `std::reduce(std::execution::unseq, …)` | 这次调用 | 标准，C++20 |

`-ffast-math` 打开的远不止重排。本机 `clang++ -### -ffast-math` 显示它还传入了 `-menable-no-nans`、`-menable-no-infs`、`-freciprocal-math`、`-ffp-contract=fast` 等选项，前两个让编译器假设不存在 NaN 和无穷大，`std::isnan(x)` 这样的检查可能被优化成常量 `false`。它作用于整个翻译单元，包括被包含的头文件。只想放开某一个循环时，用范围更小的写法。

单独加 `-fassociative-math` 在本机不起作用：`-###` 的输出里没有 `-mreassociate`，`sumf` 照旧按顺序累加。同时加上 `-fno-signed-zeros` 才生效。

`std::reduce` 的返回值规定为 *GENERALIZED_SUM*（[[reduce#7]]）。按 [[numerics.defns#2]]，它可以把元素任意排列、任意加括号，这正是向量化需要的许可。这个许可对不带执行策略的重载也成立，[[reduce#9]] 的注专门指出浮点加法会因此得到不确定的结果。不过标准只是允许，实现不一定利用：本机 libc++ 的 `std::reduce(first, last, init)` 是一个普通循环，结果和速度都和手写循环一样。

### 本机测量

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

| 版本（4096 个元素） | 默认选项 | `-ffast-math` | 结果 |
|---|---|---|---|
| 手写循环 | 约 3.6–3.8 µs | 约 211 ns | `8.89510822` / `8.89510441` |
| `vectorize(enable)` | 约 213 ns | 约 212 ns | `8.89510441` |
| `std::reduce` | 约 3.6 µs | 约 212 ns | `8.89510822` / `8.89510441` |
| `std::reduce(unseq, …)` | 约 213 ns | 约 212 ns | `8.89510441` |
| `int` 手写循环 | 约 148 ns | 约 148 ns | — |

按顺序的浮点求和每纳秒大约只加 1.1 个元素。M2 上一条浮点加法的延迟是几个周期，每一条都要等上一条，速度由这条依赖链决定。得到许可之后，同一个循环快约 17 倍。

### 交错数

`vectorize(enable)` 版本快的另一个原因是交错。`#pragma clang loop interleave_count(N)` 指定交错数，也就是用几个向量寄存器各自累加：

```cpp title="interleave_bench.cpp（节选）" ok
#include <cstddef>
[[gnu::noinline]] float ic8(const float* x, std::size_t n) {
  float s = 0;
#pragma clang loop vectorize(enable) interleave_count(8)
  for (std::size_t i = 0; i < n; ++i) s += x[i];
  return s;
}
```

| `interleave_count` | 本机中位数（4096 个 `float`） |
|---|---|
| 1 | 约 886 ns |
| 2 | 约 414 ns |
| 4（Clang 默认选的值） | 约 213 ns |
| 8 | 约 116 ns |

交错数为 1 时，所有加法都排在一个向量累加器上，又回到了一条依赖链，只是每一环加 4 个元素。累加器越多，能同时在流水线里执行的加法越多。在本机这个数据量下，8 个累加器比编译器默认的 4 个又快了约 1.8 倍；数据不在 L1 里时，瓶颈会转移到内存，这个差距不一定还在。交错数和宽度的最优值与具体 CPU 有关，这正是编译器默认交给成本模型决定的原因。

## 条件：掩码与选择

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

向量化的循环里没有逐个元素的分支。`relu` 被改写成比较和选择：`fcmgt.4s` 为 4 个通道各生成一个全 1 或全 0 的**掩码**（mask），再用 `and.16b` 把不满足条件的通道清零，每次迭代处理 16 个元素，没有一条跳转。x86 `-mavx2` 上直接用了 `vmaxps`。

`store_if` 不同：条件不成立时，原程序根本不写 `y[i]`。编译器不能把它改成无条件写回旧值，因为另一个线程可能正在写这个位置，凭空多出一次写入会制造原程序里没有的数据竞争。[[intro.races]] 的注 19（¶19）说，引入抽象机不会执行的写入一般是不允许的。x86 AVX2 有带掩码的存储指令，本机 `-mavx2` 交叉编译得到 `vcmpltps` 加 `vmaskmovps`。NEON 没有这样的指令，Clang 报告已经向量化，实际生成的是每个通道一次 `fcmp`、一次条件跳转、一次单通道存储 `st1.s { v3 }[1]`。

| 本机中位数（4096 个 `float`） | 全部为正 | 正负随机 |
|---|---|---|
| `relu`：选择 | 约 200 ns | 约 240 ns |
| `store_if`：条件存储 | 约 1.3 µs | 约 1.65 µs |
| `y[i] = x[i] > 0 ? x[i] : y[i]` | 约 1.5 µs | 约 2.7 µs |

最后一行显式写回旧值，按语义每次都写，似乎可以变成无条件的选择加存储。本机 Clang 却没有向量化它，报告 `the cost-model indicates that vectorization is not beneficial`，生成的标量循环里只在条件成立时才读写 `y[i]`。这个结果说明改写之后要再看一次报告和汇编，不能假设编译器会按你的意图生成代码。正负随机时变慢，是因为留下的分支无法预测，见 [[perf/branches|分支]]。

## gather：按下标读取

```cpp run title="gather.cpp" flags="-std=c++2c -O2" ok
#include <cstddef>
int sum_idx(const int* a, const int* idx, std::size_t n) {
  int s = 0;
  for (std::size_t i = 0; i < n; ++i) s += a[idx[i]];
  return s;
}
```

`a[idx[i]]` 的 4 个元素不在相邻位置，要用**gather**（按一组下标分别读取，装进一个向量）。NEON 没有 gather 指令，本机 Clang 报告 `the cost-model indicates that vectorization is not beneficial`，只做了 4 路交错的标量循环。

x86 的情况取决于 `-march`。本机交叉编译，`-mavx2`、`-march=haswell`、`-march=x86-64-v3` 都没有使用 AVX2 的 `vpgatherdd`，而是逐个 `vpinsrd` 把元素插进向量；`-march=skylake`、`-march=icelake-server`、`-march=znver4` 使用了 `vpgatherdd`。gather 指令在不同的微架构上速度差别很大，编译器的成本模型按目标 CPU 决定是否使用。

| 本机中位数（4096 个 `int`，都在 L1 里） | |
|---|---|
| `a[i]` | 约 148 ns |
| `a[idx[i]]`，`idx` 顺序 | 约 666 ns |
| `a[idx[i]]`，`idx` 打乱 | 约 666 ns |

下标顺序时，`a[idx[i]]` 读的其实也是连续的元素，但编译器在编译期看不出来，照样按 gather 处理，慢 4.5 倍。数据都在 L1 里，打乱下标并没有更慢；数据大到要从内存读取时，打乱的访问还会遇到缓存未命中。能把间接访问改成连续访问（例如先按下标重排数据），通常比依赖 gather 更有效。

## 对齐

早期的 SIMD 指令要求地址按向量宽度对齐，未对齐的读取要么出错，要么慢很多，因此流传着向量化前先对齐数组的建议。前面的汇编里，x86 用的是不要求对齐的 `movups`、`vmovups`，arm64 的 `ldp q` 也不要求 16 字节对齐。编译器没有为对齐生成额外的代码。

本机把 `x`、`y` 两个数组放在 64 字节对齐的缓冲区里，起点错开 0 到 32 个字节，测 `saxpy`：

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
  // 64 字节对齐的两块缓冲区，多留 64 字节用来错开起点
  auto* bx = static_cast<char*>(std::aligned_alloc(64, bytes));
  auto* by = static_cast<char*>(std::aligned_alloc(64, bytes));
  for (int off : {0, 4, 8, 16, 32}) {
    float* x = new (bx + off) float[n];   // 在偏移处创建 float 数组
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

| 起点偏移（字节） | n = 4096，在 L1 里 | n = 16777216，在内存里 |
|---|---|---|
| 0 | 约 242 ns | 约 2.2–2.5 ms |
| 4 | 约 329 ns | 约 2.2–2.5 ms |
| 8 | 约 329 ns | 约 2.2–2.5 ms |
| 16 | 约 242 ns | 约 2.2–3.1 ms |
| 32 | 约 242 ns | 约 2.2–3.1 ms |

数据在 L1 里时，起点不是 16 的倍数的数组慢了约 36%：一次 16 字节的读取有时会跨过 64 字节的缓存行边界，要访问两条缓存行。16 字节对齐就够了，再对齐到 32 或 64 字节没有变化。数据在内存里时，各偏移的最小值都在 2.2 ms 左右，中位数的差别在这台繁忙机器的噪声范围内，没有可见的影响。

`new` 返回的内存在本机至少 16 字节对齐，`std::vector<float>` 的数据一般已经满足。真正会出现错位的是从一个大缓冲区中间切出来的子数组。是否值得处理，要按自己的数据规模测一次。

## 在代码里写明意图

### Clang 的循环 pragma

`#pragma clang loop` 写在一个循环之前，只影响这个循环：

| 写法 | 作用 |
|---|---|
| `vectorize(enable)` / `vectorize(disable)` | 要求或禁止向量化；`enable` 同时允许重排浮点归约 |
| `vectorize_width(N)` | 指定宽度 |
| `interleave_count(N)` / `interleave(disable)` | 指定交错数或禁止交错 |
| `vectorize(assume_safety)` | 假设内存访问之间没有依赖，不做重叠检查 |

`vectorize(enable)` 不会让编译器生成错误的代码。给 `prefix` 加上它，本机仍然得到 `unsafe dependent memory operations` 的分析报告，外加一个警告：

```text
prefix.cpp:4:3: warning: loop not vectorized: the optimizer was unable to perform the requested transformation; the transformation might be disabled or specified as part of an unsupported transformation ordering [-Wpass-failed=transform-warning]
```

所以它适合用来检查一个热循环是否真的向量化：做不到时编译器会警告。`assume_safety` 不同，它把安全性交给程序员。

### 执行策略 `unseq`

C++17 把 Parallelism TS 的并行算法并入标准（[[P0024R2]]），C++20 又加入了只向量化、不开线程的 `std::execution::unseq`（[[P1001R2]]）。策略的含义见 [[execpol]]。按 [[algorithms.parallel.exec#5]]，用 `unseq` 调用算法时，对元素调用的函数可以在调用线程上无序、交错地执行，这正是 SIMD 需要的许可。代价是这些函数里不能调用[[g:vectorization-unsafe|向量化不安全]]的标准库函数（例如加锁），否则行为未定义。

!!! impl "libc++（LLVM 23）"
    - 执行策略是实验性功能，要加 `-fexperimental-library`；不加时 `std::execution::unseq` 不存在，加了以后 `__cpp_lib_execution`、`__cpp_lib_parallel_algorithm` 仍然没有定义。完整的实现现状见 [[algorithms.parallel]] 页尾。
    - `unseq` 版本的 `reduce` 并没有手写 SIMD 代码，而是在普通循环前放了 `#pragma clang loop vectorize(enable) interleave(enable)`（定义在 `__configuration/pstl.h` 的 `_PSTL_PRAGMA_SIMD_REDUCTION`）。它在本机得到的结果和速度都与上面手写的 `vectorize(enable)` 循环相同。

`par_unseq` 在此之上再允许多线程执行。多线程能否带来收益取决于数据量和线程调度，要单独测量。

### `std::simd` {{c++26}}

C++26 加入了 `<simd>`（[[simd]]，[[P1928R15]]），让程序员直接写出数据并行的类型，不依赖编译器去识别循环。`std::simd::vec<float>` 是一个按目标平台选定宽度的 `float` 向量，算术运算逐个通道进行，`std::simd::reduce` 的结果同样定义为 *GENERALIZED_SUM*（[[simd.reductions#3]]），重排是写在接口里的。

本机 Clang 23 + libc++ 没有 `<simd>` 头文件，下面按当前草案编写，没有经过编译，所以不带判定标记：

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
  acc += sd::partial_load<V>(x + i, n - i);  // 尾部，缺的通道补 0
  return sd::reduce(acc);
}
```

`unchecked_load` 要求范围里至少有 `w` 个元素；`partial_load` 只读实际存在的元素，其余通道取 `T()`（[[simd.loadstore#9]]）。这种写法把向量宽度、尾部处理和求和顺序都写在了代码里，代价是代码比一个 `for` 循环长。和自动向量化相比是否值得，要等实现出来以后在具体的循环上比较。

## 思考题

!!! question "1"
    把 `sumf` 的累加器改成 `double s = 0;`，循环里写 `s += x[i];`，最后 `return float(s);`。编译器能在没有任何许可的情况下向量化它吗？

<details markdown="1">
<summary>答案</summary>

不能。精度更高并不改变问题：`double` 的加法也要舍入，同样不满足结合律，重排仍可能改变结果，as-if 规则不允许（[[intro.abstract#6]]）。[[expr.pre#6]] 允许实现用更高的精度计算浮点表达式，但只能保持原来的运算顺序。用 `double` 累加能减小误差，向量化仍需要许可。
</details>

!!! question "2"
    `void scale(float* y, const float* x, std::size_t n, const float* k)` 的循环体是 `y[i] = x[i] * *k;`。为什么编译器可能要在每次迭代都重新读 `*k`？向量化的版本怎样处理？

<details markdown="1">
<summary>答案</summary>

`k` 和 `y` 类型相同，`k` 可能指向 `y` 中的某个元素，写 `y[i]` 之后 `*k` 的值可能已经变了，严格别名（[[basic.lval#11]]）帮不上忙。标量版本因此要在每次迭代重新读取。向量化版本会把 `k` 也纳入运行时检查：确认 `*k` 不在 `y` 的范围内时，才把 `*k` 读一次、广播到所有通道。本机 `-O2` 的汇编正是这样：入口处有两组 `cmp`/`ccmp`，标量回退循环每次迭代都执行 `ldr s1, [x3]`，向量循环之前只读一次。写成 `float kv = *k;` 先拷到局部变量，就把只读一次的意图写进了代码，不再需要检查 `k`。
</details>

!!! question "3"
    用 `std::reduce(v.begin(), v.end(), 0.0f)` 代替 `std::accumulate`，在本机 libc++ 上为什么没有变快？标准是否允许它变快？

<details markdown="1">
<summary>答案</summary>

允许。`reduce` 的返回值是 *GENERALIZED_SUM*（[[reduce#7]]），可以任意重排和加括号（[[numerics.defns#2]]），实现完全可以用部分和。但本机 libc++ 的无策略版本是一个普通循环，编译器看不到标准给的许可，只能按顺序累加。要在本机得到向量化，需要 `std::execution::unseq`（libc++ 用 pragma 把许可传给编译器）或者前文表格里的其他写法。
</details>

## 小结

| 问题 | 结论 | 依据 |
|---|---|---|
| 向量化能带来多少 | 本机 L1 内 `saxpy` 约 3.6 倍，内存中约 2 倍 | 本机测量 |
| 需要什么条件 | 可数的循环、无循环携带依赖、能证明不重叠 | 编译器报告 |
| 指针类型相同时 | 插入运行时重叠检查，重叠时走标量循环 | 本机汇编 |
| 指针类型不同时 | 按严格别名假设不重叠，不检查 | [[basic.lval#11]] |
| `restrict` | C 有，C++ 只有编译器扩展；macOS 上 `__restrict` 会被宏清空 | C99，`<sys/cdefs.h>` |
| 浮点求和 | 不能自行重排，需要许可 | [[intro.execution#9]]、[[expr.pre]] 注 6、[[intro.abstract#6]] |
| 标准的许可 | `std::reduce` 的 *GENERALIZED_SUM*，`unseq` 策略 | [[reduce#7]]、[[algorithms.parallel.exec#5]] |
| 整数求和 | 不需要许可 | [[expr.pre#4]] |
| 条件存储 | 不能变成无条件存储；NEON 上逐通道分支 | [[intro.races]] 注 19 |
| 对齐 | 本机 L1 内 16 字节对齐有影响，更大的对齐和内存中的数据没有可见影响 | 本机测量 |
