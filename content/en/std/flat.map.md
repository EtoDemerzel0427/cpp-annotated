---
title: flat_map and flat_multimap
summary: "Associative containers that store keys and values in two separate sorted arrays: fast lookup and iteration, linear single-element insertion; dereferencing an iterator yields a proxy object, insertion may invalidate all iterators, and after an exception the container may be emptied."
updated: 2026-10-19
---

!!! tldr
    - `flat_map` stores keys and values in two separate sorted sequence containers (two `vector`s by default). Lookup is a binary search, iteration a linear scan, and single-element insertion and erasure take linear time.
    - There are no `pair<Key, T>` objects in memory; dereferencing an iterator yields a proxy `pair<const Key&, T&>`. So `for (auto [k, v] : fm) v += "!";` modifies the container, whereas for `std::map` it would not.
    - Iterator invalidation follows the underlying containers: with `vector`, any insertion may invalidate all iterators, references and pointers.
    - After a member function throws, the standard only guarantees that the invariants are restored; the container may be emptied.
    - Passing `sorted_unique` promises the library the data is sorted and free of duplicates; data that is not is UB. Two containers of different lengths are UB too.

## A map on two arrays

`std::map` is a red-black tree with one heap node per element, and lookup jumps around memory following pointers. `std::flat_map` ({{c++23}}, [[P0429R9]]) provides almost the same interface but keeps the data in two sorted arrays:

```
keys:   [ 1 | 3 | 7 | 9 | 12 ]      KeyContainer, vector<Key> by default
values: [ a | b | c | d | e  ]      MappedContainer, vector<T> by default
          the ith value belongs to the ith key
```

Lookup is a single binary search over contiguous memory, which is cache-friendly; iteration is a sequential scan of the two arrays. The price is that inserting or erasing an element shifts every element after it by one position.

`flat_map` is a **container adaptor** ([[g:container-adaptor]]): it does not manage storage itself but wraps two sequence containers. The standard calls this kind of container a flat container ([[g:flat-container]]). The underlying containers can be swapped for `deque`, `pmr::vector` or `inplace_vector`, and `extract()` can take both arrays out wholesale to be processed and put back.

This storage scheme brings a series of rules that differ from `std::map`:

| | `std::map` | `std::flat_map` |
|---|---|---|
| Dereferencing an iterator | `pair<const Key, T>&` | `pair<const Key&, T&>`, a proxy prvalue |
| Single-element insertion and erasure | O(log N) | O(N) |
| Iterators after insertion | All valid | Invalidated per the underlying container's rules; possibly all with `vector` |
| Node handles | `extract(key)`, `insert(node)` | None; `extract()` takes out both whole containers |
| Allocators | An allocator-aware container | Not one; no `allocator_type` |
| Single-element insertion that throws | No effect (strong guarantee) | Only guarantees the invariants are restored; may be emptied |

## Dereferencing yields a proxy ([flat.map.defn])

Keys and values live in two arrays, and there is simply no `pair<Key, T>` object in memory to refer to. When an iterator is dereferenced, the implementation can only construct, on the spot, a pair made of two references and return it as a prvalue. Hence the member types:

```cpp
using value_type      = pair<key_type, mapped_type>;
using reference       = pair<const key_type&, mapped_type&>;
using const_reference = pair<const key_type&, const mapped_type&>;
```

The first consequence is that a `pair&` cannot bind to `*it`:

```cpp run title="flat-map-no-pair-ref.cpp" error
#include <flat_map>
#include <string>

int main() {
  std::flat_map<int, std::string> m{{1, "a"}};
  std::pair<const int, std::string>& r = *m.begin();  // error: cannot bind to a pair<const int&, string&> temporary
  (void)r;
}
```

More subtly, `auto` in a range-for changes meaning. Copying a proxy still copies two references:

```cpp run title="flat-map-auto-binding.cpp" ok
#include <flat_map>
#include <map>
#include <string>
#include <cassert>

int main() {
  std::flat_map<int, std::string> fm{{1, "a"}, {2, "b"}};
  for (auto [k, v] : fm) v += "!";        // copies the proxy pair<const int&, string&>; v still refers to the value in the container
  assert(fm[1] == "a!");                  // the container was modified

  auto&& ref = *fm.begin();               // OK: extends the lifetime of the temporary proxy
  ref.second = "z";
  assert(fm[1] == "z");

  std::map<int, std::string> m{{1, "a"}};
  for (auto [k, v] : m) v += "!";         // for map, auto copies a pair, and v is a copy
  assert(m[1] == "a");
}
```

The same line `for (auto [k, v] : c) v += "!";` leaves a `map` unchanged but modifies a `flat_map`. When migrating from `map` to `flat_map`, this is the difference most easily missed. `it->second` also needs special handling: implementations make `operator->` return a small object holding the proxy.

The proxy also explains a phrase in [flat.map.overview] ¶1:

!!! std
    `flat_map` supports iterators that meet the *Cpp17InputIterator* requirements and model the `random_access_iterator` concept.

By the C++20 iterator concepts it is a random access iterator; by the C++17-style named requirements (*Cpp17ForwardIterator* and above) it is only an input iterator, because those requirements say `reference` must be a real reference type. So `std::ranges` algorithms treat it as a random access iterator, while older algorithms that look only at the Cpp17 requirements can, strictly speaking, treat it only as an input iterator.

Other details of the class definition:

- `value_compare` compares only `.first`. Its constructor is private; it can be obtained only through `value_comp()`.
- `struct containers { key_container_type keys; mapped_container_type values; };` is the return type of `extract()`. ¶1 says it has only these two data members and no base classes, so you can write `auto [ks, vs] = std::move(m).extract();`.
- `keys()` and `values()` return `const&` to the underlying containers and are both `noexcept`. To hand the value array to an interface that accepts only contiguous memory, use `m.values().data()`.
- `size_type` is always `size_t`; the `size_type` of `flat_set`, by contrast, is `KeyContainer::size_type` ([[flat.set]]).
- The members *c* and *compare* are exposition only. Unlike `stack`'s `protected: Container c;`, they are not accessible to derived classes.

## Which requirements it meets ([flat.map.overview] ¶1–¶4)

¶1 `flat_map` is an associative container with unique keys: each key occurs at most once, and values of another type `T` are retrieved quickly based on the key.

¶2 It meets the requirements of a container ([[container.reqmts]]), a reversible container ([[container.rev.reqmts]]) and the optional container requirements ([[container.opt.reqmts]], i.e. `<=>` comparison), and the associative container requirements ([[associative.reqmts]]), with three exceptions:

- ¶2.1 it does not meet the node handle requirements ([[container.node]]);
- ¶2.2 it does not meet the iterator invalidation requirements;
- ¶2.3 operations that insert or erase a single element take linear time, including the versions with a position hint.

Note 1 adds that `flat_map` does not meet the additional requirements of an allocator-aware container ([[g:allocator-aware-container]]). It has no `allocator_type` or `get_allocator()`, and copy and assignment do not handle allocators according to `propagate_on_container_*`; all of that is left to the two underlying containers. It still takes part in uses-allocator construction, though; see the allocator-extended constructors below.

¶3 It supports the *a_uniq* operations of the associative container requirements for unique keys, not the *a_eq* operations for equivalent keys. `key_type` is `Key`, and `value_type` is `pair<Key, T>`, not `std::map`'s `pair<const Key, T>`.

¶4 This subclause describes only operations that are not in the requirements table or that need additional semantics. For members not mentioned here, such as `find`, `lower_bound` and `count`, the semantics in [[associative.reqmts]] apply.

## Invariants and exceptions (¶5–¶6)

¶5 A `flat_map` maintains three **invariants**:

- ¶5.1 it contains the same number of keys and values;
- ¶5.2 the keys are sorted with respect to the comparison object;
- ¶5.3 the value at offset `off` within the value container is the value associated with the key at offset `off` within the key container.

For a unique-key `flat_map`, keys also must not repeat. That is ensured by deduplication in the constructors and by the preconditions of `sorted_unique` and `replace`.

¶6 is an exception rule specific to the flat container family:

!!! std
    If any member function in [flat.map.defn] exits via an exception the invariants of the object argument are restored.

