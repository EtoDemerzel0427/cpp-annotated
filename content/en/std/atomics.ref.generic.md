---
title: Class template atomic_ref
summary: "atomic_ref<T> makes an ordinary object an atomic object for a period of time: the access rules while it is referenced, the alignment precondition, how it can differ from atomic<T> in lock-freedom, and the integral, floating-point and pointer specializations."
updated: 2026-10-19
---

!!! tldr
    - `atomic_ref<T>` does not create a new object. While it exists, the referenced ordinary object is an atomic object; once it is destroyed, the object can be accessed normally again.
    - As long as any `atomic_ref` references an object, all accesses to it must go through an `atomic_ref`, and that includes ordinary reads and writes in the same thread; violating this is UB.
    - The object must be aligned to `required_alignment`, which may be greater than `alignof(T)`; failing that is UB and is not checked.
    - `atomic_ref` can use only the object's original size, so it may not be lock-free even when `atomic<T>` of the same type is.
    - Arithmetic in the integral specializations wraps around with no UB; in the floating-point specializations the result is unspecified if not representable; in the pointer specializations going out of bounds gives a determinate but not necessarily usable address.

## Why atomic_ref is needed

`atomic<T>` requires deciding at declaration time that an object is atomic. But many objects are accessed concurrently by several threads only during some phase: a large array is accumulated into by several threads during a parallel phase and read and written by ordinary code during a serial phase. Declaring it as `atomic<int>[]` means paying for atomic operations in the serial phase too; and the layout of `atomic<int>` is not guaranteed to be the same as `int`, so it cannot be handed directly to a C interface.

`atomic_ref<T>` (C++20, [[P0019R8]]) is a reference that, while it exists, treats the referenced ordinary object as an atomic object:

```cpp run title="atomic-ref-histogram.cpp" ok
#include <atomic>
#include <cstdio>
#include <thread>
#include <vector>

int main() {
  alignas(std::atomic_ref<int>::required_alignment) int hist[4] = {};
  {
    std::vector<std::jthread> ts;
    for (int t = 0; t < 4; ++t)
      ts.emplace_back([&hist, t] {
        for (int i = 0; i < 1000; ++i)
          std::atomic_ref(hist[(i + t) % 4])
              .fetch_add(1, std::memory_order::relaxed);
      });
  }                                          // join: all atomic_refs have been destroyed
  for (int v : hist) std::printf("%d ", v);  // ordinary access: OK
  std::puts("");
}
```

The output is `1000 1000 1000 1000`, and ThreadSanitizer reports nothing. During the parallel phase, every access goes through a temporary `atomic_ref`. The `jthread`s join on destruction, after which all `atomic_ref`s have been destroyed, and the join also provides the needed happens before, so the ordinary reads are valid.

## Rules while referenced [atomics.ref.generic.general]

!!! std
    An `atomic_ref` object applies atomic operations to the object referenced by `*ptr` such that, for the lifetime of the `atomic_ref` object, the object referenced by `*ptr` is an atomic object.

¶1 For the lifetime of an `atomic_ref` object, the object it references is an atomic object ([[intro.races]]). That is the whole of `atomic_ref`'s standing in the memory model: it merely changes the identity of an existing object for a period of time.

¶2 `T` must be trivially copyable, otherwise the program is ill-formed.

¶3 places three constraints on users, each of which is UB to violate {{ub}}:

1. the lifetime of the referenced object must exceed the lifetime of all `atomic_ref`s that reference it;
2. as long as any `atomic_ref` referencing it exists, all accesses to the object must go through those `atomic_ref`s;
3. no subobject of the referenced object may be concurrently referenced by another `atomic_ref`.

The second is stricter than "no data races": even within the same thread, holding an `atomic_ref` while assigning normally violates it. The reason is that an implementation may achieve atomicity with locks or state outside the object (see the note in ¶4), and accesses that bypass the `atomic_ref` would corrupt that state.

<div class="compare" markdown="1">

```cpp ok
#include <atomic>
int x = 0;
void f() {
  {
    std::atomic_ref r(x);
    r.store(1);
  }        // r has been destroyed
  x = 2;   // OK
}
```

```cpp ub
#include <atomic>
int x = 0;
void f() {
  std::atomic_ref r(x);
  r.store(1);
  x = 2;   // UB: r still exists (¶3)
}
```

</div>

