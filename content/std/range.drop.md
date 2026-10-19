---
title: drop 与 drop_while 视图
summary: views::drop 跳过前 n 个元素，views::drop_while 跳过满足谓词的前缀；drop 尽量返回与输入同类的视图，两者在必要时缓存 begin()，因此常常没有 const 版本的 begin()。
status: done
covers: range.drop, range.drop.overview, range.drop.view, range.drop.while, range.drop.while.overview, range.drop.while.view
since: c++20
papers: P0896R4, P1739R4, P3168R2
related: range.take, range.filter, range.reverse, range.adaptors, range.range, range.nonprop.cache, range.iota, range.factories
tags: 标准库, 范围, drop, drop_while, 缓存
updated: 2026-10-19
---

!!! tldr
    - `views::drop(n)` 跳过前 n 个元素，元素不足 n 个时得到空范围，不会越界。
    - 输入是 `span`、`string_view`、`iota_view`、`subrange`、`repeat_view`、`empty_view` 时，`drop` 直接返回同类视图。
    - 找到新的起点要走 n 步，所以 `drop_view` 在底层不是随机访问且 sized 时把 `begin()` 的结果缓存起来；这时它没有 const 版本的 `begin()`。
    - `drop_while` 的起点要靠谓词逐个判断，它总是缓存，永远不能以 const 方式遍历。
    - 缓存之后再修改底层容器，视图记住的起点不会更新。

```cpp run ok
#include <cstdio>
#include <ranges>
#include <string_view>

int main() {
  for (int i : std::views::iota(0, 10) | std::views::drop(5))
    std::printf("%d ", i);                                    // 5 6 7 8 9
  auto s = std::string_view("   hello") |
           std::views::drop_while([](char c) { return c == ' '; });
  for (char c : s) std::putchar(c);                           // hello
  std::puts("");
}
```

`drop` 和 `drop_while` 是 [[range.take]] 中 `take`、`take_while` 的镜像：`take` 截掉尾部，`drop` 截掉开头。截掉开头意味着新的第一个元素在哪里需要计算，这就引出了本页的主要问题：`begin()` 的结果要不要缓存。

## `views::drop`：跳过前 n 个 [range.drop.overview]

¶1 `drop_view` 给出排除了前 N 个元素的视图；如果底层不足 N 个元素，结果是空范围。¶3 例 1 对 `iota(0) | take(10)` 跳过 5 个，打印 `5 6 7 8 9`。

¶2 和 `take` 一样，`drop` 先检查能否直接返回与输入同类的视图（[[P1739R4]]）。令 `T` 为 `E` 去掉引用和 cv 限定后的类型，`D` 为它的差值类型。`F` 不能转换为 `D` 时非良构；否则依次检查：

| 段 | `T` 是 | 结果 |
|---|---|---|
| ¶2.1 | `empty_view` 的特化 | `E` 的副本（`F` 也会求值） |
| ¶2.2 | 建模 `view` 的 `optional` 特化 {{c++26}} | `F` 为 0 时是 `E` 的副本，否则是空的 `T()` |
| ¶2.3 | 随机访问且 sized 的 `span`、`basic_string_view`、`iota_view`，或不存储大小的 `subrange` | 同类视图，范围是 `[begin + min(distance(E), F), end)` |
| ¶2.4 | 随机访问且 sized、存储大小的 `subrange` | 同上，并传入新的大小 |
| ¶2.5 | `repeat_view` | 有界时少重复 `min(distance(E), F)` 次；无界时原样返回 `E` 的副本 |
| ¶2.6 | 其他 | `drop_view(E, F)` |

¶2.3 中 `span` 的结果是动态长度的 `span<element_type>`，其余情况结果类型就是 `T`。¶2.4 针对的是迭代器与哨位不能相减、因而要在对象里另外保存大小的 `subrange`（见 [[range.subrange]]），新的大小必须一起算出来。¶2.5 的无界情形最直观：无穷个 `x` 去掉前 n 个，仍然是无穷个 `x`。

```cpp run ok
#include <ranges>
#include <string_view>

using namespace std::literals;
auto sv = "hello"sv | std::views::drop(1);
static_assert(std::same_as<decltype(sv), std::string_view>);

auto rp = std::views::repeat(7) | std::views::drop(3);
static_assert(std::same_as<decltype(rp), decltype(std::views::repeat(7))>);

int main() {}
```

## `drop_view` 为什么要缓存 begin() [range.drop.view]

`drop_view` 保存底层视图和计数 n。¶1 构造函数要求 `n >= 0`，¶2 把两者存进成员。`end()` 就是底层的 `end()`，`size()` 是底层大小减 n、最小为 0。

¶3 `begin()` 返回 `ranges::next(ranges::begin(base_), n, ranges::end(base_))`，也就是从头走 n 步，遇到终点就停。对 `vector` 这是一次加法，对 `list` 却要真的走 n 步。

