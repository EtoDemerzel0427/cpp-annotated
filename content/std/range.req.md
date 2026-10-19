---
title: 范围要求
summary: range、borrowed_range、sized_range、common_range、viewable_range、constant_range 等概念的定义，以及它们对复杂度、借用和长度的语义要求。
status: done
covers: range.req.general, range.range, range.approximately.sized, range.sized, range.refinements
since: c++20
papers: P0896R4, P2017R1, P2415R2, P2278R4
related: range.access, range.view, range.all, range.dangling, iterator.concepts, iterator.requirements.general, concepts.equality, namespace.std, ranges
tags: 标准库, 范围, 概念, 借用范围
updated: 2026-10-19
---

!!! tldr
    - `range<T>` 只问 `T` 类型的左值能否调用 `ranges::begin` 和 `ranges::end`；语义上还要求这两个调用摊还常数时间、不修改范围。这条复杂度要求是 `filter_view` 等视图缓存 `begin()` 的原因。
    - `borrowed_range` 表示从对象得到的迭代器不随对象一起失效：左值引用总是借用的，`string_view`、`span`、`subrange` 等通过 `enable_borrowed_range` 声明自己是借用的。
    - `sized_range` 要求 `ranges::size` 是常数时间且等于实际元素个数；`size()` 达不到时，用 `disable_sized_range` 退出。
    - `viewable_range` 刻画 `views::all` 能安全处理的实参：左值、可移动的右值容器、视图，但不包括 const 右值和右值 `initializer_list`。
    - 这些概念的语义部分编译器不检查。类型只满足语法而不满足语义时，把它交给标准库的结果没有保证。

## 概念家族 [range.req.general]

¶1 范围让程序能用统一的方式处理各种数据结构的元素：`ranges::begin` 返回一个迭代器，`ranges::end` 返回与之配对的哨位（[[range.access]]）。¶2–¶3 在 `range` 之上定义了一族细化概念：

```text
range ─┬─ approximately_sized_range ── sized_range
       ├─ input_range ── forward_range ── bidirectional_range
       │     ── random_access_range ── contiguous_range
       ├─ output_range<R, T>
       ├─ common_range      begin/end 同类型
       ├─ borrowed_range    迭代器不随对象失效
       ├─ view              见 [range.view]
       ├─ viewable_range    能安全转成视图
       └─ constant_range    元素不可修改
```

每个概念都有语法部分（`requires` 表达式，编译器检查）和语义部分（标准用 "models only if" 写出的条件，编译器不检查）。类型**满足**（satisfy）一个概念，指语法部分成立；**建模**（model）一个概念，指语法和语义都成立（[[res.on.requirements]]）。`view` 的内容较多，单独见 [[range.view]]。

```cpp run ok
#include <initializer_list>
#include <ranges>
#include <span>
#include <string>
#include <string_view>
#include <vector>
namespace r = std::ranges;
using V = std::vector<int>;
static_assert(r::range<V>);              // 尽管 ranges::begin(V{}) 非良构
static_assert(r::view<std::string_view> && r::view<std::span<int>>);
static_assert(!r::view<V>);              // 复制是 O(N)
static_assert(r::borrowed_range<std::string_view>);
static_assert(r::borrowed_range<V&>);
static_assert(!r::borrowed_range<V> && !r::borrowed_range<std::string>);
static_assert(r::viewable_range<V> && r::viewable_range<V&>);
static_assert(!r::viewable_range<const V>);  // const 右值不能移动
static_assert(!r::viewable_range<std::initializer_list<int>>);
static_assert(std::same_as<std::views::all_t<V&>, r::ref_view<V>>);
static_assert(std::same_as<std::views::all_t<V>, r::owning_view<V>>);
static_assert(!r::borrowed_range<r::owning_view<V>>);
static_assert(!std::copyable<r::owning_view<V>>);  // 只能移动
static_assert(r::contiguous_range<const V>);
static_assert(!r::contiguous_range<std::vector<bool>>);
static_assert(r::common_range<V>);
static_assert(!r::common_range<decltype(std::views::iota(0))>);
int main() {}
```

## range [range.range]

¶1 `range` 要求类型提供一个迭代器和一个哨位，用来表示它的元素：

```cpp
template<class T>
  concept range = requires(T& t) {
    ranges::begin(t);   // 有时保持相等性（见下）
    ranges::end(t);
  };
```

注意形参是 `T& t`：语法检查总在左值上进行。所以 `range<vector<int>>` 为 `true`，尽管 `ranges::begin(vector<int>{})` 非良构。`range` 问的是这种类型的对象能不能遍历；右值能不能直接交给 `begin`，由下面的 `borrowed_range` 回答。

¶2 对 `decltype((t))` 为 `T&` 的表达式 `t`，`T` 建模 `range` 还要求：

- 2.1 `[ranges::begin(t), ranges::end(t))` 表示一个范围（[[iterator.requirements.general]]）；
- 2.2 `ranges::begin(t)` 和 `ranges::end(t)` 都是摊还常数时间，并且不修改范围；
- 2.3 如果 `begin` 的类型建模 `forward_iterator`，`ranges::begin(t)` **保持相等性**（equality-preserving）：相等的输入给出相等的结果（[[concepts.equality]]）。

