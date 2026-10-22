---
title: Friends
summary: "A friend declaration lets a function or class name the class's private and protected members without becoming a member; friend functions defined in a class can only be found by argument-dependent lookup; friendship is neither inherited nor transitive; and which entity a friend declaration refers to, given that it doesn't introduce its name into any scope."
updated: 2026-10-19
---

!!! tldr
    - A friend is a function or class granted permission to name the class's private and protected members. It isn't a member: a friend function has no `this` and isn't affected by the access section it appears in.
    - The base-specifiers, member declarations and nested classes of a friend class all share the grant; the grant covers only the entity named, and is neither inherited nor transitive.
    - A friend function first declared in a class can't be found by ordinary name lookup, only by argument-dependent lookup (ADL); this is the hidden friend, well suited to writing operators.
    - An unqualified friend function declaration refers to the innermost enclosing namespace: `friend void h(int);` declares the `h` there, not an existing global `::h`.
    - `friend T;` is ignored when `T` isn't a class type; C++26 allows `friend Ts...;` to befriend a whole pack at once.

```cpp run title="friend-vs-member.cpp" ok
class X {
    int a = 0;
    friend void friend_set(X*, int);   // friend: not a member
public:
    void member_set(int);              // member
};
void friend_set(X* p, int i) { p->a = i; }  // object passed explicitly
void X::member_set(int i) { a = i; }        // implicit this

int main() {
    X obj;
    friend_set(&obj, 10);
    obj.member_set(10);
}
```

Some operations logically belong to a class's interface but don't suit being member functions: symmetric binary operators, stream output operators, functions that need to see the internals of two classes at once. **Friends** give them a way to access private members. The syntax of the `friend` specifier is in [[dcl.friend]], and the rules for friends involving templates are in [[temp.friend]].

## What a friend gets (¶1–¶2)

¶1 A friend of a class is a function or class that is given permission to name the private and protected members of the class. A class specifies its friends with friend declarations. Friend declarations give special access rights to the friends, but they don't make the nominated friends members of the befriending class.

Not being a member means a friend function has no `this`, can't be called as `obj.friend_set(...)`, and can't be virtual. A virtual member function of another class can be declared a friend, because friendship is only about access.

¶2 Declaring a class to be a friend means its *base-specifier*s and member declarations can name the private and protected members of the befriending class:

```cpp run title="friend-class.cpp" ok
class A {
    class B { };
    enum { N = 4 };
    friend struct X;
};
struct X : A::B {      // OK: base-specifier
    A::B mx;           // OK: member declaration
    int arr[A::N];     // OK
    class Y {
        A::B my;       // OK: a nested class is also a member of X
    };
};
int main() { X x; (void)x; }
```

