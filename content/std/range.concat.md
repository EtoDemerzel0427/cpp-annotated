---
title: concat 视图
summary: C++26 的 views::concat(rs...) 把多个范围首尾相接——concatable 约束（公共引用/值/右值引用类型必须存在且彼此兼容）、引用类型取 common_reference_t 可能退化为 prvalue、迭代器是 variant 并用 satisfy 跳过空范围、随机访问与双向要求"除最后一个外都是 common"、size 用公共无符号类型求和；它是 CPO 而非适配器，不能用管道。
status: done
covers: *
since: c++26
papers: P2542R8
related: range.adaptors, range.join, range.zip, range.adaptor.helpers, range.req, iterator.concepts, customization.point.object
tags: 标准库, 范围, concat, C++26
updated: 2026-10-18
---

`views::concat(a, b, c)` 是把几个**类型可以不同**的范围拼成一个序列：`vector<int>`、`list<int>`、`array<int,3>`、`views::single(9)` 可以串在一起。与 `join` 的区别是：`join` 处理"一个范围的范围"（内层类型都相同、个数在运行时决定），`concat` 处理"编译期已知个数、类型各异"的几个范围。它来自 C++26 的 [[P2542R8]]。

## 概览（[range.concat.overview]）

¶1 `concat_view` 给出一个连接所有底层范围的视图。¶2 `views::concat` 是**定制点对象**（不是范围适配器对象）；给定子表达式包 `Es...`：

- ¶2.1 若 `Es` 只有一个元素且其类型建模 `input_range`，表达式等价于 `views::all(Es...)`；
- ¶2.2 否则等价于 `concat_view(Es...)`。

因为它不是范围适配器对象，**没有管道形式**：`a | views::concat(b)` 不合法。零个实参时，`concat_view` 要求 `sizeof...(Views) > 0`，所以 `views::concat()` 非良构。

## *concatable* 约束（[range.concat.view] ¶1–¶2）

```cpp
template<class... Rs>
  using concat-reference-t = common_reference_t<range_reference_t<Rs>...>;
template<class... Rs>
  using concat-value-t = common_type_t<range_value_t<Rs>...>;
template<class... Rs>
  using concat-rvalue-reference-t = common_reference_t<range_rvalue_reference_t<Rs>...>;

template<class... Rs>
  concept concatable = requires {
    typename concat-reference-t<Rs...>;
    typename concat-value-t<Rs...>;
    typename concat-rvalue-reference-t<Rs...>;
  } && concat-indirectly-readable<Rs...>;
```

*concat-indirectly-readable*（¶1）要求这三个类型之间满足 `indirectly_readable` 所需的那几条 `common_reference_with` 关系，并且**每个**底层迭代器的 `*it` 能转换为 *concat-reference-t*、`ranges::iter_move(it)` 能转换为 *concat-rvalue-reference-t*。它保证合成出来的迭代器能建模 `input_iterator`。

后果是**引用类型可能退化**：

- 全是 `int&` → `int&`，可以写回；
- `int&` 与 `const int&` → `const int&`；
- `int&` 与 `long&` → `common_reference_t` 是 `long`（prvalue）——**元素不再可写**，每次解引用产生一个转换后的副本。

```cpp run ok
#include <array>
#include <list>
#include <ranges>
#include <vector>
#include <cstdio>
int main() {
  std::vector<int> a{1, 2};
  std::list<int> b{3, 4};
  std::array<int, 1> c{5};
  auto cat = std::views::concat(a, b, c);
  static_assert(std::ranges::bidirectional_range<decltype(cat)>);  // list 的 bidi 拖了后腿
  for (int& x : cat) x *= 10;                                      // 引用可写回
  for (int x : cat) std::printf("%d ", x);
  std::puts("");   // 10 20 30 40 50
  std::vector<long> d{6};
  auto mixed = std::views::concat(a, d);                           // int& 与 long& 的公共引用是 long
  static_assert(std::same_as<std::ranges::range_reference_t<decltype(mixed)>, long>);
}
```

