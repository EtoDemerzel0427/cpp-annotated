---
title: Cache latest and as input views
summary: "Two views that deliberately downgrade a range to an input range: views::cache_latest stores the result of the latest dereference in the view, so an expensive function in transform followed by filter is called only once per element; views::as_input presents any range as a single-pass range whose begin and end differ in type, sparing downstream adaptors the overhead of supporting stronger capabilities."
updated: 2026-10-19
---

!!! tldr
    - `transform(f) | filter(p)` calls `f` twice for every element that passes the filter; inserting `views::cache_latest` in between makes it once.
    - `cache_latest` stores the result of the latest dereference in the view object, so the result is only an input range, has no const `begin()`, and is not a borrowed range.
    - The reference returned by `*it` is valid only until the next `++it`.
    - `views::as_input` turns any range into a single-pass range whose begin and end have different types, so downstream `join`, `chunk` and others can use simpler implementations.
    - If you traverse only once and nothing downstream dereferences repeatedly, you need neither.

```cpp
#include <cstdio>
#include <ranges>
#include <vector>

int calls = 0;
int expensive(int x) { ++calls; return x * x; }

int main() {
  std::vector<int> v{1, 2, 3, 4};
  auto r = v | std::views::transform(expensive)
             | std::views::cache_latest
             | std::views::filter([](int y) { return y % 2 == 0; });
  for (int y : r) std::printf("%d ", y);       // 4 16
  std::printf("| calls=%d\n", calls);          // calls=4; 6 without cache_latest
}
```

[[range.filter]] dereferences the underlying iterator once when testing the predicate, and again when the loop body reads the element. When the underlying range is a `transform`, every dereference calls `expensive`, so every element that passes the filter is computed twice. `cache_latest` remembers the first result and returns it directly the second time.

Most of the views covered earlier try to preserve the underlying capabilities. These two C++26 views do the opposite: they deliberately downgrade a range to an input range, trading capability for run-time efficiency. `cache_latest` comes from [[P3138R5]].

!!! impl "Implementation status"
    At the time of writing, the libc++ we test with does not yet provide `views::cache_latest` or `views::as_input`. The code on this page follows the standard's text and has not been compiled; the call counts in the comments are derived from the standard's semantics.

## `views::cache_latest` [range.cache.latest]

¶1 `cache_latest_view` caches the last-accessed element of its underlying sequence so that the element does not have to be recomputed on repeated access. Note 1 points out that this is useful when computing elements is expensive. ¶2 `views::cache_latest(E)` is equivalent to `cache_latest_view(E)`.

### The cache lives in the view [range.cache.latest.view]

`cache_latest_view` has a [[range.nonprop.cache|non-propagating-cache]] member `cache_`, and the cached type *cache-t* depends on the result of dereferencing the underlying range:

- if the result is a reference (e.g. `int&`), a pointer to the element is cached;
- if the result is a prvalue (e.g. the `int` returned by `transform`), the value itself is cached.

[range.cache.latest.iterator] ¶6 specifies `*it`: if the cache is empty, it first dereferences the underlying iterator and stores the result in the cache, then returns the cached contents. The return type is `range_reference_t<V>&`, so even when the underlying range returns a prvalue, what you get here is an lvalue reference to the cached object. ¶4 `++it` first empties the cache and then advances the underlying iterator.

There is only one cache, in the view object, so only one meaningful iterator can exist at a time, which is exactly the semantics of an input range:

- the iterator's `iterator_concept` is `input_iterator_tag`, and the iterator is move-only, not copyable;
- [range.cache.latest.view] ¶2 `begin()` has only a non-const version, and ¶3 `end()` returns a sentinel, so the result is not a common range;
- it is not a borrowed range.

Note 1 of ¶6 also warns that concurrent calls to `operator*` on the same iterator may constitute a data race ([[intro.races]]), since both calls may write the cache.

!!! pitfall "The returned reference lives only until the next ++"
    After `auto& x = *it; ++it;`, the cache has been emptied; when the underlying range returns prvalues, the object in the cache has been destroyed. Using `x` further is {{ub}}. This is consistent with the general convention for input iterators: after an input iterator is incremented, references obtained earlier are no longer guaranteed to be valid.

`cache_latest` is meant for downstream adaptors like `filter`, `take_while` and `chunk_by` that look at an element before deciding what to do. If `transform` is followed directly by a `for` loop or `ranges::to`, each element is dereferenced only once anyway, and adding it would only cost the range its forward capability.

## `views::as_input` [range.as.input]

¶1 `as_input_view` presents a view of an underlying sequence as an input-only non-common range. Note 1 explains the purpose: avoiding overhead that may be necessary to provide support for stronger iterator categories.

¶2 Let `T` be `decltype((E))`. `views::as_input(E)` is equivalent to:

- ¶2.1 `views::all(E)` if `T` is an input range that is neither a common range nor a forward range, since it already meets the requirements;
- ¶2.2 otherwise `as_input_view(E)`.

[range.as.input.view] ¶2–¶3 `begin()` wraps the underlying iterator in `as_input_view`'s own iterator ([range.as.input.iterator]), whose category is `input_iterator_tag` and which is move-only. ¶4 `end()` returns the underlying `end()` directly, which differs in type from the wrapped iterator, so the result is not a common range. ¶5 `size()` is forwarded to the underlying range. It caches nothing, has a const `begin()`, and has the same borrowedness as the underlying range.

### What downgrading buys

Many adaptors have to do more when the underlying range is more capable:

- [[range.join]]: when the outer range is a forward range, the iterator must store both the outer and the inner iterator; when the outer range is only an input range, the outer iterator lives in the view and the iterator is smaller.
- [[range.chunk]]: the input-range version of `chunk_view` does not need to record how many elements the last chunk is short by, nor support random jumps.
- [[range.filter]], [[range.drop]] and others need to cache `begin()` only when the underlying range is a forward range.

If you intend to traverse only once, `as_input` tells downstream adaptors not to prepare for multiple passes, reverse traversal or random access, which sometimes buys smaller iterators and fewer branches.

```cpp
#include <cstdio>
#include <ranges>
#include <vector>

int main() {
  std::vector<std::vector<int>> vv{{1, 2}, {3}};
  auto j = vv | std::views::as_input | std::views::join;
  static_assert(std::ranges::input_range<decltype(j)>);
  static_assert(!std::ranges::forward_range<decltype(j)>);
  for (int x : j) std::printf("%d", x);        // 123
  std::puts("");
}
```

## Summary

| | `cache_latest` | `as_input` |
|---|---|---|
| Purpose | avoid recomputing elements | avoid paying for stronger categories |
| Result | input range, not common | input range, not common |
| Type of `*it` | `range_reference_t<V>&`, referring to the cache | same as underlying |
| Const traversal | no | same as underlying |
| Borrowed range | no | when the underlying range is |

<details class="fine" markdown="1"><summary>Remaining wording</summary>

[range.cache.latest.view] ¶1: the constructor stores the underlying view; ¶4–¶5 `size()` and `reserve_hint()` are forwarded to the underlying range. [range.cache.latest.iterator] ¶1–¶3 are the constructor and `base()`, ¶5 is postfix `++`, and `iter_move` and `iter_swap` in ¶7–¶8 act directly on the underlying iterator, bypassing the cache. [range.cache.latest.sentinel] ¶1–¶5: the sentinel stores the underlying end, and comparison and subtraction are based on the underlying iterator.

[range.as.input.view] ¶1, ¶6: the constructor and `reserve_hint()`. The paragraphs of [range.as.input.iterator] forward the operations to the underlying iterator.

</details>
