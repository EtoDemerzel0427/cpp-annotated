---
title: Comparisons
summary: "The header <compare> defines the result types of <=> (the three comparison categories), common_comparison_category for finding the common category, the three_way_comparable concept, compare_three_way_result, and comparison algorithms such as strong_order, plus C++26's type_order."
updated: 2026-10-19
---

!!! tldr
    - The result of `<=>` is one of three comparison categories, from strongest to weakest: `strong_ordering`, `weak_ordering`, `partial_ordering`; a stronger one converts implicitly to a weaker one.
    - Values of comparison categories can only be compared with the literal `0`, as in `r < 0`; comparing with other values is undefined behavior, and libc++ rejects it outright.
    - `common_comparison_category` picks the weakest of a set of categories, and a defaulted `operator<=>` uses it to deduce its return type.
    - `std::strong_order` and `std::weak_order` provide a total order and a weak order for floating-point numbers, so data containing NaN can be sorted.
    - C++26's `std::type_order` puts all types in a total order at compile time.

## What type `<=>` returns [compare.syn]

```cpp run title="partial-ordering.cpp" ok
#include <compare>
#include <limits>
int main() {
  double nan = std::numeric_limits<double>::quiet_NaN();
  auto r = 1.0 <=> nan;
  bool ok = r == std::partial_ordering::unordered
         && !(r < 0) && !(r == 0) && !(r > 0) && (r != 0);
  return ok ? 0 : 1;
}
```

C++20's three-way comparison operator `<=>` ([[expr.spaceship]]) doesn't return `int`. Comparing two `double`s gives a result of type `std::partial_ordering`. Besides less, equivalent and greater, it has a fourth value, `unordered`, meaning the two values can't be compared, for example because one is NaN.

These result types are defined by the library, yet the core language uses them directly: the result type of built-in `<=>`, the return type of a defaulted `operator<=>` ([[class.spaceship]]), and the rules rewriting `a < b` in terms of `<=>` ([[over.match.oper]]) all depend on this subclause. That is why [[expr.spaceship]] says `<compare>` must be included (or `import std;` used) before using `<=>`, even the built-in `1 <=> 2`, or the program is ill-formed.

¶1 `<compare>` specifies types, objects and functions for use primarily in connection with the three-way comparison operator. The whole header is freestanding. The function object `std::compare_three_way` is also declared in `<compare>`, but it is specified in [[comparisons.three.way]].

## The three comparison categories [cmp.categories]

### How they differ

¶1 `partial_ordering`, `weak_ordering` and `strong_ordering` are collectively called the **comparison category types**.

Telling them apart takes one notion. ¶4 **Substitutability** ([[g:substitutability]]) means: whenever `a == b` is true, `f(a) == f(b)` is true. Here `f` reads only comparison-salient state, and only through the public const members of its argument.

| Type | Values | Equality implies substitutability | Incomparable values allowed | Typical example |
|---|---|---|---|---|
| `strong_ordering` | `less`, `equal`, `greater` | Yes | No | Integers, pointers |
| `weak_ordering` | `less`, `equivalent`, `greater` | No | No | Case-insensitive strings |
| `partial_ordering` | `less`, `equivalent`, `greater`, `unordered` | No | Yes | Floating-point numbers |

With case-insensitive comparison, `"abc"` and `"ABC"` are equivalent, but their first characters differ, so they aren't substitutable, and the order can only be weak. The note in ¶2 says `strong_ordering` corresponds to a total order in mathematics.

¶1 Each type is specified in terms of an exposition-only member `value`, whose value is usually one of the following two exposition-only enumerations:

```cpp
enum class ord  { equal = 0, equivalent = equal, less = -1, greater = 1 };
enum class ncmp { unordered = -127 };
```

So `strong_ordering::equal` and `strong_ordering::equivalent` are the same value; the two names exist so that generic code can be written uniformly.

### Only comparable with the literal 0 (¶3)

!!! std
    In this context, the behavior of a program that supplies an argument other than a literal `0` is undefined.

¶3 The relational and equality operators of the comparison category types take an unnamed parameter of unspecified type. The implementation must choose this type so that it accepts the literal `0`; Example 1 says `nullptr_t` meets the requirement. Supplying any argument other than a literal `0` is undefined behavior.

So the comparison result is used just like the return value of `strcmp`: `r < 0` means less, `r == 0` means equal, and `0 > r` works too. This design keeps old habits working while preventing people from treating the result as an integer and writing code like `r == -1`.

```cpp error
#include <compare>
bool f(std::strong_ordering r) {
  return r < 1;   // standard: UB; libc++: error
}
```

