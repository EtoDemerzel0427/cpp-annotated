---
title: Range conversions with ranges::to
summary: "C++23's ranges::to materializes a range into a container: the order in which it tries four ways of construction, how it recurses into ranges of ranges, how forms like to<vector> without an element type are deduced, and the pipe form."
updated: 2026-10-19
---

!!! tldr
    - `ranges::to<C>(r, args...)` or `r | ranges::to<C>(args...)` constructs a `C` from the elements of range `r`; `C` cannot be a view.
    - It tries in order: construction directly from the range, construction with the `from_range` tag, construction from a pair of iterators, and default construction followed by appending one element at a time (with a `reserve` first when possible).
    - When the elements cannot go into `C` directly but are themselves ranges, `to` recurses on each element, so it can turn a range of ranges into `vector<vector<int>>` or `vector<string>`.
    - `to<std::vector>()` omits the element type and gets the complete type from the container's class template argument deduction.
    - The pipe form needs parentheses: `to<std::vector>()`; extra arguments are stored by value in the closure.

## From a view to a container

Views are lazy, and often need to become a container in the end. C++20 could only go through a pair of iterators:

<div class="compare" markdown="1">

```cpp
// C++20
auto r = v | std::views::take_while(pred);
std::vector<int> out(r.begin(), r.end());
// error: take_while_view is not a common_range;
// begin and end have different types
```

```cpp
// C++23
auto out = v
  | std::views::take_while(pred)
  | std::ranges::to<std::vector>();
```

</div>

C++23's `ranges::to` ([[P1206R7]]) makes this step the last stage of the pipeline. The example below shows several ways to use it:

```cpp run ok
#include <deque>
#include <list>
#include <ranges>
#include <set>
#include <string>
#include <vector>
#include <cstdio>
int main() {
  auto sq = std::views::iota(1, 5)
          | std::views::transform([](int i) { return i * i; });
  auto v = sq | std::ranges::to<std::vector>();          // deduced as vector<int>
  auto d = std::ranges::to<std::deque<long>>(sq);        // element type conversion
  auto s = sq | std::ranges::to<std::set<int, std::greater<>>>();

  std::vector<std::list<int>> ll{{1, 2}, {3}};           // range of ranges: recurses level by level
  auto vv = ll | std::ranges::to<std::vector<std::vector<int>>>();

  auto tw = std::views::iota(0)                          // not a common_range
          | std::views::take_while([](int i) { return i < 3; });
  auto w = tw | std::ranges::to<std::vector<int>>();     // default-construct, then append one by one

  auto str = std::ranges::to<std::string>(std::views::repeat('x', 3));
  std::printf("%zu %zu %d %zu %zu %s\n",
              v.size(), d.size(), *s.begin(), vv[0].size(), w.size(), str.c_str());
  // 4 4 16 2 3 xxx
}
```

## Four ways to construct [range.utility.conv.general]

¶1 The conversion functions construct an object (usually a container) from a range in one of these ways: a constructor taking a range; a constructor tagged with `from_range_t`, which C++23 added to all standard containers; a constructor taking a pair of iterators; or default construction followed by inserting the elements one at a time.

¶3–¶5 To describe the last way, the standard defines three exposition-only tools:

- *reservable-container*: `C` is a `sized_range` and has `reserve(n)`, `capacity()` and `max_size()`;
- *container-appendable*: an element can be appended with one of `emplace_back`, `push_back`, `emplace_hint(c.end(), x)`, `insert(c.end(), x)`;
- *container-append*: appends one element using the first available way in that order.

### Order of selection [range.utility.conv.to]

```cpp
template<class C, input_range R, class... Args> requires (!view<C>)
  constexpr C to(R&& r, Args&&... args);
```

¶1 `C` must be a cv-unqualified class type. The constraint `!view<C>` means `to` is only for materializing: `to<std::string_view>(r)` is not accepted; views should be constructed by view adaptors.

¶2 The return value is constructed by the following rules.

¶2.1 If `C` is not an `input_range`, or the elements of `r` are convertible to the element type of `C` (`convertible_to<range_reference_t<R>, range_value_t<C>>`), try in order:

| Item | Condition | Action |
|---|---|---|
| ¶2.1.1 | `C` is constructible from `R, Args...` | `C(std::forward<R>(r), args...)` |
| ¶2.1.2 | `C` is constructible from `from_range_t, R, Args...` | `C(from_range, std::forward<R>(r), args...)` |
| ¶2.1.3 | `R` is a `common_range`, its iterator has a C++17-style `iterator_category`, and `C` is constructible from an iterator pair plus `Args...` | `C(ranges::begin(r), ranges::end(r), args...)` |
| ¶2.1.4 | `C` is constructible from `Args...` and elements can be appended | default-construct, reserve first if possible, then append one at a time |
| ¶2.1.5 | none of the above | ill-formed |

