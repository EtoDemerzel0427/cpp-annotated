---
title: List-initialization
summary: "How brace initialization chooses what to do: the twelve-step decision of ¶3, why initializer-list constructors always win, the type and lifetime of the backing array, the full definition of narrowing conversions, and the special rules for auto and CTAD with braces."
updated: 2026-10-19
---

!!! tldr
    - Brace initialization chooses what to do in the fixed order of ¶3: aggregates get aggregate initialization, an empty list prefers the default constructor, a non-empty list tries initializer-list constructors first, and scalars get single-element initialization.
    - As long as an initializer-list constructor is viable, it wins, so `std::vector<int>{10, 20}` has two elements while `std::vector<int>(10, 20)` has ten 20s.
    - Narrowing conversions (such as `double` → `int`, non-constant `int` → `char`, pointer → `bool`) are compile errors at the top level of list-initialization; they don't make a candidate non-viable, but cause an error after it is selected.
    - A `std::initializer_list` refers to a backing array of type `const E[N]` whose lifetime is like that of a temporary bound to a reference; don't store or return it.
    - The clauses in braces are evaluated strictly left to right; `auto x{1}` deduces `int`, and `auto x = {1}` deduces `std::initializer_list<int>`.

## Same braces, different actions

```cpp run ok
#include <vector>
#include <cstdio>
struct P { int x, y; };
int main() {
  std::vector<int> a{10, 20};   // 2 elements: 10, 20
  std::vector<int> b(10, 20);   // 10 elements, each 20
  P p{1, 2};                    // aggregate initialization
  int i{};                      // value-initialization: 0
  std::printf("%zu %zu %d %d\n", a.size(), b.size(), p.y, i);   // 2 10 2 0
}
```

C++11 brace initialization aimed to be usable everywhere, to forbid narrowing, and to avoid object definitions being misparsed as function declarations. But the same pair of braces does entirely different things for aggregates, for classes with `std::initializer_list` constructors, and for scalars. The decision order of ¶3 determines which path each case takes. When [[dcl.init]] meets a braced initializer, its ¶15.1 hands control straight over to here.

## Terminology (¶1)

¶1 Initialization of an object or reference from a braced list (*braced-init-list*) is called **list-initialization**. Such an initializer is called an **initializer list**, and its comma-separated clauses (or designated clauses) are called its **elements**. The list may be empty.

