---
title: ranges::to and constructing containers from ranges (P1206)
summary: C++20 views had no way back to containers, so P1206 added ranges::to plus from_range constructors and *_range members to every standard container. Why it ended up as a free function plus a tag, why the four construction methods are tried in this order, and the later fixes and C++26's reserve_hint.
tags: proposal, ranges, ranges::to, containers, from_range, C++23
group: Library
updated: 2026-10-19
---

!!! tldr
    - C++20 views are often not common ranges (the begin and end types differ), while containers only have an iterator-pair constructor that requires both to have the same type, so `std::vector<int> v(r.begin(), r.end())` often fails to compile.
    - [[P1206R7]] adds two things: the free function `ranges::to<C>(r)` (and the pipe form `r | ranges::to<C>()`), and on every standard container a constructor tagged with `from_range`, plus members such as `insert_range`, `append_range` and `assign_range`.
    - The first idea was to add range-accepting constructors to containers directly; it was abandoned because it conflicts with `initializer_list` constructors and class template argument deduction. The tag gives the same argument a different meaning: `std::vector v{l}` and `std::vector v(std::from_range, l)` deduce different types.
    - `ranges::to` tries, in order: construction from the range, `from_range` construction, iterator-pair construction, and default construction followed by appending elements one by one (reserving first when possible). When the elements are themselves ranges it recurses level by level, so it can produce a `vector<vector<int>>` directly.
    - Later fixes broadened the target types, repaired the recursive branch and switched to `emplace_back` for appending; C++26's [[P2846R6]] lets ranges that can only estimate their length reserve memory too.

## The problem: ranges can't get back into containers

C++20's ranges library can filter, transform and truncate data in a lazy pipeline, but at the end you often need a real container: to store the results, to access them randomly, to pass them to an interface that only accepts `vector`. C++20 didn't provide that last step. The most natural way to write it is the container's iterator-pair constructor:

<div class="compare" markdown="1">

```cpp run std=c++20 error
#include <ranges>
#include <vector>
int main() {
  std::vector<int> src{1, 2, 3, 9, 4};
  auto r = src | std::views::take_while(
      [](int i) { return i < 5; });
  std::vector<int> out(r.begin(), r.end());
  // error: begin and end have different types
}
```

```cpp run ok
#include <ranges>
#include <vector>
int main() {
  std::vector<int> src{1, 2, 3, 9, 4};
  auto out = src
    | std::views::take_while(
        [](int i) { return i < 5; })
    | std::ranges::to<std::vector>();
  return out.size() == 3 ? 0 : 1;
}
```

</div>

Clang 23 reports `no matching constructor` for the left side under `-std=c++20`. The reason is that a C++20 range consists of an iterator and a **sentinel** (an object marking the end, which may have a different type from the iterator). The end of `take_while` is decided by a predicate, so its sentinel is a different type, and such a range is not a [[g:common-range|common range]]. Containers' iterator-pair constructors were written in C++98, and their two arguments must have the same type. The reasoning behind sentinels is in [[topics/ranges-design]].

The Considerations section of [[P1206R7]] tries the workarounds one by one and concludes that none always works:

1. Wrap it in `views::common` first, which wraps the sentinel to have the same type as the iterator. That works for the example above.
2. But `views::common` requires copyable iterators, and C++20 single-pass input iterators may be move-only. The paper uses `std::generator` as an example; libc++ has no `<generator>`, but `std::views::istream<int>(in) | std::views::common` fails to compile the same way. Generators themselves are covered in [[papers/generator]].
3. The only option left is a hand-written loop: default-construct a container, check whether it can `reserve`, then `ranges::copy` into a `back_inserter`.

In the comparison table of [[P1206R7]], the third approach first has to spell out the element type `iter_value_t<iterator_t<decltype(view)>>`, and then write an `if constexpr (sized_range<...>)` before it can reserve memory. The paper also lists four blog posts and Q&A threads discussing this problem, showing it had become a common stumbling block.

## The design space

### Option one: give containers range constructors

