---
title: Template argument deduction
summary: "How the compiler fills in a function template's template arguments: substitute explicit arguments, deduce, apply defaults, check constraints, then substitute everything; when substitution yields an invalid type or expression the candidate is quietly removed (SFINAE), but only in the immediate context. Also covers the four other deduction contexts: taking an address, conversion function templates, partial ordering, and deduction from a declaration."
updated: 2026-10-19
---

!!! tldr
    - At its core, deduction matches a type `P` written in terms of template parameters against an actual type `A`. Calls, taking addresses, conversion functions, partial ordering and declared specializations differ only in where `P` and `A` come from.
    - A deduction follows fixed steps: substitute explicit arguments, deduce, fill in default template arguments, check constraints, check conversions for non-dependent parameters, and finally substitute all arguments into the function type. If any step fails, the template is no longer a candidate.
    - SFINAE: when substitution produces an invalid type or expression, deduction just fails, without an error. But this only covers errors in the signature itself (the immediate context); errors in class templates instantiated for it, or in lambda bodies, are hard errors.
    - Substitution proceeds in lexical order and stops at the first failure. Moving the return type from leading to trailing can turn SFINAE into a hard error.
    - Partial ordering decides which of two templates is more specialized: deduce one template from the transformed form of the other, once in each direction.

## What deduction does

```cpp
template<class T> const T& max(const T& a, const T& b);

int x = max(1, 2);   // no <int> written; the compiler deduces T = int
```

Template arguments not written when calling a function template are worked out by the compiler from the use; this is **template argument deduction**. In the example, the compiler compares the parameter type `const T&` (call it `P`) with the argument type `int` (call it `A`) and solves for the `T` that makes them agree.

The core of every deduction context is this structural matching of `P` against `A`, whose rules are in [[temp.deduct.type]]. The contexts differ only in where `P` and `A` come from and which adjustments are made before comparing. The most common case, deduction from a function call, is in [[temp.deduct.call]]; below we first cover the overall process before and after deduction ([temp.deduct.general]), then the other four contexts.

## The steps of a deduction (¶1–¶6)

¶1 When a function template specialization is referenced, all template arguments must have values: explicitly specified, deduced from the use, or taken from default template arguments ([[temp.fct.spec]]).

```cpp
template<class U, class V> U convert(V v);

void g(double d) {
    int i = convert<int>(d);      // calls convert<int, double>(double)
    int c = convert<char>(d);     // calls convert<char, double>(double)
}
```

In a function call, the steps specified by ¶2–¶6 are:

1. substitute the explicitly written template arguments (¶2);
2. adjust the function parameter types: arrays to pointers, functions to function pointers, top-level cv removed (¶3);
3. deduce using the adjusted function type (¶5; the specific rules are in [[temp.deduct.call]]);
4. use default template arguments for template parameters that weren't deduced (¶5);
5. substitute all template arguments into the template parameter list (¶5);
6. check constraints (¶5);
7. check that arguments can be implicitly converted to non-dependent parameters (¶5);
8. substitute all template arguments into the function type (¶5).

If any step gives an invalid result, deduction fails and this template contributes no candidate to the call. ¶6 sums up that substitution into the function type happens twice: once at the start for explicit arguments, once at the end for deduced and default arguments.

### Substituting explicit arguments (¶2–¶4)

¶2 When an explicit template argument list is written, if the *template-id* (since C++26, also a splice specialization specifier) isn't valid ([[temp.names]]), deduction fails; otherwise the arguments are substituted for the corresponding template parameters.

¶3 After substitution, the parameter type adjustments of [[dcl.fct]] are performed; for example, `void(const int, int[5])` becomes `void(int, int*)`. Note 1 reminds us that a top-level `const` on a parameter doesn't affect the function type, but it still affects the type of the parameter variable in the function body:

```cpp run ok
#include <type_traits>
template <class T> void f(T t) {
    static_assert(std::is_const_v<decltype(t)> == std::is_const_v<T>);
}
template <class Z> void h(Z, Z*) { }

int main() {
    f<int>(1);          // function type void(int), t not const
    f<const int>(1);    // function type void(int), t const
    h<const int>(1, 0); // function type void(int, const int*)

    static_assert(std::is_same_v<decltype(&f<const int>), void(*)(int)>);
    static_assert(std::is_same_v<decltype(&h<const int>), void(*)(int, const int*)>);
}
```

The first parameter of `h<const int>` is `const int`, and the top-level `const` is removed; the second is `const int*`, where the `const` isn't top-level and is kept.

¶4 Note 2 points out that `f<int>(1)` and `f<const int>(1)` call two different functions, even though the function types are the same. They have separate addresses and separate static variables.

### Default template arguments (¶5)

¶5 After deduction, if a template argument hasn't been deduced and the corresponding template parameter has a default argument, the template arguments determined so far are substituted into the default to obtain it. If the substitution is invalid, deduction fails.

```cpp
template <class T, class U = double>
void f(T t = 0, U u = 0);

void g() {
    f(1, 'c');        // f<int, char>(1, 'c')
    f(1);             // f<int, double>(1, 0): U uses the default template argument
    f();              // error: T can't be deduced
    f<int>();         // f<int, double>(0, 0)
    f<int, char>();   // f<int, char>(0, 0)
}
```

