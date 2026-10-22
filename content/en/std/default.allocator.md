---
title: The default allocator std::allocator
summary: "The contract of std::allocator<T>: storage comes from ::operator new but when and how often it is called is unspecified, allocate begins only the lifetime of the array object without constructing elements, deallocate must be given the same size as the allocation, and allocations in constant evaluation must be released on the spot."
updated: 2026-10-19
---

!!! tldr
    - `std::allocator<T>` has only `allocate`, `allocate_at_least`, `deallocate` and a few type members; the rest of the interface is filled in by `allocator_traits`. It is an empty class, and all instances compare equal.
    - `allocate(n)` begins the lifetime of a `T[n]` array object but constructs no elements; elements have to be constructed one by one with `construct_at`.
    - The `n` in `deallocate(p, n)` must equal the count requested at allocation; otherwise the behavior is undefined, because it may be passed as is to the sized `operator delete`.
    - Storage comes from `::operator new`, but the standard does not specify when or how often it is called, so implementations may merge or omit allocations.
    - Since C++20 these functions are `constexpr`; memory allocated during constant evaluation must be released within the same evaluation.

## The full definition today

```cpp
template<class T> class allocator {
public:
  using value_type                             = T;
  using size_type                              = size_t;
  using difference_type                        = ptrdiff_t;
  using propagate_on_container_move_assignment = true_type;

  constexpr allocator() noexcept;
  constexpr allocator(const allocator&) noexcept;
  template<class U> constexpr allocator(const allocator<U>&) noexcept;
  constexpr ~allocator();
  constexpr allocator& operator=(const allocator&) = default;

  constexpr T* allocate(size_t n);
  constexpr allocation_result<T*> allocate_at_least(size_t n);
  constexpr void deallocate(T* p, size_t n);
};
```

Members such as `pointer`, `rebind`, `construct` and `max_size` are not here; they come from the default rules of [[allocator.traits]]. `std::allocator` is itself a minimal allocator.

### General [default.allocator.general]

¶1 All specializations of `allocator` meet the allocator completeness requirements ([[allocator.requirements.completeness]]): `allocator<T>` is a complete type even if `T` is incomplete. C++17's permission for the element types of `vector`, `list` and `forward_list` to be incomplete when the class definition is instantiated relies on this.

¶2 For any `T`, `allocator_traits<allocator<T>>::is_always_equal::value` is true.

¶2 is about the value of the traits, not a member of `allocator`. That value comes from the traits' default rule: `allocator` is an empty class, so `is_empty<allocator<T>>` is true. C++17 once added an `is_always_equal` member type to `allocator`; the problem was that derived classes inherit it: a stateful allocator derived from `std::allocator` would wrongly claim to always compare equal. The member was deprecated in C++23 and removed in C++26 by [[P2868R3]].

POCMA (`propagate_on_container_move_assignment`) is `true_type`. For an allocator that always compares equal this looks redundant; but with it, a container's move assignment can simply release its own storage and take over the other buffer without comparing allocators.

### Removed members

| Member | Status |
|---|---|
| `pointer`, `const_pointer`, `reference`, `const_reference`, `rebind`, `address`, `max_size`, `construct`, `destroy`, `allocate(n, hint)` | Deprecated in C++17, removed in C++20 |
| The explicit specialization `allocator<void>` | Deprecated in C++17, removed in C++20; the primary template can still instantiate the class definition of `allocator<void>` |
| `is_always_equal` | Deprecated in C++23, removed in C++26 |

All of these members can be obtained from the defaults of `allocator_traits`; keeping them would only encourage users to bypass the traits and call them directly.

## What `allocate` gives you [allocator.members]

```cpp run ok
#include <memory>
#include <string>

constexpr bool f() {
  std::allocator<std::string> a;
  std::string* p = a.allocate(2);   // the array string[2] begins its lifetime, the elements do not
  std::construct_at(p, "x");        // constructs only p[0]
  bool r = p[0] == "x";
  std::string* end = p + 2;         // OK: past-the-end pointer
  (void)end;                        // p[1] was never constructed and cannot be read or written
  std::destroy_at(p);
  a.deallocate(p, 2);
  return r;
}
static_assert(f());

int main() {}
```

¶2 `T` must be a complete type; `allocate` needs to know `sizeof(T)`.

¶3 Returns a pointer to the initial element of an array of `n` `T`.

¶4 Throws `bad_array_new_length` if `numeric_limits<size_t>::max() / sizeof(T) < n`, and `bad_alloc` if the storage cannot be obtained.

¶5 The storage is obtained by calling `::operator new`, but it is unspecified when or how often that function is called. This function starts the lifetime of the array object, but not that of any of the array elements.

The last sentence of ¶5 fixes the place of `allocate` in the object model ([[intro.object]]):

- The array object exists, so the returned `T*` points to an array element, and pointer arithmetic within `[p, p + n]` is valid ([[expr.add]] only allows pointer arithmetic within the same array object). This sentence was added in C++20 by [[P0593R6]]; before that, strictly speaking, `vector` implementations had always been doing pointer arithmetic on an array that did not exist.
- The elements do not exist, so they must be constructed one by one with `construct_at` or `allocator_traits::construct` ([[basic.life]]). Reading or writing an element that has not been constructed is {{ub}}.

