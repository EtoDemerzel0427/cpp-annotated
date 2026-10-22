---
title: expected for void types
summary: "expected<void, E> represents only success or an error: how one constrained partial specialization covers every cv void, why its assignment needs no reinit-expected, and how operator*, value() and the monadic operations look when there is no value."
updated: 2026-10-19
---

!!! tldr
    - `expected<void, E>` is for operations that produce no result and can only fail; `return {};` means success.
    - It is a partial specialization with `requires is_void_v<T>`, covering all four types `void`, `const void` and so on at once.
    - There is no object on the value side, so nothing needs to be backed up when switching between success and error; assignment therefore does not require `E` to be nothrow movable.
    - `*e` and `e.value()` both return `void`: the former still has a hardened precondition and can serve as an assertion that there is a value; the latter throws `bad_expected_access<E>` on error.
    - The functions passed to `and_then` and `transform` take no arguments; `expected<void, E>` can only be compared with a `void` expected or with `unexpected`.

```cpp run ok
#include <cassert>
#include <expected>
#include <string>

std::expected<void, std::string> open_file(bool ok) {
  if (!ok) return std::unexpected("cannot open");
  return {};                        // success
}

int main() {
  // the f of and_then and transform takes no arguments
  auto r = open_file(true)
      .and_then([] { return std::expected<int, std::string>(42); })
      .transform([](int n) { return n + 1; });
  assert(r == 43);

  auto e = open_file(false);
  assert(!e && e.error() == "cannot open");

  try {
    e.value();                      // returns void, but throws
    assert(false);
  } catch (const std::bad_expected_access<std::string>& x) {
    assert(x.error() == "cannot open");
  }

  e.emplace();                      // discard the error, become success
  assert(e.has_value());
  *e;                               // OK: operator* returns void
}
```

Operations such as writing a file, sending a message or validating input have no result; they only need to say that they succeeded, or that they failed because of some `E`. The primary template cannot be used for `void`: it has a member of type `remove_cv_t<T>` and its `operator*` returns `T&`, none of which works for `void`. So [expected.void] gives a complete partial specialization. For the rules and terminology of the primary template (*Constraints*, *Mandates*, hardened preconditions, *reinit-expected*), see [[expected.expected]]; for the overview, see [[expected]].

## One partial specialization covers four voids [expected.void.general]

```cpp
template<class T, class E> requires is_void_v<T>
class expected<T, E> {
public:
  using value_type = T;
  using error_type = E;
  using unexpected_type = unexpected<E>;
  template<class U> using rebind = expected<U, error_type>;
  // …
private:
  bool has_val;       // exposition only
  union {
    E unex;           // exposition only
  };
};
```

The template argument list `<T, E>` of this partial specialization is the same as the primary template's; it is more specialized than the primary template by virtue of the constraint `is_void_v<T>` ([[temp.spec.partial]]). `is_void_v` is true for `void`, `const void`, `volatile void` and `const volatile void`, so one partial specialization covers all four cases instead of four separate ones. `value_type` keeps `T` as it is: `expected<const void, E>::value_type` is `const void`.

¶1 Where the primary template says the object contains a value of type `T`, this one says it represents a value of type `T`: there is no `void` object to hold, and success is just a state. The error is still an `E` nested within the object.

¶2 `E` must be a valid template argument for `unexpected` (see [[expected]]); otherwise instantiating the definition is ill-formed. ¶3 `E` must meet *Cpp17Destructible*.

In our tests with libc++, `sizeof(std::expected<void, int>)` equals `2 * sizeof(int)`: one `int`, one `bool` flag, plus padding.

## Construction and destruction [expected.void.cons]

The constructors are essentially the same as the primary template's; the differences all come from there being no object on the value side:

- ¶1 The default constructor is `noexcept` and represents success afterwards. So in a function returning `expected<void, E>`, `return {};` returns success.
- ¶2–¶11 Copy and move construction construct *unex* only when `rhs` is an error. Whether they are deleted, trivial or noexcept depends only on `E`.
- ¶12–¶16 When converting from `expected<U, G>`, ¶13.1 requires `U` to be `void` too, so conversion is only possible from another `void` expected. The other constraints are the same as the primary template's checks on the error side; whether it is explicit depends only on whether `G` converts implicitly to `E`.
- ¶17–¶21 Constructing an error from `unexpected<G>` is the same as in the primary template.
- ¶22 `expected(in_place_t)` takes no other arguments, is explicit and `noexcept`, and represents success afterwards.
- ¶23–¶30 `expected(unexpect_t, args...)` constructs the error in place.

