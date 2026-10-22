---
title: Ordered associative container requirements
summary: "The contract shared by set, map, multiset and multimap: the comparator must be a strict weak ordering, key equivalence is decided by the comparator, plus the complexity, invalidation rules, heterogeneous lookup and exception safety of each operation."
updated: 2026-10-19
---

!!! tldr
    - The comparator must induce a strict weak ordering on the keys, and must always give the same result for the same pair of keys. Using `<=` as the comparator violates this, and the behavior is undefined.
    - Two keys are equivalent when `comp(a, b)` and `comp(b, a)` are both false. The container never calls `operator==`.
    - Insertion invalidates no iterators or references, and erasure invalidates only the erased elements; after `extract` pointers stay valid, but the element must not be accessed through them while it sits in a node handle.
    - Hinted insertion is amortized constant time when the element goes right before the hint; construction from a sorted range is linear.
    - Only with a comparator that declares `is_transparent`, such as `std::less<>`, do `find` and the other lookup functions accept arguments of a type other than the key type, without first constructing a temporary key object.

`set`, `multiset`, `map` and `multimap` are the standard library's four **ordered associative containers**: they store elements sorted by key, and lookup, insertion and erasure take logarithmic time. This subclause specifies their common requirements; each container's own clauses ([[associative]]) only add the differences. The container adaptors `flat_map`, `flat_set` and friends also reuse most of the terminology here ([[flat.map]], [[flat.set]]).

## Get the comparator wrong and the map breaks [associative.reqmts.general]

```cpp title="less-equal.cpp" run ub
#include <cstdio>
#include <functional>
#include <map>

int main() {
  // UB: less_equal is not a strict weak ordering
  std::map<int, int, std::less_equal<int>> m;
  m[1] = 10;
  m[1] = 20;
  std::printf("size=%zu find=%d\n",
              m.size(), m.find(1) != m.end());
}
```

With libc++ (Clang 23) this prints `size=2 find=0`: a unique-key `map` ends up with two keys equal to 1, and `find(1)` finds neither. This is one manifestation of violating a precondition; the standard does not guarantee any particular symptom.

### Strict weak ordering (¶2)

¶2 Each associative container is parameterized on a key type `Key` and an ordering relation `Compare` that must induce a **strict weak ordering** ([[g:strict-weak-ordering]], defined in [[alg.sorting]]) on the elements of `Key`. The object of type `Compare` is called the container's **comparison object**. `map` and `multimap` additionally associate a mapped type `T` with the key.

A relation `comp` is a strict weak ordering if it satisfies three conditions:

1. Irreflexive: `comp(a, a)` is false;
2. Transitive: `comp(a, b)` and `comp(b, c)` imply `comp(a, c)`;
3. Incomparability is transitive too: if `a` is incomparable with `b` and `b` with `c`, then `a` is incomparable with `c`. Here incomparable means `!comp(a, b) && !comp(b, a)`.

Condition 3 makes incomparability an equivalence relation that partitions the keys into equivalence classes, which are totally ordered among themselves. `<=` violates condition 1: `comp(k, k)` is true, so no key is equivalent to itself, which is why each `m[1]` in the example fails to find the existing 1.

### Equivalence is not equality (¶3)

!!! std
    two keys k1 and k2 are considered to be equivalent if for the comparison object comp, comp(k1, k2) == false && comp(k2, k1) == false.

¶3 The **equivalence** of two keys is decided entirely by the comparison object. Note 1 points out that this is not necessarily the same as the result of `k1 == k2`: the container never calls `operator==` to decide whether two keys are the same.

The same paragraph also requires that, for any two keys in the container, `comp(k1, k2)` always returns the same value. The comparator cannot have state that changes over time, and keys cannot be modified in the container to an extent that changes their relative order.

## Unique keys and equivalent keys (¶4–¶6)

¶4 `set` and `map` support **unique keys**: at most one element per key. `multiset` and `multimap` support **equivalent keys**: there may be multiple equivalent keys. For the latter two, `insert`, `emplace` and `erase` preserve the relative order of equivalent elements.

