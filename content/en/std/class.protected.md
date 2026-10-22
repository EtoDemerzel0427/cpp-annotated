---
title: Protected member access
summary: "A derived class can access the protected non-static members of a base only through objects of its own type (or a type derived from it), and must name its own class when forming a pointer to member."
updated: 2026-10-19
---

!!! tldr
    - When members and friends of a derived class `D` access a protected non-static member of a base, the static type of the object expression must be `D` or a class derived from `D`. Access through a `B&` or through a sibling class object doesn't work.
    - Forming a pointer to member requires writing `&D::m`, not `&B::m`; the resulting type is still `T B::*`.
    - Static members, enumerators, nested types and members named by a splice are exempt from this check.
    - Once formed, a pointer to member can be applied with `.*` to any `B` object, so protected guards against misuse, not deliberate circumvention.

## A derived class can only touch its own share

```cpp error
class Account {
protected:
    int balance = 0;
};
class Savings : public Account {};
class Attacker : public Account {
public:
    static void reset(Savings& s) {
        s.balance = 0;   // error: s is not an Attacker
    }
    void reset_self() {
        balance = 0;     // OK: this is an Attacker*
    }
};
```

`Attacker` is derived from `Account` and can access `Account`'s protected members, but only through `Attacker` objects. Without this restriction, anyone could derive a class from `Account` and rewrite the internal state of every `Account` object (including `Savings` objects), and protected would be little different from public.

So protected means: the interface between a base class and each of its derived classes. The invariants of `Savings` are maintained jointly by `Account` and `Savings`, and the sibling `Attacker` has no business interfering.

## The rule (¶1)

