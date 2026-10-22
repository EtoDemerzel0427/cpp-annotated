---
title: Class member access
summary: "What E1.E2 and E1->E2 mean: the arrow reduces to the dot; the object expression is always evaluated; the type and value category of the result depend on whether E2 designates a reference member, static member, non-static data member, member function or enumerator; cv-qualifiers are combined, except for mutable; accessing a member through an object of a non-similar type is UB."
updated: 2026-10-19
---

!!! tldr
    - `E1->E2` is just `(*(E1)).E2`. `*E1` is an lvalue, so the result of an arrow access is never an xvalue.
    - The object expression before the dot is always evaluated, even when `E2` is a static member.
    - Non-static data members: a member of an lvalue object is an lvalue, otherwise an xvalue; cv is the union of the object's and the member declaration's, and a `mutable` member doesn't inherit `const`.
    - Accessing a reference member or a static data member always gives an lvalue, without the object's cv added; `s.f` for a non-static member function can only be called immediately.
    - If the object's actual type is not similar to the type of `E1`, accessing a non-static member is UB, even without reading or writing the member's value.

```cpp run title="member-category.cpp" ok
#include <type_traits>
#include <utility>

int g = 0;
struct S {
    int m = 0;
    int& ref = g;
    mutable int mu = 0;
    static int sm;
};
int S::sm = 0;
S make() { return {}; }

S s;
const S cs;

static_assert(std::is_same_v<decltype((s.m)), int&>);               // member of an lvalue object: lvalue
static_assert(std::is_same_v<decltype((std::move(s).m)), int&&>);   // member of an xvalue object: xvalue
static_assert(std::is_same_v<decltype((make().m)), int&&>);         // the prvalue is materialized first: xvalue
static_assert(std::is_same_v<decltype((cs.m)), const int&>);        // the object is const, so is the member
static_assert(std::is_same_v<decltype((cs.mu)), int&>);             // mutable doesn't inherit const
static_assert(std::is_same_v<decltype((std::move(s).ref)), int&>);  // reference member: always an lvalue
static_assert(std::is_same_v<decltype((make().sm)), int&>);         // static member: always an lvalue

int main() {}
```

`s.m`, `p->f()`, `std::move(s).m`, `obj.template get<0>()` and `obj.[: r :]` are all **class member access** expressions. [expr.ref] specifies what the result of such an expression designates, and its type and value category. How the name `E2` is looked up and whether the `template` keyword is needed are specified by [[basic.lookup.qual]] and [[class.member.lookup]].

The `decltype`s in the example are all parenthesized. Without parentheses, `decltype(cs.m)` gives the member's declared type `int`; only with parentheses does it give `const int&` from the expression's type and value category ([[dcl.type.decltype]]).

## Syntax (¶1)

¶1 A postfix expression followed by `.` or `->`, optionally followed by the keyword `template`, and then by an *id-expression* or a *splice-expression* {{c++26}}, is a postfix expression.

Note 1 says `template` makes the following unqualified name be treated as a template name ([[temp.names]]). In a dependent context you have to write `obj.template get<0>()`, otherwise the `<` is parsed as less-than.

## The arrow reduces to the dot (¶2)

¶2 The expression before the arrow must be a prvalue of pointer type, and `E1->E2` is converted to `(*(E1)).E2`; the rest of this subclause deals only with the dot form. Footnote 43 reminds that `(*(E1))` is an lvalue.

So the arrow has no semantics of its own. Every property of `p->m` comes from `(*p).m`, and `*p` is an lvalue, so `std::move(p)->m` is also an lvalue. To get an xvalue, write `std::move(*p).m`.

¶2 says two more things about the expression before the dot:

- When `E2` designates a static member or an enumerator, the expression before the dot is a [[g:discarded-value-expression|discarded-value expression]]: it is still evaluated, and its value is discarded.
- When `E2` designates a non-static data member or a direct base class relationship {{c++26}}, the expression before the dot must be a glvalue. If a prvalue is written (`S{}.m`), the temporary materialization conversion ([[conv.rval]]) is applied first to get an xvalue.

