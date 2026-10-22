---
title: Types for composite class design
summary: "C++26's indirect and polymorphic: putting a class's data member on the heap while keeping value semantics (deep copy, const propagation, no empty state), fixing the three shortcomings of unique_ptr as a member."
updated: 2026-10-19
---

!!! tldr
    - With a `unique_ptr` data member, the enclosing class cannot be implicitly copied, `const` member functions can still modify the pointed-to object, and every access has to consider a null pointer.
    - `indirect<T>` is a `T` on the heap: copying copies the `T`, `const` propagates, and it can be compared and hashed by value.
    - `polymorphic<T>` holds an object of `T` or a class derived from it, and copies by dynamic type without needing a virtual `clone()`.
    - Neither has an empty state; they can only be valueless after being moved from, which `valueless_after_move()` queries.
    - At the time of writing, Clang 23 with libc++ does not implement either class yet.

[mem.composite.types] is a subclause new in C++26 ([[P3019R14]]) that contains only the two class templates [[indirect]] and [[polymorphic]] and has no normative paragraphs of its own. The title, Types for composite class design, states their purpose: to be data members of classes.

## Three problems with unique_ptr as a member

There are several common reasons to put a member on the heap: the member type is still incomplete at that point (pimpl, recursive data structures); the member is large and you want the enclosing object smaller and faster to move; the member's dynamic type is only known at run time. The traditional approach is a `std::unique_ptr<T>` member:

```cpp
struct Widget {
    std::unique_ptr<Impl> impl;
    void set(int v) const { impl->value = v; }   // even a const function can modify it
};
Widget a;
Widget b = a;      // error: the copy constructor is defined as deleted
```

1. The enclosing class cannot be copied. With a `unique_ptr` member, the implicit copy constructor is defined as deleted ([[class.copy.ctor]]), and deep copy has to be written by hand; a polymorphic member also needs a virtual `clone()`.
2. `const` does not propagate. In a `const` member function the member's type is `const unique_ptr<Impl>`, but `*impl` is still `Impl&`, and the pointed-to object can be modified just the same.
3. It can be null. Every access has to consider a null pointer, while null is often not a legitimate state at all.

The goal of `indirect<T>` and `polymorphic<T>` is to make the member behave as if a `T` were stored directly: copyable, `const`-propagating, with no empty state, just with the object stored on the heap.

## The two compared

| | `indirect<T, Allocator>` | `polymorphic<T, Allocator>` |
|---|---|---|
| Type of the owned object | Exactly `T` | `T` or a copyable public class derived from it |
| Copy | Copy-constructs a `T` | Copy-constructs according to the owned object's dynamic type |
| Comparison, hashing | Yes, delegated to `T` | No |
| `operator*` | Four overloads for lvalues and rvalues | Only `const` and non-`const` |
| Typical use | Pimpl, recursive types, large members | Polymorphic members, replacing `unique_ptr<Base>` plus a virtual `clone()` |

The design they share:

- They can lack an owned object only after being moved from; this is called **valueless** ([[g:valueless]]). Move operations simply take over the source's pointer and leave the source valueless, which is cheap and does not throw. Dereferencing a valueless object violates a precondition and is UB.
- Default construction allocates memory and constructs a `T`, unlike `unique_ptr`, which defaults to null.
- They are allocator-aware: they allocate and construct the owned object through `allocator_traits`, and whether the allocator is replaced on assignment and swap follows the same rules as for containers ([[allocator.traits]]). `std::pmr::indirect<T>` and `std::pmr::polymorphic<T>` are aliases using `polymorphic_allocator`.
- `T` may be an incomplete type; members that need the complete definition of `T`, such as the destructor, check completeness with *Mandates*.
- `T` must not be a non-object type, an array, a specialization of `in_place_t` or `in_place_type_t`, or a cv-qualified type; otherwise the program is ill-formed. A program that declares an explicit or partial specialization of them has undefined behavior.

## Compared with other wrapper types

| Type | Storage | Can be empty | Copy | const propagation |
|---|---|---|---|---|
| `T` member | Inside the object | No | Copies `T` | Yes |
| `optional<T>` | Inside the object | Yes | Copies `T` | Yes |
| `unique_ptr<T>` | Heap | Yes | Not copyable | No |
| `shared_ptr<T>` | Heap | Yes | Shares the same object | No |
| `indirect<T>` | Heap | Only after being moved from | Copies `T` | Yes |
| `polymorphic<T>` | Heap; implementations may store small objects inline | Only after being moved from | Copies by dynamic type | Yes |

libc++ (with Clang 23) does not yet provide `std::indirect` or `std::polymorphic`, so none of the examples on the two pages have been compiled.
