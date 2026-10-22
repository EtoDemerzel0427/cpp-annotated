---
title: Class template expected
summary: "The expected<T, E> primary template: how it stores a value or an error, how the constructors tell the two apart, why assignment that switches between value and error can give the strong exception guarantee, and the rules for observers, monadic operations and equality comparison."
updated: 2026-10-19
---

!!! tldr
    - `expected<T, E>` always contains exactly one `T` or one `E`, with no empty state; default construction gives a value-initialized `T`, that is, success.
    - Anything wrapped in `unexpected<X>` is always treated as an error; anything else that can construct `T` is treated as a value.
    - Assignment that switches between value and error gives the strong exception guarantee. To make this possible, the assignment operators are defined as deleted if the move constructors of both `T` and `E` may throw, and `emplace` only accepts non-throwing construction.
    - `*e`, `e->` and `e.error()` are UB when the state is wrong (terminating in a hardened implementation), while `value()` throws a `bad_expected_access<E>` carrying a copy of the error.
    - `and_then`, `or_else`, `transform` and `transform_error` change only one side and pass the other side through to the result unchanged; `and_then` cannot change the error type.

`std::expected<T, E>` {{c++23}} represents the result of a computation: either a value of type `T` or an error of type `E`. For the overview, `unexpected<E>` and `bad_expected_access`, see [[expected]]; for the partial specialization with `T` as `void`, see [[expected.void]].

Library clauses describe functions with a few fixed headings ([[structure.specifications]]). If *Constraints* are not satisfied, the function does not participate in overload resolution; if *Mandates* are not satisfied, the program is ill-formed; if *Hardened preconditions* are violated, a hardened implementation must terminate the program, and in other implementations it is UB.

## What is in the object [expected.object.general]

```cpp
template<class T, class E>
class expected {
public:
  using value_type = T;
  using error_type = E;
  using unexpected_type = unexpected<E>;
  template<class U> using rebind = expected<U, error_type>;
  // …
private:
  bool has_val;           // exposition only
  union {
    remove_cv_t<T> val;   // exposition only
    E unex;               // exposition only
  };
};
```

¶1 An `expected<T, E>` object contains a value of type `T` or a value of type `E`, nested within the expected object ([[intro.object]]), with no separate allocation. The member *has_val* records which one it currently is. The standard describes the storage as a union, meaning the two share the same memory and only one of them is the active member at any time ([[class.union]]).

`rebind<U>` gives an expected with the same error type and the value type replaced by `U`, which makes it easier for generic code to write the return types of monadic operations.

### Which types can be used (¶2–3)

¶2 `T` is a **valid value type for expected** ([[g:valid-value-type-for-expected]]) if `remove_cv_t<T>` is `void`, or a complete non-array object type that is not `in_place_t`, `unexpect_t` or a specialization of `unexpected`. Instantiating `expected` with an invalid `T` is ill-formed. `E` must be a valid template argument for `unexpected` (see [[expected]]), that is, a non-array, non-cv-qualified object type that is not a specialization of `unexpected`.

<div class="compare" markdown="1">

```cpp run ok
#include <expected>
std::expected<const int, int> a;
std::expected<void, int> b;
int main() {}
```

```cpp run error
#include <expected>
std::expected<int&, int> c;
// error: a reference is not an object type
std::expected<int, const int> d;
// error: E cannot be cv-qualified
```

</div>

The value side may be cv-qualified; the error side may not. C++26's `optional<T&>` has a reference specialization; `expected` does not. The value type cannot be `unexpected<X>`; otherwise, when `expected<unexpected<int>, int>` is constructed from `unexpected(1)`, there would be no telling whether that is a value or an error.

¶3 `T` (when not `void`) and `E` must both meet *Cpp17Destructible*.

## Construction: value or error [expected.object.cons]

```cpp run ok
#include <cassert>
#include <expected>
#include <optional>
#include <string>

std::expected<int, std::string> parse(bool good) {
  if (good) return 42;                       // value
  return std::unexpected("bad input");       // error
}

int main() {
  std::optional<int> o;                // empty
  std::expected<int, std::string> e;   // has a value, *e == 0
  assert(!o && e && *e == 0);
  assert(parse(true) == 42);
  assert(parse(false).error() == "bad input");
}
```

