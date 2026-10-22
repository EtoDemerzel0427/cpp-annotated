---
title: Range access
summary: "How the customization point objects ranges::begin, end, cbegin, rbegin, size, ssize, reserve_hint, empty, data and cdata choose an implementation: arrays, members, non-members found only by argument-dependent lookup, plus checks on the result type and on rvalues."
updated: 2026-10-19
---

!!! tldr
    - `ranges::begin(E)` tries in order: an array, a member `begin()`, and a `begin()` found only by argument-dependent lookup; each step requires the result to be an iterator, otherwise it moves on to the next.
    - For an rvalue non-borrowed range, `begin`, `end`, `cbegin`, `rbegin` and `data` all refuse the call, because the resulting iterator or pointer would dangle; `size`, `ssize` and `empty` do not.
    - `std::ranges::range` is defined with `ranges::begin` and `ranges::end`, so whether a type is a range is decided entirely by the rules of this subclause.
    - Since C++23, `ranges::cbegin` is guaranteed to return a constant iterator; the libc++ we test with does not implement this yet.
    - When the conditions are not met, the result is a substitution failure rather than a hard error, so these are safe to use in concepts and `requires`.

## Three problems with std::begin

`std::begin(c)` ([[iterator.range]]) is an ordinary function template:

- If a user type provides only a non-member `begin`, you must write the two-step `using std::begin; begin(c);` to find it;
- It does not check the return value; a `begin()` returning `int` is accepted as is;
- It accepts rvalue containers: `std::begin(std::vector<int>{})` returns an iterator that dangles immediately.

[range.access] solves all three with a set of **customization point objects** ([[g:customization-point-object]]). A customization point object is a function object whose call operator looks for an implementation in a fixed order and checks the result type ([[customization.point.object]]).

```cpp run ok
#include <ranges>
#include <vector>
namespace lib {
  struct Bag { int data[3]{1, 2, 3}; };
  // non-member begin/end: can only be found by argument-dependent lookup
  inline int* begin(Bag& b) { return b.data; }
  inline int* end(Bag& b) { return b.data + 3; }
}
using std::ranges::range;
template<class R>
concept can_begin = requires(R&& r) {
  std::ranges::begin(std::forward<R>(r));
};

static_assert(range<lib::Bag>);           // ¶2.5: finds lib::begin
static_assert(!range<const lib::Bag>);    // const Bag& cannot bind to Bag&
static_assert(!can_begin<lib::Bag>);      // ¶2.1: rvalue, not borrowed
static_assert(can_begin<std::vector<int>&>);
static_assert(!can_begin<std::vector<int>>);
static_assert(can_begin<std::ranges::subrange<int*>>);  // rvalue of a borrowed range

int main() {
  lib::Bag b;
  int s = 0;
  for (int x : b) s += x;   // range-based for also uses argument-dependent lookup
  return s == 6 ? 0 : 1;
}
```

## Common premises [range.access.general]

¶1 These customization point objects are available in both `<ranges>` and `<iterator>`.

¶2 What follows repeatedly uses the **reified object** ([[g:reified-object]]) of a subexpression `E`: if `E` is a glvalue, it is the object `E` refers to; if `E` is a prvalue, it is the temporary obtained by applying the temporary materialization conversion ([[conv.rval]]) to it.

Every customization point object says "let `t` be an lvalue that denotes the reified object for `E`". That is, whether an lvalue or an rvalue is passed, everything afterwards calls `t.begin()` or `begin(t)` on the lvalue `t`. Whether `E` is an rvalue only decides, in the first step, whether to refuse.

## ranges::begin [range.access.begin]

¶2 Given a subexpression `E` of type `T`, the checks are, in order:

| Item | Condition | `ranges::begin(E)` |
|---|---|---|
| 2.1 | `E` is an rvalue and `enable_borrowed_range<remove_cv_t<T>>` is `false` | {{ill-formed}} |
| 2.2 | `T` is an array whose element type is incomplete | {{ifndr}} |
| 2.3 | `T` is an array | `t + 0` |
| 2.4 | `auto(t.begin())` is valid and its type models `input_or_output_iterator` | `auto(t.begin())` |
| 2.5 | `T` is a class or enumeration, `auto(begin(t))` found only by argument-dependent lookup is valid and its type models `input_or_output_iterator` | that expression |
| 2.6 | otherwise | {{ill-formed}} |

