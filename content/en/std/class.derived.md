---
title: Derived classes
summary: "How base classes are declared and which base class subobjects a derived object contains; what happens when the same base appears more than once under multiple inheritance, and how virtual bases merge those occurrences into one."
updated: 2026-10-19
---

!!! tldr
    - A derived class object embeds one subobject for each base class; converting a derived pointer to a base pointer means finding that subobject.
    - A base class must already be a complete type when it appears in a *base-clause*. The order in which subobjects are laid out in memory is unspecified and determined by the ABI.
    - The same class can't be a direct base twice, but it can be an indirect base several times; there are then several subobjects of the same type, and accessing their members requires qualifying the path.
    - Each occurrence of a non-virtual base corresponds to a separate subobject; a virtual base has only one subobject in the most derived object, no matter how many times it appears.
    - A class declared `final` can't be used as a base class.

This page covers structure only: how base classes are declared and which subobjects an object contains. For how base class members are looked up see [[class.member.lookup]], for whether they can be accessed see [[class.access.base]], for how they are initialized see [[class.base.init]], and for virtual functions see [[class.virtual]].

## What a derived class object contains [class.derived.general]

```cpp
struct Base     { int a, b, c; };
struct Derived  : Base    { int b; };
struct Derived2 : Derived { int c; };
```

¶3 The *base-specifier-list* (the list of bases after the colon) specifies the types of the **base class subobjects** contained in an object of the derived class. In the standard's example above, a `Derived2` object contains a `Derived` subobject, which in turn contains a `Base` subobject. Saying a `Derived` is a `Base` means, in the object model, that every `Derived` object contains a complete `Base` object.

¶2 A class written directly in the *base-clause* is a **direct base class**. Direct base classes, and the direct bases of base classes (recursively), are all **base classes**; a base class that is not a direct base is an **indirect base class**. In the example above, `Base` is an indirect base of `Derived2`.

¶2 goes on to say that the members of a base class are also members of the derived class. Note 2 summarizes the rules that follow: base class members can be used in expressions just like the derived class's own members, unless hidden or ambiguous ([[class.member.lookup]]); `::` can name a hidden base class member explicitly; a pointer to a derived class can be implicitly converted to a pointer to an accessible unambiguous base class ([[conv.ptr]]), and an lvalue of a derived class can be bound to a reference to such a base ([[dcl.init.ref]]); and base class constructors can be inherited with a using-declaration ([[namespace.udecl]]).

### Writing base-specifiers (¶1)

```text
base-specifier:
    attribute-specifier-seq(opt) class-or-decltype
    attribute-specifier-seq(opt) virtual access-specifier(opt) class-or-decltype
    attribute-specifier-seq(opt) access-specifier virtual(opt) class-or-decltype
class-or-decltype:
    nested-name-specifier(opt) type-name
    nested-name-specifier template simple-template-id
    computed-type-specifier
```

`virtual` and the access specifier (`public`, `protected`, `private`) can come in either order: `virtual public B` is the same as `public virtual B`. *computed-type-specifier* includes `decltype(...)`, pack indexing and splice type specifiers, so you can derive from `decltype(some lambda)`. Attributes at the start appertain to that *base-specifier*.

### The base class must be complete (¶2)

¶2 The *class-or-decltype* must denote a class type, and that class must not be one that is still being defined or only declared at that point; that is, it must be a complete type. The derived class's layout has to hold the whole base class subobject, so the compiler must know the base's size and members. cv-qualifiers on the base are ignored.

Lookup for a base class name considers only types (**type-only lookup**, [[basic.lookup]]); variables and functions with the same name are ignored.

```cpp title="base-requirements.cpp" error
struct Inc;
struct A : Inc {};              // error: Inc is incomplete
struct Self : Self {};          // error: Self isn't completely defined yet
struct X {};
using CX = const X;
struct W : CX {};               // OK: cv-qualifiers are ignored
int B;
struct B {};
struct D : B {};                // OK: only types are looked up; the variable B is ignored
```

