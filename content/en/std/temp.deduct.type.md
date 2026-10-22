---
title: Deducing template arguments from a type
summary: "The algorithm shared by every deduction context: align a type P written in terms of template parameters with an actual type A by structure, taking apart pointers, references, arrays, functions, member pointers and template specializations to solve for template arguments; which positions are non-deduced contexts; how packs are deduced; how the types of constant template parameters are deduced."
updated: 2026-10-19
---

!!! tldr
    - Deduction is structural matching: align a type `P` written in terms of template parameters with an actual type `A`, taking apart only the type constructors for pointers, references, arrays, functions, member pointers and template specializations.
    - Each `P`/`A` pair is deduced independently and the results combined; if the results conflict, there are several solutions, or some template parameter is left undetermined, deduction fails. Deduction doesn't consider implicit conversions.
    - The prefix of a qualified name (`typename A<T>::type`), `decltype`, expressions involving template parameters (`N+1`) and similar positions are non-deduced contexts: nothing is solved from them, and values obtained elsewhere are substituted into them. `std::type_identity_t<T>` is a deliberately constructed non-deduced context.
    - A pack can be deduced as zero or more arguments, but a pack that isn't at the end isn't deduced.
    - When deducing a constant template parameter, its type must be identical to the type of the actual template parameter: `template<int N> void f(std::array<int, N>)` can't be deduced; write `std::size_t N` or `auto N`.

## P and A (¶1–¶2)

```cpp run ok title="forms.cpp"
#include <cstddef>
#include <type_traits>

template<class R, class... As> constexpr auto arity(R(*)(As...)) { return sizeof...(As); }
template<class C, class M> constexpr bool is_mem_obj(M C::*) { return !std::is_function_v<M>; }
template<template<class...> class TT, class... Ts> constexpr auto count(const TT<Ts...>&) { return sizeof...(Ts); }
template<class T, std::size_t N> constexpr auto len(T(&)[N]) { return N; }

struct S { int x; void f(); };
template<class...> struct List { };
int fn(int, char, double);
int arr[7];

static_assert(arity(&fn) == 3);                // function type: R = int, As = int, char, double
static_assert(is_mem_obj(&S::x));              // member pointer: C = S, M = int
static_assert(!is_mem_obj(&S::f));             // M = void()
static_assert(count(List<int, char>{}) == 2);  // template specialization: TT = List
static_assert(len(arr) == 7);                  // array: T = int, N = 7
int main() { }
```

In each call, the compiler aligns the parameter type (such as `R(*)(As...)`) with the argument type (`int(*)(int, char, double)`) layer by layer and reads off the values of `R` and `As` from the corresponding positions.

¶1 Deduction happens in many contexts: function calls ([[temp.deduct.call]]), taking the address of a function template ([[temp.deduct.funcaddr]]), conversion function templates ([[temp.deduct.conv]]), partial ordering ([[temp.deduct.partial]]), deduction from a function declaration ([[temp.deduct.decl]]), and matching partial specializations ([[temp.spec.partial.match]]). Each ultimately reduces to the problem of this subclause: given a type `P` written in terms of template parameters and an actual type `A`, find template arguments (a type for a type parameter, a value for a constant parameter, a template for a template template parameter) that make `P`, after substitution (called the deduced `A`), compatible with `A`.

¶2 Sometimes there is a single `P`/`A` pair, sometimes a set, such as one pair per function parameter. Each pair is deduced independently and the results combined. Deduction fails if any of the following happens: some pair can't be deduced; some pair has more than one set of solutions; different pairs deduce different values; or some template argument is neither deduced nor explicitly specified.

```cpp error
template<class T> void f(T x, T y) { }
struct A { };
struct B : A { };
void g(A a, B b) {
    f(a, b);    // error: T deduced as A and B
    f(b, a);    // error: likewise
    f(a, a);    // OK: T = A
    f(b, b);    // OK: T = B
}
```

Although `B` can be converted to `A`, deduction doesn't consider conversions ([[temp.deduct.call#4]] allows only a few adjustments), so `f(a, b)` fails.

A single `P`/`A` pair can also deduce several parameters at once and contradict itself (Example 3 under ¶7):

