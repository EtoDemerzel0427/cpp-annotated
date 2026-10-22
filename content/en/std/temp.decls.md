---
title: Template declarations
summary: "How primary templates are told apart from partial specializations; why default arguments, noexcept, contract specifiers and constraints are instantiated separately and only when needed; how constexpr if and the body of template for take part in instantiation; why alias templates can't be specialized."
updated: 2026-10-19
---

!!! tldr
    - A declaration whose template name is not followed by an argument list is a primary template; one followed by an argument list is a partial specialization, and only class templates and variable templates can be partially specialized.
    - A function's default arguments, `noexcept` specifier, contract specifiers, and its constraints each count as a separate definition: they are instantiated only when used, and errors in them are reported only where they are used.
    - The discarded branch of a constexpr if is not instantiated with the enclosing template, but its non-dependent parts are still checked at the template definition.
    - The body of `template for` is itself a template definition, instantiated once per expansion.
    - Alias templates can't be specialized; to dispatch on the arguments, specialize a class template and forward to it through the alias.

## Primary templates and partial specializations (¶2)

```cpp run ok
template<class T, class U> struct Pair { };          // primary template: argument list <T, U>
template<class T> struct Pair<T, T> { };             // partial specialization: argument list <T, T>
template<class... Ts> struct Tup { };                // primary template: argument list <Ts...>

template<class T> constexpr int rank = 0;            // primary template of a variable template
template<class T> constexpr int rank<T*> = 1 + rank<T>;   // partial specialization of a variable template

static_assert(rank<int**> == 2);
int main() { Pair<int, int> p; (void)p; }
```

¶2 The two kinds of template declaration are told apart by a simple criterion: whether the template name is followed by a *template-argument-list*.

