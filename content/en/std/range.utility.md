---
title: Range utilities and view_interface
summary: "A custom view that writes only begin and end gets empty, size, front, back, operator[] and other members from view_interface; plus the exposition-only concepts such as simple-view that recur throughout the adaptor specifications."
updated: 2026-10-19
---

!!! tldr
    - A class that inherits `view_interface<D>` only needs to provide `begin()` and `end()` to get `empty`, `operator bool`, `data`, `size`, `front`, `back`, `operator[]`, `at`, `cbegin` and `cend`, according to its own capabilities.
    - Each member has a const and a non-const version, which appear or disappear according to the capabilities of `D` and `const D` respectively.
    - The precondition `!empty()` of `front()` and `back()` is a hardened precondition, checked by hardened implementations.
    - *simple-view* means the iterator and sentinel types are the same with and without const; adaptors use it to merge their two implementations.

[range.utility] collects several general tools for representing and manipulating ranges: `view_interface`, covered on this page, plus `subrange` ([[range.subrange]]), `dangling` ([[range.dangling]]), `elements_of` (covered with [[coro.generator]]) and `ranges::to` ([[range.utility.conv]]).

## A minimal custom view [view.interface]

```cpp run ok
#include <ranges>
#include <algorithm>
#include <cstdio>

// the integers in the half-open interval [lo, hi)
class ints : public std::ranges::view_interface<ints> {
  int lo_ = 0, hi_ = 0;
public:
  ints() = default;
  constexpr ints(int lo, int hi) : lo_(lo), hi_(hi) {}
  constexpr auto begin() const { return std::views::iota(lo_, hi_).begin(); }
  constexpr auto end() const { return std::views::iota(lo_, hi_).end(); }
};
template<>
inline constexpr bool std::ranges::enable_borrowed_range<ints> = true;

static_assert(std::ranges::view<ints>);   // inheriting view_interface means enable_view
static_assert(std::ranges::random_access_range<ints>);

int main() {
  constexpr ints r{3, 8};
  static_assert(r.size() == 5 && r.front() == 3 && r.back() == 7);
  static_assert(r[2] == 5 && !r.empty());
  auto it = std::ranges::find(ints{3, 8}, 6);   // a real iterator, even for an rvalue
  std::printf("%d %d\n", *it, bool(r));         // 6 1
}
```

`ints` itself writes only `begin` and `end`; `size`, `front`, `back`, `operator[]`, `empty` and `operator bool` all come from the base class. Its iterator is `iota_view<int, int>::iterator`, which stores the current value directly and refers to no `iota_view` object, so declaring `ints` a borrowed range ([[range.range]]) is a true promise.

¶1 `view_interface` takes the derived class as its template argument, a pattern called CRTP (the curiously recurring template pattern). The base class obtains the derived object via `static_cast<D&>(*this)` and calls its `begin` and `end`:

```cpp
template<class D>
  requires is_class_v<D> && same_as<D, remove_cv_t<D>>
class view_interface {
  constexpr D& derived() noexcept { return static_cast<D&>(*this); }
  // ...
};
```

## Members provided by the base class

Each member appears according to what the derived class can actually do. The table lists the constraints of the non-const version; the const version replaces `D` with `const D`:

| Member | Constraint | Effect |
|---|---|---|
| `empty()` | `sized_range<D> \|\| forward_range<D>` | compares `size() == 0` if sized, otherwise `begin() == end()` |
| `cbegin()`, `cend()` | `input_range<D>` | `ranges::cbegin(derived())` etc. |
| `explicit operator bool()` | `ranges::empty(derived())` is valid | `!ranges::empty(derived())` |
| `data()` | `contiguous_iterator<iterator_t<D>>` | `to_address(ranges::begin(derived()))` |
| `size()` | `forward_range<D>`, and the sentinel and iterator can be subtracted | `end - begin`, converted to an unsigned type |
| `front()` | `forward_range<D>` | `*ranges::begin(derived())` |
| `back()` | `bidirectional_range<D> && common_range<D>` | `*ranges::prev(ranges::end(derived()))` |
| `operator[](n)` | `random_access_range<D>` | `ranges::begin(derived())[n]` |
| `at(n)` | `random_access_range<D> && sized_range<D>` | throws `out_of_range` when out of bounds |

