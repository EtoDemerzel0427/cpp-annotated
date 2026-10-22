---
title: Construction and destruction
summary: "What you can do with an object while it is being constructed or destroyed; during that time, virtual calls, typeid and dynamic_cast all treat it as an object of the class whose constructor or destructor is running."
updated: 2026-10-19
---

!!! tldr
    - A virtual function called in a base class constructor calls the base class's own version, not the derived class's override. The same goes for destruction. During this time `typeid` and `dynamic_cast` also treat the object as an object of the class whose constructor or destructor is running.
    - If this rule dispatches to a pure virtual function, the behavior is undefined; under the Itanium ABI the program prints "Pure virtual function called" and terminates.
    - For an object with a non-trivial constructor, accessing its members or bases before construction starts is UB; for an object with a non-trivial destructor, so is accessing them after destruction finishes.
    - During initialization, reading the object being initialized other than through the constructor's `this` gives an unspecified value.
    - Converting to a base during construction requires every class on the conversion path to have started construction; a virtual call made through another subobject can be UB.

## Virtual calls in a base class constructor

```cpp run title="virtual-in-ctor.cpp" ok
#include <cstdio>

struct Base {
    Base() { call(); }
    virtual ~Base() { call(); }
    virtual const char* name() const { return "Base"; }
    void call() const { std::printf("%s\n", name()); }
};

struct Derived : Base {
    Derived() { call(); }
    ~Derived() override { call(); }
    const char* name() const override { return "Derived"; }
};

int main() {
    Derived d;   // Base / Derived
}                // Derived / Base
```

While `Base()` runs, none of `Derived`'s members have been initialized yet. Calling `Derived::name()` at that point could well read uninitialized members. Destruction is the reverse: while `~Base()` runs, all of `Derived`'s members have already been destroyed.

So C++ lets an object's dynamic type change step by step during construction and destruction: while the `Base` part is constructed it behaves as a `Base`, while the `Derived` part is constructed it behaves as a `Derived`, and destruction steps back in the reverse order. Java and C# make the opposite choice: a base class constructor calls the derived class's override, while the derived class's fields still hold their default zero values.

### The rule (¶4)

¶4 Member functions, including virtual functions, can be called during construction or destruction. When a virtual function is called directly or indirectly from a constructor or destructor, and the object the call applies to is the object under construction or destruction (call it *x*), the function called is the [[g:final-overrider|final overrider]] in the constructor's or destructor's class, not one overriding it in a more derived class.

"During construction or destruction" here includes the construction or destruction of non-static data members, and {{c++26}} the evaluation of a constructor's postcondition assertions and a destructor's precondition assertions ([[dcl.contract.func]]). In the example above `call()` is non-virtual, and its call to `name()` is indirect; it is bound by this rule all the same.

!!! impl "Implementation: rewriting the vtable pointer during construction"
    In both the Itanium ABI and the MSVC ABI, each constructor sets the object's vtable pointer (vptr) to its own class's vtable after initializing the bases and before initializing the members; a destructor sets it back to its own class's vtable before running its body, and the base class destructors then change it to theirs. `typeid` reads the type information in the vtable, and `dynamic_cast` relies on it too, so all three see the current class.

    This rule also gives the optimizer a guarantee: a virtual call on `this` in a constructor always lands on the final overrider in that class, so it can be devirtualized. Clang 23 at `-O1` generates a direct call to `Base::name` for `Base::Base() { sink(name()); }`.

### Dispatching to a pure virtual function

```cpp run title="pure-virtual.cpp" ub
struct B {
    B() { init(); }
    void init() { f(); }     // indirect call; the compiler doesn't warn
    virtual void f() = 0;
    virtual ~B() = default;
};
struct D : B { void f() override {} };

int main() { D d; }   // UB: during B's construction f() is the pure B::f
```

