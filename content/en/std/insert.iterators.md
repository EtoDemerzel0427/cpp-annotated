---
title: Insert iterators
summary: "back_insert_iterator, front_insert_iterator and insert_iterator turn writes through an iterator into push_back, push_front and insert, letting copying algorithms work in insert mode."
updated: 2026-10-19
---

!!! tldr
    - Assigning to an insert iterator inserts an element into the container: by calling `push_back`, `push_front` or `insert` respectively; `*` and `++` do nothing and return the iterator itself.
    - An insert iterator holds only a pointer to the container and does not own it; the container must outlive it.
    - After each insertion, `insert_iterator` updates its position with the return value of `insert` and advances one step, so successive insertions keep their original order; for `std::set`, the position is only a hint.
    - `front_inserter` reverses the order of the elements; `back_inserter` does not `reserve` in advance.
    - Since C++20, `difference_type` is `ptrdiff_t`, so insert iterators model `output_iterator` and can be used with `ranges::` algorithms.

```cpp run title="inserters.cpp" ok
#include <algorithm>
#include <cassert>
#include <deque>
#include <iterator>
#include <list>
#include <set>
#include <vector>

// since C++20 insert iterators model output_iterator and can be used with ranges:: algorithms
static_assert(std::output_iterator<std::back_insert_iterator<std::vector<int>>, int>);
static_assert(std::output_iterator<std::insert_iterator<std::set<int>>, int>);

int main() {
    std::vector<int> v{3, 1, 2};

    std::set<int> s;
    std::ranges::copy(v, std::inserter(s, s.end()));      // the position is only a hint
    assert((s == std::set{1, 2, 3}));

    std::deque<int> d;
    std::ranges::copy(v, std::front_inserter(d));         // each goes to the front: order reversed
    assert((d == std::deque{2, 1, 3}));

    std::list<int> l{10, 20};
    std::ranges::copy(v, std::inserter(l, std::next(l.begin())));
    assert((l == std::list{10, 3, 1, 2, 20}));            // original order preserved

    std::vector<int> out;
    std::ranges::transform(v, std::back_inserter(out), [](int x) { return x * x; });
    assert((out == std::vector{9, 1, 4}));
}
```

## Insert mode [insert.iterators.general]

¶1 With ordinary iterators, the following loop overwrites the range starting at `result` with `[first, last)`:

```cpp
while (first != last) *result++ = *first++;
```

If `result` is an **insert iterator** ([[g:insert-iterator]]), the same code inserts the elements into a container. This way all the copying algorithms in the library can work in insert mode, without the destination container having to be `resize`d first.

¶2 An insert iterator is constructed from a container, and `insert_iterator` also needs an iterator indicating where to insert. It meets the output iterator requirements; `operator*` returns the insert iterator itself; assigning to it inserts the value before the position it points to. You can think of it as a cursor parked in the container.

| Class template | Effect of assignment | Helper function | Container needs |
|---|---|---|---|
| `back_insert_iterator<C>` | `container->push_back(value)` | `back_inserter(c)` | `push_back` |
| `front_insert_iterator<C>` | `container->push_front(value)` | `front_inserter(c)` | `push_front` |
| `insert_iterator<C>` | `iter = container->insert(iter, value); ++iter;` | `inserter(c, i)` | `insert(pos, value)` |

## `back_insert_iterator` and `front_insert_iterator` [back.insert.iterator] [front.insert.iterator]

```cpp
template<class Container>
class back_insert_iterator {
protected:
  Container* container;
public:
  using iterator_category = output_iterator_tag;
  using value_type        = void;
  using difference_type   = ptrdiff_t;
  using pointer           = void;
  using reference         = void;
  using container_type    = Container;

  constexpr explicit back_insert_iterator(Container& x);
  constexpr back_insert_iterator& operator=(const typename Container::value_type& value);
  constexpr back_insert_iterator& operator=(typename Container::value_type&& value);
  constexpr back_insert_iterator& operator*();
  constexpr back_insert_iterator& operator++();
  constexpr back_insert_iterator  operator++(int);
};
```

The paragraphs of [back.insert.iter.ops] specify these members:

- ¶1 The constructor initializes `container` with `addressof(x)`. `addressof` is used instead of `&` in case the container type overloads unary `&`. The iterator holds just one pointer, so copying it is cheap, but it does not own the container.
- ¶2–¶5 The two assignment operators call `push_back(value)` and `push_back(std::move(value))` respectively. The parameter type is the container's `value_type`, so writing `*it = "abc"` for a `vector<string>` first constructs a temporary `string` and then moves it in, rather than constructing in place.
- ¶6–¶7 `operator*` and both `operator++` just return `*this`. So `*it = v`, `*it++ = v` and `it = v` have exactly the same effect. `*it` does not give an element, which is also why insert iterators can only be output iterators.

Before C++20, `difference_type` was `void`. Only after it changed to `ptrdiff_t` did insert iterators model `weakly_incrementable`, and hence `output_iterator`, so that they can serve as the output of algorithms like `ranges::copy` ([[iterator.concept.output]]). All members also became `constexpr` in C++20, so they can be used in constant evaluation together with `constexpr` `vector`.

`front_insert_iterator` is completely parallel, except that it calls `push_front`. `vector` has no `push_front`, so assigning through `front_inserter(v)` fails to compile when the assignment operator is instantiated, which is a good thing, since inserting at the front of a `vector` is linear time.

`back_inserter(x)` and `front_inserter(x)` return `back_insert_iterator<Container>(x)` and `front_insert_iterator<Container>(x)` respectively.

## `insert_iterator` [insert.iterator]

```cpp
template<class Container>
class insert_iterator {
protected:
  Container* container;
  ranges::iterator_t<Container> iter;
public:
  // member types as above
  constexpr insert_iterator(Container& x, ranges::iterator_t<Container> i);
  constexpr insert_iterator& operator=(const typename Container::value_type& value);
  constexpr insert_iterator& operator=(typename Container::value_type&& value);
  constexpr insert_iterator& operator*();
  constexpr insert_iterator& operator++();
  constexpr insert_iterator& operator++(int);
};
```

¶2 [insert.iter.ops] specifies the effect of assignment as if by:

```cpp
iter = container->insert(iter, value);
++iter;
```

Neither step can be omitted:

1. Update `iter` with the return value of `insert`. Insertion may invalidate the old `iter`, for example when a `vector` reallocates; `insert` returns a valid iterator to the new element.
2. Then `++iter`, so that the next insertion happens after the element just inserted. That is why successive assignments keep the original order: inserting `3, 1, 2` one after another before the `20` of `{10, 20}` gives `{10, 3, 1, 2, 20}`.

For associative containers, `insert(hint, value)` treats `iter` as a hint; the element's final position is decided by its key, and the updated `iter` is still a valid hint. So `inserter(s, s.end())` is the idiomatic way to put an arbitrary sequence into a `std::set`.

The member `iter` and the position parameter of the helper function `inserter(Container& x, ranges::iterator_t<Container> i)` both have type `ranges::iterator_t<Container>`; before C++20 it was `typename Container::iterator`.

## Common misconceptions

!!! pitfall "`front_inserter` keeps the order"
    Each `push_front` goes to the very front, so copying `{3, 1, 2}` gives `{2, 1, 3}`. To insert at the beginning in the original order, use `inserter(c, c.begin())`.

!!! pitfall "`back_inserter` will `reserve` first"
    An insert iterator cannot see how large the source range is and can only `push_back` one element at a time. When performance matters, call `out.reserve(n)` first, or use the container's range insertion members directly, such as C++23's `append_range` and `insert_range`.

!!! pitfall "An insert iterator outliving its container"
    An insert iterator holds only a raw pointer. Storing `back_inserter(local_vec)` in an object that lives longer than `local_vec` leaves a dangling pointer.

## Questions

!!! question "Question"
    Does `std::back_insert_iterator<std::vector<int>>` model `indirectly_writable<..., long>`? What about `indirectly_writable<..., std::string>`?

<details markdown="1">
<summary>Answer</summary>

For `long`, yes. `long` converts implicitly to `int`, and `*o = long_value` calls `operator=(int&&)` through the conversion. The two `const_cast<const iter_reference_t<Out>&&>(*o)` lines in the concept are no obstacle either ([[iterator.concept.writable]]): `iter_reference_t<Out>` is `back_insert_iterator&`, adding const to a reference type is ignored, after reference collapsing it is still `back_insert_iterator&`, and the non-const assignment operator works as usual.

For `std::string`, no: `string` does not convert to `int`.
</details>
