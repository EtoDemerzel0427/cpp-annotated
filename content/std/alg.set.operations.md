---
title: 归并与有序集合操作
summary: merge 与 inplace_merge 的稳定性与“相等时先取第一个序列”的精确规则；includes、set_union、set_intersection、set_difference、set_symmetric_difference 在多重集上的 max/min/差/|m−n| 计数语义、取哪个序列的元素、2(N1+N2)−1 的比较上限，以及 C++26 有界输出版本里“被跳过的元素”与返回值
status: done
covers: alg.merge, alg.set.operations.general, includes, set.union, set.intersection, set.difference, set.symmetric.difference
papers: P0896R4, P2562R1
related: alg.sorting, alg.binary.search, algorithms.results, algorithm.stable, multiset
tags: 标准库, 算法, merge, 集合运算, 多重集
updated: 2026-10-18
---

本页的算法都要求输入**已相对 `comp`（和投影）有序**，然后以线性时间把两个有序序列合成一个。共同的前置条件有两条：输入有序（违反为 {{ub}}，通常表现为输出错乱）；**输出区间不得与任一输入重叠**。它们都是**稳定**的（[[algorithm.stable]]），而“稳定”在这里的精确含义写在各自的 *Effects* 里。

## `merge`（[alg.merge] ¶1–¶6）

¶3 的效果描述有三层：

1. 把 `[first1, last1)` 的前 K 个元素和 `[first2, last2)` 的前 N−K 个元素复制到输出（无上界时就是全部）；
2. 同一输入中先出现的元素先输出；
3. 对 `e1 ∈ 序列 1`、`e2 ∈ 序列 2`，`e2` 先于 `e1` 输出**当且仅当** `comp(e2, e1)` 为真。

第 3 条意味着：**等价元素中，第一个序列的先输出**。这就是 merge 稳定性的精确定义，也是归并排序稳定的根源。

¶5：非并行版至多 N−1 次比较；并行版 O(N)。¶4：ranges 版返回 `{first1 + K, first2 + N - K, result + N}`（`merge_result`）。

C++26 的有界版本（¶1.1.2、¶1.4）：输出空间不够时，K 是“第一个序列中会被复制到输出的元素个数”，定义得很绕——“最小的 K，使得 `first1 + K` 处的元素前面在序列 2 中至少有 N−K 个元素严格小于它”。注 1：`first1 + K` 指向最后一个被复制的元素之后。

## `inplace_merge`（¶7–¶14）

把相邻的两个有序段 `[first, middle)`、`[middle, last)` 原地合并。¶11：有足够额外内存时至多 N−1 次比较，否则 O(N log N)——与 `stable_sort` 同样的“资源敏感”复杂度，同样 `// hosted`、C++26 起 `constexpr`（[[P2562R1]]）。¶12：稳定。

## 集合操作的多重集语义（[alg.set.operations.general]）

¶1：这些操作也适用于含重复等价元素的**多重集**（[[multiset]]），语义按“标准方式”推广：`set_union` 中每个元素出现**最多次数**，`set_intersection` 中**最少次数**，依此类推。设某个等价类在序列 1 中有 m 个、在序列 2 中有 n 个：

| 算法 | 输出个数 | 取自哪个序列 |
|---|---|---|
| `set_union` | max(m, n) | 先是序列 1 的全部 m 个，然后序列 2 的**最后** max(n−m, 0) 个 |
| `set_intersection` | min(m, n) | 序列 1 的**前** min(m, n) 个 |
| `set_difference` | max(m−n, 0) | 序列 1 的**最后** max(m−n, 0) 个 |
| `set_symmetric_difference` | \|m−n\| | m > n 时取序列 1 的最后 m−n 个，m < n 时取序列 2 的最后 n−m 个 |

“取自哪个序列”在等价但不相等的元素上是可观察的（例如按 `key` 比较、但 `value` 不同的记录）：`set_intersection` 输出的总是第一个序列的元素。

