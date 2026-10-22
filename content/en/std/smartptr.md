---
title: Smart pointers
summary: "What unique_ptr, shared_ptr, weak_ptr and out_ptr each solve and how to choose between them, and why smart pointers hash by the stored pointer."
updated: 2026-10-19
---

!!! tldr
    - Use `unique_ptr` by default: exclusive ownership, the same size as a plain pointer with an empty deleter, and convertible to `shared_ptr` when needed.
    - Use `shared_ptr` only when ownership really is shared by several parties and it cannot be determined who releases last; it needs an extra control block and does atomic count operations on copy and destruction.
    - `weak_ptr` observes an object managed by `shared_ptr` without extending its lifetime; it is used for caches, observer lists and breaking reference cycles.
    - The `hash` and `==` of smart pointers are both computed from the stored pointer `get()`; to group by ownership, use `owner_hash` and `owner_equal`.

## Components

| Subclause | Components | Ownership |
|---|---|---|
| [[unique.ptr]] | `unique_ptr`, `default_delete`, `make_unique` | Exclusive, transferable |
| [[util.sharedptr]] | `shared_ptr`, `weak_ptr`, `bad_weak_ptr`, `owner_less`/`owner_hash`/`owner_equal`, `enable_shared_from_this` | Shared, reference-counted |
| [util.smartptr.hash] | `hash<unique_ptr>`, `hash<shared_ptr>` | See below |
| [[smartptr.adapt]] | `out_ptr`, `inout_ptr` | Working with C interfaces that output a pointer through a pointer parameter |

The details of `shared_ptr` are split across [[util.smartptr.shared]], [[util.smartptr.weak]], [[util.smartptr.ownerless]] and [[util.smartptr.enab]]. `atomic<shared_ptr<T>>` and `atomic<weak_ptr<T>>` are declared in `<memory>`, with their rules in [[util.smartptr.atomic]] in the atomic operations chapter.

## How to choose

1. Use `unique_ptr` by default. With an empty deleter it is the same size as a plain pointer, with no extra overhead; transferring ownership requires an explicit `std::move`. `shared_ptr` has a constructor taking `unique_ptr&&`, so you can switch to sharing at any time later; the reverse is not possible.
2. Use `shared_ptr` only when ownership really is shared by several independent lifetimes and it cannot be determined who releases last. The cost is an extra control block (one more allocation, which `make_shared` can merge into one), atomic reference-count operations on every copy and destruction, and an object that is usually twice the size of a plain pointer.
3. `weak_ptr` is for observing without extending the lifetime: caches, observer lists, breaking reference cycles between `shared_ptr`s.
4. When you need an object on the heap but with value semantics, since C++26 consider [[indirect]] and [[polymorphic]]. Like `unique_ptr` they have exclusive ownership, but they can be copied (deep copy), `const` propagates to the owned object, and comparisons compare values. They are not under [smartptr] but in [[mem.composite.types]].
5. For non-owning observation use a plain pointer or reference. The standard has no `observer_ptr`; it exists only in Library Fundamentals TS v2.

Smart pointers do not make the pointed-to object thread-safe, nor the smart pointer object itself. `shared_ptr` only guarantees that different `shared_ptr` objects operating concurrently on the same reference count do not cause a data race; concurrent reads and writes of the same `shared_ptr` object are still a data race ([[util.sharedptr]]).

## Hashing [util.smartptr.hash]

```cpp run ok
#include <cassert>
#include <memory>
#include <unordered_set>

struct P { int a, b; };

int main() {
  auto sp = std::make_shared<P>();
  std::shared_ptr<int> alias(sp, &sp->b);   // shares ownership, different get()
  std::unordered_set<std::shared_ptr<void>> s;
  s.insert(sp);
  s.insert(alias);
  assert(s.size() == 2);                     // distinguished by get()
  assert(std::hash<std::shared_ptr<P>>()(sp) ==
         std::hash<P*>()(sp.get()));
}
```

`alias` is created with the aliasing constructor ([[util.smartptr.shared]]); it shares the same control block as `sp`, but its stored pointer points to member `b`. The set treats them as two different elements.

¶1 Let `UP` be `unique_ptr<T, D>`. `hash<UP>` is enabled ([[unord.hash]]) if and only if `hash<typename UP::pointer>` is enabled. When enabled, `hash<UP>()(p)` has the same value as `hash<typename UP::pointer>()(p.get())`. These member functions are not guaranteed to be `noexcept`, because hashing a custom `pointer` type might throw.

¶2 For a `shared_ptr<T>` object `p`, `hash<shared_ptr<T>>()(p)` has the same value as `hash<typename shared_ptr<T>::element_type*>()(p.get())`.

Both are computed from the stored pointer `get()`, consistent with `operator==`, which also compares `get()`. So an aliasing `shared_ptr` and the original `shared_ptr` generally hash differently, even though they share ownership.

To group by ownership, for example to use `weak_ptr` as the key of an unordered container, use C++26's `owner_hash` and `owner_equal` ([[util.smartptr.ownerless]]). `weak_ptr` has no `hash` specialization: it has no `get()`, and its stored pointer could dangle at any moment.