!!! std
    both ranges::begin(t) and ranges::end(t) are amortized constant time and non-modifying

2.2 是整章缓存设计的来源。`filter_view::begin()` 要线性查找第一个满足谓词的元素，为了做到摊还常数时间，它只能在第一次调用时查找，然后把结果缓存起来（[[range.filter]]）。不修改指的是不改变范围表示的元素序列，写视图内部的缓存不算。

¶3 注 1 解释 2.3：对前向范围，反复调用 `begin` 和 `end` 得到相等的结果，所以可以把同一个范围交给多个算法，或者遍历多遍。输入范围没有这个要求，第二次调用 `begin` 可能得到不同的值，甚至不是良定义的。`std::generator` 就是例子，它的 `begin()` 要求协程还停在初始挂起点，第二次调用违反前置条件（[[coro.generator]]）。

## borrowed_range（¶4–¶7）

```cpp
template<class T>
  concept borrowed_range =
    range<T> &&
    (is_lvalue_reference_v<T> ||
     enable_borrowed_range<remove_cvref_t<T>>);
```

¶4 令 `U` 为 `T` 去掉右值引用后的类型。给定 `U` 类型的变量 `u`，`T` 建模 `borrowed_range` 的条件是：从 `u` 得到的迭代器的有效性，不与 `u` 这个变量的生命周期绑定。具体来说：

- 左值引用类型总是借用的：`u` 是一个引用，引用本身结束不影响被引用的对象；
- `string_view`、`span`、`subrange`、`ref_view` 是借用的，迭代器指向别人的存储；`iota_view`、`empty_view` 也是，迭代器自带值或根本不指向任何东西；
- `vector`、`string` 不是借用的，对象销毁后迭代器就悬垂；
- `filter_view`、`transform_view` 不是借用的，它们的迭代器保存着指向视图对象本身的指针，要用里面的谓词或函数。

¶5 注 2：所以形参类型建模 `borrowed_range` 的函数，可以安全地返回从这个形参得到的迭代器。[[range.dangling]] 的 `borrowed_iterator_t` 就是据此决定算法返回真正的迭代器还是 `dangling`。

¶6 用户可以为 cv 非限定的、程序定义的类型特化 `enable_borrowed_range`（[[namespace.std]]），特化必须能用于常量表达式，类型为 `const bool`。¶7 例 1 说明 `subrange` 的每个特化都通过把 `enable_borrowed_range` 特化为 `true` 来建模 `borrowed_range`。

!!! pitfall "特化 `enable_borrowed_range` 是一个承诺"
    编译器不会检查类型是否真的满足 ¶4。如果为一个持有 `std::vector` 的类型特化为 `true`，`ranges::find(make_it(), x)` 就会返回指向已销毁临时对象的迭代器，这是 {{ub}}，标准库的所有防护都被绕过了。

!!! history "有条件的借用"
    C++20 最初只有少数视图是借用的。[[P2017R1]] 以缺陷报告的形式，让 `take_view`、`drop_view`、`reverse_view` 等只转发底层迭代器的视图在底层借用时也借用。完整的清单见 [[ranges]] 中头文件概要一节。

## 长度：sized_range 与 approximately_sized_range

### sized_range [range.sized]

```cpp
template<class T>
  concept sized_range =
    approximately_sized_range<T> &&
    requires(T& t) { ranges::size(t); };
```

¶1 `sized_range` 能在摊还常数时间内求出元素个数。¶2 给定 `remove_reference_t<T>` 类型的左值 `t`，`T` 建模 `sized_range` 还要求：

- 2.1 `ranges::size(t)` 摊还常数时间，不修改 `t`，并且等于 `ranges::distance(ranges::begin(t), ranges::end(t))`；
- 2.2 如果迭代器是前向的，`ranges::size(t)` 不论在 `begin` 之前还是之后调用都是良定义的。注 1 补充，对非前向的 `sized_range`，`size` 可能只在第一次调用 `begin` 之前才良定义。

¶3 用户可以为程序定义的类型特化 `disable_sized_range`。¶4 注 2 说明它的用途：让满足但并不建模 `sized_range` 的类型也能和标准库一起用。典型例子是一个 `size()` 成员是线性时间的链表。特化为 `true` 后，`ranges::size` 会跳过成员和非成员 `size`，改用 `end - begin` 或者干脆不可用（[[range.access]]）。

### approximately_sized_range [range.approximately.sized] {{c++26}}

```cpp
template<class T>
  concept approximately_sized_range =
    range<T> && requires(T& t) { ranges::reserve_hint(t); };
```

¶1 它只要求能在摊还常数时间内给出元素个数的估计。¶2 `ranges::reserve_hint(t)` 不修改 `t`，值非负且能用 `range_difference_t<T>` 表示；迭代器是前向的时候，不论是否已经调用过 `begin` 都良定义。

