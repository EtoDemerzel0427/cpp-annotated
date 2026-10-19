---
title: 归并与有序集合操作
summary: merge 与 inplace_merge 的稳定性和等价元素谁先输出；includes、set_union、set_intersection、set_difference、set_symmetric_difference 在含重复元素时各输出几份、取自哪个序列；比较次数上限；以及带输出上界的并行版本如何报告输入消费到了哪里。
status: done
covers: alg.merge, alg.set.operations.general, includes, set.union, set.intersection, set.difference, set.symmetric.difference
papers: P0896R4, P2562R1
related: alg.sorting, alg.binary.search, algorithms.results, algorithm.stable, multiset
tags: 标准库, 算法, merge, 集合运算, 多重集
updated: 2026-10-19
---

!!! tldr
    - 本页的算法都要求输入相对于所用的比较器有序，输出区间不得与任一输入重叠；它们都是稳定的。
    - `merge` 遇到等价元素时先输出第一个序列的，这正是归并排序稳定的原因。
    - 输入含重复元素时，某个值在两个输入中分别出现 m 次和 n 次，并集输出 max(m, n) 份，交集 min(m, n) 份，差集 max(m − n, 0) 份，对称差 |m − n| 份。
    - 交集输出的元素总是取自第一个序列，这在等价但不相等的元素上看得出来。
    - 集合操作至多做 2(N1 + N2) − 1 次比较。

## 一个例子

```cpp run title="setops.cpp" ok
#include <algorithm>
#include <cassert>
#include <iterator>
#include <vector>

int main() {
    std::vector<int> a{1, 1, 2, 4}, b{1, 3, 4, 4};
    std::vector<int> u, i, d, s, m;
    auto out = [](auto& v) { return std::back_inserter(v); };
    std::set_union(a.begin(), a.end(), b.begin(), b.end(), out(u));
    std::set_intersection(a.begin(), a.end(),
                          b.begin(), b.end(), out(i));
    std::set_difference(a.begin(), a.end(),
                        b.begin(), b.end(), out(d));
    std::set_symmetric_difference(a.begin(), a.end(),
                                  b.begin(), b.end(), out(s));
    std::merge(a.begin(), a.end(), b.begin(), b.end(), out(m));
    assert((u == std::vector{1, 1, 2, 3, 4, 4}));  // max(m, n) 份
    assert((i == std::vector{1, 4}));              // min(m, n) 份
    assert((d == std::vector{1, 2}));              // max(m - n, 0) 份
    assert((s == std::vector{1, 2, 3, 4}));        // |m - n| 份
    assert(m.size() == a.size() + b.size());       // merge 不去重
    assert(std::includes(a.begin(), a.end(), i.begin(), i.end()));
}
```

`1` 在 `a` 中出现两次、在 `b` 中出现一次，所以并集里有两个 `1`，交集里有一个，差集里有一个。`merge` 只是把两个有序序列合成一个，不做任何去重。

这些算法都以线性时间处理两个有序序列，共同的前置条件有两条：两个输入分别相对于比较器（和各自的投影）有序，违反时行为未定义；输出区间不与任一输入重叠。

## `merge` 与 `inplace_merge`（[alg.merge]）

¶3 `merge` 的效果有三层：

1. 把第一个序列的前 K 个元素和第二个序列的前 N − K 个元素复制到输出。没有输出上界时就是全部元素；
2. 同一输入中先出现的元素先输出；
3. 对第一个序列的 `e1` 和第二个序列的 `e2`，`e2` 先于 `e1` 输出，当且仅当 `comp(e2, e1)` 为真。

第 3 条说的是：两个元素等价时，第一个序列的先输出。这就是 `merge` 稳定性的精确含义。[[algorithm.stable]] 对稳定的一般定义只涉及同一个序列内部的顺序，`merge` 有两个输入，所以要另外规定跨序列的顺序。归并排序之所以稳定，正是因为左半段的元素总排在右半段的等价元素之前。

¶5 非并行版本至多 N − 1 次比较，并行版本 O(N) 次。¶4 `ranges` 版本返回 `{first1 + K, first2 + N - K, result + N}`，告诉调用者两个输入各消费到了哪里。

¶1 的 K 是为带输出上界的并行 `ranges` 重载准备的。输出空间不够时，K 是第一个序列中会被复制的元素个数：使第一个序列第 K 个位置的元素前面，第二个序列中至少有 N − K 个元素严格小于它的最小 K。注 1 说明 `first1 + K` 指向最后一个被复制元素的下一个位置。

¶9 `inplace_merge(first, middle, last)` 把相邻的两个有序段 `[first, middle)` 和 `[middle, last)` 原地合并成一个有序段。¶11 有足够额外内存时至多 N − 1 次比较，否则 O(N log N) 次，¶12 稳定。它和 `stable_sort` 一样会尝试分配临时缓冲区，只在宿主实现中提供，C++26 起是 `constexpr`（[[P2562R1]]）。

