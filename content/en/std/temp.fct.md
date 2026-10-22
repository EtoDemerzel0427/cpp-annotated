---
title: Function templates
summary: "How a function template relates to a non-template function with the same name, when two function template declarations are the same template and when they are two overloads, and how expressions in signatures are compared."
updated: 2026-10-19
---

!!! tldr
    - A non-template function with the same name and type as a function template is not its specialization. If it is called, it needs its own definition; the compiler won't generate one from the template.
    - The signature of a function template specialization includes the template parameter list and template arguments, so two different templates can generate specializations of the same type without conflict.
    - Expressions in a signature that refer to template parameters (such as `A<I+J>`) are part of the signature. Whether two declarations are the same template is decided by comparing tokens one by one, with parameters allowed to be renamed.
    - Two declarations written differently but giving the same result for every argument (functionally equivalent), such as `A<I+10>` and `A<I+1+2+3+4>`, make the program ill-formed, no diagnostic required.

A function template defines a family of functions ([temp.fct.general] ¶1). For example, `template<class T> void sort(Array<T>&);` defines a `sort` for each `T`. This page covers two questions: how a function template relates to an ordinary function with the same name, and when two function template declarations are the same template. How function templates are ordered against each other is in [[temp.func.order]].

## A non-template function is not a specialization of the template [temp.fct.general]

```cpp run
void f(int);                      // non-template function, declaration only
template<class T> void f(T) { }   // function template, with a definition

int main() { f(1); }              // selects f(int), fails to link
```

The call `f(1)` has two candidates: the non-template `f(int)` and `f<int>(int)` deduced from the template. When they are equally good, overload resolution prefers the non-template ([[over.match.best]]). But `f(int)` has no definition; Clang 23 compiles the code, and the link fails with `f(int)` undefined.

¶2 The standard states explicitly that a non-template function is not related to a function template, and is never considered a specialization of it, even if it has the same name and type as a specialization the template could generate. A footnote explains that such a non-template declaration doesn't merely guide overload resolution; if it is odr-used it must be defined, and the compiler won't instantiate it from the template's definition.

There are two ways to customize a template's behavior for a particular type, and they are different things:

| | Non-template overload `void f(int)` | Explicit specialization `template<> void f(int)` |
|---|---|---|
| A specialization of the template? | No, a different function | Yes |
| How it takes part in overload resolution | As an independent candidate | Not on its own: the template is selected first, then the specialization's definition is used |
| When tied with the template | Wins over the template | Goes with the template |
| Implicit conversion of arguments | Allowed, no deduction needed | Only used if template deduction succeeds |

Generally prefer overloading. Explicitly specialize a function template ([[temp.expl.spec]]) only when an interface specifically requires a specialization (as some customization points do).

## Whether two declarations are the same template [temp.over.link]

For ordinary functions, comparing parameter types is enough to decide whether two declarations are a redeclaration or an overload. A function template's signature may contain expressions like `A<I+J>`, and comparison becomes harder: are `I+J` and `J+I` the same? What about `I+10` and `I+1+2+3+4`? This subclause's answer: compare by token structure; where the structure differs but the meaning is the same, the program is ill-formed, no diagnostic required.

### Specializations of different templates can have the same type (¶1–¶3)

¶1 Function templates can be overloaded so that two different specializations have the same type:

```cpp title="tu1.cpp"
template<class T> void f(T*);
void g(int* p) {
  f(p);    // calls f<int>(int*), from f(T*)
}
```

```cpp title="tu2.cpp"
template<class T> void f(T);
void h(int* p) {
  f(p);    // calls f<int*>(int*), from f(T)
}
```

¶2 These two specializations are different functions; although both have type `void(int*)`, they don't violate the ODR. The reason is that the signature of a function template specialization isn't just the function type; it also includes the template parameter list, the template arguments and the return type ([[intro.defs]]). Under the Itanium ABI, their mangled names encode `T*` with `T = int` and `T` with `T = int*` respectively, and the linker sees two symbols.

¶3 In a function template signature, the names of template parameters only serve to connect the parameters to the rest of the signature; the names themselves don't matter. Note 1 points out that two templates can have identical return types and function parameter lists:

```cpp run ok
template<class T> void f() { }
template<int I>   void f() { }   // OK: another template, different kind of parameter
int main() {
  f<int>();   // the first
  f<1>();     // the second
}
```

Overload resolution alone can't tell them apart, but explicit template arguments can.

### Expressions in signatures (¶4)

¶4 If an expression referring to template parameters is used in a function template's parameter list or return type, that expression is part of the signature. This is what allows a declaration in one translation unit to be linked with a declaration in another, and keeps templates meant to be different from being wrongly linked together.

```cpp error
template<int> struct A { };
template<int I, int J> A<I+J> f(A<I>, A<J>);                  // #1
template<int K, int L> A<K+L> f(A<K>, A<L>) { return { }; }   // same as #1: defines #1
template<int I, int J> A<I-J> f(A<I>, A<J>) { return { }; }   // different from #1: another overload

void t() { f(A<1>{}, A<2>{}); }   // error: ambiguous
```

The return types `A<I+J>` and `A<I-J>` make the two templates different overloads. At the call their parameters are exactly the same and partial ordering can't separate them, so the call is ambiguous. Note 2 adds that such expressions mostly use constant template parameters, but they can also refer to type parameters, as in `sizeof(T)`.

### Equivalence: comparing tokens (¶5)

¶5 Two expressions involving template parameters are **equivalent** if two function definitions containing the expressions would satisfy the ODR ([[basic.def.odr]]), except that the tokens used to name the template parameters may differ as long as a token used to name a template parameter in one expression is replaced by another token that names the same template parameter in the other.

Intuitively, compare token by token, allowing template parameters to be renamed by position. So:

- `A<I+J>` (parameters `I, J`) and `A<K+L>` (parameters `K, L`) are equivalent;
- `I+J` and `J+I` are not equivalent; the token order differs;
- `N*2` and `(N*2)` are not equivalent; parentheses are tokens too.

¶5 has three further rules:

- **Unevaluated operands that don't involve template parameters** (such as the operand of `sizeof` or `decltype`) are equivalent if they refer to the same types and declarations, even with different tokens. Note 3's example is that `A<42>` and `A<40+2>` refer to the same type.
- **Two lambda-expressions are never equivalent.** Note 4 explains the intent: to keep lambdas out of the signatures of function templates with external linkage. Every lambda has a unique closure type, and lambdas written identically in two translation units can't be guaranteed to have the same type.
- **Dependent names** ([[temp.dep]]) are compared by name only, not by the result of name lookup. Note 5 points out that an unqualified dependent name in a signature is looked up from the first declaration of the function template ([[temp.res.general]]).

An example of the last rule:

```cpp
template<class T> decltype(g(T())) h();
int g(int);
template<class T> decltype(g(T())) h()   // redeclaration of h; uses the lookup from the first declaration
  { return g(T()); }                     // even though g(int) can be found here
int i = h<int>();                        // substitution failure: g(int) isn't visible at the first declaration
```

The name in both `decltype(g(T()))` is `g`, so they are equivalent and the second declaration redeclares the first. Lookup of `g` in the signature happens at the first declaration, when `g(int)` hasn't been declared yet. At instantiation a dependent call only adds argument-dependent lookup, and `int` has no associated namespaces, so `g(int)` isn't found and substitution fails.

!!! warning "Compiler status"
    Clang 23 accepts `int i = h<int>();`; it finds the later-declared `g(int)` when instantiating the signature. Per the standard, substitution should fail here. Portable code shouldn't rely on a dependent call in a signature finding functions declared later.

### Functional equivalence (end of ¶5)

Two expressions that are not equivalent are **functionally equivalent** if they give the same result for every set of template arguments. Specifically:

- for potentially-evaluated expressions, they evaluate to the same value for any template arguments;
- for unevaluated operands, they perform the same operations on the same entities in the same order for any template arguments. Note 6's example is an extra pair of redundant parentheses.

The second half of the standard's example:

```cpp
// IFNDR: the two expressions are functionally equivalent but not equivalent
template<int N> void foo(const char (*s)[([]{}, N)]);
template<int N> void foo(const char (*s)[([]{}, N)]);

// two different declarations: the non-dependent parts are not equivalent
template<class T> void spam(decltype([]{}) (*s)[sizeof(T)]);
template<class T> void spam(decltype([]{}) (*s)[sizeof(T)]);
```

The array bound `([]{}, N)` of `foo` refers to a template parameter and contains a lambda, so the two sides are not equivalent; but its value is `N` for every `N`, so the two sides are functionally equivalent and fall under the IFNDR of ¶7 below. In `spam`, `decltype([]{})` doesn't involve template parameters; the two lambdas are not equivalent, so the two `decltype`s are different types, and these two lines definitely declare two different templates.

Functional equivalence only covers the two kinds of expression above; Example 4 shows its limits:

```cpp run ok
template<int I> concept C = true;
template<typename T> struct A {
  void f() requires C<42>;   // #1
  void f() requires true;    // OK: a different function
};
int main() {}
```

`C<42>` and `true` both have the value `true`, but neither refers to a template parameter, and neither is an unevaluated operand, so the definition of functional equivalence doesn't apply. Their tokens differ, so they are not equivalent, and the two `f` are different member functions. The class itself is valid, but when `f()` is called both constraints are satisfied and neither is more constrained, so Clang 23 reports the call as ambiguous.

### Equivalence of template-heads (¶6)

¶6 Two *template-head*s (`template<...>` plus an optional requires-clause) are equivalent if three things hold:

- their template parameter lists have the same length and corresponding parameters are equivalent;
- if a parameter on one side has a *type-constraint* (such as `Int` in `template<Int T>`), the other side has one too, and they are equivalent;
- if one side has a requires-clause, the other side has one too, and the constraint expressions are equivalent.

Two template parameters are equivalent if:

- ¶6.1 they are the same kind: type, constant, type template template, variable template template, or concept;
- ¶6.2 if one is a pack, the other is too;
- ¶6.3 constant parameters have equivalent types, ignoring *type-constraint*s on placeholder types;
- ¶6.4 template template parameters have equivalent *template-head*s.

Two *template-head*s are functionally equivalent if they accept and are satisfied by the same set of template argument lists.

```cpp
template<class T> concept Int = __is_integral(T);

template<Int T>                   void g(T);   // #1
template<class T> requires Int<T> void g(T);   // #2: functionally equivalent to #1 but not equivalent, IFNDR
template<Int T> requires true     void g(T);   // #3: not equivalent to #1, has an extra requires-clause
```

`template<Int T>` and `template<class T> requires Int<T>` are two ways of writing the constraint and accept exactly the same arguments. But ¶6 requires that if one side has a *type-constraint* the other does too, so they are not equivalent.

### Functionally equivalent but not equivalent: IFNDR (¶7–¶8)

The first sentence of ¶7: if the validity or meaning of the program depends on whether two constructs are equivalent, and they are functionally equivalent but not equivalent, the program is {{ifndr}}.

The second sentence closes a loophole. Suppose two function template declarations A and B:

- ¶7.1 introduce the same name;
- ¶7.2 have corresponding signatures ([[basic.scope.scope]]);
- ¶7.3 would declare the same entity ([[basic.link]]) if they were considered to correspond;
- ¶7.4 accept and are satisfied by the same set of template argument lists;

but do not in fact correspond because their *template-head*s or trailing constraints are not equivalent. Such a program is also IFNDR. #1 and #2 above are this case. In practice, Clang compares tokens, treats them as two different templates, and reports `g(1)` as ambiguous.

The note in ¶8 gives a set of contrasts:

```cpp
template<int> struct A { };

// Guaranteed to be the same
template<int I> void f(A<I>, A<I+10>);
template<int I> void f(A<I>, A<I+10>);

// Guaranteed to be different
template<int I> void f(A<I>, A<I+10>);
template<int I> void f(A<I>, A<I+11>);

// IFNDR
template<int I> void f(A<I>, A<I+10>);
template<int I> void f(A<I>, A<I+1+2+3+4>);
```

Note 7 explains the design intent: declarations guaranteed to be equivalent are always linked together, while implementations are not required to go to great lengths to ensure that functionally equivalent declarations are treated as distinct.

