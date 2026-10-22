---
title: Function objects
summary: "The most basic parts of <functional>: what a function object type is, the T and transparent void versions of operator function objects such as plus and less, the strict total order over pointers, compare_three_way, the concept-constrained ranges::less and friends, and identity."
updated: 2026-10-19
---

!!! tldr
    - A function object type is an object type that can appear as `x` in a function call `x(args...)`: function pointers, classes with `operator()`, and classes convertible to function pointers.
    - `std::plus<int>` converts its arguments to `int` before adding; `std::plus<>` (that is, `plus<void>`) perfectly forwards its arguments, and the result type is determined by the expression itself. The latter should generally be preferred.
    - The `void` versions carry an `is_transparent` tag; used as the comparator of a `std::set`, they allow lookup directly with other types such as `string_view`, without constructing a temporary of the key type.
    - Comparing unrelated pointers with the built-in `<` gives an unspecified result; `std::less<T*>` and friends guarantee an implementation-defined strict total order, so `std::set<T*>` is reliable.
    - `std::ranges::less` and friends require the types to model `totally_ordered_with`, so a type that only defines `<` cannot use them; `std::identity` returns its argument unchanged and is the default projection for Ranges algorithms.

[function.objects] is the entire contents of the `<functional>` header. This page covers the definition of function objects and the operator function objects; the other parts have their own pages:

| Subclause | Contents | Page |
|---|---|---|
| [func.def], [func.require], [func.invoke] | *INVOKE*, call wrappers, `std::invoke` | [[func.require]] |
| [refwrap] | `reference_wrapper`, `ref`, `cref` | [[refwrap]] |
| [func.not.fn], [func.bind.partial], [func.bind], [func.memfn] | `not_fn`, `bind_front`, `bind_back`, `bind`, `mem_fn` | [[func.bind]] etc. |
| [func.wrap] | `function`, `move_only_function`, `copyable_function`, `function_ref` | [[func.wrap]] |
| [func.search] | searchers | [[func.search]] |
| [unord.hash] | `std::hash` | [[unord.hash]] |

## Function object types [function.objects.general]

```cpp run ok
#include <algorithm>
#include <functional>
#include <vector>

bool desc(int a, int b) { return a > b; }

int main() {
  std::vector<int> v{3, 1, 2};
  std::sort(v.begin(), v.end(), desc);                   // function pointer
  std::sort(v.begin(), v.end(), std::greater<>{});       // class object
  std::sort(v.begin(), v.end(),
            [](int a, int b) { return a > b; });         // lambda
}
```

The three calls pass `sort` things of different types, and `sort` treats them all the same; it only requires that `comp(a, b)` can be written.

!!! std
    A *function object type* is an object type that can be the type of the *postfix-expression* in a function call.

¶1 An object type that can be the type of the postfix-expression in a function call is called a **function object type** ([[g:function-object-type]]), and its objects are called **function objects**. This definition looks only at syntax. A footnote lists three cases:

1. function pointers, such as `int(*)(int)`;
2. class types with a member `operator()`, including the closure types of all lambdas ([[expr.prim.lambda.closure]]);
3. class types convertible to a function pointer, where the call goes through a surrogate call function ([[over.call.object]]).

A function type itself is not a function object type, because functions are not objects. Neither is a member pointer: `pmf(obj)` is invalid. Bringing member pointers into the set of callable things is the job of the callable types and *INVOKE* in [[func.require]].

The second half of ¶1 states the design intent: wherever one would otherwise pass a function pointer to an algorithm, the interface is designed to accept a function object, so that both function pointers and arbitrary function objects can be passed.

The advantage of function objects is not only that they can carry state. A class's `operator()` is part of the type, a template is instantiated separately for each comparator type, and the call can be inlined directly. A function pointer is a run-time value, and the compiler must first determine which function it points to before it can inline. This is one of the reasons `std::sort` is usually faster than `qsort`.

## The header [functional.syn]

Some points worth noting in the synopsis:

- Almost everything is marked `// freestanding`, including `invoke`, `reference_wrapper`, all the operator function objects, `identity`, `not_fn`, `bind_front`, `bind`, `mem_fn` and `hash`. Not included are `function`, `move_only_function`, `copyable_function`, `bad_function_call`, and the two Boyer–Moore searchers.
- The operator function objects are all declared as `template<class T = void> struct plus;` with an explicit specialization for `void`. So `std::plus<>` and `std::plus<void>` are the same type.
- `ref(const T&&)` and `cref(const T&&)` are declared deleted, to reject rvalue arguments ([[refwrap]]).
- At the end, some exposition-only tools are defined, such as the concept *callable* and the alias *call-result-t*, for use by [[func.wrap.ref]] and other subclauses.

## Operator function objects: the `T` version and the `void` version