If a member function in [flat.map.defn] exits via an exception, the invariants of `*this` are restored; for the move constructor and move assignment, the invariants of both objects are restored. Note 2 says this may result in the `flat_map` being emptied.

Why not a strong guarantee like `std::map`'s? Inserting one element means one insertion into each of two containers. If inserting the key succeeds and inserting the value throws, the key container has one extra element. Getting back to the original state means erasing that key again, and for a `vector`, erasure moves the following elements, and moving can itself throw. So the standard only promises that the invariants hold, and the cheapest way to restore them is to empty both containers.

Two phrases in this rule deserve attention:

- "object argument" means the implicit object argument, that is, `*this` ([[over.match.funcs]]). The non-member function `erase_if` is not covered; it has its own rule ([flat.map.erasure] ¶5).
- "restored" only requires the result to satisfy the invariants and says nothing about which elements are kept. An implementation may roll back, empty the container, or keep only some elements. The contents after an exception are unspecified as far as users are concerned.

libc++'s single-element insertion rolls back when it can and empties otherwise. The two programs below differ only in whether the value type is copyable:

<div class="compare" markdown="1">

```cpp run title="rollback.cpp" ok
#include <flat_map>
#include <cstdio>
#include <stdexcept>

struct Bomb {    // copying may throw
  static inline bool armed = false;
  int v;
  Bomb(int x) : v(x) {}
  Bomb(const Bomb& o) : v(o.v) {
    if (armed)
      throw std::runtime_error("copy");
  }
  Bomb& operator=(const Bomb&)
    = default;
};

int main() {
  std::flat_map<int, Bomb> m;
  for (int i = 0; i < 4; ++i)
    m.try_emplace(i * 10, i);
  Bomb::armed = true;
  try {
    m.try_emplace(15, 99);
  } catch (const std::exception&) {
    // libc++: size = 4
    std::printf("size = %zu\n",
                m.size());
  }
}
```

```cpp run title="clear.cpp" ok
#include <flat_map>
#include <cstdio>
#include <stdexcept>

struct MoveOnly {  // move-only, and moving may throw
  static inline bool armed = false;
  int v;
  MoveOnly(int x) : v(x) {}
  MoveOnly(MoveOnly&& o) : v(o.v) {
    if (armed)
      throw std::runtime_error("move");
  }
  MoveOnly& operator=(MoveOnly&&)
    = default;
};

int main() {
  std::flat_map<int, MoveOnly> m;
  for (int i = 0; i < 4; ++i)
    m.try_emplace(i * 10, i);
  MoveOnly::armed = true;
  try {
    m.try_emplace(15, 99);
  } catch (const std::exception&) {
    // libc++: size = 0
    std::printf("size = %zu\n",
                m.size());
  }
}
```

</div>

Inserting in the middle shifts existing values, so both programs throw. On the left the value type is copyable, `vector`'s single-element insertion has the strong guarantee, and libc++ erases the just-inserted key, leaving `m` with 4 elements. On the right the value type is move-only with a move that may throw, `vector` cannot give the strong guarantee, and libc++ has to empty the container. Both outcomes conform to ¶6; with another standard library implementation, the number of elements left after the exception may differ.

Moves are bound by ¶6 too: after move construction and move assignment, the moved-from object must also satisfy the invariants. A moved-from `vector` is usually empty, but the standard only says it is in a valid but unspecified state. If the key container ended up empty while the value container did not, the moved-from `flat_map` would violate ¶5.1. libc++ therefore explicitly clears the source object in its move constructor.

## Underlying containers (¶7–¶8)

¶7 Any type `C` that meets the sequence container requirements ([[sequence.reqmts]]) can be used as `KeyContainer` or `MappedContainer`, provided `C::iterator` meets *Cpp17RandomAccessIterator* and `C::size` and `C::max_size` do not throw. The standard names [[vector]] and [[deque]]; Note 3 points out that [[vector.bool]] is not a sequence container and cannot be used. [[inplace.vector]] meets the requirements and yields a `flat_map` that allocates no heap memory at all.

The rule that `size` does not throw presumably serves ¶6: restoring the invariants involves comparing the lengths of the two containers, and that step must not throw again.

