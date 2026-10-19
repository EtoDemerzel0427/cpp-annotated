---
title: 迭代器适配器与两个哨位
summary: 标准库的六类迭代器适配器各自解决什么问题，以及两个空的哨位类型 default_sentinel_t 和 unreachable_sentinel_t。
status: done
covers: default.sentinel, unreachable.sentinel
since: c++98
papers: P0896R4
related: reverse.iterators, insert.iterators, const.iterators, move.iterators, iterators.common, iterators.counted, iterator.concept.sentinel, stream.iterators
tags: 标准库, 迭代器, 适配器, 哨位
updated: 2026-10-19
---

!!! tldr
    - 迭代器适配器包装一个底层迭代器或容器，只改变它的一个方面：方向、插入、常量性、移动、类型统一或计数。
    - `default_sentinel_t` 是一个空类型，配合自己知道终点在哪里的迭代器使用，比较逻辑由迭代器提供。
    - `unreachable_sentinel_t` 与任何 `weakly_incrementable` 类型比较都不相等，用来表示没有上界的区间，例如 `views::iota(0)`。
    - 用 `unreachable_sentinel` 查找时，目标一定存在成了调用者的责任；找不到就越界，行为未定义。

```cpp run title="sentinels.cpp" ok
#include <algorithm>
#include <cassert>
#include <iterator>
#include <list>
#include <ranges>
#include <vector>

int main() {
    // unreachable_sentinel：已知目标一定存在，省掉边界检查
    const char buf[] = "key=value";
    auto eq = std::ranges::find(buf + 0, std::unreachable_sentinel, '=');
    assert(eq - buf == 3);

    // default_sentinel：终点由 counted_iterator 自己掌握
    std::list<int> l{1, 2, 3, 4, 5};
    std::vector<int> out;
    std::ranges::copy(std::counted_iterator(l.begin(), 3), std::default_sentinel,
                      std::back_inserter(out));
    assert((out == std::vector{1, 2, 3}));

    // 无界的 iota：iota_view<int, unreachable_sentinel_t>
    static_assert(std::same_as<decltype(std::views::iota(0)),
                               std::ranges::iota_view<int, std::unreachable_sentinel_t>>);
    auto first_big = *std::ranges::find_if(std::views::iota(1),
                                           [](int i) { return i * i > 50; });
    assert(first_big == 8);
}
```

[predef.iterators] 的标题是 Iterator adaptors。**迭代器适配器**包装一个底层迭代器（插入迭代器包装的是容器），改变它的某一方面行为，其余尽量保持原样。

| 子条款 | 适配器 | 改变了什么 |
|---|---|---|
| [[reverse.iterators]] | `reverse_iterator` | 遍历方向 |
| [[insert.iterators]] | `back_insert_iterator` 等 | 赋值变成向容器插入 |
| [[const.iterators]] | `basic_const_iterator` | 解引用结果变成常量 |
| [[move.iterators]] | `move_iterator`、`move_sentinel` | 解引用结果变成右值 |
| [[iterators.common]] | `common_iterator` | 把迭代器和不同类型的哨位统一成一个类型 |
| [[iterators.counted]] | `counted_iterator` | 携带还剩几个元素的计数 |

`reverse_iterator` 和插入迭代器从 C++98 就有，`move_iterator` 来自 C++11，`common_iterator`、`counted_iterator`、`move_sentinel` 和两个哨位随 C++20 的范围库加入，`basic_const_iterator` 是 C++23 新增的。

这些适配器有几个共同的做法：

- 用 `base()` 取回底层迭代器。`move_iterator` 和 C++20 之后的新适配器提供 `const&` 和 `&&` 两个重载，后者把底层迭代器移出来，为仅移动的迭代器服务。
- 以隐藏友元的形式提供 `iter_move`、`iter_swap`，把定制转发给底层迭代器（[[iterator.cust]]）。
- 只在底层迭代器支持时才提供相应的操作，新适配器用 `requires` 子句表达，`reverse_iterator` 这样的老适配器则靠用到时才实例化（见 [[reverse.iterators]]）。
- `reverse_iterator`、`move_iterator` 同时声明 `iterator_category` 和 `iterator_concept`，分别给 C++17 接口（[[iterator.cpp17]]）和 C++20 概念（[[iterator.concepts]]）使用。

