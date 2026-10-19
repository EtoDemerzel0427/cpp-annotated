---
title: take 与 take_while 视图
summary: views::take 取前 n 个元素，views::take_while 取谓词第一次不成立之前的前缀；take 尽量返回与输入同类的视图，take_view 按底层能力选择迭代器，两者在输入范围上都会多消费一个元素。
status: done
covers: range.take, range.take.overview, range.take.view, range.take.sentinel, range.take.while, range.take.while.overview, range.take.while.view, range.take.while.sentinel
since: c++20
papers: P0896R4, P1739R4, P3168R2
related: range.drop, range.adaptors, range.counted, range.factories, range.iota, counted.iterator, range.common, range.req
tags: 标准库, 范围, take, take_while
updated: 2026-10-19
---

!!! tldr
    - `views::take(n)` 产生前 n 个元素；底层不足 n 个时给出全部元素，不会越界。
    - 输入是 `span`、`string_view`、`subrange`、`iota_view`、`repeat_view`、`empty_view` 时，`take` 直接返回同类视图，而不是包一层 `take_view`。
    - `take_view` 在底层既 sized 又随机访问时用底层迭代器，结果是 common range；其余情况用 `counted_iterator`，结果不是 common range。
    - `views::take_while(pred)` 的终点藏在哨位里，每次与终点比较都会调用一次谓词；它永远不是 sized，也不是 common。
    - 在 `istream` 这类输入范围上，两者都会从流里多取走一个值。

```cpp run ok
#include <cstdio>
#include <ranges>

int main() {
  for (int i : std::views::iota(1) | std::views::take(3))
    std::printf("%d ", i);                              // 1 2 3
  for (int i : std::views::iota(1) | std::views::take_while([](int x) { return x * x < 30; }))
    std::printf("%d ", i);                              // 1 2 3 4 5
  std::puts("");
}
```

`iota(1)` 是一个无穷序列。`take` 按个数截断，`take_while` 按条件截断，这是让无穷序列可以使用的两种标准做法。两者都是[[g:range-adaptor-object|范围适配器对象]]：既可以写 `views::take(r, n)`，也可以写 `r | views::take(n)`。

## `views::take`：取前 n 个 [range.take.overview]

¶1 `take_view` 给出另一个视图的前 N 个元素；如果那个视图不足 N 个元素，就给出全部元素。所以 `v | views::take(10)` 在 `v` 只有 5 个元素时也是安全的，结果就是 5 个元素。

¶3 标准的例 1 就是这个最基本的用法：对 `0..9` 取前 5 个，打印 `0 1 2 3 4`。

### 能保持原类型就保持原类型（¶2）

```cpp run ok
#include <ranges>
#include <span>
#include <vector>

std::vector<int> v{1, 2, 3, 4, 5};

auto s = std::span(v) | std::views::take(3);
static_assert(std::same_as<decltype(s), std::span<int>>);

auto io = std::views::iota(0, 10) | std::views::take(3);
static_assert(std::same_as<decltype(io), std::ranges::iota_view<int, int>>);

auto t = v | std::views::take(3);
static_assert(std::same_as<decltype(t),
    std::ranges::take_view<std::ranges::ref_view<std::vector<int>>>>);

int main() {}
```

对 `span` 取前 3 个，得到的还是 `span`，可以直接传给只接受 `span` 的函数，也不会产生 `take_view<take_view<...>>` 这样层层嵌套的类型。对 `vector` 则不行，只能得到 `take_view`；想要 `span` 就先写 `std::span(v)`。

¶2 精确的规则如下。令 `T` 为 `E` 去掉引用和 cv 限定后的类型，`D` 为它的差值类型（`range_difference_t`）。`F` 不能转换为 `D` 时，`views::take(E, F)` 非良构；否则它表达式等价于（[[g:expression-equivalent]]）下表中第一个适用的形式：

