---
title: Lambda expressions
summary: "A lambda expression defines an unnamed closure class and creates an object of it: the properties of the call operator (const, mutable, static, constexpr, generic, explicit object parameter), what is captured and how, what captured names refer to, plus the conversion to a function pointer and the special member functions."
updated: 2026-10-19
---

!!! tldr
    - Every lambda expression defines a unique unnamed class (the closure type) and creates one object of that class (the closure object); variables captured by copy become its data members.
    - The call operator is a `const` member function by default; `mutable` removes the const, `static` makes it a static member function, and it is automatically `constexpr` when it qualifies.
    - With `[=]` or `[&]`, a lambda implicitly captures whichever enclosing local variables its body references in potentially-evaluated expressions; this is decided by syntax, not by whether there is really an odr-use. The `this` implicitly captured by `[=]` is a pointer, not a copy of the object, and this is deprecated.
    - Reading the value of a constant is not an odr-use, so it can be used without capture; taking its address or binding a reference requires a capture.
    - Only a lambda with no captures and no explicit object parameter converts to a function pointer (a generic lambda gets a conversion function template); since C++20, captureless closure types can also be default-constructed and assigned.

## A lambda is a class plus an object

```cpp
void demo() {
  int n = 10;
  auto add = [n](int x) { return x + n; };
}
```

The standard introduces no new runtime concept for lambdas. It says `[n](int x) { return x + n; }` does two things: defines an unnamed class, and creates an object of that class. The class the compiler writes for you looks roughly like this (illustration only; the real closure type has no such constructor, and its members have no names):

```cpp
class __Closure {
  int __n;                                            // n captured by copy
public:
  __Closure(int n) : __n(n) {}
  auto operator()(int x) const { return x + __n; }    // const by default
};
auto add = __Closure{n};
```

Most properties of lambdas follow from this model.

