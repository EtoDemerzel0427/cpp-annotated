---
title: Concepts library
summary: "The overall design of Clause 18: every library concept consists of syntactic requirements checked by the compiler and semantic requirements vouched for by the programmer; satisfying looks only at syntax, while modeling also requires meeting the semantics; the semantic requirement running through the whole library is equality preservation."
updated: 2026-10-19
---

!!! tldr
    - Every library concept has two layers of requirements: syntactic requirements checked by the compiler, and semantic requirements written only in the wording and vouched for by the programmer.
    - Meeting only the syntax is called satisfying; meeting both layers is called modeling. A program that depends on a concept being modeled when it is only satisfied is IFNDR.
    - Expressions in the library's requires-expressions are required to be equality-preserving by default: equal inputs give equal outputs, and two evaluations on the same object give the same result.
    - Concepts write out only the const lvalue form; non-const and rvalue forms are implicitly required too, but the compiler doesn't necessarily check them.
    - Standard library concepts refer to each other by name so that subsumption works; concepts that refine only semantically (such as `regular_invocable`) don't take part in ordering for overload resolution.

## Compiling doesn't mean meeting the requirements

```cpp run title="stateful-predicate.cpp" ifndr
#include <cstdio>
#include <ranges>

int main() {
  int calls = 0;
  // the result depends on the number of calls: not equality-preserving
  auto first_three = [&calls](int) { return calls++ < 3; };
  auto v = std::views::iota(0, 6) | std::views::filter(first_three);
  for (int i : v) std::printf("%d ", i);   // first pass
  std::puts("");
  for (int i : v) std::printf("%d ", i);   // second pass
  std::puts("");
}
```

`views::filter` requires the predicate to satisfy `indirect_unary_predicate`, which ultimately requires `regular_invocable`: callable with these arguments, returning something usable as `bool`. `first_three` fits completely, so the program compiles without trouble.

But running it with libc++ (Clang 23), the first pass prints `0 1 2` and the second prints only `0`. The reason is that `filter_view` caches the result of its first `begin()` call, and this predicate gives different answers for the same element on two calls. Besides being callable, `regular_invocable` requires the call to be equality-preserving and not to modify its arguments, which this predicate can't do.

The core language's concept mechanism ([[temp.concept]], [[temp.constr]]; see also [[topics/concepts]]) answers only one question: whether the given template arguments make the constraint expression `true`, i.e. whether the code compiles. It doesn't know whether `==` really compares for equality or whether `<` is an order. Yet generic algorithms depend on exactly that: `sort` depends on the comparator being a strict weak ordering, `find` on `==` being an equivalence relation, and `filter_view` on the predicate always giving the same answer for the same element.

¶1 [concepts.general] Clause 18 gives these conventions names and writes them as normative requirements.

!!! std
    The purpose of these concepts is to establish a foundation for equational reasoning in programs.

**Equational reasoning** means deducing the behavior of code by substituting equals for equals, as in algebra: when `a == b`, replacing `a` with `b` in a suitable expression doesn't change the result.

## Satisfying and modeling

Every concept in this clause consists of two parts:

- **syntactic requirements**: the concept definition itself, the `concept C = ...;` line, checked by the compiler;
- **semantic requirements**: the prose after the definition, of the form "`T` models `C` only if ...", not checked by the compiler and vouched for by the programmer.

!!! std
    A sequence Args of template arguments is said to *model* a concept C if Args satisfies C and meets all semantic requirements (if any) given in the specification of C.

This definition is in the library's general rules, [[res.on.requirements#1]]. **Satisfaction** ([[g:constraint-satisfaction]]) is a core language notion: the constraint, with the arguments substituted, evaluates to `true` ([[temp.constr.atomic]]), which the compiler can decide. **Modeling** ([[g:models-concept]]) is a library notion: satisfying plus meeting all the semantic requirements, which the compiler in principle can't decide.

[[res.on.requirements]] specifies two consequences of satisfying without modeling:

- ¶2 If the validity or meaning of a program depends on whether a sequence of arguments models a concept, and the concept is satisfied but not modeled, the program is IFNDR: ill-formed, no diagnostic required;
- ¶3 If a declaration's constraints carry semantic requirements that aren't modeled at the point of use, the program is IFNDR too.

