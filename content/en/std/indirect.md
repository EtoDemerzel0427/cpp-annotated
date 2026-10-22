---
title: indirect
summary: "C++26's indirect<T>: a T on the heap that still has T's value semantics: copying copies the T, const propagates, it compares and hashes by value, and it can be valueless only after being moved from; plus the rules for construction, assignment, swap and allocator propagation."
updated: 2026-10-19
---

!!! tldr
    - `indirect<T>` behaves like a member of type `T`: copying copies the `T`, a `const indirect<T>` only gives out `const T&`, and `==` and `<=>` compare the value of the `T`.
    - It has no empty state. Even default construction allocates memory and constructs a `T`; it becomes valueless only after being moved from.
    - The requirements on `T` for copying, default construction and so on are written as *Mandates* rather than *Constraints*, so `T` may be incomplete; the price is that `is_copy_constructible_v<indirect<T>>` is true even for a non-copyable `T`.
    - Copy assignment assigns to the `T` directly when the allocators are equal, and otherwise constructs a new object before destroying the old one; after move assignment the source is always valueless.
    - In comparisons, a valueless object is less than any object with a value, and two valueless objects compare equal.

The design motivation for `indirect<T, Allocator = allocator<T>>` is in [[mem.composite.types]]. At the time of writing libc++ (with Clang 23) does not implement it yet, so none of the examples below have been compiled.

## Usage

```cpp
#include <memory>
#include <string>
#include <vector>

struct Expr;                                    // a recursive type
struct Binary { char op; std::indirect<Expr> lhs, rhs; };
struct Expr { std::string name; std::vector<Binary> children; };

struct Widget {
    std::indirect<std::string> name{"widget"};
    void rename(const char* s) { *name = s; }
    std::size_t len() const { return name->size(); }   // name-> is const std::string*
};

int main() {
    Widget a;
    Widget b = a;                               // implicit copy constructor: copies the string
    b.rename("other");                          // a is unaffected
    Widget c = std::move(a);
    bool gone = a.name.valueless_after_move();  // true
    a.name = std::string("revived");            // assigning a value gives it a value again
    bool eq = (a.name == std::string("revived"));   // comparison with T: true
}
```

`Expr` is still incomplete when `Binary` declares its `indirect<Expr>` members, and that is allowed. `Widget` does not need any hand-written special member functions: the implicit copy constructor copies the owned string, the implicit move constructor takes over the pointer, and in the `const` member function `len()`, `*name` is `const std::string&`.

## General [indirect.general]

¶1 An `indirect` object manages the lifetime of an **owned object**. When it has no owned object it is **valueless** ([[g:valueless]]). It can only become valueless after being moved from.

¶2 `allocator_traits<Allocator>::value_type` must be the same as `T`, otherwise the program is ill-formed. ¶3 Constructing an owned object with `args...` using allocator `a` means calling `allocator_traits<Allocator>::construct(a, p, args...)`, where `p` comes from `allocator_traits<Allocator>::allocate`. So `pmr::indirect<T>` performs uses-allocator construction of `T` ([[allocator.uses]]); for example, an owned `pmr::string` also allocates from the same memory resource.

¶4 The exposition-only member *alloc* can be replaced only by assignment or `swap`, and whether it is replaced is decided by the allocator's `propagate_on_container_copy_assignment`, `propagate_on_container_move_assignment` and `propagate_on_container_swap`, by the same rules as for containers ([[allocator.traits]]). Below they are abbreviated POCCA, POCMA and POCS.

¶5 `T` must not be a non-object type, an array, a specialization of `in_place_t` or `in_place_type_t`, or a cv-qualified type. ¶6 `T` may be an incomplete type. ¶7 `Allocator` must meet *Cpp17Allocator*. ¶8 A program that declares an explicit or partial specialization of `indirect` has undefined behavior.

The only exposition-only data members are `pointer p` and `Allocator alloc`, so for an empty allocator type implementations can usually make `indirect<T>` the size of a pointer.

## Construction [indirect.ctor]

¶2 No constructor throws unless `allocate` or `construct` throws.

