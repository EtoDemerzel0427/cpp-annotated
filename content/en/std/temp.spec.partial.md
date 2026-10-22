---
title: Partial specialization
summary: "How partial specializations of class templates and variable templates are declared and what restricts them, how the compiler decides whether one matches the arguments and which one to use when several match, and how members of a partial specialization relate to members of the primary template."
updated: 2026-10-19
---

!!! tldr
    - A partial specialization provides an alternative class or variable definition for a subset of arguments. Only class templates and variable templates can be partially specialized; function templates use overloading instead, and alias templates can't be specialized.
    - A partial specialization must be reachable before every instantiation that would use it; otherwise the program is ill-formed, no diagnostic required.
    - A partial specialization matches if its parameters can be deduced from the actual arguments and satisfy its constraints. With no match the primary template is used, with one match that one, and with several the most specialized; if none is most specialized, it's an ambiguity error.
    - To compare two partial specializations, rewrite them as single-parameter function templates and apply the partial ordering rules for function templates.
    - A partial specialization is a complete replacement definition and inherits none of the primary template's members.

## An example

```cpp run ok
template<class T> struct is_ptr       { static constexpr bool value = false; };
template<class T> struct is_ptr<T*>   { static constexpr bool value = true;  };

static_assert(!is_ptr<int>::value);
static_assert(is_ptr<int*>::value);    // uses is_ptr<T*>, T = int
int main() {}
```

The first declaration is the **primary template**: there's no argument list after the template name. The second declaration writes an argument list `<T*>` after the template name, making it a [[g:partial-specialization|**partial specialization**]]: when the argument has the shape "pointer to some type", this definition is used instead of the primary template. Unlike an explicit specialization `template<> struct is_ptr<int>`, a partial specialization still has its own template parameters and covers a whole family of arguments at once.

