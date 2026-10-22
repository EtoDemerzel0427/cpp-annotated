---
title: Initializing bases and members
summary: "What a constructor's member initializer list can contain, how subobjects it doesn't mention are initialized, the order of initialization, and the restrictions on delegating constructors and on calling member functions during construction."
updated: 2026-10-19
---

!!! tldr
    - The order of initialization is determined by the class definition alone: virtual bases (initialized only by the most derived class), direct bases (in declaration order), members (in declaration order), and finally the function body. The order in which the member initializer list is written has no effect.
    - A member not mentioned in the list uses its default member initializer if it has one, and is default-initialized otherwise; a member that is mentioned ignores its default member initializer.
    - Initializers that intermediate classes write for a virtual base are ignored when a more derived object is constructed, and their arguments aren't evaluated.
    - A delegating constructor's initializer list can contain only the delegation; the object counts as constructed once the target constructor returns, so if the delegating constructor's body then throws, the destructor is called.
    - Calling a member function of the object before all bases are initialized is UB; binding a reference member to a temporary is ill-formed.

## What happens before the constructor body

```cpp run title="init-order.cpp" ok
#include <cstdio>

struct M {
    M(const char* s) { std::printf("%s ", s); }
};
struct A { A() { std::printf("A "); } };
struct B { B() { std::printf("B "); } };

struct C : A, B {
    M m1, m2;
    C() : m2("m2"), m1("m1"), B(), A() {
        std::puts("body");
    }
};

int main() { C c; }   // A B m1 m2 body
```

The part of a constructor definition after the colon is the *ctor-initializer*, commonly called the member initializer list. Each item in it is a *mem-initializer* of the form `name(arguments)` or `name{arguments}`. By the time the function body is entered, all base class subobjects and non-static data members have been initialized. The initializer list decides how they are initialized, but not in what order: the example above writes `m2, m1, B, A`, and the actual order is `A B m1 m2`.

¶1 A *ctor-initializer* can appear only in a constructor definition (it is part of the *function-body*, [[dcl.fct.def.general]]), and can specify initializers for direct bases, virtual bases and non-static data members:

```text
ctor-initializer:
    : mem-initializer-list
mem-initializer:
    mem-initializer-id ( expression-list(opt) )
    mem-initializer-id braced-init-list
mem-initializer-id:
    class-or-decltype
    identifier
```

A *mem-initializer-id* can be a class name or `decltype` (naming a base or the class itself), or an identifier (usually naming a member). Each item can be followed by `...`, denoting a pack expansion (¶20).

## Order of initialization (¶15–¶16)

¶15 In a non-delegating constructor, initialization proceeds in the following order:

1. ¶15.1 Virtual base classes, initialized only in the constructor of the most derived class (the class of the [[g:most-derived-object|most derived object]], [[intro.object]]), in the order they appear in a depth-first left-to-right traversal of the directed acyclic graph of base classes, where "left-to-right" is the order of the base classes in the *base-specifier-list*;
2. ¶15.2 Direct base classes, in declaration order in the *base-specifier-list*;
3. ¶15.3 Non-static data members, in the order they are declared in the class definition;
4. ¶15.4 Finally, the constructor's function body is executed.

None of the last three steps depends on the order in which the *mem-initializer*s are written. Note 7 explains why: destruction must happen in the reverse order of initialization, and there is only one destructor but there can be many constructors. If the order of initialization varied with each constructor's initializer list, the destructor would need to know which constructor built the object. Using the single declaration order from the class definition avoids the problem.

Clang gives a `-Wreorder-ctor` warning for initializer lists whose written order differs from the actual order; GCC calls it `-Wreorder`. Both are in `-Wall`.

### The danger of a mismatched order

As long as the initializers don't depend on each other, the written order is merely a matter of style. The danger comes from dependencies:

```cpp run title="reorder-bug.cpp" eb
struct S {
    int a, b;
    S(int x) : b(x), a(b + 1) {}   // a is initialized first, when b has no value yet
};

int main() {
    S s(1);
    return s.a;
}
```

