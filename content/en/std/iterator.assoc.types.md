---
title: Associated types
summary: "How to find an iterator's difference type, value type and category at compile time: the rules of the three trait classes incrementable_traits, indirectly_readable_traits and iterator_traits, and how C++20's iterator_traits primary template deduces them automatically."
updated: 2026-10-19
---

!!! tldr
    - Since C++20, use `iter_difference_t<I>` for the difference type, `iter_value_t<I>` for the value type, and `iterator_traits<I>::iterator_category` for the category in the C++17 sense.
    - If the user has specialized `iterator_traits<I>`, `iter_difference_t` and `iter_value_t` follow the specialization; otherwise they consult `incrementable_traits` and `indirectly_readable_traits`.
    - `iter_value_t` recognizes both member names `value_type` and `element_type`, and gives no answer when the two conflict.
    - The `iterator_traits` primary template deduces the members itself when a type does not declare them, with `random_access_iterator_tag` as the highest category it can deduce; when nothing can be deduced it is empty and can be used safely in SFINAE.

## Three questions, three trait classes

Generic algorithms often ask three questions about an iterator `I`: what type do you get by subtracting two `I`s? What type should a value read through `*i` be stored as? Which category does `I` belong to? [iterator.assoc.types] answers with three class templates:

| Question | Preferred spelling | Underlying trait class | Subclause |
|---|---|---|---|
| Difference type | `iter_difference_t<I>` | `incrementable_traits<I>` | [incrementable.traits] |
| Value type | `iter_value_t<I>` | `indirectly_readable_traits<I>` | [readable.traits] |
| Category, `pointer`, `reference` | `iterator_traits<I>` | `iterator_traits<I>` | [iterator.traits] |

The `<iterator>` synopsis also defines two aliases directly: `iter_reference_t<T>` is `decltype(*declval<T&>())`, and `iter_rvalue_reference_t<T>` is `decltype(ranges::iter_move(declval<T&>()))` ([[iterators]], [[iterator.cust]]).

C++98 had only `iterator_traits`. C++20 split out the difference type and the value type because the new concept system needs to ask these two questions of types that are not iterators: integers that are `weakly_incrementable` need a difference type, and an `indirectly_readable` `shared_ptr<int>` needs a value type.

```cpp run title="value_type.cpp" ok
#include <iterator>
#include <memory>
#include <optional>

static_assert(std::same_as<std::iter_value_t<const int*>, int>);
static_assert(std::same_as<std::iter_value_t<int[3]>, int>);
static_assert(std::same_as<std::iter_difference_t<unsigned>, int>);
static_assert(std::indirectly_readable<std::shared_ptr<int>>);
static_assert(!std::indirectly_readable<std::shared_ptr<void>>);
static_assert(!std::indirectly_readable<std::optional<int>>);

int main() {}
```

The sections below explain these lines one by one.

## Difference type [incrementable.traits]

¶1 If `WI` models `weakly_incrementable`, `iter_difference_t<WI>` is its difference type. `incrementable_traits<T>` determines `difference_type` through the following partial specializations:

1. The primary template: no `difference_type`;
2. `T*` where `T` is an object type: `ptrdiff_t`. Function pointers and `void*` are excluded;
3. `const I`: the same as `I`;
4. `T` has a nested `difference_type`: use it;
5. No nested `difference_type`, but `a - b` has an integral type: `make_signed_t<decltype(a - b)>`.

Rule 5 gives types that can be incremented on their own, like `int` and `unsigned`, a difference type too. `unsigned - unsigned` is `unsigned`, and taking its signed version gives `int`, so `iter_difference_t<unsigned>` is `int`.

¶2 `iter_difference_t<I>` does not consult `incrementable_traits` directly. Let `RI` be `remove_cvref_t<I>`:

!!! std
    The type iter_difference_t<I> denotes incrementable_traits<RI>::difference_type if iterator_traits<RI> names a specialization generated from the primary template, and iterator_traits<RI>::difference_type otherwise.

    That is, if `iterator_traits<RI>` is generated from the primary template, `incrementable_traits` is consulted; otherwise (the user has specialized `iterator_traits`) the specialization's `difference_type` is used.