Each *base-specifier* corresponds to a **direct base class relationship**, the ordered pair (D, B). In C++26 static reflection, `std::meta::bases_of` returns reflections of these relationships, and they can also be used in `obj.[: base :]` to name base class subobjects.

### Variadic bases (¶4)

¶4 A *base-specifier* followed by `...` is a pack expansion ([[temp.variadic]]), so a class can derive from each type in a pack. A common use is combining several lambdas into one overload set:

```cpp run title="overloaded.cpp" ok
#include <string>
#include <variant>

template<class... Fs>
struct overloaded : Fs... {        // each Fs is a direct base class
    using Fs::operator()...;       // brings each base's operator() into one scope
};

int main() {
    std::variant<int, std::string> v = 42;
    int r = std::visit(overloaded{
        [](int i) { return i; },
        [](const std::string& s) { return (int)s.size(); },
    }, v);
    return r == 42 ? 0 : 1;
}
```

`overloaded{...}` can be brace-initialized because since C++17 a class with base classes can be an aggregate; since C++20 it no longer needs a hand-written deduction guide either.

## Subobject layout (¶5–¶7)

¶5 The order in which base class subobjects are allocated in the [[g:most-derived-object|most derived object]] (the complete object that is not a subobject of any other object) is unspecified. The standard only guarantees that each base class subobject exists and can be found by conversion; its offset, and whether it comes before the derived class's own members, are up to the ABI. This is what lets implementations perform the empty base optimization and place virtual bases at the end of the object. When you need a predictable layout, look at the rules for standard-layout classes ([[class.prop]]).

Note 3 points out that a derived class and its base class subobjects can be drawn as a directed acyclic graph, with arrows meaning "directly derived from"; this graph is often called a **subobject lattice**. The arrows need not have a physical representation in memory.

¶7 Note 5 points out that a base class subobject can differ from a complete object of the same type in three ways:

- The layout may differ. For example, when a class with virtual bases is a subobject, its virtual bases are not necessarily next to it (see the implementation view below); the derived class's members may also be placed in the tail padding of a base class subobject.
- The polymorphic behavior may differ. During construction and destruction, a base class subobject behaves like the class being constructed or destroyed ([[class.cdtor]]).
- The size can be zero. An empty base class subobject can occupy no space; this is the empty base optimization (EBO). But two subobjects of the same type in the same most derived object can't have the same address ([[intro.object]]).

```cpp run title="ebo.cpp" ok
struct Empty {};
struct A : Empty { int x; };
struct B : Empty { Empty e; int x; };   // the base and member e are both Empty

static_assert(sizeof(A) == sizeof(int));  // all mainstream ABIs do the empty base optimization
int main() {
    B b;
    // the two Empty subobjects can't share an address
    return (void*)static_cast<Empty*>(&b) != (void*)&b.e ? 0 : 1;
}
```

The standard doesn't require `sizeof(A) == sizeof(int)`; it only allows an empty base class subobject to have zero size. But all mainstream ABIs do this.

¶6 Note 4 points out that how base class subobjects are initialized is specified by constructors; see [[class.base.init]].

## Multiple base classes [class.mi]

¶1 A class can have any number of base classes. Having several direct base classes is usually called **multiple inheritance**.

¶2 Note 2 points out that the order in which bases are written is generally insignificant; it affects only three things: the order of construction (the order of the *base-specifier*s, [[class.base.init]]), the order of destruction (the reverse), and the storage layout.

### The same base class appearing more than once (¶3)

¶3 The same class can't be a direct base class twice, since there would be no way to tell the two subobjects apart by name. But it can be an indirect base class several times, or both a direct and an indirect base. Note 3 says there is little you can do with it then: looking up its non-static members in the derived class is ambiguous, and only static members, enumerators and types can be referred to unambiguously, since they don't belong to a particular subobject.