```cpp title="multimap-order.cpp" run ok
#include <cassert>
#include <map>
#include <string>

int main() {
  std::multimap<int, std::string> m;
  m.emplace(1, "a");
  m.emplace(2, "x");
  m.emplace(1, "b");                  // goes to the end of the equivalent range
  m.emplace_hint(m.begin(), 1, "c");  // inserted as close as possible to just before the hint
  auto [lo, hi] = m.equal_range(1);
  std::string seq;
  for (auto i = lo; i != hi; ++i) seq += i->second;
  assert(seq == "cab");
}
```

¶5 For the `set` family the value type is the key type; for the `map` family it is `pair<const Key, T>`. The `const` on the key prevents users from modifying keys through iterators and scrambling the order.

¶6 The iterators are bidirectional iterators. When the value type is the key type (the `set` family), `iterator` and `const_iterator` are both constant iterators, and whether they are the same type is unspecified. Note 2 therefore recommends always writing `const_iterator` in function parameters: otherwise `void f(set<int>::iterator); void f(set<int>::const_iterator);` is two overloads on one implementation and a redefinition on another.

## Complexity of the operations

The requirements table (¶8–¶174) lists the return type, preconditions, effects and complexity of each expression. Here are the highlights:

| Operation | Complexity | Notes |
|---|---|---|
| `X(i, j)`, `X(from_range, rg)` | N log N; linear if the range is already sorted | ¶25, ¶28, ¶31 |
| `emplace`, `insert(t)` | Logarithmic | Unique keys return `pair<iterator, bool>`; equivalent keys insert at the end of the equivalent range (¶54, ¶68) |
| `emplace_hint(p, …)`, `insert(p, t)` | Logarithmic; amortized constant if inserted right before `p` | ¶60, ¶74 |
| `insert(i, j)`, `insert_range(rg)` | N log(size + N) | The source range must not refer into `a` itself |
| `insert(nh)`, `insert(p, nh)` | Same as single-element insertion | See [[container.node]] |
| `extract(k)` / `extract(q)` | Logarithmic / amortized constant | ¶103, ¶111 |
| `erase(k)` | log(size) + count(k) | ¶121 |
| `erase(q)` | Amortized constant | ¶129 |
| `erase(q1, q2)` | log(size) + N | ¶137 |
| `find`, `count`, `contains`, `lower_bound`, `upper_bound`, `equal_range` | Logarithmic (`count` adds the number of results) | ¶141–¶174 |

A few points worth noting:

- Requiring linear construction from a sorted range rules out the naive implementation that inserts element by element in logarithmic time. The implementation has to exploit the fact that each new element always goes at the rightmost end, inserting with `end()` as the hint each time.
- `erase(q)` is amortized constant: a single erasure may take O(log n) time to rebalance or find the successor, but averaged out it is constant.
- `lower_bound(k)` returns the first element not less than `k`, `upper_bound(k)` the first element greater than `k`, and `equal_range(k)` is the range formed by the two.
- For unique-key containers, `emplace` has to construct the `value_type` object before it has a key to compare; if the key already exists, that object is destroyed again. `map::try_emplace` ([[associative]]) was designed to avoid this waste.

## Invalidation (¶175–¶176)

!!! std
    The insert, insert_range, and emplace members shall not affect the validity of iterators and references to the container, and the erase members shall invalidate only iterators and references to the erased elements.

¶175 Insertion never invalidates any iterator or reference; erasure invalidates only iterators and references to the erased elements. This follows from the node-based implementation: each element lives in its own node, and its address never changes.

¶176 `extract` invalidates only iterators to the extracted element; pointers and references to it remain valid. But accessing the element through them while it is owned by a node handle is {{ub}}; once the element is successfully inserted into a container, pointers and references obtained while the handle held it are invalidated. This rule lets the "extract, change the key, reinsert" sequence work without relocating the element ([[container.node]]).

### merge (¶112–¶117)

`a.merge(a2)` attempts to extract each element of `a2` and insert it into `a` using `a`'s comparison object. The precondition is that the two containers' allocators compare equal. For unique-key containers, an element whose key has an equivalent in `a` stays in `a2`.

