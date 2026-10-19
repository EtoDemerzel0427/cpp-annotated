---
title: 浮点类型的数学函数
summary: <cmath> 沿用 C 的 <math.h>，但用重载代替 f/l 后缀并规定混合实参的提升规则；它补充了三参 hypot、lerp 和数学特殊函数；C++23/26 让大部分函数成为 constexpr；数学错误按 C 的方式报告，不是 UB，而整数 abs(INT_MIN) 是 UB。
status: done
covers: *
papers: P0533R9, P1383R2, P0030R1, P0811R3, P0226R1, P1467R9
related: numerics, cfenv, complex.numbers, library.c, basic.fundamental, conv.rank, conv.prom, expr.const, numeric.sat, numerics.c
tags: 标准库, cmath, 浮点, constexpr, 特殊函数
updated: 2026-10-19
---

!!! tldr
    - `std::sqrt` 等函数对每个浮点类型都有重载；实参类型混合时，整数实参按 `double` 算，所以 `float` 参与的 `std::pow(x, 2)` 返回 `double`。
    - C++23 和 C++26 让绝大多数 `<cmath>` 函数成为 `constexpr`，但一次调用如果引发了 `FE_INEXACT` 以外的浮点异常（如 `sqrt(-1.0)`），它就不是常量表达式。
    - 定义域错误、极点错误、值域错误都不是 UB：按 `math_errhandling` 设置 `errno` 或引发浮点异常，返回值也有规定。依赖 `errno` 的代码不可移植。
    - 整数 `std::abs(INT_MIN)` 是 UB；`std::abs` 用于不能提升到 `int` 的无符号类型是非良构的。
    - `std::lerp(a, b, 1)` 保证精确等于 `b`，且结果随 t 单调，朴素公式 `a + t*(b-a)` 做不到。

## 一个函数名，多个浮点类型（[cmath.syn]）

```cpp run title="cmath-promotion.cpp" ok
#include <cmath>
#include <type_traits>
using std::is_same_v;

static_assert(is_same_v<decltype(std::sqrt(2)), double>);
static_assert(is_same_v<decltype(std::pow(1.0f, 2)), double>);
static_assert(is_same_v<decltype(std::pow(1.0f, 2.0f)), float>);
static_assert(is_same_v<decltype(std::fmax(1.0f, 2.0L)), long double>);
static_assert(is_same_v<decltype(std::abs(3)), int>);
```

C 用后缀区分类型：`sqrtf`、`sqrt`、`sqrtl`。C++ 保留了这些名字，同时让 `std::sqrt` 对每个浮点类型都有一个重载。上面第二行常让人意外：`x` 是 `float` 时，`std::pow(x, 2)` 的结果是 `double`。

¶1 `<cmath>` 的内容是 C `<math.h>` 的子集，只有概要里列出的声明存在。此外它增加了三参 `hypot`、`lerp` 和数学特殊函数（[sf.cmath]）。注 1 说明，有些函数在 C++ 里多了重载，但行为与 C 相同。

概要用占位符 *floating-point-type* 写函数签名。下面两段规定这个占位符怎样展开成真实的重载。

¶2 对每个至少有一个 *floating-point-type* 形参的函数，实现为每个 cv 非限定的浮点类型（[[basic.fundamental]]）各提供一个重载，把签名中的占位符全部换成这个类型。浮点类型包括 `float`、`double`、`long double`，也包括实现支持的扩展浮点类型（[[basic.extended.fp]]，如 `std::float16_t`），后者是 C++23 的 [[P1467R9]] 加入的。

¶3 除 `abs` 外，实现还要提供足够多的额外重载，处理实参类型不一致的情况。只要对应 *floating-point-type* 形参的实参都是算术类型，它们就都被转换为其中浮点转换秩（[[g:floating-point-conversion-rank]]，[[conv.rank]]）最高、子秩也最高的那个浮点类型；计算时整数实参被看作与 `double` 同秩。

整数按 `double` 算的规则来自 C 的 `<tgmath.h>`。`abs` 被排除在外，所以 `std::abs(3)` 选中整数版本，返回 `int`。

如果秩与子秩都最高的类型不存在，实现提供的重载中就没有可用的候选。这只会发生在扩展浮点类型之间：`std::float16_t` 和 `std::bfloat16_t` 的值集合互不包含，两者的转换秩无序，于是 `std::pow(std::float16_t(1), std::bfloat16_t(2))` 非良构。本机 libc++ 没有 `<stdfloat>`，无法实测。

¶4 如果 `nexttoward` 对应 *floating-point-type* 形参的实参是扩展浮点类型，调用非良构。`nexttoward` 的第二个参数固定是 `long double`，而扩展浮点类型与 `long double` 的关系因平台而异，标准索性不给它规定语义。

## 什么时候能在编译期调用

