---
title: 二分查找与划分
summary: lower_bound、upper_bound、equal_range、binary_search 真正的前置条件是序列相对于查找键已划分，而不是已排序；异构比较时比较器的两种实参顺序；partition 系列算法与作为二分查找最一般形式的 partition_point。
status: done
covers: alg.binary.search.general, lower.bound, upper.bound, equal.range, binary.search, alg.partitions
papers: P0896R4, P2562R1
related: alg.sorting, algorithms.requirements, alg.set.operations, associative.reqmts
tags: 标准库, 算法, 二分查找, lower_bound, partition
updated: 2026-10-19
---

!!! tldr
    - 二分查找只要求序列相对于查找键划分：所有小于键的元素在前面。序列不必整体有序，比较器也不必是严格弱序。
    - `lower_bound` 调用 `comp(元素, 键)`，`upper_bound` 调用 `comp(键, 元素)`。异构比较器要提供两种实参顺序。
    - 比较次数总是对数的；在 `std::list` 这类非随机访问迭代器上，移动迭代器的步数仍是线性的。
    - `binary_search` 判断的是等价，不是相等，而且不告诉你位置。
    - `partition_point` 是二分查找最一般的形式，适合在单调条件上二分。

## 一个没有排序、却可以二分的序列

```cpp run title="partitioned.cpp" ok
#include <algorithm>
#include <cassert>
#include <vector>

int main() {
    std::vector<int> p{2, 1, 3, 9, 5, 7};   // 没有排序
    auto it = std::lower_bound(p.begin(), p.end(), 4);
    assert(*it == 9);
}
```

教科书说二分查找要求数组有序，但这个调用是合法的。`{2, 1, 3, 9, 5, 7}` 没有排序，可是相对于条件 `e < 4` 已经分成了两段：前三个元素小于 4，后三个不小于 4。`lower_bound` 要找的正是这条分界线，它只需要这么多。

## 总则（[alg.binary.search.general] ¶1）

!!! std
    All of the algorithms in [alg.binary.search] are versions of binary search and assume that the sequence being searched is partitioned with respect to an expression formed by binding the search key to an argument of the comparison function.

