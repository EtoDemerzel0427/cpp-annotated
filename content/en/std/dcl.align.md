---
title: Alignment specifier
summary: "alignas applies to variables, data members and classes, and can strengthen alignment but not weaken it; with several, the strictest wins; all declarations of the same entity must give consistent alignment."
updated: 2026-10-19
---

!!! tldr
    - `alignas` can be applied to variables, data members and classes, but not to functions, function parameters, bit-fields or `catch` parameters; nor is it part of a type, so a `using` alias can't carry it.
    - `alignas(T)` is equivalent to `alignas(alignof(T))`; with several in one declaration, the strictest (largest) wins.
    - `alignas` can only strengthen alignment. If the combined result is weaker than the alignment the entity would otherwise need, the program is ill-formed; packing a struct requires compiler extensions.
    - If any declaration has `alignas`, the definition must specify the same alignment; inconsistency across translation units requires no diagnostic.
    - Since C++17, `new` of a type with alignment beyond the default calls an allocation function taking `std::align_val_t` and gets correctly aligned memory.

## Strengthening alignment with alignas

```cpp run ok
struct alignas(64) CacheLine { int v; };
static_assert(alignof(CacheLine) == 64);
static_assert(sizeof(CacheLine) == 64);

struct Pair { alignas(64) int a; alignas(64) int b; };
static_assert(sizeof(Pair) == 128);   // a and b each occupy a cache line

int main() {}
```

An object's address must be a multiple of its **alignment**. Alignment values are powers of 2; for example, on common platforms `int` is 4 and `double` is 8; see [[basic.align]]. `alignas` is the **alignment-specifier** introduced in C++11, used to request stricter alignment than the default.

A common use is making an object start on a cache-line or SIMD-register-width boundary. In the example above, the two members of `Pair` are each 64-byte aligned and so land on two separate cache lines; two threads writing `a` and `b` respectively don't interfere with each other (avoiding false sharing).

Syntactically `alignas(...)` is a kind of *attribute-specifier* ([[dcl.attr.grammar]]), so it can be written in the same positions as attributes. But unlike standard attributes, it really changes the meaning of a program: alignment affects layout, `sizeof`, `alignof` and dynamic allocation.

## Where it can be used (¶1)

```cpp run error
struct alignas(16) V { int i; };      // OK: class
alignas(32) int g;                    // OK: variable
struct M { alignas(8) char c; };      // OK: data member

alignas(double) void f();             // error: function
void h(alignas(8) int p);             // error: function parameter
struct BF { alignas(4) int b : 3; };  // error: bit-field
using T = alignas(16) int;            // error: not part of a type
```

¶1 `alignas` can be applied to variables, data members of classes, and declarations of classes (written in a *class-head* or *elaborated-type-specifier*). It can't be applied to bit-fields, function parameters or exception declarations (`catch` parameters).

Where parameters and exception objects are stored isn't decided by the declaring side: parameters are placed by the calling convention, possibly in registers; exception objects are allocated by the runtime library. Bit-fields don't even have addresses. For a parameter needing high alignment, pass a pointer or reference.

`alignas` is not part of a type either. There's no such type as `alignas(16) int`, neither `typedef` nor `using` can carry it, and `decltype` doesn't see `alignas` on a variable. For a reusable highly aligned type, define a class with `alignas`, such as `struct alignas(16) A16 { int v; };`.

An `alignas` with `...` is a pack expansion, expanding to several alignment-specifiers:

```cpp run ok
template<class... Ts>
struct alignas(Ts...) Storage {   // alignas(T1) alignas(T2) ...
  unsigned char data[16];
};
static_assert(alignof(Storage<char, double, int>)
              == alignof(double));
int main() {}
```

## Two forms (¶2–¶3)

```cpp run error
alignas(3) int a;             // error: 3 is not a power of 2
alignas(double) char b[8];    // OK: i.e. alignas(alignof(double))
alignas(1 << 20) char huge;   // whether it's accepted is up to the implementation
```

¶2 The expression in `alignas(expression)` must be an integral constant expression (¶2.1). If its value is not a valid alignment value, or is an **extended alignment** (one greater than `alignof(std::max_align_t)`) that the implementation doesn't support in the context of the declaration, the program is ill-formed (¶2.2).

Whether an extended alignment is supported depends on context. Objects with static storage duration are limited by the object file format and loader, and stack variables by the compiler's ability to realign the stack, so the same `alignas(N)` may work in one place and be ill-formed in another. Clang 23 accepts `alignas(1 << 20)` on both global and local variables.

¶3 `alignas(type)` is equivalent to `alignas(alignof(type))` ([[expr.alignof]]). The type here can't be a function type.

!!! lawyer "alignas(0)"
    C++11 stated explicitly that `alignas(0)` has no effect. ¶2 of the current draft no longer has that sentence; by ¶2.2, 0 is not an alignment value (alignment values are powers of 2), so it should be ill-formed. Yet ¶4 still speaks of the strictest nonzero alignment, with no effect otherwise, which seems to assume 0 is valid. Clang 23 accepts `alignas(0) int y;` without a warning. Don't rely on this in templates where the `N` in `alignas(N)` might be 0.

## With several: the strictest wins (¶4)

¶4 An entity's alignment requirement is the strictest nonzero alignment among its alignment-specifiers. Without alignment-specifiers, naturally, they have no effect.

```cpp run ok
alignas(4) alignas(16) alignas(8) int z;
int main() { return alignof(decltype(z)) == 4 ? 0 : 1; }   // z itself is 16-aligned
```

