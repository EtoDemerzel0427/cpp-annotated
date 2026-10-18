---
title: 比较
summary: <compare> 的全部内容——三种比较类别类型及其"只能与字面量 0 比较"的接口、可替换性、common_comparison_category、three_way_comparable 概念的语义要求、compare_three_way_result，strong_order/weak_order/partial_order 与 fallback 定制点对象（含浮点 totalOrder），以及 C++26 的 type_order
status: done
covers: *
papers: P0515R3, P0768R1, P1614R2, P1959R0
related: expr.spaceship, class.compare, class.spaceship, over.match.oper, comparisons.three.way, concept.totallyordered, customization.point.object, support.limits
tags: 标准库, 三路比较, operator<=>, strong_ordering, 概念
updated: 2026-10-18
---

C++20 的三路比较运算符 `<=>`（[[expr.spaceship]]）返回的不是 `int`，而是三种**比较类别类型**（comparison category types）之一。这些类型由**库**定义，但核心语言直接引用它们：内建 `<=>` 的结果类型、默认 `operator<=>` 的返回类型推导（[[class.spaceship]]）、重写候选（[[over.match.oper]]）都依赖于本节。¶1（[compare.syn]）：`<compare>` 规定了主要与三路比较运算符配合使用的类型、对象和函数。整个头文件是 freestanding 的。

!!! warning "必须包含 `<compare>`"
    [[expr.spaceship]] 规定：比较类别类型不是预定义的，如果在使用需要它们的 `<=>`（包括内建的 `a <=> b`）之前没有包含 `<compare>`（或 `import std;`），程序非良构。

本节的结构：

| 子条款 | 内容 |
|---|---|
| [cmp.categories] | `partial_ordering`、`weak_ordering`、`strong_ordering` |
| [cmp.common] | `common_comparison_category` |
| [cmp.concept] | `three_way_comparable`、`three_way_comparable_with` |
| [cmp.result] | `compare_three_way_result` |
| [cmp.alg] | `strong_order` 等六个定制点对象 |
| [compare.type] | `type_order` {{c++26}} |

函数对象 `std::compare_three_way` 在 `<compare>` 中声明，但规格在工具库的 [[comparisons.three.way]]。

## 比较类别类型（[cmp.categories]）

### 共同框架（[cmp.categories.pre]）

¶1：三个类型统称**比较类别类型**。每个都以一个仅用于说明的数据成员 `value` 来规定，其值通常对应以下仅用于说明的枚举之一：

```cpp
enum class ord  { equal = 0, equivalent = equal, less = -1, greater = 1 };  // exposition only
enum class ncmp { unordered = -127 };                                       // exposition only
```

¶2 注 1：`strong_ordering` 对应数学上的**全序**（total ordering）。

¶3 是这些类型接口最奇特的地方：

!!! std
    The relational and equality operators for the comparison category types are specified with an anonymous parameter of unspecified type. This type shall be selected by the implementation such that these parameters can accept literal `0` as a corresponding argument. In this context, the behavior of a program that supplies an argument other than a literal `0` is undefined.

    比较类别类型的关系与相等运算符以一个**未指明类型**的匿名形参来规定。实现选择的类型必须使这些形参能接受**字面量 `0`**。在此语境下，提供字面量 `0` 以外的实参，程序的行为是**未定义的**。

也就是说，比较类别类型的值**只能与字面量 `0` 比较**：`r < 0`、`r == 0`、`0 > r`。`r < 1`、`r == zero_variable` 都是 UB——标准不要求诊断。这是一个刻意的设计：让比较结果看起来像旧式 `strcmp` 的返回值（"小于 0 表示小于"），同时阻止人们把它当成整数来用。例 1 指出 `nullptr_t` 满足要求（`0` 可以转换为 `nullptr_t`）。

!!! impl "libc++ 把 UB 变成了编译错误"
    libc++ 的未指明类型是 `_CmpUnspecifiedParam`，它有一个 `consteval` 构造函数模板，只接受 `int`，并用 Clang 的 `__attribute__((enable_if(__zero == 0, ...)))` 要求实参为 0。`consteval` 保证实参必须是常量表达式。于是 `r < 1` 和 `r < z`（`z` 是 `int` 变量）都在编译期报错，`r < nullptr` 也会报错（类型不是 `int`）——比标准要求的更严格，但这正是标准用 UB 留出的空间。

¶4 定义了**可替换性**（[[g:substitutability]]）：若 `a == b` 为真时 `f(a) == f(b)` 总为真，其中 `f` 是只读取"比较显著"（comparison-salient）状态的函数，这些状态可经由实参的公开 `const` 成员访问。可替换性是区分 `strong` 与 `weak` 的标准。

### 三种类型的语义

