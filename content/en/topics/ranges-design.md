---
title: The design of Ranges
summary: "The core design decisions of the ranges library: iterator plus sentinel, the concept hierarchy, the distinction between views and containers, lazy evaluation, begin() caching, borrowing and dangling, pipelines, ranges::to and projections, and the consequences and common pitfalls each brings."
tags: standard library, ranges, views, lazy evaluation, dangling, topic
updated: 2026-10-19
---

!!! tldr
    - A range is an iterator plus a sentinel. The sentinel may be of a different type, so null-terminated strings, infinite sequences and "the first n" don't need their end computed up front.
    - Adaptors derive their capabilities from which concepts the underlying range satisfies: `transform` keeps random access and size, while `filter` drops to bidirectional and loses size. Algorithms use the same concepts to decide what they accept.
    - Views are lazy: building a pipeline computes nothing, and functions are called on each dereference. `transform | filter` calls the transform function one extra time for each element that passes.
    - `filter`, `drop`, `reverse` and others cache results so that `begin()` is amortized constant time; the cost is that const views can't be iterated, and after the underlying range is modified a view may give stale results or even undefined behavior.
    - Views usually don't own their elements. Algorithms return `ranges::dangling` for non-borrowed rvalue ranges, and C++23 extended the lifetime of temporaries in range-based `for` initializers; other dangling has to be avoided by the programmer.

## From iterator pairs to pipelines

Code that sorts an order book by quantity in descending order and extracts the big orders, written with iterator pairs and with ranges:

<div class="compare" markdown="1">

```cpp
std::sort(book.begin(), book.end(),
  [](const Order& a, const Order& b) {
    return a.qty > b.qty;
  });
std::vector<std::string> names;
for (auto it = book.begin();
     it != book.end(); ++it)
  if (is_big(*it))
    names.push_back(it->sym);
```

```cpp
std::ranges::sort(book,
                  std::ranges::greater{},
                  &Order::qty);
auto names = book
  | std::views::filter(is_big)
  | std::views::transform(&Order::sym)
  | std::ranges::to<std::vector>();
```

</div>

The right side changes three things. The algorithm accepts the whole range directly, so iterators from two containers can't be mismatched. The comparator becomes `greater` plus a **projection** `&Order::qty`, meaning take `qty` first, then compare. The loop in the middle becomes a pipeline in which neither `filter` nor `transform` copies elements, and only at the end does `ranges::to` collect them into a `vector`.

The same style sometimes fails to compile unexpectedly:

```cpp run error
#include <cstdio>
#include <ranges>
#include <vector>
void print(const auto& r) {
  for (int x : r) std::printf("%d ", x);
  std::puts("");
}
int main() {
  std::vector<int> v{1, 2, 3, 4, 5, 6};
  print(v | std::views::transform([](int x) { return x * 10; }));  // OK
  print(v | std::views::filter([](int x) { return x % 2 == 0; })); // error
}
```

Clang 23 reports that `filter_view`'s `begin` "is not marked const". The result of `transform` can be iterated as const; the result of `filter` can't.

And sometimes it compiles but dangles:

```cpp run ub
#include <cstdio>
#include <ranges>
#include <string>
#include <vector>
struct Config {
  std::vector<std::string> keys{"listen_port", "log_level", "worker_threads"};
  const std::vector<std::string>& items() const { return keys; }
};
Config load() { return {}; }
int main() {
  auto lens = load().items()
            | std::views::transform([](const std::string& s) { return s.size(); });
  for (std::size_t n : lens) std::printf("%zu ", n);   // UB: the Config has been destroyed
  std::puts("");
}
```

Clang 23 gives no warning at all, and with `-fsanitize=address` the run reports stack-use-after-scope inside `ref_view::begin`.

Neither phenomenon is an implementation bug; both are direct consequences of a few design decisions in the ranges library. The sections below go through these decisions one at a time.

## A range is an iterator plus a sentinel

