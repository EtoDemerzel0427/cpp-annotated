---
title: Reflection type traits
summary: "Almost every trait in <type_traits> has a consteval version in std::meta that takes reflections; this subclause specifies their naming, whether errors throw or reject compilation, and that results are always types with aliases stripped."
updated: 2026-10-19
---

!!! tldr
    - `std::is_X<T>` corresponds to `std::meta::is_X_type(^^T)`, and the transformation `std::X<T>::type` to `std::meta::X(^^T)`; the results are exactly the same as the template versions.
    - Predicates get a `_type` suffix to distinguish them from reflection queries with different meanings, such as `std::meta::is_const` and `is_function`.
    - When an argument is not the reflection of a type, or when the template version would fail by violating a *Mandates* or has no `type` member, the reflection version throws `meta::exception`, which can be caught in `consteval` code.
    - Functions returning reflections always return the type itself, never an alias; to compare reflections of two types, use `is_same_type` or `dealias` first, not `==` directly.

!!! note "About the examples on this page"
    Clang 23 does not support C++26 reflection yet. The code on this page is written from the current draft, has not been compiled, and therefore carries no verdict.

```cpp
#include <meta>

// whether all non-static data members of a class are trivially copyable
consteval bool all_members_trivially_copyable(std::meta::info cls) {
  auto ctx = std::meta::access_context::unchecked();
  for (std::meta::info m : std::meta::nonstatic_data_members_of(cls, ctx))
    if (!std::meta::is_trivially_copyable_type(std::meta::type_of(m)))
      return false;
  return true;
}
```

Writing the same check with `<type_traits>` would require first forming the member types into a type pack, and before C++26 the language had no way to get that pack at all. Reflection makes types ordinary values, so traits also need versions that take values, to compose with `for` loops, `vector` and algorithms.

¶1 [meta.reflection.traits] defines no new semantics: each `consteval` function here corresponds to a class template in [[meta.unary]], [[meta.rel]] or [[meta.trans]], called its associated class template, and the function's result is the result that class template gives.

## Naming rules (¶4)

| Kind of associated trait | Reflection version | Example |
|---|---|---|
| Unary predicate `std::X<T>` | `bool X_type(info)` | `is_trivially_copyable_type(^^T)` |
| Binary predicate `std::X<T, U>` | `bool X_type(info, info)` | `is_same_type`, `is_base_of_type`, `is_convertible_type` |
| Variadic predicate `std::X<T, U...>` | `bool X_type(info, R&& args)` | `is_constructible_type(^^T, {^^int, ^^int})` |
| Variadic predicate `std::X<R, F, U...>` | `bool X_type(info, info, R&& args)` | `is_invocable_r_type` |
| Unary transformation `std::X<T>::type` | `info X(info)`, no suffix | `remove_cvref(^^T)`, `decay(^^T)` |
| Variadic transformations | `info X(R&& args)` or `info X(info, R&& args)` | `common_type({...})`, `invoke_result(^^F, {...})` |

Here `R` is constrained by `reflection_range`, i.e. a range whose elements are `info` (see [[meta.reflection.extract]]); a braced list such as `{^^int, ^^int}` works too.

The only predicates without the `_type` suffix are `has_virtual_destructor`, `has_unique_object_representations`, `reference_constructs_from_temporary` and `reference_converts_from_temporary`, whose names do not begin with `is_` to begin with.

Why do predicates get a suffix? Because `std::meta` already has a set of queries with the same names and different meanings ([[meta.reflection.queries]]):

```cpp
const int v = 0;
static_assert(std::meta::is_const(^^v));                // the type of variable v is const
static_assert(std::meta::is_const_type(^^const int));   // the type const int
// std::meta::is_const_type(^^v);                       // throws: ^^v is not the reflection of a type
```

`is_const(r)` asks whether what the reflection represents is `const`, and can be applied to variables, function types and so on; `is_const_type(r)` is the counterpart of `std::is_const` and accepts only types. Likewise, `is_function(r)` asks whether `r` represents a function, and `is_function_type(r)` whether it is a function type. Transformation functions have no such clash and keep the original names.

