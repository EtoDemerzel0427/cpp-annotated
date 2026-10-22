---
title: Deprecated atomic operations (D.24)
summary: "The four kinds of deprecated facility in <atomic>: volatile member functions of atomic types that aren't lock-free, atomic_init, ATOMIC_VAR_INIT, and memory_order::consume and kill_dependency, which are now equivalent to acquire."
updated: 2026-10-19
---

!!! tldr
    - `memory_order::consume` can still be written, but it means exactly the same as `acquire`. The original dependency-chain semantics were never implemented by any compiler and have been removed from the main text.
    - `kill_dependency(y)` is now just an identity function returning `y`, and can simply be deleted.
    - Since C++20 the default constructor of `std::atomic<T>` value-initializes, so the two C-compatible means of initialization, `atomic_init` and `ATOMIC_VAR_INIT`, are no longer needed.
    - The main text specifies that only lock-free atomic types have usable `volatile` member functions; using them on types that aren't lock-free is still allowed, but deprecated.

**Deprecated** features are still normative; they have just been identified as candidates for possible future removal, and implementations may add `[[deprecated]]` to these names ([[depr.general#2]]). The test environment for this page is Clang 23.1.3 with libc++.

## D.24.1 General {#depr.atomics.general}

¶1 `<atomic>` additionally provides the following declarations, of which `kill_dependency` and `memory_order_consume` must also be provided in freestanding implementations:

```cpp
namespace std {
  template<class T>
    void atomic_init(volatile atomic<T>*, typename atomic<T>::value_type) noexcept;
  template<class T>
    void atomic_init(atomic<T>*, typename atomic<T>::value_type) noexcept;
  template<class T>
    constexpr T kill_dependency(T y) noexcept;
  inline constexpr memory_order memory_order_consume = memory_order::consume;

  #define ATOMIC_VAR_INIT(value) see below
}
```

## D.24.5 `memory_order::consume` {#depr.atomics.order}

```cpp
#include <atomic>
struct Node { int payload; };
std::atomic<Node*> head;

int reader() {
  Node* p = head.load(std::memory_order_consume);  // equivalent to acquire
  return p->payload;
}
```

¶1 The `memory_order` enumeration additionally has the enumerator `consume = 1`. `memory_order::consume` is allowed wherever `memory_order::acquire` is allowed, and the two mean the same thing.

¶2 `kill_dependency(y)` returns `y`.

### What consume was originally designed to be

In C++11, `consume` was acquire semantics weaker than `acquire`. `acquire` guarantees that all the publisher's writes before the release are visible to all of the acquirer's subsequent operations. `consume` gives this guarantee only for subsequent operations that depend on the value read through data dependencies. In the example above, `p->payload` depends on `p`, so it sees the `payload` written by the publisher.

This was designed for RCU-style pointer publication. On weakly ordered architectures like ARM and POWER, the hardware already guarantees that accesses depending on the result of a load aren't reordered before that load, so `consume` needs no barrier instruction, whereas `acquire` does. `kill_dependency` tells the compiler that the dependency chain ends here, so the code after it can be optimized freely.

### Why it was never implemented

For `consume` to really avoid barriers, the compiler has to track dependency chains through the entire optimization pipeline, forbidding any transformation that might break a dependency. For example, if the compiler discovers that `p` can only be some known address, it must not replace `p->payload` with a direct access to that address. Dependency chains also pass through function calls, for which the `[[carries_dependency]]` attribute was introduced.

None of the mainstream compilers did this tracking; GCC, Clang and MSVC have always treated `consume` as `acquire`. The current draft acknowledges this: the main text has removed the concepts of "carries a dependency", "dependency-ordered before" and so on (see [[intro.races]]), the `[[carries_dependency]]` attribute has been removed too, and only the enumerator is kept here for compatibility with old code ([[P3475R2]]).

libc++ gives no warning for `memory_order_consume` or `kill_dependency`. Just use `memory_order::acquire` instead; the generated code is the same as before. Calls to `kill_dependency` can simply be deleted.

## D.24.3 The non-member function `atomic_init` {#depr.atomics.nonmembers}

```cpp
#include <atomic>
std::atomic<int> ai;
void f() { std::atomic_init(&ai, 1); }  // deprecated
```

¶1 `atomic_init(object, desired)` is equivalent to `atomic_store_explicit(object, desired, memory_order::relaxed)`.

`atomic_init` comes from the compatibility interface of C11's `<stdatomic.h>`. Before C++20, the default constructor of `std::atomic<T>`, like C's `_Atomic`, didn't initialize the value, and `atomic_init` was needed to supply the initialization. At the time this step wasn't an atomic operation, so concurrent access from other threads constituted a data race. C++20 made the default constructor value-initialize the value, so `std::atomic<int> a;` has the value 0 ([[P0883R2]]), and `atomic_init` became unnecessary. The current draft defines it as a `relaxed` store, eliminating the risk of a data race.

libc++ warns from `-std=c++20` on. The replacement is to initialize directly at construction, `std::atomic<int> ai{1};`; for an object that is already constructed, write `ai.store(1, std::memory_order::relaxed)`.

## D.24.4 `ATOMIC_VAR_INIT` {#depr.atomics.types.operations}

<div class="compare" markdown="1">

```cpp
#include <atomic>
// deprecated
std::atomic<int> v = ATOMIC_VAR_INIT(5);
```

```cpp
#include <atomic>
// replacement
std::atomic<int> w{5};
```

</div>

¶1 `ATOMIC_VAR_INIT(value)` expands to a token sequence suitable for constant initialization of an atomic variable of static storage duration whose type can be initialized from `value`. Note 1 points out that this operation may need to initialize locks. Concurrent access to the variable being initialized, even through an atomic operation, constitutes a data race.

This macro too comes from C. C's `_Atomic` types have no constructors, so static atomic variables needed a macro to provide the initial value; C17 has already marked it obsolescent. C++'s `std::atomic<T>` has a `constexpr` constructor, and `std::atomic<int> w{5};` is itself constant initialization.

libc++ warns from `-std=c++20` on, with the diagnostic `macro 'ATOMIC_VAR_INIT' has been marked as deprecated [-Wdeprecated-pragma]`. A macro isn't a declaration and can't be marked `[[deprecated]]`; libc++ uses Clang's `#pragma clang deprecated(ATOMIC_VAR_INIT)`, which is why the warning option isn't `-Wdeprecated-declarations`.

## D.24.2 `volatile` access {#depr.atomics.volatile}

```cpp
#include <atomic>
struct Big { int a[16]; };
volatile std::atomic<Big> vb;  // Big is too large to be lock-free
Big f() {
  return vb.load();  // deprecated
}
```

A **lock-free** atomic type is implemented without locks; `atomic<T>::is_always_lock_free` being `true` means the type is always lock-free. The main text, [[atomics.types.operations]], constrains the `volatile` overload of every member function: the overload is usable only when `is_always_lock_free` is `true`.

¶1 This subclause relaxes that constraint. The `volatile` versions of `store`, `operator=`, `load`, `operator T`, `exchange`, `compare_exchange_weak`, `compare_exchange_strong`, `fetch_key`, the compound assignments, `++`, `--`, `wait`, `notify_one` and `notify_all` in the `atomic` specializations participate in overload resolution even if `is_always_lock_free` is `false`. The combined effect of the two provisions is:

| | `is_always_lock_free` is `true` | `is_always_lock_free` is `false` |
|---|---|---|
| Member functions of `volatile atomic<T>` | Normal use | Usable, but deprecated |

`volatile` means every access must really happen and can't be merged or removed, which is useful for memory mapped to hardware or shared with signal handlers. An atomic type that isn't lock-free is implemented internally with locks, usually a global table of locks. The locks themselves aren't `volatile`, and they can't safely be acquired in a signal handler either, so `volatile` access through locks has no consistent meaning.

libc++ neither constrains the `volatile` overloads nor marks them deprecated, so the example above gives no warning under either `-std=c++20` or `-std=c++2c`. The replacement is to remove `volatile`; when you really need `volatile` semantics, ensure the type is lock-free with `static_assert(std::atomic<T>::is_always_lock_free)`.

## Summary

| Subclause | Feature | Why deprecated | Instead | libc++ warning |
|---|---|---|---|---|
| D.24.5 | `consume`, `kill_dependency` | No compiler implemented dependency tracking | `acquire` | None |
| D.24.3 | `atomic_init` | Since C++20 default construction value-initializes | Initialize at construction, or `store(relaxed)` | Since C++20 |
| D.24.4 | `ATOMIC_VAR_INIT` | `atomic` has a `constexpr` constructor | `std::atomic<T> v{x};` | Since C++20 (`-Wdeprecated-pragma`) |
| D.24.2 | `volatile` members of `atomic` types that aren't lock-free | A lock-based implementation is incompatible with `volatile` semantics | Remove `volatile` | None |
