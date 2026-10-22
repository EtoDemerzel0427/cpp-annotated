---
title: Class template atomic
summary: "The rules of std::atomic<T>: the requirements on T, why initialization is not an atomic operation, compare_exchange comparing value representations, spurious failure of weak CAS, and the arithmetic semantics of the integral, floating-point and pointer specializations."
updated: 2026-10-19
---

!!! tldr
    - `atomic<T>` requires `T` to be trivially copyable and cv-unqualified, otherwise the program is ill-formed; atomic objects are neither copyable nor movable.
    - Construction (including default construction, which value-initializes since C++20) is not an atomic operation. Handing a newly created atomic object to other threads still needs release/acquire.
    - `compare_exchange` compares value representations, not `==`: `+0.0` and `-0.0` compare unequal, and padding bits should be ignored per the standard.
    - Atomic integer arithmetic wraps around: `INT_MAX` plus 1 gives `INT_MIN`, with no UB; atomic pointer arithmetic out of bounds gives a determinate address, also without UB.
    - `a = a + 1` is a load plus a store and is not atomic; use `++a`, `a += 1` or `fetch_add`.

## The primary template [atomics.types.generic.general]

The primary template of `std::atomic<T>` provides `load`, `store`, `exchange`, `compare_exchange` and `wait`/`notify` for any trivially copyable `T`. The integral, floating-point and pointer specializations add arithmetic; the partial specializations for `shared_ptr`/`weak_ptr` are in [[util.smartptr.atomic]].

Every operation has two overloads: one `volatile`, one non-`volatile` and `constexpr`. The copy constructor and copy assignment are deleted, so atomic objects are neither copyable nor movable. Copying the value of an atomic object takes a load and a store, which together are not atomic, and the standard does not let it look as if it were.

### Requirements on T (¶1)

```cpp title="atomic-requirements.cpp" error
#include <atomic>
#include <string>
std::atomic<std::string> s;    // error: not trivially copyable (¶1.1)
std::atomic<const int> c{0};   // error: T is cv-qualified (¶1.6)
```

¶1 `T` shall meet *Cpp17CopyConstructible* and *Cpp17CopyAssignable*. If any of the following is `false`, the program is ill-formed {{ill-formed}}: `is_trivially_copyable_v<T>`, `is_copy_constructible_v<T>`, `is_move_constructible_v<T>`, `is_copy_assignable_v<T>`, `is_move_assignable_v<T>`, `is_same_v<T, remove_cv_t<T>>`.

Trivial copyability is the core requirement: atomic operations are, in implementation terms, `memcpy` and `memcmp` on the object representation (see Note 4 on CAS below), and only trivially copyable types can be handled that way. The last condition forbids `atomic<const int>` and `atomic<volatile int>`; when volatile is needed, write `volatile atomic<int>`.

For the first line, libc++ reports with a `static_assert`: `std::atomic<T> requires that 'T' be a trivially copyable type`; the error for the second line comes from the `_Atomic(const int)` used internally.

Note 1 in ¶1 warns that type arguments that cannot be statically initialized may be difficult to use. ¶2 `atomic<bool>` is a standard-layout struct with a trivial destructor. ¶3 Note 2: the size and alignment of an `atomic` specialization need not be the same as `T`'s; for example, for a 12-byte struct the `atomic` version is 16 bytes on Apple Silicon ([[atomics.lockfree]]).

## Construction is not an atomic operation [atomics.types.operations]

¶1–¶2 The default constructor initializes with `T()`, i.e. value-initialization, so the value of `std::atomic<int> a;` is 0. This is a C++20 change. In C++17 and earlier, default construction was trivial, a local `a` had an indeterminate value, and it had to be initialized afterwards with `atomic_init` or `ATOMIC_VAR_INIT`, both now deprecated ([[depr.atomics]]).

¶3 `atomic(T desired)` initializes with `desired`. Both constructors state explicitly that initialization is not an atomic operation. Note 1 in ¶3 gives a concrete trap:

```cpp title="construction-race.cpp" ub
#include <atomic>
#include <thread>
std::atomic<std::atomic<int>*> slot{nullptr};
int main() {
  std::thread t([] {
    std::atomic<int>* p;
    while (!(p = slot.load(std::memory_order::relaxed))) {}
    p->fetch_add(1);   // UB: a data race with the construction of *p
  });
  auto* a = new std::atomic<int>(0);
  slot.store(a, std::memory_order::relaxed);
  t.join();
  delete a;
}
```

The address of a just-constructed atomic object is handed to another thread with relaxed operations, and the receiver accesses it immediately; there is no happens before between that access and the construction, so it is undefined behavior. ThreadSanitizer reports a `data race` for this program. Changing the store on `slot` to `release` and the load to `acquire` fixes it: atomic objects, too, must be properly published like ordinary data.

