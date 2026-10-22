---
title: Unary type traits
summary: "The primary type category predicates place every type in exactly one category, and the composite category predicates are combinations of them; rank, extent and alignment_of query an array's rank, its bounds, and alignment."
updated: 2026-10-19
---

!!! tldr
    - The 15 primary type category predicates (`is_void`, `is_integral`, `is_pointer`, `is_class` ...) do not overlap: for any type, exactly one of them is true.
    - The composite category predicates (`is_arithmetic`, `is_scalar`, `is_object` ...) are combinations of the primary categories and can overlap.
    - Neither kind looks at top-level cv: `is_integral_v<const volatile int>` is true.
    - Frequently misremembered: member pointers are not pointers, enumerations are not arithmetic types but are scalar types, and `std::array` is not an array type.
    - The results of `rank`, `extent` and `alignment_of` are `size_t` values, and `extent` gives 0 both for unknown bounds and out-of-range dimensions.

## General [meta.unary.general]

¶1 The templates in [meta.unary] query properties of a type at compile time. It has three parts: primary type categories, composite type categories, and type properties. Type properties are extensive and have their own page, [[meta.unary.prop]].

¶2 These templates are all *Cpp17UnaryTypeTrait*s ([[type.traits]]): they derive from `true_type` if the condition holds and from `false_type` otherwise.

## Primary type categories [meta.unary.cat]

```cpp title="primary-categories.cpp" run ok
#include <array>
#include <cstddef>
#include <type_traits>

struct S { int m; void f(); };
union U { int a; };
using Abominable = void() const;

static_assert(!std::is_array_v<std::array<int, 3>>);           // the class template array is not an array type
static_assert( std::is_array_v<int[]>);                        // arrays of unknown bound count too
static_assert(!std::is_pointer_v<int S::*>);                   // a member pointer is not a pointer
static_assert( std::is_pointer_v<void (*)()>);                 // a function pointer is a pointer
static_assert(!std::is_pointer_v<std::nullptr_t>);
static_assert( std::is_null_pointer_v<const std::nullptr_t>);  // cv does not affect the result
static_assert(!std::is_function_v<int (&)()>);                 // a function reference is a reference
static_assert( std::is_function_v<Abominable>);                // so is a cv-qualified function type
static_assert( std::is_member_function_pointer_v<void (S::*)() const&&>);
static_assert( std::is_integral_v<bool> && std::is_integral_v<char8_t>);
static_assert(!std::is_class_v<U> && std::is_union_v<U>);
static_assert( std::is_class_v<decltype([] {})>);              // a closure type is a class

int main() {}
```

¶1 The primary type categories correspond one-to-one to the type classification in [[basic.types]]. The note in ¶3 states their design goal:

!!! std
    For any given type `T`, exactly one of the primary type categories has a `value` member that evaluates to `true`.

That is, these 15 predicates divide all C++ types into 15 cells that are pairwise disjoint and together cover every type:

| Group | Predicate | Condition | Notes |
|---|---|---|---|
| Fundamental types | `is_void` | `void` | |
| | `is_null_pointer` | `std::nullptr_t` | Not a pointer |
| | `is_integral` | Integral types ([[basic.fundamental]]) | Includes `bool`, all character types, extended integer types |
| | `is_floating_point` | Floating-point types | Includes extended floating-point types |
| | `is_reflection` {{c++26}} | `std::meta::info` | |
| Compound types | `is_array` | Arrays of known or unknown bound | `std::array` is not an array type |
| | `is_pointer` | Pointer types | Includes function pointers, excludes member pointers |
| | `is_lvalue_reference`, `is_rvalue_reference` | Lvalue references, rvalue references | |
| | `is_member_object_pointer`, `is_member_function_pointer` | Pointers to data members, pointers to member functions | |
| | `is_enum` | Enumerations | Both scoped and unscoped |
| | `is_union` | Unions | |
| | `is_class` | Non-union class types | Closure types are classes too |
| | `is_function` | Function types | Includes function types with cv- or ref-qualifiers; excludes function references and function pointers |

A qualified function type like `void() const` cannot be used to declare an ordinary function and only appears as the pointee of a member function pointer, but it really is a function type ([[dcl.fct]]).

¶2 Applying these templates to `T` and to *cv* `T` must give the same result. cv-qualification on reference types and function types is ignored anyway, so the rule holds trivially for them.

!!! note "Writing `is_function` without a compiler builtin"
    Function types come in many shapes: parameter lists, `noexcept`, cv- and ref-qualifiers, C-style variadics. Early implementations exploited a core language fact: only function types and reference types stay unchanged when `const` is added ([[dcl.fct]], [[dcl.ref]]). So it could be written as:

    ```cpp
    template<class T>
    struct is_function
      : std::bool_constant<!std::is_const_v<const T> && !std::is_reference_v<T>> {};
    ```

    Today's libc++ uses the Clang builtin `__is_function(_Tp)` directly.

!!! impl "Where the implementation's extended types go"
    The standard specifies that integral types include extended integer types and floating-point types include extended floating-point types. With Clang 23 and libc++:

    - `is_integral_v<__int128>` and `is_integral_v<unsigned _BitInt(7)>` are both true; libc++ uses Clang's `__is_integral` builtin;
    - `is_floating_point_v<_Float16>` is false; libc++'s `is_floating_point` is specialized only for `float`, `double` and `long double`. libc++ does not provide `<stdfloat>` either.

    `_Float16` is a Clang extension, and the standard does not force implementations to treat it as an extended floating-point type, so this is not a violation.

## Composite type categories [meta.unary.comp]

