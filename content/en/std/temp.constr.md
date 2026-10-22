---
title: Template constraints
summary: "How constraint expressions are normalized into constraints built from conjunctions, disjunctions and atomic constraints; how satisfaction checking short-circuits and absorbs substitution failure; why an atomic constraint must be exactly bool and when two are identical; the order in which a declaration's associated constraints are formed; C++26 fold expanded constraints and concept-dependent constraints."
updated: 2026-10-19
---

!!! tldr
    - A constraint expression is first normalized: it is split at `&&` and `||`, the concepts in it are expanded, and the parts that can't be split further are called atomic constraints.
    - Satisfaction is checked left to right with short-circuiting; parts that are never reached are never substituted into. When substitution into an atomic constraint fails, it is just not satisfied, not an error.
    - After substitution an atomic constraint must be a constant expression of type exactly `bool`; an `int` or a class with `operator bool` makes the program ill-formed.
    - Two atomic constraints are identical only if they come from the same expression at the same place in the source. To make a constraint take part in overload ordering, write it as a concept.
    - `!E` and a requires-expression are each a single atomic constraint; since C++26, `&&` and `||` fold expressions can be taken apart and compared.

## What a constraint is

```cpp run title="short-circuit.cpp" ok
template<typename T>
constexpr bool get_value() { return T::value; }

template<typename T>
  requires (sizeof(T) > 1) && (get_value<T>())
void f(T) {}       // associated constraints: sizeof(T) > 1  ∧  get_value<T>()

void f(int) {}

int main() {
    f('a');        // OK: calls f(int)
}
```

For the call `f('a')`, the template's first condition `sizeof(char) > 1` is false, and the second condition `get_value<char>()` is never instantiated. Had it been instantiated, `char::value` would have caused an unrecoverable error in the function body.

So the expression after `requires` is not evaluated as one ordinary `bool` expression. A **constraint** ([[g:constraint]]), as defined in [temp.constr.constr.general] ¶1, is a sequence of logical operations and operands that specifies requirements on template arguments; the operands are themselves constraints. There are five kinds:

| Kind | Comes from | Rules |
|---|---|---|
| conjunction, written ∧ | `E1 && E2` | [temp.constr.op] |
| disjunction, written ∨ | `E1 \|\| E2` | [temp.constr.op] |
| atomic constraint | any other expression | [temp.constr.atomic] |
| fold expanded constraint {{c++26}} | `(E && ...)`, `(E \|\| ...)` | [temp.constr.fold] |
| concept-dependent constraint {{c++26}} | `CT<T>`, where `CT` is a concept template parameter | [temp.constr.concept] |

∧ and ∨ are not C++ syntax; the standard uses these symbols to distinguish them from `&&` and `||` in expressions ([temp.constr.op] ¶1).

This structure serves two purposes. The first is satisfaction checking: given the arguments, does the constraint hold, with short-circuiting and tolerance of substitution failure. The second is deciding which of two constraints is stronger ([[temp.constr.order]]). Implication between two arbitrary `bool` expressions can't be decided, but once constraints are and/or combinations of atomic propositions, and atoms are compared only by identity, implication becomes a simple problem in propositional logic.

[temp.constr.constr.general] ¶2 For a constrained template to be instantiated, its associated constraints must be satisfied. Note 1 points out two common places where this happens: naming a specialization of a class template, variable template or alias template checks its constraints ([[temp.names]]), and overload resolution requires a candidate function's constraints to be satisfied ([[over.match.viable]]).

## Normalization: from expressions to constraints [temp.constr.normal]

```cpp
#include <type_traits>
template<class T> concept Big    = sizeof(T) > 8;
template<class T> concept BigInt = Big<T> && std::is_integral_v<T>;

template<class U> void g(U) requires BigInt<U*> || (sizeof(U) == 1);
```

After normalization, the constraints of `g` are:

```text
( sizeof(T) > 8          [T ↦ U*]
  ∧ std::is_integral_v<T> [T ↦ U*] )
∨ sizeof(U) == 1          [U ↦ U]
```

¶1 The **normal form** of an expression `E` is obtained level by level by these rules:

