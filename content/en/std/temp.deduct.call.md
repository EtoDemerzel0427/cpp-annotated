---
title: Deducing template arguments from a function call
summary: "How each parameter type P is compared with the corresponding argument type A in a call to a function template: by-value parameters decay arrays and functions and drop top-level const, reference parameters use the referenced type, a forwarding reference with an lvalue replaces A with an lvalue reference; the three differences deduction tolerates; and the rules for braced lists, parameter packs and overload sets as arguments."
updated: 2026-10-19
---

!!! tldr
    - Deduction pairs each parameter type `P` with the type `A` of the corresponding argument. Before comparing, a by-value parameter makes array and function arguments decay to pointers and drops the argument's top-level `const`; a reference parameter is compared using the type it refers to.
    - When a forwarding reference of the form `T&&` meets an lvalue argument, `A` is replaced by an lvalue reference, so `T` is deduced as `X&`. `T` thereby records whether the argument was an lvalue or an rvalue, which `std::forward<T>` uses to restore it.
    - Deduction doesn't consider implicit conversions. Only three differences between argument and parameter are tolerated: extra cv, qualification conversions and function pointer conversions on pointers, and derived class to base class template.
    - For a braced list as an argument, only `std::initializer_list<T>` and `T[N]` parameters can deduce element by element; other parameters can't be deduced. This is the one difference between `auto` deduction and template deduction.
    - When the argument is the name of an overloaded function: if the set contains a function template, nothing is deduced; otherwise each member is tried, and deduction succeeds only if the result is unique.

## Three ways to write the parameter, three results

```cpp
template<class T> void byval(T);
template<class T> void byref(T&);
template<class T> void fwd(T&&);

const int ci = 0;
byval(ci);   // T = int
byref(ci);   // T = const int
fwd(ci);     // T = const int&
```

The same argument deduces three different `T`s with three ways of writing the parameter. The reason is that both the parameter type and the argument type are adjusted before comparing.

¶1 In a function call, each function parameter type that contains template parameters participating in deduction (call it `P`) is compared with the type of the corresponding argument of the call (call it `A`). The adjusted `P` and `A` are handed to [[temp.deduct.type]] for structural matching. Parameters that contain no template parameters participating in deduction (such as `int`, or parameters whose template arguments were written explicitly) don't take part in deduction; their conversions are only checked in overload resolution ([[temp.arg.explicit#7]]).

`auto` deduction uses the rules of this subclause too: `auto x = expr;` is like replacing `auto` with an invented template parameter and deducing with `expr` as the argument ([[dcl.type.auto.deduct]]). A side-by-side comparison of the two is in [[topics/type-deduction]].

### By-value parameters: the argument decays (¶2)

¶2 If `P` is not a reference type:

- ¶2.1 if `A` is an array type, the pointer type produced by the array-to-pointer conversion is used in place of `A`; otherwise
- ¶2.2 if `A` is a function type, the pointer type produced by the function-to-pointer conversion is used in place of `A`; otherwise
- ¶2.3 if `A` is a cv-qualified type, the top-level cv-qualifiers are ignored.

This models what actually happens when passing by value: arrays and functions can't be passed by value and decay to pointers, and the copied parameter doesn't care whether the argument was `const`. So `byval(ci)` deduces `T = int`.

### cv and references on the parameter (¶3)

¶3 If `P` is a cv-qualified type, the top-level cv-qualifiers are ignored for deduction. If `P` is a reference type, the type referred to is used for deduction.

```cpp
template<class T> int f(const T&);
int n1 = f(5);          // f<int>(const int&)
const int i = 0;
int n2 = f(i);          // f<int>(const int&): const T against const int, T = int
template<class T> int g(volatile T&);
int n3 = g(i);          // g<const int>(const volatile int&)
```

In `byref(ci)`, `T&` refers to `T`, and matching `T` against `const int` gives `T = const int`, so the `const` is kept. In `g(i)`, `volatile T` is matched against `const int`, `T` absorbs the `const`, giving `T = const int`; the deduced `const volatile int` has an extra `volatile` compared to the argument, a difference ¶4.1 allows.

The table below lists the `T` deduced for common arguments with the three parameter forms. Every cell was checked with `static_assert` on Clang 23.

