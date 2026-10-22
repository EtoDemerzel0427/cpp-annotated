---
title: Exception specifications
summary: "Whether a function can exit via an exception is decided by its exception specification: how noexcept is written, the defaults when it is absent (destructors and deallocation functions are non-throwing by default), the definition of potentially-throwing expressions, how compiler-generated functions deduce their exception specifications, the constraint on overriding virtual functions, and the consequences of the exception specification being part of the function type."
updated: 2026-10-19
---

!!! tldr
    - An exception specification distinguishes only two cases: the function may exit via an exception (potentially-throwing), or it will not (non-throwing). It does not list which types might be thrown.
    - `noexcept` is a promise, not a compile-time check: if an exception really does leave a `noexcept` function, the program calls `std::terminate`.
    - A function without `noexcept` is potentially-throwing by default, except for destructors, deallocation functions and functions defaulted on their first declaration, whose exception specifications are deduced by the compiler; a destructor usually comes out non-throwing.
    - The result of the `noexcept(expr)` operator depends on whether the expression has potentially-throwing subexpressions, including the destruction of temporaries.
    - Since C++17 the exception specification is part of the function type: a pointer to a `noexcept` function converts to an ordinary function pointer but not the other way round, and a function overriding a non-throwing virtual function must be non-throwing too.

```cpp run title="vector-move-if-noexcept.cpp" ok
#include <cstdio>
#include <vector>

template<bool NX>
struct W {
    W() = default;
    W(const W&) { std::puts("  copy"); }
    W(W&&) noexcept(NX) { std::puts("  move"); }
};

int main() {
    std::puts("noexcept move:");
    std::vector<W<true>> a(1);  a.reserve(2);    // moves on reallocation
    std::puts("potentially-throwing move:");
    std::vector<W<false>> b(1); b.reserve(2);    // copies on reallocation
}
```

The element types of the two `vector`s differ only by one `noexcept`, yet they behave differently on reallocation: when the move constructor does not throw, `vector` moves the elements; when it might, `vector` copies instead. The reason is that reallocation must provide the strong exception safety guarantee, meaning the original elements are unchanged on failure. If a move throws halfway, the original elements have already been moved from and cannot be restored; a failed copy leaves the originals untouched. `vector` queries the move constructor's exception specification at compile time and chooses its algorithm accordingly.

Forget `noexcept` on a move constructor and `vector` silently copies. A defaulted move constructor (`= default`) deduces the right exception specification automatically, which is one reason to prefer writing `= default`.

## An exception specification is a predicate (¶1–¶3)

¶1 The predicate indicating that a function cannot exit via an exception is called the function's [[g:exception-specification]]. If the predicate is false, the function has a [[g:potentially-throwing-exception-specification]]; if true, it has a [[g:non-throwing-exception-specification]]. The exception specification can be given explicitly by a *noexcept-specifier* at the end of the function declarator, or determined implicitly:

```text
noexcept-specifier:
    noexcept ( constant-expression )
    noexcept
```

¶2 `noexcept` without an expression is equivalent to `noexcept(true)`. The expression in the parentheses must be a contextually converted constant expression of type `bool` ([[expr.const.const]]), so narrowing is not allowed:

```cpp title="noexcept-narrowing.cpp" error
void f() noexcept(sizeof(char[2]));  // error: converting 2 to bool is narrowing
void g() noexcept(sizeof(char));     // OK: converting 1 to bool is not narrowing
```

What goes in `noexcept(...)` is often a complicated condition. If a typo like `noexcept(sizeof(T))` were silently taken as `true`, a function that might throw would be marked non-throwing, with run-time termination as the consequence.

¶2 also specifies that a `(` immediately after `noexcept` belongs to the *noexcept-specifier* and does not begin an initializer:

```cpp title="noexcept-paren.cpp" ok
void target() noexcept;
void (*p1)() noexcept (false);     // p1 is a pointer to a potentially-throwing function, with no initializer
void (*p2)() noexcept = target;    // to initialize, use = or {}
void (*p3)() noexcept {target};
```

Without this rule, `(false)` could also be read as direct-initializing `p1` with `false`.

¶3 When a *noexcept-specifier* appears in a function type, its constant expression is the exception specification of that type. The exception specification is part of the function type, discussed below.

## Potentially-throwing expressions (¶6)

How does the compiler decide whether an expression might throw? ¶6 gives the definition. An expression `E` is a [[g:potentially-throwing-expression]] if:

- ¶6.1 `E` is a function call whose called function type or function pointer type has a potentially-throwing exception specification;
- ¶6.2 `E` implicitly invokes a function with a potentially-throwing exception specification, such as an overloaded operator, an allocation function in a *new-expression*, a constructor for a function argument, or a destructor;
- ¶6.3 `E` is a *throw-expression*;
- ¶6.4 `E` is a `dynamic_cast` to a reference type that requires a run-time check, which throws `std::bad_cast` on failure;
- ¶6.5 `E` is a `typeid` applied to `*p` where `p` points to a polymorphic class type, which throws `std::bad_typeid` if `p` is null;
- ¶6.6 any of the immediate subexpressions of `E` is potentially-throwing, excluding unevaluated operands.

This judgment is static and conservative: it looks only at the exception specifications on types, not at whether a function actually throws. The result of the `noexcept` operator ([[expr.unary.noexcept]]) is exactly that its operand is not a potentially-throwing expression.

```cpp title="potentially-throwing.cpp" ok
#include <new>
#include <typeinfo>

struct Poly { virtual ~Poly(); };
struct Der : Poly {};
struct Thr { ~Thr() noexcept(false); };
Thr make_thr() noexcept;

void may();
int may_int();
void never() noexcept;
int x;
Poly* pp;

static_assert(!noexcept(may()));                    // 6.1
static_assert( noexcept(never()));
static_assert(!noexcept(new int));                  // 6.2: operator new is potentially-throwing
static_assert( noexcept(new (&x) int));             // placement operator new does not throw
static_assert(!noexcept(throw 1));                  // 6.3
static_assert(!noexcept(dynamic_cast<Der&>(*pp)));  // 6.4
static_assert( noexcept(dynamic_cast<Der*>(pp)));   // to a pointer: returns a null pointer on failure
static_assert(!noexcept(typeid(*pp)));              // 6.5
static_assert( noexcept(typeid(pp)));               // no polymorphic pointer is dereferenced
static_assert(!noexcept(make_thr()));               // 6.2: the destructor of the temporary
static_assert( noexcept(x + 1));
static_assert( noexcept(sizeof(may_int())));        // 6.6: unevaluated operands do not count
```

