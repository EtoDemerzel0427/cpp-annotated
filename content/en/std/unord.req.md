---
title: Unordered associative container requirements
summary: "The contract shared by unordered_set, unordered_map and the other hash containers: the hash function and equality predicate must agree, buckets and load factor, rehashing invalidates iterators but not references, average and worst-case complexity, and what operator== means."
updated: 2026-10-19
---

!!! tldr
    - When two keys are equivalent under the equality predicate, the hash function must give them the same value. Changing the equality predicate without changing the hash function usually violates this, and the behavior is undefined.
    - Insertion never invalidates pointers and references to elements, but it may trigger a rehash that invalidates all iterators. As long as the element count after insertion does not exceed `max_load_factor() * bucket_count()`, no rehash is guaranteed, so calling `reserve` first keeps iterators valid.
    - Lookup, insertion and erasure are constant time on average and linear in the worst case; the implementation may ignore the position hint given on insertion.
    - `==` compares two containers as multisets, independent of iteration order and bucket count.
    - Heterogeneous lookup requires both the hash function and the equality predicate to declare `is_transparent`.

C++11 added four **unordered associative containers**: `unordered_set`, `unordered_map`, `unordered_multiset` and `unordered_multimap`. They organize elements in a hash table, with constant average and linear worst-case lookup time (¶1). This subclause specifies their common requirements; each container's own clauses are in [[unord]]. Compared with the ordered associative containers ([[associative.reqmts]]), two things need the most attention: the hash function and equality predicate must agree, and rehashing invalidates all iterators.

## The hash function and the equality predicate must agree [unord.req.general]

```cpp title="hash-pred-mismatch.cpp" run ub
#include <cctype>
#include <cstdio>
#include <string>
#include <unordered_set>

struct CaseInsensitiveEq {
  bool operator()(const std::string& a,
                  const std::string& b) const {
    if (a.size() != b.size()) return false;
    for (std::size_t i = 0; i < a.size(); ++i)
      if (std::tolower((unsigned char)a[i]) !=
          std::tolower((unsigned char)b[i]))
        return false;
    return true;
  }
};

int main() {
  // UB: "ABC" and "abc" are equivalent under Pred but hash differently
  std::unordered_set<std::string, std::hash<std::string>,
                     CaseInsensitiveEq> s{"abc"};
  std::printf("%d\n", s.contains("ABC"));
}
```

In our tests this prints `0`: the hash of `"ABC"` sends the lookup to another bucket, and `CaseInsensitiveEq` never gets a chance to be called. With other strings or another bucket count, the result may become `1`. The standard places no requirements on this program.

¶3 Each unordered container has three type parameters: a key type `Key`; a hash function type `Hash` meeting the *Cpp17Hash* requirements ([[hash.requirements]]); and a binary predicate `Pred` that induces an equivalence relation on `Key`. The `unordered_map` family also associates a mapped type `T` with the key. ¶4 The container's `Hash` object is called its **hash function**, and its `Pred` object its **key equality predicate**.

¶5 Two keys are **equivalent** if `pred(k1, k2)` is valid and true.

!!! std
    If k1 and k2 are equivalent, the container's hash function shall return the same value for both.

Note 1 points out the consequence: a non-default `Pred` usually requires a non-default `Hash` as well. The fix for the example is to pair `CaseInsensitiveEq` with a hash function that lowercases the string before hashing it.

The same paragraph also requires that for any two keys in the container, `pred(k1, k2)` always returns the same value, and for any key `k` in the container, `hash(k)` always returns the same value.

## Buckets, load factor and rehashing (¶9)

¶9 Elements are organized into **buckets** ([[g:bucket]]); keys with the same hash code appear in the same bucket. The average number of elements per bucket is the **load factor** ([[g:load-factor]]). As elements are added, the container automatically increases the number of buckets to keep the load factor below `max_load_factor()`. Redistributing the elements into a new bucket array is called **rehashing**.

!!! std
    Rehashing invalidates iterators, changes ordering between elements, and changes which buckets elements appear in, but does not invalidate pointers or references to elements.

