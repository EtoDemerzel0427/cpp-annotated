---
title: The type of an expression
summary: The type of an expression is never a reference type, and evaluating a dangling reference is UB; prvalues of non-class, non-array type are not cv-qualified; the algorithm that finds the composite pointer type when two pointer operands need a common type.
updated: 2026-10-19
---

!!! tldr
    - The type of an expression is never a reference: the reference is removed before analysis, leaving only the value category. The `&` in `decltype((r))` comes from the value category, not the type.
    - When the storage of the object a reference refers to has ended, any evaluation of that reference is UB, not just reading its value.
    - Prvalues of non-class, non-array type are not cv-qualified, so the `const` in `const int f();` has no effect; class and array prvalues keep their cv-qualifiers.
    - `p == q`, `c ? p : q` and the like bring two pointers to the composite pointer type: a null pointer constant yields to the other side, `void*` absorbs object pointers, base class pointers absorb derived class pointers, and similar types merge cv level by level.
    - When merging cv, if a qualifier is added at some level, every level outside it (except the outermost) gets `const`, so `int**` and `const int**` combine to `const int* const*`.

## Expressions don't have reference types (¶1)

```cpp ok
#include <type_traits>
int i = 0;
int& r = i;
int&& rr = 0;

static_assert(std::is_same_v<decltype(r), int&>);    // decltype(name): the declared type
static_assert(std::is_same_v<decltype((r)), int&>);  // decltype(expression): type int, lvalue → int&
static_assert(std::is_same_v<decltype((rr)), int&>); // the expression rr: type int, lvalue
static_assert(std::is_same_v<decltype((i)), int&>);  // the expression i: likewise int, lvalue
```

¶1 If an expression initially has the type "reference to `T`" ([[dcl.ref]], [[dcl.init.ref]]), the type is adjusted to `T` prior to any further analysis; the value category is unchanged.

So the expressions `r` and `i` both have type `int` and are both lvalues; at the expression level there is no difference between them. `decltype((r))` gives `int&` because [[dcl.type.decltype]] encodes an lvalue as `&`. Function calls and casts work the same way: for `int& f();`, `f()` is an lvalue of type `int`, and `static_cast<int&&>(x)` is an xvalue of type `int` ([[expr.call]], [[expr.static.cast]]).

### Evaluating a dangling reference is UB

