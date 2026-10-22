---
title: Names of template specializations
summary: How the compiler decides whether < is a less-than operator or the start of a template argument list, when the template keyword is required, and how >> is split; when a template-id is valid and when its constraints are checked; why a concept-id is a bool value.
updated: 2026-10-19
---

!!! tldr
    - A `<` after a name starts a template argument list only if the compiler knows the name is a template; otherwise it is less-than.
    - In a template, names that depend on template parameters, such as `p->alloc<200>()` and `T::adjust<100>()`, cannot be looked up, and must be written `p->template alloc<200>()`.
    - Since C++20, when unqualified name lookup finds nothing or finds only functions, `<` also starts a template argument list, so `get<0>(t)` can find a function template through ADL.
    - The first non-parenthesized `>` in a template argument list ends the list, and `>>` is split into two `>`. Parenthesize a `>` operator inside angle brackets.
    - Constraints of class templates and alias templates are checked as soon as the name is written, `S<int>*` included; a concept-id such as `C<int>` is a `bool` value, not a specialization.

A **specialization** of a template is referred to by the template name followed by arguments in angle brackets, as in `std::vector<int>`, `f<double>` or `operator+<int>`. This form is called a **template-id**.

## Is `<` less-than or an angle bracket? (¶7)

```cpp title="template-keyword.cpp" error
#include <cstddef>
struct X {
    template<std::size_t> X* alloc();
    template<std::size_t> static X* adjust();
};

template<class T> void f(T* p) {
    T* p1 = p->alloc<200>();            // error: < is less-than
    T* p2 = p->template alloc<200>();   // OK
    T::adjust<100>();                   // error: < is less-than
    T::template adjust<100>();          // OK
}
```

C++ writes template arguments in angle brackets, but `<` and `>` are also comparison operators. `a < b > c` could be `(a < b) > c`, or the declaration of a variable `c` of type `a<b>`. The parser must decide which as soon as it reads `<`, and the standard's answer is: look at whether the preceding name is a template.

In the definition of the template `f`, the type of `p`, `T*`, depends on a template parameter, so what `p->alloc` refers to is only known at instantiation ([[temp.dep]]). At the definition the parser cannot see that `alloc` is a template, so it treats `<` as less-than. Where a template is meant, the programmer says so by writing `template` before the name.

`p->alloc<200>()` is an error because, parsed as less-than, the `()` in `p->alloc < 200 > ()` is an empty pair of parentheses, which is not a valid expression. In other cases, parsing as less-than may happen to be valid, and the program silently means something else. Clang 23 reports "missing 'template' keyword prior to dependent template name" for both errors above.

### The full rule

¶7 A `<` starts a template argument list if any of the following holds:

- ¶7.1 {{c++26}} it follows a reflection splice `[:r:]` (*splice-specifier*), and the splice is in a type-only context or is preceded by `template` or `typename`;
- ¶7.2 {{c++29}} it follows a pack-index template name `TTs...[I]` (see the end of the page);
- ¶7.3 it follows a name that is not a conversion function name, and:
    - ¶7.3.1 the name is preceded by `template` or `~`, which appear after the `::` of a qualified name or after a member access `.` or `->`;
    - ¶7.3.2 name lookup finds a template, or the injected-class-name of a class template (the name used inside a class template to refer to itself);
    - ¶7.3.3 it is an unqualified name, and lookup finds only functions or finds nothing;
    - ¶7.3.4 the name is in a using-declaration, is the name being declared in a declarator, or is the last name in a type-only context.

¶7.3.2 is the usual case. ¶7.3.1 is the `template` keyword above. ¶7.3.4 handles names in declarations: for example, the `f` in the explicit specialization `template<> void f<int>(int);` is the name being declared, which can't be the left operand of a comparison, so it is taken as a template name directly.

Only names whose lookup is deferred need `template`. If the object type of a member access doesn't depend on template parameters, lookup happens immediately and ¶7.3.2 applies directly:

```cpp run title="nondependent.cpp" ok
struct S { template<int> int g() { return 0; } };

template<class T> int h(T t) {
    S s;
    return s.g<1>()                // s does not depend on T: no template needed
         + t.template g<1>();      // t depends on T: needed
}
int main() { return h(S{}); }
```

### When lookup finds nothing (¶7.3.3) {{c++20}}

```cpp run title="adl-template.cpp" ok
namespace N {
    struct A {};
    template<class T> int f(A) { return 1; }
}

int g() {
    return f<int>(N::A{});   // ordinary lookup doesn't find f; ADL finds it in N
}
int main() { return g() - 1; }
```

