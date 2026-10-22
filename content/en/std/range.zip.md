---
title: "The zip family: zip, zip_transform, adjacent, adjacent_transform"
summary: "C++23's views::zip traverses several ranges at once, each element being a tuple of references to the corresponding elements, with the length of the shortest; zip_transform calls a function on corresponding elements; adjacent<N> and pairwise give sliding windows of length N, and adjacent_transform calls a function on each window."
updated: 2026-10-19
---

!!! tldr
    - The elements of `views::zip(a, b)` are temporary tuples of references like `tuple<A&, B&>`, so structured bindings can write back; traversal stops when the shortest range ends.
    - The iterator category is the weakest among the ranges; `zip` and `zip_transform` are customization point objects with no pipe form.
    - `ranges::sort(views::zip(keys, vals))` sorts two arrays together by `keys`.
    - `views::adjacent<N>` gives sliding windows of length N, whose elements are tuples of N references; `views::pairwise` is `adjacent<2>`. When the window length is only known at run time, use `views::slide`.
    - `zip_transform` and `adjacent_transform` call a function on corresponding elements or on each window, an n-ary `transform`; they are not borrowed ranges.

```cpp run ok
#include <cstdio>
#include <ranges>
#include <vector>

int main() {
  std::vector<int> v{1, 2, 3, 4};
  std::vector<char> c{'a', 'b', 'c'};
  for (auto [x, ch] : std::views::zip(v, c))
    std::printf("%d%c ", x, ch);               // 1a 2b 3c: the length of the shortest
  for (auto [p, q] : v | std::views::pairwise)
    std::printf("(%d,%d)", p, q);              // (1,2)(2,3)(3,4)
  std::puts("");
}
```

[[P2321R2]] added two kinds of views to C++23: traversing several sequences at once, and sliding windows. They are implemented the same way: internally the iterator is a set of underlying iterators, and `operator*` dereferences each of them and assembles the results into a `tuple` (using *tuple-transform* from [[range.adaptor.helpers]]).

## `views::zip` [range.zip]

¶1 `zip_view` takes any number of views and produces a view of tuples of references to the corresponding elements of each view. ¶2 `views::zip` is a [[customization.point.object|customization point object]]: with no arguments it gives an empty view with element type `tuple<>`; otherwise it is equivalent to `zip_view<views::all_t<decltype((Es))>...>(Es...)`. Because it is not a range adaptor object, `a | views::zip(b)` is not valid.

### Elements and length

The elements of `zip_view` have two types:

- The result of dereferencing is `tuple<range_reference_t<Views>...>`, a tuple prvalue holding references ([range.zip.iterator] ¶6). `auto [x, y]` copies this tuple, but its components are references, so `x` and `y` refer to the underlying elements and can be written back.
- `value_type` is `tuple<range_value_t<Views>...>`.

To make such reference tuples satisfy `indirectly_readable` and `indirectly_writable`, P2321 also changed `tuple` and `pair` themselves: it added const-qualified assignment operators and the corresponding `basic_common_reference` specializations.

Traversal stops when any component reaches its end. [range.zip.view] ¶3 `size()` is the minimum of the component sizes (after conversion to their common unsigned type).

```cpp run ok
#include <algorithm>
#include <cstdio>
#include <ranges>
#include <vector>

int main() {
  std::vector<int> keys{3, 1, 2};
  std::vector<char> vals{'c', 'a', 'b'};
  for (auto [k, v] : std::views::zip(keys, vals)) k *= 10;   // writes back to keys
  std::ranges::sort(std::views::zip(keys, vals));            // sorts both together by keys
  for (auto [k, v] : std::views::zip(keys, vals))
    std::printf("%d%c ", k, v);                               // 10a 20b 30c
  std::puts("");
}
```

Sorting works because `iter_swap` in ¶21 calls `ranges::iter_swap` on each component separately, `iter_move` in ¶19 likewise works component by component, and C++23's `tuple<int&, char&>` can be assigned to as a const object. The same code does not compile in C++20.

### Iterator category and commonness

¶1 The iterator category is the weakest among the components: random access if all are random access, bidirectional if all are bidirectional, and so on. [range.zip.view] ¶1 says two `zip_view`s have the same underlying sequence only if all their components are equal; comparing iterators from different `zip_view`s is meaningless.

`==` in ¶13 has a special design:

- when all components are bidirectional iterators, they are equal only if all components are equal;
- otherwise, they are equal if any one component is equal.

The latter rule lets `zip_view` be a common range (Note 1). A tuple of the components' `end()`s can be used directly as the end iterator: when the lengths differ, the longer components never reach their own `end()`; only the shortest one hits it, and at that point the comparison holds. Sentinel comparison ([range.zip.sentinel] ¶3) uses the same any-component-equal rule.

Bidirectional iterators cannot do this: when stepping back with `--` from the end, every component must go back to the same index, but their `end()`s correspond to different indices. So `zip_view` is a common range (the exposition-only concept *zip-is-common*) under one of these three conditions:

- there is only one component and it is a common range;
- not all components are bidirectional, and all are common ranges;
- all are random access and all are sized; then `end()` is computed as `begin() + size()`, and all components are aligned to the shortest length.

`zip_view` is a [[g:borrowed-range|borrowed range]] when all its components are.

## `views::zip_transform` [range.zip.transform]

¶1 `zip_transform_view` takes a callable object and any number of views; its M-th element is the result of calling the object with the M-th elements of all the views. ¶3 Example 1: `zip_transform(plus(), {1, 2}, {4, 5, 6})` gives `5 7`.

¶2 It is a customization point object too. With no view arguments, it gives an empty view whose element type is the function's return type; in that case it is ill-formed if the function cannot be called with no arguments or does not return an object type. Otherwise it is equivalent to `zip_transform_view(F, Es...)`.

`zip_transform_view` internally stores a `zip_view` and the function object; it is an n-ary [[range.transform]]: every dereference calls the function once; when the function returns a prvalue, `iterator_category` is `input_iterator_tag`; and it is not a borrowed range.

## `views::adjacent<N>` and `views::pairwise` [range.adjacent]

¶1 The M-th element of `adjacent_view` is a tuple of references to the M-th through (M+N−1)-th elements of the original view; if the original view has fewer than N elements, the result is empty. ¶2 `views::adjacent<N>(E)` gives an empty view with element type `tuple<>` when N is 0, and otherwise is `adjacent_view<views::all_t<decltype((E))>, N>(E)`. `views::pairwise` is just `adjacent<2>`.

```cpp run ok
#include <cstdio>
#include <functional>
#include <ranges>
#include <vector>

int main() {
  std::vector v{1, 2, 3, 4};
  for (auto i : v | std::views::adjacent<2>)
    std::printf("(%d, %d) ", std::get<0>(i), std::get<1>(i));   // (1, 2) (2, 3) (3, 4)
  for (auto i : v | std::views::adjacent_transform<2>(std::multiplies()))
    std::printf("%d ", i);                                       // 2 6 12
  std::puts("");
}
```

`adjacent_view` requires the underlying range to be a forward range, because the N elements of a window have to be referenced at the same time. The iterator stores N underlying iterators pointing to each position in the window, and `++` advances all of them by one. The element type is a tuple of N `range_reference_t<V>` (¶3 defines the exposition-only *REPEAT*).

N is a template argument, so the window length must be known at compile time. When the length is known only at run time, use `views::slide(n)` from [[range.chunk]], whose elements are subranges rather than tuples.

[range.adjacent.view] ¶2 `size()` is the underlying size minus N−1, at least 0. The iterator does not access the view object, so `adjacent_view` is a borrowed range when the underlying range is.

## `views::adjacent_transform<N>` and `views::pairwise_transform` [range.adjacent.transform]

¶1 The M-th element of `adjacent_transform_view` is the result of calling a function with the M-th through (M+N−1)-th elements. ¶2 When N is 0 it is equivalent to `views::zip_transform(F)` (with `E` still evaluated); otherwise it is an `adjacent_transform_view`. `views::pairwise_transform` is `adjacent_transform<2>`.

Typical uses are adjacent differences (`pairwise_transform(std::minus{})`), checking whether a sequence is sorted, and computing the distances between adjacent points. Like `zip_transform`, it is not a borrowed range.

```cpp run ok
#include <cstdio>
#include <functional>
#include <ranges>
#include <vector>

int main() {
  std::vector<int> v{10, 20, 30, 4};
  for (int d : v | std::views::pairwise_transform(std::minus{}))
    std::printf("%d ", d);                       // -10 -10 26
  std::puts("");
}
```

## Summary

| View | Elements | Kind | Iterator category | Borrowed range |
|---|---|---|---|---|
| `zip(rs...)` | `tuple<references...>` | customization point object | the weakest of the components | when all are |
| `zip_transform(f, rs...)` | `f(elements...)` | customization point object | the weakest of the components | no |
| `adjacent<N>`, `pairwise` | a tuple of N references | range adaptor | same as underlying (at least forward) | when the underlying range is |
| `adjacent_transform<N>(f)`, `pairwise_transform(f)` | `f(N elements)` | range adaptor | same as underlying | no |

<details class="fine" markdown="1"><summary>Remaining wording</summary>

[range.zip.iterator] ¶3: if a non-const member function of the iterator throws, the iterator becomes singular. ¶17–¶18 and [range.zip.sentinel] ¶4–¶5: the difference of two iterators is the component difference with the smallest absolute value. ¶20 and ¶22 specify the exception specifications of `iter_move` and `iter_swap`.

[range.zip.transform.view], [range.adjacent.iterator], [range.adjacent.transform.iterator] and their respective sentinel subclauses specify the constructors and operations one by one, all forwarding to the internal `zip_view` or the array of underlying iterators.

</details>
