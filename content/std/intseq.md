---
title: 编译期整数序列
summary: integer_sequence<T, I...> 把一串整数常量装进类型，作为函数实参时让 I... 可被推导并展开；make_integer_sequence<T, N> 生成 0..N-1（编译器内建）；C++26 起它还支持 tuple 协议与结构化绑定
status: draft
covers: *
papers: N3658, P1061R10
related: meta, temp.variadic, temp.deduct.call, dcl.struct.bind, tuple.apply, stmt.expand
tags: 标准库, 元编程, 形参包, index_sequence
updated: 2026-10-18
---

C++ 的形参包（[[temp.variadic]]）只能从**模板实参推导**中获得：你没法写 `for (size_t I = 0; I < N; ++I)` 然后在循环体里用 `std::get<I>(t)`，因为 `I` 不是常量表达式。[intseq] 提供的是一个极小但极关键的桥：把 "0, 1, …, N-1" **编码进一个类型** `integer_sequence<size_t, 0, 1, …, N-1>`，然后把这个类型的对象传给一个函数模板——推导会把 `0, 1, …, N-1` 还原成一个可以展开的形参包 `I...`。

¶1（[intseq.general]）把这一点说得很直白：作为函数模板的实参时，定义序列的模板形参包可以被推导，并用于包展开。注 1 指出 `index_sequence` 是 `size_t` 版本的便捷别名，并点名 `std::apply`（[[tuple.apply]]）是它的典型用户。

## 类模板 `integer_sequence`（[intseq.intseq]）

```cpp
namespace std {
  template<class T, T... I> struct integer_sequence {
    using value_type = T;
    static constexpr size_t size() noexcept { return sizeof...(I); }
  };
}
```

它是一个**空类**：没有数据成员，所有信息都在模板实参里。`size()` 就是 `sizeof...(I)`。

¶1 *Mandates*：`T` 是整数类型（integer type）。按 [[basic.fundamental]]，"integer type"是"integral type"的同义词，所以 `bool`、`char`、`char8_t` 等都可以；`double` 不行。*Mandates* 意味着违反时程序非良构（必须诊断），libc++ 用 `static_assert` 实现：

```cpp run title="intseq-mandates.cpp" error
#include <utility>

std::integer_sequence<bool, true, false> ok;   // OK：bool 是整型
std::integer_sequence<double> bad;             // error: integer_sequence 只能用整型实例化
```

## 别名模板 `make_integer_sequence`（[intseq.make]）

```cpp
template<class T, T N>
  using make_integer_sequence = integer_sequence<T, /* 0, 1, …, N-1 */>;
template<size_t N>
  using make_index_sequence = make_integer_sequence<size_t, N>;
template<class... T>
  using index_sequence_for = make_index_sequence<sizeof...(T)>;
```

¶1 *Mandates*：`N ≥ 0`。¶2：`make_integer_sequence<T, N>` 是 `integer_sequence<T, 0, 1, …, N-1>` 的别名；注 1 特别说明 `N == 0` 时得到空序列 `integer_sequence<T>`。

注意它是**别名模板**：`make_index_sequence<3>` 和 `index_sequence<0, 1, 2>` 是**同一个类型**，可以互相替换，`is_same_v` 为真。

!!! impl "libc++/Clang：一个内建模板，O(1) 实例化深度"
    朴素实现（递归或二分倍增）需要 O(N) 或 O(log N) 层实例化，N 一大就撞上实例化深度上限。Clang 提供内建别名模板 `__make_integer_seq<Template, T, N>`，GCC 提供 `__integer_pack(N)...`。libc++ 的 `__utility/integer_sequence.h` 优先使用前者：

    ```cpp
    #  if __has_builtin(__make_integer_seq)
    template <template <class _Tp, _Tp...> class _BaseType, class _Tp, _Tp _SequenceSize>
    using __make_integer_sequence_impl = __make_integer_seq<_BaseType, _Tp, _SequenceSize>;
    #  else
    template <template <class _Tp, _Tp...> class _BaseType, class _Tp, _Tp _SequenceSize>
    using __make_integer_sequence_impl = _BaseType<_Tp, __integer_pack(_SequenceSize)...>;
    #  endif
    ```

    对负的 `N`，Clang 直接给出 "integer sequences must have non-negative sequence length"——这就是 ¶1 *Mandates* 的诊断。

## 经典用法：把 tuple 拆成包

```cpp run title="index-sequence.cpp" ok
#include <cstdio>
#include <tuple>
#include <utility>

template<class Tuple, std::size_t... I>
auto reverse_impl(const Tuple& t, std::index_sequence<I...>) {
    constexpr std::size_t N = sizeof...(I);
    return std::make_tuple(std::get<N - 1 - I>(t)...);   // 包展开：I 依次为 0,1,...,N-1
}

template<class... Ts>
auto reverse(const std::tuple<Ts...>& t) {
    return reverse_impl(t, std::index_sequence_for<Ts...>{});   // 推导出 I... = 0..sizeof...(Ts)-1
}

int main() {
    auto r = reverse(std::make_tuple(1, 2.5, 'c'));
    std::printf("%c %g %d\n", std::get<0>(r), std::get<1>(r), std::get<2>(r));   // c 2.5 1
}
```

C++20 起不必再写一个单独的 `_impl` 函数：带显式模板形参列表的泛型 lambda 可以就地推导：

