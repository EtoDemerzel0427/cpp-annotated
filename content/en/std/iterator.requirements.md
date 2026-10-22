---
title: "Iterator requirements: values and ranges"
summary: "The basic vocabulary of the iterators library: value types and difference types, the six categories, dereferenceable, past-the-end and singular values, ranges and counted ranges, valid ranges, and why calling a library function on an invalid range is undefined behavior."
updated: 2026-10-19
---

!!! tldr
    - Iterator values come in three kinds: dereferenceable, past-the-end and singular. A singular value belongs to no sequence, and apart from destroying it, assigning to it and (when value-initialized) copying it, anything done with it is undefined behavior.
    - A range can be written two ways: a start plus a sentinel `[i, s)`, or a start plus a count `i+[0, n)`. `[i, s)` is a valid range only if `s` can be reached from `i` by a finite number of `++`.
    - Calling a library function on an invalid range has undefined results. Swapping the beginning and end, or taking them from different containers, are such cases, and the compiler cannot detect them.
    - For contiguous iterators the library may switch to raw pointers, so do not rely on side effects of dereferencing or incrementing.
    - An iterator that is not a forward iterator may store the current element inside itself; once the iterator is destroyed, references previously obtained from it dangle.

[iterator.requirements] has seven subclauses: the general part [iterator.requirements.general], associated types ([[iterator.assoc.types]]), two customization points ([[iterator.cust]]), C++20 concepts ([[iterator.concepts]]), C++17 named requirements ([[iterator.cpp17]]), indirect callable concepts ([[indirectcallable]]), and common algorithm requirements ([[alg.req]]). The general part defines two basic notions used everywhere else: the values of iterators, and ranges.

## What properties an iterator has (¶1–¶6)

### Value type and difference type (¶1)

¶1 Iterators are a generalization of pointers. To let template algorithms work correctly and efficiently on all kinds of data structures, the library specifies not only the interface of iterators but also their semantics and complexity.

- An input iterator `i` supports `*i`, whose result is a value of some object type `T`, called the **value type** of the iterator ([[g:iterator-value-type]]).
- An output iterator has a set of writable types: for a value `o` of each such `T`, `*i = o` is valid.
- Every iterator type has a **difference type** ([[g:iterator-difference-type]]), which is a signed integer-like type ([[iterator.concept.winc]]).

Integer-like means the difference type need not be a built-in integer; it can also be an implementation-provided **integer-class type** ([[g:integer-class-type]]). The distance between two iterators of `iota_view<long long>` may exceed `long long`, which calls for such a wider type.

### Six categories (¶2–¶4)

¶2 The semantics of iterators are a generalization of those of pointers, which ensures that function templates taking iterators work equally well with ordinary pointers. The standard divides iterators into six categories by the operations they support: input, output, forward, bidirectional, random access and contiguous.

¶3 The six categories correspond to six concepts: `input_iterator`, `output_iterator`, `forward_iterator`, `bidirectional_iterator`, `random_access_iterator` and `contiguous_iterator`. "Iterator" in general means any type that models `input_or_output_iterator`.

¶4 The categories can be substituted for one another: a forward iterator meets all the requirements of an input iterator and can be used wherever one is required; likewise bidirectional for forward, random access for bidirectional, and contiguous for random access. Output iterators are not on this chain.

### Mutable and constant iterators (¶5)

¶5 Iterators that also meet the output iterator requirements are called **mutable iterators** ([[g:mutable-iterator]]); the rest are **constant iterators** ([[g:constant-iterator]]). `vector<int>::iterator` is mutable, `vector<int>::const_iterator` is constant. C++23's `basic_const_iterator` ([[const.iterators]]) can wrap any input iterator into a constant iterator.

### Associated types must be discoverable (¶6)

¶6 An iterator type must provide the nested type names specified in [[iterator.traits]]. Note 1 gives two ways: declare them in the type itself, and `iterator_traits` picks them up automatically; or specialize `iterator_traits`. Since C++20 you can also write neither and let the `iterator_traits` primary template deduce them from expressions ([[iterator.assoc.types]]).

## The three kinds of iterator values (¶7)

¶7 By analogy with pointers into arrays, iterator values come in three kinds:

| Value | Meaning | What can be done |
|---|---|---|
| **Dereferenceable** ([[g:dereferenceable-iterator]]) | `*i` is defined | Dereference; increment and decrement according to category |
| **Past-the-end** ([[g:past-the-end-value]]) | Points past the last element of a sequence | Compare; decrement according to category; the library never assumes it is dereferenceable |
| **Singular** ([[g:singular-value]]) | Not associated with any sequence | Almost nothing |

!!! std
    Results of most expressions are undefined for singular values;

    That is, evaluating almost any expression on a singular value gives an undefined result.

Only three operations are allowed on an iterator holding a singular value:

1. destroying it;
2. assigning a non-singular value to it, in which case the singular value is overwritten like any other value;
3. if the iterator type meets *Cpp17DefaultConstructible*, using a **value-initialized** iterator as the source of a copy or move.

