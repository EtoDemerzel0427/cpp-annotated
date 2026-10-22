---
title: "C compatibility: checked integer arithmetic"
summary: "C23's <stdckdint.h> provides three function templates in C++, ckd_add, ckd_sub and ckd_mul: they compute over the mathematical integers, write the result back modulo 2ᴺ, and report overflow through the return value, so they never trigger the UB of signed overflow."
updated: 2026-10-19
---

!!! tldr
    - `ckd_add(&r, a, b)` computes `a + b` as a mathematical integer, writes the result into `r` modulo 2ᴺ, and returns `true` on overflow. There is no UB anywhere in the process.
    - The types of the three operands are independent and no usual arithmetic conversions are done, so `ckd_sub(&ll, 0u, 1)` gives −1, not `UINT_MAX`.
    - All three types must be signed or unsigned integer types; `bool`, plain `char`, character types and enumerations are not allowed.
    - There is only the header `<stdckdint.h>`, with the names in the global namespace; there is no `<cstdckdint>` and no `std::ckd_add`.

## Why overflow detection is hard to write

Signed integer overflow is UB ([[expr.pre#4]]). Computing `a + b` first and then checking whether the sign flipped already triggers the UB; comparing `a > INT_MAX - b` first avoids the UB but is easy to get wrong, and gets messier with mixed types.

C23 added `<stdckdint.h>` for this, and C++26 {{c++26}} brings it into C++ in [numerics.c]:

```cpp run title="ckd.cpp" ok
#include <climits>
#include <cstdio>
#include <stdckdint.h>

int main() {
  int r;
  bool ovf = ckd_add(&r, INT_MAX, 1);
  std::printf("%d %d\n", ovf, r);      // 1 -2147483648

  unsigned char uc;
  ovf = ckd_mul(&uc, 16, 16);
  std::printf("%d %d\n", ovf, uc);     // 1 0

  long long ll;
  ovf = ckd_sub(&ll, 0u, 1);
  std::printf("%d %lld\n", ovf, ll);   // 0 -1
}
```

The first line overflows: `r` holds the wrapped-around value and `true` is returned. In the second, 256 does not fit in an `unsigned char`, so `true` is returned as well. The third is the most noteworthy: the built-in expression `0u - 1` would first convert `1` to `unsigned`, giving `UINT_MAX`; `ckd_sub` computes over the mathematical integers and gets −1, which fits in `long long`, so it is not an overflow.

## The header ([stdckdint.h.syn])

```cpp
#define __STDC_VERSION_STDCKDINT_H__ 202311L

template<class type1, class type2, class type3>
  bool ckd_add(type1* result, type2 a, type3 b);
template<class type1, class type2, class type3>
  bool ckd_sub(type1* result, type2 a, type3 b);
template<class type1, class type2, class type3>
  bool ckd_mul(type1* result, type2 a, type3 b);
```

In C, `ckd_add` and friends are type-generic macros; in C++ they are specified as function templates, with three independent type parameters.

This header exists only in the form `<stdckdint.h>`, with declarations in the global namespace. The rule for most C headers `<name.h>` is "the same as `<cname>`, with the names also placed in the global namespace", but [[support.c.headers.other]] exempts a few headers from this rule, including `<stdckdint.h>`, `<stdbit.h>` ([[stdbit.h.syn]]) and `<stdatomic.h>`; they have no corresponding `<cname>`.

## Semantics ([numerics.c.ckdint])

¶1 *Mandates*: `type1`, `type2` and `type3` are all signed or unsigned integer types ([[basic.fundamental]]).

This excludes `bool`, plain `char` (which counts as neither a signed nor an unsigned integer type), character types such as `char8_t`, enumerations and floating-point types.

```cpp title="ckd-mandates.cpp" error
#include <stdckdint.h>

bool f(bool* r) { return ckd_add(r, 1, 1); }   // error: bool is not a signed or unsigned integer type
bool g(char* r) { return ckd_add(r, 1, 1); }   // error: neither is plain char
```

¶2 *Remarks*: each function template has the same semantics as the type-generic macro of the same name in C. C23 specifies the semantics in three steps:

1. treat `a` and `b` as mathematical integers (infinite precision) and compute a + b, a − b or a × b;
2. write the mathematical result modulo 2ᴺ into `*result`, where N is the width of `*result`'s type;
3. return `false` if the mathematical result is exactly representable in `*result`'s type, otherwise `true`.

!!! impl "In our tests: Clang's own macro version"
    libc++ has no `<stdckdint.h>` of its own. The example above compiles in our tests using the version in Clang's resource directory, shared by C and C++, which defines `ckd_add(R, A, B)` as a macro expanding to `__builtin_add_overflow((A), (B), (R))`.

    The behavior matches the standard: GCC's and Clang's `__builtin_*_overflow` already compute with infinite precision and write back modulo 2ᴺ. But they are macros, not function templates, so you cannot take their address, specify template arguments explicitly, or bring them in with `using`. For `bool*` and `char*` results, the built-ins give an error saying the result must point to a non-const integer type other than plain `char`, `bool`, bit-precise integers and enumerations, consistent with the *Mandates*.

## Compared with saturation arithmetic

C++26's `<numeric>` also provides saturation arithmetic: `saturating_add`, `saturating_sub`, `saturating_mul`, `saturating_div` and `saturating_cast` ([[numeric.sat]]). The two solve different problems:

| | `ckd_add` and friends | `saturating_add` and friends |
|---|---|---|
| result on overflow | the wrapped-around value, plus a `true` return | clamped to the type's minimum or maximum |
| tells you it overflowed | yes | no |
| operand types | three independent integer types, computed by mathematical value | both operands and the result have the same type |
| typical use | detect overflow, then report an error or switch to a wider integer | signal processing, pixel arithmetic and other cases where taking the extreme value on overflow is fine |
| `constexpr` | no | yes |
