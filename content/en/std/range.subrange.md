---
title: subrange
summary: "subrange packs an iterator and a sentinel into a borrowed view: how it is constructed, when it stores the size, how derived-to-base slicing conversions are forbidden, plus conversion to and from pair, structured bindings, and next/prev/advance."
updated: 2026-10-19
---

!!! tldr
    - `subrange<I, S, K>` combines an iterator `I` and a sentinel `S` into a view; it is always a borrowed range.
    - When the iterator and sentinel cannot be subtracted (as with `list`), the element count can be given at construction; `subrange` stores it, so `size()` is still O(1). The count is a precondition, not checked by the library.
    - Constructing a `subrange<Base*>` from a `Derived*` is ill-formed; the standard specifically blocks this conversion, which would traverse an array with the wrong stride.
    - A `subrange` converts to pair-like types such as `std::pair`, and can be unpacked with structured bindings.
    - `advance(n)` is bounded by `end` when moving forward and never goes past the end.

## A pair of iterators becomes one object

```cpp run ok
#include <ranges>
#include <map>
#include <cstdio>
int main() {
  std::multimap<int, char> m{{1, 'a'}, {1, 'b'}, {2, 'c'}};
  auto [lo, hi] = m.equal_range(1);       // old interface: a pair of iterators
  std::ranges::subrange eq(lo, hi);        // turned into a range
  for (auto& [k, c] : eq) std::printf("%c ", c);
  std::printf("%td\n", std::ranges::distance(eq));   // a b 2
}
```

C++98 interfaces represent a range as a pair of iterators, while the algorithms and adaptors of the ranges library take a range object. `subrange` packs `[i, s)` into one object so that the two can interoperate. The other direction is common too: algorithms such as `ranges::equal_range` and `ranges::search` return a `subrange`, and `views::counted` and `views::split` produce `subrange`s.

¶1 `subrange` models `view` ([[range.view]]), and also models `sized_range` when its last template argument is `subrange_kind::sized`. Its synopsis is roughly:

```cpp
template<input_or_output_iterator I, sentinel_for<I> S = I,
         subrange_kind K = sized_sentinel_for<S, I>
                             ? subrange_kind::sized : subrange_kind::unsized>
  requires (K == subrange_kind::sized || !sized_sentinel_for<S, I>)
class subrange : public view_interface<subrange<I, S, K>> {
  static constexpr bool StoreSize =
    K == subrange_kind::sized && !sized_sentinel_for<S, I>;
  I begin_ = I();
  S end_ = S();
  make-unsigned-like-t<iter_difference_t<I>> size_ = 0;  // present only if StoreSize is true
  // ...
};
```

[[ranges.syn]] specializes `enable_borrowed_range<subrange<I, S, K>>` to `true`. A `subrange` merely borrows someone else's iterators, and those iterators remain valid after the `subrange` object is destroyed, so `ranges::find(ranges::subrange{vec}, 42)` returns a real iterator rather than `dangling` ([[range.dangling]]).

## When the size is stored

`subrange_kind` has two values, `sized` and `unsized`, which decide whether `subrange` provides `size()`:

- If `S - I` can be computed in constant time (`sized_sentinel_for<S, I>`, e.g. `vector` iterators), `K` defaults to `sized`, and `size()` is always computed as `end_ - begin_`, with nothing stored;
- Otherwise `K` defaults to `unsized`. You can then specify `sized` explicitly and give the count `n` at construction. *StoreSize* is true, `subrange` stores one extra integer, and it can answer `size()` in O(1) even for ranges like `list` iterators (Note 1 in [range.subrange.ctor] ¶5);
- The `requires` clause forbids declaring `unsized` for a combination that can be subtracted.

```cpp run ok
#include <ranges>
#include <list>
#include <vector>
#include <cstdio>
int main() {
  std::vector<int> v{1, 2, 3, 4, 5};
  std::ranges::subrange sr(v.begin() + 1, v.end() - 1);    // 2 3 4
  static_assert(std::ranges::sized_range<decltype(sr)>);    // iterators can be subtracted

  std::list<int> l{1, 2, 3};
  std::ranges::subrange ls(l.begin(), l.end());
  static_assert(!std::ranges::sized_range<decltype(ls)>);   // cannot be subtracted
  std::ranges::subrange ls2(l.begin(), l.end(), l.size());  // count given and stored
  static_assert(std::ranges::sized_range<decltype(ls2)>);

  auto [b, e] = sr;                                          // structured binding
  std::printf("%td %zu %zu\n", e - b, sr.next().size(), ls2.size());   // 3 2 3
}
```

## Construction and deduction [range.subrange.ctor]

¶1–¶2 `subrange(i, s)` requires *StoreSize* to be false; its precondition is that `[i, s)` is a valid range.

¶3–¶4 `subrange(i, s, n)` requires `K` to be `sized`. The precondition additionally requires `n` to equal `ranges::distance(i, s)`. The library does not verify this value; a wrong `n` violates the precondition, after which the result of `size()` is not guaranteed.

