---
title: The friend specifier
summary: "This subclause is a single sentence and the rules for friends live in [class.friend]; this page collects the forms of friend declarations: friend functions and friend types, friend class X versus friend X, template parameters as friends, C++26 friend pack expansion, and which specifiers friend can combine with."
updated: 2026-10-19
---

!!! tldr
    - [dcl.friend] only says that `friend` is used to grant access; the rules are all in [[class.friend]].
    - `friend class X;` declares a new class if `X` can't be found; `friend X;` requires `X` to be declared already, and if `X` is not a class type the whole declaration is ignored.
    - A template parameter can only be written as `friend T;`, not `friend class T;`.
    - Since C++26 a friend declaration can list several types and expand packs: `friend Ts...;`.
    - `friend` can't combine with storage class specifiers or `virtual`; a friend function defined in a class can only be found by argument-dependent lookup.

¶1 This subclause is one sentence:

!!! std
    The `friend` specifier is used to specify access to class members; see [class.friend].

What friends can access, and why friendship is neither transitive nor inherited, are in [[class.friend]] and [[class.access]]. What follows collects the syntactic forms of `friend`; the relevant rules are scattered across [[dcl.pre]], [[dcl.spec.general]], [[dcl.type.elab]] and elsewhere.

## Friend functions and friend types

| Form | How it's written | Example |
|---|---|---|
| Friend function | An ordinary function declaration or definition with `friend` among its specifiers | `friend void f(X&);`, `friend bool operator==(const X&, const X&) = default;` |
| Friend type | *friend-type-declaration*: `friend` plus one or more types | `friend class Y;`, `friend Y;`, `friend Ts...;` |

A friend declaration that doesn't declare a function must be a *friend-type-declaration* ([[class.friend#3]]). Any declaration that matches the syntax of a *friend-type-declaration* is treated as one ([[dcl.pre#3]]), so `friend C;` is not taken as an ordinary declaration with specifiers only and a missing declarator.

### friend class X versus friend X

```cpp run ok
class C;
typedef C Ct;
class X {
    friend C;          // C must already be declared (since C++11)
    friend Ct;         // a typedef name works too; the friend is C
    friend class D;    // if D isn't found, declares a new class D in the enclosing namespace
    friend int;        // not a class type, ignored (valid since C++11)
};
int main() { }
```

The two forms differ in what happens when the name isn't found:

- `friend class D;` uses an elaborated type specifier (`class` or `struct` plus a name). If `D` isn't found in the innermost enclosing namespace, it declares a new class `D` belonging to that namespace. But this declaration doesn't make `D` findable by ordinary name lookup; to use it you must also declare it in the namespace ([[dcl.type.elab#4]]).
- In `friend D;`, `D` is an ordinary type name that must be found by lookup; if it isn't, it's an error, and no new class is introduced.

<div class="compare" markdown="1">

```cpp run ok
struct S { friend class Later; };
// an elaborated type specifier can refer to it
class Later* p = nullptr;
int main() { }
```

```cpp error
struct S { friend class Undeclared; };
Undeclared* p;   // error: not found
struct T { friend Unknown; };
                 // error: Unknown is not declared
```

</div>

### Template parameters as friends

```cpp run ok
template<class T> class Box {
    int secret = 42;
    friend T;      // a friend when T is a class, ignored otherwise
};
struct Inspector { int peek(Box<Inspector>& b) { return b.secret - 42; } };
Box<int> bi;       // OK: friend int; is ignored
int main() { Box<Inspector> b; return Inspector{}.peek(b); }
```

Since C++11 you can write `friend T;`. If `T` is instantiated with a non-class type such as `int`, the declaration is ignored rather than being an error. `friend class T;` is ill-formed, because the name in an elaborated type specifier can't be a typedef name or a template type parameter ([[dcl.type.elab#6]]):

```cpp error
template<class T> class Box2 {
    friend class T;   // error: T is a template parameter
};
```

## Friend lists and pack expansion {{c++26}}

```cpp run ok
template<class... Ts>
class Registry {
    int count = 0;
    friend Ts...;          // every class in the pack is a friend
};
struct A; struct B;
struct A { int get(Registry<A, B>& r) { return r.count; } };
struct B { void inc(Registry<A, B>& r) { ++r.count; } };

struct P; struct Q;
class Multi { friend P, Q; };   // one declaration lists several friends

int main() {
    Registry<A, B> r;
    B{}.inc(r);
    return A{}.get(r) - 1;      // 0
}
```

Since C++26, a *friend-type-declaration* can list several types separated by commas, each of which can be followed by `...` to expand a pack ([[P2893R3]]). In C++23 and earlier a friend declaration could have only one type, and making every type in a pack a friend needed a workaround such as the passkey idiom. The example in [[class.friend#3]] also has the mixed form `friend Ts::Nested..., Us...;`. Clang 23 accepts this form under `-std=c++23` too, with just a warning about a C++26 extension.

## Which specifiers friend can combine with

- At most one `friend` ([[dcl.spec.general#2]]).
- No storage class specifiers: `friend static void f();` is ill-formed ([[class.friend#7]]).
- No `virtual`: a friend function is not a member of this class, and `virtual` can only be used on the class's own non-static member functions ([[dcl.fct.spec#2]]).
- `inline`, `constexpr` and `consteval` are allowed. A friend declaration with `inline` must be a definition, or the function must have been declared inline before ([[dcl.inline#1]]).
- A friend function defined in a class (`friend void f() { }`) is implicitly inline if the class is attached to the global module (i.e. not in a named module) ([[class.friend#6]]).

```cpp error
struct S {
    friend static void f();      // error: storage class specifier
    friend virtual void g();     // error: virtual
};
```

!!! impl "Clang doesn't check non-defining friend inline declarations"
    By [[dcl.inline#1]], `struct S { friend inline void f(); };` is ill-formed: `f` wasn't declared inline before, and this isn't a definition. Clang 23 accepts the code without a diagnostic.

## Friend functions found only by ADL

```cpp run ok
struct Money {
    long cents;
    friend Money operator+(Money a, Money b) { return {a.cents + b.cents}; }
};
int main() {
    Money m = Money{100} + Money{50};   // OK: operator+ found through the argument type Money
    return int(m.cents) - 150;
}
```

If a friend function is first declared in a class, it belongs to the enclosing namespace, but neither ordinary unqualified lookup nor qualified lookup finds it; only **argument-dependent lookup** (ADL: looking for functions in the classes and namespaces associated with the argument types, [[basic.lookup.argdep]]) can. The `operator+` above is like this; the technique is called a hidden friend: it doesn't show up in unrelated overload resolution. Without an argument of class type, it can't be found:

```cpp error
struct S { friend void f() { } };
void g() { f(); }    // error: f can only be found via ADL, and there are no arguments here
```

For which scope the name in a friend declaration lands in, see [[dcl.meaning.general]] and [[class.friend]].

!!! history "History"
    - C++98: a friend type could only be written as `friend class X;`, without typedef names or template parameters.
    - C++11: `friend X;`, `friend T;` and typedef names are allowed; non-class types are ignored.
    - C++20: in named modules, friend functions defined in a class are no longer implicitly inline.
    - C++26: friend lists and pack expansion ([[P2893R3]]).

!!! question "Question"
    In `template<class T> class W { friend T; };`, is `Foo` a friend of `W<T>` when `T` is `const Foo`? And when `T` is `Foo&`?

<details markdown="1">
<summary>Answer</summary>

[[class.friend#3]] says that if a friend type specifier designates a (possibly cv-qualified) class type, that class becomes a friend; otherwise the specifier is ignored. So when `T` is `const Foo`, `Foo` is a friend; `Foo&` is a reference type, not a class type, so `friend T;` is ignored. With Clang 23, a member function of `Foo` accessing a private member of `W<Foo&>` gets an "is a private member" error.
</details>
