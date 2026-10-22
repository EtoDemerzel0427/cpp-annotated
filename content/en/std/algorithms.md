---
title: Algorithms library
summary: "A guide to Clause 26: algorithms touch data only through iterators and ranges; why one algorithm has classic, std::ranges and parallel overloads; which elements to look at when reading an algorithm's wording; and what each page of the clause covers."
updated: 2026-10-19
---

!!! tldr
    - The algorithms of Clause 26 know nothing about containers; they read and write elements only through iterators (or C++20 ranges), so they work just as well on custom data structures.
    - The same algorithm often has several groups of overloads: the classic `std::find`, C++20's `std::ranges::find`, and parallel versions taking an execution policy as the first argument.
    - Classic versions express their requirements in the names of template parameters, and violating them is undefined behavior; `ranges` versions express syntactic requirements as concept constraints, and violating them is a compile error.
    - Each algorithm's wording is laid out as *Constraints*, *Mandates*, *Preconditions*, *Effects*, *Returns*, *Complexity*. The complexity clauses are normative and often decide how many times a predicate is called.

## Several forms of the same algorithm

```cpp run ok
#include <algorithm>
#include <cassert>
#include <vector>
struct P { int id; };
int main() {
  std::vector<int> v{4, 7, 1, 7};
  auto a = std::find(v.begin(), v.end(), 7);  // classic version
  auto b = std::ranges::find(v, 7);           // takes the whole range
  std::vector<P> ps{{1}, {2}};
  auto c = std::ranges::find(ps, 2, &P::id);  // projection: compares p.id
  assert(a == b && c == ps.begin() + 1);
}
```