| Item | Expression | Normal form |
|---|---|---|
| ¶1.1 | `( E )` | the normal form of `E`; parentheses have no effect |
| ¶1.2 | `E1 \|\| E2` | the disjunction of the normal forms of `E1` and `E2` |
| ¶1.3 | `E1 && E2` | the conjunction of the normal forms of `E1` and `E2` |
| ¶1.4 | a concept specialization `C<A1, ..., An>` | expand the definition of `C`, see below |
| ¶1.5 | a fold expression over `&&` or `\|\|` | a fold expanded constraint, see later |
| ¶1.6 | any other expression | an atomic constraint |

¶2 The process of obtaining the normal form is called **normalization** ([[g:normalization]]). Note 1 says it happens at two times: when determining the associated constraints of a declaration, and when evaluating a concept specialization such as `BigInt<int>`.

¶1.2 and ¶1.3 split syntactically. Normalization happens at the template definition, when it isn't yet known whether `&&` would call an overloaded `operator&&`, so overloading is simply not considered: each side is a constraint on its own, and each must be `bool`.

### Atomic constraints and parameter mappings [temp.constr.atomic]

[temp.constr.atomic] ¶1 An **atomic constraint** ([[g:atomic-constraint]]) consists of an expression `E` and a **parameter mapping**. The parameter mapping records which argument each template parameter appearing in `E` is mapped to. Note 1 adds that `E` is never an `&&` or `||` expression, because those were split apart during normalization.

In the example above, the `E` of the first atomic constraint is `sizeof(T) > 8` exactly as written in the definition of `Big`, and the mapping is `T ↦ U*`; it is not the substituted `sizeof(U*) > 8`. The substitution is stored in the mapping, and the expression itself stays as it appears in the source. That is what later determines whether two atomic constraints are identical. Only the parameters actually used in `E` appear in the mapping; an atomic constraint like `true` has an empty mapping.

### Concepts are expanded during normalization (¶1.4)

¶1.4.2 For a concept specialization `C<A1, ..., An>`, normalization first takes the normal form of the constraint expression of `C`, then replaces the parameters of `C` appearing in each atomic constraint's mapping with the arguments `A1, ..., An` given here. In other words, concepts are inlined and mappings are composed: `BigInt<U*>` expands to `Big<T> && is_integral_v<T>` (`T ↦ U*`), and `Big<T>` expands further to `sizeof(T) > 8`, where the composed mapping is still `T ↦ U*`.

If composing a mapping forms an invalid type, the program is ill-formed, no diagnostic required (IFNDR). Example 1 from the standard:

```cpp title="normal-ifndr.cpp" ifndr
template<typename T> concept A = T::value || true;
template<typename U> concept B = A<U*>;
template<typename V> concept C = B<V&>;   // IFNDR
```

- Normalizing `B` is fine and gives `T::value` (`T ↦ U*`) ∨ `true` (empty mapping). A pointer type obviously has no `::value`, but the mapping `T ↦ U*` is a valid type in itself; the problem only shows up during satisfaction checking, where it just means "not satisfied".
- Normalizing `C` has to form the mapping `T ↦ V&*`, and a pointer to reference is not a valid type, so the program is IFNDR. Clang 23 gives no diagnostic at all.

¶1.6 All other expressions are atomic constraints, including requires-expressions. Example 2 under ¶3 gives a few contrasts:

```cpp
template<typename T> concept C1 = sizeof(T) == 1;
template<typename T> concept C2 = C1<T> && 1 == 2;
template<typename T> concept C3 = requires { typename T::type; };

template<C2 U> void f1(U);   // sizeof(T) == 1 [T ↦ U] ∧ 1 == 2
template<C3 U> void f2(U);   // requires { typename T::type; } [T ↦ U], as a whole
```

A requires-expression is not taken apart, so `requires { a; b; }` and `requires { a; }` have no structural relationship. To make them comparable, factor the common part out into a concept:

```cpp
template<class T> concept HasA  = requires (T t) { t.a(); };
template<class T> concept HasAB = HasA<T> && requires (T t) { t.b(); };   // HasAB is stronger than HasA
```

## Satisfaction checking

### Conjunction and disjunction short-circuit [temp.constr.op]

[temp.constr.op] ¶2 To check a conjunction, the left operand is checked first; if it is not satisfied, the conjunction is not satisfied, otherwise the right operand decides. ¶3 To check a disjunction, the left operand is checked first; if it is satisfied, the disjunction is satisfied, otherwise the right operand decides.

This short-circuits more thoroughly than the run-time `&&` and `||`. An operand that isn't checked is never substituted into, so neither its substitution failures nor any instantiations that would cause hard errors take place. The `f('a')` at the top of this page is the standard's Example 1.

