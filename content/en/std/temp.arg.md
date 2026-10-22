---
title: Template arguments
summary: "How template arguments are matched to template parameters: when a type and an expression are ambiguous the type wins; a constant argument must be able to initialize a static constexpr variable and cannot point to a string literal or a temporary; a template template argument matches if it accepts every use the parameter allows."
updated: 2026-10-19
---

!!! tldr
    - When a template argument can be read either as a type or as an expression, it is always read as a type: the `int()` in `f<int()>()` is a function type.
    - A constant template argument `E` must be usable as `static constexpr T x = E;`, so it is a constant expression, pointers and references can only point to objects with static storage duration, and narrowing is not allowed.
    - A pointer or reference argument cannot point to a string literal, a temporary, the result of `typeid`, or `__func__`. To use a string as a template argument, the parameter has to be of class type, such as a hand-written `fixed_string`.
    - Names in template arguments are access-checked where they are written; a template has no special access to private members of its argument types.
    - A template template argument matches if it can accept every use the parameter allows, so since C++17 `std::vector` can be passed to a `template<class> class`.

[[temp.param]] specifies which parameters a template can declare. This page covers the other half: when a template is used, how each **template argument** corresponds to a parameter and becomes the parameter's value. The standard splits this into general rules, [temp.arg.general], and rules for each of the three kinds of arguments: types, constants and templates.

## The kind of argument must match the parameter [temp.arg.general]

¶1 Each template argument must match the kind and type of its corresponding parameter: type parameters take types, constant parameters take values, template template parameters take templates. A parameter pack corresponds to zero or more arguments.

### When ambiguous, it's a type (¶4)

```cpp run title="type-wins.cpp" ok
#include <cstdio>
template<class T> void f() { std::puts("type"); }
template<int I>   void f() { std::puts("value"); }

int main() {
    f<int()>();   // int() is the type "function returning int": calls the first f
}
```

¶4 When a template argument can syntactically be read either as a *type-id* or as an expression, it is always read as a *type-id*, regardless of the corresponding parameter. This matches the principle for statements that anything that can be a declaration is a declaration ([[stmt.ambig]], [[dcl.ambig.res]]).

Even if `template<int I> void f()` were the only template, `f<int()>()` would still treat `int()` as a type and then fail to match; it would not fall back to reading it as an expression with value 0. Per footnote 102, default template arguments have no such ambiguity, because their form is determined by the parameter.

### Arguments in name form (¶3) {{c++26}}

¶3 When an argument is a possibly qualified name, the name is looked up first, and its meaning is decided by the lookup result:

- ¶3.1 if it finds an injected-class-name (the name a class template uses inside itself to refer to itself, [[temp.local]]), it denotes the class template itself when the corresponding parameter is a type template template parameter, and the current type otherwise;
- ¶3.2 if it finds a template, it denotes that template;
- ¶3.3 if it finds a type or type alias, it denotes that type;
- ¶3.4 otherwise it is treated as an expression.

The effect of ¶3.1 is that inside a class template, `A` can be used both as the type `A<T>` and as the template `A`:

```cpp run title="injected.cpp" ok
template<template<class> class TT> struct W {};
template<class T> struct V {};

template<class T>
struct A {
    W<A> w;   // for a template template parameter: A is the class template
    V<A> v;   // for a type parameter: A is the type A<T>
};
A<int> a;
int main() {}
```

### An empty `<>` can't be omitted (¶6)

¶6 When every parameter has a default argument, or there is only a parameter pack, the argument list can be empty, but the `<>` must still be written:

```cpp title="empty-angle.cpp" error
template<class T = char> class String;
String<>* p;     // OK: String<char>
String* q;       // error

template<class... Elements> class Tuple;
Tuple<>* t;      // OK: Elements is empty
Tuple* u;        // error
```

