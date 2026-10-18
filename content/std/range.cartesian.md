---
title: cartesian_product 视图
summary: C++23 的 views::cartesian_product(rs...) 按字典序（最后一个范围变化最快）产出所有组合的元组——第一个范围可以是输入范围、其余必须是前向范围；end() 的 is-empty 技巧；强度、common、sized 的分别条件；size() 返回实现定义的无符号整数类类型且乘积必须可表示；空包时得到含一个空元组的视图。
status: draft
covers: *
since: c++23
papers: P2374R4
related: range.zip, range.adaptors, range.adaptor.helpers, range.join, range.factories, iterator.concept.winc
tags: 标准库, 范围, cartesian_product, 组合
updated: 2026-10-18
---

嵌套循环

```cpp
for (auto a : A) for (auto b : B) for (auto c : C) f(a, b, c);
```

用 `views::cartesian_product(A, B, C)` 可以写成一个扁平的范围，从而能接上其他适配器（`filter`、`take`……）或交给算法。来自 C++23 的 [[P2374R4]]。

!!! impl "实现现状"
    截至编写时 libc++ 尚未提供 `views::cartesian_product`。本页代码按标准编写，未经本站环境运行验证。

## 概览（[range.cartesian.overview]）

¶1 `cartesian_product_view` 接受非零个范围，产生它们 n 元笛卡尔积的元组组成的视图。¶2 `views::cartesian_product` 是**定制点对象**：

- ¶2.1 空包：`views::single(tuple())`——零个集合的笛卡尔积是**一个**空元组（数学上的约定，类比空积为 1）；
- ¶2.2 否则 `cartesian_product_view<views::all_t<decltype((Es))>...>(Es...)`。

¶3 例 1：对 `v = {0,1,2}`，`cartesian_product(v, v, v)` 依次产生 `(0,0,0) (0,0,1) (0,0,2) (0,1,0) …`——**最后一个分量变化最快**，即字典序，与嵌套循环一致。

## 类模板（[range.cartesian.view]）

```cpp
template<input_range First, forward_range... Vs>
  requires (view<First> && ... && view<Vs>)
class cartesian_product_view : public view_interface<cartesian_product_view<First, Vs...>> {
  tuple<First, Vs...> bases_;
  template<bool Const> class iterator;
  // ...
};
```

**第一个范围可以只是输入范围，其余必须是前向范围**：嵌套循环的外层只走一遍，内层每轮都要从头再来（多趟），所以内层必须可以重新 `begin()`。

迭代器存一个底层迭代器元组 `current_`；`++` 从最后一个分量开始递增，到末尾就重置为 `begin` 并向前一个分量"进位"——就是多位数加一的过程。

### 能力的条件

说明用概念给出了各种能力的条件：

- *cartesian-product-is-random-access*：所有范围随机访问，且**除第一个外**都 sized（随机访问的 `+= n` 要把 n 按各维长度做"进制分解"，需要知道除第一维外每一维的长度）；
- *cartesian-product-is-bidirectional*：所有范围双向，且除第一个外都满足 *cartesian-product-common-arg*（common，或 sized+随机访问）——`--` 时借位要跳到内层维度的**末尾元素**；
- *cartesian-product-is-common*：**第一个**范围满足 *cartesian-product-common-arg*；
- *cartesian-product-is-sized*：全部 sized。

### `end()` 与 *is-empty*（¶4–¶5）

common 时 `end()` 返回一个迭代器：第一个分量取第一个范围的末尾，其余分量取各自的 `begin`——"进位溢出"后的状态。但若**其他某个范围为空**，整个积为空，此时 `end()` 必须等于 `begin()`；于是 ¶4.2 定义 *is-empty*：若除第一个外有任一范围为空，第一个分量也取 `begin`。否则返回 `default_sentinel`（¶6），迭代器与它比较时检查是否有任一分量到达末尾。

### `size()`（¶7–¶11）

- ¶7 返回类型是**实现定义的无符号整数类类型**；¶8 建议实践：足以存放各范围最大大小之积的最小无符号整数类类型；
- ¶10 前置条件：乘积 `p` 能用返回类型表示——三个 `size_t` 大小的范围相乘很容易超出 64 位，这时实现可能选用 128 位整数类类型；若仍溢出则违反前置条件。

迭代器的 `difference_type` 同样是实现定义的有符号整数类类型，随机访问运算的 ¶7 前置条件要求按比例换算后的和可以用它表示。

## 示例

```cpp run
#include <ranges>
#include <vector>
#include <cstdio>
int main() {
  std::vector<int> xs{1, 2};
  std::vector<char> ys{'a', 'b', 'c'};
  for (auto [x, y] : std::views::cartesian_product(xs, ys))   // C++23；libc++ 尚未提供
    std::printf("%d%c ", x, y);
  std::puts("");   // 1a 1b 1c 2a 2b 2c
  // 找出所有满足 i*i + j*j == 25 的 (i, j)
  auto sq = std::views::cartesian_product(std::views::iota(0, 6), std::views::iota(0, 6))
          | std::views::filter([](auto t) { auto [i, j] = t; return i * i + j * j == 25; });
  for (auto [i, j] : sq) std::printf("(%d,%d)", i, j);
  std::puts("");   // (0,5)(3,4)(4,3)(5,0)
}
```

## 小结

- 第一个范围可以是输入范围，其余必须前向；字典序遍历，最后一维最快；
- 随机访问/双向/common/sized 各有不同的条件，核心都是"除第一维外的维度需要知道长度或末尾"；
- `size()` 类型由实现决定，乘积必须可表示；
- 空包产生 `single(tuple())`；任一非首维为空则整体为空。