### Satisfaction of an atomic constraint (¶3)

[temp.constr.atomic] ¶3 Whether an atomic constraint is satisfied is decided in four steps:

1. Substitute the parameter mapping and the template arguments into the expression.
2. If substitution produces an invalid type or expression in the **immediate context** of the atomic constraint ([[temp.deduct.general]]), the constraint is not satisfied. This is not an error.
3. Otherwise, after lvalue-to-rvalue conversion if necessary, `E` must be a constant expression of type `bool`.
4. The constraint is satisfied if and only if `E` evaluates to `true`.

Step 3 performs no implicit conversion. If the type is `int`, or a class with `operator bool`, the program is ill-formed; the constraint is not merely unsatisfied:

```cpp title="must-be-bool.cpp" error
template<class T> struct W { static constexpr int value = 1; };

template<class T> requires (W<T>::value) void f(T) {}          // the atomic constraint has type const int
template<class T> requires (bool(W<T>::value)) void g(T) {}    // OK: explicit conversion to bool

int main() {
    f(0);    // error: atomic constraint must be of type bool
    g(0);    // OK
}
```

As a result, code that meant to check whether `T::value` exists but was written as `requires (T::value)` is rejected outright when `value` is an `int`, instead of being silently converted. To check for existence, write `requires { T::value; }`.

Example 3 in the standard stresses that this error occurs during satisfaction checking, and a better candidate can't save it:

```cpp title="not-bool-hard-error.cpp" error
template<typename T> struct S {
    constexpr operator bool() const { return true; }
};

template<typename T> requires (S<T>{})
void f(T);                      // #1
void f(int);                    // #2

void g() {
    f(0);    // error: when checking #1's constraints, S<int>{} is not of type bool;
             //        #2 being a better match doesn't help
}
```

!!! impl "Clang 23 accepts this code"
    When the non-template candidate `f(int)` is an exact match, Clang skips the template candidate's constraint check, so it never runs into this error. Only after `f(int)` is removed does Clang report atomic constraint must be of type 'bool'. Per the standard, the call in the original example is ill-formed.

### Errors outside the immediate context are hard errors

Step 2 only absorbs substitution failures in the immediate context. If substitution triggers the instantiation of another template and the error occurs inside that instantiation, it is a hard error:

<div class="compare" markdown="1">

```cpp error
template<class T>
constexpr bool hard() {
  return T::value;
}
template<class T>
  requires (hard<T>())
void f(T) {}
void f(long) {}

int main() {
  f(0);  // error: int::value appears in
         // the body of hard<int>
}
```

```cpp run ok
template<class T>
  requires (T::value)
void f(T) {}
void f(long) {}

int main() {
  f(0);  // OK: int::value fails in the immediate
         // context, constraint not satisfied, calls f(long)
}
```

</div>

### Satisfaction results must be stable (last sentence of ¶3)

The last sentence of ¶3 says: if, at different points in the program, the same atomic constraint with the same template arguments gives different satisfaction results, the program is IFNDR.

```cpp title="unstable.cpp" ifndr
template<class T> concept Complete = requires { sizeof(T); };

struct S;
static_assert(!Complete<S>);   // S is incomplete here: not satisfied
struct S {};
static_assert(Complete<S>);    // IFNDR: same atomic constraint, same arguments, different result
```

This rule lets compilers cache satisfaction results, checking each atomic constraint with a given set of arguments only once. Clang 23 does exactly that: the second `static_assert` fails, because Clang reuses the result of the first check, and it reports applying `sizeof` to the incomplete type `S`.

!!! warning "Don't write concepts that detect completeness"
    `Complete<T>`, or a concept that detects whether some overload has been declared yet, or any other concept that depends on the point in the program, almost inevitably violates this rule.

## When atomic constraints are identical [temp.constr.atomic]

```cpp title="same-appearance.cpp" error
#include <type_traits>

template<class T> concept Integral = std::is_integral_v<T>;

// Through a named concept: both std::is_integral_v<T> come from the definition of Integral
template<class T> int a(T) requires Integral<T> { return 1; }
template<class T> int a(T) requires Integral<T> && std::is_signed_v<T> { return 2; }
int ra = a(1);     // OK: picks the second; its constraints subsume the first's

// Written out twice: the two std::is_integral_v<T> are different appearances
template<class T> int b(T) requires std::is_integral_v<T> { return 1; }
template<class T> int b(T) requires std::is_integral_v<T> && std::is_signed_v<T> { return 2; }
int rb = b(1);     // error: ambiguous
```