最新草案中 [[range.join]] 的 `join_with_view` 也改用了 *concatable* 约束内层元素与分隔符的兼容性。

## 迭代器与遍历

迭代器存一个 `variant<iterator_t<maybe-const<Const, Views>>...>` 和指向父视图的指针。

- `begin()`（¶6）在第 0 个范围的开头构造迭代器，然后调用 *satisfy*`<0>()`：若当前范围已到末尾，就切换到下一个范围的开头，递归直到找到非空范围或到最后一个——**空范围被自动跳过**（`v3{}` 在标准示例中不产生任何元素）；
- `end()`（¶7）：若所有范围都是 forward 且**最后一个**是 common，则返回指向最后一个范围末尾的迭代器（结果 common）；否则返回 `default_sentinel`。

### 迭代器强度（[range.concat.iterator] ¶1）

```cpp
template<bool Const, class... Rs>
  concept concat-is-random-access =
    all-random-access<Const, Rs...> && (common_range<maybe-const<Const, Fs>> && ...);   // Fs：除最后一个外
template<bool Const, class... Rs>
  concept concat-is-bidirectional =
    all-bidirectional<Const, Rs...> && (common_range<maybe-const<Const, Fs>> && ...);
```

为什么"除最后一个外都要 common"？`--` 从第 k+1 个范围的开头退回第 k 个范围时，要拿到第 k 个范围**末尾的迭代器**再退一步——哨位做不到这一点。最后一个范围永远不会被"从后面退进来"，所以它可以不是 common。随机访问的跨段 `+= n` 同理。

`iterator_category`（¶2）：*concat-reference-t* 不是引用时为 `input_iterator_tag`；否则取所有底层类别与上述强度的交集。

### `iter_swap`

带约束（"requires see below"）地提供：¶42 用 `std::visit` 分派——两个迭代器处于**同一段**时调用底层的 `ranges::iter_swap`，处于不同段时退化为 `ranges::swap(*x, *y)`。¶41 的前置条件是两个 `variant` 都不处于 `valueless_by_exception` 状态（其他操作也普遍有这一前置条件）。因此可以对 `concat(a, b)` 调用 `ranges::sort`——前提是它是随机访问的（例如两个 `vector`），排序结果会跨越两个容器写回。

## `size()`（¶8）

```cpp
return apply([](auto... sizes) {
  using CT = make-unsigned-like-t<common_type_t<decltype(sizes)...>>;
  return (CT(sizes) + ...);
}, tuple-transform(ranges::size, views_));
```

所有范围都 sized 时才提供；先把各自的 `size` 转换到公共的无符号类型再求和。

## 性质

- 不是借用范围（[[ranges.syn]] 中没有对应的 `enable_borrowed_range` 特化）；
- 有 `const begin()`：当所有 `const Views` 都是范围且满足 *concatable*；
- 不缓存 `begin()`——*satisfy* 每次都会重新跳过开头的空范围，所以 `begin()` 的代价与开头连续空范围的个数成正比（个数是编译期常量，满足摊还 O(1)）。

!!! impl "实现现状"
    libc++ 已提供 `views::concat`（`__cpp_lib_ranges_concat` 为 `202403L`，对应 [[P2542R8]] 被采纳的时间），本页示例均在 libc++ 上验证。

## 小结

| 方面 | `views::concat` |
|---|---|
| 实参 | 一个或多个可以类型各异的 `viewable_range`（单个时退化为 `views::all`） |
| 引用类型 | 各底层引用的 `common_reference_t`，可能退化为 prvalue |
| 强度 | 所有底层的交集；双向/随机访问另需"除最后一个外都 common" |
| common | 全 forward 且最后一个 common |
| sized | 全部 sized |
| 管道 | 不支持（是 CPO 而非适配器） |
