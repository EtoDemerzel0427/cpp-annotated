---
title: Dangling iterator handling
summary: "When a ranges algorithm that returns an iterator is called with a non-borrowed rvalue range, the return type becomes ranges::dangling and code that uses the result does not compile; plus the kinds of dangling it cannot catch."
updated: 2026-10-19
---

!!! tldr
    - A ranges algorithm that returns an iterator or subrange returns `ranges::dangling` when its range argument is an rvalue that is not a borrowed range.
    - `dangling` can be constructed from any arguments but cannot be dereferenced, incremented or compared, so code that uses the result fails to compile.
    - Lvalue ranges and rvalues of borrowed ranges (`string_view`, `span`, `subrange`, `ref_view` and others) get real iterators.
    - It checks only the one expression that calls the algorithm. Storing a view, returning a view from a function, or continuing to use it after modifying the container can still dangle.

## Turning dangling into a compile error

```cpp
auto it = std::ranges::max_element(make_vector());
// the temporary vector returned by make_vector() is destroyed at the semicolon; it dangles
```

If `max_element` returned `vector<int>::iterator` here, `it` would point into an already destroyed temporary, and dereferencing it later would be undefined behavior. The standard's approach is to make the return type of such a call a type that can do nothing, `dangling`, so `*it` simply fails to compile.

```cpp run ok
#include <algorithm>
#include <ranges>
#include <vector>
std::vector<int> make() { return {3, 1, 4, 1, 5}; }
int main() {
  auto r1 = std::ranges::max_element(make());
  static_assert(std::same_as<decltype(r1), std::ranges::dangling>);
  // int bad = *r1;                        // error: dangling cannot be dereferenced

  auto v = make();
  auto r2 = std::ranges::max_element(v);   // lvalue: a real iterator
  auto r3 = std::ranges::find(std::views::all(v), 4);   // rvalue ref_view: borrowed
  return (*r2 == 5 && *r3 == 4) ? 0 : 1;
}
```

The `r3` line is worth a look: `std::views::all(v)` is an rvalue `ref_view`, but `ref_view` is a borrowed range; the returned iterator points to the elements of `v` and has nothing to do with that temporary `ref_view`, so it is safe.

## The dangling type (¶1)

¶1 When an algorithm that usually returns an iterator or subrange is called with an rvalue range argument that does not model `borrowed_range` ([[range.range]]), the return value may refer to a range whose lifetime has ended. In that case it returns `dangling` ([[g:ranges-dangling]]) instead of an iterator or subrange:

```cpp
struct dangling {
  constexpr dangling() noexcept = default;
  constexpr dangling(auto&&...) noexcept {}
};
```

It can be constructed from any arguments and discards them. This way an algorithm's implementation need not distinguish the two cases: it always computes the real iterator first and then does `return {it};`, which compiles just as well when the return type is `dangling`. `dangling` has no `operator*` or `operator++` and cannot be compared with anything.

## How the return type is chosen (¶3)

¶3 For a type `R` that models `range`:

- If `R` models `borrowed_range`, `borrowed_iterator_t<R>` is `iterator_t<R>` and `borrowed_subrange_t<R>` is `subrange<iterator_t<R>>`;
- Otherwise both are `dangling`.

Algorithms use these two aliases as their return types, for example:

```cpp
template<forward_range R, class Proj = identity, /* ... */>
  constexpr borrowed_iterator_t<R>
    ranges::max_element(R&& r, Comp comp = {}, Proj proj = {});
```

`R` is deduced through a forwarding reference. When the argument is an lvalue, `R` is deduced as `X&`, and lvalue references always count as borrowed ranges; when the argument is an rvalue, `R` is deduced as `X`, and then `enable_borrowed_range<X>` decides.

