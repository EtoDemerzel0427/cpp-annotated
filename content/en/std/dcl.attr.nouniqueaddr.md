---
title: No unique address attribute
summary: "[[no_unique_address]] lets a data member overlap other members: an empty member can take no space, and tail padding can be used by later members; subobjects of the same type still need distinct addresses, and whether anything is actually compressed is up to the implementation."
updated: 2026-10-19
---

!!! tldr
    - An empty class as an ordinary member takes at least 1 byte, often more with alignment; marked `[[no_unique_address]]`, it can take no space and share an address with other members.
    - Two subobjects of the same type must still have distinct addresses, so two empty members of the same type can't both be squeezed out.
    - Whether it actually compresses is up to the implementation. GCC and Clang compress; MSVC ignores it and offers `[[msvc::no_unique_address]]` instead.
    - Such a member is a potentially-overlapping subobject: `sizeof` gives the size of the type, which may be more than the bytes it exclusively occupies, so you can't `memcpy` a whole `sizeof` over it.
    - Adding or removing this attribute changes the class layout and is an ABI-breaking change.

## Why empty members take space

```cpp run ok
struct Empty {};
struct Plain { Empty e; int i; };
struct Packed { [[no_unique_address]] Empty e; int i; };

static_assert(sizeof(Empty) == 1);   // a complete object takes at least 1 byte
static_assert(sizeof(Plain) == 8);   // 1 byte + 3 bytes padding + int
static_assert(sizeof(Packed) == 4);  // e and i share an address
int main() {}
```

The sizes above are Clang 23's results. C++ requires every complete object to take at least 1 byte so that different objects have different addresses. A class with no data members used as a member is no exception, and with the alignment of the following `int`, `Plain` wastes 4 bytes.

Stateless allocators, deleters, hash functions and comparators are all empty classes like this, and nearly every container and smart pointer has to store one. Before C++20, the only way to make them take no space was the **empty base optimization** (EBO): an empty class used as a base can take no bytes. So standard library implementations were full of compressed pairs inheriting from allocators. This is awkward: inheritance brings name conflicts, `final` classes can't be inherited from, and virtual functions of the base can be overridden by accident.

[[P0840R2]] introduced `[[no_unique_address]]` so that data members can do the same.

## The rules (¶1–¶2)