```cpp title="mi-basics.cpp" error
class X {};
class Y : public X, public X {};    // error: X is a direct base twice

class L { public: int next; static int count; using T = int; };
class A : public L {};
class B : public L {};
class C : public A, public B {      // OK: L appears twice as an indirect base
    void f() {
        next = 0;                   // error: ambiguous, which L?
        A::next = B::next;          // OK: qualification specifies the path
        count = 1;                  // OK: static member
        T t = 0; (void)t;           // OK: type
    }
};
class D : public A, public L {};    // OK, but this direct base L is nearly unusable
```

The last line is valid; Clang only gives a warning that the direct base `L` is inaccessible due to ambiguity. The conversion from `D*` to `L*` has two targets (the `L` in `A` and the direct `L`), so it is ambiguous; writing `L::next` doesn't help either, because the qualifier `L` finds the injected-class-name, which still corresponds to two subobjects.

### Virtual base classes (¶4–¶7)

¶4 A base class specifier without `virtual` specifies a **non-virtual base class**, and one with `virtual` specifies a **virtual base class**. The difference is in the number of subobjects:

!!! std
    For each distinct base class that is specified virtual, the most derived object shall contain a single base class subobject of that type.

Each time a non-virtual base occurs in the class lattice, the most derived object contains a separate corresponding subobject; a virtual base, however many times it occurs, has only one subobject in the most derived object, shared by every subobject that has it as a virtual base. The notes in ¶5 and ¶6 contrast the two cases using the classic diamond:

```cpp run title="diamond.cpp" ok
#include <cassert>

struct L { int next = 0; };
struct A1 : L {};
struct B1 : L {};
struct C1 : A1, B1 {};               // two Ls

struct V { int v = 0; };
struct A2 : virtual V {};
struct B2 : virtual V {};
struct C2 : A2, B2 {};               // one V

int main() {
    C1 c1;
    c1.A1::next = 1;
    c1.B1::next = 2;
    assert(c1.A1::next != c1.B1::next);   // two separate subobjects
    // L* pl = &c1;                       // error: ambiguous
    L* pl = static_cast<A1*>(&c1);        // OK: pick a path first
    (void)pl;

    C2 c2;
    c2.v = 5;                             // OK: there is only one V
    V* pv = &c2;                          // OK
    assert(&static_cast<A2&>(c2).v == &static_cast<B2&>(c2).v);
    assert(pv == static_cast<V*>(static_cast<B2*>(&c2)));
}
```

This rule is stated relative to the most derived object: who shares a virtual base subobject can only be decided in the final complete object. A standalone `A2` object has its own `V`; as part of a `C2`, its `V` and `B2`'s `V` are the same one. Two consequences follow: virtual bases are initialized by the most derived class ([[class.base.init]]), and the location of a virtual base subobject has to be looked up at run time.

¶7 Note 6 points out that the same class can be both a virtual and a non-virtual base. All the virtual occurrences merge into one subobject, and each non-virtual occurrence has its own:

```cpp run title="virt-nonvirt.cpp" ok
struct B { int id = 0; };
struct X : virtual B {};
struct Y : virtual B {};
struct Z : B {};
struct AA : X, Y, Z {};     // two Bs: the virtual B shared by X and Y, and Z's own B

int main() {
    AA aa;
    B& shared = static_cast<X&>(aa);
    B& own    = static_cast<Z&>(aa);
    return &shared != &own ? 0 : 1;
}
```

## final classes