If the final overrider dispatched to under ¶4 is pure virtual, the behavior is undefined ([[class.abstract#6]]). Under the Itanium ABI, the slots for pure virtual functions in an abstract class's vtable point to `__cxa_pure_virtual`; running the example above in our tests, libc++abi prints "Pure virtual function called!" and aborts. If `B()` called `f()` directly, Clang 23 would give a `-Wcall-to-pure-virtual-from-ctor-dtor` warning.

### Calls made through other subobjects

¶4 ends: if a virtual call uses an explicit class member access (`p->f()` or `obj.f()`), and the object expression refers to the complete object of *x* or one of that object's base class subobjects, but not to *x* or one of its base class subobjects, the behavior is undefined.

Example 4 in the standard, with output added:

```cpp run title="virtual-other-path.cpp" ub
#include <cstdio>

struct V {
    virtual void f() { std::puts("V::f"); }
    virtual void g() { std::puts("V::g"); }
    virtual ~V() = default;
};
struct A : virtual V {
    void f() override { std::puts("A::f"); }
};
struct B : virtual V {
    void g() override { std::puts("B::g"); }
    B(V*, A*);
};
struct D : A, B {
    void f() override { std::puts("D::f"); }
    void g() override { std::puts("D::g"); }
    D() : B((A*)this, this) {}
};

B::B(V* v, A* a) {
    f();      // V::f: B's final overrider
    g();      // B::g, not D::g
    v->g();   // OK: V is a base of B, so B::g
    a->f();   // UB: A is not a base of B
}

int main() { D d; }
```

While the `B` subobject is being constructed, *x* is the `B` subobject. The `A` subobject has already been fully constructed, but it belongs to the complete object `D` and isn't part of *x*. What its vptr points to at this moment depends on when and in what order the implementation sets the vptrs of the various subobjects; the standard doesn't want to constrain those details, so it makes this UB.

Running the example above with Clang 23, `a->f()` prints `V::f`, neither `A::f` nor `D::f`. With virtual bases, intermediate classes use special construction vtables during construction (passed in via the VTT mentioned in [[class.base.init]]). One possible explanation: `A` shares its vptr location with the virtual base `V`, so when `B`'s constructor installs a construction vtable for `V`, it also rewrites the vptr seen by the `A` subobject.

## `typeid` and `dynamic_cast` (¶5–¶6)

```cpp run title="typeid-dyncast.cpp" ok
#include <cstdio>
#include <typeinfo>

struct V { virtual void f() {} virtual ~V() = default; };
struct A : virtual V {};
struct B : virtual V { B(V*, A*); };
struct D : A, B { D() : B((A*)this, this) {} };

B::B(V* v, A*) {
    std::printf("%d\n", typeid(*this) == typeid(B));      // 1
    std::printf("%d\n", typeid(*v) == typeid(B));         // 1
    std::printf("%d\n", dynamic_cast<B*>(v) == this);     // 1
    std::printf("%d\n", dynamic_cast<D*>(v) == nullptr);  // 1
    // typeid(*a); dynamic_cast<B*>(a);  both UB: A is not a base of B
}

int main() { D d; }
```

¶5 In a constructor (including the *mem-initializer* or default member initializer of a non-static data member), a destructor, or a function called from them directly or indirectly, if the operand of `typeid` refers to the object under construction or destruction, the result is the `std::type_info` representing the constructor's or destructor's class. If the static type of the operand is neither that class nor one of its bases, the behavior is undefined.

¶6 In the same contexts, `dynamic_cast` treats the object under construction or destruction as a most derived object of the constructor's or destructor's class. So in the example above `dynamic_cast<D*>(v)` is a null pointer: at this point the object is treated as a `B`, which has no `D` part. If the static type of the operand is not a pointer to (or object of) that class or one of its bases, the behavior is undefined.

¶4–¶6 together come down to one sentence: during construction and destruction, the object's dynamic type is the class whose constructor or destructor is running.

| When | Virtual calls dispatch to | `typeid(*this)` | `dynamic_cast<Derived*>(this)` |
|---|---|---|---|
| In the `Base` constructor | `Base`'s final overrider | `Base` | null pointer |
| In the `Derived` constructor | `Derived`'s final overrider | `Derived` | non-null |
| During the lifetime | The most derived class's final overrider | Most derived class | non-null |
| In the `Derived` destructor | `Derived`'s final overrider | `Derived` | non-null |
| In the `Base` destructor | `Base`'s final overrider | `Base` | null pointer |

## Before construction starts, after destruction ends (¶1)

```cpp run title="before-ctor.cpp" ub
struct X { int i; };
struct Y : X { Y() {} };              // non-trivial constructor
struct A { int a; };
struct B : public A { int j; Y y; };  // non-trivial constructor because of y

extern B bobj;
B* pb = &bobj;                        // OK: address of the complete object
int* p1 = &bobj.a;                    // UB: member of a base
int* p2 = &bobj.y.i;                  // UB: member of a member
A* pa = &bobj;                        // UB: conversion to a base
B bobj;                               // definition, initialized after the lines above

extern X xobj;
int* p3 = &xobj.i;                    // OK: X's constructors are all trivial
X xobj;

int main() {}
```

¶1 For an object with a non-trivial constructor, referring to any non-static member or base class of the object before the constructor begins execution is undefined behavior. For an object with a non-trivial destructor, referring to any non-static member or base class after the destructor finishes execution is likewise undefined behavior. "Referring to" here isn't limited to reading or writing values; taking a member's address and converting to a base count too.

Example 1 in the standard demonstrates with a global object declared first and defined later: global variables are dynamically initialized in definition order ([[basic.start.dynamic]]), so `bobj` hasn't been constructed yet when `p1` and the others are initialized.

A trivial constructor does nothing, so only the non-trivial case is covered. Before a non-trivial constructor starts, the object's internal structure (the vptr, the location of virtual bases) may not be set up yet, and it may not even be possible to work out where the members are. For a non-virtual base, `pa = &bobj` just adds a constant offset and happens to work in practice; if `A` were a virtual base, the offset would have to be read from a vptr that hasn't been written yet. The standard treats both cases alike.

The second part of Example 1 shows the same problem inside a constructor:

```cpp run title="before-member-ctor.cpp" ub
struct W { int j; };
struct X : public virtual W {};
struct Y {
    int* p;
    X x;
    Y() : p(&x.j) {}   // UB: x hasn't started construction yet
};

int main() { Y y; (void)y; }
```

`p` is initialized before `x`, and `&x.j` has to locate `j` via the virtual base `W`, while `x`'s construction hasn't started.

## Reading the object under initialization other than through `this` (¶2)

```cpp run title="self-ref-global.cpp" unspecified
#include <cstdio>

extern struct D d;
struct D {
    D(int a) : a(a), b(d.a) {}   // via the global name d, not via this
    int a, b;
};
D d = D(1);                      // the value of d.b is unspecified

int main() { std::printf("%d\n", d.b); }
```

¶2 During the initialization of an object, if the value or object representation of one of its subobjects is accessed through a glvalue that is not obtained (directly or indirectly) from the constructor's `this` pointer, the value obtained is unspecified.

Since C++17, `D(1)` initializes `d` directly ([[class.copy.elision]]), so `this` in the constructor is `&d`, and `d.a` really does refer to the same object. But the access doesn't go through `this`, so the value is still unspecified. Clang 23 prints `1`, which the standard doesn't guarantee. To read the member, write `b(this->a)`.

This rule serves optimization. The other part of Example 2 in the standard:

```cpp
struct C;
void no_opt(C*);

struct C {
    int c;
    C() : c(0) { no_opt(this); }
};

const C cobj;

void no_opt(C* cptr) {
    int i = cobj.c * 100;   // value unspecified
    cptr->c = 1;            // modified through this: OK
    std::printf("%d\n", cobj.c * 100);   // value unspecified
}
```

`cobj` is a `const` object, and the compiler would like to assume `cobj.c` doesn't change after initialization, so it can constant-fold it or keep it in a register. But a `const` object can be modified during construction; `const` semantics take effect only when the constructor for the most derived object ends ([[class.ctor.general#4]]). ¶2's compromise is: accesses through `this` are reliable, and accesses that bypass `this` only get an unspecified value. This is unspecified behavior, not UB: the program is still constrained; you just don't know which value you read.

## Converting to a base, forming a pointer to a member (¶3)

```cpp run title="conversion-path.cpp" ub
struct A {};
struct B : virtual A {};
struct C : B {};
struct D : virtual A { D(A*) {} };
struct X { X(A*) {} };

struct E : C, D, X {
    E() : D(this),   // UB: E* → A* may go through D, which hasn't started construction
          X(this) {} // OK: C, B, D and A are all constructed by now
};

int main() { E e; }
```

¶3 has two preconditions:

- When converting a pointer (or glvalue) to an object of class `X` to a pointer (or reference) to a base class `B` of `X`, the construction of `X`, and of all its direct or indirect bases that directly or indirectly derive from `B`, must have started, and their destruction must not have completed; otherwise the behavior is undefined.
- When forming a pointer to a direct non-static member of an object `obj` (or accessing the value of that member), the construction of `obj` must have started and its destruction must not have completed; otherwise the behavior is undefined.

The first depends on the conversion path. `D(this)` converts `E*` to `A*`, and the compiler may go through `D` to find the virtual base `A`, which requires reading information in the `D` subobject, and `D` is exactly the one that hasn't started construction. The comment in the standard's example points out that writing `D((C*)this)` is well-defined: `E*` to `C*` is fine (`E()` has started), and `C*` to `A*` is fine too (`C` has been fully constructed).

The second is more lenient: it only requires `obj` to have started construction, not the member itself to be initialized. So writing `r(a)` (binding a reference to a member not yet initialized, [[class.base.init#17]]) or `p(&member)` in a *mem-initializer* is well-defined, as long as it doesn't go through the virtual base of a member not yet constructed, as in the second example under ¶1.

## Common misconceptions

!!! pitfall "Implementing the template method pattern with a virtual call in the base constructor"
    `Base() { init(); }` meant to let derived classes customize `init()` won't call the derived version. Use two-phase initialization (call `init()` after construction), a factory function, or pass the customization point as a constructor argument. The same goes for `cleanup()` in a destructor: a derived class's cleanup belongs in the derived class's own destructor.

!!! pitfall "Publishing this in a constructor"
    After handing `this` to another thread or a global registry, other code may access the object while it is still being constructed: virtual calls dispatch to the base version, members aren't initialized yet, reads not via `this` give unspecified values (¶2), and across threads without synchronization it is also a data race. Publish only after construction is complete.

## Questions

!!! question "Question"
    What does the following program print?

    ```cpp
    #include <cstdio>
    struct B;
    struct M { M(B* b); };
    struct B {
        M m;
        B() : m(this) {}
        virtual const char* who() const { return "B"; }
        virtual ~B() = default;
    };
    struct D : B {
        const char* who() const override { return "D"; }
    };
    M::M(B* b) { std::puts(b->who()); }
    int main() { D d; }
    ```

<details markdown="1">
<summary>Answer</summary>

It prints `B`. `M`'s constructor is called while initializing `B`'s member `m`, and ¶4 explicitly includes the construction of non-static data members. `b` points to the very `B` object under construction (*x* itself), so the call dispatches to `B::who`. In implementations, `B`'s constructor has already set the vptr to `B`'s vtable before initializing the member `m`.
</details>

<details class="fine" markdown="1"><summary>History</summary>

The main rules of this subclause (¶1, ¶3–¶6) already existed in C++98, with essentially unchanged wording. With contracts in C++26, ¶4 extended dispatch-by-current-class to constructor postconditions and destructor preconditions, while [[class.base.init#18]] made member function calls in constructor preconditions and destructor postconditions UB.

</details>
