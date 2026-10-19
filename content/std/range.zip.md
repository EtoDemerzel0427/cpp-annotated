---
title: zip 家族：zip、zip_transform、adjacent、adjacent_transform
summary: C++23 的 views::zip 同时遍历几个范围，元素是由各范围对应元素的引用组成的 tuple，长度取最短；zip_transform 对对应元素调用函数；adjacent<N> 和 pairwise 给出长度为 N 的滑动窗口，adjacent_transform 对窗口调用函数。
status: done
covers: range.zip, range.zip.overview, range.zip.view, range.zip.iterator, range.zip.sentinel, range.zip.transform, range.zip.transform.overview, range.zip.transform.view, range.zip.transform.iterator, range.zip.transform.sentinel, range.adjacent, range.adjacent.overview, range.adjacent.view, range.adjacent.iterator, range.adjacent.sentinel, range.adjacent.transform, range.adjacent.transform.overview, range.adjacent.transform.view, range.adjacent.transform.iterator, range.adjacent.transform.sentinel
since: c++23
papers: P2321R2
related: range.adaptors, range.adaptor.helpers, range.transform, range.enumerate, range.chunk, range.cartesian, range.concat, range.elements, tuple, pair
tags: 标准库, 范围, zip, adjacent, pairwise
updated: 2026-10-19
---

!!! tldr
    - `views::zip(a, b)` 的元素是 `tuple<A&, B&>` 这样装着引用的临时 tuple，结构化绑定可以写回；遍历在最短的那个范围结束时停止。
    - 迭代器类别取各范围中最弱的一个；`zip` 和 `zip_transform` 是定制点对象，没有管道写法。
    - `ranges::sort(views::zip(keys, vals))` 能把两个数组按 `keys` 一起排序。
    - `views::adjacent<N>` 给出长度为 N 的滑动窗口，元素是 N 个引用组成的 tuple；`views::pairwise` 是 `adjacent<2>`。窗口长度在运行时才知道时用 `views::slide`。
    - `zip_transform`、`adjacent_transform` 对对应元素或窗口调用函数，相当于多元的 `transform`，不是借用范围。

```cpp run ok
#include <cstdio>
#include <ranges>
#include <vector>

int main() {
  std::vector<int> v{1, 2, 3, 4};
  std::vector<char> c{'a', 'b', 'c'};
  for (auto [x, ch] : std::views::zip(v, c))
    std::printf("%d%c ", x, ch);               // 1a 2b 3c：长度取最短
  for (auto [p, q] : v | std::views::pairwise)
    std::printf("(%d,%d)", p, q);              // (1,2)(2,3)(3,4)
  std::puts("");
}
```

[[P2321R2]] 为 C++23 加入了同时遍历多个序列和滑动窗口两类视图。它们的实现方式相同：迭代器内部是一组底层迭代器，`operator*` 把它们分别解引用，再组成一个 `tuple`（用的是 [[range.adaptor.helpers]] 中的 *tuple-transform*）。

## `views::zip` [range.zip]

¶1 `zip_view` 接受任意个视图，给出由各视图对应元素的引用组成的 tuple。¶2 `views::zip` 是[[customization.point.object|定制点对象]]：没有实参时得到一个元素类型为 `tuple<>` 的空视图，否则等价于 `zip_view<views::all_t<decltype((Es))>...>(Es...)`。因为它不是范围适配器对象，`a | views::zip(b)` 不合法。

### 元素和长度

`zip_view` 的元素有两个类型：

- 解引用的结果是 `tuple<range_reference_t<Views>...>`，即一个装着引用的 tuple 纯右值（[range.zip.iterator] ¶6）。`auto [x, y]` 复制的是这个 tuple，但其中的分量是引用，所以 `x`、`y` 指向底层元素，可以写回。
- `value_type` 是 `tuple<range_value_t<Views>...>`。

为了让这样的引用 tuple 满足 `indirectly_readable` 和 `indirectly_writable`，P2321 同时修改了 `tuple` 和 `pair` 本身：增加了 const 版本的赋值运算符，以及相应的 `basic_common_reference` 特化。

遍历在任何一个分量到达末尾时停止。[range.zip.view] ¶3 `size()` 是各分量大小（转换为公共的无符号类型后）的最小值。

```cpp run ok
#include <algorithm>
#include <cstdio>
#include <ranges>
#include <vector>

int main() {
  std::vector<int> keys{3, 1, 2};
  std::vector<char> vals{'c', 'a', 'b'};
  for (auto [k, v] : std::views::zip(keys, vals)) k *= 10;   // 写回 keys
  std::ranges::sort(std::views::zip(keys, vals));            // 按 keys 一起排序
  for (auto [k, v] : std::views::zip(keys, vals))
    std::printf("%d%c ", k, v);                               // 10a 20b 30c
  std::puts("");
}
```

排序能成立，是因为 ¶21 的 `iter_swap` 对每个分量分别调用 `ranges::iter_swap`，¶19 的 `iter_move` 同样逐分量进行，而 C++23 的 `tuple<int&, char&>` 可以对 const 对象赋值。C++20 里同样的代码无法编译。

### 迭代器类别和公共范围

¶1 迭代器的类别是各分量中最弱的一个：全部随机访问时是随机访问，全部双向时是双向，以此类推。[range.zip.view] ¶1 规定，两个 `zip_view` 只有在各分量都相等时才算有相同的底层序列，比较来自不同 `zip_view` 的迭代器没有意义。

¶13 的 `==` 有一个特别的设计：

- 所有分量都是双向迭代器时，所有分量都相等才相等；
- 否则，只要有一个分量相等就算相等。

