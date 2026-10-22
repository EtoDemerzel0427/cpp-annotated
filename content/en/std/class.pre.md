---
title: Class definitions and class names
summary: "How a class definition is written (class, struct, union and final), the class being complete at its closing brace, the identity of the class name inside the class (the injected-class-name), and when a nested class can be defined outside its class; plus the class-name rules: every class definition introduces a new type, and a class hidden by a variable of the same name is named with struct X."
updated: 2026-10-19
---

!!! tldr
    - `class` and `struct` differ only in default access: `class` defaults to private, `struct` to public; `union` is another kind of class.
    - A class is complete at the `}` of its definition. Inside the class, only complete-class contexts such as function bodies and default arguments can treat it as a complete type.
    - The class name also appears as a public member in the class's own scope; this is the injected-class-name. After private inheritance, an unqualified base class name in a further-derived class can be inaccessible.
    - `final` is not a reserved word. It means the class cannot be derived from only when it appears after the class name and is immediately followed by `:` or `{`.
    - Two structurally identical classes are distinct types. When a class name is hidden by a variable or function of the same name, use `struct X` to name the class.

## Writing a class definition (¶1, ¶4)

```cpp run title="class-def.cpp" ok
struct Point { int x, y; };          // members public by default
class Account {                       // members private by default
    long balance = 0;
public:
    long get() const { return balance; }
};
union Value { int i; float f; };      // holds the value of at most one member at a time

int main() {
    Point p{1, 2};
    Account a;
    Value v{.i = 3};
    return p.x + int(a.get()) + v.i - 4;
}
```

¶1 A class is a type, and its name becomes a *class-name* in its scope. Only two pieces of syntax can introduce a class name: a class definition `struct X { ... };`, and the `struct X` in an **elaborated-type-specifier** such as `struct X;` or `struct X* p;` ([[dcl.type.elab]]). A class object consists of a (possibly empty) sequence of members and base class subobjects.

A class definition is called a *class-specifier* in the grammar; its skeleton is:

```text
class-specifier:  class-head { member-specification(opt) }
class-head:       class-key attribute-specifier-seq(opt) class-head-name final(opt) base-clause(opt)
                  class-key attribute-specifier-seq(opt) base-clause(opt)            ← unnamed class
class-head-name:  nested-name-specifier(opt) class-name
class-key:        class | struct | union
```

¶4 The *class-key* determines two things (this paragraph is a note): whether the class is a union ([[class.union]]), and whether members and bases are public or private by default ([[class.access]]). There is no other difference between `class` and `struct`.

The *class-head-name* has two unusual forms. With a nested-name-specifier, `struct N::X { ... }` defines a previously declared class from outside; see ¶3 below. A template argument list form such as `A<int>` can appear only in an explicit specialization or partial specialization, as in `template<> struct A<int> { ... };`, and cannot be used to define an ordinary class.

### Unnamed classes

A class definition that omits the class name defines an **unnamed class**. `final` can only follow a class name, so an unnamed class can never be `final` (Note 1).

```cpp run title="unnamed-class.cpp" ok
struct { int x, y; } pt;                 // unnamed class, also declares the variable pt
typedef struct { int r, g, b; } Color;   // Color is a typedef name for linkage purposes
using Size = struct { int w, h; };       // an alias-declaration works too

int main() {
    pt.x = 1;
    Color c{1, 2, 3};
    Size s{4, 5};
    return pt.x + c.r + s.w - 6;
}
```

You can't write `~X()` for an unnamed class, so it cannot declare constructors or a destructor, and it cannot have static data members ([[class.static.data#2]]). The `Color` in `typedef struct {...} Color;` is a typedef name for linkage purposes ([[dcl.typedef]]); translation units use it to name the same class.

### The class name is introduced by the definition, not looked up

The last sentence of ¶1 says that, apart from the two special forms above, the class name is just an identifier: it is not subject to name lookup but is introduced by the class definition. So `struct X { ... };` always introduces or redeclares an `X` in the current scope; it never completes an `X` from an enclosing scope just because one exists.

