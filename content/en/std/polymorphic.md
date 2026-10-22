---
title: polymorphic
summary: "C++26's polymorphic<T>: holds an object of T or a class derived from it and copies by dynamic type, replacing unique_ptr<Base> plus a virtual clone(); why construction requires the derived class to be copyable, why a moved-from object is not necessarily valueless, and why there are no comparisons."
updated: 2026-10-19
---

!!! tldr
    - `polymorphic<T>` holds an object of `T` or of a public class derived from it. Copying calls the copy constructor of the actual type, with no slicing and no virtual `clone()` needed in the base class.
    - Destruction uses the actual type, so `T`'s destructor need not be virtual.
    - A type put into a `polymorphic` must be copyable, and this is checked with *Constraints* at construction.
    - The move constructor allows the implementation to move-construct a new object instead of taking over the pointer, leaving room for a small-object optimization, so a moved-from object is not necessarily valueless.
    - Copy assignment always constructs before destroying, giving the strong exception guarantee; there is no assignment from a value, and no comparison or hashing.

## An old problem

When a class has a polymorphic member and the enclosing class should still be copyable, the traditional code looks like this:

```cpp
struct Shape {
    virtual ~Shape() = default;
    virtual double area() const = 0;
    virtual std::unique_ptr<Shape> clone() const = 0;   // every derived class must implement it
};
struct Scene {
    std::vector<std::unique_ptr<Shape>> shapes;
    Scene(const Scene& o) {                             // hand-written deep copy
        for (auto& s : o.shapes) shapes.push_back(s->clone());
    }
    // copy assignment must be hand-written too
};
```

Rewritten with `polymorphic<Shape>`:

```cpp
#include <memory>
#include <vector>

struct Shape {                       // no clone() needed, and the destructor need not be virtual
    virtual double area() const = 0;
protected:
    ~Shape() = default;
};
struct Circle : Shape {
    double r;
    explicit Circle(double r) : r(r) {}
    double area() const override { return 3 * r * r; }
};
struct Square : Shape {
    double a;
    explicit Square(double a) : a(a) {}
    double area() const override { return a * a; }
};

struct Scene {
    std::vector<std::polymorphic<Shape>> shapes;   // the implicit copy is a deep copy
};

int main() {
    Scene s;
    s.shapes.emplace_back(std::in_place_type<Circle>, 1.0);
    s.shapes.emplace_back(Square(2.0));
    Scene t = s;                                   // each element is copied by its dynamic type
    static_cast<Square&>(*t.shapes[1]).a = 3.0;
    // s.shapes[1]->area() == 4.0, t.shapes[1]->area() == 9.0
}
```

`polymorphic<Shape>` remembers the actual type at construction and calls that type's copy constructor when copying. At the time of writing libc++ (with Clang 23) does not implement `std::polymorphic` yet, so this code has not been compiled. The design motivation and what it shares with [[indirect]] are covered in [[mem.composite.types]].

## General [polymorphic.general]

¶1 A `polymorphic` object manages the lifetime of an owned object, and can own objects of different types at different points in its lifetime; for example, assignment can replace a `Circle` with a `Square`. With no owned object it is valueless, and it can only become valueless after being moved from, as with [[indirect]].

¶2 `allocator_traits<Allocator>::value_type` must be `T`. ¶3 Constructing an owned object of type `U` using allocator `a` means calling `allocator_traits<Allocator>::construct(a, p, args...)`, where `p` points to storage suitable for `U`. The allocator's `value_type` is `T` while what is constructed is a `U`, so the implementation has to rebind the allocator to an internal type that contains `U`.

¶4 The allocator can be replaced only by assignment or `swap`, by the same rules as for containers ([[allocator.traits]]). ¶5–¶8 are the same as for `indirect`: `T` must not be a non-object type, an array, a specialization of `in_place_t` or `in_place_type_t`, or a cv-qualified type; `T` may be incomplete; declaring specializations is UB.

The only exposition-only data member is `Allocator alloc`; the standard deliberately leaves the internal representation unspecified. Implementations usually store a pointer to a control block holding the owned object and a set of type-erased operations (copy, destroy), conceptually similar to the control block of `shared_ptr` but without reference counts.

## Construction [polymorphic.ctor]

¶2 No constructor throws unless `allocate` or `construct` throws.

### Default construction (¶3–¶7)

*Mandates*: `T` is default constructible and copy constructible. The effect is to construct a `T`. Abstract classes cannot be default-constructed, so the default constructor of `polymorphic<Shape>` cannot be used; it must be constructed from a concrete derived class.

### Construction from a value or in place (¶12–¶23)

```cpp
template<class U = T> explicit polymorphic(U&& u);
template<class U, class... Ts> explicit polymorphic(in_place_type_t<U>, Ts&&... ts);
```

Let `UU = remove_cvref_t<U>`. The *Constraints* include:

- `derived_from<UU, T>`: it must be `T` itself or a class derived from it, and [[concept.derived]] requires public, unambiguous derivation;
- `is_copy_constructible_v<UU>`: the derived class must be copyable;
- `UU` is neither `polymorphic` itself nor a specialization of `in_place_type_t`;
- the `in_place_type_t<U>` version also requires `U` to be neither cv-qualified nor a reference, i.e. `is_same_v<remove_cvref_t<U>, U>`.

Why require copyability at construction? `polymorphic` unconditionally provides a copy constructor, and the copy constructor (¶8) has no *Mandates* at all. To guarantee that every `polymorphic` with a value can be copied, the dynamic type of an object must be confirmed copyable when it enters the `polymorphic`: on default construction the dynamic type is `T`, so ¶4 requires `T` to be copyable; when constructing from `U` the dynamic type is `U`, so `U` is required to be copyable here.

