---
title: map, set, multimap and multiset
summary: "The members specific to each of the four ordered associative containers: map::operator[] is try_emplace, try_emplace leaves its arguments alone when the key exists while emplace makes no such promise, insert_or_assign, lookup, the undefined-behavior condition of C++26 heterogeneous insertion, plus the deduction guides and erase_if."
updated: 2026-10-19
---

!!! tldr
    - `m[k]` is defined as `try_emplace(k).first->second`: when the key is absent it inserts a value-initialized value, so it is a modifying operation and requires the mapped type to be default constructible.
    - When the key already exists, `try_emplace` guarantees no effect at all, and rvalue arguments are not moved from; `emplace` gives no such guarantee.
    - `insert_or_assign` does not require the mapped type to be default constructible, and it reports whether a new element was inserted.
    - C++26 heterogeneous insertion requires the real key constructed from the heterogeneous key to fall in the same position under the comparator, or the behavior is undefined.
    - `erase_if` for node containers erases one element at a time, because `pair<const K, T>` cannot be assigned and the remove-erase idiom does not work.

[associative] defines `map` and `multimap` in `<map>` and `set` and `multiset` in `<set>`. Most of their semantics come from the associative container requirements ([[associative.reqmts]]): ordering by a comparator, logarithmic lookup and insertion, insertion that invalidates no iterators. [associative] only adds what is specific to each class template, mainly `map`'s element access and its family of keyed insertion functions.

## What m[k] does ([map.access])

```cpp title="map-subscript-nodefault.cpp" error
#include <map>
struct NoDefault { NoDefault(int) {} };
int main() {
  std::map<int, NoDefault> m;
  m.try_emplace(1, 42);    // OK
  m[1];                    // error: operator[] needs NoDefault to be default constructible
}
```

¶1 The effect of `operator[](const key_type& x)` is equivalent to `return try_emplace(x).first->second;`. ¶2 The rvalue-key version moves the key into `try_emplace`. So when the key is absent, `m[k]` constructs the mapped value from an empty argument list and inserts it. A type without a default constructor cannot use `operator[]`, even if the key already exists.