| 段 | `T` 是 | 结果 |
|---|---|---|
| ¶2.1 | `empty_view` 的特化 | `E` 的副本（`F` 也会求值） |
| ¶2.2 | 建模 `view` 的 `optional` 特化 {{c++26}} | `F` 为 0 时得到空的 `T()`，否则是 `E` 的副本 |
| ¶2.3 | 随机访问且 sized 的 `span`、`basic_string_view`、`subrange` | 同类视图，范围是 `[begin, begin + min(distance(E), F))` |
| ¶2.4 | 随机访问且 sized 的 `iota_view` | 一个更短的 `iota_view` |
| ¶2.5 | `repeat_view` | 有界时取 `min(distance(E), F)` 次的 `repeat`，无界时取 `F` 次 |
| ¶2.6 | 其他 | `take_view(E, F)` |

¶2.3 中 `span` 的结果是动态长度的 `span<element_type>`，`subrange` 的结果是 `subrange<iterator_t<T>>`。这一组特例来自 [[P1739R4]]，`optional` 一行来自让 `optional` 成为视图的 [[P3168R2]]。截至写作时，本机 libc++ 还不支持把 `optional` 当作视图。

规则只看 `T` 本身是什么，不看它能不能转换成 `span`。另外，¶2.5 让 `views::repeat(7) | views::take(3)` 直接成为一个重复 3 次的有界 `repeat_view`。

## `take_view` 怎样找到终点 [range.take.view]

需要真正构造 `take_view` 时，它只存两样东西：底层视图 `base_` 和计数 `count_`。¶1 构造函数要求 `count >= 0`，¶2 把两者存进成员。

`begin()` 和 `end()` 按底层视图的能力，选择下面三种做法之一：

| 底层视图 | `begin()` | `end()` | 结果是 common range |
|---|---|---|---|
| sized 且随机访问 | 底层迭代器 | `begin + min(size, n)` | 是 |
| 其他，但能事先算出长度 | `counted_iterator`，计数为 `min(长度, n)` | `default_sentinel` | 否 |
| 长度未知 | `counted_iterator`，计数为 `n` | `take_view::sentinel` | 否 |

[[counted.iterator|`counted_iterator`]] 把一个迭代器和剩余计数包在一起，每次 `++` 同时推进底层迭代器、计数减一。表中第二行包括两种情况：底层是 sized range（`std::list`），或者底层的哨位与迭代器可以相减。这时计数已经截到不超过实际长度，计数归零就是终点，所以终点只要一个 `default_sentinel`。

只有在长度事先无法知道时，才需要专门的哨位 `take_view::sentinel`（[range.take.sentinel] ¶4）。它保存底层的终点，与 `counted_iterator` 比较时，计数归零或者底层到达终点都算结束。

```cpp run ok
#include <cstdio>
#include <list>
#include <ranges>
#include <vector>

int main() {
  std::vector<int> v{1, 2, 3, 4, 5};
  auto t = v | std::views::take(10);          // 只有 5 个，不越界
  static_assert(std::ranges::random_access_range<decltype(t)>);
  static_assert(std::ranges::common_range<decltype(t)>);

  std::list<int> l{1, 2, 3};
  auto tl = l | std::views::take(2);          // counted_iterator + default_sentinel
  static_assert(!std::ranges::common_range<decltype(tl)>);

  std::printf("%zu %zu\n", t.size(), tl.size());   // 5 2
}
```

`take_view` 的其他性质都跟随底层视图：底层是 sized range 时它也是，`size()` 返回 `min(底层大小, n)`；底层是[[g:borrowed-range|借用范围]]时它也是；`begin()` 不做缓存，所以底层能以 const 方式遍历时它也能。

C++26 起 `take_view` 总有 `reserve_hint()`（[[range.utility.conv]] 中 `ranges::to` 用它预留容量）。底层长度未知时，`n` 本身就是一个上界，所以 `views::iota(0) | views::take(1000) | ranges::to<std::vector>()` 也可以先预留 1000 个元素。

!!! pitfall "在输入范围上会多读一个"
    `counted_iterator` 的 `++` 先推进底层迭代器，再减计数。取完第 n 个元素后，循环的最后一次 `++` 仍然推进了底层。对 `istream_view` 来说，这意味着从流里再读一个值：

    ```cpp run ok
    #include <cstdio>
    #include <ranges>
    #include <sstream>

    int main() {
      std::istringstream in{"1 2 3 4 5"};
      for (int x : std::views::istream<int>(in) | std::views::take(3))
        std::printf("%d ", x);
      int next = 0;
      in >> next;
      std::printf("| next=%d\n", next);   // next=5：4 已被 take 读走
    }
    ```

    从管道或网络读数据时，这会丢掉一条消息。需要精确消费 n 个时，用按计数执行的算法（如 `ranges::copy_n`）或手写循环。

