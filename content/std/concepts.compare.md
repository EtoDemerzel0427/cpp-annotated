---
title: 比较概念
summary: equality_comparable、totally_ordered 及其跨类型版本要求什么；它们依赖的两个说明专用概念 boolean-testable（比较结果像 bool 一样可用）和 comparison-common-type-with（两种类型在同一个值域里比较）。
status: done
covers: *
since: c++20
papers: P0898R3, P1964R2, P2404R3
related: concepts, concepts.lang, cmp.concept, class.compare, expr.log.and, expr.log.or, over.match.oper, basic.lookup.argdep
tags: 标准库, 概念, 比较, boolean-testable, equality_comparable, totally_ordered
updated: 2026-10-19
---

!!! tldr
    - `equality_comparable<T>` 要求 `==` 精确反映值的相等，因此 `==` 必须是等价关系。
    - 跨类型的 `equality_comparable_with<T, U>` 和 `totally_ordered_with<T, U>` 还要求：直接比较 `t` 和 `u` 的结果，与把两者转换到公共类型后再比较的结果一致。
    - 比较结果不必是 `bool`，但必须是 *boolean-testable* 的：能转换为 `bool`，`!` 是取反，并且 `&&`、`||` 不会被用户重载劫持。最后一条编译器不检查。
    - `totally_ordered<T>` 要求三歧性：任意两个值恰有 `<`、`>`、`==` 之一成立。`double` 也建模它，因为 NaN 不在定义域内。

[concepts.compare] 描述在可能不同的对象类型的值之间建立关系和顺序的概念（[concepts.compare.general] ¶1）。公开的概念只有四个：`equality_comparable`、`equality_comparable_with`、`totally_ordered`、`totally_ordered_with`。它们依赖两个**说明专用**（exposition-only）的概念，即只在标准里用来写规格、程序不能直接使用的概念：

- *boolean-testable*：比较的结果像 `bool` 一样可用是什么意思；
- *comparison-common-type-with*：两种类型的值在同一个值域里比较是什么意思。

`<compare>` 的 `three_way_comparable`（[[cmp.concept]]）也用到这两个概念。下文的满足、建模、保持相等性等词见 [[concepts]]，公共引用见 [[concept.commonref]]。

## 比较结果要像 `bool`：*boolean-testable*

### 问题：能转换为 `bool` 还不够

```cpp run title="hijacked-and.cpp" ok
#include <concepts>
#include <cstdio>

struct Weird {   // == 的结果类型，重载了 &&
  bool b;
  operator bool() const { return b; }
  friend Weird operator&&(Weird, Weird) {
    std::puts("user &&");
    return {false};
  }
};
struct X {
  int v;
  friend Weird operator==(X a, X b) { return {a.v == b.v}; }
  friend Weird operator!=(X a, X b) { return {a.v != b.v}; }
};
static_assert(std::equality_comparable<X>);   // 满足

int main() {
  X a{1}, b{1};
  if (a == b && a == b) std::puts("true");
  else std::puts("false");   // 打印 user && 和 false
}
```

泛型代码对比较结果做的事不只是 `if (a == b)`，还有 `!(a < b) && pred(x)`、`a == b || c == d`。如果 `==` 返回的类型重载了 `&&`，这些表达式会调用用户的函数：失去短路求值（[[expr.log.and]]），结果也可能毫无布尔含义。`X` 的 `==` 返回的 `Weird` 能转换为 `bool`，却让 `a == b && a == b` 得到了 `false`。

¶1 说明 *boolean-testable* 描述的就是这样的表达式：能转换为 `bool`，并且逻辑运算符 `&&`、`||`、`!` 具有常规的含义。

### 编译器检查的部分（¶1、¶6）

```cpp
template<class T>
  concept boolean-testable-impl = convertible_to<T, bool>;  // exposition only

template<class T>
  concept boolean-testable =                                  // exposition only
    boolean-testable-impl<T> && requires(T&& t) {
      { !std::forward<T>(t) } -> boolean-testable-impl;
    };
```

编译器只检查两件事：`T` 能隐式且显式地转换为 `bool`，`!t` 的结果也能转换为 `bool`。`&&` 和 `||` 不在语法要求里，因为"这个调用必须选中内建运算符"无法写成 requires 表达式。它们被放进了语义要求，所以上面的 `X` 满足 `equality_comparable`，但不建模它。

`!` 被删除的类型连语法都不满足：

```cpp run title="no-bang.cpp" ok
#include <concepts>

struct NoBang {
  operator bool() const { return true; }
  void operator!() const = delete;
};
struct Y {
  friend NoBang operator==(Y, Y) { return {}; }
  friend NoBang operator!=(Y, Y) { return {}; }
};
static_assert(!std::equality_comparable<Y>);

int main() {}
```

