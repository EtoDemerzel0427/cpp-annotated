---
title: enable_shared_from_this
summary: "Letting an object managed by shared_ptr safely obtain a shared_ptr to itself that shares ownership with the existing owners: who sets the internal weak-this and when, why bad_weak_ptr is thrown when the object is not owned, and the pitfalls of private inheritance, multiple inheritance and copying."
updated: 2026-10-19
---

!!! tldr
    - Writing `shared_ptr<X>(this)` in a member function creates a second ownership group and leads to a double delete; `shared_from_this()` returns a `shared_ptr` that shares ownership with the existing owners.
    - It works through a `weak_ptr` hidden in the base class (exposition-only name *weak-this*), filled in by the `shared_ptr` constructor that creates the first ownership group, or by `make_shared`.
    - When the object is not owned by any `shared_ptr` (including while its own constructor runs), `shared_from_this()` throws `bad_weak_ptr` and `weak_from_this()` returns an empty pointer.
    - The base class must be accessible: `class X : enable_shared_from_this<X>` is private inheritance, gives no diagnostic at all, and makes `shared_from_this()` always throw.
    - Copying an object does not copy *weak-this*; the copy belongs to its own owners.

## Getting another shared_ptr from inside the object

```cpp run title="shared-from-this.cpp" ok
#include <memory>
#include <cstdio>

struct Session : std::enable_shared_from_this<Session> {
    Session() {
        try { auto self = shared_from_this(); }          // during construction
        catch (const std::bad_weak_ptr&) { std::puts("in ctor: bad_weak_ptr"); }
    }
};
class Hidden : std::enable_shared_from_this<Hidden> {   // class inherits privately by default
public:
    bool ok() { return !weak_from_this().expired(); }
};
struct Copyable : std::enable_shared_from_this<Copyable> {};

int main() {
    auto s = std::make_shared<Session>();
    std::printf("use_count = %ld\n", s->shared_from_this().use_count());   // 2

    Session local;                                        // not owned by a shared_ptr
    try { (void)local.shared_from_this(); }
    catch (const std::bad_weak_ptr&) { std::puts("stack object: bad_weak_ptr"); }

    auto h = std::make_shared<Hidden>();
    std::printf("private base: %d\n", h->ok());           // 0

    auto c1 = std::make_shared<Copyable>();
    auto c2 = std::make_shared<Copyable>(*c1);
    std::printf("c2 owns itself: %d\n", c2->shared_from_this() == c2);   // 1
}
```

In our tests the output is, in order: `in ctor: bad_weak_ptr`, `use_count = 2`, `in ctor: bad_weak_ptr` (constructing `local`), `stack object: bad_weak_ptr`, `private base: 0`, `c2 owns itself: 1`. Each is explained below.

The typical use case is asynchronous I/O: a session object captures a `shared_ptr` to itself in a callback, guaranteeing that the session is still alive when the callback runs. Writing `shared_ptr<Session>(this)` directly creates a new ownership group, and it and the existing group outside would each delete the object once ([[util.smartptr.shared]]). What is needed is a `shared_ptr` that shares the same control block as the existing owners.

## Interface [util.smartptr.enab]

¶1 A class `T` can inherit from `enable_shared_from_this<T>` to inherit the member function `shared_from_this`, which obtains a `shared_ptr` pointing to `*this`. This is the CRTP pattern: the base class takes the derived class as its template argument. ¶2 In Example 1, the `q` returned by `p->shared_from_this()` compares equal to `p`, and `p.owner_equal(q)`.

```cpp
template<class T> class enable_shared_from_this {
protected:
  constexpr enable_shared_from_this() noexcept;
  constexpr enable_shared_from_this(const enable_shared_from_this&) noexcept;
  constexpr enable_shared_from_this& operator=(const enable_shared_from_this&) noexcept;
  constexpr ~enable_shared_from_this();
public:
  constexpr shared_ptr<T>       shared_from_this();
  constexpr shared_ptr<T const> shared_from_this() const;
  constexpr weak_ptr<T>       weak_from_this() noexcept;
  constexpr weak_ptr<T const> weak_from_this() const noexcept;
private:
  mutable weak_ptr<T> weak-this;  // exposition only
};
```

The special member functions are all `protected`, so it can only be used as a base class. ¶3 `T` may be an incomplete type; in `struct X : enable_shared_from_this<X>`, `X` really is still incomplete when the base class is instantiated.

¶7 `shared_from_this()` returns `shared_ptr<T>(weak-this)`; ¶8 `weak_from_this()` returns *weak-this*.

## Who sets weak-this

`enable_shared_from_this` never writes *weak-this* itself. It is written by `shared_ptr`'s constructors, by the "enables shared_from_this" rule in [[util.smartptr.shared]] ([util.smartptr.shared.const] ¶1): if `Y` has an unambiguous and accessible base class that is a specialization of `enable_shared_from_this`, and `p->weak-this` has expired, `p->weak-this` is made to share ownership with the new `shared_ptr`. Only the routes that create a new ownership group do this:

- `shared_ptr(Y* p)`, `shared_ptr(Y* p, D d)`, `shared_ptr(Y* p, D d, A a)`, when `T` is not an array;
- `shared_ptr(unique_ptr<Y, D>&&)`, which is equivalent to one of the above;
- `make_shared` and `allocate_shared` ([util.smartptr.shared.create] ¶10).

The aliasing constructor, copying and construction from `weak_ptr` do not set *weak-this*; they do not create a new ownership group.

