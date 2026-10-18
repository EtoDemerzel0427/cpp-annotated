---
title: enumerate 视图
summary: C++23 的 views::enumerate 产出 (下标, 元素) 对——下标类型是有符号的 range_difference_t、引用类型是 tuple<difference_type, range_reference_t<V>>（prvalue 元组里装着元素引用，结构化绑定可写回）、迭代器提供 index()、强度/sized/common/借用随底层，以及 range-with-movable-references 约束的由来。
status: done
covers: *
since: c++23
papers: P2164R9
related: range.adaptors, range.zip, range.iota, range.elements, range.utility, dcl.struct.bind
tags: 标准库, 范围, enumerate
updated: 2026-10-18
---

带下标遍历是最常见的需求之一：C++20 里只能手写计数器，或者 `zip(iota(0), v)`（还要处理 `iota` 与 `size_t` 的符号问题）。C++23 的 [[P2164R9]] 加入了 `views::enumerate`。

## 概览（[range.enumerate.overview]）

¶1 `enumerate_view` 的元素同时表示位置与底层序列中的值。¶2 `views::enumerate(E)` 表达式等价于 `enumerate_view<views::all_t<decltype((E))>>(E)`。

```cpp
template<view V>
  requires range-with-movable-references<V>
class enumerate_view : public view_interface<enumerate_view<V>> {
  V base_ = V();
  template<bool Const> class iterator;
  template<bool Const> class sentinel;
public:
  constexpr auto begin() requires (!simple-view<V>) { return iterator<false>(ranges::begin(base_), 0); }
  constexpr auto begin() const requires range-with-movable-references<const V>;
  constexpr auto end() requires (!simple-view<V>);   // forward+common+sized 时返回迭代器，否则 sentinel
  constexpr auto size() requires sized_range<V>;
  // ...
};
```

*range-with-movable-references*（[[range.utility]]）要求底层的 `range_reference_t` 与 `range_rvalue_reference_t` 都可以移动构造——因为它们要被装进 `tuple` 返回。

## 迭代器（[range.enumerate.iterator]）

- `difference_type` = `range_difference_t<Base>`；**下标就用这个类型**（成员 `pos_`），因此是**有符号**的（通常 `ptrdiff_t`）；
- `value_type` = `tuple<difference_type, range_value_t<Base>>`；
- 引用类型 *reference-type* = `tuple<difference_type, range_reference_t<Base>>`，`operator*` 返回一个 prvalue 元组，里面的第二个分量是底层元素的**引用**；
- `index()` 成员直接给出下标；
- `iter_move` 返回 `tuple<difference_type, range_rvalue_reference_t<Base>>`；
- 强度随底层（最高 random access）；`end()` 在底层 forward、common、sized 时返回迭代器（下标设为 `distance(base_)`），否则返回哨位，哨位只比较底层迭代器。

结构化绑定 `auto [i, x]` 绑定的是那个 prvalue 元组的副本，但 `x` 对应的分量本身是引用类型，所以通过 `x` 能修改底层元素（[[dcl.struct.bind]]）。

```cpp run ok
#include <ranges>
#include <string>
#include <vector>
#include <cstdio>
int main() {
  std::vector<std::string> v{"a", "b", "c"};
  for (auto [i, s] : std::views::enumerate(v)) {
    static_assert(std::same_as<decltype(i), std::ptrdiff_t>);   // 有符号的 range_difference_t
    s += std::to_string(i);                                      // s 是 std::string&：写回
  }
  using E = decltype(std::views::enumerate(v));
  static_assert(std::same_as<std::ranges::range_reference_t<E>, std::tuple<std::ptrdiff_t, std::string&>>);
  static_assert(std::ranges::random_access_range<E> && std::ranges::sized_range<E>);
  auto it = std::ranges::begin(std::views::enumerate(v)) + 2;    // 底层借用 → enumerate 也借用
  std::printf("%td %s %s\n", it.index(), v[0].c_str(), v[2].c_str());   // 2 a0 c2
}
```

`std::ranges::begin(std::views::enumerate(v))` 对一个**右值**视图调用 `begin` 却合法，是因为 `enable_borrowed_range<enumerate_view<V>>` 随底层，而 `ref_view` 借用（[[range.access]]、[[range.req]]）。

## 与 zip(iota, r) 的区别

| | `enumerate(r)` | `zip(iota(0), r)` |
|---|---|---|
| 下标类型 | `range_difference_t<R>`（有符号） | 由 `0` 推导（`int`），可能与 `size_t` 比较时告警 |
| `end()` | 底层 forward+common+sized 时为 common | `zip` 的 common 规则（[[range.zip]]），无界 `iota` 让它非 common |
| 下标访问 | `it.index()` | `std::get<0>(*it)` |
| 借用 | 随底层 | 全部借用时借用 |

## 小结

- 元素是 `tuple<ptrdiff_t, T&>`（prvalue 元组装引用），结构化绑定可写回；
- 下标是有符号的 `range_difference_t`；
- 其余性质都随底层，包括借用性。
