---
title: Template parameters
summary: The kinds of parameters a template can declare, which types a constant template parameter can have, where default template arguments go and how they merge, and the restrictions on parameter packs.
updated: 2026-10-19
---

!!! tldr
    - There are five kinds of template parameters: type, constant (formerly non-type), type template template, variable template template, and concept template parameters; the last two are new in C++26.
    - The constraint in `template<C T>` inserts `T` as the first argument of the concept: `C<A> T` means `C<T, A>`, and `C... Ts` means `(C<Ts> && ...)`.
    - The type of a constant template parameter must be a structural type: a scalar, an lvalue reference, or a literal class whose members are all public, non-mutable and of structural type. Neither `std::string` nor `std::string_view` qualifies.
    - A constant template parameter of class type is a `const` lvalue inside the template, and each value corresponds to exactly one template parameter object in the whole program.
    - In a class template, every parameter after one with a default argument must also have a default argument; function templates don't have this restriction, because their arguments are mostly deduced.

**Template parameters** are the names listed in `template<...>` in a template declaration. They are the template's inputs: the template arguments given when the template is used ([[temp.arg]]) correspond one by one to these parameters, and substituting them yields a concrete class, function or variable.

## The five kinds of template parameters (¶1–¶3)

```cpp run title="five-kinds.cpp" ok
#include <concepts>
#include <vector>

template<class T> constexpr bool always = true;
template<class T> concept Small = sizeof(T) <= 4;

template<
    class T,                              // type template parameter
    int N,                                // constant template parameter
    template<class...> class Container,   // type template template parameter
    template<class> auto Trait,           // variable template template parameter (C++26)
    template<class> concept Concept       // concept template parameter (C++26)
>
struct All {
    Container<T> c;
    static constexpr bool ok = Trait<T> && Concept<T> && N > 0;
};

static_assert(All<int, 1, std::vector, always, Small>::ok);
int main() {}
```

¶2 By how they are declared, template parameters fall into five kinds, each accepting one kind of argument:

| Kind | Written as | Accepts |
|---|---|---|
| type template parameter | `class T`, `typename T`, `std::integral T` | a type |
| constant template parameter | `int N`, `auto V`, `Point p` | a value |
| type template template parameter | `template<class> class TT` | a class template or alias template |
| variable template template parameter {{c++26}} | `template<class> auto VT` | a variable template |
| concept template parameter {{c++26}} | `template<class> concept CT` | a concept |

¶3 The last three are collectively called **template template parameters**: their argument is a template, not a type or a value.

In C++23 and earlier, a constant template parameter was called a **non-type template parameter** (NTTP). Once C++26 added variable template template parameters and concept template parameters, "non-type" no longer distinguished value parameters from the others, so the draft renamed them constant template parameters. The rules themselves did not change; when reading older material, just map NTTP to the new term.

### Why pass concepts and variable templates

Before C++26, the only way to pass a predicate to a template was to wrap it in a class template, write `template<class> class Pred` and use `Pred<T>::value`. A variable template like `std::is_integral_v` or a concept like `std::integral` could not be passed directly. C++26's [[P2841]] added these two kinds of parameters:

```cpp run title="concept-param.cpp" ok
#include <concepts>

// every Ts satisfies C
template<template<class> concept C, class... Ts>
concept all_satisfy = (C<Ts> && ...);

static_assert(all_satisfy<std::integral, int, long, char>);
static_assert(!all_satisfy<std::integral, int, double>);

// constrain a function parameter with a concept template parameter
template<template<class> concept C>
void take(C auto) {}

int main() { take<std::integral>(42); }
```

Clang 23 compiles both examples above; older compilers report syntax errors.

### Parameter names (¶8)

¶8 A type name or template name declared in a template parameter is not subject to name lookup, because it introduces a new name. Within the scope of the template declaration, the name of a type template parameter is a *typedef-name*, the name of a template template parameter is a *template-name*, and the name of a concept template parameter is a *concept-name*.

So `T` can be used like a typedef, but not in an elaborated type specifier such as `struct T`.

## Type template parameters

