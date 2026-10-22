---
title: Comparison concepts
summary: "What equality_comparable, totally_ordered and their cross-type versions require, and the two exposition-only concepts they depend on: boolean-testable (comparison results usable like bool) and comparison-common-type-with (two types compared within one domain of values)."
updated: 2026-10-19
---

!!! tldr
    - `equality_comparable<T>` requires `==` to reflect equality of values exactly, so `==` must be an equivalence relation.
    - The cross-type `equality_comparable_with<T, U>` and `totally_ordered_with<T, U>` additionally require that comparing `t` and `u` directly gives the same result as comparing after converting both to the common type.
    - Comparison results need not be `bool`, but they must be *boolean-testable*: convertible to `bool`, with `!` meaning negation, and with `&&` and `||` not hijacked by user overloads. The compiler doesn't check the last one.
    - `totally_ordered<T>` requires trichotomy: for any two values exactly one of `<`, `>` and `==` holds. `double` models it too, because NaN is outside the domain.

[concepts.compare] describes concepts that establish relationships and orderings on values of possibly differing object types ([concepts.compare.general] ¶1). There are only four public concepts: `equality_comparable`, `equality_comparable_with`, `totally_ordered` and `totally_ordered_with`. They depend on two **exposition-only** concepts, concepts used only to write the specification, which programs can't use directly:

- *boolean-testable*: what it means for a comparison result to be usable like a `bool`;
- *comparison-common-type-with*: what it means for values of two types to be compared within one domain of values.

`three_way_comparable` in `<compare>` ([[cmp.concept]]) also uses these two concepts. For terms such as satisfying, modeling and equality preservation below, see [[concepts]]; for common references, see [[concept.commonref]].

## Comparison results must behave like `bool`: *boolean-testable*

### The problem: convertible to `bool` isn't enough

```cpp run title="hijacked-and.cpp" ok
#include <concepts>
#include <cstdio>

struct Weird {   // the result type of ==, with && overloaded
  bool b;
  operator bool() const { return b; }
  friend Weird operator&&(Weird, Weird) {
    std::puts("user &&");
    return {false};
  }
};
struct X {
  int v;
  friend Weird operator==(X a, X b) { return {a.v == b.v}; }
  friend Weird operator!=(X a, X b) { return {a.v != b.v}; }
};
static_assert(std::equality_comparable<X>);   // satisfied

int main() {
  X a{1}, b{1};
  if (a == b && a == b) std::puts("true");
  else std::puts("false");   // prints user && and false
}
```

Generic code does more with comparison results than `if (a == b)`; it also writes `!(a < b) && pred(x)` and `a == b || c == d`. If the type returned by `==` overloads `&&`, these expressions call the user's function: short-circuit evaluation is lost ([[expr.log.and]]), and the result may have no Boolean meaning at all. The `Weird` returned by `X`'s `==` converts to `bool`, yet makes `a == b && a == b` give `false`.

¶1 explains that *boolean-testable* specifies exactly such expressions: those convertible to `bool` for which the logical operators `&&`, `||` and `!` have the conventional semantics.

### What the compiler checks (¶1, ¶6)

```cpp
template<class T>
  concept boolean-testable-impl = convertible_to<T, bool>;  // exposition only

template<class T>
  concept boolean-testable =                                  // exposition only
    boolean-testable-impl<T> && requires(T&& t) {
      { !std::forward<T>(t) } -> boolean-testable-impl;
    };
```

The compiler checks only two things: `T` converts both implicitly and explicitly to `bool`, and the result of `!t` also converts to `bool`. `&&` and `||` aren't in the syntactic requirements, because "this call must select the built-in operator" can't be written as a requires-expression. They are put into the semantic requirements instead, so `X` above satisfies `equality_comparable` but doesn't model it.

A type with `!` deleted doesn't even satisfy the syntax:

```cpp run title="no-bang.cpp" ok
#include <concepts>

struct NoBang {
  operator bool() const { return true; }
  void operator!() const = delete;
};
struct Y {
  friend NoBang operator==(Y, Y) { return {}; }
  friend NoBang operator!=(Y, Y) { return {}; }
};
static_assert(!std::equality_comparable<Y>);

int main() {}
```

### What isn't checked: disqualifying declarations (¶2–¶5)

¶2 Let `e` be an expression such that `decltype((e))` is `T`. `T` models *boolean-testable-impl* only if:

- ¶2.1 either `remove_cvref_t<T>` isn't a class type, or a search for `operator&&` and `operator||` in its scope finds nothing, i.e. there are no member overloads;
- ¶2.2 argument-dependent lookup ([[basic.lookup.argdep]]) for `operator&&` and `operator||` with `T` as the only argument type finds no **disqualifying declaration**.

Disqualifying declarations are characterized by three layered definitions. The gist: any `&&` or `||` overload that could possibly accept `e` as an operand disqualifies `T`.

1. ¶3 A **disqualifying parameter** is a function parameter declared with type `P` such that:
    - ¶3.1 `P` isn't dependent on a template parameter, and there is an implicit conversion sequence ([[over.best.ics]]) from `e` to `P`; or
    - ¶3.2 `P` is dependent on one or more template parameters, and either `P` contains no template parameter that participates in deduction, or template argument deduction ([[temp.deduct.call]]) with `e` as the argument succeeds.
2. ¶4 A **key parameter** of a function template `D` is a function parameter of type `cv X` or a reference to it, where `X` names a specialization of a class template that has the same innermost enclosing non-inline namespace as `D`, and `X` contains at least one template parameter that participates in deduction. In Example 1, `Z::operator&&(C<T> x, T y)` has a key parameter `C<T> x`; `Z::operator||(C<type_identity_t<T>> x, T y)` doesn't, because `type_identity_t<T>` doesn't participate in deduction.
3. ¶5 A **disqualifying declaration** is a non-template function declaration with at least one disqualifying parameter (¶5.1); or a function template declaration with at least one disqualifying parameter that meets one of the following (¶5.2): some disqualifying parameter is a key parameter, the declaration has no key parameters, or it declares a function template to which no name is bound ([[dcl.meaning]]).

¶6 Note 1 states the intent: for two types `T1` and `T2` that both model *boolean-testable-impl*, `declval<T1>() && declval<T2>()` and `||` must resolve to the built-in operators.

The rules are this convoluted because the concept gets only one type `T` and can't see the type of the other operand. ¶2–¶5 are a conservative approximation that looks at one type: if any overload related to `T` could possibly be selected in combination with some other type, `T` is disqualified. The key-parameter rule avoids collateral damage: an operator like `Z::operator&&(C<T>, T)` that applies only to specializations of some class template doesn't count if `C<T>` can't be deduced from `e`.

### `!` must be negation (¶7–¶8)

¶7 `T` models *boolean-testable* only if, in addition, `bool(e) == !bool(!e)`. ¶8 Example 2 lists types that model it: `bool`, `true_type`, `int*`, `bitset<N>::reference`.

!!! history
    *boolean-testable* was introduced by [[P1964R2]] before C++20 shipped, replacing a public concept `boolean` from earlier drafts. The old concept tried to enumerate with syntactic requirements the results of `&&`, `||`, `!`, `==` and `!=` across all combinations of types; it was huge, slow to compile, and still couldn't stop `&&` from being overloaded. The new approach shrinks the syntactic requirements to a minimum, writes "must not be hijacked" as a semantic requirement, and is no longer public.

## A common domain for cross-type comparison: *comparison-common-type-with*

`std::string` and `const char*` can be compared with `==`. What should that comparison mean? The standard's answer: it must give the same result as comparing after converting both sides to the common type `std::string`. *comparison-common-type-with* specifies what this common type must satisfy.

```cpp
template<class T, class U, class C = common_reference_t<const T&, const U&>>
  concept comparison-common-type-with-impl =   // exposition only
    same_as<common_reference_t<const T&, const U&>,
            common_reference_t<const U&, const T&>> &&
    requires {
      requires convertible_to<const T&, const C&> || convertible_to<T, const C&>;
      requires convertible_to<const U&, const C&> || convertible_to<U, const C&>;
    };

template<class T, class U>
  concept comparison-common-type-with =        // exposition only
    comparison-common-type-with-impl<remove_cvref_t<T>, remove_cvref_t<U>>;
```

The common domain `C` is the common reference type of `const T&` and `const U&`, and both sides must be convertible to `const C&`, either from a const lvalue or from an rvalue.

The conversion used in the semantic requirements is written *CONVERT_TO_LVALUE*`<C>(E)` ([concepts.compare.general] ¶2). It is `static_cast<const C&>(as_const(E))` if that is valid (¶2.1), and otherwise `static_cast<const C&>(std::move(E))` (¶2.2). That is, it first tries a conversion that leaves the source object alone, and only then converts from an rvalue.

