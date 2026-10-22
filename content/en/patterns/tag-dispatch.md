---
title: "Tag dispatch: from overloading to concepts"
summary: "Four ways to choose an implementation at compile time from the properties of a type: iterator category tags, enable_if, if constexpr and constrained overloads; which language rule each relies on, what their error messages look like, how much extra compile time they cost, and why the standard library uses empty tag types instead of bool parameters everywhere."
tags: tag dispatch, SFINAE, if constexpr, concepts, overload resolution, pattern
updated: 2026-10-19
---

!!! tldr
    - Tag dispatch encodes a property of a type as an empty class and picks a function through overload resolution. Tags express refinement through inheritance, and a conversion from a derived class to its nearest base is better than one to a more distant base, so the most specific version is always chosen.
    - `enable_if` writes the condition into the function signature, and a candidate is dropped when substitution fails. The price is that the conditions of the overloads must be made mutually exclusive by hand, and substitution failure only counts in the immediate context.
    - `if constexpr` gathers the branches into one function body, and the branches not taken are discarded when the template is instantiated. Only the parts depending on template parameters are discarded; code that doesn't depend on them must still be correct.
    - Constrained overloads are ordered by the subsumption of concepts, the entry point itself is constrained, and a `requires` expression truthfully answers whether it can be called. With the standard library's iterator concepts, the compile-time cost is noticeably higher than for the other three.
    - The standard library's `in_place_t`, `piecewise_construct_t`, `from_range_t`, `sorted_unique_t` and others are all empty tag types: they select a different constructor or a different semantics at compile time, which a `bool` parameter can't do.

## One operation, two algorithms

The most naive way to move an iterator forward `n` steps is to loop `n` times doing `++it`. That works for any iterator, but it is wasteful for `std::vector`'s iterators: they support `it += n`, getting there in one step.

Conversely, writing `it += n` directly doesn't work either: `std::list`'s iterators have no `+=`, and the code won't compile. We need to choose one of two implementations at compile time, based on the properties of the iterator type, and the one not chosen must not take part in compilation.

This is exactly how the standard library's `std::advance` and `std::distance` are specified: random access iterators use `+` and `-` in constant time; other iterators use `++` in linear time ([[iterator.operations#1]]). Below, the same `my_advance` is written four times, comparing which language rule each version relies on.

## Approach 1: tag dispatch

```cpp run title="tag-dispatch.cpp" ok
#include <cstdio>
#include <forward_list>
#include <iterator>
#include <list>
#include <vector>

namespace detail {
template<class It, class D>
constexpr void advance(It& it, D n, std::input_iterator_tag) {
  std::puts("input: ++ n times");
  while (n-- > 0) ++it;
}
template<class It, class D>
constexpr void advance(It& it, D n, std::bidirectional_iterator_tag) {
  std::puts("bidirectional: ++ or --");
  if (n >= 0) while (n-- > 0) ++it;
  else        while (n++ < 0) --it;
}
template<class It, class D>
constexpr void advance(It& it, D n, std::random_access_iterator_tag) {
  std::puts("random access: +=");
  it += n;
}
}  // namespace detail

template<class It, class D>
constexpr void my_advance(It& it, D n) {
  using Cat = typename std::iterator_traits<It>::iterator_category;
  detail::advance(it, n, Cat{});   // overload chosen by type; Cat{} is just an empty object
}

int main() {
  std::vector<int> v{1, 2, 3, 4, 5};
  std::list<int> l(v.begin(), v.end());
  std::forward_list<int> f(v.begin(), v.end());
  auto a = v.begin(); my_advance(a, 3);   // random access
  auto b = l.end();   my_advance(b, -2);  // bidirectional
  auto c = f.begin(); my_advance(c, 2);   // forward → input
  int* p = v.data();  my_advance(p, 4);   // pointer: random access
  std::printf("%d %d %d %d\n", *a, *b, *c, *p);
}
```

The output is `random access`, `bidirectional`, `input`, `random access` in turn, with `4 4 3 5` on the last line.