## `views::take_while`：取满足条件的前缀 [range.take.while]

¶1 给定一元谓词 `pred` 和视图 `r`，`take_while_view` 给出范围 `[begin(r), find_if_not(r, pred))`，也就是从头开始、到第一个不满足 `pred` 的元素为止。¶2 `views::take_while(E, F)` 等价于 `take_while_view(E, F)`，没有任何特例。

### 终点在哨位里 [range.take.while.view]

`take_while_view` 的 `begin()` 就是底层的 `begin()`，迭代器也就是底层迭代器。何时停止全部由哨位决定。[range.take.while.sentinel] ¶3 规定，迭代器 `x` 与哨位比较的结果是：

```cpp
return y.end_ == x || !invoke(*y.pred_, *x);
```

由此得到几个性质：

- 每次与终点比较都调用一次谓词。范围 `for` 每轮比较一次，所以谓词每个元素至少被调用一次。
- 不遍历就不知道在哪里停，所以它永远不是 sized range，也永远不是 common range。
- 哨位保存的是指向视图内部谓词的指针，所以它不是借用范围。
- 视图以 `const Pred` 调用谓词（约束是 `indirect_unary_predicate<const Pred, ...>`），带 `mutable` 的 lambda 不能使用。

```cpp run ok
#include <ranges>
#include <vector>

int main() {
  std::vector<int> v{1, 2, 3, 4, 5};
  auto tw = v | std::views::take_while([](int x) { return x < 3; });
  static_assert(!std::ranges::common_range<decltype(tw)>);
  static_assert(!std::ranges::sized_range<decltype(tw)>);
}
```

老式接口需要一对同类型的迭代器时，先经过 `views::common`（[[range.common]]）。

### 也会多读一个（¶3）

[range.take.while.overview] ¶3 例 1 从 `"0 1 2 3 4 5 6 7 8 9"` 中取所有小于 5 的数，打印 `0 1 2 3 4`。随后 `input >> i` 读到的是 6，因为 5 已经被读出来交给谓词判断了。

这与 `take` 多读的原因不同：`take_while` 必须先看到第一个不满足条件的元素，才知道应该停下，这个元素已经离开了流。

```cpp run ok
#include <iostream>
#include <ranges>
#include <sstream>

int main() {
  auto input = std::istringstream{"0 1 2 3 4 5 6 7 8 9"};
  auto small = [](const auto x) noexcept { return x < 5; };
  for (const auto i : std::views::istream<int>(input) | std::views::take_while(small))
    std::cout << i << ' ';                    // 0 1 2 3 4
  auto i = 0;
  input >> i;
  std::cout << i << '\n';                     // 6
}
```

## 小结

| | `take(n)` | `take_while(p)` |
|---|---|---|
| 返回同类视图的特例 | `empty`、`optional`、`span`、`string_view`、`subrange`、`iota`、`repeat` | 无 |
| 迭代器 | 底层迭代器或 `counted_iterator` | 底层迭代器 |
| sized range | 底层是时 | 否 |
| common range | 底层 sized 且随机访问时 | 否 |
| 借用范围 | 底层是时 | 否 |
| 输入范围上 | 多推进一次底层 | 多读出第一个不满足条件的元素 |

<details class="fine" markdown="1"><summary>其余条文</summary>

[range.take.sentinel] ¶1–3：哨位的构造函数保存底层终点；`sentinel<false>` 可以转换为 `sentinel<true>`；`base()` 返回保存的底层终点。

[range.take.while.view] ¶1–2：构造函数保存底层视图和谓词；`pred()` 返回谓词的引用。[range.take.while.sentinel] ¶1–2 是哨位的两个构造函数。

两个视图都提供推导指引 `take_view(R&&, range_difference_t<R>)`、`take_while_view(R&&, Pred)`，把 `R` 经 `views::all_t` 包成视图。

</details>
