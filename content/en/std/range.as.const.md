---
title: As const and as rvalue views
summary: "Two views that change only the element reference type: views::as_const makes elements read-only, making up for the shallow constness of views, and returns a const-qualified view of the same kind when adding const is enough; views::as_rvalue makes elements rvalues, turning copying algorithms into moving ones."
updated: 2026-10-19
---

!!! tldr
    - Views are shallowly const: a `const std::span<int>` can still modify its elements. `views::as_const` gives a view whose elements are read-only.
    - When adding const is enough, `as_const` creates no new type: `span<int>` becomes `span<const int>`, and a container lvalue becomes `ref_view<const C>`; only the remaining cases use `as_const_view`, whose iterators come from `ranges::cbegin`.
    - `views::as_rvalue` turns elements into rvalue references, with `move_iterator` as its iterator; handed to `ranges::copy`, it becomes element-by-element moving.
    - `as_rvalue` itself moves nothing; the move happens when an algorithm uses the element, so only hand it to algorithms that read each element once.
    - The libc++ we test with does not implement `views::as_const` yet; `views::as_rvalue` is available.

```cpp run ok
#include <algorithm>
#include <cstdio>
#include <iterator>
#include <ranges>
#include <string>
#include <vector>

int main() {
  std::vector<std::string> words{"the", "quick", "brown", "fox"};
  std::vector<std::string> new_words;
  std::ranges::copy(words | std::views::as_rvalue, std::back_inserter(new_words));
  std::printf("%zu [%s] [%s]\n", new_words.size(), new_words[0].c_str(), words[0].c_str());
  // 4 [the] []: the strings in words have been moved from
}
```

This is the example in [range.as.rvalue.overview] ¶3: every element that `ranges::copy` reads from the `as_rvalue` view is a `std::string&&`, so `back_inserter` move-constructs. The moved-from strings are in a valid but unspecified state; with libc++ in our tests they became empty strings.

Neither view changes the number or order of elements, only the type you get on dereference: `as_const` switches to a const reference, `as_rvalue` to an rvalue reference.

## `views::as_const`: a read-only view [range.as.const]

Views are shallowly const ([[range.all]]): `const std::span<int>` and `const ref_view<vector<int>>` can both still modify elements, because const applies only to the view object itself, not to the elements it refers to. C++20 had no good way to hand out a range as read-only; `std::as_const(sp)` changes nothing. C++23's [[P2278R4]] added `views::as_const`, and at the same time made `ranges::cbegin` guarantee a constant iterator ([[range.access]]).

¶1 `as_const_view` presents a view of an underlying sequence as constant; its elements cannot be modified.

### No wrapping if adding const suffices (¶2)

¶2 Let `T` be `decltype((E))` and `U` the type with references and cv-qualifiers removed. `views::as_const(E)` checks in order:

| Paragraph | Condition | Result |
|---|---|---|
| ¶2.1 | `views::all_t<T>` is already a [[g:constant-range|constant range]] | `views::all(E)` |
| ¶2.2 | `U` is `empty_view<X>` | a copy of `views::empty<const X>` |
| ¶2.3 | `U` is `optional<X&>` {{c++26}} | `optional<const X&>(E)` |
| ¶2.4 | `U` is `span<X, Extent>` | `span<const X, Extent>(E)` |
| ¶2.5 | `U` is `ref_view<X>` and `const X` is a constant range | `ref_view(static_cast<const X&>(E.base()))` |
| ¶2.6 | `E` is an lvalue, `const U` is a constant range, and `U` is not a view | `ref_view(static_cast<const U&>(E))` |
| ¶2.7 | otherwise | `as_const_view(E)` |

A constant range is one whose iterators yield read-only references on dereference. The first six rows share one idea: if adding const to some type gives a read-only range, return the const-qualified view of the same kind directly. For example, a `vector<int>` lvalue gives `ref_view<const vector<int>>`, and `span<int>` gives `span<const int>`. Only views that cannot themselves become read-only, such as `transform_view` and `filter_view`, need `as_const_view`.

¶3 Example 1 shows typical usage:

```cpp
template<constant_range R>
void cant_touch_this(R&&);

std::vector<char> hammer = {'m', 'c'};
std::span<char> beat = hammer;
cant_touch_this(std::views::as_const(beat));   // ¶2.4: span<const char>, will not modify hammer
```

### as_const_view [range.as.const.view]

`as_const_view`'s `begin()` and `end()` just call `ranges::cbegin` and `ranges::cend` on the underlying view. They return constant iterators: if the underlying iterator is already a constant iterator it is returned as is, otherwise it is wrapped in a `basic_const_iterator` ([[const.iterators]]). The latter changes the result of dereferencing from `int&` to `const int&`; if the underlying dereference yields a prvalue it stays unchanged, since a prvalue cannot reach the original element anyway.

`size()` and `reserve_hint()` are forwarded to the underlying view, and borrowedness is the same as the underlying view's. ¶1 The constructor stores the underlying view.

!!! impl "Implementation status"
    At the time of writing, the libc++ we test with does not implement [[P2278R4]]: there is no `views::as_const` or `basic_const_iterator`, and `__cpp_lib_ranges_as_const` in `<version>` is commented out. The code in this section follows the standard's text and has not been compiled.

Typical uses of `as_const`: a class exposes its internal data to callers as a range but does not want it modified, so it returns `std::views::as_const(data_)`; generic code requires its argument to satisfy `constant_range`; or the last step of a pipeline prevents downstream code from writing back to the underlying range through the view.

## `views::as_rvalue`: elements become rvalues [range.as.rvalue]

¶1 `as_rvalue_view` behaves like the underlying sequence, except that its elements are rvalues. Some generic algorithms can use it to replace copying with moving.

¶2 `views::as_rvalue(E)` is equivalent to `views::all(E)` when the underlying range is an input range whose rvalue reference type is the same as its reference type; otherwise it is `as_rvalue_view(E)`. The former case means the elements are already rvalues, for example `iota` produces a prvalue on each dereference, and wrapping it again would be pointless.

`as_rvalue_view`'s `begin()` returns `move_iterator(ranges::begin(base_))` ([[move.iterators]]), whose `operator*` returns `ranges::iter_move(it)`. When the underlying range is common, `end()` is also a `move_iterator`; otherwise it is a `move_sentinel`. The category of `move_iterator` follows the underlying range, up to random access, and is never contiguous. Borrowedness is the same as the underlying range's.

```cpp run ok
#include <ranges>
#include <string>
#include <vector>

std::vector<std::string> src{"alpha", "beta"};
using MV = decltype(src | std::views::as_rvalue);
static_assert(std::same_as<std::ranges::range_reference_t<MV>, std::string&&>);

using Keep = decltype(std::views::iota(0, 3) | std::views::as_rvalue);
static_assert(std::same_as<Keep, std::ranges::iota_view<int, int>>);   // ¶2.1: not wrapped

int main() {}
```

!!! pitfall "Handing it to an algorithm that reads twice"
    `as_rvalue` only changes the reference type and moves nothing by itself; an element is moved from when an algorithm uses that rvalue to initialize another object. If you hand `src | views::as_rvalue` to an algorithm that reads the same element twice, the second read sees an already moved-from object. Only hand it to operations that consume each element exactly once, such as `ranges::copy`, `ranges::to`, or a container's range constructor.

## Summary

| | `as_const` | `as_rvalue` |
|---|---|---|
| Result of dereference | const reference | rvalue reference |
| Cases not wrapped | already read-only; `empty_view`, `optional<X&>`, `span`, `ref_view` and container lvalues become const-qualified views of the same kind | elements are already rvalues |
| Iterator | the constant iterator returned by `ranges::cbegin` | `move_iterator` |
| Borrowed range | when the underlying range is | when the underlying range is |
| libc++ in our tests | not implemented | implemented |

<details class="fine" markdown="1"><summary>Remaining wording</summary>

[range.as.rvalue.view] ¶1: the constructor stores the underlying view. Both views have deduction guides that wrap `R` into a view via `views::all_t`.

</details>
