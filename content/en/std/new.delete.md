---
title: Storage allocation and deallocation
summary: "The standard library's 22 global operator new / operator delete functions: what replacements must obey and what the default versions do, how the nothrow versions forward, why size and alignment at deallocation must match allocation, why the placement forms can't be replaced, and the synchronization guarantee between allocation and deallocation."
updated: 2026-10-19
---

!!! tldr
    - A program can replace the global `operator new` / `operator delete`. A replacement must meet the Required behavior: `operator new` either returns a non-null, suitably aligned pointer or throws `bad_alloc`.
    - The default `operator new` tries to allocate in a loop and calls the new_handler on failure; whether it is implemented with `malloc` is unspecified, so memory from `new` can't be handed to `free`.
    - The nothrow versions by default call the ordinary version and swallow the exception. If you replace only `operator new(size_t)`, `new (std::nothrow)` uses your version too.
    - The pointer, size and alignment passed at deallocation must all match those at allocation; single-object and array forms can't be mixed. When replacing an `operator delete` with a size parameter, you must also replace the version without one.
    - The placement form `operator new(size_t, void*)` can't be replaced, and since C++26 it is `constexpr`. A deallocation of a given unit of storage happens before the next allocation of it, and replacements must guarantee this too.

## Replacing the global `operator new`

```cpp run title="replace-new.cpp" ok
#include <cstdio>
#include <cstdlib>
#include <new>

void* operator new(std::size_t n) {
  std::printf("my operator new(%zu)\n", n);
  if (void* p = std::malloc(n ? n : 1)) return p;
  throw std::bad_alloc();
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }

int main() {
  int* p = new (std::nothrow) int(1);  // prints: my operator new(4)
  delete p;
}
```

Defining a global function with the same signature in a program replaces the library's version, and every `new` in the whole program uses it ([[dcl.fct.def.replace]]). This example also demonstrates two rules covered below: the nothrow version by default calls your replacement `operator new(size_t)`; and `malloc(0)` may return a null pointer, so a zero-byte request is changed to at least 1 byte.

The library clauses describe these functions with two kinds of wording ([[structure.specifications]]):

- **Required behavior** ([[g:required-behavior]]) is a contract binding on replacements too; the wording says "This requirement is binding on any replacement versions of these functions". If a replacement violates it, the program's behavior is undefined ([[res.on.functions]]).
- **Default behavior** ([[g:default-behavior]]) describes only the library's own version. Once replaced, it no longer applies.

So a replacement may skip calling the new_handler and may avoid `malloc`, but it may not return a null pointer on failure.

## General [new.delete.general]

¶1 Unless otherwise specified, the requirements in [[basic.stc.dynamic]] on allocation and deallocation functions apply to the library versions as well. If an alignment argument passed to these functions isn't a valid alignment value (an integral power of two; see [[basic.align]]), the behavior is undefined, for example `::operator new(16, std::align_val_t(3))`.

¶2 On a freestanding implementation, it is implementation-defined whether the default versions meet the requirements below. Note 1 explains that calling them may lead to undefined behavior on platforms without a heap; during constant evaluation this doesn't matter, because calls to replaceable allocation functions are always omitted ([[expr.new]]). *Recommended practice*: if any default version meets the requirements of a hosted implementation, all of them should. The corresponding feature-test macro is `__cpp_lib_freestanding_operator_new`.

## Single-object forms [new.delete.single]

### The throwing `operator new` (¶1–¶4)

```cpp
void* operator new(std::size_t size);
void* operator new(std::size_t size, std::align_val_t alignment);
```

¶1 They are called by a *new-expression* to allocate `size` bytes. The second form is used for types with new-extended alignment (an alignment requirement exceeding `__STDCPP_DEFAULT_NEW_ALIGNMENT__`), the first otherwise.

¶2 Required behavior: return a non-null pointer to suitably aligned storage, or else throw a `bad_alloc` exception.

¶3 The default behavior is a loop:

1. Attempt the allocation. Whether the attempt involves a call to the C library's `malloc` or `aligned_alloc` is unspecified.
2. If it succeeds, return the pointer. On failure, if the current new_handler ([[get.new.handler]]) is a null pointer, throw `bad_alloc`.
3. Otherwise call the new_handler. If it returns, go back to step 1.
4. The loop ends when the allocation succeeds or the new_handler doesn't return (it throws or terminates the program).

The conventions for the new_handler are in [[alloc.errors]]. Paragraph 4 says these two functions are replaceable.

!!! note "Memory from `new` can't be released with `free`"
    Even if the default implementation on your platform happens to be `malloc`, the standard doesn't guarantee it. Releasing the result of `operator new` with `free`, or the result of `malloc` with `operator delete`, violates the preconditions in paragraph 10 below and is undefined behavior.

### The nothrow versions (¶5–¶9)

```cpp
void* operator new(std::size_t size, const std::nothrow_t&) noexcept;
void* operator new(std::size_t size, std::align_val_t alignment, const std::nothrow_t&) noexcept;
```

¶5 They are called by `new (std::nothrow) T`, for programs that prefer a null pointer result as the error indication. The example in paragraph 8 contrasts the two forms: `new T` throws `bad_alloc` on failure, while `new(nothrow) T` returns a null pointer.

¶6 Required behavior: return a non-null, suitably aligned pointer, or else a null pointer. Moreover, the pointer returned is as if acquired from the corresponding ordinary version (possibly replaced). So the result of `new (std::nothrow) T` can be released with an ordinary `delete`.

¶7 Default behavior: call `operator new(size)` or `operator new(size, alignment)`; if it returns normally, return its result, and if it throws, return a null pointer. This is why the nothrow version in the opening example calls the replacement function.

!!! pitfall "`new (std::nothrow) T` can still throw"
    nothrow covers only the allocation step. An exception thrown by `T`'s constructor still propagates, and the storage just allocated is released beforehand by the nothrow `operator delete` (paragraph 19 below).

### Deallocation functions (¶10–¶16)

```cpp
void operator delete(void* ptr) noexcept;
void operator delete(void* ptr, std::size_t size) noexcept;
void operator delete(void* ptr, std::align_val_t alignment) noexcept;
void operator delete(void* ptr, std::size_t size, std::align_val_t alignment) noexcept;
```

¶10–¶11 are preconditions, and violating any of them is undefined behavior:

- `ptr` is a null pointer, or an address returned by an earlier call to `operator new(size_t)` or `operator new(size_t, align_val_t)` that hasn't been deallocated yet;
- without an alignment parameter, `ptr` must come from an allocation function without an alignment parameter; with one, it must equal the alignment argument at allocation;
- with a size parameter, it must equal the size argument at allocation.

In other words, allocation and deallocation must pair up: memory allocated with alignment must be released with the aligned version, and the size passed must be the same as requested.

¶12 They are called by a *delete-expression* to render the value of `ptr` an invalid pointer value ([[g:invalid-pointer-value]]).

¶15 Default behavior: if `ptr` is null, do nothing; otherwise reclaim the storage. Paragraph 16 adds that it is unspecified when reclaimed storage is allocated again by later calls to `operator new`, `malloc` and so on.

¶13 Required behavior: a call to a version with a size parameter may be changed into a call to the version without one, without affecting memory allocation. Note 1 explains that an implementation may have `operator delete(ptr, size)` simply call `operator delete(ptr)`. The default behavior in paragraph 14 is exactly that: `size` is discarded, and only a replacement could make use of it.

### Replace them in pairs (¶16)

!!! std
    If a replacement function with a size parameter is defined by the program, the program shall also define the corresponding version without the size parameter.

The rule in ¶16 is asymmetric:

| You replaced | What the standard requires | Why |
|---|---|---|
| `operator delete(void*)`, without size | You should also replace the version with size | The default sized version currently forwards to yours, but Note 3 warns that the default behavior may change in the future |
| `operator delete(void*, size_t)`, with size | You shall also replace the version without size | ¶13 allows the implementation to turn a sized call into an unsized one, which would bypass your function |

!!! history "Sized deallocation and aligned allocation"
    The global `operator delete` with a `size_t` parameter was introduced in C++14 by [[N3778]]. Allocators such as tcmalloc and jemalloc manage memory by size class, and knowing the size at deallocation saves them a metadata lookup. The forms with `align_val_t` were introduced in C++17 by [[P0035R4]]; before that, `new` on an `alignas(64)` type could only get memory with fundamental alignment. The corresponding feature-test macros are `__cpp_sized_deallocation` and `__cpp_aligned_new`.

### nothrow deallocation functions (¶17–¶21)

```cpp
void operator delete(void* ptr, const std::nothrow_t&) noexcept;
void operator delete(void* ptr, std::align_val_t alignment, const std::nothrow_t&) noexcept;
```

A `delete` expression can't pass placement arguments, so it never calls these two functions.

¶19 The implementation calls them in only one case: the constructor in `new (std::nothrow) T` throws an exception and the storage just allocated must be released (the matching deallocation function in [[expr.new]]). Paragraph 20 says the default behavior is to call `operator delete(ptr)` or `operator delete(ptr, alignment)`.

## Array forms [new.delete.array]

The eight array signatures correspond one to one to the single-object forms, with the same Required behavior, and their default behaviors all forward to the single-object forms:

| Function | Default behavior |
|---|---|
| `operator new[](size)` / `(size, al)` | ¶3 returns `operator new(size)` / `operator new(size, al)` |
| nothrow `operator new[]` | ¶7 calls `operator new[](size)` / `(size, al)`, returning a null pointer if it throws |
| The four forms of `operator delete[]` | ¶13 the sized forms forward to the unsized ones, and the unsized ones to the single-object `operator delete` |
| nothrow `operator delete[]` | ¶18 calls `operator delete[](ptr)` / `(ptr, al)` |

The precondition in ¶9 requires `ptr` to come from `operator new[]`. So even though the default implementations forward to each other, single-object and array forms can't be mixed: `delete` on a pointer obtained from `new[]` is undefined behavior.

```cpp run title="array-cookie.cpp" impl
#include <cstdio>
#include <cstdlib>
#include <new>

void* operator new[](std::size_t n) {
  std::printf("operator new[](%zu)\n", n);
  if (void* p = std::malloc(n)) return p;
  throw std::bad_alloc();
}
void operator delete[](void* p) noexcept { std::free(p); }
void operator delete[](void* p, std::size_t) noexcept {
  std::free(p);
}

struct Trivial    { int x; };
struct NonTrivial { int x; ~NonTrivial() {} };

int main() {
  delete[] new Trivial[4];     // 16
  delete[] new NonTrivial[4];  // 32 in our tests: 16 extra bytes of cookie
}
```

Footnote 168 explains that remembering how many elements an array has isn't the job of `operator new[]` but of the *new-expression* and *delete-expression*. An array *new-expression* may request extra space and store the element count in front of the array; this space is called the **array cookie**. `delete[]` uses it to call the destructor the right number of times, so it is needed only when the element type has a non-trivial destructor.

On AArch64 macOS the cookie is 16 bytes, recording the element size and count; the x86-64 Itanium ABI usually uses only 8 bytes to record the count, where the second line would print 24. In any case, the `size` passed to `operator new[]` may be larger than `n * sizeof(T)` ([[expr.new]]).

## Placement forms [new.delete.placement]

```cpp
constexpr void* operator new  (std::size_t size, void* ptr) noexcept;
constexpr void* operator new[](std::size_t size, void* ptr) noexcept;
constexpr void  operator delete  (void* ptr, void*) noexcept;
constexpr void  operator delete[](void* ptr, void*) noexcept;
```

