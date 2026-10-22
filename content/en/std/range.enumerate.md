---
title: Enumerate view
summary: "C++23's views::enumerate gives both the index and the element during traversal; the index is the signed difference type, and the element is held as a reference inside a temporary tuple, so a structured binding can write back to the underlying range; all other properties follow the underlying range."
updated: 2026-10-19
---

!!! tldr
    - `for (auto [i, x] : views::enumerate(r))` gives both the index and the element, with no hand-written counter.
    - The index type is the underlying difference type `range_difference_t`, usually the signed `std::ptrdiff_t`, not `size_t`.
    - Each element is a temporary `tuple<index, element reference>`; the structured binding copies this tuple, but the reference inside still refers to the underlying range, so the underlying element can be modified through `x`.
    - The iterator category, sizedness and borrowedness are the same as the underlying range's; the iterator's `index()` returns the index directly.

```cpp run ok
#include <iostream>
#include <ranges>
#include <vector>

int main() {
  std::vector<int> vec{1, 2, 3};
  for (auto [index, value] : std::views::enumerate(vec))
    std::cout << index << ":" << value << ' ';    // 0:1 1:2 2:3
  std::cout << '\n';
}
```

This is Example 1 in [range.enumerate.overview] ¶2. In C++20, traversing with an index meant a hand-written counter or `zip(iota(0), v)`; the latter's index is an `int`, which also runs into signedness problems when compared with `v.size()`. C++23's [[P2164R9]] added `views::enumerate`.

## `views::enumerate` [range.enumerate.overview]

¶1 Each element of an `enumerate_view` represents both the position and the value of an element of the underlying sequence. ¶2 `views::enumerate(E)` is equivalent to `enumerate_view<views::all_t<decltype((E))>>(E)`, with no special cases.

`enumerate_view` requires the underlying range to satisfy the exposition-only concept *range-with-movable-references* ([[range.adaptor.helpers]]): both the reference type and the rvalue reference type of the elements must be move constructible, because they are packed into a `tuple` and returned.

## What the elements are [range.enumerate.iterator]

The iterator stores the underlying iterator `current_` and the index `pos_`, and there are three related types:

| Type | Definition | For `vector<string>` |
|---|---|---|
| `difference_type`, also the index type | `range_difference_t<Base>` | `ptrdiff_t` |
| `value_type` | `tuple<difference_type, range_value_t<Base>>` | `tuple<ptrdiff_t, string>` |
| result of `operator*` | `tuple<difference_type, range_reference_t<Base>>` | `tuple<ptrdiff_t, string&>` |

`operator*` returns a new `tuple` prvalue each time, whose second component is a reference to the underlying element. `auto [i, s]` first copies this tuple into a hidden variable, and `s` then names its second component ([[dcl.struct.bind]]); that component has type `string&`, so modifications through `s` write back to the underlying range. ¶6 `it.index()` returns `pos_` directly.

```cpp run ok
#include <cstdio>
#include <ranges>
#include <string>
#include <vector>

int main() {
  std::vector<std::string> v{"a", "b", "c"};
  for (auto [i, s] : std::views::enumerate(v)) {
    static_assert(std::same_as<decltype(i), std::ptrdiff_t>);
    s += std::to_string(i);                      // writes back to v
  }
  using E = decltype(std::views::enumerate(v));
  static_assert(std::same_as<std::ranges::range_reference_t<E>,
                             std::tuple<std::ptrdiff_t, std::string&>>);
  static_assert(std::ranges::random_access_range<E> && std::ranges::sized_range<E>);

  auto it = std::ranges::begin(std::views::enumerate(v)) + 2;
  std::printf("%td %s %s\n", it.index(), v[0].c_str(), v[2].c_str());   // 2 a0 c2
}
```

Calling `ranges::begin` on a temporary `enumerate_view` at the end is valid: `enumerate_view<ref_view<...>>` is a [[g:borrowed-range|borrowed range]], and its iterators do not depend on the view object, so they stay valid after the view is destroyed ([[range.access]]).

`iter_move` returns `tuple<difference_type, range_rvalue_reference_t<Base>>`, i.e. the index plus an rvalue reference to the element.

### Other properties of the iterator

- ¶1 The iterator category is the same as the underlying range's, up to random access. `iterator_category` is always `input_iterator_tag`, because dereferencing does not yield a reference.
- ¶12–¶13 Comparing two iterators compares only their indices, and `it1 - it2` is the difference of the indices too (¶17).
- When the underlying range is forward, common and sized, `end()` returns an iterator whose index is `distance(base_)`, and the result is a common range; otherwise it returns a sentinel, which compares only against the underlying iterator.
- `size()` and `reserve_hint()` are forwarded to the underlying range, and borrowedness is the same as the underlying range's.

## Compared with `zip(iota(0), r)`

| | `enumerate(r)` | `zip(iota(0), r)` |
|---|---|---|
| Index type | `range_difference_t<R>`, signed | deduced as `int` from `0` |
| Common range | when the underlying range is forward, common and sized | the unbounded `iota` makes the result not common ([[range.zip]]) |
| Getting the index | `it.index()` | `std::get<0>(*it)` |
| Borrowed range | when the underlying range is | when both are |

<details class="fine" markdown="1"><summary>Remaining wording</summary>

[range.enumerate.view] ¶1: the constructor stores the underlying view.

[range.enumerate.iterator] ¶2–¶5 are the constructors and `base()`; ¶7–¶11 are increment, decrement, `+=` and `-=`, which move the underlying iterator and the index together; ¶14–¶16 add and subtract integers to and from iterators. The sentinel in [range.enumerate.sentinel] stores the underlying end, and comparison and subtraction are based on the underlying iterator.

</details>