Member declarations include member function definitions (whether inside or outside the class), nested classes and members of nested classes, because access is passed down through nesting ([[class.access#2]]). Friends of the friend class are not included; friendship isn't transitive (¶9).

```cpp title="friend-class-scope.cpp" error
class X {
    enum { a = 100 };
    friend class Y;
};
class Y { int v[X::a]; };   // OK: Y is a friend of X
class Z { int v[X::a]; };   // error: X::a is private
```

## Preconditions for friend declarations (¶4, ¶7, ¶8)

¶4 (a note) says that a friend declaration refers to an entity, not to all the overloads under a name. Member functions of another class can be friends, and so can constructors and destructors:

```cpp
class Y {
    friend char* X::foo(int);   // only this overload is a friend
    friend X::X(char);          // constructor
    friend X::~X();             // destructor
};
```

To befriend a whole set of overloads, declare each one.

¶8 begins with a requirement: a member nominated by a friend declaration must be accessible in the class containing the friend declaration. You can't use a friend declaration to point at another class's private member function:

```cpp title="friend-member-access.cpp" error
class X {
    void priv();
public:
    void pub();
};
class Y {
    friend void X::pub();    // OK
    friend void X::priv();   // error: X::priv is not accessible in Y
};
```

The second sentence of ¶8 says the meaning of a friend declaration is the same whether it appears in the private, protected or public part of the class. ¶7 No storage class specifier, such as `static` or `extern`, may appear in the *decl-specifier-seq* of a friend declaration.

## Friendship is neither inherited nor transitive (¶9)

```cpp title="friend-not-inherited.cpp" error
class A {
    friend class B;
    int a;
};
class B {
    friend class C;
};
class C {
    void f(A* p) { p->a++; }   // error: a friend of a friend is not a friend
};
class D : public B {
    void f(A* p) { p->a++; }   // error: a class derived from a friend is not a friend
};
```

¶9 Friendship is neither inherited nor transitive.

It isn't inherited in either direction. A class derived from a friend is not a friend, like `D` above. And a class derived from the befriending class doesn't treat the base's friends as its own: `B` being a friend of `A` doesn't mean `B` can access the private members newly added by `class A2 : public A`. `B` can still access members inherited from `A` through an `A2` object, though; that relies on the recursive designating-class rule in [[class.access.base]] (¶5.7).

Friendship is a one-sided, point-to-point declaration of trust by the befriending class. If friendship could be inherited, anyone could gain access by deriving a class from a friend; if it were transitive, the boundary of trust would no longer be controlled by the befriending class.

## Friend type declarations (¶3)

¶3 A friend declaration that doesn't declare a function must be a ***friend-type-declaration***. If a *friend-type-specifier* in it designates a (possibly cv-qualified) class type, that class is declared a friend; otherwise, the specifier is ignored.

```cpp title="friend-type.cpp" error
class C;
typedef C Ct;
class X1 {
    friend C;          // OK: C is a friend
};
class X2 {
    friend Ct;         // OK: via the typedef, the friend is C
    friend D;          // error: D not found
    friend class D;    // OK: declares a new class D
};
template<class T> class R1 { friend T; };
R1<int> ri;            // OK: friend int; is ignored
```

`friend D;` without a class-key only looks up existing names and doesn't introduce a new class; `friend class D;` is an elaborated type specifier and declares a new class when none is found. Ignoring non-class types is meant for templates: the `T` in `friend T;` may be instantiated as `int`, in which case it is not an error, just has no effect.

### Pack expansions {{c++26}}

C++26 allows a *friend-type-specifier* to be followed by `...` to form a pack expansion, and several friend types can be listed in one declaration separated by commas ([[P2893R3]]):

```cpp run title="variadic-friends.cpp" ok
template<class... Ts>
class Passkey {
    friend Ts...;              // every Ts is a friend
    Passkey() = default;       // only friends can construct it
};
class Owner;
class Auditor;
class Resource {
public:
    // only classes that can make a Passkey can call this
    void reset(Passkey<Owner, Auditor>) {}
};
class Owner {
public:
    void go(Resource& r) { r.reset({}); }
};
class Auditor {
public:
    void go(Resource& r) { r.reset({}); }
};
int main() {
    Resource r;
    Owner{}.go(r);
    Auditor{}.go(r);
    // r.reset({});            // error: Passkey() is private
}
```

In C++23 and earlier, this passkey idiom needed a separate version for each number of friends. Clang 23 supports the feature with `-std=c++2c`, and accepts it as an extension in earlier modes with a `-Wc++26-extensions` warning.

## Defining friend functions in the class (¶5–¶6)

¶5 A function can be defined in a friend declaration if and only if the class is not a local class ([[class.local]]) and the function name is unqualified:

```cpp
class M {
    friend void f() { }   // defines f in M's enclosing namespace; not a member function
};
```

The name must be unqualified because `friend void N::g();` refers to an existing function, which ought to be defined in the scope it belongs to. Local classes are excluded because such a function belongs to the enclosing namespace, and there is no way to arrange for a namespace-scope function to be defined inside a class in block scope.

¶6 Such a function is implicitly `inline` if it is attached to the global module ([[dcl.inline]]), so defining a friend function in a class definition in a header doesn't violate the ODR. A function defined this way in a named module is not implicitly inline, consistent with member functions defined in a class in a named module, so changes to implementation details in a module interface don't force every importer to recompile. Note 3 adds that a friend function defined outside the class is not in the scope of the class.

### Hidden friends

```cpp title="hidden-friend.cpp" error
namespace N {
    struct V {
        int x;
        friend bool operator==(V a, V b) { return a.x == b.x; }
        friend void touch(V) {}
        friend void nonadl() {}   // no parameter related to V
    };
    struct Conv {
        Conv(V) {}
        friend void sink(Conv) {}
    };
}
int main() {
    N::V a{1}, b{1};
    bool e = (a == b);   // OK: ADL finds it in the associated class N::V
    touch(a);            // OK: likewise
    N::touch(a);         // error: qualified lookup doesn't find it
    nonadl();            // error: nothing to associate with; can never be called
    sink(a);             // error: the associated class is V, not Conv
    sink(N::Conv(a));    // OK
    return e;
}
```

A friend function first declared (and usually defined) in a class can't be found by ordinary name lookup, qualified or unqualified. It can only be found by **argument-dependent lookup** ([[g:argument-dependent-lookup|ADL]], [[basic.lookup.argdep]]): when an argument type of a call has this class as an associated class, ADL looks at the class's friends. Such a function is called a [[g:hidden-friend|hidden friend]].

The reason is that a friend declaration doesn't bind its name in any scope (¶10, [[basic.scope.scope#2.9]]). The function belongs to the enclosing namespace, but ordinary lookup can't see it there until a matching ordinary declaration appears.

Operators are often written as hidden friends, for four reasons:

1. A smaller candidate set. A namespace-scope `operator==` takes part in overload resolution for every `==` in that namespace; a hidden friend becomes a candidate only when the arguments involve this class, which helps both compile time and the length of diagnostics.
2. No accidental selection through implicit conversions. As `sink(a)` above shows, `V` being convertible to `Conv` doesn't make ADL look in `Conv`.
3. Symmetry. As a non-member, both operands can undergo implicit conversions, as long as at least one of them is associated with the class; the left operand of a member operator can't be converted.
4. Direct access to private members, with no need for extra getters.

### Friend functions defined in class templates

A friend function defined in a class template defines a different non-template function for each specialization ([[temp.friend]]). If its signature doesn't depend on the template parameters, two specializations define the same function twice:

```cpp title="friend-in-template.cpp" error
template<class T> struct Y {
    friend void ff() {}   // every specialization defines ::ff()
};
Y<int>  yi;
Y<char> yc;               // error: redefinition of ::ff()
```

Making the signature depend on `T` avoids the problem, as with `friend Y operator+(Y, Y)`, where each specialization defines its own `operator+`.

!!! pitfall "A non-template friend and a function template with the same name"
    ```cpp
    template<class T> class Box {
        friend void show(const Box&);   // non-template function show(const Box<T>&)
    };
    template<class T> void show(const Box<T>&) {}  // a separate function template
    int main() { Box<int> b; show(b); }
    ```
    The friend declaration in `Box<int>` declares a non-template function `show(const Box<int>&)`, unrelated to the function template that follows. Overload resolution prefers the non-template function when both match equally well, so the call goes to this never-defined function. Clang 23 compiles it without a warning by default, and linking fails with a missing `show(Box<int> const&)`. To befriend a specialization of the function template, declare the template first and write `friend void show<>(const Box&);`, or simply define the function in the class.

## Friend declarations don't bind names (¶10)

¶10 (a note) says that a friend declaration never binds a name ([[dcl.meaning]], [[dcl.type.elab]]). The entity it declares belongs to some enclosing scope, but its name isn't put into any scope for ordinary lookup. Specifically:

- An unqualified friend function declaration refers to a function in the innermost enclosing namespace; scopes further out are not considered.
- An unqualified friend class declaration (`friend class Z;`) that finds no existing class declares it in the innermost enclosing namespace, or, for a local class, in the innermost block scope.
- Until an ordinary declaration appears in that scope, ordinary lookup can't find the name.

```cpp title="friend-binding.cpp" error
void h(int);
template<class T> void f2(T);
namespace A {
    class X {
        friend void f(X);          // A::f(X) is a friend
        class Y {
            friend void g();       // A::g is a friend
            friend void h(int);    // A::h is a friend; ::h is not considered
            friend void f2<>(int); // ::f2<>(int) is a friend
        };
    };
    // A::f, A::g and A::h are not visible here
    X x;
    void g() { f(x); }   // defines A::g; f(x) finds A::f via ADL
    void f(X) { }        // defines A::f
    void h(int) { }      // defines A::h
    // A::f, A::g and A::h are visible here and known to be friends
}
using A::x;
void h() {
    A::f(x);             // OK
    A::X::f(x);          // error: f is not a member of A::X
    A::X::Y::g();        // error: g is not a member of A::X::Y
}
```

This is Example 8 in the standard. Note that `friend void h(int);` declares `A::h`, even though the global `::h` was declared earlier with exactly the same signature. To befriend the global function, write `friend void ::h(int);`. `f2<>` has a template argument list, so it names a specialization of an existing template and lookup finds the global `f2`.

The rules for friends in local classes are stricter:

```cpp title="friend-in-local-class.cpp" error
class X;
void a();
void f() {
    class Y;
    extern void b();
    class A {
        friend class X;   // OK: but this is a new local class X, not ::X
        friend class Y;   // OK: the Y in block scope
        friend class Z;   // OK: introduces a local class Z in block scope
        friend void a();  // error: ::a is not considered
        friend void b();  // OK: the extern declaration in block scope
        friend void c();  // error
    };
    X* px;                // OK: but finds ::X
    Z* pz;                // error: Z not found
}
```

This is Example 9 in the standard. A friend function declaration in a local class looks for an existing declaration only in the innermost block scope; if none is found it is an error, and it doesn't introduce a new function in a namespace as a non-local class would. The local classes declared by `friend class X;` and `friend class Z;` don't bind names either, so the later `X*` finds `::X`, and `Z*` finds nothing.

## Implementation view

!!! impl
    - Friendship is purely compile-time access control and doesn't affect the ABI.
    - Compilers usually implement hidden friends like this: the function declaration goes into the namespace's symbol table as usual, but with an invisibility flag; ordinary lookup skips it, and ADL finds it in the associated class's list of friends.
    - Standard library implementations use hidden friends extensively to shrink overload candidate sets, for example for iterator comparison operators; it is a common compile-time optimization.

## History

!!! history
    - Under the pre-C++98 ARM rules, the name of a friend function declared in a class was injected into the enclosing scope. C++98 standardization removed this injection, making such names invisible to ordinary lookup and findable only via ADL, which is where hidden friend behavior comes from.
    - C++11 added `friend T;` without a class-key, usable with template parameters and typedef names, and ignored for non-class types.
    - With modules in C++20, friend functions defined in a class in a named module are no longer implicitly inline, hence the "attached to the global module" condition in ¶6.
    - C++26 {{c++26}}'s [[P2893R3]] added variadic friends, `friend Ts...;`, and listing several friend types in one declaration.

## Common misconceptions

!!! pitfall "`friend void h(int);` refers to the existing global `::h`"
    It declares and befriends the `h` in the innermost enclosing namespace. To befriend the global function, write `friend void ::h(int);`.

!!! pitfall "Any function can be written as a hidden friend"
    A hidden friend can't be called when no argument is associated with the class. Don't define functions with no parameters, or with parameters unrelated to the class, this way.

!!! pitfall "Derived classes inherit the base's friends"
    Friendship isn't inherited. A friend of the base can't access private members newly added by the derived class either.

## Questions

!!! question "Question 1"
    ```cpp
    struct S {
        friend void f(S) {}
        friend void g(int) {}
    };
    void t() { f(S{}); g(1); }
    ```
    Which call in `t` is valid? How can the other one be made callable?

<details markdown="1">
<summary>Answer</summary>

`f(S{})` is valid: ADL finds the hidden friend `f` in the associated class `S`. `g(1)` is ill-formed: the argument type `int` has no associated classes, so ADL doesn't look in `S`, and ordinary lookup can't find `g` because friend declarations don't bind names.

Declaring `void g(int);` once more in the global namespace fixes it. That ordinary declaration corresponds to the friend declaration ([[basic.scope.scope]]), lets ordinary lookup find the name, and still refers to the function defined in the class.
</details>

!!! question "Question 2"
    In `class A { int x; friend class B; }; class B { public: struct N { int get(A& a) { return a.x; } }; };`, can `B::N::get` access `A::x`? What if `N` is not a nested class of `B` but a friend class of `B`?

<details markdown="1">
<summary>Answer</summary>

As a nested class, yes. ¶2 says member declarations of a friend class can name `A`'s private members; `N` is a member of `B`, so its member function definitions are covered by the grant too, since access is passed down through nesting ([[class.access#2]] and footnote 89).

If `N` is merely a friend of `B` (`class N; class B { friend class N; };`), no. Friendship isn't transitive (¶9); `N` is just a friend of a friend.
</details>
