---
title: Filter view
summary: "filter_view keeps only the elements that satisfy a predicate. To make begin() amortized constant time it caches the first result, which brings no const begin, stale results after the underlying range changes, and data races on concurrent begin calls; modifying elements so that they no longer satisfy the predicate can also lead to undefined behavior."
updated: 2026-10-19
---

!!! tldr
    - `views::filter(pred)` keeps only the elements that satisfy `pred`. The iterator is at most bidirectional, the view has no `size()`, and it is not a borrowed range.
    - The first call to `begin()` needs a linear search, and the standard requires the result to be cached in the view, so later calls are O(1).
    - The cache has to be written into the view, so `begin()` is not a const member: when the underlying range is a forward range, a `const filter_view` cannot be traversed.
    - Modifying the underlying range after the first `begin()` makes the same view give stale results; two threads calling `begin()` on the same view at once is a data race.
    - Modifying an element through the iterator so that it no longer satisfies the predicate can lead to undefined behavior. The predicate must be equality-preserving and stateless.

## Basic usage [range.filter.overview]

```cpp run ok
#include <ranges>
#include <vector>
#include <cstdio>
int main() {
  std::vector<int> is{0, 1, 2, 3, 4, 5, 6};
  auto evens = std::views::filter(is, [](int i) { return i % 2 == 0; });
  for (int i : evens) std::printf("%d ", i);   // 0 2 4 6
  std::puts("");
}
```

¶1 `filter_view` presents the elements of an underlying sequence that satisfy a predicate. ¶2 `views::filter` is a range adaptor object ([[range.adaptors]]), and `views::filter(E, P)` is equivalent to `filter_view(E, P)`. ¶3 Example 1 is the code above.

## The class template [range.filter.view]

```cpp
template<input_range V, indirect_unary_predicate<iterator_t<V>> Pred>
  requires view<V> && is_object_v<Pred>
class filter_view : public view_interface<filter_view<V, Pred>> {
  V base_ = V();
  movable-box<Pred> pred_;
  template<bool> class iterator;
  template<bool> class sentinel;
public:
  constexpr explicit filter_view(V base, Pred pred);
  constexpr const Pred& pred() const;

  constexpr iterator<false> begin();
  constexpr iterator<true> begin() const
    requires (input_range<const V> && !forward_range<const V> &&
              indirect_unary_predicate<const Pred, iterator_t<const V>>);

  constexpr auto end();       // returns an iterator if the underlying range is a common_range, otherwise a sentinel
  constexpr sentinel<true> end() const requires /* same as above */;
};
template<class R, class Pred>
  filter_view(R&&, Pred) -> filter_view<views::all_t<R>, Pred>;
```

- The predicate's constraint `indirect_unary_predicate` requires it to be callable with lvalues of the underlying iterator's reference type and value type ([[indirectcallable.indirectinvocable]]). It refines `regular_invocable`, so the predicate must be equality-preserving: it always gives equal results for equal inputs ([[concepts.equality]], [[concepts.callable]]).
- The predicate is stored in a *movable-box* ([[range.move.wrap]]), so lambdas with captures work. Since C++23, move-only predicates work too ([[P2494R2]]).
- No `size()`: you cannot know how many elements satisfy the predicate without traversing, so `filter_view` is never a `sized_range`.
- When the underlying range is a common range, `end()` returns an iterator to the underlying end and `filter_view` is common too; otherwise it returns a sentinel.

## Caching in begin() (¶3–¶7)

¶3 The precondition of `begin()` is `pred_.has_value()`: a *movable-box* can become empty if construction throws during assignment. ¶4 It returns an iterator to `ranges::find_if(base_, ref(*pred_))`, i.e. the first element that satisfies the predicate.

[[range.range]] ¶2.2 requires `begin()` to be amortized constant time, while finding the first element that satisfies the predicate takes linear time. The only way is to remember it after the first search, which is exactly what ¶5 specifies:

!!! std
    In order to provide the amortized constant time complexity required by the range concept when filter_view models forward_range, this function caches the result within the filter_view for use on subsequent calls.

This *Remarks* sentence is normative; implementations must cache ([[g:begin-caching]]). The cache is written into the `filter_view` object, so this `begin()` is not a const member function.

¶6–¶7 are wording added after C++23: there is a const `begin()` only when `const V` is an input range but not a forward range, and Note 1 says it does not cache. An input range can be traversed only once, and its `begin()` was never required to be equality-preserving ([[range.range]] ¶2.3), so there is no need to cache to meet the complexity requirement. For forward underlying ranges such as `vector` and `list`, a `const filter_view` still cannot be traversed.

!!! impl "libc++"
    libc++'s `filter_view` stores the cache only when the underlying range is a forward range (`__non_propagating_cache<iterator_t<V>>`, otherwise an empty type), consistent with the intent of the specification. As of the libc++ shipped with Clang 23, it does not yet provide the const `begin()` for input underlying ranges, and the iterator is not yet `template<bool Const>`.

## The iterator [range.filter.iterator]

The iterator stores the underlying iterator `current_`, and also a pointer `parent_` to the parent view, because `++` needs the predicate. Since the iterator depends on the view object, `filter_view` is not a borrowed range.

¶2 The rule for `iterator_concept` is: when `Const` is true it is an input iterator; otherwise it is bidirectional if the underlying range is bidirectional, forward if the underlying range is forward, and input otherwise. It is never random access, because skipping n elements that satisfy the predicate cannot be constant time. ¶3 The C++17-style `iterator_category` is declared only when the underlying range is a forward range, and likewise goes up to `bidirectional_iterator_tag` at most.

¶8 `operator*` returns a reference to the underlying element directly, so elements are writable. ¶10 `++` searches for the next element satisfying the predicate, starting from the next position:

