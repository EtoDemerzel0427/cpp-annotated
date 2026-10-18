---
title: reverse 视图
summary: views::reverse 的表达式等价规则——对 reverse_view 取回 base()、对 subrange<reverse_iterator<I>> 拆回原迭代器、对 optional 原样返回；reverse_view 要求双向底层，非 common 时 begin() 需要 O(n) 走到末尾并缓存，于是失去 const 迭代；迭代器就是 std::reverse_iterator，以及"stashing 迭代器"不能反向的老问题。
status: done
covers: *
since: c++20
papers: P0896R4
related: range.adaptors, range.drop, range.filter, range.access, reverse.iterators, range.take, range.join
tags: 标准库, 范围, reverse
updated: 2026-10-18
---

`views::reverse` 反转一个双向视图的遍历顺序。它的实现几乎就是"`std::reverse_iterator` 套在 `begin/end` 上"，但有两件事值得细看：表达式等价规则中的**消去**，以及非 common 底层带来的 **begin 缓存**。

## 表达式等价规则（[range.reverse.overview]）

¶1 `reverse_view` 接受一个双向视图，以相反顺序迭代同样的元素。¶2 `views::reverse(E)` 表达式等价于：

- ¶2.1 若 `E` 的类型是（可能 cv 限定的）`reverse_view` 特化：`E.base()`——**两次反转互相抵消**，类型也回到原来的；
- ¶2.2 若 `E` 是建模 `view` 的 `optional` 特化（{{c++26}}）：*decay-copy*`(E)`——至多一个元素，反转等于不变；
- ¶2.3 若 `E` 的类型是 `subrange<reverse_iterator<I>, reverse_iterator<I>, K>`：拆回 `subrange<I, I, K>(E.end().base(), E.begin().base()[, E.size()])`（E 只求值一次）；
- ¶2.4 否则 `reverse_view{E}`。

```cpp run ok
#include <ranges>
#include <vector>
#include <cstdio>
int main() {
  std::vector<int> v{1, 2, 3, 4, 5};
  auto rr = v | std::views::reverse | std::views::reverse;        // 2.1：直接取回 base()
  static_assert(std::same_as<decltype(rr), std::ranges::ref_view<std::vector<int>>>);
  auto tw = v | std::views::take_while([](int x) { return x < 4; });   // 双向但非 common
  auto r = tw | std::views::reverse;                                   // begin() 要先走到尾：缓存
  static_assert(!std::ranges::range<const decltype(r)>);
  for (int x : r) std::printf("%d ", x);                               // 3 2 1
  auto cr = v | std::views::reverse;
  static_assert(std::ranges::range<const decltype(cr)>);              // common 底层：O(1)，有 const begin
  std::puts("");
}
```

## `reverse_view`（[range.reverse.view]）

```cpp
template<view V>
  requires bidirectional_range<V>
class reverse_view : public view_interface<reverse_view<V>> {
  V base_ = V();
public:
  constexpr reverse_iterator<iterator_t<V>> begin();
  constexpr reverse_iterator<iterator_t<V>> begin() requires common_range<V>;
  constexpr auto begin() const requires common_range<const V>;
  constexpr reverse_iterator<iterator_t<V>> end();
  constexpr auto end() const requires common_range<const V>;
  constexpr auto size() requires sized_range<V>;
  constexpr auto size() const requires sized_range<const V>;
};
```

- **¶2–¶3：非 common 底层**，`begin()` 返回 `make_reverse_iterator(ranges::next(ranges::begin(base_), ranges::end(base_)))`——要从头走到尾才能得到"最后一个元素之后"的**迭代器**（哨位不能拿来构造 `reverse_iterator`）。这是 O(n) 的，所以规范要求**缓存**；于是没有 const `begin()`。
- **¶4：common 底层**，`begin()` 就是 `make_reverse_iterator(ranges::end(base_))`，O(1)，且 `const V` 也 common 时有 const 版本。
- ¶5 `end()` 是 `make_reverse_iterator(ranges::begin(base_))`。
- 结果总是 common 的（首尾都是 `reverse_iterator<iterator_t<V>>`）；强度同底层（最高 random access，`reverse_iterator` 不是 contiguous）；借用性随底层。

不能反转的：`forward_list`、`istream_view`、`filter` 套在 `forward_list` 上……——任何非双向的范围都不满足约束，编译失败。

## 与其他视图的联动

[[range.drop]] 的注释提到：`drop_view`/`drop_while_view` 之所以要缓存 `begin()`，正是为了让 `reverse_view` 叠在它们上面不变成平方复杂度——`reverse_iterator` 与 `rend()` 比较时会用到底层的 `begin()`。

!!! pitfall "reverse_iterator 与“藏匿型”迭代器"
    `std::reverse_iterator::operator*` 的效果是 `{ auto tmp = current; return *--tmp; }`——它对一个**局部副本**解引用并返回结果。若底层迭代器是"藏匿型"（stashing）的，即解引用返回指向迭代器**自身内部**的引用，那么 `tmp` 一销毁，返回的引用就悬垂了。标准把这类迭代器排除在双向/前向之外（[[iterator.concept.forward]] 要求引用的有效性不依赖迭代器对象），所以合规的视图不会出现这种问题；但手写迭代器时若违反了这条语义要求，`views::reverse` 会产生{{ub}}。

## 小结

- `reverse(reverse(x))` 消去为 `x`；`subrange<reverse_iterator>` 被拆回；
- 要求双向；非 common 时 `begin()` O(n) 一次并缓存、无 const 迭代；
- 结果 common，强度同底层（最高 random access），借用性随底层。