[[class.pre#6]] says that if a class marked `final` appears in a *base-clause*, the program is ill-formed.

```cpp title="final-class.cpp" error
struct F final {};
struct G : F {};          // error: F is final
```

`final` says, on the one hand, that the class isn't designed for inheritance, and on the other lets the compiler devirtualize: when a virtual function is called through an `F&`, the dynamic type can only be `F`, so it can be called directly (see [[class.virtual]]).

## Implementation view

!!! impl "Itanium C++ ABI layout (GCC and Clang on Linux and macOS)"
    - Non-virtual bases are placed at the start of the object in declaration order. The first non-virtual base with a vtable pointer is the **primary base**, which shares the vtable pointer and offset 0 with the derived class.
    - Virtual bases are placed at the end of the object, after all non-virtual parts. Their offset varies with the most derived type, so accessing a virtual base requires reading the offset from the vtable.
    - Clang 23 with `-Xclang -fdump-record-layouts` prints the layout of `D` in `struct V { int v; virtual void h(); }; struct A : virtual V { int a; }; struct B : virtual V { int b; }; struct D : A, B { int d; };`:

    ```text
             0 | struct D
             0 |   struct A (primary base)
             0 |     (A vtable pointer)
             8 |     int a
            16 |   struct B (base)
            16 |     (B vtable pointer)
            24 |     int b
            28 |   int d
            32 |   struct V (virtual base)
            32 |     (V vtable pointer)
            40 |     int v
               | [sizeof=48, dsize=44, align=8,
               |  nvsize=32, nvalign=8]
    ```

    `V` is at offset 32; in a standalone `A` object, `V` follows right after `A`'s non-virtual part, at offset 16. This is what ¶7 means when it says a subobject's layout can differ from a complete object's.

    - MSVC uses a different scheme: a subobject with virtual bases stores a separate pointer to a table of virtual base offsets (the vbptr), apart from the vtable pointer.
    - The Itanium ABI always performs the empty base optimization. Under multiple inheritance MSVC by default applies EBO only to some empty bases; `__declspec(empty_bases)` makes it apply to all of them.

## History

!!! history
    - Multiple inheritance and virtual bases existed before C++ was standardized, and the structure of this subclause has changed little since C++98.
    - C++11: base-specifiers can be pack expansions and `decltype`; `final` and inheriting constructors were introduced.
    - C++17: classes with base classes can be aggregates, which makes forms like `overloaded{...}` possible; the semantics of inheriting constructors were reworded.
    - C++26: *computed-type-specifier* extended to pack indexing and splice type specifiers; direct base class relationships can be reflected.

## Common misconceptions

!!! pitfall "Virtual inheritance solves the diamond problem, so always use it"
    Virtual bases have costs: access goes through a table lookup, objects are bigger, and the most derived class must be able to access the virtual base and is responsible for initializing it. A *mem-initializer* written for a virtual base by an intermediate class is ignored when the most derived object is constructed ([[class.base.init]]); only the one written by the most derived class takes effect. Use them only when you really need to share a single subobject.

!!! pitfall "Base class subobjects always come before the derived class's members"
    The standard doesn't guarantee this. The mainstream ABIs do lay things out that way, but the only portable guarantees are those for standard-layout classes.

!!! pitfall "The direct base L in `D : A, L` (with `A : L`) is usable as normal"
    It is valid, but almost unusable: conversions and member accesses are ambiguous.

## Questions

!!! question "Question 1"
    Is `struct A {}; struct B : A {}; struct C : A, B {};` valid? How many `A` subobjects does `C` have? Can a `C*` be converted to an `A*`?

<details markdown="1">
<summary>Answer</summary>

Valid. ¶3 only forbids the same class being a direct base twice, and here `A` is once a direct base and once an indirect base. `C` has two `A` subobjects, so the conversion from `C*` to `A*` is ambiguous. To get the `A` inside `B`, convert to `B*` first; the `A` that is a direct base has no unambiguous way to be named at all, which is why Clang warns that this direct base is inaccessible.
</details>

!!! question "Question 2"
    In `struct V {}; struct A : virtual V {}; struct B : virtual V {}; struct C : A, B {}; struct D : C, virtual V {};`, how many `V` subobjects does a `D` object have? What if `D` is written `struct D : C, V {}`?

<details markdown="1">
<summary>Answer</summary>

In the first case, one. By ¶4, a virtual base has only one subobject in the most derived object, and the three occurrences of `virtual V` in `A`, `B` and `D` all correspond to it. In the second case, two: the shared virtual `V`, plus the non-virtual `V` that `D` owns directly.
</details>
