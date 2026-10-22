---
title: Algorithms requirements
summary: "Rules shared by the whole algorithms library: template parameter names denote type requirements, predicates must not modify objects through their arguments and must give the same result for const arguments, algorithms may copy function objects freely, ranges algorithms are function objects that ADL cannot find, and explicitly specifying template arguments for classic algorithms is unspecified."
updated: 2026-10-19
---

!!! tldr
    - The template parameters of classic algorithms are unconstrained; the parameter names `InputIterator`, `ForwardIterator`, `Predicate` and so on are the requirements. Passing a type that does not meet them is undefined behavior, and the compiler need not complain.
    - A predicate must not modify elements through its argument, and must give the same result for a const lvalue of the same element. A predicate whose parameter is `int&` does not meet the requirements.
    - Algorithms may copy function objects freely. When you need the function object's state preserved, pass `std::ref(f)`.
    - The algorithms in `std::ranges` are objects, not functions: ADL cannot find them, unqualified lookup that finds them turns ADL off, and you cannot give them explicit template arguments.
    - `first + n` and `last - first` written for forward iterators in the wording are just notation, meaning step-by-step movement and step counting.

The wording of the hundred-plus algorithms that follow is very short; `find_if`, for example, has only *Returns* and *Complexity*. It can be that short because what `ForwardIterator` must satisfy, what a `Predicate` may do, and what `a + n` means for a forward iterator are all specified once, in [algorithms.requirements].

¶1 The algorithms are separated from the implementations of data structures and are parameterized by iterator types, so any program-defined data structure that provides iterators meeting the requirements can use them.

## Parameter names are requirements (¶4)

The declarations of the classic algorithms have no constraints at all:

```cpp
template<class ForwardIterator, class T>
  void fill(ForwardIterator first, ForwardIterator last, const T& value);
```

¶4 specifies that when a template parameter is unconstrained, its name denotes the type requirements:

| Parameter name | The template argument must |
|---|---|
| `InputIterator`, `InputIterator1`, `InputIterator2` | meet *Cpp17InputIterator* (¶4.2) |
| `OutputIterator`, `OutputIterator1`, `OutputIterator2` | meet *Cpp17OutputIterator* (¶4.3) |
| `ForwardIterator`, `ForwardIterator1`, `ForwardIterator2`, `NoThrowForwardIterator` | meet *Cpp17ForwardIterator* if it must be writable, otherwise model `forward_iterator` (¶4.4) |
| `BidirectionalIterator…` | meet *Cpp17BidirectionalIterator* if it must be writable, otherwise model `bidirectional_iterator` (¶4.6) |
| `RandomAccessIterator…` | meet *Cpp17RandomAccessIterator* if it must be writable, otherwise model `random_access_iterator` (¶4.7) |

Names like *Cpp17ForwardIterator* are the old-style named requirements ([[iterator.requirements]]), while `forward_iterator` is a C++20 iterator concept ([[iterator.concepts]]); the two are not identical. ¶4.1 specifies that when an algorithm's *Effects* modify the value an iterator points to, that iterator must be a mutable iterator, i.e. writable through. ¶4.5 additionally requires of `NoThrowForwardIterator` that increment, assignment, comparison and indirection through valid iterators throw no exceptions.

The consequence of violating these requirements is set by [[res.on.functions]]: when an argument to a standard library template does not meet its requirements, the behavior is undefined. So a classic algorithm used with the wrong iterator may compile and fail at run time. Note 1 says these name-based rules do not affect constrained parameters; the requirements of `ranges` algorithms are written directly as concepts.

### Read-only algorithms accept C++20 iterators

The second half of ¶4.4, ¶4.6 and ¶4.7, "otherwise model the C++20 concept", comes from C++23's [[P2408R5]].

Many C++20 views, such as `views::iota(0, n)` and `views::transform`, have iterators whose dereference yields a prvalue rather than a reference. They satisfy C++20's `random_access_iterator` but not *Cpp17ForwardIterator*, because the latter requires dereferencing to yield a real reference. Before P2408, passing such an iterator to `std::find` was strictly speaking undefined behavior. Now, algorithms that do not need to write only require the iterator to model the corresponding C++20 concept.