| 类型 | 有效值 | 适用于 | 相等是否意味着可替换 | 是否允许不可比较 |
|---|---|---|---|---|
| `partial_ordering` | `less`、`equivalent`、`greater`、`unordered` | 例如浮点数（NaN） | 否 | **是** |
| `weak_ordering` | `less`、`equivalent`、`greater` | 例如大小写不敏感的字符串 | 否 | 否 |
| `strong_ordering` | `less`、`equal`、`equivalent`、`greater` | 例如整数、指针 | **是** | 否 |

`strong_ordering::equal` 与 `strong_ordering::equivalent` 是**同一个值**（`ord::equivalent = equal`），两个名字只是为了在泛型代码中统一。

[cmp.partialord] ¶1 脚注 169："即 `a < b`、`a == b`、`a > b` 可能**全都为假**"。对 `partial_ordering` 的比较运算符，¶2 规定 `v @ 0` 返回 `v.is-ordered && v.value @ 0`——`unordered` 与 0 的任何比较（包括 `==`）都为假，只有 `!=` 为真（由 `==` 重写而来）。

```cpp run title="partial-ordering.cpp" ok
#include <compare>
#include <limits>

int main() {
    double nan = std::numeric_limits<double>::quiet_NaN();
    auto r = 1.0 <=> nan;                                    // 内建 <=>：浮点数结果为 partial_ordering
    bool ok = r == std::partial_ordering::unordered
           && !(r < 0) && !(r == 0) && !(r > 0) && (r != 0);  // 全部为假，只有 != 为真
    return ok ? 0 : 1;
}
```

### 转换与反转

- **隐式转换只能从强到弱**：`strong_ordering` → `weak_ordering` → `partial_ordering`。转换结果按 `value` 的符号映射（[cmp.weakord] ¶2，[cmp.strongord] ¶2–¶3）。反方向没有转换——你无法把 `partial_ordering` 变成 `strong_ordering`，因为 `unordered` 无处安放。
- **`0 <=> v` 反转比较结果**：`v < 0 ? greater : v > 0 ? less : v`（[cmp.partialord] ¶5 等）。这是 [[over.match.oper]] 中**合成候选**（对 `a < b` 用 `0 < (b <=> a)` 实现）的基础。`v <=> 0` 则原样返回 `v`。
- `is_eq`、`is_neq`、`is_lt`、`is_lteq`、`is_gt`、`is_gteq`（[compare.syn]）：命名比较函数，接受 `partial_ordering`（另外两种可隐式转换过来），等价于与 0 比较。在需要函数对象（如传给算法）时比 lambda 更简洁。

## `common_comparison_category`（[cmp.common]）

```cpp
template<class... Ts> struct common_comparison_category { using type = /* see below */; };
template<class... Ts> using common_comparison_category_t = typename common_comparison_category<Ts...>::type;
```

¶1：提供**所有模板实参都能转换到的最强比较类别**。注 1：一个比较类别类型比另一个"更强"，如果二者不同且前者的实例可以转换为后者。

¶2 *Remarks*：成员 `type` 是 `Ts...` 的**公共比较类型**（[[g:common-comparison-type]]，[[class.spaceship]]）；若 `Ts` 中有任何元素不是比较类别类型，则为 `void`。注 2：包展开为空时是 `std::strong_ordering`。

规则（来自 [[class.spaceship]]）简单说就是"取最弱"：任何一个是 `partial_ordering` → `partial_ordering`；否则任何一个是 `weak_ordering` → `weak_ordering`；否则 → `strong_ordering`。它正是默认 `auto operator<=>(...) = default;` 推导返回类型的方法：取所有成员 `<=>` 结果的公共比较类型。

```cpp run title="common-category.cpp" ok
#include <compare>
#include <type_traits>

using std::common_comparison_category_t;
static_assert(std::is_same_v<common_comparison_category_t<std::strong_ordering, std::weak_ordering>,
                             std::weak_ordering>);
static_assert(std::is_same_v<common_comparison_category_t<std::strong_ordering, std::partial_ordering>,
                             std::partial_ordering>);
static_assert(std::is_same_v<common_comparison_category_t<>, std::strong_ordering>);    // 注 2
static_assert(std::is_same_v<common_comparison_category_t<std::strong_ordering, int>, void>);

struct P { int i; double d; auto operator<=>(const P&) const = default; };
static_assert(std::is_same_v<decltype(P{} <=> P{}), std::partial_ordering>);           // int 强、double 偏 → 偏

int main() {}
```

## `three_way_comparable` 概念（[cmp.concept]）

```cpp
template<class T, class Cat = partial_ordering>
  concept three_way_comparable =
    weakly-equality-comparable-with<T, T> &&
    partially-ordered-with<T, T> &&
    requires(const remove_reference_t<T>& a, const remove_reference_t<T>& b) {
      { a <=> b } -> compares-as<Cat>;
    };
```

