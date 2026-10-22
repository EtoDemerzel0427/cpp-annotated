---
title: Member access control
summary: "public, protected and private control where a member may be named; access is checked after name lookup and overload resolution; how the kind of inheritance, accessible base classes and the designating class decide whether an access is valid; and the access rules for virtual functions, multiple paths and nested classes."
updated: 2026-10-19
---

!!! tldr
    - Access control is about whether a member's name can be written (the member named) at a given point, not about whether the entity itself can be used; private entities can be reached through references, pointers, `auto` and templates.
    - The compiler first performs name lookup and overload resolution without regard to access, then checks whether what was selected is accessible; if not, it is an error, and no other overload is chosen instead.
    - The kind of inheritance caps the access that base class members have in the derived class, and also decides whether a derived class pointer can be implicitly converted to a base class pointer.
    - Access to a virtual function is checked against the static type of the call expression: an overriding function that is private can still be called through the base class, which is what the non-virtual interface idiom is built on.
    - Names in explicit instantiations aren't access-checked, and in C++26 neither are members named by a splice; these are two legitimate back doors.

```cpp run title="names-not-entities.cpp" ok
class Vault {
    int secret = 42;
public:
    int& door() { return secret; }   // hands out a reference
};
int main() {
    Vault v;
    int& r = v.door();   // OK: the name secret is not written outside the class
    r = 7;               // OK: modifies the entity; access control doesn't care
    // v.secret = 7;     // error: secret is private
}
```

`secret` is a private member, yet `main` changes its value anyway. Access control checks names: it specifies where in the program a member may be **named**, that is, where a name or expression referring to it may be written. Using the entity after getting a reference to it has nothing to do with access control.

So access control is not a security mechanism. It guards against code accidentally depending on implementation details, not against deliberate circumvention. This page covers everything in 11.8 except friends ([[class.friend]]) and the additional rules for protected members ([[class.protected]]).

## The three kinds of access ([class.access.general] ¶1–¶3)

¶1 A member of a class can be:

- ¶1.1 **private**: it can be named only by members and friends of the class in which it is declared;
- ¶1.2 **protected**: in addition to those two, it can be named by classes derived from that class and their friends, with additional restrictions in [[class.protected]];
- ¶1.3 **public**: it can be named anywhere.

Note 1 says that although constructors and destructors don't have names, expressions can still name them ([[basic.def.odr]]), so they are subject to access control as well. That's what lets a private constructor prevent outside code from creating objects.

¶2 A member of a class can access everything the class has access to. A local class of a member function can access the members that the member function itself can access. Footnote 89 sums up that access is transitive and additive for nested and local classes:

```cpp run title="nested-access.cpp" ok
class Outer {
    int x = 1;
    class Inner {               // a nested class is a member and has a member's access
        int peek(Outer& o) { return o.x; }
        struct Deeper {         // one more level of nesting works too
            int peek(Outer& o) { return o.x; }
        };
    };
public:
    int f() {
        struct Local {          // local class: gets f's access
            static int get(Outer& o) { return o.x; }
        };
        return Local::get(*this);
    }
};
int main() { Outer o; return o.f() == 1 ? 0 : 1; }
```

¶3 Members of a class defined with `class` are private by default; members of one defined with `struct` or `union` are public by default. In the language, `class` and `struct` differ only here and in the default kind of inheritance (see below).

## Access specifiers ([class.access.spec])

¶1–¶2 The access specifiers `public:`, `protected:` and `private:` apply to the members that follow, until the end of the class or the next access specifier. They can appear any number of times, in any order.

¶3 When a member is redeclared within its class, the access must be the same as in its first declaration:

```cpp title="redeclare-access.cpp" error
struct S {
    class A;
    enum E : int;
private:
    class A { };            // error: can't change the access
    enum E : int { e0 };    // error: can't change the access
};
```

¶4 (a note) warns about an easy trap. Looking up a base class's name in a derived class finds the base's [[g:injected-class-name|injected-class-name]], the binding of the class name in the class's own scope. It is inherited as a member of the base, and its access changes with the kind of inheritance, so it may be less accessible than the class name in the global scope:

```cpp title="injected-class-name-access.cpp" error
class A { };
class B : private A { };
class C : public B {
    A* p;      // error: finds the injected-class-name inherited via private inheritance
    ::A* q;    // OK: the A in the global scope
};
```

## Interpretation first, then access (¶4–¶5)

```cpp title="access-after-overload.cpp" error
struct S {
    void f(int);
private:
    void f(double);
};
void g(S* sp) {
    sp->f(2);      // OK: selects the public f(int)
    sp->f(2.0);    // error: selects the private f(double)
}
```

In the second call, the private `f(double)` doesn't drop out of the candidates. Overload resolution selects it (an exact match), then the access check fails and the program is ill-formed. The compiler doesn't fall back to `f(int)`.

!!! std
    The interpretation of a given construct is established without regard to access control. If the interpretation established makes use of inaccessible members or base classes, the construct is ill-formed.

¶5 The meaning of a construct is established without regard to access control; if that meaning uses inaccessible members or base classes, the construct is ill-formed. Note 4 is more specific: access control doesn't prevent name lookup from finding members, nor does it prevent implicit conversions to base classes from being considered. ¶4 has a separate sentence on overload sets: access control is applied only to the function selected by overload resolution.

Why this design? If access took part in overload resolution, the same call could select different functions inside and outside the class. Moving code from a member function into a free function, or changing a member from public to private, would quietly change overload choices elsewhere. C++ chooses to keep meanings stable and report an error when something is wrong.

### What is checked is the declaration that is named