### 不检查的部分：取消资格的声明（¶2–¶5）

¶2 设 `e` 是 `decltype((e))` 为 `T` 的表达式。`T` 建模 *boolean-testable-impl* 需要：

- ¶2.1 `remove_cvref_t<T>` 不是类类型，或者在它的作用域中查找 `operator&&` 和 `operator||` 什么也找不到，即没有成员形式的重载；
- ¶2.2 以 `T` 为唯一实参类型，对 `operator&&` 和 `operator||` 做实参依赖查找（[[basic.lookup.argdep]]），找不到任何**取消资格的声明**（disqualifying declaration）。

取消资格的声明由三个层层递进的定义刻画。大意是：凡是有可能接受 `e` 作为操作数的 `&&`、`||` 重载，都会取消 `T` 的资格。

1. ¶3 **取消资格的形参**：声明类型为 `P` 的函数形参，满足下列之一。
    - ¶3.1 `P` 不依赖模板参数，且存在从 `e` 到 `P` 的隐式转换序列（[[over.best.ics]]）；
    - ¶3.2 `P` 依赖模板参数，并且 `P` 中没有参与推导的模板参数，或者以 `e` 为实参的模板实参推导（[[temp.deduct.call]]）成功。
2. ¶4 **关键形参**（key parameter）：函数模板 `D` 中类型为 `cv X` 或其引用的形参，其中 `X` 是某个类模板的特化，该类模板与 `D` 的最内层非内联命名空间相同，且 `X` 至少含一个参与推导的模板参数。例 1 里 `Z::operator&&(C<T> x, T y)` 有一个关键形参 `C<T> x`；`Z::operator||(C<type_identity_t<T>> x, T y)` 没有，因为 `type_identity_t<T>` 不参与推导。
3. ¶5 **取消资格的声明**：至少含一个取消资格形参的非模板函数声明（¶5.1）；或者至少含一个取消资格形参的函数模板声明，并且满足下列之一（¶5.2）：某个取消资格形参是关键形参，声明没有关键形参，或者它声明的函数模板没有绑定任何名字（[[dcl.meaning]]）。

¶6 注 1 说明了意图：对两个都建模 *boolean-testable-impl* 的类型 `T1`、`T2`，`declval<T1>() && declval<T2>()` 和 `||` 必须决议到内建运算符。

规则写得这么绕，是因为概念只拿到一个类型 `T`，看不到另一个操作数的类型。¶2–¶5 是只看一个类型的保守近似：只要与 `T` 相关的某个重载有可能在与其他类型组合时被选中，就取消 `T` 的资格。关键形参的规则用来避免误伤：像 `Z::operator&&(C<T>, T)` 这种只对某个类模板的特化起作用的运算符，如果 `e` 推导不出 `C<T>`，就不算数。

### `!` 必须是取反（¶7–¶8）

¶7 `T` 建模 *boolean-testable* 还需要 `bool(e) == !bool(!e)`。¶8 例 2 列出了建模它的类型：`bool`、`true_type`、`int*`、`bitset<N>::reference`。

!!! history
    *boolean-testable* 由 [[P1964R2]] 在 C++20 发布前引入，取代了早期草案中一个公开的概念 `boolean`。旧概念试图用语法要求穷举 `&&`、`||`、`!`、`==`、`!=` 在各种类型组合下的结果，定义庞大、编译慢，仍然拦不住 `&&` 被重载。新方案把语法要求压到最小，把不得劫持写成语义要求，并且不再公开。

## 跨类型比较的公共值域：*comparison-common-type-with*

`std::string` 和 `const char*` 可以用 `==` 比较。这个比较应该是什么含义？标准的回答是：它必须与把两边都转换到公共类型 `std::string` 之后再比较的结果一样。*comparison-common-type-with* 规定了这个公共类型要满足什么。

```cpp
template<class T, class U, class C = common_reference_t<const T&, const U&>>
  concept comparison-common-type-with-impl =   // exposition only
    same_as<common_reference_t<const T&, const U&>,
            common_reference_t<const U&, const T&>> &&
    requires {
      requires convertible_to<const T&, const C&> || convertible_to<T, const C&>;
      requires convertible_to<const U&, const C&> || convertible_to<U, const C&>;
    };

template<class T, class U>
  concept comparison-common-type-with =        // exposition only
    comparison-common-type-with-impl<remove_cvref_t<T>, remove_cvref_t<U>>;
```

公共值域 `C` 是 `const T&` 和 `const U&` 的公共引用类型，两边都要能转换到 `const C&`，可以从 const 左值转换，也可以从右值转换。

语义要求里用到的转换写成 *CONVERT_TO_LVALUE*`<C>(E)`（[concepts.compare.general] ¶2）。如果 `static_cast<const C&>(as_const(E))` 有效，就是它（¶2.1）；否则是 `static_cast<const C&>(std::move(E))`（¶2.2）。也就是先尝试不动源对象的转换，不行再从右值转换。

