---
title: 堆操作
summary: 标准怎样定义一个随机访问区间是堆；make_heap、push_heap、pop_heap、sort_heap、is_heap 的前置条件与比较次数上限；它们与 priority_queue 的关系。
status: done
covers: *
papers: P0896R4
related: alg.sorting, priority.queue, alg.binary.search
tags: 标准库, 算法, 堆, priority_queue
updated: 2026-10-19
---

!!! tldr
    - 堆算法把随机访问区间看作一棵完全二叉树：下标 `i` 的父节点是 `(i − 1) / 2`。默认比较器下父节点不小于子节点，即最大堆。
    - `push_heap` 和 `pop_heap` 只处理区间末尾一个元素的进出，容器的大小由调用者自己管理。
    - 比较次数上限：`make_heap` 3N，`push_heap` log N，`pop_heap` 2 log N，`sort_heap` 2N log N。
    - 对同一个堆的所有操作必须使用同一个比较器，否则违反前置条件。

## 一个例子

```cpp run title="heap.cpp" ok
#include <algorithm>
#include <cassert>
#include <vector>

int main() {
    std::vector<int> h{3, 1, 4, 1, 5, 9, 2, 6};
    std::make_heap(h.begin(), h.end());     // 最大堆：h[0] 最大
    assert(h.front() == 9);
    assert(std::is_heap(h.begin(), h.end()));

    h.push_back(7);                         // 先放进容器
    std::push_heap(h.begin(), h.end());     // 再并入堆

    std::pop_heap(h.begin(), h.end());      // 最大值被换到末尾
    assert(h.back() == 9);
    h.pop_back();                           // 再从容器移除

    std::sort_heap(h.begin(), h.end());     // 升序
    assert(std::is_sorted(h.begin(), h.end()));
}
```

堆算法只操作迭代器区间，不知道容器的存在。所以加入元素是先 `push_back` 再 `push_heap`，取出元素是先 `pop_heap` 再 `pop_back`。`std::priority_queue`（[[priority.queue]]）就是用这几个算法实现的。

## 什么是堆（[alg.heap.operations.general]）

¶1 随机访问区间 `[a, b)` 是**相对于 `comp` 和 `proj` 的堆**（heap with respect to，[[g:heap-with-respect-to]]），需要满足两条：

1. 设 N = b − a，对所有 0 < i < N，`comp(proj(a[⌊(i − 1)/2⌋]), proj(a[i]))` 为假；
2. 可以用 `pop_heap` 移除 `*a`，也可以用 `push_heap` 加入新元素，耗时都是 O(log N)。

第 1 条是结构性质。把区间看作按层排列的完全二叉树，`a[⌊(i − 1)/2⌋]` 是 `a[i]` 的父节点，这一条要求父节点不小于子节点。用默认的 `less` 时就是最大堆，`*a` 是最大的元素（之一）。

第 2 条规定了这是二叉堆这种数据结构，要能高效地维护。

¶2 这些性质使堆适合用作优先队列。¶3 `make_heap` 把区间变成堆，`sort_heap` 把堆变成有序序列。

堆算法都要求随机访问迭代器，因为在树中找父节点、子节点需要按下标跳转。它们也都要求比较器构成严格弱序（[[alg.sorting#3]]）。

## 各算法的契约

| 算法 | 前置条件 | 效果 | 比较次数上限 |
|---|---|---|---|
| `make_heap` | 无 | 把 `[first, last)` 变成堆 | 3N |
| `push_heap` | `[first, last − 1)` 是堆 | 把 `last − 1` 处的值并入，`[first, last)` 成为堆 | log N |
| `pop_heap` | `[first, last)` 是非空的堆 | 交换 `first` 与 `last − 1` 处的值，使 `[first, last − 1)` 成为堆 | 2 log N |
| `sort_heap` | `[first, last)` 是堆 | 排序，不稳定 | 2N log N |
| `is_heap_until` | 无 | 返回最后一个使 `[first, i)` 是堆的 `i` | 线性 |
| `is_heap` | 无 | `is_heap_until(...) == last` | 线性 |

投影的调用次数一律是比较次数的两倍。`std` 版本要求迭代器满足 *Cpp17ValueSwappable*、元素类型可以移动构造和移动赋值；`ranges` 版本都返回 `last`。

`make_heap` 的 3N 上限对应自底向上建堆的 Floyd 算法，它是线性的。逐个 `push_heap` 建堆在最坏情况下需要约 N log N 次比较，满足不了这个上限。

`pop_heap` 要求堆非空，对空区间调用是 {{ub}}。

!!! tip "最小堆"
    传入 `std::greater<>()` 得到最小堆。对同一个堆的所有操作必须使用同一个比较器。用 `less` 建堆、再用 `greater` 调用 `push_heap`，区间就不是相对于这个比较器的堆，违反前置条件，{{ub}}。`priority_queue` 把比较器存为成员，就是为了保证这一点。

## 思考题

!!! question "思考题"
    `sort_heap` 之后的区间还是堆吗？

<details markdown="1">
<summary>答案</summary>

一般不是。用 `less` 时，`sort_heap` 得到升序序列，`a[0]` 最小，而最大堆要求父节点不小于子节点，所以除非所有元素等价，它不再是堆。反过来，降序序列总是 `less` 意义下的堆：父节点的下标总比子节点小，值也就不小于子节点。
</details>

## 小结

- 堆 = 父节点不小于子节点（相对于 `comp`）+ 可以 O(log N) 地加入和移除；默认是最大堆。
- `make_heap` ≤ 3N，`push_heap` ≤ log N，`pop_heap` ≤ 2 log N，`sort_heap` ≤ 2N log N 次比较。
- `push_heap`、`pop_heap` 只处理区间末尾的一个元素，容器大小由调用者管理。
- 同一个堆的所有操作必须使用同一个比较器。
