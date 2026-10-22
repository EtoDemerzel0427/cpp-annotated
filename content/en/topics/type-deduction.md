---
title: Type deduction in all its forms
summary: The seven places in C++ where the compiler deduces a type (template argument deduction, auto, decltype, decltype(auto), CTAD, structured bindings, init-captures) actually rely on just two sets of rules; this page puts them side by side.
tags: type deduction, auto, decltype, CTAD, forwarding references, templates
updated: 2026-10-19
---

!!! tldr
    - Type deduction has only two sets of rules: template argument deduction (used by `auto`, CTAD, generic lambdas and init-captures), and the `decltype` rules (used by `decltype(auto)`).
    - Deduction by value drops references and top-level const, and arrays and functions decay to pointers; deduction by reference drops nothing.
    - `auto` differs from template deduction in just one place: `auto x = {1, 2};` deduces `std::initializer_list<int>`.
    - `decltype(x)` looks at the declaration of `x`, `decltype((x))` at the value category of the expression; as a result `decltype(auto)` can return a dangling reference from `return (x);`.
    - A forwarding reference `T&&` encodes the argument's value category into `T`, and reference collapsing together with `std::forward<T>` restores it.

## The same initializer, different results

```cpp run ok
const int ci = 0;
auto           a = ci;     // int
auto&          b = ci;     // const int&
decltype(ci)   c = ci;     // const int
decltype((ci)) d = ci;     // const int&
int main() { (void)a; (void)b; (void)c; (void)d; }
```

All four declarations have the initializer `ci`, yet the resulting types all differ. The reason is that two sets of rules are at work:

1. **Template argument deduction** ([[temp.deduct.call]]): for `template<class T> void f(P); f(expr);`, the parameter type `P` and the argument type `A` are compared to work out `T`. `auto` declarations, class template argument deduction (CTAD), generic lambdas and abbreviated function templates all reuse these rules.
2. **The `decltype` rules** ([[dcl.type.decltype]]): the type is determined by the form of the expression (whether it is an unparenthesized name) and its value category. `decltype(auto)` reuses these rules.

Structured bindings and lambda init-captures first deduce a hidden variable with `auto` and then introduce names on top of it, so each has a few peculiarities of its own.

