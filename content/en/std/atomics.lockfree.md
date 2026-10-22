---
title: Lock-free property
summary: "How to tell whether an atomic type is really lock-free: the 0, 1 and 2 of the ATOMIC_*_LOCK_FREE macros, is_always_lock_free and is_lock_free; what atomic operations that are not lock-free mean for signal handlers and progress guarantees; address-free operations and shared memory between processes; with measurements of various types on Apple Silicon."
updated: 2026-10-19
---

!!! tldr
    - `std::atomic<T>` is usable for any trivially copyable `T`; sizes the hardware cannot handle are emulated by the implementation with locks, so atomic does not mean lock-free.
    - Query at compile time with `atomic<T>::is_always_lock_free` or the `ATOMIC_*_LOCK_FREE` macros (0 never, 1 sometimes, 2 always); within one execution, all atomic objects of the same type have the same lock-free property.
    - A hosted implementation has at least one pair of signed and unsigned integer atomic types that are always lock-free; a freestanding implementation guarantees only `atomic_flag`.
    - Atomic operations that are not lock-free are considered potentially blocking: they cannot be used in signal handlers, and their progress guarantees cannot be relied on.
    - Putting atomic objects in memory shared between processes relies on the recommendation that lock-free operations be address-free; the standard itself does not guarantee atomicity across processes.

## Atomic does not mean lock-free

```cpp run title="lockfree-table.cpp" ok
#include <atomic>
#include <cstdio>

struct P2  { void* a; void* b; };   // 16 bytes
struct S12 { int a, b, c; };        // 12 bytes
struct S32 { long a[4]; };          // 32 bytes

#define SHOW(T) std::printf("%-12s sizeof(atomic) %2zu  alignof %2zu  always_lock_free %d\n", #T, \
  sizeof(std::atomic<T>), alignof(std::atomic<T>), (int)std::atomic<T>::is_always_lock_free)

int main() {
  SHOW(bool); SHOW(long long); SHOW(long double); SHOW(P2); SHOW(S12); SHOW(S32);
  std::printf("atomic_ref<S12>: required_alignment %zu  always_lock_free %d\n",
              std::atomic_ref<S12>::required_alignment, (int)std::atomic_ref<S12>::is_always_lock_free);
}
```

Output on Apple Silicon + libc++:

| Type | `sizeof(atomic<T>)` | `alignof` | Always lock-free |
|---|---|---|---|
| `bool` | 1 | 1 | 1 |
| `long long` | 8 | 8 | 1 |
| `long double` (same as `double` on this platform) | 8 | 8 | 1 |
| `P2` (16 bytes) | 16 | 16 | 1 |
| `S12` (12 bytes) | 16 | 16 | 1 |
| `S32` (32 bytes) | 32 | 8 | 0 |

`std::atomic<T>` can be used for any trivially copyable `T`, including structs of 32 bytes or even larger. The hardware has no atomic instructions that wide, so the implementation emulates them with locks. libc++ hands the operations of `atomic<S32>` to functions such as `__atomic_load` in the compiler runtime library, which implement them with a table of locks hashed by address.

Two more points in the table are worth noting:

- `atomic<S12>` is padded to 16 bytes and aligned to 16 bytes, so 16-byte atomic instructions can be used. [[atomics.types.generic.general#3]] Note 2 allows this: the representation of an `atomic` specialization need not have the same size and alignment as its argument type.
- For the same `S12`, `atomic_ref<S12>` has a `required_alignment` of only 4 and is not lock-free. An `atomic_ref` cannot change the size of the referenced object, and there is no atomic instruction for a 12-byte object. So `atomic_ref<T>` and `atomic<T>` can differ in lock-free property.

## Compile-time queries: macros and is_always_lock_free (¶1)

`<atomic>` defines 11 macros: `ATOMIC_BOOL_LOCK_FREE`, `ATOMIC_CHAR_LOCK_FREE`, `ATOMIC_CHAR8_T_LOCK_FREE`, `ATOMIC_CHAR16_T_LOCK_FREE`, `ATOMIC_CHAR32_T_LOCK_FREE`, `ATOMIC_WCHAR_T_LOCK_FREE`, `ATOMIC_SHORT_LOCK_FREE`, `ATOMIC_INT_LOCK_FREE`, `ATOMIC_LONG_LOCK_FREE`, `ATOMIC_LLONG_LOCK_FREE`, `ATOMIC_POINTER_LOCK_FREE`.

¶1 These macros indicate the lock-free property of the corresponding atomic types, with signed and unsigned variants grouped together, and apply to the corresponding specializations and partial specializations of the `atomic` template. A value of 0 means never lock-free, 1 sometimes lock-free, 2 always lock-free.

The "sometimes lock-free" category exists because the same binary may run on different CPUs. Early x86-64 processors, for example, lack the 16-byte compare-exchange instruction `cmpxchg16b`. The macros are preprocessor constants and can be used in `#if`.

`atomic<T>`'s `static constexpr bool is_always_lock_free` ([[atomics.types.operations#4]]) being `true` means the type's operations are lock-free in every execution environment. Note 2 says it is consistent with the corresponding macro, if any. It works for any `T`, while the macros cover only built-in types.

## A hosted implementation has at least one lock-free integer (¶2)

¶2 On a hosted implementation (a complete implementation with operating system support), at least one signed integral specialization of `atomic`, along with the corresponding unsigned type, is always lock-free.

This guarantee goes together with the two aliases `atomic_signed_lock_free` and `atomic_unsigned_lock_free` ([[atomics.alias]]), so portable code can always find a lock-free integer. Freestanding implementations have no such guarantee; there, the only type guaranteed lock-free is `atomic_flag` ([[atomics.flag#2]]).

## Run-time queries (¶3)

¶3 `atomic<T>::is_lock_free()` and `atomic_is_lock_free` report whether an object is lock-free ([[atomics.types.operations]]). In any given program execution, the result of the query is the same for all atomic objects of the same type.

The second sentence rules out implementations that decide lock-freedom by an object's address or alignment; `is_lock_free()` is really a property of the type in this execution. `atomic_ref` is the same: its `is_lock_free()` is specified for all objects of the type ([[atomics.ref.ops#4]]), and to that end it requires the referenced object to be aligned to `required_alignment`.

## Operations that are not lock-free may block (¶4)

¶4 Atomic operations that are not lock-free are considered to potentially block ([[intro.progress]]).

This sentence connects the atomics library with progress guarantees. [[intro.progress#2]] specifies that executions of atomic functions that are either defined to be lock-free (`atomic_flag`) or indicated to be lock-free per this subclause are **lock-free executions** ([[g:lock-free-execution]]): if only one thread is not blocked in a standard library function, a lock-free execution in that thread shall complete. Atomic operations that are not lock-free have no such guarantee. There are two practical consequences:

- In a signal handler, the only standard library calls that may be used are **plain lock-free atomic operations** ([[g:plain-lock-free-atomic-operation]]) and functions explicitly marked signal-safe ([[support.signal#2]], [[support.signal#3]]). If a signal happens to interrupt an atomic operation holding an internal lock, the handler operating on the same object would wait on itself.
- In execution agents that provide only weakly parallel forward progress guarantees, such as element access functions called by `par_unseq` parallel algorithms ([[algorithms.parallel]]), using potentially blocking operations may deadlock.

## Address-free operations and sharing between processes (¶5)

¶5 *Recommended practice*: operations that are lock-free should also be address-free, i.e., atomic operations on the same memory location via two different addresses communicate atomically (footnote 273). The implementation should not depend on any per-process state. Note 1 explains that this permits communication through memory mapped into a process more than once, and through memory shared between two processes.

This is the basis for putting `std::atomic` into shared memory with `mmap` or `shm_open`. Only lock-free atomic types are suitable for this: for atomic operations implemented with locks, the lock table is usually in process-private memory, and two processes cannot see each other's locks. ¶5 is only a recommendation; the standard itself does not guarantee atomicity across processes.

!!! pitfall "`wait` and `notify` across processes"
    An atomic object being address-free does not mean its `wait` and `notify_one` work across processes too. libc++'s waiting mechanism ([[atomics.wait]]) uses an in-process global wait table for most types, and a `notify_one` from another process cannot wake it.

## The implementation's view

!!! impl "16-byte atomics"
    Apple Silicon supports ARMv8.1's LSE (the `casp` family of instructions) and ARMv8.4's LSE2 (16-byte aligned `ldp` and `stp` are single-copy atomic), so `is_always_lock_free` is `true` for 16-byte types. In the example above, `atomic<P2>::load()` is implemented with `ldp`, and `compare_exchange_strong` compiles to `caspal`. On x86-64, 16-byte atomics need `cmpxchg16b`, which not all x86-64 processors have, and compilers and runtime libraries handle this differently (assuming it at compile time, detecting it at run time, or always reporting not lock-free).