¶8 If `Key` is not the same type as `KeyContainer::value_type`, or `T` is not the same type as `MappedContainer::value_type`, the program is {{ill-formed}}.

## sorted_unique and two kinds of UB (¶9–¶11)

```cpp run title="sorted-unique-lie.cpp" ub
#include <flat_map>
#include <vector>
#include <cstdio>

int main() {
  std::vector<int> keys{3, 1, 2};               // not sorted
  std::vector<int> vals{30, 10, 20};
  std::flat_map<int, int> m(std::sorted_unique, std::move(keys), std::move(vals));  // UB
  std::printf("contains(1) = %d\n", m.contains(1));
}
```

`std::sorted_unique` is a tag object of type `sorted_unique_t` ([[g:sorted-unique]]), defined in both `<flat_map>` and `<flat_set>` ([flat.map.syn]). Its default constructor is `explicit`, so `{}` is not implicitly converted to this tag. Passing it tells the library that the data is already sorted and has no duplicates, so it need not sort and deduplicate. In return, construction drops to constant or linear complexity.

¶10 If the data is not sorted or contains equal elements, the behavior is undefined:

!!! std
    The effect of calling a member function that takes a `sorted_unique_t` argument with a container, containers, or range that is not sorted with respect to `key_comp()`, or that contains equal elements, is undefined.

¶9 adds another case of UB: calling a constructor with a key container and a value container of different lengths.

With the default configuration of libc++ (Clang 23), the program above prints `contains(1) = 0`: binary search over an unsorted array cannot find a key that really is there. Both of these are ordinary {{ub}}, not hardened preconditions, but libc++ still checks them, at different hardening levels:

| Violation | Checked in which hardening modes |
|---|---|
| Key and value containers of different lengths (¶9, `replace`) | fast, extensive, debug |
| `sorted_unique` data unsorted or with duplicates (¶10, `replace`) | Only debug, because the check itself is O(N) |

Compiling the program above with `-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_DEBUG` makes it terminate at construction, reporting that the key container is not sorted or contains duplicates.

¶11 `iterator` and `const_iterator` meet the constexpr iterator requirements. In the current draft, the whole `flat_map` is usable in constant evaluation.

## Construction ([flat.map.cons], [flat.map.cons.alloc])

### Construction from two containers

| Paragraph | Constructor | Effect | Complexity |
|---|---|---|---|
| ¶1–¶2 | `flat_map(key_cont, mapped_cont, comp = {})` | Moves in the two containers, sorts by `value_comp()`, then removes duplicate keys | Linear if already sorted, N log N otherwise |
| ¶3–¶4 | `flat_map(sorted_unique, key_cont, mapped_cont, comp = {})` | Only moves in; no sorting or deduplication | Constant |

¶1 The two container parameters are taken by value and then moved into the members. So `flat_map(std::move(ks), std::move(vs))` copies no elements.

¶1's deduplication applies `ranges::unique` to `views::zip(keys, values)`, keeping the first of each group of equivalent keys after sorting. The sort is not required to be stable, so when the input has duplicate keys, which value survives is unspecified; do not rely on earlier entries overriding later ones or vice versa.

¶2 requires linear time when the input is already sorted. The implementation either checks first whether the input is sorted or uses a sorting algorithm that adapts to sorted input.

The other constructors given directly in the class definition all reduce to insertion: the iterator-pair constructor calls `insert(first, last)`, the `sorted_unique` iterator-pair constructor calls `insert(sorted_unique, first, last)`, the `from_range` constructor calls `insert_range(rg)`, and the `initializer_list` constructor forwards to the iterator-pair version.

### Allocator-extended construction

[flat.map.cons.alloc] ¶1 These constructors participate in overload resolution only if both `uses_allocator_v<key_container_type, Alloc>` and `uses_allocator_v<mapped_container_type, Alloc>` are true. ¶2–¶6 Their effects are the same as the corresponding versions without an allocator, except that both underlying containers are created by uses-allocator construction ([[allocator.uses.construction]]), with the same allocator given to each.

¶5 The `sorted_unique` version with an allocator has linear rather than constant complexity, because its container parameters are `const&` and must be copied.

