---
title: Linkage specifications
summary: "How extern \"C\" makes a C++ declaration connect to the outside world by C's conventions; what has language linkage, and how linkage specifications nest and apply; why same-name C functions in different namespaces are the same function."
updated: 2026-10-19
---

!!! tldr
    - `extern "C"` gives a declaration C language linkage, which in practice means naming the symbol and calling it the C way. It is separate from a name's linkage (external, internal, etc.).
    - Linkage specifications can nest, with the innermost one deciding; they don't establish a scope and can only appear at namespace scope.
    - Class members ignore C language linkage, so strictly speaking a static member function can't serve as a C callback.
    - Functions or variables with C language linkage and the same name are the same entity no matter which namespace declares them, so they can't be overloaded.
    - Per the standard, language linkage is part of a function type; GCC, Clang and MSVC don't distinguish it.

## extern "C" in C headers

C++ has namespaces and overloading, so parameter types and the enclosing namespace have to be encoded into symbol names in object files; this is called name mangling. C has none of this: the symbol for function `api` is just `api`. For C++ code to call a C library, or to export a function for C to call, the compiler has to treat the declaration by C's conventions:

```cpp
#ifdef __cplusplus
extern "C" {
#endif
int c_api(int);            // has C language linkage in C++
#ifdef __cplusplus
}
#endif
```

C headers use this idiom to serve both languages. `extern "C" { ... }` is called a **linkage specification**. The standard doesn't talk about name mangling and calling conventions; it describes them with an abstract notion: **[[g:language-linkage|language linkage]]**, the language whose conventions an entity or function type uses to connect to the outside world.

Language linkage and [[basic.link|linkage]] are two independent concepts. Linkage is about whether a name can refer to the same entity from other scopes or translation units, and comes in external, module, internal and none. The `f` in `extern "C" { static void f(); }` has internal linkage and therefore no language linkage, but its function type still has C language linkage (see Example 2 below).

## What has language linkage (¶1)

¶1 Functions and variables whose names have external linkage, and all function types, have a language linkage, C++ language linkage by default. Note 1 explains that the properties associated with a language linkage, such as the representation of external names and the calling convention, are up to each implementation and not described by the standard.

The last sentence of ¶1 says two function types with different language linkages are different types:

!!! std
    Two function types with different language linkages are distinct types even if they are otherwise identical.

The reason is that C and C++ calling conventions may differ on some platforms. If a pointer to a C++ function were handed to C code to call, the call could be made the wrong way; with language linkage as part of the type, the compiler can reject such mixing during type checking.

!!! impl "In practice no compiler does this"
    GCC, Clang and MSVC don't treat language linkage as part of the function type. On the platforms they support, C and C++ calling conventions are the same, and distinguishing the types would only cause trouble. So the following code should hold per the standard, but with Clang 23 the `static_assert` fails and the second `take` is treated as a redeclaration of the first:

    ```cpp
    extern "C" typedef void cfn();
    typedef void cppfn();
    void take(cfn*);
    void take(cppfn*);                 // standard: an overload; compilers: a redeclaration
    #include <type_traits>
    static_assert(!std::is_same_v<cfn, cppfn>);   // standard: holds; Clang 23: fails
    ```

    To accommodate implementations that do distinguish the types per the standard, [[alg.c.library]] requires `std::qsort` and `std::bsearch` to provide versions taking comparison functions with C language linkage as well as versions taking ones with C++ language linkage. Otherwise, per the standard, passing an ordinary C++ function to `std::qsort` would be a type error.

## Syntax and supported languages (¶2–¶4)

```text
linkage-specification:
    extern unevaluated-string { declaration-seq(opt) }
    extern unevaluated-string name-declaration
```

```cpp title="linkage-basic.cpp" error
struct complex { double re, im; };
complex sqrt(complex);          // C++ language linkage by default
extern "C" {
    double sqrt(double);        // C language linkage
}
extern "Ada" void ada_proc();   // error: Clang 23 doesn't recognize "Ada"
```

