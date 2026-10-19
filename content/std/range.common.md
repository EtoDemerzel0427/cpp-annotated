---
title: common 与 counted 视图
summary: views::common 把迭代器与哨位类型不同的视图变成首尾同类型的视图，供只接受一对迭代器的旧接口使用；views::counted(it, n) 把一个迭代器和一个个数变成范围，按迭代器的能力返回 span、subrange 或基于 counted_iterator 的 subrange。
status: done
covers: range.common, range.common.overview, range.common.view, range.counted
since: c++20
papers: P0896R4
related: range.take, range.req, range.subrange, iterators.common, counted.iterator, views.span, range.utility.conv, iterator.requirements.general
tags: 标准库, 范围, common, counted, 遗留接口
updated: 2026-10-19
---

!!! tldr
    - C++20 的范围可以用一个与迭代器类型不同的哨位表示终点，而 `std::accumulate` 这类旧接口要求 `first` 和 `last` 类型相同；`views::common` 负责转换。
    - 已经是公共范围时，`views::common` 不做包装；随机访问且 sized 时，只是把终点算成迭代器；其余情况用 `common_iterator` 包装，迭代器类别最多降为前向。
    - 迭代器只能移动、不能复制的视图（如 `istream_view`）不能用 `views::common`。
    - `views::counted(it, n)` 不检查 n：`it` 之后不足 n 个元素是未定义行为，这一点与会截断的 `views::take` 不同。

```cpp run ok
#include <cstdio>
#include <list>
#include <numeric>
#include <ranges>

int main() {
  std::list<int> l{1, 2, 3, 4};
  auto t = l | std::views::take(3);          // 迭代器与终点类型不同
  auto c = t | std::views::common;           // 首尾同类型
  int sum = std::accumulate(c.begin(), c.end(), 0);
  std::printf("%d\n", sum);                  // 6
}
```

`std::accumulate(t.begin(), t.end(), 0)` 编译不过：`t.begin()` 是 `counted_iterator`，`t.end()` 是 `default_sentinel_t`，模板参数推导出两个不同的类型。`views::common` 把两者变成同一个类型，旧接口就能用了。`views::counted` 走的是相反方向：把旧式的迭代器加个数变成范围。

## `views::common` [range.common]

¶1 `common_view` 接受一个迭代器与哨位类型不同的视图，把它变成元素相同、迭代器与哨位类型相同的视图，也就是[[g:common-range|公共范围]]。¶2 注 1 说明了它的用途：调用要求迭代器和哨位类型相同的旧算法。¶4 例 1 正是这种用法：

```cpp
template<forward_range R>
void my_algo(R&& r) {
  auto&& common = views::common(r);
  auto cnt = count(common.begin(), common.end());   // 旧式 count，要求同类型
}
```

¶3 `views::common(E)` 等价于：

- ¶3.1 `E` 已经是公共范围时，`views::all(E)`，不做包装；
- ¶3.2 否则 `common_view{E}`。

### 两种转换方式 [range.common.view]

`common_view` 的 `begin()` 和 `end()` 按底层视图的能力选择：

- 底层随机访问且 sized 时，`begin()` 就是底层迭代器，`end()` 是 `begin + distance`。终点被算成了一个迭代器，迭代器类别保持随机访问。
- 其他情况，首尾都包进 `common_iterator<I, S>`（[[iterators.common]]）。它内部是一个 `variant<I, S>`，既可以装迭代器，也可以装哨位，比较时分情况处理。

`common_iterator` 不提供 `--`，所以它最多是前向迭代器。`list | take(3)` 本来是双向范围，经过 `views::common` 后变成前向范围。

`common_view` 的约束要求底层迭代器可复制（`copyable<iterator_t<V>>`），因为 `common_iterator` 要求这一点。`istream_view` 的迭代器只能移动，所以 `views::istream<int>(in) | views::common` 编译失败。

