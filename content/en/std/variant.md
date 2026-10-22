---
title: Variants
summary: "The parts of <variant> outside the class template: the contracts of the accessors get, get_if and holds_alternative, how the relational operators compare different alternatives and the valueless state, and monostate, bad_variant_access and hash."
updated: 2026-10-19
---

!!! tldr
    - At any moment a `variant<Ts...>` holds a value of one of `Ts...` and remembers which one; the value is stored inside the variant object, with no heap allocation.
    - `get<T>`, `get_if<T>` and `holds_alternative<T>` require `T` to occur exactly once in the type list, otherwise compilation fails; if at run time it is not holding a `T`, `get` throws `bad_variant_access` and `get_if` returns a null pointer.
    - Comparison compares the index first and only compares values when the indices are equal: in a `variant<int, double>`, every `int` is less than every `double`.
    - The valueless state is the smallest in comparisons, and two valueless variants are equal.
    - When the first alternative cannot be default-constructed, put a `monostate` at the front and the variant becomes default-constructible.

```cpp run ok
#include <cassert>
#include <string>
#include <variant>

int main() {
  std::variant<int, std::string> v = 42;   // holds an int
  assert(v.index() == 0);
  v = "hello";                             // now holds a string
  assert(v.index() == 1);
  assert(std::get<std::string>(v) == "hello");
}
```

`std::variant`, introduced in C++17, is a type-safe union: an object holds a value of exactly one of the types in `Ts...` at any moment and remembers which one it is. In type-theory terms it is a **sum type** ([[g:sum-type]]); in terms of implementation it is just a [[class.union|union]] plus an index, with lifetime management, copying, comparison and hashing all handled by the library.

For the class template itself (construction, assignment, `emplace`, the valueless state, `swap`), see [[variant.variant]]; for `std::visit`, see [[variant.visit]].

## Alternatives [variant.general]

¶1 A variant object holds and manages the lifetime of a value; if it holds a value, the value's type has to be one of the variant's template arguments. These template arguments are called **alternatives** ([[g:variant-alternative]]).

Several facts follow from this paragraph and from [[variant.variant]]:

- The held value is nested within ([[intro.object]]) the variant object, and heap allocation is not allowed. `sizeof(variant)` is roughly the size of the largest alternative plus the index, rounded up for alignment.
- A variant may also hold no value. This **valueless state** ([[g:valueless-by-exception]]) arises only when an exception interrupts a change of type; `index()` then returns `variant_npos`, i.e. `size_t(-1)`. See [[variant.variant]] for details.
- The same type may appear more than once; `variant<int, int>` is valid. In that case the alternatives can only be distinguished by index, not by type, which is why many of the functions below require `T` to occur exactly once.

¶2 The standard also defines a set of exposition-only function templates *GET*. They have the same form as `get<I>`; the difference is that their precondition requires `v.index()` to be `I`, and violating it is undefined behavior, whereas the public `get` throws when the index is wrong. The standard uses *GET* when describing copying, comparison and `visit`, meaning that the implementation already knows the index is correct at that point and needs no check.

## Accessing the value [variant.get]

```cpp run ok
#include <cassert>
#include <string>
#include <variant>

int main() {
  std::variant<int, std::string> v = "hello";

  assert(std::holds_alternative<std::string>(v));
  assert(std::get<1>(v).size() == 5);

  try {
    (void)std::get<int>(v);        // holds a string: throws
    assert(false);
  } catch (const std::bad_variant_access&) {}

  assert(std::get_if<int>(&v) == nullptr);   // does not throw, returns a null pointer
  if (auto* p = std::get_if<std::string>(&v)) *p += '!';
  assert(std::get<std::string>(v) == "hello!");

  std::variant<int, std::string>* none = nullptr;
  assert(std::get_if<0>(none) == nullptr);   // a null pointer argument is also valid

  std::string s = std::get<1>(std::move(v)); // returns string&&
  assert(s == "hello!");
}
```

The functions in this section check at two levels: getting the index or type wrong is a compile-time error; holding something other than what you asked for at run time is a run-time error.

### `holds_alternative<T>` (¶1–2)

¶1 `T` must occur exactly once in `Types`. ¶2 It returns whether `index()` equals the index of `T` in `Types`. The function is `noexcept`; when valueless, `index()` is `variant_npos` and the result is `false`.

"Exactly once" is *Mandates*, not *Constraints* ([[structure.specifications]]). So `holds_alternative<double>(variant<int, long>{})` (zero occurrences) and `holds_alternative<int>(variant<int, int>{})` (two occurrences) are both ill-formed, and the compiler must report an error. It does not quietly return `false`, nor does it cause a substitution failure in an enclosing template.

