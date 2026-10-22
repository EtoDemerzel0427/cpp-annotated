---
title: Views
summary: "Which ranges adaptors can cheaply hold by value: the definition of the view concept, its complexity requirements, and declaring a type a view with view_base, view_interface or enable_view."
updated: 2026-10-19
---

!!! tldr
    - A `view` is a range that can be passed by value cheaply; the underlying ranges that range adaptors store by value are all views.
    - The definition is `range<T> && movable<T> && enable_view<T>`. Views and ordinary containers cannot be told apart syntactically, so a type has to declare itself a view.
    - The semantic requirements are all complexity promises: move construction O(1), copy construction O(1) if copyable, and total destruction cost O(N+M) for N copies.
    - A view may own its elements, as long as copying does not duplicate that ownership. `owning_view`, `single_view` and `std::generator` are all views.
    - There are three ways to declare one: publicly inherit `view_base`, publicly inherit a single `view_interface<D>`, or specialize `enable_view`.

## Why a view concept is needed

```cpp
std::vector<int> v = /* a million elements */;
auto r = v | std::views::filter(pred)
           | std::views::transform(f);
```

An adaptor stores its underlying range by value ([[range.adaptors]]). If `filter` stored a copy of the `vector`, every stage of the pipeline might copy the whole data set, and lazy evaluation would be pointless. In fact `v` is first wrapped by `views::all` into a `ref_view`, which stores only a pointer ([[range.all]]).

So adaptors need a concept that answers: which ranges can safely be stored by value? That concept is `view`; for the term see [[g:range-view]].

## Definition (¶1, ¶5)

¶1 `view` consists of three conditions:

```cpp
template<class T>
  concept view = range<T> && movable<T> && enable_view<T>;
```

`range<T>` requires `begin` and `end` ([[range.range]]). `movable<T>` requires `T` to be an object type that can be move-constructed, move-assigned and swapped ([[concepts.object]]).

¶5 The third condition, `enable_view<T>`, is a variable template that the type declares for itself. The reason is that `vector` and `span` both have `begin` and `end` and are both movable, so syntax cannot tell them apart; they differ in the cost of copying and destruction, which only the type's author can promise.

## Complexity requirements (¶2–¶4)

¶2 A type that satisfies the concept above models `view`, i.e. really is a view, only if it also meets these five conditions:

- ¶2.1 move construction is O(1);
- ¶2.2 move assignment is no more complex than destruction followed by move construction;
- ¶2.3 if N objects are copied or moved from an object containing M elements, destroying those N objects costs O(N+M) in total;
- ¶2.4 either it is not copy constructible, or copy construction is O(1);
- ¶2.5 either it is not copyable, or copy assignment is no more complex than destruction followed by copy construction.

¶3 Note 1 points out that these conditions imply that destroying a moved-from object is O(1).

The wording of ¶2.3 allows a view to own its elements, as long as those elements are destroyed only once in total. Compare these three types:

| Type | Destroying N copies | Conforms? |
|---|---|---|
| `owning_view<vector<int>>`: move-only, moved-from object is empty | one object destroys M elements, the other N−1 are empty | O(N+M), conforms |
| elements shared via `shared_ptr` | the last copy destroys M elements, the rest only decrement the reference count | O(N+M), conforms |
| copyable, every copy deep-copies the elements | each copy destroys M elements | copying itself already violates ¶2.4 |

¶4 Example 1 lists three typical views: a type wrapping a pair of iterators; a type holding its elements by `shared_ptr` with all copies sharing ownership; and a type that generates its elements on demand. `vector<string>` is not a view, because copying it copies all elements and cannot be done in constant time.

## How to declare a view (¶5–¶7)

```cpp
template<class T>
  constexpr bool enable_view =
    derived_from<T, view_base> || is-derived-from-view-interface<T>;
```

¶6 *is-derived-from-view-interface*`<T>` is an exposition-only variable template. It is `true` if and only if `T` has exactly one public base class `view_interface<U>` and no other base class of type `view_interface<V>`.

So there are three ways for a type to become a view:

1. Publicly inherit `std::ranges::view_base`, an empty tag class;
2. Publicly inherit `std::ranges::view_interface<Derived>` ([[view.interface]]), which also provides members such as `empty()`, `size()`, `front()` and `operator[]`. This is the usual recommendation;
3. Specialize `enable_view`. ¶7 allows users to specialize it for cv-unqualified program-defined types: `true` for types that model `view`, `false` for those that do not. The specialization must be usable in constant expressions and have type `const bool`.