```cpp run ok
#include <list>
#include <ranges>
#include <vector>

int main() {
  std::list<int> l{1, 2, 3, 4};
  auto t = l | std::views::take(3);
  auto c = t | std::views::common;
  static_assert(std::ranges::bidirectional_range<decltype(t)>);
  static_assert(std::ranges::common_range<decltype(c)>);
  static_assert(!std::ranges::bidirectional_range<decltype(c)>);   // 降为前向

  std::vector<int> v{1, 2, 3};
  auto same = v | std::views::common;        // 已是公共范围：只是 views::all
  static_assert(std::same_as<decltype(same), std::ranges::ref_view<std::vector<int>>>);
}
```

`size()` 和 `reserve_hint()` 直接转发给底层。底层是[[g:borrowed-range|借用范围]]时，`common_view` 也是。

!!! tip "需要 views::common 的场合越来越少"
    C++23 起容器可以用 `from_range` 构造，`ranges::to` 会自己选择合适的做法（[[range.utility.conv]]），`std::ranges` 中的算法都接受迭代器加哨位。`views::common` 主要剩下与第三方库或旧 API 交互的用途。

## `views::counted`：迭代器加个数 [range.counted]

¶1 counted 视图给出**计数范围**（counted range）`i + [0, n)` 中的元素，也就是从迭代器 `i` 开始的 n 个元素（[[iterator.requirements.general]]），其中 n 非负。

¶2 `views::counted` 是[[customization.point.object|定制点对象]]，不是范围适配器，没有管道写法。令 `T` 为 `E` 退化后的类型，`D` 为它的差值类型。`F` 不能转换为 `D` 时非良构；注 1 指出，这在模板的直接语境中会导致替换失败。否则 `views::counted(E, F)` 等价于：

| 段 | `T` 是 | 结果 |
|---|---|---|
| ¶2.1 | 连续迭代器 | `span(to_address(E), n)`，动态长度 |
| ¶2.2 | 随机访问迭代器 | `subrange(E, E + n)` |
| ¶2.3 | 其他 | `subrange(counted_iterator(E, n), default_sentinel)` |

```cpp run ok
#include <iterator>
#include <list>
#include <ranges>
#include <span>
#include <vector>

int main() {
  std::vector<int> v{1, 2, 3, 4, 5};
  auto c1 = std::views::counted(v.begin() + 1, 3);
  static_assert(std::same_as<decltype(c1), std::span<int>>);

  std::list<int> l{1, 2, 3};
  auto c2 = std::views::counted(l.begin(), 2);
  static_assert(std::same_as<decltype(c2),
      std::ranges::subrange<std::counted_iterator<std::list<int>::iterator>,
                            std::default_sentinel_t>>);
  return (c1[0] == 2 && std::ranges::distance(c2) == 2) ? 0 : 1;
}
```

使用时要注意：

- n 不做检查。`i + [0, n)` 必须是一个有效的计数范围，否则行为未定义。`views::counted(v.begin(), 100)` 对 5 个元素的 `vector` 是{{ub}}；`views::take(100)` 则会截断到实际长度。
- 结果总是借用范围（`span` 和 `subrange` 都是），它只引用 `E` 所指的存储，不拥有元素。
- ¶2.3 的结果是 sized range（`counted_iterator` 与 `default_sentinel` 可以相减），但不是公共范围。

## 小结

| | `views::common` | `views::counted` |
|---|---|---|
| 种类 | 范围适配器对象，可以用管道 | 定制点对象，不能用管道 |
| 输入 | 一个视图 | 迭代器和个数 |
| 输出 | `views::all`、保留原迭代器的 `common_view`，或基于 `common_iterator` 的 `common_view` | `span`、`subrange` 或基于 `counted_iterator` 的 `subrange` |
| 检查 | 迭代器必须可复制 | 个数不检查，是前置条件 |

<details class="fine" markdown="1"><summary>其余条文</summary>

[range.common.view] ¶1：构造函数保存底层视图。推导指引 `common_view(R&&)` 把 `R` 经 `views::all_t` 包成视图。

</details>
