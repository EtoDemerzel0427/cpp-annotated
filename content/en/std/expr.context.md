---
title: Context dependence
summary: "Unevaluated operands (of sizeof, decltype, noexcept and others) are not evaluated; discarded-value expressions are evaluated only for their side effects: when they read a volatile object, and when they materialize a temporary object."
updated: 2026-10-19
---

!!! tldr
    - The operands of `sizeof`, `decltype`, `noexcept`, requires-expressions and so on are unevaluated operands: they are not evaluated and the names in them don't need definitions, but all semantic checks are performed as usual.
    - Expressions written only for their side effects (expression statements, the left side of a comma, `(void)e`) are discarded-value expressions: they are evaluated and their result is discarded.
    - A discarded-value expression doesn't read ordinary variables; only a volatile glvalue written as a name, `*p`, `a[i]`, `s.m` and similar forms is actually read once, and `vi = 1;` doesn't read again.
    - A discarded prvalue of class type materializes a temporary object, so `make();` also requires a usable destructor.

## Unevaluated operands (¶1)

```cpp ok
#include <utility>
struct S { int m; static int sm; };   // sm is only declared, never defined
int g();                              // only declared, never defined

auto a = sizeof(g());                 // g is not called and needs no definition
auto b = sizeof(S::m);                // a non-static member can be named without an object
auto c = sizeof(S::sm);               // not an odr-use
using T = decltype(std::declval<S>().m);   // declval is only declared and can never be evaluated

int n = 0;
auto d = sizeof(n++);                 // n is still 0
constexpr bool e = noexcept(g());     // false: g isn't declared noexcept, but it isn't called
```

¶1 In some contexts, operands are **unevaluated operands** ([[g:unevaluated-operand]]):

!!! std
    An unevaluated operand is not evaluated.

The contexts the current draft lists are: simple requirements and compound requirements in a requires-expression ([[expr.prim.req.simple]], [[expr.prim.req.compound]]), the operand of `typeid` (except a glvalue of polymorphic class type, [[expr.typeid]]), `sizeof` ([[expr.sizeof]]), the `noexcept` operator ([[expr.unary.noexcept]]), {{c++26}} the reflection operator `^^` ([[expr.reflect]]), `decltype` ([[dcl.type.decltype]]), and constraint expressions in template constraints and concept definitions ([[temp.pre]], [[temp.concept]]). The operand of `alignof` is a type, not an expression, so it isn't on the list.

Note 1 lists three consequences:

1. A non-static class member can be named without an object, as in `sizeof(S::m)` ([[expr.prim.id]]).
2. Naming an object or function does not by itself require a definition. Names in unevaluated operands are not **odr-uses** ([[g:odr-use]], the kind of use that requires a definition, [[basic.def.odr]]), which is why `std::declval` can be declared without being defined.
3. An unevaluated operand is considered a full-expression ([[g:full-expression]]).

### Not evaluated, but checked as usual

