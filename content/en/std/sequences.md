---
title: Sequence containers
summary: "Subclause 23.3 contains all the concrete sequence containers; this page describes what each one is for, how to choose among them, and the iter-value-type used by the deduction guides."
updated: 2026-10-19
---

!!! tldr
    - Seven headers, `<array>`, `<deque>`, `<forward_list>`, `<hive>`, `<inplace_vector>`, `<list>` and `<vector>`, define all the sequence containers, which all follow the requirements in [[sequence.reqmts]].
    - Use `vector` by default; when element addresses must stay stable, choose among `deque`, `hive` and `list` according to how the sequence grows.
    - `std::vector v(first, last)` can deduce the element type thanks to `iter-value-type` in the deduction guides; write it with braces and you get a `vector` of iterators.

¶1 Seven headers define class templates that meet the sequence container requirements. `array` and `hive` meet them only partially: `array` has a fixed number of elements, and `hive` decides the insertion position itself ([[sequence.reqmts#1]]).

## How to choose

| Container | Header | Characteristics | Notes |
|---|---|---|---|
| `array<T, N>` | `<array>` | Fixed size, an aggregate, a zero-overhead wrapper around a built-in array | [[array]] |
| `vector<T>` | `<vector>` | Contiguous storage, amortized O(1) insertion at the end, the default choice | [[vector]] |
| `vector<bool>` | `<vector>` | A bit-packed partial specialization whose element references are proxy objects | [[vector.bool]] |
| `inplace_vector<T, N>` {{c++26}} | `<inplace_vector>` | A `vector` with fixed capacity and storage inside the object | [[inplace.vector]] |
| `deque<T>` | `<deque>` | O(1) insertion at both ends; insertion at the ends does not invalidate references | [[deque]] |
| `list<T>` | `<list>` | Doubly linked list, O(1) insertion and erasure anywhere, `splice` | [[list]] |
| `forward_list<T>` | `<forward_list>` | Singly linked list with no overhead compared to a hand-written C linked list | [[forward.list]] |
| `hive<T>` {{c++26}} | `<hive>` | Position chosen by the container, O(1) insertion and erasure, stable addresses | [[hive]] |

As a rule of thumb, start with `vector`. When element addresses must stay unchanged across insertions, pick `deque` if the sequence grows only at the ends, `hive` if order does not matter, and `list` if you need insertion at arbitrary positions or `splice` between sequences. Use `inplace_vector` when the size has a small upper bound and you want to avoid dynamic allocation, and `array` when the size is fixed at compile time. For a comparison of the containers' invalidation rules, complexity and exception safety, see [[container.requirements]].

## iter-value-type in the deduction guides (¶2)

```cpp title="ctad-iter.cpp" run ok
#include <list>
#include <type_traits>
#include <vector>

int main() {
  std::list<double> l{1.0, 2.0};
  std::vector v(l.begin(), l.end());
  static_assert(std::is_same_v<decltype(v),
                               std::vector<double>>);
  std::vector w{l.begin(), l.end()};   // braces
  static_assert(std::is_same_v<decltype(w)::value_type,
                               std::list<double>::iterator>);
}
```

¶2 defines an exposition-only alias template `iter-value-type<InputIterator>`, which is `iterator_traits<InputIterator>::value_type`. The deduction guides of the sequence containers use it to deduce the element type from a pair of iterators, so `v` is a `vector<double>`.

`w` uses braces. In list-initialization, class template argument deduction considers initializer-list constructors first, so `w` is deduced as a `vector` holding two iterators.