With multiple threads it is easier still to trip over:

```cpp title="atomic-ref-mixed.cpp" ub
#include <atomic>
#include <thread>
int counter = 0;
int main() {
  std::thread t([] { std::atomic_ref(counter).fetch_add(1); });
  ++counter;   // UB: the atomic_ref in t may still exist, and this access does not go through it
  t.join();
}
```

ThreadSanitizer reports a `data race` for this program.

The third forbids overlap: an `atomic_ref<S>` referencing a struct while an `atomic_ref<int>` references one of its members is not allowed. Atomicity is defined over the whole referenced object, and two partially overlapping atomic objects have no consistent modification order.

¶4 Atomic operations applied through an `atomic_ref` are atomic with respect to atomic operations applied through any other `atomic_ref` referencing the same object. So each thread constructing its own `atomic_ref` to the same object is correct usage; there is no need to share one instance. Note 1 explains that atomic operations or the `atomic_ref` constructor may acquire a shared resource, such as a lock associated with the referenced object.

¶5 If `is_always_lock_free` is `false` and `T` is a volatile type, the program is ill-formed.

### The shape of the class

- The only data member is the exposition-only `T* ptr`; an `atomic_ref` is a small object that can be passed by value.
- `value_type` is `remove_cv_t<T>`.
- The constructor is `explicit atomic_ref(T&)`; `atomic_ref(T&&)` is deleted, so it cannot reference a temporary.
- It is copy-constructible, but copy assignment is deleted: like a reference, it cannot be rebound.
- All member functions are `const`. A `const atomic_ref<int>` can still modify the referenced `int`, just as an `int* const` can modify `*p`.

## Alignment and lock-freedom [atomics.ref.ops]

¶1 `required_alignment` is the alignment required for an object to be referenced by an `atomic_ref`, at least `alignof(T)`. For a type `U` similar to `T` (differing only in cv-qualification), `atomic_ref<remove_cv_t<U>>` has the same value, so `atomic_ref<const int>` and `atomic_ref<int>` have the same requirement.

¶2 Note 1: an implementation can make `required_alignment` greater than `alignof(T)` to ensure all operations are lock-free. For example, on some 32-bit platforms `alignof(long long)` is 4, while 8-byte atomic instructions require 8-byte alignment.

¶5 The precondition of the constructor is that the referenced object is aligned to `required_alignment`. The `alignas` in the histogram example above is there for this: usually redundant for `int`, possibly necessary for `double`, `long long` and structs.

¶3 `is_always_lock_free` is `true` if the operations are always lock-free. ¶4 `is_lock_free()` returns `true` if operations on all objects of type `atomic_ref<T>` are lock-free.

The lock-freedom of `atomic_ref` can differ from that of `atomic<T>`. `atomic<T>` can add padding to itself and raise its alignment; `atomic_ref` can only use the object's original size and alignment. Tested with Clang 23 on Apple Silicon, for the 12-byte `struct S12 { int a, b, c; }`: `sizeof(atomic<S12>)` is 16 and `atomic<S12>::is_always_lock_free` is `true`; `atomic_ref<S12>::required_alignment` is 4 and `is_always_lock_free` is `false` (see also [[atomics.lockfree]]).

## Operations [atomics.ref.ops]

### Construction and conversion (¶5–¶10)

Besides the alignment precondition above, ¶8 copy construction yields an `atomic_ref` referencing the same object. The converting constructor `atomic_ref(const atomic_ref<U>&)` in ¶9 requires `T` and `U` to be similar and `U*` to be convertible to `T*`, i.e. it only allows adding cv-qualification: an `atomic_ref<int>` can convert to an `atomic_ref<const int>`. This is post-C++23 wording added along with cv-qualified `T`.

### Load, store, exchange and CAS (¶11–¶27)

These operations are the same, one for one, as the corresponding operations of `atomic<T>` ([[atomics.types.operations]]), except that they act on `*ptr`:

| Operation | Paragraphs | Key points |
|---|---|---|
| `store` | ¶11–¶13 | `T` cannot be const; the memory order can only be `relaxed`, `release` or `seq_cst` |
| `operator=` | ¶14–¶15 | equivalent to `store(desired); return desired;`, returning a value, not a reference |
| `load`, `operator value_type` | ¶16–¶19 | the memory order can only be `relaxed`, `acquire` or `seq_cst` |
| `exchange` | ¶20–¶22 | an atomic read-modify-write operation |
| `compare_exchange_weak/strong` | ¶23–¶27 | compares value representations; the weak version may fail spuriously |

