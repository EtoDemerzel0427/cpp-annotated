---
title: 通用算法要求
summary: 算法族常用的几个组合概念：在迭代器之间移动、复制、交换元素，跨序列比较，以及原地重排、合并和排序。
status: done
covers: *
since: c++20
papers: P0896R4
related: iterator.concepts, indirectcallable, iterator.cust, concepts.object, range.cmp, algorithms.requirements, lib.types.movedfrom
tags: 标准库, 迭代器, 概念, 算法
updated: 2026-10-19
---

!!! tldr
    - 这一节给算法常用的约束组合起了名字：移动、复制、交换元素，跨序列比较，以及原地重排、合并、排序。
    - 带 `_storable` 的版本还要求能先把元素存进一个值类型的临时对象再写出去，`sort`、`rotate` 这类需要暂存元素的算法要用它。
    - `sortable` 只描述元素能不能排，不含遍历类别；`ranges::sort` 另外要求随机访问，所以 `std::list` 的迭代器是 `sortable`，却不能交给 `ranges::sort`。
    - 默认比较器 `ranges::less` 要求类型 `totally_ordered`，只定义了 `operator<` 的类型能用 `std::sort`，不能用 `ranges::sort`。

单个迭代器概念描述一个迭代器能做什么（[[iterator.concepts]]）。算法关心的往往是几个类型之间的关系：从 `In` 读出的东西能不能写进 `Out`，两个元素能不能原地交换，能不能用比较器比较两个序列的元素。

¶1 [alg.req.general] 把这些组合分成三组：

- 在可读类型和可写类型之间转移元素：`indirectly_movable`、`indirectly_copyable`、`indirectly_swappable`；
- 重排：`permutable`、`mergeable`、`sortable`；
- 跨序列比较：`indirectly_comparable`。

## 默认比较器也有约束（¶2）

<div class="compare" markdown="1">

```cpp run error
#include <algorithm>
#include <vector>
struct L {
  int v;
  bool operator<(const L& o) const
  { return v < o.v; }
};
int main() {
  std::vector<L> v{{2}, {1}};
  std::sort(v.begin(), v.end());  // OK
  std::ranges::sort(v);  // error
}
```

```cpp run ok
#include <algorithm>
#include <vector>
struct S {
  int v;
  auto operator<=>(const S&) const
    = default;
};
int main() {
  std::vector<S> v{{2}, {1}};
  std::sort(v.begin(), v.end());  // OK
  std::ranges::sort(v);           // OK
}
```

</div>

¶2 注 1 提醒，下面几个概念用作默认实参的 `ranges::less` 本身带有约束（[[range.cmp]]），它要求两边的类型建模 `totally_ordered_with`，也就是 `==`、`!=`、`<`、`>`、`<=`、`>=` 都要有。左边的 `L` 只有 `operator<`，所以不是 `sortable<L*>`。最简单的修法是像右边那样默认 `operator<=>`，它同时带来 `==`。也可以显式传一个 `std::less<>{}` 作比较器。

## 移动与复制 [alg.req.ind.move] [alg.req.ind.copy]

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

¶1 `indirectly_movable` 表示可以 `*out = ranges::iter_move(in)`，把元素直接搬过去，`ranges::move` 用的就是它。

¶2 `indirectly_movable_storable` 还要求可以先搬进一个值类型的临时对象，再从临时对象搬出去。`rotate`、`sort` 这类算法需要把一个元素拿出来暂存，就要这个概念。¶3 语义要求：执行 `iter_value_t<In> obj(ranges::iter_move(i));` 之后，`obj` 等于 `*i` 原来的值；如果 `iter_rvalue_reference_t<In>` 是右值引用，`*i` 处于有效但未指明的状态（[[lib.types.movedfrom]]）。

复制版本与之平行：

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

