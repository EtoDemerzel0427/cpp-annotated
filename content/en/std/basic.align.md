---
title: Alignment
summary: "Alignment is a divisibility requirement that object addresses must satisfy; alignments up to max_align_t are fundamental, larger ones are extended; creating an object in insufficiently aligned storage is undefined behavior."
updated: 2026-10-19
---

!!! tldr
    - The alignment of a type `T` is `alignof(T)`, and the address of a `T` object must be a multiple of it. Alignment values are always powers of 2.
    - Creating an object in storage that does not meet its alignment requirement is undefined behavior, whether by a definition, placement new or implicit creation.
    - An alignment no greater than `alignof(std::max_align_t)` is a fundamental alignment and is supported everywhere; a greater one is an extended alignment, and a type with an extended alignment is an over-aligned type.
    - Beyond `__STDCPP_DEFAULT_NEW_ALIGNMENT__`, since C++17 `new` calls allocation functions taking `std::align_val_t`. This threshold is not necessarily the same as the alignment of `max_align_t`.
    - For a byte array used as raw storage, write `alignas(T) std::byte buf[sizeof(T)];`; don't use the deprecated `std::aligned_storage`.

## Alignment requirements (¶1)

```cpp run title="misaligned.cpp" ub
#include <new>

int main() {
    alignas(int) unsigned char buf[sizeof(int) + 1];
    int* p = ::new (buf + 1) int(42);   // UB: buf + 1 does not satisfy int's alignment (when alignof(int) > 1)
    return *p;
}
```

On x86-64 and Apple Silicon, this code usually runs fine and returns 42. But per the standard, `buf + 1` is not a multiple of `alignof(int)`, and creating an `int` object there is undefined behavior.

¶1 Every object type has an **alignment requirement** that restricts the addresses at which objects of that type may be placed ([[basic.fundamental]], [[basic.compound]]). An **alignment** is an implementation-defined integer value representing the number of bytes between successive addresses at which a given object can be allocated. Saying `alignof(int)` is 4 means the address of an `int` object must be a multiple of 4.

The alignment specifier `alignas` can request a stricter alignment ([[dcl.align]]), but not a weaker one.

!!! std
    Attempting to create an object in storage that does not meet the alignment requirements of the object's type is undefined behavior.

