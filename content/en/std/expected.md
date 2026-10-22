---
title: Expected objects
summary: "expected<T, E> represents either a result or an error. This page covers its design trade-offs, the error wrapper unexpected<E>, the unexpect tag, and bad_expected_access, which is thrown when access fails."
updated: 2026-10-19
---

!!! tldr
    - `std::expected<T, E>` {{c++23}} holds either a result of type `T` or an error of type `E`, with no third state; the interface favors the `T` side.
    - To return an error you must write `std::unexpected(e)` or use the `unexpect` tag; a value of type `E` never implicitly becomes an error, so there is no confusion even when `T` and `E` are the same type.
    - The `E` of `unexpected<E>` must be an object type, and cannot be an array, cv-qualified, or itself a specialization of `unexpected`.
    - `value()` throws `bad_expected_access<E>` when there is no value, and the exception object carries the error value; all such exceptions can be caught by a reference to `bad_expected_access<void>`.

For the members of the primary template, see [[expected.expected]]; for the partial specialization when `T` is `void`, see [[expected.void]].

## A result or an error

```cpp run title="parse.cpp" ok
#include <cassert>
#include <charconv>
#include <expected>
#include <string_view>
#include <system_error>

std::expected<int, std::errc> parse(std::string_view s) {
  int v{};
  auto [p, ec] = std::from_chars(s.data(), s.data() + s.size(), v);
  if (ec != std::errc{}) return std::unexpected(ec);
  if (p != s.data() + s.size())
    return std::unexpected(std::errc::invalid_argument);
  return v;
}

int main() {
  auto ok = parse("42");
  assert(ok && *ok == 42);

  auto bad = parse("4x");
  assert(!bad && bad.error() == std::errc::invalid_argument);
  assert(bad == std::unexpected(std::errc::invalid_argument));

  try {
    (void)bad.value();
  } catch (const std::bad_expected_access<std::errc>& e) {
    assert(e.error() == std::errc::invalid_argument);
  }
}
```

¶1 [expected.general] has a single sentence of definition: an `expected<T, E>` object holds an object of type `T` or an object of type `E` and manages the lifetime of the contained object.

It can be seen as a generalization of `optional<T>` ([[optional]]): `optional` can only say there is no value, while `expected` can also say why there is no value. Unlike `optional`, `expected` always contains an object, either a value or an error; there is no empty state.

What distinguishes it from `variant<T, E>` is the asymmetry. `T` is the expected side and `E` the unexpected side, and the interface favors `T`: `*e`, `e->` and `e.value()` access the value, `if (e)` checks for success, and accessing the error requires writing `e.error()` explicitly.

### When to use expected

C++ has traditionally had two ways of handling anticipated failures (parse errors, missing files, network timeouts):

| | exceptions | error codes | `expected<T, E>` |
|---|---|---|---|
| Failure information | any type | usually just an integer or enumeration | any type `E` |
| Successful value | returned normally | via an output parameter, or squeezed into one return value with the error code | returned normally |
| Can it be ignored? | propagates if not handled | easily ignored | taking the value without checking makes `value()` throw |
| Control flow | invisible; any call may jump out | explicit | explicit, and can be chained with monadic operations |
| Does the signature show it can fail? | no | partly | yes, `E` is in the return type |
| With exceptions disabled | unavailable | available | available except for `value()` |

`expected` suits situations where failure is itself a normal outcome and the caller usually handles it on the spot: parsing, validation, lookup, I/O. Errors that should not happen and cannot be recovered from locally when they do (broken invariants, memory exhaustion) are better served by exceptions or contract assertions. Common choices for `E` are `std::errc` or `std::error_code` ([[syserr]]), a custom enumeration, or a struct carrying context.

### Why errors are wrapped

`return v;` constructs a value, and `return std::unexpected(ec);` constructs an error. Why not let `E` implicitly convert to `expected`? Because `T` and `E` may be the same type, or convertible to each other: in `expected<int, int> f() { return 0; }`, is `0` a result or an error code? The `unexpected` wrapper makes the intent part of the type.