[concept.comparisoncommontype] ¶1 的语义要求与 [[concept.commonref]] 平行：设 `t1`、`t2` 是 `remove_cvref_t<T>` 类型的保持相等性的左值，则 *CONVERT_TO_LVALUE*`<C>(t1)` 等于 *CONVERT_TO_LVALUE*`<C>(t2)` 当且仅当 `t1` 等于 `t2`；对 `U` 一方也一样。转换到公共值域既不能合并不同的值，也不能拆开相等的值。

!!! history "为什么不直接用 `common_reference_with`"
    C++20 最初的 `equality_comparable_with<T, U>` 要求 `common_reference_with<const T&, const U&>`。对 `unique_ptr<int>` 和 `nullptr_t`，公共引用类型是非引用的 `unique_ptr<int>`，从 `const unique_ptr<int>&` 转换过去需要复制，所以只能移动的类型不满足，尽管 `p == nullptr` 显然有意义。C++23 的 [[P2404R3]] 引入了 *comparison-common-type-with* 和 *CONVERT_TO_LVALUE*，把要求放宽为能转换到 `const C&`，并同样修改了 `totally_ordered_with` 和 `three_way_comparable_with`。

## `equality_comparable`（[concept.equalitycomparable]）

### 四个方向（¶1）

```cpp
template<class T, class U>
  concept weakly-equality-comparable-with = // exposition only
    requires(const remove_reference_t<T>& t, const remove_reference_t<U>& u) {
      { t == u } -> boolean-testable;
      { t != u } -> boolean-testable;
      { u == t } -> boolean-testable;
      { u != t } -> boolean-testable;
    };
```

四个方向都要可用，结果都要是 *boolean-testable*。C++20 起有了重写候选（[[over.match.oper]]、[[class.compare]]），只定义一个 `operator==` 就能让四个表达式都有效。

¶1 的语义要求：四个表达式定义域相同（¶1.1）；`u == t` 与 `t == u` 结果相同（¶1.2）；`t != u` 是 `t == u` 的否定（¶1.3）；`u != t` 与 `t != u` 结果相同（¶1.4）。

### `==` 就是相等（¶2–¶3）

```cpp
template<class T>
  concept equality_comparable = weakly-equality-comparable-with<T, T>;
```

!!! std
    T models equality_comparable only if bool(a == b) is true when a is equal to b, and false otherwise.

¶2 这一句把抽象的相等（[[concepts.equality]]）和 `==` 运算符连在一起：`a` 与 `b` 相等时 `a == b` 为真，否则为假。¶3 注 1 补充，`a == b` 被要求保持相等性，由此可推出 `==` 对称且传递；再加上任何值都等于自身，`==` 就是一个等价关系。

这条要求有两个直接的后果：

