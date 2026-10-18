---
title: 堆操作
summary: “相对 comp 和 proj 的堆”的精确定义（a[⌊(i−1)/2⌋] 不小于 a[i]，且支持 O(log N) 的 push/pop）、make_heap/push_heap/pop_heap/sort_heap/is_heap/is_heap_until 的前置条件与比较次数上限，以及它们与 priority_queue 的关系
status: done
covers: *
papers: P0896R4
related: alg.sorting, priority.queue, alg.binary.search
tags: 标准库, 算法, 堆, priority_queue
updated: 2026-10-18
---

堆算法把一个随机访问区间当作**隐式完全二叉树**来维护：下标 `i` 的父节点是 `⌊(i−1)/2⌋`。它们是 `std::priority_queue`（[[priority.queue]]）的底层实现，也是 `partial_sort` 和 introsort 退化路径的基础。

## 堆的定义（[alg.heap.operations.general] ¶1–¶3）

¶1：随机访问区间 `[a, b)` 是**相对于 `comp` 和 `proj` 的堆**（[[g:heap-with-respect-to]]），当且仅当：

1. 令 N = b − a，对所有 0 < i < N，`bool(invoke(comp, invoke(proj, a[⌊(i−1)/2⌋]), invoke(proj, a[i])))` 为 `false`——父节点不“小于”子节点；
2. `*a` 可以由 `pop_heap` 移除，或者新元素可以由 `push_heap` 加入，耗时 O(log N)。

第 1 条是结构性质：用默认的 `less` 时就是**最大堆**，`*a` 是最大元素（之一）。第 2 条看似多余，实际上是在规定“这是二叉堆这种数据结构”，排除了只满足第 1 条但无法高效维护的布局。¶2：这些性质使堆适合做优先队列。¶3：`make_heap` 把区间变成堆，`sort_heap` 把堆变成有序序列。

所有堆算法都要求 `comp` 是严格弱序（[[alg.sorting#3]]），并要求随机访问迭代器——树形下标计算需要 O(1) 跳转。

## 各算法的契约

| 算法 | 前置条件 | 效果 | 比较次数上限 |
|---|---|---|---|
| `make_heap` | — | 把 `[first, last)` 变成堆 | 3N |
| `push_heap` | `[first, last − 1)` 是堆 | 把 `last − 1` 处的值并入，`[first, last)` 成为堆 | log N |
| `pop_heap` | `[first, last)` 是**非空**堆 | 交换 `first` 与 `last − 1`，使 `[first, last − 1)` 成为堆 | 2 log N |
| `sort_heap` | `[first, last)` 是堆 | 排序（**不稳定**） | 2 N log N |
| `is_heap_until` | — | 最后一个使 `[first, i)` 是堆的 `i` | 线性 |
| `is_heap` | — | `is_heap_until(...) == last` | 线性 |

投影次数一律是比较次数的两倍。经典版的元素要求都是 *Cpp17ValueSwappable* 迭代器 + 值类型可移动构造/赋值。ranges 版都返回 `last`。

几点细节：

- `make_heap` 的 3N 上限对应自底向上的 Floyd 建堆法（线性），而不是逐个 `push_heap`（N log N）；
- `pop_heap` 在空区间上调用违反前置条件（{{ub}}）；
- `push_heap` 的典型用法是先 `push_back` 再 `push_heap`，`pop_heap` 则是先 `pop_heap` 再 `pop_back`——算法只管区间，不管容器大小。

```cpp run title="heap.cpp" ok
#include <algorithm>
#include <cassert>
#include <vector>

int main() {
    std::vector<int> h{3, 1, 4, 1, 5, 9, 2, 6};
    std::make_heap(h.begin(), h.end());          // 最大堆：h[0] 最大
    assert(h.front() == 9 && std::is_heap(h.begin(), h.end()));
    h.push_back(7);
    std::push_heap(h.begin(), h.end());          // 前置条件：[first, last-1) 已是堆
    std::pop_heap(h.begin(), h.end());           // 最大值被换到 last-1
    assert(h.back() == 9);
    h.pop_back();
    std::sort_heap(h.begin(), h.end());          // 升序
    assert(std::is_sorted(h.begin(), h.end()));
}
```

!!! tip "最小堆"
    传 `std::greater<>()` 得到最小堆。所有对同一个堆的操作必须使用**同一个** `comp`——用 `less` 建堆、用 `greater` `push_heap` 违反前置条件（区间不是“相对该 `comp` 的堆”），{{ub}}。`priority_queue` 把比较器存为成员，正是为了保证这一点。

## 思考题

<details markdown="1">
<summary>`sort_heap` 之后的区间还是堆吗？</summary>

用 `less` 时，`sort_heap` 得到升序序列，而 `less` 最大堆要求父节点不小于子节点，升序序列中 `a[0]` 最小，一般不再是堆（除非所有元素等价）。反过来，降序序列总是 `less` 意义下的堆。
</details>

## 小结

- 堆 = 父不小于子（相对 `comp`）+ 可 O(log N) push/pop；默认是最大堆。
- `make_heap` ≤ 3N，`push_heap` ≤ log N，`pop_heap` ≤ 2 log N，`sort_heap` ≤ 2N log N 次比较。
- `push_heap`/`pop_heap` 只处理区间末尾一个元素的进出，容器大小由调用者管理。
- 同一个堆的所有操作必须用同一个 `comp`。
