---
title: Virtual functions
summary: "Which member functions are virtual, when a derived class function overrides a base class virtual function, which function a virtual call ends up executing, and the constraints both ends of an override must satisfy on return type, qualifiers, deleted and consteval."
updated: 2026-10-19
---

!!! tldr
    - A member function is virtual if its first declaration has `virtual`, or if it overrides a virtual function of a base class; writing `virtual` in the derived class makes no difference.
    - A derived class function overrides a base class virtual function only if they correspond in name, parameter types, cv-qualifiers and ref-qualifier; the return type and access don't take part in the decision. Being slightly off turns it into hiding, which is why you write `override`.
    - Calling a virtual function through a base pointer or reference executes the final overrider in the object's dynamic type; each virtual function of each base class subobject must have exactly one final overrider.
    - Only the choice of function body is made at run time. Name lookup, overload resolution, access checking, default arguments and the type of the call expression are all determined by the static type.
    - A call with a qualified name `B::f()` suppresses the virtual call; a declared virtual function must be defined (or be pure virtual), and otherwise the usual symptom is a link error about a missing vtable.

```cpp run ok
#include <cstdio>
struct Shape {
    virtual void draw() const { std::puts("Shape"); }
    virtual ~Shape() = default;
};
struct Circle : Shape {
    void draw() const override { std::puts("Circle"); }
};
int main() {
    Circle c;
    const Shape& s = c;
    s.draw();     // prints Circle
}
```

The static type of `s` is `Shape`, but the object it refers to is a `Circle`. The most derived type of the object a glvalue refers to is its **dynamic type** ([[defns.dynamic.type]]). `draw` is virtual, so `s.draw()` chooses the function body by dynamic type and executes `Circle::draw`.

