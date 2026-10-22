---
title: Arithmetic types
summary: "The exact-width, minimum-width and fastest integer types of <cstdint>, plus intptr_t and intmax_t, and the optional extended floating-point type aliases float16_t through bfloat16_t in <stdfloat>."
updated: 2026-10-19
---

!!! tldr
    - Exact-width types such as `int32_t` have exactly N bits and no padding bits. They are optional, but if the platform has such an integer type, the implementation must provide them.
    - Types of at least N bits, such as `int_least32_t` and `int_fast32_t`, always exist for N of 8, 16, 32 and 64.
    - In C++, `intptr_t` and `uintptr_t` always exist; in C they are optional.
    - On mainstream implementations `int8_t` is `signed char`, and it is printed as a character.
    - The `<stdfloat>` aliases such as `float16_t` are all optional, and when they exist they are types distinct from `float` and `double`; Clang 23 + libc++ doesn't provide them yet.

[[basic.fundamental]] specifies only minimum widths for the standard integer types, for example at least 16 bits for `int` and at least 32 bits for `long`; the exact widths are up to the implementation. When you need an integer of exactly 32 bits or at least 64 bits, use `<cstdint>`; when you need an IEEE 754 16-bit floating-point number, use `<stdfloat>`.

## `<cstdint>` ([cstdint.syn])

¶1 `<cstdint>` supplies integer types having specified widths, and macros that specify the limits of those types. The whole header must be provided by freestanding implementations too. There are five families of types, where N is the width:

| Type | Meaning | Always present? |
|---|---|---|
| `intN_t`, `uintN_t` | Exactly N bits, no padding bits | Optional (¶3) |
| `int_leastN_t`, `uint_leastN_t` | The narrowest type with at least N bits | Always present for N of 8, 16, 32, 64 |
| `int_fastN_t`, `uint_fastN_t` | The usually fastest type with at least N bits | Always present for N of 8, 16, 32, 64 |
| `intmax_t`, `uintmax_t` | The widest integer type (with an exception; see below) | Always present |
| `intptr_t`, `uintptr_t` | An integer type that can round-trip a `void*` | Always present in C++ (¶2) |

The macros include `INT32_MIN`, `INT32_MAX`, `UINT32_MAX`, the width macros such as `INT32_WIDTH` added in C23, `PTRDIFF_MAX`, `SIZE_MAX`, and the constant-building `INT64_C(v)`, `UINT64_C(v)` and `INTMAX_C(v)`.

```cpp run title="cstdint.cpp" impl
#include <cstdint>
#include <type_traits>

static_assert(sizeof(std::int32_t) * 8 == 32);         // exactly 32 bits when present
static_assert(sizeof(std::int_least16_t) * 8 >= 16);
static_assert(std::is_same_v<std::int8_t, signed char>); // true in practice, not guaranteed by the standard

int main() {
    int x = 0;
    auto i = reinterpret_cast<std::uintptr_t>(&x);
    int* p = reinterpret_cast<int*>(i);   // converting back gives the original pointer
    return p == &x ? 0 : 1;
}
```

### Differences from C (¶2)

¶2 The types and macros in `<cstdint>` are the same as C's `<stdint.h>`, with two differences.

First, `intptr_t`, `uintptr_t` and the macros `INTPTR_MIN`, `INTPTR_MAX` and `UINTPTR_MAX` are always defined in C++. This matches [[expr.reinterpret.cast]]: a pointer converted to a sufficiently large integer type and back yields the original value, and `intptr_t` is the sufficiently large type guaranteed to exist.

Second, `intmax_t` and `uintmax_t` need not be able to represent all values of extended integer types wider than `long long` and `unsigned long long`. `intmax_t` appears in the interfaces of C library functions such as `printf("%jd")` and `imaxabs`, and once fixed it can't be widened without breaking the ABI. With this exception, an implementation that later adds a 128-bit extended integer type doesn't have to change `intmax_t`.

### Which types always exist (¶3)

- Types with N are optional when N isn't 8, 16, 32 or 64, for example `int24_t` and `int_least128_t`.
- The exact-width types `intN_t` and `uintN_t` are optional even for N of 8, 16, 32 and 64. But if the implementation has an integer type of that width with no padding bits, it must declare these names. So on any platform with a 32-bit integer type without padding, `int32_t` is guaranteed to exist.
- Each macro is defined if and only if the corresponding typedef name exists, so `#ifdef INT8_MAX` can check whether `int8_t` exists.
- Note 1: `INTN_C` and `UINTN_C` correspond to `int_leastN_t` and `uint_leastN_t`, not `intN_t`. `INT64_C(5)` expands to an integer constant whose type is the promoted type of `int_least64_t`, such as `5LL`.

!!! pitfall "`int8_t` is a character type"
    On almost all implementations, `std::int8_t` is `signed char` and `std::uint8_t` is `unsigned char`. So `std::cout << std::int8_t{65}` prints the character `A`, not `65`. Like `unsigned char*`, a `uint8_t*` can access any object ([[basic.lval]]), so the optimizer can't assume that writes through it don't affect objects of other types. The standard doesn't guarantee that `int8_t` is `signed char`; in theory it could be an 8-bit extended integer type, but changing it would break the ABI, so in practice it won't change.

!!! impl "`int64_t` is a different type on different platforms"
    On macOS (Apple Silicon), `int64_t` is `long long` and `intptr_t` is `long`; on x86-64 Linux (glibc), `int64_t` is `long`. Both are 64 bits, yet they are different types. If a set of overloads provides only a `long` version and an `int` version, a call with an `int64_t` is an exact match on one platform and may be ambiguous on the other.

## `<stdfloat>` ([stdfloat.syn])

¶1 `<stdfloat>` declares aliases for the optional extended floating-point types specified by [[basic.extended.fp]], each guarded by the corresponding predefined macro ([[cpp.predefined]]):

```cpp
namespace std {
#if defined(__STDCPP_FLOAT16_T__)
  using float16_t = implementation-defined;   // IEEE binary16
#endif
  // likewise for float32_t, float64_t, float128_t and bfloat16_t
}
```

A compiler that defines a macro such as `__STDCPP_FLOAT16_T__` is saying it provides an extended floating-point type with the corresponding IEEE format. That type is distinct from `float` and `double`; even with the same format, `std::float64_t` isn't `double`. The literal suffixes of these types (`1.0f16`, `1.0bf16`), their conversion ranks ([[conv.rank]]), and rules such as the prohibition of implicit narrowing are all specified in the core language.

!!! impl "Not yet provided by Clang + libc++"
    Clang 23 doesn't predefine any `__STDCPP_FLOAT*_T__` macro. It has extension types such as `_Float16` and `__bf16`, but doesn't implement them as [[basic.extended.fp]] requires. libc++ has no `<stdfloat>` header either, and `#include <stdfloat>` reports that the file isn't found. GCC 13 and later, with libstdc++, support these types. Portable code should check both `__has_include(<stdfloat>)` and the corresponding macro:

```cpp run title="stdfloat-detect.cpp" ok
#if __has_include(<stdfloat>)
#  include <stdfloat>
#endif

int main() {
#if defined(__STDCPP_FLOAT16_T__)
    std::float16_t h = 1.5f16;
    return h == 1.5f16 ? 0 : 1;
#else
    return 0;                     // the implementation doesn't provide float16_t
#endif
}
```
