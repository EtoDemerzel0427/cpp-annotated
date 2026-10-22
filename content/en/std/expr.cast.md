---
title: Explicit type conversion (cast notation)
summary: "A C-style cast (T)e interprets itself, in a fixed order, as one of the named casts or a combination of them; it can ignore access control on base classes and, when a class is incomplete, may not adjust the pointer, so C++ code should use the named casts instead."
updated: 2026-10-19
---

!!! tldr
    - `(T)e` tries, in order, `const_cast`, `static_cast`, `static_cast` followed by `const_cast`, `reinterpret_cast`, and `reinterpret_cast` followed by `const_cast`, and uses the first interpretation that matches, even if that interpretation is ill-formed.
    - It never performs a `dynamic_cast`, so `(Derived*)p` does no run-time check.
    - When it acts as a `static_cast`, it can ignore `private`/`protected` inheritance and still adjust the pointer correctly.
    - When one of the two classes is incomplete, it is unspecified whether it is interpreted as `static_cast` or `reinterpret_cast`, and the resulting pointer may not be adjusted.
    - A functional cast with a single argument, `T(e)`, is exactly equivalent to `(T)e`, with the same problems.

## Notation and result (¶1–¶3)

`(T)e` is the cast notation inherited from C; C++ also has four named casts: `static_cast`, `const_cast`, `reinterpret_cast` and `dynamic_cast`. ¶2 lists these three notations and gives the grammar:

```text
cast-expression:
    unary-expression
    ( nofun-type-id ) cast-expression
```

The grammar is right-recursive, so `(T)a.b` is `(T)(a.b)`, `(T)*p` is `(T)(*p)`, and `(T)a + b` is `((T)a) + b`. The *nofun-type-id* in the parentheses ([[dcl.name]]) is a type name that cannot be a function type: function types have no values, so converting to one makes no sense.

¶1 The type of the result is `T`. If `T` is an lvalue reference type or an rvalue reference to function type, the result is an lvalue; if it is an rvalue reference to object type, the result is an xvalue; otherwise it is a prvalue. Note 1 adds that prvalues of non-class type lose their cv-qualification, so the type of `(const int)3` is `int` ([[expr.prop]]).

¶3 Apart from the conversions listed in ¶4 below and the user-defined conversions through constructors or conversion functions ([[class.conv]]), every other conversion is ill-formed.

