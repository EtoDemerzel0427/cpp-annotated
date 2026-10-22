---
title: The using declaration
summary: "A using-declaration binds the result of one qualified lookup to a name in the current scope; it is used to bring in namespace members, bring base class members into a derived class and change their access, and inherit constructors."
updated: 2026-10-19
---

!!! tldr
    - `using N::f;` makes `f` in the current scope denote the set of declarations that looking up `f` in `N` finds at this point. Overloads added to `N` later aren't seen.
    - In a class, a using-declaration can only name base class members or enumerators. It merges the base class's whole overload set into the derived class, and a function the derived class declares itself with the same signature hides or overrides the corresponding one.
    - The access section a using-declaration appears in determines the new name's access; that's why `public: using Base::g;` can make a protected member public. Every declaration named must be accessible.
    - `using Base::Base;` inherits constructors: the base class's constructors take part in constructing the derived class, and the derived class's other members are initialized by default.
    - Class members (other than enumerators) can't be brought in by a using-declaration outside the class, static members included.

## What it does

```cpp run title="udecl-snapshot.cpp" ok
#include <cstdio>

namespace A {
    void f(int) { std::puts("f(int)"); }
}

using A::f;              // f is a synonym for A::f(int)

namespace A {
    void f(char) { std::puts("f(char)"); }
}

void foo() {
    f('a');              // f(int): f(char) didn't exist at the using-declaration
}
void bar() {
    using A::f;          // by now A::f(int) and A::f(char) are both declared
    f('a');              // f(char)
}
int main() { foo(); bar(); }
```

A **[[g:using-declaration|using-declaration]]** `using A::f;` introduces the name `f` into the current scope. When a later lookup of `f` finds this using-declaration, it is replaced by the set of declarations it names (Note 1 in paragraph 2).

¶9 That set is fixed at the point of the using-declaration. The `f` in `foo` can only find `A::f(int)`, even though `A::f(char)` exists at the time of the call. Default arguments, default template arguments and template specializations are exceptions: ones added later are considered too, because they aren't new declarations but attach to existing entities.

This is exactly the difference from a using-directive `using namespace A;`: a using-directive introduces no names and only changes the lookup path, so it always sees later declarations ([[namespace.udir]]). A comparison table of the two is in [[basic.namespace]].

A using-declaration has three main uses:

1. Bringing in namespace members, e.g. `using std::swap;`;
2. Bringing base class members into a derived class, to undo name hiding or change access;
3. Inheriting constructors, `using Base::Base;`.

It can also bring in enumerators, and `using enum` ([[enum]]) is built on this mechanism.

## Syntax and the declarations named (¶1)

```text
using-declaration:      using using-declarator-list ;
using-declarator-list:  using-declarator ...(opt)
                      | using-declarator-list , using-declarator ...(opt)
using-declarator:       typename(opt) nested-name-specifier unqualified-id
```

The *nested-name-specifier* is not optional: a using-declaration is always qualified, and bringing in a global name is written `using ::x;`. Since C++17 one using-declaration can have several declarators, `using A::x, B::y;` being equivalent to writing them one by one (footnote 77), and a declarator can be followed by `...` for a pack expansion ([[P0195R2]]).

¶1 Each declarator names the set of declarations found by qualified name lookup of it ([[basic.lookup.qual]]), with only three adjustments:

- Within one scope, a variable or function hides a class or enumeration of the same name, and ordinary lookup drops the hidden class. A using-declaration doesn't drop it, only ignores it when checking for ambiguity, so the hidden class name comes along too (see `struct g` in the section on conflicts below).
- Conversion function templates with a dependent return type are ignored.
- A corresponding function in the derived class hides the base class function; see paragraph 11.

To bring in a dependent type name in a template, write `typename` before the declarator ([[temp.res]]):

```cpp title="udecl-typename.cpp" ok
template<class T>
struct Derived : T {
    using typename T::value_type;   // dependent type name
    using T::get;                   // dependent non-type member
    value_type v{};
};

struct Base { using value_type = int; int get() const { return 1; } };

int main() { Derived<Base> d; return d.get() - 1 + d.v; }
```

## Conflicts within a scope (¶10)

¶10 has two rules, both based on declarations that [[basic.scope.scope|potentially conflict]]. Intuitively, two declarations potentially conflict if they introduce the same name in the same scope and are neither redeclarations of the same entity nor overloads that can coexist.

First: if a declaration named by a using-declaration potentially conflicts with another declaration B in the scope of the using-declaration, and either is reachable from the other, the program is ill-formed. The only exception is C++26's name-independent declaration `_` ([[P2169R4]]): B is a name-independent declaration and the using-declaration precedes B.

