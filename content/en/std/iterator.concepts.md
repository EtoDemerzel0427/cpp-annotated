---
title: Iterator concepts
summary: "C++20 describes iterators with a dozen or so concepts: whether they can be read, written and incremented, how they relate to sentinels, and six traversal levels from input to contiguous."
updated: 2026-10-19
---

!!! tldr
    - Which level an iterator belongs to is decided jointly by syntax (whether it has `--`, `+=`, `[]`) and the tag it declares; the tag only caps the level, and with no tag declared it is decided purely by syntax.
    - `indirectly_readable` requires dereferencing a const iterator to give the same type, so `std::optional<int>` does not count as readable; `indirectly_writable` uses two lines of `const_cast` to reject writing into temporaries returned by value.
    - C++20 iterators need not be copyable or comparable with each other; the end is represented by a **sentinel**, whose type may differ from the iterator's.
    - The key to forward iterators is the multi-pass guarantee: `a == b` implies `++a == ++b`, and incrementing a copy does not affect the original. This is a semantic requirement that the compiler does not check.
    - Contiguous iterators require dereferencing to give a real lvalue reference and conversion to a pointer with `std::to_address`, so proxy iterators are never contiguous.

C++17 described iterators with requirements tables ([[iterator.cpp17]]); C++20 rewrote them as composable concepts ([[concepts]]). Each concept has two layers of requirements. **Syntactic requirements** are written in the concept definition and checked by the compiler. **Semantic requirements** are written as "`I` models ... only if ..." and not checked by the compiler; a type that passes the syntactic check but does not meet the semantic requirements is said to satisfy but not model the concept, and handing it to the standard library is {{ifndr}} ([[res.on.requirements]]).

The concepts relate as follows, each lower one including all requirements of those above:

```text
indirectly_readable      weakly_incrementable ── incrementable
        │                        │
        │               input_or_output_iterator ─┬─ sentinel_for ── sized_sentinel_for
        │                        │                │
        └──────── input_iterator ┘          output_iterator  (+ indirectly_writable)
                       │
               forward_iterator      (+ incrementable, sentinel_for<I, I>)
                       │
            bidirectional_iterator   (+ --)
                       │
            random_access_iterator   (+ <, sized_sentinel_for<I, I>, += + -= - [])
                       │
              contiguous_iterator    (+ real lvalue reference, to_address)
```

## Which level an iterator belongs to [iterator.concepts.general]

```cpp run title="iter_concept.cpp" ok
#include <iterator>

struct I {
    using value_type = int;
    using difference_type = int;
    int operator*() const;
    I& operator++();
    I operator++(int);
    I& operator--();
    I operator--(int);
    bool operator==(I) const;
};

// C++17 view: *i is an int prvalue, which does not meet the forward iterator requirements
static_assert(std::same_as<std::iterator_traits<I>::iterator_category,
                           std::input_iterator_tag>);
// C++20 view: I declares no category, and by syntax reaches bidirectional
static_assert(std::bidirectional_iterator<I>);
static_assert(!std::random_access_iterator<I>);   // lacks += and friends

int main() {}
```

For the same type, C++17's `iterator_traits` says input iterator, while C++20's concepts say bidirectional iterator. For properties that cannot be inferred from syntax, like multi-pass or contiguous storage, both systems rely on the iterator's own declaration; the difference is where that declaration is read from.

¶1 The standard describes the reading process with two exposition-only names. If `iterator_traits<I>` is generated from the primary template, *`ITER_TRAITS(I)`* is `I` itself; if someone has specialized `iterator_traits<I>`, it is that specialization. *`ITER_CONCEPT(I)`* is taken in order as:

1. *`ITER_TRAITS(I)`*`::iterator_concept`, if it exists;
2. otherwise *`ITER_TRAITS(I)`*`::iterator_category`, if it exists;
3. otherwise, if `iterator_traits<I>` is generated from the primary template, `random_access_iterator_tag`;
4. otherwise it denotes no type.

