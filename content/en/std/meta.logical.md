---
title: Logical operator traits
summary: "conjunction, disjunction and negation compute AND, OR and NOT over type traits; the first two stop instantiating later arguments once an argument decides the result, and use that argument itself as their base class."
updated: 2026-10-19
---

!!! tldr
    - `conjunction` and `disjunction` short-circuit: after the first argument that decides the result, the `::value` of later arguments is not instantiated. The fold expression `(B::value && ...)` cannot do this.
    - The base class of `conjunction<B...>` is the first `Bi` that is false, or the last argument if all are true; it is not necessarily `true_type` or `false_type`. `disjunction` is symmetric.
    - For an empty pack, `conjunction_v<>` is true and `disjunction_v<>` is false.
    - `negation<B>` is just `bool_constant<!bool(B::value)>`; its role is to express negation as a type that can go into the argument list of `conjunction`.
    - In C++20 constraints, `&&` and `||` short-circuit by themselves, and these templates are usually unnecessary.

[meta.logical] provides three templates that perform logical operations on other type traits (paragraph 1): `conjunction` (AND), `disjunction` (OR) and `negation` (NOT). They were added in C++17 by [[P0013R1]].

## Why not just use a fold expression

```cpp run title="short-circuit.cpp" ok
#include <type_traits>

template<class T>
struct Bad {  // an error as soon as it is instantiated
  static_assert(sizeof(T) == 0, "instantiated!");
  static constexpr bool value = true;
};

static_assert(!std::conjunction_v<std::false_type, Bad<int>>);
static_assert( std::disjunction_v<std::true_type, Bad<int>>);

int main() {}
```

As soon as `Bad<int>` is instantiated, the `static_assert` in it fails. Both assertions above pass, because the first argument already decides the result, and `conjunction` and `disjunction` do not instantiate `Bad<int>`.

A fold expression does not work:

```cpp error
#include <type_traits>

template<class T>
struct Bad {
  static_assert(sizeof(T) == 0, "instantiated!");
  static constexpr bool value = true;
};

template<class... B>
constexpr bool fold_and = (B::value && ...);

static_assert(!fold_and<std::false_type, Bad<int>>);  // error
```

The fold expression does short-circuit when evaluated, but merely writing the expression `Bad<int>::value` requires class member lookup and therefore implicitly instantiates `Bad<int>` ([[temp.inst]]). Short-circuiting happens at evaluation, which is too late.

What `conjunction` short-circuits is template instantiation. Instantiation may fail, may be expensive, or may have side effects, so this matters in practice. A typical use is `conjunction<is_reference<T>, is_constructible<Foo, T>>`: when the first is false, the second may involve incomplete types or trigger errors, and should not be instantiated.

## `conjunction`

¶2–3 specify: `conjunction<B1, …, BN>` computes the logical AND of its arguments; if `bool(Bi::value)` is false for some `Bi`, instantiating `conjunction<B1, …, BN>::value` does not require instantiating `Bj::value` for any `j > i`. Note 1 points out that this is analogous to the short-circuiting of the built-in `&&`.

### The base class

¶5 does not simply say that `conjunction` derives from `true_type` or `false_type`; it specifies its base class:

!!! std
    The specialization `conjunction<B1, …, BN>` has a public and unambiguous base that is either the first type `Bi` in the list `true_type, B1, …, BN` for which `bool(Bi::value)` is `false`, or if there is no such `Bi`, the last type in the list.

That is, find the first type with a false value in the list `true_type, B1, …, BN`, and that is the base; if there is none, the last type is the base (Note 2). From this it follows:

- The list of `conjunction<>` contains only `true_type`, so `conjunction_v<>` is true.
- At the first false `Bi`, the base is `Bi` itself, and all of `Bi`'s members are accessible through `conjunction`, not just `value`.
- When all are true, the base is the last argument. The type of `conjunction<integral_constant<int, 7>>::value` is `const int`, and its value is 7.

```cpp run title="conjunction-base.cpp" ok
#include <type_traits>

using Zero  = std::integral_constant<int, 0>;
using Seven = std::integral_constant<int, 7>;
using C = std::conjunction<std::true_type, Zero, Seven>;

static_assert(std::conjunction_v<>);
static_assert(std::is_base_of_v<Zero, C>);  // the first false one
static_assert(std::is_same_v<decltype(std::conjunction<Seven>::value),
                             const int>);
static_assert(std::conjunction<Seven>::value == 7);

int main() {}
```

¶6 requires that the member names of the base not be hidden in `conjunction` and be usable unambiguously. The exceptions are two names, `conjunction` and `operator=`: the former is `conjunction`'s own injected-class-name, which necessarily hides the base's injected-class-name; the latter is the assignment operator every class implicitly declares.