### Default construction gives success (¶2–5)

¶2–¶4 The default constructor requires `T` to be default-constructible; it value-initializes *val*, and afterwards `has_value()` is true. This is the opposite of `optional`: `optional` defaults to empty, while `expected` has no empty state and can only default to success. Keep this in mind when rewriting `optional` code into `expected`.

### Constructing from a value (¶23–26)

```cpp
template<class U = remove_cv_t<T>>
  constexpr explicit(!is_convertible_v<U, T>) expected(U&& v);
```

¶23 This constructor accepts any argument that can construct `T`, but excludes the following `remove_cvref_t<U>`: `in_place_t`, `expected` itself, `unexpect_t`, and any specialization of `unexpected`. The last one (¶23.4) is the key to telling values from errors: an `unexpected<X>` is never treated as a value.

¶23.6 handles the case where `T` is `bool`. A `bool` can be direct-initialized from another `expected` through `explicit operator bool`; without the exclusion, `expected<bool, E> b(other)` might take the truthiness of `other` as the new value. `optional` has the same provision ([[optional.optional]]).

¶24 The effect is to direct-non-list-initialize *val* with `std::forward<U>(v)`. The constructor is non-explicit only when `U` is implicitly convertible to `T`, which is why `return 42;` can be written in a function returning `expected<int, E>`.

### Constructing an error from `unexpected<G>` (¶27–31)

```cpp
template<class G> constexpr explicit(!is_convertible_v<const G&, E>)
  expected(const unexpected<G>& e);
template<class G> constexpr explicit(!is_convertible_v<G, E>)
  expected(unexpected<G>&& e);
```

¶28–¶29 As long as `E` can be constructed from `G`, *unex* is direct-non-list-initialized with `e.error()`. In the example above, `std::unexpected("bad input")` has type `unexpected<const char*>`, and `const char*` converts implicitly to `std::string`, so the constructor is not explicit and can be used in a `return` directly.

### In-place construction (¶32–47)

`expected(in_place_t, args...)` constructs the value directly in *val*, and `expected(unexpect_t, args...)` constructs the error directly in *unex*; each has a version taking an `initializer_list`. They are all explicit, constrained on the corresponding `is_constructible_v`.

### Copy, move and converting construction (¶6–22)

¶6–¶16 Copy and move construction construct *val* or *unex* according to the state of `rhs`. If either `T` or `E` is not copy-constructible, the copy constructor is defined as deleted (¶9); if both are trivially copy-constructible, it is trivial (¶10). The noexcept of the move constructor is equivalent to both being nothrow move-constructible (¶15); if both are trivially move-constructible, it is trivial (¶16).

¶17–¶22 When converting from `expected<U, G>`, the value is constructed from `U` and the error from `G`. The constructor is non-explicit only when both sides convert implicitly (¶22).

Two groups of the constraints in ¶18 are there to avoid ambiguity. ¶18.3 borrows *converts-from-any-cvref* defined in [[optional.optional]]: if `T` can be constructed from the whole `expected<U, G>` (when `T` is not `bool`), member-wise conversion is not done, and ¶23 takes it as a value in its entirety. ¶18.4–¶18.7 are the same kind of check on the error side: if `unexpected<E>` can be constructed from the whole `expected<U, G>`, this converting constructor likewise steps aside.

## Destruction and triviality [expected.object.dtor]

¶1 The destructor destroys whichever of *val* and *unex* is active. ¶2 When `T` and `E` are both trivially destructible, the destructor is trivial.

The triviality conditions of the special members are summarized below; both `T` and `E` must meet them:

| Special member | Trivial when | Source |
|---|---|---|
| copy constructor | trivially copy-constructible | [expected.object.cons] ¶10 |
| move constructor | trivially move-constructible | [expected.object.cons] ¶16 |
| destructor | trivially destructible | [expected.object.dtor] ¶2 |
| copy assignment | trivially copy-constructible, copy-assignable and destructible | [expected.object.assign] ¶5 |
| move assignment | trivially move-constructible, move-assignable and destructible | [expected.object.assign] ¶10 |

Per [[class.prop]], this means types such as `expected<int, int>` and `expected<double, std::errc>` should be trivially copyable and can be copied with `memcpy`.

