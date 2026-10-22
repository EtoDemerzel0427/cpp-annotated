---
title: Shared ownership pointers
summary: "The model behind shared_ptr and weak_ptr: two pointers plus a control block; the single allocation of make_shared and its cost; what the standard's thread-safety guarantee covers; and bad_weak_ptr."
updated: 2026-10-19
---

!!! tldr
    - All `shared_ptr`s and `weak_ptr`s sharing an object point to the same control block, which holds the strong count, the weak count and the deleter; each `shared_ptr` itself is two pointers.
    - The deleter is stored in the control block according to the actual type at construction, so `shared_ptr<Base>` and `shared_ptr<void>` also destroy derived objects correctly, and `T` may be incomplete.
    - `make_shared` puts the object and the control block in a single allocation; the cost is that the memory cannot be released while any `weak_ptr` remains.
    - Different `shared_ptr` objects can be freely copied and destroyed in different threads; concurrent reads and writes of the same `shared_ptr` object are a data race and need `atomic<shared_ptr<T>>`.
    - Constructing a `shared_ptr` from an expired `weak_ptr` throws `bad_weak_ptr`; `weak_ptr::lock()` does not throw and returns a null pointer when expired.

[util.sharedptr] contains `bad_weak_ptr`, `shared_ptr`, `weak_ptr`, `owner_less`, `owner_hash`, `owner_equal` and `enable_shared_from_this`. The standard describes them with abstract notions such as ownership and shared ownership and never mentions reference counts or control blocks, but without the implementation model below it is hard to see why the clauses say what they say. Paragraph-by-paragraph notes on each class template:

- [[util.smartptr.shared]]: construction of `shared_ptr`, the aliasing constructor, `make_shared`, casts;
- [[util.smartptr.weak]]: `weak_ptr` and `lock`;
- [[util.smartptr.ownerless]]: `owner_less`, `owner_hash`, `owner_equal`;
- [[util.smartptr.enab]]: `enable_shared_from_this`.

## Two pointers and a control block

```text
shared_ptr<T>           control block (on the heap)
┌─────────────┐         ┌──────────────────────────────┐
│ T* ptr      │──┐      │ vptr                         │
│ ctrl*       │──┼────▶ │ strong count (use_count)     │
└─────────────┘  │      │ weak count                   │
                 │      │ deleter D, allocator A       │
                 │      │   (type-erased)              │
                 │      │ [with make_shared: T itself] │
                 └────▶ └──────────────────────────────┘
```

A group of `shared_ptr`s and `weak_ptr`s that share ownership with each other corresponds, in every implementation, to one **control block**. A `shared_ptr` object stores two pointers:

- the **stored pointer** `ptr`: `get()` returns it, and dereferencing uses it. It does not necessarily point to the owned object; the aliasing constructor and conversion to a base class both make it point elsewhere.
- the **control block pointer**: the control block holds the strong count (how many `shared_ptr`s own the object), the weak count (how many `weak_ptr`s; implementations usually add 1 while the strong count is nonzero), the owned pointer, the deleter and the allocator.

When the strong count drops to zero, the deleter is called to destroy the owned object; when the weak count also drops to zero, the control block itself is released.

This model explains many seemingly odd rules in the standard:

| What the standard says | Explanation by the model |
|---|---|
| The `T` of `shared_ptr<T>` may be incomplete, or even a function type ([[util.smartptr.shared#3]]) | The deleter is stored in the control block according to the actual type at construction, so destroying a `shared_ptr` does not need to know `T` |
| There can be an empty `shared_ptr` whose stored pointer is non-null (aliasing constructor, [util.smartptr.shared.const] ¶17) | The control block pointer is null, the stored pointer is not |
| The pointer returned by `get_deleter` may remain valid after the last `shared_ptr` is destroyed (the note in [[util.smartptr.getdeleter]]) | The deleter is in the control block, and the implementation may wait until the weak count drops to zero before destroying it |
| `owner_before` and `operator<` give different results | The former compares control blocks, the latter stored pointers |
| `shared_ptr(p)` may throw `bad_alloc`, and does `delete p` when it does ([util.smartptr.shared.const] ¶6, ¶8) | It has to allocate a control block; if that fails it must clean up the `p` it has already taken over |

!!! impl "The libc++ control block"
    libc++'s control block base class is `__shared_weak_count`, derived from `__shared_count`. It has a vtable pointer: the virtual function `__on_zero_shared()` destroys the object when the strong count reaches zero, `__on_zero_shared_weak()` releases the control block when the weak count reaches zero, and `__get_deleter(const type_info&)` implements `get_deleter`. The two count fields `__shared_owners_` and `__shared_weak_owners_` both store the count minus one, so `use_count()` returns `__shared_owners_ + 1`.

    Derived classes differ by how they are created: `__shared_ptr_pointer<P, D, A>` holds the pointer, deleter and allocator and is created by constructors like `shared_ptr(p, d, a)`; `__shared_ptr_emplace<T, A>` places the `T` object directly in the control block and is created by `make_shared` and `allocate_shared`.

    Increments use `__ATOMIC_RELAXED` and decrements use `__ATOMIC_ACQ_REL`. When incrementing, the caller already holds a reference, so the object cannot be destroyed in the meantime and no synchronization is needed; when decrementing, the thread that takes the count to 0 has to destroy the object, and it must see every modification other threads made to the object through their own copies.

## `make_shared` allocates once

```cpp run impl
#include <cstdio>
#include <cstdlib>
#include <memory>
#include <new>

static int allocs = 0;
void* operator new(std::size_t n) {
  ++allocs;
  if (void* p = std::malloc(n)) return p;
  throw std::bad_alloc();
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }

struct Big { char data[64]; };

int main() {
  allocs = 0;
  std::shared_ptr<Big> a(new Big);
  std::printf("shared_ptr(new T): %d\n", allocs);   // 2
  allocs = 0;
  auto b = std::make_shared<Big>();
  std::printf("make_shared:       %d\n", allocs);   // 1
  std::printf("%zu %zu\n", sizeof a,
              sizeof(std::weak_ptr<Big>));          // 16 16
}
```

The comments show the output with libc++ in our tests. `shared_ptr<T>(new T)` allocates twice, once for `new T` and once for the control block. `make_shared<T>()` puts `T` inside the control block and allocates once. [util.smartptr.shared.create] ¶7.1 recommends that implementations perform no more than one allocation; this is a recommendation, not a requirement, so the verdict is {{impl}}.

One allocation saves a call to `malloc` and keeps the object next to its counts. It has two costs:

1. Deallocation is delayed. `T` and the control block are in the same block of memory; when the strong count reaches zero `T` is destroyed, but as long as a `weak_ptr` remains the weak count is nonzero and the whole block cannot be released, including the part `T` occupied. A large object combined with a long-lived `weak_ptr` (in a cache, say) can hold on to a considerable amount of memory.
2. No custom deleter, and the class's own `operator new` and `operator delete` are not used: ¶7.4 specifies that `make_shared` constructs the object with `::new(pv) U(...)`. Use `allocate_shared` when allocation needs to be customized.

## Thread safety

All of `shared_ptr`'s thread-safety guarantees come from [[util.smartptr.shared#5]]:

!!! std "[util.smartptr.shared.general]/5"
    For purposes of determining the presence of a data race, member functions shall access and modify only the shared_ptr and weak_ptr objects themselves and not objects they refer to. Changes in use_count() do not reflect modifications that can introduce data races.

When determining whether there is a data race, member functions count as accessing and modifying only the `shared_ptr` and `weak_ptr` objects themselves, not the objects they refer to; changes in `use_count()` do not count as modifications that can cause data races either. In concrete terms:

| Scenario | Data race? |
|---|---|
| Two threads each copy and destroy different `shared_ptr` objects, even if they share one control block | No; count modifications do not count, and the implementation must use atomic operations |
| Two threads simultaneously read (copy, `get()`) the same `shared_ptr` object | No; these are all const operations ([[res.on.data.races]]) |
| One thread writes (assigns, `reset`s) a `shared_ptr` object while another thread reads or writes it | Yes, {{ub}} |
| Several threads access the pointed-to object through `shared_ptr`s | Unrelated to `shared_ptr`; depends on that object itself |

```cpp run ub
#include <memory>
#include <thread>
int main() {
  auto p = std::make_shared<int>(1);
  std::thread t([&] {
    for (int i = 0; i < 100000; ++i) { auto copy = p; }   // reads p
  });
  for (int i = 0; i < 100000; ++i)
    p = std::make_shared<int>(i);   // writes p: data race
  t.join();
}
```

In our tests, running with `-fsanitize=thread` makes ThreadSanitizer report a data race; with `-fsanitize=address`, AddressSanitizer reports heap-use-after-free. When the reader thread copies `p`, it may read the new stored pointer together with the old control block pointer; or the writer thread may have released the old control block before the reader increments its count.

When several threads need to read and write the same `shared_ptr` variable, since C++20 use `std::atomic<std::shared_ptr<T>>` ([[util.smartptr.atomic]], [[P0718R2]]). It replaces the C++11 free functions `atomic_load(&sp)` and `atomic_store(&sp, ...)`, which were deprecated in C++20 and removed in C++26. At the time of writing, libc++ (with Clang 23) does not yet implement `atomic<shared_ptr>`; `__cpp_lib_atomic_shared_ptr` in `<version>` is commented out.

Two more points are easy to overlook:

- In multithreaded code `use_count()` is only an approximation ([util.smartptr.shared.obs] ¶17). Implementations read it with relaxed ordering, and `use_count() == 1` does not mean that accesses other threads made through now-destroyed `shared_ptr`s have completed. Using it to decide that you are the sole owner and may modify the object without a lock is wrong. This is one of the reasons C++20 removed `unique()`.
- The object is destroyed on whichever thread destroys the last `shared_ptr`. Take special care with objects that hold locks, depend on thread-local state, or must be destroyed on the GUI thread.

## `bad_weak_ptr` [util.smartptr.weak.bad]

```cpp
class bad_weak_ptr : public exception {
public:
  constexpr const char* what() const noexcept override;
};
```

¶1 The `shared_ptr` constructor taking a `weak_ptr` throws `bad_weak_ptr` when that `weak_ptr` has expired ([util.smartptr.shared.const] ¶27). `shared_from_this()` is implemented with this constructor, so calling `shared_from_this()` on an object not owned by any `shared_ptr` throws it too. This is the C++17 rule; before that it was undefined behavior ([[util.smartptr.enab]]).

¶2 `what()` returns an implementation-defined NTBS (null-terminated byte string).

`what()` is `constexpr`. C++26 makes `shared_ptr` usable in constant evaluation ([[P3037R6]]) and also allows throwing and catching exceptions in constant evaluation, so constructing a `shared_ptr` from an expired `weak_ptr` throws this exception at compile time too.

`weak_ptr::lock()` does not throw; it returns an empty `shared_ptr` when expired. That is the whole difference between the two ways of getting a `shared_ptr`: on failure one throws, the other returns empty.

## Questions

!!! question "Question 1"
    On a 64-bit platform, why is a `shared_ptr<T>` 16 bytes rather than 8 like an intrusive smart pointer?

<details markdown="1">
<summary>Answer</summary>

The stored pointer can differ from the owned pointer; the aliasing constructor and conversion to a base class both change the address. With only a control block pointer, `get()` would be unavailable unless every dereference took an extra indirection. The standard interface requires the aliasing constructor and makes `get()` a `noexcept` constant-time operation, which in practice forces implementations to store two pointers.
</details>

!!! question "Question 2"
    An object created with `make_shared` is being observed by a `weak_ptr`. After the last `shared_ptr` is destroyed, does the object's destructor run? Is the memory released?

<details markdown="1">
<summary>Answer</summary>

The destructor runs; the object is destroyed when the strong count reaches zero. The memory is not released: the object lives in the control block, and the control block is released only when the weak count reaches zero, i.e. after that `weak_ptr` is destroyed too.
</details>