```cpp title="udecl-name-independent.cpp" error
int _;
void f() {
    int _;          // B: a name-independent declaration
    _ = 0;
    using ::_;      // error: the using-declaration doesn't precede B
}
void g() {
    using ::_;      // OK: precedes B
    int _;          // OK: a name-independent declaration can coexist with it
}
```

Second: if the declarations named by two using-declarations in the same scope potentially conflict, are reachable from each other, and are not all functions or function templates, the program is ill-formed. If they are all functions, the using-declarations themselves are fine; it's just that overload resolution may not be able to tell them apart (Note 5).

Example 8 in the standard puts all these cases together:

```cpp title="udecl-conflicts.cpp" error
namespace A {
    int x;
    int f(int);
    int g;
    void h();
}
namespace B {
    int i;
    struct g { };
    struct x { };
    void f(int);
    void f(double);
    void g(char);                     // OK: hides struct g
}

void func() {
    int i;
    using B::i;                       // error: conflicts with the local variable i
    void f(char);
    using B::f;                       // OK: all functions
    using A::f;                       // OK, but has the same signature as B::f(int)
    f(1);                             // error: ambiguous
    static_cast<int(*)(int)>(f)(1);   // OK: calls A::f
    f(3.5);                           // OK: B::f(double)
    using B::g;
    g('a');                           // OK: B::g(char)
    struct g g1;                      // OK: g1 has type B::g
    using A::g;                       // error: conflicts with B::g
    void h();
    using A::h;                       // error: conflicts with the locally declared h
    using B::x;
    using A::x;                       // OK: the variable A::x hides struct B::x
    using A::x;                       // OK: names the same declaration again
    x = 99;                           // assigns to A::x
    struct x x1;                      // x1 has type B::x
}
```

- `using B::g;` brings both the function `B::g(char)` and the class `B::g` it hides. Afterwards `g('a')` finds the function and `struct g` finds the class.
- `void h();` declares the global `::h`, while `using A::h;` names `A::h`. They have the same signature but are different entities, so they conflict.
- At block and namespace scope the same using-declaration can be repeated, like the two `using A::x;` here. Not at class scope; see paragraph 8 below.

## Use in classes

### Only base class members or enumerators (¶3)

```cpp title="udecl-member.cpp" error
enum class button { up, down };

struct B {
    void f(char);
    enum E { e };
    union { int x; };
};
struct C { int f(); };

struct S {
    using button::up;         // OK (C++20): an enumerator need not come from a base class
    button b = up;
};

struct D : B {
    using B::f;               // OK: B is a base of D
    using B::e;               // OK: an enumerator of the base B
    using B::x;               // OK: an anonymous union member of the base B
    using C::f;               // error: C is not a base of D
    void f(int) { f('c'); }   // calls B::f(char)
    void g(int) { g('c'); }   // recursively calls D::g(int)
};

template<typename... bases>
struct X : bases... {
    using bases::f...;        // C++17: pack expansion
};
X<B, C> xx;                   // OK: names B::f and C::f
```

¶3 In a using-declaration that is a class member, each declarator either names an enumerator or has a *nested-name-specifier* that names a base class of the current class. If it names a constructor, it must be a direct base. In a class template, the class must be derived from the specified base, or have at least one dependent base, in which case the check is deferred until instantiation.

The `f('c')` in `D::f(int)` calls `B::f(char)`. Without `using B::f;`, `D::f` would hide all functions named `f` in the base class ([[class.member.lookup]]), and `f('c')` could only convert `'c'` to `int` and call `D::f(int)`. That's what happens with `g`.

### Class members can only be brought in inside the class (¶7)

¶7 A using-declaration that names a class member (other than an enumerator) must be a member-declaration. Writing `using X::s;` at block or namespace scope is ill-formed, even if `s` is a static member:

```cpp title="udecl-class-member-outside.cpp" error
struct X {
    int i;
    static int s;
    enum { e };
};

void f() {
    using X::i;    // error: a class member, and this is not a member-declaration
    using X::s;    // error: not even static members
    using X::e;    // OK: the enumerator exception
}
```

If you want a short name, use a reference instead, e.g. `auto& s = X::s;`.

### Other restrictions (¶4–¶6, ¶8)

¶5 A using-declaration can't name a *template-id*. It introduces a name, and bringing in a template brings all its specializations along:

```cpp title="udecl-template-id.cpp" error
struct A {
    template<class T> void f(T);
    template<class T> struct X { };
};
struct B : A {
    using A::f<double>;   // error
    using A::X<int>;      // error
    using A::f;           // OK: brings in the whole function template
};
```