[[P1206R0]]'s initial proposal was direct: add a range-accepting constructor to every container, `string`, `span` and `string_view`, so you could write `std::vector<int> vec{lst};` or even `std::vector vec = ranges::iota(42);`.

R0 spent a good deal of space on whether this constructor should be `explicit`. Implicit conversion is the most convenient to write, but creates invisible O(n) copies:

```cpp
void foo(const std::vector<int>&);
std::deque<int> d = /* ... */;
foo(d);   // if implicit conversion were allowed: copies the whole deque on every call
foo(d);   // and copies it again
```

R0's compromise: construction from a container is always `explicit`, while construction from an rvalue view can be implicit, since an rvalue view can only be materialized once and there is no redundant copy to speak of. The paper itself admits this produces odd results; for example, `deque dq = std::move(some_span);` would allow implicit construction and still copy every element.

This option was abandoned in the next revision. [[P1206R1]] gives the reason as the conflict with `initializer_list`:

```cpp
std::vector<int> foo = /* ... */;
std::vector a{foo};   // today: vector<vector<int>>, one element
std::vector b(foo);   // with a range constructor added: vector<int>
```

Brace initialization prefers the **initializer-list constructor** ([[g:initializer-list-constructor|initializer-list constructor]]), and combined with class template argument deduction (CTAD, [[over.match.class.deduct]]), the meaning of `std::vector a{foo}` was long settled: a `vector` with `foo` as its single element. A new constructor would only make the difference between parentheses and braces harder to remember, and it must not change the meaning of existing code.

### Option two: a conversion operator or a member function

Another direction is to make views responsible for the conversion. [[P1206R0]] mentions Abseil's approach: the return value of `absl::StrSplit` has a templated conversion operator `template<Container C> operator C();`, so it can be assigned directly to `vector<string>`, `set<string>` and so on. R0 also mentions that around 2014 someone proposed a member function form like `view.to_container<vector>()`.

Both share the problem that the conversion logic has to be written into every view type. R0's view is that there are far more kinds of views than containers, and converting between containers is useful too, so this is not a general solution. Users' own views would each have to implement it as well.

### Option three: the free function ranges::to

[[P1206R1]] switched to what range-v3 already did: a free function template, called `to_` and later `to` in range-v3. It works with any range and any container (including non-standard ones), with no cooperation needed from either views or containers.

R1 also kept a convenience from range-v3: the pipe form could omit the parentheses, as in `r | ranges::to<std::vector<int>>`. But that only works for complete types. `to<std::vector>` names only a class template; it is the name of a function template, not an object, and letting it sit to the right of `|` without parentheses would need a core language change. R3's revision history records removing the parenthesis-free syntax; today both forms must write `()`.

### A tag: giving the constructor a different meaning

A free function alone is not enough. `ranges::to` can only fill elements through a container's public interface, but the container itself can do better: it can work directly with uninitialized memory, and containers without `reserve` (`deque`, `list`) can still allocate in blocks internally. [[P1206R7]] cites a set of measurements in which, across three scenarios, the tagged range constructor was faster than both the iterator-pair constructor and `reserve` plus element-by-element copying.

So from R3 on, range constructors were added back to containers, but with an empty **tag type** `from_range_t` as the first parameter ([[ranges.syn]]):

```cpp
struct from_range_t { explicit from_range_t() = default; };
inline constexpr from_range_t from_range{};
```

The tag resolves option one's conflict. With the same argument `l`, only the tag means construction from a range, and CTAD deduces a different type accordingly. The paper also points out another ambiguity: for a container whose element type is `std::any`, given a range, should it insert the range itself or each of its elements? That is why the member functions use new names (`insert_range`) rather than adding overloads to `insert`.