### Requirements on the arguments

¶4 requires that every `Bi` whose `::value` is instantiated be usable as a base class and have a member `value` convertible to `bool`, not hidden and unambiguously accessible. Arguments skipped by short-circuiting are not subject to these constraints.

The "usable as a base class" condition excludes `final` classes. By paragraph 5, `conjunction<F>` would have `F` as its base, so for `struct F final : std::true_type {};`, libc++ (with Clang 23) reports an error at `conjunction_v<F>`, pointing out that the base `F` is marked `final`.

## `disjunction`

`disjunction` is symmetric to `conjunction` (paragraphs 7–11):

- If `bool(Bi::value)` is true for some `Bi`, later `Bj::value` need not be instantiated (paragraph 8; Note 3 draws the analogy with the built-in `||`).
- The base is the first type with a true value in the list `false_type, B1, …, BN`, or the last type if there is none (paragraph 10), so `disjunction_v<>` is false.
- The requirements on the arguments and on member visibility are the same as for `conjunction` (paragraphs 9 and 11).

Since the base is the first true argument, `disjunction` can be used to find the first element satisfying a condition at compile time. As long as each argument carries extra members, the information of the match can be retrieved through `disjunction`:

```cpp run title="disjunction-find.cpp" ok
#include <type_traits>

template<class T>
struct Match : std::is_integral<T> {
  using type = T;  // hides integral_constant's type
};

using First =
    std::disjunction<Match<float>, Match<long>, Match<int>>::type;
static_assert(std::is_same_v<First, long>);

int main() {}
```

`Match<float>` has value false and `Match<long>` true, so the base of the `disjunction` is `Match<long>`, and `::type` is `long`. `Match<int>` is never instantiated.

## `negation`

¶12: `negation<B>` is a unary type trait with base characteristic `bool_constant<!bool(B::value)>`. It always derives from `true_type` or `false_type`, and it instantiates `B::value`.

The point of `negation` is to express negation as a type as well, so it can go into the argument list of `conjunction` or `disjunction` and take part in short-circuiting, for example `conjunction<is_class<T>, negation<is_final<T>>>`.

!!! impl "The libc++ implementation"
    libc++'s `conjunction` is almost a literal translation of paragraph 5:

    ```cpp
    template <class...>
    struct conjunction : true_type {};
    template <class _Arg>
    struct conjunction<_Arg> : _Arg {};
    template <class _Arg, class... _Args>
    struct conjunction<_Arg, _Args...>
        : conditional_t<!bool(_Arg::value), _Arg, conjunction<_Args...>> {};
    ```

    Both branches of `conditional_t` are written out, but naming `conjunction<_Args...>` does not instantiate it; it is instantiated only when chosen as the base. So the recursion stops at the first false `_Arg`.

## Relation to constraints

In `requires` clauses and concept definitions, `&&` and `||` form conjunctions and disjunctions of constraints ([[temp.constr]]), and checking constraint satisfaction short-circuits by itself. The constraint `std::is_integral_v<T> && Bad<T>::value` does not instantiate `Bad<double>` when `T = double`.

So `conjunction` is usually unnecessary in C++20 constraints. It is mainly used in other places where types are computed: base class lists, `enable_if` arguments, `static_assert`.

## Questions

!!! question "Question"
    What observable differences are there between `std::conjunction<std::is_integral<T>, std::is_signed<T>>` and `std::bool_constant<std::is_integral_v<T> && std::is_signed_v<T>>`?

<details markdown="1">
<summary>Answer</summary>

Their `::value` is the same; they differ in two ways.

First, the base classes differ. The base of the former is `is_integral<T>` (when it is false) or `is_signed<T>`; it is not itself `true_type` or `false_type`, only indirectly derived from one of them. So `std::is_same_v<..., std::true_type>` is always false for the former, and true for the latter when the condition holds.

Second, instantiation differs. The former does not instantiate `is_signed<T>::value` when `is_integral<T>` is false; the latter necessarily instantiates it by writing `std::is_signed_v<T>`. For these two traits it makes no difference, but if the second item could cause an error, only the former is safe.
</details>

## Quick reference

| Template | Short-circuit | Base class | Empty pack |
|---|---|---|---|
| `conjunction<B...>` | Stops at the first false argument | The first false `Bi`, otherwise the last | `true_type` |
| `disjunction<B...>` | Stops at the first true argument | The first true `Bi`, otherwise the last | `false_type` |
| `negation<B>` | Not applicable | `bool_constant<!bool(B::value)>` | Not applicable |
