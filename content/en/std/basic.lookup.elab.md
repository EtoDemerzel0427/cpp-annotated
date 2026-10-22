---
title: Lookup in elaborated type specifiers
summary: "The name in struct X, class X, union X or enum X is looked up as a type only, skipping same-named variables and functions; an unqualified form that finds nothing declares a new class on the spot, while a qualified form must find an existing type."
updated: 2026-10-19
---

!!! tldr
    - The `X` in `struct X` or `enum X` is looked up only as a type, so it can reach past a same-named variable or function to a class that would otherwise be hidden.
    - If an unqualified `struct X*` does not find `X`, it declares a class on the spot in the nearest enclosing namespace or block scope, not in the current class.
    - `enum X` cannot declare an enumeration on the spot; a qualified `struct N::X` never declares a new type either, and not finding it is an error.
    - The keyword must match the kind of type: `enum` for enumerations, `union` for unions; `struct` and `class` are interchangeable.

## Type names with a keyword

```cpp run ok
#include <sys/stat.h>
int size_of(const char* path) {
    struct stat st;          // the function stat hides the class stat; struct is needed to name the type
    if (stat(path, &st) != 0) return -1;
    return static_cast<int>(st.st_size);
}
```

POSIX headers have both a class `stat` and a function `stat`. Within one scope, a class name is hidden by a same-named function or variable ([[basic.lookup#4]]), for compatibility with C. To refer to the class you have to write `struct stat`.

A type name with a `class`, `struct`, `union` or `enum` keyword is an **elaborated-type-specifier**. Besides getting around hiding, it has two more uses: `struct Node* next;` with no prior declaration declares class `Node` on the spot; and `struct X;` and `friend class Y;` serve as forward declarations and friend declarations.

This subclause has only three paragraphs, specifying how the names in it are looked up. What is declared after the lookup, and where, is specified by [[dcl.type.elab]], and is covered here as well.

## Unqualified: types only (¶1)

¶1 When the keyword is followed by an identifier that is not itself followed by `::`, the identifier is looked up by [[g:type-only-lookup|type-only lookup]] ([[basic.lookup#4]]): only types and templates whose specializations are types are considered.

Note 1 explains that if the identifier is followed by `::`, like the `X` in `struct X::Y`, it is part of the `X::` prefix and is looked up per [[basic.lookup.qual]]; the final `Y` is handled by ¶2.

Type-only lookup makes non-type declarations irrelevant. It not only gets around a variable or function in the same scope, but can also reach past a same-named variable in an inner scope to a type in an outer one:

```cpp run error
struct S { int m; };
void f() {
    int S = 0;                 // for ordinary lookup, the local variable S hides ::S
    struct S s{};              // OK: type-only lookup skips int S and finds ::S further out
    static_assert(sizeof(struct S) == sizeof(int));
    (void)S; (void)s;
}

namespace A { struct X {}; }
namespace B { int X; }
using namespace A;
using namespace B;
struct X* px;    // OK: B::X is not a type and is skipped, giving A::X
X* py;           // error: ordinary lookup finds both A::X and B::X: ambiguous
```

`X* py` is ambiguous because `A::X` and `B::X` come from searches of different namespaces, and a class is not hidden by a variable from elsewhere ([[namespace.qual#4]]).

Type-only lookup also specifies that when a type alias and the type it denotes are both found, the alias is discarded. [[dcl.type.elab#6]] makes it ill-formed for an elaborated type specifier to resolve to a typedef-name; with this rule, as long as the original type can be found, happening to find an alias too causes no error.

### Declaring a class on the spot when nothing is found

[[dcl.type.elab#3]] specifies that when unqualified lookup of an unqualified identifier finds nothing:

- `enum` cannot be used, that is, an enumeration cannot be declared on the spot this way. A forward declaration of an enumeration needs a complete opaque-enum-declaration (such as `enum E : int;`);
- the identifier is declared as a class name, in the nearest enclosing namespace or block scope, not in a class scope.

```cpp run error
struct Outer {
    struct Inner* q;          // Inner is not found; declares ::Inner at global scope
};
Inner* gi;                    // OK: ::Inner

struct L {
    void g() {
        struct Fn* r = nullptr;   // nearest enclosing block scope: Fn is a local class in g's body
        (void)r;
    }
};
Fn* bad;                      // error: there is no Fn at global scope

enum Color* pc;               // error: enum cannot declare an enumeration on the spot
```

`struct X;` on its own as a declaration is a different matter. Per [[dcl.type.elab#2]], it declares `X` in the current scope (which may be a class scope); it is an ordinary forward declaration and does not go through "not found, so declare".

### Friends only see the nearest enclosing namespace

[[dcl.type.elab#4]] places an extra restriction on `friend class Y;`: unqualified lookup does not consider scopes outside the nearest enclosing namespace (or block scope), and the declaration binds no name. That is, it looks only in the class itself, enclosing classes, and the nearest enclosing namespace. If nothing is found, it refers to a not-yet-declared class in the nearest enclosing namespace; until a real declaration appears, the name remains invisible.

## Qualified: must already exist (¶2)

¶2 If the terminal name of an elaborated type specifier is a qualified name (`struct N::X`, `class C::Inner`), lookup likewise considers only types; if no previously declared type-name is found, the program is ill-formed.

So a qualified elaborated type specifier never declares a new type. A declaration needs a target scope, and `struct N::X*` appears outside `N`; names cannot be added to another namespace or class from outside. To forward-declare `X` in `N`, write `namespace N { struct X; }`.

## The standard's example (¶3)

```cpp run error
struct Node {
    struct Node* Next;            // OK: finds the injected-class-name of Node
    struct Data* Data;            // OK: Data is not found; declares ::Data at global scope, and also declares member Data
};

struct Data {
    struct Node* Node;            // OK: type-only lookup finds ::Node
    friend struct ::Glob;         // error: Glob is not declared, and a qualified name cannot introduce a type
    friend struct Glob;           // OK: refers to a not-yet-declared Glob at global scope
};

struct Base {
    struct Data;                  // OK: a declaration on its own; declares the nested class Base::Data
    struct ::Data*     thatData;  // OK: ::Data
    struct Base::Data* thisData;  // OK: the nested Data
    friend class ::Data;          // OK: the global Data is a friend
    friend class Data;            // OK: the nested Data is a friend
    struct Data { };              // defines the nested Data
};

struct Data;                      // OK: redeclares the global Data
struct ::Data;                    // error: a qualified name cannot introduce a type
struct Base::Data;                // error: same as above
struct Base::Datum;               // error: Datum is not declared
struct Base::Data* pBase;         // OK: the nested Data
```

Three spots deserve a closer look.

`struct Data* Data;` does two things at once: the elaborated type specifier declares the global class `::Data`, and the declarator declares the member variable `Node::Data`. From then on inside `Node`, ordinary lookup of `Data` finds the member variable, and naming the type requires `struct Data`.

`struct ::Data;` and `struct Base::Data;` are errors even though the type exists. The reason is not lookup: [[dcl.type.elab#2]] does not allow an elaborated type specifier that forms a declaration on its own to have an `X::` prefix (except for explicit specializations, explicit instantiations and the like). Such a declaration would be meaningless anyway, since declarations cannot be placed into another scope.

When `friend class Data;` is written in `Base`, the class scope already contains `Base::Data`. Friend lookup looks at the class itself first, so it refers to the nested class.

## The keyword must match the kind

[[dcl.type.elab#7]] requires the keyword to agree with the declaration the name refers to: `enum` for an enumeration, `union` for a union, and `class` or `struct` for a non-union class, the last two being interchangeable.

```cpp run error
enum class E { a, b };
enum E x = E::a;                  // OK: a scoped enumeration is also elaborated with enum (not enum class)
struct S { } s;
class S* p = &s;                  // OK: struct and class are interchangeable
union U { };
struct U* pu;                     // error: U is a union
```

!!! warning "ABI hazard of mixing struct and class"
    The standard lets `struct` and `class` be interchanged, but MSVC's name mangling distinguishes them. Forward-declaring `class X;` and defining `struct X {}` can lead to unresolved symbols at link time on MSVC. The Itanium ABI does not distinguish them. Clang's `-Wmismatched-tags` warning about such mixing points at exactly this problem.

## Template parameters cannot take a keyword

[[dcl.type.elab#6]] Note 3 points out that in a class template with type template parameter `T`, `friend class T;` is ill-formed, because `T` acts like a typedef-name there; `friend T;` is valid ([[class.friend]], since C++11).

```cpp run error
template<class T> struct TT {
    friend T;          // OK
    friend class T;    // error
};
```

Clang 23 rejects the second declaration; its diagnostic says that it shadows the template parameter, which is a different reason from the standard's, but the conclusion is the same.

!!! history "History"
    - C++98: the rules of this subclause were essentially in place, including declaring the class in the nearest enclosing namespace or block scope when nothing is found.
    - C++11: scoped enumerations and opaque enumeration declarations were introduced, as was `friend T;`.
    - C++23: [[P1787R6]] promoted type-only lookup to a general concept in [basic.lookup.general] and added the rule that the alias is discarded when both an alias and the original type are found; this subclause shrank to three paragraphs, with the semantics of the declaration collected in [dcl.type.elab].

## Common misconceptions

!!! pitfall "struct X* inside a class declares a nested class"
    `struct Outer { struct Inner* q; };` declares a namespace-scope `Inner`, not `Outer::Inner`. Defining `struct Outer::Inner {}` elsewhere later is an error, because they are not the same class. For a nested class, write `struct Inner;` in the class first.

!!! pitfall "A class declared on the spot in a function body is visible outside the function"
    `struct Impl* p;` written in a function body declares a local class. It is not visible outside the function and cannot be defined outside it.

## Questions

!!! question "Question"
    ```cpp
    namespace N {
        struct A {
            struct B* p;
        };
    }
    struct B { };
    N::B* q;   // (1)
    ::B* r;    // (2)
    ```
    Are (1) and (2) valid?

<details markdown="1">
<summary>Answer</summary>

`struct B* p;` looks for the type `B` in `A`, `N` and the global scope in turn. The global `struct B` is declared only after it, so nothing is found, and `N::B` is declared in the nearest enclosing namespace `N`.

(1) is valid; `q` points to the incomplete type `N::B`. (2) is also valid, but `::B` and `N::B` are two different classes, and `A::p` cannot point to a global `B` object. For `a.p = &b` (where `b` is a global `B`), Clang 23 reports incompatible pointer types.
</details>

## Summary

| Case | Lookup | If nothing is found |
|---|---|---|
| `struct X` (unqualified, not a declaration on its own) | types only, unqualified lookup | declares class `X` in the nearest enclosing namespace or block scope |
| `enum X` (unqualified) | types only | ill-formed |
| `struct X;` (a declaration on its own) | no lookup | declares `X` in the current scope |
| `friend struct X;` | types only, not beyond the nearest enclosing namespace | refers to `X` in that namespace, binding no name |
| `struct N::X` (qualified) | types only, qualified lookup | ill-formed; never declares a new type |
| both an alias and the original type found | the alias is discarded | |
| only a typedef-name found | | ill-formed |
