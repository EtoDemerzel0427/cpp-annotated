---
title: Placeholder type specifiers
summary: "How auto, decltype(auto) and Concept auto deduce a type and where they may appear; the rules for function return type deduction: multiple returns, recursion, when deduction happens in templates, and redeclarations."
updated: 2026-10-19
---

!!! tldr
    - `auto` deduction is template argument deduction: the type of `x` in `const auto& x = e;` equals the parameter type when calling `template<class U> void f(const U&)`. The only difference is that `auto x = {1, 2};` deduces `std::initializer_list<int>`.
    - `decltype(auto)` deduces by the rules of `decltype`, so it keeps references, and parentheses change the result.
    - Multiple returns in a function must deduce exactly the same type; after the first return, the function can call itself recursively.
    - Return type deduction in templates instantiates the function body, and errors there are hard errors that don't trigger SFINAE.
    - Placeholder types can only appear where the standard explicitly allows them: variables, return types, function and lambda parameters, template parameters, `new auto`, `auto(x)`; anywhere else is ill-formed.

A **placeholder type** is a specifier that holds a place and is later replaced by a concrete type, usually deduced from an initializer. It has two forms, each optionally preceded by a concept as a constraint:

```text
placeholder-type-specifier:
    type-constraint(opt) auto
    type-constraint(opt) decltype ( auto )
```

[dcl.type.auto.deduct] specifies how deduction works; [dcl.spec.auto.general] specifies where they can be written. A class template name without template arguments (CTAD) is another kind of placeholder; see [[dcl.type.class.deduct]].

## How auto deduces [dcl.type.auto.deduct]

```cpp run ok
#include <type_traits>
template<class A, class B> constexpr bool same = std::is_same_v<A, B>;
int i = 0;
const int ci = 0;
const int carr[3] = {1, 2, 3};
int f(int);

auto a1 = ci;    static_assert(same<decltype(a1), int>);             // top-level const dropped
auto& a2 = ci;   static_assert(same<decltype(a2), const int&>);      // a reference keeps const
auto a3 = carr;  static_assert(same<decltype(a3), const int*>);      // array decays
auto& a4 = carr; static_assert(same<decltype(a4), const int(&)[3]>); // a reference doesn't decay
auto a5 = f;     static_assert(same<decltype(a5), int(*)(int)>);     // function decays to pointer
auto&& a6 = i;   static_assert(same<decltype(a6), int&>);            // lvalue → int&
auto&& a7 = 1;   static_assert(same<decltype(a7), int&&>);           // rvalue → int&&
int main() {}
```

These rules match function template argument deduction exactly, because that is how the standard defines `auto`. ¶1 calls the process of replacing a type containing a placeholder with the deduced type **placeholder type deduction** ([[g:placeholder-type-deduction]]).

### What is deduced, and from what (¶2)

¶2 first determines T, the type containing the placeholder, and E, the initializer-clause used for deduction:

| Context | T | E |
|---|---|---|
| ¶2.1 return statement | The declared return type of the function | The operand of the return; `void()` if there is no operand; `(X)` if the operand is a comma expression X; ill-formed for a braced list |
| ¶2.2 variable | The declared type of the variable | The `e` in `= e`, `{ e }`, `( e )`; only a single expression is allowed inside braces or parentheses |
| ¶2.3 `auto(…)`, `auto{…}` | `auto` | The single expression inside |
| ¶2.4 constant template parameter | The declared type of the template parameter | The corresponding template argument |

T can't be an array type. If E has type `void` (a return with no operand, or returning a `void` expression), T can only be `decltype(auto)` or `cv auto`, not `auto&`, `auto*` and the like. The comma expression gets wrapped in parentheses only because it can't serve directly as an initializer-clause; the meaning is unchanged.

```cpp error
#include <initializer_list>
auto f() { return {1, 2}; }    // error: return can't deduce from a braced list
auto x3{ 1, 2 };               // error: only one element allowed
auto v[] = { 1, 2 };           // error: T can't be an array
auto& g() { return void(); }   // error: E is void
```