Since C++17, `String s("x");` can omit `<>`, but that is class template argument deduction ([[over.match.class.deduct]]), where `String` is a placeholder to be deduced. The position of `String*` doesn't allow a placeholder.

### Function templates in an overload set (¶9)

¶9 When the name in a template-id finds an overload set, non-template functions and function templates whose parameters don't match the arguments are ignored. Note 2: if none match, the program is ill-formed.

```cpp run title="overload-set.cpp" ok
void f(int);
template<int N> int f() { return N; }
template<class T> int f() { return sizeof(T); }

int a = f<1>();        // only template<int N> remains
int b = f<double>();   // only template<class T> remains
int main() {}
```

### Access is checked where the argument is written (¶5)

```cpp title="access-arg.cpp" error
template<class T> class X {
    static T t;
};

class Y {
    struct S {};   // private
    X<S> x;        // OK: S is accessible inside Y
};

X<Y::S> y;         // error: S is a private member of Y
```

¶5, Note 1: a name in a template argument is subject to access control where it appears. A template parameter is not a class member, so uses of `T` inside the template are not access-checked again. Once `X<S>` has been validly written inside `Y`, nothing `X` does with `Y::S` is affected. This is why a private type can escape a class through a template.

The second half of ¶5 says that when an argument is a class type or class template, the template definition has no special access to the argument's members:

```cpp title="no-special-access.cpp" error
template<template<class TT> class T> class A {
    typename T<int>::S s;      // needs to access B<int>::S
};

template<class U> class B {
    struct S {};               // private
};

A<B> b;                        // error: A cannot access B<int>::S
```

!!! lawyer "Explicit instantiations are not access-checked"
    In contrast to ¶5, [[temp.explicit]] says names in an explicit instantiation are not subject to the usual access checks. Writing `&Class::private_member` as a constant template argument in an explicit instantiation legally obtains a pointer to a private member; this well-known trick relies on exactly that rule.

## Template type arguments [temp.arg.type]

¶1 The argument for a type parameter must be a type (*type-id*). The example and note in ¶2 show that local types, types without names and incomplete types are all allowed:

```cpp run title="type-args.cpp" ok
template<class T> class X {};
template<class T> void f(T) {}
struct {} unnamed_obj;

void g() {
    struct A {};
    enum { e1 };
    typedef struct {} B;
    B b;
    X<A>  x1;          // local type
    X<A*> x2;
    X<B>  x3;          // unnamed class (with a typedef name)
    f(e1);             // unnamed enumeration
    f(unnamed_obj);    // unnamed class
    f(b);
    (void)x1; (void)x2; (void)x3;
}

struct Incomplete;
X<Incomplete>* p;      // incomplete type
int main() { g(); }
```

C++03 did not allow local types and unnamed types as template arguments, on the grounds that they have no linkage, so the specialization could not be referred to from another translation unit. C++11 lifted the restriction. This is essential for lambdas: the closure type of every lambda is an unnamed local type, and if it couldn't be a template argument, `std::sort(v.begin(), v.end(), [](int a, int b) { ... })` would not compile.

## Constant template arguments [temp.arg.nontype]

### It must be able to initialize a static constexpr variable (¶1)

¶1 Let the type of the constant parameter be `T` and the argument `E`. Invent a declaration

```cpp
T x = E ;
```

