---
title: common_iterator
summary: common_iterator<I, S> 内部存一个迭代器或一个哨位，把首尾类型不同的范围变成首尾同类型，以便交给只接受迭代器对的旧接口。
status: done
covers: *
since: c++20
papers: P0896R4
related: predef.iterators, iterators.counted, default.sentinel, iterator.concept.sentinel, iterator.assoc.types, variant, structure.specifications, range.common
tags: 标准库, 迭代器, 适配器, 哨位, variant
updated: 2026-10-19
---

!!! tldr
    - `common_iterator<I, S>` 内部是一个 `variant<I, S>`：要么持有迭代器，要么持有哨位。首尾两端都用这个类型，就能交给要求 `first`、`last` 同类型的旧接口。
    - 它最高是前向迭代器，不支持 `--` 和 `+=`。
    - 两个都处于哨位状态的 `common_iterator` 比较时总是相等。
    - `operator->` 和后置 `++` 借助说明专用的代理类，让它满足 C++17 输入迭代器的要求。
    - 对哨位状态解引用或递增违反加固前置条件，在加固实现中会终止程序。

## 问题：首尾类型不同

C++20 的范围允许终点是另一种类型的对象，叫做**哨位**（sentinel）：它只需要能与迭代器比较相等（[[iterator.concept.sentinel]]）。例如 `counted_iterator` 配上 `default_sentinel_t` 表示数够 n 个就停（[[iterators.counted]]）。

但大量已有接口要求首尾同类型：容器的迭代器对构造函数、`std::` 命名空间里的旧算法、用户自己的模板。`common_iterator` 就是连接两边的适配器：

```cpp run title="common_iterator.cpp" ok
#include <cassert>
#include <iterator>
#include <list>
#include <ranges>
#include <vector>

int main() {
  std::list<int> l{1, 2, 3, 4, 5, 6};
  using CI = std::common_iterator<
      std::counted_iterator<std::list<int>::iterator>,
      std::default_sentinel_t>;
  // vector 的迭代器对构造函数要求首尾同类型
  std::vector<int> v(CI(std::counted_iterator(l.begin(), 3)),
                     CI(std::default_sentinel));
  assert((v == std::vector{1, 2, 3}));

  static_assert(std::forward_iterator<CI>);
  static_assert(!std::bidirectional_iterator<CI>);

  // views::common 自动做同样的事
  auto r = std::views::counted(l.begin(), 4) | std::views::common;
  std::vector<int> w(r.begin(), r.end());
  assert(w.size() == 4);
}
```

`views::counted` 对非随机访问的迭代器生成 `subrange<counted_iterator<...>, default_sentinel_t>`，首尾类型不同。`views::common`（[[range.common]]）把它包成 `common_view`，`begin()` 和 `end()` 都返回 `common_iterator`。

## 定义 [common.iterator]

¶1 `common_iterator` 是迭代器兼哨位适配器，能把首尾类型不同的**非公共范围**（non-common range）表示成首尾类型相同的**公共范围**（common range）。它的做法是持有一个迭代器或一个哨位，并相应地定义相等比较。¶2 注 1 说明它适合与要求首尾同类型的旧代码对接。

```cpp
template<input_or_output_iterator I, sentinel_for<I> S>
  requires (!same_as<I, S> && copyable<I>)
class common_iterator {
  // ...
private:
  variant<I, S> v_;   // 说明专用
};
```

约束 `!same_as<I, S>` 是因为首尾已经同类型时不需要它。约束 `copyable<I>` 是因为旧接口要求迭代器可复制，只能移动的迭代器无法改造成可复制的。`v_` 的索引 0 表示持有迭代器，索引 1 表示持有哨位（[[variant]]）。

## 关联类型 [common.iter.types]

`iter_difference_t<common_iterator<I, S>>` 就是 `iter_difference_t<I>`。`I` 是输入迭代器时，标准特化了 `iterator_traits<common_iterator<I, S>>`：

- ¶2.1 `iterator_concept`：`I` 建模 `forward_iterator` 时为 `forward_iterator_tag`，否则为 `input_iterator_tag`。哨位状态无法后退，也无法做算术，所以最高只到前向。
- ¶1 `iterator_category`：只有 `iter_difference_t<I>` 是整数类型时才声明。`I` 的类别派生自 `forward_iterator_tag` 时为 `forward_iterator_tag`，否则为 `input_iterator_tag`。
- ¶2.2 `pointer`：`a.operator->()` 良构时取它的类型，否则为 `void`。

`iterator_category` 是给 C++17 接口看的，而 *Cpp17Iterator* 要求 `difference_type` 是有符号整数类型（[[iterator.iterators]]）。差值类型是整数类类型（例如某些 `iota_view` 的迭代器）时，迭代器不满足 C++17 的要求，声明类别就成了虚假申报。