When both overloads are satisfied, the compiler has to compare which one's constraints are stronger ([[temp.constr.order]]). That comparison ultimately comes down to whether atomic constraints are identical.

¶2 Two atomic constraints are **identical** when two conditions hold:

1. they are formed from the same appearance of the same *expression* in the source;
2. their parameter mappings map the parameters to the same arguments. Precisely: imagine a template whose parameters are the parameters involved in the mappings, and write its specializations using the targets of each mapping as arguments; the two specializations are the same type per [[temp.type]].

Condition 1 is the key. Each declaration of `b` writes out `std::is_integral_v<T>` once; the tokens are identical, but they are two appearances and never identical. Both declarations of `a` bring it in through `Integral<T>`, and after normalization both trace back to the one expression in the definition of `Integral`, so they are identical. For the ambiguity in `b`, Clang 23 adds a note: similar constraint expressions are not considered equivalent unless they originate from the same concept.

Deciding semantically whether two expressions are the same is undecidable; comparing tokens is fragile, since it's unclear how to treat `a+b` versus `b+a` or tokens coming from macro expansion. Deciding by "same appearance" avoids these problems: identity can only be established by giving the constraint a name.

### Comparing mappings (¶2, note 2)

The way condition 2 compares mappings is similar to declaration matching involving alias templates ([[temp.alias]]). Example 1 from the standard:

```cpp run title="mapping.cpp" ok
template<unsigned N> constexpr bool Atomic = true;
template<unsigned N> concept C = Atomic<N>;
template<unsigned N> concept Add1 = C<N + 1>;
template<unsigned N> concept AddOne = C<N + 1>;

template<unsigned M> void f() requires Add1<2 * M>;
template<unsigned M> int f() requires AddOne<2 * M> && true;

int x = f<0>();    // OK: in both f the atomic constraint from C is Atomic<N>,
                   // both mappings amount to N ↦ 2 * M + 1; the second is more constrained
int main() {}
```

`Add1` and `AddOne` are two different concepts, but both expand to the same `Atomic<N>` in the definition of `C`, and the mappings `N ↦ 2 * M + 1` on both sides are equivalent expressions ([[temp.over.link]]), so the atomic constraints are identical.

If two mappings are only functionally equivalent but not equivalent, for example `2 * N` and `N * 2`, and the meaning of the program depends on whether they are identical, the program is IFNDR:

```cpp title="func-equiv.cpp" ifndr
template<unsigned N> constexpr bool Atomic = true;
template<unsigned N> concept C = Atomic<N>;
template<unsigned N> concept Add1 = C<N + 1>;

template<unsigned N> void f2() requires Add1<2 * N>;
template<unsigned N> int f2() requires Add1<N * 2> && true;
void h2() {
    f2<0>();   // IFNDR: requires deciding whether two functionally equivalent but not equivalent atomic constraints are identical
}
```

Clang 23 reports the call as ambiguous, which is one of the outcomes IFNDR allows.

## Negation is an atomic constraint [temp.constr.op]

¶5 Note 2 points out that `!E` as a whole is an atomic constraint; negation is not a logical operation on constraints. This has two consequences:

1. Two separately written `!E`, even if equivalent, are two appearances and don't subsume each other.
2. A substitution failure makes the atomic constraint unsatisfied, whether or not there is a `!` outside. If substitution into `E` fails, `!E` is not satisfied; it is not the case that `E` is false and `!E` true.

```cpp title="negation.cpp" error
template<class T> concept sad = false;

template<class T> int f1(T) requires (!sad<T>);
template<class T> int f1(T) requires (!sad<T>) && true;
int i1 = f1(42);        // error: ambiguous, the two !sad<T> are different appearances

template<class T> concept not_sad = !sad<T>;
template<class T> int f2(T) requires not_sad<T> { return 1; }
template<class T> int f2(T) requires not_sad<T> && true { return 2; }
int i2 = f2(42);        // OK: both !sad<T> come from the definition of not_sad

template<class T> int f3(T) requires (!sad<typename T::type>);
int i3 = f3(42);        // error: substitution fails, the atomic constraint !sad<int::type> is not satisfied

template<class T> concept sad_nested_type = sad<typename T::type>;
template<class T> int f4(T) requires (!sad_nested_type<T>) { return 4; }
int i4 = f4(42);        // OK: the substitution failure is wrapped in a concept, sad_nested_type<int> is false
```

