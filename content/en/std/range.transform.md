---
title: Transform view
summary: "transform_view lazily applies a function to each element: the requirements on the function, the conditions for const traversal, why the iterator strength follows the underlying range while the C++17 category degrades to input when the function returns a value, and pitfalls such as calling the function on every dereference and returning dangling references."
updated: 2026-10-19
---

!!! tldr
    - The i-th element of `views::transform(f)` is `f(the i-th underlying element)`. It keeps the underlying iterator strength (up to random access), size and commonness, but it is not a borrowed range.
    - Elements are not stored; every dereference calls `f` once. `transform | filter` calls `f` twice for elements that pass the filter.
    - `f` must be equality-preserving (`regular_invocable`) and its return type cannot be `void`; a `const transform_view` can be traversed only if `f` can be called as const.
    - When `f` returns a value rather than a reference, the C++17-style `iterator_category` is `input_iterator_tag`, and old interfaces that only understand C++17 categories treat it as an input iterator.
    - When `f` returns a reference or a view, it must refer to an object that outlives the view, not to a temporary inside the function.

## Basic usage [range.transform.overview]

```cpp run ok
#include <ranges>
#include <vector>
#include <cstdio>
int main() {
  std::vector<int> is{0, 1, 2, 3, 4};
  auto squares = std::views::transform(is, [](int i) { return i * i; });
  for (int i : squares) std::printf("%d ", i);   // 0 1 4 9 16
  std::puts("");
}
```

¶1 `transform_view` presents a view of an underlying sequence after applying a transformation function to each element, the equivalent of map in functional programming. ¶2 `views::transform` is a range adaptor object ([[range.adaptors]]), and `views::transform(E, F)` is equivalent to `transform_view(E, F)`. ¶3 Example 1 is the code above.

## The class template [range.transform.view]

```cpp
template<input_range V, move_constructible F>
  requires view<V> && is_object_v<F> &&
           regular_invocable<F&, range_reference_t<V>> &&
           can-reference<invoke_result_t<F&, range_reference_t<V>>>
class transform_view : public view_interface<transform_view<V, F>> {
  template<bool> struct iterator;
  template<bool> struct sentinel;
  V base_ = V();
  movable-box<F> fun_;
public:
  constexpr iterator<false> begin();
  constexpr iterator<true> begin() const
    requires range<const V> &&
             regular_invocable<const F&, range_reference_t<const V>>;
  constexpr sentinel<false> end();
  constexpr iterator<false> end() requires common_range<V>;
  // the const versions of end() have the same conditions as above
  constexpr auto size() requires sized_range<V> { return ranges::size(base_); }
  // likewise for size() const and reserve_hint
};
template<class R, class F>
  transform_view(R&&, F) -> transform_view<views::all_t<R>, F>;
```

- `regular_invocable` requires the function to be equality-preserving ([[concepts.callable]]). The view may call `f` on the same element several times, so if `f` has side effects or depends on external mutable state, the behavior is not guaranteed.
- *can-reference* requires that a reference can be formed to the type of the call result, i.e. it cannot be `void`.
- `F` only needs to be move constructible. The function object is stored in a *movable-box* ([[range.move.wrap]]), and since C++23 move-only function objects work too ([[P2494R2]]).
- `begin() const` requires `const F&` to be callable with `range_reference_t<const V>` as well. The `operator()` of a `mutable` lambda is not const, so it makes a `const transform_view` impossible to traverse.
- Transformation does not change the number of elements, so `size()` is forwarded directly when the underlying range is sized.
- There is no `begin()` caching; `begin()` simply constructs an iterator from `ranges::begin(base_)` and is O(1).

## The iterator [range.transform.iterator]

The iterator stores the underlying iterator `current_` and a pointer `parent_` to the parent view, which it needs to find `fun_`. Hence `transform_view` is not a borrowed range.

- `operator*` is equivalent to `invoke(*parent_->fun_, *current_)`; every dereference calls `f` once;
- `value_type` is the return type of `f` with references and cv-qualifiers removed;
- `++`, `--`, `+=` and the like only move `current_` and do not call `f`.

### iterator_concept and iterator_category (¶1–¶2)

¶1 `iterator_concept` follows the underlying range exactly: random access if the underlying range is random access, and so on down through bidirectional, forward and input. It is never contiguous, since the transformed elements are not stored contiguously in memory.

¶2 The C++17-style `iterator_category` is declared only when the underlying range is a forward range. Let `C` be the C++17 category of the underlying iterator:

- ¶2.1 If `f` returns a reference type: `random_access_iterator_tag` if `C` derives from `contiguous_iterator_tag`, otherwise `C`;
- ¶2.2 Otherwise `f` returns a value (a prvalue), and the category is `input_iterator_tag`.

The two disagree because C++17's *Cpp17ForwardIterator* requires `reference` to be a real reference type ([[iterator.cpp17]]). A lambda returning `x * x` makes `reference` be `int`, so by the C++17 rules it is only an input iterator, even though by the C++20 concepts it is a random access iterator.