```cpp run title="introduce-not-lookup.cpp" ok
struct X { int a; };

namespace N {
    struct X { double d; };   // introduces a new class N::X, does not define ::X
}

static_assert(sizeof(N::X) == sizeof(double));
int main() { }
```

## A class is complete at its closing brace (¶2)

```cpp title="complete-at-brace.cpp" error
struct S;
S s1;                     // error: S is not yet complete

struct T {
    T* self;              // OK: pointer to an incomplete type
    char buf[sizeof(T)];  // error: T is not yet complete here
    int f() { return sizeof(T); }   // OK: a function body is a complete-class context
};
static_assert(sizeof(T*) > 0);
```

¶2 As soon as the closing brace of the class definition (the *class-specifier*, usually just called the class definition) appears, the class is regarded as defined, even though its member functions are in general not yet defined. At that point the compiler has determined the class's size, alignment, layout and the declarations of all its members, including the implicitly declared special member functions ([[special#1]]). The member functions can be defined in another translation unit.

Inside the class definition, the class is in general incomplete. The exception is a **complete-class context**: function bodies, default arguments, default member initializers, `noexcept` specifiers and so on, where the class is regarded as complete ([[class.mem.general#10]], [[class.mem.general#11]]). So a member function body can contain `sizeof(T)`, but a data member declaration cannot.

### Attributes on the class-head belong to the class

The last sentence of ¶2: attributes in the *class-head* appertain to the class itself, and every later use that names the class carries them.

```cpp run title="class-attrs.cpp" ok
struct [[nodiscard]] Error { int code; };
struct alignas(64) CacheLine { char data[64]; };

Error make() { return {0}; }

int main() {
    static_assert(alignof(CacheLine) == 64);
    (void)make();           // without (void) you get a nodiscard warning
}
```

## The injected-class-name (¶2)

```cpp run title="injected-class-name.cpp" ok
#include <type_traits>

template<class T>
struct List {
    List* next;                 // List means List<T>
    List<int>* other;           // followed by <, it is used as the template name
    static_assert(std::is_same_v<List, List<T>>);
};

struct Base { int v = 1; };
struct Derived : Base {
    int f() { return Base::v; } // Base is found via the inherited injected-class-name
};

int main() {
    List<char> l{};
    Derived d;
    return d.f() - 1 + (l.next == nullptr ? 0 : 1);
}
```

¶2 The class name is also bound in the scope of the class (or class template) itself; this is the **injected-class-name** ([[g:injected-class-name|injected-class-name]]). Think of every class as having an implicit member `X` that denotes `X` itself. For access checking, it is treated as a public member name.

This rule has three benefits. Inside the class, the class name always finds the class itself, unaffected by entities of the same name in enclosing scopes. Through inheritance, a base class name becomes a member that can be looked up in the derived class's scope, so `Derived` can write `Base::v`. In a class template, the template name by itself denotes the current specialization: `List` is `List<T>`.

### Private inheritance makes the base class name inaccessible

Since the injected-class-name is a member, it is affected by the kind of inheritance like any other member:

<div class="compare" markdown="1">

```cpp error
struct A { };
struct B : private A { };
struct C : B {
  void f() { A a; }
  // error: finds the injected-class-name A
  //   inherited from B, and B inherits A privately
};
```

```cpp run ok
struct A { };
struct B : private A { };
struct C : B {
  void f() { ::A a; (void)a; }
  // OK: the qualified name finds the global A directly
};
int main() { C{}.f(); }
```

</div>

Unqualified lookup of `A` in a member function of `C` first searches `C`'s class scope through its bases and finds the injected-class-name `A` inherited from `B`. It is found before the global `::A`, and it is reached through private inheritance, so it is inaccessible ([[class.access.base]]). Clang's diagnostic is `'A' is a private member of 'A'`.

### `X::X` means the constructor

```cpp title="ctor-name.cpp" error
struct D { };
D::D d;   // error: here D::D names the constructor, not a type
```

In a qualified name whose lookup context is a class `C`, `C::C` names the constructor rather than the injected-class-name ([[class.qual#1]]). This rule is what lets the compiler recognize an out-of-class constructor definition `X::X() { }` and an inheriting constructor `using Base::Base;`. The cost is that `D::D` is no longer a type name in ordinary contexts. When you need the type you can write `struct D::D`, because an elaborated-type-specifier only finds types.

## Defining a nested class outside its class (¶3)

```cpp title="qualified-class-def.cpp" error
namespace N {
    template<class> struct A { struct B; };
    struct C;
}
using N::A;
template<class T> struct A<T>::B { };  // OK: defines N::A<T>::B
template<> struct A<void> { };         // OK: explicit specialization
struct N::C { };                       // OK: defines the previously declared N::C
struct N::D { };                       // error: no declaration of D in N

struct E { struct F; };
struct G {
    struct E::F { };                   // error: cannot appear in a class scope
};
```

¶3 When the class name has a nested-name-specifier (`struct N::C { }`), there are three restrictions:

1. The class definition shall not inhabit a class scope: you cannot define another class's member class with a qualified name inside a class;
2. It must correspond ([[basic.scope.scope]]) to an existing declaration in the class, class template or namespace that the nested-name-specifier nominates. In other words, a qualified name can only provide a definition for an existing declaration; it cannot introduce a new name;
3. Those declarations must have the same target scope, and that is the class definition's target scope.

The first lines are adapted from Example 1 in the standard. The nested-name-specifier itself can be found in any way: the `A` in `A<T>::B` finds `N::A` via a using-declaration. The wording only requires that `N::A<T>` contain a nominable declaration of `B`, that is, one that precedes this point and whose target scope is that class.

## `final` (¶5, ¶6)

```cpp run title="final-disambig.cpp" ok
struct A;
struct A final { };     // defines the final class A, not value-initializing a variable named final

struct X {
    struct C { constexpr operator int() { return 5; } };
    struct B final : C { };   // defines the final nested class B, not a bit-field
};

struct final { };       // final can still be used as an ordinary identifier
final f;

int main() { (void)f; }
```

¶5 `final` is not a reserved word but an identifier with special meaning ([[lex.name]]). The rule is: when a *class-key* is followed by a class name, the identifier `final`, and then a colon or left brace, `final` is interpreted as a class-virt-specifier. `final` can appear at most once on a class.

This rule resolves a real ambiguity. The `struct B final : C { };` above can also be parsed as declaring a bit-field named `final` of type `struct B`, with width 5, obtained from `C{}` via the conversion function. Per ¶5, anything matching the pattern class name, `final`, `:` or `{` is always taken as the `final` specifier.

¶6 Naming a `final` class in a base-clause makes the program ill-formed:

```cpp title="final-base.cpp" error
struct H final { };
struct I : H { };       // error: H is final
```

`final` says the class is not designed for inheritance. It also helps the compiler devirtualize: a virtual call through a pointer or reference to a `final` class cannot have a more-derived overrider, so it can be called directly. Places in the standard library that derive from a user type to take advantage of the empty base optimization check `std::is_final` first and use member storage for `final` classes.

!!! impl "Devirtualization and `-Wsuggest-final-types`"
    GCC and Clang both take advantage of `final`: when the static type is `F*` (with `F` a `final` class), `p->vf()` calls the final overrider directly without consulting the vtable. GCC's `-Wsuggest-final-types` and `-Wsuggest-final-methods`, under LTO, suggest which types or functions would benefit from devirtualization if marked `final`.

## Complete objects have nonzero size (¶7)

```cpp run title="nonzero-size.cpp" ok
struct Empty { };
struct D : Empty { int x; };                         // a base class subobject can occupy no space
struct M { [[no_unique_address]] Empty e; int x; };  // likewise

static_assert(sizeof(Empty) >= 1);                   // complete objects have nonzero size
int main() { return sizeof(D) == sizeof(int) ? 0 : 1; }
```

¶7 This paragraph is a note: complete objects of class type have nonzero size. Base class subobjects and members declared with `[[no_unique_address]]` are not so constrained; they are potentially-overlapping subobjects ([[intro.object]]). The empty base optimization (EBO) rests on this.

A complete object cannot have zero size because distinct objects must have distinct addresses: the ten elements of `Empty a[10]` must be distinguishable, and pointer arithmetic `p + 1` also requires a nonzero element size. The standard does not guarantee that EBO happens; `sizeof(D) == sizeof(int)` is the actual behavior of the mainstream ABIs. MSVC ignores `[[no_unique_address]]` by default; you have to write `[[msvc::no_unique_address]]`.

## Every class definition introduces a new type [class.name]

```cpp title="distinct-types.cpp" error
struct X { int a; };
struct Y { int a; };

int f(X);
int f(Y);          // an overload, not a redeclaration

void g() {
    X a1;
    Y a2;
    a1 = a2;       // error: cannot assign Y to X
}

struct S { int a; };
struct S { int a; };   // error: S defined twice
```

[[class.name#1]] Every class definition introduces a new type. C++'s type system is nominal: two structurally identical classes are distinct types and can serve as parameter types of separate overloads.

Defining `S` twice in one translation unit is a redefinition error. Having an identical definition in each of several translation units is allowed; that is how a class definition in a header gets included into multiple source files. If the definitions differ, the ODR is violated ([[basic.def.odr]]).

### Naming a hidden class with `struct X`

```cpp run title="stat.cpp" ok
struct stat { int size; };

stat gstat;                        // here stat is only a class name and can be used directly

int stat(struct stat* p) { return p->size; }   // stat is now also a function name

int main() {
    struct stat s{42};             // struct is required: plain stat finds the function
    return stat(&s) - 42;          // calls the function stat
}
```

[[class.name#2]] C puts struct tags in a separate name space, so `struct stat` and the function `stat` don't interfere. C++ puts class names in the ordinary scope, but for C compatibility it allows the same name in the same scope to be both a class and a variable, function or enumerator. The ordinary name then hides the class name, and to name the class you must write the elaborated-type-specifier `struct stat`, which performs a lookup that considers only types ([[basic.lookup.elab]]). POSIX's `<sys/stat.h>` is exactly this case.

An elaborated-type-specifier can also declare a new class name. A `struct s;` in block scope introduces a local class that hides the outer class of the same name:

```cpp run title="local-redecl.cpp" ok
struct s { int a; };

void g() {
    struct s;                 // declares a local class s, hiding the global s
    s* p = nullptr;           // points to the local s
    struct s { char* q; };    // defines the local s
    struct s;                 // redeclaration, no effect
    (void)p;
}

int main() { g(); }
```

After the forward declaration `class Vector;`, `Matrix` can use `Vector` in a friend declaration, and the two classes can refer to each other.

[[class.name#3]] When used in an ordinary declaration, `struct s` can also refer to an existing class rather than introduce a new one:

```cpp run title="elab-refer.cpp" ok
struct s { int a; };

void g(int s) {
    struct s* p = new struct s;   // the global struct s (the parameter s hides the ordinary name)
    p->a = s;                     // the parameter s
    delete p;
}

int main() { g(1); }
```

!!! lawyer "Where the `struct Q*` in a parameter list is declared"
    For `void h(struct Q* q);`, if unqualified lookup does not find `Q`, `Q` is declared as a class name whose target scope is the nearest enclosing namespace or block scope ([[dcl.type.elab#3]]), not the parameter scope. So writing `Q* qq;` later in the same namespace is valid. C's rule is different: a struct tag declared this way is only in scope within the function prototype, and compilers often warn about it.

### A declaration takes effect right after its identifier

```cpp run title="class-A-star-A.cpp" ok
class A * A;     // first declares A as a class, then declares A as a pointer variable to an object of that class

int main() {
    class A* p = A;   // from here on the class can only be named as class A
    (void)p;
}
```

[[class.name#4]] The declaration of a class name takes effect immediately after the identifier is seen ([[basic.scope.pdecl]]). So once `class A` has been read, `A` is already a class name, and the `* A` in the same declaration then declares `A` as a variable. The standard itself says this style is confusing and best avoided.

[[class.name#5]] `T<...>` is a class name only when the template name names a class template. For an alias template `template<class T> using V = std::vector<T>;`, `V<int>` is a type name but not a class name, and cannot appear where a class name is required, such as the *class-head-name* of a class definition.

<details class="fine" markdown="1"><summary>Remaining wording</summary>

¶8 is a note: class objects can be assigned, passed as arguments and returned from functions, unless copying or moving has been deleted or is inaccessible ([[dcl.fct.def.delete]], [[class.access]]). Other operations such as equality comparison can be user-defined ([[over.oper]]) and, since C++20, defaulted with `= default` ([[class.compare]]).

</details>

!!! impl "ABI consequences of mixing struct and class"
    Writing `class X;` first and `struct X { };` later is well-formed; [[dcl.type.elab]] only forbids mixing `union` with non-`union`. Itanium ABI name mangling doesn't distinguish the two, but MSVC's mangled names do distinguish `struct` from `class`, and mixing them can cause link errors. Clang has the `-Wmismatched-tags` warning for this, MSVC has C4099.

## History

!!! history
    - C++98 already had the class definition syntax, the injected-class-name, and the elaborated-type-specifier rules for compatibility with C tag names; `struct` and `class` differed only in default access.
    - C++11 introduced the contextual keyword `final`, and attributes could be written on the *class-head*.
    - C++20 modules changed whether a class is complete from whether its definition precedes to whether its definition is reachable ([[module.reach]]; see [[class.mem.general#11]]).
    - During C++26 work, two class-property-specifiers related to trivial relocatability were added next to `final` ([[P2786]]) and later removed. In the current draft `final` is the only class-virt-specifier.

## Common misconceptions

!!! pitfall "A class is complete within its own definition"
    `struct T { char buf[sizeof(T)]; };` is ill-formed. Only complete-class contexts such as function bodies and default arguments treat the class as a complete type.

!!! pitfall "`struct X;` and `class X { }` can be mixed freely"
    Valid at the standard level, but it can cause link errors on MSVC. A class should use the same *class-key* throughout a codebase.

## Questions

!!! question "Question 1"
    What does each line below do? Is the whole program well-formed?

    ```cpp
    struct A { };
    struct B final : A { };
    struct C { struct D { constexpr operator int() const { return 3; } }; struct E final : D { }; };
    struct final { };
    struct F : final { };
    ```

<details markdown="1">
<summary>Answer</summary>

- `struct B final : A { };` defines the `final` class `B`, derived from `A`.
- `struct E final : D { };` matches the pattern class name, `final`, `:`, so per ¶5 it defines the `final` nested class `E`, not a bit-field of width `D{}`.
- `struct final { };` defines an ordinary class named `final`; `final` is not a reserved word.
- In `struct F : final { };` the `final` is preceded by `:`, not by a class name, so ¶5 doesn't apply: it is just the base class name.

The whole program is well-formed.
</details>

!!! question "Question 2"
    Why is the injected-class-name treated as a public member for access checking, rather than simply having no access at all?

<details markdown="1">
<summary>Answer</summary>

The injected-class-name is found by member name lookup ([[class.member.lookup]]), and whatever is found needs a definite access to be access-checked ([[class.access]]). Making it public means it is always accessible in the class itself and in publicly derived classes; it can become inaccessible only after non-public inheritance lowers the access ([[class.access.base]]). Private inheritance is meant to hide the derivation as an implementation detail, and that is exactly when the base class name should become inaccessible too.
</details>

!!! question "Question 3"
    Is `template<class T> struct Z { }; struct Z<int> { };` valid? What about `struct Y<int> { };` (where `Y` is not a template)?

<details markdown="1">
<summary>Answer</summary>

The class name in `struct Z<int> { };` is a *simple-template-id*, and per ¶1 such a declaration must be an explicit specialization or partial specialization. It lacks `template<>`, so it is ill-formed; it should be written `template<> struct Z<int> { };`.

In `struct Y<int> { };`, `Y` is not a template name, so `Y<int>` doesn't form a *simple-template-id* at all; it is a syntax error.
</details>
