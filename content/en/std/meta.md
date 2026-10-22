---
title: Metaprogramming library
summary: "A guide to Chapter 21: compile-time integer sequences, <type_traits>, C++26 static reflection in <meta>, and compile-time rationals in <ratio>, plus how the two generations of metaprogramming interfaces differ."
updated: 2026-10-19
---

!!! tldr
    - Everything in Chapter 21 works at compile time: querying properties of types, turning one type into another, carrying integers and rationals in types, and C++26 static reflection.
    - `<type_traits>` is a class template interface: template arguments are the input, and `::value` or `::type` is the output.
    - C++26's `<meta>` is a value interface: the reflection value `std::meta::info` is input and output, and queries are ordinary `consteval` functions.
    - Most traits just turn definitions that already exist in the core language (trivially copyable, aggregate, convertible, ...) into something code can query, so understanding a trait starts with understanding the corresponding core rule.

## Four parts

¶1 The chapter consists of four subclauses:

| Subclause | Header | Contents |
|---|---|---|
| [[intseq]] | `<utility>` | `integer_sequence`, `make_index_sequence`: encoding 0..N-1 into a type for a function template to deduce as a parameter pack |
| [[type.traits]] | `<type_traits>` | Type categories, type properties, type relationships, type transformations, logical composition, member relationships, the constant evaluation context |
| [[meta.reflection]] | `<meta>` | {{c++26}} The static reflection library: queries on `std::meta::info`, member enumeration, `substitute`, `define_aggregate` |
| [[ratio]] | `<ratio>` | `std::ratio<N, D>`: exact compile-time rationals, on which the units of `<chrono>` are built |

`integer_sequence` is declared in `<utility>`, not `<type_traits>`. The first line of the synopses of `<type_traits>` and `<ratio>` reads `// all freestanding`: a freestanding implementation (one that does not depend on an operating system; see [[g:freestanding-implementation]]) must provide them in full too, because they need no run-time support at all.

## Two generations of interface

Two generations of design sit side by side in this chapter.

The first generation is `<type_traits>`, using class templates as compile-time functions. The input of `std::is_trivially_copyable<T>` is the template argument, and the output is the static member `value` in the base class `integral_constant<bool, v>`; the output of `std::remove_cv<T>` is the nested type `type`. Branching is done with partial specialization or SFINAE, looping with recursive instantiation. The [[type.traits]] page covers the three standard shapes of this interface.

The second generation is C++26's `<meta>`. `std::meta::info` is a scalar type ([[basic.fundamental]]), `^^T` produces a value of it ([[expr.reflect]]), and `[: r :]` splices it back into code ([[basic.splice]]). The functions in `<meta>` are all ordinary `consteval` functions taking `info` and returning `bool`, `info` or `vector<info>`, and can be processed with `for` loops and `ranges` algorithms. [[meta.reflection.traits]] also provides a corresponding function for each first-generation trait.

```cpp
// first generation: types in, a type or bool out
static_assert(std::is_same_v<std::remove_cvref_t<const int&>, int>);

// second generation: reflection values in, reflection values out
static_assert(std::meta::remove_cvref(^^const int&) == ^^int);
```

The second assertion has not been compiled: Clang 23 does not support reflection, and libc++ has no `<meta>` header.

One generation does not replace the other. Most `<type_traits>` traits are thin wrappers around compiler builtins, cheap to instantiate, and remain the workhorse of everyday generic code. Reflection solves problems traits cannot express: enumerating the members of a class, reading the names of declarations, generating a new class from a description.

## Traits restate the core language

This chapter rarely defines new concepts. Most traits turn some definition in the core language into a queryable interface:

| Library component | Corresponding core rule |
|---|---|
| `is_trivially_copyable`, `is_standard_layout`, `is_implicit_lifetime` | [[basic.types.general#7]], [[class.prop]] |
| `is_aggregate` | [[dcl.init.aggr]] |
| `is_structural` | Structural types in [[temp.param]] |
| `is_layout_compatible`, `is_pointer_interconvertible_base_of` | Layout compatibility in [[basic.types]], pointer-interconvertibility in [[basic.compound]] |
| `is_constructible`, `is_convertible` | Whether a hypothetical variable definition or `return` statement is well-formed ([[dcl.init]], [[stmt.return]]) |
| `common_type` | The result type of the conditional operator `?:` ([[expr.cond]]) |
| `reference_constructs_from_temporary` | Reference binding and lifetime extension of temporaries ([[class.temporary]]) |
| `is_constant_evaluated`, `is_within_lifetime` | Constant evaluation ([[expr.const]]) and lifetime ([[basic.life]]) |
| `std::meta::*` | [[expr.reflect]], [[basic.splice]] |

So when reading a trait, first pin down the core definition it corresponds to, then look at where the library wording departs from intuition. For example, `is_signed<E>` is always `false` for an enumeration, and on Clang `is_nothrow_constructible` also depends on the destructor.

## Evolution

!!! history
    - C++11 adopted the type traits from TR1, establishing the interface of an `integral_constant` base plus `::value` and `::type`, and added `<ratio>`, `declval`, `common_type` and the `is_constructible` family that depends on new language features.
    - C++14 added the `_t` alias templates (`remove_cv_t<T>`) and `integer_sequence`.
    - C++17 added the `_v` variable templates, `void_t`, `conjunction` / `disjunction` / `negation`, `is_aggregate` and `has_unique_object_representations`, and replaced `result_of` with `is_invocable` / `invoke_result`.
    - C++20 added `remove_cvref`, `type_identity`, `common_reference`, `is_constant_evaluated`, and the layout-compatibility and pointer-interconvertibility families, and deprecated `is_pod`.
    - C++23 added `is_scoped_enum`, `reference_constructs_from_temporary` and `is_implicit_lifetime`.
    - C++26 added `is_virtual_base_of`, `is_within_lifetime` and static reflection in `<meta>` ([[P2996R13]]), deprecated `is_trivial` ([[P3247R2]]), and gave `integer_sequence` structured binding support.

## Page index

1. [[intseq]]: `integer_sequence`, `make_integer_sequence`, and C++26 structured binding support;
2. [[type.traits]]: the three shapes of a trait, the no-specialization and incomplete-type rules, `integral_constant`;
3. [[meta.unary]]: primary type categories, composite type categories, `rank` / `extent` / `alignment_of`;
4. [[meta.unary.prop]]: type properties, including the precise definition of `is_constructible` and its trivial and nothrow variants;
5. [[meta.rel]]: `is_same`, `is_base_of`, `is_convertible`, `is_invocable`, layout compatibility;
6. [[meta.trans]] and [[meta.trans.other]]: the type transformations, `decay`, `common_type`, `common_reference`;
7. [[meta.logical]], [[meta.member]], [[meta.const.eval]];
8. [[meta.reflection]] and its subpages: the C++26 reflection library;
9. [[ratio]].
