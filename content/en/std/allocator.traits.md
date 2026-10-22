---
title: Allocator traits
summary: "allocator_traits is the only interface through which containers use an allocator; it fills in defaults for the members an allocator leaves out, and decides whether the allocator moves along when a container is assigned or swapped."
updated: 2026-10-19
---

!!! tldr
    - An allocator only needs to provide `value_type`, `allocate`, `deallocate`, a converting constructor and `==`; `allocator_traits` fills in defaults for the remaining members, and containers use allocators only through `allocator_traits`.
    - The three `propagate_on_container_*` members decide whether the allocator is replaced along with the contents on copy assignment, move assignment and swap; by default it is never replaced.
    - On move assignment, if the allocator neither propagates nor compares equal, the container cannot take over the other buffer and has to move the elements one by one; the same situation on swap is undefined behavior.
    - `is_always_equal` defaults to `is_empty<Alloc>`; together with POCMA it decides whether a container's move assignment can be declared `noexcept`.
    - `construct`/`destroy` default to calling `construct_at`/`destroy_at`; an allocator can define them itself, which is what uses-allocator construction relies on. Specializing `allocator_traits` is not allowed.

## A minimal allocator

```cpp run ok
#include <cstdio>
#include <memory>
#include <new>
#include <type_traits>
#include <vector>

// minimal allocator: value_type, allocate, deallocate, converting constructor, ==
template<class T>
struct Mini {
  using value_type = T;
  int id;
  explicit Mini(int i) : id(i) {}
  template<class U>
  Mini(const Mini<U>& o) noexcept : id(o.id) {}
  T* allocate(std::size_t n) {
    std::printf("  [%d] allocate %zu\n", id, n);
    return static_cast<T*>(::operator new(n * sizeof(T)));
  }
  void deallocate(T* p, std::size_t) noexcept {
    ::operator delete(p);
  }
  friend bool operator==(const Mini& a, const Mini& b) {
    return a.id == b.id;
  }
};

using Tr = std::allocator_traits<Mini<int>>;
static_assert(std::is_same_v<Tr::pointer, int*>);
static_assert(std::is_same_v<Tr::size_type, std::size_t>);
static_assert(std::is_same_v<Tr::rebind_alloc<long>, Mini<long>>);
static_assert(!Tr::propagate_on_container_move_assignment::value);
static_assert(!Tr::is_always_equal::value);   // Mini is not an empty class

int main() {
  std::vector<int, Mini<int>> a({1, 2, 3}, Mini<int>(1));
  std::vector<int, Mini<int>> b(Mini<int>(2));
  std::puts("b = std::move(a):");
  b = std::move(a);   // cannot take over a's buffer
  std::printf("  b.size()=%zu, b alloc id=%d\n", b.size(),
              b.get_allocator().id);
}
```

Output with Clang 23 and libc++:

```text
  [1] allocate 3
b = std::move(a):
  [2] allocate 3
  b.size()=3, b alloc id=2
```

`Mini` does not define `pointer`, `size_type`, `construct` or the other members; `allocator_traits` supplies defaults for them, and `vector` works just the same. The move assignment on the last line does not take over `a`'s buffer; instead it allocates again with `b`'s allocator. The reason is the allocator propagation rules, described below.

The C++98 allocator requirements were a long list of members that had to be written by hand, and implementations were allowed to assume that allocators of the same type always compare equal, which made stateful allocators practically unusable. C++11 cut the allocator requirements down to the few items above ([[allocator.requirements.general]]), introduced `allocator_traits` to fill in the rest, and required standard containers to access allocators only through it ([[container.alloc.reqmts]]).

## General [allocator.traits.general]

¶1 makes three rules:

- `allocator_traits` provides a uniform interface to all allocator types.
- An allocator must be a class type, even if `allocator_traits` could supply its whole required interface. Note 1 gives the reason: so that it is always possible to derive from an allocator. `scoped_allocator_adaptor` ([[allocator.adaptor]]) derives from its outer allocator, and library implementations often rely on derivation or `[[no_unique_address]]` to make empty allocators take up no space.
- A program that declares an explicit or partial specialization of `allocator_traits` is {{ifndr}} (ill-formed, no diagnostic required). This was added in C++23 by [[P2652R2]]. Containers depend on the exact behavior of `allocator_traits`; to customize behavior, change the allocator itself.

## Member types [allocator.traits.types]

Every member type follows the same rule: if `Alloc` has a member type of the same name, use it; otherwise use the default.

