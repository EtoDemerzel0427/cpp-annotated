---
title: 数值库
summary: 第 29 章导读——复数、随机数、valarray、<cmath>、数学常数、线性代数、std::simd 与 C 的检查整数运算各在哪里；本章反复出现的几类法律后果（结果超出可表示范围即 UB、算法由实现定义、按模板形参名施加的要求）；以及本机 libc++ 的实现现状
status: done
covers: numerics.general
related: numeric.requirements, cfenv, complex.numbers, rand, numarray, c.math, numbers, linalg, simd, numerics.c, numeric.ops, numeric.sat, basic.fundamental
tags: 导读, 标准库, 数值
updated: 2026-10-18
---

第 29 章 [numerics] 收的是**半数值**（seminumerical）组件：它们不是"算法"那种对序列的通用操作，而是围绕数学对象本身的类型和函数——复数、随机数、数值数组、初等与特殊函数、数学常数、BLAS 风格的线性代数和 SIMD 向量类型。

读这一章，核心语言里最常用到的背景是：

- 算术类型的分类与浮点类型的**转换秩**（[[basic.fundamental]]、[[conv.rank]]）——`<cmath>`、`<complex>`、`std::simd` 的重载集合和隐式/显式转换规则都直接用"浮点转换秩"来写；
- 表达式求值中"结果不在可表示范围内即 UB"的规则（[[expr.pre#4]]）——本章多处把同样的规则搬到库函数上；
- 常量求值里 C 库函数的特殊规定（[[library.c#3]]，[[g:non-constant-library-call]]）——它决定了 `constexpr` 的 `<cmath>` 什么时候不是常量表达式。

## 本章地图（[numerics.general]）

¶1 只说本章描述"半数值运算"组件。¶2 的表 125 列出各子条款与头文件：

| 子条款 | 内容 | 头文件 | 本站笔记 |
|---|---|---|---|
| [numeric.requirements] | `complex`、`valarray` 对元素类型的要求 | — | [[numeric.requirements]] |
| [cfenv] | 浮点环境：异常标志、舍入模式 | `<cfenv>` | [[cfenv]] |
| [complex.numbers] | `complex<T>`、超越函数、字面量后缀、C++26 元组接口 | `<complex>` | [[complex.numbers]] |
| [rand] | 引擎、引擎适配器、分布、`random_device`、`seed_seq` | `<random>` | [[rand]]、[[rand.req]]、[[rand.eng]]、[[rand.device]]、[[rand.util]]、[[rand.dist]] |
| [numarray] | `valarray` 与四种切片代理 | `<valarray>` | [[numarray]] |
| [c.math] | `<cmath>` 函数、整数 `abs`、三参 `hypot`、`lerp`、数学特殊函数 | `<cmath>`、`<cstdlib>` | [[c.math]] |
| [numbers] | `std::numbers::pi` 等数学常数 | `<numbers>` | [[numbers]] |
| [linalg] | 基于 `mdspan` 的 BLAS 1/2/3 算法 {{c++26}} | `<linalg>` | [[linalg]] |
| [simd] | 数据并行类型 `basic_vec`/`basic_mask` {{c++26}} | `<simd>` | [[simd]] |

表后还有一个没进表的子条款 [numerics.c]：C23 的 `<stdckdint.h>`（`ckd_add`/`ckd_sub`/`ckd_mul`），见 [[numerics.c]]。

!!! lawyer "¶2 的措辞落后于目录"
    ¶2 仍说下面的子条款描述 "generalized numeric algorithms"，但 `accumulate`、`reduce`、`inclusive_scan`、`gcd`、`midpoint`、饱和算术等早已挪到算法章的 [[numeric.ops]] 与 [[numeric.sat]]（`<numeric>` 头文件），表 125 里也没有它们。这类过时的导言文字不具规范效力上的意义——真正的规则在各函数条目里——但查找时要知道去算法章找。

不在本章、但经常被误以为在本章的东西：

| 设施 | 实际位置 |
|---|---|
| `numeric_limits`、`<cfloat>`/`<climits>` | 语言支持库 [[support.limits]] |
| `<stdfloat>` 的 `float16_t` 等别名 | [[support.arith.types]]，类型本身在 [[basic.extended.fp]] |
| `<bit>`（`popcount`、`bit_cast`…） | 工具库 [[bit]] |
| `to_chars`/`from_chars` | 文本处理 [[charconv]] |
| `shuffle`、`sample`、`ranges::generate_random` 的规范正文 | 算法章 [[alg.random.shuffle]]、[[alg.random.sample]]、[[alg.rand.generate]] |
| `mdspan` 本身 | 容器章 [[views.multidim]] |

## 本章反复出现的几种法律后果

数值库的条文风格和容器、算法章不太一样：它大量借用数学记号，而且常常把**数学上的失败**直接定义成 UB。读之前先记住下面几种模式。

### 1. "结果在数学上无定义或不可表示" → UB

[[complex.numbers]] 的 [complex.numbers.general] ¶3 写得最直白：复数函数的结果在数学上无定义、或超出其类型的可表示范围时，行为未定义。这比当前草案的核心语言还严：[[expr.pre#4]] 对内建算术表达式只在数学结果"既不可表示、也不是该类型拥有的无穷或 NaN"时才是 UB，所以对 IEEE 浮点类型，内建运算里只剩除以零是 UB；`<complex>` 的 ¶3 没有这层豁免。`<cmath>` 则不同——它沿用 C 的 `math_errhandling` 机制报告定义域错误和值域错误（见 [[c.math]]），**不是** UB；但整数 `std::abs(INT_MIN)` 仍然是 UB，因为 C 对 `abs` 就是这么规定的。

### 2. 算法由实现定义 → 结果不可移植

[[rand.dist]] 的 [rand.dist.general] ¶3：每个分布**怎么**从均匀比特生成目标分布，由实现定义。于是同一个种子、同一个引擎，`uniform_int_distribution` 在 libc++、libstdc++、MSVC STL 上给出的序列可以不同。与之相对，引擎的算法是完全规定的，[[rand.eng]] 甚至给出"第 10000 次调用必须得到某个值"的 *Required behavior*。`default_random_engine` 的选择、`random_device` 的熵源也都是实现定义的。

### 3. 用模板形参的**名字**表达要求

[rand.req.genl] ¶1 规定：`<random>` 里凡是名为 `RealType`、`IntType`、`UIntType`、`URBG`、`Sseq`、`Engine` 的模板形参，自动带上相应要求；其中 `RealType`/`IntType`/`UIntType` 不合要求时程序**非良构**（所以 `uniform_int_distribution<char>` 必须被诊断）。[linalg] 用同样的手法（[linalg.algs.reqs]）：名为 `Triangle`、`DiagonalStorage`、`ExecutionPolicy` 的形参各有约束。读函数签名时，形参名本身就是合同的一部分。

### 4. Mandates / Constraints / Preconditions 的分工

与其他库章一样（见 [[mem]] 导读的表），本章的 *Mandates* 失败必须诊断，*Constraints* 失败使重载静默退出，*Preconditions* 失败是 UB。本章有几处值得注意的选择：

- `std::numbers::pi_v<int>`：实例化主模板直接**非良构**（[math.constants] ¶3）；
- `complex<int>`：实例化的效果是**未指明**的（[complex.numbers.general] ¶2）——既不保证能用，也不要求诊断；
- `valarray::operator[]`：*Hardened preconditions* {{c++26}}，加固实现下越界会被检查（[[g:hardened-precondition]]）；
- `linalg` 大量使用 *Mandates* 检查**静态** extent 是否兼容，再用 *Preconditions* 约束**动态** extent。

## 实现现状（本机 Clang 23 + libc++）

写作时对本机 libc++ 的实测结论汇总如下，细节见各页：

| 设施 | 状态 |
|---|---|
| `<complex>` 基本功能、字面量 | 已实现；C++26 的元组接口（结构化绑定）已实现 |
| `<complex>`/`<cmath>` 的 C++23/26 `constexpr` 扩展 | **未实现**：`std::floor`、`std::abs(double)`、`std::sin` 在常量表达式中都会被拒绝 |
| `<random>` 的经典引擎与分布 | 已实现；`default_random_engine` 是 `minstd_rand` |
| `philox_engine`、`ranges::generate_random` {{c++26}} | **未实现** |
| `generate_canonical` 的新规格 | **未采用**：仍是旧算法，可返回 1.0（见 [[rand.util]]） |
| `<valarray>` | 已实现，使用表达式模板 |
| 数学特殊函数 | 只有 `hermite`；`riemann_zeta`、`cyl_bessel_j` 等没有 |
| `<linalg>` {{c++26}} | **没有该头文件** |
| `<simd>` {{c++26}} | **没有该头文件** |
| `<stdckdint.h>` | 由 Clang 自带的 C 头文件提供，`ckd_*` 是宏而不是标准要求的函数模板 |

## 小结

- 本章 = 复数 + 随机数 + valarray + `<cmath>` + 常数 + `linalg` + `simd`（+ `<stdckdint.h>`）；`<numeric>` 的算法不在这里。
- "数学上无定义/不可表示"在 `<complex>` 里是 UB；`<cmath>` 走 C 的错误报告；整数 `abs` 的溢出是 UB。
- 分布算法由实现定义：要跨平台复现随机序列，只能依赖引擎，不能依赖分布。
- 模板形参名本身携带要求；违反 `RealType`/`IntType`/`UIntType` 要求是非良构。