## 含重复元素时的语义（[alg.set.operations.general]）

¶1 这些集合操作也适用于含多个等价元素的序列，即多重集（[[multiset]]）。推广的方式是：并集里每个元素出现最多的次数，交集里出现最少的次数，以此类推。

设某个等价类在第一个序列中有 m 个元素，在第二个序列中有 n 个。各算法的 ¶3 规定了输出几份、取自哪里：

| 算法 | 输出个数 | 取自哪个序列 |
|---|---|---|
| `set_union` | max(m, n) | 先是第一个序列的全部 m 个，再是第二个序列的最后 max(n − m, 0) 个 |
| `set_intersection` | min(m, n) | 第一个序列的前 min(m, n) 个 |
| `set_difference` | max(m − n, 0) | 第一个序列的最后 max(m − n, 0) 个 |
| `set_symmetric_difference` | \|m − n\| | m > n 时取第一个序列的最后 m − n 个，m < n 时取第二个序列的最后 n − m 个 |

元素等价但不相等时，取自哪个序列是看得出来的。例如两个记录序列按 `key` 比较，`value` 各不相同，`set_intersection` 输出的总是第一个序列里的记录。

¶6 四个产生输出的集合操作都是稳定的。¶5 它们至多做 2·((last1 − first1) + (last2 − first2)) − 1 次比较，每个投影的调用次数也不超过这个数。系数 2 来自判断等价需要两次比较：`comp(a, b)` 和 `comp(b, a)`。

## `includes`（[includes]）

¶3 `includes` 在第二个序列是第一个序列的**子序列**时返回 `true`。注 1 解释，子序列指从原序列删去若干元素（可以一个不删，也可以全删）、保持剩余元素顺序得到的序列。

对含重复元素的序列，这意味着每个等价类在第二个序列中的个数不能超过在第一个序列中的个数。所以 `includes({1, 2}, {1, 1})` 为 `false`。

## 有输出上界时：被跳过的元素

经典版本的返回值很简单：`std` 版本返回输出终点，`ranges` 版本返回两个输入的终点和输出终点。C++26 的并行 `ranges` 重载还接受输出区间的终点，输出写满时算法提前结束。调用者想接着处理剩下的输入，就需要知道每个输入消费到了哪里。

为此各算法的 ¶3 引入了**被跳过**（skipped）的元素：没有被复制、但已经处理过的输入元素。返回值形如 `{first1 + A, first2 + B, ...}`，A、B 分别是两个输入中被复制或被跳过的元素个数。例如：

- `set_union`：一个等价类中第一个序列的 k 个元素被复制时，第二个序列中对应的前 min(k, n) 个元素视为被跳过，它们已经由第一个序列的元素代表了；
- `set_intersection`：第一个序列被复制的 k 个元素对应的第二个序列的前 k 个元素视为被跳过；此外，比交集中第 min(M, N + 1) 个元素小的未复制元素也视为被跳过（M 是完整交集的长度，N 是实际输出的个数）。

`set_difference` 的返回类型也因此不同：经典 `ranges` 版本返回 `in_out_result`，不报告第二个输入的位置；并行有界版本返回 `set_difference_truncated_result`，见 [[algorithms.results]]。

## 思考题

!!! question "思考题 1"
    两个 `vector` 都已用 `std::greater<>()` 排成降序，然后调用 `std::set_union(a.begin(), a.end(), b.begin(), b.end(), out)`，不传比较器，会怎样？

<details markdown="1">
<summary>答案</summary>

前置条件要求输入相对于所用的比较器有序。不传比较器时用的是 `less{}`，降序序列不满足这个条件，{{ub}}，实际表现是输出既不有序也不是正确的并集。必须传入与排序时相同的 `std::greater<>()`。
</details>

!!! question "思考题 2"
    `std::includes(a.begin(), a.end(), b.begin(), b.end())` 为真，是否意味着 `set_difference(b, a)` 为空？

<details markdown="1">
<summary>答案</summary>

是。`includes` 为真说明每个等价类在 `b` 中的个数 n 不超过在 `a` 中的个数 m，于是 `set_difference(b, a)` 中每个等价类输出 max(n − m, 0) = 0 份。
</details>

## 小结

- 输入必须相对于同一个比较器有序；输出不得与输入重叠；所有算法都稳定。
- `merge`：等价元素中第一个序列的先输出；N − 1 次比较。`inplace_merge` 视能否分配内存为 N − 1 或 O(N log N) 次比较。
- 重复元素：并集 max，交集 min，差集 max(m − n, 0)，对称差 |m − n|；交集取第一个序列的元素。
- 集合操作至多 2(N1 + N2) − 1 次比较。
- 带输出上界的并行版本用被复制或被跳过的元素个数报告每个输入的消费位置。
