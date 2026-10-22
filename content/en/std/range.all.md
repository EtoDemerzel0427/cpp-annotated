---
title: "All view: ref_view and owning_view"
summary: "views::all decides how a range enters a pipeline: a view is copied, an lvalue is borrowed through ref_view, an rvalue is taken over by owning_view; plus the properties of these two views and the ownership rules that follow."
updated: 2026-10-19
---

!!! tldr
    - `views::all(E)` has three outcomes: if `E` is already a view, it is copied; if `E` is an lvalue, you get a `ref_view`; otherwise `E` is moved into an `owning_view`.
    - Every adaptor's deduction guide goes through `views::all_t`, so `v | views::filter(p)` borrows `v`, while `std::move(v) | views::filter(p)` owns `v`'s elements.
    - `ref_view` stores only a pointer, is copyable, and is a borrowed range; its constness does not propagate to the elements. It rejects all rvalues, including those a `const R&` could bind to.
    - `owning_view` is move-only, propagates const to the elements, and is borrowed only if its underlying range is; it does not accept `initializer_list`.

## Who owns the elements in a pipeline

```cpp run ok
#include <ranges>
#include <vector>
using V = std::vector<int>;
V make() { return {1, 2, 3}; }
int main() {
  V v{1, 2, 3};
  const V cv{4, 5};
  auto a = std::views::all(v);        // ref_view<V>
  auto b = std::views::all(cv);       // ref_view<const V>
  auto c = std::views::all(make());   // owning_view<V>: the temporary is moved in
  auto d = std::views::all(a);        // a is already a view: copied
  static_assert(std::same_as<decltype(a), std::ranges::ref_view<V>>);
  static_assert(std::same_as<decltype(b), std::ranges::ref_view<const V>>);
  static_assert(std::same_as<decltype(c), std::ranges::owning_view<V>>);
  static_assert(std::same_as<decltype(d), std::ranges::ref_view<V>>);
  static_assert(sizeof(a) == sizeof(void*));
  return (c.size() == 3 && &a.base() == &v) ? 0 : 1;
}
```

The underlying range of every adaptor must be a view ([[range.adaptors]]), while what users have in hand is usually a container like `vector`. `views::all` decides how a range enters a pipeline: borrowed (`ref_view`), taken over (`owning_view`), or, if it is already a view, simply copied. Every adaptor's deduction guide is written `xxx_view(R&&, ...) -> xxx_view<views::all_t<R>, ...>`, so once you understand `views::all`, you understand ownership in pipelines.

| Form | Underlying type | Who owns the elements | Can the view outlive the original? |
|---|---|---|---|
| `v \| views::filter(p)` | `ref_view<V>` | `v` | no |
| `std::move(v) \| views::filter(p)` | `owning_view<V>` | the view | yes |
| `make_vec() \| views::filter(p)` | `owning_view<V>` | the view | yes |
| `std::span(v) \| views::filter(p)` | `span<int>` | `v` | no |
| `std::as_const(v) \| views::filter(p)` | `ref_view<const V>` | `v` | no |

## views::all [range.all.general]

¶1 `views::all` returns a view that includes all elements of its range argument. ¶2 It is a range adaptor object. Given a subexpression `E`, `views::all(E)` tries in order:

1. ¶2.1 If the decayed type of `E` models `view`, the result is a copy of `E` (*decay-copy*`(E)`);
2. ¶2.2 Otherwise, if `ref_view{E}` is well-formed, the result is that;
3. ¶2.3 Otherwise, the result is `owning_view{E}`.