The reason is backward compatibility. Up to C++17, specializing `iterator_traits` was the standard way to provide associated types for a custom iterator (the example in [[std.iterator.tags]] does just that). The new aliases must respect those specializations, or the same iterator would have two contradictory sets of answers. Conversely, the primary template is itself deduced from `incrementable_traits` and friends, so consulting it again would be circular.

A program has no direct way to ask whether a specialization was generated from the primary template; this is just the standard's means of expression, and implementations usually put a marker member in the primary template.

!!! impl "libc++"
    libc++ defines `using __primary_template = iterator_traits;` in the `iterator_traits` primary template and then checks whether `iterator_traits<I>::__primary_template` is `iterator_traits<I>` itself. A user specialization has no such member and is thereby recognized.

¶3 Users may specialize `incrementable_traits` for program-defined types.

## Value type [readable.traits]

¶1 If `R` models `indirectly_readable`, `iter_value_t<R>` is its value type. The rules are more involved than for the difference type, because value types come under two common member names: iterators customarily use `value_type`, smart pointers `element_type`.

First an exposition-only helper class *cond-value-type*`<T>` is defined: it provides `value_type = remove_cv_t<T>` only if `T` is an object type. Then the rules of `indirectly_readable_traits<T>` are:

| What `T` is | `value_type` |
|---|---|
| `U*` | *cond-value-type*`<U>`: `int` for `const int*`, none for `void*` |
| An array type | `remove_cv_t<remove_extent_t<T>>`: `int` for `int[3]` |
| `const I` | The same as `I` |
| Only `value_type` or only `element_type` | That one (through *cond-value-type*) |
| Both, the same after removing cv | `value_type` |
| Both, different after removing cv | No `value_type` |

The last row means: when the two members contradict each other, better to give no answer.

¶2 Exactly parallel to the difference type: when `iterator_traits<RI>` is generated from the primary template, `indirectly_readable_traits` is consulted; otherwise `iterator_traits<RI>::value_type` is used. ¶3 Users may specialize `indirectly_readable_traits` for program-defined types.

¶4 Note 1: some legacy output iterators declare `value_type` as `void`. *cond-value-type*`<void>` is empty, so they have no value type and are not `indirectly_readable`.

¶5 Note 2: `shared_ptr<int>` is `indirectly_readable`, with value type `int`; the `element_type` of `shared_ptr<void>` is `void`, so it has no value type and is not `indirectly_readable`.

### Why `optional<int>` is not `indirectly_readable`

`optional<int>` has a `value_type` and an `operator*`, yet it is not `indirectly_readable`. The reason is in [[iterator.concept.readable]]: that concept requires the type obtained by dereferencing a `const In` to be exactly the same as `iter_reference_t<In>`. `optional` is deeply const: `*const_opt` gives `const int&` and `*opt` gives `int&`, which differ. `shared_ptr` is shallowly const: dereferencing a `const shared_ptr<int>` still gives `int&`, so it qualifies. This requirement separates pointer-like things from value-like containers.

## `iterator_traits` [iterator.traits]

### What it provides (¶1)

¶1 `iterator_traits<I>` has five members: `iterator_category` (the category tag), `value_type`, `difference_type`, `pointer` and `reference`. For an iterator object `a` of class type, `pointer` and `reference` should be `decltype(a.operator->())` and `decltype(*a)` respectively; if `operator->` is not supported, `pointer` is `void`. For an output iterator, `value_type`, `difference_type` and `reference` may be `void`.

### How the primary template deduces (¶2–¶3)

C++20's primary template deduces the members itself when a type does not declare them. To do so it first has to judge whether `I` looks like a C++17 iterator. ¶2 defines five exposition-only concepts that are syntactic approximations of the named requirements in [[iterator.cpp17]]:

| Concept | Adds to the previous one |
|---|---|
| *cpp17-iterator* | `*i` and `*i++` are referenceable, `++i` returns `I&`, `copyable<I>` |
| *cpp17-input-iterator* | `equality_comparable`; `incrementable_traits` gives a `signed_integral` difference type; `indirectly_readable_traits` gives a value type; two `common_reference` requirements |
| *cpp17-forward-iterator* | Default constructible; `iter_reference_t<I>` is a reference type that, with cvref removed, equals the value type; type constraints on `i++` and `*i++` |
| *cpp17-bidirectional-iterator* | `--i`, `i--`, `*i--` |
| *cpp17-random-access-iterator* | `totally_ordered`; `+=`, `-=`, `+`, `-`, `[]` and `i - i` |

Two details decide how many types are classified: *cpp17-input-iterator* requires the difference type to be `signed_integral`, so integer-class types do not count; *cpp17-forward-iterator* requires `*i` to return a real reference.

¶3 A specialization generated from the primary template determines its members in this order:

1. (3.1) `I` declares the four members `difference_type`, `value_type`, `reference` and `iterator_category` itself: copy them. Copy `pointer` if present, otherwise it is `void`. This is the path for C++98-style iterators.
2. (3.2) Otherwise, if `I` satisfies *cpp17-input-iterator*:
    - `value_type` comes from `indirectly_readable_traits`, and `difference_type` from `incrementable_traits`;
    - `pointer`: `I::pointer` if it exists, otherwise the return type of `operator->()` if that is valid, otherwise `void`;
    - `reference`: `I::reference` if it exists, otherwise `iter_reference_t<I>`;
    - `iterator_category`: `I::iterator_category` if it exists, otherwise the random access, bidirectional, forward or input tag according to the strongest *cpp17* concept satisfied.
3. (3.3) Otherwise, if `I` satisfies *cpp17-iterator*: it is treated as an output iterator. `iterator_category` is `output_iterator_tag`, and `value_type`, `pointer` and `reference` are `void`; `difference_type` is taken from `incrementable_traits` if available, otherwise `void`.
4. (3.4) Otherwise, `iterator_traits<I>` has none of the above members.

Rule 4 lets `iterator_traits` be used safely in SFINAE: `iterator_traits<int>::value_type` is just a substitution failure, not a hard error. The highest category (3.2) can deduce is `random_access_iterator_tag`, never `contiguous_iterator_tag`, because the C++17 named requirements have no contiguous level.

```cpp run title="traits_deduce.cpp" ok
#include <iterator>
#include <ranges>

// C++20 style: declares only iterator_concept, value_type and difference_type
struct It {
  using iterator_concept = std::forward_iterator_tag;
  using value_type = int;
  using difference_type = std::ptrdiff_t;
  int* p;
  int& operator*() const { return *p; }
  It& operator++() { ++p; return *this; }
  It operator++(int) { auto t = *this; ++p; return t; }
  bool operator==(const It&) const = default;
};
// no iterator_category: goes through (3.2) and satisfies cpp17-forward-iterator
static_assert(std::same_as<std::iterator_traits<It>::iterator_category,
                           std::forward_iterator_tag>);
static_assert(std::same_as<std::iterator_traits<It>::pointer, void>);
static_assert(std::forward_iterator<It>);

// iota's iterator: *it returns an int prvalue
using IotaIt = std::ranges::iterator_t<std::ranges::iota_view<int, int>>;
static_assert(std::same_as<std::iterator_traits<IotaIt>::iterator_category,
                           std::input_iterator_tag>);
static_assert(std::random_access_iterator<IotaIt>);

int main() {}
```

The `iterator_category` of `iota_view`'s iterator is actually a member it declares itself: when `W` models `incrementable` and the difference type is an integral type, [[range.iota.iterator]] specifies it as `input_iterator_tag`. This agrees with what (3.2) would deduce, because `*it` is not a reference and does not satisfy *cpp17-forward-iterator*.

### `iterator_concept` (¶4)

¶4 An explicit or partial specialization of `iterator_traits` may have an `iterator_concept` member indicating the type's conformance to the C++20 iterator concepts. Example 1: to indicate that a type conforms to the `input_iterator` concept but does not meet *Cpp17InputIterator*, the specialization can have `iterator_concept` as `input_iterator_tag` and not declare `iterator_category`. How these members are read is described by *ITER_TRAITS* and *ITER_CONCEPT* in [[iterator.concepts]].