The preceding sentence says that when and how often `::operator new` is called is unspecified. This gives implementations freedom to merge or omit allocations, just as [[expr.new]] allows the allocation calls of *new-expression*s to be omitted or merged. So if you replace the global `operator new` to count calls, the count need not match the number of `allocate` calls. Outside constant evaluation libc++ calls `__builtin_operator_new`, a builtin that tells Clang this call enjoys the same omission permission as a *new-expression*.

### Concurrency (¶1)

¶1 Except for the destructor, member functions of the default allocator do not introduce data races when called concurrently from different threads. Calls that allocate or deallocate a particular unit of storage occur in a single total order, and each deallocation happens before the next allocation in that order.

The second sentence means: when a block of memory is freed by one thread and then allocated by another, all of the first thread's writes to it are visible to the second thread, and there is no data race. This is the same guarantee [[new.delete.dataraces]] gives for `operator new` and `operator delete`.

## `allocate_at_least` (¶6–¶9) {{c++23}}

¶7 `allocate_at_least(n)` allocates storage just like `allocate`, but returns `allocation_result<T*>{ptr, count}` with `count >= n` ([[P0401R6]]). For its purpose see [[allocator.traits]]: a container can count the extra space in its capacity. The requirements, exceptions and remarks in ¶6, ¶8 and ¶9 are the same as for `allocate`.

```cpp run ok
#include <cstdio>
#include <limits>
#include <memory>
#include <new>

int main() {
  std::allocator<int> a;
  auto [p, n] = a.allocate_at_least(5);   // an aggregate, so structured bindings work
  std::printf("asked 5, got %zu\n", n);   // libc++: 5
  a.deallocate(p, 5);                     // the second argument can be any value in [5, n]

  try {
    (void)a.allocate(std::numeric_limits<std::size_t>::max() / 2);
  } catch (const std::bad_array_new_length&) {
    std::puts("bad_array_new_length");    // max / sizeof(int) < n
  }
  static_assert(std::allocator<int>() == std::allocator<long>());
}
```

The standard allows `count` to exceed `n` but does not require it. libc++ (Clang 23) returns exactly 5, because the underlying `operator new` cannot report the actual size of the block it got.

## The size passed to `deallocate` (¶10–¶12)

¶10 The precondition requires the sizes to match:

- ¶10.1 if `p` came from `allocate_at_least`, where that call requested `req` and returned `ret`, then `p == ret.ptr` and `req <= n <= ret.count`;
- ¶10.2 otherwise `p` came from `allocate`, and `n` must equal the value originally passed to `allocate`.

Violating it is {{ub}}. Since C++14 `::operator delete` has sized versions, and an implementation may pass `n * sizeof(T)` straight to one. Allocators such as tcmalloc and jemalloc use this size to determine the size class directly instead of looking up metadata, so passing the wrong size corrupts the heap.

¶11–¶12 `deallocate` releases the storage pointed to by `p`, using `::operator delete`; it is unspecified when that function is called.

## Equality [allocator.globals]

¶1 `operator==(const allocator<T>&, const allocator<U>&)` always returns `true`; `!=` is generated by the C++20 rewrite rules. Two `allocator`s with different `T` also compare equal: after rebinding, one can deallocate memory allocated by the other.

## `std::allocator` in constant evaluation

Since C++20 `allocate` and `deallocate` are `constexpr` ([[P0784R7]]), which is the basis for `constexpr std::vector` and `std::string`. An allocation during constant evaluation must be a **transient allocation** ([[g:transient-allocation]]): released within the same evaluation, never carried over to run time ([[expr.const]]).

```cpp run error
#include <memory>
constexpr int* leak() {
  std::allocator<int> a;
  int* p = a.allocate(1);
  std::construct_at(p, 7);
  return p;   // not released within this constant evaluation
}
constexpr int* q = leak();   // error: not a constant expression
```

Clang 23 reports that `q` must be initialized by a constant expression, with a note that a pointer to a heap-allocated object is not a constant expression, and points out where the allocation happened.

The only things that can allocate memory during constant evaluation are *new-expression*s (calling a replaceable global allocation function) and `std::allocator<T>::allocate`. A custom allocator that wants to work in constant evaluation must delegate to `std::allocator` internally.

## Questions

!!! question "Question 1"
    Derive an allocator `Counting<int>` with a counter member from `std::allocator<int>`. What is `allocator_traits<Counting<int>>::is_always_equal` in C++17? In C++26?

<details markdown="1">
<summary>Answer</summary>

In C++17 `std::allocator` has the member `using is_always_equal = true_type;`, `Counting` inherits it, and the traits prefer `Alloc::is_always_equal`, so the result is true. That is wrong: `Counting` has state, and a container's move assignment would simply take over the other buffer. This is exactly why the member was deprecated and removed. In C++26 there is no member to inherit, the traits fall back to `is_empty<Counting<int>>`, and the result is false.
</details>

!!! question "Question 2"
    What happens if you write `n` as 0 when calling `a.deallocate(p, n)`?

<details markdown="1">
<summary>Answer</summary>

Unless the original call was `allocate(0)`, it violates the precondition in ¶10 and is {{ub}}. In practice, if the implementation calls the sized `operator delete(p, 0)`, an allocator that manages memory by size class will put the block on the wrong free list.
</details>