### Functions that do not follow the pattern above (¶7–¶13)

| Function | Result |
|---|---|
| `rank(type)`, `extent(type, i = 0)` | `std::rank<T>::value`, `std::extent<T, I>::value` |
| `tuple_size(type)`, `tuple_element(index, type)` | `std::tuple_size<T>::value`, the reflection of `std::tuple_element<I, T>::type` |
| `variant_size(type)`, `variant_alternative(index, type)` | Likewise |
| `type_order(t1, t2)` | `std::type_order<T1, T2>::value`, of type `strong_ordering` |

The `index` and `i` here are ordinary function parameters and need not be constant expressions: the `i` in `tuple_element(i, ^^T)` can be a loop variable. This is where the reflection versions are more convenient than the template versions.

The synopsis of `<meta>` ([[meta.syn]]) also declares `is_applicable_type`, `is_nothrow_applicable_type` and `apply_result`, corresponding to `std::is_applicable` and friends. Note that `alignment_of` is not in this subclause: `std::meta::alignment_of` is the layout query in [[meta.reflection.queries]], which accepts variables, data members and more besides types.

## What happens on errors (¶2–¶3)

```cpp
consteval bool has_signed_version(std::meta::info t) {
  try {
    (void)std::meta::make_signed(t);
    return true;
  } catch (const std::meta::exception&) {
    return false;
  }
}
static_assert( has_signed_version(^^unsigned));
static_assert(!has_signed_version(^^bool));   // std::make_signed<bool> violates its Mandates
```

¶2 The arguments must be reflections of types. Every parameter of type `info` must satisfy `is_type`, and so must every element of a `reflection_range` argument; otherwise `meta::exception` is thrown. So `is_class_type(^^std::vector)` (a template is not a type) and `remove_cvref(^^some_variable)` both throw.

¶3 handles the cases where the associated class template itself has a problem. Let `S` be the class template specialization corresponding to the call:

1. ¶3.1 If the template arguments of `S` violate the *Mandates* of the class template, or the call is to return a type and `S` has no member `type`, or `S::value` cannot be converted to the function's return type, `meta::exception` is thrown. In the first case `S` is not instantiated (Note 1). So `make_signed(^^bool)`, `common_type({^^int, ^^std::string})` and `underlying_type(^^int)` all throw and can be caught in `consteval` code, whereas the corresponding template versions are either hard errors or have no `type`.
2. ¶3.2 Otherwise, if instantiating `S` would have undefined behavior because it depends on an incomplete type ([[meta.rqmts]] paragraph 5), the call is not a constant subexpression, and the compiler must reject it.
3. ¶3.3 Otherwise, if the template arguments do not meet a precondition of the class template (most commonly the requirement that a type be complete), it is unspecified whether the call is a constant subexpression; if it is, the result is as if the class template had no such precondition.

Rules 2 and 3 correspond to the two layers of rules on incomplete types in [[type.traits]]. Violating those rules with the template versions is undefined behavior; undefined behavior is not allowed during constant evaluation, so the reflection versions tighten this into either rejecting compilation or giving a definite result.

## The results are types, not aliases (¶4–¶6)

```cpp
using Int = int;
static_assert(^^int != ^^Int);                          // a type and an alias are different constructs
static_assert(std::meta::is_same_type(^^int, ^^Int));   // but they are the same type
static_assert(^^int == std::meta::dealias(^^Int));
static_assert(std::meta::remove_cvref(^^const Int&) == ^^int);   // the result has aliases stripped
```

¶4 Table 64 uniformly specifies the return values for each signature: predicates return `std::X<T...>::value`, and transformations return a reflection representing `std::X<T...>::type`, where `T` is the type or type alias represented by the argument. Implementations need not actually instantiate the associated class template, and can compute the result directly with compiler builtins (Note 2).

¶5 Functions returning reflections always represent a type, never a type alias (Note 3). ¶6 Conversely, `==` on reflections compares the represented constructs: `^^int` represents a type and `^^Int` an alias, so the two are not equal, but `is_same_type` considers them the same type (Note 4). So when comparing types in reflection code, use `is_same_type`, or `dealias` before comparing.