### Deduction as for template arguments (¶3)

¶3 For the `auto` form (possibly constrained), deduction has three steps:

1. Replace the `auto` in T with a new invented type template parameter `U` to get P. If the initialization is copy-list-initialization (`= { … }`), replace it with `std::initializer_list<U>` instead; `std::initializer_list` must have been declared (you need to include `<initializer_list>`).
2. Treat P as the parameter type of a function template and E as the argument, and deduce `U` by the rules for a function call ([[temp.deduct.call]]). If deduction fails, the declaration is ill-formed.
3. Substitute `U` back into P to get the final type.

Example 2 is the most direct illustration of this rule: the type of `i` in `const auto& i = expr;` is the type of `u` in the call `f(expr)` of `template<class U> void f(const U& u);`.

There is also a corner-case rule in the middle of ¶3: if E is a value synthesized for a constant template parameter of type `decltype(auto)` during partial ordering of function templates ([[temp.func.order]]), the declaration is ill-formed.

### Braces: the only difference from template deduction

Template argument deduction can deduce nothing from `{1, 2}`, but `auto` can:

```cpp run ok
#include <initializer_list>
#include <type_traits>
auto x1 = { 1, 2 };   // std::initializer_list<int>
auto x4 = { 3 };      // std::initializer_list<int>: = {…} is always initializer_list
auto x5{ 3 };         // int: direct-list-initialization deduces from the single element
static_assert(std::is_same_v<decltype(x1), std::initializer_list<int>>);
static_assert(std::is_same_v<decltype(x4), std::initializer_list<int>>);
static_assert(std::is_same_v<decltype(x5), int>);
int main() {}
```

```cpp error
#include <initializer_list>
auto x2 = { 1, 2.0 };   // error: U is both int and double
auto x3{ 1, 2 };        // error: direct-list-initialization allows only one element
```

!!! history "`auto x{3};` used to be initializer_list"
    In C++11, `auto x{3};` deduced `std::initializer_list<int>`, which almost always surprised people. [[N3922]] changed it to today's rule: direct-list-initialization allows only one element and deduces its type; `= {…}` still deduces initializer_list. The change was applied to C++14 as a defect report, and compilers usually apply the new rule in C++11 mode as well.

### decltype(auto): deduction by decltype (¶4)

¶4 For the `decltype(auto)` form, T must be the placeholder alone; it can't be written as `decltype(auto)*` or `const decltype(auto)&`. The deduced type is the type obtained by using E as the operand of `decltype` ([[dcl.type.decltype]]).

```cpp run ok
#include <type_traits>
template<class A, class B> constexpr bool same = std::is_same_v<A, B>;
int i;
int&& f();
auto           x4a = (i);   static_assert(same<decltype(x4a), int>);
decltype(auto) x4d = (i);   static_assert(same<decltype(x4d), int&>);   // parentheses
auto           x5a = f();   static_assert(same<decltype(x5a), int>);
decltype(auto) x5d = f();   static_assert(same<decltype(x5d), int&&>);
auto f2(int x) -> decltype(auto) { return (x); }   // dangling reference; Clang warns
static_assert(same<decltype(f2(0)), int&&>);
int main() {}
```

The return type of `f2` is `int&&`: since C++23 ([[P2266]]), an expression naming a local variable or parameter in a return statement is an xvalue ([[expr.prim.id.unqual]]), parenthesized or not. In C++20 it deduces `int&`. Either way it returns a dangling reference.

```cpp error
#include <initializer_list>
int i;
decltype(auto) x6d = { 1, 2 };   // error: { 1, 2 } is not an expression
decltype(auto)*x7d = &i;         // error: not decltype(auto) alone
```

