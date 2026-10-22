---
title: "Memory: the <memory> header"
summary: "Notable parts of the <memory> synopsis (the freestanding split, POINTER_OF), how the specialized memory algorithms relate to placement new, why addressof exists, and the rules for C's malloc family in the C++ object model: implicit object creation, and realloc(p, 0) is erroneous behavior."
updated: 2026-10-19
---

!!! tldr
    - `construct_at` is a placement new and `destroy_at` is a destructor call; both can be used in constant evaluation.
    - `std::addressof` returns the actual address of an object, unaffected by an overloaded unary `operator&`; generic code should take addresses with it.
    - `malloc`, `calloc` and `realloc` do not call `operator new`, but they implicitly create objects in the returned storage, so using a `malloc`'d block directly as an `int` array is well-defined.
    - `realloc(p, 0)` is erroneous behavior in C++, with implementation-defined effects; C23 made it undefined behavior.
    - `unique_ptr`, `allocator_traits` and `addressof` are freestanding; `std::allocator` and `shared_ptr` are not.

[memory] is the first subclause of Chapter 20. ¶1 ([memory.general]) says it describes the contents of `<memory>` and some of the contents of `<cstdlib>`; the latter is the `malloc` family in the last section of this page.

This site splits its subclauses into pages by topic:

| Subclause | Note on this site |
|---|---|
| [pointer.traits], [pointer.conversion] | [[pointer.traits]]: `pointer_traits`, `to_address` |
| [ptr.align] | [[ptr.align]]: `align`, `assume_aligned`, `is_sufficiently_aligned` |
| [obj.lifetime] | [[obj.lifetime]]: `start_lifetime_as` and friends |
| [allocator.tag], [allocator.uses] | [[allocator.uses]]: `allocator_arg`, `uses_allocator`, uses-allocator construction |
| [allocator.traits] | [[allocator.traits]] |
| [default.allocator] | [[default.allocator]]: `std::allocator` |
| [specialized.addressof], [c.malloc] | This page |

## Specialized memory algorithms: placement new as a library

```cpp run title="construct-at.cpp" ok
#include <memory>
#include <new>

struct S { int v; };

constexpr int f() {
    std::allocator<S> a;
    S* p = a.allocate(2);                       // only the array object's lifetime begins, not the elements'
    std::construct_at(p, 1);                    // usable in constant evaluation since C++20
    ::new (static_cast<void*>(p + 1)) S{2};     // placement new also works since C++26
    int r = p[0].v + p[1].v;
    std::destroy(p, p + 2);
    a.deallocate(p, 2);
    return r;
}
static_assert(f() == 3);

int main() {}
```

`uninitialized_copy`, `uninitialized_fill`, `construct_at`, `destroy_at`, `destroy` and the rest are declared in `<memory>` and specified in [[specialized.algorithms]].

The effect of `construct_at(p, args...)` is `::new (voidify(*p)) T(std::forward<Args>(args)...)` ([[specialized.construct]]), where `voidify(obj)` converts `addressof(obj)` to `void*`. So it is a placement new ([[expr.new]]) with three differences:

- it uses `::new`, bypassing any class-specific `operator new`;
- it uses `addressof` instead of `&`, so an overloaded `operator&` does not interfere;
- it is `constexpr`. Before C++26 placement new could not be written directly in constant evaluation, and `construct_at` was the only way. Clang 23 rejects the placement new line of the example above with `-std=c++23` and accepts it with `-std=c++2c`.

`destroy_at(p)` is `p->~T()` for a non-array type; for an array it destroys the elements one by one.

When these algorithms create new objects in storage, the lifetime of the object previously occupying that storage ends, by the rule in [[basic.life]]. If an exception is thrown partway through construction, the objects already constructed are destroyed in an unspecified order and the exception is then propagated ([[specialized.algorithms.general]]).

## `addressof` [specialized.addressof]

Unary `&` on an operand of class type participates in overload resolution ([[over.match.oper]]), so a class can make `&x` return anything, or even define it as deleted:

```cpp run title="addressof.cpp" ok
#include <memory>

struct Evil {
    int x;
    void operator&() const = delete;   // taking the address is forbidden
};

constexpr int g() {
    Evil e{5};
    // &e;                               // error: calls the deleted operator&
    return std::addressof(e)->x;         // OK: the actual address, and usable in constant evaluation
}
static_assert(g() == 5);

int main() {}
```

¶1 `addressof(r)` returns the actual address of the object or function referenced by `r`, even in the presence of an overloaded `operator&`. ¶2 If `E` is an lvalue constant subexpression, `addressof(E)` is a constant subexpression too.

Generic code such as containers, `optional` and `construct_at` must get the actual address, so the standard library uses `addressof` throughout.

The synopsis also has a deleted overload `const T* addressof(const T&&) = delete;` that rejects rvalue arguments: `std::addressof(Evil{})` is {{ill-formed}}, because the address of a temporary would almost certainly dangle.

!!! impl "Implementation"
    An `addressof` usable in constant evaluation cannot be written in plain C++, because `reinterpret_cast` cannot appear in a constant expression. libc++, libstdc++ and the MSVC STL all implement it with the compiler builtin `__builtin_addressof`.

## C library memory allocation [c.malloc]

These functions are declared in `<cstdlib>` (the note in ¶1). ¶2 and ¶8 specify that their semantics are those of the C standard (currently C23, ISO/IEC 9899:2024, 7.24.4), and C++ adds three rules.

### Implicit object creation (¶4, ¶7)

```cpp run title="malloc-objects.cpp" ok
#include <cstdio>
#include <cstdlib>

struct Point { int x, y; };

int main() {
    int* p = static_cast<int*>(std::calloc(4, sizeof(int)));
    auto* q = static_cast<Point*>(std::malloc(sizeof(Point)));
    q->x = 1; q->y = 2;                      // no placement new needed
    std::printf("%d %d\n", p[3], q->x + q->y);   // 0 3
    std::free(q);
    std::free(p);
}
```

!!! std
    These functions implicitly create objects ([intro.object]) in the returned region of storage and return a pointer to a suitable created object.

¶4 These functions **implicitly create objects** in the returned storage and return a pointer to a suitable created object. That makes the example well-defined: `Point` is an implicit-lifetime type (an aggregate or scalar type, for example), the storage returned by `malloc` already contains a `Point` object, and its members can be assigned directly. The mechanism is described in the implicit object creation part of [[intro.object]]; the rule was added in C++20 by [[P0593R6]].

¶4 and ¶7 also specify two orderings:

- `calloc` creates the objects first and then zeroes the storage. So the zeroed bytes are the values of those objects, and `p[3]` in the example reads 0.
- When `realloc` returns a non-null pointer, it creates the objects first and then copies the old contents. The old contents are copied into new objects that already exist, so reading elements after `realloc`ing an `int` array is well-defined.

### No `operator new` involved (¶3, ¶7, ¶9)

`malloc`, `calloc`, `aligned_alloc` and `realloc` do not call `::operator new()`, and `free` does not call `::operator delete()`. So replacing the global `operator new` ([[new.delete]]) does not affect `malloc`; releasing memory from `new` with `free`, or memory from `malloc` with `delete`, is {{ub}} ([[basic.stc.dynamic.deallocation]]).

### `realloc(p, 0)` is erroneous behavior (¶5–¶6)

¶5 The precondition is that `free(ptr)` has well-defined behavior, that is, `ptr` is null or comes from the `malloc` family and has not been freed yet.

!!! std
    If ptr is not null and size is zero, the behavior is erroneous and the effects are implementation-defined.

¶6 When `ptr` is not null and `size` is zero, the behavior is erroneous behavior ([[g:erroneous-behavior]]) and the effects are implementation-defined.

C implementations have long disagreed on `realloc(p, 0)`: some free `p` and return a null pointer, others return a minimal block. C23 changed it to undefined behavior. C++ did not follow and classified it as {{erroneous}} instead: the implementation must give a definite effect, while the usage is recognized as an error that the implementation may diagnose or terminate on. Portable code should handle `size == 0` separately.

