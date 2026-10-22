---
title: Initialization by inherited constructor
summary: "using B::B lets base class constructors take part in constructing the derived class; when one is selected, it initializes the base class subobject, and the rest of the derived class is initialized as if by a defaulted default constructor."
updated: 2026-10-19
---

!!! tldr
    - After `using B::B;`, `B`'s constructors are also candidates when constructing a `D`. When one is selected, it initializes the `B` subobject, and `D`'s other bases and members are initialized as if by a defaulted default constructor.
    - Since C++17, what is called is the base class constructor itself: default arguments, `explicit`, `constexpr` and access are all kept as they are, and the arguments directly initialize the base constructor's parameters, with no intermediate copy.
    - A constructor that the derived class declares itself with the same parameters hides the inherited one; with a single argument, the base's copy and move constructors don't take part in constructing a `D`.
    - If `B` is a virtual base and this initialization isn't responsible for constructing it, the call to the inherited constructor is omitted, together with the evaluation of its arguments.
    - If the same constructor is inherited through several base class subobjects of type `B`, the program is ill-formed.

## What `using B::B;` is

```cpp
struct D : B {
    D(int x) : B(x) {}
    D(int x, double y) : B(x, y) {}
    D(const char* s) : B(s) {}
    // every new base constructor needs a matching one here
};
```

When a derived class merely adds a little to its base, forwarding every one of the base's constructors is tedious. C++11's **inheriting constructors** ([[g:inherited-constructor|inheriting constructor]]) replace all that forwarding with a single line, `using B::B;`.

