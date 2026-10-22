---
title: Metaprogramming and type traits
summary: "The general rules of <type_traits>: the three shapes of a trait and the base characteristic, why specializing a trait is undefined behavior, the two layers of rules for incomplete types, the header synopsis, and integral_constant."
updated: 2026-10-19
---

!!! tldr
    - A predicate trait (such as `is_integral<T>`) derives from `true_type` or `false_type` but is itself a different class; a transformation trait (such as `remove_cv<T>`) provides a nested type `type`.
    - Apart from a few explicitly permitted exceptions (`common_type`, `basic_common_reference`), adding specializations of a trait is undefined behavior; libc++ turns it into a compile error.
    - Traits can by default be instantiated with incomplete types, but if the answer could differ once the type is completed, the program has undefined behavior; many traits additionally require their arguments to be complete.
    - `integral_constant<T, v>` is the foundation of all predicate traits: `value`, `type`, implicit conversion to the value, and `operator()`.

## What a trait is

```cpp title="integral-constant.cpp" run ok
#include <cstdio>
#include <type_traits>

using five = std::integral_constant<int, 5>;
static_assert(five{} + five{} == 10);       // implicit conversion to int
static_assert(std::is_integral<int>{}());   // operator()

template<class T> void kind(std::true_type)  { std::puts("integral"); }
template<class T> void kind(std::false_type) { std::puts("not integral"); }

int main() {
    kind<int>(std::is_integral<int>{});      // derived-to-base conversion to true_type
    kind<double>(std::is_integral<double>{});
}
```

A **type trait** is a class template that answers a question about types at compile time. The answer of `is_integral<int>` lives in its base class `true_type`; passing an `is_integral<T>` object to overloads that take `true_type` and `false_type` respectively selects an implementation by type. This technique is called **tag dispatch**.

[type.traits.general] ¶1 summarizes the uses of traits: supporting as many types as possible in templates, optimizing template code (the classic example is using `memcpy` for trivially copyable types), detecting type-related errors at compile time, and performing type inference and transformation. It also divides traits into three groups:

- type categorization: placing every C++ type into a complete classification and answering which category a given type belongs to; see [[meta.unary]];
- type property inspection: checking properties of a single type or a combination of types; see [[meta.unary.prop]], [[meta.rel]];
- type transformation: modifying certain properties of a type; see [[meta.trans]].

¶2 All functions specified in [type.traits] are signal-safe ([[support.signal]]) and can be called in a signal handler. The functions meant here are real functions such as `is_constant_evaluated`, and the member functions of `integral_constant`.

## Three shapes [meta.rqmts]

The standard describes the interface of traits with three named requirements:

| Requirement | Purpose | Shape |
|---|---|---|
| ¶1 *Cpp17UnaryTypeTrait* | A property of one type | One type argument (possibly with auxiliary arguments, such as `extent<T, I>`), derived from its base characteristic |
| ¶2 *Cpp17BinaryTypeTrait* | A relationship between two types | Two type arguments (possibly with auxiliary arguments), derived from its base characteristic |
| ¶3 *Cpp17TransformationTrait* | Modifying a type | One type argument (possibly with auxiliary arguments), with a public nested type `type` naming the modified type |

The **base characteristic** ([[g:base-characteristic]]) is a specialization `integral_constant<T, v>`, where `T` and `v` are determined by the specific trait. The base characteristic of `is_trivially_copyable<T>` is `true_type` or `false_type`; that of `rank<int[2][3]>` is `integral_constant<size_t, 2>`.

Traits of the first two kinds must be default constructible and copy constructible, which is why `std::is_integral<int>{}` can be written. They must derive publicly and unambiguously from their base characteristic, and the member names of the base characteristic must not be hidden, so `::value`, `::type` and `::value_type` always reach the base characteristic's versions.

The requirements only say that a trait derives from its base characteristic, not that the trait is its base characteristic:

```cpp title="base-characteristic.cpp" run ok
#include <type_traits>

// the trait itself is a different class
static_assert(!std::is_same_v<std::is_same<int, int>, std::true_type>);
// ::type is the base characteristic
static_assert( std::is_same_v<std::is_same<int, int>::type, std::true_type>);
static_assert( std::is_base_of_v<std::true_type, std::is_same<int, int>>);

int main() {}
```

So the tag dispatch above relies on a derived-to-base conversion, not an exact match.

Several transformation traits in [[meta.trans.other]] have no `type` member in some cases, for example `enable_if<false>`, `common_type` with no common type, and `underlying_type<int>`. Accessing a nonexistent `type` during substitution causes deduction failure rather than an error, which is why they can be used for SFINAE.

## No specializations (¶4)

!!! std
    Unless otherwise specified, the behavior of a program that adds specializations for any of the templates specified in [type.traits] is undefined.

¶4 Adding specializations for any template in [type.traits] is undefined behavior unless otherwise specified.

This is stricter than the general rule of [[namespace.std]]. Normally users may add specializations of standard library class templates that depend on their own types (such as `std::hash<MyType>`), but not of traits. A trait's answer is determined by core language rules; if users were allowed to lie, for example claiming that a class with virtual functions is trivially copyable, the library code relying on it (`std::copy` going through `memmove`) would produce real UB.

The only exceptions "otherwise specified" are two, both in [[meta.trans.other]]:

- `common_type<T1, T2>`: may be specialized for types that are unchanged by decay (`is_same_v<T, decay_t<T>>`), with at least one argument a program-defined type;
- `basic_common_reference<T, U, TQual, UQual>`: may be specialized to influence the result of `common_reference`.

Variable templates such as `is_integral_v` cannot be specialized either. [[namespace.std]] specifies that, unless explicitly allowed, adding specializations of standard library variable templates is undefined behavior.

```cpp title="no-specialize.cpp" run error
#include <type_traits>

struct My {};
template<> struct std::is_trivially_copyable<My>  // error: forbidden by libc++
    : std::false_type {};
template<> inline constexpr bool
    std::is_integral_v<My> = true;                 // error: forbidden by libc++
template<> struct std::common_type<My, int> {
    using type = My;                               // OK: explicitly allowed by the standard
};

int main() {}
```

The standard only says this is UB and requires no diagnostic. libc++ marks almost every trait with Clang's `[[clang::no_specializations]]` attribute, so the first two specializations get a `'is_trivially_copyable' cannot be specialized` error. This diagnostic belongs to the error-by-default warning group `-Winvalid-specialization`.

## Incomplete types (¶5)

The rules for incomplete types come in two layers.

The first layer is each trait's own preconditions. In the tables of [[meta.unary.prop]], [[meta.rel]] and [[meta.trans.other]], most traits have a *Preconditions* column, typically worded as `T` shall be a complete type, *cv* `void`, or an array of unknown bound. Violating a precondition of a library function or template is UB ([[structure.specifications#3.4]]).

The second layer is the umbrella rule of ¶5:

!!! std
    The behavior of a program is undefined if an instantiation of a template specified in [type.traits] directly or indirectly depends on an incompletely-defined object type `T`, and that instantiation could yield a different result were `T` hypothetically completed.

¶5 first specifies that, unless otherwise stated, the templates in [type.traits] may be instantiated with incomplete types. This is the opposite of the general rule in [[res.on.functions]], under which instantiating a library template with an incomplete type is UB. So `is_class_v<S>`, `is_same_v<S, int>` and `add_pointer_t<S>` are all fine for an `S` that is declared but not defined; completing it does not affect the answer.

¶5 then specifies that if an instantiation directly or indirectly depends on an incompletely-defined object type ([[g:incompletely-defined-object-type]], such as a class that is declared but not defined), and the result could be different were that type completed, the behavior is undefined.

This rule is needed because a template specialization is instantiated only once. At the first instantiation the compiler computes the answer from the information available then, and from then on the same specialization has that answer throughout the program. If the type is completed later, the old answer is wrong:

```cpp title="incomplete-trait.cpp" run ub
#include <cstdio>
#include <type_traits>

struct Base {};
struct Derived;                       // only declared, not defined, at this point

constexpr bool before =
    std::is_convertible_v<Derived*, Base*>;   // UB: the result depends on an incomplete type

struct Derived : Base {};             // now it is complete

constexpr bool after = std::is_convertible_v<Derived*, Base*>;

int main() {
    Derived d;
    Base* pb = &d;                    // the language itself allows this conversion
    std::printf("before=%d after=%d real=%d\n", before, after, pb != nullptr);
}
```

With Clang 23 and libc++ it prints `before=0 after=0 real=1`. The variable template specialization `is_convertible_v<Derived*, Base*>` is instantiated as `false` when first used, and asking again after `Derived` is completed gives the same specialization's `false`. `Derived*` itself is a complete type, so the first-layer precondition is not violated; it is ¶5 that makes this code UB.

!!! impl "How much the compiler catches"
    For first-layer preconditions, most of Clang's builtin traits report an error: incomplete type 'S' used in type trait expression; `is_trivially_copyable`, `is_constructible`, `is_base_of` and `is_empty` all do. But not all of them: in our tests, for an incomplete class `S`, `std::is_convertible_v<S, int>` silently yields `false`, even though it violates a precondition.

    Whether the second layer's answer would change after completion is in principle undetectable by the compiler, and the example above gets no diagnostic at all.

## The header synopsis [meta.type.synop]

The synopsis begins with `// all freestanding`, so freestanding implementations must provide it in full. Grouped by subclause:

| Group | Representative members | Page |
|---|---|---|
| Helper classes | `integral_constant`, `bool_constant`, `true_type`, `false_type` | See [meta.help] below |
| Primary type categories | `is_void` … `is_function`, `is_reflection` | [[meta.unary]] |
| Composite type categories | `is_reference`, `is_arithmetic`, `is_object`, `is_scalar` … | [[meta.unary]] |
| Type properties | `is_const`, `is_aggregate`, the `is_constructible` family, the `is_assignable` family, the `is_destructible` family, `has_unique_object_representations` … | [[meta.unary.prop]] |
| Type property queries | `alignment_of`, `rank`, `extent` | [[meta.unary]] |
| Type relations | `is_same`, `is_base_of`, `is_convertible`, the `is_invocable` family … | [[meta.rel]] |
| Type transformations | `remove_const`, `add_lvalue_reference`, `make_signed`, `decay`, `common_type`, `void_t` … | [[meta.trans]], [[meta.trans.other]] |
| Logical operators | `conjunction`, `disjunction`, `negation` | [[meta.logical]] |
| Member relationships | `is_pointer_interconvertible_with_class`, `is_corresponding_member` | [[meta.member]] |
| Constant evaluation context | `is_constant_evaluated`, `is_within_lifetime` | [[meta.const.eval]] |

Naming conventions:

- Every transformation trait `X` has an alias template `X_t<T>` equal to `X<T>::type` (since C++14).
- Every predicate and query trait has a variable template `X_v<...>` equal to `X<...>::value` (since C++17).
- `void_t` is the only alias without a corresponding class template: `template<class...> using void_t = void;`. Its purpose is to make argument substitution failures trigger SFINAE.
- The deprecated `is_trivial`, `is_pod`, `aligned_storage` and `aligned_union` are not in this synopsis but in [[depr.meta.types]] in Annex D. `is_trivial` was deprecated in C++26 ([[P3247R2]]). libc++ still provides them, with a `-Wdeprecated-declarations` warning on use.

## `integral_constant` [meta.help]

```cpp
namespace std {
  template<class T, T v> struct integral_constant {
    static constexpr T value = v;
    using value_type = T;
    using type = integral_constant<T, v>;
    constexpr operator value_type() const noexcept { return value; }
    constexpr value_type operator()() const noexcept { return value; }
  };
  template<bool B> using bool_constant = integral_constant<bool, B>;
  using true_type  = bool_constant<true>;
  using false_type = bool_constant<false>;
}
```