`a` is declared first, so it is initialized first and reads `b` before `b` is initialized. `s` has automatic storage duration, so in C++26 it reads an erroneous value, which is erroneous behavior ([[basic.indet]]); in C++23 and earlier, reading an indeterminate value was UB. Clang 23 gives both `-Wreorder-ctor` and `-Wuninitialized` for this code. The fix is to make the declaration order match the dependencies, or to compute every initializer from the parameters only.

### Order of virtual bases (¶16)

A virtual base exists only once in the whole object, but several intermediate classes may want to initialize it. The standard's choice is that only the most derived class initializes it, and the intermediate classes' initializers are all ignored (see "Virtual bases are initialized only by the most derived class" below). Example 9 in the standard with output added:

```cpp run title="vbase-order.cpp" ok
#include <cstdio>

struct V {
    V()      { std::puts("V()"); }
    V(int i) { std::printf("V(%d)\n", i); }
};
struct A : virtual V { A() {} A(int i) : V(i) {} };
struct B : virtual V { B() {} B(int) {} };
struct C : A, B, virtual V { C() {} C(int) {} };

int main() {
    V v(1);   // V(1)
    A a(2);   // V(2): A is the most derived class
    B b(3);   // V(): B(int) has no initializer for V
    C c(4);   // V(): C(int) has none; those of A and B are ignored
}
```

With several virtual bases, the depth-first left-to-right traversal guarantees that all derived classes use the same order. For example, with `struct Q : virtual R {}; struct X : virtual P, Q {};`, traversing `X` meets `P` first, then enters `Q` and meets `R`, so the two virtual bases `P` and `R` are initialized first, and only then the non-virtual direct base `Q`.

## What the initializer list can contain (¶2–¶5)

### Name lookup (¶2)

```cpp run title="same-name-param.cpp" ok
struct P {
    int x;
    P(int x) : x(x) {}   // outside the parentheses: the member; inside: the parameter
};

int main() { return P(0).x; }
```

¶2 Unqualified lookup for a *mem-initializer-id* ignores the constructor's parameter scope, so the `x` outside the parentheses finds the member `P::x`. The arguments inside the parentheses are ordinary expressions in the parameter scope (¶17), where the parameter `x` hides the member.

Note 1: if the class has a member with the same name as a direct or virtual base class, a *mem-initializer-id* that is a single identifier refers to the member; to initialize the hidden base, use a qualified name.

<div class="compare" markdown="1">

```cpp error
struct Base { Base(int) {} };
struct S1 : Base {
    int Base;
    S1() : Base(1) {}
    // error: Base is the member int Base,
    // and the base class Base has no default constructor
};
```

```cpp ok
struct Base { Base(int) {} };
struct S2 : ::Base {
    int Base;
    S2() : ::Base(1), Base(2) {}
    // ::Base is the base class, Base is the member
};
```

</div>

¶2 ends: a *mem-initializer-id* can name only the constructor's class itself (delegation, ¶6), a direct non-static data member of that class, or a direct or virtual base of that class; otherwise it is ill-formed. Members of members, indirect non-virtual bases and static members can't be initialized here.

### Naming the base (¶3)

¶3 A base class can be initialized using any *class-or-decltype* that denotes that base class type: a typedef, an alias, the injected-class-name and `decltype` all work.

```cpp run title="base-alias.cpp" ok
template<class T> struct TB { TB(T) {} };

struct S3 : TB<int> {
    using Alias = TB<int>;
    S3() : Alias(1) {}
};
struct S4 : TB<int> {
    S4() : TB(1) {}   // the base class's injected-class-name
};

int main() { S3 a; S4 b; }
```

The form in `S4` is convenient in templates: the injected-class-name `TB` of the base `TB<int>` is inherited into `S4`'s scope ([[class.pre]]). If the base depends on a template parameter, as in `template<class T> struct D : TB<T>`, unqualified lookup can't see names in the dependent base, and you must write `TB<T>` in full.

### Two ill-formed cases (¶4–¶5)