| Member | Default |
|---|---|
| ¶1 `pointer` | `value_type*` |
| ¶2 `const_pointer` | `pointer_traits<pointer>::rebind<const value_type>` |
| ¶3 `void_pointer` | `pointer_traits<pointer>::rebind<void>` |
| ¶4 `const_void_pointer` | `pointer_traits<pointer>::rebind<const void>` |
| ¶5 `difference_type` | `pointer_traits<pointer>::difference_type` |
| ¶6 `size_type` | `make_unsigned_t<difference_type>` |
| ¶7 `propagate_on_container_copy_assignment` | `false_type` |
| ¶8 `propagate_on_container_move_assignment` | `false_type` |
| ¶9 `propagate_on_container_swap` | `false_type` |
| ¶10 `is_always_equal` | `is_empty<Alloc>::type` |
| ¶11 `rebind_alloc<T>` | `Alloc::rebind<T>::other`; otherwise replace the first argument of `Alloc<U, Args...>` with `T`; ill-formed if neither works |

All the pointer types are derived from `pointer` via [[pointer.traits]], so an allocator only has to define a fancy `pointer` and gets the rest. `value_type` has no default; it is the only type member an allocator must provide. The three propagation members are often abbreviated POCCA, POCMA and POCS.

`rebind_alloc` is used a lot, because containers rarely allocate `value_type` itself. `std::list<int, A>` allocates list nodes, `std::map` allocates tree nodes, and `allocate_shared` allocates a control block. They use `rebind_alloc<Node>` to get the type `A<Node>` from `A<int>`, then convert-construct an `A<Node>` object from the `A<int>` object they hold. That is why an allocator must support `template<class U> A(const A<U>&)`.

## Allocator propagation

A container's allocator can only be replaced on assignment or `swap`, and only when the corresponding `propagate_on_container_*::value` is true ([[container.reqmts#64]]). An allocator represents who owns the memory: a container allocated from arena A should usually stay in arena A after being assigned to, so the default is not to propagate.

### Copy assignment

For `a = b`, if POCCA is true, `a`'s allocator is replaced with a copy of `b`'s allocator; if the two are not equal, `a` first has to release its old storage with the old allocator. If POCCA is false, `a` keeps its own allocator, uses it to allocate new storage and copies the elements.

### Move assignment

`a = std::move(b)` has three cases:

1. POCMA is true: release `a`'s storage, replace the allocator, take over `b`'s buffer. Constant time, no exceptions.
2. POCMA is false, but the two allocators are equal: equality means one can deallocate memory allocated by the other, so the buffer is taken over just the same.
3. POCMA is false and the allocators are not equal: `a`'s allocator cannot deallocate `b`'s memory, so the buffer cannot be taken over. The only option is to allocate again with `a`'s allocator and move the elements one by one. Linear time, may throw. The example at the top is this case.

Case 3 can only be detected at run time by comparing the allocators. To declare move assignment `noexcept`, it has to be ruled out at compile time. If POCMA is true, or `is_always_equal` is true, case 3 cannot happen. So `vector`'s move assignment is declared like this ([[vector.overview]]), and so are the move assignments of `indirect` and `polymorphic`:

```cpp
constexpr vector& operator=(vector&& x)
  noexcept(allocator_traits<Allocator>::propagate_on_container_move_assignment::value ||
           allocator_traits<Allocator>::is_always_equal::value);
```

`is_always_equal` defaults to `is_empty<Alloc>`: an allocator with no data members has no distinguishable instances. `std::allocator` is an empty class and also sets POCMA to `true_type` ([[default.allocator]]).

### Swap