¶6 `subrange(r)` constructs from a borrowed range. When *StoreSize* is true it is equivalent to `subrange(r, ranges::size(r))`, so it then requires `sized_range<R>`; otherwise it is equivalent to `subrange(ranges::begin(r), ranges::end(r))`.

The deduction guides give:

| Form | Deduced type |
|---|---|
| `subrange(i, s)` | `subrange<I, S>`, `K` by the default rule |
| `subrange(i, s, n)` | `subrange<I, S, sized>` |
| `subrange(r)` | `sized` if `r` is a `sized_range` or its iterators can be subtracted, otherwise `unsized` |
| `subrange(r, n)` | `sized` |

Both forms that construct from a range require `r` to be a borrowed range ([[range.range]]). `subrange{std::vector<int>{}}` is ill-formed; otherwise you would get a view into a destroyed temporary.

### Slicing is forbidden

```cpp run error
#include <ranges>
struct Base { int x; };
struct Derived : Base { int y; };
Derived arr[3];
std::ranges::subrange<Base*> s(arr, arr + 3);   // error: Derived* to Base* would slice
int main() {}
```

`Derived*` implicitly converts to `Base*`, but when traversing a `Derived` array with a `Base*`, each `++` advances only `sizeof(Base)` bytes, and from the second step on the pointer no longer points to a `Base` object: undefined behavior {{ub}} ([[expr.add]]). So the iterator parameters of the constructors are constrained by these concepts:

```cpp
template<class From, class To>
  concept uses-nonqualification-pointer-conversion =
    is_pointer_v<From> && is_pointer_v<To> &&
    !convertible_to<remove_pointer_t<From>(*)[], remove_pointer_t<To>(*)[]>;
template<class From, class To>
  concept convertible-to-non-slicing =
    convertible_to<From, To> &&
    !uses-nonqualification-pointer-conversion<decay_t<From>, decay_t<To>>;
```

The test borrows pointers to arrays: `Derived(*)[]` cannot convert to `Base(*)[]`, while `int(*)[]` can convert to `const int(*)[]`, since the latter only adds cv-qualification. So `subrange<const int*>` can be constructed from `int*`, but `subrange<Base*>` cannot be constructed from `Derived*`.

### Conversion to pair-like

¶7 A `subrange` converts to any pair-like type (`std::pair`, a two-element `std::tuple` and so on, see [[tuple.like]]), provided the target type is not a range, is not a reference, is constructible from `const I&, const S&`, and the conversion of the first element does not slice. This lets a `subrange` be passed directly to old code that still takes `std::pair<It, It>`:

```cpp run ok
#include <ranges>
#include <utility>
#include <vector>
int main() {
  std::vector<int> v{1, 2, 3};
  std::ranges::subrange sr(v);
  using It = std::vector<int>::iterator;
  std::pair<It, It> p = sr;
  return p.first == v.begin() ? 0 : 1;
}
```

## Accessors [range.subrange.access]

¶1–¶2 `begin() const` returns a copy of `begin_` when `I` is copyable. When `I` is move-only (some input iterators), there is only a non-const `begin()`, which returns `std::move(begin_)`; it can therefore be called only once, and the `subrange` cannot be iterated as const.

¶3 `end()` returns a copy of `end_`. ¶4 `empty()` returns `begin_ == end_`. ¶5 `size()` returns the stored value when *StoreSize* is true, and otherwise `end_ - begin_` converted to unsigned.

¶6–¶8 `next(n)` and `prev(n)` return a copy advanced forward or backward by `n` steps. `next` also has an rvalue version `next(n) &&`, which advances in place and then moves itself out, usable with move-only iterators.

¶9 `advance(n)` behaves in one of two ways:

- If the iterator is bidirectional and `n < 0`, `begin_` moves back `-n` steps and the stored size increases accordingly;
- Otherwise it advances with `ranges::advance(begin_, n, end_)`, bounded by `end_` and never past the end, and the stored size decreases by the number of steps actually taken.

¶10 `get<0>` returns `begin()` and `get<1>` returns `end()`. Together with the specializations of `tuple_size` and `tuple_element` in [[ranges.syn]], this makes structured bindings like `auto [b, e] = sr;` work ([[dcl.struct.bind]]). Calling `get<0>` on a const lvalue requires `I` to be copyable.

## Common misconceptions

!!! pitfall "A borrowed range cannot dangle"
    Borrowed only means that the validity of the iterators does not depend on the lifetime of the `subrange` object itself. If the `subrange` borrows iterators of a temporary `vector`, they dangle once the `vector` is destroyed. `subrange(r)` requires `r` to be a borrowed range, which only blocks the most common case of constructing directly from a temporary container; constructing from iterators, as in `subrange(tmp.begin(), tmp.end())`, cannot be caught by the type system.