[arithmetic.operations], [comparisons], [logical.operations] and [bitwise.operations] all have exactly the same structure. Each operator corresponds to a class template:

| Category | Class templates | Operators | `T` version returns |
|---|---|---|---|
| arithmetic | `plus`, `minus`, `multiplies`, `divides`, `modulus`, `negate` | `+ - * / %`, unary `-` | `T` |
| comparison | `equal_to`, `not_equal_to`, `greater`, `less`, `greater_equal`, `less_equal` | `== != > < >= <=` | `bool` |
| logical | `logical_and`, `logical_or`, `logical_not` | `&& \|\| !` | `bool` |
| bitwise | `bit_and`, `bit_or`, `bit_xor`, `bit_not` | `& \| ^ ~` | `T` |

```cpp run ok
#include <cstdio>
#include <functional>
#include <numeric>
#include <vector>

int main() {
  std::vector<double> v{0.5, 0.5, 0.5, 0.5};
  double a = std::accumulate(v.begin(), v.end(), 0.0,
                             std::plus<int>());  // truncated to int at every step
  double b = std::accumulate(v.begin(), v.end(), 0.0,
                             std::plus<>());     // double + double
  std::printf("%g %g\n", a, b);                  // 0 2
}
```

Taking `plus` as an example, [arithmetic.operations.plus] gives two forms.

The `T` version (¶1) has two parameters of type `const T&`, returns `T`, and its effect is `x + y`. The arguments are first converted to `T`, and the result of the operation is then converted to the return type:

```cpp
template<class T = void> struct plus {
  constexpr T operator()(const T& x, const T& y) const;
};
```

The `void` version (¶2) has two independently deduced forwarding-reference parameters, and its return type is the type of the expression itself, with no extra conversion:

```cpp
template<> struct plus<void> {
  template<class T, class U> constexpr auto operator()(T&& t, U&& u) const
    -> decltype(std::forward<T>(t) + std::forward<U>(u));
  using is_transparent = unspecified;
};
```

In the example above, the parameters of `plus<int>` are `const int&`, so `0.0` and `0.5` are both first converted to the `int` 0. This conversion happens inside the standard library, and even `-Wall -Wextra` gives no warning. The `void` version has no such problem, so unless you really need the conversion first, write `std::plus<>{}`.

The trailing return type of the `void` version has another effect: when `t + u` is invalid, substitution fails and `operator()` does not participate in overload resolution, instead of producing an error inside the function body.

!!! note "These function objects are not `noexcept`"
    The wording does not mark `operator()` as `noexcept`. Implementations may add a non-throwing exception specification to non-virtual functions ([[res.on.exception.handling]]). libc++'s `void` versions carry specifications like `noexcept(noexcept(t + u))`; the `T` versions do not. Portable code should not depend on whether they are `noexcept`.

## Transparent comparators and heterogeneous lookup

<div class="compare" markdown="1">

```cpp run ok
#include <set>
#include <string>
#include <string_view>
#include <functional>
int main() {
  std::set<std::string, std::less<>>
    s{"apple"};
  std::string_view key = "apple";
  return s.contains(key);   // OK
}
```

```cpp run error
#include <set>
#include <string>
#include <string_view>
int main() {
  std::set<std::string> s{"apple"};
  std::string_view key = "apple";
  return s.contains(key);
  // error: no matching contains
}
```

</div>

Every `void` specialization has a member `using is_transparent = unspecified;`. This alias takes no part in the operation; it is just a tag saying that the comparator can compare arguments of different types directly. A comparator carrying this tag is called a **transparent comparator** ([[g:transparent-comparator]]).

The `find`, `count`, `contains`, `lower_bound`, `upper_bound` and `equal_range` of ordered associative containers ([[associative.reqmts]]) all have a set of member templates, such as `template<class K> iterator find(const K& x);`. These templates participate in overload resolution only if `Compare::is_transparent` exists and is a type.

On the left the comparator is `less<>`, and `contains` compares the `string_view` with the elements directly, without constructing a `std::string`. On the right the comparator is the default `less<std::string>`, which has only `contains(const key_type&)`, and `string_view` cannot be implicitly converted to `std::string`, so there is no usable function.

The default `less<Key>` does not automatically become transparent, because transparency changes the semantics. `less<std::string>` converts its arguments to `std::string` before comparing; a transparent version directly uses the mixed comparison of `const char*` with `std::string`. If a type's converting constructor performs normalization (for example, converting to lowercase), the two comparisons can give different results. So the standard leaves it to users to opt in to a transparent comparator explicitly.

Since C++20, unordered containers ([[unord.req]]) also support heterogeneous lookup ([[P0919R3]], [[P1690R1]]), but they require both the hash function and the equality predicate to be transparent; otherwise `string_view` and `std::string` might hash to different values. `std::hash<std::string>` itself is not transparent, so you have to write a hash with `is_transparent` yourself (see [[unord.hash]]).