*`compares-as<T, Cat>`* 要求 `common_comparison_category_t<T, Cat>` 就是 `Cat`——即 `T` 至少和 `Cat` 一样强。所以 `three_way_comparable<double>` 成立，`three_way_comparable<double, std::weak_ordering>` 不成立。

和所有标准概念一样，它分为**语法要求**（`requires` 表达式，编译器检查）和**语义要求**（"T models ... only if"，编译器不检查）。¶2 的语义要求：`a <=> b` 的结果必须与 `==`、`!=`、`<`、`>`、`<=`、`>=` 的结果**一致**（¶2.1–¶2.7），反转对称（¶2.3），并且若 `Cat` 可转换为 `strong_ordering`，`T` 还必须 model `totally_ordered`（¶2.8，[[concept.totallyordered]]）。

一个类型满足语法要求但不 model 语义要求时，使用依赖该概念的标准库组件，按 [[res.on.requirements]] 是未定义行为（或者说程序的行为不受保证）。例如一个 `<=>` 与 `<` 结果不一致的类型，满足 `three_way_comparable` 的语法检查，但不 model 它。

*`partially-ordered-with<T, U>`* 要求八个关系运算（`t < u`、`u < t`……）都可用，¶1 的语义要求它们具有相同的域且互为镜像（`t < u` 当且仅当 `u > t`……）。`three_way_comparable_with<T, U, Cat>`（¶3）额外要求 `T` 与 `U` 有公共引用类型，并且混合比较的结果与转换到公共类型后比较的结果相同（¶3.5）。

## `compare_three_way_result`（[cmp.result]）

¶2：令 `t`、`u` 为 `const remove_reference_t<T>` 和 `const remove_reference_t<U>` 类型的左值。若 `t <=> u` 作为不求值操作数是良构的，成员 `type` 为 `decltype(t <=> u)`；否则**没有**成员 `type`（SFINAE 友好）。¶1：程序为 `compare_three_way_result` 添加特化，行为未定义。

注意它查询的是**`const` 左值**之间的比较。一个只有非 `const` `operator<=>` 的类型，`compare_three_way_result_t` 不存在。

## 比较算法：六个定制点对象（[cmp.alg]）

`strong_order`、`weak_order`、`partial_order`、`compare_strong_order_fallback`、`compare_weak_order_fallback`、`compare_partial_order_fallback` 都是**定制点对象**（[[customization.point.object]]）：它们是函数对象，调用时按固定顺序尝试一系列方案，选中第一个良构的。不良构的情况在模板实例化的直接语境中表现为替换失败（注 1–注 6）。

所有六个都首先要求两个实参**退化后的类型相同**（¶1.1 等），否则非良构——它们不做混合类型比较。

### `strong_order(E, F)`（¶1）

按顺序尝试：

1. ¶1.2 经**仅 ADL**查找找到的 `strong_order(E, F)`，结果转换为 `strong_ordering`——这是用户定制的入口；
2. ¶1.3 若 `E` 的类型 `T` 是**浮点类型**：产生一个与 `T` 的比较运算符所观察到的顺序一致的 `strong_ordering`；若 `numeric_limits<T>::is_iec559` 为真，还要与 ISO/IEC 60559 的 **totalOrder** 操作一致；
3. ¶1.4 `strong_ordering(compare_three_way()(E, F))`，若良构；
4. 否则非良构。

¶1.3 是最有价值的部分：浮点数的内建 `<=>` 只给出 `partial_ordering`（NaN 不可比较、`-0.0 == +0.0`），无法用于需要全序的场合（例如对含 NaN 的数组排序、作为 `std::map` 的键）。IEEE 754 的 totalOrder 给出一个全序：`-NaN < -Inf < 负数 < -0 < +0 < 正数 < +Inf < +NaN`，并且区分不同 payload 的 NaN。

### `weak_order(E, F)`（¶2）

与 `strong_order` 类似，但浮点情形（¶2.3）要求与以下**等价类**（从小到大）一致：所有负 NaN；负无穷；每个负规格化数；每个负次正规数；**两个零一起**；每个正次正规数；每个正规格化数；正无穷；所有正 NaN。于是 `weak_order(-0.0, +0.0)` 为 `equivalent`，所有正 NaN 彼此等价。没有其他方案时，退回到 `weak_ordering(strong_order(E, F))`（¶2.5）。

### `partial_order(E, F)`（¶3）

依次尝试 ADL 定制、`compare_three_way()(E, F)`、`weak_order(E, F)`。

