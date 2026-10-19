---
title: 逻辑运算符特征
summary: conjunction、disjunction、negation 对类型特征做与、或、非；前两者遇到能决定结果的实参就不再实例化后面的实参，并以那个实参本身作为基类。
status: done
covers: meta.logical
papers: P0013R1
related: type.traits, meta.help, temp.inst, expr.log.and, expr.prim.fold, temp.constr
tags: 标准库, type_traits, 短路, 元编程
updated: 2026-10-19
---

!!! tldr
    - `conjunction` 和 `disjunction` 会短路：遇到第一个能决定结果的实参后，不再实例化后面实参的 `::value`。折叠表达式 `(B::value && ...)` 做不到这一点。
    - `conjunction<B...>` 的基类是第一个为假的 `Bi`，全为真时是最后一个实参，不一定是 `true_type` 或 `false_type`。`disjunction` 对称。
    - 空包时 `conjunction_v<>` 为真，`disjunction_v<>` 为假。
    - `negation<B>` 就是 `bool_constant<!bool(B::value)>`，作用是把取反写成一个类型，放进 `conjunction` 的实参列表。
    - 在 C++20 的约束中，`&&` 和 `||` 本身就短路，通常不需要这些模板。

[meta.logical] 提供三个对其他类型特征做逻辑运算的模板（第 1 段）：`conjunction`（与）、`disjunction`（或）、`negation`（非）。它们在 C++17 由 [[P0013R1]] 加入。

## 为什么不直接用折叠表达式

```cpp run title="short-circuit.cpp" ok
#include <type_traits>

template<class T>
struct Bad {  // 一旦实例化就报错
  static_assert(sizeof(T) == 0, "instantiated!");
  static constexpr bool value = true;
};

static_assert(!std::conjunction_v<std::false_type, Bad<int>>);
static_assert( std::disjunction_v<std::true_type, Bad<int>>);

int main() {}
```

`Bad<int>` 一旦被实例化，其中的 `static_assert` 就会失败。上面两个断言都能通过，因为第一个实参已经决定了结果，`conjunction` 和 `disjunction` 不会去实例化 `Bad<int>`。

换成折叠表达式就不行：

```cpp error
#include <type_traits>

template<class T>
struct Bad {
  static_assert(sizeof(T) == 0, "instantiated!");
  static constexpr bool value = true;
};

template<class... B>
constexpr bool fold_and = (B::value && ...);

static_assert(!fold_and<std::false_type, Bad<int>>);  // error
```

折叠表达式在运行时求值时会短路，但写出 `Bad<int>::value` 这个表达式本身，就需要查找类成员，因而要隐式实例化 `Bad<int>`（[[temp.inst]]）。短路发生在求值阶段，太晚了。

`conjunction` 短路的对象是模板实例化。实例化可能失败，可能代价很高，也可能有副作用，所以这一点有实际意义。典型的用法是 `conjunction<is_reference<T>, is_constructible<Foo, T>>`：第一项为假时，第二项可能涉及不完整类型或会引发错误，此时不应去实例化它。

## `conjunction`

¶2–3 规定：`conjunction<B1, …, BN>` 计算各实参的逻辑与；如果某个 `Bi` 的 `bool(Bi::value)` 为假，实例化 `conjunction<B1, …, BN>::value` 时不需要实例化 `j > i` 的任何 `Bj::value`。注 1 指出，这和内建 `&&` 的短路类似。

### 基类

¶5 不是简单地规定 `conjunction` 派生自 `true_type` 或 `false_type`，而是规定它的基类：

!!! std
    The specialization `conjunction<B1, …, BN>` has a public and unambiguous base that is either the first type `Bi` in the list `true_type, B1, …, BN` for which `bool(Bi::value)` is `false`, or if there is no such `Bi`, the last type in the list.

也就是说，在列表 `true_type, B1, …, BN` 中找第一个值为假的类型，它就是基类；找不到就以最后一个类型为基类（注 2）。由此可以推出：

- `conjunction<>` 的列表里只有 `true_type`，所以 `conjunction_v<>` 为真。
- 遇到第一个为假的 `Bi` 时，基类就是 `Bi` 本身，`Bi` 的全部成员都能通过 `conjunction` 访问，不只是 `value`。
- 全为真时，基类是最后一个实参。`conjunction<integral_constant<int, 7>>::value` 的类型是 `const int`，值是 7。

```cpp run title="conjunction-base.cpp" ok
#include <type_traits>

using Zero  = std::integral_constant<int, 0>;
using Seven = std::integral_constant<int, 7>;
using C = std::conjunction<std::true_type, Zero, Seven>;

static_assert(std::conjunction_v<>);
static_assert(std::is_base_of_v<Zero, C>);  // 第一个为假的
static_assert(std::is_same_v<decltype(std::conjunction<Seven>::value),
                             const int>);
static_assert(std::conjunction<Seven>::value == 7);

int main() {}
```