## 构造、访问与递增

[common.iter.const] ¶1–¶2 从 `I` 或 `S` 构造，分别放进 `variant` 的第 0 或第 1 个备选项。这两个构造函数都不是 explicit，所以 `S` 可以直接传给接受 `common_iterator` 的参数。¶3–¶6 从 `common_iterator<I2, S2>` 转换或赋值，按对方当前持有的备选项构造或赋值同一个备选项。

[common.iter.access] ¶1–¶2 `operator*` 返回 `*get<I>(v_)`，加固前置条件是 `holds_alternative<I>(v_)`。**加固前置条件**（hardened precondition）是 C++26 的说法：在加固实现中违反它会以终止型语义报告契约违反，在其他实现中仍是 UB（[[structure.specifications]]）。

¶3–¶5 `operator->` 按底层的情况分三种实现：

1. `I` 是指针或有 `operator->`：返回 `get<I>(v_)` 本身，让 `->` 继续链下去；
2. `iter_reference_t<I>` 是引用类型：返回 `*get<I>(v_)` 的地址；
3. 否则返回说明专用的 *`proxy`* 对象。它把 `*it` 的值存进成员 `keep_`，`operator->` 返回 `keep_` 的地址。解引用按值返回元素的迭代器，就这样得到了一个可以取地址的对象。

[common.iter.nav] ¶1–¶3 前置 `++` 执行 `++get<I>(v_)`。¶4–¶5 后置 `++` 对前向迭代器返回递增前的副本。对单遍的输入迭代器，如果 `*i++` 本身能产生引用，或者值类型无法从引用构造、无法移动构造，就直接返回 `get<I>(v_)++`；否则返回说明专用的 *`postfix-proxy`*，它在递增前保存当前元素的值。

后置 `++` 写得这么复杂，是为了让 `*it++` 可用。*Cpp17InputIterator* 要求这个表达式（[[input.iterators]]），而 C++20 输入迭代器的后置 `++` 可以返回 `void`。有了 *`postfix-proxy`*，`common_iterator` 才能真正交给 C++17 的接口。

[common.iter.cust] 的 `iter_move` 和 `iter_swap` 转发给底层迭代器，加固前置条件是持有迭代器。

## 比较 [common.iter.cmp]

`operator==` 有两个重载，按 `I` 与另一端的 `I2` 能否比较相等来区分：

| 情形 | 两个都是迭代器 | 一个迭代器一个哨位 | 两个都是哨位 |
|---|---|---|---|
| `I`、`I2` 不能比较（¶2） | `true` | 迭代器 `==` 哨位 | `true` |
| `I`、`I2` 能比较（¶4） | 迭代器 `==` 迭代器 | 迭代器 `==` 哨位 | `true` |

¶2 的规则是：两边索引相同就返回 `true`，否则比较两边实际持有的对象。第一行的两个迭代器总是相等，看起来奇怪，但 C++20 输入迭代器本来就不必支持 `==`。旧接口用 `common_iterator` 时只会拿当前位置与终点比较，不会比较两个都持有迭代器的对象，返回什么都不影响结果。两个哨位都表示终点，相等也合理。

¶6 `operator-` 在两边都是哨位时返回 0，否则对实际持有的对象相减，要求相应的 `sized_sentinel_for` 成立。¶1、¶3、¶5 要求比较和相减的两边都不处于 valueless 状态，这也是加固前置条件。

!!! impl "libc++"
    libc++ 用断言实现这些加固前置条件。本机用 `-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_FAST` 编译后，对持有哨位的 `common_iterator` 解引用，程序在断言处陷入并终止；不开加固时同一程序以段错误结束。

## 常见误解

!!! pitfall "`common_iterator` 保留底层的类别"
    它最高只到前向。需要随机访问的旧算法，比如 `std::sort`，不能通过 `common_iterator` 使用随机访问。如果范围是随机访问的且终点是 sized 哨位，更好的办法是用 `ranges::next(first, last)` 直接算出终点迭代器。

!!! pitfall "任何迭代器都能这样包装"
    约束 `copyable<I>` 直接拒绝只能移动的迭代器。这类 C++20 输入迭代器无法接入要求可复制迭代器的旧接口，`views::common` 因此对某些视图不可用。

## 思考题

!!! question "思考题"
    两个 `common_iterator` 都持有哨位，但哨位的值不同（例如两个带不同谓词的哨位），`==` 返回什么？这样规定合理吗？

<details markdown="1">
<summary>答案</summary>

返回 `true`，因为两边的索引都是 1（¶2、¶4）。使用 `common_iterator` 时，哨位状态只出现在终点一侧，一个范围只有一个终点，两个终点相等是合理的。标准也无法比较哨位本身：`sentinel_for` 只要求哨位能与迭代器比较，不要求哨位之间能比较。
</details>
