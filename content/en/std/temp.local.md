---
title: Locally declared names
summary: "Inside a class template, when the class name X means the current specialization X<T> and when it means the template itself; why a template parameter's name can't be redeclared; and why a member of a non-dependent base class hides a template parameter with the same name."
updated: 2026-10-19
---

!!! tldr
    - Inside a class template `X`, a plain `X` means the current specialization `X<T>`; followed by an argument list, as a template template argument, or in a friend class template declaration, `X` means the template itself.
    - So `X(args)` inside a class template doesn't perform class template argument deduction; to deduce, write `::X(args)`.
    - A class name inherited from a dependent base class can't be found at the definition; in a mem-initializer write `D::Base(...)` or `Base<T>(...)`.
    - Within its scope, a template parameter's name can't be declared again as something else, except by a friend function declaration.
    - Unqualified lookup searches class scope (including non-dependent bases) before template parameters, so a member with the same name in a non-dependent base hides the template parameter, with no diagnostic at all.

## What X means inside a class template (¶1)

Every class injects its own name into its own scope; this name is the [[g:injected-class-name|**injected-class-name**]] ([[class.pre#2]]). So writing the class name in the class definition finds this member, not a declaration in an enclosing scope.

¶1 Class templates have an injected-class-name too, and it has two uses:

| Form | Meaning |
|---|---|
| followed by a template argument list: `X<int>` | template name, refers to the class template itself |
| as the argument for a type template template parameter: `TT<X>` | template name |
| the final identifier in the elaborated type specifier of a friend class template declaration: `template<class> friend class X;` | template name |
| all other cases | type name, equivalent to `X` followed by the template-head's argument list, i.e. `X<T>`; a parameter pack gives `X<Ts...>` |

```cpp run ok
#include <type_traits>
template<template<class> class> struct TT { };

template<class T> struct X {
    X* self;            // type name: X<T>*
    X<int>* other;      // template name with argument list: X<int>*
    TT<X> tt;           // template template argument: refers to template X itself
};

template<class... Ts> struct P { using self = P; };    // P means P<Ts...>
static_assert(std::is_same_v<P<int, char>::self, P<int, char>>);
int main() { }
```

The design reflects the fact that inside a class template you almost always mean the current specialization: the copy constructor `X(const X&)`, the `X&` returned by assignment, a list node's `X* next`. Writing `X<T>` everywhere would get verbose with many template parameters. At the same time you need to be able to name other specializations (`X<int>`) and the template itself (passed to a template template parameter), so the two uses are distinguished by context.

### The injected-class-name defeats CTAD

Inside a class template, the `X` in `X(args)` is the type name `X<T>`, and no class template argument deduction is done (CTAD, [[over.match.class.deduct]]). To deduce, bypass the injected-class-name with `::X` (¶5):

```cpp run ok
#include <type_traits>
template<class T> struct X {
    T v;
    X(T t) : v(t) { }
    auto a() { return X(1.5); }      // X<T>: 1.5 is converted to T
    auto b() { return ::X(1.5); }    // template name: deduces X<double>
};
static_assert(std::is_same_v<decltype(X<int>(0).a()), X<int>>);
static_assert(std::is_same_v<decltype(X<int>(0).b()), X<double>>);
int main() { }
```

In `X<int>::a()`, `X(1.5)` converts `1.5` to the `int` value `1`. Clang 23 gives a `-Wliteral-conversion` warning here, but this style can easily hide bugs without any warning.

### The name from the enclosing scope always means the template (¶5)

¶5 When the template's normal name is used, that is, the name from the enclosing scope rather than the injected-class-name, it always refers to the class template itself:

```cpp error
template<class T> class X {
    X* p;           // X<T>
    X<T>* p2;
    X<int>* p3;
    ::X* p4;        // error: missing template argument list
};
```

`::X` skips the class scope and finds the template `X` in the global scope. A bare template name where a type is required is valid only where CTAD applies (a variable declaration with an initializer, a function-style cast, and so on); a data member isn't one of those places.

## Injected-class-names of specializations (¶2)

¶2 Explicit specializations and partial specializations of a class template also have injected-class-names. Used as a type name, it is equivalent to the template name followed by that specialization's own template arguments:

```cpp run ok
template<template<class> class T> class A { };
template<class T> class Y;
template<> class Y<int> {
    Y* p;                                 // Y<int>
    Y<char>* q;                           // Y<char>
    A<Y>* a;                              // A<::Y>: refers to the template itself
    class B {
        template<class> friend class Y;   // ::Y
    };
};

template<class T> class Y<T*> {
    Y* p;                                 // Y<T*>, not Y<T>
};
int main() { }
```

In the partial specialization `Y<T*>`, `Y` means `Y<T*>`, the partial specialization's argument list, not `Y<T>` formed from its parameters.

## Inherited injected-class-names (¶3)

¶3 The injected-class-name of a class template or a specialization of one can be used as either a template name or a type name wherever it is named. An injected-class-name is a member of the class, so it is inherited. A derived class can get the base class's injected-class-name through a qualified name, and both uses still work:

```cpp run ok
template <class T> struct Base {
    Base* p;
};

template <class T> struct Derived : public Base<T> {
    typename Derived::Base* p;    // Derived::Base<T>: used as a type name
};

template<class T, template<class> class U = T::template Base> struct Third { };
Third<Derived<int>> t;            // OK: injected-class-name used as a template

int main() { }
```

`Derived::Base` needs `typename`: `Base` comes from the dependent base `Base<T>`, can't be found at the definition, and by [[temp.dep.type#5]] is a dependent name.

!!! impl "Clang differs from the standard's Example 2"
    Example 2 in the standard writes `template<class> class U = T::Base`, without the `template` keyword, and marks it OK. Clang 23 rejects this, reporting that the default argument of a template template parameter must be a class template; it accepts `T::template Base`. The latter form (`template` not followed by an argument list) is deprecated ([[depr.template.template]]) but still well-formed.

### The class name from a dependent base can't be found at the definition

¶3 explains a common compile error:

<div class="compare" markdown="1">

```cpp error
template<class T>
struct Base { Base(int) { } };
template<class T>
struct D : Base<T> {
  D() : Base(0) { }  // error
};
D<int> d;
```

```cpp run ok
template<class T>
struct Base { Base(int) { } };
template<class T>
struct D : Base<T> {
  D() : D::Base(0) { }  // OK
};
D<int> d;
int main() { }
```

</div>

On the left, the unqualified `Base` is looked up at the definition. It isn't in `D`'s own scope, dependent bases aren't searched ([[class.member.lookup#4]]), so lookup continues outward and finds the class template `::Base` in the global scope. A template name without an argument list isn't the name of a base class, and Clang reports that it is neither a data member nor a base class.

On the right, `D::Base` is a dependent qualified name; at instantiation it finds the injected-class-name of the base `Base<int>` in `D<int>`. `Base<T>(0)` also works; `D::Base` is handier when the base class template's name is long.

## Injected-class-names from several bases (¶4)

¶4 When lookup finds injected-class-names in several base classes, the result can be ambiguous ([[class.member.lookup]]). But if all the injected-class-names found are specializations of the same class template and the name is used as a template name, it refers to the class template itself and isn't ambiguous:

<div class="compare" markdown="1">

```cpp error
template <class T> struct Base { };
template <class T>
struct D2 : Base<int>, Base<char> {
  typename D2::Base b;
  // error: Base<int> or Base<char>?
};
D2<int> d2;
```

```cpp run ok
template <class T> struct Base { };
template <class T>
struct D2 : Base<int>, Base<char> {
  typename D2::Base<double> d;
  // OK: refers to the template Base
};
D2<int> d2;
int main() { }
```

</div>

As a type name, `Base` is `Base<int>` in one base and `Base<char>` in the other, which really is ambiguous. As a template name, both refer to the same template, and the ambiguity is only apparent. Here `Base` is a member of non-dependent bases and is found to be a template at the definition, so no `template` is needed before `<`.

## Template parameters can't be redeclared (¶6)

¶6 The name of a template parameter shall not be bound to any following declaration whose locus (the point where the name starts to take effect, see [[basic.scope.pdecl]]) is contained by the scope to which the template parameter belongs.

```cpp error
template<class T, int i> class Y {
    int T;                    // error: template parameter hidden
    void f() {
        char T;               // error: template parameter hidden
    }
    friend void T();          // OK: a friend declaration doesn't bind the name here
};

template<class X> class X;    // error: hidden by a template parameter
```

With this rule, `T` inside a template always means that template parameter and never turns into something else after some line. It covers a lot of ground:

```cpp error
template<class T> struct S {
    template<class T> void f();      // error: inner template parameter has the same name as the outer one
};
template<class T> void g(int T);     // error: function parameter has the same name as a template parameter
template<class T> struct S2 { void h(); };
template<class T> void S2<T>::h() {
    using T = int;                   // error: the body of an out-of-class member definition is in scope too
}
```

`friend void T();` is fine because a friend function declaration doesn't bind the name in the class scope ([[class.friend]], [[basic.scope.scope]]); its target scope is the innermost enclosing namespace, which isn't within the template parameter's scope.

In `template<class X> class X;`, the locus of the class template name `X` is after the template-head, inside the scope of the template parameter `X`, so it is prohibited too.

!!! note "Difference from the pre-C++23 wording"
    C++20 and earlier said "a template-parameter shall not be redeclared within its scope (including nested scopes)". [[P1787R6]] rewrote it in terms of binding and loci; the effect is essentially the same, but it directly explains why friend declarations aren't affected.

## Lookup finds class members before template parameters (¶7)

!!! pitfall "Members of a non-dependent base hide template parameters"
    ```cpp run ok
    #include <type_traits>
    struct NB { using U = int; };
    template<class U> struct E : NB {
        U y;            // NB::U (int), not the template parameter U
    };
    static_assert(std::is_same_v<decltype(E<double>::y), int>);
    int main() { }
    ```
    The type of `E<double>::y` is `int`. ¶6 only forbids declaring an entity with the same name within the template parameter's scope; `NB::U` is declared in `NB` and isn't restricted, and the lookup order finds it first. The compiler gives no diagnostic, so be careful when giving template parameters common names like `value_type` or `size_type`.

    Dependent base classes don't cause this problem, because they aren't searched at the definition ([[temp.dep.type#3]]). In `template<class value_type> struct D : Base<value_type> { value_type x; };`, `value_type` is always the template parameter.

¶7 For unqualified lookup, the template parameter scope of a template declaration is considered immediately after the outermost scope associated with the template being declared, even if the template parameter list isn't actually outside that scope (as for an out-of-class member definition).

Note 1 points out the most important consequence: the scope of a class template, including its non-dependent base classes, is searched before the template parameter scope. That's how the pitfall above arises. The standard's Example 6 shows three cases in out-of-class member definitions:

```cpp run ok
struct B { };
namespace N {
    typedef void V;
    template<class T> struct A : B {
        typedef void C;
        void f();
        template<class U> void g(U);
    };
}

template<class V> void N::A<V>::f() {   // N::V not considered here
    V v{};                              // V is the template parameter, not N::V
    (void)v;
}

template<class B> template<class C> void N::A<B>::g(C) {
    B b;                                // B is the base class ::B, not the template parameter
    C c;                                // C is the template parameter, not A::C
    static_assert(__is_same(B, ::B));
    (void)b; (void)c;
}

template void N::A<int>::f();
template void N::A<int>::g(int);
int main() { }
```

- `V` in `f`: class `A` has no `V`; next comes the template parameter scope, which finds the parameter `V`. Namespace `N`'s `typedef void V` comes after the template parameters and is hidden.
- `B` in `g`: the outer template-head declares a member of the class template `A`, so its outermost associated scope is class `A`. Class `A` is searched first, and the injected-class-name `B` is found in the non-dependent base `::B`, hiding the template parameter `B`.
- `C` in `g`: the inner template-head declares the member template `g`, whose outermost associated scope is `g`'s function parameter scope. The template parameter `C` comes right after it, before class `A`, so `C` means the template parameter, not `A::C`.

Why this arrangement? It makes an out-of-class member definition mean the same as it would inside the class. When a member function is written inside the class, the class scope is naturally closer than the enclosing template-head; once it's moved outside, ¶7 places the template parameter scope after the class scope to simulate the same nesting. The pitfall above is the price.

!!! history "History"
    - C++98 already had injected-class-names, the ban on redeclaring template parameters, and the lookup order in out-of-class member definitions.
    - That a class template's injected-class-name can be used as a template name was clarified in C++03 by the defect report [[CWG176]].
    - After C++17 introduced CTAD, the injected-class-name being a type name inside the class template meant that `X(args)` doesn't deduce.
    - C++23's [[P1787R6]] rewrote ¶6 and ¶7 in terms of binding, loci and template parameter scopes ([[basic.scope.temp]]). The phrase in ¶7 about the parent scope not containing the template parameter list was written for out-of-class member definitions.

## Questions

!!! question "Question 1"
    ```cpp
    template<class T> struct List {
        struct Node { Node* next; List* owner; };
    };
    ```
    What types do `Node*` and `List*` in `Node` refer to?

<details markdown="1">
<summary>Answer</summary>

`Node` is the injected-class-name of the nested class and refers to `List<T>::Node`. `List` is the injected-class-name of the enclosing class template; members of the enclosing class can still be found inside the nested class. Used here as a type name, it refers to `List<T>`. Both are the current instantiation ([[temp.dep.type#1]]).
</details>

!!! question "Question 2"
    ```cpp
    struct Base { using T = long; };
    template<class T> struct S : Base {
        T a;
        void f(T b);
    };
    ```
    What are the types of `a` and `b`? What if the base is replaced by `template<class> struct Base2 { using T = long; };`, written as `S : Base2<T>`?

<details markdown="1">
<summary>Answer</summary>

In the first case, the class scope of `S` (including the non-dependent base `Base`) is searched before the template parameter scope, `T` finds `Base::T`, and both `a` and `b` are `long`, regardless of the template argument. ¶6 doesn't apply, because `Base::T` isn't declared within the template parameter's scope.

In the second case, `Base2<T>` is a dependent base, isn't searched at the definition, and `T` is the template parameter. The two versions differ only in whether the base is dependent, yet their meanings are completely different.
</details>

## Summary

| Rule | Paragraph | Key point |
|---|---|---|
| Two uses of the injected-class-name | ¶1 | template name with an argument list, as a template template argument, or in a friend class template; otherwise `X<T...>` |
| Injected-class-names of specializations | ¶2 | as a type name, equals the specialization's own arguments |
| Inherited injected-class-names | ¶3 | both uses still work when named through `Derived::Base` |
| Injected-class-names from several bases | ¶4 | not ambiguous when used as a template name |
| The name from the enclosing scope | ¶5 | `::X` is always the template itself and can trigger CTAD |
| Template parameters can't be redeclared | ¶6 | not by members, local variables, inner template parameters, or a class template of the same name; friend functions are fine |
| Lookup order | ¶7 | class scope (including non-dependent bases) before the template parameter scope |
