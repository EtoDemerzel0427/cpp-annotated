---
title: "Templates: preamble"
summary: What a template declaration consists of and what it can declare; the definition of templated entities; the restricted grammar of the requires-clause; and why template definitions go in headers.
updated: 2026-10-19
---

!!! tldr
    - A template defines a family of classes, functions or variables, an alias for a family of types, or a concept. `std::vector` is a template; `std::vector<int>` is the class.
    - Enumerations, `typedef`s and namespaces cannot be templates. Templates can only be declared at namespace or class scope; the only way to get a template inside a function body is a generic lambda.
    - Function templates cannot be partially specialized, and a template declaration can declare only one entity.
    - Things defined inside a template (member functions of a class template, local classes, closure types of lambdas, and so on) are not templates, but they are templated entities, and many rules apply to them just as to templates.
    - A `requires` clause only accepts primary expressions joined by `&&` and `||`; `requires sizeof(T) > 1` must be written `requires (sizeof(T) > 1)`.

## What a template declaration looks like (¶1)

```cpp run title="kinds.cpp" ok
template<class T> struct Box { T v; };                 // class template
template<class T> T twice(T x) { return x + x; }       // function template
template<class T> constexpr T pi = T(3.14159L);        // variable template (C++14)
template<class T> using Ptr = T*;                      // alias template (C++11)
template<class T> concept Small = sizeof(T) <= 4;      // concept (C++20)
int main() {
  Box<int> b{1};
  Ptr<int> p = &b.v;
  static_assert(Small<int>);
  return twice(*p) - 2 + int(pi<double>) - 3;
}
```

¶1 A **template** defines a family of classes, functions or variables, an alias for a family of types, or a concept; these are called class templates, function templates, variable templates, alias templates and concepts. A template itself is not a class or a function; its **specializations** are: `Box` is not a type, `Box<int>` is.

Grammatically, a template declaration is a *template-head* followed by a declaration or a concept definition:

```text
template-declaration:
    template-head declaration
    template-head concept-definition
template-head:
    template < template-parameter-list > requires-clause(opt)
```

The *requires-clause* is part of the *template-head*, so the template head carries its constraints with it. For two declarations to be redeclarations of the same template, their *template-head*s (including the *requires-clause*) must be equivalent ([[temp.over.link]]).

Note 1: the `>` after a *template-parameter-list* can come from splitting `>>` into two `>` tokens ([[temp.names]]), so since C++11 `template<template<class> class TT>` doesn't need a space between the two `>`.

## Which declarations can be templates (¶2)

¶2 The declaration in a template declaration must be one of the following:

- ¶2.1 it declares or defines a function, a class or a variable;
- ¶2.2 it defines a member function, member class, member enumeration or static data member of a class template outside the class, for example `template<class T> void A<T>::f() {}`;
- ¶2.3 it defines a member template of a class or class template;
- ¶2.4 it is a *friend-type-declaration*;
- ¶2.5 it is a deduction guide ([[temp.deduct.guide]]);
- ¶2.6 it is an *alias-declaration*.

It also cannot be a linkage specification (of the form `extern "C++" ...`). So enumerations, `typedef`s and namespaces cannot be templates:

```cpp title="not-templatable.cpp" error
template<class T> enum E { a };   // error: an enumeration cannot be a template
template<class T> typedef T X;    // error: a typedef cannot be a template
template<class T> using Y = T;    // OK: alias template
```

For an alias that varies with a type, use an alias template. When C++11 added alias templates it chose the new `using` syntax rather than extending `typedef`, and since then `using` has been the recommended way to write aliases.

A member enumeration of a class template can be defined outside the class (¶2.2), as in `template<class T> enum class A<T>::E : int { x };`. The enumeration is specialized along with the class template, but it is not an enumeration template itself.

A template also cannot have C language linkage ([[dcl.link]]), because C names are not mangled and could not tell `f<int>` from `f<double>`:

```cpp title="c-linkage.cpp" error
extern "C" {
  template<class T> void f(T);   // error: a template cannot have C language linkage
}
```

## Variable templates (¶3)

¶3 A template declaration of a variable introduces a **variable template**; a variable template at class scope is a **static data member template**.

```cpp run title="variable-template.cpp" ok
#include <cstdio>
template<class T>
constexpr T pi = T(3.1415926535897932385L);

template<class T>
T circular_area(T r) { return pi<T> * r * r; }

struct S {
  template<class T>
  static constexpr int size = sizeof(T);   // static data member template
};

int main() {
  std::printf("%f %d\n", circular_area(1.0), S::size<double>);
}
```

Before C++14 added variable templates, a constant that varies by type had to be written as `std::is_same<T, U>::value` or as a `constexpr` function template. Variable templates are what made the C++17 `_v` components such as `std::is_same_v<T, U>` possible.