| Mechanism | Which rules | Where in the standard | Introduced |
|---|---|---|---|
| Function template argument deduction | Template deduction | [[temp.deduct]] | C++98 |
| `auto` variables, `auto` return types | Template deduction, plus the `initializer_list` special case | [[dcl.type.auto.deduct]] | C++11 / C++14 |
| `decltype(e)` | decltype rules | [[dcl.type.decltype]] | C++11 |
| `decltype(auto)` | decltype rules | [[dcl.type.auto.deduct#4]] | C++14 ([[N3638]]) |
| CTAD: `std::vector v{1, 2};` | Template deduction on invented function templates | [[over.match.class.deduct]] | C++17 ([[P0091R3]]) |
| Structured bindings `auto [a, b] = e;` | `auto`, plus a special `decltype` | [[dcl.struct.bind]] | C++17 ([[P0217R3]]) |
| Init-captures `[x = e]` | `auto` | [[expr.prim.lambda.capture#6]] | C++14 ([[N3648]]) |
| Generic lambdas, abbreviated function templates `void f(auto x)` | Template deduction | [[dcl.fct]] | C++14 / C++20 ([[P1141R2]]) |

## Template argument deduction

For `template<class T> void f(P); f(expr);`, let `A` be the type of `expr`. Before comparing, `P` and `A` are adjusted according to the form of `P` ([[temp.deduct.call#2]], [[temp.deduct.call#3]]):

- `P` is not a reference (pass by value): if `A` is an array it is replaced by a pointer, if a function by a function pointer, and top-level cv is removed.
- `P` is a reference: the referenced type is used for comparison; `A` doesn't decay, and cv is kept.
- `P` is a forwarding reference `T&&` (see below) and the argument is an lvalue: `A` is replaced by `A&`.

<div class="compare" markdown="1">

```cpp
template<class T> void byval(T);
const int ci = 0;
int arr[3];
byval(ci);   // T = int
byval(arr);  // T = int*
```

```cpp
template<class T> void byref(T&);
const int ci = 0;
int arr[3];
byref(ci);   // T = const int
byref(arr);  // T = int[3]
```

</div>

Deduction seeks only an exact match and doesn't consider implicit conversions. [[temp.deduct.call#4]] tolerates only three kinds of difference: with a reference parameter, the deduced type may be more cv-qualified; qualification conversions and function pointer conversions between pointers; and an argument type derived from a deduced class template specialization. So `std::max(1, 2.0)` fails to deduce: the two arguments deduce `T = int` and `T = double` respectively, and differing deductions make deduction fail ([[temp.deduct.type#2]]); `1` isn't converted to `double`.

When you need a conversion, you can write the template argument explicitly, `std::max<double>(1, 2.0)`, or use `std::type_identity_t<T>` (C++20, [[P0887R1]]) to put a parameter in a non-deduced context, so it takes part only in conversion and not in deduction.

## auto: template deduction plus one braced special case

[[dcl.type.auto.deduct#3]] says deducing `auto` means replacing `auto` with an invented template parameter `U`, treating the initializer as the argument, and deducing according to [[temp.deduct.call]]. The type deduced for `const auto& x = e;` is the same as `U` in `template<class U> void f(const U&); f(e);`.

The only exception is **copy-list-initialization** (the `= {...}` form): in that case `auto` is replaced with `std::initializer_list<U>` before deducing.

```cpp
auto x1 = { 1, 2 };   // std::initializer_list<int>
auto x2 = { 1, 2.0 }; // error: can't deduce the element type
auto x3{ 1, 2 };      // error: direct-list-initialization takes only one element
auto x4 = { 3 };      // std::initializer_list<int>
auto x5{ 3 };         // int

template<class T> void g(T);
g({1, 2, 3});         // error: the braced list puts T in a non-deduced context
```

How function templates handle braced arguments is in [[temp.deduct.call#1]]: deduction from a braced list is possible only when the parameter has the form `std::initializer_list<T>` or `T[N]`; otherwise the parameter takes no part in deduction.

`auto` in a return type has no such special case: `return {1, 2};` is simply ill-formed (¶2.1.2 of [[dcl.type.auto.deduct#2]]).

!!! history "The changing meaning of auto x{1}"
    In C++11/14, `auto x{3};` deduced `std::initializer_list<int>`, contrary to most people's intuition. [[N3922]] changed it to `int`, and specified that direct-list-initialization may have only one element. This was a C++17 change, and mainstream compilers adopt the new rule in C++11/14 modes as well, as a defect fix.

## decltype: names versus expressions

[[dcl.type.decltype#1]] splits `decltype(e)` into two cases:

1. `e` is an unparenthesized name (*id-expression*) or an unparenthesized class member access: the result is the **declared type** of the entity the name refers to. Structured bindings and constant template parameters have their own rules; see below.
2. Any other expression: a reference is added according to the [[topics/value-categories|value category]] of `e`. An xvalue gives `T&&`, an lvalue gives `T&`, and a prvalue gives `T`.

So `decltype(x)` asks what `x` was declared as, while `decltype((x))` asks what value category the expression `(x)` has. A named variable is an lvalue, so `decltype((x))` is always an lvalue reference.

## One comparison table

Given these declarations:

```cpp
int i = 0;  const int ci = 0;  int& ri = i;  const int& cri = ci;
int&& f();  int arr[3];  void fn(int);
```

| Input `e` | `T` in `g(T)` | `T` in `g(T&)` | `T` in `g(T&&)` | `auto x = e;` | `auto& x = e;` | `decltype(e)` | `decltype(auto) x = e;` |
|---|---|---|---|---|---|---|---|
| `i` | `int` | `int` | `int&` | `int` | `int&` | `int` | `int` |
| `(i)` | `int` | `int` | `int&` | `int` | `int&` | `int&` | `int&` |
| `ci` | `int` | `const int` | `const int&` | `int` | `const int&` | `const int` | `const int` |
| `ri` | `int` | `int` | `int&` | `int` | `int&` | `int&` | `int&` |
| `cri` | `int` | `const int` | `const int&` | `int` | `const int&` | `const int&` | `const int&` |
| `42` | `int` | ✗ | `int` | `int` | ✗ | `int` | `int` |
| `f()` (xvalue) | `int` | ✗ | `int` | `int` | ✗ | `int&&` | `int&&` |
| `std::move(i)` | `int` | ✗ | `int` | `int` | ✗ | `int&&` | `int&&` |
| `arr` | `int*` | `int[3]` | `int(&)[3]` | `int*` | `int(&)[3]` | `int[3]` | `int[3]`¹ |
| `fn` | `void(*)(int)` | `void(int)` | `void(&)(int)` | `void(*)(int)` | `void(&)(int)` | `void(int)` | ✗² |
| `"hi"` | `const char*` | `const char[3]` | `const char(&)[3]` | `const char*` | `const char(&)[3]` | `const char(&)[3]` | `const char(&)[3]` |
| `{1, 2}` | ✗ | ✗ | ✗ | `initializer_list<int>` | ✗ | ✗ (not an expression) | ✗ |

✗ means deduction fails or the code is ill-formed. ¹ The deduced type is `int[3]`, but an array can't be initialized from another array, so this declaration is ill-formed. ² The deduced type is the function type `void(int)`, and a variable of that type can't be declared.

A few patterns can be read off the table:

- The `auto` column is identical to the `g(T)` column, except for the braced row. `auto&` corresponds to `g(T&)`, and `auto&&` to `g(T&&)`.
- Deduction by value turns `ci`, `ri` and `cri` all into `int`.
- `decltype` drops nothing, but treats names and expressions differently, so the `i` and `(i)` rows differ.
- A string literal is an lvalue, so `decltype("hi")` is `const char(&)[3]`.

The code below checks most cells of the table with `static_assert`; it compiles with Clang 23:

```cpp run ok title="deduction_table.cpp"
#include <type_traits>
#include <initializer_list>
#include <utility>
template<class T, class U> constexpr bool same = std::is_same_v<T, U>;

int i = 0; const int ci = 0; int& ri = i; const int& cri = ci; int&& f(); int arr[3];
void fn(int);

template<class Expect, class T> void byval(T)  { static_assert(same<T, Expect>); }
template<class Expect, class T> void byref(T&) { static_assert(same<T, Expect>); }
template<class Expect, class T> void fwd(T&&)  { static_assert(same<T, Expect>); }

auto  a1 = ci;     static_assert(same<decltype(a1), int>);
auto& a2 = ci;     static_assert(same<decltype(a2), const int&>);
auto&& a3 = i;     static_assert(same<decltype(a3), int&>);
auto&& a4 = 0;     static_assert(same<decltype(a4), int&&>);
auto  a5 = arr;    static_assert(same<decltype(a5), int*>);
auto& a6 = arr;    static_assert(same<decltype(a6), int(&)[3]>);
auto  a7 = fn;     static_assert(same<decltype(a7), void(*)(int)>);
auto  a8 = {1, 2}; static_assert(same<decltype(a8), std::initializer_list<int>>);
auto  a9{1};       static_assert(same<decltype(a9), int>);
auto  a10 = {1};   static_assert(same<decltype(a10), std::initializer_list<int>>);

static_assert(same<decltype(i), int> && same<decltype((i)), int&>);
static_assert(same<decltype(f()), int&&> && same<decltype(ci), const int>);
static_assert(same<decltype("hi"), const char(&)[3]>);

decltype(auto) d1 = ci;  static_assert(same<decltype(d1), const int>);
decltype(auto) d2 = (i); static_assert(same<decltype(d2), int&>);
decltype(auto) d3 = f(); static_assert(same<decltype(d3), int&&>);

int main() {
    byval<int*>(arr);   byref<int[3]>(arr);          fwd<int(&)[3]>(arr);
    byval<int>(ci);     byref<const int>(ci);        fwd<const int&>(ci);
    byval<const char*>("hi"); byref<const char[3]>("hi"); fwd<const char(&)[3]>("hi");
    byval<void(*)(int)>(fn);  byref<void(int)>(fn);       fwd<void(&)(int)>(fn);
    fwd<int>(42);       fwd<int>(std::move(i));
}
```

## Forwarding references and reference collapsing

A [[g:forwarding-reference|forwarding reference]] is `T&&` written for a cv-unqualified template parameter `T`; `auto&&` is one too ([[temp.deduct.call#3]]). When the argument is an lvalue, `T` is deduced as an lvalue reference type; when it is an rvalue, `T` is deduced as a non-reference type. The name comes from [[N4164]]; before that it was often called a universal reference.

```cpp
template<class T> void f(T&& x);
int i = 0;
f(i);   // T = int&, parameter type int& && collapses to int&
f(0);   // T = int,  parameter type int&&
```

Substituting `T = int&` back into `T&&` gives `int& &&`. A program can't write a reference to a reference directly, but when one is formed through a template parameter or type alias, **reference collapsing** applies ([[dcl.ref#7]]): if either is an lvalue reference, the result is an lvalue reference.

| `T` | `T&` | `T&&` |
|---|---|---|
| `int` | `int&` | `int&&` |
| `int&` | `int&` | `int&` |
| `int&&` | `int&` | `int&&` |

This way, whether the argument was an lvalue or an rvalue is recorded in `T`.

### How std::forward restores the value category

```cpp
template<class T>
constexpr T&& forward(std::remove_reference_t<T>& t) noexcept {
    return static_cast<T&&>(t);
}
```

Inside the function body, a named parameter `x` is an lvalue no matter how it was declared. `std::forward<T>(x)` uses the `T` deduced by the enclosing function to restore the value category the caller passed in:

- `T = int&` (the original argument was an lvalue): the return type `int& &&` collapses to `int&`, and the result is an lvalue.
- `T = int` (the original argument was an rvalue): the return type is `int&&`, and the result is an xvalue.

The parameter is written `std::remove_reference_t<T>&`, where `T` appears in the qualifying part before `::`, a non-deduced context ([[temp.deduct.type#5]]). So `T` must be written explicitly when calling it. `std::move` doesn't need information from the outer layer; it unconditionally converts to `std::remove_reference_t<T>&&`, and the result is always an xvalue.

### `&&` that isn't a forwarding reference

| Form | Reason |
|---|---|
| `template<class T> void f(const T&&)` | Has cv |
| `template<class T> void f(std::vector<T>&&)` | Not a reference to the template parameter itself |
| `template<class T> struct S { void f(T&&); };` | `T` is already determined when `f` is called; no deduction |
| `T&&` in a constructor during CTAD (`T` a class template parameter) | Explicitly excluded by the definition ([[temp.deduct.call#3]] Example 4) |

## decltype(auto): forwarding return values unchanged

`decltype(auto)` takes the initializer (or the operand of `return`) as the operand of `decltype` to determine the type ([[dcl.type.auto.deduct#4]]). Its main use is forwarding a function's return value: if the forwarded function returns a reference, so does the forwarder:

```cpp
template<class F, class... Args>
decltype(auto) call(F&& f, Args&&... args) {
    return std::forward<F>(f)(std::forward<Args>(args)...);
}
```

With `auto` as the return type, a function returning `int&` would become one returning an `int` copy after passing through `call`.

### Parenthesizing the returned name

```cpp
int g = 0;
auto           r1() { return (g); }   // int
decltype(auto) r2() { return (g); }   // int&: (g) is an lvalue expression
decltype(auto) r3() { return g; }     // int: an unparenthesized name, takes the declared type
```

When the returned thing is a local variable, parentheses produce a dangling reference:

```cpp
decltype(auto) bad() {
    int x = 0;
    return (x);     // C++20: int&; since C++23: int&&. Dangling either way
}
```

C++23's [[P2266R3]] says that if the operand of `return` is a name designating an implicitly movable entity (such as a local variable), with or without parentheses it is an xvalue. So the `(x)` here is an xvalue and deduces `int&&`. Clang 23 gives a `-Wreturn-stack-address` warning for this line.

Example 3 in [[dcl.type.auto.deduct#4]] shows exactly this:

```cpp
auto f1(int x) -> decltype((x)) { return (x); }   // return type is int&
auto f2(int x) -> decltype(auto) { return (x); }  // return type is int&&
```

!!! lawyer "The body of f1 is ill-formed"
    The example only asserts the return type of `f1`. The trailing return type isn't in a `return` statement, so `decltype((x))` is still `int&`; but the `(x)` in the function body is an xvalue under P2266 and can't bind to `int&`. Under `-std=c++2c`, Clang 23 reports an error for `f1`, "non-const lvalue reference to type 'int' cannot bind to a temporary of type 'int'"; under `-std=c++20` it only gives a dangling warning. `f2` compiles, but returns a dangling reference to the parameter.

## CTAD: deduction on invented function templates

When you write `std::pair p(1, "x");`, the compiler generates an invented function template for each constructor and each deduction guide of `pair`, whose template parameters are the class template's parameters plus the constructor template's own. It then performs ordinary overload resolution on the initializer ([[over.match.class.deduct]]). So the results of CTAD follow the rules of template deduction:

```cpp
std::vector v{1, 2};             // vector<int>: initializer_list constructor
std::pair   pr(1, "x");          // pair<int, const char*>: the deduction guide takes by value, arrays decay
std::tuple  tp{ci, ri};          // tuple<int, int>: deduced by value, const and references dropped
std::array  ar{1, 2, 3};         // array<int, 3>: deduction guide
template<class T> struct Agg { T x, y; };
Agg ag{1, 2};                    // Agg<int>: C++20 aggregate deduction
```

The most surprising case is braces containing a single object of the same class:

```cpp
std::vector v2{v};       // vector<int>, not vector<vector<int>>
std::vector v4{v, v};    // vector<vector<int>>
```

Besides constructors and deduction guides, CTAD has a **copy deduction candidate**, equivalent to `template<class T> vector(vector<T>) -> vector<T>`. ¶6.1 of [[over.match.class.deduct#6]] says that when the braces contain a single expression whose type is a specialization of this class template (or derived from one), the round that prefers `initializer_list` constructors is skipped, so the copy deduction candidate wins. Whether you get an extra layer of wrapping depends on the number of elements, so writing `std::vector{x}` in generic code is dangerous; write `std::vector<T>{x}`.

## Structured bindings: the names aren't variables

`auto [a, b] = e;` first declares a hidden variable, as if `auto e' = e;` (with `&`, `&&` and cv all applied to it), and then makes `a` and `b` refer to the elements of `e'` ([[dcl.struct.bind]]). For class types, `a` and `b` aren't independent variables, just names referring to members:

```cpp
struct P { int a; const double b; };
P p{1, 2.0};
auto  [sa, sb] = p;       // e' is a copy of P
auto& [ra, rb] = p;       // e' is a P&

decltype(sa)    // int: the declared type of the member
decltype(sb)    // const double
decltype(ra)    // int, not int&
decltype((sa))  // int&: the expression is an lvalue
```

¶1.1 of [[dcl.type.decltype#1]] says that for an unparenthesized structured binding name, `decltype` gives the **referenced type** defined in the structured binding declaration. So even though `ra` actually refers to `p.a`, `decltype(ra)` has no reference.

`auto` and cv apply to the hidden variable, not to `a` and `b` themselves. In `const auto& [x, y] = p;`, `e'` is a `const P&`, so `decltype(x)` is `const int`.

## Init-captures: just auto

[[expr.prim.lambda.capture#6]] says an init-capture without an ellipsis behaves as if it declares and explicitly captures a variable of the form `auto init-capture;`. So in `[x = e]`, the type of `x` is deduced as for `auto x = e;`, dropping references and top-level const:

```cpp
const int ci = 0;
auto L1 = [x = ci] { /* decltype(x) is int; decltype((x)) is const int& because operator() is const */ };
auto L2 = [&r = ci] { /* decltype(r) is const int& */ };
auto L3 = [x = ci] mutable { /* decltype((x)) is int& */ };
```

An ordinary capture by copy `[ci]` doesn't go through `auto`; the closure member's type is just the type of `ci`, `const int`, and can't be modified even in a `mutable` lambda. Since C++20 you can also write a pack init-capture `[...xs = std::move(args)]` ([[P0780R2]]).

## Other places that reuse template deduction

- **Generic lambdas**: the call operator of `[](auto x, auto&& y) {}` is a function template, with an invented template parameter for each `auto` parameter ([[expr.prim.lambda]]).
- **Abbreviated function templates** (C++20, [[P1141R2]]): `void f(auto x);` is equivalent to `template<class T> void f(T x);`. Likewise for `void f(const auto& x)` and `void f(std::integral auto x)`.
- **`auto` constant template parameters**: in `template<auto N> struct S;`, the type of `N` is deduced from the template argument (¶2.4 of [[dcl.type.auto.deduct#2]]). Writing `template<decltype(auto) N>` can deduce reference types.

## Common surprises

| Symptom | Reason | Source |
|---|---|---|
| `auto x = vec_bool[0];` gives a proxy object, not a `bool` | `auto` deduces the expression's real type, `vector<bool>::reference` | [[vector.bool]] |
| `auto s = "hi";` is a `const char*` | Deduced by value; the array decays | [[temp.deduct.call#2]] |
| `std::max(1, 2.0)` fails to compile | The two arguments deduce different `T`s, and deduction does no conversions | [[temp.deduct.type#2]] |
| `template<class T> void f(std::vector<T>); f({1, 2});` fails | A braced list can only deduce `initializer_list<T>` and `T[N]` parameters | [[temp.deduct.call#1]] |
| In `const auto& [x, y] = f();`, `decltype(x)` isn't a reference | `decltype` on a structured binding gives the referenced type | [[dcl.type.decltype#1]] |
| `std::vector{v}` isn't a vector of vectors | With a single element of the same class, `initializer_list` constructors are skipped | [[over.match.class.deduct#6]] |
| `decltype(auto) f() { return (x); }` returns a reference | A parenthesized name is treated as an expression | [[dcl.type.decltype#1]] |
| A constructor with a forwarding reference steals copy construction | For a non-const lvalue, the `Person&` deduced by `T&&` matches better than `const Person&` | [[over.match.best]] |
| `template<class T> void f(T&&, T&&); f(i, 0);` fails | The lvalue deduces `int&`, the rvalue `int`, and they conflict | [[temp.deduct.call#3]] |
| `template<class C> void f(typename C::iterator);` can't deduce `C` | The part before `::` is a non-deduced context | [[temp.deduct.type#5]] |

## Questions

!!! question "Question 1"
    ```cpp
    const int arr[2] = {1, 2};
    auto a = arr;
    auto& b = arr;
    decltype(auto) c = (arr[0]);
    auto [x, y] = arr;
    ```
    What are `decltype(a)`, `decltype(b)`, `decltype(c)` and `decltype(x)`?

<details markdown="1">
<summary>Answer</summary>

- `a`: deduced by value, the array decays to a pointer, and the pointed-to const is kept, giving `const int*`.
- `b`: deduced by reference, no decay; `auto` deduces `const int[2]`, and `b` is `const int(&)[2]`.
- `c`: `(arr[0])` is an lvalue of type `const int`, giving `const int&`.
- `x`: when the initializer is an array, [[dcl.struct.bind#1]] says the type of the hidden variable is the array type `const int[2]` itself, copied element by element without decay. `decltype(x)` is the element type `const int`.

All of these were checked with `static_assert` on Clang 23.
</details>

!!! question "Question 2"
    Why does `std::forward` require its template argument to be written explicitly, while `std::move` doesn't? What would go wrong if `forward`'s parameter were changed to `T&& t` so it deduced on its own?

<details markdown="1">
<summary>Answer</summary>

What `forward` restores is the value category at the caller's level, and that information is kept only in the `T` deduced by the enclosing function template: `T = U&` for an lvalue, `T = U` for an rvalue. Inside the function body a named parameter is always an lvalue, so if `forward` deduced from it, it could only deduce `U&` and would always return an lvalue, making `forward` useless. So `forward` puts its parameter in a non-deduced context, forcing the caller to pass in the outer `T`. `std::move` doesn't need information from the outer level; it always converts to an xvalue and can deduce on its own.
</details>

!!! question "Question 3"
    When does the type deduced by `auto x = expr;` differ from the `T` deduced by `template<class T> void f(T); f(expr);`?

<details markdown="1">
<summary>Answer</summary>

Only when `expr` is a braced list: `auto x = {1, 2};` deduces `std::initializer_list<int>`, while `f({1, 2})` fails to deduce. `auto x{1};` is direct-list-initialization with a single element, deduces `int`, and agrees with `f(1)`. In every other case [[dcl.type.auto.deduct#3]] simply follows [[temp.deduct.call]], and the results are the same. `auto` in a return type doesn't even have this exception: `return {1, 2};` is ill-formed.
</details>