### `get<I>` and `get<T>` (¶6–9)

¶6–7 `get<I>(v)` requires `I < sizeof...(Types)`; if `v.index() == I` it returns a reference to the stored object, otherwise it throws `bad_variant_access`. ¶8–9 `get<T>(v)` requires `T` to occur exactly once; if `v` holds a value of type `T` it returns a reference to it, otherwise it throws `bad_variant_access`.

Each has four overloads, `&`, `&&`, `const&` and `const&&`, carrying `v`'s value category and constness over to the result: `get<1>(std::move(v))` returns `T1&&`, so the value can be moved out directly.

`optional`'s `operator*` has a hardened precondition when empty ([[optional.optional]]), whereas `variant`'s `get` has been specified since C++17 as a defined failure, namely throwing an exception. The standard provides no public accessor that skips the index check (*GET* is only for exposition); when you need one, you can only use `visit` or `get_if`.

The synopsis of `<variant>` is marked mostly freestanding: a freestanding implementation (one without operating system support) provides `<variant>`, but the `get`s that throw `bad_variant_access` are marked *freestanding-deleted* and may be defined as deleted; `get_if` and `holds_alternative` do not throw and are provided as usual.

### `get_if` (¶10–13)

¶10–11 `get_if<I>(p)` requires `I < sizeof...(Types)`; if `p != nullptr` and `p->index() == I`, it returns a pointer to the stored value, otherwise `nullptr`. ¶12–13 `get_if<T>(p)` requires `T` to occur exactly once and is equivalent to calling `get_if` with the index of `T`.

The parameter is a pointer, and passing a null pointer is explicitly allowed. This shape is borrowed from the pointer overload of `any_cast` ([[any]]): the pointer version returns null on failure, the reference version throws.

### A type that occurs twice or not at all

<div class="compare" markdown="1">

```cpp run error
#include <variant>

int main() {
  std::variant<int, int> v;
  // error: int occurs twice
  return std::get<int>(v);
}
```

```cpp run ok
#include <variant>

int main() {
  std::variant<int, int> v;
  // OK: by index
  return std::get<0>(v);
}
```

</div>

libc++ implements these *Mandates* as `static_assert`s; the diagnostic on the left is "type occurs more than once in type list".

!!! pitfall "`get<T>` performs type conversions"
    `get<long>(std::variant<int, std::string>{1})` does not convert the `int` to `long`: `long` occurs zero times in the type list, so compilation simply fails. Access matches on the type itself; conversions happen only in construction and assignment (see the *FUN* rule in [[variant.variant]]).

## Relational operators [variant.relops]

```cpp run ok
#include <cassert>
#include <compare>
#include <variant>

struct S { operator int() { throw 42; } };

std::variant<float, int> make_valueless() {
  std::variant<float, int> v{12.f};
  try { v.emplace<1>(S()); } catch (int) {}
  return v;                // still valueless after copying
}

int main() {
  auto e1 = make_valueless(), e2 = make_valueless();
  std::variant<float, int> a = 1.0f, b = 0;  // indices 0 and 1

  assert(e1.valueless_by_exception());
  assert(e1 == e2 && !(e1 < e2));  // two valueless: equal
  assert(e1 < a && e1 < b);        // valueless is less than anything with a value
  assert(a < b);                   // index first: 0 < 1
  assert((e1 <=> a) == std::strong_ordering::less);
  assert((a <=> b) < 0);
}
```

The relational operators are all non-member functions and only compare two objects of the same `variant` type; `variant<int, long>` and `variant<long, int>` cannot be compared. The general rule is to compare the index first and the value only when the indices are equal, with a special convention for the valueless state:

| Operation | Rule |
|---|---|
| `v == w` | ¶2 `false` if the indices differ; otherwise `true` if `v` is valueless; otherwise `GET<i>(v) == GET<i>(w)` |
| `v != w` | ¶4 `true` if the indices differ; otherwise `false` if `v` is valueless; otherwise `GET<i>(v) != GET<i>(w)` |
| `v < w` | ¶6 `false` if `w` is valueless; otherwise `true` if `v` is valueless; otherwise compare indices; compare values only if the indices are equal |
| `v > w` | ¶8 `false` if `v` is valueless; otherwise `true` if `w` is valueless; otherwise compare indices, then values |
| `v <= w` | ¶10 `true` if `v` is valueless; otherwise `false` if `w` is valueless; otherwise compare indices, then values |
| `v >= w` | ¶12 `true` if `w` is valueless; otherwise `false` if `v` is valueless; otherwise compare indices, then values |
| `v <=> w` | ¶13 `equal` if both are valueless; `less` if only `v` is; `greater` if only `w` is; if the `<=>` of the indices is nonzero, return it; otherwise return `GET<i>(v) <=> GET<i>(w)` |

