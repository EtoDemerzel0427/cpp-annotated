---
title: Specialized <memory> algorithms
summary: "Algorithms that create and destroy objects in uninitialized storage: automatic destruction of already-constructed objects on exceptions, why the destination iterator must not throw, the difference between default-initialization and value-initialization, the state of the source objects after uninitialized_move fails, and construct_at, destroy_at and destroy."
updated: 2026-10-19
---

!!! tldr
    - Ordinary algorithms assign to objects that already exist; the algorithms in this subclause create objects in raw storage with placement new, or end objects' lifetimes.
    - If an exception is thrown partway through construction, the objects already constructed are destroyed automatically before the exception propagates further.
    - The destination iterator must be a forward iterator, and its increment, comparison and dereference must not throw, because rolling back walks the destination range again.
    - `uninitialized_default_construct` does nothing for types like `int`; `uninitialized_value_construct` zeroes them.
    - `construct_at` makes it possible to construct an object at a given location even during constant evaluation; it is what allowed `std::vector` to become `constexpr` in C++20.

## Assignment versus construction

```cpp run title="uninit_rollback.cpp" flags="-std=c++2c -fsanitize=address,undefined" ok
#include <cassert>
#include <memory>
#include <stdexcept>
#include <string>

static int live = 0;
struct T {
    std::string s;
    explicit T(const std::string& x) : s(x) {
        if (x == "boom") throw std::runtime_error("boom");
        ++live;
    }
    T(const T& o) : T(o.s) {}
    ~T() { --live; }
};

int main() {
    std::string src[] = {"a", "b", "boom", "c"};
    alignas(T) unsigned char buf[sizeof(T) * 4];   // raw storage, no T objects
    T* p = reinterpret_cast<T*>(buf);
    try {
        // the 3rd construction throws
        std::uninitialized_copy(std::begin(src), std::end(src), p);
    } catch (const std::runtime_error&) {
        assert(live == 0);   // the already-constructed "a" and "b" have been destroyed automatically
    }
}
```

`buf` is just a block of bytes with no `T` objects in it. Doing `std::copy` into it would mean assigning to objects that do not exist, which is undefined behavior ([[basic.life]]). `std::uninitialized_copy` instead creates a new object at each position with placement new ([[expr.new]]).

Components that manage their own storage, such as `vector`, `optional` and memory pools, are built from these algorithms. For example, when a `vector` grows, it roughly does an `uninitialized_move` (or copy) into the new storage, then `destroy`s the elements in the old storage.

## General ([specialized.algorithms.general])

¶1 The contents of this subclause are declared in `<memory>`.

!!! std
    Unless otherwise specified, if an exception is thrown in the following algorithms, objects constructed by a placement *new-expression* are destroyed in an unspecified order before allowing the exception to propagate.

¶2 specifies the behavior on exceptions: objects already constructed by placement new are destroyed in unspecified order before the exception propagates further. For the destination range, either everything is constructed successfully, or it goes back to having no objects. The caller does not need to track how far construction got; in the example above, `live` returns to 0.

¶3 Note 1 reminds us that when these algorithms create new objects in a region of storage, the lifetime of any object that occupied that storage ends ([[basic.life]]).

¶4 defines two exposition-only function templates:

```cpp
template<class T>
  constexpr void* voidify(T& obj) noexcept {
    return addressof(obj);
  }

template<class I>
  constexpr decltype(auto) deref-move(I& it) {
    if constexpr (is_lvalue_reference_v<decltype(*it)>)
      return std::move(*it);
    else
      return *it;
  }
```

`voidify` uses `addressof` rather than `&` so as not to be affected by an overloaded `operator&`. It returns `void*` so that `::new (p) T` calls the global placement allocation function, without letting a class's own `operator new` interfere.

`addressof(obj)` is implicitly converted to `void*`, and that conversion is invalid when `obj` is a const object. So objects cannot be constructed at locations a const iterator points to. libc++ in our tests rejects `std::uninitialized_fill(const int*, const int*, 1)` with `static_cast from 'const int *' to 'void *' is not allowed`. Earlier wording used `const_cast` to strip cv-qualification and allowed this; it was later changed to the current form.

*deref-move* moves from `*it` when it is an lvalue reference, and otherwise (for example, when the iterator returns a prvalue) uses the result of `*it` directly. This is more accurate than an unconditional `std::move(*it)`.