```cpp run title="tag.cpp" ok
#include <any>
#include <cstdio>
#include <list>
#include <ranges>
#include <type_traits>
#include <vector>
int main() {
  std::list<int> l{1, 2, 3};
  std::vector a{l};                    // braces: initializer_list wins
  std::vector b(std::from_range, l);   // tag: construct from the range
  static_assert(std::is_same_v<decltype(a), std::vector<std::list<int>>>);
  static_assert(std::is_same_v<decltype(b), std::vector<int>>);

  std::list<std::any> la{1, 2.0, 'c'};
  std::vector<std::any> v;
  v.insert(v.end(), la);               // inserts one any holding the whole list
  v.insert_range(v.end(), la);         // inserts three anys
  std::printf("%zu %zu %zu\n", a.size(), b.size(), v.size());   // 1 3 4
}
```

It prints `1 3 4`. Other examples of tag types in the standard library, and why a `bool` parameter isn't used instead, are in [[patterns/tag-dispatch]].

### Ranges only, no iterator plus sentinel

Almost every `std::ranges` algorithm provides two overloads: one taking a range, one taking an iterator plus a sentinel. The new constructors only take ranges. [[P1206R7]] gives two reasons.

First, a range may know more than an iterator pair. `std::list` is a `sized_range` (`size()` is constant time), but its iterator and sentinel do not satisfy `sized_sentinel_for` and cannot be subtracted. Given the whole `list`, a `vector` can allocate once; given only `list.begin()` and `list.end()`, it has to count first or grow while inserting. When you really only have an iterator and a sentinel, `subrange(it, s)` wraps them into a range.

Second, the tagged constructor is also a protocol: a user container only needs to provide `C(from_range_t, R&&)`, and `ranges::to` will use it. With only one form, the protocol stays simple.

### Both are needed

[[P1206R7]] states explicitly that the two parts complement each other. `ranges::to` supports non-standard containers and containers of containers; tagged constructors give containers a chance to provide more efficient implementations, and serve as the customization point for `ranges::to`. The paper also says that if time ran short the two parts could be split, but `ranges::to` had to make C++23, because it was a key missing piece of the ranges library. When [[P2214R2]] planned the ranges library for C++23, it also listed `ranges::to` at the highest priority.

## The final design

### The four branches of ranges::to