`views::all_t<R>` is defined as `decltype(views::all(declval<R>()))` ([[ranges.syn]]) and requires `R` to be a `viewable_range` ([[range.refinements#6]]): either a view, or an lvalue range, or a movable rvalue range that is not an `initializer_list`.

## ref_view [range.ref.view]

¶1 `ref_view` is a view of the elements of some other range:

```cpp
template<range R> requires is_object_v<R>
class ref_view : public view_interface<ref_view<R>> {
  R* r_;
public:
  template<different-from<ref_view> T> requires see below
    constexpr ref_view(T&& t);
  constexpr R& base() const { return *r_; }
  constexpr iterator_t<R> begin() const { return ranges::begin(*r_); }
  constexpr sentinel_t<R> end() const { return ranges::end(*r_); }
  // empty, size, reserve_hint, data forwarded according to R's capabilities
};
template<class R> ref_view(R&) -> ref_view<R>;
```

### Lvalues only (¶2–¶3)

¶3 The constructor's constraint is expressed with two exposition-only functions *FUN*:

```cpp
void FUN(R&);
void FUN(R&&) = delete;
// constraint: convertible_to<T, R&> && requires { FUN(declval<T>()); }
```

Why not simply write `ref_view(R& r)`? Because when `R` is `const V`, a `const V&` can bind to a temporary `V`, so a `ref_view<const V>` could be constructed from a temporary and would dangle immediately. With the deleted `FUN(R&&)` added, an rvalue argument matches it better, `FUN(declval<T>())` selects the deleted function, the constraint fails, and that path is blocked.

Writing the constructor as a template taking `T&&` also lets it accept types implicitly convertible to `R&`. ¶2 The effect of construction is `r_ = addressof(static_cast<R&>(std::forward<T>(t)))`. The `different-from<ref_view>` constraint ensures it does not steal `ref_view`'s own copy construction ([[range.utility]]).

```cpp run ok
#include <ranges>
#include <vector>
using V = std::vector<int>;
static_assert(!std::constructible_from<std::ranges::ref_view<V>, V>);
static_assert(!std::constructible_from<std::ranges::ref_view<const V>, V>);   // blocked by FUN(R&&)
static_assert(std::constructible_from<std::ranges::ref_view<const V>, V&>);
int main() {}
```

### Properties

- It stores only a pointer and copying is O(1), so it is a view.
- Const does not propagate to the elements: `begin() const` returns `iterator_t<R>`, not `iterator_t<const R>`. Elements can still be modified through a `const ref_view<vector<int>>`. It behaves like a pointer, not like a container.
- It is a borrowed range: `enable_borrowed_range<ref_view<T>>` is always `true`, since the iterators point into `*r_` and have nothing to do with the `ref_view` object.
- It has no default constructor; there is no sensible default for the pointer member. C++20 originally required views to be default constructible, and `ref_view` then initialized its pointer to `nullptr`; after [[P2325R3]] removed that requirement, `ref_view`'s default constructor was removed too.

## owning_view [range.owning.view]

¶1 `owning_view` is a move-only view of the elements of some other range:

```cpp
template<range R>
  requires movable<R> && (!is-initializer-list<R>)
class owning_view : public view_interface<owning_view<R>> {
  R r_ = R();
public:
  owning_view() requires default_initializable<R> = default;
  constexpr owning_view(R&& t);                 // ¶2: initializes r_ with std::move(t)
  owning_view(owning_view&&) = default;
  owning_view& operator=(owning_view&&) = default;
  constexpr R& base() & noexcept;               // plus three more overloads: const&, &&, const&&
  constexpr iterator_t<R> begin();
  constexpr auto begin() const requires range<const R>;
  // end, empty, size, reserve_hint, data likewise come in const and non-const versions
};
```

### Properties

- It is move-only. The class declares move operations, so copy construction and copy assignment are implicitly deleted. The elements exist in only one object, so the complexity requirement for views is met: destroying N copies costs O(N+M) in total ([[range.view]]).
- Const propagates to the elements: `begin() const` uses `const R`, as containers do.
- Whether it is borrowed depends on the underlying range: `enable_borrowed_range<owning_view<T>>` equals `enable_borrowed_range<T>`. That is false for `vector`, so algorithms return `dangling` for an rvalue `owning_view<vector<int>>` ([[range.dangling]]).
- It does not accept `initializer_list`. An `initializer_list` does not own its elements; it refers to a temporary array, and owning an `initializer_list` does not extend that array's lifetime, so the result would inevitably dangle.

!!! history "Putting rvalue containers into pipelines"
    C++20 originally had no `owning_view`, and `views::all` was simply ill-formed for an rvalue that is not a view, so `make_vector() | views::filter(p)` did not compile. [[P2415R2]] (What is a view?), as a defect report against C++20, redefined views to allow move-only views that own their elements, and added `owning_view`. Since then this form is valid and safe: the temporary `vector` is moved into the pipeline and lives as long as the view.

## Common misconceptions

!!! pitfall "Returning a view over a local container from a function"
    `return local_vec | views::transform(f);` returns a `transform_view<ref_view<V>, F>` whose `ref_view` points to `local_vec`, which is about to be destroyed; using it afterwards is {{ub}}. Write `return std::move(local_vec) | views::transform(f);` instead, and the underlying range becomes an `owning_view`. [[range.dangling]] has a runnable side-by-side example.

!!! pitfall "owning_view makes the whole pipeline move-only"
    `p` in `auto p = make_vec() | views::filter(f);` can only be moved. Passing it by value to a function with an `auto r` parameter requires `std::move(p)`; passing it as `const auto&` fails, because `filter_view` has no const `begin`. A generic function can be written as `void consume(std::ranges::viewable_range auto&& r)` and use `views::all(std::forward<decltype(r)>(r))` inside.

## Questions

!!! question "Question 1"
    Does `views::all(std::initializer_list<int>{1, 2, 3})` compile? What about `auto il = {1, 2, 3}; views::all(il)`?

<details markdown="1">
<summary>Answer</summary>

The former does not: an rvalue `initializer_list` is not a `viewable_range` ([[range.refinements#6]]), and `owning_view` explicitly excludes it as well. The latter does: `il` is an lvalue, giving a `ref_view<std::initializer_list<int>>`, which is safe as long as `il` is in scope.
</details>

!!! question "Question 2"
    `ref_view`'s `begin()` is a const member function, yet it returns a mutable iterator. Does this violate const-correctness?

<details markdown="1">
<summary>Answer</summary>

No. The state of a `ref_view` is just a pointer; `const ref_view` means that pointer does not change, not that the pointed-to object does not change, just like `int* const`. Views are generally like this, and so is `span`. When you need read-only access, use `views::as_const` or `ranges::cbegin` ([[range.as.const]], [[range.access]]).
</details>