¶1 Clause 26 describes components for performing algorithmic operations on containers and other sequences. Algorithms never touch containers directly: `find` gets a pair of iterators, or a range, and knows only how to move iterators and read elements. So an algorithm written once works on arrays, `vector`s, linked lists, and any custom structure that provides suitable iterators ([[algorithms.requirements#1]]).

Open the synopsis of `<algorithm>` ([algorithm.syn]) and the same algorithm usually has four to six declarations. Taking `find` as the example:

| Form | Introduced | How requirements are expressed | On violation |
|---|---|---|---|
| `std::find(first, last, v)` | C++98, `constexpr` since C++20 | template parameter name `InputIterator` | {{ub}} |
| `std::find(std::execution::par, first, last, v)` | C++17 | parameter name `ForwardIterator` | {{ub}} |
| `std::ranges::find(first, last, v, proj)`, `std::ranges::find(r, v, proj)` | C++20 | concept constraints such as `input_iterator` | compile error |
| `std::ranges::find(std::execution::par, r, v, proj)` | C++26 | `random_access_iterator` plus `sized_sentinel_for` | compile error |

Some notes:

- The template parameters of the classic versions are unconstrained; names like `InputIterator` and `ForwardIterator` carry normative meaning per [[algorithms.requirements#4]]. Passing an iterator that does not meet the requirements is not guaranteed to be diagnosed.
- The `ranges` versions write their requirements directly as constraints, and do not take part in overload resolution when they are not met. They generally have one extra **projection** ([[g:projection]]) parameter: before comparing or calling the predicate, the projection is applied to each element; `&P::id` above is a projection. They are also not functions but objects, and ADL does not find them; see [[algorithms.requirements]].
- The parallel overloads take an execution policy as the first argument, are not `constexpr`, and have stronger iterator requirements: the classic parallel versions need at least forward iterators, because splitting up the work needs multiple passes; C++26's parallel `ranges` versions ([[P3179R9]]) require the length to be computable in constant time and random access. See [[algorithms.parallel]].

!!! note "Why the `ranges` algorithms are a separate set"
    C++20 Ranges ([[P0896R4]]) did not modify the classic algorithms; it added a new set in `std::ranges`. The classic algorithms require `first` and `last` to have the same type, have no projections, throw away some information they have already computed in their return values (`std::copy` does not return how far the input got), and can express their requirements only in prose. Changing the signatures directly would have broken existing code, so the two sets coexist.

## Map of the clause

¶2 The clause is divided into the groups below, per Table 85. Note that the headers are not all `<algorithm>`:

| Subclause | Header | Contents |
|---|---|---|
| [[algorithms.requirements]] | | conventions for the whole clause: parameter names as requirements, the predicate contract, algorithm function objects |
| [[algorithms.parallel]] | `<execution>` | the semantics of parallel algorithms; execution policies themselves are in [[execpol]] |
| [[algorithms.results]] | `<algorithm>` | return types of `ranges` algorithms, such as `in_out_result` |
| [[alg.nonmodifying]] | `<algorithm>` | `find`, `count`, `equal`, `search`, `fold_left` and others |
| [[alg.modifying.operations]] | `<algorithm>` | `copy`, `transform`, `remove`, `unique`, `rotate`, `shuffle` and others |
| [[alg.sorting]] | `<algorithm>` | sorting, [[alg.binary.search\|binary search]], [[alg.set.operations\|set operations]], [[alg.heap.operations\|heaps]], [[alg.min.max\|minimum and maximum]] |
| [[numeric.ops]] | `<numeric>` | `accumulate`, `reduce`, the various scans |
| [[specialized.algorithms]] | `<memory>` | `uninitialized_copy`, `construct_at`, `destroy` |
| [[alg.rand]] | `<random>` | `ranges::generate_random` |
| [[alg.c.library]] | `<cstdlib>` | `qsort`, `bsearch` |

## Reading an algorithm's wording

Most of the wording in this clause follows the same format ([[structure.specifications]]). It first defines a conditional expression with "Let *E* be …", so that the classic and `ranges` versions, and the versions with and without a predicate, share one description, and then lists in order:

| Element | Consequence of violation | Typical content |
|---|---|---|
| *Constraints* | does not take part in overload resolution | mostly in `ranges` versions |
| *Mandates* | ill-formed, diagnosis required | `Size` is convertible to an integral type; `*first` is writable to `result` |
| *Preconditions* | {{ub}} | ranges are valid, non-overlapping, already sorted; `comp` is a strict weak ordering |
| *Effects*, *Returns* | | what it does, what it returns |
| *Complexity* | the implementation does not conform | exactly N assignments; at most log₂N + O(1) comparisons |
| *Remarks* | | whether it is stable ([[algorithm.stable]]), whether it can operate in place |

The complexity clauses are worth reading closely; they are often observable promises. `std::count` specifies exactly `last - first` applications of the predicate, `std::find` at most that many. So a predicate with side effects is called a definite number of times in `count`, while in `find` the number depends on where the element is found. `adjacent_find` specifies exactly `min((i - first) + 1, (last - first) - 1)` applications, and an implementation may not compare more to go faster.

Note that the `ranges` versions turn only the syntactic requirements into constraints. Semantic requirements, such as whether a comparison function really is a strict weak ordering, cannot be checked by the compiler, and violating them is still undefined behavior.

## Algorithms in freestanding implementations

The first comment in the synopsis is `// mostly freestanding`: freestanding implementations (those without operating system support, see [[intro.compliance]]) must also provide most of the algorithms in this clause. The few algorithms that may need to allocate a temporary buffer, such as `stable_sort`, `stable_partition` and `inplace_merge`, are marked `// hosted` and provided only in hosted implementations.

The parallel overloads are marked `// freestanding-deleted`. Per [[freestanding.item#3]], a freestanding implementation may define such overloads as deleted or provide them as usual, at its choice. Defining them as deleted rather than omitting them ensures that the same call selects the same overload on both kinds of implementation.

## Evolution

| Version | Main changes |
|---|---|
| C++98 | STL algorithms adopted wholesale into the standard; `sort` required only O(N log N) on average |
| C++11 | `sort` required to be O(N log N) in the worst case; added `all_of`/`any_of`/`none_of`, `is_sorted`, `minmax`, `move`, `shuffle` and others |
| C++17 | parallel algorithms and execution policies ([[P0024R2]]); `reduce` and the scan family; `sample`, `clamp` |
| C++20 | most algorithms became `constexpr`; `std::ranges` algorithms ([[P0896R4]]); `shift_left`/`shift_right` |
| C++23 | `ranges::fold_left` and friends, `ranges::contains`, `ranges::starts_with`/`ends_with`, `ranges::find_last` |
| C++26 | `stable_sort` and others became `constexpr` ([[P2562R1]]); value arguments can be written as braced lists ([[P2248R8]]); parallel `ranges` overloads ([[P3179R9]]); algorithm function objects became customization point objects ([[P3136R1]]) |