¶1 These types are used as base classes to define a uniform interface for the various traits. Points of note in the design:

- `type` refers to itself. So taking `::type` is idempotent, and `is_same<A, B>::type` is exactly the base characteristic.
- The conversion function `operator value_type()` lets an object convert implicitly to its value, so both `if (std::is_integral<T>{})` and `five{} + five{}` can be written.
- `operator()()` lets a trait object be passed around as a nullary callable.
- `value` is a `static constexpr` data member, implicitly an inline variable since C++17, so no out-of-class definition is needed.

## Implementation: traits wrap compiler builtins

Traits that need to know a class's internals (whether it is trivial, standard-layout, constructible) cannot be implemented with pure C++ templates before reflection; only the compiler can provide them. In libc++'s `__type_traits/` directory, the vast majority of traits forward directly to Clang builtins:

| Trait | libc++ implementation |
|---|---|
| `is_trivially_copyable` | `__is_trivially_copyable(_Tp)` |
| `is_constructible` | `__is_constructible(_Tp, _Args...)` |
| `is_convertible` | `__is_convertible(_T1, _T2)` |
| `is_same` | `__is_same(_Tp, _Up)` |
| `decay` | `__decay(_Tp)` |
| `make_integer_sequence` | `__make_integer_seq<...>` |

Traits like `is_same` and `decay`, which could be written as pure templates, also use builtins, for compilation speed: a builtin does not need to instantiate any class template.

## Common mistakes

!!! pitfall "Compiling is not the same as being correct"
    When a first-layer precondition is violated Clang usually reports an error, which makes it easy to assume the compiler will always catch it. But a few traits such as `is_convertible` silently give an answer, and the second-layer rule gets no diagnostic at all. Asking `is_convertible` or `is_base_of` about pointers to a class that is only forward-declared in a header is a bug that has occurred in real projects.

!!! pitfall "Do not specialize a trait to fix its result"
    To make `is_trivially_copyable<MyType>` true (say, so that some container uses `memcpy`), the correct approach is to make `MyType` actually trivially copyable, for example by defaulting all its special member functions. Specializing the trait directly is UB, and a compile error with libc++.

## Questions

!!! question "Question 1"
    What are `std::is_same_v<std::true_type, std::integral_constant<bool, true>>` and `std::is_same_v<std::true_type, std::is_void<void>>`?

<details markdown="1">
<summary>Answer</summary>

The first is `true`: `true_type` is an alias for `bool_constant<true>`, i.e. `integral_constant<bool, true>` ([meta.help]). The second is `false`: `is_void<void>` merely derives from its base characteristic `true_type` ([meta.rqmts] ¶1) and is itself a different class; `is_void<void>::type` is `true_type`.
</details>

!!! question "Question 2"
    Is `struct S; static_assert(std::is_class_v<S>);` the UB described in [meta.rqmts] ¶5? What about `std::is_empty_v<S>`?

<details markdown="1">
<summary>Answer</summary>

`is_class_v<S>` is fine: `is_class` has no completeness precondition, `S` is still a class after completion, the result cannot change, and the condition of ¶5.2 is not met.

`is_empty_v<S>` violates the precondition in the [[meta.unary.prop]] table that a non-union class type must be complete; this is the first layer, and it is UB. Clang reports an error here: incomplete type 'S' used in type trait expression.
</details>

## Summary

| Rule | Key points |
|---|---|
| Three shapes | Predicate traits derive from an `integral_constant` base characteristic; transformation traits provide `type` |
| ¶4 No specializations | UB by default; the exceptions are `common_type` and `basic_common_reference`; `_v` variable templates cannot be specialized either |
| ¶5 Incomplete types | Allowed by default; UB if the result could differ after completion; each trait also has its own completeness preconditions |
| `integral_constant` | `value`, `value_type`, `type` (itself), implicit conversion, `operator()` |