¶2 The quoted part is an unevaluated string ([[lex.string.uneval]]) and can't have an encoding prefix. The standard only specifies the meaning of `"C"` and `"C++"`, and paragraph 3 requires every implementation to support both. Other strings are conditionally-supported, with implementation-defined meaning {{impl}}; Note 3 points out that a language linkage the implementation doesn't recognize must be diagnosed. The recommended practice is to spell it as in the document defining the language, e.g. `Ada` rather than `ADA`.

The two `sqrt`s are overloads: functions with the same name can coexist as long as at most one has C language linkage (the reason is in paragraph 7 below).

¶4 A module import declaration inside a linkage specification whose language linkage is not C++ is conditionally-supported, with implementation-defined meaning.

## Nesting, scope and reach (¶5)

```cpp title="linkage-nest.cpp" error
extern "C++" {
    extern "C" void inner();          // OK: the innermost is "C"
}
extern "C" { int x_in_global; }       // x_in_global is a member of the global namespace
int* p = &::x_in_global;              // OK

void blk() {
    extern "C" void nope();           // error: a linkage specification can't appear at block scope
}
```

¶5 Linkage specifications can nest, and the innermost one determines the language linkage. Note 4 points out that a linkage specification doesn't establish a scope, so `x_in_global` above is a member of the global namespace. A linkage specification can only appear at namespace scope.

Inside a linkage specification, the specified language linkage applies to two kinds of things: the function types of all function declarators, and functions and variables whose names have external linkage. So a function and its type can have different language linkages; Example 2 in the standard shows several combinations:

```cpp title="linkage-types.cpp" ok
extern "C"
    void f1(void (*pf)(int));   // f1 and its type have C language linkage; pf points to a C function

extern "C" typedef void FUNC();
FUNC f2;                        // f2 has C++ language linkage; its type has C language linkage

extern "C" FUNC f3;             // f3 and its type both have C language linkage

void (*pf2)(FUNC*);             // pf2 has C++ language linkage; its type is pointer to a C++ function
                                // whose parameter is a pointer to a C function
extern "C" {
    static void f4();           // internal linkage, so f4 has no language linkage; its type has C language linkage
}

extern "C" void f5() {
    extern void f4();           // OK: linkage (internal) and type's language linkage (C) carried over from the earlier declaration
}
extern void f4();               // OK: same as above
void f6() {
    extern void f4();           // OK: same as above
}

static void f4() {}
int main() {}
```

To express a function type with C language linkage on its own, say to declare the type of a C callback, the only way is to put a `typedef` in a linkage specification, as with `FUNC`.

### Class members ignore C language linkage

The last sentence of ¶5 says that C language linkage is ignored when determining the language linkage of three things: class members, friend functions with a trailing requires-clause, and the function types of non-static member functions.

```cpp title="linkage-members.cpp" ok
extern "C" typedef void FUNC_c();

class C {
    void mf1(FUNC_c*);          // mf1 and its type have C++ language linkage; the parameter points to a C function
    FUNC_c mf2;                 // mf2 and its type have C++ language linkage
    static FUNC_c* q;           // q has C++ language linkage; its type is pointer to a C function
};

extern "C" {
    class X {
        void mf();              // mf and its type have C++ language linkage
        void mf2(void(*)());    // mf2 has C++ language linkage; the parameter points to a C function
    };
}

int main() {}
```

C code has no `this` and no class scope and can't call member functions directly, so giving them C language linkage is meaningless. And wrapping C headers containing struct definitions in `extern "C" { }` is extremely common, so the standard chose to ignore it silently rather than make it an error. Note that the parameter type of `X::mf2` is still affected by the linkage specification: `void(*)()` is a pointer to a C function.

!!! pitfall "A static member function can be used directly as a C callback"
    Per the standard, a static member function, as a class member, always has C++ language linkage. Passing `&S::cb` to a C API expecting an `extern "C"` function pointer (such as `pthread_create`) is a type mismatch per the standard. Because compilers don't distinguish them, it works in practice; the strictly portable approach is to define an `extern "C"` forwarding function at namespace scope.

## Directly contained declarations are treated as extern (¶8)