Why not say that functionally equivalent declarations are the same? Because deciding whether two arbitrary expressions give the same result for all arguments is in general undecidable. Why not say that non-equivalent declarations are always different? Because then compilers would have to preserve every source token when generating mangled names, redundant parentheses included, whereas many implementations normalize expressions first. IFNDR lets the standard permit both approaches.

!!! impl "Expressions in mangled names"
    The Itanium ABI encodes dependent expressions in signatures as expression trees, so `A<I+10>` and `A<I+1+2+3+4>` have different mangled names, and Clang and GCC treat them as two templates. When called in the same translation unit, both deduce the same results with the same parameters, so the call is reported as ambiguous; when declared and defined separately in different translation units, the symptom is an unresolved symbol at link time. Both are outcomes IFNDR allows.

```cpp ifndr
template<int> struct A { };
template<int I> void f(A<I>, A<I+10>);
template<int I> void f(A<I>, A<I+1+2+3+4>) { }
void t() { f(A<1>{}, A<11>{}); }   // Clang 23: ambiguous call
```

## History

!!! history
    - The framework of equivalence and functional equivalence has existed since C++98, at the time aimed at constant expressions like `A<I+J>`.
    - C++11's `decltype` brought arbitrary expressions (including function calls) into signatures, which made the rule that dependent names are compared by name only important.
    - C++20 introduced constraints, so ¶6 was extended to *type-constraint*s and requires-clauses, and the second sentence of ¶7 handles constraints written in different forms; lambdas became allowed in unevaluated operands, so the rule that lambdas are never equivalent was added.
    - C++26 added variable template template parameters and concept template parameters, and the kinds of parameter in ¶6.1 were extended accordingly.

## Common misconceptions

!!! pitfall "If you declare a non-template function with the same name and type, the compiler generates its definition from the template"
    It doesn't ([temp.fct.general] ¶2). It is a different function and needs its own definition when used.

!!! pitfall "`template<C T>` and `template<class T> requires C<T>` can be mixed between declaration and definition"
    They are functionally equivalent but not equivalent, and mixing them is IFNDR. Clang treats them as different templates and reports the call as ambiguous.

!!! pitfall "`A<I+J>` and `A<J+I>` are the same"
    They are not equivalent. For integer addition they are functionally equivalent, so mixing them in two declarations is IFNDR.

!!! pitfall "Two specializations with the same function type violate the ODR"
    They don't. They are specializations of different templates and have different signatures.

## Questions

!!! question "Question 1"
    Which of the following declarations are the same template, which are different templates, and which are IFNDR?

    ```cpp
    template<int> struct A {};
    template<int N> void f(A<N*2>);   // (a)
    template<int M> void f(A<M*2>);   // (b)
    template<int N> void f(A<(N*2)>); // (c)
    template<int N> void f(A<2*N>);   // (d)
    template<int N> void f(A<N*3>);   // (e)
    ```

<details markdown="1">
<summary>Answer</summary>

- (a) and (b): only the parameter is renamed; they are equivalent and the same template.
- (a) and (c): redundant parentheses. Parentheses are tokens, so the two expressions are not equivalent; but they have the same value for every `N`, so they are functionally equivalent, and it's IFNDR (Note 6 uses exactly redundant parentheses as its example).
- (a) and (d): `N*2` and `2*N` have different token orders and are not equivalent; the values are the same, so they are functionally equivalent: IFNDR.
- (a) and (e): not equivalent, and with `N = 1` the values differ, so not functionally equivalent either; guaranteed to be two different templates.
</details>

!!! question "Question 2"
    Given `template<class T> void f(T) {}` and `void f(int) {}`, are the pointers `&f<int>` and `static_cast<void(*)(int)>(&f)` equal?

<details markdown="1">
<summary>Answer</summary>

No. `&f<int>` points to the template specialization. `static_cast<void(*)(int)>(&f)` takes the address of an overload set ([[over.over]]); the candidates are the non-template `f(int)` and the deduced `f<int>`, the non-template wins, and the result points to the non-template `f(int)`. They are different functions ([temp.fct.general] ¶2). With Clang 23, the comparison evaluates to 0 at run time.
</details>
