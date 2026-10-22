---
title: Explicit lifetime management
summary: "start_lifetime_as uses bytes that are already in place directly as an object, without copying or touching memory; C++26's start_lifetime makes a union member the active member without initializing it."
updated: 2026-10-19
---

!!! tldr
    - Reading externally written bytes, such as a network packet or an `mmap`ed file, as a struct through `reinterpret_cast` is undefined behavior; `std::start_lifetime_as<T>(p)` {{c++23}} is the valid way to do it.
    - `start_lifetime_as` implicitly creates a `T` in place whose object representation is the existing bytes, with the value obtained by the rules of `bit_cast`; it neither reads nor writes the storage, so it works on read-only memory.
    - `T` must be an implicit-lifetime type, such as an aggregate or a trivially copyable struct; types that need a constructor, like `std::string`, are not allowed.
    - For a run-time length use `start_lifetime_as_array<T>(p, n)`, which creates an array object; when `n == 0`, `p` may be null.
    - `std::start_lifetime(r)` {{c++26}} serves a different purpose: it begins the lifetime of an aggregate member of a union and makes it the active member without any initialization, mainly for constant evaluation.

## The bytes are already there

```cpp run ub
#include <cstdint>
#include <cstdio>
struct Header { std::uint32_t magic; std::uint32_t length; };
int main() {
  alignas(Header) unsigned char packet[16] = {0x78, 0x56, 0x34, 0x12, 8};
  auto* h = reinterpret_cast<Header*>(packet);
  std::printf("%u\n", (unsigned)h->length);   // UB: h does not point to a Header object
}
```

