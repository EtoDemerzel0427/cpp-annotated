---
title: 通用算法要求
summary: 把迭代器概念组合成"算法族"的需求——indirectly_movable(_storable)、indirectly_copyable(_storable)、indirectly_swappable、indirectly_comparable、permutable、mergeable、sortable；"_storable" 版本额外要求能经由值类型的中间对象中转；permutable 只要求前向迭代器，sortable 不含遍历类别要求，所以 ranges::sort 还要另加 random_access_iterator。
status: done
covers: *
since: c++20
papers: P0896R4
related: iterator.concepts, indirectcallable, iterator.cust, concepts.object, range.cmp, algorithms.requirements, lib.types.movedfrom
tags: 标准库, 迭代器, 概念, 算法
updated: 2026-10-18
---

单个迭代器概念描述的是"一个迭代器能做什么"；而算法关心的是**迭代器之间、迭代器与函数对象之间**的关系：能不能把 `In` 读出的东西写进 `Out`？能不能原地交换两个元素？能不能拿比较器比较两个序列的元素？[alg.req] 把这些常用组合起了名字，让 [[algorithms]] 中上百个 `ranges::` 算法的约束保持简短一致。

¶1 of [alg.req.general] 把它们分为三组：

- 元素在 `indirectly_readable` 与 `indirectly_writable` 之间**转移**：`indirectly_movable`、`indirectly_copyable`、`indirectly_swappable`；
- **重排**：`permutable`、`mergeable`、`sortable`；
- 跨序列**比较**：`indirectly_comparable`。

¶2（注 1）提醒：下文用作默认参数的 `ranges::less` 自身的约束（`totally_ordered_with`，[[range.cmp]]）也会施加到这些概念的实参上——默认比较器不是"无条件可用"的。

## 移动与复制（[alg.req.ind.move]、[alg.req.ind.copy]）

```cpp
template<class In, class Out>
concept indirectly_movable =
  indirectly_readable<In> && indirectly_writable<Out, iter_rvalue_reference_t<In>>;

template<class In, class Out>
concept indirectly_movable_storable =
  indirectly_movable<In, Out> &&
  indirectly_writable<Out, iter_value_t<In>> &&
  movable<iter_value_t<In>> &&
  constructible_from<iter_value_t<In>, iter_rvalue_reference_t<In>> &&
  assignable_from<iter_value_t<In>&, iter_rvalue_reference_t<In>>;
```

- `indirectly_movable`：能 `*out = ranges::iter_move(in)`——直接"搬"过去。对应 `ranges::move`。
- `indirectly_movable_storable`：还能先搬进一个**值类型的临时对象**、再从临时对象搬出去。这是 `rotate`、`sort` 中"拿出一个元素暂存"的需要。¶3 语义：`iter_value_t<In> obj(ranges::iter_move(i));` 之后 `obj` 等于 `*i` 原先的值；若 `iter_rvalue_reference_t<In>` 是右值引用，`*i` 处于有效但未指明状态（[[lib.types.movedfrom]]）。

复制版本平行：

```cpp
template<class In, class Out>
concept indirectly_copyable =
  indirectly_readable<In> && indirectly_writable<Out, iter_reference_t<In>>;

template<class In, class Out>
concept indirectly_copyable_storable =
  indirectly_copyable<In, Out> &&
  indirectly_writable<Out, iter_value_t<In>&> &&
  indirectly_writable<Out, const iter_value_t<In>&> &&
  indirectly_writable<Out, iter_value_t<In>&&> &&
  indirectly_writable<Out, const iter_value_t<In>&&> &&
  copyable<iter_value_t<In>> &&
  constructible_from<iter_value_t<In>, iter_reference_t<In>> &&
  assignable_from<iter_value_t<In>&, iter_reference_t<In>>;
```

`_storable` 版要求临时值的**四种值类别**都能写入 `Out`，因为算法可能以任意方式使用暂存值。¶3 语义：`iter_value_t<In> obj(*i);` 之后 `obj` 等于 `*i` 原先的值；若 `iter_reference_t<In>` 本身是右值引用（如 `move_iterator`），`*i` 处于有效但未指明状态。

典型用户：`ranges::copy` 只要 `indirectly_copyable`；`ranges::unique_copy` 在输入是单遍迭代器、输出又不可读时，必须把"上一个元素"存成值，因而要 `indirectly_copyable_storable`。

## 交换（[alg.req.ind.swap]）

```cpp
template<class I1, class I2 = I1>
concept indirectly_swappable =
  indirectly_readable<I1> && indirectly_readable<I2> &&
  requires(const I1 i1, const I2 i2) {
    ranges::iter_swap(i1, i1);
    ranges::iter_swap(i2, i2);
    ranges::iter_swap(i1, i2);
    ranges::iter_swap(i2, i1);
  };
```

完全建立在 `ranges::iter_swap`（[[iterator.cust]]）之上：只要它的某个分支可用即可。注意对 `const I1` 调用——交换的是**所指元素**，迭代器自身是 const 也无妨。

## 比较（[alg.req.ind.cmp]）

