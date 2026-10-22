---
title: "Constant iterators: basic_const_iterator"
summary: "C++23's basic_const_iterator wraps any input iterator so that its dereference result cannot be used to modify elements, while keeping the original traversal category; it underlies ranges::cbegin and views::as_const."
updated: 2026-10-19
---

!!! tldr
    - `std::cbegin` does not help for types like `span<int>` whose constness does not propagate to the elements: the iterator it returns is still writable. C++23's `std::ranges::cbegin` uses `basic_const_iterator` instead, and only then do you get a truly read-only iterator.
    - `iter_const_reference_t<It>` is the common reference of `const iter_value_t<It>&&` and the original reference type; if it equals the original reference type, the iterator is already a constant iterator.
    - `const_iterator<I>` returns `I` unchanged when it is already a constant iterator, and `basic_const_iterator<I>` otherwise.
    - `basic_const_iterator` keeps every category of the underlying iterator, contiguous included, and converts implicitly back to native constant iterators such as `const int*`.
    - At the time of writing, the libc++ shipped with Clang 23 does not implement this subclause yet; the examples on this page need GCC.

## Why it is needed

`std::span<int>` is a view; a `const span<int>` only means the view itself cannot be re-pointed, and the elements are still writable. So C++11's `std::cbegin(s)`, which is `std::begin(std::as_const(s))`, returns an iterator that can still write the elements:

```cpp run ok
#include <iterator>
#include <span>
int main() {
  int a[3]{1, 2, 3};
  std::span<int> s(a);
  *std::cbegin(s) = 42;   // OK: cbegin fails to prevent the write
  return a[0] == 42 ? 0 : 1;
}
```

C++23's answer is a general-purpose wrapper: put a layer around any input iterator that changes only the result type of dereferencing, so that it cannot be used to modify elements. That is `basic_const_iterator`. `std::ranges::cbegin` and `views::as_const` are both built on it ([[range.access]]).

¶1 [const.iterators.general] states the goal in terms of a **constant iterator**: one through which the referenced element cannot be modified ([[iterator.requirements]]). `basic_const_iterator` behaves exactly like its underlying iterator, except that its indirection operator converts the underlying dereference result to a type that makes it a constant iterator. ¶2 All specializations of it are constant iterators.

## How to tell whether an iterator is already constant [const.iterators.alias]

```cpp
template<indirectly_readable It>
  using iter_const_reference_t =
    common_reference_t<const iter_value_t<It>&&,
                       iter_reference_t<It>>;

template<class It>
  concept constant-iterator =        // exposition only
    input_iterator<It> &&
    same_as<iter_const_reference_t<It>, iter_reference_t<It>>;
```

`iter_const_reference_t<It>` answers the question: what type should we get by adding const to this iterator's reference type? It takes the **common reference** of a const rvalue reference to the value type and the original reference type (the type both reference types can convert to; see `common_reference` in [[meta.trans.other]]). If the result equals the original reference type, adding const changed nothing, and the iterator is already a constant iterator.

| `iter_reference_t<It>` | `iter_value_t<It>` | `iter_const_reference_t<It>` | Constant iterator? |
|---|---|---|---|
| `int&` | `int` | `const int&` | No |
| `const int&` | `int` | `const int&` | Yes |
| `int&&` | `int` | `const int&&` | No |
| `int` (prvalue) | `int` | `int` | Yes |
| `vector<bool>::reference` | `bool` | `bool` | No |
| `tuple<int&, int&>` (zip) | `tuple<int, int>` | `tuple<const int&, const int&>` | No |

The prvalue row is a constant iterator because dereferencing yields a copy, and modifying the copy does not affect the original element. The last two rows are proxy references (class objects that behave like references): the common reference is either the value type itself or a proxy with const added to every member, and neither can modify the original element any more.

¶1 `const_iterator<I>` is just `I` itself when `I` models *`constant-iterator`*, with no extra layer; otherwise it is `basic_const_iterator<I>`.

¶2 `const_sentinel<S>` equals `const_iterator<S>` when `S` is itself an input iterator (a range whose begin and end have the same type), and is `S` otherwise. A pure sentinel cannot be dereferenced and needs no wrapping. The synopsis also has `make_const_iterator(it)` and `make_const_sentinel(s)`, which return objects of these two types respectively.

## The interface of basic_const_iterator [const.iterators.iterator]

```cpp
template<input_iterator Iterator>
class basic_const_iterator {
  Iterator current_ = Iterator();                      // exposition only
  using reference = iter_const_reference_t<Iterator>;  // exposition only
  using rvalue-reference =                             // exposition only
    iter-const-rvalue-reference-t<Iterator>;
public:
  using iterator_type = Iterator;
  using iterator_concept = see below;
  using iterator_category = see below;  // not always present
  using value_type = iter_value_t<Iterator>;
  using difference_type = iter_difference_t<Iterator>;
  // constructors, base(), *, ->, ++, --, +=, -=, [], comparisons, +, -,
  // conversion operators, iter_move
};
```

`reference` and `rvalue-reference` are both exposition-only private aliases; the public interface has no `reference` member. `iterator_traits` deduces the reference type through `iter_reference_t`. *`iter-const-rvalue-reference-t<I>`* is `common_reference_t<const iter_value_t<I>&&, iter_rvalue_reference_t<I>>` and is used by `iter_move`.

### Every category is kept [const.iterators.types]

¶1 `iterator_concept` checks the underlying iterator for contiguous, random access, bidirectional and forward in that order, and is input when none of them hold. The contiguous category is kept too, unlike with `move_iterator` and `reverse_iterator`: adding const does not change where elements live in memory, so `basic_const_iterator<int*>` is still a contiguous iterator.