The standard also specializes `uses_allocator` for `flat_map`, true when both underlying containers use the allocator. So although `flat_map` is not an allocator-aware container, it still receives the outer memory resource when placed in a `pmr::vector`:

```cpp run title="flat-map-pmr.cpp" ok
#include <flat_map>
#include <memory_resource>
#include <vector>
#include <cassert>

template<class K, class V>
using pmr_flat_map = std::flat_map<K, V, std::less<K>, std::pmr::vector<K>, std::pmr::vector<V>>;

template<class T> concept has_allocator_type = requires { typename T::allocator_type; };
static_assert(!has_allocator_type<pmr_flat_map<int, int>>);          // not an allocator-aware container
static_assert(std::uses_allocator_v<pmr_flat_map<int, int>,          // but takes part in uses-allocator construction
                                    std::pmr::polymorphic_allocator<>>);

int main() {
  std::pmr::monotonic_buffer_resource arena;
  std::pmr::vector<pmr_flat_map<int, int>> outer(&arena);
  outer.emplace_back();                       // the outer vector passes arena to both inner containers
  outer[0][1] = 10;
  assert(outer[0].keys().get_allocator().resource() == &arena);
  assert(outer[0].values().get_allocator().resource() == &arena);
}
```

The class definition is followed by more than a dozen deduction guides. When deducing from two containers, `Key` and `T` are taken from the respective `value_type`s and the container types are kept; when deducing from an iterator pair or an `initializer_list<pair<Key, T>>`, `vector` is used by default. All of them are subject to the general rules for deduction guides in [[container.adaptors]].

## Capacity and access ([flat.map.capacity], [flat.map.access])

[flat.map.capacity] ¶1 `size()` returns the key container's `size()`; ¶2 `max_size()` returns the smaller of the two containers' `max_size()`.

[flat.map.access]:

| Paragraph | Member | Specification |
|---|---|---|
| ¶1–¶2 | `operator[](const key_type&)`, `operator[](key_type&&)` | Equivalent to `return try_emplace(x).first->second;` |
| ¶3–¶4 | `template<class K> operator[](K&&)` | Requires a transparent comparator (`Compare::is_transparent` exists); otherwise the same |
| ¶5–¶7 | `at(const key_type&)` | Returns a reference to the corresponding value; throws `out_of_range` if absent; logarithmic complexity |
| ¶8–¶12 | `template<class K> at(const K&)` | Same, additionally requiring a transparent comparator and that `find(x)` is well-formed with well-defined behavior |
| ¶13–¶16 | `lookup(x)` | Returns `optional<mapped_type&>`: a reference to `find(x)->second` if present, `nullopt` otherwise; logarithmic complexity |

`operator[]` is defined through `try_emplace`, so it requires `mapped_type` to be default constructible, and an `m[k]` with an absent key is an O(N) insertion.

`lookup` is a member added to the draft relatively recently, which `std::map` gained at the same time. It uses `optional<T&>` to save the `find`-then-compare-with-`end()` pattern. At the time of writing, libc++'s `flat_map` in Clang 23 does not have `lookup` yet.

## Modifiers ([flat.map.modifiers])

### Single-element insertion

¶1–¶3 `emplace(args...)` first constructs a `pair<key_type, mapped_type>` object `t` from the arguments. If an equivalent key already exists, `*this` is unchanged; otherwise it is equivalent to:

```cpp
auto key_it = ranges::upper_bound(c.keys, t.first, compare);
auto value_it = c.values.begin() + distance(c.keys.begin(), key_it);
c.keys.insert(key_it, std::move(t.first));
c.values.insert(value_it, std::move(t.second));
```

This code makes the complexity clear: one logarithmic binary search plus two linear insertions in the middle. It also shows that `emplace` constructs `t` even if the key already exists; to avoid that construction, use `try_emplace`.

¶4–¶5 `insert(P&&)` and `insert(hint, P&&)` are equivalent to `emplace` and `emplace_hint` respectively. Per ¶2.3, the hinted version is still linear time; the hint saves at most one binary search.