The semantic requirement in [concept.comparisoncommontype] ¶1 parallels [[concept.commonref]]: let `t1` and `t2` be equality-preserving lvalues of type `remove_cvref_t<T>`; then *CONVERT_TO_LVALUE*`<C>(t1)` equals *CONVERT_TO_LVALUE*`<C>(t2)` if and only if `t1` equals `t2`; likewise for the `U` side. Conversion to the common domain can neither merge different values nor split equal ones.

!!! history "Why not just use `common_reference_with`"
    C++20's original `equality_comparable_with<T, U>` required `common_reference_with<const T&, const U&>`. For `unique_ptr<int>` and `nullptr_t`, the common reference type is the non-reference `unique_ptr<int>`, and converting to it from `const unique_ptr<int>&` requires a copy, so move-only types didn't satisfy it, even though `p == nullptr` obviously makes sense. C++23's [[P2404R3]] introduced *comparison-common-type-with* and *CONVERT_TO_LVALUE*, relaxing the requirement to convertibility to `const C&`, and changed `totally_ordered_with` and `three_way_comparable_with` in the same way.

## `equality_comparable` ([concept.equalitycomparable])

### Four directions (¶1)

```cpp
template<class T, class U>
  concept weakly-equality-comparable-with = // exposition only
    requires(const remove_reference_t<T>& t, const remove_reference_t<U>& u) {
      { t == u } -> boolean-testable;
      { t != u } -> boolean-testable;
      { u == t } -> boolean-testable;
      { u != t } -> boolean-testable;
    };
```

All four directions must work, and all results must be *boolean-testable*. Since C++20 there are rewritten candidates ([[over.match.oper]], [[class.compare]]), so defining a single `operator==` makes all four expressions valid.

¶1's semantic requirements: the four expressions have the same domain (¶1.1); `u == t` gives the same result as `t == u` (¶1.2); `t != u` is the negation of `t == u` (¶1.3); `u != t` gives the same result as `t != u` (¶1.4).

### `==` is equality (¶2–¶3)

```cpp
template<class T>
  concept equality_comparable = weakly-equality-comparable-with<T, T>;
```

!!! std
    T models equality_comparable only if bool(a == b) is true when a is equal to b, and false otherwise.

¶2 This sentence ties abstract equality ([[concepts.equality]]) to the `==` operator: `a == b` is true when `a` and `b` are equal, and false otherwise. ¶3 Note 1 adds that `a == b` is required to be equality-preserving, from which it follows that `==` is symmetric and transitive; together with every value being equal to itself, `==` is an equivalence relation.

This requirement has two direct consequences:

- `double` models `equality_comparable`. NaN is outside the domain of `==` ([[structure.requirements#8]]), which doesn't affect modeling, but algorithms relying on this concept can't be expected to give meaningful results for data containing NaN.
- An `==` that compares names case-insensitively models it only if "the same ignoring case" really is equality of values for that type. If some equality-preserving operation (such as an accessor `name()`) can distinguish two objects that differ in case, with `a == b` true but `a.name() != b.name()`, then `==` no longer coincides with equality.

### The cross-type version (¶4)

```cpp
template<class T, class U>
  concept equality_comparable_with =
    equality_comparable<T> && equality_comparable<U> &&
    comparison-common-type-with<T, U> &&
    equality_comparable<common_reference_t<const remove_reference_t<T>&,
                                           const remove_reference_t<U>&>> &&
    weakly-equality-comparable-with<T, U>;
```

Cross-type equality comparison means more than having an `operator==(T, U)`. Each side must be equality comparable on its own, there must be a common domain `C`, `C` itself must be equality comparable, and only then come the four cross-type operations.

¶4's semantic requirement: let `t` and `t2` be lvalues denoting distinct but equal objects of types `const remove_reference_t<T>` and `remove_cvref_t<T>` respectively, and likewise `u` and `u2`; then

```cpp
bool(t == u) == bool(CONVERT_TO_LVALUE<C>(t2) == CONVERT_TO_LVALUE<C>(u2))
```

This fixes the meaning of `string == const char*` as comparing by `string` value, not comparing pointers.

```cpp run title="equality-comparable-with.cpp" ok
#include <concepts>
#include <cstddef>
#include <memory>
#include <string>
#include <string_view>

using std::equality_comparable_with;

static_assert(equality_comparable_with<
  std::string, const char*>);
static_assert(equality_comparable_with<
  std::string, std::string_view>);
static_assert(!equality_comparable_with<int, std::string>);
// holds since P2404R3
static_assert(equality_comparable_with<
  std::unique_ptr<int>, std::nullptr_t>);

int main() {}
```

## `totally_ordered` ([concept.totallyordered])

```cpp
template<class T>
  concept totally_ordered = equality_comparable<T> && partially-ordered-with<T, T>;
```

*partially-ordered-with* is defined in [[cmp.concept]]: the 8 expressions `<`, `>`, `<=` and `>=` in both directions are all usable, the results are *boolean-testable*, and `t < u` agrees with `u > t` and `t <= u` with `u >= t`.

¶1's semantic requirements: for lvalues `a`, `b` and `c` of type `const remove_reference_t<T>`,

- ¶1.1 exactly one of `bool(a < b)`, `bool(a > b)` and `bool(a == b)` is true; this is called **trichotomy**;
- ¶1.2 if `a < b` and `b < c`, then `a < c`;
- ¶1.3 `bool(a <= b) == !bool(b < a)`;
- ¶1.4 `bool(a >= b) == !bool(a < b)`.

Trichotomy, together with `==` being equality, means `<` is a total order: any two unequal values can be ranked. This is stricter than a comparator's `strict_weak_order` ([[concept.strictweakorder]]), which allows elements that are indistinguishable yet not equal.

¶2's `totally_ordered_with<T, U>` has the same structure as `equality_comparable_with`: each side totally ordered, cross-type equality comparable, the common domain totally ordered, and the 8 cross-type operations usable. ¶2.1–¶2.8 require each cross-type `<`, `>`, `<=` and `>=` to agree with the result of comparing after converting to `C`.

```cpp run title="totally-ordered.cpp" ok
#include <concepts>
#include <cmath>

static_assert(std::totally_ordered<double>);
static_assert(std::totally_ordered_with<int, double>);

int main() {
  double nan = std::nan("");
  // all three are false, violating trichotomy;
  // this only shows that NaN is outside the domain
  return (nan < 1.0 || nan > 1.0 || nan == 1.0) ? 1 : 0;
}
```

## Common misconceptions

!!! pitfall "Comparison operators returning a custom type"
    Expression template libraries (some linear algebra libraries, SQL DSLs) make `a == b` return a lazily evaluated expression object and overload `&&` and `||` to combine expressions. Such types can satisfy `equality_comparable` but almost never model *boolean-testable*. Handing them to `ranges::find` or `ranges::sort` is {{ifndr}} ([[res.on.requirements]]).

!!! pitfall "Writing only `operator!=`"
    C++20's rewritten candidates fill in `!=` and the reversed comparisons from a single `operator==`, so *weakly-equality-comparable-with* is usually satisfied automatically. The converse doesn't work: if only `operator!=` is written, `!=` isn't used to rewrite `==`.

!!! pitfall "Cross-type comparison disagreeing with the common type"
    If `S == int` compares `S::id`, while `common_reference_t<const S&, const int&>` yields something else through some conversion, `equality_comparable_with<S, int>` is satisfied but not modeled. When defining cross-type comparisons for a pair of types, make sure their common type reaches the same conclusions, or simply don't provide implicit conversions that produce a common type.

## Questions

!!! question "Questions"
    1. Why does *boolean-testable* only require the result of `!t` to be convertible to `bool`, rather than requiring `!t` itself to be *boolean-testable*?
    2. Is `std::equality_comparable_with<int, double>` true? Are the semantic requirements modeled? What about `long long` and `double`?
    3. A type writes only `auto operator<=>(const S&) const = default;` and no `operator==`. Does it satisfy `totally_ordered`? What if the `operator<=>` is implemented by the user?

<details markdown="1">
<summary>Answer</summary>

1. A recursive definition would expand forever (`!!t`, `!!!t`…). The standard requires only one level, and ¶7's `bool(e) == !bool(!e)` guarantees that level means the right thing.
2. True: the common reference type is `double`, and all four comparisons work. It is also modeled when `int` is 32 bits: every `int` is exactly representable as a double, so converting to `double` merges no values. Not so for `long long` and `double`: distinct values above 2^53 may become equal after conversion, violating [concept.comparisoncommontype] ¶1.
3. It does. By [[class.compare.default]], a defaulted `operator<=>` implicitly declares a defaulted `operator==`, so `==`, `!=`, and `<` and the others rewritten through `<=>` are all usable. A user-implemented `operator<=>` brings no `operator==`, so `equality_comparable` isn't satisfied, and neither is `totally_ordered`.
</details>
