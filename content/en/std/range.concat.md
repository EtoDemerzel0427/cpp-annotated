---
title: Concat view
summary: "C++26's views::concat joins several ranges, possibly of different types, end to end into one view; the element reference type is the common reference of the ranges' reference types and may become a non-writable copy; it is a customization point object and has no pipe form."
updated: 2026-10-19
---

!!! tldr
    - `views::concat(a, b, c)` joins a compile-time-known number of ranges, each possibly of a different type, into one view; empty ranges are skipped automatically.
    - The element reference type is the `common_reference_t` of the ranges' reference types: `int&` with `int&` gives `int&`, which can be written back; `int&` with `long&` gives `long`, and each dereference yields a copy.
    - The iterator category of the result is the weakest among the ranges; for bidirectional or random access, every range except the last must also be a common range.
    - `views::concat` is a customization point object, not a range adaptor; there is no `a | views::concat(b)` form.

```cpp run ok
#include <array>
#include <cstdio>
#include <ranges>
#include <vector>

int main() {
  std::vector<int> v1{1, 2, 3}, v2{4, 5}, v3{};
  std::array a{6, 7, 8};
  auto s = std::views::single(9);
  for (auto&& i : std::views::concat(v1, v2, v3, a, s))
    std::printf("%d ", i);                    // 1 2 3 4 5 6 7 8 9
  std::puts("");
}
```

This is Example 1 in [range.concat.overview] ¶2. `vector`, `array` and `single_view` are all different types and `v3` is empty, yet they are joined into one sequence.

`concat` and [[range.join]] can both join several pieces together; they differ in the shape of their input: `join` handles a range of ranges whose inner ranges all have the same type and whose number is decided at run time; `concat` handles a compile-time-known number of ranges of different types. It comes from C++26's [[P2542R8]].

## `views::concat` [range.concat.overview]

¶1 `concat_view` presents a view that concatenates all the underlying ranges. ¶2 `views::concat` is a [[customization.point.object|customization point object]]. Given a pack of subexpressions `Es...`:

- ¶2.1 if there is only one argument and it is an input range, it is equivalent to `views::all(Es...)`, with no wrapping;
- ¶2.2 otherwise it is equivalent to `concat_view(Es...)`.

`concat_view` requires at least one view, so `views::concat()` is ill-formed. Nor is it a [[g:range-adaptor-object|range adaptor object]], so it has no pipe form: in `a | views::concat(b)`, `views::concat(b)` is just `views::all(b)` by ¶2.1, and a view cannot go to the right of `|`, so it fails to compile.

## Element type: the common reference [range.concat.view]

The element types of the ranges may differ, and once they are joined, dereferencing has to return a single type. The standard settles this with three exposition-only aliases:

| Alias | Definition | Used for |
|---|---|---|
| *concat-reference-t* | the `common_reference_t` of the ranges' `range_reference_t` | the type of `*it` |
| *concat-value-t* | the `common_type_t` of the ranges' `range_value_t` | `value_type` |
| *concat-rvalue-reference-t* | the `common_reference_t` of the ranges' `range_rvalue_reference_t` | the type of `iter_move` |

¶2 The exposition-only concept *concatable* requires all three types to exist and to satisfy *concat-indirectly-readable* from ¶1: each range's `*it` must convert to *concat-reference-t*, `iter_move(it)` must convert to *concat-rvalue-reference-t*, and the three must have the common-reference relationships that `indirectly_readable` needs. Only then can the combined iterator be a valid input iterator.

The resulting common reference decides whether elements can be written back:

- all `int&` gives `int&`, which can be written back;
- `int&` and `const int&` give `const int&`, read-only;
- `int&` and `long&` give `long`, a prvalue: each dereference produces a converted copy, and writing to it does not affect the original containers.

```cpp run ok
#include <cstdio>
#include <list>
#include <ranges>
#include <vector>

int main() {
  std::vector<int> a{1, 2};
  std::list<int> b{3, 4};
  auto cat = std::views::concat(a, b);
  for (int& x : cat) x *= 10;                  // int&: writes back to a and b
  for (int x : cat) std::printf("%d ", x);     // 10 20 30 40
  std::puts("");

  std::vector<long> d{6};
  auto mixed = std::views::concat(a, d);
  static_assert(std::same_as<std::ranges::range_reference_t<decltype(mixed)>, long>);
}
```