For `atomic_ref<const T>`, all modifying operations are excluded by *Constraints*, leaving only read-only operations such as `load` and `wait`.

### Waiting and notifying (¶28–¶36)

`wait(old, order)` repeatedly performs `load(order)` and compares by value representation with `old`, blocking if equal until notified or spuriously woken. `notify_one` and `notify_all` require `T` not to be const. The rules are in [[atomics.wait]].

### address() (¶37)

¶37 `address()` returns `ptr`, with type *COPYCV*`(T, void)*`, which is `const void*` for `atomic_ref<const int>`. It returns `void*` rather than `T*`: with the address you can compare and hash (for example, to implement locks bucketed by address), but accessing the object must still go through `atomic_ref`, and returning `void*` makes misuse harder. This too is post-C++23 wording.

!!! impl "libc++ support (Clang 23)"
    - `address()` is implemented.
    - `atomic_ref<const int>` cannot be used: the constructor internally passes a `const int*` to an `int*` parameter and fails to compile.
    - The member functions are not yet `constexpr`, so using `atomic_ref` in a constant expression fails.

## Integral specializations [atomics.ref.int]

¶1 There are specializations for every integral type except cv `bool`, providing integral-specific atomic operations; `atomic_ref<bool>` uses the primary template. The specialization's `difference_type` is just `value_type`.

¶4–¶9 `fetch_add`, `fetch_sub`, `fetch_and`, `fetch_or`, `fetch_xor`, `fetch_max` and `fetch_min` are atomic read-modify-write operations returning the value before the modification. ¶8 specifies that, except for `max`/`min`, signed integer computation is as if converted to the corresponding unsigned type, computed, and converted back, so overflow wraps around with no UB. ¶9 `fetch_max`/`fetch_min` compute as if by `std::max`/`std::min` {{c++26}}.

