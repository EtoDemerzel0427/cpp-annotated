---
title: Declarations and definitions
summary: "A declaration is a definition by default, with only 22 exceptions; what redeclarations and first declarations are; implicit definitions of special member functions; a defined object can't have an incomplete or abstract class type."
updated: 2026-10-19
---

!!! tldr
    - A declaration tells the compiler that an entity exists and what its type is; a definition actually provides it: the storage for a variable, the body of a function, the full member list of a class.
    - The standard doesn't define a definition directly. Instead it says every declaration is a definition unless it is one of the 22 exceptions listed in ¶2, such as a function declaration without a body, an `extern` declaration without an initializer, or a non-inline static data member in a class.
    - `extern "C" { int v; }` is a definition, `extern "C" int v;` is not; a `static const int` member is only a declaration in the class, while a `static constexpr` member is a definition.
    - A declaration is a redeclaration if another declaration of the same entity is reachable from it; otherwise it is a first declaration.
    - When an object is defined, its type can't be an incomplete type or an abstract class; a mere declaration has no such restriction.

## Declarations versus definitions

<div class="compare" markdown="1">

```cpp
// declarations only
extern int a;
int f(int);
struct S;
struct X { static int y; };
```

```cpp
// definitions
int a;
int f(int x) { return x + a; }
struct S { int m; };
int X::y = 1;
```

</div>

A **declaration** ([[basic.pre]] ¶5 lists all its forms) tells the compiler that such an entity exists and what its type is, which is enough to check uses and generate calls. A **definition** actually provides it: storage for a variable, a body for a function, a full member list for a class.

This distinction is what lets C++ split a program into translation units compiled separately. Each translation unit only needs to see declarations to compile; a definition only needs to appear once in some translation unit to be found at link time. An entity can be declared many times, but the number of definitions is constrained by the [[basic.def.odr|ODR]].

## Which declarations are not definitions (¶2)

¶2 specifies that each entity declared by a declaration is also defined by it, unless it falls under one of the 22 exceptions below. To keep a declaration from being a definition you have to write it in some explicit way, such as omitting the function body, adding `extern`, or declaring a `static` member in a class.

### Functions and variables: no content given

| ¶ | Exception | Example |
|---|---|---|
| 2.1 | Declares a function without specifying its body | `int f(int);` |
| 2.2 | Has `extern` or a linkage specification, and neither an initializer nor a function body | `extern int a;`, `extern "C" int g(int);` |
| 2.3 | A non-inline static data member in a class definition | `struct X { static int y; };` |
| 2.4 | Redeclares, outside the class, a static data member defined in the class with `constexpr` (deprecated) | `constexpr int X::n;` |
| 2.8 | A parameter declaration in a function declarator that is not part of a function definition | `x` in `int f(int x);` |

