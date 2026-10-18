---
title: 数学常数
summary: <numbers> 中 13 个数学常数的变量模板与 double 版本——对浮点类型取最近可表示值的保证；主模板"未指明"、实例化它即非良构；程序可以为自定义类型特化；与 M_PI、4*atan(1) 的对比
status: done
covers: *
papers: P0631R8
related: numerics, c.math, namespace.std, temp.expl.spec, concepts.arithmetic, basic.extended.fp
tags: 标准库, 数学常数, 变量模板
updated: 2026-10-18
---

C++20 之前，C++ 程序要用 π 只有几种不理想的选择：POSIX 的 `M_PI`（不是标准 C 也不是标准 C++，MSVC 要先定义 `_USE_MATH_DEFINES`）、手写字面量（容易抄错位数）、或者 `4 * std::atan(1.0)`（运行期计算，且依赖 `atan` 的精度）。[[P0631R8]] 在 C++20 引入 `<numbers>`，把常用常数做成 `constexpr` 变量模板，精度由标准保证。

## 概要（[numbers.syn]）

所有名字都在 `std::numbers` 命名空间中。对 13 个常数，各有三层声明：

1. 主变量模板：`template<class T> constexpr T pi_v = unspecified;`
2. 对浮点类型的部分特化：`template<floating_point T> constexpr T pi_v<T> = see below;`
3. `double` 的简写：`inline constexpr double pi = pi_v<double>;`

| 名字 | 值 | 名字 | 值 |
|---|---|---|---|
| `e` | e | `ln10` | ln 10 |
| `log2e` | log₂ e | `sqrt2` | √2 |
| `log10e` | log₁₀ e | `sqrt3` | √3 |
| `pi` | π | `inv_sqrt3` | 1/√3 |
| `inv_pi` | 1/π | `egamma` | 欧拉–马斯刻若尼常数 γ |
| `inv_sqrtpi` | 1/√π | `phi` | 黄金比 (1 + √5)/2 |
| `ln2` | ln 2 | | |

部分特化用的约束是 `floating_point<T>`（[[concepts.arithmetic]]），它对 cv 限定的浮点类型也成立，所以 `pi_v<const double>` 同样可用；扩展浮点类型（[[basic.extended.fp]]）也自动覆盖。

## 精度保证（[math.constants] ¶1）

¶1：库定义的部分特化，以 e、log₂e、…、φ 的**最近可表示值**初始化。

这是一个很强的保证：`std::numbers::pi` 恰好是与 π 最接近的 `double`，`pi_v<float>` 恰好是与 π 最接近的 `float`。它不是 `static_cast<float>(pi_v<double>)`——两次舍入（先到 `double` 再到 `float`）在某些常数上可能与一次舍入的结果不同，标准要求的是一次舍入。

对比 `4 * std::atan(1.0)`：`atan` 的精度标准不作保证，而且它不是常量表达式（至少在本机 libc++ 上）。本机实测两者的位模式相同（都是 `0x1.921fb54442d18p+1`），但这只是 libm 的质量好，不是标准的承诺。

```cpp run title="numbers.cpp" ok
#include <cstdio>
#include <numbers>

int main() {
  static_assert(std::numbers::pi == std::numbers::pi_v<double>);
  constexpr float pf = std::numbers::pi_v<float>;         // 最近的 float
  constexpr double area = std::numbers::pi * 2.0 * 2.0;   // 编译期可用
  std::printf("%.9g %.17g\n", pf, area);
}
```

## 为自定义类型特化（¶2）

¶2：依据 [[namespace.std]]，程序可以部分特化或显式特化数学常数变量模板，**前提是**特化依赖于程序定义的类型。

这让定点数、区间算术、多精度浮点等库可以提供 `std::numbers::pi_v<MyType>`，使泛型代码写一次 `pi_v<T>` 就能适用于内建与自定义类型：

```cpp run title="numbers-specialize.cpp" ok
#include <numbers>

struct Interval { double lo, hi; };     // 区间算术：用两个 double 夹住真值

template<>
inline constexpr Interval std::numbers::pi_v<Interval>{3.141592653589793, 3.1415926535897936};

template<class T>
constexpr T circle_area(T r) { return std::numbers::pi_v<T> * r * r; }

int main() {
  constexpr Interval p = std::numbers::pi_v<Interval>;
  static_assert(p.lo < p.hi);
  static_assert(circle_area(1.0) == std::numbers::pi);
}
```

对 `int`、`double` 之类非程序定义类型特化，按 [[namespace.std]] 是 UB；对标准库类型（如 `std::complex<double>`）特化也不允许。

## 实例化主模板即非良构（¶3）

¶3：实例化数学常数变量模板**主模板**的程序非良构。

主模板的初始化器写作 *unspecified*，正是因为它永远不应被使用：对一个非浮点、又没有用户特化的类型取 `pi_v<T>`，必须得到诊断，而不是悄悄地把 π 截断成 3。

```cpp title="numbers-int.cpp" error
#include <numbers>

auto x = std::numbers::pi_v<int>;   // error：实例化主模板
```

本机 libc++ 用一个依赖于 `T` 的 `static_assert` 实现这条规则，诊断信息直接引用了标准原文："A program that instantiates a primary template of a mathematical constant variable template is ill-formed."

!!! lawyer "只命名、不实例化"
    ¶3 的触发条件是**实例化**主模板。变量模板特化只有在需要其定义时才被隐式实例化（[[temp.inst]]）；仅出现在 `decltype` 中只需要声明。所以 `using T = decltype(std::numbers::pi_v<int>);` 是良构的，`T` 就是 `int`——本机 libc++ 对它不报错，与标准一致。只有真正读取它的值（odr-use 或常量求值）时才实例化定义，触发诊断。

## 小结

| 规则 | 出处 | 后果 |
|---|---|---|
| 浮点类型的值 | [math.constants] ¶1 | 最近可表示值（一次舍入） |
| 用户特化 | ¶2 | 仅限依赖于程序定义类型的特化 |
| 实例化主模板 | ¶3 | 非良构 |
| `pi` 等简写 | [numbers.syn] | `inline constexpr double` |
