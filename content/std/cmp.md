---
title: 比较
summary: 头文件 <compare> 定义 <=> 的结果类型（三种比较类别）、取公共类别的 common_comparison_category、three_way_comparable 概念、compare_three_way_result，以及 strong_order 等比较算法和 C++26 的 type_order。
status: done
covers: *
papers: P0515R3, P0768R1, P1614R2, P1959R0
related: expr.spaceship, class.compare, class.spaceship, over.match.oper, comparisons.three.way, concept.totallyordered, customization.point.object, support.limits
tags: 标准库, 三路比较, operator<=>, strong_ordering, 概念
updated: 2026-10-19
---

!!! tldr
    - `<=>` 的结果是三种比较类别之一：`strong_ordering`、`weak_ordering`、`partial_ordering`，依次越来越弱；强的可以隐式转换为弱的。
    - 比较类别的值只能和字面量 `0` 比较，例如 `r < 0`；和其他值比较是未定义行为，libc++ 直接报错。
    - `common_comparison_category` 取一组类别中最弱的那个，默认的 `operator<=>` 就用它推导返回类型。
    - `std::strong_order`、`std::weak_order` 为浮点数提供全序和弱序，可以给含 NaN 的数据排序。
    - C++26 的 `std::type_order` 在编译期给所有类型排出一个全序。

## `<=>` 的结果是什么类型 [compare.syn]

```cpp run title="partial-ordering.cpp" ok
#include <compare>
#include <limits>
int main() {
  double nan = std::numeric_limits<double>::quiet_NaN();
  auto r = 1.0 <=> nan;
  bool ok = r == std::partial_ordering::unordered
         && !(r < 0) && !(r == 0) && !(r > 0) && (r != 0);
  return ok ? 0 : 1;
}
```

C++20 的三路比较运算符 `<=>`（[[expr.spaceship]]）不返回 `int`。两个 `double` 比较，结果的类型是 `std::partial_ordering`。它除了小于、等价、大于，还有第四个值 `unordered`，表示两个值无法比较，比如其中一个是 NaN。

这些结果类型由库定义，核心语言却直接使用它们：内建 `<=>` 的结果类型、默认 `operator<=>` 的返回类型（[[class.spaceship]]）、用 `<=>` 改写 `a < b` 的规则（[[over.match.oper]]）都依赖本节。所以 [[expr.spaceship]] 规定，使用 `<=>` 之前，即使是内建的 `1 <=> 2`，也必须包含 `<compare>`（或 `import std;`），否则程序非良构。

¶1 `<compare>` 提供主要与三路比较运算符配合使用的类型、对象和函数。整个头文件是 freestanding 的。函数对象 `std::compare_three_way` 也在 `<compare>` 中声明，但它的规定在 [[comparisons.three.way]]。

## 三种比较类别 [cmp.categories]

### 它们的区别

¶1 `partial_ordering`、`weak_ordering`、`strong_ordering` 统称**比较类别类型**（comparison category types）。

区分它们要用到一个概念。¶4 **可替换性**（[[g:substitutability]]）指：只要 `a == b` 为真，`f(a) == f(b)` 就为真。这里的 `f` 只读取比较相关的状态，而且只通过实参的公开 const 成员读取。

| 类型 | 值 | 相等意味着可替换 | 允许无法比较 | 典型例子 |
|---|---|---|---|---|
| `strong_ordering` | `less`、`equal`、`greater` | 是 | 否 | 整数、指针 |
| `weak_ordering` | `less`、`equivalent`、`greater` | 否 | 否 | 不区分大小写的字符串 |
| `partial_ordering` | `less`、`equivalent`、`greater`、`unordered` | 否 | 是 | 浮点数 |

不区分大小写比较时，`"abc"` 和 `"ABC"` 等价，但它们的第一个字符不同，所以不可替换，只能是弱序。¶2 的注说明，`strong_ordering` 对应数学上的全序。

