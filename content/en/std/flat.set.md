---
title: flat_set and flat_multiset
summary: "Set containers that keep their keys in one sorted array; most rules are the same as for flat_map, the differences being a single underlying container, iterators that dereference to genuine const references, and no member functions for observing the underlying container."
updated: 2026-10-19
---

!!! tldr
    - `flat_set` stores all keys in one sorted sequence container (`vector<Key>` by default). Single-element insertion is linear time, iterator invalidation follows the underlying container, and after an exception only the invariants are guaranteed to be restored, all as with [[flat.map]].
    - Its iterators are constant iterators, and `*it` is a genuine `const Key&`, not a proxy as with `flat_map`.
    - The constructor from a container is `explicit`: `flat_set<int> s = vec;` does not compile, because the conversion sorts and deduplicates.
    - There is no observer like `keys()`; the underlying container can only be taken out with `std::move(s).extract()` and put back with `replace()`.
    - `flat_multiset` does not deduplicate, and its `emplace` inserts the new element at the end of the equivalent elements.

## A set on one sorted array

```cpp run title="flat-set-basics.cpp" ok
#include <flat_set>
#include <string>
#include <string_view>
#include <vector>
#include <iterator>
#include <cassert>
#include <type_traits>

int main() {
  std::flat_set<std::string, std::less<>> s{"pear", "apple", "fig", "apple"};
  assert(s.size() == 3 && *s.begin() == "apple");       // sorted and deduplicated on construction

  using namespace std::literals;
  auto [it, ok] = s.insert("kiwi"sv);                     // heterogeneous insert: constructs a string only if absent
  assert(ok && *it == "kiwi");
  static_assert(std::is_same_v<std::iter_reference_t<decltype(s)::iterator>,
                               const std::string&>);      // constant iterator

  std::vector<std::string> raw = std::move(s).extract(); // take out the underlying sorted vector
  assert(s.empty() && raw.size() == 4);                   // guaranteed empty after extract

  std::flat_multiset<int> ms{3, 1, 3, 2};
  auto pos = ms.emplace(3);                               // multiset's emplace returns an iterator
  assert(ms.count(3) == 3 && pos == std::prev(ms.end()));  // inserted at the end of the equivalent elements
}
```

`std::flat_set` ({{c++23}}, [[P1222R4]]) provides the interface of `std::set` with a sorted sequence container as storage. Lookup is a binary search, iteration a linear scan. It shares the design of [[flat.map]], and the following rules are exactly the same; see that page for details:

- Single-element insertion and erasure are linear time; bulk insertion appends, sorts, merges and deduplicates.
- Iterator invalidation depends on the underlying container (the general rule of [[container.adaptors]]).
- After a member function throws, only the invariants are guaranteed to be restored, and the container may be emptied.
- It is not an allocator-aware container, but the standard specializes `uses_allocator`, so it takes part in uses-allocator construction.
- The `sorted_unique` tag ([[g:sorted-unique]]) is a promise made to the library; data that does not keep it is UB.
- `extract() &&` takes the underlying container out wholesale, and `replace()` puts it back wholesale.

## Differences from flat_map

| | `flat_map` | `flat_set` |
|---|---|---|
| Underlying containers | Two: `KeyContainer`, `MappedContainer` | One: `KeyContainer`, member type name `container_type` |
| `value_type` | `pair<Key, T>` | `Key` |
| `*it` | Proxy `pair<const Key&, T&>` | `const Key&` |
| Cpp17 iterator requirements | Only *Cpp17InputIterator* | The standard only says it models `random_access_iterator` |
| `value_compare` | A nested class comparing only `.first` | Simply `Compare` |
| `size_type` | `size_t` | `KeyContainer::size_type` |
| Observing the underlying container | `keys()`, `values()` | None |
| Invariants | Equal length, sorted, corresponding by offset | Only sorted |
| UB preconditions | Containers of unequal length; `sorted_unique` data unsorted or with duplicates | Only the latter |

### The iterators are constant iterators