The `range` concept only requires that `ranges::begin` and `ranges::end` can be called on an lvalue ([[range.range#1]]). `begin` gives an iterator and `end` gives a **sentinel**. A sentinel only needs to be comparable for equality with the iterator; its type may differ ([[iterator.concept.sentinel]]).

Why not require the beginning and end to have the same type, as in C++98? Because for many sequences the end isn't a position but a condition:

```cpp run ok
#include <algorithm>
#include <cstdio>
#include <iterator>
#include <numeric>
#include <ranges>

struct null_sentinel {   // the end: reaching '\0'
  friend bool operator==(const char* p, null_sentinel) { return *p == '\0'; }
};

int main(int argc, char** argv) {
  const char* s = argc > 1 ? argv[1] : "hello, ranges";
  auto str = std::ranges::subrange(s, null_sentinel{});   // no strlen first
  auto comma = std::ranges::find(str, ',');
  std::printf("%td\n", comma - s);                        // 5

  static_assert(!std::ranges::common_range<decltype(str)>);
  static_assert(!std::ranges::sized_range<decltype(str)>);

  auto c = str | std::views::common;                      // for old interfaces
  long n = std::accumulate(c.begin(), c.end(), 0L);
  // std::accumulate(str.begin(), str.end(), 0L);         // error: begin and end have different types
  std::printf("%ld\n", n);
}
```

Each step of `find` compares with `null_sentinel` once, that is, checks `*p == '\0'` once, and traverses only once. If the beginning and end had to be the same type, you'd have to `strlen` first and then search, traversing twice. Similar examples in the standard library are the unbounded `views::iota(0)` (whose end is `unreachable_sentinel_t`, equal to nothing), `take_while` (whose end holds the predicate), and `views::istream` (whose end is `default_sentinel_t`, checking the stream's state on comparison).

The cost is that there are now two kinds of range. Those whose iterator and sentinel have the same type are called a [[g:common-range|common range]] ([[range.refinements#4]]); all standard containers are. Those that differ are not. Old interfaces that accept only one type, such as `std::accumulate` and containers' iterator-pair constructors, need a conversion with `views::common` first ([[range.common]]). The language side prepared for this in C++17: [[P0184R0]] declared the `begin` and `end` of range-based `for` with separate `auto`s ([[stmt.ranged#1]]), and since then range-based `for` can iterate non-common ranges directly.

Algorithms changed their return values as a result. When the end is a condition, the iterator obtained by reaching the end is new information the algorithm has computed, so `ranges::` algorithms return it where possible; for example `ranges::copy` returns iterators at both the input and output ends. Every overload that accepts a range behaves as if it first took `ranges::begin(r)` and `ranges::end(r)` and then called the iterator-plus-sentinel version ([[algorithms.requirements#14]]).

## The concept hierarchy: capabilities decide behavior

The capabilities of a range are described by a set of concepts, defined in detail in [[range.req]]:

| Dimension | Concepts | What it asks |
|---|---|---|
| Traversal | `input_range` → `forward_range` → `bidirectional_range` → `random_access_range` → `contiguous_range` | How the iterator can move; whether multiple passes are possible; whether elements are in contiguous memory |
| Size | `sized_range` | Whether the number of elements can be obtained in constant time ([[range.sized#2]]) |
| End | `common_range` | Whether the sentinel and iterator have the same type |
| Cost | `view` | Whether move is O(1) and copy cheap (next section) |
| Lifetime | `borrowed_range` | Whether iterators don't depend on the range object itself staying alive |
| Pipeline-ready | `viewable_range` | Whether it can be safely converted to a view with `views::all` |

Adaptors read these properties of the underlying range to compute their own; algorithms read them to decide what to accept and which implementation to use. Checking each one on Clang 23:

```cpp run ok
#include <algorithm>
#include <list>
#include <ranges>
#include <span>
#include <sstream>
#include <vector>
namespace r = std::ranges;
namespace vw = std::views;
using V = std::vector<int>;
inline V v;
inline std::list<int> l;
constexpr auto sq = [](int x) { return x * x; };
constexpr auto ev = [](int x) { return x % 2 == 0; };

using T = decltype(v | vw::transform(sq));       // one-to-one: keeps random access, size, common
static_assert(r::random_access_range<T> && r::sized_range<T> && r::common_range<T>);
static_assert(!r::contiguous_range<T>);           // elements are computed, not in memory

using F = decltype(v | vw::filter(ev));           // skips ahead: bidirectional at most, no size
static_assert(r::bidirectional_range<F> && !r::random_access_range<F>);
static_assert(!r::sized_range<F> && r::common_range<F>);

using TV = decltype(v | vw::take(3));             // underlying random access with size: end can be computed
static_assert(r::contiguous_range<TV> && r::sized_range<TV> && r::common_range<TV>);
using TL = decltype(l | vw::take(3));             // list: the end has to be counted out, becomes non-common
static_assert(r::sized_range<TL> && !r::common_range<TL>);

using TW = decltype(v | vw::take_while(ev));      // the end is a condition
static_assert(r::contiguous_range<TW> && !r::sized_range<TW> && !r::common_range<TW>);

static_assert(std::same_as<decltype(std::span(v) | vw::take(3)), std::span<int>>);

template<class R> concept sortable_r = requires(R&& x) { r::sort(x); };
static_assert(sortable_r<V&> && !sortable_r<F&> && !sortable_r<std::list<int>&>);
using IS = decltype(vw::istream<int>(std::declval<std::istream&>()));
static_assert(r::input_range<IS> && !r::forward_range<IS>);
template<class R> concept reversible = requires(R&& x) { x | vw::reverse; };
static_assert(reversible<F&> && !reversible<IS&>);
int main() {}
```

Some results worth noting:

- `views::take(3)` applied to a `span` returns a shorter `span` directly, rather than wrapping it in a `take_view` ([[range.take]]). Adaptors keep the original type when they can.
- The same `take(3)` is a common range when applied to a `vector` but not when applied to a `list`: a `list` can't compute the end iterator without walking to the 3rd element, so `take_view` has to use a counted iterator and a sentinel.
- `ranges::sort` requires random access, so it can't sort the result of `filter`, nor a `list`. `views::reverse` requires bidirectional, so it can't reverse an `istream`. These errors all happen at concept checking, and the diagnostic points out which constraint isn't satisfied (the general mechanism of concepts is in [[topics/concepts]]).

## Views and containers

An adaptor stores its underlying range by value. If `filter` stored a copy of the `vector`, every stage of the pipeline would copy all the elements, and lazy evaluation would be pointless. So an adaptor's underlying range must be a [[g:range-view|view]]: moving is O(1), copying (when copyable) is O(1), and destroying N copies costs O(N+M) in total, where M is the number of elements ([[range.view#2]]).

These requirements are only about cost, not ownership. `span` and `string_view` don't own their elements, while `owning_view` owns a container moved into it; both are views. `vector` is not, because copying it copies all its elements. The difference can't be seen syntactically, so a type has to declare itself a view, by inheriting from `view_interface` or specializing `enable_view` ([[range.view]]).

When a container enters a pipeline, `views::all` decides how it enters ([[range.all.general#2]]):

| Form | Underlying | Who owns the elements |
|---|---|---|
| `v \| views::filter(p)`, `v` an lvalue | `ref_view<V>`: stores only a pointer | `v` |
| `std::move(v) \| views::filter(p)` or `make_vec() \| views::filter(p)` | `owning_view<V>`: the container is moved in, move-only | The view |
| `ev \| views::reverse`, `ev` itself a view | A copy of `ev` | Same as `ev` |

The opening `Config` example dangles because of the first row: `load().items()` is an lvalue expression, `views::all` chose `ref_view`, and it remembered only a pointer to the `vector` inside the temporary `Config`. Whether the expression is an lvalue or an rvalue decides between borrowing and taking over, regardless of how long the object actually lives. Details of `ref_view` and `owning_view` are in [[range.all]].

## Lazy evaluation and the cost model

Building a pipeline accesses no elements; elements are computed one by one during iteration: a `transform` iterator calls the function each time it is dereferenced ([[range.transform]]), and a `filter` iterator calls the predicate on each element it passes over as it advances ([[range.filter]]). So the cost depends on how downstream code uses the iterators, not on how the pipeline is written. Below it is measured with two functions that count their calls:

```cpp run ok
#include <algorithm>
#include <cstdio>
#include <ranges>
#include <vector>
int f_calls = 0, p_calls = 0;
int sq(int x) { ++f_calls; return x * x; }
bool even(int x) { ++p_calls; return x % 2 == 0; }
void report(const char* what) {
  std::printf("%-28s f=%d p=%d\n", what, f_calls, p_calls);
  f_calls = p_calls = 0;
}
int main() {
  std::vector<int> v{1, 2, 3, 4, 5, 6, 7, 8, 9, 10};
  namespace vw = std::views;

  auto a = v | vw::transform(sq);
  report("build transform");
  for (int x : a) (void)x;
  report("iterate transform");

  for (int x : v | vw::transform(sq) | vw::take(3)) (void)x;
  report("transform|take(3)");

  for (int x : v | vw::filter(even) | vw::transform(sq) | vw::take(3)) (void)x;
  report("filter|transform|take(3)");

  for (int x : v | vw::transform(sq) | vw::filter(even)) (void)x;
  report("transform|filter");

  auto t = v | vw::transform(sq);
  auto m = std::ranges::max_element(t);
  (void)*m;
  report("max_element(transform)");
  (void)std::ranges::max_element(v, {}, sq);
  report("max_element(v, {}, sq)");

  auto ev = v | vw::filter(even);
  for (int x : ev) (void)x;
  report("filter 1st pass");
  for (int x : ev) (void)x;
  report("filter 2nd pass");
  for (int x : ev | vw::reverse) (void)x;
  report("filter|reverse");
  (void)std::ranges::distance(ev);
  report("distance(filter)");
}
```

```text
build transform              f=0 p=0
iterate transform            f=10 p=0
transform|take(3)            f=3 p=0
filter|transform|take(3)     f=3 p=8
transform|filter             f=15 p=10
max_element(transform)       f=19 p=0
max_element(v, {}, sq)       f=18 p=0
filter 1st pass              f=0 p=10
filter 2nd pass              f=0 p=8
filter|reverse               f=0 p=20
distance(filter)             f=0 p=8
```

Line by line:

- Building computes nothing, and `take` means later elements are never computed at all. A 10-element `transform` plus `take(3)` calls `sq` only 3 times.
- A `filter` before `take` searches one step further. In `filter | transform | take(3)` the predicate is called 8 times, not 6. After handling the 3rd element, range-based `for` still executes `++`; `take_view`'s counted iterator advances the underlying iterator first and then decrements the count to 0, so the underlying `filter` goes on to check 7 and 8. When the underlying range is an input range, this step really reads one more value from the stream (see the last section).
- `transform | filter` calls the function twice for elements that pass. 10 + 5 = 15: one dereference when the predicate tests it, another when the loop body reads it. `transform_view` doesn't store computed values; that's the price of laziness. Fix it by swapping the order, or with C++26's `views::cache_latest` ([[range.cache.latest]], not yet implemented in libc++ in our tests).
- Algorithms dereference repeatedly. `max_element` dereferences two iterators per comparison: 9 comparisons make 18 calls, and the final `*m` one more, 19 in total. Using a projection instead also gives 18: projection results aren't cached, and every comparison recomputes them. When the transformation is expensive, store the results in a container first.
- The second pass is cheaper, and gets expensive again after a copy. The first pass of `filter` checks all 10 elements, the second only 8, because the position of `begin()` was cached. In `ev | vw::reverse`, `ev` is an lvalue view, `views::all` copies it, and the copy has no cache, so it has to find `begin()` again (2 calls); each dereference of a `reverse_iterator` first steps a copy of the underlying iterator back, so each element is checked twice (18 calls), 20 in total. The last line, `ranges::distance(ev)`, acts on the lvalue `ev` and uses the cached start, again 8 calls.

!!! pitfall "Counters make bad predicates"
    `sq` and `even` above modify global variables only to count calls. Adaptors require functions and predicates to be **equality-preserving** (equal inputs give equal outputs, [[concepts.equality]]); these two only happen to satisfy that because they don't depend on the counters' values. In real code, a function that factors a counter's value into its result makes the result of `filter` unpredictable.

## Caching begin()

The semantics of `range` require `ranges::begin` to be amortized constant time ([[range.range#2]]). The first element of a `filter_view` can only be determined by a linear search, so the standard says it caches the result in the view object on the first call to `begin()` ([[range.filter.view#5]], [[g:begin-caching]]). `drop_view`, `drop_while_view`, `reverse_view`, `split_view` and `chunk_by_view` do the same under certain conditions. This decision has three consequences.

First, `begin()` has to write the cache, so it isn't a const member. When the underlying range is a forward range, a const `filter_view` is not a `range`, which is why the opening `print(const auto&)` fails to compile. Why not use a `mutable` member? Then two threads calling the const `begin()` at the same time would have a data race, violating the standard library's convention for const member functions ([[res.on.data.races]]). When a generic function accepts a view, write the parameter as `auto&&`, or as `std::ranges::view auto` by value, not `const auto&`.

Second, the cache doesn't propagate on copy. A copy of a `filter_view` searches again ([[range.nonprop.cache]]); that's where the 2 extra calls for `filter|reverse` in the previous section came from.

Third, the cache can go stale. If the underlying container is modified after the first iteration, the position the view remembered isn't updated:

<div class="compare" markdown="1">

```cpp
auto ev = v | views::filter(even);
for (int x : ev) use(x);
v.push_back(6);   // reallocates
for (int x : ev) use(x);
// UB: the cached iterator
// points into the freed old buffer
```

```cpp
auto sq = v | views::transform(f);
for (int x : sq) use(x);
v.push_back(5);   // reallocates
for (int x : sq) use(x);
// OK: transform doesn't cache;
// every begin() gets v.begin() afresh
```

</div>

```cpp run ub
#include <cstdio>
#include <ranges>
#include <vector>
int main() {
  std::vector<int> v{1, 2, 3, 4};
  auto ev = v | std::views::filter([](int x) { return x % 2 == 0; });
  for (int x : ev) std::printf("%d ", x);   // 2 4: begin() is now cached
  v.push_back(6);                           // not enough capacity, reallocates
  for (int x : ev) std::printf("%d ", x);   // UB: the cached iterator points into the old buffer
  std::puts("");
}
```

ASan reports heap-use-after-free on line 9. Modifications that don't reallocate aren't UB, but the result may be stale: after `v[0]` is changed to an even number, `ev` still starts from the cached position. If an element is modified through a `filter` iterator so that it no longer satisfies the predicate, a note in the standard says more explicitly that this may lead to undefined behavior. These examples are in [[range.filter]].

The practical rule: use a view soon after creating it and then discard it; when the underlying range may change, create the view again.

## Dangling and borrowed ranges

Most views don't own their elements, so they dangle if they outlive the underlying range. The standard blocks some of this at the type level.

### Algorithms return `ranges::dangling`

```cpp run ok
#include <algorithm>
#include <ranges>
#include <vector>
int main() {
  std::vector<int> v{3, -7, 5};
  auto mag = [](int x) { return x < 0 ? -x : x; };

  auto it = std::ranges::max_element(v | std::views::transform(mag));
  static_assert(std::same_as<decltype(it), std::ranges::dangling>);
  // int m = *it;                 // error: dangling can't be dereferenced

  auto t = v | std::views::transform(mag);
  int m1 = *std::ranges::max_element(t);              // lvalue: a real iterator
  int m2 = std::ranges::max(v | std::views::transform(mag));   // only the value is needed
  int m3 = *std::ranges::max_element(v, {}, mag);     // projection: the iterator points into v
  return (m1 == 7 && m2 == 7 && m3 == -7) ? 0 : 1;
}
```

When an algorithm that returns an iterator receives an rvalue range that isn't a [[g:borrowed-range|borrowed range]] (one whose iterators don't depend on the range object itself staying alive), the return type becomes `ranges::dangling` ([[range.dangling#1]]). It supports no operations, so code that uses the result doesn't compile.

The first line is surprising: `v` is clearly still alive. But a `transform_view` iterator holds a pointer to the view object, to use the function inside it, and this view is a temporary destroyed at the semicolon. So `transform_view` isn't a borrowed range, and `dangling` blocks a real dangling iterator. The last line uses a projection instead of `transform`, so the algorithm works directly on `v`, and the returned iterator points to the element `-7` of `v` without going through a temporary view.

Borrowed ranges include all lvalue references, `span`, `string_view`, `subrange`, `ref_view`, `iota_view`, and `take`, `drop`, `reverse` and others when their underlying range is borrowed ([[range.range#4]]).

### Temporaries in range-based `for` {{c++23}}

If the opening `Config` example is written directly in a range-based `for`:

```cpp run title="cfg-for.cpp" std=c++23 ok
#include <cstdio>
#include <ranges>
#include <string>
#include <vector>
struct Config {
  std::vector<std::string> keys{"listen_port", "log_level", "worker_threads"};
  const std::vector<std::string>& items() const { return keys; }
};
Config load() { return {}; }
int main() {
  for (std::size_t n : load().items()
                     | std::views::transform([](const std::string& s) { return s.size(); }))
    std::printf("%zu ", n);   // 11 9 14
  std::puts("");
}
```

C++23's [[P2718R0]] says all temporaries created in a range-based `for` initializer live until the end of the loop ([[class.temporary#7]]), so the temporary `Config` exists throughout the loop. Clang 23 with `-std=c++23` prints `11 9 14`; with `-std=c++20`, ASan reports stack-use-after-scope.

This fix applies only to range-based `for` initializers. Storing the pipeline in a variable first and then iterating, as at the start, still dangles. Other routes (returning a view of a local container from a function, storing a view as a member, and so on) are covered in [[topics/dangling-references]] and [[range.dangling]].

## Adaptor objects and pipelines

`views::filter(r, p)` and `r | views::filter(p)` are the same thing. The latter works because `views::filter(p)` first does **partial application**: it copies `p` into a [[g:range-adaptor-closure-object|range adaptor closure object]], and calls `views::filter(r, p)` once it gets a range ([[range.adaptor.object#8]]). A closure object `C` satisfies that `R | C` is equivalent to `C(R)`; two closure objects `C | D` form a new closure that, when called, equals `D(C(r))` ([[range.adaptor.object#1]]).

So a pipeline can be assembled first and attached to a range later, and since C++23 your own adaptors can join in too ([[P2387R3]]):

```cpp run ok
#include <ranges>
#include <vector>
#include <cstdio>
struct evens_only : std::ranges::range_adaptor_closure<evens_only> {
  auto operator()(std::ranges::viewable_range auto&& r) const {
    return std::views::filter(std::forward<decltype(r)>(r),
                              [](int x) { return x % 2 == 0; });
  }
};
inline constexpr evens_only evens;
int main() {
  std::vector<int> v{1, 2, 3, 4, 5, 6};
  auto squares = std::views::transform([](int x) { return x * x; });
  auto pipeline = evens | squares | std::views::take(2);   // no range yet
  for (int x : v | pipeline) std::printf("%d ", x);       // 4 16
  std::puts("");
}
```

`pipeline` is just a function object that can be stored, passed around and reused. It holds the argument of `take(2)` and the two lambdas by value, so the lifetime of arguments inside a closure matters too: a lambda that captures a local variable by reference, placed into a closure, can dangle just the same. The calling rules for each adaptor are in [[range.adaptors]].

## `ranges::to` and projections

Views are lazy; when you need a real container, use C++23's `ranges::to` ([[P1206R7]]). Projections are another design element of C++20 algorithms: almost every `ranges::` algorithm gained a `Proj` parameter, defaulting to `std::identity`, which the algorithm calls on each element before comparing or testing ([[g:projection]]).

```cpp run ok
#include <algorithm>
#include <cstdio>
#include <map>
#include <ranges>
#include <string>
#include <vector>
struct Order { std::string sym; int qty; };
int main() {
  std::vector<Order> book{{"NVDA", 120}, {"AAPL", 300}, {"MSFT", 50}};

  std::ranges::sort(book, {}, &Order::sym);                 // ascending by sym
  auto it = std::ranges::find(book, "MSFT", &Order::sym);   // find by sym
  auto big = std::ranges::max(book, {}, &Order::qty);       // returns a copy of the Order
  std::printf("%s %d %s\n", book[0].sym.c_str(), it->qty, big.sym.c_str());

  auto qty = book | std::views::transform([](const Order& o) {
                      return std::pair{o.sym, o.qty};
                    })
                  | std::ranges::to<std::map<std::string, int>>();
  std::string syms = book | std::views::transform(&Order::sym)
                          | std::views::join_with(',')
                          | std::ranges::to<std::string>();
  std::printf("%d %s\n", qty["NVDA"], syms.c_str());        // 120 AAPL,MSFT,NVDA
}
```

The output is `AAPL 50 AAPL` and `120 AAPL,MSFT,NVDA`.

The difference between a projection and `transform` is where the result points. `ranges::find(book, "MSFT", &Order::sym)` returns an iterator to the `Order` in `book`, through which `qty` can be accessed; the iterator returned by `ranges::find(book | views::transform(&Order::sym), "MSFT")` can only see `sym`. A projection isn't called fewer times per element than `transform`, as the counts in the previous section showed. The type requirements for projections are expressed by `projected` ([[projected#1]]).

`ranges::to` tries, in order, constructing directly from the range, constructing with the `from_range` tag, constructing from an iterator pair, and default-constructing then appending element by element ([[range.utility.conv.to#2]]). `to<std::vector>()` may omit the element type, which class template argument deduction fills in. Details are in [[range.utility.conv]].

## New views in C++23 and C++26

| Facility | Purpose | Standard | libc++ in our tests |
|---|---|---|---|
| `views::zip`, `zip_transform` | Iterate several ranges side by side | C++23 | Yes |
| `views::adjacent<N>`, `pairwise` | Sliding windows of length N, elements are tuples | C++23 | Yes |
| `views::enumerate` | Gives the index and the element together | C++23 | Yes |
| `views::chunk`, `slide` | Chunks by count; sliding windows of run-time length | C++23 | No |
| `views::chunk_by` | Splits into runs by a relation between adjacent elements | C++23 | Yes |
| `views::stride` | Takes every nth element | C++23 | Yes |
| `views::join_with` | Flattens and inserts a separator | C++23 | Yes |
| `views::cartesian_product` | Cartesian product | C++23 | No |
| `views::as_const`, `as_rvalue` | Elements become read-only; elements become rvalues | C++23 | Only `as_rvalue` |
| `views::repeat` | Repeats the same value | C++23 | Yes |
| `ranges::to`, `range_adaptor_closure` | Collect into a container; custom pipeline adaptors | C++23 | Yes |
| `std::generator` | Write input ranges with coroutines | C++23 | No |
| `views::concat` | Concatenates several ranges, possibly of different types | C++26 | Yes |
| `views::indices` | Shorthand for `iota(0, n)` | C++26 | Yes |
| `views::cache_latest`, `as_input` | Cache the dereferenced result; downgrade to an input range | C++26 | No |

The libc++ column was obtained by compile checks against the libc++ that ships with Clang 23.

```cpp run ok
#include <cstdio>
#include <functional>
#include <ranges>
#include <string>
#include <vector>
namespace vw = std::views;
int main() {
  std::vector<std::string> sym{"AAPL", "MSFT", "NVDA"};
  std::vector<int> px{230, 410, 120};

  for (auto [s, p] : vw::zip(sym, px)) std::printf("%s=%d ", s.c_str(), p);
  std::puts("");                                       // AAPL=230 MSFT=410 NVDA=120
  for (auto [i, s] : vw::enumerate(sym)) std::printf("%td:%s ", i, s.c_str());
  std::puts("");                                       // 0:AAPL 1:MSFT 2:NVDA
  for (auto [a, b] : px | vw::pairwise) std::printf("%d ", b - a);
  std::puts("");                                       // 180 -290
  std::vector<int> t{1, 2, 5, 3, 4, 0};
  for (auto run : t | vw::chunk_by(std::ranges::less{})) {
    for (int x : run) std::printf("%d", x);
    std::printf(" ");
  }
  std::puts("");                                       // 125 34 0
  for (int x : vw::concat(px, t | vw::stride(2))) std::printf("%d ", x);
  std::puts("");                                       // 230 410 120 1 5 4
  for (int i : vw::indices(3)) std::printf("%d ", i);
  std::puts("");                                       // 0 1 2
}
```

The elements of `zip` and `enumerate` are temporary tuples holding references; the names from structured bindings still refer to the underlying elements and can be written through ([[range.zip]], [[range.enumerate]]). `zip` and `concat` take several ranges and have no pipe form.

## Common pitfalls

### `split` versus `lazy_split`

```cpp run ok
#include <cstdio>
#include <ranges>
#include <sstream>
#include <string>
#include <string_view>
int main() {
  std::string_view csv = "AAPL,MSFT,,NVDA";
  for (auto part : csv | std::views::split(',')) {
    std::string_view s(part);                     // split: each part is a contiguous subrange
    std::printf("[%.*s] ", int(s.size()), s.data());
  }
  std::puts("");                                  // [AAPL] [MSFT] [] [NVDA]

  std::istringstream in("a b c");
  auto chars = std::views::istream<char>(in);     // input range (skips whitespace)
  // chars | std::views::split('b');              // error: split requires a forward range
  for (auto part : chars | std::views::lazy_split('b')) {
    for (char c : part) std::printf("%c", c);     // part can only be iterated element by element
    std::printf("|");
  }
  std::puts("");                                  // a|c|
}
```

`split` requires a forward range, and each part is a `subrange` of the underlying range, which can be converted directly to a `string_view` when splitting a `string_view`. `lazy_split` works on input ranges, at the cost that each part is a lazy inner range that can't be converted to a `string_view`. C++20's original `split` is today's `lazy_split`; [[P2210R2]] renamed it as a defect report and replaced `split` with today's design ([[range.split]]).

### `istream` can be iterated only once, and `take` reads one too many

```cpp run ok
#include <cstdio>
#include <ranges>
#include <sstream>
int main() {
  std::istringstream in("1 2 3 4 5 6");
  auto nums = std::views::istream<int>(in);
  for (int x : nums | std::views::take(2)) std::printf("%d ", x);
  std::puts("|");                                 // 1 2 |
  for (int x : nums) std::printf("%d ", x);
  std::puts("|");                                 // 4 5 6 |
  static_assert(!std::ranges::forward_range<decltype(nums)>);
}
```

Where did `3` go? After the first loop handles `2`, it still executes `++`; `take_view`'s counted iterator advances the underlying iterator, reading `3` from the stream, then the count reaches 0 and the loop ends. The second loop calls `nums.begin()`, and `basic_istream_view::begin()` always does `*stream_ >> value_` first ([[range.istream.view]]), reading another value, so it starts from `4`. The two extra elements checked by `filter | take(3)` in the earlier section have the same cause; it's just that on an input range, the extra value read is lost.

An input range doesn't guarantee that a second call to `begin()` gives the same result ([[range.range#3]]); handing it to two algorithms, iterating it twice, or copying the view and iterating each copy all interfere with each other. When you need multiple passes, collect it first with `ranges::to<std::vector>()`. When you must read exactly n values and not one more, write a plain loop `for (int i = 0; i < n && in >> x; ++i)`. The behavior of `take` and `take_while` on input ranges is covered in [[range.take]].

### Views shouldn't be passed as `const&`

See the section on caching begin(): `const auto&` can't accept views such as `filter`, `drop_while`, `split` and `chunk_by`. When a function template accepts ranges, use an `auto&&` forwarding reference; when it accepts only views, take them by value and pass them on with `std::move`.

## Questions

!!! question "1"
    Does `std::ranges::find(std::views::iota(0) | std::views::take(10), 7)` return `dangling`? What about with `std::vector<int>{...} | std::views::take(10)`?

<details markdown="1">
<summary>Answer</summary>

The former doesn't return `dangling`. `views::iota(0)` has no upper bound and isn't a sized range, so `take` can't replace it with a shorter `iota_view`, and the result is `take_view<iota_view<int, unreachable_sentinel_t>>`. `take_view` is borrowed when its underlying range is, and `iota_view` is a borrowed range (its iterators carry the current value and don't depend on the view object), so `find` returns a real iterator. With a bounded `views::iota(0, 100)`, `take(10)` returns an `iota_view<int, int>` directly, with the same conclusion.

The latter returns `dangling`. The temporary `vector` is moved into an `owning_view`; `take_view<owning_view<vector<int>>>` is borrowed only if its underlying range is, whether `owning_view` is borrowed follows the `vector`, and `vector` isn't a borrowed range. That is the correct result: the `vector` is destroyed together with this temporary view.
</details>

!!! question "2"
    Why doesn't `transform_view` cache `begin()`, while `filter_view` must?

<details markdown="1">
<summary>Answer</summary>

`transform_view::begin()` just wraps the underlying `begin()`; if the underlying one is amortized constant time, so is it, and no cache is needed. `filter_view::begin()` has to call `ranges::find_if` to find the first element satisfying the predicate, linear time in the worst case, and only caching can meet the amortized constant time requirement of [[range.range#2]] ([[range.filter.view#5]]). When the underlying range is only an input range, `filter_view` doesn't model a forward range, `begin()` isn't required to be equality-preserving in the first place, and the standard doesn't require caching.
</details>

!!! question "3"
    After `auto r = v | views::filter(p); auto r2 = r | views::take(3);`, if you iterate `r` first and then `r2`, is the predicate called again on the first element of `r2`?

<details markdown="1">
<summary>Answer</summary>

Yes. `r` is an lvalue view, `views::all(r)` copies it ([[range.all.general#2]]), and `r2` contains a copy of `r`. The copy happened before `r` was iterated, and in any case the cache doesn't propagate on copy ([[range.nonprop.cache]]), so `r2` has to search again on its first `begin()`. That's where the 2 extra calls for `filter|reverse` in the counts above came from.
</details>
