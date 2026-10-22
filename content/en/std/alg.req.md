---
title: Common algorithm requirements
summary: "The composite concepts commonly used by families of algorithms: moving, copying and swapping elements between iterators, comparing across sequences, and permuting, merging and sorting in place."
updated: 2026-10-19
---

!!! tldr
    - This subclause gives names to constraint combinations algorithms use often: moving, copying and swapping elements, comparing across sequences, and permuting, merging and sorting in place.
    - The `_storable` versions additionally require that an element can first be stored in a temporary of the value type and then written out; algorithms that need to hold an element aside, like `sort` and `rotate`, use them.
    - `sortable` only describes whether elements can be sorted, not the traversal category; `ranges::sort` additionally requires random access, so `std::list`'s iterator is `sortable` but cannot be passed to `ranges::sort`.
    - The default comparator `ranges::less` requires the type to be `totally_ordered`, so a type that defines only `operator<` works with `std::sort` but not with `ranges::sort`.

A single iterator concept describes what one iterator can do ([[iterator.concepts]]). What algorithms care about is often the relation among several types: can what is read from `In` be written into `Out`, can two elements be swapped in place, can the elements of two sequences be compared with a comparator.

¶1 [alg.req.general] divides these combinations into three groups:

- transferring elements between readable and writable types: `indirectly_movable`, `indirectly_copyable`, `indirectly_swappable`;
- rearranging: `permutable`, `mergeable`, `sortable`;
- comparing across sequences: `indirectly_comparable`.

## The default comparator is constrained too (¶2)

<div class="compare" markdown="1">

```cpp run error
#include <algorithm>
#include <vector>
struct L {
  int v;
  bool operator<(const L& o) const
  { return v < o.v; }
};
int main() {
  std::vector<L> v{{2}, {1}};
  std::sort(v.begin(), v.end());  // OK
  std::ranges::sort(v);  // error
}
```

```cpp run ok
#include <algorithm>
#include <vector>
struct S {
  int v;
  auto operator<=>(const S&) const
    = default;
};
int main() {
  std::vector<S> v{{2}, {1}};
  std::sort(v.begin(), v.end());  // OK
  std::ranges::sort(v);           // OK
}
```

</div>

¶2 Note 1 reminds us that `ranges::less`, used as a default argument by several of the concepts below, is itself constrained ([[range.cmp]]): it requires the types on both sides to model `totally_ordered_with`, that is, `==`, `!=`, `<`, `>`, `<=` and `>=` must all exist. `L` on the left has only `operator<`, so it is not `sortable<L*>`. The simplest fix is to default `operator<=>` as on the right, which brings `==` along as well. Alternatively, pass `std::less<>{}` explicitly as the comparator.

## Moving and copying [alg.req.ind.move] [alg.req.ind.copy]

```cpp
template<class In, class Out>
concept indirectly_movable =
  indirectly_readable<In> && indirectly_writable<Out, iter_rvalue_reference_t<In>>;

template<class In, class Out>
concept indirectly_movable_storable =
  indirectly_movable<In, Out> &&
  indirectly_writable<Out, iter_value_t<In>> &&
  movable<iter_value_t<In>> &&
  constructible_from<iter_value_t<In>, iter_rvalue_reference_t<In>> &&
  assignable_from<iter_value_t<In>&, iter_rvalue_reference_t<In>>;
```

¶1 `indirectly_movable` means `*out = ranges::iter_move(in)` works, moving the element straight across; `ranges::move` uses it.

¶2 `indirectly_movable_storable` additionally requires that the element can first be moved into a temporary of the value type and then moved out of it. Algorithms like `rotate` and `sort`, which need to take an element out and hold it aside, need this concept. ¶3 Semantic requirement: after `iter_value_t<In> obj(ranges::iter_move(i));`, `obj` equals the previous value of `*i`; if `iter_rvalue_reference_t<In>` is an rvalue reference, `*i` is in a valid but unspecified state ([[lib.types.movedfrom]]).

The copying versions are parallel:

```cpp
template<class In, class Out>
concept indirectly_copyable =
  indirectly_readable<In> && indirectly_writable<Out, iter_reference_t<In>>;

template<class In, class Out>
concept indirectly_copyable_storable =
  indirectly_copyable<In, Out> &&
  indirectly_writable<Out, iter_value_t<In>&> &&
  indirectly_writable<Out, const iter_value_t<In>&> &&
  indirectly_writable<Out, iter_value_t<In>&&> &&
  indirectly_writable<Out, const iter_value_t<In>&&> &&
  copyable<iter_value_t<In>> &&
  constructible_from<iter_value_t<In>, iter_reference_t<In>> &&
  assignable_from<iter_value_t<In>&, iter_reference_t<In>>;
```

¶2 The `_storable` version requires the stored value to be writable into `Out` in all four forms (lvalue, const lvalue, rvalue, const rvalue), because how an algorithm uses the stored value is not restricted. ¶3 Semantic requirement: after `iter_value_t<In> obj(*i);`, `obj` equals the previous value of `*i`; if `iter_reference_t<In>` is itself an rvalue reference (as with `move_iterator`), `*i` is in a valid but unspecified state.

