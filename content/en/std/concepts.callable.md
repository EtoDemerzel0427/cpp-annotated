---
title: Callable concepts
summary: "What invocable, regular_invocable, predicate, relation, equivalence_relation and strict_weak_order require; three of them strengthen only semantically and the compiler can't tell them apart; the precise definition of strict weak ordering, and why using <= as a comparator goes wrong."
updated: 2026-10-19
---

!!! tldr
    - `invocable<F, Args...>` only requires that the call can be made with `std::invoke`, pointers to members included; the call may have state and side effects.
    - `regular_invocable` requires the call to be pure (equal inputs give equal results, and nothing is modified), but syntactically it is word for word the same as `invocable`, so the compiler can't tell them apart, and it can't be used to select overloads.
    - `predicate` is a `regular_invocable` whose result is *boolean-testable*; `relation<R, T, U>` requires all four directions to be predicates.
    - `strict_weak_order` requires irreflexivity, and transitivity of both `comp` and "neither is less than the other". Using `<=` as a sort comparator violates it, and on libc++ reads and writes out of bounds.

[concepts.callable] describes requirements on [[func.def|callable types]] and their arguments ([concepts.callable.general] ¶1). Of the six concepts, only `invocable`, `predicate` and `relation` have their own syntactic definitions. The definitions of `regular_invocable`, `equivalence_relation` and `strict_weak_order` are word for word those of the concepts they refine; the difference lies entirely in the semantic requirements, which is called purely semantic refinement. For terms such as satisfying, modeling and equality preservation below, see [[concepts]].

## `invocable` ([concept.invocable])

```cpp run title="invocable.cpp" ok
#include <concepts>
#include <random>
#include <string>

struct S { int m; int f(int) const { return m; } };
using PMF = int (S::*)(int) const;

static_assert(std::invocable<int S::*, S&>);         // pointer to data member
static_assert(std::invocable<PMF, const S*, int>);   // pointer to member function
static_assert(!std::invocable<PMF, S, std::string>);
static_assert(std::invocable<std::mt19937&>);        // stateful is fine too

struct RV { int operator()() && { return 1; } };
static_assert(std::invocable<RV> && !std::invocable<RV&>);

int main() {}
```

```cpp
template<class F, class... Args>
  concept invocable = requires(F&& f, Args&&... args) {
    invoke(std::forward<F>(f), std::forward<Args>(args)...); // not required to be equality-preserving
  };
```

¶1 `invocable` specifies a relationship between a callable type `F` and a set of argument types `Args...`: they can be evaluated by the library function `std::invoke` ([[func.invoke]]). Using `invoke` rather than `f(args...)` means it covers every form of *INVOKE*: ordinary functions, function objects, pointers to member functions (with the first argument an object, reference, pointer or `reference_wrapper`), and pointers to data members.

Value categories are passed through unchanged via `F&&`, `Args&&...` and `std::forward`. `invocable<F&, int>` checks a call on an lvalue `F`, and `invocable<F, int>` a call on an rvalue `F`. `RV` above has only a `&&`-qualified `operator()`, so the two give different results.

The comment in the definition says this call expression isn't required to be equality-preserving, an exception to the default rule of [[concepts.equality]]. ¶2 Example 1 says a function that generates random numbers can model `invocable`. `invocable` says only that the call can be made; it places no requirements on the result.

## `regular_invocable`: pure functions

```cpp
template<class F, class... Args>
  concept regular_invocable = invocable<F, Args...>;
```

¶1 requires the `invoke` call expression to be equality-preserving and not to modify the function object or the arguments. Note 1 says this requirement supersedes the "not required to be equality-preserving" annotation in the definition of `invocable`. ¶2 Example 1: a random number generator doesn't model `regular_invocable`. ¶3 Note 2: the distinction between the two is purely semantic.

Equality preservation plus no modification is a pure function in the mathematical sense: equal inputs (including the state of the function object itself) always give equal outputs, with no observable side effects. Algorithms rely on this to call the same function several times, cache results, and reorder calls.

