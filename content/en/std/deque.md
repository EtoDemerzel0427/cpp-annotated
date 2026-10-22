---
title: Class template deque
summary: "std::deque is a random-access sequence with constant-time insertion and erasure at both ends; its complexity and invalidation rules almost uniquely determine the \"fixed-size blocks plus a table of block pointers\" implementation."
updated: 2026-10-19
---

!!! tldr
    - Inserting a single element at either end always takes constant time and calls a constructor of `T` exactly once; existing elements never move.
    - Insertion at either end invalidates all iterators but no references to elements; insertion in the middle invalidates both.
    - Single-element insertion at either end has an unconditional strong exception guarantee, stronger than `vector::push_back`.
    - When inserting or erasing in the middle, the implementation shifts only the side closer to an end.
    - `deque` is not contiguous storage and has no `capacity()` or `reserve()`.

`std::deque` (double-ended queue) is a random-access sequence that supports efficient insertion at both ends. Its wording is short, but its complexity and invalidation rules almost uniquely determine its data structure, so the best approach is to work backwards from the wording to the implementation.

## Starting from one guarantee

```cpp title="deque-refs.cpp" run ok
#include <cstdio>
#include <deque>

int main() {
  std::deque<int> d{1, 2, 3};
  int* p = &d[1];
  for (int i = 0; i < 10000; ++i) d.push_back(i);
  for (int i = 0; i < 10000; ++i) d.push_front(i);
  std::printf("%d\n", *p);   // 2: insertion at the ends does not invalidate references
}
```

After twenty thousand insertions, `p` still points to the original 2. `vector` cannot do this: growing moves the elements into new storage and leaves every old pointer dangling.

¶1 A `deque` supports random access iterators, and insertion and erasure at the beginning or end take constant time, in the middle linear time. ¶2 It meets the requirements of a container, reversible container, allocator-aware container and sequence container, including all the optional operations in [[sequence.reqmts]]: `front`, `back`, `push_front`, `push_back`, `emplace_front`, `emplace_back`, `prepend_range`, `append_range`, `pop_front`, `pop_back`, `operator[]` and `at`. `deque` is the only container in the standard library that provides all of them.

## The data structure the wording dictates