The other way is to pass a tag at construction. [expected.syn] defines:

```cpp
struct unexpect_t { explicit unexpect_t() = default; };
inline constexpr unexpect_t unexpect{};
```

`expected<T, E>(std::unexpect, args...)` constructs the error in place from `args...`, just as `std::in_place` is used to construct the value in place. The default constructor is `explicit`, the usual pattern for standard library tag types (`in_place_t` and `allocator_arg_t` are the same): `{}` cannot be copy-list-initialized into an `unexpect_t`, so `e = {}` and `f({})` do not accidentally match overloads that take an `unexpect_t` parameter.

The synopsis also declares the primary template and a partial specialization `template<class T, class E> requires is_void_v<T> class expected<T, E>;`. A single constrained partial specialization covers all four cases: `void`, `const void`, `volatile void` and `const volatile void`.

## unexpected: the error value wrapper ([expected.unexpected])

### Which types can be E

```cpp run title="bad_unexpected.cpp" error
#include <expected>
auto a = sizeof(std::unexpected<const int>);  // error: cv-qualified
auto b = sizeof(std::unexpected<int[2]>);     // error: array
auto c = sizeof(std::unexpected<std::unexpected<int>>);  // error
auto d = sizeof(std::unexpected<int&>);       // error: not an object type
int main() {}
```

¶2 [expected.un.general] specifies that a program that instantiates the definition of `unexpected` with a non-object type, an array type, a specialization of `unexpected`, or a cv-qualified type is ill-formed. A type meeting these conditions is called a valid template argument for `unexpected` ([[g:valid-unexpected-argument]]), and the requirements on `E` in [[expected.expected]] refer directly to this notion. The reasons, one by one:

- Non-object types (references, functions, `void`): `unexpected` stores the error by value; `expected<T, E&>` is not supported, and the error side is always held by value.
- Arrays: they can be neither copy-initialized nor assigned.
- Specializations of `unexpected`: `unexpected<unexpected<E>>` is meaningless, and would also make deduction in constructors like `expected(const unexpected<G>&)` ambiguous. Only by forbidding nesting does the convention "`unexpected<X>` is the error value `X`" always hold.
- cv-qualification: `unexpected<const E>` would have a const member, so its copy assignment would be deleted, which in turn would make `expected`'s assignment unusable too. Besides, the deduction guide `unexpected(E) -> unexpected<E>` deduces by value and could never deduce a cv-qualified type anyway.

The wording says ill-formed only when the definition is instantiated. Merely writing `unexpected<const int>` (for example as the return type in a function declaration) is not an error; it is reported only where a complete type is needed (defining a variable, `sizeof`). libc++ implements this with `static_assert` in the class body, which fires exactly when the class template's definition is instantiated.

### Construction

`unexpected` has no default constructor: an error must have content. The copy and move constructors and assignments are all `= default`. The other three constructors are all `explicit`:

- ¶1 [expected.un.cons] `template<class Err = E> explicit unexpected(Err&& e)`: constrained on `Err`, with cv and references removed, being neither `unexpected` nor `in_place_t`, and on `is_constructible_v<E, Err>`. The default template argument `Err = E` makes braced arguments usable, for example `unexpected<std::string>({'a', 'b'})`.
- ¶4 `explicit unexpected(in_place_t, Args&&...)` and the version with an `initializer_list` (paragraph 7): construct the error value in place.

`explicit` is intentional: a value of type `E` becomes an error only when you write `std::unexpected(...)`. The deduction guide makes `std::unexpected(ec)` deduce `unexpected<std::errc>`. `std::unexpected("oops")` deduces `unexpected<const char*>`, which is then turned into the real `E` by `expected`'s converting constructor that accepts `unexpected<G>`:

```cpp run title="unexpected-convert.cpp" ok
#include <cassert>
#include <expected>
#include <string>

std::expected<int, std::string> f() {
  return std::unexpected("oops");  // unexpected<const char*>
}

int main() {
  assert(f().error() == "oops");  // converted to std::string
}
```

### Access, swap and comparison

