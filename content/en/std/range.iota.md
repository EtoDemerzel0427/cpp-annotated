---
title: iota view and views::indices
summary: "views::iota generates a sequence by repeated incrementing: bounded and unbounded forms, elements that can be integers or iterators, why bounds of different signedness are rejected, why the difference type is wider, how the iterator strength is determined, and C++26's views::indices."
updated: 2026-10-19
---

!!! tldr
    - `views::iota(a)` produces the infinite sequence `a, a+1, a+2, …`, and `views::iota(a, b)` produces `[a, b)`. The elements can be integers, or pointers or any iterators.
    - When both bounds are integers they must have the same signedness, so `views::iota(0, v.size())` fails to compile. Use `views::iota(0uz, v.size())` or C++26's `views::indices(v.size())` instead.
    - `views::iota(5, 0)` is not an empty range; it violates a precondition, and the behavior is undefined.
    - The difference type of `iota_view<int, int>` is wider than `int`, and `size()` is computed in the unsigned domain, so `iota(INT_MIN, INT_MAX)` does not overflow.
    - The iterator returns elements by value, so from the C++17 point of view it is only an input iterator; `iota_view` is a borrowed range.

## Counting from 0 to n

```cpp run ok
#include <ranges>
#include <vector>
#include <list>
#include <cstdio>
int main() {
  for (int i : std::views::iota(1, 4)) std::printf("%d ", i);    // 1 2 3

  std::vector<int> v{10, 20, 30};
  for (auto i : std::views::iota(0uz, v.size()))                  // 0uz: both unsigned
    std::printf("%d ", v[i]);                                       // 10 20 30

  std::list<int> l{7, 8};
  for (auto it : std::views::iota(l.begin(), l.end()))            // the elements are iterators
    std::printf("%d ", *it);                                        // 7 8
  std::puts("");
}
```

[range.iota.overview] ¶1 `iota_view` generates a sequence by repeatedly incrementing an initial value. ¶2 `views::iota(E)` and `views::iota(E, F)` are equivalent to `iota_view<decay_t<decltype((E))>>(E)` and `iota_view(E, F)` respectively; the latter determines its type by class template argument deduction.

```cpp
template<weakly_incrementable W, semiregular Bound = unreachable_sentinel_t>
  requires weakly-equality-comparable-with<W, Bound> && copyable<W>
class iota_view : public view_interface<iota_view<W, Bound>> {
  W value_ = W();
  Bound bound_ = Bound();
  // ...
};
```

`W` only needs to be incrementable (`weakly_incrementable`), copyable, and equality-comparable with `Bound`. Integers, pointers and iterators all qualify. `Bound` defaults to `unreachable_sentinel_t`, a sentinel that compares unequal to every value ([[unreachable.sentinel]]), so with a single argument the sequence is infinite.

## Bounds of different signedness are rejected

```cpp run error
#include <ranges>
#include <vector>
int main() {
  std::vector<int> v{1, 2, 3};
  for (auto i : std::views::iota(0, v.size())) (void)i;
  // error: int and size_t differ in signedness; deduction fails
}
```

The deduction guide of `iota_view` is constrained:

```cpp
template<class W, class Bound>
  requires (!is-integer-like<W> || !is-integer-like<Bound> ||
            (is-signed-integer-like<W> == is-signed-integer-like<Bound>))
  iota_view(W, Bound) -> iota_view<W, Bound>;
```

When both arguments are of integer type, they must have the same signedness. The reason is that with mixed signedness, the `value_ == bound_` that loop termination relies on goes through the arithmetic conversions, and it is easy to end up never equal, with the loop running past the end until it overflows. So the standard makes it fail at deduction.

There are three ways to fix it: `views::iota(0uz, v.size())`, `views::iota(std::size_t{0}, v.size())`, or `views::indices`.

### views::indices {{c++26}}