When writing is needed, the *Cpp17* version is still required, because implementations of classic algorithms rely heavily on dereferencing yielding a real reference, for example calling `swap` on `*a` and `*b`, and the C++20 concepts do not guarantee that. `InputIterator` has no such relaxation: a C++20 `input_iterator` may be move-only, while classic algorithms copy iterators.

## The predicate contract (¶6–¶8)

```cpp
std::vector<int> v{1, 2, 3};
auto it = std::find_if(v.begin(), v.end(),
                       [](int& x) { return x == 2; });  // does not meet ¶6
```

This code compiles with libc++ in our tests and does find 2, but it does not meet the standard's requirements on `Predicate`. ¶6 specifies three things for algorithms that take a `Predicate pred` (where `first` is an iterator argument with value type `T`):

1. `pred(*first)` is well-formed and its return type models *boolean-testable* ([[g:boolean-testable]]). That is, the return type need not be `bool`, but it must be usable like `bool` in `!`, `&&` and `||` ([[concept.booleantestable]]).
2. `pred` must not apply any non-constant function through its argument, i.e. it must not modify the element through the argument.
3. For a glvalue `u` of type `T` or `const T` that designates the same object as `*first`, `pred(u)` must be a valid expression equal to `pred(*first)`.

Item 3 allows an implementation to pass the element to the predicate as a const lvalue, or to copy it into a local variable first and call the predicate on that. The lambda above does not accept a `const int`, violating item 3. It compiles only because libc++ happens to pass a non-const lvalue; per [[res.on.functions]], this is undefined behavior.

`ranges::find_if` does not reject this lambda either. Its constraint `indirect_unary_predicate` only checks that the predicate can be called with `iter_value_t<I>&` and `iter_reference_t<I>` ([[indirectcallable]]), and for a non-const `vector<int>` both are `int&`. The constraint check fails only when it is used on a `const vector<int>`.

¶7 makes the corresponding rules for `BinaryPredicate`: `binary_pred(*first1, *first2)` is well-formed and its return type models *boolean-testable*, it must not modify objects through its arguments, and it gives the same results for const arguments. In addition, unless otherwise specified, the first argument always comes from the first sequence; when the signature has a `T value`, the call is `binary_pred(*first1, value)`.

The fixed argument order is useful for heterogeneous comparison: you can write a predicate that only accepts `(Elem, Key)` in that order. `std::upper_bound` is one of the "otherwise specified" cases; it calls `comp(value, *i)` ([[alg.binary.search]]).