```cpp title="merge.cpp" run ok
#include <cassert>
#include <set>

int main() {
  std::set<int> a{1, 2, 3}, b{3, 4, 5};
  auto it = b.find(4);
  const int* p = &*it;
  a.merge(b);                       // moves nodes, does not copy elements
  assert((a == std::set<int>{1, 2, 3, 4, 5}));
  assert((b == std::set<int>{3}));  // a already has 3: it stays in b
  assert(p == &*a.find(4));         // the pointer refers to the same element
  assert(it == a.find(4));          // it is now an iterator into a
}
```

¶115 Pointers and references to transferred elements keep referring to the same elements, which now belong to `a`. If `a.begin()` and `a2.begin()` have the same type, iterators also keep referring to the same elements and now behave as iterators into `a`. ¶116 `merge` throws nothing unless the comparison object throws; ¶117 the complexity is N log(a.size() + N).

## Heterogeneous lookup (¶7, ¶180)

```cpp title="heterogeneous-lookup.cpp" run ok
#include <cassert>
#include <set>
#include <string>
#include <string_view>

int main() {
  std::set<std::string, std::less<>> s{"apple", "banana"};
  std::string_view key = "apple";
  assert(s.contains(key));         // no temporary std::string is constructed
  s.erase(s.find(key));
  assert(s.count("banana") == 1);  // const char* is compared with string directly

  std::set<std::string> plain{"apple"};
  // plain.find(key);  // error: less<string> is not transparent,
  //                   // and string_view does not implicitly convert to string
  assert(plain.find(std::string(key)) != plain.end());
}
```

¶180 `find`, `count`, `contains`, `lower_bound`, `upper_bound`, `equal_range`, `erase` and `extract` each have a member function template version that accepts an argument of any type. These templates participate in overload resolution only if `Compare::is_transparent` is valid and denotes a type.

!!! std
    The member function templates find, count, contains, lower_bound, upper_bound, equal_range, erase, and extract shall not participate in overload resolution unless the qualified-id Compare::is_transparent is valid and denotes a type.

A comparator that declares `is_transparent` is called a **transparent comparator** ([[g:transparent-comparator]]). `std::less<>` (that is, `less<void>`) is transparent; `std::less<std::string>` is not. Users must opt in explicitly to protect existing code: calling `find` with a value implicitly convertible to `Key` used to mean "convert, then compare"; if the template versions participated in overload resolution unconditionally, the meaning of those calls would silently change.

The same paragraph says that the template versions of `erase` and `extract` do not participate in overload resolution when the argument is convertible to `iterator` or `const_iterator`, so that `erase(it)` is not hijacked by the template.

¶7 specifies the conditions heterogeneous arguments must meet. Let `x` range over the keys of the container's elements and `c` be the comparison object:

| Notation | Condition | Used by |
|---|---|---|
| `kl` | The container is partitioned with respect to `c(x, kl)` | `lower_bound` |
| `ku` | The container is partitioned with respect to `!c(ku, x)` | `upper_bound` |
| `ke` | Partitioned with respect to both `c(x, ke)` and `!c(ke, x)`, with the former implying the latter | `find`, `count`, `contains`, `equal_range` |
| `kx` | As for `ke`, and not convertible to `iterator` or `const_iterator` | `erase`, `extract` |

Partitioned ([[alg.sorting]]) means all elements satisfying the condition come before all elements that do not. That is exactly the weakest condition under which binary search works: the heterogeneous key need not form a strict weak ordering with the keys in the container; it only has to split the ordered sequence into a front part and a back part.

!!! impl
    The heterogeneous `erase` and `extract` were added in C++23. libc++ in Clang 23 does not define `__cpp_lib_associative_heterogeneous_erasure`, and `s.erase(key)` does not compile, which is why the example uses `s.erase(s.find(key))`.

## Other guarantees

### Iteration order (¶177–¶178)

