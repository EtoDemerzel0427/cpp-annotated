---
title: Memory model
summary: "The byte is the fundamental unit of storage, and every byte has a unique address; a memory location is a scalar object or a sequence of adjacent nonzero-width bit-fields, and two threads can access different memory locations without interfering."
updated: 2026-10-19
---

!!! tldr
    - A byte is the smallest addressable unit of storage, at least 8 bits; the exact number of bits is the implementation-defined `CHAR_BIT`.
    - A program's memory is one or more sequences of contiguous bytes, and every byte has a unique address.
    - A memory location is a scalar object that is not a bit-field, or a sequence of adjacent bit-fields all of nonzero width.
    - Two threads writing different memory locations at the same time do not interfere; writing the same memory location at the same time without synchronization is a data race.
    - Adjacent bit-fields share one memory location by default; a zero-width bit-field `: 0` separates them.

## Bytes (¶1–¶2)

¶1 The fundamental storage unit in the C++ memory model is the **byte** ([[g:byte|byte]]). The standard places three requirements on it:

- A byte is at least large enough to contain the ordinary literal encoding of any element of the basic literal character set ([[lex.charset]]) and the eight-bit code units of UTF-8. The latter means a byte has at least 8 bits.
- A byte is composed of a contiguous sequence of bits, the number of which is implementation-defined; it is `CHAR_BIT` in `<climits>`. All mainstream platforms use 8; some DSPs use 16 or 32.
- The memory available to a program consists of one or more sequences of contiguous bytes, and every byte has a unique address.

`sizeof(char)`, `sizeof(signed char)` and `sizeof(unsigned char)` are all 1 ([[expr.sizeof]]), and `std::byte` also occupies one byte. A byte is a unit of storage and `char` is a type; the two have the same size.

The standard says one or more sequences, rather than requiring the whole address space to be one flat array. That is why comparing pointers to unrelated objects (`p < q`) gives an unspecified result ([[expr.rel]]), and pointer arithmetic is only allowed within one array ([[expr.add]]). On segmented memory, comparing addresses across segments is meaningless.