¶10–¶13 The `store_key` family such as `store_add` {{c++26}} does the same computation without returning a value. They are **atomic modify-write operations**: read-modify-write operations with weaker synchronization requirements, intended to be implemented with hardware mechanisms not ordered by acquire fences ([[atomics.order#12]], [[atomics.fences]]). The memory order can only be `relaxed`, `release` or `seq_cst`.

¶14–¶15 Compound assignments such as `operator+=` are equivalent to `return fetch_key(operand) op operand;`, returning the new value, and the memory order is always `seq_cst`.

## Floating-point specializations [atomics.ref.float]

¶1 There are specializations for every floating-point type, including extended floating-point types. They provide `fetch_add`, `fetch_sub` and six kinds of max/min: `fetch_max`, `fetch_min`, `fetch_fmaximum`, `fetch_fminimum`, `fetch_fmaximum_num`, `fetch_fminimum_num`.

¶8 If the result is not representable, the result is unspecified {{unspec}}, but the operation itself has no UB. One more point is easily overlooked: the floating-point environment ([[cfenv]]) used by atomic arithmetic may differ from the calling thread's, so a rounding mode set with `fesetround` does not necessarily apply to `fetch_add`.

¶9 specifies the semantics of the various max/min:

- `fetch_fmaximum`/`fetch_fminimum` behave as C's `fmaximum`/`fminimum`, propagating NaN;
- `fetch_fmaximum_num`/`fetch_fminimum_num` behave as `fmaximum_num`/`fminimum_num`, ignoring NaN;
- `fetch_max`/`fetch_min` behave as `fmaximum_num`/`fminimum_num`, with three relaxations: if both arguments are NaN, an unspecified NaN is stored; if exactly one is NaN, either the other argument or an unspecified NaN is stored; if the two arguments are zeros of different sign, which one is stored is unspecified. ¶10 recommends treating `-0` as less than `+0`.

The relaxations allow a direct mapping to hardware floating-point max/min instructions, which behave differently from one another on NaN and signed zeros.

¶11–¶16 `store_add`, `store_sub`, `store_max` and so on are atomic modify-write operations. ¶14 additionally allows their arithmetic rules to differ from ordinary floating-point operations, and Note 1 explicitly permits tree reductions: when a thousand threads do `store_add` on the same `float`, the hardware may first add pairs and then combine. Floating-point addition is not associative, so the result may differ from every sequential order of addition.

¶17–¶18 `operator+=` and `operator-=` return the new value.

## Pointer specializations [atomics.ref.pointer]

¶1 There are specializations for every object pointer type.

¶2 Ordinary pointer arithmetic out of bounds is UB ([[expr.add]]), but an atomic pointer's `fetch_add` cannot have UB, because the value it computes with may have just been changed by another thread. So ¶2 specifies: except during constant evaluation, if an operation on an atomic pointer would produce a pointer value `p` that is invalid in the context of the evaluation ([[basic.compound]]), the result is instead `reinterpret_cast<T*>(reinterpret_cast<uintptr_t>(p))`.

So the out-of-bounds result is a pointer that has round-tripped through an integer: its value is determinate, it just does not necessarily point to any object. ¶10 and ¶16 accordingly state that the result may be an undefined address, but the operation itself has no undefined behavior.

¶5–¶11 The operand of `fetch_add` and `fetch_sub` is `difference_type` (`ptrdiff_t`), and the operand of `fetch_max` and `fetch_min` is a pointer. ¶7 requires pointers to complete object types; arithmetic on `void*` and function pointers is ill-formed. ¶11 Note 1 warns that comparing pointers to different complete objects with `<` does not establish a strict weak ordering ([[expr.rel]]), in which case the result of `fetch_max` has no reliable meaning.

¶12–¶16 are the modify-write versions such as `store_add`, and ¶17–¶18 are `operator+=` and `operator-=`.

## Increment and decrement [atomics.ref.memop]

The integral and pointer specializations share four operators, all requiring the referenced type not to be const:

| Operator | Equivalent to | Returns |
|---|---|---|
| `r++` | `fetch_add(1)` | old value |
| `r--` | `fetch_sub(1)` | old value |
| `++r` | `fetch_add(1) + 1` | new value |
| `--r` | `fetch_sub(1) - 1` | new value |

Prefix `++` also returns a value, not a reference.

## Common misconceptions

!!! pitfall "Insufficient alignment is just slower"
    An `atomic_ref<double>` referencing a `double` obtained by `reinterpret_cast` from a byte buffer, with only 4-byte alignment, violates the constructor's precondition and is UB. The actual consequence may be loss of atomicity (one access split into two), or an alignment fault on some hardware.

!!! pitfall "The whole and its parts can be accessed atomically separately"
    Atomically reading an 8-byte struct with an `atomic_ref<uint64_t>` while modifying half of it with an `atomic_ref<uint32_t>` violates the third constraint of ¶3. When access is sometimes to the whole and sometimes to a part, always do CAS on the whole.

## Questions

!!! question "Question 1"
    Two threads each construct an `atomic_ref<int>` referencing the same `int`, and each does 1000 `fetch_add(1, relaxed)`. Is the value read after join always 2000?

<details markdown="1">
<summary>Answer</summary>

Always. ¶4 specifies that atomic operations on the same object through different `atomic_ref`s are atomic with respect to each other; ¶1 makes the object an atomic object during that time, so it has a single modification order; [[atomics.order#11]] specifies that each read-modify-write reads the value immediately preceding it in the modification order, so no increment is lost. After join both `atomic_ref`s have been destroyed, join provides happens before, and the ordinary read is valid.
</details>

!!! question "Question 2"
    What is `std::atomic_ref<const int>` for?

<details markdown="1">
<summary>Answer</summary>

For the read-only side. When another thread modifies the object through an `atomic_ref<int>`, by ¶3 the reader must also access it through an `atomic_ref`, yet it may hold only a `const int&`. Before cv-qualified `T` was allowed, the only option was to `const_cast` and construct an `atomic_ref<int>`. `atomic_ref<const int>` offers only operations like `load` and `wait`, and can also be obtained by converting an `atomic_ref<int>` (¶9).
</details>

## Summary

| | `atomic<T>` | `atomic_ref<T>` |
|---|---|---|
| when the object is atomic | always | only while an `atomic_ref` references it |
| layout | may differ from `T` | is `T` itself |
| lock-freedom | can be achieved through padding and alignment | limited by the object's size; requires `required_alignment` |
| copying | not copyable | copy-constructible (copies the reference), not copy-assignable |
| mixing with ordinary access | impossible | forbidden while referenced (UB) |
