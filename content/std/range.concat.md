---
title: concat 视图
summary: C++26 的 views::concat 把几个类型可以不同的范围首尾相接成一个视图；元素的引用类型取各范围引用类型的公共引用，可能变成不可写的副本；它是定制点对象，不能用管道写法。
status: done
covers: *
since: c++26
papers: P2542R8
related: range.adaptors, range.join, range.zip, range.adaptor.helpers, range.req, iterator.concepts, customization.point.object
tags: 标准库, 范围, concat, C++26
updated: 2026-10-19
---

!!! tldr
    - `views::concat(a, b, c)` 把个数在编译期已知、类型可以各不相同的几个范围连成一个视图；空范围被自动跳过。
    - 元素的引用类型是各范围引用类型的 `common_reference_t`：`int&` 与 `int&` 得 `int&`，可以写回；`int&` 与 `long&` 得 `long`，每次解引用得到一个副本。
    - 结果的迭代器类别取各范围中最弱的一个；要双向或随机访问，除最后一个外的范围还必须是公共范围。
    - `views::concat` 是定制点对象，不是范围适配器，没有 `a | views::concat(b)` 这种写法。

```cpp run ok
#include <array>
#include <cstdio>
#include <ranges>
#include <vector>

int main() {
  std::vector<int> v1{1, 2, 3}, v2{4, 5}, v3{};
  std::array a{6, 7, 8};
  auto s = std::views::single(9);
  for (auto&& i : std::views::concat(v1, v2, v3, a, s))
    std::printf("%d ", i);                    // 1 2 3 4 5 6 7 8 9
  std::puts("");
}
```

这是 [range.concat.overview] ¶2 的例 1。`vector`、`array`、`single_view` 类型各不相同，`v3` 是空的，它们被连成一个序列。

`concat` 和 [[range.join]] 都能把几段连起来，区别在于输入的形状：`join` 处理一个范围的范围，内层的类型都相同，个数在运行时决定；`concat` 处理编译期已知个数、类型各异的几个范围。它来自 C++26 的 [[P2542R8]]。

## `views::concat` [range.concat.overview]

¶1 `concat_view` 给出一个把所有底层范围连接起来的视图。¶2 `views::concat` 是一个[[customization.point.object|定制点对象]]。给定一组子表达式 `Es...`：

- ¶2.1 只有一个实参且它是输入范围时，等价于 `views::all(Es...)`，不包装；
- ¶2.2 否则等价于 `concat_view(Es...)`。

`concat_view` 要求至少有一个视图，所以 `views::concat()` 非良构。它也不是[[g:range-adaptor-object|范围适配器对象]]，没有管道形式：`a | views::concat(b)` 里的 `views::concat(b)` 按 ¶2.1 就是 `views::all(b)`，一个视图不能放在 `|` 右边，所以编译失败。

## 元素类型：取公共引用 [range.concat.view]

几个范围的元素类型可能不同，连起来以后，解引用要返回一个统一的类型。标准用三个说明用别名来定：

| 别名 | 定义 | 用途 |
|---|---|---|
| *concat-reference-t* | 各范围 `range_reference_t` 的 `common_reference_t` | `*it` 的类型 |
| *concat-value-t* | 各范围 `range_value_t` 的 `common_type_t` | `value_type` |
| *concat-rvalue-reference-t* | 各范围 `range_rvalue_reference_t` 的 `common_reference_t` | `iter_move` 的类型 |

¶2 说明用概念 *concatable* 要求这三个类型都存在，并满足 ¶1 的 *concat-indirectly-readable*：每个范围的 `*it` 能转换为 *concat-reference-t*，`iter_move(it)` 能转换为 *concat-rvalue-reference-t*，三者之间还要有 `indirectly_readable` 所需的公共引用关系。这样合成的迭代器才能是一个合格的输入迭代器。

公共引用的结果决定了元素能不能写回：

- 全是 `int&`，得到 `int&`，可以写回；
- `int&` 与 `const int&`，得到 `const int&`，只读；
- `int&` 与 `long&`，得到 `long`，这是一个纯右值（prvalue），每次解引用产生一个转换后的副本，写它不会影响原容器。

```cpp run ok
#include <cstdio>
#include <list>
#include <ranges>
#include <vector>

int main() {
  std::vector<int> a{1, 2};
  std::list<int> b{3, 4};
  auto cat = std::views::concat(a, b);
  for (int& x : cat) x *= 10;                  // int&：写回 a 和 b
  for (int x : cat) std::printf("%d ", x);     // 10 20 30 40
  std::puts("");

  std::vector<long> d{6};
  auto mixed = std::views::concat(a, d);
  static_assert(std::same_as<std::ranges::range_reference_t<decltype(mixed)>, long>);
}
```