!!! lawyer "f1 in the standard's Example 3 is ill-formed in C++23"
    The same example has another line whose comment says the return type is `int&`:

    ```cpp
    auto f1(int x) -> decltype((x)) { return (x); }
    ```

    The return type is indeed `int&`; the `(x)` in `decltype((x))` is just an ordinary lvalue. But `return (x);` in the body is an xvalue since C++23, and `int&` can't bind to it, so this definition is ill-formed. Clang 23 reports "non-const lvalue reference to type 'int' cannot bind to a temporary of type 'int'". The example only comments on the return type and doesn't mention this.

### Constrained placeholders (¶5)

¶5 If the placeholder has a concept constraint, the deduced type must satisfy its **immediately-declared constraint** ([[temp.param]]): the deduced type as the concept's first argument, followed by any arguments written explicitly.

```cpp error
#include <concepts>
std::integral auto a = 1;                 // OK
std::integral auto b = 1.0;               // error: std::integral<double> is not satisfied
std::convertible_to<long> auto c = 'x';   // OK: checks std::convertible_to<char, long>
```

## Where placeholder types can appear [dcl.spec.auto.general]

¶1 A placeholder type stands for a type to be substituted later. These are all the permitted positions:

| Position | Meaning | ¶ |
|---|---|---|
| Variable `auto x = e;` | Deduced from the initializer | 5 |
| Return type `auto f() { return e; }` | Deduced from return statements | 4 |
| `auto f() -> int` | Just syntax; the return type follows `->` | 3 |
| Parameter `void f(auto x)`, `[](auto x) {}` | The function becomes a template, deduced at each call | 2 |
| Template parameter `template<auto N>` | The type of a constant parameter is deduced from the template argument | 2 |
| `new auto(e)` | The allocated type is deduced from the initializer | 6 |
| `auto(e)`, `auto{e}` | Decay-copy | 7 |
| Structured binding `auto [a, b] = e;` | Deduces the type of the hidden variable | 5 |

¶8 Using a placeholder type anywhere not explicitly allowed makes the program ill-formed. For example the template argument `std::vector<auto>`, `sizeof(auto)`, `catch (auto e)`, array element types, `using T = auto;`.

### Variables (¶5, ¶9)

¶5 A variable declared with a placeholder type has its type deduced from its initializer, and this is only allowed in an initializing declaration of a variable: the placeholder must be one of the specifiers in the specifier sequence, and every declarator after it must have a non-empty initializer. The end of ¶5 notes that `auto` is also used to introduce structured bindings ([[dcl.struct.bind]]).

```cpp run ok
auto x = 5;                  // int
const auto *v = &x, u = 6;   // v: const int*, u: const int
static auto y = 0.0;         // double
auto f() -> int;
auto (*fp)() -> auto = f;    // function pointer whose return type is deduced too
int f() { return 0; }
int main() { return fp() + int(y) + u - 6; }
```

```cpp error
auto x;                      // error: no initializer
auto int r;                  // error: auto is no longer a storage class specifier since C++11
struct S { auto m = 1; };    // error: a non-static data member is not a variable
```

Non-static data members can't use `auto`: a default member initializer is only a default, constructors may not use it, and the member's type must be known when the class definition ends. A static data member is a variable, so `static inline auto m = 1;` works.

¶9 If a declaration has multiple declarators, they must all declare variables. Each variable is deduced separately, but the type that replaces `auto` must be the same. What is compared is the type replacing `auto`, not the variables' final types:

```cpp error
#include <initializer_list>
int x = 5;
auto a = 5, *y = &x;        // OK: auto is int in both
auto b = 5, c = { 1, 2 };   // error: int vs std::initializer_list<int>
auto d = 1, e = 2.0;        // error: int vs double
```

### Parameters: abbreviated function templates and generic lambdas (¶2)

¶2 The types of the following three kinds of parameters can be declared with `type-constraint(opt) auto`:

- ¶2.1 a function parameter, making the function an **abbreviated function template** ([[dcl.fct]]), introduced in C++20;
- ¶2.2 a lambda parameter, i.e. a generic lambda ([[expr.prim.lambda]]), introduced in C++14;
- ¶2.3 a template parameter, i.e. `template<auto N>` (C++17) and `template<std::integral auto N>` (C++20).