```cpp
template<class I1, class I2, class R, class P1 = identity, class P2 = identity>
concept indirectly_comparable =
  indirect_binary_predicate<R, projected<I1, P1>, projected<I2, P2>>;
```

"用 `R` 比较两个序列各自投影后的元素"。`ranges::equal`、`ranges::search`、`ranges::find_first_of` 用它。

## 重排（[alg.req.permutable]、[alg.req.mergeable]、[alg.req.sortable]）

```cpp
template<class I>
concept permutable =
  forward_iterator<I> && indirectly_movable_storable<I, I> && indirectly_swappable<I, I>;

template<class I1, class I2, class Out, class R = ranges::less,
         class P1 = identity, class P2 = identity>
concept mergeable =
  input_iterator<I1> && input_iterator<I2> && weakly_incrementable<Out> &&
  indirectly_copyable<I1, Out> && indirectly_copyable<I2, Out> &&
  indirect_strict_weak_order<R, projected<I1, P1>, projected<I2, P2>>;

template<class I, class R = ranges::less, class P = identity>
concept sortable = permutable<I> && indirect_strict_weak_order<R, projected<I, P>>;
```

- `permutable`：**原地**重排所需的最低条件——前向迭代器（多遍）、能暂存、能交换。`rotate`、`reverse`（另需双向）、`partition`、`remove` 等用它。
- `mergeable`：把两个有序输入序列**复制**合并到输出——不要求原地，所以只要 `input_iterator` 与 `indirectly_copyable`。
- `sortable`：`permutable` + 投影后的严格弱序。它**不含**随机访问要求：`ranges::sort` 另外写了 `random_access_iterator<I>`，而 `ranges::stable_sort`、`ranges::partial_sort` 等也各自加上遍历要求；`ranges::inplace_merge` 则要求 `bidirectional_iterator` + `sortable`。

```cpp run title="alg_req.cpp" ok
#include <iterator>
#include <list>
#include <memory>
#include <vector>

// list 的迭代器"可排序"——sortable 不关心遍历类别
static_assert(std::sortable<std::list<int>::iterator>);
// const_iterator 不能写入：不是 permutable
static_assert(!std::sortable<std::vector<int>::const_iterator>);

// unique_ptr：能移动暂存，不能复制暂存
using UP = std::unique_ptr<int>*;
static_assert(std::indirectly_movable_storable<UP, UP>);
static_assert(!std::indirectly_copyable_storable<UP, UP>);
static_assert(std::permutable<std::vector<std::unique_ptr<int>>::iterator>);

// 代理迭代器也可以 permutable：vector<bool>
static_assert(std::permutable<std::vector<bool>::iterator>);

int main() {}
```

`std::ranges::sort(lst)` 对 `std::list` 依然编译失败，原因在于 `ranges::sort` 的 `random_access_range` 约束，而不是 `sortable`——这正好说明了两者的分工：`sortable` 描述"元素层面能不能排"，遍历概念描述"算法能不能高效地走"。

## 常见误区

!!! pitfall "以为 `sortable<I>` 就能调用 `ranges::sort`"
    见上：`sortable` 不含遍历类别。查找"某算法到底要求什么"时，以该算法自己的声明为准（[[algorithms]]），这些组合概念只是其中一部分。

!!! pitfall "默认比较器的约束被遗忘"
    `sortable<I>` 的默认 `R` 是 `ranges::less`，它要求值类型 `totally_ordered`（¶2 注 1）。一个只定义了 `operator<` 的类型满足不了 `totally_ordered`（还需要 `>`、`<=`、`>=` 与 `==`）——C++20 中最简单的做法是给它 `operator<=>` 与 `operator==`。

## 思考题

!!! question "思考题"
    1. 为什么 `permutable` 要求 `forward_iterator`，而不是 `input_iterator`？
    2. `mergeable` 为什么用 `indirectly_copyable` 而不是 `indirectly_copyable_storable`？

<details markdown="1">
<summary>展开查看答案与解析</summary>

1. 原地重排至少要回到某个位置写入（比如 `remove` 把后面的元素搬到前面，`rotate` 要记住中点），这要求同一位置能被访问多次、迭代器能被复制保存——这就是多遍保证（[[iterator.concept.forward]]）。单遍迭代器"走过即作废"，无法原地重排。
2. 合并时每一步只需比较两个输入的当前元素、把较小者直接从输入复制到输出，不需要中间暂存。`ranges::merge` 的实现不会创建 `iter_value_t` 临时对象，所以不必要求值类型可复制——这让元素是只读代理或复制代价高的情形也能使用。
</details>

## 小结

!!! summary
    - 转移：`indirectly_movable/copyable`（直接搬）与 `_storable`（可经值类型临时对象中转）；`indirectly_swappable` 基于 `ranges::iter_swap`。
    - 比较：`indirectly_comparable` = 投影后的二元谓词。
    - 重排：`permutable` = 前向 + 可暂存 + 可交换；`mergeable` = 两个输入 + 可复制 + 严格弱序；`sortable` = `permutable` + 严格弱序。
    - 这些概念都不包含算法所需的遍历类别（`permutable` 的前向除外）；遍历要求写在各算法自己的约束里。