```cpp title="ambiguous-base.cpp" error
struct A { A() {} };
struct B : virtual A {};
struct C : A, B { C(); };
C::C() : A() {}   // error: the direct base A or the virtual base A?
```

¶4 If a *mem-initializer-id* designates both a direct non-virtual base class and an indirect virtual base class, it is ill-formed. Such a class hierarchy by itself makes Clang warn that the direct base `A` is inaccessible due to ambiguity, and should be avoided in practice.

¶5 A *ctor-initializer* can initialize a variant member ([[g:variant-member]], a member of a union or anonymous union) of the constructor's class. Mentioning the same member or base twice is ill-formed: `D(int v) : x(v), x(1) {}` is rejected.

## How unmentioned subobjects are initialized (¶9, ¶12, ¶10)

```cpp title="unmentioned.cpp" error
struct A { A(); };
struct B { B(int); };

struct C {
    C() {}
    A a;          // OK: calls A::A()
    const B b;    // error: B has no default constructor
    int i;        // OK: i is not initialized
    int j = 5;    // OK: j has the value 5
};
```

¶9 In a non-delegating constructor other than an implicitly-defined copy or move constructor (whose rules are in [[class.copy.ctor]]), if a [[g:potentially-constructed-subobjects|potentially constructed subobject]] (a non-static data member, a direct base, or a virtual base of a non-abstract class) is not designated by any *mem-initializer*:

- ¶9.1 if it is a non-static data member with a default member initializer ([[g:default-member-initializer]]), it is initialized from that default member initializer, provided that, if it belongs to a union (or anonymous union), no other member of the same union is designated by a *mem-initializer* (¶9.1.1, ¶9.1.2);
- ¶9.2 otherwise, if it is an anonymous union or a variant member, no initialization is performed;
- ¶9.3 otherwise, it is default-initialized.

Note 4: for an object of automatic or dynamic storage duration, after the constructor returns (and not as part of value-initialization), a member that was neither initialized nor assigned a value in the body has an indeterminate or erroneous value ([[basic.indet]]). `i` in the example above is such a member.

### The initializer list takes precedence over the default member initializer (¶12)

```cpp run title="dmi-ignored.cpp" ok
#include <cstdio>

int side_effect() { std::puts("side effect"); return 1; }

struct A {
    int i = side_effect();
    A() {}                  // uses the default member initializer
    A(int arg) : i(arg) {}  // doesn't evaluate the default member initializer
};

int main() {
    A a1;      // side effect
    A a2(5);   // no output
    return a2.i;
}
```

¶12 A member that has both a default member initializer and a *mem-initializer* is initialized by the *mem-initializer*; the default member initializer is ignored, along with any side effects in it. This is exactly the use C++11 introduced default member initializers for ([[N2756]]): write a default shared by most constructors, and let individual constructors override it.

¶10 An attempt to initialize more than one non-static data member of a union is ill-formed, for example `union U { int a; float b; U() : a(1), b(2) {} };`.

## How the arguments initialize subobjects (¶7, ¶8, ¶13)

¶7 The arguments in a *mem-initializer* initialize the designated subobject (or, for delegation, the whole object) according to the direct-initialization rules of [[dcl.init]]. So `explicit` constructors can be selected, and `m{...}` is direct-list-initialization, which forbids narrowing.

Note 2: the initialization performed by each *mem-initializer* constitutes a full-expression ([[intro.execution]]). Temporaries created in it are destroyed at the end of that item's initialization, not at the end of the constructor.

### Reference members can't bind to temporaries

<div class="compare" markdown="1">

```cpp error
struct A {
    A() : v(42) {}  // error
    const int& v;
};
```

```cpp error
struct A {
    A() = default;
    const int& v = 42;
};
A a1;  // error: uses this
       // default member initializer
```

</div>

¶8 Binding a temporary to a reference member in a *mem-initializer* is ill-formed. ¶13 says the same for default member initializers, with the error reported where the default member initializer is used.

