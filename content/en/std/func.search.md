---
title: Searchers
summary: "default_searcher, boyer_moore_searcher and boyer_moore_horspool_searcher take the pattern at construction, search the target sequence when called, and return the matching range; the Boyer–Moore family requires the hash and the equality predicate to agree."
updated: 2026-10-19
---

!!! tldr
    - A searcher is a function object: the pattern to look for is given at construction (preprocessed only once), the sequence to search is given at the call, and it returns the matching range `[i, j)`.
    - Used through `std::search(first, last, searcher)`, you only get the start; calling `searcher(first, last)` directly gives the end as well.
    - `default_searcher` merely wraps `std::search` in the searcher interface; it needs only forward iterators and is `constexpr` and freestanding.
    - The two Boyer–Moore searchers require random access iterators, may allocate memory at construction, and require `hf(A) == hf(B)` whenever `pred(A, B)` is true; violating this is UB and usually shows up as silently finding the wrong thing.

## Usage

```cpp run title="searchers.cpp" ok
#include <functional>
#include <algorithm>
#include <string>
#include <string_view>
#include <cstdio>

int main() {
  std::string text = "the quick brown fox jumps over the lazy dog";
  std::string_view pat = "lazy";

  auto it = std::search(text.begin(), text.end(),
                        std::boyer_moore_searcher(pat.begin(), pat.end()));
  std::printf("%td\n", it - text.begin());                              // 35

  std::boyer_moore_horspool_searcher bmh(pat.begin(), pat.end());
  auto [first, last] = bmh(text.begin(), text.end());                   // called directly
  std::printf("%td %td\n", first - text.begin(), last - text.begin());  // 35 39

  std::default_searcher ds(pat.begin(), pat.end());                     // needs only forward iterators
  std::printf("%td\n", std::search(text.begin(), text.end(), ds) - text.begin());   // 35
}
```

`std::search(first, last, s_first, s_last)` specifies the result but not the algorithm, and implementations generally use naive matching, O(N·M) in the worst case. When the pattern is long, or the same pattern is searched for repeatedly, Boyer–Moore-style algorithms first preprocess the pattern and skip several positions at once on a mismatch, which is much faster on average.

So searchers split a search into two steps. Paragraph 1 of [func.search.general] specifies that the pattern `[pat_first, pat_last)` is given to the constructor and the sequence to be searched, `[first, last)`, to the function call operator. Preprocessing is done at construction, after which the searcher can be called many times.

[[alg.search]] provides a dedicated `std::search` overload for searchers, whose effect is equivalent to `return searcher(first, last).first;`: it just forwards to the searcher and discards the end. When you need the end, call the searcher directly.

In the example above, the pattern's iterators are `string_view::const_iterator` and the target sequence's iterators are `string::iterator`; it does not matter that the two types differ. A searcher's `operator()` is a separate member template that only requires the value types of the two sides to be the same (see below).

## default_searcher ([func.search.default])

```cpp
template<class ForwardIterator1, class BinaryPredicate = equal_to<>>
class default_searcher;
```

¶1–¶2 The constructor stores the two pattern iterators and the predicate, and can only throw exceptions from the copy constructors of the iterators or the predicate.

¶3 `operator()` returns a pair of iterators `i` and `j`: `i` is the result of `search(first, last, pat_first_, pat_last_, pred_)`; if `i == last` then `j == last`, otherwise `j == next(i, distance(pat_first_, pat_last_))`.

It merely wraps `std::search` in the searcher interface, so it requires only forward iterators, its constructor and `operator()` are `constexpr`, and it is freestanding. Its use is to unify the interface: write a generic function that accepts any searcher, and callers can switch algorithms as needed.

## Boyer–Moore searchers ([func.search.bm], [func.search.bmh])

The specifications of `boyer_moore_searcher` and `boyer_moore_horspool_searcher` are identical paragraph by paragraph, differing only in name:

```cpp
template<class RandomAccessIterator1,
         class Hash = hash<typename iterator_traits<RandomAccessIterator1>::value_type>,
         class BinaryPredicate = equal_to<>>
class boyer_moore_searcher;
```

### Why a hash is needed

The Boyer–Moore family of algorithms relies on a bad-character table: for each distinct value occurring in the pattern, it records the position of its last occurrence. On a mismatch, this table is consulted to decide how far to skip. When the value type is a single-byte type like `char`, the table can be a 256-entry array; for general value types, an implementation can only use a hash table, keyed by the values themselves, hashed with `Hash` and compared with `BinaryPredicate`.

For a hash table to work, two keys that compare equal must have the same hash value. Unordered containers have the same requirement on their hash and equality predicate ([[unord.hash]]).

### Constructor (¶1–¶4)

¶1 Preconditions: the value type of the pattern is default-constructible, copy-constructible and copy-assignable, because implementations use it as a table key.

¶2 Let `V` be the value type. For any two values `A` and `B` of type `V`, if `pred(A, B) == true`, then `hf(A) == hf(B)` must be true. This paragraph directly follows the preconditions in ¶1, and violating it is {{ub}}.

The most common way to violate it is to change the predicate but forget the hash:

```cpp run title="hash_pred_consistency.cpp" ub
#include <functional>
#include <algorithm>
#include <cctype>
#include <string>
#include <cstdio>

struct ci_eq {
  bool operator()(char a, char b) const {
    return std::tolower(static_cast<unsigned char>(a)) ==
           std::tolower(static_cast<unsigned char>(b));
  }
};
struct ci_hash {
  std::size_t operator()(char c) const {
    return std::hash<int>{}(std::tolower(static_cast<unsigned char>(c)));
  }
};

int main() {
  std::string text = "Hello WORLD", pat = "world";
  std::boyer_moore_searcher good(pat.begin(), pat.end(), ci_hash{}, ci_eq{});
  std::printf("%td\n", std::search(text.begin(), text.end(), good) - text.begin());  // 6

  std::boyer_moore_searcher bad(pat.begin(), pat.end(), std::hash<char>{}, ci_eq{}); // UB: violates ¶2
  std::printf("%td\n", std::search(text.begin(), text.end(), bad) - text.begin());   // outputs 11 in our tests
}
```

In `bad`, `'w'` and `'W'` compare equal, but `std::hash<char>` gives them different hash values. During table lookup, `'W'` is treated as a character not present in the pattern, the algorithm skips past the real match, and it finally reports that nothing was found. The program does not crash; it just silently gives the wrong answer.

¶3 The constructor stores the pattern iterators, the hash and the predicate. ¶4 It may throw exceptions thrown by the relevant operations of the iterators, the value type, the predicate and the hash, and may also throw `bad_alloc` if allocating the internal data structures fails. That is, constructing a Boyer–Moore searcher allocates memory, so they are neither `constexpr` nor freestanding.

### Function call operator (¶5–¶8)

¶5 Mandates: `RandomAccessIterator1` and `RandomAccessIterator2` have the same value type. Searching a `std::string` for a pattern held in a `std::vector<char>` is fine; searching a `std::u8string` for a pattern held in a `std::string` is ill-formed.

¶7 Returns: `i` is the first position such that every element of the pattern satisfies `pred` with `*(i + n)`, and `j == next(i, pattern length)`. For an empty pattern it returns `make_pair(first, first)`, and if nothing is found it returns `make_pair(last, last)`.

¶8 Complexity: at most (last − first) × (pattern length) applications of the predicate. This is only the worst-case upper bound, the same as naive search. The average sublinear advantage of Boyer–Moore has no testable statement in the standard.

!!! lawyer "A match at the very end"
    The range written in ¶7.1 is the half-open `[first, last - (pat_last_ - pat_first_))`, which, read strictly literally, excludes the position `last - pattern length` where a match lies exactly at the end. This is clearly not the intent. In our tests, searching `"abclazy"` for `"lazy"` with libc++, both searchers return position 3, the match at the end.

## General requirements ([func.search.general])

¶2 Every searcher specialization must meet *Cpp17CopyConstructible* and *Cpp17CopyAssignable*. Template parameters named `ForwardIterator1`, `RandomAccessIterator2`, `BinaryPredicate` and so on have the same requirements as the identically named parameters in the algorithms library ([[algorithms.requirements]]); a parameter named `Hash` must meet *Cpp17Hash* ([[hash.requirements]]).

¶3 says the Boyer–Moore searcher implements the Boyer–Moore algorithm and the Horspool searcher implements the Boyer–Moore–Horspool algorithm, and that in general the former uses more memory and runs faster. The standard cannot define precisely what it means to implement a given algorithm; this paragraph expresses design intent.

!!! impl "The libc++ implementation"
    `default_searcher` calls the internal implementation of `std::search` directly.

    The Boyer–Moore bad-character table comes in two versions: when the value type is a single-byte integral type, `Hash` is exactly `hash<value_type>` and the predicate is exactly `equal_to<>`, it uses `std::array<difference_type, 256>`; otherwise it uses `unordered_map<Key, Value, Hash, BinaryPredicate>`. So as soon as a custom predicate is passed, even just `std::equal_to<char>` rather than `equal_to<>`, the hash table is used, and the consistency requirement of ¶2 really comes into play.

    The table produced by preprocessing is held by a `shared_ptr`, so copies of a searcher share the same table, meeting the copyability requirement without redoing the preprocessing.

## History

!!! history
    Searchers first appeared in the Library Fundamentals TS (`std::experimental`) and were merged into the standard in C++17 by [[P0220R1]]. In the TS, `operator()` returned only the start of the match; [[P0253R1]] changed it to return a pair of iterators, giving the end as well. Since C++20, `default_searcher` is `constexpr`.

## Questions

!!! question "Question"
    To find a subsequence made up of several `std::string`s in a `std::vector<std::string>`, can `boyer_moore_searcher` be used? What needs to be provided?

<details markdown="1">
<summary>Answer</summary>

Yes. `std::string` is default-constructible, copy-constructible and copy-assignable (¶1), `std::hash<std::string>` is an enabled specialization consistent with the default `equal_to<>` (¶2), and `vector`'s iterators are random access. Here each "character" is a whole string, and the bad-character table is a hash table keyed by `std::string`; each comparison is much more expensive than for `char`, but when the pattern is long and there are many distinct strings, it can still skip many positions. If case-insensitive comparison is used instead, a case-insensitive hash must be provided as well.
</details>