*Constraints* rather than *Mandates* is used here because at the point of construction the derived type `U` is necessarily complete, so there is no need to make concessions for incomplete types.

### Copy construction (¶8–¶9)

¶8 The allocator is `select_on_container_copy_construction(other.alloc)`; if `other` is valueless the result is valueless; otherwise it constructs an owned object of type `U`, where `U` is the type of `other`'s owned object, with that object as the argument. It uses the copy constructor of the dynamic type `U`, not of `T`, so there is no slicing even if `T` has a public copy constructor.

### Move construction (¶10–¶11)

!!! std "[polymorphic.ctor]/10"
    … either `*this` takes ownership of the owned object of `other` or, owns an object of the same type constructed from the owned object of `other` considering that owned object as an rvalue, using the allocator *alloc*.

¶10 Move construction has two permitted outcomes: take over `other`'s owned object, or move-construct a new object of the same type from it as an rvalue. The latter leaves room for a small buffer optimization: an implementation may store small objects directly inside the `polymorphic`, and such objects can only be move-constructed when moved, not taken over by pointer.

So `polymorphic`'s move constructor has no postcondition that `other` becomes valueless, unlike `indirect`. On the small-object path, `other` still has a value, just in a moved-from state. The move constructor is unconditionally `noexcept`, so an implementation can only put types whose move constructor does not throw into the internal buffer.

¶11 Move construction with an allocator: when the allocators are equal, it is again either take-over or move construction; when they are not, it constructs a new `U` from the rvalue using *alloc*. Its `noexcept` depends on `is_always_equal`.

## Destruction [polymorphic.dtor]

¶1 *Mandates*: `T` is complete. ¶2 If not valueless, calls `allocator_traits<Allocator>::destroy` with a `U*` pointing to the owned object, where `U` is the type of the owned object, and then deallocates the storage. Destruction is by dynamic type, so `T`'s destructor need not be virtual; in the example above, `Shape`'s destructor is even `protected`. Like `shared_ptr`, it remembers the type at construction, unlike `unique_ptr<Base>`.

## Assignment [polymorphic.assign]

### Copy assignment (¶1–¶4)

¶1 *Mandates*: `T` is complete. Unlike `indirect`, it always constructs before destroying:

- ¶2.2 if `other` is not valueless, constructs a new object of type `U` (`other`'s dynamic type) with `allocator_traits::construct`, using `*this`'s allocator, or `other`'s if it needs updating;
- ¶2.3 destroys and deallocates the old object; ¶2.4 replaces the allocator if it needs updating.
- ¶4 If an exception is thrown, `*this` is unchanged; this is the strong exception guarantee.

`indirect` assigns to the owned object directly when the allocators are equal, but `polymorphic` cannot: `*this` may hold a `Circle` and `other` a `Square`, and there is no assignment operator to call.

### Move assignment (¶5–¶8)

`noexcept(POCMA || is_always_equal)`, where POCMA is the allocator's `propagate_on_container_move_assignment`. ¶5 When both are false, the *Mandates* requires `T` to be complete. ¶6 If the allocator needs updating or the two are equal, it takes over `other`'s object; otherwise it constructs a new `U` from the rvalue. ¶8 If an exception is thrown, neither `*this` nor `other` changes.

`polymorphic` has no `operator=(U&&)` for assignment from a value. To switch to a new object, write `p = std::polymorphic<Shape>(std::in_place_type<Square>, 2.0);`.

## Observers and swap [polymorphic.obs] [polymorphic.swap]

¶1–¶4 `operator*` returns `T&` or `const T&`, `operator->` returns `pointer` or `const_pointer`, the precondition is not being valueless, and `const` propagates here too. There are no rvalue overloads as in `indirect`, because moving a `T` out of a `polymorphic` would slice. ¶5 `valueless_after_move()` and ¶6 `get_allocator()` are the same as for `indirect`.

The rules for swap ([polymorphic.swap]) are also the same as for `indirect`: `noexcept(POCS || is_always_equal)`; UB when the allocators are unequal and do not propagate; it swaps states and does not call `swap` on the owned objects. In an implementation with a small-object optimization, swapping states may require move-constructing objects.

## No comparison or hashing

`indirect` can delegate `==` and `<=>` to `T`, but `polymorphic` cannot. The two objects' dynamic types may differ, and the base class's `operator==` can only compare the base part, which would most likely give the wrong answer. The standard chooses to provide nothing rather than a misleading version.

## Questions

!!! question "Question"
    After `std::polymorphic<Shape> p(std::in_place_type<Circle>, 1.0);` and then `std::polymorphic<Shape> q = std::move(p);`, is `p.valueless_after_move()` necessarily true?

<details markdown="1">
<summary>Answer</summary>

Not necessarily. ¶10 allows the implementation to move-construct a new object of the same type from the rvalue, in which case `p` still owns a moved-from `Circle`, and the standard gives the move constructor no postcondition that `other` is valueless. `p` is valueless only if the implementation chooses to take over the pointer. Portable code should not depend on whether `p` has a value after the move, and should only assume it can be assigned to or destroyed.
</details>

## Summary

- `polymorphic<T>` holds an object of `T` or a public class derived from it, copies and destroys by dynamic type, and needs neither a virtual `clone()` nor a virtual destructor.
- A type entering a `polymorphic` must be copyable, checked with *Constraints* at construction.
- Move construction may take over the pointer or move-construct a new object, so a moved-from object is not necessarily valueless.
- Copy assignment always constructs before destroying, giving the strong exception guarantee; there is no assignment from a value, and no comparison or hashing.