Each traversal concept is written as `derived_from<ITER_CONCEPT(I), some_tag> && other syntactic requirements`, so the tag only serves as a cap. Rule 3 gives the highest tag when nothing is declared, which amounts to no cap: the category is decided entirely by syntax.

¶2 The `I` in the example takes exactly rule 3. Note that *`ITER_TRAITS(I)`* is `I` itself, not the `iterator_traits<I>` deduced by the primary template; otherwise it would read the deduced `input_iterator_tag` and carry C++17's conservative judgment into C++20. Note 1 describes this as the category (the `iterator_category` for C++17 interfaces) and the concept (the `iterator_concept` for C++20 interfaces) being determinable separately.

## Reading and writing

### `indirectly_readable` [iterator.concept.readable]

¶1 Types whose values can be read with `operator*` model this concept, including pointers, smart pointers and iterators:

```cpp
template<class In>
concept indirectly-readable-impl =
  requires(const In in) {
    typename iter_value_t<In>;
    typename iter_reference_t<In>;
    typename iter_rvalue_reference_t<In>;
    { *in } -> same_as<iter_reference_t<In>>;
    { ranges::iter_move(in) } -> same_as<iter_rvalue_reference_t<In>>;
  } &&
  common_reference_with<iter_reference_t<In>&&, iter_value_t<In>&> &&
  common_reference_with<iter_reference_t<In>&&, iter_rvalue_reference_t<In>&&> &&
  common_reference_with<iter_rvalue_reference_t<In>&&, const iter_value_t<In>&>;

template<class In>
concept indirectly_readable = indirectly-readable-impl<remove_cvref_t<In>>;
```

Item by item:

- The three associated types, value type, reference type and rvalue reference type, must all exist ([[iterator.assoc.types]]).
- `iter_reference_t<In>` is the type of dereferencing a non-const lvalue `In&`, whereas `in` here is a `const In`. The two must be the same, meaning the result of dereferencing does not change with whether the iterator object itself is const. Pointers, `shared_ptr` and iterators qualify; `std::optional<int>` gives `const int&` when a const object is dereferenced, so it is not `indirectly_readable`.
- The three common-reference requirements ask for a common type among the reference, the value and the rvalue reference. Generic algorithms sometimes need to handle `*it` together with an `iter_value_t` temporary (for example, `unique_copy` compares a saved value with the current element), and the common reference is a type both can bind to. Proxy iterators fit into the system by meeting these ([[iterator.cust]]).
- `remove_cvref_t` is applied first on the outside, so `indirectly_readable<const int* const&>` is the same thing as `indirectly_readable<const int*>`.

¶2 The only semantic requirement is that `*i` is equality-preserving ([[concepts.equality]]): equal iterators dereference to equal results, and repeatedly dereferencing the same iterator gives the same result.

### `indirectly_writable` [iterator.concept.writable]

```cpp
template<class Out, class T>
concept indirectly_writable =
  requires(Out&& o, T&& t) {
    *o = std::forward<T>(t);
    *std::forward<Out>(o) = std::forward<T>(t);
    const_cast<const iter_reference_t<Out>&&>(*o) = std::forward<T>(t);
    const_cast<const iter_reference_t<Out>&&>(*std::forward<Out>(o)) = std::forward<T>(t);
  };   // none of the four expressions is required to be equality-preserving
```

The first two lines are straightforward. The `const_cast`s in the last two are there to reject a kind of iterator whose `operator*` returns an ordinary object by value, say a `std::string`. Then `*o = "x"` compiles, because a temporary `string` can be assigned to, but the written value is destroyed with the temporary, and the write is silently lost.

¶6 Note 2 explains this trick. After the result of dereferencing is cast to a const rvalue:

- a real reference `T&` is still `T&` after reference collapsing and can be assigned as usual;
- proxy objects usually provide a const-qualified assignment operator, meaning that writing through a const proxy writes to the element it refers to, so they pass too;
- a `std::string` returned by value becomes `const std::string&&`, which cannot be assigned, and is rejected.

