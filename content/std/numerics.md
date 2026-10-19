---
title: 数值库
summary: 第 29 章导读：复数、随机数、valarray、<cmath>、数学常数、线性代数和 std::simd 各在哪里，本章常见的几类规则后果，以及本机 libc++ 的实现现状。
status: done
covers: numerics.general
related: numeric.requirements, cfenv, complex.numbers, rand, numarray, c.math, numbers, linalg, simd, numerics.c, numeric.ops, numeric.sat, basic.fundamental
tags: 导读, 标准库, 数值
updated: 2026-10-19
---

!!! tldr
    - 第 29 章收的是围绕数学对象的类型和函数：复数、随机数、`valarray`、`<cmath>`、数学常数、`<linalg>` 和 `<simd>`。`accumulate`、`reduce`、`gcd` 这些 `<numeric>` 算法在算法章，不在这里。
    - `<complex>` 的函数结果在数学上无定义或无法表示时是 UB；`<cmath>` 改用 C 的错误报告机制，不是 UB。
    - 随机数分布的算法由实现定义，同一个种子在不同标准库上可以得到不同的序列；引擎的算法则是完全规定的。
    - `<random>` 用模板形参的名字表达要求：名为 `IntType`、`RealType` 等的形参只接受规定范围内的类型，否则程序非良构。
    - 本机 libc++ 还没有 `<linalg>`、`<simd>`、`philox_engine`，`<cmath>` 的 `constexpr` 扩展也未实现。

## 本章地图（[numerics.general]）

¶1–¶2 本章描述用于**半数值**（seminumerical）运算的组件，即围绕数学对象本身的类型和函数，不是对序列的通用算法。表 125 列出各子条款：

| 子条款 | 内容 | 头文件 | 本站笔记 |
|---|---|---|---|
| [numeric.requirements] | `complex`、`valarray` 对元素类型的要求 | — | [[numeric.requirements]] |
| [cfenv] | 浮点环境：异常标志、舍入模式 | `<cfenv>` | [[cfenv]] |
| [complex.numbers] | `complex<T>`、超越函数、字面量后缀 | `<complex>` | [[complex.numbers]] |
| [rand] | 引擎、引擎适配器、分布、`random_device`、`seed_seq` | `<random>` | [[rand]] |
| [numarray] | `valarray` 与四种切片代理 | `<valarray>` | [[numarray]] |
| [c.math] | `<cmath>` 函数、整数 `abs`、`lerp`、数学特殊函数 | `<cmath>`、`<cstdlib>` | [[c.math]] |
| [numbers] | `std::numbers::pi` 等数学常数 | `<numbers>` | [[numbers]] |
| [linalg] | 基于 `mdspan` 的 BLAS 风格算法 {{c++26}} | `<linalg>` | [[linalg]] |
| [simd] | 数据并行类型 `basic_vec`、`basic_mask` {{c++26}} | `<simd>` | [[simd]] |

表后还有一个子条款 [[numerics.c]]，即 C23 的 `<stdckdint.h>`：带溢出检查的 `ckd_add`、`ckd_sub`、`ckd_mul`。

¶2 的导言仍然提到 generalized numeric algorithms，但 `accumulate`、`reduce`、`inclusive_scan`、`gcd`、`midpoint`、饱和算术等早已移到算法章的 [[numeric.ops]] 和 [[numeric.sat]]。查找它们要去那里。

还有一些设施常被误以为在本章：

| 设施 | 实际位置 |
|---|---|
| `numeric_limits`、`<cfloat>`、`<climits>` | 语言支持库 [[support.limits]] |
| `<stdfloat>` 的 `float16_t` 等别名 | [[support.arith.types]]，类型本身在 [[basic.extended.fp]] |
| `<bit>`（`popcount`、`bit_cast` 等） | 工具库 [[bit]] |
| `to_chars`、`from_chars` | 文本处理 [[charconv]] |
| `shuffle`、`sample`、`ranges::generate_random` | 算法章 [[alg.random.shuffle]]、[[alg.random.sample]]、[[alg.rand.generate]] |
| `mdspan` 本身 | 容器章 [[views.multidim]] |

## 本章常见的几类规则后果

数值库大量借用数学记号，并且常把数学上的失败直接规定为某种后果。下面几种模式在各页反复出现。

### 结果无定义或无法表示

```cpp
auto z = std::log(std::complex<double>(0, 0));
// <complex>：ln 0 在数学上无定义，按 ¶3 是 UB
double d = std::log(0.0);
// <cmath>：极点错误，返回 -HUGE_VAL
// 并按 math_errhandling 报告，不是 UB
```