- One without an argument list is a **primary template** ([[g:primary-template|primary template]]). Its template argument list is its own parameters: the nth argument is the nth parameter, and a parameter pack is written as a pack expansion ([[temp.arg#2]]). In the example above, the primary template of `Pair` is equivalent to `Pair<T, U>`.
- One with an argument list is a **partial specialization** of the template ([[temp.spec.partial]]), and what is specialized must be a class template or a variable template.

Viewing the primary template as a specialization with argument list `<T, U>` comes up again and again. Deciding whether a partial specialization is more specialized than the primary template means comparing the partial specialization's argument list against it ([[temp.spec.partial#9.2]]); and a partial specialization's argument list can't be identical to the primary template's, since that would specialize nothing.

Neither function templates nor alias templates can be partially specialized:

```cpp error
template<class T> void f(T);
template<class T> void f<T*>(T*);                    // error: function templates can't be partially specialized
template<class T> using Ptr = T*;
template<class T> using Ptr<T*> = T;                 // error: alias templates can't be specialized (¶4)
```

Function templates don't need partial specialization, because overloading plus partial ordering of function templates ([[temp.func.order]]) already expresses the same thing: just add another overload `template<class T> void f(T*);`. Adding partial specialization on top would give two mechanisms deciding which function gets called at the same time, and since specializations don't take part in overload resolution, the result would be hard to predict. To dispatch on types, overload directly, use constraints or `if constexpr`, or forward to a class template that can be partially specialized.

## Default arguments, noexcept and constraints are instantiated on demand (¶3)

```cpp run ok
struct NoValue { };

template<class T>
struct Box {
    void put(T t, int n = T::value);          // default argument: invalid for T = NoValue
    void swap(Box&) noexcept(T::nothrow);     // noexcept: invalid for T = NoValue
};
template<class T> void Box<T>::put(T, int) { }

int main() {
    Box<NoValue> b;          // OK: the default argument and noexcept are not instantiated
    b.put(NoValue{}, 42);    // OK: the default argument isn't used
}
```

`NoValue` has neither `value` nor `nothrow`, yet this code is well-formed. An error occurs only when the default argument is actually used:

```cpp error
struct NoValue { };
template<class T> struct Box { void put(T, int = T::value) { } };
int main() {
    Box<NoValue> b;
    b.put(NoValue{});        // error: the default argument T::value now has to be instantiated
}
```

¶3 states the underlying rule. The following three things of a templated function F are called the **separately instantiated constructs** of F ([[g:separately-instantiated-construct|separately instantiated construct]]):

- ¶3.1 its default arguments;
- ¶3.2 its *noexcept-specifier*;
- ¶3.3 its *function-contract-specifier*s, i.e. C++26 `pre(...)` and `post(...)` ([[dcl.contract.func]]).

!!! std
    For purposes of name lookup and instantiation, separately instantiated constructs, *type-constraint*s, and *requires-clause*s are considered definitions; each ... is a separate definition which is unrelated to the templated function definition ...

For name lookup and instantiation, these constructs, together with *type-constraint*s and *requires-clause*s, count as definitions. Each is a separate definition, unrelated to the function definition and to each other. Three consequences follow:

1. On-demand instantiation. A default argument is instantiated only when a call uses it, an exception specification only when it is needed ([[temp.inst]], [[except.spec#13]]), and constraints are substituted into only when their satisfaction is checked ([[temp.constr]]).
2. Each has its own point of instantiation ([[temp.point]]), and ADL for dependent names is done from that point.
3. Errors are isolated from each other. An invalid default argument is reported only at calls that omit that argument, and doesn't affect the function itself.

The same applies to function templates; the default argument and the function body are two definitions:

```cpp run ok
template<class T> int def(T, int n = T::size) { return n; }
int main() { return def(1, 0); }   // OK: the second argument is given explicitly, T::size is never instantiated
```

If default arguments counted as part of the function definition, then once the function was instantiated, all its default arguments would have to be instantiated with it, even if every call supplied the arguments explicitly. The standard library depends on the opposite behavior; for example, `noexcept(std::is_nothrow_swappable_v<T>)` on a member function must not be an immediate error when `T` isn't swappable.

### constexpr if and template for

The last two sentences of ¶3 give similar treatment to two kinds of statement.

The substatements of a constexpr if count as definitions for the purpose of instantiation ([[stmt.if]]). So when the enclosing template is instantiated, the discarded branch is not:

```cpp run ok
#include <type_traits>
template<class T>
int size_of(T t) {
    if constexpr (std::is_pointer_v<T>)
        return sizeof(*t);    // discarded for T = int, *t is not instantiated
    else
        return sizeof(t);
}
int main() { int x = 0; return size_of(&x) - size_of(x); }
```

The wording only says "for the purpose of instantiation"; it says nothing about name lookup. So an error in a discarded branch that doesn't depend on template parameters is still diagnosed at the template definition:

```cpp error
template<class T> void f() {
    if constexpr (false) {
        undeclared_name();   // error: non-dependent name, must be found when the template is defined
    }
}
```

In a non-template function, both branches of `if constexpr` are fully checked; the discarded branch merely takes no part in return type deduction, and entities used in it are not odr-used. constexpr if is not the preprocessor's `#if`.

C++26's expansion statement `template for` ([[stmt.expand]]) goes further: its compound statement counts as a template definition for name lookup and instantiation, and it is instantiated once per expansion. So even when the enclosing function is not a template, expressions in the loop body that depend on the expansion variable can have a different type in each iteration:

```cpp run ok
#include <tuple>
#include <cstdio>
int main() {
    auto t = std::tuple{1, 2.5, 'c'};
    template for (auto e : t) {             // C++26; the body must be a compound statement
        std::printf("%zu ", sizeof(e));     // e is int, double, char in turn
    }
}
```

## Alias templates can't be specialized (¶4)

¶4 The grammar of *alias-declaration* doesn't allow a *template-id*; `using Name<Args> = ...` is not a valid declaration, so alias templates can be neither partially nor explicitly specialized. An alias template only does type substitution ([[temp.alias]]) and can't choose different definitions based on its arguments.

To dispatch on the arguments, put the specialization on a class template and let the alias just forward:

```cpp run ok
#include <type_traits>
template<class T> struct remove_ptr_impl       { using type = T; };
template<class T> struct remove_ptr_impl<T*>   { using type = T; };   // specialize the class template
template<class T> using remove_ptr = typename remove_ptr_impl<T>::type;   // the alias just forwards

static_assert(std::is_same_v<remove_ptr<int*>, int>);
int main() { }
```

That is why the standard library's `std::xxx_t` aliases are all defined as `typename std::xxx<T>::type`.

## The other subclauses of this section

¶1 says only one thing: a template's template parameters are the list in angle brackets right after the keyword `template`. When a member template is defined outside its class there are several levels of `template<...>`, and each level's parameters belong to the corresponding template ([[temp.mem#1]]).

The other subclauses of 13.7 give the details for each kind of declaration: out-of-class definitions of class templates and their members [[temp.class]], member templates [[temp.mem]], variadic templates [[temp.variadic]], friends [[temp.friend]], partial specializations [[temp.spec.partial]], function templates [[temp.fct]], alias templates [[temp.alias]], concepts [[temp.concept]].

## Common misconceptions

!!! pitfall "`template<> void f<int*>(int*)` is a partial specialization"
    It is an explicit specialization, i.e. a full specialization, and it doesn't introduce a new template. A partial specialization's argument list still contains template parameters, and only class templates and variable templates have them.

!!! pitfall "Instantiating `Box<X>` instantiates all its members"
    Implicit instantiation of a class template instantiates only the declarations of its members ([[temp.inst]]), and not even the default arguments, `noexcept` or constraints in those declarations. Member function definitions, default arguments and exception specifications are all instantiated on demand.

!!! pitfall "The false branch of constexpr if isn't compiled"
    It isn't instantiated, but it is still parsed when the template is defined, and its non-dependent parts are checked as usual.

## Questions

!!! question "Question 1"
    Is the following program well-formed?

    ```cpp
    template<class T> struct S {
        void f() noexcept(sizeof(T) > 4);
    };
    struct Incomplete;
    S<Incomplete> s;
    ```

<details markdown="1">
<summary>Answer</summary>

It is well-formed. Instantiating `S<Incomplete>` instantiates only the declaration of `f`, and the *noexcept-specifier* is a separately instantiated construct (¶3.2), instantiated only when the exception specification is needed (calling `f`, taking its address, defining it, and so on, [[except.spec#13]]). It is never needed here, so `sizeof(Incomplete)` is never evaluated. If `s.f();` were written later, the `noexcept` would be instantiated at that point and an error reported.
</details>

!!! question "Question 2"
    The standard says each separately instantiated construct is unrelated to the other separately instantiated constructs. Give an example where this makes an observable difference.

<details markdown="1">
<summary>Answer</summary>

Suppose a function template has two default arguments, `int a = T::x, int b = T::y`. If a call supplies `a` and omits `b`, only `T::y` is instantiated, and `T::x` causes no error even if it is invalid. If all default arguments counted as one unit, using one of them would require instantiating them all.

Another difference is the point of instantiation: each default argument's point of instantiation can differ from the function definition's, and overloads declared in between may be found by ADL. If that changes the meaning, the program is ill-formed, no diagnostic required ([[temp.point]]).
</details>