```cpp run ok
#include <iterator>
#include <string>

struct ByValue {
    using difference_type = std::ptrdiff_t;
    std::string operator*() const;
    ByValue& operator++();
    ByValue operator++(int);
};

void f(ByValue b) { *b = "x"; }   // compiles, but the value is written into a temporary
static_assert(!std::indirectly_writable<ByValue, std::string>);

int main() {}
```

C++23 added const-qualified assignment operators to `std::tuple` and `std::pair` precisely so that proxy references like the `tuple<T&...>` returned by `views::zip` pass this check ([[P2321R2]]).

¶2 Semantic requirement: if `Out` is also readable and its value type is `decay_t<T>`, then after the assignment `*o` equals the value before the assignment: what is written is what is read back. ¶3 After the assignment, `o` is no longer required to be dereferenceable. ¶4 If the source of the assignment is an xvalue, the source object is in a valid but unspecified state ([[g:valid-but-unspecified-state]]). ¶5 Note 1 sums up: the only valid use of `*o` is on the left side of an assignment, writing only once through the same value. These provisions cater for iterators like output streams that are spent after a single write.

## Incrementing

### `weakly_incrementable` [iterator.concept.winc]

```cpp
template<class I>
concept weakly_incrementable =
  movable<I> &&
  requires(I i) {
    typename iter_difference_t<I>;
    requires is-signed-integer-like<iter_difference_t<I>>;
    { ++i } -> same_as<I&>;   // not required to be equality-preserving
    i++;                      // not required to be equality-preserving
  };
```

¶1 The requirements are few: the type is movable (not necessarily copyable or comparable), the difference type is signed-integer-like, prefix `++` returns a reference to itself, and postfix `++` may return anything, including `void`. `int` itself satisfies it.

¶14 Semantic requirement: `i` is said to be **incrementable** if it is in the domain of both prefix and postfix `++`. The domains of `++i` and `i++` must be the same; if `i` is incrementable, both advance `i` to the next element, and `addressof(++i) == addressof(i)`.

¶15 Recommended practice: algorithms on such types should be single-pass, never passing through the same value twice. Note 3 gives the reason: `a == b` does not imply `++a == ++b`. When two `istream_iterator`s refer to the same stream, advancing one changes what the other sees.

### Integer-class types (¶2–¶13)

Why isn't the difference type simply required to be a signed integer? Because the difference between two iterators of `iota_view<long long, long long>` can exceed the range of `long long`, which needs a wider type.

¶2 **Integer-class types** ([[g:integer-class-type]]) are an implementation-defined set of types that behave like integers. Note 1 points out they need not be class types. ¶3 Their width is greater than that of any integral type of the same signedness. ¶4 **Integer-like types** ([[g:integer-like-type]]) are the types other than `bool` that model `integral`, plus the integer-class types; they are further divided into signed and unsigned.

```cpp run title="integer_like.cpp" ok
#include <ranges>

using D = std::ranges::range_difference_t<
    std::ranges::iota_view<long long, long long>>;
static_assert(!std::same_as<D, long long>);   // must be wider than long long

int main() {}
```

This assertion holds on every implementation. In libc++ (Clang 23), `D` is `__int128`, an extended type it treats as an integral type; MSVC STL provides a class type. Portable code should write `iter_difference_t<I>` and use only the operations listed below.

<details class="fine" markdown="1"><summary>Full specification of integer-class types</summary>

| Paragraph | Contents |
|---|---|
| ¶3 | The range of values is a contiguous interval: −2<sup>N−1</sup> to 2<sup>N−1</sup>−1 for signed, 0 to 2<sup>N</sup>−1 for unsigned; `N` is called the width |
| ¶5 | Each integer-class type `I` corresponds to a hypothetical extended integer type `B(I)` of the same signedness and width; the operations below are all described in terms of `B(I)` |
| ¶6 | Explicitly convertible to any integer-like type, implicitly convertible to integer-class types of the same signedness and no smaller width; integral types are implicitly and explicitly convertible to integer-class types; conversions do not throw, and the result is the value congruent modulo 2<sup>N</sup> |
| ¶7 | `a++`, `++a`, `&a`, unary operations, compound assignments and binary operations have the same value and effect as the corresponding operations on `B(I)`; a result of type `B(I)` maps back to `I` |
| ¶8 | Contextually convertible to `bool` as if by `bool(E != I(0))` |
| ¶9 | Models `regular` and `three_way_comparable<strong_ordering>` |
| ¶10 | Value-initialization gives 0 |
| ¶11 | `numeric_limits<I>` is specialized, with every member consistent with `numeric_limits<B(I)>` |
| ¶12 | When at least one of two integer-like types is an integer-class type, `common_type_t` is an integer-class type whose width is no less than either; if both are signed, the result is signed too |
| ¶13 | *`is-integer-like`* and *`is-signed-integer-like`* test exactly the classification of ¶4 |

