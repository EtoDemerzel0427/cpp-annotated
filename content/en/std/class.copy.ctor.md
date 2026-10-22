---
title: Copy/move constructors
summary: "Which constructors are copy or move constructors (templates never are), when the compiler implicitly declares them, deletes them or makes them trivial, and what the implicitly-defined versions do member by member."
updated: 2026-10-19
---

!!! tldr
    - A non-template constructor whose first parameter is `cv X&` is a copy constructor, and one whose first parameter is `cv X&&` is a move constructor; all other parameters must have default arguments. A constructor template is never a copy or move constructor.
    - The implicit copy constructor is usually `X(const X&)`; when some subobject can only be copied from a non-const lvalue, it degrades to `X(X&)`.
    - If the user declares any of the copy constructor, copy assignment, move assignment or destructor, no move constructor is implicitly declared, and rvalues use the copy constructor instead.
    - The implicitly-defined copy/move constructor copies or moves bases and members one by one in declaration order, ignoring default member initializers; for a union it copies the bytes and starts the lifetime of the corresponding members in the target.
    - When a non-const lvalue is matched against `template<class T> X(T&&)`, the template is a better match than the copy constructor: this is how forwarding constructors hijack copies.

The copy constructor and move constructor decide what happens when one object is initialized from another of the same type: `T b = a;`, `T b(std::move(a));`, pass-by-value and return-by-value when the copy can't be elided, and container growth. This subclause is structured almost exactly in parallel with [[class.copy.assign]]; for an overview of all special member functions see [[special]].

## Which constructors are copy/move constructors (¶1–¶3)

```cpp run title="copy-ctor-forms.cpp" ok
struct X {
    X(int) { }
    X(const X&, int = 1) { }   // copy constructor
};

int main() {
    X a(1);      // X(int)
    X b(a, 0);   // X(const X&, int)
    X c = b;     // X(const X&, int), as the copy constructor
    (void)c;
}
```

¶1 A **non-template** constructor of class `X` is a **copy constructor** if its first parameter is of type `X&`, `const X&`, `volatile X&` or `const volatile X&`, and either there are no other parameters or all other parameters have default arguments.

¶2 Replace the lvalue references above with rvalue references `X&&`, `const X&&` and so on, and you have a **move constructor**.

```cpp run title="move-ctor.cpp" ok
#include <cstdio>
#include <utility>

struct Y {
    Y() { }
    Y(const Y&) { std::puts("copy"); }
    Y(Y&&)      { std::puts("move"); }
};

Y f(int) { return Y(); }

int main() {
    Y d(f(1));          // calls neither: the prvalue initializes d directly
    Y e = d;            // copy: d is an lvalue
    Y g = std::move(e); // move: xvalue
    (void)g;
}
```

Example 2 in the standard still comments `Y d(f(1));` with "calls Y(Y&&)". Since C++17, the prvalue `f(1)` initializes `d` directly and neither the copy nor the move constructor is called ([[dcl.init]]); in our tests the output is just the two lines `copy` and `move`.

¶3 Note 1 says all the forms can be declared together in the same class. `X(const X&&)` is valid but usually pointless, because resources can't be taken out of a const object. One of its few uses is to write it `= delete` to forbid construction from const rvalues.

## A template is never a copy constructor

¶1 and ¶2 both require a non-template. A constructor template is not a copy constructor, even if one of its specializations happens to have the signature `X(const X&)`. This has two consequences:

1. A constructor template doesn't suppress the declaration of the implicit copy constructor;
2. But in overload resolution, a template specialization may be a better match than the implicit copy constructor, and get selected.

The commonest form of the second point is a forwarding-reference constructor:

```cpp run title="forwarding-hijack.cpp" ok
#include <cstdio>
#include <string>

struct P {
    std::string s;
    P(const char* p) : s(p) { }
    template<class T>
    P(T&&) { std::puts("template"); }
    P(const P& o) : s(o.s) { std::puts("copy"); }
};

int main() {
    P a("x");
    P b = a;          // template
    const P c("y");
    P d = c;          // copy
    (void)b; (void)d;
}
```