¶4 Access control applies uniformly to declarations and expressions. Note 2 points out that it also applies to members named in friend declarations ([[class.friend#8]]) and using-declarations ([[namespace.udecl]]). When a name introduced by a using-declaration is named, the access of the using-declaration itself is checked, not that of the declaration it introduces.

Note 3 applies the same principle to type aliases: only the alias declaration itself is checked, not the underlying entity.

```cpp title="typedef-access.cpp" error
class A {
    class B { };
public:
    typedef B BB;
};
void f() {
    A::BB x;           // OK: A::BB is public
    auto y = A::BB{};  // OK
    decltype(y) z;     // OK: A::B is never written
    A::B w;            // error: A::B is private
}
```

### Access checking and SFINAE

During template argument substitution, access checking is part of the substitution ([[temp.deduct.general#8]] note 5). Naming an inaccessible member during substitution is merely a substitution failure, not a hard error, so you can write a trait that detects whether a member is accessible:

```cpp run title="sfinae-access.cpp" ok
#include <type_traits>
#include <utility>
template<class T, class = void>
struct has_v : std::false_type {};
template<class T>
struct has_v<T, std::void_t<decltype(std::declval<T&>().v)>>
    : std::true_type {};

class Hidden { int v; };
struct Open  { int v; };
static_assert(!has_v<Hidden>::value);   // inaccessible: substitution failure
static_assert(has_v<Open>::value);
int main() {}
```

## In whose declaration the name appears (¶6–¶9)

¶6 Access control governs the ability to name a class member from the declaration of a particular entity. That declaration includes the parts that appear before the name of the entity being declared, and, if the entity is a class, the definitions of members of that class appearing outside the class. Note 5 adds that implicit references to constructors, conversion functions and destructors are checked in the same context.

This solves a parsing-order problem:

```cpp title="access-context.cpp" ok
class A {
    typedef int I;          // private
    I f();
    friend I g(I);
    static I x;
    template<int> struct Q;
    template<int> friend struct R;
protected:
    struct B { };
};
A::I A::f() { return 0; }   // OK: the return type is part of the declaration of member A::f
A::I g(A::I p = A::x);      // OK: g is a friend, and default arguments count too
A::I g(A::I) { return 0; }
A::I A::x = 0;              // OK: definition of a static member
template<A::I> struct A::Q { };
template<A::I> struct R { };  // OK: R is a friend
struct D : A::B, A { };     // OK: D derives from A (Clang wrongly rejects this)
```

¶7 Example 4 is the same (the current draft's version also adds contract assertions to `f` and `g`, omitted here). When parsing the `A::I` in `A::I A::f()`, the compiler doesn't yet know that a member function of `A` follows, so the access check for the first `A::I` has to be deferred. The last line is similar: when `A::B` is parsed, `, A` hasn't been seen yet and it isn't known that `D` derives from `A`, so the check for the *base-specifier* has to wait until the whole base list has been read.

!!! impl "Where Clang deviates"
    At the time of writing, Clang 23 rejects the last line with `'B' is a protected member of 'A'`; it doesn't defer access checks in *base-specifier*s to the end of the list. Clang accepts all the other lines. By the standard, the whole example is well-formed.

¶8 Access for default arguments is checked at the point of declaration, not at the point of use. A default argument is part of the declaration and the responsibility of whoever wrote it; callers just accept the default. Default arguments of function templates and of member functions of class templates are checked by the rules in [[temp.inst]].

```cpp run title="default-arg-access.cpp" ok
class C {
    static int k;              // private
public:
    static void h(int = k) {}  // OK: k is named in a member declaration of C
};
int C::k = 0;
int main() { C::h(); }         // OK: not rechecked at the call
```

¶9 Access for default template arguments is checked in the context in which they appear, not at the point of use:

```cpp title="default-template-arg-access.cpp" error
class B { };
template<class T> class C {
protected:
    typedef T TT;
};
template<class U, class V = typename U::TT>  // checked at namespace scope
class D : public U { };

D<C<B>>* d;   // error: C<B>::TT is protected
```

`D` does end up deriving from `C<B>`, but the default argument is written in `D`'s template parameter list, which is at namespace scope, not within `D`'s class scope, so it doesn't get a derived class's access to protected members. ¶8 and ¶9 express the same principle: a name is checked with the permissions of whoever wrote it.

## Inheritance and base class accessibility ([class.access.base])

### Kinds of inheritance (¶1–¶2)

¶1 The kind of inheritance determines the access that base class members have in the derived class:

| Member in the base | `public` inheritance | `protected` inheritance | `private` inheritance |
|---|---|---|---|
| public | public | protected | private |
| protected | protected | protected | private |
| private | inaccessible | inaccessible | inaccessible |

Footnote 90 stresses that private members of a base class remain inaccessible to the derived class unless the base explicitly grants access with a friend declaration.

¶2 Without an access specifier, a derived class defined with `struct` inherits publicly by default, and one defined with `class` inherits privately by default. This is decided by the derived class's class-key, regardless of which keyword the base class was defined with.

### Inaccessible as an inherited member, accessible when named directly (¶3)

```cpp title="private-base-note.cpp" error
class B {
public:
    int mi;
    static int si;
};
class D : private B { };
class DD : public D {
    void f();
};
void DD::f() {
    mi = 3;                  // error: mi is private in D
    si = 3;                  // error: same for static members
    ::B b;
    b.mi = 3;                // OK: named directly through ::B
    b.si = 3;                // OK
    ::B::si = 3;             // OK
    ::B* bp1 = this;         // error: B is a private base
    ::B* bp2 = (::B*)this;   // OK: C-style cast
    bp2->mi = 3;             // OK: access through B*
}
```

This is the example from the note in ¶3. `mi` is inaccessible when named via the path `DD → D → B`, because it is private in `D`; but naming it directly through a `::B` object is fine.

The same note points out that a pointer conversion to an inaccessible base is ill-formed if done implicitly, but allowed with an explicit conversion. A C-style cast can ignore base class accessibility ([[expr.cast]]) and still performs the correct pointer adjustment. This is one of the few things it can do that `static_cast` can't.

### Accessible base classes (¶4–¶5)

¶4 defines when a base class `B` of `N` is an **accessible base class** at a point *R*. Imagine `B` has a public member m; any one of the following suffices:

- ¶4.1 m would be a public member of `N`, that is, inheritance from `N` down to `B` is public all the way;
- ¶4.2 *R* occurs in a direct member or friend of `N`, and m would be a private or protected member of `N`;
- ¶4.3 *R* occurs in a direct member or friend of a class `P` derived from `N`, and m would be a private or protected member of `P`;
- ¶4.4 there is a class `S` such that `B` is an accessible base of `S` at *R* and `S` is an accessible base of `N` at *R*.

```cpp run title="accessible-base-transitive.cpp" ok
class B { public: int m; };
class S : private B { friend class N; };
class N : private S {
public:
    void f() {
        B* p = this;   // OK: by ¶4.4
        (void)p;
    }
};
int main() { N n; n.f(); }
```

In `N::f`, `S` is an accessible base of `N` (¶4.2, `f` is a member of `N`); `B` is an accessible base of `S` (¶4.2, `N` is a friend of `S`). By transitivity under ¶4.4, `B` is an accessible base of `N`.

¶5 opens by stating what this definition is for: when a base class is accessible, a derived class pointer can be implicitly converted to a pointer to that base ([[conv.ptr]], [[conv.mem]]). So members and friends of a class `X` can implicitly convert an `X*` to a pointer to a private or protected direct base of `X`.

### The designating class (¶5)

Whether a member is accessible depends on which class it is named as a member of. ¶5 calls this class the **designating class** ([[g:designating-class|designating class]]). When an expression E names a member m, its designating class is:

- ¶5.1 if E is a *splice-expression* {{c++26}}, the innermost class of which m is directly a member;
- ¶5.2 otherwise, the class in whose scope name lookup performed a search that found m.

Note 3 gives examples: in `T::m` the designating class is `T`; in `p->m` it is the class of `*p`, and the same for an implicit `this->m`; in `p->T::m` it is `T`.

A member m is accessible at *R* when named in class `N` if one of the following holds:

- ¶5.3 m is designated by a *splice-expression* {{c++26}};
- ¶5.4 m as a member of `N` is public;
- ¶5.5 m as a member of `N` is private, and *R* occurs in a direct member or friend of `N`;
- ¶5.6 m as a member of `N` is protected, and *R* occurs in a direct member or friend of `N`, or in a member of a class `P` derived from `N` where m as a member of `P` is accessible (subject also to the additional check in [[class.protected]]);
- ¶5.7 there is a base class `B` of `N` that is accessible at *R*, and m is accessible at *R* when named in class `B`.

¶5.7 is recursive; it lets a grant of access to a base class member take effect through an accessible derived-to-base conversion:

```cpp run title="designating-class.cpp" ok
class B;
class A {
private:
    int i;
    friend void f(B*);
};
class B : public A { };
void f(B* p) {
    p->i = 1;   // OK
}
int main() { B b; f(&b); }
```

The designating class of `p->i` is `B`. `i` is not accessible as a member of `B`, since it is a private member of `A` and `f` is not a friend of `B`. But `A` is an accessible base of `B`, and `i` as a member of `A` is accessible in `f` (`f` is a friend of `A`), so ¶5.7 holds.

### The object expression must convert to the designating class (¶6)

¶6 When a non-static data member or non-static member function is accessed with a class member access operator (including an implicit `this->`), the left operand (considered as a pointer, after taking its address in the `.` case) must be implicitly convertible to a pointer to the designating class. Note 4 stresses that this requirement is in addition to the member itself being accessible.

Accessing a non-static member requires finding that subobject within the object first, which implies a derived-to-base conversion, and that conversion itself must be valid. Static members don't belong to any subobject, so they aren't subject to this restriction:

```cpp title="object-expression-conversion.cpp" error
class A { public: int x; static int s; };
class B : private A { friend void g(); };
int A::s = 0;
void h() {
    B b;
    b.::A::x = 1;   // error: x is accessible, but B* → A* is not
    b.::A::s = 1;   // OK: static member
}
void g() {
    B b;
    b.::A::x = 1;   // OK: g is a friend of B
}
```

## Access to virtual functions ([class.access.virt])

```cpp title="virtual-access.cpp" error
class B {
public:
    virtual int f();
};
class D : public B {
private:
    int f() override;
};
void f() {
    D d;
    B* pb = &d;
    D* pd = &d;
    pb->f();   // OK: B::f is public; D::f is called at run time
    pd->f();   // error: D::f is private
}
```

¶1 The access rules for a virtual function are determined by its declaration and aren't affected by functions that later override it. ¶2 Access is checked at the point of call using the type of the expression that denotes the object, that is, its static type. The class in which the function is actually defined, and its access there, is generally not known.

This is consistent with the principle that access control concerns only names: `pb->f()` names `B::f`, and the check ends there; where run-time dispatch goes has nothing to do with access. Overriding doesn't consider access either ([[class.virtual]] footnote 87).

The **Non-Virtual Interface** (NVI) idiom is built on this rule: a public non-virtual function calls a private virtual function, derived classes override that private virtual function to customize behavior, and outside code can only enter through the base class's public interface.

```cpp run title="nvi.cpp" ok
#include <cstdio>
class Widget {
public:
    void draw() { prepare(); do_draw(); }   // shared preliminary logic
    virtual ~Widget() = default;
private:
    void prepare() { std::puts("prepare"); }
    virtual void do_draw() { std::puts("Widget"); }
};
class Button : public Widget {
    void do_draw() override { std::puts("Button"); }
};
int main() {
    Button b;
    Widget& w = b;
    w.draw();   // prepare / Button
}
```

## Multiple paths take the widest ([class.paths])

```cpp run title="multiple-paths.cpp" ok
class W { public: void f() {} };
class A : private virtual W { };
class B : public virtual W { };
class C : public A, public B {
public:
    void g() { W::f(); }   // OK: via B's public path
};
int main() { C c; c.g(); c.f(); }
```

¶1 If a declaration can be reached by several paths through the inheritance graph, the access is that of the path that gives most access.

Only virtual inheritance gives the same subobject several paths. Under non-virtual inheritance each path leads to a different subobject, which is a question of ambiguity, not access.

## Nested classes ([class.access.nest])

```cpp title="nested-class-access.cpp" error
class E {
    int x;
    class B { };
    class I {
        B b;                  // OK: E::I can access E::B
        int y;
        void f(E* p, int i) {
            p->x = i;         // OK: E::I can access E::x
        }
    };
    int g(I* p) {
        return p->y;          // error: I::y is private to I
    }
};
```

¶1 A nested class is a member and as such has the same access rights as any other member. Conversely, members of the enclosing class have no special access to members of a nested class; the usual access rules apply.

The reason for the asymmetry: a nested class is part of the enclosing class's implementation, while the enclosing class is just one user of the nested class, which has its own encapsulation. When access in the other direction is needed, declare the enclosing class a friend in the nested class.

## Legitimate back doors

### Explicit instantiations aren't access-checked

[[temp.spec.general#6]] says the usual access checking rules don't apply to names in a declaration of an explicit instantiation or explicit specialization, except for names in function bodies, default arguments, *base-clause*s, member specifications, enumerator lists, and initializers of static data members or variable templates. Its note says private types or objects that would normally be inaccessible can be used in template arguments and function declarators.

The intent of this rule is convenience: specializing a trait for a class's private nested type, or explicitly instantiating a template with a private type as an argument in a library implementation, doesn't require declaring friends. But it has a famous side effect: it lets you legitimately obtain a member pointer to any private member:

```cpp run title="private-access-via-explicit-instantiation.cpp" ok
#include <cstdio>
class Safe {
    int secret = 42;
    void hidden() const { std::puts("hidden called"); }
};
// one tag per member to grab; get can only be found via ADL
struct SecretTag { friend constexpr auto get(SecretTag); };
struct HiddenTag { friend constexpr auto get(HiddenTag); };

template<class Tag, auto M>
struct Thief {
    friend constexpr auto get(Tag) { return M; }
};
// explicit instantiation: &Safe::secret in the template argument isn't access-checked
template struct Thief<SecretTag, &Safe::secret>;
template struct Thief<HiddenTag, &Safe::hidden>;

int main() {
    Safe s;
    std::printf("%d\n", s.*get(SecretTag{}));  // 42
    (s.*get(HiddenTag{}))();                    // hidden called
}
```

Every step is well-formed:

1. The template argument `&Safe::secret` of the explicit instantiation definition isn't subject to access checking.
2. Instantiating `Thief<SecretTag, &Safe::secret>` defines the friend function `get(SecretTag)`, which returns that member pointer.
3. `get(SecretTag{})` in `main` finds it in the associated class `SecretTag` by argument-dependent lookup ([[basic.lookup.argdep]]).
4. `s.*p` uses a member pointer and doesn't name `secret`.

This is an oddity of the rules, not engineering practice. Unit tests and debugging tools occasionally use it.

### Splice expressions aren't access-checked {{c++26}}

¶5.3 says a member named by a *splice-expression* is always accessible. Combined with listing all members using `std::meta::access_context::unchecked()` ([[meta.reflection.access.context]]), you can write `obj.[: member :]` directly:

```cpp
#include <meta>
class Safe { int secret = 42; };

consteval std::meta::info secret_member() {
    return std::meta::nonstatic_data_members_of(
        ^^Safe, std::meta::access_context::unchecked())[0];
}
int peek(Safe& s) { return s.[: secret_member() :]; }  // OK
```

Clang 23 doesn't support static reflection yet, so this code hasn't been verified by compiling it. The design reasoning is that reflection queries themselves take an access context parameter, and `access_context::current()` returns only the members accessible in the current context. Whether access control is respected is chosen explicitly by the programmer at query time; a splice merely uses a reflection already obtained and doesn't check again.

## Implementation view

!!! impl
    - Access control is mostly a compile-time notion, but it can affect layout indirectly. The Itanium ABI uses POD in the C++03 sense (POD for the purpose of layout) to decide whether a derived class can reuse a base class's tail padding, and C++03 POD requires no private or protected non-static data members. So changing a data member from public to private can change the layout and size of derived classes.
    - MSVC encodes a member's access in its mangled name; the Itanium ABI's mangled names don't include access. So on MSVC, compiling part of the code with tricks like `#define private public` leads to missing symbols at link time.

## History

!!! history
    - In C++98, nested classes had no privileged access to the enclosing class's private members and needed friendship. [[CWG45]] fixed this, and since C++11 a nested class, being a member, has a member's access.
    - C++11 specified that access checking is part of template argument substitution, so an inaccessible member causes a substitution failure rather than a hard error ([[CWG1170]]).
    - C++26 {{c++26}} specifies the designating class for *splice-expression*s and makes members named by them unconditionally accessible; reflection queries control accessibility explicitly with `access_context`.

## Common misconceptions

!!! pitfall "Overload resolution skips private overloads"
    It doesn't. A private overload is reported as an error only after being selected; `sp->f(2.0)` is an error, not a call to `f(int)`.

!!! pitfall "private protects data"
    It restricts only names. References, pointers, `auto`, `decltype`, templates, explicit instantiations and C++26 splices can all reach private entities.

!!! pitfall "Making a virtual function private in an override hides it"
    It can still be called through a base class pointer or reference; the access check looks at the declaration in the base class.

!!! pitfall "Changing struct to class only affects the default member access"
    The default kind of inheritance also changes from public to private: `class D : B` is private inheritance.

## Questions

!!! question "Question 1"
    Which function does each of these calls select? Is the program well-formed?
    ```cpp
    class X {
    public:
        void f(long);
    private:
        void f(int);
        friend void call(X&);
    };
    void call(X& x) { x.f(1); }
    void other(X& x) { x.f(1); }
    ```

<details markdown="1">
<summary>Answer</summary>

Both select `f(int)` (an exact match). `call` is a friend of `X` and can access `f(int)`, so it is well-formed. In `other`, overload resolution also selects `f(int)`, then the access check fails, so `other` is ill-formed. The compiler doesn't switch to `f(long)` because `f(int)` is inaccessible ([class.access.general] ¶4, ¶5).
</details>

!!! question "Question 2"
    With `struct B { int m; }; struct D : private B { using B::m; }; struct E : D {};`, is `E e; e.m = 1;` well-formed? And `B* p = &e;`?

<details markdown="1">
<summary>Answer</summary>

`e.m = 1;` is well-formed. Lookup in `E` finds the using-declaration inherited through `D`; it is in the default public region of `struct D` and is still public in `E`; access checking applies to the using-declaration itself ([class.access.general] ¶4). The designating class is `E`, and the conversion from `E*` to `E*` required by ¶6 obviously holds.

`B* p = &e;` is ill-formed: `B` is a private base of `D`, and outside the class it is not an accessible base of `E` ([class.access.base] ¶4). The using-declaration changes only the access of the name `m`, not the accessibility of the base class. Clang reports `cannot cast 'E' to its private base class 'B'`.
</details>