¶1 每个类型都以一个仅用于说明的成员 `value` 来规定，它的值通常是下面两个仅用于说明的枚举之一：

```cpp
enum class ord  { equal = 0, equivalent = equal, less = -1, greater = 1 };
enum class ncmp { unordered = -127 };
```

所以 `strong_ordering::equal` 和 `strong_ordering::equivalent` 是同一个值，两个名字是为了让泛型代码写法统一。

### 只能和字面量 0 比较（¶3）

!!! std
    In this context, the behavior of a program that supplies an argument other than a literal `0` is undefined.

¶3 比较类别类型的关系运算符和相等运算符，形参是一个未指定类型的匿名形参。实现选择这个类型时，必须让它能接受字面量 `0`；例 1 说 `nullptr_t` 就满足要求。传入字面量 `0` 以外的实参，行为未定义。

于是比较结果的用法和 `strcmp` 的返回值一样：`r < 0` 表示小于，`r == 0` 表示相等，`0 > r` 也可以。这个设计让旧代码的习惯继续可用，同时防止人们把结果当作整数，写出 `r == -1` 这样的代码。

```cpp error
#include <compare>
bool f(std::strong_ordering r) {
  return r < 1;   // 标准：UB；libc++：error
}
```

!!! impl "libc++ 把这种 UB 变成了编译错误"
    libc++ 的形参类型是 `_CmpUnspecifiedParam`，它只有一个 `consteval` 构造函数模板，只接受 `int`，并用 Clang 的 `enable_if` 属性要求实参等于 0。所以 `r < 1`、`r < z`（`z` 是 `int` 变量）、`r < nullptr` 都会在编译期报错。这比标准更严格，标准把这种情况定为 UB，正是给实现留出了报错的余地。

### `partial_ordering` 的 `unordered`

[cmp.partialord] 的脚注说，对 `partial_ordering` 的类型，`a < b`、`a == b`、`a > b` 可能全都为假。¶2 规定 `v @ 0`（`@` 是任一关系或相等运算符）的结果是 `v` 有序并且 `v.value @ 0`。所以 `unordered` 和 0 的任何比较都为假，只有 `!=` 为真，因为 `!=` 由 `==` 改写而来。开头的例子演示的就是这一点。

### 转换和反转

- **隐式转换只能从强到弱**：`strong_ordering` → `weak_ordering` → `partial_ordering`，按 `value` 的符号对应（[cmp.weakord] ¶2，[cmp.strongord] ¶2–¶3）。反方向没有转换，`unordered` 在 `weak_ordering` 里没有对应的值。
- **`0 <=> v` 把结果反过来**：小于变大于，大于变小于，其余不变（[cmp.partialord] ¶5，[cmp.weakord] ¶6，[cmp.strongord] ¶7）。`v <=> 0` 原样返回 `v`。编译器把 `a < b` 改写为 `0 < (b <=> a)` 时（[[over.match.oper]]），依赖的就是这一点。
- **具名比较函数** `is_eq`、`is_neq`、`is_lt`、`is_lteq`、`is_gt`、`is_gteq`（[compare.syn]）接受 `partial_ordering`，等价于与 0 比较。另外两种类别可以隐式转换过来，所以也能用。

## 取最弱的类别 [cmp.common]

```cpp run title="common-category.cpp" ok
#include <compare>
#include <type_traits>
using std::common_comparison_category_t;
using std::strong_ordering, std::weak_ordering, std::partial_ordering;
static_assert(std::is_same_v<
  common_comparison_category_t<strong_ordering, weak_ordering>,
  weak_ordering>);
static_assert(std::is_same_v<
  common_comparison_category_t<strong_ordering, partial_ordering>,
  partial_ordering>);
static_assert(std::is_same_v<
  common_comparison_category_t<>, strong_ordering>);
static_assert(std::is_same_v<
  common_comparison_category_t<strong_ordering, int>, void>);

struct P {
  int i;
  double d;
  auto operator<=>(const P&) const = default;
};
static_assert(std::is_same_v<decltype(P{} <=> P{}), partial_ordering>);
int main() {}
```