### `class` and `typename` (¶7)

¶7 `template<class T>` and `template<typename T>` are exactly equivalent. What matters is what follows `typename`: followed by a simple name, it declares a type parameter; followed by a qualified name (such as `T::type`), the whole parameter is a constant parameter of type `T::type`.

```cpp run title="class-vs-typename.cpp" ok
struct S { using type = int; };

template<class T, typename T::type N>   // T is a type parameter, N a constant parameter
struct Q { static constexpr auto value = N; };

static_assert(Q<S, 3>::value == 3);
int main() {}
```

`class T` always declares a type parameter, even if the enclosing scope happens to have a class named `T`:

```cpp run title="class-T.cpp" ok
class T {};
int i;

template<class T, T i> void f(T t) {
    T t1 = i;         // template parameters T and i
    ::T t2 = ::T();   // the global class T
    (void)t; (void)t1; (void)t2;
}

int main() { f<int, 3>(0); }
```

Here `f` has a type parameter named `T`, not an unnamed constant parameter of type `class T`.

The end of ¶7 adds two restrictions: a constant template parameter cannot have a storage class specifier (`template<static int N>` is invalid), and a template parameter declaration cannot define a new type (`template<struct Q {} q>` is invalid).

### Constraining type parameters with concepts (¶9–¶10)

Since C++20, a type parameter can use a *type-constraint* in place of `class`, as in `template<std::integral T>`. A type constraint is a concept name, optionally with some of its template arguments.

```cpp run title="immediately-declared.cpp" ok
#include <concepts>
template<typename T> concept C1 = true;
template<typename... Ts> concept C2 = true;
template<typename T, typename U> concept C3 = true;

template<C1 T> struct s1;          // constraint C1<T>
template<C1... T> struct s2;       // (C1<T> && ...)
template<C2... T> struct s3;       // (C2<T> && ...), not C2<T...>
template<C3<int> T> struct s4;     // C3<T, int>
template<C3<int>... T> struct s5;  // (C3<T, int> && ...)

template<std::convertible_to<long> T>
struct s6;                         // std::convertible_to<T, long>
int main() {}
```

¶9 The rule: the constrained type `T` is always inserted as the first argument of the concept. A type constraint written `C<A1, ..., An>` gives `C<T, A1, ..., An>`, and one written `C` gives `C<T>`. If `T` is a pack, the result is further wrapped in a fold expression `(C<T> && ...)`, checking each element separately. The constraint expression obtained this way is called the **immediately-declared constraint** ([[g:immediately-declared-constraint]]).

¶10 A type parameter that starts with a type constraint adds that immediately-declared constraint to the template's associated constraints ([[temp.constr.decl]]).

`T` goes first so that `template<std::convertible_to<long> T>` reads like "T convertible to long". The standard library's binary concepts (`same_as`, `derived_from`, `convertible_to`, and so on) all follow the convention that the constrained type comes first.

`s3` is easy to misread: `C2` itself is a variadic concept, but `C2... T` still expands to checking `C2<T>` for each element, not a single check of `C2<T...>`.