[[structure.requirements#9]] adds that when a library function's constraints refer to a concept, the semantic requirements of that concept are imposed on uses of the function as well. So the opening program is IFNDR; likewise, passing `<=` as the comparator to `std::ranges::sort` satisfies `strict_weak_order` syntactically but isn't a strict weak ordering semantically, so that program is IFNDR too. The consequence isn't just a wrong sort result; the whole program loses every guarantee the standard gives.

!!! note "Why IFNDR rather than UB"
    Violating a semantic requirement is regarded as the program itself being non-conforming, a static property of the program, rather than a particular execution doing something illegal. Diagnosing it would require proving mathematical properties of arbitrary code, which is generally undecidable, so the standard requires no diagnostic. In practice the effect is very close to UB: the implementation may assume the semantic requirements hold and design algorithms and optimizations accordingly.

[[structure.requirements#8]] also says that the operations a concept requires need not be total functions, i.e. they need not meet the semantics for all arguments. `double`'s `<` doesn't meet the semantic requirements of `totally_ordered` for NaN, but that doesn't stop `double` from modeling `totally_ordered`. So both of these statements hold: `double` models `totally_ordered`; don't hand data containing NaN to `ranges::sort`. The domain in the next section is about exactly this.

## Equality preservation [concepts.equality]

The semantic requirements of almost every concept in this clause come down to some expression being equality-preserving, and the same is true of the concepts in `<iterator>` and `<ranges>`.

### Inputs and outputs (¶1)

!!! std
    An expression is *equality-preserving* if, given equal inputs, the expression results in equal outputs.

¶1 An expression is **equality-preserving** ([[g:equality-preserving]]) if, given equal inputs, it always produces equal outputs. This is the mathematical definition of a function: the same arguments give the same value.

- The **inputs** of an expression are its operands;
- The **outputs** of an expression are its result plus all the operands it modifies.

So the outputs of `a = std::move(b)` aren't just the return value of `=`, but also the modified `a` and `b`. Saying assignment is equality-preserving means that starting from equal `a` and `b`, execution yields equal `a`, equal `b` and equal return values.

Operands have a special definition here: the largest subexpressions consisting only of the following two kinds of component:

- ¶1.1 an *id-expression* ([[expr.prim.id]]), i.e. a variable name;
- ¶1.2 invocations of `std::move`, `std::forward` and `std::declval`.

Example 1: the operands of `a = std::move(b)` are `a` and `std::move(b)`. This way, the variables in a requires-expression, together with transformations of their value category, are treated as the arguments, and the remaining parts, operators and member calls, are treated as the function under consideration.

!!! note "Equality isn't `==`"
    Equality here means abstract equality of values, two objects representing the same value, not `==` returning `true`. That is precisely why the semantic requirement of `equality_comparable` has content: it requires `a == b` to be `true` if and only if `a` and `b` are equal ([[concept.equalitycomparable#2]]). `==` must reflect equality, not define it. For types without `==`, such as some `semiregular` types, equality between their objects is still meaningful.

### Domain (¶2)

¶2 Not all inputs need be valid. Example 2: integer `a / b` isn't well-defined when `b == 0`, but that doesn't stop `a / b` from being equality-preserving. The set of input values for which an expression is required to be well-defined is called its **domain** ([[g:expression-domain]]).

With domains, operations that aren't total functions can appear in concepts: NaN isn't in the domain of `double`'s `<`; two pointers into different arrays aren't in the domain of `<` ([[expr.rel]]). Note 1 of `assignable_from` likewise says that if assigning to `x` would change `y`, then `x = y` is likely not in the domain of `=`.

### Stability (¶3)

!!! std
    Expressions required to be equality-preserving are further required to be stable: two evaluations of such an expression with the same input objects are required to have equal outputs absent any explicit intervening modification of those input objects.

¶3 Expressions required to be equality-preserving must also be **stable**: two evaluations with the same input objects must have equal outputs as long as those objects aren't explicitly modified in between. ¶1 is about equal inputs, which may be different objects; ¶3 is about the same object at different times.

With stability, generic code can trust that a value it just saw will still be there when it looks again. Note 1 lists what stability in effect forbids:

- an object's value changing spontaneously;
- an object being modified by another thread;
- an object changing as a side effect of a non-modifying expression, for example a const member function changing an observable `mutable` member;
- an object changing as a side effect of modifying another object (aliasing), in a way a library function could observe through an equality-preserving expression.

### Required by default unless annotated (¶4)

!!! std
    Expressions declared in a *requires-expression* in the library clauses are required to be equality-preserving, except for those annotated with the comment "not required to be equality-preserving."

¶4 Expressions declared in requires-expressions in the library clauses are required to be equality-preserving by default, except those annotated with "not required to be equality-preserving". That is why the definition of `equality_comparable` doesn't say `==` must be equality-preserving: ¶4 already says it.

The most common exemption is `invocable`:

```cpp
template<class F, class... Args>
  concept invocable = requires(F&& f, Args&&... args) {
    invoke(std::forward<F>(f), std::forward<Args>(args)...);
      // not required to be equality-preserving
  };
```

So a random number generator can model `invocable` ([[concept.invocable#2]]) but not `regular_invocable` ([[concept.regularinvocable#2]]), which revokes exactly this exemption. `++i` and `*i` of input iterators are also exempt, since single-pass traversal isn't stable by nature.

An exempt expression may still be equality-preserving; it just isn't required to be.

### Which operands may be modified (¶5)

¶5 An expression **modifies** an input if it changes the input's value in a way observable by equality-preserving expressions. There is a convention for reading requires-expressions:

- a non-const lvalue or rvalue operand may be modified;
- a const lvalue or rvalue operand shall not be modified.

For determining constness and value category, each template type parameter is assumed to denote a cv-unqualified complete non-array object type. So in `requires(T a, const T c)`, `a` is a modifiable lvalue, `c` is a non-modifiable lvalue, and `std::move(a)` is a modifiable rvalue.

### Implicit expression variations (¶6–¶8)

When a concept's author writes `c == d` (with `c` and `d` both `const T`), the intent is that objects of `T` can be compared with `==`, not that only const lvalues can be compared. If every concept had to list all combinations of const and non-const, lvalue and rvalue, the definitions would balloon several times over.

!!! std
    Where a *requires-expression* declares an expression that is non-modifying for some constant lvalue operand, additional variations of that expression that accept a non-constant lvalue or (possibly constant) rvalue for the given operand are also required ...

¶6 So the standard says: when an expression in a requires-expression is non-modifying for some const lvalue operand, the variations obtained by replacing that operand with a non-const lvalue or an rvalue (const or not) are also required, with the same semantics, including not modifying that operand. These variations are called **implicit expression variations** ([[g:implicit-expression-variation]]). If some variation is already explicitly required with different semantics, it isn't implicitly required.

¶7 Example 3 shows the various cases:

```cpp
template<class T> concept C = requires(T a, T b, const T c, const T d) {
  c == d;           // #1
  a = std::move(b); // #2
  a = c;            // #3
};
```

- ¶7.1 #1 modifies neither operand, #2 modifies both operands, and #3 modifies only `a`.
- ¶7.2 #1 implicitly requires `c == b`, `std::move(c) == d`, `a == std::move(b)` and the remaining 15 combinations, none of which may modify the operands.
- ¶7.3 #3 implicitly requires `a = b` and `a = std::move(c)`, but not the version whose second operand is a non-const rvalue, because #2 already requires it explicitly with different semantics: #2 allows `b` to be modified.

The last sentence of ¶6 is: the extent to which an implementation validates the syntax of these variations is unspecified. ¶8 Example 4 shows the consequence:

```cpp
struct T {
  bool operator==(const T&) const { return true; }
  bool operator==(T&) = delete;
};
```

`T` meets the syntactic requirements `C` writes out explicitly, but comparing two non-const lvalues selects the deleted overload, so the implicit variation fails. So `T` satisfies but doesn't model `C`, and whether the implementation diagnoses a program requiring `C<T>` as ill-formed is unspecified.

This isn't just a paper problem. libc++ checks only the explicitly written const lvalue form, so `std::equality_comparable<T>` is `true` and the constraint check of `ranges::find` passes, with the error appearing only when the function body compares non-const lvalues:

```cpp run title="implicit-variation.cpp" error
#include <algorithm>
#include <concepts>
#include <vector>

struct T {
  bool operator==(const T&) const { return true; }
  bool operator==(T&) = delete;
};
static_assert(std::equality_comparable<T>);   // only the const lvalue form was checked

int main() {
  std::vector<T> v(3);
  T key;
  auto it = std::ranges::find(v, key);   // error: the library internally selects the deleted ==
  (void)it;
}
```

Clang 23 reports the error in the library header `ranges_operations.h` (`overload resolution selected deleted operator '=='`), not at the constraint check. The error slips past the concept check and appears deep inside the template, the typical symptom of satisfying without modeling.

### The reasoning equality preservation enables

Put together, these rules give generic algorithms three kinds of reasoning:

1. **Repeated evaluation**. An algorithm can call a predicate or comparator on the same element several times and trust the results to agree; `sort` implementations do compare the same pair of elements repeatedly.
2. **Caching**. The `range` concept requires `begin()` to have amortized constant complexity, so `filter_view` and `drop_while_view` cache the result of the first `begin()`. The caching is correct because the predicate is required to model `regular_invocable`. The opening example breaks exactly this.
3. **Substituting equals for equals**. When `a == b` is true, replacing `a` with `b` in any equality-preserving expression doesn't change the result.

## Organization of the clause [concepts.general] [concepts.syn]

¶2 [concepts.general] This clause has five parts, as shown in Table 48, and the concepts are all in `<concepts>`:

| Subclause | Contents |
|---|---|
| [concepts.equality] | Equality preservation, the semantic foundation of the whole clause (see above) |
| [[concepts.lang]] | Language-related concepts: `same_as`, `derived_from`, `convertible_to`, `common_reference_with`, `integral`, `assignable_from`, `swappable`, `constructible_from` and others |
| [[concepts.compare]] | Comparison concepts: *`boolean-testable`*, `equality_comparable`, `totally_ordered` |
| [[concepts.object]] | Object concepts: `movable`, `copyable`, `semiregular`, `regular` |
| [[concepts.callable]] | Callable concepts: `invocable`, `predicate`, `relation`, `strict_weak_order` and others |

`<iterator>`, `<ranges>`, and `three_way_comparable` in `<compare>` ([[cmp.concept]]) are all built on this clause.

[concepts.syn] The header `<concepts>` is entirely freestanding and must be provided by freestanding implementations ([[g:freestanding-implementation]]) too, since it contains only concept definitions and one customization point object and needs no run-time support. The only thing in the synopsis that isn't a concept is:

```cpp
namespace ranges {
  inline namespace unspecified {
    inline constexpr unspecified swap = unspecified;
  }
}
```

`ranges::swap` is a **customization point object** ([[g:customization-point-object]], [[customization.point.object]]), a function object that dispatches by fixed rules to a user customization or a default implementation; see [[concept.swappable]] for details. It sits in an inline namespace with an unspecified name so that types in `std::ranges` can have hidden friends named `swap` without clashing with it: the object's name is in the inner namespace, while the hidden friends' names belong to the outer `std::ranges`, so they aren't in the same scope.

## How concepts refine each other

The concepts in this clause refer to each other by name, forming a graph of refinement relations:

```text
destructible ← constructible_from ← default_initializable
                                  ← move_constructible ← copy_constructible
movable     = object ∧ move_constructible ∧ assignable_from<T&, T> ∧ swappable
copyable    = copy_constructible ∧ movable ∧ assignable_from<T&, T&> ∧ …
semiregular = copyable ∧ default_initializable
regular     = semiregular ∧ equality_comparable

invocable ← regular_invocable ← predicate ← relation ← equivalence_relation
                                                    ← strict_weak_order
equality_comparable ← totally_ordered
```

By [[temp.constr.order]], two constraints can be compared for subsumption only if they come from the same place in the same concept definition. So the standard library always writes `concept B = A<T> && ...` rather than copying the definition of `A`. That way `regular<T>` subsumes `semiregular<T>`, `f(std::regular auto)` is more constrained than `f(std::semiregular auto)`, and `f(1)` selects the former.

A few definitions designed for subsumption, or worth noting:

- `same_as<T, U>` is written as `same-as-impl<T, U> && same-as-impl<U, T>`, so `same_as<T, U>` and `same_as<U, T>` subsume each other ([[concept.same]]).
- Wherever a type trait would be written directly, it is wrapped in a concept, for example `integral<T>` rather than `is_integral_v<T>` directly. The reason is the same: the atomic constraint `is_integral_v<T>` counts as the same constraint only if it appears in the same concept definition.
- Concepts that refine only semantically don't take part in ordering. `regular_invocable<F>` is defined as just `invocable<F>`, and `strict_weak_order` and `equivalence_relation` are both defined as `relation<R, T, U>`. Normalization expands a concept into its definition ([[temp.constr.normal]]), so after normalization they are identical to the concepts they refine, subsume each other, and neither is more constrained.

<div class="compare" markdown="1">

```cpp run ok
#include <concepts>
int g(std::semiregular auto) { return 1; }
int g(std::regular auto) { return 2; }
int y = g(1);   // OK: selects the regular version
```

```cpp run error
#include <concepts>
template<std::invocable F>
int f(F) { return 1; }
template<std::regular_invocable F>
int f(F) { return 2; }
int x = f([]{});   // error: ambiguous
```

</div>

A purely semantic refinement is only a contract written for programmers and doesn't take part in overload resolution (see also [[concepts.callable]]).

!!! history
    The concepts library was introduced in C++20 by [[P0898R3]], coming from the Ranges TS. Equality preservation, semantic requirements and the distinction between satisfying and modeling had already taken shape in the Ranges TS. Concepts were originally named in `PascalCase` (`EqualityComparable`); [[P1754R1]] changed them to today's `snake_case`. The main later changes were concentrated in the comparison concepts, such as *`boolean-testable`* and support for move-only types; see [[concepts.compare]].

## Common misconceptions

!!! pitfall "The `static_assert` passed, so the type is safe to use"
    `static_assert(std::regular<T>)` proves only satisfaction. `T`'s `==` might not be an equivalence relation, and a copy might not equal the original; these can only be caught by code review and testing.

!!! pitfall "Providing the semantics for the const version is enough"
    Concepts write out only the const lvalue form, but the implicit variations require non-const and rvalue forms to be usable as well, with the same semantics. Providing an overload for `T&` with different semantics, or deleting it, makes the type satisfy without modeling, and the error may appear deep inside the library implementation.

!!! pitfall "Stateful function objects"
    Wherever `predicate`, `regular_invocable` or `indirect_*` constrain something, a function object whose result depends on the number of calls violates the semantic requirements. The old `std::` algorithms usually also had requirements on function objects, such as not modifying their arguments; the ranges algorithms turned them into formal requirements expressed with concepts.

## Questions

!!! question "Question 1"
    Which expressions does `requires(const T a, const T b) { a < b; }` implicitly require? If `T` also has a `bool operator<(T&&) const` that steals the right operand's resources, does `T` model this concept?

<details markdown="1">
<summary>Answer</summary>

It implicitly requires every combination obtained by replacing `a` and `b` with a non-const lvalue, a const rvalue or a non-const rvalue, and none of them may modify the operands (¶6). When the right operand is a non-const rvalue, `operator<(T&&)` is selected, which modifies the operand, violating the non-modifying semantic requirement. So `T` satisfies but doesn't model the concept. Whether the implementation diagnoses it is unspecified (the last sentence of ¶6).
</details>

!!! question "Question 2"
    Does `std::uniform_int_distribution<int>` with `std::mt19937&` model `invocable`? Does it model `regular_invocable`? Can the compiler tell the two cases apart?

<details markdown="1">
<summary>Answer</summary>

It models `invocable`, whose call expression is exempt from equality preservation ([[concept.invocable#2]]). It doesn't model `regular_invocable` ([[concept.regularinvocable#2]]). The compiler can't tell them apart: the syntactic requirements are identical ([[concept.regularinvocable#3]]), and `std::regular_invocable<...>` is `true` all the same.
</details>

!!! question "Question 3"
    Note 1 on stability forbids an object being modified by another thread. How does this differ from data races causing UB in [[intro.races]]?

<details markdown="1">
<summary>Answer</summary>

Stability is a semantic requirement, and violating it makes the program IFNDR ([[res.on.requirements]]). Even if another thread modifies the object with atomic operations, which under [[intro.races]] isn't a data race, stability is still violated. So the concepts' requirement is stronger than freedom from data races: even without UB, the value must not change while the algorithm is observing it.
</details>
