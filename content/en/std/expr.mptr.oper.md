---
title: Pointer-to-member operators
summary: ".* and ->* bind a pointer to member to a specific object; this page covers the operand requirements, the value category and cv-qualification of the result, the restrictions on ref-qualified member functions, and three kinds of undefined behavior."
updated: 2026-10-19
---

!!! tldr
    - `obj.*pm` uses the pointer to member `pm` to access a member of the object `obj`; `p->*pm` is just `(*p).*pm`. Calling through a pointer to member function needs parentheses: `(obj.*pmf)(args)`.
    - The value category and cv-qualification of the result are the same as for `obj.member`: for a data member the result is an lvalue or xvalue according to `obj`, and a `const` object gives a `const` result; but `mutable` has no effect through a pointer to member.
    - A `&`-qualified member function cannot be called when the object is an rvalue, except `const &` since C++20; a `&&`-qualified member function cannot be called when the object is an lvalue.
    - Three cases are UB: the pointer to member is null; the object has no such member at all; the type of the object expression is not similar to the actual object.
    - Since C++17 the left operand is evaluated before the right operand.

## A pointer to member has to be bound to an object

A **pointer to member** ([[dcl.mptr]]) does not point to any object. `int S::*pm = &S::m;` only records which member of `S` is meant, and is usually implemented as an offset. To access data, it must be combined with a specific object, and that is what `.*` and `->*` do:

```cpp run title="mptr-basic.cpp" ok
struct S { int a = 1, b = 2; int sum() const { return a + b; } };

int main() {
    int S::* pm = &S::b;
    int (S::*pmf)() const = &S::sum;
    S s;
    S* p = &s;
    int x = s.*pm;          // 2
    int y = (p->*pmf)();    // 3
    return x + y == 5 ? 0 : 1;
}
```

Implicit conversions of pointers to members go in the opposite direction from object pointers: `int B::*` converts implicitly to `int D::*`, not the other way round ([[conv.mem]]).

## Precedence and parentheses (¶1)

¶1 `.*` and `->*` group left-to-right and form their own level, *pm-expression*, binding tighter than `*`, `/` and `%` and looser than the unary operators and casts:

```text
pm-expression:
    cast-expression
    pm-expression .* cast-expression
    pm-expression ->* cast-expression
```

The function call `()` is a postfix operator with much higher precedence than `.*`, so calling through a pointer to member function needs parentheses:

<div class="compare" markdown="1">

```cpp error
struct S { int f(int x) { return x; } };

int g(S& s, int (S::*pmf)(int)) {
  return s.*pmf(1);
  // error: parsed as s.*(pmf(1))
}
```

```cpp ok
struct S { int f(int x) { return x; } };

int g(S& s, S* p, int (S::*pmf)(int)) {
  return (s.*pmf)(1) + (p->*pmf)(2);
}
```

</div>

Left-to-right grouping means `a.*pm1.*pm2` is `(a.*pm1).*pm2`: first the member subobject is obtained, then the second pointer to member is applied to it.

## Operand requirements (¶2–¶3)

¶2 In `E1.*E2`, `E2` must be a prvalue of type "pointer to member of `T`" (if it is a variable, its value is read first). `E1` must be a glvalue whose type is `T` or a class of which `T` is an unambiguous and accessible base class. The result is the object or function designated by `E2`.

Derived classes of `T` are allowed because a derived class object always contains a `T` subobject, and therefore always contains that member. Conversely, `int D::*` cannot be used on a `B` object, which need not contain a member of `D`:

```cpp title="mptr-operands.cpp" error
struct B { int b = 1; };
struct D : B { int d = 2; };

struct A { int x; };
struct L : A {};
struct R : A {};
struct LR : L, R {};          // two A subobjects
struct P : private A {};

void f(D& dobj, B& bobj, LR& lr, P& p) {
    int B::* pb = &B::b;
    int D::* pd = &D::d;
    dobj.*pb = 0;      // OK: B is an unambiguous, accessible base of D
    bobj.*pd = 0;      // error: a B object need not contain D::d
    int A::* pa = &A::x;
    lr.*pa = 1;        // error: A is an ambiguous base of LR
    p.*pa = 1;         // error: A is an inaccessible base of P
}
```

