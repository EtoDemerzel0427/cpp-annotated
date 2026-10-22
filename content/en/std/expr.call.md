---
title: Function call
summary: "Everything a function call expression means once the function is chosen: what can be called, virtual calls, the type and value category of the result, initialization and destruction of parameters, C++17 evaluation order, variadic arguments and default argument promotions, the UB of calling through the wrong function type, and the evaluation order of C++26 contract assertions."
updated: 2026-10-19
---

!!! tldr
    - A call returning an lvalue reference is an lvalue, one returning an rvalue reference to an object is an xvalue, and everything else is a prvalue; this rule is exactly how `std::move` produces an xvalue.
    - Since C++17, the callee expression is evaluated before all arguments; parameter initializations don't interleave with each other, but which goes first is unspecified.
    - Whether parameters are destroyed when the function returns or at the end of the full-expression containing the call is implementation-defined; GCC and Clang on common platforms do the latter.
    - Arguments passed through `...` undergo the default argument promotions: `float` becomes `double`, `char` and `short` become `int`.
    - Calling a function through a function pointer of a mismatched type is UB; the only allowed mismatch is dropping `noexcept`.

```cpp run title="chained-replace.cpp" ok
#include <cassert>
#include <string>

int main() {
    std::string s = "but I have heard it works even if you don't believe in it";
    s.replace(0, 4, "").replace(s.find("even"), 4, "only").replace(s.find(" don't"), 6, "");
    assert(s == "I have heard it works only if you believe in it");   // guaranteed since C++17
}
```

This is Example 4 in the standard. It comes from a popular C++ textbook, and someone later found that under C++14 it wasn't guaranteed to be correct: the second `s.find("even")` might be evaluated before the first `replace`, giving the wrong position. Since C++17 it always holds, based on the evaluation order in [[expr.call#8]].

Operator overloads, constructors, lambdas and `std::invoke` all eventually come down to a function call. When a name refers to an overload set, which function is chosen is decided by overload resolution ([[over.match.call]]); [expr.call] specifies what happens after the function is chosen.

## What can be called (¶1–¶3)

¶1 A function call is a postfix expression followed by parentheses containing a possibly empty, comma-separated list of *initializer-clause*s, which are the **arguments** of the function. Arguments can be braced lists, `f({1, 2})`, or pack expansions, `f(xs...)`.

The postfix expression before the parentheses (the callee expression below) must have function type or pointer-to-function type. For a call to a non-member function or a static member function, the callee expression is either an lvalue referring to a function, in which case the function-to-pointer conversion ([[conv.func]]) is not applied, or a prvalue of function pointer type.

```cpp run title="callee-forms.cpp" ok
int f(int x) { return x + 1; }

int main() {
    int (&rf)(int) = f;
    int (*pf)(int) = f;
    int a = f(1);        // lvalue referring to a function
    int b = rf(1);       // function lvalue (through a reference)
    int c = pf(1);       // function pointer prvalue (pf undergoes lvalue-to-rvalue conversion first)
    int d = (*pf)(1);    // *pf is a function lvalue
    int e = (**********pf)(1);   // each * gives a function lvalue, which decays to a pointer again; still valid
    return (a + b + c + d + e == 10) ? 0 : 1;
}
```

