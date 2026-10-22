---
title: Optional objects
summary: "An overview of <optional>: what an optional object is, why nullopt_t cannot be constructed from {}, the comparison rules between optional and optional, nullopt and T, swap, make_optional, hash, bad_optional_access and the header synopsis."
updated: 2026-10-19
---

!!! tldr
    - `optional<T>` keeps the storage for `T` inside itself and allocates no heap memory; when it has no value, there is no `T` object in it at all.
    - The comparison rules boil down to one sentence: an empty optional is less than any value and equal only to another empty optional. Each operator forwards to the operator of the same name on `T`, without inventing relations `T` does not have.
    - `nullopt_t` deliberately cannot be constructed from `{}`, so `o = {}` is not ambiguous, and its effect is to empty `o`.
    - Since C++26 `make_optional<int&>(x)` returns `optional<int&>` and no longer silently decays to `optional<int>`.
    - On `optional<bool>` and `optional<T*>`, `o == false` compares the value while `!o` checks whether there is a value; the two are different.

[[optional.optional]] covers the members of the primary template, and [[optional.optional.ref]] covers C++26's `optional<T&>`. This page covers the rest: the definition, `nullopt`, the exception class, the comparison operators, `swap`, `make_optional`, `hash` and the header synopsis.

## What an optional object is ([optional.general])

```cpp run title="optional_lifetime.cpp" ok
#include <optional>
#include <cstdio>

struct Noisy {
  Noisy()  { std::puts("constructed"); }
  ~Noisy() { std::puts("destroyed"); }
};

int main() {
  std::optional<Noisy> o;        // prints nothing: there is no Noisy object
  std::puts("before emplace");
  o.emplace();                   // constructed
  o.reset();                     // destroyed
  std::puts("end of main");
}
```

The lifetime of `o` begins on the first line, but there is no `Noisy` object in it: not a default value, but no object. Only `emplace` constructs one, and `reset` destroys it again, while `o` itself stays alive.

!!! std "[optional.general]/1"
    An *optional object* is an object that contains the storage for another object and manages the lifetime of this contained object, if any.

¶1 An **optional object** contains the storage for another object and manages the lifetime of that contained object, if any. The contained object can be initialized after the optional object has been initialized and can be destroyed before the optional object is destroyed; whether it exists is tracked by the optional object itself.

These sentences correspond to three practical properties:

1. The storage is embedded. `sizeof(optional<T>)` is at least `sizeof(T)`, usually plus a `bool` and alignment padding; there is no heap allocation and no indirection.
2. The contained object's lifetime is independent of the `optional`. [[optional.optional]] describes the storage with a union member *val*; there is a value if and only if *val* is the active member of the union ([[class.union]]).
3. The state is tracked by the `optional`. A typical implementation uses a `bool` to record whether *val* exists, so as to do the right thing in destruction, copying and assignment. `optional<T&>` instead represents "no value" directly with a null pointer ([[optional.optional.ref]]).

Before `optional`, "maybe no value" was usually expressed with sentinel values (`-1`, `npos`), pointers (unclear ownership, often with an extra heap allocation) or `std::pair<T, bool>` (which requires `T` to be default-constructible and constructs a `T` even when there is no value). `optional` solves all of these problems.

## Why nullopt_t cannot be constructed from {} ([optional.nullopt])

```cpp ok
#include <optional>
void f() {
  std::optional<int> o = 5;
  o = {};    // OK: o becomes empty
}
```

¶1 `nullopt_t` is an empty class used as a marker for the empty state: `optional<T>` has a constructor whose only parameter is `nullopt_t`, which constructs an empty `optional`. `nullopt` is a constant object of this type, with an unspecified initializer.

!!! std "[optional.nullopt]/2"
    Type `nullopt_t` does not have a default constructor or an initializer-list constructor, and is not an aggregate.

¶2 specifies that `nullopt_t` has no default constructor, no initializer-list constructor, and is not an aggregate, so it cannot be constructed from `{}`. The reason lies in expressions like `o = {}`. `optional` has several assignment operators: `operator=(nullopt_t)`, `operator=(const optional&)`, `operator=(optional&&)` and others. If `nullopt_t` were an ordinary `struct nullopt_t {};`, `{}` could construct both a `nullopt_t` and an `optional`; both conversion sequences are user-defined conversions using different constructors, they cannot be ranked, and the call is ambiguous:

```cpp error
struct N {};                     // a hypothetical nullopt_t that can be constructed from {}
struct Opt {
  Opt() {}
  Opt(N) {}
  Opt& operator=(N);
  Opt& operator=(const Opt&);
  Opt& operator=(Opt&&);
};
void g(Opt o) { o = {}; }        // error: operator= is ambiguous
```

Because `nullopt_t` cannot be constructed from `{}`, `operator=(nullopt_t)` is not viable for `o = {}`. Of the remaining copy and move assignments, move assignment is better (binding an rvalue to an rvalue reference is preferred, [[over.ics.rank]]); the right-hand side is a value-initialized empty `optional`, so `o` is emptied. Another candidate, `operator=(U&&)`, is excluded by its own constraints; see the assignment section of [[optional.optional]].

¶2 also requires `nullopt_t` to model `copyable` and `three_way_comparable<strong_ordering>`: `nullopt` can be copied, and two `nullopt_t`s always compare equal.

!!! impl "How libc++ keeps users from creating a nullopt_t"
    libc++'s `nullopt_t` has a single `explicit` constructor taking two arguments of a nested tag type `__secret_tag`, and `nullopt` is initialized with `nullopt_t{nullopt_t::__secret_tag{}, nullopt_t::__secret_tag{}}`. User code will not write such a call.

## Comparison operators

All the comparison rules boil down to one sentence: **an empty optional is less than any value and equal only to another empty optional**. Formally there are three groups.

```cpp run title="cmp.cpp" ok
#include <cassert>
#include <compare>
#include <optional>

int main() {
  std::optional<int> none, zero = 0, one = 1;
  assert(none < zero);              // empty is less than any value
  assert(none < -1000);             // same when comparing with T
  assert(zero == 0 && one != 0);
  assert(none != 0);                // empty is not equal to any value
  assert(none == std::nullopt);
  assert((none <=> std::nullopt) == 0);
  assert((zero <=> none) > 0);
  std::optional<long> l = 1;
  assert(one == l);                 // optional<int> and optional<long> are comparable
}
```

### optional with optional ([optional.relops])

All six relational operators are `template<class T, class U>`, so `optional<int>` can be compared with `optional<long>`. Taking `operator<` as an example: ¶7 requires `*x < *y` to be well-formed with a result convertible to `bool`; ¶8 specifies that it returns `false` if `y` is empty, otherwise `true` if `x` is empty, otherwise `*x < *y`. The other operators (¶1–¶18) are defined by the same truth table:

| `x` | `y` | `x == y` | `x < y` | `x <= y` | `x > y` | `x >= y` |
|---|---|---|---|---|---|---|
| empty | empty | `true` | `false` | `true` | `false` | `true` |
| empty | has value | `false` | `true` | `true` | `false` | `false` |
| has value | empty | `false` | `false` | `false` | `true` | `true` |
| has value | has value | `*x == *y` | `*x < *y` | `*x <= *y` | `*x > *y` | `*x >= *y` |

Each operator forwards to the operator of the same name on `T`: `x <= y` uses `*x <= *y`, not `!(*y < *x)`. This matters for floating-point NaN and for types that define only some of the operators; `optional` does not impose on `T` an equality or ordering relation it does not have. Note 1 states explicitly that `T` need not meet *Cpp17EqualityComparable*.

These requirements are all *Constraints*: when `*x < *y` is invalid, `operator<` simply does not participate in overload resolution, and `requires { a < b; }` yields `false` instead of a hard error. The *Remarks* of each paragraph specify that the corresponding specialization is a constexpr function only if `*x < *y` and so on is a core constant expression.

¶19 `operator<=>` requires `U` to model `three_way_comparable_with<T>`; it returns `*x <=> *y` when both have values, and otherwise `x.has_value() <=> y.has_value()`. Comparing `bool`s happens to encode "empty is smallest".

### optional with nullopt ([optional.nullops])

This group has only two functions, both `noexcept`, and requires no comparison capability from `T`:

- ¶1 `operator==(const optional<T>& x, nullopt_t)` returns `!x`;
- ¶2 `operator<=>(const optional<T>& x, nullopt_t)` returns `x.has_value() <=> false`, of type `strong_ordering`.

