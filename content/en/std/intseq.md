---
title: Compile-time integer sequences
summary: "integer_sequence packs a list of integer constants into a type; passed to a function template it can be deduced as a parameter pack and expanded; make_index_sequence<N> generates 0..N-1; since C++26 it can also be destructured with structured bindings."
updated: 2026-10-19
---

!!! tldr
    - `std::index_sequence<0, 1, 2>` is an empty class; all of its information is in its template arguments.
    - Passing such an object to a function template whose parameter is `index_sequence<I...>` makes deduction produce the parameter pack `I...`, so the function body can write `std::get<I>(t)...`.
    - `make_index_sequence<N>` is an alias for `index_sequence<0, …, N-1>`, and `index_sequence_for<Ts...>` generates a sequence by the length of a pack.
    - Since C++26 integer sequences support the tuple protocol, so `auto [...Is] = std::make_index_sequence<N>{};` gives a pack directly inside a function template.

## The problem: a loop variable is not a constant

The natural way to reverse a `tuple` is to loop `I` from 0 to N-1 and take `std::get<N-1-I>(t)` each time. But the index of `std::get` is a template argument and must be a constant expression; an ordinary loop variable will not do.

The only thing in a template that can be expanded as a list of constants is a parameter pack ([[temp.variadic]]), and parameter packs are obtained through template argument deduction. The approach of [intseq] is to encode 0, 1, …, N-1 into a type and let deduction turn it back into a pack:

```cpp title="index-sequence.cpp" run ok
#include <cstdio>
#include <tuple>
#include <utility>

template<class Tuple, std::size_t... I>
auto reverse_impl(const Tuple& t, std::index_sequence<I...>) {
    constexpr std::size_t N = sizeof...(I);
    return std::make_tuple(std::get<N - 1 - I>(t)...);   // I is 0,1,...,N-1 in turn
}

template<class... Ts>
auto reverse(const std::tuple<Ts...>& t) {
    return reverse_impl(t, std::index_sequence_for<Ts...>{});
}

int main() {
    auto r = reverse(std::make_tuple(1, 2.5, 'c'));
    std::printf("%c %g %d\n", std::get<0>(r), std::get<1>(r), std::get<2>(r));   // c 2.5 1
}
```

`reverse` constructs an `index_sequence<0, 1, 2>` object and passes it to `reverse_impl`; deduction gives `I... = 0, 1, 2` ([[temp.deduct.call]]), and `std::get<N - 1 - I>(t)...` expands the pack into three calls.

[intseq.general] ¶1 describes exactly this use: when an integer sequence is used as an argument to a function template, the template parameter pack defining the sequence can be deduced and used in a pack expansion. Note 1 mentions that `index_sequence` is a convenience alias for the `size_t` case and points to `std::apply` ([[tuple.apply]]), a typical user of this technique.

Since C++20 a separate `_impl` function is unnecessary; a generic lambda with a template parameter list can deduce in place:

```cpp title="lambda-seq.cpp" run ok
#include <utility>

constexpr auto sum = []<std::size_t... I>(std::index_sequence<I...>) {
    return (I + ... + 0);
}(std::make_index_sequence<101>{});
static_assert(sum == 5050);

int main() {}
```

## `integer_sequence` [intseq.intseq]

```cpp
namespace std {
  template<class T, T... I> struct integer_sequence {
    using value_type = T;
    static constexpr size_t size() noexcept { return sizeof...(I); }
  };
}
```

It has no data members, and `size()` is just `sizeof...(I)`.

¶1 *Mandates*: `T` is an integer type. By [[basic.fundamental]], integer type is a synonym for integral type, so `bool` and the character types are allowed, but floating-point types are not. If the *Mandates* is not met, the program is ill-formed and the compiler must diagnose it:

```cpp title="intseq-mandates.cpp" run error
#include <utility>

std::integer_sequence<bool, true, false> ok;   // OK: bool is an integral type
std::integer_sequence<double> bad;             // error: only integral types are allowed
```

libc++ implements this requirement with a `static_assert`.

## `make_integer_sequence` [intseq.make]

```cpp
template<class T, T N>
  using make_integer_sequence = integer_sequence<T, /* 0, 1, …, N-1 */>;
template<size_t N>
  using make_index_sequence = make_integer_sequence<size_t, N>;
template<class... T>
  using index_sequence_for = make_index_sequence<sizeof...(T)>;
```

¶1 *Mandates*: `N ≥ 0`.

¶2 `make_integer_sequence<T, N>` is an alias for `integer_sequence<T, 0, 1, …, N-1>`. Note 1 says that when `N` is 0 the result is the empty sequence `integer_sequence<T>`.

These are all alias templates, so `make_index_sequence<3>` and `index_sequence<0, 1, 2>` are the same type, and `is_same_v` is true.