`f3` and `f4` mean different things:

- `requires (!sad<typename T::type>)` requires that a nested type `type` exists and that it is not sad;
- `requires (!sad_nested_type<T>)` requires that there is no sad nested type; having no nested type at all also counts.

The atomic constraint of `f3` is the whole `!sad<typename T::type>`, and substituting `T = int` fails right away. The atomic constraint of `f4` is `!sad_nested_type<T>`; substitution gives `!sad_nested_type<int>`, and that step doesn't fail. Then the concept specialization `sad_nested_type<int>` is evaluated, and the substitution failure inside it just makes its value `false` ([[temp.names]]); negated, that gives `true`.

## Associated constraints of a declaration [temp.constr.decl]

```cpp run title="assoc-order.cpp" ok
template<typename T> concept C = true;
template<typename T> concept C1 = true;
template<typename T> concept C2 = sizeof(T) > 0;

template<C T> void f1(T);                     // associated constraints are all C<T>
template<typename T> requires C<T> void f2(T);
template<typename T> void f3(T) requires C<T>;

template<C1 T> void f4(T) requires C2<T>;     // C1<T> ∧ C2<T>
template<typename T> requires C1<T> && C2<T> void f5(T);   // C1<T> ∧ C2<T>

template<C1 T> requires C2<T> void f6();      // C1<T> ∧ C2<T>
template<C2 T> requires C1<T> void f7();      // C2<T> ∧ C1<T>, different order

void f8(C1 auto x) requires C2<decltype(x)>;  // C1<T′> ∧ C2<decltype(x)>
int main() {}
```

¶1–¶2 Constraints can be written into a declaration in several places: a *requires-clause* after the template parameter list, a trailing *requires-clause* at the end of a function declarator, a *type-constraint* in the template parameter list (`template<C T>`), and a *type-constraint* in a parameter of an abbreviated function template (`C1 auto x`, [[dcl.fct]]).

¶3 The **associated constraints** of a declaration ([[g:associated-constraints]]) are formed as follows:

- ¶3.1 if there are no constraint expressions, there are no associated constraints;
- ¶3.2 if there is exactly one, the associated constraints are its normal form;
- ¶3.3 if there are several, they are joined with `&&` in the following order and then normalized:
    1. the *type-constraint*s in the template parameter list, in order of appearance;
    2. the *requires-clause* after the template parameter list;
    3. the *type-constraint*s in the function parameters;
    4. the trailing *requires-clause*.

This order is the order in which the constraints are instantiated during satisfaction checking, and it determines what short-circuits. The associated constraints of `f6` and `f7` are `C1 ∧ C2` and `C2 ∧ C1`; when comparing strength they subsume each other, but when checking satisfaction a different one is checked first.