In C++17, ordinary unqualified lookup doesn't find `f`, so `f < int > (N::A{})` is parsed as a comparison; `int` is not an expression, and the program is ill-formed. This meant explicit template arguments and argument-dependent lookup (ADL, looking up functions in the namespaces associated with the argument types) could not be used together. The typical example is writing `get<0>(t)` without `using std::get`.

C++20's [[P0846R0]] added ¶7.3.3: when unqualified name lookup finds nothing, or finds only functions, `<` is also taken as the start of a template argument list, and ADL then finds the actual function template. The only-functions case is included because comparing a function with something else is almost never meaningful. Clang 23 accepts the code above under `-std=c++17` too, with just a `-Wc++20-extensions` warning.

In rare cases this rule changed the meaning of old code: if there is an ordinary function named `f` in scope, `f < 0 > (x)` is a comparison in C++17 but a template argument list in C++20, which usually results in an error.

## `>` and `>>` (¶8)

```cpp title="right-angle.cpp" error
template<int i> class X {};
template<class T> class Y {};

X< 1>2 > x1;        // error: the first > ends the list
X<(1>2)> x2;        // OK

Y<X<1>> x3;         // OK: same as Y<X<1> > x3;
Y<X<6>>1>> x4;      // error: >> is split and ends X's list
Y<X<(6>>1)>> x5;    // OK
```

¶8 When parsing a template argument list, the first non-nested `>` ends the list rather than being greater-than. The first non-nested `>>` is treated as two separate `>` tokens: the first ends the current list, and the second can end an enclosing list or belong to some other construct.

A `>` inside parentheses is nested. Per the footnote, the `>` in the four casts such as `static_cast<T>`, and the `>` of another template-id in the list, also count as nested.

In C++03 `>>` was always the right-shift operator, so `Y<X<1>>` was a syntax error and had to be written `Y<X<1> >`. C++11's [[N1757]] introduced the splitting rule. The cost is that a few C++03 programs changed meaning: `X< 1>>2 >` is `X<(1>>2)>` in C++03 and a syntax error in C++11.

So whenever a `>`, `>>`, `>=` or `>>=` operator appears in a template argument, parenthesize it.

## Other rules for the `template` keyword (¶9, ¶11)

<div class="compare" markdown="1">

```cpp ok
template<class T> struct A {
  void f(int);
  template<class U> void f(U);
};
template<class T> void g(T t) {
  A<T> a;
  a.template f<>(t);  // calls the template
}
```

```cpp error
template<class T> struct A {
  void f(int);
  template<class U> void f(U);
};
template<class T> void g(T t) {
  A<T> a;
  a.template f(t);  // error
}
```

</div>

¶11 A name preceded by `template` must be followed by a template argument list, even an empty `<>`. The other case is a name that refers to a class template or alias template without an argument list, such as the template template argument `T::template C`; this form is deprecated ([[depr.template.template]]). `template` also cannot go directly before `~` to name a destructor; `p->template ~T()` is an error.

Note 5: as with `typename`, adding `template` is well-formed even if lookup would find the template anyway. Writing the keyword unnecessarily is harmless; omitting it where needed is not. Since C++11 it can also be written outside templates. Note 4: `template` cannot be put before a non-template member of a class template.

¶9 `template` cannot appear in the qualified name of an entity being declared:

```cpp title="declarative-template.cpp" error
struct S { template<class T> void f(); };
template<> void S::template f<int>() {}   // error: violates ¶9
```

Clang 23 only gives a warning for this (`-Wtemplate-in-declaration-name`). A warning is still a diagnostic, which satisfies the standard ([[intro.compliance]]), but the code is still ill-formed.

## When a template-id is valid (¶13)

```cpp title="validity.cpp" error
template<class T, T::type n = 0> class X;
struct S { using type = int; };

using T1 = X<S, int, int>;   // error: too many arguments
using T2 = X<>;              // error: T has no default argument
using T3 = X<1>;             // error: 1 can't correspond to a type parameter
using T4 = X<int>;           // error: int::type is invalid
using T5 = X<S>;             // OK
```

¶13 A template-id is **valid** ([[g:valid-template-id]]) if:

- ¶13.1 there are at most as many arguments as parameters, or one of the parameters is a parameter pack;
- ¶13.2 there is an argument for each parameter that has no default argument, is not a pack and cannot be deduced;
- ¶13.3 each argument matches its corresponding parameter ([[temp.arg]]);
- ¶13.4 substituting the arguments into later parameters succeeds, such as `T::type` in the example above;
- ¶13.5 if the template-id is not dependent, the template's constraints are satisfied (see the next section).

A template-id that names a class template, alias template or variable template must be valid, otherwise the program is ill-formed. A template-id that names a function template may be incomplete for now; the remaining arguments are filled in by template argument deduction, and a failure of deduction or substitution just discards that candidate (SFINAE, [[temp.deduct]]) rather than being an error. This is also why ¶13.2 talks about parameters that cannot be deduced.

## Constraints are checked as soon as the name is written (¶14)

```cpp title="constraint-check.cpp" error
template<typename T> concept C1 = sizeof(T) != sizeof(int);

template<C1 T> struct S1 {};
template<C1 T> using Ptr = T*;

S1<int>* p;               // error: constraints not satisfied
Ptr<int> q;               // error: constraints not satisfied

template<typename T>
struct S3 { Ptr<T> x; };  // OK: the argument depends on T, not checked now
S3<int> x;                // error: Ptr<int> is checked at instantiation
```

¶14 When a template-id names a constrained class template, alias template or variable template, or a constrained template template parameter, and none of its arguments are dependent ([[temp.dep.temp]]), the template's constraints must be satisfied.

`S1<int>*` is just a pointer type; it doesn't require `S1<int>` to be complete and doesn't instantiate it, but the constraints must still be satisfied. Constraints thereby become part of the type system: the type `S1<int>` doesn't exist at all, rather than existing but being impossible to instantiate.

When the arguments depend on template parameters, the check is deferred to instantiation. If a template definition names something whose constraints aren't satisfied and that doesn't depend on template parameters, such as `Ptr<int>` inside `S2<T>`, the template can have no valid specialization, which per [[temp.res]] is ill-formed, no diagnostic required. Clang 23 still reports an error.

Explicit instantiations and explicit specializations must also satisfy the constraints; you can't use an explicit specialization to supply a definition for arguments that don't satisfy them:

```cpp title="explicit-spec-constraint.cpp" error
template<typename T> concept C2 = sizeof(T) == 1;
template<C2 T> struct S {};

template struct S<char[2]>;         // error: constraints not satisfied
template<> struct S<char[2]> {};    // error: constraints not satisfied
```

Function templates are not covered by ¶14. Their constraints are checked during overload resolution ([[over.match.viable]]), and failing them just makes the candidate non-viable.

## A concept-id is a `bool` value (¶15)

```cpp title="concept-id.cpp" error
template<typename T> concept C = sizeof(T) > 1;

static_assert(C<int>);           // OK
static_assert(!C<char>);         // OK: not satisfied simply means false
constexpr bool b = C<int> && C<long>;
auto p = &C<int>;                // error: cannot take the address of a prvalue
```

