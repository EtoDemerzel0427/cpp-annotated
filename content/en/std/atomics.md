---
title: Atomic operations
summary: "The entry point to 32.5: what atomic objects are, what <atomic> declares, how the atomic_xxx non-member functions and <stdatomic.h> let one header be compiled as both C and C++, and the atomic_signed_lock_free alias."
updated: 2026-10-19
---

!!! tldr
    - Atomic objects are objects of `atomic<T>` and `atomic_flag`, plus objects while they are referenced by some `atomic_ref`. Access to them solely through atomic operations never forms a data race, but their initialization is not an atomic operation.
    - Non-member functions such as `atomic_fetch_add(&a, 1)` are exactly equivalent to the member functions; they exist so that C and C++ can share code.
    - C++'s `<stdatomic.h>` defines `_Atomic(T)` as `std::atomic<T>` and brings the C names into the global namespace; representation compatibility between C and C++ atomic objects is only recommended practice.
    - `atomic_signed_lock_free` and `atomic_unsigned_lock_free` name an integer atomic type that is always lock-free and for which waiting/notifying is most efficient.

## Atomic objects [atomics.general]

[[intro.races]] specifies that if two threads access the same memory location in conflicting ways, at least one access is not atomic, and there is no happens before between them, that is a data race, and the behavior of the whole program is undefined. So to let several threads share a variable without locks, you must use atomic objects and atomic operations.

¶2 This subclause describes components for fine-grained atomic access, provided via operations on **atomic objects**. Atomic objects come from two sources:

- objects of type `atomic<T>` and `atomic_flag`;
- ordinary objects referenced by an `atomic_ref`, which are atomic objects during the lifetime of that `atomic_ref` ([[atomics.ref.generic#1]]).

If all accesses to an atomic object go through atomic operations, there is no data race. The one exception is initialization: [[atomics.types.operations#2]] specifies that the initialization of an atomic object is not an atomic operation. If the address of a just-constructed object is passed to another thread through a relaxed atomic operation and that thread accesses it immediately, it may still race with the construction.

¶1 defines an exposition-only alias *COPYCV*`(FROM, TO)`, meaning `TO` with the top-level cv-qualifiers of `FROM` added, used for return types such as `atomic_ref<const T>::address()` that need to preserve cv-qualification.

The remaining subclauses of this chapter:

| Page | Contents |
|---|---|
| [[atomics.order]] | The semantics of `memory_order`: release/acquire, the single total order S, read-modify-write |
| [[atomics.lockfree]] | `ATOMIC_*_LOCK_FREE`, `is_always_lock_free`, sharing across processes |
| [[atomics.wait]] | `wait`, `notify_one`, `notify_all` |
| [[atomics.ref.generic]] | `atomic_ref<T>` |
| [[atomics.types.generic]] | `atomic<T>` and its integral, floating-point and pointer specializations |
| [[util.smartptr.atomic]] | `atomic<shared_ptr<T>>`, `atomic<weak_ptr<T>>` |
| [[atomics.flag]] | `atomic_flag` |
| [[atomics.fences]] | `atomic_thread_fence`, `atomic_signal_fence` |

## What `<atomic>` contains [atomics.syn]

The synopsis of `<atomic>` is marked mostly freestanding: apart from `atomic_signed_lock_free` and `atomic_unsigned_lock_free`, which are marked hosted, everything must also be provided in a freestanding implementation (one that may lack operating system support). It declares:

- `enum class memory_order` and five inline constants such as `memory_order_relaxed`. `memory_order` has been a scoped enumeration since C++20; the constants are kept for compatibility with old code and C. `memory_order_consume` is not here; it is in Annex D ([[depr.atomics]]).
- 11 macros from `ATOMIC_BOOL_LOCK_FREE` to `ATOMIC_POINTER_LOCK_FREE` ([[atomics.lockfree]]).
- The class templates `atomic_ref` and `atomic`, and the partial specialization `atomic<T*>`.
- A set of `atomic_xxx` and `atomic_xxx_explicit` non-member function templates, each with two overloads taking `volatile atomic<T>*` and `atomic<T>*`.
- Type aliases from `atomic_bool` to `atomic_uintmax_t` and so on, `atomic_flag` and its non-member functions, and `ATOMIC_FLAG_INIT`.
- The fence functions `atomic_thread_fence` and `atomic_signal_fence`, declared `extern "C"` so that C and C++ use the same entity, which is what lets `<stdatomic.h>` bring them in with using-declarations.

In the non-member functions, the parameters representing values are written `typename atomic<T>::value_type` rather than `T`. This is deliberate: the part left of `::` is a non-deduced context, so `T` is deduced only from the first argument. So `atomic<long> a; atomic_store(&a, 1);` compiles, with `1` implicitly converted to `long`; if the parameter were written `T`, the two arguments would deduce `long` and `int` respectively, and deduction would fail.

Almost all atomic operations are declared `constexpr`; this is post-C++23 wording ([[P3309R3]]). There is no concurrency during constant evaluation, so atomic operations are just ordinary reads and writes, and `atomic<T>` can be used in `constexpr` functions.

!!! impl "libc++ does not yet implement constexpr atomic operations"
    In the libc++ shipped with Clang 23, members of `atomic<T>` such as `load` and `fetch_add` are not `constexpr`, and calling them in a constant expression is an error.

## Non-member functions [atomics.nonmembers]

¶1 A non-member function template whose name has the form `atomic_f` or `atomic_f_explicit` calls the member function `f`, with the first argument as the object and the remaining arguments passed in order to the member function. A parameter of type `atomic<T>::value_type*` is dereferenced before being passed; this corresponds to the `expected` of `compare_exchange`. If there is no corresponding member function, the program is ill-formed.

So `atomic_fetch_add_explicit(&a, 1, memory_order_relaxed)` is exactly equivalent to `a.fetch_add(1, memory_order::relaxed)`. ¶2 Note 1 gives the reason for their existence: C has no member functions, and with these names programmers can write code that compiles both as C and as C++, for example shared headers.

## C compatibility: `<stdatomic.h>` [stdatomic.h.syn]

```cpp run title="stdatomic-shared.cpp" ok
// the following goes in a header shared by C and C++
#include <stdatomic.h>
typedef struct { _Atomic(int) hits; } counter;
static inline void bump(counter* c) {
  atomic_fetch_add_explicit(&c->hits, 1, memory_order_relaxed);
}

// C++ side
#include <type_traits>
static_assert(std::is_same_v<_Atomic(int), std::atomic<int>>);
int main() {
  counter c{};
  bump(&c);
  return atomic_load(&c.hits) == 1 ? 0 : 1;
}
```

In our tests the shared part also compiles and runs as C code with `clang -std=c23`.

C11 introduced the type qualifier `_Atomic` and the header `<stdatomic.h>`. Since C++23, C++'s `<stdatomic.h>` provides:

- the macro `_Atomic(T)`, which expands to `std::atomic<T>` (via an exposition-only alias);
- all the `ATOMIC_*_LOCK_FREE` macros and `ATOMIC_FLAG_INIT`;
- a set of using-declarations that bring `std::memory_order`, constants such as `memory_order_relaxed` (including `memory_order_consume`), `atomic_flag`, aliases such as `atomic_int`, functions such as `atomic_load`, and the two fence functions into the global namespace.

¶1 Each using-declaration brings in the same entity as in `<atomic>`, and the macros other than `_Atomic(T)` are defined the same as in `<atomic>`. Whether `<stdatomic.h>` also provides the declarations in `std` is unspecified. ¶2 The using-declarations corresponding to `intN_t`, `uintN_t`, `intptr_t` and `uintptr_t` are provided only if `<atomic>` declares the corresponding aliases.

¶3 The `_Atomic` macro and these global declarations are provided only by `<stdatomic.h>`; no other C++ standard library header provides them.

¶4 *Recommended practice*: implementations should ensure that C and C++ atomic objects have compatible representations, so that the same object can be accessed as `_Atomic(T)` from C code and as `atomic<T>` from C++ code. This is only a recommendation, not a requirement.

In C++, `_Atomic` is a macro and can only be written in function form, `_Atomic(T)`. The C qualifier form `_Atomic int x;` is not standard C++.

!!! pitfall "`_Atomic` when only `<atomic>` is included"
    Per ¶3, `_Atomic(int)` should not be available when only `<atomic>` is included. Clang accepts it anyway, because in C++ Clang treats `_Atomic` as a C11 extension keyword (warning with `-Wc11-extensions` under `-pedantic`). What you get then is Clang's built-in atomic type, not `std::atomic<int>`, and the `static_assert` in the example above would fail. Shared headers should include `<stdatomic.h>`.

## Type aliases [atomics.alias]

¶1 `atomic_intN_t` and `atomic_uintN_t` are declared if and only if `intN_t` and `uintN_t` exist.

¶2 `atomic_signed_lock_free` and `atomic_unsigned_lock_free` name specializations of `atomic` for some signed and unsigned integral type respectively, whose `is_always_lock_free` is `true`. Note 1 says they are optional in freestanding implementations. Implementations should choose the integral type for which atomic waiting and notifying operations ([[atomics.wait]]) are most efficient.

This pair of aliases comes from C++20's synchronization library ([[P1135R6]]). The native waiting mechanisms on different platforms support different integer widths; Linux's futex, for example, supports only 32 bits. When portable code needs the atomic integer that waits fastest, it uses this alias.

!!! impl "libc++'s choice"
    libc++ prefers the integer type used by the platform's waiting mechanism, and otherwise picks the largest lock-free integer. In the default configuration, on macOS it is `int64_t`, so `atomic_signed_lock_free` is an 8-byte `atomic<long long>`; on Linux it is `int32_t`, corresponding to `atomic<int>` (see `<__atomic/aliases.h>`, `<__atomic/contention_t.h>`).

## Related content in Annex D

[[depr.atomics]] retains a few deprecated facilities {{deprecated}}:

- `atomic_init(obj, v)`, equivalent to `atomic_store_explicit(obj, v, memory_order::relaxed)`;
- `ATOMIC_VAR_INIT(value)`, unnecessary since C++20 because the default constructor of `atomic<T>` value-initializes;
- `memory_order::consume` and `kill_dependency`; `consume` can be used wherever `acquire` is allowed and means the same as `acquire` (see [[atomics.order]]);
- operations on `volatile atomic<T>`: the main text says these overloads are available only when `is_always_lock_free` is `true`, and Annex D lets them participate in overload resolution when `is_always_lock_free` is `false`, but such use is deprecated.
