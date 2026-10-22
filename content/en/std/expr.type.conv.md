---
title: Functional-notation casts
summary: "What T(x), T(a, b), T(), T{...}, auto(x) and a class template name with an initializer mean: with a single parenthesized argument T(x) is exactly the C-style cast (T)x, and the other forms direct-initialize a T from the initializer."
updated: 2026-10-19
---

!!! tldr
    - With a single parenthesized argument, `T(x)` is exactly equivalent to the C-style cast `(T)x` and can silently perform a `const_cast` or `reinterpret_cast`.
    - The other forms (multiple arguments, empty parentheses, braces) yield a prvalue of `T` direct-initialized from the initializer; the braced forms forbid narrowing.
    - The type part can only be a single type name; `unsigned long(x)` and `int*(p)` can't be written.
    - A class template name first goes through class template argument deduction, `auto` is first deduced by the `auto` rules, and only then are the rules above applied.
    - C++23's `auto(x)` yields a prvalue copy of the decayed `x`, commonly used to keep a reference from being changed by a later operation.

```cpp run title="functional-is-c-cast.cpp" ok
#include <cstdint>

struct B {};
struct D : private B {};   // private inheritance

int main() {
    const int c = 42;
    using IP = int*;
    using UIP = std::uintptr_t;
    using BP = B*;

    IP p = IP(&c);     // equivalent to (int*)&c: casts away const
    UIP u = UIP(&c);   // equivalent to (std::uintptr_t)&c: reinterpret_cast
    D d;
    BP bp = BP(&d);    // equivalent to (B*)&d: ignores private inheritance
    (void)p; (void)u; (void)bp;
    // *p = 1;         // if executed: UB, modifying a const object
}
```

`int(3.7)`, `std::string("abc")`, `Point{1, 2}`, `std::vector{1, 2, 3}` and `auto(x)` are syntactically the same kind of expression: an **explicit type conversion (functional notation)**. It looks like a constructor call, but the example above shows it isn't always that gentle: none of the three conversions gets any warning under `-Wall -Wextra -pedantic`.

## Which types can be written

The type part of a functional cast can only be a *simple-type-specifier* (a single type name, `int`, `auto`, `decltype(e)`, a template name, etc.) or a *typename-specifier* (`typename T::type`); see the grammar in [[expr.post]]. Types made of several keywords and types with declarators are not allowed:

```cpp title="simple-type-only.cpp" error
int x = 1;
unsigned long a = unsigned long(x);   // error: not a single type specifier
int* p = int*(nullptr);               // error: can't have a declarator
using UL = unsigned long;
UL b = UL(x);                         // OK: an alias is a single type name
```

So for such types, either introduce an alias first or use `static_cast<unsigned long>(x)` instead.

## First determine the type T (¶1)

¶1 A type specifier followed by an initializer (an optional parenthesized expression list or a braced list) constructs a value of the specified type from it. Before anything else, the type `T` is determined:

1. If a class template name was written (a placeholder for a deduced class type, such as `std::pair`), it is replaced by the return type of the function selected by class template argument deduction (CTAD, [[over.match.class.deduct]]).
2. Otherwise, if the type contains `auto`, it is replaced by the type deduced by [[dcl.type.auto.deduct]].

```cpp run title="deduce-T.cpp" ok
#include <type_traits>
#include <utility>
#include <vector>

int x = 1;
int arr[3];
std::vector<int> v;

static_assert(std::is_same_v<decltype(std::pair(1, 2.0)), std::pair<int, double>>);
static_assert(std::is_same_v<decltype(std::vector{1, 2}), std::vector<int>>);
static_assert(std::is_same_v<decltype(std::vector(v)), std::vector<int>>);  // a copy, not vector<vector<int>>
static_assert(std::is_same_v<decltype(auto(x)), int>);       // C++23
static_assert(std::is_same_v<decltype(auto(arr)), int*>);    // the array decays to a pointer
static_assert(std::is_same_v<decltype(auto{arr}), int*>);

int main() {}
```

The deduction for `auto(x)` is the same as for the declaration `auto v(x);`, so decay happens: arrays become pointers, functions become function pointers, references and top-level cv are dropped. The type part can only be `auto` itself; `decltype(auto)(x)` and `auto&(x)` are both ill-formed.

