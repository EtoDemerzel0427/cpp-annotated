---
title: Class template hive
summary: "C++26's std::hive stores elements in a number of element blocks; the container chooses where to insert, insertion and erasure are both constant time, and neither ever moves other elements."
updated: 2026-10-19
---

!!! tldr
    - `hive` suits programs where many objects are created and destroyed frequently and refer to one another by pointer: element addresses are stable, and iteration is much faster than with `list`.
    - The container chooses the insertion position and may reuse slots left by erased elements; insertion invalidates only the past-the-end iterator, and erasure only the erased elements.
    - There is no `front`, `back`, `push_back` or `operator[]`, and no `==`; position hints given on insertion are always ignored.
    - `reserve` and `trim_capacity` never invalidate anything; `shrink_to_fit`, `reshape` and `sort` may move elements and scramble their order.
    - Block capacity limits that exceed the implementation's hard limits, and `x.splice(x)`, are erroneous behavior, not undefined behavior.

`std::hive` ({{c++26}}) comes from the object-pool pattern common in games, simulations and similar fields, also known as a bucket array. Such programs create and destroy large numbers of objects frequently, with objects referring to one another by pointer, so element addresses must be stable; at the same time they iterate over all objects often, so memory locality must be good.

`vector` shifts the following elements when erasing, so addresses are not stable; `list` allocates each element separately, so iteration jumps around in memory. `hive` compromises: elements live in a few large blocks, erasure merely marks a slot as empty to be skipped during iteration, and insertion fills those empty slots first.

!!! impl
    At the time of writing, libc++ in Clang 23 does not provide `<hive>`, and we had no other implementation available, so the code on this page has not been verified by compilation and carries no verdict.

```cpp title="hive-sketch.cpp"
#include <hive>

struct Particle { float x, y; Particle* target; };

void step(std::hive<Particle>& ps, Particle* dead) {
  // get an iterator back from the pointer, then erase; other elements keep their addresses
  ps.erase(ps.get_iterator(dead));
  // the container chooses the insertion position and may reuse the slot dead left behind
  auto it = ps.insert({0, 0, nullptr});
  for (Particle& p : ps) p.x += 1;   // iteration skips empty slots
  (void)it;
}
```

## Element blocks and skipping erasure [hive.overview]

¶1 A `hive` is a sequence container with constant-time insertion and erasure. Storage is managed automatically in multiple memory blocks, called **element blocks**. The container chooses where to insert, and insertion may reuse the memory locations of erased elements. Note 1 adds that construction and assignment are not considered insertion.

¶2 Blocks that contain elements are **active blocks**; blocks that contain none are **reserved blocks**. An active block that becomes empty is either deallocated or becomes a reserved block; a reserved block becomes active again when it stores an element. Calling `reserve` can create more reserved blocks.

¶3 Erasure marks the erased locations using an unspecified constant-time technique, so that they are skipped during later iteration, instead of shifting the following elements over. The reference implementation uses a skipfield that records the lengths of runs of empty slots, so an iterator can skip a whole run in one step.

¶4 The capacity of active blocks grows by an implementation-defined growth factor, which need not be an integer. For example, a new block's capacity could equal the sum of the capacities of the existing active blocks.

¶6 A `hive` meets the container requirements, except that it does not provide `==` and `!=`; it also meets the reversible container and allocator-aware container requirements, and some of the sequence container requirements. It does not provide `==` because the container decides the order of elements: two `hive`s with the same contents may iterate in different orders, so comparing element by element is meaningless, and comparing as multisets would be too expensive.

¶7 The iterators meet the *Cpp17BidirectionalIterator* requirements and also model `three_way_comparable<strong_ordering>`, so `<` can compare which of two iterators comes first.

### Block capacity limits (¶5)

Both the user and the implementation can set a minimum and maximum capacity for element blocks, expressed as `hive_limits{min, max}`:

- (5.1) The minimum limit shall be no larger than the maximum limit;
- (5.2) if the user does not specify limits at construction, the implementation's default limits are used;
- (5.3) the default limits are not necessarily the same as the smallest and largest block capacities the implementation can support, which are called its **hard limits**. The maximum hard limit shall be no larger than `allocator_traits<Allocator>::max_size()`;
- (5.4) if limits passed to a constructor or `reshape` lie outside the hard limits, or the minimum is greater than the maximum, the behavior is erroneous and the effects are implementation-defined. Note 3 points out that `is_within_hard_limits` can be used to check beforehand;
- (5.5) a block whose capacity is within [min, max] is said to be within the bounds of that pair of limits.