2.1 rejects rvalues because the resulting iterator would become invalid together with the temporary. A **borrowed range** is the exception: its iterators point into storage elsewhere and do not depend on the range object staying alive, e.g. `string_view`, `span`, `subrange` ([[range.range#4]]). A type declares this by specializing the variable template `enable_borrowed_range` to `true`.

2.3 writes `t + 0` instead of `t` to get a pointer prvalue rather than an array lvalue.

`auto(x)` is the C++23 decay-copy notation ([[expr.type.conv]]): the result is always a copy by value, so even a `begin()` that returns a reference decays to a value.

Both 2.4 and 2.5 check the result type. If a member `begin()` exists but does not return an iterator, 2.4 does not choose it and 2.5 is tried; if neither works, it is ill-formed. So a type that happens to have a member named `begin` is not mistaken for a range:

```cpp run ok
#include <ranges>
// begin() returns int rather than an iterator: rejected by the customization point object
struct Weird { int begin() { return 0; } int end() { return 0; } };
static_assert(!std::ranges::range<Weird>);
int main() {}
```

2.5 uses only argument-dependent lookup ([[basic.lookup.argdep]]); ordinary unqualified lookup does not take part. Otherwise it would find `std::begin` itself and drag in an unconstrained template.

¶3 Note 1 explains that when the diagnosable ill-formed cases above appear in the immediate context of a template instantiation, they result in substitution failure. This is exactly what [[customization.point.object]] requires: when the conditions are not met, there is no call operator that can take part in overload resolution. ¶4 Note 2: whenever `ranges::begin(E)` is valid, its type models `input_or_output_iterator`.

!!! history "Poison pills"
    The original C++20 wording was: overload resolution for the non-member `begin(t)` is performed in a context that declares some deleted `begin` function templates. These deleted declarations were nicknamed poison pills; their purpose was to stop unqualified lookup there so that `std::begin` was not found. But the poison pills were themselves candidates in overload resolution, and sometimes matched better than a user's legitimate customization, blocking it instead. [[P2602R2]] changed this, as a defect report, to today's "as if only argument-dependent lookup were performed".

!!! impl "How libc++ implements argument-dependent-lookup only"
    libc++ declares `void begin() = delete;`, a deleted function with zero parameters, in the internal namespace that holds the customization point object. Unqualified lookup stops there and does not go further out to find `std::begin`; since it accepts no arguments it is never viable, so the effect is that only candidates found by argument-dependent lookup remain. The function object also ends with a catch-all `void operator()(auto&&) const = delete;`.

## ranges::end [range.access.end]

¶2 Has the same structure as `begin`, with three differences:

- 2.3 An array of unknown bound (`int[]`) is ill-formed, since there is no known end;
- 2.4 An array of known bound gives `t + extent_v<T>`;
- 2.5, 2.6 The result of a member `end()` or non-member `end(t)` must model `sentinel_for<iterator_t<T>>`, i.e. `end` is checked against the result type of `begin`.

¶4 Note 2: whenever both are valid, the type `S` of `end` and the type `I` of `begin` model `sentinel_for<S, I>`.

## cbegin and cend [range.access.cbegin]

¶1 Since C++23 ([[P2278R4]]) they are guaranteed to return constant iterators (elements cannot be modified through them, see [[const.iterators]]):

- 1.1 An rvalue non-borrowed range is ill-formed;
- 1.2 Let `U` be `ranges::begin(possibly-const-range(t))`; the result is `const_iterator<decltype(U)>(U)`.

*`possibly-const-range(r)`* returns `const R&` when `const R` is an input range, and `R&` otherwise ([[ranges.syn]]). For `vector<int>`, adding const gives a `const_iterator`, which `const_iterator<>` no longer wraps. For a view like `filter_view` that has no const `begin()`, only a non-const iterator is available, and `const_iterator<>` wraps it in a `basic_const_iterator`, whose dereference gives `const int&`.

This fixes an old C++20 problem. In C++20, `ranges::cbegin(s)` merely called `begin` on a `const span<int>`, and since `span`'s constness does not propagate to its elements, the result was still writable.

[range.access.cend] ¶1 `cend` symmetrically uses `ranges::end` and `const_sentinel`.

```cpp run
#include <ranges>
#include <span>
#include <type_traits>
#include <vector>
int main() {
  std::vector<int> v{1, 2, 3};
  std::span<int> s = v;
  auto it = std::ranges::cbegin(s);
  static_assert(std::is_same_v<decltype(*it), const int&>);
  auto ev = v | std::views::filter([](int x) { return x > 1; });
  auto ci = std::ranges::cbegin(ev);   // works even without a const begin()
  static_assert(std::is_same_v<decltype(*ci), const int&>);
  return *ci == 2 ? 0 : 1;
}
```

According to the standard this code should compile. The libc++ we test with does not implement [[P2278R4]] yet and still follows C++20 by just calling `begin` on a const object: `ranges::cbegin(s)` returns a writable iterator, so the first `static_assert` fails; `filter_view` has no const `begin()`, so `ranges::cbegin(ev)` is an error outright. That is why this example has no verdict mark.

## rbegin, rend, crbegin, crend

[range.access.rbegin] ¶2 First tries a member `rbegin()`, then an `rbegin(t)` found only by argument-dependent lookup; both require the result to be an iterator. 2.5 is the final fallback: if `ranges::begin(t)` and `ranges::end(t)` have the same type and it models `bidirectional_iterator`, the result is `make_reverse_iterator(ranges::end(t))`.

The fallback requires begin and end to have the same type because `reverse_iterator` needs to start from an iterator and walk backwards, while a sentinel is generally neither an iterator nor decrementable. A range whose begin and end differ in type must first go through `views::common`.

[range.access.rend] symmetrically uses `make_reverse_iterator(ranges::begin(t))` and requires the result to be a sentinel for the result of `rbegin`. [range.access.crbegin] and [range.access.crend] work like `cbegin` and `cend`: they call `rbegin` and `rend` on *`possibly-const-range(t)`* and wrap the result in `const_iterator` or `const_sentinel`.

## ranges::size [range.prim.size]

¶2 The order is:

1. An array of unknown bound: ill-formed;
2. An array: `auto(extent_v<T>)`;
3. `disable_sized_range<remove_cv_t<T>>` is `false` and `auto(t.size())` is integer-like (a type that behaves like an integer, including built-in integers, [[iterator.concept.winc]]): use the member;
4. `T` is a class or enumeration, not disabled, and `auto(size(t))` found only by argument-dependent lookup is integer-like: use it;
5. With `I` and `S` the types of `begin` and `end`, if they model `sized_sentinel_for<S, I>` and `forward_iterator<I>`: `to-unsigned-like(end - begin)`;
6. Otherwise: ill-formed.

Unlike `begin`, `size` does not reject rvalues. A length is a value that does not depend on the container staying alive after the call, so `ranges::size(std::vector<int>(3))` is valid.

`disable_sized_range` ([[range.sized#3]]) turns off steps 3 and 4: when a type has a `size()` member that is not constant time, or means something else, specialize it to `true`.

Step 5 requires a forward iterator. For a single-pass input iterator, computing `end - begin` might itself invalidate `begin`.

The result is not necessarily unsigned: if the member `size()` returns `int`, `ranges::size` returns `int`. Only step 5 forces a conversion to unsigned.

## ranges::ssize [range.prim.ssize]

¶2 If `ranges::size(t)` is ill-formed, so is `ssize`. Otherwise let `D` be *`make-signed-like-t<decltype(ranges::size(t))>`*, or `ptrdiff_t` if that is wider; the result is `static_cast<D>(ranges::size(t))`. With it, `for (auto i = 0; i < ranges::ssize(v); ++i)` no longer warns about a signed/unsigned comparison.

```cpp run ok
#include <cstddef>
#include <ranges>
#include <vector>
struct S { int* begin(); int* end(); int size() const { return 3; } };
// member size() returns int: ranges::size returns int unchanged
static_assert(std::same_as<
    decltype(std::ranges::size(std::declval<S&>())), int>);
// ssize: make-signed-like-t<int> is int; ptrdiff_t is wider, so ptrdiff_t is used
static_assert(std::same_as<
    decltype(std::ranges::ssize(std::declval<S&>())), std::ptrdiff_t>);
// size does not reject rvalues
static_assert(std::ranges::size(std::vector<int>(3)) == 3);
int main() {}
```

## ranges::reserve_hint [range.prim.size.hint] {{c++26}}

¶2 If `ranges::size(E)` is valid, it is used; otherwise a member `t.reserve_hint()` and then a `reserve_hint(t)` found only by argument-dependent lookup are tried, and the result must be integer-like in each case.

It serves C++26's `approximately_sized_range` ([[range.approximately.sized]]). Some ranges cannot give an exact length in constant time but can give an estimate, which `ranges::to` can use to `reserve` in advance. The libc++ we test with does not provide this customization point object yet.

## ranges::empty [range.prim.empty]

¶2 The order is: an array of unknown bound is ill-formed; `bool(t.empty())`; `(ranges::size(t) == 0)`; if the type of `begin` models `forward_iterator`, `bool(ranges::begin(t) == ranges::end(t))`; otherwise ill-formed.

It does not reject rvalues either. The last step requires a forward iterator because calling `begin` on an input range may itself have side effects; for example, `begin` on an `istream_view` reads a value ([[range.factories]]).

## ranges::data and ranges::cdata

[range.prim.data] ¶2 The order is: an rvalue non-borrowed range is ill-formed; an array with incomplete element type is IFNDR; if `auto(t.data())` has object pointer type, use the member; if `ranges::begin(t)` models `contiguous_iterator`, use `to_address(ranges::begin(t))`; otherwise ill-formed.

[range.prim.cdata] ¶1 `cdata` is equivalent to *`as-const-pointer`*`(ranges::data(possibly-const-range(t)))`. *`as-const-pointer`* just turns `T*` into `const T*`.

## Customization point objects vs. function templates

| | `std::begin` (function template) | `ranges::begin` (customization point object) |
|---|---|---|
| Supports a user's non-member `begin` | needs the two-step `using std::begin;` | one qualified call, with argument-dependent lookup inside |
| Checks the result type | no | must be an iterator, otherwise substitution failure |
| Rvalue protection | none | rejects rvalues of non-borrowed ranges |
| Passed as an object | an overload set, cannot be passed directly | an object; can be copied and used as a template argument |
| Hijacked by argument-dependent lookup | possible | no; objects do not take part in argument-dependent lookup |

## Common misconceptions

!!! pitfall "A type with begin and end members is a range"
    `range<T>` checks whether `ranges::begin(t)` and `ranges::end(t)` pass all the rules above. A member `begin()` that does not return an iterator, an `end()` that does not return a matching sentinel, or a missing const version all make it `false`. Debugging with `static_assert(std::ranges::range<T>)` gives clearer error messages than writing a range-based `for` directly.

!!! pitfall "Customizing only the non-const version"
    `lib::Bag` above provides only `begin(Bag&)`, so `const Bag` is not a range and `views::all(std::as_const(b))` fails too. View adaptors often require `range<const V>`, e.g. `transform_view::begin() const`, so a customization should provide const overloads as well.

## Questions

!!! question "Question 1"
    Is `ranges::size(std::vector<int>{1, 2, 3})` valid? What about `ranges::begin(std::vector<int>{1, 2, 3})`? Why the difference?

<details markdown="1">
<summary>Answer</summary>

The former is valid and returns 3; the latter is ill-formed. [range.prim.size] ¶2 has no item rejecting non-borrowed rvalues, because a length is a value that does not depend on the container staying alive after the call. [range.access.begin] ¶2.1 explicitly rejects non-borrowed rvalues, because the resulting iterator would point into a temporary that has already been destroyed.
</details>

!!! question "Question 2"
    A type has both a member `begin()` (returning `int*`) and a non-member `begin(T&)` visible to argument-dependent lookup (returning a different iterator). Which does `ranges::begin` choose?

<details markdown="1">
<summary>Answer</summary>

The member. ¶2.4 comes before ¶2.5; when the member version is valid and returns an iterator it is used, and the non-member version is never considered. Argument-dependent lookup gets its turn only when the member does not exist or does not return an `input_or_output_iterator`.
</details>