¶1 `common_comparison_category<Ts...>::type` 是所有模板实参都能转换到的最强类别。注 1 解释了更强的意思：两个类别不同，而前者可以转换为后者。

¶2 它就是 `Ts...` 的**公共比较类型**（[[g:common-comparison-type]]，定义在 [[class.spaceship]]）。只要有一个实参不是比较类别类型，结果就是 `void`。注 2 说明，实参为空时结果是 `strong_ordering`。

简单地说就是取最弱：有一个是 `partial_ordering`，结果就是 `partial_ordering`；否则有一个是 `weak_ordering`，结果就是 `weak_ordering`；否则是 `strong_ordering`。默认的 `auto operator<=>` 正是这样推导返回类型的：取所有成员的 `<=>` 结果的公共比较类型。上例中 `P` 的 `int` 成员给出强序，`double` 成员给出偏序，合起来是偏序。

## `three_way_comparable` 概念 [cmp.concept]

```cpp
template<class T, class Cat = partial_ordering>
  concept three_way_comparable =
    weakly-equality-comparable-with<T, T> &&
    partially-ordered-with<T, T> &&
    requires(const remove_reference_t<T>& a, const remove_reference_t<T>& b) {
      { a <=> b } -> compares-as<Cat>;
    };
```

这个概念要求 `T` 的 const 左值之间能用 `==`、`!=`、四个关系运算符和 `<=>` 比较。仅用于说明的 *`compares-as<R, Cat>`* 要求 `common_comparison_category_t<R, Cat>` 就是 `Cat`，也就是说 `<=>` 的结果至少和 `Cat` 一样强。所以 `three_way_comparable<double>` 成立，`three_way_comparable<double, std::weak_ordering>` 不成立。

和所有标准概念一样，它分成两层。上面的 `requires` 表达式是语法要求，编译器检查。另一层是语义要求，条文写作 "T models ... only if"，编译器不检查：

- ¶2.1–¶2.7 `a <=> b` 的结果与 `==`、`!=`、`<`、`>`、`<=`、`>=` 的结果一致，而且 `(a <=> b) <=> 0` 与 `0 <=> (b <=> a)` 相等；
- ¶2.8 如果 `Cat` 能转换为 `strong_ordering`，`T` 还必须构成 `totally_ordered`（[[concept.totallyordered]]）。

