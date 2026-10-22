---
title: Specifiers
summary: "The kinds of specifiers that start a declaration and which may not be repeated; attributes at the end of the specifier sequence appertain to the type; when a type name in the specifier sequence is a type and when it is the name being declared."
updated: 2026-10-19
---

!!! tldr
    - Keywords and type names at the start of a declaration, such as `static constexpr unsigned long` or `inline virtual`, form the specifier sequence, which applies to the whole declaration; the order of specifiers is free.
    - `friend`, `typedef` and `inline` may each appear at most once; at most one of `constexpr`, `consteval` and `constinit` may appear.
    - Attributes at the end of the specifier sequence appertain to the type, not to the declared entity; no standard attribute may be used in that position.
    - A type name in the specifier sequence counts as a type only if no type specifier (other than a cv-qualifier) precedes it; otherwise it is the name being declared. So in `void h(unsigned Pc);`, `Pc` is the parameter name.
    - typedef is not macro substitution: after `typedef char* Pc;`, `const Pc` is `char* const`, not `const char*`.

## When a typedef name is a type

```cpp run ok
#include <type_traits>
typedef char* Pc;
void f(const Pc);          // Pc is a type → void f(char* const)
void g(const int Pc);      // Pc is the parameter name → void g(const int)
void h(unsigned Pc);       // Pc is the parameter name → void h(unsigned int)

static_assert(std::is_same_v<decltype(f), void(char*)>);   // a parameter's top-level const isn't part of the function type
static_assert(std::is_same_v<decltype(h), void(unsigned)>);
int main() { }
```

The same name `Pc` is a type in `f`, but a parameter name in `g` and `h`. This is decided by paragraph 3 of [dcl.spec.general]; below we first go through the kinds of specifiers, then come back to this rule.

## Kinds of specifiers (¶1)

¶1 There are nine kinds of **decl-specifier** that can start a declaration, and a sequence of them is a *decl-specifier-seq*:

| Specifier | Effect | See |
|---|---|---|
| *storage-class-specifier*: `static` `thread_local` `extern` `mutable` | Storage duration, linkage, mutable members | [[dcl.stc]] |
| *defining-type-specifier*: type specifiers, class definitions, enumeration definitions | Gives the base type | [[dcl.type]] |
| *function-specifier*: `virtual`, `explicit`, `explicit(bool)` | Functions only | [[dcl.fct.spec]] |
| `friend` | Friend declarations | [[dcl.friend]] |
| `typedef` | Type aliases | [[dcl.typedef]] |
| `constexpr` | Usable in constant evaluation | [[dcl.constexpr]] |
| `consteval` | Immediate functions, callable only in constant evaluation | [[dcl.constexpr]] |
| `constinit` | Requires static initialization | [[dcl.constinit]] |
| `inline` | Allows one definition per translation unit | [[dcl.inline]] |

A few things are not specifiers:

- Since C++11, `auto` is no longer a storage class specifier but a placeholder type specifier, which is a type specifier ([[dcl.spec.auto]]); `register` was removed in C++17 ([[dcl.stc]]).
- `override` and `final` are written after the declarator ([[class.mem]]).
- `noexcept` is part of the function type and is written in the declarator ([[except.spec]]).
- `extern "C"` is a linkage specification, not a storage class specifier ([[dcl.link]]).