## Destination iterators must not throw ([special.mem.concepts])

The rollback of ¶2 requires the implementation, after an exception, to walk the already-constructed destination range again from the start and destroy each object. This places two requirements on the destination iterator:

- It must be a forward iterator, able to make multiple passes;
- Its increment, copy, comparison and dereference must not throw. If another exception were thrown during rollback, the rollback could not be completed.

The `std` versions express this requirement in the template parameter name `NoThrowForwardIterator` (¶4.5 of [[algorithms.requirements#4]]). The `ranges` versions express it with a set of exposition-only concepts: *nothrow-input-iterator*, *nothrow-forward-iterator*, *nothrow-sentinel-for* and so on; C++26's parallel versions also use *nothrow-random-access-iterator* and others.

¶1, in defining *nothrow-input-iterator*, also requires `iter_reference_t<I>` to be an lvalue reference whose type, with cv and reference removed, is the value type. The construction target must be real storage; iterators that return proxy objects do not qualify.

The no-throw part is a semantic requirement (¶2, ¶4 and so on) that the compiler cannot check. The notes on each say that these concepts allow some operations that the corresponding standard iterator concepts permit to throw; the difference lies only in whether the type models the concept.

## Default construction and value construction ([uninitialized.construct.default], [uninitialized.construct.value])

Their effects are equivalent to, respectively:

```cpp
for (; first != last; ++first)
  ::new (voidify(*first)) iterator_traits<I>::value_type;    // default construction
for (; first != last; ++first)
  ::new (voidify(*first)) iterator_traits<I>::value_type();  // value construction
```

The only difference is a pair of `()`.

Default-initialization does nothing for types like `int`; the object's value is whatever the storage held. For dynamic storage obtained from an allocator, that is an **indeterminate value**, and reading it is {{ub}}. C++26's erroneous values apply only to objects with automatic storage duration; see [[basic.indet]]. Value-initialization zeroes such objects.

Default construction is used for `make_unique_for_overwrite`, buffers whose contents need no initialization, and the like, saving the cost of zeroing.

The `_n` versions return where construction ended; the `ranges` `_n` versions are defined in terms of `counted_iterator`.

## `uninitialized_copy` and `uninitialized_move` ([uninitialized.copy], [uninitialized.move])

The precondition of [uninitialized.copy] ¶1 is that the destination range does not overlap the source range at all. `std::copy` allows some overlap; here no overlap at all is allowed: the destination is uninitialized storage, which should not coincide with existing objects anyway. The effect in ¶2 is `::new (voidify(*result)) value_type(*first)` at each destination position.

The `ranges` versions (¶4–¶5) take two ranges, stop when either is exhausted, and return `{input position, output position}`. The output has an end, so there is no writing out of bounds.

`uninitialized_move` has the same structure, except that it obtains the source objects with *deref-move* (`std` versions) or `ranges::iter_move` (`ranges` versions). The notes in [uninitialized.move] ¶5 and ¶10 say that if an exception is thrown, some objects in the source range are left in a valid but unspecified state. The destination range is rolled back, but source objects already moved from cannot be restored.

That is exactly the dilemma of `vector` growth. Using `uninitialized_move` may lose the strong exception guarantee, so `vector` moves only when the element's move constructor is `noexcept` (or the element is not copyable), and copies otherwise; that is what `move_if_noexcept` is for.

[uninitialized.move] ¶7 The classic `uninitialized_move_n` returns a pair of positions `{first, result}`, while `uninitialized_copy_n` returns only `result`.

## `uninitialized_fill` ([uninitialized.fill])

¶1 performs `::new (voidify(*first)) value_type(x)` at each position, copy-constructing from `x`.

## `construct_at` ([specialized.construct]) {{c++20}}

```cpp
template<class T, class... Args>
  constexpr T* construct_at(T* location, Args&&... args);
```

¶1 *Constraints*: `T` is not an array of unknown bound, and `::new (declval<void*>()) T(declval<Args>()...)` is well-formed. ¶2 *Mandates*: if `T` is an array type, there are no constructor arguments. ¶3 If `T` is an array, it performs `::new (voidify(*location)) T[1]()`, value-initializing the whole array; otherwise it performs `::new (voidify(*location)) T(std::forward<Args>(args)...)`.

C++20 allowed `std::construct_at` and `std::allocator<T>::allocate` in constant expressions, but not placement new written directly ([[P0784R7]]). `std::vector` became `constexpr` in C++20 thanks to `construct_at`. Since C++26, placement new can also be written directly in constant expressions, and Clang 23 already supports it.

`construct_at` initializes with parentheses, so `construct_at<Agg>(p, 1, 2)` works for aggregates too, since aggregates support parenthesized initialization from C++20 on ([[dcl.init.general]]).

## `destroy_at`, `destroy`, `destroy_n` ([specialized.destroy])

¶1 `destroy_at(location)` destroys each element in turn for an array type (arrays supported since C++20), and otherwise calls `location->~T()`.

¶2 `destroy(first, last)` calls `destroy_at(addressof(*first))` on each element, from front to back. Arrays and standard containers generally destroy their elements in reverse order when destroyed; the order here is the opposite.

¶3 The `ranges` version of `destroy` requires only *nothrow-input-iterator*. Destruction needs no rollback, so a single pass suffices.

```cpp run title="construct_at_constexpr.cpp" ok
#include <memory>

struct Agg { int x, y; };

constexpr int f() {
    std::allocator<int> a;
    int* p = a.allocate(3);
    int src[3] = {1, 2, 3};
    std::uninitialized_copy(src, src + 3, p);  // constexpr since C++26
    std::destroy_at(p);
    std::construct_at(p, 10);                  // replace the first element
    int r = p[0] + p[1] + p[2];
    std::destroy(p, p + 3);
    a.deallocate(p, 3);
    return r;
}
static_assert(f() == 15);

constexpr int g() {
    std::allocator<Agg> a;
    Agg* p = a.allocate(1);
    std::construct_at(p, 1, 2);                // parenthesized aggregate initialization
    int r = p->y;
    std::destroy_at(p);
    a.deallocate(p, 1);
    return r;
}
static_assert(g() == 2);

int main() {}
```

!!! history "Evolution"
    - C++98: `uninitialized_copy`, `uninitialized_fill`, `uninitialized_fill_n`;
    - C++17: `uninitialized_default_construct`, `uninitialized_value_construct`, `uninitialized_move`, `destroy_at`, `destroy` ([[P0040R3]]), and parallel overloads;
    - C++20: `construct_at`; the `destroy` family became `constexpr` ([[P0784R7]]); `ranges` versions ([[P0896R4]]); `destroy_at` supports arrays;
    - C++26: all of `uninitialized_*` became `constexpr` ([[P2283R2]]), plus parallel `ranges` versions.

## Questions

!!! question "Question 1"
    Why does the `std` version of `uninitialized_copy` require only an input iterator for the source, but a `NoThrowForwardIterator` for the destination?

<details markdown="1">
<summary>Answer</summary>

The source only needs to be read once. When an exception occurs, the destination has to be walked back over to destroy the already-constructed objects (¶2), so it must support multiple passes; and iterator operations must not throw during the rollback, or it could not be completed. That is exactly what `NoThrow` means (¶4.5 of [[algorithms.requirements#4]]).
</details>

!!! question "Question 2"
    What happens if you call `std::uninitialized_fill` on storage that already holds `std::string` objects?

<details markdown="1">
<summary>Answer</summary>

Placement new creates new objects in that storage, and the lifetime of the original `string`s ends (¶3 Note 1), but their destructors are not called, so the heap memory they held leaks. Per [[basic.life]], not calling the destructor is not by itself undefined behavior, as long as the program does not depend on the destructor's side effects; but it is almost always a bug. The right approach is to `destroy` first and then `uninitialized_fill`, or simply assign with `fill`.
</details>

## Summary

| Algorithm | How it initializes | Precondition | On exception |
|---|---|---|---|
| `uninitialized_default_construct` | default-initialization; `int` and the like are not zeroed | none | rolled back |
| `uninitialized_value_construct` | value-initialization | none | rolled back |
| `uninitialized_copy`, `_n` | copy construction | no overlap | rolled back |
| `uninitialized_move`, `_n` | move construction (*deref-move*) | no overlap | rolled back; source objects may have been moved from |
| `uninitialized_fill`, `_n` | copy construction from `x` | none | rolled back |
| `construct_at` | `T(args...)` with parentheses; arrays value-initialized | none | the exception propagates directly |
| `destroy_at`, `destroy`, `destroy_n` | n/a | none | destroyed front to back |