```cpp
current_ = ranges::find_if(std::move(++current_), ranges::end(parent_->base_),
                           ref(*parent_->pred_));
```

¶12 `--` keeps stepping back until it meets an element that satisfies the predicate: `do --current_; while (!invoke(*parent_->pred_, *current_));`. There is no lower-bound check here; stepping back from `begin()` goes past the start of the underlying range and violates the precondition.

¶1 Note 1 gives a warning:

!!! std
    Modification of the element a filter_view::iterator denotes can result in undefined behavior if the underlying range is a forward_range and the resulting value does not satisfy the filter predicate when the predicate is next evaluated for that element

The reason is that both the cached `begin()` and any iterator in use assume they point to elements that satisfy the predicate. Once an element is changed so that it no longer does, that assumption fails and the premise of the algorithm is broken.

## Common pitfalls

### A const filter_view cannot be traversed

```cpp run error
#include <ranges>
#include <vector>
void print(const auto& r) { for (int x : r) (void)x; }
int main() {
  std::vector<int> v{1, 2, 3, 4};
  auto ev = v | std::views::filter([](int x) { return x % 2 == 0; });
  print(ev);   // error: const filter_view has no begin()
}
```

The fix is to make the parameter a forwarding reference `auto&&`, or take it by value as `std::ranges::view auto`. This is not unique to `filter_view`; every view that caches `begin()` has it: `drop_while_view`, `split_view` and `chunk_by_view` have no const `begin`; neither do `drop_view` when the underlying range is not random access and sized, or `reverse_view` when the underlying range is not common.

### Modifying the underlying range after the first begin()

```cpp run ok
#include <ranges>
#include <vector>
#include <cstdio>
int main() {
  std::vector<int> v{1, 2, 3, 4};
  auto ev = v | std::views::filter([](int x) { return x % 2 == 0; });
  auto copy = ev;           // copying the view: the cache is not copied along
  (void)ev.begin();         // ev caches an iterator to 2
  v[0] = 0;
  std::printf("%d %d\n", *ev.begin(), *copy.begin());   // 2 0
}
```

After `v[0] = 0`, the first element satisfying the predicate is actually `0`, but `ev.begin()` still gives the cached `2`. Same view, same underlying data, yet the result of traversal depends on whether `begin()` was called before. `copy` did not inherit the cache (the cache does not propagate, see [[range.nonprop.cache]]), so it searches again and gets `0`.

So it is best to use a view once soon after creating it and then discard it; when the underlying range may change, create the view anew. If a modification makes the underlying range reallocate (e.g. `v.push_back(...)`), the cached iterator is invalidated, and calling `ev.begin()` again is {{ub}}.

### Using filter to modify elements so they no longer satisfy the predicate

```cpp run ub
#include <ranges>
#include <vector>
#include <cstdio>
int main() {
  std::vector<int> v{2, 4, 6};
  auto ev = v | std::views::filter([](int x) { return x % 2 == 0; });
  for (int& x : ev) x += 1;     // make them all odd
  for (int x : ev) std::printf("%d ", x);   // UB: the cached begin points to 3, which fails the predicate
  std::puts("");
}
```

Built with Clang 23 in our tests, the second loop prints `3`: a view that filters even numbers yields an odd one. By ¶1 Note 1, this is undefined behavior. When you need to change matching elements so they no longer match, use `std::ranges::for_each` with a hand-written condition, or collect the elements into a container first.

### Stateful predicates

```cpp
int n = 0;
auto first3 = v | views::filter([&n](int) { return n++ < 3; });
// violates the semantic requirements of regular_invocable
```

The predicate may be called on both `++` and `--`, and `filter` does not guarantee one call per element; bidirectional traversal calls it again. A stateful predicate is not equality-preserving, and the behavior is not guaranteed. To take the first 3 elements, use `views::take(3)`.

### Concurrent calls to begin()

The standard library only guarantees that concurrent calls to const member functions do not cause data races ([[res.on.data.races]]). `filter_view::begin()` is not const; it writes the cache. Two threads calling `begin()` on the same `filter_view` object at once, for example both traversing it with a range-based `for`, is a data race and undefined behavior {{ub}}. Give each thread its own copy of the view; copies do not share the cache.

### The function is called twice when combined with transform

In `transform | filter`, `filter` dereferences once to test, calling the transform function once; reading the element dereferences again and calls it again. See [[range.transform]].

## Questions

!!! question "Question 1"
    Why doesn't the standard implement the cache with a `mutable` member and so provide a const `begin()`?

<details markdown="1">
<summary>Answer</summary>

Then a const member function would write shared state, breaking the convention of [[res.on.data.races]] that concurrent calls to const members of library types are safe. Either it would need a lock, with extra overhead, or const members would stop being thread-safe, breaking the convention for the whole library. The standard chose not to provide const traversal and to put "the cache belongs to this object" into the type.
</details>

!!! question "Question 2"
    When the underlying range is an `istream_view`, does `filter_view` cache `begin()`?

<details markdown="1">
<summary>Answer</summary>

No, and it does not need to. ¶5 only requires caching when `filter_view` models `forward_range`. An input range can be traversed only once, and its `begin()` was never required to be equality-preserving ([[range.range]] ¶2.3). The current draft also provides a non-caching const `begin()` for the case where `const V` is an input but not forward range (¶6–¶7).
</details>

## Summary

| Property | `filter_view` |
|---|---|
| Iterator strength | at most bidirectional |
| sized | never |
| common | when the underlying range is common |
| borrowed | no |
| traversable as const | no; except for input-but-not-forward underlying ranges |
| `begin()` | O(n) the first time, O(1) afterwards; the result is cached |
| writable elements | yes, but changing them so they fail the predicate may be UB |
