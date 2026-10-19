---
title: counted_iterator
summary: counted_iterator<I> 在底层迭代器旁边记录还剩几个元素，与 default_sentinel 配对表示从某位置开始的 n 个元素；比较和相减只看计数。
status: done
covers: *
since: c++20
papers: P0896R4
related: predef.iterators, iterator.requirements, default.sentinel, iterators.common, iterator.concept.sizedsentinel, structure.specifications, range.counted, istream.iterator
tags: 标准库, 迭代器, 适配器, 计数范围
updated: 2026-10-19
---

!!! tldr
    - `counted_iterator(it, n)` 加上 `default_sentinel` 表示从 `it` 开始的 `n` 个元素，不需要事先知道终点。
    - 比较和相减只看剩余计数，所以与 `default_sentinel` 的距离总能在常数时间得到，即使底层是 `list` 的迭代器。
    - 只看计数的前提是两个迭代器指向同一序列，也就是计数归零的位置对齐；否则是 UB。
    - 遍历类别原样继承自底层，包括 contiguous。
    - 底层是 `istream_iterator` 时，计数归零的那次 `++` 会从流里多读一个元素。

## 计数范围 [counted.iterator]

```cpp run title="counted.cpp" ok
#include <algorithm>
#include <cassert>
#include <iterator>
#include <list>
#include <vector>

int main() {
  std::list<int> l{1, 2, 3, 4, 5, 6};
  std::vector<int> out;
  std::ranges::copy(std::counted_iterator(l.begin(), 4),
                    std::default_sentinel,
                    std::back_inserter(out));
  assert((out == std::vector{1, 2, 3, 4}));

  // list 迭代器只是双向的，但计数范围的距离是常数时间可得的
  using CI = std::counted_iterator<std::list<int>::iterator>;
  static_assert(std::sized_sentinel_for<std::default_sentinel_t, CI>);
  static_assert(std::bidirectional_iterator<CI>);
  static_assert(!std::random_access_iterator<CI>);
  CI it(l.begin(), 4);
  assert(std::default_sentinel - it == 4);

  // 连续迭代器的类别被保留
  static_assert(std::contiguous_iterator<std::counted_iterator<int*>>);
}
```

