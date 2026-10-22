---
title: unordered_map, unordered_set and their multi versions
summary: "The members specific to each of the four unordered associative containers: the default bucket count is implementation-defined and the maximum load factor starts at 1.0, operator[], try_emplace and insert_or_assign mirror map, C++26 heterogeneous insertion requires an unchanged hash and a key not yet present, plus the layout and bucket-count policy of libc++'s hash table."
updated: 2026-10-19
---

!!! tldr
    - `operator[]`, `at`, `try_emplace` and `insert_or_assign` of `unordered_map` follow the same rules as for `map`; only the elements are organized by hash instead of by order.
    - The bucket count after default construction is implementation-defined (0 in libc++), and `max_load_factor()` starts at 1.0.
    - Insertion may trigger a rehash that invalidates all iterators, but references and pointers to elements are never invalidated by insertion.
    - C++26 heterogeneous insertion requires the real key constructed from the heterogeneous key to have the same hash and not yet be in the container, or the behavior is undefined.
    - Iteration order is unspecified and changes after a rehash; `std::hash` uses no random seed, so keys from untrusted input can be crafted to collide en masse.

[unord] defines `unordered_map` and `unordered_multimap` in `<unordered_map>` and `unordered_set` and `unordered_multiset` in `<unordered_set>`. The general rules of hash tables, including that the hash function and equality predicate must agree, what a rehash invalidates, complexity, and the meaning of `operator==`, are in the unordered associative container requirements [[unord.req]]. [unord] only adds what is specific to each class template.

The interface of `unordered_map` is deliberately kept consistent with `map` ([[associative]]); the specifications of `operator[]`, `try_emplace` and `insert_or_assign` are almost word for word the same.

## Buckets and load factor

```cpp title="buckets.cpp" run ok
#include <unordered_map>
#include <cstdio>

int main() {
  std::unordered_map<int, int> m;
  std::size_t last = m.bucket_count();
  std::printf("buckets: %zu", last);
  for (int i = 0; i < 1000; ++i) {
    m[i];
    if (m.bucket_count() != last)
      std::printf(" %zu", last = m.bucket_count());
  }
  std::printf("\nload_factor=%.3f max_load_factor=%.1f\n",
              m.load_factor(), m.max_load_factor());
  std::size_t b = m.bucket(42);
  std::printf("key 42 in bucket %zu (size %zu)\n", b, m.bucket_size(b));
  for (auto it = m.begin(b); it != m.end(b); ++it)   // local iterator: walks a single bucket
    std::printf("  %d\n", it->first);
}
```

