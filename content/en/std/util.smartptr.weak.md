---
title: weak_ptr
summary: "weak_ptr observes an object managed by shared_ptr without owning it: a shared_ptr can be obtained only atomically through lock(), comparison is by ownership only, and it is commonly used for caches, observers and breaking reference cycles."
updated: 2026-10-19
---

!!! tldr
    - `weak_ptr` keeps the control block alive but not the object; after the object is destroyed, `weak_ptr` can still reliably report that.
    - It has no `operator*`, `operator->` or `get()`; the only way to access the object is `lock()`, which atomically checks whether the object is alive and obtains a `shared_ptr`.
    - Calling `expired()` and then `lock()` is a race; the correct way is `if (auto sp = w.lock())`.
    - `weak_ptr` can only be compared and hashed by ownership, and such comparisons remain stable after the object is destroyed, so `weak_ptr` can be a container key.
    - Two objects pointing to each other with `shared_ptr` are never released; changing the back-pointing side to `weak_ptr` breaks the cycle.

## Breaking reference cycles

```cpp run title="break-cycle.cpp" ok
#include <memory>
#include <cstdio>
struct Node {
    std::shared_ptr<Node> next;     // owns the next node
    std::weak_ptr<Node>   prev;     // only observes the previous node
    ~Node() { std::puts("~Node"); }
};
int main() {
    auto a = std::make_shared<Node>();
    auto b = std::make_shared<Node>();
    a->next = b;
    b->prev = a;
    std::weak_ptr<Node> w = b;
    if (auto sp = w.lock())
        std::printf("alive, use_count=%ld\n", sp.use_count());   // 3
}
```

In our tests it prints `alive, use_count=3` (`b`, `a->next` and `sp`), then `~Node` twice. If `prev` were also a `shared_ptr`, the counts of `a` and `b` would both still be 1 at the end of `main`, neither node would be destroyed, and the memory would leak. `shared_ptr` is just reference counting, with no cycle detection.

Which side uses `weak_ptr` depends on the direction of ownership: the owner holds a `shared_ptr` (a parent owns its children, a container owns its elements), and the owned side uses `weak_ptr` when pointing back at the owner.

## What weak_ptr is [util.smartptr.weak.general]

¶1 `weak_ptr` stores a weak reference to an object that is already managed by a `shared_ptr`. To access the object, convert it to a `shared_ptr` with the member function `lock()`. ¶2 It is copy constructible and copy assignable, and `T` may be an incomplete type.

In the physical model of [[util.sharedptr]], `weak_ptr` is also two pointers: the stored pointer and the control block pointer. What it increments is the weak count in the control block. When the strong count reaches zero the object is destroyed, but the control block is released only when the weak count also reaches zero, so `weak_ptr` can always safely query whether the object is still there.

The interface deliberately has no `operator*`, `operator->` or `get()`. The observed object could be destroyed by another thread at any moment, and any direct access would have a race between check and use. The `shared_ptr` returned by `lock()`, by contrast, guarantees the object stays alive within its scope.

## Construction, assignment and destruction [util.smartptr.weak.const]

¶1–¶2 Default construction gives an empty `weak_ptr` that stores a null pointer, with `use_count() == 0`.