¶1 `no_unique_address` specifies that a non-static data member is a **potentially-overlapping subobject** ([[g:potentially-overlapping-subobject|potentially-overlapping subobject]], [[intro.object#7]]). It takes no arguments and can be applied to non-static data members other than bit-fields. Base class subobjects are potentially-overlapping subobjects anyway; this attribute gives members the same status.

The note in ¶2 explains what this means: the member can share an address with another member or a base class; and the padding that would otherwise be inserted at the end of the object can be used to store other members.

¶2 also recommends that `__has_cpp_attribute(no_unique_address)` be nonzero only if the attribute actually can make a potentially-overlapping subobject have zero size.

The standard's example is a hash table:

```cpp run ok
struct Bucket;
template<typename Key, typename Value,
         typename Hash, typename Pred, typename Allocator>
class hash_map {
  [[no_unique_address]] Hash hasher;
  [[no_unique_address]] Pred pred;
  [[no_unique_address]] Allocator alloc;
  Bucket* buckets;
};

struct H {}; struct P {}; struct A {};
static_assert(sizeof(hash_map<int, int, H, P, A>)
              == sizeof(void*));   // holds with Clang 23
int main() {}
```

When `Hash`, `Pred` and `Allocator` are all empty types, they can share an address with `buckets`, and the whole object is the size of one pointer.

## When it is zero-sized, and when addresses can be shared

The attribute itself only says the member is a potentially-overlapping subobject; the concrete effects are specified by two paragraphs of [[intro.object]].

[[intro.object#8]] specifies zero size. An object has nonzero size if any of the following holds: it is not a potentially-overlapping subobject; it is not of class type; it has virtual functions or virtual bases; it has subobjects of nonzero size or unnamed bit-fields of nonzero length. Among the remaining objects, a base class subobject of a standard-layout class with no non-static data members has zero size; otherwise, when it has zero size is implementation-defined {{impl}}.

So for a `[[no_unique_address]]` member, the standard doesn't guarantee zero size. An implementation that ignores the attribute entirely also conforms, consistent with the ignorability of [[dcl.attr.grammar#8]].

[[intro.object#10]] specifies addresses. Two objects with overlapping lifetimes may have the same address in some cases, one of which (¶10.3) is: they are subobjects of the same complete object, at least one has zero size, and their types are not similar. Otherwise they must have distinct addresses and occupy disjoint bytes. The address of a zero-sized subobject is the address of an unspecified byte of the storage of its complete object.

```cpp run impl
#include <cstdio>
struct Empty {};
struct Empty2 {};
struct B { [[no_unique_address]] Empty e1;
           [[no_unique_address]] Empty e2; int i; };
struct C { [[no_unique_address]] Empty e1;
           [[no_unique_address]] Empty2 e2; int i; };
int main() {
  B b; C c;
  std::printf("B=%zu C=%zu\n", sizeof(B), sizeof(C));
  std::printf("B: %d\n", (void*)&b.e1 == (void*)&b.e2);
  std::printf("C: %d\n", (void*)&c.e1 == (void*)&c.e2);
}
```

In our tests this prints `B=4 C=4`, `B: 0`, `C: 1`. The two members of `B` have the same type, so their addresses must differ; Clang puts `e1` at offset 0 and `e2` at offset 1, both overlapping the `int`, and the class is still 4 bytes. The two members of `C` have different types and can share one address.

Distinct addresses for objects of the same type are an identity guarantee of the C++ object model: a program may rely on `&b.e1 != &b.e2`, for example by using addresses as map keys.

## Reusing tail padding

The other kind of compression in the note in ¶2 is letting later members occupy the **tail padding** of a non-empty member, i.e. the bytes added at the end of an object for alignment.

```cpp run impl
#include <cstdio>
struct Pod    { int i; char c; };              // a trivial C-style struct
struct NonPod { int i; char c; NonPod() {} };  // has a user-provided constructor

struct T1 { [[no_unique_address]] Pod p;    char d; };
struct T2 { [[no_unique_address]] NonPod p; char d; };
struct T3 { NonPod p; char d; };

int main() {
  std::printf("T1=%zu T2=%zu T3=%zu\n", sizeof(T1), sizeof(T2), sizeof(T3));
}
```

In our tests this prints `T1=12 T2=8 T3=12`. `NonPod` takes 8 bytes, the last 3 of which are tail padding, and `T2` puts `d` into those 3 bytes.

`T1` isn't compressed because of a rule of the Itanium C++ ABI (the ABI GCC and Clang use on Linux and macOS): tail padding can only be reused for types that aren't POD for the purpose of layout (roughly C++03 POD). The rule was originally made for base classes, and `[[no_unique_address]]` members follow it. C-style structs are often copied whole with `memcpy`, tail padding included; if their tail padding were reused, such code would clobber neighboring members.

### sizeof is no longer the number of bytes safe to copy

```cpp run
#include <cstdio>
#include <cstring>
struct Inner {
  int i; char c;
  Inner(int i = 0, char c = 0) : i(i), c(c) {}
};
struct Outer {
  [[no_unique_address]] Inner in;
  char d;   // placed in the tail padding of in
};
int main() {
  Outer o{{1, 'a'}, 'D'};
  Inner src{2, 'b'};
  o.in = src;                              // writes only in's own bytes
  std::printf("d=%c\n", o.d);
  std::memcpy(&o.in, &src, sizeof(Inner)); // overwrites d too
  std::printf("d=%d\n", o.d);
}
```

In our tests this prints `d=D` and then `d=0`: `sizeof(Inner)` and `sizeof(Outer)` are both 8, and when `memcpy` overwrites the 8 bytes of `in`, it overwrites `d` too. The compiler-generated assignment only copies `Inner`'s own data (what the Itanium ABI calls dsize) and doesn't touch the tail padding, so it's fine.

The standard has two corresponding places. [[expr.sizeof#2]] says that `sizeof` applied to a potentially-overlapping subobject gives the size of the type, not the size the subobject actually occupies. [[basic.types.trivial#3]] allows the bytes of an object of trivially copyable type to be copied out and back in, but explicitly excludes potentially-overlapping subobjects.

Base class subobjects have always had the same problem. So in generic code, given a reference or pointer, optimizing assignment of trivially copyable types with `memcpy(&x, &y, sizeof x)` is unsafe: you don't know whether `x` is a potentially-overlapping subobject inside some larger object.

## Other consequences

- Transparent replacement: creating a new object of the same type with placement new in the storage of a potentially-overlapping subobject doesn't make the new object a subobject of the enclosing object (item 2.3 of [[intro.object#2]]), and the original member name and pointers don't automatically refer to it ([[basic.life#9]]).
- `offsetof`: several empty members can have the same offset, possibly also equal to the offset of other members.
- Layout compatibility with C: once compression happens, the class layout no longer matches the corresponding C struct, so don't use this attribute on structs shared with C.
- ABI: adding or removing the attribute changes the layout and is an ABI-breaking change.

!!! impl "MSVC and `msvc::no_unique_address`"
    MSVC accepts `[[no_unique_address]]` but it has no effect. MSVC promises binary compatibility across versions since VS 2015 and doesn't want a standard attribute to change layout without the user knowing. It offers `[[msvc::no_unique_address]]` instead, which really compresses. Clang targeting the MSVC ABI (`-target x86_64-pc-windows-msvc`) behaves the same: in our tests it gives an unknown-attribute warning for `[[no_unique_address]]`, `__has_cpp_attribute(no_unique_address)` is 0, and `[[msvc::no_unique_address]]` makes empty members take no space.

    Portable code is usually written like this:

    ```cpp
    #if defined(_MSC_VER)
    #  define NO_UNIQUE_ADDRESS [[msvc::no_unique_address]]
    #else
    #  define NO_UNIQUE_ADDRESS [[no_unique_address]]
    #endif
    ```

    Both behaviors conform, since when something has zero size is implementation-defined anyway.

## Comparison with the empty base optimization

| | Empty base optimization | `[[no_unique_address]]` |
|---|---|---|
| Applies to | Base classes | Non-static data members |
| Name conflicts, accidental overriding | At risk | None |
| `final` classes | Can't be inherited from | Usable |
| Several of the same type | Can't directly inherit the same class twice | Can be declared, but can't share an address |
| Zero size | Guaranteed for standard-layout empty bases | Implementation-defined |
| MSVC | Needs `__declspec(empty_bases)` with multiple inheritance | Needs the `msvc::` version |

## History

!!! history
    - Introduced in C++20 ([[P0840R2]]). An attribute was chosen over new syntax because when to compress can be left to the implementation anyway, and ignoring it doesn't change the program's meaning.
    - The term potentially-overlapping subobject was introduced at the same time. Since then, rules for `sizeof`, the bytewise copying guarantee, transparent replacement, address uniqueness and so on are stated in its terms, treating base class subobjects and members with this attribute uniformly.

## Questions

!!! question "Question"
    Under the Itanium ABI, what is `sizeof` of each of the three classes below?
    ```cpp
    struct E {};
    struct X { [[no_unique_address]] E e; char c; };
    struct Y { [[no_unique_address]] E e1; [[no_unique_address]] E e2; };
    struct Z { E e; [[no_unique_address]] E e2; };
    ```

<details markdown="1">
<summary>Answer</summary>

- `X` is 1. `e` and `c` have different types and can share an address.
- `Y` is 2. `e1` and `e2` have the same type, so their addresses must differ. Both can be zero-sized, but the address of a zero-sized subobject must still fall on some byte of the complete object, and two distinct addresses need at least 2 bytes.
- `Z` is 2. `e` has no attribute and occupies 1 byte at offset 0; `e2` has the same type, can't be placed at offset 0, and can only go at offset 1.

These three values were verified with `static_assert` on Clang 23. The standard itself only guarantees that subobjects of the same type have distinct addresses and that complete objects have nonzero size; the exact numbers depend on the ABI.
</details>
