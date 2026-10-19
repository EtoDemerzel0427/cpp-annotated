---
title: enumerate 视图
summary: C++23 的 views::enumerate 在遍历时同时给出下标和元素；下标是有符号的差值类型，元素以引用的形式装在一个临时 tuple 里，所以结构化绑定可以写回底层；其余性质都与底层相同。
status: done
covers: *
since: c++23
papers: P2164R9
related: range.adaptors, range.zip, range.iota, range.elements, range.adaptor.helpers, dcl.struct.bind
tags: 标准库, 范围, enumerate
updated: 2026-10-19
---

!!! tldr
    - `for (auto [i, x] : views::enumerate(r))` 同时得到下标和元素，不必手写计数器。
    - 下标的类型是底层的差值类型 `range_difference_t`，通常是有符号的 `std::ptrdiff_t`，不是 `size_t`。
    - 每个元素是一个临时的 `tuple<下标, 元素引用>`；结构化绑定复制的是这个 tuple，但其中的引用仍指向底层，所以通过 `x` 可以修改底层元素。
    - 迭代器类别、是否 sized、是否借用都与底层相同；迭代器的 `index()` 直接返回下标。

```cpp run ok
#include <iostream>
#include <ranges>
#include <vector>

int main() {
  std::vector<int> vec{1, 2, 3};
  for (auto [index, value] : std::views::enumerate(vec))
    std::cout << index << ":" << value << ' ';    // 0:1 1:2 2:3
  std::cout << '\n';
}
```

这是 [range.enumerate.overview] ¶2 的例 1。C++20 里带下标遍历只能手写计数器，或者写 `zip(iota(0), v)`，后者的下标是 `int`，和 `v.size()` 比较时还会遇到符号问题。C++23 的 [[P2164R9]] 加入了 `views::enumerate`。

## `views::enumerate` [range.enumerate.overview]

¶1 `enumerate_view` 的每个元素同时表示底层序列中一个元素的位置和值。¶2 `views::enumerate(E)` 等价于 `enumerate_view<views::all_t<decltype((E))>>(E)`，没有特例。

`enumerate_view` 要求底层满足说明用概念 *range-with-movable-references*（[[range.adaptor.helpers]]）：元素的引用类型和右值引用类型都能移动构造，因为它们要被装进 `tuple` 返回。

## 元素是什么 [range.enumerate.iterator]

迭代器保存底层迭代器 `current_` 和下标 `pos_`，有三个相关的类型：

| 类型 | 定义 | 对 `vector<string>` |
|---|---|---|
| `difference_type`，也是下标类型 | `range_difference_t<Base>` | `ptrdiff_t` |
| `value_type` | `tuple<difference_type, range_value_t<Base>>` | `tuple<ptrdiff_t, string>` |
| `operator*` 的结果 | `tuple<difference_type, range_reference_t<Base>>` | `tuple<ptrdiff_t, string&>` |

`operator*` 每次返回一个新的 `tuple` 纯右值，第二个分量是底层元素的引用。`auto [i, s]` 先把这个 tuple 复制到一个隐藏的变量里，`s` 再指代其中的第二个分量（[[dcl.struct.bind]]）；这个分量的类型是 `string&`，所以对 `s` 的修改会写回底层。¶6 `it.index()` 直接返回 `pos_`。

```cpp run ok
#include <cstdio>
#include <ranges>
#include <string>
#include <vector>

int main() {
  std::vector<std::string> v{"a", "b", "c"};
  for (auto [i, s] : std::views::enumerate(v)) {
    static_assert(std::same_as<decltype(i), std::ptrdiff_t>);
    s += std::to_string(i);                      // 写回 v
  }
  using E = decltype(std::views::enumerate(v));
  static_assert(std::same_as<std::ranges::range_reference_t<E>,
                             std::tuple<std::ptrdiff_t, std::string&>>);
  static_assert(std::ranges::random_access_range<E> && std::ranges::sized_range<E>);

  auto it = std::ranges::begin(std::views::enumerate(v)) + 2;
  std::printf("%td %s %s\n", it.index(), v[0].c_str(), v[2].c_str());   // 2 a0 c2
}
```

最后对一个临时的 `enumerate_view` 调用 `ranges::begin` 是合法的：`enumerate_view<ref_view<...>>` 是[[g:borrowed-range|借用范围]]，迭代器不依赖视图对象，视图销毁后仍然有效（[[range.access]]）。

`iter_move` 返回 `tuple<difference_type, range_rvalue_reference_t<Base>>`，即下标加上元素的右值引用。

### 迭代器的其他性质

- ¶1 迭代器类别与底层相同，最高到随机访问。`iterator_category` 固定是 `input_iterator_tag`，因为解引用得到的不是引用。
- ¶12–¶13 两个迭代器的比较只比较下标，`it1 - it2` 也是下标之差（¶17）。
- `end()` 在底层是前向、公共且 sized 的范围时，返回一个下标为 `distance(base_)` 的迭代器，结果是公共范围；否则返回哨位，哨位只与底层迭代器比较。
- `size()`、`reserve_hint()` 转发给底层，借用性也与底层相同。

## 与 `zip(iota(0), r)` 比较

| | `enumerate(r)` | `zip(iota(0), r)` |
|---|---|---|
| 下标类型 | `range_difference_t<R>`，有符号 | 由 `0` 推导为 `int` |
| 公共范围 | 底层是前向、公共且 sized 时 | 无界的 `iota` 让结果不是公共范围（[[range.zip]]） |
| 取下标 | `it.index()` | `std::get<0>(*it)` |
| 借用范围 | 底层是时 | 两个都是时 |

<details class="fine" markdown="1"><summary>其余条文</summary>

[range.enumerate.view] ¶1：构造函数保存底层视图。

[range.enumerate.iterator] ¶2–¶5 是构造函数和 `base()`；¶7–¶11 是自增、自减和 `+=`、`-=`，同时移动底层迭代器和下标；¶14–¶16 是迭代器加减整数。[range.enumerate.sentinel] 的哨位保存底层终点，比较和相减都基于底层迭代器。

</details>
