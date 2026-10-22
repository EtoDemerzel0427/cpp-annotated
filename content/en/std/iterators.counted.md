---
title: counted_iterator
summary: "counted_iterator<I> records, next to the underlying iterator, how many elements are left; paired with default_sentinel it denotes the n elements starting at a position, and comparisons and subtraction look only at the count."
updated: 2026-10-19
---

!!! tldr
    - `counted_iterator(it, n)` plus `default_sentinel` denotes the `n` elements starting at `it`, without knowing the end in advance.
    - Comparison and subtraction look only at the remaining count, so the distance to `default_sentinel` is always available in constant time, even when the underlying iterator is a `list` iterator.
    - Looking only at the count assumes both iterators refer to the same sequence, i.e. the positions where their counts reach zero line up; otherwise it is UB.
    - The traversal category is inherited unchanged from the underlying iterator, contiguous included.
    - With an `istream_iterator` underneath, the `++` that brings the count to zero reads one extra element from the stream.

## Counted ranges [counted.iterator]

```cpp run title="counted.cpp" ok
#include <algorithm>
#include <cassert>
#include <iterator>
#include <list>
#include <vector>

int main() {
  std::list<int> l{1, 2, 3, 4, 5, 6};
  std::vector<int> out;
  std::ranges::copy(std::counted_iterator(l.begin(), 4),
                    std::default_sentinel,
                    std::back_inserter(out));
  assert((out == std::vector{1, 2, 3, 4}));

  // list iterators are only bidirectional, but the distance of a counted range is available in constant time
  using CI = std::counted_iterator<std::list<int>::iterator>;
  static_assert(std::sized_sentinel_for<std::default_sentinel_t, CI>);
  static_assert(std::bidirectional_iterator<CI>);
  static_assert(!std::random_access_iterator<CI>);
  CI it(l.begin(), 4);
  assert(std::default_sentinel - it == 4);

  // the contiguous category is kept
  static_assert(std::contiguous_iterator<std::counted_iterator<int*>>);
}
```