[[iterator.requirements.general#11]] 定义了**计数范围** `i+[0, n)`：从 `i` 开始的 `n` 个元素。¶1 `counted_iterator` 把它做成了迭代器：行为与底层迭代器相同，另外记录到范围末尾还有多远。它与 `default_sentinel`（一个空的标记类型的对象，[[default.sentinel]]）配合，就能把从某位置开始的 `N` 个元素交给泛型算法。¶2 是标准的例子，与上面的 `ranges::copy` 相同。

```cpp
template<input_or_output_iterator I>
class counted_iterator {
public:
  using iterator_type = I;
  using value_type = iter_value_t<I>;     // 仅当 I 可读
  using difference_type = iter_difference_t<I>;
  using iterator_concept = I::iterator_concept;   // 仅当存在
  using iterator_category = I::iterator_category; // 仅当存在
  // ...
private:
  I current = I();                    // 说明专用
  iter_difference_t<I> length = 0;    // 说明专用
};
```

`iterator_concept` 和 `iterator_category` 直接取自 `I` 的同名成员，所以底层的遍历类别原样保留，连续迭代器也不例外。概要另外为 `iterator_traits<counted_iterator<I>>` 提供了一个特化，继承 `iterator_traits<I>` 的全部成员，只把 `pointer` 改成连续时为 `add_pointer_t<iter_reference_t<I>>`、否则为 `void`。这个特化只在 `I` 的 `iterator_traits` 是特化过的时候才启用。

### 指向同一序列（¶3）

比较和相减只看计数，不看底层迭代器。这要求两个计数迭代器描述的是同一个范围，¶3 给出了精确定义：

!!! std
    Two values i1 and i2 of types counted_iterator<I1> and counted_iterator<I2> refer to elements of the same sequence if and only if there exists some integer n such that next(i1.base(), i1.count() + n) and next(i2.base(), i2.count() + n) refer to the same (possibly past-the-end) element.

换句话说，两个迭代器各自走到计数归零的位置，那两个位置要对齐（允许整体再多走 `n` 步后对齐）。`counted_iterator(v.begin(), 3)` 与 `counted_iterator(v.begin() + 1, 2)` 指向同一序列，终点都是 `v.begin() + 3`。`counted_iterator(v.begin(), 3)` 与 `counted_iterator(v.begin(), 5)` 则不是，比较它们违反前置条件，是 UB。

## 构造与访问

[counted.iter.const] ¶1–¶2 `counted_iterator(I i, iter_difference_t<I> n)` 的加固前置条件是 `n >= 0`。**加固前置条件**（hardened precondition）是 C++26 的说法：在加固实现中，函数在产生其他副作用之前以终止型语义检查它，违反就终止程序；在非加固实现中违反仍是 {{ub}}（[[structure.specifications#3.5]]）。¶3–¶5 可以从 `counted_iterator<I2>` 转换和赋值。

[counted.iter.access] `base()` 返回底层迭代器，`count()` 返回 `length`，后者是 `noexcept` 的。

[counted.iter.elem] 元素访问：

- ¶1–¶2 `*it` 返回 `*current`，加固前置条件是 `length > 0`；
- ¶3 `operator->` 只在 `I` 是连续迭代器时提供，返回 `to_address(current)`；
- ¶4–¶5 `it[n]` 返回 `current[n]`，加固前置条件是 `n < length`。

## 移动位置 [counted.iter.nav]

| 运算 | 效果 | 加固前置条件 |
|---|---|---|
| `++it` | `++current; --length;` | `length > 0`（¶1） |
| `it++`（非前向） | 见下 | `length > 0`（¶3） |
| `it++`（前向） | `= default` | |
| `--it` | `--current; ++length;`（要求双向） | |
| `it + n`、`n + it` | `counted_iterator(current + n, length - n)` | |
| `it += n` | `current += n; length -= n;` | `n <= length`（¶8） |
| `it - n` | `counted_iterator(current - n, length + n)` | |
| `it -= n` | `current -= n; length += n;` | `-n <= length`（¶15） |

¶4 非前向迭代器的后置 `++` 等价于：

```cpp
--length;
try { return current++; }
catch(...) { ++length; throw; }
```

底层的后置 `++` 抛出异常时，计数恢复原值。返回类型是 `decltype(auto)`，底层的后置 `++` 返回什么就返回什么，可能是 `void`。前向迭代器的后置 `++` 和 `--` 声明为 `= default`，效果是复制、前置递增或递减、返回副本（[[over.inc.default]]）。

## 比较与距离

所有比较和距离运算都只用计数：

| 表达式 | 结果 | 前置条件 |
|---|---|---|
| `x - y` | `y.length - x.length` | 同一序列（[counted.iter.nav] ¶11–¶12） |
| `x - default_sentinel` | `-x.length` | |
| `default_sentinel - y` | `y.length` | |
| `x == y` | `x.length == y.length` | 同一序列（[counted.iter.cmp] ¶1–¶2） |
| `x == default_sentinel` | `x.length == 0` | |
| `x <=> y` | `y.length <=> x.length` | 同一序列（¶4–¶5） |

[counted.iter.cmp] ¶6 注 1 解释了 `<=>` 里参数顺序为什么反过来：`length` 越往后越小。比较两个 `counted_iterator` 时底层类型可以不同（`template<common_with<I> I2>`），例如 `vector<int>::iterator` 和 `vector<int>::const_iterator`。

因为距离就是计数，`counted_iterator<I>` 与 `default_sentinel_t` 总是建模 `sized_sentinel_for`（[[iterator.concept.sizedsentinel]]）。`ranges::advance(it, n, default_sentinel)` 因此可以直接算出最多能走几步。

[counted.iter.cust] ¶1–¶4 `iter_move` 和 `iter_swap` 转发给底层迭代器，加固前置条件是相关的计数大于 0。

## 陷阱：与 istream_iterator 组合会多读一个

```cpp run title="counted_istream.cpp" ok
#include <algorithm>
#include <cstdio>
#include <iterator>
#include <sstream>
#include <vector>

int main() {
  std::istringstream in("1 2 3 4 5");
  std::vector<int> out;
  std::ranges::copy(
      std::counted_iterator(std::istream_iterator<int>(in), 2),
      std::default_sentinel, std::back_inserter(out));
  int next;
  in >> next;
  std::printf("copied %zu, next = %d\n", out.size(), next);
}
```

本机输出 `copied 2, next = 4`。只取了 2 个元素，流里的 `3` 却已经被读走了。

`istream_iterator` 在构造时读第一个元素，每次 `++` 读下一个（[[istream.iterator]]）。`ranges::copy` 处理完第 2 个元素后，还会对 `counted_iterator` 执行一次 `++`，计数从 1 变成 0，才等于 `default_sentinel`。这次 `++` 也推进了底层迭代器，于是读走了 `3`。

`views::take`、`views::counted` 作用于输入流时有同样的现象。如果流来自终端，这次多余的读取还会阻塞，等待用户输入。需要精确控制读几个时，用手写循环。

## 思考题

!!! question "思考题 1"
    为什么 `counted_iterator` 比较时不同时比较 `current`？

<details markdown="1">
<summary>答案</summary>

在指向同一序列的前提下，计数相等当且仅当位置相等。只比计数既正确又便宜，而且底层迭代器不能比较相等时也能工作，C++20 的输入迭代器就不必支持 `==`。代价是比较不同序列的计数迭代器违反前置条件，是 UB。
</details>

!!! question "思考题 2"
    `counted_iterator<int*>` 是连续迭代器，`std::to_address` 作用于它时怎样得到指针？

<details markdown="1">
<summary>答案</summary>

`to_address` 对类类型先找 `pointer_traits<counted_iterator<int*>>::to_address`，这里没有；于是调用 `it.operator->()`。`counted_iterator` 恰好只在底层是连续迭代器时提供 `operator->`，返回 `to_address(current)`（[counted.iter.elem] ¶3）。
</details>