Such a binding has no legitimate use: the temporary would live at most until the constructor ends, so the reference would dangle as soon as the object is constructed. The C++98 rule was to keep the temporary alive until the constructor exits; [[CWG1696]] made both forms ill-formed.

The rule can only catch the one case that can be determined statically, binding a temporary. Example 8 in the standard also has a line `A(int v) : v(v) {}` followed by `A a2(1);`, commented "OK, unfortunately": the reference binds to the parameter and likewise dangles after the constructor returns, but it is well-formed. Clang 23 gives a `-Wdangling-field` warning for this.

## Virtual bases are initialized only by the most derived class (end of ¶7, note 3)

```cpp run title="vbase-ignored.cpp" ok
#include <cstdio>

int g() { std::puts("g()"); return 1; }

struct V { V(int i = 0) { std::printf("V(%d)\n", i); } };
struct A : virtual V { A() : V(g()) { std::puts("A()"); } };
struct B : A {};

int main() {
    A a;   // g() / V(1) / A()
    B b;   // V(0) / A(): g() is not called
}
```

¶7 ends by saying that when an object of a class that is not the most derived class is constructed, a *mem-initializer* that names a virtual base is ignored, and its arguments aren't evaluated. When constructing a `B`, `A` is not the most derived class, so `A`'s `V(g())` is discarded; `B` itself has no initializer for `V`, so `V` is default-initialized per ¶9.3.

So if a virtual base has no default constructor, every most derived class must write an initializer for it. Note 3 points out an exception: an abstract class is never a most derived class, so its constructors never initialize virtual bases, and the corresponding initializers can be omitted.

```cpp run title="abstract-vbase.cpp" ok
struct V { V(int) {} };            // no default constructor
struct Abs : virtual V {
    Abs() {}                       // OK: an abstract class doesn't initialize V
    virtual void f() = 0;
};
struct Impl : Abs {
    Impl() : V(1) {}               // the most derived class must initialize V
    void f() override {}
};

int main() { Impl i; }
```

!!! impl "The Itanium ABI's two constructor variants"
    So that virtual bases are initialized only by the most derived class, the Itanium ABI (used by GCC and Clang on Linux and macOS) generates two variants of each constructor: the complete object constructor (`C1` in the mangled name) initializes virtual bases; the base object constructor (`C2`), called by derived class constructors, skips them. Without virtual bases the two are identical and usually share code. Destructors likewise have `D1` and `D2`, plus `D0`, which also frees memory.

    With virtual bases, `C2` also needs to know where the virtual bases are in the current most derived object and which vtable to use during construction; this information is passed in as a hidden parameter, a table called the VTT. MSVC uses a different scheme: constructors take an extra hidden integer parameter saying whether they are constructing the most derived object.

## Delegating constructors (¶6, ¶11)

```cpp title="delegating.cpp" error
struct C {
    C(int) {}              // #1
    C() : C(42) {}         // #2: delegates to #1
    C(char) : C(42.0) {}   // #3 and #4 delegate to each other: IFNDR
    C(double) : C('a') {}  // #4
};

struct E {
    E() : E(1), m(2) {}    // error: delegation must be the only item
    E(int);
    int m;
};
```

¶6 If a *mem-initializer-id* designates the constructor's class itself, the constructor is a [[g:delegating-constructor|delegating constructor]], and the constructor selected (by overload resolution) is the [[g:target-constructor|target constructor]]. There are three rules:

- The delegating *mem-initializer* must be the only one. The target constructor fully initializes all bases and members; if `m` could also be initialized, it would be initialized twice.
- The body of the delegating constructor runs only after the target constructor returns.
- A constructor that delegates to itself, directly or indirectly, is ill-formed, no diagnostic required (IFNDR): the compiler needn't report it, and the program's behavior has no guarantees. No diagnostic is required because the target constructor may be defined in another translation unit. When the whole cycle is visible in one translation unit, Clang 23 reports an error (`-Wdelegating-ctor-cycles`, an error by default).

### When the object is fully constructed (¶11)