¶2.2 Otherwise, if the elements of `r` are themselves ranges, `to<range_value_t<C>>` is called recursively on each element, and the results are handed to the outer `to<C>`:

```cpp
to<C>(ref_view(r) | views::transform([](auto&& elem) {
  return to<range_value_t<C>>(std::forward<decltype(elem)>(elem));
}), std::forward<Args>(args)...);
```

¶2.3 Otherwise, the program is ill-formed.

¶2 Example 1 shows what the recursion is for:

```cpp
string_view str = "the quick brown fox";
auto words = views::split(str, ' ') | to<vector<string>>();
// {"the", "quick", "brown", "fox"}
```

Each element of `split` is a `subrange` denoting a run of characters. It is not implicitly convertible to `string`, but it is itself a range, so ¶2.2 applies: `to<string>` is called on each element, and that in turn uses the `from_range` construction of ¶2.1.2.

### Some details

¶2.1.3 checks for a C++17-style `iterator_category` because the iterator-pair constructors of old containers are written against the *Cpp17InputIterator* requirements. Iterators of C++20 views do not necessarily define it; for example, when the underlying range of a `transform_view` is not a `forward_range`, its iterator has no `iterator_category`. Then ¶2.1.3 does not apply, and it falls back to ¶2.1.4.

The reservation condition in ¶2.1.4 is `approximately_sized_range<R> && reservable-container<C>`, and the amount reserved comes from `ranges::reserve_hint(r)`. The original C++23 wording used `sized_range` and `ranges::size`; the current draft relaxes this to merely requiring an estimate of the element count {{c++26}}, so ranges whose size is unknown but can be bounded can also preallocate.

The condition at the start of ¶2.1, "`C` is not an `input_range`", allows conversion to a type that is not a range, as long as it can be constructed from a range, for example a statistics accumulator class that takes a range.

## Omitting the element type: to<vector> (¶3–¶5)

```cpp
template<template<class...> class C, input_range R, class... Args>
  constexpr auto to(R&& r, Args&&... args);
```

`to<std::vector>(r)` gives only the class template, and the complete `vector<int>` has to be deduced. ¶4 defines *DEDUCE_EXPR*, which tries three expressions in order, all using the container's class template argument deduction (CTAD):

1. `C(declval<R>(), declval<Args>()...)`;
2. `C(from_range, declval<R>(), declval<Args>()...)`;
3. `C(declval<input-iterator>(), declval<input-iterator>(), declval<Args>()...)`.

¶3 The *input-iterator* in item 3 is an exposition-only iterator type that meets the syntactic requirements of *Cpp17InputIterator* and has `value_type` `range_value_t<R>`; it is used to apply the container's iterator-pair deduction guides.

¶5 The deduced type is `decltype(DEDUCE_EXPR)`, and the result is `to<decltype(DEDUCE_EXPR)>(r, args...)`. For example, the elements of `views::zip(keys, values) | to<std::map>()` are `tuple`s; `map`'s iterator-pair deduction guide obtains the key and value types from elements 0 and 1 of the `tuple`, and Clang 23 deduces `map<int, std::string>` (with `int` keys and `string` values).

## The pipe form [range.utility.conv.adaptors]

```cpp
template<class C, class... Args> requires (!view<C>)
  constexpr auto to(Args&&... args);
template<template<class...> class C, class... Args>
  constexpr auto to(Args&&... args);
```

¶2 Calling `to` without a range argument returns a range adaptor closure object ([[range.adaptor.object]]), so it can go to the right of `|`. The closure stores `args` by value as `decay_t<Args>` and, when called, performs `to<C>(r, bound_args...)` ([[func.require]]). So `r | to<std::vector>(alloc)` copies the allocator into the closure.

`to` itself is not a range adaptor, since it does not return a view, but the closure it returns can be composed with other closures: `auto pipeline = views::filter(p) | ranges::to<std::vector>();` gives a closure that filters and then materializes.

<div class="compare" markdown="1">

```cpp run error
#include <ranges>
#include <string_view>
auto x = std::views::iota(0, 3)
  | std::ranges::to<std::string_view>();
// error: C cannot be a view
int main() {}
```

```cpp run error
#include <ranges>
#include <vector>
auto x = std::views::iota(0, 3)
  | std::ranges::to<std::vector>;
// error: missing (); the right-hand side is a function template
int main() {}
```

</div>

!!! pitfall "Forgetting the parentheses in to<vector>"
    `r | std::ranges::to<std::vector>` does not compile. `to<std::vector>` names a function template, not an object; you must call it to get a closure: `to<std::vector>()`. `views::join` is different: it is itself a closure object and takes no parentheses.
