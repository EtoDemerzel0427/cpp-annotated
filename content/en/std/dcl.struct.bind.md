---
title: Structured binding declarations
summary: "auto [x, y] = expr declares only one hidden variable e, and x and y are names for parts of e; e is decomposed in one of three ways: as an array, as tuple-like, or by data members."
updated: 2026-10-19
---

!!! tldr
    - `auto [x, y] = p;` declares only one variable: the unnamed *e*, initialized from `p`. `x` and `y` are names for parts of *e*, neither variables nor references.
    - `auto`, `const`, `&`, `static` and `constexpr` in the declaration all apply to *e*, not to the individual names.
    - *e* tries three ways of decomposition in order: array; tuple-like with `get<i>` when `std::tuple_size<E>` has a `value`; otherwise by non-static data members.
    - `decltype(x)` gives the referenced type; `return x;` doesn't move implicitly, because `x` is not a variable.
    - Since C++26 you can write `constexpr`, put attributes on individual names, use it in an `if` condition, and in templates use binding packs like `[first, ...rest]`.

## The hidden variable *e* (¶1)

```cpp run title="hidden-e.cpp" ok
#include <cassert>

struct P { int x, y; };

int main() {
    P p{1, 2};

    auto [a, b] = p;        // e is a copy of p: P e = p;
    a = 100;
    assert(p.x == 1);       // the original is unchanged

    auto& [c, d] = p;       // e is a reference: P& e = p;
    c = 100;
    assert(p.x == 100);     // p modified through e

    int arr[2] = {3, 4};
    auto [u, v] = arr;      // e is int[2], copied element by element
    u = 0;
    assert(arr[0] == 3);
}
```

`auto [a, b] = p;` looks like it declares two variables initialized from `p.x` and `p.y`. That's not what the standard says.

¶1 A structured binding declaration first introduces a variable *e* with a unique name that can't be written in the program. Its declaration is the original with the bracketed part replaced by *e*, everything else copied: `auto [a, b] = p;` is equivalent to `auto e = p;`, and `auto& [c, d] = p;` to `auto& e = p;`. This declaration is never interpreted as a function declaration, so `auto [a, b](x);` is unambiguous too.

Then each name in the brackets becomes a [[g:structured-binding|structured binding]] that refers to an element or member of *e*. That's why modifying `a` above doesn't affect `p`: it modifies the copy *e*.

Decomposing an array by value is an exception. Arrays can't be copied as a whole, and `auto` deduction would decay an array to a pointer, so when the initializer is an array and there's no `&`, *e* is declared directly with the same array type and initialized element by element.

The type of the id-expression *e* is called E. Note 1 points out that E is never a reference type, because the type of an expression has references removed ([[expr.prop]]): in `auto& [c, d] = p;`, *e* is `P&` and E is `P`.

### Modifiers apply to *e*

¶1 calls the cv-qualifiers in the *decl-specifier-seq* *cv*, and `constexpr`, `constinit`, `static` and `thread_local` *S*. Like `&` and `&&`, they all modify *e*:

```cpp title="const-applies-to-e.cpp" ok
#include <type_traits>

struct S { int& r; int v; };

void f(int& i) {
    const auto [r, v] = S{i, 1};     // const goes on e: const S e = S{i, 1};
    static_assert(std::is_same_v<decltype(v), const int>);   // e.v is const int
    static_assert(std::is_same_v<decltype(r), int&>);        // reference member
    r = 42;                           // OK: const doesn't reach the object the reference refers to
}

int main() { int i = 0; f(i); }
```

`const auto [r, v]` doesn't make `r` const. `r` refers to the reference member `r` of *e*, and the object referred to by a reference member of a const object can still be modified. `volatile` in *cv* is deprecated ([[depr.volatile.type]]).

*e* is an ordinary variable or reference, so the lifetime rules for temporaries ([[class.temporary]]) apply as usual:

```cpp title="lifetime-ext.cpp" error
#include <string>
#include <utility>

std::pair<std::string, int> make();

void f() {
    auto&& [s1, n1] = make();        // OK: e is an rvalue reference; the temporary lives until e's scope ends
    const auto& [s2, n2] = make();   // OK: likewise
    auto& [s3, n3] = make();         // error: a non-const lvalue reference can't bind to a prvalue
}
```