First, recall two concepts from [[class.access.base]]. The **designating class** ([[g:designating-class]]) is the class in which the member name was looked up: in `p->m` it is the class `p` points to, in `p->B::m` it is `B`. A protected member is accessible at some point because the reference occurs in a member or friend of some class C, and C is derived from the class the member belongs to ([[class.access.base#5]]).

¶1 On top of that, an additional check applies to protected non-static data members and non-static member functions (except when the member is designated by a *splice-expression*). Suppose access is granted because the reference occurs in a member or friend of C:

- if the access is to form a pointer to member ([[expr.unary.op]]), the *nested-name-specifier* must denote C or a class derived from C;
- otherwise, if the access involves an object expression (which may be an implicit `*this`, [[expr.prim.id.general]], [[expr.ref]]), the class of the object expression must be C or a class derived from C.

!!! std
    Otherwise, if the access involves a (possibly implicit) object expression, the class of the object expression shall be C or a class derived from C.

Footnote 91 adds that this check doesn't apply to other members, such as static data members and enumerators.

## The standard's example, line by line

```cpp title="protected-std-example.cpp" error
class B {
protected:
    int i;
    static int j;
};
class D1 : public B {};
class D2 : public B {
    friend void fr(B*, D1*, D2*);
    void mem(B*, D1*);
};

void fr(B* pb, D1* p1, D2* p2) {
    pb->i = 1;                 // error: the class of the object expression is B
    p1->i = 2;                 // error: D1 is a sibling of D2
    p2->i = 3;                 // OK
    p2->B::i = 4;              // OK: the designating class is B, but the object is a D2
    int B::* pmi_B = &B::i;    // error: must write &D2::i
    int B::* pmi_B2 = &D2::i;  // OK: the type is still int B::*
    B::j = 5;                  // error: fr is not a friend of B
    D2::j = 6;                 // OK: static member, designating class D2
}

void D2::mem(B* pb, D1* p1) {
    pb->i = 1;                 // error
    p1->i = 2;                 // error
    i = 3;                     // OK: implicit this->i
    B::i = 4;                  // OK: implicit (*this).B::i
    int B::* pmi_B = &B::i;    // error
    int B::* pmi_B2 = &D2::i;  // OK
    j = 5;                     // OK: static member
    B::j = 6;                  // OK: static member
}

void g(B* pb, D1* p1, D2* p2) {
    pb->i = 1;                 // error: g is neither a member nor a friend
    p1->i = 2;                 // error
    p2->i = 3;                 // error
}
```

`p2->B::i` shows that the additional check and the designating class are separate things: the qualified name makes `B` the designating class, but the additional check looks at the class of the object expression, `D2`, so it is valid.

`B::j` is an error in `fr` but not in `D2::mem`, and the reason isn't the additional check (static members aren't subject to it) but basic accessibility. Item 5.6 of [[class.access.base#5]] allows references that occur in members of a derived class, and `fr` is only a friend of `D2`; the designating class is `B`, and `fr` is not a friend of `B`. Rewritten as `D2::j`, the designating class becomes `D2`, `j` as a member of `D2` is protected, and `fr` is a friend of `D2`, so it is accessible.

`&B::i` and `&D2::i` both have type `int B::*`, because the type of a pointer to member is determined by the class the member actually belongs to ([[expr.unary.op]]). The only difference is that the latter passes the additional check.

## Common ways to hit the wall

### Converting to the base breaks it

```cpp error
class B { protected: int i = 0; };
class D : public B {
    void f() {
        i = 1;                         // OK: this->i
        this->B::i = 2;                // OK: the object's class is D
        static_cast<B&>(*this).i = 3;  // error: the object's class became B
        B* pb = this;
        pb->i = 4;                     // error: even though pb points to *this
    }
};
```

The additional check looks only at the static type of the object expression, not at whether it happens to point to the object itself at run time.

### Copying from a base class object

```cpp error
class Base { protected: int v = 0; };
class Derived : public Base {
public:
    void copy_from(const Derived& o) { v = o.v; }  // OK
    void copy_from(const Base& o)    { v = o.v; }  // error
};
```

The usual approach is to provide a protected helper in `Base`, such as `assign_from(const Base&)`, so that `Base` reads `o.v` itself.

### Skipping a generation

```cpp error
class B { protected: void f(); };
class D : public B {};
class E : public D {
    void g(D& d, E& e) {
        d.f();   // error: D is a base of E, not a class derived from E
        e.f();   // OK
    }
};
```

In a member of `E`, access is granted because of membership in `E`, so C is `E`. `D` is also derived from `B`, but it is neither `E` nor a class derived from `E`.

### Protected constructors and destructors

```cpp error
class B {
protected:
    B() = default;
    ~B() = default;
};
class D : public B {
    void f() {
        D d;           // OK: initializes D's base class subobject
        B b;           // error: constructs a standalone B object
        B* p = new B;  // error
    }
};
```

Making a constructor protected conventionally means the class can only be used as a base class; making a non-virtual destructor protected means objects can't be `delete`d through a base class pointer. Clang 23 rejects `B b;` (reporting both the constructor and the destructor as inaccessible) and `new B`.

!!! lawyer "The object expression in a constructor call"
    `B b;` has no literal object expression, and the wording of how ¶1 applies to constructor calls isn't entirely clear. The common understanding among implementations is that creating a standalone `B` object in a member of `D` amounts to accessing a protected member through a `B` object, so it is rejected, while initializing `D`'s own `B` base class subobject is allowed.

## Pointers to members get around the check

¶1 requires writing `&D2::i`, but the resulting `int B::*` can be applied to any `B` object:

```cpp run title="pmf-loophole.cpp" ok
#include <cstdio>

class B {
protected:
    int i = 1;
};
class D1 : public B {};
class D2 : public B {
public:
    static int peek(B& any) {
        // return any.i;          // error
        int B::* p = &D2::i;      // OK
        return any.*p;            // OK: .* doesn't name the member
    }
};

int main() {
    D1 sibling;
    std::printf("%d\n", D2::peek(sibling));  // 1
}
```

`.*` and `->*` ([[expr.mptr.oper]]) don't name members, so access control is checked only once, when the pointer to member is formed. This is a known consequence of the rules, not a compiler bug. Access control targets unintentional misuse, not deliberate circumvention.

## Cases exempt from the additional check

| Case | Reason |
|---|---|
| Static data members, static member functions | They don't belong to a particular object (footnote 91) |
| Enumerators, nested types, type aliases | Same as above |
| Members designated by a *splice-expression* {{c++26}} | ¶1 excludes them explicitly; such members are always accessible ([[class.access.base#5]] item 5.3) |
| Members that are public in the designating class | The additional check applies only to members that are protected in the designating class |

An example for the last row: `struct S { int x; }; class T : protected S {}; class U : public T {};`. In a member of `U`, writing `s.x` through `S& s` has designating class `S`, and `x` is public in `S`, so it is accessible directly without involving the additional check.

A static member has only one copy, shared by the whole class hierarchy, so there is no "someone else's share" to protect. If it were subject to the additional check, a form like `B::j` with no object expression couldn't be checked at all; and `pb->j` would be valid or invalid depending on the type of `pb`, even though it accesses the same entity.

!!! note "Diagnostics"
    Clang reports a failed additional check just like ordinary inaccessibility, saying only `'i' is a protected member of 'B'` without mentioning the type of the object expression, which easily misleads people into thinking derived classes can't access protected members at all.

## Questions

!!! question "Question"
    Can a friend function `fr(D1& x)` of `D2` access `x`'s `i` through `static_cast<B&>(x).i`? Through `x.*(&D2::i)`?

<details markdown="1">
<summary>Answer</summary>

The first, no: the class of the object expression is `B`, not `D2` or a class derived from it. The second, yes: `&D2::i` satisfies the requirement for pointers to members and has type `int B::*`; `D1&` converts implicitly to `B&`, and `.*` does no access checking. Friends and members are bound by the same constraints here, and share the same loophole.
</details>

<details class="fine" markdown="1"><summary>Remaining wording</summary>

This rule has existed since C++98 and its substance has never changed; the wording has been rewritten several times as concepts like the designating class and object expressions were tidied up. With static reflection in C++26, the condition excluding *splice-expression*s was added.

</details>