For the non-const lvalue `a`, the template deduces `T = P&` and yields `P(P&)`. It doesn't need to add const to the argument, so it is a better match than `P(const P&)` and is selected. For the const lvalue `c` the two are equally good, and then the non-template wins ([[over.match.best]]).

If the template body were `s(std::forward<T>(t))`, initializing a `std::string` from a `P&` would fail to compile; worse, it might compile with the wrong semantics. The fix is to constrain the template to exclude `P` itself:

```cpp
template<class T>
    requires (!std::is_same_v<std::remove_cvref_t<T>, P>)
P(T&& t);
```

To exclude classes derived from `P` as well, use `!std::is_base_of_v<P, std::remove_cvref_t<T>>` instead.

## No `X(X)` (¶5)

```cpp title="X-of-X.cpp" error
struct Bad {
    Bad(Bad);   // error: the first parameter must be a reference
};
```

¶5 A constructor declaration is ill-formed if its first parameter is of type `cv X` by value and either there are no other parameters or all other parameters have default arguments. Taking an `X` by value requires copying the argument first, and the copy would call this very constructor.

A member function template is never instantiated to produce such a signature either:

```cpp run title="no-X-of-X.cpp" ok
struct S {
    template<typename T> S(T) { }
    S() { }
};

S g;

int main() {
    S a(g);   // does not instantiate S::S<S>(S); uses the implicit copy constructor
    (void)a;
}
```

Without this rule, `S a(g);` would deduce `T = S` and get `S(S)`; taking `g` by value would require copying `g`, which would select the template again.

## The implicitly-declared copy constructor (¶4, ¶6–¶7)

¶6 If a class has no **user-declared** ([[g:user-declared]]) copy constructor and is not an anonymous union, the compiler implicitly declares a non-explicit copy constructor:

- if the class definition declares a move constructor or move assignment operator, it is **defined as deleted** (as if `= delete`);
- otherwise it is **defaulted** (its definition is generated by the compiler, [[dcl.fct.def]]). In that case, if the class has a user-declared copy assignment operator or destructor, this implicit generation is deprecated ([[depr.impldec]]).

¶7 The implicit copy constructor usually has the form `X::X(const X&)`. Only when some **potentially constructed subobject** ([[g:potentially-constructed-subobjects]], the direct bases, non-static data members and virtual bases) of class type has no copy constructor accepting `const M&` (or `const volatile M&`) does it degrade to `X::X(X&)`.

```cpp title="implicit-copy-form.cpp" error
struct M { M() { } M(M&) { } };   // can only be copied from non-const lvalues
struct X { M m; };                // implicit copy constructor is X(X&)

X x1;
const X cx{};
X x2 = x1;      // OK
X x3 = cx;      // error: X(X&) can't accept a const X
```

It degrades rather than being deleted because copying `m` memberwise calls `M(M&)`, which only requires the source not to be const. Keeping `X(X&)` means copying from non-const lvalues still works.

¶4 Note 2 is about exactly such classes: a class with only `X(X&)` can't be copied from a const or volatile initializer. C++98's `std::auto_ptr` was like this; its copy constructor modified the source to transfer ownership. C++11 move semantics were designed for exactly this kind of need.

!!! lawyer "volatile objects can't be copied implicitly"
    Footnote 82 points out that a `const X&` parameter can't bind to a volatile lvalue, so `volatile X vx; X y = vx;` is ill-formed. If you need it, declare `X(const volatile X&)` yourself. C allows copying from a volatile struct; this is one of the C/C++ incompatibilities listed in [[diff.class]].

## The implicitly-declared move constructor (¶8–¶9)

¶8 If a class has no user-declared move constructor, a non-explicit defaulted move constructor is implicitly declared if and only if all of the following hold:

- ¶8.1 it is not an anonymous union;
- ¶8.2 there is no user-declared copy constructor;
- ¶8.3 there is no user-declared copy assignment operator;
- ¶8.4 there is no user-declared move assignment operator;
- ¶8.5 there is no user-declared destructor.

¶9 Its form is `X::X(X&&)`.

