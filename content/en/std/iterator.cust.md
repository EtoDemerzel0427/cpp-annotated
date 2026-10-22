---
title: ranges::iter_move and ranges::iter_swap
summary: "How generic code moves an element out of an iterator and swaps the elements two iterators point to: the two customization point objects first look for a user-provided version via ADL, then fall back to a default; iterators that return proxy objects depend on them to be moved and swapped correctly by algorithms."
updated: 2026-10-19
---

!!! tldr
    - In generic code, move an element out of an iterator with `ranges::iter_move(it)` and swap the elements two iterators point to with `ranges::iter_swap(a, b)`, not with `std::move(*it)` or `std::swap(*a, *b)`.
    - `iter_move(E)` first looks for a user customization found only by ADL; failing that, it returns `std::move(*E)` if `*E` is an lvalue, and `*E` itself otherwise.
    - `iter_swap(E1, E2)` first looks for an ADL customization, then tries `ranges::swap(*E1, *E2)`, and finally swaps with three moves.
    - A customization may change only how values are taken out or swapped, not what the values are; violating this makes the program {{ifndr}}.
    - `iter_rvalue_reference_t<I>` is defined by the return type of `iter_move`.

## The problem with proxy iterators

C++11 generic algorithms move an element out like this: `T tmp = std::move(*it);`. That works for `vector<int>::iterator`. But for some iterators `*it` returns not a reference but a temporary **proxy object** standing for the underlying element, for example `vector<bool>::iterator` and the iterators of `views::zip`. For such iterators, `std::move(*it)` merely turns the proxy into an rvalue without moving the underlying element, and `std::swap(*a, *b)` swaps only two temporary proxies.

C++20 made these two operations customizable: `ranges::iter_move` and `ranges::iter_swap`. They are **customization point objects** ([[customization.point.object]]): function objects that first try a user-provided version and fall back to a reasonable default implementation otherwise.

Their results also take part in defining associated types: `iter_rvalue_reference_t<I>` is `decltype(ranges::iter_move(declval<I&>()))`, and `indirectly_readable` requires `iter_reference_t` and `iter_rvalue_reference_t` to have a common reference ([[iterator.concept.readable]]).

## `ranges::iter_move` [iterator.cust.move]

¶1 For a subexpression `E`, `ranges::iter_move(E)` is [[g:expression-equivalent]] to the first applicable expression below:

1. (1.1) If `E` has class or enumeration type and `iter_move(E)` is well-formed when treated as an unevaluated operand, where the name `iter_move` is looked up only by argument-dependent lookup (ADL, [[basic.lookup.argdep]]): `iter_move(E)`.
2. (1.2) Otherwise, if `*E` is well-formed: `std::move(*E)` if `*E` is an lvalue, `*E` otherwise.
3. (1.3) Otherwise it is ill-formed. Note 1 points out that when this happens in the immediate context of a template instantiation it causes a substitution failure, so `ranges::iter_move` can be used safely in SFINAE on non-dereferenceable types.

"Only by ADL" means ordinary unqualified lookup takes no part. An `iter_move` template written in the global namespace is not found; only declarations in namespaces associated with the type of `E` (hidden friends included) count.

```cpp run title="iter_move_types.cpp" ok
#include <iterator>
#include <string>
#include <utility>

int* p;
static_assert(std::same_as<decltype(std::ranges::iter_move(p)), int&&>);
static_assert(std::same_as<std::iter_rvalue_reference_t<int*>, int&&>);

struct X {   // operator* returns an xvalue
  using value_type = std::string;
  using difference_type = long;
  std::string* s;
  std::string&& operator*() const { return std::move(*s); }
  X& operator++();
  X operator++(int);
};
static_assert(std::same_as<std::iter_rvalue_reference_t<X>, std::string&&>);

int main() {}
```

