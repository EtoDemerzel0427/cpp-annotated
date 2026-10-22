---
title: static_cast
summary: "What static_cast can do: anything that converts implicitly or can be direct-initialized, plus the inverse of most standard conversions (downcasts, void* to T*, integers to enumerations, etc.), and when each of these is undefined behavior."
updated: 2026-10-19
---

!!! tldr
    - Whatever converts implicitly, or can be direct-initialized as `T t(e);`, can be done with `static_cast<T>(e)`, including calling `explicit` constructors and narrowing conversions.
    - It can also do the inverse of most standard conversions: base class pointer to derived class pointer, `void*` to `T*`, integer to enumeration, pointer to member of derived to pointer to member of base. These reverse conversions do no checking at all; the wrong type is undefined behavior.
    - `std::move(x)` is just `static_cast<T&&>(x)`: it only changes the value category and moves nothing itself.
    - It can't cast away `const`, convert between unrelated pointer types, convert between pointers and integers, or downcast through a virtual base.
    - A `static_cast` through `void*` is exactly equivalent to `reinterpret_cast` and doesn't get around the strict aliasing rule.

## One keyword, two directions

```cpp run title="static-cast-overview.cpp" ok
struct Base { virtual ~Base() = default; };
struct Derived : Base { int extra = 42; };
enum class Color { red, green };

int main() {
  double d = 3.9;
  int i = static_cast<int>(d);              // truncates to 3
  int c = static_cast<int>(Color::green);   // 1
  Derived obj;
  Base* pb = &obj;                          // implicit upcast
  auto* pd = static_cast<Derived*>(pb);     // explicit downcast, unchecked
  return i == 3 && c == 1 && pd->extra == 42 ? 0 : 1;
}
```

The first two conversions go in the forward direction: `double` to `int` happens implicitly anyway, and writing `static_cast` just states the intent. The third goes in the reverse direction: derived pointer to base pointer is an implicit conversion, and `static_cast` allows reversing it, but doesn't check whether `*pb` really is a `Derived`.

The whole subclause is structured around these two directions. Paragraphs 2–5 handle the forward direction and a few special cases, matched in order; paragraph 6 says that otherwise only the reverse conversions listed in paragraphs 7–12 are allowed, and nothing else.

## Value category of the result (¶1)

¶1 The value category of the result is determined by `T` alone:

| `T` | Result |
|---|---|
| Lvalue reference, or rvalue reference to function | lvalue |
| Rvalue reference to object | xvalue |
| Non-reference type | prvalue |

