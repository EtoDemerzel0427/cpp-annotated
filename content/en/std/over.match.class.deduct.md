---
title: Class template argument deduction
summary: "How CTAD works: the constructors, deduction guides and so on of a class template are turned into a set of function templates, ordinary deduction and overload resolution run over them, and the return type of the winner is the deduced type."
updated: 2026-10-19
---

!!! tldr
    - CTAD has no deduction algorithm of its own: each constructor is translated into a function template returning `C<…>`, ordinary template argument deduction and overload resolution are performed on this set of function templates, and the return type of the winner is the deduced type.
    - This set of function templates is called the guides; they come from constructors, the copy deduction candidate `C(C<T>)`, user-written deduction guides, the aggregate deduction candidate of C++20, and the inherited constructors of C++23.
    - A `T&&` in a constructor (where `T` is a parameter of the class template) isn't a forwarding reference in CTAD and can't be deduced from an lvalue.
    - `std::vector v{other_vector}` is a copy, not nesting: when the braces contain a single object of the same class, the `initializer_list` phase is skipped.
    - User-written deduction guides beat implicit guides in a tie; written carelessly, they can turn a copy into nesting.

```cpp run ok
#include <utility>
#include <vector>
#include <type_traits>
int main() {
  std::pair p(1, 2.0);
  std::vector v{1, 2, 3};
  static_assert(std::is_same_v<decltype(p), std::pair<int, double>>);
  static_assert(std::is_same_v<decltype(v), std::vector<int>>);
}
```

`std::pair p(1, 2.0)` has no template arguments, and the compiler deduces `std::pair<int, double>`. This is **class template argument deduction** (CTAD, [[P0091R3]]), introduced in C++17. For when CTAD is triggered, see [[dcl.type.class.deduct]]; for the syntax of deduction guides, see [[temp.deduct.guide]].

CTAD reuses existing machinery. It translates the constructors of a class template into a set of function templates called **guides**, then performs ordinary function template argument deduction and overload resolution on them. The return type of the winning function template is the deduced type. So CTAD automatically inherits all the rules of overload resolution, including the unintuitive ones.

## Where the guides come from (¶1)

¶1 When a deduced class type placeholder (a class template name without template arguments, or {{c++26}} a *splice-type-specifier*) designates a primary class template `C`, the guides of `C` comprise the following.

### One function template per constructor (¶1.1)

¶1.1 If `C` is defined, each of its constructors yields a function template:

- whose template parameters are the template parameters of `C` followed by the constructor's own template parameters (including default template arguments);
- whose associated constraints are the conjunction of the constraints of `C` and those of the constructor, with `C`'s checked first (Note 1);
- whose parameter list is the constructor's parameter list;
- whose return type is `C<…>` with the template parameters of `C` as arguments.

```cpp
template<class T, class U> struct pair {
  pair(const T&, const U&);
  template<class X, class Y> pair(X&&, Y&&);
};
// The corresponding guides (schematic):
template<class T, class U>                   auto G1(const T&, const U&) -> pair<T, U>;
template<class T, class U, class X, class Y> auto G2(X&&, Y&&)         -> pair<T, U>;
```

`T` and `U` of `G2` don't appear in its parameters and can't be deduced from the arguments, so deduction fails for `pair p(1, 2.0)` and it doesn't become a candidate. For `pair p("a", 1)`, `G1` would deduce `pair<char[2], int>` with an array type. That is why the standard library additionally provides the deduction guide `pair(T1, T2) -> pair<T1, T2>`, whose by-value parameters make arrays decay to pointers, deducing `pair<const char*, int>`.

### Default construction and the copy deduction candidate (¶1.2–¶1.3)

¶1.2 If `C` isn't defined or declares no constructors, a guide is generated in the same way from a hypothetical constructor `C()`.

¶1.3 In addition, a guide is always generated from a hypothetical constructor `C(C)`, called the **[[g:copy-deduction-candidate|copy deduction candidate]]**:

```cpp
template<class T> auto G_copy(C<T>) -> C<T>;
```

Because of it, initializing from a `C<X>` deduces `C<X>`, not `C<C<X>>`.

### User-written deduction guides (¶1.4)

¶1.4 Each *deduction-guide* yields a function (template) whose template-head and parameter list come from the deduction guide and whose return type is the type after `->`.

```cpp run ok
#include <vector>
#include <type_traits>
int main() {
  std::vector<int> src{1, 2, 3};
  std::vector v(src.begin(), src.end());
  static_assert(std::is_same_v<decltype(v), std::vector<int>>);
}
```