| Constructor | Requirements | Effect |
|---|---|---|
| `indirect()` (¶3–¶5) | *Constraints*: the allocator is default constructible; *Mandates*: `T` is default constructible | Constructs a value-initialized `T` |
| `indirect(allocator_arg_t, a)` (¶6–¶7) | *Mandates*: `T` is default constructible | Same, using `a` |
| Copy constructor (¶8–¶9) | *Mandates*: `T` is copy constructible | The allocator is `select_on_container_copy_construction(other.alloc)`; if `other` is valueless the result is valueless, otherwise copies `*other` |
| Copy with an allocator (¶10–¶11) | Same | Uses the given `a` |
| Move constructor, `noexcept` (¶12–¶13) | None | Moves the allocator and takes over `other`'s pointer; `other` is then valueless |
| Move with an allocator (¶14–¶16) | *Mandates*: `T` is complete if `is_always_equal` is false | If the allocators are equal, takes over the pointer; otherwise constructs a new object from `*std::move(other)`; `other` is then valueless |
| `indirect(U&& u)` (¶17–¶20) | *Constraints*: `U` is not `indirect` or `in_place_t`, and `is_constructible_v<T, U>` | Constructs from `std::forward<U>(u)` |
| `indirect(in_place_t, us...)` (¶21–¶24) | *Constraints*: `is_constructible_v<T, Us...>` | Constructs in place |
| `indirect(in_place_t, ilist, us...)` (¶25–¶28) | *Constraints*: `is_constructible_v<T, initializer_list<I>&, Us...>` | Constructs in place |

¶3–¶5 Default construction allocates memory and constructs a `T`, unlike `unique_ptr`, which defaults to null.

Apart from copy and move, all constructors are `explicit`, including the default constructor. `indirect<std::string> s = "hi";` does not work; you write `indirect<std::string> s("hi");`, so there is never an invisible heap allocation.

!!! lawyer "The explicit default constructor and aggregate initialization"
    A member of an aggregate that is neither explicitly initialized nor has a default member initializer is copy-initialized from an empty initializer list per [[dcl.init.aggr]], and copy-list-initialization cannot select an `explicit` constructor. So `struct A { std::indirect<int> p; int x; }; A a{};` and `A b{.x = 1};` are both ill-formed, while `A a;` is fine. In our tests with a stand-in class having an `explicit` default constructor, Clang 23 reports `chosen constructor is explicit in copy-initialization`. Giving the member a default member initializer, such as `std::indirect<int> p{};`, avoids the problem.

¶8 The copy constructor's requirement on `T` is a *Mandates*, not a *Constraints*. *Constraints* would have to check `T` during overload resolution, when `T` may still be incomplete; *Mandates* is checked only when the function is actually instantiated. The price is that for a non-copyable `T`, `is_copy_constructible_v<indirect<T>>` is still true, and the error appears only on an actual copy.

¶12 The move constructor is unconditionally `noexcept`: it always takes over the pointer and leaves `other` valueless. The valueless state is exactly the price paid for this.

The deduction guide is `indirect(Value) -> indirect<Value>`; `indirect(allocator_arg_t, Allocator, Value)` deduces the allocator rebound to `Value`.

## Destruction [indirect.dtor]

¶1 *Mandates*: `T` is a complete type. ¶2 If not valueless, destroys the owned object with `allocator_traits::destroy` and then deallocates the storage. As with `unique_ptr` for pimpl, the enclosing class's destructor must be defined where `Impl` is complete.

## Assignment [indirect.assign]

### Copy assignment (¶1–¶4)

¶1 *Mandates*: `T` is copy assignable and copy constructible. ¶2 Self-assignment has no effect; otherwise:

- ¶2.1 If POCCA is true, the allocator needs updating.
- ¶2.2 If `other` is valueless: `*this` becomes valueless too, and the old object is destroyed and deallocated.
- ¶2.3 Otherwise, if the two allocators are equal and `*this` is not valueless: equivalent to `**this = *other`, copy-assigning the owned object directly and reusing the existing storage.
- ¶2.4 Otherwise, constructs a new object as a copy of `*other` using `*this`'s allocator (or `other`'s, if it needs updating).
- ¶2.5, ¶2.6 Destroys and deallocates the old object, and replaces the allocator if it needs updating.

¶4 If an exception is thrown, the result of `valueless_after_move()` is unchanged. If the exception comes from `T`'s copy constructor, there are no effects; if it comes from `T`'s copy assignment, the state of the owned object depends on the exception safety guarantee of `T`'s copy assignment itself.

This is a compromise: when the storage can be reused it assigns directly, which is fast but carries only the guarantee of `T`'s assignment operator; when it cannot, it constructs a new object before destroying the old one, which gives the strong exception guarantee.

### Move assignment (¶5–¶9)

`noexcept(POCMA || is_always_equal)`. ¶5 When POCMA and `is_always_equal` are both false, the *Mandates* requires `T` to be move constructible, because with unequal allocators the only option is to construct a new object ([[LWG4251]] relaxed this requirement from copy constructible to move constructible).

- ¶6.3 If the allocator needs updating or the two are equal, `*this` takes over `other`'s owned object.
- ¶6.4 Otherwise, constructs a new object using `*this`'s allocator, from `other`'s owned object as an rvalue.

