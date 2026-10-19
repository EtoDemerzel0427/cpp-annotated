---
title: 数学常数
summary: <numbers> 把 π、e、√2 等 13 个常数做成 constexpr 变量模板，对每种浮点类型给出最近的可表示值；程序可以为自己的类型特化它们，但用非浮点类型实例化主模板是非良构的。
status: done
covers: *
papers: P0631R8
related: numerics, c.math, namespace.std, temp.expl.spec, concepts.arithmetic, basic.extended.fp
tags: 标准库, 数学常数, 变量模板
updated: 2026-10-19
---

!!! tldr
    - C++20 起，`std::numbers::pi` 是一个 `constexpr double`，值恰好是离 π 最近的 `double`；`pi_v<float>` 是离 π 最近的 `float`。
    - 每个常数都有三种写法：变量模板 `pi_v<T>`、它对浮点类型的部分特化，以及 `double` 版的简写 `pi`。
    - 程序可以为自己定义的类型（定点数、区间、多精度数）特化 `pi_v<T>`，让泛型代码一律写 `pi_v<T>`。
    - `pi_v<int>` 这类用法会实例化主模板，程序非良构，编译器必须报错，而不会悄悄把 π 截成 3。

## 用法

```cpp run title="numbers.cpp" ok
#include <cstdio>
#include <numbers>

int main() {
  static_assert(std::numbers::pi == std::numbers::pi_v<double>);
  constexpr float pf = std::numbers::pi_v<float>;         // 最近的 float
  constexpr double area = std::numbers::pi * 2.0 * 2.0;   // 编译期可用
  std::printf("%.9g %.17g\n", pf, area);                  // 3.14159274 12.566370614359172
}
```

C++20 之前要用 π，只能用 POSIX 的 `M_PI`（不属于标准 C 或标准 C++，MSVC 还要先定义 `_USE_MATH_DEFINES`）、手抄一个字面量，或者在运行期算 `4 * std::atan(1.0)`。`<numbers>`（[[P0631R8]]）给出了一个可移植、编译期可用、精度有保证的替代。

## 13 个常数（[numbers.syn]）

所有名字都在命名空间 `std::numbers` 里。以 π 为例，每个常数有三层声明：

```cpp
template<class T> constexpr T pi_v = unspecified;              // 主模板
template<floating_point T> constexpr T pi_v<T> = see below;    // 浮点类型的部分特化
inline constexpr double pi = pi_v<double>;                     // double 简写
```

| 名字 | 值 | 名字 | 值 |
|---|---|---|---|
| `e` | e | `ln10` | ln 10 |
| `log2e` | log₂ e | `sqrt2` | √2 |
| `log10e` | log₁₀ e | `sqrt3` | √3 |
| `pi` | π | `inv_sqrt3` | 1/√3 |
| `inv_pi` | 1/π | `egamma` | 欧拉–马斯刻若尼常数 γ |
| `inv_sqrtpi` | 1/√π | `phi` | 黄金比 (1 + √5)/2 |
| `ln2` | ln 2 | | |

部分特化的约束是 `floating_point<T>`（[[concepts.arithmetic]]）。这个概念对 cv 限定的浮点类型也成立，所以 `pi_v<const double>` 同样可用；实现支持的扩展浮点类型（[[basic.extended.fp]]）也自动包括在内。

## 精度保证（[math.constants]）

¶1 标准库提供的部分特化，用各个常数的最近可表示值初始化。

所以 `pi_v<float>` 是从真实的 π 一次舍入到 `float` 的结果。它不等同于 `static_cast<float>(pi_v<double>)`：先舍入到 `double` 再舍入到 `float` 是两次舍入，在个别情况下会与一次舍入的结果不同。

与 `4 * std::atan(1.0)` 比，`atan` 的精度不受标准约束，而且本机 libc++ 中它不能用在常量表达式里。本机实测两者的位模式相同（都是 `0x1.921fb54442d18p+1`），但这是平台数学库质量好，不是标准的承诺。

## 为自己的类型特化（¶2）

¶2 按照 [[namespace.std]] 的一般规则，程序可以部分特化或显式特化这些变量模板，条件是特化依赖于一个程序定义的类型。

这样，区间算术、定点数之类的库可以提供 `pi_v<MyType>`，泛型代码写一次 `pi_v<T>` 就同时适用于内建类型和自定义类型：

```cpp run title="numbers-specialize.cpp" ok
#include <numbers>

struct Interval { double lo, hi; };   // 用两个 double 夹住真值

template<>
inline constexpr Interval std::numbers::pi_v<Interval>{
    3.141592653589793, 3.1415926535897936};

template<class T>
constexpr T area(T r) { return std::numbers::pi_v<T> * r * r; }

int main() {
  constexpr Interval p = std::numbers::pi_v<Interval>;
  static_assert(p.lo < p.hi);
  static_assert(area(1.0) == std::numbers::pi);
}
```

为 `int`、`double` 这类不是程序定义的类型写特化，或者为 `std::complex<double>` 这类标准库类型写特化，都不在允许之列，行为未定义。

## 主模板不能被实例化（¶3）

¶3 实例化数学常数变量模板主模板的程序是非良构的。

主模板的初始化器写成 *unspecified*，就是因为它永远不该被用到。对一个既不是浮点类型、也没有用户特化的类型求 `pi_v<T>`，编译器必须给出诊断：

```cpp title="numbers-int.cpp" error
#include <numbers>

auto x = std::numbers::pi_v<int>;   // error: 实例化主模板
```

本机 libc++ 用一个依赖于 `T` 的 `static_assert` 实现这条规则，报错信息直接引用了这一段的原文。

!!! lawyer "只命名、不实例化"
    ¶3 只管实例化。变量模板特化只有在需要它的定义时才会隐式实例化（[[temp.inst]]），出现在 `decltype` 里只需要声明。所以 `using T = decltype(std::numbers::pi_v<int>);` 是良构的，`T` 是 `const int`（变量声明为 `constexpr`，所以带 `const`）。本机 libc++ 对它不报错，与标准一致。只有真正读取它的值时才会实例化定义，触发诊断。
