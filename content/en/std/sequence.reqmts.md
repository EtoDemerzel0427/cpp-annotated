---
title: Sequence container requirements
summary: "The contract shared by vector, deque, list and the other sequence containers: preconditions and return values of construction, insert, emplace, erase and assign, which self-referencing arguments are allowed, why integers are not taken as iterators, and how front, back and operator[] became hardened preconditions in C++26."
updated: 2026-10-19
---

!!! tldr
    - Inserting into or erasing from the middle of a `vector`, `deque` or `inplace_vector` shifts existing elements, so these containers additionally require elements to be move-assignable, which `list` does not.
    - Single-element operations like `v.push_back(v[0])` and `v.insert(p, v.back())` may refer to the container's own elements; but `v.insert(p, v.begin(), v.end())`, using the container's own range as the source, is UB.
    - In range construction and insertion, each source iterator is dereferenced exactly once.
    - Optional operations such as `push_front` and `operator[]` are provided only by containers that can do them in amortized constant time, which is why `vector` has no `push_front` and `list` has no `operator[]`.
    - Since C++26, the preconditions of `front`, `back`, `pop_*` and `operator[]` are hardened preconditions, and a hardened implementation terminates the program on violation; `at` out of bounds throws `out_of_range`.

## What a sequence container is (¶1)

¶1 A **sequence container** organizes a finite set of objects of the same type into a strictly linear arrangement, where an element's position is determined by how it was inserted, not by its value. The library provides five basic sequence containers: `vector`, `inplace_vector`, `forward_list`, `list` and `deque`.

`array` and `hive` are sequence containers too, but provide only limited sequence operations: `array` has a fixed number of elements and cannot insert or erase; `hive` chooses the insertion position itself, so it has no "insert before p" operation.

The container adaptors `stack`, `queue`, `flat_map`, `flat_multimap`, `flat_set` and `flat_multiset` are built from the basic sequence containers, and ¶1 says they can also be built from program-defined sequence containers. So a container you write yourself can go into these adaptors as long as it meets the requirements in this subclause ([[container.adaptors]], [[flat.map]]).

The clauses for specific containers only add what this subclause does not say. For example, the full semantics of `vector::insert` are the entries here plus the rules of [vector.modifiers] in [[vector]].

## Notation (¶2–¶4)

¶2 sets out the notation, and a few items in it are easy to overlook:

- `A` denotes `X::allocator_type` if that name is valid and denotes a type, and `allocator<T>` otherwise. This lets containers that are not allocator-aware, such as `inplace_vector`, use terms like *Cpp17CopyInsertable* ([[container.requirements.general]]).
- `p` is a valid constant iterator into `a`, possibly `end()`; `q` is a dereferenceable constant iterator, which cannot be `end()`. So `erase(end())` violates a precondition.
- `[q1, q2)` is a valid range of constant iterators into `a`.
- `t` is an lvalue or `const` rvalue of `value_type`, and `rv` a non-`const` rvalue.

¶3 The complexities of the expressions are sequence-dependent: the entries in this subclause almost never state complexity; it is given in each container's clauses. ¶4 A type `X` meets the sequence container requirements if it meets the container requirements and the following statements and expressions are well-formed and have the specified semantics.

## Construction and assignment (¶5–¶19)

| Expression | Preconditions | Key points |
|---|---|---|
| `X u(n, t);` | Copy-insertable | ¶5–¶7 n copies of `t` |
| `X u(i, j);` | Emplace-constructible from `*i`; for `vector`, also move-insertable if the iterators do not meet the forward iterator requirements | ¶9 Each iterator is dereferenced exactly once |
| `X(from_range, rg)` | Same; for `vector`, also move-insertable if `rg` can only estimate its length (`approximately_sized_range` rather than `sized_range`) or is a single-pass range | ¶13 Recommended practice: if the estimated length `reserve_hint` is not less than the actual length, reallocate at most once |
| `X(il)` | | ¶15 Equivalent to `X(il.begin(), il.end())` |
| `a = il` | Copy-insertable and copy-assignable | ¶18 Existing elements are assigned to or destroyed |