Such a call is a **virtual function call**, defined in [[expr.call#2]]: when the selected function is virtual and not named with a qualified name, the call invokes its final overrider in the dynamic type of the object. This subclause specifies which functions are virtual, what overriding means, which function is the final overrider, and the constraints an override must meet. For virtual calls during construction and destruction, see [[class.cdtor#4]].

## Which functions are virtual (¶1, ¶11)

¶1 A non-static member function is virtual in two cases: its first declaration has the keyword `virtual`, or it overrides a virtual function declared in some base class. Footnote 85 says writing `virtual` on an overriding function is valid but redundant. So virtualness is passed down the inheritance chain, and a derived class function with a corresponding signature is automatically virtual.

A class that has virtual functions (declared or inherited) is called a **polymorphic class**. Only polymorphic classes can be downcast with `dynamic_cast` ([[expr.dynamic.cast]]), and `typeid` evaluates its operand and returns the dynamic type only for glvalues of polymorphic class type ([[expr.typeid]]). Footnote 86 adds that a class is still polymorphic even if all its virtual functions are `consteval` and no vtable is needed at run time at all.

The following kinds of function can't be virtual:

| Function | Basis |
|---|---|
| Non-member functions, static member functions | ¶11: a virtual call needs a specific object to determine the call target |
| Constructors | [[class.ctor]] |
| Member function templates | [[temp.mem#3]]: the size of the vtable must be fixed when the class is defined, but a template can have any number of specializations |
| Functions with a trailing *requires-clause* | ¶6, see below |
| Explicit object member functions (first parameter has `this`) | [[dcl.fct#7]] |

```cpp title="cannot-be-virtual.cpp" error
struct S {
    virtual static void a();              // error: static member
    template<class T> virtual void b(T);  // error: member function template
    virtual void c(this S& self);         // error: explicit object member function
};
template<class T> struct R {
    virtual void d() requires true;       // error: constrained
};
```

The note in ¶11 also mentions that a virtual function of one class can be declared a friend of another class ([[class.friend]]). Friendship grants access and has nothing to do with virtualness.

## Overriding (¶2–¶3)

### Almost, but not an override

```cpp run title="overriding-basics.cpp" ok
#include <cstdio>
struct B {
    virtual void f(int)    { std::puts("B::f(int)"); }
    virtual void g() const { std::puts("B::g const"); }
    virtual ~B() = default;
    void call_h() { h(); }
private:
    virtual void h()       { std::puts("B::h"); }
};
struct D : B {
    void f(int) override   { std::puts("D::f(int)"); }
    void f(long)           { std::puts("D::f(long)"); }
    void g()               { std::puts("D::g"); }
    void h() override      { std::puts("D::h"); }
};
int main() {
    D d;
    B& b = d;
    b.f(1);       // D::f(int): overrides
    b.g();        // B::g const: D::g lacks const, so doesn't override
    b.call_h();   // D::h: overriding ignores access
}
```

Neither `D::f(long)` nor `D::g()` overrides anything; they are just new functions with the same name, and they hide the base class functions of that name in `D`'s scope. The compiler doesn't report an error. With `-Wall`, Clang gives a `-Woverloaded-virtual` warning for `D::g` (it hides an overloaded virtual function), and that warning almost always means a bug.

### The definition of overriding

¶2 opens with the definition:

!!! std
    If a virtual member function F is declared in a class B, and, in a class D derived (directly or indirectly) from B, a declaration of a member function G corresponds to a declaration of F, ignoring trailing requires-clauses, then G overrides F.

"[[g:correspond|Corresponds]]" is a term defined in [[basic.scope.scope#4]], originally used to decide whether two declarations in the same scope are the same function. For two non-static member functions it requires:

- The same name, or both being destructors. So a derived class destructor overrides a virtual base class destructor, even though their names differ.
- The same non-object-parameter-type-list, that is, the parameter types other than the one corresponding to `this` (with top-level cv already ignored).
- Corresponding object parameters ([[basic.scope.scope#3]]), which compares cv-qualifiers and ref-qualifiers. `void g() const` and `void g()` don't correspond, so there is no override.

Not compared: the return type (constrained separately by ¶8), the exception specification (constrained separately by [[except.spec#5]]), access (footnote 87), default arguments, and `constexpr`.

!!! lawyer "Comparing object parameters across classes"
    The object parameter type of an implicit object member function includes its class: for `B::f` it is `B&`, for `D::f` it is `D&`. Read literally per [[basic.scope.scope#3]], these two types are not the same. The intent of ¶2 is clearly to compare everything except the class, namely the cv-qualifiers and ref-qualifier, and all implementations read it that way.

### The overridden function needn't be visible

¶3 Note 2 says overriding is defined in terms of the class hierarchy and doesn't go through name lookup. In the example below, `D::f(int)` hides `B::f()`, and lookup of `f` in `D2` can't find `B::f()` at all, but `D2::f()` still overrides it:

```cpp run title="override-invisible.cpp" ok
#include <cstdio>
struct B  { virtual void f() { std::puts("B::f"); } virtual ~B() = default; };
struct D  : B { void f(int) {} };       // hides B::f(); D::f(int) is not virtual
struct D2 : D { void f() override { std::puts("D2::f"); } };
int main() {
    D2 d2;
    B& b = d2;
    b.f();        // D2::f
}
```

## The final overrider (¶2, ¶13–¶15)

¶2 goes on to say that, for convenience, any virtual function overrides itself. A virtual member function V of a class object S is a **final overrider** of S unless the most derived class of which S is a base class subobject (if any) has another member function that overrides V.

Intuitively, looking down from the type of the complete object, the function that overrides this subobject's V last is the final overrider, and that is what the virtual call executes.

The last sentence of ¶2 requires uniqueness: in a derived class, if a virtual member function of a base class subobject has more than one final overrider, the program is ill-formed. This rule is computed per subobject, so ordinary and virtual inheritance give different results.

### Ordinary inheritance: each subobject on its own

```cpp run title="final-overrider-nonvirtual.cpp" ok
#include <cstdio>
struct A  { virtual void f() { std::puts("A::f"); } virtual ~A() = default; };
struct B1 : A { void f() override { std::puts("B1::f"); } };
struct B2 : A { void f() override { std::puts("B2::f"); } };
struct D  : B1, B2 {};   // two A subobjects
int main() {
    D d;
    // A* ap = &d;        // error: which A? ambiguous
    A* ap1 = static_cast<B1*>(&d);
    A* ap2 = static_cast<B2*>(&d);
    ap1->f();             // B1::f
    ap2->f();             // B2::f
    // d.f();             // error: name lookup is ambiguous
}
```

`D` contains two `A` subobjects, each with its own `f`. The final overrider for the one in `B1` is `B1::f`, and for the one in `B2` it is `B2::f`; they don't conflict (Example 7 in the standard). Example 2 makes the same point: one side overrides and the other doesn't, so the two subobjects have `C::f` and `A::f` as their respective final overriders.

### Virtual inheritance: a shared subobject can have only one

Virtual inheritance makes two paths share the same `A` subobject. Overriders on the two paths then compete for the same `f`, and there can be two final overriders (¶14, Example 8):

```cpp title="final-overrider-virtual.cpp" error
struct A   { virtual void f(); };
struct VB1 : virtual A { void f(); };
struct VB2 : virtual A { void f(); };
struct Error : VB1, VB2 {};             // error: A::f has two final overriders
struct Okay  : VB1, VB2 { void f(); };  // OK: Okay::f overrides both
```

If only one path overrides `f`, the result can be surprising (¶15, Example 9):

```cpp run title="cross-delegation.cpp" ok
#include <cstdio>
struct A    { virtual void f() { std::puts("A::f"); } virtual ~A() = default; };
struct VB2  : virtual A { void f() override { std::puts("VB2::f"); } };
struct VB1a : virtual A {};       // doesn't declare f
struct Da   : VB1a, VB2 {};
int main() {
    VB1a* p = new Da;
    p->f();       // VB2::f
    delete p;
}
```

In `Da`, the `f` of the shared `A` subobject has only one overrider, `VB2::f`, which is therefore the final overrider. So calling `f` through a `VB1a*` enters a function in the sibling branch `VB2`, even though `VB1a` knows nothing about `VB2`. This is a direct consequence of virtual inheritance sharing the subobject.

### using-declarations don't take part in overriding

```cpp run title="using-and-override.cpp" ok
#include <cstdio>
struct A { virtual void f() { std::puts("A::f"); } virtual ~A() = default; };
struct B : virtual A { void f() override { std::puts("B::f"); } };
struct C : B, virtual A { using A::f; };
int main() {
    C c;
    c.f();        // B::f: lookup finds A::f via the using-declaration, but this is a virtual call
    c.C::f();     // A::f: the qualified name suppresses the virtual call (¶16)
}
```

This is Example 1 in the standard. A using-declaration only introduces a name into `C`'s scope and affects name lookup; the final overrider is still computed from the class hierarchy, and it is `B::f`.

## `override` and `final` (¶4–¶5)

```cpp title="final-override.cpp" error
struct B {
    virtual void f() const final;
    virtual void g(int);
};
struct D : B {
    void f() const;          // error: overrides the final B::f
    void g(long) override;   // error: marked override but overrides nothing
    void g(int) override;    // OK
};
```

¶4 If a virtual function in a base class is marked `final`, any function in a derived class that overrides it makes the program ill-formed. ¶5 If a function marked `override` doesn't override a member function of a base class, the program is ill-formed.

`override` turns "I think this overrides" into a fact the compiler checks, and catches a whole class of signature mistakes: `int` written as `long`, a missing `const`, a base class function that was renamed. Both are contextual keywords with special meaning only at the end of a member function declarator; elsewhere they can still be used as ordinary identifiers.

A few details:

- `final` can be placed on the virtual function that first introduces it (`virtual void f() final;`), so derived classes can't override it. `final` and `override` can appear together.
- Both can appear only in the first declaration of a virtual function, not on an out-of-class definition, and each at most once ([[class.mem.general#19]]). Putting them on a non-virtual function is ill-formed.
- Class-level `final` (`struct D final : B`) forbids deriving from `D` ([[class.pre]]), so none of `D`'s virtual functions can be overridden again, and the compiler can devirtualize based on that.

## Both ends of an override must be compatible

The caller sees only the base class declaration and compiles the call against it. So an overriding function can't break the promises made by the base class declaration. The rules below all follow from that.

### Same ref-qualifier (¶7)

¶7 The overriding function must have the same ref-qualifier (or absence of one) as the overridden function.

```cpp title="ref-qualifier.cpp" error
struct B {
    virtual void g();
    virtual void k() &;
};
struct D : B {
    void g() &;    // error: overrides B::g, but with a different ref-qualifier
    void k() &&;   // doesn't correspond to B::k() &: a new function that hides B::k
};
```

This rule only matters when the correspondence rule lets the pair through. Per [[basic.scope.scope#3]], when exactly one of them is an implicit object member function with no ref-qualifier, the references are stripped before comparing, so `virtual void g();` and `void g() &;` correspond; the latter overrides the former and is then ill-formed because of ¶7. `&` and `&&` don't correspond at all, so that is just hiding.

For `D::g`, Clang reports that functions with the same name with and without a ref-qualifier can't be overloaded, which is the other face of the same rule in [[over.load]]; for `D::k` it only warns about a hidden virtual function.

### No constraints (¶6)

¶6 A virtual function can't have a trailing *requires-clause*. Constraints decide whether a function exists in a given specialization, while the vtable slots must be fixed when the class is defined. If virtual functions of a class template could be constrained, some specializations would have a slot and some wouldn't, and the overriding relationships would vary with whether the constraints were satisfied.

Note that ¶2 ignores trailing *requires-clause*s when deciding overriding. A constrained function in a derived class with a corresponding signature is still identified as an overrider, so it becomes virtual, and is then ill-formed because of ¶6.

### deleted, consteval and noexcept (¶17–¶18)

```cpp title="deleted-consteval.cpp" error
struct B {
    virtual void del() = delete;
    virtual void ok();
    virtual consteval int ce() const { return 1; }
    virtual int rt() const { return 1; }
};
struct D : B {
    void del() override;              // error: non-deleted overrides deleted
    void ok() override = delete;      // error: deleted overrides non-deleted
    int ce() const override { return 2; }   // error
    consteval int rt() const override { return 2; }  // error
};
```

¶17 A deleted function can't override a non-deleted function, and vice versa. If the former were allowed, `b.ok()` would compile but have no function to call at run time; if the latter were allowed, the base class's `= delete` would be meaningless.

¶18 An immediate (`consteval`) function and a non-immediate function can't override each other. An immediate function can only be called at compile time; if it overrode an ordinary virtual function, a virtual call at run time could land on it.

The rule for exception specifications is in [[except.spec#5]]: if a base class virtual function is non-throwing, any function that overrides it must be non-throwing too, unless the overrider is deleted. The other direction (base may throw, overrider `noexcept`) is allowed; promises can only be strengthened.

## Covariant return types (¶8–¶9)

The return type of an overriding function generally has to be the same as that of the overridden function. The exception is for functions like `clone`: the base returns `Base*`, and the derived class wants to return `Derived*` so that calls through a `Derived` don't need another conversion.

¶8 The return type of an overriding function must be either identical to that of the overridden function or **covariant** with it. If `D::f` overrides `B::f`, their return types are covariant if and only if:

- ¶8.1 both are pointers to classes, both are lvalue references to classes, or both are rvalue references to classes. Footnote 88 excludes multi-level pointers and references to multi-level pointers.
- ¶8.2 the class in the return type of `B::f` is the same class as in `D::f`, or is an unambiguous and accessible (direct or indirect) base class of it.
- ¶8.3 both pointers or references have the same cv-qualification, and the class type in the return type of `D::f` has the same or less cv-qualification than the class type in the return type of `B::f`.

¶9 adds two more rules. First, if the classes differ, the class in the return type of `D::f` must be complete at the [[g:locus|locus]] of the overriding declaration, or be `D` itself, which is why `D* clone()` can be written in `D`'s class body. Second, when the overriding function is called as the final overrider, its result is converted to the return type of the statically chosen overridden function ([[expr.call]]).

All these conditions come from the caller's point of view: the call site is compiled against `B::f` and expects an `A1*`. The `A2*` returned by `D::f` has to be convertible to it without the call site knowing anything more. So only pointers or references are allowed (returning by value could change the size), the base must be accessible and unambiguous (otherwise the conversion itself would be invalid), the class must be complete (the compiler needs the base's offset to adjust the pointer), and cv can't be added.

```cpp title="covariance.cpp" error
struct A1 {};
struct A2 : A1 {};
struct A3 : A1 {};
struct Amb : A2, A3 {};      // two A1s
class Priv : private A1 {};
struct Inc;

struct B {
    virtual A1*  p1();
    virtual A1*  p2();
    virtual A1*  p3();
    virtual A1&  r1();
    virtual A1*  p4();
    virtual A1** pp();
    virtual A1*  p5();
    virtual A1   v();
    virtual const A1* c();
    virtual B*   self();
};
struct D : B {
    A2*  p1() override;       // OK
    Amb* p2() override;       // error: A1 is an ambiguous base
    Priv* p3() override;      // error: A1 is a private base
    A2&& r1() override;       // error: lvalue reference vs rvalue reference
    const A2* p4() override;  // error: cv added
    A2** pp() override;       // error: multi-level pointer
    Inc* p5() override;       // error: Inc is incomplete
    A2   v() override;        // error: return by value
    A2*  c() override;        // OK: cv removed
    D*   self() override;     // OK: incomplete, but it is D itself
};
```

The "accessible" in ¶8.2 is judged in the context of the class containing the overriding function. In Example 6 in the standard, with `class D : private B { friend class Derived; };`, `No_good::vf4` can't return `D*`, because in `No_good`, `B` is an inaccessible base of `D`; `Derived` is a friend of `D`, so `Derived::vf4` can.

### Covariant calls adjust the pointer

```cpp run title="covariant-call.cpp" ok
#include <cassert>
struct X { virtual ~X() = default; int x = 1; };
struct Y { virtual ~Y() = default; int y = 2; };
struct Z : X, Y { int z = 3; };   // the Y subobject is not at offset 0

struct B { virtual Y* get() { return nullptr; } virtual ~B() = default; };
struct D : B {
    Z obj;
    Z* get() override { return &obj; }
};
int main() {
    D d;
    B& b = d;
    Y* py = b.get();    // calls D::get; Z* is converted to Y*
    assert(py == static_cast<Y*>(&d.obj));
    assert(py->y == 2);
    Z* pz = d.get();    // D::get is statically chosen; no conversion
    assert(pz == &d.obj);
}
```

Going from `Z*` to `Y*` means adding the offset of the `Y` subobject, so this conversion isn't free. The implementation view section explains how compilers do it with return-adjusting thunks.

## Only the function body is chosen dynamically (¶10)

¶10 (a note) restates the rule of [[expr.call]]: the interpretation of a virtual function call depends on the dynamic type of the object, whereas a non-virtual call depends only on the static type of the pointer or reference.

Put the other way round, everything other than which function body runs is determined by the statically chosen function: name lookup, overload resolution, access checking ([[class.access.virt]]), default arguments ([[dcl.fct.default#10]]), and the type of the call expression ([[expr.call#4]]).

### Default arguments come from the static type

```cpp run title="default-args.cpp" ok
#include <cstdio>
struct A {
    virtual void f(int a = 7) { std::printf("A::f(%d)\n", a); }
    virtual ~A() = default;
};
struct B : A {
    void f(int a = 42) override { std::printf("B::f(%d)\n", a); }
};
int main() {
    B b;
    A& ra = b;
    ra.f();     // B::f(7)
    b.f();      // B::f(42)
}
```

[[dcl.fct.default#10]] says a virtual function call uses the default arguments from the declaration determined by the static type, and an overriding function doesn't inherit the default arguments of the function it overrides. Default arguments are filled in by the compiler at the call site, which only knows the static type; choosing them by dynamic type would mean putting default arguments into the vtable too, which isn't worth the cost. In practice, don't respecify default arguments in overriding functions; clang-tidy has a dedicated check for it.

### Contract assertions {{c++26}}

C++26 contract assertions also have a static part and a dynamic part in virtual calls ([[expr.call#5]]). A virtual function call first checks the preconditions of the statically chosen function, then those of the function actually called; on return it checks the postconditions of the function actually called first, then those of the statically chosen function.

```cpp
struct X1 { virtual void f() pre(a) post(b) {} };
struct Z : X1 { void f() override pre(g) post(h) {} };

void t(X1& x1ref) {      // x1ref refers to a Z
  x1ref.f();             // checks a, g, h, b
  x1ref.X1::f();         // not a virtual call: checks only a, b
}
```

This is an excerpt of Example 1 in [[expr.call]] (`a`, `b` and so on stand for boolean conditions). At the time of writing Clang 23 doesn't support contract syntax, so this code hasn't been verified by compiling it.

## Suppressing the virtual call with a qualified name (¶16)

```cpp run title="qualified-call.cpp" ok
#include <cstdio>
struct B { virtual void f() { std::puts("B::f"); } virtual ~B() = default; };
struct D : B {
    void f() override {
        B::f();       // statically bound to B::f; no infinite recursion
        std::puts("D::f");
    }
};
int main() {
    D d;
    B& b = d;
    b.f();       // D::f → B::f
    b.B::f();    // calls only B::f
}
```

¶16 Explicit qualification with the scope operator suppresses the virtual call mechanism. This is the standard way for an overriding function to call the base class version.

!!! lawyer "Splices and member pointers don't suppress the virtual call"
    The condition in [[expr.call#2]] is that the *id-expression* in the member access is a *qualified-id*. A C++26 *splice-expression* such as `x.[: ^^X1::f :]()` is not a *qualified-id*, so it is still a virtual call, as Example 1 in [[expr.call]] states explicitly. A call through a member pointer, `(x.*pmf)()`, is also a virtual call.

## Declared means defined (¶12)

¶12 A virtual function declared in a class must be defined, or declared pure ([[class.abstract]]), or both; no diagnostic is required.

```cpp title="missing-virtual-def.cpp" ifndr
struct W {
    virtual void f();   // declared only, never defined
    virtual void g() {}
};
int main() { W w; }     // IFNDR: in practice a link error
```

An ordinary function needs a definition only if it is [[g:odr-use|odr-used]]. Virtual functions are different: per [[basic.def.odr#8]], a virtual function that isn't pure is always odr-used, because its address has to go into the vtable, whether or not the program calls it. The definition may be in another translation unit, which the compiler can't check, so the rule requires no diagnostic.

!!! impl "Missing vtable"
    Under the Itanium C++ ABI, the vtable is emitted only in the translation unit that defines the **key function**, the first non-inline, non-pure virtual function of the class. In the example above the key function is `W::f`, which isn't defined, so the vtable is never emitted at all. The linker reports a missing vtable for `W`, not a missing `W::f`. In our tests the linker also adds a hint that a missing vtable usually means the first non-inline virtual function has no definition.

## Virtual calls during construction and destruction

```cpp run title="cdtor-virtual.cpp" ok
#include <cstdio>
struct Base {
    Base()  { who(); }
    virtual void who() { std::puts("Base::who"); }
    virtual ~Base() { who(); }
};
struct Der : Base {
    Der()   { who(); }
    void who() override { std::puts("Der::who"); }
    ~Der() override { who(); }
};
int main() { Der d; }
// output: Base::who / Der::who / Der::who / Base::who
```

A virtual call on the object under construction or destruction inside a constructor or destructor executes the final overrider in the constructor's or destructor's own class ([[class.cdtor#4]]). While the `Base` subobject is being constructed, `Der`'s members aren't initialized yet; entering `Der::who` at that point would read uninitialized members. So during `Base`'s construction, the object behaves as if it were a `Base`.

If the final overrider in that class is a pure virtual function, the behavior is undefined ([[class.abstract#6]]); the familiar "pure virtual function called" crash comes from here.

## Virtual functions in constant evaluation

```cpp run title="constexpr-virtual.cpp" ok
struct Shape {
    constexpr virtual int sides() const { return 0; }
    constexpr virtual ~Shape() = default;
};
struct Tri : Shape {
    constexpr int sides() const override { return 3; }
};
constexpr int count() {
    Shape* p = new Tri;    // dynamic allocation in constant evaluation
    int n = p->sides();    // virtual call
    delete p;              // virtual destructor
    return n;
}
static_assert(count() == 3);

struct CB { virtual consteval int id() const { return 1; } };
struct CD : CB { consteval int id() const override { return 2; } };
consteval int cid() { CD d; const CB& b = d; return b.id(); }
static_assert(cid() == 2);

int main() {}
```

Since C++20, virtual functions can be `constexpr`, and virtual calls can be made during constant evaluation ([[P1064R0]]), because the constant evaluator always knows an object's dynamic type.

The exception is objects whose dynamic type is unknown. When constant evaluation refers to an object whose lifetime didn't begin within the evaluation and which isn't usable in constant expressions, its dynamic type is constexpr-unknown, and a virtual call on it is not a constant expression ([[expr.const.core#2.6]]). For example, in `constexpr int k = via(s);`, where `via` calls `s.sides()` on its reference parameter `s`, Clang reports `virtual function called on object 's' whose dynamic type is not constant`.

## Implementation view

!!! impl "vptr and vtable"
    All mainstream implementations implement virtual functions with **virtual function tables** (vtables). Each polymorphic class has one static table (or a group of them) of function pointers, and each polymorphic object (or subobject) stores a **vtable pointer** (vptr) to it. A virtual call is: read the vptr, fetch the function pointer from a fixed slot, call indirectly. The standard doesn't use the word vtable, but many of its rules follow from this model:

    - Member function templates can't be virtual: the table size has to be fixed.
    - The current class's version is called during construction: each level's constructor sets the vptr to its own class's vtable on entry.
    - Default arguments go by static type: default arguments aren't in the table.
    - [[basic.life]] forbids virtual calls, `dynamic_cast` and conversion to a virtual base outside an object's lifetime: all of these read the vptr.

!!! impl "Itanium C++ ABI vtable layout"
    GCC and Clang use the Itanium ABI on non-Windows platforms. The vptr points to an **address point** in the table; before the address point come, in order, vcall offsets, vbase offsets, offset-to-top (the offset from this subobject to the start of the complete object) and the RTTI pointer; after it come the virtual function pointers. The destructor takes two slots: the complete object destructor only destroys, and the deleting destructor destroys and then calls `operator delete`, which is how `delete p` finds the right deallocation function.

    Clang 23 with `-Xclang -fdump-vtable-layouts` prints the vtable of `struct C : A, B`, where `A` has a virtual function `f`, a virtual destructor and an `int` member, `B` has a virtual function `g`, and `C` overrides `f` and `g`:

    ```text
    Vtable for 'C' (9 entries).
       0 | offset_to_top (0)
       1 | C RTTI
           -- (A, 0) vtable address --
           -- (C, 0) vtable address --
       2 | void C::f()
       3 | C::~C() [complete]
       4 | C::~C() [deleting]
       5 | void C::g()
       6 | offset_to_top (-16)
       7 | C RTTI
           -- (B, 16) vtable address --
       8 | void C::g()
           [this adjustment: -16 non-virtual] method: void B::g()
    ```

    `A` is the primary base and shares one vptr and the first half of the table with `C`. The `B` subobject is at offset 16 and has its own vptr, pointing into a secondary vtable.

!!! impl "Thunks"
    When `g()` is called through a `B*`, `this` points to the `B` subobject at offset 16, while `C::g` expects `this` to point to the whole `C`. So the slot in the secondary table doesn't point directly to `C::g` but to a **this-adjusting thunk**: subtract 16 from `this`, then jump to `C::g`, which is the `[this adjustment: -16 non-virtual]` above. If the base is a virtual base, the offset isn't known at compile time, and the thunk first reads a vcall offset from the vtable before adjusting.

    Covariant returns need a **return-adjusting thunk** working in the opposite direction: call the real function first, then adjust the returned pointer. For `D` in `covariant-call.cpp` above, Clang 23's output is:

    ```text
       2 | Z *D::get()
           [return adjustment: 16 non-virtual] method: Y *B::get()
       3 | Z *D::get()
    ```

    `D`'s table has two `get` slots: the one inherited from `B` returns `Y*` via the thunk, and the new one added by `D` returns `Z*` directly, for virtual calls through a `D*`. ¶9 requires the class in the return type to be complete at the overriding declaration precisely because generating the thunk requires knowing the offset.

!!! impl "MSVC"
    MSVC's vtable has no offset-to-top; RTTI is obtained through a complete object locator in the slot before the table. Virtual base offsets are kept in a separate vbtable pointed to by a separate vbptr. The destructor takes only one slot in the table, a scalar deleting destructor that uses a flag parameter to decide whether to free memory. Covariant returns and this adjustment are also implemented with thunks.

!!! impl "Devirtualization"
    When the compiler can determine an object's dynamic type, it can turn a virtual call into a direct call and then inline it. Common grounds are: the class or function is marked `final`; the object is a local variable or was just created by `new`; whole-program analysis (LTO with `-fwhole-program-vtables` and so on) proves a virtual function has only one overrider; GCC's speculative devirtualization compares the vptr with the expected table and calls directly if they match.

    Clang 23 at `-O2` (x86-64 target) with `struct D final : B`, for comparison:

    ```text
    call_b(B const&):          # through B&: read the vptr, jump indirectly
        movq    (%rdi), %rax
        jmpq    *(%rax)
    call_d(D const&):          # through a reference to the final class D: direct tail call
        jmp     D::f() const
    ```

    The rules in [[basic.life]] that an object's dynamic type doesn't change during its lifetime, and that `std::launder` is needed otherwise, are the basis for such optimizations.

## History

!!! history
    - C++98 already had virtual functions, pure virtual functions and covariant return types.
    - C++11 added `override` and `final`. They are contextual keywords and took no new reserved words, so old code using those names as identifiers is unaffected. Deleted functions and ref-qualifiers, added at the same time, brought ¶17 and ¶7.
    - C++20 allows `constexpr` virtual functions and virtual calls in constant evaluation ([[P1064R0]]); `consteval` brought ¶18, and concepts brought ¶6.
    - C++23's deducing this ([[P0847R7]]) introduced explicit object member functions and specified that they can't be virtual.
    - C++26 {{c++26}} specifies the order in which contract assertions are checked in virtual calls; member calls made through a *splice-expression* are still virtual calls.

## Common misconceptions

!!! pitfall "If the signature looks the same, it's an override"
    A difference anywhere in `const`, the ref-qualifier or a parameter type (`int` vs `long`, `T&` vs `const T&`) gives hiding instead of overriding, with no error. Always write `override`.

!!! pitfall "An overriding function can use a different default argument"
    You can write one, but calls through the base class still use the default argument from the base declaration, so the same function body gets different arguments depending on how it is called.

!!! pitfall "Deleting through a base class pointer is always safe"
    When the base class has no virtual destructor, deleting a derived object through a base pointer is UB ([[expr.delete#3]]). The destructor of a polymorphic base class should be either public and virtual, or protected and non-virtual.

!!! pitfall "A using-declaration can change which function gets called"
    A using-declaration affects only name lookup. `c.f()` still calls the final overrider; only a qualified call such as `c.C::f()` lands on the function brought in by the using-declaration.

!!! pitfall "A member function template can override a virtual function"
    A specialization of a member function template doesn't override a base class virtual function ([[temp.mem#4]]), and the template itself can't be virtual.

## Questions

!!! question "Question 1"
    ```cpp
    struct B { virtual void f(int = 1); };
    struct D : B { void f(int = 2) override; };
    struct E : D { void f(int) override; };
    void t(E& e) { D& d = e; B& b = e; e.f(); d.f(); b.f(); }
    ```
    Which calls in `t` are valid? For the valid ones, which function is called, and with what argument?

<details markdown="1">
<summary>Answer</summary>

`e.f()` is ill-formed: `E::f` in the static type `E` has no default argument, overriding functions don't inherit default arguments, and there are too few arguments. Clang reports `too few arguments to function call`.

`d.f()` is valid and calls `E::f(2)`: the function is chosen by the dynamic type, and the default argument comes from the declaration in the static type `D`. `b.f()` is valid and calls `E::f(1)`.
</details>

!!! question "Question 2"
    Is the following program valid? If so, what does `p->f()` call?
    ```cpp
    struct A { virtual void f(); };
    struct B : virtual A { void f() override; };
    struct C : virtual A { };
    struct D : B, C { };
    void g(C* p) { p->f(); }   // p points to the C subobject of some D object
    ```

<details markdown="1">
<summary>Answer</summary>

Valid. `A` is a virtual base, so `D` contains only one `A` subobject, and its `f` has only one final overrider in `D`, `B::f` (`C` doesn't override it), so uniqueness holds.

`p->f()` statically selects `A::f` inherited through `C`, and at run time calls the final overrider `B::f`, even though `C` and `B` are unrelated. In implementations, in the secondary table of `D`'s vtable for the `C` subobject, the slot for `f` points to a thunk that adjusts `this` from the `C` subobject to the `B` subobject and then calls `B::f`.
</details>

!!! question "Question 3"
    Why does ¶9 allow `struct D : B { D* clone() override; };` (where `D` is still incomplete) but not returning a pointer to an incomplete class unrelated to `D`?

<details markdown="1">
<summary>Answer</summary>

A covariant return has to convert the returned pointer to the base class's return type, so the compiler must know the offset of the base within the return type, and whether the conversion is accessible and unambiguous. Whether the vtable needs a new slot and whether a return-adjusting thunk is needed must also be decided at that point.

For an incomplete class unrelated to `D`, none of this information exists yet at the overriding declaration. `D` itself is incomplete inside its class body, but its base class list is already fixed at the *base-clause*, so the offsets and accessibility of its base class subobjects can be computed; that is why the standard allows this case specifically.
</details>
