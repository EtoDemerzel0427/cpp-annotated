---
title: Class template array
summary: "std::array is an aggregate with a single built-in array member; it gives built-in arrays value semantics, a container interface and a tuple interface, and nearly all of its behavior comes from the core language's aggregate rules."
updated: 2026-10-19
---

!!! tldr
    - `array<T, N>` is an aggregate with no user-declared constructors; its initialization, copying and triviality are all decided by the core language's aggregate rules and follow `T`.
    - Unlike other containers, a default-constructed `array` (with N > 0) is not empty; `size()` is always N.
    - `array::swap` swaps element by element: it takes linear time, may throw, and iterators do not move over to the other container with the elements.
    - `array<T, 0>` must be supported; then `begin() == end()` and the return value of `data()` is unspecified.
    - When `T` is a structural type, `array<T, N>` can be the type of a non-type template parameter; `to_array` lets the compiler count the elements while you specify the element type.

`std::array<T, N>` is a thin wrapper around the built-in array `T[N]`. A built-in array cannot be copied, passed or returned by value, and decays to a pointer as soon as it is used; `array` adds this value semantics, along with a container interface and a tuple interface, at no extra cost.

## array is an aggregate [array.overview]

```cpp title="array-basics.cpp" run ok
#include <array>
#include <type_traits>

std::array<int, 3> a = {1, 2, 3};     // inner braces elided
std::array<int, 3> b = {{1, 2, 3}};   // full braces
std::array c{1, 2, 3};                // CTAD: array<int, 3>
auto d = std::to_array("abc");        // array<char, 4>
static_assert(std::is_same_v<decltype(d),
                             std::array<char, 4>>);
static_assert(std::is_aggregate_v<std::array<int, 3>>);
static_assert(
    std::is_trivially_copyable_v<std::array<int, 3>>);

template<std::array<int, 2> P>        // structural type
int f() { return P[0] + P[1]; }

int main() {
  auto [x, y, z] = a;                 // tuple interface
  return f<{3, 4}>() - 7 + (x + y + z - 6)
       + (b[0] - 1) + (c[2] - 3);
}
```

¶2 An `array` is an **aggregate** ([[dcl.init.aggr]]) that can be list-initialized with up to N elements whose types are convertible to `T`. It is usually implemented as a struct with a single `T[N]` member. `{1, 2, 3}` can initialize an `array<int, 3>` directly thanks to brace elision in aggregate initialization: the outer braces correspond to the `array` itself and the inner ones to the `T[N]` member, and the inner ones may be omitted.

¶1 `array` is a contiguous container; an `array<T, N>` stores N elements of type `T`, and `size() == N` is an invariant.

¶3 `array` meets all the requirements of a container and of a reversible container, with one exception: when N > 0, a default-constructed `array` is not empty. It meets only some of the sequence container requirements, because it cannot insert or erase; nor is it an allocator-aware container.

¶4 If `T` is a structural type ([[temp.param]]), `array<T, N>` is a structural type too, so it can be the type of a non-type template parameter. Two such template arguments are equivalent if and only if their corresponding elements are pairwise equivalent. `f<{3, 4}>()` in the example uses this.

¶5 The iterators of `array` meet the constexpr iterator requirements.

## Copying and assignment come from implicit members [array.cons]

¶1 `array` relies on the implicitly-declared special member functions to meet the container requirements table. In addition, the implicit move constructor and move assignment operator require `T` to be *Cpp17MoveConstructible* and *Cpp17MoveAssignable* respectively.

So the properties of `array<T, N>` follow `T` entirely: if `T` is trivially copyable, so is the `array`; if `T` is not copyable, neither is the `array`. None of this requires any library code.

¶2 The deduction guide `array(T, U...) -> array<T, 1 + sizeof...(U)>` has a *Mandates*: every `U` must be the same as `T`.

```cpp title="array-ctad-mandates.cpp" error
#include <array>
std::array e{1, 2.0};   // error: element types differ
```

Clang reports `no viable constructor or deduction guide for deduction of template arguments of 'std::array'`. The standard writes the requirement as a *Mandates*, meaning the program is ill-formed once this deduction guide is selected; libc++ implements it as a constraint on the deduction guide, so the guide simply does not participate in overload resolution when it is not met. Both approaches must reject this example; the difference is observable only in a SFINAE context.

## Member functions [array.members]

- ¶1 `size()` returns N.
- ¶2 `data()` returns a pointer such that `[data(), data() + size())` is a valid range; when non-empty, `data() == addressof(front())`.
- ¶3 `fill(u)` is as if by `fill_n(begin(), N, u)`.
- ¶4 `swap(y)` is equivalent to `swap_ranges(begin(), end(), y.begin())`, with exception specification `noexcept(is_nothrow_swappable_v<T>)`.