### Purely semantic refinement doesn't take part in subsumption

```cpp run title="semantic-refinement.cpp" error
#include <concepts>

template<class F> requires std::invocable<F>
int pick(F) { return 1; }

template<class F> requires std::regular_invocable<F>
int pick(F) { return 2; }

int main() {
  return pick([] {});   // error: the call is ambiguous
}
```

During constraint normalization ([[temp.constr.normal]]), a concept-id is replaced by the normal form of its definition, so `regular_invocable<F>` and `invocable<F>` yield exactly the same atomic constraints. By [[temp.constr.order]], they subsume each other and neither is more constrained, so the call is ambiguous.

So you can't overload a faster version for pure functions. A semantic refinement is only a contract written for people: it tells callers that the function is assumed to be pure here, and a program that violates it is {{ifndr}} ([[res.on.requirements]]). `std::regular_invocable<std::mt19937&>` is true all the same.

## `predicate` and `relation`

```cpp
template<class F, class... Args>
  concept predicate =
    regular_invocable<F, Args...> && boolean-testable<invoke_result_t<F, Args...>>;

template<class R, class T, class U>
  concept relation =
    predicate<R, T, T> && predicate<R, U, U> &&
    predicate<R, T, U> && predicate<R, U, T>;
```

A predicate is a pure function whose result is *boolean-testable* ([[concept.booleantestable]]). There is a new syntactic requirement here, so `predicate` genuinely subsumes `regular_invocable`. Functions returning `int`, a pointer or `bitset::reference` can all be predicates; one returning `void` can't, and one returning a type that overloads `&&` satisfies without modeling.

A binary relation `relation<R, T, U>` requires predicates in all four directions: `T×T`, `U×U`, `T×U` and `U×T`. A comparator providing only the cross-type directions doesn't satisfy it. The same-type directions are needed because algorithms compare elements with keys and also elements with elements; the properties of equivalence relations and strict weak orders below (reflexivity, transitivity) also have to be stated on a single type.

```cpp run title="relation.cpp" ok
#include <concepts>
#include <functional>
#include <string>

struct LessIntStr {   // only the two cross-type directions
  bool operator()(int, const std::string&) const;
  bool operator()(const std::string&, int) const;
};
static_assert(!std::relation<LessIntStr, int, std::string>);

static_assert(std::equivalence_relation<
  std::equal_to<>, int, long>);
static_assert(std::strict_weak_order<
  std::less<>, int, long>);

int main() {}
```

## `equivalence_relation` ([concept.equiv])

```cpp
template<class R, class T, class U>
  concept equivalence_relation = relation<R, T, U>;
```

¶1 A relation models `equivalence_relation` only if it imposes an equivalence relation on its arguments: reflexive, symmetric and transitive. The comparators of `ranges::unique` and `ranges::adjacent_find` are such relations.

Unlike `equality_comparable`, it doesn't require equivalence to be equality. Comparing strings case-insensitively is a valid equivalence relation, even though `"A"` and `"a"` aren't equal.

## `strict_weak_order` ([concept.strictweakorder])

```cpp
template<class R, class T, class U>
  concept strict_weak_order = relation<R, T, U>;
```

¶1 A relation models `strict_weak_order` only if it imposes a **strict weak ordering** ([[g:strict-weak-ordering|strict weak ordering]]) on its arguments.

Intuitively, a strict weak ordering divides all elements into groups, with the groups arranged in a line and the elements within a group indistinguishable from each other. An address book sorted by surname is like this: people with the same surname are in the same group.

¶2 gives the precise definition. Strict means irreflexive: `!comp(x, x)` for all `x`. Weak means the requirement is weaker than a total order and stronger than a partial order. Let `equiv(a, b)` be `!comp(a, b) && !comp(b, a)`, i.e. neither is less than the other; then both `comp` and `equiv` are required to be transitive:

- ¶2.1 `comp(a, b) && comp(b, c)` implies `comp(a, c)`;
- ¶2.2 `equiv(a, b) && equiv(b, c)` implies `equiv(a, c)`.

