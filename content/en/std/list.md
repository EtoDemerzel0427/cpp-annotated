---
title: Class template list
summary: "std::list is a doubly linked list: constant-time insertion and erasure anywhere, insertion and erasure never invalidate other elements, and splice and merge only relink nodes, letting iterators follow their elements into another list."
updated: 2026-10-19
---

!!! tldr
    - Inserting or erasing a single element anywhere is constant time; insertion invalidates no iterators or references, and erasure invalidates only the erased elements.
    - Any insertion into a `list`, range insertion included, has no effect if it throws.
    - `splice` and `merge` link nodes from one `list` into another without copying or moving elements, and iterators and references follow the elements; if the two `list`s' allocators are unequal, `splice` is undefined behavior.
    - `size()` must be constant time, so a `splice` that moves a range out of another `list` is linear.
    - `sort` and `reverse` rearrange links and do not invalidate iterators.

`std::list` is a doubly linked list. It is not fast to iterate: nodes are scattered over the heap and unfriendly to caches. Its value lies in three guarantees no other container gives: constant-time insertion and erasure at any position; insertion and erasure never invalidate iterators and references to other elements; and elements can be moved, node and all, into another `list` in constant time.

## Overview [list.overview]

¶1 A `list` supports bidirectional iterators and constant-time insertion and erasure anywhere in the sequence, but not fast random access.

¶2 It meets the requirements of a container, reversible container, allocator-aware container and sequence container, including most of the optional operations; the exceptions are that it does not provide `operator[]` and `at`. A footnote explains that these two members are provided only by containers whose iterators are random access iterators.

¶3 The iterators meet the constexpr iterator requirements. libc++ in Clang 23 already supports using `list` in constant evaluation; `__cpp_lib_constexpr_list` is `202502L`.

¶4 An incomplete type `T` may be used when instantiating `list`, provided the allocator meets the completeness requirements.

!!! impl
    A libc++ `list<int>` node is 24 bytes: predecessor pointer, successor pointer, plus the `int` and padding. With Clang 23, `sizeof(std::list<int>)` is 24: the two pointers of a sentinel node plus the element count. The sentinel node lives inside the `list` object, so `end()` points into the container object itself, and after two `list`s are swapped, `end()` does not move across.

## Insertion and erasure [list.modifiers]

¶1 Inserting a single element is constant time with exactly one call to a constructor of `T`; inserting multiple elements is linear, and the number of calls to the copy or move constructor equals exactly the number of elements inserted.

¶2 Insertion does not affect the validity of iterators and references; if an exception is thrown, there is no effect. This is much stronger than [[vector]] and [[deque]]: range insertion into a `list` has the strong exception guarantee too. An implementation can construct all new nodes on a temporary chain first and link them in at once after everything has succeeded.

¶3–¶5 `erase`, `pop_front`, `pop_back` and `clear` invalidate only iterators and references to the erased elements and do not throw. Erasing a single element is constant time with one destructor call; erasing a range is linear in its length.

`resize` in [list.capacity] is specified in terms of `insert` and `erase` (¶1–¶4), so its invalidation rules are those of these two operations.

## splice: move nodes, not elements [list.ops]

```cpp title="splice.cpp" run ok
#include <cassert>
#include <list>

int main() {
  std::list<int> a{1, 2, 3}, b{10, 20};
  auto it = b.begin();             // points to 10
  int& r = *it;
  a.splice(a.end(), b);            // constant time: only pointers change
  assert(b.empty());
  assert(&r == &*it && *it == 10); // the iterator and reference still refer to the same element
  a.erase(it);                     // it is now an iterator into a
  assert((a == std::list<int>{1, 2, 3, 20}));
}
```

¶2 `list` provides three forms of `splice`, which destructively move elements from one `list` to another. The same paragraph also says:

!!! std
    The behavior of splice operations is undefined if get_allocator() != x.get_allocator().

`splice` can be constant time only because a node can change owners as is. The node was allocated by `x`'s allocator; once linked into `*this` it will eventually be deallocated by `*this`'s allocator, so the two allocators must be equal.

| Form | Preconditions | Complexity |
|---|---|---|
| `splice(pos, x)` | `addressof(x) != this` | Constant (¶3–¶6) |
| `splice(pos, x, i)` | `i` is a dereferenceable iterator into `x`; unchanged if `pos == i` or `pos == ++i` | Constant (¶7–¶10) |
| `splice(pos, x, first, last)` | `[first, last)` is a valid range in `x`, and `pos` is not in it | Constant if `addressof(x) == this`, otherwise linear (¶11–¶14) |