!!! impl "libc++'s assignment is not trivial yet"
    libc++ implements conditional triviality with C++20's constrained special members ([[P0848]]): the same special member is declared several times, an unconstrained `= delete`, a `= default` constrained on the trivial case, and a user-provided version constrained on the non-trivial case.

    But as of the libc++ that ships with Clang 23, copy assignment and move assignment have only two versions, deleted and user-provided. In our tests, `expected<int, int>` is trivially copy-constructible and trivially destructible but not trivially copy-assignable, so `std::is_trivially_copyable_v<std::expected<int, int>>` is false. The requirements of [expected.object.assign] ¶5 and ¶10 in the draft are not implemented yet.

## Assignment: never empty [expected.object.assign]

### The strong exception guarantee when switching

```cpp run ok
#include <cassert>
#include <expected>
#include <stdexcept>

struct Fragile {
  int v;
  Fragile(int n) : v(n) {
    if (n < 0) throw std::invalid_argument("neg");
  }
};

int main() {
  std::expected<Fragile, int> e =
      std::unexpected(7);
  try {
    e = -1;   // throws while constructing Fragile(-1)
  } catch (const std::invalid_argument&) {}
  assert(!e.has_value() && e.error() == 7);

  e = 5;
  assert(e && e->v == 5);
}
```

`e` originally contains the error 7, and the assignment has to replace it with a value. The value and the error share the same storage, so the old error must be destroyed before the new value can be constructed in its place. If the construction throws, the object would have neither a value nor an error.

In this situation `optional` can fall back to the empty state and `variant` enters the `valueless_by_exception` state ([[variant.variant]]); `expected` has neither. The program above still holds the original error 7 after the exception: this is the strong exception guarantee, under which an assignment either succeeds or leaves the object as it was.

### *reinit-expected* (¶1)

¶1 The standard describes this switch with an exposition-only function template [[g:reinit-expected]]. `newval` is the member to be constructed and `oldval` the currently active member:

```cpp
template<class T, class U, class... Args>
constexpr void reinit-expected(T& newval, U& oldval, Args&&... args) {  // exposition only
  if constexpr (is_nothrow_constructible_v<T, Args...>) {
    destroy_at(addressof(oldval));
    construct_at(addressof(newval), std::forward<Args>(args)...);
  } else if constexpr (is_nothrow_move_constructible_v<T>) {
    T tmp(std::forward<Args>(args)...);
    destroy_at(addressof(oldval));
    construct_at(addressof(newval), std::move(tmp));
  } else {
    U tmp(std::move(oldval));
    destroy_at(addressof(oldval));
    try {
      construct_at(addressof(newval), std::forward<Args>(args)...);
    } catch (...) {
      construct_at(addressof(oldval), std::move(tmp));
      throw;
    }
  }
}
```

The three branches use different means to ensure that no exception can occur after the old object has been destroyed:

1. The new object can be constructed from the arguments without throwing: destroy the old object directly, then construct the new one.
2. The new object's type can be move-constructed without throwing: first construct the new object in a local variable. This step may throw, but the old object is still intact at that point. Then destroy the old object and move the local variable in, which does not throw. `Fragile` above takes this branch.
3. Neither: first move the old object into a local variable as a backup, destroy it, then try to construct the new object. If that throws, move the backup back into place and rethrow. This requires the old object's type to be move-constructible without throwing; otherwise the restoration could fail too.

The precondition of branch 3 is guaranteed by the deletion condition of the assignment operators:

!!! std
    This operator is defined as deleted unless: … `is_nothrow_move_constructible_v<T> || is_nothrow_move_constructible_v<E>` is `true`.

This is ¶4.5 for copy assignment, and ¶6.5 for move assignment has the same constraint. As long as one of `T` and `E` can be move-constructed without throwing, switching in both directions has a safe branch to take (Question 1 gives the reasoning). When both may throw, assignment is unavailable at compile time:

```cpp run ok
#include <expected>
#include <type_traits>

struct Throwy {             // move constructor may throw
  Throwy() = default;
  Throwy(const Throwy&) {}
  Throwy(Throwy&&) noexcept(false) {}
  Throwy& operator=(const Throwy&) = default;
  Throwy& operator=(Throwy&&) = default;
};

using A = std::expected<Throwy, int>;
using B = std::expected<Throwy, Throwy>;
static_assert(std::is_copy_assignable_v<A>);
static_assert(!std::is_copy_assignable_v<B>);
static_assert(!std::is_move_assignable_v<B>);
static_assert(std::is_copy_constructible_v<B>);  // construction is unaffected
int main() {}
```

