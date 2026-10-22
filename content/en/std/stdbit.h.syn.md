---
title: "Header <stdbit.h> synopsis"
summary: C++26 adopts C23's <stdbit.h> so that one header can be compiled as both C and C++; its functions are close to those in <bit>, but the names are in the global namespace, are not constexpr, and return unsigned types.
updated: 2026-10-19
---

!!! tldr
    - `<stdbit.h>` comes from C23 and provides bit counting, power-of-2 functions and endianness macros. C++26 adopts it only so that C and C++ can share the same header. Pure C++ code should use `<bit>` ([[bit]]).
    - Each function family has 5 ordinary functions named by argument type (`_uc` to `_ull`), plus one function template that replaces C's type-generic macro.
    - The function template *Mandates* an unsigned integer type: passing an `int` is ill-formed, whereas the corresponding `<bit>` function simply does not participate in overload resolution.
    - The names are in the global namespace, there is no `<cstdbit>`, the functions are not `constexpr`, and counts are returned as unsigned types.

## Contents ([stdbit.h.syn])

C23 added the header `<stdbit.h>`. Since {{c++26}} C++ provides it too ([[P3370]], together with `<stdckdint.h>`, as the new headers coming from C23). The first line of the synopsis is `// all freestanding`, and the contents fall into three parts:

1. The version macro `__STDC_VERSION_STDBIT_H__`, with value `202311L`.
2. The endianness macros `__STDC_ENDIAN_BIG__`, `__STDC_ENDIAN_LITTLE__` and `__STDC_ENDIAN_NATIVE__`, with values as specified by the C standard. They correspond one-to-one to the three values of `std::endian` ([[bit.endian]]).
3. 14 groups of functions. Each group has 5 ordinary functions distinguished by an argument-type suffix (`_uc`, `_us`, `_ui`, `_ul`, `_ull`, for `unsigned char` through `unsigned long long`), plus 1 function template.

| C function family | Corresponding `<bit>` function | Return type of the ordinary functions |
|---|---|---|
| `stdc_leading_zeros`, `stdc_leading_ones` | `countl_zero`, `countl_one` | `unsigned int` |
| `stdc_trailing_zeros`, `stdc_trailing_ones` | `countr_zero`, `countr_one` | `unsigned int` |
| `stdc_first_leading_zero`, `stdc_first_leading_one` | none | `unsigned int` |
| `stdc_first_trailing_zero`, `stdc_first_trailing_one` | none | `unsigned int` |
| `stdc_count_zeros`, `stdc_count_ones` | `popcount` and its complement | `unsigned int` |
| `stdc_has_single_bit` | `has_single_bit` | `bool` |
| `stdc_bit_width` | `bit_width` | `unsigned int` |
| `stdc_bit_floor`, `stdc_bit_ceil` | `bit_floor`, `bit_ceil` | same as the argument type |

The `first_*` functions return a position, not a count. Per the C standard it is the 1-based position counted from the corresponding end, and 0 if no such bit is found. `<bit>` has no counterpart; when composing one from something like `countl_zero(x) + 1`, the not-found case needs separate handling.

## Function templates instead of type-generic macros (¶1–¶3)

In C, `stdc_leading_zeros(value)` is a type-generic macro that selects the matching function by argument type. C++ has no `_Generic`, so the synopsis declares them as function templates, for example `template<class T> see below stdc_leading_zeros(T value);`.

¶1 A function template whose return type is not spelled out in the synopsis returns an implementation-defined unsigned integer type large enough to represent all possible results. Each template has the same semantics as the type-generic function of the same name in the C standard (ISO/IEC 9899:2024, subclause 7.18).

¶2 *Mandates*: `T` is an unsigned integer type. This uses *Mandates*, whereas `<bit>` uses *Constraints* ([[structure.specifications]]). The difference shows when an `int` is passed:

- `std::popcount(1)` finds no matching function, because the function template does not participate in overload resolution; this can be detected with a `requires` expression;
- `stdc_count_ones(1)` selects the function template and is then ill-formed because the *Mandates* is not met, which requires a diagnostic. Implementations usually do this with `static_assert`, so it generally cannot be detected with SFINAE or `requires`.

¶3 Otherwise, the contents and meaning of `<stdbit.h>` are the same as the C standard library's `<stdbit.h>`.

## Differences from `<bit>`

- The names are in the global namespace; there is no `std::` version and no `<cstdbit>`. Like `<stdckdint.h>` and `<stdatomic.h>`, this header exists only for C compatibility ([[support.c.headers]]).
- None of the functions is `constexpr` or `noexcept`. Use `<bit>` for compile-time computation.
- The counting functions return `unsigned int` or an implementation-defined unsigned type, while `<bit>` returns `int`. Watch for signed/unsigned comparison warnings when mixing the two.

At the time of writing, the libc++ we tested (LLVM 23) does not provide `<stdbit.h>`, and neither does the C library in the macOS SDK; `#include <stdbit.h>` fails to find the file in both C and C++ modes. That is why this page has no runnable example.

## Summary

| Aspect | `<stdbit.h>` | `<bit>` |
|---|---|---|
| Origin | C23, adopted by C++26 | C++20 |
| Namespace | global | `std` |
| Generic form | function template, *Mandates* unsigned integer | function template, *Constraints* unsigned integer |
| `constexpr` | no | yes |
| Type of count results | `unsigned int` or implementation-defined | `int` |
| Use | headers shared by C and C++ | first choice in C++ code |