In the guide generated from the constructor `vector(InputIt, InputIt)`, the element type `T` can't be deduced. CTAD succeeds only because the standard library provides the deduction guide `vector(It, It) -> vector<iter-value-type<It>>`.

### The aggregate deduction candidate {{c++20}}

```cpp run ok
#include <type_traits>
template<class T> struct Agg { T a; T b; };
template<class T, class U> struct Two { T a; U b; };
int main() {
  Agg x{1, 2};     // equivalent to the guide template<class T> Agg<T> G(T, T)
  Two y{1, 2.0};   // equivalent to template<class T, class U> Two<T, U> G(T, U)
  static_assert(std::is_same_v<decltype(x), Agg<int>>);
  static_assert(std::is_same_v<decltype(y), Two<int, double>>);
}
```

An aggregate class has no constructors, so in C++17 using CTAD with it required a hand-written deduction guide. [[P1816R0]] and [[P2082R1]] in C++20 added the **[[g:aggregate-deduction-candidate|aggregate deduction candidate]]**.

The second half of ¶1 says this candidate is added when all of the following hold: `C` is defined and satisfies the requirements of an aggregate class (assuming any dependent base class has no virtual functions and no virtual base classes), the initializer is a non-empty braced list or parenthesized expression list, and `C` has no deduction guides.

It is built as follows: for each element `xi` of the initializer list, find the element `ei` that it would initialize under aggregate initialization ([[dcl.init.aggr]]), then generate a guide from a hypothetical constructor `C(T1, …, Tn)`, where `Ti` is generally the declared type of `ei` (¶1.10). If some `xi` has no corresponding element, the candidate isn't added. Finding the corresponding elements has some special rules:

- ¶1.5 no brace elision is done for three kinds of elements: a non-array type dependent on a template parameter, an array type with a value-dependent bound, and an array type with a dependent element type where `xi` is a string literal;
- ¶1.6, ¶1.7 a pack expansion element is considered to correspond to no initializer if it isn't at the end, and to all remaining initializers if it is;
- ¶1.8 if `ei` is an array and `xi` is a braced list, `Ti` is an rvalue reference to the declared type of `ei`;
- ¶1.9 if `ei` is an array and `xi` is a string literal, `Ti` is an lvalue reference to the const-qualified declared type of `ei`.

