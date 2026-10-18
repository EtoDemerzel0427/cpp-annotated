---
title: 逻辑运算符特征
summary: conjunction / disjunction / negation——对 trait 做与、或、非；前两者保证"短路实例化"（遇到决定性的 Bi 就不再实例化后面的 Bj::value），并以那个 Bi 本身（而不一定是 true_type/false_type）作为基类
status: draft
covers: meta.logical
papers: P0013R1
related: type.traits, meta.help, temp.inst, expr.log.and, expr.prim.fold, temp.constr
tags: 标准库, type_traits, 短路, 元编程
updated: 2026-10-18
---

[meta.logical] 提供三个"作用于 trait 的逻辑运算符"：`conjunction`（与）、`disjunction`（或）、`negation`（非）。它们由 [[P0013R1]] 在 C++17 加入。¶1 说明本子条款描述的是把逻辑运算应用于其他类型特征的 trait。

既然 C++17 同时有了折叠表达式，为什么还需要它们？答案只有一个词：**短路实例化**。

## `conjunction`：短路的"与"（¶2–¶6）

```cpp
template<class... B> struct conjunction : /* see below */ { };
```

!!! std
    For a specialization `conjunction<B1, …, BN>`, if there is a template type argument `Bi` for which `bool(Bi::value)` is `false`, then instantiating `conjunction<B1, …, BN>::value` does not require the instantiation of `Bj::value` for `j > i`.

    对特化 `conjunction<B1, …, BN>`，若存在某个模板类型实参 `Bi` 使 `bool(Bi::value)` 为假，则实例化 `conjunction<B1, …, BN>::value` 时**不需要**实例化 `j > i` 的 `Bj::value`。

注 1 把它类比为内建 `&&` 的短路求值（[[expr.log.and]]）。这里"短路"的对象不是运行期求值，而是**模板实例化**——而实例化可能失败（硬错误）、可能很昂贵、可能产生副作用（如友元注入）。

```cpp run title="short-circuit.cpp" ok
#include <type_traits>

template<class T>
struct Bad {                     // 一旦实例化就是硬错误
    static_assert(sizeof(T) == 0, "instantiated!");
    static constexpr bool value = true;
};

static_assert(!std::conjunction_v<std::false_type, Bad<int>>);   // Bad<int> 不会被实例化
static_assert( std::disjunction_v<std::true_type, Bad<int>>);

// template<class... B> constexpr bool fold_and = (B::value && ...);
// static_assert(!fold_and<std::false_type, Bad<int>>);   // error: 折叠表达式要形成每个 B::value

int main() {}
```

折叠表达式 `(B::value && ...)` 的运行期求值当然会短路，但**形成**表达式时就要对每个 `B` 查找 `B::value`，这会隐式实例化每个 `B`（[[temp.inst]]）。这就是 `conjunction` 存在的理由：典型场景是 `conjunction<is_reference<T>, is_constructible<Foo, T>>`，当第一项为假时，第二项可能涉及不完整类型或会触发硬错误。

### 基类不一定是 `true_type`/`false_type`（¶5）

!!! std
    The specialization `conjunction<B1, …, BN>` has a public and unambiguous base that is either the first type `Bi` in the list `true_type, B1, …, BN` for which `bool(Bi::value)` is `false`, or if there is no such `Bi`, the last type in the list.

    `conjunction<B1, …, BN>` 有一个公开且无歧义的基类：它是列表 `true_type, B1, …, BN` 中第一个使 `bool(Bi::value)` 为假的 `Bi`；若没有这样的 `Bi`，则是列表中的最后一个类型。

注 2：这意味着 `conjunction` 的特化**不一定**派生自 `true_type` 或 `false_type`。几个推论：

- `conjunction<>` 的列表只有 `true_type`，所以 `conjunction_v<>` 为真；
- `conjunction<A, B>` 全为真时，基类是**最后一个** `B`——`conjunction<std::integral_constant<int, 7>>::value` 的类型是 `const int`，值为 7；
- 遇到第一个为假的 `Bi` 时，基类就是那个 `Bi` 本身——它的所有成员（不只是 `value`）都透过来。

¶6：基类的成员名（除了 `conjunction` 和 `operator=`）不得被隐藏，且在 `conjunction` 中无歧义可用。这里排除 `conjunction` 是因为注入类名本来就会遮住基类的注入类名，排除 `operator=` 是因为每个类都有自己隐式声明的赋值运算符。

```cpp run title="conjunction-base.cpp" ok
#include <type_traits>

using Zero  = std::integral_constant<int, 0>;
using Seven = std::integral_constant<int, 7>;

static_assert( std::conjunction_v<>);                                          // 只有 true_type
static_assert( std::is_base_of_v<Zero, std::conjunction<std::true_type, Zero, Seven>>);   // 第一个为假的
static_assert( std::is_same_v<decltype(std::conjunction<Seven>::value), const int>);     // 全真：最后一个
static_assert( std::conjunction<Seven>::value == 7);

int main() {}
```

### 对实参的要求（¶4）

