---
title: "Range factories: empty, single, repeat, istream"
summary: "Factories that create views without an underlying range: empty_view, which is always empty; single_view, which holds one element; repeat_view, which repeats one value; and basic_istream_view, which reads elements from an input stream. iota has its own page."
updated: 2026-10-19
---

!!! tldr
    - Range factories take no underlying range and create views directly; they start pipelines. They are all in `std::ranges::views`.
    - `views::empty<T>` has no elements; its iterator is a null `T*`, and it often serves as the zero in generic code.
    - `views::single(x)` stores a copy of `x`; modifying the element in the view does not affect the original object.
    - `views::repeat(x)` repeats the same object forever, `views::repeat(x, n)` repeats it `n` times; the iterator is random access, and all elements are the same object.
    - `views::istream<T>(s)` reads elements from a stream; `begin()` itself consumes a value, and it can be traversed only once.

```cpp run ok
#include <ranges>
#include <string>
#include <cstdio>
int main() {
  static_assert(std::ranges::empty(std::views::empty<int>));

  std::string s = "hi";
  auto one = std::views::single(s);            // copies s
  one.front() += "!";
  std::printf("%s %s\n", s.c_str(), one.front().c_str());   // hi hi!

  auto rp = std::views::repeat(std::string("ab"), 3);
  for (auto& x : rp) std::printf("%s", x.c_str());           // ababab
  std::printf(" %d\n", &rp[0] == &rp[2]);     // 1: all elements are the same object
}
```

[range.factories] ¶1 defines **range factories** ([[g:range-factory]]): utilities for creating views. ¶2 They are declared in `std::ranges::views`. A range adaptor ([[range.adaptors]]) takes an underlying range and produces a view, whereas a factory needs no underlying range. This page covers `empty`, `single`, `repeat` and `istream`; the most commonly used, `iota` and `indices`, are in [[range.iota]].

Names below such as `views::single` are customization point objects: function objects whose call is equivalent to the expression the standard specifies ([[customization.point.object]]).

## empty_view [range.empty]

¶1 `empty_view<T>` produces a view with element type `T` and no elements at all:

```cpp
template<class T> requires is_object_v<T>
class empty_view : public view_interface<empty_view<T>> {
public:
  static constexpr T* begin() noexcept { return nullptr; }
  static constexpr T* end() noexcept { return nullptr; }
  static constexpr T* data() noexcept { return nullptr; }
  static constexpr size_t size() noexcept { return 0; }
  static constexpr bool empty() noexcept { return true; }
};
```

Its iterator is `T*`, so it is a contiguous, sized and common range. [[ranges.syn]] declares it a borrowed range. `views::empty<T>` is a variable template whose value is `empty_view<T>{}`.

Its main use is as the zero in generic code. For example, `views::zip()` with no arguments returns `views::empty<tuple<>>` ([[range.zip]]); applying `views::take` to an `empty_view` gives back that same `empty_view` ([[range.take]]).

## single_view [range.single]

¶1 `single_view` produces a view that contains exactly one element of a specified value. ¶2 `views::single(E)` is equivalent to `single_view<decay_t<decltype((E))>>(E)`, i.e. `E` is copied or moved by value.

```cpp
template<move_constructible T> requires is_object_v<T>
class single_view : public view_interface<single_view<T>> {
  movable-box<T> value_;
public:
  constexpr explicit single_view(const T& t) requires copy_constructible<T>;
  constexpr explicit single_view(T&& t);
  template<class... Args> requires constructible_from<T, Args...>
    constexpr explicit single_view(in_place_t, Args&&... args);
  constexpr T* begin() noexcept;
  constexpr const T* begin() const noexcept;
  constexpr T* end() noexcept;               // data() + 1
  static constexpr size_t size() noexcept;   // 1
  // ...
};
```

`single_view` owns its element. It is still a view because copying it copies only one element, a constant cost ([[range.view]]). Several properties follow:

- Modifying the element in the view does not affect the original object; see the example at the top of this page;
- `begin()` on a `const single_view` returns `const T*`: const propagates to the element, as with containers and unlike `span`;
- It is not a borrowed range; its iterators point inside the view object;
- The element is stored in a *movable-box* ([[range.move.wrap]]). A view must be move-assignable, while `T` may not be assignable (for example, a lambda that captures a reference); *movable-box* supplies the assignment.

## repeat_view [range.repeat] {{c++23}}

¶1 `repeat_view` produces the same value over and over. ¶2 `views::repeat(E)` and `views::repeat(E, F)` are equivalent to `repeat_view<decay_t<decltype((E))>>(E)` and `repeat_view(E, F)` respectively. It was introduced by [[P2474R2]].

```cpp
template<move_constructible T, semiregular Bound = unreachable_sentinel_t>
  requires (is_object_v<T> && same_as<T, remove_cv_t<T>> &&
            (integer-like-with-usable-difference-type<Bound> ||
             same_as<Bound, unreachable_sentinel_t>))
class repeat_view;
```