```cpp error
template <class T, class U> void f(T (*)(T, U, U));
int  g1(int, float, float);
char g2(int, float, float);
int  g3(int, char, float);
void r() {
    f(g1);    // OK: T = int, U = float
    f(g2);    // error: T deduced as char from the return type and as int from the parameter
    f(g3);    // error: U deduced as char and float
}
```

## The forms that can be taken apart (¶3, ¶8–¶12)

¶3 A type `P` can be composed of other types, templates and constant values: a function type includes its parameter types, return type and exception specification; a pointer-to-member type includes the class type and the member type; a class template specialization `A<int>` includes its template arguments; an array type includes the element type and the bound.

¶8 A type parameter `T`, a constant parameter `i`, a template template parameter `TT` denoting a class template or alias template, or a template template parameter `VV` denoting a variable template or concept, can be deduced only if `P` and `A` have one of the following forms:

```text
cv(opt) T
T*
T&
T&&
T(opt)[i(opt)]
T(opt)(T(opt)) noexcept(i(opt))
T(opt) T(opt)::*
TT(opt)<T>
TT(opt)<i>
TT(opt)<TT>
TT(opt)<VV>
TT(opt)<>
```

The positions marked `(opt)` can contain these forms recursively, or be a non-deduced context, or be the same non-dependent type or the same constant value in `P` and `A` (¶8.1–¶8.4). `<T>` denotes a template argument list where at least one argument contains a `T`, and `<>` one where none does.

¶11 These forms can be nested like `T`; for example, `X<int> (*)(char[6])` has the form `type (*)(T)`, where `type` is `X<int>` and `T` is `char[6]`. ¶12 Template arguments can't be deduced from any other construct.

In other words, deduction only takes apart type constructors. Aliases aren't among them; they are already expanded to the target type before deduction.

Example 3 under ¶7 also shows deduction from exception specifications. Since C++17 the exception specification is part of the function type, so the `E` in `noexcept(E)` can be deduced:

```cpp error
template<bool E> void f1(void (*)() noexcept(E));
template<bool> struct A { };
template<bool B> void f2(void (*)(A<B>) noexcept(B));

void g1();
void g2() noexcept;
void g3(A<true>);

void h() {
    f1(g1);   // OK: E = false
    f1(g2);   // OK: E = true
    f2(g3);   // error: B deduced as true from A<true> and as false from noexcept
}
```

## Non-deduced contexts (¶4–¶6)

```cpp run ok title="type_identity.cpp"
#include <type_traits>
template<class T> T vmax(T a, std::type_identity_t<T> b) { return a < b ? b : a; }

auto r = vmax(1.5, 2);    // T deduced as double from the first argument only; 2 converted to double
static_assert(std::is_same_v<decltype(r), double>);

int main() { }
```

`std::type_identity_t<T>` is `typename std::type_identity<T>::type` (C++20, [[P0887R1]]). `T` appears before `::`, a position that doesn't take part in deduction. Once `T` is fixed by the first argument and substituted, the second parameter becomes an ordinary `double` parameter that accepts any argument implicitly convertible to it. Without it, `vmax(1.5, 2)` would fail because `T` would be deduced as both `double` and `int`.

¶4 Most parts of `P` take part in deduction: they can be used to determine template arguments, and the values determined must agree with those from elsewhere. But in some positions, a value doesn't take part in deduction and instead uses a value deduced elsewhere or explicitly specified; these positions are called **non-deduced contexts** ([[g:non-deduced-context|non-deduced context]]). If a template parameter appears only in non-deduced contexts and isn't explicitly specified, deduction fails.

¶5 The non-deduced contexts are:

| ¶ | Context | Example (`T`, `N` not deduced here) |
|---|---|---|
| 5.1 | the part of a qualified name before `::` (the *nested-name-specifier*) | `typename A<T>::type`, `std::type_identity_t<T>` |
| 5.2 | a pack index {{c++26}} | `Ts...[0]` |
| 5.3 | a type-constraint | `C<T>` in `C<T> auto` |
| 5.4 | the operand of `decltype` | `decltype(T{} + 1)` |
| 5.5 | the constant expression in a splice specifier {{c++26}} | `refl` in `[: refl :]` |
| 5.6 | a constant template argument or array bound in which a subexpression references a template parameter | `A<N+1>`, `int[N*2]` |
| 5.7 | a parameter for which this call uses a default argument | `f(T = 5)` called as `f()` |
| 5.8 | the argument is an overload set and several functions of different types match, no function matches, or the set contains a function template | `f(g)` where `g` is overloaded |
| 5.9 | the argument is a braced initializer list and the parameter isn't a type that can be deduced from a list | `template<class T> void g(T); g({1,2,3});` |
| 5.10 | a function parameter pack that isn't at the end of the parameter list | `template<class... Ts> void f(Ts..., int)` |