The standard library uses this everywhere: `std::unique_ptr<T[]>`, `std::is_pointer<T*>`, `std::tuple_size<std::array<T, N>>`. Only class templates and variable templates can be partially specialized ([[temp.decls#2]]). Function templates get the same effect through overloading plus partial ordering ([[temp.func.order]]), and alias templates can't be specialized at all ([[temp.decls#4]]).

## Declaring partial specializations [temp.spec.partial.general]

### Parameters and argument lists (¶3, ¶5)

¶3 In the standard's example, the first declaration is the primary template and the other four are partial specializations of it:

```cpp run ok
template<class T1, class T2, int I> class A             { };   // primary template
template<class T, int I>            class A<T, T*, I>   { };   // #2
template<class T1, class T2, int I> class A<T1*, T2, I> { };   // #3
template<class T>                   class A<int, T*, 5> { };   // #4
template<class T1, class T2, int I> class A<T1, T2*, I> { };   // #5
int main() {}
```

¶5 The **template argument list** of a partial specialization is the *template-argument-list* after the template name, for example `<T, T*, I>` for #2. It must correspond one-to-one with the primary template's parameter list: three positions, a type, a type and an `int` value. The number of the partial specialization's own template parameters is unrelated to the primary template; #4 has only one parameter, `T`.

### The primary template comes first; partial specializations must be reachable (¶1)

¶1 The primary template must be declared before any of its partial specializations. In addition, if an implicit or explicit instantiation would have used a partial specialization, that partial specialization must be reachable there; otherwise the program is {{ifndr}}.

```cpp run ifndr
template<class T> struct Traits { static constexpr int v = 0; };
int use() { return Traits<int*>::v; }   // only the primary template is visible here
template<class T> struct Traits<T*> { static constexpr int v = 1; };
int main() { return use(); }
```

`use()` has already instantiated `Traits<int*>` from the primary template, and a partial specialization appearing later can't take effect retroactively. Clang 23 gives no diagnostic, and the program returns 0. No diagnostic is required because the multi-translation-unit case can't be checked: if one translation unit sees the partial specialization and another doesn't, the same specialization has two different definitions. The safe practice is to put partial specializations in the same header as the primary template.

### Each partial specialization is a distinct template (¶2)

¶2 Two partial specialization declarations declare the same entity if they specialize the same template and have equivalent *template-head*s and template argument lists (see [[temp.over.link]] for the definition of equivalent). Each partial specialization is a distinct template, with its own template parameters and its own members.

### Where they can be declared (¶6)

¶6 A partial specialization may be declared in any scope in which the primary template may be defined. A partial specialization of a member template can be written inside or outside the class:

```cpp run ok
template<class T> struct A {
  struct C {
    template<class T2> struct B { static constexpr int v = 1; };
    template<class T2> struct B<T2**> { static constexpr int v = 2; };  // #1, in the class
  };
};

template<class T> template<class T2>
struct A<T>::C::B<T2*> { static constexpr int v = 3; };                 // #2, outside the class

static_assert(A<short>::C::B<int*>::v == 3);    // only #2 matches
static_assert(A<short>::C::B<int**>::v == 2);   // #1 and #2 both match, #1 is more specialized
int main() {}
```

### Partial specializations don't introduce names (¶7)

¶7 A partial specialization declaration doesn't introduce a new name. When the program uses the name of the primary template, all reachable partial specializations are considered. Note 1 points out a consequence: a using-declaration referring to a class template doesn't restrict which partial specializations can be found through it, even partial specializations declared after the using-declaration.

```cpp run ok
namespace N {
  template<class T1, class T2> class A { public: static constexpr int v = 0; };
}
using N::A;                                  // refers to the primary template

namespace N {
  template<class T> class A<T, T*> { public: static constexpr int v = 1; };
}

static_assert(A<int, int*>::v == 1);         // the later partial specialization is still used
int main() {}
```

Function overloads don't work this way: a using-declaration only brings in the overloads visible at that point ([[namespace.udecl]]). A partial specialization isn't an independent name; it belongs to the primary template and is always found along with it.

### Constrained partial specializations (¶4) {{c++20}}

¶4 A partial specialization can be constrained ([[temp.constr]]):

```cpp run ok
template<typename T> concept C = true;

template<typename T> struct X { static constexpr int v = 0; };
template<typename T> struct X<T*> { static constexpr int v = 1; };   // #1
template<C T> struct X<T> { static constexpr int v = 2; };           // #2

static_assert(X<int>::v == 2);
static_assert(X<int*>::v == 1);
int main() {}
```

Both partial specializations are more specialized than the primary template, but for different reasons. #1 has a more specific shape: every argument `X<T*>` can match, the primary template can match too, but not the other way round. The argument list `<T>` of #2 is identical to the primary template's; it is more specialized only because it is more constrained ([[temp.constr.order]]).

`X<int*>` matches both #1 and #2, and #1 is chosen. By the partial ordering method described below, #1 is more specialized than #2 in shape; that step already decides the winner, and constraints don't take part in the comparison at all. Constraints only decide when the shapes are the same and deduction succeeds in both directions ([[temp.func.order#8]]).

### Restrictions on a partial specialization's argument list (¶8–¶9)

¶8 Two terms first. A constant template argument that is just the name of a constant template parameter, like `I` in #2, is [[g:non-specialized-argument|**non-specialized**]]; all other constant template arguments are **specialized**, like the `5` in #4.

¶9 The argument list of a partial specialization is subject to four restrictions.

¶9.1 If a specialized constant argument corresponds to a primary template parameter whose type depends on a parameter of the partial specialization, the program is ill-formed:

```cpp error
template<class T, T t> struct C { };
template<class T> struct C<T, 1>;          // error: the type T of parameter t isn't determined yet

template<int X, int (*array_ptr)[X]> class A { };
int array[5];
template<int X> class A<X, &array> { };    // error: the type of array_ptr depends on X
```

Matching `C<T, 1>` requires comparing `1` with the actual second argument, whose type is `T`. Until `T` is deduced, it's unknown what type `1` should be converted to before the comparison; `char(1)` in `C<char, 1>` and `long(1)` in `C<long, 1>` aren't the same value. The standard simply forbids this. A non-specialized argument is just a parameter name and doesn't have this problem.

¶9.2 A partial specialization must be more specialized than the primary template; how this is decided is covered under partial ordering below. The most common violation is writing a partial specialization identical to the primary template:

```cpp error
template<class T> struct P { };
template<class T> struct P<T> { };   // error: specializes nothing
```

The constrained `template<C T> struct X<T>` doesn't violate this rule, because its constraints make it more specialized.

¶9.3 The template parameter list of a partial specialization can't contain default template arguments. A footnote explains that there is no situation in which they would be used: the parameters of a partial specialization are always deduced, never given explicitly.

¶9.4 An argument can't contain an unexpanded pack; if an argument is a pack expansion, it must be the last argument.

```cpp error
template<class T, class U> struct Q { };
template<class T, class U = int> struct Q<T*, U> { };   // error: ¶9.3, default argument

template<class... Ts> struct R { };
template<class... Ts> struct R<Ts> { };                 // error: ¶9.4, unexpanded pack
template<class... Ts, class T> struct R<Ts..., T> { };  // error: ¶9.4, pack expansion not last
```

For the last line, Clang 23 reports that the parameters can't be deduced and the partial specialization will never be used (`-Wunusable-partial-specialization`, an error by default). A different angle, the same conclusion.

### Exemption from access checking (¶10)

¶10 Non-dependent names in the template arguments of a partial specialization are not subject to the usual access checking, so private types that are normally inaccessible can be used:

```cpp run ok
class Outer { struct Priv { }; };    // Priv is private

template<class T> struct Trait { static constexpr int v = 0; };
template<class T> struct Trait<T(*)(Outer::Priv)> { static constexpr int v = 1; };  // OK
template<> struct Trait<Outer::Priv> { static constexpr int v = 2; };              // OK
int main() {}
```

Explicit specializations and explicit instantiations have the same exemption ([[temp.spec.general#6]]). Dependent names can't be checked when the partial specialization is declared; they are checked when arguments are substituted into the partial specialization.

## Which definition is used [temp.spec.partial.match]

### Three outcomes (¶1)

¶1 When a template specialization needs to be instantiated, the compiler has to decide whether the primary template or some partial specialization generates it. It does so by matching the specialization's arguments against the argument list of each partial specialization:

- ¶1.1 If exactly one partial specialization matches, it is used.
- ¶1.2 If more than one matches, the partial ordering rules are used to find the one that is more specialized than all the others; if there is none, the program is ill-formed.
- ¶1.3 If none matches, the primary template is used.

This step happens only when instantiation is needed. Merely naming `A<int*, int>`, for example declaring a pointer `A<int*, int>* p;`, doesn't require choosing a definition.

### Matching is deduction plus constraints (¶2)

¶2 A partial specialization matches a given argument list if and only if its template arguments can be deduced from the actual arguments and the deduced arguments satisfy its constraints, if any. Deduction uses the rules for deducing from a type in [[temp.deduct.type]]: the partial specialization's argument list is P, the actual arguments are A, compared position by position.

```cpp error
template<class T1, class T2, int I> class A             { };    // #1
template<class T, int I>            class A<T, T*, I>   { };    // #2
template<class T1, class T2, int I> class A<T1*, T2, I> { };    // #3
template<class T>                   class A<int, T*, 5> { };    // #4
template<class T1, class T2, int I> class A<T1, T2*, I> { };    // #5

A<int, int, 1>   a1;   // uses #1: no partial specialization matches
A<int, int*, 1>  a2;   // uses #2, T = int, I = 1; #5 also matches, but #2 is more specialized
A<int, char*, 5> a3;   // uses #4, T = char; #5 also matches, but #4 is more specialized
A<int, char*, 1> a4;   // uses #5, T1 = int, T2 = char, I = 1
A<int*, int*, 2> a5;   // error: #3 and #5 both match, neither is more specialized
```

Checking `a2` one by one:

| Partial specialization | P | Deduction | Result |
|---|---|---|---|
| #2 | `<T, T*, I>` | position 1 gives `T = int`; position 2, `T*` against `int*`, also gives `T = int`, consistent; `I = 1` | matches |
| #3 | `<T1*, T2, I>` | position 1, `T1*` against `int`, fails | doesn't match |
| #4 | `<int, T*, 5>` | position 3, `5` is not equal to `1` | doesn't match |
| #5 | `<T1, T2*, I>` | `T1 = int`, `T2 = int`, `I = 1` | matches |

#2 and #5 both match, so they are compared to see which is more specialized. #2 requires the second argument to be exactly a pointer to the first argument, which demands more than #5, so #2 is chosen.

A partial specialization whose constraints aren't satisfied doesn't match:

```cpp run ok
template<typename T> concept C = requires (T t) { t.f(); };

template<typename T> struct S { static constexpr int v = 1; };   // #1
template<C T> struct S<T> { static constexpr int v = 2; };       // #2

struct Arg { void f(); };
static_assert(S<int>::v == 1);   // #2's constraints aren't satisfied, only the primary template is left
static_assert(S<Arg>::v == 2);   // #2 matches and is more specialized than the primary template
int main() {}
```

### Partial specializations whose parameters can't be deduced (¶3)

¶3 If, because of the structure of the parameter list and argument list, the template arguments of a partial specialization can't be deduced at all, the program is ill-formed:

```cpp error
template<int I, int J> struct A { };
template<int I> struct A<I+5, I*2> { };    // error: I only appears in non-deducible positions
template<int I> struct A<I, I> { };        // OK

template<int I, int J, int K> struct B { };
template<int I> struct B<I, I*2, 2> { };   // OK: I deduced from position 1, position 2 only checked
```

An expression containing a template parameter, such as `I+5`, is a non-deduced context ([[temp.deduct.type]]) and is skipped during deduction. If every appearance of `I` is in such a position, it can never be deduced and the partial specialization can never be chosen, so the standard requires an error at the declaration. In `B<I, I*2, 2>`, `I` can be deduced from position 1, and once deduced, position 2 is checked to equal `2*I`.

### Default arguments are filled in before matching (¶4)

¶4 When a specialization of a class template or variable template is written, for example `A<int, int, 1>`, the argument list corresponds to the primary template's parameter list. The partial specialization's arguments are deduced from the primary template's arguments.

So by the time matching happens, the primary template's default template arguments have already been filled in. The `void_t` detection idiom is built on this:

```cpp run ok
#include <type_traits>
template<class T, class = void>          // primary template: the second parameter defaults to void
struct has_type : std::false_type { };

template<class T>
struct has_type<T, std::void_t<typename T::type>> : std::true_type { };

struct Yes { using type = int; };
static_assert(has_type<Yes>::value);
static_assert(!has_type<int>::value);
int main() {}
```

`has_type<Yes>` is first completed to `has_type<Yes, void>`, then matched against the partial specialization. Position 1 deduces `T = Yes`. Position 2 is a non-deduced context; substituting `T` gives `void_t<int>`, which is `void`, consistent with the actual argument, so the match succeeds. For `int`, substituting into `int::type` fails; that is a deduction failure, the partial specialization doesn't match, and the primary template is used. For why substitution fails even though the argument of `void_t` isn't used, see [[temp.alias#3]].

## Choosing among several matches [temp.spec.partial.order]

### Rewriting as function templates (¶1)

¶1 To decide which of two partial specializations is [[g:more-specialized|**more specialized**]], the standard doesn't set up a separate set of rules; it rewrites each as a function template and compares them with the partial ordering of function templates ([[temp.func.order]]):

- ¶1.1 each function template has the same template parameters and constraints as the corresponding partial specialization;
- ¶1.2 each function template has a single function parameter whose type is a specialization of the class template with the partial specialization's argument list as its arguments.

That is, `template<P...> struct X<args>` is rewritten as `template<P...> void f(X<args>)`. Partial ordering of function templates replaces one template's parameters with synthesized unique types or values and checks whether the other template can deduce from them; if only one direction succeeds, the template being deduced in the successful direction is less specialized, and the other is more specialized.

### Examples (¶2)

```cpp run ok
template<int I, int J, class T> struct X { static constexpr int v = 0; };
template<int I, int J> struct X<I, J, int> { static constexpr int v = 1; };   // #1
template<int I>        struct X<I, I, int> { static constexpr int v = 2; };   // #2

// After rewriting:
template<int I0, int J0> void f(X<I0, J0, int>);   // A
template<int I0>         void f(X<I0, I0, int>);   // B

static_assert(X<3, 3, int>::v == 2);   // #1 and #2 both match, #2 is more specialized
static_assert(X<1, 2, int>::v == 1);   // only #1 matches
int main() {}
```

| Direction | Transformed argument | Deduction against the other | Result |
|---|---|---|---|
| B against A | `X<u, u, int>`, u a synthesized value | `X<I0, J0, int>` gives `I0 = u`, `J0 = u` | succeeds |
| A against B | `X<u1, u2, int>`, two different synthesized values | `X<I0, I0, int>` needs `I0` to be both u1 and u2 | fails |

Every argument B accepts, A accepts too, but not the reverse, so B is more specialized, and #2 is more specialized.

`auto` constant parameters work the same way:

```cpp run ok
template<auto v>    struct Y { static constexpr int k = 0; };
template<auto* p>   struct Y<p> { static constexpr int k = 1; };    // #3
template<auto** pp> struct Y<pp> { static constexpr int k = 2; };   // #4

int i; int* ip = &i;
static_assert(Y<&i>::k == 1);    // only #3 matches
static_assert(Y<&ip>::k == 2);   // #3 and #4 both match, #4 is more specialized
static_assert(Y<1>::k == 0);
int main() {}
```

Rewrite them as `template<auto* p0> void g(Y<p0>)` (C) and `template<auto** pp0> void g(Y<pp0>)` (D). In partial ordering, a value synthesized for a constant parameter also has the placeholders in its type replaced by synthesized unique types ([[temp.func.order#3]]). D's synthesized value has type `U**`, which matches C's `auto*`; C's synthesized value has type `V*`, which can't match D's `auto**`. So D is more specialized.

When the shapes are the same, constraints are compared:

```cpp run ok
template<typename T> concept C = requires (T t) { t.f(); };
template<typename T> concept D = C<T> && requires (T t) { t.f(); };

template<typename T> class S { public: static constexpr int v = 0; };
template<C T> class S<T> { public: static constexpr int v = 1; };   // #1
template<D T> class S<T> { public: static constexpr int v = 2; };   // #2

struct Arg { void f(); };
static_assert(S<Arg>::v == 2);
int main() {}
```

After rewriting, deduction between `template<C T> void f(S<T>)` and `template<D T> void f(S<T>)` succeeds in both directions, so constraints are compared: `D` subsumes `C` ([[temp.constr.order]]), so #2 is more constrained and therefore more specialized.

## Members of partial specializations [temp.spec.partial.member]

### Unrelated to the primary template's members (¶1)

¶1 The members of a class template partial specialization are unrelated to the members of the primary template. Members of a partial specialization that are used in a way that requires a definition must be defined for the partial specialization; the definitions of the primary template's members are never used as definitions for members of the partial specialization.

```cpp
template<class T, int I> struct A { void f(); };       // primary template
template<class T, int I> void A<T, I>::f() { }

template<class T> struct A<T, 2> {                     // partial specialization
  void f();
  void g();
  void h();
};
template<class T> void A<T, 2>::g() { }                // member of the partial specialization
template<> void A<char, 2>::h() { }                    // explicit specialization of a member of the partial specialization

int main() {
  A<char, 0> a0;
  A<char, 2> a2;
  a0.f();   // OK: uses the definition of the primary template's member
  a2.g();   // OK: uses the definition of the partial specialization's member
  a2.h();   // OK: uses the explicit specialization's definition
  a2.f();   // error: A<T, 2>::f has no definition; the primary template's f is not used
}
```

The standard's example marks the last line as an error. Strictly, it odr-uses a function with no definition, which is an error with no diagnostic required ([[basic.def.odr]]); Clang 23 compiles it, and the link fails with `A<char, 2>::f()` undefined.

A partial specialization is a complete replacement definition, not a patch on top of the primary template. Every member that's needed has to be declared and defined again. To share the implementation, put the common parts in a base class.

An explicit specialization of a member of a partial specialization is written the same way as an explicit specialization of a member of the primary template, like `h` in the example above.

### Partial specializations of member templates (¶2)

¶2 A member template of a class template can also have partial specializations, and they are likewise member templates of the enclosing class template. When the enclosing class template is instantiated, the declaration of each member template partial specialization is instantiated along with it.

If the member template itself (the primary member template) is explicitly specialized for a given specialization of the enclosing template, then for that enclosing specialization all of the member template's original partial specializations are ignored. Conversely, if only a partial specialization of the member template is explicitly specialized, the primary member template and the other partial specializations still take part in matching.

```cpp run ok
template<class T> struct A {
  template<class T2> struct B { static constexpr int v = 1; };        // #1
  template<class T2> struct B<T2*> { static constexpr int v = 2; };   // #2
};

// Explicitly specialize the primary member template for A<short>:
template<> template<class T2> struct A<short>::B { static constexpr int v = 3; };   // #3

static_assert(A<char>::B<int*>::v == 2);    // uses #2
static_assert(A<short>::B<int*>::v == 3);   // uses #3; #2 has no effect for A<short>
static_assert(A<char>::B<int>::v == 1);     // uses #1
int main() {}
```

#2 was written against #1. For `A<short>`, `B` has been replaced by the entirely new #3, so the original partial specializations no longer make sense.

## Partial specializations of variable templates

The rules on this page apply equally to variable templates ([[temp.decls#2]]):

```cpp run ok
template<class T> constexpr int ptr_depth = 0;
template<class T> constexpr int ptr_depth<T*> = 1 + ptr_depth<T>;
template<class T> constexpr int ptr_depth<T* const> = 1 + ptr_depth<T>;

static_assert(ptr_depth<int> == 0);
static_assert(ptr_depth<int**> == 2);
static_assert(ptr_depth<int* const*> == 2);
int main() {}
```

## Implementation notes

!!! impl
    - For partial specializations that can never be used, as in ¶3 and ¶9.4, Clang gives `-Wunusable-partial-specialization`, an error by default; for violations of ¶9.2, it reports that the partial specialization does not specialize any template argument.
    - Compilers usually can't detect violations of the reachability requirement in ¶1. The consequence is that the same specialization has different definitions in different translation units, which after linking can cause hard-to-explain differences in behavior.

## History

!!! history
    - Class template partial specialization has existed since C++98.
    - C++14 introduced variable templates, which can also be partially specialized.
    - C++17's `auto` constant template parameters made partial specializations like `Y<auto* p>` possible; `std::void_t` entered the standard library, and the detection idiom became popular.
    - C++20 allowed constrained partial specializations, whose argument list may be identical to the primary template's as long as they are more constrained.
    - The current draft renamed non-type template parameters to constant template parameters, and the specialized and non-specialized arguments of ¶8 now use that term too.

## Common misconceptions

!!! pitfall "A partial specialization inherits the primary template's members"
    It doesn't. A partial specialization is a complete replacement definition, and every member used must be defined again ([temp.spec.partial.member] ¶1).

!!! pitfall "A partial specialization can be written after its use"
    It can't. It must be reachable before every instantiation that would use it; otherwise the program is IFNDR, and the compiler probably won't warn you.

!!! pitfall "A partial specialization can have default template arguments"
    Not allowed (¶9.3). Defaults belong on the primary template, which is exactly what the `void_t` idiom does.

!!! pitfall "When two match, the compiler picks the one that looks more specific"
    The compiler compares by strict partial ordering rules. If neither of two partial specializations is more specialized, the program has an ambiguity error; the compiler doesn't pick one by intuition.

## Questions

!!! question "Question 1"
    Which definition does `T<int*, int*>` use below?

    ```cpp
    template<class A, class B> struct T { };          // #0
    template<class A>          struct T<A, A> { };    // #1
    template<class A, class B> struct T<A*, B*> { };  // #2
    ```

<details markdown="1">
<summary>Answer</summary>

It's ambiguous, and the program is ill-formed. #1 (`A = int*`) and #2 (`A = int, B = int`) both match. Rewrite them as `f(T<A, A>)` and `g(T<A*, B*>)` for partial ordering: deducing #2 from #1's synthesized `T<U, U>` fails, since `U` is not a pointer; deducing #1 from #2's synthesized `T<U1*, U2*>` fails, since `A` would have to be both `U1*` and `U2*`. Both directions fail, so neither is more specialized. Adding `template<class A> struct T<A*, A*>` removes the ambiguity, as it is more specialized than both #1 and #2. Clang 23 reports ambiguous partial specializations.
</details>

!!! question "Question 2"
    Why does the `void_t` detection idiom require the primary template's second parameter to default to `void`, and not to some other type such as `int`?

<details markdown="1">
<summary>Answer</summary>

By [temp.spec.partial.match] ¶4, `has_type<X>` is first completed with the primary template's default argument to `has_type<X, default>`, then matched against the partial specialization `<T, void_t<typename T::type>>`. When substitution succeeds, the partial specialization's second argument is always `void`. If the default were `int`, matching would require `void` to equal `int`, which always fails; the partial specialization would never be chosen, and the trait would always be false.
</details>
