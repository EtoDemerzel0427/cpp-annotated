---
title: reinterpret_cast
summary: "The conversions reinterpret_cast can perform (pointers and integers, between function pointers, between object pointers, function and object pointers, between member pointers, references) and what each one really guarantees: the conversion is almost always valid, usually only the round trip is guaranteed, and accessing an object through the result often violates the strict aliasing rule."
updated: 2026-10-19
---

!!! tldr
    - `reinterpret_cast` changes the type without changing the value: it views a pointer as another kind of pointer, an integer or a reference, and generates almost no instructions.
    - The conversion itself is usually valid, but it guarantees very little, mainly one thing: converting there and back gives the original value.
    - `reinterpret_cast<T*>(p)` between object pointers is `static_cast<T*>(static_cast<void*>(p))`. When there is no interconvertible `T` object at the address, the result still points to the original object, and reading or writing through it usually violates the strict aliasing rule.
    - To reinterpret the bit pattern of a value, use `std::bit_cast` or `std::memcpy`, not `reinterpret_cast` plus a dereference.
    - `reinterpret_cast` can't cast away `const`, can't convert between arithmetic types, and can't appear in constant expressions.

## The conversion is valid; the use may not be

```cpp run title="strict-aliasing-opt.cpp" flags="-std=c++2c -O2" ub
int f(int* i, float* p) {
  *i = 1;
  *p = 2.0f;
  return *i;   // the compiler assumes *p and *i are not the same object
}

int main() {
  int x = 0;
  return f(&x, reinterpret_cast<float*>(&x));  // UB: writes an int object through a float lvalue
}
```

In our tests with Clang 23 at `-O2`, `f` is optimized to store 1, store 2.0f, and return the constant 1 directly; the program's exit code is 1. With `-fno-strict-aliasing`, `f` reads `*i` from memory again and the exit code becomes 0, i.e. the low 8 bits of 2.0f's bit pattern `0x40000000`.

The conversion `reinterpret_cast<float*>(&x)` itself is entirely valid. What goes wrong is writing an `int` object through a `float` lvalue afterward. So when discussing `reinterpret_cast`, keep two things apart:

1. Whether the conversion is valid. The rules are in this subclause, and it usually is.
2. Whether using the result is valid. The rules are elsewhere: accessing an object through the resulting pointer is governed by the [[basic.lval#11|strict aliasing rule]], calling through the resulting function pointer by [[expr.call#6]], and member access by [[expr.ref#10]].

## Which conversions are possible (¶1–¶3)

¶1 The value category of the result is the same as for [[expr.static.cast]]: an lvalue if `T` is an lvalue reference or rvalue reference to function, an xvalue if it is an rvalue reference to object, otherwise a prvalue, in which case the lvalue-to-rvalue, array-to-pointer and function-to-pointer conversions are applied to the operand first. The conversions that can be performed with `reinterpret_cast` are listed below; no others can be.

¶2 `reinterpret_cast` can't cast away `const` or `volatile` ([[expr.const.cast#6]]). An expression of integral, enumeration, pointer or pointer-to-member type can be converted to its own type, and the result is the value of the operand. That way generic code can write `reinterpret_cast` unconditionally even when the value may already have the target type.

¶3 is a note: the mapping performed by `reinterpret_cast` might, or might not, produce a representation different from the original value.

```cpp title="rc-basic.cpp" error
void t(int* ip, const int* cip) {
  int a = reinterpret_cast<int>(5);         // OK: to its own type
  int* q = reinterpret_cast<int*>(ip);      // OK: to its own type
  int* w = reinterpret_cast<int*>(cip);     // error: casts away const
  double d = reinterpret_cast<double>(1L);  // error: not between arithmetic types
  char c = reinterpret_cast<char>(ip);      // error: char can't hold a pointer
  (void)a; (void)q; (void)w; (void)d; (void)c;
}
```

`reinterpret_cast<double>(1L)` is ill-formed: `reinterpret_cast` can't reinterpret the bit pattern of an arithmetic value. Many people think it can, and write `*reinterpret_cast<double*>(&l)` instead, which is actually a valid pointer conversion plus an undefined access; see the section on type punning below.

## Pointers and integers (¶4, ¶5)

¶4 A pointer can be converted to any integral type large enough to hold all values of the pointer; the mapping is implementation-defined. Note 2 says the mapping is intended to be unsurprising to those who know the addressing structure of the underlying machine; on common platforms it is the address value.

A value of type `std::nullptr_t` can also be converted to an integer, with the same effect as converting `(void*)0` to that integer. Note 3 reminds that the reverse is not possible: no value can be converted to `std::nullptr_t` by `reinterpret_cast`.

```cpp run title="ptr-to-int.cpp" ok
#include <cstdint>

int main() {
  int x = 0;
  auto u = reinterpret_cast<std::uintptr_t>(&x);
  auto z = reinterpret_cast<std::uintptr_t>(nullptr);
  int* back = reinterpret_cast<int*>(u);   // an integer obtained from a pointer, converted back
  *back = 1;                               // OK: back points to x
  return x == 1 && z == 0 ? 0 : 1;   // z == 0 holds on common platforms, not guaranteed by the standard
}
```

`std::uintptr_t` and `std::intptr_t` are optional ([[cstdint.syn]]): an implementation provides them only if there is an integer type through which a `void*` can round-trip.

¶5 An integral or enumeration value can be converted to a pointer, in two cases:

1. If the integer value can result from converting one or more pointer values: the result is one of those pointers that gives the program defined behavior, and which one is unspecified. If there is none, the behavior is undefined.
2. Otherwise, e.g. if the integer is the address of a hardware register `0x40001000`, the result is implementation-defined. Note 5 says it may be an invalid pointer value.

Case 1 involves the **provenance** of pointers: a pointer is not just an address; it also remembers which object it points to. One integer may correspond to several pointers; for example, the past-the-end address of one object may equal the start address of the next object, and both convert to the same integer. The implementation must then pick one that doesn't lead to undefined behavior: if it is subsequently used to access the second object, it is the pointer to the second object. Note 4 reminds that even so, the result may be invalid, e.g. if the storage it points to has ended its duration. This is new wording after C++23.

!!! history "Safely-derived pointers"
    C++11 introduced safely-derived pointers to support optional garbage collection: only pointers obtained from `new` and then through traceable operations counted as safely derived. A pointer converted to an integer, manipulated and converted back could be invalid on implementations with strict pointer safety. No mainstream implementation ever adopted strict pointer safety, and C++23 removed all garbage collection support through [[P2186R2]], this concept included.

## Between object pointers (¶7)

!!! std
    When a prvalue v of object pointer type is converted to the object pointer type "pointer to cv T", the result is `static_cast<cv T*>(static_cast<cv void*>(v))`.

¶7 An object pointer can be converted to another object pointer type, and the result is that of converting to `void*` first and then to the target type with `static_cast`. So the result is entirely determined by [[expr.static.cast#12]]:

- if the address doesn't satisfy `T`'s alignment requirement, the resulting value is unspecified;
- if there is an object at the address of a type similar to `T` that is **pointer-interconvertible** (reachable from each other through the same address, [[basic.compound]]) with the original object, the result points to that object;
- otherwise the pointer value is unchanged: the result still points to the original object, only the type has changed.

```cpp run title="obj-ptr-cast.cpp" ok
struct S { int first; double second; };   // standard layout

int main() {
  S s{1, 2.0};
  int* pi = reinterpret_cast<int*>(&s);  // interconvertible with s.first: points to s.first
  *pi = 10;                              // OK
  S* back = reinterpret_cast<S*>(pi);    // points back to s
  return back == &s && s.first == 10 ? 0 : 1;
}
```

A standard-layout class object is pointer-interconvertible with its first non-static data member, so `pi` really points to `s.first`, and writing through it is fine.

Note 7 gives the resulting round-trip guarantee: a `T1*` pointing to a `T1` object, converted to `T2*` (where `T2`'s alignment requirement is no stricter than `T1`'s) and back to `T1*`, gives the original pointer value.

## Why type punning is undefined behavior

**Type punning** means reading or writing an object's storage as if it were another type. The typical way to do it with `reinterpret_cast` looks like this:

```cpp run title="punning-ub.cpp" ub
#include <cstdint>

float fast_abs(float f) {
  auto bits = *reinterpret_cast<std::uint32_t*>(&f);  // UB: reads a float object
  bits &= 0x7fffffffu;
  return *reinterpret_cast<float*>(&bits);            // UB: reads a uint32_t object
}

int main() { return fast_abs(-1.0f) == 1.0f ? 0 : 1; }
```

By paragraph 7, `reinterpret_cast<std::uint32_t*>(&f)` itself is valid: there is no interconvertible `uint32_t` object at the address, so the pointer value is unchanged and the result still points to the `float` object `f`. The problem is the read after the dereference.

[[basic.lval#11]] says that accessing an object of dynamic type `Tobj` through a glvalue of type `Tref` is allowed only if `Tref` is similar to one of: `Tobj` itself, the signed or unsigned type corresponding to `Tobj`, `char`, `unsigned char`, `std::byte`. Everything else is undefined behavior. This is the **strict aliasing rule**.

The rule enables type-based alias analysis: the compiler assumes lvalues of different types don't refer to the same object, so it can reorder and cache reads and writes; that is how the `f` at the top was optimized.

!!! impl "Compilers and strict aliasing"
    GCC and Clang enable `-fstrict-aliasing` by default at `-O2` and above; projects such as the Linux kernel compile with `-fno-strict-aliasing`. MSVC has historically not done type-based alias optimization, so punning code that runs fine on MSVC may break when ported to GCC or Clang.

There are four valid alternatives (see [[topics/type-punning]]):

- `std::bit_cast<To>(from)` (C++20, [[P0476R2]], [[bit.cast]]): copies the bits into a new object, usable in constant evaluation;
- `std::memcpy`: copies the bytes into an object of the target type; since C++20 it also implicitly creates objects ([[P0593R6]]);
- accessing byte by byte through `char`, `unsigned char` or `std::byte` lvalues, which the strict aliasing rule explicitly allows;
- `std::start_lifetime_as<T>(p)` (C++23, [[P2590R2]], [[obj.lifetime]]): starts the lifetime of a `T` object on existing bytes while keeping their contents, suitable for reading a network buffer as some struct.

```cpp run title="punning-ok.cpp" ok
#include <bit>
#include <cstdint>
#include <cstring>

constexpr float abs_bitcast(float f) {
  auto bits = std::bit_cast<std::uint32_t>(f) & 0x7fffffffu;
  return std::bit_cast<float>(bits);
}

float abs_memcpy(float f) {
  std::uint32_t bits;
  std::memcpy(&bits, &f, sizeof bits);
  bits &= 0x7fffffffu;
  std::memcpy(&f, &bits, sizeof f);
  return f;
}

static_assert(abs_bitcast(-2.5f) == 2.5f);   // works at compile time too

int main() {
  return abs_bitcast(-1.0f) == 1.0f && abs_memcpy(-1.0f) == 1.0f ? 0 : 1;
}
```

## Function pointers (¶6, ¶8)

¶6 A function pointer can be converted to another function pointer type, and the pointer value is unchanged. Note 6 reminds that calling a function through a function pointer whose type is not **call-compatible** (the same type, or differing only in `noexcept`) with the function's definition is undefined behavior ([[expr.call#6]]).

```cpp run title="fnptr-cast.cpp" ok
int add(int a, int b) { return a + b; }

int main() {
  using Generic = void (*)();
  auto g = reinterpret_cast<Generic>(&add);         // stored as a generic function pointer
  auto f = reinterpret_cast<int (*)(int, int)>(g);  // converted back to the original type
  return f(1, 2) == 3 ? 0 : 1;                      // OK: called with the original type
}
```

Changing it to `reinterpret_cast<int (*)(long, long)>(g)(1, 2)` makes the types not call-compatible, which is undefined behavior. C-style callback tables and dynamically loaded code commonly store function pointers of different types this way: store as `void (*)()`, convert back to the original type when used.

¶8 Converting between function pointers and object pointers is **conditionally-supported** (an implementation need not support it, but must diagnose it if it doesn't), with implementation-defined meaning. If an implementation supports conversion in both directions, the round trip must give the original value.

```cpp run title="fn-obj-ptr.cpp" impl
void fn() {}

int main() {
  void* vp = reinterpret_cast<void*>(&fn);       // conditionally-supported
  auto back = reinterpret_cast<void (*)()>(vp);  // the round trip gives the original value
  back();
  return back == &fn ? 0 : 1;
}
```

It is conditionally-supported because on some architectures code and data live in different address spaces, and even the pointer widths may differ. POSIX requires support for this conversion, because `dlsym` returns `void*` but is often used to get functions. GCC, Clang and MSVC all support it; Clang 23 doesn't warn about it even under `-pedantic`.

## Null pointers (¶9)

¶9 A null pointer value is converted to the null pointer value of the target type. Note 8 adds two points:

- a null pointer constant of type `std::nullptr_t` can't be converted to a pointer by `reinterpret_cast`; use `static_cast` or an implicit conversion;
- an integral null pointer constant `0` doesn't necessarily give a null pointer value. `reinterpret_cast<int*>(0)` goes through paragraph 5's integer-to-pointer mapping, not the null pointer conversion of [[conv.ptr]]. On platforms where the null pointer is not represented as all zeros, the two give different results.

```cpp title="rc-null.cpp" error
void t() {
  int* a = reinterpret_cast<int*>(nullptr);  // error: nullptr_t to a pointer
  int* b = reinterpret_cast<int*>(0);  // OK: the ¶5 mapping, not guaranteed to be null
  int* c = static_cast<int*>(0);       // OK: guaranteed to be null
  (void)a; (void)b; (void)c;
}
```

## Pointers to members (¶10)

¶10 As long as `T1` and `T2` are both function types or both object types, a pointer to member of `X` of type `T1` can be converted to a pointer to member of `Y` of type `T2`, and `X` and `Y` can be completely unrelated. A null member pointer converts to a null member pointer. Except for the following two round trips, the result is unspecified:

- ¶10.1 a pointer to member function converted to another pointer-to-member-function type and back gives the original value;
- ¶10.2 a pointer to data member converted to another pointer-to-data-member type (where `T2`'s alignment requirement is no stricter than `T1`'s) and back gives the original value.

## References (¶11)

¶11 Let a glvalue `v` of type `T1` designate an object or function *x*. As long as `T1*` can be converted to `T2*` by `reinterpret_cast`, `v` can be converted to `T2&`, and the result is `*reinterpret_cast<T2*>(p)`, where `p` is a `T1*` pointing to *x*. Note 9 stresses that no temporary is created, no copy is made, and no constructors or conversion functions are called.

```cpp title="rc-ref.cpp" error
void t() {
  int i = 0;
  float& fr = reinterpret_cast<float&>(i);  // OK: the conversion is valid, reading or writing through fr is UB
  long&& lr = reinterpret_cast<long&&>(i);  // OK: the result is an xvalue
  int&& rr = reinterpret_cast<int&&>(5);    // error: the operand must be a glvalue
  (void)fr; (void)lr; (void)rr;
}
```

This is exactly the difference from `static_cast`: `static_cast<float>(i)` creates a new `float` value, turning 3 into 3.0f; `reinterpret_cast<float&>(i)` just looks at the same memory with a different type. Footnote 49 says that when the result refers to the same object as the source glvalue, this is sometimes called type punning.

## Not usable in constant expressions

A `reinterpret_cast` expression is not a core constant expression ([[expr.const.core]]). The constant evaluator can't give meaningful semantics to a reinterpreted pointer, and compile-time computation thus never involves implementation-defined mappings. When you need to reinterpret a bit pattern at compile time, use `std::bit_cast`.

```cpp title="rc-constexpr.cpp" error
constexpr int g() {
  int x = 1;
  return *reinterpret_cast<unsigned*>(&x);  // the access itself is allowed
}
static_assert(g() == 1);   // error: reinterpret_cast can't appear in constant evaluation
```

## History and evolution

!!! history
    - C++98: `reinterpret_cast` was introduced. The result of converting between object pointers was unspecified, with only the round trip guaranteed.
    - C++11: the result in paragraph 7 was redefined via `static_cast` through `void*`, but at the time only when both sides were standard-layout types; later revisions extended it to all object pointers. Converting between function pointers and object pointers changed from not allowed to conditionally-supported. Safely-derived pointers were introduced.
    - C++17: adopted the object model of [[P0137R1]] (pointer-interconvertibility, `std::launder`), and the result in paragraph 7 is now described in terms of which object the pointer points to.
    - C++20: `std::bit_cast` ([[P0476R2]]) provides valid reinterpretation of bit patterns; implicit object creation was introduced ([[P0593R6]]).
    - C++23: garbage collection support and safely-derived pointers removed ([[P2186R2]]); `std::start_lifetime_as` added ([[P2590R2]]).
    - After C++23: paragraph 5 rewritten in terms of provenance.

## Common misconceptions

!!! pitfall "If it compiles and runs at -O0, the punning is fine"
    Except for `char`, `unsigned char`, `std::byte` and the corresponding signed/unsigned type, reading or writing the original object through a pointer obtained by `reinterpret_cast` violates the strict aliasing rule. The example at the top gives the expected result at `-O0` and changes at `-O2`.

!!! pitfall "reinterpret_cast a byte buffer to a struct"
    `auto* hdr = reinterpret_cast<Header*>(buf);` was almost always undefined behavior before C++20, because there was no `Header` object there. Since C++20, if `buf` comes from an operation that implicitly creates objects, such as `std::malloc` or `new unsigned char[]`, and `Header` is an implicit-lifetime type, the object may already have been implicitly created; but if the buffer is already occupied by objects of other types, things get much more complicated. The clearest forms are `std::start_lifetime_as<Header>(buf)` (C++23), or `memcpy` into a local `Header`. Mind the alignment too: by paragraph 7, a misaligned address gives an unspecified value.

!!! pitfall "reinterpret_cast to a base class pointer"
    With multiple inheritance, the second and later base class subobjects are not at the same address as the derived object. `reinterpret_cast` doesn't know about inheritance and doesn't adjust the offset, so the result still points to the derived object; accessing base class members afterward is undefined behavior (Example 2 of [[expr.ref#10]] is exactly this case). Clang 23 warns about this with `-Wreinterpret-base-class`.

## Questions

!!! question "Question 1"
    ```cpp
    int a[2] = {1, 2};
    auto n = reinterpret_cast<std::uintptr_t>(&a[0]) + sizeof(int);
    int* p = reinterpret_cast<int*>(n);
    ```
    Is `*p` defined?

<details markdown="1">
<summary>Answer</summary>

On implementations where the mapping is the address value, `n` happens to equal the integer obtained from `&a[1]`, so it is a value that can result from converting a pointer value. By paragraph 5, among the candidates, the pointer to `a[1]` gives `*p` defined behavior, so the result points to `a[1]` and `*p == 2`.

However, this depends on the implementation-defined mapping (¶4) happening to be linear; the standard itself doesn't guarantee that integer addition corresponds to pointer arithmetic. The portable form is `&a[0] + 1`.
</details>

!!! question "Question 2"
    Is `unsigned u = 1; int& r = reinterpret_cast<int&>(u); r = -1;` undefined behavior? What is the value of `u`?

<details markdown="1">
<summary>Answer</summary>

No. The conversion itself is valid (¶11); `int` is the signed type corresponding to `unsigned int`, so by [[basic.lval#11.2]] `u` can be accessed through an `int` glvalue.

After writing `-1`, `u` has the value `UINT_MAX`, because the two's complement representation of `-1` is all ones. This is one of the few valid forms of punning with `reinterpret_cast`.
</details>

!!! question "Question 3"
    When `x` is a `long`, why is `reinterpret_cast<double>(x)` ill-formed while `reinterpret_cast<long>(x)` is well-formed?

<details markdown="1">
<summary>Answer</summary>

¶1 says only the conversions listed below can be performed. ¶2 allows an integral type to be converted to its own type, so `long` to `long` is fine; the list contains no conversion from one arithmetic type to another, so `long` to `double` is ill-formed. Reinterpreting the bit pattern of an arithmetic value is `std::bit_cast`'s job.
</details>

## Summary

!!! summary
    | Wording | Conversion | Guarantee |
    |---|---|---|
    | ¶2 | Integer, enumeration, pointer, member pointer to its own type | Value unchanged |
    | ¶4 | Pointer to a wide enough integer; `nullptr_t` to integer | Implementation-defined mapping |
    | ¶5 | Integer, enumeration to pointer | From a pointer: a candidate giving defined behavior is chosen, UB if none; otherwise implementation-defined |
    | ¶6 | Function pointer to function pointer | Value unchanged; calling through an incompatible type is UB |
    | ¶7 | Object pointer to object pointer | Two `static_cast`s through `void*`; round trip preserved when alignment allows |
    | ¶8 | Between function pointers and object pointers | Conditionally-supported; round trip preserved when both directions are supported |
    | ¶9 | Null pointer value | Gives the null pointer value; `nullptr_t` can't convert to a pointer; integer `0` not guaranteed to give null |
    | ¶10 | Member pointer to member pointer | Only the round trip is guaranteed |
    | ¶11 | glvalue to reference | Equals `*reinterpret_cast<T2*>(&x)`; no temporary created |