Specializing to `false` has a real use: a type mistakenly treated as a view because it inherits from some base derived from `view_interface` can switch it off this way. The standard library's `basic_string_view` and `span` use method 3: their header synopses ([[string.view.synop]], [[span.syn]]) specialize both `enable_view` and `enable_borrowed_range` to `true`.

```cpp run ok
#include <memory>
#include <ranges>
#include <vector>
#include <cstdio>

// shared ownership: copying only increments a reference count, O(1)
class shared_ints : public std::ranges::view_interface<shared_ints> {
  std::shared_ptr<std::vector<int>> p_ = std::make_shared<std::vector<int>>();
public:
  shared_ints() = default;
  explicit shared_ints(std::vector<int> v)
    : p_(std::make_shared<std::vector<int>>(std::move(v))) {}
  auto begin() const { return p_->begin(); }
  auto end() const { return p_->end(); }
};
static_assert(std::ranges::view<shared_ints>);

// a move-only view
struct once : std::ranges::view_interface<once> {
  std::unique_ptr<int[]> data{new int[3]{1, 2, 3}};
  int* begin() const { return data.get(); }
  int* end() const { return data.get() + 3; }
};
static_assert(std::ranges::view<once> && !std::copyable<once>);

// satisfies the concept, but copying is O(M): does not model view
struct fat : std::ranges::view_base {
  std::vector<int> v;
  auto begin() const { return v.begin(); }
  auto end() const { return v.end(); }
};
static_assert(std::ranges::view<fat>);

int main() {
  auto r = shared_ints({1, 2, 3, 4})
         | std::views::transform([](int x) { return x * 10; });
  for (int x : r) std::printf("%d ", x);
  for (int x : once{} | std::views::reverse) std::printf("%d ", x);
  std::puts("");   // 10 20 30 40 3 2 1
}
```

The compiler only checks whether the concept is satisfied. `fat` claims to be a view and the `static_assert` passes, but its copy is a deep copy, violating ¶2.4. Put it in a pipeline and the program still runs, but every adaptor stage that copies it copies the whole `vector`. Strictly speaking, the program has then violated a library requirement ([[res.on.requirements]]), and the standard no longer guarantees anything about its behavior.

!!! pitfall "Exactly one view_interface base"
    If a class derives from both `view_interface<X>` and `view_interface<Y>`, for example by inheriting two views each defined with CRTP, *is-derived-from-view-interface* is false. The two bases would each provide `empty()`, `size()` and so on, which would be ambiguous anyway.

## History and evolution

!!! history "The definition of a view was relaxed three times"
    1. The original C++20 Ranges proposal ([[P0896R4]]) required views to be `semiregular` (copyable and default constructible), with O(1) copy, move and destruction. This effectively forbade views from owning elements.
    2. [[P1456R1]] (in C++20) relaxed `semiregular` to `movable`, allowing move-only views such as types holding a `unique_ptr` or a coroutine handle.
    3. [[P2325R3]] removed default constructibility from `view`, and the default constructors of the standard views became conditional (`requires default_initializable<V>`).
    4. [[P2415R2]] changed O(1) destruction to today's O(N+M) in ¶2.3, allowing move-only views that own elements, and accordingly added `owning_view`, making `views::all(std::move(vec))` valid ([[range.all]]).

    The last two were handled as defect reports (DRs) against C++20, so the major implementations use the new rules under `-std=c++20` too.

## Common misconceptions

!!! pitfall "A view is a range that does not own its elements"
    Today's definition cares only about cost, not ownership. `owning_view`, `single_view` (which holds one element) and `std::generator` (which owns a coroutine frame) are all views. A more accurate reading: passing a view by value never pushes the total cost beyond something linear in the number of elements.

!!! pitfall "Views are always copyable"
    `owning_view`, `generator`, and the results of adaptors over move-only views can only be moved. Generic code that takes a view by value as `std::ranges::view auto v` should pass it on with `std::move(v)` rather than copying it.

## Questions

!!! question "Question 1"
    Is it valid to explicitly specialize `enable_view` to `true` for `std::vector<int>`?

<details markdown="1">
<summary>Answer</summary>

No. ¶7 only allows specializations for program-defined types ([[namespace.std]]), and `std::vector<int>` is not a program-defined type. Even if it were allowed, its copy is O(N), so it would not model `view`.
</details>

!!! question "Question 2"
    Why doesn't ¶2.2 simply require move assignment to be O(1)?

<details markdown="1">
<summary>Answer</summary>

Move assignment first has to destroy what the left operand held. When a view owns its elements (like `owning_view`), destroying the old contents is O(M), which cannot be O(1). So the wording is "no more complex than destruction plus move construction": the cost of destruction is already bounded by the O(N+M) total in ¶2.3, and move construction is O(1).
</details>