¶6 A using-declaration can't name a namespace; that's what namespace aliases and using-directives are for ([[basic.namespace]]). Note 2 in paragraph 4 points out that destructors have no names, so a using-declaration can't refer to a base class destructor either.

¶8 If the same declaration is named by two declarators in the same class scope, the program is ill-formed:

```cpp title="udecl-duplicate.cpp" error
struct C { int i; };
struct D1 : C { };
struct D2 : C { };

struct D3 : D1, D2 {
    using D1::i;     // OK: equivalent to using C::i
    using D1::i;     // error: duplicate
    using D2::i;     // error: duplicate, it also names C::i
};
```

!!! impl "Clang's deviation"
    Clang 23 only diagnoses the second line `using D1::i;` and accepts the third line `using D2::i;`. By paragraph 8, `D2::i` finds the same declaration `C::i` and should be ill-formed.

¶4 Note 3: a using-declaration naming a base class member function doesn't suppress the implicit declaration of the derived class's special member functions, even with the same signature. After `using Base::operator=;`, the derived class still has its own copy assignment operator:

```cpp run title="udecl-special-members.cpp" ok
#include <cstdio>

struct Base {
    Base& operator=(const Base&) { std::puts("Base::operator=(const Base&)"); return *this; }
    Base& operator=(int) { std::puts("Base::operator=(int)"); return *this; }
};
struct Derived : Base {
    using Base::operator=;    // both Base::operator= are brought in
};

int main() {
    Derived d1, d2;
    d1 = 5;                   // Base::operator=(int)
    d1 = d2;                  // Derived's implicit copy assignment, which in turn calls Base::operator=
}
```

The candidates for `d1 = d2` include `Derived::operator=(const Derived&)` and the brought-in `Base::operator=(const Base&)`. The former is an exact match, the latter needs a derived-to-base conversion, so the former is chosen. The program's two lines of output come from `operator=(int)` and from the base class call inside the implicit copy assignment.

## The derived class's declarations take precedence (¶11, ¶12)

```cpp run title="udecl-hide-override.cpp" ok
#include <cstdio>

struct B {
    virtual void f(int)  { std::puts("B::f(int)"); }
    virtual void f(char) { std::puts("B::f(char)"); }
    void g(int)  { std::puts("B::g(int)"); }
    void h(int)  { std::puts("B::h(int)"); }
    void i()     { std::puts("B::i()"); }
    void j()     { std::puts("B::j()"); }
};

struct D : B {
    using B::f;
    void f(int) override { std::puts("D::f(int)"); }   // overrides B::f(int)
    using B::g;
    void g(char) { std::puts("D::g(char)"); }          // a new overload
    using B::h;
    void h(int) { std::puts("D::h(int)"); }            // hides B::h(int)
    using B::i;
    void i(this B&) { std::puts("D::i(this B&)"); }    // doesn't correspond to B::i
    using B::j;
    void j(this D&) { std::puts("D::j(this D&)"); }    // corresponds to B::j and hides it
};

int main() {
    D d; D* p = &d;
    p->f(1);     // D::f(int)
    p->f('a');   // B::f(char)
    p->g(1);     // B::g(int)
    p->g('a');   // D::g(char)
    p->i();      // per the standard: B::i(); Clang 23 actually calls D::i
    p->j();      // D::j(this D&)
}
```

¶11 The set named by a using-declaration in a derived class C excludes any base class member function that, considered as a member of C, **corresponds** ([[basic.scope.scope]]) to a function declared in C itself, i.e. has the same name, parameter-type-list, cv-qualifiers and ref-qualifier. So a derived class function with the same signature hides the base class version (overrides it, if virtual), and the two don't conflict.

¶12 Note 6: when building the set of overload candidates, functions brought in by a using-declaration are treated as direct members of the derived class, and their implicit object parameter is taken to be a reference to the derived class rather than to the base class ([[over.match.funcs]]). The function's type doesn't change, and in other respects it is still a member of the base class; for example, the type of `&D::g` is `void (B::*)(int)`.

If the implicit object parameter stayed `B&`, the derived class's own members would always be better matches on the object argument, the brought-in functions would always be at a disadvantage, and merging them into the same overload set would be pointless.

The `i` and `j` lines show how these two paragraphs interact with C++23 explicit object parameters ([[dcl.fct]]). `B::j`, considered as a member of D, has object parameter `D&`, which corresponds to `j(this D&)`, so it is hidden. `B::i` doesn't correspond to `i(this B&)`, so both are candidates. By paragraph 12, the object parameter of `B::i` is taken to be `D&`, an identity conversion for a `D` lvalue; `D::i` needs a derived-to-base conversion, so Example 9 in the standard says `B::i` is called.

