---
title: 浮点类型的数学函数
summary: <cmath> 的合同——C <math.h> 的子集外加三参 hypot、lerp 与数学特殊函数；按浮点类型逐一重载与"按最高浮点转换秩提升"的额外重载（整数视作 double）；C++23/26 的 constexpr 化与"引发浮点异常即非常量"；math_errhandling 的错误报告；整数 abs 的 INT_MIN 是 UB、无符号实参非良构；lerp 的精确性与单调性保证；特殊函数的定义域错误规则与 n ≥ 128 的实现定义行为
status: done
covers: *
papers: P0533R9, P1383R2, P0030R1, P0811R3, P0226R1, P1467R9
related: numerics, cfenv, complex.numbers, library.c, basic.fundamental, conv.rank, conv.prom, expr.const, numeric.sat, numerics.c
tags: 标准库, cmath, 浮点, constexpr, 特殊函数
updated: 2026-10-18
---

`<cmath>` 的绝大部分内容来自 C 的 `<math.h>`，C++ 的贡献在于三件事：

1. **重载代替后缀**：C 用 `sqrtf`/`sqrt`/`sqrtl` 区分类型，C++ 为每个浮点类型（包括扩展浮点类型）提供 `std::sqrt` 的重载，并规定混合类型实参如何提升；
2. **少量 C 没有的函数**：三参 `hypot`、`lerp`、21 族数学特殊函数；
3. **constexpr**：C++23 起逐步允许在常量表达式中调用数学函数。

本页覆盖 [c.math] 全部子条款，包括 21 个特殊函数子条款（[sf.cmath.*]）。

## 头文件与重载规则（[cmath.syn]）

概要声明了 `HUGE_VAL`、`INFINITY`、`NAN`、`FP_*` 分类宏、`FP_FAST_FMA*`、`MATH_ERRNO`/`MATH_ERREXCEPT`/`math_errhandling` 等宏，`float_t`/`double_t`，以及以 *floating-point-type* 为占位的函数族。

¶1：内容与含义是 C `<math.h>` 的子集，**只有**概要中的声明存在，此外增加三维 `hypot`、`lerp` 和 [sf.cmath] 的特殊函数。注释：有些函数有额外重载，但行为与 C 相同。

### 每个浮点类型一个重载（¶2）

¶2：对每个至少有一个 *floating-point-type* 形参的函数，实现为**每个 cv 非限定浮点类型**（[[basic.fundamental]]）提供一个重载，把签名中所有 *floating-point-type* 替换为该类型。"浮点类型"包括标准的 `float`/`double`/`long double` 和实现支持的扩展浮点类型（[[basic.extended.fp]]，如 `std::float16_t`）——这是 [[P1467R9]]（C++23）的改动。

### 混合实参的额外重载（¶3）

¶3：对每个至少有一个 *floating-point-type* 形参、且**不是 `abs`** 的函数，实现还提供足够的额外重载，使得：若对应 *floating-point-type* 形参的每个实参都是算术类型，则每个这样的实参都被"实际转换"为它们之中**浮点转换秩最高、且浮点转换子秩最高**的浮点类型（[[conv.rank]]，[[g:floating-point-conversion-rank]]）；**整数类型的实参被视为与 `double` 同秩**。若不存在这样一个"秩与子秩都最高"的类型，重载决议得不到可用候选。

```cpp run title="cmath-promotion.cpp" ok
#include <cmath>
#include <type_traits>

static_assert(std::is_same_v<decltype(std::sqrt(2)),          double>);       // int → 视作 double
static_assert(std::is_same_v<decltype(std::pow(1.0f, 2)),     double>);       // float 与 "double" 取高者
static_assert(std::is_same_v<decltype(std::pow(1.0f, 2.0f)),  float>);
static_assert(std::is_same_v<decltype(std::fmax(1.0f, 2.0L)), long double>);
```

第二行常常出乎意料：`std::pow(x, 2)` 当 `x` 是 `float` 时结果是 `double`。这条规则继承自 C 的 `<tgmath.h>`：整数实参按 `double` 处理。