In C++17 there were 12 functions here (6 operators, in two directions). Since C++20, `nullopt == x`, `x != nullopt`, `x < nullopt` and so on are all obtained from these two functions through rewritten candidates ([[over.match.oper]]).

### optional with T ([optional.comp.with.t])

An `optional<T>` can be compared directly with a plain value: 6 operators in each direction, plus one `<=>`. The effect matches the truth table above: when `x` has a value, `*x` is compared with `v`; when it is empty, it is treated as smallest.

¶1–¶24 The constraints of every function begin with `U` (or `T` for the other direction) **not** being a specialization of `optional`. Without this, `optional<int> == optional<long>` would match not only the version in [optional.relops] but also `operator==(const optional<T>&, const U&)` here with `U = optional<long>`; checking its constraints would in turn look at `*x == optional<long>`, that is `int == optional<long>`, which leads back to this group. Excluding `optional` specializations cuts off this back-and-forth.

¶25 The constraint of `operator<=>` is `!is-derived-from-optional<U> && three_way_comparable_with<T, U>`. The exposition-only concept *is-derived-from-optional* checks whether `U` can bind to some `const optional<X>&`, that is, whether `U` is a specialization of `optional` or publicly derived from some `optional`. It excludes a wider range: a type derived from `optional` can be implicitly converted to `const optional<X>&` and should be handled by the optional-with-optional version; otherwise checking `three_way_comparable_with<T, U>` would consider this template itself again, and the constraint would depend on itself. The effect of ¶25 is `x.has_value() ? *x <=> v : strong_ordering::less`.

## swap and make_optional ([optional.specalg])

¶1–¶2 The non-member `swap(x, y)` calls `x.swap(y)`, with the same exception specification. The constraint is `is_reference_v<T> || (is_move_constructible_v<T> && is_swappable_v<T>)`; the first branch is for `optional<T&>`: swapping two `optional<T&>`s only swaps the internal pointers and does not require `T` to be swappable.

`make_optional` has three overloads:

- ¶4 `make_optional(v)` returns `optional<decay_t<T>>(std::forward<T>(v))`;
- ¶5 `make_optional<T>(args...)` returns `optional<T>(in_place, args...)`;
- ¶6 `make_optional<T>(il, args...)` returns `optional<T>(in_place, il, args...)`.

¶3 {{c++26}} The first overload has a special constraint: the call does not use an explicit template argument list that begins with a type template argument. In other words, once you write `make_optional<X>(...)`, the first overload is never selected.

```cpp run title="make_optional.cpp" ok
#include <optional>
#include <type_traits>

int main() {
  int x = 0;
  auto a = std::make_optional(x);          // deduced: optional<int>
  auto b = std::make_optional<int&>(x);    // explicit argument: skips the first overload
  static_assert(std::is_same_v<decltype(a), std::optional<int>>);
  static_assert(std::is_same_v<decltype(b), std::optional<int&>>);
}
```

Without this constraint, `make_optional<int&>(x)` could select the first overload with `T = int&`, but its return type `optional<decay_t<int&>>` is `optional<int>`: you explicitly wrote `int&` and got a copy. Once C++26 has `optional<T&>`, this silent decay is unacceptable.

With C++17's CTAD, `make_optional` is not really needed anymore: `std::optional o = x;` and `std::optional<T>(std::in_place, args...)` are more direct.

## hash ([optional.hash])

¶1 `hash<optional<T>>` is enabled if and only if `hash<remove_const_t<T>>` is enabled (see [[unord.hash]] for what enabled means). For an `o` with a value, `hash<optional<T>>()(o)` must equal `hash<remove_const_t<T>>()(*o)`, so the hashes of non-empty elements in an `unordered_set<optional<int>>` match those of `unordered_set<int>`. For an empty `o`, the result is an unspecified value; libc++ returns 0. The member functions are not guaranteed to be `noexcept`.

!!! lawyer "hash<optional<int&>>"
    For `T = int&`, `remove_const_t<T>` is just `int&`, and `hash<int&>` is not an enabled specialization. Read literally, `hash<optional<int&>>` is disabled; when C++26 added `optional<T&>`, hashing support was not added for it. libc++ 23 agrees: `std::hash<std::optional<int&>>` is not default-constructible. Do not assume `unordered_set<optional<T&>>` works.

## bad_optional_access ([optional.bad.access])

