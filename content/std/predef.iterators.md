---
title: 迭代器适配器与两个哨位
summary: [predef.iterators] 导读——六类迭代器适配器（reverse、insert、const、move、common、counted）各自解决什么问题；以及两个空哨位类型：default_sentinel_t（"迭代器自己知道何时结束"）与 unreachable_sentinel_t（与任何 weakly_incrementable 比较都不等，用来表示无界区间）。
status: done
covers: default.sentinel, unreachable.sentinel
since: c++98
papers: P0896R4
related: reverse.iterators, insert.iterators, const.iterators, move.iterators, iterators.common, iterators.counted, iterator.concept.sentinel, stream.iterators
tags: 标准库, 迭代器, 适配器, 哨位
updated: 2026-10-18
---

[predef.iterators]（标题 "Iterator adaptors"）收录标准库预定义的迭代器适配器与哨位。**适配器**包装一个底层迭代器（或容器），改变它的某一方面行为，其余尽量保持不变——这是"装饰器"模式在迭代器上的应用。

| 子条款 | 适配器 | 改变了什么 | 页面 |
|---|---|---|---|
| [reverse.iterators] | `reverse_iterator` | 遍历方向 | [[reverse.iterators]] |
| [insert.iterators] | `back_insert_iterator` 等 | 赋值 = 插入容器 | [[insert.iterators]] |
| [const.iterators] | `basic_const_iterator` | 解引用结果变为常量 | [[const.iterators]] |
| [move.iterators] | `move_iterator`、`move_sentinel` | 解引用结果变为右值 | [[move.iterators]] |
| [iterators.common] | `common_iterator` | 把"迭代器 + 不同类型哨位"统一为一个类型 | [[iterators.common]] |
| [default.sentinel] | `default_sentinel_t` | ——（哨位标记类型） | 本页 |
| [iterators.counted] | `counted_iterator` | 携带"还剩几个"的计数 | [[iterators.counted]] |
| [unreachable.sentinel] | `unreachable_sentinel_t` | ——（"永不到达"的哨位） | 本页 |

前两类是 C++98 的老成员；`move_iterator` 来自 C++11；其余（以及 `move_sentinel`）随 C++20 Ranges 加入，`basic_const_iterator` 则是 C++23 新增的。C++20 之后，老适配器都被改写为同时满足两套体系：它们既声明 `iterator_category`（给 [[iterator.cpp17]] 接口），又声明或可推导 `iterator_concept`（给 [[iterator.concepts]]）。

适配器的一些共同模式：

- 以 `base()` 取回底层迭代器；C++20 起的新适配器（以及 `move_iterator`）提供 `const&` 与 `&&` 两个重载，后者把底层迭代器移出——为仅移动的迭代器服务；
- 以**隐藏友元**的形式提供 `iter_move`、`iter_swap`，把定制转发给底层迭代器（[[iterator.cust]]）；
- 只在底层迭代器支持时才提供相应操作（用 `requires` 子句，或者在 C++98 风格的适配器中通过"实例化即要求"的规则，见 [[reverse.iterators]]）。

## `default_sentinel_t`（[default.sentinel]）

```cpp
namespace std {
  struct default_sentinel_t { };
  inline constexpr default_sentinel_t default_sentinel{};
}
```

¶1：一个空类型，用来表示范围的终点；可与"自己知道范围边界"的迭代器类型一起使用，例如 `counted_iterator`（[[counted.iterator]]）。

`default_sentinel_t` 本身没有任何比较运算符——比较逻辑由各个迭代器以 `operator==(const It&, default_sentinel_t)` 的形式提供。标准库中使用它的有：

- `counted_iterator`：计数为 0 时等于 `default_sentinel`；
- `istream_iterator`、`istreambuf_iterator`：到达流末尾时等于 `default_sentinel`，也可以从它构造流末迭代器（[[stream.iterators]]）；
- 若干视图的迭代器（如 `views::lazy_split` 的内层迭代器、生成器类视图）以它作为 `end()` 的类型。

它的价值在于：终点信息完全存在迭代器内部时，哨位不需要携带任何状态，一个空类型就够了，而且 `[it, default_sentinel)` 的写法让"终点由迭代器决定"一目了然。

## `unreachable_sentinel_t`（[unreachable.sentinel]）