Every iterator type declares which category it belongs to through `iterator_traits<It>::iterator_category`; this member type is called an **iterator category tag** ([[g:iterator-category-tag|iterator category tag]], [[std.iterator.tags#1]]). The tag itself is an empty class carrying no data; its only use is its type.

`my_advance` constructs a tag object and passes it as the third argument to the three overloads of `detail::advance`. What the compiler does is ordinary overload resolution: whichever overload's third parameter type can be converted to from `Cat`, with the best conversion, gets chosen. The overloads not chosen are never instantiated, so a `list` iterator never meets `it += n`.

### Why tags inherit

The standard library's tags are related by inheritance ([[std.iterator.tags#1]]):

```cpp
struct input_iterator_tag { };
struct forward_iterator_tag : input_iterator_tag { };
struct bidirectional_iterator_tag : forward_iterator_tag { };
struct random_access_iterator_tag : bidirectional_iterator_tag { };
struct contiguous_iterator_tag : random_access_iterator_tag { };
```

`forward_list`'s tag is `forward_iterator_tag`, and no overload above was written for it. The call still succeeds, because when the argument type is derived from the parameter type, the implicit conversion sequence is a **derived-to-base conversion**, with Conversion rank ([[over.best.ics#7]]). Forward iterators therefore automatically fall back to the input iterator algorithm, without an overload for every category.

When several overloads are viable, inheritance also decides the winner:

```cpp run title="nearest-base.cpp" ok
#include <cstdio>
#include <iterator>

void pick(std::input_iterator_tag)         { std::puts("input"); }
void pick(std::bidirectional_iterator_tag) { std::puts("bidirectional"); }
void pick(std::random_access_iterator_tag) { std::puts("random access"); }

int main() {
  pick(std::forward_iterator_tag{});     // only input is viable
  pick(std::contiguous_iterator_tag{});  // all three viable; the nearest base wins
}
```

It prints `input` and `random access`. The conversions from `contiguous_iterator_tag` to the three bases all have Conversion rank, so rank can't separate them. At this point the rule in [[over.ics.rank#4.5]] steps in: if C is derived from B and B from A, the conversion from C to B is better than the conversion from C to A (4.5.3). The nearer the base along the inheritance chain, the better, so the most specific algorithm is always chosen.

!!! std
    If class B is derived directly or indirectly from class A and class C is derived directly or indirectly from B, … conversion of C to B is better than conversion of C to A.

    [[over.ics.rank#4.5]]: along an inheritance chain, converting to a nearer base is better than converting to a more distant one. The ordering of tag dispatch rests entirely on this sentence.

Break the inheritance chain and this ordering fails. A tag deriving from two unrelated classes makes the overloads ambiguous:

```cpp title="broken-chain.cpp" error
struct input {};
struct forward {};                       // forgot to inherit from input
struct random_access : input, forward {};
void pick(input);
void pick(forward);
void f() { pick(random_access{}); }      // error: ambiguous
```

Clang 23 reports `call to 'pick' is ambiguous`. There is no derivation between `input` and `forward`, none of the bullets of 4.5 apply, and the two conversion sequences are indistinguishable.

### The run-time cost of empty tags

A tag is an empty class with `sizeof` 1, but it carries no information, and nothing of it remains after optimization. With Clang 23 at `-O2`, calling `my_advance` on an `int*` generates a single arm64 instruction, `add x0, x0, x1, lsl #2`, exactly the same as writing `p + n` directly.

Even without inlining, an empty class type parameter takes no register. For a `[[gnu::noinline]] int f(int a, Empty, int b)`, on both arm64 (Apple ABI) and x86-64 Linux targets in our tests, `b` goes straight into the second integer register, and the code is identical to that of `int g(int a, int b)`.

### The standard library does the same

libc++'s `std::advance` in our tests has exactly the structure above: an entry function constructs `iterator_category()` and forwards to three tag-overloaded `__advance` functions. The standard itself demonstrates this technique in the example in [[std.iterator.tags#3]].

## Approach 2: enable_if and SFINAE

Since C++11, the condition can be written straight into the function template's signature, without an intermediate layer:

```cpp run title="enable-if.cpp" ok
#include <cstdio>
#include <forward_list>
#include <iterator>
#include <list>
#include <type_traits>
#include <vector>

template<class It>                       // alias template: substitution failure stays in the immediate context
using category_t = typename std::iterator_traits<It>::iterator_category;

template<class It, class Tag>
using is_at_least = std::is_base_of<Tag, category_t<It>>;

template<class It, class D,
         std::enable_if_t<is_at_least<It, std::random_access_iterator_tag>::value, int> = 0>
constexpr void my_advance(It& it, D n) {
  it += n;
}

template<class It, class D,
         std::enable_if_t<is_at_least<It, std::bidirectional_iterator_tag>::value &&
                          !is_at_least<It, std::random_access_iterator_tag>::value, int> = 0>
constexpr void my_advance(It& it, D n) {
  if (n >= 0) while (n-- > 0) ++it;
  else        while (n++ < 0) --it;
}

template<class It, class D,
         std::enable_if_t<is_at_least<It, std::input_iterator_tag>::value &&
                          !is_at_least<It, std::bidirectional_iterator_tag>::value, int> = 0>
constexpr void my_advance(It& it, D n) {
  while (n-- > 0) ++it;
}

int main() {
  std::vector<int> v{1, 2, 3, 4, 5};
  std::list<int> l(v.begin(), v.end());
  std::forward_list<int> f(v.begin(), v.end());
  auto a = v.begin(); my_advance(a, 3);
  auto b = l.end();   my_advance(b, -2);
  auto c = f.begin(); my_advance(c, 2);
  std::printf("%d %d %d\n", *a, *b, *c);
}
```

`std::enable_if_t<C, int>` is `int` when `C` is true and doesn't exist at all when it is false. For the template whose condition is false, substituting the deduced types back into the signature during template argument deduction forms an invalid type, deduction fails, and the template simply drops out of the candidates without an error. This rule is called **SFINAE** ([[g:sfinae|substitution failure is not an error]], [[temp.deduct.general#8]]).

Inheritance-based ordering is no longer used here; only one of the three templates may survive for a given type. So each condition must exclude the stronger cases: the bidirectional version writes `!random_access`, the input version `!bidirectional`. To add another level, such as a separate version for `contiguous_iterator_tag`, you'd have to go back and change the random access version's condition.

### Substitution failure only counts in the immediate context

SFINAE swallows only errors in the immediate context. The **immediate context** ([[g:immediate-context|immediate context]]) means the substituted positions themselves, such as the function type and the template parameter declarations, not other templates instantiated as a side effect of substitution, such as class template definitions or the initializers of variable templates ([[temp.deduct.general#8]]).

The example above uses an alias template, `category_t`. An alias template is expanded directly during substitution, so the failure still happens in the signature. Change it to a variable template, which looks equivalent, and the behavior differs:

<div class="compare" markdown="1">

```cpp
template<class It>
using category_t = typename
  std::iterator_traits<It>
    ::iterator_category;
// fails in the signature: SFINAE
```

```cpp
template<class It, class Tag>
inline constexpr bool at_least_v =
  std::is_base_of_v<Tag, typename
    std::iterator_traits<It>
      ::iterator_category>;
// fails in the initializer: hard error
```

</div>

With the right-hand version, calling `my_advance` on an `int`, Clang 23 doesn't report that no function matches, but three times `no type named 'iterator_category' in 'std::iterator_traits<int>'`, each with `in instantiation of variable template specialization ... requested here`. The initializer of a variable template specialization is instantiated separately, outside the immediate context, so the error is not treated as a substitution failure.

### Error messages

With the correct version, passing an output iterator, Clang 23's diagnostic is:

```text
error: no matching function for call to 'my_advance'
note: candidate template ignored: requirement 'std::is_base_of<std::random_access_iterator_tag,
      std::output_iterator_tag>::value' was not satisfied [with It = std::ostream_iterator<int>, D = int]
note: candidate template ignored: requirement 'std::is_base_of<std::bidirectional_iterator_tag,
      std::output_iterator_tag>::value' was not satisfied [...]
note: candidate template ignored: requirement 'std::is_base_of<std::input_iterator_tag,
      std::output_iterator_tag>::value' was not satisfied [...]
```

(The inline source snippets have been removed here and below.) Clang expands and prints the `enable_if` condition, which is much friendlier than older compilers. But it can only tell you which boolean expression is false; why the condition is false, the reader has to work out against the trait's definition.

## Approach 3: if constexpr

Since C++17, all the branches can go into a single function body:

```cpp run title="if-constexpr.cpp" ok
#include <cstdio>
#include <forward_list>
#include <iterator>
#include <list>
#include <type_traits>
#include <vector>

template<class It, class D>
constexpr void my_advance(It& it, D n) {
  using Cat = typename std::iterator_traits<It>::iterator_category;
  if constexpr (std::is_base_of_v<std::random_access_iterator_tag, Cat>) {
    it += n;                         // list iterators have no +=: this branch is discarded
  } else if constexpr (std::is_base_of_v<std::bidirectional_iterator_tag, Cat>) {
    if (n >= 0) while (n-- > 0) ++it;
    else        while (n++ < 0) --it;
  } else if constexpr (std::is_base_of_v<std::input_iterator_tag, Cat>) {
    while (n-- > 0) ++it;
  } else {
    static_assert(false, "my_advance needs an input iterator");
  }
}

int main() {
  std::vector<int> v{1, 2, 3, 4, 5};
  std::list<int> l(v.begin(), v.end());
  std::forward_list<int> f(v.begin(), v.end());
  auto a = v.begin(); my_advance(a, 3);
  auto b = l.end();   my_advance(b, -2);
  auto c = f.begin(); my_advance(c, 2);
  std::printf("%d %d %d\n", *a, *b, *c);
}
```

The condition of `if constexpr` must be a constant expression. When the condition is false, the first substatement is a **discarded statement** ([[g:discarded-statement|discarded statement]]); when it is true, the substatement after `else` is discarded. During template instantiation, if the condition is no longer dependent on template parameters, the discarded substatement is not instantiated ([[stmt.if#2]]).

The order of the branches is their priority. The conditions use `is_base_of_v` to mean "at least this category", so they must test from the strongest category downward; testing input iterators first would make every iterator fall into the first branch.

Passing an output iterator, Clang 23 gives just two lines: `static assertion failed: my_advance needs an input iterator`, and `in instantiation of function template specialization 'my_advance<std::ostream_iterator<int>, int>' requested here`. The author writes the message, so it can be very direct.

### Discarded statements still have to be correct

Discarded does not mean ignored. There are two limits.

First, discarding only means something in templates. In an ordinary function, an `if constexpr (false)` branch is still compiled in full, just not executed; odr-uses in it don't require the entity to be defined (note in [[stmt.if#2]]).

Second, in a template, code in a discarded branch that doesn't depend on template parameters is still checked at the definition. That code is the same for every template argument, and if it is wrong in itself, no instantiation could be correct:

<div class="compare" markdown="1">

```cpp title="non-template.cpp" error
#include <string>

int g() {
  if constexpr (sizeof(int) == 2) {
    std::string s = 42;  // error
  }
  return 0;
}
```

```cpp title="non-dependent.cpp" ifndr
template<class T>
void f(T t) {
  if constexpr (sizeof(T) == 1) {
    t.foo();       // depends on T: not checked
    undeclared();  // doesn't depend on T
  }
}
int main() { f(0); }
```

</div>

The left side is not in a template, so `std::string s = 42` is an ordinary error, and Clang 23 reports `no viable conversion from 'int' to 'std::string'`. On the right, the branch of `f<int>` is discarded; `t.foo()` depends on `T` and is never checked; `undeclared()` doesn't depend on `T` and can't be correct for any `T`. By [[temp.res.general#6]] (6.1, 6.7), such a program is ill-formed, no diagnostic required; Clang 23 reports `use of undeclared identifier 'undeclared'` right at the definition.

`static_assert(false, ...)` is the one exception to this rule. When determining whether a valid specialization can be generated, [[temp.res.general#6]] explicitly ignores failing `static_assert`s, so placed in a discarded `else` branch, it errors only when that branch is actually reached ([[P2593R1]]). Before that, the common workaround was a false condition dependent on a template parameter, such as `static_assert(sizeof(T) == 0)`. Clang 23 accepts `static_assert(false)` with `-std=c++20` too.

## Approach 4: constrained overloads

C++20 concepts write the condition into the template head, and also provide rules for ordering by the strength of conditions:

```cpp run title="concepts.cpp" ok
#include <cstdio>
#include <forward_list>
#include <iterator>
#include <list>
#include <vector>

template<std::input_iterator It>
constexpr void my_advance(It& it, std::iter_difference_t<It> n) {
  while (n-- > 0) ++it;
}

template<std::bidirectional_iterator It>
constexpr void my_advance(It& it, std::iter_difference_t<It> n) {
  if (n >= 0) while (n-- > 0) ++it;
  else        while (n++ < 0) --it;
}

template<std::random_access_iterator It>
constexpr void my_advance(It& it, std::iter_difference_t<It> n) {
  it += n;
}

int main() {
  std::vector<int> v{1, 2, 3, 4, 5};
  std::list<int> l(v.begin(), v.end());
  std::forward_list<int> f(v.begin(), v.end());
  auto a = v.begin(); my_advance(a, 3);
  auto b = l.end();   my_advance(b, -2);
  auto c = f.begin(); my_advance(c, 2);
  std::printf("%d %d %d\n", *a, *b, *c);
}
```

For a `vector` iterator, all three templates satisfy their constraints and are equally specialized by type deduction. The constraints are then compared: the definition of `random_access_iterator` begins with `bidirectional_iterator<I> && ...`, which in turn begins with `forward_iterator<I> && ...`, so the former **subsumes** ([[g:subsumes|subsumes]]) the latter, and the template with the stronger constraint is more specialized ([[temp.func.order#8]] 8.4, [[temp.constr.order#5]]). The effect is the same as the nearest base winning in tag dispatch, except that the ordering is based on the logical implication of concepts rather than class inheritance.

Subsumption recognizes only references between named concepts; the same condition written out twice does not count as identical. The detailed rules and counterexamples are in [[topics/concepts]].

### Behind the concepts there are still tags

The standard iterator concepts haven't abandoned tags. The definition of `random_access_iterator` contains `derived_from<ITER_CONCEPT(I), random_access_iterator_tag>` ([[iterator.concept.random.access#1]]). `ITER_CONCEPT(I)` prefers the `iterator_concept` member, falling back to `iterator_category` only if it is absent ([[iterator.concepts.general#1]]).

The tag's role has changed here: it no longer selects overloads, but serves as the iterator author's declaration of willingness to meet a category's semantic requirements. Syntactic checks are left to *requires* expressions; the semantic promise still relies on the tag.

### Error messages

Passing the same output iterator, Clang 23 gives a chain of reasons for each candidate. The part for the first candidate is:

```text
error: no matching function for call to 'my_advance'
note: candidate template ignored: constraints not satisfied [with It = std::ostream_iterator<int>]
note: because 'std::ostream_iterator<int>' does not satisfy 'input_iterator'
note: because 'std::ostream_iterator<int>' does not satisfy 'indirectly_readable'
note: because 'remove_cvref_t<...>' (aka 'std::ostream_iterator<int>') does not satisfy '__indirectly_readable_impl'
note: because 'typename iter_value_t<_In>' would be invalid: no type named 'value_type' in
      'std::indirectly_readable_traits<std::ostream_iterator<int>>'
...
```

Of the four approaches, this is the only one that states the root cause: an output iterator has no `value_type`, so it isn't readable. The price is length: each of the three candidates is expanded along the hierarchy of standard library concepts, 34 lines of errors and notes in total, compared with 5 lines for tag dispatch, 4 for `enable_if`, and 2 for `if constexpr` with `static_assert`. The first two or three lines are usually enough; the rest is evidence from drilling down layer by layer.

## Comparing the four approaches

### Is the entry point constrained

The entry point `my_advance` of tag dispatch and of `if constexpr` is an unconstrained template that matches any argument, and the error happens in the function body. This isn't just about where error messages appear: asking whether it can be called with a *requires* expression gives the wrong answer.

```cpp
template<class It>
concept advanceable = requires(It& it) { my_advance(it, 1); };

static_assert(advanceable<std::ostream_iterator<int>>);
```

With Clang 23, this assertion holds for the tag dispatch and `if constexpr` versions, and fails for the `enable_if` and concept versions. The first two claim to be callable for any type, misleading any other overloads or constraints that depend on them.

libc++'s `std::ranges::advance` combines the two: the entry point is constrained with `input_or_output_iterator`, and the body branches with `if constexpr (random_access_iterator<I>)` (the standard's specification is in [[range.iter.op.advance#2]]). The entry point's constraint truthfully declares what it accepts, and the internal branching avoids ordering problems between multiple overloads.

### Compile time

A script generated 1500 distinct element types `W<K>`, and for each type called `my_advance` once on a `W<K>*`, once on a forward iterator and once on a bidirectional iterator, 4500 instantiations in total. Clang 23 + libc++, `-O0 -c`, user CPU time and peak memory:

| Approach | User time | Peak memory |
|---|---|---|
| Type definitions only, no calls | 0.2 s | 110 MB |
| Tag dispatch | 1.1 s | 288 MB |
| `enable_if` | 1.1 s | 295 MB |
| `if constexpr` | 1.0 s | 258 MB |
| Custom concept checking only `iterator_category` | 1.1 s | 323 MB |
| Standard library iterator concepts | 18 s | about 1.9 GB |

The machine was heavily loaded during measurement and wall-clock times fluctuated a lot, so only the order of magnitude of these numbers matters. The first four are nearly identical, with `if constexpr` slightly cheaper since it instantiates only one function per call.

The cost of the standard library concepts isn't in the concept mechanism itself: replacing them with a custom concept that only compares tags takes about as long as tag dispatch. The cost comes from the many requirements that concepts like `input_iterator` check, with `common_reference_with` inside `indirectly_readable` being especially expensive. Checking `std::input_iterator` once for a new type takes about 2.4 ms in our tests. That is nothing for everyday code; for low-level libraries instantiated for thousands of types, it is worth knowing.

### What they can express

| | Tag dispatch | `enable_if` | `if constexpr` | Constrained overloads |
|---|---|---|---|---|
| Minimum standard | C++98 | C++11 | C++17 | C++20 |
| Basis of selection | inheritance of tag types | hand-written mutually exclusive conditions | branch order | subsumption of concepts |
| Adding a level | one more derived tag and one more overload | must change existing overloads' conditions | change this function | one more refined concept and one more overload |
| Extensible by third parties | yes, tags can be derived from; with unqualified calls, ADL can also find new overloads | hard | no, the branches are closed | yes |
| Constrained entry point | no | yes | no | yes |
| Usable on constructors | yes, with a tag parameter | yes | only inside the body | yes |
| Error messages | overload failure inside the body | lists the false conditions | your own `static_assert` | a chain of reasons, rather long |

## Tags in the standard library

Iterator categories are tags that let types carry properties. The standard library has another, more common kind of tag: the caller explicitly passes an empty object to select a particular constructor or a particular semantics.

```cpp run title="library-tags.cpp" ok
#include <cstdio>
#include <flat_map>
#include <list>
#include <map>
#include <new>
#include <optional>
#include <string>
#include <tuple>
#include <utility>
#include <variant>
#include <vector>

int main() {
  // in_place: forward the arguments to T's constructor as they are, instead of building a T and moving it in
  std::optional<std::string> o(std::in_place, 3, 'x');            // "xxx"
  // in_place_type / in_place_index: constructors can't take explicit template arguments, so the type must come in through an argument
  std::variant<int, std::string> v(std::in_place_type<std::string>, 2, 'y');
  // piecewise_construct: the two tuples are unpacked for first and second respectively
  std::map<std::string, std::vector<int>> m;
  m.emplace(std::piecewise_construct,
            std::forward_as_tuple("k"), std::forward_as_tuple(4, 7));
  // nothrow: selects another allocation function that returns null on failure instead of throwing
  int* p = new (std::nothrow) int[16];
  delete[] p;
  // from_range: construct from a range, and let class template argument deduction deduce the element type
  std::list<int> src{3, 1, 2};
  std::vector w(std::from_range, src);                             // vector<int>
  std::vector u{src};                                              // vector<list<int>>
  // sorted_unique: the caller promises the keys are already sorted and unique, skipping the sort
  std::flat_map<int, char> fm(std::sorted_unique, {1, 2, 3}, {'a', 'b', 'c'});

  std::printf("%s %s %zu %zu %zu %zu %c\n", o->c_str(), std::get<1>(v).c_str(),
              m["k"].size(), w.size(), u.size(), u[0].size(), fm[2]);
}
```

In our tests it prints `xxx yy 4 3 1 3 b`. Note `w` and `u`: both take `src` as the argument, but with the tag deduction gives `vector<int>`, while braces without a tag deduce a single-element `vector<list<int>>`.

| Tag | Declared in | Purpose |
|---|---|---|
| `in_place_t` / `in_place_type_t<T>` / `in_place_index_t<I>` | [[utility.syn]] | in-place construction of the contained object of `optional`, `variant`, `any`, `expected`; the last two carry a type or index into the constructor |
| `piecewise_construct_t` | [[pair.piecewise]] | each of `pair`'s two members is constructed by unpacking one `tuple` |
| `allocator_arg_t` | [[allocator.tag]] | constructors of `tuple` and similar types: the next argument is an allocator |
| `nothrow_t` | [[new.syn]] | selects a non-throwing allocation function via placement syntax; returns null on failure |
| `destroying_delete_t` | [[new.syn]] | a class's `operator delete` that takes it makes the `delete` expression no longer call the destructor first |
| `from_range_t` | [[ranges.syn]] | containers constructed from or inserting any range ([[P1206R7]]) |
| `sorted_unique_t` / `sorted_equivalent_t` | [[flat.map.syn]] | the caller guarantees the input is already sorted, so construction doesn't sort |
| Execution policies `sequenced_policy` etc. | [[execpol]] | overloads of the parallel algorithms: choose sequenced, parallel or vectorized execution |

### Why not bool

Imagine `flat_map` used a `bool assume_sorted` parameter instead of `sorted_unique`. There are three differences.

First, the semantics are separated at compile time. The constructor without the tag sorts and then removes duplicates ([[flat.map.cons#1]]), while the version with `sorted_unique` only moves the containers, in constant time ([[flat.map.cons#4]]). With `bool`, both paths would be compiled into one function and decided at run time. For `in_place_type<T>` it is even more obvious: a `bool` can't carry a type at all.

Second, a tag can give the same arguments a different meaning. `pair(tuple, tuple)` originally means initializing the two members with two tuples; only with `piecewise_construct` does it mean unpacking the tuples into constructor arguments. `vector{src}` is already valid; only with `from_range` does it become construction from a range. With `bool`, these overloads couldn't be distinguished by signature.

Third, the call site is readable. The `true` in `flat_map(keys, values, true)` requires reading the documentation, while `sorted_unique` states its intent, and the wrong type is rejected at compile time. Other solutions to the same problem for ordinary functions are in [[patterns/named-parameters]] and [[patterns/strong-types]].

### How tag types are written

The standard library's tags are all written the same way:

```cpp
struct in_place_t { explicit in_place_t() = default; };
inline constexpr in_place_t in_place{};
```

The default constructor is `explicit` ([[LWG2510]]), so `std::in_place_t t = {};` is ill-formed: copy-list-initialization from empty braces selects an explicit constructor ([[over.match.ctor#1]]). A casually written `{}` will never be silently taken as a tag.

The `inline constexpr` variable lets callers write `std::in_place` instead of `std::in_place_t{}`, and every translation unit sees the same object. `nothrow` is the exception: it has existed since C++98 and is declared as `extern const nothrow_t nothrow;`.

Constructors with tags also need to guard against their own forwarding constructors. `optional(U&& v)` accepts any type, so the standard specifically constrains it not to participate when `U` is `in_place_t` ([[optional.ctor#23]]); `any(T&& value)` likewise excludes specializations of `in_place_type_t` ([[any.cons#6]]), or else `std::any a(std::in_place_type<int>);` would store the tag object itself. When writing similar types yourself, forwarding constructors need the same constraint.

### A tag recognized by the core language

Most tags only matter in the library; `destroying_delete_t` is one of the few that changes core language semantics. When the second parameter of a class's `operator delete` has this type, it is a **destroying operator delete** ([[basic.stc.dynamic.deallocation#2]]), the `delete` expression no longer automatically calls the destructor ([[expr.delete#5]]), and destroying the object becomes that function's responsibility ([[P0722R3]]).

```cpp run title="destroying-delete.cpp" ok
#include <cstdio>
#include <new>

struct Shape {
  enum Kind { circle, square } kind;
  // second parameter is destroying_delete_t: the delete expression no longer calls the destructor first
  void operator delete(Shape* p, std::destroying_delete_t);
};
struct Circle : Shape { double r; ~Circle() { std::puts("~Circle"); } };
struct Square : Shape { double a; ~Square() { std::puts("~Square"); } };

void Shape::operator delete(Shape* p, std::destroying_delete_t) {
  // destroys by dynamic type without a virtual destructor: dispatch on kind ourselves
  if (p->kind == circle) { auto* c = static_cast<Circle*>(p); c->~Circle(); ::operator delete(c, sizeof(Circle)); }
  else                   { auto* s = static_cast<Square*>(p); s->~Square(); ::operator delete(s, sizeof(Square)); }
}

int main() {
  Shape* a = new Circle{{Shape::circle}, 1.0};
  Shape* b = new Square{{Shape::square}, 2.0};
  delete a;   // ~Circle
  delete b;   // ~Square
}
```

It prints `~Circle` and `~Square`, with no ASan or UBSan reports in our tests. Deleting a derived object through a base pointer when the base has no virtual destructor is normally UB; [[expr.delete#3]] makes an exception when a destroying operator delete is selected, because the class itself is then responsible for destroying by dynamic type. The tag here is not used to select overloads; the compiler recognizes the type itself.

### Execution policies

`std::execution::seq`, `par`, `par_unseq` and `unseq` are tag objects too, each of its own class, with no inheritance between them. The overloads of the parallel algorithms constrain their first parameter with the exposition-only concept *execution-policy*, which checks `is_execution_policy_v` ([[algorithms.parallel.defns]], [[execpol.type#2]]). Users cannot specialize this trait ([[execpol.type#3]]), so new policies can only come from the implementation. In our tests, libc++'s parallel algorithms require `-fexperimental-library`.

## Traps

!!! pitfall "Dispatching on iterator_category underestimates C++20 iterators"
    The iterators of `iota_view`, and those of a `transform_view` returning prvalues, have `iterator_category` `input_iterator_tag`, because the old iterator requirements say dereferencing a forward iterator must return a reference ([[range.iota.iterator]], [[range.transform.iterator#2]]). Yet their `iterator_concept` is random access. A `my_advance` dispatching on `iterator_category` will increment them one step at a time; a version overloaded on `std::random_access_iterator` will use `+=`.

```cpp ok
#include <iterator>
#include <ranges>
#include <type_traits>
#include <vector>

using It = std::ranges::iterator_t<std::ranges::iota_view<long, long>>;
static_assert(std::is_same_v<std::iterator_traits<It>::iterator_category,
                             std::input_iterator_tag>);   // old category: input
static_assert(std::random_access_iterator<It>);           // new concept: random access

int square(int x) { return x * x; }
using Squares = decltype(std::declval<std::vector<int>&>() | std::views::transform(square));
using Jt = std::ranges::iterator_t<Squares>;
static_assert(std::is_same_v<std::iterator_traits<Jt>::iterator_category,
                             std::input_iterator_tag>);   // dereferencing returns a prvalue
static_assert(std::random_access_iterator<Jt>);
```

!!! pitfall "Constrained overloads must have the same parameter shape"
    Ordering by constraints requires the two templates to be equally specialized by type deduction and their template parameter lists to be equivalent ([[temp.func.order#8]]). The first template below has an extra parameter `D`, and the constraints are of no use.

```cpp run title="shape-mismatch.cpp" ok
#include <cstdio>
#include <iterator>
#include <vector>

template<std::input_iterator It, class D>
void my_advance(It& it, D n) { std::puts("input"); while (n-- > 0) ++it; }

template<std::random_access_iterator It>
void my_advance(It& it, std::iter_difference_t<It> n) { std::puts("random access"); it += n; }

int main() {
  std::vector<int> v(10);
  auto it = v.begin();
  my_advance(it, 3);   // prints input
}
```

The argument `3` is an `int`. The first template deduces `D = int`, an exact match; the second template's parameter is `ptrdiff_t`, requiring an integral conversion. Overload resolution picks the first by conversion sequence before constraints are ever compared, and the `vector` iterator is incremented 3 times one step at a time, without any warning. Change the argument to `3L` and both conversions are exact matches, but the template parameter lists differ in length, so by [[temp.func.order#8]] (8.1) the constraints are not compared, and Clang 23 reports `call to 'my_advance' is ambiguous`. Giving all the overloads the same parameter shape, as in `concepts.cpp`, avoids this.

!!! pitfall "The entry point of tag dispatch is unconstrained"
    The entry template accepts every argument, errors appear only inside the body, and `requires` expressions and other overloads see a function that can be called with anything. If the entry point will be probed by other generic code, constrain it, e.g. `template<std::input_iterator It>`, and still dispatch internally with tags or `if constexpr`.

## Which to use when

| Situation | Choice |
|---|---|
| New C++20-and-later code choosing algorithms by type capability | constrain the entry point with a concept and branch internally with `if constexpr`; or use constrained overloads directly |
| A fixed set of choices that only the author will extend | `if constexpr`, with the branches in one place |
| Third parties must be able to add a new level for their own types | constrained overloads, or tags with inheritance |
| A constructor needs a different meaning, or must carry in a type | a tag parameter, written like `in_place_t` |
| Standards before C++17 must be supported | tag dispatch; `enable_if` when the conditions don't overlap |
| Instantiated for a large number of types, compile time matters | avoid checking heavyweight standard library concepts on hot paths; use lighter custom concepts or tags |

## Questions

!!! question "1"
    In approach 1, if the tag parameters of the three `detail::advance` overloads are changed to references such as `const std::input_iterator_tag&`, does the chosen overload change?

<details markdown="1">
<summary>Answer</summary>

No. When a reference binds directly to a derived class object, the implicit conversion sequence is also a derived-to-base conversion ([[over.ics.ref#1]]), with Conversion rank; bullet 4.5.3 of [[over.ics.rank#4.5]] looks only at the derivation between classes and treats by-value and by-reference alike. The nearest base still wins. Passing an empty tag by value has no run-time cost either, so the standard library usually passes tags by value.
</details>

!!! question "2"
    What is wrong with the code below?

    ```cpp
    template<class T>
    void serialize(const T& x) {
      if constexpr (std::is_arithmetic_v<T>) write_number(x);
      else if constexpr (requires { x.serialize(); }) x.serialize();
      else static_assert(false, "not serializable");
    }
    ```

<details markdown="1">
<summary>Answer</summary>

Under the current draft it is correct: `static_assert(false)` sits in a discarded branch, [[temp.res.general#6]] ignores failing `static_assert`s when determining valid specializations, and the error appears only when the last branch is actually taken. The real problem is the design: the set of branches is closed, users can't hook their own types into serialization without changing this function; and `serialize` is unconstrained, so `requires { serialize(y); }` holds for every type. When extensibility is needed, switch to constrained overloads, or a customization point found through ADL; see [[topics/name-lookup-and-customization]].
</details>

!!! question "3"
    Does the `o` constructed by `std::optional<std::in_place_t> o(std::in_place);` have a value?

<details markdown="1">
<summary>Answer</summary>

The program is ill-formed. `in_place_t` and `nullopt_t` are not valid contained types of `optional`, and instantiating `optional` with them is an error ([[optional.optional.general#2]]). Otherwise `optional(std::in_place)` could mean either in-place construction with an empty argument list or storing a tag object, and `optional(std::nullopt)` would have a similar ambiguity. libc++ in our tests reports it with a `static_assert`: `instantiation of optional with in_place_t is ill-formed`.

The same consideration shows in the constraint on `optional(U&&)`: it does not participate in overload resolution when `U` is `in_place_t` ([[optional.ctor#23]]), so a tag always lands on the tagged constructor.
</details>

## Summary

| Question | Conclusion | Source |
|---|---|---|
| Why do tags inherit? | derived-to-base is Conversion rank, and the nearest base is preferred | [[over.best.ics#7]], [[over.ics.rank#4.5]] |
| Run-time cost of empty tags | zero at `-O2` in our tests; even without inlining they take no register | measured in our tests |
| Which errors does SFINAE swallow? | only substitution failures in the immediate context | [[temp.deduct.general#8]] |
| Discarded statements | not instantiated in templates; parts not dependent on template parameters must still be correct | [[stmt.if#2]], [[temp.res.general#6]] |
| How are constrained overloads ordered? | by subsumption; requires matching template parameter lists and function parameter types | [[temp.constr.order#5]], [[temp.func.order#8]] |
| Iterator concepts and tags | the concepts still determine the category from the `ITER_CONCEPT(I)` tag internally | [[iterator.concepts.general#1]] |
| How tag types are written | an empty class, an explicit default constructor, an `inline constexpr` object | [[utility.syn]], [[LWG2510]] |