It must satisfy all the requirements for defining a constexpr variable with static storage duration ([[dcl.constexpr]]). If `T` contains a placeholder such as `auto`, the type of the parameter is deduced from this declaration; if the deduced type cannot be a constant parameter type ([[temp.param#11]]), the program is ill-formed.

Many rules follow directly from this model:

- the argument must be a constant expression;
- pointers and references can only refer to objects or functions with static storage duration, not to local variables;
- an `auto` parameter is deduced as in `auto x = E;`: `char` in `B<'a'>`, and `void` in `B<void(0)>`, which is not allowed.

```cpp title="invented-decl.cpp" error
template<int& r> class A {};
extern int x;
A<x> a;                       // OK

void f(int p) {
    constexpr int& r = p;     // OK per the current draft, see below
    A<r> a2;                  // error: a static constexpr reference can't refer to p
}

template<auto n> struct B {};
B<5>       b1;                // int
B<'a'>     b2;                // char
B<2.5>     b3;                // double (since C++20)
B<void(0)> b4;                // error: deduces void
```

Example 1 in the standard marks `constexpr int& r = p;` as OK. The C++26 draft relaxed the rules so that, within the same function, a constexpr reference can refer to an automatic variable ([[expr.const]]). But `A<r>` is still invalid, because the invented variable has static storage duration and cannot refer to `p`. At the time of writing, Clang 23 doesn't implement this relaxation yet, and rejects `constexpr int& r = p;` itself.

### Non-class types: no narrowing (¶2)

¶2 When the parameter is not of class type and the argument is not a braced list, the argument must be a **converted constant expression** ([[expr.const.const]]) of the parameter's type: only a few implicit conversions are allowed, and no narrowing. The value of the parameter is the converted argument.

```cpp title="converted.cpp" error
template<char c> struct X {};
template<unsigned u> struct U {};

X<'a'> x1;        // OK
X<65>  x2;        // OK: 65 is representable as char
X<300> x3;        // error: narrowing
U<-1>  u1;        // error: narrowing
U<1.0> u2;        // error: floating-to-integral conversion not allowed
```

Constant arguments determine type identity. If `X<300>` silently became `X<44>`, the two would be the same type, which is almost never what the programmer meant.

The example in ¶8 lists the permitted conversions: array-to-pointer, adding const, and selecting a function from an overload set.

```cpp run title="arg-conversions.cpp" ok
template<const int* pci> struct X {};
int ai[10];
X<ai> xi;                  // array to pointer, then add const

struct Y {};
template<const Y& b> struct Z {};
Y y;
Z<y> z;                    // no conversion; the reference adds const

template<int (&pa)[5]> struct W {};
int b[5];
W<b> w;                    // no conversion

void f(char);
void f(int);
template<void (*pf)(int)> struct A {};
A<&f> a;                   // overload resolution selects f(int)

template<int i> struct C {};
C<{ 42 }> c1;              // braced list, see ¶5

void f(char) {}
void f(int) {}
int main() {}
```

`C<{ 42 }>` is valid; Clang 23 gives a `-Wbraced-scalar-init` warning.

### Class types: copied into a unique template parameter object (¶3–¶5)

¶3 When the parameter is of class type, or the argument is a braced list, the standard introduces a temporary variable

```cpp
constexpr T v = A;
```

whose lifetime ends immediately after it is initialized. Such a `v` is called a **candidate initializer**.

¶5 For a non-class type (where the argument is a braced list), the value of the parameter is the value of `v`, so `template<int i>` can accept `C<{42}>`.

¶4 For a class type, the parameter designates a template parameter object ([[temp.param#13]]) that is copy-initialized from some candidate initializer equivalent to `v`. The program is ill-formed if any of the following happens:

- ¶4.1 the initialization itself is ill-formed;
- ¶4.2 the initialization is not a constant expression;
- ¶4.3 the object obtained by copying is not template-argument-equivalent to `v` ([[temp.type]]).

Why so roundabout? The same value has only one template parameter object in the whole program, but different translation units can write that value with different argument expressions. The standard has to guarantee that whichever expression the copy comes from, the resulting object is the same. If the copy constructor changes the value, the unique object can't be determined, so ¶4.3 makes it ill-formed.

```cpp title="candidate-init.cpp" error
template<auto> struct B {};

struct J1 {
    J1* self = this;     // points to itself
};
B<J1{}> j1;    // error: the initialization is not a constant expression (¶4.2)

struct J2 {
    J2* self = this;
    constexpr J2() {}
    constexpr J2(const J2&) {}   // after copying, self points to the new object
};
B<J2{}> j2;    // error: the copy is not equivalent to v (¶4.3)
```

Clang 23 rejects both lines, but for both it gives the reason "pointer to temporary object is not allowed in a template argument", which is the ¶6 check in the next section. The conclusion is the same.

### What pointers and references cannot point to (¶6)

¶6 A constant argument of reference or pointer type, and a member of reference or pointer type in an argument of class type, cannot refer or point to:

- ¶6.1 a temporary object ([[class.temporary]]);
- ¶6.2 a string literal object ([[lex.string]]);
- ¶6.3 the result of a `typeid` expression ([[expr.typeid]]);
- ¶6.4 the predefined variable `__func__` ([[dcl.fct.def.general]]);
- ¶6.5 a subobject of any of the above.

What these objects have in common is an unstable identity. Whether two identical string literals are the same object is unspecified, and in different translation units they are usually different objects. The result of `typeid(int)` may be a different object in different shared libraries; every function has its own `__func__`. If they were allowed as template arguments, `X<"abc">` could be two different types in two translation units.

Everything outside this list is allowed, including, since C++20, addresses of subobjects and past-the-end pointers:

```cpp run title="subobject-ptr.cpp" ok
int arr[3];
struct S { int m; } s;

template<int* p> struct P {};
P<&arr[1]> pa;      // address of an array element (since C++20)
P<&s.m>    pm;      // address of a member (since C++20)
P<&arr[3]> pe;      // past-the-end pointer
P<nullptr> pn;
int main() {}
```

In C++17 and earlier, a pointer argument had to point to a complete object and could not be a past-the-end pointer. C++20's [[P1907R1]] removed these restrictions.

### Strings as template arguments (¶9)

<div class="compare" markdown="1">

```cpp error
template<const char* p>
struct X {};

X<"Studebaker"> x;  // error
X<"Knope" + 1> x2;  // error: subobject

const char p[] = "Vivisectionist";
X<p> y;             // OK: named array
```

```cpp ok
struct A {
  constexpr A(const char*) {}
};
template<A a> struct Y {};

// the literal is just a constructor argument
Y<"Pyrophoricity"> z;
```

</div>

¶9, Note 2: a string literal cannot be the argument for a constant parameter of non-class type, because its value would point to a string literal object (¶6.2). The `p` on the left is a named array initialized from a literal; it is not a string literal object itself, so it is fine.

The right side shows how, since C++20, a string can be a template argument: the parameter is of class type, and the literal is only used to initialize the template parameter object. The `fixed_string` below copies the characters into its own array, so the template parameter object holds the character values, not a pointer to the literal:

```cpp run title="fixed-string.cpp" ok
#include <cstddef>
#include <cstdio>
#include <type_traits>

template<std::size_t N>
struct fixed_string {
    char data[N]{};
    constexpr fixed_string(const char (&s)[N]) {
        for (std::size_t i = 0; i < N; ++i) data[i] = s[i];
    }
};

template<fixed_string S>   // placeholder for a deduced class type ([temp.param]/11.3)
struct Named {
    static void print() { std::puts(S.data); }
};

static_assert(!std::is_same_v<Named<"a">, Named<"b">>);
static_assert(std::is_same_v<Named<"a">, Named<"a">>);   // compared by value

int main() { Named<"hello">::print(); }
```

If `fixed_string` stored a `const char*`, we would be back to pointing at a string literal.

### References can't bind to temporaries (¶10)

¶10, Note 3: when the parameter is of reference type, an argument that would need a temporary cannot be used:

```cpp title="temporary-arg.cpp" error
template<const int& CRI> struct B {};
B<1> b1;                  // error: would need a temporary
int c = 1;
B<c> b2;                  // OK

struct X { int n; };
struct Y { const int& r; };
template<Y y> struct C {};
C<Y{X{1}.n}> c;           // error: the reference member binds to a subobject of a temporary
```

## Template template arguments [temp.arg.template]

### The argument must name a template (¶1–¶3)

¶1 The argument for a template template parameter must be the name of a template. ¶3 specifies which kind of parameter accepts which kind of template; a parameter and argument that meet this are called **compatible**:

| Parameter | Argument |
|---|---|
| type template template parameter `template<...> class` | a class template, an alias template, or another type template template parameter |
| variable template template parameter `template<...> auto` {{c++26}} | a variable template, or another variable template template parameter |
| concept template parameter `template<...> concept` {{c++26}} | a concept, or another concept template parameter |

Only the primary template is considered for matching; partial specializations are not considered even if their parameter lists would fit. ¶2 However, when a specialization is used through a template template parameter, the partial specializations of the primary template take part in selection as usual:

```cpp run title="tt-partial.cpp" ok
#include <type_traits>
template<class T> class A { public: int x; };        // primary template
template<class T> class A<T*> { public: long x; };   // partial specialization

template<template<class U> class V> class C {
public:
    V<int>  y;     // uses the primary template: y.x is int
    V<int*> z;     // uses the partial specialization: z.x is long
};

C<A> c;
static_assert(std::is_same_v<decltype(c.y.x), int>);
static_assert(std::is_same_v<decltype(c.z.x), long>);
int main() {}
```

If a partial specialization is not reachable at the point of instantiation but would have been selected had it been reachable, the program is ill-formed, no diagnostic required.

### Whatever the parameter can do, the argument must accept (¶4–¶5)

```cpp run title="p0522.cpp" ok
#include <vector>

template<template<class> class C>
struct Wrap { C<int> c; };

Wrap<std::vector> w;   // OK (since C++17)

template<class T> class A {};
template<class T, class U = T> class B {};
template<class... Types> class C {};
template<auto n> class D {};
template<template<class> class P> class X {};
template<template<class...> class Q> class Y {};
template<template<int> class R> class Z {};

X<A> xa;   // OK
X<B> xb;   // OK: U has a default argument (ill-formed before C++17)
X<C> xc;   // OK: a pack can accept one argument
Y<A> ya;   // OK
Y<B> yb;   // OK
Y<C> yc;   // OK
Z<D> zd;   // OK: an auto parameter can accept an int value (ill-formed before C++17)
int main() {}
```

`template<template<class> class C>` amounts to a promise that the template will only ever write `C<X>` with one type argument. `std::vector` has two parameters, but the second has a default argument, so `std::vector<X>` is perfectly valid, and `std::vector` is an acceptable argument.

¶4 Precisely: an argument `A` matches a parameter `P` if `A` is compatible with `P` and `P` is **at least as specialized as** `A`. If `P` is unconstrained, the constraints of `A` are ignored.

¶5 At-least-as-specialized is determined by rewriting both as function templates and applying the partial ordering rules for function templates ([[temp.func.order]]). Imagine a class template `X` whose template head is exactly that of `A`, including default arguments and constraints; then write two function templates whose template parameters come from `P` and from `A` respectively, each with one function parameter of type `X<...>`. With `P = template<class> class` and `A = std::vector`:

```cpp
template<class T, class Alloc = std::allocator<T>> class X;   // template head taken from A

template<class T>              void fP(X<T>);          // corresponds to P
template<class T, class Alloc> void fA(X<T, Alloc>);   // corresponds to A
```

`X<T>` is `X<T, std::allocator<T>>`, so `T` and `Alloc` of `fA` can be deduced from the parameter of `fP`; therefore `fP` is at least as specialized as `fA`, and `std::vector` matches. If the rewrite produces an invalid type, `P` is not at least as specialized as `A`.

The second half of ¶4 handles a `P` that contains a parameter pack: then `A` also matches `P` if each parameter of `A` matches the corresponding parameter of `P`. Two parameters match if they are of the same kind, constant parameters have equivalent types ([[temp.over.link]]), and the parameters of template template parameters match recursively. A parameter pack in `P` can correspond to zero or more parameters of the same kind in `A`, whether or not they are packs. So `Y<A>` and `Y<B>` are valid, even though writing `Q<int, int, int>` inside `Y` would fail at instantiation:

```cpp title="pack-tt-use.cpp" error
template<class T, class U = T> class B {};
template<template<class...> class Q> struct Y1 { Q<int, int, int> q; };
Y1<B> y;    // matches, but at instantiation B<int, int, int> has too many arguments: error
```

### Matching with constraints

Example 4 in ¶4 shows how constraints take part in matching. `P` being at least as specialized as `A` means `P`'s constraints must subsume ([[temp.constr.order]]) `A`'s:

```cpp title="tt-constraints.cpp" error
template<typename T> concept C = requires (T t) { t.f(); };
template<typename T> concept D = C<T> && requires (T t) { t.g(); };

template<template<C> class P> struct S {};

template<C> struct X {};
template<D> struct Y {};
template<typename T> struct Z {};

S<X> s1;   // OK: same constraints
S<Y> s2;   // error: Y requires D, stricter than the C that P guarantees
S<Z> s3;   // OK: Z is unconstrained
```

`S` only guarantees that it instantiates `P` with types that satisfy `C`. `Y` requires `D`, and `S` might hand it a type that only satisfies `C`, so it is rejected. `Z` accepts any type and is safe.

When `P` is unconstrained, the constraints of `A` are ignored, so `template<template<class> class P>` can accept `template<std::integral T> class A`. This is for compatibility with pre-C++20 code: most existing template template parameters are unconstrained, and if constrained arguments were always rejected, a lot of user code would break as soon as standard library components gained constraints. The cost is that writing `P<double>` inside the template only fails, with unsatisfied constraints, at instantiation.

### No parameter matches every class template

```cpp title="eval.cpp" error
template<class T> struct eval;
template<template<class, class...> class TT, class T1, class... Rest>
struct eval<TT<T1, Rest...>> {};

template<class T1> struct A;
template<class T1, class T2> struct B;
template<int N> struct C;
template<class T1, int N> struct D;
template<class T1, class T2, int N = 17> struct E;

eval<A<int>> eA;           // OK: matches the partial specialization
eval<B<int, float>> eB;    // OK
eval<C<17>> eC;            // error: C's parameter is a constant parameter
eval<D<int, 17>> eD;       // error: D's second parameter is a constant parameter
eval<E<int, float>> eE;    // error: E has a constant parameter, even with a default argument
```

`template<class, class...> class TT` looks as if it would match any class template, but constant parameters and type parameters never match each other. The partial specialization doesn't match for the last three lines, so the primary template `eval`, which is only declared, is used, hence the errors.

## Implementation notes

!!! impl
    - [[P0522R0]] relaxed the matching of template template arguments in C++17, but it introduced new partial ordering ambiguities: the same argument can match the template template parameters of several partial specializations. For a long time Clang therefore didn't enable it by default and required `-frelaxed-template-template-args`; recent versions enable it by default. Clang 23 accepts the `Wrap<std::vector>` above by default.
    - Clang gives a specific reason for each violation of ¶6, such as "pointer to temporary object is not allowed in a template argument" and "reference to type_info object is not allowed in a template argument".
    - The template parameter object for a constant argument of class type is a mergeable read-only constant in the object file; see the implementation notes in [[temp.param]].

## History

!!! history
    - C++98/03: constant arguments could only be integral constant expressions or addresses of objects and functions with external linkage, which had to be written in the form `&obj`; local types and unnamed types could not be type arguments.
    - C++11: allowed objects with internal linkage, `nullptr`, and constant expressions whose value is a null pointer; local and unnamed types could be type arguments.
    - C++17: every constant argument can be a general converted constant expression ([[N4268]]); relaxed matching of template template arguments ([[P0522R0]]); `template<auto>`.
    - C++20: constant arguments of class type and floating-point type ([[P0732R2]], [[P1907R1]]); pointers and references to subobjects allowed; constraints take part in matching template template arguments.
    - C++26: concepts and variable templates can be template template arguments ([[P2841]]); interpretation rules for arguments in name form (¶3); "non-type" renamed "constant".

## Common misconceptions

!!! pitfall "Since C++20 a string literal can always be a template argument"
    `X<"abc">` only works when `X`'s parameter is of class type (such as `fixed_string`). A `const char*` parameter never accepts a string literal (¶6.2, ¶9).

!!! pitfall "`template<char c>` accepts `X<300>` and truncates it"
    A converted constant expression doesn't allow narrowing, so `X<300>` is ill-formed (¶2).

!!! pitfall "An unconstrained template template parameter rejects constrained arguments"
    It doesn't. When `P` is unconstrained the argument's constraints are ignored, and problems only show up at instantiation (¶4).

## Questions

!!! question "Question 1"
    Which of these template arguments are valid?

    ```cpp
    template<const char* p> struct S {};
    static const char a[] = "x";
    constexpr const char* q = "y";
    S<a> s1;          // (a)
    S<q> s2;          // (b)
    S<&a[1]> s3;      // (c)
    ```

<details markdown="1">
<summary>Answer</summary>

- (a) Valid. `a` is a named array initialized from a literal, not a string literal object; an array-to-pointer conversion is all that's needed.
- (b) Invalid. The value of `q` points to a string literal object (¶6.2).
- (c) Valid (since C++20). `a` has two elements, `'x'` and `'\0'`, and `&a[1]` points to an element of a named array.
</details>

!!! question "Question 2"
    Given

    ```cpp
    template<std::integral T> struct I {};
    template<std::signed_integral T> struct J {};
    template<template<class> class P> struct S1 {};
    template<template<std::integral T> class P> struct S2 {};
    template<template<std::signed_integral T> class P> struct S3 {};
    ```

    which of `S1<I>`, `S2<J>` and `S3<I>` are valid?

<details markdown="1">
<summary>Answer</summary>

- `S1<I>` is valid: `P` is unconstrained, so `I`'s constraints are ignored (¶4).
- `S2<J>` is invalid: `P`'s constraint is `std::integral<T>`, while `J` requires `std::signed_integral<T>`. The standard library defines the latter as `integral<T> && is_signed_v<T>`; the former doesn't subsume the latter, so `P` is not at least as specialized as `J`.
- `S3<I>` is valid: after normalization `std::signed_integral<T>` subsumes `std::integral<T>`; `S3` only instantiates `P` with signed integers, all of which `I` accepts.

Subsumption is determined by the normalized definitions of the concepts, not by their names.
</details>

<details class="fine" markdown="1"><summary>Remaining wording</summary>

[temp.arg.general] ¶2 defines the template argument list of a template head: the n-th argument is the n-th parameter itself, and a pack parameter `Ts` corresponds to the pack expansion `Ts...`. It is used to describe the primary template itself; for example, the argument list of a partial specialization cannot be identical to it ([[temp.spec.partial]]).

¶7 When explicitly calling the destructor of an object of a class template specialization, template arguments can be written: both `p->A<int>::~A()` and `q->A<int>::~A<int>()` are allowed. Clang 23 gives a `-Wdtor-name` warning for the former under `-pedantic`; the standard's example marks it OK.

¶8 If the use of a template argument gives rise to an ill-formed construct in the instantiation of a specialization, the program is ill-formed. Substitution failures in function template deduction are handled separately by [[temp.deduct]].

¶10 When a template-id does not name a function, a default template argument is implicitly instantiated when its value is needed; for example, `S<bool>*` needs the `int` in `S<bool, int>`.

¶11 A template argument followed by an ellipsis is a pack expansion ([[temp.variadic]]).

</details>