`int*` is not a class type, so (1.1) does not apply; `*p` is an lvalue, so the result is `std::move(*p)`, of type `int&&`. For `X`, `*x` is an xvalue, not an lvalue, so (1.2) returns `*x` directly, whose type is still `std::string&&`.

¶2 Customizations must also obey a semantic rule:

!!! std
    If ranges::iter_move(E) is not equal to *E, the program is ill-formed, no diagnostic required.

    That is, if `ranges::iter_move(E)` is not equal to `*E`, the program is {{ifndr}}.

In other words, a customization may change only how the value is taken out (moved or copied, what type is returned), not what the value taken out is.

!!! impl "The libc++ implementation"
    libc++ declares `void iter_move() = delete;` in an internal namespace and then uses three mutually exclusive concepts for (1.1) and the two cases of (1.2), each with its own `operator()` overload. The deleted nullary declaration makes unqualified lookup stop in that namespace without going further out to find some other `iter_move`, so in effect only ADL remains.

## `ranges::iter_swap` [iterator.cust.swap]

¶1 `ranges::iter_swap` swaps the values denoted by its arguments (for what it means to swap values, see [[concept.swappable]]).

¶2–¶3 First an exposition-only function template *iter-exchange-move*`(x, y)` is defined:

```cpp
iter_value_t<X> old_value(iter_move(x));
*x = iter_move(y);
return old_value;
```

It moves `*x` out to a temporary, moves `*y` into `*x`, and returns the old value. Whether it is `noexcept` is decided by these two steps.

¶4 `ranges::iter_swap(E1, E2)` is equivalent to the first applicable expression below:

1. (4.1) If `E1` or `E2` has class or enumeration type and `iter_swap(E1, E2)` is well-formed: `(void)iter_swap(E1, E2)`. Overload resolution here is performed in a special context that contains the declaration `template<class I1, class I2> void iter_swap(I1, I2) = delete;` and does not include `ranges::iter_swap` itself. If the selected function does not swap the values denoted by the two, the program is {{ifndr}}.
2. (4.2) Otherwise, if both types model `indirectly_readable` and their reference types model `swappable_with`: `ranges::swap(*E1, *E2)`.
3. (4.3) Otherwise, if the two types `T1` and `T2` model `indirectly_movable_storable` with respect to each other ([[alg.req]]): `(void)(*E1 = iter-exchange-move(E2, E1))`, except that `E1` is evaluated only once.
4. (4.4) Otherwise it is ill-formed. As with `iter_move`, this can cause a substitution failure.

### What the deleted `iter_swap` template is for

The deleted template in (4.1) is unconstrained and takes two parameters by value, the same shape as `std::iter_swap(ForwardIt1, ForwardIt2)`. If an iterator type is associated with namespace `std` (say it is `std::vector<MyType>::iterator`, or a template argument comes from `std`), ADL finds the equally unconstrained `std::iter_swap`. The deleted template matches just as well, overload resolution fails with an ambiguity, (4.1) does not hold, and we move on to (4.2).

Note 1 points out the other side: when the deleted template is viable, a user customization must be more specialized than it ([[temp.func.order]]) to be selected. A hidden friend whose parameters have concrete types, or a template whose parameters have concrete types, meets this.

## Example: a zip-like proxy iterator

```cpp run title="iter_move_swap.cpp" ok
#include <cassert>
#include <iterator>
#include <utility>

namespace lib {
struct Ref {                       // the proxy returned by *it
  int* a; int* b;
  operator std::pair<int, int>() const { return {*a, *b}; }
};
struct It {
  int* a; int* b;
  using value_type = std::pair<int, int>;
  using difference_type = std::ptrdiff_t;
  Ref operator*() const { return {a, b}; }
  It& operator++() { ++a; ++b; return *this; }
  It operator++(int) { auto t = *this; ++*this; return t; }
  bool operator==(const It&) const = default;
  // hidden friends: found only by ADL
  friend std::pair<int, int> iter_move(const It& i) { return {*i.a, *i.b}; }
  friend void iter_swap(const It& x, const It& y) {
    std::swap(*x.a, *y.a);
    std::swap(*x.b, *y.b);
  }
};
}

static_assert(std::same_as<std::iter_rvalue_reference_t<lib::It>,
                           std::pair<int, int>>);

int main() {
  int a[]{1, 2}, b[]{3, 4};
  lib::It x{a, b}, y{a + 1, b + 1};
  std::ranges::iter_swap(x, y);    // calls the hidden friend via (4.1)
  assert(a[0] == 2 && a[1] == 1 && b[0] == 4 && b[1] == 3);
}
```