Variable templates can also be partially specialized ([[temp.spec.partial]]). Note 3 in ¶4 points out that declaring a class template or variable template with a *simple-template-id* (such as `rank<T[]>`) declares a partial specialization:

```cpp run title="var-partial.cpp" ok
template<class T> constexpr int rank = 0;
template<class T> constexpr int rank<T[]> = 1 + rank<T>;          // partial specialization
template<class T, int N> constexpr int rank<T[N]> = 1 + rank<T>;
static_assert(rank<int[2][3]> == 2);
static_assert(rank<int[][4]> == 2);
int main() {}
```

## Where and how templates are declared (¶4–¶5)

Note 2 in ¶4: a template declaration can appear only at namespace scope or class scope.

```cpp title="block-scope.cpp" error
void g() {
  template<class T> struct L {};          // error: cannot declare a template at block scope
  auto lam = [](auto x) { return x; };    // OK: generic lambda
}
```

A generic lambda is the only way to get a template inside a function body. Its closure type and `operator()` template are generated by the language, not introduced by a template declaration at block scope.

¶4 has two more requirements. First, the declaration in a template declaration cannot be an export declaration: to export a template, `export` goes on the outside, as in `export template<class T> void f(T);`. Second, the declarator name of a function template declaration must be a name (an identifier, `operator@`, a conversion function name or a literal operator name), not a *template-id*. This is the rule that forbids partial specialization of function templates:

```cpp title="no-fn-partial-spec.cpp" error
template<class T> void f(T);
template<class T> void f<T*>(T*);   // error: function templates cannot be partially specialized
template<class T> void f(T*);       // OK: another overloaded function template, chosen by partial ordering
```

When you need a similar effect, use overloading plus partial ordering ([[temp.func.order]]), or forward the logic to a class template, which can be partially specialized.

¶5 A template declaration, explicit specialization or explicit instantiation can have at most one declarator; a declaration of a class template cannot have a declarator at all:

```cpp title="one-declarator.cpp" error
template<class T> T a, b;          // error: a template declaration can declare only one entity
template<class T> struct S {} s;   // error: cannot declare a variable together with a class template
```

If `template<class T> T a, b;` were allowed, it would be unclear whether `a` and `b` are one template or two, and whether an explicit specialization of `a<int>` also specializes `b`. The standard simply forbids it.

The second half of ¶5 says that a friend type declaration in a template declaration can only be a single `friend friend-type-specifier ;`. C++26 lets one friend declaration declare several friend types with a pack expansion, but such an expansion cannot be used in a template declaration:

```cpp title="friend-pack.cpp" error
template<class...> struct C { struct Nested {}; };
template<class... Us>
struct S {
  template<class... Ts>
  friend class C<Ts>::Nested...;   // error: a friend in a template declaration cannot be a pack expansion
  friend class C<Us>::Nested...;   // OK (C++26): not a template declaration; expands the outer pack
};
```

## Specializations and names (¶6–¶7)

¶6 A specialization of a template (explicit or implicit) is distinct from every specialization of any other template, even if the two have exactly the same structure. An alias template does not produce new types; its specialization is the type after substitution ([[temp.alias]]):

```cpp run title="distinct.cpp" ok
#include <type_traits>
template<class T> struct A { T x; };
template<class T> struct B { T x; };
static_assert(!std::is_same_v<A<int>, B<int>>);   // different templates, different types
template<class T> using AA = A<T>;
static_assert(std::is_same_v<AA<int>, A<int>>);   // the specialization of the alias template is A<int>
int main() {}
```

Note 4 in ¶6: for purposes of template instantiation, default arguments of function templates and of member functions of class templates are considered definitions ([[temp.decls]]) and must obey the ODR.

Note 5 in ¶7: a template cannot have the same name as another name in the same scope ([[basic.scope.scope]]). The exception is function templates, which can share a name with names introduced by using-declarations, types, ordinary functions and other function templates; this is what lets function templates take part in overloading. A specialization (including a partial specialization) does not introduce a new name; it belongs to the same scope as the primary template.

```cpp title="names.cpp" error
void f() {}
class f {};                                    // OK: a function and a class with the same name
template<typename> void f(long) {}             // #1 OK: a function template with the same name as a function
template<typename> void f(long) {}             // error: redefinition of #1
template<typename> void f(long long) {}        // OK: another overload
template<>         void f<int>(long long) {}   // OK: an explicit specialization introduces no name
template<typename> struct f2 {};
int f2;                                        // error: a class template cannot share a name with a variable
```

## Templated entities (¶8)

```cpp run title="templated.cpp" ok
template<class T>
struct A {
  void f() {}          // A<T>::f is not a template, but it is templated (¶8.4)
  enum E { e1 };       // both E and e1 are templated (¶8.4, ¶8.5)
  friend void g(A) {}  // a friend defined in a templated class: templated (Note 6)
};
template<class T>
void h() {
  struct Local { T t; };   // templated class (¶8.3)
  auto lam = [] {};        // the closure type is templated (¶8.6)
  (void)lam; Local l{}; (void)l;
}
int main() { h<int>(); A<int>{}.f(); }
```

