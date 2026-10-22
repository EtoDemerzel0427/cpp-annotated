---
title: "Container requirements: complexity, invalidation and exception-safety tables"
summary: "The three general rules of the container requirements (complexity counts only element operations, elements are constructed only through the allocator, which member functions count as const for data races), plus comparison tables of complexity, iterator invalidation and exception safety for every standard container."
updated: 2026-10-19
---

!!! tldr
    - Container complexity in the standard counts only operations on elements, but these requirements effectively dictate the data structure: `vector` grows geometrically, `deque` is built from blocks, `unordered_map` has one node per element.
    - Allocator-aware containers call `allocator_traits::construct` and `destroy` only for the element type, never for internal node types.
    - Several threads calling `begin`, `find`, `at` and the like at the same time do not cause a data race, but `operator[]` of an associative container may insert and does not count as read-only. Concurrently modifying different elements is not a data race either, except for `vector<bool>`.
    - The general principle of invalidation is that nothing is invalidated unless specified. For `vector` the question is whether it reallocates, for `deque` whether the operation is at an end; node-based containers invalidate only the erased elements, and insertion into an unordered container never invalidates references.
    - The default exception guarantee is that a throwing single-element insertion has no effect and erasure does not throw; `vector`, `deque` and some others have exceptions when the element's own operations throw.

```cpp title="invalidate.cpp" run ub
#include <vector>
#include <cstdio>

int main() {
  std::vector<int> v{1, 2, 3};          // capacity() == 3
  int& first = v[0];
  v.push_back(4);                       // new size exceeds capacity: reallocation
  std::printf("%d\n", first);           // UB: first refers into the freed old buffer
}
```

Run with `-fsanitize=address`, ASan reports `heap-use-after-free`. The `push_back` itself is entirely legal and violates no precondition; the UB comes from then accessing, through the invalidated reference, an object whose lifetime has ended ([[basic.life]]). To know whether an operation invalidates a reference you hold, you have to read the general requirements together with the clauses for the specific container; the tables on this page are the result of combining them.

The parts of [container.requirements] are spread across these pages:

| Subclause | Contents | Notes |
|---|---|---|
| [container.requirements.pre] | Three general rules | This page |
| [container.requirements.general] | Four sets of requirements: container, reversible container, optional operations, allocator-aware container | [[container.requirements.general]] |
| [container.requirements.dataraces] | Which member functions count as `const` for data races | This page |
| [sequence.reqmts] | Sequence container requirements | [[sequence.reqmts]] |
| [container.node], [container.insert.return] | Node handles and `insert_return_type` | [[container.node]] |
| [associative.reqmts] | Ordered associative container requirements | [[associative.reqmts]] |
| [unord.req] | Unordered associative container requirements | [[unord.req]] |

These are **named requirements** ([[structure.requirements]]): written conventions about a set of expressions and their semantics, not C++20 concepts, and the compiler does not check them. Violating them is generally a precondition violation, that is {{ub}}, not a compile error.

## Three general rules [container.requirements.pre]

### Containers control the lifetime of their elements (¶1)

¶1 Containers are objects that store other objects, and they control the allocation and deallocation of those objects through constructors, destructors, insert and erase operations. An element's lifetime ([[basic.life]]) is entirely up to the container, so the question of when a reference, pointer or iterator you hold still refers to a live object is exactly what the invalidation rules answer.

### Complexity counts only operations on elements (¶2)

!!! std
    All of the complexity requirements in this Clause are stated solely in terms of the number of operations on the contained objects.

¶2 The complexity requirements of this chapter count only the number of operations performed on the contained objects. Example 1: the copy constructor of `vector<vector<int>>` has linear complexity: it performs one copy construction for each of the n outer elements; that each of those copies is linear internally is not counted.

The complexity requirements do not constrain the number of memory allocations unless a clause says so separately. The amortized constant time of `vector::push_back` is in terms of the number of constructions of `T`. It still forces implementations into geometric growth, because reallocation moves every element into the new buffer: if each reallocation added only a constant number of slots, the total number of moves would be quadratic.

The complexity requirements also rule out some implementations:

| Complexity requirement | What it rules out |
|---|---|
| `size()` is constant ([[container.reqmts#54]]) | `list::size()` cannot count by traversal. That is why, since C++11, `splice` of a range between two `list`s is linear: it has to count how many elements were moved ([[list]]) |
| Insertion at either end of a `deque` is constant and calls exactly one constructor of `T` ([[deque]]) | `deque` cannot be implemented as a ring buffer that grows by relocating |
| Rehashing an unordered container does not invalidate pointers and references ([[unord.req#9]]) | The hash table cannot use open addressing; it must have one node per element |
| `swap` is constant and does not move, copy or swap any element ([[container.reqmts#50]], [[container.reqmts#65]]) | Except for `array` and `inplace_vector`, swapping can only exchange internal pointers (plus the allocator, comparator and so on) |

### Elements are constructed only through the allocator (¶3)

¶3 Allocator-aware containers other than `basic_string` construct elements with `allocator_traits<A>::rebind_traits<U>::construct` and destroy them with `...::destroy` ([[allocator.traits]]), where `U` is either `value_type` or an internal type of the container. These functions are called only for the container's element type, not for internal types.

Note 1 spells out the consequence: a node-based container such as `list` or `map` cannot `construct` a node; it must first allocate node memory that contains an aligned buffer and then call `construct` for the element inside that buffer. This way `scoped_allocator_adaptor` ([[allocator.adaptor]]) and the uses-allocator construction of `polymorphic_allocator` ([[allocator.uses]]) see the construction of every element, and only of elements.

{{impl}} Using a counting allocator, we measured libc++'s node sizes with Clang 23: `std::map<int,int>` uses 40 bytes per node (left, right and parent pointers, a color flag, plus 8 bytes of `pair<const int,int>`), `std::list<int>` 24 bytes and `std::forward_list<int>` 16 bytes.

## Data races: which member functions count as const [container.requirements.dataraces]

Is it a data race ([[intro.races]]) for two threads to call `v.begin()` at the same time? The library's general rule [[res.on.data.races]] says that a standard library function may modify objects through non-`const` arguments and may only read through `const` arguments. The non-`const` `begin()` receives a non-`const` `*this`, so under the general rule it might modify `v`.

¶1 Hence this subclause says specifically: for purposes of avoiding data races, implementations shall consider `begin`, `end`, `rbegin`, `rend`, `front`, `back`, `data`, `find`, `lower_bound`, `upper_bound`, `equal_range` and `at` to be `const`, and `operator[]` as well, except in associative and unordered associative containers.

`map::operator[]` is excluded because it inserts when the key is absent, which really is a modification. Several threads reading a shared `map` should use `find`, `at` or `contains`. This rule only guarantees that the container's own structure is race-free; reading and writing the same element through the returned references is still judged by [[intro.races]].

¶2 Notwithstanding [[res.on.data.races]], concurrently modifying the contained objects of different elements in the same container does not cause a data race, except for `vector<bool>`. The note in ¶3 gives the contrast:

```cpp title="dataraces.cpp" run ok
#include <thread>
#include <vector>

int main() {
  std::vector<int> x(2);
  std::thread t1([&] { x[1] = 5; });
  std::thread t2([&] { *x.begin() = 10; });   // different elements: no data race
  t1.join(); t2.join();
  return x[0] == 10 && x[1] == 5 ? 0 : 1;
}
```

For a `vector<bool> y`, executing `y[0] = true` and `y[1] = true` concurrently may be a data race: both bits sit in the same word, and writing one bit is a read-modify-write of the whole word ([[vector.bool]]).

## Table 1: structure and complexity

n is the number of elements.

| Container | Iterator category | Contiguous | Allocator-aware | Insertion at front/back | Insertion and erasure in the middle | Lookup | Source |
|---|---|---|---|---|---|---|---|
| `array<T,N>` | Random access | Yes | No | Cannot insert | Cannot insert | | [[array]] |
| `vector<T>` | Random access | Yes (`T` is not `bool`) | Yes | Amortized O(1) at the back | O(distance to the end) | | [[vector]] |
| `vector<bool>` | Random access (proxy reference) | No | Yes | Amortized O(1) at the back | Same as above | | [[vector.bool]] |
| `inplace_vector<T,N>` {{c++26}} | Random access | Yes | No | O(1) at the back; throws `bad_alloc` when full | O(distance to the end) | | [[inplace.vector]] |
| `deque<T>` | Random access | No | Yes | O(1) at both ends, exactly one construction | O(distance to the nearer end) | | [[deque]] |
| `list<T>` | Bidirectional | No | Yes | O(1) | O(1) | | [[list]] |
| `forward_list<T>` | Forward | No | Yes | O(1) at the front | O(1) (`insert_after`) | | [[forward.list]] |
| `hive<T>` {{c++26}} | Bidirectional | No | Yes | Position chosen by the container, O(1) | Erasure O(1); worst case O(number of blocks) when a block becomes empty | | [[hive]] |
| `set`, `map` and the multi versions | Bidirectional | No | Yes | O(log n); amortized O(1) when the new element goes right before the hint | O(log n); erasure by iterator amortized O(1) | O(log n) | [[associative.reqmts]] |
| `unordered_*` | At least forward | No | Yes | Average O(1), worst O(n) | Average O(1), worst O(n) | Average O(1), worst O(n) | [[unord.req]] |

A few complexity rules are outside the table:

- Except for `array` and `inplace_vector`, every container's move constructor and `swap` are constant ([[container.reqmts#16]], [[container.reqmts#50]]).
- `forward_list` does not provide `size()` ([[forward.list]]).
- `list::splice` of a range is constant within the same `list` and linear across `list`s.
- Constructing an associative container from a sorted range is linear ([[associative.reqmts#25]]).

## Table 2: invalidation of iterators, pointers and references

The "references" column also covers pointers; the standard always lists the two together. "end" means the past-the-end iterator. Keep two general rules in mind when reading the table:

- [[container.reqmts#67]]: unless otherwise specified (either explicitly or by defining a function in terms of other functions), invoking a container member function or passing a container as an argument to a library function does not invalidate iterators to, or change the values of, objects within that container. So operations not listed in the table (`size`, `find`, `begin` and so on) never invalidate anything.
- [[container.reqmts#66]], item 6: except for `array` and `inplace_vector`, `swap` invalidates no references, pointers or iterators referring to elements; they now refer to the same elements in the other container. `end()` refers to no element, so it may be invalidated; ¶65 says it is unspecified whether `a.end()` before the swap equals `b.end()` after it.

### Sequence containers

| Container | Operation | Iterators invalidated | References invalidated | Source |
|---|---|---|---|---|
| `vector` | Insertion (`push_back`, `emplace`, `insert`, `append_range`, growing `resize`) that reallocates | All, including end | All | [[vector.modifiers#2]] |
| `vector` | Insertion without reallocation | At and after the insertion point, including end | At and after the insertion point | [[vector.modifiers#2]] |
| `vector` | `erase`, `pop_back`, shrinking `resize` | At and after the erasure point, including end | At and after the erasure point | [[vector.modifiers#4]] |
| `vector` | `reserve`, `shrink_to_fit` that reallocates | All, including end | All | [[vector.capacity#7]], [[vector.capacity#11]] |
| `deque` | Insertion at either end | All, including end | None | [[deque.modifiers#1]] |
| `deque` | Insertion in the middle | All | All | [[deque.modifiers#1]] |
| `deque` | Erasing the last element (e.g. `pop_back`) | The erased element and end | The erased element | [[deque.modifiers#4]] |
| `deque` | Erasing the first element but not the last (e.g. `pop_front`) | The erased element | The erased element | [[deque.modifiers#4]] |
| `deque` | Erasing elements that are neither first nor last | All, including end | All | [[deque.modifiers#4]] |
| `deque` | `shrink_to_fit` (when size differs from the old capacity) | All, including end | All | [[deque.capacity#8]] |
| `list` | Any insertion | None | None | [[list.modifiers#2]] |
| `list` | Erasure, `remove`, `unique` | The erased elements | The erased elements | [[list.modifiers#3]], [[list.ops]] |
| `list` | `splice`, `merge`, `sort`, `reverse` | None; iterators to moved elements now belong to the target `list` | None | [[list.ops]] |
| `forward_list` | Insertion, erasure, `splice_after`, `merge`, `sort`, `reverse` | Same as `list`; `clear()` does not invalidate end | Same as `list` | [[forward.list.modifiers#1]], [[forward.list.modifiers#38]] |
| `array` | No operation invalidates; `swap` exchanges values, and iterators still refer to the original `array` | None | None | [[array.members#5]] |
| `inplace_vector` | `erase`, `pop_back` | At and after the erasure point | At and after the erasure point | [[inplace.vector.modifiers#19]] |
| `inplace_vector` | Insertion | Not stated explicitly in the draft. Storage is inside the object and never moves, but positions after the insertion point now hold the shifted values | Same | [[inplace.vector]] |
| `hive` | `insert`, `emplace`, `insert_range` | Only end | None | [[hive.modifiers#5]], [[hive.modifiers#10]], [[hive.modifiers#14]] |
| `hive` | Erasure | The erased elements; also end when the last element is erased | The erased elements | [[hive.modifiers#17]] |
| `hive` | `reserve`, `trim_capacity` | None | None | [[hive.capacity#7]], [[hive.capacity#14]] |
| `hive` | `shrink_to_fit`, `reshape`, `sort` that reallocates | All, including end; the order of elements may change too | All | [[hive.capacity#11]], [[hive.capacity#27]], [[hive.operations#16]] |
| All sequence containers | `clear()` | All elements, and may invalidate end | All | [[sequence.reqmts#54]] |
| All sequence containers | `assign`, `assign_range` | All elements; for `vector` and `deque` also end | All | [[sequence.reqmts#59]], [[sequence.reqmts#63]], [[sequence.reqmts#68]] |

### Associative and unordered containers

| Container | Operation | Iterators invalidated | References invalidated | Source |
|---|---|---|---|---|
| `set`, `map` and the multi versions | `insert`, `emplace`, `insert_range` | None | None | [[associative.reqmts#175]] |
| Same | `erase` | The erased elements | The erased elements | [[associative.reqmts#175]] |
| Same | `extract` | The extracted element | Not invalidated, but accessing the element through them while a node handle owns it is UB; references obtained during that time are invalidated once the element is successfully inserted | [[associative.reqmts#176]] |
| Same | `merge` | Not invalidated; when the iterator types are the same, iterators to transferred elements now belong to the target container | Not invalidated | [[associative.reqmts#115]] |
| `unordered_*` | `insert`, `emplace`, `insert_range` | All if a rehash happens; no rehash is guaranteed when (N+n) ≤ z·B | Never | [[unord.req#242]], [[unord.req#243]] |
| Same | `rehash`, `reserve` | All | None | [[unord.req#9]] |
| Same | `erase` | The erased elements | The erased elements | [[unord.req#242]] |
| Same | `extract` | The extracted element | Same as ordered associative containers | [[unord.req#244]] |
| Same | `merge` | Iterators to transferred elements, and all iterators of the target container | Not invalidated | [[unord.req#146]] |

In the table, N is the number of elements before the insertion, n the number inserted, B the bucket count and z the maximum load factor. For container adaptors such as `flat_map`, invalidation depends on the underlying sequence containers; see [[flat.map]].

## Table 3: exception safety

[[container.reqmts#66]] gives the default guarantees, and the clauses for individual containers carve out exceptions:

| Default guarantee in ¶66 | Meaning | Exceptions |
|---|---|---|
| ¶66.1 A single-element `insert` or `emplace` that throws has no effect | Strong guarantee | Insertion into `vector`, `deque` and `inplace_vector` is not covered when `T`'s own copy, move or assignment throws; unordered containers are not covered when the hash function throws |
| ¶66.2 `push_back`, `push_front`, `emplace_back`, `emplace_front` that throw have no effect | Strong guarantee | `vector` guarantees it only if `T` is copy-insertable or `is_nothrow_move_constructible_v<T>` |
| ¶66.3 `erase`, `clear`, `pop_back`, `pop_front` do not throw | No-throw | `erase` of `vector`, `deque` and `inplace_vector` may throw from `T`'s assignment; `erase(k)` of associative and unordered containers may throw from comparison or hashing |
| ¶66.4 Copy construction and assignment of returned iterators do not throw | No-throw | None |
| ¶66.5 `swap` does not throw | No-throw | `array`, `inplace_vector`; `swap` of associative and unordered containers may throw from the `swap` of `Compare`, `Hash` or `Pred` |

The insertion guarantee of each container:

| Container | Guarantee on insertion | Source |
|---|---|---|
| `vector` | No effect if the exception is thrown by something other than `T`'s copy constructor, move constructor, assignment or move assignment, or an operation of an input iterator. For a single element inserted at the end: no effect if `T` is copy-insertable or its move constructor does not throw; otherwise, if the exception comes from the move constructor of a non-copyable `T`, the effects are unspecified | [[vector.modifiers#2]] |
| `vector::reserve`, `shrink_to_fit`, `resize` | No effect, unless the move constructor of a non-copyable `T` throws | [[vector.capacity]] |
| `deque` | A single-element insertion at either end that throws has no effect; no non-throwing move constructor is needed, because `deque` never moves existing elements | [[deque.modifiers#3]] |
| `list`, `forward_list` | Any insertion that throws has no effect, range insertions included | [[list.modifiers#2]], [[forward.list.modifiers#1]] |
| `inplace_vector` | `push_back`, `emplace_back` and the `try_*` family have no effect; when `insert` throws from an operation of `T`, `size()` is not less than n and the first n elements are unchanged | [[inplace.vector.modifiers]] |
| `hive` | `emplace` and `insert` have no effect if they throw | [[hive.modifiers#2]] |
| Ordered associative containers | Single-element insertion has no effect; `clear` does not throw; `erase(k)` can throw only from `Compare` | [[associative.reqmts]] |
| Unordered associative containers | For single-element insertion, no effect if an operation other than the hash function throws; for `rehash`, no effect if an operation other than hashing and comparison throws | [[unord.req]] |

The `vector` row explains what `std::move_if_noexcept` is for: on reallocation, if `T`'s move constructor may throw and `T` is copyable, the implementation must copy the old elements, so that the old buffer is still intact if something fails partway. See [[vector]] for details.

## Common misconceptions

!!! pitfall "`deque::push_back` invalidates nothing"
    It invalidates no references, but it invalidates all iterators, including those to untouched elements. A `deque` iterator holds a pointer into the table of block pointers, and inserting at either end can reallocate that table.

!!! pitfall "Inserting into an `unordered_map` is safe as long as there is no rehash"
    For references it is safe regardless of rehashing: insertion never invalidates references. For iterators, the only reliable way to know there will be no rehash is the condition (N+n) ≤ z·B in [[unord.req#243]], and calling `reserve` beforehand exists to satisfy it.

!!! pitfall "`end()` is still usable after `clear()`"
    [[sequence.reqmts#54]] says `clear()` may invalidate the past-the-end iterator. Only `forward_list::clear()` explicitly guarantees not to invalidate it ([[forward.list.modifiers#38]]).

## Questions

!!! question "Question 1"
    Why can't `std::unordered_map` be implemented with open addressing?

<details markdown="1">
<summary>Answer</summary>

[[unord.req#9]] says rehashing does not invalidate pointers and references to elements, and [[unord.req#242]] says insertion does not affect the validity of references. Open addressing stores elements directly in an array of slots, and growing it moves the elements into a new array, invalidating every reference. To meet both rules, each element needs its own stable address, that is, a separately allocated node. Node handles ([[container.node]]) also require that `extract` and `insert` can transfer an element together with its storage to another container. So an open-addressing hash table like Abseil's `flat_hash_map` cannot serve as an implementation of `std::unordered_map`.
</details>

!!! question "Question 2"
    Two threads call `m[1]` and `m.find(2)` respectively on the same `std::map<int,int> m`. Even if key 1 already exists, is this a data race?

<details markdown="1">
<summary>Answer</summary>

By the standard, yes. [[container.requirements.dataraces#1]] explicitly excludes `operator[]` of associative containers from the functions considered `const`. `m[1]` is a call that modifies `m`; it conflicts with the other thread's access to `m` and, per [[intro.races]], is a data race with undefined behavior, even if this particular call happens not to insert. Reader threads should use `find`, `at` or `contains`.
</details>

## Summary

- Complexity counts only element operations, but in effect it decides each container's data structure.
- Elements are constructed and destroyed only through `allocator_traits::construct` and `destroy`, and only for the element type.
- `begin`, `end`, `front`, `back`, `data`, `find`, `at` and the like are considered `const`; `operator[]` of associative containers is not. Different elements may be modified concurrently, except in `vector<bool>`.
- Nothing is invalidated unless specified; `swap` makes iterators follow their elements.
- Default exception guarantees: strong for single-element insertion, no-throw for erasure; `vector`, `deque` and `inplace_vector` are exceptions when the element's own operations throw.