¶2 `iterator_category` is declared only when the underlying iterator models `forward_iterator`, and is the underlying `iterator_traits<Iterator>::iterator_category`.

### Constness is applied at dereference [const.iterators.ops]

¶6 `operator*` is equivalent to `return static_cast<reference>(*current_);`. ¶13 `operator[]` likewise goes through `static_cast<reference>`. The rest of the adaptor just forwards operations to `current_`.

- ¶1–¶3 Construction: from `Iterator` (moved in); converting from `basic_const_iterator<U>` (where `U` is convertible to `Iterator`); from any `T&&` convertible to `Iterator`. The last one lets `basic_const_iterator<vector<int>::const_iterator>` be constructed directly from a `vector<int>::iterator`. Default construction exists only if the underlying iterator is default-initializable.
- ¶4–¶5 `base() const&` returns `const Iterator&`; `base() &&` moves the underlying iterator out.
- ¶7 `operator->` is provided only when the underlying reference is an lvalue reference that, with cvref removed, is the value type; it returns `const auto*`. When the underlying iterator is contiguous it returns `to_address(current_)`, otherwise `addressof(*current_)`.
- ¶9 For single-pass input iterators, postfix `++` returns `void`. For forward and stronger iterators, postfix `++` and `--` are declared `= default`, which copies, does the prefix increment or decrement, and returns the copy ([[over.inc.default]]).
- ¶14 `==` against a sentinel; ¶17–¶18 relational comparisons and `<=>` against the same type; ¶19–¶22 comparisons in both directions against other types `I` that the underlying iterator can be compared with. The last group lets `basic_const_iterator<It>` be compared directly with `It`.
- ¶23–¶26 For random access, `+` and `-` are provided, plus the distance to a sized sentinel.

### Converting back to native constant iterators (¶15–¶16)

```cpp
template<not-a-const-iterator CI>
  requires constant-iterator<CI> &&
           convertible_to<Iterator const&, CI>
constexpr operator CI() const &;
template<not-a-const-iterator CI>
  requires constant-iterator<CI> &&
           convertible_to<Iterator, CI>
constexpr operator CI() &&;
```

As long as the underlying iterator can convert to some constant iterator type `CI`, `basic_const_iterator` converts to it implicitly. For example, `basic_const_iterator<int*>` converts to `const int*`, and `basic_const_iterator<vector<int>::iterator>` converts to `vector<int>::const_iterator`. So the result of `ranges::cbegin(v)` can still be passed to older interfaces that accept only native constant iterators.

*`not-a-const-iterator<CI>`*, defined in [const.iterators.iterator] ¶1, excludes the case where `CI` is a specialization of `basic_const_iterator`, avoiding ambiguity with the converting constructor.

The synopsis also specializes `common_type`: the common type of `basic_const_iterator<T>` and `U` is `basic_const_iterator<common_type_t<T, U>>`. Two iterators where one side went through const-wrapping and the other did not can therefore be unified into one type.

## Example

```cpp run title="const_iterator.cpp" ok cc=gsnapshot
#include <cassert>
#include <iterator>
#include <ranges>
#include <span>

using std::basic_const_iterator;
static_assert(std::same_as<
    std::iter_const_reference_t<int*>, const int&>);
// already a constant iterator: not wrapped
static_assert(std::same_as<
    std::const_iterator<const int*>, const int*>);
static_assert(std::same_as<
    std::const_iterator<int*>, basic_const_iterator<int*>>);
// category kept
static_assert(std::contiguous_iterator<
    basic_const_iterator<int*>>);

int main() {
  int a[3]{1, 2, 3};
  std::span<int> s(a);
  auto it = std::ranges::cbegin(s);
  // *it = 42;                  // error: *it is const int&
  assert(*it == 1);

  basic_const_iterator<int*> ci = a;
  const int* p = ci;           // back to a native constant iterator
  assert(p == a);
}
```

The libc++ shipped with Clang 23 does not yet have `basic_const_iterator`, `const_iterator` or `iter_const_reference_t`, and `__cpp_lib_ranges_as_const` is still commented out in its `<version>`, so this code does not compile there in our tests. libstdc++ and the MSVC STL implement it; use the godbolt button to run it on GCC. The common references in the table above were checked one by one with `std::common_reference_t` on Clang 23.

## Common misconceptions

!!! pitfall "`std::cbegin` and `std::ranges::cbegin` are the same thing"
    `std::cbegin(c)` still has its C++11 definition `std::begin(std::as_const(c))` ([[iterator.range]]) and returns a writable iterator for views like `span<int>`. When you need a truly read-only iterator, use `std::ranges::cbegin` or `views::as_const`.

!!! pitfall "Making an iterator constant downgrades it"
    `move_iterator` goes up to random access at most, but `basic_const_iterator` keeps contiguous. So `std::span<const int>(ranges::cbegin(s), ranges::cend(s))` is valid.

## Questions

!!! question "Question 1"
    Why does `iter_const_reference_t` use `const iter_value_t<It>&&` rather than `const iter_value_t<It>&` when computing the common reference?

<details markdown="1">
<summary>Answer</summary>

So that rvalue references do not turn into lvalue references. If `iter_reference_t` is `int&&` (for example with `move_iterator<int*>`), its common reference with `const int&&` is `const int&&`, still an rvalue; with `const int&` it would be `const int&`. For an lvalue reference `int&`, both spellings give `const int&`.
</details>

!!! question "Question 2"
    What type is `const_iterator<std::istreambuf_iterator<char>>`?

<details markdown="1">
<summary>Answer</summary>

The reference type of `istreambuf_iterator<char>` is `char` (a prvalue), and `iter_const_reference_t` is also `char`, so it already satisfies *`constant-iterator`*. By [const.iterators.alias] ¶1, the result is therefore `istreambuf_iterator<char>` itself.
</details>