By [[expr.type.conv#1]], a single-argument functional cast `T(e)` is equivalent to `(T)e`, and everything on this page applies to it.

## Order of interpretations (¶4)

```cpp title="c-cast-order.cpp" error
struct A { };
struct I1 : A { };
struct I2 : A { };
struct D : I1, I2 { };
A* foo(D* p) {
    return (A*)(p);             // error: the static_cast interpretation is chosen, and A is an ambiguous base
}

int*** ptr = 0;
auto t = (int const* const* const*)ptr;   // OK: const_cast interpretation

struct S {
    operator const int*();
    operator volatile int*();
};
int* p = (int*)S();             // error: two interpretations as static_cast + const_cast
```

¶4 The cast notation can perform the following five conversions, each subject to the restrictions and behavior of the corresponding named cast:

| Order | Interpretation |
|---|---|
| ¶4.1 | `const_cast` |
| ¶4.2 | `static_cast` |
| ¶4.3 | `static_cast` followed by `const_cast` |
| ¶4.4 | `reinterpret_cast` |
| ¶4.5 | `reinterpret_cast` followed by `const_cast` |

If a conversion can be interpreted in more than one way, the interpretation that appears first in the list is used, even if it makes the conversion ill-formed. The compiler does not try each one and use whichever compiles; it commits as soon as one matches in form.

In the first function, `D*` to `A*` is in form a derived-to-base `static_cast`, so that interpretation is chosen; `A` is an ambiguous base, so the conversion is ill-formed. If falling back to `reinterpret_cast` were allowed, this would silently produce a wrong, unadjusted pointer.

`int***` to `int const* const* const*` only adds cv-qualification; `const_cast` can do that, and it comes first.

`S` can be `static_cast` to either `const int*` or `volatile int*` and then `const_cast` to `int*`. ¶4 says that if a conversion can be interpreted in more than one way as a `static_cast` followed by a `const_cast`, it is ill-formed.

### What common casts actually mean

| `(T)e` | Actual interpretation |
|---|---|
| `(int)3.7`, `(double)n`, `(Enum)i` | `static_cast` |
| `(Derived*)base_ptr` | `static_cast`, unchecked |
| `(int*)const_int_ptr` | `const_cast` |
| `(char*)"literal"` | `const_cast` |
| `(long*)int_ptr`, `(std::uintptr_t)ptr` | `reinterpret_cast` |
| `(char*)const_int_ptr` | `reinterpret_cast` plus `const_cast` |
| `(void)expr` | `static_cast` ([[expr.static.cast#4]]) |

`dynamic_cast` is not on the list, so a C-style cast never does a run-time check.

## Ignoring access control on base classes (¶4.6–¶4.8)

```cpp run title="c-cast-private-base.cpp" ok
struct X { int x = 2; };
struct B { int b = 1; };
struct D : X, private B { int d = 3; };   // B is a private base, and not the first base

int main() {
    D d;
    B* pb = (B*)&d;                  // OK: ¶4.6, adjusted to the B subobject
    D* back = (D*)pb;                // OK: ¶4.8, downcast
    int D::* pm = (int D::*)&B::b;   // OK: ¶4.8, pointer to base member to pointer to derived member
    // static_cast<B*>(&d);          // error: B is an inaccessible base
    return (pb->b == 1 && back == &d && d.*pm == 1) ? 0 : 1;
}
```

¶4 says that when the cast notation performs a `static_cast` in the following situations, the conversion is valid even if the base class is inaccessible:

- ¶4.6 a pointer to, or an lvalue or rvalue of, a derived class type converted to a pointer or reference to an unambiguous base class;
- ¶4.7 a pointer to member of a derived class converted to a pointer to member of an unambiguous non-virtual base class;
- ¶4.8 a pointer to, glvalue of, or pointer to member of an unambiguous non-virtual base class converted to a pointer, reference or pointer to member of a derived class.

The named casts cannot do this: `static_cast` is an error because the base is inaccessible, and `reinterpret_cast` does no address adjustment. The C-style cast is the only means in the language of legally crossing private inheritance; Example 2 in [[expr.dynamic.cast]] uses it to obtain a pointer to a private base. Access control expresses the class author's design, and this cast can bypass it without leaving a trace.

## Incomplete classes (¶5)

```cpp run title="c-cast-incomplete.cpp" unspecified
struct P;
struct Q;
Q* f(P* p) { return (Q*)p; }   // P and Q are incomplete here: the interpretation is unspecified

struct X { int x; };
struct P { int a; };
struct Q : X, P {};            // P is Q's second base, so the two interpretations differ

int main() {
    Q q;
    P* pp = &q;
    return f(pp) == &q ? 0 : 1;   // static_cast interpretation gives 0; reinterpret_cast gives 1
}
```

¶5 Both the operand and the target type may be pointers to incomplete classes. If both point to class types and at least one of them is incomplete, it is unspecified whether the `static_cast` or the `reinterpret_cast` interpretation is used, even if the two classes really are related by inheritance.

Note 2 explains why neither is required: the class may be defined later in the same translation unit, and a multi-pass compiler could interpret the cast according to the complete class. GCC, Clang and MSVC all decide at the point of the cast, cannot see the inheritance relationship, and so treat it as `reinterpret_cast` without adjusting the address. With Clang 23 this program exits with 1.

The named casts don't have this problem: `static_cast<Q*>(p)` is simply ill-formed when the classes are incomplete, and `reinterpret_cast` explicitly does not adjust.

## Why to use the named casts instead

- The intent is invisible. From `(Foo*)p` you cannot tell whether it is a downcast, a removal of const, or a reinterpretation. Each named cast expresses one intent, and they are easy to search for.
- The meaning changes with context, without any diagnostic. `(Derived*)base` is a `static_cast` with public inheritance; change it to private inheritance and it still compiles (¶4.6); remove a header so the class is incomplete, and it becomes a `reinterpret_cast` (¶5); replace the base with an unrelated class, and it still compiles.
- It can do two dangerous things at once, such as removing const and reinterpreting the type (¶4.5).
- `T(e)` has the same problems, while looking like a constructor call.

!!! tip "Tools"
    GCC and Clang's `-Wold-style-cast` warns on every C-style cast, but ignores the functional notation. Clang-Tidy's `cppcoreguidelines-pro-type-cstyle-cast` and `google-readability-casting` can suggest the corresponding named cast. C++ Core Guidelines ES.48 and ES.49 recommend avoiding casts, and using named casts when a cast is necessary.

!!! history
    C has only one explicit conversion, `(T)e`. C++98 introduced the four named casts and defined the C-style cast as a combination of them; the access-control exception and the unspecified behavior for incomplete classes have existed since then. C++11 added rvalue reference target types, whose result is an xvalue.

## Common misconceptions

!!! pitfall "`(Derived*)p` checks the type"
    It is a `static_cast`, not a `dynamic_cast`. A downcast to the wrong type is UB without any warning.

!!! pitfall "`(int)x` and `int(x)` are different"
    The two are identical. To forbid narrowing, write `int{x}`; to state the intent, write `static_cast<int>(x)`.

## Questions

!!! question "Question 1"
    What is `const char* s = "abc"; auto p = (unsigned char*)s;` interpreted as?

<details markdown="1">
<summary>Answer</summary>

Check in order: `const_cast` doesn't work, since `const char*` and `unsigned char*` are not similar types; `static_cast` doesn't work, since unrelated object pointers cannot be `static_cast` to each other; `static_cast` to `const unsigned char*` followed by `const_cast` doesn't work either; `reinterpret_cast` alone cannot cast away constness. Finally, `reinterpret_cast` to `const unsigned char*` followed by `const_cast` to `unsigned char*` works: that is ¶4.5.

Reading through `p` is fine, since `unsigned char` may access any object; writing through `p` modifies a string literal and is UB.
</details>

!!! question "Question 2"
    Given `struct X { int x; }; struct B { int b; }; struct D : X, private B {}; D d;`, outside the members and friends of `D`, how do `((B&)d).b` and `reinterpret_cast<B&>(d).b` differ?

<details markdown="1">
<summary>Answer</summary>

By ¶4.6, `(B&)d` is a `static_cast` that ignores access; the result refers to the `B` base class subobject of `d`, and reading `.b` is fine.

`reinterpret_cast<B&>(d)` does not adjust the address. `B` is not the first base, so `d` and its `B` subobject are not pointer-interconvertible, and the result still refers to `d` itself. `D` and `B` are not similar, so accessing `.b` through it is UB by [[expr.ref#10]].
</details>
