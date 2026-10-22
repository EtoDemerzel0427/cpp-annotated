---
title: Join and join_with views
summary: "views::join flattens a range of ranges into one range, and views::join_with inserts a separator between adjacent inner ranges; whether the inner ranges are references or temporaries decides whether the result can be traversed forward and whether it can be traversed as const."
updated: 2026-10-19
---

!!! tldr
    - `views::join` flattens a `vector<vector<int>>` into a sequence of `int`s, skipping empty inner ranges.
    - When the inner ranges are references to the outer elements, the result can be up to a bidirectional range and can also be traversed as const.
    - When the inner ranges are temporaries (e.g. a `transform` that returns `std::string`), they are stashed in the view, the result is only an input range, and it cannot be traversed as const.
    - `views::join_with(sep)` inserts the separator only between adjacent inner ranges, not at the start or end; the separator can be a single element or a range.
    - A string literal cannot be used directly as the separator; write a `string_view` or a single character.

```cpp run ok
#include <iostream>
#include <ranges>
#include <string>
#include <vector>

int main() {
  std::vector<std::string> ss{"hello", " ", "world", "!"};
  for (char ch : ss | std::views::join) std::cout << ch;     // hello world!

  std::vector<std::string> vs{"the", "quick", "brown", "fox"};
  for (char c : vs | std::views::join_with('-')) std::cout << c;
  std::cout << '\n';                                          // the-quick-brown-fox
}
```

These two parts are the standard examples in [range.join.overview] ¶3 and [range.join.with.overview] ¶3. `join` is the inverse of [[range.split]], joining the cut pieces back together; `transform` plus `join` is what other languages call `flat_map` (one element becomes several).

## `views::join` [range.join.overview]

¶1 `join_view` flattens a view of ranges into a view. ¶2 `views::join(E)` is equivalent to `join_view<views::all_t<decltype((E))>>{E}`, with no special cases.

A `join_view` iterator has to remember two positions at once: which inner range the outer iterator has reached, and which element within that inner range. Almost all of the complexity in the rules comes from one question: where is the inner range object stored?

## Inner ranges are references: the iterator remembers everything [range.join.iterator]

The element type of `vector<vector<int>>` is `vector<int>&`; the inner range lives inside the outer container and keeps existing. The iterator only needs to store an outer iterator and an inner iterator, and can return to the outer level at any time. The standard distinguishes this case with the exposition-only constant *ref-is-glvalue* (whether `range_reference_t<Base>` is a reference type).

¶1 When the inner ranges are references, the iterator category is:

- bidirectional when the outer range is bidirectional and the inner range is bidirectional and a [[g:common-range|common range]] (`begin()` and `end()` have the same type);
- forward when both the outer and inner ranges are forward ranges;
- input otherwise (¶1.3).

Bidirectional also requires the inner range to be common because when `--` steps back from the next inner range into the previous one, it walks back from the previous inner range's `end()` (¶15), and that `end()` must be an iterator that can be decremented.

```cpp run ok
#include <cstdio>
#include <ranges>
#include <vector>

int main() {
  std::vector<std::vector<int>> vv{{1, 2}, {}, {3}};
  auto flat = vv | std::views::join;
  static_assert(std::ranges::bidirectional_range<decltype(flat)>);
  static_assert(std::ranges::range<const decltype(flat)>);
  static_assert(!std::ranges::sized_range<decltype(flat)>);
  for (int x : flat) std::printf("%d", x);                         // 123
  for (int x : flat | std::views::reverse) std::printf(" %d", x);  // 3 2 1
  std::puts("");
}
```

`join_view` is never a sized range: the total length is known only after looking at every inner range. It is not a borrowed range either.

### Skipping empty inner ranges (¶4–¶6)

¶4 The iterator skips empty inner ranges with the exposition-only function *satisfy*. *satisfy*, defined in ¶6, keeps advancing the outer iterator until it finds a non-empty inner range or the outer range ends; it is called when the iterator is constructed (¶7–8) and every time `++` finishes an inner range (¶13). So `{{1, 2}, {}, {3}}` flattens to `1 2 3`; the empty `{}` produces no elements.

Hence `++` is not strictly O(1): when there are many consecutive empty inner ranges, one `++` skips all of them.

## Inner ranges are temporaries: stashed in the view [range.join.view]

```cpp run ok
#include <cstdio>
#include <ranges>
#include <string>
#include <vector>

int main() {
  std::vector<int> v{1, 2, 3};
  auto j = v | std::views::transform([](int i) { return std::string(i, 'x'); })
             | std::views::join;
  static_assert(std::ranges::input_range<decltype(j)>);
  static_assert(!std::ranges::forward_range<decltype(j)>);
  static_assert(!std::ranges::range<const decltype(j)>);
  for (char c : j) std::putchar(c);   // xxxxxx
  std::puts("");
}
```

Here, dereferencing the outer iterator returns a new `std::string` temporary each time. The inner iterator points into it, so it has to be stored somewhere; otherwise it would be destroyed at the end of the expression, and the inner iterator would dangle along with it.

