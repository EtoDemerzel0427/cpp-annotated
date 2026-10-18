---
title: 二分查找与划分
summary: lower_bound、upper_bound、equal_range、binary_search 的真正前置条件是“相对某个表达式已划分”而非“已排序”、comp 不必是严格弱序、异构比较时 comp 的实参顺序；以及 is_partitioned、partition、stable_partition、partition_copy、partition_point 的契约与复杂度
status: done
covers: alg.binary.search.general, lower.bound, upper.bound, equal.range, binary.search, alg.partitions
papers: P0896R4, P2562R1
related: alg.sorting, algorithms.requirements, alg.set.operations, associative.reqmts
tags: 标准库, 算法, 二分查找, lower_bound, partition
updated: 2026-10-18
---

教科书说“二分查找要求有序数组”。标准说的比这**更弱也更精确**：要求序列相对于“把查找键绑定到比较函数的一个实参上得到的表达式”是**划分**的（[[alg.sorting#7]] 中定义的 [[g:partitioned-with-respect-to]]）。这一区别决定了哪些异构查找合法、`comp` 需要满足什么，以及 `partition_point` 为什么能作为二分查找的“原语”。

## 总则（[alg.binary.search.general] ¶1）

!!! std
    All of the algorithms in [alg.binary.search] are versions of binary search and assume that the sequence being searched is partitioned with respect to an expression formed by binding the search key to an argument of the comparison function.

后半段讲复杂度：它们对**任何**迭代器类别都只做对数次**比较**；对随机访问迭代器，步数也是对数的；对非随机访问迭代器（比如 `list` 的迭代器），移动迭代器的步数是**线性**的。所以 `std::lower_bound` 用在 `std::list` 上合法，比较次数是 O(log N)，但总时间是 O(N)——比较昂贵（如长字符串）时这仍然可能比线性查找划算。

还要注意 [[alg.sorting#3]] 的措辞：“For algorithms **other than** those described in [alg.binary.search], `comp` shall induce a strict weak ordering”——二分查找**不要求** `comp` 是严格弱序，只要求划分性质。

## `lower_bound`（[lower.bound]）

¶2 *Preconditions*：`[first, last)` 中的元素 `e` 相对于 `bool(invoke(comp, invoke(proj, e), value))` 是划分的——即所有“小于 `value`”的元素都在前面。

¶3 *Returns*：最远的 `i ∈ [first, last]`，使得对每个 `j ∈ [first, i)`，`comp(*j, value)` 为真。即**第一个不小于 `value` 的位置**。

¶4：至多 log₂(last − first) + O(1) 次比较与投影。

## `upper_bound`（[upper.bound]）

¶2：元素相对于 `!bool(invoke(comp, value, invoke(proj, e)))` 划分——所有“`value` 不小于它”的元素在前。

¶3：返回**第一个大于 `value` 的位置**。

!!! warning "两个函数调用 `comp` 的实参顺序相反"
    `lower_bound` 调用 `comp(element, value)`，`upper_bound` 调用 `comp(value, element)`。这是 [[algorithms.requirements#7]] 中“第一个实参总是第一个序列的元素”规则的“另有规定”。写异构比较器时两种签名都要提供；`equal_range` 和 `binary_search` 两种都会用到。

```cpp run title="lower_upper.cpp" ok
#include <algorithm>
#include <cassert>
#include <string>
#include <vector>

struct Rec { int key; std::string val; };

// std 版本：lower_bound 调 comp(elem, value)，upper_bound 调 comp(value, elem)
struct ByKey {
    bool operator()(const Rec& r, int k) const { return r.key < k; }
    bool operator()(int k, const Rec& r) const { return k < r.key; }
};

int main() {
    std::vector<Rec> rs{{1, "a"}, {3, "b"}, {3, "c"}, {7, "d"}};
    auto lo = std::lower_bound(rs.begin(), rs.end(), 3, ByKey{});
    auto hi = std::upper_bound(rs.begin(), rs.end(), 3, ByKey{});
    assert(hi - lo == 2);

    // ranges 版本：用投影，比较器只需比较 int
    auto [b, e] = std::ranges::equal_range(rs, 3, {}, &Rec::key);
    assert(b == lo && e == hi);

    // 前置条件只要求“划分”，不要求“排序”
    std::vector<int> p{2, 1, 3, 9, 5, 7};          // 相对 e < 4 是划分的
    assert(*std::lower_bound(p.begin(), p.end(), 4) == 9);
}
```

最后两行说明：`{2, 1, 3, 9, 5, 7}` 并未排序，但相对 `e < 4` 是划分的（前三个 `< 4`，后三个不是），所以 `lower_bound(..., 4)` 完全合法，返回指向 `9` 的迭代器。

ranges 版本的约束是 `indirect_strict_weak_order<const T*, projected<I, Proj>>`——**语法上**要求 `comp` 对 `(T, 元素)` 和 `(元素, T)` 两种顺序都可调用，这比经典版对 `lower_bound` 只用一种顺序的要求更严。用投影把元素映射到与键同类型，通常就不需要异构比较器了。

## `equal_range` 与 `binary_search`（[equal.range]、[binary.search]）

¶2 *Preconditions*：相对**两个**表达式都划分（`comp(e, value)` 与 `!comp(value, e)`），并且对经典版额外要求：对所有元素 `e`，`comp(e, value)` 蕴含 `!comp(value, e)`——排除了 `comp` 在同一对 `(e, value)` 上“两头都成立”的情形，否则“等价区间”无从谈起。

`equal_range` 返回 `{lower_bound(...), upper_bound(...)}`；至多 2·log₂N + O(1) 次比较。

`binary_search` 只返回 `bool`：是否存在与 `value` 等价的元素（¶3：`!comp(*i, value) && !comp(value, *i)`）。它**不告诉你位置**；需要位置时用 `lower_bound` 后自己判断 `it != last && !comp(value, *it)`。

!!! pitfall "`binary_search` 的“找到”是等价，不是相等"
    `binary_search` 判断的是 `!(a < b) && !(b < a)`，不调用 `operator==`。对按长度比较的字符串序列，查找 `"abc"` 可能因为存在 `"xyz"` 而返回 `true`。

!!! tip "关联容器的成员函数"
    `std::set::lower_bound` 等成员函数利用树结构，对数时间且不受迭代器类别影响；在 `set`/`map` 上调用自由函数 `std::lower_bound` 会退化为线性步数（双向迭代器）。透明比较器（`std::less<>`）配合成员函数可以做异构查找，见 [[associative.reqmts]]。

## 划分（[alg.partitions]）

### `is_partitioned`（¶1–¶3）

判断序列是否相对 `pred`（经投影）划分。线性，至多 N 次谓词应用。空区间是划分的。

### `partition`（¶4–¶8）

把满足 `E(x) = bool(invoke(pred, invoke(proj, x)))` 的元素移到前面，返回分界点 `i`（ranges 版返回 `{i, last}`）。**不稳定**。¶8 的复杂度精细地区分了迭代器类别：恰好 N 次谓词；双向迭代器至多 N/2 次交换（从两端向中间扫描），前向迭代器至多 N 次交换（单向扫描）；并行版 O(N log N) 次交换。

### `stable_partition`（¶9–¶13）

同上但**保持两组内部的相对顺序**。¶13：至多 N log₂N 次交换，若有足够额外内存则 O(N) 次——又一个“资源敏感”的复杂度条款，与 `stable_sort` 同理；同样是 `// hosted`，C++26 起 `constexpr`（[[P2562R1]]）。

### `partition_copy`（¶14–¶22）

把满足条件的元素复制到 `out_true`，其余复制到 `out_false`；¶19 输入与输出不得重叠。经典版返回 `{out_true + Q, out_false + V}`（`pair`），ranges 版返回 `partition_copy_result`（`in_out_out_result`）。C++26 的有界版本（¶15–¶17）在任一输出写满时停下，`N = min(i1 - first, i2 - first)` 这一段条文定义了“停在哪里”。

### `partition_point`（¶23–¶26）

¶24 *Preconditions*：已划分。¶25：返回分界点 `mid`。¶26：O(log N) 次谓词应用。

`partition_point` 是二分查找最一般的形式：`lower_bound(first, last, value, comp)` 等价于 `partition_point(first, last, [&](const auto& e) { return comp(e, value); })`。当你的“查找条件”不是一个“键 + 比较器”时（例如“第一个满足 `f(x) >= target` 的 `x`”，在单调函数上二分），直接用 `partition_point` 最清楚。

```cpp run title="partition_point.cpp" ok
#include <algorithm>
#include <cassert>
#include <ranges>

int main() {
    // 求最小的 n 使 n*n >= 1000：在 iota 视图上二分
    auto r = std::views::iota(0, 1000);
    auto it = std::ranges::partition_point(r, [](int n) { return n * n < 1000; });
    assert(*it == 32);
}
```

## 思考题

<details markdown="1">
<summary>1. 对一个按降序排列的 `vector<int>` 调用 `std::lower_bound(v.begin(), v.end(), 5)` 是 UB 吗？</summary>

一般是。前置条件要求元素相对 `e < 5` 是划分的，即所有 `< 5` 的元素在前；降序序列中 `< 5` 的元素在**后**，除非全部 `< 5` 或全部 `>= 5`，否则不满足前置条件，{{ub}}（实际表现为返回错误位置）。正确做法是传入 `std::greater<>()`：此时要求相对 `e > 5` 划分，降序序列满足。
</details>

<details markdown="1">
<summary>2. 为什么 [alg.sorting.general] ¶3 把二分查找从“严格弱序”要求中豁免？</summary>

二分查找只关心一个固定的 `value` 把序列分成两段，这只需要划分性质；豁免使得更多有用的异构查找合法，例如“按前缀查找”：在有序的字符串序列中，`comp(e, prefix)` 定义为“`e` 的前缀小于 `prefix`”，它对单个 `prefix` 形成划分，但作为元素之间的关系并不一定是严格弱序。
</details>

## 小结

| 算法 | 前置条件（划分相对于） | 返回 | 比较次数 |
|---|---|---|---|
| `lower_bound` | `comp(e, value)` | 第一个不小于 `value` | log₂N + O(1) |
| `upper_bound` | `!comp(value, e)` | 第一个大于 `value` | log₂N + O(1) |
| `equal_range` | 以上两者，且 `comp(e,v)` ⇒ `!comp(v,e)` | `{lower, upper}` | 2 log₂N + O(1) |
| `binary_search` | 同上 | `bool`（等价，不是相等） | log₂N + O(1) |
| `partition_point` | `pred` | 分界点 | O(log N) |
| `partition` | — | 分界点 | N 次谓词；不稳定 |
| `stable_partition` | — | 分界点 | 稳定；N log N 或 O(N) 次交换 |