¶1 二分查找的前置条件是：把查找键绑定到比较函数的一个实参上，得到一个关于元素的条件，序列相对于这个条件是划分的。划分（[[g:partitioned-with-respect-to]]）的定义在 [[alg.sorting#7]]：使条件为真的元素都排在前面。

¶1 的后半段讲复杂度。对任何迭代器，比较次数都是对数的。对随机访问迭代器，在数据结构里移动的步数也是对数的；对非随机访问迭代器，移动的步数是线性的。所以 `std::lower_bound` 用在 `std::list` 上是合法的，比较 O(log N) 次，但总时间是 O(N)。比较代价很高时（例如长字符串），这仍可能比线性查找划算。

[[alg.sorting#3]] 要求比较器构成严格弱序，但明确把二分查找排除在外。二分查找只需要上面的划分性质。

## `lower_bound` 与 `upper_bound`（[lower.bound]、[upper.bound]）

[lower.bound] ¶2 的前置条件是：元素 `e` 相对于 `comp(proj(e), value)` 划分，即所有小于 `value` 的元素在前。¶3 它返回最远的位置 `i`，使得 `[first, i)` 中每个元素都小于 `value`。也就是第一个不小于 `value` 的位置。

[upper.bound] ¶2 的前置条件是：元素相对于 `!comp(value, proj(e))` 划分，即所有不大于 `value` 的元素在前。¶3 它返回第一个大于 `value` 的位置。

两者的 ¶4 都规定至多 log₂(last − first) + O(1) 次比较和投影。

!!! warning "两个函数调用 `comp` 的实参顺序相反"
    `lower_bound` 调用 `comp(元素, value)`，`upper_bound` 调用 `comp(value, 元素)`。一般规则是比较器的第一个实参来自第一个序列（[[algorithms.requirements#7]]），`upper_bound` 是一个例外。写异构比较器时要提供两种签名，因为 `equal_range` 和 `binary_search` 两种都会用到。

```cpp run title="lower_upper.cpp" ok
#include <algorithm>
#include <cassert>
#include <string>
#include <vector>

struct Rec { int key; std::string val; };

// lower_bound 调 comp(elem, k)，upper_bound 调 comp(k, elem)
struct ByKey {
    bool operator()(const Rec& r, int k) const {
        return r.key < k;
    }
    bool operator()(int k, const Rec& r) const {
        return k < r.key;
    }
};

int main() {
    std::vector<Rec> rs{{1, "a"}, {3, "b"}, {3, "c"}, {7, "d"}};
    auto lo = std::lower_bound(rs.begin(), rs.end(), 3, ByKey{});
    auto hi = std::upper_bound(rs.begin(), rs.end(), 3, ByKey{});
    assert(hi - lo == 2);

    // ranges 版本：用投影把元素映射成 int，比较器只需比较 int
    auto [b, e] = std::ranges::equal_range(rs, 3, {}, &Rec::key);
    assert(b == lo && e == hi);
}
```

`ranges` 版本用 `indirect_strict_weak_order<const T*, projected<I, Proj>>` 约束比较器，要求 `(键, 元素)` 和 `(元素, 键)` 两种顺序都能调用。这比经典版严格：经典版 `lower_bound` 只用到一种顺序。好在有了投影（[[g:projection]]），通常可以把元素映射成与键相同的类型，根本不需要异构比较器。

## `equal_range` 与 `binary_search`（[equal.range]、[binary.search]）

两者的 ¶2 要求序列同时相对于 `comp(e, value)` 和 `!comp(value, e)` 划分。对 `std` 中的版本还额外要求：`comp(e, value)` 蕴含 `!comp(value, e)`，即不能对同一对元素和键同时报告小于和大于，否则与键等价的区间就无从谈起。

[equal.range] ¶3 返回 `{lower_bound(...), upper_bound(...)}`，¶4 至多 2·log₂N + O(1) 次比较。

[binary.search] ¶3 只返回一个 `bool`：是否存在与 `value` 等价的元素，即满足 `!comp(*i, value) && !comp(value, *i)` 的元素。它不告诉你位置。需要位置时，用 `lower_bound` 得到 `it`，再检查 `it != last && !comp(value, *it)`。

!!! pitfall "`binary_search` 找到的是等价元素"
    `binary_search` 判断的是 `!(a < b) && !(b < a)`，从不调用 `operator==`。在一个按长度比较的字符串序列里查找 `"abc"`，只要存在 `"xyz"` 就会返回 `true`。

!!! tip "关联容器用成员函数"
    `std::set::lower_bound` 等成员函数直接沿着树查找，时间是对数的。对 `set` 或 `map` 调用自由函数 `std::lower_bound`，迭代器是双向的，步数退化为线性。透明比较器（如 `std::less<>`）配合成员函数也可以做异构查找，见 [[associative.reqmts]]。

## 划分算法（[alg.partitions]）

### `is_partitioned`（¶1–¶3）

¶2 判断序列是否相对于 `pred`（经投影）划分。¶3 至多 N 次谓词调用。空区间是划分的。

### `partition` 与 `stable_partition`（¶4–¶13）

¶6 `partition` 把满足谓词的元素移到前面，返回分界点（`ranges` 版本返回 `{分界点, last}`）。它不稳定。¶8 的复杂度区分了迭代器类别：恰好 N 次谓词调用；双向迭代器至多 N/2 次交换（从两端向中间扫描），前向迭代器至多 N 次交换（单向扫描）；并行版本 O(N log N) 次交换。

¶11 `stable_partition` 做同样的事，并保持两组内部的相对顺序。¶13 至多 N log₂N 次交换，有足够额外内存时只需 O(N) 次。这与 `stable_sort` 一样，复杂度取决于能否分配到临时缓冲区；它同样只在宿主实现中提供，C++26 起是 `constexpr`（[[P2562R1]]）。

### `partition_copy`（¶14–¶22）

¶20 把满足条件的元素复制到 `out_true`，其余复制到 `out_false`。¶19 输入与输出不得重叠。¶21 经典版返回 `pair{out_true + Q, out_false + V}`，`ranges` 版返回 `{输入终点, out_true + Q, out_false + V}`。

¶15–¶17 是为 `ranges` 的并行重载写的。这些重载为两个输出区间各给出一个终点，任一输出写满时算法停止。¶17 定义了停在哪里：第一个装不下的元素之前。

### `partition_point`（¶23–¶26）

¶24 前置条件是序列已划分。¶25 返回分界点 `mid`。¶26 O(log N) 次谓词调用。

`partition_point` 是二分查找最一般的形式。`lower_bound(first, last, value, comp)` 就等价于 `partition_point(first, last, [&](const auto& e) { return comp(e, value); })`。查找条件不是键加比较器的形式时，例如找第一个满足 `f(x) >= target` 的 `x`（`f` 单调），直接用 `partition_point` 最清楚：

```cpp run title="partition_point.cpp" ok
#include <algorithm>
#include <cassert>
#include <ranges>

int main() {
    // 求最小的 n 使 n*n >= 1000：在 iota 视图上二分
    auto r = std::views::iota(0, 1000);
    auto it = std::ranges::partition_point(
        r, [](int n) { return n * n < 1000; });
    assert(*it == 32);
}
```

## 思考题

!!! question "思考题 1"
    对一个按降序排列的 `vector<int>` 调用 `std::lower_bound(v.begin(), v.end(), 5)`，是未定义行为吗？

<details markdown="1">
<summary>答案</summary>

一般是。前置条件要求小于 5 的元素都在前面，降序序列里它们都在后面。除非元素全部小于 5 或全部不小于 5，前置条件不满足，{{ub}}，实际表现为返回错误的位置。正确做法是传入 `std::greater<>()`，这时前置条件变成大于 5 的元素都在前面，降序序列满足它。
</details>

!!! question "思考题 2"
    为什么 [[alg.sorting#3]] 把二分查找从严格弱序的要求里排除？

<details markdown="1">
<summary>答案</summary>

二分查找只关心一个固定的键把序列分成两段，有划分性质就够了。放宽之后，更多有用的查找成为合法的。例如在有序的字符串序列里按前缀查找：`comp(e, prefix)` 定义为 `e` 截取到 `prefix` 的长度后小于 `prefix`。对一个固定的 `prefix`，它把序列分成两段，但作为字符串之间的关系，它不一定是严格弱序。
</details>

## 小结

| 算法 | 前置条件：相对于什么划分 | 返回 | 比较次数 |
|---|---|---|---|
| `lower_bound` | `comp(e, value)` | 第一个不小于 `value` 的位置 | log₂N + O(1) |
| `upper_bound` | `!comp(value, e)` | 第一个大于 `value` 的位置 | log₂N + O(1) |
| `equal_range` | 以上两者，且 `comp(e, v)` 蕴含 `!comp(v, e)` | `{lower, upper}` | 2 log₂N + O(1) |
| `binary_search` | 同上 | `bool`，按等价判断 | log₂N + O(1) |
| `partition_point` | `pred` | 分界点 | O(log N) |
| `partition` | 无 | 分界点 | N 次谓词；不稳定 |
| `stable_partition` | 无 | 分界点 | 稳定；N log N 或 O(N) 次交换 |
