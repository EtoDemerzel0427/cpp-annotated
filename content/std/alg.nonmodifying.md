---
title: 不修改序列的操作
summary: 只读元素的算法：all_of 等量词、contains、for_each、find 系列、count、mismatch 与 equal、is_permutation、search 系列、starts_with 与 ends_with、fold 系列。重点是空区间的结果、谓词调用次数的承诺、三迭代器 equal 的越界风险，以及 fold_left 与 accumulate 的类型差异。
status: done
covers: *
papers: P0896R4, P2322R6, P2302R4, P1223R5, P1659R3, P2248R8
related: algorithms.requirements, algorithms.results, alg.req, alg.modifying.operations, numeric.ops, func.search
tags: 标准库, 算法, find, equal, search, fold
updated: 2026-10-19
---

!!! tldr
    - 这些算法只读元素、调用谓词，按 [[algorithms.requirements#3]] 也不得写入元素，多个线程可以同时对同一个序列调用它们。
    - 复杂度条款是承诺：`find` 至多调用 N 次谓词，找到就停；`count` 恰好调用 N 次。
    - `std::equal(first1, last1, first2)` 假定第二个序列至少一样长，更短时越界读取，是未定义行为。用四个迭代器或 `ranges::equal`。
    - 空区间上，`all_of` 和 `none_of` 返回 `true`，`any_of` 返回 `false`；空模式串上，`search` 返回 `first1`，`find_end` 返回 `last1`。
    - `ranges::fold_left` 的结果类型由二元运算的返回类型决定；`std::accumulate` 的累加器类型就是初值的类型，用 `0` 累加 `double` 会截断。

## 条文的统一写法

每个子条款开头都用 "Let *E* be" 定义一个条件，让各个版本共用一段描述。以 [alg.find] ¶1 为例：

| 版本 | *E* |
|---|---|
| `std::find` | `*i == value` |
| `std::find_if` | `pred(*i) != false` |
| `ranges::find` | `bool(invoke(proj, *i) == value)` |
| `ranges::find_if` | `bool(invoke(pred, invoke(proj, *i)))` |

规律是：经典版本直接写 `*i == value` 或 `pred(*i)`；`ranges` 版本先对元素调用投影，再用 `invoke` 调用谓词，外面通常套一层 `bool(...)`。下文不再逐个重复。

## 量词：`all_of`、`any_of`、`none_of`

[alg.all.of]、[alg.any.of]、[alg.none.of] 的 ¶2 用 *Returns* 的措辞决定了空区间的结果：

- `all_of`：对某个 `i` 有 *E* 为假时返回 `false`，否则返回 `true`。空区间返回 `true`。
- `any_of`：对某个 `i` 有 *E* 为真时返回 `true`，否则返回 `false`。空区间返回 `false`。
- `none_of`：对某个 `i` 有 *E* 为真时返回 `false`，否则返回 `true`。空区间返回 `true`。

¶3 三者都至多调用 `last - first` 次谓词和投影，结果确定后就停止。

### `ranges::contains` 与 `contains_subrange` {{c++23}}

[alg.contains] 只有 `ranges` 版本（[[P2302R4]]）。¶1 `contains` 返回 `ranges::find(std::move(first), last, value, proj) != last`。¶3 `contains_subrange` 返回 `first2 == last2 || !ranges::search(...).empty()`，所以空的子序列总是被包含。C++26 起两者都有并行重载（¶2、¶4）。

## `for_each` 与 `for_each_n` [alg.foreach]

`for_each` 是少数会把函数对象还给调用方的算法。非并行的 `std::for_each` 规定如下：

- ¶1 `Function` 满足 *Cpp17MoveConstructible*。注 1 特意说明它不必可复制，所以可以传捕获了 `std::unique_ptr` 的 lambda；
- ¶2 从 `first` 到 `last - 1` 依次对每个元素应用 `f`。注 2：迭代器可写时，`f` 可以通过解引用的结果修改元素；
- ¶3 返回 `f`，可以用来带回累积的状态；¶5 `f` 的返回值被忽略。

[[algorithms.requirements]] 说算法可以随意复制函数对象，¶3 是一个明确的例外。

其他版本的差别：

| 版本 | 段落 | 对 `f` 的要求 | 返回 | 顺序 |
|---|---|---|---|---|
| `std::for_each` | ¶1–¶5 | 可移动构造 | `f` | 依次 |
| 并行 `std::for_each` | ¶6–¶10 | 可复制构造 | `void` | 不保证 |
| `ranges::for_each` | ¶11–¶15 | 建模 `copy_constructible`（注 6） | `{last, std::move(f)}` | 依次 |
| 并行 `ranges::for_each` {{c++26}} | ¶16–¶19 | 同上 | `last` | 不保证 |

并行版本不返回函数对象，注 4 给出的理由是并行化通常无法高效地累积状态。它们的 *Remarks* 还规定，实现不能像其他并行算法那样复制元素（[[algorithms.parallel.exec#3]]），`f` 也可以通过实参修改对象（¶19.3）。

`for_each_n`（¶20–¶38）对 `[first, first + n)` 做同样的事。¶20 要求 `Size` 能转换为整数类型，¶21 要求 `n >= 0`。¶23 它返回 `first + n` 而不是函数对象；`ranges::for_each_n` 两者都返回（¶32）。

## 查找

### `find`、`find_if`、`find_if_not` [alg.find]

¶2 返回第一个使 *E* 为真的迭代器，找不到时返回 `last`。¶3 至多调用 `last - first` 次谓词。

`find` 的值形参 `T` 有一个默认模板实参：

```cpp
template<class InputIterator, class T = iterator_traits<InputIterator>::value_type>
  constexpr InputIterator find(InputIterator first, InputIterator last, const T& value);
```

这来自 C++26 的 [[P2248R8]]。实参是花括号列表时，`T` 无法从中推导，有了默认实参就退回到元素的值类型。于是对 `std::vector<std::pair<int, int>> v`，可以写 `std::find(v.begin(), v.end(), {3, 4})`。`ranges` 版本的默认实参是 `projected_value_t<I, Proj>`。`count`、`replace`、`fill`、`remove`、`search_n`、`lower_bound` 等接受值的算法都加了同样的默认实参。

!!! impl "libc++ 尚未实现 P2248"
    本机 Clang 23 + libc++ 上，`std::find(v.begin(), v.end(), {3, 4})` 和 `std::ranges::find(v, {3, 4})` 都报 couldn't infer template argument '_Tp'。

### `ranges::find_last` 系列 {{c++23}}

[alg.find.last] 由 [[P1223R5]] 引入，有 `find_last`、`find_last_if`、`find_last_if_not` 三个。¶2 返回 `{i, last}`，`i` 是最后一个使 *E* 为真的迭代器；找不到时返回 `{last, last}`。

它返回 `subrange` 而不是一个迭代器：为了找最后一个匹配，算法必须走到终点，既然已经算出了终点对应的迭代器，就一并返回（见 [[algorithms.results]]）。它要求 `forward_iterator`：算法要记住目前为止最后一个匹配的位置再继续往前走，只能遍历一趟的输入迭代器做不到。

### `find_end` 与 `find_first_of`

[alg.find.end] 的 `find_end` 在 `[first1, last1)` 中查找子序列 `[first2, last2)` 最后一次出现的位置，名字容易误解，它其实是查找最后一次出现。¶1.3 子序列为空、比主序列长或者找不到时，结果是 `last1`。`ranges` 版本返回 `subrange`。

[alg.find.first.of] 的 `find_first_of` 返回 `[first1, last1)` 中第一个与 `[first2, last2)` 中任一元素匹配的位置，相当于 C 的 `strpbrk`。第一个序列可以是输入迭代器，第二个必须是前向迭代器，因为对每个元素都要从头扫描第二个序列。¶4 至多比较 `(last1 - first1) * (last2 - first2)` 次。

### `adjacent_find` [alg.adjacent.find]

¶2 返回第一个使 `*i == *(i + 1)`（或 `pred(*i, *(i + 1))`）成立的 `i`，找不到时返回 `last`。

¶3 的复杂度写得很精确：非并行版本恰好调用 `min((i - first) + 1, (last - first) - 1)` 次谓词，`i` 是返回值。实现不能多比较一次。投影的调用次数不超过谓词的两倍，因为每次比较要对两个元素调用投影，标准不要求实现缓存投影结果。

## `count` 与 `count_if` [alg.count]

¶2 返回使 *E* 成立的迭代器个数。¶3 恰好调用 `last - first` 次谓词：与 `find` 不同，`count` 不能提前结束。返回类型是迭代器的差类型，经典版是 `iterator_traits<I>::difference_type`，`ranges` 版是 `iter_difference_t<I>`，不是 `size_t`。

## `mismatch` 与 `equal`

```cpp run title="equal3.cpp" flags="-std=c++2c -O0 -fsanitize=address" ub
#include <algorithm>
#include <cstdio>
#include <vector>

int main() {
  std::vector<int> a{1, 2, 3, 4};
  std::vector<int> b{1, 2};
  bool e = std::equal(a.begin(), a.end(), b.begin());  // UB：假定 b 至少有 4 个元素
  std::printf("%d\n", e);
}
```

本机以 `-fsanitize=address` 运行，报告 heap-buffer-overflow。

两个算法都有三迭代器和四迭代器两种经典形式。只给出 `first2` 时，[alg.equal] ¶1.1 和 [alg.mismatch] ¶1 令 `last2` 为 `first2 + (last1 - first1)`，也就是假定第二个序列至少和第一个一样长。第二个序列更短时，`[first2, last2)` 不是有效区间，算法会读到它的末尾之后。

C++14 加入了四迭代器形式：

- [alg.mismatch] ¶3 取 `N = min(last1 - first1, last2 - first2)`，只比较较短的长度。¶4 返回第一对不匹配的迭代器，经典版是 `pair`，`ranges` 版是 `mismatch_result`；
- [alg.equal] ¶2 先比较长度，不相等就返回 `false`。

`ranges::equal` 和 `ranges::mismatch` 只有四迭代器（或两个范围）的形式。上面的例子改成 `std::equal(a.begin(), a.end(), b.begin(), b.end())` 或 `std::ranges::equal(a, b)` 即可。

[alg.equal] ¶3 的复杂度同时是优化许可和承诺：两个序列的长度能在常数时间求出（经典版要求 *Cpp17RandomAccessIterator*，`ranges` 版要求 `sized_sentinel_for` 或 `sized_range`）而且不相等时，一次谓词都不调用；否则至多调用 `min(N1, N2)` 次。

## `is_permutation` [alg.is.permutation]

¶4 判断第二个序列能否重排成与第一个序列相等。¶2 要求两个迭代器的值类型相同。¶3 要求比较函数是**等价关系**：自反、对称、传递。这比严格弱序弱，但仍是语义要求，编译器检查不了，违反了是{{ub}}。

¶5 的复杂度：长度能在常数时间判断且不相等时，不调用谓词；两个序列逐个相等时，恰好调用 N 次；否则最坏 O(N²)。算法只能判断相等，不能比较大小，所以无法先排序再线性比较，平方复杂度由此而来。需要更快时，自己排序后用 `equal`，或者用哈希表计数。

## 子序列查找

### `search` 与 `search_n` [alg.search]

¶1 `search` 查找子序列第一次出现的位置。子序列为空时返回 `first1`，与 `find_end` 返回 `last1` 正好相反；找不到时返回 `last1`。¶2 至多比较 `(last1 - first1) * (last2 - first2)` 次，这是朴素算法的上界。¶3 `ranges` 版本返回 `subrange{i, i + (last2 - first2)}`。

¶5–¶10 `search_n` 查找连续 `count` 个等于 `value` 的元素。¶5 要求 `Size` 能转换为整数类型，¶8 至多比较 `last - first` 次。

¶11 C++17 加入了接受搜索器的重载：`search(first, last, searcher)` 等价于 `return searcher(first, last).first;`。配合 `<functional>` 中的 `boyer_moore_searcher`、`boyer_moore_horspool_searcher`（[[func.search]]），长模式串的查找可以快得多。¶12 `Searcher` 不必可复制构造，因为搜索器可能持有很大的预处理表。

### `starts_with` 与 `ends_with` {{c++23}}

两者只有 `ranges` 版本（[[P1659R3]]）。

[alg.starts.with] ¶1 `starts_with` 返回 `ranges::mismatch(...).in2 == last2`，即第二个序列被完整匹配。

[alg.ends.with] ¶1–¶2 `ends_with` 先求两个序列的长度 N1、N2。N1 < N2 时返回 `false`，否则对第一个序列的最后 N2 个元素调用 `ranges::equal`。因为要先知道长度，迭代器版本对每个序列要求 `forward_iterator` 或者 `sized_sentinel_for`：要么能在常数时间求出长度，要么能先数一遍再回头。¶6 范围版本用 `views::drop` 跳过前 N1 − N2 个元素。

## fold 系列 [alg.fold] {{c++23}}

```cpp run title="fold.cpp" ok
#include <algorithm>
#include <cassert>
#include <functional>
#include <numeric>
#include <type_traits>
#include <vector>

int main() {
  std::vector<double> v{0.5, 0.5, 0.5};
  auto a = std::accumulate(v.begin(), v.end(), 0);       // 累加器是 int
  auto f = std::ranges::fold_left(v, 0, std::plus<>());  // 结果类型由 plus 决定
  static_assert(std::is_same_v<decltype(a), int>);
  static_assert(std::is_same_v<decltype(f), double>);
  assert(a == 0 && f == 1.5);

  std::vector<int> w{1, 2, 3};
  auto l = std::ranges::fold_left(w, 0, std::minus<>());   // ((0-1)-2)-3
  auto r = std::ranges::fold_right(w, 0, std::minus<>());  // 1-(2-(3-0))
  assert(l == -6 && r == 2);

  std::vector<int> empty;
  auto e = std::ranges::fold_left_first(empty, std::plus<>());
  assert(!e);   // 空范围：空的 optional
}
```

`std::accumulate` 的累加器类型就是初值的类型。初值写成 `0`，累加器就是 `int`，每一步的 `double` 结果都被截断，最后得到 0。

C++23 的 [[P2322R6]] 为范围提供了 `accumulate` 的替代品。¶6 规定 `fold_left_with_iter` 的累加类型 `U` 是 `decay_t<invoke_result_t<F&, T, iter_reference_t<I>>>`，由二元运算的返回类型决定，而不是由初值的类型决定。`fold_left` 等其他函数都按它定义。

| 函数 | 计算 | 返回 |
|---|---|---|
| `fold_left(r, init, f)` | `f(f(f(init, x1), x2), x3)` | `U` |
| `fold_left_first(r, f)` | 以第一个元素为初值 | `optional<U>` |
| `fold_right(r, init, f)` | `f(x1, f(x2, f(x3, init)))` | `U` |
| `fold_right_last(r, f)` | 以最后一个元素为初值 | `optional<U>` |
| `fold_left_with_iter`、`fold_left_first_with_iter` | 同上，并返回终点迭代器 | `in_value_result` |

其他要点：

- `fold_right` 要求 `bidirectional_iterator`，¶3 的实现从 `last` 往回走；
- `fold_left` 和 `fold_right` 不返回迭代器，需要终点时用 `*_with_iter` 版本；
- 它们都没有投影形参，需要时先用 `views::transform`；
- 它们规定了严格的左结合或右结合，没有并行版本。需要并行归约时用 `std::reduce`（[[numeric.ops]]）。

## 思考题

!!! question "思考题 1"
    `std::find_if(first, last, pred) != last` 和 `std::count_if(first, last, pred) > 0` 有什么可以观察到的区别？

<details markdown="1">
<summary>答案</summary>

`find_if` 至多调用 N 次谓词，第一次命中就停；`count_if` 恰好调用 N 次，必须走完。谓词有副作用（比如写日志）或者代价很高时，两者不同。对输入迭代器，`find_if` 停下后，剩下的元素没有被读取。
</details>

!!! question "思考题 2"
    `std::is_permutation(a.begin(), a.end(), b.begin(), b.end(), [](double x, double y) { return std::abs(x - y) < 0.1; })` 有什么问题？

<details markdown="1">
<summary>答案</summary>

差小于 0.1 不满足传递性：0.0 与 0.08 接近，0.08 与 0.16 接近，但 0.0 与 0.16 不接近。所以它不是等价关系，违反了 [alg.is.permutation] ¶3 的前置条件，是未定义行为，结果可能取决于实现内部比较的顺序。
</details>

!!! question "思考题 3"
    为什么 `ranges::find_last` 要求 `forward_iterator`，而 `ranges::find` 只要求 `input_iterator`？

<details markdown="1">
<summary>答案</summary>

`find_last` 必须扫描到末尾才知道哪个是最后一个匹配，途中要保存当前的候选迭代器。对输入迭代器，原迭代器自增之后，保存的副本就失效了，因为它只能遍历一趟。所以至少需要能多趟遍历的前向迭代器。
</details>

## 小结

| 算法 | 承诺 | 注意 |
|---|---|---|
| `all_of`/`any_of`/`none_of` | 至多 N 次，可提前结束 | 空区间：`true`/`false`/`true` |
| `for_each` | 依次调用；返回 `f`；`f` 可以只能移动 | 并行版不返回 `f`、不保证顺序 |
| `find` 系列 | 至多 N 次；返回第一个 | C++26 支持花括号值实参，libc++ 尚未实现 |
| `find_last` | 返回 `subrange` | 需要前向迭代器 |
| `count` | 恰好 N 次 | 返回差类型 |
| 三迭代器 `mismatch`/`equal` | | 第二个序列更短时越界，UB |
| `is_permutation` | 最坏 O(N²) | 谓词必须是等价关系 |
| `search` / `find_end` | | 空模式串返回 `first1` / `last1` |
| `fold_left` | 结果类型由运算决定 | 没有投影，没有并行版 |