!!! impl "Compiler-builtin generators"
    Implementing `make_integer_sequence` by recursion or by doubling needs O(N) or O(log N) levels of template instantiation, and runs into the instantiation depth limit for large N. Clang provides the builtin alias template `__make_integer_seq<Template, T, N>` and GCC provides `__integer_pack(N)...`, each producing the whole sequence in one step. libc++ uses the former if available and the latter otherwise.

    For negative `N`, Clang reports integer sequences must have non-negative sequence length directly; this is the diagnostic ¶1 requires.

## Structured binding support [intseq.binding] {{c++26}}

C++26 gives integer sequences the tuple protocol, i.e. specializations of `tuple_size` and `tuple_element` and a non-member `get`:

```cpp
template<class T, T... Values>
  struct tuple_size<integer_sequence<T, Values...>>
    : integral_constant<size_t, sizeof...(Values)> { };
template<size_t I, class T, T... Values>
  struct tuple_element<I, integer_sequence<T, Values...>> { using type = T; };
template<size_t I, class T, T... Values>
  struct tuple_element<I, const integer_sequence<T, Values...>> { using type = T; };
template<size_t I, class T, T... Values>
  constexpr T get(integer_sequence<T, Values...>) noexcept;
```

¶1–¶2 Both *Mandates* require `I < sizeof...(Values)`; an out-of-range index is ill-formed, not UB. ¶3 `get` returns `Values...[I]`; the specification uses C++26 pack indexing ([[g:pack-index]]) directly.

So integer sequences can be destructured by structured bindings ([[dcl.struct.bind]]) and expansion statements ([[stmt.expand]]). Combined with C++26 structured binding packs ([[P1061R10]]), a function body can get the pack 0..N-1 directly, with no helper function:

```cpp title="binding-pack.cpp" run ok
#include <utility>

template<std::size_t N>
constexpr std::size_t triangular() {
    auto [...Is] = std::make_index_sequence<N>{};   // Is... is a structured binding pack
    return (Is + ... + 0);
}
static_assert(triangular<5>() == 10);

int main() {
    auto [a, b, c] = std::make_index_sequence<3>{};   // a=0, b=1, c=2
    return static_cast<int>(a + b + c) - 3;
}
```

Structured binding packs can only appear in templates. A declaration containing a structured binding pack must declare a templated entity ([[dcl.pre]]), so writing `auto [...Is] = ...;` directly in `main` is ill-formed; Clang reports pack declaration outside of template.

!!! note "Why `get` takes its parameter by value, and why `tuple_element` has a separate `const` version"
    The values of the sequence are all in the type, so `get` does not need to read the object; taking an empty class by value costs nothing, and it returns a prvalue of `T`.

    The general `tuple_element<I, const U>` ([[tuple.helper]]) would give `const T`. The standard additionally provides a version for `const integer_sequence` whose `type` is `T`, so in `const auto [a, b] = std::index_sequence<1, 2>{};`, `decltype(a)` is still `size_t`, consistent with the return type of `get` (verified with Clang 23).

## Common mistakes

!!! pitfall "An integer sequence does not produce a pack by itself"
    What produces the pack is template argument deduction for a function template, or a C++26 structured binding pack. After `using S = std::make_index_sequence<3>;`, there is no way to expand `S` in non-template code; it has to be handed to a template whose parameter type is `integer_sequence<T, I...>`.

!!! pitfall "`T` must match"
    `make_integer_sequence<int, 5>` is `integer_sequence<int, 0, 1, 2, 3, 4>`, not `index_sequence<0, 1, 2, 3, 4>` (whose `T` is `size_t`). A function whose parameter is `std::index_sequence<I...>` cannot deduce from it.

## Questions

!!! question "Question 1"
    Is `std::make_integer_sequence<unsigned char, 300>` well-formed?

<details markdown="1">
<summary>Answer</summary>

No. The type of the alias template's second template parameter is `T`, i.e. `unsigned char`, and the argument `300` must be a converted constant expression ([[g:converted-constant-expression]]) of type `unsigned char`. Converting `300` to `unsigned char` is a narrowing conversion, so the template argument is ill-formed ([[temp.arg.nontype]]), and the error occurs before the *Mandates* of [intseq.make] ¶1 is even checked.
</details>

!!! question "Question 2"
    What happens with `std::get<0>(std::index_sequence<>{})`?

<details markdown="1">
<summary>Answer</summary>

The *Mandates* `I < sizeof...(Values)` of [intseq.binding] ¶2 is not met (`0 < 0` is false), so the program is ill-formed and must be diagnosed. libc++ triggers a `static_assert` first, and Clang then also reports the pack index out of range.
</details>

## Summary

| Component | Key points |
|---|---|
| `integer_sequence<T, I...>` | Empty class; `T` must be an integral type (including `bool` and character types); `size()` equals `sizeof...(I)` |
| `make_integer_sequence<T, N>` | Alias for `integer_sequence<T, 0, …, N-1>`; `N ≥ 0`; implemented with compiler builtins |
| `index_sequence` etc. | Convenience aliases for `size_t` |
| C++26 tuple protocol | `tuple_size`, `tuple_element`, `get`; out-of-range is ill-formed; usable with structured bindings and structured binding packs |