¶16–¶19 `try_emplace(k, args...)`: if an equivalent key exists, neither `*this` nor `args...` is changed, and the arguments are not moved from; otherwise the key and the value are inserted at the `upper_bound` position in their respective containers.

¶20–¶24 are the heterogeneous version `try_emplace(K&& k, args...)`, where the key can be of a type other than `key_type`, such as `string_view`. There are four constraints: the comparator is transparent; `key_type` is constructible from `K`; `mapped_type` is constructible from `args...`; and in the first overload `K` is not convertible to an iterator, to avoid confusion with `try_emplace(hint, ...)`. ¶21 also has a precondition:

!!! std
    The conversion from `k` into `key_type` constructs an object `u`, for which `find(k) == find(u)` is true.

That is, the heterogeneous key and the real key it converts into must be at the same position as far as the comparator is concerned. If a transparent comparator compares `string_view` and `string` inconsistently, say one case-sensitive and the other case-insensitive, this is {{ub}}.

¶25–¶33 `insert_or_assign(k, obj)`: if there is an element `e` whose key is equivalent, `std::forward<M>(obj)` is assigned to `e.second`; otherwise it reduces to `try_emplace`. The heterogeneous versions (¶29–¶33) have the same constraints and preconditions as `try_emplace`.

### Bulk insertion

¶6–¶8 `insert(first, last)` first appends all new elements to the end of the two containers, then sorts the newly added part by `value_comp()`, merges it with the existing part into one sorted sequence, and finally deduplicates in the same way as the constructors.

- ¶7 The complexity is N + M log M, where N is the original size and M the number of new elements. Inserting one by one would cost M·N, so a batch of elements should be inserted at once.
- ¶8 The merge is done in place (an in-place merge) and may allocate memory.

The wording does not say which value survives when a new key duplicates an existing one, because it does not specify which of the new and old elements comes first in the merge. libc++ in Clang 23 keeps the old element, consistent with `map::insert` not inserting when the key exists. Which of several duplicate keys among the new elements survives depends on the sort, as with the constructors, and is unspecified.

¶9–¶10 The effect of `insert(sorted_unique, first, last)` is specified as equivalent to `insert(first, last)`, with only the complexity changed to linear (N being the size after the operation). The tag only allows the implementation to skip sorting the new elements; the result is exactly the same.

¶11–¶15 `insert_range(rg)` and `insert_range(sorted_unique, rg)` correspond one to one with the above.

### extract and replace

¶35–¶36 `extract() &&` returns `std::move(c)`, moving both underlying containers out wholesale:

!!! std
    *Postconditions*: `*this` is emptied, even if the function exits via an exception.

It is `&&`-qualified, so you must write `std::move(m).extract()`, which makes it literally visible that the contents of `m` are taken. It is entirely different from `map::extract(key)`, which takes out a node handle; `flat_map` has no node handles.

¶37–¶38 `replace(key_cont&&, mapped_cont&&)` move-assigns the two containers in. There are three preconditions: the two containers have equal length, the keys are sorted with respect to *compare*, and the keys contain no duplicates. Violating them is {{ub}}, and libc++ checks them at the same levels as in the table above.

Together, the two let you process data in bulk outside the `flat_map` with any algorithm:

```cpp run title="flat-map-extract-replace.cpp" ok
#include <flat_map>
#include <algorithm>
#include <ranges>
#include <vector>
#include <cassert>

// take the two arrays out, process them outside, and put them back at once
void scale_and_drop_small(std::flat_map<int, double>& m, double factor) {
  auto [keys, vals] = std::move(m).extract();     // m is now empty (¶35)
  for (double& v : vals) v *= factor;
  auto z = std::views::zip(keys, vals);
  auto tail = std::ranges::remove_if(z, [](const auto& kv) { return std::get<1>(kv) < 1.0; });
  auto n = tail.begin() - z.begin();
  keys.erase(keys.begin() + n, keys.end());
  vals.erase(vals.begin() + n, vals.end());
  m.replace(std::move(keys), std::move(vals));     // remove_if keeps relative order, so keys stay sorted and unique
}

int main() {
  std::flat_map<int, double> m{{1, 0.5}, {2, 3.0}, {3, 0.1}, {4, 2.0}};
  scale_and_drop_small(m, 2.0);
  assert(m.size() == 3 && m[2] == 6.0 && !m.contains(3));
  assert(std::erase_if(m, [](const auto& kv) { return kv.first == 4; }) == 1);
}
```