In the same situation `variant` allows assignment and becomes valueless on failure; `expected` chooses to reject it at compile time, to maintain that there is always a value or an error.

### Copy assignment and move assignment (¶2–10)

¶2 Copy assignment has four cases:

- ¶2.1 both have values: `val = *rhs`, with the exception guarantee depending on `T`'s assignment;
- ¶2.2 this has a value and `rhs` is an error: *reinit-expected*`(unex, val, rhs.error())`;
- ¶2.3 this is an error and `rhs` has a value: *reinit-expected*`(val, unex, *rhs)`;
- ¶2.4 both are errors: `unex = rhs.error()`.

Finally, only if no exception was thrown, `has_val = rhs.has_value()` is executed. Because the flag is updated last, it still describes the original state if an exception occurs.

¶4 Besides ¶4.5, copy assignment also requires `T` and `E` to be both copy-assignable and copy-constructible, otherwise it is defined as deleted. ¶6–¶7 Move assignment works the same way, with the conditions written as *Constraints*. ¶9 The noexcept of move assignment is equivalent to both `T` and `E` being nothrow move-assignable and nothrow move-constructible.

### Assigning from a value or `unexpected` (¶11–17)

¶11 The constraints of `operator=(U&& v)` are similar to those of the constructor in ¶23: `U` is neither `expected` itself nor a specialization of `unexpected`, and `T` can be constructed and assigned from `U`. There is one more:

```cpp
is_nothrow_constructible_v<T, U> || is_nothrow_move_constructible_v<T> ||
is_nothrow_move_constructible_v<E>   // ¶11.5
```

The three terms are the preconditions of the three branches of *reinit-expected*; if any one is met, the switch has a safe path. ¶12 If there is currently a value, it does `val = std::forward<U>(v)` directly; otherwise it calls *reinit-expected*`(val, unex, …)` and then sets `has_val = true`.

¶14–¶17 `operator=(unexpected<G>)` is symmetric, with ¶15.3 replacing the first term by `is_nothrow_constructible_v<E, GF>`.

`expected` has no reset operation like `optional`'s. `e = {}` matches `operator=(U&&)` with `U` taking the default argument `remove_cv_t<T>`, so the result is that `e` contains a value-initialized `T`.

### `emplace` only accepts non-throwing construction (¶18–21)

```cpp
template<class... Args> constexpr T& emplace(Args&&... args) noexcept;
```

¶18–¶19 `emplace` requires `is_nothrow_constructible_v<T, Args...>`. It destroys the current value or error and then constructs the new value in place.

`optional::emplace` allows construction to throw, and the object becomes empty on failure. `expected::emplace` has nowhere to fall back to; and backing up first as *reinit-expected* does would defeat the point of in-place construction. So it only allows non-throwing construction; in other cases use assignment, `e = T(args...)`.

```cpp run error
#include <expected>
struct Fragile { Fragile(int); };   // construction may throw
int main() {
  std::expected<Fragile, int> e =
      std::unexpected(7);
  e.emplace(-1);  // error: not nothrow-constructible
}
```

## swap [expected.object.swap]

¶1 The member `swap` requires `T` and `E` to be swappable and move-constructible, with at least one of them nothrow move-constructible, for the same reason as assignment.

¶2 When both have values it swaps *val*; when both are errors it swaps *unex*. When one has a value and the other an error, the standard gives a piece of code in the same spirit as *reinit-expected*: if `E` can be moved without throwing, it first moves the other side's error into a local variable; otherwise it first moves its own value into a local variable. On error it restores from the backup and rethrows.

¶4 The noexcept is equivalent to `T` and `E` both being nothrow move-constructible and nothrow swappable.

## Reading the value and the error [expected.object.obs]

### Dereference and `error()` (¶1–8, ¶15–18)

The hardened precondition of `operator->` and `operator*` is that `has_value()` is true (¶1, ¶3, ¶5); the hardened precondition of `error()` is that `has_value()` is false (¶15, ¶17). Calling `error()` on an expected that contains a value reads an inactive member of the union, which is just as dangerous as dereferencing an error. In a hardened implementation these violations terminate the program; in other implementations they are {{ub}} ([[P3471]]).

