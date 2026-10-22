---
title: Class template forward_list
summary: "std::forward_list is a singly linked list designed to have no overhead compared with a hand-written C singly linked list, so it has no size(), back() or push_back(), and every modification happens after some position."
updated: 2026-10-19
---

!!! tldr
    - `forward_list` aims for zero space and time overhead relative to a hand-written C singly linked list, so it has no `size()`, `back()` or `push_back()`, and cannot be traversed backwards.
    - A singly linked list cannot reach the predecessor, so insertion and erasure are spelled `insert_after` and `erase_after`; at the head of the list, `before_begin()` serves as the predecessor.
    - The ranges of `erase_after` and `splice_after` are open ranges `(first, last)`.
    - Insertion invalidates no iterators or references, and erasure invalidates only the erased elements; a modifying operation that throws has no effect on the container.
    - `splice_after(pos, x)`, which takes over a whole list, is linear time, because it first has to walk to the end of `x`.

`std::forward_list` (C++11) is a singly linked list. It is not a trimmed-down [[list]]; the two have different design goals: `list` aims for the full sequence container interface, `forward_list` for zero overhead.

## What zero overhead leaves out [forward.list.overview]

¶1 A `forward_list` supports forward iterators and constant-time insertion and erasure anywhere in the sequence, but not fast random access. Note 1 states the design goal of the whole class:

!!! std
    It is intended that forward_list have zero space or time overhead relative to a hand-written C-style singly linked list. Features that would conflict with that goal have been omitted.

The omitted features are:

- `size()`: maintaining an element count takes an extra field and an extra increment or decrement on every insertion and erasure. Paragraph 2 therefore says `forward_list` meets the container requirements, except that it does not provide `size()` and its `operator==` has linear complexity. For containers in general, `==` is constant time when the sizes differ ([[container.reqmts#45]]), which is impossible without `size()`.
- `back()`, `push_back()`, `pop_back()`: constant-time access to the end would need an extra tail pointer.
- Reverse iteration: impossible for a singly linked list, so it is not a reversible container.

!!! impl
    With libc++ (Clang 23), `sizeof(std::forward_list<int>)` is 8: just a head pointer. A `forward_list<int>` node is 16 bytes: the next pointer plus the `int` and padding.

¶2 also says that `forward_list` meets the allocator-aware container requirements and provides the `assign` member functions and some of the optional sequence operations: `front`, `emplace_front`, `push_front`, `prepend_range` and `pop_front`.

¶4 The iterators meet the constexpr iterator requirements; libc++ in Clang 23 already supports using `forward_list` in constant evaluation. ¶5 An incomplete type `T` may be used when instantiating `forward_list`, provided the allocator meets the completeness requirements.

## Operating after a position

```cpp title="erase-after.cpp" run ok
#include <cassert>
#include <forward_list>
#include <iterator>

int main() {
  std::forward_list<int> l{1, 2, 3, 4};
  // erase the first even number: we need the position before it
  for (auto prev = l.before_begin(), cur = l.begin();
       cur != l.end(); prev = cur++) {
    if (*cur % 2 == 0) { l.erase_after(prev); break; }
  }
  assert((l == std::forward_list<int>{1, 3, 4}));
  assert(std::distance(l.begin(), l.end()) == 3);  // no size()
}
```

Erasing a node from a singly linked list means modifying the next pointer of the node before it, and a singly linked list has no constant-time way to find the predecessor. So the modifying operations of `forward_list` all take the predecessor as their argument: `insert_after(pos, x)` inserts after `pos`, and `erase_after(pos)` erases the element after `pos`.

¶3 Note 2 uses this to explain how ranges are written: `erase_after` and `splice_after` use open ranges `(first, last)`, where `first` itself is not in the range; it is the predecessor of the first element processed.

### before_begin [forward.list.iter]

When inserting or erasing at the head of the list, the first element has no predecessor. `before_begin()` and `cbefore_begin()` supply one.

¶2 `before_begin()` returns a non-dereferenceable iterator that, when incremented, is equal to `begin()`. ¶3 `before_begin() == end()` shall be false.

In implementations, `before_begin()` points to a header node embedded in the container object, which has only a next field. Like `end()`, it corresponds to no element.

## Modifiers [forward.list.modifiers]

¶1 is the general rule for all modifying operations:

- Insertion does not affect the validity of iterators and references; erasure invalidates only iterators and references to the erased elements;
- if any modifying operation throws, it has no effect on the container;
- inserting n elements is linear time with exactly n calls to the copy or move constructor; erasing n elements is linear time with exactly n destructor calls.

Highlights of each member:

| Member | Preconditions | Return value and notes |
|---|---|---|
| `emplace_front`, `push_front`, `prepend_range` | None | `prepend_range` keeps the elements' original order; it does not reverse them (¶4) |
| `pop_front()` | Non-empty | As if by `erase_after(before_begin())` (¶5) |
| `insert_after(pos, x)` | `pos` is `before_begin()` or a dereferenceable iterator in `[begin(), end())` | Points to the new element (¶6–¶11) |
| `insert_after(pos, n, x)` | Same | Points to the last new element; returns `pos` if n is 0 (¶12–¶14) |
| `insert_after(pos, first, last)` | Same; `first` and `last` are not iterators into `*this` | Points to the last new element, or `pos` (¶15–¶17) |
| `insert_range_after(pos, rg)` | Same; `rg` and `*this` do not overlap | Same (¶18–¶20) |
| `emplace_after(pos, args...)` | Same | The new element is direct-non-list-initialized with `args...` (¶22–¶24) |
| `erase_after(pos)` | The iterator following `pos` is dereferenceable | The element after the erased one, or `end()`; does not throw (¶25–¶28) |
| `erase_after(pos, last)` | All iterators in `(pos, last)` are dereferenceable | `last`; does not throw (¶29–¶32) |
| `resize(sz)`, `resize(sz, c)` | None | Specified in terms of `distance(begin(), end())`, hence linear (¶33–¶36) |
| `clear()` | None | `noexcept`, does not invalidate the past-the-end iterator (¶37–¶38) |

`list::insert` returns the first new element, but the `insert_after` family returns the last new element. That is because continuing to insert further on needs exactly that last new element as the predecessor.

¶38 explicitly guarantees that `clear()` does not invalidate the past-the-end iterator. For sequence containers in general, [[sequence.reqmts#54]] only says `clear()` may invalidate it.

## List operations [forward.list.ops]

¶1 Same conventions as [[list]]: arguments named `Predicate` and `BinaryPredicate` must meet the requirements of the algorithms library, and the definitions of [[alg.sorting]] apply to `merge` and `sort`. `i + n` means `next(i, n)`; since a forward iterator cannot go backwards, `i - n` is defined separately as the iterator `j` such that `j + n == i`.

### splice_after

All three forms of `splice_after` unhook nodes from `x` and link them after `pos`, without copying or moving elements. Pointers and references to transferred elements keep referring to the same elements, and so do iterators, which from then on behave as iterators into `*this`. The preconditions all include that the two lists' allocators compare equal.

| Form | Elements moved | Complexity |
|---|---|---|
| `splice_after(pos, x)` | All elements of `x`, leaving `x` empty; requires `addressof(x) != this` | O(distance(x.begin(), x.end())) (¶2–¶5) |
| `splice_after(pos, x, i)` | The one element after `i`; unchanged if `pos == i` or `pos == ++i` | O(1) (¶6–¶9) |
| `splice_after(pos, x, first, last)` | The open range `(first, last)`; `pos` is not in the range | O(distance(first, last)) (¶10–¶12) |

Splicing a whole list is not constant time. To link `x` after `pos`, the next pointer of `x`'s last node must point to `pos`'s former successor, and the only way to find the last node is to walk from the head to the end. That is the direct cost of not keeping a tail pointer.

### remove, unique, merge, sort, reverse

- `remove(value)`, `remove_if(pred)` (¶13–¶17): erase all elements satisfying the condition and return the number erased; the predicate is applied exactly `distance(begin(), end())` times; only the erased elements are invalidated; stable.
- `unique()`, `unique(pred)` (¶18–¶23): the precondition is that `pred` is an equivalence relation; keeps only the first element of each group of consecutive equivalent elements.
- `merge(x)` (¶24–¶28): both lists are sorted with respect to `comp` and have equal allocators. Afterwards `x` is empty; no elements are copied, and iterators follow their elements; stable; if an operation other than a comparison throws, there is no effect.
- `sort()` (¶29–¶31): stable, approximately N log N comparisons, does not affect the validity of iterators and references, because it rearranges node links, not element values.
- `reverse()` (¶32–¶33): `noexcept`, linear time, does not affect the validity of iterators and references.

## erase and erase_if [forward.list.erasure]

¶1 The non-member `erase(c, value)` delegates to `erase_if` with a lambda that compares equal to `value` as the predicate; ¶2 `erase_if(c, pred)` is equivalent to `c.remove_if(pred)`. A linked list can unhook nodes directly, without `remove` followed by `erase`.

## Questions

!!! question "Question"
    Why is `forward_list::splice_after(pos, x)` linear while `list::splice(pos, x)` is constant time?

<details markdown="1">
<summary>Answer</summary>

Linking all of `x` after `pos` requires modifying the next pointer of `x`'s last node. `list` is doubly linked, and `x`'s last node is the predecessor of `x.end()`, available in constant time. `forward_list` keeps only a head pointer, so finding the last node means walking from head to end: O(distance(x.begin(), x.end())) (¶5).

For the range versions the situation is the reverse. A range `splice` between different `list`s is linear because it has to count the elements in the range to update `size()`; `forward_list` has no `size()`, but it still has to walk the range to find its last node.
</details>
