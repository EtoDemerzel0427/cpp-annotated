---
title: C++17 iterator requirements
summary: "The six iterator requirements tables in use since C++98, kept since C++20 with a Cpp17 prefix, which still constrain std:: algorithms, container constructors and primitives such as std::advance."
updated: 2026-10-19
---

!!! tldr
    - *Cpp17Iterator* and the other five sets of requirements are prose specifications in table form that the compiler does not check; a type declares which level it belongs to through `iterator_traits<X>::iterator_category`.
    - They still constrain the non-`ranges::` algorithms, the iterator-pair constructors of containers, and `std::advance`, `std::distance`, `std::next` and `std::prev`.
    - Compared with the C++20 concepts, these requirements are stricter: every iterator must be copyable, input iterators must already be equality comparable, and the `reference` of a forward iterator must be a real reference.
    - So the iterators of many C++20 views count only as input iterators here. `std::prev(iota.end())` fails to compile outright on libc++; use `std::ranges::prev` instead.

C++98 described five kinds of iterators with a set of tables. When C++20 introduced iterator concepts ([[iterator.concepts]]), the old requirements were not removed; they were renamed with a Cpp17 prefix and gathered into this subclause. Requirements like these, written in tables and not checked by the compiler, are called **named requirements**.

The old requirements are still in use because many interfaces have always been based on them:

- non-`ranges::` algorithms express requirements through template parameter names: a parameter named `InputIterator` must meet *Cpp17InputIterator*, and so on ([[algorithms.requirements#4]]);
- the iterator-pair constructors of containers, as well as `insert` and `assign` ([[container.requirements]]);
- `std::advance`, `std::distance`, `std::next` and `std::prev` ([[iterator.operations]]);
- the template parameters of `reverse_iterator` and `move_iterator`, which accept types that meet the *Cpp17* requirements or model the corresponding concepts.

A type declares which level it meets through `iterator_traits<X>::iterator_category` ([[std.iterator.tags]]). Declaring a level without meeting it means instantiating a standard library template with a type that does not meet the requirements, which is undefined behavior ([[res.on.functions#2.3]]).

## C++20 iterators meet C++17 interfaces

```cpp run title="cpp17_vs_cpp20.cpp" ok
#include <cstdio>
#include <iterator>
#include <ranges>
#include <vector>

int main() {
    auto io = std::views::iota(0, 10);
    using It = decltype(io.begin());
    static_assert(std::random_access_iterator<It>);            // C++20: random access
    static_assert(std::same_as<std::iterator_traits<It>::iterator_category,
                               std::input_iterator_tag>);      // C++17: input

    // std::distance dispatches on iterator_category and can only ++ one step at a time
    std::printf("%td\n", std::distance(io.begin(), io.end()));
    // ranges::distance dispatches on concepts: a single subtraction
    std::printf("%td\n", std::ranges::distance(io.begin(), io.end()));

    // the iterator-pair constructor also looks only at iterator_category and cannot compute the length in advance
    std::vector<int> v(io.begin(), io.end());
    std::printf("%zu\n", v.size());
}
```

Dereferencing an `iota_view` iterator gives an `int` prvalue, not a reference. By the forward iterator requirements below, `reference` must be a real reference, so in the C++17 system it can only declare itself an input iterator, even though in C++20 it is a random access iterator.

`std::prev` requires *Cpp17BidirectionalIterator*, so the following code violates the requirements on the template argument, and the behavior is undefined. libc++ checks `iterator_category` with a `static_assert`, turning it into a compile error:

```cpp run title="prev_iota.cpp"
#include <iterator>
#include <ranges>

int main() {
    auto io = std::views::iota(0, 10);
    auto last = std::prev(io.end());   // UB: does not meet Cpp17BidirectionalIterator
    return *last;                      // libc++ reports a static_assert error before this
}
```

Using `std::ranges::prev(io.end())` instead is fine, since it decides by concepts.

## Notation [iterator.cpp17.general]

¶1 In the tables that follow, `a` and `b` are values of `X` or `const X`, `r` is a value of `X&`, `n` is a value of `difference_type`, `t` is a value of the value type `T`, and `o` is some value writable to the output iterator. `difference_type` and `reference` refer to the types of the same names in `iterator_traits<X>`. Note 1 reminds us that for an iterator type `X` there must be an instantiation of `iterator_traits<X>`; these requirements cannot do without `iterator_traits`.

## *Cpp17Iterator* [iterator.iterators]

¶1 The basic requirements met by all iterators. ¶2 `X` meets *Cpp17Iterator* if and only if:

1. it is copy constructible, copy assignable, swappable and destructible ([[utility.arg.requirements]], [[swappable.requirements]]);
2. `iterator_traits<X>::difference_type` is a signed integer type or `void`, `void` being reserved for output iterators;
3. the expressions of Table 78 are valid: the return type of `*r` is unspecified, provided `r` is dereferenceable; `++r` returns `X&`.

## *Cpp17InputIterator* [input.iterators]

¶1 `X` meets *Cpp17Iterator* and *Cpp17EqualityComparable*, and the expressions of Table 79 are valid:

| Expression | Requirements |
|---|---|
| `a != b` | Equivalent to `!(a == b)`; precondition: `(a, b)` is in the domain of `==` |
| `*a` | Returns `reference`, convertible to `T`; `(void)*a, *a` is equivalent to `*a`; if `a == b`, `*a` is equivalent to `*b` |
| `a->m` | Equivalent to `(*a).m` |
| `++r` | Afterwards `r` is dereferenceable or past-the-end; copies of the previous value of `r` are no longer required to be dereferenceable or to be in the domain of `==` |
| `(void)r++` | Equivalent to `(void)++r` |
| `*r++` | Convertible to `T`; equivalent to `{ T tmp = *r; ++r; return tmp; }` |

¶2 **The domain of `==`** has its mathematical meaning: the set of values for which `==` is required to be defined, and this set can change over time. Each algorithm places additional requirements on the domain according to how it uses `==` and `!=`. Example 1 uses `find(a, b, x)`: it requires that, starting at `a` and incrementing one step at a time, `b` can be reached before `*i == x` is encountered.

¶3 Recommended practice: algorithms on input iterators should be single-pass. Note 1 points out that `a == b` does not imply `++a == ++b`, and the value type is not required to be copy assignable, so that `istream_iterator` can serve as an algorithm's input.

## *Cpp17OutputIterator* [output.iterators]

¶1 Meets *Cpp17Iterator*, and the expressions `*r = o`, `++r`, `r++` and `*r++ = o` of Table 80 are valid. `++r` requires `addressof(r) == addressof(++r)`, and `r++` is convertible to `const X&`. After each of these operations, `r` is no longer required to be dereferenceable but can still be incremented.

¶2 Recommended practice: single-pass. Note 1 says the only valid use of `operator*` is on the left side of an assignment, writing only once through the same iterator value; equality and inequality need not be defined.

## *Cpp17ForwardIterator* [forward.iterators]

¶1 `X` meets *Cpp17ForwardIterator* if and only if:

1. it meets *Cpp17InputIterator*;
2. it is default constructible;
3. the `reference` of a mutable iterator is `T&`, and that of a constant iterator `const T&`;
4. the expressions of Table 81 are valid: `r++` is convertible to `const X&`, and `*r++` returns `reference`;
5. it provides the multi-pass guarantee.

¶2 The domain of `==` is iterators into the same sequence. Value-initialized iterators can be compared and are equal to other value-initialized iterators of the same type; Note 1 says they behave as if they pointed past the end of the same empty sequence.

¶3 The **multi-pass guarantee**: `a == b` implies `++a == ++b`; and either `X` is a pointer type or `(void)++X(a), *a` is equivalent to `*a`, i.e. incrementing a copy does not affect the original. ¶4 Note 2 explains that the multi-pass guarantee, plus being able to assign through a mutable iterator multiple times, makes one-directional algorithms that need to look back possible.

¶5 Two equal iterators are either both dereferenceable or both not. ¶6 Two dereferenceable iterators are equal if and only if `*a` and `*b` are bound to the same object.

Item 3 and ¶6 keep proxy iterators out: `reference` must be a real reference, and equality must mean referring to the same object. The `reference` of `vector<bool>::iterator` is a proxy class, so strictly speaking it does not even meet *Cpp17ForwardIterator*, yet mainstream implementations have always declared it `random_access_iterator_tag`. C++20's `forward_iterator` concept dropped these two items and instead excludes iterators that store elements inside themselves by requiring references to remain valid while the range is valid ([[iterator.concept.forward]]).

## *Cpp17BidirectionalIterator* [bidirectional.iterators]

¶1 On top of *Cpp17ForwardIterator*, Table 82 requires:

- `--r` returns `X&`. Precondition: there exists `s` such that `r == ++s`; afterwards `r` is dereferenceable, `--(++r) == r`, `--r == --s` implies `r == s`, and `addressof(r) == addressof(--r)`.
- `r--` is convertible to `const X&`, and `*r--` returns `reference`.

## *Cpp17RandomAccessIterator* [random.access.iterators]

¶1 On top of *Cpp17BidirectionalIterator*, Table 83 gives the semantics of each operation with reference code:

| Expression | Returns | Semantics |
|---|---|---|
| `r += n` | `X&` | As if `n` applications of `++`; if `n` is negative, as if `-n` applications of `--` |
| `a + n`, `n + a` | `X` | `{ X tmp = a; return tmp += n; }`, and `a + n == n + a` |
| `r -= n` | `X&` | `return r += -n;`, provided the absolute value of `n` is representable by `difference_type` |
| `a - n` | `X` | `{ X tmp = a; return tmp -= n; }` |
| `b - a` | `difference_type` | Precondition: there exists `n` such that `a + n == b`; `b == a + (b - a)` |
| `a[n]` | Convertible to `reference` | `*(a + n)` |
| `a < b` | Models *`boolean-testable`* | Equivalent to `b - a > 0`; `<` is a total ordering |
| `a > b`, `a >= b`, `a <= b` | Same | Derived from `<` |

The loops in the table only say what the result should be, not how to implement it. [[iterator.requirements.general#14]] still requires these operations to be constant time.

## The two systems compared

| Aspect | *Cpp17* named requirements | C++20 concepts |
|---|---|---|
| Checking | Prose specification, not checked by the compiler | The syntactic part is checked by the compiler |
| Where the category is read from | `iterator_traits<X>::iterator_category` | *`ITER_CONCEPT`*, reading `iterator_concept` first |
| Copyable | Every iterator | From `forward_iterator` on |
| `==` | From input iterators on | From `forward_iterator` on; before that, comparison with sentinels |
| `reference` | Must be a real reference from forward on | Not required, except for `contiguous_iterator` |
| Difference type | A signed integer type or `void` | A signed integer-like type, possibly an integer-class type |
| Postfix `++` | Must return a usable value | May return `void` for input iterators |
| `a[n]` | Convertible to `reference` | Must be exactly `iter_reference_t` |
| Contiguous | No such level | `contiguous_iterator` |
| End | Same type as the iterator | Any `sentinel_for` |

## Common misconceptions

!!! pitfall "Judging a C++20 iterator's abilities by `iterator_category`"
    Dispatch code that still reads `iterator_traits<I>::iterator_category` treats the iterators of views like `iota` and `transform` as input iterators across the board. New code should dispatch on concepts, for example `if constexpr (std::random_access_iterator<I>)`, or call the `ranges::` versions of the primitives directly.

!!! pitfall "C++23 has relaxed everything to concepts"
    C++23's [[P2408R5]] relaxed [[algorithms.requirements#4]], but only for the algorithms of Chapter 26, and only where mutable iterators are not required: parameters named `ForwardIterator` and so on may merely model the corresponding concept. `std::advance`, `std::distance`, `std::next`, `std::prev` and the iterator-pair constructors of containers are not covered.

## Questions

!!! question "Question 1"
    For `++r` of *Cpp17InputIterator*, the requirements say copies of the previous value are no longer required to be dereferenceable, and add that they are no longer required to be in the domain of `==`. What is the second half for?

<details markdown="1">
<summary>Answer</summary>

It says that even comparison loses its meaning. The `==` of `istream_iterator` only compares whether the two refer to the same stream ([[istream.iterator]]). Advancing one copy reads data out of the shared stream, so the old values held by the other copies no longer match the stream's state, and comparing them gives results that do not reflect position; the standard simply makes no guarantee at all.
</details>

!!! question "Question 2"
    The `reference` of `std::istreambuf_iterator<char>` is `char`, not a reference. Which *Cpp17* level does it meet? Which concept level does it model?

<details markdown="1">
<summary>Answer</summary>

`reference` is not a reference, so it does not meet item 3 of *Cpp17ForwardIterator*; it is only a *Cpp17InputIterator*. In C++20 it models `input_iterator` and likewise not `forward_iterator`: it is inherently single-pass, and its declared `input_iterator_tag` also caps *`ITER_CONCEPT`*.
</details>
