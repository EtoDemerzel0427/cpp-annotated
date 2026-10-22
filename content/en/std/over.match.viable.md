---
title: Viable functions
summary: "The second step of overload resolution: drop the candidate functions that can't be called with these arguments at all. The filter looks at only three things: the number of arguments, constraints, and implicit conversion sequences."
updated: 2026-10-19
---

!!! tldr
    - To be a viable function, a candidate must meet three requirements in order: the number of parameters fits, its associated constraints are satisfied, and every argument can be implicitly converted to its corresponding parameter.
    - Viability only answers whether the function can be called; it doesn't compare candidates. Comparing is the next step, [[over.match.best]].
    - Access, `= delete`, narrowing, bit-fields and explicit don't affect viability. Functions with these problems still take part in the comparison; the error comes only after one is selected.
    - Having an ellipsis in the declaration is no disadvantage. `f(int)` and `f(int, ...)` are ambiguous for `f(1)`.
    - C++26 specifies precisely which declaration the default arguments come from: the default arguments used by the selected function must come from exactly one scope.

Overload resolution has three steps: first collect the **candidate functions** for the context of the call ([[over.match.funcs]]), then filter out the **viable functions** among them, and finally pick the best one among the viable functions ([[over.match.best]]).

```cpp run ok
#include <cstdio>
void f(int&)       { std::puts("f(int&)"); }
void f(const int&) { std::puts("f(const int&)"); }
int main() {
  int i = 0;
  f(i);   // both viable; f(int&) is better
  f(1);   // f(int&) not viable: a non-const lvalue reference can't bind to an rvalue
}
```

In the first call both candidates are viable and the next step decides between them. In the second call `f(int&)` is eliminated while viable functions are filtered, and never takes part in the comparison. When you ask why some function wasn't chosen, the answer is often that it wasn't viable.

¶1 Filtering viable functions looks only at the associated constraints and the relationship between arguments and parameters, not at which conversion sequence is better. The next three sections cover the three requirements in turn.

## Requirement one: the number of parameters (¶2)

¶2 Say the call has `m` arguments. A candidate function must fit in number, in one of three cases:

- ¶2.1 It has exactly `m` parameters: viable.
- ¶2.2 It has fewer than `m` parameters: viable only if the parameter list has an ellipsis `...`. All the extra arguments are considered to match the ellipsis ([[over.ics.ellipsis]]).
- ¶2.3 It has more than `m` parameters: every extra parameter must have a default argument. C++26 is more precise about which declaration the default arguments come from; see below.

```cpp run ok
#include <cstdio>
void f(int)      { std::puts("f(int)"); }
void f(int, ...) { std::puts("f(int, ...)"); }
void g(...)      { std::puts("g(...)"); }
int main() {
  f(1, 2);     // only f(int, ...) viable: argument 2 matches the ellipsis
  g();         // a lone ellipsis also accepts 0 arguments
  g(1, "a");
}
```

What about `f(1)`? Both candidates are viable, and for the argument `1` both are the identity conversion from `int` to `int`. No tie-breaker says "the one without an ellipsis wins", so the call is ambiguous:

```cpp error
void f(int);
void f(int, ...);
void use() {
  f(1);      // error: ambiguous
}
```