Class types can overload `->` ([[over.ref]]): `x->m` is interpreted as `(x.operator->())->m`, recursively until a built-in pointer is obtained. Smart pointers and iterators rely on this rule.

## The object expression is always evaluated (¶3)

```cpp run title="static-via-object.cpp" ok
#include <cstdio>

struct S { static int sm; };
int S::sm = 42;
S make() { std::puts("make() called"); return {}; }

int main() {
    int x = make().sm;   // prints make() called: the object expression is evaluated, then discarded
    int y = S::sm;       // no object involved
    return x == y ? 0 : 1;
}
```

¶3 The postfix expression before the dot is evaluated, and the result of that evaluation together with `E2` determines the result of the whole expression. Footnote 44 stresses that this subexpression is evaluated whenever the member access expression is evaluated, even if its result isn't needed, e.g. when `E2` is a static member. `sizeof(make().sm)` is different: that is an unevaluated operand, and `make()` is not called.

## The type of the object expression (¶4–¶6)

¶4 In `E1.E2`, `E1` is called the [[g:object-expression|object expression]]. If the object expression has scalar type, `E2` must be the pseudo-destructor of the same type (ignoring cv) ([[expr.prim.id.dtor]]), and `E1.E2` is a prvalue of type "function of no parameters returning `void`" that can only be called. So `p->~T()` is valid even when `T` is `int`, and the call ends the lifetime of that scalar object ([[expr.call#4]]).

```cpp run title="pseudo-dtor-access.cpp" ok
#include <new>

using I = int;

int main() {
    int x = 0;
    x.~I();          // pseudo-destructor call, ends the lifetime of x
    ::new (&x) int(1);
    int* p = &x;
    p->~I();         // equivalent to (*p).~I()
    ::new (p) int(2);
    return x == 2 ? 0 : 1;
}
```

¶5 Otherwise the object expression must have class type, and the class must be complete unless the member access appears in the definition of that class itself (a member function body, `this->m` in a default member initializer). Note 3: if lookup after the class is complete would give a different result, the program is ill-formed ([[class.member.lookup]]).

```cpp title="incomplete-access.cpp" error
struct Fwd;
int get(Fwd& f);

struct Self {
    int a = 1;
    int b = this->a + 1;          // OK: within the class's own definition
};

int get(Fwd& f) { return f.x; }   // error: Fwd is incomplete
```

¶6 {{c++26}} If `E2` is a *splice-expression* ([[expr.prim.splice]]), it must designate a member of `E1`'s type `T1`, or a direct base class relationship `(T1, B)`. That is, the member represented by the reflection `r` in `obj.[: r :]` must belong to `obj`'s class itself ([[P2996R13]]).

## Type and value category of the result (¶7–¶8)

¶7 If `E2` designates a bit-field, `E1.E2` is also a bit-field, so its address can't be taken and it can't bind to a non-`const` reference. Below, *cq* stands for `const` or nothing, and *vq* for `volatile` or nothing.

### Reference members

!!! std
    If E2 designates an entity that is declared to have type "reference to T", then E1.E2 is an lvalue of type T.

¶8 Accessing a reference member always gives an lvalue whose type is the referenced type `T`, without `E1`'s cv added, regardless of whether `E1` is an lvalue or an xvalue. The object a reference member refers to is not a subobject of `E1`, so whether `E1` is about to expire or is `const` has nothing to do with it.

### The other cases

| Item | `E2` designates | Value category | Type |
|---|---|---|---|
| ¶8.1 | A static data member (of type `T`) | lvalue | `T` |
| ¶8.2 | A non-static data member (of type *cq2 vq2* `T`) | lvalue if `E1` is an lvalue, otherwise xvalue | *cq12 vq12* `T`; *vq12* `T` for a `mutable` member |
| ¶8.3 | A member function (overload set) | lvalue for a static member function, prvalue for a non-static one | Function type |
| ¶8.4 | A nested type | Ill-formed | |
| ¶8.5 | A member enumerator (of type `T`) | prvalue | `T` |
| ¶8.6 | A direct base class relationship `(D, B)` {{c++26}} | lvalue if `E1` is an lvalue, otherwise xvalue | cv `B` |
| ¶8.7 | Anything else | Ill-formed | |

### Non-static data members: the union of cv (¶8.2)

Let `E1` have type *cq1 vq1* `X` and the member be declared with type *cq2 vq2* `T`. The result's cv is the union of the two: if either the object or the member is `const`, the result is `const`, and likewise for `volatile`. The only exception is a `mutable` member, which doesn't inherit `const` but still inherits `volatile`.

This is why a `const` member function can't modify members: in a `const` member function, the object expression of `this->m` has type `const X`, so the result is `const`.

The value category follows the object expression. This is also the language basis for moving an expiring object member by member: `std::move(s).m` is itself an xvalue and can bind directly to `T&&`.

### Member functions (¶8.3)

When `E2` designates an overload set, `E1.E2` must be the left operand of a member function call (possibly parenthesized), and overload resolution ([[over.match]]) selects the function:

- ¶8.3.1 A static member function: `E1.E2` is an lvalue and can be taken out and used; `int (*p)() = s.sf;` is valid.
- ¶8.3.2 A non-static member function: `E1.E2` is a prvalue that can only be called immediately.

`s.f` would represent a function bound to an object, and C++ has no such value that can be stored on its own. Use a lambda or `std::bind_front` when needed. Note 5: redundant parentheses are ignored, so `(s.f)()` is a valid call.

```cpp title="member-fn-access.cpp" error
struct S {
    int f() { return 1; }
    static int sf() { return 2; }
    struct Nested {};
};

void t(S s) {
    int (*p)() = s.sf;      // OK: ¶8.3.1
    auto q = s.f;           // error: a non-static member function can only be called
    auto r = &s.f;          // error: can't take its address, write &S::f
    S::Nested n = s.Nested{};   // error: ¶8.4, can't access a nested type through an object
    (void)p;
}
```

### Direct base class relationships (¶8.6) {{c++26}}

Static reflection introduces a new kind of accessible thing: the direct base class relationship. The reflection returned by `std::meta::bases_of(^^D, ctx)[i]` represents "`D` has `B` as a direct base class", and `d.[: r :]` designates that direct base class subobject of `d`. `E1` is first implicitly converted to "reference to cv `D`" (an lvalue or rvalue reference following `E1`), and the result is the subobject of type cv `B`, with the value category following `E1`.

Example 1 in the standard shows how it helps resolve ambiguity:

```cpp title="splice-base.cpp"
#include <meta>

struct B { int b; };
struct C : B { int get() const { return b; } };
struct D : B, C { };          // D has two B subobjects: the direct one, and one indirectly via C

constexpr int f() {
    D d = {1, {}};
    // the reflection designates exactly D's direct base B; static_cast<B&>(d) would be ambiguous here
    B& b = d.[: std::meta::bases_of(^^D, std::meta::access_context::current())[0] :];
    b.b += 10;
    return 10 * b.b + d.get();
}
static_assert(f() == 110);
```

Clang 23 doesn't implement static reflection yet (there is no `<meta>` header), so this example has not been verified by compiling.

## Ambiguous bases (¶9)

¶9 If `E2` designates a non-static member and the class of which `E2` is a direct member is an ambiguous base of the designating class of `E2` ([[class.access.base]]), the program is ill-formed. Note 6: it is likewise ill-formed if the naming class is an ambiguous base of the object expression's type.

```cpp title="ambiguous-base.cpp" error
struct A { int x; };
struct L : A {};
struct R : A {};
struct D : L, R {};

int f(D& d) {
    int a = d.L::x;     // OK: A is an unambiguous base of L
    return d.x + a;     // error: name lookup is ambiguous, there are two A::x
}

int g(D& d) {
    return d.A::x;      // error: A is an ambiguous base of D
}
```

## Non-similar object type: UB (¶10)

```cpp run title="not-similar.cpp" ub
struct A { int i; };
struct B { int j; };
struct D : A, B {};

int main() {
    D d{};
    int a = static_cast<B&>(d).j;        // OK: the object expression designates d's B subobject
    int b = reinterpret_cast<B&>(d).j;   // UB: the result still designates d, whose type is not B
    return a + b;
}
```

!!! std
    If E2 designates a non-static member (possibly after overload resolution) or direct base class relationship and the result of E1 is an object whose type is not similar to the type of E1, the behavior is undefined.

¶10 Two types are [[conv.qual|similar]], roughly, if they are the same after ignoring cv at every level. `reinterpret_cast` doesn't adjust the address, and `D` and `B` are not pointer-interconvertible ([[expr.reinterpret.cast]]), so `reinterpret_cast<B&>(d)` still designates `d` itself. The object expression of `.j` has type `B`, while the actual object has type `D`, so the behavior is undefined. `static_cast` performs the correct address adjustment. Clang has a dedicated warning for this pattern, `-Wreinterpret-base-class`.

This rule makes the access itself UB, without waiting for the aliasing rule of [[basic.lval#11]] to judge a read or write of the member's value. Merely taking the address `&p->m`, or calling a member function that doesn't touch any data, is equally UB.

Two related rules:

- Accessing a non-static data member or calling a non-static member function of an object before its lifetime starts or after it ends is UB ([[basic.life#7]], [[basic.life#8]]).
- Reading an inactive member of a union is UB because it is not within its lifetime; but assigning to it can switch the active member by the rules of [[class.union]]. Writing the expression `u.f` itself doesn't violate ¶10: the object expression `u` has the union type.

```cpp run title="union-access.cpp" ok
union U { int i; float f; };

int main() {
    U u{.i = 1};
    u.f = 2.0f;           // assignment makes f the active member
    float x = u.f;        // OK
    // int y = u.i;       // UB: i is not within its lifetime
    return x == 2.0f ? 0 : 1;
}
```

## Implementation view

!!! impl
    - Access to a non-static data member compiles to the object's base address plus a constant offset; `p->m` is a single load with an offset.
    - Compilers rely on ¶10 and the aliasing rules for type-based alias analysis (TBAA), assuming member accesses through `A*` and through `B*` don't overlap.
    - For `p->static_member` with `p` null, the generated code usually doesn't dereference `p`. But per the standard, ¶3 requires evaluating `*p`, and applying `*` to a pointer that doesn't point to an object is UB ([[expr.unary.op#1]]). Clang 23's UBSan (`-fsanitize=null`) doesn't report this case, and it is accepted in constant expressions too, without the required diagnostic.

## Common misconceptions

!!! pitfall "`std::move(obj).ref` is an xvalue"
    Accessing a reference member always gives an lvalue. When generic code forwards member by member and a member may be a reference, use C++23's `std::forward_like<Self>(self.m)` to forward according to the object's value category; don't rely on `std::move(self).m`.

!!! pitfall "Modifying a `mutable` member of a `const` object is UB"
    It isn't. A `mutable` member doesn't inherit `const`, and modifying a `mutable` member of a `const` object is well-defined ([[dcl.type.cv]]).

## Questions

!!! question "Question 1"
    Given `struct S { const int c = 0; int& r; }; S s{0, x};`, what are `decltype((std::move(s).c))` and `decltype((std::move(s).r))`?

<details markdown="1">
<summary>Answer</summary>

`std::move(s).c`: by ¶8.2, `E1` is an xvalue, so the result is an xvalue; `s` is not `const`, the member is `const int`, and the union is `const int`. So it is `const int&&`. `std::move(s).r`: a reference member is always an lvalue, of type `int`, so it is `int&`.
</details>

!!! question "Question 2"
    Given `struct S { static int n; }; S* p = nullptr; int x = p->n;`, is this UB? What about `decltype(*p)::n`?

<details markdown="1">
<summary>Answer</summary>

`p->n` reduces to `(*p).n`. ¶3 and footnote 44 say the object expression `*p` is evaluated even though `n` is a static member; `p` doesn't point to an object, so by [[expr.unary.op#1]] this is UB. In practice compilers don't emit a dereference, and Clang 23 even accepts it in constant expressions, but per the standard it is still UB.

`decltype(*p)` is an unevaluated operand giving `S&`. `decltype(*p)::n` is ill-formed because a reference type can't be a nested-name-specifier; write `std::remove_reference_t<decltype(*p)>::n`. Neither form evaluates `p`.
</details>
