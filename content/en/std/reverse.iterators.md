---
title: Reverse iterators
summary: "reverse_iterator internally stores the position one past its logical position, which leads to base() being off by one, reversed comparisons, and dangling references for iterators that store their elements inside themselves."
updated: 2026-10-19
---

!!! tldr
    - The `current` stored inside a `reverse_iterator` is one position past the element it logically refers to; dereferencing copies it and applies `--` first, so `*r` equals `*prev(r.base())`.
    - To erase an element through a reverse iterator, write `v.erase(std::next(rit).base())`; `v.erase(rit.base())` erases the element after it.
    - It is at most a random access iterator, never a contiguous one; operations like `+=` and `[]` require random access from the underlying iterator only when they are actually used.
    - All comparisons are reversed: `x < y` is `x.base() > y.base()`, and `x - y` is `y.base() - x.base()`.
    - It relies on the underlying iterator's references not referring into the iterator itself; wrapped around an iterator that stores the current value inside itself, dereferencing gives a dangling reference.

```cpp run title="reverse_base.cpp" ok
#include <algorithm>
#include <cassert>
#include <iterator>
#include <vector>

int main() {
    std::vector<int> v{1, 2, 3, 4, 5};
    auto rit = std::find(v.rbegin(), v.rend(), 3);
    assert(*rit == 3);
    assert(*rit.base() == 4);            // base() points to the element after the logical position

    // erase the element rit refers to: advance one step first, then take base()
    v.erase(std::next(rit).base());      // erases 3
    assert((v == std::vector{1, 2, 4, 5}));

    static_assert(std::random_access_iterator<std::reverse_iterator<int*>>);
    static_assert(!std::contiguous_iterator<std::reverse_iterator<int*>>);
}
```

¶1 [reverse.iterators.general]: `reverse_iterator` is an iterator adaptor that iterates from the end of the sequence defined by its underlying iterator to the beginning of that sequence. The containers' `rbegin()` and `rend()`, `std::rbegin` ([[iterator.range]]) and `views::reverse` are all built on it.

## Why the offset by one

When traversing `[begin, end)` in reverse, the start is the last element and the end is the position before the first element. But the position before the first element does not exist: for an array, computing a pointer before the first element is undefined behavior ([[expr.add]]).

`reverse_iterator`'s solution is to store a `current` one position past the logical position:

```text
                rend()                       rbegin()
                  ↓                             ↓
  logical:     (before e0)  e0    e1    e2    e3
  current:                 begin                    end
```

