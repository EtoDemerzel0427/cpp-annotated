---
title: Algorithm result types
summary: "The nine result class templates returned by std::ranges algorithms (in_out_result, in_in_result, min_max_result and others): why ranges algorithms also return how far the input got, why they are aggregates, the [[no_unique_address]] on their members, and member-wise conversion only within the same template."
updated: 2026-10-19
---

!!! tldr
    - `ranges` algorithms return all the useful information they compute, so `ranges::copy` returns the ends of both the input and the output, not just the output end.
    - The return value is one of nine class templates, such as `in_out_result<I, O>`; the member names `in` and `out` are specified by the standard and can be unpacked with structured bindings.
    - They are aggregates with no base classes and no extra members; every member except `found` carries `[[no_unique_address]]`, so empty function objects take no space.
    - When the argument is a temporary range that will be destroyed, the iterator members become `ranges::dangling`, and misusing them fails to compile.

```cpp run title="results.cpp" ok
#include <algorithm>
#include <cassert>
#include <ranges>
#include <type_traits>
#include <vector>

std::vector<int> make() { return {3, 1, 2}; }

int main() {
  std::vector<int> src{1, 2, 3}, dst(3);
  auto [in, out] = std::ranges::copy(src, dst.begin());
  assert(in == src.end() && out == dst.end());

  // rvalue non-borrowed range: returns ranges::dangling
  auto it = std::ranges::max_element(make());
  static_assert(std::is_same_v<decltype(it), std::ranges::dangling>);
  // *it;   // error: dangling cannot be dereferenced

  auto mm = std::ranges::minmax({3, 1, 4, 1, 5});   // min_max_result<int>
  assert(mm.min == 1 && mm.max == 5);

  // member-wise conversion
  int a[2]{};
  std::ranges::in_out_result<int*, int*> r{a, a + 1};
  std::ranges::in_out_result<const int*, int*> r2 = r;
  assert(r2.in == a);
}
```

## Why return the input's end

The classic `std::copy(first, last, out)` returns only the output end. For classic algorithms this loses nothing, because the caller already has `last`.

C++20 algorithms allow the end to be a **sentinel** of a different type, such as `unreachable_sentinel_t`, or a condition like "stop on reading 0". Then the caller only knows when to stop, not which iterator it stopped at. If the input is a single-pass iterator like `istream_iterator`, information once lost can never be recovered. So C++20 Ranges ([[P0896R4]]) adopted the principle that algorithms return all the useful information they compute. `ranges::copy` therefore returns two iterators, `{in, out}`, which calls for a set of result types with named members.

## The nine class templates (¶1)

| Class template | Members | `ranges` algorithms that use it (aliases) |
|---|---|---|
| `in_fun_result<I, F>` | `in`, `fun` | `for_each_result`, `for_each_n_result` |
| `in_in_result<I1, I2>` | `in1`, `in2` | `mismatch_result`, `swap_ranges_result` |
| `in_out_result<I, O>` | `in`, `out` | `copy_result`, `move_result`, `unary_transform_result`, `remove_copy_result`, `set_difference_result` and others |
| `in_in_out_result<I1, I2, O>` | `in1`, `in2`, `out` | `binary_transform_result`, `merge_result`, `set_union_result`; C++26's `reverse_copy_truncated_result` and others |
| `in_out_out_result<I, O1, O2>` | `in`, `out1`, `out2` | `partition_copy_result` |
| `min_max_result<T>` | `min`, `max` | `minmax_result`, `minmax_element_result` |
| `in_found_result<I>` | `in`, `found` | `next_permutation_result`, `prev_permutation_result` |
| `in_value_result<I, T>` | `in`, `value` | `fold_left_with_iter_result`, `fold_left_first_with_iter_result` |
| `out_value_result<O, T>` | `out`, `value` | `iota_result` in `<numeric>` |

!!! std
    Each of the class templates specified in this subclause has the template parameters, data members, and special members specified below, and has no base classes or members other than those specified.

No base classes and no other members guarantees that they are all aggregates. So they can be unpacked with structured bindings ([[dcl.struct.bind]]), and the `return {last, result + N};` common in the wording can construct them directly with braces. The member names are part of the specification; `r.in` and `r.out` work on every implementation.

### `[[no_unique_address]]`

Every member except `in_found_result::found` (a `bool`) is marked `[[no_unique_address]]` ([[dcl.attr.nouniqueaddr]]). Iterators and function objects are often empty classes, such as captureless lambdas and `unreachable_sentinel_t`, and then the result object need not allocate storage for them. With Clang in our tests, `for_each_result<int*, Lambda>` is the same size as a pointer, 8 bytes.

### Member-wise conversion

Each template has a pair of conversion function templates. The `const&` version copies the members and the `&&` version moves them; the constraint is that each member is convertible to the corresponding member of the target type:

```cpp
template<class I2, class O2>
  requires convertible_to<const I&, I2> && convertible_to<const O&, O2>
constexpr operator in_out_result<I2, O2>() const & { return {in, out}; }
```

So an `in_out_result<int*, int*>` can be converted to an `in_out_result<const int*, int*>`, as in the last few lines of the opening example. Conversion functions are used rather than converting constructors because aggregates cannot have user-declared constructors. Conversion happens only within the same class template; an `in_out_result` cannot become an `in_in_result`.

## Working with `dangling`

The result types have no safety mechanism of their own. The protection comes from the return types of the range overloads: they use `borrowed_iterator_t<R>` as the type of the iterator members. When the argument is an rvalue and not a borrowed range (a range whose iterators do not depend on the range object staying alive, like `std::span`), this type is `ranges::dangling` ([[range.dangling]]). A temporary `vector` is destroyed at the end of the full-expression, so an iterator into it would inevitably dangle; `dangling` moves that error to compile time.

!!! pitfall "Are the members of `min_max_result` values or iterators"
    `ranges::minmax` returns `min_max_result<T>`, whose members are values (`const T&` when the arguments are lvalues); `ranges::minmax_element` returns `min_max_result<I>`, whose members are iterators. The members are named `min` and `max` in both cases, with entirely different meanings; see [[alg.min.max]].

## Questions

!!! question "Question"
    `ranges::set_difference` returns an `in_out_result`, with only the end of the first input; `ranges::set_union` returns an `in_in_out_result`. Why?

<details markdown="1">
<summary>Answer</summary>

`set_difference` outputs the elements that are in the first sequence but not in the second. The algorithm ends once the first sequence is exhausted; the second sequence may not have been fully traversed, and where it stopped means nothing to the caller. `set_union`, on the other hand, traverses both sequences to the end.

C++26's parallel `ranges` version has an output bound and may stop partway, so it returns `set_difference_truncated_result`, i.e. `in_in_out_result`, telling the caller how far each of the two inputs was processed; see [[alg.set.operations]].
</details>