¶2 Example 1 shows three cases: `ranges::find(f(), 42)` is called with an rvalue `vector` and returns `dangling`; `ranges::find(vec, 42)` is called with an lvalue and returns an iterator; `ranges::find(ranges::subrange{vec}, 42)` is called with an rvalue `subrange`, which is a borrowed range, and also returns an iterator ([[range.subrange]]).

!!! tip "When you only need the value"
    For an rvalue container, if you only want the maximum, use an algorithm that returns a value: `std::ranges::max(make())` returns `int` and has no dangling problem. If you only want to know whether an element exists, use C++23's `ranges::contains`, which returns `bool`.

## What it does not catch

`dangling` only judges by the value category of the argument at the moment the algorithm is called. All of the following get around it.

### Storing a view or returning it from a function

```cpp run ub
#include <ranges>
#include <vector>
#include <cstdio>
auto evens() {
  std::vector<int> v{1, 2, 3, 4};
  return v | std::views::filter([](int x) { return x % 2 == 0; });
  // the ref_view inside the view points to the local variable v
}
int main() {
  for (int x : evens()) std::printf("%d\n", x);   // UB: v has been destroyed
}
```

`v` is an lvalue, `views::all(v)` gives a `ref_view`, and the type system sees nothing wrong. Run with Clang 23 and `-fsanitize=address` in our tests, it reports an error as soon as `filter_view::begin` reads `v` (stack-buffer-overflow: it reads the stack memory where the destroyed local variable was). The fix is `return std::move(v) | views::filter(...)`: an rvalue container is moved into an `owning_view` ([[range.all]]), so the view owns the data itself.

### Continuing after modifying the underlying container

```cpp
std::vector<int> v{1, 2, 3};
auto f = v | std::views::filter(pred);
auto it = f.begin();     // filter_view caches the result of begin
v.push_back(4);          // may reallocate
```

The `ref_view` inside the view only stores a pointer to `v` and is unaffected. But after `push_back` reallocates, both `it` and the `begin` iterator cached inside `filter_view` are invalid (see [[container.reqmts]] for the iterator invalidation rules), and calling `f.begin()` again still returns that invalid cached value.

### Borrowing is declared by the type's author

Specialize `enable_borrowed_range` to `true` for a type that actually owns its elements, and `dangling` never appears; the dangling is then the type author's responsibility (see [[range.range]]).

### Temporaries in range-based for (before C++23)

In `for (auto x : get_obj().items())`, in C++20 and earlier the temporary returned by `get_obj()` is destroyed once the initializer has been evaluated, and the reference returned by `items()` dangles. This has nothing to do with `dangling`, since no ranges algorithm is called here. Since C++23, the lifetime of temporaries in the initializer of a range-based `for` is extended to the whole loop ([[stmt.ranged]], [[class.temporary]]).

## Questions

!!! question "Question 1"
    What are the return types of `std::ranges::find(std::string("hello"), 'l')` and `std::ranges::find(std::string_view("hello"), 'l')`?

<details markdown="1">
<summary>Answer</summary>

The former is `dangling`: an rvalue `std::string` is not a borrowed range. The latter is `string_view::const_iterator`: `string_view` is a borrowed range, and the iterator points into the static storage of the string literal, which really is safe.
</details>

!!! question "Question 2"
    What does `ranges::find` return when called with an rvalue `owning_view<vector<int>>`?

<details markdown="1">
<summary>Answer</summary>

`enable_borrowed_range<owning_view<T>>` equals `enable_borrowed_range<T>` ([[range.owning.view]]), and `vector` is not a borrowed range, so it returns `dangling`. That is the right result: the `owning_view` owns the `vector`, and once it is destroyed the iterators dangle.
</details>

<details class="fine" markdown="1"><summary>elements_of [range.elementsof]</summary>

`elements_of<R, Allocator>`, also in [range.utility], is a tag type that holds a range and an allocator. In a `std::generator`, `co_yield ranges::elements_of(r);` yields the elements of `r` one by one, while `co_yield r;` yields `r` itself as a single value. See [[coro.generator]].

</details>