## Load, store and exchange (¶4–¶20)

¶4 `is_always_lock_free` and ¶5 `is_lock_free()` query lock-freedom; see [[atomics.lockfree]].

| Operation | Paragraphs | Memory order precondition | Key points |
|---|---|---|---|
| `store(desired, order)` | ¶6–¶8 | `relaxed`, `release`, `seq_cst` | |
| `operator=(desired)` | ¶9–¶11 | | equivalent to `store(desired)`; returns the value `desired`, not a reference |
| `load(order)` | ¶12–¶15 | `relaxed`, `acquire`, `seq_cst` | |
| `operator T()` | ¶16–¶17 | | equivalent to `return load();` |
| `exchange(desired, order)` | ¶18–¶20 | | atomic read-modify-write operation, returns the old value |

`operator=` returns a value rather than a reference, so in `a = b = 5;` `a` gets 5 without reading `b` again.

Every `volatile` overload has the same *Constraints*: `is_always_lock_free` is `true` (¶6, ¶9, ¶12 and so on). That is, for atomic types that might be implemented with locks, the `volatile` versions do not participate in overload resolution. The typical uses of `volatile` atomic objects are communicating with signal handlers or memory-mapped hardware, where lock-based implementations are unreliable anyway. Annex [[depr.atomics]] keeps the old behavior: these overloads also participate in overload resolution when `is_always_lock_free` is `false`, but this is deprecated.

## compare_exchange (¶21–¶28)

### Basic semantics

¶23 `compare_exchange_strong(expected, desired, success, failure)` first retrieves the value of `expected`, then atomically compares whether the value representation of `*this` equals it:

- equal: replaces it with `desired`, with memory affected according to `success`; this is an atomic read-modify-write operation;
- not equal: writes the value read back into `expected`, with memory affected according to `failure`; this is an atomic load.

When only one memory order argument is given, `success` is that order and `failure` is derived from it: `acq_rel` becomes `acquire`, `release` becomes `relaxed`. ¶22 requires `failure` to be only `relaxed`, `acquire` or `seq_cst`.

¶25 Note 4 explains that for objects with no padding bits, the effect of `compare_exchange_strong` is as if:

```cpp
if (memcmp(this, &expected, sizeof(*this)) == 0)
  memcpy(this, &desired, sizeof(*this));
else
  memcpy(&expected, this, sizeof(*this));
```

### expected is written only on failure

The standard's Example 2 inserts at the head of a linked list, using `p->next` directly as `expected`:

```cpp
do {
  p->next = head;                                   // the new node points to the current head
} while (!head.compare_exchange_weak(p->next, p));  // attempt the insertion
```

On success `p` has been published, and other threads may read `p->next` at any moment. If CAS still wrote `expected` (that is, `p->next`) after succeeding, that write would race with their reads. Writing back only on failure avoids the problem.

### Weak CAS and spurious failure (¶26–¶27)

¶27 `compare_exchange_weak` may **fail spuriously**: it may return `false` even when the value representations are equal. Note 5 explains that this lets CAS be implemented on LL/SC (load-linked/store-conditional) architectures. As a result, the weak version is almost always written in a loop:

```cpp
expected = current.load();
do {
  desired = function(expected);
} while (!current.compare_exchange_weak(expected, desired));
```

When already in a loop, the weak version is faster on some platforms; when weak would need a loop and strong would not, use strong. ¶26 recommends that implementations not make weak CAS fail consistently when the value has not changed and there is no concurrent modification.

### Consequences of comparing value representations (¶28)

Three notes in ¶28 describe the consequences of comparing value representations.

Note 6: equal values are not equal representations. In IEC 60559 floating point, `-0.0` and `+0.0` are equal under `==` but unequal under `memcmp`; NaNs with the same payload are equal under `memcmp` but unequal under `==`.

```cpp run title="cas-float-zero.cpp" ok
#include <atomic>
#include <cstdio>
int main() {
  std::atomic<double> d{+0.0};
  double expected = -0.0;   // == +0.0, but a different bit pattern
  bool ok = d.compare_exchange_strong(expected, 1.0);
  std::printf("%d %g\n", ok, expected);   // 0 0
}
```

The CAS fails, and `expected` is overwritten with `+0.0`.

Note 7: padding bits that never participate in the value representation are ignored. So the standard asserts that the following CAS always succeeds, and does not fail because the padding bytes of `expected` are garbage:

```cpp run title="cas-padding.cpp" ok
#include <atomic>
#include <cstdio>
struct padded {
  char clank = 0x42;
  // padding here
  unsigned biff = 0xC0DEFEFE;
};
std::atomic<padded> pad = {};
bool zap() {
  padded expected, desired{0, 0};
  return pad.compare_exchange_strong(expected, desired);
}
int main() { std::printf("%d\n", zap()); }   // the standard requires printing 1
```