Without these two hidden friends, `It` is still `indirectly_readable`: `Ref` converts to `pair<int, int>`, and their common reference type is `pair<int, int>`. But:

- `ranges::iter_move(x)` takes the second case of (1.2) and returns the `Ref` prvalue itself. In an algorithm, `iter_value_t<I> tmp(ranges::iter_move(it));` then copies instead of moving; when the elements are `pair<std::string, std::string>`, that is a real performance difference.
- None of the three paths of `ranges::iter_swap(x, y)` works. `Ref` prvalues cannot be `ranges::swap`ped; (4.3) requires a `pair<int, int>` to be assignable to `*x`, and `Ref` cannot be assigned from a `pair`. So `indirectly_swappable<It>` is false, and algorithms that need `permutable`, such as `ranges::sort`, reject it.

Clang 23 confirmed these points in our tests: without the two friends, `indirectly_readable<It>` is true, `iter_rvalue_reference_t<It>` is `Ref`, and `indirectly_swappable<It>` is false.

The standard library's `vector<bool>::iterator` does not customize `iter_move`. Its `*it` returns a `vector<bool>::reference` prvalue, `iter_rvalue_reference_t` is that proxy type, and its common reference with `bool&` is `bool`. It can be swapped because the proxy can be assigned from `bool` and the library provides a `swap` overload for it.

## How adaptors forward

The iterator adaptors all provide `iter_move` and `iter_swap` as hidden friends that forward the operations to the underlying iterator, so user customizations pass through the wrapper:

- `reverse_iterator` first copies the underlying iterator and decrements it, then calls `ranges::iter_move` on it ([[reverse.iterators]]);
- `move_iterator`, `counted_iterator`, `common_iterator` and `basic_const_iterator` forward directly ([[move.iterators]], [[iterators.counted]], [[iterators.common]], [[const.iterators]]).

## Common misconceptions

!!! pitfall "Writing `std::move(*it)` in generic algorithms"
    For proxy iterators, `std::move(*it)`, `std::swap(*a, *b)` and `std::iter_swap(a, b)` either do not really move or swap, or fail to compile. `std::ranges::sort` can sort `views::zip(a, b)` because it uses `ranges::iter_move` and `ranges::iter_swap`. `std::sort` requires *Cpp17RandomAccessIterator*, which zip's iterator does not meet (`*it` is not a reference), so by the standard it cannot be used this way; with libc++ (Clang 23) it happens to compile and sort correctly, which the standard does not guarantee.

!!! pitfall "Customizing with an unconstrained template"
    ```cpp
    namespace mine {
      template<class I> void iter_swap(I a, I b);   // not more specialized than the deleted template
    }
    ```
    For iterators associated with `std`, such a customization is ambiguous with the deleted template and is therefore skipped. Following Note 1's advice, write it as a hidden friend with concrete parameter types.

## Questions

!!! question "Question"
    Why does (4.1) require `E1` or `E2` to have class or enumeration type?

<details markdown="1">
<summary>Answer</summary>

Scalar types like pointers have no associated classes, so ADL cannot find any user customization and there is no point trying; nor should users be allowed to change how pointers swap. `ranges::swap` has the same restriction ([[concept.swappable]]).
</details>