Paragraph 2 of the insertion subclause ([[deque.modifiers#2]]) is the key:

!!! std
    Inserting a single element at either the beginning or end of a deque always takes constant time and causes a single call to a constructor of T.

It says always constant time, not amortized constant; and exactly one constructor call, so existing elements cannot be moved. Together with the rule that insertion at the ends does not invalidate references, it follows that an element never moves once placed, and new elements can only go into newly allocated blocks. On the other hand, `operator[]` must be constant time, so there also has to be a table of block pointers (usually called the map) to locate which block holds the ith element.

```text
   map (table of block pointers; can grow, may leave free slots at both ends)
  ┌────┬────┬────┬────┬────┐
  │    │ b0 │ b1 │ b2 │    │
  └────┴─┬──┴─┬──┴─┬──┴────┘
         ▼    ▼    ▼
       [..xx][xxxx][xx..]       ← fixed-size element blocks; x is an element
          ▲              ▲
        begin           end
```

Every rule can be explained in terms of this structure:

- Insertion at an end constructs the element in a free slot of the first or last block; if there is none, it allocates a new block and registers it at one end of the map. A full map has to be reallocated, but that copies only block pointers, not elements. So references stay valid; iterators, however, hold a pointer to a map slot internally and are invalidated as soon as the map is reallocated.
- Growing the map copies O(number of blocks) pointers, which strictly speaking is not constant time. The standard's complexity counts only operations on elements ([[container.requirements.pre#2]]), so "always constant time" holds in terms of element operations.
- Insertion in the middle can only shift elements, so it is linear, and the implementation shifts the shorter side.

!!! impl
    libc++'s block size is `sizeof(T) < 256 ? 4096 / sizeof(T) : 16` elements, so a block of `deque<int>` holds 1024 `int`s. With Clang 23, `sizeof(std::deque<int>)` is 48. libstdc++ uses 512-byte blocks; MSVC STL's blocks are only 16 bytes, so for elements larger than 8 bytes each block holds a single element, which for large objects amounts to one allocation per element.

## Insertion [deque.modifiers]

¶1 The invalidation rules depend on the insertion position:

- Insertion in the middle invalidates all iterators and references to elements of the `deque`;
- insertion at either end invalidates all iterators but has no effect on the validity of references to elements.

This makes `deque` a good fit when you need stable element addresses and grow only at the ends, as in object pools or event queues. It uses less memory than `list` and is cache-friendlier, and unlike `vector` it never relocates elements when growing.

¶2 The complexity is linear in the number of elements inserted plus the lesser of the distances from the insertion point to the beginning and to the end. That is, when inserting near the beginning, the implementation shifts the front part forward rather than the back part backward.

¶3 Exception safety has three cases:

- If the exception is not thrown by `T`'s copy constructor, move constructor, copy assignment or move assignment: no effect;
- if it is thrown while inserting a single element at either end: no effect;
- otherwise, if it is thrown by the move constructor of a non-*Cpp17CopyInsertable* `T`: the effects are unspecified.

Compare [[vector]]: the strong guarantee of `vector::push_back` depends on `T` being copyable or having a non-throwing move constructor, because growing relocates the old elements. Insertion at either end of a `deque` never relocates old elements, so its strong guarantee is unconditional.

## Erasure

¶4 The invalidation rules depend on the erasure position:

| Elements erased | What is invalidated |
|---|---|
| Include the last element (e.g. `pop_back`) | Iterators and references to the erased elements, plus the past-the-end iterator |
| Include the first but not the last element (e.g. `pop_front`) | Only iterators and references to the erased elements |
| Neither the first nor the last | The past-the-end iterator, and all iterators and references to all elements |

Note 1 makes clear that `pop_front` and `pop_back` are erase operations too.

¶5 Erasure throws nothing unless `T`'s assignment operator throws. ¶6 The number of destructor calls equals the number of elements erased; the number of assignment operator calls is no more than the lesser of the number of elements before and after the erased elements, again shifting only the shorter side.

!!! pitfall "Thinking all iterators are invalidated after pop_front"
    Erasing the first element (when it is not also the last) invalidates only the erased element. When a `deque` is used as a FIFO queue, iterators to the remaining elements stay valid after `pop_front`. A subsequent `push_back`, however, invalidates all iterators.

## Capacity [deque.capacity]

¶1–¶4 `resize(sz)` and `resize(sz, c)`: shrinking erases the surplus elements at the end, growing appends default-inserted elements or copies of `c` at the end.

¶5–¶8 `shrink_to_fit()` is a non-binding request to reduce memory use without changing the number of elements. It has no effect if the size already equals the old capacity, or if an exception is thrown other than by the move constructor of a non-*Cpp17CopyInsertable* `T`. If shrinking actually happens, the complexity is linear, and all references, pointers and iterators, as well as the past-the-end iterator, are invalidated.

`deque` has no `capacity()` or `reserve()`; the capacity in paragraphs 6 to 8 is a concept internal to the specification. Not providing `reserve` is reasonable: insertion at the ends never relocates elements, so reserving space gains nothing.

!!! pitfall "Thinking deque is contiguous"
    `deque`'s iterators are random access iterators but not `contiguous_iterator`s. `&d[0] + i == &d[i]` holds only within a block; passing `&d[0]` to a C interface as a contiguous buffer makes any access beyond a block boundary {{ub}}.

## Construction and erase_if

The constructors in [deque.cons] match the general entries in [[sequence.reqmts]]: empty construction is constant, `deque(n)` and `deque(n, value)` are linear in n, and iterator-range and `from_range` construction are linear in the length of the range (¶1–¶12).

The non-member `erase` and `erase_if` in [deque.erasure] are equivalent to the `remove`/`remove_if` followed by `erase` idiom, as for [[vector]] (¶1–¶2).

## Relationship with the container adaptors

The default underlying container of both `std::stack` and `std::queue` is `deque` ([[container.adaptors]]). `queue` needs `push_back` and `pop_front`, and `vector` lacks the latter; `stack` uses only operations at the back, which `vector` could also handle. Defaulting to `deque` is inherited from C++98; its advantage is that growth never relocates elements and never causes a single huge reallocation.

!!! impl
    In the current draft every member of `deque` is `constexpr`, and its iterators meet the constexpr iterator requirements ([[deque.overview#3]]). libc++ in Clang 23 has not implemented this for `deque` yet: constructing a `deque` in a `consteval` function cannot be constant-evaluated.

## Questions

!!! question "Question"
    Does `d.insert(d.begin() + 1, x)` call `T`'s assignment operator? Which iterators and references remain valid afterwards?

<details markdown="1">
<summary>Answer</summary>

Usually yes, about once. The insertion point is only one element from the beginning, and [[deque.modifiers#2]] requires complexity linear in the number inserted plus the lesser distance to an end, so the implementation shifts that one element in front: it move constructs the original `d[0]` into the new first position, then assigns `x` into the slot where element 0 used to be. That is also why [[sequence.reqmts#25]] additionally requires `T` to be *Cpp17CopyAssignable* for `deque`'s `insert(p, t)`.

This is an insertion in the middle, so per [[deque.modifiers#1]] all iterators and references are invalidated, even though physically most elements did not move at all.
</details>
