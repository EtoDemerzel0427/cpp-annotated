---
title: Atomic smart pointers
summary: "atomic<shared_ptr<T>> and atomic<weak_ptr<T>>: which steps are inside the atomic operation, how CAS and wait compare two smart pointers, and why the old atomic_load(shared_ptr*) family was removed in C++26."
updated: 2026-10-19
---

!!! tldr
    - The reference count of `shared_ptr` is atomic, but one thread assigning to a `shared_ptr` variable while another reads the same variable is still a data race. Only `atomic<shared_ptr<T>>` makes the variable itself safe for concurrent reads and writes.
    - The atomic operation includes modifying the pointer and incrementing `use_count`; the decrement, destruction and deallocation happen after the atomic operation, not within it.
    - CAS and `wait` compare for equivalence: the same stored pointer, and sharing ownership or both empty. This is stricter than `==`.
    - An atomic smart pointer protects only the pointer variable, not the object it points to.
    - The old non-member `atomic_load(const shared_ptr<T>*)` family was deprecated in C++20 and removed in C++26. As of this writing, libc++ does not yet provide these two partial specializations.

## shared_ptr itself is not a thread-safe variable

The reference count in a `shared_ptr`'s control block is updated atomically, which is often misread as "`shared_ptr` is thread-safe". In fact, one thread assigning to a `shared_ptr` object while another copies the same object is a data race ([[res.on.data.races]]). Assignment has to change two words, the stored pointer and the control block pointer, and adjust the counts of both the old and new control blocks, and these steps together are not atomic.

`atomic<shared_ptr<T>>` and `atomic<weak_ptr<T>>` (C++20, [[P0718R2]]) provide shared pointer variables that can be read and written concurrently. They are partial specializations of the `atomic` primary template. `shared_ptr` is not trivially copyable, so the primary template's requirements on `T` ([[atomics.types.generic]]) do not apply to them, and they are specified separately here.

## The boundary of atomicity [util.smartptr.atomic.general]

¶1 The library provides partial specializations of `atomic` for shared-ownership smart pointers ([[util.sharedptr]]). Note 1: they are declared in `<memory>`, not `<atomic>`. Unless otherwise specified, all operations behave as in [[atomics.types.generic]]. The template parameter `T` may be an incomplete type, which is needed for linked-list nodes such as `struct node { atomic<shared_ptr<node>> next; };`.

¶2 specifies which steps are part of the atomic operation:

| Step | Inside the atomic operation? |
|---|---|
| modifying the atomic smart pointer itself | yes |
| the associated `use_count` increments | yes |
| the associated `use_count` decrements | not required; sequenced after the atomic operation |
| any resulting destruction of the object and deallocation | no; sequenced after the atomic update step |

Note 2 adds: if the atomic operation is implemented with a lock, the lock is held while `use_count` is adjusted, and not held while destruction or deallocation is performed.

The increment must be inside the atomic operation. `load()` must return a new `shared_ptr`, so it must increment the reference count at the same time as it reads the pointer; otherwise, between reading the pointer and incrementing the count, another thread might `store` a new value, drop the old object's count to zero and delete it, and `load` would return a dangling pointer.

The decrement can be outside. By the time it happens, the old value has been replaced and nobody can see it through this atomic pointer anymore. The destructor may be slow, and might even access this atomic pointer again, so it should not run under the lock either.

## Example: a linked list (¶3)

Example 1 in ¶3 is a singly linked list. `find` takes shared ownership of each node with `head.load()` while traversing, and `push_front` inserts with CAS:

```cpp
template<typename T> class atomic_list {
  struct node {
    T t;
    shared_ptr<node> next;
  };
  atomic<shared_ptr<node>> head;
public:
  shared_ptr<node> find(T t) const {
    auto p = head.load();
    while (p && p->t != t)
      p = p->next;
    return p;
  }
  void push_front(T t) {
    auto p = make_shared<node>();
    p->t = t;
    p->next = head;
    while (!head.compare_exchange_weak(p->next, p)) {}
  }
};
```

Every node `find` reaches is kept alive by the `shared_ptr` it holds, so even if another thread unlinks a node, the traversal never touches freed memory. A lock-free list written with raw pointers needs hazard pointers ([[saferecl]]) to achieve this. The price is an atomic reference count modification at every step.

As of this writing, the libc++ in Clang 23 does not implement `atomic<shared_ptr<T>>`, so this code has not been verified by compiling.

## The shared_ptr partial specialization [util.smartptr.atomic.shared]

The shape of the class differs from the primary template in a few places: the exposition-only member is `shared_ptr<T> p`; it can be constructed from and assigned `nullptr`; `operator=` returns `void`, because returning a value would need another copy of the `shared_ptr` and another pair of reference count operations; and there are no `volatile` overloads.