Note 8: when some bits of a union participate in the value representation of only some members, CAS may always fail, because the values of the bits not used by the currently active member are indeterminate.

!!! impl "libc++'s atomic<T> does not ignore padding bits"
    Compiling `cas-padding.cpp` with Clang 23 + libc++ on Apple Silicon prints `1` at `-O2` and `0` at `-O0`. `expected` is a local variable on the stack whose padding bytes hold leftover values, and libc++'s `atomic<T>::compare_exchange_strong` compares them too. libc++ uses `__builtin_clear_padding` to clear padding bits only in `atomic_ref`. This is a conformance defect of the implementation. Portable code had better not let types with padding take part in CAS, or first `memset` both `expected` and the initial value to zero.

### wait and notify (¶29–¶38)

`wait(old, order)` repeatedly loads and compares by value representation with `old`, blocking if equal; `notify_one` and `notify_all` unblock eligible waiters. The rules are in [[atomics.wait]].

## Integral specializations [atomics.types.int]

¶1 There are specializations for every character type, every standard integer type, and other types used by the typedefs in `<cstdint>` (which may be extended integer types). Note 1: `atomic<bool>` uses the primary template and has no arithmetic operations. ¶2 These specializations are standard-layout structs with trivial destructors; `difference_type` is just `value_type`.

¶4–¶9 `fetch_add`, `fetch_sub`, `fetch_and`, `fetch_or`, `fetch_xor`, `fetch_max` and `fetch_min` are atomic read-modify-write operations returning the value before the modification.

!!! std
    Except for `fetch_max` and `fetch_min`, for signed integer types the result is as if the object value and parameters were converted to their corresponding unsigned types, the computation performed on those types, and the result converted back to the signed type.

¶8 specifies that signed integers are computed in the corresponding unsigned type and converted back, and Note 2 stresses that the computation produces no undefined results. Ordinary `int` overflow is UB; atomic `int` overflow wraps around:

```cpp run title="atomic-wrap.cpp" ok
#include <atomic>
#include <climits>
#include <cstdio>
int main() {
  std::atomic<int> a{INT_MAX};
  int old = a.fetch_add(1);
  std::printf("%d %d\n", old, a.load());   // 2147483647 -2147483648
}
```

Run with `-fsanitize=undefined`, UBSan reports nothing. Atomic arithmetic is implemented with the hardware's wrapping addition anyway, and the standard simply acknowledges that.

¶9 `fetch_max`/`fetch_min` compute as if by `std::max`/`std::min` {{c++26}} ([[P0493R5]]). Before that, an atomic max had to be written as a CAS loop.

