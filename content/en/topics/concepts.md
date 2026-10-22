---
title: Concepts and constraints
summary: From defining a concept to overloading on constraints. The difference between requires-expressions and requires-clauses, satisfaction and subsumption of constraints, the four places to write a constraint, the hierarchy of standard library concepts, migrating from enable_if, and the most common pitfalls.
tags: concepts, constraints, generic programming, SFINAE, overload resolution
updated: 2026-10-19
---

!!! tldr
    - A concept is a name given to a set of compile-time requirements. Constraints answer two independent questions: is this declaration usable for the given arguments (satisfaction), and of two usable declarations, which is more specialized (subsumption).
    - Satisfaction checks the atomic constraints against the arguments one by one: left to right with short-circuiting; a substitution failure only means not satisfied, but the result of an atomic constraint must be exactly `bool`.
    - Subsumption compares only the structure of constraints: two atomic constraints are identical only if they come from the same expression in the source. To have overloads ordered by their constraints, define the conditions as named concepts, and have the stronger concept refer to the weaker one by name.
    - The same constraint must have the same satisfaction result at different points in the program; otherwise the program is ill-formed, no diagnostic required. Clang caches the first result.
    - Migrating from `enable_if` to constraints gains, besides readability, the ability to order overloads by subsumption and clearer error messages.

The rules for concepts are spread across several clauses: concept definitions in [[temp.concept]], *requires*-expressions in [[expr.prim.req]], normalization and satisfaction of constraints in [[temp.constr]], subsumption in [[temp.constr.order]], and their role in overload resolution in [[over.match.viable]] and [[over.match.best]].

## The same condition written twice: why is it ambiguous?

<div class="compare" markdown="1">

```cpp error
#include <type_traits>
template<class T>
int g(T) requires
  std::is_integral_v<T>
{ return 1; }
template<class T>
int g(T) requires
  std::is_integral_v<T> &&
  std::is_signed_v<T>
{ return 2; }
int r = g(1);  // error: ambiguous
```

```cpp ok
#include <concepts>
template<class T>
int g(T) requires
  std::integral<T>
{ return 1; }
template<class T>
int g(T) requires
  std::signed_integral<T>
{ return 2; }
int r = g(1);  // OK: picks the second
```

</div>

Both sides mean the same thing: the second overload's condition is stricter than the first's. Clang rejects the left one as ambiguous and picks the second overload on the right.

The difference lies in how the compiler decides which constraint is stricter. It doesn't understand what `is_integral_v<T>` means; it only compares the structure of the constraints, and the two `is_integral_v<T>` on the left are two different expressions in the source, treated as two unrelated conditions. On the right, `std::signed_integral` refers to `std::integral` by name in its definition, so after expansion both sides contain the same expression, and from that the compiler knows the second constraint implies the first. The rest of this section explains the mechanism.

## Satisfaction and subsumption are two questions

Constraints are first **normalized** ([[temp.constr.normal]]): parentheses are removed, `&&` and `||` are split into conjunctions and disjunctions, and uses of concepts are replaced by their definitions, until only indivisible parts remain. These indivisible parts are called [[g:atomic-constraint|atomic constraints]]. For example, `std::integral<T> && (sizeof(T) > 2)` normalizes to the conjunction of two atomic constraints, `std::is_integral_v<T>` and `sizeof(T) > 2`.

On that basis, constraints answer two independent questions:

| Question | Mechanism | Input | Clause |
|---|---|---|---|
| Is this declaration usable for the given arguments? | **Satisfaction** | The constraint and concrete template arguments | [[temp.constr.op]], [[temp.constr.atomic]] |
| Of two usable declarations, which is more specialized? | **Subsumption** | The structure of the two constraints, ignoring the arguments | [[temp.constr.order]] |

Satisfaction substitutes the arguments into each atomic constraint and evaluates it, so a substitution failure just means not satisfied. Subsumption compares only structure, so constraints with the same meaning but different origins don't subsume each other, which is the source of the ambiguity at the start. Most of the surprising behavior of concepts can be explained from these two points.

