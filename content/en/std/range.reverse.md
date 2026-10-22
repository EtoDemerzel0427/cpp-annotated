---
title: Reverse view
summary: "views::reverse traverses a bidirectional view backwards: two reversals cancel out, and a reversed subrange is unwrapped back to the original iterators; when the underlying range is not common, begin() has to walk to the end first and cache the result, so it loses its const begin()."
updated: 2026-10-19
---

!!! tldr
    - `views::reverse` only accepts bidirectional ranges; ranges such as `forward_list` and `istream_view` cannot be reversed.
    - `x | views::reverse | views::reverse` gives a view of `x` itself directly, and a reversed `subrange` is unwrapped back into a forward `subrange`.
    - The iterator of `reverse_view` is just `std::reverse_iterator`, and the result is always a common range.
    - When the underlying range is not common, `begin()` has to walk from the start to the end to find the last element; the result is cached, so there is no const `begin()`.

```cpp run ok
#include <cstdio>
#include <ranges>
#include <vector>

int main() {
  std::vector<int> is{0, 1, 2, 3, 4};
  for (int i : is | std::views::reverse)
    std::printf("%d ", i);                     // 4 3 2 1 0
  std::puts("");
}
```

This is Example 1 in [range.reverse.overview] ¶3. What `reverse_view` does is simple: it wraps the underlying `end()` and `begin()` in `std::reverse_iterator` ([[reverse.iterators]]) and uses them as the new `begin()` and `end()`. Two things are worth noting: the cases where no wrapping is needed at all, and what happens when the underlying range has no end iterator.

## Cases that are not wrapped [range.reverse.overview]

¶1 `reverse_view` takes a bidirectional view and produces another view that iterates the same elements in reverse order. ¶2 `views::reverse(E)` checks in order:

- ¶2.1 `E` is itself a `reverse_view`: the result is `E.base()`; the two reversals cancel out and the type goes back to the original view.
- ¶2.2 {{c++26}} `E` is an `optional` that models `view`: a copy of `E` is returned as is. It has at most one element, so reversing changes nothing.
- ¶2.3 `E` is a `subrange<reverse_iterator<I>, reverse_iterator<I>, K>`: the forward iterators inside are extracted, giving `subrange<I, I, K>(E.end().base(), E.begin().base())`; when `K` says the size is stored, the size is passed along too.
- ¶2.4 Otherwise: `reverse_view{E}`.

```cpp run ok
#include <ranges>
#include <vector>

std::vector<int> v{1, 2, 3};

auto rr = v | std::views::reverse | std::views::reverse;      // ¶2.1
static_assert(std::same_as<decltype(rr), std::ranges::ref_view<std::vector<int>>>);

auto sr = std::ranges::subrange(v.rbegin(), v.rend()) | std::views::reverse;   // ¶2.3
static_assert(std::same_as<decltype(sr), std::ranges::subrange<std::vector<int>::iterator>>);

int main() {}
```

## When the underlying range has no end iterator [range.reverse.view]

A `reverse_iterator` can only be constructed from an iterator, not from a sentinel. Reverse traversal starts at the position just past the last underlying element; if the underlying `end()` returns a sentinel, you must first walk step by step from `begin()` to the sentinel to obtain a real iterator.

¶2 So when the underlying range is not a [[g:common-range|common range]], `begin()` returns `make_reverse_iterator(ranges::next(ranges::begin(base_), ranges::end(base_)))`, which takes n steps. ¶3 To meet the `range` concept's requirement that `begin()` be amortized constant time, the result is cached in the view, so in this case there is no const `begin()`.

¶4 When the underlying range is common, `begin()` is just `make_reverse_iterator(ranges::end(base_))`, O(1), and there is also a const version when `const V` is common too. ¶5 `end()` is always `make_reverse_iterator(ranges::begin(base_))`.

```cpp run ok
#include <cstdio>
#include <ranges>
#include <vector>

int main() {
  std::vector<int> v{1, 2, 3, 4, 5};

  auto cr = v | std::views::reverse;                  // underlying range is common
  static_assert(std::ranges::range<const decltype(cr)>);

  auto tw = v | std::views::take_while([](int x) { return x < 4; });   // bidirectional, but the end is a sentinel
  auto r = tw | std::views::reverse;                  // begin() walks to the end and caches
  static_assert(!std::ranges::range<const decltype(r)>);
  for (int x : r) std::printf("%d ", x);              // 3 2 1
  std::puts("");
}
```

Other properties of `reverse_view`:

- Both begin and end are `reverse_iterator<iterator_t<V>>`, so the result is always a common range.
- The iterator category is the same as the underlying range's, up to random access; `reverse_iterator` is not a contiguous iterator.
- `size()` and `reserve_hint()` are forwarded to the underlying range; it is a [[g:borrowed-range|borrowed range]] when the underlying range is.

## Caching in drop

In [[range.drop]], `drop_view` and `drop_while_view` cache `begin()`, and the note gives `reverse_view` as precisely the reason: `reverse_view::end()` calls the underlying `begin()` every time, and if the underlying range had to walk n steps again each time, the total cost of reverse traversal would be quadratic.

## Common misconceptions

!!! pitfall "Iterators whose dereference returns a reference into themselves"
    `reverse_iterator`'s `operator*` is equivalent to `{ auto tmp = current; return *--tmp; }`: it dereferences a local copy and returns the result. If the underlying iterator's dereference returns a reference into the iterator object itself, the returned reference dangles as soon as `tmp` is destroyed.

    [[iterator.concept.forward]] requires references obtained from a forward iterator to stay valid as long as the range is valid; such an iterator does not meet that semantic requirement, so conforming bidirectional views do not have this problem. When a hand-written iterator violates the requirement, `views::reverse` leads to {{ub}}.

<details class="fine" markdown="1"><summary>Remaining wording</summary>

[range.reverse.view] ¶1: the constructor stores the underlying view. The deduction guide `reverse_view(R&&)` wraps `R` into a view via `views::all_t`.

</details>
