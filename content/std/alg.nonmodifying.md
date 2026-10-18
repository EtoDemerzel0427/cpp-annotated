---
title: 不修改序列的操作
summary: all_of/any_of/none_of、contains、for_each、find 家族（含 find_last）、find_end、find_first_of、adjacent_find、count、mismatch、equal、is_permutation、search/search_n、starts_with/ends_with、fold 家族——逐个讲清“Let E be”统一表述、谓词调用次数的精确承诺、三实参 mismatch/equal 的越界 UB、空区间语义、fold_left 与 accumulate 的类型差异
status: done
covers: *
papers: P0896R4, P2322R6, P2302R4, P1223R5, P1659R3, P2248R8
related: algorithms.requirements, algorithms.results, alg.req, alg.modifying.operations, numeric.ops, func.search
tags: 标准库, 算法, find, equal, search, fold
updated: 2026-10-18
---

本节收录“只读”算法：它们通过迭代器**读**元素、调用谓词，但规范不要求修改任何元素——按 [[algorithms.requirements#3]]，它们也**不得**修改，因此多个线程可以同时对同一序列调用它们。

每个子条款都以同一套句式开头：“Let *E* be: `pred(*i)` for the overloads in namespace std; `invoke(pred, invoke(proj, *i))` for the overloads in namespace ranges.” 读者只需记住这条映射：**经典版直接调用 `pred(*i)`/`*i == value`，ranges 版先投影再 `invoke`，并且往往套一层 `bool(...)`**。下文不再一一重复。

## 量词：`all_of`、`any_of`、`none_of`（[alg.all.of]、[alg.any.of]、[alg.none.of]）

*Returns* 的措辞决定了空区间的语义：

- `all_of`：“若对某个 `i` E 为 false 则返回 false，否则 true”——空区间返回 **true**（空真）；
- `any_of`：“若对某个 `i` E 为 true 则返回 true，否则 false”——空区间返回 **false**；
- `none_of`：空区间返回 **true**。

*Complexity*：“至多 `last - first` 次”谓词与投影应用——命中即可短路。

## `ranges::contains` 与 `contains_subrange`（[alg.contains]）{{c++23}}

只有 ranges 版本（[[P2302R4]]）。¶1：`contains` 返回 `ranges::find(std::move(first), last, value, proj) != last`；¶3：`contains_subrange` 返回 `first2 == last2 || !ranges::search(...).empty()`——空的子序列总是“被包含”。C++26 起两者都有并行重载（¶2、¶4）。

## `for_each` 与 `for_each_n`（[alg.foreach]）

非并行的 `std::for_each`（¶1–¶5）：

- *Preconditions*：`Function` 满足 *Cpp17MoveConstructible*；注 1 特意说明**不需要**可复制——所以可以传入只可移动的函数对象（如捕获 `unique_ptr` 的 lambda）；
- *Effects*：从 `first` 到 `last - 1` **按顺序**应用 `f`；注 2：若迭代器可变，`f` 可以通过解引用结果调用非 const 函数（即可以修改元素）；
- *Returns*：`f`——这是“函数对象可随意复制”这一默认规则（[[algorithms.requirements#9]]）的显式例外，可用来带回累积状态；
- *Remarks*：`f` 的返回值被忽略。

并行版（¶6–¶10）改为要求 *Cpp17CopyConstructible*、**不保证顺序**、**返回 `void`**（注 4：并行化通常无法高效累积状态），并明确实现**没有**复制元素的自由（[[algorithms.parallel.exec#3]] 的例外）。

ranges 版（¶11–¶15）返回 `for_each_result<I, Fun>`，即 `{last, std::move(f)}`；注 6：ranges 重载要求 `Fun` model `copy_constructible`（来自 `indirectly_unary_invocable` 概念），这与经典版只需可移动不同。C++26 的并行 ranges 版（¶16–¶19）只返回迭代器，¶19.3 明确 `f` 可以经实参修改对象。

`for_each_n`（¶20–¶38）：*Mandates* `Size` 可转换为整数类型，*Preconditions* `n >= 0`，返回 `first + n`——它与 `for_each` 的区别是返回迭代器而非函数对象（ranges 版两者都返回）。

## 查找：`find`、`find_if`、`find_if_not`（[alg.find]）

¶1 的 E 表把六个版本统一起来：`*i == value`、`pred(*i) != false`、`pred(*i) == false`，以及 ranges 版的 `bool(invoke(proj, *i) == value)` 等。¶2：返回**第一个**使 E 为真的 `i`，找不到返回 `last`。¶3：至多 `last - first` 次。

注意概要中 `T` 有默认实参：

```cpp
template<class InputIterator, class T = iterator_traits<InputIterator>::value_type>
  constexpr InputIterator find(InputIterator first, InputIterator last, const T& value);
```

这是 C++26 的 [[P2248R8]]：当实参是花括号初始化列表时 `T` 无法推导，有了默认实参就能退回到值类型，于是 `std::find(v.begin(), v.end(), {3, 4})`（`v` 是 `vector<pair<int,int>>`）变得合法。ranges 版对应的默认是 `projected_value_t<I, Proj>`。同样的默认实参出现在 `count`、`replace`、`fill`、`remove`、`search_n`、`lower_bound`/`upper_bound`/`binary_search` 等接受“值”的算法上。

!!! impl "libc++ 尚未实现"
    截至 LLVM 23，libc++ 的 `std::find` 仍是 `template <class _InputIterator, class _Tp>`，上述花括号写法报 “couldn't infer template argument '_Tp'”。

### `ranges::find_last` 系列（[alg.find.last]）{{c++23}}

由 [[P1223R5]] 引入。¶2：返回 `{i, last}`，其中 `i` 是**最后一个**满足条件的迭代器；找不到返回 `{last, last}`。返回 `subrange` 而不是单个迭代器，是因为对前向迭代器，算法为了找“最后一个”必须走到 `last`——既然已经算出了 `last`（可能来自一个哨位），就一并返回（[[algorithms.results]] 的同一原则）。要求 `forward_iterator`：输入迭代器不能“回头”，自然无法记住最后一个匹配位置后再继续。

## `find_end` 与 `find_first_of`（[alg.find.end]、[alg.find.first.of]）

`find_end`（名字起得糟糕，实际是“search_last”）：在 `[first1, last1)` 中找子序列 `[first2, last2)` **最后一次**出现的位置。¶1.3：子序列为空或比主序列长时返回 `last1`。ranges 版返回 `subrange`。¶3 复杂度为 `(last2 - first2) * (last1 - first1 - (last2 - first2) + 1)` 次。

`find_first_of`：返回 `[first1, last1)` 中第一个与 `[first2, last2)` 中**任意**元素匹配的位置（相当于 `strpbrk`）。第一个序列可以是输入迭代器，第二个必须是前向迭代器——因为对每个 `*i` 都要从头扫描第二个序列。

## `adjacent_find`（[alg.adjacent.find]）

返回第一个使 `*i == *(i + 1)`（或 `pred(*i, *(i + 1))`）的 `i`。¶3 的复杂度写得异常精确：非并行版**恰好** `min((i - first) + 1, (last - first) - 1)` 次谓词应用。实现不能多比一次，也不能少——这排除了“先跳着比较再回头确认”的策略。投影次数“不超过两倍”，因为每次比较两个元素都要投影，而实现不必缓存投影结果。

## `count` 与 `count_if`（[alg.count]）

返回使 E 成立的迭代器数目。¶3：**恰好** `last - first` 次谓词应用——与 `find` 的“至多”不同，`count` 不能提前结束。返回类型是迭代器的差类型（经典版 `iterator_traits<I>::difference_type`，ranges 版 `iter_difference_t<I>`），不是 `size_t`。

## `mismatch` 与 `equal`：三实参形式的陷阱（[alg.mismatch]、[alg.equal]）

两者都有“三迭代器”和“四迭代器”两种形式：

- 三迭代器（只给 `first2`）：¶1 令 `last2 = first2 + (last1 - first1)`——即**假定**第二个序列至少和第一个一样长。这是一个隐含的前置条件：若第二个序列更短，就会越界读取，{{ub}}。
- 四迭代器（C++14 起）：`mismatch` 取 `N = min(last1 - first1, last2 - first2)`（¶3）；`equal` 先比长度，不等就返回 `false`（¶2）。

```cpp run title="equal3.cpp" flags="-std=c++2c -O0 -fsanitize=address" ub
#include <algorithm>
#include <cstdio>
#include <vector>

int main() {
    std::vector<int> a{1, 2, 3, 4};
    std::vector<int> b{1, 2};
    bool e = std::equal(a.begin(), a.end(), b.begin());   // UB：认为 b 至少有 4 个元素
    std::printf("%d\n", e);
}
```

本机以 `-fsanitize=address` 运行报 `heap-buffer-overflow`。改写为 `std::equal(a.begin(), a.end(), b.begin(), b.end())` 或 `std::ranges::equal(a, b)`（ranges 版**只有**四迭代器/双 range 形式）即可。

`equal` 的 ¶3 复杂度里藏着一个优化许可，也是一个承诺：若两个序列的长度能 O(1) 求得（*Cpp17RandomAccessIterator*，或 ranges 版 model `sized_sentinel_for`/`sized_range`）且不相等，则**零次**谓词调用；否则至多 `min(N1, N2)` 次。

`mismatch` 返回一对迭代器（经典版 `pair`，ranges 版 `mismatch_result` 即 `in_in_result`）。`starts_with`/`ends_with` 就是用它和 `equal` 定义的（见下）。

## `is_permutation`（[alg.is.permutation]）

¶2 *Mandates*：两个迭代器的值类型**相同**。¶3 *Preconditions*：比较函数是**等价关系**（自反、对称、传递）——这比严格弱序更弱，但仍是语义要求，违反为 {{ub}}。¶5 复杂度：长度可 O(1) 判断且不等则零次；若两序列逐元素相等则恰好 N 次；否则最坏 **O(N²)**。没有要求可比较大小，所以无法排序后线性比较——这就是平方复杂度的来源。需要更快的话自己排序后用 `equal`，或用哈希计数。

## `search` 与 `search_n`（[alg.search]）

`search` 找子序列**第一次**出现（¶1）；子序列为空时返回 `first1`（与 `find_end` 返回 `last1` 正好相反）。¶2：朴素实现的最坏复杂度 `(last1 - first1) * (last2 - first2)`。ranges 版返回 `subrange{i, i + (last2 - first2)}`（¶3）。

`search_n`（¶5–¶10）找连续 `count` 个等于 `value` 的元素。

¶11–¶12 是 C++17 的**搜索器重载**：`search(first, last, searcher)` 等价于 `return searcher(first, last).first;`，配合 `<functional>` 中的 `boyer_moore_searcher`、`boyer_moore_horspool_searcher`（[[func.search]]），在长模式串上可以达到亚线性。¶12：`Searcher` 不需要满足 *Cpp17CopyConstructible*（搜索器可能持有大表，不应被复制）。

## `starts_with` 与 `ends_with`（[alg.starts.with]、[alg.ends.with]）{{c++23}}

只有 ranges 版（[[P1659R3]]）：

- `starts_with` = `ranges::mismatch(...).in2 == last2`——第二个序列被完全匹配；
- `ends_with`：令 N1、N2 为两序列长度，N1 < N2 时返回 `false`，否则对第一个序列的末尾 N2 个元素调用 `ranges::equal`。因为要先知道两个长度，迭代器+哨位版对每个序列要求“`forward_iterator` **或** `sized_sentinel_for`”——要么能 O(1) 求长度，要么能先数一遍再回头；range 版用 `views::drop` 跳过前 N1−N2 个元素（¶6）。

## fold 家族（[alg.fold]）{{c++23}}

C++23 的 [[P2322R6]] 为 ranges 引入了 `accumulate` 的正式替代：

| 函数 | 语义 | 返回 |
|---|---|---|
| `fold_left(r, init, f)` | `f(f(f(init, x1), x2), x3)` | `U` |
| `fold_left_first(r, f)` | 以首元素为初值 | `optional<U>` |
| `fold_right(r, init, f)` | `f(x1, f(x2, f(x3, init)))` | `U` |
| `fold_right_last(r, f)` | 以末元素为初值 | `optional<U>` |
| `fold_left_with_iter` / `fold_left_first_with_iter` | 同上，并返回终点迭代器 | `in_value_result` |

关键在 ¶6/¶3 中累加类型 `U` 的定义：`U = decay_t<invoke_result_t<F&, T, iter_reference_t<I>>>`——**由 `f` 的返回类型决定，而不是由 `init` 的类型决定**。对比 `std::accumulate`，其累加器类型就是 `init` 的类型 `T`，于是经典陷阱“用 `0` 累加 `double`”会悄悄截断：

```cpp run title="fold.cpp" ok
#include <algorithm>
#include <cassert>
#include <numeric>
#include <vector>

int main() {
    std::vector<double> v{0.5, 0.5, 0.5};
    auto a = std::accumulate(v.begin(), v.end(), 0);          // 累加器类型是 int！
    auto f = std::ranges::fold_left(v, 0, std::plus<>());     // 结果类型由 f 决定：double
    static_assert(std::is_same_v<decltype(a), int>);
    static_assert(std::is_same_v<decltype(f), double>);
    assert(a == 0 && f == 1.5);

    auto r = std::ranges::fold_right(std::vector{1, 2, 3}, 0, std::minus<>());  // 1-(2-(3-0)) = 2
    auto l = std::ranges::fold_left(std::vector{1, 2, 3}, 0, std::minus<>());   // ((0-1)-2)-3 = -6
    assert(r == 2 && l == -6);
    auto e = std::ranges::fold_left_first(std::vector<int>{}, std::plus<>());   // 空区间 → 空 optional
    assert(!e);
}
```

其他要点：

- `fold_right` 需要 `bidirectional_iterator`（¶3 的实现从 `last` 往回走）；
- `fold_left`/`fold_right` 不返回迭代器，`*_with_iter` 版本才返回——这是为了让最常用的形式直接返回值；
- 这些都**没有投影形参**，需要时用 `views::transform` 先变换；
- fold 是严格的左/右结合，**没有**并行版；需要并行归约用 `reduce`（[[numeric.ops]]）。

## 思考题

<details markdown="1">
<summary>1. `std::find_if(first, last, pred)` 和 `std::count_if(first, last, pred) > 0` 在可观察行为上有什么区别？</summary>

`find_if` “至多 N 次”谓词调用，第一次命中即停；`count_if` “恰好 N 次”，必须走完。若 `pred` 有可观察副作用（打日志）或很昂贵，两者不同。另外对输入迭代器，`find_if` 停下后剩余元素仍未被读取。
</details>

<details markdown="1">
<summary>2. `std::is_permutation(a.begin(), a.end(), b.begin(), b.end(), [](double x, double y){ return std::abs(x - y) < 0.1; })` 有什么问题？</summary>

“差小于 0.1”不是传递的（0.0≈0.08≈0.16 但 0.0 与 0.16 不“相等”），不是等价关系，违反 [alg.is.permutation] ¶3 的前置条件，{{ub}}——结果可能依赖于实现内部的比较顺序。
</details>

<details markdown="1">
<summary>3. 为什么 `ranges::find_last` 要求 `forward_iterator`，而 `ranges::find` 只要 `input_iterator`？</summary>

`find_last` 必须扫描到末尾才知道哪个是最后一个匹配，并在途中**保存**之前的候选迭代器；对输入迭代器，保存的副本在自增原迭代器后即失效（单趟），所以至少需要多趟保证的前向迭代器。
</details>

## 小结

| 算法 | 关键承诺 | 坑 |
|---|---|---|
| `all_of`/`any_of`/`none_of` | 至多 N 次，短路 | 空区间：true/false/true |
| `for_each` | 按序；返回 `f`；可只移动 | 并行版不返回 `f`、不保证顺序 |
| `find` 系列 | 至多 N 次；第一个 | C++26 支持 `{...}` 值实参（libc++ 未实现） |
| `find_last` | 返回 `subrange` | 需前向迭代器 |
| `count` | 恰好 N 次 | 返回差类型 |
| `mismatch`/`equal` 三迭代器 | — | 第二序列短 → 越界 UB |
| `is_permutation` | 最坏 O(N²) | 谓词须是等价关系 |
| `search` / `find_end` | 空模式：`first1` / `last1` | — |
| `fold_left` | 结果类型由 `f` 决定 | 无投影、无并行版 |