当前草案中 [[range.join]] 的 `join_with_view` 也用 *concatable* 检查内层元素与分隔符是否兼容。

## 迭代器怎样在各段之间移动 [range.concat.iterator]

迭代器保存一个 `variant`，其中是当前所在那一段的底层迭代器，另外保存一个指向视图的指针。

[range.concat.view] ¶6 `begin()` 在第 0 段的开头构造迭代器，然后调用说明用函数 *satisfy*。[range.concat.iterator] ¶3 规定，*satisfy* 发现当前段已经走到末尾时，就切换到下一段的开头，并继续检查，直到找到非空的段或者到达最后一段。空范围就是这样被跳过的。

[range.concat.view] ¶7 `end()` 在所有段都是前向范围、且最后一段是公共范围时，返回指向最后一段末尾的迭代器，结果是公共范围；否则返回 `default_sentinel`。

### 双向和随机访问要求前面的段是公共范围（¶1）

¶1 迭代器的类别是各段类别中最弱的一个，但双向和随机访问还多一个条件：除最后一段外，每一段都必须是[[g:common-range|公共范围]]（[range.concat.view] ¶3–¶4）。

原因在 `--`（¶4）：从第 k+1 段的开头退回第 k 段时，要先拿到第 k 段末尾的迭代器，再退一步。如果第 k 段的 `end()` 只是一个哨位，就做不到。最后一段永远不会从后面退进来，所以它可以不是公共范围。跨段的 `+=` 和 `-=`（¶5–¶6）也是同样的道理。

¶2 `iterator_category` 只在所有段都是前向范围时定义；如果 *concat-reference-t* 不是引用类型，它是 `input_iterator_tag`，因为老式的前向迭代器要求解引用得到引用。

### 可以跨容器排序（¶41–¶42）

`iter_swap` 用 `std::visit` 分派：两个迭代器当前的底层迭代器类型相同时，调用底层的 `ranges::iter_swap`；否则退化为 `ranges::swap(*x, *y)`（¶42）。所以两个 `vector` 连起来后是随机访问范围，可以直接排序，结果写回两个容器：

```cpp run ok
#include <algorithm>
#include <cstdio>
#include <ranges>
#include <vector>

int main() {
  std::vector<int> a{5, 1, 4}, b{3, 2};
  auto cat = std::views::concat(a, b);
  static_assert(std::ranges::random_access_range<decltype(cat)>);
  std::ranges::sort(cat);
  for (int x : a) std::printf("%d ", x);       // 1 2 3
  for (int x : b) std::printf("%d ", x);       // 4 5
  std::printf("| size=%zu\n", cat.size());     // size=5
}
```

¶41 和其他许多操作一样，前置条件是 `variant` 不处于因异常而无值的状态。

## 其他性质

- [range.concat.view] ¶8 所有段都是 sized range 时才有 `size()`：先把各段大小转换为它们的公共无符号类型，再相加。¶9 的 `reserve_hint()` 同理。
- 所有 `const Views` 都是范围并满足 *concatable* 时，有 const 版本的 `begin()`。
- 不缓存 `begin()`。*satisfy* 每次都重新跳过开头的空段，代价与段数成正比，而段数是编译期常量。
- 不是借用范围。

!!! impl "实现现状"
    本机 libc++ 已提供 `views::concat`（`__cpp_lib_ranges_concat` 为 `202403L`），本页示例都在 libc++ 上验证过。

## 小结

| 方面 | `views::concat` |
|---|---|
| 实参 | 一个或多个类型可以不同的范围；只有一个时等于 `views::all` |
| 引用类型 | 各段引用类型的 `common_reference_t`，可能是不可写的副本 |
| 迭代器类别 | 各段中最弱的；双向和随机访问另要求除最后一段外都是公共范围 |
| 公共范围 | 全是前向范围且最后一段是公共范围时 |
| sized range | 全部是时 |
| 管道写法 | 没有 |

<details class="fine" markdown="1"><summary>其余条文</summary>

[range.concat.view] ¶5：构造函数保存所有视图。

[range.concat.iterator] ¶7–9 是构造函数（从非 const 迭代器转换时，按当前下标复制底层迭代器）；¶10–¶40 逐一规定解引用、自增自减、随机访问运算、比较和距离，每个操作都以 `variant` 有值为前置条件；`iter_move` 返回 *concat-rvalue-reference-t*。¶43 规定 `iter_swap` 的异常说明和约束。

</details>
