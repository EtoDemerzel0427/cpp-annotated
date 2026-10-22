---
title: Concept definitions
summary: "How to define a concept, and the restrictions on concepts: they can only be defined at namespace scope, can't be constrained, can't be instantiated or specialized, and can't refer to themselves; and which concepts can be written as a type-constraint."
updated: 2026-10-19
---

!!! tldr
    - A concept is a name for a set of constraints: `template<class T> concept C = constraint-expression;`. `C<int>` is not a specialization but a `bool` expression whose value is `true` or `false`.
    - A concept can only be defined at namespace scope, can't be declared without being defined, and can't have a requires-clause or type-constraint.
    - A concept can't be instantiated, explicitly specialized or partially specialized. To let users customize it, make the concept depend on a variable template that can be specialized.
    - A concept's definition can't refer to the concept itself, so expanding concepts level by level always terminates.
    - Only concepts whose first template parameter is a type parameter (type concepts) can be written as `template<C T>` or `C auto`.

## Defining and using a concept (¶1–¶2)

```cpp run title="concept-def.cpp" ok
#include <concepts>

template<typename T>
concept EqualityComparable = requires(T x) {
  { x == x } -> std::convertible_to<bool>;
};

template<typename T>
  requires EqualityComparable<T>      // used in a requires-clause
T f1(T x) { return x; }

template<EqualityComparable T>        // used as a type-constraint
T f2(T x) { return x; }

auto f3(EqualityComparable auto x) { return x; }   // used as a constrained placeholder

int main() { return f1(0) + f2(0) + f3(0); }
```

¶1 A **concept** is a template that defines constraints on its template arguments. The grammar of a definition is:

```text
concept-definition:
    concept concept-name attribute-specifier-seq(opt) = constraint-expression ;
```

It is preceded by `template<...>` ([[temp.pre]]). ¶2 Such a definition declares a concept, and its identifier becomes a concept-name referring to it within its scope. The optional attributes appertain to the concept; for example, you can write `concept Old [[deprecated]] = ...;`.

