---
title: gcd, lcm, midpoint and saturation arithmetic
summary: "The single-value utilities in <numeric>, all about integer overflow: gcd and lcm require their results to be representable, otherwise the behavior is undefined; midpoint is guaranteed not to overflow, and integer results round toward the first argument; C++26's saturation arithmetic computes the mathematical value first and returns the nearest extreme value when it is out of range."
updated: 2026-10-19
---

!!! tldr
    - `gcd` and `lcm` accept only integer types (excluding `bool`), and the result is always non-negative; |m|, |n| and the result of `lcm` must all be representable in the common type, otherwise the behavior is undefined, as in `gcd(INT_MIN, 0)`.
    - `midpoint(a, b)` is guaranteed not to overflow; the integer version rounds toward `a` when the sum is odd, so `midpoint(1, 4) == 2` while `midpoint(4, 1) == 3`.
    - C++26's `saturating_add` and friends compute with infinite precision first and, when the result is out of range, return the nearest maximum or minimum, without integral promotion.
    - The saturating functions accept only signed and unsigned integer types; character types such as `char`, and `bool`, are not allowed.
    - `saturating_div` by zero is undefined behavior, but it is diagnosed during constant evaluation.

All three groups of functions deal with integer overflow, each in a different way: `gcd` and `lcm` leave avoiding overflow to the caller, `midpoint` guarantees no overflow internally, and saturation arithmetic clamps overflowing results to the bounds of the type.

## `gcd` and `lcm` ([numeric.ops.gcd], [numeric.ops.lcm]) {{c++17}}

```cpp
template<class M, class N>
  constexpr common_type_t<M, N> gcd(M m, N n);
template<class M, class N>
  constexpr common_type_t<M, N> lcm(M m, N n);
```

The two functions were introduced by [[P0295R0]]; the return type is the common type of the two argument types.

[numeric.ops.gcd] ¶1 *Mandates* require `M` and `N` both to be integer types other than (cv-qualified) `bool`. Passing a `double` fails to compile.

¶2 The precondition is that |m| and |n| are representable as values of `common_type_t<M, N>`. Note 1 explains the reason for this requirement: to ensure that `gcd(m, m)`, i.e. |m|, is always representable. ¶3 If both are zero it returns zero; otherwise it returns the greatest common divisor of |m| and |n|, so the result is always non-negative.

A typical precondition violation is `gcd(INT_MIN, 0)`: |INT_MIN| cannot be represented in `int`. With libc++ in our tests, `-fsanitize=undefined` reports `negation of -2147483648 cannot be represented in type 'int'`.

[numeric.ops.lcm] has the same *Mandates*. The precondition in ¶2 adds one more condition: the least common multiple itself must also be representable in the common type. So `lcm(65536, 65537)` for `int` is {{ub}}; libc++ in our tests reports no error and returns `65536`. ¶3 If either argument is zero it returns zero.

## `midpoint` ([numeric.ops.midpoint]) {{c++20}}

`midpoint` was introduced by [[P0811R3]], the same proposal that added `lerp` to `<cmath>`.

### Arithmetic version (¶1–¶3)

```cpp
template<class T> constexpr T midpoint(T a, T b) noexcept;
```

¶1 `T` must be an arithmetic type other than `bool`. ¶2 Returns half the sum of `a` and `b`; if `T` is an integer type and the sum is odd, the result is rounded toward `a`. ¶3 No overflow occurs; for floating-point types, at most one inexact operation occurs.

No overflow is useful. The naive `(a + b) / 2` overflows for `int`, which is {{ub}}; `a + (b - a) / 2` may also overflow when `a` and `b` have opposite signs. Implementations (including libc++) avoid both by using unsigned arithmetic internally.

Rounding toward `a`, rather than toward zero or downward, makes `midpoint` asymmetric: `midpoint(1, 4) == 2`, `midpoint(4, 1) == 3`, `midpoint(-3, 0) == -2`. Binary search can exploit this: `midpoint(lo, hi)` leans toward `lo`, `midpoint(hi, lo)` toward `hi`.