For a call to a non-static member function, the callee expression is a class member access `E1.E2`, or the implicit `(*this).E2`. By [[expr.ref#8]], `E1.E2` is then a prvalue that can only be called immediately; the pointer-to-member form `(obj.*pmf)(args)` is the same ([[expr.mptr.oper]]).

¶2 If the selected function is not virtual, or the member access uses a qualified name (`p->Base::f()`), that function is called. Otherwise, what is called is, in the [[g:dynamic-type|dynamic type]] of the object expression, the function's [[g:final-overrider|final overrider]] ([[class.virtual]]); this is a [[g:virtual-function-call|virtual function call]]. Note 2 adds that for an object under construction or destruction, the behavior of virtual calls is specified by [[class.cdtor]].

```cpp run title="virtual-call.cpp" ok
struct B { virtual int f() { return 1; } };
struct D : B { int f() override { return 2; } };

int main() {
    D d;
    B& b = d;
    int x = b.f();        // virtual call: D::f, gives 2
    int y = b.B::f();     // qualified name: not a virtual call, B::f, gives 1
    int (B::*pmf)() = &B::f;
    int z = (b.*pmf)();   // calling a virtual function through a member pointer: still dispatches to D::f
    return (x == 2 && y == 1 && z == 2) ? 0 : 1;
}
```

¶3 is a note: if a function name is used and name lookup finds no declaration, the program is ill-formed; a call doesn't implicitly declare a function. C89 would treat an undeclared `foo()` as `int foo()`.

## The result of the call (¶4, ¶9, ¶15)

### Value category (¶15)

¶15 The value category of a call expression is determined by the return type:

| Return type | Value category | Example |
|---|---|---|
| Lvalue reference `T&` | lvalue | `v.front()`, `std::cout << x` |
| Rvalue reference to function `F&&` | lvalue | Rare |
| Rvalue reference to object `T&&` | xvalue | `std::move(x)`, `std::forward<T>(t)` |
| Non-reference type | prvalue | `f()`, `std::string()` |

`std::move` is just a function returning `T&&`; by this table its call is an xvalue, and it moves nothing itself. See [[topics/value-categories]].

If the call is a non-`void` prvalue, its type must be complete, except in the cases specified by [[dcl.type.decltype]]: a function call that is the operand of `decltype` doesn't require a complete return type and introduces no temporary. So metaprogramming can do type deduction on functions returning incomplete types.

```cpp title="incomplete-return.cpp" error
struct I;
I make();
I& make_ref();

using T = decltype(make());   // OK: the decltype exception
void h() {
    make_ref();               // OK: returns a reference, the result is an lvalue
    make();                   // error: the prvalue's type I is incomplete
}
```

### The type comes from the statically chosen function (¶4, ¶9)

¶4 The type of a call expression is the return type of the statically chosen function (i.e. ignoring `virtual`), even if the function actually called has a different return type. This corresponds to covariant return types. ¶9 adds that the result of the call is the operand of the `return` statement that transferred control out of the called function (possibly converted, [[stmt.return]]); if the final overrider in a virtual call has a different return type, the return value is further converted to the return type of the statically chosen function, including any necessary pointer adjustment.

```cpp run title="covariant.cpp" ok
#include <type_traits>

struct B { virtual B* clone() const { return new B(*this); } virtual ~B() = default; };
struct D : B { D* clone() const override { return new D(*this); } };

int main() {
    D d;
    const B& b = d;
    static_assert(std::is_same_v<decltype(b.clone()), B*>);   // B::clone statically chosen
    static_assert(std::is_same_v<decltype(d.clone()), D*>);   // D::clone statically chosen
    B* p = b.clone();     // actually calls D::clone; the returned D* is converted to B* (¶9)
    delete p;
}
```

### Destructors and pseudo-destructors (¶4)

When the callee expression designates a destructor or pseudo-destructor ([[expr.prim.id.dtor]]), the call has type `void`. A pseudo-destructor is the destructor notation for scalar types, e.g. `p->~T()` with `T` being `int`. Calling it destroys the scalar object designated by the object expression, i.e. ends its lifetime ([[basic.life]]). This provision was added in C++20 by [[P0593R6]]; before that, a pseudo-destructor call had no effect at all.

```cpp run title="pseudo-dtor.cpp" ok
#include <new>

template<class T> void destroy(T* p) { p->~T(); }   // a pseudo-destructor call when T is int

int main() {
    int x = 1;
    destroy(&x);          // since C++20: x's lifetime ends
    ::new (&x) int(2);    // recreate an int in the same storage; the name x can be used afterward
    return x == 2 ? 0 : 1;
}
```

## Initializing parameters (¶7)

### Matching arguments to parameters

¶7 When a function is called, each parameter is initialized with its corresponding argument ([[dcl.init]], [[class.copy.ctor]]). This is copy-initialization, so `explicit` constructors can't be used to convert arguments implicitly. A parameter with no corresponding argument uses its default argument ([[dcl.fct.default]]).

Example 2 in the standard is an easy trap:

```cpp title="default-arg-pack.cpp" error
template<typename... T> int f(int n = 0, T... t);
int x = f<int>();   // error: no argument for the second parameter
```

After `T` is explicitly specified as `int`, the second parameter `int t` has neither an argument nor a default argument.

C++23's explicit object member functions ([[P0847R7]]) have an explicit object parameter. If the call has an implied object argument, i.e. the `obj` in `obj.f(args)` ([[over.call.func]]), it is placed at the front of the argument list and corresponds to the explicit object parameter.

```cpp run title="explicit-object.cpp" ok
struct S {
    int v = 1;
    int get(this const S& self) { return self.v; }
    int add(this S self, int k) { return self.v + k; }    // by value: self is a copy
};

int main() {
    S s;
    int a = s.get();               // the implied object argument s corresponds to self
    int b = s.add(2);              // s copy-initializes self, 2 initializes k
    auto pf = &S::add;             // the address of an explicit object member function is an ordinary function pointer
    int c = pf(s, 3);              // called like an ordinary function
    return (a == 1 && b == 3 && c == 4) ? 0 : 1;
}
```

A traditional non-static member function has an implicit object parameter ([[over.match.funcs]]). In the call, the object expression of the member access must be a glvalue, and the implicit object parameter is initialized with that glvalue as if by an explicit type conversion. Note 5 explains why it is worded this way: this derived-to-base conversion doesn't repeat access and ambiguity checks, since they were already done for the member access ([[class.member.lookup]], [[class.access.base]], [[expr.ref]]).

### Parameter types must be complete and non-abstract

At the call, a parameter type can't be an incomplete or abstract class type. Note 6 says parameters of pointer or reference to such types are still fine. The check happens at the call; the declaration `void f(Incomplete);` itself is valid.

```cpp title="incomplete-param.cpp" error
struct Inc;
struct Abs { virtual void g() = 0; };
void f(Inc);          // OK: may be incomplete at the declaration
void a(Abs);          // OK: the declaration itself is valid, it just can't be defined or called
void k(Inc* p) {
    f(*p);            // error: the parameter type Inc is incomplete at the call
}
```

## Evaluation order (¶8)

¶8 The C++17 evaluation-order proposal [[P0145R3]] established the following:

1. The callee expression is sequenced before each argument and each default argument.
2. The initialization of each parameter, including every associated value computation and side effect, is [[g:indeterminately-sequenced|indeterminately sequenced]] with respect to the initializations of the other parameters: one comes before the other, but which is unspecified. If the implementation introduces temporaries to hold parameter values, this refers to the initialization of those temporaries.
3. All of the above is sequenced before the evaluation of the precondition assertions, which are evaluated in order {{c++26}}.
4. If temporaries holding parameter values were introduced, the initialization of the parameter objects from those temporaries is indeterminately sequenced with respect to the precondition assertions {{c++26}}.

Note 7 adds that all side effects of argument evaluations are complete before the function is entered.

The `replace` chain at the top uses item 1. The callee expression of each `.replace(...)` is "the previous call's `.replace`", which contains the previous call itself, so it comes before this call's argument `s.find(...)`. So each `find` runs after the preceding `replace`.

"Including every associated value computation and side effect" in item 2 means one argument's evaluation happens as a whole and doesn't interleave with another argument's. Before C++17 there was no such guarantee: `f(std::unique_ptr<A>(new A), g())` could execute `new A`, then call `g()`, and only then construct the `unique_ptr`; if `g()` threw, the memory leaked.

```cpp run title="unique-ptr-leak.cpp" ok
#include <memory>
#include <stdexcept>

struct A {};
int g() { throw std::runtime_error("boom"); }
void f(std::unique_ptr<A>, int) {}

int main() {
    try {
        f(std::unique_ptr<A>(new A), g());   // no leak since C++17
    } catch (...) {}
}
```

The order among arguments is still unspecified, and implementations differ: on x86-64, GCC usually evaluates arguments right to left, Clang usually left to right. An early version of P0145 proposed mandating left to right, but in the end only "no interleaving, unspecified order" was adopted.

### Operator notation versus function notation

Note 8 points out that when an overloaded operator is called with operator notation, the arguments are evaluated in the order of the built-in operator ([[over.match.oper]]); with function call notation, by the rules of this subclause. Example 5 in the standard:

```cpp run title="operator-order.cpp" unspecified
struct S { S(int) {} };
int operator<<(S, int) { return 0; }

int main() {
    int i, j;
    int x = S(i = 1) << (i = 2);          // operator notation: built-in << order, left before right, i is 2
    int y = operator<<(S(j = 1), j = 2);  // function notation: whether j is 1 or 2 is unspecified
    return x + y + i + j;
}
```

Clang 23 reports `-Wunsequenced` for the second line. The wording is inaccurate under C++17: the two arguments are indeterminately sequenced, not unsequenced, and the result is unspecified, not UB.

!!! lawyer "Order in constant evaluation"
    [[intro.execution#16]] says that during evaluation as a core constant expression, subexpressions that would otherwise be unsequenced or indeterminately sequenced are evaluated in lexical order, and default arguments are evaluated in the order they would appear in the argument positions. So the result of constant evaluation doesn't depend on the implementation.

## When parameters are destroyed (¶7)

!!! std
    It is implementation-defined whether a parameter is destroyed when the function in which it is defined exits or at the end of the enclosing full-expression; parameters are always destroyed in the reverse order of their construction.

¶7 Whether a parameter is destroyed when the function exits or at the end of the full-expression containing the call is implementation-defined; either way, parameters are destroyed in the reverse order of construction.

```cpp run title="param-destroy.cpp" impl
#include <cstdio>

struct P {
    const char* n;
    P(const char* n) : n(n) { std::printf("ctor %s\n", n); }
    ~P() { std::printf("dtor %s\n", n); }
};
struct T { ~T() { std::puts("dtor temp"); } };

int f(P, P) { std::puts("in f"); return 0; }
int g(int, const T&) { std::puts("in g"); return 0; }

int main() {
    g(f(P("a"), P("b")), T{});
    std::puts("next statement");
}
// Output with Clang 23 (arm64, Itanium ABI) in our tests:
// ctor a / ctor b / in f / in g / dtor temp / dtor b / dtor a / next statement
// f's parameters are not destroyed until the whole full-expression ends, after g returns.
```

This is implementation-defined because it is part of the calling convention. In the Itanium C++ ABI (GCC and Clang on Linux and macOS), a non-trivial class object passed by value is constructed by the caller on its own stack, its address is passed to the callee, and the caller destroys it at the end of the full-expression. In the MSVC ABI the callee destroys the parameters before returning, so in the example above `dtor b` and `dtor a` would appear after `in f` and before `in g`.

¶7 also says the initialization and destruction of parameters occur within the context of the full-expression containing the call ([[intro.execution]]). Example 3 gives two consequences:

1. Access checking of the parameter's constructor, conversion functions and destructor happens at the call site, with the caller's permissions.
2. An exception thrown by the construction or destruction of a parameter is not caught by the callee's *function-try-block*, because at that point we are not yet in the callee.

!!! impl "Passing non-trivial objects by value in the Itanium ABI"
    If a class has a non-trivial copy constructor, move constructor or destructor, the Itanium ABI passes it by value by constructing the argument in temporary storage in the caller and passing its address; the callee's parameter is that storage. So passing `std::unique_ptr<T>` by value costs an extra memory access compared with a raw pointer: its destructor is non-trivial, so it can't be passed in a register. Clang's `[[clang::trivial_abi]]` attribute can change this, at the cost of the callee destroying the parameter instead.

## Variadic arguments (¶12–¶13)

¶12 A function can be declared to accept fewer arguments than parameters (default arguments), or more arguments than parameters (an ellipsis `...` or a function parameter pack).

```cpp run title="varargs.cpp" ok
#include <cstdarg>
#include <cstdio>

void show(int n, ...) {
    std::va_list ap;
    va_start(ap, n);
    double d = va_arg(ap, double);   // float is promoted to double; va_arg(ap, float) is wrong
    int c = va_arg(ap, int);         // char is promoted to int
    void* p = va_arg(ap, void*);     // nullptr is converted to void*
    std::printf("%g %c %p\n", d, c, p);
    va_end(ap);
}

int main() { show(3, 1.5f, 'x', nullptr); }
```

¶13 An argument with no corresponding parameter, i.e. one matching `...`, is passed in such a way that the receiver can obtain it with `va_arg` ([[support.runtime]]). Note 11 says this doesn't involve function parameter packs: a pack is expanded at instantiation, and every argument has a corresponding parameter. `...` arguments go through the following steps:

1. The lvalue-to-rvalue, array-to-pointer and function-to-pointer conversions are applied; `std::nullptr_t` is converted to `void*`.
2. If after conversion it doesn't have arithmetic, enumeration, pointer, pointer-to-member or class type, the program is ill-formed.
3. Passing a potentially-evaluated argument of scoped enumeration type, or of class type with a non-trivial copy constructor, move constructor or destructor, is [[g:conditionally-supported|conditionally-supported]] with implementation-defined semantics.
4. Integral and enumeration types subject to integral promotion are promoted ([[conv.prom]]), and `float` is promoted to `double` ([[conv.fpprom]]). These are called the [[g:default-argument-promotions|default argument promotions]].

The default argument promotions come from K&R C. Without a prototype the callee doesn't know the argument types, so the convention was to pass narrower types as `int` or `double`. That is why `printf("%f", 1.0f)` works and why `va_arg(ap, float)` is UB: the type given to `va_arg` must be compatible with the promoted type.

Passing a non-trivial class object through `...` is only conditionally-supported because `va_arg` can only move bytes, while a non-trivial object needs its copy constructor and destructor called, and the standard can't specify who calls them and when.

```cpp title="varargs-nontrivial.cpp" error
#include <string>
void v(int, ...);

void f() {
    std::string s;
    v(1, s);                      // error (Clang): Clang doesn't support this
    using R = decltype(v(1, s));  // OK: unevaluated operand, not restricted
    v(1, f);                      // OK: a function pointer after the function-to-pointer conversion
}
```

Clang 23 rejects `v(1, s)` with cannot pass object of non-trivial type through variadic function (controlled by `-Wnon-pod-varargs`, an error by default). GCC accepts it and passes a copy; `-Wconditionally-supported` gives a warning. For a scoped enumeration passed through `...`, Clang gives no diagnostic at all in our tests.

The restriction to potentially-evaluated arguments is deliberate: passing non-trivial objects through `...` inside unevaluated operands like `sizeof` and `decltype` is harmless, so SFINAE idioms like `decltype(check(std::declval<T>()))` with a `check(...)` fallback are unaffected.

## Calling through an incompatible function type: UB (¶6)

¶6 first defines a term: if a function type `Tcall` is the same as `Tfunc`, or "pointer to `Tfunc`" can be converted to "pointer to `Tcall`" by a function pointer conversion ([[conv.fctptr]], i.e. dropping `noexcept`), then `Tcall` is [[g:call-compatible|call-compatible]] with `Tfunc`.

!!! std
    Calling a function through an expression whose function type is not call-compatible with the type of the called function's definition results in undefined behavior.

In other words, the only allowed mismatch is that the expression's type is potentially throwing while the called function is actually `noexcept` (Note 4). The other way around, calling a potentially-throwing function through a `noexcept` function type is UB, because the compiler may assume the call doesn't throw and omit the exception-handling code.

```cpp run title="call-compatible.cpp" flags="-std=c++2c -fsanitize=function" ub
void may_throw() {}
void nothrow() noexcept {}
void takes_int(int) {}

int main() {
    void (*p)() = nothrow;           // OK: the function pointer conversion drops noexcept
    p();                             // OK: void() is call-compatible with void() noexcept
    auto q = reinterpret_cast<void (*)() noexcept>(&may_throw);
    q();                             // UB: void() noexcept is not call-compatible with void()
    auto r = reinterpret_cast<void (*)()>(&takes_int);
    r();                             // UB: different parameter lists
    auto s = reinterpret_cast<void (*)(int)>(r);
    s(1);                            // OK: converted back to the original type before calling
}
```

Converting a function pointer with `reinterpret_cast` is itself valid ([[expr.reinterpret.cast#6]]); calling through the wrong type is what is UB. In our tests, Clang 23's `-fsanitize=function` reports `r()` at run time but not the `noexcept` mismatch in `q()`.

C also says calling through an incompatible type is UB, though C's notion of compatible types is broader. The most common violation in practice is casting `int cmp(const Foo*, const Foo*)` to `int (*)(const void*, const void*)` to pass to `qsort`. It happens to work on common ABIs, but it is UB, and builds with control-flow integrity (CFI) checks will stop it.

## Order of contract assertions (¶5, ¶10) {{c++26}}

C++26 allows precondition assertions `pre` and postcondition assertions `post` on function declarations ([[dcl.contract.func]], [[P2900R14]]). ¶5 specifies which assertions are checked for a call, and in what order:

| Item | Assertions |
|---|---|
| ¶5.1 | If the callee expression is a class member access and this is a virtual call: the preconditions of the statically chosen function |
| ¶5.2 | The preconditions of the function actually called |
| ¶5.3 | The postconditions of the function actually called |
| ¶5.4 | If the callee expression is a class member access and this is a virtual call: the postconditions of the statically chosen function |

The caller sees the interface of the static type, whose contract must be checked; the overrider's own contract must be checked too. Preconditions go from interface to implementation, postconditions from implementation back to interface, forming a symmetric nesting. The key points of Example 1 in the standard:

```cpp title="contracts-virtual.cpp"
struct X1 { virtual void f() pre(a) post(b) {} };
struct Y : X1 { void f() override pre(e) post(f) {} };

void t(Y& y) {
    X1& x = y;
    x.f();          // virtual call: a, e, f, b
    x.X1::f();      // qualified name, not a virtual call: a, b
    y.f();          // Y::f is the statically chosen function: e, f
    void (X1::*pmf)() = &X1::f;
    (x.*pmf)();     // call through a member pointer: only e, f
}
```

The last line is easy to misread. ¶5.1 and ¶5.4 add the statically chosen function's assertions only when the callee expression is a class member access; `.*` is not a class member access, so only the assertions of the function actually called are checked. Clang 23 doesn't support the contract syntax yet, so this example has not been verified by compiling.

¶10 When the called function returns normally, all postcondition assertions are evaluated in order. If the implementation introduces temporaries to hold the return value ([[class.temporary]]), the postconditions are indeterminately sequenced with the initialization of those temporaries or of the result object. All postconditions are sequenced before the destruction of the parameters, so postconditions can refer to parameters.

## Remaining wording

¶11 is a note: a function can modify its non-`const` parameters, but unless the parameter is a reference, the argument is unaffected; a `const T&` parameter binds to a temporary when needed.

¶14 allows recursive calls, except of `main`. [[basic.start.main]] goes further and says `main` shall not be used within a program. Clang 23 accepts `return main();` as an extension with a `-Wmain` warning.

## History and evolution

!!! history
    - C++11: passing non-trivial classes through `...` changed from UB to conditionally-supported; with rvalue references, ¶15 gained the xvalue row; `std::nullptr_t` passed through `...` is converted to `void*`.
    - C++17: callee before arguments, no interleaving between arguments ([[P0145R3]]); `noexcept` became part of the function type ([[P0012R1]]), which created the problem of calling a potentially-throwing function through a `noexcept` type that ¶6 deals with.
    - C++20: pseudo-destructor calls end the lifetime of scalar objects ([[P0593R6]]).
    - C++23: explicit object parameters ([[P0847R7]]).
    - C++26: evaluation order of contract assertions (¶5, ¶8, ¶10, [[P2900R14]]).

## Common misconceptions

!!! pitfall "`f(i++, i++)` is UB"
    Since C++17 the two modifications are indeterminately sequenced; the result is unspecified, either `f(0, 1)` or `f(1, 0)`, not UB. Clang's `-Wunsequenced` and GCC's `-Wsequence-point` still warn, and such code really shouldn't be written.

!!! pitfall "An RAII object passed by value is destroyed when the function returns"
    On the Itanium ABI, a guard object passed by value is not destroyed until the end of the whole full-expression. Code that depends on when parameters are destroyed is not portable.

!!! pitfall "A member function pointer can be called directly"
    `pmf(obj)` is ill-formed: a member function pointer is not a function pointer; write `(obj.*pmf)()` or `(ptr->*pmf)()`. The parentheses can't be omitted: `obj.*pmf()` parses as `obj.*(pmf())`. `std::invoke(pmf, obj)` unifies these forms. Explicit object member functions are the exception: their address is an ordinary function pointer.

## Questions

!!! question "Question 1"
    Under C++17, what is the difference between `std::cout << f() << g();` and `operator<<(operator<<(std::cout, f()), g());`?

<details markdown="1">
<summary>Answer</summary>

The operator notation follows the sequencing rule of the built-in `<<`: the left operand is sequenced before the right ([[expr.shift]]), so `f()` is always before `g()`. In the function call notation, the two arguments of the outer `operator<<`, `operator<<(std::cout, f())` and `g()`, are indeterminately sequenced, so `g()` may run first. This is the difference Note 8 talks about.
</details>

!!! question "Question 2"
    Is `void (*p)() noexcept = nullptr; void (*q)() = p;` valid? What about the reverse, `void (*r)() noexcept = q;`? If you force the conversion with `reinterpret_cast` and then call, when is it UB?

<details markdown="1">
<summary>Answer</summary>

`q = p` is valid: a function pointer conversion can drop `noexcept` ([[conv.fctptr]]). `r = q` is ill-formed: there is no implicit conversion that adds `noexcept`. `reinterpret_cast` can perform the conversion ([[expr.reinterpret.cast#6]]). Then, calling through `r`: if the called function's definition is not `noexcept`, "pointer to `void()`" can't be converted to "pointer to `void() noexcept`" by a function pointer conversion, so the types are not call-compatible and it is UB by ¶6; if the called function happens to be `noexcept`, the types are the same and there is no problem.
</details>

!!! question "Question 3"
    Given `struct S { void f() &&; }; S s;`, how is the implicit object parameter initialized in `std::move(s).f()`? And in `S().f()`?

<details markdown="1">
<summary>Answer</summary>

By ¶7, the object expression must be a glvalue, and it initializes the implicit object parameter of type `S&&`. `std::move(s)` is already an xvalue and binds directly. `S()` is a prvalue, but ¶7 requires a glvalue, so temporary materialization ([[conv.rval]]) is applied first, and the resulting xvalue binds to `S&&`.
</details>