- ¶1 The default constructor value-initializes `p`. ¶2 Initialization by `atomic(shared_ptr<T> desired)` is not an atomic operation; Note 1 warns of the race with construction, as for the primary template.
- ¶3–¶4 `store(desired, order)` atomically replaces as if by `p.swap(desired)`. The old value is swapped into the parameter `desired` and released when the parameter is destroyed, which is exactly outside the atomic operation, as ¶2 requires.
- ¶5–¶6 `operator=(shared_ptr<T>)` and `operator=(nullptr_t)` are equivalent to `store`.
- ¶7–¶10 `load(order)` atomically returns a copy of `p`; `operator shared_ptr<T>()` is equivalent to `load()`.
- ¶11–¶12 `exchange` behaves as if by `p.swap(desired)`, is an atomic read-modify-write operation, and returns the old value.

### compare_exchange and equivalence (¶13–¶19)

¶14 If `p` is equivalent to `expected`, `desired` is assigned to `p`, with synchronization semantics corresponding to `success`; otherwise `p` is assigned to `expected`, with synchronization semantics corresponding to `failure`.

¶16 Two `shared_ptr` objects are **equivalent** if they store the same pointer value and either share ownership or are both empty. The weak form may fail spuriously.

Equivalence is stricter than `==`; the `==` of `shared_ptr` compares only `get()`. Two `shared_ptr`s may store the same pointer yet belong to different control blocks, for example one obtained by aliasing construction, or two mistakenly created from the same raw pointer. They are `==` but not equivalent, and CAS fails. If only pointers were compared, a successful CAS could mistake a value belonging to another control block for the current value, and the reference counts would get corrupted.

¶17 If it returns `true`, `expected` is not accessed after the atomic update, and the operation is an atomic read-modify-write; otherwise it is an atomic load, and `expected` is updated with the value read. The `use_count` update corresponding to the write to `expected` is part of the atomic operation; the write to `expected` itself need not be.

¶18–¶19 For the overloads taking a single memory order, `failure` is derived from it: `acq_rel` becomes `acquire`, `release` becomes `relaxed`.

### wait and notify (¶20–¶26)

¶21 `wait(old, order)` repeatedly does `load(order)` and returns when the result is not equivalent to `old`, blocking otherwise. ¶22 says the same equivalence definition is used here, not a byte comparison. `notify_one` and `notify_all` are as usual; see [[atomics.wait]].

## The weak_ptr partial specialization [util.smartptr.atomic.weak]

It parallels the `shared_ptr` version clause by clause: the member is `weak_ptr<T> p`; it provides `load`, `store`, `exchange`, `compare_exchange_*`, `wait` and `notify_*`; and the definition of equivalence is the same. Typical uses are caches and observer lists: several threads atomically read and write a reference that may have expired, calling `lock()` when needed.

## The removed old interface

The C++11 approach was to call a set of non-member functions on an ordinary `shared_ptr` variable: `atomic_load(const shared_ptr<T>*)`, `atomic_store`, `atomic_exchange`, `atomic_compare_exchange_*` and their `_explicit` versions. C++20 deprecated them {{deprecated}}, and C++26 removes them {{removed:C++26}}.

The rationale given in [[diff.cpp23.depr]] is that the old approach was not protected by the type system and could silently produce undefined behavior when interacting with code that does not use this API. A single place in the code that forgets `atomic_load` and copies the variable directly is a data race, and the compiler says nothing. `atomic<shared_ptr<T>>` provides no non-atomic access at all.

## The implementation's view

!!! impl "The state of libc++ (Clang 23)"
    `__cpp_lib_atomic_shared_ptr` is not defined. Writing `std::atomic<std::shared_ptr<int>>` falls through to the primary template and is rejected by a `static_assert`: `std::atomic<T> requires that 'T' be a trivially copyable type`.

    On the other hand, functions such as `std::atomic_load(const shared_ptr<T>*)`, already removed in C++26, are still available under `-std=c++2c`, without even a deprecation warning.

!!! impl "Common implementation strategies"
    A `shared_ptr` consists of two pointers, so operating on it atomically needs a 16-byte CAS or a lock. libstdc++ puts a spin-lock bit in the lowest bit of the control block pointer (control blocks are pointer-aligned, so the lowest bit is free): `load` first locks that bit, copies the pointer and increments the reference count, then unlocks. So it is usually not lock-free, and `is_always_lock_free` is `false`, but the critical section is short.

## Common misconceptions

!!! pitfall "An atomic smart pointer protects the pointed-to object"
    Two threads executing `ap.load()->value = 42;` at the same time is still a data race on `value`. What an atomic smart pointer guarantees is that reading and writing the pointer variable is safe, and that the object you obtained is not freed while you use it. Concurrent access to the object itself needs separate synchronization, or treat the object as immutable: for every modification, `make_shared` a new object and `store` it.

!!! pitfall "The old object is destroyed in the thread that does the store"
    After `store` or `exchange` replaces the old value, the old object is destroyed only when its last holder releases it. That may be the thread doing the `store`, or a reader thread that just did a `load` and releases it later. A destructor should not depend on which thread it runs on.