¶3–¶5 Copying from a `weak_ptr` or `shared_ptr`: the template versions require `Y*` to be compatible with `T*` ([[util.smartptr.shared#6]]). If `r` is empty, the result is empty; otherwise the result shares ownership with `r` and stores a copy of the pointer stored in `r`.

¶6–¶8 After move construction, `r` is empty and stores a null pointer.

Destruction ([util.smartptr.weak.dest] ¶1) destroys only the `weak_ptr` itself and has no effect on the object its stored pointer points to. Assignment ([util.smartptr.weak.assign]) is defined, as for `shared_ptr`, as constructing a temporary and then `swap`ping, and ¶3 allows the implementation not to actually create the temporary. `reset()` is equivalent to `weak_ptr().swap(*this)`. The deduction guide `weak_ptr(shared_ptr<T>) -> weak_ptr<T>` lets you write `std::weak_ptr w = sp;` directly.

### Converting an expired weak_ptr

Converting `shared_ptr<Derived>` to `shared_ptr<Base>` only needs a derived-to-base conversion of the stored pointer. For `weak_ptr` it is trickier: the object might already be destroyed, and the stored pointer dangling. If `Base` is a virtual base class, the conversion has to read information in the object to compute the address of the base class subobject, and doing that on a destroyed object is UB. ¶4 only says that a copy of the pointer stored in `r` is stored; how to obtain that copy safely is left to the implementation.

libc++ always calls `lock()` first and then constructs from the resulting `shared_ptr`:

```cpp run title="convert-expired.cpp" impl
#include <memory>
#include <cstdio>
struct B { int x; };
struct D : B {};
int main() {
    std::weak_ptr<D> w;
    { auto sp = std::make_shared<D>(); w = sp; }   // w has expired, but is not empty
    std::weak_ptr<B> wb = w;                        // per ¶4: shares ownership with w
    std::weak_ptr<B> empty;
    bool same = !w.owner_before(wb) && !wb.owner_before(w);
    bool is_empty = !wb.owner_before(empty) && !empty.owner_before(wb);
    std::printf("same group: %d, empty: %d\n", same, is_empty);
}
```

With libc++ in our tests it prints `same group: 0, empty: 1`. `w` has expired, `lock()` returns an empty `shared_ptr`, so `wb` becomes an empty `weak_ptr` and no longer belongs to the same ownership group as `w`. By ¶4, `w` is not empty (expired is not the same as empty), so the result should share ownership with `w`. This is an observable difference between libc++ and the standard's wording: if a container uses expired `weak_ptr`s as keys, the keys before and after conversion are no longer equivalent under ownership comparison.

## Observers [util.smartptr.weak.obs]

¶1 `use_count()` returns 0 if empty, otherwise the number of `shared_ptr`s that share ownership with it. ¶2 `expired()` returns `use_count() == 0`.

!!! std "[util.smartptr.weak.obs]/3"
    *Returns*: `expired() ? shared_ptr<T>() : shared_ptr<T>(*this)`, executed atomically.

The key in ¶3 is "executed atomically". Checking that the strong count is nonzero and incrementing it must be one indivisible step; otherwise another thread could take the count to 0 and destroy the object between the two steps. Implementations typically use a compare-exchange loop that increments the count only when it is nonzero.

!!! pitfall "Calling `expired()` before `lock()`"
    ```cpp
    if (!w.expired()) {
        auto sp = w.lock();   // sp may still be null
        sp->f();              // may dereference a null pointer
    }
    ```
    The result of `expired()` can be stale as soon as it returns; only a `true` result is stable, because a destroyed object never comes back to life. The correct way is `if (auto sp = w.lock()) { ... }`.

¶4–¶7 `owner_before`, `owner_hash` and `owner_equal` are the same as the `shared_ptr` members of the same names; see [[util.smartptr.ownerless]]. After a `weak_ptr` expires, the control block still exists at the same address, so the results of these comparisons do not change. This is exactly why `weak_ptr` can be the key of ordered or unordered containers.

`weak_ptr` has no `operator==`, no `operator<` and no `std::hash` specialization. Its stored pointer may dangle, so comparing by stored pointer is meaningless.

<details class="fine" markdown="1"><summary>Remaining wording</summary>

[util.smartptr.weak.mod] ¶1: the member `swap` exchanges the contents of two objects. [util.smartptr.weak.spec] ¶1: the non-member `swap(a, b)` is equivalent to `a.swap(b)`.

</details>

## Questions

!!! question "Question 1"
    If you use `std::map<Key, std::weak_ptr<Value>>` as a cache, will it grow without bound?

<details markdown="1">
<summary>Answer</summary>

Yes. After an object is destroyed, the expired `weak_ptr` stays in the map. If the object was created by `make_shared`, the object and the control block are in the same allocation, the weak count never reaches zero, and none of that memory is released ([[util.sharedptr]]). Expired entries need to be cleaned up periodically, or `erase`d whenever `lock()` fails.
</details>

!!! question "Question 2"
    In a single thread, how does `w.lock().use_count()` relate to `w.use_count()` evaluated just before it?

<details markdown="1">
<summary>Answer</summary>

If the object is still alive, the former is 1 greater than the latter, because the `shared_ptr` returned by `lock()` itself counts as an owner. Note 2 on `use_count` in [[util.smartptr.shared]] makes exactly this point: `weak_ptr::lock()` affects the value returned by `use_count()`.
</details>

## Summary

- `weak_ptr` extends the life of the control block, not of the object.
- The object can be accessed only through `lock()`, which atomically checks and obtains a `shared_ptr`; `expired()` can only be trusted when it returns `true`.
- Comparison and hashing are by ownership only, and the results do not change after expiry, so it can be a container key.
- The owner holds a `shared_ptr` and the side pointing back holds a `weak_ptr`; this breaks cycles.