- When the second argument is omitted, `Bound` is `unreachable_sentinel_t`, `end()` returns a sentinel that never compares equal ([[unreachable.sentinel]]), and the sequence is infinite. When a count is given, the view is sized and common.
- The iterator is random access. It stores only a pointer to the value and the current index; `it + n` only changes the index.
- All elements are the same object; `*it` returns `const T&`.
- ¶1, ¶3 The precondition is that the count `bound >= 0`. ¶5 When piecewise-constructing with `piecewise_construct`, ending up with a negative count is {{ub}}.
- `views::take` and `views::drop` handle `repeat_view` specially ([[range.take]], [[range.drop]]): the result of `views::repeat(x) | views::take(n)` is still a `repeat_view`, not a `take_view` wrapped around it.

```cpp run ok
#include <ranges>
#include <string>
int main() {
  auto rp = std::views::repeat(std::string("ab"), 3);
  static_assert(std::ranges::random_access_range<decltype(rp)>);
  static_assert(std::ranges::sized_range<decltype(rp)>);

  auto inf = std::views::repeat(0);
  static_assert(!std::ranges::sized_range<decltype(inf)>);
  auto five = inf | std::views::take(5);
  static_assert(std::same_as<decltype(five), std::ranges::repeat_view<int, long>>);
}
```

In the result type of `take`, the count type is `long`: the difference type of an unbounded `repeat_view` is `ptrdiff_t`, which is `long` on the platform we test on (macOS arm64).

## basic_istream_view [range.istream]

¶1 `basic_istream_view` models `input_range` and reads elements one after another from an input stream using `operator>>`. ¶2 For an expression `E` of type `U`, if `U` is derived from `basic_istream<typename U::char_type, typename U::traits_type>`, `views::istream<T>(E)` is equivalent to `basic_istream_view<T, typename U::char_type, typename U::traits_type>(E)`; otherwise it is ill-formed. `istream_view<T>` and `wistream_view<T>` are aliases for the `char` and `wchar_t` versions.

```cpp
template<movable Val, class CharT, class Traits = char_traits<CharT>>
  requires default_initializable<Val> && stream-extractable<Val, CharT, Traits>
class basic_istream_view
    : public view_interface<basic_istream_view<Val, CharT, Traits>> {
public:
  constexpr explicit basic_istream_view(basic_istream<CharT, Traits>& stream);
  constexpr auto begin() { *stream_ >> value_; return iterator{*this}; }
  constexpr default_sentinel_t end() const noexcept;
private:
  basic_istream<CharT, Traits>* stream_;
  Val value_ = Val();
};
```

The key point is that `begin()` reads: it first performs `*stream_ >> value_` and then returns the iterator. [range.istream.iterator] specifies the iterator's behavior: ¶4 `*it` returns a reference to the view's `value_`; ¶2 `++it` reads another value; ¶5 comparison with `default_sentinel` checks `!*stream_`, ending once the stream enters a failed state.

```cpp run ok
#include <ranges>
#include <sstream>
#include <cstdio>
int main() {
  std::istringstream in{"1 2 3 4"};
  auto v = std::views::istream<int>(in);
  auto it = v.begin();   // begin() has already read 1
  int x = 0;
  in >> x;               // reads 2
  std::printf("%d %d\n", *it, x);   // 1 2
}
```

Several things follow:

- It can be traversed only once. The iterator is move-only, not copyable, and the view has no const `begin()`;
- Calling `begin()` itself consumes input. This is exactly why [[range.range]] requires `begin` to be equality-preserving only for forward iterators, and why `ranges::empty` falls back to comparing `begin() == end()` only for forward ranges ([[range.prim.empty]]);
- The current element is stored in the view object, so it is not a borrowed range, and iterators cannot be dereferenced after the view is destroyed.

!!! pitfall "Reading one extra element when combined with take_while"
    The standard's example in [[range.take.while]] shows this: with `views::istream<int>(input) | views::take_while(small)`, by the time `5` is found not to satisfy the predicate, `5` has already been read from the stream, and a subsequent `input >> i` after the loop reads `6`. Lazy evaluation does not mean nothing extra is read; testing the termination condition itself requires taking out an element.

## Summary

| Factory | Source of elements | Iterator category | Borrowed |
|---|---|---|---|
| `views::empty<T>` | none | contiguous, sized, common | yes |
| `views::single(x)` | a copy inside the view | contiguous, sized, common | no |
| `views::repeat(x[, n])` | one object inside the view, referenced repeatedly | random access; sized and common when bounded | no |
| `views::istream<T>(s)` | a stream, read starting at `begin()` | input, move-only iterator | no |
| `views::iota`, `views::indices` | increasing values | see [[range.iota]] | yes |