There are two sets, const and non-const, because a derived class may have only a non-const `begin()`, like `filter_view` ([[range.filter]]), or may have both. Each set checks its own constraints independently.

`operator[]` and `at` are written as member templates `template<random_access_range R = D>`. Their parameter type is `range_difference_t<R>`; written directly as `range_difference_t<D>`, that type would be computed when the base class is instantiated, and when a CRTP base is instantiated `D` is still incomplete, so it cannot be computed. As templates with `D` as the default argument, the parameter type is deferred until the call. The other members' parameters do not depend on `D`, so their constraints are trailing *requires-clause*s, checked only on use.

¶2 This also gives the requirements on `D`: it may be an incomplete type, but before any non-special member of `view_interface<D>` is referenced, `D` must be complete and model both `derived_from<view_interface<D>>` and `view`.

### Preconditions of front, back and at [view.interface.members]

¶1, ¶3 The precondition of `front()` and `back()` is `!empty()`, which the standard marks as a **hardened precondition** {{c++26}}: in a hardened implementation a violation is checked and terminates the program; in a non-hardened implementation it is still undefined behavior ([[structure.specifications]]).

¶5–¶6 `at(n)` returns `(*this)[n]`; if `n < 0` or `n >= ranges::distance(derived())`, it throws `out_of_range`. `at` is freestanding-deleted, since exceptions are not necessarily available there.

!!! impl "libc++"
    libc++'s `__ranges/view_interface.h` checks non-emptiness in `front()` and `back()` with `_LIBCPP_ASSERT_VALID_ELEMENT_ACCESS`, effective when hardening is enabled. `operator[]` is not checked. As of the libc++ shipped with Clang 23, `view_interface` has no `at()` member yet.

!!! pitfall "Wrong CRTP argument"
    With a typo like `class A : public view_interface<B>`, `A` still has exactly one `view_interface<U>` base, so `enable_view<A>` is true and `A` is treated as a view. If `B` is itself a well-formed view, calling `a.empty()` even compiles, and the base class `static_cast`s an `A` object to `B&`, which is {{ub}}. Adding `static_assert(std::derived_from<A, std::ranges::view_interface<A>>)` catches it.

## Exposition-only helper concepts [range.utility.helpers]

¶1 Almost every adaptor specification that follows uses these four exposition-only concepts. They are not part of the library, just a way of writing the specification:

```cpp
template<class R>
  concept simple-view =
    view<R> && range<const R> &&
    same_as<iterator_t<R>, iterator_t<const R>> &&
    same_as<sentinel_t<R>, sentinel_t<const R>>;

template<class I>
  concept has-arrow =
    input_iterator<I> &&
    (is_pointer_v<I> || requires(const I i) { i.operator->(); });

template<class T, class U>
  concept different-from = !same_as<remove_cvref_t<T>, remove_cvref_t<U>>;

template<class R>
  concept range-with-movable-references =
    input_range<R> && move_constructible<range_reference_t<R>> &&
    move_constructible<range_rvalue_reference_t<R>>;
```

***simple-view*** ([[g:simple-view]]) means a view has exactly the same iterator and sentinel types with and without const. `ref_view<vector<int>>` and `iota_view` are simple-views; `filter_view` is not, as it has no const `begin`. Adaptors are often written as a pair:

```cpp
constexpr auto begin() requires (!simple-view<V>);
constexpr auto begin() const requires range<const V>;
```

When the underlying view is a simple-view, the non-const version is constrained away and only the const version remains. This instantiates one less set of code, and the outer adaptor's `iterator_t<X>` and `iterator_t<const X>` are also the same, so the outer adaptor is still a simple-view.

***has-arrow*** tests whether an iterator supports `->`. Adaptor iterators provide `operator->` only when the underlying iterator does.

***different-from*** constrains forwarding constructors so they do not hijack copy and move construction. For example, `ref_view`'s constructor is written `template<different-from<ref_view> T> ref_view(T&&)`: when the argument is itself a `ref_view`, the template does not take part and the copy constructor is chosen as usual.

***range-with-movable-references*** requires both the reference type and the rvalue reference type of the elements to be move constructible. Views like `enumerate_view`, which pack references into a `tuple` and hand them out, need it.
