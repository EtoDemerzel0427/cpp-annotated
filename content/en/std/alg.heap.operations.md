---
title: Heap operations
summary: "How the standard defines when a random access range is a heap; the preconditions and comparison bounds of make_heap, push_heap, pop_heap, sort_heap and is_heap; and how they relate to priority_queue."
updated: 2026-10-19
---

!!! tldr
    - The heap algorithms view a random access range as a complete binary tree: the parent of index `i` is `(i − 1) / 2`. With the default comparator, a parent is not less than its children, i.e. a max-heap.
    - `push_heap` and `pop_heap` only handle one element entering or leaving at the end of the range; the caller manages the size of the container.
    - Comparison bounds: `make_heap` 3N, `push_heap` log N, `pop_heap` 2 log N, `sort_heap` 2N log N.
    - All operations on the same heap must use the same comparator, or a precondition is violated.

## An example

```cpp run title="heap.cpp" ok
#include <algorithm>
#include <cassert>
#include <vector>

int main() {
    std::vector<int> h{3, 1, 4, 1, 5, 9, 2, 6};
    std::make_heap(h.begin(), h.end());     // max-heap: h[0] is the largest
    assert(h.front() == 9);
    assert(std::is_heap(h.begin(), h.end()));

    h.push_back(7);                         // first put it in the container
    std::push_heap(h.begin(), h.end());     // then merge it into the heap

    std::pop_heap(h.begin(), h.end());      // the maximum is swapped to the end
    assert(h.back() == 9);
    h.pop_back();                           // then remove it from the container

    std::sort_heap(h.begin(), h.end());     // ascending
    assert(std::is_sorted(h.begin(), h.end()));
}
```

The heap algorithms operate only on iterator ranges and know nothing of containers. So adding an element is `push_back` followed by `push_heap`, and taking one out is `pop_heap` followed by `pop_back`. `std::priority_queue` ([[priority.queue]]) is implemented with these algorithms.

## What a heap is ([alg.heap.operations.general])

¶1 A random access range `[a, b)` is a **heap with respect to `comp` and `proj`** ([[g:heap-with-respect-to]]) if two conditions hold:

1. With N = b − a, for all 0 < i < N, `comp(proj(a[⌊(i − 1)/2⌋]), proj(a[i]))` is false;
2. `*a` can be removed with `pop_heap`, and a new element can be added with `push_heap`, both in O(log N) time.

Condition 1 is the structural property. Viewing the range as a complete binary tree laid out level by level, `a[⌊(i − 1)/2⌋]` is the parent of `a[i]`, and the condition requires that a parent not be less than its children. With the default `less`, this is a max-heap, and `*a` is (one of) the largest elements.

Condition 2 specifies that this is the binary heap data structure, which must be efficiently maintainable.

¶2 These properties make heaps useful as priority queues. ¶3 `make_heap` turns a range into a heap, and `sort_heap` turns a heap into a sorted sequence.

The heap algorithms all require random access iterators, because finding parents and children in the tree needs jumps by index. They also all require the comparator to induce a strict weak ordering ([[alg.sorting#3]]).

## The contract of each algorithm

| Algorithm | Precondition | Effect | Comparison bound |
|---|---|---|---|
| `make_heap` | none | turns `[first, last)` into a heap | 3N |
| `push_heap` | `[first, last − 1)` is a heap | merges the value at `last − 1` in, so `[first, last)` becomes a heap | log N |
| `pop_heap` | `[first, last)` is a non-empty heap | swaps the values at `first` and `last − 1` and makes `[first, last − 1)` a heap | 2 log N |
| `sort_heap` | `[first, last)` is a heap | sorts, not stable | 2N log N |
| `is_heap_until` | none | returns the last `i` such that `[first, i)` is a heap | linear |
| `is_heap` | none | `is_heap_until(...) == last` | linear |

The number of projection applications is always twice the number of comparisons. The `std` versions require the iterators to meet *Cpp17ValueSwappable* and the element type to be move constructible and move assignable; the `ranges` versions all return `last`.

The 3N bound for `make_heap` corresponds to Floyd's bottom-up heap construction, which is linear. Building a heap by repeated `push_heap` takes about N log N comparisons in the worst case and cannot meet that bound.

`pop_heap` requires the heap to be non-empty; calling it on an empty range is {{ub}}.

!!! tip "Min-heaps"
    Pass `std::greater<>()` to get a min-heap. All operations on the same heap must use the same comparator. If you build the heap with `less` and then call `push_heap` with `greater`, the range is not a heap with respect to that comparator; the precondition is violated, which is {{ub}}. `priority_queue` stores its comparator as a member precisely to guarantee this.

## Questions

!!! question "Question"
    Is the range still a heap after `sort_heap`?

<details markdown="1">
<summary>Answer</summary>

Generally not. With `less`, `sort_heap` produces an ascending sequence with `a[0]` the smallest, while a max-heap requires parents to be not less than their children, so unless all elements are equivalent it is no longer a heap. Conversely, a descending sequence is always a heap in the sense of `less`: a parent's index is always smaller than its children's, so its value is not less than theirs.
</details>

## Summary

- Heap = parents not less than children (with respect to `comp`) + O(log N) insertion and removal; the default is a max-heap.
- `make_heap` ≤ 3N, `push_heap` ≤ log N, `pop_heap` ≤ 2 log N, `sort_heap` ≤ 2N log N comparisons.
- `push_heap` and `pop_heap` handle only the one element at the end of the range; the caller manages the container's size.
- All operations on the same heap must use the same comparator.
