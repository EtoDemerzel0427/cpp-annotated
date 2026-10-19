---
title: 编译期整数序列
summary: integer_sequence 把一串整数常量装进类型，传给函数模板后可以推导成形参包并展开；make_index_sequence<N> 生成 0..N-1；C++26 起它还能被结构化绑定解构。
status: done
covers: *
papers: N3658, P1061R10
related: meta, temp.variadic, temp.deduct.call, dcl.struct.bind, tuple.apply, stmt.expand
tags: 标准库, 元编程, 形参包, index_sequence
updated: 2026-10-19
---

!!! tldr
    - `std::index_sequence<0, 1, 2>` 是一个空类，它的全部信息都在模板实参里。
    - 把这样的对象传给形参为 `index_sequence<I...>` 的函数模板，推导会得到形参包 `I...`，函数体里就能写 `std::get<I>(t)...`。
    - `make_index_sequence<N>` 是 `index_sequence<0, …, N-1>` 的别名，`index_sequence_for<Ts...>` 按包的长度生成序列。
    - C++26 起整数序列支持 tuple 协议，`auto [...Is] = std::make_index_sequence<N>{};` 可以在函数模板里直接得到一个包。

## 问题：循环变量不是常量

想把一个 `tuple` 倒过来，自然的写法是循环 `I` 从 0 到 N-1，每次取 `std::get<N-1-I>(t)`。但 `std::get` 的下标是模板实参，必须是常量表达式，普通循环变量不行。

模板里能当作一串常量来展开的，只有形参包（[[temp.variadic]]），而形参包要通过模板实参推导得到。[intseq] 的做法是把 0, 1, …, N-1 编码进一个类型，再让推导把它还原成包：

```cpp title="index-sequence.cpp" run ok
#include <cstdio>
#include <tuple>
#include <utility>

template<class Tuple, std::size_t... I>
auto reverse_impl(const Tuple& t, std::index_sequence<I...>) {
    constexpr std::size_t N = sizeof...(I);
    return std::make_tuple(std::get<N - 1 - I>(t)...);   // I 依次为 0,1,...,N-1
}

template<class... Ts>
auto reverse(const std::tuple<Ts...>& t) {
    return reverse_impl(t, std::index_sequence_for<Ts...>{});
}

int main() {
    auto r = reverse(std::make_tuple(1, 2.5, 'c'));
    std::printf("%c %g %d\n", std::get<0>(r), std::get<1>(r), std::get<2>(r));   // c 2.5 1
}
```

`reverse` 构造一个 `index_sequence<0, 1, 2>` 对象传给 `reverse_impl`，推导得到 `I... = 0, 1, 2`（[[temp.deduct.call]]），`std::get<N - 1 - I>(t)...` 再把包展开成三个调用。

[intseq.general] ¶1 描述的就是这个用途：整数序列作为函数模板的实参时，定义序列的模板形参包可以被推导，并用于包展开。注 1 提到 `index_sequence` 是 `size_t` 版本的便捷别名，并指向 `std::apply`（[[tuple.apply]]），它是这种技巧的典型用户。

C++20 起不必单独写一个 `_impl` 函数，带模板形参列表的泛型 lambda 可以就地推导：

```cpp title="lambda-seq.cpp" run ok
#include <utility>

constexpr auto sum = []<std::size_t... I>(std::index_sequence<I...>) {
    return (I + ... + 0);
}(std::make_index_sequence<101>{});
static_assert(sum == 5050);

int main() {}
```

## `integer_sequence` [intseq.intseq]

```cpp
namespace std {
  template<class T, T... I> struct integer_sequence {
    using value_type = T;
    static constexpr size_t size() noexcept { return sizeof...(I); }
  };
}
```

它没有数据成员，`size()` 就是 `sizeof...(I)`。

¶1 *Mandates*：`T` 是整数类型。按 [[basic.fundamental]]，integer type 是 integral type 的同义词，所以 `bool` 和各种字符类型都可以，浮点类型不行。*Mandates* 不满足时程序非良构，编译器必须诊断：

```cpp title="intseq-mandates.cpp" run error
#include <utility>

std::integer_sequence<bool, true, false> ok;   // OK：bool 是整型
std::integer_sequence<double> bad;             // error: 只能用整型实例化
```

libc++ 用 `static_assert` 实现这条要求。

## `make_integer_sequence` [intseq.make]

```cpp
template<class T, T N>
  using make_integer_sequence = integer_sequence<T, /* 0, 1, …, N-1 */>;
template<size_t N>
  using make_index_sequence = make_integer_sequence<size_t, N>;
template<class... T>
  using index_sequence_for = make_index_sequence<sizeof...(T)>;
```

¶1 *Mandates*：`N ≥ 0`。

¶2 `make_integer_sequence<T, N>` 是 `integer_sequence<T, 0, 1, …, N-1>` 的别名。注 1 说明 `N` 为 0 时得到空序列 `integer_sequence<T>`。

这些都是别名模板，所以 `make_index_sequence<3>` 和 `index_sequence<0, 1, 2>` 是同一个类型，`is_same_v` 为真。