A lambda expression is a prvalue ([[expr.prim.lambda.general#2]]), and its result object is called the **closure object** ([[g:closure-object|closure object]]). Because it is a prvalue, the `f` in `auto f = [] {};` is that closure object itself, with no copy or move ([[dcl.init]]).

The type of a lambda expression is called the **closure type** ([[g:closure-type|closure type]]), a unique, unnamed non-union class type ([[expr.prim.lambda.closure#1]]). "Unique" is literal: two lambdas that are identical token for token are still two types.

```cpp run ok
#include <type_traits>

auto a = [] { return 1; };
auto b = [] { return 1; };
static_assert(!std::is_same_v<decltype(a), decltype(b)>);

using T1 = decltype([] {});   // since C++20 lambdas can appear in unevaluated operands
using T2 = decltype([] {});
static_assert(!std::is_same_v<T1, T2>);

int main() {}
```

The closure type is declared in the smallest block scope, class scope or namespace scope that contains the lambda. This determines which namespaces it is associated with for argument-dependent lookup (ADL) ([[expr.prim.lambda.closure#3]], [[basic.lookup.argdep]]).

## Grammar [expr.prim.lambda.general]

A lambda consists of these parts in order; all except the leading `[captures]` and the final body can be omitted:

```text
[captures]  <template-params> requires-clause  attributes  (params)  specifiers  noexcept  attributes  -> return-type  requires-clause  contracts  { body }
```

- `<template-params>` {{c++20}}: `[]<class T>(T a) {}`.
- Attributes before `(params)` {{c++23}} appertain to the call operator itself, e.g. `[] [[nodiscard]] () { return 1; }`; attributes after `(params)` appertain to the call operator's type.
- The specifiers are some of `mutable`, `constexpr`, `consteval`, `static`.
- With no parameters, `()` can be omitted. Since C++23 it can be omitted even when followed by specifiers, `noexcept` or a trailing return type: `[] mutable {}` is valid, whereas C++20 required `[]() mutable {}`.
- Contracts {{c++26}}: `[](int x) pre(x > 0) { … }`.

¶4 There are a few restrictions on combining specifiers: each specifier appears at most once; `constexpr` and `consteval` can't both appear; `mutable` and `static` can't both appear; with an explicit object parameter (`this auto self`) you can't write `mutable` or `static`; and with `static` there can be no captures at all.

```cpp error
auto e1 = [](int) constexpr consteval {};   // error: constexpr and consteval can't coexist
auto e2 = [](this auto) mutable {};         // error: explicit object parameter with mutable
auto e3 = [](this auto) static {};          // error: explicit object parameter with static
auto e4 = [](int) mutable static {};        // error: mutable with static
void f() {
  int x = 0;
  auto e5 = [x](int) static { return x; };  // error: a static lambda can't have captures
}
```

All of these restrictions come from the class model above. `mutable` makes the call operator non-const; with an explicit object parameter that is expressed by the type of `self` instead. A static member function has no object, so it has no way to access capture members.

## The call operator

### Return type [expr.prim.lambda.general]

¶5 Without a trailing return type, the lambda is treated as if it had `-> auto`, and the return type is deduced from the `return` statements by [[dcl.spec.auto]]. So multiple `return`s must deduce the same type, `return {1, 2};` can't be deduced, and the deduced type is never a reference. To return a reference, write `-> auto&` or `-> decltype(auto)`.

```cpp error
void f() {
  auto x1 = [](int i) { return i; };       // OK: returns int
  auto x2 = [] { return { 1, 2 }; };       // error: can't deduce a return type from a braced list
  int j;
  auto x3 = [&]() -> auto&& { return j; }; // OK: returns int&
}
```

In C++11, only a lambda whose body consisted of a single `return expression;` had its return type deduced; all others returned `void`. C++14 switched to the same rules as `auto` return types of ordinary functions.

### const, mutable, static [expr.prim.lambda.closure]

¶5 The closure type has a public inline function call operator. Its parameters and return type come from the lambda's parameter list and return type. ¶7 says which kind of member function it is:

| Lambda form | Call operator |
|---|---|
| `[]() { }` | Non-static member function, `const` |
| `[]() mutable { }` | Non-static member function, not const |
| `[]() static { }` {{c++23}} | Static member function |
| `[](this auto&& self) { }` {{c++23}} | Explicit object member function; cv and reference determined by the type of `self` |

The call operator is never `virtual` and never `volatile`. `noexcept` and contracts written on the lambda apply to the call operator.

¶7 also says the call operator is a constexpr function if either it is declared `constexpr` or `consteval`, or it satisfies the requirements for a constexpr function ([[dcl.constexpr]]). The latter means that since C++17 most lambdas can be called in constant expressions without any annotation. A `consteval` one is an immediate function and can only be called at compile time.

```cpp run ok
auto ID = [](auto a) { return a; };
static_assert(ID(3) == 3);                          // implicitly constexpr

auto ce = [](int i) consteval { return i + 1; };    // immediate function
static_assert(ce(1) == 2);

auto sl = [](int i) static { return i * 2; };       // C++23
static_assert(decltype(sl)::operator()(3) == 6);    // callable without an object

int main() {}
```

The call operator being a constexpr function doesn't make every call a constant expression. In the example in ¶8, the `two` in `auto two = monoid(2);` is not a constexpr variable, and calling `two()` must read its capture member, so `static_assert(two() == 2)` is ill-formed.

!!! tip "What static lambdas are for"
    The non-static `operator()` of a captureless lambda still takes an object argument, even though the object is empty. `static` makes the call operator a real static function and drops that argument; converting to a function pointer (see below) then also yields its address directly, without an intermediate forwarding function.

### Generic lambdas and explicit object parameters

¶6 A lambda with `auto` parameters or a template parameter list is called a **generic lambda** ([[g:generic-lambda|generic lambda]]). `[](this auto self, int i)` is also a generic lambda, because `this auto` is also an `auto` parameter ([expr.prim.lambda.general]).

By [[expr.prim.lambda.closure#5]], the call operator of a generic lambda is a member function template whose template parameters consist of those written in `<…>` plus one invented for each `auto` parameter. The *requires-clause* after `<…>` and the one after the parameter list both become constraints of that template.

Example 1 in the standard shows nested generic lambdas, capturing a function parameter pack, and recursion with an explicit object parameter:

```cpp run ok
#include <iostream>
#include <utility>

int main() {
  auto vglambda = [](auto printer) {
    return [=](auto&&... ts) {                   // ts is a function parameter pack
      printer(std::forward<decltype(ts)>(ts)...);
      return [=]() { printer(ts...); };          // implicitly captures printer and the whole pack ts by copy
    };
  };
  auto p = vglambda([](auto v1, auto v2, auto v3) { std::cout << v1 << v2 << v3; });
  auto q = p(1, 'a', 3.14);    // prints 1a3.14
  q();                         // prints 1a3.14 again

  auto fact = [](this auto self, int n) -> int {
    return (n <= 1) ? 1 : n * self(n - 1);
  };
  std::cout << '\n' << fact(5) << '\n';         // 120
}
```

Before C++23, there was no way for a lambda body to refer to the lambda itself: the closure type has no name, and `this` refers to the enclosing object (see the next section). The explicit object parameter `self` is the closure object itself.

[[expr.prim.lambda.closure#6]] says that for a lambda with captures, the type of the explicit object parameter can only be the closure type, a class publicly and unambiguously derived from it, or a reference to one of these. Accessing a capture means accessing a member of `self`, which makes no sense when `self`'s type is unrelated to the closure.

```cpp error
struct C {
  template <typename T> C(T);   // constructible from any type
};

void func(int i) {
  int x = [=](this auto&&) { return i; }();   // OK
  int y = [=](this C) { return i; }();        // error: has captures, C is unrelated to the closure type
  int z = [](this C) { return 42; }();        // OK: no captures
}
```

### The body is not in the scope of the closure type [expr.prim.lambda.closure]

¶16 The lambda's body becomes the body of the call operator, but it is not in the scope of the closure type. So in a lambda body, name lookup doesn't find members of the closure type; `this` points to the enclosing object ([[expr.prim.this]]); and writing `operator()` finds the enclosing class's `operator()`.

```cpp ok
struct S1 {
  int x, y;
  int operator()(int);
  void f() {
    [=, this]() -> int {
      return operator()(this->x + y);   // i.e. S1::operator()(this->x + (*this).y)
    };
  }
};
```

Except in the body of a `consteval` block ({{c++26}}), `__func__` is implicitly defined at the start of a lambda body ([[dcl.fct.def.general]]); its contents are implementation-defined, and Clang and GCC give `"operator()"`.

## Captures [expr.prim.lambda.capture]

¶1 A lambda body uses local entities from enclosing scopes by capturing them. A **local entity** ([[g:local-entity|local entity]], [[basic.pre]]) is a variable with automatic storage duration, a structured binding, or `*this` in a member function. Global variables and static local variables are not local entities; they can't and needn't be captured; just use the name.

### How to write a capture list (¶2–¶5)

```text
[=]  [&]                     capture-default
[x]  [&x]  [this]  [*this]   simple-capture; x may carry ... (pack expansion)
[x = e]  [&r = e]            init-capture; ...x = e is also possible
```

¶2 Some rules prevent redundancy: if the capture-default is `&`, simple captures can't also have `&`; if the capture-default is `=`, simple captures can only be `&x`, `this` or `*this`; the same name or `this` can't appear twice.

```cpp error
struct S2 { void f(int i); };
void S2::f(int i) {
  [&, i]{ };        // OK
  [&, this, i]{ };  // OK, equivalent to [&, i]
  [&, &i]{ };       // error: with & as default, i can't have & again
  [=, *this]{ };    // OK
  [=, this]{ };     // OK, equivalent to [=], but without the deprecation warning
  [i, i]{ };        // error: i repeated
  [this, *this]{ }; // error: this appears twice
}
```

`[&, this]` is redundant but still accepted for compatibility with C++14 (Note 1). `[=, this]` was added in C++20 to state explicitly that `*this` is captured by reference.

¶3 A lambda can have a capture-default or simple-captures only if its innermost enclosing scope is a block scope (it is in a function body), or it appears in a default member initializer or in a contract assertion. A lambda at namespace scope can't write `[=]`, `[&]` or `[x]`: there are no local entities there. Init-captures are not subject to this restriction; `auto counter = [i = 0]() mutable { return i++; };` at namespace scope is valid.

¶4 The name in a simple-capture must denote a local entity; `this` and `*this` both denote the local entity `*this`. An entity designated by a simple-capture is said to be **explicitly captured** ([[g:explicitly-captured|explicitly captured]]). ¶5 A captured name can't be the same as a parameter or template parameter of the lambda: `[x](int x) {}` is ill-formed.

### Prerequisites: odr-use and odr-usable

The capture rules are built on two concepts from [[basic.def.odr]].

An **odr-use** ([[g:odr-use]]) roughly means using a variable in a way that requires the variable itself to exist: taking its address, binding a reference to it, reading a non-constant value. Reading the value of a constant (`N` in `const int N = 10;` used as an array bound or in arithmetic) is not an odr-use; the compiler just uses its value.

A local entity is **odr-usable** ([[g:odr-usable]]) at a point if no function parameter scope or class scope (e.g. a member function of a local class) intervenes between its declaration and that point, and every intervening lambda captures it. Odr-using a local entity where it is not odr-usable makes the program ill-formed ([[basic.def.odr#10]]). This is the basis for "a lambda must capture an enclosing variable to use it".

### Implicit capture (¶7)

With a capture-default `[=]` or `[&]`, which entities are captured? ¶7 first defines which local entities an expression **potentially references**:

- (7.1) an *id-expression* that names a local entity potentially references it; an *id-expression* that names a non-static member (and doesn't form a pointer to member) potentially references `*this`, even if overload resolution ends up selecting a static member function (Note 3);
- (7.2) `this` potentially references `*this`;
- (7.3) a lambda expression potentially references the entities named by its simple-captures, so that an outer lambda becomes aware of an inner lambda's explicit captures.

Then comes the definition of implicit capture:

!!! std
    If an expression potentially references a local entity within a scope in which it is odr-usable, and the expression would be potentially evaluated if the effect of any enclosing `typeid` expressions were ignored, the entity is said to be *implicitly captured* by each intervening *lambda-expression* with an associated *capture-default* that does not explicitly capture it.

That is: if an expression potentially references a local entity at some point, the entity is odr-usable there, and the expression would be **potentially evaluated** ([[g:potentially-evaluated|potentially evaluated]], not inside an unevaluated operand such as `sizeof` or `decltype`), then each intervening lambda with a capture-default that doesn't explicitly capture the entity **implicitly captures** ([[g:implicitly-captured|implicitly captured]]) it.

Three things about this definition are worth noting.

First, it doesn't require an odr-use. In a generic lambda, whether the same expression is an odr-use may not be known until instantiation selects an overload; but the capture set must be fixed when the lambda is defined, so the standard looks only at syntax. Example 4 in the standard:

```cpp ok
#include <typeinfo>

void f(int, const int (&)[2] = {});   // #1: takes by value
void f(const int&, const int (&)[1]); // #2: takes by reference, will odr-use

void test() {
  const int x = 17;
  auto g = [](auto a) {
    f(x);              // OK: calls #1, not an odr-use, usable without a capture-default
  };
  auto g1 = [=](auto a) {
    f(x);              // OK: calls #1, x is implicitly captured; the implementation may optimize the capture away
  };
  auto g2 = [=](auto a) {
    int selector[sizeof(a) == 1 ? 1 : 2]{};
    f(x, selector);    // OK: captures x, calls #1 or #2 depending on the type of a
  };
  auto g3 = [=](auto a) {
    typeid(a + x);     // captures x whether or not a + x is evaluated
  };
}
```

Second, `typeid` is ignored. Whether `typeid(e)` evaluates `e` depends on whether `e` is an lvalue of polymorphic class type, which in a generic lambda may not be known until instantiation. The standard treats it as evaluated across the board, preferring to capture too much.

Third, the capture set is decided by syntax: even if the expression is in a discarded branch of `if constexpr`, the entity is captured (Note 4):

```cpp ok
template<bool B>
void f(int n) {
  [=](auto a) {
    if constexpr (B && sizeof(a) > 4) {
      (void)n;         // n is captured regardless of B and sizeof(int)
    }
  }(0);
}
```

!!! warning "Implicit capture of this by `[=]` is deprecated {{deprecated}}"
    The last sentence of ¶7 says that implicitly capturing `*this` when the capture-default is `=` is deprecated ([[depr.capture.this]]). In a member function, the `x` in `[=] { x = n; }` is `this->x`; what gets captured is the pointer `this`, and the object itself is not copied. `[=]` suggests that everything is copied, and when the lambda outlives the object, it dangles. Since C++20, write `[=, this]` (explicitly by reference) or `[=, *this]` (copy the whole object). Clang warns about the old form with `-Wdeprecated-this-capture`.

### Being captured means being odr-used (¶8–¶9)

¶8 An entity that is captured (explicitly or implicitly) is odr-used by the lambda expression. Note 5 draws the consequence: explicitly capturing an entity that is not odr-usable at that point makes the program ill-formed.

This is how captures propagate outward through nested lambdas, layer by layer. The first half of Example 6 in the standard:

```cpp error
void f1(int i) {
  int const N = 20;
  auto m1 = [=]{
    int const M = 30;
    auto m2 = [i]{
      int x[N][M];         // OK: N and M are not odr-used
      x[0][0] = i;         // OK: i is explicitly captured by m2 and implicitly captured by m1
    };
  };
  struct s1 {
    int f;
    void work(int n) {
      int m = n*n;
      int j = 40;
      auto m3 = [this,m] {
        auto m4 = [&,j] {  // error: m3 doesn't capture j, so j is not odr-usable here
          int x = n;       // error: likewise, n is blocked by m3
          x += m;          // OK: m is implicitly captured by m4 and explicitly captured by m3
          x += i;          // error: i is blocked by the scopes of local class s1 and member function work
          x += f;          // OK: this is implicitly captured by m4 and explicitly captured by m3
        };
      };
    }
  };
}
```

The `m2` line uses ¶7.3: `m2` explicitly captures `i`, so the lambda expression `m2` itself potentially references `i`, and the enclosing `m1` with `[=]` implicitly captures `i`.

¶9 Note 6 adds that local entities are not odr-usable in default arguments, so a lambda in a default argument can't capture any local entity; it can have init-captures, as long as their initializers don't reference local variables.

### Capture by copy (¶10–¶11)

¶10 An entity is **captured by copy** ([[g:captured-by-copy|captured by copy]]) in two cases: it is implicitly captured with a capture-default of `=` (except `*this`), or it is explicitly captured with a capture that doesn't use `&` and isn't of the form `this`.

For each entity captured by copy, an unnamed non-static data member is declared in the closure type; its type is:

- the referenced type, if the entity is a reference to an object, i.e. the referenced object is copied;
- an lvalue reference to the function type, if the entity is a reference to a function, since functions can't be copied;
- otherwise the type of the entity itself, including `const`.

A member of an anonymous union can't be captured by copy.

!!! pitfall "Capture by copy keeps const, and mutable can't remove it"
    ```cpp
    const std::string s = "x";
    auto l = [s]() mutable { s += "y"; };   // error: the member's type is const std::string
    ```
    `mutable` only makes the call operator non-const; the member's own `const` remains. For a modifiable copy, use the init-capture `[s = s]`: it is deduced as with `auto`, dropping the top-level const.

¶11 In the lambda body, every odr-use of an entity captured by copy is transformed into an access to the corresponding member of the closure. A use that is not an odr-use refers to the original entity, never to the closure member (Note 7).

```cpp ok
void f(const int*);
void g() {
  const int N = 10;
  [=] {
    int arr[N];   // not an odr-use: refers to the outer N, reading only its constant value
    f(&N);        // taking the address is an odr-use: N is captured, &N points to the closure member
  };
}
```

So a lambda with no captures at all can still use a constant's value, but can't take its address or bind a reference to it:

```cpp error
#include <algorithm>

void f(int n) {
  [] { n = 1; };                         // error: n is not captured
  const int N = 10;
  [] { return N; };                      // OK: reading a constant's value is not an odr-use
  [] { return std::max(N, 1); };         // error: max takes const int&, and binding a reference is an odr-use
}
```

### Capture by reference (¶12–¶13)

¶12 An entity that is captured but not by copy is **captured by reference** ([[g:captured-by-reference|captured by reference]]). It is unspecified whether the closure type declares data members for them {{unspec}}; if it does, they must be of literal type, which ensures that lambdas capturing by reference can be used in constant expressions too:

```cpp ok
static_assert([](int n) { return [&n] { return ++n; }(); }(3) == 4);
```

Bit-fields and members of anonymous unions can't be captured by reference, because no reference to them can be formed.

¶13 When a lambda body uses a reference captured by reference, it refers to the object that reference is bound to, not to the reference itself. So whether such a capture is valid depends on that object's lifetime (Note 8):

```cpp ok
auto h(int& r) {
  return [&] {
    ++r;   // still valid after h returns, as long as the object r is bound to is alive
  };
}
```

### Dangling (¶17)

¶17 Note 10: if a non-reference entity is captured by reference and the closure is called after the entity's lifetime has ended, undefined behavior is likely to result. It says "likely" because it is UB only if the nonexistent object is actually accessed ([[basic.life]]).

```cpp run ub
#include <cstdio>
#include <functional>

std::function<int()> make() {
  int local = 42;
  return [&] { return local; };   // captures a local variable by reference
}

int main() {
  auto f = make();
  std::printf("%d\n", f());        // UB: local no longer exists
}
```

In our tests, compiling with `-fsanitize=address` and running with `ASAN_OPTIONS=detect_stack_use_after_return=1`, AddressSanitizer reports `stack-use-after-return`. When the closure is used synchronously within the current scope, `[&]` is safe and efficient; once the closure is returned, stored or handed to another thread, capture only by copy, or capture by reference only objects known to live longer.

### init-capture (¶6)

¶6 An init-capture `[x = e]` behaves as if it declares a variable `auto x = e;` and explicitly captures it; `[&r = e]` as if `auto& r = e;`. It inhabits the lambda's lambda scope ([[basic.scope.lambda]]) and differs from an ordinary variable in two ways: by copy, the variable and the closure member are the same object, with no extra copy or destruction; by reference, the reference variable's lifetime ends when the closure object's lifetime ends.

Note 2 points out that this makes `[x = std::move(x)]` possible: the `x` on the right of the `=` refers to the enclosing variable, because the init-capture's name is not yet visible in its own initializer (unlike an ordinary variable `int x = x;`).

```cpp run ok
#include <cstdio>

int main() {
  int x = 4;
  auto y = [&r = x, x = x + 1]() -> int {   // r refers to the outer x; the inner x is 5
    r += 2;
    return x + 2;
  }();                                      // outer x becomes 6, y is initialized to 7
  std::printf("%d %d\n", x, y);             // 6 7

  auto counter = [i = 0]() mutable -> decltype(i) { return i++; };   // returns int
  counter();
  std::printf("%d\n", counter());           // 1
}
```

`decltype(i)` in the trailing return type finds the init-capture `i` because the lambda scope covers the whole declarator. This rule was established by C++23's [[P2036R3]].

The const rules for init-captures differ from simple captures: `[x]` keeps the const of `x`, `[x = x]` is deduced as with `auto` and drops the top-level const, and `[&x = x]` is deduced as with `auto&` and keeps the const.

### Nested lambdas (¶14)

¶14 When an inner lambda `m2` captures an entity that the immediately enclosing lambda `m1` also captures: if `m1` captures it by copy, `m2` captures the corresponding member of `m1`'s closure (treated as const if `m1` is not `mutable`); if `m1` captures it by reference, `m2` captures the same original entity.

Example 11 in the standard prints `123234`:

```cpp run ok
#include <iostream>

int main() {
  int a = 1, b = 1, c = 1;
  auto m1 = [a, &b, &c]() mutable {
    auto m2 = [a, b, &c]() mutable {
      std::cout << a << b << c;
      a = 4; b = 4; c = 4;
    };
    a = 3; b = 3; c = 3;
    m2();
  };
  a = 2; b = 2; c = 2;
  m1();
  std::cout << a << b << c << '\n';
}
```

Step by step:

1. When `m1` is created, it copies `a` (value 1) and holds the outer `b` and `c` by reference. Then all three outer variables become 2.
2. Calling `m1()` creates `m2` inside it. `m2`'s `a` is copied from `m1`'s member (1); `m1` captures `b` by reference, so `m2` copies the current value of the outer `b` (2); `c` is still the outer `c`.
3. `m1` sets its own `a` and the outer `b` and `c` to 3, then calls `m2()`, which prints `m2`'s `a` (1), `b` (2) and the outer `c` (3), i.e. `123`; it then sets its own copies and the outer `c` to 4.
4. Finally the outer `a` (2), `b` (3) and `c` (4) are printed, i.e. `234`.

### Initialization order (¶15–¶16)

¶15 The order in which closure members are declared is unspecified {{unspec}}, but the members for explicit captures are declared in the order of the capture list. ¶16 When the lambda expression is evaluated, entities captured by copy are used to direct-initialize the corresponding members, and init-captures are initialized by their own initializers, in the order the members are declared. So explicit captures are initialized in the order written and destroyed in reverse order (Note 9).

```cpp ok
#include <utility>
#include <vector>

void f(std::vector<int>&& v) {
  [size = v.size(), own = std::move(v)] {};   // size is initialized first and gets the original size
}
```

### Packs and structured bindings (¶18)

¶18 A simple-capture with `...` (`args...`, `&args...`) is a pack expansion; an init-capture with `...` (`...xs = std::move(args)`) is a pack expansion that declares an init-capture pack {{c++20}}.

```cpp run ok
#include <cstdio>
#include <utility>

template<class... Args> int sum(Args... args) {
  auto l1 = [args...] { return (0 + ... + args); };                 // captures the whole pack by copy
  auto l2 = [...xs = std::move(args)] { return (0 + ... + xs); };   // C++20: init-capture pack
  auto l3 = [&...rs = args] { return (0 + ... + rs); };             // C++20: by reference
  return l1() + l2() + l3();
}

int main() { std::printf("%d\n", sum(1, 2, 3)); }   // 18
```

The position of `...` follows a pattern: in a simple-capture it goes after (`args...`), like an ordinary pack expansion; in an init-capture it goes before (`...xs = e`), like declaring a new pack (`class... Ts`).

Structured bindings are local entities and, since C++20, can be captured by copy or by reference like variables. A structured binding that refers to a bit-field can't be captured by reference (¶12).

```cpp ok
#include <utility>

void sb() {
  auto [p, q] = std::pair{1, 2};
  auto l  = [p, &q] { return p + q; };   // OK since C++20
  auto l2 = [=] { return p; };           // implicit capture works too
}
```

### Contract assertions can't cause captures [expr.prim.lambda.closure] {{c++26}}

¶10 If all potential references to an implicitly captured local entity appear in contract assertions of the call operator (`pre`, `post`) or in `contract_assert`s in the lambda body, the program is ill-formed. Note 4 explains the purpose: adding contract assertions to an existing program shouldn't cause extra captures; otherwise adding an assertion could change the closure's size and layout.

```cpp
void test() {
  int i = 1;
  auto f2 = [=] pre(i > 0) {};   // error: can't implicitly capture i here
  auto f3 = [i] pre(i > 0) {};   // OK: explicit capture
  auto f5 = [=] {
    contract_assert(i > 0);      // OK: i is also referenced below
    (void)i;
  };
}
```

Clang 23 doesn't support the contract syntax yet, so this code has no verdict mark.

## Conversion to a function pointer [expr.prim.lambda.closure]

¶11 If a lambda is not generic, has no captures and no explicit object parameter, and its constraints (if any) are satisfied, its closure type has a conversion function to a pointer to function. The function pointer has the same parameters and return type as the call operator; if the call operator is non-throwing, the conversion is to a `noexcept` function pointer.

If the call operator is a static member function, the conversion yields its address. Otherwise it yields the address of some function F, and calling F has the same effect as calling the call operator on a default-constructed closure object.

Only captureless lambdas convert, because a function pointer is just an address, with nowhere to store captured state.

```cpp run ok
int (*fp)(int) = [](int i) { return i; };     // implicit conversion
void (*fnp)() noexcept = []() noexcept {};    // converts to a noexcept function pointer
auto p = +[](int i) { return i * 2; };        // unary + triggers the conversion; p has type int(*)(int)

int main() { return fp(0) + p(0); }
```

¶12 A captureless generic lambda has a conversion function template. It deduces template arguments from the target function pointer type, and then uses the deduced specialization to determine the return type (Note 5, ¶13). Example 7 in the standard shows the limits of this deduction:

```cpp error
void f1(int (*)(int))   { }
void f2(char (*)(int))  { }
void g(int (*)(int))    { }     // #1
void g(char (*)(char))  { }     // #2
void h(int (*)(int))    { }     // #3
void h(char (*)(int))   { }     // #4

auto glambda = [](auto a) { return a; };
void test() {
  f1(glambda);   // OK: a is deduced as int, returns int
  f2(glambda);   // error: with a deduced as int it returns int, not char
  g(glambda);    // error: both #1 and #2 are viable, ambiguous
  h(glambda);    // OK: only #3 is viable
}
int& (*fpi)(int*) = [](auto* a) -> auto& { return *a; };   // OK
```

¶14 The function obtained by converting a generic lambda follows the same rules as ¶11: if static, it points to the specialization of the call operator template, otherwise to a forwarding function. This triggers instantiation of the lambda body (Note 6).

¶15 The conversion function is public, constexpr, non-virtual, non-explicit, const, and has a non-throwing exception specification. The conversion itself can always be performed in a constant expression, but whether the resulting function pointer can be called in a constant expression depends on whether the call operator is a constexpr function:

```cpp error
auto Fwd = [](int (*fp)(int), auto a) { return fp(a); };
auto C  = [](auto a) { return a; };
static_assert(Fwd(C, 3) == 3);    // OK

auto NC = [](auto a) { static int s; return a; };   // has a static local variable, can't be constexpr
static_assert(Fwd(NC, 3) == 3);   // error: not a constant expression
```

## Special member functions [expr.prim.lambda.closure]

¶17 The special member functions of a closure type:

| | With captures | Without captures |
|---|---|---|
| Default constructor | None | Defaulted {{c++20}} |
| Copy and move constructors | Defaulted | Defaulted |
| Copy assignment operator | Deleted | Defaulted {{c++20}} |
| Move assignment operator | Not declared; assignment selects the deleted copy assignment | Defaulted {{c++20}} |

These functions are implicitly defined as usual and may therefore be defined as deleted (Note 7). For example, if a `std::unique_ptr` is captured by copy, the copy constructor is deleted and the closure can only be moved. ¶18 The closure type has an implicitly-declared destructor.

Before C++20, no closure type could be default-constructed or assigned. C++20 allowed this for captureless lambdas, and together with lambdas being allowed in `decltype`, a lambda's type can be used directly as a comparator or deleter:

```cpp run ok
#include <cstdio>
#include <memory>
#include <set>

int main() {
  using Cmp = decltype([](int a, int b) { return a > b; });
  std::set<int, Cmp> s{1, 3, 2};          // set default-constructs a Cmp
  std::printf("%d\n", *s.begin());        // 3

  std::unique_ptr<int, decltype([](int* p) { delete p; })> up(new int(1));
}
```

## Other properties of closure types [expr.prim.lambda.closure]

¶4 A closure type is not an aggregate, so you can't fake a closure object with brace initialization. It is not final, so you can derive from a closure type; the common `overloaded` idiom relies on this. It is a **structural type** ([[g:structural-type|structural type]], [[temp.param]]) if and only if the lambda has no captures, in which case it can be used as a non-type template argument.

!!! std
    The closure type is not an aggregate type and is not final; it is a structural type if and only if the lambda has no *lambda-capture*.

```cpp run ok
#include <cstdio>
#include <string>
#include <variant>

template<class... Fs> struct overloaded : Fs... { using Fs::operator()...; };

template<auto F> int call() { return F(); }   // captureless lambda as a non-type template argument

int main() {
  std::variant<int, std::string> v = std::string("hi");
  std::visit(overloaded{[](int i) { std::printf("int %d\n", i); },
                        [](const std::string& s) { std::printf("str %s\n", s.c_str()); }}, v);
  std::printf("%d\n", call<[] { return 42; }>());
}
```

The second half of ¶4 allows implementations to define the closure type differently from the description above, as long as observable behavior is unchanged, except that three things may differ: the size and alignment of the closure type, whether it is trivially copyable, and whether it is a standard-layout class. An implementation may not add members of rvalue reference type to a closure type. So the `sizeof` of a closure and the result of `std::is_trivially_copyable_v` are not guaranteed to agree between compilers.

<details class="fine" markdown="1"><summary>Remaining wording</summary>

¶3 ([expr.prim.lambda.general]) A *requires-clause* can end with an attribute, which conflicts with attributes before the lambda declarator, e.g. `[]<class T> requires T::operator int [[attr]] (int) {}`. The standard says such attributes always belong to the lambda. Note 2 points out that such an ambiguous form has no valid meaning anyway, because the type of the constraint expression wouldn't be `bool`.

¶2 ([expr.prim.lambda.closure]) The closure type is incomplete until the end of the lambda's body.

¶8 ([expr.prim.lambda.closure]) is a long example about constexpr lambdas; the key points are covered above.

¶9 ([expr.prim.lambda.closure]) Note 3 says the call operator can be constrained with type constraints, a *requires-clause* after `<…>`, and a trailing *requires-clause*, the same as an ordinary function template ([[temp.constr.decl]]).

¶19 ([expr.prim.lambda.closure]) Members of a closure type can't be explicitly instantiated or explicitly specialized, and can't be named in a friend declaration.

</details>

## Implementation view

!!! impl
    - Mainstream implementations implement captures by copy as ordinary data members, and usually store one pointer per capture by reference. On Clang 23, a closure capturing two `int`s by reference has `sizeof` 16; a captureless closure is an empty class with `sizeof` 1. ¶4 and ¶12 also allow other representations, such as storing only a stack frame pointer.
    - The Itanium C++ ABI specifies name mangling for lambdas, so that a lambda appearing in a place that can be defined in multiple translation units (an inline function, a class definition, etc.) gets the same closure type in every translation unit, which is a prerequisite for satisfying the ODR ([[basic.def.odr]]).
    - For a non-static captureless lambda, the compiler generates a static forwarding function that constructs an empty closure object and calls `operator()`; that is the F in ¶11.
    - Clang's `-Wunused-lambda-capture` flags entities that are explicitly captured but never odr-used, such as constants.

## History and evolution

!!! history
    - C++11 introduced lambdas. Return type deduction was limited to a single `return` statement, and only automatic variables and `this` could be captured.
    - C++14: generic lambdas (`auto` parameters); init-captures, for capturing move-only objects; return type deduction unified with ordinary functions.
    - C++17: constexpr lambdas and implicit constexpr ([[P0170R1]]); `[*this]` to capture the whole object by copy ([[P0018R3]]).
    - C++20: template parameter lists ([[P0428R2]]); captureless lambdas default-constructible and assignable ([[P0624R2]]); lambdas in unevaluated operands ([[P0315R4]]); init-capture packs ([[P0780R2]]); `[=, this]` and deprecation of implicit `this` capture by `[=]` ([[P0806R2]]); capturing structured bindings ([[P1091R3]], [[P1381R1]]); implicit capture switched to a syntax-based rule ([[P0588R1]]), whereas the earlier rule was based on odr-use with complicated special rules for generic lambdas.
    - C++23: relaxed rules for omitting `()` ([[P1102R2]]); `static` lambdas ([[P1169R4]]); explicit object parameters ([[P0847R7]]); attributes before the declarator ([[P2173R1]]); captured names visible in the trailing return type ([[P2036R3]]).
    - C++26: lambdas can have contracts, and contract assertions must not cause implicit captures.

## Common mistakes

!!! pitfall "Every lambda is a different type"
    `auto g = cond ? [k] { return 1; } : [k] { return 2; };` is ill-formed: the two branches are different classes, neither convertible to the other. Without the captures, `cond ? [] { return 1; } : [] { return 2; }` is well-formed: when the operands are of different class types, [[expr.cond]] tries conversions, and both captureless closures convert to `int(*)()`, so the result type is that function pointer.

!!! pitfall "Constants needn't be captured, unless you take their address or bind a reference"
    `const int N = 10; [] { return N * 2; }` is fine; `[] { return &N; }` and `[] { return std::max(N, 1); }` are both ill-formed, the latter because `std::max` takes its arguments by `const T&`.

## Questions

!!! question "Question 1"
    Is the following lambda well-formed? What is the `sizeof` of the closure object on Clang?
    ```cpp
    void f() {
      const int N = 10;
      auto l = [=] { return N + 1; };
    }
    ```

<details markdown="1">
<summary>Answer</summary>

It is well-formed. `N` is potentially referenced and potentially evaluated in the lambda body and is odr-usable there, so by [[expr.prim.lambda.capture#7]] it is implicitly captured; implicit capture doesn't require an odr-use. But `N + 1` only reads the constant's value and is not an odr-use, so by [[expr.prim.lambda.capture#11]] it refers to the outer `N`, not the closure member, and the implementation can optimize the capture away. On Clang 23, `sizeof(l)` is 1. The standard doesn't guarantee this size ([[expr.prim.lambda.closure#4]]).
</details>

!!! question "Question 2"
    What does the following code print?
    ```cpp
    int x = 1;
    auto l = [x]() mutable { return ++x; };
    auto l2 = l;
    l(); l();
    std::cout << l() << l2() << x;
    ```

<details markdown="1">
<summary>Answer</summary>

It prints `421`. `l` is called three times; its member becomes 2, 3, 4 in turn, and the third call returns 4. `l2` was copied before any call, so its member is still 1, and calling it returns 2. The outer `x` was never modified and is 1. Since C++17 the left operand of `<<` is evaluated before the right, so the order is determined. A closure object is just an ordinary object; copying it copies all captured state.
</details>