Three points can be drawn from the table:

1. The valueless state is the smallest element, and two valueless variants are equal. In `==` both indices are `variant_npos`, so evaluation reaches the "`true` if `v` is valueless" step.
2. The index decides the broad category. `variant<int, double>(100) < variant<int, double>(0.5)` is `true`: what is compared is which alternative, not the numeric value. So the declaration order of the alternatives is part of the comparison semantics, and reordering the type list is a breaking change.
3. Each operator only calls the same operator on the alternatives: `v >= w` uses `Ti`'s `>=` and is not rewritten as `!(v < w)`. For values that do not form a total order, such as NaN, the variant behaves consistently with the underlying type.

### Constraints {{c++26}}

¶1, ¶3, ¶5, ¶7, ¶9 and ¶11 require that for every `i`, the corresponding expression such as `GET<i>(v) == GET<i>(w)` be valid and convertible to `bool`; these are *Constraints*. In C++23 and earlier they were *Mandates*: the declaration of `==` for `variant<int, NoEq>` existed and using it was a hard error, but concepts only check declarations, so `std::equality_comparable<variant<int, NoEq>>` was wrongly `true`. With *Constraints*, the operator simply does not participate in overload resolution, and the concept's verdict becomes accurate:

```cpp run ok
#include <concepts>
#include <variant>

struct NoEq {};
static_assert(std::equality_comparable<std::variant<int, double>>);
static_assert(!std::equality_comparable<std::variant<int, NoEq>>);
int main() {}
```

In our tests libc++ 23 only constrains these operators under `-std=c++2c`; compiling the example above with `-std=c++23`, the second `static_assert` fails.

`operator<=>` has carried the constraint `requires (three_way_comparable<Types> && ...)` since it was introduced in C++20, and its return type is the `common_comparison_category_t` of the `compare_three_way_result_t<Types>`s ([[cmp.common]]).

## monostate [variant.monostate]

```cpp run ok
#include <cassert>
#include <type_traits>
#include <variant>

struct NoDefault { NoDefault(int) {} };

static_assert(!std::is_default_constructible_v<
              std::variant<NoDefault, int>>);
std::variant<std::monostate, NoDefault, int> v;  // OK

int main() {
  assert(std::holds_alternative<std::monostate>(v));
  v = 42;                     // index() == 2
  v = std::monostate{};       // back to the empty state
  assert(v.index() == 0);
}
```

`struct monostate{};` is an empty type with only one state. ¶1 explains its purpose: placed in the first alternative position, it makes the variant default-constructible. The variant's default constructor requires the first alternative `T0` to be default-constructible ([[variant.ctor#2]]); if it is not, pad the front with a `monostate`.

It is also often used as an empty state, which is more controllable than the valueless state: the valueless state can only be produced by an exception, while a `monostate` can be assigned at any time.

[variant.monostate.relops] specifies that `==` on two `monostate`s is always `true` and `<=>` is always `strong_ordering::equal`, since it has only one state. Since C++26, `<utility>` also declares `monostate` ([[P0472R3]]), so there is no need to include `<variant>` just for it.

## Helper classes [variant.helper]

`variant_size<V>` and `variant_alternative<I, V>` are the variant counterparts of `tuple_size` and `tuple_element`: `variant_size_v<variant<int, char>>` is 2, and `variant_alternative_t<1, variant<int, char>>` is `char`.

- ¶1 Specializations of `variant_size` have `integral_constant<size_t, N>` as their base class. The primary template is not defined, so using it on a non-variant type is a compile error rather than giving 0.
- ¶2–3 `variant_size<const T>` is the same as `variant_size<T>`; `variant_alternative<I, const T>::type` is `const` added to `variant_alternative<I, T>::type`.
- ¶4–5 `variant_alternative<I, variant<Types...>>::type` is the `I`th type in `Types`; an out-of-range `I` violates *Mandates* and is a compile error, not a substitution failure.

The current draft has only the `const` specializations. The `volatile` versions were deprecated in C++20 and are no longer in the draft; libc++ 23 (in our tests) still provides them.

## swap, bad_variant_access and hash

### Non-member `swap` [variant.specalg]

¶1 The non-member `swap` requires every `Ti` to be move-constructible and swappable; these are *Constraints*. ¶2 The effect is equivalent to `v.swap(w)`, and ¶3 the exception specification is equivalent to `noexcept(v.swap(w))`. The member `swap`'s requirement of move-constructibility, by contrast, is *Mandates* ([[variant.swap#1]]). Only because the non-member version uses *Constraints* can `std::is_swappable_v<variant<...>>` honestly report `false`, instead of an error appearing only at the call.

