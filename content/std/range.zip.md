---
title: zip 家族：zip、zip_transform、adjacent、adjacent_transform
summary: C++23 的多序列适配器——zip 产出 tuple<引用...>、长度取最短、强度取交集、common 规则 zip-is-common 以及"任一分量相等即相等"的非双向比较技巧；zip_transform 对对应元素调用函数；adjacent<N>/pairwise 产出滑动窗口元组（迭代器存 N 个底层迭代器）；adjacent_transform<N>/pairwise_transform。
status: done
covers: range.zip, range.zip.overview, range.zip.view, range.zip.iterator, range.zip.sentinel, range.zip.transform, range.zip.transform.overview, range.zip.transform.view, range.zip.transform.iterator, range.zip.transform.sentinel, range.adjacent, range.adjacent.overview, range.adjacent.view, range.adjacent.iterator, range.adjacent.sentinel, range.adjacent.transform, range.adjacent.transform.overview, range.adjacent.transform.view, range.adjacent.transform.iterator, range.adjacent.transform.sentinel
since: c++23
papers: P2321R2
related: range.adaptors, range.adaptor.helpers, range.transform, range.enumerate, range.chunk, range.cartesian, range.concat, range.elements, tuple, pair
tags: 标准库, 范围, zip, adjacent, pairwise
updated: 2026-10-18
---

[[P2321R2]] 为 C++23 带来了"同时遍历多个序列"与"滑动窗口"两类视图。它们共享一套实现思路：迭代器内部是一个 `tuple` 的底层迭代器，`operator*` 用 *tuple-transform*（[[range.adaptor.helpers]]）把它们各自解引用后组成新元组。

## `views::zip`（[range.zip]）

¶1 `zip_view` 接受任意个视图，产生一个"由各视图对应元素的引用组成的元组"的视图。¶2 `views::zip` 是**定制点对象**；`views::zip(Es...)` 表达式等价于：

- ¶2.1 `Es` 为空包时：`auto(views::empty<tuple<>>)`；
- ¶2.2 否则：`zip_view<views::all_t<decltype((Es))>...>(Es...)`。

因为是 CPO 而非适配器对象，**没有管道写法**：`a | views::zip(b)` 不合法。

```cpp
template<class... Rs>
concept zip-is-common =
  (sizeof...(Rs) == 1 && (common_range<Rs> && ...)) ||
  (!(bidirectional_range<Rs> && ...) && (common_range<Rs> && ...)) ||
  ((random_access_range<Rs> && ...) && (sized_range<Rs> && ...));

template<input_range... Views>
  requires (view<Views> && ...) && (sizeof...(Views) > 0)
class zip_view : public view_interface<zip_view<Views...>> {
  tuple<Views...> views_;
  // ...
  constexpr auto size() requires (sized_range<Views> && ...);   // ¶3：各 size 转公共无符号类型后取 min
};
```

### 元素与长度

- 引用类型是 `tuple<range_reference_t<Views>...>`——一个**prvalue 元组，里面装着引用**。结构化绑定 `auto [x, y]` 中的 `x`、`y` 引用底层元素，可以写回；
- 值类型是 `tuple<range_value_t<Views>...>`。C++23 为了让这样的"引用元组"能满足 `indirectly_readable`，同时修改了 `tuple`/`pair` 本身（增加了 `const` 的赋值运算符、与 `basic_common_reference` 的特化），这也是 P2321 的一部分；
- **长度取最短**：遍历在任何一个分量到达末尾时停止；`size()` 是各 `size` 的最小值。

### 迭代器强度与 common 规则

强度是所有分量的**交集**（`all-random-access` → random access，依此类推）。¶1 规定：两个 `zip_view` 当且仅当各分量相等且有相同的底层序列时才"有相同底层序列"——比较来自不同 `zip_view` 的迭代器没有意义。

[range.zip.iterator] ¶13 的 `==` 有个精巧之处：

- 所有分量都双向时：**所有**分量都相等才相等；
- 否则：**任一**分量相等就算相等。注 1：这使得所有分量都 common 时 `zip_view` 也能是 common 的——`end()` 就是"各分量的 `end()` 组成的元组"，而由于长度不一，较长的分量永远到不了自己的 `end()`，只有最短的那个会命中。

但对双向迭代器这招不行（从 `end()` 往回 `--` 时，各分量需要退回到**同一个下标**，而它们的 `end()` 对应的下标不同）。于是 *zip-is-common* 的三种情形是：只有一个分量且 common；不全是双向但全是 common；全是随机访问且全 sized（此时 `end()` 可以由 `begin() + size()` 算出，各分量对齐到最短长度）。

- 借用：`enable_borrowed_range<zip_view<Views...>>` 当且仅当所有分量都借用。

