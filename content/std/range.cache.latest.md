---
title: cache_latest 与 as_input 视图
summary: 两个主动把范围降为输入范围的视图：views::cache_latest 把最近一次解引用的结果存在视图里，使 transform 后接 filter 时昂贵的函数每个元素只调用一次；views::as_input 把任意范围呈现为只能单趟遍历、首尾类型不同的范围，免去下游为更强能力付出的开销。
status: draft
covers: range.cache.latest, range.cache.latest.overview, range.cache.latest.view, range.cache.latest.iterator, range.cache.latest.sentinel, range.as.input, range.as.input.overview, range.as.input.view, range.as.input.iterator
since: c++26
papers: P3138R5
related: range.transform, range.filter, range.nonprop.cache, range.adaptors, range.join, range.chunk, range.req
tags: 标准库, 范围, cache_latest, as_input, C++26
updated: 2026-10-19
---

!!! tldr
    - `transform(f) | filter(p)` 会让 `f` 对每个通过筛选的元素调用两次；在中间插入 `views::cache_latest`，就只调用一次。
    - `cache_latest` 把最近一次解引用的结果存在视图对象里，所以结果只是输入范围，没有 const 版本的 `begin()`，也不是借用范围。
    - `*it` 返回的引用只在下一次 `++it` 之前有效。
    - `views::as_input` 把任何范围变成只能单趟遍历、首尾类型不同的范围，下游的 `join`、`chunk` 等因此可以用更简单的实现。
    - 只遍历一次、而且没有会重复解引用的下游时，两者都不需要。

```cpp
#include <cstdio>
#include <ranges>
#include <vector>

int calls = 0;
int expensive(int x) { ++calls; return x * x; }

int main() {
  std::vector<int> v{1, 2, 3, 4};
  auto r = v | std::views::transform(expensive)
             | std::views::cache_latest
             | std::views::filter([](int y) { return y % 2 == 0; });
  for (int y : r) std::printf("%d ", y);       // 4 16
  std::printf("| calls=%d\n", calls);          // calls=4；去掉 cache_latest 则为 6
}
```

[[range.filter]] 判断谓词时解引用一次底层迭代器，循环体读取元素时又解引用一次。底层是 `transform` 时，每次解引用都调用一次 `expensive`，所以每个通过筛选的元素要算两次。`cache_latest` 记住了第一次的结果，第二次直接返回。

前面介绍的视图大多尽量保留底层的能力。这两个 C++26 的视图相反，主动把范围降为输入范围，用能力换取运行时的效率。`cache_latest` 来自 [[P3138R5]]。

!!! impl "实现现状"
    截至写作时，本机 libc++ 还没有提供 `views::cache_latest` 和 `views::as_input`。本页的代码按标准原文编写，没有经过编译验证；注释中的调用次数是按标准语义推算的。

## `views::cache_latest` [range.cache.latest]

¶1 `cache_latest_view` 缓存底层序列中最近一次访问的元素，重复访问时就不必重新计算。注 1 指出，这在计算元素的代价很高时有用。¶2 `views::cache_latest(E)` 等价于 `cache_latest_view(E)`。

### 缓存在视图里 [range.cache.latest.view]

`cache_latest_view` 有一个 [[range.nonprop.cache|non-propagating-cache]] 成员 `cache_`，缓存的类型 *cache-t* 取决于底层解引用的结果：

- 结果是引用（如 `int&`）时，缓存一个指向元素的指针；
- 结果是纯右值（如 `transform` 返回的 `int`）时，缓存这个值本身。

[range.cache.latest.iterator] ¶6 规定了 `*it`：缓存为空时，先解引用底层迭代器并存入缓存，然后返回缓存的内容。返回类型是 `range_reference_t<V>&`，所以即使底层返回纯右值，这里得到的也是一个指向缓存对象的左值引用。¶4 `++it` 先清空缓存，再推进底层迭代器。

缓存只有一份，放在视图对象里，因此同一时刻只能有一个有意义的迭代器，这正是输入范围的语义：

- 迭代器的 `iterator_concept` 是 `input_iterator_tag`，迭代器只能移动，不能复制；
- [range.cache.latest.view] ¶2 `begin()` 只有非 const 版本，¶3 `end()` 返回哨位，结果不是公共范围；
- 不是借用范围。