The contents of `packet` could come from `recv`, `mmap` or DMA. The program wants to read the first 8 bytes as a `Header`. With Clang 23 it compiles and runs fine and prints `8`, but by the standard it is undefined behavior: `reinterpret_cast` only changes the type of the pointer, `h` still points to the `unsigned char` `packet[0]`, and there is no `Header` object there that can be accessed through `h` ([[basic.lval#11]]).

For the access to be valid, there really has to be a `Header` object in that storage. Objects of implicit-lifetime types ([[g:implicit-lifetime-type]]: scalars, aggregates, classes with trivial construction and destruction, and arrays of them) can be **implicitly created** by certain operations without a constructor ([[g:implicitly-create-objects]], [[intro.object#13]]). `malloc`, `operator new`, `memcpy` and `memmove` all have this effect.

So the portable way in C++20 is to copy the bytes onto themselves in place:

```cpp run ok
#include <cstdint>
#include <cstdio>
#include <cstring>

struct Header {
  std::uint32_t magic;
  std::uint32_t length;
};

Header* as_header(void* p) {
  // memmove implicitly creates objects; the return value points to the new Header
  return static_cast<Header*>(
      std::memmove(p, p, sizeof(Header)));
}

int main() {
  alignas(Header) unsigned char packet[16] = {
      0x78, 0x56, 0x34, 0x12, 8, 0, 0, 0};
  Header* h = as_header(packet);
  std::printf("%x %u\n", (unsigned)h->magic,
              (unsigned)h->length);  // on little-endian: 12345678 8
}
```

[[cstring.syn#3]] specifies that `memcpy` and `memmove` return a pointer to a suitable created object, so the return value can be used directly, with no `std::launder`. If you discard the return value and keep doing `reinterpret_cast` on `packet`, you are back to the problem above.

This works, but the intent is not obvious, and it writes to the storage, which fails on read-only mapped pages. C++23's `start_lifetime_as` ([[P2590R2]]) gives the operation a name and removes the reads and writes of the storage.

## `start_lifetime_as` {{c++23}}

```cpp
template<class T> T* start_lifetime_as(void* p) noexcept;
// plus three overloads taking const void*, volatile void* and const volatile void*,
// returning a correspondingly qualified T*
```

The example above rewritten with it:

```cpp
#include <memory>
#include <cstddef>
#include <cstdint>

struct Header { std::uint32_t magic; std::uint32_t length; };

const Header* parse(const std::byte* packet) {
  // precondition: packet has sizeof(Header) bytes of allocated storage, aligned for Header
  return std::start_lifetime_as<Header>(packet);   // no copy, no access to the storage
}
```

At the time of writing, Clang 23 with libc++ does not yet provide `start_lifetime_as`, so this code has not been compiled.

### Requirements on `T` (¶3)

¶3 `T` must be an implicit-lifetime type and not an incomplete type; otherwise the program is ill-formed.

`start_lifetime_as` calls no constructor; it creates the object by implicit object creation, and only objects of implicit-lifetime types can be created that way. The invariants of `std::string` have to be established by a constructor, so `start_lifetime_as<std::string>` is {{ill-formed}}. The incomplete-type rule excludes arrays of unknown bound such as `int[]`: writing `start_lifetime_as<int[]>` by mistake where `start_lifetime_as_array` was meant is a compile-time error.

### Requirements on the storage (¶4)

¶4 There are three preconditions, and violating any of them is undefined behavior:

- `[p, (char*)p + sizeof(T))` denotes a region of allocated storage;
- that storage is within the range **reachable through `p`** ([[g:reachable-through]], [[basic.compound]]). For example, when `p` points to an `int` member of a struct, you cannot use it to make the adjacent members part of the new object;
- the address is suitably aligned for `T`. The library does not check this.

### Where the value comes from (¶5)

¶5 is the heart of the function:

!!! std "[obj.lifetime]/5"
    The object representation of *a* is the contents of the storage prior to the call to start_lifetime_as.

`start_lifetime_as` implicitly creates an object *a* of type `T` at `p`, together with the objects nested within it. The object representation of *a* is the bytes in the storage before the call.

The value of each created object depends on its type:

- for an object of a trivially copyable type `U`, the value is determined in the same way as for `bit_cast<U>(E)` ([[bit.cast]]), except that the storage is not accessed. It thereby inherits all of `bit_cast`'s rules on padding bits and indeterminate values: if the original bytes are indeterminate, the resulting value is correspondingly indeterminate.
- the value of any other object is unspecified; Note 2 says it can be an indeterminate value.

As with all implicit object creation, which nested objects are created is chosen so as to give the program defined behavior ([[intro.object#13]]).

### Return value (¶6)

¶6 Returns a pointer to *a*. As with the `memmove` approach, the object should afterwards be accessed through this return value; continuing to `reinterpret_cast` the original `unsigned char*` would still need `std::launder`.

### The `const` and `volatile` overloads

The `memmove` approach writes to the storage; even though it writes back the same values, it segfaults on read-only pages mapped with `PROT_READ`. `start_lifetime_as` does not access the storage, and the `const void*` overload returns `const T*`, so it can be used directly on read-only memory. The `volatile` overloads are for memory-mapped hardware registers.

## `start_lifetime_as_array` (¶7–¶10) {{c++23}}

```cpp
template<class T> T* start_lifetime_as_array(void* p, size_t n) noexcept;
// likewise with const / volatile / const volatile overloads
```

`start_lifetime_as<T[4]>` requires the length to be a constant expression. When the length is only known at run time, for example when a packet header says how many records follow, use `start_lifetime_as_array`.

¶7 `T` must be a complete type. `T` need not be an implicit-lifetime type here, because array types are always implicit-lifetime types. The element values are still determined by ¶5: trivially copyable elements by the `bit_cast` rules, other elements have unspecified values.

¶8 Preconditions: `p` is suitably aligned for an array of `T` or is null; `n <= size_t(-1) / sizeof(T)`, i.e. `n * sizeof(T)` does not overflow; and if `n > 0`, `[p, p + n * sizeof(T))` denotes allocated storage reachable through `p`.

¶9 If `n > 0`, the effect is equivalent to `start_lifetime_as<U>(p)`, where `U` is an array of `n` `T`; otherwise there are no effects.

¶10 Returns a pointer to the first element of the created array; if no array was created, returns a pointer that compares equal to `p`.

The rules for `n == 0` and null pointers were added by [[P2679R2]] before C++23 was published. Under the original wording `n == 0` was undefined behavior and generic code had to special-case empty ranges; now `n == 0` is valid, and `p` may then be null. The returned pointer can only be used like a past-the-end pointer and cannot be dereferenced.

!!! lawyer "Why not call `start_lifetime_as<T>` n times in a loop"
    `start_lifetime_as_array` creates one array object, and the returned `T*` points to its elements, so pointer arithmetic within `[0, n]` is valid. Calling `start_lifetime_as<T>` `n` times in a loop yields `n` unrelated complete objects; [[expr.add]] only allows pointer arithmetic within the same array object, so moving a pointer between them is undefined behavior.

## `start_lifetime` (¶1–¶2) {{c++26}}

```cpp
template<class T> constexpr void start_lifetime(T& r) noexcept;
```

This function was added by [[P3726R2]] and has a completely different purpose from the two above. It solves this problem:

```cpp
#include <cstddef>
#include <memory>

template<class T, std::size_t N>
struct Storage {
  union { T elems[N]; };          // no element should be initialized on construction
  constexpr Storage() {
    std::start_lifetime(elems);   // elems becomes the active member; the array's lifetime begins, the elements' does not
  }
  constexpr ~Storage() {}
};
```

Containers like `inplace_vector` need a block of uninitialized storage in which elements are later constructed one by one with `std::construct_at(&elems[i], ...)`. Putting it in a union avoids initializing the elements on construction. At run time, implicit object creation or assigning to a member can make the member active. Constant evaluation, however, requires knowing exactly which member is active and which objects exist, and accessing an inactive member makes the expression not a constant expression. `start_lifetime` provides an explicit signal that does no initialization.

¶1 `T` must be a complete implicit-lifetime aggregate type. Arrays satisfy this.

¶2 If the object referred to by `r` is already within its lifetime, there are no effects; otherwise its lifetime begins. Note 1 adds: no initialization is performed and no subobject has its lifetime started; if `r` denotes a member of a union `U`, it becomes the active member of `U` ([[class.union]]).

At the time of writing, libc++ (with Clang 23) does not yet provide `std::start_lifetime`, so the code above has not been compiled.

## Comparison with related tools

| Tool | Creates objects | Accesses storage | Resulting value | Typical use |
|---|---|---|---|---|
| `reinterpret_cast<T*>(p)` | No | No | No object to access, {{ub}} | Wrong usage |
| `std::launder(p)` | No | No | Requires a `T` object already at `p` | Fixing up a pointer value, see [[ptr.launder]] |
| `memmove(p, p, n)` | Yes | Reads and writes | The original bytes | The portable C++20 approach |
| `start_lifetime_as<T>(p)` | Yes | No | The original bytes, by the `bit_cast` rules | Network packets, `mmap`, read-only memory |
| `start_lifetime(r)` | Begins `r`'s lifetime | No | Not initialized | Union storage in constant evaluation |
| placement new / `construct_at` | Yes | Writes | The result of initialization | Ordinary construction |

The most common confusion is between `launder` and `start_lifetime_as`. `launder` never creates an object; it only fixes up a pointer value when the object already exists but the pointer value in hand does not point to it. What makes the object appear is `start_lifetime_as`.

## Questions

!!! question "Question 1"
    After calling `start_lifetime_as<Header>(buf)` on an `unsigned char buf[64]` written by `recv`, can `buf[0]` still be read?

<details markdown="1">
<summary>Answer</summary>

Yes, and it still reads the original byte. An `unsigned char` array provides storage for objects created within it ([[intro.object#3]]), so the array and its elements do not end their lifetimes because a `Header` appears; reading the bytes of any object through an `unsigned char` lvalue is also allowed ([[basic.lval#11]]). If `length` is later modified through the returned `Header*`, reading `buf[4]` sees the new byte, because it is the same storage.
</details>

!!! question "Question 2"
    Why does `start_lifetime_as` accept only implicit-lifetime types?

<details markdown="1">
<summary>Answer</summary>

`start_lifetime_as` runs no constructor; ¶5 says it implicitly creates objects, and [[intro.object#13]] only allows implicit creation of objects of implicit-lifetime types. Objects of other types must begin their lifetime through a constructor ([[basic.life]]), or their invariants could never be established.
</details>