```cpp run ok
#include <functional>
#include <map>
#include <ranges>
#include <string>
#include <vector>
#include <cstdio>
int main() {
  std::vector<int> v{1, 2, 3, 4};
  std::vector<char> c{'a', 'b', 'c'};
  for (auto [x, ch] : std::views::zip(v, c)) std::printf("%d%c ", x, ch);      // 长度取最短
  std::puts("");                                                                // 1a 2b 3c
  for (auto [x, ch] : std::views::zip(v, c)) x *= 10;                          // 元素是 tuple<int&, char&>
  for (int s : std::views::zip_transform(std::plus{}, v, v)) std::printf("%d ", s);
  std::puts("");   // 20 40 60 8（v 现在是 10 20 30 4）
  for (auto [p, q] : v | std::views::pairwise) std::printf("(%d,%d)", p, q);
  std::puts("");   // (10,20)(20,30)(30,4)
  for (int d : v | std::views::pairwise_transform(std::minus{})) std::printf("%d ", d);
  std::puts("");   // -10 -10 26
  std::map<std::string, int> m{{"x", 1}, {"y", 2}};
  for (auto& k : m | std::views::keys) std::printf("%s", k.c_str());
  for (int& val : m | std::views::values) val += 100;
  std::printf(" %d\n", m["y"]);   // xy 102
}
```

!!! pitfall "zip 的结果不能直接 ranges::sort 吗？"
    可以——C++23 起 `zip_view` 的迭代器提供 `iter_swap`（逐分量 `ranges::iter_swap`）与 `iter_move`，并且 `tuple<int&, char&>` 可以 const 赋值，`ranges::sort(views::zip(keys, vals))` 能把两个数组按 `keys` 一起排序。这正是 P2321 修改 `tuple`/`pair` 的动机之一。（C++20 时代这样做无法编译。）

## `views::zip_transform`（[range.zip.transform]）

¶1 `zip_transform_view` 接受一个可调用对象和任意个视图，其第 M 个元素是以各视图第 M 个元素调用该对象的结果。¶2 它是 CPO：

- ¶2.1 视图包为空时：令 `FD` = `decay_t<decltype((F))>`；若 `move_constructible<FD> && regular_invocable<FD&>` 不成立或结果不是对象类型，非良构；否则等价于 `((void)F, auto(views::empty<decay_t<invoke_result_t<FD&>>>))`；
- ¶2.2 否则 `zip_transform_view(F, Es...)`。

它就是"多元 `transform`"：内部持有一个 `zip_view` 和一个 *movable-box*`<F>`，每次解引用对分量调用 `f`——与 [[range.transform]] 一样**每次都调用**，C++17 类别在 `f` 返回 prvalue 时退化为 input，且**不是借用范围**。

## `views::adjacent<N>` 与 `views::pairwise`（[range.adjacent]）

¶1 `adjacent_view` 产生一个视图，其第 M 个元素是原视图第 M 到第 M+N−1 个元素的引用组成的元组；原视图元素少于 N 个时结果为空。¶2 `views::adjacent<N>(E)`：`N == 0` 且 `E` 是前向范围时为 `((void)E, auto(views::empty<tuple<>>))`，否则 `adjacent_view<views::all_t<decltype((E))>, N>(E)`。`views::pairwise` 是 `adjacent<2>` 的别名。

```cpp
template<forward_range V, size_t N>
  requires view<V> && (N > 0)
class adjacent_view;
```

- **要求前向范围**：窗口中的元素要能被同时引用；
- 迭代器存一个 `array<iterator_t<Base>, N>`，分别指向窗口里的 N 个位置，`++` 时全部前进一步——**N 是编译期常量**，元素是 `tuple<REPEAT(range_reference_t<V>, N)...>`（¶3 定义了 *REPEAT*）；
- 若窗口大小要在运行时决定，用 [[range.chunk]] 中的 `views::slide(n)`，它的元素是子范围而不是元组；
- `size()` = `max(size(base) - (N-1), 0)`；借用性随底层（迭代器不访问视图）。

## `views::adjacent_transform<N>` 与 `views::pairwise_transform`（[range.adjacent.transform]）

¶1 `adjacent_transform_view` 的第 M 个元素是以第 M 到 M+N−1 个元素为实参调用函数的结果。¶2 `N == 0` 且 `E` 是前向范围时等价于 `((void)E, views::zip_transform(F))`（E 与 F 求值顺序不定），否则 `adjacent_transform_view<views::all_t<decltype((E))>, decay_t<decltype((F))>, N>(E, F)`。`views::pairwise_transform` 是 `adjacent_transform<2>`。

典型用途：相邻差分（`pairwise_transform(std::minus{})`）、检测有序性、计算相邻元素的距离。不是借用范围。

## 小结

| 视图 | 元素 | 种类 | 强度 | 借用 |
|---|---|---|---|---|
| `zip(rs...)` | `tuple<引用...>` | CPO | 交集 | 全部借用时 |
| `zip_transform(f, rs...)` | `f(元素...)` | CPO | 交集 | 否 |
| `adjacent<N>` / `pairwise` | `tuple<N 个引用>` | 适配器 | 同底层（需 forward） | 随底层 |
| `adjacent_transform<N>(f)` / `pairwise_transform(f)` | `f(N 个元素)` | 适配器 | 同底层 | 否 |