An ellipsis is a disadvantage only when some argument actually matches it, because the ellipsis conversion sequence ranks below every other conversion sequence ([[over.ics.rank#2]]). An ellipsis in the declaration is no disadvantage in itself.

## Requirement two: constraints (¶3)

¶3 If the candidate function has associated constraints ([[temp.constr.decl]]), that is, conditions introduced by a `requires` clause or by constrained template parameters, those constraints must be satisfied ([[temp.constr.constr]]).

The constraints of a function template are already checked during template argument deduction, and a specialization that doesn't satisfy them never becomes a candidate ([[temp.deduct]]). So this requirement mainly applies to constraints on non-template functions, typically the trailing `requires` clause of an ordinary member function of a class template:

```cpp error
#include <concepts>
template<class T>
struct Wrapper {
  void reset() requires std::default_initializable<T>;
  void set(int) requires std::integral<T>;
  void set(double);
};
struct NoDefault { NoDefault(int); };
void use(Wrapper<int>& wi, Wrapper<NoDefault>& wn, Wrapper<double>& wd) {
  wi.set(1);    // OK: both set are viable; set(int) is an exact match
  wd.set(1);    // OK: set(int)'s constraint isn't satisfied, so it isn't viable; set(double) is chosen
  wi.reset();   // OK
  wn.reset();   // error: the only candidate isn't viable
}
```

`wi.set(1)` and `wd.set(1)` have the same candidate set but different viable sets. A constraint says whether something can be used, so it belongs to viability. "More constrained wins" is a different rule ([[over.match.best#2.6]]) and only applies when both candidates are viable.

## Requirement three: every argument converts (¶4)

¶4 For each argument there must be an **implicit conversion sequence** (ICS, [[over.best.ics]]) that converts it to the type of the corresponding parameter, that is, the chain of conversions the compiler inserts automatically to pass the argument.

When the parameter is a reference, the conversion sequence includes binding the reference. A non-const lvalue reference can't bind to an rvalue, and an rvalue reference can't bind to an lvalue; these two restrictions make a candidate non-viable ([[over.ics.ref#3]]):

```cpp error
void f(int&);
void g(int&&);
void h(const int&);
void use(int i) {
  f(i);   // OK
  f(1);   // error: the only candidate isn't viable: an rvalue can't bind to int&
  g(i);   // error: the only candidate isn't viable: an lvalue can't bind to int&&
  g(1);   // OK
  h(i);   // OK
  h(1);   // OK: a const lvalue reference can bind to a temporary
}
```

Each function here has a single candidate, so non-viable means an immediate error. With other overloads, a non-viable candidate is silently eliminated and the call picks a different function. This is what lets `T&`, `const T&` and `T&&` overloads dispatch on value category.

## What viability ignores

As long as the types can be converted, the candidate is viable. The following properties, which have nothing to do with types, take no part in viability; they are checked only after the candidate is selected, and if there's a problem the program is ill-formed ([[over.best.ics#2]], [[over.ics.ref#4]]):

| Property | Example | Where the error happens |
|---|---|---|
| Access | a `private` member function is selected | after selection ([[over.match#3]]) |
| Deleted | a `= delete` function is selected | after selection ([[dcl.fct.def.delete]]) |
| Bit-field | an `int&` parameter with an `int` bit-field argument | after selection, when binding the reference ([[dcl.init.ref]]) |
| Narrowing | `f({1.5})` with an `int` parameter | after selection ([[dcl.init.list]]) |
| Ambiguous conversion sequence | two user-defined conversion paths from one argument to its parameter | after selection ([[over.best.ics#12]]) |

```cpp error
struct S { int bf : 4; };
void f(int&);
void f(long);
void use(S s) {
  f(s.bf);   // error: f(int&) is selected, then int& turns out unable to bind to a bit-field
}
```

When the conversion sequences are computed, `s.bf` is treated as an ordinary `int` lvalue, so `f(int&)` is an exact match and beats `f(long)`, which needs an integral conversion. Only after it is selected does it turn out that a non-const reference can't bind to a bit-field. This design keeps properties unrelated to types from silently changing the outcome of overloading.

The same goes for explicit constructors in copy-list-initialization: they still take part in forming the ICS, and the error comes only if one is actually used to perform the initialization ([[over.match.list]] note 1).

```cpp
struct X { explicit X(int); };
struct Y { Y(int); };
void f(X);
void f(Y);
void use() {
  f({1});   // per the standard: f(X) and f(Y) are both viable; ambiguous
}
```

Per the standard, `{1}` has a user-defined conversion sequence both to `X` and to `Y`, and the two candidates can't be distinguished. In our tests Clang 23 doesn't count the explicit constructor; it accepts this call and selects `f(Y)`.

## Where default arguments come from (¶2.3) {{c++26}}

A function can have several declarations, and each declaration can add default arguments. Those declarations may be spread over different scopes: one in a namespace and another redeclaration inside some function body; or one `extern "C"` declaration in each of two namespaces, which are the same function, both brought in by *using-declaration*s. Which set of default arguments does a call use then?

A redeclaration at block scope is the most common case; it hides the outer declaration:

```cpp run ok
#include <cstdio>
void h(int x = 7) { std::printf("%d\n", x); }
void local() {
  void h(int = 8);   // redeclared at block scope with a different default argument
  h();               // prints 8: only the block-scope declaration is visible
}
int main() { h(); local(); }
```

¶2.3 describes this situation in terms of the **host scope** ([[basic.scope.scope#2]]), roughly the scope the declaration is in. Let candidate function `C` have more than `m` parameters, and define the set of scopes `G`, where each scope `X` satisfies:

- ¶2.3.1 one of the declarations of `C` considered by overload resolution has `X` as its host scope;
- ¶2.3.2 for each parameter after the `m`th, some reachable declaration whose host scope is `X` provides a default argument for it.

If `G` is non-empty, `C` is viable as far as the number of arguments goes. If `C` is eventually selected, it must also satisfy:

- ¶2.3.3 `G` contains exactly one scope, call it `S`;
- ¶2.3.4 if the candidate was obtained through a *splice-expression* (`[: r :]` from reflection), `S` must not be a block scope;
- ¶2.3.5 the default arguments used by the call are those provided by the reachable declarations whose host scope is `S`.

For the purposes of overload resolution, the parameter list is truncated on the right to exactly `m` parameters.

In other words, viability only asks whether some scope can supply all the needed default arguments; at actual selection, that scope must be unique, otherwise there's no way to decide which set to use.

```cpp
namespace A {
  extern "C" void f(int, int = 5);
  extern "C" void f(int = 6, int);   // default arguments added step by step in the same scope
}
namespace B {
  extern "C" void f(int, int = 7);   // the same function as A::f
}
void use() {
  using A::f;
  using B::f;
  f(3, 4);   // OK: no default arguments used
  f(3);      // error: both A and B can supply the second default argument; G has two scopes
  f();       // OK: only A can supply both default arguments
}
```

Parameters produced by expanding a parameter pack have no default arguments:

```cpp error
template<typename... Ts>
int k(int = 3, Ts...);
int i = k<int>();   // error: the second parameter (from the pack expansion) has no default argument
int j = k<>();      // OK: only one parameter, and it has a default argument
```

!!! impl "Clang deviates"
    In our tests Clang 23 does the opposite of the standard on the *using-declaration* example: it accepts `f(3)` but rejects `f()`, reporting that at least 1 argument is required; it doesn't combine the default arguments of the two declarations in `A`. The block-scope and parameter-pack examples agree with the standard. The part of the standard's example that uses a *splice-expression* needs static reflection, which Clang 23 can't compile.

In C++23 and earlier, ¶2.3 only said that every extra parameter must have a default argument, without saying which declaration's default arguments are used; the multiple-scope case was handled by [[dcl.fct.default]], and the wording was incomplete. Once C++26 introduced reflection, a call like `[:^^f:]()` doesn't go through name lookup, so there's no notion of the declarations visible at the point of call, and it became necessary to say exactly which set of default arguments is used.

## Common misconceptions

!!! pitfall "Deleted, private or narrowing functions aren't viable"
    They are all viable, can be selected, and only then cause an error. To exclude an overload at the viability stage, use constraints (`requires`) or SFINAE.

!!! pitfall "Giving the same function different default arguments in different scopes"
    This is allowed, but which set of default arguments applies depends on which declarations the call site can see. Under the C++26 rules, if the default arguments of two scopes are both usable, the call is ill-formed.

## Questions

!!! question "Question 1"
    Which function does the call `f(x)` below call? What if #2 is replaced by `void f(Base) = delete;`?
    ```cpp
    struct Base {};
    struct Derived : Base {};
    void f(Base&);       // #1
    void f(Derived&&);   // #2
    Derived x;
    // f(x);
    ```

<details markdown="1">
<summary>Answer</summary>

`x` is an lvalue, and #2's rvalue reference can't bind to an lvalue, so #2 isn't viable. #1 is viable (a derived-class lvalue binds to a base-class reference), so #1 is selected.

After replacing it with `void f(Base) = delete;`, both candidates are viable. #1 binds a reference to base to a derived object; the by-value one copy-initializes a `Base` from `x`. Both conversion sequences are derived-to-base Conversions of the same rank ([[over.best.ics#6]], [[over.ics.ref#1]]). Nothing in [[over.ics.rank]] distinguishes the two, so the call is ambiguous. `= delete` never gets a chance to matter here. In our tests Clang 23 reports the ambiguity.
</details>

!!! question "Question 2"
    What's the practical significance of the order of the three requirements (number, constraints, conversion sequences)?

<details markdown="1">
<summary>Answer</summary>

For the outcome, all three must hold, so the order doesn't matter. But the order decides what work the compiler has to do. Computing conversion sequences may require instantiating class templates (for example to look up converting constructors or to determine derivation), and instantiation can produce hard errors or cause circular dependencies during concept checking. Checking constraints first eliminates candidates that don't satisfy them before those instantiations are triggered. For the same reason, constraint checking for function templates happens before the deduced arguments are substituted into the function parameter types ([[temp.deduct]]).
</details>