These positions aren't deduced because in general they can't be inverted. Solving for `T` from `typename A<T>::type` being `int` amounts to inverting an arbitrary type function, and `A` might be specialized into anything. `N+1 == 5` can be solved for `N`, but `N*N` or `f(N)` can't, so the standard simply says nothing is deduced whenever a template parameter appears in a subexpression. And a pack that isn't at the end doesn't know how many arguments to consume.

A parameter in a non-deduced context isn't ignored: after deduction it is still substituted, the substituted type must be valid, and the argument must be convertible to it.

```cpp error
template <int i> class A { };
template <int i> void g(A<i+1>);
template <int i> void f(A<i>, A<i+1>);

void k() {
    A<1> a1;
    A<2> a2;
    g(a1);          // error: i+1 isn't deduced, so i can't be determined
    g<0>(a1);       // OK
    f(a1, a2);      // OK: i deduced as 1 from A<i>, A<i+1> substitutes to A<2>, consistent
}
```

¶6 When a type name is written in a way that includes a non-deduced context, none of the types composing it are deduced: in `A<T>::B<T2>` neither `T` nor `T2` is deduced, and in `A<I+J>::X<T>` none of `I`, `J` and `T` are. But a compound type can be partly deduced and partly not: in `void f(typename A<T>::B, A<T>)`, the `T` in the first parameter isn't deduced, while the one in the second is.

Note 1 under ¶4 adds: if the deduced contexts of `P` contain no template parameters at all, no deduction is done for that pair, and `P` and `A` needn't have the same form, as long as the argument is convertible.

### Array bounds

```cpp error
template<int i> void f1(int a[10][i]);
template<int i> void f2(int a[i][20]);
template<int i> void f3(int (&a)[i][20]);

void g() {
    int v[10][20];
    f1(v);          // OK: i deduced as 20
    f1<20>(v);      // OK
    f2(v);          // error: can't deduce i
    f2<10>(v);      // OK
    f3(v);          // OK: i deduced as 10
}
```

Note 5 under ¶17 explains this example: except for references and pointers, the outermost array bound isn't part of a function parameter's type. `int a[i][20]` is adjusted to `int (*a)[20]`, `i` disappears, and naturally can't be deduced; `f3` keeps it by using a reference.

## Packs in template argument lists and function parameter lists (¶9–¶10, ¶24)

```cpp ok
template<class> struct X { };
template<class R, class... ArgTypes> struct X<R(int, ArgTypes...)> { };
template<class... Types> struct Y { };
template<class T, class... Types> struct Y<T, Types&...> { };

template<class... Types> int f(void (*)(Types...));
void g(int, float);

X<int> x1;                      // primary template
X<int(int, float, double)> x2;  // partial specialization; ArgTypes = float, double
X<int(float, int)> x3;          // primary template (the first parameter isn't int)
Y<> y1;                         // primary template; Types is empty
Y<int&, float&, double&> y2;    // partial specialization; T = int&, Types = float, double
Y<int, float, double> y3;       // primary template; float and double aren't references
int fv = f(g);                  // OK; Types = int, float
```

Note 8 under ¶24 points out that a pack can be deduced as zero or more arguments.

¶9 When `P` contains a template argument list, each of its arguments `Pi` is compared with the corresponding argument `Ai` of `A`. If `Pi` is a pack expansion, its pattern is compared with each remaining argument of `A` in turn, each comparison determining the next element of the pack. If the pack expansion isn't the last argument of the list, the whole template argument list is a non-deduced context.

¶10 When `P` contains a function parameter type list, the rule is the same: the type of the parameter pack is compared with each remaining parameter type of `A` in turn.

¶9 and ¶10 each have two rules used only in partial ordering ([[temp.deduct.partial]]). In partial ordering, if `Ai` was originally a pack: if there is nothing in `P` corresponding to it, it is ignored (¶9.1, ¶10.1); otherwise, if `Pi` isn't a pack, deduction fails (¶9.2, ¶10.2). They let specializations with packs be compared with specializations without them:

```cpp ok
template<class T1, class... Z> class S;                                 // #1
template<class T1, class... Z> class S<T1, const Z&...> { };            // #2
template<class T1, class T2>   class S<T1, const T2&> { };              // #3
S<int, const int&> s;           // #2 and #3 both match; #3 is more specialized

template<class T, class... U> void f(T*, U...) { }   // #4
template<class T>             void f(T) { }          // #5
template void f(int*);                               // selects #4: T* is more specialized than T
```

### Forwarding references in function types (¶10)

```cpp run ok title="spec_fwd.cpp"
#include <cstdio>
template <class T> void f(T&&)  { std::puts("primary"); }
template <> void f(int&)  { std::puts("#1 f<int&>"); }    // T&& against int&: adjusted to T, T = int&
template <> void f(int&&) { std::puts("#2 f<int>"); }     // T&& against int&&: T = int

int main() {
    int i = 0;
    f(i);    // calls #1
    f(0);    // calls #2
}
```

¶10 makes one adjustment to function types in two contexts: when taking the address of a function template ([[temp.deduct.funcaddr]]), and when deducing from a function declaration ([[temp.deduct.decl]], such as an explicit specialization). If a top-level parameter `Pi` is a **forwarding reference** (a cv-unqualified `T&&` where `T` is a type parameter of the function template) and `Ai` is an lvalue reference, `Pi` is changed to `T`, so `T` is deduced as `X&`. Without this adjustment, `T&&` and `int&` wouldn't match structurally, and it would be impossible to write an explicit specialization for the lvalue specialization.

## Types of constant template parameters (¶13–¶16, ¶20)

If the type of a constant template parameter depends on another template parameter, deducing its value also deduces its type.

¶13 When the value is deduced from an expression, the type is deduced from the type of the value:

```cpp ok
template<long n> struct A { };

template<typename T> struct C;
template<typename T, T n> struct C<A<n>> { using Q = T; };

using R = long;
using R = C<A<2>>::Q;     // OK: T deduced as long
```

`T` is `long`, not `int`: the `2` in `A<2>` has already been converted to `A`'s parameter type `long`.

¶14 In an array type `T[N]`, the type of `N` is `std::size_t`; ¶15 in a function type's `noexcept(B)`, the type of `B` is `bool`:

```cpp ok
#include <cstddef>
template<typename T> struct S;
template<typename T, T n> struct S<int[n]> { using Q = T; };
using V = S<int[42]>::Q;  // T deduced as std::size_t
static_assert(sizeof(V) == sizeof(std::size_t));

template<bool> struct A { };
template<auto> struct B;
template<auto X, void (*F)() noexcept(X)> struct B<F> { A<X> ax; };
void f_nothrow() noexcept;
B<f_nothrow> bn;          // the type of X deduced as bool
```

The example in ¶16 shows the same thing with a function call: calling `template<class T, T i> void f(int (&a)[i]);` with `int v[10]` makes `T` `std::size_t`. The last sentence of ¶2 says a type parameter is deduced from an array bound only if it can't be deduced from anywhere else.

¶20 If `P` contains `<i>`, the type of `i` must be exactly the type of the corresponding parameter of the template of `A` (ignoring top-level cv), otherwise deduction fails:

```cpp error
template<int i> class A { };
template<short s> void f(A<s>);
void k1() {
    A<1> a;
    f(a);           // error: int and short differ
    f<1>(a);        // OK: explicitly specified, not deduced
}

template<const short cs> class B { };
template<short s> void g(B<s>);
void k2() {
    B<1> b;
    g(b);           // OK: cv on the template parameter type is ignored
}
```

If the type of `i` contains a placeholder (`auto`, `decltype(auto)`), the placeholder is deduced by treating the corresponding parameter as the initializer expression:

```cpp error
template<int> struct D;
template<auto x> void f(D<x> *);
void g(D<0LL> *ap) {
    f(ap);          // OK: D's parameter is int, x deduced as an int value
}

template<int &> struct E;
template<auto x> void f(E<x> *);
int v;
void g(E<v> *bp) {
    f(bp);          // error: auto deduces int, which differs from the parameter type int&
}

template<const int &> struct F;
template<decltype(auto) x> void f(F<x> *);
int i;
void g(F<i> *ap) {
    f(ap);          // OK: decltype(auto) deduces const int&
}
```