### swap

¶34 `swap` swaps the comparator, the key container and the value container in turn. If all three are nothrow-swappable, it is `noexcept`. If it throws partway, say after the key containers were swapped but before the value containers were, ¶6 of the overview applies as well; libc++ empties both `flat_map`s in that case.

## erase_if ([flat.map.erasure])

¶1 Precondition: `Key` and `T` meet *Cpp17MoveAssignable*.

¶2–¶4 For each element `e`, the predicate is called with `pair<const Key&, const T&>(e)`, the elements for which it is true are erased, and the number erased is returned. The predicate is invoked exactly `c.size()` times and receives const references, so it cannot take the opportunity to modify elements.

¶5 The erasure is stable ([[algorithm.stable]]): the remaining elements keep their original relative order. `erase_if` is a non-member function not covered by ¶6 of the overview, so it has its own rule: if an exception is thrown, `c` is in a valid but unspecified state. Note 1 adds that `c` still meets its invariants but may be empty.

## Iterator invalidation

¶2.2 says `flat_map` does not meet the [[g:iterator-invalidation|iterator invalidation]] requirements of associative containers. The replacement rule is in the general rules of [[container.adaptors]]: `insert`, `emplace` and `erase` affect iterators, references and pointers in the same way as the same-named operations of the underlying containers. For the default `vector`:

- when an insertion causes reallocation, all iterators, references and pointers are invalidated;
- without reallocation, those at and after the insertion point are invalidated;
- on erasure, those at and after the erasure point are invalidated.

A `flat_map` iterator consists internally of two underlying iterators (in libc++, `flat_map<int, int>::iterator` takes 16 bytes), and it is invalidated if either of them is. The most accident-prone case is the reference returned by `operator[]`:

```cpp run title="flat-map-dangling.cpp" ub
#include <flat_map>
#include <map>
#include <string>

int main() {
  std::map<int, std::string> m{{2, "two"}};
  std::string& a = m[2];
  m[1] = "one";              // OK: insertion into a map does not invalidate references
  a += "!";

  std::flat_map<int, std::string> fm{{2, "two"}};
  std::string& b = fm[2];
  fm[1] = "one";             // inserts at the front of values: the storage b refers to is shifted or freed
  b += "!";                  // UB
}
```

In our tests AddressSanitizer reports heap-use-after-free. Even with a prior `reserve` and no reallocation, `b` would refer to a different element, because the original `"two"` has been shifted to the next position. That is UB as well, and in practice the program does not crash but silently modifies the wrong data.

## flat_multimap ([flat.multimap])

`flat_multimap` allows equivalent keys and is structured in parallel with `flat_map`. The paragraphs of its overview correspond one to one with those of `flat_map`, with these differences:

| Paragraph | `flat_multimap` | Compared with `flat_map` |
|---|---|---|
| ¶1 | Supports equivalent keys | Unique keys become equivalent keys |
| ¶3 | Supports *a_eq*, not *a_uniq* | The reverse |
| ¶4 | Unless otherwise specified, operations are equivalent to the corresponding `flat_map` operations, except that elements with equal keys are not erased or replaced | Construction and bulk insertion do not deduplicate |
| ¶10 | Calling a member taking `sorted_equivalent_t` with unsorted data is UB | Only sortedness is required; equal elements are allowed |

¶2, ¶5–¶9 and ¶11 are the same as for `flat_map`: the same three exceptions, the same invariants and exception rule, the same underlying-container requirements and the same two UB preconditions.

The tag becomes `std::sorted_equivalent`, whose name says the data is sorted but may contain equivalent elements. `flat_multimap` has no `operator[]`, `at`, `lookup`, `try_emplace` or `insert_or_assign`, all of which depend on unique keys. Its `emplace` returns `iterator` rather than `pair<iterator, bool>` and inserts at `upper_bound`, putting the new element at the end of the equivalent keys, consistent with `multimap`.