## Four cases (¶1.1–¶1.4)

Once `T` is determined, the form of the initializer is matched in order:

| Item | Condition | Meaning | Value category |
|---|---|---|---|
| ¶1.1 | Exactly one expression in parentheses | Equivalent to the C-style cast `(T)e` ([[expr.cast]]) | Determined by `(T)e` |
| ¶1.2 | `T` is cv `void` | The initializer must be `()` or `{}` (after pack expansion); no initialization is performed | A prvalue of `void` |
| ¶1.3 | `T` is a reference type | As if direct-initializing an invented variable `T t` from the initializer, with `t` as the result | lvalue for an lvalue reference or rvalue reference to function, xvalue for an rvalue reference to object |
| ¶1.4 | Otherwise | A prvalue of `T` whose result object is direct-initialized from the initializer ([[dcl.init]]) | prvalue |

There is one more restriction: if the initializer is parenthesized, `T` shall not be an array type.

### A single parenthesized argument is a C-style cast (¶1.1)

!!! std
    If the initializer is a parenthesized single expression, the type conversion expression is equivalent to the corresponding cast expression.

The equivalence here has no reservations. A C-style cast tries `const_cast`, `static_cast`, `static_cast` plus `const_cast`, `reinterpret_cast`, and `reinterpret_cast` plus `const_cast` in turn, and its `static_cast` can even ignore access control to convert to a private base class ([[expr.cast#4]]). The three lines in the example at the top each use one of these abilities.

For scalar and pointer types, a functional cast is no safer than a C-style cast. The safe single-argument forms are `static_cast<T>(x)`, or braces `T{x}`, which also forbid narrowing.

For a class type `T`, `T(x)` goes through the C-style cast to `static_cast`, which by [[expr.static.cast#5]] becomes the direct-initialization `T t(x)`, i.e. a constructor call. So the everyday `std::string(p)` is fine; the ones to watch are pointer, reference and arithmetic types.

Functional casts predate the named casts. C++ originally introduced `T(x)` to give built-in and user-defined types a uniform construction syntax, and the only thing it could align with at the time was the C-style cast; the named casts came later, when the meaning of `T(x)` could no longer be changed.

### `void()` (¶1.2)

`void()` and `void{}` are prvalues of type `void` that do nothing; they are used mainly in generic code:

```cpp run title="void-expr.cpp" ok
template<class... T>
void ignore(T... t) {
    (void(t), ...);       // each item is ¶1.1: (void)t
}

template<class F>
auto call(F f) -> decltype(f(), void()) {   // checks that f() is valid; the return type is always void
    f();
}

int main() {
    ignore();
    ignore(1, 2.0);
    call([] { return 42; });
}
```

The "after pack expansion" qualification is about `void(t...)`: with an empty pack the initializer is `()`, which is valid; with one element it is a single expression, `(void)t` by ¶1.1; with two or more elements it is ill-formed.

### Reference types (¶1.3)

When `T` is a reference (which can only be written through an alias or `decltype`), a single parenthesized argument is still handled by ¶1.1; the other forms are as if declaring `T t(initializer);` and then using `t`:

```cpp run title="ref-conv.cpp" ok
#include <type_traits>

int x = 1;
using R = int&;
using RR = int&&;
using CR = const int&;

static_assert(std::is_same_v<decltype(R(x)), int&>);          // ¶1.1: (int&)x
static_assert(std::is_same_v<decltype(RR(x)), int&&>);        // ¶1.1: (int&&)x
static_assert(std::is_same_v<decltype(R{x}), int&>);          // ¶1.3: int& t{x};
static_assert(std::is_same_v<decltype(CR{1}), const int&>);   // ¶1.3: binds to a temporary

int main() {}
```

`CR{1}` binds a temporary. The standard doesn't say what the lifetime of the invented variable `t` is, so how long this temporary lives is unclear. The safe practice is to use the result only within its full-expression.

### Direct-initializing a prvalue (¶1.4)

All remaining cases yield a prvalue of `T` whose result object is direct-initialized. Since C++17 a prvalue is not itself an object; the result object is provided by the context ([[basic.lval]]): in `T t = T(a, b);` the result object is `t`, with no temporary and no need for a move constructor.

| Form | Initialization | Effect |
|---|---|---|
| `T()` | [[g:value-initialization|Value-initialization]] | Scalars become zero; a user-provided default constructor is called if there is one |
| `T{}` | List-initialization | Value-initialization, or aggregate initialization for aggregates |
| `T(a, b)` | Direct-initialization | Calls a constructor; since C++20 aggregates can also use parentheses ([[P0960R3]]) |
| `T{a, b}` | Direct-list-initialization | Prefers `initializer_list` constructors; forbids narrowing |

```cpp run title="value-init.cpp" ok
#include <string>

struct Agg { int a, b; };
struct Ctor { int v; Ctor(int a, int b) : v(a + b) {} };

int main() {
    int i = int();             // 0
    int j = int{};             // 0
    Agg g1 = Agg(1, 2);        // C++20: parenthesized aggregate initialization
    Agg g2 = Agg{1, 2};        // aggregate initialization
    Ctor c = Ctor(1, 2);       // constructor
    std::string s = std::string(3, 'x');   // "xxx"
    std::string t = std::string{3, 'x'};   // initializer_list: two characters, '\3' and 'x'
    return (i + j + g1.a + g2.b + c.v == 6 && s == "xxx" && t.size() == 2) ? 0 : 1;
}
```

`int(3.5)` falls under ¶1.1, a C-style cast, and truncates to 3; `int{3.5}` falls under ¶1.4, list-initialization, and [[g:narrowing-conversion|narrowing]] makes it ill-formed.

<div class="compare" markdown="1">

```cpp run ok
int a = int(3.5);   // (int)3.5, value 3
long long big = 1LL << 40;
int b = int(big);   // truncates, no error
int main() { return a + b; }
```

```cpp error
int c = int{3.5};   // error: narrowing
long long big = 1LL << 40;
int d = int{big};   // error: narrowing
using A = int[3];
auto e = A(1, 2, 3);  // error: with parentheses
                      // T can't be an array
```

</div>

Arrays can only use braces: `A{1, 2, 3}` is valid and gives an array prvalue. But `auto v = A{1, 2, 3};` deduces `v` as `int*`, pointing to a temporary array destroyed at the end of the full-expression, so `v` dangles; Clang gives a `-Wdangling` warning.

## `auto(x)`: taking a copy (C++23)

[[P0849R8]] allows `auto` as the type of a functional cast. `auto(x)` deduces a type by the `auto` rules and copies `x` into a prvalue, which is what the standard library's specifications often call decay-copy. Example 1 in the standard:

```cpp run title="auto-copy.cpp" ok
struct A {};
void f(A&) {}     // #1
void f(A&&) {}    // #2
A& g() { static A a; return a; }

int main() {
    f(g());          // calls #1: g() is an lvalue
    f(A(g()));       // calls #2: A(g()) is a prvalue, but the type name has to be written
    f(auto(g()));    // calls #2: no type name needed
}
```

Before C++23, getting a copy meant writing out the type (`std::decay_t<decltype(x)>(x)`) or introducing a named variable. A typical use:

```cpp run title="auto-copy-erase.cpp" ok
#include <vector>

int main() {
    std::vector<int> v{1, 2, 1, 3, 1};
    // std::erase(v, v.front());     // dangerous: front() is a reference, and the element it refers to gets overwritten during removal
    std::erase(v, auto(v.front()));  // copy the value 1 first, then remove
    return v == std::vector<int>{2, 3} ? 0 : 1;
}
```

`auto{x}` deduces the same type as `auto(x)`, except that the braces must contain exactly one element. `auto{1, 2}`, `auto()` and `auto{}` are all ill-formed; the last two have nothing to deduce from.

After `T` is deduced, `auto(x)` is, as usual, equivalent to `(T)x` by ¶1.1. Since `T` is just the decayed type of `x`, this conversion can only be a `static_cast` or a copy/move construction of a class type; it never becomes a `reinterpret_cast`.

## Class template name with an initializer

When a class template name is followed by an initializer, CTAD first determines `T` ([[P0091R3]]), and only then is it dispatched by ¶1.1–¶1.4. That is why `std::pair(1, 2.0)` and `std::lock_guard(m)` can omit the template arguments. In `std::vector(v)`, where `v` is a `std::vector<int>`, CTAD selects the copy deduction candidate and gives `std::vector<int>`; then by ¶1.1 it is equivalent to `(std::vector<int>)v`, i.e. copy construction.

## Ambiguity with declarations

When `T(x);` stands alone as a statement, [[stmt.ambig]] says it is treated as a declaration if it can be one. So `std::lock_guard<std::mutex>(m);` declares a `lock_guard` variable named `m` rather than locking the mutex `m`: it either fails to compile or means something entirely different. This rule is not in this subclause, but it is the most common surprise when using functional casts.

## History and evolution

!!! history
    - C++98: `T(x)` is equivalent to `(T)x`; `T()` initializes to a zero value (called value-initialization since C++03); `T(a, b)` calls a constructor.
    - C++11: braced forms `T{...}`; list-initialization forbids narrowing.
    - C++17: class template argument deduction ([[P0091R3]]); prvalues directly initialize the final object, no longer going through a temporary.
    - C++20: parenthesized aggregate initialization ([[P0960R3]]).
    - C++23: `auto(x)` and `auto{x}` ([[P0849R8]]).

## Common misconceptions

!!! pitfall "`T(x)` is always a constructor call"
    For pointer and arithmetic types it is a C-style cast. `IntPtr(&const_obj)`, `Handle(pointer)` and `uintptr_t(p)` can all silently perform a `const_cast` or `reinterpret_cast`. In code review, a single-argument functional cast to a scalar or pointer type should be treated the same as a C-style cast.

!!! pitfall "`T(a)` and `T{a}` are just different spellings"
    They can select different constructors: `std::vector<int>(3)` is three zeros, `std::vector<int>{3}` is one element 3; `std::string(3, 'x')` and `std::string{3, 'x'}` also differ.

!!! pitfall "`auto(x)` is cheap"
    For a class type, `auto(v)` copies the whole object, e.g. an entire `std::vector`. Its value is in stating the intent clearly, not in being cheap.

## Questions

!!! question "Question 1"
    Given `const char* p = "abc";`, which of `std::uintptr_t(p)`, `std::uintptr_t{p}` and `static_cast<std::uintptr_t>(p)` are valid?

<details markdown="1">
<summary>Answer</summary>

Only `std::uintptr_t(p)` is valid: by ¶1.1 it is equivalent to `(std::uintptr_t)p`, which ends up as a `reinterpret_cast`. `std::uintptr_t{p}` is list-initialization by ¶1.4, and a pointer can't be implicitly converted to an integer, so it is ill-formed. `static_cast` can't convert a pointer to an integer ([[expr.static.cast]]), so that is ill-formed too. The most harmless-looking form is the only one that compiles.
</details>

!!! question "Question 2"
    Given `template<class... T> void h(T... t) { int(t...); }`, what happens with `h()`, `h(1)` and `h(1, 2)`?

<details markdown="1">
<summary>Answer</summary>

`h()`: the pack is empty, giving `int()`, value-initialization by ¶1.4; valid. `h(1)`: a single expression, `(int)1` by ¶1.1; valid. `h(1, 2)`: by ¶1.4 an `int` would have to be direct-initialized from two initializers, but a scalar can have only one; ill-formed.
</details>

!!! question "Question 3"
    In `using A = int[2]; auto&& r = A{1, 2};`, what is the type of `r`? How long does the temporary array live? How does this differ from `auto v = A{1, 2};`?

<details markdown="1">
<summary>Answer</summary>

`A{1, 2}` is a prvalue of `int[2]`. Deduction for `auto&&` doesn't decay, so `r` has type `int(&&)[2]`; the temporary array is materialized and bound to the reference, and its lifetime is extended to that of `r` ([[class.temporary]]), so this is safe. In `auto v = A{1, 2};`, deduction decays the array to a pointer, `v` is `int*`, the temporary array is destroyed at the end of the full-expression, and `v` dangles.
</details>
