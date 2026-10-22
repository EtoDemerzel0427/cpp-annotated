---
title: Legal and illegal type punning
summary: When reading a piece of bytes as another type is legal in C++, and what problem each of strict aliasing, unions, reinterpret_cast, memcpy, std::bit_cast and std::start_lifetime_as addresses.
tags: type punning, strict aliasing, bit_cast, object model, UB, topic
updated: 2026-10-19
---

!!! tldr
    - Reading or writing an object of one type through a pointer or reference of another type is legal only when the target is a byte type (`char`, `unsigned char`, `std::byte`) or the corresponding signed/unsigned type; everything else is UB, and Clang at `-O2` makes visible miscompilations based on it.
    - `reinterpret_cast<T*>(p)` only changes the pointer's type and almost never changes which object it points to; reading an inactive union member is UB in C++.
    - Copying bytes into a new object of the right type (`std::memcpy`, C++20's `std::bit_cast`) is always correct, and the compiler optimizes it into a single register move.
    - When you don't want to copy, use C++23's `std::start_lifetime_as<T>(p)` to create an object in place, preserving the bytes.
    - During constant evaluation, `std::bit_cast` is the only general-purpose punning tool available, but it doesn't accept types such as pointers and unions.

## What type punning is

**Type punning** means interpreting the bytes of an object of one type as another type: looking at the bit pattern of a `float` as a `uint32_t`, treating the bytes of a network packet as a struct, iterating over an `int` array as an `unsigned` array. C programmers do this with pointer casts and unions. In C++, both tools are UB in most cases.

Deciding whether a pun is legal means answering three questions in turn, which belong to different layers of the object model (see [[topics/object-model]]):

1. Does the object exist? Is there a `T` object within its lifetime at that address ([[intro.object]], [[basic.life]])?
2. Does the pointer point to it? Does the value of the `T*` in hand point to that `T` object, or still to the original object ([[basic.compound#7]], [[expr.static.cast#12]])?
3. Is this access allowed? Does reading or writing that object through a glvalue of type `T` (an expression designating an object, see [[topics/value-categories]]) satisfy the access rules ([[basic.lval#11]])?

On top of these there is the physical precondition of alignment ([[basic.align]]).

`reinterpret_cast<T*>(p)` answers none of these questions. The legal punning tools are each a way of getting a yes to one of them:

| Tool | Which question it addresses | Effect |
|---|---|---|
| Access through `char`, `unsigned char`, `std::byte` | Access | Byte types can access any object |
| Access through the corresponding signed/unsigned type | Access | `int` and `unsigned` can access each other |
| Pointer-interconvertibility | Points to | Between a standard-layout class and its first member, or a union and its members, `reinterpret_cast` changes the target |
| `memcpy`, `std::bit_cast` | Sidesteps all of them | Copies the bytes into a new object of the right type |
| `std::start_lifetime_as` | Exists, points to | Creates an object in place, preserving the bytes, and returns a pointer to it |
| `std::launder` | Points to | Gets a pointer to an object that already exists |
| `-fno-strict-aliasing` | Access (compiler extension) | The compiler promises not to optimize based on the access rules |

## Strict aliasing

### A real miscompilation

```cpp run title="tbaa.cpp" ub
#include <cstdio>
[[gnu::noinline]] int store_and_read(int* i, float* f) {
  *i = 1;
  *f = 2.0f;        // the compiler assumes a float lvalue can't modify an int object
  return *i;        // so it returns the constant 1 directly
}
int main() {
  int x = 0;
  int r = store_and_read(&x, reinterpret_cast<float*>(&x));   // UB: accesses an int object through a float lvalue
  std::printf("r = %d, x = %d\n", r, x);
}
```

Results with Clang 23 (arm64):

```text
-O0                          r = 1073741824, x = 1073741824
-O2                          r = 1, x = 1073741824
-O2 -fno-strict-aliasing     r = 1073741824, x = 1073741824
```

At `-O2`, `store_and_read` stores 1, then stores `0x40000000`, and returns the constant 1 without reloading `*i`:

```text
__Z14store_and_readPiPf:
	mov	w8, #1
	str	w8, [x0]
	mov	w8, #1073741824
	str	w8, [x1]
	mov	w0, #1          ; *i not reloaded
	ret
```

For the same variable `x`, the function's return value says it is 1, while memory holds the bit pattern of `2.0f`.

### The access rule ([basic.lval]/11)

The compiler's basis for this is [[basic.lval#11]]:

!!! std
    An object of dynamic type Tobj is type-accessible through a glvalue of type Tref if Tref is similar to: Tobj, a type that is the signed or unsigned type corresponding to Tobj, or a char, unsigned char, or std::byte type.

When an object's dynamic type (the type of object it actually is) is `Tobj`, it may only be accessed through a glvalue whose type is similar to one of: `Tobj` itself; the signed/unsigned type corresponding to `Tobj`; `char`, `unsigned char` or `std::byte`. **Similar** roughly means the same after ignoring cv-qualification at every level ([[conv.qual]]). Reading or writing ([[defns.access]]) the stored value of an object through a glvalue of any other type has undefined behavior. For item-by-item details, for example that `signed char`, `char8_t` and `int8_t` are not among the exemptions, see [[basic.lval]].

This rule is commonly called **strict aliasing**. It allows the compiler to perform **type-based alias analysis** (TBAA): an `int*` and a `float*` can't point to the same object, so a write through the `float*` can't change the value of `*int_ptr`. That's where the miscompilation above comes from.

!!! impl "Who can catch it"
    Neither UBSan nor ASan. Compiling the example with `-fsanitize=address,undefined`, the program quietly prints `r = 1073741824` (the instrumentation happens to suppress the optimization), with no report.

    The dedicated detector is TypeSanitizer (`-fsanitize=type`, available only in recent Clang versions). Output with Clang 23:

    ```text
    ==9400==ERROR: TypeSanitizer: type-aliasing-violation on address 0x00016f20674c (pc ...)
    WRITE of size 4 at 0x00016f20674c with type float accesses an existing object of type int
        #0 0x000100bffd5c in store_and_read(int*, float*)+0x54 (alt:arm64+0x100007d5c)
    ```

    It tracks the effective type of each piece of memory at run time, in line with [[basic.lval#11]]; its overhead is high, so it suits testing rather than production.

### What -fno-strict-aliasing changes

GCC's and Clang's `-fno-strict-aliasing` turns off TBAA, and the compiler no longer assumes that pointers of different types don't overlap. Many C codebases that rely on pointer punning, such as the Linux kernel, are compiled this way.

From the standard's point of view this is a conforming extension ([[intro.compliance.general#11]]): it gives a meaning to behavior that was undefined, without changing the behavior of any well-formed program. But it handles only one of the questions, the access rule:

- An object that doesn't exist, a pointer that doesn't point to it, a misaligned address, reading an inactive union member, pointer arithmetic leaving the array ([[expr.add#6]]): these are still UB, and the compiler may still exploit them through other reasoning.
- It doesn't affect constant evaluation: `reinterpret_cast` isn't allowed in constant expressions at all (¶2.16 of [[expr.const.core#2]]).
- Code that depends on it isn't portable; a different set of compile options, LTO, or a different compiler can all break it again.

So it's suitable as a safety net for legacy code, not as a basis for writing new code.

## Union punning: legal in C, UB in C++

```cpp ub
#include <cstdint>
union U { float f; std::uint32_t u; };
std::uint32_t bits_of(float x) {
  U v;
  v.f = x;
  return v.u;     // C: OK, reinterprets the bytes as uint32_t
                  // C++: UB, reads an object not within its lifetime
}
```

A C++ union has at most one **active member** at a time, the member whose lifetime is in progress ([[class.union.general#2]]). `v.f = x` makes `f` active, `u`'s lifetime hasn't begun, and reading `v.u` accesses an object that isn't within its lifetime (¶8.1 of [[basic.life#8]]).

The only special case is the common initial sequence: when several standard-layout struct members start with members of the same types, that common part can be read through any of the structs ([[class.mem]]).

GCC's documentation for `-fstrict-aliasing` says this kind of punning is permitted when memory is accessed through the union type; Clang behaves the same in practice. But the extension covers only writing `u.member` directly. Once you take a member's address and access through the pointer, you're back in strict aliasing territory:

```cpp run title="union-pun.cpp" ub
#include <cstdio>
union U { int i; float f; };
[[gnu::noinline]] int direct(U& u) {
  u.i = 1;
  u.f = 2.0f;          // written through a union member access expression
  return u.i;          // C++: reads an inactive member, UB; under the extension, the bit pattern of 2.0f
}
[[gnu::noinline]] int via_ptr(int* ip, float* fp) {
  *ip = 1;
  *fp = 2.0f;          // the pointers have left the union
  return *ip;
}
int main() {
  U u;
  std::printf("%d\n", direct(u));
  std::printf("%d\n", via_ptr(&u.i, &u.f));
}
```

Clang 23 at `-O2` prints `1073741824` and `1`. The first function works per the extension, and the second is optimized by TBAA into returning the constant 1. By the standard, both are UB.

During constant evaluation, reading an inactive member must be diagnosed (¶2.11 of [[expr.const.core#2]]):

```cpp run title="union-constexpr.cpp" error
#include <cstdint>
union U { float f; std::uint32_t u; };
constexpr std::uint32_t via_union(float x) { U v{.f = x}; return v.u; }
static_assert(via_union(1.0f) == 0x3f800000);
// error: read of member 'u' of union with active member 'f' is not allowed in a constant expression
```

## reinterpret_cast: changes the type, almost never the target

`reinterpret_cast<T*>(p)` between object pointers is defined as `static_cast<T*>(static_cast<void*>(p))` ([[expr.reinterpret.cast#7]]). A `static_cast` from `void*` changes which object the pointer points to in only one case: when the object *a* the original pointer points to is **pointer-interconvertible** with some object *b* whose type is similar to `T`, the result points to *b*. Otherwise the pointer value is unchanged; it still points to the original object, just with a different type ([[expr.static.cast#12]]).

The pointer-interconvertibility relations listed in [[basic.compound#7]] are few:

| Relation | Example | Points to after conversion |
|---|---|---|
| The same object | | Unchanged |
| A union object and its non-static data members | `reinterpret_cast<float*>(&u)` | The member whose type is similar to the target type |
| A standard-layout class object and its first non-static data member | `reinterpret_cast<int*>(&hdr)` | The first member of `hdr` |
| A standard-layout class object and any of its base class subobjects | `reinterpret_cast<Base*>(&derived)` | The base class subobject |
| Transitive combinations of the above | union → member → that member's first member | The final object |

Note 7 points out specifically that an array and its first element have the same address but are not pointer-interconvertible.

Outside these cases, `reinterpret_cast` gives a pointer of type `T*` that points to an object of some other type. Whether dereferencing it is a legal access depends entirely on the access rule: only if `T` is a byte type or the corresponding signed/unsigned type.

### Pitfall: treating a byte buffer as a struct

```cpp run title="packet.cpp" ub
#include <cstdint>
#include <cstdio>
#include <cstring>
std::uint32_t read_u32_bad(const unsigned char* p) {
  return *reinterpret_cast<const std::uint32_t*>(p);     // UB: there's no uint32_t object there (and it may be misaligned)
}
std::uint32_t read_u32_good(const unsigned char* p) {
  std::uint32_t v;
  std::memcpy(&v, p, sizeof v);                           // OK: any alignment, any source
  return v;
}
int main() {
  alignas(4) unsigned char packet[8] = {0, 1, 0, 0, 0, 0, 0, 0};
  std::printf("%u\n", read_u32_good(packet + 1));
  std::printf("%u\n", read_u32_bad(packet + 1));
}
```

The bad version breaks two rules at once: there's no `uint32_t` object there, and the address isn't aligned to 4. UBSan can report the latter; no sanitizer can report the former:

```text
packet.cpp:5:10: runtime error: load of misaligned address 0x00016b9d6641 for type 'const std::uint32_t' (aka 'const unsigned int'), which requires 4 byte alignment
```

ARM64 and x86-64 hardware both tolerate ordinary misaligned loads, so code like this often shows no problem for a long time, until the compiler vectorizes it into SIMD instructions that require alignment, or it is ported to a strict-alignment platform.

### Pitfall: arithmetic on a punned pointer

```cpp
int arr[5] = {1, 2, 3, 4, 5};
unsigned* p = reinterpret_cast<unsigned*>(arr + 1);
unsigned k = *p;          // OK: an int object may be accessed through an unsigned lvalue
unsigned* q = p + 1;      // UB: p points to an element of an int array, and unsigned is not similar to int
```

The access rule allows reading an `int` as `unsigned`, but pointer arithmetic requires the pointer type to be similar to the array element type ([[expr.add#6]]; this is exactly the standard's example there). So iterating over an `int[]` as an `unsigned[]` is literally UB, even if each individual read is legal.

### Pitfall: walking an object representation byte by byte

`reinterpret_cast<const unsigned char*>(&obj)[k]` is the basic operation of serialization and hashing. But this pointer points to `obj` itself, not to an element of some `unsigned char` array; for pointer arithmetic, `obj` is treated as an array of one element whose element type is `obj`'s type. `unsigned char` isn't similar to that element type, so by the letter of [[expr.add#6]], adding to this pointer is already UB.

This is an acknowledged wording defect, and [[P1839]] tries to give object representations real byte-array semantics. In the meantime, every compiler supports this idiom.

## memcpy: copying into an object of the right type

```cpp ok
#include <cstdint>
#include <cstring>
std::uint32_t bits_of(float f) {
  std::uint32_t u;
  std::memcpy(&u, &f, sizeof u);    // u gets f's value representation (1.0f → 0x3f800000)
  return u;
}
```

`std::memcpy` and `std::memmove` implicitly create objects in the destination region before copying ([[cstring.syn#3]]). For trivially copyable types, copying the bytes of one object into another gives the destination the source's value ([[basic.types.trivial#4]]).

None of the three questions poses an obstacle: `u` is a real `uint32_t` object, the pointer points to it, and the access type is its own type. Copying isn't looking at an object through the wrong type; it moves the bytes into a new object of the right type.

Compilers recognize `memcpy`, and small copies are inlined into a single register move, so performance isn't a concern:

```cpp
#include <cstdint>
#include <cstring>
std::uint32_t by_memcpy(float x) { std::uint32_t r; std::memcpy(&r, &x, sizeof r); return r; }
```

```text
__Z9by_memcpyf:          ; Clang 23 -O2, arm64
	fmov	w0, s0
	ret
```

## std::bit_cast {{c++20}}

`std::bit_cast<To>(from)` ([[bit.cast]], [[P0476R2]]) packages the `memcpy` idiom as a function that returns a value, and it can be used during constant evaluation:

```cpp run title="bit-cast.cpp" ok
#include <bit>
#include <cstdint>
#include <cstring>
#include <cstdio>
constexpr std::uint32_t bits(float x) { return std::bit_cast<std::uint32_t>(x); }
static_assert(bits(1.0f) == 0x3f800000);          // usable at compile time
int main(int argc, char**) {
  float f = static_cast<float>(argc);
  std::uint32_t a = bits(f);
  std::uint32_t b; std::memcpy(&b, &f, sizeof b);
  std::printf("%x %x\n", a, b);                   // 3f800000 3f800000
}
```

It requires `sizeof(To) == sizeof(From)`, and both must be trivially copyable types ([[bit.cast#1]]). The value representation of the result is bit-for-bit equal to the object representation of `from`, and objects nested in the result are implicitly created.

### Two kinds of failure

The run-time problem is indeterminate bits ([[bit.cast#3]]). Padding bits of the source, subobjects not within their lifetime (such as the inactive part of a union), and objects that themselves have indeterminate values all produce indeterminate bits. If indeterminate bits land in an object of non-byte type in the result, the behavior is undefined; if they land in an `unsigned char` or `std::byte`, only the value of that byte is indeterminate (¶3.1).

The constant evaluation restriction is constexpr-unknown representation ([[bit.cast#2]]). The compile-time evaluator doesn't know the numeric value of pointers, nor which representation a union currently holds, so if either `To` or `From` has a **constexpr-unknown representation**, the `bit_cast` can't appear in a constant expression. [[expr.const.core#1]] lists these types: unions, `std::meta::info`, pointers and pointers to members, volatile-qualified types, classes with reference members, and types with base classes or members of these types.

```cpp run title="bit-cast-constexpr.cpp" error
#include <bit>
#include <cstdint>
struct P { int* p; };
struct S { char c; int i; };       // 3 bytes of padding after c
int g;
constexpr auto a = std::bit_cast<std::uintptr_t>(P{&g});    // error: a pointer has a constexpr-unknown representation
constexpr auto b = std::bit_cast<std::uint64_t>(S{'a', 1}); // error: padding bits go into the value representation of uint64_t
```

Clang 23's diagnostics:

```text
note: bit_cast from a pointer type is not allowed in a constant expression
note: indeterminate value can only initialize an object of type 'unsigned char' or 'std::byte'; 'unsigned long long' is invalid
```

The second line is UB at run time too, since indeterminate bits land in a `uint64_t`. Constant evaluation just turns it into a mandatory diagnostic.

## std::start_lifetime_as {{c++23}}

`memcpy` and `bit_cast` both copy. If the bytes are already there, such as a file brought in by `mmap`, a buffer written by DMA, or a network packet received by `recv`, and the object is large, copying is a waste. `std::start_lifetime_as<T>(p)` ([[obj.lifetime]], [[P2590R2]]) solves this:

!!! std
    Implicitly creates objects within the denoted region consisting of an object *a* of type T whose address is p, and objects nested within *a*. The object representation of *a* is the contents of the storage prior to the call.

It creates a `T` object at `p` (and the objects nested within it), whose object representation is the contents of the storage before the call, and returns a pointer to it. The object exists and the pointer points to it: two questions solved at once. It requires `T` to be an implicit-lifetime type (scalars, arrays, trivial classes and so on, [[basic.types.general]]), and the storage to be allocated and aligned ([[obj.lifetime#3]], [[obj.lifetime#4]]). There is also `start_lifetime_as_array<T>(p, n)`.

How it differs from related tools:

| | Creates an object | Preserves the existing bytes | Copies | Returns a pointer to the new object |
|---|---|---|---|---|
| `std::memcpy(dst, src, n)` | Yes (at `dst`) | Yes (copied over) | Yes | Yes |
| placement new `new (p) T` | Yes | No; indeterminate value after default-initialization | No | Yes |
| `std::launder(p)` | No | | No | Yes, requires the object to exist already |
| `std::start_lifetime_as<T>(p)` | Yes | Yes | No | Yes |

!!! impl "Not yet in libc++"
    At the time of writing, `std::start_lifetime_as` can't be found in the libc++ that ships with Clang 23; for libstdc++'s support, see its documentation. An alternative available since C++20 is to have `memmove` copy the buffer onto itself: `memmove` implicitly creates objects and returns a pointer to a suitable created object, followed by a `launder` for good measure:

    ```cpp
    #include <cstdint>
    #include <cstring>
    #include <new>
    struct Header { std::uint32_t magic, length; };
    const Header* view_header(unsigned char* buf) {
      return std::launder(static_cast<Header*>(std::memmove(buf, buf, sizeof(Header))));
    }
    ```

    Compilers recognize this self-copy, and Clang 23 at `-O2` compiles `view_header` to a single `ret`.

## Putting objects in byte arrays

The standard way to put an object in a buffer is `alignas(T) unsigned char buf[sizeof(T)]` or a `std::byte` array, then placement new, keeping its return value:

```cpp run title="placement.cpp" ok
#include <cstddef>
#include <new>
#include <string>
int main() {
  alignas(std::string) std::byte storage[sizeof(std::string)];
  std::string* s = ::new (storage) std::string("pun-free");   // uses the return value of placement new
  bool ok = s->size() == 8;
  s->~basic_string();
  return ok ? 0 : 1;
}
```

Two rules of the object model are involved here:

- Only `unsigned char` and `std::byte` arrays can **provide storage** for a newly created complete object, without affecting the array's own lifetime ([[intro.object#3]]). `char` arrays are not included: creating an object in a `char` array reuses the storage, and the lifetimes of the overwritten `char` elements end.
- When the lifetime of an `unsigned char` or `std::byte` array begins, objects are implicitly created within it ([[intro.object#16]]). So after `alignas(Header) unsigned char buf[64]; recv(fd, buf, 64, 0);`, there can already be a `Header` in `buf`. But a pointer obtained by decay from `buf` doesn't point to it, and `std::launder` is needed (see Puzzle 5 in [[topics/object-model]]).

## Punning during constant evaluation

The compile-time evaluator rejects nearly every punning tool:

| Tool | Usable in constant expressions? | Basis |
|---|---|---|
| `reinterpret_cast` | No | ¶2.16 of [[expr.const.core#2]] |
| Reading an inactive union member | No, must be diagnosed | ¶2.11 |
| `static_cast<T*>(void_ptr)` | Yes since C++26, provided it really points to an object whose type is similar to `T` | ¶2.15 ([[P2738R1]]) |
| `memcpy` | No, it's not a constexpr function | ¶2.3 |
| `std::bit_cast` | Yes, unless a constexpr-unknown representation is involved | [[bit.cast#2]] |
| Implicit object creation | Doesn't happen | [[intro.object#16]] |

So `std::bit_cast` is the only general-purpose punning tool usable both at compile time and at run time.

## Choosing by need

| Need | Use | Don't use |
|---|---|---|
| Look at the bit pattern of a `float`/`double` | `std::bit_cast<std::uint32_t>(f)` | A union, `*(uint32_t*)&f` |
| Read an integer from a byte stream | `memcpy` into a local variable, then handle byte order | `*reinterpret_cast<uint32_t*>(p)` |
| Use a large block of existing bytes as a struct without copying | `std::start_lifetime_as<T>`; in C++20, a self-`memmove` plus `launder` | `reinterpret_cast<T*>(buf)` |
| Inspect or hash an arbitrary object byte by byte | `const unsigned char*` or `const std::byte*`; or `bit_cast` to `std::array<std::byte, N>` | `std::int8_t*`, `char8_t*` |
| Put an object in a buffer | `alignas(T) std::byte buf[N]` plus placement new, keeping the return value | An unaligned `char buf[N]` |
| Tagged multi-type storage | `std::variant`, or a union with explicit switching of the active member | Writing one member and reading another |
| Viewing signed as unsigned and vice versa | Access directly through a glvalue of the corresponding type; this is legal | |
| Accessing a C-style struct header | A standard-layout type, using pointer-interconvertibility with the first member | The same thing on a non-standard-layout type |

## Questions

!!! question "Question 1"
    On mainstream platforms `std::uint8_t` is an alias for `unsigned char`. Is `reinterpret_cast<std::uint8_t*>(&obj)[0]` legal? What about `std::int8_t`?

<details markdown="1">
<summary>Answer</summary>

It's legal when `uint8_t` is a typedef for `unsigned char`. A typedef doesn't introduce a new type, so this is an `unsigned char` glvalue, which satisfies ¶11.3 of [[basic.lval#11]]. But the standard doesn't require `uint8_t` to be `unsigned char`; it could be an extended integer type, so the portability of this form depends on the implementation.

`std::int8_t` is usually `signed char`, and `signed char` isn't among the exemptions. It can only access `signed char` or `unsigned char` objects (via ¶11.1, ¶11.2); accessing a `float` through it is UB. (For the arithmetic problem with the subscript `[0]` itself, see the section on walking an object representation byte by byte above.)
</details>

!!! question "Question 2"
    From which line does the code below go wrong?

    ```cpp
    struct A { int x; };
    struct B { int y; };
    A a{1};
    B* pb = reinterpret_cast<B*>(&a);
    int* py = &pb->y;
    int v = *py;
    ```

<details markdown="1">
<summary>Answer</summary>

Objects of `A` and `B` aren't pointer-interconvertible, so the value of `pb` still points to `a` ([[expr.static.cast#12]]). `pb->y` is a member access, while `*pb` designates an `A` object, and `A` isn't similar to `B`. [[expr.ref#10]] states explicitly that this is UB, and its standard example is exactly `reinterpret_cast<B&>(d).j`.

So forming `pb->y` on the fifth line is already UB, without waiting for the read on the sixth line. That `A` and `B` have identical layouts doesn't help: layout compatibility only matters in C++ for the common initial sequence of a union.
</details>

!!! question "Question 3"
    Is `std::bit_cast<std::array<unsigned char, 8>>(S{'a', 1})` (with `S` as above, containing 3 bytes of padding) legal at run time? Can it be used to initialize a `constexpr` variable?

<details markdown="1">
<summary>Answer</summary>

It's legal at run time. The indeterminate bits produced by padding all land in `unsigned char` elements, so by ¶3.1 of [[bit.cast#3]] those few elements merely have indeterminate values; it's not UB. Reading the values of those elements afterwards is still subject to [[basic.indet]].

But it can't initialize a `constexpr` variable: the result of a constant expression can't contain indeterminate values. Clang 23 reports "subobject '__elems_' is not initialized" for this.
</details>