The second half of ¶1 specifies the result of a reference expression. Let `X` be the object or function the reference denotes. If a pointer to `X` would be valid in the context of the evaluation ([[basic.compound#6]]: roughly, the storage of `X` hasn't ended yet), the result designates `X`; otherwise the behavior is undefined. Note 1 adds that using a reference before its lifetime begins or after it ends is undefined behavior ([[basic.life]]).

```cpp ub
int main() {
    int* p = new int(1);
    int& r = *p;
    delete p;
    int* q = &r;   // UB: the storage of the object r refers to has ended; evaluating r itself is UB
    (void)q;
}
```

Compare this with pointers. After `delete p`, `p` holds an invalid pointer value; indirection through it is UB, but other uses such as copying it are only implementation-defined ([[basic.compound#6]]). A reference has no such intermediate state: evaluating it at all is UB, even just to take its address. The C++23 wording only said the expression designates the object or function the reference denotes and didn't discuss this case; the current draft makes it explicitly UB.

## Non-class prvalues are not cv-qualified (¶2)

¶2 If a prvalue initially has the type cv `T`, where `T` is a cv-unqualified non-class, non-array type, the type of the expression is adjusted to `T`.

```cpp ok
#include <type_traits>
const int  f();
const int* g();
struct S {};
const S    h();

static_assert(std::is_same_v<decltype(f()), int>);         // top-level const removed
static_assert(std::is_same_v<decltype(g()), const int*>);  // const not at the top level is kept
static_assert(std::is_same_v<decltype(h()), const S>);     // class prvalues keep cv
static_assert(std::is_same_v<decltype(static_cast<const int>(1)), int>);
```

A non-class prvalue has no identity: a `const int` value and an `int` value are indistinguishable; it can neither be modified nor have member functions called on it, and keeping cv would only complicate type deduction and overload resolution. Class and array prvalues are materialized into objects and can have member functions called on them, so `const` has observable effects ([[basic.lval#9]]). Under `-Wextra`, Clang gives a `-Wignored-qualifiers` warning for `const int f();`, because the `const` has no effect.

## The composite pointer type (¶3)

```cpp ok
struct Base {};
struct Derived : Base {};

bool same(Base* b, Derived* d) { return b == d; }   // d is converted to Base* first
const void* pick(bool c, void* v, const int* p) {
    return c ? v : p;                               // both sides are converted to const void*
}
```

When both operands of `==`, `!=` ([[expr.eq]]), `<` and friends ([[expr.rel]]), `<=>` ([[expr.spaceship]]) or the conditional operator `?:` ([[expr.cond]]) are pointers, they first have to be converted to the same type. ¶3 defines that type, called the **composite pointer type** ([[g:composite-pointer-type]]). It is only used when at least one operand is a pointer, a pointer to member, or `std::nullptr_t`.

### The algorithm

Let the two operands `p1` and `p2` have types `T1` and `T2`. ¶3 tries the following items in order and uses the first that applies:

| Item | Condition | Composite pointer type |
|---|---|---|
| ¶3.1 | Both are null pointer constants | `std::nullptr_t` |
| ¶3.2 | One of them is a null pointer constant | The type of the other |
| ¶3.3 | One points to *cv1* `void`, the other to *cv2* `T` (`T` an object type or `void`) | Pointer to *cv12* `void`, where *cv12* is the union of the two |
| ¶3.4 | One points to a `noexcept` function, the other to a function, otherwise the same | Pointer to function (without `noexcept`) |
| ¶3.5 | They point to `C1` and `C2`, one of which is reference-related to the other | The qualification-combined type of the two, built on the base class side |
| ¶3.6 | Two pointers to member functions, one `noexcept` and one not, with reference-related classes | Pointer to member function without `noexcept`, with the derived class side as the class |
| ¶3.7 | Pointers to members of `C1` and `C2` of types *cv1* `U` and *cv2* `U`, with reference-related classes | The qualification-combined type of the two, built on the derived class side |
| ¶3.8 | `T1` and `T2` are similar | The qualification-combined type of `T1` and `T2` |
| ¶3.9 | Otherwise | A program that needs the composite pointer type is ill-formed |

The table uses three terms:

- **null pointer constant** ([[g:null-pointer-constant]]): an integer literal with value zero, or a prvalue of type `std::nullptr_t` ([[conv.ptr]]).
- **reference-related** ([[dcl.init.ref]]): `C1` is similar to `C2`, or one is a base class of the other.
- **Similar** ([[g:similar-types|similar]]) and **qualification-combined type** are both defined in [[conv.qual]]. Similar roughly means the two types are the same once cv at every level is removed and array bounds are ignored. The qualification-combined type takes the union of both sides' cv at each level, and if that changes some level, every level outside it (except the outermost) gets `const`.

Pointers (¶3.5) and pointers to members (¶3.7) go in opposite directions. `Base*` and `Derived*` combine to `Base*`, matching the direction of the implicit conversion from derived class pointer to base class pointer; `int Base::*` and `int Derived::*` combine to `int Derived::*`, matching the direction of the pointer-to-member conversion from base to derived ([[conv.mem]]).

### Examples

```cpp ok
#include <type_traits>
#include <utility>
#include <cstddef>
template<class A, class B>
using CPT = decltype(true ? std::declval<A>() : std::declval<B>());

struct Base {}; struct Derived : Base {};
void f(); void g() noexcept;

static_assert(std::is_same_v<CPT<std::nullptr_t, int*>, int*>);               // ¶3.2
static_assert(std::is_same_v<CPT<void*, const int*>, const void*>);           // ¶3.3
static_assert(std::is_same_v<CPT<decltype(&f), decltype(&g)>, void (*)()>);   // ¶3.4
static_assert(std::is_same_v<CPT<Base*, const Derived*>, const Base*>);       // ¶3.5
static_assert(std::is_same_v<CPT<int Base::*, int Derived::*>, int Derived::*>);  // ¶3.7
static_assert(std::is_same_v<CPT<int**, const int**>, const int* const*>);    // ¶3.8
static_assert(std::is_same_v<CPT<const int**, volatile int**>,
                             const volatile int* const*>);                    // ¶3.8
```

<div class="compare" markdown="1">

```cpp error
struct B {}; struct D : B {};
bool a(int* p, long* q) {
    return p == q;   // error: ¶3.9
}
bool b(B** p, D** q) {
    return p == q;   // error: ¶3.9
}
```

```cpp ok
struct B {}; struct D : B {};
bool a(int* p, const int* q) {
    return p == q;   // ¶3.8
}
bool b(B* const* p, B** q) {
    return p == q;   // ¶3.8
}
```

</div>

`int*` and `long*` are not similar, and `int` and `long` are not reference-related, so this falls through to ¶3.9. The same goes for `B**` and `D**`: ¶3.5 only looks one level deep, and the pointed-to types `B*` and `D*` are neither similar nor related as base and derived. This is also why `D**` can't be implicitly converted to `B**`; otherwise you could use it to write a pointer to some other `B` object into a `D*` slot.

### Why `int**` and `const int**` combine to `const int* const*`

Compare level by level. The innermost level is `int` versus `const int`; the union is `const int`, so this level changed. By the rule, the intermediate level outside it (the pointer being pointed to) has to get `const`. The outermost level doesn't take part. The result is `const int* const*`.

Without `const` at the intermediate level, the result would be `const int**`. But a conversion from `int**` to `const int**` breaks const-correctness: through it you could write a `const int*` into an `int*` slot, then modify that `const` object through the original `int**` ([[conv.qual]] gives the full counterexample). When the intermediate level is `const`, nobody can write into the intermediate level through a pointer of the combined type, so both sides can safely convert to it.

!!! lawyer "Array bounds and where Clang deviates"
    Since C++20, the qualification-combined type also handles arrays of known and unknown bound ([[P0388R4]]): if at some level one side is `[N]` and the other `[]`, they combine to `[]`, and the levels outside it get `const` in the same way. By the wording:

    - For `int(*)[3]` and `int(*)[]`, the change happens at level 1, there are no outer levels that need `const`, and they combine to `int(*)[]`.
    - For `int(**)[3]` and `int(**)[]`, the change happens at level 2, level 1 gets `const`, and they combine to `int(* const*)[]`.

    At the time of writing, Clang 23 gives `const int(*)[]` and `const int(* const*)[]` for these two, adding an extra `const` to the array elements. Both results let both sides convert safely, but Clang's results don't match the wording.

## History

!!! history
    - In C++98 the composite pointer type only handled object pointers, `void*` and null pointer constants, and was defined in the subclause on relational operators; it later moved to the general expression clause.
    - C++11 added `std::nullptr_t` (¶3.1, ¶3.2).
    - Since C++17, `noexcept` is part of the function type ([[P0012R1]]), so ¶3.4 and ¶3.6 were added.
    - C++20's qualification conversions support array bounds ([[P0388R4]]), so the composite pointer type can handle `T[N]` and `T[]` as well.
    - The new wording after C++23 added to ¶1 the rule that it is UB when what a reference refers to is no longer valid.

## Common misconceptions

!!! pitfall "`decltype(x)` is the same as `decltype((x))`"
    `decltype(r)` looks at the declared type of the name, `decltype((r))` at the type and value category of the expression. For a reference variable both happen to be `int&`, which hides the difference; for `int i;`, the former is `int` and the latter `int&`.

!!! pitfall "Any 0 in `?:` is a null pointer constant"
    The `0` in `c ? p : 0` is an integer literal, hence a null pointer constant, and per ¶3.2 the composite type is the type of `p`. After `int zero = 0;`, in `c ? p : zero`, `zero` is not a literal and not a null pointer constant, so it is ill-formed.

## Questions

!!! question "Question 1"
    Can `Base* const*` and `Derived**` be compared with `==`?

<details markdown="1">
<summary>Answer</summary>

No. ¶3.5 requires the pointed-to types `C1` and `C2` to be reference-related. Here `C1` is `Base* const` and `C2` is `Derived*`; they are neither similar nor related as base and derived. The two types themselves are not similar either, so ¶3.8 doesn't apply. That falls through to ¶3.9: ill-formed.
</details>

!!! question "Question 2"
    Given `const char* s; char* t; void* v;`, what is `t` converted to in `s == t`? And in `s == v`?

<details markdown="1">
<summary>Answer</summary>

`s == t`: `const char*` and `char*` are similar, and per ¶3.8 they combine to `const char*`. Only the innermost level changes, so no intermediate level needs `const`. `t` becomes `const char*` by a qualification conversion.

`s == v`: per ¶3.3 they combine to `const void*`. `s` becomes `const void*` by a pointer conversion, and `v` becomes `const void*` by a qualification conversion.
</details>
