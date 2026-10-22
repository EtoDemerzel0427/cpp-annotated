---
title: Iterator primitives
summary: "Iterator category tags and tag dispatch, std::advance, distance, next and prev, and their ranges:: versions, which dispatch on concepts and support sentinels."
updated: 2026-10-19
---

!!! tldr
    - The six category tags form an inheritance chain (with `output_iterator_tag` on its own), which C++98 uses together with overload resolution to choose an algorithm's implementation at compile time.
    - `std::advance`, `distance`, `next` and `prev` dispatch on `iterator_category`: negative steps work only with bidirectional iterators; `distance` on random access iterators may return a negative number.
    - `ranges::advance` has three forms: take `n` steps, go to a sentinel, or take at most `n` steps without passing the sentinel; the last returns the number of steps not taken.
    - The `ranges::` versions are algorithm function objects: ADL cannot find them, they switch ADL off when they are found, and explicit template arguments cannot be given.

`std::list`'s iterator has no `+`, and `std::forward_list`'s iterator has no `--`. [[iterator.requirements.general#14]] says each category of iterator provides only operations that can be done in constant time. But algorithms often need to take `n` steps or compute the distance between two iterators, and the tools in this subclause choose the fastest approach according to the iterator's capabilities.

¶1 [iterator.primitives.general] has a single sentence: to simplify the use of iterators, the library provides several classes and functions.

## Category tags [std.iterator.tags]

```cpp
struct output_iterator_tag { };
struct input_iterator_tag { };
struct forward_iterator_tag : public input_iterator_tag { };
struct bidirectional_iterator_tag : public forward_iterator_tag { };
struct random_access_iterator_tag : public bidirectional_iterator_tag { };
struct contiguous_iterator_tag : public random_access_iterator_tag { };
```

¶1 Function templates often need to know the most specific category of their iterator argument so as to select the most efficient algorithm at compile time. For that, the library provides these empty classes, called **category tags** ([[g:iterator-category-tag]]). For every iterator type `I`, `iterator_traits<I>::iterator_category` must be the tag describing its behavior; additionally, `iterator_traits<I>::iterator_concept` can indicate which C++20 concept it conforms to ([[iterator.concepts]]).

¶3 Example 2 shows how to dispatch on them, a technique called **tag dispatch**:

```cpp
template<class BidirectionalIterator>
void evolve(BidirectionalIterator first, BidirectionalIterator last) {
  evolve(first, last,
         typename iterator_traits<BidirectionalIterator>::iterator_category());
}
template<class BidirectionalIterator>
void evolve(BidirectionalIterator first, BidirectionalIterator last,
            bidirectional_iterator_tag);   // general but slower
template<class RandomAccessIterator>
void evolve(RandomAccessIterator first, RandomAccessIterator last,
            random_access_iterator_tag);   // faster but requires more
```

This is where the inheritance chain does its work. Called with `random_access_iterator_tag`, the exactly matching overload wins; called with `contiguous_iterator_tag`, among derived-to-base conversions the conversion to the nearer base is better ([[over.ics.rank]]), so the random access version is still chosen; called with `forward_iterator_tag`, neither is viable. `output_iterator_tag` is not on the chain, because output and input are two capabilities, neither of which includes the other.

¶2 Example 1 shows the C++98-style way of declaring a category: specialize `iterator_traits` for your own `BinaryTreeIterator<T>`, setting `iterator_category` to `bidirectional_iterator_tag`.

Since C++20, the same dispatch is more often written as `if constexpr (std::random_access_iterator<I>)` or as constrained overloads, with subsumption between concepts ([[temp.constr.order]]) replacing inheritance between tags. `contiguous_iterator_tag` was added only in C++20; the `iterator_category` of pointers is still `random_access_iterator_tag` ([[iterator.traits]]), so this tag appears mainly in `iterator_concept`.

## `std::advance`, `distance`, `next`, `prev` [iterator.operations]

¶1 Only random access iterators provide `+` and `-`, so the library provides `advance` and `distance`: for random access iterators they use `+` and `-` in constant time; for other iterators they apply `++` repeatedly, in linear time. All four functions are `constexpr`.

`advance(i, n)` modifies `i` by reference and returns `void`; the step type `Distance` is a separate template parameter. ¶2 The precondition is that `n` may be negative only for bidirectional iterators. ¶3 If `n` is non-negative, it increments `n` times, otherwise it decrements `-n` times.

The precondition of `distance(first, last)` deserves attention:

!!! std
    *Preconditions*: last is reachable from first, or InputIterator meets the *Cpp17RandomAccessIterator* requirements and first is reachable from last.

¶4–¶5 For random access iterators it returns `last - first`, so swapping the beginning and end is fine and gives a negative result. For other iterators it increments from `first` until it equals `last` and returns the number of increments; swapping the beginning and end is then undefined behavior.

¶6 `next(x, n)` is equivalent to `advance(x, n); return x;`. ¶7 `prev(x, n)` is equivalent to `advance(x, -n); return x;`. The template parameter of `prev` is named `BidirectionalIterator`, so it requires a bidirectional iterator even when `n` is negative and it actually moves forward.

These four functions work by the *Cpp17* requirements and `iterator_category`. The iterators of many C++20 views declare themselves only input iterators here, so `std::distance` can only count one by one and `std::prev` violates its precondition outright; see the example in [[iterator.cpp17]].

## The `ranges::` versions [range.iter.ops]

```cpp run title="primitives.cpp" ok
#include <cassert>
#include <iterator>
#include <list>
#include <ranges>

int main() {
    int a[5]{};
    int* p = a;
    // wanted 10 steps, took only 5; returns the 5 not taken
    auto left = std::ranges::advance(p, 10, a + 5);
    assert(p == a + 5 && left == 5);

    assert(std::ranges::next(a, 3, a + 5) == a + 3);
    assert(std::ranges::distance(a) == 5);          // range form: sized_range
    assert(std::ranges::distance(a, a + 5) == 5);   // array argument decays to a pointer
    assert(std::distance(a + 5, a) == -5);          // random access: can be reversed

    std::list<int> l{1, 2, 3, 4};
    auto it = std::ranges::next(l.begin(), 2);      // bidirectional iterator: 2 ++s
    assert(*it == 3);
    assert(*std::ranges::prev(l.end()) == 4);

    // iterators of C++20 views: dispatched on concepts, they work fine
    auto io = std::views::iota(0, 10);
    assert(*std::ranges::prev(io.end()) == 9);
}
```

¶1 [range.iter.ops.general] explains that these four functions choose the most efficient implementation according to the operators the iterator actually provides. Example 1: `ranges::advance` uses `+` to advance in constant time for a `random_access_iterator`, and applies `++` `n` times for other iterators. Compared with the `std::` versions, they determine the category by C++20 concepts and support sentinels.

### `ranges::advance` [range.iter.op.advance]

`advance(i, n)` takes `n` steps. ¶1 The precondition is that `n` is not negative if `I` is not a bidirectional iterator. ¶2 For random access it is equivalent to `i += n`; otherwise it increments or decrements step by step.

`advance(i, bound)` goes to the sentinel. ¶4 It chooses, in order:

1. if `I` is assignable from `S`, simply `i = std::move(bound)`;
2. otherwise, if `S` is a sized sentinel for `I`, `ranges::advance(i, bound - i)`;
3. otherwise, `++` one step at a time until `i == bound`.

¶3 The precondition is that one of the first two cases holds or `[i, bound)` denotes a range. In the first two cases a single assignment or a single subtraction puts `i` in the right place, relying on the semantic requirements of [[iterator.concept.sentinel]] and [[iterator.concept.sizedsentinel]].

`advance(i, n, bound)` takes at most `n` steps, stops on reaching `bound`, and returns the number of steps not taken:

- ¶5 Preconditions: if `n > 0`, `[i, bound)` denotes a range; if `n == 0`, `[i, bound)` or `[bound, i)` denotes a range; if `n < 0`, `[bound, i)` denotes a range, `I` is a bidirectional iterator, and `S` and `I` are the same type.
- ¶6 Effects: if `S` is a sized sentinel, it goes straight to `bound` when `|n| >= |bound - i|`, and otherwise takes `n` steps; if it is not a sized sentinel, it advances or retreats step by step, at most `|n|` steps, stopping at `bound`.
- ¶7 Returns `n - M`, where `M` is the signed distance `i` actually moved.

This is the standard tool for safely taking at most `n` steps. The `begin()` of `views::drop` is specified as `ranges::next(ranges::begin(base_), count_, ranges::end(base_))` ([[range.drop.view]]).

### `ranges::distance` [range.iter.op.distance]

There are three overloads:

- `distance(I first, S last)`, for when `S` is not a sized sentinel. ¶1 The precondition is that `[first, last)` denotes a range; ¶2 it counts by incrementing one step at a time.
- `distance(I&& first, S last)`, for when `S` is a sized sentinel for `decay_t<I>`. ¶3 It returns `last - first` directly; if `first` is an array, it is converted to a pointer first. The forwarding reference plus this special handling lets calls that use an array itself as the iterator, like `ranges::distance(arr, arr + 5)`, work too.
- `distance(R&& r)`. ¶4 If `R` is a `sized_range`, it returns `ranges::size(r)` converted to the difference type; otherwise `ranges::distance(ranges::begin(r), ranges::end(r))`.

The second overload has no reachability precondition; as long as the subtraction is defined, the result may be negative.

### `ranges::next`, `ranges::prev` [range.iter.op.next] [range.iter.op.prev]

`next(x)` is `++x; return x;`. `next(x, n)`, `next(x, bound)` and `next(x, n, bound)` call the corresponding `ranges::advance` on `x` and return `x`.

`prev(x)`, `prev(x, n)` and `prev(x, n, bound)` require `bidirectional_iterator` and are `--x`, `ranges::advance(x, -n)` and `ranges::advance(x, -n, bound)` respectively; in the bounded `prev`, the type of `bound` is `I` itself.

`ranges::next(x, n, bound)` returns only the iterator and discards the number of steps not taken; when you need that number, use `ranges::advance` directly.

## Algorithm function objects

¶2 Paragraph 2 of [range.iter.ops.general] is short but has a large impact:

!!! std
    The entities defined in [range.iter.ops] are algorithm function objects ([alg.func.obj]).

An **algorithm function object** is a kind of customization point object ([[customization.point.object]]): the standard describes it as a set of overloaded function templates, but it is actually an object. Note 1 of [[alg.func.obj]] points out two consequences:

- argument-dependent lookup (ADL, [[basic.lookup.argdep]]) cannot find them;
- when ordinary unqualified lookup finds them and they are used in a function call, ADL is not performed, because ADL happens only when ordinary lookup finds a function or finds nothing.

The community often calls such objects niebloids. The effect:

```cpp run title="niebloid.cpp" ok
#include <cassert>
#include <iterator>
#include <vector>

namespace user {
struct Widget { int v; };
template<class It> It next(It it) { return it; }   // a same-named template that accepts anything
}

int main() {
    std::vector<user::Widget> v(3);
    using namespace std::ranges;
    // unqualified lookup finds the object std::ranges::next; no ADL, so user::next does not take part
    auto it = next(v.begin());
    assert(it == v.begin() + 1);
}
```

Remove `using namespace std::ranges;` and write `next(v.begin())`, and ADL finds both `std::next` and `user::next`, in `std` (the associated namespace of the `vector` iterator) and in `user` (the associated namespace of the template argument `Widget`). Both are exact matches for this argument and partial ordering cannot rank them, so Clang 23 reports call to 'next' is ambiguous. Algorithm function objects avoid this kind of problem at the root.

Because they are objects, they can be passed directly as callables, for example to `views::transform`; `std::next` is an overload set and cannot be. Conversely, `std::ranges::next<int*>(p)` is ill-formed, since an object cannot take template arguments.

!!! impl "The libc++ implementation"
    libc++ defines `ranges::advance` as an `inline constexpr` object of struct `ranges::__advance`, placed in the inline namespace `__cpo`; each function template in the standard corresponds to an `operator()` overload of the struct. That objects are not found by ADL follows directly from the language rules; no extra trickery is needed.

## Common misconceptions

!!! pitfall "Using `std::prev` or a negative `std::advance` on forward iterators"
    The template parameter of `prev` requires a bidirectional iterator regardless of the sign of `n`; `std::advance(it, -1)` on a forward iterator violates the precondition. In our tests with libc++ and hardening enabled (for example `-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_DEBUG`), `std::advance(it, -1)` on a `forward_list` iterator reports an assertion failure and terminates.

!!! pitfall "Swapping the beginning and end for non-random-access iterators"
    `std::distance(l.end(), l.begin())` on a `std::list` is undefined behavior; the precondition is relaxed only for random access iterators. libc++'s linked list is circular, and in our tests this call quietly returned 1 with no warning at all. `ranges::distance` likewise requires `[first, last)` to denote a range in the non-sized case.

## Questions

!!! question "Question 1"
    The first case of `ranges::advance(i, bound)` is written `i = std::move(bound)`. Why is it fine to move from `bound`?

<details markdown="1">
<summary>Answer</summary>

The signature of this overload is `advance(I& i, S bound)`: the sentinel is passed by value, and the `bound` in the function is its own copy, so moving from it does not affect the caller. A sentinel may hold resources, such as a predicate object, and moving is cheaper than copying.
</details>

!!! question "Question 2"
    Why does the second overload of `ranges::distance` say `sized_sentinel_for<S, decay_t<I>>` instead of `sized_sentinel_for<S, I>`?

<details markdown="1">
<summary>Answer</summary>

`first` is a forwarding reference, so `I` may be deduced as `It&`, or as `int(&)[5]` when an array is passed. The concept needs the iterator type itself, hence `decay_t`; for an array, `decay_t` gives exactly the pointer type, matching the `static_cast<decay_t<I>>(first)` in ¶3.
</details>

!!! question "Question 3"
    When `S` is a sized sentinel, does `ranges::advance(i, n, bound)` still perform `++` one step at a time?

<details markdown="1">
<summary>Answer</summary>

It may. It first uses `bound - i` to decide how far to go, then calls `ranges::advance(i, bound)` or `ranges::advance(i, n)`. If `I` is a random access iterator, the latter is a single `+=`; but a sized sentinel does not require the iterator to be random access, as with `counted_iterator<std::list<int>::iterator>` paired with `default_sentinel_t`, in which case `ranges::advance(i, n)` still does `++` one step at a time. Still, the bounds check takes just one subtraction instead of comparing with `bound` at every step.
</details>