```cpp run title="lambda-seq.cpp" ok
#include <utility>

constexpr auto sum = []<std::size_t... I>(std::index_sequence<I...>) {
    return (I + ... + 0);
}(std::make_index_sequence<101>{});
static_assert(sum == 5050);

int main() {}
```

## 结构化绑定支持（[intseq.binding]）{{c++26}}

C++26 给 `integer_sequence` 补上了 **tuple 协议**：`tuple_size`、`tuple_element` 的特化以及非成员 `get`。这样它就能被结构化绑定（[[dcl.struct.bind]]）和展开语句（[[stmt.expand]]）直接解构：

```cpp
template<class T, T... Values>
  struct tuple_size<integer_sequence<T, Values...>> : integral_constant<size_t, sizeof...(Values)> { };
template<size_t I, class T, T... Values>
  struct tuple_element<I, integer_sequence<T, Values...>> { using type = T; };
template<size_t I, class T, T... Values>
  struct tuple_element<I, const integer_sequence<T, Values...>> { using type = T; };
template<size_t I, class T, T... Values>
  constexpr T get(integer_sequence<T, Values...>) noexcept;
```

- ¶1、¶2 *Mandates*：`I < sizeof...(Values)`——越界是非良构，不是 UB；
- ¶3 *Returns*：`Values...[I]`——直接用 C++26 的**包索引**（[[g:pack-index]]）写出规格。

配合 C++26 的**结构化绑定包**（[[P1061R10]]），"给我一个 0..N-1 的包"终于可以在函数体内就地完成，不再需要辅助函数：

```cpp run title="binding-pack.cpp" ok
#include <utility>

template<std::size_t N>
constexpr std::size_t triangular() {
    auto [...Is] = std::make_index_sequence<N>{};   // Is... 是一个结构化绑定包
    return (Is + ... + 0);
}
static_assert(triangular<5>() == 10);

int main() {
    auto [a, b, c] = std::make_index_sequence<3>{};   // a=0, b=1, c=2
    return static_cast<int>(a + b + c) - 3;
}
```

!!! note "按值的 `get` 与 `const` 版本的 `tuple_element`"
    `integer_sequence` 是空类，按值传递零开销；序列的值都在类型里，`get` 根本不需要读对象，于是返回 `T` 的纯右值。与之配套，标准额外给出了 `tuple_element<I, const integer_sequence<...>>` 并令其 `type` 为 `T`（而非 `const T`）：若没有这个更特化的版本，通用的 `tuple_element<I, const U>`（[[tuple.helper]]）会给出 `const T`。于是 `const auto [a, b] = std::index_sequence<1, 2>{};` 中隐藏变量虽是 `const`，`decltype(a)` 仍是 `size_t` 而非 `const size_t`，与 `get` 的返回类型一致（本地 Clang 23 验证）。

## 陷阱

!!! pitfall "结构化绑定包只能出现在模板里"
    `auto [...Is] = std::make_index_sequence<3>{};` 写在非模板函数（如 `main`）里是非良构的——含结构化绑定包的声明必须声明一个模板化实体（[[dcl.pre]]），Clang 报 "pack declaration outside of template"。上面的 `triangular<N>` 是函数模板，所以没问题。

!!! pitfall "形参包只能在推导语境里出现"
    `integer_sequence` 本身并不"产生"包——是**函数模板实参推导**（[[temp.deduct.call]]）或结构化绑定包把类型里的常量还原成包。如果你写 `using S = std::make_index_sequence<3>;` 然后想在非模板代码里"展开 S"，是做不到的；必须把它交给一个以 `integer_sequence<T, I...>` 为形参类型的模板。

!!! pitfall "`T` 与 `N` 的类型要一致"
    `make_integer_sequence<int, 5>` 生成 `integer_sequence<int, 0,1,2,3,4>`，它**不是** `index_sequence<0,1,2,3,4>`（后者是 `size_t`）。以 `std::index_sequence<I...>` 为形参的函数无法从 `integer_sequence<int, ...>` 推导。

## 思考题

!!! question "思考题 1"
    `std::make_integer_sequence<unsigned char, 300>` 是良构的吗？

<details markdown="1">
<summary>展开查看答案与解析</summary>

不是。别名模板的第二个模板形参类型是 `T`（这里是 `unsigned char`），实参 `300` 必须是 `unsigned char` 的**转换后常量表达式**（[[g:converted-constant-expression]]），而 `300 → unsigned char` 是窄化转换，模板实参非良构（[[temp.arg.nontype]]）。这一错误在走到 ¶1 的 *Mandates* 之前就发生了。
</details>

!!! question "思考题 2"
    `std::get<0>(std::index_sequence<>{})` 会怎样？

<details markdown="1">
<summary>展开查看答案与解析</summary>

¶2 的 *Mandates* `I < sizeof...(Values)` 不满足（`0 < 0` 为假），程序非良构，必须诊断。libc++ 先触发 `static_assert`，随后 Clang 还会报包索引越界。
</details>

## 小结

| 组件 | 要点 |
|---|---|
| `integer_sequence<T, I...>` | 空类；`T` 须为整型（含 `bool`、字符类型）；`size()` = `sizeof...(I)` |
| `make_integer_sequence<T, N>` | 别名 = `integer_sequence<T, 0..N-1>`；`N ≥ 0`；编译器内建实现 |
| `index_sequence` / `make_index_sequence` / `index_sequence_for` | `size_t` 版本的便捷别名 |
| C++26 tuple 协议 | `tuple_size`、`tuple_element`、`get`；越界非良构；可用于结构化绑定与结构化绑定包 |