满足语法要求、不满足语义要求的类型，叫做满足（satisfy）但不构成（model）这个概念。例如一个 `<=>` 和 `<` 结果不一致的类型。程序的有效性或含义依赖于它是否构成某个概念时，满足而不构成的情形是 IFNDR，即非良构但不要求诊断（[[res.on.requirements#2]]）。

¶1 仅用于说明的 *`partially-ordered-with<T, U>`* 要求 `t < u`、`u > t` 等八个关系运算都可用；语义上它们定义在同一个值域上，并且互为镜像，例如 `t < u` 与 `u > t` 结果相同。

¶3 `three_way_comparable_with<T, U, Cat>` 用于两个不同的类型。它额外要求 `T` 和 `U` 有公共引用类型，混合比较的结果与把两边转换到公共类型后再比较的结果相同（¶3.5），`Cat` 能转换为 `strong_ordering` 时还要构成 `totally_ordered_with`（¶3.10）。

## `compare_three_way_result` [cmp.result]

¶2 设 `t`、`u` 分别是 `const remove_reference_t<T>` 和 `const remove_reference_t<U>` 类型的左值。如果 `t <=> u` 作为不求值操作数是良构的，`compare_three_way_result<T, U>::type` 就是 `decltype(t <=> u)`；否则没有成员 `type`，在模板里可以据此做 SFINAE。

它查询的是 const 左值之间的比较。一个类型只有非 const 的 `operator<=>` 时，`compare_three_way_result_t` 不存在。

¶1 程序为 `compare_three_way_result` 添加特化，行为未定义。

## 比较算法 [cmp.alg]

### 六个定制点对象

`strong_order`、`weak_order`、`partial_order`、`compare_strong_order_fallback`、`compare_weak_order_fallback`、`compare_partial_order_fallback` 都是**定制点对象**（[[customization.point.object]]）：它们是函数对象，调用时按固定顺序尝试几种实现方式，选第一个可行的。都不可行时调用非良构，在模板实参替换中表现为替换失败（注 1–注 6）。

六个对象都先要求两个实参退化后的类型相同（¶1.1、¶2.1 等），否则非良构，它们不做混合类型的比较。

### 浮点数的全序和弱序

```cpp run title="cmp-alg.cpp" ok
#include <compare>
#include <limits>
int main() {
  double nan = std::numeric_limits<double>::quiet_NaN();
  bool ok =
      ((-0.0 <=> 0.0) == 0)               // 内建：-0 与 +0 等价
   && (std::strong_order(-0.0, 0.0) < 0)  // totalOrder：-0 < +0
   && (std::strong_order(nan, nan) == 0)  // 同一个 NaN：相等
   && (std::weak_order(-0.0, 0.0) == 0)   // 两个零在同一等价类
   && (std::strong_order(1.0, nan) < 0);  // 正 NaN 大于所有正数
  return ok ? 0 : 1;
}
```

浮点数的内建 `<=>` 只给出 `partial_ordering`：NaN 无法比较，`-0.0` 和 `+0.0` 等价。需要全序的场合，例如给含 NaN 的数组排序，就不能用它。

¶1 `strong_order(E, F)` 依次尝试：

1. ¶1.2 只用实参依赖查找（ADL）找到的 `strong_order(E, F)`，结果转换为 `strong_ordering`，这是用户定制的入口；
2. ¶1.3 如果实参是浮点类型，给出与该类型比较运算符一致的全序；如果 `numeric_limits<T>::is_iec559` 为真，这个全序还要与 IEEE 754（ISO/IEC 60559）的 totalOrder 操作一致；
3. ¶1.4 `strong_ordering(compare_three_way()(E, F))`，如果良构。

totalOrder 的顺序是：负 NaN、负无穷、负数、`-0`、`+0`、正数、正无穷、正 NaN，而且区分不同位模式的 NaN。

¶2 `weak_order(E, F)` 的步骤类似。浮点情形（¶2.3）给出下面这些等价类，从小到大：所有负 NaN、负无穷、每个负正规数、每个负次正规数、两个零、每个正次正规数、每个正正规数、正无穷、所有正 NaN。所以 `weak_order(-0.0, +0.0)` 是 `equivalent`。对非浮点类型，依次尝试 `compare_three_way()(E, F)`（¶2.4）和 `strong_order(E, F)`（¶2.5）。

¶3 `partial_order(E, F)` 依次尝试 ADL 找到的 `partial_order`、`compare_three_way()(E, F)` 和 `weak_order(E, F)`。

### 三个 fallback（¶4–¶6）

<div class="compare" markdown="1">

```cpp run ok
#include <compare>
struct Legacy {   // 只有 == 和 <
  int v;
  bool operator==(const Legacy&) const
    = default;
  bool operator<(const Legacy& o) const
    { return v < o.v; }
};
int main() {
  auto r = std::compare_weak_order_fallback(
    Legacy{1}, Legacy{2});
  return std::is_lt(r) ? 0 : 1;
}
```

```cpp run error
#include <compare>
struct Legacy {   // 只有 == 和 <
  int v;
  bool operator==(const Legacy&) const
    = default;
  bool operator<(const Legacy& o) const
    { return v < o.v; }
};
// error: 没有 <=>，无可用方式
auto r = std::weak_order(
  Legacy{1}, Legacy{2});
```

</div>

¶4 `compare_strong_order_fallback(E, F)` 先尝试 `strong_order(E, F)`。不可行时，如果 `E == F` 和 `E < F` 都良构，结果类型能当作 `bool` 使用，就用

```cpp
E == F ? strong_ordering::equal : E < F ? strong_ordering::less : strong_ordering::greater
```

¶5 `compare_weak_order_fallback` 同理。¶6 `compare_partial_order_fallback` 用 `E == F`、`E < F`、`F < E` 三个比较，都为假时得到 `unordered`。

它们让泛型代码同时支持只定义了 `==` 和 `<` 的 C++17 风格类型。代价是 fallback 相信这两个运算符构成了相应的序；如果不是，得到的结果没有意义。

## 类型的全序 `type_order` [compare.type] {{c++26}}

¶1 所有类型之间有一个由实现定义的全序。对任意两个类型 `X`、`Y`（可以是不完整类型），*`TYPE-ORDER`*`(X, Y)` 是一个 `strong_ordering` 类型的常量表达式：`X` 在前为 `less`，`Y` 在前为 `greater`，同一类型为 `equal`。

```cpp
template<class T, class U> struct type_order {
  static constexpr strong_ordering value = TYPE-ORDER(T, U);
  using value_type = strong_ordering;
  constexpr operator value_type() const noexcept { return value; }
  constexpr value_type operator()() const noexcept { return value; }
};
template<class T, class U>
  constexpr strong_ordering type_order_v = type_order<T, U>::value;
```

它的用途是在编译期给类型排序，例如把 `variant<int, double>` 和 `variant<double, int>` 规范化成同一个类型，或者给一组类型生成规范的排列。截至写作时，本机 libc++ 还没有提供 `type_order`。

- 注 1：`int`、`const int`、`int&` 是不同的类型，各有各的位置。
- 注 2：这个顺序不必与 `type_info::before`（[[support.rtti]]）一致。
- 注 3：不同翻译单元的 TU 局部类型之间的顺序无法观察，因为写不出所需的 `type_order` 特化。
- ¶2 声明 `type_order` 的显式特化或偏特化，程序非良构。¶3 可以用不完整类型实例化 `type_order` 和 `type_order_v`。
- ¶4 建议这个顺序对形参类型列表和模板实参列表按字典序排列。

!!! history
    三路比较由 [[P0515R3]] 引入 C++20，[[P0768R1]] 补充了库的部分，也就是 `<compare>` 的大部分内容。[[P1614R2]] 把 `<=>` 推广到整个标准库。早期设计还有 `strong_equality` 和 `weak_equality` 两个类别，[[P1959R0]] 删除了它们，所以今天只剩三个。

## 常见误解

!!! pitfall "`r != 0` 为真，就说明 `r < 0` 或 `r > 0`"
    对 `partial_ordering` 不成立。`unordered != 0` 为真，而 `unordered < 0`、`unordered > 0` 都为假。处理浮点比较结果时要单独考虑 `unordered`。

!!! pitfall "`std::strong_order` 能比较 `int` 和 `long`"
    六个比较算法都要求两个实参退化后的类型相同，`std::strong_order(1, 2L)` 非良构。要比较不同类型，用 `<=>` 或 `std::compare_three_way`。

## 思考题

!!! question "思考题"
    `struct S { float f; std::string s; auto operator<=>(const S&) const = default; };` 的 `<=>` 返回什么类型？`std::three_way_comparable<S, std::weak_ordering>` 成立吗？

<details markdown="1">
<summary>答案</summary>

`float` 的 `<=>` 结果是 `partial_ordering`，`std::string` 的是 `strong_ordering`，公共比较类型取最弱的，所以返回 `std::partial_ordering`（[[class.spaceship]]、[cmp.common]）。`compares-as<partial_ordering, weak_ordering>` 要求 `common_comparison_category_t<partial_ordering, weak_ordering>` 是 `weak_ordering`，实际是 `partial_ordering`，所以概念不成立。
</details>