Why does only `vector` require move-insertability for single-pass input iterators? A single-pass range cannot tell its length in advance, so `vector` can only append while reading, and growing midway moves the existing elements into a new buffer. With forward iterators it can compute `distance` first, allocate once, and then construct element by element without relocating.

"Each iterator is dereferenced exactly once" is a restriction on implementations. An implementation cannot walk an input range first just to find its length (single-pass iterators do not support walking twice anyway), nor dereference the same position more than once. For an iterator whose dereference has side effects, such as `istream_iterator`, one extra dereference means extra input is read.

The C++23 range interface generalizes these constructions to any `container-compatible-range`:

```cpp title="ranges-api.cpp" run ok
#include <vector>
#include <list>
#include <deque>
#include <ranges>
#include <cassert>

int main() {
  // C++23 range interface: from_range construction, append_range, prepend_range, insert_range
  auto squares = std::views::iota(1, 5) | std::views::transform([](int x) { return x * x; });
  std::vector<int> v(std::from_range, squares);           // {1, 4, 9, 16}
  std::deque<int> d;
  d.append_range(v);
  d.prepend_range(std::views::iota(-2, 0));               // order is not reversed: {-2, -1, 1, 4, 9, 16}
  std::list<int> l = d | std::ranges::to<std::list>();
  l.insert_range(std::next(l.begin()), std::views::single(0));
  assert((l == std::list<int>{-2, 0, -1, 1, 4, 9, 16}));
}
```

## Insertion and erasure (¶20–¶52)

### Why array-like containers require move-assignability

| Expression | Preconditions for all sequence containers | Additional requirements for `vector`, `inplace_vector`, `deque` |
|---|---|---|
| `a.emplace(p, args)` | Emplace-constructible from `args` | Move-insertable, move-assignable (¶21) |
| `a.insert(p, t)` | Copy-insertable | Copy-assignable (¶25) |
| `a.insert(p, rv)` | Move-insertable | Move-assignable (¶29) |
| `a.insert(p, n, t)` | Copy-insertable, copy-assignable (¶33, required for every container) | None |
| `a.insert(p, i, j)`, `a.insert_range(p, rg)` | Emplace-constructible from `*i` | Move-insertable, and `T` move-constructible, move-assignable and swappable (¶37, ¶41) |
| `a.erase(q)`, `a.erase(q1, q2)` | None | Move-assignable (¶46, ¶50) |

Inserting into the middle of an array-like container shifts the elements after the insertion point backwards. The newly added slots at the end held no objects before, so they are filled by move construction; the other slots already hold objects, so they get move assignment. Erasure is the reverse: assign the later elements forward, then destroy the surplus objects at the end. `list` only changes pointers, so it has none of these requirements.

Range insertion also requires swappability because implementations commonly append at the end first and then `rotate` into place, and `rotate` relies on `swap`.

### Return values

- ¶23, ¶27, ¶31 `emplace`, `insert(p, t)` and `insert(p, rv)` return an iterator to the new element.
- ¶35, ¶39, ¶43 `insert(p, n, t)`, `insert(p, i, j)` and `insert_range` return an iterator to the first new element, or `p` if nothing was inserted.
- ¶48 `erase(q)` returns an iterator to the element that immediately followed `q` before the erasure, or `end()` if there is none. ¶52 `erase(q1, q2)` returns an iterator to the element `q2` pointed to before the erasure.

So erasing while iterating is written `it = c.erase(it);`.

### Arguments that refer to the container's own elements

```cpp title="self-reference.cpp" run ok
#include <vector>
#include <string>
#include <cassert>

int main() {
  std::vector<std::string> v{"hello"};
  v.shrink_to_fit();                    // make the next push_back certain to reallocate
  v.push_back(v[0]);                    // OK: the implementation must construct the new element before freeing the old buffer
  v.emplace_back(v[1]);                 // OK: likewise (¶22 Note 1)
  v.insert(v.begin(), v.back());        // OK: t in insert(p, t) may refer to an element of the container
  assert(v.size() == 4 && v[0] == "hello" && v[3] == "hello");
}
```

¶22's Note 1 says the arguments of `emplace` can directly or indirectly refer to a value in `a`. `insert(p, t)` likewise has no precondition that "`t` shall not refer into `a`". So all three calls must work: the implementation has to construct the element in its new place before shifting or freeing the old elements.

