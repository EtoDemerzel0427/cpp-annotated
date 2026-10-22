---
title: Abstract classes
summary: "How pure virtual functions are written and when they need a definition; which classes are abstract and where abstract types may appear; and why a virtual call to a pure virtual function during construction or destruction is undefined behavior."
updated: 2026-10-19
---

!!! tldr
    - A virtual function declared with `= 0` is a pure virtual function; as long as the final overrider of some pure virtual function is still pure, the class is abstract and can't have objects of its own.
    - A pure virtual function can have a definition (written outside the class), which is needed only when it is called with a qualified name like `Base::f()`; a pure virtual destructor, however, must always be defined.
    - A derived class that forgets to override a pure virtual function becomes abstract itself; a pure virtual function can also override a virtual function that already has an implementation, making the class abstract again.
    - Since C++20, whether a parameter or return type is an abstract class is checked only at function definitions and function calls; plain declarations aren't restricted.
    - In an abstract class's constructor or destructor, making a virtual call, directly or indirectly, to a pure virtual function is undefined behavior; the usual symptom is "pure virtual function called" followed by program termination.

```cpp error
struct Shape {
    virtual double area() const = 0;   // pure virtual function
    virtual ~Shape() = default;
};
struct Square : Shape {
    double side = 1;
    double area() const override { return side * side; }
};
Square sq;          // OK
Shape* p = &sq;     // OK: pointer to an abstract class
Shape s;            // error: Shape is an abstract class
```

`Shape` represents only a general concept; what is meaningful are its concrete variants. The note in ¶1 describes exactly this use: an abstract class represents a general concept, or defines an interface for which derived classes provide different implementations. C++ has no `interface` keyword; an abstract class whose member functions are all pure virtual and that has no data members amounts to an interface.

C++ doesn't declare abstractness with a keyword either; it is inferred from pure virtual functions. Reading this page requires knowing what overriding and final overriders mean; see [[class.virtual]].

## Pure virtual functions (¶2)

¶2 Writing a ***pure-specifier*** (`= 0`) in a function declaration in a class definition makes the virtual function a **pure virtual function**. A class with at least one pure virtual function is an **abstract class**; ¶4 makes this definition more precise.

The syntactic details of `= 0` are in [[class.mem.general]]:

- The token sequence must be exactly `= 0`; `= 0L`, `= false` and `= nullptr` don't work.
- It can only be used in the declaration of a virtual function, not in a friend declaration ([[class.mem.general#17]]).
- It comes last: the declarator, the *virt-specifier-seq* (`override`, `final`), C++26 contract specifiers (`pre`, `post`), and only then `= 0`, as in `void f() override = 0;`.

```cpp title="pure-specifier.cpp" error
struct A {
    virtual void f() = 0;            // OK
    virtual void g() = 0L;           // error: not a pure-specifier
    void h() = 0;                    // error: non-virtual function
    virtual void k() override = 0;   // error: overrides nothing
};
struct B : A {
    void f() override = 0;           // OK: overrides, and is still declared pure
};
```

¶2 Note 3 points out that an abstract class can be used only as a base class of some other class: no objects of an abstract class can be created except as base class subobjects of a derived class object.

### A pure virtual function can have a definition

```cpp run title="pure-default-impl.cpp" ok
#include <cstdio>
struct Shape {
    virtual void draw() const = 0;
    virtual ~Shape() = default;
};
void Shape::draw() const {      // definition of a pure virtual function
    std::puts("Shape: outline");
}
struct Circle : Shape {
    void draw() const override {
        Shape::draw();          // qualified call, uses the definition above
        std::puts("Circle: fill");
    }
};
int main() {
    Circle c;
    const Shape& s = c;
    s.draw();
}
```

¶2 ends by saying that a pure virtual function needs to be defined only if it is called with, or as if with, the *qualified-id* syntax (see the next subsection). A virtual call never lands on a pure virtual function, so its definition can only be reached through a qualified call like `Shape::draw()`.

What this expresses is: derived classes must decide the behavior themselves, but may choose to reuse a default implementation. An ordinary virtual function lets a derived class inherit the default behavior by writing nothing; a pure virtual function with a definition is a stronger constraint.

¶2 Note 4 says a single declaration can't have both `= 0` and a function body, so the definition must be written outside the class:

```cpp error
struct C {
    virtual void f() = 0 { }   // error
};
```

### A pure virtual destructor must be defined

```cpp run title="pure-virtual-dtor.cpp" ok
#include <cstdio>
struct Interface {
    virtual ~Interface() = 0;   // makes the class abstract
};
Interface::~Interface() { std::puts("~Interface"); }   // must be defined

struct Impl : Interface {};     // Impl::~Impl overrides it, so Impl is not abstract

int main() { Impl i; }          // prints ~Interface
```

When a class has no suitable member function to make pure but should still be abstract, the usual trick is to declare the destructor pure virtual.

The "as if called with a qualified name" in the previous subsection refers to destructors. After a derived class's destructor runs its own body, it calls the destructors of its bases as if with qualified names, without virtual dispatch ([[class.dtor]]). So a pure virtual destructor is always called. [[class.dtor#11]] also says directly that if a destructor is virtual and the program creates an object of that class or a derived class, the destructor must be defined. Forgetting the definition shows up under the Itanium ABI as a link error about a missing `Interface::~Interface()`.

## Abstractness is inherited (¶4–¶5)

¶4 gives the precise definition: a class is abstract if and only if it has at least one pure virtual function whose final overrider is pure virtual.

So when a derived class doesn't override all the pure virtual functions, it is still abstract. This is the full version of Example 3 in the standard:

```cpp run title="abstract-inherit.cpp" ok
#include <type_traits>
class shape {
public:
    virtual void rotate(int) = 0;
    virtual void draw() = 0;
    virtual ~shape() = default;
};
class ab_circle : public shape {
public:
    void rotate(int) override {}
    // doesn't override draw: the final overrider is still the pure shape::draw
};
class circle : public shape {
public:
    void rotate(int) override {}
    void draw() override {}
};
static_assert(std::is_abstract_v<shape>);
static_assert(std::is_abstract_v<ab_circle>);
static_assert(!std::is_abstract_v<circle>);
int main() { circle c; (void)c; }
```

¶5 (a note) points out two possibilities in the other direction: an abstract class can be derived from a class that is not abstract, and a pure virtual function can override a virtual function that is not pure. The latter turns a virtual function that already has an implementation back into a pure one, forcing classes further down to reimplement it:

```cpp run title="re-abstract.cpp" ok
#include <type_traits>
struct Concrete {
    virtual int f() { return 1; }
    virtual ~Concrete() = default;
};
struct Abs : Concrete { int f() override = 0; };
struct Again : Abs { int f() override { return 3; } };
static_assert(!std::is_abstract_v<Concrete>);
static_assert(std::is_abstract_v<Abs>);
static_assert(!std::is_abstract_v<Again>);
int main() { Again a; return a.f() == 3 ? 0 : 1; }
```

!!! lawyer "Relative to which class is the final overrider computed"
    When deciding whether class X is abstract, the final overrider is computed with X itself as the most derived class. With virtual inheritance, a pure virtual function may be overridden on only one branch:

    ```cpp
    struct A { virtual void f() = 0; };
    struct B : virtual A { void f() override; };
    struct C : virtual A {};
    struct D : B, C {};
    ```

    In `C`, the final overrider of `A::f` is the pure `A::f`, so `C` is abstract. In `D`, the final overrider of `f` for the shared `A` subobject is `B::f`, so `D` is not abstract.

## Where abstract types can appear (¶3)

The starting point is that what's restricted is creating objects of an abstract type, not mentioning the type. The note in ¶3 gathers the normative rules scattered across the standard:

```cpp title="abstract-uses.cpp" error
struct A { virtual void f() = 0; };

A make();                    // OK: just a declaration
void take(A);                // OK: just a declaration
struct S { A g(); };         // OK: member function declaration
using F = A(A);              // OK: function type
using T = decltype(make());  // OK: decltype creates no temporary
A* p;                        // OK
void ref(A& r);              // OK

A make2() { }                // error: return type of a function definition
void use(A& a) { take(a); }  // error: the parameter is of abstract type at the call
A arr[2];                    // error: array object of abstract type
void h() { A{}; }            // error: result of an explicit type conversion
```

| Context | Allowed? | Basis |
|---|---|---|
| Parameter or return type of a function definition | No, except for deleted functions | [[dcl.fct.def.general#2]] |
| By-value parameter in a function call | No | [[expr.call#7]] |
| Parameter or return type of a function that is only declared (not defined) | Yes (since C++20) | |
| Explicit type conversion `A()`, `A{}`, `static_cast<A>(x)` | No; the result would be a prvalue of abstract type | [[basic.lval#9]] |
| Variable definition, `new A`, non-static data member | No, and not arrays of them either | [[basic.def#5]], [[expr.new]], [[class.mem.general#20]] |
| An array `A[2]` used only as a type | Yes ([[dcl.array]] doesn't forbid it) | |
| A call returning an abstract type as the operand of `decltype` | Yes | [[dcl.type.decltype#2]] |
| Pointers, references, `sizeof`, `typeid`, `std::is_abstract` | Yes | |

`decltype(make())` works because when the operand of `decltype` is a function call, the prvalue isn't materialized into a temporary, so no object is created ([[dcl.type.decltype#2]]). The "except as specified in [dcl.type.simple]" in the note in ¶3 refers to this exception.

!!! impl "Where Clang deviates"
    Under the current [[dcl.array]], `using X = A[2];`, used only as a type, creates no object and should be valid. At the time of writing, Clang 23 still rejects it with `array of abstract class type`. Also, Clang accepts the declaration-only uses above even with `-std=c++17`, without distinguishing language versions.

### Why C++20 relaxed this

In C++17 and earlier, an abstract type couldn't be a function's parameter or return type at all, even in a mere declaration. That caused two problems.

The first is timing. A class is complete only at its closing brace, and until then it isn't known whether it is abstract. In `struct A { A f(); virtual void g() = 0; };`, when the compiler sees `A f();` it doesn't yet know `A` is abstract, so it can only check retroactively, and compilers handled this inconsistently.

The second is unexpected errors in templates. Instantiating a function that is only declared, such as `T f();` in some trait, could produce a hard error because `T` is abstract, even though the function is never defined or called.

[[P0929R2]] postpones the check to where an object is actually needed, namely function definitions and function calls. Incomplete types have always been handled this way: they can appear in function declarations and must be complete only at definitions or calls. Abstractness is now treated as another reason objects can't be created, on the same footing as incompleteness.

## Calling pure virtual functions during construction and destruction (¶6)

```cpp run title="pure-call.cpp" ub
#include <cstdio>
struct Base {
    Base() { init(); }        // indirect call
    void init() { hook(); }   // virtual call; the final overrider in Base is pure
    virtual void hook() = 0;
    virtual ~Base() = default;
};
struct Der : Base {
    void hook() override { std::puts("Der::hook"); }
};
int main() { Der d; }         // UB
```

¶6 Member functions can be called from a constructor or destructor of an abstract class; but the effect of making a virtual call, directly or indirectly, to a pure virtual function for the object being created or destroyed from such a constructor or destructor is undefined.

The reason is in [[class.cdtor#4]]: virtual calls during construction and destruction land on the final overrider in the current class. While the `Base` subobject is being constructed, the final overrider of `hook` in `Base` is the pure `Base::hook` itself, and there is no function body to run. Even if `Base::hook` has a definition, a virtual call won't select it.

The UB applies only to virtual calls. If `Base::hook` has a definition, writing `Base::hook()` in the constructor is an ordinary qualified call and is perfectly valid.

Compilers can catch direct calls: change the example to `Base() { hook(); }` and Clang gives a `-Wcall-to-pure-virtual-from-ctor-dtor` warning. An indirect call through an ordinary member function, as in the example, usually goes undetected.

!!! impl "What happens in practice"
    The Itanium ABI fills the vtable slots of pure virtual functions with the runtime library function `__cxa_pure_virtual`. While the `Base` subobject is being constructed, the vptr points to `Base`'s vtable, so the example calls this function, which prints a message and terminates the program. In our tests (libc++abi) the output is:

    ```text
    libc++abi: Pure virtual function called!
    ```

    The corresponding function in MSVC is `_purecall`. But this is UB, and the optimizer may make other assumptions as well, such as treating the path as unreachable.

## Implementation view

!!! impl
    - An abstract class still has a vtable, because the vptr has to point to it during construction and destruction, with pure slots filled with `__cxa_pure_virtual`. If every virtual function of a class is either pure or inline, it has no key function under the Itanium ABI, and its vtable is emitted as a COMDAT in every translation unit that uses it, to be merged by the linker.
    - MSVC provides `__declspec(novtable)`, which tells the compiler the class will never be instantiated directly. Its constructors can then skip setting the vptr, saving a store, and if nothing else refers to the vtable it can be dropped entirely. The cost is that a virtual call in its constructor reads an invalid vptr.

## History

!!! history
    - C++98 already had pure virtual functions and abstract classes. Back then, abstract types couldn't appear as function parameter types, return types or array element types, even in mere declarations.
    - Since C++11, `override` can be written together with `= 0`: `void f() override = 0;`.
    - C++20's [[P0929R2]] postponed the abstract type checks to function definitions and function calls, consistent with incomplete types; array element types are no longer forbidden from being abstract classes.
    - In C++26 {{c++26}}, contract specifiers go between the *virt-specifier-seq* and `= 0`.

## Common misconceptions

!!! pitfall "A pure virtual function can't have a body"
    It can; a virtual call just won't use it, so it can only be called with a qualified name. A pure virtual destructor must have a definition.

!!! pitfall "Missing an override of a pure virtual function is an immediate error"
    It isn't. The derived class just quietly becomes abstract, and the error appears only when someone creates an object of it, possibly far from the class definition. Writing `static_assert(!std::is_abstract_v<D>)` for a derived class catches it earlier; marking every overriding function `override` rules out signature mistakes that cause a missed override.

!!! pitfall "It's safe as long as the constructor doesn't call the pure virtual function directly"
    An indirect call through an ordinary member function is just as much UB, and compilers usually don't warn about it.

## Questions

!!! question "Question 1"
    Given `struct A { virtual ~A() = 0; };` with no definition for `~A`, are the following two programs OK? (a) `int main() { A* p = nullptr; }`; (b) `struct B : A {}; int main() { B b; }`.

<details markdown="1">
<summary>Answer</summary>

(a) Fine. The program creates no object of `A` or a derived class, so [[class.dtor#11]] doesn't require a definition; and a pure virtual function isn't odr-used merely because it is virtual ([[basic.def.odr#8]]).

(b) Not fine. It creates a `B` object; `B`'s destructor is defined and calls `A::~A` as if with a qualified name. `A::~A` is odr-used but not defined, which violates the ODR, no diagnostic required. In practice it is a link error about a missing `A::~A()`.
</details>

!!! question "Question 2"
    Why does [[expr.call]] check whether a parameter is of abstract type only at the call, and not at the function declaration? Give an example where this relaxation is useful in practice.

<details markdown="1">
<summary>Answer</summary>

Only a call needs to create objects for by-value parameters; a declaration by itself creates no object.

There are two kinds of practical use. One is helper functions in metaprogramming that are declared but never defined, such as `template<class T> T make();`, used only in `decltype(make<A>())`; in C++17 this could produce a hard error when `T` is abstract. The other is declaring, in a class body, a member function that returns the class type itself (`A clone() const;`), when whether the class is abstract is known only at the closing brace; in C++17 this led to inconsistencies in when the check happened.
</details>