This placeholder is called a **generic parameter type placeholder**. Only `auto` can be used here, not `decltype(auto)`.

```cpp run ok
#include <concepts>
#include <cstdio>
void print(const auto& x) { std::printf("%d\n", int(x)); }
std::integral auto twice(std::integral auto n) { return n * 2; }
template<auto N> struct Const { static constexpr auto value = N; };
int main() {
    print(3.7);   // equivalent to template<class T> void print(const T&)
    auto add = [](auto a, auto b) { return a + b; };
    static_assert(Const<'x'>::value == 'x');
    return twice(2) + add(1, 2) - 7;
}
```

```cpp error
void f(decltype(auto) x);   // error: parameters can only use auto
```

Each generic parameter type placeholder corresponds to an invented template parameter, so an abbreviated function template is a function template: it can be specialized and explicitly instantiated, participates in partial ordering, and is subject to the ODR like any template.

### new and auto(x) (¶6–¶7)

¶6 `new auto(1)` allocates an `int`. ¶7 `auto` can be used as the type in a function-style type conversion, i.e. `auto(x)` and `auto{x}` (C++23, [[P0849R8]]).

```cpp run ok
#include <vector>
#include <type_traits>
int main() {
    int* p = new auto(42);
    std::vector<int> v{3, 1, 3, 2};
    // front() returns a reference, and the element it refers to is overwritten during erasure, so copy it first
    std::erase(v, auto(v.front()));
    const int ci = 0;
    static_assert(std::is_same_v<decltype(auto(ci)), int>);
    int r = int(v.size()) - 2 + (*p - 42);   // v == {1, 2}
    delete p;
    return r;
}
```

The semantics of `auto(x)` are **decay-copy**: the result is a prvalue whose type is the type of `x` after array-to-pointer and function-to-pointer conversion, with references and top-level cv removed. In generic code, spelling out this type (`std::decay_t<decltype(x)>`) is often long, and previously you had to write `auto tmp = x;` first.

## Function return type deduction

¶4 Any function declaration except a conversion function may have a placeholder in its return type (`operator auto()` is specified separately in [[class.conv.fct]]). The return type is deduced from the **non-discarded** return statements in the function body, i.e. not counting returns in a discarded branch of `if constexpr` ([[stmt.if]]):

```cpp run ok
#include <type_traits>
template<class T>
auto unwrap(T t) {
    if constexpr (std::is_pointer_v<T>) return *t;   // with T = int*, only this one counts
    else return t;
}
int main() { int v = 3; return unwrap(&v) + unwrap(4) - 7; }
```

¶3 If the function uses a trailing return type, the leading `auto` is just a syntactic placeholder and the return type is the type after `->`; a placeholder can appear there too, for example `auto g() -> auto&`.

### Multiple returns and no return (¶10–¶11)

¶10 Each non-discarded return is deduced separately, and the results must be exactly the same; no common type is computed. ¶11 With no return, it is as if there were a return with no operand at the end of the function body, and the deduced type is `void`.

<div class="compare" markdown="1">

```cpp error
auto f(bool b) {
    if (b) return 1;
    return 2.0;  // error: int earlier
}
```

```cpp error
auto  f() { }  // OK: void
auto* g() { }  // error: can't deduce
               // auto* from void()
```

</div>

Clang's diagnostic for the left one is "'auto' in return type deduced as 'double' here but deduced as 'int' in earlier return statement".

### No use before deduction (¶13)

¶13 If an expression names a variable or function whose type hasn't been deduced yet, the program is ill-formed. But once a non-discarded return statement has appeared in a function, the deduced type can be used in the rest of the function. So as long as the first return isn't recursive, the function can recurse:

<div class="compare" markdown="1">

```cpp run ok
auto sum(int i) {
    if (i == 1)
        return i;  // deduces int
    else
        return sum(i - 1) + i;
}
int main() { return sum(4) - 10; }
```

