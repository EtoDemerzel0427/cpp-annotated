---
title: Split and lazy_split views
summary: "views::split cuts a forward range into pieces at a delimiter, each piece being a subrange of the underlying range, so splitting a string gives string_views directly; views::lazy_split keeps the original C++20 design and works on input ranges, but each piece is only a lazy inner range."
updated: 2026-10-19
---

!!! tldr
    - `views::split(sep)` requires the underlying range to be a forward range, and each piece is a `subrange<iterator_t<V>>`; when splitting a `string_view`, each piece can be converted directly to a `string_view`.
    - `split_view` caches the position of the first piece, so it has no const `begin()`.
    - Ending with a delimiter yields an extra empty piece, two consecutive delimiters have an empty piece between them, and an empty input yields no pieces at all; an empty pattern splits the sequence into single elements.
    - `views::lazy_split` works on input ranges such as `istream_view` (with a single-element delimiter only), at the cost that each piece is only a lazy forward range.
    - Do not write the delimiter as a string literal; write a character or a `string_view`.

```cpp run ok
#include <iostream>
#include <ranges>
#include <string>
#include <string_view>

int main() {
  std::string str{"the quick brown fox"};
  for (auto word : std::views::split(str, ' '))
    std::cout << std::string_view(word) << '*';
  std::cout << '\n';                            // the*quick*brown*fox*
}
```

This is the example in [range.split.overview] ¶3. Each `word` is a pair of iterators into `str`, and `std::string_view(word)` refers directly to the characters in the original string, without copying.

The original C++20 `views::split` was different: to support input ranges, each piece was designed as a lazy inner range, and you could not even write `std::string(word.begin(), word.end())`, because its `begin()` and `end()` had different types. [[P2210R2]] fixed this as a defect report against C++20: the old design was renamed `lazy_split`, and `split` was replaced by today's design for forward ranges.

## `views::split` [range.split]

¶1 `split_view` takes a view and a delimiter and splits the view into subranges at the delimiter. The delimiter can be a single element or a view of elements. ¶2 `views::split(E, F)` is equivalent to `split_view(E, F)`.

### Each piece is a subrange [range.split.view]

The element type of `split_view` is `subrange<iterator_t<V>>`, i.e. a pair of iterators into the underlying view ([[range.subrange]]). This brings two requirements and one benefit:

- The underlying range must be a forward range. Finding the next delimiter requires looking ahead while keeping the start of the current piece, so multiple passes must be possible.
- The pattern must also be a forward range, and its elements must be equality-comparable with the underlying elements (`indirectly_comparable`).
- When the underlying range is random access, each piece is also a random access, sized range; when the underlying range is a contiguous string, a `string_view` can be constructed directly from each piece (since C++23, `string_view` has an explicit constructor from contiguous ranges).

When the delimiter is a single element, the deduction guide and the constructor in ¶2 wrap it in a `single_view`.

### begin() caches the first piece (¶3–¶5)

¶3 The iterator returned by `begin()` stores the start of the current piece and the position of the next delimiter; the latter is computed by the exposition-only function *find-next*. ¶4 Finding the first piece takes a search, and to meet the `range` concept's requirement that `begin()` be amortized constant time, the result is cached in the view. So `split_view` has only a non-const `begin()`.

¶5 *find-next* uses `ranges::search` to find the next occurrence of the pattern. If the pattern is empty, `search` always matches at the current position, which would yield infinitely many empty pieces; so in that case the found position is moved forward by one element. The result is that an empty pattern splits the sequence into single-element pieces.

```cpp run ok
#include <cstdio>
#include <ranges>
#include <string_view>
using namespace std::literals;

int main() {
  for (auto w : "a,bb,,c"sv | std::views::split(','))
    std::printf("[%.*s]", int(std::string_view(w).size()), std::string_view(w).data());
  std::puts("");                                              // [a][bb][][c]

  using Split = decltype("x"sv | std::views::split(','));
  static_assert(std::ranges::forward_range<Split>);
  static_assert(!std::ranges::range<const Split>);           // no const begin()
}
```

### The ends and empty input [range.split.iterator]

Besides the position of the current piece, the iterator has a flag *trailing_empty_*. When the sequence ends with a delimiter, `++` past the last delimiter first sets this flag and then yields an empty piece (¶4); when compared with the sentinel, it is at the end only if it has reached the underlying end and the flag is not set ([range.split.sentinel] ¶2).