When `E1` is a prvalue, as in `S{}.*pm`, it first undergoes temporary materialization ([[conv.rval]]) and becomes an xvalue; that is the general rule wherever a glvalue is expected ([[basic.lval]]).

¶3 In `E1->*E2`, `E1` must be a pointer to `U`, where `U` is `T` or a class of which `T` is an unambiguous and accessible base class. The whole expression is rewritten as `(*(E1)).*E2`, so all the rules for `->*` reduce to those for `.*`.

The two differ under overloading. `->` has a special rule that calls `operator->` repeatedly until a built-in pointer is obtained ([[over.ref]]); `->*` is just an ordinary binary operator ([[over.binary]]) and does not chain. None of the standard library's smart pointers provide `operator->*`; you write `(*sp).*pm` or `std::invoke(pm, *sp)`:

```cpp run title="mptr-arrow.cpp" ok
#include <memory>
#include <functional>

struct S { int v = 7; int get() const { return v; } };

int main() {
    auto sp = std::make_unique<S>();
    int S::* pm = &S::v;
    int a = (*sp).*pm;                       // OK: dereference first, then .*
    int b = std::invoke(&S::get, *sp);       // OK
    // int c = sp->*pm;                      // error: unique_ptr has no operator->*
    return a + b == 14 ? 0 : 1;
}
```

## Value category of the result (¶6)

¶6 If the second operand is a pointer to data member, the result is an lvalue if the first operand is an lvalue, and an xvalue otherwise. If the second operand is a pointer to member function, the result is a prvalue, and it can only be called immediately.

This matches the rule for accessing a non-static data member with `E1.E2` ([[expr.ref]]). A member taken from an expiring object is itself expiring, so `std::move(obj).*pm` can be moved from:

```cpp run title="mptr-valcat.cpp" ok
#include <utility>
#include <string>
#include <type_traits>

struct S { std::string name; };

int main() {
    S s{"hello"};
    std::string S::* pm = &S::name;
    static_assert(std::is_same_v<decltype((s.*pm)), std::string&>);             // lvalue
    static_assert(std::is_same_v<decltype((std::move(s).*pm)), std::string&&>); // xvalue
    static_assert(std::is_same_v<decltype((S{}.*pm)), std::string&&>);          // xvalue
    std::string t = std::move(s).*pm;   // move construction
    return t == "hello" ? 0 : 1;
}
```

The beginning of ¶6 says that if the result of `.*` or `->*` is a function, it can only be used as the operand of a function call `()`. A member function bound to an object cannot have its address taken or be stored, just as `obj.memfn` cannot be used on its own. To package an object with a member function, use a lambda or `std::bind_front`.

```cpp title="mptr-bound-fn.cpp" error
struct S { void f() {} };

void g(S& s) {
    void (S::*pmf)() = &S::f;
    auto x = s.*pmf;       // error: the result is a function and can only be called immediately
    (s.*pmf)();            // OK
}
```

## cv-qualification and `mutable` (¶5)

¶5 The cv-qualification of the result, and the restrictions on the cv-qualification of the operands, are the same as for `E1.E2` ([[expr.ref]]): a data member of a `const` object gives a `const` result.

The difference is `mutable`. When `E1.E2` accesses a `mutable` member, the object's `const` is not carried over; but `mutable` is not part of the type, and `int S::*` does not record whether the member it points to is `mutable`. So, as Note 1 explains, accessing a `mutable` member of a `const` object through a pointer to member still gives a `const int` lvalue:

```cpp title="mptr-mutable.cpp" error
struct S {
    mutable int i = 0;
};

void f() {
    const S cs;
    cs.i = 1;              // OK: mutable member accessed through .
    int S::* pm = &S::i;   // pm points to the mutable member S::i
    cs.*pm = 88;           // error: cs.*pm is a const int lvalue
}
```

At compile time it is generally not known which member a pointer to member points to, so the type system can only treat it as `const` across the board.

## Ref-qualified member functions (¶6)

A member function can have a **ref-qualifier** ([[dcl.fct]]): a `&`-qualified one can only be called on lvalues, and a `&&`-qualified one only on rvalues. ¶6 makes `.*` follow the same rules:

| Object expression | Member function qualifier | Result |
|---|---|---|
| rvalue | `&` | {{ill-formed}} |
| rvalue | `const &` | OK {{c++20}} |
| rvalue | `&&`, no ref-qualifier | OK |
| lvalue | `&&` | {{ill-formed}} |
| lvalue | `&`, `const &`, no ref-qualifier | OK |

<div class="compare" markdown="1">

```cpp ok
struct S {
  int lref() &       { return 1; }
  int cref() const & { return 2; }
  int rref() &&      { return 3; }
};
int main() {
  S s;
  int r = (s.*&S::lref)();
  r += (S{}.*&S::cref)();  // since C++20
  r += (S{}.*&S::rref)();
  return r == 6 ? 0 : 1;
}
```

```cpp error
struct S {
  void lref() & {}
  void rref() && {}
};
void f(S& s) {
  (S{}.*&S::lref)();
  // error: rvalue object, & qualifier
  (s.*&S::rref)();
  // error: lvalue object, && qualifier
}
```

</div>

The second row was fixed in C++20 by [[P0704R1]]. Calling `S{}.cref()` directly has always been valid, because `const&` can bind to an rvalue; but the `.*` rule in C++11–17 only said that an rvalue cannot be used with `&`, with no exception for `const &`, so `(S{}.*&S::cref)()` was ill-formed instead. Generic code runs into this when it calls a `const&` member function on a temporary through `std::invoke`.

## Undefined behavior and evaluation order (¶4, ¶6)

¶4 calls `E1` in `E1.*E2` the **object expression**, in the same sense as [[expr.ref]]. The following two cases are UB:

- The type of the object that `E1` actually refers to is not similar ([[conv.qual]]) to the type of `E1`. This is another form of accessing an object through a glvalue of the wrong type.
- The most derived object of the object that `E1` actually refers to does not contain the member that `E2` refers to.

The second case can arise because `static_cast` allows `int D::*` to be explicitly converted back to `int B::*` ([[expr.static.cast]]). The conversion itself is valid, and using it on an object whose most derived type really is `D` is fine; using it on a plain `B` object accesses a member that does not exist:

```cpp run title="mptr-not-contain.cpp" ub
struct B { int b; };
struct D : B { int d; };

int main() {
    int B::* pm = static_cast<int B::*>(&D::d);   // OK: explicit conversion

    D dobj{};
    B& ref = dobj;
    ref.*pm = 1;      // OK: the most derived object of ref is a D, which contains D::d

    B bobj{};
    return bobj.*pm;  // UB: bobj is only a B and has no D::d
}
```

In our tests AddressSanitizer reports the last line as a stack-buffer-overflow: it reads memory past `bobj`.

The last sentence of ¶6: if the second operand is the null member pointer value, the behavior is undefined. This holds for both pointers to data members and pointers to member functions:

```cpp title="mptr-null.cpp" ub
struct S { int m; };

int f(S& s) {
    int S::* pm = nullptr;
    return s.*pm;        // UB: null member pointer
}
```

!!! std
    The expression E1 is sequenced before the expression E2.

The last sentence of ¶4 was added in C++17 by [[P0145R3]]: `E1` and all its side effects complete before `E2`. Before that the two were unsequenced, and the order of the two calls in `f().*g()` was unspecified. Now `.*` and `->*`, like `.`, `->`, `<<`, `>>` and `[]`, are strictly left before right ([[topics/order-of-evaluation]]):

```cpp run title="mptr-order.cpp" ok
#include <cstdio>

struct S { int a = 1, b = 2; };
S s;
S& obj()          { std::puts("obj");    return s; }
int S::* member() { std::puts("member"); return &S::b; }

int main() {
    return obj().*member() == 2 ? 0 : 1;   // prints obj first, then member
}
```

## Virtual functions and pointers to member functions

A pointer to member function that points to a virtual function performs virtual dispatch when called through `.*`, calling the final overrider in the dynamic type of the object ([[class.virtual]], [[expr.call]]). A pointer to member function records which virtual function is meant, not which function body:

```cpp run title="mptr-virtual.cpp" ok
struct B { virtual int f() { return 1; } virtual ~B() = default; };
struct D : B { int f() override { return 2; } };

int main() {
    int (B::*pmf)() = &B::f;
    D d;
    B& b = d;
    return (b.*pmf)() == 2 ? 0 : 1;   // calls D::f
}
```

To bypass virtual dispatch and call `B::f`, you have to write the qualified name `b.B::f()`; a pointer to member function cannot do it.

!!! impl "Implementation view: how pointers to members are represented"
    - Itanium C++ ABI (GCC and Clang on Linux and macOS): a pointer to data member is a `ptrdiff_t` offset, with `-1` as the null value, because offset 0 is a valid value for the first member. A pointer to member function takes two words `{ptr, adj}`: for a non-virtual function `ptr` is the function's address, for a virtual function `ptr` is 1 plus the offset into the vtable, with the low bit set to 1 marking a virtual function; `adj` is the adjustment applied to `this` before the call, needed with multiple inheritance.
    - MSVC: the size of a pointer to member function depends on the class's inheritance model. For a single-inheritance class it is 8 bytes on x64; multiple inheritance adds a `this` adjustment, and virtual inheritance needs even more information. When a pointer to member is declared for an incomplete class, the compiler doesn't know the inheritance model and has to use the largest representation; `/vmg` and keywords such as `__single_inheritance` control this.
    - So `reinterpret_cast`ing a pointer to member to an ordinary pointer, or inspecting its contents with `memcpy`, is not portable.

## Common misconceptions

!!! pitfall "`mutable` takes effect through a pointer to member"
    `cs.*pm` always carries the `const` of `cs`, even if `pm` points to a `mutable` member.

!!! pitfall "`->*` chains like `->`"
    An overloaded `operator->*` is an ordinary binary operator. On smart pointers, use `(*p).*pm` or `std::invoke`.

## Questions

!!! question "Question 1"
    Is the following code well-formed? What is the type of `r`? How long does the temporary live?

    ```cpp
    struct S { int m; };
    const S make();
    auto&& r = make().*&S::m;
    ```

<details markdown="1">
<summary>Answer</summary>

It is well-formed. `make()` is a prvalue of type `const S`, which becomes an xvalue after materialization. By ¶6, the first operand is not an lvalue, so the result is an xvalue; by ¶5, the result carries the object's `const`. So `make().*&S::m` is a `const int` xvalue, and the type of `r` is `const int&&`.

The forms listed in [[class.temporary#6]] that extend a temporary's lifetime include a `.*` expression whose right operand is a pointer to data member, so the temporary lives until the end of the scope of `r`.
</details>

!!! question "Question 2"
    Why did C++20 make an exception only for `const &`, so that a member function qualified `const volatile &` still cannot be called on an rvalue through `.*`?

<details markdown="1">
<summary>Answer</summary>

Because that is how reference binding already works: `const T&` can bind to an rvalue, while `volatile T&` and `const volatile T&` cannot ([[dcl.init.ref]]). When calling `S{}.f()` directly, the implicit object parameter has the corresponding reference type, so a `const volatile &` member function could never be called on an rvalue anyway. ¶6 says "unless its *cv-qualifier-seq* is `const`", letting through exactly `const` and nothing else, consistent with direct calls.
</details>

## Summary

| Aspect | Rule | Paragraph |
|---|---|---|
| Precedence | Left-to-right, lower than `()`; calling a pointer to member function needs parentheses | ¶1 |
| `E1.*E2` | `E2` is a pointer to member of `T`; `E1` is a glvalue of `T` or of a class derived from it unambiguously and accessibly | ¶2 |
| `E1->*E2` | Equivalent to `(*(E1)).*E2`; an ordinary binary operator when overloaded | ¶3 |
| Evaluation order | `E1` before `E2` (C++17) | ¶4 |
| cv | As for `E1.E2`, but `mutable` has no effect | ¶5 |
| Value category | Data member: lvalue or xvalue according to `E1`; member function: prvalue, can only be called immediately | ¶6 |
| Ref-qualifiers | rvalue cannot use `&` (except `const &`, C++20); lvalue cannot use `&&` | ¶6 |
| UB | Types not similar; most derived object lacks the member; null member pointer | ¶4, ¶6 |
