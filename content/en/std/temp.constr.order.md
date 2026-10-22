---
title: Partial ordering by constraints
summary: "Which of two declarations is more constrained when both are satisfied: how subsumption is defined through disjunctive and conjunctive normal forms, why atomic constraints subsume only when identical, the difference between at least as constrained and more constrained, and how non-template member functions of a class template overload on constraints alone."
updated: 2026-10-19
---

!!! tldr
    - When two overloads both satisfy their constraints, the one with the stronger constraints wins; stronger means its constraints subsume the other's.
    - Subsumption is pure propositional logic: more conjuncts make it stronger, more disjuncts make it weaker, and atomic constraints are compared only by identity, not by meaning.
    - Atomic constraints are identical only if they come from the same expression, so to make constraints take part in ordering, write the weaker constraint as a concept and refer to it from the stronger concept.
    - A declaration without constraints is the weakest; of two constraints that don't subsume each other, neither is stronger, and the call is ambiguous.
    - Non-template member functions with the same signature in a class template can also be ordered by constraints; since C++20 this lets a class declare several destructors and pick the trivial one conditionally.

## Overloading on constraints

```cpp run title="overload-by-constraint.cpp" ok
#include <iterator>
#include <list>
#include <vector>
#include <cstdio>

template<std::forward_iterator I>       void advance_impl(I) { std::puts("forward"); }
template<std::bidirectional_iterator I> void advance_impl(I) { std::puts("bidirectional"); }
template<std::random_access_iterator I> void advance_impl(I) { std::puts("random access"); }

int main() {
    std::vector<int> v; std::list<int> l;
    advance_impl(v.begin());   // random access: all three satisfied, the most constrained is chosen
    advance_impl(l.begin());   // bidirectional
}
```

A `vector` iterator satisfies all three concepts, and the compiler picks the `random_access_iterator` overload, because the definition of `random_access_iterator` refers to `bidirectional_iterator`, which in turn refers to `forward_iterator`. Before C++20 this took tag dispatch (`iterator_category`) or hand-written mutually exclusive SFINAE conditions.

[[temp.constr]] covers how constraints are normalized into a structure of conjunctions (∧), disjunctions (∨) and atomic constraints, and when atomic constraints are identical. This page covers how those structures are used to compare the strength of two constraints.

## Subsumption (¶1)

¶1 A constraint `P` **subsumes** ([[g:subsumes|subsumes]]) a constraint `Q` if and only if every clause in the disjunctive normal form of `P` subsumes every clause in the conjunctive normal form of `Q`, where:

- ¶1.1 a disjunctive clause subsumes a conjunctive clause if and only if some atomic constraint in the former subsumes some atomic constraint in the latter;
- ¶1.2 an atomic constraint `A` subsumes an atomic constraint `B` if and only if they are identical ([[temp.constr.atomic#2]]);
- ¶1.3 {{c++26}} a fold expanded constraint `A` subsumes `B` if they are compatible for subsumption ([[temp.constr.fold#5]]), have the same fold-operator, and the constraint of `A` subsumes that of `B`.

The two normal forms are defined in footnotes 103 and 104. The **disjunctive normal form** (DNF) is a disjunction of clauses, each a conjunction of atomic constraints (or fold expanded constraints); the **conjunctive normal form** (CNF) is the other way round, a conjunction of disjunctive clauses. Taking `A ∧ (B ∨ C)` as an example:

| Normal form | Written | Clauses |
|---|---|---|
| DNF | `(A ∧ B) ∨ (A ∧ C)` | `A ∧ B`, `A ∧ C` |
| CNF | `A ∧ (B ∨ C)` | `A`, `B ∨ C` |

### Why this definition is implication

Treat each atomic constraint as an independent propositional variable. `P` implies `Q` when every way for `P` to hold (each DNF clause, a set of atoms holding together) makes every necessary condition of `Q` hold (each CNF clause, a set of atoms of which at least one must hold). When atoms have no logical relationship to each other, a set of atoms holding together makes a disjunction true if and only if the two share an atom. That is ¶1.1.

The fact that atoms have no relationship at all is the key to understanding subsumption. `sizeof(T) > 4` semantically implies `sizeof(T) > 2`, but to the subsumption rules they are two unrelated propositional variables.

### Examples (Example 1)

Let `A` and `B` be atomic constraints:

| Relation | Subsumes? | Why |
|---|---|---|
| `A ∧ B` subsumes `A` | yes | DNF clause `A ∧ B` and CNF clause `A` share `A` |
| `A` subsumes `A ∧ B` | no | DNF clause `A` and CNF clause `B` share no atom |
| `A` subsumes `A ∨ B` | yes | the CNF has one clause `A ∨ B`, which contains `A` |
| `A ∨ B` subsumes `A` | no | DNF clause `B` and CNF clause `A` share no atom |
| any constraint subsumes itself | yes | |

Requiring A and B is stricter than requiring only A; requiring A or B is looser than requiring only A:

```cpp run title="subsume-basic.cpp" ok
template<class T> concept P = sizeof(T) >= 1;
template<class T> concept Q = alignof(T) >= 1;

template<class T> constexpr int g(T) requires P<T> || Q<T> { return 1; }
template<class T> constexpr int g(T) requires P<T>         { return 2; }

template<class T> constexpr int h(T) requires P<T> && Q<T> { return 1; }
template<class T> constexpr int h(T) requires P<T>         { return 2; }

static_assert(g(1) == 2);   // P subsumes P ∨ Q: the second is more constrained
static_assert(h(1) == 1);   // P ∧ Q subsumes P: the first is more constrained
int main() {}
```

### Writing the same expression twice doesn't create subsumption

<div class="compare" markdown="1">

```cpp error
#include <type_traits>
template<class T> int f(T)
  requires std::is_integral_v<T>
{ return 1; }
template<class T> int f(T)
  requires std::is_integral_v<T>
        && std::is_signed_v<T>
{ return 2; }

int r = f(1);   // error: ambiguous
```

```cpp run ok
#include <type_traits>
template<class T> concept Integral =
  std::is_integral_v<T>;
template<class T> concept SignedIntegral =
  Integral<T> && std::is_signed_v<T>;

template<class T> int f(T)
  requires Integral<T>       { return 1; }
template<class T> int f(T)
  requires SignedIntegral<T> { return 2; }

int main() { return f(1) == 2 ? 0 : 1; }
```

</div>

By ¶1.2, atomic constraints subsume only when identical, and identity requires the same appearance of the same expression. On the left, the two `std::is_integral_v<T>` are two appearances; the second declaration's constraints don't subsume the first's, and the call is ambiguous. On the right, both `std::is_integral_v<T>` come from the one place in the definition of `Integral`, and `SignedIntegral` subsumes `Integral`.

So to make a constraint take part in overload ordering, define it as a concept and refer to the weaker concept by name inside the stronger one. The standard library's concept hierarchies, such as `std::integral` and `std::signed_integral`, or `std::forward_iterator` and `std::bidirectional_iterator`, are all built this way.

A requires-expression is also a single atomic constraint. `requires (T t) { t.a(); t.b(); }` and `requires (T t) { t.a(); }` have no subsumption relationship; to make them comparable, factor `t.a()` out into a concept `HasA`, then define `HasAB = HasA<T> && requires (T t) { t.b(); }`.

### Subsumption of fold expanded constraints (¶1.3) {{c++26}}

```cpp run title="fold-order.cpp" ok
#include <concepts>

template<class... Ts> requires (std::integral<Ts> && ...)
constexpr int k(Ts...) { return 1; }
template<class... Ts> requires (std::signed_integral<Ts> && ...)
constexpr int k(Ts...) { return 2; }

static_assert(k(1, 2) == 2);   // the signed_integral fold subsumes the integral fold
int main() {}
```

Both folds expand the same pack `Ts`, both operators are `&&`, and `std::signed_integral<Ts>` subsumes `std::integral<Ts>`, so the second is more constrained. In C++23 both fold expressions are ordinary atomic constraints that don't subsume each other, and this call is ambiguous.

## At least as constrained and more constrained (¶3–¶5)

```cpp run title="more-constrained.cpp" ok
#include <cstdio>
template<typename T> concept C1 = requires(T t) { --t; };
template<typename T> concept C2 = C1<T> && requires(T t) { *t; };

template<C1 T> void f(T) { std::puts("#1"); }
template<C2 T> void f(T) { std::puts("#2"); }
template<typename T> void g(T) { std::puts("#3"); }
template<C1 T> void g(T) { std::puts("#4"); }

int main() {
    f(0);           // #1: int doesn't satisfy C2
    f((int*)0);     // #2: both satisfied, C2 subsumes C1
    g(true);        // #3: bool can't be decremented, C1<bool> not satisfied
    g(0);           // #4: both satisfied, #4 has constraints and #3 doesn't
}
```

Subsumption is a relation between constraints; overload resolution compares declarations. ¶4 A declaration `D1` is **at least as constrained** as `D2` if:

- ¶4.1 both are constrained, the associated constraints of `D1` are eligible for subsumption (see below), and they subsume the associated constraints of `D2`; or
- ¶4.2 `D2` has no associated constraints.

¶5 If `D1` is at least as constrained as `D2` and `D2` is not at least as constrained as `D1`, then `D1` is **more constrained** ([[g:more-constrained|more constrained]]) than `D2`. In the example above `g(0)` picks #4 by ¶4.2: every declaration is at least as constrained as an unconstrained one. Two unconstrained declarations are each at least as constrained as the other, and neither is more constrained.

¶3 {{c++26}} If the associated constraints of a declaration contain a concept-dependent constraint ([[temp.constr.concept]], of the form `X<T>` where `X` is a concept template parameter), they are **not eligible for subsumption**; otherwise they are eligible. `X<T>` can't be expanded at the template definition, could later be any concept, and can't be compared with other constraints.

### Example 3 in the standard: the wording and the example disagree

```cpp
template<template<typename T> concept CT, typename T>
struct S {};
template<typename T>
concept A = true;

template<template<typename T> concept X, typename T>
int f(S<X, T>) requires A<T> { return 42; }      // #1
template<template<typename T> concept X, typename T>
int f(S<X, T>) requires X<T> { return 43; }      // #2

int r = f(S<A, int>{});   // standard's comment: OK, picks #1 because #2 is not eligible for subsumption
```

!!! lawyer "Read literally, it is ambiguous"
    For #1 to be at least as constrained as #2, ¶4.1 requires #1's constraints (the atomic constraint `true` in the definition of `A`) to subsume #2's constraints (the concept-dependent constraint `X<T>`). By ¶1.2, atomic constraints subsume only when identical, and `true` is not identical to `X<T>`. On the other hand, #2's constraints are not eligible for subsumption, so #2 is not at least as constrained as #1 either. Read literally, neither is more constrained, and the call is ambiguous.

    The example clearly intends a declaration that isn't eligible for subsumption to lose the comparison, but the normative wording doesn't say so. Clang 23 reports this call as ambiguous. Before relying on this behavior, check the latest draft and the related core issues.

## Ordering non-template functions by constraints (¶6)

¶6 A non-template function `F1` is **more partial-ordering-constrained** than a non-template function `F2` if all of the following hold:

- ¶6.1 they have the same non-object-parameter-type-lists ([[dcl.fct]]);
- ¶6.2 if they are member functions, both are direct members of the same class;
- ¶6.3 if both are non-static member functions, they have the same types for their object parameters;
- ¶6.4 the declaration of `F1` is more constrained than the declaration of `F2`.

How can a non-template function have constraints? A member function of a class template is not a template, but it is a templated entity and can have a trailing *requires-clause*. When two such candidates have indistinguishable conversion sequences, the more partial-ordering-constrained one wins ([[over.match.best#2.6]]); taking the address of a function picks by the same rule ([[over.over]]).

```cpp run title="non-template.cpp" ok
#include <string>
#include <type_traits>

template<class T>
struct W {
    int f() requires std::is_integral_v<T> { return 1; }
    int f() { return 2; }       // unconstrained
};
int a = W<int>{}.f();       // 1: both viable, the first is more partial-ordering-constrained
int b = W<double>{}.f();    // 2: the first is not satisfied

// Selecting a destructor by constraints
template<class T>
struct Box {
    T t;
    ~Box() requires std::is_trivially_destructible_v<T> = default;
    ~Box() {}
};
static_assert(std::is_trivially_destructible_v<Box<int>>);
static_assert(!std::is_trivially_destructible_v<Box<std::string>>);
int main() {}
```

`Box` shows the most important use of this rule. `std::optional` and `std::variant` are required to be trivially destructible when `T` is. Before C++20 this could only be done by inheriting from a conditionally specialized base class; C++20 lets a class declare several **prospective destructors** ([[class.dtor]]), and overload resolution picks the actual destructor by constraints. Copy and move constructors and assignment operators can be made conditionally trivial the same way.

¶6.1–¶6.3 limit the comparison to functions with the same signature that differ only in constraints. Otherwise `void f(int) requires A` and `void f(long) requires B` would also be ordered by constraints, and a function whose parameter types match worse could win by having more constraints.

## Where this partial ordering is used (¶2)

¶2 Note 1 lists the uses of the subsumption relation:

- ¶2.1 choosing the best viable function among non-template functions ([[over.match.best]]);
- ¶2.2 taking the address of a non-template function ([[over.over]]);
- ¶2.3 matching template template arguments ([[temp.arg.template]]);
- ¶2.4 partial ordering of class template partial specializations ([[temp.spec.partial.order]]);
- ¶2.5 partial ordering of function templates ([[temp.func.order]]).

## Implementation notes

!!! impl "The cost of normal forms, and diagnostics"
    - Conversion to a normal form is exponential in the worst case. The DNF of `(A1 ∨ B1) ∧ (A2 ∨ B2) ∧ ... ∧ (An ∨ Bn)` has 2ⁿ clauses. Constraints in real code rarely get that complex.
    - When Clang 23 reports an ambiguity and finds two atomic constraints that are written the same but aren't identical, it adds a note: similar constraint expressions are not considered equivalent unless they originate from the same concept.

## History

!!! history
    - C++20 introduced, together with concepts, the subsumption rules based on DNF and CNF, and the ordering of non-template functions by constraints (used for prospective destructors and similar).
    - C++26 added subsumption between fold expanded constraints (¶1.3, [[P2963R3]]), and the eligibility-for-subsumption restriction that came with concept template parameters (¶3, [[P2841]]).

## Common misconceptions

!!! pitfall "A semantically stronger constraint is more constrained"
    Subsumption looks only at structure and identity; `sizeof(T) > 4` doesn't subsume `sizeof(T) > 2`.

!!! pitfall "Do parentheses or wrapping affect subsumption?"
    `(C<T> && D<T>)` subsumes `C<T>` just as `C<T> && D<T>` does; parentheses have no effect during normalization. But `bool(C<T> && D<T>)` or `(C<T> && D<T>) == true` turns the whole thing into one atomic constraint that no longer subsumes anything else.

!!! pitfall "The compiler takes advantage of `!A<T>` and `A<T>` being mutually exclusive"
    It doesn't. Subsumption has no negation; `!A<T>` is just another atomic constraint.

!!! pitfall "Of two constraints that don't subsume each other, the one with more conditions is chosen"
    The number of conditions means nothing. If neither subsumes the other, the call is ambiguous.

## Questions

!!! question "Question 1"
    Let `A`, `B` and `C` be atomic constraints. Does `(A ∨ B) ∧ C` subsume `A ∨ (B ∧ C)`? What about the other way round?

<details markdown="1">
<summary>Answer</summary>

The DNF of `P = (A ∨ B) ∧ C` is `(A ∧ C) ∨ (B ∧ C)`. The CNF of `Q = A ∨ (B ∧ C)` is `(A ∨ B) ∧ (A ∨ C)`.

- `A ∧ C` shares `A` with `A ∨ B`, and also with `A ∨ C`;
- `B ∧ C` shares `B` with `A ∨ B`, and `C` with `A ∨ C`.

So `P` subsumes `Q`.

The other way round, the DNF clauses of `Q` are `A` and `B ∧ C`, and the CNF clauses of `P` are `A ∨ B` and `C`. Clause `A` shares no atom with `C`, so `Q` doesn't subsume `P`. This agrees with propositional logic: when `P` holds, `C` holds and at least one of `A`, `B` holds, so `A` or `B ∧ C` holds.
</details>

!!! question "Question 2"
    Which one does the following call choose?

    ```cpp
    template<class T> concept C = true;
    template<class T> concept D = C<T>;
    template<class T> int f(T) requires C<T>;
    template<class T> int f(T) requires D<T>;
    int x = f(0);
    ```

<details markdown="1">
<summary>Answer</summary>

It's ambiguous. `D<T>` normalizes to the normal form of `C<T>`, the atomic constraint `true` in the definition of `C`; `C<T>` also normalizes to that same `true`. The two declarations have identical associated constraints, they subsume each other, and neither is more constrained. Different concept names don't mean different constraints.
</details>

!!! question "Question 3"
    Why does ¶6 require two non-template functions to have the same non-object-parameter-type-lists before comparing them by constraints?

<details markdown="1">
<summary>Answer</summary>

Constraints should only break ties when everything else is equal. If functions with different parameter types were also ordered by constraints, a function with a worse parameter match but more constraints could win, which would also be inconsistent with partial ordering of function templates: function templates compare constraints only when they are equally specialized by deduction ([[temp.func.order]]). ¶6.1–¶6.3 restrict the comparison to functions in the same class with the same signature, which is exactly what prospective destructors and conditionally trivial special member functions need.
</details>
