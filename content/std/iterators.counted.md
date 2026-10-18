---
title: counted_iterator
summary: counted_iterator<I> 携带"到范围末尾还剩几个"的计数 length，与 default_sentinel 配对表示计数范围 i+[0, n)；比较与相减只看计数（前提是"指向同一序列"）；保留底层的 iterator_concept/iterator_category；C++26 以 hardened preconditions 约束 n >= 0、解引用时 length > 0 等；与 istream_iterator 组合时会多读一个元素。
status: done
covers: *
since: c++20
papers: P0896R4
related: predef.iterators, iterator.requirements, default.sentinel, iterators.common, iterator.concept.sizedsentinel, structure.specifications, range.counted, istream.iterator
tags: 标准库, 迭代器, 适配器, 计数范围
updated: 2026-10-18
---

[[iterator.requirements.general#11]] 定义了**计数范围** `i+[0, n)`：从 `i` 开始的 `n` 个元素，不需要知道终点。`counted_iterator` 把这个概念做成了迭代器：

¶1 of [counted.iterator]：`counted_iterator` 是迭代器适配器，行为与底层迭代器相同，只是**额外记录到范围末尾的距离**。它可与 `default_sentinel` 一起，在调用泛型算法时处理"从某位置开始的 `N` 个元素"，而无需事先知道终点。¶2 例 1：

```cpp
ranges::copy(counted_iterator(s.begin(), 10), default_sentinel, back_inserter(v));
```

## "指向同一序列"（¶3）

!!! std
    Two values i1 and i2 of types counted_iterator<I1> and counted_iterator<I2> refer to elements of the same sequence if and only if there exists some integer n such that next(i1.base(), i1.count() + n) and next(i2.base(), i2.count() + n) refer to the same (possibly past-the-end) element.

    两个 `counted_iterator` **指向同一序列**，当且仅当存在整数 `n`，使二者各自"走到计数终点再多走 `n` 步"后指向同一元素（可以是过尾位置）。

换言之：它们的**计数终点对齐**。这是比较与相减的前条件——因为这些运算只看计数，不看底层迭代器。`counted_iterator(v.begin(), 3)` 与 `counted_iterator(v.begin() + 1, 2)` 指向同一序列（终点都是 `v.begin() + 3`）；`counted_iterator(v.begin(), 3)` 与 `counted_iterator(v.begin(), 5)` 则不是。

## 类定义要点

```cpp
template<input_or_output_iterator I>
class counted_iterator {
public:
  using iterator_type = I;
  using value_type = iter_value_t<I>;            // 仅当 I 建模 indirectly_readable
  using difference_type = iter_difference_t<I>;
  using iterator_concept = I::iterator_concept;   // 仅当该限定名有效
  using iterator_category = I::iterator_category; // 仅当该限定名有效
  // ...
private:
  I current = I();                    // 说明专用
  iter_difference_t<I> length = 0;    // 说明专用
};

template<input_iterator I>
  requires same_as<ITER_TRAITS(I), iterator_traits<I>>
struct iterator_traits<counted_iterator<I>> : iterator_traits<I> {
  using pointer = conditional_t<contiguous_iterator<I>,
                                add_pointer_t<iter_reference_t<I>>, void>;
};
```

- **类别完全保留**：`iterator_concept` 与 `iterator_category` 直接取自 `I` 的成员（若存在）。底层是连续迭代器时，`counted_iterator` 的 `iterator_concept` 也是 `contiguous_iterator_tag`；未声明时，*`ITER_CONCEPT`* 落到默认的 `random_access_iterator_tag`，再由语法要求决定实际类别。
- `iterator_traits` 特化：仅当 `I` 的 `iterator_traits` 是用户/库特化（*`ITER_TRAITS(I)`* 就是 `iterator_traits<I>`）时才提供，继承底层的全部成员，只改写 `pointer`。用户没有特化时，`counted_iterator` 自己的成员已足以让主模板正确推导。

## 构造与访问（[counted.iter.const]、[counted.iter.access]、[counted.iter.elem]）

- `counted_iterator(I i, iter_difference_t<I> n)`：¶1 **加固前条件** `n >= 0`；¶2 初始化 `current`、`length`。C++26 把这类前条件改为加固前条件（[[structure.specifications]]）：在加固实现（[[g:hardened-implementation]]）中，函数在产生任何其他可观察副作用之前，以**终止语义**求值相应的契约断言（[[basic.contract.eval]]）——违反即终止程序；在非加固实现中违反仍是 {{ub}}（[[structure.specifications#3.5]]）。
- 转换构造/赋值：从 `counted_iterator<I2>`（¶3–¶5）。
- `base() const&`、`base() &&`、`count()`：`count()` 返回 `length`，`noexcept`。
- `operator*`：¶1 加固前条件 `length > 0`；¶2 `return *current;`。
- `operator->`：仅当 `I` 是连续迭代器时提供，`noexcept`，返回 `to_address(current)`（¶3）。
- `operator[](n)`：¶4 加固前条件 `n < length`；¶5 `return current[n];`。

## 导航（[counted.iter.nav]）

| 运算 | 效果 | 加固前条件 |
|---|---|---|
| `++it` | `++current; --length;` | `length > 0` |
| `it++`（非前向） | `--length; try { return current++; } catch(...) { ++length; throw; }` | `length > 0` |
| `it++`（前向） | 预置（[[over.inc.default]]） | — |
| `--it` | `--current; ++length;`（要求双向） | — |
| `it + n`、`n + it` | `counted_iterator(current + n, length - n)`（要求随机访问） | — |
| `it += n` | `current += n; length -= n;` | `n <= length` |
| `it - n` | `counted_iterator(current - n, length + n)` | — |
| `it -= n` | `current -= n; length += n;` | `-n <= length` |

非前向时的后置 `++` 用 `try`/`catch` 保证**强异常安全**：若底层的后置 `++` 抛出，计数恢复原值。返回类型是 `decltype(auto)`——底层后置 `++` 返回什么（可能是 `void`）就返回什么。

## 比较与距离（[counted.iter.nav]、[counted.iter.cmp]）

全部只看计数：

- `x - y`（`counted_iterator` 之间）：¶11 前条件：指向同一序列；¶12 返回 `y.length - x.length`；
- `x - default_sentinel`：`-x.length`；`default_sentinel - y`：`y.length`（均 `noexcept`）；
- `x == y`：前条件同一序列，返回 `x.length == y.length`；
- `x == default_sentinel`：`x.length == 0`；
- `x <=> y`：返回 `y.length <=> x.length`——注 1：参数顺序反转，因为 `length` 是**递减**计数的。

所以 `counted_iterator<I>` 与 `default_sentinel_t` **总是**建模 `sized_sentinel_for`，即使 `I` 是 `list` 迭代器：距离就是计数，常数时间可得（[[iterator.concept.sizedsentinel]] 例 1）。这也是 `ranges::advance(it, n, default_sentinel)` 对计数迭代器能一次算出可走步数的原因。

比较两个 `counted_iterator` 允许底层类型不同（`template<common_with<I> I2>`）——例如 `counted_iterator<iterator>` 与 `counted_iterator<const_iterator>`。

## 定制（[counted.iter.cust]）

`iter_move(i)`：加固前条件 `i.length > 0`，转发 `ranges::iter_move(i.current)`；`iter_swap(x, y)`：加固前条件两者计数都大于 0，转发 `ranges::iter_swap`。

## 例子

```cpp run title="counted.cpp" ok
#include <algorithm>
#include <cassert>
#include <iterator>
#include <list>
#include <vector>

int main() {
    std::list<int> l{1, 2, 3, 4, 5, 6};
    std::vector<int> out;
    std::ranges::copy(std::counted_iterator(l.begin(), 4), std::default_sentinel,
                      std::back_inserter(out));
    assert((out == std::vector{1, 2, 3, 4}));

    // list 迭代器只是双向的，但计数范围的距离是常数时间可得的
    using CI = std::counted_iterator<std::list<int>::iterator>;
    static_assert(std::sized_sentinel_for<std::default_sentinel_t, CI>);
    static_assert(std::bidirectional_iterator<CI> && !std::random_access_iterator<CI>);
    CI it(l.begin(), 4);
    assert(std::default_sentinel - it == 4);

    // 连续迭代器的类别被保留
    static_assert(std::contiguous_iterator<std::counted_iterator<int*>>);
}
```

## 陷阱：与 `istream_iterator` 组合会多读一个

```cpp run title="counted_istream.cpp" ok
#include <algorithm>
#include <cstdio>
#include <iterator>
#include <sstream>
#include <vector>

int main() {
    std::istringstream in("1 2 3 4 5");
    std::vector<int> out;
    std::ranges::copy(std::counted_iterator(std::istream_iterator<int>(in), 2),
                      std::default_sentinel, std::back_inserter(out));
    int next;
    in >> next;
    std::printf("copied %zu, next read = %d\n", out.size(), next);   // copied 2, next read = 4
}
```

只取了 2 个元素，流中的 `3` 却已被消费。原因：`istream_iterator` 在**构造时**读第一个元素、每次 `++` 读下一个（[[istream.iterator]]）；`ranges::copy` 处理完第 2 个元素后仍会对 `counted_iterator` 执行一次 `++`（计数从 1 变为 0，从而等于 `default_sentinel`），而这次 `++` 推进了底层迭代器，读走了 `3`。`views::take`、`views::counted` 作用于输入流时有同样的现象。若流是交互式的（如终端），这次多余的读取还会**阻塞**等待输入。社区曾提议增加一个"惰性"计数迭代器（在计数归零时不推进底层）来解决，但未被标准采纳；需要精确控制时，手写循环。

## 思考题

!!! question "思考题"
    1. 为什么 `counted_iterator` 的比较不同时比较 `current`？
    2. `counted_iterator<int*>` 是 `contiguous_iterator`，它的 `to_address` 是如何得到的？

<details markdown="1">
<summary>展开查看答案与解析</summary>

1. 在"指向同一序列"的前条件下，计数相等当且仅当位置相等，只比计数既正确又便宜，而且对底层不可比较的迭代器（C++20 输入迭代器）也能工作。代价是比较不同序列的计数迭代器是 UB（违反前条件）。
2. `to_address` 对类类型先找 `pointer_traits<counted_iterator<int*>>::to_address`（不存在），再调用 `it.operator->()`——而 `counted_iterator` 恰好只在底层是连续迭代器时提供 `operator->`，返回 `to_address(current)`（[counted.iter.elem] ¶3）。
</details>

## 小结

!!! summary
    - `counted_iterator` = 底层迭代器 + 剩余计数；配 `default_sentinel` 表示 `i+[0, n)`。
    - 比较、相减只看计数，前提是"指向同一序列"（计数终点对齐）；与 `default_sentinel` 总是 sized。
    - 类别从底层原样继承，包括 contiguous。
    - 前条件（`n >= 0`、解引用时 `length > 0` 等）在 C++26 中为加固前条件。
    - 对单遍输入迭代器，计数归零时那次 `++` 会多推进一次底层。