```cpp run title="setops.cpp" ok
#include <algorithm>
#include <cassert>
#include <iterator>
#include <vector>

int main() {
    std::vector<int> a{1, 1, 2, 4}, b{1, 3, 4, 4};
    std::vector<int> u, i, d, s, m;
    std::set_union(a.begin(), a.end(), b.begin(), b.end(), std::back_inserter(u));
    std::set_intersection(a.begin(), a.end(), b.begin(), b.end(), std::back_inserter(i));
    std::set_difference(a.begin(), a.end(), b.begin(), b.end(), std::back_inserter(d));
    std::set_symmetric_difference(a.begin(), a.end(), b.begin(), b.end(), std::back_inserter(s));
    std::merge(a.begin(), a.end(), b.begin(), b.end(), std::back_inserter(m));
    assert((u == std::vector{1, 1, 2, 3, 4, 4}));   // 每个值取 max(m, n) 份
    assert((i == std::vector{1, 4}));               // 取 min(m, n) 份
    assert((d == std::vector{1, 2}));               // 取 max(m - n, 0) 份
    assert((s == std::vector{1, 2, 3, 4}));         // 取 |m - n| 份
    assert(m.size() == a.size() + b.size());        // merge 不去重
    assert(std::includes(a.begin(), a.end(), i.begin(), i.end()));
}
```

## `includes`（[includes]）

¶3：当且仅当 `[first2, last2)` 是 `[first1, last1)` 的**子序列**（注 1：可以删去若干元素、保持剩余顺序得到）时返回 `true`。在多重集语义下，这意味着每个等价类在序列 2 中的个数不超过序列 1 中的个数：`includes({1, 2}, {1, 1})` 为 `false`。

## 复杂度与稳定性

所有集合操作：至多 2·((last1 − first1) + (last2 − first2)) − 1 次比较和每个投影的应用。系数 2 是因为判断等价需要比较两次（`comp(a, b)` 和 `comp(b, a)`）。四个产出型操作都是稳定的（¶6）。

## C++26 有界输出：被“跳过”的元素与返回值

经典版（无上界）只返回输出终点（`std::`）或两个输入终点 + 输出终点（`ranges::`）。C++26 的并行 ranges 重载带输出上界，输出写满时算法提前结束，此时调用者需要知道**每个输入消费到了哪里**才能续传。条文为此引入“**被跳过**”（*skipped*）的概念：

- `set_union`（¶3）：若某等价类中序列 1 的 k 个元素被复制，则序列 2 中对应的前 min(k, n) 个元素视为被跳过；
- `set_intersection`（¶3）：被复制的 k 个元素对应的序列 2 的前 k 个视为被跳过；另外，比交集中第 min(M, N+1) 个元素小的未复制元素也视为被跳过；
- 返回 `{first1 + A, first2 + B, ...}`，A、B 是各输入中“被复制或被跳过”的元素数。

注意 `set_difference` 的经典 ranges 版返回 `in_out_result`（不含第二个输入的位置），并行有界版返回 `set_difference_truncated_result`（`in_in_out_result`），见 [[algorithms.results]]。

## 思考题

<details markdown="1">
<summary>1. 两个 `vector` 都已用 `std::greater<>()` 降序排好，调用 `std::set_union(a.begin(), a.end(), b.begin(), b.end(), out)`（不传比较器）会怎样？</summary>

前置条件要求两个输入相对于**所用的** `comp` 有序；不传比较器时 `comp` 是 `less{}`，降序序列不满足，{{ub}}——实际表现是输出既不有序也不是正确的并集。必须传入与排序时相同的 `std::greater<>()`。这也是为什么集合算法的比较器参数总是与排序时的比较器“成对出现”。
</details>

<details markdown="1">
<summary>2. 为什么 `merge` 的稳定性要专门规定“`e2` 先于 `e1` 当且仅当 `comp(e2, e1)`”，而不是简单地说“稳定”？</summary>

[[algorithm.stable]] 对“稳定”的一般定义只涉及**同一个**输入序列内等价元素的相对顺序；`merge` 有两个输入，必须额外规定跨序列的等价元素谁先谁后。这条规则（等价时取序列 1 的）正是归并排序能保持稳定的关键：左半段的元素总在右半段等价元素之前。
</details>

## 小结

- 输入必须有序；输出不得与输入重叠；都稳定。
- `merge`：等价元素中第一个序列的先出；N−1 次比较；`inplace_merge` 视内存为 N−1 或 N log N。
- 多重集语义：并 = max，交 = min，差 = max(m−n, 0)，对称差 = |m−n|；交集取第一个序列的元素。
- 集合操作至多 2(N1+N2)−1 次比较。
- C++26 有界版本用“复制或跳过的元素数”报告每个输入的消费位置。