```cpp
class bad_optional_access : public exception {
public:
  constexpr const char* what() const noexcept override;
};
```

¶1 This is the type of the exception thrown when `value()` is called on an empty `optional`. ¶2 `what()` returns an implementation-defined string; during constant evaluation, the string is encoded as an ordinary literal. It is `constexpr` because C++26 allows throwing and catching exceptions during constant evaluation.

It derives directly from `std::exception`, not from `std::logic_error`, so `catch (const std::logic_error&)` does not catch it.

## Header synopsis ([optional.syn])

The synopsis of `<optional>` is marked mostly freestanding: in a **freestanding implementation** (an implementation that does not depend on an operating system; see [[g:freestanding-implementation|freestanding implementation]]), most of it must also be provided. `optional` and `optional<T&>` are partially freestanding classes: `value()`, which throws `bad_optional_access`, is deleted in a freestanding implementation, and only non-throwing interfaces such as `operator*` and `value_or` can be used ([[P2407]]).

Also worth noting in the synopsis are three variable template specializations {{c++26}}:

- `ranges::enable_view<optional<T>>` is `true`: `optional` is a view containing at most one element and can be used in a range-based `for` (see the iterators in [[optional.optional]]);
- `format_kind<optional<T>>` is `range_format::disabled`: although `optional` is a range, `std::format` does not format it as a range; otherwise `optional<int>{1}` would be printed as `[1]` ([[P3168]]);
- `ranges::enable_borrowed_range<optional<T&>>` is `true`: the iterators of `optional<T&>` point to an external object and do not dangle after the `optional<T&>` itself is destroyed.

The deduction guide `optional(T) -> optional<T>` is in [[optional.optional]]. It deduces by value, so `std::optional o = 1;` is `optional<int>` and `std::optional s = "abc";` is `optional<const char*>`.

!!! history
    `optional` comes from Boost.Optional; it went into the Library Fundamentals TS first and then into C++17 with [[P0220R1]]. Early proposals included `optional<T&>`, which was removed because of disagreement over whether assigning to it should rebind or write through; it was only added back by [[P2988]] in C++26 ([[optional.optional.ref]]). C++20 greatly simplified the comparison operators with `<=>` and rewritten candidates. C++23 added `and_then`, `transform` and `or_else` ([[P0798]]). C++26 added range support ([[P3168]]), `optional<T&>`, partial freestanding support ([[P2407]]) and the explicit-argument constraint on `make_optional`.

## Common misconceptions

!!! pitfall "== false and ! on optional<bool>"
    With `std::optional<bool> b = false;`, `b == false` compares the value and is `true`; `!b` checks whether there is a value and is `false`. Likewise, `opt == nullptr` and `!opt` on `optional<T*>` are two different things.

!!! pitfall "bad_optional_access is a logic_error"
    It derives directly from `std::exception`. Catching `logic_error` misses it.

## Questions

!!! question "Question 1"
    With `std::optional<double> a = NAN, b = NAN;`, why do `a <= b` and `!(b < a)` give different results? Why does the standard not define the former in terms of the latter?

<details markdown="1">
<summary>Answer</summary>

Both have values, so by [optional.relops] ¶14, `a <= b` is `*a <= *b`, and any comparison involving NaN is `false`; `!(b < a)` is `!false`, which is `true`.

The standard forwards each operator to the operator of the same name on `T` precisely so as not to impose a total-order assumption on `T`. Comparison of `optional<T>` is an extension of comparison of `T`, and when both sides have values it behaves exactly like `T`.
</details>

!!! question "Question 2"
    In `std::optional<int> o = 5; o = {};`, why is `operator=(U&&)` not selected? What would happen if it were?

<details markdown="1">
<summary>Answer</summary>

The template parameter of `operator=(U&&)` has the default argument `U = remove_cv_t<T>`; a braced list cannot deduce `U`, so it takes the default `int`. In [[optional.optional]], its constraints say that it does not participate in overload resolution when `T` is a scalar type and `decay_t<U>` is `T` ([optional.assign] ¶14.2), which excludes exactly this case.

If it were selected, `{}` would value-initialize an `int` 0, and `o` would hold the value 0 instead of being emptied. The same spelling would then behave differently for `optional<int>` and `optional<std::string>`; this constraint guarantees that `o = {}` always empties.
</details>