Member functions of a class template and local classes in a function template are not templates themselves, yet they live inside a template and there is one of each for every specialization of the template. ¶8 calls all of these **templated entities** ([[g:templated-entity|templated entity]]). An entity is templated if it is:

| | Case | Example |
|---|---|---|
| ¶8.1 | a template | `template<class T> void f(T);` |
| ¶8.2 {{c++26}} | an entity defined or created in the *for-range-declaration* or body of an expansion statement ([[stmt.expand]]) | `L` in `template for (auto x : tup) { struct L {}; }` |
| ¶8.3 | an entity defined or created in a templated entity | a local class, local variable or temporary object in a function template |
| ¶8.4 | a member of a templated entity | a member function of a class template |
| ¶8.5 | an enumerator of a templated enumeration | an enumerator of a member enumeration of a class template |
| ¶8.6 | the closure type of a lambda appearing in the declaration of a templated entity | the closure type of `[]{}` in a function template |

A **templated function** is a function template or a function that is templated; templated classes and templated variables are defined likewise.

¶8.2 was added with C++26 expansion statements: the body of `template for` is instantiated once per element, and entities defined in it must be treated as templated so that the type of `x` can differ each time.

Many rules apply to templated entities, not just to templates:

- Only a templated function can have a trailing *requires-clause* ([[dcl.decl]]), so ordinary member functions of a class template can be constrained too:

    ```cpp title="member-requires.cpp" error
    template<class T>
    struct S {
      void f() requires (sizeof(T) > 1);   // OK: S<T>::f is a templated function
    };
    S<char> s;                             // OK: only s.f() can't be called
    void g() requires true;                // error: not a templated function
    ```

- The discarded branch of `if constexpr` is not instantiated only inside a templated entity ([[stmt.if]]); in an ordinary function the discarded branch must still be entirely valid.
- Only inside a templated entity can names and expressions be dependent (depend on template parameters, [[temp.dep]]).
- The IFNDR rule for a template that can have no valid specialization ([[temp.res]]) applies to all templated entities.

## The requires clause (¶9)

```cpp title="requires-grammar.cpp" error
#include <type_traits>
template<class T> concept C = true;
template<class T> requires C<T> && std::is_integral_v<T> void f1();   // OK
template<class T> requires (sizeof(T) > 1) void f2();                 // OK: parenthesized
template<class T> requires requires (T t) { t + t; } void f3();       // OK: requires-expression
template<class T> requires sizeof(T) > 1 void f4();                   // error: needs parentheses
template<class T> requires !C<T> void f5();                           // error: must be written (!C<T>)
```

¶9 The optional *requires-clause* constrains the template arguments ([[temp.constr.decl]]). Its expression is an **unevaluated operand** ([[expr.context]]) and is never evaluated at run time.

Its grammar, *constraint-logical-or-expression*, only allows **primary expressions** (*primary-expression*) joined by `&&` and `||`: literals, names (including `C<T>` and `std::is_integral_v<T>`), parenthesized expressions, lambdas, fold expressions, requires-expressions, and so on. `sizeof(T) > 1`, `!C<T>` and `N == 0` are not primary expressions and must be parenthesized.

Why the restriction? A *requires-clause* is immediately followed by the rest of the declaration, and decl-specifiers could be misread as part of the expression. The example in Note 7:

```cpp error
template<int N> requires N == sizeof new unsigned short
int f();   // error: parentheses required around == expression
```

If arbitrary expressions were allowed, would `int` belong to `new unsigned short int`, or be the return type of `f`? The parser has no way to tell. With primary expressions only, any complex expression must be parenthesized and the boundary is clear. A trailing *requires-clause* after a function declarator uses the same grammar ([[dcl.decl]]).

In `template<class T> requires requires (T t) { ++t; }`, the first `requires` starts the *requires-clause* and the second starts a requires-expression. This is valid, but it usually means the requires-expression should be given a name by defining a concept: only named concepts take part in subsumption between constraints ([[temp.constr.order]]).

Although constraints are not evaluated, checking whether a constraint is satisfied involves substitution and constant evaluation ([[temp.constr.atomic]]), which can cause templates to be implicitly instantiated. There is no contradiction: constant evaluation happens at compile time and is not part of program execution.

## Template definitions go in headers (¶10)

¶10 The definition of a function template, a member function of a class template, a variable template, or a static data member of a class template must be reachable from the end of every **definition domain** (roughly a translation unit, see [[basic.def.odr]]) in which it is implicitly instantiated, unless the corresponding specialization is explicitly instantiated in some translation unit; otherwise {{ifndr}}.

