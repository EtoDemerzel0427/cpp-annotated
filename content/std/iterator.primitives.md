---
title: 迭代器原语
summary: 迭代器类别标签与标签分派，std::advance、distance、next、prev，以及按概念分派、支持哨位的 ranges:: 版本。
status: done
covers: *
since: c++98
papers: P0896R4
related: iterator.requirements, iterator.concepts, iterator.cpp17, iterator.assoc.types, alg.func.obj, customization.point.object, basic.lookup.argdep, expr.add
tags: 标准库, 迭代器, advance, distance, 标签分派, 算法函数对象
updated: 2026-10-19
---

!!! tldr
    - 六个类别标签组成一条继承链（`output_iterator_tag` 单独一个），C++98 靠它们和重载决议在编译期选择算法的实现。
    - `std::advance`、`distance`、`next`、`prev` 按 `iterator_category` 分派：负步长只能用于双向迭代器；随机访问迭代器的 `distance` 可以返回负数。
    - `ranges::advance` 有三种形式：走 `n` 步、走到哨位、最多走 `n` 步但不越过哨位，最后一种返回没走完的步数。
    - `ranges::` 版本是算法函数对象：ADL 找不到它们，它们被找到时还会关闭 ADL，也不能显式指定模板实参。

`std::list` 的迭代器没有 `+`，`std::forward_list` 的迭代器没有 `--`。[[iterator.requirements.general#14]] 规定每类迭代器只提供能在常数时间完成的操作。可是算法常常要走 `n` 步或者算两个迭代器的距离，这一节提供的工具会按迭代器的能力选择最快的做法。

¶1 [iterator.primitives.general] 只有一句话：为了方便使用迭代器，库提供了若干类和函数。

## 类别标签 [std.iterator.tags]

```cpp
struct output_iterator_tag { };
struct input_iterator_tag { };
struct forward_iterator_tag : public input_iterator_tag { };
struct bidirectional_iterator_tag : public forward_iterator_tag { };
struct random_access_iterator_tag : public bidirectional_iterator_tag { };
struct contiguous_iterator_tag : public random_access_iterator_tag { };
```

¶1 函数模板常常需要知道迭代器实参最具体属于哪一类，以便在编译期选出最高效的算法。为此库提供了这些空类，叫做**类别标签**（[[g:iterator-category-tag]]）。每个迭代器类型 `I` 的 `iterator_traits<I>::iterator_category` 必须是描述它行为的标签；另外还可以用 `iterator_traits<I>::iterator_concept` 表明它符合哪个 C++20 概念（[[iterator.concepts]]）。

¶3 例 2 展示了怎样用它们分派，这种写法叫**标签分派**（tag dispatch）：

```cpp
template<class BidirectionalIterator>
void evolve(BidirectionalIterator first, BidirectionalIterator last) {
  evolve(first, last,
         typename iterator_traits<BidirectionalIterator>::iterator_category());
}
template<class BidirectionalIterator>
void evolve(BidirectionalIterator first, BidirectionalIterator last,
            bidirectional_iterator_tag);   // 通用但较慢
template<class RandomAccessIterator>
void evolve(RandomAccessIterator first, RandomAccessIterator last,
            random_access_iterator_tag);   // 更快但要求更多
```

继承链在这里起作用。以 `random_access_iterator_tag` 调用时，精确匹配的重载胜出；以 `contiguous_iterator_tag` 调用时，派生类到基类的转换中，转换到更近的基类更好（[[over.ics.rank]]），还是选中随机访问版本；以 `forward_iterator_tag` 调用则两个都不可行。`output_iterator_tag` 不在链上，因为输出和输入是两种互不包含的能力。

¶2 例 1 展示了 C++98 式的申报方法：为自己的 `BinaryTreeIterator<T>` 特化 `iterator_traits`，把 `iterator_category` 定为 `bidirectional_iterator_tag`。

C++20 之后，同样的分派更常写成 `if constexpr (std::random_access_iterator<I>)` 或带约束的重载，概念之间的包含关系（[[temp.constr.order]]）取代了标签之间的继承关系。`contiguous_iterator_tag` 是 C++20 才加入的，指针的 `iterator_category` 仍是 `random_access_iterator_tag`（[[iterator.traits]]），这个标签主要出现在 `iterator_concept` 里。

## `std::advance`、`distance`、`next`、`prev` [iterator.operations]

¶1 只有随机访问迭代器提供 `+` 和 `-`，所以库提供 `advance` 和 `distance`：对随机访问迭代器用 `+`、`-`，常数时间；对其他迭代器反复 `++`，线性时间。四个函数都是 `constexpr`。

`advance(i, n)` 按引用修改 `i`，返回 `void`；步数的类型 `Distance` 是单独的模板参数。¶2 前提是只有双向迭代器才能传负的 `n`。¶3 `n` 非负时递增 `n` 次，否则递减 `-n` 次。

`distance(first, last)` 的前提值得注意：

!!! std
    *Preconditions*: last is reachable from first, or InputIterator meets the *Cpp17RandomAccessIterator* requirements and first is reachable from last.

¶4–¶5 随机访问迭代器返回 `last - first`，所以首尾传反了也可以，结果是负数。其他迭代器从 `first` 一路递增直到等于 `last`，返回递增的次数；这时传反首尾是未定义行为。

¶6 `next(x, n)` 等价于 `advance(x, n); return x;`。¶7 `prev(x, n)` 等价于 `advance(x, -n); return x;`。`prev` 的模板参数名是 `BidirectionalIterator`，即使 `n` 是负数、实际在往前走，也要求双向迭代器。

这四个函数按 *Cpp17* 要求和 `iterator_category` 工作。很多 C++20 视图的迭代器在这里只申报为输入迭代器，`std::distance` 只能逐个数，`std::prev` 则直接违反前提，见 [[iterator.cpp17]] 中的例子。

## `ranges::` 版本 [range.iter.ops]

```cpp run title="primitives.cpp" ok
#include <cassert>
#include <iterator>
#include <list>
#include <ranges>

int main() {
    int a[5]{};
    int* p = a;
    // 想走 10 步，只走了 5 步，返回没走完的 5
    auto left = std::ranges::advance(p, 10, a + 5);
    assert(p == a + 5 && left == 5);

    assert(std::ranges::next(a, 3, a + 5) == a + 3);
    assert(std::ranges::distance(a) == 5);          // 范围形式：sized_range
    assert(std::ranges::distance(a, a + 5) == 5);   // 数组实参退化为指针
    assert(std::distance(a + 5, a) == -5);          // 随机访问：可以反过来

    std::list<int> l{1, 2, 3, 4};
    auto it = std::ranges::next(l.begin(), 2);      // 双向迭代器：2 次 ++
    assert(*it == 3);
    assert(*std::ranges::prev(l.end()) == 4);

    // C++20 视图的迭代器：按概念分派，正常工作
    auto io = std::views::iota(0, 10);
    assert(*std::ranges::prev(io.end()) == 9);
}
```

¶1 [range.iter.ops.general] 说明，这四个函数根据迭代器实际提供的运算符选择最高效的实现。例 1：`ranges::advance` 对 `random_access_iterator` 用 `+` 在常数时间内前进，对其他迭代器执行 `n` 次 `++`。和 `std::` 版本相比，它们按 C++20 概念判断类别，并且支持哨位。

### `ranges::advance` [range.iter.op.advance]

`advance(i, n)` 走 `n` 步。¶1 前提是 `I` 不是双向迭代器时 `n` 不能为负。¶2 随机访问时等价于 `i += n`，否则逐步递增或递减。

`advance(i, bound)` 走到哨位。¶4 按顺序选择：

1. `I` 可以从 `S` 赋值时，直接 `i = std::move(bound)`；
2. 否则，`S` 是 `I` 的 sized 哨位时，执行 `ranges::advance(i, bound - i)`；
3. 否则逐个 `++`，直到 `i == bound`。

¶3 前提是：上面前两种情形之一成立，或者 `[i, bound)` 是一个范围。前两种情形下一次赋值或一次减法就能把 `i` 放到正确位置，这依赖 [[iterator.concept.sentinel]] 和 [[iterator.concept.sizedsentinel]] 的语义要求。

`advance(i, n, bound)` 最多走 `n` 步，到达 `bound` 就停，返回没走完的步数：

- ¶5 前提：`n > 0` 时 `[i, bound)` 是范围；`n == 0` 时 `[i, bound)` 或 `[bound, i)` 是范围；`n < 0` 时 `[bound, i)` 是范围，`I` 是双向迭代器，并且 `S` 与 `I` 是同一类型。
- ¶6 效果：如果 `S` 是 sized 哨位，`|n| >= |bound - i|` 时直接走到 `bound`，否则走 `n` 步；不是 sized 哨位时逐步前进或后退，最多 `|n|` 步，遇到 `bound` 就停。
- ¶7 返回 `n - M`，`M` 是 `i` 实际移动的有符号距离。

这是安全地最多走 `n` 步的标准工具。`views::drop` 的 `begin()` 就规定为 `ranges::next(ranges::begin(base_), count_, ranges::end(base_))`（[[range.drop.view]]）。

### `ranges::distance` [range.iter.op.distance]

有三个重载：

- `distance(I first, S last)`，用于 `S` 不是 sized 哨位的情形。¶1 前提是 `[first, last)` 是范围；¶2 逐个递增计数。
- `distance(I&& first, S last)`，用于 `S` 是 `decay_t<I>` 的 sized 哨位的情形。¶3 直接返回 `last - first`；如果 `first` 是数组，先转换为指针。转发引用加上这个特殊处理，让 `ranges::distance(arr, arr + 5)` 这种把数组本身当迭代器的调用也能工作。
- `distance(R&& r)`。¶4 如果 `R` 是 `sized_range`，返回 `ranges::size(r)`，转换为差值类型；否则返回 `ranges::distance(ranges::begin(r), ranges::end(r))`。

第二个重载没有可达性前提，只要减法有定义，结果可以是负数。

### `ranges::next`、`ranges::prev` [range.iter.op.next] [range.iter.op.prev]

`next(x)` 是 `++x; return x;`。`next(x, n)`、`next(x, bound)`、`next(x, n, bound)` 对 `x` 调用对应的 `ranges::advance` 后返回 `x`。

`prev(x)`、`prev(x, n)`、`prev(x, n, bound)` 要求 `bidirectional_iterator`，分别是 `--x` 和 `ranges::advance(x, -n)`、`ranges::advance(x, -n, bound)`；带上限的 `prev` 中 `bound` 的类型就是 `I`。

`ranges::next(x, n, bound)` 只返回迭代器，丢掉了没走完的步数；需要这个数时直接用 `ranges::advance`。

## 算法函数对象

¶2 [range.iter.ops.general] 的第 2 段很短，影响却很大：

!!! std
    The entities defined in [range.iter.ops] are algorithm function objects ([alg.func.obj]).

**算法函数对象**（algorithm function object）是一种定制点对象（[[customization.point.object]]）：标准按一组重载的函数模板来描述它，但它实际上是一个对象。[[alg.func.obj]] 的注 1 指出两个后果：

- 实参依赖查找（ADL，[[basic.lookup.argdep]]）找不到它们；
- 普通的非限定查找找到它们、并用作函数调用时，ADL 不会进行，因为 ADL 只在普通查找找到的是函数或者什么也没找到时才进行。

社区常把这种对象叫做 niebloid。效果如下：

```cpp run title="niebloid.cpp" ok
#include <cassert>
#include <iterator>
#include <vector>

namespace user {
struct Widget { int v; };
template<class It> It next(It it) { return it; }   // 什么都能接的同名模板
}

int main() {
    std::vector<user::Widget> v(3);
    using namespace std::ranges;
    // 非限定查找找到对象 std::ranges::next，不进行 ADL，user::next 不参与
    auto it = next(v.begin());
    assert(it == v.begin() + 1);
}
```

去掉 `using namespace std::ranges;` 再写 `next(v.begin())`，ADL 会在 `std`（`vector` 迭代器的关联命名空间）和 `user`（模板实参 `Widget` 的关联命名空间）里同时找到 `std::next` 和 `user::next`。两者对这个实参都是精确匹配，偏序也分不出高下，本机 Clang 23 报告 call to 'next' is ambiguous。算法函数对象从根上避免了这类问题。

因为它们是对象，所以可以直接当作可调用对象传递，例如传给 `views::transform`；`std::next` 是一个重载集，做不到这一点。反过来，`std::ranges::next<int*>(p)` 是非良构的，对象不能带模板实参。

!!! impl "libc++ 的实现"
    libc++ 把 `ranges::advance` 定义为结构体 `ranges::__advance` 的 `inline constexpr` 对象，放在内联命名空间 `__cpo` 里；标准里的各个函数模板对应结构体的各个 `operator()` 重载。对象不会被 ADL 找到是语言规则的直接结果，不需要额外的技巧。

## 常见误解

!!! pitfall "`std::prev` 或负步长的 `std::advance` 用于前向迭代器"
    `prev` 的模板参数要求双向迭代器，与 `n` 的正负无关；`std::advance(it, -1)` 对前向迭代器违反前提。本机 libc++ 在开启加固模式（例如 `-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_DEBUG`）时，对 `forward_list` 迭代器执行 `std::advance(it, -1)` 会报告断言失败并终止。

!!! pitfall "对非随机访问迭代器传反首尾"
    `std::distance(l.end(), l.begin())` 对 `std::list` 是未定义行为，前提只对随机访问迭代器放宽。本机 libc++ 的链表是环形的，这个调用安静地返回了 1，没有任何提示。`ranges::distance` 在非 sized 情形下同样要求 `[first, last)` 是范围。

## 思考题

!!! question "思考题 1"
    `ranges::advance(i, bound)` 的第一种情形写的是 `i = std::move(bound)`。为什么可以移走 `bound`？

<details markdown="1">
<summary>答案</summary>

这个重载的签名是 `advance(I& i, S bound)`，哨位按值传入，函数里的 `bound` 是自己的副本，移走它不影响调用者。哨位可能持有资源，比如一个谓词对象，移动比复制便宜。
</details>

!!! question "思考题 2"
    `ranges::distance` 的第二个重载为什么写 `sized_sentinel_for<S, decay_t<I>>`，而不是 `sized_sentinel_for<S, I>`？

<details markdown="1">
<summary>答案</summary>

`first` 是转发引用，`I` 推导出来可能是 `It&`，传数组时可能是 `int(&)[5]`。概念需要的是迭代器类型本身，所以要 `decay_t`；对数组，`decay_t` 正好得到指针类型，与 ¶3 中的 `static_cast<decay_t<I>>(first)` 相对应。
</details>

!!! question "思考题 3"
    `S` 是 sized 哨位时，`ranges::advance(i, n, bound)` 还会不会执行逐个的 `++`？

<details markdown="1">
<summary>答案</summary>

可能会。它先用 `bound - i` 决定走多远，然后调用 `ranges::advance(i, bound)` 或 `ranges::advance(i, n)`。如果 `I` 是随机访问迭代器，后者是一次 `+=`；但 sized 哨位并不要求迭代器是随机访问的，例如 `counted_iterator<std::list<int>::iterator>` 配 `default_sentinel_t`，这时 `ranges::advance(i, n)` 仍然逐个 `++`。不过越界判断只需一次减法，不必每步都和 `bound` 比较。
</details>
