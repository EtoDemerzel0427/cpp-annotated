---
title: common_iterator
summary: common_iterator<I, S> 用 variant<I, S> 同时容纳迭代器或哨位，把"首尾类型不同"的范围变成首尾同类型的 common range，以便交给只接受迭代器对的老接口；它最多是前向迭代器；两个哨位状态互相比较总相等；operator-> 与后置 ++ 需要 proxy 类；C++26 起大量前条件改为 hardened preconditions。
status: done
covers: *
since: c++20
papers: P0896R4
related: predef.iterators, iterators.counted, default.sentinel, iterator.concept.sentinel, iterator.assoc.types, variant, structure.specifications, range.common
tags: 标准库, 迭代器, 适配器, 哨位, variant
updated: 2026-10-18
---

C++20 允许范围的首尾类型不同（迭代器 + 哨位），但大量既有接口——容器的迭代器对构造函数、非 `ranges::` 算法、用户的老代码——都要求 `first` 与 `last` **同类型**。`common_iterator` 是两个世界之间的桥：

¶1 of [common.iterator]：类模板 `common_iterator` 是迭代器/哨位适配器，能把**非公共范围**（*non-common range*，迭代器与哨位类型不同）表示为**公共范围**（*common range*，二者类型相同）。做法是**持有一个迭代器或一个哨位**，并相应地实现相等比较。¶2（注 1）：它适合与要求首尾同类型的遗留代码对接。`views::common`（[[range.common]]）就是用它实现的。

## 类定义要点

```cpp
template<input_or_output_iterator I, sentinel_for<I> S>
  requires (!same_as<I, S> && copyable<I>)
class common_iterator {
  // ...
private:
  variant<I, S> v_;   // 说明专用
};
```

- 约束 `!same_as<I, S>`：首尾已经同类型时不需要它；
- 约束 `copyable<I>`：老接口要求迭代器可复制，仅移动的迭代器无法被"变成"可复制的；
- 存储是 `variant<I, S>`（[[variant]]）：索引 0 表示"我是迭代器"，索引 1 表示"我是哨位"。

关联类型（[common.iter.types]）通过特化 `incrementable_traits` 与 `iterator_traits` 给出：

- `iter_difference_t<common_iterator<I, S>>` = `iter_difference_t<I>`；
- `iterator_traits<common_iterator<I, S>>`（`I` 为输入迭代器时）：
    - ¶2.1 `iterator_concept`：`I` 建模 `forward_iterator` 时为 `forward_iterator_tag`，否则 `input_iterator_tag`——**最高是前向**。`common_iterator` 不支持 `--`、`+=`，因为"哨位状态"无法后退或做算术。
    - ¶1 `iterator_category`：仅当 `iter_difference_t<I>` 是**整数类型**时声明（整数类类型不行——老接口要求内建整数）；`I` 的类别派生自 `forward_iterator_tag` 时为 `forward_iterator_tag`，否则 `input_iterator_tag`。
    - ¶2.2 `pointer`：若 `a.operator->()` 合法则为其类型，否则 `void`。

## 构造与转换（[common.iter.const]）

- 从 `I`：`v_{in_place_type<I>, std::move(i)}`；从 `S`：`v_{in_place_type<S>, std::move(s)}`（¶1–¶2）——均为隐式构造，所以可写 `CI(it)`、`CI(sentinel)`，也可以直接把 `it` 传给接受 `CI` 的参数。
- 从 `common_iterator<I2, S2>` 转换：¶3 *Hardened preconditions*：`x.v_` 不是 valueless；¶4 按 `x` 的当前索引构造同一备选项。
- 赋值：同索引则就地赋值，不同则 `emplace`（¶6）。

## 访问与导航（[common.iter.access]、[common.iter.nav]）

- `operator*`：¶1 *Hardened preconditions*：`holds_alternative<I>(v_)`——**对哨位状态解引用违反加固前条件**；¶2 返回 `*get<I>(v_)`。
- `operator->`：¶3 的 requires 子句要求 `indirectly_readable<const I>`，且下列之一成立：`I` 有 `operator->`、`iter_reference_t<I>` 是引用、值类型可从引用构造。¶5 三种实现：
    1. `I` 是指针或有 `operator->`：返回 `get<I>(v_)` 本身（让 `->` 链式下钻）；
    2. 引用是引用类型：`auto&& tmp = *get<I>(v_); return addressof(tmp);`；
    3. 否则：返回说明专用类 *`proxy`*，它把 `*it` 的值存进成员 `keep_`，其 `operator->` 返回 `addressof(keep_)`——为按值返回元素的迭代器制造一个可取地址的临时副本。
- `operator++`：¶1 加固前条件 `holds_alternative<I>(v_)`；¶2 `++get<I>(v_)`。
- 后置 `operator++(int)`：对前向迭代器是预置的（[[over.inc.default]]）；对输入迭代器，¶5 规定：若 `*i++` 可引用，或值类型无法从引用构造/无法移动构造，则返回 `get<I>(v_)++`；**否则**返回一个 *`postfix-proxy`*，它在递增前保存当前元素的值，使 `*it++` 这一 *Cpp17InputIterator* 必需的表达式可用。