!!! impl "libc++ turns this UB into a compile error"
    libc++'s parameter type is `_CmpUnspecifiedParam`, which has only a `consteval` constructor template accepting just `int`, with Clang's `enable_if` attribute requiring the argument to equal 0. So `r < 1`, `r < z` (with `z` an `int` variable) and `r < nullptr` are all compile-time errors. This is stricter than the standard; the standard makes the case UB precisely to leave implementations room to report an error.

### `unordered` in `partial_ordering`

A footnote in [cmp.partialord] says that for a type with `partial_ordering`, `a < b`, `a == b` and `a > b` can all be false. ¶2 says the result of `v @ 0` (where `@` is any relational or equality operator) is that `v` is ordered and `v.value @ 0`. So every comparison of `unordered` with 0 is false, except `!=`, which is true because `!=` is rewritten from `==`. The opening example demonstrates exactly this.

### Conversion and reversal

- **Implicit conversion only goes from stronger to weaker**: `strong_ordering` → `weak_ordering` → `partial_ordering`, mapped by the sign of `value` ([cmp.weakord] ¶2, [cmp.strongord] ¶2–¶3). There is no conversion in the opposite direction; `unordered` has no counterpart in `weak_ordering`.
- **`0 <=> v` reverses the result**: less becomes greater, greater becomes less, and the rest are unchanged ([cmp.partialord] ¶5, [cmp.weakord] ¶6, [cmp.strongord] ¶7). `v <=> 0` returns `v` unchanged. The compiler relies on this when it rewrites `a < b` as `0 < (b <=> a)` ([[over.match.oper]]).
- **Named comparison functions** `is_eq`, `is_neq`, `is_lt`, `is_lteq`, `is_gt` and `is_gteq` ([compare.syn]) take a `partial_ordering` and are equivalent to comparing with 0. The other two categories convert to it implicitly, so they can be used too.

## Picking the weakest category [cmp.common]

```cpp run title="common-category.cpp" ok
#include <compare>
#include <type_traits>
using std::common_comparison_category_t;
using std::strong_ordering, std::weak_ordering, std::partial_ordering;
static_assert(std::is_same_v<
  common_comparison_category_t<strong_ordering, weak_ordering>,
  weak_ordering>);
static_assert(std::is_same_v<
  common_comparison_category_t<strong_ordering, partial_ordering>,
  partial_ordering>);
static_assert(std::is_same_v<
  common_comparison_category_t<>, strong_ordering>);
static_assert(std::is_same_v<
  common_comparison_category_t<strong_ordering, int>, void>);

struct P {
  int i;
  double d;
  auto operator<=>(const P&) const = default;
};
static_assert(std::is_same_v<decltype(P{} <=> P{}), partial_ordering>);
int main() {}
```

¶1 `common_comparison_category<Ts...>::type` is the strongest category to which all of the template arguments can be converted. Note 1 explains what "stronger" means: the two categories are different and the former can be converted to the latter.

¶2 It is the **common comparison type** ([[g:common-comparison-type]], defined in [[class.spaceship]]) of `Ts...`. If any argument isn't a comparison category type, the result is `void`. Note 2 says the result is `strong_ordering` when the argument list is empty.

Put simply, it picks the weakest: if any is `partial_ordering`, the result is `partial_ordering`; otherwise if any is `weak_ordering`, the result is `weak_ordering`; otherwise `strong_ordering`. A defaulted `auto operator<=>` deduces its return type exactly this way: the common comparison type of the `<=>` results of all members. In the example, `P`'s `int` member gives a strong ordering and its `double` member a partial ordering, so together it is partial.

## The `three_way_comparable` concept [cmp.concept]

```cpp
template<class T, class Cat = partial_ordering>
  concept three_way_comparable =
    weakly-equality-comparable-with<T, T> &&
    partially-ordered-with<T, T> &&
    requires(const remove_reference_t<T>& a, const remove_reference_t<T>& b) {
      { a <=> b } -> compares-as<Cat>;
    };
```

This concept requires const lvalues of `T` to be comparable with `==`, `!=`, the four relational operators and `<=>`. The exposition-only *`compares-as<R, Cat>`* requires `common_comparison_category_t<R, Cat>` to be `Cat`, that is, the result of `<=>` must be at least as strong as `Cat`. So `three_way_comparable<double>` holds, and `three_way_comparable<double, std::weak_ordering>` doesn't.

Like all standard concepts, it has two layers. The `requires` expression above is the syntactic requirement, which the compiler checks. The other layer is the semantic requirements, written as "T models ... only if", which the compiler doesn't check:

- ¶2.1–¶2.7 The result of `a <=> b` is consistent with the results of `==`, `!=`, `<`, `>`, `<=` and `>=`, and `(a <=> b) <=> 0` equals `0 <=> (b <=> a)`;
- ¶2.8 If `Cat` is convertible to `strong_ordering`, `T` must also model `totally_ordered` ([[concept.totallyordered]]).

A type that meets the syntactic requirements but not the semantic ones is said to satisfy but not model the concept, for example a type whose `<=>` and `<` disagree. When the validity or meaning of a program depends on whether a type models a concept, satisfying without modeling is IFNDR: ill-formed, no diagnostic required ([[res.on.requirements#2]]).

¶1 The exposition-only *`partially-ordered-with<T, U>`* requires the eight relational operations `t < u`, `u > t` and so on to be usable; semantically, they are defined over the same domain and mirror each other, for example `t < u` and `u > t` give the same result.

¶3 `three_way_comparable_with<T, U, Cat>` is for two different types. It additionally requires `T` and `U` to have a common reference type, with mixed comparisons giving the same results as comparing after converting both sides to the common type (¶3.5), and, when `Cat` is convertible to `strong_ordering`, to model `totally_ordered_with` (¶3.10).

## `compare_three_way_result` [cmp.result]

¶2 Let `t` and `u` be lvalues of types `const remove_reference_t<T>` and `const remove_reference_t<U>` respectively. If `t <=> u` is well-formed as an unevaluated operand, `compare_three_way_result<T, U>::type` is `decltype(t <=> u)`; otherwise there is no member `type`, which templates can use for SFINAE.

It queries comparison between const lvalues. If a type has only a non-const `operator<=>`, `compare_three_way_result_t` doesn't exist.

¶1 The behavior of a program that adds specializations for `compare_three_way_result` is undefined.

## Comparison algorithms [cmp.alg]

### Six customization point objects

`strong_order`, `weak_order`, `partial_order`, `compare_strong_order_fallback`, `compare_weak_order_fallback` and `compare_partial_order_fallback` are all **customization point objects** ([[customization.point.object]]): function objects that, when called, try several implementation strategies in a fixed order and pick the first viable one. If none is viable, the call is ill-formed, which shows up as substitution failure during template argument substitution (Notes 1–6).

All six objects first require the decayed types of the two arguments to be the same (¶1.1, ¶2.1 and so on), otherwise the call is ill-formed; they don't do mixed-type comparisons.

### Total and weak orders for floating-point numbers

```cpp run title="cmp-alg.cpp" ok
#include <compare>
#include <limits>
int main() {
  double nan = std::numeric_limits<double>::quiet_NaN();
  bool ok =
      ((-0.0 <=> 0.0) == 0)               // built-in: -0 and +0 are equivalent
   && (std::strong_order(-0.0, 0.0) < 0)  // totalOrder: -0 < +0
   && (std::strong_order(nan, nan) == 0)  // the same NaN: equal
   && (std::weak_order(-0.0, 0.0) == 0)   // the two zeros are in one equivalence class
   && (std::strong_order(1.0, nan) < 0);  // a positive NaN is greater than every positive number
  return ok ? 0 : 1;
}
```

The built-in `<=>` for floating-point numbers gives only `partial_ordering`: NaN is incomparable, and `-0.0` and `+0.0` are equivalent. Where a total order is needed, for example to sort an array containing NaN, it can't be used.

¶1 `strong_order(E, F)` tries in order:

1. ¶1.2 `strong_order(E, F)` found only by argument-dependent lookup (ADL), with the result converted to `strong_ordering`; this is the entry point for user customization;
2. ¶1.3 if the arguments are of floating-point type, a total order consistent with that type's comparison operators; if `numeric_limits<T>::is_iec559` is true, this total order must also be consistent with the totalOrder operation of IEEE 754 (ISO/IEC 60559);
3. ¶1.4 `strong_ordering(compare_three_way()(E, F))`, if well-formed.

The totalOrder sequence is: negative NaNs, negative infinity, negative numbers, `-0`, `+0`, positive numbers, positive infinity, positive NaNs, and it distinguishes NaNs with different bit patterns.

¶2 `weak_order(E, F)` has similar steps. The floating-point case (¶2.3) gives the following equivalence classes, from smallest to largest: all negative NaNs, negative infinity, each negative normal number, each negative subnormal number, the two zeros, each positive subnormal number, each positive normal number, positive infinity, all positive NaNs. So `weak_order(-0.0, +0.0)` is `equivalent`. For non-floating-point types, it tries `compare_three_way()(E, F)` (¶2.4) and then `strong_order(E, F)` (¶2.5).

¶3 `partial_order(E, F)` tries the ADL-found `partial_order`, `compare_three_way()(E, F)`, and `weak_order(E, F)` in order.

### The three fallbacks (¶4–¶6)

<div class="compare" markdown="1">

```cpp run ok
#include <compare>
struct Legacy {   // only == and <
  int v;
  bool operator==(const Legacy&) const
    = default;
  bool operator<(const Legacy& o) const
    { return v < o.v; }
};
int main() {
  auto r = std::compare_weak_order_fallback(
    Legacy{1}, Legacy{2});
  return std::is_lt(r) ? 0 : 1;
}
```

```cpp run error
#include <compare>
struct Legacy {   // only == and <
  int v;
  bool operator==(const Legacy&) const
    = default;
  bool operator<(const Legacy& o) const
    { return v < o.v; }
};
// error: no <=>, no viable strategy
auto r = std::weak_order(
  Legacy{1}, Legacy{2});
```

</div>

¶4 `compare_strong_order_fallback(E, F)` first tries `strong_order(E, F)`. If that isn't viable, and `E == F` and `E < F` are both well-formed with results usable as `bool`, it uses

```cpp
E == F ? strong_ordering::equal : E < F ? strong_ordering::less : strong_ordering::greater
```

¶5 `compare_weak_order_fallback` is analogous. ¶6 `compare_partial_order_fallback` uses three comparisons, `E == F`, `E < F` and `F < E`, giving `unordered` when all are false.

They let generic code support C++17-style types that define only `==` and `<` as well. The price is that the fallback trusts these two operators to form the corresponding order; if they don't, the result is meaningless.

## A total order on types: `type_order` [compare.type] {{c++26}}

¶1 There is an implementation-defined total ordering of all types. For any two types `X` and `Y` (possibly incomplete), *`TYPE-ORDER`*`(X, Y)` is a constant expression of type `strong_ordering`: `less` if `X` precedes `Y`, `greater` if `Y` precedes `X`, and `equal` if they are the same type.

```cpp
template<class T, class U> struct type_order {
  static constexpr strong_ordering value = TYPE-ORDER(T, U);
  using value_type = strong_ordering;
  constexpr operator value_type() const noexcept { return value; }
  constexpr value_type operator()() const noexcept { return value; }
};
template<class T, class U>
  constexpr strong_ordering type_order_v = type_order<T, U>::value;
```

Its purpose is to sort types at compile time, for example to canonicalize `variant<int, double>` and `variant<double, int>` into the same type, or to produce a canonical permutation of a set of types. At the time of writing, libc++ doesn't provide `type_order` yet.

- Note 1: `int`, `const int` and `int&` are different types, each with its own position.
- Note 2: this order need not be consistent with `type_info::before` ([[support.rtti]]).
- Note 3: the ordering of TU-local types from different translation units isn't observable, because the necessary `type_order` specializations can't be written.
- ¶2 A program declaring an explicit or partial specialization of `type_order` is ill-formed. ¶3 `type_order` and `type_order_v` can be instantiated with incomplete types.
- ¶4 It is recommended that the order be lexicographical for parameter-type-lists and template argument lists.

!!! history
    Three-way comparison was introduced into C++20 by [[P0515R3]], and [[P0768R1]] supplied the library part, i.e. most of `<compare>`. [[P1614R2]] extended `<=>` throughout the standard library. The early design also had two categories `strong_equality` and `weak_equality`; [[P1959R0]] removed them, which is why only three remain today.

## Common misconceptions

!!! pitfall "`r != 0` being true means `r < 0` or `r > 0`"
    Not for `partial_ordering`. `unordered != 0` is true, while `unordered < 0` and `unordered > 0` are both false. Consider `unordered` separately when handling floating-point comparison results.

!!! pitfall "`std::strong_order` can compare `int` with `long`"
    All six comparison algorithms require the decayed types of the two arguments to be the same, so `std::strong_order(1, 2L)` is ill-formed. To compare different types, use `<=>` or `std::compare_three_way`.

## Questions

!!! question "Question"
    What type does the `<=>` of `struct S { float f; std::string s; auto operator<=>(const S&) const = default; };` return? Does `std::three_way_comparable<S, std::weak_ordering>` hold?

<details markdown="1">
<summary>Answer</summary>

The `<=>` of `float` gives `partial_ordering`, and that of `std::string` gives `strong_ordering`; the common comparison type picks the weakest, so it returns `std::partial_ordering` ([[class.spaceship]], [cmp.common]). `compares-as<partial_ordering, weak_ordering>` requires `common_comparison_category_t<partial_ordering, weak_ordering>` to be `weak_ordering`, but it is actually `partial_ordering`, so the concept doesn't hold.
</details>