The conditions are this strict because a user declaring any of copy, assignment or destruction often means the class manages a resource, where moving member by member is quite likely wrong. For example, if the destructor `delete`s a raw pointer member, a memberwise move just copies the pointer and the two objects free it twice. So C++11 generates move operations only when the user has customized nothing.

Note 3 explains the consequence when it isn't generated: a place that would have called the move constructor may call the copy constructor instead, because `const X&` can also bind to rvalues. That is slower, but correct.

## When they are defined as deleted (¶10–¶11)

¶10 An implicitly-declared copy/move constructor is an inline public member of its class. A defaulted copy/move constructor for class `X` is defined as deleted if `X` has any of the following:

- ¶10.1 a potentially constructed subobject `M` (or multidimensional array thereof) that can't be copied/moved: overload resolution to choose its constructor finds no usable candidate; or it is a **variant member** ([[g:variant-member]], a member of a union) and the selected function is non-trivial.
- ¶10.2 a potentially constructed subobject whose destructor is deleted or inaccessible.
- ¶10.3 for the copy constructor only: a non-static data member of rvalue reference type.

```cpp title="copy-ctor-deleted.cpp" error
#include <string>
#include <utility>

union U {
    std::string s;
    int i;
    U() : i(0) { }
    ~U() { }
};
U u1;
U u2 = u1;               // error: ¶10.1

struct RR { int&& r; };
int g = 1;
RR r1{std::move(g)};
RR r2 = r1;              // error: ¶10.3
RR r3 = std::move(r1);   // OK
```

The variant member clause of ¶10.1 is the rule for unions. A union doesn't know which member is active and can only copy bytes (¶16), so as soon as some member (such as `std::string`) has a non-trivial copy constructor, the union's copy constructor is deleted.

