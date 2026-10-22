---
title: Best viable function
summary: "The last step of overload resolution: compare implicit conversion sequences argument by argument; the function that is no worse anywhere and better somewhere wins; when everything ties, a dozen or so tie-breakers apply in a fixed order; the call is valid only if one function beats all others."
updated: 2026-10-19
---

!!! tldr
    - Viable function `F1` is better than `F2` when two conditions hold: on every argument, `F1`'s conversion is no worse than `F2`'s; and it is better on at least one argument, or, when everything ties, some tie-breaker favors `F1`.
    - Tie-breakers apply only when all arguments tie. If `F1` is worse on even one argument, being a non-template or more constrained doesn't help it.
    - The tie-breakers are, in order: conversion function result, kind of function reference, non-template, more specialized template, more constrained non-template, the derived class's own constructor, non-rewritten candidate, non-reversed candidate; the last four are only for class template argument deduction.
    - The call is valid only if one viable function is better than all other viable functions. If two candidates each win one argument, that's ambiguity; the compiler doesn't add up scores.

## Each wins one argument: ambiguity

```cpp error
void Fcn(const int*, short);
void Fcn(int*, int);

int i;
short s = 0;

void f() {
  Fcn(&i, s);     // error: ambiguous
  Fcn(&i, 1L);    // OK: Fcn(int*, int)
  Fcn(&i, 'c');   // OK: Fcn(int*, int)
}
```

This is Example 8 in the standard. Overload resolution first finds all the [[g:viable-function|viable functions]], that is, the functions whose number of parameters fits and to whose parameter types every argument can be implicitly converted ([[over.match.viable]]). Both `Fcn` are viable for all three calls; next they have to be ranked against each other.

What gets compared is each argument's [[g:implicit-conversion-sequence|implicit conversion sequence]] (ICS), the chain of conversions used to convert that argument to the parameter type ([[over.best.ics]]). Which of two ICSs is better is specified by [[over.ics.rank]]. The ICSs of the three calls:

| Call | Argument | `Fcn(const int*, short)` | `Fcn(int*, int)` | Better on this argument |
|---|---|---|---|---|
| `Fcn(&i, s)` | `&i` | qualification conversion | identity | the latter |
| | `s` | identity | integral promotion | the former |
| `Fcn(&i, 1L)` | `&i` | qualification conversion | identity | the latter |
| | `1L` | integral conversion | integral conversion | tie |
| `Fcn(&i, 'c')` | `&i` | qualification conversion | identity | the latter |
| | `'c'` | integral conversion | integral promotion | the latter |

In the first call each function wins one argument and neither is no-worse everywhere, so the call is ambiguous. In the other two calls `Fcn(int*, int)` is no worse everywhere and better on `&i`, so it wins.

