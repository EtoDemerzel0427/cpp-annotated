---
title: common_iterator
summary: "common_iterator<I, S> holds either an iterator or a sentinel, turning a range whose begin and end have different types into one where they match, so it can be passed to older interfaces that take an iterator pair."
updated: 2026-10-19
---

!!! tldr
    - Inside, `common_iterator<I, S>` is a `variant<I, S>`: it holds either an iterator or a sentinel. Using this type for both ends lets the range be passed to older interfaces that require `first` and `last` to have the same type.
    - It is at most a forward iterator and does not support `--` or `+=`.
    - Two `common_iterator`s that both hold a sentinel always compare equal.
    - `operator->` and postfix `++` use exposition-only proxy classes so that it meets the C++17 input iterator requirements.
    - Dereferencing or incrementing one in the sentinel state violates a hardened precondition, which terminates the program in a hardened implementation.

## The problem: begin and end of different types

C++20 ranges allow the end to be an object of a different type, called a **sentinel**: it only needs to be equality-comparable with the iterator ([[iterator.concept.sentinel]]). For example, `counted_iterator` paired with `default_sentinel_t` means "stop after n elements" ([[iterators.counted]]).

But many existing interfaces require begin and end to have the same type: containers' iterator-pair constructors, the older algorithms in namespace `std::`, users' own templates. `common_iterator` is the adaptor that connects the two sides:

```cpp run title="common_iterator.cpp" ok
#include <cassert>
#include <iterator>
#include <list>
#include <ranges>
#include <vector>

int main() {
  std::list<int> l{1, 2, 3, 4, 5, 6};
  using CI = std::common_iterator<
      std::counted_iterator<std::list<int>::iterator>,
      std::default_sentinel_t>;
  // vector's iterator-pair constructor requires both ends to have the same type
  std::vector<int> v(CI(std::counted_iterator(l.begin(), 3)),
                     CI(std::default_sentinel));
  assert((v == std::vector{1, 2, 3}));

  static_assert(std::forward_iterator<CI>);
  static_assert(!std::bidirectional_iterator<CI>);

  // views::common does the same thing automatically
  auto r = std::views::counted(l.begin(), 4) | std::views::common;
  std::vector<int> w(r.begin(), r.end());
  assert(w.size() == 4);
}
```

For non-random-access iterators, `views::counted` produces `subrange<counted_iterator<...>, default_sentinel_t>`, whose begin and end types differ. `views::common` ([[range.common]]) wraps it in a `common_view`, whose `begin()` and `end()` both return `common_iterator`.

## Definition [common.iterator]

¶1 `common_iterator` is an iterator/sentinel adaptor that can represent a **non-common range** (begin and end of different types) as a **common range** (begin and end of the same type). It does so by holding either an iterator or a sentinel and defining equality comparison accordingly. ¶2 Note 1 says it is useful for interfacing with legacy code that expects begin and end to have the same type.

```cpp
template<input_or_output_iterator I, sentinel_for<I> S>
  requires (!same_as<I, S> && copyable<I>)
class common_iterator {
  // ...
private:
  variant<I, S> v_;   // exposition only
};
```

The constraint `!same_as<I, S>` is there because it is not needed when begin and end already have the same type. The constraint `copyable<I>` is there because older interfaces require copyable iterators, and a move-only iterator cannot be turned into a copyable one. Index 0 of `v_` means it holds the iterator, index 1 that it holds the sentinel ([[variant]]).

## Associated types [common.iter.types]

`iter_difference_t<common_iterator<I, S>>` is just `iter_difference_t<I>`. When `I` is an input iterator, the standard specializes `iterator_traits<common_iterator<I, S>>`:

- ¶2.1 `iterator_concept`: `forward_iterator_tag` when `I` models `forward_iterator`, `input_iterator_tag` otherwise. The sentinel state can neither go back nor do arithmetic, so it tops out at forward.
- ¶1 `iterator_category`: declared only when `iter_difference_t<I>` is an integral type. It is `forward_iterator_tag` when `I`'s category derives from `forward_iterator_tag`, and `input_iterator_tag` otherwise.
- ¶2.2 `pointer`: the type of `a.operator->()` if that is well-formed, `void` otherwise.

`iterator_category` is meant for C++17 interfaces, and *Cpp17Iterator* requires `difference_type` to be a signed integer type ([[iterator.iterators]]). When the difference type is an integer-class type (as with some `iota_view` iterators), the iterator does not meet the C++17 requirements, and declaring a category would be a false claim.

## Construction, access and increment