None of the three forms throws. Pointers and references to the moved elements keep referring to the same elements, which are now members of `*this`; iterators also keep referring to the same elements but from then on behave as iterators into `*this`.

Why is a range `splice` across `list`s linear? Because `size()` must be constant time ([[container.reqmts#54]]), so `list` maintains an element count. When `[first, last)` is moved out of `x`, the number of elements moved must be known, and the only way is to count them. Splicing all of `x`, or a single element, needs no counting: the numbers are `x.size()` and 1. A range `splice` within the same `list` does not change the count and needs no counting either.

!!! history
    C++03 only said `size()` should be constant time, and libstdc++ at the time chose a linear `size()` in exchange for constant-time range `splice`. C++11 made constant-time `size()` mandatory, and the trade-off has been settled by the standard ever since.

## Other list operations

¶1 Because a linked list can insert and erase quickly in the middle, the standard provides a set of operations specifically for it. Arguments named `Predicate` and `BinaryPredicate` must meet the requirements of the algorithms library; `i + n` and `i - n` mean `next(i, n)` and `prev(i, n)`; the definitions of [[alg.sorting]] apply to `merge` and `sort`, and the comparator must be a strict weak ordering.

- `remove(value)`, `remove_if(pred)` (¶15–¶19): erase all elements satisfying the condition, invalidating only the erased elements; return the number erased (they returned `void` before C++20); the predicate is applied exactly `size()` times; stable.
- `unique()`, `unique(pred)` (¶20–¶25): the precondition is that `pred` is an equivalence relation; keeps only the first element of each group of consecutive equivalent elements; the predicate is applied exactly `size() - 1` times.
- `merge(x)` (¶26–¶30): both `list`s are sorted with respect to `comp` and have equal allocators. If `addressof(x) == this`, there is no effect; otherwise `x` is empty afterwards, no elements are copied, and iterators follow their elements; at most `size() + x.size() - 1` comparisons; stable; if an operation other than a comparison throws, there is no effect.
- `reverse()` (¶31–¶32): `noexcept`, linear time, does not affect the validity of iterators and references.
- `sort()` (¶33–¶35): stable, approximately N log N comparisons, does not affect the validity of iterators and references, because it sorts node links rather than element values; if an exception is thrown, the order of the elements is unspecified.

`list` has its own `sort` because `std::sort` needs random access iterators. `list::sort` is usually implemented as a merge sort that only adjusts pointers.

!!! lawyer "constexpr on list::sort"
    In the current draft, the two `sort` declarations in the `list` class definition carry `constexpr`, but the two declarations describing `sort` in [list.ops] do not, an editorial inconsistency. For `forward_list`, both places carry `constexpr`. In libc++ (Clang 23), `list::sort` can be called in constant evaluation.

## erase and erase_if [list.erasure]

¶1 The non-member `erase(c, value)` delegates to `erase_if`; ¶2 `erase_if(c, pred)` is equivalent to `c.remove_if(pred)`. A linked list can unhook nodes directly, without `remove` followed by `erase`.

## When to use list

- When you insert and erase in the middle and need iterators and references to stay valid throughout (`deque` guarantees valid references only for insertion at the ends);
- when you need to transfer elements between sequences in constant time. The classic LRU cache implementation is an `unordered_map<Key, list<…>::iterator>` plus `splice`-ing the hit element to the front;
- when the elements can be neither copied nor moved. `list`'s `emplace` requires only *Cpp17EmplaceConstructible*, and insertion never moves existing elements.

In other situations, the contiguous `vector` is almost always faster.

## Questions

!!! question "Question"
    Is `a.splice(a.begin(), a, std::next(a.begin()), a.end())` valid? What is its complexity, and what does it do?

<details markdown="1">
<summary>Answer</summary>

It is valid. The precondition in paragraph 11 only requires `[first, last)` to be a valid range in `x` (here `*this`) with `pos` not in it; `a.begin()` is not in `[next(a.begin()), a.end())`.

By paragraph 14, it is constant time when `addressof(x) == this`, because the element count does not change and the range length need not be counted. The effect is to move every element except the first in front of the first, that is, to move the original first element to the end.
</details>
