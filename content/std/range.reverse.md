---
title: reverse 视图
summary: views::reverse 反向遍历一个双向视图：两次反转互相抵消，反向的 subrange 被拆回原迭代器；底层不是公共范围时，begin() 要先走到末尾并缓存结果，因此失去 const 版本的 begin()。
status: done
covers: *
since: c++20
papers: P0896R4
related: range.adaptors, range.drop, range.filter, range.access, reverse.iterators, range.take, range.join
tags: 标准库, 范围, reverse
updated: 2026-10-19
---

!!! tldr
    - `views::reverse` 只接受双向范围；`forward_list`、`istream_view` 这类范围不能反转。
    - `x | views::reverse | views::reverse` 直接得到 `x` 本身的视图，反向的 `subrange` 也会被拆回正向的 `subrange`。
    - `reverse_view` 的迭代器就是 `std::reverse_iterator`，结果总是公共范围。
    - 底层不是公共范围时，`begin()` 要从头走到尾才能找到最后一个元素，结果被缓存，因此没有 const 版本的 `begin()`。

```cpp run ok
#include <cstdio>
#include <ranges>
#include <vector>

int main() {
  std::vector<int> is{0, 1, 2, 3, 4};
  for (int i : is | std::views::reverse)
    std::printf("%d ", i);                     // 4 3 2 1 0
  std::puts("");
}
```

这是 [range.reverse.overview] ¶3 的例 1。`reverse_view` 做的事情很简单：把底层的 `end()` 和 `begin()` 分别包进 `std::reverse_iterator`（[[reverse.iterators]]），当作新的 `begin()` 和 `end()`。值得注意的是两件事：哪些情况根本不需要包装，以及底层没有尾迭代器时怎么办。

## 哪些情况不包装 [range.reverse.overview]

¶1 `reverse_view` 接受一个双向视图，以相反的顺序遍历同样的元素。¶2 `views::reverse(E)` 依次检查：

- ¶2.1 `E` 本身就是一个 `reverse_view`：结果是 `E.base()`，两次反转互相抵消，类型也回到原来的视图。
- ¶2.2 {{c++26}} `E` 是建模 `view` 的 `optional`：原样返回 `E` 的副本。它至多有一个元素，反转等于不变。
- ¶2.3 `E` 是 `subrange<reverse_iterator<I>, reverse_iterator<I>, K>`：拆出里面的正向迭代器，得到 `subrange<I, I, K>(E.end().base(), E.begin().base())`；`K` 表示存储大小时，大小也一并传过去。
- ¶2.4 其他情况：`reverse_view{E}`。

```cpp run ok
#include <ranges>
#include <vector>

std::vector<int> v{1, 2, 3};

auto rr = v | std::views::reverse | std::views::reverse;      // ¶2.1
static_assert(std::same_as<decltype(rr), std::ranges::ref_view<std::vector<int>>>);

auto sr = std::ranges::subrange(v.rbegin(), v.rend()) | std::views::reverse;   // ¶2.3
static_assert(std::same_as<decltype(sr), std::ranges::subrange<std::vector<int>::iterator>>);

int main() {}
```

## 底层没有尾迭代器时 [range.reverse.view]

`reverse_iterator` 只能从一个迭代器构造，不能从哨位构造。反向遍历的起点是底层最后一个元素之后的位置，如果底层的 `end()` 返回的是哨位，就必须先从 `begin()` 一步步走到哨位处，得到一个真正的迭代器。

¶2 因此在底层不是[[g:common-range|公共范围]]时，`begin()` 返回 `make_reverse_iterator(ranges::next(ranges::begin(base_), ranges::end(base_)))`，这要走 n 步。¶3 为了满足 `range` 概念对 `begin()` 摊还常数时间的要求，结果被缓存在视图里，所以这时没有 const 版本的 `begin()`。

¶4 底层是公共范围时，`begin()` 就是 `make_reverse_iterator(ranges::end(base_))`，O(1)，`const V` 也是公共范围时还有 const 版本。¶5 `end()` 总是 `make_reverse_iterator(ranges::begin(base_))`。

```cpp run ok
#include <cstdio>
#include <ranges>
#include <vector>

int main() {
  std::vector<int> v{1, 2, 3, 4, 5};

  auto cr = v | std::views::reverse;                  // 底层是公共范围
  static_assert(std::ranges::range<const decltype(cr)>);

  auto tw = v | std::views::take_while([](int x) { return x < 4; });   // 双向，但终点是哨位
  auto r = tw | std::views::reverse;                  // begin() 走到尾并缓存
  static_assert(!std::ranges::range<const decltype(r)>);
  for (int x : r) std::printf("%d ", x);              // 3 2 1
  std::puts("");
}
```

`reverse_view` 的其他性质：

- 首尾都是 `reverse_iterator<iterator_t<V>>`，所以结果总是公共范围。
- 迭代器类别与底层相同，最高到随机访问；`reverse_iterator` 不是连续迭代器。
- `size()` 和 `reserve_hint()` 直接转发给底层；底层是[[g:borrowed-range|借用范围]]时它也是。

## 与 drop 的缓存

[[range.drop]] 中 `drop_view` 和 `drop_while_view` 缓存 `begin()`，注释给出的理由正是 `reverse_view`：`reverse_view::end()` 每次都要调用底层的 `begin()`，如果底层每次都要重新走 n 步，反向遍历的总代价就成了平方级。

## 常见误解

!!! pitfall "解引用返回自身内部引用的迭代器"
    `reverse_iterator` 的 `operator*` 相当于 `{ auto tmp = current; return *--tmp; }`：它对一个局部副本解引用并返回结果。如果底层迭代器解引用时返回指向迭代器对象自身内部的引用，`tmp` 一销毁，返回的引用就悬垂了。

    [[iterator.concept.forward]] 要求从前向迭代器得到的引用在范围有效期间一直有效，这样的迭代器不满足这条语义要求，所以合规的双向视图不会有这个问题。手写迭代器违反了这一要求时，`views::reverse` 会导致{{ub}}。

<details class="fine" markdown="1"><summary>其余条文</summary>

[range.reverse.view] ¶1：构造函数保存底层视图。推导指引 `reverse_view(R&&)` 把 `R` 经 `views::all_t` 包成视图。

</details>
