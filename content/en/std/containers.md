---
title: Containers library
summary: "A guide to Chapter 23: container requirements, sequence containers, associative containers, unordered containers, container adaptors and views; a container's contract is read along four lines: complexity, iterator invalidation, exception safety and allocators."
updated: 2026-10-19
---

!!! tldr
    - The clauses for the individual containers are short; most of the semantics live in the groups of general requirements in [[container.requirements]]. To read a container, take the general requirements and that container's own additional clauses together.
    - A container's contract falls into four categories: complexity, when iterators and references are invalidated, exception-safety guarantees, and how the allocator is used.
    - Container function preconditions come in several strengths: an unmet *Constraints* makes the overload non-viable, an unmet *Mandates* is a compile error, a violated *Preconditions* is UB, and a violated C++26 hardened precondition terminates the program in a hardened implementation.
    - `basic_string`, `bitset` and `valarray` are not in this chapter, but `basic_string` meets this chapter's container requirements.

## What the chapter contains ([containers.general])

¶1 This chapter describes components that programs use to organize collections of information. Table 74 in ¶2 lists its six parts:

| Subclause | Contents | Headers | Notes on this site |
|---|---|---|---|
| [container.requirements] | Requirements for general, allocator-aware, sequence, associative and unordered containers; node handles | none | [[container.requirements]], [[container.requirements.general]], [[sequence.reqmts]], [[container.node]], [[associative.reqmts]], [[unord.req]] |
| [sequences] | Sequence containers | `<array>` `<deque>` `<forward_list>` `<hive>` `<inplace_vector>` `<list>` `<vector>` | [[sequences]], [[array]], [[deque]], [[forward.list]], [[hive]], [[list]], [[vector]], [[vector.bool]], [[inplace.vector]] |
| [associative] | Ordered associative containers | `<map>` `<set>` | [[associative]] |
| [unord] | Unordered associative containers | `<unordered_map>` `<unordered_set>` | [[unord]] |
| [container.adaptors] | Container adaptors | `<queue>` `<stack>` `<flat_map>` `<flat_set>` | [[container.adaptors]], [[flat.map]], [[flat.set]] |
| [views] | Views | `<span>` `<mdspan>` | [[views]], [[views.contiguous]], [[views.multidim]] |

Several types often thought of as containers are not in this chapter: `basic_string` is in Chapter 27 ([[basic.string]]) but meets this chapter's contiguous-container and allocator-aware-container requirements; `bitset` is in Chapter 22; `valarray` is in Chapter 29; `basic_stacktrace` is in Chapter 19 and meets the allocator-aware container requirements. Iterator concepts and range adaptors are in Chapters 24 and 25 ([[iterators]], [[ranges]]).

## Four aspects of a container contract

Nearly every rule for a specific container belongs to one of the four categories below, and the container pages on this site are organized along them:

1. **Complexity**. The standard counts only operations on elements ([[container.requirements]]), but these requirements effectively dictate the data structure: `vector` must grow geometrically, `deque` must be built from blocks, `unordered_map` must have one node per element.
2. **Invalidation**. Which operations make which iterators, pointers and references stop being valid. The general principle is that nothing is invalidated unless it is specified to be ([[container.reqmts#67]]).
3. **Exception safety**. By default, a single-element insertion that throws has no effect and erasure does not throw ([[container.reqmts#66]]); `vector`, `deque`, the associative containers and the unordered containers each have exceptions.
4. **Allocators**. Elements may be constructed and destroyed only through `allocator_traits::construct` and `destroy`; how the allocator is propagated on copy, move, assignment and swap is decided by the three propagate traits ([[container.requirements.general]]). The allocator protocol itself is in [[mem]] and [[allocator.traits]].

[[container.requirements]] collects each container's rules on the last three aspects into comparison tables.

## Strengths of preconditions

The function descriptions in this chapter use the elements defined in [[structure.specifications]], and violating each has a different consequence:

| Element | Example | Consequence of violation |
|---|---|---|
| *Constraints* | `insert(InputIterator, InputIterator)` requires the arguments to qualify as input iterators; `container-compatible-range` | Does not participate in overload resolution |
| *Mandates* | `vector<T, A>` requires `A::value_type` to be `T` | Ill-formed, diagnostic required |
| *Preconditions* | in `insert(p, i, j)`, `i` and `j` are not iterators into the container itself; the element type is *Cpp17CopyInsertable* | {{ub}}; an unmet type requirement usually shows up as an instantiation error |
| *Hardened preconditions* {{c++26}} | `front()`, `back()`, `pop_*` and `operator[]` require non-empty and in-bounds | Terminates the program in a hardened implementation, UB otherwise |

## History and evolution

| Version | Main changes to this chapter |
|---|---|
| C++98 | The STL enters the standard: `vector`, `deque`, `list`, `set`, `map` and their multi versions, `stack`, `queue`, `priority_queue`, `vector<bool>` |
| C++11 | `array`, `forward_list`, `unordered_*`; move semantics and `emplace`; `allocator_traits`; `size()` must be constant time; `initializer_list` constructors |
| C++14 | Heterogeneous lookup in associative containers (transparent comparators) |
| C++17 | Node handles, `extract`, `merge`; `try_emplace`, `insert_or_assign`; `std::pmr` aliases; `vector`, `list` and `forward_list` allow incomplete element types |
| C++20 | `std::erase`, `erase_if`; `contains`; `constexpr` `vector`; `<=>`; `span`; heterogeneous lookup in unordered containers |
| C++23 | `flat_map`, `flat_set`; `mdspan`; `from_range` constructors and `*_range` member functions; iterator-pair constructors for `stack` and `queue` |
| C++26 | `inplace_vector`, `hive`; standard library hardening; `deque`, `list`, `forward_list`, the associative containers, the unordered containers and the container adaptors usable in constant evaluation; heterogeneous insertion into associative containers; `span::at`; `submdspan` |

libc++ in Clang 23 supports the C++26 parts only partially. `constexpr` for `list`, `forward_list`, `map`, `set`, `flat_map`, `flat_set` and `queue` is implemented (the corresponding `__cpp_lib_constexpr_*` macros are `202502L`), but not for `deque`; `<inplace_vector>` and `<hive>` are not provided yet; heterogeneous insertion into associative containers is not implemented either.

```cpp title="constexpr-containers.cpp" run ok
#include <list>
#include <map>
#include <vector>

constexpr int sum() {
  std::list<int> l{1, 2, 3};
  std::map<int, int> m{{1, 10}, {2, 20}};
  std::vector<int> v(l.begin(), l.end());
  int s = 0;
  for (int x : v) s += x;
  return s + m.at(2);
}
static_assert(sum() == 26);
int main() {}
```