The no-brace-elision rule leads to the following (adapted from the standard's example):

```cpp error
template <typename T> struct S { T x; T y; };
template <typename T> struct C { S<T> s; T t; };
template <typename T> struct D { S<int> s; T t; };

C c1 = {1, 2};          // error: s has a dependent type, so no brace elision; 1 corresponds to s, and S<T> can't be deduced from 1
C c3 = {{1u, 2u}, 3};   // OK: T is deduced as int from 3; {1u, 2u} is a non-deduced context
D d1 = {1, 2};          // error: S<int> doesn't depend on T; with brace elision, 1 and 2 initialize s and no element corresponds to t
D d2 = {1, 2, 3};       // OK: 1 and 2 initialize s, 3 initializes t, deducing D<int>
```

Array elements and string literals:

```cpp error
#include <cstddef>
template<class T, std::size_t N> struct H { T array[N]; };
template<class T, std::size_t N> struct I { volatile T array[N]; };
template<std::size_t N> struct J { unsigned char array[N]; };

H h = { "abc" };   // OK: parameter const T(&)[N], deduces H<char, 4>; T isn't const char
I i = { "def" };   // OK: parameter const volatile T(&)[N], deduces I<char, 4>
J j = { "ghi" };   // error: const unsigned char(&)[N] can't bind to const char[4]
```

### Inherited constructors {{c++23}}

The last part of ¶1 says: if `C` is defined and inherits constructors from a direct base class `B` through a *using-declaration*, the guides of `B`, after a transformation, are also added to the guides of `C` ([[P2582R1]]).

```cpp error
template <typename T> struct B { B(T); };
template <typename T> struct C : public B<T> { using B<T>::B; };
template <typename T> struct D : public B<T> {};

C c(42);   // OK: deduces C<int> through the inherited B(T)
D d(42);   // error: D inherits no constructors; no usable guide
```

The transformation: let `A` be an alias template with the same template parameter list as `C` whose defining type is `B`. If `A` is deducible ([[dcl.type.simple]]), take the guides of `A` (built by the alias template rules below), then map the return type of each guide from a specialization of `B` back to the corresponding specialization of `C`. The standard describes this mapping with partial specializations of a helper class template `CC` (Note 2).

!!! impl "Implementation status"
    In our tests Clang 23 doesn't implement CTAD from inherited constructors yet; in the example above it also reports no viable constructor or deduction guide for `C c(42);`.

Annex [[diff.cpp20.over]] records the compatibility impact of this change: code that previously used other guides may deduce a different type.

## CTAD for alias templates (¶4–¶5) {{c++20}}

```cpp run ok
#include <vector>
#include <type_traits>
template<class T> using Vec = std::vector<T>;
int main() {
  Vec v{1, 2, 3};   // deduces std::vector<int>
  static_assert(std::is_same_v<decltype(v), std::vector<int>>);
}
```

[[P1814R0]] in C++20 allowed CTAD for alias templates.

¶4 When the placeholder designates an alias template `A`, the defining type of `A` must be of the form `C<…>`, a *simple-template-id*, possibly qualified ([[dcl.type.simple]]). The guides of `A` are obtained by transforming each guide `f` of `C`:

1. Deduce the template arguments of the return type of `f` from the defining type of `A` ([[temp.deduct.type]]). Not deducing all of them isn't a failure; if deduction fails for another reason, proceed as if nothing was deduced.
2. Substitute the deduction results into `f`, giving `g`. If substitution succeeds, form a new guide `f''`: with the function type of `g` (¶4.1); whose template parameters are the template parameters of `A` that appear in the deduction results above, plus the template parameters of `f` that weren't deduced (¶4.2); whose associated constraints are those of `g` plus one more: the template arguments of `A` are deducible from the return type (¶4.3).
3. The properties of `f` of being a copy deduction candidate, coming from a deduction guide, and being `explicit` are all carried over to `f''` unchanged (¶4.4–¶4.6).

¶5 The template arguments of `A` are deducible from a type `T` if, given a helper class template `AA` with a single partial specialization `AA<A<template parameters…>>`, `AA<T>` matches that partial specialization.

The key is the constraint added by ¶4.3. It ensures the deduced type really is some specialization of `A`, not just some specialization of `C`:

```cpp error
#include <concepts>
#include <type_traits>
template <class T, class U> struct C {
  C(T, U);                                    // #1
};
template<class T, class U>
  C(T, U) -> C<T, std::type_identity_t<U>>;   // #2

template<class V> using A = C<V*, V*>;
template<std::integral W> using B = A<W>;

int i{};
double d{};
A a1(&i, &i);   // OK: deduces A<int>, i.e. C<int*, int*>
A a2(i, i);     // error: V* can't be deduced from int
A a3(&i, &d);   // error: #1 can't deduce (V*, V*) from (int*, double*); #2 deduces C<int*, double*>, which isn't an A<V>
B b1(&i, &i);   // OK: deduces B<int>
B b2(&d, &d);   // error: C<double*, double*> is A<double>, but double doesn't satisfy std::integral
```

The standard's Example 3 gives one possible implementation: transform #1 into

```cpp
template<class V> requires deduces_A<C<V*, V*>>
  auto f1_prime(V*, V*) -> C<V*, V*>;
```

where `deduces_A<T>` uses the `AA` partial specialization technique above to check whether `T` is a specialization of `A`.

### CTAD for template template parameters (¶3)

¶3 When the placeholder is a type template template parameter `P`, the corresponding template argument must be a deducible template. Let `A` be an alias template with the same template parameter list as `P` whose defining type is the argument template applied to the template arguments of `P`; then `A` replaces the original name and the alias template rules apply.

```cpp error
template<typename ... Ts>
struct Y {
  Y();
  Y(Ts ...);
};
template<template<typename T = char> class X>
void f() {
  X x;          // OK: deduces Y<char>
  X x1{1};      // OK: deduces Y<int>
  X x2{1, 2};   // error: X<T> can't be deduced from Y<int, int>
}
template void f<Y>();
```

Here `A` amounts to `template<typename T = char> using A = Y<T>;`. For `X x`, the guide generated from `Y()` carries the template parameter `T = char` of `A` after the transformation, so `Y<char>` is deduced. `Y<int, int>` deduced for `X x2{1, 2}` isn't a specialization of `A` and is excluded by the ¶4.3 constraint.

!!! impl "Where Clang deviates"
    In our tests Clang 23 handles `X x1{1}` as the standard says. But it deduces `X x;` as `Y<>`, not using the default template argument of `P`, and then reports an error because the two constructors of `Y<>` have the same signature; it also accepts `X x2{1, 2}`. Both differ from the standard's example.

## Overload resolution over the guides (¶6)

¶6 For deduction, the guides are treated as constructors of a hypothetical class, and initialization and overload resolution are performed per [[dcl.init]] and [[over.match.ctor]], [[over.match.copy]] or [[over.match.list]] (depending on the form of initialization). There are two exceptions:

- ¶6.1 If the initializer list has a single expression of type `cv U`, where `U` is a specialization of the class template designated by the placeholder or a class derived from one, the first phase of [[over.match.list]] (the `initializer_list` constructors) is skipped.
- ¶6.2 When deducing for the aggregate deduction candidate, the number of elements of a trailing parameter pack is taken from the number of remaining arguments only if it isn't deduced otherwise.

The hypothetical constructor corresponding to a guide generated from an `explicit` constructor or deduction guide is also explicit. All hypothetical constructors are considered public members.

### A single object of the same class in braces is a copy (¶6.1)

```cpp run ok
#include <vector>
#include <type_traits>
int main() {
  std::vector v1{1, 2};
  std::vector v2{v1};       // the initializer_list phase is skipped; the copy deduction candidate deduces vector<int>
  std::vector v3{v1, v1};   // two elements, ¶6.1 doesn't apply; deduces vector<vector<int>>
  static_assert(std::is_same_v<decltype(v2), std::vector<int>>);
  static_assert(std::is_same_v<decltype(v3), std::vector<std::vector<int>>>);
}
```

Without ¶6.1, `std::vector v2{v1}` would select the guide generated from `vector(initializer_list<T>)` in the first phase and deduce `vector<vector<int>>`, contrary to the intuition that braces around a single object of the same class mean a copy. The price is that `v2` and `v3` behave inconsistently: in generic code the type of `std::vector v{args...}` changes with the number of `args`.

### `T&&` in a constructor isn't a forwarding reference

```cpp error
template<class T> struct W { W(T&&); };
int n;
W w1{0};   // OK: W<int>
W w2{n};   // error: T&& isn't a forwarding reference and can't be deduced from an lvalue
```

In a guide generated from a constructor, `T` is a template parameter of the class template. [[temp.deduct.call]] says such a `T&&` isn't a forwarding reference in CTAD.

If it were a forwarding reference, `W w2{n}` would deduce `W<int&>`, and the constructor would become `W(int&)`. The author wrote a constructor taking an rvalue, yet CTAD would silently produce a specialization with a reference type as its argument, which is almost always wrong. When forwarding semantics are needed, write the deduction guide `template<class U> W(U&&) -> W<std::decay_t<U>>;`.

### explicit carries over to the guides

In copy-initialization or copy-list-initialization, if deduction selects an explicit guide, the deduction itself is ill-formed, even if the constructor actually used for the initialization afterwards isn't explicit (¶7, Example 2):

```cpp error
template <class T> struct A {
  explicit A(const T&, ...) noexcept;   // #1
  A(T&&, ...);                          // #2
};
int i;
A a1 = { i, i };   // error: deduction selects the explicit #1 (#2 can't be deduced from the lvalue i)
A a2{i, i};        // OK: direct-list-initialization; #1 deduces A<int> and #1 initializes
A a3{0, i};        // OK: #2 deduces A<int> (0 is an rvalue)
A a4 = {0, i};     // OK: same as above; #2 isn't explicit
```

## Tie-breakers

The tie-breakers specific to CTAD are [[over.match.best#2.10]] to [[over.match.best#2.13]], ranked after the comparison of conversion sequences, partial ordering of templates, and constraints:

| Rule | Contents |
|---|---|
| 2.10 | A guide not generated from an inherited constructor beats one generated from an inherited constructor (when all corresponding parameter types are the same) |
| 2.11 | One generated from a deduction guide beats one not generated from a deduction guide |
| 2.12 | The copy deduction candidate beats the others |
| 2.13 | One generated from a non-template constructor beats one generated from a constructor template |

```cpp ok
#include <type_traits>
template <class T> struct A {
  using value_type = T;
  A(value_type);    // #1
  A(const A&);      // #2
  A(T, T, int);     // #3
  template<class U>
    A(int, T, U);   // #4
  // #5 is the copy deduction candidate A(A)
};

A x(1, 2, 3);       // uses #3: #3 and #4 are equally good, and 2.13 picks #3, generated from a non-template constructor

template <class T>
A(T) -> A<T>;       // #6

A a(42);            // uses #6 to deduce A<int>, then #1 to initialize
A b = a;            // uses #5 to deduce A<int>: #5 is more specialized than #6, and partial ordering applies before 2.11

template <class T>
A(A<T>) -> A<A<T>>; // #7, as specialized as #5

A b2 = a;           // uses #7 to deduce A<A<int>>: partial ordering ties, and 2.11 makes the deduction guide win
static_assert(std::is_same_v<decltype(b), A<int>>);
static_assert(std::is_same_v<decltype(b2), A<A<int>>>);
```

Why isn't #1 used for `A a(42)`? The parameter of #1 is `value_type`, i.e. `typename A<T>::value_type`, a non-deduced context, so `T` can't be deduced from `42`; deduction fails for the guide generated from #1, and only #6 is usable.

`b2` is a common trap: the user-written #7 and the copy deduction candidate #5 both have the parameter `A<T>`, partial ordering ties, 2.11 makes the deduction guide win, and `b2` becomes `A<A<int>>`.

<details class="fine" markdown="1"><summary>Remaining wording</summary>

¶2, ¶7, ¶8 and ¶9 are example paragraphs, and the main parts have been cited above. ¶2 also has several inherited constructor examples: if the deduction guide `B(int) -> B<char>` is declared after `C` inherits `B(T)`, `C c2(42)` deduces `C<char>`; when the base class doesn't depend on the template parameters of `C` (`struct E : B<int>`), the inherited guides can't deduce the template arguments of `E`.

</details>

## Implementation view

!!! impl
    - Compilers really do generate these guides. Clang generates an implicit deduction guide declaration for each constructor, visible with `-Xclang -ast-dump`; when CTAD fails, the candidate template ignored lines in the diagnostic are these implicit guides.
    - Deduction guides only take part in type deduction and produce no code or symbols.

## History

!!! history
    - C++17: [[P0091R3]] introduced CTAD, including implicit guides, the copy deduction candidate, user deduction guides, and the rule that `T&&` in a constructor isn't a forwarding reference. The single-element exception of ¶6.1 was added later by a defect report.
    - C++20: the aggregate deduction candidate ([[P1816R0]], [[P2082R1]]); CTAD for alias templates ([[P1814R0]]).
    - C++23: CTAD from inherited constructors ([[P2582R1]]).
    - C++26: a *splice-type-specifier* can also be a deduced class type placeholder.

## Common misconceptions

!!! pitfall "A constructor's `T&&` is a forwarding reference in CTAD"
    It isn't. When forwarding semantics are needed, write a deduction guide; the standard library provides deduction guides for this in `std::optional`, `std::tuple` and others.

!!! pitfall "CTAD can specify only some of the template arguments"
    It can't. `std::pair<int> p(1, 2.0);` is ill-formed: with a template argument list it is no longer a deduced class type placeholder, and all arguments must be given.

## Questions

!!! question "Question 1"
    What type does `std::tuple t{std::tuple{1}};` deduce? What about `std::tuple t{std::tuple{1}, 2};`?

<details markdown="1">
<summary>Answer</summary>

The first is `std::tuple<int>`. The braces contain a single specialization of `std::tuple`, so ¶6.1 skips the initializer list phase (`tuple` has no `initializer_list` constructor anyway). There are three main contenders: the copy deduction candidate `tuple(tuple<Ts...>) -> tuple<Ts...>`, deducing `tuple<int>`; the standard library deduction guide `tuple(Ts...) -> tuple<Ts...>`, deducing `tuple<tuple<int>>`; and the guide generated from the constructor `tuple(const Types&...)`, also deducing `tuple<tuple<int>>`. All three have identity conversion sequences, so the tie-breakers come in. Partial ordering of templates ([[over.match.best#2.5]]) ranks before 2.11, and the parameter `tuple<Ts...>` of the copy deduction candidate is more specialized than `Ts...` and `const Ts&...`, so it wins.

The second has two elements, so the copy deduction candidate isn't viable, and `std::tuple<std::tuple<int>, int>` is deduced. Clang 23 gives the same results in our tests.
</details>

!!! question "Question 2"
    Why is the aggregate deduction candidate added only when `C` has no deduction guides?

<details markdown="1">
<summary>Answer</summary>

Writing deduction guides for an aggregate shows that the author wants precise control over the deduced result. Adding an automatically generated aggregate deduction candidate on top could beat the user's guides through conversion sequence comparison or partial ordering of templates (both rank before 2.11), defeating them. Also, deduction guides written for aggregates in C++17 should keep their meaning in C++20; not generating the candidate when guides exist is the simplest way to stay compatible.
</details>