¶2–¶6 The two `operator new`s simply return `ptr` and intentionally perform no other action. `new (place) T(...)` uses them to construct an object at a known address.

¶7–¶10 The two `operator delete`s do nothing; they are what is called when the initialization in a placement *new-expression* throws an exception.

¶1 These four functions are reserved, and a program may not define its own versions to displace them ([[constraints]]). They don't allocate memory, so the requirements of [[basic.stc.dynamic]] don't apply to them.

!!! pitfall "A placement `operator new` in a class hides the global version"
    Declaring `operator new(size_t, void*)` in class scope is allowed; it is an allocation function specific to that class and makes that class's `new (buf) T` call your version. That is why standard containers always write `::new (p) T(...)`, using `::` to skip class-scope lookup.

C++26 made these four functions `constexpr` ([[P2747R2]]), so placement new can construct objects during constant evaluation. `std::inplace_vector` and the `constexpr` version of `std::optional` both depend on this. The core language has further restrictions, such as the pointer having to point to storage of a suitable type ([[expr.const]]).

```cpp run title="constexpr-placement.cpp" ok
#include <memory>
#include <new>

constexpr int f() {
  std::allocator<int> a;
  int* p = a.allocate(1);
  int* q = ::new (p) int(42);   // usable during constant evaluation since C++26
  int r = *q;
  std::destroy_at(q);
  a.deallocate(p, 1);
  return r;
}
static_assert(f() == 42);

int main() {}
```

Clang 23 accepts this code with `-std=c++2c` and rejects the `static_assert` with `-std=c++23`.

## Synchronization between allocation and deallocation [new.delete.dataraces]

Thread A finishes writing an object and `delete`s it; thread B then `new`s an object, happens to get the same memory, and writes to it. There is no other synchronization between the two threads. Without an additional rule, A's writes and B's writes would form a data race.

¶1 specifies two things. First, the library versions and replacements of `operator new` / `operator delete`, as well as the C library's `aligned_alloc`, `calloc`, `malloc`, `free` and `realloc`, shall not introduce a data race ([[res.on.data.races]]). Second:

!!! std
    Calls to these functions that allocate or deallocate a particular unit of storage shall occur in a single total order, and each such deallocation call shall happen before the next allocation (if any) in this order.

Allocations and deallocations of the same unit of storage form a total order, and each deallocation happens before the next allocation ([[intro.races]]). So A's writes before the deallocation happen before B's writes after the allocation, and the scenario above has no data race.

This rule constrains replacements too. A hand-written lock-free memory pool must provide this happens-before relation, which generally means release semantics on deallocation and acquire semantics on allocation.

## Questions

!!! question "Question 1"
    What does this replacement violate?
    ```cpp
    void* operator new(std::size_t n) { return std::malloc(n); }
    ```

<details markdown="1">
<summary>Answer</summary>

It violates the Required behavior in paragraph 2: on failure it must throw `bad_alloc`, but `malloc` returns a null pointer on failure. In addition, `malloc(0)` may return a null pointer, violating [[basic.stc.dynamic.allocation]]'s requirement that even a zero-byte request return a unique non-null pointer.

The Required behavior binds replacements, so such a program has undefined behavior. Compilers really do exploit this: when the allocation function doesn't have a non-throwing exception specification, the result of the *new-expression* can't be a null pointer, and later null checks can be removed ([[expr.new]]).
</details>

!!! question "Question 2"
    A program replaces only `operator new(size_t)` and no `operator delete`. Does `delete new int` work correctly?

<details markdown="1">
<summary>Answer</summary>

Not necessarily. `delete` calls the library's default `operator delete`, which reclaims storage allocated by your `operator new`. Whether it works depends on whether the two happen to use the same underlying allocator. libc++'s default implementation is based on `malloc` / `free`, so it happens to work if the replacement also uses `malloc`, but that isn't guaranteed by the standard. The portable approach is to always replace the corresponding `operator delete`, including the sized versions, whenever you replace `operator new`.
</details>
