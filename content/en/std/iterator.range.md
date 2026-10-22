---
title: Range access functions
summary: "The non-member function templates std::begin, std::end, std::size, std::data and friends: for containers they forward to the member functions, for built-in arrays they give the pointer and length, so generic code can use one spelling for both."
updated: 2026-10-19
---

!!! tldr
    - `std::begin(c)` is just `c.begin()`, and `std::size(c)` is just `c.size()`; their use is to give built-in arrays the same spelling.
    - `std::ssize` returns a signed type, avoiding the underflow of `v.size() - 1` on an empty container.
    - `std::cbegin(c)` is merely `std::begin` with const added, and does not guarantee a read-only iterator for views like `span<int>`.
    - All of these functions can bind temporaries, and the returned iterators become invalid along with the temporary; C++20's `std::ranges::begin` and friends reject such calls at compile time, and new code should prefer them.

## Why non-member versions are needed

```cpp run title="range_access.cpp" ok
#include <cstdio>
#include <iterator>
#include <ranges>
#include <vector>

int main() {
  int a[4]{1, 2, 3, 4};
  static_assert(std::size(a) == 4 && std::ssize(a) == 4);
  static_assert(!std::empty(a));
  static_assert(std::same_as<decltype(std::rbegin(a)),
                             std::reverse_iterator<int*>>);

  std::vector<int> v{1, 2, 3};
  static_assert(std::same_as<decltype(std::ssize(v)), std::ptrdiff_t>);
  for (auto i = std::ssize(v) - 1; i >= 0; --i)  // signed: safe to iterate backwards
    std::printf("%d", v[i]);
  std::puts("");

  std::initializer_list<int> il{1, 2, 3};
  auto r = std::rbegin(il);                      // initializer_list overload
  std::printf("%d\n", *r);
}
```

Built-in arrays have no member functions; you cannot write `a.begin()`. Generic code writes `std::begin(x)`, which works whether `x` is a `std::vector<int>` or an `int[4]`. [iterator.range] provides exactly such a set of non-member function templates: for containers they forward to the member function of the same name, for arrays they give the pointer and length directly.

¶1 Besides `<iterator>`, these functions are also available when any of 21 headers is included, among them `<array>`, `<vector>`, `<string>`, `<string_view>`, `<span>` and `<optional>`. `<optional>` is on the list because since C++26 `optional` is itself a range of at most one element, with `begin()` and `end()`.

## Overview of the functions

| Function | Returns | Paragraphs |
|---|---|---|
| `begin(c)`, `end(c)` | `c.begin()`, `c.end()` | ¶2–¶3 |
| `begin(arr)`, `end(arr)` | `arr`, `arr + N` | ¶4–¶5 |
| `cbegin(c)`, `cend(c)` | `std::begin(c)`, `std::end(c)`, parameter is `const C&` | ¶6–¶7 |
| `rbegin(c)`, `rend(c)` | `c.rbegin()`, `c.rend()` | ¶8–¶9 |
| `rbegin(arr)`, `rend(arr)` | `reverse_iterator<T*>(arr + N)`, `reverse_iterator<T*>(arr)` | ¶10–¶11 |
| `rbegin(il)`, `rend(il)` | reverse iterators of `initializer_list<E>` | ¶12–¶13 |
| `crbegin(c)`, `crend(c)` | `std::rbegin(c)`, `std::rend(c)`, parameter is `const C&` | ¶14–¶15 |
| `size(c)`, `size(arr)` | `c.size()`, `N` (`size_t`) | ¶16–¶17 |
| `ssize(c)`, `ssize(arr)` | the length as a signed value | ¶18–¶19 |
| `empty(c)`, `empty(arr)` | `c.empty()`, `false` | ¶20–¶21 |
| `data(c)`, `data(arr)` | `c.data()`, `arr` | ¶22–¶23 |

They are all constexpr functions. The noexcept of the container versions follows the corresponding member function, e.g. `noexcept(noexcept(c.begin()))`; the array versions are unconditionally noexcept. The container versions all have trailing return types such as `decltype(c.begin())`, so for a type without the corresponding member, substitution failure merely removes that overload from overload resolution.

## A few details worth noting

¶21 `empty(arr)` is always `false`. In C++ an array's length must be greater than zero ([[dcl.array]]); there are no empty arrays.

