---
title: scoped_allocator_adaptor
summary: "C++11's scoped allocator adaptor: the outer allocator serves the container itself and the inner allocators are passed to the elements through uses-allocator construction, so every level of a nested container uses the specified allocator."
updated: 2026-10-19
---

!!! tldr
    - `scoped_allocator_adaptor<Outer, Inner...>` uses `Outer` for the container's own memory and passes `Inner...` on to the elements, the elements' elements, and so on.
    - With only one allocator, the inner allocator is the adaptor itself, and every level recursively shares the same allocator.
    - It derives from the outer allocator; `allocate` and `deallocate` use only the outer one, and `construct` is responsible for injecting the inner allocator into the element's construction.
    - The propagation traits are the OR of all levels, and `is_always_equal` is the AND.
    - New code more often uses `pmr::polymorphic_allocator` to solve the same problem, but the uses-allocator construction protocol was originally designed for this adaptor.

## The problem it solves

Give a `vector<string>` a custom allocator, and the allocator only manages the `vector`'s own element array; each `string`'s character buffer still uses the allocator the `string` default-constructed for itself. To make the elements use the specified allocator too, it has to be passed in when each element is constructed.

`scoped_allocator_adaptor` (header `<scoped_allocator>`) does this automatically at the point where the container constructs an element:

```cpp title="scoped-allocator.cpp" run ok
#include <scoped_allocator>
#include <vector>
#include <string>
#include <cassert>
#include <new>

template<class T>
struct Tagged {                       // a stateful allocator carrying a tag
    using value_type = T;
    int tag = 0;
    Tagged() = default;
    explicit Tagged(int t) : tag(t) {}
    template<class U>
    Tagged(const Tagged<U>& o) noexcept : tag(o.tag) {}
    T* allocate(std::size_t n) {
        return static_cast<T*>(::operator new(n * sizeof(T)));
    }
    void deallocate(T* p, std::size_t) noexcept { ::operator delete(p); }
    friend bool operator==(const Tagged& a, const Tagged& b) {
        return a.tag == b.tag;
    }
};

using Str = std::basic_string<char, std::char_traits<char>, Tagged<char>>;

int main() {
    // no adaptor: the allocator is used only for the vector's own buffer
    std::vector<Str, Tagged<Str>> v0(Tagged<Str>(1));
    v0.emplace_back("a long string that does not fit in SSO.......");
    assert(v0[0].get_allocator().tag == 0);   // the element uses a default-constructed allocator

    // one allocator: outer and inner are the same
    using A1 = std::scoped_allocator_adaptor<Tagged<Str>>;
    std::vector<Str, A1> v1(A1(Tagged<Str>(1)));
    v1.emplace_back("a long string that does not fit in SSO.......");
    assert(v1[0].get_allocator().tag == 1);   // the element got the allocator automatically

    // two allocators: outer for the vector, inner for the elements
    using A2 = std::scoped_allocator_adaptor<Tagged<Str>, Tagged<char>>;
    std::vector<Str, A2> v2(A2(Tagged<Str>(1), Tagged<char>(2)));
    v2.emplace_back("a long string that does not fit in SSO.......");
    assert(v2.get_allocator().outer_allocator().tag == 1);
    assert(v2[0].get_allocator().tag == 2);
}
```

When `v1` constructs an element, the adaptor appends its inner allocator (here `A1` itself) to the end of the arguments, and the element is actually constructed as `Str(const char*, const Tagged<char>&)`. This works because `A1` derives from `Tagged<Str>` and can be converted to `Str`'s allocator type `Tagged<char>`, so `uses_allocator<Str, A1>` is true ([[allocator.uses]]).

## Outer and inner [allocator.adaptor.syn]

¶1 The adaptor is instantiated with one outer allocator type and zero or more inner allocator types:

- With only one allocator type, the inner allocator is the adaptor itself. The container, the elements, the elements' elements... all recursively use the same allocator.
- With several, the first goes to the container, the second is passed to the elements' constructors, the third to the elements' elements, and so on. When the nesting is deeper than the number of allocators, the last one is reused.

Note 1 points out that the adaptor is **derived from** the outer allocator type, so it can be used in place of the outer allocator in most expressions.

```cpp
template<class OuterAlloc, class... InnerAllocs>
class scoped_allocator_adaptor : public OuterAlloc {
  using OuterTraits = allocator_traits<OuterAlloc>;   // exposition only
  scoped_allocator_adaptor<InnerAllocs...> inner;     // exposition only
  // ...
};
```

The exposition-only member `inner` is itself an adaptor, so the structure is recursive: `scoped_allocator_adaptor<A, B, C>` contains `scoped_allocator_adaptor<B, C>`, which contains `scoped_allocator_adaptor<C>`. With only one allocator, `inner_allocator()` returns `*this`.

Member types such as `value_type` and `pointer` all come from the outer allocator's traits. `rebind<Tp>::other` rebinds only the outer allocator; the inner types are unchanged. The class template also has the deduction guide `scoped_allocator_adaptor(OuterAlloc, InnerAllocs...)`.