"秩最高且子秩最高的类型不存在"的情形只会出现在扩展浮点类型之间：例如 `std::float16_t` 与 `std::bfloat16_t` 的值集合互不包含，它们的转换秩**无序**，于是 `std::pow(std::float16_t(1), std::bfloat16_t(2))` 没有可用候选，非良构。（本机 libc++ 没有 `<stdfloat>`，无法实测。）

¶4：对 `nexttoward`，若对应 *floating-point-type* 形参的实参具有扩展浮点类型，调用非良构。原因是 `nexttoward` 的第二参数固定为 `long double`，而扩展浮点类型与 `long double` 之间的关系由平台决定，规定其语义没有意义。

### constexpr 与错误：什么时候不是常量表达式

当前草案中，除 `nearbyint`、`rint`、`lrint`、`llrint`（结果依赖当前舍入模式）和 `nan`（解析字符串）外，概要中几乎所有函数都声明为 `constexpr`。演进分两步：

- C++23（[[P0533R9]]）：`abs`、`fabs`、`floor`、`ceil`、`trunc`、`round`、`fmod`、`frexp`、`ldexp`、`fmin`/`fmax`、`copysign`、分类与比较函数等"不需要近似算法"的函数；
- C++26（[[P1383R2]]）{{c++26}}：扩展到 `sin`、`exp`、`log`、`pow`、`sqrt`、`hypot` 等需要近似计算的函数。