```cpp title="linkage-extern.cpp" error
extern "C" double f();
static double f();              // error: inconsistent with the earlier external linkage

extern "C" int i;               // a declaration, as if extern int i;
extern "C" {
    int i;                      // a definition
}

extern "C" static void g();     // error: can't have a storage class specifier
```

¶8 A declaration directly contained in a linkage specification is treated as having an `extern` specifier ([[dcl.stc]]) for the purpose of determining the linkage of the name and whether it is a definition, and it can't have a storage class specifier.

"Directly contained" means the form without braces, `extern "C" declaration`. Declarations inside braces aren't directly contained, so `extern "C" int i;` is just a declaration, while `extern "C" { int i; }` is a definition. When giving a variable C language linkage in a header, this difference decides whether you get multiple definitions.

## Declarations of the same entity must agree (¶6)

```cpp title="linkage-redecl.cpp" error
extern "C" void g();
void g();                       // OK: keeps C language linkage
extern "C++" void g();          // error: conflicts with the earlier C language linkage
```

¶6 If two declarations of the same entity give different language linkages, the program is ill-formed. If neither declaration is reachable from the other, for example when they are in two translation units, no diagnostic is required {{ifndr}}: neither the compiler nor the linker may report it, and the program's behavior has no guarantees. A redeclaration without a linkage specification keeps the entity's (and, where applicable, its type's) original language linkage.

Thanks to this rule, an `extern "C"` declaration in a header paired with a definition without `extern "C"` in the implementation file works fine:

```cpp
// c_api.h
extern "C" int api_version();
// c_api.cpp
#include "c_api.h"
int api_version() { return 3; }   // C language linkage; the symbol is the unmangled api_version
```

Conversely, if the implementation file forgets to include the header, the definition is a different function with C++ language linkage and a mangled symbol name. When other translation units call `api_version` with C language linkage, the linker reports an undefined symbol. This is what "no diagnostic required when not mutually reachable" looks like in practice: the compiler can't see the conflict, and often only the linker can find it.

## C functions don't belong to namespaces (¶7)

```cpp run title="linkage-cross-ns.cpp" ok
namespace A { extern "C" int f(); }
namespace B { extern "C" int f(); }

int A::f() { return 7; }

int main() { return B::f() == 7 ? 0 : 1; }   // B::f is A::f
```

¶7 When two declarations introduce the same name, if one declares a function or variable with C language linkage and the other declares such an entity too, or declares a variable belonging to the global scope, the two declarations declare the same entity.

C's external names are flat, with no namespaces, so functions or variables with C language linkage and the same name are the same entity no matter which namespace declares them. This is why `g()` in the example in [[namespace.udir#7]] isn't ambiguous. Example 4 in the standard:

```cpp title="linkage-same-entity.cpp" error
int x;
namespace A {
    extern "C" int f();
    extern "C" int g() { return 1; }
    extern "C" int h();
    extern "C" int x();               // error: same name as the global variable x
}

namespace B {
    extern "C" int f();               // A::f and B::f are the same function
    extern "C" int g() { return 1; }  // error: two definitions of g with C language linkage
}

int A::f() { return 98; }             // definition of the f with C language linkage
extern "C" int h() { return 97; }     // defines h; A::h and ::h are the same function
```

- `A::x()` and the global variable `x` are the same entity, one a function and one a variable, so it's ill-formed. The rule specifically mentions variables at global scope because in mainstream ABIs global variable symbols are unmangled anyway, and the C++ global variable `x` and an `x` with C language linkage are indistinguishable at the symbol level.
- `B::g` and `A::g` are two definitions of the same function, violating the ODR. They are in the same translation unit, so it must be diagnosed.

It also follows that functions with C language linkage can't be overloaded. Two `extern "C"` functions with the same name and different parameters in the same scope declare the same entity with different types, so it's ill-formed:

```cpp title="linkage-no-overload.cpp" error
extern "C" int over(int);
extern "C" int over(double);    // error: same entity, conflicting types
```

## Across the language boundary (¶9, ¶10)

¶9 Note 5: language linkage is part of a function type, so when calling through a pointer to a C function, the called function is considered a C function.

¶10 Linkage from C++ to entities defined in other languages, and vice versa, is implementation-defined and language-dependent {{impl}}. Such linkage is only possible when the object layout strategies of the two language implementations are similar enough.

In other words, `extern "C"` only guarantees the connection at the level of names and calls. Whether struct layout matches the C compiler's, whether `bool` and `_Bool` are compatible, and whether exceptions can pass through C stack frames are all up to the implementation. In practice, the platform ABI guarantees that standard-layout types have the same layout as C structs, e.g. the Itanium C++ ABI plus the System V psABI on Linux, and the Microsoft x64 ABI on Windows.

## Implementation notes

!!! impl "Symbol names"
    - On Itanium ABI platforms, functions and variables with C language linkage use unmangled names, with macOS adding a leading underscore throughout. Functions with C++ language linkage use mangled names starting with `_Z` that encode the namespace and parameter types.
    - On 32-bit x86, MSVC decorates C function symbols with a `_` prefix or `@n` suffix depending on the calling convention, and barely decorates them on x64; C++ names use mangling starting with `?`.
    - Symbols with C language linkage contain no parameter types, so the linker can't catch errors like a function declared as `int f(int)` and defined as `int f(double)`. This is the most dangerous class of problem in C interoperability.

!!! impl "Templates must have C++ language linkage"
    Including a C++ header inside `extern "C" { }` causes trouble with the templates in it: Clang 23 reports "templates must have C++ linkage" for `extern "C" { template<class T> void f(T); }`, and GCC rejects it as well. Earlier standards stated explicitly that a template shall not have C language linkage; the related wording visible in the current draft is that the declaration in a template declaration can't be a linkage specification ([[temp.pre]]). When needed, nest an `extern "C++" { }` inside to restore C++ language linkage.

## Common misconceptions

!!! pitfall "extern \"C\" makes a function compile as C"
    The function body is still compiled as C++ and can use templates, throw exceptions and call overloaded functions; only the function's own name is exported by C's conventions. Letting an exception propagate from an `extern "C"` function to a C caller has implementation-defined results, usually as severe as undefined behavior.

!!! pitfall "You can write a separate copy of the same C interface in different namespaces"
    You can't. Per paragraph 7 they are the same entity: two definitions conflict, and two declarations silently merge into one.

!!! pitfall "extern \"C\" int i; is a definition"
    The form without braces is treated as having `extern`, so it is only a declaration (paragraph 8) and must be defined separately somewhere.

## Questions

!!! question "Question 1"
    What language linkage does each function below have? And their function types?

    ```cpp
    extern "C" {
        static int s();
        namespace N { int t(); }
        struct S { static int u(); };
    }
    ```

<details markdown="1">
<summary>Answer</summary>

- `s`: the name has internal linkage, so it has no language linkage; its function type has C language linkage, like `f4` in Example 2.
- `N::t`: a linkage specification doesn't establish a scope and can contain namespace definitions. `t` has external linkage, so it and its type have C language linkage. By paragraph 7, it is the same function as any `extern "C" int t()` in any namespace.
- `S::u`: class members ignore C language linkage, so `u` has C++ language linkage. But paragraph 5 only ignores C language linkage for the function types of non-static member functions; `u` is a static member function, so by the literal rule its function type has C language linkage. Since compilers don't distinguish the language linkage of function types, this can't be observed in practice.
</details>

!!! question "Question 2"
    Why does paragraph 7 include variables at global scope in the same-entity test, but not C++ functions at global scope?

<details markdown="1">
<summary>Answer</summary>

Functions can be distinguished by overloading: `extern "C" int f(int);` and a global `int f(double);` are two functions, and the latter's symbol is mangled. Variables can't be overloaded, and in mainstream ABIs global variable symbols are unmangled anyway, indistinguishable at the symbol level from a same-name entity with C language linkage. If `namespace A { extern "C" int x(); }` and a global `int x;` were allowed to coexist as two entities, the linker would see two symbols with the same name. So the standard specifies them as the same entity and then derives ill-formedness from the type mismatch.
</details>