¶177 The fundamental property of associative container iterators is that they iterate in non-descending order of keys, where non-descending is defined by the comparison used to construct the container: for any two dereferenceable iterators `i` and `j` such that the distance from `i` to `j` is positive, `value_comp(*j, *i) == false`. ¶178 Unique-key containers satisfy the stronger condition `value_comp(*i, *j) != false`.

### The comparison object is held by value (¶179)

¶179 Even when the comparison object is passed to the constructor by reference, the container must not store a pointer or reference to it. When a container is copied, the target uses the source's comparison object as if it had been passed at construction. So a stateful comparator is copied into the container.

### Deduction guides (¶181)

¶181 During class template argument deduction, a deduction guide does not participate in overload resolution if it deduces for `Compare` a type that qualifies as an allocator (two other rules exclude an `InputIterator` that does not look like an iterator and an `Allocator` that does not look like an allocator). This way `alloc` in `std::map m(first, last, alloc);` is not mistaken for a comparator.

### Exception safety [associative.reqmts.except]

¶1 `clear()` does not throw; `erase(k)` throws only if the comparison object throws.

¶2 For `insert` or `emplace` of a single element, if any operation throws, the insertion has no effect: the strong exception guarantee.

¶3 `swap` throws only if the `swap` of the comparison object throws.

## Questions

!!! question "Question 1"
    What happens if you insert NaN into a `std::set<double>`?

<details markdown="1">
<summary>Answer</summary>

`std::less<double>` is not a strict weak ordering over values that include NaN. NaN is incomparable with every value, so NaN is incomparable with 1.0 and with 2.0, while 1.0 and 2.0 are comparable: incomparability is no longer transitive. Paragraph 2 requires `Compare` to induce a strict weak ordering on the container's keys; inserting NaN violates that requirement, and the behavior is undefined. Common symptoms are NaN being treated as equivalent to some existing element so that insertion fails, or being inserted and then never found again. If you need to hold NaN, use a comparator based on `std::strong_order`, which gives a total order on floating-point values.
</details>

!!! question "Question 2"
    Why does `insert(p, t)` promise amortized constant time when the element goes right before `p`, rather than right after?

<details markdown="1">
<summary>Answer</summary>

The C++03 wording did say after `p`; C++11 changed it to before. With "before", `end()` can serve as the hint: inserting an ascending sequence with `insert(m.end(), x)` puts each new element right before `end()`, for linear total complexity, and that is how linear construction from a sorted range (¶25) can be implemented. With "after", there is no iterator that denotes the end. "Before" is also consistent with sequence containers, whose `insert(p, t)` inserts before `p`, so generic code such as `std::inserter` works efficiently with both kinds of container.
</details>

<details class="fine" markdown="1"><summary>Remaining wording</summary>

¶1 lists the four associative containers and mentions that sequence containers can be used to build adaptors such as `flat_map`.

¶7 also defines the other notation used in the requirements table: `a` and `b` are values of the container, `a_uniq` and `a_eq` denote unique-key and equivalent-key containers respectively, `a_tran` denotes a container for which `X::key_compare::is_transparent` is valid, `i` and `j` are input iterators, `p`, `q` and `r` are various iterators into `a`, `t` is a value of `value_type`, `k` a value of `key_type`, and `nh` a node handle rvalue.

¶8 `X` meets the associative container requirements if it meets all the requirements of allocator-aware containers and the expressions in the requirements table are well-formed with correct semantics. For `map` and `multimap`, the requirements that [container.reqmts] places on `value_type` apply instead to `key_type` and `mapped_type`, because `pair<const K, T>` itself is not copy-assignable.

¶9–¶17 specify the nested types: `key_type` is `Key`, `mapped_type` is `T` (only in the `map` family), `key_compare` is `Compare` and must be copy-constructible, `value_compare` equals `key_compare` for the `set` family and is a predicate comparing `pair`s by `first` for the `map` family, and `node_type` is a specialization of the node-handle template in [[container.node]].

¶18–¶45 specify the constructors, the assignment `a = il` (N log N, linear if sorted), and `key_comp()` and `value_comp()` (return the comparison object used at construction, constant time).

</details>
