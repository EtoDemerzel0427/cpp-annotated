---
title: General utilities library
summary: "A guide to Clause 22: what <utility>, pair, tuple, optional, variant, any, expected, bitset, <functional> and <bit> are each for, plus the Constraints, Mandates, Preconditions and Hardened preconditions elements you need to recognize before reading the wording."
updated: 2026-10-19
---

!!! tldr
    - Clause 22 collects small components that almost every program uses but that are not containers, algorithms or I/O. Many of them are also building blocks for the rest of the library, such as `std::move`, `std::pair` and `std::invoke`.
    - `optional`, `variant`, `any` and `expected` all hold a value that may be of different kinds in a single object. The first two and `expected` never allocate, and their special member functions are conditionally trivial depending on the element types.
    - Library function specifications are split into fixed elements: if *Constraints* are not met, the function drops out of overload resolution; if *Mandates* are violated, compilation fails; violating *Preconditions* is undefined behavior.
    - C++26 turned unchecked accesses such as `optional::operator*` into *Hardened preconditions*: in a hardened implementation a violation terminates the program; in other implementations it is still undefined behavior.

## Map of the clause [utilities.general]

¶1 This Clause describes utilities that are generally useful in C++ programs; some of these utilities are used by other elements of the C++ standard library.

| Section | Subclause | Header | Contents |
|---|---|---|---|
| 22.2 | [[utility]] | `<utility>` | `swap`, `exchange`, `move`, `forward`, `declval`, safe integer comparisons `cmp_less` etc., `to_underlying`, `unreachable`; {{c++26}} `constant_wrapper` ([[const.wrap.class]]) |
| 22.3 | [[pairs]] | `<utility>` | `pair` |
| 22.4 | [[tuple]] | `<tuple>` | `tuple`, `apply`, `make_from_tuple` |
| 22.5 | [[optional]] | `<optional>` | possibly empty value `optional<T>`; {{c++26}} `optional<T&>` |
| 22.6 | [[variant]] | `<variant>` | type-safe union `variant`, `visit` |
| 22.7 | [[any]] | `<any>` | `any`, which can hold any copyable type |
| 22.8 | [[expected]] | `<expected>` | {{c++23}} value or error `expected<T, E>` |
| 22.9 | [[bitset]] | `<bitset>` | fixed-size bit sets |
| 22.10 | [[function.objects]] | `<functional>` | *INVOKE*, `reference_wrapper`, `bind_front`, `function`, `move_only_function`, `function_ref`, `hash`, etc. |
| 22.11 | [[bit]] | `<bit>` | `bit_cast`, `byteswap`, powers of 2, rotations, bit counting |
| 22.12 | [[stdbit.h.syn]] | `<stdbit.h>` | {{c++26}} the C23 bit manipulation header |

!!! note "Content that has moved"
    In C++17 and C++20, [utilities] also contained smart pointers and memory utilities, `<type_traits>`, `<ratio>`, `<charconv>`, `<format>`, execution policies, `type_index` and so on (C++17 also had `<chrono>`). They are now spread elsewhere: memory is in [[mem]], type traits and `<ratio>` in [[meta]], `<charconv>` and `<format>` in [[text]], execution policies in [[execpol]], `type_index` in [[type.index]], and the time library in [[time]]. Keep this in mind when citing subclause numbers from older standards.

## Four vocabulary types

`optional`, `variant`, `any` and `expected` are often called **vocabulary types**: when different libraries use the same type to express the same thing, their interfaces fit together. Their design trade-offs can be compared in one table:

| | `optional<T>` | `variant<Ts...>` | `any` | `expected<T, E>` |
|---|---|---|---|---|
| Holds | a `T`, or nothing | exactly one of `Ts` | any copyable type | a `T`, or an error `E` |
| Storage | inside the object | inside the object | possibly on the heap (the standard encourages avoiding allocation for small objects) | inside the object |
| Empty state | `nullopt`, a normal state | `valueless_by_exception()`, arises only from exceptions | an empty `any`, a normal state | none: always holds a value or an error |
| Accessing the wrong thing | `operator*` violates a hardened precondition; `value()` throws `bad_optional_access` | `get` throws `bad_variant_access`; `get_if` returns a null pointer | `any_cast` throws `bad_any_cast` or returns a null pointer | `operator*` violates a hardened precondition; `value()` throws `bad_expected_access<E>` |
| Triviality | special members conditionally trivial depending on `T` | depending on all `Ts` | not trivial | depending on `T` and `E` |

The last row deserves a closer look:

```cpp run title="optional-trivial.cpp" ok
#include <optional>
#include <string>
#include <type_traits>

static_assert( std::is_trivially_copyable_v<std::optional<int>>);
static_assert(!std::is_trivially_copyable_v<std::optional<std::string>>);

int main() {}
```

`optional<int>` can be copied with `memcpy` and passed in registers just like `int`; `optional<string>` cannot. For a class template to achieve this, it needs language support on two fronts: a union's special member is not deleted only when the corresponding function of every variant member is trivial ([[class.union]]); and since C++20 a class can declare several prospective destructors (and other special members) with different constraints, and the constraints select one of them ([[class.dtor]], [[special]]). See [[optional.optional]] and [[variant.variant]] for the details, and [[class.prop]] for why triviality matters.

## Elements to recognize before reading library wording

Every function in the library wording is written using the elements specified by [[structure.specifications#3]]. Violating different elements has completely different consequences:

| Element | When not satisfied |
|---|---|
| *Constraints* | the function does not participate in overload resolution; no error, and it can be detected by a `requires` expression |
| *Mandates* | the program is ill-formed and the compiler must diagnose it |
| *Constant When* | this call is not a constant subexpression |
| *Preconditions* | undefined behavior |
| *Hardened preconditions* | a hardened implementation checks the condition before the function has any other observable side effects and terminates on failure; in other implementations it is undefined behavior |

```cpp run title="mandates.cpp" error
#include <variant>
int main() {
  std::variant<int, int> v{std::in_place_index<0>, 1};
  return std::get<int>(v);   // error: int appears twice in Ts, violating Mandates
}
```

`std::get<T>(variant)` requires `T` to occur exactly once in `Ts...`. This is a *Mandates* element: violating it fails compilation outright, and the compiler does not fall back to another overload. Getting by index with `std::get<0>(v)` has no such problem. Conversely, the converting constructor of `optional<T>` uses *Constraints*: when the condition is not met, the constructor simply drops out of overload resolution, and `is_constructible_v<optional<int>, std::string>` quietly yields `false`. This distinction is what decides whether a library interface can be used in concept checks.

### Hardened preconditions {{c++26}}

```cpp title="hardened.cpp"
#include <optional>
int main() {
  std::optional<int> o;
  return *o;   // violates a hardened precondition: has_value() is false
}
```

Unchecked accessors such as `optional::operator*`, `expected::operator->` and `bitset::operator[]` used to have ordinary preconditions, and violating them was undefined behavior. C++26 changed them to hardened preconditions: the same code, run against a hardened standard library, terminates deterministically at this point. In our tests, compiling the program above against libc++ with `-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_FAST` makes it terminate at run time with `SIGTRAP`; without that macro there is no check at all. See [[intro.compliance]] for which implementations count as hardened.

Another common phrase is Equivalent to: when *Effects* says a function is equivalent to some code, the semantics of that code (which functions it calls, which exceptions it throws, whether it can be used in constant evaluation) are the semantics of the function ([[structure.specifications#4]]). `std::apply`, `optional::value_or`, `expected`'s `and_then` and others are all defined this way.

## Suggested reading order

1. [[utility]]: `move`, `forward` and `declval` are the basic vocabulary for reading the rest of the wording.
2. [[func.require]]: the definition of *INVOKE*, on which `apply`, `visit`, `function` and `optional::and_then` are all built.
3. [[pairs]] and [[tuple]]: the tuple-like protocol and its relationship to structured bindings ([[dcl.struct.bind]]).
4. [[optional.optional]], [[variant.variant]], [[expected.expected]]: the same conditional-triviality technique used three times; [[any]] is the type-erased contrast.
5. [[func.wrap]]: the trade-offs among the four polymorphic function wrappers.
6. [[bit]]: `bit_cast` is the standard, legal way to reinterpret an object representation; read it alongside the aliasing rules in [[basic.lval]].

## Questions

!!! question "Question"
    Is `std::optional<int>` trivially copyable? Where does the standard guarantee this?

<details markdown="1">
<summary>Answer</summary>

Yes. [optional.ctor] specifies that if `is_trivially_copy_constructible_v<T>` is true, the copy constructor is trivial; the move constructor, copy assignment, move assignment and destructor ([optional.dtor]) all have similar provisions. `int` satisfies all of the conditions, so `optional<int>` meets the definition of a trivially copyable class in [[class.prop]]. The copy constructor and destructor of `std::string` are not trivial, so `optional<std::string>` is not trivially copyable.
</details>
