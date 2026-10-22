---
title: Deprecated core language features (D.2–D.9)
summary: 'The 8 core language deprecations in Annex D: implicitly defined copy operations, [=] implicitly capturing this, several uses of volatile, out-of-class redeclaration of static constexpr members, whitespace in operator "" _x, a missing comma before an ellipsis, a redundant template prefix, and declarations that expose TU-local entities; for each, the motivation, the fix, and Clang 23's warning.'
updated: 2026-10-19
---

!!! tldr
    - When a class has a user-declared destructor or copy operation, the copy operations the compiler generates implicitly are deprecated and may become deleted in the future. This is the standardized form of the rule of three.
    - `[=]` implicitly capturing `this` is deprecated: `[=]` looks like capture by value, but what is captured is a pointer. Write `[=, this]` or `[=, *this]`.
    - `++`/`--` on `volatile` objects, using the result of an assignment to `volatile`, and `volatile` parameters, return types and structured bindings are all deprecated; they either suggest atomicity that doesn't exist or mean nothing at all.
    - The rest are syntactic cleanups: redeclaring a `static constexpr` member outside the class, whitespace in `operator "" _x`, the missing comma in `void f(int...)`, and a `template` prefix with no argument list after it.
    - Clang gives no warning at all for D.2 and D.9; D.6 and D.7 need `-Wextra` or `-Wdeprecated` to produce warnings.

Most of these rules are written in the main text, which says "is deprecated" at the relevant spot and points here; the Annex D side gives examples and the reasons for keeping them. Whether something is deprecated and what deprecation means is covered in [[depr]]. The warnings below are all as observed with Clang 23.1.3 in our tests.

## Implicitly defined copy functions {#depr.impldec}

```cpp
struct S {
  int* p;
  ~S() { delete p; }   // user-provided destructor
};
void f() {
  S a{new int};
  S b = a;   // deprecated: implicit copy constructor
}            // b.p is the same as a.p, so it's deleted twice on destruction
```

¶1 The implicit definition of a copy constructor as defaulted is deprecated if the class has a user-declared copy assignment operator or a user-declared destructor; the implicit definition of a copy assignment operator as defaulted is deprecated if the class has a user-declared copy constructor or a user-declared destructor. The standard notes that a future revision may make these implicit definitions deleted ([[dcl.fct.def.delete]]).

This is the rule of three: a class that needs a custom destructor or one of the copy operations is almost certainly managing some resource, and the memberwise copy the compiler generates is very likely wrong. When C++11 introduced move semantics, it specified that a class with a user-declared copy operation or destructor no longer gets implicitly declared move operations; the copy operations are still generated implicitly for compatibility, but are listed as deprecated.

Clang doesn't warn by default. `-Wextra` turns on only the copy-operation half (`-Wdeprecated-copy-with-user-provided-copy`); the destructor half needs `-Wdeprecated`: a user-provided destructor corresponds to `-Wdeprecated-copy-with-user-provided-dtor`, and one that is merely user-declared, like `~S() = default;`, to `-Wdeprecated-copy-with-dtor`.

When you need memberwise copying, write `S(const S&) = default;` and `S& operator=(const S&) = default;` explicitly. For classes that manage resources, a better approach is to use members like `std::unique_ptr` so that the class needs no custom destructor at all (the rule of zero).

## Implicit capture of `*this` by reference {#depr.capture.this}

```cpp ok
struct X {
  int x;
  void foo(int n) {
    auto f = [=]() { x = n; };        // deprecated
    auto g = [=, this]() { x = n; };  // recommended
    f(); g();
  }
};
```

¶1 For compatibility with prior revisions, a lambda expression with capture default `=` may implicitly capture `*this` by reference ([[expr.prim.lambda.capture]]). This implicit capture is deprecated.

`[=]` literally means capture by value, so readers assume `x` has been copied. In fact `x` is `this->x`, what is captured is the `this` pointer, and `x = n` modifies the original object. If the lambda outlives the object, say because it is stored as a callback or handed to another thread, it accesses through a dangling pointer. C++20 requires this to be spelled out: `[=, this]` captures the object by reference, `[=, *this]` copies the whole object.

Clang gives a `-Wdeprecated-this-capture` warning by default in C++20 and later. `[=, this]` is ill-formed in C++17; Clang accepts it as an extension with a `-Wc++20-extensions` warning. When you need to be compatible with both C++17 and C++20, write an explicit list with no capture default, such as `[this, n]`.

## Several uses of `volatile` {#depr.volatile.type}

The legitimate uses of `volatile`, such as memory that maps hardware registers, `sig_atomic_t` variables shared with signal handlers, and local variables used across `setjmp`, need only one semantic: every access really reads or writes memory. C++20 deprecated several forms that have nothing to do with this or are easily misunderstood.