`&i → int*` beats `&i → const int*` because no conversion is always better than one qualification conversion ([[over.ics.rank#3.2.1]]). `char → short` is not a promotion; promotions target only a few types such as `int` and `unsigned int` ([[conv.prom]]), so it is worse than `char → int`.

## What a better function is (¶1–¶2)

¶1 The standard writes **ICSi(F)** for the implicit conversion sequence that converts the `i`th argument to the type of the `i`th parameter of viable function `F`.

The `i`th argument is counted from the candidate function's point of view. A member function has an extra implied object argument, corresponding to its object parameter ([[over.match.funcs#2]]). For a static member function this position takes no part in the comparison; its ICS is neither better nor worse than any standard conversion sequence ([[over.best.ics#8]]). For a reversed rewritten candidate, the order of the two arguments is swapped ([[over.match.oper]]).

¶2 Viable function `F1` is **better** than `F2` if, for all arguments `i`, ICSi(F1) is no worse than ICSi(F2), and one of the following holds. They are checked in order; the next is considered only if the previous doesn't hold.

!!! std
    "a viable function F1 is defined to be a *better* function than another viable function F2 if for all arguments i, ICSi(F1) is not a worse conversion sequence than ICSi(F2), and then …"

¶2.1 The first is the main rule: for some argument `j`, ICSj(F1) is better than ICSj(F2). The vast majority of calls are decided here.

The rest, ¶2.2–¶2.13, are **tie-breakers**: when all arguments tie, they look at properties unrelated to ICSs. Since "no worse on all arguments" is a precondition, if `F1` is worse on even one argument, none of them can rescue it.

## Tie-breakers (¶2.2–¶2.13)

The standard checks these rules in order from ¶2.2 to ¶2.13; the table at the end of this section lists them in that order. Below we first cover the ones most often met in everyday code, then the ones that only show up with conversion functions and class template argument deduction.

### Non-template preferred, but conversions come first (¶2.4)

```cpp run ok
#include <cstdio>
void f(int)                 { std::puts("f(int)"); }
template<class T> void f(T) { std::puts("f<T>(T)"); }
int main() {
  f(1);      // f(int)
  f('a');    // f<char>
  f<>(1);    // f<int>
}
```

¶2.4 If `F1` is not a function template specialization and `F2` is, `F1` is better.

In `f(1)` the template deduces `f<int>(int)`; both functions' ICSs are identity and tie, so the non-template wins. In `f('a')` the template deduces `f<char>(char)` with an identity ICS, while `f(int)` needs the integral promotion `char → int`. The main rule ¶2.1 already decides it, and ¶2.4 never gets a chance. `f<>(1)` has an explicit template argument list, so only the template is a candidate.

The signature a template deduces usually matches the arguments exactly, so templates often beat non-templates through a better conversion.

### More specialized template (¶2.5)

```cpp run ok
#include <concepts>
#include <cstdio>
template<class T> void g(T)  { std::puts("g(T)"); }
template<class T> void g(T*) { std::puts("g(T*)"); }
template<class T>         void h(T) { std::puts("h(T)"); }
template<std::integral T> void h(T) { std::puts("h(integral T)"); }
int main() {
  int i = 0;
  g(&i);     // g(T*)
  h(1);      // h(integral T)
  h(1.0);    // h(T)
}
```

¶2.5 If `F1` and `F2` are both function template specializations and, according to the partial ordering rules of [[temp.func.order]], `F1`'s template is [[g:more-specialized|more specialized]] than `F2`'s, `F1` is better.

In `g(&i)` both templates deduce `g(int*)` with identical ICSs; any argument `T*` accepts can be given to `T`, but not the other way round, so `g(T*)` is more specialized. Partial ordering also considers constraints: when two templates are equivalent except for constraints, the [[g:more-constrained|more constrained]] one is more specialized ([[temp.constr.order]]), so `h(1)` picks the constrained version. In `h(1.0)` the constrained version doesn't satisfy its constraint and isn't a viable function at all.

### More constrained non-template function (¶2.6)

```cpp run ok
template <typename T = int>
struct S {
  constexpr int f() { return 1; }                        // #1
  constexpr int f(this S&) requires true { return 2; }   // #2
};
int main() {
  S<> s;
  return s.f() == 2 ? 0 : 1;   // calls #2
}
```

¶2.6 If `F1` and `F2` are both non-template functions and `F1` is more partial-ordering-constrained than `F2` ([[temp.constr.order]]), `F1` is better. The comparison has preconditions: the two functions have the same non-object-parameter-type-lists; if they are member functions, they are direct members of the same class and have the same object parameter type.

In the example #1 is an ordinary member function and #2 has an explicit object parameter, but both object parameter types are `S&`, so they can be compared by constraints, and #2 wins.

A non-template function can only have a `requires` clause inside a template, for example as a member function of a class template. So this rule is mainly for member functions provided conditionally in class templates.

### The derived class's own constructor preferred (¶2.7)

```cpp run ok
struct A {
  A(int = 0) {}
};
struct B : A {
  using A::A;
  B() {}
};
int main() {
  B b;      // B::B()
}
```

¶2.7 If `F1` is a constructor of class `D`, `F2` is a constructor of a base class `B` of `D` (inherited via `using`), and for all arguments the corresponding parameters have the same types, `F1` is better.

Once inherited, `A(int = 0)` can also be called without arguments and ties with `B()`. The derived class wrote another constructor that can be called the same way, and using that one is what makes sense. Without this rule, `B b;` would be ambiguous.

### Hand-written comparison operators preferred (¶2.8–¶2.9)

Since C++20, the candidates for `a < b` include not only every `operator<` but also `(a <=> b) < 0` rewritten from `operator<=>`, and `0 < (b <=> a)` with the operands swapped. The former is a [[g:rewritten-candidate|rewritten candidate]]; the latter is a synthesized candidate with reversed parameters ([[over.match.oper]]).

```cpp run ok
#include <compare>
#include <cstdio>
struct S {
  friend auto operator<=>(const S&, const S&) = default;   // #1
  friend bool operator<(const S&, const S&) {               // #2
    std::puts("#2"); return false;
  }
};
int main() { (void)(S() < S()); }   // calls #2
```

¶2.8 If `F2` is a rewritten candidate and `F1` is not, `F1` is better. The candidate rewritten from #1 has exactly the same ICSs as #2, and the hand-written #2 wins.

```cpp run ok
#include <compare>
#include <cstdio>
using std::weak_ordering;
struct S {
  friend weak_ordering operator<=>(const S&, int) {   // #1
    std::puts("#1"); return weak_ordering::equivalent;
  }
  friend weak_ordering operator<=>(int, const S&) {   // #2
    std::puts("#2"); return weak_ordering::equivalent;
  }
};
int main() { (void)(1 < S()); }   // calls #2
```

¶2.9 If `F1` and `F2` are both rewritten candidates, and `F2` is a synthesized candidate with reversed parameters and `F1` is not, `F1` is better. `1 < S()` can be rewritten as `(1 <=> S()) < 0`, using #2; or reversed as `0 < (S() <=> 1)`, using #1. The ICSs are the same, and the non-reversed one wins.

These two also apply only on a tie. If an ordinary candidate and a reversed candidate differ on some argument, for example because one is a non-const member function, the comparison never gets here. Many of C++20's `operator==` ambiguities arise this way; see [[over.match.oper]].

### User-defined conversions: compare the step after the conversion (¶2.2)

```cpp error
struct A {
  A();
  operator int();
  operator double();
} a;
int   i = a;   // OK: operator int()
float x = a;   // error: ambiguous
```

¶2.2 If the context is an initialization by user-defined conversion ([[dcl.init]], [[over.match.conv]], [[over.match.ref]]) and the standard conversion sequence from the result of `F1` to the destination type is better than the one from the result of `F2`, `F1` is better.

When `a` initializes an `int`, the candidates are the two conversion functions, the only argument is the object `a`, the two ICSs are identical, and the main rule can't tell them apart. The real difference comes after the conversion function returns: the result of `operator int()` needs no further conversion, while the result of `operator double()` still needs `double → int`. That step belongs to no argument's ICS, hence a separate rule. When initializing a `float`, `int → float` and `double → float` both have Conversion rank and tie, so the result is ambiguous.

Ordinary function calls don't compare return values this way, because the result of a call expression has no definite destination type; it may be discarded or passed to another function.

### Kind of function reference (¶2.3)

```cpp
template <class T> struct A {
  operator T&();    // #1
  operator T&&();   // #2
};
typedef int Fn();
A<Fn> a;
Fn&  lf = a;        // calls #1
Fn&& rf = a;        // calls #2
```

¶2.3 If the context is an initialization by conversion function for direct reference binding of a reference to function type, the return type of `F1` is the same kind of reference (lvalue or rvalue) as the reference being initialized, and the return type of `F2` is not, `F1` is better.

Functions are only lvalues, and an rvalue reference can also bind to a function lvalue, so #1 and #2 both work for both references. This rule makes the matching kind win, complementing [[over.ics.rank#3.2.4]].

!!! impl "Clang deviates"
    In our tests Clang 23 picks #1 for `Fn& lf = a;` but reports "reference initialization … is ambiguous" for `Fn&& rf = a;`; it doesn't implement the second half of this rule. Per the standard, the initialization of `rf` is well-formed and calls #2.

### Only for class template argument deduction (¶2.10–¶2.13)

When you write `std::vector v{1, 2};`, the compiler generates a set of notional function templates from the class template's constructors and deduction guides and performs overload resolution on them to deduce `T`. This is class template argument deduction (CTAD, [[over.match.class.deduct]]). The following four rules are used only in that notional overload resolution:

| Rule | `F1` is better than `F2` if |
|---|---|
| ¶2.10 | both are generated for class `D`, `F2` comes from a constructor inherited from a base class and `F1` doesn't, and for each explicit argument the corresponding parameters are either both ellipses or have the same type |
| ¶2.11 | `F1` is generated from a user-written [[g:deduction-guide\|deduction guide]] and `F2` is not |
| ¶2.12 | `F1` is the [[g:copy-deduction-candidate\|copy deduction candidate]] (the candidate `A(A)` that deduces `A` itself) and `F2` is not |
| ¶2.13 | `F1` is generated from a non-template constructor and `F2` from a constructor template |

```cpp
template <class T> struct A {
  using value_type = T;
  A(value_type);    // #1
  A(const A&);      // #2
  A(T, T, int);     // #3
  template<class U>
    A(int, T, U);   // #4
  // #5 is the copy deduction candidate A(A)
};

A x(1, 2, 3);       // uses #3 for deduction (¶2.13)

template <class T>
A(T) -> A<T>;       // #6, less specialized than #5

A a(42);            // #6 deduces A<int>, then #1 initializes
A b = a;            // #5 deduces A<int> (¶2.5), then #2 initializes

template <class T>
A(A<T>) -> A<A<T>>; // #7, as specialized as #5

A b2 = a;           // #7 deduces A<A<int>> (¶2.11), then #1 initializes
```

The generated candidates are all function templates, so ¶2.4 hardly ever applies, and the partial ordering of ¶2.5 often decides before ¶2.11–¶2.13. That is the difference between `b` and `b2`: #6's parameter `T` is less specialized than #5's `A<T>`, so partial ordering already picks #5; #7 is as specialized as #5, partial ordering ties, and only then does ¶2.11 let the deduction guide win.

### Summary

| Order | Rule | Typical situation |
|---|---|---|
| ¶2.1 | Better ICS on some argument | the vast majority of calls |
| ¶2.2 | Better conversion from the conversion function's result to the destination | `int i = obj;` choosing among several conversion functions |
| ¶2.3 | Matching kind of function reference | `Fn& r = obj;` |
| ¶2.4 | Non-template beats template specialization | `f(int)` vs `template f(T)` |
| ¶2.5 | More specialized template (including constraints) | `g(T*)` vs `g(T)` |
| ¶2.6 | More constrained non-template function | member functions provided conditionally in class templates |
| ¶2.7 | Derived-class constructor beats inherited constructor | `using Base::Base;` |
| ¶2.8 | Non-rewritten beats rewritten | hand-written `<` vs `<` rewritten from `<=>` |
| ¶2.9 | Non-reversed beats reversed | `x <=> y` vs reversed `y <=> x` |
| ¶2.10–¶2.13 | CTAD only | deduction guides, the copy deduction candidate, etc. |

## The unique best (¶3–¶4)

¶3 If exactly one viable function is better than all other viable functions, it is the result of overload resolution; otherwise the call is ill-formed.

Comparing n functions pairwise takes O(n²) comparisons. Footnote 98 gives a linear method:

1. In a first pass, like a knockout tournament, keep a current winner `W` and compare it with each function in turn, replacing `W` whenever the challenger is better.
2. In a second pass, check that `W` is better than every other function.

Every function `F` that didn't end up as the final `W` met, in some round, a `G` it failed to beat, so `F` can't be better than all functions. If a best function exists, it can only be `W`, and the second pass confirms it. The argument doesn't need the "better" relation to be transitive.

¶4 Note 1 points out that if the best viable function is viable only because of default arguments, there's an extra requirement: those default arguments can't come from declarations in several different scopes ([[over.match.viable#2]]).

## Implementation view

!!! impl
    - Clang's `isBetterOverloadCandidate` follows the order of ¶2 closely: first it compares ICSs argument by argument and returns immediately if one is worse; then it checks the conversion function result, non-template, partial ordering, constraints, inherited constructors, rewritten and reversed candidates, and the CTAD-only rules in turn. GCC's counterpart is `joust`.
    - An ambiguity diagnostic lists all the candidates competing for best. When reading it, first find which argument each of them wins on; that usually locates the problem.
    - For some of the ambiguities caused by C++20's reversed `operator==`, Clang and GCC pick one function as an extension and issue a warning; see [[over.match.oper]].

## History

!!! history
    - C++98 already had the main rule, the conversion function result rule, non-template preference and template partial ordering.
    - C++11 added the rule about the kind of function reference (¶2.3).
    - C++17 added three rules for CTAD (¶2.11–¶2.13) and rewrote ¶2.7 for the new model of inheriting constructors.
    - C++20 made partial ordering consider constraints and added the rule comparing non-template functions by constraints, plus the two rules for rewritten and reversed candidates (¶2.8, ¶2.9).
    - C++23 added the CTAD rule for inherited constructors (¶2.10).
    - Wording after C++23 changed ¶2.6 to use the term more partial-ordering-constrained and made explicit the preconditions under which two non-template functions can be compared by constraints.

## Common misconceptions

!!! pitfall "Non-template preference can override a better conversion"
    Tie-breakers apply only on a tie. With `f(int)` and `template<class T> void f(T)` both present, `f('a')`, `f(1L)` and `f(1.0f)` all pick the template.

!!! pitfall "Being more constrained can override a better conversion"
    Likewise. Constraints matter in only two places: a function whose constraints aren't satisfied isn't viable; when ICSs tie, the more constrained one wins.

!!! pitfall "The compiler adds up a score"
    Overload resolution doesn't weight or count. If two candidates each win one argument, that's ambiguity, even if one of them is an exact match on the remaining ten arguments.

## Questions

!!! question "Question 1"
    Which function does each of the two calls below pick?
    ```cpp
    void f(int, double);             // #1
    void f(long, int);               // #2
    template<class T> void f(T, T);  // #3
    // f(1, 2);    f(1, 2.0);
    ```

<details markdown="1">
<summary>Answer</summary>

`f(1, 2)`: #3 deduces `f<int>(int, int)`, identity on both arguments. #1 is identity plus a floating-integral conversion; #2 is an integral conversion plus identity. #3 is no worse than #1 and #2 on both arguments and better on at least one, so it wins by ¶2.1; non-template preference never comes into play.

`f(1, 2.0)`: #3 deduces `int` and `double` from the two arguments, deduction fails, and it isn't a candidate. #1 is two identities, #2 an integral conversion plus a floating-integral conversion, so #1 is picked. (Running it with Clang 23 agrees.)
</details>

!!! question "Question 2"
    Why does ¶2.2 compare the conversion from result to destination only in initialization by user-defined conversion, while ordinary calls don't compare return types?

<details markdown="1">
<summary>Answer</summary>

The result of an ordinary call has no definite destination type: it may be discarded, passed to another overloaded function, or received by `auto`. Overload resolution doesn't depend on the context after the call, which is also why you can't overload on return type alone. In contexts such as [[over.match.conv]] and [[over.match.ref]], the only purpose of calling a conversion function is to get a value of some destination type, so the destination type is known; and all candidates have the same object as their argument, with identical ICSs, so the conversion from result to destination is the only way to distinguish them.
</details>
