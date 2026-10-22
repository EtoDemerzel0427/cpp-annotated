---
title: Constructors
summary: "How constructors are declared and why they have no name and can't have their address taken; when the default constructor is implicitly declared, deleted or trivial, and how an out-of-class = default changes the result of T{}."
updated: 2026-10-19
---

!!! tldr
    - A constructor is recognized by the shape of its declaration: inside the class, the injected-class-name followed by a parameter list, with no type in front. It has no name, can't have its address taken, can't be a coroutine and can't have an explicit object parameter.
    - An object isn't `const` yet while it is being constructed, so the constructor of a `const` object can assign to members.
    - As soon as a class declares any constructor (including a copy constructor or a constructor template), the compiler no longer implicitly declares a default constructor.
    - A reference member, a `const` member without an initializer, or a subobject that can't be default-constructed or destroyed makes the defaulted default constructor deleted. Since C++26, variant members of unions no longer trigger this.
    - A default constructor defaulted inside the class is not user-provided, and `T{}` zeroes the object first; move the `= default` outside the class and it becomes user-provided, and `T{}` no longer zeroes.

## Declaring constructors [class.ctor.general]

```cpp title="ctor-decl.cpp" error
struct S {
    S();                     // constructor
    explicit S(int);         // OK
    constexpr S(double) { }  // OK
    void S(char);            // error: can't have a return type
    static S(long);          // error: can't be static
    virtual S(short);        // error: can't be virtual
};
S::S() { }                   // out-of-class definition
```

A constructor is used to initialize objects of its class type. It is a special member function: it has no return type and no name.

### Recognized by shape (¶1)

¶1 A function declarator declares a constructor if, after removing the parameter list, exception specification and attributes, what remains is just an *id-expression* of one of these three forms:

- ¶1.1 in a friend declaration, a qualified name that names a constructor, such as `friend X::X();`;
- ¶1.2 in a member declaration inside a class definition, the **injected-class-name** ([[g:injected-class-name]], the name by which a class appears in its own scope under its own name, [[class.pre#2]]) of the immediately-enclosing class;
- ¶1.3 otherwise, a qualified name whose last component is the injected-class-name, as in the out-of-class definition `S::S() { }`.

The rest of the declaration may contain only the specifiers `friend`, `inline`, `constexpr`, `consteval` and `explicit` (including `explicit(bool)`). That is why `void`, `static` and `virtual` in the example above are errors.

!!! lawyer "`X<T>()` in a class template"
    In `template<class T> struct X`, `X<T>` is a template-id, not the injected-class-name, so `X<T>();` doesn't match ¶1.2 and, since C++20, is no longer a valid constructor declaration; write `X();`. The same goes for destructors: write `~X();` ([[class.dtor#1]]). Clang 23, even with `-pedantic`, silently accepts both `X<T>()` and `~X<T>()`; GCC gives a `-Wtemplate-id-cdtor` warning.

### Constructors have no name (¶1–¶2)

¶1 ends by stating explicitly that constructors do not have names. A few things follow directly:

- Unqualified name lookup never finds a constructor (¶2, note 1).
- `S(1)` is not a call to a constructor but an explicit type conversion in functional notation ([[expr.type.conv]]). It yields a prvalue, and the constructor is called when that prvalue's result object is initialized.
- The rule that a member can't have the same name as its class ([[class.mem.general#25]]) does not apply to constructors.

Since C++17, `S x = S(1);` calls the constructor only once. The prvalue `S(1)` initializes the result object `x` directly; there is no temporary in between, and no usable copy or move constructor is needed ([[class.temporary]], [[dcl.init]]).

¶3 (note 5) points out that operations such as calling virtual functions during construction have special semantics; see [[class.base.init]] and [[class.cdtor]].

## The object isn't const during construction (¶4)

```cpp run title="const-during-ctor.cpp" ok
struct K {
    int v;
    constexpr K() : v(0) {
        v = 5;   // OK: members can be modified during construction
    }
};

const K k;           // becomes const only after construction ends
constexpr K ck;
static_assert(ck.v == 5);

int main() { return k.v - 5; }
```

¶4 A constructor can be invoked for a `const`, `volatile` or `const volatile` object. `const` and `volatile` semantics are not applied to an object under construction. They come into effect when the constructor for the **most derived object** ([[g:most-derived-object]], the complete object that is not a subobject of any other object) ends.

Without this rule, the `v = 5` in the constructor body above would be modifying a const object, which is undefined behavior.

The point at which they take effect is the end of the most derived object's construction, not the end of each subobject's construction. While a derived class constructor's body runs, the base class part, although already fully constructed, can still be modified. The same goes for `volatile`: accesses to members during construction are not volatile accesses.

## Three prohibitions (¶5–¶7)

```cpp title="ctor-restrictions.cpp" error
struct S {
    S() { }
    S(int) { return; }         // OK: return without a value
    S(long) { return 1; }      // error: can't return a value
    S(this S self, char);      // error: can't have an explicit object parameter
};
auto p = &S::S;                // error: can't take the address of a constructor
```

¶5 The address of a constructor can't be taken. A `return` in a constructor body also can't have a value (note 6, [[stmt.return]]).

A constructor receives storage that isn't initialized yet, and at the ABI level there are often several versions of it (see the implementation view below), so no single function pointer could represent it. When you need construction as a callable, use a lambda or `std::construct_at`.

¶6 A constructor can't be a coroutine. If a coroutine were suspended, the object would be only half constructed, and its lifetime couldn't be defined.

¶7 A constructor can't have an explicit object parameter ([[dcl.fct]]). When a constructor starts running, the object doesn't exist yet, so there is nothing to pass as the object argument.

## Default constructors [class.default.ctor]

### What a default constructor is (¶1)

```cpp title="ambiguous-default.cpp" error
struct Amb {
    Amb();
    Amb(int = 0);   // also a default constructor
};
Amb a;              // error: ambiguous
Amb b(1);           // OK: only Amb(int) is viable
```

¶1 A constructor is a **default constructor** if every parameter that is not a function parameter pack has a default argument. A constructor with no parameters naturally counts. So `X()`, `X(int = 0)` and `X(int = 0, double = 1.0)` are all default constructors. A class can have several, but default initialization is then ambiguous.

### Implicit declaration and suppression (¶1)

¶1 If a class has no **user-declared** ([[g:user-declared]], a declaration written in the class, including `= default` and `= delete`) constructor or constructor template and is not an anonymous union, the compiler implicitly declares a default constructor with no parameters that is not explicit. It is **defaulted** (its definition is generated by the compiler according to the rules, [[dcl.fct.def]]), and it is an inline public member of the class.

```cpp run title="suppressed.cpp" ok
#include <type_traits>

struct A { };
struct B { B(int); };
struct C { C(const C&) = default; };
struct D { template<class T> D(T); };
struct E { E(int); E() = default; };

static_assert( std::is_default_constructible_v<A>);
static_assert(!std::is_default_constructible_v<B>);
static_assert(!std::is_default_constructible_v<C>);
static_assert(!std::is_default_constructible_v<D>);
static_assert( std::is_default_constructible_v<E>);
int main() { }
```

Any user-declared constructor suppresses the implicit default constructor: an ordinary constructor (`B`), a copy constructor (`C`), a constructor template (`D`), and a constructor declared `= delete`. If you still want a default constructor, write `= default` explicitly, as `E` does.

Inherited constructors (`using Base::Base;`) are not user-declared constructors of the class itself and don't suppress the implicit default constructor.

### When it is deleted (¶2)

```cpp title="default-deleted.cpp" error
#include <string>

struct R  { int& r; };
struct C1 { const int c; };
struct C2 { const std::string s; };
struct C3 { const int c = 1; };
struct P  { private: P(); };
struct Q  { P p; };

R  r;      // error: ¶2.1
C1 c1;     // error: ¶2.2
C2 c2;     // OK
C3 c3;     // OK
Q  q;      // error: ¶2.3
```

¶2 A defaulted default constructor is **defined as deleted**, that is, treated as if written `= delete` so that calling it is an error, in these four cases:

- ¶2.1 It has a non-static data member of reference type with no default member initializer. A reference must be bound to some object.
- ¶2.2 The class is not a union and has a non-variant member of `const` type with no initializer whose type is not **const-default-constructible** ([[g:const-default-constructible]]).
- ¶2.3 A non-variant **potentially constructed subobject** ([[g:potentially-constructed-subobjects]], the direct bases and non-static data members, plus the virtual bases when most derived) has no initializer, and overload resolution to choose its default constructor finds no usable candidate: it fails, is ambiguous, selects a deleted function, or selects a function that is inaccessible.
- ¶2.4 A potentially constructed subobject has a destructor that is deleted or inaccessible, and the subobject either is not a variant member or has a default member initializer.

A **variant member** ([[g:variant-member]]) is a member of a union, or a member of an anonymous union.

Roughly, const-default-constructible means that default-initializing the type yields a determinate value: either it calls a user-provided constructor (as `std::string` does), or every member has a default member initializer (see [[dcl.init.general#7]] for the details). So `C2` is valid and `C1` is not.

¶2.4 checks destructors because a constructor can exit partway through via an exception. The subobjects already constructed then have to be destroyed ([[except.ctor]]), so their destructors must be usable.

### Unions: C++26 trivial unions {{c++26}}

¶2.3 and ¶2.2 look only at non-variant members; ¶2.4 checks a variant member's destructor only when it has a default member initializer. So a union member with a non-trivial default constructor doesn't make the union's default constructor deleted.

```cpp title="trivial-union.cpp"
#include <string>

union U { std::string s; };   // C++26: trivial default constructor, not deleted
U u;                          // C++26 OK; C++23 error
int main() { }
```

This is a C++26 change ([[P3074R7]]). In C++23, a union's default constructor was deleted when a variant member had a non-trivial default constructor and no variant member had a default member initializer, so users had to write `U() {}` by hand. C++26 dropped this, and adjusted the destructor rules to match ([[class.dtor#7]]).

So storage that manages element lifetimes by hand, as in `std::optional` or `std::inplace_vector`, can simply be written `union { T storage[N]; };` and used in constant evaluation too. Clang 23 doesn't implement this change yet and reports that the default constructor of the example above is implicitly deleted, so the example carries no verdict.

### Trivial default constructors (¶3)

```cpp run title="trivial-default.cpp" ok
#include <type_traits>

struct T1 { int x; };
struct T2 { int x = 0; };
struct T3 { virtual void f(); };
struct T4 : T2 { };
struct T5 { T5() = default; int x; };
struct T6 { T6(); int x; };
T6::T6() = default;

using std::is_trivially_default_constructible_v;
static_assert( is_trivially_default_constructible_v<T1>);
static_assert(!is_trivially_default_constructible_v<T2>);
static_assert(!is_trivially_default_constructible_v<T3>);
static_assert(!is_trivially_default_constructible_v<T4>);
static_assert( is_trivially_default_constructible_v<T5>);
static_assert(!is_trivially_default_constructible_v<T6>);
int main() { }
```

¶3 A default constructor can be **trivial** only if it is not **user-provided** ([[g:user-provided]]). User-provided means user-declared and not defaulted or deleted on its first declaration. So `T5`'s is not user-provided, while `T6`'s, defaulted outside the class, is user-provided. In addition, four conditions must hold:

- ¶3.1 the class has no virtual functions and no virtual base classes (otherwise the vtable pointer has to be set, `T3`);
- ¶3.2 no non-static data member has a default member initializer (otherwise the initializer has to run, `T2`);
- ¶3.3 all direct base classes have trivial default constructors (`T4`);
- ¶3.4 the class is a union, or every non-variant non-static data member of class type (or array thereof) has a trivial default constructor.

A trivial default constructor does nothing, and scalar members are not initialized. For objects with automatic storage duration, since C++26 those members hold erroneous values, and reading them is erroneous behavior ([[basic.indet]]).

That unions always satisfy ¶3.4 is the other half of C++26 trivial unions. C++23 required the variant members of a union to have trivial default constructors too.

### An out-of-class `= default` changes the result of `T{}`

Whether the default constructor is user-provided also decides how **value-initialization** ([[g:value-initialization]], the initialization `T()` or `T{}` performs when nothing more specific applies) behaves: if the selected default constructor is not user-provided, the whole object is first zero-initialized and then the constructor is called; if it is user-provided, it is only called ([[dcl.init.general#8]]).

```cpp run title="value-init.cpp" ok
struct A { int x; };
struct B { B() = default; int x; };
struct C { C(); int x; };
C::C() = default;   // defaulted outside the class: user-provided

int main() {
    A a{};   // aggregate initialization: x == 0
    B b{};   // value-initialization, zeroed first: x == 0
    C c{};   // value-initialization, only calls C(): x uninitialized
    (void)b; (void)c;
    return a.x;
}
```

- `A` is an aggregate ([[dcl.init.aggr]]), so `A{}` is aggregate initialization and `x` is value-initialized to 0.
- `B` has a user-declared constructor, so since C++20 it is no longer an aggregate, and `B{}` is value-initialization. `B()` is not user-provided, so the object is zeroed first and `b.x == 0`.
- `C{}` is also value-initialization, but `C()` is user-provided, so nothing is zeroed. Reading `c.x` is erroneous behavior in C++26, and was undefined behavior before.

Merely moving `= default` from inside the class to outside changes the result of `T{}` from all zeros to uninitialized.

### Implicit definition (¶4)

¶4 An implicitly-defined default constructor performs exactly the initialization that a hand-written default constructor with no member initializer list and an empty body would: members with a default member initializer are initialized by it, and the remaining bases and members are default-initialized. If that hand-written version would be ill-formed, the program is ill-formed.

¶4 also says an implicitly-defined default constructor is `constexpr`. That doesn't mean it can always be used in constant expressions; whether it can be constant-evaluated still depends on what it actually does:

```cpp title="constexpr-default.cpp" error
struct S { int x; };
constexpr S s1{};   // OK: value-initialization, x == 0
constexpr S s2;     // error: default-initializes a const object,
                    // but S is not const-default-constructible

struct N {
    int* p = new int(1);
    constexpr ~N() { delete p; }
};
constexpr bool ok() { N n; return *n.p == 1; }
static_assert(ok());   // OK: allocated at compile time and freed in the same evaluation
```

Before a defaulted default constructor is implicitly defined, all the non-user-provided default constructors of its bases and members are implicitly defined first. An implicitly-declared default constructor has an implied exception specification: it is `noexcept` when none of the functions it would call throw (note 1, [[except.spec]]).

<details class="fine" markdown="1"><summary>Remaining wording</summary>

¶5 note 2: when no initializer is given (default initialization, [[dcl.init.general]]), a default constructor is called implicitly to initialize a class object, and it must be accessible.

¶6 note 3: the order in which bases and members are constructed, and how to specify arguments for them, are covered in [[class.base.init]].

</details>

## Implementation view

!!! impl "One constructor, several symbols"
    The Itanium C++ ABI generates two variants of every constructor: C1 (complete object constructor) constructs a complete object, including virtual bases; C2 (base object constructor) constructs the object as a base class subobject and skips virtual bases. The specification also has C3 (allocating constructor), which isn't used in practice. Without virtual bases, C1 and C2 behave identically, and GCC and Clang often emit one as an alias of the other.

    A trivial default constructor generates no code. An implicitly-defined non-trivial default constructor (for example, with a `std::string` member) calls the members' constructors in turn and is usually inlined.

## History

!!! history
    - C++98 already had implicitly-declared default constructors and the notion of triviality (used for POD).
    - C++11 introduced `= default`, `= delete` and default member initializers, and replaced "implicit definition is ill-formed" with "defined as deleted"; from then on, reference and `const` members made the default constructor deleted.
    - Since C++20, a class with user-declared constructors is no longer an aggregate, and a constructor in a class template can no longer be declared as `X<T>()`.
    - C++23 relaxed the restrictions on `constexpr` functions, and implicitly-defined default constructors became unconditionally `constexpr`.
    - C++26 trivial unions ([[P3074R7]]) stop variant members from making a union's default constructor deleted or non-trivial; default-initialized scalar members hold erroneous values.

## Common misconceptions

!!! pitfall "Assuming a constructor template can stand in for the default constructor"
    `template<class... Ts> X(Ts&&...);` can match zero arguments, so `X x;` uses it. But it suppresses the implicit default constructor and is not itself defaulted, so `X` no longer has a trivial default constructor.

!!! pitfall "Adding a default member initializer changes triviality"
    The default constructor of `struct P { int x = 0; };` is not trivial, and `std::is_trivially_default_constructible_v<P>` is `false`. Some optimizations that rely on trivial default construction (such as skipping initialization when a container grows) are lost, though `P` is still trivially copyable.

## Questions

!!! question "Question 1"
    Which of these classes have a usable default constructor?

    ```cpp
    struct A { int& r = *new int; };
    struct B { const int c; B() = default; };
    union  C { const int c; int i; };
    struct D { struct { const int c; } s; };
    ```

<details markdown="1">
<summary>Answer</summary>

- `A`: usable. The reference member has a default member initializer, so ¶2.1 doesn't apply (the code leaks memory, but it is valid).
- `B`: not usable. `c` has no initializer and `const int` is not const-default-constructible, so by ¶2.2 the defaulted default constructor is deleted. Clang gives a `-Wdefaulted-function-deleted` warning on this declaration.
- `C`: usable. ¶2.2 applies only to non-union classes, and `c` is a variant member. `C x;` is valid and `x` has no active member. But `const C x;` is not: for a union to be const-default-constructible, exactly one variant member must have a default member initializer.
- `D`: not usable. The unnamed type of member `s` has no usable default constructor because of ¶2.2, so ¶2.3 holds for `D`.

</details>

!!! question "Question 2"
    In `struct E { E(); int x; }; E::E() = default;`, what is the value of `e.x` after `E e{};`? And if the `= default` is moved into the class?

<details markdown="1">
<summary>Answer</summary>

The out-of-class `= default` makes `E()` user-provided. `E{}` is value-initialization (`E` has a user-declared constructor, so it is not an aggregate) and only calls `E()`; `x` is not initialized, and reading it is erroneous behavior in C++26. Moved into the class, `E()` is no longer user-provided, so value-initialization zero-initializes first and `e.x == 0` ([[dcl.init.general#8]]).

</details>
