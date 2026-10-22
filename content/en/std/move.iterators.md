---
title: move_iterator and move_sentinel
summary: "Dereferencing a move_iterator yields an rvalue reference, so algorithms and constructors that would copy elements move them instead; move_sentinel lets it pair with any sentinel."
updated: 2026-10-19
---

!!! tldr
    - `*it` is equivalent to `ranges::iter_move(current)`, which gives `T&&` for `T*`; calling a copying algorithm or constructor with `move_iterator`s moves the elements.
    - It is at most a random access iterator, never a contiguous one; `operator->` is deprecated.
    - For single-pass input iterators, postfix `++` returns `void`.
    - `move_sentinel<S>` wraps any sentinel into the end of a moving range.
    - Hand it only to algorithms that dereference each element once; if a `copy_if` predicate takes its parameter by value, the elements are moved out during the test.

## Purpose [move.iterators.general]

¶1 `move_iterator` is an iterator adaptor that behaves like its underlying iterator, except that dereferencing yields an rvalue. Many generic algorithms and constructors only ever write `*out = *it`; give them such an iterator and the copy becomes a move. ¶2 is the standard's example:

<div class="compare" markdown="1">

```cpp
list<string> s;
// copies every string
vector<string> v1(s.begin(), s.end());
```

```cpp
// moves every string
vector<string> v2(
  make_move_iterator(s.begin()),
  make_move_iterator(s.end()));
```

</div>

`vector`'s iterator-pair constructor dereferences each element only once, so moving is safe. Move-only types can be transferred this way too, for example moving the elements of a `vector<unique_ptr<int>>` into another `vector`.

## Class definition [move.iterator]

```cpp
template<class Iterator>
class move_iterator {
public:
  using iterator_type     = Iterator;
  using iterator_concept  = see below;
  using iterator_category = see below;  // not always present
  using value_type        = iter_value_t<Iterator>;
  using difference_type   = iter_difference_t<Iterator>;
  using pointer           = Iterator;
  using reference         = iter_rvalue_reference_t<Iterator>;
  // ...
private:
  Iterator current = Iterator();        // exposition only
};
```

`reference` is `iter_rvalue_reference_t<Iterator>`, the result type of `ranges::iter_move(*it)` ([[iterator.cust]]). For `T*` it is `T&&`; for proxy iterators that customize `iter_move` (dereferencing returns a class object that behaves like a reference, such as the iterators of `views::zip`), it is the rvalue form the proxy defines.

The class definition has no `operator->`. It is {{deprecated}} in Annex D, [[depr.move.iter.elem]], and returns `current`. Accessing a member through `->` gives an lvalue, which is inconsistent with dereferencing giving an rvalue.

### The category goes up to random access (¶1–¶2)

¶1 `iterator_concept` checks the underlying iterator for random access, bidirectional and forward in that order, and is input when none of them hold. It is never `contiguous_iterator_tag`, because a contiguous iterator requires its reference to be an lvalue reference ([[iterator.concept.contiguous]]).

¶2 `iterator_category` is declared only when `iterator_traits<Iterator>::iterator_category` is valid. It is `random_access_iterator_tag` when the underlying category derives from `random_access_iterator_tag`, and the underlying category otherwise. In other words, to C++17-style interfaces it still reports random access, so a container constructor can compute the element count first and allocate once.

## Operations

[move.iter.requirements] ¶1 requires `Iterator` to meet the *Cpp17InputIterator* requirements or model `input_iterator`. The bidirectional and random access operations require the corresponding requirements of the underlying iterator only when they are instantiated.

| Operation | Effect | Source |
|---|---|---|
| Default construction | Exists only if the underlying iterator is default-initializable | class definition |
| `explicit move_iterator(Iterator i)` | Initializes `current` with `std::move(i)` | [move.iter.cons] ¶1 |
| Conversion and assignment from `move_iterator<U>` | `U` differs from `Iterator` and is convertible | [move.iter.cons] ¶2–¶6 |
| `base() const&` / `base() &&` | Returns `const Iterator&` / moves out | [move.iter.op.conv] |
| `*it` | `ranges::iter_move(current)` | [move.iter.elem] ¶1 |
| `it[n]` | `ranges::iter_move(current + n)` | [move.iter.elem] ¶2 |
| `++`, `--`, `+`, `+=`, `-`, `-=` | Applied to `current` | [move.iter.nav] |
| `==`, `<`, `<=>`, etc. | Compare `base()`, each with its own constraints | [move.iter.op.comp] |
| `x - y` | `x.base() - y.base()` | [move.iter.nonmember] ¶1 |
| `iter_move`, `iter_swap` | Forward to `ranges::iter_move`, `ranges::iter_swap` | [move.iter.nonmember] ¶4–¶5 |
| `make_move_iterator(i)` | `move_iterator<Iterator>(std::move(i))` | [move.iter.nonmember] ¶6 |