- `current` of `rbegin()` is `end()`, logically referring to `e3`;
- `current` of `rend()` is `begin()`, logically referring to before `e0`, which is a valid, comparable position;
- dereferencing is as if by `Iterator tmp = current; return *--tmp;` ([[reverse.iter.elem#1]]).

The whole class is written around this offset: `operator++` is `--current`, `operator+(n)` returns `reverse_iterator(current - n)`, and `operator[](n)` returns `current[-n - 1]`. `base()` returns `current` directly, so it is one position past the logical position. `&*rit == &*(rit.base() - 1)` always holds.

## The class definition [reverse.iterator]

```cpp
template<class Iterator>
class reverse_iterator {
public:
  using iterator_type     = Iterator;
  using iterator_concept  = see below;
  using iterator_category = see below;
  using value_type        = iter_value_t<Iterator>;
  using difference_type   = iter_difference_t<Iterator>;
  using pointer           = iterator_traits<Iterator>::pointer;
  using reference         = iter_reference_t<Iterator>;
  // construction, base(), *, ->, ++, --, +, +=, -, -=, [], iter_move, iter_swap
protected:
  Iterator current;
};
```

¶1 If the underlying iterator models `random_access_iterator`, `iterator_concept` is `random_access_iterator_tag`; otherwise it is `bidirectional_iterator_tag`. It is never `contiguous_iterator_tag`: in reverse traversal element addresses decrease, which violates the contiguous iterator requirement `to_address(b) == to_address(a) + (b - a)` ([[iterator.concept.contiguous]]). So `std::span<int>(v.rbegin(), v.rend())` does not compile.

¶2 If the underlying `iterator_category` derives from `random_access_iterator_tag`, `iterator_category` is `random_access_iterator_tag`, i.e. `contiguous_iterator_tag` is lowered one level; otherwise the underlying tag is copied.

`current` is an ordinary protected data member, not an exposition-only one. Derived classes can access it directly; it is a public interface kept from C++98.

## Requirements on the underlying iterator [reverse.iter.requirements]

¶1 `Iterator` must meet *Cpp17BidirectionalIterator* or model `bidirectional_iterator`.

¶2 If the definitions of the members `+`, `-`, `+=`, `-=` and `[]`, or of the non-members `<`, `>`, `<=`, `>=`, `-` and `+`, are instantiated, `Iterator` must additionally meet *Cpp17RandomAccessIterator* or model `random_access_iterator`.

The definitions of member functions of a class template are instantiated only when used ([[temp.inst]]), so `reverse_iterator<std::list<int>::iterator>` is a valid type as long as `+=` is not called. This is the C++98 approach, at the cost of these members always appearing to exist as far as declarations go:

```cpp run ok
#include <iterator>
#include <list>

using R = std::reverse_iterator<std::list<int>::iterator>;
static_assert(requires(R r) { r += 1; });         // the declaration exists, so the check passes
static_assert(!std::random_access_iterator<R>);   // but iterator_concept gives the right answer

int main() {}
```

The adaptors added after C++20 use `requires` clauses instead, so the members exist only when the underlying iterator supports them.

## Construction and conversion [reverse.iter.cons] [reverse.iter.conv]

- ¶1 Default construction value-initializes `current`.
- ¶2 `explicit reverse_iterator(Iterator x)` initializes `current` with `x`. It is explicit, so an ordinary iterator is never silently reversed.
- ¶3–¶7 Converting construction and converting assignment from `reverse_iterator<U>` are available when `U` differs from `Iterator` and `const U&` is convertible to `Iterator`; assignment also requires `assignable_from<Iterator&, const U&>`. So `reverse_iterator<iterator>` converts to `reverse_iterator<const_iterator>`.
- `base()` returns `current` ([[reverse.iter.conv#1]]).

## Element access and navigation [reverse.iter.elem] [reverse.iter.nav]

¶2 `operator->` is provided only when `Iterator` is a pointer or `i.operator->()` is valid: for a pointer it returns `prev(current)`, otherwise `prev(current).operator->()`. ¶3 `operator[](n)` returns `current[-n - 1]`, with an unspecified return type.

The twelve paragraphs of [reverse.iter.nav] reverse every direction: `++` is `--current`, `--` is `++current`, `+ n` is `current - n`, `+= n` is `current -= n`, and so on.

## Comparisons [reverse.iter.cmp]

| Expression | Result |
|---|---|
| `x == y`, `x != y` | `x.base() == y.base()`, `x.base() != y.base()` |
| `x < y` | `x.base() > y.base()` |
| `x > y` | `x.base() < y.base()` |
| `x <= y` | `x.base() >= y.base()` |
| `x >= y` | `x.base() <= y.base()` |
| `x <=> y` | `y.base() <=> x.base()` |

¶13–¶14 `<=>` swaps the order of its arguments, which Note 1 explains is because it is a reverse iterator. The first six operators are all constrained: the corresponding `base()` expression must be well-formed and convertible to `bool`, so concept checks get accurate results.

## Non-member functions [reverse.iter.nonmember]

- ¶1 `x - y` returns `y.base() - x.base()`; note the order. ¶2 `n + x` returns `reverse_iterator(x.base() - n)`.
- ¶3–¶4 `iter_move(i)` is equivalent to `auto tmp = i.base(); return ranges::iter_move(--tmp);`. It is `noexcept` if copying the underlying iterator and `iter_move` on it do not throw.
- ¶5–¶6 `iter_swap(x, y)` copies each `base()`, decrements each, and then calls `ranges::iter_swap`.
- ¶7 `make_reverse_iterator(i)` returns `reverse_iterator<Iterator>(i)`.

`operator-` is constrained only through its return type `decltype(y.base() - x.base())`. It exists whenever the underlying iterator has subtraction, whether or not that subtraction is constant time. That is why [[iterator.synopsis]] specializes `disable_sized_sentinel_for<reverse_iterator<I1>, reverse_iterator<I2>>` to be `true` when `I2` and `I1` do not model `sized_sentinel_for`, making the answer follow the underlying iterators ([[iterator.concept.sizedsentinel]]).

## Iterators that store their elements inside themselves

```cpp run title="reverse_stash.cpp" ub
#include <cstdio>
#include <iterator>

// the current value is stored in the iterator itself, and *it returns a reference to the member
struct Counter {
    using value_type = int;
    using difference_type = std::ptrdiff_t;
    int cur = 0;
    const int& operator*() const { return cur; }
    Counter& operator++() { ++cur; return *this; }
    Counter operator++(int) { auto t = *this; ++cur; return t; }
    Counter& operator--() { --cur; return *this; }
    Counter operator--(int) { auto t = *this; --cur; return t; }
    bool operator==(const Counter&) const = default;
};
static_assert(std::bidirectional_iterator<Counter>);   // satisfied, but not modeled

int main() {
    std::reverse_iterator<Counter> r(Counter{3});
    const int& x = *r;        // tmp in operator* is a local variable, and the reference refers to it
    std::printf("%d\n", x);   // UB: dangling reference
}
```

`Counter` passes all the syntactic checks of `bidirectional_iterator`, but violates the semantic requirement of forward iterators that references obtained from an iterator remain valid while the range is valid ([[iterator.concept.forward#3]]). Such an iterator can only count as an input iterator ([[iterator.requirements.general#15]]).

`reverse_iterator::operator*` relies on exactly this requirement: it dereferences the local copy `tmp`, and the returned reference must refer to something other than `tmp`. Running the example with `-fsanitize=address -fsanitize-address-use-after-return=always` in our tests, AddressSanitizer reports stack-use-after-return.

!!! history "A former patch"
    The resolution of [[LWG198]] once added, in C++11, an exposition-only member `deref_tmp` to `reverse_iterator`, so that `operator*` stored the decremented iterator in the member before dereferencing, to support such iterators. But that made `reverse_iterator` itself an iterator storing its element inside itself, with references invalidated together with the adaptor object; and a const `operator*` modifying a member causes data races when read from multiple threads. [[LWG2204]] reverted the change in C++14, going back to copying into a local variable and dereferencing that.

## Questions

!!! question "Question 1"
    Why is the return type of `operator[]` unspecified rather than `reference`?

<details markdown="1">
<summary>Answer</summary>

The type of `current[-n - 1]` is determined by the underlying iterator. For *Cpp17RandomAccessIterator*, `a[n]` is only required to be convertible to `reference`, and may be a proxy object. Specifying `reference` as the return type would force a conversion, which could produce a dangling reference for proxy iterators. An unspecified return type allows implementations to return the result of `current[-n - 1]` directly.
</details>

!!! question "Question 2"
    How does `reverse_iterator<reverse_iterator<I>>` relate to `I`? Why don't you get such a type when applying `views::reverse` to a `reverse_view` again?

<details markdown="1">
<summary>Answer</summary>

Two reversals cancel out in behavior, giving the same result as `I`, but with a more complicated type, and each dereference does an extra copy and an extra decrement. So `views::reverse` special-cases `reverse_view`, and `subrange`s made of `reverse_iterator`s, retrieving the underlying range directly ([[range.reverse.overview]]).
</details>