¶15 A template-id whose template name is a concept name is called a **concept-id** ([[g:concept-id]]). It is a prvalue of type `bool` and does not name any specialization, because concepts are never instantiated ([[temp.concept#5]]). Its value is `true` if the arguments satisfy the concept's normalized constraint expression, and `false` otherwise.

Note 6: a constraint expression is an unevaluated operand, so a concept-id in a constraint expression is not evaluated to a `bool` and then combined like an ordinary expression. When `C<T> && D<T>` is a constraint, it is checked term by term according to the conjunction rule in [[temp.constr.op]], checking only as much as is needed to decide satisfaction.

!!! lawyer "A concept-id inside and outside constraints"
    - In a *requires-clause* or concept definition, `C<T>` is normalized, expanded into the atomic constraints of `C`, and takes part in subsumption between constraints ([[temp.constr.normal]]).
    - In an ordinary expression, such as `static_assert(C<int>)` or `if constexpr (C<T>)`, `C<int>` is just a `bool` value.
    - If a concept-id is wrapped in another expression, such as `!C<T>`, `(C<T> == true)` or `bool(C<T>)`, the whole expression becomes one atomic constraint, is no longer expanded, and therefore can't take part in subsumption ([[temp.constr.atomic]]).

## History

!!! history
    - C++98 established the disambiguation rules for the `template` keyword; `>>` was the right-shift token, and nested templates had to be written `> >`.
    - C++11 introduced splitting of `>>` ([[N1757]]) and allowed the `template` keyword outside templates.
    - C++20 added ¶7.3.3 ([[P0846R0]]) and concept-ids, as well as the constraint checking in ¶14. In the same version, [[P0634R3]] made dependent qualified names default to types in several contexts, so `typename` isn't needed there. These contexts were later organized as type-only contexts ([[temp.res.general#4]]), which is what ¶7.3.4 refers to.
    - C++26 added `<` after a splice (¶7.1, ¶10) and *template-argument-name*, and deprecated `template` not followed by an argument list. After C++26 was finalized, [[P3670R4]] added pack-index template names (¶3–¶6, ¶7.2).

## Common misconceptions

!!! pitfall "The compiler figures out by itself whether `template` is needed"
    It doesn't. A `<` after a name that depends on template parameters is less-than by default (¶7).

!!! pitfall "`S<int>*` is just a pointer and doesn't need to satisfy the constraints"
    It does. As soon as a non-dependent `S<int>` is written, its constraints must be satisfied (¶14). An explicit specialization can't get around the constraints either.

## Questions

!!! question "Question 1"
    In the template definition `template<class T> void f(T t) { t.get<0>(); }`, if the global scope happens to contain a function template `template<int> void get();`, how is the `<` parsed?

<details markdown="1">
<summary>Answer</summary>

As less-than; `t.get<0>()` is ill-formed and must be written `t.template get<0>()`.

The `get` in `t.get` is a member name, looked up in the type of `t` ([[basic.lookup.qual.general#2]]). That type depends on `T`, so lookup is deferred to instantiation ([[basic.lookup.qual.general#3]]) and the global `get` plays no part, so ¶7.3.2 doesn't apply; `get` isn't an unqualified name either, so ¶7.3.3 doesn't apply. Clang 23 reports "missing 'template' keyword prior to dependent template name".

Earlier standards required a second lookup in the context of the entire postfix-expression, and compilers behaved inconsistently. The current rule makes the result independent of whatever happens to be in the global scope.
</details>

!!! question "Question 2"
    Does `Y<X<1>>2>> y;` compile (where `X` is `template<int>` and `Y` is `template<class>`)? How do you fix it?

<details markdown="1">
<summary>Answer</summary>

No. The `>>` in `X<1>>2` is split into two `>`: the first ends `X<1>`, the second ends `Y<X<1>>`, and the remaining `2>> y;` can't be parsed. Write `Y<X<(1>>2)>> y;` instead.
</details>

!!! question "Question 3"
    Which of these declarations requires the constraints to be satisfied?

    ```cpp
    template<std::integral T> struct S {};
    template<class T> void f(S<T>*);       // (a)
    void g(S<double>*);                    // (b)
    ```

<details markdown="1">
<summary>Answer</summary>

In (a), the argument of `S<T>` depends on `T`, and ¶14 doesn't require satisfaction at this point. In (b), `S<double>` doesn't depend on template parameters, so its constraints must be satisfied. `std::integral<double>` is false, so (b) is ill-formed, even if `g` is never called and `S<double>` is never instantiated.
</details>

<details class="fine" markdown="1"><summary>Remaining wording</summary>

¶1 gives the grammar of a template-id. Besides `template-name<argument-list>` (*simple-template-id*), an operator function name or literal operator name can also be followed by an argument list, as in `operator+<int>` and `operator""_x<'a'>`. A template argument can be a type (*type-id*), a constant expression, a braced list (such as `C<{42}>`, used to initialize a constant parameter), or a possibly qualified name (*template-argument-name*) {{c++26}}. An argument in name form is first looked up as a name, and then [[temp.arg.general#3]] decides from the lookup result whether it is a template, a type or an expression; this is what lets concepts and variable templates be template template arguments.

¶2 and ¶12 define component names: the component name of a template-id is the first name in it; the component names of a *template-argument-name* are the names in its qualifying part and the final identifier. Other subclauses use this term to specify lookup.

¶3–¶6 {{c++29}} Pack-index template names `P...[I]`: `P` must be a template template parameter pack, and `I` a converted constant expression of type `std::size_t` with `0 ≤ I < sizeof...(P)`. It is itself a pack expansion and names the `I`-th template name in the pack, as in `TTs...[0]<int>`. At the time of writing, Clang 23 supports pack indexing of types and expressions but not this form yet.

¶10 {{c++26}} A template argument cannot be an unparenthesized splice expression: `S<[:r:]>` is ill-formed, while `S<([:r:])>` and `S<[:r:] + 1>` are valid. In a template argument position, `[:r:]` could splice a type, a template or a value; the parentheses force it to be treated as an expression.

</details>