!!! impl "Clang disagrees with the standard's example"
    Running the program above with Clang 23, `p->i()` prints `D::i(this B&)`, which doesn't match Example 9 in the standard.

## Access control (¶14, ¶16)

```cpp title="udecl-access.cpp" error
class A {
private:
    void f(char);
public:
    void f(int);
protected:
    void g();
};

class B : public A {
    using A::f;       // error: A::f(char) is inaccessible
public:
    using A::g;       // OK: B::g is a public synonym for A::g
};
```

¶14 When not naming a constructor, every declaration named by a declarator must be accessible. `using A::f;` names the whole overload set `{f(char), f(int)}`, of which `f(char)` is private, and a using-declaration can't pick just one of them.

¶16 Like any other member declaration, a using-declaration has the access of the section it is in. This is the basis for using it to change access: making a protected member public (the `g` above), or selectively exposing part of the interface under private inheritance:

```cpp run title="udecl-private-inherit.cpp" ok
#include <vector>

class Stack : private std::vector<int> {
public:
    using vector::push_back;     // expose only the interface needed
    using vector::back;
    using vector::pop_back;
    using vector::empty;
    using vector::size;
};

int main() {
    Stack s;
    s.push_back(1);
    s.push_back(2);
    s.pop_back();
    return s.back() == 1 ? 0 : 1;
    // s.begin();   // error: begin is still privately inherited
}
```

## It can't resolve inheritance ambiguity (¶15)

¶15 Note 8: a declarator refers to a member of a base class, not to a member of a particular base class subobject, so a using-declaration can't be used to resolve the ambiguity caused by repeated inheritance:

```cpp title="udecl-ambiguous-base.cpp" error
struct A { int x(); };
struct B : A { };
struct C : A {
    using A::x;
    int x(int);
};

struct D : B, C {
    using C::x;
    int x(double);
};

int f(D* d) {
    return d->x();   // error: overload resolution selects A::x, but A is an ambiguous base of D
}
```

`using C::x;` brings `A::x()` and `C::x(int)` into D, and overload resolution selects `A::x()`. Calling it requires converting `D*` to `A*`, but D has two A subobjects, one via B and one via C, so the conversion is ambiguous ([[conv.ptr]]). A using-declaration has no way to say "the A via C".

## Inheriting constructors (¶2, ¶13, ¶1)

```cpp run title="inherit-ctor.cpp" ok
#include <string>
#include <cstdio>

struct Base {
    Base(int n) : s(std::to_string(n)) {}
    Base(const char* p) : s(p) {}
    std::string s;
};

struct Derived : Base {
    using Base::Base;      // inherits Base(int) and Base(const char*)
    int extra = 42;        // initialized by its default member initializer
};

int main() {
    Derived a(7), b("hi");
    std::printf("%s %s %d\n", a.s.c_str(), b.s.c_str(), a.extra);   // 7 hi 42
}
```

¶2 If a declarator names a constructor, the using-declaration declares that the current class **inherits** that set of base class constructors. Paragraph 13 says that when looking up the derived class's constructors ([[class.qual]]) or building the candidate set for construction ([[over.match.ctor]] etc.), these constructors are treated as constructors of the derived class.

When an inherited constructor is selected, the base it came from is initialized with it, and the other bases and members are implicitly initialized by default ([[class.inhctor.init]]). If the other subobjects can't be default-initialized, the constructor is deleted:

```cpp title="inherit-ctor-deleted.cpp" error
struct P { P(int) {} };
struct Q { Q(const char*) {} };

template<class... Bs>
struct M : Bs... {
    using Bs::Bs...;       // C++17: inherits the constructors of all bases
};

M<P, Q> m(1);              // error: selects P(int), but Q can't be default-initialized, so the constructor is deleted
```

If the derived class declares a constructor with the same signature itself, it hides the inherited version per paragraph 11. If two bases provide constructors with the same signature, using them directly is ambiguous:

```cpp title="udecl-ctor-ambiguity.cpp" error
struct B1 { B1(int); };
struct B2 { B2(int); };

struct D1 : B1, B2 {
    using B1::B1;
    using B2::B2;
};
D1 d1(0);           // error: ambiguous, B1(int) or B2(int)?

struct D2 : B1, B2 {
    using B1::B1;
    using B2::B2;
    D2(int);        // OK: hides B1(int) and B2(int)
};
D2 d2(0);           // OK: calls D2::D2(int)
```