The range forms are different: their preconditions explicitly exclude self-reference:

| Code | Verdict | Basis |
|---|---|---|
| `a.insert(p, i, j)` with `i`, `j` iterators into `a` | {{ub}} | ¶37: neither `i` nor `j` are iterators into `a` |
| `a.assign(i, j)`, same | {{ub}} | ¶58 |
| `a.insert_range(p, rg)`, `a.assign_range(rg)` where `rg` overlaps `a` | {{ub}} | ¶41, ¶62: `rg` and `a` do not overlap |
| `a.assign(n, t)` where `t` refers to an element of `a` | {{ub}} | ¶67: `t` is not a reference into `a` |
| `a.push_back(std::move(a[0]))` | The implementation may assume no aliasing | [[res.on.arguments#1]], item 3: for an argument bound to an rvalue reference parameter, the implementation may assume it is the only reference |

```cpp title="self-range.cpp" ub
#include <vector>

int main() {
  std::vector<int> v{1, 2, 3};
  v.insert(v.begin(), v.begin(), v.end());   // UB: i and j cannot be iterators into v
}
```

In our tests with libc++ (Clang 23), this code runs under ASan without errors and the result even looks right. That does not change the fact that it violates the precondition; with another implementation or another element type, it may read elements that have already been shifted.

### `clear` and `assign` (¶53–¶68)

- ¶54–¶56 `a.clear()` destroys all elements and invalidates all references, pointers and iterators referring to elements, and may invalidate the past-the-end iterator. Linear complexity.
- ¶59, ¶63, ¶68 `assign(i, j)`, `assign_range(rg)` and `assign(n, t)` replace the existing elements with new contents and invalidate all references, pointers and iterators referring to elements; for `vector` and `deque` they also invalidate the past-the-end iterator.
- ¶61 `assign_range` has a *Mandates*: `assignable_from<T&, range_reference_t<R>>` is modeled. For `inplace_vector`, if `ranges::size(rg)` is a constant expression it shall not exceed `max_size()`, so a range that does not fit is caught at compile time.

## Integers are not iterators (¶69)

The two arguments of `std::vector<int> v(5, 3)` have the same type, and the template constructor `X(InputIterator, InputIterator)` can deduce `InputIterator = int`. ¶69 specifies for every sequence container in Chapter 23 and Chapter 27 (strings):

- ¶69.1 The constructor `X(InputIterator first, InputIterator last, const allocator_type& = ...)` does not participate in overload resolution if `InputIterator` does not qualify as an input iterator.
- ¶69.2 Likewise for member function templates of the forms `F(p, first, last)` (such as `insert`), `F(first, last)` (such as `append`, `assign`) and `F(i1, i2, first, last)` (such as `replace`).
- ¶69.3 A deduction guide does not participate in overload resolution if it deduces an `InputIterator` that does not qualify as an input iterator or an `Allocator` that does not qualify as an allocator.

Paragraph 69 of [[container.requirements.general]] sets the minimum: integral types do not qualify as input iterators. So `std::vector<int> v(5, 3)` is five 3s, and so is `v.assign(5, 3)`.

## Optional operations (¶70–¶128)

¶70 The following operations are provided only by some sequence containers. Except for `prepend_range` and `append_range`, they must take amortized constant time. That also decides who provides them: a container that cannot do it in amortized constant time does not provide it. So `vector` has no `push_front`, `list` has no `operator[]`, and `forward_list` has neither `push_back` nor `back`.

| Operation | Preconditions | `vector` | `inplace_vector` | `deque` | `list` | `forward_list` | `array` | `basic_string` |
|---|---|---|---|---|---|---|---|---|
| `front()` | Hardened: `!empty()` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `back()` | Hardened: `!empty()` | ✓ | ✓ | ✓ | ✓ | | ✓ | ✓ |
| `emplace_front`, `push_front`, `prepend_range` | | | | ✓ | ✓ | ✓ | | |
| `emplace_back`, `append_range` | | ✓ | ✓ | ✓ | ✓ | | | |
| `push_back` | | ✓ | ✓ | ✓ | ✓ | | | ✓ |
| `pop_front()` | Hardened: `!empty()` | | | ✓ | ✓ | ✓ | | |
| `pop_back()` | Hardened: `!empty()` | ✓ | ✓ | ✓ | ✓ | | | ✓ |
| `operator[](n)` | Hardened: `n < size()` | ✓ | ✓ | ✓ | | | ✓ | ✓ |
| `at(n)` | Throws `out_of_range` when out of bounds | ✓ | ✓ | ✓ | | | ✓ | ✓ |

`basic_string` is not required to provide `emplace_back` and `append_range`; it has its own `append`.

Since C++17, `emplace_front` and `emplace_back` return a reference to the new element, equivalent to returning `a.front()` and `a.back()` respectively (¶82, ¶87). `inplace_vector::push_back` also returns a reference, which is its own rule ([[inplace.vector]]).

¶85 `emplace_back` requires move-insertability for `vector`, because growing moves the old elements into the new buffer by move construction. ¶80 `emplace_front` requires only emplace-constructibility: `deque` inserting at the front constructs the new element in an empty slot and never touches existing elements.

### Hardened preconditions

```cpp title="hardened-front.cpp" run ub
#include <vector>
int main() {
  std::vector<int> e;
  return e.front();   // violates a hardened precondition: a.empty() is true
}
```

C++26 standard library hardening ([[P3471R4]]) turned the preconditions of `front`, `back`, `pop_front`, `pop_back` and `operator[]` into *Hardened preconditions* (¶72, ¶76, ¶114, ¶118, ¶122). In a **hardened implementation** ([[g:hardened-implementation]]), violating them is checked as a contract violation with a terminating semantic; in a non-hardened implementation it is still {{ub}} ([[intro.compliance]], [[structure.specifications]]).

libc++ selects the mode with the macro `_LIBCPP_HARDENING_MODE`, whose values are `_LIBCPP_HARDENING_MODE_NONE`, `_FAST`, `_EXTENSIVE` and `_DEBUG`. In our tests: under `_EXTENSIVE` the program executes a trap instruction and terminates with no message; under `_DEBUG` it first prints *libc++ Hardening assertion !empty() failed: front() called on an empty vector* and then terminates.

`at(n)` has no precondition: out of bounds it throws `out_of_range` (¶127), and the behavior is defined. The two represent two error models: an out-of-bounds `operator[]` indicates a bug in the program, and a hardened implementation terminates; an out-of-bounds `at` is an error the caller anticipates and intends to catch.

## Common misconceptions

!!! pitfall "Appending a container's own range to its end is fine"
    `v.insert(v.end(), v.begin(), v.end())` violates ¶37 and is {{ub}}. Once it triggers a reallocation, `[i, j)` points into the freed buffer. Copy into a temporary container first, then `append_range`.

!!! pitfall "`erase(end())` does nothing"
    `erase(q)` requires `q` to be dereferenceable (the notation in ¶2), and `end()` is not dereferenceable, so this is {{ub}}. In `erase(q1, q2)`, `q1 == q2 == end()` is a valid empty range.

## Questions

!!! question "Question"
    Why does `deque::emplace(p, args)` require the element to be move-assignable while `deque::emplace_front` does not?

<details markdown="1">
<summary>Answer</summary>

`emplace(p, args)` inserts in the middle: `deque` shifts the elements on one side of the insertion point (the shorter side) by one slot, and shifting into slots that already hold objects uses move assignment, so ¶21 requires move-assignability for `vector`, `inplace_vector` and `deque`. `emplace_front` only constructs the new element in an empty slot at the front without touching existing elements (paragraph 2 of [deque.modifiers]: it calls a constructor of `T` exactly once), so ¶80 requires only emplace-constructibility.
</details>

## Summary

- The preconditions reflect the physical implementation: array-like containers (`vector`, `inplace_vector`, `deque`) need move assignment for insertion and erasure in the middle; node-based containers do not.
- Range construction and insertion: each iterator is dereferenced exactly once; the source range cannot refer into the container itself; `t` in `assign(n, t)` cannot refer into it either. Single-element `insert`, `push_back` and `emplace` may refer to the container's own elements.
- Optional operations are provided only by containers that can do them in amortized constant time.
- C++26: `front`, `back`, `pop_*` and `operator[]` have hardened preconditions; `at` out of bounds still throws.