The elements of a `flat_set` are its keys, and modifying an element could break the ordering. [[associative.reqmts]] says that for associative containers whose value type is the same as the key type, both `iterator` and `const_iterator` are constant iterators. `flat_set` meets the associative container requirements and this point is not among the exceptions, so:

```cpp run title="flat-set-const-iter.cpp" error
#include <flat_set>

int main() {
  std::flat_set<int> s{1, 2, 3};
  *s.begin() = 0;   // error: cannot modify a key through a constant iterator
}
```

The member type `reference` is defined as `value_type&`, without const, yet the type of `*it` is `const Key&`. This is the same as for `std::set`: in the container requirements table `X::reference` is just an alias for `T&`, and the constness comes from the stronger requirement that the iterators be constant iterators.

In libc++ (Clang 23), `flat_set<int>::iterator` and `const_iterator` are the same type, as they are for `std::set`. The class definition therefore adds `requires (!same_as<iterator, const_iterator>)` to `erase(iterator)`, so that it does not become a duplicate declaration of `erase(const_iterator)`.

`*it` is a genuine reference: there really is a `Key` object in memory. So `flat_set` has none of the problems of proxy references, and `for (auto x : s)` copies the key itself.

### No keys()

`flat_map` exposes its underlying containers as `const&` through `keys()` and `values()`; `flat_set` has no corresponding member. To hand the underlying array to an interface that accepts only `const vector<Key>&`, you have to take it out with `std::move(s).extract()` and `replace` it afterwards, or pass an iterator range.

Nor can the iterator range be used as contiguous memory. The standard promises only `random_access_iterator`, and libc++ (Clang 23) does not mark the iterator as `contiguous_iterator` even when the underlying container is a `vector`. So code like `std::to_address(s.begin())` or `std::span(s.begin(), s.end())` does not work.

## Overview ([flat.set.overview])

¶1 A `flat_set` is an associative container with unique keys, supporting fast retrieval of the keys themselves. Its iterators model `random_access_iterator`.

¶2 It meets the requirements of a container, reversible container, the optional container requirements and the associative container requirements, with the same exceptions as `flat_map`: it does not meet the node handle requirements or the iterator invalidation requirements, and single-element insertion and erasure take linear time. Note 1: it does not meet the additional requirements of an allocator-aware container.

¶3 It supports the *a_uniq* operations and not the *a_eq* operations; `key_type` and `value_type` are both `Key`.

¶4 Only operations not in the requirements table, or needing additional semantics, are described.

¶5 There is only one invariant: the keys are sorted with respect to the comparison object.

¶6 If a member function exits via an exception, the invariants of `*this` are restored; move construction and move assignment restore the invariants of both objects. Note 2: this may result in the container being emptied.