</details>

### `incrementable` [iterator.concept.inc]

```cpp
template<class I>
concept incrementable = regular<I> && weakly_incrementable<I> &&
  requires(I i) { { i++ } -> same_as<I>; };
```

¶1 On top of `weakly_incrementable`, it requires the type to be `regular` (copyable, default constructible, equality comparable), postfix `++` to return `I`, and incrementing to be equality-preserving. Note 1 says this overrides the annotations in the definition of `weakly_incrementable` that say equality preservation is not required.

¶2 Semantic requirement: if `a == b`, then `a++ == b` and `((void)a++, a) == ++b`. ¶3 Note 2 points out that it is precisely `a == b` implying `++a == ++b` that makes multi-pass one-directional algorithms possible.

## Iterators and sentinels

### `input_or_output_iterator` [iterator.concept.iterator]

```cpp
template<class I>
concept input_or_output_iterator =
  requires(I i) { { *i } -> can-reference; } && weakly_incrementable<I>;
```

¶1 This is the root of the whole system, modeled by every iterator: it can be dereferenced (to something other than `void`) and incremented. ¶2 Note 1 stresses that unlike C++17's *Cpp17Iterator*, it does not require copyability. A move-only input iterator wrapping an exclusive resource is a valid iterator in C++20.

### `sentinel_for` [iterator.concept.sentinel]

```cpp
template<class S, class I>
concept sentinel_for =
  semiregular<S> && !is-integer-like<S> &&
  input_or_output_iterator<I> && weakly-equality-comparable-with<S, I>;
```

¶1 A sentinel is a value denoting the end of a range. It can be compared with the iterator using `==` and `!=` ([[concepts.equalitycomparable]]), and must itself be copyable and default constructible, so that it can be stored in views and passed to multiple algorithms. `std::unreachable_sentinel_t` and `std::default_sentinel_t` are common sentinel types.

A sentinel cannot be an integer-like type. Integers have another meaning in the ranges library, a number of steps, as in `ranges::advance(it, 5)`; if integers could also be sentinels, such calls would be ambiguous.

¶2 Let `[i, s)` denote a range. The semantic requirements for `S` and `I` to model `sentinel_for` are:

1. `i == s` is well-defined;
2. if `i != s`, then `i` is dereferenceable and `[++i, s)` denotes a range too;
3. `assignable_from<I&, S>` is either modeled or not satisfied at all;
4. if `I` and `S` are the same type, `i == i` is true.

Rule 3 guards against sentinels that can be assigned but with the wrong meaning. `ranges::advance(i, bound)` simply does `i = bound` when assignment is possible ([[range.iter.op.advance]]), which is correct only if the result of the assignment really is reaching the end.

¶3 contains a sentence that is easy to overlook:

!!! std
    The domain of == is not static.

Meaning: when `[i, s)` denotes a range and `i != s`, incrementing some other iterator equal to `i` means `i` and `s` are no longer guaranteed to denote a range, and `i == s` is no longer guaranteed to be well-defined. This is again the `istream_iterator` situation: two copies share one stream, and advancing one makes the other stale.

### `sized_sentinel_for` [iterator.concept.sizedsentinel]

```cpp
template<class S, class I>
concept sized_sentinel_for =
  sentinel_for<S, I> &&
  !disable_sized_sentinel_for<remove_cv_t<S>, remove_cv_t<I>> &&
  requires(const I& i, const S& s) {
    { s - i } -> same_as<iter_difference_t<I>>;
    { i - s } -> same_as<iter_difference_t<I>>;
  };
```