## Member types [allocator.adaptor.types]

¶1 `inner_allocator_type` is `scoped_allocator_adaptor<OuterAlloc>` if there are no inner allocators, and `scoped_allocator_adaptor<InnerAllocs...>` otherwise.

¶2–¶4 Each of the three propagation traits (`propagate_on_container_copy_assignment`, `_move_assignment`, `_swap`) is `true_type` if the corresponding trait of the outer allocator or of any inner allocator is true. When a container is assigned or swapped, if any level needs to move along with the container, the whole adaptor must move along; otherwise that level would be separated from the memory it allocated.

¶5 `is_always_equal` is `true_type` only if it is true for every level. The whole adaptor always compares equal only if every level does.

## Construction [allocator.adaptor.cnstr]

¶1 The default constructor value-initializes the outer base class and `inner`.

¶2–¶3 The main constructor `(OuterA2&& outerAlloc, const InnerAllocs&... innerAllocs)` requires `OuterAlloc` to be constructible from `OuterA2`; it initializes the base class with `outerAlloc` and recursively initializes `inner` with `innerAllocs...`.

¶4–¶9 Copy, move, and conversion from an adaptor with a different outer type (needed after `rebind`) all initialize each level from the corresponding allocator. All constructors are `noexcept`, because copying and moving allocators are not allowed to throw anyway.

## Member functions [allocator.adaptor.members]

### The container's own memory uses only the outer allocator (¶2–¶8)

¶2 `inner_allocator()` returns `*this` if there are no inner allocators, and `inner` otherwise. ¶3–¶4 `outer_allocator()` returns `static_cast<OuterAlloc&>(*this)`.

¶5–¶8 `allocate`, `deallocate` and `max_size` all forward to the outer allocator. The inner allocators never allocate memory for the container itself.

### Finding the outermost (¶1)

¶1 The outer allocator may itself be a `scoped_allocator_adaptor`. To find the one really responsible for construction, the standard defines the exposition-only *OUTERMOST*(x): *OUTERMOST*(`x.outer_allocator()`) if `x.outer_allocator()` is a valid expression, and `x` otherwise. *OUTERMOST_ALLOC_TRAITS*(x) is its `allocator_traits`.

Note 1 explains that this is a recursive definition whose termination is guaranteed by the definition of `outer_allocator()`; it terminates for all instantiations of `scoped_allocator_adaptor`.

### `construct`: injecting the inner allocator (¶9)

```cpp
apply([p, this](auto&&... newargs) {
        OUTERMOST_ALLOC_TRAITS(*this)::construct(
          OUTERMOST(*this), p, std::forward<decltype(newargs)>(newargs)...);
      },
      uses_allocator_construction_args<T>(inner_allocator(),
                                          std::forward<Args>(args)...));
```

¶9 Construction takes two steps:

1. `uses_allocator_construction_args<T>(inner_allocator(), args...)` rewrites the arguments into a form carrying the inner allocator: the allocator goes in front, at the end, or is left out, and `pair` is handled member by member recursively ([[allocator.uses]]).
2. The rewritten arguments are handed to the outermost allocator's `construct`.

Step 2 guarantees that the outermost allocator's own `construct` is still called, for example if it logs or switches to default-initialization. The adaptor only inserts the step of injecting the inner allocator in between.

### `destroy` and copying a container (¶10–¶11)

¶10 `destroy(p)` is handed to the outermost allocator's `destroy`.

¶11 `select_on_container_copy_construction()` returns a new adaptor in which each level is initialized with the result of that level's allocator's `select_on_container_copy_construction`.

## Equality [scoped.adaptor.operators]

¶1 With no inner allocators, only the outer allocators are compared; otherwise both the outer and (recursively) the inner allocators must be equal.

## Compared with `pmr`

C++17's `pmr::polymorphic_allocator` ([[mem.poly.allocator.class]]) also passes the allocator to elements through uses-allocator construction, but puts the strategy in a run-time `memory_resource*`:

| | `scoped_allocator_adaptor<A...>` | `pmr::polymorphic_allocator` |
|---|---|---|
| Allocation strategy | Compile time, determined by the type | Run time, determined by a `memory_resource*` |
| Types of nested containers | Each level must spell out its allocator type | Uniform `pmr::` aliases |
| Different allocators per level | Directly supported | With automatic passing, all levels share one resource |
| Allocation overhead | Can be inlined | One virtual function call |
| Propagation on assignment and swap | OR of all levels' traits | Never propagates |

## Summary

- The outer allocator serves the container itself, and the inner allocators are passed to the elements through uses-allocator construction; with only one allocator, it recursively reuses itself.
- The adaptor derives from the outer allocator; `allocate` and `deallocate` use only the outer one.
- The propagation traits are the OR of all levels, and `is_always_equal` is the AND.
- `construct` first injects the inner allocator with `uses_allocator_construction_args`, then hands off to the outermost allocator's `construct`.