后一种规则让 `zip_view` 可以是公共范围（注 1）。各分量的 `end()` 组成的 tuple 可以直接当作终点迭代器：长度不同时，较长的分量永远走不到自己的 `end()`，只有最短的那个会碰上，此时比较就成立。哨位的比较（[range.zip.sentinel] ¶3）用的也是任一分量相等的规则。

双向迭代器不能这样做：从终点 `--` 时，各分量必须退回到同一个下标，而它们的 `end()` 对应的下标各不相同。所以 `zip_view` 是公共范围的条件（说明用概念 *zip-is-common*）是下面三者之一：

- 只有一个分量，且它是公共范围；
- 分量不全是双向的，且全是公共范围；
- 全是随机访问且全是 sized，这时 `end()` 用 `begin() + size()` 算出，各分量都对齐到最短长度。

`zip_view` 在所有分量都是借用范围时也是[[g:borrowed-range|借用范围]]。

## `views::zip_transform` [range.zip.transform]

¶1 `zip_transform_view` 接受一个可调用对象和任意个视图，它的第 M 个元素是以各视图的第 M 个元素为实参调用该对象的结果。¶3 例 1：`zip_transform(plus(), {1, 2}, {4, 5, 6})` 得到 `5 7`。

¶2 它也是定制点对象。没有视图实参时，得到一个元素类型为函数返回类型的空视图；这时如果函数不能无参调用、或者返回的不是对象类型，就是非良构的。否则等价于 `zip_transform_view(F, Es...)`。

`zip_transform_view` 内部保存一个 `zip_view` 和函数对象，就是多元的 [[range.transform]]：每次解引用都调用一次函数；函数返回纯右值时，`iterator_category` 是 `input_iterator_tag`；它不是借用范围。

## `views::adjacent<N>` 与 `views::pairwise` [range.adjacent]

¶1 `adjacent_view` 的第 M 个元素是原视图第 M 到第 M+N−1 个元素的引用组成的 tuple；原视图不足 N 个元素时结果为空。¶2 `views::adjacent<N>(E)` 在 N 为 0 时得到元素类型为 `tuple<>` 的空视图，否则是 `adjacent_view<views::all_t<decltype((E))>, N>(E)`。`views::pairwise` 就是 `adjacent<2>`。

```cpp run ok
#include <cstdio>
#include <functional>
#include <ranges>
#include <vector>

int main() {
  std::vector v{1, 2, 3, 4};
  for (auto i : v | std::views::adjacent<2>)
    std::printf("(%d, %d) ", std::get<0>(i), std::get<1>(i));   // (1, 2) (2, 3) (3, 4)
  for (auto i : v | std::views::adjacent_transform<2>(std::multiplies()))
    std::printf("%d ", i);                                       // 2 6 12
  std::puts("");
}
```

`adjacent_view` 要求底层是前向范围，因为窗口里的 N 个元素要同时被引用。迭代器保存 N 个底层迭代器，分别指向窗口中的各个位置，`++` 时全部前进一步。元素类型是 N 个 `range_reference_t<V>` 组成的 tuple（¶3 定义了说明用的 *REPEAT*）。

N 是模板实参，所以窗口长度必须在编译期确定。运行时才知道长度时，用 [[range.chunk]] 中的 `views::slide(n)`，它的元素是子范围而不是 tuple。

[range.adjacent.view] ¶2 `size()` 是底层大小减去 N−1，最小为 0。迭代器不访问视图对象，所以底层是借用范围时 `adjacent_view` 也是。

## `views::adjacent_transform<N>` 与 `views::pairwise_transform` [range.adjacent.transform]

¶1 `adjacent_transform_view` 的第 M 个元素是以第 M 到第 M+N−1 个元素为实参调用函数的结果。¶2 N 为 0 时等价于 `views::zip_transform(F)`（同时求值 `E`），否则是 `adjacent_transform_view`。`views::pairwise_transform` 是 `adjacent_transform<2>`。

典型用途是相邻差分（`pairwise_transform(std::minus{})`）、检查是否有序、计算相邻点之间的距离。它和 `zip_transform` 一样不是借用范围。

```cpp run ok
#include <cstdio>
#include <functional>
#include <ranges>
#include <vector>

int main() {
  std::vector<int> v{10, 20, 30, 4};
  for (int d : v | std::views::pairwise_transform(std::minus{}))
    std::printf("%d ", d);                       // -10 -10 26
  std::puts("");
}
```

## 小结

| 视图 | 元素 | 种类 | 迭代器类别 | 借用范围 |
|---|---|---|---|---|
| `zip(rs...)` | `tuple<引用...>` | 定制点对象 | 各分量中最弱的 | 全部是时 |
| `zip_transform(f, rs...)` | `f(元素...)` | 定制点对象 | 各分量中最弱的 | 否 |
| `adjacent<N>`、`pairwise` | N 个引用组成的 tuple | 范围适配器 | 与底层相同（至少前向） | 底层是时 |
| `adjacent_transform<N>(f)`、`pairwise_transform(f)` | `f(N 个元素)` | 范围适配器 | 与底层相同 | 否 |

<details class="fine" markdown="1"><summary>其余条文</summary>

[range.zip.iterator] ¶3：迭代器的非 const 成员函数抛出异常时，迭代器变为奇异值。¶17–¶18 与 [range.zip.sentinel] ¶4–¶5：两个迭代器之差取各分量之差中绝对值最小的那个。¶20、¶22 规定 `iter_move` 和 `iter_swap` 的异常说明。

[range.zip.transform.view]、[range.adjacent.iterator]、[range.adjacent.transform.iterator] 及各自的哨位条款逐一规定构造函数和运算，都转发给内部的 `zip_view` 或底层迭代器数组。

</details>