!!! pitfall "malloc only guarantees fundamental alignment"
    `malloc` only guarantees suitability for fundamental alignment ([[g:fundamental-alignment]], i.e. `alignof(max_align_t)`). For a type with extended alignment (such as `alignas(64)`), use `aligned_alloc`, where by the C standard `size` should be an integral multiple of `alignment`; or just use `new`, which since C++17 calls the allocation function taking `align_val_t` for over-aligned types.

## Notable parts of the synopsis [memory.syn]

¶1 lists what `<memory>` contains: utilities describing the properties of pointers and pointer-like types, managing memory for containers, destroying objects, and constructing objects in uninitialized memory; `pointer_tag_pair` ([[ptrtag]]), where which bits of the pointer it uses is implementation-defined and the wrapper has the same size as the original pointer; and smart pointers and `out_ptr_t` / `inout_ptr_t` ([[smartptr]]). The synopsis itself runs to more than eight hundred lines, almost all declarations; the following points are worth noting.

### The freestanding markers

Most declarations in the synopsis carry a `// freestanding` comment, meaning a freestanding implementation ([[g:freestanding-implementation]]) must provide them too. The dividing line is whether a heap is needed:

- `pointer_traits`, `allocator_traits`, `uses_allocator`, `addressof`, `construct_at`, `unique_ptr`, `default_delete`, `out_ptr` and `pointer_tag_pair` are freestanding. A `unique_ptr` with a custom deleter works even in a kernel.
- `std::allocator`, `make_unique`, `shared_ptr`, `weak_ptr`, `indirect` and `polymorphic` are not. They either call `::operator new` directly or, like `shared_ptr`, need to allocate a control block.
- The parallel algorithm overloads taking an execution policy are marked `// freestanding-deleted`: in a freestanding implementation these overloads exist but are defined as deleted ([[freestanding.item]]).

### `POINTER_OF` (¶2–¶3)

¶2 defines the exposition-only type function *POINTER_OF*(T): `T::pointer` if that is a valid type (¶2.1); otherwise `T::element_type*` if `T::element_type` is valid (¶2.2); otherwise `pointer_traits<T>::element_type*` (¶2.3).

¶3 *POINTER_OF_OR*(T, U) is *POINTER_OF*(T) if that is valid, otherwise `U`. `out_ptr` / `inout_ptr` in [[smartptr.adapt]] use them to derive the corresponding raw pointer type from an arbitrary smart pointer class.

At the end of the synopsis, `pmr::indirect<T>` and `pmr::polymorphic<T>` are declared in `std::pmr`, the versions using `polymorphic_allocator<T>` ([[indirect]], [[polymorphic]]).

## Questions

!!! question "Question 1"
    In `std::addressof(f)`, where `f` is a function, what is the result? Can `addressof` be used on a bit-field?

<details markdown="1">
<summary>Answer</summary>

¶1 says `addressof` returns the actual address of an object or function, so `std::addressof(f)` returns a function pointer, with `T` deduced as a function type.

Bit-fields come in two cases. For a non-const bit-field `b.a`, `T` is deduced as `int`; `int&` cannot bind to a bit-field ([[dcl.init.ref]]), so the call is ill-formed, and Clang reports non-const reference cannot bind to bit-field. For a const bit-field `b.c`, `T` is deduced as `const int`, and `const int&` binds to a temporary, so `addressof` returns the address of the temporary, which dangles once the full-expression ends. The deleted `addressof(const T&&)` does not catch it, because the argument is an lvalue. Clang 23 gives no diagnostic for this.
</details>

!!! question "Question 2"
    Is the following well-defined in C++20? `int* p = (int*)std::calloc(4, sizeof(int)); return p[3];`

<details markdown="1">
<summary>Answer</summary>

Yes, and it returns 0. `calloc` implicitly created suitable objects (here an `int` array or several `int`s, determined by how they are used afterwards), and the objects were created before the storage was zeroed ([[c.malloc#4]]), so their values are 0. In C++17 and earlier, strictly by the standard there was no `int` object in this storage at all and the read was undefined behavior; [[P0593R6]] fixed this.
</details>