¶7 Whichever path is taken, `other` is valueless after the assignment. ¶9 If an exception is thrown, neither `*this` nor `other` changes.

### Assignment from a value (¶10–¶12)

`template<class U = T> indirect& operator=(U&& u)`: ¶10 the *Constraints* require that `U` is not `indirect` and that `T` is both constructible and assignable from `U`. ¶11 If `*this` is valueless, constructs a new object from `u`; otherwise equivalent to `**this = std::forward<U>(u)`. To give a valueless object a value again, use this, or assign it another `indirect` that has a value.

## Observers [indirect.obs]

```cpp
constexpr const T&  operator*() const &  noexcept;
constexpr T&        operator*() &        noexcept;
constexpr const T&& operator*() const && noexcept;
constexpr T&&       operator*() &&       noexcept;
constexpr const_pointer operator->() const noexcept;
constexpr pointer       operator->() noexcept;
```

`operator*` of a `const indirect<T>` returns `const T&` and `operator->` returns `const_pointer`; this is `const` propagation. ¶3–¶4 Dereferencing an rvalue `indirect` gives `T&&`, so `auto x = *std::move(ind);` moves from the owned object; `ind` itself still has a value, but the object is in a moved-from state.

¶1, ¶3, ¶5 The precondition of dereferencing is that `*this` is not valueless; violating it is UB. ¶7 `valueless_after_move()` queries whether it is valueless, and ¶8 `get_allocator()` returns *alloc*.

## Swap [indirect.swap]

`noexcept(POCS || is_always_equal)`. ¶1 Precondition: if POCS is true, the allocators are swappable; otherwise the two allocators must be equal. As with containers, swapping when the allocators are unequal and do not propagate is UB. ¶2 It swaps the states of the two objects, i.e. the pointers to the owned objects or the valueless state; Note 1 points out that `swap` is not called on the owned objects.

## Comparison and hashing [indirect.relops] [indirect.comp.with.t] [indirect.hash]

`indirect` compares by value:

- [indirect.relops] ¶1–¶2 `==` between two `indirect`s: if either is valueless, returns whether both are valueless; otherwise returns `*lhs == *rhs`. The *Mandates* requires `*lhs == *rhs` to be well-formed and convertible to `bool`.
- ¶3 `<=>`: if either is valueless, returns `!lhs.valueless_after_move() <=> !rhs.valueless_after_move()`, i.e. a valueless one is less than one with a value; otherwise returns *synth-three-way*`(*lhs, *rhs)`. *synth-three-way* works even when `T` only has `<` ([[expr.spaceship]]).
- [indirect.comp.with.t] Comparison with a value of `T`: if `lhs` is valueless, `==` is `false` and `<=>` is `strong_ordering::less`.

[indirect.hash] ¶1 `hash<indirect<T, Allocator>>` is enabled if and only if `hash<T>` is enabled. When there is a value, the result equals `hash<T>()(*i)`; when valueless, it is an implementation-defined value. The member functions are not guaranteed to be `noexcept`.

## Questions

!!! question "Question 1"
    When the allocators are unequal, `indirect`'s move assignment has to construct a new object, and `other`'s object is in fact still there. Why does the postcondition still require `other` to be valueless?

<details markdown="1">
<summary>Answer</summary>

To make the result independent of the allocators. If the copying path kept `other`'s object, the state the caller sees would depend on whether the two allocators are equal, a condition only known at run time. Making it valueless uniformly means the caller always sees the same result, and it also frees the storage `other` was using.
</details>

!!! question "Question 2"
    What is `std::is_copy_constructible_v<std::indirect<std::unique_ptr<int>>>`?

<details markdown="1">
<summary>Answer</summary>

`true`. The copy constructor has no *Constraints*, only a *Mandates* (¶8), so it participates in overload resolution and the trait reports that it can be copied; only when the copy constructor is actually instantiated does the unmet *Mandates* make the program ill-formed. This is the price of supporting incomplete `T`; trait detection on `std::vector<std::unique_ptr<int>>` shows the same phenomenon.
</details>

## Summary

- `indirect<T>` is a `T` on the heap plus value semantics: it copies the `T`, compares and hashes by value, and propagates both `const` and value category.
- Default construction allocates and constructs a `T`; there is no empty state, only the valueless state after being moved from.
- Copy assignment assigns directly when the storage can be reused, otherwise constructs before destroying; move assignment takes over the pointer when the allocators are equal or propagate, and the source is always valueless afterwards.
- In comparisons a valueless object is the smallest, and two valueless objects compare equal.
- Many requirements are *Mandates* rather than *Constraints*, to support incomplete types.
