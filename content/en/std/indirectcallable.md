---
title: Indirect callable requirements and projected
summary: "The six concepts that constrain predicates, comparators and projections in algorithms, and projected, which combines an iterator and a projection into a new iterator type."
updated: 2026-10-19
---

!!! tldr
    - The indirect callable concepts check the relation between a callable object and the result of dereferencing an iterator, not some value type.
    - Each concept requires `F` to be copyable, to be invoked as an lvalue `F&`, and to accept two kinds of argument: an lvalue of the value type and the result of `*it`.
    - So for a predicate on `vector<bool>`, accepting only `bool&` or only the proxy class does not work; writing `const auto&` or a generic lambda is the safest.
    - `projected<I, Proj>` is a type used only in constraints, whose reference type is the result of the projection; it lets algorithms write "project, then compare" as a single constraint.
    - A comparator that is not a strict weak ordering (for example `<=`) merely satisfies without modeling, and passing it to `ranges::sort` is {{ifndr}}.

```cpp run title="indirect.cpp" ok
#include <algorithm>
#include <cassert>
#include <string>
#include <vector>

struct Person { std::string name; int age; };

int main() {
    std::vector<Person> v{{"bob", 30}, {"alice", 25}, {"carol", 35}};
    std::ranges::sort(v, std::ranges::less{}, &Person::age);   // sort by age
    assert(v.front().name == "alice");

    auto it = std::ranges::find(v, "carol", &Person::name);    // compare after projecting
    assert(it != v.end() && it->age == 35);
}
```

Most C++20 algorithms accept callable objects, and many also accept a **projection** ([[defns.projection]]): a transformation applied to each element before comparing or testing it, like `&Person::age` above. This subclause defines the concepts constraining these parameters.

¶1 [indirectcallable.general] has a single sentence: the concepts below gather the requirements of algorithms that take callable objects. "Indirect" in their names means that `F` must be usable on the result of dereferencing an iterator.

## Six concepts [indirectcallable.indirectinvocable]

¶1 The six concepts have almost the same shape; take the unary one as an example:

```cpp
template<class F, class I>
concept indirectly_unary_invocable =
  indirectly_readable<I> &&
  copy_constructible<F> &&
  invocable<F&, indirect-value-t<I>> &&
  invocable<F&, iter_reference_t<I>> &&
  common_reference_with<
    invoke_result_t<F&, indirect-value-t<I>>,
    invoke_result_t<F&, iter_reference_t<I>>>;
```

For ordinary iterators, *`indirect-value-t<I>`* is just `iter_value_t<I>&`, an lvalue of the value type (the full definition is in the next-but-one section). `iter_reference_t<I>` is the type of `*it` ([[iterator.assoc.types]]).

| Concept | Requirement on `F&` | Used by, for example |
|---|---|---|
| `indirectly_unary_invocable<F, I>` | `invocable`, and the two results have a common reference | `ranges::for_each` |
| `indirectly_regular_unary_invocable<F, I>` | `regular_invocable`, same as above | Projections (through `projected`) |
| `indirect_unary_predicate<F, I>` | `predicate` | `find_if`, `count_if`, `all_of` |
| `indirect_binary_predicate<F, I1, I2>` | `predicate` under all four argument combinations | `adjacent_find`; `equal` and `search` through `indirectly_comparable` |
| `indirect_equivalence_relation<F, I1, I2 = I1>` | `equivalence_relation` under all four combinations | `unique`, `unique_copy` |
| `indirect_strict_weak_order<F, I1, I2 = I1>` | `strict_weak_order` under all four combinations | `lower_bound`; `sort` through `sortable` |

Each requirement has a reason:

1. `copy_constructible<F>`: algorithms may copy the function object by value.
2. Invoked as `F&`: inside the algorithm a named function object is held and called repeatedly. A function object with only `operator() &&` is not accepted.
3. Both kinds of argument are tested: an algorithm may call directly on `*it`, or copy the element into a value first and call on that. When `ranges::unique_copy` processes input iterators, it has to store the previous element as an `iter_value_t` object and compare it with the current `*it`. The binary concepts therefore test 2×2 = 4 combinations, leaving algorithm implementations free to choose.

The semantic requirements all come from [[concepts.callable]]: `predicate` must be equality-preserving, `equivalence_relation` reflexive, symmetric and transitive, `strict_weak_order` irreflexive and transitive with transitive incomparability. `<=` passes the syntactic check but is not a strict weak ordering.

The two kinds of argument are the same type for most containers; the difference shows up with proxy iterators:

```cpp run ok
#include <iterator>
#include <vector>

using VB = std::vector<bool>::iterator;
// indirect-value-t<VB> is bool&, iter_reference_t<VB> is the proxy class vector<bool>::reference
struct A { bool operator()(bool&) const; };
struct B { bool operator()(std::vector<bool>::reference) const; };
struct C { bool operator()(const bool&) const; };

static_assert(!std::indirect_unary_predicate<A, VB>);   // cannot accept the proxy
static_assert(!std::indirect_unary_predicate<B, VB>);   // cannot accept bool&
static_assert( std::indirect_unary_predicate<C, VB>);   // the proxy converts to bool

int main() {}
```

`indirect_result_t<F, Is...>` is the accompanying result type alias, namely `invoke_result_t<F, iter_reference_t<Is>...>`, requiring each `Is` to be readable and `F` to be invocable with their references ([[iterator.synopsis]]).

## `projected` [projected]

¶1 `projected` combines a readable type `I` and a projection type `Proj` into a new readable type, whose reference type is the result of applying `Proj` to `iter_reference_t<I>`:

```cpp
template<class I, class Proj>
struct projected-impl {
  struct type {
    using value_type = remove_cvref_t<indirect_result_t<Proj&, I>>;
    using difference_type = iter_difference_t<I>;   // only if I models weakly_incrementable
    indirect_result_t<Proj&, I> operator*() const;   // not defined
  };
};

template<indirectly_readable I, indirectly_regular_unary_invocable<I> Proj>
  using projected = projected-impl<I, Proj>::type;
```

`operator*` is declared but not defined; nobody ever really creates such an object. It is used only to write constraints, for example:

```cpp
template<random_access_iterator I, sentinel_for<I> S,
         class Comp = ranges::less, class Proj = identity>
  requires sortable<I, Comp, Proj>   // includes indirect_strict_weak_order<Comp, projected<I, Proj>>
constexpr I ranges::sort(I first, S last, Comp comp = {}, Proj proj = {});
```

The comparator faces not `I` but the projected `projected<I, Proj>`, so the six concepts of the previous section need no separate versions for projections.

`projected` requires the projection to model `indirectly_regular_unary_invocable`, i.e. to be equality-preserving: the same input gives the same output. A projection involving random numbers or counters merely satisfies the syntax without modeling it.

The reference type of `projected<int*, std::identity>` is `int&`, and its `value_type` is `int`.

### Why the extra nested class

C++20 originally defined `projected<I, Proj>` directly as a class template. The problem was argument-dependent lookup (ADL, [[basic.lookup.argdep]]): when a function is called with it as an argument type, the associated namespaces and classes of `I` and `Proj` are searched; if one of them is an incomplete type, or a class template that triggers a hard error, merely checking a constraint could fail.

C++23 changed it to an alias for the nested class `projected-impl<I, Proj>::type` of a class template ([[P2538R1]]). The template arguments of the enclosing class template of a nested class are not its associated entities, so ADL no longer sees `I` and `Proj`.

## *`indirect-value-t`* [indirectcallable.traits]

¶1 When implementing algorithms with projections, one needs to know what type an iterator's value has after projection. *`indirect-value-t<T>`* is defined as:

- if `T` is `projected<I, Proj>`, `invoke_result_t<Proj&, indirect-value-t<I>>`;
- otherwise `iter_value_t<T>&`.

For a projected iterator, it recursively applies the projection to the value lvalue of the underlying iterator, which is exactly the type an algorithm actually gets when it copies out a value first and then projects it.

C++20 originally used `iter_value_t<T>&` directly here. For `projected<I, Proj>`, that is an lvalue of the projection result with cv and reference removed; when the projection returns a proxy or a non-copyable type, it differs from the type the algorithm actually uses, and some correct callable objects were rejected. C++23's [[P2609R3]] introduced *`indirect-value-t`* to fix this. `iter_common_reference_t<T>` was redefined in terms of it at the same time ([[iterator.synopsis]]).

## Questions

!!! question "Question 1"
    Why does the predicate below not satisfy `indirect_unary_predicate<NeedsMutable, const int*>` but satisfy `indirect_unary_predicate<NeedsMutable, int*>`?
    ```cpp
    struct NeedsMutable { bool operator()(int&) const { return true; } };
    ```

<details markdown="1">
<summary>Answer</summary>

For `const int*`, *`indirect-value-t`* is `iter_value_t<const int*>&`, i.e. `int&` (the value type drops const), while `iter_reference_t` is `const int&`. `NeedsMutable` accepts the former but not the latter, so it does not satisfy the concept. For `int*`, both are `int&`.
</details>

!!! question "Question 2"
    Why do the binary concepts test four combinations instead of just `(iter_reference_t<I1>, iter_reference_t<I2>)`?

<details markdown="1">
<summary>Answer</summary>

An algorithm may store the elements of one side as values first and then compare them with references from the other side. `ranges::unique_copy` does this for input iterators, so the comparator receives (an lvalue of the value, a reference). By requiring all combinations to be usable, and through requirements like `strict_weak_order` that they be semantically consistent, the concept lets algorithm implementations choose any of them as needed.
</details>
