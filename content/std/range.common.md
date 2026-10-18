---
title: common 与 counted 视图
summary: views::common 把首尾类型不同的视图包装成 common range 以喂给 C++17 风格的接口——已 common 时直接 views::all、随机访问+sized 时只算出尾迭代器、否则用 common_iterator（要求迭代器可复制，强度最多 forward）；views::counted(it, n) 按迭代器强度产出 span / subrange / counted_iterator 子范围。
status: done
covers: range.common, range.common.overview, range.common.view, range.counted
since: c++20
papers: P0896R4
related: range.take, range.req, range.subrange, iterators.common, counted.iterator, views.span, range.utility.conv, iterator.requirements.general
tags: 标准库, 范围, common, counted, 遗留接口
updated: 2026-10-18
---

C++20 允许范围的尾是一个与迭代器不同类型的哨位，而 C++17 及以前的所有接口——`std::accumulate`、容器的迭代器对构造函数、大量第三方库——都要求 `first`、`last` **同类型**。这两个小设施负责在两个世界之间搭桥：`views::common` 统一首尾类型，`views::counted` 把"迭代器 + 个数"变成范围。

## `views::common`（[range.common]）

¶1 `common_view` 接受一个迭代器与哨位类型不同的视图，把它变成元素相同、迭代器与哨位类型相同的视图。¶2 注 1：它对调用"要求迭代器和哨位同类型"的遗留算法很有用。

¶3 `views::common(E)` 表达式等价于：

- ¶3.1 `views::all(E)`，若 `decltype((E))` 建模 `common_range` 且 `views::all(E)` 良构；
- ¶3.2 否则 `common_view{E}`。

所以对已经 common 的范围，`views::common` **什么也不包装**。

```cpp
template<view V>
  requires (!common_range<V> && copyable<iterator_t<V>>)
class common_view : public view_interface<common_view<V>> {
  V base_ = V();
public:
  constexpr auto begin() requires (!simple-view<V>) {
    if constexpr (random_access_range<V> && sized_range<V>)
      return ranges::begin(base_);
    else
      return common_iterator<iterator_t<V>, sentinel_t<V>>(ranges::begin(base_));
  }
  constexpr auto end() requires (!simple-view<V>) {
    if constexpr (random_access_range<V> && sized_range<V>)
      return ranges::begin(base_) + ranges::distance(base_);
    else
      return common_iterator<iterator_t<V>, sentinel_t<V>>(ranges::end(base_));
  }
  // const 版本同理；size / reserve_hint 转发
};
```

两条路径：

1. **随机访问 + sized**：不需要包装，`end()` 直接算出 `begin + size`——结果迭代器仍是原生迭代器，保留随机访问；
2. **其他**：用 `common_iterator<I, S>`（[[iterators.common]]），它内部是 `variant<I, S>`，既可以装迭代器也可以装哨位，比较时分情况。

约束 `copyable<iterator_t<V>>`：`common_iterator` 要求迭代器可复制。所以 `istream_view`（迭代器只能移动）不能 `views::common`——编译失败。

`common_iterator` 的强度**最多是 forward**（它不提供 `--`），所以 `list | take(3)` 本来是双向的，经过 `views::common` 后变成前向。借用性随底层。

```cpp run ok
#include <list>
#include <ranges>
#include <vector>
#include <numeric>
#include <cstdio>
int main() {
  std::list<int> l{1, 2, 3, 4};
  auto t = l | std::views::take(3);                   // counted_iterator + default_sentinel
  auto c = t | std::views::common;                    // common_iterator 包装
  static_assert(std::ranges::common_range<decltype(c)>);
  static_assert(std::ranges::bidirectional_range<decltype(t)>);
  static_assert(!std::ranges::bidirectional_range<decltype(c)>);   // common_iterator 最多 forward
  int sum = std::accumulate(c.begin(), c.end(), 0);  // C++17 算法要求首尾同类型
  std::vector<int> v{1, 2, 3};
  auto same = v | std::views::common;                 // 已经 common：views::all，不包装
  static_assert(std::same_as<decltype(same), std::ranges::ref_view<std::vector<int>>>);
  std::printf("%d\n", sum);   // 6
}
```

!!! tip "需要 common 的场合越来越少"
    C++23 起，容器可以用 `from_range` 构造、`ranges::to` 会自动选择合适的路径（[[range.utility.conv]]），`std::ranges::` 算法全部接受迭代器-哨位对。`views::common` 主要剩下与第三方/遗留 API 交互的用途。

## `views::counted`（[range.counted]）

¶1 counted 视图呈现**计数范围**（counted range，[[iterator.requirements.general]]）`i + [0, n)` 的元素，`i` 为迭代器、`n` 为非负整数。

¶2 `views::counted` 是**定制点对象**（不是适配器，因此不能用管道）。令 `T` = `decay_t<decltype((E))>`，`D` = `iter_difference_t<T>`。若 `F` 不能转换为 `D`，非良构（注 1：在模板立即语境中可导致替换失败）。否则 `views::counted(E, F)` 表达式等价于：

| 条 | `T` 建模 | 结果 |
|---|---|---|
| 2.1 | `contiguous_iterator` | `span(to_address(E), static_cast<size_t>(static_cast<D>(F)))` |
| 2.2 | `random_access_iterator` | `subrange(E, E + static_cast<D>(F))`（E 只求值一次） |
| 2.3 | 其他 | `subrange(counted_iterator(E, F), default_sentinel)` |

```cpp run ok
#include <list>
#include <ranges>
#include <span>
#include <vector>
#include <iterator>
int main() {
  std::vector<int> v{1, 2, 3, 4, 5};
  auto c1 = std::views::counted(v.begin() + 1, 3);
  static_assert(std::same_as<decltype(c1), std::span<int>>);           // contiguous → span
  std::list<int> l{1, 2, 3};
  auto c2 = std::views::counted(l.begin(), 2);
  static_assert(std::same_as<decltype(c2),
      std::ranges::subrange<std::counted_iterator<std::list<int>::iterator>, std::default_sentinel_t>>);
  return (c1[0] == 2 && std::ranges::distance(c2) == 2) ? 0 : 1;
}
```

要点：

- **`n` 是前置条件，不做检查**：`i + [0, n)` 必须是有效的计数范围。`views::counted(v.begin(), 100)` 对 5 个元素的 `vector` 是{{ub}}——与 `views::take` 截断到实际长度不同；
- **结果是借用的**（`span`、`subrange` 都是），它只是借用 `E` 指向的存储；
- `counted_iterator` 版本是 sized 的（`counted_iterator` 与 `default_sentinel` 可求差），但不是 common；
- 2.1 产生的是**动态 extent** 的 `span`，可以直接交给接受 `span` 的接口。

## 小结

| | `views::common` | `views::counted` |
|---|---|---|
| 种类 | 范围适配器对象（可管道） | CPO（不可管道） |
| 输入 | 视图 | 迭代器 + 个数 |
| 输出 | 已 common → `all`；随机访问+sized → 原生迭代器；否则 `common_iterator` | `span` / `subrange` / `subrange<counted_iterator>` |
| 检查 | 迭代器须可复制 | 个数不检查（前置条件） |