That rehashing does not invalidate pointers and references dictates the implementation: each element must have its own stable address, usually one node per element, with the nodes of a bucket linked into a list. An open-addressing implementation that stores elements directly in an array of slots has to move elements when rehashing and does not meet this requirement.

For `unordered_multiset` and `unordered_multimap`, rehashing preserves the relative order of equivalent elements.

### The bucket interface (¶192–¶239)

| Expression | Meaning |
|---|---|
| `bucket_count()` | The number of buckets |
| `bucket(k)` | The index of the bucket in which key `k` is (or would be) found; precondition `bucket_count() > 0` |
| `bucket_size(n)`, `begin(n)`, `end(n)` | The element count and local iterators of the `n`th bucket |
| `load_factor()` | The average number of elements per bucket |
| `max_load_factor()` / `max_load_factor(z)` | The upper bound on the load factor that the container tries to maintain; when setting it, `z` is only a hint |
| `rehash(n)` | Afterwards `bucket_count() >= n` and `bucket_count() >= size() / max_load_factor()` |
| `reserve(n)` | Equivalent to `rehash(ceil(n / max_load_factor()))` |

A local iterator (`local_iterator`) can only iterate within one bucket, not across buckets (¶21–¶22).

The bucket count of a default-constructed container is unspecified (¶33) and may be 0. With libc++ (Clang 23), a default-constructed `unordered_set<int>` indeed has `bucket_count()` 0, and calling `bucket(k)` on it violates the precondition and is {{ub}}. The containers in [[unord]] further specify that the bucket count on default construction is implementation-defined and that `max_load_factor()` initially returns 1.0.

## Invalidation (¶242–¶244)

!!! std
    The insert, insert_range, and emplace members shall not affect the validity of references to container elements, but may invalidate all iterators to the container.

¶242 Insertion never invalidates references to elements, but may invalidate all iterators to the container, because insertion may trigger a rehash. Erasure invalidates only iterators and references to the erased elements and preserves the relative order of the remaining elements.

¶243 gives a sufficient condition for no rehash:

!!! std
    The insert, insert_range, and emplace members shall not affect the validity of iterators if (N + n) <= z * B

where N is the number of elements before the insertion, n the number inserted, B the bucket count and z the maximum load factor. This is the only basis for continuing to use old iterators after an insertion: call `reserve(N + n)` first, and insertions within that capacity will not rehash.

```cpp title="rehash-invalidation.cpp" run ok
#include <cassert>
#include <unordered_map>

int main() {
  std::unordered_map<int, int> u;
  u.reserve(1000);          // guarantees (N + n) <= z * B
  int& ref = u[0];
  auto it = u.find(0);
  for (int i = 1; i < 1000; ++i)
    u[i] = i;               // no rehash: iterators and references stay valid
  assert(&ref == &it->second);

  u.rehash(100000);         // rehash: all iterators are invalidated
  ref = 42;                 // the reference is still valid
  assert(u.at(0) == 42);
}
```