¶6 的注 1 还提醒，对同一个迭代器并发调用 `operator*` 可能构成数据竞争（[[intro.races]]），因为两次调用都可能写缓存。

!!! pitfall "返回的引用只活到下一次 ++"
    `auto& x = *it; ++it;` 之后，缓存已经被清空；底层返回纯右值时，缓存里的对象已经销毁。继续使用 `x` 是{{ub}}。这与输入迭代器的一般约定一致：输入迭代器递增后，之前得到的引用不再保证有效。

`cache_latest` 是给 `filter`、`take_while`、`chunk_by` 这类先看一眼元素再决定怎么做的下游准备的。如果 `transform` 后面直接是 `for` 循环或 `ranges::to`，每个元素本来就只解引用一次，加上它只会让范围失去前向能力。

## `views::as_input` [range.as.input]

¶1 `as_input_view` 把底层序列呈现为一个只能输入、不是公共范围的范围。注 1 说明了目的：避免为支持更强的迭代器类别而可能产生的开销。

¶2 令 `T` 为 `decltype((E))`，`views::as_input(E)` 等价于：

- ¶2.1 `T` 是输入范围，既不是公共范围、也不是前向范围时，结果是 `views::all(E)`，它已经满足要求；
- ¶2.2 否则是 `as_input_view(E)`。

[range.as.input.view] ¶2–¶3 `begin()` 把底层迭代器包进 `as_input_view` 自己的迭代器（[range.as.input.iterator]），它的类别是 `input_iterator_tag`，只能移动。¶4 `end()` 直接返回底层的 `end()`，与包装后的迭代器类型不同，所以结果不是公共范围。¶5 `size()` 转发给底层。它不缓存任何东西，有 const 版本的 `begin()`，借用性与底层相同。

### 降级有什么好处

许多适配器在底层能力更强时要做更多的事：

- [[range.join]]：外层是前向范围时，迭代器要同时保存外层和内层迭代器；外层只是输入范围时，外层迭代器放在视图里，迭代器更小。
- [[range.chunk]]：输入范围版本的 `chunk_view` 不需要记录最后一块缺几个元素，也不需要支持随机跳转。
- [[range.filter]]、[[range.drop]] 等只在底层是前向范围时才需要缓存 `begin()`。

如果只打算遍历一遍，`as_input` 告诉下游不必为多趟、反向或随机访问做准备，有时能换来更小的迭代器和更少的分支。

```cpp
#include <cstdio>
#include <ranges>
#include <vector>

int main() {
  std::vector<std::vector<int>> vv{{1, 2}, {3}};
  auto j = vv | std::views::as_input | std::views::join;
  static_assert(std::ranges::input_range<decltype(j)>);
  static_assert(!std::ranges::forward_range<decltype(j)>);
  for (int x : j) std::printf("%d", x);        // 123
  std::puts("");
}
```

## 小结

| | `cache_latest` | `as_input` |
|---|---|---|
| 目的 | 避免重复计算元素 | 避免为更强的类别付出开销 |
| 结果 | 输入范围，不是公共范围 | 输入范围，不是公共范围 |
| `*it` 的类型 | `range_reference_t<V>&`，指向缓存 | 与底层相同 |
| const 遍历 | 不能 | 与底层相同 |
| 借用范围 | 否 | 底层是时 |

<details class="fine" markdown="1"><summary>其余条文</summary>

[range.cache.latest.view] ¶1：构造函数保存底层视图；¶4–¶5 `size()`、`reserve_hint()` 转发给底层。[range.cache.latest.iterator] ¶1–¶3 是构造函数和 `base()`，¶5 是后置 `++`，¶7–¶8 的 `iter_move`、`iter_swap` 直接作用于底层迭代器，不经过缓存。[range.cache.latest.sentinel] ¶1–¶5：哨位保存底层终点，比较和相减都基于底层迭代器。

[range.as.input.view] ¶1、¶6：构造函数和 `reserve_hint()`。[range.as.input.iterator] 的各段把运算转发给底层迭代器。

</details>
