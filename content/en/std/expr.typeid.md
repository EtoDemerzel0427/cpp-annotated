---
title: Type identification (typeid)
summary: "typeid yields a std::type_info object describing a type: a polymorphic object gives its actual type at run time and the operand is evaluated, other expressions give the static type without evaluation; typeid(*p) on a null pointer throws std::bad_typeid; top-level cv and references are ignored; std::type_info must be declared before use."
updated: 2026-10-19
---

!!! tldr
    - `typeid(e)` and `typeid(T)` yield a `const std::type_info` lvalue referring to an object that lives until the end of the program, so references or pointers to it can be kept safely.
    - When the operand is a glvalue of polymorphic class type, `typeid` evaluates it and gives the object's actual type; otherwise the operand is not evaluated and the expression's static type is given.
    - `typeid(*p)` on a null pointer is not undefined behavior; it throws `std::bad_typeid`. This exception looks only at the syntactic form and applies only to the outermost `*`.
    - Top-level `const`, `volatile` and references are all ignored: `typeid(const D&) == typeid(D)`.
    - You must include `<typeinfo>` or `import std;` before using `typeid`, otherwise the program is ill-formed.

## Static type or actual type

<div class="compare" markdown="1">

```cpp run ok
#include <typeinfo>
struct B {};         // no virtual functions
struct D : B {};

int main() {
  D d;
  B* p = &d;
  return typeid(*p) == typeid(B)
    ? 0 : 1;         // gives B
}
```

```cpp run ok
#include <typeinfo>
struct B { virtual ~B() = default; };
struct D : B {};

int main() {
  D d;
  B* p = &d;
  return typeid(*p) == typeid(D)
    ? 0 : 1;         // gives D
}
```

</div>

The two programs differ only by a virtual destructor. On the left, `B` is not a polymorphic class, so `typeid(*p)` looks only at the expression's static type `B`, determined at compile time. On the right, `B` is a **polymorphic class** (a class with at least one virtual function, [[class.virtual]]); its objects carry a pointer to type information, and `typeid` reads the object's actual type `D` at run time.

`typeid` is one half of run-time type identification (RTTI); the other half is [[expr.dynamic.cast]]. Its result can be compared with `==`, can give an implementation-defined name, and can be wrapped in a `std::type_index` to go into associative containers.

## The result (¶1)

¶1 The result of a `typeid` expression is an lvalue of static type `const std::type_info` ([[type.info]]). Its dynamic type is either `const std::type_info` or some implementation-defined class publicly derived from `std::type_info`. Footnote 46 recommends naming that class `extended_type_info`.

The object the result refers to lives until the end of the program; whether its destructor is called at program end is unspecified. Three things follow:

- Keeping a `const std::type_info&` or `const std::type_info*` is safe; they won't dangle.
- The copy operations of `std::type_info` are deleted; you can only hold a reference or pointer, or wrap it in a `std::type_index`.
- Two `typeid`s of the same type don't necessarily give the same object. The standard only guarantees they compare equal with `==`, not `&typeid(T) == &typeid(T)`.

## Polymorphic glvalues: evaluated, actual type (¶4)

¶4 When `typeid` is applied to a glvalue of polymorphic class type, the result refers to the type of the **most derived object** (the complete object that is not a subobject of any other object, [[intro.object]]) that the glvalue refers to, i.e. its **dynamic type**.

Knowing the dynamic type requires reading the object at run time, so in this case the operand is evaluated. [[expr.context]] and [[basic.def.odr]] both exclude this case when defining unevaluated operands.

## Other operands: not evaluated, static type (¶5)

¶5 When the operand is an expression other than a glvalue of polymorphic class type, the result refers to the expression's static type, and:

- the lvalue-to-rvalue, array-to-pointer and function-to-pointer conversions are not applied, so `typeid` can tell array and function types apart;
- if the expression is a prvalue, the temporary materialization conversion ([[conv.rval]]) is applied;
- the expression is an **unevaluated operand** (an operand that is not executed at run time, [[expr.context]]).

```cpp run title="typeid-eval.cpp" ok
#include <typeinfo>

struct P { virtual ~P() = default; };
struct Q : P {};
struct N {};

int calls = 0;
P& get_poly() { ++calls; static Q q; return q; }
N& get_plain() { ++calls; static N n; return n; }

int main() {
  auto& a = typeid(get_poly());   // polymorphic glvalue: get_poly() is called
  auto& b = typeid(get_plain());  // not polymorphic: get_plain() is not called
  int arr[3];
  bool c = typeid(arr) == typeid(int[3]);  // didn't decay to a pointer
  return calls == 1 && a == typeid(Q) && b == typeid(N) && c ? 0 : 1;
}
```

Clang 23 gives a `-Wpotentially-evaluated-expression` warning for `typeid(get_poly())`: the expression with side effects is still evaluated even though it is the operand of `typeid`. Many people believe the operand of `typeid` is never evaluated, and this warning exists for exactly that reason.

