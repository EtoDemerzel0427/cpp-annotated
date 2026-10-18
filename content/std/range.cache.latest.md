---
title: cache_latest 与 as_input 视图
summary: 两个"降级换性能"的 C++26 视图——cache_latest 把最近一次解引用的结果存进视图的 non-propagating-cache，使 transform|filter 中的昂贵函数每个元素只算一次，代价是退化为输入范围、无 const 迭代、operator* 返回左值引用；as_input 把任意范围呈现为仅输入、非 common 的范围，以省掉为更强迭代器类别付出的开销（如 join、chunk 的额外状态）。
status: draft
covers: range.cache.latest, range.cache.latest.overview, range.cache.latest.view, range.cache.latest.iterator, range.cache.latest.sentinel, range.as.input, range.as.input.overview, range.as.input.view, range.as.input.iterator
since: c++26
related: range.transform, range.filter, range.nonprop.cache, range.adaptors, range.join, range.chunk, range.req
tags: 标准库, 范围, cache_latest, as_input, C++26
updated: 2026-10-18
---

前面的视图都在努力**保留**底层的能力（强度、common、sized）。这两个 C++26 视图反其道而行：主动把范围**降级为输入范围**，换取运行时效率。

!!! impl "实现现状"
    截至编写时 libc++ 尚未提供 `views::cache_latest` 与 `views::as_input`。本页代码按标准编写，未经本站环境运行验证。

## `views::cache_latest`（[range.cache.latest]）

¶1 `cache_latest_view` 缓存底层序列中最近一次访问的元素，使得重复访问时不必重新计算该元素。注 1：在计算元素代价高昂时很有用。¶2 `views::cache_latest(E)` 表达式等价于 `cache_latest_view(E)`。

### 它解决的问题

[[range.transform]] 中演示过：

```cpp
v | views::transform(expensive) | views::filter(pred)
```

`filter` 判断谓词时解引用一次（调用 `expensive`），使用者读取元素时又解引用一次（再调用一次）。插入 `cache_latest`：

```cpp
v | views::transform(expensive) | views::cache_latest | views::filter(pred)
```

`filter` 的两次解引用都落在 `cache_latest` 上，第一次计算并缓存，第二次直接返回缓存，`expensive` 每个元素只调用一次。

### 规范（[range.cache.latest.view]、[range.cache.latest.iterator]）

```cpp
template<input_range V> requires view<V>
class cache_latest_view : public view_interface<cache_latest_view<V>> {
  V base_ = V();
  using cache-t = conditional_t<is_reference_v<range_reference_t<V>>,
                                add_pointer_t<range_reference_t<V>>,
                                range_reference_t<V>>;
  non-propagating-cache<cache-t> cache_;
  class iterator;
  class sentinel;
public:
  constexpr auto begin();     // 只有非 const 版本
  constexpr auto end();
  constexpr auto size() requires sized_range<V>;
  // ...
};
```

- 缓存的类型 *cache-t*：底层引用是引用时存**指针**，是 prvalue 时存**值**；
- 迭代器 `operator*`（¶6）：若缓存为空，就 `cache_ = addressof(as-lvalue(*current_))` 或 `cache_.emplace-deref(current_)`（[[range.nonprop.cache]]），然后返回缓存——**返回类型是 `range_reference_t<V>&`**，即使底层是 prvalue，也得到一个指向缓存对象的左值引用；
- `++`（¶4）：先 `parent_->cache_.reset()`，再推进底层；
- 迭代器只可移动，`iterator_concept` 是 `input_iterator_tag`；`begin()` 只有非 const 版本——缓存存在**视图对象**里，所以只能有一个活跃的迭代器，这正是输入范围的语义；
- 不是借用范围。

!!! pitfall "返回的引用只活到下一次 ++"
    `auto& x = *it; ++it;` 之后 `x` 指向的缓存已被 `reset()`（prvalue 情形下对象被销毁）——继续使用 `x` 是{{ub}}。这与输入迭代器的一般语义一致：输入迭代器递增后，之前的引用不保证有效。

!!! tip "什么时候不需要它"
    若 `transform` 之后没有会重复解引用的适配器（例如直接 `for` 循环或交给 `ranges::to`），每个元素本来就只解引用一次，加 `cache_latest` 只会让范围失去前向能力。它是给 `filter`、`take_while`、`chunk_by` 这类"先看一眼再决定"的下游准备的。

## `views::as_input`（[range.as.input]）

¶1 `as_input_view` 把底层序列呈现为**仅输入、非 common** 的范围。注 1：这可以避免为支持更强迭代器类别所需操作而可能产生的开销。

¶2 令 `T` 为 `decltype((E))`，`views::as_input(E)` 表达式等价于：

- ¶2.1 `views::all(E)`，若 `T` 建模 `input_range`、**不满足** `common_range`、也**不满足** `forward_range`（已经是"仅输入、非 common"）；
- ¶2.2 否则 `as_input_view(E)`。

```cpp
template<input_range V> requires view<V>
class as_input_view : public view_interface<as_input_view<V>> {
  V base_ = V();
  template<bool Const> class iterator;
public:
  constexpr auto begin() requires (!simple-view<V>);   // iterator<false>(ranges::begin(base_))
  constexpr auto begin() const requires range<const V>;
  constexpr auto end() requires (!simple-view<V>);      // ranges::end(base_)：底层哨位/迭代器直接作哨位
  constexpr auto end() const requires range<const V>;
  constexpr auto size() requires sized_range<V>;
  // ...
};
```

迭代器（[range.as.input.iterator]）包装底层迭代器，`iterator_concept` 为 `input_iterator_tag`，只可移动；`end()` 直接返回底层的 `end`，因此首尾类型不同（非 common）。借用性随底层（[[ranges.syn]]）。

### 为什么要"降级"

很多适配器在底层更强时会做更多的事：

- [[range.join]]：外层是前向范围时，迭代器要同时保存外层与内层迭代器，并维护双向所需的状态；外层仅输入时则把外层迭代器放进视图缓存，迭代器更小；
- [[range.chunk]]：输入版本的 `chunk_view` 不必计算 `missing_`、不必支持随机访问跳转；
- 各种 `begin()` 缓存只在 `forward_range` 时才需要（[[range.filter]]、[[range.drop]]）。

如果你只打算遍历一遍，`as_input` 告诉下游"不必为多趟/反向/随机访问做准备"，有时能换来更小的迭代器与更少的分支。

```cpp run
#include <ranges>
#include <vector>
#include <cstdio>
int main() {
  std::vector<std::vector<int>> vv{{1, 2}, {3}};
  auto j = vv | std::views::as_input | std::views::join;        // C++26；libc++ 尚未提供
  static_assert(std::ranges::input_range<decltype(j)> && !std::ranges::forward_range<decltype(j)>);
  for (int x : j) std::printf("%d", x);
  std::puts("");   // 123
}
```

## 小结

| | `cache_latest` | `as_input` |
|---|---|---|
| 目的 | 避免重复计算元素 | 避免为更强类别付出开销 |
| 结果强度 | input，非 common | input，非 common |
| 引用类型 | `range_reference_t<V>&`（缓存的左值） | 同底层 |
| const 迭代 | 否 | 随底层 |
| 借用 | 否 | 随底层 |