[[iterator.requirements.general#11]] defines the **counted range** `i+[0, n)`: the `n` elements starting at `i`. ¶1 `counted_iterator` turns it into an iterator: it behaves like the underlying iterator and additionally keeps track of the distance to the end of the range. Together with `default_sentinel` (an object of an empty tag type, [[default.sentinel]]), it lets the `N` elements starting at some position be passed to generic algorithms. ¶2 is the standard's example, the same as the `ranges::copy` above.

```cpp
template<input_or_output_iterator I>
class counted_iterator {
public:
  using iterator_type = I;
  using value_type = iter_value_t<I>;     // only if I is readable
  using difference_type = iter_difference_t<I>;
  using iterator_concept = I::iterator_concept;   // only if present
  using iterator_category = I::iterator_category; // only if present
  // ...
private:
  I current = I();                    // exposition only
  iter_difference_t<I> length = 0;    // exposition only
};
```

`iterator_concept` and `iterator_category` are taken directly from the members of `I` with the same names, so the underlying traversal category is kept unchanged, contiguous iterators being no exception. The synopsis also provides a specialization of `iterator_traits<counted_iterator<I>>` that inherits all members of `iterator_traits<I>`, changing only `pointer` to `add_pointer_t<iter_reference_t<I>>` when contiguous and `void` otherwise. This specialization is enabled only when `iterator_traits` for `I` has been specialized.

### Referring to the same sequence (¶3)

Comparison and subtraction look only at the count, not at the underlying iterators. That requires both counted iterators to describe the same range; ¶3 gives the precise definition:

!!! std
    Two values i1 and i2 of types counted_iterator<I1> and counted_iterator<I2> refer to elements of the same sequence if and only if there exists some integer n such that next(i1.base(), i1.count() + n) and next(i2.base(), i2.count() + n) refer to the same (possibly past-the-end) element.

In other words, when each iterator walks to the position where its count reaches zero, those two positions must line up (alignment after both walk another `n` steps is allowed). `counted_iterator(v.begin(), 3)` and `counted_iterator(v.begin() + 1, 2)` refer to the same sequence; both end at `v.begin() + 3`. `counted_iterator(v.begin(), 3)` and `counted_iterator(v.begin(), 5)` do not, and comparing them violates a precondition, which is UB.

## Construction and access

[counted.iter.const] ¶1–¶2 `counted_iterator(I i, iter_difference_t<I> n)` has the hardened precondition `n >= 0`. **Hardened precondition** is C++26 terminology: in a hardened implementation the function checks it with a terminating semantic before any other side effect, and a violation terminates the program; in a non-hardened implementation a violation is still {{ub}} ([[structure.specifications#3.5]]). ¶3–¶5 allow conversion and assignment from `counted_iterator<I2>`.

[counted.iter.access] `base()` returns the underlying iterator; `count()` returns `length` and is `noexcept`.

[counted.iter.elem] Element access:

- ¶1–¶2 `*it` returns `*current`, with the hardened precondition `length > 0`;
- ¶3 `operator->` is provided only when `I` is a contiguous iterator, and returns `to_address(current)`;
- ¶4–¶5 `it[n]` returns `current[n]`, with the hardened precondition `n < length`.

## Moving the position [counted.iter.nav]

| Operation | Effect | Hardened precondition |
|---|---|---|
| `++it` | `++current; --length;` | `length > 0` (¶1) |
| `it++` (non-forward) | see below | `length > 0` (¶3) |
| `it++` (forward) | `= default` | |
| `--it` | `--current; ++length;` (requires bidirectional) | |
| `it + n`, `n + it` | `counted_iterator(current + n, length - n)` | |
| `it += n` | `current += n; length -= n;` | `n <= length` (¶8) |
| `it - n` | `counted_iterator(current - n, length + n)` | |
| `it -= n` | `current -= n; length += n;` | `-n <= length` (¶15) |

¶4 Postfix `++` for non-forward iterators is equivalent to:

```cpp
--length;
try { return current++; }
catch(...) { ++length; throw; }
```

If the underlying postfix `++` throws, the count is restored. The return type is `decltype(auto)`: whatever the underlying postfix `++` returns is returned, possibly `void`. For forward iterators, postfix `++` and `--` are declared `= default`, which copies, does the prefix increment or decrement, and returns the copy ([[over.inc.default]]).

## Comparison and distance

All comparisons and distance operations use only the count:

| Expression | Result | Precondition |
|---|---|---|
| `x - y` | `y.length - x.length` | same sequence ([counted.iter.nav] ¶11–¶12) |
| `x - default_sentinel` | `-x.length` | |
| `default_sentinel - y` | `y.length` | |
| `x == y` | `x.length == y.length` | same sequence ([counted.iter.cmp] ¶1–¶2) |
| `x == default_sentinel` | `x.length == 0` | |
| `x <=> y` | `y.length <=> x.length` | same sequence (¶4–¶5) |

[counted.iter.cmp] ¶6 Note 1 explains why the argument order in `<=>` is reversed: `length` gets smaller the further along you are. When comparing two `counted_iterator`s, the underlying types may differ (`template<common_with<I> I2>`), for example `vector<int>::iterator` and `vector<int>::const_iterator`.

Because the distance is the count, `counted_iterator<I>` and `default_sentinel_t` always model `sized_sentinel_for` ([[iterator.concept.sizedsentinel]]). So `ranges::advance(it, n, default_sentinel)` can compute directly how many steps it can take at most.

[counted.iter.cust] ¶1–¶4 `iter_move` and `iter_swap` forward to the underlying iterator, with the hardened precondition that the relevant counts are greater than 0.

## Pitfall: combined with istream_iterator, it reads one too many

```cpp run title="counted_istream.cpp" ok
#include <algorithm>
#include <cstdio>
#include <iterator>
#include <sstream>
#include <vector>

int main() {
  std::istringstream in("1 2 3 4 5");
  std::vector<int> out;
  std::ranges::copy(
      std::counted_iterator(std::istream_iterator<int>(in), 2),
      std::default_sentinel, std::back_inserter(out));
  int next;
  in >> next;
  std::printf("copied %zu, next = %d\n", out.size(), next);
}
```

In our tests this prints `copied 2, next = 4`. Only 2 elements were taken, yet the `3` in the stream has already been read.

`istream_iterator` reads the first element on construction and the next one on every `++` ([[istream.iterator]]). After handling the 2nd element, `ranges::copy` does one more `++` on the `counted_iterator`, which takes the count from 1 to 0 so that it equals `default_sentinel`. That `++` also advances the underlying iterator, which reads the `3`.

`views::take` and `views::counted` show the same behavior on input streams. If the stream comes from a terminal, the extra read also blocks waiting for user input. When you need exact control over how many items are read, write the loop by hand.

## Questions

!!! question "Question 1"
    Why doesn't `counted_iterator` also compare `current` when comparing?

<details markdown="1">
<summary>Answer</summary>

Given that both refer to the same sequence, the counts are equal exactly when the positions are equal. Comparing only the counts is both correct and cheap, and it also works when the underlying iterators cannot be compared for equality: C++20 input iterators need not support `==`. The price is that comparing counted iterators over different sequences violates a precondition and is UB.
</details>

!!! question "Question 2"
    `counted_iterator<int*>` is a contiguous iterator. How does `std::to_address` get a pointer from it?

<details markdown="1">
<summary>Answer</summary>

For a class type, `to_address` first looks for `pointer_traits<counted_iterator<int*>>::to_address`, which does not exist here; so it calls `it.operator->()`. `counted_iterator` provides `operator->` exactly when the underlying iterator is contiguous, returning `to_address(current)` ([counted.iter.elem] ¶3).
</details>