- `double` 建模 `equality_comparable`。NaN 不在 `==` 的定义域内（[[structure.requirements#8]]），不影响建模，但含 NaN 的数据不能指望依赖这个概念的算法给出有意义的结果。
- 一个忽略大小写比较名字的 `==`，只有当忽略大小写后相同本来就是这个类型的值相等时才建模它。如果某个保持相等性的操作（比如访问器 `name()`）能区分大小写不同的两个对象，`a == b` 为真而 `a.name() != b.name()`，`==` 就不再等同于相等。

### 跨类型版本（¶4）

```cpp
template<class T, class U>
  concept equality_comparable_with =
    equality_comparable<T> && equality_comparable<U> &&
    comparison-common-type-with<T, U> &&
    equality_comparable<common_reference_t<const remove_reference_t<T>&,
                                           const remove_reference_t<U>&>> &&
    weakly-equality-comparable-with<T, U>;
```

跨类型的相等比较不只是有一个 `operator==(T, U)`。两边各自要能比较相等，要有公共值域 `C`，`C` 本身也要能比较相等，最后才是跨类型的四个运算。

¶4 的语义要求：设 `t` 和 `t2` 是表示不同但相等的对象的左值，类型分别是 `const remove_reference_t<T>` 和 `remove_cvref_t<T>`，`u`、`u2` 同理，则

```cpp
bool(t == u) == bool(CONVERT_TO_LVALUE<C>(t2) == CONVERT_TO_LVALUE<C>(u2))
```

这就把 `string == const char*` 的含义固定为按 `string` 的值比较，而不是比较指针。

```cpp run title="equality-comparable-with.cpp" ok
#include <concepts>
#include <cstddef>
#include <memory>
#include <string>
#include <string_view>

using std::equality_comparable_with;

static_assert(equality_comparable_with<
  std::string, const char*>);
static_assert(equality_comparable_with<
  std::string, std::string_view>);
static_assert(!equality_comparable_with<int, std::string>);
// 自 P2404R3 起成立
static_assert(equality_comparable_with<
  std::unique_ptr<int>, std::nullptr_t>);

int main() {}
```

## `totally_ordered`（[concept.totallyordered]）

```cpp
template<class T>
  concept totally_ordered = equality_comparable<T> && partially-ordered-with<T, T>;
```

*partially-ordered-with* 定义在 [[cmp.concept]]：`<`、`>`、`<=`、`>=` 在两个方向上共 8 个表达式都可用，结果是 *boolean-testable*，并且 `t < u` 与 `u > t` 一致、`t <= u` 与 `u >= t` 一致。

¶1 的语义要求：对 `const remove_reference_t<T>` 类型的左值 `a`、`b`、`c`，

- ¶1.1 `bool(a < b)`、`bool(a > b)`、`bool(a == b)` 恰有一个为真，这叫**三歧性**（trichotomy）；
- ¶1.2 `a < b` 且 `b < c` 时 `a < c`；
- ¶1.3 `bool(a <= b) == !bool(b < a)`；
- ¶1.4 `bool(a >= b) == !bool(a < b)`。

三歧性加上 `==` 就是相等，意味着 `<` 是全序：任意两个不相等的值都能分出大小。这比比较器的 `strict_weak_order`（[[concept.strictweakorder]]）严格，后者允许存在不可区分却不相等的元素。

¶2 的 `totally_ordered_with<T, U>` 与 `equality_comparable_with` 结构相同：两边各自全序，能跨类型比较相等，公共值域全序，跨类型的 8 个运算可用。¶2.1–¶2.8 要求每个跨类型的 `<`、`>`、`<=`、`>=` 都与转换到 `C` 后比较的结果一致。

```cpp run title="totally-ordered.cpp" ok
#include <concepts>
#include <cmath>

static_assert(std::totally_ordered<double>);
static_assert(std::totally_ordered_with<int, double>);

int main() {
  double nan = std::nan("");
  // 三个都为 false，违反三歧性，
  // 只说明 NaN 不在定义域内
  return (nan < 1.0 || nan > 1.0 || nan == 1.0) ? 1 : 0;
}
```

## 常见误解

!!! pitfall "比较运算符返回自定义类型"
    表达式模板库（某些线性代数库、SQL DSL）让 `a == b` 返回一个延迟求值的表达式对象，并重载 `&&`、`||` 来拼接表达式。这样的类型可以满足 `equality_comparable`，但几乎不可能建模 *boolean-testable*。把它们交给 `ranges::find`、`ranges::sort` 是 {{ifndr}}（[[res.on.requirements]]）。

!!! pitfall "只写 `operator!=`"
    C++20 的重写候选能从一个 `operator==` 补齐 `!=` 和反方向的比较，所以 *weakly-equality-comparable-with* 通常自动满足。反过来不行：只写 `operator!=` 时，`!=` 不会被用来重写 `==`。

!!! pitfall "跨类型比较与公共类型的结论不一致"
    如果 `S == int` 比较的是 `S::id`，而 `common_reference_t<const S&, const int&>` 经某个转换得到的是别的东西，`equality_comparable_with<S, int>` 就是满足但不建模。为一对类型定义跨类型比较时，要保证它们的公共类型给出同样的结论，或者干脆不提供能产生公共类型的隐式转换。

## 思考题

!!! question "思考题"
    1. *boolean-testable* 为什么只要求 `!t` 的结果能转换为 `bool`，而不要求 `!t` 本身也是 *boolean-testable*？
    2. `std::equality_comparable_with<int, double>` 为真吗？语义要求被建模吗？换成 `long long` 和 `double` 呢？
    3. 一个类型只写了 `auto operator<=>(const S&) const = default;`，没有写 `operator==`，它满足 `totally_ordered` 吗？如果 `operator<=>` 是用户自己实现的呢？

<details markdown="1">
<summary>答案</summary>

1. 递归的定义会无限展开（`!!t`、`!!!t`……）。标准只要求一层，¶7 的 `bool(e) == !bool(!e)` 保证这一层的含义正确。
2. 为真：公共引用类型是 `double`，四个比较都可用。在 `int` 为 32 位时也建模：每个 `int` 都能精确表示为双精度浮点数，转换到 `double` 不合并任何值。`long long` 和 `double` 则不然，超过 2^53 的不同值转换后可能相等，违反 [concept.comparisoncommontype] ¶1。
3. 满足。按 [[class.compare.default]]，预置的 `operator<=>` 会隐式声明一个预置的 `operator==`，于是 `==`、`!=` 以及经 `<=>` 重写的 `<` 等都可用。用户自己实现的 `operator<=>` 不会带来 `operator==`，`equality_comparable` 不满足，`totally_ordered` 也就不满足。
</details>
