---
title: Range adaptors
summary: "How range adaptors are called and composed: the exact meaning of the pipe operator |, partial application such as views::filter(pred), joining pipelines with your own adaptors via range_adaptor_closure; the pattern shared by all views, and the two helper components movable-box and non-propagating-cache."
updated: 2026-10-19
---

!!! tldr
    - A range adaptor turns a range into a view; adaptors chain into pipelines with `|`, and elements are computed only during traversal.
    - For a closure object `C`, `R | C` is equivalent to `C(R)`; two closure objects `C | D` form a new closure, and calling it is `D(C(r))`.
    - `views::filter(pred)` is partial application: it copies `pred` by value into a closure and calls `views::filter(r, pred)` once it receives a range.
    - Since C++23, once a class `T` publicly inherits `range_adaptor_closure<T>`, its objects can appear on either side of `|`.
    - *movable-box* lets non-assignable lambdas be stored in views; *non-propagating-cache* is a cache that is not copied along when the view is copied.

## Two notations: pipe and function call [range.adaptors.general]

```cpp run ok
#include <ranges>
#include <vector>
#include <algorithm>
#include <cassert>
#include <cstdio>
int main() {
  std::vector<int> ints{0, 1, 2, 3, 4, 5};
  auto even = [](int i) { return i % 2 == 0; };
  auto square = [](int i) { return i * i; };
  for (int i : ints | std::views::filter(even) | std::views::transform(square))
    std::printf("%d ", i);                                   // 0 4 16
  std::puts("");
  assert(std::ranges::equal(ints | std::views::filter(even),
                            std::views::filter(ints, even)));
}
```

¶1 A **range adaptor** ([[g:range-adaptor]]) transforms a range into a view with some custom behavior. Adaptors can be chained into pipelines, and the resulting view computes its elements one at a time only as it is traversed; this is called lazy evaluation. ¶2 They are declared in `std::ranges::views`, and `std::views` is an alias for that namespace.

¶3 The bitwise or operator `|` is overloaded to build pipelines; every adaptor also supports an equivalent function call notation. ¶4 Example 1 is the code above: `ints | views::filter(even)` and `views::filter(ints, even)` give the same result.

## Closure objects and | [range.adaptor.object]

¶1 A **range adaptor closure object** ([[g:range-adaptor-closure-object]]) is a unary function object that accepts a range argument. `views::reverse` and `views::filter(even)` are both closure objects. For a closure object `C` and a range expression `R`, these two expressions are equivalent:

```cpp
C(R)
R | C
```

Two closure objects can also be combined with `|`. `C | D` produces a new closure object `E`, which is a perfect forwarding call wrapper ([[func.require]]):

- ¶1.1 it holds a copy `d` of `D`, of type `decay_t<decltype((D))>`;
- ¶1.2 it holds a copy `c` of `C`;
- ¶1.3 calling `E(arg)` is `d(c(arg))`.

!!! std
    the expression C | D produces another range adaptor closure object E. … Its call pattern is d(c(arg))

Several conclusions follow:

- `|` is left-associative. `r | C | D` is `(r | C) | D`, which produces a view and then adapts it; `C | D` on its own produces a pipeline not yet attached to a range, which can be stored in a variable and reused. Both give the same result.
- Closure objects store their components by value. `auto p = views::filter(pred) | views::transform(f);` copies both `pred` and `f` into `p`. If `pred` captures a local variable by reference and `p` outlives that variable, it dangles.
- A perfect forwarding call wrapper forwards its own value category to `c` and `d`: an lvalue `E` calls them as lvalues, an rvalue `E` calls them as rvalues.

### Adaptor objects and partial application (¶6–¶8)

¶6 A **range adaptor object** ([[g:range-adaptor-object]]) is a customization point object ([[customization.point.object]]) that accepts a `viewable_range` as its first argument and returns a view. ¶7 An adaptor object that takes only one argument is itself a closure object, e.g. `views::reverse`, `views::join`, `views::all`.

¶8 An adaptor object that takes several arguments, such as `views::filter` or `views::take`, can be given only the arguments other than the range. If `adaptor(range, args...)` is well-formed, then `adaptor(args...)` produces a closure object `f`, which is also a perfect forwarding call wrapper:

- ¶8.1 it holds a copy of `adaptor`;
- ¶8.2 it stores `args...` by value as `bound_args`, of types `decay_t<decltype((args))>...`;
- ¶8.3 calling `f(r)` is `adaptor(r, bound_args...)`.

That is why `views::filter(pred)` can be written on its own: it is a partial application of `filter`, much like `std::bind_back(views::filter, pred)`. The last sentence of ¶8 says that whether `adaptor(args...)` is well-formed depends only on whether the arguments can be stored; it does not check whether it can later be called with some range, so type errors appear only at `r | f`.

```cpp run ok
#include <ranges>
#include <vector>
#include <cstdio>
int main() {
  std::vector<int> v{1, 2, 3};
  auto f = std::views::transform([](int x) { return x + 1; });   // partial application
  auto a = f(v);          // C(R)
  auto b = v | f;         // R | C, equivalent to the previous line
  static_assert(std::same_as<decltype(a), decltype(b)>);
  auto ab = std::views::take(2) | f;     // C | D: when called, take first, then transform
  for (int x : v | ab) std::printf("%d ", x);    // 2 3
  std::puts("");
}
```

### Custom closures: range_adaptor_closure (¶2–¶5) {{c++23}}

In C++20, user-written function objects could not join pipelines, because the library's way of implementing `|` was not public. C++23's [[P2387R3]] provides a CRTP base class:

```cpp
template<class D>
  requires is_class_v<D> && same_as<D, remove_cv_t<D>>
class range_adaptor_closure { };
```

¶2 If an object `t` of type `T` meets all of the following conditions, the implementation guarantees that `t` is a range adaptor closure object: it can be written as `r | t` and combined with other closures as `t | other`:

- ¶2.1 `t` is a unary function object that accepts a range argument;
- ¶2.2 `T` is derived from `range_adaptor_closure<T>`;
- ¶2.3 `T` has no other base class of type `range_adaptor_closure<U>`;
- ¶2.4 `T` is not itself a range. If a type were both a range and a closure, `a | b` could not tell which applies to which.

```cpp run ok
#include <ranges>
#include <vector>
#include <cstdio>
// a custom closure: square every element
struct square_fn : std::ranges::range_adaptor_closure<square_fn> {
  template<std::ranges::viewable_range R>
  constexpr auto operator()(R&& r) const {
    return std::forward<R>(r)
         | std::views::transform([](auto x) { return x * x; });
  }
};
inline constexpr square_fn square;

int main() {
  std::vector<int> v{1, 2, 3, 4, 5};
  auto odd_squares = std::views::filter([](int x) { return x % 2; }) | square;
  for (int x : v | odd_squares) std::printf("%d ", x);                 // 1 9 25
  for (int x : square(v | std::views::take(2))) std::printf("%d ", x); // 1 4
  std::puts("");
}
```

¶3–¶5 specify three kinds of undefined behavior:

- ¶3 `D` may be an incomplete type, but when an expression of type `cv D` is used as an operand of `|`, `D` must be complete and derived from `range_adaptor_closure<D>`. If overload resolution selects a program-defined `operator|` for such an expression, the behavior is undefined. So do not write another `operator|` for your closure classes.
- ¶4 If `U` has a base class `range_adaptor_closure<T>` and `T` is not `U`, using an object of `U` as an operand of `|` is {{ub}}. This is the case of a wrong CRTP argument.
- ¶5 A program adding specializations of `range_adaptor_closure` is {{ub}}.

A custom adaptor with parameters can follow ¶8 and provide two overloads, a full call and a partial application:

```cpp run ok
#include <ranges>
#include <vector>
#include <cstdio>
// both every_nth(r, n) and r | every_nth(n) work
struct every_nth_closure
    : std::ranges::range_adaptor_closure<every_nth_closure> {
  std::ptrdiff_t n;
  constexpr explicit every_nth_closure(std::ptrdiff_t k) : n(k) {}
  template<std::ranges::viewable_range R>
  constexpr auto operator()(R&& r) const {
    return std::forward<R>(r) | std::views::stride(n);
  }
};
struct every_nth_fn {
  template<std::ranges::viewable_range R>
  constexpr auto operator()(R&& r, std::ptrdiff_t n) const {   // full call
    return every_nth_closure(n)(std::forward<R>(r));
  }
  constexpr auto operator()(std::ptrdiff_t n) const {          // partial application
    return every_nth_closure(n);
  }
};
inline constexpr every_nth_fn every_nth;

int main() {
  std::vector<int> v{0, 1, 2, 3, 4, 5, 6};
  for (int x : v | every_nth(3)) std::printf("%d ", x);    // 0 3 6
  for (int x : every_nth(v, 2)) std::printf("%d ", x);     // 0 2 4 6
  auto pipe = std::views::reverse | every_nth(2);          // standard closure | custom closure
  for (int x : v | pipe) std::printf("%d ", x);            // 6 4 2 0
  std::puts("");
}
```

C++23's `std::bind_back` can also do partial application, but its result does not derive from `range_adaptor_closure` and cannot go directly on the right of `|`; it needs another wrapper.

!!! impl "The libc++ implementation"
    In `__ranges/range_adaptor.h`, libc++ implements pipelines with an internal CRTP base `__range_adaptor_closure<T>`, and the public `range_adaptor_closure` is just an empty class derived from it. `range | closure` calls `std::invoke(closure, range)`; `closure | closure` returns `__pipeable(__compose(c2, c1))`, i.e. the `d(c(arg))` of ¶1.3. When deciding whether a type is a closure, it likewise excludes `ranges::range` types (¶2.4).

## The pattern shared by all views

Almost every adaptor view is defined after the same pattern; once you can read one, the rest are easy:

```cpp
template<input_range V, ...> requires view<V> && ...
class xxx_view : public view_interface<xxx_view<V, ...>> {
  V base_ = V();                         // stores the underlying view by value
  movable-box<F> fun_;                   // if there is a function object
  template<bool Const> class iterator;   // when Const is true, the underlying range is const V
  template<bool Const> class sentinel;
public:
  xxx_view() requires default_initializable<V> = default;
  constexpr explicit xxx_view(V base, ...);
  constexpr V base() const & requires copy_constructible<V>;
  constexpr V base() &&;
  constexpr auto begin() requires (!simple-view<V>);
  constexpr auto begin() const requires range<const V> && ...;
  // ...
};
template<class R, ...> xxx_view(R&&, ...) -> xxx_view<views::all_t<R>, ...>;
```

- The underlying range is always a view `V`. The deduction guide uses `views::all_t<R>` to turn any `viewable_range` into a view ([[range.all]]).
- The constructors are `explicit`. [[P2711R1]] made the multi-parameter constructors `explicit` across the board.
- The iterator is written as `template<bool Const>`, so one piece of code serves both non-const and const traversal: when `Const` is true the underlying range is *maybe-const*`<Const, V>`, i.e. `const V`. `iterator<false>` implicitly converts to `iterator<true>`.
- For the pairing of `begin() requires (!simple-view<V>)` and `begin() const`, see [[range.utility]].

## movable-box [range.move.wrap]

Views must be move-assignable ([[range.view]]), but a lambda with captures has copy and move constructors while its assignment operators are deleted. If `filter_view` stored its predicate directly as a lambda member, it could not be assigned and would therefore not be a view.

¶1 The exposition-only *movable-box*`<T>` ([[g:movable-box]]) solves this. It behaves exactly like `optional<T>`, with only these differences:

- ¶1.1 it constrains `T` to be move constructible and an object type;
- ¶1.2 when `T` is default initializable, the default constructor constructs a value rather than producing the empty state;
- ¶1.3 when `T` is not copy assignable, copy assignment becomes: `emplace(*that)` if the other holds a value, otherwise `reset()`;
- ¶1.4 when `T` is not move assignable, move assignment likewise uses `emplace`.

That is, it emulates assignment by destroying the old value and constructing the new one in place. The cost is an extra empty state: if the in-place construction throws, the box is left empty. This is why `filter_view::begin()` has the precondition `pred_.has_value()` ([[range.filter]]).