¶9 also requires the concept named by a type constraint to be a **type concept** ([[temp.concept#7]]), that is, a concept whose first parameter is a type parameter:

```cpp title="value-concept.cpp" error
template<int N> concept Positive = N > 0;
template<Positive T> struct X {};   // error: Positive is not a type concept
```

¶16 The same mechanism is used for constant parameters. If the type of a constant parameter contains a constrained placeholder, such as `std::integral auto`, the immediately-declared constraint is applied to the type deduced for the placeholder:

```cpp title="constrained-auto.cpp" error
#include <concepts>
template<std::integral auto N> struct I {};
I<3>   a;     // OK
I<3.0> b;     // error: double does not satisfy std::integral
```

### Two restrictions on type constraints (¶4–¶5)

¶4 The qualifying part of a type constraint (its *nested-name-specifier*) cannot depend on an enclosing template parameter. Constraints take part in normalization and subsumption at the point of the template definition ([[temp.constr.normal]]), so it must be known at that point which concept is meant.

This rule also removes an ambiguity. In `template<T::C U>`, if `T` is an enclosing template parameter, `T::C` cannot be a type constraint, so it can only be the type of a constant parameter. [[temp.res.general#4]] also lists this position as a context where only a type can appear, so `typename` isn't needed:

```cpp run title="dependent-nns.cpp" ok
namespace N { template<class T> concept C = true; }
template<N::C T> struct X {};      // OK: N does not depend on a template parameter

template<class T>
struct W {
    template<T::C U>               // a constant parameter of type typename T::C
    static constexpr auto g() { return U; }
};
struct S { using C = int; };
static_assert(W<S>::g<3>() == 3);
X<int> x;
int main() {}
```

¶5 A concept template parameter cannot be constrained. A concept itself cannot be constrained ([[temp.concept#4]]), and the same goes for a concept used as a parameter:

```cpp title="constrained-concept-param.cpp" error
#include <concepts>
template<template<std::integral T> concept C>   // error: violates ¶5
struct X {};
```

At the time of writing, Clang 23 accepts this code without a diagnostic. By the standard it is ill-formed.

## Types of constant template parameters (¶11–¶15)

### Why restrict the type

The value of a constant template parameter is part of a type's identity. Whether `X<a>` and `X<b>` are the same type depends on whether `a` and `b` are **template-argument-equivalent** ([[temp.type#2]]). That comparison has to meet a few conditions:

1. It can be done at compile time, so the value must be computable during constant evaluation;
2. It gives the same result in every translation unit. The linker merges identical specializations by their mangled symbol names, so the value must be encodable member by member into the symbol name;
3. It doesn't depend on a user-written `operator==`. Otherwise different translation units might see different `==` operators, or `==` might not even be an equivalence relation, and the type system could not stay consistent.

The standard's approach is to allow only types that can be compared member by member, and to compare them only member by member.

### Structural types (¶11–¶12)

¶11 The type of a constant template parameter must be one of the following (possibly cv-qualified):

- ¶11.1 a structural type;
- ¶11.2 a type that contains a placeholder, such as `auto`, `auto*`, `decltype(auto)` or `std::integral auto` ([[dcl.spec.auto]]) {{c++17}};
- ¶11.3 a placeholder for a deduced class type, i.e. only the class template name is written and class template argument deduction determines the concrete type, as in `template<fixed_string s>` ([[dcl.type.class.deduct]]) {{c++20}}.

Top-level cv-qualifiers on the parameter are ignored; `template<const int N>` declares the same kind of parameter as `template<int N>`.

¶12 A **structural type** ([[g:structural-type]]) is one of:

- ¶12.1 a scalar type: arithmetic types, enumerations, pointers, pointers to members, `std::nullptr_t`, and C++26's reflection type `std::meta::info`;
- ¶12.2 an lvalue reference type;
- ¶12.3 a literal class type ([[basic.types.general]]) that meets two conditions:
    - ¶12.3.1 all base classes and non-static data members are public and non-mutable;
    - ¶12.3.2 the types of all base classes and non-static data members are structural types or (possibly multidimensional) arrays thereof.

Members must be public because the result of a member-wise comparison is directly observable by the user and must not expose private implementation details. They must be non-mutable because the template parameter object is `const` and its value cannot change. A structural type doesn't need to be trivial and can have user-written constructors; it also has nothing to do with `operator==`.

```cpp title="structural.cpp" error
#include <array>
#include <string_view>
#include <utility>

struct P1 { int x, y; };                    // structural
struct P2 { int x; private: int y = 0; };   // has a private member
struct P3 { mutable int x; };               // has a mutable member
struct P4 { double d; int* p; int& r; };    // structural
struct P5 : P1 { float f[3]; };             // structural

template<P1 p> struct A1 {};
template<P2 p> struct A2 {};                // error: P2 is not a structural type
template<P3 p> struct A3 {};                // error: P3 is not a structural type
template<P4 p> struct A4 {};
template<P5 p> struct A5 {};

template<std::array<int, 3> a> struct B1 {};    // OK
template<std::pair<int, int> p> struct B2 {};   // OK with libc++
template<std::string_view s> struct B3 {};      // error: has private members
```

Clang checks whether the type is structural where the parameter is declared, so the error is reported on the `template<P2 p>` line rather than at a use.

!!! warning "Most standard library types are not guaranteed to be structural"
    The standard library only specifies the public interface of its classes; data members are usually private or exposition-only. `std::array` is an aggregate and works as a constant parameter type in real implementations; in our tests libc++'s `std::pair` works too. `std::tuple`, `std::optional`, `std::string_view` and `std::string` were all rejected in our tests. For portable code, it's best to define your own aggregate with all members public.

Rvalue references and `void` cannot be the type of a constant parameter. The note in ¶14 calls out `void` specifically; `void*` is fine, since it's a pointer:

```cpp title="void-param.cpp" error
template<void v> class X;       // error
template<void* pv> class Y;     // OK
template<int&& r> class Z;      // error: an rvalue reference is not a structural type
```

### Floating point, lambdas and unions

Since C++20, floating-point types are valid constant parameter types, because they are scalars. But equivalence of floating-point arguments requires the two values to be identical, not merely `==`. `0.0 == -0.0`, but their bit patterns differ, so they are different arguments ([[temp.type#2]]).

```cpp run title="float-nttp.cpp" ok
#include <type_traits>
template<double D> struct F {};
static_assert(!std::is_same_v<F<0.0>, F<-0.0>>);
static_assert(std::is_same_v<F<0.1 + 0.2>,
                             F<0.30000000000000004>>);

template<auto L> struct Lam {};
// each lambda has its own closure type
static_assert(!std::is_same_v<Lam<[]{}>, Lam<[]{}>>);

union U { int i; float f; };
template<U u> struct UU {};
// a different active member means a different argument
static_assert(!std::is_same_v<UU<U{.i = 0}>, UU<U{.f = 0}>>);
int main() {}
```

The closure type of a captureless lambda is a literal class with no data members, so it is a structural type. A union is also a structural type as long as all its members are public, non-mutable and of structural type.

### Array and function types are adjusted to pointers (¶15)

¶15 As with function parameters, a constant parameter of type "array of `T`" or of function type `T` is adjusted to "pointer to `T`":

```cpp run title="adjust.cpp" ok
template<int* a>   struct R {};
template<int b[5]> struct S {};   // adjusted to int*
int p;
R<&p> w;        // OK
S<&p> x;        // OK: the parameter has been adjusted to a pointer
int v[5];
R<v> y;         // OK: array-to-pointer conversion on the argument
S<v> z;         // OK: both
int main() {}
```

To pass the array itself, use a reference to an array, `template<int (&arr)[5]>`; references are not adjusted.

## Template parameter objects (¶13)

<div class="compare" markdown="1">

```cpp error
template<int i>
void f() {
  i++;         // error: i is a prvalue
  (void)&i;    // error: cannot take its address
}
```

```cpp ok
struct A { int v; };
template<A a>
void g() {
  (void)&a;    // OK: a is an lvalue
  const A& r = a;   // binds to the object itself
  (void)r;
}
```

</div>

¶13 A constant parameter of class type designates an object that really exists inside the template, called a **template parameter object** ([[g:template-parameter-object]]). It has static storage duration and type `const T`. No two template parameter objects are template-argument-equivalent; in other words, each value corresponds to exactly one object in the whole program.

Note 3 explains the value category of each kind of parameter when used in an expression:

| Type of the parameter | Using it in the template gives | Address can be taken? |
|---|---|---|
| non-class, non-reference (`int i`) | a prvalue | no |
| class type `T` (`A a`) | an lvalue of type `const T`, i.e. the template parameter object | yes |
| reference type (`const X& x`) | an lvalue of the referenced object | yes |

So `int& ri = i;` is an error, because `i` is a prvalue and a non-const lvalue reference can't bind to it; `const int& cri = i;` is fine, and binds to a temporary.

That each value corresponds to one object is observable:

```cpp run title="param-object-identity.cpp" ok
struct A { int v; };

template<A a> constexpr const A* addr() { return &a; }

static_assert(addr<A{1}>() == addr<A{1}>());   // the same object
static_assert(addr<A{1}>() != addr<A{2}>());
int main() {}
```

String literals are the opposite: whether two string literals with the same contents are the same object is unspecified ([[lex.string]]). This is one of the reasons a string literal cannot be used as a constant argument of pointer type ([[temp.arg.nontype#6]]).

Note 2 adds that C++26 reflection facilities (such as `std::define_static_array`, [[meta.define.static]]) can create template parameter objects of array type. The name of a constant template parameter never designates such an object, and its address may coincide with that of another live object ([[intro.object]]).

## Default template arguments (¶17–¶21)

### Where they can go (¶17)

¶17 A **default template argument** is the argument after `=` in a template parameter. It can be written in a template declaration, with a few places where it cannot:

```cpp title="default-where.cpp" error
template<class... Ts = int> struct P;    // error: a parameter pack cannot have a default argument

template<class T> struct A {
    template<class U> void f();
};
template<class T> template<class U = int>
void A<T>::f() {}                        // error: out-of-class member definition

template<class T> struct C {
    template<class U = int>
    friend void h(U);                    // error: must be a definition
    template<class U = int>
    friend void k(U) {}                  // OK
};
```

The full rules are:

1. A parameter pack cannot have a default argument;
2. When a member of a class template is defined outside the class, its template parameter list cannot contain default arguments; they can only go on the declaration inside the class;
3. A friend class template declaration cannot have default arguments;
4. If a friend function template declaration has a default template argument, that declaration must be a definition, and no other declaration of it may be reachable from it or vice versa.

The last two make sure a template has the same default arguments wherever it is seen. A friend declaration is written inside a class but declares an entity of the enclosing namespace. If it could add default arguments, whether a template had a default argument would depend on which classes had been instantiated.

At the time of writing, Clang 23 does not diagnose default arguments on friend class templates (rule 3), nor the second half of rule 4.

### Merging across declarations (¶18)

¶18 Default arguments in multiple declarations of the same template are merged, the same way as default arguments of functions ([[dcl.fct.default]]):

```cpp run title="merge.cpp" ok
#include <type_traits>
template<class T1, class T2 = int> class A;
template<class T1 = int, class T2> class A;   // merged: <int, int>
template<class T1, class T2> class A {};

static_assert(std::is_same_v<A<>, A<int, int>>);
int main() {}
```

In the second declaration `T1` has a default argument and `T2` doesn't, which seems to violate the ordering rule below, but after merging `T2` already has a default argument, so it is valid. A default argument for the same parameter can be given only once, even if both values are the same.

### Order: class templates and function templates differ (¶19)

<div class="compare" markdown="1">

```cpp error
// class template: after a default argument
// every parameter needs one
template<class T = int, class U>
struct S;  // error
```

```cpp ok
// function template: U can be deduced
template<class T = int, class U>
void f(U) {}

int main() { f(1.0); }  // T=int
```

</div>

¶19 Arguments of a class template can only be given by position: the `X` in `S<X>` always goes to the first parameter. If a parameter without a default argument followed one with a default, it could never receive an argument. Arguments of a function template are mostly deduced and position doesn't matter, so there is no such restriction. The full rules:

| Kind of template | After a parameter with a default argument | Position of a parameter pack |
|---|---|---|
| class, variable and alias templates | every later parameter needs a default argument or is a parameter pack | in a primary template, a parameter pack must be last |
| function templates | no restriction | parameters after a pack must be deducible from the function parameters or have default arguments |
| deduction guide templates | no restriction | parameters without default arguments must be deducible from the parameters of the deduction guide |

```cpp title="default-order.cpp" error
template<class R = void, class... Args, class F>
R invoke_like(F, Args...);                   // OK: both Args and F can be deduced

template<class... T, class... U> void g() {} // error: U cannot be deduced
template<class... T, class U> void h() {}    // error: same
```

At the time of writing, Clang 23 does not diagnose the declarations of `g` and `h`; it only reports a deduction failure at the call. Example 8 in the standard explicitly marks them ill-formed.

The pack-must-be-last rule applies only to primary templates. The parameters of a partial specialization are all deduced from the arguments of the primary template, so its parameter pack can go anywhere:

```cpp run title="pack-not-last.cpp" ok
#include <type_traits>
template<class... Ts> struct List {};
template<class L, class T> struct Append;

template<class... Ts, class T>        // partial specialization: pack not last, OK
struct Append<List<Ts...>, T> { using type = List<Ts..., T>; };

static_assert(std::is_same_v<Append<List<int>, char>::type,
                             List<int, char>>);
int main() {}
```

In C++98 function templates could not have default template arguments at all; this was allowed only from C++11 ([[CWG226]]). The `template<class T, class = std::enable_if_t<...>>` idiom, which uses a default template argument for SFINAE, depends on it.

### `>` in a default argument (¶20)

¶20 In the default argument of a constant parameter, the first `>` that is not inside parentheses is taken as the end of the parameter list:

```cpp title="gt-default.cpp" error
template<int i = 3 > 4 > class X {};      // error: syntax error
template<int i = (3 > 4) > class Y {};    // OK
```

Template argument lists have the same rule ([[temp.names#8]]). Always parenthesize a `>` operator inside angle brackets.

### Default arguments for parameters of a template template parameter (¶21)

¶21 The parameters of a template template parameter can have default arguments too, but they apply only within that one declaration and do not merge across declarations like ordinary default arguments:

```cpp title="tt-default.cpp" error
template<template<class TT = float> class T> struct A {
    void f();
    void g();
};
template<template<class TT> class T> void A<T>::f() {
    T<> t;            // error: TT has no default argument here
}
template<template<class TT = char> class T> void A<T>::g() {
    T<> t;            // OK: T<char>
}
```

The last sentence of ¶21 {{c++26}}: a constraint of a template template parameter cannot depend on a concept template parameter in the same list; such a constraint is called a **concept-dependent constraint** ([[temp.constr.concept]]):

```cpp title="tt-concept-dependent.cpp" error
template<
    template<typename> concept C,
    template<C> class TT          // error: C forms a concept-dependent constraint
>
struct A {};
```

Matching a template template argument compares constraints for subsumption ([[temp.arg.template#4]]), and until `C` is known, a constraint that depends on it cannot be normalized and so cannot be compared. At the time of writing, Clang 23 accepts the code above without a diagnostic.

## Parameter packs (¶6)

¶6 A template parameter declaration with an ellipsis before its name declares a **template parameter pack** ([[temp.variadic]]), which can correspond to zero or more arguments: `class... Ts`, `int... Ns`, `auto... Vs`, `template<class> class... TTs`, `std::integral... Ts`.

A parameter pack can also be a pack expansion at the same time, i.e. its declaration uses another pack that has not been expanded yet:

```cpp title="pack-expansion-param.cpp" error
template<class... T>
struct value_holder {
    template<T... Values> struct apply {};  // OK: Values expands the outer T
};
value_holder<int, char>::apply<1, 'a'> ok;  // parameters are int, char in order

template<class... T, T... Values>           // error: expands T from the same list
struct static_array;
```

The number and types of `apply`'s parameters are determined by the outer `T`, which is already known in `value_holder<int, char>`. `static_array` is different: `T` and `Values` are in the same list, so determining how many elements `T` has and how many parameters `Values` has depend on each other, and the standard forbids it.

The same rule applies to a template template parameter pack whose parameter list contains an unexpanded pack, and to a type parameter pack whose type constraint contains an unexpanded pack.

## Implementation notes

!!! impl "How constant template arguments get into symbol names"
    The Itanium ABI encodes constant template arguments in the mangled name. Results with Clang 23:
    
    - `fi<42>()` mangles to `_Z2fiILi42EEvv`; the integer is encoded as `Li42E`;
    - the argument in `fd<1.0>()` is encoded as `Ld3ff0000000000000E`, the bit pattern of the double. That is why `0.0` and `-0.0` are different arguments;
    - `addr<A{1}>()` mangles to `_Z4addrIXtl1ALi1EEEEPKS0_v`; a value of class type is encoded member by member, and `tl` stands for brace initialization.
    
    The template parameter object `A{1}` itself is emitted as a read-only constant named `_ZTAXtl1ALi1EEE`, in a mergeable form in each object file, so only one copy remains after linking. This is how the one-object-per-value requirement of ¶13 is implemented.

## History

!!! history
    - C++98 already had type parameters, class template template parameters, and non-type parameters of integral, enumeration, pointer, reference and pointer-to-member type, but function templates could not have default template arguments.
    - C++11 added template parameter packs and allowed default template arguments on function templates.
    - C++17 added `template<auto N>` ([[P0127R2]]).
    - C++20 allowed constant parameters of class type ([[P0732R2]]). That proposal originally required the class to have a defaulted `operator<=>` ([[P1185R2]] changed this to a defaulted `operator==`); later [[P1907R1]] replaced it with today's definition of structural types, which looks only at members and has nothing to do with `==`, and allowed floating-point types. The same version added type constraints.
    - C++26 added variable template template parameters and concept template parameters ([[P2841]]), and renamed non-type template parameters to constant template parameters.

## Common misconceptions

!!! pitfall "C++20 lets you write `template<std::string s>`"
    It doesn't. `std::string` is a literal type in C++20, but its members are private, so it is not a structural type. To pass a string, write a `fixed_string` aggregate with all members public; see [[temp.arg.nontype]].

!!! pitfall "`C... Ts` is the same as `C<Ts...>`"
    `C... Ts` checks each element separately, which is `(C<Ts> && ...)` (¶9).

!!! pitfall "`template<const int N>` and `template<int N>` are different templates"
    Top-level cv-qualifiers are ignored (¶11). `template<int N> void h();` and `template<const int N> void h() {}` are a declaration and a definition of the same function template.

## Questions

!!! question "Question 1"
    Which of these types can be the type of a constant template parameter?

    ```cpp
    struct A { int x; constexpr A(int v) : x(v) {} };              // (a)
    struct B { int x; bool operator==(const B&) const = delete; }; // (b)
    struct C { const int& r; };                                    // (c)
    struct D { int&& r; };                                         // (d)
    struct E { std::array<float, 2> a; };                          // (e)
    ```

<details markdown="1">
<summary>Answer</summary>

- (a) Yes. It is a literal class with public members; a user-written constructor does not affect being structural.
- (b) Yes. Structural types have nothing to do with `operator==`; deleting `==` makes no difference.
- (c) Yes. An lvalue reference is a structural type, but a reference in an argument cannot bind to a temporary ([[temp.arg.nontype#6]]).
- (d) No. An rvalue reference is not a structural type.
- (e) Yes in practice: the members of `std::array` are public in implementations, and `float` is a scalar. The standard itself doesn't guarantee this.
</details>

!!! question "Question 2"
    Given `template<auto... Vs> struct V {};`, is `V<1, 'a', nullptr>` valid? What are the types of the elements of `Vs`?

<details markdown="1">
<summary>Answer</summary>

Yes. Each element of an `auto...` parameter pack has its type deduced separately ([[temp.arg.nontype#1]] invents a declaration `auto x = E;` for each argument): `int`, `char` and `std::nullptr_t`. If all elements must have the same type, write `template<class T, T... Vs>`.
</details>

<details class="fine" markdown="1"><summary>Remaining wording</summary>

¶1 gives the grammar for the five kinds of template parameters: *type-parameter*, *parameter-declaration*, *type-tt-parameter*, *variable-tt-parameter* and *concept-tt-parameter*. A few details: the default argument of a type template template parameter can be written `= N::template X`; a concept template parameter starts directly with `template<...>`, not a general *template-head*, so it cannot have a *requires-clause*.

The component names of a type constraint are its concept name and the names in its qualifying part; other subclauses use this term to specify lookup.

Note 1: the `>` after the parameter list of a template template parameter can come from splitting `>>` ([[temp.names#8]]); for example, the `>>` in `template<template<class = A<int>> class TT>` doesn't need to be written apart.

</details>
