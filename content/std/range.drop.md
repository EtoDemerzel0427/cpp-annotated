---
title: drop 与 drop_while 视图
summary: views::drop(n) 的表达式等价规则（对 span/string_view/iota_view/subrange/repeat_view/optional 返回同类视图），drop_view 在底层不是"随机访问且有大小"时缓存 begin()——因此 list | drop(n) 没有 const 迭代；drop_while 总是缓存；注释说明了缓存的真实动机：避免 reverse 叠加时出现平方复杂度。
status: done
covers: range.drop, range.drop.overview, range.drop.view, range.drop.while, range.drop.while.overview, range.drop.while.view
since: c++20
papers: P0896R4, P1739R4, P3168R2
related: range.take, range.filter, range.reverse, range.adaptors, range.range, range.nonprop.cache, range.iota, range.factories
tags: 标准库, 范围, drop, drop_while, 缓存
updated: 2026-10-18
---

`drop(n)` 跳过前 n 个，`drop_while(p)` 跳过满足谓词的前缀。它们是 `take`/`take_while` 的镜像，但有一个关键区别：**截断发生在开头**，于是"第一个元素在哪"需要计算——这又回到了 [[range.filter]] 中讨论过的 `begin()` 缓存问题。

## `views::drop` 的表达式等价规则（[range.drop.overview]）

¶1 `drop_view` 产生排除前 N 个元素的视图；元素少于 N 时产生空范围。¶2 令 `T` = `remove_cvref_t<decltype((E))>`，`D` = `range_difference_t<decltype((E))>`；`F` 不能转换为 `D` 时非良构。否则：

| 条 | `T` 是 | 结果 |
|---|---|---|
| 2.1 | `empty_view` | `((void)F, decay-copy(E))` |
| 2.2 | 建模 `view` 的 `optional`（{{c++26}}） | `F == 0 ? decay-copy(E) : ((void)E, T())` |
| 2.3 | random access + sized 的 `span`、`basic_string_view`、`iota_view`、或 *StoreSize* 为假的 `subrange` | `U(ranges::begin(E) + std::min<D>(ranges::distance(E), F), ranges::end(E))`；`span` 得 `span<element_type>`，其余为 `T` |
| 2.4 | random access + sized 的 `subrange`（*StoreSize* 为真） | `T(begin + min(dist, F), end, to-unsigned-like(dist - min(dist, F)))` |
| 2.5 | `repeat_view` | 有界：`views::repeat(*E.value_, distance(E) - min(distance(E), F))`；无界：`((void)F, decay-copy(E))` |
| 2.6 | 其他 | `drop_view(E, F)` |

与 [[range.take]] 一样，这些特例保持结果类型与输入同类（[[P1739R4]]）。2.5 的无界情形很有趣：无限个 `x` 去掉前 n 个仍是无限个 `x`，直接返回原视图。

## `drop_view`（[range.drop.view]）

```cpp
template<view V>
class drop_view : public view_interface<drop_view<V>> {
public:
  constexpr explicit drop_view(V base, range_difference_t<V> count);   // ¶1 前置条件 count >= 0
  constexpr auto begin()
    requires (!(simple-view<V> && random_access_range<const V> && sized_range<const V>));
  constexpr auto begin() const
    requires random_access_range<const V> && sized_range<const V>;
  constexpr auto end() requires (!simple-view<V>) { return ranges::end(base_); }
  constexpr auto end() const requires range<const V> { return ranges::end(base_); }
  constexpr auto size() requires sized_range<V>;        // s < count ? 0 : s - count
  constexpr auto size() const requires sized_range<const V>;
  // reserve_hint 同理
private:
  V base_ = V();
  range_difference_t<V> count_ = 0;
};
```

¶3 两个 `begin()` 都返回 `ranges::next(ranges::begin(base_), count_, ranges::end(base_))`——以 `end` 为界前进，不会越界。

¶4 *Remarks*：

!!! std
    In order to provide the amortized constant-time complexity required by the range concept when drop_view models forward_range, the first overload caches the result within the drop_view for use on subsequent calls.

    为了在 drop_view 建模 forward_range 时提供 range 概念要求的摊还常数复杂度，第一个重载把结果缓存在 drop_view 内。

注 1 给出了真正的动机：**没有缓存的话，把 `reverse_view` 套在 `drop_view` 上会产生平方级的迭代复杂度**。`reverse_view::begin()` 需要 `drop_view::end()`，反向迭代器每一次解引用、比较都可能涉及 `drop_view` 的 `begin()`（例如反向迭代器与 `rend()` 比较，而 `rend()` 就是 `reverse_iterator(drop.begin())`）。若每次 `begin()` 都要走 n 步，总代价就是 O(n·m)。