## Defining a concept

```cpp run title="define.cpp" ok
#include <concepts>
#include <cstddef>

// based on type traits
template<class T>
concept Arithmetic = std::integral<T> || std::floating_point<T>;

// based on a requires-expression: which expressions must be valid, and of what type
template<class T>
concept Container = requires (T c, const T cc) {
  typename T::value_type;                              // type requirement
  { cc.size() } -> std::convertible_to<std::size_t>;   // compound requirement
  c.begin(); c.end();                                  // simple requirements
};

// composition: refer to the weaker concept by name; this decides whether overloads can be ordered
template<class T>
concept SizedRandomContainer = Container<T> && requires (T c) {
  { c[0] } -> std::same_as<typename T::value_type&>;
};

int main() {}
```

Restrictions on concept definitions ([[temp.concept]]):

- They may only appear at namespace scope, can't be declared first and defined later, and can't be overloaded;
- A concept itself can't be constrained: `template<std::integral T> concept C = ...` is ill-formed; the condition goes on the right-hand side of the `=`;
- They can't be specialized. To let users customize, make the concept depend on a variable template that can be specialized, such as `std::ranges::enable_view`;
- They can't refer to themselves.

`C<Args...>` is a prvalue of type `bool` ([[temp.names#15]]) and can be used anywhere a `bool` constant is needed, such as `static_assert` and `if constexpr`.

## requires-expressions and requires-clauses

Both use the keyword `requires`, but they are completely different things:

| | *requires*-expression ([[expr.prim.req]]) | *requires*-clause ([[temp.pre#9]]) |
|---|---|---|
| What it is | An expression of type `bool` | Part of a declaration, adding a constraint to it |
| Where it goes | Anywhere a `bool` constant is needed, most often in a concept definition | After a template parameter list, or after a function declarator |
| When a requirement is invalid | Inside a template, the result is `false` | |
| Role in constraints | One atomic constraint, not split further | Introduces a constraint expression |

```cpp run ok
template<class T>
  requires requires (T x) { x + x; }   // the first requires is a clause, the second an expression
T twice(T x) { return x + x; }
int main() { return twice(0); }
```

`requires requires` is valid, but it usually means the condition should be extracted into a named concept, for reasons explained under subsumption below.

!!! warning "requires-expressions outside templates"
    Only invalid expressions produced by substituting template arguments make a *requires*-expression `false`. Outside a template, in `requires (std::vector<int> v) { v.foo(); }`, `v.foo()` is an ordinary ill-formed expression and the program is ill-formed ([[expr.prim.req.general#5]] Note 1).

## Four places to write a constraint

```cpp run title="four-ways.cpp" ok
#include <concepts>

template<std::integral T> T f1(T x) { return x; }                    // (1) type-constraint
template<class T> requires std::integral<T> T f2(T x) { return x; }  // (2) requires-clause
template<class T> T f3(T x) requires std::integral<T> { return x; }  // (3) trailing requires-clause
std::integral auto f4(std::integral auto x) { return x; }            // (4) constrained placeholder

int main() { return f1(0) + f2(0) + f3(0) + f4(0); }
```

All four functions' constraints normalize to `std::integral<T>` ([[temp.constr.decl]]). But their template heads are written differently, and the declaration and definition of a function template must use the same form ([[temp.over.link]]).

When a declaration has constraints in several places, they form a conjunction in a fixed order ([[temp.constr.decl#3]]): type-constraints in the template parameter list, the *requires*-clause after the template parameter list, `C auto` in function parameters, and finally the trailing *requires*-clause. This order is also the short-circuit order of satisfaction checking.

Form (4) is called an [[g:abbreviated-function-template|abbreviated function template]] ([[P1141R2]]): each `C auto` parameter introduces an invented type template parameter. The `std::integral auto` on the return type is not a template parameter but a check on the deduced return type; failing it is a hard error. Constrained placeholders can also be used for variables: `std::integral auto n = 1.0;` deduces `double`, which doesn't satisfy the constraint, so it's an error.

A trailing *requires*-clause can only be used on templated functions ([[dcl.decl.general#5]]), and non-template member functions of class templates count. So member functions can be overloaded on constraints without becoming templates.

## How satisfaction is checked

Satisfaction checking ([[temp.constr]]) comes down to five points:

1. A conjunction is checked left to right. When the left side is not satisfied, the right side is not substituted at all.
2. A substitution failure in an atomic constraint means it is not satisfied. This applies only to the immediate context of the atomic constraint itself; if the substitution triggers the instantiation of some function template body and the error is there, it's a hard error.
3. After substitution, the type of an atomic constraint must be exactly `bool`, with no conversion.
4. `!E` is one atomic constraint. `!` doesn't flip a substitution failure into satisfaction.
5. The same atomic constraint with the same arguments must have the same satisfaction result at different points in the program; otherwise the program is IFNDR (ill-formed, no diagnostic required; see [[ifndr]]).

Points 1 and 3 can be seen together:

<div class="compare" markdown="1">

```cpp ok
struct S {
  static constexpr int value = 1;
};
template<class T>
  requires (sizeof(T) > 100)
        && (T::value)
int f(T) { return 1; }
int f(...) { return 2; }
int r = f(S{});  // 2
```

```cpp error
struct S {
  static constexpr int value = 1;
};
template<class T>
  requires (sizeof(T) > 0)
        && (T::value)
int f(T) { return 1; }
int f(...) { return 2; }
int r = f(S{});  // error
```

</div>

`T::value` has type `int`, not `bool`. On the left, the first atomic constraint isn't satisfied, the second isn't substituted, nothing happens, and the call picks `f(...)`. On the right, the first atomic constraint is satisfied, the second is substituted, and Clang reports `atomic constraint must be of type 'bool' (found 'const int')`.

## How subsumption compares

Subsumption ([[temp.constr.order]]) treats atomic constraints as propositional variables: constraint P subsumes constraint Q if and only if P implies Q according to their and/or structure. Atomic constraints are compared only by identity: two atomic constraints are identical if and only if they come from the same expression in the source and their parameter mappings are equivalent ([[temp.constr.atomic#2]]).

This gives the most important rule of thumb for using concepts: if a constraint is to take part in overload ordering, define it as a named concept and have the stronger concept refer to the weaker one by name. The standard library's iterator concepts are organized this way: the definition of `random_access_iterator` contains `bidirectional_iterator<I> && ...`, so they subsume layer by layer:

```cpp run title="subsumption.cpp" ok
#include <concepts>
#include <iterator>
#include <cstdio>
#include <list>
#include <vector>

template<std::input_iterator I>
void walk(I) { std::puts("input"); }
template<std::bidirectional_iterator I>
void walk(I) { std::puts("bidirectional"); }
template<std::random_access_iterator I>
void walk(I) { std::puts("random access"); }

int main() {
  std::vector<int> v; std::list<int> l;
  walk(v.begin());   // random access
  walk(l.begin());   // bidirectional
}
```

The example on the left at the start is ambiguous because the two `is_integral_v<T>` come from different expressions. Likewise, two *requires*-expressions written out separately, two `!C<T>` written out separately, and a wrapped `(C<T> && D<T>) == true` all can't take part in subsumption.

C++26 fills in the case of parameter packs: a fold expression of the form `(C<Ts> && ...)` becomes a **fold expanded constraint** ([[temp.constr.fold]], [[P2963R3]]) and can be compared for subsumption with `(D<Ts> && ...)`. In C++23 they are unrelated atomic constraints.

```cpp run ok
#include <concepts>
template<class... T> requires (std::integral<T> && ...)
int f(T...) { return 1; }
template<class... T> requires (std::signed_integral<T> && ...)
int f(T...) { return 2; }
int main() { return f(1, 2); }   // 2
```

Clang 23 already implements this rule, and the program returns 2.

## Where constraints affect the choice

| Situation | Rule | Clause |
|---|---|---|
| Between function templates | Partial ordering: when equally specialized by deduction, the more constrained one is more specialized | [[temp.func.order]] |
| Between non-template functions, such as member functions of class templates | With the same parameter types, the more constrained one wins | [[over.match.best]], [[temp.constr.order#6]] |
| Class template partial specializations | The more constrained partial specialization is more specialized | [[temp.spec.partial.order]] |
| Template template arguments | The parameter must be at least as specialized as the argument, constraints included; if the parameter is unconstrained, the argument's constraints are ignored | [[temp.arg.template#4]] |
| Special member functions | Several destructors or copy constructors with different constraints can be declared and selected by constraint, giving conditional triviality | [[class.dtor]] |

```cpp run title="partial-spec.cpp" ok
#include <concepts>
#include <cstdio>

template<class T> struct Printer { static void print() { std::puts("generic"); } };
template<std::integral T> struct Printer<T> { static void print() { std::puts("integral"); } };
template<std::signed_integral T> struct Printer<T> { static void print() { std::puts("signed"); } };

int main() {
  Printer<double>::print();     // generic
  Printer<unsigned>::print();   // integral
  Printer<int>::print();        // signed: signed_integral subsumes integral
}
```

## Standard library concepts

The standard library concepts are mostly in `<concepts>`, `<iterator>` and `<ranges>`, organized in hierarchies. In the table below an arrow means refinement: the concept on the right refers to the one on the left by name, therefore subsumes it, and can be used to order overloads.

| Header | Category | Hierarchy |
|---|---|---|
| `<concepts>` | Core language | `same_as`, `derived_from`, `convertible_to`, `common_with`; `integral` → `signed_integral`, `unsigned_integral`; `floating_point`; `destructible` → `constructible_from` → `default_initializable`, `move_constructible` → `copy_constructible` |
| `<concepts>` | Comparison | `equality_comparable`, `totally_ordered`, and their `_with` versions |
| `<concepts>` | Object | `movable` → `copyable` → `semiregular` → `regular` |
| `<concepts>` | Callable | `invocable` → `predicate` → `relation` |
| `<iterator>` | Iterators | `input_or_output_iterator` → `input_iterator` → `forward_iterator` → `bidirectional_iterator` → `random_access_iterator` → `contiguous_iterator`; `sentinel_for`, `sized_sentinel_for` |
| `<iterator>` | Algorithm requirements | `indirectly_readable`, `indirectly_copyable`, `sortable`, `mergeable`, `permutable` |
| `<ranges>` | Ranges | `range` → `input_range` → … → `contiguous_range`; `sized_range`, `view`, `borrowed_range`, `viewable_range` |

`regular_invocable` and `invocable`, and `equivalence_relation` and `strict_weak_order` versus `relation`, have exactly the same definitions; they differ only in semantic requirements. They subsume each other and can't be used to distinguish overloads.

Standard library concepts usually also have **semantic requirements** the compiler can't check; for example `equality_comparable` requires `==` to be an equivalence relation. A type that meets the syntactic requirements but violates the semantic ones is said to satisfy but not [[g:models-concept|model]] the concept. If the validity or meaning of a program depends on whether a set of arguments models a concept, and they satisfy it without modeling it, the program is IFNDR ([[res.on.requirements]]).

## Migrating from enable_if

| C++17 | C++20 | Notes |
|---|---|---|
| `template<class T, std::enable_if_t<cond<T>, int> = 0>` | `template<class T> requires cond<T>` | Or define `cond` as a concept |
| `void_t` detection idiom plus a trait class | *requires*-expression plus a concept | Much more readable |
| Tag dispatch on `iterator_category` | Overloading on constraints | Requires concepts that subsume layer by layer |
| Conditional triviality through conditional base classes | Several constrained special member functions | Less code, faster compilation |
| Member function template `template<class U = T, enable_if_t<...>>` | Trailing *requires*-clause | The member function no longer has to be a template |
| Controlling partial specializations with `std::enable_if_t<...>* = nullptr` | Constrained partial specializations | |

To the compiler, the condition of an `enable_if` is an opaque boolean. Two `enable_if` overloads with overlapping conditions can only be disambiguated by hand-crafting mutually exclusive conditions:

```cpp title="enable-if-overlap.cpp" error
#include <type_traits>
template<class T, std::enable_if_t<std::is_integral_v<T>, int> = 0>
int f(T) { return 1; }
template<class T, std::enable_if_t<std::is_integral_v<T> && std::is_signed_v<T>, int> = 0>
int f(T) { return 2; }

int a = f(1);   // error: ambiguous; enable_if can't express which is more specialized
```

Switching to named concepts gives the form on the right at the start.

Differences to watch for when migrating:

- [[g:sfinae|SFINAE]] works during template argument deduction; constraints are checked after deduction succeeds. Candidates whose constraints aren't satisfied are removed from the set of viable functions ([[over.match.viable]]).
- `enable_if` can't constrain a class template itself, only via an extra defaulted template parameter. `template<std::integral T> struct S;` makes `S<double>` an error as soon as it is named ([[temp.names#14]]).
- The boundary of hard errors hasn't changed. If an expression in a constraint triggers the instantiation of a function body that fails, it is still a hard error, consistent with SFINAE's immediate-context rule.

## Error messages

When a constraint isn't satisfied, the compiler follows the normalized structure to point out which atomic constraint failed and why:

```cpp title="diagnostic.cpp" error
#include <concepts>
template<class T>
concept Addable = requires (T a, T b) { a + b; };

template<Addable T> T sum(T a, T b) { return a + b; }

struct P {};
int main() { sum(P{}, P{}); }   // error: constraints not satisfied
```

Clang 23's diagnostics are, in order: `no matching function for call to 'sum'`; `candidate template ignored: constraints not satisfied [with T = P]`; `because 'P' does not satisfy 'Addable'`; `because 'a + b' would be invalid: invalid operands to binary expression ('P' and 'P')`. In C++17, the same error was often reported deep inside the body of `sum`, or at the `enable_if` with nothing more than a missing member named `type`.

Some habits that make diagnostics more useful:

- Keep concepts at a moderate granularity, and give them names that state the intent; the diagnostic prints the concept name;
- Split complex requirements into a conjunction of several named concepts, so the diagnostic can pinpoint the one that failed;
- For overloads that should not be called, write a constrained `= delete` rather than letting them vanish from the candidates; the latter sometimes makes the diagnostic harder to understand.

## Common pitfalls

!!! pitfall "Subsumption only recognizes the same expression"
    The same expression written in two places doesn't produce subsumption; it has to go through the same named concept ([[temp.constr.atomic#2]]). Conversely, if two differently named concepts expand to the same expression, their atomic constraints are identical: `template<class T> concept D = C<T>;` normalizes to the same thing as `C`, so two overloads constrained with `C` and `D` respectively subsume each other, and a call is ambiguous.

!!! pitfall "An atomic constraint must be exactly bool"
    `requires (T::value)` (of type `int`) and `requires (std::tuple_size<T>{})` (a class type, even though it converts to `bool`) are both ill-formed, not merely unsatisfied ([[temp.constr.atomic#3]]). Write `requires (bool(T::value))` or `requires (T::value != 0)` when needed.

!!! pitfall "Negation doesn't flip a substitution failure"
    `requires (!std::integral<typename T::type>)` is not satisfied for a `T` without a `type` member. To express "has no nested type meeting the requirement", put the negation outside the concept: first define `template<class T> concept HasIntegralType = std::integral<typename T::type>;`, then write `requires (!HasIntegralType<T>)`.

!!! pitfall "Satisfaction results are cached"
    ```cpp
    template<class T> concept Complete = requires { sizeof(T); };
    struct S;
    static_assert(!Complete<S>);
    struct S {};
    static_assert(Complete<S>);   // IFNDR; Clang reuses the cached result and this assertion fails
    ```
    Any concept whose satisfaction depends on the current point in the program runs into the IFNDR of [[temp.constr.atomic#3]]: checking whether a type is complete, checking whether some overload has been declared, relying on ADL to find a function declared later.

!!! pitfall "A requires-expression is one unit"
    `requires { a; b; }` and `requires { a; }` don't subsume each other. Extract the common part into a concept.

!!! pitfall "When constraints are checked"
    Constraints of function templates are checked during overload resolution, and unsatisfied candidates are not viable. Constraints of class templates, alias templates and variable templates are checked as soon as they are named; even just writing `S<double>*` requires them to be satisfied. You also can't provide an explicit specialization for arguments that don't satisfy the constraints ([[temp.names#14]]).

!!! pitfall "An unconstrained template template parameter accepts a constrained template"
    `template<template<class> class TT>` accepts `template<std::integral T> class X` ([[temp.arg.template#4]]), and the constraint only fails when `TT<double>` is instantiated.

!!! pitfall "Constraint checking that depends on itself"
    ```cpp
    template<class T> concept Printable = requires (T t) { print(t); };
    template<Printable T> void print(T);
    ```
    Checking `Printable<S>` requires overload resolution for `print(t)`, which in turn requires checking `Printable<S>`. Clang 23 reports `satisfaction of constraint 'requires (T t) { print(t); }' depends on itself`. When designing a concept, don't make it depend on the functions it constrains.

## Changes in C++26

**Concept template parameters** ([[P2841]]) let concepts be passed as template arguments, so you can write concepts that take concepts:

```cpp run ok
#include <concepts>
template<template<class> concept C, class... Ts>
concept all_satisfy = (C<Ts> && ...);
static_assert(all_satisfy<std::integral, int, long>);
static_assert(!all_satisfy<std::integral, int, double>);
int main() {}
```

Clang 23 already supports this feature. At the template definition it isn't known yet which concept `C` is, so normalization has to be deferred to instantiation; such constraints are called **concept-dependent constraints** ([[temp.constr.concept]]), and they don't take part in subsumption.

Fold expanded constraints ([[P2963R3]]) are covered in the subsumption section above.

## Questions

!!! question "Question 1"
    Which overload does this call pick?

    ```cpp
    template<class T> concept Small = sizeof(T) <= 4;
    template<class T> concept Tiny  = sizeof(T) <= 1;
    template<Small T> int f(T) { return 1; }
    template<Tiny T>  int f(T) { return 2; }
    int x = f('a');
    ```

<details markdown="1">
<summary>Answer</summary>

Ambiguous. Both constraints are satisfied. `sizeof(T) <= 1` does imply `sizeof(T) <= 4`, but they are two different atomic constraints and subsumption doesn't look at meaning, so neither subsumes the other. The fix is `template<class T> concept Tiny = Small<T> && sizeof(T) <= 1;`.
</details>

!!! question "Question 2"
    `template<class T> requires (sizeof(T) > 1) && (T::value)` causes no error for `T = char`. What about `requires (sizeof(T) > 1 && T::value)`?

<details markdown="1">
<summary>Answer</summary>

No error either. Parentheses are transparent during normalization ([[temp.constr.normal]] ¶1.1), so `(sizeof(T) > 1 && T::value)` is likewise split into a conjunction of two atomic constraints, and short-circuiting still applies. Only turning it into an expression whose top-level operator isn't `&&` or `||`, such as `bool(sizeof(T) > 1 && T::value)`, makes it a single atomic constraint. Then the substitution failure for `char::value` makes the whole atomic constraint unsatisfied; it's still not a hard error, there's just no short-circuiting any more.
</details>

!!! question "Question 3"
    Which member function does `W<int>{}.f()` call below? What about `W<unsigned>{}.f()`?

    ```cpp
    template<class T> struct W {
      int f() requires std::integral<T>;
      int f() requires std::signed_integral<T>;
    };
    ```

<details markdown="1">
<summary>Answer</summary>

`W<int>`: both are viable. They are direct members of the same class with the same parameter-type-list, and the second is more constrained (`signed_integral` subsumes `integral`), so by [[over.match.best]] ¶2.6 the second is called. `W<unsigned>`: only the first satisfies its constraints, so the first is called.
</details>