| Argument | `f(T)` | `f(T&)` | `f(T&&)` |
|---|---|---|---|
| `int i` (lvalue) | `int` | `int` | `int&` |
| `const int ci` (lvalue) | `int` | `const int` | `const int&` |
| `42` (prvalue) | `int` | deduces `int`, but can't bind: fails | `int` |
| `std::move(i)` (xvalue) | `int` | same, fails | `int` |
| `int arr[3]` | `int*` | `int[3]` | `int(&)[3]` |
| `const int carr[2]` | `const int*` | `const int[2]` | `const int(&)[2]` |
| `"hi"` (lvalue of `const char[3]`) | `const char*` | `const char[3]` | `const char(&)[3]` |
| `void fn(int)` | `void(*)(int)` | `void(int)` | `void(&)(int)` |

`const int carr[2]` by value gives `const int*`: after the array decays, the `const` qualifies the `int` the pointer points to, not the top level, so it is kept.

## Forwarding references (¶3)

!!! std
    A *forwarding reference* is an rvalue reference to a cv-unqualified template parameter that does not represent a template parameter of a class template (during class template argument deduction).

A [[g:forwarding-reference|**forwarding reference**]] is an rvalue reference to a template parameter without cv-qualification, i.e. `T&&`. During class template argument deduction, a `T&&` where `T` represents a class template parameter doesn't count (see below). ¶3 says: if `P` is a forwarding reference and the argument is an lvalue, the type "lvalue reference to `A`" is used in place of `A` for deduction.

```cpp
template <class T> int f(T&& heisenreference);
template <class T> int g(const T&&);
int i;
int n1 = f(i);   // f<int&>(int&)
int n2 = f(0);   // f<int>(int&&)
int n3 = g(i);   // error: g<int>(const int&&) would bind an rvalue reference to an lvalue
```

The standard names the parameter heisenreference, after Heisenberg: until observed, you don't know whether it's an lvalue reference or an rvalue reference. Deduction for `f(i)` goes:

1. `P = T&&` is a forwarding reference and the argument `i` is an lvalue, so `A` changes from `int` to `int&`;
2. `P` is a reference, so its referred type `T` is matched against `int&`, giving `T = int&`;
3. after substitution `T&&` is `int& &&`, which collapses to `int&` by reference collapsing ([[dcl.ref#7]]).

The argument of `f(0)` is an rvalue, `A` is unchanged, `T = int`, and the parameter is `int&&`. The parameter of `g` has `const`, so it isn't a forwarding reference; `T` is deduced as `int`, and `const int&&` can't bind an lvalue.

So the deduced `T` records the argument's value category: `T` is an lvalue reference when the argument is an lvalue, and not a reference when it's an rvalue. `std::forward<T>(x)` uses `T` to restore the original value category:

```cpp run ok
#include <cstdio>
#include <utility>
void sink(int&)  { std::puts("lvalue"); }
void sink(int&&) { std::puts("rvalue"); }

template<class T> void relay(T&& x) {
    sink(x);                       // always lvalue: the named x is an lvalue
    sink(std::forward<T>(x));      // lvalue when T = int&, rvalue when T = int
}

int main() {
    int i = 0;
    relay(i);        // lvalue lvalue
    relay(42);       // lvalue rvalue
}
```

Which forms are forwarding references:

| Form | Forwarding reference? | Why |
|---|---|---|
| `template<class T> void f(T&&)` | yes | |
| `template<class T> void f(const T&&)` | no | cv-qualified |
| `template<class T> void f(std::vector<T>&&)` | no | not a reference to the template parameter itself |
| `template<class T> struct S { void f(T&&); }` | no | `T` is already fixed when `f` is called; nothing is deduced |
| `template<class T> struct S { template<class U> void f(U&&); }` | yes (`U&&`) | |
| `auto&& x = expr;` | yes | [[dcl.type.auto.deduct]] |
| a constructor's `T&&` in class template argument deduction (`T` a class template parameter) | no | explicitly excluded by the definition |
| `T&&` in a deduction guide | yes | the deduction guide's parameters belong to it |

The last two rows correspond to the second half of Example 4 in the standard:

```cpp
template <class T> struct A {
    template <class U>
        A(T&&, U&&, int*);   // #1: T&& isn't a forwarding reference, U&& is
    A(T&&, int*);            // #2
};
template <class T> A(T&&, int*) -> A<T>;   // #3: T&& is a forwarding reference

int i; int *ip;
A a{i, 0, ip};    // error: can't deduce from #1 (T&& can't bind the lvalue i)
A a0{0, 0, ip};   // deduces A<int> from #1, initializes with #1
A a2{i, ip};      // deduces A<int&> from #3, initializes with #2
```

Class template argument deduction ([[over.match.class.deduct]]) treats constructors as invented function templates, with the class template parameter `T` becoming a parameter of the invented template. If the `T&&` in `A(T&&, ...)` counted as a forwarding reference too, an lvalue argument would deduce `A<int&>`, which usually isn't what the class author intended, so the definition excludes it. A deduction guide is written deliberately by the author and can ask for forwarding-reference semantics.

The term was introduced into the standard by [[N4164]]. Before that it was often called a universal reference; both mean the same thing.

## The three differences deduction tolerates (¶4–¶5)

¶4 In general, deduction tries to find template arguments that make the substituted `P` (the deduced `A`) identical to the adjusted `A`. But three cases allow them to differ:

- ¶4.1 If the original `P` is a reference type, the deduced `A` can be more cv-qualified than `A`. For example, `const T&` accepts an `int` lvalue.
- ¶4.2 `A` can be another pointer or pointer-to-member type that can be converted to the deduced `A` via a function pointer conversion and/or a qualification conversion. For example, `const T*` accepts `int*`, and `void(*)()` accepts `void(*)() noexcept`.
- ¶4.3 If `P` is a class with the form of a *simple-template-id* (like `B<T>`), `A` can be a class derived from the deduced `A`; if `P` is a pointer to such a class, `A` can be a pointer to a derived class.

```cpp ok
template<class T> void f(const T*) { }
template<class T> struct B { };
template<class T> struct D : B<T> { };
template<class T> void g(B<T>*) { }

void t() {
    int* p = nullptr;
    f(p);         // ¶4.2: int* becomes const int* via a qualification conversion, T = int
    D<int> d;
    g(&d);        // ¶4.3: D<int>* converted to B<int>*, T = int
}
```

The last sentence of ¶4.3 specifies which base to choose when several bases of the derived class could match: if some base `C` is itself derived from `B` and `C` could also be the deduced result, `B` is not chosen. In other words, the base closer to the derived class wins:

```cpp ok
template <typename... T> struct X;
template <> struct X<> { };
template <typename T, typename... Ts>
struct X<T, Ts...> : X<Ts...> { };      // X<int> derives from X<>

struct D : X<int> { };
struct E : X<>, X<int> { };             // E derives directly from X<> and X<int>

template <typename... T> constexpr int f(const X<T...>&) { return sizeof...(T); }

static_assert(f(D()) == 1);   // f<int>, not f<>: B is X<>, C is X<int>
static_assert(f(E()) == 1);   // f<int>, not f<>
```

`D`'s bases `X<int>` and `X<>` both match `X<T...>`. Without this rule, deduction would have two results and fail; with it, `X<int>`, which derives from `X<>`, wins. Recursive-inheritance implementations in the style of `std::tuple` rely on this.

¶5 These three exceptions are considered only if deduction would otherwise fail. If they then yield more than one possible result, deduction fails.

Note 1 reminds us that a template parameter that appears in no function parameter, or only in [[g:non-deduced-context|non-deduced contexts]], can't be deduced from a call and must be specified explicitly, as in `convert<int>(d)`.

!!! pitfall "Deduction doesn't consider implicit conversions"
    Apart from the three differences above, integral promotions, arithmetic conversions, converting constructors and conversion operators are never considered:

    ```cpp
    template<class T> struct Wrapper { Wrapper(T) { } };
    template<class T> void take(Wrapper<T>);
    void t() { take(42); }   // error: int isn't Wrapper<T>, and deduction won't look for Wrapper<int>(int)
    ```

    Likewise, `template<class C> bool eq(const std::basic_string<C>&, const std::basic_string<C>&)` doesn't accept `eq(s, "abc")`. There are three fixes: specify the argument explicitly; put the parameter in a non-deduced context (`std::type_identity_t<Wrapper<T>>`); or define a non-template friend function in the class (a hidden friend), which is an ordinary function once the class template is instantiated and can perform conversions.

## Braced lists as arguments (¶1)

A braced initializer list has no type and can't serve directly as `A`. ¶1 specifies:

- If removing references and cv from `P` gives `std::initializer_list<P'>` or `P'[N]` and the argument is a non-empty initializer list, each element of the list is treated as the argument of a separate parameter of type `P'` and deduced individually. In `P'[N]`, if `N` is a constant template parameter, `N` is deduced from the length of the list.
- Otherwise, an initializer list argument makes the parameter a non-deduced context ([[temp.deduct.type#5]] ¶5.9).

```cpp ok
#include <initializer_list>
template<class T> void f(std::initializer_list<T>) { }
template<class T, int N> void h(T const(&)[N]) { static_assert(N == 3); }
template<class T> void j(T const(&)[3]) { }
struct Aggr { int i; int j; };
template<int N> void k(Aggr const(&)[N]) { static_assert(N == 3); }
template<int M, int N> void m(int const(&)[M][N]) { static_assert(M == 2 && N == 2); }

void t() {
    f({1, 2, 3});            // T = int
    h({1, 2, 3});            // T = int, N = 3
    j({42});                 // T = int; the array bound 3 doesn't take part in deduction
    k({{1}, {2}, {3}});      // N = 3: each {1} initializes an Aggr
    m({{1, 2}, {3, 4}});     // M = 2, N = 2
}
```

```cpp error
#include <initializer_list>
template<class T> void f(std::initializer_list<T>);
template<class T> void g(T);
struct Aggr { int i; int j; };
template<int N> void k(Aggr const(&)[N]);

void t() {
    f({1, "asdf"});   // error: T deduced as int and const char*, conflict
    g({1, 2, 3});     // error: non-deduced context, T can't be deduced
    k({1, 2, 3});     // error: int can't be converted to Aggr
}
```

- `g({1, 2, 3})` fails, whereas `auto x = {1, 2, 3};` deduces `std::initializer_list<int>`. This is the one rule difference between `auto` and template deduction: [[dcl.type.auto.deduct]] specifically replaces `auto` with `initializer_list<U>` before deducing.
- `k({1, 2, 3})` fails: each element `1` corresponds to `P' = Aggr`, which contains no template parameters, so it is checked whether `int` can be implicitly converted to `Aggr`, and it can't. In `k({{1}, {2}, {3}})` each element `{1}` is itself a list and only needs to be able to initialize an `Aggr`.
- In `j({42})` the array bound is a fixed 3 and doesn't take part in deduction; a single element is fine, and the rest are value-initialized.

Elements can also be overloaded function names. In the following example, `T` is deduced as `int` from the first element; the second element `&f4` is an overload set and deduces nothing (see ¶6 below), and `N = 2`:

```cpp
template<typename T, int N> void o(T (* const (&)[N])(T)) { }
int f1(int);
int f4(int);
char f4(char);
o({ &f1, &f4 });                                // OK
o({ &f1, static_cast<char(*)(char)>(&f4) });    // error: T deduced as int and char, conflict
```

## Function parameter packs (¶1)

For a function parameter pack at the end of the parameter list, the type of the pack's declarator is used as `P` and deduced against each remaining argument, each deduction determining the template argument for the next position in the pack. A function parameter pack in a non-deduced context never has its type deduced, for example when the pack isn't at the end:

```cpp
template<class... Types> void f(Types&...);
template<class T1, class... Types> void g(T1, Types...);
template<class T1, class... Types> void g1(Types..., T1);

void h(int x, float& y) {
    const int z = x;
    f(x, y, z);                   // Types = int, float, const int
    g(x, y, z);                   // T1 = int; Types = float, int
    g1(x, y, z);                  // error: Types isn't at the end, not deduced
    g1<int, int, int>(x, y, z);   // OK: no deduction, Types = int, int, T1 = int
}
```

In `f(x, y, z)`, `z` deduces `const int`, because `P = Types&` is a reference and cv is kept (¶3). In `g(x, y, z)`, `z` deduces `int`, because `P = Types` is by value and top-level cv is dropped (¶2.3).

## Overloaded function names as arguments (¶6–¶10)

¶6 When `P` is a function type, function pointer type or pointer-to-member-function type and the argument is an overload set:

- ¶6.1 if the set contains one or more function templates, the parameter is treated as a non-deduced context;
- ¶6.2 if the set contains no function templates, deduction is attempted with each member whose constraints are satisfied. If all successful attempts give the same `A`, that is the deduced result; otherwise the parameter is treated as a non-deduced context.

```cpp ok
// Example 6: only one member can match, so deduction works
template <class T> int f(T (*p)(T));
int g(int);
int g(char);
int i = f(g);       // only g(int) fits T(*)(T), T = int
```

```cpp ok
// Example 7: two members match with different results, so nothing is deduced; T comes from another argument
template <class T> int f(T, T (*p)(T));
int g(int);
char g(char);
int i = f(1, g);    // T deduced as int from 1, then g(int) is selected
```

```cpp ok
// Example 8: the overload set contains a template, so nothing is deduced
template <class T> int f(T, T (*p)(T));
char g(char);
template <class T> T g(T);
int i = f(1, g);    // T = int, g<int> selected
```

```cpp ok
// Example 9: several members giving the same type still count as a successful deduction
template<bool B> struct X {
    static void f(short) requires B;   // #1
    static void f(short);              // #2
};
void test() {
    auto x = &X<true>::f;    // OK: deduces void(*)(short), selects #1
    auto y = &X<false>::f;   // OK: deduces void(*)(short), selects #2
    (void)x; (void)y;
}
```

In Example 9, the two members of `X<true>::f` have the same type, and ¶6.2 only requires all successful attempts to give the same `A`, so the deduced type is `void(*)(short)`. Which function is actually selected is decided after deduction by [[over.over]], which picks #1 by constraints. Deduction only determines the type, and it's enough that the type is unambiguous.

## Common misconceptions

!!! pitfall "`T&&` is always an rvalue reference"
    In `template<class T> void f(T&&)`, `T&&` can bind lvalues. When it is overloaded with `f(const T&)`, a non-const lvalue argument selects the `T&&` version: `T` deduces as `U&`, and the parameter is `U&`. Both are reference bindings, but `const U&` refers to a more cv-qualified type and ranks lower per [[over.ics.rank]]. This is also why perfect-forwarding constructors hijack copy construction.

!!! pitfall "A by-value parameter can deduce `const` or an array type"
    `template<class T> void f(T)` never deduces `const`, a reference or an array type. To keep the array length, write `T(&)[N]` or `const T(&)[N]`; to keep everything, write `T&&`.

!!! pitfall "`f({1, 2, 3})` can deduce `vector<int>`"
    `template<class T> void f(std::vector<T>)` doesn't accept `f({1, 2, 3})`. `vector<T>` is neither `initializer_list<T>` nor `T[N]`, so the braced list makes the parameter a non-deduced context and `T` can't be deduced. Write `f<int>({1, 2, 3})` or `f(std::vector{1, 2, 3})`.

## Questions

!!! question "Question 1"
    ```cpp
    template<class T> void f(T&&, T&&);
    int i = 0;
    f(i, 0);
    ```
    Does this compile?

<details markdown="1">
<summary>Answer</summary>

No. In the first pair `i` is an lvalue, `A` becomes `int&`, and `T = int&` is deduced; in the second pair `0` is an rvalue, and `T = int` is deduced. The two pairs disagree, so deduction fails ([[temp.deduct.type#2]]). A forwarding reference records the value category in `T`, so when several forwarding-reference parameters share one `T`, the arguments' value categories must agree too. Usually you should write `template<class T, class U> void f(T&&, U&&)`.
</details>

!!! question "Question 2"
    ```cpp
    template<class T> void f(const T& a, const T& b);
    f("ab", "abc");
    ```
    Does this compile? What if the parameters are by value, `f(T a, T b)`?

<details markdown="1">
<summary>Answer</summary>

By reference, no. `P` is a reference, so arrays don't decay (¶2 only applies to non-reference `P`). The first pair deduces `T = char[3]`, the second `T = char[4]`, a conflict.

By value, yes. Per ¶2.1 the arrays decay to `const char*`, and both pairs deduce `T = const char*`. That's why `std::max("ab", "abc")` fails to compile (the parameters of `max` are `const T&`), while the by-value version compiles, though it compares two pointers, which is almost certainly not what was wanted. Clang 23 agrees.
</details>
