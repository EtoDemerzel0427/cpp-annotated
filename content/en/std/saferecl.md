---
title: "Safe reclamation: RCU and hazard pointers"
summary: "The two safe-reclamation mechanisms of C++26, RCU and hazard pointers, which solve the problem in lock-free data structures of a writer deleting an object that a reader is still using."
updated: 2026-10-19
---

!!! tldr
    - In a lock-free structure, after a reader obtains a pointer, a writer may already have deleted the object; safe reclamation defers the deletion until no reader is still using it.
    - RCU: readers delimit a read-side critical section with `lock`/`unlock` on an `rcu_domain`, and writers `retire` old objects; deletion waits until every critical section that might have seen the old object has ended.
    - Hazard pointers: a reader uses `protect` to make a hazard pointer point to the object it wants to use; as long as a hazard pointer still points to it, it is not reclaimed.
    - RCU has the lowest reader overhead, but the number of unreclaimed objects is unbounded; hazard pointers must protect each object individually, but the number of unreclaimed objects is bounded.
    - `retire` and `unlock` may also run previously scheduled deleters, so calling them while holding a lock that a deleter needs deadlocks. The libc++ shipped with Clang 23 does not implement these two headers yet.

## The access-deletion race

```cpp
#include <atomic>
struct Node { int value; };
std::atomic<Node*> head{new Node{1}};

int reader() {
  Node* p = head.load(std::memory_order::acquire);
  return p->value;            // *p may already have been deleted
}

void writer() {
  Node* old = head.exchange(new Node{2});
  delete old;                 // reader may still be using old
}
```

After `reader` reads the pointer `p` and before it accesses `*p`, `writer` may already have unlinked and deleted it. Once the two threads interleave like this, `reader`'s access is a use after free, which is undefined behavior. This problem is called an **access-deletion race**.

A mutex solves it, but then every reader has to lock, which defeats the point of a lock-free structure. `atomic<shared_ptr>` ([[util.smartptr.atomic]]) also solves it, but every read has to modify a reference count atomically, which is expensive when reads far outnumber writes.

¶1 The **safe reclamation** techniques of subclause 32.11 are meant for exactly this problem {{c++26}}. Both mechanisms share one idea: the writer does not delete the old object directly but hands it to the library to **retire**, and the library calls the deleter once it has made sure no reader is still using it.

| | RCU ([[P2545R4]]) | Hazard pointers ([[P2530R3]]) |
|---|---|---|
| What readers do | Enter and leave a read-side critical section | Publish once and validate once per pointer used |
| Scope of protection | Every object read inside the critical section | One hazard pointer protects one object |
| When deletion happens | After every critical section that might have seen it has ended | When no hazard pointer points to it any more |
| Number of unreclaimed objects | Unbounded | Bounded |
| Header | `<rcu>` | `<hazard_pointer>` |

!!! impl "Not yet implemented in libc++"
    The libc++ shipped with Clang 23 has neither `<rcu>` nor `<hazard_pointer>`, and neither `__cpp_lib_rcu` nor `__cpp_lib_hazard_pointer` is defined. The code on this page that uses these headers has not been compiled; it is written from the draft wording alone. The reference implementations of both come from the Folly library.

## RCU

### Usage