```cpp title="constexpr-cmath.cpp" error
#include <cmath>

constexpr double a = std::sqrt(2.0);    // OK（C++26）：只引发 FE_INEXACT
constexpr double b = std::sqrt(-1.0);   // error: 引发 FE_INVALID
constexpr double c = std::log(0.0);     // error: 引发 FE_DIVBYZERO
constexpr double d = std::floor(2.5);   // OK（C++23）
```

在当前草案中，概要里几乎所有函数都标了 `constexpr`。例外是结果依赖当前舍入模式的 `nearbyint`、`rint`、`lrint`、`llrint`，要解析字符串的 `nan`，以及全部数学特殊函数。这分两步完成：

- C++23 的 [[P0533R9]] 让不需要近似算法的函数成为 `constexpr`：`abs`、`fabs`、`floor`、`ceil`、`trunc`、`round`、`fmod`、`frexp`、`ldexp`、`fmin`、`fmax`、`copysign`、分类和比较函数等。
- C++26 {{c++26}} 的 [[P1383R2]] 扩展到 `sin`、`exp`、`log`、`pow`、`sqrt`、`hypot` 这类需要近似计算的函数。

`constexpr` 不代表每次调用都是常量表达式。[[library.c#3]] 规定，一次 C 标准库函数调用如果引发了 `FE_INEXACT` 以外的浮点异常，就是[[g:non-constant-library-call|非常量库调用]]，所在的表达式不是核心常量表达式。常量求值中的语义按 C 标准附录 F。注 2 给了一个等价说法：在 `math_errhandling & MATH_ERRNO` 为真的实现上，这就是会设置 `errno` 的那些调用。

!!! impl "libc++ 尚未实现"
    本机 libc++ 把这些函数直接转发到平台 C 库的非 `constexpr` 函数，`__cpp_lib_constexpr_cmath` 在它的 `<version>` 中是注释掉的。所以上例四行在本机全部报错，连 `std::floor(2.5)`、`std::fabs(-2.5)` 也不例外。

## 数学错误不是 UB

```cpp run title="math-errhandling.cpp" impl
#include <cerrno>
#include <cfenv>
#include <cmath>
#include <cstdio>

int main() {
  std::printf("ERRNO=%d ERREXCEPT=%d\n",
              (math_errhandling & MATH_ERRNO) != 0,
              (math_errhandling & MATH_ERREXCEPT) != 0);
  errno = 0;
  std::feclearexcept(FE_ALL_EXCEPT);
  volatile double m = -1.0;
  double r = std::sqrt(m);
  std::printf("%g errno=%d FE_INVALID=%d\n",
              r, errno, std::fetestexcept(FE_INVALID) != 0);
}
```

本机（macOS）输出 `ERRNO=0 ERREXCEPT=1` 和 `nan errno=0 FE_INVALID=1`：这个平台只用浮点异常报告错误，从不设置 `errno`。glibc 上两种方式通常都启用。

`<cmath>` 的错误处理完全沿用 C，错误分三类：

- 定义域错误（domain error）：实参不在函数的定义域内，如 `sqrt(-1)`；
- 极点错误（pole error）：结果在数学上趋于无穷，如 `log(0)`；
- 值域错误（range error）：结果太大或太小，无法表示。

发生错误时，如果 `math_errhandling & MATH_ERRNO` 为真，函数把 `errno` 设为 `EDOM` 或 `ERANGE`；如果 `math_errhandling & MATH_ERREXCEPT` 为真，函数引发相应的浮点异常（[[cfenv]]）。实现支持哪一种或两种由实现决定。返回值也有规定，比如 `sqrt(-1)` 返回 NaN。这和 `<complex>` 不同，那里结果在数学上无定义时行为未定义（[[complex.numbers]]）。

## 绝对值（[c.math.abs]）

¶1 注 1 说明，`<cstdlib>` 和 `<cmath>` 都声明本节的函数。

¶2 `int`、`long`、`long long` 版本的 `abs` 分别具有 C 的 `abs`、`labs`、`llabs` 的语义。C 规定结果不可表示时行为未定义，所以：

```cpp run title="abs-int-min.cpp" ub
#include <climits>
#include <cstdlib>

int main(int argc, char**) {
  int v = INT_MIN + (argc - 1);   // 运行期才知道的 INT_MIN
  return std::abs(v) > 0;         // UB: -INT_MIN 不可表示
}
```

用 `-fsanitize=undefined` 运行会报告 `negation of -2147483648 cannot be represented in type 'int'`。补码机器上典型的结果是 `abs(INT_MIN) == INT_MIN`，一个负的绝对值。需要安全的写法时，可以先转成无符号类型再取反，或者用 C++26 的饱和算术（[[numeric.sat]]）。

¶3 如果用类型 `X` 的实参调用 `abs`，`is_unsigned_v<X>` 为真，并且 `X` 不能经整型提升（[[conv.prom]]）转换为 `int`，程序非良构。注 2 说明，允许能提升为 `int` 的实参是为了与 C 兼容。

<div class="compare" markdown="1">

```cpp ok
#include <cstdlib>
unsigned short s = 1;
// 提升为 int，良构
// Clang 警告 -Wabsolute-value
int a = std::abs(s);
```

```cpp error
#include <cstdlib>
unsigned u = 1;
// unsigned 不能提升为 int
long b = std::abs(u);
```

</div>

这条规则拦住了一个常见错误：`a`、`b` 是 `size_t` 时写 `std::abs(a - b)`。差值已经回绕成一个很大的无符号数，对它取绝对值没有意义。本机 Clang 对右边报告 `call to 'abs' is ambiguous`。

¶4 浮点版本 `abs(floating-point-type)` 返回绝对值。概要中整数版本标为 freestanding，浮点版本标为 *freestanding-deleted*（[[g:freestanding-deleted-function]]）。

## 线性插值 lerp（[c.math.lerp]）

```cpp run title="lerp.cpp" ok
#include <cmath>
#include <cstdio>

int main() {
  double a = 1e17, b = 3.0;
  double naive = a + 1.0 * (b - a);   // b - a 舍入为 -1e17，结果是 0
  double r = std::lerp(a, b, 1.0);    // 保证精确等于 b
  std::printf("%g %g\n", naive, r);   // 0 3
}
```

`lerp(a, b, t)` 由 C++20 的 [[P0811R3]] 引入，是 `noexcept` 的。¶1 它返回 a + t(b − a)。真正有价值的是 ¶2 的 *Remarks*：设返回值为 r，当 `isfinite(a) && isfinite(b)` 时，

- ¶2.1 `t == 0` 时 r == a；
- ¶2.2 `t == 1` 时 r == b，精确相等；
- ¶2.3 0 ≤ t ≤ 1 时 r 是有限值；
- ¶2.4 t 有限且 a == b 时 r == a；
- ¶2.5 t 有限，或者 t 不是 NaN 且 b − a ≠ 0 时，r 不是 NaN。

¶2 最后还要求单调性：对任意 t₁、t₂，CMP(lerp(a,b,t₂), lerp(a,b,t₁))、CMP(t₂, t₁)、CMP(b, a) 三者之积非负，其中 CMP 返回 1、−1 或 0。直观地说，t 增大时结果只会沿着从 a 到 b 的方向走，不会回退。

上例说明朴素公式 `a + t * (b - a)` 不满足 ¶2.2。另一种朴素公式 `(1 - t) * a + t * b` 能保证端点精确，但不满足单调性，a == b 时也可能不返回 a。同时满足这些性质需要按 t 的范围和 a、b 的符号分情况处理，这是把它放进标准库的理由。

## 三维 hypot 与分类函数

[c.math.hypot3] ¶1 `hypot(x, y, z)` 返回 √(x² + y² + z²)，由 C++17 的 [[P0030R1]] 加入。直接算 `x*x + y*y + z*z` 时，x 在 1e200 左右中间结果就会上溢，而最终结果本来完全可以表示；好的实现会避免这种不必要的上溢和下溢。标准只规定了返回值的数学含义，没有规定精度。

[c.math.fpclass] ¶1 `fpclassify`、`isfinite`、`isinf`、`isnan`、`isnormal`、`signbit`，以及比较函数 `isgreater`、`isgreaterequal`、`isless`、`islessequal`、`islessgreater`、`isunordered`，行为与 C 中同名的宏相同。在 C++ 里它们是函数，有按浮点类型的重载和 ¶3 的额外重载，所以可以写 `std::isnan`，也可以传整数。比较函数与内建 `>` 等的区别是，遇到 NaN 时不引发 `FE_INVALID`。

## 数学特殊函数（[sf.cmath]）

C++17 的 [[P0226R1]] 把原先的特殊函数技术报告 ISO/IEC 29124 并入标准。一共 21 族，每族有 *floating-point-type* 版本和 `f`、`l` 后缀版本：

| 类别 | 函数 | 定义域（摘要） |
|---|---|---|
| 正交多项式 | `assoc_laguerre`、`assoc_legendre`、`hermite`、`laguerre`、`legendre` | 拉盖尔：x ≥ 0；勒让德：\|x\| ≤ 1 |
| Beta、指数积分、ζ | `beta`、`expint`、`riemann_zeta` | `beta`：x > 0，y > 0 |
| 椭圆积分 | `comp_ellint_1/2/3`、`ellint_1/2/3` | \|k\| ≤ 1 |
| 柱贝塞尔函数 | `cyl_bessel_i`、`cyl_bessel_j`、`cyl_bessel_k`、`cyl_neumann` | x ≥ 0 |
| 球函数 | `sph_bessel`、`sph_neumann`、`sph_legendre` | x ≥ 0；\|m\| ≤ ℓ |

### 统一的错误规则（[sf.cmath.general]）

¶1 任何实参是 NaN 时，函数返回 NaN，但不报告定义域错误。否则，函数只在以下情况报告定义域错误：

- ¶1.1 *Returns* 中明确给出了定义域，而实参落在定义域之外；
- ¶1.2 对应的数学函数值有非零的虚部；
- ¶1.3 对应的数学函数在数学上无定义。脚注说明，有定义是指在这组实参上明确有定义，或者极限存在且与趋近方向无关。

¶2 除非另有说明，每个函数对所有有限值以及正负无穷都有定义。

这里的报告定义域错误就是 C 意义上的：按 `math_errhandling` 设置 `errno = EDOM` 或引发 `FE_INVALID`，不是 UB。

### 高阶参数由实现定义

许多特殊函数的 *Remarks* 规定，整数阶参数大于等于 128 时，调用的效果由实现定义（{{impl}}）。例如 [sf.cmath.assoc.laguerre] ¶3（n ≥ 128 或 m ≥ 128）、[sf.cmath.cyl.bessel.j] ¶3（ν ≥ 128）、[sf.cmath.legendre] ¶3（ℓ ≥ 128）。高阶时这些函数很难算准，标准选择不作要求。

### 注意公式的约定

每个函数的 *Returns* 用一个公式给出。不同教材对同一个函数的定义可能相差一个符号因子，移植公式时要核对：

- [sf.cmath.hermite] 用的是物理学家的厄米多项式 Hₙ(x) = (−1)ⁿ e^(x²) dⁿ/dxⁿ e^(−x²)。
- [sf.cmath.assoc.legendre] 的 Pₗᵐ(x) = (1 − x²)^(m/2) dᵐ/dxᵐ Pₗ(x) 不带 (−1)ᵐ（Condon–Shortley 相位因子），而 [sf.cmath.sph.legendre] 的球谐函数带这个因子。
- [sf.cmath.assoc.laguerre] 的 Lₙᵐ(x) = (−1)ᵐ dᵐ/dxᵐ Lₙ₊ₘ(x)。

!!! impl "libc++ 的现状"
    本机 libc++ 只实现了 `hermite`（`std::hermite(3, 2.0)` 返回 40）。`riemann_zeta`、`cyl_bessel_j` 等都不存在，`std::riemann_zeta(2.0)` 报错 `no member named 'riemann_zeta' in namespace 'std'`。libstdc++ 和 MSVC STL 提供了全部特殊函数。

## fma 与浮点收缩

概要中的 `fma(x, y, z)` 计算 x·y + z，只在最后舍入一次。它能暴露普通表达式中被舍入吞掉的误差：

```cpp run title="fma.cpp" ok
#include <cmath>
#include <cstdio>

int main() {
  double p = 0.1 * 10.0 - 1.0;            // 0.1*10.0 舍入为 1.0，结果 0
  double q = std::fma(0.1, 10.0, -1.0);   // 只舍入一次：2^-54
  std::printf("%a %a\n", p, q);           // 0x0p+0 0x1p-54
}
```

反过来，编译器也可能自动把 `a * b + c` 收缩成一条 fma 指令。本机 arm64 上，把 `a * b + c` 写在一个对运行期值求值的函数里，Clang 默认（`-ffp-contract=on`）得到 `0x1p-54`，加 `-ffp-contract=off` 才得到 `0x0p+0`。C 用 `FP_CONTRACT` 编译指示控制这种收缩；在 C++ 中，允许它的依据是 [[expr.pre#6]]：浮点操作数和浮点表达式的结果可以用比类型要求更高的精度和范围表示。

所以同一个浮点表达式在不同编译选项下可能得到不同的舍入结果。需要逐位可复现时，要么显式写 `fma`，要么关闭收缩。

## 思考题

!!! question "思考题 1"
    `std::abs(-2147483648)`（字面量，`int` 为 32 位）是 UB 吗？

<details markdown="1">
<summary>答案</summary>

不是。`2147483648` 不能用 `int` 表示，按 [[lex.icon]] 它的类型是 `long`（`long` 只有 32 位时是 `long long`）。取负后得到 `long`（或 `long long`）的 −2147483648，于是选中对应的 `abs` 重载，结果 2147483648 在这个类型里可以表示。只有真正的 `int` 值 `INT_MIN` 才会触发 UB。
</details>

!!! question "思考题 2"
    `std::isnan(1)` 良构吗？返回什么？

<details markdown="1">
<summary>答案</summary>

良构。`isnan` 有 *floating-point-type* 形参且不是 `abs`，[cmath.syn] ¶3 的额外重载让整数实参按 `double` 处理，相当于 `isnan(1.0)`，返回 `false`。
</details>