`f()` fails because the function's default argument `T t = 0` doesn't take part in deduction ([[temp.deduct.type#22]]): the default argument's type itself depends on `T`.

### Constraints and non-dependent parameters come before the final substitution (¶5)

¶5 goes on to specify:

- Once all template arguments are determined, they are first substituted into the template parameter list (for example the types of constant template parameters); if that's invalid, deduction fails.
- If the function template has associated constraints, they are checked ([[temp.constr.constr]]); if not satisfied, deduction fails.
- In a function call, for each parameter with an argument whose type was non-dependent before any explicit arguments were substituted, it is checked whether the argument can be implicitly converted to that type; if not, deduction fails. Note 3 explains that conversions for the other parameters are left for overload resolution to check.
- Only if all of these pass are the template arguments substituted into the function type.

The constraint and non-dependent-parameter checks both come before substitution into the function type. Substituting into the function type may require instantiating other templates, and errors in those instantiations are hard errors; doing the cheap checks that need no instantiation first can eliminate candidates before anything is instantiated:

```cpp ok
template <class T> struct Z {
    typedef typename T::x xx;          // instantiating for T = int or A would be an error
};
template <class T> concept C = requires { typename T::A; };

template <C T> typename Z<T>::xx f(void *, T);   // #1
template <class T> void f(int, T);               // #2

struct A {} a;
struct ZZ {
    template <class T, class = typename Z<T>::xx> operator T *();
    operator int();
};

int main() {
    ZZ zz;
    f(1, a);    // OK: calls #2
    f(zz, 42);  // OK: calls #2
}
```

- `f(1, a)`: #1's first parameter `void*` doesn't depend on template parameters, and `1` can't be converted to `void*`, so deduction fails right there, and the return type `Z<A>::xx` is never substituted. Otherwise instantiating `Z<A>` would be a hard error, since there is no `A::x`.
- `f(zz, 42)`: `T = int`, the constraint `C<int>` isn't satisfied, deduction fails. If the conversion were checked first, the conversion from `zz` to `void*` would consider `operator T*()`, which would substitute `Z<void>::xx`, again a hard error.

The earlier rule substituted the whole function type first and checked conversions in overload resolution, so many candidates that should have been eliminated triggered hard errors while substituting the return type. When C++20 introduced constraints, [[CWG2369]] adjusted the checks into today's order.

## SFINAE (¶7–¶12)

### Substitution failure is not an error

```cpp ok
template<typename T>
T* fun(T&& v);   // #1

void fun(...);   // #2

void test() {
    int i = 0;
    fun(i);      // calls #2
}
```

In `fun(i)`, `i` is an lvalue, so `T` is deduced as `int&` ([[temp.deduct.call]]), and substituting into the return type gives a pointer to reference `int&*`, a type that doesn't exist. But the program has no error: #1 just fails deduction and drops out of the candidates, and the call goes to #2.

This behavior is commonly called [[g:sfinae|**SFINAE**]], Substitution Failure Is Not An Error. The acronym comes from the book *C++ Templates*; the standard itself doesn't use it. The consequence that a template whose deduction fails contributes no candidate function is specified in [[temp.over]].

What fails needn't be a type; it can be an expression:

```cpp run ok
struct X { };
struct Y { Y(X) { } };

template <class T> auto f(T t1, T t2) -> decltype(t1 + t2);   // #1
X f(Y, Y);                                                    // #2

X x1, x2;
X x3 = f(x1, x2);   // #1 fails deduction (X + X is invalid), calls #2

int main() { }
```

`decltype(t1 + t2)` writes the requirement of supporting `+` into the signature. This is **expression SFINAE**, introduced in C++11 ([[N2634]]); before that, only type failures (like `typename T::type`) reliably counted as deduction failures. Since C++20 the same requirement is usually expressed with constraints ([[temp.constr]]).

### Where substitution happens (¶7)

¶7 defines the [[g:deduction-substitution-loci|**deduction substitution loci**]], the places where substitution happens during deduction:

- ¶7.1 the function type, excluding the *noexcept-specifier*;
- ¶7.2 the *explicit-specifier* (`explicit(bool)`);
- ¶7.3 the template parameter declarations;
- ¶7.4 the template argument list of a partial specialization ([[temp.spec.partial.general]]).

Substitution happens in all types and expressions used in these places, including constant expressions like array bounds and constant template arguments, and general expressions in `sizeof` and `decltype`.

Note 4 points out that exception specifications and function contract assertions aren't among these loci. They are substituted only when instantiated, and an error at that point makes the program ill-formed:

```cpp error
template<class T> void f(T) noexcept(T::value);
void f(...);
void t() { f(0); }   // error: after the template is selected, noexcept is instantiated and int::value is invalid
```

### Only errors in the immediate context are deduction failures (¶8)

¶8 If substitution results in an invalid type or expression, deduction fails. Invalid means that it would be ill-formed, with a diagnostic required, if written directly in the same place using the substituted arguments. Note 5 adds that access checking is part of substitution.

But the rule has a limited scope: only invalid types and expressions in the [[g:immediate-context|**immediate context**]] of the deduction substitution loci cause deduction failure. The immediate context is the substitution loci themselves, excluding the bodies of lambda-expressions in them, and excluding [[g:separately-instantiated-construct|separately instantiated constructs]] (such as class template specializations and default arguments).

```cpp error
template<class T> struct Wrap { using type = typename T::value_type; };

template<class T> typename Wrap<T>::type first(T);   // #1
template<class T> void first(...);                   // #2

void t() { first<int>(0); }   // error: the error is in the class body of Wrap<int>
```

Substituting `Wrap<int>::type` requires instantiating `Wrap<int>` first, and the error with `int::value_type` occurs inside the class template's instantiation. Notes 6 and 7 explain that such effects of substitution (instantiating template specializations, generating implicitly defined functions, and so on) are not in the immediate context, and errors in them make the program ill-formed.

So `Wrap` itself has to handle types without `value_type` gracefully, for example with a constrained partial specialization that provides `type` only when valid:

```cpp ok
template<class T> struct Safe { };                                    // no type
template<class T> requires requires { typename T::value_type; }
struct Safe<T> { using type = typename T::value_type; };

template<class T> typename Safe<T>::type first(T);   // #1
template<class T> void first(...);                   // #2

void t() { first<int>(0); }   // OK: Safe<int> validly has no type, calls #2
```

This is how standard library traits are SFINAE-friendly: when there is no answer, `std::common_type<A, B>` and `std::invoke_result<F, Args...>` simply have no `type` member, rather than erroring in the class body.

Access checking is part of substitution, so an access failure is also a deduction failure:

```cpp ok
class P { using secret = int; };                             // private

template<class T> auto probe(T*) -> typename T::secret;      // access fails: deduction fails
template<class T> char probe(...);

static_assert(sizeof(probe<P>(nullptr)) == 1);               // probe(...) chosen
```

### Statements aren't in the immediate context (¶9)

¶9 Note 8 points out that no statement is in the immediate context. Since C++20 lambdas can appear in unevaluated operands ([[P0315R4]]), so lambdas can appear in signatures, and lambda bodies consist of statements:

```cpp
template <class T>
    auto f(T) -> decltype([]() { T::invalid; } ());
void f(...);
f(0);              // error: an error in the lambda body isn't in the immediate context

template <class T, std::size_t = sizeof([]() { T::invalid; })>
    void g(T);
void g(...);
g(0);              // error: likewise

template <class T>
    auto h(T) -> decltype([x = T::invalid]() { });
void h(...);
h(0);              // OK: the init-capture's initializer is in the immediate context, calls h(...)

template <class T>
    auto i(T) -> decltype([]() -> typename T::invalid { });
void i(...);
i(0);              // OK: the lambda's return type is in the immediate context, calls i(...)

template <class T>
    auto j(T t) -> decltype([](auto x) -> decltype(x.invalid) { } (t));
void j(...);
j(0);              // OK: return type deduction of the generic lambda fails, the call expression is invalid, calls j(...)
```

The declaration parts of a lambda (capture initializers, parameters, return type) are in the immediate context; the body isn't. Clang 23 reports errors for `f(0)` and `g(0)`, and the other three calls compile.

### Substitution proceeds in lexical order (¶7)

!!! std
    The substitution proceeds in lexical order and stops when a condition that causes deduction to fail is encountered.

Substitution proceeds in the order things appear in the source and stops when it hits something that causes deduction to fail. The order is specified because substitution may trigger instantiation, and instantiation may produce hard errors. A failure encountered earlier spares the later parts from substitution:

```cpp
template <class T> struct A { using X = typename T::X; };

template <class T> typename T::X f(typename A<T>::X);
template <class T> void f(...) { }

template <class T> auto g(typename A<T>::X) -> typename T::X;
template <class T> void g(...) { }

void x() {
    f<int>(0);    // OK: the return type int::X is substituted first, fails, stops
    g<int>(0);    // error: the parameter type is substituted first, instantiating A<int>, where int::X is a hard error
}
```

The only difference between `f` and `g` is whether the return type is written before or after: a trailing return type lexically follows the parameters. `f<int>` fails at the return type, and `A<int>` is never instantiated. Clang 23 reports an error only for `g<int>(0)`.

The last sentence of ¶7: if substitution into different declarations of the same function template would cause template instantiations to occur in a different order or not at all, the program is IFNDR (ill-formed, no diagnostic required). Using the two forms above as two declarations of the same template `h`, for example, `h<int>(0)` would fall into this case.

This ordering rule was clarified by [[CWG1227]] as a defect report against C++14. Before that the standard only said substitution happens in all types and expressions, and compilers used different orders.

### Common reasons for deduction failure (¶11–¶12)

¶11 Note 9 lists common reasons for deduction failure. It is only a non-exhaustive list of hints; the only normative rule is the one in ¶8.

| ¶ | Reason | Example |
|---|---|---|
| 11.1 | expanding a pack expansion containing several packs of different lengths | `pair<A, B>...` where `A` and `B` differ in length |
| 11.2 | creating an array of `void`, functions or references, or an array of zero or negative size | `template<class T> int f(T[5]); f<void>(0);` |
| 11.3 | using a non-class, non-enumeration type in a qualified name | `template<class T> int f(typename T::B*); f<int>(0);` |
| 11.4 | the type in a qualified name has no such member, or the member is of the wrong kind | see below |
| 11.5 | creating a pointer to reference | `T*` with `T = int&` |
| 11.6 | creating a reference to `void` | `T&` with `T = void` |
| 11.7 | creating a pointer to member of `T` when `T` isn't a class type | `template<class T> int f(int T::*); f<int>(0);` |
| 11.8 | giving a constant template parameter an invalid type | using a value of non-structural type as a constant template argument |
| 11.9 | an invalid conversion in a template argument expression or an expression in a function declaration | `template<class T, T*> int f(int); f<int, 1>(0);` |
| 11.10 | creating a function type with a `void` parameter, or returning a function or array | `T(int)` with `T = int[3]` |
| 11.11 | giving the explicit object parameter of a lambda's call operator a disallowed type | — |

The cases of ¶11.4:

```cpp ok
template <int I> struct X { };
template <template <class T> class> struct Z { };
template <class T> void f(typename T::Y*) { }
template <class T> void g(X<T::N>*) { }
template <class T> void h(Z<T::template TT>*) { }
template <class T> void f(...) { }
template <class T> void g(...) { }
template <class T> void h(...) { }

struct A { };
struct B { int Y; };
struct C { typedef int N; };
struct D { typedef int TT; };

int main() {        // on each line the first template fails deduction and the (...) version is called
    f<A>(0);        // A has no member Y
    f<B>(0);        // B::Y isn't a type
    g<C>(0);        // C::N isn't a value
    h<D>(0);        // D::TT isn't a template
}
```

The standard writes the parameter of `h` as `Z<T::TT>*`; Clang 23 requires the `template` disambiguator, so it is rewritten accordingly here.

¶12 Substitution also fails when a constant template argument would require a narrowing conversion:

```cpp
template <int> int f(int);
template <signed char> int f(int);
int i1 = f<1000>(0);    // OK: 1000 to signed char narrows, the second template fails deduction
int i2 = f<1>(0);       // error: ambiguous, 1 doesn't narrow, both templates are viable
```

This assumes `signed char` can't represent 1000.

## Taking the address of a function template ([temp.deduct.funcaddr])

```cpp ok
template<class T> T twice(T x) { return x + x; }
int    (*pf)(int)    = twice;       // T = int: deduced from the target type
double (*pd)(double) = &twice;      // T = double
auto pa = &twice<long>;             // no target type: must be specified explicitly
void take(int (*)(int));
void use() { take(twice); }         // the target is the parameter type
```

¶1 When taking the address of an overload set containing a function template, template arguments can be deduced from the target type. The target type is the pointer or reference being initialized, the left operand of an assignment, a function parameter, the target of a cast, and so on ([[over.over]]). With a target, the function template's function type is `P`, the target type is `A`, and deduction follows [[temp.deduct.type]]. Without a target, `P` and `A` are both empty, and template arguments can only come from explicit arguments and defaults:

```cpp error
template<class T> T twice(T x) { return x + x; }
auto pa = &twice;                   // error: no target, T can't be deduced
```

¶2 A placeholder type (`auto`) in the return type of the function template is a non-deduced context. After deduction succeeds, the return type is determined by instantiating the function body:

```cpp ok
template<class T> auto ret(T x) { return x; }
int (*pr)(int) = ret;   // T deduced from the parameter as int; the return type is int after instantiation
```

## Conversion function templates ([temp.deduct.conv])

```cpp run ok
#include <cstdio>
struct Any {
    template<class T> operator T() const { std::puts("operator T"); return T(); }
};
struct Ref {
    template<class T> operator T&() { static T t{}; std::puts("operator T&"); return t; }
};

int main() {
    Any a;
    int x = a;            // T = int
    double d = a;         // T = double
    Ref r;
    int y = r;            // P = T&, ¶2: compare using T, T = int
    const int& cy = r;    // A = const int&, ¶4: compare using const int, T = const int
    (void)x; (void)d; (void)y; (void)cy;
}
```

¶1 Template arguments of a conversion function template `operator T()` are deduced with its return type as `P` and the type required as the result of the conversion as `A`, per [[temp.deduct.type]]. If the conversion function is being considered in overload resolution ([[over.match.funcs]]), the following adjustments are made before comparing. They go in the opposite direction from those in call deduction: in a call `P` is the parameter and `A` the argument; here `P` is the type the conversion produces and `A` the type needed.

| ¶ | Adjustment |
|---|---|
| 2 | if `P` is a reference type, use the type referred to instead of `P` |
| 3 | if `A` isn't a reference type: if `P` is an array, replace it by a pointer; if a function, by a function pointer; otherwise remove `P`'s top-level cv |
| 4 | remove `A`'s top-level cv; if `A` is a reference type, use the type referred to |
| 5 | in general the deduced `A` must be identical to `A`. If deduction would otherwise fail, three differences may be ignored: the cv of the referred type when the original `A` is a reference (5.1); the exception specification when the original `A` is a potentially-throwing pointer to function or pointer to member function (5.2); cv that a qualification conversion can restore (5.3). If this leaves more than one possibility, deduction fails |

A class like `Any` that converts to any type makes lots of overload resolutions ambiguous and should be avoided in real code.

## Deduction during partial ordering ([temp.deduct.partial])

When two function templates can both match a call, [[g:partial-ordering|partial ordering]] ([[temp.func.order]]) decides which is more specialized. Partial ordering is also used to determine which template an explicit specialization or explicit instantiation belongs to ([[temp.deduct.decl]]), and when taking the address of an overloaded function template. [[temp.func.order]] specifies how a template is transformed into a concrete form: each template parameter is replaced by a unique synthesized type, value or template. This subclause specifies how deduction works after the transformation.

```cpp run ok
#include <cstdio>
template<class... Args>           void f(Args...)     { std::puts("#1"); }
template<class T1, class... Args> void f(T1, Args...) { std::puts("#2"); }
template<class T1, class T2>      void f(T1, T2)      { std::puts("#3"); }

int main() {
    f();          // #1: only #1 is viable
    f(1, 2, 3);   // #2: #2 is more specialized than #1
    f(1, 2);      // #3: the non-variadic #3 is more specialized than the variadic #1 and #2
}
```

### Deduction in both directions (¶1–¶4, ¶8, ¶10)

¶2 Each template has an original function type and a transformed function type. Deduction is done with one template's transformed form as the argument template and the other's original form as the parameter template, then again with the roles swapped.

Intuitively, partial ordering asks: does template 2 accept every kind of argument that template 1 accepts? If template 2 can be deduced from an arbitrary instance of template 1, template 2 is at least as general as template 1, which is to say template 1 is at least as specialized as template 2.

¶3 The types compared depend on the context:

- ¶3.1 a function call: the types of the function parameters that have corresponding arguments. Default arguments aren't arguments (footnote 112); they only become arguments after the function is selected;
- ¶3.2 a call to a conversion function: the return types of the conversion function templates;
- ¶3.3 other contexts: the whole function type.

¶4 Each type in the parameter template and the corresponding type in the argument template are used as `P` and `A` respectively.

¶8 If `A` came from a function parameter pack and `P` isn't a pack, deduction fails. Otherwise deduction follows [[temp.deduct.type]]; if `P` is a function parameter pack, it is compared with each remaining parameter type of the argument template. If deduction succeeds for a given type, the type from the argument template is said to be at least as specialized as the type from the parameter template.

¶10 If, for each pair of types used for ordering, the type from `F` is at least as specialized as the type from `G`, `F` is [[g:at-least-as-specialized|**at least as specialized as `G`**]]. `F` is **more specialized** than `G` if `F` is at least as specialized as `G` and not the other way round.

### Adjustments before comparing, and the reference tie-breaker (¶5–¶7, ¶9)

Before comparing, `P` and `A` are adjusted:

- ¶5 a reference type is replaced by the type it refers to;
- ¶6 if `P` and `A` were both originally references, note which one is more cv-qualified, for use in ¶9;
- ¶7 top-level cv is removed from both.

¶9 If after adjustment the two types are identical and `P` and `A` were both originally references, two more comparisons are made: if the argument template's type was an lvalue reference and the parameter template's wasn't, the parameter type isn't considered at least as specialized (¶9.1); otherwise, if the argument template's type is more cv-qualified, the parameter type isn't considered at least as specialized either (¶9.2).

```cpp run ok
#include <cstdio>
template<class T> void q(T&&) { std::puts("q(T&&)"); }
template<class T> void q(T&)  { std::puts("q(T&)"); }

int main() {
    int i = 0;
    q(i);    // q(T&): both deduce q(int&), ¶9.1 makes T& more specialized
    q(0);    // q(T&&): q(T&) isn't viable
}
```

### Trailing packs and unused parameters (¶11–¶13)

¶11 If by the above `F` and `G` are each at least as specialized as the other, and `G` has a trailing function parameter pack for which `F` has no corresponding parameter, and `F` has no trailing function parameter pack, then `F` is more specialized. This handles comparing `f(T)` and `f(T, Args...)` with a single argument: the pack has no corresponding argument and doesn't appear in the comparison of ¶3.1.

¶12 In general, deduction fails if some template parameter has no value. But in partial ordering, a template parameter may remain without a value as long as it doesn't appear in the types used for ordering. Note 2 explains that appearing in a non-deduced context counts as appearing.

```cpp ok
template <class T> T f(int);            // #1
template <class T, class U> T f(U);     // #2
void g() {
    f<int>(1);                          // calls #1
}
```

Both are viable, and only the types of parameters with arguments are used for ordering: `int` for #1, `U` for #2. Deducing #2's `U` from #1's `int` succeeds, and `T` doesn't appear in the compared types, so it needs no value. The other way round, deducing #1's `int` from a synthesized type fails. So #1 is more specialized.

¶13 Note 3 points out that partial ordering of function templates containing template parameter packs is independent of how many arguments were deduced for the packs:

```cpp run ok
#include <cstdio>
template<class...> struct Tuple { };
template<class... Types>           void g(Tuple<Types...>)      { std::puts("#1"); }
template<class T1, class... Types> void g(Tuple<T1, Types...>)  { std::puts("#2"); }
template<class T1, class... Types> void g(Tuple<T1, Types&...>) { std::puts("#3"); }

int main() {
    g(Tuple<>());              // #1
    g(Tuple<int, float>());    // #2
    g(Tuple<int, float&>());   // #3
    g(Tuple<int>());           // #3: Types is empty, #2 and #3 both match, #3 is more specialized
}
```

On the last line, `Types&...` and `Types...` are both deduced as empty packs and seem indistinguishable. But partial ordering compares patterns, not how many elements were deduced, and `Types&...` is more specialized than `Types...`.

## Deduction from a function declaration ([temp.deduct.decl])

```cpp ok
template<class T> void f(T) { }      // #1
template<class T> void f(T*) { }     // #2
template<> void f(int*) { }          // both match, #2 is more specialized: this is #2's f<int>
template void f(double*);            // likewise: instantiates #2's f<double>
```

¶1 If the *declarator-id* of a declaration refers to a function template specialization, deduction determines which specialization it refers to. This is used for explicit instantiations, explicit specializations and certain friend declarations, and also to determine whether a deallocation function template specialization matches a placement operator new ([[basic.stc.dynamic.deallocation]], [[expr.new]]). `P` is the type of the candidate function template, `A` is the function type in the declaration (or the type of the deallocation function that would match the placement allocation function), and deduction follows [[temp.deduct.type]].

¶2 If, after partial ordering is considered, there is no matching template or more than one, deduction fails; in a declaration, the program is ill-formed:

```cpp error
template<class T> void f(T, int);
template<class T> void f(int, T);
template<> void f(int, int);   // error: both templates match, and partial ordering can't separate them
```

Which template a specialization belongs to depends on which templates are visible when it is declared. The example in [[temp.expl.spec]] where moving a specialization changes the result of a call comes from this mechanism.

[[temp.deduct.type#10]] has a special adjustment for this kind of deduction: if the top-level parameter is a forwarding reference `T&&` and `A` is an lvalue reference, `P` is treated as `T`. So `template<> void f(int&)` can be recognized as `f<int&>` of `template<class T> void f(T&&)`.

## Implementation notes

!!! impl "How compilers implement SFINAE"
    - Compilers trap diagnostics during substitution: errors produced in the immediate context aren't emitted but turned into deduction failures (Clang internally calls this a SFINAE trap). Once work outside the immediate context begins, such as instantiating class templates or generating implicit members, the trap is suspended and diagnostics are emitted as usual. This corresponds exactly to Notes 6 and 7 under ¶8.
    - When reporting that no function matches, compilers list the removed candidates and the reasons in notes (Clang writes substitution failure); this is the main tool for debugging SFINAE.
    - Large numbers of `std::enable_if`-based overloads are expensive, since every candidate undergoes a full substitution. Constraints can eliminate candidates at the constraint check step of ¶5, and satisfaction results are cached, so they are usually faster and give clearer diagnostics.

## Common misconceptions

!!! pitfall "If it's in the signature, it's in the immediate context"
    `typename Wrap<T>::type` is written in the signature, but the error occurs in the class body of `Wrap<T>`, outside the immediate context, so it's a hard error. Similarly, in `decltype(T{})`, if `T`'s default constructor is implicitly defined and that definition is ill-formed (for example because some member can't be default-constructed), generating the implicit definition isn't in the immediate context either.

!!! pitfall "An `auto` return type takes part in SFINAE"
    The return type of `template<class T> auto size_of(const T& c) { return c.size(); }` can only be obtained by instantiating the function body, which isn't in the immediate context. Calling it with an unsuitable type causes a hard error while instantiating the body. For SFINAE, write `-> decltype(c.size())`, or use a constraint.

## Questions

!!! question "Question 1"
    Which of the following calls cause hard errors?
    ```cpp
    template<class T> struct Bad { static_assert(sizeof(T) == 0); using type = int; };
    template<class T> typename Bad<T>::type a(T);     void a(...);
    template<class T> decltype(Bad<T>{}) b(T);        void b(...);
    template<class T, class = typename T::type> void c(T); void c(...);
    void t() { a(1); b(1); c(1); }
    ```

<details markdown="1">
<summary>Answer</summary>

`a(1)`: substituting `Bad<int>::type` requires instantiating `Bad<int>`; the `static_assert` in the class body fails outside the immediate context, a hard error.

`b(1)`: `Bad<int>{}` needs a complete type, which also requires instantiating `Bad<int>`, a hard error.

`c(1)`: `int::type` is written directly in the template parameter list (a substitution locus per ¶7.3), and uses a non-class type in a qualified name (¶11.3), so deduction fails and `c(...)` is called, with no error.

Compiling the three calls separately with Clang 23 gives exactly these results.
</details>

!!! question "Question 2"
    ```cpp
    template<class T> void f(T*, const T&);   // #1
    template<class T> void f(T, T&);          // #2
    ```
    Which one does `int i; f(&i, i);` call?

<details markdown="1">
<summary>Answer</summary>

#1. #1 deduces `T = int`, with parameters `(int*, const int&)`. #2 deduces `T = int*` from the first argument and `T = int` from the second, a conflict, so deduction fails. Only #1 is viable, and partial ordering never comes into play. Partial ordering only matters when both templates deduce successfully.
</details>