[flat.multimap.cons] ¶1–¶2 The two-container constructor sorts without deduplicating, with the same complexity as for `flat_map`; ¶3–¶4 the `sorted_equivalent` version is constant. [flat.multimap.cons.alloc] ¶1–¶6 correspond paragraph by paragraph to `flat_map`, with ¶5 likewise linear. [flat.multimap.erasure] ¶1–¶5 are the same as `flat_map`'s `erase_if`.

## When to use flat_map

Rough measurements from our tests (Apple Silicon, `-O2`, `int` to `int`, one million random keys, orders of magnitude only):

| Operation | `std::map` | `std::flat_map` |
|---|---|---|
| Build: `map` inserting one by one, `flat_map` constructed from two containers (one sort) | ~930 ms | ~100 ms |
| One million random `find`s | ~860 ms | ~220 ms |
| Full iteration summing values | ~140 ms | <1 ms |
| 100,000 random single-element insertions | ~60 ms | ~1600 ms |

`flat_map` suits read-mostly workloads with small elements that can be built in bulk. `map` suits workloads that need stable references and iterators, frequent single-element insertion and erasure, or very large elements. Also, the keys and values of a `flat_map` must be movable, because insertion shifts elements; `map` can hold types that can be neither copied nor moved.

!!! impl "The libc++ implementation"
    In libc++ (Clang 23), `__cpp_lib_flat_map` is `202511L` and `__cpp_lib_constexpr_flat_map` is `202502L`. Both `iterator_concept` and `iterator_category` of the iterator are `random_access_iterator_tag`; the latter is higher than the input iterator the standard promises, and libc++ labels it this way to keep older algorithms from degrading at run time. After move construction the source object is explicitly cleared; `swap`, `erase` and bulk insertion call `clear()` on their exception paths; single-element insertion rolls back where possible. `lookup` is not implemented yet.

## History

!!! history
    - C++23: `flat_map` and `flat_multimap` added by [[P0429R9]], and the `flat_set` family by [[P1222R4]] at the same time.
    - C++26: all members become `constexpr`.
    - Drafts after C++26: the `lookup` member is added, in step with `std::map`.

## Questions

!!! question "Question 1"
    Does calling `std::ranges::sort(m)` on a `flat_map<int, int> m` compile?

<details markdown="1">
<summary>Answer</summary>

No. `ranges::sort` requires the iterator to satisfy `sortable`, which includes swapping and moving elements through iterators. The `reference` of `flat_map` is `pair<const int&, int&>`, whose `.first` is a const reference that cannot be assigned, so the constraint is not satisfied; Clang 23 reports no matching function. This is exactly the desired result: keys must not be modified, or the sorted invariant would break. If you really need to reorder, `extract()` the two containers, sort `views::zip(keys, values)`, and `replace()` them back.
</details>

!!! question "Question 2"
    A function receives `const std::flat_map<K, V>& m` and hands `m.values().data()` to a C library to keep. Which later operations on `m` may invalidate that pointer?

<details markdown="1">
<summary>Answer</summary>

`values()` returns a const reference to the value container, and the validity of `data()` follows the rules of `vector`. Insertion (including `operator[]` with an absent key), `erase`, `clear`, `extract`, `replace`, assignment and `swap` may all invalidate it or make it point to different contents. In addition, per [flat.map.overview] ¶6, any member function that exits via an exception may empty `m`, so after a caught exception you cannot assume the pointer is still valid either.
</details>

!!! question "Question 3"
    Why is the effect of `insert(sorted_unique, first, last)` specified as equivalent to `insert(first, last)` instead of being described separately?

<details markdown="1">
<summary>Answer</summary>

When the precondition holds, the new elements are already sorted and duplicate-free, so sorting them changes nothing and both produce the same result. Writing "equivalent to" lets it reuse the description of appending, merging and deduplicating in [flat.map.modifiers] ¶6, only tightening the complexity from N + M log M to linear, which forces the implementation to skip the sort. If the data is in fact unsorted, the sequence the implementation merges after skipping the sort is not sorted, the invariant breaks, and every later binary search may go wrong, which is why ¶10 makes it UB.
</details>