The last line also shows that `alignas` doesn't enter the type: `decltype(z)` is just `int`, with alignment still 4.

## It can't weaken (¶5)

```cpp run error
struct alignas(8) S {};
struct alignas(1) U {
  S s;
};                     // error: U would need 8; alignas(1) is weaker

alignas(1) int weak;   // error: int needs 4
```

¶5 The combined effect of all alignment-specifiers in a declaration must not be weaker than the alignment the entity would require without them. That is, `alignas` can only strengthen alignment, not weaken it.

To weaken alignment (packing a struct), the only options are implementation extensions such as `#pragma pack` and `[[gnu::packed]]`. They are outside the standard, and accessing packed members may produce misaligned accesses.

¶5 checks the combined effect, not each specifier separately. The example in ¶7 uses this to write a general buffer declaration with alignment A that can hold N objects of type T:

```cpp
alignas(T) alignas(A) T buffer[N];
```

If A is smaller than `alignof(T)`, writing `alignas(A)` alone would violate ¶5; adding `alignas(T)` makes ¶4 take the stricter of the two, so the result is always valid.

## All declarations must agree (¶6)

```cpp run error
alignas(double) unsigned char c[sizeof(double)];  // definition
extern unsigned char c[sizeof(double)];   // OK: may omit it
alignas(float)
  extern unsigned char c[sizeof(double)]; // error: different alignment
```

¶6 has three requirements:

- If the definition has an alignment-specifier, other non-defining declarations either specify equivalent alignment or none;
- Conversely, if any declaration has an alignment-specifier, every definition must specify equivalent alignment;
- If declarations in different translation units have different alignment-specifiers, the program is ill-formed, no diagnostic required ({{ifndr}}: the compiler need not report it, and the program has no guarantees).

```cpp title="tu1.cpp"
struct S { int x; } s, *p = &s;
```

```cpp title="tu2.cpp" ifndr
struct alignas(16) S;   // but the definition of S in tu1 doesn't have this alignment
extern S* p;
```

The rule has a direction. A translation unit that just uses an object needn't care about alignment and can write an `extern` declaration without `alignas`. But once some translation unit sees `alignas(16)`, it may generate SIMD loads requiring 16-byte alignment based on it; the storage is allocated by the definition, and if the definition didn't specify that alignment, things go wrong at run time. The compiler sees one translation unit at a time and can't catch such inconsistency, hence IFNDR.

## Dynamic allocation

If a type declared with `alignas` needs extended alignment, `new` before C++17 didn't guarantee it, because `operator new` only guarantees fundamental alignment. C++17's [[P0035R4]] added allocation functions taking a `std::align_val_t` parameter. When a type's alignment exceeds `__STDCPP_DEFAULT_NEW_ALIGNMENT__`, a `new` expression calls them automatically ([[expr.new]], [[basic.stc.dynamic.allocation]]).

```cpp run ok
#include <cstdint>
#include <cstdio>
#include <cstddef>

struct alignas(64) CacheLine { int v; };

int main() {
  auto* p = new CacheLine[3];   // calls operator new[](size_t, align_val_t)
  auto addr = reinterpret_cast<std::uintptr_t>(p);
  std::printf("misalign=%d max_align=%zu\n",
              static_cast<int>(addr % 64), alignof(std::max_align_t));
  delete[] p;
}
```

In our tests (arm64 macOS) this prints `misalign=0 max_align=8`; on x86-64 Linux the alignment of `max_align_t` is 16. `std::malloc` only guarantees fundamental alignment and ignores `alignas`; for over-aligned memory use `new` or `std::aligned_alloc`.

!!! impl "Implementation notes"
    - GCC and Clang map `alignas` to the same mechanism as `__attribute__((aligned(N)))`. The GNU `aligned` attribute can lower alignment on a typedef; that is an extension the standard form doesn't allow.
    - An over-aligned stack variable requires the compiler to realign the stack pointer at function entry; on x86-64 you'll see instructions like `and rsp, -64`, usually needing a frame pointer as well.
    - `std::hardware_destructive_interference_size` (C++17, `<new>`) gives the spacing needed to avoid false sharing and is often used together with `alignas`.

## History

!!! history
    - C++11: `alignas`, `alignof`, `std::aligned_storage` ([[N2341]]); `alignas(0)` stated to have no effect.
    - C++17: `new` supports over-aligned types ([[P0035R4]]); `std::hardware_destructive_interference_size` added.
    - C++23: `std::aligned_storage` and `std::aligned_union` deprecated in favor of writing `alignas(T) std::byte buf[sizeof(T)];` directly.
    - ¶2 of the current draft no longer mentions `alignas(0)`, while ¶4 still says nonzero; see above.

## Questions

!!! question "Question"
    Assuming `alignof(short) == 2`, is each of the following declarations well-formed?
    ```cpp
    alignas(2) alignas(char) short s1;
    alignas(char) short s2;
    alignas(short) alignas(1) short s3;
    ```

<details markdown="1">
<summary>Answer</summary>

- `s1`: well-formed. The strictest is 2, not weaker than `short`'s own alignment.
- `s2`: ill-formed. The combined effect is 1, weaker than the 2 it would have without it, violating ¶5. Clang reports `requested alignment is less than minimum alignment of 2`.
- `s3`: well-formed. Although `alignas(1)` alone is weaker, ¶5 only looks at the combined effect, which is 2. The `alignas(T) alignas(A)` idiom in ¶7 relies on exactly this.
</details>