Anything else, such as copying a default-initialized iterator, applying `++` to it, or comparing two singular iterators, is {{ub}}. A dereferenceable value is never singular.

```cpp run title="singular.cpp" ok
#include <vector>

int main() {
  std::vector<int>::iterator a;     // default-initialized: singular
  std::vector<int>::iterator b{};   // value-initialized: singular, but copyable
  auto c = b;                       // OK: exception 3
  // auto d = a;                    // UB: copying a default-initialized singular iterator
  bool e = (b == c);                // OK, and true; see below for why
  a = c;                            // OK: assigning to a singular iterator
  (void)a; (void)e;
}
```

Exception 3 holds only for value-initialization (`It it{};`, `It()`). Note 2 points out that the difference between default- and value-initialization matters in practice only for types with a trivial default constructor, such as pointers and aggregates containing pointers: `int* p;` is uninitialized, while `int* p{};` is a null pointer.

`b == c` is valid, but the permission does not come from ¶7. Forward iterators have an extra guarantee: value-initialized iterators of the same type can be compared with each other and are equal, as if they all pointed past the end of the same empty sequence ([[iterator.concept.forward#2]]).

!!! impl "What libc++ does"
    libc++'s `vector<T>::iterator` is `__wrap_iter<T*>`, whose default constructor is written `__wrap_iter() noexcept : __i_() {}`, so the internal pointer is nulled even under default-initialization. So on libc++, `auto d = a;` does not actually misbehave. But at the level of the standard `a` is still singular, and with another implementation or with debug iterators turned on, it may be diagnosed.

!!! lawyer "Relationship with C++26 erroneous values"
    `int* p; int* q = p;` is **erroneous behavior** in C++26's core language, not UB: an uninitialized automatic variable holds an erroneous value ([[basic.indet]]). But ¶7 is a library rule: passing such a `p` to a library function as an iterator still lets the library say the result is undefined. The core language governs reading the value itself; the library governs what happens after it is used as an iterator.

## Ranges (¶8–¶13)

### Two notations (¶8)

¶8 Most of the library's algorithms take **ranges** as their interface. A range has two representations:

- an iterator plus a **sentinel**, written `[i, s)`, marking where a computation starts and ends;
- an iterator plus a count, written `i+[0, n)`, marking the start and the number of elements.

Footnote 177 says the sentinel can have the same type as the iterator or a different one.

### Which elements `[i, s)` contains (¶9)

¶9 The iterator and sentinel denoting a range must be comparable. If `i == s`, the range is empty; otherwise `[i, s)` starts with the element `i` points to and goes up to, but not including, the element pointed to by the first iterator `j` such that `j == s`.

Note "the first". For `[p, unreachable_sentinel)` no such `j` exists, and the range has no end.

### Reachability and valid ranges (¶10)

!!! std
    A sentinel s is called *reachable from* an iterator i if and only if there is a finite sequence of applications of the expression ++i that makes i == s.

    In other words, `s` is **reachable** from `i` ([[g:reachable-sentinel]]) when applying `++i` a finite number of times makes `i == s`.

¶10 If `s` is reachable from `i`, then `[i, s)` is a **valid range** ([[g:valid-range]]). Validity is a run-time property that the type system cannot express. `std::find(v.end(), v.begin(), x)` compiles, but for a non-empty `v`, incrementing from `end()` never reaches `begin()`, so this is not a valid range.

### Counted ranges (¶11)

¶11 The definition of a **counted range** ([[g:counted-range]]) `i+[0, n)` is recursive: if `n == 0` it is empty and valid; otherwise it is valid if and only if `n` is positive, `i` is dereferenceable, and `++i+[0, --n)` is valid. `std::copy_n`, `counted_iterator` ([[iterators.counted]]) and `views::counted` are all based on this model: you need not know where the end is, only how many elements remain.

### Invalid ranges are undefined behavior (¶12)

!!! std
    The result of the application of library functions to invalid ranges is undefined.

    That is, calling a library function on an invalid range has undefined results.

¶12 This rule covers many situations: swapping the beginning and end, taking them from different containers, or modifying the container during traversal so that some iterator is invalidated all fall here.

```cpp run title="invalid_range.cpp" ok
#include <algorithm>
#include <vector>

int main() {
  std::vector<int> a{1, 2, 3}, b{4, 5, 6};
  auto n1 = std::count(a.begin(), a.end(), 2);    // OK
  // auto n2 = std::count(a.begin(), b.end(), 2); // UB: b.end() is not reachable from a.begin()
  // auto n3 = std::count(a.end(), a.begin(), 2); // UB: likewise
  return static_cast<int>(n1) - 1;
}
```

### Contiguous iterators can be replaced by pointers (¶13)

¶13 For an `i` that models `contiguous_iterator`, library functions may replace `[i, s)` with `[to_address(i), to_address(i + ranges::distance(i, s)))`, and `i+[0, n)` with `[to_address(i), to_address(i + n))`.

Note 3 spells out the consequence: programs cannot rely on side effects of dereferencing a contiguous iterator or of incrementing it step by step. The library may never call your `operator*` and `operator++` at all, instead taking raw pointers and calling `memmove` directly, or jumping to the end with a single `i + n`. Adding an access counter to the `operator*` of a contiguous iterator gives unreliable numbers.

## Other rules (¶14–¶17)

### Only operations implementable in constant time are required (¶14)

¶14 Each category requires only those operations that can be implemented in constant time (possibly amortized) for that category, so the requirements tables and concept definitions state no complexity. That is why `std::list`'s iterators have no `operator+`: not because it cannot be done, but because it cannot be done in constant time. To move several steps, use `std::advance` or `ranges::next` ([[iterator.primitives]]).

### Destroying an iterator may invalidate references (¶15)

!!! std
    Destruction of an iterator may invalidate pointers and references previously obtained from that iterator if its type does not meet the *Cpp17ForwardIterator* requirements and does not model forward_iterator.

    That is, if an iterator type neither meets *Cpp17ForwardIterator* nor models `forward_iterator`, destroying an iterator may invalidate pointers and references obtained from it earlier.

¶15 This rule lets input iterators store the current element inside themselves. `istream_iterator<T>` does exactly that, and `*it` returns a reference to its member ([[istream.iterator]]). So the following dangles:

```cpp
const int& r = *std::istream_iterator<int>(std::cin);
// the temporary iterator is destroyed at the end of the full-expression; r dangles
```

Forward iterators cannot do this. [[iterator.concept.forward#3]] requires pointers and references obtained from `[i, s)` to stay valid as long as it remains a range. A type that stores its element inside itself does not model `forward_iterator`, even if it satisfies it syntactically. `reverse_iterator`'s `operator*` copies, decrements and then dereferences, so used with such a type it returns a dangling reference ([[reverse.iterators]]).

### Invalid iterators (¶16)

¶16 An **invalid iterator** ([[g:invalid-iterator]]) is an iterator that may be singular. Footnote 178 adds two points: the definition applies to pointers as well, and dereferencing an invalidated iterator has undefined behavior. The "invalidates iterators" rules in the container clauses (as after a `vector::push_back` reallocates) refer to this state: the iterator need not really become singular, but the program can no longer assume it is not.

### constexpr iterators (¶17)

¶17 If all the operations provided to meet the category requirements are constexpr functions, the iterator meets the **constexpr iterator** requirements ([[g:constexpr-iterator]]). Note 4 gives `int*` and `reverse_iterator<int*>` as examples. Calling constexpr algorithms such as `std::sort` during constant evaluation needs such iterators.

## Common misconceptions

!!! pitfall "If it compiles, it is a valid range"
    The type system can only check that the iterator and sentinel can be compared (`sentinel_for`), not whether the sentinel is reachable. Reachability is always the caller's precondition. The `ranges::` algorithms write it into the semantic requirements of [[iterator.concept.sentinel]], which the compiler does not check either.

!!! pitfall "A value-initialized iterator is the begin of an empty range"
    `It{}` has the "as if past the end of the same empty sequence" semantics only for forward iterators, and can only be compared with value-initialized iterators of the same type. Comparing it with some container's `end()` is still UB, because they do not belong to the same sequence.

## Questions

!!! question "Question 1"
    In `std::vector<int> v; auto b = v.begin(), e = v.end();`, are `b` and `e` singular? Is `[b, e)` a valid range?

<details markdown="1">
<summary>Answer</summary>

They are not singular; they are associated with the empty sequence `v`. `b == e` is true and is reached with zero `++`, so `[b, e)` is a valid empty range (¶9, ¶10). `b` is a past-the-end value and is not dereferenceable.
</details>

!!! question "Question 2"
    ¶7 allows value-initialized iterators only as copy sources. Why not simply declare that value-initialized iterators are not singular?

<details markdown="1">
<summary>Answer</summary>

A value-initialized iterator really is not associated with any sequence, so by definition it is singular. Allowing it to be copied makes code like `It tmp{}; ... tmp = other;` well-defined. The stronger guarantee of comparability is given only to forward iterators ([[iterator.concept.forward#2]]).
</details>

!!! question "Question 3"
    A type caches the current element in itself, its `operator*` returns a reference to that member, and all its other operations satisfy the syntax of `forward_iterator`. Is `std::forward_iterator<It>` true? What happens if you pass it to `std::ranges::reverse_view`?

<details markdown="1">
<summary>Answer</summary>

It is true, because a concept checks only syntax. But the type violates the semantic requirement of [[iterator.concept.forward#3]], so it only satisfies `forward_iterator` without modeling it. Per [[res.on.requirements#2]], when the meaning of a program depends on a concept that is satisfied but not modeled, the program is {{ifndr}}. At run time, `reverse_iterator::operator*` copies, decrements and then dereferences, and the returned reference refers to a destroyed temporary copy.
</details>