`range` 概念要求 `begin()` 是摊还常数时间的（[[range.range]]）。¶4 因此规定：当 `drop_view` 是前向范围时，第一个 `begin()` 重载把结果缓存在视图里，之后的调用直接返回缓存值。注 1 给出了不缓存的后果：在 `drop_view` 外面再套一层 `reverse_view`，遍历的复杂度会变成平方级，因为外层视图会反复调用 `begin()`。

缓存要修改视图对象，只能在非 const 的 `begin()` 里做。所以两个重载的约束是：

- `begin() const` 只在 `const V` 随机访问且 sized 时存在，此时走 n 步是 O(1)，不需要缓存；
- 非 const 的 `begin()` 在其余情况下使用，按需缓存。

<div class="compare" markdown="1">

```cpp run ok
#include <ranges>
#include <vector>
std::vector<int> v{1, 2, 3, 4, 5};
using DV = decltype(v | std::views::drop(2));
// 随机访问且 sized：可以 const 遍历
static_assert(std::ranges::range<const DV>);
int main() {}
```

```cpp run ok
#include <list>
#include <ranges>
std::list<int> l{1, 2, 3, 4, 5};
using DL = decltype(l | std::views::drop(2));
// 要缓存：没有 const begin()
static_assert(!std::ranges::range<const DL>);
int main() {}
```

</div>

缓存的是底层迭代器，不指向 `drop_view` 自身，所以底层是[[g:borrowed-range|借用范围]]时 `drop_view` 也是。缓存用的是 [[range.nonprop.cache|non-propagating-cache]]：复制视图时缓存不随之复制，新对象会重新计算。

!!! impl "libc++"
    libc++ 只在 `forward_range<V> && !(random_access_range<V> && sized_range<V>)` 时存放缓存。输入范围不缓存：输入范围的 `begin()` 只能调用一次，摊还常数的要求自然满足。

## `views::drop_while`：跳过满足条件的前缀 [range.drop.while]

¶1 给定一元谓词 `pred` 和视图 `r`，`drop_while_view` 给出 `[find_if_not(r, pred), end(r))`。¶2 `views::drop_while(E, F)` 等价于 `drop_while_view(E, F)`，没有特例。[range.drop.while.overview] ¶3 例 1 用它跳过字符串开头的空格和制表符。

[range.drop.while.view] ¶4 `begin()` 返回 `find_if_not(base_, cref(*pred_))`；¶3 的前置条件是谓词存在（只有在赋值时抛异常的极端情况下才会不存在）。¶5 和 `drop_view` 一样，视图是前向范围时第一次调用的结果被缓存，理由也是避免 `reverse_view` 套在外面时的平方复杂度。

和 `drop_view` 不同的是，即使底层是 `vector`，跳过多少个也只能逐个调用谓词才知道。所以 `drop_while_view` 只有非 const 的 `begin()`，永远不能以 const 方式遍历。

```cpp run ok
#include <cstdio>
#include <ranges>
#include <string_view>

int main() {
  auto dw = std::string_view("   hi") |
            std::views::drop_while([](char c) { return c == ' '; });
  static_assert(!std::ranges::range<const decltype(dw)>);
  for (char c : dw | std::views::reverse) std::putchar(c);   // ih
  std::puts("");
}
```

`drop_while_view` 的迭代器和终点都直接来自底层，所以它的迭代器类别、是否 common range 都与底层相同。它的终点不调用谓词，因此底层是借用范围时它也是。这一点与 `take_while` 相反：`take_while` 的哨位要调用谓词，所以不借用。

## 常见误解

!!! pitfall "缓存之后修改底层"
    ```cpp
    std::list<int> lst{1, 2, 3};
    auto d = lst | std::views::drop(1);
    d.begin();             // 缓存：指向元素 2
    lst.push_front(0);     // lst 现在是 0 1 2 3
    // d 仍从元素 2 开始，而不是新的第二个元素 1
    ```
    `drop_while` 同理：缓存的是第一个不满足谓词的位置，之后修改前面的元素，它也不会重新计算。这和 [[range.filter]] 的缓存问题一样。

!!! pitfall "创建视图不消费输入，第一次 begin() 才消费"
    `views::istream<int>(in) | views::drop(3)` 本身什么也不读。第一次调用 `begin()` 时，`istream_view` 先读出第一个值，`drop` 再推进 3 次，一共从流里读走 4 个值，第 4 个就是结果的第一个元素。

## 小结

| | `drop(n)` | `drop_while(p)` |
|---|---|---|
| 返回同类视图的特例 | `empty`、`optional`、`span`、`string_view`、`iota`、`subrange`、`repeat` | 无 |
| 缓存 `begin()` | 前向范围，且底层不是随机访问 + sized 时 | 前向范围时总是缓存 |
| 可以 const 遍历 | `const V` 随机访问且 sized 时 | 从不 |
| sized range | 底层是时 | 否 |
| 借用范围 | 底层是时 | 底层是时 |
