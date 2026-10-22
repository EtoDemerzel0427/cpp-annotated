---
title: Object concepts
summary: "The four progressively stronger concepts movable, copyable, semiregular and regular describe value types that behave like int: what each level adds, and which level common types stop at."
updated: 2026-10-19
---

!!! tldr
    - The four concepts get progressively stronger: `movable` (can be moved and swapped) ⊂ `copyable` (can also be copied) ⊂ `semiregular` (can also be default-initialized) ⊂ `regular` (can also be compared with `==`).
    - Only object types can be `movable`; references, `const T` and classes with const members aren't.
    - A lambda with captures can't be assigned, so it isn't even `movable`; a captureless lambda, however, is `regular`.
    - These four concepts have no semantic requirements of their own; all the semantics come from the concepts they combine.

[concepts.object] ¶1 says these concepts specify the basis of the value-oriented programming style on which the library is based. Value-oriented means objects behave like `int`: copying gives an equal and independent copy, the two sides are equal after assignment, an object can be default-constructed and assigned later, and equality can be tested with `==`. The STL assumed element types were like this from the start, and such types are called regular types. C++20 wrote this down as four concepts.

## Which level common types stop at

```cpp run title="object-concepts.cpp" ok
#include <concepts>
#include <functional>
#include <memory>
#include <string>

static_assert(!std::movable<int&>);      // not an object type
static_assert(!std::movable<const int>); // can't be assigned

using UP = std::unique_ptr<int>;
static_assert(std::movable<UP> && !std::copyable<UP>);

using RW = std::reference_wrapper<int>;
static_assert(std::copyable<RW>);
static_assert(!std::semiregular<RW>);    // can't be default-constructed

static_assert(std::regular<std::string>);

// a lambda with a capture: copy constructible, not assignable
using WithCapture = decltype([x = 0] { return x; });
static_assert(std::copy_constructible<WithCapture>);
static_assert(!std::movable<WithCapture>);

// a captureless lambda: regular
using NoCapture = decltype([] { return 1; });
static_assert(std::regular<NoCapture>);

int main() {}
```

| Concept | Adds to the previous level | Typical types that stop at this level |
|---|---|---|
| `movable` | Object type, move construction, move assignment, swappable | `unique_ptr<T>`, `thread`, `ifstream` |
| `copyable` | Copy construction and copy assignment from three sources | `reference_wrapper<T>` |
| `semiregular` | Default-initializable | Simple aggregates without `==` |
| `regular` | Comparable with `==`, where `==` means equality | `int`, `string`, `vector<int>` |

The results for the two lambdas deserve explanation.

A lambda with captures has its copy assignment operator defined as deleted ([[expr.prim.lambda.closure]]), so move assignment isn't available either, and it isn't even `movable`. Views in the ranges library need to store function objects and be assignable, so the standard stores them in an exposition-only wrapper *movable-box*, which emulates assignment by destroying and reconstructing in place.

A captureless lambda can be default-constructed and assigned since C++20. It also converts implicitly to a function pointer, so `a == b` becomes valid through built-in pointer comparison. Two objects of the same closure type have no state and are equal anyway, and the function pointers they convert to compare equal too, so it doesn't just satisfy `regular`, it models it.

## The four definitions

```cpp
template<class T>
  concept movable = is_object_v<T> && move_constructible<T> &&
                    assignable_from<T&, T> && swappable<T>;
template<class T>
  concept copyable = copy_constructible<T> && movable<T> && assignable_from<T&, T&> &&
                     assignable_from<T&, const T&> && assignable_from<T&, const T>;
template<class T>
  concept semiregular = copyable<T> && default_initializable<T>;
template<class T>
  concept regular = semiregular<T> && equality_comparable<T>;
```

### `movable`

- `is_object_v<T>`: value semantics are about objects only, so references, function types and `void` aren't `movable`. `move_constructible<int&>` is true, and this term exists precisely to exclude it.
- `assignable_from<T&, T>`: move assignment, returning `T&`, with a common reference ([[concept.assignable]]). So `const T` isn't `movable`.
- `swappable<T>`: can be swapped with `ranges::swap`. A type meeting the first two terms can always be swapped with three moves, so syntactically this term almost always holds. Its role is semantic: if the type provides a custom `swap`, that function must really exchange the values ([[concept.swappable]]).

### `copyable`

On top of `movable`, it requires copy construction (`copy_constructible`) and copy assignment from all three sources `T&`, `const T&` and `const T`. The three sources have to be listed one by one for the same reason as in [[concept.copyconstructible]]: this combines concepts rather than requires-expressions, so the implicit expression variations of [[concepts.equality]] don't apply.

### `semiregular` and `regular`

¶2 Note 1 says `semiregular` is modeled by types that behave similarly to fundamental types like `int` but are not necessarily comparable with `==`. ¶3 Note 2 says `regular` is modeled by types that behave similarly to `int` and are comparable with `==`.

A typical user of `semiregular` is iterator sentinels: `sentinel_for<S, I>` requires `semiregular<S>`. A typical user of `regular` is `forward_iterator`, which requires iterators to be equality comparable.

!!! note "Why `movable` includes `swappable`"
    The basic operation of algorithms such as `sort`, `rotate` and `partition` is swapping. If `movable` required only move construction and move assignment, an efficient user-written `swap` (for example, one that swaps only internal pointers) would either not be used, or be used without any semantic constraint. Including `swappable` both guarantees that `ranges::swap` works and requires the user's `swap` to exchange the values.

!!! note "Why `regular` doesn't include `totally_ordered`"
    Value semantics can't do without equality comparison: you need it to tell whether a copy succeeded, or whether two iterators have reached the same position. Ordering isn't essential: complex numbers, coordinates and colors have no natural total order. When ordering is needed, just add a `totally_ordered` constraint.

## Common misconceptions

!!! pitfall "`const` data members make a type lose `movable`"
    The assignment operator of `struct S { const int id; };` is implicitly deleted, so `S` isn't `movable`. A `std::vector<S>` can't be passed to `ranges::sort`, because sorting requires elements to be move-assignable (`sortable` requires `indirectly_movable_storable` via `permutable`). Reference data members are the same. The rule of thumb that value types shouldn't have const or reference data members shows up right here at the level of concepts.

!!! pitfall "Satisfying `regular` means `==` compares values"
    A type that gets `==` through an implicit conversion (to a pointer, to `bool`) may satisfy `regular`, but the comparison doesn't necessarily mean value equality, in which case it satisfies without modeling. Captureless lambdas happen to be fine; a stateful type convertible to `bool` won't be so lucky.

## Questions

!!! question "Questions"
    1. Is `std::regular<int*>` true? Do invalid pointer values stop `int*` from modeling `regular`?
    2. Is `std::array<int, 0>` `regular`? What about `std::array<const int, 1>`?
    3. Why does `semiregular` use `default_initializable` rather than `constructible_from<T>`?

<details markdown="1">
<summary>Answer</summary>

1. It is true, and it is modeled. Copying and comparing invalid pointer values are outside the domains of these operations ([[structure.requirements#8]]), which doesn't affect modeling.
2. `array<int, 0>` is `regular`. The elements of `array<const int, 1>` are const, so copy assignment is deleted, and it isn't even `movable`.
3. `constructible_from<T>` only guarantees that `T()` works, but generic code also writes `T{}` and `T t;` (declare first, assign later). `default_initializable` checks all three ([[concept.default.init]]), which is what matches the "like `int`" intuition.
</details>
