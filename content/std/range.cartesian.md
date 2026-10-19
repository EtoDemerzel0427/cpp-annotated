---
title: cartesian_product 视图
summary: C++23 的 views::cartesian_product 把若干个范围的所有组合排成一个扁平的视图，顺序与嵌套循环相同；第一个范围可以只是输入范围，其余必须是前向范围；size() 的类型由实现决定，乘积必须能放得下。
status: draft
covers: *
since: c++23
papers: P2374R4
related: range.zip, range.adaptors, range.adaptor.helpers, range.join, range.factories, iterator.concept.winc
tags: 标准库, 范围, cartesian_product, 组合
updated: 2026-10-19
---

!!! tldr
    - `views::cartesian_product(A, B, C)` 依次给出 `(a, b, c)` 的所有组合，最后一个范围变化最快，与三重嵌套循环的顺序相同。
    - 元素是装着各分量引用的 `tuple`，结果可以接着用 `filter`、`take` 等适配器，也可以交给算法。
    - 第一个范围可以只是输入范围，其余必须是前向范围，因为内层循环每一轮都要从头再走一遍。
    - 除第一个外任何一个范围为空，整个结果就为空；不给任何实参时，结果是只含一个空 tuple 的视图。
    - `size()` 和 `difference_type` 的类型由实现决定，所有范围大小的乘积必须能用它表示。

```cpp
#include <cstdio>
#include <ranges>
#include <vector>

int main() {
  std::vector<int> xs{1, 2};
  std::vector<char> ys{'a', 'b', 'c'};
  for (auto [x, y] : std::views::cartesian_product(xs, ys))
    std::printf("%d%c ", x, y);               // 1a 1b 1c 2a 2b 2c
  std::puts("");

  // 找出所有满足 i*i + j*j == 25 的 (i, j)
  auto sq = std::views::cartesian_product(std::views::iota(0, 6), std::views::iota(0, 6))
          | std::views::filter([](auto t) { auto [i, j] = t; return i * i + j * j == 25; });
  for (auto [i, j] : sq) std::printf("(%d,%d)", i, j);   // (0,5)(3,4)(4,3)(5,0)
  std::puts("");
}
```

上面第一个循环相当于 `for (int x : xs) for (char y : ys) ...`。写成一个范围之后，嵌套循环就能接上其他适配器，第二个例子就是这样用 `filter` 筛选组合的。这个视图来自 C++23 的 [[P2374R4]]。

!!! impl "实现现状"
    截至写作时，本机 libc++ 还没有提供 `views::cartesian_product`。本页的代码按标准原文编写，没有经过编译验证。

## `views::cartesian_product` [range.cartesian.overview]

¶1 `cartesian_product_view` 接受非零个范围，给出它们的 n 元笛卡尔积，每个元素是一个 tuple。¶2 `views::cartesian_product` 是[[customization.point.object|定制点对象]]：

- ¶2.1 没有实参时，结果是 `views::single(tuple())`。零个集合的笛卡尔积按数学约定含有一个元素，即空 tuple，就像空乘积等于 1。
- ¶2.2 否则是 `cartesian_product_view<views::all_t<decltype((Es))>...>(Es...)`。

¶3 例 1 对 `v = {0, 1, 2}` 求 `cartesian_product(v, v, v)`，依次得到 `0 0 0`、`0 0 1`、`0 0 2`、`0 1 0`……，也就是字典序。

## 迭代器像一个多位数计数器 [range.cartesian.view]

```cpp
template<input_range First, forward_range... Vs>
  requires (view<First> && ... && view<Vs>)
class cartesian_product_view;
```

迭代器保存一个由各范围的迭代器组成的 tuple。`++` 从最后一个分量开始：它前进一步，如果到达末尾，就重置为该范围的起点，并让前一个分量前进一步。这和给一个多位数加 1、逢十进位是同一个过程。

这也解释了模板参数的要求：除第一个以外的范围在进位时都要重置到起点，相当于重新遍历一次，所以必须是前向范围；第一个范围只走一遍，输入范围就够了。

### 各种能力的条件

| 能力 | 条件（说明用概念） | 原因 |
|---|---|---|
| 随机访问 | 全部随机访问，且除第一个外都 sized | `it += n` 要把 n 按各维长度拆分，需要知道这些长度 |
| 双向 | 全部双向，且除第一个外都是公共范围或随机访问且 sized | `--` 借位时要跳到内层维度的最后一个元素，必须能得到它的尾迭代器 |
| 公共范围 | 第一个范围是公共范围，或随机访问且 sized | 终点迭代器要用第一个范围的尾迭代器构造 |
| sized | 全部 sized | 大小是各维大小之积 |

`cartesian_product_view` 不是借用范围。所有范围都能以 const 方式遍历时，它也能（¶3）。

### 终点和空范围（¶4–¶6）

在公共范围的情况下，¶5 `end()` 返回一个迭代器：第一个分量是第一个范围的末尾，其余分量是各自的起点。这正是最后一次进位溢出之后的状态。

但如果除第一个外有某个范围是空的，整个积就是空的，此时 `end()` 必须等于 `begin()`。¶4.2 为此定义了 *is-empty*：这种情况下第一个分量也取起点，而不是末尾。

不是公共范围时，¶6 `end()` 返回 `default_sentinel`。[range.cartesian.iterator] ¶23 规定，迭代器的任何一个分量到达了自己所在范围的末尾，就等于这个哨位，这同样覆盖了某个内层范围为空的情况。

### size() 的类型（¶7–¶11）

三个大小为 2³² 的范围相乘就超出了 64 位整数的范围。所以 ¶7 规定 `size()` 的返回类型是实现定义的无符号的类整数类型（integer-like type，可以是比 `size_t` 更宽的类类型，见 [[iterator.concept.winc]]）。¶8 建议它取能放下各范围最大大小之积的最小类型。¶9–¶11 返回各范围大小之积 p，前置条件是 p 能用返回类型表示。

迭代器的 `difference_type` 同理是实现定义的有符号类整数类型（[range.cartesian.iterator] ¶2–¶3）。随机访问运算要求按各维长度换算后的距离能用它表示（¶7）。

## 小结

- 顺序与嵌套循环相同，最后一个范围变化最快；第一个范围可以是输入范围，其余必须是前向范围。
- 随机访问、双向、公共范围、sized 各有条件，核心都是除第一维外需要知道长度或末尾。
- 任一非首维为空则整体为空；没有实参时得到 `single(tuple())`。
- `size()` 的类型由实现决定，乘积必须能放得下。

<details class="fine" markdown="1"><summary>其余条文</summary>

[range.cartesian.view] ¶1–¶3：构造函数保存所有范围；`begin()` 由各范围的起点组成。

[range.cartesian.iterator] ¶1 规定迭代器类别；¶4–¶5 是进位和借位用的 *next*、*prev*；¶6–¶8 是计算两个位置之间距离的 *distance-from*；¶9–¶10 是构造函数；之后各段规定自增自减、`+=`（¶15–¶19，常数复杂度）、比较、相减、`iter_move` 和 `iter_swap`。

</details>