¶1 The composite category predicates are combinations of the primary categories, corresponding to the definitions in [[basic.types]]. ¶2 They also ignore cv. Unlike the primary categories, they overlap; for example, `int*` is both a scalar type and a compound type.

| Predicate | Condition | Made up of which primary categories |
|---|---|---|
| `is_reference` | Reference | Lvalue references, rvalue references |
| `is_arithmetic` | Arithmetic type | Integral, floating-point |
| `is_fundamental` | Fundamental type | Arithmetic, `void`, `nullptr_t`, `meta::info` |
| `is_object` | Object type ([[basic.types.general#6]]) | Everything except functions, references and `void` |
| `is_scalar` | Scalar type | Arithmetic, enumerations, pointers, member pointers, `nullptr_t`, `meta::info` |
| `is_compound` | Compound type ([[basic.compound]]) | Everything except fundamental types |
| `is_member_pointer` | Member pointer | Pointers to data members, pointers to member functions |

```cpp title="composite-categories.cpp" run ok
#include <cstddef>
#include <type_traits>

enum E { e };
struct S { int m; };

static_assert(!std::is_arithmetic_v<E> && !std::is_integral_v<E>);
static_assert( std::is_scalar_v<E>);
static_assert( std::is_fundamental_v<void> && !std::is_object_v<void>);
static_assert( std::is_object_v<int[]>);
static_assert(!std::is_object_v<int&> && std::is_compound_v<int&>);
static_assert( std::is_scalar_v<int S::*> && std::is_scalar_v<std::nullptr_t>);
static_assert(!std::is_scalar_v<int[1]>);

int main() {}
```

Points that are easy to get wrong:

- Enumerations are neither arithmetic types nor integral types, even though unscoped enumerations undergo integral promotion; but enumerations are scalar types.
- `void` is a fundamental type, not an object type. The array of unknown bound `int[]` is an object type, just incomplete.
- References are compound types, not object types.
- {{c++26}} `std::meta::info` is a scalar type ([[basic.types.general#7]]). Reflection values are copied and compared like integers or pointers, which is why they can be constant template arguments.

## Type property queries [meta.unary.prop.query]

¶1–¶2 These three templates are also *Cpp17UnaryTypeTrait*s, but their base characteristic is `integral_constant<size_t, Value>` and the result is a number:

| Template | Value |
|---|---|
| `alignment_of<T>` | `alignof(T)`; *Mandates*: `alignof(T)` is a valid expression ([[expr.alignof]]) |
| `rank<T>` | The number of dimensions of an array; 0 if not an array |
| `extent<T, I = 0>` | The bound of dimension `I` (counting from 0); 0 if `T` is not an array, its rank is not greater than `I`, or `I` is 0 and `T` is an array of unknown bound |

```cpp title="rank-extent.cpp" run ok
#include <type_traits>

static_assert(std::rank_v<int> == 0);
static_assert(std::rank_v<int[][4]> == 2);
static_assert(std::extent_v<int[2][4]> == 2);
static_assert(std::extent_v<int[2][4], 1> == 4);
static_assert(std::extent_v<int[][4]> == 0);       // dimension 0 of unknown bound
static_assert(std::extent_v<int[][4], 1> == 4);
static_assert(std::extent_v<int[3][4], 2> == 0);   // not enough dimensions
static_assert(std::alignment_of_v<int&> == alignof(int));
static_assert(std::alignment_of_v<int[]> == alignof(int));

int main() {}
```

The standard examples in ¶3–¶4 are similar. A few remarks:

- `alignment_of` predates the `alignof` operator; today just write `alignof(T)`. By its *Mandates*, `alignment_of<void>` and `alignment_of<void()>` are ill-formed; `alignment_of<int&>` is valid with the value `alignof(int)`, because `alignof` applied to a reference type gives the alignment of the referenced type; the value of `alignment_of<int[]>` is the element's alignment.
- `rank` and `extent` only recognize built-in arrays; `rank_v<std::array<int, 3>>` is 0.
- `extent` uses 0 for "not an array", "out of range" and "unknown bound" alike; to distinguish them, combine it with `is_bounded_array` and `is_unbounded_array` ([[meta.unary.prop]]).

The C++26 reflection library has corresponding `consteval` functions `std::meta::rank` and `std::meta::extent`. `std::meta::alignment_of` applies more broadly and also accepts reflections of data members and variables ([[meta.reflection.queries]]).

## Common mistakes

!!! pitfall "`is_pointer` does not recognize smart pointers or member pointers"
    `is_pointer_v<std::unique_ptr<int>>` is false, since it is a class type; `is_pointer_v<int S::*>` is also false, since member pointers are a separate primary category. Generic code that means "something that can be dereferenced" should use a concept such as `std::indirectly_readable`.

## Questions

!!! question "Question"
    For which types `T` are `std::is_fundamental_v<T>` and `std::is_compound_v<T>` both false?

<details markdown="1">
<summary>Answer</summary>

There are no such types. [[basic.compound]] classifies every type other than the fundamental types as a compound type, and the 15 primary categories split exactly into fundamental (`void`, `nullptr_t`, integral, floating-point, `meta::info`) and compound (the rest). So `is_compound_v<T> == !is_fundamental_v<T>` holds for every type.
</details>

## Summary

| Group | Key points |
|---|---|
| Primary categories (15) | Pairwise exclusive, covering all types; ignore cv; `is_reflection` is new in C++26 |
| Composite categories (7) | Combinations of primary categories, can overlap; enumerations are not arithmetic but are scalar |
| Property queries | `alignment_of` equals `alignof`; `rank` and `extent` only recognize built-in arrays and give 0 for unknown bounds and out-of-range dimensions |