A hash table divides its elements into a number of **buckets**: keys with the same hash value are always in the same bucket ([[unord.req.general#9]]). The **load factor** is the number of elements divided by the number of buckets, that is, the average number of elements per bucket. When the load factor would exceed the **maximum load factor**, the container increases the bucket count and redistributes the elements among the buckets, which is called a **rehash**.

With libc++ (Clang 23), the bucket count goes `0 2 5 11 23 47 97 197 397 797 1597`, ending with `load_factor=0.626`. libc++'s `std::hash<int>` is the identity function, so key 42 lands exactly in bucket 42.

[unord.map.cnstr] ¶1–¶2 Default construction and `(n, hf, eql, a)` construction produce an empty container with at least `n` buckets; on default construction the bucket count is implementation-defined; `max_load_factor()` returns 1.0; constant time. ¶3–¶4 Range, `from_range` and initializer-list construction likewise use an implementation-defined bucket count when no `n` is given, then insert the elements; average linear, worst case quadratic.

With libc++ (Clang 23), the bucket count after default construction is 0. So for a freshly default-constructed container, the precondition `bucket_count() > 0` of `bucket(k)` does not hold ([[unord.req.general#199]]).

A rehash invalidates all iterators and changes the ordering between elements and which buckets they are in, but does not invalidate references and pointers to elements ([[unord.req.general#9]]): nodes are only relinked, and the elements themselves do not move.

## Overview ([unord.general], [unord.map.overview])

[unord.general] ¶2 The deduction guides use the set of exposition-only aliases defined in [associative.general], such as `iter-key-type` and `range-key-type`; see [[associative]].

[unord.map.overview] ¶1 An `unordered_map` supports unique keys, associates mapped values with keys, and supports forward iterators.

¶2 It meets the requirements of a container, allocator-aware container and unordered associative container, providing the operations for unique keys; its `value_type` is `pair<const Key, T>`. It is not a reversible container and has no `rbegin`.

¶4 `iterator`, `const_iterator`, `local_iterator` and `const_local_iterator` meet the constexpr iterator requirements. In the current draft the unordered containers as a whole are usable in constant evaluation; libc++ in Clang 23 has not implemented this.

¶5 A `size_type` parameter in a deduction guide refers to the `size_type` of the deduced container type. So the `16` in `std::unordered_map m(first, last, 16)` is the bucket count. [[unord.req.general#246]] also says a deduction guide shall not deduce an integral type for `Hash`, so `16` is not taken as a hash function.

## Element access ([unord.map.elem])

| Member | Specification | Source |
|---|---|---|
| `operator[](const key_type&)`, `(key_type&&)` | Equivalent to `try_emplace(k).first->second` | ¶1–¶2 |
| `template<class K> operator[](K&&)` {{c++26}} | Participates in overload resolution only if both `Hash::is_transparent` and `Pred::is_transparent` exist | ¶3–¶4 |
| `at(k)` | Returns the mapped value of the element whose key is equivalent to `k`; throws `out_of_range` if absent | ¶5–¶6 |
| `template<class K> at(const K&)` | Likewise requires both to be transparent; precondition: `find(k)` is well-formed and has well-defined behavior | ¶7–¶10 |
| `lookup(k)` | Returns `optional<mapped_type&>`, `nullopt` if the key is absent; average constant, worst case linear | ¶11–¶14 |

As with `map`, `operator[]` is a modifying operation, requires the mapped type to be constructible from an empty argument list, and cannot be used for read-only access.

Heterogeneous lookup in unordered containers requires both the hash function and the equality predicate to be transparent, whereas ordered containers only require the comparator to be transparent. The reason is that lookup first computes the bucket with `Hash` and then compares within the bucket with `Pred`, and both steps must accept the heterogeneous key directly.

## Modifiers ([unord.map.modifiers])

- ¶1–¶4 `insert(P&&)`, `insert(hint, P&&)`: participate in overload resolution if `is_constructible_v<value_type, P&&>` is true; equivalent to `emplace` and `emplace_hint`.
- ¶5–¶12 `try_emplace(k, args...)`: if the key exists, no effect and the arguments are not moved from; otherwise constructs with `piecewise_construct` and inserts.
- ¶18–¶27 `insert_or_assign(k, obj)`: requires `is_assignable_v<mapped_type&, M&&>`; assigns if the key exists, inserts otherwise.

The motivation and usage of these three are exactly as for `map`; see [[associative]] for examples.

### C++26 heterogeneous insertion (¶13–¶17, ¶28–¶33) {{c++26}}

The heterogeneous `try_emplace` and `insert_or_assign` require both `Hash` and `Pred` to be transparent. ¶15's undefined-behavior condition has a different shape from `map`'s:

!!! std
    let h be hash_function()(k). Constructs an object u of type value_type ... If hash_function()(u.first) != h || contains(u.first) is true, the behavior is undefined.

Each condition has its use. The first requires the real key constructed from `k` to have the same hash as `k`, so the implementation can put the new node directly into the bucket computed from `h` without hashing again. The second requires the real key not to be in the container already: if `k` is not equivalent to any existing key but `u.first` is, then the equality semantics of `Key` and `K` disagree.

libc++ in Clang 23 does not implement heterogeneous insertion yet.

## erase_if ([unord.map.erasure])

¶1 `erase_if(c, pred)` is a loop that checks and erases one element at a time, returning the number of elements erased.

## The multimap and set versions

**unordered_multimap** ([unord.multimap]) supports equivalent keys and has no `operator[]`, `at`, `lookup`, `try_emplace` or `insert_or_assign`. Its only modifier is the `insert(P&&)` template; construction and `erase_if` are the same as for `unordered_map`. Elements with equivalent keys are adjacent in the iteration order ([[unord.req.general#6]]).

For **unordered_set** ([unord.set]) and **unordered_multiset**, the value type is the key type, and the iterators are constant iterators. [unord.set.modifiers] ¶1–¶5 add C++26 heterogeneous `insert(K&&)` and `insert(hint, K&&)` to `unordered_set`: both must be transparent; if an equivalent element exists there is no effect; otherwise let `h = hash_function()(x)` and construct `u` from `std::forward<K>(x)`; if `hash_function()(u) != h || contains(u)` is true, the behavior is undefined. `unordered_multiset` has no heterogeneous `insert`.

## The libc++ implementation

{{impl}} The following comes from reading the source of libc++ (`<__hash_table>`) and testing with Clang 23.

- **Layout**: `sizeof(std::unordered_map<int, int>)` is 40 bytes: the bucket array pointer and bucket count, a sentinel node containing only a next pointer, the element count, and the `float` maximum load factor (empty `Hash` and `Pred` classes take no space).
- **One linked list**: all elements are strung on a single singly linked list, and each entry of the bucket array points to the predecessor of the bucket's first node. This way, inserting or removing within a bucket only needs the predecessor, and iterating over the whole container is just one walk along the list.
- **Nodes**: a next pointer, the cached hash value (`size_t`) and the element. A node of `unordered_map<int, int>` is 24 bytes; the first insertion also allocates a 2-entry, 16-byte bucket array (verified with an allocator that prints requested sizes). Caching the hash means rehashing need not call `Hash` again.
- **Bucket-count policy**: when growing, the new bucket count is `max(2 * bc + !is_power_of_2(bc), ceil((size + 1) / max_load_factor()))`, rounded up to the next prime if it is not a power of 2. The bucket index is normally `hash % bc`, switching to `hash & (bc - 1)` when the bucket count is a power of 2 greater than 2. So successive insertions produce a sequence of primes, while `rehash(64)` gives 64 and `rehash(100)` gives 101.

`std::hash<int>` is the identity function, so with a power-of-2 bucket count, keys that are all multiples of 1024, for example, all land in the same bucket.

## Common misconceptions

!!! pitfall "Relying on iteration order"
    Iteration order is unspecified, and a rehash changes it ([[unord.req.general#9]]). Another standard library, another insertion order, or even one more call to `reserve` can produce a different order. Tests comparing two unordered containers should use `==`, which compares them as multisets.

!!! pitfall "Thinking reserve protects references"
    Insertion never invalidates references and pointers, regardless of `reserve`. What `reserve` protects is iterators: as long as the element count after insertion does not exceed the maximum load factor times the bucket count, there is no rehash and iterators stay valid ([[unord.req.general#243]]).

!!! pitfall "The attacker controls the keys, and the hash is predictable"
    `std::hash` is usually the identity function for integers and a deterministic, unseeded function for strings. If keys come from untrusted input, an attacker can craft many keys that land in the same bucket, dragging average constant-time operations down to linear time, a worst case the standard permits. In such settings, use a hash function with a random seed.

## Questions

!!! question "Question"
    After `std::unordered_map<std::string, int> m; m.reserve(100); m.max_load_factor(0.5f);`, are iterators invalidated while inserting 100 elements?

<details markdown="1">
<summary>Answer</summary>

They may be. `reserve(100)` performs `rehash(ceil(100 / 1.0))` using the maximum load factor at that time, 1.0, so the bucket count B is at least 100 (101 with libc++). The maximum load factor is then changed to 0.5, and the no-rehash condition of [[unord.req.general#243]] becomes (N + n) ≤ 0.5 × B; 100 ≤ 0.5 × 101 is false, so a rehash may happen during insertion.

The correct order is to set `max_load_factor` first and then `reserve`. As for references and pointers, they are never invalidated in either order.
</details>

## Summary

| Aspect | Rule |
|---|---|
| Access and insertion | Same as `map`: `operator[]` is `try_emplace`, `try_emplace` leaves its arguments alone, `insert_or_assign` reports whether it inserted |
| Initial state | Default bucket count is implementation-defined (0 in libc++); `max_load_factor()` is 1.0 |
| Invalidation | A rehash invalidates iterators; references and pointers are unaffected by insertion |
| Heterogeneous insertion | The key constructed from `k` must hash the same and not yet exist, otherwise UB; requires both `Hash` and `Pred` to be transparent |
| libc++ | A singly linked list plus a bucket array pointing to predecessors; nodes cache the hash; two bucket-count schemes, prime and power of 2 |