`ranges::to<C>(r, args...)` tries the alternatives in the order of [[range.utility.conv.to#2]]; the extra arguments `args` go at the end of the constructor arguments and are used to pass allocators, comparators, hash functions and so on:

| Paragraph | Condition | Action |
|---|---|---|
| ¶2.1.1 | `C(r, args...)` is valid | Construct directly |
| ¶2.1.2 | `C(from_range, r, args...)` is valid | Tagged construction |
| ¶2.1.3 | `r` is a common range, its iterator has a C++17-style `iterator_category`, and `C(begin, end, args...)` is valid | Iterator-pair construction |
| ¶2.1.4 | `C(args...)` is valid and elements can be appended | Default-construct, reserve if possible, append one by one |

In the first three branches the container constructs itself; in the fourth, `ranges::to` does the work. A type that records how it was constructed shows which branch is chosen:

```cpp run title="order.cpp" ok
#include <cstdio>
#include <ranges>
#include <vector>

template<bool Tagged>
struct Probe {
  using value_type = int;
  std::vector<int> v;
  const char* how = "append";
  Probe() = default;
  template<class R> requires Tagged
  Probe(std::from_range_t, R&& r) : how("from_range") {
    for (int x : r) v.push_back(x);
  }
  template<class It>
  Probe(It f, It l) : v(f, l), how("iterator pair") {}
  void push_back(int x) { v.push_back(x); }
  auto begin() const { return v.begin(); }
  auto end() const { return v.end(); }
};

int main() {
  std::vector<int> src{1, 2, 3, 9, 4};
  auto common = src | std::views::transform([](int i) { return i * 2; });
  auto noncommon = src | std::views::take_while([](int i) { return i < 5; });

  std::printf("%s\n", std::ranges::to<Probe<true>>(common).how);
  std::printf("%s\n", std::ranges::to<Probe<false>>(common).how);
  std::printf("%s\n", std::ranges::to<Probe<false>>(noncommon).how);
}
```

It prints `from_range`, `iterator pair` and `append` in turn. The third line is exactly the situation from the start of this page: the container has no tagged constructor and the range is not a common range, so `ranges::to` falls back to appending one by one and still completes the conversion. The precise meaning of each concept in the conditions, and why ¶2.1.3 checks `iterator_category`, are in [[range.utility.conv]].

This order puts tagged construction before the iterator pair, because tagged construction receives the whole range and has the most information. An issue, [[LWG3958]], suggested going further and moving the reserve-and-append branch before the iterator pair: for a third-party container without a tagged constructor, the iterator pair loses the range's known length. LWG closed it as NAD (not a defect), on the grounds that this would optimize for a rare case at the expense of the common one.

### Reserving and allocation counts

¶2.1.4 is the only branch where `ranges::to` decides the allocation strategy itself. When `r` can give its length and `C` is a *reservable-container* (it has `reserve`, `capacity` and `max_size`, [[range.utility.conv.general#3]]), it calls `reserve` first. Requiring all three members avoids calling functions with the same name but different semantics, such as `unordered_map::reserve`, and lets implementations check that `max_size()` is not exceeded (the reservable-container section of [[P1206R7]]).

Below, the global `operator new` is replaced to count allocations. `Bag` has neither a tagged constructor nor an iterator-pair constructor, so it can only take ¶2.1.4:

```cpp run title="alloc.cpp" ok
#include <cstdio>
#include <cstdlib>
#include <new>
#include <ranges>
#include <sstream>
#include <string>
#include <vector>

static int allocs = 0;
void* operator new(std::size_t n) {
  ++allocs;
  if (void* p = std::malloc(n)) return p;
  throw std::bad_alloc{};
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }

struct Bag {
  using value_type = int;
  std::vector<int> v;
  void reserve(std::size_t n) { v.reserve(n); }
  std::size_t capacity() const { return v.capacity(); }
  std::size_t max_size() const { return v.max_size(); }
  std::size_t size() const { return v.size(); }
  void push_back(int x) { v.push_back(x); }
  auto begin() const { return v.begin(); }
  auto end() const { return v.end(); }
};

template<class F> void count(const char* what, F f) {
  allocs = 0;
  f();
  std::printf("%-28s %d\n", what, allocs);
}

int main() {
  std::vector<int> src(1000, 1);
  int calls = 0;
  auto sized = src | std::views::transform([](int i) { return i + 1; });
  auto unsized = src | std::views::take_while([&](int) { ++calls; return true; });

  count("Bag   <- sized", [&] { auto b = std::ranges::to<Bag>(sized); });
  count("Bag   <- not sized", [&] { auto b = std::ranges::to<Bag>(unsized); });
  count("vector<- sized", [&] { auto v = std::ranges::to<std::vector>(sized); });
  calls = 0;
  count("vector<- forward, not sized", [&] { auto v = std::ranges::to<std::vector>(unsized); });
  std::printf("predicate calls: %d\n", calls);

  std::string text;
  for (int i = 0; i < 1000; ++i) text += "1 ";
  std::istringstream in(text);
  auto input = std::views::istream<int>(in);
  count("vector<- input range", [&] { auto v = std::ranges::to<std::vector>(input); });
}
```

Results with Clang 23 and libc++ at `-O2`:

| Target ← source | Branch taken | Allocations |
|---|---|---|
| `Bag` ← sized `transform` | ¶2.1.4, `reserve(1000)` first | 1 |
| `Bag` ← unsized `take_while` | ¶2.1.4, can't reserve | 11 |
| `vector` ← sized `transform` | ¶2.1.2, tagged construction | 1 |
| `vector` ← unsized `take_while` (forward range) | ¶2.1.2, tagged construction | 1 |
| `vector` ← `istream` (single-pass input range) | ¶2.1.2, tagged construction | 11 |

The fourth row shows the advantage of tagged construction: `vector` itself knows `take_while` is a forward range, so it can count first and allocate once. The cost is that the predicate is called 2000 times instead of 1000, and the range is traversed twice. A single-pass `istream` cannot be counted twice, so it can only grow while reading; 11 allocations is the result of libc++ doubling from 1 to 1024.

### C++26: ranges that can only estimate their length

The 11 allocations and the double traversal in the table above are exactly what [[P2846R6]] sets out to fix. Its example is Unicode uppercasing: `ß` becomes `SS`, so the result is longer than the input, and the transforming view cannot be a `sized_range`; but most characters keep their length, so the input's length is a very good estimate.

P2846R6 adds the customization point object `ranges::reserve_hint` ([[range.prim.size.hint]]) and the concept `approximately_sized_range` ([[range.approximately.sized]]): the former returns `ranges::size` for sized ranges and otherwise calls the range's own `reserve_hint`; the latter means a non-negative estimate can be given in constant time. `sized_range` satisfies it automatically. `take(n)` gives `n` as an estimate even when the underlying range doesn't know its length; views that select by predicate, such as `filter` and `take_while`, provide no estimate, to avoid over-allocating.

¶2.1.4 of `ranges::to` changes accordingly to reserve by estimate:

```cpp
if constexpr (approximately_sized_range<R> && reservable-container<C>)
  c.reserve(static_cast<range_size_t<C>>(ranges::reserve_hint(r)));
```

Containers' tagged constructors get a corresponding recommendation: [[sequence.reqmts#13]] says that if the estimate is not less than the actual length, implementations should not reallocate more than once. libc++ does not implement `reserve_hint` yet and `__cpp_lib_ranges_reserve_hint` is not defined, so the measurements above all reflect C++23 behavior.

### Ranges of ranges

¶2.2 handles the case where the elements are themselves ranges and cannot be converted directly to the target element type: it calls `to<range_value_t<C>>` recursively on each element. This was not in [[P1206R1]] and was added in R3; it is also the capability `ranges::to` has beyond tagged constructors:

```cpp run title="nested.cpp" ok
#include <cstdio>
#include <deque>
#include <forward_list>
#include <list>
#include <ranges>
#include <string>
#include <string_view>
#include <type_traits>
#include <vector>
int main() {
  std::list<std::forward_list<int>> lst{{0, 1, 2, 3}, {4, 5, 6, 7}};

  auto a = std::ranges::to<std::vector<std::vector<int>>>(lst);    // recurses level by level
  auto b = std::ranges::to<std::vector<std::deque<double>>>(lst);  // inner level also changes element type
  auto c = std::ranges::to<std::vector>(lst);                      // only the outer level changes
  static_assert(std::is_same_v<decltype(c), std::vector<std::forward_list<int>>>);

  std::string_view str = "the quick brown fox";
  auto words = std::views::split(str, ' ') | std::ranges::to<std::vector<std::string>>();
  std::printf("%zu %zu %g %zu %s\n", a[1].size(), b.size(), b[1][0], c.size(),
              words[2].c_str());   // 4 2 4 2 brown
}
```

It prints `4 2 4 2 brown`. The outer type of `c` is deduced: `to<std::vector>` names only the class template, CTAD gives `vector<forward_list<int>>`, and the elements can be copied directly, so there is no recursion. The last line is Example 1 of [[range.utility.conv.general#2]]: each element of `split` is a `subrange` of characters, which cannot be converted to `string`, so `to<string>` is called on each piece, which in turn takes `string`'s tagged construction.

The deduction rule used when the element type is omitted (*DEDUCE_EXPR*, [[range.utility.conv.to#4]]) changed between [[P1206R1]] and R2: R1 had planned to automatically drop the `const` on keys when converting a `map` to a `vector`; R2 removed that special case and relies entirely on the containers' deduction guides ([[g:deduction-guide|deduction guide]]).

### New container members

For every member function that used to take a pair of input iterators, [[P1206R7]] added a version taking a range, uniformly named with a `_range` suffix, while constructors uniformly use the `from_range` tag. The requirement is *container-compatible-range*: an input range whose reference type is convertible to the container's element type ([[container.requirements.general#2]]).

```cpp run title="members.cpp" ok
#include <cstdio>
#include <deque>
#include <ranges>
#include <set>
#include <string>
int main() {
  auto r = std::views::iota(1) | std::views::take_while([](int i) { return i <= 3; });

  std::deque<int> d(std::from_range, r);        // 1 2 3
  d.append_range(r);                            // 1 2 3 1 2 3
  d.prepend_range(std::views::iota(7, 9));      // 7 8 1 2 3 1 2 3 (not reversed)
  d.insert_range(d.begin() + 2, r);             // 7 8 1 2 3 1 2 3 1 2 3
  std::set<int> s;
  s.insert_range(d);                            // 1 2 3 7 8
  std::string str;
  str.assign_range(r | std::views::transform([](int i) { return char('a' + i); }));
  str.append_range(std::string_view("!"));

  for (int x : d) std::printf("%d ", x);
  std::printf("| %zu | %s\n", s.size(), str.c_str());
}
```

It prints `7 8 1 2 3 1 2 3 1 2 3 | 5 | bcd!`.

| Member | Containers |
|---|---|
| `C(from_range, rg, ...)` | All sequence containers, associative containers, unordered containers, `string`, container adaptors |
| `insert_range` | Sequence containers (`insert_range_after` for `forward_list`), associative containers, unordered containers, `string` |
| `assign_range` | Sequence containers, `string` |
| `append_range` / `prepend_range` | Sequence containers with `push_back` / `push_front`, and `string` (only `append_range`) |
| `push_range` | `stack`, `queue`, `priority_queue` |
| `replace_with_range` | `string` |

`append_range` and `prepend_range` were requested by SG9 (the ranges study group), originally named `push_back_range` and `push_front_range`; LEWG later asked for the current names. `prepend_range` keeps the elements' original order (Note 2 in [[sequence.reqmts#99]]); [[P1206R7]] reasons that reversing would surprise most people, and reversing would require a bidirectional range, making it much less useful; when you need reversal, write `views::reverse`.

## Wording

The wording of [[P1206R7]] has two parts.

The first part is in the ranges library. [[ranges.syn]] adds `from_range_t` and `from_range`, and four declarations of `to`. The new [[range.utility.conv]] is split into three subclauses: an overview with exposition-only helper concepts (general), the two `to`s taking a range argument (to), and the two `to`s returning a pipe closure (adaptors). The first sentence of the overview sums up the whole design:

!!! std
    The range conversion functions construct an object (usually a container) from a range, by using a constructor taking a range, a `from_range_t` tagged constructor, or a constructor taking a pair of iterators, or by inserting each element of the range into the default-constructed object. ([[range.utility.conv.general#1]])

    The range conversion functions construct an object (usually a container) from a range in one of four ways, corresponding to ¶2.1.1 through ¶2.1.4 in turn.

The pipe form is not an adaptor; it returns a range adaptor closure object ([[g:range-adaptor-closure-object|range adaptor closure object]], [[range.utility.conv.adaptors#2]]), so it can be written to the right of `|` and composed with other closures.

The second part is in the containers library. [[container.requirements.general#2]] adds *container-compatible-range*; the requirement tables of sequence, associative and unordered containers each gain rows such as `X(from_range, rg)` and `insert_range`, for example [[sequence.reqmts#11]] through ¶14; and each container's class synopsis gains the corresponding members and deduction guides. The range parameter of the deduction guides is written as a forwarding reference; R7's revision history says this is to prevent arrays from decaying to pointers.

The paper also adds two feature-test macros: `__cpp_lib_ranges_to_container` for `ranges::to`, and `__cpp_lib_containers_ranges` for the new container members; R7's revision history specifically notes that these are new macros rather than a change to the value of `__cpp_lib_ranges`.

## Consequences

### Later fixes

The wording of `ranges::to` was fixed several times by LWG around the finalization of C++23. Here are the issues that changed today's text:

| Issue | Original wording | Fix |
|---|---|---|
| [[LWG3785]] | The first step checked `convertible_to<range_reference_t<R>, range_value_t<C>>`, so `C` had to be a range | Skip this check when `C` is not an `input_range`, so conversion to types that are not ranges but can be constructed from ranges is possible (C++23) |
| [[LWG3847]] | Only the constraint `!view<C>`, which `to<const std::string_view>` could bypass, returning a possibly dangling view | Adds a *Mandates*: `C` must be a cv-unqualified class type (C++23) |
| [[LWG3733]] | ¶2.1.3 used the *cpp17-input-iterator* concept to check the iterator | Checks instead that `iterator_traits<...>::iterator_category` derives from `input_iterator_tag` (C++23) |
| [[LWG3984]] | The recursive branch wrote `r \| views::transform(...)`, which is ill-formed when `r` is a non-borrowable non-view lvalue (such as an lvalue `owning_view`) | Changed to `ref_view(r) \| views::transform(...)` (C++26) |
| [[LWG4016]] | The append branch used `back_inserter` or `inserter`; the requirements and checks didn't match, and an extra temporary element was constructed | Calls the members directly, preferring `emplace_back` (C++26) |
| [[LWG4121]] | The append branch called `c.emplace(c.end(), x)` for associative containers, whose `emplace` takes no position | Uses `emplace_hint(c.end(), x)` instead (after C++26 was finalized) |

These fixes together with P2846R6 make up today's [[range.utility.conv.to#2]] and [[range.utility.conv.general#4]], ¶5.

### Compatibility and implementation

P1206 only adds new functions and members, and there is no corresponding incompatibility entry in [[diff.cpp20]]. That the new members all carry a `_range` suffix and the constructors all carry a tag is itself designed to avoid changing overload resolution for existing calls.

Clang 23 with libc++: both macros are `202202` under `-std=c++23` and `-std=c++2c`, and both are undefined under `-std=c++20`. All the examples above pass `-Wall -Wextra -pedantic` under `-std=c++2c`, and `alloc.cpp` runs under ASan and UBSan with no reports. libc++'s append branch already prefers `emplace_back` per [[LWG4016]]; for a custom container with only `emplace_hint` and `insert`, it calls `insert`, not yet following [[LWG4121]]. `reserve_hint` is not implemented yet.

## Questions

!!! question "1. What is the difference between `std::vector<int> v(std::from_range, r)` and `auto v = r | std::ranges::to<std::vector<int>>()`?"

<details markdown="1">
<summary>Answer</summary>

For `vector` and a range whose elements convert directly, there is none: `ranges::to` reaches ¶2.1.2 per [[range.utility.conv.to#2]] and calls exactly this tagged constructor (assuming ¶2.1.1 doesn't apply; `vector<int>` has no untagged range constructor).

The differences are in other cases. `ranges::to` works with non-standard containers that have no tagged constructor (falling back to the iterator pair or appending), handles ranges of ranges recursively, allows the element type to be omitted as `to<std::vector>()`, and can sit at the end of a pipeline. The tagged constructor is the container's own interface, and also the entry point `ranges::to` uses to reach a more efficient implementation.
</details>

!!! question "2. Why can't `std::vector v{lst};` be understood as construction from a range, the way `std::string s{sv};` is?"

<details markdown="1">
<summary>Answer</summary>

`vector` has an `initializer_list<T>` constructor, which brace initialization considers first; CTAD deduces `T = list<int>` from the type of `lst`, giving a `vector<list<int>>` with one element. This meaning has been fixed since C++17, and [[P1206R1]] abandoned the untagged range constructor precisely because it would conflict with this rule. Construction from a range is written `std::vector v(std::from_range, lst);`.
</details>

!!! question "3. Does `std::ranges::to<std::unordered_set<int>>(v)` call `unordered_set::reserve` first?"

<details markdown="1">
<summary>Answer</summary>

No. First, `unordered_set` has a `from_range` tagged constructor, so `ranges::to` stops at ¶2.1.2 and never reaches the reserve-and-append ¶2.1.4; reserving buckets is up to the container's constructor. Second, even an unordered container without a tagged constructor but with `reserve` has no `capacity()`, so it is not a *reservable-container* ([[range.utility.conv.general#3]]) and the `if constexpr` condition is false. [[P1206R7]] requires all three members to be present precisely to avoid a `reserve` like the unordered containers', with the same name but different semantics (reserving buckets rather than element space).
</details>