¶7 `operator bool` and `has_value()` return *has_val*. ¶8 `has_error()` returns `!has_value()`. This member was added to the draft after C++23, and as of this writing the libc++ shipped with Clang 23 does not provide it yet.

### `value()` throws an exception carrying the error (¶9–14)

```cpp run ok
#include <expected>
#include <cstdio>
#include <string>

int main() {
  std::expected<int, std::string> e =
      std::unexpected("not found");
  try {
    std::printf("%d\n", e.value());
  } catch (const std::bad_expected_access<std::string>& x) {
    std::printf("error: %s\n", x.error().c_str());
  }
}
```

¶10–¶11 When there is a value, `value()` returns *val*; otherwise it throws `bad_expected_access(as_const(error()))`. The program above outputs `error: not found`.

¶9 The *Mandates* of the lvalue version requires `E` to be copy-constructible: the exception object holds a copy of `E`, a thrown exception object must be copy-constructible ([[except.throw]]), and the lvalue `value()` cannot move the error out of `*this`. ¶12–¶14 The rvalue version throws `bad_expected_access(std::move(error()))`, and in addition to copy-constructibility requires `E` to be constructible from `std::move(error())`.

So a move-only error type can be used with `expected`, but `value()` cannot be called:

```cpp run error
#include <expected>
#include <memory>
int main() {
  std::expected<int, std::unique_ptr<int>> e = 1;
  int a = *e;          // OK
  int b = e.value();   // error: E is not copyable (Mandates)
  (void)a; (void)b;
}
```

### `value_or` and `error_or` (¶19–26)

¶19–¶20 `value_or(v)` returns a copy of the value when there is one, otherwise `static_cast<T>(std::forward<U>(v))`. ¶23–¶24 `error_or(e)` is its mirror image: it returns a copy of the error when there is one, and `e` when there is a value. Both have their conditions as *Mandates*: the result type is copy-constructible (move-constructible for the rvalue versions), and the argument is implicitly convertible to the result type.

`error_or` is handy for turning an expected into a status code, for example `return r.error_or(std::errc{});`, which returns the "no error" value on success.

## Monadic operations [expected.object.monadic]

```cpp run ok
#include <cassert>
#include <expected>
#include <string>
#include <type_traits>

enum class Err { empty, too_big };

std::expected<int, Err> length(std::string s) {
  if (s.empty()) return std::unexpected(Err::empty);
  return static_cast<int>(s.size());
}
std::expected<int, Err> small(int n) {
  if (n > 3) return std::unexpected(Err::too_big);
  return n;
}

int main() {
  // and_then: f returns expected<_, Err>; transform: f returns a plain value
  auto r = length("ab").and_then(small)
                       .transform([](int n) { return n * 10; });
  assert(r == 20);

  auto e = length("abcdef").and_then(small);
  assert(e.error() == Err::too_big);

  // transform_error: change the error type
  std::expected<int, std::string> msg = e.transform_error([](Err x) {
    return std::string(x == Err::empty ? "empty" : "too big");
  });
  assert(msg.error() == "too big");

  // or_else: recover from the error
  auto ok = e.or_else([](Err) { return std::expected<int, Err>(0); });
  assert(ok == 0);

  // transform's f returns void, giving expected<void, Err>
  auto v = r.transform([](int) {});
  static_assert(std::is_same_v<decltype(v), std::expected<void, Err>>);

  assert(e.value_or(-1) == -1);
  assert(e.error_or(Err::empty) == Err::too_big);
  assert(r.error_or(Err::empty) == Err::empty);
}
```

[[P2505]] added four monadic operations, each with four overloads: `&`, `const &`, `&&` and `const &&`. Each operation hands one side to `f` and puts the other side into the result unchanged:

| Operation | `f` handles | Passed through | `f` returns | Result type |
|---|---|---|---|---|
| `and_then` | the value | the error | `expected<U, E>`; the error type must be `E` | the return type of `f` |
| `or_else` | the error | the value | `expected<T, G>`; the value type must be `T` | the return type of `f` |
| `transform` | the value | the error | any valid value type `U`, possibly `void` | `expected<U, E>` |
| `transform_error` | the error | the value | a valid argument `G` for `unexpected` | `expected<T, G>` |