¶2 Recommended practice: when the empty state is not needed, e.g. `T` is itself assignable or its copy and move constructors do not throw, *movable-box*`<T>` should store just a `T`, without a flag recording whether it holds a value, so there is no extra overhead.

!!! history "From copyable-box to movable-box"
    In C++20 it was called *copyable-box* and required `T` to be copy constructible. [[P2494R2]] relaxed it to *movable-box*, after which `views::transform`, `views::filter` and others can accept move-only function objects, such as a lambda that captures a `unique_ptr`. The comments in libc++'s `__ranges/movable_box.h` record the rename.

## non-propagating-cache [range.nonprop.cache]

¶1 The exposition-only *non-propagating-cache*`<T>` ([[g:non-propagating-cache]]) also behaves like `optional<T>`, except that it does not propagate its contents:

- ¶1.2 copy construction copies nothing; the new object is empty;
- ¶1.3 move construction gives an empty object and empties the source;
- ¶1.4–¶1.5 copy assignment and move assignment both empty the object itself, and move assignment also empties the source;
- ¶1.6 the extra member *emplace-deref*`(i)` empties the cache and then direct-initializes the contained value from `*i`. When `*i` is a prvalue, copy elision allows construction even if `T` cannot be moved.

¶2 Note 2 says it enables an input view to temporarily cache values as it is iterated over.

The cache belongs to one view object only. Copying a view gives a new view without the cache, which recomputes on first use. There are two reasons: the cached contents may point inside the original view, such as the inner range cached by `join_view`, which would dangle if copied over; and the cached result may no longer be right for the new view.

Places in the standard that use it: `join_view` and `join_with_view` (caching the outer iterator and a prvalue inner range), `lazy_split_view` and the input version of `chunk_view` (caching the current iterator), and `cache_latest_view` (caching the most recent element). The `begin()` caching of `filter_view` and similar views is written in the standard only as one sentence in Remarks, "caches the result", and implementations usually use a type with the same semantics.

<details class="fine" markdown="1"><summary>Remaining wording: helpers [range.adaptor.helpers]</summary>

[range.adaptor.helpers] defines several exposition-only tools: *tuple-transform* calls a function on each element of a tuple and collects the results into a new `tuple`; *tuple-for-each* calls a function on each element; *as-lvalue* uses an rvalue as an lvalue; *all-random-access*, *all-bidirectional* and *all-forward* check whether a set of views (under *maybe-const*) all reach a given iterator strength. They mainly serve multi-view adaptors such as `zip`, `zip_transform`, `cartesian_product` and `concat`.

</details>

## The cost of lazy evaluation

- Constructing a view is O(1); it just stores the underlying view and the function objects.
- Each `++` may do more than constant work: `filter` has to skip elements that fail the predicate, and `join` has to skip empty inner ranges. The total cost of a full traversal is still linear in the number of underlying elements.
- Dereferencing may recompute: `transform`'s `operator*` calls the function every time. `transform | filter` calls the function twice for elements that pass the filter, once when `filter` tests them and once when they are read; see [[range.transform]]. C++26's `views::cache_latest` is designed for exactly this case ([[range.cache.latest]]).
- The first `begin()` may be O(n), and later ones O(1): `filter`, `drop_while`, `split`, `chunk_by` and others cache the first result.

## Index of views

| Category | Views |
|---|---|
| Wrapping | [[range.all\|all, ref_view, owning_view]], [[range.common\|common, counted]], [[range.as.const\|as_const, as_rvalue]], [[range.cache.latest\|cache_latest, as_input]] |
| Selection | [[range.filter\|filter]], [[range.take\|take, take_while]], [[range.drop\|drop, drop_while]], [[range.chunk\|stride]] |
| Transformation | [[range.transform\|transform]], [[range.elements\|elements, keys, values]], [[range.enumerate\|enumerate]] |
| Order | [[range.reverse\|reverse]] |
| Flattening and concatenation | [[range.join\|join, join_with]], [[range.concat\|concat]] |
| Splitting | [[range.split\|split, lazy_split]], [[range.chunk\|chunk, slide, chunk_by]] |
| Multiple sequences | [[range.zip\|zip, zip_transform, adjacent, adjacent_transform]], [[range.cartesian\|cartesian_product]] |