¶6 要求基类的成员名在 `conjunction` 中不被隐藏、可以无歧义地使用。例外是 `conjunction` 和 `operator=` 两个名字：前者是 `conjunction` 自己的注入类名，必然遮住基类的注入类名；后者是每个类都会隐式声明的赋值运算符。

### 对实参的要求

¶4 要求：凡是 `::value` 被实例化了的 `Bi`，都必须能作为基类，并且有一个可以转换为 `bool` 的成员 `value`，这个成员不被隐藏、可以无歧义地访问。被短路跳过的实参不受这些约束。

能作为基类这一条排除了 `final` 类。按第 5 段，`conjunction<F>` 要以 `F` 为基类，所以对 `struct F final : std::true_type {};`，本机 libc++ 在 `conjunction_v<F>` 处报错，指出基类 `F` 被标记为 `final`。

## `disjunction`

`disjunction` 与 `conjunction` 对称（第 7–11 段）：

- 如果某个 `Bi` 的 `bool(Bi::value)` 为真，就不需要实例化后面的 `Bj::value`（第 8 段，注 3 类比内建 `||`）。
- 基类是列表 `false_type, B1, …, BN` 中第一个值为真的类型，找不到就是最后一个类型（第 10 段），所以 `disjunction_v<>` 为假。
- 对实参的要求和成员可见性的要求与 `conjunction` 相同（第 9 段、第 11 段）。

由于基类就是第一个为真的实参，`disjunction` 可以用来在编译期查找第一个满足条件的元素。只要每个实参都带着额外的成员，就能通过 `disjunction` 取出匹配项的信息：

```cpp run title="disjunction-find.cpp" ok
#include <type_traits>

template<class T>
struct Match : std::is_integral<T> {
  using type = T;  // 遮住 integral_constant 的 type
};

using First =
    std::disjunction<Match<float>, Match<long>, Match<int>>::type;
static_assert(std::is_same_v<First, long>);

int main() {}
```

`Match<float>` 的值为假，`Match<long>` 为真，于是 `disjunction` 的基类是 `Match<long>`，`::type` 就是 `long`。`Match<int>` 不会被实例化。

## `negation`

¶12：`negation<B>` 是一个一元类型特征，基特征是 `bool_constant<!bool(B::value)>`。它总是派生自 `true_type` 或 `false_type`，而且会实例化 `B::value`。

`negation` 的用处是把取反也写成一个类型，这样它就能放进 `conjunction` 或 `disjunction` 的实参列表，参与短路，例如 `conjunction<is_class<T>, negation<is_final<T>>>`。

!!! impl "libc++ 的实现"
    libc++ 的 `conjunction` 几乎就是第 5 段的直译：

    ```cpp
    template <class...>
    struct conjunction : true_type {};
    template <class _Arg>
    struct conjunction<_Arg> : _Arg {};
    template <class _Arg, class... _Args>
    struct conjunction<_Arg, _Args...>
        : conditional_t<!bool(_Arg::value), _Arg, conjunction<_Args...>> {};
    ```

    `conditional_t` 的两个分支都会被写出，但写出 `conjunction<_Args...>` 这个名字并不实例化它，只有被选为基类时才实例化。所以递归在第一个为假的 `_Arg` 处停止。

## 与约束的关系

在 `requires` 子句和概念定义中，`&&` 和 `||` 组成的是约束的合取和析取（[[temp.constr]]），检查约束是否满足时本身就会短路。约束 `std::is_integral_v<T> && Bad<T>::value` 在 `T = double` 时不会实例化 `Bad<double>`。

所以在 C++20 的约束中通常不需要 `conjunction`。它主要用在其他需要计算类型的地方：基类列表、`enable_if` 的实参、`static_assert`。

## 思考题

!!! question "思考题"
    `std::conjunction<std::is_integral<T>, std::is_signed<T>>` 与 `std::bool_constant<std::is_integral_v<T> && std::is_signed_v<T>>` 有什么可以观察到的区别？

<details markdown="1">
<summary>答案</summary>

两者的 `::value` 相同，区别有两点。

一是基类不同。前者的基类是 `is_integral<T>`（当它为假时）或 `is_signed<T>`，它本身不是 `true_type` 或 `false_type`，只是间接派生自其中之一。所以 `std::is_same_v<..., std::true_type>` 对前者恒为假，对后者在条件成立时为真。

二是实例化不同。前者在 `is_integral<T>` 为假时不实例化 `is_signed<T>::value`，后者写出 `std::is_signed_v<T>` 时必然实例化它。对这两个 trait 来说没有影响，但如果第二项可能引发错误，只有前者安全。
</details>

## 速查

| 模板 | 短路 | 基类 | 空包 |
|---|---|---|---|
| `conjunction<B...>` | 遇到第一个为假的实参就停止 | 第一个为假的 `Bi`，否则最后一个 | `true_type` |
| `disjunction<B...>` | 遇到第一个为真的实参就停止 | 第一个为真的 `Bi`，否则最后一个 | `false_type` |
| `negation<B>` | 不适用 | `bool_constant<!bool(B::value)>` | 不适用 |