The wording uses different headings for the requirements on the two sides. The side that is passed through is under *Constraints*: for example, ¶2 of `and_then` requires `E` to be constructible from `error()`. The requirements on the return value of `f` are under *Mandates*: for example, ¶3 requires the return type to be a specialization of `expected` whose error type is exactly `E`.

Why use *Constraints* for the passed-through side? Suppose `E` is move-only. Calling `and_then` on an lvalue `e`, the `&` overload would need to copy `error()` into the result, which is impossible. With *Constraints*, that overload drops out of overload resolution: `e.and_then(f)` reports that there is no matching function, while `std::move(e).and_then(f)` can select the `&&` overload and work normally.

A few details:

- `and_then` cannot change the error type, and `or_else` cannot change the value type. When you need to change them, convert first with `transform_error` or `transform`.
- ¶19–¶20 When `transform`'s `f` returns `void`, `f` is called first and then an `expected<void, E>` with a value is returned.
- ¶20.2, ¶28 `transform` and `transform_error` direct-non-list-initialize the member of the result with the result of calling `f`, without going through a temporary, so the result type need not be movable.

## Equality comparison [expected.object.eq]

All three comparison operators are hidden friends, with their conditions written as *Constraints*:

- ¶1–¶2 Comparison with another `expected<T2, E2>` (`T2` cannot be `void`): unequal if the states differ; values are compared when both have values, errors when both are errors.
- ¶3–¶4 Comparison with a value `v` (`T2` cannot be a specialization of `expected`): returns `*x == v` when there is a value, otherwise false.
- ¶5–¶6 Comparison with `unexpected<E2>`: compares the errors when it is an error, otherwise false.

There is no `<` or `<=>`: there is no natural order between success and failure. `!=` is obtained through C++20's rewriting rules ([[over.match.oper]]). `expected`'s comparisons use *Constraints*, while `unexpected`'s own `operator==` uses *Mandates* (see [[expected]]); the former can be detected in a `requires` expression.

## Common misconceptions

!!! pitfall "A default-constructed expected means not yet assigned"
    `std::expected<int, E> e;` contains the value 0. It represents success, not a placeholder state.

!!! pitfall "`e = {}` empties the expected"
    `expected` has no empty state. `e = {}` makes `e` contain a value-initialized `T`.

!!! pitfall "A move-only error type can be used with `value()` too"
    `value()` has to copy the error into the exception object, so calling it when `E` is not copy-constructible is ill-formed. Use `has_value()` with `*e` or `error()` instead.

## Questions

!!! question "Question 1"
    [expected.object.assign] ¶4.5 only requires one of `T` or `E` to be nothrow move-constructible, not both. Why is that enough? Consider switching from an error to a value and from a value to an error separately.

<details markdown="1">
<summary>Answer</summary>

Suppose `T` can be moved without throwing and `E` cannot.

Switching from an error to a value, the new object is a `T`. If `T` can be constructed from the arguments without throwing, branch 1 is taken; otherwise `T` can be moved without throwing, so branch 2 is taken. Both are safe.

Switching from a value to an error, the new object is an `E`. If `E` can be constructed from the arguments without throwing, branch 1 is taken; otherwise `E` cannot be moved without throwing, so only branch 3 is possible, and the backup is of the old object, a `T`. `T` can be moved without throwing, so the restoration cannot fail.

If instead `E` can and `T` cannot, the reasoning is symmetric. Only when neither can does some direction fall into branch 3 with a restoring move that may throw again, so only that one combination is excluded.
</details>

!!! question "Question 2"
    If `expected::emplace` allowed the construction to throw, how would its effect have to be described to keep "always a value or an error"? What would it cost?

<details markdown="1">
<summary>Answer</summary>

It would have to copy *reinit-expected*: either construct the new value in a local variable first and then move it in, or back up the old object first and restore it if construction fails. The former costs an extra move and is impossible for a non-movable `T`; the latter also costs an extra move and requires the old object's type to be nothrow movable. Either way, `emplace` would no longer be zero-overhead in-place construction. The standard therefore restricts `emplace` to non-throwing construction and leaves other cases to the assignment operators.
</details>
