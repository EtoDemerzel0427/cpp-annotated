---
title: An overview of casts
summary: What implicit conversions, the four named casts, C-style and functional casts, and std::bit_cast each do, which one to pick for a given job, which kinds of type punning are legal, and the most common cast-related UB.
tags: casts, strict aliasing, type punning, UB
updated: 2026-10-19
---

!!! tldr
    - Conversions come in two kinds: value conversions compute a new value (`3` becomes `3.0`); reinterpretations only look at the same storage or the same bits through a different type.
    - The `reinterpret_cast` conversion itself is almost always valid. The trouble comes from reading or writing an object through the result, which often violates the strict aliasing rule.
    - To look at the bit pattern of a `float`, use `std::bit_cast` or `std::memcpy`; byte-wise access through `unsigned char` or `std::byte` is also valid. Union type punning is UB in C++.
    - For a downcast, use `static_cast` when you know the type is right, and `dynamic_cast` when you don't.
    - A C-style cast `(T)e` picks a different named cast depending on context, so the meaning of the same line can change depending on whether a type is complete.

## UB that produces the right result

<div class="compare" markdown="1">

```cpp run ub
#include <cstdint>
#include <cstdio>
int main() {
  float f = 1.0f;
  auto u = *reinterpret_cast<
      std::uint32_t*>(&f);  // UB
  std::printf("%x\n", u);
}
```

```cpp run ok
#include <bit>
#include <cstdint>
#include <cstdio>
int main() {
  float f = 1.0f;
  auto u = std::bit_cast<
      std::uint32_t>(f);    // OK
  std::printf("%x\n", u);
}
```

</div>