List-initialization can occur in direct-initialization or copy-initialization contexts ([[dcl.init#13]], [[dcl.init#14]]):

| Name | Examples |
|---|---|
| **direct-list-initialization** | `T x{a};`, `new T{a}`, `T{a}`, `: m{a}` |
| **copy-list-initialization** | `T x = {a};`, `f({a})`, `return {a};`, `{a}` in an aggregate element |
| **direct-non-list-initialization** | Direct-initialization that is not list-initialization: `T x(a);` |

Note 1 lists where list-initialization can appear: variable initializers, *new-expression*s, `return`, range-`for` initializers, function arguments, template arguments, subscripts `a[{1, 2}]`, constructor call arguments, default member initializers, *mem-initializer*s, and the right-hand side of assignment.

```cpp
int a = {1};
std::complex<double> z{1, 2};
new std::vector<std::string>{"once", "upon", "a", "time"};  // 4 strings
f({"Nicholas", "Annemarie"});         // passes a two-element list
return {"Norah"};                     // returns a one-element list
int* e{};                             // null pointer
x = double{1};                        // explicitly constructs a double
std::map<std::string, int> anim = {{"bear", 4}, {"cassowary", 2}, {"tiger", 7}};
```

## Initializer-list constructors (¶2)

¶2 A constructor is an **initializer-list constructor** ([[g:initializer-list-constructor]]) if its first parameter is of type `std::initializer_list<E>` or `cv std::initializer_list<E>&` and any other parameters have default arguments. Note 2 points out that list-initialization favors such constructors ([[over.match.list]]).

A constructor template `template<class T> C(T)` is not an initializer-list constructor: a braced-list argument makes the corresponding parameter a non-deduced context ([[temp.deduct.call]]), so `T` is never deduced as `initializer_list<...>`.

`std::initializer_list` is not a built-in type of the language. Wherever it is used, even implicitly without spelling the type name as in `auto x = {1, 2};`, the program is ill-formed if the declaration from `<initializer_list>` (or one provided by `import std;`) is not reachable.

## The decision order (¶3)

¶3 List-initialization of an object or reference of type *cv* `T` checks the following in order, and the first condition that holds determines the action:

| Step | Condition | Action |
|---|---|---|
| ¶3.1 | Has designated initializers, `T` is not a reference | `T` must be an aggregate class; aggregate initialization |
| ¶3.2 | `T` is an aggregate class, the list has one element of type `T` or a class derived from it | Initialize from that element (copy or move) |
| ¶3.3 | `T` is a character array, the list has a single string literal | Initialize per [[dcl.init.string]] |
| ¶3.4 | `T` is an aggregate | Aggregate initialization ([[dcl.init.aggr]]) |
| ¶3.5 | The list is empty, `T` is a class with a default constructor | Value-initialization |
| ¶3.6 | `T` is `std::initializer_list<E>` | Construct a backing array (¶5) |
| ¶3.7 | `T` is a class | Constructor overload resolution ([[over.match.list]]); ill-formed if narrowing |
| ¶3.8 | `T` is an enumeration with a fixed underlying type, a single scalar element, direct-list-initialization | `T(v)`; ill-formed if narrowing |
| ¶3.9 | A single element, and `T` is not a reference or its referenced type is reference-related to the element's type | Initialize from that element; ill-formed if narrowing |
| ¶3.10 | `T` is a reference | Generate a prvalue, then initialize the reference with it |
| ¶3.11 | The list is empty | Value-initialization |
| ¶3.12 | Otherwise | Ill-formed |

The order itself is the rule. ¶3.4 comes before ¶3.7, so aggregates never go through constructor overload resolution; ¶3.5 comes before ¶3.7, so `T{}` calls the default constructor rather than an initializer-list constructor with an empty list; ¶3.9 comes after ¶3.7, so a single-element list for a class type also looks for constructors first.

### Designated initializers (¶3.1) {{c++20}}

```cpp error
struct A { int x; int y; int z; };
A a{.y = 2, .x = 1};   // error: order doesn't match declaration order
A b{.x = 1, .z = 2};   // OK: b.y is initialized to 0
```

¶3.1 If the braced list contains a *designated-initializer-list* and `T` is not a reference, `T` must be an aggregate class; the associated elements ([[dcl.init.aggr#3]]) of the members named by the designators must be in non-decreasing element order; then aggregate initialization is performed. Clang 23 only gives a `-Wreorder-init-list` warning for `a` (an extension inherited from C); by the standard it is ill-formed, and the warning satisfies the diagnostic requirement.

The current draft also allows designating members of base classes {{c++29}}, a change after C++26 ([[diff.cpp26]] records an incompatibility it introduces). Requiring non-decreasing rather than strictly increasing order is exactly because several designators can correspond to the same associated element: in the example below, `.x` and `.y` both belong to the base class `A`.

```cpp
struct B : A { int q; };
B e{.x = 1, .q = 3};   // OK: e.y and e.z are 0
B f{.q = 3, .x = 1};   // error: order

struct C { int p; int x; };
struct D : A, C { };
D g{.y = 1, .p = 2};   // OK
D h{.x = 2};           // error: lookup of x is ambiguous

struct NonAggr { int na; NonAggr(int); };
struct E : NonAggr { int e; };
E i{.na = 1, .e = 2};  // error: na belongs to NonAggr, which is not an aggregate base of E
```

As of writing, Clang 23 doesn't support designating base class members, so this code is analyzed from the draft text. The other restrictions on designated initializers (no nesting `.a.b`, not for arrays, no mixing with ordinary clauses) are in [[dcl.init.aggr]].

### Aggregates: same-type copy, strings, aggregate initialization (¶3.2–¶3.4)

```cpp run ok
struct S { int x; };
struct D : S { int y; };
int main() {
  S a{1};
  S b{a};          // ¶3.2: copy, b.x == 1
  D d{{1}, 2};
  S c{d};          // ¶3.2: copy from a derived class (slicing)
  char s[] = {"abc"};   // ¶3.3: same as char s[] = "abc";
  (void)b; (void)c; (void)s;
}
```

¶3.2 If `T` is an aggregate class and the list has a single element of type *cv1* `U`, where `U` is `T` or a class derived from `T`, the object is initialized directly from that element: by copy-initialization for copy-list-initialization, and by direct-initialization for direct-list-initialization.

Without this step, `S b{a};` would go to aggregate initialization and use `a` to initialize `b.x`, and there is no conversion from `S` to `int`. The original C++11 rules really had this problem; ¶3.2 was added later through the resolution of a core issue.

¶3.3 If `T` is a character array and the list has a single string literal of a suitable type, it is initialized per [[dcl.init.string]]. Without this step, ¶3.4 would treat `"abc"` as the initializer of the first `char` element.

¶3.4 If `T` is an aggregate (an array or aggregate class), aggregate initialization is performed ([[dcl.init.aggr]]). If an element's initializer is itself a braced list, that element is list-initialized recursively. Narrowing on aggregate elements is an error too:

```cpp error
double ad[] = { 1, 2.0 };     // OK
int ai[] = { 1, 2.0 };        // error: narrowing

struct S2 { int m1; double m2, m3; };
S2 s21 = { 1, 2, 3.0 };       // OK
S2 s22 { 1.0, 2, 3 };         // error: narrowing
S2 s23 { };                   // OK: all 0
```

!!! lawyer "Where narrowing of aggregate elements comes from"
    C++23's [dcl.init.aggr] stated explicitly that if an element's initializer is an expression and a narrowing conversion is required, the program is ill-formed. After the current draft rewrote aggregate initialization in terms of clauses that appertain to elements, that sentence can't be found in [[dcl.init.aggr#5.3]]; only the one in [[dcl.init.aggr#5.2.1]] for designated initializers remains. The standard's own Example 3 and all implementations still treat `ai` and `s22` as ill-formed, and nothing suggests the intent has changed.

### An empty list calls the default constructor (¶3.5)

```cpp run ok
#include <initializer_list>
#include <cstdio>
struct U {
  U(std::initializer_list<int>) { std::puts("#1"); }
  U() { std::puts("#2"); }
};
int main() {
  U u1{};      // ¶3.5: #2
  U u2{{}};    // ¶3.7: #1, the list has one element (an int with value 0)
  U u3({});    // not list-initialization: #1, an empty initializer_list
}
```

¶3.5 If the list is empty and `T` is a class with a default constructor, the object is value-initialized ([[dcl.init#8]]). This stops initializer-list constructors from hijacking `T{}`.

`u3` is not list-initialization but ordinary constructor overload resolution with `{}` as the argument. `{}` to `initializer_list<int>` is an identity conversion, while `U`'s copy or move constructor would need a user-defined conversion, so #1 is selected.

### `std::initializer_list` itself (¶3.6)

¶3.6 If `T` is a specialization of `std::initializer_list<E>`, a backing array is constructed per ¶5, as in `std::initializer_list<int> il = {1, 2, 3};` or the argument of an initializer-list constructor.

### Constructors: two-phase overload resolution (¶3.7)

¶3.7 If `T` is a class type (not an aggregate, and the list is non-empty or there is no default constructor), constructor overload resolution is performed per [[over.match.list]]. If any argument requires a narrowing conversion, the program is ill-formed. [[over.match.list]] has two phases:

1. If the list is non-empty or `T` has no default constructor, the candidates are only the initializer-list constructors, with the whole list as the single argument.
2. If the first phase finds no viable function, the candidates are all constructors, with the elements of the list as separate arguments.

```cpp error
#include <vector>
#include <string>
std::vector<int> v1{10, 20};       // first phase viable: 2 elements
std::vector<int> v2(10, 20);       // not a list: ten 20s
std::vector<std::string> v3{3};    // int → string not viable, second phase: 3 empty strings
std::vector<int> v4{3.0};          // error: selected in the first phase, then narrowing is found
```

`v4` is the most counterintuitive. Narrowing doesn't make a conversion non-viable ([[over.ics.list]]); it only makes the program ill-formed after selection, so it doesn't fall back to `vector(size_type)`. This is by design: if narrowing merely made a candidate non-viable, `v4` would silently select a constructor with a completely different meaning.

As long as an initializer-list constructor is viable, it blocks even the copy constructor. Example 4 in the standard:

```cpp
struct S {
  S(std::initializer_list<double>);   // #1
  S(std::initializer_list<int>);      // #2
  S(std::initializer_list<S>);        // #3
  S();                                // #4
};
S s1 = { 1.0, 2.0, 3.0 };             // #1
S s2 = { 1, 2, 3 };                   // #2
S s3{s2};                             // #3, not the copy constructor
S s4 = { };                           // #4 (¶3.5)
```

`S` is not an aggregate, so ¶3.2 doesn't apply; in the first phase, constructing an `initializer_list<S>` by copy-initializing an `S` element from `s2` is viable, so #3 is selected. So adding an `initializer_list<T>` constructor to a class, where `T` can be converted from that class, changes every copy of the form `X{x}`.

Without initializer-list constructors, ¶3.7 is ordinary constructor overload resolution plus a narrowing check. Copy-list-initialization has one more peculiarity:

```cpp error
struct S { explicit S(int); S(long); };
S s1 = {1};     // error: selected explicit S(int)
S s2 = 1;       // OK: copy-initialization doesn't consider explicit, so S(long) is chosen
S s3{1};        // OK: direct-list-initialization
```

In [[g:copy-list-initialization|copy-list-initialization]], explicit constructors participate in overload resolution, and if one is selected the program is ill-formed ([[over.match.list]]); ordinary copy-initialization doesn't consider them at all. This way, adding `explicit` to a constructor doesn't make `= {...}` silently switch to a different overload.

### Enumerations with a fixed underlying type (¶3.8) {{c++17}}

```cpp error
#include <cstdint>
enum byte : unsigned char { };
byte b { 42 };              // OK
byte c = { 42 };            // error: copy-list-initialization
byte d = byte{ 42 };        // OK: same value as b
byte e { -1 };              // error: narrowing

struct A { byte b; };
A a1 = { { 42 } };          // error: aggregate elements are copy-initialized
A a2 = { byte{ 42 } };      // OK

void f(byte);
void g() { f({ 42 }); }     // error: argument passing is copy-initialization

enum class Handle : std::uint32_t { Invalid = 0 };
Handle h { 42 };            // OK
```

¶3.8 If `T` is an enumeration with a fixed underlying type `U` (`enum class E` or `enum E : U`), the list has a single scalar element `v` that can be implicitly converted to `U`, and it is direct-list-initialization, the object's value is `T(v)`. If converting `v` to `U` requires narrowing, the program is ill-formed.

[[P0138R2]] added this rule so that strongly typed integers like `std::byte` can be written `byte b{42};` without a `static_cast`. There is no implicit conversion from integers to enumerations, and allowing only direct-list-initialization ensures that implicit contexts like `f({42})` and `return {42};` still can't turn an integer into an enumeration.

### A single element (¶3.9)

```cpp error
int x1 {2};          // OK
int x2 {2.0};        // error: narrowing
int i = 0;
int& r {i};          // the referenced type int is reference-related to int: binds to i
const long& rl {i};  // not reference-related: handed to ¶3.10
```

¶3.9 If the list is not a designated list and has a single element of type `E`, and either `T` is not a reference or its referenced type is [[g:reference-related|reference-related]] to `E`, the object is initialized from that element (by copy or direct, depending on context); if narrowing is required, it is ill-formed. This is the most common step for scalars. Requiring reference-relatedness for references guarantees that `int& r{i};` really binds to `i`.

### References (¶3.10)

```cpp
struct S {
  S(std::initializer_list<double>);   // #1
  S(const std::string&);              // #2
};
const S& r1 = { 1, 2, 3.0 };          // OK: #1
const S& r2 { "Spinach" };            // OK: #2
S& r3 = { 1, 2, 3 };                  // error: a prvalue can't bind to a non-const lvalue reference
const int& i1 = { 1 };                // OK (¶3.9)
const int& i2 = { 1.1 };              // error: narrowing
const int (&iar)[2] = { 1, 2 };       // OK: binds to a temporary array
const int (&iau)[] = { 1, 2, 3 };     // OK: the temporary array has type const int[3]

struct A { } a;
struct B { explicit B(const A&); };
const B& b2{a};                       // error: can't copy-list-initialize a B temporary from A

struct C { int x; };
C&& c = { .x = 1 };                   // OK
```

¶3.10 If `T` is a reference (and ¶3.9 doesn't apply), a prvalue is generated whose result object is copy-list-initialized from the list, and the reference is then direct-initialized from that prvalue ([[dcl.init.ref]]). The prvalue's type is the referenced type; if `T` is "reference to array of unknown bound of `U`", the prvalue's type is the type of `x` in the declaration `U x[] H` (where `H` is the list), i.e. the bound is deduced from the list.

`const B& b2{a};` as a whole is direct-list-initialization, but the prvalue generated by ¶3.10 is copy-list-initialized, so the explicit constructor can't be used.

!!! impl
    Clang 23 accepts `const B& b2{a};` and only reports chosen constructor is explicit in copy-initialization for `const B& b3 = {a};`. By the standard both are ill-formed.

### Empty lists and everything else (¶3.11–¶3.12)

¶3.11 If the list is empty, the object is value-initialized. Class types have all been handled earlier, so what reaches here are non-class types such as scalars: `int** pp{};` is a null pointer, and `int k{};` is 0.

¶3.12 Everything else is ill-formed, for example `int x{1, 2};`.

## Braces guarantee left-to-right evaluation (¶4)

```cpp run ok
#include <iostream>
struct I { I(int x) { std::cout << x; } };
struct S { S(I, I = 2) {} };
int main() {
  S(1, 2); std::cout << '\n';   // order unspecified: prints 12 or 21
  S{1, 2}; std::cout << '\n';   // always prints 12
  S{1};                         // always prints 12: default arguments are evaluated in their position
}
```

¶4 The clauses in a braced list, including those produced by pack expansions, are evaluated in the order they appear: every value computation and side effect of one clause is sequenced before the next. If the clauses are used as constructor arguments, any default arguments used are also evaluated in order, in the positions they would have occupied.

Note 4 stresses that this order holds regardless of the semantics of the initialization. Even when the elements end up as constructor arguments (and the arguments of an ordinary function call are unsequenced relative to each other), braces guarantee left to right. So `T{f(), g()}` is one of the few forms that guarantees evaluation order, and before C++17 `(void)std::initializer_list<int>{(process(args), 0)...};` was commonly used to sequence side effects in a pack expansion.

## `std::initializer_list` and the backing array (¶5–¶6)

¶5 When a `std::initializer_list<E>` object is constructed from an initializer list, it is as if the implementation generated and materialized a prvalue of type "array of `N` `const E`", where `N` is the number of elements. This array is called the **backing array**. Each element of the array is copy-initialized from the corresponding element of the list, and the `initializer_list` object refers to this array. Three consequences follow:

1. The elements are `const` and can't be moved from. `std::vector<std::unique_ptr<int>> v{std::make_unique<int>(1)};` is ill-formed: `vector`'s initializer-list constructor can only copy the elements, and `unique_ptr` is not copyable.
2. The elements are copy-initialized, so explicit constructors can't be used; the selected constructor or conversion function must be accessible in the context of the list (Note 5).
3. If narrowing is required, the program is ill-formed.

Note 6 {{c++26}} explains that the backing array is a **potentially non-unique object** ([[intro.object]]), like a string literal. This comes from [[P2752R3]]: when all elements are constants, the implementation can put the array in static read-only storage and share it with other arrays of the same contents, instead of constructing it on the stack every time. In C++23 and earlier, every evaluation had to produce a distinct array object, which got in the way of this optimization.

¶6 The backing array has the same lifetime as other temporaries ([[class.temporary]]), except that when it is used to initialize an `initializer_list` object, the array's lifetime is extended just as when a reference binds to a temporary. Example 13 in the standard:

```cpp
void f(std::initializer_list<double> il);
void g(float x) { f({1, x, 3}); }
void h() { f({1, 2, 3}); }

struct A { mutable int i; };
void q(std::initializer_list<A>);
void r() { q({A{1}, A{2}, A{3}}); }
```

The implementation is roughly equivalent to:

```cpp
void g(float x) {
  const double __a[3] = {double{1}, double{x}, double{3}};             // backing array
  f(std::initializer_list<double>(__a, __a + 3));
}
void h() {
  static constexpr double __b[3] = {double{1}, double{2}, double{3}};  // can be static
  f(std::initializer_list<double>(__b, __b + 3));
}
void r() {
  const A __c[3] = {A{1}, A{2}, A{3}};   // has a mutable member, so it can't go in read-only storage
  q(std::initializer_list<A>(__c, __c + 3));
}
```

This assumes the implementation can construct an `initializer_list` from a pair of pointers. Even though `__b` is static, by the standard its lifetime doesn't extend beyond the call to `f`.

Example 14 in the standard shows several lifetimes:

```cpp
std::vector<std::complex<double>> v1 = { 1, 2, 3 };  // the initializer_list is a function argument: the array lives until the end of the full-expression
void f() {
  std::initializer_list<int> i3 = { 1, 2, 3 };      // the initializer_list is a variable: the array lives as long as i3
}
struct A {
  std::initializer_list<int> i4;
  A() : i4{ 1, 2, 3 } {}   // error: equivalent to binding a temporary array to a reference member
};
```

Returning an `initializer_list` isn't diagnosed as ill-formed, but it always dangles:

```cpp run ub
#include <initializer_list>
#include <cstdio>
std::initializer_list<int> make(int n) {
  return {n, n + 1, n + 2};     // the backing array is destroyed at the end of the return statement
}
int main(int argc, char**) {
  auto il = make(argc);
  std::printf("%d\n", *il.begin());   // UB: reads a destroyed array
}
```

Clang 23 gives a `-Wreturn-stack-address` warning for the `return`; compiled with `-fsanitize=address` and run with `ASAN_OPTIONS=detect_stack_use_after_return=1`, it reports stack-use-after-return. If all elements are constants (`return {1, 2, 3};`), Clang puts the array in static storage and the program appears to work, but by the standard it is still UB.

`initializer_list` itself has no reference members (it is usually a pointer plus a length), so the rule of [[stmt.return#6]] about constituent references bound to temporaries doesn't reach it. Think of it as a view onto a temporary array, like `std::string_view`: don't store it and don't return it.

## Narrowing conversions (¶7)

```cpp error
int x = 999;          // not a constant expression
const int y = 999;
const int z = 99;
char c1 = x;          // OK: not list-initialization (although it does narrow)
char c2{x};           // error: may narrow
char c3{y};           // error: narrows (assuming 8-bit char)
char c4{z};           // OK: the constant 99 fits
unsigned char uc1 = {5};    // OK
unsigned char uc2 = {-1};   // error
unsigned int ui1 = {-1};    // error
signed int si1 = { (unsigned int)-1 };   // error
int ii = {2.0};       // error: no constant exception for floating to integer
float f1 { x };       // error: may narrow
float f2 { 7 };       // OK: 7 is exactly representable as float
bool b = {"meow"};    // error: pointer to bool
int f(int);
int a[] = { 2, f(2), f(2.0) };   // OK: the double → int is not at the top level
```

¶7 A **narrowing conversion** ([[g:narrowing-conversion|narrowing conversion]]) is one of the following implicit conversions:

| Paragraph | From | To | Exception that isn't narrowing |
|---|---|---|---|
| ¶7.1 | Floating-point | Integer | None, not even the constant `2.0` |
| ¶7.2 | Floating-point `T` | A floating-point type whose conversion rank is neither greater than nor equal to `T`'s | The source is a constant expression and the value after conversion is finite and doesn't overflow, or the values before and after are both non-finite |
| ¶7.3 | Integer or unscoped enumeration | Floating-point | The source is a constant expression, the converted value fits, and converting back yields the original value |
| ¶7.4 | Integer or unscoped enumeration | An integer type that can't represent all values of the source type | ¶7.4.1 the source is a bit-field whose width w is less than its type's width, and the target can represent all values of a w-bit integer of the same signedness; ¶7.4.2 the source is a constant expression whose value (after integral promotion) fits |
| ¶7.5 | Pointer or pointer to member | `bool` | None |

Note 7 points out that these conversions are only forbidden at the top level of list-initialization; those nested inside other expressions are unaffected, such as the `double` → `int` inside `f(2.0)` in the example above.

```cpp error
double d = 0.1;
float f1{d};                // error: not a constant
float f2{0.1};              // OK: constant and finite; inexactness is fine
float f3{1e300};            // error: overflow
long double ld{d};          // OK: higher rank
float f5{16777217};         // error: 2²⁴+1 doesn't round-trip
float f6{16777216};         // OK
struct BF { unsigned v : 4; } bf;
unsigned char uc{bf.v};     // OK: ¶7.4.1
bool b1{1};                 // OK: the constant 1 fits
bool b2{2};                 // error
int* p = nullptr;
bool b3{p};                 // error: ¶7.5
```

Each exception has its reason:

- ¶7.1 Floating to integer has no constant exception. Writing `int i{2.0}` almost always means the type is wrong.
- ¶7.2 The constant exception for floating-point demotion allows inexactness: otherwise you couldn't even write `float f{0.1};`, since `0.1` isn't exactly representable as `float`. It only requires the value to be finite and not to overflow, so `float f{1e300};` is ill-formed; infinities and NaNs can convert among themselves. Since C++23 the rule is phrased in terms of **floating-point conversion rank** ([[conv.rank]]) to cover extended floating-point types ([[P1467R9]]): the ranks of `std::float16_t` and `std::bfloat16_t` are unordered, so conversion between them is narrowing in both directions.
- ¶7.3 Integer to floating requires an exact round trip, so `float f{16777217};` is ill-formed and `float f{16777216};` is valid.
- ¶7.4.1 The value of `unsigned v : 4` is always between 0 and 15, so initializing an `unsigned char` from it loses no information and isn't narrowing even if `v` isn't a constant. This is a newer rule added through a defect report.
- ¶7.5 Pointer to `bool` was added by [[P1957R2]] (C++20, as a defect report). Before it, `std::variant<bool, std::string> v = "abc";` selected `bool`, because `const char*` → `bool` is a standard conversion, better than the user-defined conversion to `std::string`. `variant`'s converting constructor filters alternative types by whether they can be list-initialized without narrowing, and counting pointer to `bool` as narrowing fixed this problem.

## `auto` and braces

```cpp error
#include <initializer_list>
auto x1 = { 1, 2 };         // std::initializer_list<int>
auto x2 = { 1, 2.0 };       // error: can't deduce the element type
auto x3{ 1, 2 };            // error: direct-list-initialization allows only one element
auto x4 = { 3 };            // std::initializer_list<int>
auto x5{ 3 };               // int
decltype(auto) x6 = { 1, 2 };   // error: { 1, 2 } is not an expression
```

[[dcl.spec.auto]] has special deduction rules for braced initializers. The difference between `x4` and `x5` comes from [[N3922]]: under the original C++11/14 rules, `auto x5{3};` also deduced `initializer_list<int>`, which was widely regarded as a design mistake. N3922 changed direct-list-initialization to deduce the element type in C++17, and mainstream compilers treat it as a defect fix applied to all modes since C++11.

Deducing `initializer_list` from a braced list is special to `auto`; function template argument deduction and return type deduction don't do it:

```cpp error
#include <initializer_list>
template<class T> void f(T);
template<class T> void g(std::initializer_list<T>);
void test() {
  f({1, 2});      // error: the braced list makes T a non-deduced context
  g({1, 2});      // OK: T = int
}
auto lam = [] { return {1, 2}; };   // error: can't deduce a return type from a braced list
```

## Class template argument deduction and braces

```cpp run ok
#include <vector>
#include <type_traits>
std::vector v{1, 2, 3};          // vector<int>
std::vector v2{v};               // vector<int>: copy
std::vector v3{v, v};            // vector<vector<int>>
static_assert(std::is_same_v<decltype(v2), std::vector<int>>);
static_assert(std::is_same_v<decltype(v3), std::vector<std::vector<int>>>);
int main() {}
```

The inconsistency between `v2` and `v3` often confuses people. [[over.match.class.deduct#6]] says that during class template argument deduction (CTAD), if the list has a single expression whose type is a specialization of the template being deduced or a class derived from one, the first phase of [[over.match.list]] (initializer-list constructors) is skipped, so the copy deduction candidate wins.

This is exactly the opposite of `S s3{s2}` selecting the `initializer_list<S>` constructor under ¶3.7: this CTAD step prefers copying, and after the type has been deduced, constructor selection still follows ¶3.7.

## Implementation notes

!!! impl
    - Layout of `std::initializer_list`: libc++ and libstdc++ use a pointer plus a length, MSVC STL uses two pointers to the beginning and end. The compiler constructs it directly through a private constructor, so it must come from the standard library header.
    - Placement of the backing array: when all elements are constants, compilers have long put the array in a read-only data section, which the as-if rule allows when the address is not observable; [[P2752R3]] makes this optimization valid even when the address can be observed.
    - Clang's narrowing diagnostics belong to the `-Wc++11-narrowing` group, which is an error by default in C++11 and later modes, with diagnostics like type 'double' cannot be narrowed to 'int' in initializer list.

## History

!!! history
    - C++11: list-initialization, `std::initializer_list` and narrowing conversions.
    - C++14: brace elision in aggregate initialization relaxed; classes with default member initializers can also be aggregates ([[dcl.init.aggr]]).
    - C++17: [[N3922]] makes `auto x{1}` deduce `int`; [[P0138R2]] allows enumerations with a fixed underlying type to be direct-list-initialized from integers; defect fixes such as ¶3.2.
    - C++20: [[P0329R4]] designated initializers; [[P1957R2]] makes pointer to `bool` narrowing; references to arrays of unknown bound can deduce the bound from a list.
    - C++23: [[P1467R9]] extended floating-point types, with narrowing rules phrased in terms of floating-point conversion rank.
    - C++26: [[P2752R3]] allows backing arrays to be placed in static storage and shared.
    - After C++26: designating members of base classes is allowed.

## Common misconceptions

!!! pitfall "`vector<int>{n, v}` equals `vector<int>(n, v)`"
    For types with initializer-list constructors, non-empty braces almost always select them. When you need the constructor taking a size and a value, use parentheses.

!!! pitfall "Double braces with `vector<string>`"
    In `std::vector<std::string> v{{"a", "b"}};`, the outer braces correspond to `initializer_list<string>`, and the inner `{"a", "b"}` initializes just one `string`, calling the iterator-range constructor `string(const char*, const char*)`. The two pointers point to different literals, so the behavior is undefined. The correct form is `{"a", "b"}`.

!!! pitfall "Narrowing just makes a candidate non-viable"
    Narrowing is an error, not a mismatch. `std::vector<int> v{3.0};` doesn't fall back to `vector(size_type)`. In generic code, `T{args...}` can fail because of narrowing where `T(args...)` succeeds.

!!! pitfall "Moving elements out of an `initializer_list`"
    The backing array's elements are const, so `std::vector<std::unique_ptr<T>> v{std::make_unique<T>()};` is ill-formed. Use `reserve` plus `emplace_back` instead, or construct from an array or range.

!!! pitfall "Keeping an `initializer_list` as a container"
    It is only a view onto a temporary backing array, and dangles as a data member or return value. As a data member initialized in a *mem-initializer* it gets a diagnostic; returning it only gets a warning.

## Questions

!!! question "Question 1"
    Which constructor does each line call?
    ```cpp
    struct X {
      X(int, int);                             // #1
      X(std::initializer_list<long>);          // #2
      explicit X(std::initializer_list<int>);  // #3
    };
    X a{1, 2};
    X b = {1, 2};
    X c(1, 2);
    ```

<details markdown="1">
<summary>Answer</summary>

- `a`: direct-list-initialization. The first-phase candidates are #2 and #3. `{1, 2}` to `initializer_list<int>` is an identity conversion, while to `initializer_list<long>` it needs integral conversions, so #3 is better. Direct-initialization allows explicit, so #3 is selected.
- `b`: copy-list-initialization. The first phase likewise selects #3; explicit constructors participate in overload resolution, and once one is selected the program is ill-formed, with no fallback to #2.
- `c`: not list-initialization; in ordinary overload resolution only #1 is viable.
</details>

!!! question "Question 2"
    Which step of ¶3 does `struct S { int x; }; S s{S{1}};` take? What if `S` gets a constructor `S(std::initializer_list<S>)`?

<details markdown="1">
<summary>Answer</summary>

`S` is an aggregate and the list has one element of type `S`, so ¶3.2 applies: `s` is initialized directly from `S{1}`. Per [[dcl.init#15.6.1]], a prvalue of the same type becomes `s` directly, with no copy.

With that constructor added, `S` has a user-declared constructor and is no longer an aggregate, so neither ¶3.2 nor ¶3.4 applies. Look first at the inner `S{1}`: it goes through ¶3.7, and the first phase would have to initialize an `S` element from `1`, but `S` has no constructor taking `int`, so it isn't viable; the second phase has no viable constructor either. So `S{1}` is ill-formed, and so is the whole declaration.
</details>

!!! question "Question 3"
    Why does ¶3.8 only allow direct-list-initialization, while ¶3.9 allows both direct- and copy-list-initialization for scalars?

<details markdown="1">
<summary>Answer</summary>

¶3.9 handles cases where an implicit conversion is allowed anyway, such as `int` → `long`. Braces only add a narrowing check; `long l = {1};` means the same as `long l = 1;`, and there's no reason to forbid it.

¶3.8 handles a case where no implicit conversion is allowed: there is no implicit conversion from integers to enumerations, and here braces add a new conversion ability. If copy-list-initialization were allowed, `f({42})`, `return {42};` and an aggregate member `{42}` would all silently turn integers into enumerations, defeating the purpose of strongly typed enumerations. Allowing only direct-list-initialization requires the type to be written at the point of initialization: `byte b{42}` or `byte{42}`.
</details>