## `default_sentinel_t` [default.sentinel]

```cpp
struct default_sentinel_t { };
inline constexpr default_sentinel_t default_sentinel{};   // 在 <iterator> 概要中声明
```

¶1 `default_sentinel_t` 是一个空类型，用来表示范围的终点，配合知道自己范围边界的迭代器使用，例如 `counted_iterator`（[[counted.iterator]]）。

它自己没有任何比较运算符，比较逻辑由各个迭代器以 `operator==(const It&, default_sentinel_t)` 的形式提供：

- `counted_iterator` 的计数为 0 时等于 `default_sentinel`；
- `istream_iterator`、`istreambuf_iterator` 到达流末尾时等于 `default_sentinel`，也可以从它构造一个流末迭代器（[[stream.iterators]]）；
- `views::lazy_split` 的迭代器、`std::generator` 等用它作为 `end()` 的类型。

终点信息完全保存在迭代器内部时，哨位不需要任何状态，一个空类型就够了。`[it, default_sentinel)` 这种写法也直接表明终点由迭代器决定。反过来，`vector<int>::iterator` 不知道终点，和 `default_sentinel` 配对不能编译。

## `unreachable_sentinel_t` [unreachable.sentinel]

```cpp
struct unreachable_sentinel_t {
  template<weakly_incrementable I>
    friend constexpr bool operator==(unreachable_sentinel_t, const I&) noexcept
    { return false; }
};
inline constexpr unreachable_sentinel_t unreachable_sentinel{};   // 在 <iterator> 概要中声明
```

¶1 它可以和任何 `weakly_incrementable` 类型一起使用，表示无界区间的上界。比较永远返回 `false`；`!=` 和参数颠倒的写法由 C++20 的比较重写规则自动得到（[[over.match.oper]]）。

约束是 `weakly_incrementable` 而不是 `input_or_output_iterator`，所以它也能和整数比较。`views::iota(0)` 的类型就是 `iota_view<int, unreachable_sentinel_t>`，一个没有尽头的整数序列。

¶2 例 1 给出了它在算法中的用途：在一个确知含有换行符的缓冲区里查找换行符。

```cpp
char* nl = find(p, unreachable_sentinel, '\n');
```

如果换行符确实存在，这样写可能让 `find` 更快，因为每次循环不必再和终点比较，少了一个条件分支。如果换行符不存在，`find` 会读过缓冲区末尾；对无效范围调用库函数，结果是未定义的（[[iterator.requirements.general#12]]）。在不可信的输入上这样查找分隔符，就是一个越界读漏洞。

## 思考题

!!! question "思考题 1"
    `std::sized_sentinel_for<std::unreachable_sentinel_t, int*>` 为真吗？`std::ranges::distance(p, std::unreachable_sentinel)` 会怎样？

<details markdown="1">
<summary>答案</summary>

为假，它没有 `-` 运算。于是 `ranges::distance` 选择逐个递增的重载，它的前提 `[first, last)` 是一个范围不可能满足，调用是未定义行为，实际会一直递增下去。同理，`views::iota(0)` 不是 `sized_range`。
</details>

!!! question "思考题 2"
    `unreachable_sentinel_t::operator==` 为什么写成隐藏友元模板，而不是成员函数？

<details markdown="1">
<summary>答案</summary>

隐藏友元只能通过 ADL 找到，只有某个实参是 `unreachable_sentinel_t` 时才进入重载决议，不会增加其他类型的 `==` 候选。它也不是 `std` 命名空间里的普通函数模板，`using namespace std;` 之后不会出现在任意两个类型的 `==` 查找结果里。C++20 的重写规则再从这一个声明得到 `i == s`、`s != i`、`i != s` 三种写法。
</details>