注意 `begin() const` 的约束：只有 `const V` 是 **random access 且 sized** 时才有 const 版本——此时 `ranges::next` 是 O(1)，不需要缓存。所以：

- `vector | drop(2)`：const 可迭代，无缓存；
- `list | drop(2)`：**没有** const `begin()`，第一次 `begin()` 走两步并缓存。

!!! impl "libc++"
    libc++ 的 `drop_view` 只在 `forward_range<V> && !(random_access_range<V> && sized_range<V>)` 时存放 `__non_propagating_cache<iterator_t<V>>`。源码注释说明了对输入范围不缓存的理由：输入范围的 `begin()` 本就不保持相等性，而且只能调用一次，"平凡地"满足摊还 O(1)。

借用性：`enable_borrowed_range<drop_view<T>>` = `enable_borrowed_range<T>`。缓存的是**底层**迭代器，不指向 `drop_view` 本身，所以只要底层借用，结果就借用。

## `drop_while_view`（[range.drop.while]）

¶1 给定谓词 `pred` 与视图 `r`，产生 `[ranges::find_if_not(r, pred), ranges::end(r))`。¶2 `views::drop_while(E, F)` 表达式等价于 `drop_while_view(E, F)`。

```cpp
template<view V, class Pred>
  requires input_range<V> && is_object_v<Pred> &&
           indirect_unary_predicate<const Pred, iterator_t<V>>
class drop_while_view : public view_interface<drop_while_view<V, Pred>> {
public:
  constexpr const Pred& pred() const;
  constexpr auto begin();                    // 只有非 const 版本
  constexpr auto end() { return ranges::end(base_); }
private:
  V base_ = V();
  movable-box<Pred> pred_;
};
```

[range.drop.while.view] ¶3 前置条件 *pred_*`.has_value()`；¶4 返回 `ranges::find_if_not(base_, cref(*pred_))`；¶5 当它建模 `forward_range` 时**第一次调用缓存结果**，注 1 同样以"`reverse_view` 套在上面会平方"为理由。

- **永远没有 const `begin()`**——即使底层是 `vector`，跳过前缀的长度也要靠谓词逐个判断；
- 迭代器就是底层迭代器，所以强度、common 性同底层；
- 借用性随底层（缓存的是底层迭代器，`end()` 不涉及谓词）。这点与 `take_while` 相反：`take_while` 的哨位要调用谓词，所以不借用。

```cpp run ok
#include <list>
#include <ranges>
#include <string_view>
#include <vector>
#include <cstdio>
int main() {
  std::vector<int> v{1, 2, 3, 4, 5};
  std::list<int> l{1, 2, 3, 4, 5};
  using DV = decltype(v | std::views::drop(2));
  using DL = decltype(l | std::views::drop(2));
  static_assert(std::ranges::range<const DV>);    // random access + sized：begin() 直接 O(1) 计算
  static_assert(!std::ranges::range<const DL>);   // list：begin() 要缓存，没有 const 版本
  auto dw = std::string_view("   hi") | std::views::drop_while([](char c) { return c == ' '; });
  static_assert(!std::ranges::range<const decltype(dw)>);   // drop_while 永远缓存
  for (char c : dw | std::views::reverse) std::putchar(c);  // ih
  auto d = v | std::views::drop(10);                        // 超出长度：空，不越界
  std::printf(" %d\n", int(d.empty()));                     // 1
}
```

## 坑点

!!! pitfall "缓存后修改底层"
    与 `filter` 一样：`auto d = lst | views::drop(1); d.begin();` 之后再 `lst.push_front(0)`，`d.begin()` 仍指向原来的第二个节点，而不是新的第二个元素。`drop_while` 同理——缓存的"第一个不满足谓词的位置"不会因为你修改了前面的元素而更新。

!!! pitfall "输入范围上 drop 会立即消费"
    `views::istream<int>(in) | views::drop(3)` 的 `begin()` 会把前 3 个值（加上 `istream_view::begin` 自己读的那一个）从流里读掉。对输入范围来说，"创建视图"不消费，"第一次 `begin()`"才消费——但它确实消费了。

## 小结

| | `drop(n)` | `drop_while(p)` |
|---|---|---|
| 特化返回同类视图 | `empty`、`optional`、`span`、`string_view`、`iota`、`subrange`、`repeat` | 无 |
| begin 缓存 | forward 且非（random access + sized）时 | forward 时总是 |
| const 可迭代 | `const V` 为 random access + sized 时 | 从不 |
| sized | 随底层 | 否 |
| 借用 | 随底层 | 随底层 |
