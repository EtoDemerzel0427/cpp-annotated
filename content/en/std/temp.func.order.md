---
title: Partial ordering of function templates
summary: "When several function templates can generate viable specializations for a call and the conversion sequences don't decide, how the compiler determines which template is more specialized, and under what conditions constraints take part in the comparison."
updated: 2026-10-19
---

!!! tldr
    - Partial ordering decides which of two function templates is more specialized: replace one template's parameters with synthesized unique types and see whether the other can deduce from them; if only one direction succeeds, the template that was transformed is the more specialized one.
    - Partial ordering compares the templates themselves, not the arguments. In a call, only parameters that have corresponding arguments are compared; parameters with default arguments, function parameter packs and ellipses don't take part.
    - `f(T)` vs `f(T&)` is always ambiguous; for lvalues, `f(T&)` is more specialized than `f(T&&)`; `f(const T&)` is more specialized than `f(T&)`.
    - Constraints take part only when deduction succeeds in both directions and the two templates correspond exactly apart from their constraints; the more constrained one is more specialized.
    - In overload resolution, partial ordering comes after comparing conversion sequences and after the non-template preference; it is a late tie-breaker.

## The problem

```cpp run ok
template<class T> int f(T)  { return 1; }   // #1
template<class T> int f(T*) { return 2; }   // #2
int main() {
  int* p = nullptr;
  return f(p) - 2;   // calls #2
}
```

`#1` deduces `f<int*>(int*)`, and `#2` deduces `f<int>(int*)`. Both specializations have parameter type `int*`, both are exact matches, and comparing conversion sequences can't separate them. Intuitively, `#2` accepts only pointers while `#1` accepts anything, so `#2` is more specific and should be chosen. [[g:partial-ordering|**Partial ordering**]] turns this intuition into an algorithm.

It's called partial ordering because it isn't a total order: two templates may each fail to be more specialized than the other, such as `f(T, int)` and `f(int, T)`, and then the call is ambiguous.

## When partial ordering is used (¶1)

¶1 When one name refers to several function templates, template argument deduction ([[temp.deduct]]) may find a specialization in more than one of them. Partial ordering decides which template is meant in these four situations:

- ¶1.1 overload resolution for a call to a function template specialization ([[over.match.best]]);
- ¶1.2 taking the address of a function template specialization ([[over.over]]);
- ¶1.3 selecting the placement deallocation function that matches a placement new, when it is a function template specialization ([[basic.stc.dynamic.deallocation]], [[expr.new]]);
- ¶1.4 when a friend declaration, an explicit instantiation or an explicit specialization refers to a function template specialization.

In overload resolution, partial ordering comes late: implicit conversion sequences are compared first, then whether a non-template beats a template, and only then partial ordering ([[over.match.best]]).

¶1.4 is easy to overlook. For an explicit specialization written without template arguments, deduction plus partial ordering decides which template it specializes:

```cpp run ok
template<class T> int f(T)  { return 1; }   // #1
template<class T> int f(T*) { return 2; }   // #2
template<> int f(int*) { return 5; }        // #1 (T = int*) and #2 (T = int) both match; partial ordering picks #2
int main() { int x; return f(&x) - 5; }     // calls the explicit specialization of #2
```

## The algorithm

### Transformation and deduction in both directions (¶2–¶4)

¶2 Partial ordering transforms each of the two templates in turn and performs template argument deduction using the function type, to decide which is more specialized. If deduction succeeds in both directions, the more constrained template is then chosen by constraints (see ¶8).

¶3 The transformation: for each type, constant, type template, variable template or concept template parameter (including parameter packs), synthesize a unique type, value, class template, variable template or concept respectively, and substitute it for each occurrence of that parameter in the function type. If the type of a value synthesized for a constant parameter contains a placeholder (such as `auto`), the placeholder is also replaced by a synthesized unique type. ¶4 Each synthesized template has the same *template-head* as the corresponding template template parameter.

A synthesized type is unique in the sense that it is not equal to any other type. Once `T` is transformed into `U`, deducing `P = int` from `A = U` fails, because `U` is not `int`.

The steps for comparing templates F and G:

1. Transform F, and use its parameter types as the arguments A.
2. Take G's original parameter types as the parameters P, and deduce P from A ([[temp.deduct.partial]]). If this succeeds, F is **at least as specialized as** G.
3. Conversely, deduce F from the transformed G.
4. If F is at least as specialized as G and G is not at least as specialized as F, F is **more specialized**.
5. If both directions succeed, go to ¶8 to compare constraints; if both fail, or constraints don't decide either, neither is more specialized.

The transformed F can be thought of as the most general argument F accepts. If G accepts it, G's range of acceptance includes F's; if the reverse fails, F's range is strictly smaller.

Constraints are not checked during deduction: whether the synthesized type `U` satisfies `std::integral` is never asked. Constraints are compared separately in ¶8, by subsumption between the constraints themselves ([[temp.constr.order]]).

### Deduction details (¶6, [temp.deduct.partial])

¶6 The details of deducing the other template from a transformed function type are in [[temp.deduct.partial]]:

- **Which types are compared** ([[temp.deduct.partial#3]]): in a call, only the parameters that have corresponding arguments in the call (a default argument is not an argument); for a call to a conversion function, the return types; in other contexts, such as taking an address or an explicit specialization, the whole function type.
- **Preprocessing** (paragraphs 5–7): if P or A is a reference, it is replaced by the referenced type; if both were originally references, note which side is more cv-qualified; then top-level cv-qualifiers are removed.
- **Deduction** (paragraph 8): if A came from a function parameter pack and P is not a pack, deduction fails. Otherwise deduction follows [[temp.deduct.type]], without the relaxations allowed in call deduction. If P is a function parameter pack, each remaining parameter type in A is compared with the pack's element type.
- **Tie-breaking for references** (paragraph 9): when a pair of types is the same after deduction and both P and A were originally references: if the argument template's side is an lvalue reference and the parameter template's side is not, the parameter side is considered not at least as specialized as the argument side; otherwise, if the argument side is more cv-qualified, the same conclusion is drawn.
- **Summary** (paragraph 10): if each type of F is at least as specialized as the corresponding type of G, F is at least as specialized as G.
- **Trailing packs** (paragraph 11): if F and G are each at least as specialized as the other, and G has a trailing function parameter pack for which F has no corresponding parameter, and F itself has no trailing pack, F is more specialized.
- **Unused template parameters** (paragraph 12): a template parameter may remain without a deduced value, as long as it isn't used in the types being compared.

### Member functions (¶5)

¶5 A member function template M is treated as having an extra first parameter, whose type is written X(M). If M is a member of class A with cv-qualification cv:

- ¶5.1 if M's ref-qualifier is `&&`, or M has no ref-qualifier and the corresponding parameter of the other transformed template is an rvalue reference, X(M) is an rvalue reference to cv A (if this determination depends recursively on X(M) itself, it is not an rvalue reference);
- ¶5.2 otherwise, X(M) is an lvalue reference to cv A.

Note 1 explains that this lets member functions be ordered together with non-member functions, with the same result as for two equivalent non-member functions. In addition, if exactly one of the templates was considered as a rewritten candidate with reversed parameter order ([[over.match.oper]], e.g. C++20 also considering `a == b` as `b == a`), the order of its transformed parameters is reversed too.

```cpp run ok
struct A { };
template<class T> struct B {
  template<class R> int operator*(R&) { return 1; }           // #1
};
template<class T, class R> int operator*(T&, R&) { return 2; }  // #2

// For partial ordering, #1 is treated as template<class R> int operator*(B<A>&, R&);   // #1a

int main() {
  A a;
  B<A> b;
  return (b * a) - 1;   // calls #1
}
```

| Direction | Transformed arguments | Deduction against the other | Result |
|---|---|---|---|
| #1a against #2 | `(B<A>&, U&)` | `T&` gives `T = B<A>`, `R&` gives `R = U` | succeeds |
| #2 against #1a | `(U1&, U2&)` | `B<A>&` against `U1&`: `U1` is not `B<A>` | fails |

#1 is more specialized. The `A` in `B<A>` is not a template parameter, so it isn't replaced by a synthesized type.

## Worked examples

### T, T*, const T* (¶6 Example 2)

```cpp run ok
template<class T> int f(T)        { return 1; }
template<class T> int f(T*)       { return 2; }
template<class T> int f(const T*) { return 3; }
int main() {
  const int* p = nullptr;
  return f(p) - 3;   // calls f(const T*)
}
```

The three candidates deduce `T = const int*`, `T = const int` and `T = int` respectively; the parameter types are all `const int*`, so partial ordering follows:

| Transformed argument | Parameter | Deduction | Conclusion |
|---|---|---|---|
| `T*` transformed to `U*` | `T` | `T = U*` | `T*` is at least as specialized as `T` |
| `T` transformed to `U` | `T*` | `U` is not a pointer | not the other way round |
| `const T*` transformed to `const U*` | `T*` | `T = const U` | `const T*` is at least as specialized as `T*` |
| `T*` transformed to `U*` | `const T*` | `U` has no const | not the other way round |

`f(T*)` is more specialized than `f(T)`, and `f(const T*)` is more specialized than both. The fourth row shows that deduction in partial ordering is exact matching: call deduction allows adding const to the argument ([[temp.deduct.call]]), partial ordering doesn't.

### T vs T&: always ambiguous

```cpp error
template<class T> void g(T);
template<class T> void g(T&);
void m() {
  float x;
  g(x);   // error: ambiguous
}
```

`g(T&)` transforms to `U&`, which after removing the reference is `U`, and deducing the `T` of `g(T)` succeeds. `g(T)` transforms to `U`, and deducing the `T` of `g(T&)` after removing its reference also succeeds. Both directions succeed, and the reference tie-breaker requires both sides to have been references originally; only one side is, so it doesn't apply. There are no constraints to compare, so the call is ambiguous. Overloading the same function template by value and by reference always ends this way.

### T& vs const T&, T& vs T&&

```cpp run ok
template<class T> int a(T&)       { return 1; }
template<class T> int a(const T&) { return 2; }
template<class T> int b(T&)       { return 1; }
template<class T> int b(T&&)      { return 2; }
int main() {
  const int ci = 0;
  int i = 0;
  return (a(ci) - 2) + (b(i) - 1);   // a(ci) calls a(const T&), b(i) calls b(T&)
}
```

`a(ci)`: `a(T&)` deduces `T = const int`, `a(const T&)` deduces `T = int`, and both bind `const int&`. In partial ordering, after removing references and top-level cv, deduction succeeds in both directions. But both sides were originally references, so the tie-breaker applies: when deducing with the `const T&` side as the argument, the argument side is more cv-qualified, so `T&` is considered not at least as specialized as `const T&`. As a result `a(const T&)` is more specialized. Intuitively, the `T` in `T&` can absorb const, so the pattern is broader; `const T&` hard-codes const into the pattern and is more specific.

`b(i)`: `b(T&)` deduces `T = int`, and `b(T&&)`, a forwarding reference, deduces `T = int&`; both parameter types are `int&`. In partial ordering, when deducing with the `b(T&)` side as the argument, the argument side is an lvalue reference and the parameter side is not, so `T&&` is considered not at least as specialized as `T&`. So `b(T&)` is more specialized. This rule lets forwarding-reference overloads and lvalue-reference overloads coexist.

### Only parameters with arguments are compared (¶7)

¶7 is a note: in a call, only parameters with corresponding arguments are considered, so function parameter packs, parameters with default arguments and ellipsis parameters are ignored.

```cpp run ok
template<class T> int f(T)           { return 1; }   // #1
template<class T> int f(T*, int = 1) { return 2; }   // #2
template<class T> int g(T)           { return 3; }   // #3
template<class T> int g(T*, ...)     { return 4; }   // #4

int main() {
  int* ip = nullptr;
  return (f(ip) - 2) + (g(ip) - 4);   // calls #2 and #4
}
```

`f(ip)` has one argument, so partial ordering compares only the first parameter: `T*` against `T`, and #2 is more specialized. The second parameter, which has a default argument, doesn't take part. Likewise for `g`, where the ellipsis doesn't take part.

Ignoring parameters can also lead to ambiguity (Example 4):

```cpp error
template<class T, class U> struct A { };

template<class T, class U> void f(U, A<U, T>* p = 0);   // #1
template<         class U> void f(U, A<U, U>* p = 0);   // #2
template<class T         > void g(T, T = T());          // #3
template<class T, class... U> void g(T, U...);          // #4

void h() {
  f<int>(42, (A<int, int>*)0);   // OK: calls #2
  f<int>(42);                    // error: ambiguous
  g(42);                         // error: ambiguous
}
```

- `f<int>(42, (A<int, int>*)0)` has two arguments, and both parameters are compared. #2 transforms to `(U, A<U, U>*)`; deducing #1 gives `U = U`, `T = U`, success. #1 transforms to `(U2, A<U2, U1>*)`; deducing #2 requires `U` to be both `U2` and `U1`, failure. #2 is more specialized.
- `f<int>(42)` has one argument, so only the first parameter is compared; both sides are `U`, and both directions succeed. #1's `T` only appears in a parameter with no argument, so it may remain without a value. On to ¶8: the two templates have different numbers of template parameters (2 vs 1), so by ¶8.1 neither is more specialized: ambiguous.
- In `g(42)`, the second parameter of #3 has a default argument and is ignored; #4's pack is deduced as empty and has no arguments either. Both directions succeed. The trailing-pack tie-breaker requires F to have no parameter where G has its trailing pack, but #3 has a parameter with a default argument there, so it doesn't apply: ambiguous.

An example with packs (Example 5):

```cpp run ok
template<class T, class... U> int f(T, U...)  { return 1; }   // #1
template<class T>             int f(T)        { return 2; }   // #2
template<class T, class... U> int g(T*, U...) { return 3; }   // #3
template<class T>             int g(T)        { return 4; }   // #4

int main() {
  int i;
  return (f(&i) - 2) + (g(&i) - 3);   // calls #2 and #3
}
```

`f(&i)` compares only the first parameter, `T` against `T`, and both directions succeed. #1 has a trailing pack, #2 has no parameter there and no pack of its own, so #2 is more specialized. In `g(&i)`, `T*` is more specialized than `T`; deduction already decides the winner, and the pack doesn't affect the result.

### Between variadic templates

The example from [[temp.deduct.partial#8]]:

```cpp run ok
template<class... Args>           int f(Args...)     { return 1; }   // #1
template<class T1, class... Args> int f(T1, Args...) { return 2; }   // #2
template<class T1, class T2>      int f(T1, T2)      { return 3; }   // #3

int main() {
  return (f() - 1) + (f(1, 2, 3) - 2) + (f(1, 2) - 3);
}
```

- For `f()`, only #1 is viable.
- For `f(1, 2, 3)`, #1 and #2 are viable. #2 transforms to `(U1, Us...)`, compared element by element against #1's `Args...`: success. #1 transforms to `(Us...)`; when deducing #2's `T1`, A came from a parameter pack and P is not a pack: failure. #2 is more specialized.
- For `f(1, 2)`, all three are viable. #3 deduces successfully against both others, while the transformations of the other two contain packs and fail against #3's non-pack parameters. #3 is the most specialized.

The general conclusion: non-variadic is more specialized than variadic, and a variadic template with a fixed leading parameter is more specialized than a purely variadic one.

### Parameters that appear only in the return type

```cpp run ok
template<class T> T c(int) { return 1; }            // #1
template<class T, class U> T c(U) { return 2; }     // #2
int main() { return c<int>(1) - 1; }                // calls #1
```

In a call only parameter types are compared: #1's `int` against #2's `U`. Deducing #2 from #1 gives `U = int`, success; #2's `T` appears only in the return type, so it may have no value ([[temp.deduct.partial#12]]). Deducing #1's `int` from #2's transformed `U2` fails. #1 is more specialized.

## Constraints as a tie-breaker (¶8) {{c++20}}

```cpp run ok
#include <concepts>
template<class T>         int d(T) { return 1; }   // #1
template<std::integral T> int d(T) { return 2; }   // #2

int main() { return (d(1) - 2) + (d(1.0) - 1); }   // d(1) picks #2; for d(1.0) only #1 is viable
```

For `d(1)`, deduction succeeds in both directions and the parameter lists are identical, so constraints are compared, and the more constrained #2 wins.

¶8 specifies when constraints take part:

- ¶8.1 If the two templates' template parameter lists (including invented parameters of abbreviated function templates) or function parameter lists have different lengths, neither is more specialized.
- ¶8.2.1 If exactly one template is a rewritten candidate with reversed parameters: if either template has a template parameter that isn't deducible from its function parameters, neither is more specialized; if there is no reordering, or more than one reordering, of the template parameters such that corresponding template parameters are equivalent and positionally corresponding function parameters have the same type, neither is more specialized either.
- ¶8.2.2 Otherwise, if corresponding template parameters are not equivalent ([[temp.over.link]]), or positionally corresponding function parameters have different types, neither is more specialized.
- ¶8.3 If partial ordering happens in the context of a call to a conversion function and the two templates have different return types, neither is more specialized.
- ¶8.4 Otherwise, if one template is more constrained than the other ([[temp.constr.order]]), it is more specialized.
- ¶8.5 Otherwise, neither is more specialized.

The overall idea: constraints decide only when the two templates correspond exactly apart from their constraints. The reason is that subsumption between constraints only makes sense when the template parameters on both sides refer to the same thing. The `T` and `U` of `template<std::integral T> void f(T)` and `template<class U> void f(U*)` don't correspond at all, so saying the former is more constrained is meaningless.

An example of ¶8.1:

```cpp error
#include <concepts>
template<std::integral T> void r(T);
template<class T, class U = void> void r(T);   // one extra template parameter
void t() { r(1); }                             // error: ambiguous, constraints not compared
```

Deduction succeeds in both directions (`U` isn't in the compared types), but the numbers of template parameters differ, and ¶8.1 directly rules that neither is more specialized, even though the first looks more constrained.

### Abbreviated and ordinary syntax can correspond (first half of Example 6)

```cpp run ok
template<typename> constexpr bool True = true;
template<typename T> concept C = True<T>;

void f(C auto&, auto&) = delete;    // #1: equivalent to template<C T1, class T2> void f(T1&, T2&)
template<C Q> void f(Q&, C auto&);  // #2: equivalent to template<C Q, C T2> void f(Q&, T2&)

void g(struct A* ap, struct B* bp) {
  f(*ap, *bp);   // OK: picks #2
}
int main() {}
```

Both templates have two template parameters and two function parameters, corresponding position by position, and ignoring constraints the parameters are equivalent, so constraints are compared. #2's constraints `C<Q> ∧ C<T2>` subsume #1's `C<T1>`, so #2 is more constrained, and #2 is called rather than the deleted #1. One using abbreviated syntax and the other a *template-head* doesn't prevent them from corresponding.

### Reordering for reversed candidates (second half of Example 6)

```cpp
template<typename> constexpr bool True = true;
template<typename T> concept C = True<T>;
template<typename T, typename U> struct X { };

template<typename T, C U, typename V> bool operator==(X<T, U>, V) = delete;   // #1
template<C T, C U, C V>               bool operator==(T, X<U, V>);            // #2

void h() {
  X<void*, int>{} == 0;   // standard: OK, picks #2
}
```

#1 matches normally with `T = void*, U = int, V = int`. #2 can only match in reversed form, `0 == X<...>`, with `T = int, U = void*, V = int`. Reversed, #2's parameters are `(X<U, V>, T)`, which correspond positionally to #1's `(X<T, U>, V)`, requiring #1's `[T, U, V]` to line up with #2's `[U, V, T]`. There is exactly one such reordering, and ignoring constraints the parameters are equivalent, so constraints are compared: #2 constrains all three parameters, #1 only `U`, so #2 is more constrained.

!!! warning "Compiler status"
    For this example Clang 23 reports that overload resolution selected the deleted `operator==`, i.e. it chose #1; it doesn't implement the ¶8.2.1 reordering rule. Per the standard, #2 should be chosen.

### Conversion functions (¶8.3)

When partial ordering is done for a call to a conversion function, return types are compared ([[temp.deduct.partial#3]]). ¶8.3 further says that when two conversion function templates have different return types, constraints don't decide: conversion functions with different target types are not differently constrained versions of the same function.

## Partial specializations reuse these rules

When deciding which of two partial specializations of a class template or variable template is more specialized ([[temp.spec.partial.order]]), each partial specialization is rewritten as a function template with a single parameter, and the algorithm on this page is used as is, comparing the whole function type. So the worked methods on this page apply to partial specializations too.

## Implementation notes

!!! impl
    - Compilers implement partial ordering by replacing template parameters with a set of opaque special types and reusing the deduction engine. Not matching any concrete type is exactly the property of an opaque type.
    - Clang's ambiguity diagnostics list each candidate and its deduced arguments (`candidate function [with T = ...]`), but don't explain why partial ordering failed. To find out, you have to work it through yourself using the tables on this page.

## History

!!! history
    - The C++98 partial ordering rules were already largely in place: transformation, deduction in both directions, handling of references and cv.
    - C++11 variadic templates brought rules for function parameter packs ([[temp.deduct.partial]] paragraphs 8 and 11); rvalue references brought the tie-breaker favoring lvalue references; X(M) for member functions began taking ref-qualifiers into account.
    - C++20 let constraints decide when deduction succeeds in both directions, and required the two templates to correspond apart from constraints; reversed candidates for `operator==` brought the parameter reversal in ¶5 and the reordering rule in ¶8.2.1.
    - C++26 added variable template template parameters and concept template parameters, and ¶3 correspondingly synthesizes unique variable templates and concepts for them.

## Common misconceptions

!!! pitfall "Partial ordering compares which specialization matches the arguments better"
    No. Partial ordering compares the templates themselves, independent of the actual arguments; the arguments only decide which parameters take part.

!!! pitfall "`f(T&&)` is an rvalue reference, so it is more specialized than `f(T&)`"
    The opposite. For an lvalue argument, `f(T&)` is more specialized ([[temp.deduct.partial#9]]).

!!! pitfall "The constrained version always wins"
    Constraints are compared only when the two templates correspond exactly apart from constraints. If the number of template parameters or the parameter types differ, constraints have no effect (¶8.1, ¶8.2.2).

!!! pitfall "A default argument can make a template more specialized"
    In a call, parameters with no corresponding argument, including parameters with default arguments, don't take part in partial ordering at all.

## Questions

!!! question "Question 1"
    Which one does the following call choose?

    ```cpp
    template<class T> void p(T, int);    // #1
    template<class T> void p(int, T);    // #2
    p(1, 1);
    ```

<details markdown="1">
<summary>Answer</summary>

It's ambiguous. Both templates are viable (`T = int`), and both parameter types are `(int, int)`. #1 transforms to `(U, int)`; deducing #2's `(int, T)` fails at the first position, `int` against `U`. #2 transforms to `(int, U)`; deducing #1's `(T, int)` fails at the second position. Both directions fail, so neither is more specialized. Each template is more specific than the other in one position, and neither wins overall. Clang 23 reports the call as ambiguous.
</details>

!!! question "Question 2"
    With `template<class T> void f(T*)` and `template<class T> void f(const T*)`, why does `int* p; f(p);` choose the former and `const int* q; f(q);` the latter?

<details markdown="1">
<summary>Answer</summary>

`f(p)`: the parameter of `f(T*)` is `int*`, an identity conversion; the parameter of `f(const T*)` is `const int*`, which needs a qualification conversion. By [[over.ics.rank]] the identity conversion sequence is better, so comparing conversion sequences already selects `f(T*)`, and partial ordering never comes into play.

`f(q)`: both parameter types are `const int*`, the conversion sequences are the same, partial ordering follows, and `f(const T*)` is more specialized. Many choices that seem to be made by partial ordering are actually settled when conversion sequences are compared.
</details>

!!! question "Question 3"
    With `template<class T> int f(T, T*)` and `template<class T, class U> int f(T, U*)`, which does `int i; f(i, &i)` choose? What if the second is changed to `template<class T, class U> requires std::same_as<T, U> int f(T, U*)`?

<details markdown="1">
<summary>Answer</summary>

In the first case, the first template. The first transforms to `(V, V*)`, and deducing the second gives `T = V, U = V`, success; the second transforms to `(V1, V2*)`, and deducing the first requires `T` to be both `V1` and `V2`, failure.

In the second case, still the first template. Deduction ignores constraints, so the result is the same as before: only one direction succeeds, and constraints never get a chance to take part. Even if both directions succeeded, the two templates have different numbers of parameters, and ¶8.1 would still disable the constraints. Constraints can't make a template with a more general shape more specialized. Clang 23 agrees.
</details>