```cpp
volatile int velociraptor;
++velociraptor;   // deprecated
```

¶1 Prefix and postfix `++` and `--` on `volatile`-qualified arithmetic and pointer types are deprecated ([[expr.post.incr]], [[expr.pre.incr]]). `++v` is really three steps, read, add one, write; it is neither an atomic operation nor a single access, and writing it as `++` invites the mistaken belief that it is.

```cpp
int neck, tail;
volatile int brachiosaur;
brachiosaur = neck;          // OK
tail = brachiosaur;          // OK
tail = brachiosaur = neck;   // deprecated
brachiosaur += neck;         // OK
```

¶2 Certain assignments where the left operand is a `volatile`-qualified non-class type are deprecated. The exact rule is in [[expr.assign#5]]: it is deprecated when the assignment expression is neither a [[g:discarded-value-expression]] nor an unevaluated operand, that is, when its result is used. In `tail = brachiosaur = neck`, different people expect different things: whether `tail`'s value comes from `neck` or from reading `brachiosaur` again.

Compound assignment has gone back and forth. C++20 deprecated all compound assignments to `volatile` lvalues; C++23 undid the deprecation for the bitwise compound assignments, because embedded code uses `|=` and `&=` heavily to manipulate register bits. The current draft only looks at whether the result is used, so `brachiosaur += neck;` as a standalone statement isn't deprecated, while `int x = (brachiosaur += 1);` is. Clang gives no warning for the latter.

```cpp
volatile struct amber jurassic();                              // deprecated
void trex(volatile short left_arm, volatile short right_arm);  // deprecated
void fly(volatile struct pterosaur* pteranodon);               // OK
```

¶3 Function types with `volatile`-qualified parameter or return types are deprecated ([[dcl.fct]]). Parameters and return values passed by value are copies, so `volatile` means nothing to the caller, and top-level cv-qualifiers on parameters aren't even part of the function type. Parameters that are pointers to `volatile` aren't affected.

```cpp
struct linhenykus { short forelimb; };
void park(linhenykus alvarezsauroid) {
  volatile auto [what_is_this] = alvarezsauroid;   // deprecated
}
```

¶4 Structured bindings of a `volatile`-qualified type are deprecated ([[dcl.struct.bind]]). The `volatile` qualifies the hidden object behind the bindings, while the names a structured binding introduces are just aliases for its members or elements, and through the tuple protocol the semantics become unclear.

For the forms above, Clang gives a `-Wdeprecated-volatile` warning by default in C++20 and later, and no warning under C++17. The fixes: write `++v` as `v = v + 1`, making it clearly one read and one write; split chained assignments into two statements; remove `volatile` from parameter and return types.

## Redeclaring `static constexpr` data members {#depr.static.constexpr}

```cpp ok
struct A {
  static constexpr int n = 5;   // definition (only a declaration in C++14)
};
constexpr int A::n;             // redundant declaration (a definition in C++14)
```

¶1 For compatibility with prior revisions, a `constexpr` static data member may be redundantly redeclared outside the class with no initializer ([[basic.def]], [[class.static.data]]). This usage is deprecated.

In C++14 the in-class line is only a declaration, and once `A::n` is odr-used, for example bound to a `const int&`, an out-of-class definition must be written once in some source file, or linking fails. C++17 made `constexpr` static data members implicitly inline variables ([[dcl.inline]]), so the in-class line is itself the definition, and the out-of-class line became redundant.

Clang gives a `-Wdeprecated-redundant-constexpr-static-def` warning in C++17 and later when `-Wdeprecated` is added. Just delete the out-of-class line; if you still need to support C++14, wrap it in `#if __cplusplus < 201703L`.

## Whitespace in literal operator names {#depr.lit}

```cpp ok
long double operator"" _km(long double);  // deprecated
long double operator""_m(long double);    // OK
```

¶1 A literal operator name of the form `operator` *unevaluated-string* *identifier* is deprecated ([[over.literal]]), that is, the form with whitespace between `""` and the suffix. The recommended form is `operator""_m`, where `""_m` is a single token and the suffix is part of that token.

The problem lies in the reserved-name rules. With whitespace, `_km` is a separate identifier subject to the reservation rules of [[lex.name]]: identifiers beginning with an underscore followed by an uppercase letter are reserved to the implementation, so a user writing `operator "" _KM` breaks the rule. Without whitespace, the suffix is part of a token and isn't subject to that rule. The two forms ought to be equivalent, yet one space makes different rules apply, so the form with whitespace was deprecated.

Clang gives a `-Wdeprecated-literal-operator` warning by default, from `-std=c++11` on. The standard library's own suffixes, such as `operator""s` and `operator""ms`, have always used the form without whitespace.

## Missing comma before an ellipsis {#depr.ellipsis.comma}

```cpp
void f(int...);      // deprecated: equivalent to void f(int, ...)
void g(auto...);     // OK: declares a function parameter pack
void h(auto......);  // deprecated: a parameter pack followed by a C-style ellipsis
```

A parameter-declaration-clause of the form *parameter-declaration-list* `...`, that is, with no comma before the ellipsis, is deprecated ([[dcl.fct]]). {{c++26}}

`void f(int...)` is something C++ has always allowed, meaning C-style variadic arguments. But function parameter packs also use `...`: in `void g(T...)` where `T` is a template parameter pack, it declares a parameter pack. The two are distinguished only by whether the type is a pack, which is easy to confuse, and `auto......` stacks both meanings together. Once a comma is required before a C-style ellipsis, a `...` right after a type means only a parameter pack. C has always required this comma.

In C++26 mode Clang gives a `-Wdeprecated-missing-comma-variadic-parameter` warning by default for `f` and `h`; under C++20 it gives only `-Wambiguous-ellipsis`, for `h`. The fix is to add the comma: `void f(int, ...)`, `void h(auto..., ...)`.

## Redundant `template` before a qualified name {#depr.template.template}

```cpp ok
template<template<class> class TT> struct W {};
namespace N { template<class T> struct V {}; }
W<N::template V> w;   // deprecated
W<N::V> w2;           // OK
```

¶1 Writing the `template` keyword before a qualified name of a class template or alias template without a following template argument list is deprecated ([[temp.names]]).

The `template` disambiguator's job is to tell the compiler, in a dependent qualified name, that the following `<` begins a template argument list, as in `T::template apply<int>`. When a template itself is passed as a template template argument, there is no `<` after it at all, so the keyword disambiguates nothing. [[temp.names#11]] specifies that a name prefixed by `template` must either be followed by a template argument list or refer to a class template or alias template, and the latter case is deprecated.

This deprecation makes no distinction between dependent and non-dependent names. The example in [[temp.names]] explicitly includes dependent names:

```cpp ok
template <class T> struct B {
  template <class T2> struct C { };
};
// deprecated: T::C is assumed to name a class template
template <class T,
          template <class X> class TT = T::template C>
struct D { };
D<B<int>> db;
```

Clang gives no diagnostic at all for either example. Conversely, if the `template` is removed in the dependent case, writing `TT = T::C`, Clang reports the error `default template argument for a template template parameter must be a class template`. So for non-dependent names, just delete the redundant `template`; for a dependent name used as a template template argument, the deprecated form is currently the only one that works on Clang.

## Declarations that expose TU-local entities {#depr.local}

```cpp
namespace {
  struct A {
    void f() {}
  };
}
A h();                        // deprecated: h doesn't have internal linkage
inline void g() { A().f(); }  // deprecated: g is an inline function, also without internal linkage
```

The `A` in the unnamed namespace is a [[g:tu-local]] entity: the `A` in each translation unit is a different type, and other translation units can't name it. A declaration that names a TU-local entity in a part that other translation units will see is called an [[g:exposure]] (see [[basic.link]]). The body of a non-inline function isn't such a part; the body of an inline function is, because its definition has to appear in every translation unit that uses it.

¶1 A declaration of a non-TU-local entity that is an exposure is deprecated. Note 1 points out that such a declaration in an importable module unit is ill-formed.

`h` has external linkage, so in principle other translation units could declare and call it, but its return type `A` can't even be written in another translation unit. `g` is more subtle: the definition of an inline function must be the same in every translation unit, but the `A`s of different translation units are different entities, so the copies of `g`'s definition actually refer to different types, violating the ODR. In modules, such declarations are simply ill-formed; in the traditional header model this kind of code is too widespread, so it is deprecated first.

Clang gives no diagnostic for it at all under `-Wall -Wextra -Wdeprecated`. The fix is to move `A` out of the unnamed namespace, or give `h` and `g` internal linkage, for example by declaring them `static` or putting them in the same unnamed namespace.

## Summary

| Subclause | Clang 23 warns by default | Option needed |
|---|---|---|
| D.2 Exposing TU-local entities | No | No corresponding warning |
| D.3 `[=]` capturing `this` | Yes (since C++20) | |
| D.4 `volatile` | Yes (since C++20); no warning when the result of a compound assignment is used | |
| D.5 `int...` | Yes (C++26 mode) | |
| D.6 Implicit copy operations | No | `-Wextra` (copy-operation case), `-Wdeprecated` (destructor case) |
| D.7 Redeclaring `static constexpr` | No | `-Wdeprecated` |
| D.8 `operator "" _x` | Yes | |
| D.9 Redundant `template` | No | No corresponding warning |
