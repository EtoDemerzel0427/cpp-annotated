---
title: Iterator adaptors and two sentinels
summary: "What problem each of the standard library's six kinds of iterator adaptors solves, and the two empty sentinel types default_sentinel_t and unreachable_sentinel_t."
updated: 2026-10-19
---

!!! tldr
    - An iterator adaptor wraps an underlying iterator or container and changes only one aspect of it: direction, insertion, constness, moving, type unification or counting.
    - `default_sentinel_t` is an empty type used with iterators that know where their own end is; the comparison logic is provided by the iterator.
    - `unreachable_sentinel_t` compares unequal to every `weakly_incrementable` type and represents an interval with no upper bound, such as `views::iota(0)`.
    - When searching with `unreachable_sentinel`, it becomes the caller's responsibility that the target exists; if it is not found, the search runs out of bounds and the behavior is undefined.

```cpp run title="sentinels.cpp" ok
#include <algorithm>
#include <cassert>
#include <iterator>
#include <list>
#include <ranges>
#include <vector>

int main() {
    // unreachable_sentinel: the target is known to exist, so the bounds check is skipped
    const char buf[] = "key=value";
    auto eq = std::ranges::find(buf + 0, std::unreachable_sentinel, '=');
    assert(eq - buf == 3);

    // default_sentinel: counted_iterator itself knows where the end is
    std::list<int> l{1, 2, 3, 4, 5};
    std::vector<int> out;
    std::ranges::copy(std::counted_iterator(l.begin(), 3), std::default_sentinel,
                      std::back_inserter(out));
    assert((out == std::vector{1, 2, 3}));

    // unbounded iota: iota_view<int, unreachable_sentinel_t>
    static_assert(std::same_as<decltype(std::views::iota(0)),
                               std::ranges::iota_view<int, std::unreachable_sentinel_t>>);
    auto first_big = *std::ranges::find_if(std::views::iota(1),
                                           [](int i) { return i * i > 50; });
    assert(first_big == 8);
}
```

The title of [predef.iterators] is Iterator adaptors. An **iterator adaptor** wraps an underlying iterator (an insert iterator wraps a container) and changes one aspect of its behavior, keeping the rest as unchanged as possible.

| Subclause | Adaptor | What it changes |
|---|---|---|
| [[reverse.iterators]] | `reverse_iterator` | The direction of traversal |
| [[insert.iterators]] | `back_insert_iterator` and friends | Assignment becomes insertion into a container |
| [[const.iterators]] | `basic_const_iterator` | The result of dereferencing becomes constant |
| [[move.iterators]] | `move_iterator`, `move_sentinel` | The result of dereferencing becomes an rvalue |
| [[iterators.common]] | `common_iterator` | Unifies an iterator and a sentinel of a different type into one type |
| [[iterators.counted]] | `counted_iterator` | Carries a count of the elements remaining |

`reverse_iterator` and the insert iterators date back to C++98, `move_iterator` comes from C++11, `common_iterator`, `counted_iterator`, `move_sentinel` and the two sentinels arrived with the C++20 ranges library, and `basic_const_iterator` is new in C++23.

These adaptors share several practices:

- `base()` retrieves the underlying iterator. `move_iterator` and the adaptors newer than C++20 provide two overloads, `const&` and `&&`, the latter moving the underlying iterator out, for the sake of move-only iterators.
- They provide `iter_move` and `iter_swap` as hidden friends, forwarding customizations to the underlying iterator ([[iterator.cust]]).
- They provide an operation only when the underlying iterator supports it; the newer adaptors express this with `requires` clauses, while old adaptors like `reverse_iterator` rely on members being instantiated only when used (see [[reverse.iterators]]).
- `reverse_iterator` and `move_iterator` declare both `iterator_category` and `iterator_concept`, for C++17 interfaces ([[iterator.cpp17]]) and C++20 concepts ([[iterator.concepts]]) respectively.

## `default_sentinel_t` [default.sentinel]

```cpp
struct default_sentinel_t { };
inline constexpr default_sentinel_t default_sentinel{};   // declared in the <iterator> synopsis
```

¶1 `default_sentinel_t` is an empty type used to denote the end of a range, together with iterators that know the bounds of their range, such as `counted_iterator` ([[counted.iterator]]).

It has no comparison operators of its own; the comparison logic is provided by each iterator in the form `operator==(const It&, default_sentinel_t)`:

- a `counted_iterator` equals `default_sentinel` when its count is 0;
- `istream_iterator` and `istreambuf_iterator` equal `default_sentinel` when they reach the end of the stream, and an end-of-stream iterator can be constructed from it ([[stream.iterators]]);
- the iterators of `views::lazy_split`, `std::generator` and others use it as the type of `end()`.

When the end information is held entirely inside the iterator, the sentinel needs no state, and an empty type suffices. The notation `[it, default_sentinel)` also states directly that the iterator decides where the end is. Conversely, `vector<int>::iterator` does not know its end, and pairing it with `default_sentinel` does not compile.

## `unreachable_sentinel_t` [unreachable.sentinel]

```cpp
struct unreachable_sentinel_t {
  template<weakly_incrementable I>
    friend constexpr bool operator==(unreachable_sentinel_t, const I&) noexcept
    { return false; }
};
inline constexpr unreachable_sentinel_t unreachable_sentinel{};   // declared in the <iterator> synopsis
```

¶1 It can be used with any `weakly_incrementable` type to denote the upper bound of an unbounded interval. Comparison always returns `false`; `!=` and the reversed-argument forms come automatically from C++20's rewriting rules for comparisons ([[over.match.oper]]).

The constraint is `weakly_incrementable`, not `input_or_output_iterator`, so it can also be compared with integers. The type of `views::iota(0)` is `iota_view<int, unreachable_sentinel_t>`, an endless sequence of integers.

¶2 Example 1 shows its use in algorithms: searching for a newline in a buffer known to contain one.

```cpp
char* nl = find(p, unreachable_sentinel, '\n');
```

If the newline really is there, this can make `find` faster, since each iteration no longer compares with the end and there is one conditional branch fewer. If there is no newline, `find` reads past the end of the buffer; calling a library function on an invalid range has undefined results ([[iterator.requirements.general#12]]). Searching for a delimiter this way in untrusted input is an out-of-bounds read vulnerability.

## Questions

!!! question "Question 1"
    Is `std::sized_sentinel_for<std::unreachable_sentinel_t, int*>` true? What happens with `std::ranges::distance(p, std::unreachable_sentinel)`?

<details markdown="1">
<summary>Answer</summary>

It is false; there is no `-` operation. So `ranges::distance` chooses the overload that increments one step at a time, whose precondition that `[first, last)` denotes a range can never be met; the call is undefined behavior and in practice keeps incrementing forever. Likewise, `views::iota(0)` is not a `sized_range`.
</details>

!!! question "Question 2"
    Why is `unreachable_sentinel_t::operator==` written as a hidden friend template rather than a member function?

<details markdown="1">
<summary>Answer</summary>

A hidden friend can only be found by ADL, so it enters overload resolution only when one of the arguments is an `unreachable_sentinel_t`, and adds no `==` candidates for other types. Nor is it an ordinary function template in namespace `std`, so after `using namespace std;` it does not appear in the `==` lookup results for arbitrary pairs of types. C++20's rewriting rules then derive the three forms `i == s`, `s != i` and `i != s` from this one declaration.
</details>