`ranges::copy` requires only `indirectly_copyable`. `ranges::unique_copy` has to remember the previous element: with forward iterators as input it can remember an iterator, but otherwise it often has to copy the element into a value, and then it requires `indirectly_copyable_storable`.

## Swapping [alg.req.ind.swap]

```cpp
template<class I1, class I2 = I1>
concept indirectly_swappable =
  indirectly_readable<I1> && indirectly_readable<I2> &&
  requires(const I1 i1, const I2 i2) {
    ranges::iter_swap(i1, i1);
    ranges::iter_swap(i2, i2);
    ranges::iter_swap(i1, i2);
    ranges::iter_swap(i2, i1);
  };
```

¶1 This concept is built entirely on the customization point `ranges::iter_swap` ([[iterator.cust]]). The arguments are `const I1` because what is swapped is the elements the iterators point to; whether the iterators themselves are const does not matter.

## Comparing [alg.req.ind.cmp]

```cpp
template<class I1, class I2, class R, class P1 = identity, class P2 = identity>
concept indirectly_comparable =
  indirect_binary_predicate<R, projected<I1, P1>, projected<I2, P2>>;
```

¶1 It means the elements of two sequences, each after its projection, can be compared with `R` (for `projected` see [[indirectcallable]]). `ranges::equal`, `ranges::search` and `ranges::find_first_of` use it.

## Rearranging [alg.req.permutable] [alg.req.mergeable] [alg.req.sortable]

```cpp
template<class I>
concept permutable =
  forward_iterator<I> && indirectly_movable_storable<I, I> && indirectly_swappable<I, I>;

template<class I1, class I2, class Out, class R = ranges::less,
         class P1 = identity, class P2 = identity>
concept mergeable =
  input_iterator<I1> && input_iterator<I2> && weakly_incrementable<Out> &&
  indirectly_copyable<I1, Out> && indirectly_copyable<I2, Out> &&
  indirect_strict_weak_order<R, projected<I1, P1>, projected<I2, P2>>;

template<class I, class R = ranges::less, class P = identity>
concept sortable = permutable<I> && indirect_strict_weak_order<R, projected<I, P>>;
```

- `permutable` is the minimum condition for rearranging in place: a forward iterator that can store aside and swap. `rotate`, `partition`, `remove` and others use it; `reverse` additionally requires bidirectional.
- `mergeable` copies two sorted input sequences into an output, merging them; it is not an in-place operation, so it requires only input iterators and `indirectly_copyable`.
- `sortable` is `permutable` plus a strict weak ordering after projection.

`sortable` contains no random access requirement. `ranges::sort`, `ranges::stable_sort` and `ranges::partial_sort` each add `random_access_iterator`, and `ranges::inplace_merge` adds `bidirectional_iterator`.

```cpp run title="alg_req.cpp" ok
#include <iterator>
#include <list>
#include <memory>
#include <vector>

// sortable does not care about the traversal category
static_assert(std::sortable<std::list<int>::iterator>);
// a const_iterator cannot be written through, so it is not permutable
static_assert(!std::sortable<std::vector<int>::const_iterator>);

// unique_ptr: can be stored aside by moving, not by copying
using UP = std::unique_ptr<int>*;
static_assert(std::indirectly_movable_storable<UP, UP>);
static_assert(!std::indirectly_copyable_storable<UP, UP>);
static_assert(std::permutable<std::vector<std::unique_ptr<int>>::iterator>);

// proxy iterators can be permutable too
static_assert(std::permutable<std::vector<bool>::iterator>);

int main() {}
```

`std::ranges::sort(lst)` on a `std::list` fails to compile, and Clang's diagnostic points to `random_access_range` not being satisfied, not to `sortable`. The two divide the work: `sortable` says whether the elements can be sorted, the traversal concepts say whether the algorithm can move around the sequence efficiently. To find out exactly what an algorithm requires, look at its own declaration ([[algorithms]]).

## Questions

!!! question "Question 1"
    Why does `permutable` require `forward_iterator` rather than just `input_iterator`?

<details markdown="1">
<summary>Answer</summary>

Rearranging in place needs to go back and write to positions already passed: `remove` moves later elements forward, `rotate` has to remember the middle. That requires iterators that can be copied and kept, with the same position accessible multiple times, i.e. the multi-pass guarantee ([[iterator.concept.forward]]). A single-pass iterator is spent once it moves on, so it cannot rearrange in place.
</details>

!!! question "Question 2"
    Why does `mergeable` use `indirectly_copyable` rather than `indirectly_copyable_storable`?

<details markdown="1">
<summary>Answer</summary>

Each step of a merge only compares the current elements of the two inputs and copies the smaller one directly from its input to the output, with no intermediate storage. So the concept does not require the value type to be copy constructible, and it also works when elements are expensive to copy or can only be read and written through proxies.
</details>