Access control has separate rules for constructors. Paragraph 14 says no access check is done when naming constructors; otherwise a single private constructor in the base would make the whole set uninheritable. Paragraph 16 says an inherited constructor's accessibility is the same as when using it to construct an object of the base class; the section the using-declaration is in is ignored:

```cpp title="inherit-ctor-access.cpp" error
class Base3 { protected: Base3(int) {} };
struct Der3 : Base3 {
    using Base3::Base3;   // being in a public section doesn't make it public
};
Der3 d3(1);               // error: constructing the base with Base3(int) is inaccessible here
```

The second half of ¶1 handles the template case. When the terminal name (the last component name) of a declarator is dependent, the compiler can't tell at template definition time whether it names a constructor. The rule: it is taken to name a constructor if and only if the terminal name of the *nested-name-specifier* is the same as the *unqualified-id*, i.e. forms like `using T::T;` and `using Base<U>::Base;`. If instantiation shows the guess was wrong, the program is ill-formed:

```cpp title="udecl-dependent-ctor.cpp" error
struct Base { Base(int) {} Base() {} };

template<class T> struct X : T { using T::T; };      // taken to name a constructor
X<Base> x(1);                                         // OK

template<class T> struct W : T { using T::Base; };   // T differs from Base: not taken as a constructor
W<Base> w;    // error: after instantiation Base::Base names the constructor
```

Clang 23 also rejects `W<Base>`, but diagnoses it from a different angle: it reports that the dependent using-declaration resolved to a type (the injected-class-name of `Base`) without `typename`.

## History

!!! history
    - C++98 already had using-declarations, including bringing base class members into a class and changing their access.
    - C++11 added inheriting constructors. The original semantics implicitly declared a corresponding set of constructors in the derived class, which had many problems with default arguments, variadic constructors and so on.
    - C++17 redefined inheriting constructors ([[P0136R1]]): instead of generating constructor declarations in the derived class, the base class constructors are treated as derived class constructors for lookup and overload resolution. The same year added multiple declarators and pack expansion ([[P0195R2]]).
    - C++20 allowed using-declarations to name enumerators not belonging to a base class, and added `using enum` ([[P1099R5]]).
    - C++26 added the name-independent declaration `_` ([[P2169R4]]), the source of the exception in paragraph 10.

## Common misconceptions

!!! pitfall "A using-declaration updates automatically as overloads are added"
    It doesn't. An `f` added to `A` after `using A::f;` is invisible to it (paragraph 9). If a header writes the using-declaration first and then includes another header that extends `A::f`, whether the new overload can be called depends on include order.

!!! pitfall "You can expose just one overload of a base class"
    You can't. A using-declaration always brings in the whole overload set, and every member of it must be accessible (paragraph 14). To expose just one, write a forwarding function.

!!! pitfall "Inheriting constructors initializes the derived class's own members"
    Apart from the base the constructor comes from, all other subobjects are initialized by default ([[class.inhctor.init]]). A new `int` member of the derived class without a default member initializer reads as an indeterminate value; since C++26, an erroneous value.

## Questions

!!! question "Question 1"
    Which of the following lines are well-formed? Which function does `f(1.5)` call?

    ```cpp
    namespace N { void f(int); }
    using N::f;
    namespace N { void f(double); }
    void g() { f(1.5); }

    struct S { static int s; };
    using S::s;
    ```

<details markdown="1">
<summary>Answer</summary>

- `f(1.5)` is well-formed, but calls `N::f(int)`, converting `1.5` to `int`. The using-declaration only names the `f(int)` that existed at its point (paragraph 9).
- `using S::s;` is ill-formed. A using-declaration naming a class member (other than an enumerator) must be a member-declaration (paragraph 7), static members included.
</details>

!!! question "Question 2"
    In `struct B { void f(); }; struct D : B { using B::f; void f(); };`, what is the relationship between D's `f` and `B::f`? What if D's declaration is changed to `void f() const;`?

<details markdown="1">
<summary>Answer</summary>

First case: `B::f`, considered as a member of D, corresponds to `D::f()`, so by paragraph 11 it is not in the set named by the using-declaration; that is, it is hidden by `D::f`. The two neither conflict nor are redeclarations of the same function.

Second case: `f() const` differs from `B::f()` in cv-qualification, so they don't correspond, and both are in the overload set. Calling `f()` on a non-const `D` object selects `B::f`, because its object parameter is taken to be `D&` (paragraph 12), which is better than `const D&`; calling it on a const object selects `D::f() const`.
</details>