### `bad_variant_access` [variant.bad.access]

`bad_variant_access` publicly inherits from `std::exception`. ¶1 It is used to report invalid access to a variant's value: the index or type passed to `get` does not match the current value, or `visit` encounters a valueless variant ([[variant.visit#7]]). ¶2 `what()` returns an implementation-defined string. In the current draft `what()` is `constexpr`, and during constant evaluation the string is encoded as an ordinary literal; in our tests libc++ 23's `what()` is not yet `constexpr`.

What libc++ actually throws is an internal subclass, and `what()` distinguishes `std::get: variant is valueless`, `std::get: wrong alternative for variant` and `std::visit: variant is valueless`. Catching with `catch (const std::bad_variant_access&)` is unaffected.

### Hashing [variant.hash]

¶1 `hash<variant<Types...>>` is enabled if and only if every `hash<remove_const_t<Types>>` is enabled ([[unord.hash]]). A disabled specialization cannot be default-constructed or called, so `unordered_set<variant<int, NoHash>>` fails at compile time. Its member functions are not guaranteed to be `noexcept`, because the underlying types' hashes may throw. ¶2 `hash<monostate>` is always enabled.

```cpp run ok
#include <functional>
#include <string>
#include <type_traits>
#include <unordered_set>
#include <variant>

struct NoHash {};
using H1 = std::hash<std::variant<int, std::string>>;
using H2 = std::hash<std::variant<int, NoHash>>;
static_assert(std::is_default_constructible_v<H1>);   // enabled
static_assert(!std::is_default_constructible_v<H2>);  // disabled

int main() {
  std::unordered_set<std::variant<int, std::string>> s{1, "one"};
  return s.size() == 2 ? 0 : 1;
}
```

The standard does not specify how the hash value is computed. In practice the index takes part in the hash; otherwise `7` and `7L` in a `variant<int, long>` would always collide. libc++ hashes the current value first and then combines it with `hash<size_t>{}(index())`; when valueless, a fixed constant replaces the value's hash.

## History and evolution

!!! history
    - C++17: [[P0088R3]] introduced `variant`. The most debated design question was what to do when an exception interrupts assignment. Boost.Variant guarantees a value is always present by using a backup on the heap; the standard chose the zero-overhead valueless state ([[g:never-quite-empty]]).
    - C++20: [[P0608R3]] fixed the *FUN* rule for converting construction, so `variant<string, bool> v = "abc"` no longer chooses `bool`; propagation of the triviality of special member functions was also added in this period. See [[variant.variant]] for details.
    - C++23: [[P2162R2]] made `std::visit` accept classes derived from `variant`; see [[variant.visit]].
    - C++26: [[P2637R3]] added the member function `visit`; the relational operators changed from *Mandates* to *Constraints*; `bad_variant_access::what()` became `constexpr`; `monostate` is also available from `<utility>`.

## Questions

!!! question "Question 1"
    Given `std::variant<int, double> a = 100, b = 0.5;`, what are `a < b`, `a == b` and `a <=> b`? What if the type order is changed to `variant<double, int>`?

<details markdown="1">
<summary>Answer</summary>

By [[variant.relops#6]] and ¶13, the indices are compared first: `a.index()` is 0 and `b.index()` is 1, so `a < b` is `true`, `a == b` is `false`, and `a <=> b` is `strong_ordering::less`, given by `<=>` on `size_t`. The magnitudes of 100 and 0.5 play no part at all. With `variant<double, int>`, `a` holds an `int` (index 1) and `b` holds a `double` (index 0), and the conclusions are reversed.
</details>

!!! question "Question 2"
    Write a generic function `template<class V> bool is_int(const V& v) { return std::holds_alternative<int>(v); }`. What happens when it is called with a `variant<long>`? Why does the standard work this way?

<details markdown="1">
<summary>Answer</summary>

Compilation fails; it does not return `false`. The condition of `holds_alternative` is *Mandates*, and violating it makes the program ill-formed with a required diagnostic ([[structure.specifications]]). It is triggered only when the function template is instantiated, not in the immediate context of substitution ([[g:immediate-context]]), so it is not a substitution failure either.

Asking whether a variant holds a type it could never hold is almost always a typo, and silently returning `false` would hide the error. If generic code needs a type that is not in the list to count as `false`, it should first check for itself whether the type occurs exactly once (for example by counting `is_same_v` with a fold expression) and then decide whether to make the call.
</details>