The rules are split across two places. [[namespace.udecl]] says what `using B::B;` is: when looking up `D`'s constructors and forming the set of overload candidates, `B`'s constructors are treated as constructors of `D` ([[namespace.udecl#13]]). This page, [[class.inhctor.init]], says how the `D` object is initialized once such a constructor is selected.

C++17 rewrote these rules with [[P0136R1]]. The old C++11/14 model synthesized a set of forwarding constructors for the derived class; since C++17 nothing is synthesized, and the candidates are the base class constructors themselves. Much older material online describes the old model.

### Which constructors can be used

```cpp run title="hiding.cpp" ok
#include <cstdio>

struct B {
    B(int x, int y = 7) { std::printf("B(%d,%d)\n", x, y); }
    B(const char*)      { std::puts("B(const char*)"); }
};

struct D : B {
    using B::B;
    D(const char*) : B(1, 1) { std::puts("D(const char*)"); }
    int m = 42;
};

int main() {
    D a(1);     // B(1,7): default arguments work as usual
    D b("x");   // B(1,1) / D(const char*)
    return a.m == 42 ? 0 : 1;   // m uses its default member initializer
}
```

These rules decide the candidate set:

- When `D` itself declares a constructor with the same parameter list, the base's isn't inherited ([[namespace.udecl#11]]). In the example above, `D(const char*)` hides `B(const char*)`.
- `D a(1)` calls `B(int, int = 7)` itself, so the default argument is available. Under the old model, the derived class synthesized one constructor for each parameter list obtained by dropping trailing default arguments, and those had no default arguments of their own; that is what the old saying "default arguments aren't inherited" referred to.
- `using B::B;` isn't a user-declared constructor, so `D` still has its implicitly declared default, copy and move constructors. When a constructor of `D` and an inherited constructor have the same parameter types for all arguments, the derived class's wins ([[over.match.best#2.7]]).
- With a single argument, an inherited constructor whose first parameter is a reference to `B` (such as the copy and move constructors) is not a candidate for constructing a `D` ([[over.match.funcs#9]]).

The effect of the last rule is that a `D` can't be constructed from a `B` object:

```cpp title="no-copy-from-base.cpp" error
struct B {
    B(int) {}
    B(const B&) = default;
};
struct D : B { using B::B; };

void f() {
    B bb(3);
    D d(bb);   // error: B(const B&) is not a candidate
}
```

If it were allowed, `D d(bb);` would produce a `D` whose `B` part comes from `bb` and whose remaining parts are default-initialized, which is almost always a mistake. When you need such a construction, write `D(const B& b) : B(b) {}` explicitly.

### Properties are kept as they are

```cpp title="properties.cpp" error
struct B {
    B(int) {}
    explicit B(double) {}
    constexpr B(long) {}
protected:
    B(char) {}
};
struct D : B { using B::B; };

constexpr D cd(1L);  // OK: B(long) is constexpr
D d1(2.0);           // OK: direct-initialization
D d2 = 2.0;          // error: explicit B(double) isn't considered;
                     //   B(int) and B(char) are ambiguous
D d3('c');           // error: B(char) is protected
```

`d3` illustrates [[namespace.udecl#16]]: an inherited constructor is accessible where it would be accessible when used to construct a `B` object, and the access specifier the *using-declaration* itself appears under is ignored. So even putting `using B::B;` under `public:` can't make a protected constructor public. Only *using-declaration*s of ordinary member functions can change access.

## How initialization proceeds once selected (¶1)

¶1 When a constructor for type `B` is invoked to initialize an object of a different type `D` (that is, when the constructor was inherited), initialization proceeds as if a defaulted default constructor were used to initialize the `D` object and each base class subobject from which the constructor was inherited, except that the `B` subobject is initialized by the inherited constructor.

Intuitively, selecting a constructor brought in by `using B::B;` is roughly equivalent to having written:

```text
D(args...) : B(args...) {}
// other bases and members: default member initializer if present, otherwise default-initialized
```

But it differs from a hand-written forwarding constructor in three ways.

### Parameters are initialized only once

```cpp run title="single-call.cpp" ok
#include <cstdio>

struct NM {
    NM(int) { std::puts("NM(int)"); }
    NM(const NM&) = delete;   // neither copyable nor movable
};
struct B { B(NM) { std::puts("B(NM)"); } };
struct D : B { using B::B; };

int main() {
    D d(1);   // NM(int) / B(NM)
}
```

¶1, third sentence: the complete initialization is considered to be a single function call; unless omitted (see the next subsection), the initialization of the inherited constructor's parameters is sequenced before the initialization of any part of the `D` object. The arguments directly initialize the parameters of `B::B`; there is no layer of derived constructor parameters, and so no extra copy or move.

Compiling the same code with `-std=c++14`, Clang 23 reports "copying parameter of type 'NM' invokes deleted constructor": the forwarding constructor synthesized under the old model has to pass its parameter on to `B`. A hand-written forwarding constructor has the same problem.

### When it isn't responsible for the virtual base, the whole call is omitted

```cpp run title="omitted.cpp" ok
#include <cstdio>

struct V {
    V() { std::puts("V()"); }
    V(int) { std::puts("V(int)"); }
};
struct Q { Q() {} };
struct A : virtual V, Q {
    using V::V;
    A() = delete;
};
int bar() { std::puts("bar()"); return 42; }
struct B : A {
    B() : A(bar()) {}   // selects V(int), inherited by A
};
struct C : B {};

int main() {
    C c;   // per the standard: prints only V()
}
```

¶1, second sentence: if the `B` subobject would not be initialized as part of the `D` object, the invocation of the inherited constructor, including the evaluation of any arguments, is omitted. The typical case is that `B` is a virtual base and `D` is not the most derived class: virtual bases are initialized only by the most derived class ([[class.base.init#15]]).

This is Example 2 in the standard. `A(bar())` selects the inherited `V(int)`, but the `A` subobject isn't the most derived object, so `V` isn't initialized as part of `A`, and the call to `V(int)` is omitted together with `bar()`. `V` is default-initialized by the most derived class `C`, printing `V()`. `A() = delete;` doesn't get in the way, because the rest of `A` (the `Q` subobject) is initialized as if by a defaulted default constructor, and the deleted `A()` is never called.

Changing `main` to `B b;` gives the same conclusion: the `A` subobject is never the most derived object, and `V` is always initialized by `B`.

!!! warning "Clang disagrees with the standard"
    Running the example above with Clang 23 prints `V()` and then `bar()`. It correctly doesn't call `V(int)`, but still evaluates the argument `bar()`, contrary to ¶1's "including the evaluation of any arguments". The same happens with `B b;`.

### Intermediate classes on the path

```cpp run title="chain.cpp" ok
struct W { W(int) {} };
struct X : virtual W { using W::W; X() = delete; };
struct Y : X { using X::X; };
struct Z : Y, virtual W { using Y::Y; };

int main() {
    Z z(0);   // OK
}
```

`Z z(0)` selects `W(int)`, inherited all the way to `Z` through `Y` and `X`. Initialization proceeds as if defaulted default constructors initialized `Z` and the `Y` and `X` on the path, while `W` (since `Z` is the most derived class, the virtual base `W` is initialized by `Z`) is initialized by `W(0)`. `X() = delete` is irrelevant: the `X` subobject is initialized as if by a defaulted default constructor, and its only subobject without a way to be default-constructed, `W`, is already handled by the inherited constructor.

### New members must be default-initializable

```cpp title="d1-d2.cpp" error
struct B1 { B1(int, ...) {} };
struct B2 { B2(double) {} };
int get();

struct D1 : B1 {
    using B1::B1;   // inherits B1(int, ...)
    int x;
    int y = get();
};

void test() {
    D1 d(2, 3, 4);  // OK: B1(2, 3, 4), x not initialized, y = get()
    D1 e;           // error: D1 has no default constructor
}

struct D2 : B2 {
    using B2::B2;
    B1 b;           // B1 has no default constructor
};

D2 f(1.0);          // error: b can't be default-initialized
```

An inherited constructor takes care only of the base class part. In `D1 d(2, 3, 4)`, `x` is default-initialized and has no value; `D2 f(1.0)` fails because the member `b` has to be initialized as in a defaulted default constructor, and `B1` has no default constructor. Giving the derived class's new members default member initializers avoids both problems.

Example 1 in the standard ends with a template showing a typical use of inheriting constructors, wrapping an arbitrary class:

```cpp run title="log-wrapper.cpp" ok
#include <iostream>
#include <string>

template<class T> struct Log : T {
    using T::T;   // inherits all of T's constructors
    ~Log() { std::clog << "Destroying wrapper\n"; }
};

int main() {
    Log<std::string> s(3, 'x');      // std::string(size_type, char)
    std::cout << s << std::endl;     // xxx
}                                    // Destroying wrapper
```

## Inherited through several subobjects of the same type (¶2)

```cpp title="multiple-subobjects.cpp" error
struct A { A(int) {} };
struct B : A { using A::A; };

struct C1 : B { using B::B; };
struct C2 : B { using B::B; };
struct D1 : C1, C2 {
    using C1::C1;
    using C2::C2;
};
D1 d1(0);   // error: two B subobjects; which one?

struct V1 : virtual B { using B::B; };
struct V2 : virtual B { using B::B; };
struct D2 : V1, V2 {
    using V1::V1;
    using V2::V2;
};
D2 d2(0);   // OK: only one virtual base B subobject

struct M { M() {} M(int) {} };
struct N : M { using M::M; };
struct O : M {};
struct P : N, O { using N::N; using O::O; };
P p(0);     // OK: only the one via N
```

¶2 If the selected constructor is inherited from multiple base class subobjects of type `B`, the program is ill-formed. What counts is subobjects: a non-virtual diamond has two `B` subobjects, a virtual diamond only one.

`D2 d2(0)` initializes the virtual base `B` (and `B` initializes its base `A` with `A(0)`), then initializes `V1` and `V2` as if by defaulted default constructors. `P p(0)` is valid because `O` doesn't write `using M::M;`, so `using O::O;` brings in only `O`'s own implicit constructors. So the `M` in `N` is initialized by `M(0)`, and the `M` in `O` by `M()`.

## When initialization is complete (¶3)

¶3 When an object is initialized by an inherited constructor, initialization of the object is complete when the initialization of all subobjects is complete.

This corresponds to "initialization is complete when a non-delegating constructor returns" in [[class.base.init#11]]. With an inherited constructor, the constructor called is `B`'s, and when it returns `D`'s members aren't initialized yet, so the return of the constructor can't be the criterion. The point of completion decides when the object's lifetime begins ([[basic.life]]), and whether `D`'s destructor is called on an exception: subobjects initialized under this subclause are "known to be initialized" and are destroyed on an exception ([[except.ctor#3]] item 3.3), whereas `D`'s own destructor is called only once initialization is complete.

## Other related rules

- A class with inherited constructors is not an aggregate ([[dcl.init.aggr]]).
- Since C++23, class template argument deduction also considers inherited constructors ([[over.match.class.deduct]], [[P2582R1]]), with a corresponding tie-breaker in [[over.match.best#2.10]]. At the time of writing, Clang 23 doesn't support this yet: `template<class T> struct D : B<T> { using B<T>::B; }; D d(1);` fails to deduce.

!!! impl "Symbols Clang generates"
    Under the C++17 model, Clang generates a constructor entity in the derived class for each inherited constructor actually used; it takes the same parameters as the base constructor and performs the initialization described in ¶1. The Itanium ABI defines dedicated name mangling for it: `CI1`, `CI2` (complete object and base object versions) followed by the base type. For example, for the inherited `B(int)` in `struct D : B { using B::B; int m = 1; };`, Clang 23 generates `_ZN1DCI11BEi` and `_ZN1DCI21BEi`.

## History

!!! history
    - C++11 introduced inheriting constructors with [[N2540]], using a synthesis model: for each base constructor (other than copy, move and default constructors), and for each parameter list obtained by dropping trailing default arguments, a constructor with the same parameters was implicitly declared in the derived class, forwarding to the base. By-value parameters were therefore copied or moved one extra time, default arguments weren't kept, and non-movable parameter types couldn't be used.
    - C++17's [[P0136R1]] switched to the current model: base class constructors are directly candidates for constructing the derived class. Default arguments, `explicit`, templates and access are naturally kept; "copy and move constructors aren't inherited" was rewritten as the candidate exclusion rule in [[over.match.funcs#9]].
    - C++23's [[P2582R1]] lets class template argument deduction use inherited constructors too.

## Questions

!!! question "Question 1"
    What does the following program print? And after deleting `S(int)`?

    ```cpp
    #include <cstdio>
    struct B {
        B(int)  { std::puts("B(int)"); }
        B(long) { std::puts("B(long)"); }
    };
    struct S : B {
        using B::B;
        S(int) : B(0L) { std::puts("S(int)"); }
    };
    int main() { S s(1); }
    ```

<details markdown="1">
<summary>Answer</summary>

It prints `B(long)` and `S(int)`. `S(int)` has the same parameter list as `B(int)`, so per [[namespace.udecl#11]] `B(int)` isn't inherited. The only candidates are `S(int)` and the inherited `B(long)`, and the former is an exact match.

After deleting `S(int)`, the candidates are the inherited `B(int)` and `B(long)`; `B(int)` is selected and `B(int)` is printed.
</details>

!!! question "Question 2"
    In `struct B { B(int); }; struct D : B { using B::B; std::string s; };`, in what order do the initialization of `B::B(int)`'s parameter, the initialization of the `B` subobject and the initialization of `s` happen for `D d(1);`? If the initialization of `s` throws, which destructors are called?

<details markdown="1">
<summary>Answer</summary>

The order is: parameter, `B` subobject, `s`. ¶1 says the parameters are initialized before any part of `D`, and the remaining parts follow the order in [[class.base.init#15]].

When the construction of `s` throws, the `B` subobject has been fully initialized and is a subobject known to be initialized ([[except.ctor#3]] item 3.3), so `B::~B()` is called. `D`'s initialization is not complete, so `D::~D()` isn't called.
</details>