¶10–¶13 The `store_key` family such as `store_add` {{c++26}} returns no value and consists of atomic modify-write operations (read-modify-writes with weaker synchronization requirements, [[atomics.order#12]]); the memory order can only be `relaxed`, `release` or `seq_cst`. ¶14–¶15 Compound assignments such as `operator+=` return the new value.

!!! impl "Not yet implemented in libc++"
    In the libc++ shipped with Clang 23, `atomic<int>` has no `fetch_max` or `fetch_min` (`__cpp_lib_atomic_min_max` is not defined), nor `store_add` and the like.

## Floating-point specializations [atomics.types.float]

¶1 There are specializations for every cv-unqualified floating-point type, introduced by C++20's [[P0020R6]]. ¶2 They are standard-layout structs with trivial destructors.

```cpp run title="atomic-float.cpp" ok
#include <atomic>
#include <cstdio>
#include <thread>
#include <vector>

int main() {
  std::atomic<double> sum{0.0};
  {
    std::vector<std::jthread> ts;
    for (int t = 0; t < 4; ++t)
      ts.emplace_back([&] {
        for (int i = 0; i < 1000; ++i)
          sum.fetch_add(0.5, std::memory_order::relaxed);
      });
  }
  std::printf("%g\n", sum.load());   // 2000
}
```

Multiples of 0.5 are exactly representable in `double`, so the result does not depend on the order of addition and is always 2000.

¶4–¶10 provide `fetch_add`, `fetch_sub` and six kinds of max/min. ¶8 If the result is not representable, the result is unspecified {{unspec}}, but there is no other undefined behavior; the floating-point environment of atomic arithmetic may differ from the calling thread's. The max/min semantics of ¶9 are the same as for the floating-point specializations of [[atomics.ref.generic]]: `fetch_max`/`fetch_min` are deliberately relaxed on NaN and signed zeros so as to map onto hardware instructions.

¶11–¶16 are the modify-write versions such as `store_add`; ¶14 allows their arithmetic rules to differ from ordinary operations (Note 1: tree reductions are permitted). ¶17–¶19 `operator+=` and `operator-=` return the new value, likewise subject to the rule of ¶8.

!!! impl "Atomic floating-point addition is usually not one instruction"
    Most hardware has no atomic floating-point add instruction. On Apple Silicon, libc++'s `atomic<float>::fetch_add` compiles at `-O2` to a loop of load, `fadd` and CAS, which retries repeatedly under high contention.

## Pointer partial specialization [atomics.types.pointer]

¶1 `atomic<T*>` is a partial specialization whose specializations are standard-layout structs with trivial destructors.

¶2 Except during constant evaluation, if an atomic pointer operation would produce a pointer value `p` that is invalid in the context of the evaluation, the result is instead `reinterpret_cast<T*>(reinterpret_cast<uintptr_t>(p))`. So out-of-bounds atomic pointer arithmetic has a determinate result (it just does not necessarily point to an object), and ¶9 states that the operation itself has no UB. The reason is the same as for the pointer specializations of [[atomics.ref.generic]]: the value used in the computation may have just been changed by another thread, and that cannot be allowed to produce UB.

¶4–¶10 The operand of `fetch_add` and `fetch_sub` is `ptrdiff_t`, and that of `fetch_max` and `fetch_min` is `T*`. ¶6 requires `T` to be a complete object type; arithmetic on `void*` and function pointers is ill-formed. ¶10 Note 2: comparing pointers to different complete objects with `<` does not establish a strict weak ordering, and `fetch_max` has no reliable meaning for them.

¶11–¶14 are the modify-write versions such as `store_add`, and ¶15–¶16 are `operator+=` and `operator-=`.

## Increment and decrement [atomics.types.memop]

| Operator | Equivalent to | Returns |
|---|---|---|
| `a++` | `fetch_add(1)` | old value |
| `a--` | `fetch_sub(1)` | old value |
| `++a` | `fetch_add(1) + 1` | new value |
| `--a` | `fetch_sub(1) - 1` | new value |

They all use the default `seq_cst` and all return values. The new value returned by `++a` is computed within this atomic operation, without reading `a` again, so later modifications by other threads are not reflected in the return value.

## Common misconceptions

!!! pitfall "`a = a + 1` is atomic"
    `a + 1` first calls `operator T()` to do a load, then `operator=` does a store, and other threads' modifications can slip in between the two atomic operations, so increments are lost. Use `++a`, `a += 1` or `fetch_add`.

!!! pitfall "Writing a lock-free stack's pop symmetrically"
    The push in Example 2 is correct. The symmetric pop, `while (!head.compare_exchange_weak(old, old->next))`, has two problems: the node may already have been freed by another thread when `old->next` is read; and there is ABA: a node is popped, freed, reallocated and pushed back, and the CAS believes nothing changed. The solutions are hazard pointers or RCU from [[saferecl]], or `atomic<shared_ptr>` from [[util.smartptr.atomic]].

!!! pitfall "Predicting the result of CAS with floating-point `==`"
    If an `atomic<double>` holds a NaN and `expected` is the same NaN bit pattern, `memcmp` says equal and the CAS succeeds, even though `NaN == NaN` is false. If `expected` is a different NaN bit pattern, it always fails.

## History and evolution

!!! history
    - C++11 introduced `atomic<T>` with a trivial default constructor and an indeterminate value.
    - C++20 made default construction value-initialize; added the floating-point specializations ([[P0020R6]]) and `wait`/`notify`; deprecated `volatile` operations on non-lock-free types; and made CAS explicitly ignore padding bits.
    - C++26 adds `fetch_max`/`fetch_min` ([[P0493R5]]) and atomic modify-write operations such as `store_add`.
    - Post-C++23 wording makes most operations `constexpr` and adds the `fmaximum` family to the floating-point specializations.

## Questions

!!! question "Question 1"
    In `std::atomic<int> a; int x = a;` where `a` is a local variable, what is `x`? What about in C++17?

<details markdown="1">
<summary>Answer</summary>

Since C++20 the default constructor value-initializes ([[atomics.types.operations#2]]), so `x` is 0. In C++17 the default constructor was trivial, a local `a` had an indeterminate value, and reading it was UB; an `a` with static storage duration would be zero-initialized.
</details>

!!! question "Question 2"
    Why does `compare_exchange` write `expected` only on failure?

<details markdown="1">
<summary>Answer</summary>

See Example 2: on success, `expected` may be part of an object that has just been published (`p->next`). If it were still written after success, that write would happen after publication and race with reads of `p->next` by other threads that have seen `p`. The specification of `atomic<shared_ptr>` puts it more directly: on success, `expected` is not accessed after the atomic update ([[util.smartptr.atomic]]).
</details>