!!! impl "编译器内建的生成器"
    用递归或二分倍增实现 `make_integer_sequence`，需要 O(N) 或 O(log N) 层模板实例化，N 很大时会碰到实例化深度上限。Clang 提供内建别名模板 `__make_integer_seq<Template, T, N>`，GCC 提供 `__integer_pack(N)...`，一步得到整个序列。libc++ 有前者时用前者，否则用后者。

    `N` 为负时，Clang 直接报 integer sequences must have non-negative sequence length，这就是 ¶1 要求的诊断。

## 结构化绑定支持 [intseq.binding] {{c++26}}

C++26 给整数序列加上了 tuple 协议，也就是 `tuple_size`、`tuple_element` 的特化和非成员 `get`：

```cpp
template<class T, T... Values>
  struct tuple_size<integer_sequence<T, Values...>>
    : integral_constant<size_t, sizeof...(Values)> { };
template<size_t I, class T, T... Values>
  struct tuple_element<I, integer_sequence<T, Values...>> { using type = T; };
template<size_t I, class T, T... Values>
  struct tuple_element<I, const integer_sequence<T, Values...>> { using type = T; };
template<size_t I, class T, T... Values>
  constexpr T get(integer_sequence<T, Values...>) noexcept;
```

¶1–¶2 两处 *Mandates* 都要求 `I < sizeof...(Values)`，下标越界是非良构的，不是 UB。¶3 `get` 返回 `Values...[I]`，规格直接用了 C++26 的包索引（[[g:pack-index]]）。

于是整数序列可以被结构化绑定（[[dcl.struct.bind]]）和展开语句（[[stmt.expand]]）解构。配合 C++26 的结构化绑定包（[[P1061R10]]），在函数体里就能直接得到 0..N-1 的包，不再需要辅助函数：

```cpp title="binding-pack.cpp" run ok
#include <utility>

template<std::size_t N>
constexpr std::size_t triangular() {
    auto [...Is] = std::make_index_sequence<N>{};   // Is... 是结构化绑定包
    return (Is + ... + 0);
}
static_assert(triangular<5>() == 10);

int main() {
    auto [a, b, c] = std::make_index_sequence<3>{};   // a=0, b=1, c=2
    return static_cast<int>(a + b + c) - 3;
}
```

结构化绑定包只能出现在模板里。含结构化绑定包的声明必须声明一个模板化实体（[[dcl.pre]]），所以把 `auto [...Is] = ...;` 直接写在 `main` 里是非良构的，Clang 报 pack declaration outside of template。

!!! note "为什么 `get` 按值传参，还要单独给 `const` 版本的 `tuple_element`"
    序列的值都在类型里，`get` 不需要读对象，按值接收一个空类也没有开销，返回 `T` 的纯右值。

    通用的 `tuple_element<I, const U>`（[[tuple.helper]]）会给出 `const T`。标准额外给出 `const integer_sequence` 的版本，令其 `type` 为 `T`，于是 `const auto [a, b] = std::index_sequence<1, 2>{};` 里 `decltype(a)` 仍是 `size_t`，与 `get` 的返回类型一致（本机 Clang 23 验证）。

## 常见错误

!!! pitfall "整数序列本身不产生包"
    产生包的是函数模板的实参推导，或 C++26 的结构化绑定包。`using S = std::make_index_sequence<3>;` 之后，非模板代码里没有办法展开 `S`，必须把它交给一个以 `integer_sequence<T, I...>` 为形参类型的模板。

!!! pitfall "`T` 必须一致"
    `make_integer_sequence<int, 5>` 是 `integer_sequence<int, 0, 1, 2, 3, 4>`，不是 `index_sequence<0, 1, 2, 3, 4>`（后者的 `T` 是 `size_t`）。以 `std::index_sequence<I...>` 为形参的函数无法从它推导。

## 思考题

!!! question "思考题 1"
    `std::make_integer_sequence<unsigned char, 300>` 是良构的吗？

<details markdown="1">
<summary>答案</summary>

不是。别名模板第二个模板形参的类型是 `T`，即 `unsigned char`，实参 `300` 必须是 `unsigned char` 的转换后常量表达式（[[g:converted-constant-expression]]）。`300` 转成 `unsigned char` 是窄化转换，所以模板实参非良构（[[temp.arg.nontype]]），在检查 [intseq.make] ¶1 的 *Mandates* 之前就出错了。
</details>

!!! question "思考题 2"
    `std::get<0>(std::index_sequence<>{})` 会怎样？

<details markdown="1">
<summary>答案</summary>

[intseq.binding] ¶2 的 *Mandates* `I < sizeof...(Values)` 不满足（`0 < 0` 为假），程序非良构，必须诊断。libc++ 先触发 `static_assert`，Clang 随后还会报包索引越界。
</details>

## 小结

| 组件 | 要点 |
|---|---|
| `integer_sequence<T, I...>` | 空类；`T` 必须是整型（含 `bool` 和字符类型）；`size()` 等于 `sizeof...(I)` |
| `make_integer_sequence<T, N>` | `integer_sequence<T, 0, …, N-1>` 的别名；`N ≥ 0`；编译器内建实现 |
| `index_sequence` 等 | `size_t` 版本的便捷别名 |
| C++26 tuple 协议 | `tuple_size`、`tuple_element`、`get`；越界非良构；可用于结构化绑定和结构化绑定包 |