(5.4) uses C++26 **erroneous behavior** ([[intro.defs]]): the program is wrong, but the behavior is determinate and implementation-defined. An implementation may diagnose it, for example by terminating the program or throwing an exception, or clamp the limits into the valid range, but it may not assume it never happens as it could with UB.

## An interface that differs from vector

- Insertion takes no position argument: `insert(x)` and `emplace(args...)` return an iterator to the new element. The hint in `emplace_hint(hint, ...)` and `insert(hint, x)` is ignored (paragraphs 2 and 6 of [hive.modifiers]); they exist only for compatibility with generic code written for other containers.
- No `front`, `back`, `push_back` or `operator[]`, because the user does not control positions.
- An extra set of capacity-management functions: `capacity`, `reserve`, `shrink_to_fit`, `trim_capacity`, `block_capacity_limits` and `reshape`.
- A few extra operations: `splice`, `unique`, `sort` and `get_iterator`.
- Most members are not `constexpr`; only the constructors that create an empty `hive` and the functions related to `hive_limits` are.

## Construction and assignment [hive.cons]

Every constructor has a version that takes a `hive_limits`, used to initialize the exposition-only member *current-limits* (¶3, ¶6, ¶9 and so on).

¶16 Copy construction uses `x`'s *current-limits*. Copy assignment does not change *current-limits* (¶26 Note 1), much as `vector` assignment does not propagate `capacity`.

¶19 The move constructor, and the allocator-extended move constructor when the allocators are equal, move the element blocks from `x` wholesale and take over *current-limits* as well. Pointers, references and iterators keep referring to the same elements, which now belong to `*this`. This is constant time. With unequal allocators the elements can only be moved one by one; all iterators of `x` (including the past-the-end iterator) are invalidated, and it takes linear time (¶21). ¶20 In both cases `x` is empty afterwards, and the relative order of the elements is unchanged.

¶28–¶31 Move assignment has the exception specification `noexcept(POCMA || is_always_equal)`. If POCMA is true or the allocators are equal, it takes over the blocks wholesale along with *current-limits*; otherwise it moves the elements one by one.

## Capacity [hive.capacity]

| Member | Effect | Invalidation |
|---|---|---|
| `capacity()` | The total number of elements that can be held without allocating more element blocks (¶1) | None |
| `reserve(n)` | If `n > capacity()`, allocates reserved blocks so that afterwards `capacity() >= n`; throws `length_error` if above `max_size()` (¶3–¶6) | Everything stays valid, including the past-the-end iterator (¶7) |
| `shrink_to_fit()` | A non-binding request to bring `capacity()` close to `size()`; may reallocate elements (¶9) | If it reallocates, element order may change and everything is invalidated (¶11) |
| `trim_capacity()`, `trim_capacity(n)` | Deallocates all reserved blocks, or reduces capacity to no less than n; `noexcept` (¶12) | Everything stays valid (¶14) |
| `block_capacity_limits()` | Returns *current-limits* (¶15) | None |
| `block_capacity_default_limits()`, `block_capacity_hard_limits()` | Static functions returning the implementation's default limits and hard limits (¶17, ¶19) | None |
| `is_within_hard_limits(lim)` | `hl.min <= lim.min && lim.min <= lim.max && lim.max <= hl.max` (¶22) | None |
| `reshape(limits)` | Reallocates elements from active blocks not within the new limits into blocks that are, and deallocates the out-of-bounds blocks; `size()` is unchanged (¶24–¶25) | If it reallocates, order may change and everything is invalidated; otherwise everything stays valid (¶27) |

The difference between `trim_capacity` and `shrink_to_fit` is central to the design of `hive`. The former only deallocates empty blocks and never touches elements, so it invalidates nothing; the latter may move elements out of sparse blocks to compact memory, so it invalidates everything and scrambles the order. A program that relies on stable element addresses should use only `trim_capacity`.

## Insertion and erasure [hive.modifiers]