估计值不必等于实际个数，`ranges::to` 等用它提前 `reserve`。C++26 让 `sized_range` 细化 `approximately_sized_range`；`size` 可用时 `reserve_hint` 就等于 `size`，所以原来的 `sized_range` 都不受影响。

## 其他细化 [range.refinements]

### 按迭代器强度（¶1–¶3）

```cpp
template<class R, class T>
  concept output_range =
    range<R> && output_iterator<iterator_t<R>, T>;
template<class T>
  concept input_range =
    range<T> && input_iterator<iterator_t<T>>;
// forward_range、bidirectional_range、random_access_range 同理逐级细化
template<class T>
  concept contiguous_range =
    random_access_range<T> && contiguous_iterator<iterator_t<T>> &&
    requires(T& t) {
      { ranges::data(t) } -> same_as<add_pointer_t<range_reference_t<T>>>;
    };
```

¶2 `contiguous_range` 还要求能使用 `ranges::data`，而且结果类型恰好是 `add_pointer_t<range_reference_t<T>>`。`const vector<int>` 的 `data()` 返回 `const int*`，与引用类型 `const int&` 吻合。`vector<bool>` 的引用是代理类，它不是连续范围。¶3 语义上要求 `to_address(ranges::begin(t)) == ranges::data(t)`。

### common_range（¶4）

```cpp
template<class T>
  concept common_range =
    range<T> && same_as<iterator_t<T>, sentinel_t<T>>;
```

¶4 例 1 指出标准容器都是 common range。很多视图不是，例如 `take_while`、没有上界的 `iota`、`istream`。旧接口，比如容器的迭代器对构造函数和 C++17 算法，需要首尾同类型，可以先用 `views::common` 转换（[[range.common]]）。

### viewable_range（¶5–¶6）

```cpp
template<class T>
  concept viewable_range =
    range<T> &&
    ((view<remove_cvref_t<T>> &&
      constructible_from<remove_cvref_t<T>, T>) ||
     (!view<remove_cvref_t<T>> &&
      (is_lvalue_reference_v<T> ||
       (movable<remove_reference_t<T>> &&
        !is-initializer-list<T>))));
```

¶6 `viewable_range` 是能安全转换成视图的范围，正好对应 `views::all` 能接受的实参（[[range.all]]）。¶5 定义的 *`is-initializer-list<R>`* 在 `remove_cvref_t<R>` 是 `initializer_list` 的特化时为 `true`。

| 实参 | viewable？ | `views::all` 的结果 |
|---|---|---|
| 能从实参构造的视图 | 是 | 视图本身的副本 |
| 非视图的左值，如 `vector<int>&` | 是 | `ref_view` |
| 非视图的可移动右值，如 `vector<int>&&` | 是 | `owning_view`，把容器移进去 |
| `const vector<int>&&` | 否 | 不能从 const 右值移动 |
| 右值 `initializer_list<int>` | 否 | 它只借用一块临时数组，存进 `owning_view` 必然悬垂 |
| 只能移动的视图的左值 | 否 | 不能复制 |

### constant_range（¶7）

```cpp
template<class T>
  concept constant_range =
    input_range<T> && constant-iterator<iterator_t<T>>;
```

¶7 `constant_range` 的元素不能通过迭代器修改，由 C++23 的 [[P2278R4]] 引入。*`constant-iterator`* 要求加 const 不改变迭代器的引用类型（[[const.iterators]]）。`const vector<int>` 是常量范围，`span<int>` 不是，因为 `span` 的 const 不传递到元素；`views::as_const` 能把后者变成前者（[[range.as.const]]）。

### sized-random-access-range（¶8）

¶8 说明专用的 *`sized-random-access-range`* 就是 `random_access_range<T> && sized_range<T>`。注 1 说明它用来约束第 26 章中一些带执行策略的并行算法：并行切分需要随机访问，也需要事先知道长度。

## 思考题

!!! question "思考题 1"
    底层是 `vector` 时，`range<const std::ranges::filter_view<...>>` 为什么是 `false`？这违反 [range.range] ¶2.2 的不修改要求吗？

<details markdown="1">
<summary>答案</summary>

`filter_view` 的 `begin()` 要缓存结果，只有底层是仅输入（不是前向）的范围时才提供 const 版本（[[range.filter]]）。底层是 `vector` 时，`requires(T& t) { ranges::begin(t); }` 中的 `t` 是 `const filter_view&`，调用不了非 const 的 `begin()`，于是不满足 `range`。

这不违反 ¶2.2。缓存不改变范围表示的元素序列，不修改指的是这个可观察的序列，而不是对象里的每一个字节。
</details>

!!! question "思考题 2"
    `get_ref()` 返回某个全局 `vector<int>` 的引用。`std::ranges::find(get_ref(), 0)` 会返回 `dangling` 吗？

<details markdown="1">
<summary>答案</summary>

不会。实参类型是 `vector<int>&`，左值引用总是借用的，算法返回真正的迭代器。只有非借用范围的右值，例如按值返回的 `vector`，才会得到 `dangling`。至于那个全局 `vector` 是否还活着，是程序员自己的责任。
</details>
