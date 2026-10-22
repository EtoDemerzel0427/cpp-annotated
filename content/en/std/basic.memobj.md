---
title: Memory and objects
summary: "A guide to subclause 6.8: how storage, storage duration, objects and lifetime differ, and which question each of the seven subclauses answers."
updated: 2026-10-19
---

!!! tldr
    - Storage, storage duration, objects and lifetime are four different concepts: having bytes does not mean having an object, and storage may still exist when an object is not within its lifetime.
    - Objects are created only by a few constructs: definitions, `new`, operations that implicitly create objects, changing the active member of a union, and temporary objects. `reinterpret_cast` creates no object.
    - Deciding whether an access is valid takes three questions: is there an object there? Is it within its lifetime? Does the pointer or reference you hold point to it?
    - Subclause 6.8 itself has no normative paragraphs; the rules are spread over seven subclauses.

## Four concepts

```cpp run title="four-concepts.cpp" ok
#include <new>
#include <cstdlib>
#include <string>

int main() {
    void* raw = std::malloc(sizeof(std::string));    // obtain storage
    // at this point there is storage, but no std::string object
    auto* s = ::new (raw) std::string("hello");      // create the object; construction completes and its lifetime begins
    s->~basic_string();                              // destruction starts and the lifetime ends; the storage remains
    std::free(raw);                                  // release the storage
}
```

Four things appear in turn in these lines:

| Concept | What it is | Determined by | Defined in |
|---|---|---|---|
| storage | a contiguous sequence of addressable bytes | variable definitions, allocation functions, allocations inside the implementation | [[intro.memory]] |
| storage duration | the minimum time storage exists: static, thread, automatic or dynamic | the syntactic construct used to create the object | [[basic.stc]] |
| object | a typed entity that occupies a region of storage, possibly with a name | definitions, `new`, implicit creation, changing union members, temporaries | [[intro.object]] |
| lifetime | the period of run time during which the object can be used normally according to its type | begins when initialization completes; ends when destruction starts, or when the storage is released or reused | [[basic.life]] |

Storage can exist before the object (after `malloc`, before construction) and can outlive it (after destruction, before `free`). During these two periods, pointers and references can be used only in limited ways ([[basic.life#7]], [[basic.life#8]]).

Several objects can be created one after another in the same storage. Whether pointers, references and names of the old object automatically refer to the new one is decided by the transparent-replacement rule ([[basic.life#9]]); when they don't, `std::launder` is needed.

An array of `unsigned char` or `std::byte` can **provide storage** for objects created in it ([[intro.object#3]]), which is the basis of hand-written buffers and implementations like `std::optional`.

Some simple types (implicit-lifetime types) need no explicit construction: operations like `malloc` and `memcpy` make such objects appear when needed ([[intro.object#13]]). `std::string` is not one of them, so the example above has to use placement new.

## Seven subclauses

| Subclause | Question it answers |
|---|---|
| [[intro.memory]] Memory model | What is a byte; what is a memory location, and why is it the smallest unit of data races; which bit-fields share a memory location |
| [[intro.object]] Object model | Which constructs create objects; subobjects, complete objects, providing storage; when objects can have the same address; implicit object creation |
| [[basic.align]] Alignment | At which addresses objects can be placed; fundamental and extended alignment; how over-aligned types are allocated |
| [[basic.life]] Lifetime | When lifetime begins and ends; what pointers outside the lifetime can do; transparent replacement and `std::launder` |
| [[basic.indet]] Indeterminate and erroneous values | What happens when reading an uninitialized object; in C++26, reading an automatic variable yields an erroneous value |
| [[basic.stc]] Storage duration | The four storage durations; the constraints global allocation and deallocation functions must satisfy |
| [[class.temporary]] Temporary objects | When temporaries appear and are destroyed; the rules for lifetime extension by reference binding and the exceptions |

[[intro.object]] and [[basic.life]] are the core: the former covers where objects come from, the latter when they can be used. They are best read together.

Some closely related subclauses outside 6.8:

- [[basic.types]]: object and value representations, trivially copyable types, implicit-lifetime types.
- [[basic.lval]]: restrictions on accessing an object through a glvalue of another type, i.e. the strict aliasing rule.
- [[basic.compound]]: the states of a pointer value, pointer-interconvertibility.
- [[expr.new]], [[expr.delete]]: creating and destroying dynamic objects.
- [[class.union]]: changing the active member of a union.
- [[intro.races]]: data races, defined in units of memory locations.