### Pointer version (¶4–¶7)

```cpp
template<class T> constexpr T* midpoint(T* a, T* b);
```

¶4 `T` must be an object type, ¶5 and a complete type. ¶6 The precondition is that `a` and `b` point to the i-th and j-th elements of the same array object. Note 1 says that an object that is not an array element is considered to be an array with one element, and a past-the-end pointer is considered to point to a hypothetical n-th element ([[basic.compound]]).

¶7 Returns a pointer to the element i + (j − i)/2, with the division truncating toward zero. The formula differs from the arithmetic version, but likewise leans toward `a`. The pointer version is not `noexcept`; two pointers into different arrays violate the precondition, which is {{ub}}.

```cpp run title="midpoint_gcd.cpp" ok
#include <cassert>
#include <climits>
#include <numeric>

int main() {
    assert(std::midpoint(INT_MAX, INT_MAX - 2) == INT_MAX - 1); // no overflow
    assert(std::midpoint(1, 4) == 2);       // rounds toward a
    assert(std::midpoint(4, 1) == 3);
    assert(std::midpoint(-3, 0) == -2);     // toward a, not toward zero
    int arr[5] = {};
    assert(std::midpoint(arr, arr + 5) == arr + 2);
    assert(std::midpoint(arr + 5, arr) == arr + 3); // 5 + (-5)/2 = 3
    assert(std::midpoint(1e308, 1e308) == 1e308);   // no overflow for floating point either

    assert(std::gcd(-12, 18) == 6);         // result is non-negative
    assert(std::lcm(4, -6) == 12);
    assert(std::gcd(0, 0) == 0 && std::lcm(0, 5) == 0);
    static_assert(std::gcd(12u, 18L) == 6); // common_type_t<unsigned, long>
}
```

## Saturation arithmetic ([numeric.sat]) {{c++26}}

```cpp
template<class T> constexpr T saturating_add(T x, T y) noexcept;
template<class T> constexpr T saturating_sub(T x, T y) noexcept;
template<class T> constexpr T saturating_mul(T x, T y) noexcept;
template<class T> constexpr T saturating_div(T x, T y) noexcept;
template<class R, class T> constexpr R saturating_cast(T x) noexcept;
```

These functions come from [[P0543R3]], where they were named `add_sat`, `sub_sat`, `mul_sat`, `div_sat` and `saturate_cast`; the current draft has renamed them as above. The libc++ we test with provides the new names, with `__cpp_lib_saturation_arithmetic` at `202603L`.

```cpp run title="saturating.cpp" ok
#include <climits>
#include <cstdint>
#include <numeric>

using std::int8_t, std::int16_t, std::uint8_t;
static_assert(std::saturating_add<int8_t>(100, 100) == 127);
static_assert(std::saturating_sub(0u, 1u) == 0u);  // unsigned no longer wraps
static_assert(std::saturating_mul<int16_t>(-300, 300) == INT16_MIN);
static_assert(std::saturating_div(INT_MIN, -1) == INT_MAX);
static_assert(std::saturating_cast<uint8_t>(-5) == 0);
static_assert(std::saturating_cast<int8_t>(1000) == 127);

int main() {}
```

### Compute the mathematical value, then clamp (¶1–¶7)

!!! std
    In the following descriptions, an arithmetic operation is performed as a mathematical operation with infinite range and then it is determined whether the mathematical result fits into the result type.

¶1 Each operation is first evaluated as a mathematical operation with infinite range, and then it is checked whether the result fits into the result type. ¶3, ¶5 and ¶7 specify: if it is representable, that result is returned; otherwise, whichever of the largest and smallest values of `T` is closer to the mathematical result is returned.

There is no integral promotion here. `saturating_add<int8_t>(100, 100)` gives 127, not 200 from first promoting to `int`. The two parameters have the same type, so when `x` is an `int8_t`, `saturating_add(x, 1)` has conflicting deductions and must be written `saturating_add<int8_t>(x, 1)`.

