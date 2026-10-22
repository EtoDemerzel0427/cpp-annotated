---
title: Iterators library
summary: "A guide to Chapter 24: iterators are a generalization of pointers; the standard has two coexisting ways of describing iterators, C++98's named requirements plus category tags and C++20's concepts plus sentinels, and the same type may fall into different categories under the two."
updated: 2026-10-19
---

!!! tldr
    - Iterators separate containers from algorithms: an algorithm only asks for something supporting `++`, `*` and `==`, so the same `std::find` works on arrays, linked lists and streams.
    - C++98 describes iterators with named requirements written as tables (*Cpp17InputIterator* and so on), and types declare their category through an `iterator_category` tag.
    - C++20 adds a set of compiler-checked concepts (`input_iterator` through `contiguous_iterator`) and allows the end of a range to be a sentinel of a different type.
    - Both systems are in force at once: `std::` algorithms look at the named requirements, `std::ranges::` algorithms at the concepts; the same iterator can have different categories in the two.
    - Almost everything in `<iterator>` except the stream iterators is freestanding, so freestanding implementations must provide it too.

## What problem iterators solve

```cpp run title="sentinel.cpp" ok
#include <algorithm>
#include <cassert>
#include <iterator>

int main() {
  const char buf[] = "hello\nworld";
  auto nl = std::ranges::find(buf + 0, std::unreachable_sentinel, '\n');
  assert(nl == buf + 5);
}
```

`std::ranges::find` does not know that `buf` is an array. All it needs is a starting point that can be incremented, dereferenced and compared with the end, plus an end. An **iterator** is the abstraction of such a starting point, with semantics generalized from pointers to array elements ([[expr.add]]). That way `N` containers and `M` algorithms need `N + M` pieces of code instead of `N × M`.

The end in the example is not a pointer but `std::unreachable_sentinel`: an object that compares unequal to every iterator ([[unreachable.sentinel]]). So the loop is left with just one test, `*p == '\n'`. The price is that the caller must guarantee `'\n'` is there; otherwise `find` runs past the end of the array and the behavior is undefined.

Chapter 24 [iterators] specifies precisely which operations an iterator supports, their semantics and complexity, and how to query its properties at compile time, and provides a set of ready-made iterators and adaptors.

## Organization of the chapter [iterators.general]

¶1 The components of this chapter serve iteration over containers ([[containers]]), streams ([[iostream.format]]), stream buffers ([[stream.buffers]]) and other ranges ([[ranges]]).

¶2 Table 76 lists five subclauses, all in the header `<iterator>`:

| Subclause | Contents | Pages on this site |
|---|---|---|
| [iterator.requirements] | Values and ranges of iterators; associated types; `iter_move`/`iter_swap`; C++20 iterator concepts; C++17 named requirements; indirect callable concepts; common algorithm requirements | [[iterator.requirements]], [[iterator.assoc.types]], [[iterator.cust]], [[iterator.concepts]], [[iterator.cpp17]], [[indirectcallable]], [[alg.req]] |
| [iterator.primitives] | Category tags; `advance`/`distance`/`next`/`prev` and their `ranges::` versions | [[iterator.primitives]] |
| [predef.iterators] | Iterator adaptors: `reverse_iterator`, insert iterators, `basic_const_iterator`, `move_iterator`, `common_iterator`, `counted_iterator`, and two sentinel types | [[predef.iterators]] |
| [stream.iterators] | `istream_iterator`, `ostream_iterator`, `istreambuf_iterator`, `ostreambuf_iterator` | [[stream.iterators]] |
| [iterator.range] | Non-member `begin`/`end`/`size`/`ssize`/`empty`/`data` | [[iterator.range]] |

## Two parallel classifications

### C++98: named requirements plus category tags

C++98 defined five sets of requirements in prose and tables: *Cpp17InputIterator*, *Cpp17OutputIterator*, *Cpp17ForwardIterator*, *Cpp17BidirectionalIterator* and *Cpp17RandomAccessIterator*, now collected in [[iterator.cpp17]]. The Cpp17 prefix in the names was added in C++20 to distinguish them from the new concepts.

The compiler cannot check tables, so each iterator also declares a **category tag** through `iterator_traits<I>::iterator_category`, for example `random_access_iterator_tag`. Algorithms choose overloads based on the tag ([[std.iterator.tags]]). This approach has three problems:

- The tag is only a declaration. If a type claims to be a random access iterator, the library uses it as one; if the claim is wrong, the behavior is undefined.
- The requirements are bundled too tightly. *Cpp17ForwardIterator* requires `*it` to return a real reference, so `vector<bool>::iterator` and iterators that return elements by value can officially only count as input iterators, even if they support constant-time random access.
- The beginning and end must have the same type. A string terminated by `'\0'` must have its end computed first before being handed to an algorithm.