```cpp
namespace std {
  struct unreachable_sentinel_t {
    template<weakly_incrementable I>
      friend constexpr bool operator==(unreachable_sentinel_t, const I&) noexcept
      { return false; }
  };
  inline constexpr unreachable_sentinel_t unreachable_sentinel{};
}
```

¶1：`unreachable_sentinel_t` 可以与任何 `weakly_incrementable` 类型一起使用，表示无界区间的"上界"。比较永远返回 `false`（`!=` 由 C++20 的重写规则从 `==` 得到，[[over.match.oper]]）。

¶2 例 1 给出了它的用途：在一个**确知含有换行符**的缓冲区中查找换行符：

```cpp
char* nl = find(p, unreachable_sentinel, '\n');
```

如果换行符确实存在，这样写**可能**让 `find` 更高效：循环条件不再需要与终点比较，少一个条件分支。若换行符不存在，`find` 会越过缓冲区——对无效范围调用库函数是 {{ub}}（[[iterator.requirements.general#12]]）。

约束用的是 `weakly_incrementable` 而不是 `input_or_output_iterator`，所以它也能与整数比较：`views::iota(0)` 就是 `iota_view<int, unreachable_sentinel_t>`，一个"无限"的整数序列。

```cpp run title="sentinels.cpp" ok
#include <algorithm>
#include <cassert>
#include <iterator>
#include <list>
#include <ranges>
#include <vector>

int main() {
    // unreachable：已知目标一定存在时省掉边界检查
    const char buf[] = "key=value";
    auto eq = std::ranges::find(buf + 0, std::unreachable_sentinel, '=');
    assert(eq - buf == 3);

    // default_sentinel：终点由 counted_iterator 自己掌握
    std::list<int> l{1, 2, 3, 4, 5};
    std::vector<int> out;
    std::ranges::copy(std::counted_iterator(l.begin(), 3), std::default_sentinel,
                      std::back_inserter(out));
    assert((out == std::vector{1, 2, 3}));

    // 无界 iota：iota_view<int, unreachable_sentinel_t>
    static_assert(std::same_as<decltype(std::views::iota(0)),
                               std::ranges::iota_view<int, std::unreachable_sentinel_t>>);
    auto first_big = *std::ranges::find_if(std::views::iota(1), [](int i) { return i * i > 50; });
    assert(first_big == 8);
}
```

## 常见误区

!!! pitfall "`default_sentinel` 不是\"通用的终点\""
    它只对**专门支持它**的迭代器有意义。把 `vector<int>::iterator` 与 `default_sentinel` 配对不能编译（没有对应的 `operator==`），这是好事。

!!! pitfall "`unreachable_sentinel` 让算法不再有安全网"
    它把"目标一定存在"变成了调用者的前提条件。在不可信输入上用它查找分隔符，就是一个越界读漏洞。

## 思考题

!!! question "思考题"
    1. `std::sized_sentinel_for<std::unreachable_sentinel_t, int*>` 为真吗？`std::ranges::distance(p, std::unreachable_sentinel)` 会怎样？
    2. 为什么 `unreachable_sentinel_t::operator==` 是隐藏友元模板而不是一个接受 `const auto&` 的成员函数？

<details markdown="1">
<summary>展开查看答案与解析</summary>

1. 为假：它没有 `-` 运算。于是 `ranges::distance` 选择逐个递增的重载，其前条件 `[first, last)` 是范围不可能满足（永不可达）——调用是 UB，实际表现是无限循环直到越界崩溃。同理 `views::iota(0)` 不是 `sized_range`。
2. 隐藏友元只能经 ADL 找到，只在实参之一是 `unreachable_sentinel_t` 时才参与重载决议，不污染其他类型的 `==` 候选集；同时，C++20 的比较重写规则会自动生成 `I == unreachable_sentinel`（参数顺序颠倒）和 `!=` 的形式，一个声明覆盖四种写法。
</details>

## 小结

!!! summary
    - 六类适配器：方向（reverse）、插入（insert）、常量（const）、移动（move）、类型统一（common）、计数（counted）。
    - `default_sentinel_t`：空标记类型，比较逻辑由"知道终点"的迭代器提供（`counted_iterator`、流迭代器等）。
    - `unreachable_sentinel_t`：与任何 `weakly_incrementable` 比较都不等，表示无界；正确性完全由调用者担保。