Both snippets print `3f800000` in our tests. The cast on the left is fine in itself; the problem is the dereference, which reads a `float` object through an lvalue of type `uint32_t`. Under the strict aliasing rule ([[basic.lval#11]]), an object may only be accessed through a type similar to its own, the corresponding signed or unsigned type, or `char`, `unsigned char` or `std::byte`; anything else is UB. Compilers' alias analysis relies on this rule, and after optimization the code on the left may read a stale value.

`std::bit_cast` on the right creates a new `uint32_t` object and copies the bits of `f`; no aliasing is involved.

This example shows the two kinds of risk in conversions. Below, conversions are first classified, then the capabilities of each are listed, and finally type punning and common UB are covered.

## Two kinds of conversion

| Kind | What it does | Examples |
|---|---|---|
| Value conversion | Computes a new value of a different type with the same meaning, e.g. `3` becomes `3.0`, `Derived*` becomes a `Base*` with an adjusted address | Implicit conversions, `static_cast`, `dynamic_cast`, functional casts |
| Reinterpretation | Doesn't change the address or the bit pattern; only views it through a different type | `reinterpret_cast`, `const_cast` (changes only cv-qualification), `std::bit_cast` (copies the bit pattern into a new object) |

The risk of value conversions is trust. When `static_cast` does a downcast, it trusts that the type the programmer gave is right; if not, it's UB.

The risk of reinterpretations is access. The pointer or reference the cast produces is usually valid, but reading or writing an object through it may violate the strict aliasing rule.

## What each conversion can do

| Conversion | Clause | Capabilities | Checking | Constant evaluation |
|---|---|---|---|---|
| Implicit conversion | [[conv]], [[over.best.ics]] | A standard conversion sequence plus at most one user-defined conversion | Compile time; only list-initialization forbids narrowing | Yes |
| `static_cast` | [[expr.static.cast]] | Implicit conversions and their inverses, explicit constructors and conversion functions, downcasts, `void*` to `T*`, enumerations | Compile time; downcasts don't check the dynamic type | Yes (`void*` to `T*` since C++26) |
| `dynamic_cast` | [[expr.dynamic.cast]] | Downcasts and cross-casts of polymorphic types, getting the address of the most derived object | Run time; failure gives a null pointer or throws `bad_cast` | Yes (since C++20) |
| `const_cast` | [[expr.const.cast]] | Changes only cv-qualification | Compile time | Yes, but it can't be used to modify a const object |
| `reinterpret_cast` | [[expr.reinterpret.cast]] | Pointer ↔ integer, between unrelated pointer types, between function pointer types, reinterpreting references | None | No |
| `(T)e` | [[expr.cast]] | Tries `const_cast`, `static_cast`, `reinterpret_cast` and their combinations in order; can ignore private inheritance | Depends on the one chosen | Depends on the one chosen |
| `T(e)` | [[expr.type.conv]] | Same as `(T)e` with a single argument; direct-initialization with several arguments | Same as above | Same as above |
| `T{e}` | [[expr.type.conv]], [[dcl.init.list]] | Direct-list-initialization | Forbids narrowing | Yes |
| `auto(e)` | [[expr.type.conv]] | Makes a prvalue copy (C++23, [[P0849R8]]) | Compile time | Yes |
| `std::bit_cast<T>(e)` | [[bit.cast]] | Copies the object representation into a new `T` object (C++20, [[P0476R2]]) | Equal sizes, both trivially copyable | Yes, but the types must not contain pointers, references or unions |

Two more tools don't change the type of an expression but deal with the identity of objects: `std::launder` ([[ptr.launder]]) and `std::start_lifetime_as` ([[obj.lifetime]]). The latter is introduced in the type punning section below.

## Which one to use for a given job

| What you want to do | Use | Don't use |
|---|---|---|
| Convert between numeric types, truncation allowed | `static_cast<T>(x)` | `(T)x`, `T(x)`: unclear intent |
| Numeric conversion, but no loss of information allowed | `T{x}` | |
| Scoped enumeration ↔ integer | `static_cast`, or C++23's `std::to_underlying(e)` | `reinterpret_cast`: ill-formed |
| Integer to an enumeration without a fixed underlying type | Check the range first, then `static_cast` | Converting directly: out of range is UB |
| Derived-class pointer to base-class pointer | Implicit conversion | `reinterpret_cast`: doesn't adjust the address |
| Base to derived, type known to be right | `static_cast` | C-style cast: see below |
| Base to derived, type not known | `dynamic_cast` (requires a polymorphic type) | `static_cast`: UB if wrong |
| Downcast through a virtual base, or cross-cast | `dynamic_cast` | `static_cast`: ill-formed |
| Address of the complete object of a polymorphic object | `dynamic_cast<void*>(p)` | `static_cast<void*>(p)`: only the subobject's address |
| Call an old interface that isn't const-correct | `const_cast`, and make sure nothing writes | C-style cast |
| Mark an lvalue as movable | `std::move(x)`, i.e. `static_cast<T&&>(x)` | |
| Perfect forwarding | `std::forward<T>(x)` | Hand-written `static_cast<T&&>`: easy to get wrong |
| Get a prvalue copy | `auto(x)` (C++23) | |
| Discard a value, e.g. to silence a `[[nodiscard]]` warning | `static_cast<void>(x)` or `(void)x` | |
| Pointer to integer (hashing, checking alignment) | `reinterpret_cast<std::uintptr_t>(p)` | `static_cast`: ill-formed |
| Integer to pointer (memory-mapped hardware address) | `reinterpret_cast<T*>(addr)`; the result is implementation-defined | |
| Store function pointers of different types | `reinterpret_cast<void(*)()>(f)`, cast back to the original type before calling | Calling through the wrong type: UB |
| Look at the raw bytes of an object | `reinterpret_cast<const unsigned char*>(&obj)` or `std::as_bytes` | Reading through `uint32_t*`: UB |
| Get the bit pattern of a `float` | `std::bit_cast<std::uint32_t>(f)` | Reading through `uint32_t*`, union punning: UB |
| Use a byte buffer as a struct | `std::start_lifetime_as<T>(buf)` (C++23), or `memcpy` into a local object | Accessing directly after `reinterpret_cast<T*>(buf)` |

### The meaning of a C-style cast can change

`(T)e` tries several named casts in turn and takes the first one that is valid ([[expr.cast#4]]). Which one the same line picks depends on the declarations visible at that point:

```cpp run unspecified
#include <cstdio>
struct A { int a; };
struct B { int b; };
struct C;                          // only a forward declaration here
B* early(C* c) { return (B*)c; }   // Clang interprets it as reinterpret_cast
struct C : A, B {};
B* late(C* c) { return (B*)c; }    // interpreted as static_cast
int main() {
  C c;
  std::printf("%d\n", early(&c) == late(&c));   // 0
}
```

When `C` is complete, `(B*)c` is interpreted as `static_cast`, and the address is offset by the `B` subobject. When `C` is incomplete, the standard says it is unspecified whether the `static_cast` or the `reinterpret_cast` interpretation is used ([[expr.cast#5]]): a multi-pass compiler could see the later definition. Clang works in a single pass and at that point doesn't know `B` is a base of `C`, so it can only interpret it as `reinterpret_cast`, leaving the address unchanged.

In our tests it prints `0`, with no warning at compile time. Written as `static_cast<B*>(c)`, the incomplete case is simply a compile error.

## Type punning: which forms are legal

[[g:type-punning|Type punning]] means reading the storage of an object as another type. In C++ only the following ways are legal.

### std::bit_cast

```cpp run title="pun-bitcast.cpp" ok
#include <bit>
#include <cstdint>

constexpr std::uint32_t float_bits(float f) { return std::bit_cast<std::uint32_t>(f); }
static_assert(float_bits(1.0f) == 0x3f800000u);   // usable at compile time

int main() { return float_bits(-0.0f) == 0x80000000u ? 0 : 1; }
```

`bit_cast` requires the two types to have the same size and both to be trivially copyable. It creates a new object, so there is no aliasing issue. During constant evaluation, the types also must not contain pointers, references, unions or volatile members.

### std::memcpy

```cpp run title="pun-memcpy.cpp" ok
#include <cstdint>
#include <cstring>

std::uint32_t float_bits(float f) {
  std::uint32_t u;
  std::memcpy(&u, &f, sizeof u);   // copy the object representation
  return u;
}

int main() { return float_bits(1.0f) == 0x3f800000u ? 0 : 1; }
```

Before C++20 this was the only portable way. Modern compilers optimize this `memcpy` into a single register move with no extra cost.

### Access through char, unsigned char, std::byte

The strict aliasing rule explicitly allows any object to be accessed through these three types ([[basic.lval#11]] ¶11.3); `memcpy`, serialization and hash functions all depend on this. The exemption is one-way: reading a `float` through `unsigned char*` is valid, but reading an `unsigned char` array through `float*` is not, because there is no `float` object there.

### The corresponding signed and unsigned types

An `int` object may be accessed through an lvalue of type `unsigned int`, and vice versa (¶11.2).

### std::start_lifetime_as (C++23)

```cpp title="pun-start-lifetime.cpp"
#include <cstdint>
#include <memory>
#include <cstddef>

struct Header { std::uint16_t type; std::uint16_t len; };

void parse(std::byte* buf) {   // buf comes from the network; contents ready, aligned for Header
  Header* h = std::start_lifetime_as<Header>(buf);   // starts a Header's lifetime in place, keeping the bytes
  // use h->type, h->len ...
}
```

`start_lifetime_as` ([[P2590R2]], [[obj.lifetime]]) implicitly creates an object of an [[g:implicit-lifetime-type]] in existing storage, preserving the existing byte values. Reading a network buffer as a struct used to be possible only through UB or `memcpy`; this function provides a legal way. libc++ in our tests does not provide it yet, so this example has not been compiled.

### Illegal forms

| Form | Why it is UB |
|---|---|
| `*reinterpret_cast<std::uint32_t*>(&f)` | Accesses a `float` object through a `uint32_t` lvalue, violating [[basic.lval#11]] |
| `*static_cast<std::uint32_t*>(static_cast<void*>(&f))` | Exactly equivalent to the previous line ([[expr.reinterpret.cast#7]]) |
| Union punning: write `x.f`, then read `x.u` | `x.u` is not the active member and is not within its lifetime ([[class.union]]). C allows this, C++ does not; GCC guarantees its behavior as an extension |
| `reinterpret_cast<Header*>(buf)->len` where `buf` is a plain byte array | There is no `Header` object there |

```cpp run title="pun-union.cpp" ub
#include <cstdint>

int main() {
  union { float f; std::uint32_t u; } x;
  x.f = 1.0f;
  return x.u == 0x3f800000u ? 0 : 1;   // UB: u is not the active member (legal type punning in C)
}
```

## Common cast-related UB

| UB | Rule | How to avoid it |
|---|---|---|
| `static_cast` downcast to the wrong derived class | [[expr.static.cast#2]], [[expr.static.cast#10]] | Use `dynamic_cast`, or avoid it by design |
| Integer converted to an enumeration without a fixed underlying type, out of range | [[expr.static.cast#8]] | Give the enumeration an underlying type |
| Floating point converted to integer out of range, e.g. `(int)1e10` | [[conv.fpint]] | Check the range first |
| Modifying a const object through `const_cast` | [[dcl.type.cv]] | Only remove const from objects that weren't const to begin with |
| Reading or writing an object of an incompatible type through a pointer from `reinterpret_cast` | [[basic.lval#11]] | `bit_cast` or `memcpy` |
| Accessing a class member through a pointer from `reinterpret_cast` when the object type isn't similar | [[expr.ref#10]] | Use `static_cast` for base-class conversions |
| Calling a function through an incompatible function type | [[expr.call#6]] | Cast back to the original type before calling |
| `dynamic_cast` on an object whose lifetime has ended | [[expr.dynamic.cast#7]] | Manage lifetimes properly |
| Converting `void*` to `T*` with a misaligned address, then dereferencing | [[expr.static.cast#12]], [[basic.align]] | Check alignment, or use `memcpy` |

## Compilers and tools

!!! impl
    - Warnings: `-Wold-style-cast` (C-style casts), `-Wcast-qual` (removing cv-qualification), `-Wcast-align` (increased alignment requirement), Clang's `-Wreinterpret-base-class` (`reinterpret_cast` to a base class at a non-zero offset), GCC's `-Wstrict-aliasing`.
    - Run-time checks: UBSan's `-fsanitize=vptr` checks member accesses and downcasts with the wrong dynamic type (requires RTTI); `-fsanitize=function` checks calls through a function pointer of the wrong type; `-fsanitize=float-cast-overflow` checks floating-to-integer overflow; `-fsanitize=enum` checks loads of invalid enumeration values.
    - `-fno-strict-aliasing` turns off type-based alias analysis, so code that violates the strict aliasing rule runs the way the programmer expected. It doesn't change the UB at the level of the standard, and it isn't portable to other compilers.
    - Under `-fno-rtti`, `typeid` and most `dynamic_cast`s are unavailable; upcasts and, in Clang, `dynamic_cast<void*>` still work.

```cpp run title="ubsan-vptr.cpp" flags="-std=c++2c -fsanitize=vptr,undefined" ub
struct B { virtual ~B() = default; };
struct D1 : B { int x = 1; };
struct D2 : B { int y = 2; };

int main() {
  D2 d2;
  B* b = &d2;
  D1* p = static_cast<D1*>(b);   // UB: b actually points to a D2
  return p->x;
}
```

At run time UBSan reports `downcast of address … which does not point to an object of type 'D1'`.

## Evolution

!!! history
    - C and early C++ had only `(T)e`. The functional notation `T(e)` was added so that construction looks the same for built-in and class types.
    - C++98 added the four named casts, and the C-style cast was redefined as a combination of them; RTTI (`dynamic_cast`, `typeid`) was added at the same time.
    - C++11 added list-initialization with narrowing checks, as well as rvalue references and `std::move` and `std::forward`, which are essentially `static_cast`s.
    - C++17 rewrote the object model, introducing the notion of pointer-interconvertible objects and `std::launder`.
    - C++20 added `std::bit_cast` ([[P0476R2]]) and implicit object creation ([[P0593R6]]); `dynamic_cast` and `typeid` became usable in constant evaluation.
    - C++23 added `auto(x)` ([[P0849R8]]), `std::start_lifetime_as` ([[P2590R2]]) and `std::to_underlying`.
    - C++26 allows converting `void*` to `T*` during constant evaluation.