¶8 Parameters such as `UnaryOperation` and `BinaryOperation` are only required to be function objects ([[function.objects]]), without the no-modification requirements of ¶6 and ¶7. Individual algorithms add their own restrictions in their *Preconditions*; for example, `transform` requires that `op` not modify the elements in the ranges ([[alg.transform#2]]).

¶10 When the wording uses an expression like `*first == value` as a condition, it must evaluate to `true` or `false` in a boolean context.

## Function objects may be copied (¶9)

```cpp run title="ref.cpp" ok
#include <algorithm>
#include <cassert>
#include <functional>
#include <vector>

struct Counter {
  int calls = 0;
  bool operator()(int x) { ++calls; return x % 2 == 0; }
};

int main() {
  std::vector<int> v{5, 3, 8, 1, 9, 2, 7, 4, 6, 0};
  Counter c;
  (void)std::count_if(v.begin(), v.end(), c);
  assert(c.calls == 0);            // the algorithm used a copy of c
  (void)std::count_if(v.begin(), v.end(), std::ref(c));
  assert(c.calls == 10);           // c itself is called through the reference
}
```

Algorithms take function objects by value, so the caller's `c` does not change. Note 2 of ¶9 goes further: unless otherwise specified, algorithms that take function objects may copy them freely, and the standard does not limit the number of copies. So code relying on state accumulated inside a function object is not portable. When you need the same object kept, pass a `std::reference_wrapper` ([[refwrap]]), as with `std::ref(c)` above.

`for_each` is an "otherwise specified" example: the non-parallel `std::for_each` returns the function object to the caller, and `ranges::for_each` brings it back in the `fun` member of its return value ([[alg.foreach]]).

Note that `Counter::operator()` modifies the predicate's own state, not its argument, so it does not violate item 2 of ¶6. But the `ranges` versions require the predicate to model `predicate`, which includes equality preservation: equal inputs must give equal results. A stateful predicate like `Counter`, whose result may differ from call to call, satisfies the syntactic requirements but does not model the concept in a `ranges` algorithm, which is likewise undefined behavior.

## No sneaky writes (¶3)

!!! std
    For purposes of determining the existence of data races, algorithms shall not modify objects referenced through an iterator argument unless the specification requires such modification.

Two threads calling `std::find` or `std::count` on the same `vector` at the same time do not constitute a data race ([[intro.races]]). An implementation may not temporarily rewrite elements to go faster, such as placing a sentinel value at the end and restoring it after the search.

## `ranges` algorithms are objects (¶2)

¶2 specifies that the entities described in this clause as function templates in `std::ranges` are all **algorithm function objects** ([[g:algorithm-function-object]]). What the wording writes as

```cpp
template<input_iterator I, sentinel_for<I> S, class Proj = identity, ...>
  constexpr I ranges::find(I first, S last, const T& value, Proj proj = {});
```

is only a way of describing it. `std::ranges::find` is actually an object, whose `operator()` overloads correspond one-to-one to these templates. [[alg.func.obj]] defines it as a kind of **customization point object** ([[g:customization-point-object]]). This has several observable consequences:

- ADL does not find them.
- When unqualified name lookup finds them, ADL does not take place, because what was found is an object, not a function ([[basic.lookup.argdep]]).
- They can be copied and passed around like ordinary objects.
- They cannot be given explicit template arguments: `std::ranges::sort<std::vector<int>&>(v)` is ill-formed; Clang reports 'sort' does not name a template but is followed by template arguments.

```cpp run title="niebloid.cpp" ok
#include <algorithm>
#include <cassert>
#include <vector>

namespace lib {
  struct Widget { int id; };
  bool operator==(Widget a, Widget b) { return a.id == b.id; }
  // a function template of the same name, findable only by ADL
  template<class It, class T>
  It find(It f, It, const T&) { return f; }
}

int main() {
  std::vector<lib::Widget> v{{1}, {2}, {3}};
  using namespace std::ranges;
  auto it = find(v.begin(), v.end(), lib::Widget{3});
  assert(it == v.end() - 1);   // ranges::find is called

  auto sorter = std::ranges::sort;  // can be copied and passed around
  std::vector<int> w{3, 1, 2};
  sorter(w);
  assert((w == std::vector<int>{1, 2, 3}));
}
```

Unqualified lookup finds the object `std::ranges::find` through the using-directive, so ADL is turned off, and neither `lib::find` nor `std::find` becomes a candidate. The classic `std::sort` is a function template, and the situation is the opposite:

```cpp run title="adl.cpp" error
#include <algorithm>
#include <vector>
int main() {
  std::vector<int> v{3, 1, 2};
  sort(v.begin(), v.end());  // OK: ADL finds std::sort
  sort(v);                   // error: ranges::sort is not found by ADL
}
```

The iterators of `vector` are associated with namespace `std`, so `std::sort` can be called through ADL without writing `std::`. `sort(v)` expects `ranges::sort`, which ADL cannot find, and `std::sort` has no single-argument overload.

Such objects are commonly called niebloids in the community, after Eric Niebler. C++20 only specified that they are not found by ADL and that finding them turns ADL off; implementations generally satisfied this with objects. C++26's [[P3136R1]] formally defines them as customization point objects, so they also have the other properties of customization point objects ([[customization.point.object]]).

## Explicit template arguments (¶15)

!!! std
    The well-formedness and behavior of a call to an algorithm with an explicitly-specified template argument list is unspecified, except where explicitly stated otherwise.

Note 4 explains why: an implementation may declare an algorithm with template parameters different from those the standard lists, for example an extra defaulted template argument or a different order. So whether `std::find<std::vector<int>::iterator, int>(...)` compiles, and what it does, is {{unspec}}.

The explicitly stated exceptions are `std::min`, `std::max` and `std::minmax`: the *Remarks* in [[alg.min.max]] allow an explicit argument for `T`, and `std::max<long>(1, 2L)` is a common idiom.

## `a + n` and `b - a` are just notation (¶11–¶13)

For brevity, the wording writes `first + n` and `last - first` even for iterators that do not support arithmetic. ¶11 defines what they mean:

- `a + n` is equivalent to copying `a` and then incrementing it (decrementing if `n` is negative) `|n|` times;
- if `[a, b)` is a range, `b - a` is equivalent to the number of steps from `a` to `b`; if `[b, a)` is a range, the result is negative;
- if an iterator `i` and a sentinel `s` come from the same range `r`, `s - i` has the same type and value as `ranges::distance(i, s)`. Note 3 allows an implementation to use `ranges::distance(r)` instead when the result is the same, which takes only constant time for a range that knows its size.

So "`last - first` comparisons" in a complexity clause makes sense for forward iterators too, but it does not mean the algorithm actually computes that subtraction. A complexity clause counts only the operations it names, such as applications of the predicate.

¶12 When `n` is integer-like but not the iterator's difference type `D`, `a + n` means `a + D(n)`. ¶13 When a return value is described, a sentinel `s` sometimes appears where an iterator is needed; it means `ranges::next(i, s)`. This is why `ranges::sort(first, sentinel)` returns an iterator rather than a sentinel.

## How range overloads forward (¶14)

!!! std
    Overloads of algorithms that take range arguments behave as if they are implemented by dispatching to the overload in namespace `ranges` that takes separate iterator and sentinel arguments

For each range argument `r`, the corresponding iterator argument is `ranges::begin(r)` and the sentinel argument is `ranges::end(r)` or `ranges::begin(r) + N`, where `N` equals `ranges::distance(r)`. The latter is useful for ranges that know their size but whose begin and end differ in type: it gives an end of the same type as `begin`, which can satisfy overloads that require `sized_sentinel_for`, such as C++26's parallel `ranges` overloads.

`borrowed_iterator_t<R>` appears often in the return types of range overloads. When the argument is a temporary range that will be destroyed at the end of the call, this type is `ranges::dangling`, and using the returned iterator fails to compile; see [[algorithms.results]].

## Naming conventions (¶5)

Some algorithms provide both an in-place version and a copying version; the copying version is named *algorithm*`_copy`. Versions that take a predicate get the suffix `_if`, placed after `_copy`, as in `remove_copy_if`. Footnote 179 explains why there is no `sort_copy`: when the cost of the operation itself dominates the cost of copying, no copying version is provided; users can simply `copy` first and then `sort`.

## Questions

!!! question "Question 1"
    Does `std::count_if(v.begin(), v.end(), [n = 0](int) mutable { return ++n % 2 == 0; })` necessarily return the same result on different implementations?

<details markdown="1">
<summary>Answer</summary>

Not necessarily. ¶9 allows algorithms to copy function objects freely; if an implementation copied the predicate and used different copies for different elements, the counts would diverge. Real implementations all use a single copy, but the standard does not guarantee it. The more fundamental problem is that this predicate gives different results when called twice on the same element, violating ¶6's requirement that `pred(u)` equal `pred(*first)`; it is undefined behavior.
</details>

!!! question "Question 2"
    After writing `using std::ranges::sort;` at global scope, which function does `sort(v.begin(), v.end())` call?

<details markdown="1">
<summary>Answer</summary>

The using-declaration introduces the object `std::ranges::sort`. Unqualified lookup finds an object, so per [[basic.lookup.argdep]] ADL does not take place, and `std::sort` does not become a candidate. The overload of `ranges::sort` taking an iterator and a sentinel is called. With `using std::sort;` instead, `std::sort` is called.
</details>

## Summary

| Rule | Paragraph | Consequence of violation |
|---|---|---|
| Parameter names decide iterator requirements; read-only use only needs to model the C++20 concept | ¶4 | {{ub}} |
| Predicates: return value usable as `bool`, no modification through arguments, same result for const arguments | ¶6–¶7 | {{ub}} |
| Algorithms may copy function objects freely; use `std::ref` when the same object is needed | ¶9 | |
| Algorithms must not write objects the specification does not require them to write | ¶3 | an obligation on the implementation |
| `ranges` algorithms are algorithm function objects; ADL cannot find them, and finding them turns ADL off | ¶2 | |
| Explicitly specifying template arguments for classic algorithms | ¶15 | {{unspec}} (except `min`, `max`) |
| `a + n` and `b - a` are notation | ¶11–¶13 | |