- ¶1–¶5 `emplace` and `emplace_hint`: require `T` to be emplace-constructible from `args`; no effect if an exception is thrown; constant time, exactly one construction of `T`; invalidate only the past-the-end iterator. Note 1 says `args` may refer to elements in `*this`.
- ¶6 Each `insert(x)` is equivalent to `emplace(std::forward<decltype(x)>(x))`.
- ¶7–¶10 `insert(il)` and `insert_range(rg)`: `rg` shall not overlap `*this`; each iterator in the range is dereferenced exactly once; linear time; invalidates the past-the-end iterator if elements were inserted.
- ¶11–¶15 `insert(n, x)` inserts n copies; `insert(first, last)` is equivalent to `insert_range(ranges::subrange(first, last))`.
- ¶16–¶17 `erase`: linear in the number of elements erased; if an active block becomes empty as a result, in the worst case there is additional time linear in the number of blocks, to unlink the empty block from the block chain. Only iterators, pointers and references to the erased elements are invalidated; when the last element is erased, the past-the-end iterator is invalidated too.
- ¶18–¶19 `swap`: exchanges the elements, `capacity()` and *current-limits*; constant time.

## Other operations [hive.operations]

¶1 Arguments named `Predicate` and `BinaryPredicate` must meet the requirements of the algorithms library; `i + n` and `i - n` mean `next(i, n)` and `prev(i, n)`; the definitions of [[alg.sorting]] apply to `sort`.

**splice** (¶2–¶6). The precondition is that the two `hive`s' allocators compare equal. If `addressof(x) == this`, the behavior is erroneous and there is no effect. Otherwise the active blocks of `x` are transferred into `*this`, leaving `x` empty, and pointers, references and iterators follow their elements; the reserved blocks of `x` are not transferred. If `x` has an active block that is not within the bounds of `*this`'s *current-limits*, `length_error` is thrown; if an exception is thrown there is no effect. The complexity is linear in the total number of blocks of both, not in the number of elements. The past-the-end iterators of both are invalidated.

**unique** (¶7–¶12). Keeps only the first element of each group of consecutive equivalent elements; the predicate is applied exactly `size() - 1` times; only the erased elements are invalidated, plus the past-the-end iterator if the last element is erased.

**sort** (¶13–¶16). Requires `T` to be move-insertable, move-assignable and swappable; O(N log N) comparisons; may allocate; references, pointers and iterators (including the past-the-end iterator) may all be invalidated; Note 1 says it is not required to be stable. This is the opposite of `list::sort`: `list` rearranges links, invalidates nothing and is stable; the elements of a `hive` sit in blocks, so sorting can only move values.

**get_iterator** (¶17–¶19). The precondition is that `p` points to an element in `*this`; it returns an iterator to the same element, with complexity linear in the number of active blocks, because it has to find which block `p` falls into. Objects store raw pointers to one another, and when one of them is to be erased, this is how its pointer is turned back into an iterator.

## erase and erase_if [hive.erasure]

¶1 The non-member `erase(c, value)` delegates to `erase_if`. ¶2 `erase_if(c, pred)` is specified as a loop calling `c.erase(i)` one at a time, not as `remove_if` followed by `erase`: `remove_if` would move element values around, destroying the address stability of `hive`.

## Comparison with other sequence containers

| | `vector` | `deque` | `list` | `hive` |
|---|---|---|---|---|
| Insertion position | Chosen by the user | Chosen by the user | Chosen by the user | Chosen by the container |
| Insertion invalidates other elements | All, on reallocation | Iterators yes, references no | No | No, only the past-the-end iterator |
| Erasure invalidates other elements | Everything after the erasure point | Depends on position | No | No |
| Separate allocation per element | No | No | Yes | No, allocated in blocks |
| Memory locality of iteration | Best | Good | Poor | Good, skipping empty slots |
| Random access | Yes | Yes | No | No |

<details class="fine" markdown="1"><summary>Remaining wording</summary>

The precondition of [[hive.modifiers#7]] says `T` is *Cpp17EmplaceInsertable* into hive, but the term defined in [container.alloc.reqmts] is *Cpp17EmplaceConstructible*; there is no *Cpp17EmplaceInsertable*. From context it should read as the latter; this is a typo awaiting an editorial fix.

</details>