Concepts are very different from other templates: they produce no entity at all, no type, function or object. Writing `C<int>` gives a prvalue of type `bool`, not a specialization of some template ([[temp.names#15]]). Keep this in mind and the restrictions in this subclause are easy to understand.

A few things follow directly from the grammar:

- A concept can only be defined, never just declared. `template<class T> concept C;` is a syntax error, so there is no such thing as a declaration disagreeing with a definition.
- Defining another concept with the same name in the same scope is a redefinition.
- A concept can have several parameters, default template arguments, parameter packs and constant parameters:

```cpp run title="concept-params.cpp" ok
template<class T, class U = int>
concept AtLeastAsBig = sizeof(T) >= sizeof(U);   // default template argument
static_assert(AtLeastAsBig<long>);

template<class... Ts>
concept AllNonEmpty = ((sizeof(Ts) > 0) && ...); // parameter pack

template<int N>
concept Positive = N > 0;                        // constant parameter
static_assert(Positive<1> && !Positive<0>);
int main() {}
```

## Namespace scope only (¶3)

¶3 A concept definition must appear at namespace scope ([[basic.scope.namespace]]).

```cpp title="concept-scope.cpp" error
struct S {
  template<class T> concept C = true;   // error: a concept can't be a class member
};
```

Template declarations can't appear at block scope anyway, so the only thing left to rule out is class scope. A member concept would be subject to access control and could depend on the parameters of an enclosing class template, so the same concept could have different definitions in different specializations of the enclosing class, and deciding whether two places name the same concept when comparing constraints would get more complicated. The standard picked the simplest option: concepts can only be namespace members. Concepts from another namespace can be brought in with a using-declaration.

## No constraints (¶4)

¶4 A concept can't have associated constraints; that is, it can't have a requires-clause, and its parameters can't be declared with a type-constraint:

```cpp title="constrained-concept.cpp" error
#include <concepts>
template<class T> requires std::integral<T>
concept C1 = sizeof(T) == 4;    // error: a concept can't have a requires-clause

template<std::integral T>
concept C2 = sizeof(T) == 4;    // error: a type-constraint also introduces associated constraints
```

If this were allowed, `C1<double>` would be unclear: is the expression ill-formed because the constraints aren't satisfied, or is its value `false`? The deeper reason is normalization: when constraints are compared, a concept name is replaced by its constraint expression ([[temp.constr.normal]]), and there is nowhere suitable to put an extra layer of associated constraints. Put the requirement directly into the constraint expression instead:

```cpp run title="fix-constrained.cpp" ok
#include <concepts>
template<class T>
concept C = std::integral<T> && sizeof(T) == 4;
static_assert(C<int> && !C<double>);
int main() {}
```

This has another benefit: `C` subsumes `std::integral` and can take part in comparing which constraint is stronger ([[temp.constr.order]]).

## Not instantiated, not specializable (¶5)

¶5 A concept is not instantiated ([[temp.spec]]). Note 1 explains that a concept name with arguments (a concept-id) is evaluated as an expression; a concept can't be explicitly instantiated, explicitly specialized or partially specialized.

```cpp title="no-specialization.cpp" error
template<class T> concept C = true;

template<> concept C<int> = false;          // error: can't be explicitly specialized
template concept C<int>;                    // error: can't be explicitly instantiated
template<class T> concept C<T*> = false;    // error: can't be partially specialized
```

Allowing specialization would cause two problems. First, the result of `C<int>` would depend on whether the specialization is visible, so the same constraint could give different answers at different points in the program. Second, normalization could no longer simply replace `C<T>` with the constraint expression of `C`, because some `T` would use a different definition, and subsumption between constraints couldn't be compared.

To let users customize, make the concept depend on a variable template that can be specialized:

```cpp run title="customizable.cpp" ok
template<class T> constexpr bool enable_my_view = false;   // users may specialize this
template<class T> concept MyView = enable_my_view<T>;

struct V {};
template<> constexpr bool enable_my_view<V> = true;

static_assert(MyView<V> && !MyView<int>);
int main() {}
```

The standard library's `std::ranges::enable_view` and `std::ranges::enable_borrowed_range` work exactly this way.

## The constraint expression is an unevaluated operand (¶6)

¶6 The constraint expression in a concept definition is an unevaluated operand ([[expr.context]]), so it doesn't odr-use anything and can refer to functions that are declared but not defined, such as `std::declval`.

Unevaluated doesn't mean unchecked. When checking whether constraints are satisfied, each atomic constraint, after substitution, is evaluated as a constant expression ([[temp.constr.atomic#3]]):

```cpp error
int f();                                       // not constexpr
template<class T> concept C = (f(), true);     // the definition itself is fine
static_assert(C<int>);                         // error: the atomic constraint is not a constant expression
```

## Prototype parameters and type concepts (¶7)

¶7 The first declared template parameter of a concept definition is its [[g:prototype-parameter|**prototype parameter**]]. A concept whose prototype parameter is a type parameter is a [[g:type-concept|**type concept**]].

Only type concepts can be used as a type-constraint ([[temp.param#9]]) or written as `C auto` ([[dcl.spec.auto]]). Both forms insert the constrained type as the first argument: `template<C<int> T>` means `C<T, int>`.

```cpp title="type-concept.cpp" error
#include <concepts>
template<int N> concept Positive = N > 0;                     // prototype parameter is a constant parameter
template<class T, class U> concept Same = std::same_as<T, U>; // type concept

template<Same<int> T> struct A {};    // OK: the constraint is Same<T, int>
template<Positive T> struct B {};     // error: Positive is not a type concept
```

C++26 concept template parameters follow the same rule: when used as a type-constraint, the concept's first parameter must be a type parameter ([[P2841]]).

```cpp run ok
#include <concepts>
template<template<class> concept C, class T> requires C<T>
int f(T) { return 1; }

template<template<class> concept C>
int g(C auto x) { return x; }

int main() { return f<std::integral>(1) + g<std::integral>(1) - 2; }
```

## A concept can't refer to itself

```cpp title="recursive.cpp" error
template<class T> concept C = C<T*>;   // error: a concept definition can't refer to itself
```

This rule isn't in this subclause but in [[basic.scope.pdecl#14]]: the locus of a concept definition is immediately after the concept name, and the note there says the constraint expression can't use that concept name.

With the locus placed after the name, a `C` in the constraint expression always finds the concept itself and is rejected, rather than silently finding something with the same name in an enclosing scope. Without recursion, normalization, which replaces concept names with their constraint expressions level by level, always terminates with only atomic constraints left, and only then is comparing subsumption between constraints decidable.

## Implementation notes

!!! impl
    - Clang has dedicated diagnostics for the violations in this subclause: `concept declarations may only appear in global or namespace scope`, `concept cannot have associated constraints`, `a concept definition cannot refer to itself`, `concept named in type constraint is not a type concept`. For an attempt to explicitly specialize a concept, it reports a syntax-level error.
    - A concept itself generates no code or symbols.

## History

!!! history
    - The Concepts TS had two forms: variable concepts `template<class T> concept bool C = ...;` and function concepts `template<class T> concept bool C() { return ...; }`, and function concepts could even be overloaded.
    - When C++20 merged concepts ([[P0734R0]] and later revisions), only the `concept C = ...;` form was kept: `bool` was dropped, overloading and specialization were prohibited, and definitions were required to be at namespace scope.
    - C++26 allows concepts to be passed as template arguments (concept template parameters, [[P2841]]).

## Common misconceptions

!!! pitfall "You can specialize a concept's result for a particular type"
    You can't (¶5). Make the concept depend on a variable template that can be specialized.

!!! pitfall "`template<std::integral T> concept C = ...;` just adds a restriction on `T`"
    It is ill-formed (¶4). Write `std::integral<T>` into the constraint expression with `&&`.

!!! pitfall "`C<T>` is a type or a specialization"
    It is a prvalue of type `bool` ([[temp.names#15]]).

!!! pitfall "The constraint expression isn't evaluated, so anything goes"
    When satisfaction is checked, each atomic constraint must be a constant expression of type exactly `bool`.

## Questions

!!! question "Question 1"
    The standard forbids specializing concepts but allows specializing variable templates. Used in constraints, what is the fundamental difference between `template<class T> constexpr bool C_v = ...;` and `template<class T> concept C = ...;`?

<details markdown="1">
<summary>Answer</summary>

In a constraint, `C_v<T>` is an opaque atomic constraint: the compiler doesn't look inside it and doesn't care whether it has been specialized. A concept-id is expanded into the concept's constraint expression during normalization, which requires `C<X>` to use the same definition for every `X`; specialization would break that, and with it the comparison of subsumption. So: for customizability, use a variable template, but it doesn't take part in subsumption; to take part in overload ordering, use a concept, but it can't be specialized.
</details>

!!! question "Question 2"
    Given `template<class T, class U> concept C = ...;`, does `template<C<int> T>` constrain `C<T, int>` or `C<int, T>`?

<details markdown="1">
<summary>Answer</summary>

`C<T, int>`. The constrained type is always inserted as the first argument ([[temp.param#9]]), which is also why `C` must be a type concept.
</details>