In the current draft, `join_with_view` in [[range.join]] also uses *concatable* to check that the inner elements and the separator are compatible.

## How the iterator moves between pieces [range.concat.iterator]

The iterator stores a `variant` holding the underlying iterator of the piece it is currently in, plus a pointer to the view.

[range.concat.view] ¶6 `begin()` constructs an iterator at the start of piece 0 and then calls the exposition-only function *satisfy*. [range.concat.iterator] ¶3 specifies that when *satisfy* finds the current piece exhausted, it switches to the start of the next piece and keeps checking until it finds a non-empty piece or reaches the last piece. That is how empty ranges are skipped.

[range.concat.view] ¶7 When all pieces are forward ranges and the last piece is a common range, `end()` returns an iterator to the end of the last piece and the result is a common range; otherwise it returns `default_sentinel`.

### Bidirectional and random access require the earlier pieces to be common (¶1)

¶1 The iterator's category is the weakest among the pieces' categories, but bidirectional and random access have an extra condition: every piece except the last must be a [[g:common-range|common range]] ([range.concat.view] ¶3–¶4).

The reason is `--` (¶4): stepping back from the start of piece k+1 into piece k requires first getting an iterator to the end of piece k and then stepping back once. If piece k's `end()` is just a sentinel, that cannot be done. The last piece is never entered from behind, so it need not be common. Cross-piece `+=` and `-=` (¶5–¶6) work the same way.

¶2 `iterator_category` is defined only when all pieces are forward ranges; if *concat-reference-t* is not a reference type it is `input_iterator_tag`, because old-style forward iterators require dereferencing to yield a reference.

### Sorting across containers (¶41–¶42)

`iter_swap` dispatches with `std::visit`: when the current underlying iterators of the two iterators have the same type, it calls the underlying `ranges::iter_swap`; otherwise it falls back to `ranges::swap(*x, *y)` (¶42). So two `vector`s joined together form a random access range that can be sorted directly, with the results written back into both containers:

```cpp run ok
#include <algorithm>
#include <cstdio>
#include <ranges>
#include <vector>

int main() {
  std::vector<int> a{5, 1, 4}, b{3, 2};
  auto cat = std::views::concat(a, b);
  static_assert(std::ranges::random_access_range<decltype(cat)>);
  std::ranges::sort(cat);
  for (int x : a) std::printf("%d ", x);       // 1 2 3
  for (int x : b) std::printf("%d ", x);       // 4 5
  std::printf("| size=%zu\n", cat.size());     // size=5
}
```

¶41 As with many other operations, the precondition is that the `variant` is not valueless by exception.

## Other properties

- [range.concat.view] ¶8 There is a `size()` only when all pieces are sized ranges: the piece sizes are converted to their common unsigned type and summed. ¶9 `reserve_hint()` works the same way.
- When all `const Views` are ranges and satisfy *concatable*, there is a const `begin()`.
- `begin()` is not cached. *satisfy* skips leading empty pieces anew each time, at a cost proportional to the number of pieces, which is a compile-time constant.
- It is not a borrowed range.

!!! impl "Implementation status"
    The libc++ we test with already provides `views::concat` (`__cpp_lib_ranges_concat` is `202403L`), and all examples on this page were checked with libc++.

## Summary

| Aspect | `views::concat` |
|---|---|
| Arguments | one or more ranges, possibly of different types; with only one it equals `views::all` |
| Reference type | the `common_reference_t` of the pieces' reference types; may be a non-writable copy |
| Iterator category | the weakest of the pieces; bidirectional and random access additionally require every piece but the last to be common |
| common range | when all are forward ranges and the last piece is common |
| sized range | when all are |
| Pipe form | none |

<details class="fine" markdown="1"><summary>Remaining wording</summary>

[range.concat.view] ¶5: the constructor stores all the views.

[range.concat.iterator] ¶7–9 are the constructors (converting from a non-const iterator copies the underlying iterator at the current index); ¶10–¶40 specify dereference, increment and decrement, random access arithmetic, comparison and distance one by one, each with the precondition that the `variant` holds a value; `iter_move` returns *concat-rvalue-reference-t*. ¶43 specifies the exception specification and constraints of `iter_swap`.

</details>