后置 `++` 的复杂处理，目的正是让 `common_iterator` 满足 *Cpp17InputIterator* 的 `*r++` 要求（[[input.iterators]]），从而真正能交给 C++17 接口——即使底层 C++20 输入迭代器的后置 `++` 返回 `void`。

## 比较与距离（[common.iter.cmp]）

两个 `operator==` 重载按 `I` 与 `I2` 是否可比较区分：

| 情形 | 两个都是迭代器 | 一个迭代器一个哨位 | 两个都是哨位 |
|---|---|---|---|
| `I`、`I2` 不可比较（¶2） | **总是 `true`**（`i == j` 时） | 迭代器 `==` 哨位 | `true` |
| `I`、`I2` 可比较（¶4） | 迭代器 `==` 迭代器 | 迭代器 `==` 哨位 | `true` |

第一行"两个迭代器总相等"初看惊人。原因：¶2 的规则是"索引相同（`i == j`）则返回 `true`"——对**不可比较**的输入迭代器（C++20 输入迭代器不必支持 `==`），老接口最多只会拿"当前位置"与"终点"比较，从不比较两个都处于迭代器状态的对象，所以返回什么都无所谓。而两个都处于哨位状态时，它们都表示"终点"，相等是合理的。

`operator-`（¶6）：两个都是哨位时为 0，否则对实际持有的对象做减法，要求相应的 `sized_sentinel_for`。所有比较与距离运算都有加固前条件：两个 `variant` 都不是 valueless。

## 定制（[common.iter.cust]）

`iter_move` 与 `iter_swap` 转发给底层迭代器，加固前条件要求持有的是迭代器。

## 例子：把计数范围交给老接口

```cpp run title="common_iterator.cpp" ok
#include <cassert>
#include <iterator>
#include <list>
#include <ranges>
#include <vector>

int main() {
    std::list<int> l{1, 2, 3, 4, 5, 6};
    using CI = std::common_iterator<std::counted_iterator<std::list<int>::iterator>,
                                    std::default_sentinel_t>;
    // vector 的迭代器对构造函数要求首尾同类型
    std::vector<int> v(CI(std::counted_iterator(l.begin(), 3)), CI(std::default_sentinel));
    assert((v == std::vector{1, 2, 3}));

    static_assert(std::forward_iterator<CI>);
    static_assert(!std::bidirectional_iterator<CI>);    // list 迭代器是双向的，但 CI 封顶前向

    // views::common 自动做同样的事
    auto r = std::views::counted(l.begin(), 4) | std::views::common;
    std::vector<int> w(r.begin(), r.end());
    assert(w.size() == 4);
}
```

（`views::counted(l.begin(), 4)` 对非随机访问迭代器生成 `subrange<counted_iterator<...>, default_sentinel_t>`，不是公共范围；`views::common` 把它包成 `common_view`，其 `begin()`/`end()` 都是 `common_iterator`。）

!!! impl "libc++"
    libc++ 把各处"加固前条件"实现为 `_LIBCPP_ASSERT_VALID_ELEMENT_ACCESS` 等断言：在快速加固模式下，对哨位状态的 `common_iterator` 解引用会直接陷入（trap），而不是读取 `variant` 中不存在的备选项。

## 常见误区

!!! pitfall "以为 `common_iterator` 保留底层类别"
    它最高只到前向。需要随机访问的老算法（`std::sort`）不能经由 `common_iterator` 获得随机访问能力；对随机访问 + sized 哨位的范围，更好的做法是直接算出终点迭代器（`ranges::next(first, last)`）。

!!! pitfall "对仅移动的迭代器使用"
    约束 `copyable<I>` 直接拒绝。C++20 输入迭代器若是仅移动的，无法接入要求可复制迭代器的老接口——这是 `views::common` 对某些视图不可用的原因。

## 思考题

!!! question "思考题"
    1. 为什么 `iterator_category` 只在差值类型是**整数类型**时才声明？
    2. 两个 `common_iterator` 都持有哨位、但哨位的值不同（例如两个不同的谓词哨位），`==` 返回什么？这合理吗？

<details markdown="1">
<summary>展开查看答案与解析</summary>

1. `iterator_category` 是给 C++17 接口看的，而 *Cpp17Iterator* 要求 `difference_type` 是有符号整数类型（[[iterator.iterators]]）。若差值类型是整数类类型（如 `iota_view<long long>` 的迭代器），它根本不满足 *Cpp17InputIterator*，声明类别就是虚假申报。不声明则老接口会因缺少类别而拒绝它。
2. 返回 `true`（两个索引都是 1）。在 `common_iterator` 的使用场景中，哨位状态只出现在"终点"一侧，一个范围只有一个终点，比较两个终点相等是合理的；标准选择不去比较哨位本身，因为哨位不要求能相互比较（`sentinel_for` 只要求哨位与迭代器可比较）。
</details>

## 小结

!!! summary
    - `common_iterator<I, S>` = `variant<I, S>`：把"迭代器 + 异类哨位"统一成一个类型，供要求首尾同类型的接口使用。
    - 类别最高前向；`iterator_category` 仅在差值类型是整数类型时声明。
    - `->` 与后置 `++` 借助说明专用的 proxy 类，使其满足 *Cpp17InputIterator*。
    - 两个哨位状态总相等；不可比较的输入迭代器之间也"总相等"。
    - C++26 将其前条件标为加固前条件（hardened preconditions）。