```cpp title="a.h"
template<class T> T twice(T x);   // declaration only
```

```cpp title="a.cpp"
#include "a.h"
template<class T> T twice(T x) { return x + x; }
template int twice<int>(int);     // explicit instantiation definition: twice<int> is generated here
```

```cpp title="main.cpp" ok
#include "a.h"
int main() {
  return twice(21) == 42 ? 0 : 1;   // OK: twice<int> is explicitly instantiated in a.cpp
  // twice(1.0) would be IFNDR: the definition of twice<double> is not reachable and it is not explicitly instantiated
}
```

This is the basis for putting templates in headers. Why no diagnostic? When compiling `main.cpp` the compiler cannot see `a.cpp`, and does not know whether `twice<double>` is explicitly instantiated somewhere else.

In practice the typical symptom of violating this rule is a link error (undefined symbol `twice<double>`), but the standard guarantees nothing. If another translation unit happens to implicitly instantiate the same specialization, the linker may quietly use it and the program seems to work; with a different link order or optimization level, that translation unit may inline the call and no longer emit the symbol, and linking fails.

In modules, the definition can come from an imported module interface unit, as long as it is reachable ([[module.reach]]). So with modules, template definitions still have to go in the interface; in an implementation unit they are not reachable.

!!! impl
    - GCC, Clang (Itanium ABI) and MSVC all put implicitly instantiated template specializations into every object file that uses them as COMDAT or weak symbols, and the linker merges them.
    - An explicit instantiation declaration `extern template` ([[temp.explicit]]) tells the compiler not to instantiate here because it exists elsewhere; it is used to reduce compile time and object file size.
    - Name mangling encodes the template arguments; for example, `twice<int>` mangles to `_Z5twiceIiET_S0_`. For a constrained template the constraints also go into the mangled name: for `c1<int>` of `template<class T> requires std::integral<T> void c1(T)`, Clang produces `_Z2c1IiQsr3stdE8integralIT_EEvS0_`, where `Q...` encodes the *requires-clause*, to distinguish overloads that differ only in their constraints.

## History

!!! history
    - C++98 had only class templates and function templates. It also had `export template`, which allowed putting template definitions in a `.cpp` file and made the implementation responsible for instantiating across translation units, precisely to solve the ¶10 problem; but only compilers based on the EDG front end ever implemented it.
    - C++11 removed `export` templates (keeping the keyword reserved) and added alias templates, variadic templates, splitting of `>>`, and `extern template`.
    - C++14 added variable templates; C++17 added deduction guides.
    - C++20 added concepts and the *requires-clause*. Modules brought the `export` keyword back into use, which is why ¶4 says the declaration in a template declaration cannot be an export declaration.
    - C++26 made entities in expansion statements templated (¶8.2) and added pack expansion of friend types (¶5).

## Common misconceptions

!!! pitfall "A member function of a class template is a function template"
    `A<T>::f` is a templated function (¶8.4), not a function template: calling it does no template argument deduction, and it can only be explicitly specialized for a particular `A<X>` with `template<>`. It is instantiated on demand because [[temp.inst]] has specific rules for members of templated entities.

!!! pitfall "Putting a template definition in a .cpp file at worst causes a link error"
    By the standard this is IFNDR (¶10). If another translation unit happens to instantiate the same specialization, the program may run, and then fail with a different link order or optimization level.

## Questions

!!! question "1. Which of these declarations are well-formed?"
    ```cpp
    template<class T> struct A { enum class E; };
    template<class T> enum class A<T>::E { x };           // (a)
    template<class T> int v1 = 1, v2 = 2;                 // (b)
    template<class T> auto lam = [](T t) { return t; };   // (c)
    ```

<details markdown="1">
<summary>Answer</summary>

- (a) Well-formed. ¶2.2 allows defining a member enumeration of a class template outside the class.
- (b) Ill-formed. ¶5 says a template declaration has at most one declarator.
- (c) Well-formed. This is a variable template initialized with a lambda; `lam<int>` and `lam<double>` each have their own closure type (the closure type is templated, ¶8.6).
</details>

!!! question "2. The function template `template<class T> void g(T) {}` is defined only in `x.cpp`, and `x.cpp` calls `g(1)`; `y.cpp` has only a declaration and also calls `g(1)`. Is the program well-formed?"

<details markdown="1">
<summary>Answer</summary>

It is IFNDR (¶10). `y.cpp` implicitly instantiates `g<int>`, but its definition is not reachable from `y.cpp`, and `g<int>` is not explicitly instantiated in any translation unit: the one in `x.cpp` is only an implicit instantiation. In practice it usually links, because `x.cpp` emits a weak symbol `g<int>`; but with optimization `x.cpp` may inline `g<int>` and no longer emit the symbol, and linking fails.
</details>