This UB constrains the act of creating an object, including definitions, placement new and implicit object creation ([[intro.object#13]]). Merely `reinterpret_cast`ing an unaligned address to `int*` is not covered (the result of the conversion is specified by [[expr.reinterpret.cast]]). Implicit object creation only creates objects that give the program defined behavior; if a later access needs an unaligned object, no such choice exists, and the program's behavior is undefined.

!!! note "UBSan can catch it"
    Compiling the program above with `-fsanitize=alignment` (included in `-fsanitize=undefined`), Clang 23 reports `load of misaligned address` when `*p` is read. x86 hardware tolerates unaligned access to ordinary scalars, so such errors often surface only with certain ARM instructions or after vectorization.

## Fundamental alignment (¶2)

¶2 A **fundamental alignment** is an alignment no greater than the greatest alignment the implementation supports in all contexts, which equals `alignof(std::max_align_t)` ([[support.types]]). Every fundamental alignment must be supported by static variables, the stack, `malloc` and `new`.

The same type can have different alignment requirements as a complete object and as a subobject. Example 1 is the virtual-inheritance case:

```cpp
struct B { long double d; };
struct D : virtual B { char c; };
```

As a complete object, `D` contains its own `B` subobject and must be aligned for `long double`. If `D` is a base class subobject of another class that also virtually inherits `B`, the `B` subobject may be placed elsewhere and shared, and the `D` subobject can have a weaker alignment requirement. `alignof` always gives the alignment for the complete-object case.

## Extended alignment and over-aligned types (¶3)

¶3 An alignment greater than `alignof(std::max_align_t)` is an **extended alignment**. Whether extended alignments are supported, and in which contexts, is implementation-defined. A type having an extended alignment requirement is an **over-aligned type**.

Note 1 points out that an over-aligned type is or contains a class type to which extended alignment applies, for example one whose member uses `alignas(64)`. All scalar types have fundamental alignments.

An alignment greater than `__STDCPP_DEFAULT_NEW_ALIGNMENT__` ([[cpp.predefined]]) is a **new-extended alignment**. `operator new(std::size_t)` itself guarantees the alignment given by this macro; when a type's alignment exceeds it, a `new` expression calls the allocation function taking a `std::align_val_t` argument instead ([[expr.new]]).

Extended alignment and new-extended alignment are two different thresholds:

| Platform | `alignof(std::max_align_t)` | `__STDCPP_DEFAULT_NEW_ALIGNMENT__` |
|---|---|---|
| x86-64 Linux (GCC, Clang) | 16 | 16 |
| arm64 macOS (Clang, libc++, measured) | 8 | 16 |
| MSVC x64 | 8 | 16 |

On arm64 macOS, a type with `alignas(16)` exceeds 8 and is over-aligned; but it does not exceed 16, so it is not a new-extended alignment, and `new` can use the ordinary `operator new(size_t)`. On x86-64 the alignment of `max_align_t` is 16 because `long double` is 80-bit extended precision aligned to 16 bytes; on arm64 macOS, `long double` is just `double`.

```cpp run title="over-aligned-new.cpp" ok
#include <cstdint>
#include <cstdio>
#include <cstddef>

struct alignas(64) CacheLine { int x; };    // over-aligned, and new-extended too

int main() {
    std::printf("max_align_t=%zu default_new=%zu CacheLine=%zu\n",
                alignof(std::max_align_t),
                static_cast<std::size_t>(__STDCPP_DEFAULT_NEW_ALIGNMENT__),
                alignof(CacheLine));
    CacheLine* p = new CacheLine;            // calls operator new(size_t, align_val_t)
    bool ok = reinterpret_cast<std::uintptr_t>(p) % 64 == 0;
    delete p;                                // calls the matching operator delete taking align_val_t
    return ok ? 0 : 1;
}
```

In our tests (arm64 macOS) the output is `max_align_t=8 default_new=16 CacheLine=64`, and the return value is 0.

!!! history "Over-aligned new before C++17"
    C++11 introduced `alignas`, but `new CacheLine` still called only `operator new(size_t)`, which guarantees only fundamental alignment; the resulting pointer was quite possibly not a multiple of 64, and creating the object there was UB. Programmers had to use `posix_memalign` or `_aligned_malloc` plus placement new. C++17's [[P0035R4]] added `std::align_val_t`, aligned versions of the allocation and deallocation functions, and `__STDCPP_DEFAULT_NEW_ALIGNMENT__`; since then over-aligned types can be `new`ed directly ([[basic.stc.dynamic.allocation#3]]).

## Alignment values (¶4–¶7)

¶4 Alignments are represented as values of type `std::size_t`. The valid alignments are only the `alignof` values of the fundamental types, plus an additional implementation-defined, possibly empty, set of values. Every alignment value must be a non-negative integral power of two.

¶5 Alignments are ordered from weaker to stronger; larger values are stricter. An address that satisfies an alignment requirement also satisfies any weaker valid alignment; for example, a multiple of 64 is always a multiple of 16. ¶7 adds that comparing alignments means comparing their values.

¶6 The alignment requirement of a complete type can be queried with `alignof` ([[expr.alignof]]). The narrow character types have the weakest alignment requirement, that is, 1. So note 2 says an `unsigned char` array can be used as aligned raw storage, with `alignas` raising its alignment.

```cpp run title="alignas-rules.cpp" error
struct alignas(8) S {};
struct alignas(1) U { S s; };   // error: weaker than the alignment without alignas (8)
alignas(3) int x;               // error: 3 is not a power of 2
alignas(int) alignas(64) unsigned char buf[256];   // OK: takes the strictest, 64
```

The first two lines violate the rules of [[dcl.align]]; Clang 23 reports `requested alignment is less than minimum alignment` and `requested alignment is not a power of 2` respectively.

¶8 is a note: at run time, `std::align` ([[ptr.align]]) can find an aligned position in a buffer.

```cpp run title="std-align.cpp" ok
#include <memory>
#include <new>
#include <cstddef>

struct alignas(32) V { float f[8]; };

int main() {
    unsigned char arena[256];
    void* p = arena;
    std::size_t space = sizeof arena;
    if (std::align(alignof(V), sizeof(V), p, space)) {   // adjusts p to a multiple of 32
        V* v = ::new (p) V{};                             // OK: the storage satisfies the alignment
        v->f[0] = 1.0f;
        v->~V();
    }
}
```

## Unsupported extended alignments (¶9)

¶9 If a requested extended alignment is not supported by the implementation in a given context, the program is ill-formed, and the compiler must diagnose it. For example, an implementation might allow `alignas(4096)` for static variables but not for automatic ones. Which alignments are supported is up to the implementation (¶3), but when one is not supported it must be an error; the implementation cannot silently produce an insufficiently aligned object.

## Implementation view

!!! impl "What alignment looks like in code generation"
    - Each member of a struct is placed according to its own alignment, with padding inserted as needed; the struct's alignment is the largest among its members, and `sizeof` is rounded up to a multiple of the alignment so that every element of an array is aligned.
    - For an over-aligned variable on the stack, the compiler aligns the stack pointer downward at function entry (as in `and rsp, -64`), and usually needs a frame pointer to access arguments.
    - `#pragma pack` and `__attribute__((packed))` are non-standard extensions that produce members with less than natural alignment. Taking the address of such a member and dereferencing it may crash on strict-alignment hardware, and compilers usually warn.

## Common misconceptions

!!! pitfall "Byte buffers don't need `alignas`"
    `unsigned char buf[sizeof(T)]` has an alignment of only 1. Before placement new of a `T` into it, `alignas(T)` must be added. This is the most common mistake in hand-written small buffers or `optional`s, and on x86 it usually does not cause trouble right away.

!!! pitfall "`malloc` satisfies any alignment"
    `malloc` guarantees only fundamental alignment. Over-aligned types need `std::aligned_alloc` (which requires the size to be a multiple of the alignment) or C++17's aligned `operator new`.

!!! pitfall "`std::aligned_storage` is the standard aligned buffer"
    C++23 deprecated `std::aligned_storage` and `std::aligned_union` ([[P1413R3]]). They are easy to misuse: forgetting `::type` gives an empty class; the member `type` is not guaranteed to be an array of `unsigned char` or `std::byte`, so per [[intro.object#3]] it may not provide storage for objects in it; and accessing the object needs `reinterpret_cast`. Write `alignas(T) std::byte buf[sizeof(T)];` directly.

## Questions

!!! question "Question 1"
    Is `struct alignas(16) A { char c; };` an over-aligned type on arm64 macOS? Which allocation function does `new A` call?

<details markdown="1">
<summary>Answer</summary>

`alignof(std::max_align_t)` is 8, and 16 is greater than 8, so `A` is over-aligned. But 16 is not greater than `__STDCPP_DEFAULT_NEW_ALIGNMENT__` (16), so it is not a new-extended alignment, and `new A` calls the ordinary `operator new(std::size_t)`, which already guarantees 16-byte alignment (item 3.3 of [[basic.stc.dynamic.allocation#3]]). Replacing the global `operator new` in our tests shows exactly this version being called.

On x86-64 Linux, 16 does not exceed the alignment of `max_align_t`, so `A` is not even an over-aligned type.
</details>

!!! question "Question 2"
    On a platform where `alignof(int) == 4`, does the following placement new have UB?

    ```cpp
    alignas(8) unsigned char buf[16];
    int* p = ::new (buf + 4) int(1);
    ```

<details markdown="1">
<summary>Answer</summary>

No. The address of `buf` is a multiple of 8, so `buf + 4` is a multiple of 4, which satisfies `int`'s alignment; it is not 8-byte aligned, but `int` only needs 4. `buf` is an `unsigned char` array and the new object lies entirely within it, so `buf` provides storage for this `int` ([[intro.object#3]]), and the lifetime of `buf` itself is unaffected.
</details>