`f1`, `f2` and `f3` have the same associated constraints, but they are not three equivalent ways of writing the same function template. When deciding whether two declarations declare the same template, the *type-constraint*s and *requires-clause*s must correspond as written ([[temp.over.link#6]]). If one name is declared in the form of `f2` and defined in the form of `f1`, the two accept the same arguments but don't correspond, and the program is IFNDR ([[temp.over.link#7]]). Use the same form for declaration and definition.

### Corresponding constraints of class template members (¶4)

```cpp run title="member-spec.cpp" ok
template<class T> concept C = true;

template<class T> struct A {
    template<class U> U f(U) requires C<typename T::type>;   // #1
    template<class U> U f(U) requires C<T>;                  // #2
};

template<> template<class U>
U A<int>::f(U u) requires C<int> { return u; }               // OK: specializes #2

int main() {}
```

¶4 When the constraint expression of a member declaration in an instantiated class template is compared for equivalence with the constraint expression of a declaration outside the class, the former is instantiated first; if instantiation yields an invalid expression, the two are not equivalent. Note 1 says this comparison happens when determining which member template an explicit specialization specializes. In the example above, #1 in `A<int>` instantiates to the invalid `C<int::type>` and doesn't match; #2 instantiates to `C<int>` and matches.

!!! lawyer "Comparing the written form and checking satisfaction are different things"
    ¶4 compares the constraint expressions themselves, so `C<int::type>` counts as invalid. But for the call `A<int>{}.f(0)`, satisfaction checking goes through normalization: the normal form of `C` is the atomic constraint `true` with an empty mapping, `int::type` is never substituted, and #1's constraints are in fact satisfied. Both candidates' associated constraints are the same `true` in the definition of `C`, they subsume each other, and the call is ambiguous. Clang 23 reports exactly that.

## Fold expanded constraints [temp.constr.fold] {{c++26}}

```cpp run title="fold-subsume.cpp" ok
#include <concepts>

template<class... T> requires (std::integral<T> && ...)
constexpr int f(T...) { return 1; }

template<class... T> requires (std::signed_integral<T> && ...)
constexpr int f(T...) { return 2; }

static_assert(f(1, 2L) == 2);   // C++26: picks the second; C++23: ambiguous
static_assert(f(1u, 2) == 1);   // only the first is satisfied
static_assert(f() == 2);        // empty pack: both satisfied, the second is more constrained
int main() {}
```

In C++23, `(std::integral<T> && ...)` is just one atomic constraint; the two fold expressions are two different appearances, neither subsumes the other, and the call above is ambiguous. C++26, through [[P2963R3]], normalizes such fold expressions into **fold expanded constraints** ([[g:fold-expanded-constraint]]) so they can be compared.

¶1 A fold expanded constraint consists of a constraint `C` and a fold-operator, `&&` or `||`. It is a pack expansion ([[temp.variadic]]), and `N` is the number of elements in the packs being expanded.

¶2 An `&&` fold expanded constraint is satisfied if the pack expansion is valid and either `N = 0` or, for each `i` in increasing order, `C` is satisfied when each pack is replaced by its `i`th element. ¶3 An `||` fold expanded constraint is satisfied if the pack expansion is valid, `N > 0`, and `C` is satisfied for some `i`. Both short-circuit: once the first `i` that decides the result is reached, later elements are not substituted.

With an empty pack, `&&` is satisfied and `||` is not, consistent with the convention that the fold expressions `(E && ...)` and `(E || ...)` give `true` and `false`. ¶4 Note 1 adds that when packs have different lengths the pack expansion is invalid and the constraint is not satisfied, rather than an error:

```cpp title="fold-satisfaction.cpp" error
#include <concepts>
template<class T> concept HasV = requires { T::v; };
struct A { static constexpr int v = 0; };

template<class... Ts> requires (HasV<Ts> || ...)
constexpr int any() { return 1; }
static_assert(any<int, A>() == 1);     // OK: satisfied at i = 1

template<class... Ts, class... Us>
  requires (std::same_as<Ts, Us> && ...)
void pairs() {}
int main() {
    pairs<int>();   // error: Ts = <int>, Us = <>, lengths differ, constraint not satisfied, no viable function
}
```

¶5 Two fold expanded constraints are **compatible for subsumption** if their constraints contain equivalent unexpanded packs ([[temp.over.link]]). `(C<Ts> && ...)` and `(D<Ts> && ...)` expand the same `Ts` and can be compared; `(C<Ts> && ...)` and `(D<Us> && ...)` can't. The comparison rules are in [[temp.constr.order#1]].

### How fold expressions are normalized ([temp.constr.normal] ¶1.5)

Only fold expressions whose fold-operator is `&&` or `||` become fold expanded constraints; `(sizeof(Ts) + ...) > 10` is still an ordinary atomic constraint. Also, the operand of a fold expression can't be an unparenthesized binary expression; write `((sizeof(Ts) > 0) && ...)`.

- ¶1.5.1 A left fold `( ... Op E )` and a right fold `( E Op ... )` have the same normal form.
- ¶1.5.2 A binary fold with an initial value splits off the end that contains no pack as an operand of an ordinary conjunction or disjunction: `( E1 Op ... Op E2 )` is treated as `( E1 Op ... ) Op E2` if `E1` contains a pack, and as `E1 Op ( E2 Op ... )` otherwise.
- ¶1.5.3.2 In the general case, the normal form of `( E Op ... )` is a fold expanded constraint whose constraint is the normal form of `E` and whose operator is `Op`.

¶1.5.3 also handles a special case: `E` expands a concept template parameter pack (concept template parameters are new in C++26, [[temp.param]]). The elements of a concept pack are already known at normalization time, so ¶1.5.3.1 expands it directly into an ordinary conjunction or disjunction. A single fold expression can't expand both a concept parameter pack and a pack of another kind (Example 5 in the standard). Example 4 from the standard:

```cpp title="concept-pack.cpp" ok
template<typename T> concept A = true;
template<typename T> concept B = A<T> && true;     // B subsumes A
template<typename T> concept C = true;
template<typename T> concept D = C<T> && true;     // D subsumes C

template<typename T, template<typename> concept... CTs>
concept all_of = (CTs<T> && ...);

template<typename T> requires all_of<T, A, C>
constexpr int f(T) { return 1; }                   // #1: A<T> ∧ C<T>
template<typename T> requires all_of<T, B, D>
constexpr int f(T) { return 2; }                   // #2: B<T> ∧ D<T>

static_assert(f(1) == 2);                          // #2 is more constrained
```

!!! impl "Clang 23 reports an ambiguity"
    Clang 23 reports `f(1)` in the example above as ambiguous, meaning it doesn't yet implement the ¶1.5.3.1 rule that expands a concept pack into a conjunction. The standard says #2 is chosen.

## Concept-dependent constraints [temp.constr.concept] {{c++26}}

C++26 allows concepts as template parameters ([[temp.param]]), so a constraint can contain something like `CT<T>`, where `CT` is a concept template parameter. At the template definition it isn't known which concept `CT` is, so it can't be expanded.

[temp.constr.normal] ¶1.4.1 When normalization meets such a dependent concept, it doesn't expand it but produces a **concept-dependent constraint** ([[g:concept-dependent-constraint]]). [temp.constr.concept] ¶1 A concept-dependent constraint is an atomic constraint whose expression is a concept specialization `CI` in which the concept `C` is dependent.

¶2–¶4 Checking whether it is satisfied amounts to deferring the expansion until the arguments are known:

1. First substitute the arguments to determine which concept `C` is. If this yields an invalid concept specialization in the immediate context, the constraint is not satisfied.
2. Take the normal form `CI′` of the substituted concept specialization. Note 1 warns that this step may be IFNDR.
3. In the mappings of the atomic constraints of `CI′`, replace the parameters of `C` with the corresponding arguments, giving `CI″`.
4. If `CI″` is satisfied, the original constraint is satisfied. Note 2 points out that this may recursively produce more concept-dependent constraints.

```cpp run title="concept-dependent.cpp" ok
template<typename>
concept C = true;

template<typename T, template<typename> concept CC>
concept D = CC<T>;

template<typename U,
         template<typename> concept CT,
         template<typename, template<typename> concept> concept CU>
int f() requires CU<U, CT> { return 0; }

int i = f<int, C, D>();
int main() {}
```

The associated constraint of `f` is a concept-dependent constraint whose expression is `CU<U, CT>`. At the call, `D` is substituted for `CU`, giving `D<U, CT>`, whose normal form is `CC<T>` (mapping `T ↦ U, CC ↦ CT`), again a concept-dependent constraint. Then `C` is substituted for `CC`, normalization gives the atomic constraint `true`, and it is satisfied.

[temp.constr.normal] ¶3 Example 3 contrasts two cases: in `requires CT<U*, C>`, `CT` is a concept parameter and the normal form is a concept-dependent constraint; in `requires CC<U*, C>`, `CC` is a concrete concept and only one of its arguments is the concept `C`, so normalization substitutes and expands it directly, ending with the atomic constraint `true`.

Concept-dependent constraints can't take part in strength comparison: associated constraints containing one are not eligible for subsumption ([[temp.constr.order#3]]), because what it will expand to can't be known at the definition.

<details class="fine" markdown="1"><summary>Remaining wording</summary>

[temp.constr.general] ¶1 is a note describing the structure of this subclause: the abstract syntax and satisfaction rules of constraints are in [temp.constr.constr], how constraints are associated with declarations is in [temp.constr.decl], and ordering declarations by constraints is in [[temp.constr.order]]. Constraints are an abstract structure the standard uses to describe semantics; what programmers write is a *constraint-expression*.

The grammar in [temp.constr.decl] ¶1, `constraint-expression: logical-or-expression`, says that a constraint expression is syntactically just an ordinary *logical-or-expression*.

</details>

## Implementation notes

!!! impl "Caching, diagnostics and mangled names"
    - Clang caches satisfaction results of atomic constraints, keyed on the atomic constraint plus the template arguments. ¶3 makes unstable results IFNDR; in practice this shows up as the first result being reused.
    - Comparing constraint strength requires converting constraints to disjunctive or conjunctive normal form, and in the worst case the number of clauses grows exponentially with the size of the constraint ([[temp.constr.order]]). Constraints in real code rarely get that complex.
    - When Clang reports an unsatisfied constraint, it walks down the normalized structure and points out which atomic constraint failed and why.
    - The signature of a function template includes the trailing *requires-clause* ([[defns.signature.templ]]), so constraints become part of the mangled name. The Itanium ABI introduces a constraint expression with `Q`; for example, Clang 23 mangles the specialization `g<int>` of `template<class T> int g(T) requires C<T>` as `_Z1gIiEiT_Q1CIS0_E`.

## History

!!! history
    - C++20 merged the constraint machinery of the Concepts TS into the standard through [[P0734R0]], and at the same time removed the TS's function concepts and variable concepts of the form `concept bool`; concepts are uniformly written `concept C = ...;`.
    - C++26 added concept template parameters and with them concept-dependent constraints ([[P2841]]), as well as fold expanded constraints ([[P2963R3]]). Before that, `(C<Ts> && ...)` was an indivisible atomic constraint.

## Common misconceptions

!!! pitfall "A constraint is just a compile-time `bool` expression"
    Satisfaction is checked atomic constraint by atomic constraint through conjunctions and disjunctions; a substitution failure only makes that one atomic constraint unsatisfied, and with short-circuiting the later operands are never substituted. This differs from how `static_assert(expr)` is evaluated.

!!! pitfall "`!C<T>` is the negation of `C<T>`"
    When comparing strength, `!C<T>` is a new atomic constraint with no logical relationship to `C<T>`. When checking satisfaction, a `!E` whose substitution fails is also unsatisfied.

!!! pitfall "Writing the same expression twice makes them comparable"
    Atomic constraints must come from the same appearance, that is, be brought in through the same concept.

!!! pitfall "`requires (T::value)` checks whether `value` exists"
    It checks the value of `T::value`, and requires its type to be exactly `bool`. To check existence, write `requires { T::value; }`.

## Questions

!!! question "Question 1"
    Given `template<class T> concept HasX = requires { T::x; };`, are the following two constraints satisfied for `T = int`?

    ```cpp
    template<class T> requires (!HasX<T>) void f(T);              // (a)
    template<class T> requires (!requires { T::x; }) void g(T);   // (b)
    ```

<details markdown="1">
<summary>Answer</summary>

Both are satisfied. The atomic constraint of (a) is `!HasX<T>`; substituting `T = int` gives `!HasX<int>`, and the substitution itself doesn't fail; `HasX<int>` is `false`, and its negation is `true`. The atomic constraint of (b) is `!requires { T::x; }`; an invalid expression inside a requires-expression is not a substitution failure, it only makes the requires-expression `false` ([[expr.prim.req]]), and the negation is `true`.

Compare `requires (!sad<typename T::type>)`: there `typename T::type` fails to substitute in the immediate context of the atomic constraint, and the atomic constraint is simply not satisfied.
</details>

!!! question "Question 2"
    Why does normalization expand concepts, instead of treating `C<T>` as a single atomic constraint?

<details markdown="1">
<summary>Answer</summary>

If `C<T>` were an indivisible atom, that would already be enough for `D = C<T> && E<T>` to be stronger than `C`. But expanding brings two further abilities. One is identity across concepts: `Add1` and `AddOne` are two different concepts both based on `C`, and their expanded atomic constraints can be identical (Example 1 in [temp.constr.atomic]). The other is that the internal structure of a concept can take part in the comparison: `std::signed_integral<T>` expands to something containing the atomic constraint of `std::integral<T>`, so it is stronger than any constraint that directly requires `std::integral<T>`. The cost is that normal forms can get large, and composed mappings can form invalid types (the IFNDR in ¶1.4.2).
</details>

!!! question "Question 3"
    What are the associated constraints of `template<class... Ts> requires (std::integral<Ts> && ...) void f(Ts...);` in C++23 and in C++26?

<details markdown="1">
<summary>Answer</summary>

In C++23 it is one atomic constraint whose expression is the whole fold expression. In C++26 it is an `&&` fold expanded constraint whose constraint is the normal form of `std::integral<Ts>`, namely the atomic constraint `is_integral_v<T>` from the definition of `std::integral`, with mapping `T ↦ Ts`. Only in C++26 can it be compared for strength with `(std::signed_integral<Ts> && ...)`.
</details>