¶244 `extract` invalidates only iterators to the extracted element; pointers and references remain valid, but accessing the element through them while it is owned by a node handle is {{ub}}, and they are invalidated once the element is successfully inserted. This is the same rule as for ordered containers ([[associative.reqmts#176]], [[container.node]]).

## Unique keys, equivalent keys and equivalent-key groups (¶6–¶8)

¶6 `unordered_set` and `unordered_map` support unique keys; the `multi` versions support equivalent keys. In an equivalent-key container, elements with equivalent keys are adjacent to each other in the iteration order. The absolute order of elements is unspecified, but they are organized into **equivalent-key groups** ([[g:equivalent-key-group]]), all keys of a group being equivalent. Unless otherwise specified, mutating operations preserve the relative order of elements within each group.

¶7–¶8 The rules for the value type and iterators are the same as for ordered containers: the value type of the `set` family is `Key`, that of the `map` family is `pair<const Key, T>`; when the value type is the key type, `iterator` and `const_iterator` are both constant iterators, whether they are the same type is unspecified, and function parameters should use `const_iterator`. ¶241 adds that the iterators are at least forward iterators.

## Complexity

Most complexities in the requirements table (¶11–¶239) come in two tiers, average and worst case. The worst case arises when many keys land in the same bucket, for example because the hash function is poor or because someone deliberately crafted colliding keys.

| Operation | Average | Worst |
|---|---|---|
| Constructors that specify a bucket count, such as `X(n, hf, eq)` | O(n) | O(n) |
| Range construction, copy construction, copy assignment | O(N) | O(N²) |
| `emplace`, `insert(t)`, `insert(nh)` | O(1) | O(size) |
| `insert(i, j)`, `insert_range(rg)` | O(N) | O(N · (size + 1)) |
| `find`, `contains`, `extract`, `erase(q)` | O(1) | O(size) |
| `count(k)`, `equal_range(k)`, `erase(k)` | O(count(k)) | O(size) |
| `rehash(n)` | O(size) | O(size²) |

The `p` in `emplace_hint(p, …)` and `insert(p, t)` is only a hint about where to start the search, and the implementation may ignore it (¶89, ¶103). Unlike the ordered containers, insertion into a `multi` version does not specify where in the equivalent-key group the new element goes; it only requires equivalent elements to be adjacent.

Unordered containers have no `lower_bound` or `upper_bound`, because their elements have no order.

### merge (¶143–¶147)

`a.merge(a2)` extracts the elements of `a2` one by one and inserts them into `a` using `a`'s hash function and equality predicate; in unique-key containers, elements whose key has an equivalent in `a` stay in `a2`. The precondition is that the two allocators compare equal.

¶146 Pointers and references to transferred elements keep referring to the same elements, which now belong to `a`. But unlike the ordered containers, iterators to transferred elements and all iterators into `a` are invalidated, because merging may trigger a rehash; iterators to elements remaining in `a2` stay valid.

## operator== compares multisets (¶240)

```cpp title="unordered-equality.cpp" run ok
#include <cassert>
#include <unordered_set>

int main() {
  std::unordered_multiset<int> a{1, 1, 2, 3}, b{3, 2, 1, 1};
  assert(a == b);
  std::unordered_set<int> c, d;
  for (int i = 0; i < 100; ++i) c.insert(i);
  for (int i = 99; i >= 0; --i) d.insert(i);
  d.rehash(1024);
  assert(c == d);   // different bucket count and iteration order, still equal
}
```

¶2 notes that `==` on unordered containers has different semantics from other containers. ¶240 specifies that two unordered containers are equal if and only if their `size()`s are equal and, for each equivalent-key group in `a`, the corresponding equivalent-key group in `b` is a permutation of it (`is_permutation` is true). So the result is independent of iteration order and bucket count.

Complexity: for unique keys, O(N) on average and O(N²) in the worst case. For equivalent keys, the average is the sum of the squares of the equivalent-key group sizes and the worst case O(N²); if the elements of corresponding groups are in the same order (for example, when one container is an unmodified copy of the other), the average drops to O(N).

¶240 ends with a UB condition:

!!! std
    The behavior of a program that uses operator== or operator!= on unordered containers is undefined unless the Pred function object has the same behavior for both containers and the equality comparison function for Key is a refinement of the partition into equivalent-key groups produced by Pred.

Footnote 173 explains refinement: no two objects that compare equal with `==` fall into different equivalent-key groups. In other words, `Key`'s `==` may be stricter than `Pred`, but not looser. If the case-insensitive container from earlier is given a consistent hash function, `"abc" == "ABC"` being false while `Pred` considers them equivalent is allowed; conversely, if `Pred` is stricter than `==`, using `==` on the containers is {{ub}}.

## Heterogeneous lookup requires both to be transparent (¶10, ¶245)

```cpp title="transparent-hash.cpp" run ok
#include <cassert>
#include <string>
#include <string_view>
#include <unordered_map>

struct SvHash {
  using is_transparent = void;   // the hash function must be transparent too
  std::size_t operator()(std::string_view s) const noexcept {
    return std::hash<std::string_view>{}(s);
  }
};

int main() {
  std::unordered_map<std::string, int, SvHash,
                     std::equal_to<>> m{{"one", 1}, {"two", 2}};
  std::string_view k = "two";
  assert(m.find(k)->second == 2);   // no std::string is constructed
  assert(m.contains("one"));
}
```

¶245 The member function template versions of `find`, `count`, `equal_range`, `contains`, `extract`, `erase` and `bucket` participate in overload resolution only if both `Pred::is_transparent` and `Hash::is_transparent` are valid; the template versions of `extract` and `erase` also exclude arguments convertible to iterators.

Why must both be transparent? Heterogeneous lookup first hashes the argument with `Hash`, then compares with `Pred`. If either one does not accept the heterogeneous argument, the argument has to be converted to `Key` first, and heterogeneous lookup becomes pointless. `std::hash<std::string>` is not transparent, so you need to write one yourself as in the example.

¶10 specifies the conditions on heterogeneous arguments `ke` and `kx`. Let `r1` and `r2` be keys of elements in the container:

- Symmetry: `eq(r1, ke) == eq(ke, r1)`;
- Hash consistency: if `eq(r1, ke)` is true, then `hf(r1) == hf(ke)`;
- Transitivity: if any two of `eq(r1, ke)`, `eq(r2, ke)` and `eq(r1, r2)` are true, all three are.

`kx` (used by `erase` and `extract`) is additionally required not to be convertible to an iterator. In other words, a heterogeneous key has to fit into `Pred`'s equivalence partition as a real key would, and hash to the same value.

## Exception safety [unord.req.except]

¶1 `clear()` does not throw; `erase(k)` throws only if the `Hash` or `Pred` object throws.

¶2 For single-element insertion, if an exception is thrown by any operation other than the hash function, the insertion has no effect. There is no such guarantee when the hash function throws.

¶3 `swap` throws only if the `swap` of `Hash` or `Pred` throws.

¶4 In `rehash()`, if an exception is thrown by an operation other than the hash function or the comparison function, `rehash()` has no effect.

So a hash function should preferably be `noexcept`.

## Questions

!!! question "Question"
    Under what conditions does the following loop have no UB? Even without UB, is its behavior determinate?
    ```cpp
    for (auto it = m.begin(); it != m.end(); ++it)
      if (cond(*it)) m.emplace(f(*it));
    ```

<details markdown="1">
<summary>Answer</summary>

Whether an insertion rehashes is decided by paragraph 243. If enough capacity was `reserve`d before the loop that (N + n) ≤ z·B always holds, iterators are not invalidated and the loop itself has no UB.

But the behavior is still not determinate. A newly inserted element may land before `it` or after it, and the iteration order is unspecified, so whether the new element is visited again in this loop is unspecified too. If the key produced by `f` also satisfies `cond`, insertions can cascade. The safe approach is to collect the elements to insert into a temporary container first and `insert_range` them after the loop.
</details>

<details class="fine" markdown="1"><summary>Remaining wording</summary>

¶10 also defines the other notation in the requirements table: `a_uniq` and `a_eq` denote unique-key and equivalent-key containers respectively, `a_tran` denotes a container for which both `key_equal::is_transparent` and `hasher::is_transparent` are valid, `hf` and `eq` are values of the hash function and equality predicate, `n` is a value of `size_type`, and `z` a value of `float`.

¶11 `X` meets the unordered associative container requirements if it meets all the requirements of allocator-aware containers and the expressions in the requirements table are well-formed with correct semantics. For the `unordered_map` family, the requirements on `value_type` apply instead to `key_type` and `mapped_type`.

¶12–¶23 specify the nested types: `hasher` is `Hash`, and `hf(k)` must have type `size_t`; `key_equal` is `Pred`, which must be copy-constructible and an equivalence relation on `Key`; `local_iterator` has the same iterator category, value type, difference type, pointer and reference types as `iterator`; `node_type` is a specialization of the node-handle template.

¶63, ¶66 Copy construction and copy assignment copy the hash function, equality predicate and maximum load factor in addition to the elements.

¶246 A deduction guide does not participate in overload resolution if it deduces an integral type or an allocator type for `Hash`, because an integer argument is usually the bucket count; likewise if it deduces an allocator type for `Pred`.

</details>