¶18 `ssize(c)` returns the common type of `ptrdiff_t` and `make_signed_t<decltype(c.size())>`, which is usually just `ptrdiff_t`. If some container's `size_type` is wider than `ptrdiff_t`, the result widens accordingly instead of truncating. Its main use is subtraction and comparison with negative numbers:

<div class="compare" markdown="1">

```cpp
// i is unsigned and always >= 0: infinite loop
for (auto i = v.size() - 1; i >= 0; --i)
```

```cpp
// i is ptrdiff_t: terminates normally
for (auto i = std::ssize(v) - 1; i >= 0; --i)
```

</div>

¶19 The template parameter of `ssize(arr)` is written `ptrdiff_t N`. The type of an array bound is `size_t`, but template argument deduction allows it to be received by a non-type template parameter of another integer type ([[temp.deduct.type]]), and the deduced value is the same.

¶6 `cbegin(c)` has a single `const C&` overload and returns `std::begin(c)`. It relies on const to get a constant iterator. For views like `std::span<int>`, const applies only to the view itself: `begin()` on a `const span<int>` still returns a writable iterator, and `std::cbegin` does not help. Only C++23's `std::ranges::cbegin` guarantees a constant iterator ([[const.iterators]]).

¶12–¶13 Only two dedicated overloads remain for `initializer_list`: `rbegin` and `rend`. C++26 added `data()` and `empty()` members to `initializer_list` ([[support.initlist]]), so the generic `std::data(c)` and `std::empty(c)` can be used directly; the non-member `begin` and `end` overloads for it that used to live in `<initializer_list>` were also removed, leaving the job to the generic `begin(const C&)`. `initializer_list` has no `rbegin()` member, so the two reverse overloads still have to stay.

!!! lawyer "The exception specification of crend"
    In the current draft, the declaration before ¶15 gives `crend` the exception specification `noexcept(noexcept(c.crend()))`, while its return type is `decltype(std::rend(c))`; the synopsis in [[iterator.synopsis]] has `noexcept(noexcept(std::rend(c)))` instead. `crbegin` uses `std::rbegin(c)`, so by symmetry the former looks like a typo: built-in arrays have no `crend()` member at all. Go by the synopsis when reading the intent.

## `using std::begin; begin(x);` and ranges::begin

From C++11 to C++17, generic code that wanted to support arrays, types with a member `begin`, and user types providing only a non-member `begin` used this idiom:

```cpp
using std::begin;
auto it = begin(x);  // unqualified call: ordinary lookup finds std::begin,
                     // argument-dependent lookup also finds begin in x's namespace
```

The range-based `for` statement does the same in the core language: it looks for a member `begin` first, and uses argument-dependent lookup if there is none ([[stmt.ranged]], [[basic.lookup.argdep]]). The idiom has two problems: forget the `using` and arrays are not supported; and argument-dependent lookup may find an unrelated, unconstrained `begin`.

C++20's `std::ranges::begin` is a **customization point object**: a function object that tries, in a fixed order, arrays, a member `begin()`, and a `begin()` found by argument-dependent lookup ([[range.access]]). It also requires the result to model `input_or_output_iterator`, and rejects calls on rvalue non-borrowed ranges at compile time. New code should prefer `ranges::begin`, `ranges::end`, `ranges::size`, `ranges::ssize`, `ranges::empty` and `ranges::data`.

## Common misconceptions

!!! pitfall "The iterator from `std::begin(f())` is usable"
    `std::begin(const C&)` can bind a temporary, and the returned iterator becomes invalid together with the temporary container at the end of the full-expression. `std::ranges::begin(std::vector<int>{1})` simply fails to compile; Clang 23 reports a call to a deleted function.

!!! pitfall "`std::rbegin({1, 2, 3})` can be kept around"
    The call compiles, using exactly the `initializer_list<E>` overload. But the array behind `{1, 2, 3}` ([[dcl.init.list]]) lives only until the end of the full-expression, and `auto r = std::rbegin({1, 2, 3}); *r;` is reported as stack-use-after-scope under AddressSanitizer. Bind the list to a named `initializer_list` variable first, and the backing array's lifetime is extended with it, like `il` in the full example above.

## Questions

!!! question "Question"
    Why does `std::cbegin` have only a `const C&` overload, while `std::begin` has both `C&` and `const C&`?

<details markdown="1">
<summary>Answer</summary>

The whole point of `cbegin` is to call `begin` in a const way, so its parameter only needs to be `const C&`, which binds to both lvalues and rvalues. `begin` needs the `C&` overload to return a writable iterator for non-const containers.
</details>