Unevaluated operands still have to pass every semantic check: overload resolution, access control and type completeness (`sizeof` requires a complete type) all happen as usual. [[class.temporary#1]] also specifies that even when the creation of a temporary object is unevaluated, all the semantic restrictions must be respected as if the temporary object had been created and later destroyed, including accessible, non-deleted constructors and destructors. The only exception is the operand of `decltype`, which doesn't introduce a temporary object ([[dcl.type.decltype#2]]).

<div class="compare" markdown="1">

```cpp ok
struct NoDtor { ~NoDtor() = delete; };
NoDtor make();
// decltype doesn't introduce a temporary
using T = decltype(make());
```

```cpp error
struct NoDtor { ~NoDtor() = delete; };
NoDtor make();
// not evaluated, but the destructor must still be usable
auto s = sizeof(make());   // error
```

</div>

## Discarded-value expressions (¶2)

¶2 In some contexts, an expression only appears for its side effects; such an expression is called a **discarded-value expression** ([[g:discarded-value-expression]]). Common ones:

| Context | Subclause |
|---|---|
| Expression statement `e;` | [[stmt.expr]] |
| Left operand of the comma operator `e, x` | [[expr.comma]] |
| Conversion to `void`: `(void)e`, `static_cast<void>(e)` | [[expr.static.cast#4]] |
| The third clause of a `for` statement | [[stmt.for]] |
| The object expression on the left when `.` accesses a static member or enumerator | [[expr.ref#2]] |

For a discarded-value expression, ¶2 proceeds as follows:

1. The array-to-pointer and function-to-pointer conversions are not applied, so `arr;` and `func;` do nothing.
2. The lvalue-to-rvalue conversion, i.e. an actual read ([[conv.lval]]), is applied if and only if the expression is a glvalue of volatile-qualified type and has one of the following forms:
    - ¶2.1 `( e )`, where `e` is one of the forms in this list;
    - ¶2.2 an *id-expression* (a name);
    - ¶2.3 {{c++26}} a splice expression;
    - ¶2.4 subscripting `a[i]`;
    - ¶2.5 class member access `s.m`, `p->m`;
    - ¶2.6 indirection `*p`;
    - ¶2.7 pointer-to-member operation `s.*pm`, `p->*pm`;
    - ¶2.8 a conditional expression whose second and third operands are both forms in this list;
    - ¶2.9 a comma expression whose right operand is a form in this list.
3. If the (possibly converted) expression is a prvalue of object type, the temporary materialization conversion is applied ([[conv.rval]]).
4. The expression is evaluated and its result is discarded.

Note 2 explains that the list above only covers operators with built-in meaning. Using an overloaded operator is a function call and isn't covered.

### The list of volatile reads

Volatile accesses are observable behavior ([[intro.abstract]]), and programmers need to be able to predict exactly whether a statement reads memory. The typical scenario is reading a hardware status register once to clear a flag:

```cpp
volatile unsigned* const STATUS = /* device address */ nullptr;
void clear_flag() { *STATUS; }   // ¶2.6: indirection, read once
```

The list contains the forms that syntactically clearly designate an object. Whoever writes a name, `*p`, `a[i]` or `s.m` evidently wants to access that object. The results of assignment `vi = 1` and pre-increment `++vi` are also volatile lvalues, but whoever writes them wants a write, and an extra read would be counterintuitive, so they are not on the list.

```cpp ok
void demo(volatile int& vi, int x) {
    vi;              // ¶2.2: read once
    (void)vi;        // the operand of a conversion to void is a discarded-value expression: read once
    vi = 1;          // only written once; the result is not read again
    x ? vi : vi;     // ¶2.8: read once (only one of the operands is evaluated)
    (x, vi);         // ¶2.9: read once
}
```

Compiling this with Clang 23 `-O2 -emit-llvm`, `vi;`, `(void)vi;`, `x ? vi : vi;` and `(x, vi);` each produce one `load volatile`, and `vi = 1;` produces just one `store volatile`.

!!! note "Differences from C"
    In C the result of an assignment expression is a value, not an lvalue, and whether `vi` should be read again after `vi = 1;` was once disputed in C. In C++ the result of assignment is an lvalue, and assignment isn't on the list, so it is definitely not read again. Before C++11, whether `vi;` reads was also unclear in the C++ standard; C++11 introduced today's list-based rule through [[CWG1054]].

Note 3 points out that if the original expression is an lvalue of class type, the lvalue-to-rvalue conversion copy-initializes a temporary object from it ([[conv.lval]]), which requires the class to have a copy constructor that accepts a volatile argument. The implicitly declared copy constructor's parameter is `const S&`, which can't bind to an lvalue of `volatile S`:

```cpp error
struct S { int x; };
void f(volatile S& s) {
    s;     // per the standard: needs S(const volatile S&), ill-formed
}
```

At the time of writing, Clang 23 doesn't diagnose the example above under this rule; it only gives a `-Wunused-volatile-lvalue` warning and doesn't generate a copy. This is a divergence between the implementation and the wording, though such code is of almost no use anyway.

### Discarded prvalues are materialized

By step 3, in `make();`, if `make` returns a class type, a temporary object is materialized and destroyed at the end of the full-expression, so the destructor must be usable:

```cpp error
struct NoDtor { ~NoDtor() = delete; };
NoDtor make();
void use() {
    make();          // error: the discarded prvalue is materialized, which needs a destructor
}
```

This is how "since C++17, a prvalue of object type always has a result object" ([[basic.lval#5]] Note 4) plays out in a discarded-value context: although the result is unused, the object still has to exist briefly.

!!! note "`[[nodiscard]]` and `(void)`"
    `[[nodiscard]]` ([[dcl.attr.nodiscard]]) encourages implementations to warn when a nodiscard function is called in a potentially-evaluated discarded-value expression, unless it is explicitly cast to `void`. So `(void)f();` is the idiomatic way to suppress the warning; it is still a discarded-value expression, just explicitly exempted.

### The connection to the ODR

[[basic.def.odr#5]] specifies that when the name of a variable `x` appears among the potential results of a discarded-value expression and the lvalue-to-rvalue conversion is not applied to it, that appearance is not an odr-use. So `x;` for an ordinary variable doesn't odr-use `x`; `vx;` for a volatile variable reads it and is an odr-use.

## History

!!! history
    - C++98/03 only said that the result of an expression statement is discarded; whether a volatile lvalue was read was unclear.
    - C++11 introduced the term discarded-value expression and the volatile list through [[CWG1054]].
    - C++17 added the rule that discarded prvalues materialize a temporary object, along with [[P0135R1]]'s new prvalue model.
    - C++20's [[P1152R4]] deprecated many uses of volatile, including using the result of a volatile assignment expression as a value (as in `a = vi = 1`). A discarded `vi = 1;` is unaffected ([[expr.assign#5]]).
    - C++26 added the operand of the reflection operator to the unevaluated contexts, and splice expressions to the discarded-value list.

## Common misconceptions

!!! pitfall "The operand of `typeid` is never evaluated"
    Neither `sizeof(i++)` nor `decltype(launch())` is evaluated. But in `typeid(*p)`, when `*p` is an lvalue of polymorphic class type, it is evaluated, because the dynamic type has to be read; if `p` is null, `std::bad_typeid` is thrown.

!!! pitfall "`(void)x` just silences a warning"
    For ordinary variables, yes. For a volatile object, `(void)status_reg;` performs a real hardware read. If you only want to suppress an unused warning, put `[[maybe_unused]]` on the declaration.

## Questions

!!! question "Question 1"
    Given `volatile int vi;`, how many times do `vi += 1;`, `++vi;`, `vi++;` and `(vi, vi);` each read `vi`?

<details markdown="1">
<summary>Answer</summary>

- `vi += 1;`: compound assignment reads the old value and writes back, so 1 read. Compound assignment isn't on the list, so the discarded-value context adds no extra read.
- `++vi;`: equivalent to `vi += 1`, 1 read.
- `vi++;`: reads the old value as the result and writes back the new value, 1 read; the result is a prvalue, which isn't on the list.
- `(vi, vi);`: the left operand `vi` is a discarded-value expression, 1 read; the whole comma expression is also a discarded-value expression whose right operand is a name, so per ¶2.9 another read, 2 in total.

Also, since C++20 using `+=` and `++` on volatile objects is deprecated (C++23 restored `|=`, `&=` and `^=`); here we only count reads and writes.
</details>

!!! question "Question 2"
    Does `struct S { static int n; }; S make(); int k = make().n;` call `make()`?

<details markdown="1">
<summary>Answer</summary>

Yes. Per [[expr.ref#2]], when the right side of `.` is a static member, the expression on the left is a discarded-value expression. It is evaluated, so `make()` is called; the result is a prvalue, which is materialized and then discarded. This makes `obj.static_member` and `obj.nonstatic_member` behave the same as far as whether the left side is evaluated.
</details>