`constexpr` 不意味着"永远是常量"。[[library.c#3]] 规定：C 标准库函数调用若**引发 `FE_INEXACT` 以外的浮点异常**，就是[[g:non-constant-library-call|非常量库调用]]，所在表达式不是核心常量表达式；常量求值中的语义按 C 附录 F。注释换了个等价说法：当 `math_errhandling & MATH_ERRNO` 为真时，就是"会设置 `errno` 的调用"。

```cpp title="constexpr-cmath.cpp" error
#include <cmath>

constexpr double a = std::sqrt(2.0);     // OK（C++26）：只引发 FE_INEXACT
constexpr double b = std::sqrt(-1.0);    // error：引发 FE_INVALID，非常量库调用
constexpr double c = std::log(0.0);      // error：引发 FE_DIVBYZERO（极点错误）
constexpr double d = std::floor(2.5);    // OK（C++23）
```

!!! impl "libc++ 尚未实现"
    本机 libc++ 中，`std::floor(2.5)`、`std::abs(-2.5)`、`std::sin(1.0)` 在常量表达式中都会被拒绝——它们直接转发到平台 C 库的非 `constexpr` 函数。`__cpp_lib_constexpr_cmath` 在 libc++ 的 `<version>` 中是注释掉的。所以上例中标为 OK 的两行在本机也会报错。

### 错误报告：math_errhandling

`<cmath>` 的错误处理完全沿用 C：

- **定义域错误**（domain error）：实参不在函数定义域内，如 `sqrt(-1)`；
- **极点错误**（pole error）：结果在数学上趋于无穷，如 `log(0)`；
- **值域错误**（range error）：结果太大或太小无法表示。

发生错误时，若 `math_errhandling & MATH_ERRNO`，设置 `errno`（`EDOM`/`ERANGE`）；若 `math_errhandling & MATH_ERREXCEPT`，引发相应浮点异常（[[cfenv]]）。由实现决定支持哪一种或两种。这些**都不是 UB**，返回值也有规定（如 `sqrt(-1)` 返回 NaN），这与 `<complex>` 的"结果无定义即 UB"（[[complex.numbers]]）形成对比。

```cpp run title="math-errhandling.cpp" impl
#include <cerrno>
#include <cfenv>
#include <cmath>
#include <cstdio>

int main() {
  std::printf("ERRNO=%d ERREXCEPT=%d\n",
              (math_errhandling & MATH_ERRNO) != 0, (math_errhandling & MATH_ERREXCEPT) != 0);
  errno = 0;
  std::feclearexcept(FE_ALL_EXCEPT);
  volatile double m = -1.0;
  double r = std::sqrt(m);
  std::printf("%g errno=%d FE_INVALID=%d\n", r, errno, std::fetestexcept(FE_INVALID) != 0);
}
```

本机（macOS）输出 `ERRNO=0 ERREXCEPT=1` 和 `nan errno=0 FE_INVALID=1`：这个平台只用浮点异常报告错误，从不设置 `errno`。在 glibc 上两者通常都启用。依赖 `errno` 检测数学错误的代码不可移植。

## 绝对值（[c.math.abs]）

¶1 注释：`<cstdlib>` 与 `<cmath>` 都声明这些函数。

¶2：`int`、`long`、`long long` 的 `abs` 具有 C 的 `abs`、`labs`、`llabs` 的语义。C 规定：结果不可表示时行为未定义。于是：

```cpp run title="abs-int-min.cpp" ub
#include <climits>
#include <cstdlib>

int main(int argc, char**) {
  int v = INT_MIN + (argc - 1);   // 运行期才知道的 INT_MIN
  return std::abs(v) > 0;         // UB：-INT_MIN 不可表示
}
```

用 `-fsanitize=undefined` 运行，报告"negation of -2147483648 cannot be represented in type 'int'"。二进制补码下典型的结果是 `abs(INT_MIN) == INT_MIN`，一个负的"绝对值"。需要安全的版本时，可以先转成无符号再取反，或用 C++26 的饱和算术（[[numeric.sat]]）。

¶3：若以类型 `X` 的实参调用 `abs`，`is_unsigned_v<X>` 为真且 `X` 不能经**整型提升**转换为 `int`（[[conv.prom]]），程序**非良构**。注释：允许能提升为 `int` 的实参是为了与 C 兼容。所以：

- `std::abs(unsigned short{1})`：`unsigned short` 提升为 `int`，良构（Clang 会警告"对无符号类型取绝对值没有效果"）；
- `std::abs(1u)`：`unsigned int` 不能提升为 `int`，非良构。

这条规则堵住了一个常见 bug：`std::abs(a - b)`，其中 `a`、`b` 是 `size_t`，差值已经回绕成一个巨大的无符号数，取"绝对值"毫无意义。

¶4：浮点版本 `abs(floating-point-type)` 返回绝对值。概要中它被标为 *freestanding-deleted*（[[g:freestanding-deleted-function]]），整数版本是 freestanding 的。注意 ¶3 的额外重载规则明确排除了 `abs`：`std::abs(3)` 选中整数版本，返回 `int`，不会变成 `double`。

## 三维 hypot（[c.math.hypot3]）

¶1：`hypot(x, y, z)` 返回 √(x² + y² + z²)。由 [[P0030R1]] 在 C++17 引入。和二元 `hypot` 一样，实现应当避免中间结果不必要的上溢和下溢——`x*x + y*y + z*z` 在 x 约为 1e200 时就上溢了，而结果本身完全可表示。不过标准只规定返回值的数学含义，没有对精度作出要求。

## 线性插值 lerp（[c.math.lerp]）

`lerp(a, b, t)` 由 [[P0811R3]] 在 C++20 引入，`noexcept`。¶1：返回 a + t(b − a)。重点在 ¶2 的 *Remarks*：设 r 为返回值，若 `isfinite(a) && isfinite(b)`：

- ¶2.1 `t == 0` 时 r == a；
- ¶2.2 `t == 1` 时 r == b——**精确**；
- ¶2.3 0 ≤ t ≤ 1 时 r 有限；
- ¶2.4 t 有限且 a == b 时 r == a；
- ¶2.5 t 有限，或 t 不是 NaN 且 b − a ≠ 0 时，r 不是 NaN。

还有**单调性**：对任意 t₁、t₂，CMP(lerp(a,b,t₂), lerp(a,b,t₁))·CMP(t₂, t₁)·CMP(b, a) ≥ 0——即 t 增大时结果沿 a→b 的方向不回退。

朴素公式 `a + t * (b - a)` 不满足 ¶2.2：

```cpp run title="lerp.cpp" ok
#include <cmath>
#include <cstdio>

int main() {
  double a = 1e17, b = 3.0;
  double naive = a + 1.0 * (b - a);     // b - a 舍入为 -1e17，结果是 0
  double r = std::lerp(a, b, 1.0);      // 标准保证精确得到 b
  std::printf("%g %g\n", naive, r);     // 0 3
}
```

另一种朴素公式 `(1 - t) * a + t * b` 满足端点精确，但不满足单调性，a == b 时也可能不返回 a。`lerp` 的实现需要按 t 的范围和 a、b 的符号分情况处理，这正是把它放进标准库的理由。

## 分类与比较函数（[c.math.fpclass]）

¶1：`fpclassify`、`isfinite`、`isinf`、`isnan`、`isnormal`、`signbit`、`isgreater`、`isgreaterequal`、`isless`、`islessequal`、`islessgreater`、`isunordered` 的行为与 C 中同名**宏**相同。在 C++ 中它们是函数（每个浮点类型一个重载，加上提升规则），不是宏——所以 `std::isnan` 可以加命名空间限定。`isgreater` 等比较函数与内建 `>` 的区别是：遇到 NaN 时不引发 `FE_INVALID`。

## 数学特殊函数（[sf.cmath]）

C++17 由 [[P0226R1]] 把原先的 ISO/IEC 29124（特殊函数 TR）并入标准。21 族函数，每族有 *floating-point-type* 版本和 `f`/`l` 后缀版本：

| 族 | 函数 | 定义域（摘要） |
|---|---|---|
| 正交多项式 | `assoc_laguerre`、`assoc_legendre`、`hermite`、`laguerre`、`legendre` | 拉盖尔：x ≥ 0；勒让德：\|x\| ≤ 1 |
| Beta / 指数积分 / ζ | `beta`、`expint`、`riemann_zeta` | `beta`：x > 0, y > 0 |
| 椭圆积分 | `comp_ellint_1/2/3`、`ellint_1/2/3` | \|k\| ≤ 1 |
| 柱贝塞尔 | `cyl_bessel_i`、`cyl_bessel_j`、`cyl_bessel_k`、`cyl_neumann` | x ≥ 0 |
| 球函数 | `sph_bessel`、`sph_neumann`、`sph_legendre` | x ≥ 0；\|m\| ≤ ℓ |

### 统一的错误规则（[sf.cmath.general]）

¶1：

- 任何实参是 NaN 时，函数**返回 NaN**，但**不报告定义域错误**；
- 否则，函数仅在以下情况报告定义域错误：¶1.1 *Returns* 中明确给出了定义域、而实参落在其外；¶1.2 对应的数学函数值有非零虚部；¶1.3 对应的数学函数在数学上无定义。

脚注 232：数学函数在一组实参上"有定义"，指它在那里被明确定义，或者其极限存在且与趋近方向无关。

¶2：除非另有规定，每个函数对所有有限值和正负无穷都有定义。

"报告定义域错误"就是 C 意义上的：按 `math_errhandling` 设置 `errno = EDOM` 或引发 `FE_INVALID`。这不是 UB。

### n ≥ 128 时实现定义

许多函数在 *Remarks* 中规定：整数阶参数（n、m、ℓ）**大于等于 128**，或贝塞尔函数的阶 ν ≥ 128 时，调用的效果是**实现定义**的（{{impl}}）。例如 [sf.cmath.assoc.laguerre] ¶3（n ≥ 128 或 m ≥ 128）、[sf.cmath.cyl.bessel.j] ¶3（ν ≥ 128）、[sf.cmath.legendre] ¶3（ℓ ≥ 128）。高阶时这些函数的数值计算很难保证精度，标准选择放手。

### 公式的约定

每个函数的 *Returns* 用一个公式给出，例如 [sf.cmath.hermite]：Hₙ(x) = (−1)ⁿ eˣ² dⁿ/dxⁿ e⁻ˣ²（物理学家的厄米多项式）。阅读时要注意标准选定的**约定**——不同教材的勒让德函数可能带 (−1)ᵐ 的 Condon–Shortley 相位因子，[sf.cmath.assoc.legendre] 的公式 Pₗᵐ(x) = (1 − x²)^(m/2) dᵐ/dxᵐ Pₗ(x) **不带**这个因子；而 [sf.cmath.sph.legendre] 的球谐函数带 (−1)ᵐ。移植公式时需要核对。

!!! impl "libc++ 的现状"
    本机 libc++ 只实现了 `hermite`（`hermite(3, 2.0)` 返回 40，NaN 实参返回 NaN），`riemann_zeta`、`cyl_bessel_j` 等都不存在——`std::riemann_zeta(2.0)` 编译报错"no member named 'riemann_zeta' in namespace 'std'"。libstdc++ 和 MSVC STL 提供了完整的特殊函数。

## 一个 fma 例子

概要中的 `fma(x, y, z)` 计算 x·y + z 并**只舍入一次**。它能暴露普通表达式中被吞掉的舍入误差：

```cpp run title="fma.cpp" ok
#include <cmath>
#include <cstdio>

int main() {
  double p = 0.1 * 10.0 - 1.0;            // 0.1*10.0 舍入为 1.0，结果 0
  double q = std::fma(0.1, 10.0, -1.0);   // 精确的 0.1(double)×10 − 1 = 2^-54
  std::printf("%a %a\n", p, q);           // 0x0p+0 0x1p-54
}
```

反过来，编译器也可能**自动**把 `a * b + c` 收缩成一条 fma 指令。实测：本机 arm64 上把 `a * b + c` 写在一个对运行期值求值的函数里，Clang 在默认设置（`-ffp-contract=on`）下得到 `0x1p-54`，加 `-ffp-contract=off` 才得到 `0x0p+0`。C 用 `FP_CONTRACT` 编译指示控制这种收缩；C++ 中它的依据是 [[expr.pre#6]]：浮点操作数和浮点表达式的结果可以用比类型要求更高的精度和范围表示。结论是同一个表达式在不同编译选项下可以有不同的舍入结果，需要逐位可复现时要显式写 `fma` 或关闭收缩。

## 思考题

!!! question "1"
    `std::abs(-2147483648)`（字面量，`int` 为 32 位）是 UB 吗？

<details markdown="1">
<summary>答案</summary>

不是。`2147483648` 不能用 `int` 表示，按 [[lex.icon]] 它的类型是 `long`（或 `long long`），一元负号作用后是 `long` 的 −2147483648。于是选中 `abs(long)`，结果 2147483648 可以用 `long` 表示（64 位 `long` 或 `long long` 的情况下）。只有真正的 `int` 值 `INT_MIN` 才触发 UB。
</details>

!!! question "2"
    `std::isnan(1)` 良构吗？返回什么？

<details markdown="1">
<summary>答案</summary>

良构。`isnan` 有 *floating-point-type* 形参且不是 `abs`，[cmath.syn] ¶3 的额外重载使整数实参被视作 `double`，相当于 `isnan(1.0)`，返回 `false`。
</details>

## 小结

| 规则 | 出处 | 要点 |
|---|---|---|
| 每个浮点类型一个重载 | [cmath.syn] ¶2 | 含扩展浮点类型 |
| 混合实参提升 | ¶3 | 取秩与子秩最高者；整数视作 `double`；`abs` 除外 |
| `nexttoward` + 扩展浮点 | ¶4 | 非良构 |
| constexpr | 概要、[[library.c#3]] | C++23/26 逐步扩大；引发非 inexact 异常即非常量 |
| 数学错误 | C 的 `math_errhandling` | 设 `errno` 或引发异常，不是 UB |
| `abs(INT_MIN)` | [c.math.abs] ¶2 | UB |
| `abs(unsigned)`（不能提升到 `int`） | ¶3 | 非良构 |
| `lerp` | [c.math.lerp] ¶2 | 端点精确、[0,1] 内有限、单调 |
| 特殊函数 | [sf.cmath.general] | NaN 进 NaN 出不报错；定义域外报定义域错误；高阶实现定义 |