The *Constraints* in ¶2 and the other paragraphs require `T` to be a **signed or unsigned integer type** ([[basic.fundamental]]). That term excludes `bool`, `char`, `wchar_t`, `char8_t`, `char16_t` and `char32_t`: they are integral types but not signed or unsigned integer types. So `saturating_add('a', 'b')` finds no viable overload and fails to compile.

### `saturating_div` (¶8–¶11)

¶9 The precondition is `y != 0`. ¶10 The only possible overflow is `numeric_limits<T>::min() / -1` for signed types, in which case `max()` is returned.

¶11 specifies that a call violating the precondition is not a core constant expression ([[expr.const.core]]). So division by zero during constant evaluation must be diagnosed:

```cpp run title="saturating_div0.cpp" error
#include <numeric>
// error: a call that violates the precondition is not a core constant expression
constexpr int x = std::saturating_div(1, 0);
int main() {}
```

At run time, division by zero is still {{ub}}.

### `saturating_cast` ([numeric.sat.cast])

¶1 `R` and `T` must both be signed or unsigned integer types. ¶2 Returns `x` if it is representable as `R`; otherwise returns the nearest extreme value of `R`.

`static_cast` to a narrower unsigned type wraps modulo 2ⁿ; `saturating_cast` clamps to the bounds instead: `saturating_cast<uint8_t>(-5) == 0`, `saturating_cast<int8_t>(1000) == 127`. Its comparisons must handle signed/unsigned mixtures correctly; libc++ uses `cmp_less` and `cmp_greater` internally ([[utility.intcmp]]).

!!! note "Division of labor with `<stdckdint.h>`"
    C23's `ckd_add` and friends ([[numerics.c.ckdint]]) report whether overflow occurred, and also give the wrapped result. Saturation arithmetic does not report overflow; it clamps directly. The former suits cases where overflow is an error; the latter suits signal processing, pixel arithmetic and the like, where taking the boundary value on overflow is fine.

## Questions

!!! question "Question 1"
    If a binary search is written `while (lo < hi) { auto mid = std::midpoint(lo, hi); ... }`, can the rounding direction cause an infinite loop?

<details markdown="1">
<summary>Answer</summary>

When `lo < hi`, `midpoint(lo, hi)` rounds toward `lo`, so `mid` lies in `[lo, hi)`. If the updates are `lo = mid + 1` or `hi = mid`, the interval strictly shrinks every time and there is no infinite loop.

If the updates are `lo = mid` or `hi = mid - 1` (finding the last position satisfying a condition), you need a midpoint that leans toward `hi`, and should write `std::midpoint(hi, lo)`. Otherwise, when `hi == lo + 1`, `mid == lo`, `lo = mid` does not change the interval, and the loop never ends.
</details>

!!! question "Question 2"
    What are the type and value of `std::gcd(-5, 10u)`? Is there undefined behavior?

<details markdown="1">
<summary>Answer</summary>

`common_type_t<int, unsigned>` is `unsigned`. The precondition requires |−5| = 5 and 10 to be representable as `unsigned`, which they are, so there is no undefined behavior, and the result is `5u`.

The standard is talking about whether the mathematical value |m| is representable, not about first converting −5 to `unsigned` (which would give 4294967291). The implementation must take the absolute value before converting.
</details>

## Summary

| Function | Type requirements | Preconditions | On overflow |
|---|---|---|---|
| `gcd`, `lcm` | integer types, not `bool` (*Mandates*) | \|m\|, \|n\| and the result of `lcm` are representable | precondition violation, UB |
| `midpoint` (arithmetic) | arithmetic types, not `bool` (*Constraints*) | none | guaranteed not to overflow; integers round toward `a` |
| `midpoint` (pointer) | complete object types | point into the same array | n/a |
| `saturating_add`, `_sub`, `_mul` | signed or unsigned integer types | none | clamped to the nearest extreme value |
| `saturating_div` | same as above | `y != 0`, diagnosed during constant evaluation | `min / -1` returns `max` |
| `saturating_cast` | same as above | none | clamped |