¶11 The initialization of an object is complete once a non-delegating constructor returns. Note 5 points out that the object's lifetime ([[basic.life]]) can therefore begin before all delegating constructors have completed.

This rule decides whether the destructor is called on an exception:

```cpp run title="delegating-throw.cpp" ok
#include <cstdio>
#include <stdexcept>

struct Res {
    Res()  { std::puts("Res()"); }
    ~Res() { std::puts("~Res()"); }
};

struct A {
    Res r;
    A(int) { std::puts("A(int)"); }
    A() : A(0) { throw std::runtime_error("x"); }
    ~A() { std::puts("~A()"); }
};

struct B {
    Res r;
    B(int) { std::puts("B(int)"); throw 1; }
    ~B() { std::puts("~B()"); }
};

int main() {
    try { A a; } catch (...) {}    // Res() A(int) ~A() ~Res()
    try { B b(1); } catch (...) {} // Res() B(int) ~Res()
}
```

`B(int)` is a non-delegating constructor; when it throws, the object was never fully constructed, so `~B()` isn't called and only the members already constructed are destroyed ([[except.ctor#3]]). The target constructor of `A()` has already returned, so the object is fully constructed, and when the delegating constructor's body throws, `~A()` is called ([[except.ctor#4]]).

This gives an idiom: establish the invariants in the target constructor, put subsequent steps that might fail in the delegating constructor's body, and let the destructor clean up on failure.

## Destructors of subobjects (¶14)

```cpp title="dtor-potentially-invoked.cpp" error
struct NoDtor { ~NoDtor() = delete; };

struct H {
    NoDtor n;
    H() {}   // error: needs NoDtor::~NoDtor()
};
```

¶14 In a non-delegating constructor, the destructor of each potentially constructed subobject of class type is potentially invoked ([[class.dtor]]). A potentially invoked destructor must be accessible and not deleted, or the program is ill-formed. Note 6 gives the reason: if an exception is thrown partway through construction, the subobjects already constructed have to be destroyed ([[except.ctor]]). The requirement stands even if the constructor is declared `noexcept`.

!!! lawyer "Delegating constructors and deleted destructors"
    ¶14 speaks only of non-delegating constructors. But [[except.ctor#4]] says that when a delegating constructor's body exits via an exception, the object's destructor is invoked, and [[class.dtor]] counts the cases where it would actually be invoked as potential invocations too. So in `struct S { S() : S(0) {} S(int); ~S() = delete; };`, `S()` needs a usable destructor, and Clang 23 rejects it (attempt to use a deleted function).

## `this` and member functions in initializers (¶17–¶19)

```cpp run title="this-in-init.cpp" ok
class X {
    int a;
    int b;
    int i;
    int j;
public:
    const int& r;
    X(int i) : r(a), b(i), i(i), j(this->i) {}
};

int main() { X x(3); (void)x; }
```

¶17 is a note: the arguments of a *mem-initializer* are in the constructor's parameter scope, and `this` can be used to refer to the object being initialized. In Example 10 in the standard:

- `r(a)` binds the reference to the member `a`. It uses only `a`'s address and doesn't read its value, so it doesn't matter that `a` isn't initialized yet ([[class.cdtor#3]]);
- `b(i)` and `i(i)` use the parameter `i`;
- `j(this->i)` reads the member `i`. The parameter hides the member, so `this->i` must be written. It reads the right value because `i` is declared before `j` and initialized first.

Clang 23 gives `-Wreorder-ctor` for this example (`r` is declared last but written first), which is harmless here.

### No member function calls before the bases are initialized (¶18)

```cpp run title="call-before-bases.cpp" ub
struct A { A(int) {} };

class B : public A {
    int j;
public:
    int f() { return 0; }
    B() : A(f()),   // UB: the base A isn't initialized yet
          j(f()) {} // OK: all bases are initialized
};

class C { public: C(int) {} };

class D : public B, C {
    int i;
public:
    D() : C(f()),   // UB: the base C isn't initialized yet
          i(f()) {} // OK
};

int main() { D d; }
```

¶18 Member functions (including virtual ones) can be called for an object under construction or destruction, and it can be the operand of `typeid` or `dynamic_cast`. But doing so is undefined behavior at three points:

- ¶18.1 in a *ctor-initializer* (including functions called from it directly or indirectly), before all the *mem-initializer*s for base classes have completed;
- ¶18.2 in a precondition assertion of a constructor {{c++26}};
- ¶18.3 in a postcondition assertion of a destructor {{c++26}} ([[dcl.contract.func]]).

The boundary is "all bases initialized" because a member function may access base class members or call virtual functions through a base, and the base class subobjects (including their vtable pointers) aren't set up before then. The `D` example shows that having `B` constructed isn't enough; `C` has to be done too. A constructor's preconditions are evaluated before any subobject is initialized, and a destructor's postconditions after all subobjects have been destroyed; at those two points the object is entirely unusable.

To compute a value in a base class initializer, use a static member function or a free function instead.

¶19 is a note: for the well-defined cases, the results of virtual function calls, `typeid` and `dynamic_cast` during construction are described in [[class.cdtor]].

## Pack expansions (¶20)

```cpp run title="mixins.cpp" ok
#include <cstdio>

template<class... Mixins>
class X : public Mixins... {
public:
    X(const Mixins&... mixins) : Mixins(mixins)... {}
};

struct Loud {
    Loud() = default;
    Loud(const Loud&) { std::puts("Loud copied"); }
};
struct Quiet {};

int main() {
    X<Loud, Quiet> x(Loud{}, Quiet{});   // Loud copied
}
```

¶20 A *mem-initializer* followed by an ellipsis is a pack expansion ([[temp.variadic]]) that initializes the base classes specified by a pack expansion in the *base-specifier-list*. This is the standard way to compose mixins.

## History

!!! history
    - C++98 already had member initializer lists, initialization in declaration order, and virtual bases initialized only by the most derived class.
    - C++11 added delegating constructors ([[N1986]]), default member initializers ([[N2756]]), brace-form *mem-initializer*s and pack expansions.
    - [[CWG1696]] made binding a reference member to a temporary (in a *mem-initializer* or a default member initializer) ill-formed.
    - C++26 added the two contract assertion items to ¶18, and extended "indeterminate value" in note 4 to "indeterminate or erroneous value".

## Questions

!!! question "Question 1"
    What does the following program print?

    ```cpp
    #include <cstdio>
    struct P { P(const char* s) { std::puts(s); } };
    struct Q { Q(const char* s) { std::puts(s); } };
    struct V { V(const char* s = "V()") { std::puts(s); } };
    struct L : virtual V {
        P p{"L::p"};
        L() : V("V from L") { std::puts("L"); }
    };
    struct R : virtual V { R() { std::puts("R"); } };
    struct X : R, L {
        Q q;
        X() : L(), q("X::q"), V("V from X") { std::puts("X"); }
    };
    int main() { X x; }
    ```

<details markdown="1">
<summary>Answer</summary>

```text
V from X
R
L::p
L
X::q
X
```

`X` is the most derived class, so the virtual base `V` is initialized first, using `X`'s own initializer; `V("V from L")` in `L` is ignored. Then come `R` and then `L`, in *base-specifier-list* order, even though only `L()` is written in the initializer list. Constructing `L` first initializes `p` from its default member initializer, then runs the body. Last come the member `q` and `X`'s body.
</details>

!!! question "Question 2"
    If Example 10 in the standard is changed as follows, what is the value of `j`?

    ```cpp
    class X {
        int j;
        int i;
    public:
        X(int i) : i(i), j(this->i) {}
    };
    ```

<details markdown="1">
<summary>Answer</summary>

`j` is declared before `i`, so `j` is initialized first, when `this->i` has no value yet; the written order can't change that. For an `X` object with automatic storage duration, C++26 reads an erroneous value (erroneous behavior), and C++23 and earlier have UB; for an object with static storage duration, it reads 0 from zero-initialization. `-Wreorder-ctor` warns about it.
</details>