!!! lawyer "Prvalue materialization and deleted destructors"
    Paragraph 5 applies temporary materialization to prvalues. [[class.temporary#1]] says that even when the creation of a temporary object is unevaluated, all the semantic restrictions apply as if it were created and later destroyed, including that the destructor is accessible and not deleted; the only exception is the operand of `decltype`. So for a class `S` with a deleted destructor, `typeid(S())` is ill-formed per the standard. Clang 23 accepts it, which is inconsistent with the standard.

## `*p` on a null pointer (¶3)

¶3 If the operand is a unary `*` expression (possibly parenthesized) and the operand of the `*` evaluates to a null pointer, the `typeid` expression throws an exception of a type that would match a handler of type `std::bad_typeid` ([[bad.typeid]]). Note 1 reminds that in other contexts, applying `*` to a null pointer is undefined behavior ([[expr.unary.op]]).

```cpp run title="bad-typeid.cpp" ok
#include <typeinfo>

struct P { virtual ~P() = default; };

int main() {
  P* p = nullptr;
  try {
    (void)typeid(*p);     // throws std::bad_typeid
    return 1;
  } catch (const std::bad_typeid&) {}
  try {
    (void)typeid((*p));   // the same with parentheses
    return 1;
  } catch (const std::bad_typeid&) {}
  return 0;
}
```

For a polymorphic glvalue, `typeid` has to read the vtable pointer in the object, and reading it through a null pointer is bound to go wrong. The standard recognizes the most common form, `typeid(*p)`, syntactically, so that implementations check for null before reading. The exception looks only at the syntactic form, and its scope is narrow:

```cpp title="bad-typeid-narrow.cpp" ub
#include <typeinfo>

struct P {
  virtual ~P() = default;
  P& self() { return *this; }
};

int main() {
  P* p = nullptr;
  (void)typeid(p->self());  // UB: not a * expression; a member function is called on a null pointer first
  (void)typeid(*&*p);       // UB: the inner *p is an ordinary dereference
}
```

In the second line the outermost operator is indeed `*`, but evaluating its operand `&*p` already performs an ordinary `*` on the null pointer, which paragraph 3 doesn't protect.

For a non-polymorphic type, the operand of `typeid(*p)` is not evaluated and `*p` is never executed, so there is neither an exception nor undefined behavior; the result is just the static type.

## Type operands and cv-qualification (¶6, ¶7)

¶6 The result of `typeid(type-id)` refers to that type. If the type is a reference, the result refers to the referenced type, without cv-qualification. Note 2 reminds that the *type-id* can't be a cv-qualified or ref-qualified function type, so `typeid(void() const)` is ill-formed.

¶7 If the type of the expression or *type-id* is cv-qualified, the result refers to the cv-unqualified type. All four comparisons in Example 1 of the standard are `true`:

```cpp run title="typeid-cv.cpp" ok
#include <typeinfo>

class D {};
D d1;
const D d2;

int main() {
  bool ok = typeid(d1) == typeid(d2)
         && typeid(D) == typeid(const D)
         && typeid(D) == typeid(d2)
         && typeid(D) == typeid(const D&);
  // only top-level cv is dropped: the const of the pointee is part of the type
  bool diff = typeid(int*) != typeid(const int*);
  static_assert(typeid(int) == typeid(const volatile int&));
  return ok && diff ? 0 : 1;
}
```

`typeid` answers what type the object is. Whether the object is `const`, and whether it is accessed directly or through a reference, doesn't change the object's type, so both are ignored. This is similar to how template argument deduction by value drops cv and references, except that `typeid` doesn't let arrays and functions decay to pointers.

The `static_assert` line can be decided at compile time because `type_info::operator==` is `constexpr` since C++23.

## Prerequisites (¶2, ¶8)

¶2 If the type of the operand is a class type or a reference to a class type (possibly cv-qualified), the class must be complete. A pointer to an incomplete class is fine, because then it is the pointer type that is identified.

```cpp title="typeid-incomplete.cpp" error
#include <typeinfo>

struct I;

void f(I* p) {
  (void)typeid(I*);   // OK: pointer type
  (void)typeid(p);    // OK: the expression's type is I*
  (void)typeid(I);    // error: I is incomplete
  (void)typeid(*p);   // error: the expression's type I is incomplete
}
```

¶8 `std::type_info` is not predeclared by the language. Before a `typeid` expression, the standard library's declaration of it must be reachable, from `<typeinfo>` or the standard library module `std` ([[std.modules]]); otherwise the program is ill-formed.

```cpp title="typeid-no-header.cpp" error
int main() {
  return typeid(int) == typeid(int);   // error: no <typeinfo>
}
```

Clang 23's diagnostic is `you need to include <typeinfo> or import std before using the 'typeid' operator`. There are few places where the language depends on library declarations; similar ones are `std::initializer_list`, `<compare>` for `<=>`, and `<coroutine>` for coroutines.

## During construction and destruction (¶9)

¶9 is a note pointing to [[class.cdtor#5]]: in a constructor or destructor (including functions they call directly or indirectly), if the operand refers to the object under construction or destruction, the result is the class of the current constructor or destructor.

```cpp run title="typeid-ctor.cpp" ok
#include <typeinfo>

struct B {
  virtual ~B() = default;
  B() { in_ctor = &typeid(*this); }
  const std::type_info* in_ctor;
};
struct D : B {};

int main() {
  D d;
  return *d.in_ctor == typeid(B) && typeid(d) == typeid(D) ? 0 : 1;
}
```

While `B` is being constructed, the `D` part doesn't exist yet, so the object is treated as a `B`, for the same reason virtual calls during construction dispatch to the current class. [[class.cdtor#5]] also says that if the operand refers to the object under construction and its static type is neither the current class nor one of its bases, the behavior is undefined.

## Constant evaluation

Since C++20 ([[P1327R1]]), polymorphic `typeid` can appear in constant expressions, provided the object's dynamic type is known during constant evaluation. When the dynamic type is not known at compile time, e.g. for an object referred to by a reference parameter, it is not a constant expression ([[expr.const.core#2.30]]).

## Implementation view

!!! impl
    - In the Itanium C++ ABI (used by GCC and Clang on Linux and macOS), a polymorphic class's vtable stores a pointer to the `type_info` object in the word just before the location the vtable pointer points to. `typeid(*p)` compiles to three steps: check for null, read the vtable pointer, read the word before it. The non-polymorphic case and `typeid(T)` directly refer to a `_ZTI...` symbol determined at compile time.
    - The result of `type_info::name()` is implementation-defined. GCC and Clang return the Itanium mangled name (such as `1D`, `PKi`), which can be demangled with `abi::__cxa_demangle`; MSVC returns a readable name (such as `class D`). It is guaranteed to be neither unique nor readable; don't base logic on it.
    - On platforms where `type_info` objects are globally unique, equality only needs to compare addresses; on some platforms (especially involving shared libraries and symbol visibility), the name strings have to be compared.
    - GCC and Clang reject `typeid` when RTTI is disabled with `-fno-rtti`; MSVC's `/GR-` is similar.

## History and evolution

!!! history
    - C++98: `typeid` was standardized together with `std::type_info`.
    - C++11: added `type_info::hash_code()` and `std::type_index`, making it easy to use in unordered containers; the copy operations of `type_info` became deleted.
    - C++20: polymorphic `typeid` usable in constant expressions ([[P1327R1]]).
    - C++23: `type_info::operator==` became `constexpr`; the standard library module `std` was introduced, which can also provide the declaration required by paragraph 8.

## Common misconceptions

!!! pitfall "The operand of typeid is never evaluated"
    In `typeid(*make_shape())`, if `make_shape()` returns a pointer to a polymorphic class, the function is called; if it returns a non-polymorphic type, it isn't. Add a virtual function to the class and the same line of code behaves differently.

!!! pitfall "typeid(*base_ptr) always gives the actual type"
    If the base class has no virtual functions, `typeid(*p)` is always the base class type, regardless of what the object actually is. To get the dynamic type, the base class needs at least one virtual function, typically a virtual destructor.

!!! pitfall "Comparing name() or &typeid(T)"
    Deciding whether types are the same with `strcmp(a.name(), b.name())` or by comparing `type_info` addresses is not portable. Use `==` or `std::type_index`.

## Questions

!!! question "Question 1"
    Given `struct P { virtual ~P(); }; P* f();`, does `sizeof(typeid(*f()))` call `f`? What is the value of `noexcept(typeid(*f()))`?

<details markdown="1">
<summary>Answer</summary>

No. The operand of `sizeof` is an unevaluated operand, and none of its subexpressions are evaluated. `typeid` evaluating a polymorphic operand only happens when the `typeid` expression itself is evaluated.

`noexcept(typeid(*f()))` is `false`. The expression contains a potentially-throwing `typeid` (the `*p` form on a polymorphic class may throw `std::bad_typeid`, see [[except.spec]]), plus a call to `f`, which is not declared `noexcept`.
</details>

!!! question "Question 2"
    Given `int a[3];`, what are `typeid(a) == typeid(int*)` and `typeid(+a) == typeid(int*)`?

<details markdown="1">
<summary>Answer</summary>

The first is `false`: paragraph 5 says no array-to-pointer conversion is applied, and `a` has type `int[3]`.

The second is `true`: unary `+` requires an arithmetic or pointer operand, so `a` first decays to `int*`, and `+a` is a prvalue of type `int*`.
</details>

## Summary

!!! summary
    | Operand | Evaluated? | Result refers to |
    |---|---|---|
    | glvalue of polymorphic class type | Evaluated | The dynamic type |
    | The `*p` form with `p` null, of polymorphic class type | Evaluated | Throws `std::bad_typeid` |
    | Other expressions | Not evaluated; no decay; prvalues materialized | The static type |
    | *type-id* | N/A | That type, without reference and top-level cv |
    | Object under construction or destruction | Evaluated | The class of the current constructor or destructor |