¶2 `_storable` 版本要求暂存的值以四种形式（左值、const 左值、右值、const 右值）都能写进 `Out`，因为算法怎样使用暂存值不受限制。¶3 语义要求：执行 `iter_value_t<In> obj(*i);` 之后 `obj` 等于 `*i` 原来的值；如果 `iter_reference_t<In>` 本身是右值引用（例如 `move_iterator`），`*i` 处于有效但未指明的状态。

`ranges::copy` 只要求 `indirectly_copyable`。`ranges::unique_copy` 要记住上一个元素：输入是前向迭代器时可以记一个迭代器，否则往往只能把元素复制成值保存，这时就要求 `indirectly_copyable_storable`。

## 交换 [alg.req.ind.swap]

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

¶1 这个概念完全建立在定制点 `ranges::iter_swap` 上（[[iterator.cust]]）。实参是 `const I1`，因为交换的是迭代器所指的元素，迭代器本身是不是 const 无关紧要。

## 比较 [alg.req.ind.cmp]

```cpp
template<class I1, class I2, class R, class P1 = identity, class P2 = identity>
concept indirectly_comparable =
  indirect_binary_predicate<R, projected<I1, P1>, projected<I2, P2>>;
```

¶1 意思是能用 `R` 比较两个序列各自投影之后的元素（`projected` 见 [[indirectcallable]]）。`ranges::equal`、`ranges::search`、`ranges::find_first_of` 用它。

## 重排 [alg.req.permutable] [alg.req.mergeable] [alg.req.sortable]

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

- `permutable` 是原地重排的最低条件：前向迭代器、能暂存、能交换。`rotate`、`partition`、`remove` 等用它，`reverse` 另外要求双向。
- `mergeable` 把两个有序的输入序列复制合并到输出，不是原地操作，所以只要求输入迭代器和 `indirectly_copyable`。
- `sortable` 是 `permutable` 加上投影后的严格弱序。

`sortable` 不含随机访问要求。`ranges::sort`、`ranges::stable_sort`、`ranges::partial_sort` 各自另加 `random_access_iterator`，`ranges::inplace_merge` 另加 `bidirectional_iterator`。

```cpp run title="alg_req.cpp" ok
#include <iterator>
#include <list>
#include <memory>
#include <vector>

// sortable 不关心遍历类别
static_assert(std::sortable<std::list<int>::iterator>);
// const_iterator 不能写入，所以不是 permutable
static_assert(!std::sortable<std::vector<int>::const_iterator>);

// unique_ptr：能移动暂存，不能复制暂存
using UP = std::unique_ptr<int>*;
static_assert(std::indirectly_movable_storable<UP, UP>);
static_assert(!std::indirectly_copyable_storable<UP, UP>);
static_assert(std::permutable<std::vector<std::unique_ptr<int>>::iterator>);

// 代理迭代器也可以是 permutable
static_assert(std::permutable<std::vector<bool>::iterator>);

int main() {}
```

`std::ranges::sort(lst)` 对 `std::list` 编译失败，Clang 的诊断指出的是 `random_access_range` 不满足，而不是 `sortable`。两者分工不同：`sortable` 说元素层面能不能排，遍历概念说算法能不能高效地在序列上移动。查一个算法到底要求什么，要看它自己的声明（[[algorithms]]）。

## 思考题

!!! question "思考题 1"
    为什么 `permutable` 要求 `forward_iterator`，而不只是 `input_iterator`？

<details markdown="1">
<summary>答案</summary>

原地重排需要回到已经走过的位置写入：`remove` 把后面的元素搬到前面，`rotate` 要记住中点。这要求迭代器可以复制保存，同一位置可以多次访问，也就是多遍保证（[[iterator.concept.forward]]）。单遍迭代器走过即作废，无法原地重排。
</details>

!!! question "思考题 2"
    `mergeable` 为什么用 `indirectly_copyable`，而不是 `indirectly_copyable_storable`？

<details markdown="1">
<summary>答案</summary>

合并的每一步只需比较两个输入的当前元素，把较小的那个直接从输入复制到输出，不需要中间暂存。所以概念不要求值类型可以复制构造，元素复制代价高或者只能通过代理读写的情形也能使用。
</details>