The reason for ¶10.2 is the same as for the default constructor ([[class.default.ctor#2]]): if an exception is thrown partway through construction, the subobjects already constructed have to be destroyed.

The reason for ¶10.3: in a copy constructor, `x.r` read through a `const X&` is an lvalue and can't directly initialize the new object's rvalue reference member. The move constructor handles it with `static_cast<T&&>(x.r)` per ¶15.2, so `r3` is valid.

Note 4: a defaulted move constructor that is defined as deleted is ignored by overload resolution ([[over.match]], [[over.over]]). Otherwise it would block rvalue initializations that the copy constructor could perform. See `deleted-move-ignored.cpp` in [[special]] for an example.

¶11 Note 5: a derived class `C` inheriting base class constructors with a *using-declaration* never suppresses the implicit declaration of `C`'s own copy/move constructors. Moreover, an inherited constructor whose parameter is a reference to the base is not used to construct a `C` from a single object of the same type ([[over.match.funcs.general#9]] excludes it from the candidates).

## Trivial copy/move constructors (¶12)

```cpp run title="trivial-copy.cpp" ok
#include <type_traits>
#include <string>

struct A { int x; std::string* p; };
struct B { std::string s; };
struct C { virtual void f() { } };
struct D { D(const D&) = default; int x; };
struct E { E(const E&); int x; };
E::E(const E&) = default;   // defaulted outside the class: user-provided

using std::is_trivially_copy_constructible_v;
static_assert( is_trivially_copy_constructible_v<A>);
static_assert(!is_trivially_copy_constructible_v<B>);
static_assert(!is_trivially_copy_constructible_v<C>);
static_assert( is_trivially_copy_constructible_v<D>);
static_assert(!is_trivially_copy_constructible_v<E>);
int main() { }
```

¶12 A copy/move constructor can be **trivial** only if it is not **user-provided** ([[g:user-provided]], user-declared and not defaulted or deleted on its first declaration), and in addition:

- ¶12.1 the class has no virtual functions and no virtual base classes;
- ¶12.2 the constructor selected to copy/move each direct base class is a direct member of that base and is trivial;
- ¶12.3 the constructor selected to copy/move each non-static data member of class type (or array thereof) is trivial.

A trivial copy constructor amounts to copying the object's bytes.

Virtual functions make copying non-trivial because of slicing: with `Derived d; Base b = d;`, a byte-wise copy would leave `b`'s vtable pointer pointing at `Derived`'s vtable, giving `b` the wrong dynamic type. So the copy constructor has to set the vtable pointer to `Base`'s vtable rather than copy it from the source.

¶12.2 and ¶12.3 look at the function actually selected, not at whether the member type has some trivial constructor. For example, if a member type `M` has a trivial `M(const M&)` and a user-provided `M(M&&)`, the enclosing class's copy constructor can be trivial while its move constructor is not. ¶12.2 requires the selected constructor to be a direct member of the base in order to exclude constructors that the base inherited from its own bases.

## Implicit definition (¶13–¶16)

### When it is defined (¶13–¶14)

¶13 Note 6: the copy/move constructor is implicitly defined even if the implementation elides its odr-use (copy elision, [[class.copy.elision]]). So if the implicit definition is ill-formed, copy elision can't make the program valid, and whether the program is well-formed doesn't depend on whether the compiler performed an optional elision.

¶13 also says an implicitly-defined copy/move constructor is `constexpr`.

¶14 Before a defaulted copy/move constructor is implicitly defined, all the non-user-provided copy/move constructors of its potentially constructed subobjects are implicitly defined first. An implicitly-declared version has an implied exception specification (note 7, [[except.spec]]): it is `noexcept` when none of the constructors it calls throw.

!!! tip "Mark move constructors `noexcept`"
    When a `std::vector` grows, it moves the elements only if the element's move constructor is `noexcept` (or the element isn't copyable); otherwise it copies them to keep the strong exception safety guarantee. An implicitly-defined move constructor deduces `noexcept` automatically; when you write one yourself, you have to mark it.

### Non-unions: memberwise copy/move (¶15)

```cpp run title="memberwise.cpp" ok
#include <string>
#include <utility>
#include <cassert>

struct X {
    int arr[3];
    std::string s;
    int& ref;
    int counter = 100;   // ignored when copying
};

int main() {
    int target = 7;
    X a{{1, 2, 3}, "hello", target, 5};
    X b = a;
    assert(b.arr[2] == 3 && b.s == "hello");
    assert(&b.ref == &target && b.counter == 5);

    X c = std::move(a);  // s is moved from
    assert(c.s == "hello");
}
```

¶15 The implicit copy/move constructor of a non-union class performs a memberwise copy/move of its bases and members, in the same order a user-written constructor would initialize them ([[class.base.init]]: virtual bases, direct bases, then members in declaration order). Default member initializers are ignored (note 8), so `b.counter` is 5, not 100.

Let `x` be the constructor's parameter, or, for a move constructor, an xvalue referring to the parameter. Each subobject is handled according to its type:

- ¶15.1 an array: each element is direct-initialized with the corresponding element of `x`;
- ¶15.2 a member `m` of rvalue reference type `T&&`: it is direct-initialized with `static_cast<T&&>(x.m)`;
- ¶15.3 any other base or member: it is direct-initialized with the corresponding base or member of `x`.

Virtual base class subobjects are initialized only once.

¶15.1 is the only implicit way arrays get copied. An array itself can't be copy-initialized, but inside a class it is copied along with the class. The effect of ¶15.3 on a reference member is that the new object's reference is bound to the same object (`&b.ref == &target`).

### Unions: copying the object representation (¶16)

```cpp run title="union-copy.cpp" ok
union U { int i; float f; };

int main() {
    U a;
    a.f = 1.5f;          // f is the active member
    U b = a;             // b.f becomes b's active member
    return b.f == 1.5f ? 0 : 1;
}
```

¶16 The implicit copy/move constructor of a union copies the whole object representation, that is, it copies the bytes ([[basic.types.general]]). In addition, for each object nested within the source, the corresponding object in the target (the subobject, if there is one, otherwise a newly created object) starts its lifetime before the copy.

The second half guarantees that the active member is carried over: in the example above, `b.f` is the active member of `b` and can be read. Without it, after a byte-wise copy the target union would have no active member, and reading any member would be undefined behavior. By ¶10.1, a union has a usable implicit copy constructor only if all its variant members have trivial copy constructors.

## Implementation view

!!! impl "Trivial copies and calling conventions"
    A trivial copy/move constructor compiles to `memcpy` or a register transfer, and `std::vector` copies trivial elements with a plain `memmove`. The Itanium C++ ABI says that when a class has a non-trivial copy constructor, move constructor or destructor (or all its copy and move constructors are deleted), it can't be passed by value in registers; the caller constructs the object in memory and passes its address. So adding a user-provided copy constructor to a small class changes its calling convention and breaks ABI compatibility.

    Clang's `[[clang::trivial_abi]]` attribute lets types like `unique_ptr` still be passed in registers, at the cost of destroying them in the callee instead. It doesn't change triviality in the standard's sense.

## History

!!! history
    - C++98 had only the copy constructor; the `X(X&)` degradation rule already existed then.
    - C++11 introduced the move constructor with its strict conditions for implicit declaration; declaring a move operation deletes the implicit copy; with a user-declared copy assignment or destructor, the implicit copy is deprecated. That deleted defaulted move constructors are ignored by overload resolution was added by a defect report shortly after C++11 was published.
    - C++17's guaranteed copy elision means initializing an object from a prvalue of the same type no longer needs a usable copy/move constructor.
    - C++20 says that when a union is implicitly copied, the corresponding members in the target start their lifetime ([[P0593R6]]). Conditionally trivial special member functions from the same period ([[P0848R3]]) let one class template decide by its arguments whether the copy constructor is trivial.
    - Since C++23, implicitly-defined copy/move constructors are unconditionally `constexpr`.

## Common misconceptions

!!! pitfall "Writing only a destructor quietly turns moves into copies"
    A user-declared destructor stops the move constructor from being implicitly declared (¶8.5), and rvalues use the copy constructor instead. For a class with a custom destructor, check whether you need to `= default` the move operations explicitly; see [[special]].

!!! pitfall "Scalar members of the source are unchanged after a move"
    An implicit move of a scalar member such as an `int` or raw pointer is just a copy, and the value in the source is unchanged. A class that expresses ownership with a raw pointer must write its own move operations that null out the source pointer, or use a `std::unique_ptr` member instead.

## Questions

!!! question "Question 1"
    ```cpp
    struct A {
        A() = default;
        A(A&) = default;
    };
    struct B { A a; };
    const B cb{};
    B b2 = cb;   // ?
    ```
    Is the last line valid? What form does `B`'s implicit copy constructor have?

<details markdown="1">
<summary>Answer</summary>

Not valid. `A`'s only copy constructor is `A(A&)`; a defaulted function may change `const A&` to `A&` ([[dcl.fct.def.default#2]]). By ¶7, member `a` has no copy constructor accepting `const A&`, so `B`'s implicit copy constructor is `B(B&)`, which can't bind `cb` of type `const B`.

</details>

!!! question "Question 2"
    In `struct S { template<class T> S(const T&); };`, which constructor does `S s2 = s1;` call? What if the template is changed to `template<class T> S(T&)` and `s1` is a non-const lvalue?

<details markdown="1">
<summary>Answer</summary>

In the first case it calls the implicit copy constructor `S(const S&)`. The template is not a copy constructor and doesn't suppress it; the template specialization `S(const S&)` has the same signature, and the non-template wins ([[over.match.best]]). In the second case the deduction yields `S(S&)`, which needs one qualification conversion fewer than `S(const S&)`, so the template is selected.

</details>

## Summary

| | Copy constructor | Move constructor |
|---|---|---|
| Recognized by | Non-template; first parameter `cv X&`; others have default arguments | Non-template; first parameter `cv X&&`; others have default arguments |
| Implicitly declared when | No user-declared copy constructor | No user-declared copy constructor, copy assignment, move assignment or destructor |
| Form | `X(const X&)`, or `X(X&)` when necessary | `X(X&&)` |
| Deleted when | A move operation is declared; a subobject can't be copied or destroyed; there is an rvalue reference member | A subobject can't be moved or destroyed; once deleted, ignored by overload resolution |
| Trivial when | Not user-provided, no virtual functions or virtual bases, the selected base and member constructors are all trivial | Same |
| Implicit definition | Memberwise direct-initialization, ignoring default member initializers; unions copy bytes | Same, with the source as an xvalue |