```cpp run title="cmp-alg.cpp" ok
#include <compare>
#include <limits>

int main() {
    double nan = std::numeric_limits<double>::quiet_NaN();
    bool ok =
        ((-0.0 <=> 0.0) == 0)                   // 内建：-0 与 +0 等价
     && (std::strong_order(-0.0, 0.0) < 0)      // totalOrder：-0 < +0
     && (std::strong_order(nan, nan) == 0)      // 同一 NaN 位模式：相等
     && (std::weak_order(-0.0, 0.0) == 0)       // 弱序：两个零在同一等价类
     && (std::strong_order(1.0, nan) < 0);      // +NaN 大于一切正数
    return ok ? 0 : 1;
}
```

### 三个 fallback（¶4–¶6）

`compare_strong_order_fallback(E, F)` 先尝试 `strong_order(E, F)`；不行的话，若 `E == F` 和 `E < F` 都良构且结果类型 model *boolean-testable*，则用

```cpp
E == F ? strong_ordering::equal : E < F ? strong_ordering::less : strong_ordering::greater
```

（`E`、`F` 各只求值一次）。`compare_weak_order_fallback` 同理。`compare_partial_order_fallback` 需要 `E == F`、`E < F`、`F < E` 三者，都不成立时得到 `unordered`。

它们的用途是让泛型代码可以**同时支持新旧类型**：只定义了 `==` 和 `<` 的 C++17 风格类型，也能得到一个三路比较结果。代价是：fallback 版本**相信**你的 `==` 和 `<` 构成了相应的序——如果它们不是，结果没有意义。

```cpp run title="fallback.cpp" ok
#include <compare>

struct Legacy {                                    // C++17 风格：只有 == 和 <
    int v;
    bool operator==(const Legacy&) const = default;
    bool operator<(const Legacy& o) const { return v < o.v; }
};

int main() {
    // std::weak_order(Legacy{1}, Legacy{2});                         // error: 没有 <=>，无可用方案
    auto r = std::compare_weak_order_fallback(Legacy{1}, Legacy{2});  // 用 == 和 < 合成
    return std::is_lt(r) ? 0 : 1;
}
```

!!! history "历史"
    三路比较由 [[P0515R3]] 引入 C++20；[[P0768R1]] 补充了库的支持（`<compare>` 的大部分内容）。C++20 后期的 [[P1614R2]]（"The Mothership Has Landed"）把 `<=>` 推广到整个标准库；[[P1959R0]] 删除了早期设计中的 `strong_equality`、`weak_equality` 两个类别——今天只剩三个比较类别。

## 类型排序 `type_order`（[compare.type]）{{c++26}}

¶1：所有类型之间存在一个**由实现定义的全序**。对任意（可能不完整的）类型 `X` 和 `Y`，*`TYPE-ORDER`*`(X, Y)` 是一个 `strong_ordering` 类型的常量表达式：`X` 在前为 `less`，`Y` 在前为 `greater`，同一类型为 `equal`。

```cpp
template<class T, class U> struct type_order {
  static constexpr strong_ordering value = TYPE-ORDER(T, U);
  using value_type = strong_ordering;
  constexpr operator value_type() const noexcept { return value; }
  constexpr value_type operator()() const noexcept { return value; }
};
template<class T, class U> constexpr strong_ordering type_order_v = type_order<T, U>::value;
```

- 注 1：`int`、`const int`、`int&` 是不同的类型，各有其位置。
- 注 2：这个顺序**不必**与 `type_info::before` 一致（[[support.rtti]]）——后者是运行期的、可能随执行而变的；`type_order` 是编译期常量。
- 注 3：来自不同翻译单元的 TU 局部类型之间的顺序不可观察，因为无法写出需要的 `type_order` 特化。
- ¶2：声明 `type_order` 的显式或偏特化，程序非良构。¶3：可以用不完整类型实例化。
- ¶4 推荐实践：顺序应当按形参类型列表和模板实参列表做字典序。

主要用途是**编译期类型排序**：例如把 `variant<int, double>` 和 `variant<double, int>` 规范化成同一个类型，或者为类型集合生成规范形式。截至本文编写时，libc++ 尚未提供 `type_order`。

## 小结

!!! summary
    - 三个比较类别：`partial_ordering`（允许不可比较）、`weak_ordering`（等价不意味着可替换）、`strong_ordering`（相等意味着可替换，即全序）。
    - 比较类别的值只能与字面量 `0` 比较，其他实参是 UB（libc++ 直接报错）。
    - 转换只能从强到弱；`0 <=> v` 反转结果，支撑重写候选。
    - `common_comparison_category` 取最弱的公共类别，非类别类型得 `void`，空包得 `strong_ordering`。
    - `three_way_comparable` 有语法与语义两层要求；`compare_three_way_result` 查询 `const` 左值的 `<=>` 结果。
    - `strong_order`/`weak_order` 为浮点数提供 IEEE totalOrder 全序与弱序；fallback 版本用 `==` 和 `<` 合成三路结果。
    - C++26 的 `type_order` 给出所有类型上的编译期全序。
