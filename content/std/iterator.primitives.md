---
title: 迭代器原语
summary: 六个类别标签及其继承链与标签分派；std::advance / distance / next / prev 的前条件（负步长只对双向迭代器、distance 允许随机访问迭代器"反向可达"）；ranges::advance 的三个重载（计数、哨位、计数+哨位并返回剩余步数）、ranges::distance、ranges::next/prev——它们是算法函数对象，不参与 ADL 且会抑制 ADL。
status: done
covers: *
since: c++98
papers: P0896R4
related: iterator.requirements, iterator.concepts, iterator.cpp17, iterator.assoc.types, alg.func.obj, customization.point.object, basic.lookup.argdep, expr.add
tags: 标准库, 迭代器, advance, distance, 标签分派, 算法函数对象
updated: 2026-10-18
---

[[iterator.requirements.general#14]] 规定每个迭代器类别只提供能在常数时间实现的操作：`list` 迭代器没有 `+`，`forward_list` 迭代器没有 `--`。但算法常常需要"走 `n` 步"或"算距离"。[iterator.primitives] 提供这些"按类别选择最优实现"的工具：

- 类别标签（[std.iterator.tags]）——C++98 的编译期分派手段；
- `std::advance`/`distance`/`next`/`prev`（[iterator.operations]）——按 `iterator_category` 分派；
- `std::ranges::advance`/`distance`/`next`/`prev`（[range.iter.ops]）——按 C++20 概念分派，并支持哨位。

¶1 of [iterator.primitives.general]：为了简化迭代器的使用，库提供若干类与函数。

## 类别标签（[std.iterator.tags]）

```cpp
struct output_iterator_tag { };
struct input_iterator_tag { };
struct forward_iterator_tag : public input_iterator_tag { };
struct bidirectional_iterator_tag : public forward_iterator_tag { };
struct random_access_iterator_tag : public bidirectional_iterator_tag { };
struct contiguous_iterator_tag : public random_access_iterator_tag { };
```

¶1：函数模板特化常需要知道迭代器实参"最具体"的类别以便在编译期选择最高效的算法，为此库引入这些空的**类别标签**类（[[g:iterator-category-tag]]）。对每个迭代器类型 `I`，`iterator_traits<I>::iterator_category` 必须声明为描述其行为的标签；另外可以用 `iterator_traits<I>::iterator_concept` 表示对 C++20 概念的符合。

继承链的意义在于**重载决议中的派生到基类转换**：以 `random_access_iterator_tag` 实参调用一组接受 `input_iterator_tag`/`bidirectional_iterator_tag`/`random_access_iterator_tag` 的重载，最精确的匹配胜出；没有随机访问重载时，派生到基类转换会选中双向版本（[[over.ics.rank]]）。`output_iterator_tag` 不在链上——"输出"与"输入"是正交的能力。

¶2 例 1 展示了 C++98 式的做法：特化 `iterator_traits<BinaryTreeIterator<T>>`，申报为 `bidirectional_iterator_tag`。¶3 例 2 展示标签分派：

```cpp
template<class BidirectionalIterator>
void evolve(BidirectionalIterator first, BidirectionalIterator last) {
  evolve(first, last,
         typename iterator_traits<BidirectionalIterator>::iterator_category());
}
// 再分别提供 bidirectional_iterator_tag 与 random_access_iterator_tag 两个重载
```

C++20 之后，同样的分派更常写成 `if constexpr (std::random_access_iterator<I>)` 或带约束的重载——概念之间的包含关系（[[temp.constr.order]]）取代了标签之间的继承关系。

!!! note "`contiguous_iterator_tag` 与老代码"
    `contiguous_iterator_tag` 派生自 `random_access_iterator_tag`，所以老式标签分派代码遇到它会自然退化为随机访问路径。不过标准库自己的类型在 `iterator_category` 中几乎从不申报它（指针的 `iterator_category` 仍是 `random_access_iterator_tag`，见 [[iterator.traits]]），它主要出现在 `iterator_concept` 中。

## `std::` 版本（[iterator.operations]）

¶1：只有随机访问迭代器提供 `+` 和 `-`，所以库提供 `advance` 和 `distance`：对随机访问迭代器用 `+`/`-`（常数时间），对其他迭代器用 `++`（线性时间）。四个函数都是 `constexpr`。

### `advance(i, n)`

¶2 *Preconditions*：`n` 只有对**双向**迭代器才可以为负。¶3 *Effects*：`n` 非负时把 `i` 递增 `n` 次，否则递减 `-n` 次。

`Distance` 是独立的模板参数，可以是任何整数类型；返回 `void`，`i` 按引用修改。

### `distance(first, last)`

!!! std
    *Preconditions*: last is reachable from first, or InputIterator meets the *Cpp17RandomAccessIterator* requirements and first is reachable from last.

    前条件：`last` 从 `first` 可达；**或者** `InputIterator` 满足 *Cpp17RandomAccessIterator* 且 `first` 从 `last` 可达。

¶5 *Effects*：随机访问迭代器返回 `last - first`；否则递增 `first` 直到到达 `last`，返回递增次数。所以对随机访问迭代器 `distance` 可以返回**负数**；对其他迭代器传反了首尾是 UB（实际上会一直 `++` 越过末尾）。

### `next(x, n = 1)`、`prev(x, n = 1)`

¶6：`next` 等价于 `advance(x, n); return x;`。¶7：`prev` 等价于 `advance(x, -n); return x;`。注意 `prev` 的模板参数名是 `BidirectionalIterator`——即使 `n` 是负数（"向前走"），也要求双向迭代器。

这四个函数都按 *Cpp17* 命名要求与 `iterator_category` 工作；对 C++20 迭代器（如 `iota_view` 的迭代器，类别标签是 `input_iterator_tag`）会退化为线性实现，甚至违反前条件（`prev`）——见 [[iterator.cpp17]] 中的实例。

## `std::ranges::` 版本（[range.iter.ops]）

¶1 of [range.iter.ops.general]：`ranges::advance`、`distance`、`next`、`prev` 根据每种迭代器类别提供的运算符给出尽可能高效的实现。例 1：对 `random_access_iterator`，`ranges::advance` 用 `+` 在常数时间内前进；否则执行 `n` 次 `++`。

¶2 关键一句：

!!! std
    The entities defined in [range.iter.ops] are algorithm function objects ([alg.func.obj]).

    [range.iter.ops] 中定义的实体是**算法函数对象**。

### 算法函数对象：不被 ADL 找到，也抑制 ADL

[[alg.func.obj]] 规定：算法函数对象是一种定制点对象（[[customization.point.object]]），按"一组重载的函数模板"来规格化；`o(args...)` 与"名字查找结果为该重载集的 `s(args...)`"表达式等价。其注 1 说明后果：

- 它们**不会**被实参依赖查找找到；
- 当它们被非限定查找找到、作为函数调用的后缀表达式时，会**抑制** ADL（[[basic.lookup.argdep]]：若普通查找找到的不是函数或函数模板声明，就不进行 ADL）。

这正是社区俗称的 "niebloid"（以 Eric Niebler 命名）。效果：

```cpp run title="niebloid.cpp" ok
#include <cassert>
#include <iterator>
#include <vector>

namespace user {
struct Widget { int v; };
// 一个"贪婪"的、可能被 ADL 找到的同名模板
template<class It> It next(It it) { return it; }
}

int main() {
    std::vector<user::Widget> v(3);
    using namespace std::ranges;
    // 非限定查找找到 std::ranges::next（一个对象）→ 不进行 ADL，
    // user::next 不会参与竞争，即便实参类型关联了 user 命名空间
    auto it = next(v.begin());
    assert(it == v.begin() + 1);
}
```

对比：若去掉 `using namespace std::ranges;`、直接写 `next(v.begin())`，ADL 会在 `std`（`vector` 迭代器的关联命名空间）和 `user`（模板实参 `Widget` 的关联命名空间）中同时找到 `std::next` 与 `user::next`。两者对这一个实参都是完全匹配，部分排序只比较有实参对应的那个参数，分不出高下——clang 报 "call to 'next' is ambiguous"。算法函数对象从根本上消除了这类问题。

!!! impl "libc++ 的实现"
    libc++ 把 `ranges::advance` 实现为结构体 `ranges::__advance` 的 `inline constexpr` 实例（位于内联命名空间 `__cpo` 中），`operator()` 重载对应标准中的各个函数模板。对象类型不可被 ADL 找到是语言规则的自然结果，不需要额外技巧。

### `ranges::advance`（[range.iter.op.advance]）

三个重载：

**`advance(i, n)`**：¶1 前条件：若 `I` 不建模 `bidirectional_iterator`，`n` 非负。¶2：随机访问时等价于 `i += n`；否则 `n` 非负时递增 `n` 次，负时递减 `-n` 次。

**`advance(i, bound)`**：¶3 前条件：`assignable_from<I&, S> || sized_sentinel_for<S, I>` 被建模，**或者** `[i, bound)` 表示范围。¶4：

1. `I` 可从 `S` 赋值 → `i = std::move(bound)`（一步到位）；
2. 否则 `S` 是 `I` 的 sized 哨位 → `ranges::advance(i, bound - i)`；
3. 否则逐个 `++` 直到 `i == bound`。

前条件中的"或者"说明：前两种情况下甚至不需要 `[i, bound)` 是范围——赋值和减法本身就把 `i` 放到了正确位置（这里隐含地依赖 [[iterator.concept.sentinel]] (2.3) 与 [[iterator.concept.sizedsentinel]] 的语义要求）。

**`advance(i, n, bound)`**——带上限的前进，返回**未走完的步数**：

- ¶5 前条件：`n > 0` 时 `[i, bound)` 是范围；`n == 0` 时 `[i, bound)` 或 `[bound, i)` 是范围；`n < 0` 时 `[bound, i)` 是范围、`I` 是双向迭代器且 `S` 与 `I` 同类型；
- ¶6 效果：若 `S` 是 sized 哨位——`|n| >= |bound - i|` 时直接走到 `bound`，否则走 `n` 步；否则逐步前进（或后退），在到达 `bound` 时提前停止，至多 `|n|` 步；
- ¶7 返回：`n - M`，`M` 是 `i` 实际移动的有符号距离。

这是"安全地走最多 `n` 步"的标准工具；例如 `views::drop` 的 `begin()` 就规定为 `ranges::next(ranges::begin(base), count, ranges::end(base))`。

### `ranges::distance`（[range.iter.op.distance]）

三个重载：

- `distance(first, last)`，`S` **不是** sized 哨位：¶1 前条件 `[first, last)` 是范围；¶2 逐个递增计数。注意 `first` 按值传入。
- `distance(I&& first, S last)`，`S` 是 `decay_t<I>` 的 sized 哨位：¶3 直接 `last - first`；若 `I` 是数组类型的引用，先 `static_cast<decay_t<I>>(first)` 退化为指针。转发引用加上这个特殊处理，是为了让 `ranges::distance(arr, arr + 5)` 这种"把数组本身当迭代器"的调用正确工作。
- `distance(R&& r)`：¶4 若 `R` 建模 `sized_range`，返回 `static_cast<range_difference_t<R>>(ranges::size(r))`；否则 `ranges::distance(ranges::begin(r), ranges::end(r))`。

与 `std::distance` 不同，第二个重载对 sized 哨位**没有"可达"前条件**——只要减法有定义即可，结果可以为负。

### `ranges::next`、`ranges::prev`（[range.iter.op.next]、[range.iter.op.prev]）

`next(x)`：`++x; return x;`；`next(x, n)`、`next(x, bound)`、`next(x, n, bound)`：对 `x` 调用对应的 `ranges::advance` 后返回。`prev(x)`、`prev(x, n)`、`prev(x, n, bound)`：要求 `bidirectional_iterator`，对应 `--x` 或 `ranges::advance(x, -n[, bound])`；带上限的 `prev` 的 `bound` 类型就是 `I`。

注意 `ranges::next(x, n, bound)` 返回迭代器而**丢弃**了"剩余步数"；需要它时直接用 `ranges::advance`。

## 例子

```cpp run title="primitives.cpp" ok
#include <cassert>
#include <iterator>
#include <list>
#include <ranges>

int main() {
    int a[5]{};
    int* p = a;
    // 带上限前进：想走 10 步，只走了 5 步，返回未走完的 5
    auto left = std::ranges::advance(p, 10, a + 5);
    assert(p == a + 5 && left == 5);

    assert(std::ranges::next(a, 3, a + 5) == a + 3);
    assert(std::ranges::distance(a) == 5);          // 范围重载：sized_range
    assert(std::ranges::distance(a, a + 5) == 5);   // 数组实参退化为指针
    assert(std::distance(a + 5, a) == -5);          // 随机访问：允许"反向可达"

    std::list<int> l{1, 2, 3, 4};
    auto it = std::ranges::next(l.begin(), 2);      // 双向迭代器：2 次 ++
    assert(*it == 3);
    assert(*std::ranges::prev(l.end()) == 4);

    // C++20 迭代器 + ranges::prev：按概念分派，正常工作
    auto io = std::views::iota(0, 10);
    assert(*std::ranges::prev(io.end()) == 9);
}
```

## 常见误区

!!! pitfall "`std::prev(it, -n)` 不能用于前向迭代器"
    `prev` 的模板参数要求双向迭代器，与 `n` 的符号无关。同理 `std::advance(it, -1)` 对前向迭代器违反前条件——libc++ 在调试模式下会断言。

!!! pitfall "对非随机访问迭代器传反首尾"
    `std::distance(l.end(), l.begin())` 对 `list` 是 UB（前条件只对随机访问迭代器放宽），实际表现是在链表中无限地 `++`，越过哨兵节点。`ranges::distance` 对非 sized 情形同样要求 `[first, last)` 是范围。

!!! pitfall "取算法函数对象的地址、或对其显式指定模板实参"
    `std::ranges::next<int*>(p)` 非良构：`ranges::next` 是对象，不是函数模板。好处是它们可以直接作为可调用对象传递（`std::views::transform(its, std::ranges::next)`），这对 `std::next` 是做不到的（重载集无法直接传递）。

## 思考题

!!! question "思考题"
    1. `ranges::advance(i, bound)` 的第 1 分支为什么用 `std::move(bound)`？`bound` 是按值传入的吗？
    2. `ranges::distance` 的第二个重载为什么要求 `sized_sentinel_for<S, decay_t<I>>`，而不是 `sized_sentinel_for<S, I>`？
    3. 若 `S` 是 sized 哨位，`ranges::advance(i, n, bound)` 是否需要执行任何 `++`？

<details markdown="1">
<summary>展开查看答案与解析</summary>

1. 是，`advance(I& i, S bound)` 按值接受哨位，所以可以安全地把它移走——哨位可能持有资源（例如一个 `std::function` 谓词），移动比复制便宜。
2. `I` 被推导为转发引用的类型，可能是 `int(&)[5]` 或 `It&`；概念需要的是"迭代器类型"，所以要 `decay_t`——对数组则退化为指针类型，正与 ¶3 中的 `static_cast<decay_t<I>>` 对应。
3. 不需要：它先算 `bound - i`，然后要么 `ranges::advance(i, bound)`（可能是一次赋值或一次 `+=`），要么 `ranges::advance(i, n)`（随机访问时一次 `+=`）。只有当 `I` 不是随机访问迭代器、却有 sized 哨位时（例如 `counted_iterator<list::iterator>` 配 `default_sentinel`），后者才会退化为逐步 `++`。
</details>

## 小结

!!! summary
    - 六个类别标签构成继承链（output 独立），用于 C++98 式标签分派；`contiguous_iterator_tag` 主要见于 `iterator_concept`。
    - `std::advance/distance/next/prev`：按 `iterator_category` 分派；负步长仅限双向；随机访问时 `distance` 可为负。
    - `ranges::advance` 三个重载：计数、哨位（可赋值/可相减时一步到位）、计数+哨位（返回剩余步数）。
    - `ranges::distance` 对 sized 哨位直接相减，对数组先退化，对 sized range 用 `ranges::size`。
    - `ranges::` 版本是算法函数对象：不被 ADL 找到，并抑制 ADL；可作为对象传递，不能显式指定模板实参。