### C++20: concepts plus sentinels

The Ranges proposal [[P0896R4]] introduced a set of iterator **concepts** ([[iterator.concepts]]): `input_or_output_iterator`, `input_iterator`, `output_iterator`, `forward_iterator`, `bidirectional_iterator`, `random_access_iterator`, and a new level, `contiguous_iterator` (elements contiguous in memory). Compared with the named requirements:

- Syntactic requirements are checked by the compiler. The category still has to be declared, but the `iterator_concept` member is what is read (the rules are *ITER_CONCEPT* in [[iterator.concepts]]).
- `*it` need not return a real reference, so iterators that return proxy objects can be random access too.
- `input_iterator` requires neither copyability nor `==` comparison, so move-only input iterators are valid.
- The end of a range can be a **sentinel**: its type may differ from the iterator's, as long as the two can be compared (`sentinel_for`).

The inclusion order of the six categories is contiguous → random access → bidirectional → forward → input, with output as a separate branch ([[iterator.requirements.general#2]]). "Iterator" in general means any type that models `input_or_output_iterator`.

!!! warning "The same type can get different answers from the two systems"
    The iterator of `std::ranges::iota_view<int, int>` models `random_access_iterator`, but its `iterator_traits<>::iterator_category` is `input_iterator_tag`, because `*it` returns an `int` prvalue, which does not meet the reference requirement of *Cpp17ForwardIterator*. Hand it to functions that look only at the tag, such as `std::distance` and `std::prev`, and it gets treated as an input iterator. See [[iterator.cpp17]] and [[iterator.primitives]] for details.

## The header `<iterator>` [iterator.synopsis]

By function, the synopsis falls into several groups, each covered in detail on later pages:

| Group | Main contents | Details |
|---|---|---|
| Associated types | `iter_difference_t`, `iter_value_t`, `iterator_traits`, `iter_reference_t`, `iter_rvalue_reference_t`, `iter_common_reference_t` | [[iterator.assoc.types]] |
| Customization point objects | `ranges::iter_move`, `ranges::iter_swap` | [[iterator.cust]] |
| Concepts | 13 iterator concepts (from `indirectly_readable` to `contiguous_iterator`), 6 indirect callable concepts, 9 algorithm requirement concepts (from `indirectly_movable` to `sortable`) | [[iterator.concepts]], [[indirectcallable]], [[alg.req]] |
| Primitives | 6 category tags, two sets of `advance`/`distance`/`next`/`prev` | [[iterator.primitives]] |
| Adaptors and sentinels | `reverse_iterator` through `unreachable_sentinel_t` | [[predef.iterators]] |
| Stream iterators, range access | `istream_iterator` and friends; `std::begin` and friends | [[stream.iterators]], [[iterator.range]] |

The synopsis begins by defining two exposition-only concepts: *can-reference* (`T&` is valid, i.e. `T` is not `void`) and *dereferenceable* (the result of `*t` satisfies *can-reference*). `iter_reference_t<T>` is defined as `decltype(*declval<T&>())` and requires `T` to satisfy *dereferenceable*.

Apart from the stream iterators, almost every item in the synopsis is marked `// freestanding`, so freestanding implementations ([[g:freestanding-implementation]]) must provide them too. The stream iterators depend on `<istream>`/`<ostream>` and are not included. `<iterator>` must include `<compare>`, `<concepts>` and `<initializer_list>`. The iterator concepts live in `<iterator>` rather than `<concepts>` because they depend on associated types and `iter_move`, facilities defined only in this chapter.

## Questions

!!! question "Question 1"
    Now that C++20 has concepts, why haven't `iterator_traits` and the *Cpp17* named requirements been deprecated?

<details markdown="1">
<summary>Answer</summary>

Many `std::` algorithms ([[algorithms.requirements]]), the iterator-pair constructors of containers, and user code dispatch on `iterator_category`. The C++20 concepts assign higher categories to proxy iterators, and replacing one with the other outright would change which overloads old code selects. So the two coexist: `std::` algorithms follow the named requirements ([[algorithms.requirements#4]] allows forward-iterator parameters of non-modifying algorithms to model `forward_iterator` instead), and `std::ranges::` algorithms follow the concepts.
</details>

!!! question "Question 2"
    Before C++20 there was only `random_access_iterator_tag` and no tag for contiguous iterators. What did that cost?

<details markdown="1">
<summary>Answer</summary>

The library could not know at compile time that elements are contiguous in memory, so it could not replace the iterators with pointers and call `memmove` or `memcmp`. Implementations could only special-case types they knew (pointers, and the iterators of their own `vector`/`string`). `contiguous_iterator_tag` and `std::to_address` let user types get this optimization too ([[iterator.requirements.general#13]]).
</details>
