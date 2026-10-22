---
title: "Deprecated library features, part 1: numerics, C compatibility, type traits and utilities (D.10–D.19)"
summary: "Ten library deprecations in Annex D, from numeric_limits::has_denorm, is_pod and aligned_storage to std::rel_ops and std::iterator: why each was deprecated, what to use instead, and whether libc++ warns."
updated: 2026-10-19
---

!!! tldr
    - These ten facilities are still part of the standard, but the main text no longer mentions them; their full definitions remain only in Annex D, and they may be removed in the future.
    - The concepts behind `is_pod` and `is_trivial` are too coarse, and `aligned_storage` and `aligned_union` are easy to misuse. Use more precise traits such as `is_trivially_copyable` instead, and `alignas(T) std::byte buf[sizeof(T)]`.
    - `std::rel_ops` has been superseded by C++20's `operator<=>` and rewritten candidates; rather than the `std::iterator` base class, write out the five type aliases directly.
    - `numeric_limits::has_denorm` and the `*_HAS_SUBNORM` macros can't answer at compile time a question that is only settled at run time, so their values were made unspecified.
    - libc++ adds `[[deprecated]]` to most of the deprecated names, but the macros, the `volatile` specializations and the static `swap` of `vector<bool>` produce no warning.

**Deprecated** features are still normative and implementations must provide them; they have just been identified as candidates for possible future removal ([[depr.general#2]]). Implementations can add the `[[deprecated]]` attribute to these library names, so that using them produces a `-Wdeprecated-declarations` warning (on by default).

The test environment for this page is Clang 23.1.3 with libc++. libc++ usually adds the attribute only from the language version in which the deprecation happened, so the same code may produce no warning under `-std=c++17`.

## D.10 The `has_denorm` members of `numeric_limits` {#depr.numeric.limits.has.denorm}

```cpp
#include <limits>
auto hd  = std::numeric_limits<double>::has_denorm;       // deprecated
auto hdl = std::numeric_limits<double>::has_denorm_loss;  // deprecated
std::float_denorm_style st = std::denorm_present;         // deprecated
```

¶1 `<limits>` additionally defines the enumeration `float_denorm_style`, with enumerators `denorm_indeterminate = -1`, `denorm_absent = 0` and `denorm_present = 1`. ¶2 and ¶4 add two static members to the primary template of `numeric_limits` and to `numeric_limits<bool>`: `has_denorm` is `denorm_absent`, and `has_denorm_loss` is `false`.

¶3 The values of these two members in the individual specializations are unspecified. That is, the standard no longer guarantees that `numeric_limits<double>::has_denorm` tells you anything true.

These two members were meant to answer: does this floating-point type support denormalized (subnormal) numbers? And is loss of precision due to denormalization or to an inexact result? The problem is that on the same machine, whether subnormal numbers are available can change with the floating-point mode at run time (for example x86's FTZ/DAZ flags), and a compile-time constant can't give a reliable answer. Implementations also disagreed on what `has_denorm_loss` meant. So C++23 deprecated them ([[P2614R2]]).

libc++ issues `-Wdeprecated-declarations` warnings for all four names above from `-std=c++23` on.

**Instead**: `numeric_limits<T>::denorm_min()` is still in the main text, returning the smallest positive subnormal value, or the smallest positive normalized value when subnormals aren't supported. If you need to know the run-time behavior, detect it at run time.

## D.11 Deprecated C macros {#depr.c.macros}

¶1 `<cfloat>` has the macros `FLT_HAS_SUBNORM`, `DBL_HAS_SUBNORM`, `LDBL_HAS_SUBNORM` and `DECIMAL_DIG`, defined as in C's `<float.h>`. C23 marks them obsolescent: `*_HAS_SUBNORM` has the same problem as `has_denorm` above, and `DECIMAL_DIG` has been superseded by the per-type `FLT_DECIMAL_DIG`, `DBL_DECIMAL_DIG` and `LDBL_DECIMAL_DIG`.

¶2 The macros `INFINITY` and `NAN` should normally be obtained from `<cfloat>`. Including `<cmath>` also provides them, and it is this way of obtaining them that is deprecated. C23 moved the primary home of these two macros to `<float.h>`, making the copies in `<math.h>` an obsolescent feature, and C++ followed suit.

¶3 The macro `__bool_true_false_are_defined` in `<stdbool.h>` has the value 1. In C23, `bool`, `true` and `false` became keywords, so this macro for detecting whether those macros are defined became pointless.

Macros can't be marked `[[deprecated]]`, and libc++ gives no warning for any of these macros (not even under `-Wdeprecated`). The replacements are the `DBL_DECIMAL_DIG` family of macros, getting `INFINITY` and `NAN` from `<cfloat>`, or using `std::numeric_limits<double>::infinity()` and `quiet_NaN()`.

## D.12 Deprecated error numbers {#depr.cerrno}

```cpp
#include <cerrno>
#include <system_error>
int en = ENODATA;                           // macro: no warning
auto ec = std::errc::no_message_available;  // deprecated
```

¶1–¶2 `<cerrno>` additionally defines the macros `ENODATA`, `ENOSR`, `ENOSTR` and `ETIME`, with meanings specified by POSIX. ¶3–¶4 `enum class errc` additionally has the corresponding enumerators `no_message_available`, `no_stream_resources`, `not_a_stream` and `stream_timeout`, with the same values as these macros.

These four error codes belong to POSIX's STREAMS subsystem. POSIX marked STREAMS obsolescent and removed it from later versions, and C++ deprecated them accordingly.

libc++ warns about these `errc` enumerators in all language modes; the macros produce no warning. Ordinary code has no use for them; if you really need to interact with STREAMS, use the macros from the platform headers directly.

## D.13 Deprecated type traits {#depr.meta.types}

¶1 `<type_traits>` additionally provides `is_trivial`, `is_pod`, `aligned_storage` and `aligned_union`, along with the corresponding `_v` variable templates and `_t` alias templates. ¶2 A program that adds specializations for them has undefined behavior, unless the specification of the corresponding template explicitly allows it.

### `is_trivial` and trivial types

¶3 A **trivial class** is a class that is trivially copyable and has one or more eligible default constructors, all of which are trivial. A **trivial type** is a scalar type, a trivial class, an array of these, or a cv-qualified version of these. ¶6 specifies that `is_trivial<T>` is `true_type` when `T` is a trivial type. ¶5 requires `T` (after removing array extents) to be a complete type or cv `void`, and ¶7 notes that whether a closure type is a trivial type is unspecified.

The concept of a trivial type is now defined only here; C++26 moved it out of the main text ([[P3247R2]]). It bundles trivially default constructible together with trivially copyable, and real code almost never needs exactly both at once. When the main text describes memory operations, it uses two more precise concepts: **trivially copyable** ([[basic.types.general]], can be copied with `memcpy`) and **implicit-lifetime type** ([[g:implicit-lifetime-type]], can be created implicitly by operations such as `malloc`).

libc++ warns about `is_trivial_v` under `-std=c++2c`, with a suggestion: `Consider using is_trivially_copyable_v<T> && is_trivially_default_constructible_v<T> instead.`

### `is_pod` and POD

¶4 A **POD class** is a class that is both a trivial class and a standard-layout class, and has no non-static data members of non-POD class type (or array thereof). A **POD type** is a scalar type, a POD class, an array of these, or a cv-qualified version of these. ¶9 specifies that `is_pod<T>` is `true_type` when `T` is a POD type; the preconditions and note in ¶8 and ¶10 are the same as for `is_trivial`.

C++11 split POD into two independent concepts, trivial and standard-layout, with POD being their intersection. Wherever POD is required, in practice only one half is ever needed: to `memcpy`, check trivially copyable; to share a layout with C, check `is_standard_layout`. So C++20 deprecated `is_pod` ([[P0767R1]]), and libc++ warns from `-std=c++20` on.

### `aligned_storage` and `aligned_union`

<div class="compare" markdown="1">

```cpp
#include <type_traits>
template<class T> struct Slot1 {
  // deprecated
  std::aligned_storage_t<
      sizeof(T), alignof(T)> buf;
};
```

```cpp
#include <cstddef>
template<class T> struct Slot2 {
  // replacement
  alignas(T)
    std::byte buf[sizeof(T)];
};
```

</div>

¶11–¶13 `aligned_storage<Len, Align>::type` is a trivial standard-layout type that can be used as uninitialized storage for any object whose size is at most `Len` and whose alignment is a divisor of `Align`. The default value of `Align` is the most stringent alignment requirement of any object type whose size is no greater than `Len`. The note in ¶14 points out that it can be replaced by a `std::byte[Len]` array declared with `alignas(Align)`; ¶15 gives such a typical implementation.

¶16–¶17 `aligned_union<Len, Types...>::type` can hold an object of any of the `Types`, and is at least `Len` in size; the static member `alignment_value` is the strictest alignment among these types.

These two templates are easy to misuse. If you forget the `::type`, `std::aligned_storage<16, 8>` itself is just an empty class, with `sizeof` 1 in libc++, and using it as storage goes out of bounds. Omitting `Align` gives a default alignment that may differ from what you need. And whatever they can do, an `alignas` array does more directly. C++23 deprecated them ([[P1413R3]]), and libc++ warns from `-std=c++23` on.

**Instead**: `alignas(T) std::byte buf[sizeof(T)]`. For the union case, write `alignas(Ts...) std::byte buf[std::max({sizeof(Ts)...})]`. After creating an object in this storage with placement new, obtain a pointer through `std::launder(reinterpret_cast<T*>(buf))`.

| Deprecated trait | Use instead |
|---|---|
| `is_trivial<T>` | `is_trivially_copyable<T>`, `is_trivially_default_constructible<T>`, depending on which you actually need; to decide whether it can be used directly after `malloc`, use `is_implicit_lifetime<T>` (C++23) |
| `is_pod<T>` | `is_standard_layout<T>` plus the traits above |
| `aligned_storage`, `aligned_union` | A `std::byte` array declared with `alignas` |

## D.14 Relational operators: `std::rel_ops` {#depr.relops}

```cpp
#include <utility>
struct R {
  bool operator==(const R&) const;
  bool operator<(const R&) const;
};
bool rel(R a, R b) {
  using namespace std::rel_ops;
  return a != b && a > b;
}
```

¶1–¶2 The namespace `std::rel_ops` in `<utility>` provides four function templates that give a type defining only `==` and `<` the other four operators automatically:

| Template | Precondition | Returns |
|---|---|---|
| ¶3–¶4 `operator!=(x, y)` | `T` meets *Cpp17EqualityComparable* | `!(x == y)` |
| ¶5–¶6 `operator>(x, y)` | `T` meets *Cpp17LessThanComparable* | `y < x` |
| ¶7–¶8 `operator<=(x, y)` | Same as above | `!(y < x)` |
| ¶9–¶10 `operator>=(x, y)` | Same as above | `!(x < y)` |

It has to be brought in with `using namespace std::rel_ops;`. This has two consequences: template code in other namespaces can't see these operators, because ADL doesn't look in `std::rel_ops`; and once brought in, every type in scope gets these four operator templates. C++20's three-way comparison and rewritten candidates ([[over.match.oper]]) solved the same problem at the language level, and `rel_ops` was deprecated as a result.

Under libc++ with `-std=c++20`, the example above warns only at `a > b`, not at `a != b`. The reason is that in C++20 `a != b` has another candidate, `!(a == b)`, rewritten from `R::operator==`. That is a non-template function, while `rel_ops::operator!=` is a function template specialization, and overload resolution prefers the non-template function in a tie, so the `rel_ops` version isn't called at all.

**Instead**: define `operator==` and `operator<=>` for the type, usually as `= default`. `!=`, `<`, `>`, `<=` and `>=` are all provided by rewritten candidates.

## D.15 `volatile` specializations for `tuple` {#depr.tuple}

```cpp
#include <tuple>
#include <type_traits>
using V = volatile std::tuple<int, long>;
static_assert(std::tuple_size<V>::value == 2);         // deprecated
static_assert(std::tuple_size<std::remove_volatile_t<V>>::value == 2);
```

¶1 `<tuple>` additionally provides `tuple_size<volatile T>`, `tuple_size<const volatile T>`, `tuple_element<I, volatile T>` and `tuple_element<I, const volatile T>`.

¶2–¶3 The two `tuple_size` specializations derive from `integral_constant<size_t, tuple_size<T>::value>` when `tuple_size<T>::value` is well-formed, and otherwise have no `value` member. This lets them be used safely in SFINAE. ¶5 The two `tuple_element` specializations give `volatile TE` and `const volatile TE` respectively, where `TE` is `tuple_element_t<I, T>`. ¶4 and ¶6 specify that they are also available when `<array>`, `<ranges>` or `<utility>` is included.

`tuple_size<const T>` and `tuple_element<I, const T>` aren't here; they are still part of the main text ([[tuple]]).

## D.16 `volatile` specializations for `variant` {#depr.variant}

¶1–¶3 `<variant>` additionally provides the same four specializations for `variant_size` and `variant_alternative`, with the same rules as D.15.

Deprecating these two groups of specializations was part of C++20's `volatile` cleanup, in the same batch as [[depr.volatile.type]]. A `volatile` `tuple`, `pair`, `array` or `variant` makes almost no sense: `std::get` doesn't accept `volatile` references, and the object as a whole can't be accessed with `volatile` semantics anyway.

libc++ gives no warning for any of these specializations. When needed, remove `volatile` first, as with `std::remove_volatile_t<V>` in the example above.

## D.17 The static `swap` of `vector<bool>` {#depr.vector.bool.swap}

```cpp
#include <vector>
void f(std::vector<bool>& v) {
  std::vector<bool>::swap(v[0], v[1]);  // deprecated
  swap(v[0], v[1]);  // replacement: ADL finds the friend swap of reference
}
```

¶1–¶2 `vector<bool, Allocator>` additionally has a static member function `static constexpr void swap(reference x, reference y) noexcept;`, with effects as if by `bool b = x; x = y; y = b;`.

The `reference` of `vector<bool>` is a proxy class, not `bool&`. `v[i]` returns a temporary of the proxy type, which the generic `std::swap` can't bind to, which is why this static member was added in the first place. But it has the same name as the member `swap(vector&)` that swaps whole containers, with a completely different signature, which invites confusion. Nowadays `vector<bool>::reference` has three friend `swap`s of its own ([[vector.bool]]), and simply writing `swap(v[i], v[j])` finds them through ADL.

libc++ gives no warning for the static `swap`.

## D.18 The `std::iterator` class template {#depr.iterator}

¶1–¶2 `<iterator>` additionally provides the class template `iterator<Category, T, Distance = ptrdiff_t, Pointer = T*, Reference = T&>`, which defines only five member type aliases: `iterator_category`, `value_type`, `difference_type`, `pointer` and `reference`. A custom iterator can derive from it to avoid writing these aliases by hand. The example in ¶4 shows this usage.

```cpp
#include <iterator>
template<class T>
struct It : std::iterator<std::forward_iterator_tag, T> {  // deprecated
  // value_type v;  // error: a member of a dependent base, not found by unqualified lookup
};
```

The note in ¶3 explains its problem: if the new iterator is itself a class template, these aliases aren't visible inside the class template, only to its users. The base class depends on template parameters, and names in it aren't found by unqualified lookup ([[temp.dep]]). So you have to write `using value_type = ...;` again inside the class anyway, cancelling out the code the base class saved. Moreover, the order of the five template parameters is hard to remember, with `Distance` before `Pointer`; getting one position wrong silently defines the wrong aliases.

libc++ warns from `-std=c++17` on. The replacement is to write these aliases directly in the iterator class; from C++20 you should also add `iterator_concept`.

## D.19 `move_iterator::operator->` {#depr.move.iter.elem}

```cpp
#include <iterator>
#include <string>
void f(std::string* p) {
  std::move_iterator<std::string*> m(p);
  auto n1 = m->size();          // deprecated
  auto n2 = (*m).size();        // *m is std::string&&
  auto n3 = m.base()->size();   // explicitly through the underlying iterator
}
```

¶1–¶2 `move_iterator<Iterator>` additionally has the member `constexpr pointer operator->() const;`, which returns the underlying iterator `current`.

The purpose of `move_iterator` is to make dereferencing yield an rvalue: `*m` is `std::move(*current)`. But `m->x` accesses the member through the underlying iterator and yields an lvalue. On the same iterator, `(*m).x` and `m->x` have different value categories, breaking the convention that `->` is equivalent to `(*).`, so C++20 deprecated it. libc++ warns from `-std=c++20` on.

## Summary

| Subclause | Feature | Instead | libc++ warning |
|---|---|---|---|
| D.10 | `has_denorm`, `has_denorm_loss` | `denorm_min()`, run-time detection | Since C++23 |
| D.11 | Macros such as `*_HAS_SUBNORM` and `DECIMAL_DIG` | `DBL_DECIMAL_DIG` etc. | None |
| D.12 | STREAMS error codes | Platform headers | Only the `errc` enumerators, all modes |
| D.13 | `is_trivial`, `is_pod`, `aligned_storage`, `aligned_union` | Precise type traits, `alignas` arrays | `is_pod` since C++20, `aligned_*` since C++23, `is_trivial` C++26 |
| D.14 | `std::rel_ops` | `operator==` plus `operator<=>` | Since C++20 (`!=` doesn't trigger it because of rewritten candidates) |
| D.15, D.16 | `volatile` specializations for `tuple` and `variant` | `remove_volatile_t` | None |
| D.17 | The static `swap` of `vector<bool>` | Call `swap` through ADL | None |
| D.18 | `std::iterator` | Write the type aliases directly | Since C++17 |
| D.19 | `move_iterator::operator->` | `(*m).x` or `m.base()->x` | Since C++20 |