This matches the rule for function calls ([[expr.call#15]]): a call to a function returning `T&&` is also an xvalue.

## If it can be initialized, it can be converted (¶5)

¶5 is the broadest rule. When ¶2–¶4 don't apply, an expression `E` can be converted to `T` if any of the following holds:

1. there is an implicit conversion sequence from `E` to `T` ([[over.best.ics]]);
2. overload resolution for direct-initializing an object or reference of type `T` from `E` finds at least one viable function ([[over.match.viable]]), so `explicit` constructors and `explicit` conversion functions count too;
3. {{c++20}} `T` is an aggregate type and there is an implicit conversion sequence from `E` to the type of its first element. This goes together with parenthesized aggregate initialization ([[P0960R3]]).

If `T` is a reference type, the effect is as if declaring `T t(E);` and then using `t`; otherwise the result object is direct-initialized from `E`.

```cpp run title="static-cast-init.cpp" ok
struct Ex { explicit Ex(int) {} };
struct Conv { explicit operator int() const { return 7; } };
struct Agg { int a; double b; };

int main() {
  double d = static_cast<double>(3);    // implicit conversion
  long l = static_cast<long>(3.9);      // floating to integer, truncated
  Ex e = static_cast<Ex>(1);            // explicit constructor
  int i = static_cast<int>(Conv{});     // explicit conversion function
  Agg g = static_cast<Agg>(1);          // C++20: initializes the first element a
  const int& cr = static_cast<const int&>(42);  // as if const int& t(42);
  (void)e;
  return d == 3.0 && l == 3 && i == 7 && g.a == 1 && cr == 42 ? 0 : 1;
}
```

Narrowing conversions are forbidden only in list-initialization ([[dcl.init.list]]). `static_cast<int>(3.9)` goes through direct-initialization, so it is allowed.

Note 3 reminds that converting an expression of class type to an inaccessible or ambiguous base class is ill-formed.

!!! lawyer "Clang and Note 4"
    Note 4 says that if `T` is an array of unknown bound `U[]`, this direct-initialization deduces the expression's type as `U[1]`. So `decltype(static_cast<int[]>(1))` should be `int[1]`. Clang 23 gives `int[]`, which is inconsistent with the standard.

## Discarding a value (¶4)

¶4 Any expression can be converted to `void`; the operand is then a **discarded-value expression** (an expression computed but whose value is not used, [[expr.context]]).

```cpp run title="cast-to-void.cpp" ok
[[nodiscard]] int compute() { return 42; }

int main() {
  static_cast<void>(compute());   // explicitly discarded, no nodiscard warning
  int unused = 0;
  (void)unused;                   // the C-style form, same effect
}
```

Note 1 says such a conversion has no result, since it is a prvalue of type `void`. Note 2 says that if the value is in a temporary object, that temporary is destroyed at the end of the full-expression as usual.

## What `std::move` really is (¶3)

¶3 An lvalue of type `T1` can be converted to `T2&&` if `T2` is **reference-compatible** with `T1` ([[dcl.init.ref]]), roughly meaning `T2` is `T1` itself or one of its base classes, with at least the cv-qualification of `T1`. The result refers to the object, or to its base class subobject. If `T2` is an inaccessible or ambiguous base class, it is ill-formed.

```cpp run title="lvalue-to-xvalue.cpp" ok
#include <string>

struct B {};
struct D : B {};
struct BF { int b : 3; };

int main() {
  std::string s = "hello";
  std::string t = static_cast<std::string&&>(s);  // same as std::move(s)
  D d;
  B&& br = static_cast<B&&>(d);      // refers to d's B subobject
  BF bf{1};
  int&& r = static_cast<int&&>(bf.b);  // bit-field: the value is read first, bound to a temporary
  (void)br;
  return t == "hello" && r == 1 ? 0 : 1;
}
```

`std::move(x)` is implemented as `static_cast<std::remove_reference_t<T>&&>(x)`. It turns an lvalue into an xvalue so overload resolution selects the move constructor or move assignment operator; the actual move happens inside that function.

A reference can't bind to a bit-field, so when the operand is a bit-field, its value is read first, and the resulting prvalue goes on through the rest of this subclause's rules, finally binding to a temporary.

## Conversions in the reverse direction (¶6)

¶6 When ¶2–¶5 don't apply, the lvalue-to-rvalue, array-to-pointer and function-to-pointer conversions are first applied to the operand, and then only the conversions listed in ¶7–¶12 are allowed. They are basically the inverses of some implicit conversion:

| Wording | Conversion | Corresponding forward direction |
|---|---|---|
| ¶7 | Scoped enumeration to integer, floating point | None; scoped enumerations deliberately don't convert implicitly |
| ¶8 | Integer, enumeration, floating point to enumeration | Unscoped enumeration to integer |
| ¶9 | Floating point to any other floating point | Floating-point conversion ([[conv.double]]) |
| ¶10 | Base class pointer to derived class pointer | Derived class pointer to base class pointer ([[conv.ptr]]) |
| ¶11 | Pointer to member of derived to pointer to member of base | Pointer to member of base to pointer to member of derived ([[conv.mem]]) |
| ¶12 | `void*` to `T*` | `T*` to `void*` ([[conv.ptr]]) |

¶2 handles reference downcasts, with the same rules as the pointer version in ¶10; the two are covered together below.

## Downcasts (¶2, ¶10)

¶10 A pointer to *cv1* `B` can be converted to a pointer to *cv2* `D`, where `D` is a complete class derived from `B` and *cv2* is at least *cv1*. A null pointer converts to a null pointer. If `*p` really is a base class subobject of some `D` object, the result points to that enclosing `D` object; otherwise the behavior is undefined.

¶2 is the reference version: an lvalue of *cv1* `B` can be converted to *cv2* `D&`, and an xvalue to *cv2* `D&&`, with the same restrictions and consequences as ¶10.

<div class="compare" markdown="1">

```cpp run ok
struct B {};
struct D : B { int extra = 42; };

int main() {
  D d;
  B& br = d;
  D& dr = static_cast<D&>(br);
  // OK: br really is a subobject of a D
  return dr.extra == 42 ? 0 : 1;
}
```

```cpp run ub
struct B {};
struct D : B { int extra = 42; };

int main() {
  B b;
  D& dr = static_cast<D&>(b);
  // UB: b is not a subobject of any D
  return dr.extra;
}
```

</div>

In our tests, AddressSanitizer reports stack-buffer-overflow for the program on the right: `dr.extra` reads the stack memory after `b`.

The following cases are errors at compile time:

```cpp title="ptr-downcast-rules.cpp" error
struct VB {};
struct VD : virtual VB {};
struct B {};
struct PD : private B {};
struct A {};
struct L : A {};
struct R : A {};
struct M : L, R {};

VD* f(VB* p) { return static_cast<VD*>(p); }  // error: through a virtual base
PD* g(B* p)  { return static_cast<PD*>(p); }  // error: private base
M*  h(A* p)  { return static_cast<M*>(p); }   // error: A is an ambiguous base of M
M*  k(L* p)  { return static_cast<M*>(p); }   // OK
```

`static_cast` can only add or subtract a fixed offset determined at compile time. The position of a virtual base subobject depends on the type of the whole object: when `VD` stands alone, its `VB` subobject is at one offset; when `VD` is a base of another class, `VB` may be elsewhere. The offset can't be computed at compile time, so it is forbidden. Use [[expr.dynamic.cast]] for this case.

| | `static_cast<D*>(pb)` | `dynamic_cast<D*>(pb)` |
|---|---|---|
| Check | None | Runtime check of the dynamic type |
| On the wrong type | Undefined behavior | Null pointer |
| Requires a polymorphic type | No | Yes |
| Through a virtual base | Ill-formed | Allowed |
| Cross-cast | Ill-formed | Allowed |
| Cost | Add or subtract a constant; with a nonzero offset, a null check first | A call into the runtime library |

The null check is necessary: a null pointer must still be null after conversion and can't have an offset subtracted. So with multiple inheritance, even `static_cast` is not zero-cost.

## Enumerations (¶7, ¶8)

¶7 A scoped enumeration can be converted to an integer type; the result is the same as converting first to the enumeration's underlying type and then to the target type. It can also be converted to a floating-point type; the result is the same as converting the original value directly to that floating-point type.

```cpp run title="scoped-enum-out.cpp" ok
enum class Color : unsigned char { red = 1, big = 200 };

int main() {
  int a = static_cast<int>(Color::big);          // 200
  auto b = static_cast<signed char>(Color::big); // 200 → -56
  double c = static_cast<double>(Color::red);    // 1.0
  return a == 200 && b == -56 && c == 1.0 ? 0 : 1;
}
```

The value of `b` is first 200 as an `unsigned char`, then converted to `signed char`. Since C++20, integral conversions are modulo 2<sup>8</sup> ([[conv.integral]]), so the result is a well-defined -56.

¶8 A value of integral or enumeration type can be converted to a complete enumeration type; the result depends on whether the enumeration has a **fixed underlying type**. Scoped enumerations always do; an unscoped enumeration does only if `: type` is written.

- With a fixed underlying type: the value first becomes the underlying type by integral promotion or integral conversion, then the enumeration. Every value of the underlying type is a valid enumeration value, so this is always defined.
- Without a fixed underlying type: if the original value is within the **range of enumeration values** ([[dcl.enum]]), it is unchanged; otherwise the behavior is undefined.

The range is the range of values of the smallest bit-field that can hold all the enumerators. `enum E { a, b, c };` has enumerators 0 to 2, needing 2 bits, so the range is 0 to 3:

```cpp title="enum-range.cpp" error
enum E { a, b, c };            // range [0, 3]
enum F : unsigned char { x };  // fixed underlying type

constexpr E e1 = static_cast<E>(3);    // OK: within the range
constexpr E e2 = static_cast<E>(4);    // error: UB, rejected in constant evaluation
constexpr F f1 = static_cast<F>(255);  // OK
constexpr F f2 = static_cast<F>(300);  // OK: first converted to unsigned char 44
```

Clang 23 reports integer value 4 is outside the valid range of values [0, 3]. There is no check at run time.

Why have a range at all: for an enumeration without a fixed underlying type, the compiler may assume its value is always within the range, store it in a narrower type, or omit the default branch when a `switch` covers the whole range. An enumeration with a fixed underlying type, on the other hand, is effectively an integer type with named constants, commonly used for strongly typed IDs or bit flags, and must be able to hold any value.

Finally, ¶8 also allows converting a floating-point value to an enumeration: the value is first converted to the underlying type ([[conv.fpint]], truncating toward zero, undefined behavior if out of range), then to the enumeration.

## Between floating-point types (¶9)

¶9 A floating-point prvalue can be converted to any other floating-point type:

- if the source value can be represented exactly in the target type, the result is that value;
- if the source value is between two adjacent values of the target type, the result is one of them, with the choice implementation-defined, usually following the current rounding mode;
- otherwise the behavior is undefined.

This paragraph became necessary after C++23. C++23 introduced extended floating-point types (`std::float16_t`, `std::bfloat16_t` etc., [[basic.extended.fp]]), and implicit conversions between them are only allowed when they don't lower the conversion rank ([[conv.double]]). `double` to `std::float16_t` can't happen implicitly; only `static_cast` can do it.

!!! lawyer "Out of range under IEEE 754"
    When the target type can represent infinity, `+inf` is one of its values, so `1e300` lies between the two adjacent values `FLT_MAX` and `+inf`, and by the second bullet this is an implementation-defined choice, not undefined behavior. Clang 23 accepts `constexpr float f = static_cast<float>(1e300);` in constant evaluation, with the result `+inf`. Only for floating-point formats without infinity does the third bullet really apply.

## Pointers to members (¶11)

¶11 A pointer to member of `D` of type *cv1* `T` can be converted to a pointer to member of `B` of type *cv2* `T`, where `B` is a base class of `D` and *cv2* is at least *cv1*. Note 5 reminds that function types have no cv-qualification, so the cv here only matters for data members.

The direction is the opposite of pointers. The implicit pointer-to-member conversion goes from base to derived ([[conv.mem]]): a member of `B` is also a member of `D`, so an `int B::*` is safe to use on any `D` object. `static_cast` allows reversing it, from `int D::*` to `int B::*`.

```cpp run title="pm-upcast.cpp" ok
struct B { int b = 1; };
struct D : B { int d = 2; };

int main() {
  int D::* pmd = &D::d;
  int B::* pmb = static_cast<int B::*>(pmd);
  D obj;
  B& br = obj;
  return br.*pmb == 2 ? 0 : 1;   // OK: br's dynamic type D has member d
}
```

If `B` contains the original member, or is a base of a class that contains it, the result points to the original member; otherwise the behavior is undefined. Note 6 adds that `B` itself doesn't need to have the member, but when the pointer to member is later used for access, the dynamic type of the object must have it ([[expr.mptr.oper]]). Above, if `br` referred to a plain `B` object, `br.*pmb` would be undefined behavior. MFC's message maps rely on this rule, storing derived-class member function pointers as base-class member function pointers.

## `void*` to `T*` (¶12)

¶12 A pointer to *cv1* `void` can be converted to a pointer to *cv2* `T`, where `T` is an object type and *cv2* is at least *cv1*. There are three cases for the result:

1. If the original pointer value is the address of a byte that doesn't satisfy `T`'s alignment requirement, the resulting pointer value is unspecified.
2. Otherwise, if the original pointer points to an object *a*, and there is an object *b* of type similar to `T` that is **pointer-interconvertible** with *a* ([[basic.compound]]), the result points to *b*.
3. Otherwise, the pointer value is unchanged.

Pointer-interconvertible means the two objects can be reached from each other through the same address: the same object, a union and its member, a standard-layout class object and its first non-static data member, for example.

```cpp run title="void-to-T.cpp" ok
struct S { int first; double second; };   // standard layout

int main() {
  S s{1, 2.0};
  void* vp = &s;
  int* pi = static_cast<int*>(vp);  // s and s.first are interconvertible: pi points to s.first
  *pi = 10;
  int x = 5;
  void* vx = &x;
  int* px = static_cast<int*>(vx);  // round trip: gives back the original pointer
  return s.first == 10 && px == &x ? 0 : 1;
}
```

Case 2 reflects the object model since C++17 ([[P0137R1]]): a pointer is not just an address; it also remembers which object it points to. Case 3 means that when there is no `T` object at the address to interconvert with, the result still points to the original object, merely with type `T*`. Accessing the object through it can then violate the [[basic.lval#11|strict aliasing rule]]:

```cpp run title="void-to-T-alias.cpp" ub
int main() {
  float f = 1.0f;
  void* vp = &f;
  int* pi = static_cast<int*>(vp);  // valid: the pointer value is unchanged, still points to f
  return *pi;                       // UB: reads a float object through an int lvalue
}
```

`reinterpret_cast<T*>(p)` between object pointers is defined precisely as these two `static_cast` steps ([[expr.reinterpret.cast#7]]). So going through `void*` is no safer than `reinterpret_cast`; the two are exactly equivalent. To reinterpret an object's bit pattern, use `std::bit_cast` or `std::memcpy` ([[topics/type-punning]]).

### `void*` to `T*` in constant evaluation {{c++26}}

C++26 ([[P2738R1]]) allows converting `void*` to `T*` during constant evaluation, provided the pointer really points to an object of a type similar to `T`. This lets `std::any`, type-erased function wrappers and the like work at compile time.

```cpp run title="constexpr-void-cast.cpp" ok
constexpr int f() {
  int x = 42;
  void* p = &x;
  return *static_cast<int*>(p);
}
static_assert(f() == 42);

int main() {}
```

Clang 23 rejects this example under `-std=c++23` and accepts it under `-std=c++2c`.

## What `static_cast` can't do

```cpp title="static-cast-no.cpp" error
struct A {};
struct B {};

void f(const int* cp, int* ip, A* pa, void (*fp)()) {
  static_cast<int*>(cp);    // error: casts away const, use const_cast
  static_cast<long*>(ip);   // error: unrelated pointer types
  static_cast<B*>(pa);      // error: no inheritance relationship
  static_cast<long>(ip);    // error: pointer to integer, use reinterpret_cast
  static_cast<void*>(fp);   // error: function pointer to void*
}
```

The last three need `reinterpret_cast` ([[expr.reinterpret.cast]]). Converting a function pointer to an object pointer is conditionally-supported; all mainstream platforms support it.

## History and evolution

!!! history
    - C++98: the four named casts were introduced, replacing most uses of C-style casts.
    - C++11: added the lvalue-to-rvalue-reference conversion of paragraph 3, for move semantics; added scoped enumerations and the conversions in paragraph 7.
    - C++17: [[P0137R1]] introduced pointer-interconvertibility and the model of pointers pointing to objects, and paragraph 12 was rewritten into its current form. Converting an out-of-range value to an enumeration without a fixed underlying type changed from an unspecified result to undefined behavior.
    - C++20: paragraph 5 gained the case of an aggregate's first element ([[P0960R3]]); signed integers use two's complement, so the results of integral conversions became well-defined.
    - C++23: extended floating-point types made the explicit floating-point conversion of paragraph 9 necessary.
    - C++26: `void*` to `T*` allowed in constant evaluation ([[P2738R1]]).

## Common misconceptions

!!! pitfall "A downcast to the wrong type will always cause some visible error"
    `static_cast<Derived*>(base_ptr)` doesn't fail when the type is wrong; it just gives a pointer with the wrong offset, and later access is undefined behavior. Where the type can't be guaranteed, use `dynamic_cast`, or check with `assert(dynamic_cast<D*>(p))` in debug builds.

!!! pitfall "Any integer can be static_cast to an enumeration"
    For an enumeration without a fixed underlying type, going out of range is undefined behavior. Before converting an integer read from the network or a file to an enumeration, either give the enumeration an underlying type or check the range first.

!!! pitfall "Going through void* makes type punning legal"
    `static_cast<int*>(static_cast<void*>(&f))` and `reinterpret_cast<int*>(&f)` are exactly equivalent, and reading `f` through either result violates the strict aliasing rule.

## Questions

!!! question "Question 1"
    Given `struct B {}; struct D : B {}; B b;`, is `D&& r = static_cast<D&&>(std::move(b));` well-formed? What is its behavior?

<details markdown="1">
<summary>Answer</summary>

It is well-formed. Paragraph 2 allows an xvalue of *cv1* `B` to be converted to *cv2* `D&&`, and here `D` is derived from `B` in a non-virtual, accessible and unambiguous way.

But `b` is not a base class subobject of any `D` object, so the behavior is undefined. Even if `r` is never used afterward, the conversion itself is already undefined behavior.
</details>

!!! question "Question 2"
    Given `enum class E : int { a }; float f = 3.9f;`, is `static_cast<E>(f)` valid? What is the result? What about `static_cast<E>(1e20f)`?

<details markdown="1">
<summary>Answer</summary>

It is valid (the last sentence of paragraph 8). 3.9f is first converted to the underlying type `int`, truncating toward zero to 3 ([[conv.fpint]]), then converted to `E`; the result is an `E` with value 3.

`1e20f` after truncation is outside the range of `int`, which [[conv.fpint]] says is undefined behavior.
</details>

!!! question "Question 3"
    Why is `static_cast<int B::*>(&D::d)` allowed but `int B::* p = &D::d;` not? Which direction is safe?

<details markdown="1">
<summary>Answer</summary>

The implicit pointer-to-member conversion is `int B::*` to `int D::*`: every member of `B` is a member of `D`, so it is safe to use on any `D` object. The reverse direction is not meaningful for every `B` object, since a plain `B` object has no member `d`, so it can only be done with an explicit `static_cast` (¶11), and the programmer guarantees that the object's dynamic type has the member when it is used.

This is exactly the opposite of object pointers: `D*` to `B*` is the safe implicit conversion, and `B*` to `D*` needs `static_cast`.
</details>

## Summary

!!! summary
    | Wording | Conversion | When it goes wrong |
    |---|---|---|
    | ¶2, ¶10 | Base reference or pointer to derived | Not really a subobject: UB; virtual base, inaccessible, ambiguous: ill-formed |
    | ¶3 | Lvalue to `T&&` (`std::move`) | Inaccessible or ambiguous base: ill-formed |
    | ¶4 | Any expression to `void` | Never |
    | ¶5 | Implicit conversion, explicit constructor or conversion function, aggregate's first element | By the initialization rules |
    | ¶7 | Scoped enumeration to integer, floating point | Never |
    | ¶8 | Integer, enumeration, floating point to enumeration | No fixed underlying type and out of range: UB |
    | ¶9 | Floating point to floating point | Between two values: implementation-defined; out of range: UB |
    | ¶11 | `T D::*` to `T B::*` | Doesn't contain the original member: UB |
    | ¶12 | `void*` to `T*` | Misaligned: unspecified value; no interconvertible object: pointer value unchanged |