¶4 In `views::indices(E)`, let `T` be the type of `E` with references and cv-qualifiers removed. If `T` is an integer-like type, it is equivalent to `views::iota(T(0), E)`; otherwise it is ill-formed. It is meant specifically for counting from 0 to a container's size, with the type of the start automatically matching `E`.

```cpp run ok
#include <ranges>
#include <vector>
#include <cstdio>
int main() {
  std::vector<int> v{10, 20, 30};
  for (auto i : std::views::indices(v.size()))
    std::printf("%zu:%d ", i, v[i]);      // 0:10 1:20 2:30
  std::puts("");
}
```

## Preconditions of construction [range.iota.view]

¶6, ¶8 The precondition for constructing `iota_view(value, bound)` is that `Bound` is `unreachable_sentinel_t`, or that `bound` is reachable from `value` by repeated incrementing. If `W` and `Bound` can be ordered (`totally_ordered_with`), `value <= bound` is also required.

So `views::iota(5, 0)` is not an empty range: it violates the precondition, and the behavior is undefined. When the bounds come from run-time data, sort them out first with `std::min` and `std::max`.

¶10–¶11 An `iota_view` can also be constructed from a pair of its own iterators (or an iterator and a sentinel). `views::take` and `views::drop` use this to keep representing the result of slicing as an `iota_view`; see below.

## The difference type: IOTA-DIFF-T (¶1)

What type does subtracting two iterators of `iota_view<int, int>` give? `int` is not enough: the length of `iota(INT_MIN, INT_MAX)` exceeds `INT_MAX`. *IOTA-DIFF-T*(W), defined in ¶1, chooses in order:

- ¶1.1 If `W` is not an integral type, or `iter_difference_t<W>` is wider than `W`, use `iter_difference_t<W>`;
- ¶1.2 Otherwise, if there is a signed integer type wider than `W`, use it;
- ¶1.3 Otherwise, use an unspecified signed-integer-like type at least as wide as `W` ([[iterator.concept.winc]]). Note 1 says it is unspecified whether this type satisfies `weakly_incrementable`.

So the difference type of `iota_view<int, int>` is a wider standard type; `iota_view<long long, long long>`, on a platform with no wider standard integer, has to use an implementation-provided integer-class type. In our tests libc++ uses `__int128`.

¶16 `size()` avoids overflow too. When both bounds are integers, it first splits on sign and then subtracts or adds in the unsigned domain:

```cpp
if constexpr (is-integer-like<W> && is-integer-like<Bound>)
  return (value_ < 0)
    ? ((bound_ < 0)
      ? to-unsigned-like(-value_) - to-unsigned-like(-bound_)
      : to-unsigned-like(bound_) + to-unsigned-like(-value_))
    : to-unsigned-like(bound_) - to-unsigned-like(value_);
else
  return to-unsigned-like(bound_ - value_);
```

Writing `bound_ - value_` directly would overflow in the signed domain for `iota(INT_MIN, INT_MAX)`. ¶17 says `size()` exists when any of these holds: `W` and `Bound` are the same type and `W` is *advanceable* (see below); both are integer-like types; or `Bound` and `W` can be subtracted (`sized_sentinel_for`).

¶12–¶15 `begin()` returns an iterator to `value_`. When `W` and `Bound` are the same type, `end()` also returns an iterator and the view is common; otherwise it returns a sentinel or `unreachable_sentinel`. `empty()` returns `value_ == bound_`.

## Iterator strength [range.iota.iterator]

How many operations the iterator supports depends on `W`. ¶2–¶5 define two exposition-only concepts describing what `W` can do:

- ***decrementable***: on top of `incrementable`, supports `--i` and `i--`, with `++` and `--` inverse to each other;
- ***advanceable***: on top of *decrementable*, can be ordered, supports `+=`, `-=`, `+` and `-` with the difference type, and two values can be subtracted. The long list of semantic requirements after ¶5 boils down to: adding `n` gives the same result as incrementing `n` times.

[range.iota.iterator] ¶1 determines the iterator's `iterator_concept` from this:

| `W` models | `iterator_concept` | Example |
|---|---|---|
| *advanceable* | `random_access_iterator_tag` | integers, pointers, `vector` iterators |
| *decrementable* | `bidirectional_iterator_tag` | `list` iterators |
| `incrementable` | `forward_iterator_tag` | `forward_list` iterators |
| otherwise | `input_iterator_tag` | types that only satisfy `weakly_incrementable` |

The iterator stores just one `W value_`. ¶4 `operator*` returns a copy of `value_` by value, and `operator[](n)` returns `W(value_ + n)`. Precisely because it returns by value, the C++17-style `iterator_category` is at most `input_iterator_tag`, and is declared only when `W` is `incrementable` and the difference type is an integral type: *Cpp17ForwardIterator* requires `reference` to be a real reference. Old algorithms that only understand the C++17 categories treat `iota` iterators as input iterators.

¶2 Note 1 points out that the iterator intentionally provides no overloads of `iter_move` and `iter_swap`: the elements are prvalues anyway, so the default behavior is correct. ¶5 Note 2 explains that the `noexcept` specification of `operator*` is there for the default `iter_move`.

The iterator carries its own value and has nothing to do with the `iota_view` object, so `iota_view` is a borrowed range ([[ranges.syn]]). The sentinel in [range.iota.sentinel] stores a `Bound bound_` and compares with the iterator by `value_ == bound_`; when `Bound` and `W` can be subtracted, sentinels and iterators can be subtracted too.

```cpp run ok
#include <ranges>
#include <iterator>
int main() {
  using I = std::ranges::iota_view<int, int>;
  static_assert(sizeof(std::ranges::range_difference_t<I>) > sizeof(int));
  using L = std::ranges::iota_view<long long, long long>;
  static_assert(sizeof(std::ranges::range_difference_t<L>) > sizeof(long long));
  static_assert(std::ranges::random_access_range<I> && std::ranges::sized_range<I>);
  static_assert(std::same_as<
      std::iterator_traits<std::ranges::iterator_t<I>>::iterator_category,
      std::input_iterator_tag>);          // only an input iterator from the C++17 point of view
  static_assert(std::ranges::borrowed_range<I>);
}
```

## Working with take and drop

When an `iota_view` is both random access and sized, the results of `views::take` and `views::drop` are still `iota_view`s rather than an extra wrapper ([[range.take]], [[range.drop]]). The unbounded `iota(0)` has no size, so `iota(0) | take(10)` gives a `take_view<iota_view<int>>`; `iota(0, 100) | take(10)` gives an `iota_view<int, int>`.

```cpp run ok
#include <ranges>
int main() {
  auto a = std::views::iota(0) | std::views::take(10);
  auto b = std::views::iota(0, 100) | std::views::take(10);
  static_assert(std::same_as<decltype(a),
      std::ranges::take_view<std::ranges::iota_view<int, std::unreachable_sentinel_t>>>);
  static_assert(std::same_as<decltype(b), std::ranges::iota_view<int, int>>);
}
```

## Common misconceptions

!!! pitfall "An unbounded iota plus filter will stop"
    `views::iota(0) | views::filter(p)` is an infinite sequence. If the predicate is never true again after some point, finding the next element searches forever. For example, `iota(0) | filter([](int x) { return x < 10; }) | take(20)` enters an infinite loop when looking for the 11th element and eventually hits signed overflow, which is undefined behavior {{ub}}. To express "up to some point", use `views::take_while`.

## Questions

!!! question "Question"
    Does `views::iota(0, 10u)` compile? What about `views::iota(0L, 10)`?

<details markdown="1">
<summary>Answer</summary>

The former does not: `int` is signed and `unsigned int` is unsigned, so the deduction guide's constraint is not met. The latter does: `long` and `int` are both signed, and it deduces `iota_view<long, int>`. The two types differ, so `end()` returns a sentinel rather than an iterator and the view is not common; `size()` still exists because both are integral types.
</details>