The `make_thr()` line is easy to misread. `make_thr` itself is `noexcept`, but the `noexcept` operator materializes a prvalue operand into a temporary ([[expr.unary.noexcept#1]]), which is destroyed at the end of the full-expression, and `Thr`'s destructor is potentially-throwing. (Clang warns that the `new` and `throw` in the unevaluated operands have no effect; that is expected.)

## When noexcept is not written (¶4, ¶8, ¶10)

¶4 A function declaration without a *noexcept-specifier* is potentially-throwing by default, with three kinds of exceptions:

- destructors (¶8);
- deallocation functions, that is, the `operator delete` family (¶10);
- functions defaulted (`= default`) on their first declaration (¶7, ¶9, ¶11; see the next section).

### Destructors are non-throwing by default (¶8)

¶8 An implicitly declared destructor, or a destructor without a *noexcept-specifier* (including one with a user-written body), is potentially-throwing only in two cases: the destructor of some potentially constructed subobject (base classes and non-static data members, [[class.base.init]]) is potentially-throwing; or the destructor is virtual and the destructor of some virtual base class is potentially-throwing.

```cpp title="dtor-implicit-noexcept.cpp" ok
#include <type_traits>

struct User { ~User() { /* noexcept even if it throws here */ } };
static_assert(std::is_nothrow_destructible_v<User>);

struct Loud { ~Loud() noexcept(false); };
struct Holder { Loud l; };                 // a subobject is potentially-throwing, so this is too
static_assert(!std::is_nothrow_destructible_v<Holder>);

struct Holder2 { Loud l; ~Holder2() {} };  // user-provided with no specifier: also deduced from subobjects
static_assert(!std::is_nothrow_destructible_v<Holder2>);
```

This is the precise meaning of destructors being `noexcept` by default. As long as `noexcept(false)` is not written and the subobjects' destructors do not throw, it is non-throwing, and a `throw` in its body leads to `std::terminate`.

There are two reasons destructors are non-throwing by default. Destructors are called during stack unwinding, and throwing then would terminate the program ([[except.throw]]); and the standard library containers require element destructors not to throw ([[res.on.exception.handling]]). Making non-throwing the default gives the vast majority of code the right semantics automatically, and lets the compiler omit cleanup code in callers.

### Deallocation functions are non-throwing by default (¶10)

¶10 A deallocation function with no explicit *noexcept-specifier* is non-throwing. Deallocation functions are called when construction fails in a *new-expression*, while an exception is propagating ([[except.ctor]]), and they cannot throw again at that point.

```cpp title="dealloc-noexcept.cpp" ok
#include <cstddef>

struct Pool {
    static void* operator new(std::size_t);
    static void  operator delete(void*);      // implicitly noexcept
};
static_assert(noexcept(Pool::operator delete(nullptr)));
static_assert(!noexcept(Pool::operator new(1)));
```

### Other declarations cannot add noexcept (¶4)

For these three kinds of functions, ¶4 also specifies that if any declaration lacks a *noexcept-specifier*, no other declaration of the function may have one. So a destructor's `noexcept` is either written on every declaration or on none:

<div class="compare" markdown="1">

```cpp error
struct S { ~S(); };
S::~S() noexcept {}  // error
```

```cpp ok
struct S { ~S() noexcept(false); };
S::~S() noexcept(false) {}
```

</div>

Clang 23 gives only a warning (`-Wimplicit-exception-spec-mismatch`) for the left side, and the same for the reverse, `~T() noexcept;` with `T::~T() {}`. Per [[intro.compliance]], a warning counts as a diagnostic, but the program is still ill-formed.

For ordinary functions, declarations with different exception specifications simply have different types, which [[basic.link#11]] deals with:

```cpp title="redecl-mismatch.cpp" error
void k();
void k() noexcept;   // error: different type from the previous declaration
```

The second half of ¶4 deals with explicit instantiations ([[temp.explicit]]): an explicit instantiation may or may not have a *noexcept-specifier*; if it does, it must be the same as the exception specification of the other declarations of the function. A diagnostic is required only if the inconsistency appears within a single translation unit.

```cpp title="explicit-inst.cpp" error
template<class T> void tf(T) noexcept(sizeof(T) > 1) {}

template void tf<int>(int) noexcept;     // OK: consistent
template void tf<char>(char);            // OK: omitting it is fine too
template void tf<char>(char) noexcept;   // error: tf<char> is noexcept(false)
```

## Compiler-generated functions (¶7, ¶9, ¶11–¶12)

The exception specification of a compiler-generated function depends on what it actually calls: if it would call a potentially-throwing function, or contains a potentially-throwing expression, it is potentially-throwing. This applies to implicitly declared functions and to functions defaulted on their first declaration without a *noexcept-specifier*.

¶7 A constructor is potentially-throwing if any of the following is potentially-throwing: a constructor selected to initialize a potentially constructed subobject (¶7.1); a subexpression of such an initialization, such as a default argument (¶7.2); for a default constructor, a default member initializer (¶7.3).

Note 1 explains an apparent omission. When a constructor throws midway, the destructors of the constructed subobjects are invoked ([[except.ctor]]), but they take no part in the deduction. That is because if such a destructor threw at that point, `std::terminate` would be called directly, and the exception would not leave the constructor.

¶9 An assignment operator is potentially-throwing if some assignment operator invoked in its implicit definition is potentially-throwing.

¶11 A comparison operator function ([[class.compare]]), and a defaulted postfix increment or decrement operator function ([[over.inc]], {{c++29}} [[P3668R4]]), is potentially-throwing if its implicit definition contains a potentially-throwing expression.

```cpp title="defaulted-compare.cpp" ok
#include <string>

struct P { int a, b; bool operator==(const P&) const = default; };
static_assert(noexcept(P{} == P{}));

struct Q {
    std::string s;
    auto operator<=>(const Q&) const = default;
    bool operator==(const Q&) const = default;
};
static_assert(noexcept(Q{} == Q{}) == noexcept(std::string{} == std::string{}));
```

A defaulted postfix `++` does not compile yet with Clang 23 (`only special member functions and comparison operators may be defaulted`).

¶12 Example 3 in the standard puts these rules together:

```cpp title="except-spec-example.cpp" ok
#include <new>
#include <type_traits>
#include <utility>

struct A {
    A(int = (A(5), 0)) noexcept;
    A(const A&) noexcept;
    A(A&&) noexcept;
    ~A();                                 // implicitly noexcept(true)
};
struct B {
    B() noexcept;
    B(const B&) = default;                // deduced as noexcept(true)
    B(B&&, int = (throw 42, 0)) noexcept; // the default argument throws
    ~B() noexcept(false);
};
int n = 7;
struct D : public A, public B {
    int* p = new int[n];
    // D::D()         potentially-throwing: the new in the default member initializer
    // D::D(const D&) non-throwing
    // D::D(D&&)      potentially-throwing: the default argument of B(B&&, int) throws (7.2)
    // D::~D()        potentially-throwing: B::~B is potentially-throwing
};

static_assert(!std::is_nothrow_default_constructible_v<D>);
static_assert(!std::is_nothrow_move_constructible_v<D>);
static_assert(!std::is_nothrow_destructible_v<D>);
static_assert(!noexcept(D(std::declval<const D&>())));
static_assert( noexcept(::new (static_cast<void*>(nullptr)) D(std::declval<const D&>())));
```

The last two assertions deserve attention. `D(const D&)` itself is non-throwing, but the expression `D(...)` also includes the destruction of the temporary, and `D::~D()` is potentially-throwing, so the result is `false`. Constructing with placement new involves no temporary, so what is queried is the constructor's own exception specification.

Example 3 ends by saying that if `A::~A()` were virtual, the program would be ill-formed: `D::~D()` is potentially-throwing but overrides a non-throwing virtual function, violating ¶5 below.

## Overriding virtual functions (¶5)

¶5 If a virtual function is non-throwing, all declarations, including the definition, of any function that overrides it in any derived class must also be non-throwing, unless the overriding function is defined as deleted.

```cpp title="virtual-noexcept.cpp" error
struct B {
    virtual void f() noexcept;
    virtual void g();
    virtual void h() noexcept = delete;
};

struct D : B {
    void f();              // error: B::f does not throw, but the overrider is potentially-throwing
    void g() noexcept;     // OK: tightens the promise
    void h() = delete;     // OK: deleted functions are excepted
};
```

Code calling `f()` through a `B&` relies on the promise not to throw, and the compiler may omit cleanup code at the call site on that basis, so a derived class cannot loosen it. Conversely, a base that may throw with a derived class that guarantees not to throw tightens the promise, which is fine.

!!! impl "Clang rejects deleted overriders"
    Clang 23 also reports `exception specification of overriding function is more lax than base version` for `void h() = delete;` in the example above. Under the exception in ¶5 this line is well-formed; this is a nonconformance in Clang.

The most common trigger is virtual destructors. As soon as some member's destructor is `noexcept(false)`, the implicit destructor of the derived class is potentially-throwing and conflicts with the base class's non-throwing virtual destructor.

## When the exception specification is computed (¶13)

¶13 The exception specification of a defaulted function is computed only when needed. It is needed when:

- ¶13.1 the function is selected by overload resolution ([[over.match]], [[over.over]]) in an expression;
- ¶13.2 the function is odr-used ([[basic.def.odr]]);
- ¶13.3 the exception specification is compared to that of another declaration, such as an explicit specialization or an overriding virtual function;
- ¶13.4 the function is defined;
- ¶13.5 {{c++26}} the function is represented by a reflection ([[meta.reflection]]);
- ¶13.6 the exception specification is needed for a defaulted function that calls the function.

Why delay? Computing a defaulted function's exception specification may require the complete class and its default member initializers. Inside the class definition they may not be ready yet; for example, a nested class's default constructor may depend on a default member initializer of the enclosing class that has not been parsed. Computing it only when someone actually asks avoids such circular dependencies.

Note 2 adds that a defaulted declaration does not by itself require the exception specification of a base member function to be evaluated immediately; but if the defaulted function has an explicit *noexcept-specifier*, the implicit exception specification must be computed for comparison. Since C++20, when the two differ, the explicitly written one prevails ([[P1286R2]]):

```cpp title="defaulted-explicit-noexcept.cpp" ok
#include <type_traits>

struct Base { Base() noexcept(false); };
struct D1 : Base { D1() = default; };            // deduced as potentially-throwing
struct D2 : Base { D2() noexcept = default; };   // the explicit noexcept prevails
static_assert(!std::is_nothrow_default_constructible_v<D1>);
static_assert( std::is_nothrow_default_constructible_v<D2>);
```

If `D2()` actually receives an exception from `Base()`, the program calls `std::terminate`.

## The exception specification is part of the function type

Since C++17 the exception specification is part of the function type ([[dcl.fct]], [[P0012R1]]):

```cpp title="noexcept-in-type.cpp" ok
#include <type_traits>

void g() noexcept;
void h();

static_assert(!std::is_same_v<decltype(g), decltype(h)>);

void (*p1)() = g;               // OK: function pointer conversion drops noexcept
// void (*p2)() noexcept = h;   // error: noexcept cannot be added out of thin air

void take(void (*)());
void take(void (*)() noexcept); // OK: different parameter types, so two overloads

template<class F> constexpr bool is_nx(F) { return std::is_nothrow_invocable_v<F>; }
static_assert(is_nx(g) && !is_nx(h));
```

| Aspect | Consequence |
|---|---|
| Conversions | a pointer to a `noexcept` function implicitly converts to an ordinary function pointer (function pointer conversion, [[conv.fctptr]]), but not the reverse |
| Overloading | the same function cannot be overloaded on the exception specification alone, but parameters can be distinguished by whether they are `noexcept` |
| Template deduction | passing a `noexcept` function deduces `F` as `void(*)() noexcept` |
| Name mangling | the Itanium ABI marks `noexcept` function types with `Do`: `void take(void (*)() noexcept)` mangles to `_Z4takePDoFvvE` (tested locally) |

Because `noexcept` entered name mangling, an interface taking a `noexcept` function pointer as a parameter gets different symbol names when compiled as C++14 and as C++17. GCC provided the `-Wnoexcept-type` warning for this when C++17 came out.

The effect of `noexcept` on code generation: call sites of `noexcept` functions need no landing pad for exceptions; a `noexcept` function itself needs a landing pad that catches everything and calls `std::terminate`, but it can omit cleanup of its internal objects, because [[except.terminate#2]] allows not unwinding, or only partially unwinding, in that case. For assembly examples see [[toolchain/exception-implementation]].

## History and evolution

!!! history
    - C++98's exception specifications were dynamic: `void f() throw(A, B);` declared that `f` throws only `A` or `B`, and a violation called `std::unexpected()`. The check happened at run time, the type list was nearly impossible to get right in templates, and compilers could not optimize on it. In practice only `throw()` saw use.
    - C++11 introduced the `noexcept` specifier and the `noexcept` operator ([[N3050]]). A violation calls `std::terminate` directly, destructors are non-throwing by default, and dynamic exception specifications were deprecated.
    - C++17 made the exception specification part of the function type ([[P0012R1]]) and removed `throw(T...)`, keeping only `throw()` as a deprecated spelling of `noexcept(true)` ([[P0003R5]]).
    - C++20 removed `throw()` ([[P0619R4]]), and allowed explicitly defaulted functions to state an exception specification different from the deduced one ([[P1286R2]]).
    - Since C++26, ¶13 includes being represented by a reflection. After C++26, defaulted postfix increment and decrement were added to ¶11.

!!! impl "How compilers treat the old syntax"
    Under `-std=c++2c`, Clang 23 rejects `throw(int)` (`ISO C++17 does not allow dynamic exception specifications`), but silently accepts `throw()`, even with `-pedantic`, treating it as `noexcept(true)`. Under the current standard, `throw()` no longer exists in the grammar.

## Common misconceptions

!!! pitfall "`noexcept` is checked at compile time"
    `void f() noexcept { may_throw(); }` is perfectly valid ([[except.handle#7]] Note 3). The consequence of breaking the promise is `std::terminate` at run time.

!!! pitfall "A conditional `noexcept` that tests only the construction"
    `noexcept(T(std::declval<T>()))` tests constructing a temporary `T` and then destroying it. For a type whose destructor might throw, the result is `false` even if the move constructor is `noexcept`. `std::is_nothrow_move_constructible` also includes the destruction with libc++; this is a known library issue ([[LWG2116]]).

!!! pitfall "`noexcept(false)` destructors are contagious"
    A member's `~M() noexcept(false)` makes the implicit destructor of every class containing it potentially-throwing (¶8), and those classes then cannot override a non-throwing virtual destructor (¶5).

## Questions

!!! question "Question 1"
    What is `b` below?

    ```cpp
    struct S { S(int) noexcept; ~S() noexcept(false); };
    void f(S) noexcept;
    bool b = noexcept(f(1));
    ```

<details markdown="1">
<summary>Answer</summary>

`false`. `f(1)` calls the constructor `S(int)` to initialize the parameter (non-throwing), then calls `f` (non-throwing), but the parameter object must eventually be destroyed, and `~S()` is potentially-throwing. ¶6.2 explicitly counts both the constructor and the destructor invoked for a function argument as implicitly invoked functions. Where the parameter is destroyed is implementation-defined ([[expr.call]]), but wherever it is, it is implicitly invoked by this call expression.
</details>

!!! question "Question 2"
    In `struct X { virtual ~X(); }; struct Y : X { std::vector<int> v; };`, does `Y`'s destructor throw? What if `std::vector<int>` is replaced by a type `M` with `~M() noexcept(false)`?

<details markdown="1">
<summary>Answer</summary>

`X::~X()` has no specifier and is deduced per ¶8: `X` has no subobjects, so it is non-throwing. The subobjects of `Y`'s implicit destructor, `X` and `std::vector<int>`, are both non-throwing, so it is non-throwing too.

With `M`, `Y::~Y()` is potentially-throwing because of `M::~M()`, but it overrides the non-throwing virtual function `X::~X()`, violating ¶5, so the program is ill-formed. This is exactly the situation the last sentence of Example 3 describes.
</details>