`join_view` stores it in the view object's member `inner_`. `inner_` is a [[range.nonprop.cache|non-propagating-cache]] (a cache not copied along when the view is copied), and every time a new outer element is entered, *satisfy* reconstructs the inner range in it (the *emplace-deref* in ¶6).

The consequences:

- Part of the iterator's state lives in the view, so two iterators cannot each stop on a different inner range; the result can only be an input range (¶1.3);
- Writing `inner_` modifies the view, so there is no const `begin()`;
- `ranges::to<std::vector>` cannot know the size in advance, and you cannot wrap `reverse` around the result.

When you need multiple passes, materialize into a container first, or make the transformation function return a lightweight view.

### When the outer range is only an input range

When the outer `V` is only an input range, the outer iterator is also stored in the view, in the `outer_` cache: `begin()` first performs `outer_ = ranges::begin(base_)`, and the iterator itself only stores a pointer to the view ([range.join.iterator] ¶5, ¶8). This design comes from [[P2770R0]], merged as a defect report during C++23. The problem it fixes: some input iterators return, on dereference, a reference into the iterator itself, and once the iterator is moved, the inner range obtained earlier dangles.

## `views::join_with`: flattening with a separator [range.join.with] {{c++23}}

¶1 `join_with_view` takes a view and a delimiter, flattens the view, and inserts every element of the delimiter between adjacent inner ranges. The delimiter can be a single element or a view of elements. ¶2 `views::join_with(E, F)` is equivalent to `join_with_view(E, F)` ([[P2441R2]]).

```cpp run ok
#include <cstdio>
#include <ranges>
#include <string>
#include <string_view>
#include <vector>

int main() {
  std::vector<std::string> words{"a", "bc", "d"};
  auto s = words | std::views::join_with(std::string_view(", "))
                 | std::ranges::to<std::string>();
  std::printf("[%s]\n", s.c_str());                  // [a, bc, d]

  std::vector<std::vector<int>> vv{{1, 2}, {}, {3}};
  for (int x : vv | std::views::join_with(0))
    std::printf("%d", x);                            // 12003
  std::puts("");
}
```

The second example shows that an empty inner range still counts as an element: one 0 is inserted between `{1, 2}` and `{}`, and another between `{}` and `{3}`, giving `1 2 0 0 3`. No separator is added at the start or end.

`join_with_view` makes the same *ref-is-glvalue* distinction as `join_view`: when the inner ranges are temporaries they are stashed in the view's `inner_`, and when the outer range is only an input range the outer iterator is stored in `outer_it_`, with the same conclusions. A few other points:

- When the separator is a single element, the deduction guide and the second constructor ([range.join.with.view] ¶2) wrap it in a `single_view`.
- The constraints require the inner range and the separator to be *concatable* (shared with [[range.concat]]): their elements must have a common reference type and value type. ¶12 The iterator's `operator*` returns the `common_reference_t` of the two reference types.
- Internally the iterator holds its current position in a `variant`, which points either into the separator or into an inner range (¶8, ¶13).

## Common misconceptions

!!! pitfall "Using a string literal as the separator"
    `w | views::join_with("--")` fails to compile. The pipe form first stores its arguments by value ([[range.adaptor.object#8]]), so the array decays to `const char*`, which is neither a range nor a `char`.

    The function call form `views::join_with(w, "--")` compiles, but the result is wrong: the array does not decay and is wrapped in a `ref_view<const char[3]>`, so the separator includes the terminating `'\0'`.

    ```cpp run ok
    #include <cstdio>
    #include <ranges>
    #include <string>
    #include <vector>

    int main() {
      std::vector<std::string> w{"a", "b"};
      auto s = std::views::join_with(w, "--") | std::ranges::to<std::string>();
      std::printf("%zu\n", s.size());   // 5: a - - \0 b
    }
    ```

    Write the separator as `std::string_view("--")` or a single character instead.

## Summary

| Case | Iterator category | Traversable as const | State stored in |
|---|---|---|---|
| inner ranges are references; outer and inner bidirectional, inner common | bidirectional | yes | the iterator |
| inner ranges are references; outer and inner forward | forward | yes | the iterator |
| inner ranges are temporaries | input | no | the view's `inner_` |
| outer range is only an input range | input | no | the view's `outer_` |

<details class="fine" markdown="1"><summary>Remaining wording</summary>

[range.join.view] ¶1: the constructor stores the underlying view. `end()` returns an iterator, making the result a common range, when the outer and inner ranges are both forward and common and the inner ranges are references; otherwise it returns a sentinel.

[range.join.iterator] ¶2–3: `iterator_category` is defined only when the inner ranges are references and both the outer and inner ranges are forward ranges; it is the weaker of the outer and inner categories. `difference_type` is the common type of the two difference types. ¶7–10 are the constructors, ¶11 is `operator->`, ¶12–14 are `++`, ¶16 is equality comparison, ¶17 is `iter_swap`.

[range.join.sentinel] ¶1–3: the sentinel stores the outer end; the iterator is at the end when its outer position reaches it.

[range.join.with.iterator] and [range.join.with.sentinel] have the same structure; the `value_type` is the common type of the inner and separator value types (¶3).

</details>