[expected.void.dtor] The destructor destroys *unex* when the object is an error; when `E` is trivially destructible, the destructor is trivial.

## Assignment needs no *reinit-expected* [expected.void.assign]

<div class="compare" markdown="1">

```cpp run ok
#include <expected>
#include <type_traits>
struct Throwy {   // move constructor may throw
  Throwy() = default;
  Throwy(const Throwy&) {}
  Throwy(Throwy&&) noexcept(false) {}
  Throwy& operator=(const Throwy&)
    = default;
  Throwy& operator=(Throwy&&) = default;
};
static_assert(std::is_copy_assignable_v<
  std::expected<void, Throwy>>);
int main() {}
```

```cpp run ok
#include <expected>
#include <type_traits>
struct Throwy {   // same as on the left
  Throwy() = default;
  Throwy(const Throwy&) {}
  Throwy(Throwy&&) noexcept(false) {}
  Throwy& operator=(const Throwy&)
    = default;
  Throwy& operator=(Throwy&&) = default;
};
static_assert(!std::is_copy_assignable_v<
  std::expected<Throwy, Throwy>>);
int main() {}
```

</div>

The primary template forbids assignment when the move constructors of both `T` and `E` may throw; the `void` partial specialization has no such restriction. The reason is in the four cases of copy assignment in ¶1:

- ¶1.1 Both represent success: do nothing.
- ¶1.2 This is success and `rhs` is an error: construct *unex* from `rhs.unex`, then set `has_val = false`.
- ¶1.3 This is an error and `rhs` is success: destroy *unex* and set `has_val = true`.
- ¶1.4 Both are errors: `unex = rhs.error()`.

In ¶1.2, constructing *unex* may throw, but nothing has been destroyed before that and the flag has not been changed yet, so the object still represents success. ¶1.3 only destroys, and destruction does not throw. So switching states naturally has the strong exception guarantee, with no need for the backup-and-restore of the primary template.

¶3 Copy assignment therefore only requires `E` to be copy-assignable and copy-constructible, otherwise it is defined as deleted. ¶4 It is trivial when `E` is trivially copy-constructible, copy-assignable and destructible. ¶5–¶9 Move assignment is symmetric: it is constrained on `E` being move-constructible and move-assignable, and its noexcept is equivalent to `E` being nothrow move-constructible and nothrow move-assignable.

¶10–¶13 Assignment from `unexpected<G>` is equally simple: if the object is success, construct *unex* and set the flag to false; otherwise assign to *unex*.

¶14 `emplace()` takes no parameters, returns `void` and is `noexcept`: if the object is an error, it destroys *unex*, and then it represents success.

!!! impl "libc++'s assignment is not trivial yet"
    As with the primary template, as of the libc++ shipped with Clang 23, the copy and move assignment of `expected<void, E>` are always user-provided, so `std::is_trivially_copyable_v<std::expected<void, int>>` is false, while `is_trivially_copy_constructible_v` is true.

## swap [expected.void.swap]

¶1 `swap` requires `E` to be swappable and move-constructible. ¶2 If both are success, it does nothing; if both are errors, it swaps *unex*; if this is an error and the other is success, it calls `rhs.swap(*this)`. The remaining case, this is success and the other is an error:

```cpp
construct_at(addressof(unex), std::move(rhs.unex));
destroy_at(addressof(rhs.unex));
has_val = false;
rhs.has_val = true;
```

If the move construction throws, `rhs.unex` has not been destroyed yet and neither flag has changed, so again no backup is needed. ¶4 The noexcept is equivalent to `E` being nothrow move-constructible and nothrow swappable.

## Observers [expected.void.obs]