¶3 Note 1 lists what follows from this: `equiv` is an equivalence relation (¶3.1); `comp` induces a well-defined relation on the equivalence classes determined by `equiv` (¶3.2); and that relation is a strict total ordering (¶3.3). The equivalence classes are the groups mentioned above.

It constrains something different from [[concept.totallyordered|totally_ordered]]:

| | `strict_weak_order` | `totally_ordered` |
|---|---|---|
| What it constrains | A comparator `R` | The `<` and other operators of a type `T` |
| Indistinguishable elements | Equivalent, not necessarily equal | Necessarily equal |
| Typical use | Comparators of `sort`, `lower_bound`, `set` | What the default comparator `ranges::less` requires of a type |

`ranges::less` requires `totally_ordered_with`, while `ranges::sort` requires only a strict weak order of its comparator (via `sortable` and `indirect_strict_weak_order`). So a custom comparator only needs to be a strict weak order, but with the default comparator the element type must be totally ordered.

### Using `<=` as a comparator

```cpp run title="le-comparator.cpp" ifndr
#include <algorithm>
#include <concepts>
#include <vector>

int main() {
  auto le = [](int a, int b) { return a <= b; };
  // satisfied: syntactically it is just a relation
  static_assert(std::strict_weak_order<decltype(le), int, int>);
  std::vector<int> v(100, 42);
  std::ranges::sort(v, le);   // not modeled: le(x, x) is true
}
```

`<=` violates irreflexivity. The consequence isn't just a possibly wrong sort result: the inner loops of many `sort` implementations rely on the comparator returning `false` for elements equal to the pivot in order to stop, and with `<=` they can read and write past the end of the array.

!!! impl "Behavior on libc++"
    With Clang 23 + libc++ in the default configuration, the program above accesses out of bounds inside `sort` and crashes with a bus error (exit code 138). With `-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_FAST`, the bounds check terminates the program with a trap instruction; with `_LIBCPP_HARDENING_MODE_DEBUG`, it first prints "Would read out of bounds, does your comparator satisfy the strict-weak ordering requirement?" and then terminates.

## Common misconceptions

!!! pitfall "Thinking `regular_invocable` can block stateful function objects at compile time"
    It can't: `std::regular_invocable<std::mt19937&>` is true. The compiler can't tell whether a function is pure.

!!! pitfall "Floating-point comparators and NaN"
    `std::less<double>` is a strict weak order on data without NaN. When the data contains NaN, NaN is equivalent to every number, `equiv` is no longer transitive, and the premise of `sort` is broken. When needed, use `std::strong_order` ([[cmp.alg]]) as the comparator, which gives a total order including NaN.

## Questions

!!! question "Questions"
    1. A function object's `operator()` modifies a `mutable` call counter, but its return value depends only on its arguments. Does it model `regular_invocable`?
    2. If `comp` is a strict weak order, does `[](auto a, auto b) { return !comp(b, a); }` satisfy `strict_weak_order`? Does it model it?
    3. Why doesn't ¶2 require asymmetry (`comp(a, b)` implies `!comp(b, a)`)?

<details markdown="1">
<summary>Answer</summary>

1. It depends on whether the counter can be observed. Modification in the sense of [[concepts.equality]] means changing a value in a way observable through equality-preserving expressions. If the counter can be read through some public equality-preserving interface, ¶1 is violated; if it is completely invisible from outside (purely debugging statistics), it generally doesn't count as a modification. A non-atomic counter in a multithreaded setting also brings data races, but that is a separate problem.
2. It satisfies it, since syntactically it only needs to be a `relation`. It doesn't model it: for any `x`, `!comp(x, x)` is true, so it returns `true` for `(x, x)`, violating irreflexivity.
3. Asymmetry can be derived: if `comp(a, b)` and `comp(b, a)` were both true, transitivity would give `comp(a, a)`, contradicting irreflexivity.
</details>