### When not owned: bad_weak_ptr is thrown

The way ¶7 is written determines the behavior on failure: constructing a `shared_ptr` from an expired `weak_ptr` throws `bad_weak_ptr` ([util.smartptr.shared.const] ¶27). So calling `shared_from_this()` on an object not owned by any `shared_ptr` throws `bad_weak_ptr`. `weak_from_this()` instead returns an empty `weak_ptr` and does not throw.

C++17's [[P0033R1]] established this behavior and added `weak_from_this()`. In C++11 and C++14, `shared_from_this()` had a precondition that some `shared_ptr` owning `*this` must exist, and violating it was UB.

Calling `shared_from_this()` in the constructor always fails: the object is not fully constructed yet, and `make_shared` or the `shared_ptr` constructor has not reached the step that sets *weak-this*. A class that needs to register itself elsewhere at creation can use a private constructor plus a static factory function: the factory does `make_shared` first and then calls an `init()` that does the registration. The same holds in the destructor: by then the strong count is zero and *weak-this* has expired.

### Copying does not pass on weak-this (¶4–¶6)

¶4 Both default construction and copy construction value-initialize *weak-this*, i.e. leave it empty. ¶5–¶6 Copy assignment returns `*this`, and Note 1 points out that *weak-this* is unchanged.

This is necessary. A copy of an object is a new object, and its owners (if any) have nothing to do with the original. If *weak-this* were copied, the copy's `shared_from_this()` would return a `shared_ptr` pointing to the original object: the right type, but the wrong address. In the example, `c2` is copy-constructed from `*c1`, and `c2->shared_from_this()` correctly equals `c2`.

## Pitfalls

### Private inheritance

The "enables" condition requires the base class to be accessible ([[class.access.base]]). `class X : enable_shared_from_this<X>` is private inheritance; the `shared_ptr` constructor cannot see the base class and silently does not set *weak-this*, with no diagnostic at all, and `shared_from_this()` always throws. `Hidden` in the example is exactly this case. Write the base as `public`, or use `struct`.

### Two enable_shared_from_this bases

```cpp run title="two-bases.cpp" impl
#include <memory>
#include <cstdio>
struct A : std::enable_shared_from_this<A> {};
struct B : std::enable_shared_from_this<B> {};
struct C : A, B {};
int main() {
    auto c = std::make_shared<C>();
    std::printf("A: %d B: %d\n", !c->A::weak_from_this().expired(),
                                 !c->B::weak_from_this().expired());
}
```

`C` has two base classes that are different specializations of `enable_shared_from_this`, each unambiguous and accessible on its own. The standard's wording says "has such a base class" and does not say what happens when there are two. libc++ (with Clang 23) prints `A: 0 B: 0`: it sets neither. Avoid this design: usually only the topmost common base class inherits `enable_shared_from_this`, and derived classes get a pointer of the derived type with `std::static_pointer_cast<Derived>(shared_from_this())`.

C++23's explicit object parameters ([[dcl.fct]]) let this cast be written as one generic helper, with `Self` deduced as the caller's actual type:

```cpp run title="shared-from-self.cpp" ok
#include <memory>
#include <cstdio>
struct Base : std::enable_shared_from_this<Base> {
    template<class Self>
    auto shared_from(this Self& self) {
        return std::static_pointer_cast<Self>(self.shared_from_this());
    }
    virtual ~Base() = default;
};
struct Derived : Base { int v = 7; };
int main() {
    auto d = std::make_shared<Derived>();
    std::shared_ptr<Derived> p = d->shared_from();
    std::printf("%d %ld\n", p->v, d.use_count());   // 7 2
}
```

### Concurrency

The assignment that sets *weak-this* is not atomic and conflicts with any potentially concurrent access to the same object (the last sentence of [util.smartptr.shared.const] ¶1). If the object's address is seen by another thread before it is handed to a `shared_ptr`, that thread calling `weak_from_this()` and the construction of the `shared_ptr` form a data race.

## Questions

!!! question "Question 1"
    `X` inherits from `enable_shared_from_this<X>`. What happens with `auto p = std::shared_ptr<X>(new X); auto q = std::shared_ptr<X>(p.get());`?

<details markdown="1">
<summary>Answer</summary>

It is still double-delete UB. When `q` is constructed, `p->weak-this` has not expired, so it is not overwritten, but `q` still creates a second control block and owns the same object. `enable_shared_from_this` only provides a correct way to get another `shared_ptr`; it cannot prevent the wrong way.
</details>

!!! question "Question 2"
    What type does calling `shared_from_this()` on a `const X` object return? Why is *weak-this* `mutable`?

<details markdown="1">
<summary>Answer</summary>

It returns `shared_ptr<const X>`. In `shared_ptr<const X>(new const X)`, `Y` is `const X`, and the statement that enables shared_from_this assigns to `p->weak-this` through a `p` of type `const X*`; only a `mutable` member can be modified that way. The `const_cast<remove_cv_t<Y>*>(p)` in the same statement lets the newly created `shared_ptr<X>` point to the object.
</details>

## Summary

- *weak-this* is set by the `shared_ptr` constructor that creates a new ownership group, or by `make_shared`, provided the base class is unambiguous and accessible.
- When the object is not owned, `shared_from_this()` throws `bad_weak_ptr` (since C++17) and `weak_from_this()` returns empty.
- `shared_from_this()` cannot be used in the constructor or the destructor.
- Neither copy construction nor copy assignment passes on *weak-this*.