### Which specifiers are allowed ([[dcl.pre#7]])

| Constraint | Content |
|---|---|
| Specifiers | Only `constexpr`, `constinit`, `static`, `thread_local`, `auto`, cv-qualifiers |
| Type | Must be unconstrained `auto`; not `C auto`, `decltype(auto)` or a concrete type |
| Initializer | One of `= expr`, `{ expr }`, `( expr )`, each with a single expression |
| Initializer expression | Array or non-union class type; in a condition, only non-union class type |

```cpp title="sb-specifiers.cpp" error
#include <utility>
template<class T> concept C = true;

void f() {
    auto [a, b] = std::pair{1, 2};               // OK
    static auto [e1, e2] = std::pair{1, 2};      // OK (C++20)
    C auto [g, h] = std::pair{1, 2};             // error: constrained placeholder
    int [i, j] = std::pair{1, 2};                // error: must use auto
    auto [k, l] = {1, 2};                        // error: the initializer can't be a braced list
    auto [m] = 42;                               // error: int is neither an array nor a class
}
```

`auto [k, l]{p};` is allowed: there's only one expression in the braces. `= {1, 2}` isn't, because `=` must be followed by an expression. Clang 23 first deduces *e* as `std::initializer_list<int>` and then reports that it can't bind its private members; the conclusion is the same, the reason differs from the standard's.

## Three ways of decomposition

E determines how *e* is decomposed, trying the following in order:

| Kind | Condition | SB*ᵢ* refers to | Referenced type | Extra variables |
|---|---|---|---|---|
| Array (¶6) | E is an array of known bound | The *i*-th element of *e* | The element type | None |
| Tuple-like (¶7) | `tuple_size<E>` has a member `value` | The object bound by *rᵢ* | `tuple_element<i, E>::type` | *rᵢ* |
| Data members (¶8) | Other class types | The *i*-th member of *e* | The member's declared type (for references) or the type of `e.mᵢ` | None |

Each kind gives E's [[g:structured-binding-size|structured binding size]], the number of bindings to introduce (¶2). Without a binding pack, the number of names in the brackets must equal it exactly. SB*ᵢ* denotes the *i*-th structured binding (¶3).