¶1 [expected.un.obs] `error()` has four overloads, `const&`, `&`, `const&&` and `&&`, returning the stored error value; the rvalue versions return the result of `std::move`. All are `noexcept`.

¶1 [expected.un.swap] The member `swap` requires (*Mandates*) `is_swappable_v<E>`, and its effect is `using std::swap; swap(unex, other.unex);`, which can find `E`'s own `swap` via ADL. The friend `swap(x, y)` in paragraph 3 is written with the constraint (*Constraints*) `is_swappable_v<E>`.

The difference is intentional. The friend `swap` enters, via ADL, the candidate set of any unqualified `swap` call on `unexpected<E>`, including the detection inside `is_swappable`, so it must drop out of overload resolution when the condition is not met; otherwise `is_swappable_v<unexpected<X>>` would give the wrong answer (see Question 1). A member function is only instantiated when called explicitly, so reporting an error directly with *Mandates* is fine.

¶1 [expected.un.eq] `operator==` is a hidden friend template `template<class E2> friend constexpr bool operator==(const unexpected&, const unexpected<E2>&)` returning `x.error() == y.error()`. The requirement that `x.error() == y.error()` be well-formed and convertible to `bool` is *Mandates*, not a constraint. So for a non-comparable `X`, `std::equality_comparable<unexpected<X>>` is still true (the declaration is always viable), and the error appears only on an actual call. Keep this in mind when detecting with concepts.

## bad_expected_access ([expected.bad], [expected.bad.void])

```cpp
template<class E>
class bad_expected_access : public bad_expected_access<void> {
public:
  constexpr explicit bad_expected_access(E);
  constexpr const char* what() const noexcept override;
  constexpr E& error() & noexcept;  // plus three other cvref overloads
private:
  E unex;  // exposition only
};
```

¶1 This is the exception thrown when `value()` is called on an `expected<T, E>` with no value. Unlike `bad_optional_access`, it carries the error value: ¶2 the constructor takes `E` by value and moves it in, and `error()` gets it back. An outer `catch` can obtain the specific reason for the failure.

Carrying `E` also brings a restriction. A thrown exception object must be copyable ([[except.throw]]), and `value()` constructs the exception from a copy of the error value made with `as_const(error())`, so the *Mandates* of `value()` requires `is_copy_constructible_v<E>` ([[expected.expected]]). A move-only error type can be put into an `expected`, but `value()` cannot be called.

[expected.bad.void] provides the common base class:

```cpp
template<>
class bad_expected_access<void> : public exception {
protected:
  constexpr bad_expected_access() noexcept;
  constexpr bad_expected_access(const bad_expected_access&) noexcept;
  // the move constructor and both assignment operators are protected too
  constexpr ~bad_expected_access();
public:
  constexpr const char* what() const noexcept override;
};
```

With it, all such exceptions can be caught without caring about `E`: `catch (const std::bad_expected_access<void>& e)`. Its special members are all `protected`, so you can neither create an object of it on its own nor slice-copy a derived object into it; it exists only as a base class:

```cpp run title="catch-by-value.cpp" error
#include <expected>

void f() {
  try {
  } catch (std::bad_expected_access<void> e) {  // error: constructor and destructor are protected
  }
}
int main() {}
```

The `what()` of both classes returns an implementation-defined NTBS, and all members are `constexpr`. C++26 allows exceptions to be thrown and caught during constant evaluation, so `bad_expected_access` can also be thrown and handled during constant evaluation.

## Compared with optional and variant

| | `optional<T>` | `expected<T, E>` | `variant<T, E>` |
|---|---|---|---|
| States | value or no value | value or error | one of several alternatives |
| Can it hold nothing? | yes, a normal state | no | only after an exception (valueless) |
| Throws on failed access | `bad_optional_access` | `bad_expected_access<E>`, carrying the error | `bad_variant_access` |
| Symmetry | not applicable | favors `T` | all alternatives equal |
| Monadic operations | `and_then`, `transform`, `or_else` | plus `transform_error` | none; use `visit` |
| Spelling for "no value" | not applicable | `expected<void, E>` | `variant<monostate, E>` |