The order of specifiers is free. `int static const x = 0;`, `const static int y = 0;` and `static int const z = 0;` are exactly equivalent, and multi-word types like `unsigned long` can be interleaved with other specifiers ([[dcl.type.simple#4]]):

```cpp run ok
int static const x = 0;
long unsigned long const static y = 0;   // static const unsigned long long
inline static int z = 0;                  // same as static inline
int main() { return x + int(y) + z; }
```

The C standard lists storage class specifiers not at the beginning as an obsolescent feature; the C++ standard has no such rule. Still, for readability and for headers shared with C, convention puts `static` and `extern` first.

### Attributes at the end of the specifier sequence

¶1 The grammar also allows attributes at the end of the specifier sequence. These attributes **appertain to the type determined by the preceding specifiers**, and affect that type only in this declaration. Attributes at the start of a declaration and after a name appertain to the declared entity ([[dcl.pre#4]]).

```cpp error
int [[deprecated]] x;      // error: deprecated can't apply to a type, and here it appertains to int
[[deprecated]] int y;      // OK: the leading attribute appertains to y
```

No standard attribute can apply to a type, so writing a standard attribute in this position is always an error. The position is meant for implementation-specific type attributes.

## Specifiers that can't be repeated (¶2)

¶2 Each of `friend`, `typedef` and `inline` may appear at most once in a specifier sequence; at most one of `constexpr`, `consteval` and `constinit` may appear in total.

```cpp error
inline inline void f();          // error: inline repeated
constexpr constinit int x = 1;   // error: constexpr and constinit can't both appear
consteval constexpr int g();     // error: likewise
```

Clang 23 gives only a `-Wduplicate-decl-specifier` warning for `inline inline` and `const const int`; this follows C, which allows repeated qualifiers and `inline`. In C++ both are ill-formed, and the warning satisfies the requirement for a diagnostic. `constexpr constinit` is an error.

A `constexpr` variable already requires constant initialization ([[dcl.constexpr#6]]), and `constinit` expresses only half of that, so writing both makes no sense. For functions, `constexpr` and `consteval` are mutually exclusive properties: callable in constant evaluation versus callable only in constant evaluation.

The repetition rules for other specifiers are in their own subclauses: at most one storage class specifier, except that `thread_local` may be combined with `static` or `extern` ([[dcl.stc#1]]); for combining type specifiers see [[dcl.type.general#2]]: `long long` is valid, `const const` is not.

## Does a type name belong to the specifiers or to the declarator (¶3–4)

Back to the opening question. `unsigned Pc` in `void h(unsigned Pc);` can be read two ways: `unsigned` plus the type name `Pc` form the specifier sequence and the parameter is unnamed; or `unsigned` is the specifier sequence and `Pc` is the parameter name. `unsigned` plus a typedef name isn't a valid type to begin with, so we want the second reading. But `const Pc` has the same two readings, and `const` plus `Pc` is a valid combination.

¶3 gives a definite rule:

!!! std
    If a *type-name* is encountered while parsing a *decl-specifier-seq*, it is interpreted as part of the *decl-specifier-seq* if and only if there is no previous *defining-type-specifier* other than a *cv-qualifier* in the *decl-specifier-seq*.

    A type name met while parsing the specifier sequence belongs to it if and only if no type specifier other than a cv-qualifier has appeared before it.

In other words, the specifier sequence swallows only the first type. Once a specifier that actually gives a type (`int`, `unsigned`, `long`, another type name, `class X {…}`, and so on) has appeared, a later type name no longer belongs to the specifier sequence; it starts the declarator, i.e. it is the name being declared. `const` doesn't count, because it can't form a type on its own.

¶4 (note) `signed`, `unsigned`, `long` and `short` imply `int` when used alone, so a type name after them is the name being declared; `void h(unsigned Pc)` is this case. This is just a corollary of ¶3.

```cpp error
typedef char* Pc;
static Pc;                 // error: Pc went into the specifier sequence, no declarator is left
```

This is Example 1 in the standard. To declare a static variable named `Pc`, you must first write a type specifier other than a cv-qualifier so that `Pc` lands in the declarator position: `static char* Pc;`. Clang 23 gives only a "declaration does not declare anything" warning for `static Pc;`.

### More edge cases

```cpp run ok
typedef int T;
void a(T const T);         // the first T is a type, the second the parameter name
void b() {
    T T = 1;               // declares a local int variable named T
    (void)T;               // from here on in this block, T refers to the variable
}
int main() { }
```

<div class="compare" markdown="1">

```cpp error
typedef long L;
void c(L long);
// error: L is already a type,
// long can't combine with it
```

```cpp error
typedef int T;
unsigned T u;
// error: T became the variable name,
// the following u can't be parsed
```

</div>

`void c(L long)` shows that the rule never backtracks. After `L` is swallowed into the specifier sequence, `long` is also a type specifier, but it is not a type name, so ¶3 doesn't apply to it, and `L long` violates the combination rules of [[dcl.type.general#2]]. The compiler won't reinterpret `L` as the parameter name because the combination failed.

¶3 only affects type names (class names, enum names, typedef names, [[dcl.type.simple]]); ordinary variable names never appear in a specifier sequence anyway. Deciding whether an identifier is a type name requires name lookup, which is one reason C++ parsing can't do without semantic information.

!!! note "Constructor declarations"
    In `S();` inside a class, `S` finds the injected-class-name; applying ¶3 mechanically would swallow it into the specifier sequence, leaving `()` as an unnamed function declarator. Constructors are recognized by a dedicated rule in [[class.ctor.general]]: a function declarator consisting of the injected-class-name followed directly by a parameter list, with no other type specifiers, declares a constructor.

¶3 Its last sentence requires the specifier sequence to be self-consistent; the concrete constraints are spread over the following subclauses of 9.2: [[dcl.stc]], [[dcl.fct.spec]], [[dcl.typedef]], [[dcl.type.general]], and so on.

## Common misconceptions

!!! pitfall "`const Pc` equals `const char*`"
    typedef is not textual substitution. `Pc` stands for the whole pointer type `char*`, and `const` is applied to that pointer type, giving `char* const` ([[dcl.type.cv]], [[dcl.typedef]]).

!!! pitfall "The order of specifiers matters"
    `int const static` and `static const int` are exactly the same. The only position-dependent rule is ¶3: a type name that appears after another type specifier becomes the name being declared.

## Questions

!!! question "Question 1"
    What is the type of each function below, and what are its parameters called?
    ```cpp
    typedef int A;
    typedef int B;
    void f(A B);
    void g(const A, B);
    void h(A const B);
    ```

<details markdown="1">
<summary>Answer</summary>

- `f(A B)`: `A` is a type; `B` is preceded by the type specifier `A`, so it is the parameter name. The type is `void(int)`.
- `g(const A, B)`: each parameter has its own specifier sequence. In the first, `const` doesn't count and `A` is a type; in the second, `B` is a type. Both parameters are unnamed, and the type is `void(int, int)`.
- `h(A const B)`: `A` is a type, `const` is a cv-qualifier, and `B` is preceded by `A`, so it is the parameter name. The type is `void(int)`.

We verified all three types with `__is_same` on Clang 23.
</details>

!!! question "Question 2"
    In `struct S { }; S S; S s2;`, why is the last declaration an error? How do you fix it?

<details markdown="1">
<summary>Answer</summary>

In `S S;` the first `S` is the class name and the second is the variable name, so this declares a variable named `S`. When lookup finds both a class and a variable, the class declaration is hidden ([[basic.lookup.general#4]]), so the `S` in `S s2;` finds the variable, not a type name, and that's a syntax error. Write `struct S s2;` instead: lookup for an elaborated type specifier ignores names that aren't types ([[basic.lookup.elab]]).
</details>