The primary template never produces `iterator_concept`. For an ordinary class-type iterator, *ITER_CONCEPT* reads `I::iterator_concept` directly, without going through `iterator_traits`.

### The specialization for pointers (¶5–¶6)

¶5 Pointers have a dedicated partial specialization:

```cpp
template<class T> requires is_object_v<T>
struct iterator_traits<T*> {
  using iterator_concept  = contiguous_iterator_tag;
  using iterator_category = random_access_iterator_tag;
  using value_type        = remove_cv_t<T>;
  using difference_type   = ptrdiff_t;
  using pointer           = T*;
  using reference         = T&;
};
```

`requires is_object_v<T>` excludes function pointers and `void*`; `value_type` removes cv, so the value type of `const int*` is `int`; `iterator_category` is still random access, for compatibility with old code that dispatches on tags, and contiguity is expressed only through `iterator_concept`.

¶6 Example 2 writes a `reverse` using `iterator_traits<BI>::difference_type` and `value_type`, the typical style of C++98 generic code. Today you would write `iter_difference_t<BI>` and `iter_value_t<BI>`.

## Common misconceptions

!!! pitfall "After specializing `iterator_traits`, the other members are still deduced automatically"
    Once `iterator_traits<MyIt>` is specialized, ¶2 makes `iter_value_t<MyIt>` and `iter_difference_t<MyIt>` consult that specialization instead, and so does *ITER_CONCEPT* ([[iterator.concepts]]). Leave `iterator_concept` out of the specialization and the C++20 concepts can see only `iterator_category`; leave out `value_type` and `iter_value_t` does not exist. Since C++20, adding members to the type itself is almost always better than specializing `iterator_traits`.

!!! pitfall "`iterator_traits<const I>` is the same as `iterator_traits<I>`"
    `incrementable_traits` and `indirectly_readable_traits` have `const I` partial specializations, and aliases like `iter_value_t` apply `remove_cvref_t` first, but `iterator_traits` has no such handling. For an iterator that declares the four members itself, `const It` still takes path (3.1); for an iterator that relies on deduction, a `const It` cannot be incremented, does not satisfy *cpp17-iterator*, nothing can be deduced, and `iterator_traits<const It>` is empty; `int* const` does not match the pointer specialization and is empty too. Use `iterator_traits` on the cv-unqualified type, or use the `iter_*_t` aliases directly.

## Questions

!!! question "Question 1"
    A type has both `value_type = int` and `element_type = const int`. What is `iter_value_t`? What if `element_type = long`?

<details markdown="1">
<summary>Answer</summary>

`value_type` is the same as `remove_cv_t<element_type>`, so it is `int`. If `element_type = long`, the two differ, `indirectly_readable_traits` has no `value_type`, `iter_value_t` does not exist, and the type is not `indirectly_readable`.
</details>

!!! question "Question 2"
    Why does rule 5 of `incrementable_traits` use `make_signed_t`? What is `iter_difference_t<unsigned char>`?

<details markdown="1">
<summary>Answer</summary>

The difference type must be signed ([[iterator.concept.winc]]). `unsigned char - unsigned char` gives `int` after integral promotion, and `make_signed_t<int>` is still `int`, so the answer is `int`.
</details>

!!! question "Question 3"
    Write a type that declares no member types and for which `iterator_traits<X>::iterator_category` is `output_iterator_tag`.

<details markdown="1">
<summary>Answer</summary>

Any type that satisfies *cpp17-iterator* but not *cpp17-input-iterator* will do, for example:

```cpp
struct Out { Out& operator*(); Out& operator++(); Out& operator++(int); };
```

It is copyable, and `*i`, `++i` and `*i++` are all valid, but it has no `operator==`, so it does not satisfy `equality_comparable` and takes path (3.3). Its `difference_type` is `void`, because `incrementable_traits<Out>` has no answer.
</details>