!!! history
    The `expected` proposal went through more than a dozen revisions before entering C++23 as [[P0323R12]]. The issues debated along the way included whether the error side should have a default type and whether implicit construction from `E` should be allowed; the final decision was that errors must be expressed explicitly via `unexpected`. [[P2505R5]], also in C++23, added the monadic operations `and_then`, `or_else`, `transform` and `transform_error`, and `__cpp_lib_expected` was raised to `202211L` accordingly, which is the value libc++ 23 reports in our tests. The current draft also adds `has_error()` to `expected`, which libc++ 23 does not provide yet.

## Questions

!!! question "Question 1"
    Let `X` be neither swappable nor movable. If `unexpected`'s friend `swap` were changed to *Mandates*, what would `std::is_swappable_v<std::unexpected<X>>` give?

<details markdown="1">
<summary>Answer</summary>

It would wrongly give `true`. `is_swappable` detects whether `swap(declval<T&>(), declval<T&>())` is well-formed after `using std::swap;`. ADL finds `unexpected`'s friend `swap`; if it had only *Mandates*, the declaration would always be viable, and since the detection only looks at declarations, it would report `true`, with the error appearing only on an actual call.

With *Constraints*, the friend whose condition is not met drops out of overload resolution, leaving only `std::swap`. That requires `unexpected<X>` to be move-constructible and move-assignable, and those members are `= default`, so they are deleted when `X` is not movable, and `std::swap` is not viable either; the result is the correct `false`. In our tests on libc++ 23, when `X` has a deleted move constructor, `std::is_swappable_v<std::unexpected<X>>` is indeed `false`.
</details>

!!! question "Question 2"
    Why is the copy constructor of `bad_expected_access<void>` `protected` rather than `public`?

<details markdown="1">
<summary>Answer</summary>

If it were `public`, catching by value as in `catch (std::bad_expected_access<void> e)` would slice-copy the derived object into a base object and lose the error value, and this spelling looks perfectly reasonable, so the problem would be hard to notice. `protected` turns catching by value into a compile error, forcing you to catch by reference. The copy constructor of the derived class `bad_expected_access<E>` can still call the base's protected copy constructor, so throwing, `exception_ptr` and other situations that need to copy the exception object are unaffected.
</details>

## Summary

| Topic | Rule |
|---|---|
| `expected<T, E>` | holds one of `T` or `E`; no empty state |
| Constructing an error | via `unexpected<E>` or the `unexpect` tag; `E` never implicitly becomes an error |
| `unexpect_t` | its default constructor is `explicit`, so `{}` does not match it |
| `E` of `unexpected<E>` | an object type that is not an array, not cv-qualified, and not a specialization of `unexpected`; checked when the definition is instantiated |
| Construction of `unexpected` | all `explicit`; deduction guide `unexpected(E) -> unexpected<E>` |
| `swap` | the member uses *Mandates*; the friend uses *Constraints* |
| `operator==` | *Mandates*: the `error()`s are comparable |
| `bad_expected_access<E>` | carries the error value; so `value()` requires `E` to be copy-constructible |
| `bad_expected_access<void>` | the common base; all special members `protected`, preventing slicing |

<details class="fine" markdown="1"><summary>Remaining wording</summary>

[expected.syn]: the header synopsis is marked mostly freestanding. The `expected` primary template and the `void` partial specialization are marked partially freestanding; the throwing `value()` is deleted in a freestanding implementation.

[expected.un.general]/1 only says that the class template `unexpected` described in this subclause represents an unexpected value stored in an `expected` object.

The *Throws* elements of the constructors in [expected.un.cons] (¶3, ¶6, ¶9) only say that any exception thrown by the initialization of the error value is thrown.

[expected.bad]/3–4 are the return values of the four `error()` overloads; paragraph 5 and [expected.bad.void]/1 specify that `what()` returns an implementation-defined NTBS, encoded as an ordinary literal during constant evaluation ([[lex.ccon]]).

</details>