[common.iter.const] ¶1–¶2 construct from `I` or `S`, placing it in alternative 0 or 1 of the `variant` respectively. Neither constructor is explicit, so an `S` can be passed directly to a parameter that takes a `common_iterator`. ¶3–¶6 convert or assign from `common_iterator<I2, S2>`, constructing or assigning the same alternative that the other object currently holds.

[common.iter.access] ¶1–¶2 `operator*` returns `*get<I>(v_)`, with the hardened precondition `holds_alternative<I>(v_)`. **Hardened precondition** is C++26 terminology: violating one in a hardened implementation reports a contract violation with a terminating semantic, and is still UB in other implementations ([[structure.specifications]]).

¶3–¶5 `operator->` has three implementations depending on the underlying iterator:

1. `I` is a pointer or has `operator->`: return `get<I>(v_)` itself, so the `->` chain continues;
2. `iter_reference_t<I>` is a reference type: return the address of `*get<I>(v_)`;
3. otherwise return an exposition-only *`proxy`* object. It stores the value of `*it` in its member `keep_`, and its `operator->` returns the address of `keep_`. That is how an iterator whose dereference returns elements by value gets an object whose address can be taken.

[common.iter.nav] ¶1–¶3 prefix `++` does `++get<I>(v_)`. ¶4–¶5 postfix `++` returns a copy from before the increment for forward iterators. For single-pass input iterators, if `*i++` itself yields a reference, or the value type cannot be constructed from the reference or cannot be move-constructed, it simply returns `get<I>(v_)++`; otherwise it returns an exposition-only *`postfix-proxy`*, which saves the current element's value before incrementing.

Postfix `++` is this elaborate so that `*it++` works. *Cpp17InputIterator* requires this expression ([[input.iterators]]), while a C++20 input iterator's postfix `++` may return `void`. Only with *`postfix-proxy`* can a `common_iterator` really be handed to C++17 interfaces.

`iter_move` and `iter_swap` in [common.iter.cust] forward to the underlying iterator, with the hardened precondition that it holds the iterator.

## Comparison [common.iter.cmp]

`operator==` has two overloads, distinguished by whether `I` and the other side's `I2` can be compared for equality:

| Case | Both iterators | One iterator, one sentinel | Both sentinels |
|---|---|---|---|
| `I`, `I2` not comparable (¶2) | `true` | iterator `==` sentinel | `true` |
| `I`, `I2` comparable (¶4) | iterator `==` iterator | iterator `==` sentinel | `true` |

The rule in ¶2: if both sides have the same index, return `true`; otherwise compare the objects the two sides actually hold. Two iterators always being equal in the first row looks strange, but C++20 input iterators need not support `==` at all. An older interface using `common_iterator` only ever compares the current position with the end, never two objects that both hold iterators, so whatever is returned does not affect the result. Two sentinels both denote the end, so equality is reasonable too.

¶6 `operator-` returns 0 when both sides are sentinels, and otherwise subtracts the objects actually held, requiring the corresponding `sized_sentinel_for` to hold. ¶1, ¶3 and ¶5 require neither side of a comparison or subtraction to be valueless; this is also a hardened precondition.

!!! impl "libc++"
    libc++ implements these hardened preconditions as assertions. In our tests, compiled with `-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_FAST`, dereferencing a `common_iterator` that holds a sentinel traps at the assertion and terminates; without hardening the same program ends with a segmentation fault.

## Common misconceptions

!!! pitfall "`common_iterator` keeps the underlying category"
    It tops out at forward. Older algorithms that need random access, such as `std::sort`, cannot get random access through `common_iterator`. If the range is random access and its end is a sized sentinel, a better approach is to compute the end iterator directly with `ranges::next(first, last)`.

!!! pitfall "Any iterator can be wrapped this way"
    The constraint `copyable<I>` rejects move-only iterators outright. Such C++20 input iterators cannot be plugged into older interfaces that require copyable iterators, which is why `views::common` is unavailable for some views.

## Questions

!!! question "Question"
    Two `common_iterator`s both hold sentinels, but the sentinels have different values (for example, two sentinels with different predicates). What does `==` return? Is that a reasonable rule?

<details markdown="1">
<summary>Answer</summary>

It returns `true`, because both sides have index 1 (¶2, ¶4). When `common_iterator` is used, the sentinel state appears only on the end side, and a range has only one end, so two ends comparing equal is reasonable. The standard could not compare the sentinels themselves anyway: `sentinel_for` only requires a sentinel to be comparable with an iterator, not with other sentinels.
</details>