```cpp error
auto fact(int n) {
    // error: the very first return
    // uses fact's type
    return n <= 1 ? 1
         : n * fact(n - 1);
}
```

</div>

```cpp error
auto n = n;          // error: the initializer refers to n itself
auto f();
void g() { &f; }     // error: f isn't defined yet, return type unknown
```

### When deduction happens in templates (¶15)

¶15 Return type deduction for a templated function happens when the definition is instantiated, even if the return operand doesn't depend on template parameters. Note 3 points out that therefore any use of the specialization, even just inside `decltype`, causes implicit instantiation; errors during that instantiation are not in the **immediate context** of the function type ([[temp.deduct]]) and make the program ill-formed instead of causing deduction failure.

```cpp run ok
template<class T> auto f(T t) { return t; }
typedef decltype(f(1)) fint_t;          // instantiates f<int> to get the return type
template<class T> auto f(T* t) { return *t; }
void g() { int (*p)(int*) = &f; (void)p; }   // both f's must be instantiated; the second is chosen
int main() {}
```

!!! warning "Return type deduction is not suitable for SFINAE detection"
    With `template<class T> auto size_of(T t) { return t.size(); }`, for a type without `size()` the error occurs while instantiating the function body and is a hard error. When you need SFINAE, use a trailing return type `-> decltype(t.size())` or a `requires` constraint.

¶19 An explicit instantiation declaration (`extern template`) doesn't instantiate an entity declared with a placeholder type, but it doesn't prevent instantiation needed to determine the type:

```cpp run ok
template<class T> auto f(T t) { return t; }
extern template auto f(int);   // doesn't instantiate f<int>
int (*p)(int) = f;             // instantiates f<int> to determine its return type
template auto f(int);          // an explicit instantiation definition is still needed somewhere in the program
int main() { return p(0); }
```

### Redeclarations must use the same placeholder (¶16)

¶16 If the declared return type of a function or function template F uses a placeholder, redeclarations and specializations of F must use the same placeholder, not the deduced type; conversely, if the original declaration didn't use a placeholder, redeclarations can't either.

```cpp error
auto f();
auto f() { return 42; }   // returns int
auto f();                 // OK
int f();                  // error: auto doesn't match int
decltype(auto) f();       // error: auto doesn't match decltype(auto)
```

This way the compiler knows from a declaration alone that the return type needs deduction. For function templates, this rule decides which explicit instantiations match which template. The template part of the standard's Example 7:

```cpp
template<typename T> auto g(T t) { return t; }  // #1
template auto g(int);                           // OK: returns int
template char g(char);                          // error: no matching template
template<> auto g(double);                      // OK: forward declaration of an explicit specialization

template<class T> T g(T t) { return t; }        // OK: not equivalent to #1, a different template
template char g(char);                          // OK: matches this template
template auto g(float);                         // still matches #1
void h() { return g(42); }                      // error: ambiguous
```

This restriction only applies to functions. The end of Example 7 shows that variables can be redeclared with `auto`: `extern int v; auto v = 17;` is valid, and `auto S::i = 23;` can also define a static data member.

### Other restrictions (¶12, ¶14, ¶17, ¶18)

¶17 A function whose return type uses a placeholder can't be virtual, and per ¶18 it can't be a coroutine either.

```cpp error
struct S { virtual auto f() { return 1; } };   // error: can't be virtual
```

Overriding a virtual function requires checking that the return types are the same or covariant ([[class.virtual]]), which needs the return type known at the class definition, while deduction has to wait for the function definition, which may be outside the class or even in another translation unit. A coroutine's return type determines its promise type (`std::coroutine_traits<R, Args...>`), while deducing the return type would first require analyzing `co_return`, which is circular.

¶12 An exported function whose return type uses a placeholder must be defined in the translation unit containing its exported declaration (outside the private module fragment), because importers need to see the body to know the return type. Note 2 points out that the deduced return type can't name something with internal linkage ([[basic.link]]).