For `a.swap(b)`, if POCS is true the allocators are swapped too. If POCS is false the allocators are not swapped, and if they are not equal the behavior is undefined ([[container.reqmts#65]]).

```cpp run ub
#include <memory_resource>
#include <vector>

int main() {
  std::pmr::monotonic_buffer_resource r1, r2;
  std::pmr::vector<int> a({1, 2}, &r1), b({3}, &r2);
  a.swap(b);   // UB: POCS is false and the allocators are not equal
}
```

`polymorphic_allocator` does not define the propagation members, so POCS takes the default false ([[mem.poly.allocator.class]]). So swapping two `pmr::vector`s using different resources is undefined behavior. In our tests with a default build, the program ends normally, but the two vectors have swapped buffers without swapping allocators, and `a` will later use `r1` to deallocate memory that came from `r2`. With `-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_EXTENSIVE`, the program traps at the `swap` and terminates.

| Operation | Member | With the default (false) | Consequence when not propagating and the allocators are unequal |
|---|---|---|---|
| Copy assignment | POCCA | Keep the left-hand allocator | No extra cost |
| Move assignment | POCMA | Keep the left-hand allocator | Element-wise move, linear time, may throw |
| Swap | POCS | Do not swap the allocators | {{ub}} |

### Copy construction

On copy construction, the new container has no existing allocator to keep. The container calls `select_on_container_copy_construction(rhs.get_allocator())` to decide the new container's allocator (¶9, [[container.reqmts#64]]), which by default returns a copy of `rhs`. `polymorphic_allocator` customizes it to return a default-constructed allocator, i.e. one using `get_default_resource()`: a copy does not inherit the original's arena.

## Static member functions [allocator.traits.members]

| Function | When `Alloc` provides it | Otherwise |
|---|---|---|
| ¶1 `allocate(a, n)` | `a.allocate(n)` (required) | |
| ¶2 `allocate(a, n, hint)` | `a.allocate(n, hint)` | `a.allocate(n)` |
| ¶3 `allocate_at_least(a, n)` | `a.allocate_at_least(n)` | `{a.allocate(n), n}` |
| ¶4–¶5 `deallocate(a, p, n)` | `a.deallocate(p, n)`, throws nothing | |
| ¶6 `construct(a, p, args...)` | `a.construct(p, args...)` | `construct_at(p, args...)` |
| ¶7 `destroy(a, p)` | `a.destroy(p)` | `destroy_at(p)` |
| ¶8 `max_size(a)` | `a.max_size()` | `numeric_limits<size_type>::max() / sizeof(value_type)` |
| ¶9 `select_on_container_copy_construction(rhs)` | `rhs.select_on_container_copy_construction()` | `rhs` |

### `construct` and `destroy` (¶6–¶7)

¶6–¶7 default to calling `construct_at` and `destroy_at` ([[specialized.construct]]), both `constexpr`. C++20 removed `std::allocator::construct`, so a `std::vector` in constant evaluation constructs its elements via `allocator_traits::construct`, which lands on `construct_at`.

The second parameter of `construct` is `T*`, not `pointer`. Even when the allocator uses fancy pointers, construction is passed a plain pointer, and the container converts with `to_address` ([[pointer.traits]]).

An allocator can define `construct` itself; this is the entry point for uses-allocator construction ([[allocator.uses]]): `polymorphic_allocator` and `scoped_allocator_adaptor` pass the allocator to the element's constructor in their own `construct`. Another common use is making `construct(U* p)` with no extra arguments perform `::new(p) U`, so that `vector<double, A>(n)` does not zero the elements.

### `allocate_at_least` (¶3)

¶3 was added in C++23 by [[P0401R6]]. Underlying allocators usually round up to size classes, so the space actually obtained exceeds the request. `allocate_at_least` lets the allocator return the actual count as well, and `vector` can count the extra in its `capacity()`, reducing later reallocations.

The return type `allocation_result<pointer, size_type>` is an aggregate with just two data members, `ptr` and `count`. [allocator.traits.other] ¶1 specifies that it has no other bases or members, so structured bindings can be used on it. When the allocator does not provide this function, the default result is `{a.allocate(n), n}`.

### The rest

¶5 `deallocate` throws nothing. Containers call it in destructors and exception cleanup paths, where it must not throw again.

¶8 The default of `max_size` is only a theoretical upper bound. Container implementations usually also take the smaller of it and `numeric_limits<difference_type>::max()`, because the number of elements must be representable as a difference of iterators.

## Questions

!!! question "Question 1"
    For a stateful arena allocator, what are the options for making a container's move assignment both `noexcept` and constant time? What does each cost?

<details markdown="1">
<summary>Answer</summary>

- Set POCMA to `true_type`: the allocator is replaced on move assignment. The cost is that the assigned-to container moves to another arena. If the program relies on container X's memory always being in arena A, for example to release A wholesale later, that assumption breaks.
- Set `is_always_equal` to `true_type`: correct only when all instances really can deallocate each other's memory, for example when they share one global arena. Declaring it for a truly stateful allocator makes the container take over the other buffer and then release it with its own allocator, which is undefined behavior.
- Set neither: accept linear time and possible exceptions. This is the path `pmr` takes; both POCMA and `is_always_equal` are false for `polymorphic_allocator`, so `pmr::vector`'s move assignment is not `noexcept`.
</details>

!!! question "Question 2"
    Why does `is_always_equal` default to `is_empty<Alloc>` rather than `true_type`?

<details markdown="1">
<summary>Answer</summary>

An empty class has no state, two instances of the same type cannot be told apart, and inferring that they always compare equal is safe. A non-empty class may have state, such as a pointer to an arena; defaulting to true would make containers wrongly take over buffers on move assignment and swap. Conversely, an allocator with data members that is nonetheless always equal (for example one with a debug counter that shares the global heap) needs to declare `using is_always_equal = std::true_type;` explicitly.
</details>

!!! question "Question 3"
    Can you specialize `std::allocator_traits<MyAlloc>` to add a `construct`?

<details markdown="1">
<summary>Answer</summary>

No. ¶1 specifies that a program declaring an explicit or partial specialization of `allocator_traits` is {{ifndr}}. The correct approach is to add a `construct` member to `MyAlloc` itself; `allocator_traits::construct` calls it in preference.
</details>