Each binding also has a [[g:referenced-type|referenced type]]. Unparenthesized `decltype(x)` gives exactly this (item 1.1 of [[dcl.type.decltype#1]]), not the declared type of some variable.

### Arrays (¶6)

¶6 E can't be an array of unknown bound. If E is any other array type, the binding size is the number of elements, and SB*ᵢ* is an lvalue referring to element *i*, whose type and referenced type are both the element type T. Note 3 points out that the top-level cv of T is the *cv* of the declaration.

```cpp title="sb-array.cpp" ok
auto f() -> int(&)[2];

void k() {
    auto [x, y] = f();       // e is int[2], copied element by element from the array f() returns
    auto& [xr, yr] = f();    // e is int(&)[2]; xr and yr refer to the array f returns
    (void)x; (void)y; (void)xr; (void)yr;
}

int main() {}
```

```cpp title="sb-array-unknown.cpp" error
extern int arr[];
void f() {
    auto& [a, b] = arr;   // error: E can't be an array of unknown bound
}
```

### Tuple-like (¶7)

A user-defined class that wants to hide its data members, or to expose computed components, takes this route.

¶7 If E is not an array and `std::tuple_size<E>` is a complete class type with a member named `value`, the tuple-like protocol is used. `tuple_size<E>::value` must be a non-negative integral constant expression, and it is the binding size. If only the primary template is declared, or the specialization has no `value`, this route isn't taken and it falls through to the data member protocol.

The initializer of each element is determined as follows (*i* is an index of type `std::size_t`):

- The name `get` is looked up in the scope of E. If at least one function template is found whose first template parameter is a constant template parameter (non-type template parameter), the initializer is `e.get<i>()`;
- Otherwise the initializer is `get<i>(e)`, where `get` is looked up only by argument-dependent lookup (ADL, [[basic.lookup.argdep]]), not by ordinary unqualified lookup (Note 4).

In both cases `get<i>` is interpreted as a template name, and the `<` is not taken as less-than.

```cpp run title="sb-tuple-like.cpp" ok
#include <cstddef>
#include <tuple>
#include <type_traits>
#include <utility>

namespace lib {
    struct Point {
        int x, y;
        int get() const { return 42; }   // a non-template member get: doesn't count and doesn't block ADL
    };
    template<std::size_t I> int& get(Point& p) { return I == 0 ? p.x : p.y; }
    template<std::size_t I> const int& get(const Point& p) { return I == 0 ? p.x : p.y; }
    template<std::size_t I> int&& get(Point&& p) { return std::move(I == 0 ? p.x : p.y); }
}
template<> struct std::tuple_size<lib::Point> : std::integral_constant<std::size_t, 2> {};
template<std::size_t I> struct std::tuple_element<I, lib::Point> { using type = int; };

int main() {
    lib::Point p{1, 2};
    auto& [a, b] = p;                 // ADL finds lib::get<0>(e), with e an lvalue
    a = 10;
    static_assert(std::is_same_v<decltype(a), int>);   // referenced type int
    return p.x == 10 ? 0 : 1;
}
```

The C++17 rule used the member form as soon as the class had any member named `get`. Many classes already have a `get()` unrelated to tuples, smart pointers for example, and as soon as they wanted to support structured bindings, `e.get<0>()` failed to compile. C++20's [[P0961R1]] changed it to accept only member templates of the form `get<I>`.

!!! lawyer "`template<class T> T get()` doesn't count either"
    A member `get` whose first template parameter is a type parameter (like `std::get<T>`) doesn't satisfy the condition and doesn't block ADL. Conversely, as soon as the class has one member template `get` that satisfies the condition, the member form is used, even if it can't be called for the current *i*; there is no fallback to ADL.

Next, what each element binds to. If the entity *e* has an lvalue reference type, the expression *e* is an lvalue; otherwise it is an xvalue. So `auto [a, b] = t;` calls `get` with an xvalue, and `auto& [a, b] = t;` with an lvalue.

Let T*ᵢ* be `std::tuple_element<i, E>::type`. The standard introduces a set of variables `S Uᵢ rᵢ = initializer;`, where U*ᵢ* is determined by the value category of the initializer: T*ᵢ* for a prvalue, `Tᵢ&` for an lvalue, `Tᵢ&&` for an xvalue. SB*ᵢ* is an lvalue of type T*ᵢ* referring to the object bound by *rᵢ*, with referenced type T*ᵢ*.

Unlike the other two kinds, this one really creates variables *rᵢ*, usually references. When `get` returns a prvalue, *rᵢ* is a separate object, and SB*ᵢ* refers to it rather than to part of *e*. `static`, `constexpr` and so on in *S* also apply to each *rᵢ*. *e* is initialized first, then *r₀*, *r₁*, … in order.

```cpp run title="sb-tuple-ref.cpp" ok
#include <string>
#include <tuple>
#include <type_traits>

int main() {
    int i = 0;
    std::tuple<int&, std::string> t{i, "hi"};
    auto [r, s] = t;      // e is a copy of t, but its element 0 still refers to i
    static_assert(std::is_same_v<decltype(r), int&>);          // T0 = int&
    static_assert(std::is_same_v<decltype(s), std::string>);   // T1 = std::string
    static_assert(std::is_same_v<decltype((s)), std::string&>);
    r = 99;               // modifies i
    return i == 99 ? 0 : 1;
}
```

`decltype(s)` is the referenced type `std::string`, not the type of *r₁*, `std::string&&`. The parenthesized `decltype((s))` is handled as an ordinary lvalue expression and gives `std::string&`.

### Data members (¶8)

¶8 If E is neither an array nor has a usable `tuple_size`, it is decomposed by non-static data members. The conditions are:

1. All non-static data members of E are direct members of E, or all are direct members of the same base class of E;
2. Each member, written `e.name` at the location of the structured binding, is well-formed, i.e. accessible;
3. E has no anonymous union members.

The binding size is the number of non-static data members. Calling the members m₀, m₁, … in declaration order, SB*ᵢ* is an lvalue referring to member m*ᵢ* of *e*, whose type is the type of `e.mᵢ` ([[expr.ref]]), so it combines the cv of *e* with the member's `mutable`. The referenced type is the declared type if the member is declared as a reference, and otherwise the type of `e.mᵢ`. If the member is a bit-field, this lvalue is a bit-field too.

```cpp title="sb-members.cpp" ok
#include <type_traits>

struct S { mutable int x1 : 2; volatile double y1; };
S f();

void g() {
    const auto [x, y] = f();
    static_assert(std::is_same_v<decltype(x), int>);                    // mutable cancels the const
    static_assert(std::is_same_v<decltype(y), const volatile double>);
}

int main() {}
```

```cpp title="sb-members-errors.cpp" error
struct B { int a; };
struct D : B { int b; };
struct OnlyBase : B { };
class Priv { int x; public: int y; friend void friend_ok(); };
struct Anon { union { int u; float f; }; int v; };
union U { int i; };

void f() {
    auto [a1] = OnlyBase{};    // OK: all members come from the same base B
    auto [a2, b2] = D{};       // error: members are spread across D and B
    auto [x, y] = Priv{};      // error: x is inaccessible here
    auto [u, v] = Anon{};      // error: has an anonymous union member
    auto [i] = U{};            // error: unions can't be decomposed ([dcl.pre]/7)
}

void friend_ok() {
    auto [x, y] = Priv{};      // OK: x is accessible in a friend
}
```

The members must all be in one class because only then does numbering them in declaration order have a clear meaning. When members are spread across a base class and a derived class, which one is number 0 would depend on some layout convention, and the standard specifies none. The accessibility requirement was relaxed by C++20's [[P0969R0]]; C++17 required all members to be public.

## Structured bindings are not variables

[[basic.pre#8]] lists structured bindings as a kind of entity alongside variables. This makes a visible difference in several places:

| Situation | Ordinary variable | Structured binding |
|---|---|---|
| `decltype(x)` | Declared type | Referenced type |
| Implicit move in `return x;` | Yes (non-volatile object with automatic storage duration) | No; it is not an [[expr.prim.id.unqual#15\|implicitly movable entity]] |
| Lambda capture | Allowed | Allowed since C++20 ([[P1091R3]], [[P1381R1]]) |
| Taking the address, binding a reference | Allowed | Allowed, except when bound to a bit-field |

```cpp title="sb-no-implicit-move.cpp" error
#include <memory>

struct H { std::unique_ptr<int> p; int n; };
H make();

std::unique_ptr<int> f() {
    auto [p, n] = make();
    return p;               // error: no implicit move, tries to copy the unique_ptr
}

std::unique_ptr<int> g() {
    auto [p, n] = make();
    return std::move(p);    // OK
}
```

The bit-field case comes from the same model. If the standard defined a binding as `auto& x = e.x1;`, a bit-field couldn't be bound at all; as it is, the binding name is itself a bit-field lvalue that can be read and written normally, except that its address can't be taken and it can't be bound to a non-const reference.

Capturing a bit-field by reference in a lambda is ill-formed ([[expr.prim.lambda.capture]]), and this applies to structured bindings too:

```cpp title="sb-capture.cpp" error
struct S { int bf : 3; int v; };

int main() {
    auto [bf, v] = S{1, 2};
    auto l1 = [bf, &v] { return bf + v; };   // OK (C++20)
    auto l2 = [&bf] { return bf; };          // error: a bit-field can't be captured by reference
    return l1() + l2();
}
```

!!! impl "Clang's deviation"
    Clang 23's diagnostic for `[&bf]` above is "non-const reference cannot bind to bit-field". If the declaration is changed to `const auto [bf, v]`, Clang 23 accepts `[&bf]`. The standard's rule doesn't distinguish const: capturing a bit-field by reference is always ill-formed.

## The initializer can't use the names it introduces (¶5)

¶5 If the initializer refers to a name introduced by this declaration, the program is ill-formed.

```cpp title="sb-self-ref.cpp" error
struct P { int x, y; };
void f() {
    auto [a, b] = (a, P{});   // error: a used in the initializer
}
```

For an ordinary variable the point of declaration is after the declarator, so `int x = x;` compiles ([[basic.scope.pdecl]]). A structured binding refers to part of *e*, and *e* only exists after the initializer has been evaluated, so using it in the initializer has no sensible meaning and is forbidden outright.

## Structured binding packs (¶1–¶3) {{c++26}}

```cpp run title="sb-pack.cpp" ok
#include <tuple>
#include <cstdio>

template<class Tuple>
auto sum(const Tuple& t) {
    const auto& [...xs] = t;          // xs is a structured binding pack
    return (0 + ... + xs);
}

template<class T>
void print_all(const T& agg) {
    const auto& [first, ...rest] = agg;
    std::printf("first=%d, rest has %zu elements\n", first, sizeof...(rest));
}

struct Triple { int a, b, c; };

int main() {
    std::printf("%d\n", sum(std::tuple{1, 2, 3}));   // 6
    print_all(Triple{1, 2, 3});                       // first=1, rest has 2 elements
}
```

¶1 A name preceded by `...` introduces a [[g:structured-binding-pack|structured binding pack]] ([[temp.variadic#4]]), each element of which is a structured binding. Like a function parameter pack, it can be expanded, counted with `sizeof...`, and used in fold expressions.

¶2 With a binding pack, the number of other names can't exceed the binding size, and the rest all go into the pack, which may be empty. The pack can appear in any position (the standard example in ¶3):

```cpp title="sb-pack-positions.cpp" ok
struct C { int x, y, z; };

template<class T>
void now_i_know_my() {
    auto [a, b, c] = C();          // SB0=a, SB1=b, SB2=c
    auto [d, ...e] = C();          // pack e contains SB1, SB2
    auto [...f, g] = C();          // pack f contains SB0, SB1; g is SB2
    auto [h, i, j, ...k] = C();    // k is an empty pack
    // auto [l, m, n, o, ...p] = C();   // error: structured binding size too small
}

int main() { now_i_know_my<int>(); }
```

[[dcl.pre#7]] says a declaration can have at most one pack, and a declaration containing a pack must declare a [[g:templated-entity|templated entity]], i.e. it can only appear in a templated context such as a template or generic lambda. The whole pack expansion machinery rests on the number of elements being determined at instantiation; supporting it in non-template code would be a heavy burden on implementations, so the proposal narrowed its scope as it evolved.

```cpp title="sb-pack-nontemplate.cpp" error
struct P { int x, y; };
void f() {
    auto [...xs] = P{};   // error: a declaration with a binding pack must be a templated entity
}
```

Clang 23 reports "pack declaration outside of template" for this.

## In a condition (¶4) {{c++26}}

¶4 When a structured binding declaration is the condition of an `if`, `while` or `switch`, the condition's [[g:decision-variable|decision variable]] is *e* ([[stmt.pre]]). `if (auto [a, b] = expr)` tests the result of contextually converting *e* to `bool`, not the value of some binding.

```cpp run title="sb-condition.cpp" ok
#include <cstddef>
#include <cstdio>
#include <utility>

struct Parsed {
    int value;
    bool ok;
    explicit operator bool() const { std::puts("operator bool"); return ok; }
    template<std::size_t I> auto get() const {
        std::printf("get<%zu>\n", I);
        if constexpr (I == 0) return value; else return ok;
    }
};
template<> struct std::tuple_size<Parsed> { static constexpr std::size_t value = 2; };
template<> struct std::tuple_element<0, Parsed> { using type = int; };
template<> struct std::tuple_element<1, Parsed> { using type = bool; };

Parsed parse(const char*) { return {42, true}; }

int main() {
    if (auto [v, ok] = parse("42"))      // tests e, calling operator bool
        std::printf("v=%d ok=%d\n", v, ok);
}
// output: operator bool / get<0> / get<1> / v=42 ok=1
```

The order of the output is guaranteed by the end of ¶7: the initialization of *e* and the conversion of *e* as a decision variable are both sequenced before the initialization of any *rᵢ*. Types like `expected` can often only safely yield their components on success; testing first and decomposing afterwards means `get` is never called in the failure state. The initializer expression in a condition can only be of non-union class type; arrays can't be converted to `bool`.

## static, constexpr and attributes

### static and thread_local

Since C++20, `static` and `thread_local` apply to *e* and to each *rᵢ* under the tuple-like protocol. Only *e* is an object, so `static auto [a, b] = ...;` creates just one static object, initialized once:

```cpp run title="sb-static.cpp" ok
#include <cstdio>
#include <utility>

std::pair<int, int> next() {
    static int n = 0;
    ++n;
    return {n, n * 10};
}

void f() {
    static auto [a, b] = next();   // initialized only on the first call to f
    std::printf("%d %d\n", a, b);
}

int main() { f(); f(); }   // prints 1 10 both times
```

### constexpr and constinit {{c++26}}

Since C++26 ([[P2686R5]]), `constexpr` and `constinit` likewise apply to *e* and each *rᵢ*, so *e* must be constant-initialized and the bindings can then be used in constant expressions. Previously you had to write `constexpr auto t = ...;` first and take the parts one by one.

```cpp title="sb-constexpr.cpp" ok
#include <array>
#include <utility>

constexpr auto [a, b] = std::pair{1, 2.5};
static_assert(a == 1 && b == 2.5);

constinit auto [c, d] = std::pair{3, 4};

constexpr std::array<int, 3> arr{1, 2, 3};
constexpr auto& [x, y, z] = arr;
static_assert(y == 2);

struct P { int x, y; };
void f() {
    constexpr auto [p, q] = P{1, 2};            // data member protocol: the names refer directly to members of e
    static_assert(p + q == 3);
}

int main() {}
```

!!! impl "Tuple-like decomposition at block scope"
    Writing `constexpr auto [p, q] = std::pair{1, 2};` in a function, the tuple-like protocol introduces references like `constexpr int&& r0 = get<0>(std::move(e));` that refer to an object with automatic storage duration. The same proposal changed the rules for references in constant expressions: an automatic object that is constexpr-referenceable from the current point ([[expr.const.init#2]], roughly within the same function invocation) can be referred to by the result of a constant expression. So under the current draft this is well-formed.

    Clang 23 rejects it with "address of non-static constexpr variable may differ on each invocation" and suggests adding `static`; changing it to `static constexpr` compiles. The array and data member protocols introduce no references, and Clang accepts them.

### Attributes {{c++26}}

Since C++26 ([[P0609R3]]), each name can be followed by an attribute list that appertains only to that binding. The most common use is marking only the unused name `[[maybe_unused]]`:

```cpp title="sb-attr.cpp" ok
#include <map>
#include <string>

int count_values(const std::map<std::string, int>& m) {
    int total = 0;
    for (const auto& [key [[maybe_unused]], value] : m)
        total += value;
    return total;
}

int main() {}
```

Previously `[[maybe_unused]]` could only be put on the whole declaration ([[dcl.attr.unused#2]]), suppressing warnings for all names at once. [[dcl.attr.unused#4]] also recommends warning about an unmarked structured binding declaration only when none of its bindings is used. C++26's placeholder name `_` can also be repeated within one structured binding declaration: `auto [_, value, _] = triple;` ([[basic.scope.scope]]).

## Interaction with other features

- Range-`for`: `for (auto& [k, v] : m)` initializes a new *e* from `*__begin` on every iteration ([[stmt.ranged]]).
- Expansion statements {{c++26}}: when `template for` expands by destructuring, it uses the same structured binding size and decomposition ([[stmt.expand]]).
- The standard library's `std::pair`, `std::tuple`, `std::array`, `std::ranges::subrange`, and since C++26 `std::complex`, all provide `tuple_size`, `tuple_element` and `get`.

!!! impl "*e* in object code"
    - *e* is a real object or reference. In the Itanium C++ ABI, an *e* at namespace scope needs a linkage name, which starts with `_ZDC` followed by the binding names: for a global `auto [ga, gb] = ...;`, Clang 23 generates `_ZDC2ga2gbE`. DC comes from the proposal-era name "decomposition declaration".
    - Under the data member protocol, binding names are just aliases for members of *e* and take no extra storage; in a debugger you can usually see *e* (shown with a synthesized name) and the individual bindings.
    - Under the tuple-like protocol, *rᵢ* are real reference variables, which after optimization are no different from calling `get` directly.

## History

!!! history
    - C++17 introduced structured bindings ([[P0217R3]]). Initially only `auto`, cv and references were allowed; data members all had to be public; no `static`, `thread_local` or `constexpr`; they couldn't be captured by lambdas; and any member named `get` in the class triggered the member form.
    - C++20 fixed the lookup of `get` ([[P0961R1]]), required data members only to be accessible ([[P0969R0]]), and allowed `static`, `thread_local` and lambda capture ([[P1091R3]], [[P1381R1]]).
    - C++26 allows attributes on individual bindings ([[P0609R3]]), use in conditions ([[P0963R3]]), binding packs ([[P1061R10]]), and `constexpr` ([[P2686R5]]). With `-std=c++2c`, Clang 23's `__cpp_structured_bindings` is `202411L`.

## Common misconceptions

!!! pitfall "`const auto& [a, b]` guarantees a and b can't be modified"
    cv and references modify *e*. When a member is itself a reference (data member protocol), or `tuple_element` is a reference type (as in `std::tuple<int&>`), you can still write to the outside object through the binding.

!!! pitfall "Decomposing a tuple by value moves the components out"
    In `auto [s] = std::tuple<std::string>{...};`, *e* is an object, `get` is called with an xvalue and yields `std::string&&`, and *r₀* is an rvalue reference. It refers to the string inside *e*; no move happens at all. Components are only really moved out when your own `get(T&&)` returns a prvalue and move-constructs a new object inside.

!!! pitfall "`return x;` moves like an ordinary local variable"
    A structured binding is not a variable and isn't implicitly moved. To move, write `return std::move(x);`, or use an ordinary variable instead.

## Questions

!!! question "Question 1"
    What does the following program print?

    ```cpp
    #include <cstdio>
    struct P { int x, y; };
    int main() {
        P p{1, 2};
        auto [a, b] = p;
        auto& [c, d] = p;
        a = 10; c = 20;
        std::printf("%d %d %d\n", p.x, a, c);
    }
    ```

<details markdown="1">
<summary>Answer</summary>

It prints `20 10 20`. In the first declaration, *e* is a copy of `p` and `a` refers to the copy's `x`; in the second, *e* is `P&` and `c` refers to `p.x` itself. So `a = 10` only changes the copy, while `c = 20` changes `p.x`.
</details>

!!! question "Question 2"
    Class `Handle` has a member function `int* get() const;`, and its author has also specialized `std::tuple_size` and `std::tuple_element` for it and provided a free function template `template<std::size_t I> auto get(const Handle&)` in the same namespace. What happens with `auto [a, b] = h;` in C++17 and in C++20?

<details markdown="1">
<summary>Answer</summary>

In C++17, a member named `get` is found in `Handle`, so `e.get<i>()` is used; but the member `get` is not a template, so `e.get<0>()` is ill-formed. Since C++20 (¶7), the member form is used only if a member function template whose first template parameter is a constant template parameter is found; `int* get() const` is not a template, so `get<i>(e)` is used instead and ADL finds the free function template: well-formed.
</details>

!!! question "Question 3"
    After `struct S { int a; }; const S s{1};`, is `auto& [x] = s; x = 2;` well-formed? What about `auto [y] = s; y = 2;`?

<details markdown="1">
<summary>Answer</summary>

In `auto& [x] = s;`, *e* is deduced as `const S&`, `x` refers to `e.a` with type `const int`, so `x = 2` is ill-formed. In `auto [y] = s;`, `auto` deduction drops the top-level const, *e* is a non-const copy of type `S`, `y` has type `int`, and `y = 2` is well-formed, modifying the copy.
</details>