RCU stands for read-copy update. [[saferecl.rcu.general#1]] says it is suited to linked data structures that are read frequently and updated rarely. It provides no mutual exclusion; instead, it lets the user **schedule** actions such as deletion for some later time.

```cpp
// Not compiled: libc++ has no <rcu> yet
#include <atomic>
#include <mutex>
#include <rcu>
#include <string>

struct Config : std::rcu_obj_base<Config> {
  Config(std::string ep, int t) : endpoint(std::move(ep)), timeout_ms(t) {}
  std::string endpoint;
  int timeout_ms;
};

std::atomic<Config*> current{new Config("localhost", 100)};

int read_timeout() {
  std::scoped_lock rl(std::rcu_default_domain());   // enter the read-side critical section
  Config* c = current.load(std::memory_order::acquire);
  return c->timeout_ms;                              // *c is not deleted inside the critical section
}                                                    // leave the critical section

void update(std::string ep, int t) {                 // assumes writers are mutually excluded elsewhere
  Config* fresh = new Config(std::move(ep), t);
  Config* old = current.exchange(fresh, std::memory_order::acq_rel);
  old->retire();                                     // schedules delete old
}
```

Readers delimit a critical section with `lock`/`unlock` on an `rcu_domain`, here managed by `scoped_lock`. The writer first replaces the pointer with a new object (copy-update), then retires the old one. RCU guarantees that `delete old` runs only after every reader that might have read the old object has left its critical section.

`rcu_domain` meets *Cpp17Lockable*, so the standard RAII locks ([[thread.lock]]) work with it, but it is not mutually exclusive: any number of readers can hold it at once, and `try_lock()` always returns `true`.

### The core guarantee

¶4 The span from a `lock` to its matching `unlock` is a **[[g:region-of-rcu-protection|region of RCU protection]]**, the read-side critical section mentioned above. ¶3 specifies how they pair when nested: within a thread, `lock`/`unlock` on the same domain match like parentheses.

¶5 is the guarantee of RCU as a whole:

!!! std
    Given a region of RCU protection R on a domain dom and given an evaluation E that scheduled another evaluation F in dom, if E does not strongly happen before the start of R, the end of R strongly happens before evaluating F.

In the example above, E is the writer's call to `retire`, F is `delete old`, and R is some reader's critical section. There are two cases:

- If `retire` strongly happens before the reader enters its critical section, the pointer had already been replaced when the reader entered, so it cannot have read `old`, and the deletion need not wait for it.
- Otherwise, the reader may have read `old`, and the deletion must wait until this critical section ends.

Strongly happens before is an inter-thread ordering relation defined in [[intro.races]], stronger than happens before; the difference shows up only when `seq_cst` is mixed with weaker memory orders, so for everyday purposes you can read it as happens before.

¶6 Scheduled deleters may run on any thread, potentially concurrently with each other, and each runs at most once. If several deleters share state, they must synchronize it themselves.

### Two ways to retire

`rcu_obj_base<T, D>` is a CRTP base class. ¶2 says that a type `T` is **rcu-protectable** if it has exactly one public, non-virtual base of type `rcu_obj_base<T, D>` (and no other base `rcu_obj_base<X, Y>`). Such an object can call the member `retire(d, dom)` directly ([[saferecl.rcu.base#9]]); the deleter `D` defaults to `default_delete<T>` and is stored in the base subobject, so this call does not allocate and is `noexcept`.

If you do not want to change the class definition, use the free function `rcu_retire(p, d, dom)` ([[saferecl.rcu.domain.func#8]]). It has to allocate a separate node to record the pointer and the deleter, so it may throw `bad_alloc`; if it throws, nothing is scheduled.

An object may be retired only once ([[saferecl.rcu.base#8]]), and a deleter that exits via an exception is undefined behavior.

### Waiting: rcu_synchronize and rcu_barrier

The two functions wait for different things:

- `rcu_synchronize(dom)` ([[saferecl.rcu.domain.func#2]]) waits for all critical sections that began before the call to end. With it, a writer can skip `retire`: replace the pointer, call `rcu_synchronize()`, then `delete` directly.
- `rcu_barrier(dom)` ([[saferecl.rcu.domain.func#4]]) waits for all deleters scheduled before the call to finish running. Typical uses are draining the pending-deletion queue before unloading a module or exiting the program.

The note in [[saferecl.rcu.domain.func#5]] points out explicitly that neither implies the other.

### Deleters may run on your thread

The member `retire`, `rcu_retire` and `unlock` may all run previously scheduled deleters along the way ([[saferecl.rcu.base#9]], [[saferecl.rcu.domain.members#6]]). If you call them while holding a mutex `m`, and some deleter also locks `m`, the thread deadlocks with itself. The standard warns about this with a note in each of these places.

## Hazard pointers

### Usage

A **hazard pointer** is a single-writer, multi-reader pointer ([[saferecl.hp.general#1]]). It is owned by at most one thread at a time; only the owner may modify it, and any thread may read it. When the owner points it at an object, it tells any thread that might delete that object: this object must not be deleted yet.

Here is the standard's Example 1 ([[saferecl.hp.general#7]]):

```cpp
// Not compiled: libc++ has no <hazard_pointer> yet
struct Name : public hazard_pointer_obj_base<Name> { /* details */ };
atomic<Name*> name;
// called often and in parallel
void print_name() {
  hazard_pointer h = make_hazard_pointer();
  Name* ptr = h.protect(name);          // protection starts
  // ... *ptr can be accessed safely
}                                       // protection ends
// called rarely, but possibly concurrently with print_name
void update_name(Name* new_name) {
  Name* ptr = name.exchange(new_name);
  ptr->retire();
}
```

`make_hazard_pointer()` creates a hazard pointer, and `protect` reads `name` and makes the hazard pointer point to the object read. After the writer retires the old object, it is not reclaimed as long as a hazard pointer still points to it.

As with RCU, ¶2 defines **hazard-protectable** types: those with exactly one public, non-virtual base `hazard_pointer_obj_base<T, D>`. Its `retire(d)` has no domain parameter; the standard interface has no notion of a hazard pointer domain.

### Publish first, then validate

`protect` is equivalent to calling `try_protect` repeatedly until it succeeds ([[saferecl.hp.holder.mem#2]]):

```cpp
T* ptr = src.load(memory_order::relaxed);
while (!try_protect(ptr, src)) {}
return ptr;
```

[[saferecl.hp.holder.mem#5]] specifies that `try_protect(ptr, src)` does four things in order:

1. records `old = ptr`;
2. points the hazard pointer at `old`, publicly declaring that it is going to use it;
3. reads the source again with `src.load(memory_order::acquire)` and stores the result in `ptr`;
4. if `old != ptr`, removes the protection.

Finally it returns `old == ptr`. This is the crux of the hazard pointer algorithm: only by reading the same pointer again after publishing can the reader be sure the object had not been replaced at the time of publication. Any thread that retires it later is then certain to see this hazard pointer.

### When an object may be reclaimed

¶3 divides the time from a hazard pointer's creation to its destruction into **[[g:protection-epoch|protection epochs]]**. In each epoch it is either associated with one object or unassociated; every change of association (even to the same object) ends the old epoch and starts a new one. ¶4 and ¶5 define that an object `x` is **retired** when `retire` is called on it and **reclaimed** when its deleter is invoked.

¶6 defines when `x` is **possibly-reclaimable** with respect to an evaluation A, i.e. the condition under which A may reclaim it. Roughly: `x` has been retired and not yet reclaimed, and every protection epoch associated with `x` that began before the retirement has ended before A.

"Began before the retirement" can be established in two ways (¶6.3.1, ¶6.3.2):

- the start of the epoch happens before the retirement;
- the epoch was started by `try_protect`, whose load read a value of `src` from before some modification B of it, and B happens before the retirement. This corresponds to the situation in Example 1: the reader read the old pointer before the `exchange`, and even though there is no happens-before relation between the two, the reader's epoch must still protect the old object.

¶7 says the number of possibly-reclaimable objects has an unspecified upper bound, which may for example be a function of the number of hazard pointers and the number of threads. This is the advantage of hazard pointers over RCU: a slow reader cannot make memory grow without bound.

### hazard_pointer objects

`hazard_pointer` is a move-only handle that is either empty or owns one hazard pointer ([[saferecl.hp.holder.general#1]]). An empty handle differs from a handle owning an unassociated hazard pointer: the former has no hazard pointer at all and cannot call `protect`.

- Default construction gives an empty handle; use `make_hazard_pointer()` to obtain a real hazard pointer, which may throw `bad_alloc` when memory runs out.
- The destructor destroys the owned hazard pointer, thereby ending the current protection epoch.
- `reset_protection(p)` switches to protecting `p`, and `reset_protection()` removes protection.
- `swap` only exchanges ownership; the hazard pointers themselves keep protecting the same objects, and no epoch begins or ends.
- `make_hazard_pointer_batch` and `clear_hazard_pointer_batch` respectively create hazard pointers for the empty elements, or destroy those of the non-empty elements, of a `span<hazard_pointer>` in one go.

## How to choose

If reads are extremely frequent, critical sections are short, and you can tolerate a temporary pile-up of objects awaiting deletion, choose RCU. Entering and leaving a critical section is usually just incrementing and decrementing a thread-local counter.

If readers may hold an object for a long time, or unreclaimed memory must be bounded, choose hazard pointers. The cost is a publish plus a validation for each object protected, plus whatever fences the implementation needs.

In read-mostly workloads both are faster than `atomic<shared_ptr>`, because readers do not modify any shared counter.

## Pitfalls

!!! pitfall "Calling retire or unlock under a lock a deleter needs"
    RCU's `retire`, `rcu_retire` and `unlock`, and the hazard pointer `retire`, may all run previously scheduled deleters on the current thread. Calling them while holding a lock that a deleter needs may deadlock.

!!! pitfall "Retiring twice"
    The preconditions of both kinds of `retire` require that the object has not been retired before. Retiring twice is undefined behavior, which usually shows up as a double free.

!!! pitfall "Blocking inside an RCU critical section"
    If a reader stays in its critical section for a long time, none of the objects retired after that can be reclaimed, memory keeps growing, and `rcu_synchronize` blocks the whole time. Do not do I/O or wait for other threads inside a critical section.

<details class="fine" markdown="1"><summary>Remaining wording</summary>

- [[saferecl.rcu.base]] ¶2–¶6: adding specializations of `rcu_obj_base` is undefined behavior; `T` may be an incomplete type, but must be complete before any member of the specialization is referenced; `D` must be a function object type callable as `d(ptr)` that meets *Cpp17DefaultConstructible* and *Cpp17MoveAssignable*; if `D` is trivially copyable, so is `rcu_obj_base<T, D>`.
- [[saferecl.hp.base]] ¶1–¶4: the corresponding requirements for `hazard_pointer_obj_base`.
- [[saferecl.rcu.domain.members]]: calls to `lock` and `unlock` do not themselves introduce data races involving the domain; the precondition of `unlock` is that a previous `lock` has not yet been closed; it closes the most recently opened region.
- [[saferecl.rcu.domain.func#1]]: `rcu_default_domain()` returns the same object of static storage duration every time.
- [[saferecl.rcu.domain.func#6]], ¶7: `rcu_retire` requires `D` to be move constructible and `d(p)` to be well-formed.

</details>