The consequence is that old interfaces that only understand C++17 categories treat it as an input iterator. `std::vector(first, last)` still works, just without computing the length in advance; functions that require bidirectional iterators, like `std::prev`, do not:

```cpp run
#include <iterator>
#include <ranges>
#include <vector>
int main() {
  std::vector<int> v{1, 2, 3};
  auto sq = v | std::views::transform([](int x) { return x * x; });
  static_assert(std::ranges::random_access_range<decltype(sq)>);
  static_assert(std::same_as<
      std::iterator_traits<std::ranges::iterator_t<decltype(sq)>>::iterator_category,
      std::input_iterator_tag>);
  auto last = std::prev(sq.end());   // libc++ refuses to compile this
  return *last == 9 ? 0 : 1;
}
```

Both `static_assert`s hold. The final `std::prev` is rejected by an internal `static_assert` in the libc++ we test with (Attempt to prev(it) with a non-bidirectional iterator). At the level of the standard, `std::prev` requires its argument to meet *Cpp17BidirectionalIterator*; passing an iterator that only meets *Cpp17InputIterator* violates a library requirement, the behavior is undefined, and refusing to compile is one outcome an implementation is allowed, so this example has no verdict mark. Use the concept-based `std::ranges::prev` instead.

## A transform that returns references

A pointer to member is also a callable object. `views::transform(&Person::name)`, called with an lvalue `Person&`, gives `std::string&`. Since it returns a reference, the elements are writable and `iterator_category` keeps the underlying category:

```cpp run ok
#include <ranges>
#include <string>
#include <vector>
#include <cstdio>
struct Person { std::string name; int age; };
int main() {
  std::vector<Person> ps{{"Ada", 36}, {"Alan", 41}};
  auto names = ps | std::views::transform(&Person::name);   // element type std::string&
  static_assert(std::same_as<std::ranges::range_reference_t<decltype(names)>,
                             std::string&>);
  for (auto& n : names) n += "!";                            // writes back to the original objects

  auto ages = ps | std::views::transform([](const Person& p) { return p.age; });
  for (int a : ages) std::printf("%d ", a);
  std::printf("%s\n", ps[0].name.c_str());   // 36 41 Ada!
}
```

If you just want an algorithm to compare by some field, the algorithm's projection parameter is more direct, e.g. `ranges::sort(ps, {}, &Person::age)` ([[g:projection]]).

## Common pitfalls

### The function is called on every dereference

```cpp run ok
#include <ranges>
#include <vector>
#include <cstdio>
int main() {
  int calls = 0;
  std::vector<int> v{1, 2, 3, 4, 5, 6};
  auto r = v | std::views::transform([&](int x) { ++calls; return x * x; })
             | std::views::filter([](int x) { return x % 2 == 0; });
  for (int x : r) (void)x;
  std::printf("%d\n", calls);   // 9
}
```

When `filter` tests the predicate it dereferences the underlying range once per element, 6 calls for 6 elements; when the loop body reads the squares of the 3 even numbers it dereferences each again, 3 more calls. An expensive transformation function gets called repeatedly. Ways to deal with it:

- When the predicate can be expressed on the original elements, put `filter` before `transform`;
- Use C++26's `views::cache_latest` ([[range.cache.latest]]): `transform(f) | cache_latest | filter(p)` computes each element only once.

The lambda here captures a counter by reference and has side effects only to count the calls. It is not equality-preserving and formally violates the semantic requirements of `regular_invocable`; don't write this in real code.

### Returning a dangling reference or view

```cpp run ub
#include <ranges>
#include <string>
#include <string_view>
#include <vector>
#include <cstdio>
int main() {
  std::vector<std::string> words{"alpha", "beta"};
  auto r = words | std::views::transform(
      [](const std::string& s) -> std::string_view {
        return s + "!";   // points into a temporary string destroyed after return
      });
  for (std::string_view sv : r)
    std::printf("%.*s\n", int(sv.size()), sv.data());   // UB
}
```

Clang 23 gives a `-Wreturn-stack-address` warning for this code (returning address of local temporary object). When the transformation function returns a reference or view, it must refer to an object that outlives the view: a subobject of the underlying element (like `&Person::name`) is fine; a temporary inside the function is not.

### mutable lambdas

```cpp
auto r = v | views::transform([n = 0](int x) mutable { return x + n++; });
// a const r cannot be traversed: const F& is not callable
// n++ also stops the function from being equality-preserving, violating the semantic requirements of regular_invocable
```

## Summary

| Property | `transform_view` |
|---|---|
| Iterator strength (C++20 concepts) | same as underlying, up to random access |
| C++17 category | same as underlying when returning a reference (contiguous lowered to random access); input when returning a value |
| sized, common | same as underlying |
| borrowed | no |
| traversable as const | when `const V` is a range and `const F&` is callable |
| function calls | one per dereference |