The declarations of postfix increment and decrement deserve a separate look:

```cpp
constexpr void operator++(int);  // [move.iter.nav] ¶3
move_iterator operator++(int)
  requires forward_iterator<Iterator> = default;
move_iterator operator--(int) = default;
```

For single-pass input iterators, postfix `++` returns `void`. After the increment, a copy of the old position is already invalid, so returning it is pointless, and the underlying iterator may be move-only anyway.

For forward and stronger iterators, postfix `++` and `--` are declared `= default`. A defaulted postfix increment is equivalent to copying `*this`, doing the prefix increment, and returning the copy ([[over.inc.default]]).

The comparison operators' constraints are all written as *Constraints*: the corresponding expression such as `x.base() == y.base()` must be well-formed and convertible to `bool`. As with `reverse_iterator`, the synopsis specializes `disable_sized_sentinel_for` for two `move_iterator`s; it is `true` when the underlying iterators do not model `sized_sentinel_for`.

## move_sentinel [move.sentinel]

`move_iterator`'s comparison operators accept only another `move_iterator`. C++20 ranges can use a sentinel of a different type as the end, so a matching sentinel adaptor is needed.

¶1 If `sentinel_for<S, I>` holds, then `sentinel_for<move_sentinel<S>, move_iterator<I>>` holds as well. `move_iterator` has the corresponding hidden friends `==` (requiring `sentinel_for<S, Iterator>`) and `-` (requiring `sized_sentinel_for`).

¶2 The standard uses it with `ranges::copy_if` to write a `move_if`:

```cpp
template<input_iterator I, sentinel_for<I> S,
         weakly_incrementable O,
         indirect_unary_predicate<I> Pred>
  requires indirectly_movable<I, O>
void move_if(I first, S last, O out, Pred pred) {
  ranges::copy_if(move_iterator<I>{std::move(first)},
                  move_sentinel<S>{last},
                  std::move(out), pred);
}
```

`move_sentinel<S>` requires `semiregular<S>` and just stores `S` in a private member `last`. [move.sent.ops] ¶1 the default constructor value-initializes `last`, and it is constexpr when `S` is trivially default constructible; ¶2 explicit construction from `S`; ¶3–¶4 conversion and assignment from `move_sentinel<S2>`; ¶5 `base()` returns `last`.

## Pitfall: dereferencing the same element twice

```cpp run title="move_twice.cpp" ok
#include <algorithm>
#include <cstdio>
#include <iterator>
#include <string>
#include <vector>

int main() {
  std::vector<std::string> src{"apple", "banana", "cherry"};
  std::vector<std::string> dst;
  std::copy_if(std::make_move_iterator(src.begin()),
               std::make_move_iterator(src.end()),
               std::back_inserter(dst),
               [](std::string s) { return s.size() > 5; });
  std::printf("%zu \"%s\" \"%s\"\n",
              dst.size(), dst[0].c_str(), src[1].c_str());
}
```

With libc++ (Clang 23) this prints `2 "" ""`: `dst` has two elements, but both are empty strings. For each element, `copy_if` first calls `pred(*it)` and then does `*out = *it`, dereferencing twice. The predicate takes its parameter by value, so the first dereference already moves the element into the parameter `s`, and the second one moves the moved-from empty string into `dst`.

The program itself has no UB: a moved-from `string` is in a valid but unspecified state ([[lib.types.movedfrom]]). The result is still clearly wrong. Change the lambda's parameter to `const std::string&`, and the first dereference merely binds a reference without moving.

`indirect_unary_predicate` does not catch this mistake. It only requires the predicate to be callable with `iter_reference_t` (here `string&&`) and `iter_value_t&` (`string&`), and a by-value parameter accepts both. So the general rule is: hand `move_iterator`s only to algorithms that guarantee each element is dereferenced once, or make the predicate take `const&`.

## Questions

!!! question "Question"
    When the underlying iterator is `T*`, why can't the `iterator_concept` of `move_iterator<T*>` be `contiguous_iterator_tag` either?

<details markdown="1">
<summary>Answer</summary>

`contiguous_iterator` requires `iter_reference_t` to be an lvalue reference ([[iterator.concept.contiguous]]), while the reference type of `move_iterator<T*>` is `T&&`. From a design point of view, a contiguous iterator lets the library replace it with a pointer (`to_address`); once replaced by a `T*`, dereferencing gives an lvalue, the library would copy instead of move, and the move semantics would be lost.
</details>