[[complex.numbers]] 的 [complex.numbers.general] ¶3 规定，复数函数的结果在数学上无定义，或者超出其类型的可表示范围时，行为未定义。这比核心语言还严。按 [[expr.pre#4]]，内建算术表达式只有在数学结果既不可表示、也不是该类型拥有的无穷或 NaN 时才是 UB，所以对 IEEE 浮点类型，内建运算里只剩除以零是 UB。`<complex>` 没有这层豁免。本机 libc++ 实际上按 C 附录 G 的约定让上例返回 `(-inf, 0)`，但标准不保证。

`<cmath>` 沿用 C 的 `math_errhandling` 机制报告定义域错误和值域错误（见 [[c.math]]），不是 UB。但整数的 `std::abs(INT_MIN)` 仍是 UB，因为 C 对 `abs` 就是这样规定的。

### 算法由实现定义

```cpp
std::mt19937 eng(42);
std::uniform_int_distribution<int> d(1, 6);
int x = d(eng);   // 不同标准库可能给出不同的 x
```

[[rand.dist]] 的 [rand.dist.general] ¶3 规定，每个分布如何从均匀的随机比特生成目标分布，由实现定义。所以同一个引擎、同一个种子，`uniform_int_distribution` 在 libc++、libstdc++、MSVC STL 上的结果可以不同。

引擎则相反：`mt19937` 的算法完全规定，[[rand.predef]] 甚至规定了默认构造的引擎第 10000 次调用必须得到的值。需要跨平台复现随机序列时，只能依赖引擎的输出，自己写从比特到分布的变换。`default_random_engine` 是哪个引擎、`random_device` 的熵从哪里来，也都由实现定义。

### 模板形参的名字携带要求

[rand.req.genl] ¶1 规定，`<random>` 中名为 `RealType`、`IntType`、`UIntType`、`URBG`、`Sseq`、`Engine` 的模板形参自动带有相应的要求。前三者的实参不在允许的类型集合里时，程序非良构。例如 `IntType` 只接受标准整数类型、宽度在 `char` 与 `long long` 之间的扩展整数类型，以及实现自行列入的其他整数类型。`char` 和 `bool` 不是标准整数类型，只有实现把它们列入时才可以使用；本机 libc++ 用 `static_assert` 拒绝 `uniform_int_distribution<char>`。

[[linalg]] 用同样的手法（[linalg.algs.reqs]）：名为 `Triangle`、`DiagonalStorage`、`ExecutionPolicy` 的形参各有约束。读这些函数签名时，形参名本身就是要求的一部分。

### Mandates、Constraints 与 Preconditions

与其他库章一样，*Mandates* 不满足时程序非良构，必须诊断；*Constraints* 不满足时，这个重载退出重载决议，没有任何诊断；*Preconditions* 不满足时是 UB（[[structure.specifications]]）。本章有几处值得留意：

- 实例化 `std::numbers::pi_v<int>` 这样的主模板，程序非良构（[math.constants] ¶3）；
- 实例化 `complex<int>`，效果是未指明的：不保证能用，也不要求诊断（[[numeric.requirements]]）；
- `valarray::operator[]` 的越界检查是加固前置条件 {{c++26}}，加固实现下越界会被检查并终止（[[g:hardened-precondition]]）；
- `<linalg>` 用 *Mandates* 检查静态 extent 是否兼容，用 *Preconditions* 约束动态 extent。

## 实现现状（本机 Clang 23 + libc++）

| 设施 | 状态 |
|---|---|
| `<complex>` 基本功能、字面量 | 已实现；C++26 的结构化绑定支持也已实现 |
| `<complex>`、`<cmath>` 的 C++23/26 `constexpr` 扩展 | 未实现：`std::floor` 等在常量表达式中被拒绝 |
| `<random>` 的经典引擎与分布 | 已实现；`default_random_engine` 是 `minstd_rand` |
| `philox_engine`、`ranges::generate_random` {{c++26}} | 未实现 |
| `generate_canonical` 的新规格 | 未采用，仍是旧算法，可能返回 1.0（见 [[rand.util]]） |
| `<valarray>` | 已实现，使用表达式模板 |
| 数学特殊函数 | 只有 `hermite`，没有 `riemann_zeta`、`cyl_bessel_j` 等 |
| `<linalg>`、`<simd>` {{c++26}} | 没有这两个头文件 |
| `<stdckdint.h>` | 由 Clang 自带的 C 头文件提供，`ckd_*` 是宏，不是标准要求的函数模板 |