Every byte having a unique address is the basis of the rules for object addresses ([[intro.object#10]]): an object's address is the address of its first byte.

¶2 is a note pointing to [[basic.types.general]], where the object and value representations of types are defined.

## Memory locations (¶3)

```cpp run title="separate-locations.cpp" ok
#include <thread>

struct S {
    char a;
    char b;     // a and b are two memory locations
};

S s;

int main() {
    std::thread t1([] { for (int i = 0; i < 100000; ++i) s.a = char(i); });
    std::thread t2([] { for (int i = 0; i < 100000; ++i) s.b = char(i); });
    t1.join();
    t2.join();
}   // no data race: the two threads write different memory locations
```

Two threads write adjacent members of the same struct at the same time without a lock, and yet the program is correct. The reason is that the two members are different **memory locations** ([[g:memory-location|memory location]]):

!!! std
    A *memory location* is the storage occupied by the object representation of either an object of scalar type that is not a bit-field or a maximal sequence of adjacent bit-fields all having nonzero width.

¶3 There are two kinds of memory location:

- the storage occupied by a scalar object (arithmetic type, enumeration, pointer, pointer to member, `std::nullptr_t`) that is not a bit-field. Class objects and arrays are not memory locations themselves; they consist of several memory locations.
- a sequence of adjacent bit-fields all of nonzero width, taken as long as possible, until a non-bit-field member, a zero-width bit-field or the end of the struct is reached.

The last sentence of ¶3 is a requirement on implementations: two or more threads of execution can access separate memory locations without interfering with each other. A compiler may not generate, for a write to `s.a`, a wide store that also overwrites `s.b`, unless it can prove no other thread can observe it.

Data races ([[intro.races]]) are defined in units of memory locations: two threads access the same memory location, at least one access is a write, and there is no synchronization; the behavior is undefined.

Note 3 adds that language mechanisms like references and virtual functions may involve additional memory locations not accessible to programs, such as the vptr; their concurrency safety is the implementation's responsibility.

### Why bit-fields are grouped together

Hardware cannot write just 3 bits. To modify a bit-field, the compiler must read the whole storage unit containing it, change some bits, and write it back. If two threads each modify one of two bit-fields in the same unit, the two read-modify-write sequences overwrite each other.

The standard acknowledges this by defining a sequence of adjacent bit-fields as one memory location. Modifying them at the same time is a data race, and the programmer must synchronize:

```cpp run title="bitfield-race.cpp" ub
#include <thread>

struct Flags {
    unsigned ready : 1;
    unsigned error : 1;   // in the same memory location as ready
};

Flags f{};

int main() {
    std::thread t1([] { f.ready = 1; });
    std::thread t2([] { f.error = 1; });  // UB: accesses the same memory location as t1 without synchronization: a data race
    t1.join();
    t2.join();
}
```

Built with `-fsanitize=thread` and run in our tests, ThreadSanitizer reports a `data race`. There are three fixes: add a mutex; insert a zero-width bit-field between the two bit-fields; or don't use bit-fields, and use `std::atomic<unsigned>` with bit operations instead.

```cpp run title="bitfield-fixed.cpp" ok
#include <thread>

struct Flags {
    unsigned ready : 1;
    unsigned       : 0;   // zero-width bit-field: puts the two bit-fields in different memory locations
    unsigned error : 1;
};

Flags f{};

int main() {
    std::thread t1([] { f.ready = 1; });
    std::thread t2([] { f.error = 1; });  // OK: different memory locations
    t1.join();
    t2.join();
}
```

## Which bit-fields share a memory location (¶4–¶5)

¶4 is a note that spells out the definition of ¶3 as conclusions that can be applied directly. Two bit-fields are in different memory locations whenever something between them breaks the sequence:

| Case | Same memory location? |
|---|---|
| a bit-field and an adjacent non-bit-field member | no |
| a zero-width bit-field `: 0` between two bit-fields | no |
| a non-bit-field member between two bit-fields | no |
| one in a nested struct, one not | no |
| only nonzero-width bit-fields between two bit-fields | yes |

The example in ¶5:

```cpp run title="bitfield-locations.cpp" ok
struct S {
    char a;          // memory location #1
    int b : 5,       // ┐
        c : 11,      // ┘ memory location #2: b and c are adjacent and both of nonzero width
          : 0,       // zero-width bit-field: breaks the sequence
        d : 8;       // memory location #3
    struct {
        int ee : 8;  // memory location #4: in a nested struct
    } e;
};

int main() {
    S s{};
    s.a = 1; s.b = 2; s.c = 3; s.d = 4; s.e.ee = 5;
}
```

`a`, `d` and `e.ee` can each be modified concurrently with any other member; `b` and `c` cannot be modified concurrently, but `b` and `a` can.

!!! warning "Unnamed nonzero-width bit-fields don't separate"
    The rule only requires bit-fields to have nonzero width, not names. In `int x : 3; int : 5; int y : 4;`, `x`, the unnamed bit-field and `y` are one memory location, and `x` and `y` cannot be modified concurrently. Only an unnamed bit-field of width zero separates.

## Implementation view

!!! impl "How compilers write bit-fields"
    - Under the Itanium C++ ABI (GCC and Clang on Linux and macOS), the allocation unit of a bit-field is determined by its declared type, adjacent bit-fields are packed contiguously within a unit, and `: 0` makes the next bit-field start a new allocation unit. MSVC's rules differ; for example, adjacent bit-fields with different declared types do not share a unit, so the same struct may have different `sizeof` under different ABIs. But which bit-fields form one memory location is specified by the standard, independent of the ABI.
    - To write a bit-field, the compiler generates a sequence that reads the whole unit, masks, ORs in the new value, and writes it back. The C++11 memory model requires this read-modify-write not to cross the boundary of the current memory location: in the example in ¶5, writing `b` may not read or write `a` or `d`.
    - An ordinary `char` member is written with a single-byte store instruction, which naturally satisfies ¶3. On old hardware without single-byte stores, meeting this requirement is expensive.

!!! history "History"
    C++98/03 only specified bytes and that every byte has a unique address, with no notion of memory locations, because the language itself did not know threads existed, and a compiler could merge a write to `char a` into a wider read-modify-write. C++11 added memory locations and the bit-field rules of this subclause when it introduced the multi-threaded memory model ([[intro.multithread]]); C11 adopted almost the same definition.

## Common misconceptions

!!! pitfall "A class object is one memory location"
    In `struct P { int x; int y; };`, `p.x` and `p.y` are two memory locations, and two threads writing them separately do not race. But two threads assigning to the whole `p` at the same time (`p = P{...}`) access the same memory locations, which is a data race.

!!! pitfall "The elements of `std::vector<bool>` are separate memory locations"
    `std::vector<bool>` stores bits packed, and its elements are not objects. Whether modifying different elements concurrently is safe is specified by the library's data race clause ([[container.requirements]]), not by this subclause; in practice different elements are often in the same word and cannot be modified concurrently.

## Questions

!!! question "Question 1"
    In the struct below, which members can be modified concurrently by two threads without synchronization?

    ```cpp
    struct T {
        int  a : 4;
        int    : 4;
        int  b : 4;
        char c;
        int  d : 4;
        int    : 0;
        int  e : 4;
    };
    ```

<details markdown="1">
<summary>Answer</summary>

The memory locations are: `a`, the unnamed 4-bit bit-field and `b` form one (the unnamed bit-field has nonzero width and does not separate); `c` is one; `d` is one (separated by `c` before and by `: 0` after); `e` is one. So `a` and `b` cannot be modified concurrently, while any two members in different locations (such as `a` and `c`, `b` and `d`, `d` and `e`) can.
</details>

!!! question "Question 2"
    Can `CHAR_BIT` be 7? Can it be 9?

<details markdown="1">
<summary>Answer</summary>

Not 7: ¶1 requires a byte to hold the eight-bit code units of UTF-8, so it has at least 8 bits (the C standard also requires `CHAR_BIT >= 8`). It can be 9: the number of bits is implementation-defined, and the standard only gives a lower bound.
</details>