¶1 This concept says the distance from an iterator to a sentinel can be computed with `-` in constant time. ¶2 Let `N` be the smallest number of `++i` needed to make `i == s`; then `s - i == N` if `N` is representable, and `i - s == -N` if `-N` is representable. ¶5 Example 1 notes that a pair of random access iterators, and `counted_iterator` with `default_sentinel_t`, both model it.

Constant time is a semantic requirement, and the library trusts it and optimizes on that basis, for example by getting a range's size directly from `s - i`. If some type has a `-` operator that is linear time, or whose meaning is not a distance at all, an opt-out switch is needed:

¶3–¶4 `disable_sized_sentinel_for<S, I>` is a variable template defaulting to `false`. When `S` or `I` is a program-defined type, users may specialize it to `true`; the specialization must be usable in constant expressions and have type `const bool`. Note 1 says it exists for types that satisfy but do not model the concept.

The standard library uses this switch itself. The `operator-` of `reverse_iterator` and `move_iterator` is declared for any underlying iterator, so [[iterator.synopsis]] disables the corresponding combinations when the underlying iterators do not model `sized_sentinel_for`.

## The six traversal levels

### `input_iterator` [iterator.concept.input]

```cpp
template<class I>
concept input_iterator =
  input_or_output_iterator<I> && indirectly_readable<I> &&
  requires { typename ITER_CONCEPT(I); } &&
  derived_from<ITER_CONCEPT(I), input_iterator_tag>;
```

¶1 Readable and incrementable. Note 1 says it does not require `==`, because iterators are usually compared with sentinels rather than with other iterators. Nor does it require copyability, or that postfix `++` return anything.

### `output_iterator` [iterator.concept.output]

```cpp
template<class I, class T>
concept output_iterator =
  input_or_output_iterator<I> && indirectly_writable<I, T> &&
  requires(I i, T&& t) { *i++ = std::forward<T>(t); };
```

¶1 Writable and incrementable; Note 1 points out that equality comparison is not required. ¶2 The semantic requirement is that `*i++ = E;` is equivalent to `*i = E; ++i;`. ¶3 The recommended practice is single-pass.

It differs from the other five levels in two ways: it does not look at *`ITER_CONCEPT`*, so whether something can output is decided purely by syntax; and it takes a value type parameter `T`, because the types an iterator can write form a set.

### `forward_iterator` [iterator.concept.forward]

```cpp
template<class I>
concept forward_iterator =
  input_iterator<I> && derived_from<ITER_CONCEPT(I), forward_iterator_tag> &&
  incrementable<I> && sentinel_for<I, I>;
```

¶1 Adds copyability, equality comparison and the multi-pass guarantee on top of input iterators. There are three semantic requirements:

- ¶2 The domain of `==` is iterators into the same sequence. The exception is value-initialized iterators of the same type, which can be compared with each other and are equal; Note 1 says they behave as if they pointed past the end of the same empty sequence.
- ¶3 Pointers and references obtained from a forward iterator remain valid while `[i, s)` still denotes a range. So elements cannot be stored inside the iterator object; compare [[iterator.requirements.general#15]].
- ¶4 The **multi-pass guarantee** ([[g:multi-pass-guarantee]]): for two dereferenceable `a` and `b`, `a == b` implies `++a == ++b`; and `((void)[](X x){++x;}(a), *a)` is equivalent to `*a`, that is, incrementing a copy of `a` does not affect `a`.

¶5 Note 2 explains that the multi-pass guarantee, together with being able to assign multiple times through a mutable iterator (a freedom output iterators lack), makes one-directional algorithms that need to look back, such as `search` and `adjacent_find`, possible.

### `bidirectional_iterator` [iterator.concept.bidir]

```cpp
template<class I>
concept bidirectional_iterator =
  forward_iterator<I> && derived_from<ITER_CONCEPT(I), bidirectional_iterator_tag> &&
  requires(I i) {
    { --i } -> same_as<I&>;
    { i-- } -> same_as<I>;
  };
```

¶2 If there exists some `q` such that `++q == r`, then `r` is said to be **decrementable**; a decrementable `r` must be in the domain of `--r` and `r--`. An iterator to the first element is not decrementable.

¶3 The semantic requirements make `--` the inverse of `++`. For equal `a` and `b`: if decrementable, `addressof(--a) == addressof(a)`, `a-- == b`, they remain equal after each is decremented, and `++(--a) == b`; if incrementable, `--(++a) == b`.

### `random_access_iterator` [iterator.concept.random.access]

```cpp
template<class I>
concept random_access_iterator =
  bidirectional_iterator<I> && derived_from<ITER_CONCEPT(I), random_access_iterator_tag> &&
  totally_ordered<I> && sized_sentinel_for<I, I> &&
  requires(I i, const I j, const iter_difference_t<I> n) {
    { i += n } -> same_as<I&>;
    { j +  n } -> same_as<I>;
    { n +  j } -> same_as<I>;
    { i -= n } -> same_as<I&>;
    { j -  n } -> same_as<I>;
    {  j[n]  } -> same_as<iter_reference_t<I>>;
  };
```

¶1 Adds constant-time `+=`, `+`, `-=` and `-`, constant-time distance computation, and subscripting. `j[n]` must return exactly `iter_reference_t<I>`; C++17's *Cpp17RandomAccessIterator* only required it to be convertible to `reference`.

¶2 Twelve semantic requirements say that these operations mean taking `n` steps: let `b` be obtained by incrementing `a` `n` times; then `(a += n) == b`, `a + n` equals `a += n`, `(b -= n) == a`, `a + D(0) == a`, `a + D(x + y)` equals `(a + x) + y`, `a[n] == *b` if `b` is dereferenceable, `a <= b`, and so on.

### `contiguous_iterator` [iterator.concept.contiguous]

```cpp
template<class I>
concept contiguous_iterator =
  random_access_iterator<I> && derived_from<ITER_CONCEPT(I), contiguous_iterator_tag> &&
  is_lvalue_reference_v<iter_reference_t<I>> &&
  same_as<iter_value_t<I>, remove_cvref_t<iter_reference_t<I>>> &&
  requires(const I& i) {
    { to_address(i) } -> same_as<add_pointer_t<iter_reference_t<I>>>;
  };
```

¶1 Elements are stored contiguously in memory. Syntactically, dereferencing must yield a real lvalue reference which, with cv and reference removed, is the value type, so proxy iterators can never be contiguous. It must also be possible to get a pointer with `std::to_address` ([[pointer.conversion]]): for class-type iterators, that prefers calling `pointer_traits<I>::to_address`, and otherwise calls `i.operator->()`.

¶2 Let `a` and `b` be dereferenceable and `c` not, with `b` reachable from `a` and `c` reachable from `b`, and let `D` be the difference type. The semantic requirements are:

1. `to_address(a) == addressof(*a)`;
2. `to_address(b) == to_address(a) + D(b - a)`;
3. `to_address(c) == to_address(a) + D(c - a)`, i.e. the past-the-end iterator can be converted to a pointer too, pointing exactly one past the last element;
4. `to_address(I{})` is well-defined;
5. `ranges::iter_move(a)` has the same type, value category and effects as `std::move(*a)`;
6. if `ranges::iter_swap(a, b)` is well-formed, its effect is equivalent to `ranges::swap(*a, *b)`.

The last two are prerequisites of [[iterator.requirements.general#13]]. That paragraph lets the library replace contiguous iterators with pointers at any time; if users could change behavior by customizing `iter_move` and `iter_swap`, such a replacement would change the meaning of the program.

## Which level standard library types reach

```cpp run title="where.cpp" ok
#include <deque>
#include <forward_list>
#include <iterator>
#include <list>
#include <ranges>
#include <string>
#include <vector>

static_assert(std::contiguous_iterator<std::vector<int>::iterator>);
static_assert(std::contiguous_iterator<std::string::const_iterator>);
static_assert(std::random_access_iterator<std::deque<int>::iterator>
           && !std::contiguous_iterator<std::deque<int>::iterator>);
static_assert(std::bidirectional_iterator<std::list<int>::iterator>);
static_assert(std::forward_iterator<std::forward_list<int>::iterator>);
static_assert(std::input_iterator<std::istream_iterator<int>>
           && !std::forward_iterator<std::istream_iterator<int>>);
static_assert(std::output_iterator<std::ostream_iterator<int>, int>
           && !std::input_iterator<std::ostream_iterator<int>>);
// proxy iterator: random access, but not contiguous
static_assert(std::random_access_iterator<std::vector<bool>::iterator>
           && !std::contiguous_iterator<std::vector<bool>::iterator>);

// move-only input iterator: valid in C++20, not in C++17
struct MoveOnly {
    using value_type = int;
    using difference_type = std::ptrdiff_t;
    MoveOnly(MoveOnly&&) = default;
    MoveOnly& operator=(MoveOnly&&) = default;
    int operator*() const;
    MoveOnly& operator++();
    void operator++(int);
};
static_assert(std::input_iterator<MoveOnly> && !std::copyable<MoveOnly>);

int main() {}
```

## Common misconceptions

!!! pitfall "Satisfying `forward_iterator` makes it a forward iterator"
    The multi-pass guarantee, references not pointing into the iterator itself, and the domain of `==` are all semantic requirements. A generator-style iterator that caches the current element inside itself passes the syntactic check as soon as it declares `forward_iterator_tag`; but it only satisfies the concept without modeling it, and handing it to algorithms that rely on multi-pass or reference stability is {{ifndr}}. When in doubt, declare `input_iterator_tag`.

!!! pitfall "Writing only `iterator_category` lowers the C++20 category"
    Without `iterator_concept`, *`ITER_CONCEPT`* reads `iterator_category`. A random-access proxy iterator that honestly tells C++17 interfaces it does not meet *Cpp17ForwardIterator* by writing `iterator_category = input_iterator_tag` is pushed down to `input_iterator` in C++20 as well. Write both: `iterator_category = input_iterator_tag` and `iterator_concept = random_access_iterator_tag`. The iterators of `iota_view` and `views::transform` do exactly that.

!!! pitfall "Using the result of `i++` on an input iterator"
    `weakly_incrementable` places no requirement on the type of `i++`; only `incrementable` requires it to return `I`. The `operator++(int)` of input iterators often returns `void`; the standard library's `move_iterator` and `basic_const_iterator` do so when the underlying iterator is not a forward iterator. Generic code should write only `++i` for non-forward iterators.

## Questions

!!! question "Question 1"
    Is `int` `weakly_incrementable`? Is it an `input_or_output_iterator`? Why can `std::unreachable_sentinel_t` be compared with `int`?

<details markdown="1">
<summary>Answer</summary>

`int` is movable, its difference type is `int` ([[incrementable.traits]]), and `++i` returns `int&`, so it models `weakly_incrementable`, and even `incrementable`. But `*i` is not valid, so it is not an `input_or_output_iterator`.

The `operator==` of `unreachable_sentinel_t` constrains the other side only to be `weakly_incrementable` ([[unreachable.sentinel]]), so it can be compared with `int`, which lets `views::iota(0)` have no end. Still, `sentinel_for<unreachable_sentinel_t, int>` is false, because `int` is not an iterator.
</details>

!!! question "Question 2"
    `std::shared_ptr<int>` is `indirectly_readable`, `std::optional<int>` is not. Both have `operator*`; what is the difference?

<details markdown="1">
<summary>Answer</summary>

The concept requires the type of `*in` (with `in` a const object) to be the same as `iter_reference_t<In>` (the type of dereferencing a non-const lvalue). `shared_ptr` is shallowly const: dereferencing a const `shared_ptr<int>` still gives `int&`; `optional` is deeply const: dereferencing a const `optional<int>` gives `const int&`, which differs from `int&`. An `optional` is a container holding a value, not a handle referring elsewhere, and that distinction is exactly what the concept aims to capture.
</details>