`operator[]` is therefore a modifying operation: it cannot be used on a `const map`, and it is not on the list of functions considered const in [[container.requirements.dataraces#1]], so two threads calling `operator[]` on the same map at the same time is a data race. For read-only access, use one of these:

| Member | Specification | Source |
|---|---|---|
| `at(x)` | Returns a reference to the mapped value; throws `out_of_range` if the key is absent; logarithmic | ¶5–¶7 |
| `lookup(x)` | Returns `optional<mapped_type&>`: a reference to the mapped value if present, `nullopt` otherwise | ¶13–¶16 |
| `find(x)`, `contains(x)` | See [[associative.reqmts]] | |

`lookup` is a new interface after C++26 that uses `optional<T&>`. libc++ in Clang 23 does not provide it yet.

¶3–¶4, ¶8–¶12 `operator[]` and `at` each also have a template version `template<class K>`, which participates in overload resolution only if the comparator has a member type `is_transparent`; lookup can then proceed without first constructing a `key_type`. ¶9 makes it a precondition of `at(const K&)` that `find(x)` is well-formed and has well-defined behavior.

## try_emplace versus emplace ([map.modifiers])

```cpp title="try-emplace.cpp" run ok
#include <map>
#include <memory>
#include <string>
#include <cassert>

int main() {
  std::map<std::string, std::unique_ptr<int>> m;
  m.emplace("a", std::make_unique<int>(1));

  auto p = std::make_unique<int>(2);
  m.try_emplace("a", std::move(p));   // key exists: p is not moved from
  assert(p != nullptr);

  auto q = std::make_unique<int>(3);
  m.emplace("a", std::move(q));       // q may have been moved into a temporary node and discarded
  // the standard does not specify q's state here; with libc++ (Clang 23) q is now empty

  auto [it, inserted] = m.insert_or_assign("a", std::make_unique<int>(4));
  assert(!inserted && *it->second == 4);   // exists: assigns to the mapped value
}
```

¶3–¶10 The effect of `try_emplace(k, args...)`:

!!! std
    If the map already contains an element whose key is equivalent to k, there is no effect.

No effect means `args...` are not moved from. Otherwise it inserts an element constructed with `piecewise_construct, forward_as_tuple(k), forward_as_tuple(args...)`, that is, the key constructed from `k` and the mapped value from `args...`.

`emplace(args...)` only specifies "constructs an element t and inserts it if and only if there is no element in the container with a key equivalent to the key of t" ([[associative.reqmts.general#49]]). The key is inside `args`, and in general the element has to be constructed before the key is known. If the key exists, the element is destroyed, and the rvalue arguments have already been moved into it.

{{impl}} libc++ looks the key up first, without constructing a node, when the first argument of `emplace` is exactly `key_type`: changing the example to `std::map<int, std::unique_ptr<int>>` and `m.emplace(1, std::move(q))`, `q` stays intact in our tests. When the argument needs a conversion, like `"a"` (`const char[2]`), it has to construct the node first. This is merely an implementation optimization; the standard guarantees it only for `try_emplace`.

### insert_or_assign and insert(P&&)

¶16–¶25 `insert_or_assign(k, obj)` requires `is_assignable_v<mapped_type&, M&&>` (a *Mandates*; ill-formed if not met). If the key exists, it assigns `obj` to the mapped value; otherwise it inserts `value_type(k, std::forward<M>(obj))`. It returns `pair<iterator, bool>`; the hinted version returns `iterator`.

Compared with `m[k] = obj`, it does not require the mapped type to be default constructible, does not construct a default value first only to assign over it, and tells you whether a new element was inserted.

¶1–¶2 `template<class P> insert(P&& x)` participates in overload resolution if `is_constructible_v<value_type, P&&>` is true, and is equivalent to `emplace(std::forward<P>(x))`. With it, `m.insert(std::pair{1, "x"})` can construct a `pair<const int, std::string>` directly from a `pair<int, const char*>`, without an intermediate `value_type` temporary.

### The counting idiom

```cpp run ok
#include <map>
#include <string>
#include <cassert>

int main() {
  std::map<std::string, int> counts;
  ++counts["x"];     // absent: inserts a value-initialized 0, then increments
  ++counts["x"];
  assert(counts.at("x") == 2);
}
```

Value-initialization guarantees that a newly inserted `int` is 0, so `++counts[k]` is the standard way to count occurrences.

## C++26 heterogeneous insertion (¶11–¶15, ¶26–¶31) {{c++26}}

A `std::map<std::string, int, std::less<>>` can already be searched with a `const char*` or `string_view` without constructing a `std::string`. C++26 extends this to insertion: `try_emplace(K&& k, ...)`, `insert_or_assign(K&& k, obj)` and `operator[](K&&)` all gain heterogeneous versions, which require the comparator to have `is_transparent`.

¶13's effects contain an undefined-behavior condition:

!!! std
    let r be equal_range(k). Constructs an object u of type value_type with ... If equal_range(u.first) == r is false, the behavior is undefined.

That is, the real key `u.first` constructed from `k` must fall in the same position as `k` under the comparator. If the conversion from `K` to `Key` changes the sort position, for example by truncating the string or normalizing case while the comparator does not, the behavior is {{ub}}. This requirement lets the implementation find the insertion point with `k` first and then construct the node and link it in directly, without searching again with `u.first`.

libc++ in Clang 23 does not implement heterogeneous insertion yet (`__cpp_lib_associative_heterogeneous_insertion` is not defined).

!!! lawyer "Why the iterator-excluding constraint sits on different overloads"
    ¶11 requires, for the heterogeneous `map::try_emplace`, that `K&&` not be convertible to an iterator, and this constraint is added only to the overload without a hint; for the heterogeneous `set::insert` it is the opposite, added to the hinted overload ([set.modifiers] ¶1). They guard against different ambiguities: if `k` in `try_emplace(k, args...)` were an iterator, it could be confused with the hinted `try_emplace(hint, key, args...)`; if `x` in `insert(hint, x)` were an iterator, it could be confused with the range insertion `insert(first, last)`.

## Construction and deduction guides ([associative.general], [map.cons])

[map.cons] ¶1–¶6 Construction from a comparator and an allocator is constant time. Range construction (iterator pair or `from_range`) is linear if the range is already sorted with respect to the comparator, and N log N otherwise.

[associative.general] ¶2 defines several exposition-only aliases used by the deduction guides:

| Alias | Meaning |
|---|---|
| `iter-value-type<It>` | `iterator_traits<It>::value_type` |
| `iter-key-type<It>` | `remove_const_t<tuple_element_t<0, iter-value-type<It>>>` |
| `iter-mapped-type<It>` | `tuple_element_t<1, iter-value-type<It>>` |
| `iter-to-alloc-type<It>` | `pair<const iter-key-type<It>, iter-mapped-type<It>>` |
| `range-key-type<R>` and so on | The same treatment applied to `ranges::range_value_t<R>` |

`iter-key-type` removes `const`, so deducing from another map's iterators (whose value type is `pair<const K, V>`) gives `map<K, V>`; so does deducing from a `vector<pair<K, V>>`. The initializer-list deduction guide accepts `initializer_list<pair<Key, T>>`, so `std::map m{std::pair{1, 2.0}, std::pair{2, 3.0}};` deduces `map<int, double>`.

## erase_if ([map.erasure])

¶1 `erase_if(c, pred)` is specified as a loop that checks each element and calls `c.erase(i)` one at a time, returning the number of elements erased. Node containers cannot use the remove-erase idiom: `remove` assigns to elements, and `pair<const K, T>` cannot be assigned, nor can the elements of a `set` be modified through iterators.

## multimap, set, multiset

**multimap** ([multimap]) supports equivalent keys, so one key can map to several values. It has no `operator[]`, `at`, `try_emplace` or `insert_or_assign`, because "the value for this key" is not defined in a `multimap`. Its only modifier is the `insert(P&&)` template, equivalent to `emplace`; construction and `erase_if` are the same as for `map`. When an equivalent key is inserted, the new element goes at the end of the range of existing equivalent elements ([[associative.reqmts.general#54]]).

**set** ([set]) has `Key` as both `key_type` and `value_type`, and its iterators are constant iterators: modifying an element through an iterator could break the ordering, so it is not allowed ([[associative.reqmts.general#6]]).

[set.modifiers] ¶1–¶3 has a C++26 heterogeneous `insert(K&& x)`, which requires a transparent comparator. If an element equivalent to `x` exists, there is no effect; otherwise let `r = equal_range(x)` and construct `u` from `std::forward<K>(x)`; if `equal_range(u) == r` is false, the behavior is undefined. This is the same pattern as `map`'s heterogeneous insertion.

**multiset** is the same as `set` but supports equivalent keys and has no heterogeneous `insert`.

## The libc++ implementation

{{impl}} All four ordered containers in libc++ are based on the red-black tree in `<__tree>`.

- `sizeof(std::map<int, int>)` and `sizeof(std::set<int>)` are both 24 bytes: a pointer to the leftmost node, an end node containing only a left pointer (serving as `end()` and as the root's parent, embedded directly in the container object), and the element count. An empty comparator class takes no space.
- Each node has three pointers, left, right and parent, a color bit (padded to 8 bytes), and then the element. A `map<int, int>` node is 40 bytes, which we verified with an allocator that prints requested sizes.
- The end node is embedded in the container object, so `end()` points into the container object, and after two containers are swapped, `end()` does not follow the elements. This is the practical reason [[container.reqmts#65]] leaves it unspecified whether `a.end()` equals `b.end()` after a swap.

## Common misconceptions

!!! pitfall "Using `m[k]` to test whether a key exists"
    `if (m[k] == 0)` inserts `k`. Test for existence with `contains(k)` (C++20) or `find(k) != end()`.

!!! pitfall "Using `<=` as the comparator"
    The comparator must be a strict weak ordering; this is a precondition of the associative containers, and violating it is undefined behavior. With `std::less_equal`, a unique-key container ends up with duplicate keys and `find` fails too; see [[associative.reqmts]].

!!! pitfall "`const_cast`ing an element of a `set` and modifying members used in comparison"
    The iterators of `set` are constant iterators precisely to prevent this. If you only modify members that do not take part in comparison, declare them `mutable`; to modify the part used in comparison, `extract`, modify, then `insert` ([[container.node]]).

## Questions

!!! question "Question"
    In `std::map<std::string, int> m;` the key `"k"` already exists. Which of `m.emplace("k", 1);` and `m.try_emplace("k", 1);` might allocate memory?

<details markdown="1">
<summary>Answer</summary>

`emplace` might. Its first argument is a `const char[2]`, not a `std::string`, so libc++ has to allocate a node and construct the `pair<const std::string, int>` in it before it has a key to compare; on finding the duplicate, it destroys and deallocates the node.

`try_emplace("k", 1)` first converts `"k"` into a `std::string` temporary (a short string does not allocate heap memory) and searches with it; since the key exists there is no effect, and no node is allocated. With C++26's heterogeneous `try_emplace` and a transparent comparator, even that temporary `std::string` can be avoided.
</details>

## Summary

| Container | Keys | Specific members |
|---|---|---|
| `map` | Unique | `operator[]` (i.e. `try_emplace`), `at`, `lookup`, `try_emplace`, `insert_or_assign`, plus C++26 heterogeneous versions |
| `multimap` | Equivalent | Only `insert(P&&)` |
| `set` | Unique | C++26 heterogeneous `insert(K&&)` |
| `multiset` | Equivalent | None |