The key to ¶2.2 is the condition "neither an initializer". `extern const int c = 1;` has an initializer, so it is a definition. This is how you define a `const` variable with external linkage at namespace scope, because a `const` variable without `extern` has internal linkage ([[basic.link#3]]).

Footnote 12 adds that whether a declaration inside the braces of `extern "C" { ... }` is a definition is unaffected by the linkage specification.

```cpp run ok
extern "C" int cvar2;      // declaration: a single-declaration linkage specification acts like extern
extern "C" { int cvar; }   // definition: same as outside the braces
extern "C" int cfun(int);  // declaration: there is no function body anyway
int main() { }
```

¶2.3 explains why, before C++17, an in-class `static const int N = 10;` still needed a definition outside the class. Since C++17 introduced inline variables, `static inline` members and `static constexpr` members (`constexpr` implies `inline`, [[dcl.constexpr]]) are definitions when declared in the class. A `static const int` member is not inline and is still only a declaration in the class; see the common misconceptions below.

¶2.4 is a compatibility rule kept for C++14 code. The out-of-class definition `constexpr int X::n;` that C++14 code wrote for a `static constexpr` member became a redundant redeclaration in C++17 and was deprecated ([[depr.static.constexpr]]). It can't count as a definition, or it would duplicate the inline definition in the class.

### Types: only a name or an alias

| ¶ | Exception | Example |
|---|---|---|
| 2.5 | *elaborated-type-specifier* | `struct S;`, the `struct S` in `struct S* p;` |
| 2.6 | *opaque-enum-declaration* (an enum declaration without an enumerator list) | `enum class E : int;` |
| 2.9 | typedef declaration | `typedef int Int;` |
| 2.10 | *alias-declaration* | `using Int = int;` |

A type alias only gives an existing type a new name and defines nothing. So consistent `typedef`s can be repeated in the same scope, and the ODR doesn't care about them.

### Declarations that only direct

| ¶ | Exception |
|---|---|
| 2.7 | template parameter |
| 2.11 | *namespace-alias-definition* (has "definition" in its name, but isn't one) |
| 2.12 | *using-declaration* |
| 2.13 | deduction guide |
| 2.14 | `static_assert` declaration |
| 2.15 | `consteval { ... }` block {{c++26}} |
| 2.16 | attribute declaration `[[attr]];` |
| 2.17 | empty declaration `;` |
| 2.18 | *using-directive* |
| 2.19 | `using enum` declaration |

The `consteval` block of ¶2.15 is a declaration form brought by C++26 static reflection. It executes some code during constant evaluation and defines nothing itself. It can generate a class definition through `std::meta::define_aggregate`; that definition is called an injected declaration ([[expr.const.reflect]]) and is a different declaration.

### Templates

| ¶ | Exception | Example |
|---|---|---|
| 2.20 | A template declaration whose template-head is followed by neither a concept-definition nor a declaration that defines a function, class, variable or static data member | `template<class T> void f(T);` |
| 2.21 | explicit instantiation declaration | `extern template struct Box<long>;` |
| 2.22 | an explicit specialization whose declaration is not a definition | `template<> struct Box<void>;` |

¶2.20 simply means: whether a template declaration is a definition depends on whether the declaration after the template-head is a definition.

```cpp run ok
template<class T> struct Box;           // declaration
template<class T> struct Box { T t; };  // definition
template<> struct Box<void>;            // declaration of an explicit specialization (¶2.22)
template struct Box<int>;               // explicit instantiation definition: a definition
extern template struct Box<long>;       // explicit instantiation declaration (¶2.21)
template<class T> concept C = true;     // concept definition: a definition
int main() { }
```

The explicit instantiation definition `template struct Box<int>;` isn't among the exceptions, so it defines `Box<int>` and its members. Combined with `extern template`, it lets a specialization be instantiated in only one translation unit ([[temp.explicit]]).

### The standard's example

Example 1 in ¶2 summarizes the rules above:

```cpp run ok
int a;                        // definition: no extern, so a definition even without an initializer
extern const int c = 1;       // definition: has extern but also an initializer
int f(int x) { return x+a; }  // defines f and the parameter x
struct S { int a; int b; };   // defines S, S::a, S::b
struct X {                    // defines X
  int x;                      // defines the non-static data member x
  static int y;               // declaration only (¶2.3)
  X(): x(0) { }               // defines the constructor
};
int X::y = 1;                 // defines X::y
enum { up, down };            // defines up and down
namespace N { int d; }        // defines N and N::d
X anX;                        // defines anX

extern int a;                 // everything below is a declaration only
extern const int c;
int f(int);
struct S;
typedef int Int;
namespace N1 = N;
extern X anotherX;
using N::d;
int main() { }
```

The in-class `int x;` falls under no exception, so it defines the non-static data member `X::x`. A member has no separate storage, but the standard still says it is defined: definition is a semantic notion, not the same as allocating storage.

`namespace N { }` is also a definition, but a namespace is not a definable item for the ODR ([[basic.def.odr#1]]), so the same namespace can be reopened again and again.

## Redeclarations and first declarations (¶1)

¶1 A declaration may introduce one or more names or entities into a translation unit and specify properties such as their type and linkage.

!!! std
    A declaration of an entity X is a *redeclaration* of X if another declaration of X is reachable from it; otherwise, it is a *first declaration*.

If another declaration of an entity X is reachable ([[module.reach]]) from a declaration of X, that declaration is a **redeclaration**; otherwise it is a **first declaration**. In ordinary header-based code, reachable roughly means "appears earlier"; in modules it also depends on imports. Phrasing it in terms of reachability lets one rule cover both cases.

Quite a few rules are written in terms of the first declaration:

- You can't define a function first and add `inline` later: if a definition is reachable at the point of the first inline declaration, the program is ill-formed ([[dcl.inline#4]]);
- If any declaration has `[[noreturn]]`, the first declaration must have it ([[dcl.attr.noreturn]]);
- A later declaration can't specify a default argument again, not even with the same value ([[dcl.fct.default]]).

Note 1 lists the effects a declaration can have besides introducing names: static assertions, controlling template instantiation, guiding template argument deduction for constructors, using attributes, and the empty declaration doing nothing.

## A defined object must be complete and non-abstract (¶5)

¶5 When an object is defined, its type can't be an incomplete type ([[basic.types.general]]), an abstract class ([[class.abstract]]), or an array of these.

A definition allocates storage and constructs the object, so the compiler must know the size and must be able to construct a complete object. Merely declaring an object needs neither; `extern Inc ei;` is valid as long as it is defined elsewhere.

```cpp error
struct Inc;
struct Abs { virtual void f() = 0; };

Inc i;           // error: incomplete type
Abs a;           // error: abstract class
Abs arr[2];      // error: array of abstract class
extern Inc ei;   // OK: declaration only
extern Abs ea;   // OK per the standard, but Clang rejects it; see below
Inc* pi;         // OK: the pointer type is complete
void take(Inc);  // OK: a function declaration that isn't a definition
Abs make();      // OK: likewise
```

!!! impl "How Clang handles `extern Abs ea;`"
    C++20's [[P0929R2]] narrowed the restriction on abstract classes to the cases that really need a complete object: defining an object, defining or calling a function with it as a parameter or return type, and explicitly converting to it (the note in [[class.abstract#3]]). By that rule, `extern Abs ea;` is only a declaration and is well-formed. Clang 23 still reports "variable type 'Abs' is an abstract class", which is a place where the implementation lags the standard; `Abs make();` is accepted as expected.

## Implicitly defined special member functions (¶3)

```cpp run ok
#include <string>
struct C {
  std::string s;
};
int main() {
  C a;      // uses the default constructor, which is implicitly defined
  C b = a;  // copy constructor
  b = a;    // copy assignment operator
}           // destructor
```

¶3 is a note: in some circumstances, the implementation **implicitly defines** the default constructor, the copy and move constructors, the copy and move assignment operators, and the destructor.

There are two steps here. At the end of the class definition, if the user hasn't declared a given special member and it isn't suppressed, the compiler implicitly declares it. Later, it is implicitly defined only when it is odr-used (actually used and so needing a definition, see [[basic.def.odr]]) or needed for constant evaluation (for example [[class.default.ctor#4]]).

The standard's Example 2 says the `C` above is equivalent to this:

```cpp
struct C {
  std::string s;
  C() : s() { }
  C(const C& x): s(x.s) { }
  C(C&& x): s(static_cast<std::string&&>(x.s)) { }
  C& operator=(const C& x) { s = x.s; return *this; }
  C& operator=(C&& x) {
    s = static_cast<std::string&&>(x.s); return *this;
  }
  ~C() { }
};
```

This is only a semantic approximation. The implicitly defined versions keep the properties of defaulted functions: they may be trivial, may be `constexpr`, and their `noexcept` is deduced from the subobjects. The hand-written versions lose those properties.

Implicit definitions are also subject to the ODR: [[basic.def.odr#17]] says an implicit definition is treated as occurring once in each translation unit that uses it, and every one of them must call the same subobject constructors.

¶4 is another note: an *elaborated-type-specifier* can also implicitly declare a class name.

```cpp run ok
void f(struct Q* q);  // the first appearance of Q also declares the global class Q
Q* p = nullptr;       // OK
int main() { }
```

For why `Q` belongs to the global namespace rather than the function parameter scope, see [[dcl.type.elab]].

## The implementation's view

!!! impl "Declarations and definitions in object files"
    - When a function or variable that is only declared is used, the object file contains an undefined symbol (`U` in `nm`), which the linker looks for in other object files. A definition produces a defined symbol (`T` for code, `D` or `B` for data).
    - In C, `int a;` is a [[g:tentative-definition|tentative definition]], and C compilers long placed it in the common section, allowing it to be repeated across translation units (since GCC 10 and Clang 11, C also defaults to `-fno-common`). C++ has no tentative definitions; writing `int a;` in two translation units violates the ODR ([[basic.def.odr#16]]) and produces a duplicate-symbol error at link time.
    - Class definitions, type aliases and template declarations produce no symbols themselves; only the functions, variables, vtables and typeinfo generated from them do.

## History

!!! history
    - C++98 already used the approach of "a declaration is a definition by default, with listed exceptions"; there were fewer than ten exceptions then.
    - C++11 added alias declarations, `static_assert`, attribute declarations, empty declarations, opaque enum declarations, and `extern template`.
    - C++17's inline variables ([[P0386R2]]) made in-class `static inline` and `static constexpr` members definitions, leaving behind the deprecation clause of ¶2.4; deduction guides were added at the same time.
    - C++20 added `using enum` and concepts; because of modules, redeclaration was redefined in terms of reachability.
    - C++26 added `consteval` blocks (¶2.15).

## Common misconceptions

!!! pitfall "Since C++17, all in-class static constant members are inline"
    Only `constexpr` static data members are implicitly inline ([[dcl.constexpr]]). `static const int N = 0;` is still only a declaration in the class. Merely reading its value needs no definition, so usually nothing shows; but as soon as it is bound to a reference, for example passed to `std::max`, whose parameters are `const int&`, a definition is needed.

    ```cpp
    #include <algorithm>
    struct S { static const int N = 0; };     // declaration only
    int main() { return std::max(S::N, 1); }  // needs a definition of S::N
    ```

    With Clang 23 at `-O0` this fails to link (`"S::N", referenced from`); at `-O2` the call is inlined and the constant folded, so it happens to link. By the standard, the program lacks a definition, which is an error for which no diagnostic is required. The fix is to write `static constexpr int N = 0;` or `static inline const int N = 0;`, or to add `const int S::N;` in some .cpp file.

!!! pitfall "An `extern` declaration is never a definition"
    `extern int x = 1;` is a definition, because ¶2.2 only excludes the case without an initializer. Put it in a header included by two translation units and you have a duplicate definition. Clang warns about it with `-Wextern-initializer`, but it really is valid.

## Questions

!!! question "Question 1"
    Which of these declarations are definitions?

    ```cpp
    struct A { static constexpr int n = 1; static const int m = 2; static int k; };
    constexpr int A::n;
    const int A::m;
    template<class T> void f(T);
    template<> void f<int>(int);
    template<> void f<char>(char) { }
    namespace NS = std;
    extern "C" { void g(); int v; }
    ```

<details markdown="1">
<summary>Answer</summary>

- The class definition of `A` defines `A`.
- `A::n`: a definition in the class (`constexpr` implies inline); the out-of-class `constexpr int A::n;` is not a definition (¶2.4, deprecated).
- `A::m`: a declaration in the class (¶2.3); the out-of-class `const int A::m;` is a definition.
- `A::k`: only the in-class declaration, no definition.
- `template<class T> void f(T);` is not a definition (¶2.20); neither is `template<> void f<int>(int);` (¶2.22); `template<> void f<char>(char) { }` is a definition of an explicit specialization.
- `namespace NS = std;` is not a definition (¶2.11).
- `extern "C" { void g(); int v; }`: `g` has no body and is only declared; `v` is defined (footnote 12).
</details>

!!! question "Question 2"
    Are `extern Abs ea;` and `Abs make();` valid (where `Abs` is an abstract class)?

<details markdown="1">
<summary>Answer</summary>

Both are valid. ¶5 only constrains definitions of objects. The note in [[class.abstract#3]] says an abstract class can't be used as a parameter or return type of a function being defined or called; a mere function declaration is unaffected.
</details>

## Summary

- A declaration is a definition by default; ¶2 lists 22 exceptions.
- Common non-defining declarations: function declarations without a body, `extern` without an initializer, non-inline static data members in a class, `struct S;`, opaque enums, type aliases, the various usings, `static_assert`, template declarations without a defining body, `extern template`, explicit specializations without a defining body.
- Two misleading names: a *namespace-alias-definition* is not a definition; a concept definition is a definition.
- `extern "C" { int v; }` is a definition; `extern "C" int v;` is not.
- Special member functions are implicitly defined only when used, and are subject to the ODR.
- A definition of an object can't have an incomplete or abstract class type; a declaration can.