!!! history
    The transparent operator function objects (the `void` specializations such as `less<>`) were added in C++14 by [[N3421]], heterogeneous lookup for ordered associative containers was added in C++14 by [[N3657]], and heterogeneous lookup for unordered containers came in C++20 with [[P0919R3]] and [[P1690R1]].

## The strict total order over pointers [comparisons.general]

```cpp run ok
#include <cstdio>
#include <functional>
int a, b;
int main() {
  int* p = &a;
  int* q = &b;
  bool x = std::less<int*>{}(p, q);
  bool y = std::less<int*>{}(q, p);
  std::printf("%d\n", x != y);                     // 1: exactly one is true
  std::printf("%d\n", std::less<>{}(p, q) == x);   // 1
}
```

When pointers are compared with the built-in `<`, only cases such as elements of the same array or members of the same object have a specified result. Comparing the addresses of two unrelated global variables gives an unspecified result ([[expr.rel#5]]). `std::set<T*>` and `std::map<T*, V>` need a comparator that is a strict weak ordering; unspecified results cannot guarantee transitivity, and the container's invariants could be broken.

¶2 adds a guarantee to the library function objects for this reason:

!!! std
    For templates `less`, `greater`, `less_equal`, and `greater_equal`, the specializations for any pointer type yield a result consistent with the implementation-defined strict total order over pointers.

The implementation-defined strict total order over pointers is in [[defns.order.ptr]]: it covers all pointer values and agrees with the results of the built-in operators where those are defined. So:

- `less<T*>`, `greater<T*>`, `less_equal<T*>` and `greater_equal<T*>` give a definite result for any two pointers. Note 1 says that when the built-in `<` is defined, the two give the same result.
- For `less<void>` and the like, if the call operator ends up using a built-in operator comparing pointers, the result is also consistent with this total order. This was added by [[LWG2450]].
- `equal_to` and `not_equal_to` are not in the list, because equality comparison of pointers is always defined.

On mainstream platforms with a flat address space, the `<` generated by the compiler already compares addresses numerically, so libc++'s `less<T>` simply writes `return __x < __y;`. But this only holds at run time:

```cpp run error
#include <functional>
int a, b;
constexpr bool r = std::less<int*>{}(&a, &b);
// error: not a constant expression
```

!!! lawyer "There is no such total order in constant evaluation"
    `less<T*>::operator()` is a `constexpr` function, but the implementation-defined total order has no known value at compile time. [[expr.const]] specifies that a relational comparison whose result is unspecified is not a constant expression. Clang's note for the example above is `comparison between pointers to unrelated objects '&a' and '&b' has unspecified value`. Comparing pointers into the same array is fine.

## `compare_three_way` [comparisons.three.way]

`compare_three_way` is the function object corresponding to `<=>`. It is not a template, has no `T` version, and is transparent in itself.

- ¶1 *Constraints*: `T` and `U` model `three_way_comparable_with` ([[cmp.concept]]); otherwise `operator()` does not participate in overload resolution.
- ¶2 *Preconditions* (violating them is UB): if the expression calls a built-in `<=>` comparing pointers, the conversions from `T` and `U` to the pointer type must be equality-preserving ([[concepts.equality]]), that is, equal inputs always convert to equal pointers; otherwise `T` and `U` must model the semantic requirements of `three_way_comparable_with`.
- ¶3 When comparing pointers it returns `strong_ordering::less`, `greater` or `equal` according to the strict total order; in other cases it is just `t <=> u`.

The requirement on conversions in ¶2 is necessary: if some class type could be converted to a pointer with a different result each time, comparing according to the total order would be meaningless.

## Concept-constrained comparators [range.cmp]

```cpp run ok
#include <cstdio>
#include <functional>
#include <type_traits>

struct V {
  int x;
  friend bool operator<(V a, V b) { return a.x < b.x; }   // only <
};
static_assert(!std::totally_ordered<V>);
static_assert(!std::is_invocable_v<std::ranges::less, V, V>);

int main() {
  V a{1}, b{2};
  std::printf("%d\n", std::less<>{}(a, b));   // OK: only requires a < b to be valid
}
```

C++20's Ranges ([[P0896R4]]) provides six non-template comparators in `std::ranges`: `equal_to`, `not_equal_to`, `greater`, `less`, `greater_equal` and `less_equal`. They differ from `std::less<>` in their requirements on the types:

| | `std::less<>` | `std::ranges::less` |
|---|---|---|
| Callable when | `t < u` is valid | ¶8 *Constraints*: `totally_ordered_with<T, U>` |
| Semantic requirements | none | ¶9 *Preconditions*: models the semantic requirements of `totally_ordered_with`, and exactly one of three holds |
| Return type | `decltype(t < u)` | `bool` |
| Pointers | total order when the built-in comparison is used | also the total order (¶10.1) |

`totally_ordered_with` requires all six comparison operators to exist with results usable as `bool`, and across types it also requires a common reference type ([[concepts.compare]]). So `V`, which only defines `operator<`, can use `std::less<>` but not `ranges::less`.

Although all six operators are required to exist, only `<` is actually called: ¶7 `ranges::greater` is `less` with the arguments swapped, ¶12 `greater_equal` is `!less(t, u)`, and ¶14 `less_equal` is `!less(u, t)`. Algorithms such as `ranges::sort` assume that `<` describes the same order as `==`, `>` and the rest, and the concept constraint keeps out types that only provide `<`.

The last sentence of ¶9 requires that for any two values, exactly one of `less(a, b)`, `less(b, a)` and `equal_to(a, b)` is true. This is a semantic requirement on values that the compiler cannot check. `double` meets the syntactic requirements of `totally_ordered`, but NaN fails this condition when compared with any value, so sorting a `vector<double>` containing NaN with `ranges::sort` violates the precondition.

¶1–¶3 `ranges::equal_to` requires `equality_comparable_with`; when comparing pointers it also uses the total order, and two pointers are equal if neither is ordered before the other. ¶4–¶5 `ranges::not_equal_to` is its negation.

## `identity` [func.identity]

```cpp
struct identity {
  template<class T> constexpr T&& operator()(T&& t) const noexcept;
  using is_transparent = unspecified;
};
```

¶1 `std::identity` returns `std::forward<T>(t)`, forwarding the argument unchanged and preserving its value category. It is the default value of the projection parameter of every Ranges algorithm: the `proj` in `ranges::sort(r, comp, proj)` defaults to `identity{}`.

```cpp run ok
#include <algorithm>
#include <cstdio>
#include <functional>
#include <vector>

struct Emp { int id; double salary; };

int main() {
  std::vector<Emp> v{{3, 10}, {1, 30}, {2, 20}};
  // projection: the member pointer is called via std::invoke
  std::ranges::sort(v, std::ranges::less{}, &Emp::salary);
  std::vector<int> w{3, 1, 2};
  std::ranges::sort(w, {}, std::identity{});   // same as no projection
  std::printf("%d %d\n", v[0].id, w[0]);       // 3 1
}
```

!!! pitfall "`identity` returns a reference"
    In `auto&& r = std::identity{}(make_string());`, `identity` returns a `std::string&&` to the temporary object. The temporary is destroyed at the end of the full-expression, and `r` dangles. Like `std::move` and `std::forward`, `identity` only passes a reference along and does not extend lifetimes.

## Old facilities that have been removed

C++98's `<functional>` also had the base classes `unary_function` and `binary_function`, and `bind1st`, `bind2nd`, `ptr_fun`, `mem_fun`, `mem_fun_ref`, `not1`, `not2` and so on. Except for `not1` and `not2`, they were deprecated in C++11 and removed in C++17 ([[N4190]]); `not1` and `not2` were deprecated in C++17 and removed in C++20. They have been replaced by lambdas, `bind`, `bind_front`, `mem_fn` and `not_fn` respectively ([[func.bind]]).

## Questions

!!! question "Question 1"
    A `std::set<int*>` holds pointers to different heap objects. If the default `std::less<int*>` is replaced by `[](int* a, int* b) { return a < b; }`, what is the difference in terms of the standard?

<details markdown="1">
<summary>Answer</summary>

The default `std::less<int*>` gives an implementation-defined strict total order per [comparisons.general] ¶2, which meets the container's requirement of a strict weak ordering.

The hand-written lambda uses the built-in `<` directly. For pointers to different objects the result is unspecified ([[expr.rel#5]]), with no guarantee of transitivity or consistency, so the requirements on `Compare` in [[associative.reqmts]] are not guaranteed to hold, and the program's behavior is not guaranteed. On mainstream platforms the two generate the same code; the difference is that the former has the standard's guarantee while the latter only happens to work.
</details>

!!! question "Question 2"
    Why is `ranges::less` designed as an ordinary class, rather than with a template parameter defaulting to `void` like `std::less`?

<details markdown="1">
<summary>Answer</summary>

The `T` version of `std::less<T>` merely converts the arguments to `T` before comparing. Since C++14 introduced the transparent `less<>`, it has been kept mainly for compatibility with old code. Ranges was designed from scratch and needs only one form, transparent and concept-constrained. As an ordinary class, `ranges::less{}` is shorter to write, and no template argument needs to be written when it is used as an algorithm's default argument (`Comp comp = {}`).
</details>