| Member | Rule |
|---|---|
| `operator bool`, `has_value()` | return *has_val* (¶1) |
| `has_error()` | returns `!has_value()` (¶2); added after C++23, not yet provided by libc++ in our tests |
| `void operator*() const noexcept` | hardened precondition: `has_value()` is true (¶3) |
| `void value() const &` | *Mandates* `E` is copy-constructible; on error throws `bad_expected_access(error())` (¶4–5) |
| `void value() &&` | *Mandates* `E` is copy-constructible and move-constructible; on error throws `bad_expected_access(std::move(error()))` (¶6–7) |
| the four overloads of `error()` | hardened precondition: `has_value()` is false (¶8–11) |
| `error_or(G&&)` | same as the primary template (¶12–15) |

`operator->` and `value_or` make no sense for `void` and are not provided.

`operator*` returns nothing, yet it still has a hardened precondition. Its existence lets generic code write `*e` uniformly even when `T` may be `void`. In a hardened implementation, evaluating `*e` on an `expected<void, E>` in the error state terminates the program, which amounts to a very cheap assertion. In a non-hardened implementation, violating it is {{ub}}, even though the function does nothing.

`value()` returns `void` but throws. `e.value();` means "continue on success, throw the error as an exception on failure", which is handy at the boundary between expected-style code and exception-style code.

## Monadic operations [expected.void.monadic]

Compared with the primary template, the only essential difference is that there is nothing to pass from the value side, so the `f` of `and_then` and `transform` takes no arguments:

- ¶1–¶8 `and_then`: `U = remove_cvref_t<invoke_result_t<F>>`, which must be an expected whose error type is `E`. On success it returns `invoke(f)`, otherwise `U(unexpect, error())`.
- ¶9–¶14 `or_else`: `f` takes the error, and its return type `G` must be an expected whose value type is `T`. There are no *Constraints* here, because there is nothing on the value side to pass into the result; on success it simply returns `G()`.
- ¶15–¶22 `transform`: `U = remove_cv_t<invoke_result_t<F>>`. On success with `U` not `void`, the value of the result is direct-initialized with `invoke(f)`; when `U` is `void`, it calls `f` and returns a successful `expected<U, E>`.
- ¶23–¶28 `transform_error`: on success it returns `expected<T, G>()`, otherwise it initializes the new error with `invoke(f, error())`.

With `transform`, `void` and non-`void` expecteds can be converted into each other: `expected<void, E>` with `transform([] { return 42; })` gives `expected<int, E>`, and `expected<int, E>` with `transform([](int) {})` gives `expected<void, E>`.

## Equality comparison [expected.void.eq]

¶1–¶2 Comparison with another `expected<T2, E2>` requires `T2` to be `void` too: unequal if the states differ, equal if both are success, and the errors are compared if both are errors. ¶3–¶4 Comparison with `unexpected<E2>` is the same as in the primary template.

There is no overload for comparing with a value, since there is no value. The corresponding operator in the primary template carries `requires (!is_void_v<T2>)`, and this one carries `requires is_void_v<T2>`; the two are complementary, so `void` and non-`void` expecteds cannot be compared with each other:

```cpp run error
#include <expected>
bool f(std::expected<void, int> a,
       std::expected<int, int> b) {
  return a == b;   // error: no usable operator==
}
```

<details class="fine" markdown="1"><summary>Remaining wording</summary>

[expected.void.monadic] ¶2 in the current draft reads `is_constructible_v<E, decltype(error())>>`, with an extra `>`. Comparing with ¶16 and with ¶2 of the primary template's [expected.object.monadic], the intent is `is_constructible_v<E, decltype(error())>`. This is an editorial error that does not affect the meaning.

</details>

## Questions

!!! question "Question"
    The assignment of the `void` partial specialization does not require `E` to be nothrow move-constructible. Can we conclude from this that assignment of `expected<void, E>` gives the strong exception guarantee for any `E`?

<details markdown="1">
<summary>Answer</summary>

For assignment that switches state, yes: going from success to error only constructs *unex*, and nothing has changed if that fails; going from error to success only destroys.

But when both sides are errors (¶1.4), the effect is `unex = rhs.error()`, which calls `E`'s own copy assignment. If that only gives the basic guarantee, the error in `*this` may be left in a valid but unspecified state. The accurate statement is: *has_val* never changes because of an exception, switching states has the strong guarantee, and assignment within the same state inherits `E`'s guarantee. The same holds for the case in the primary template where both sides have values ([expected.object.assign] ¶2.1).
</details>