¶7 Any sequence container supporting *Cpp17RandomAccessIterator* can be used; the standard names `vector` and `deque`. Note 3: `vector<bool>` is not a sequence container. Compared with [[flat.map#7]], the requirement that `size` and `max_size` not throw is missing here, perhaps because with only one container there is no need to compare the lengths of two containers when restoring the invariants.

¶8 If `Key` differs from `KeyContainer::value_type`, the program is {{ill-formed}}.

¶9 Calling a member function taking `sorted_unique_t` with a range that is unsorted or contains equal elements has undefined behavior.

¶10 `iterator` and `const_iterator` meet the constexpr iterator requirements.

With only one container, exception recovery is also much simpler. The underlying `vector::insert` itself has the strong guarantee when the element type is copyable or its move does not throw, so `flat_set::insert` can often naturally have no effect on failure. But what the standard promises is still only the invariant restoration of ¶6.

## Construction ([flat.set.defn], [flat.set.cons], [flat.set.cons.alloc])

[flat.set.cons] ¶1 `flat_set(container_type cont, const key_compare& comp = key_compare())` moves `cont` in, sorts by *compare*, and then keeps only the first of each group of consecutive equivalent elements. ¶2 Linear if `cont` is already sorted, N log N otherwise.

This constructor is `explicit`. `flat_map`'s two-container constructor does not need `explicit`, because it takes at least two arguments and could never take part in an implicit conversion anyway. `flat_set` needs just one argument, and `explicit` prevents a `vector<int>` from being silently converted into a `flat_set<int>`, with sorting and deduplication along the way:

<div class="compare" markdown="1">

```cpp run ok
#include <flat_set>
#include <vector>
// direct-initialization; the result is {1, 2, 3}
std::flat_set<int> s(
    std::vector<int>{3, 1, 2});
```

```cpp run error
#include <flat_set>
#include <vector>
// error: copy-initialization cannot use an explicit constructor
std::flat_set<int> s =
    std::vector<int>{3, 1, 2};
```

</div>

The `sorted_unique` iterator-pair constructor given directly in the class definition differs from `flat_map`'s in one respect:

```cpp
template<class InputIterator>
  constexpr flat_set(sorted_unique_t, InputIterator first, InputIterator last,
                     const key_compare& comp = key_compare())
    : c(first, last), compare(comp) { }
```

`flat_set` constructs the underlying container directly from `(first, last)`, whereas `flat_map`'s corresponding version calls `insert(sorted_unique, first, last)`, whose effect per the wording is equivalent to an ordinary bulk insertion. So passing unsorted data to `flat_set` yields an object that violates its invariant immediately; what happens when passing unsorted data to `flat_map` depends on whether the implementation really skips the sort. In the standard, both cases are UB.

[flat.set.cons.alloc] ¶1 The allocator-extended constructors participate in overload resolution only if `uses_allocator_v<container_type, Alloc>` is true. ¶2–¶6 They are equivalent to the corresponding versions without an allocator, except that the underlying container is created by uses-allocator construction ([[allocator.uses.construction]]). ¶5 The `sorted_unique` version with an allocator is linear time, because the `const&` parameter must be copied.

## Modifiers ([flat.set.modifiers])

¶1–¶4 The heterogeneous `insert(K&& x)` and `insert(hint, K&& x)` are overloads only set-like containers have; in the current draft `std::set` has them too. `flat_map` has no counterpart, because insertion there also needs a value.

- Constraints: the comparator is transparent (`Compare::is_transparent` exists), and `value_type` is constructible from `K`.
- Precondition: the object `u` obtained by converting `x` satisfies `find(x) == find(u)`.
- Effects: if an equivalent element exists, neither `*this` nor `x` is changed; otherwise as if by `emplace(std::forward<K>(x))`.

Its point is to construct a `Key` only when an insertion really happens. The opening example checks for duplicates with a `string_view` and allocates a `string` only if it is absent.

| Paragraph | Member | Specification |
|---|---|---|
| ¶5–¶7 | `insert(first, last)` | Appends at the end, sorts the new elements, merges with the existing part, keeps only the first of each group of equivalent elements; N + M log M; the in-place merge may allocate |
| ¶8–¶9 | `insert(sorted_unique, first, last)` | Equivalent to `insert(first, last)`; linear |
| ¶10–¶14 | `insert_range(rg)`, `insert_range(sorted_unique, rg)` | Same as above |
| ¶15 | `swap` | Swaps the comparator and the container; `noexcept` if both are nothrow-swappable |
| ¶16–¶17 | `extract() &&` | Postcondition: `*this` is emptied, even if the function exits via an exception; returns `std::move(c)` |
| ¶18–¶19 | `replace(container_type&& cont)` | Precondition: `cont` is sorted with respect to *compare* and contains no equal elements; effect `c = std::move(cont)` |

`emplace`, `erase`, `find` and the rest are not described separately here; per ¶4 the specifications of [[associative.reqmts]] apply, except that the complexity becomes linear (¶2.3).

## erase_if ([flat.set.erasure])

¶1 Precondition: `Key` meets *Cpp17MoveAssignable*. ¶2–¶4 For each element `e`, the predicate is called with `as_const(e)`, the elements for which it is true are erased, and the number erased is returned; the predicate is invoked exactly `c.size()` times. ¶5 The erasure is stable; if an exception is thrown, `c` is in a valid but unspecified state, still meeting its invariants but possibly empty.

The only difference from `flat_map` is the predicate's argument: `flat_map` passes `pair<const Key&, const T&>`, while `flat_set` passes `as_const(e)` directly.

## flat_multiset ([flat.multiset])

`flat_multiset` allows equivalent keys, and its tag becomes `sorted_equivalent_t`. Overview paragraphs ¶1–¶10 correspond paragraph by paragraph to `flat_set`, with these differences:

- ¶1 it supports equivalent keys, that is, it can contain multiple copies of the same key value;
- ¶3 it supports *a_eq* and not *a_uniq*;
- ¶9 calling a member taking `sorted_equivalent_t` with an unsorted range is {{ub}}; equal elements are allowed.

[flat.multiset.cons] ¶1–¶2 Construction from a container only sorts and does not deduplicate; [flat.multiset.cons.alloc] ¶1–¶6 correspond to `flat_set`.

[flat.multiset.modifiers] describes `emplace` in addition to what `flat_set` has:

!!! std
    First, initializes an object `t` of type `value_type` with `std::forward<Args>(args)...`, then inserts `t` as if by: `auto it = ranges::upper_bound(c, t, compare); c.insert(it, std::move(t));`

¶1 The constraint is `is_constructible_v<value_type, Args...>`; ¶2 first constructs `t`, then inserts it at `upper_bound`; ¶3 returns an iterator to the new element. Inserting at `upper_bound` places the new element after the existing equivalent elements, consistent with `std::multiset`, and equivalent elements keep their insertion order.

The remaining paragraphs: ¶4–¶6 bulk `insert` appends, sorts and merges without deduplicating, N + M log M; ¶7–¶8 the `sorted_equivalent` version is linear time; ¶9–¶13 the two versions of `insert_range`; ¶14 `swap`; ¶15–¶16 `extract`; ¶17–¶18 `replace`, whose precondition requires only sortedness. [flat.multiset.erasure] ¶1–¶5 are the same as for `flat_set`.

!!! impl "The libc++ implementation"
    In libc++ (Clang 23), `__cpp_lib_flat_set` is `202511L` and `__cpp_lib_constexpr_flat_set` is `202502L`. `iterator` and `const_iterator` are the same type and are not marked as contiguous iterators. The sortedness preconditions of `sorted_unique`, `sorted_equivalent` and `replace` are checked only in the debug hardening mode; after a bulk insertion with `sorted_unique`, it also checks that the newly appended part is sorted and duplicate-free.

## Questions

!!! question "Question 1"
    [flat.set.overview] ¶1 only says the iterators model `random_access_iterator`. Why does [[flat.map#1]] go out of its way to say they meet *Cpp17InputIterator*?

<details markdown="1">
<summary>Answer</summary>

`*it` of a `flat_set` is a genuine `const Key&`, so a thin wrapper around `vector`'s iterator meets *Cpp17RandomAccessIterator*, and the standard needs no downgrade notice. `*it` of a `flat_map` is a proxy prvalue, and *Cpp17ForwardIterator* requires `reference` to be a real reference type, which it cannot be. So the standard has to state that by the Cpp17 requirements it is only an input iterator, and only by the C++20 concepts is it a random access iterator.
</details>

!!! question "Question 2"
    After `std::flat_multiset<int> ms{2, 1};`, calling `ms.insert(ms.begin(), 2)`: does the new 2 go before or after the existing 2?

<details markdown="1">
<summary>Answer</summary>

Hinted insertion is not described separately in [flat.multiset.modifiers], so per ¶4 [[associative.reqmts]] applies: for containers that allow equivalent keys, `insert(p, t)` always inserts, placing `t` as close as possible to the position just prior to `p`. `ms.begin()` points to 1, and the closest position that keeps the order is just before the existing 2, so the new element goes first. With `int` there is no visible difference; with a struct whose comparator compares only one field, libc++ (Clang 23) places the new element before the existing equivalent element.
</details>