¶20 also says: if `P` contains `[i]` and `i` isn't integral, or contains `noexcept(i)` and `i` isn't `bool`, deduction fails.

!!! impl "Clang deviates"
    The last part of Example 13 in the standard is:

    ```cpp
    template <decltype(auto) q> struct G;
    template <auto x> long *f(G<x> *);              // #1
    template <decltype(auto) x> short *f(G<x> *);   // #2

    const int j = 0;
    short *g(G<(j)> *ap) { return f(ap); }   // q has type const int&, only #2 matches
    long *g(G<j> *ap) { return f(ap); }      // q has type int, #1 is more specialized
    ```

    Clang 23 reports the last call as ambiguous. Per the standard, #1 should be selected.

## Function arguments, default arguments, template template parameters (¶21–¶23)

¶21 Template arguments can be deduced from function types, function pointer types and pointer-to-member-function types. When the argument is an overload set, ¶5.8 applies:

```cpp error
template<class T> void f(void(*)(T, int));
template<class T> void foo(T, int);
void g(int, int);
void g(char, int);
void h(int, int, int);
void h(char, int);

int m() {
    f(&g);      // error: both g match, with different T
    f(&h);      // OK: only void h(char, int) matches, T = char
    f(&foo);    // error: the overload set contains a template
    return 0;
}
```

In both errors the parameter becomes a non-deduced context, and `T` has nowhere else to be deduced from, so what is reported is that no function matches.

¶22 A type parameter can't be deduced from the type of a default argument:

```cpp error
template <class T> void f(T = 5, T = 7);
void g() {
    f(1);           // OK: f<int>(1, 7); the second parameter uses its default and doesn't take part in deduction
    f();            // error: can't deduce T
    f<int>();       // OK: f<int>(5, 7)
}
```

¶23 A template template parameter is deduced from a class template specialization in the argument type:

```cpp ok
template <template <class T> class X> struct A { };
template <template <class T> class X> void f(A<X>) { }
template<class T> struct B { };
A<B> ab;
void use() { f(ab); }      // X deduced as B
```

## Common misconceptions

!!! pitfall "Alias templates can always be deduced through"
    After `template<class T> using Vec = std::vector<T>;`, `f(Vec<T>)` is equivalent to `f(std::vector<T>)` and can be deduced. But with `template<class T> using Id = typename std::type_identity<T>::type;`, `T` ends up in a qualified name after expansion, and `f(Id<T>)` can't be deduced. Deduction looks at the expanded type.

!!! pitfall "Deducing the container from an iterator"
    `template<class C> void f(typename C::iterator)` can't deduce `C` from an iterator (¶5.1). That's why standard algorithms take the iterator type itself as the template parameter: `template<class It> void sort(It, It)`.

## Questions

!!! question "Question 1"
    ```cpp
    template<class T> struct Box { };
    template<class T> void f(Box<T>, typename Box<T>::value_type);
    f(Box<int>{}, 3);
    ```
    Does this compile?

<details markdown="1">
<summary>Answer</summary>

No (assuming no other candidates). `T` is deduced as `int` from the first parameter; the `T` in the second parameter is a non-deduced context. After deduction it is substituted, `Box<int>::value_type` doesn't exist, the function type is invalid, deduction fails, the template drops out of the candidate set, and no matching function is reported.
</details>

!!! question "Question 2"
    Why does deduction fail for `template<int N> void f(std::array<int, N>)` with `std::array<int, 3>`?

<details markdown="1">
<summary>Answer</summary>

By ¶20, the type of `N` must be the same as the type of `std::array`'s second template parameter. That parameter has type `std::size_t`, while `N` is `int`, so deduction fails. Either `std::size_t N` or `auto N` works; the latter deduces `std::size_t`.
</details>

<details class="fine" markdown="1"><summary>Remaining wording</summary>

¶8 Note 3: if a type matches one of the forms above but contains no `T`, `i` or `TT`, nothing can be deduced.

¶19 Note 7 stresses again that a template parameter used only in non-deduced contexts doesn't take part in deduction; for example, in `deduce<77>(a.xm, 62, b.ym)`, `T` is deduced from the second argument and `i` is given by the explicit argument.

Footnote to ¶20: although a parameter of type `bool` can be deduced from an array bound, the result is always `true`, because array bounds are non-zero.

</details>