```cpp run ok
#include <cstdio>
#include <ranges>
#include <string_view>
using namespace std::literals;

int count(auto&& r) { int n = 0; for (auto&& x : r) { (void)x; ++n; } return n; }

int main() {
  std::printf("%d ", count("a,b,"sv | std::views::split(',')));    // 3: a, b, empty
  std::printf("%d ", count("a,,b"sv | std::views::split(',')));    // 3: a, empty, b
  std::printf("%d ", count("abc"sv | std::views::split(""sv)));    // 3: empty pattern splits one by one
  std::printf("%d\n", count(""sv | std::views::split(',')));       // 0: empty input has no pieces
}
```

An empty input gives 0 pieces, not 1 empty piece. This differs from the `split` functions of many languages.

## `views::lazy_split`: splitting input ranges [range.lazy.split]

¶1–2 `lazy_split_view` has the same semantic description as `split_view`, and `views::lazy_split(E, F)` is equivalent to `lazy_split_view(E, F)`. The difference is that its underlying range can be merely an input range:

```cpp run ok
#include <cstdio>
#include <ranges>
#include <sstream>

int main() {
  std::istringstream in{"1 2 0 3 0 4 5"};
  for (auto grp : std::views::istream<int>(in) | std::views::lazy_split(0)) {
    std::printf("{");
    for (int x : grp) std::printf("%d", x);
    std::printf("}");
  }
  std::puts("");                                 // {12}{3}{45}
}
```

### On input ranges the pattern can be only one element [range.lazy.split.view]

When the underlying range is an input range, the pattern must satisfy the exposition-only concept *tiny-range*: its size is a compile-time constant no greater than 1. The reason is that an input sequence cannot go back: if the pattern had several elements and a partial match failed, the elements already read could not be put back.

*tiny-range* uses `require-constant<R::size()>` to check whether `size()` can be used as a template argument, i.e. whether it is a static constexpr member function. The `size()` of `single_view` and `empty_view` is exactly that ([[range.factories]]), so single-element delimiters work.

When the underlying range is an input range, the current position is stored in the view's `current_`, a [[range.nonprop.cache|non-propagating-cache]]. When the underlying range is a forward range, `lazy_split_view` also has a const `begin()`, unlike `split_view`.

### Each piece is a lazy inner range

The `value_type` ([range.lazy.split.outer.value]) of the outer iterator ([range.lazy.split.outer]) is not a `subrange` but a special inner range. Its iterator ([range.lazy.split.inner]) compares against the pattern as it advances, walking up to the next delimiter.

So this inner range is not a common range, is at most a forward range, and cannot be used to construct a `string_view` directly. To get a string, write `word | ranges::to<std::string>()` or copy the characters one by one.

```cpp run ok
#include <ranges>
#include <string_view>
using namespace std::literals;

using LS = decltype("x"sv | std::views::lazy_split(','));
using Inner = std::ranges::range_reference_t<LS>;
static_assert(std::ranges::forward_range<Inner>);
static_assert(!std::ranges::common_range<Inner>);
static_assert(!std::ranges::contiguous_range<Inner>);

int main() {}
```

`lazy_split` gives the same results as `split` for the ends, empty input and empty patterns.

## Common misconceptions

!!! pitfall "Writing the pattern as a string literal"
    The pipe form `str | views::split(" ")` fails to compile: when the argument is stored by value the array decays to `const char*` ([[range.adaptor.object#8]]), which is neither a range nor a `char`.

    The function call form `views::split(str, " ")` compiles, but the pattern is the two characters `{' ', '\0'}` of a `const char[2]`, which almost never matches. Write `' '` or `" "sv`. `join_with` has the same problem; see [[range.join]].

## Which to choose

| Need | Use |
|---|---|
| split a `string` or `string_view` and get a `string_view` per piece | `split` |
| the underlying range is an input range like `istream_view` | `lazy_split`, with a single-element delimiter |
| pieces that are random access or have `size()` | `split` (pieces are random access when the underlying range is) |
| split by a relation between adjacent elements rather than a fixed delimiter | `chunk_by` ([[range.chunk]]) |
| join the pieces back together | `join` or `join_with` ([[range.join]]) |

<details class="fine" markdown="1"><summary>Remaining wording</summary>

[range.split.view] ¶1–2: two constructors; the second wraps a single element in a `single_view`. `end()` returns an iterator when the underlying range is a common range, otherwise a sentinel.

[range.split.iterator] ¶1–5: the constructor stores a pointer to the view, the current position and the next delimiter; `base()` returns the start of the current piece; `*it` returns `{current start, delimiter start}`; `++` skips the delimiter and searches for the next; equality compares both the position and *trailing_empty_*.

[range.split.sentinel] ¶1: the sentinel stores the underlying end.

[range.lazy.split.view] ¶1–2 are the two constructors of `lazy_split_view`. [range.lazy.split.outer], [range.lazy.split.outer.value] and [range.lazy.split.inner] specify the members of the outer iterator, the piece object and the inner iterator one by one.

</details>