¶14 {{c++26}} The result binding in a postcondition (the `r` in `post(r : …)`, [[dcl.contract.res]]) never has an undeduced placeholder type, so a function with return type `auto` can still use `r` in a postcondition:

```cpp
auto f()
    post(r : r == 7)   // OK: the type of r is the deduced int
{
    return 7;
}
```

As of writing, Clang 23 doesn't support contract syntax, so this example has not been verified by compiling.

## Implementation notes

!!! impl "Name mangling and compile-time cost"
    - An abbreviated function template and the equivalent ordinary function template have the same mangled names: specializations of `void h(auto)` and `template<class T> void k(T)` are both encoded as `...IiEvT_` under the Itanium ABI.
    - For a function template using return type deduction, the name encodes the placeholder itself (`Da` for `auto`, `Dc` for `decltype(auto)`), not the deduced type. Clang 23 mangles `f<int>` of `template<class T> auto f(T)` as `_Z1fIiEDaT_`. This is consistent with ¶16 requiring redeclarations to use the same placeholder.
    - Return type deduction requires the function body to be visible at every point of use, usually meaning it goes in a header; any use that takes `decltype` triggers instantiation (¶15). Heavy use of `auto` return types increases compile time.

## History

!!! history
    | Standard | Change |
    |---|---|
    | C++11 | `auto` variables (the keyword repurposed); trailing return types |
    | C++14 | Return type deduction for ordinary functions and `decltype(auto)` ([[N3638]]); generic lambdas; `auto x{1}` changed to `int` ([[N3922]]) |
    | C++17 | `template<auto N>`; structured bindings; CTAD |
    | C++20 | Abbreviated function templates, constrained placeholders `Concept auto` ([[P1141]]) |
    | C++23 | `auto(x)`, `auto{x}` ([[P0849R8]]); simpler implicit move ([[P2266]]), affecting `decltype(auto)` deduction |
    | C++26 | Result bindings in contracts (¶14) |

## Common misconceptions

!!! pitfall "`auto x = expr;` keeps references and const"
    It doesn't. Deduction by value drops references and top-level cv. To keep them, use `auto&`, `const auto&`, `auto&&` or `decltype(auto)`.

!!! pitfall "Multiple returns deduce a common type"
    They don't; they must be exactly the same. The conditional operator `?:` is what computes a common type.

!!! pitfall "`decltype(auto)` is a better `auto`"
    It keeps references, and parenthesizing a local variable in a return makes it return a dangling reference. Use it only when you need to forward the reference-ness of a return value exactly.

## Questions

!!! question "Question 1"
    What is the type of each variable below?

    ```cpp
    const char* const p = "hi";
    auto a = p;
    auto b = "hi";
    auto& c = "hi";
    auto d = { p };
    auto e { p };
    ```

<details markdown="1">
<summary>Answer</summary>

- `a`: `const char*`. Deduction by value drops the top-level const (the pointer's own const) and keeps the low-level const.
- `b`: `const char*`. A string literal is an lvalue of type `const char[3]`, and the array decays to a pointer in deduction by value.
- `c`: `auto` deduces `const char[3]`, and `c` is `const char(&)[3]`; references don't decay.
- `d`: `std::initializer_list<const char*>`; requires including `<initializer_list>`.
- `e`: `const char*`; direct-list-initialization deduces from the single element.
</details>

!!! question "Question 2"
    Why does `x` also become `false` after `std::vector<bool> v{true}; auto x = v[0]; v[0] = false;`? Does `auto(v[0])` fix it?

<details markdown="1">
<summary>Answer</summary>

`vector<bool>::operator[]` returns a proxy object `std::vector<bool>::reference` (a prvalue), and `auto` deduces exactly this proxy type. The proxy refers to that bit in `v`, so `x` changes along with `v[0]`.

`auto(v[0])` doesn't fix it either: decay-copy only copies the proxy object itself, and the type is still `reference`. Write the target type: `bool x = v[0];` or `auto x = static_cast<bool>(v[0]);`. `auto` deduces the type of the expression, and a proxy type is preserved as is.
</details>