每个**被实例化了 `::value`** 的 `Bi` 必须：可以作为基类使用、有一个可转换为 `bool` 的成员 `value`、该成员未被隐藏且无歧义可用。注意"被实例化了"这个限定——被短路跳过的 `Bj` 不受约束。

"可以作为基类"排除了 `final` 类：本地 libc++ 对 `struct F final : std::true_type {}; conjunction_v<F>` 报错 "base 'F' is marked 'final'"——因为按 ¶5，`conjunction<F>` 要以 `F` 为基类。

## `disjunction`：短路的"或"（¶7–¶11）

与 `conjunction` 完全对称：

- ¶8：若某个 `Bi` 的 `bool(Bi::value)` 为真，则不需要实例化 `j > i` 的 `Bj::value`（注 3：类比 `||`）；
- ¶10：基类是列表 `false_type, B1, …, BN` 中第一个使 `bool(Bi::value)` 为真的 `Bi`，若没有则为最后一个；因此 `disjunction_v<>` 为假；
- ¶9、¶11：对实参的要求与成员可见性同 `conjunction`。

`disjunction` 有一个常被忽视的用法：**编译期的"查找第一个满足条件的元素"**。因为它的基类就是第一个为真的 `Bi`，如果每个 `Bi` 都携带额外的成员（如 `using type = ...`），`disjunction<...>::type` 就取出了"第一个匹配项"的附加信息。

```cpp run title="disjunction-find.cpp" ok
#include <type_traits>

template<class T>
struct Match : std::is_integral<T> { using type = T; };   // 注意：这个 type 遮住了基特征的 type

using First = std::disjunction<Match<float>, Match<long>, Match<int>>::type;
static_assert(std::is_same_v<First, long>);   // 基类是第一个为真的 Match<long>

int main() {}
```

## `negation`（¶12）

```cpp
template<class B> struct negation : bool_constant<!bool(B::value)> { };
```

`negation<B>` 是一个 *Cpp17UnaryTypeTrait*，基特征为 `bool_constant<!bool(B::value)>`。它总是派生自 `true_type` 或 `false_type`，并且**会**实例化 `B::value`。它的意义在于把 `!` 也表达为一个**类型**，从而可以放进 `conjunction`/`disjunction` 的实参列表里参与短路：`conjunction<is_class<T>, negation<is_final<T>>>`。

## 实现视角

!!! impl "libc++ 的 `conjunction` 与内部的 `_And`"
    libc++ 的实现几乎就是 ¶5 的直译：

    ```cpp
    template <class...>
    struct conjunction : true_type {};
    template <class _Arg>
    struct conjunction<_Arg> : _Arg {};
    template <class _Arg, class... _Args>
    struct conjunction<_Arg, _Args...>
        : conditional_t<!bool(_Arg::value), _Arg, conjunction<_Args...>> {};
    ```

    `conditional_t` 的两个分支都会被**命名**，但 `conjunction<_Args...>` 只是被命名、不会被**实例化**——除非它被选中作为基类。这就是短路的来源：递归在第一个为假的 `_Arg` 处停止实例化。

    libc++ 内部另有一个 `_And<_Pred...>`，用 `decltype(__and_helper<_Pred...>(0))` 和 `enable_if` 的 SFINAE 实现。源码注释指出：`_And` 是别名，会**立即**求值（但仍然短路），而 `conjunction` 是类模板，只有在实例化时才求值；要推迟求值时用 `conjunction`。

## 与概念的关系

在 `requires` 子句和概念定义中，`&&` 和 `||` 构成的是**合取/析取约束**（[[temp.constr]]），约束满足性检查本身就是短路的：`std::is_integral_v<T> && Bad<T>::value` 作为约束，`T = double` 时不会实例化 `Bad<double>`。因此在 C++20 的约束里通常不需要 `conjunction`；它的主战场是**类型计算**（基类列表、`enable_if` 实参、`static_assert`）。

## 思考题

!!! question "思考题"
    `std::conjunction<std::is_integral<T>, std::is_signed<T>>` 与 `std::bool_constant<std::is_integral_v<T> && std::is_signed_v<T>>` 有什么可观察的区别？

<details markdown="1">
<summary>展开查看答案与解析</summary>

1. **基类不同**：前者的基类是 `is_integral<T>`（若其为假）或 `is_signed<T>`（否则），不是 `true_type`/`false_type`；后者恰好是 `bool_constant`。所以 `std::is_same_v<..., std::true_type>` 对前者恒为假。
2. **实例化不同**：前者在 `is_integral<T>` 为假时不实例化 `is_signed<T>::value`；后者形成 `std::is_signed_v<T>` 时必然实例化它。对这两个特定 trait 而言无害，但若第二项可能硬错误，只有前者安全。
3. 二者作为类型是不同的，但 `::value` 相同。
</details>

## 小结

| 模板 | 短路 | 基类 | 空包 |
|---|---|---|---|
| `conjunction<B...>` | 第一个为假即停止实例化 | 第一个为假的 `Bi`，否则最后一个 | `true_type` |
| `disjunction<B...>` | 第一个为真即停止实例化 | 第一个为真的 `Bi`，否则最后一个 | `false_type` |
| `negation<B>` | — | `bool_constant<!bool(B::value)>` | — |