¶5 Note 1 points out how `array::swap` differs from other containers:

!!! std
    Unlike the swap function for other containers, array::swap takes linear time, can exit via an exception, and does not cause iterators to become associated with the other container.

Other containers swap their internal pointers to element storage; the elements themselves stay put, and iterators move to the other container along with the elements ([[container.requirements.general#65]]). The elements of an `array` are inside the object, so it can only swap values one by one; iterators still refer to the same position in the original `array`, which now holds the other array's former value.

## Non-member swap [array.special]

¶1 The non-member `swap(x, y)` is constrained on `N == 0 || is_swappable_v<T>`; ¶2 its effect is as if by `x.swap(y)`; ¶3 its complexity is linear in N. With this constraint, an `array` whose elements are not swappable does not participate in overload resolution for `swap`, and `is_swappable_v<array<T, N>>` reports that accurately.

## Zero-sized array [array.zero]

The core language does not allow arrays of length 0 ([[dcl.array]]), so `array<T, 0>` cannot simply wrap a `T[0]`. The standard still requires it to be supported:

- ¶1 The case `N == 0` must be supported;
- ¶2 in that case `begin() == end()`, equal to some unique value, and the return value of `data()` is unspecified;
- ¶3 the member `swap()` must have a non-throwing exception specification.

!!! impl
    With libc++ (Clang 23), `sizeof(std::array<int, 0>)` is 4. It contains a placeholder member with the size and alignment of `T`, so that the object has nonzero size and `data()` can return a suitably aligned pointer.

## to_array [array.creation]

C++20's `to_array` converts a built-in array into an `array<remove_cv_t<T>, N>`. The lvalue version `to_array(T (&a)[N])` copies each element, and the rvalue version `to_array(T (&&a)[N])` moves each element (¶3, ¶6). Both require that `T` is not itself an array type, so multidimensional arrays are not supported (¶1, ¶4).

Its point is letting the compiler count the elements while still letting you specify the element type. `std::to_array<long>({1, 2, 3})` gives an `array<long, 3>`, which CTAD cannot do: CTAD either deduces all template arguments or requires all of them to be written out. For a string literal, `to_array("abc")` gives an `array<char, 4>` that includes the terminating null character.

## Tuple interface [array.tuple]

`tuple_size<array<T, N>>` is N, `tuple_element<I, array<T, N>>::type` is `T`, and `get<I>` returns a reference to the Ith element; both `tuple_element` and `get` require `I < N` (¶1–¶3). So `array` works with `std::apply` and `std::tuple_cat`.

When a structured binding ([[dcl.struct.bind]]) finds that `tuple_size<array<…>>` is defined, it binds tuple-like, fetching elements through `get<I>` rather than binding directly to data members.

## Comparison with built-in arrays, inplace_vector and span

| | `T[N]` | `array<T, N>` | `inplace_vector<T, N>` | `span<T, N>` |
|---|---|---|---|---|
| Owns its elements | Yes | Yes | Yes | No |
| Number of elements | Always N | Always N | 0 to N | Always N |
| Copyable, comparable, returnable by value | No | Yes | Yes | Shallow copy |
| All elements constructed | Yes | Yes | Only the first `size()` | N/A |
| Complexity of `swap` | N/A | Linear | Linear | Constant |

`inplace_vector` ([[inplace.vector]]) is an `array` with fixed capacity and variable size; `span` ([[views.contiguous]]) is a non-owning view of any contiguous storage.

## Questions

!!! question "Question"
    ```cpp
    std::array<std::string, 2> a;
    auto it = a.begin();
    std::array<std::string, 2> b{"x", "y"};
    a.swap(b);
    ```
    What is `*it` afterwards? What if both `array`s are replaced by `std::vector<std::string>` (with `a` holding two empty strings)?

<details markdown="1">
<summary>Answer</summary>

For `array`, `*it` is `"x"`. `array::swap` exchanges values (¶4); `it` still refers to `a[0]`, and `a[0]` now holds the former value of `b[0]`.

For `vector`, `*it` is the value `a[0]` had before the swap, an empty string, but `it` is now an iterator into `b`. [[container.requirements.general#65]] says iterators keep referring to the same element, and that element now belongs to `b` together with its storage.
</details>

<details class="fine" markdown="1"><summary>Remaining wording</summary>

In [array.syn], the `<array>` header is marked mostly freestanding and `array` itself partially freestanding: the throwing `at()` is deleted in a freestanding implementation ([[freestanding.item]]).

</details>
