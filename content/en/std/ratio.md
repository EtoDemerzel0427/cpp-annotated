---
title: Compile-time rational arithmetic
summary: "std::ratio<N, D> represents an exact rational number as a type, with addition, subtraction, multiplication, division and comparison at compile time; if a result does not fit in intmax_t, the program is ill-formed. It is the basis of the time units in <chrono>."
updated: 2026-10-19
---

!!! tldr
    - `ratio<N, D>` is a type whose `num` and `den` are the reduced numerator and denominator, with the denominator always positive.
    - `ratio<2, 4>` and `ratio<1, 2>` are different types with the same `num` and `den`; to test equality use `ratio_equal_v` or compare `::type`.
    - The results of arithmetic aliases such as `ratio_add` are always reduced `ratio`s; if a result does not fit in `intmax_t` the program is ill-formed, and when only an intermediate value overflows the implementation should try to compute it correctly, and must still report an error if it cannot.
    - The eight SI prefixes such as `zepto` and `yocto` are declared only if `intmax_t` can represent them; with a 64-bit `intmax_t` none of them exist.

## Units as types

```cpp run title="chrono-period.cpp" ok
#include <chrono>
#include <ratio>
#include <type_traits>

using namespace std::chrono;
static_assert(std::is_same_v<milliseconds::period, std::milli>);   // milli is ratio<1, 1000>
static_assert(std::is_same_v<std::milli, std::ratio<1, 1000>>);

int main() {
  milliseconds ms = seconds(3);   // the conversion factor 1000/1 is computed at compile time
  return ms.count() == 3000 ? 0 : 1;
}
```

The `Period` of the duration type `duration<Rep, Period>` is a `ratio` giving how many seconds one tick is. With the unit in the type, conversion factors between units can be computed exactly at compile time, leaving only one multiplication or division at run time. `<ratio>` was prepared for `<chrono>` in C++11, when `constexpr` was still weak, so its design does arithmetic with types: the values live in template arguments, addition, subtraction, multiplication and division are alias templates, and comparisons are class templates. The whole header is freestanding and must be provided even in environments without an operating system.

## `ratio` and reduction [ratio.ratio]

```cpp
template<intmax_t N, intmax_t D = 1> class ratio {
public:
  static constexpr intmax_t num;
  static constexpr intmax_t den;
  using type = ratio<num, den>;
};
```

```cpp run title="ratio-basic.cpp" ok
#include <ratio>
#include <type_traits>
using namespace std;

static_assert(ratio<2, 4>::num == 1 && ratio<2, 4>::den == 2);
static_assert(ratio<1, -3>::num == -1 && ratio<1, -3>::den == 3);   // the sign goes to the numerator
static_assert(ratio<-6, -4>::num == 3 && ratio<-6, -4>::den == 2);
static_assert(!is_same_v<ratio<2, 4>, ratio<1, 2>>);                // different types
static_assert( is_same_v<ratio<2, 4>::type, ratio<1, 2>>);         // the same canonical form
static_assert( ratio_equal_v<ratio<2, 4>, ratio<1, 2>>);

int main() {}
```

¶2 `num` and `den` are the values after reduction and sign normalization. With `gcd` the greatest common divisor of `|N|` and `|D|`, `num` is `sgn(N) * sgn(D) * abs(N) / gcd` and `den` is `abs(D) / gcd`. So `den` is always positive, and the sign is carried entirely by `num`.

Reduction is reflected only in the values of `num` and `den`; the type itself does not change: `ratio<2, 4>` is still `ratio<2, 4>`. The member `type` is the reduced canonical form `ratio<1, 2>`.

¶1 If `D` is zero, or the absolute value of `N` or `D` cannot be represented in `intmax_t`, the program is ill-formed. The second condition excludes the most negative value: in two's complement the absolute value of `INTMAX_MIN` does not fit. With this restriction, reduction and sign normalization can safely operate on absolute values (Note 1).

```cpp run title="ratio-zero.cpp" error
#include <ratio>
using X = std::ratio<1, 0>;    // just an alias, not yet instantiated, no error
constexpr auto n = X::num;     // error: instantiates ratio<1, 0>, zero denominator
int main() {}
```

An alias declaration does not instantiate the class template, so the second line itself is fine. The third line uses `X::num`, `ratio<1, 0>` is instantiated, and libc++'s `static_assert` reports "ratio divide by 0".

## Arithmetic [ratio.arithmetic]

| Alias | `X` | `Y` |
|---|---|---|
| `ratio_add<R1, R2>` | `R1::num * R2::den + R2::num * R1::den` | `R1::den * R2::den` |
| `ratio_subtract<R1, R2>` | `R1::num * R2::den - R2::num * R1::den` | `R1::den * R2::den` |
| `ratio_multiply<R1, R2>` | `R1::num * R2::num` | `R1::den * R2::den` |
| `ratio_divide<R1, R2>` | `R1::num * R2::den` | `R1::den * R2::num` |

¶1 The four alias templates first compute `X` and `Y` per the table above, and the result is `ratio<U, V>`, where `U` and `V` are `ratio<X, Y>::num` and `ratio<X, Y>::den`. So the result is always in canonical form, even if the inputs are not:

```cpp run title="ratio-arith.cpp" ok
#include <ratio>
#include <type_traits>
using namespace std;

static_assert(is_same_v<ratio_add<ratio<1, 3>, ratio<1, 6>>, ratio<1, 2>>);
static_assert(is_same_v<ratio_add<ratio<2, 4>, ratio<0>>, ratio<1, 2>>);   // unreduced input
static_assert(is_same_v<ratio_multiply<milli, kilo>, ratio<1>>);

int main() {}
```

[ratio.general] ¶2 specifies that wherever a template parameter is named `R1` or `R2`, the template argument must be a specialization of `ratio`, or the program is ill-formed. A class of your own with `num` and `den` members does not qualify.

### Overflow

```cpp run title="ratio-overflow.cpp" error
#include <cstdint>
#include <ratio>

constexpr std::intmax_t M = INTMAX_MAX;
// the denominator M*(M-1) of 1/M + 1/(M-1) does not fit in intmax_t
constexpr auto v = std::ratio_add<std::ratio<1, M>, std::ratio<1, M - 1>>::num;   // error

int main() {}
```

!!! std
    If it is not possible to represent `U` or `V` with `intmax_t`, the program is ill-formed. Otherwise, an implementation should yield correct values of `U` and `V`.

¶2 The overflow rule has two layers. If the final result `U` or `V` does not fit, the program is definitely ill-formed and the compiler must report an error. If the result fits and only the intermediate `X` or `Y` does not, the implementation should compute the correct result, for example by cross-cancelling common factors before multiplying; if the implementation does not get it right, the program must still be ill-formed and may not silently get a wrong value.

```cpp run title="ratio-intermediate.cpp" ok
#include <cstdint>
#include <ratio>
#include <type_traits>
using namespace std;

constexpr intmax_t M = INTMAX_MAX;
// by definition Y = M * 2 overflows, but the result 1/2 fits; libc++ reduces first and gets it right
static_assert(is_same_v<ratio_multiply<ratio<1, M>, ratio<M, 2>>, ratio<1, 2>>);

int main() {}
```

¶3 The standard's example includes this case too, with a comment noting that it may be ill-formed on some implementations. For the overflowing example above, libc++ reports "overflow in __ll_add" in its internal checking helper template.

## Comparison [ratio.comparison]

The six comparison templates all derive from `bool_constant`, with corresponding `_v` variable templates:

- `ratio_equal`: `R1::num == R2::num && R1::den == R2::den`. Both sides are already in canonical form, so comparing term by term is numeric equality;
- `ratio_less`: ¶1 true if `R1::num × R2::den < R2::num × R1::den`;
- `ratio_not_equal`, `ratio_less_equal`, `ratio_greater` and `ratio_greater_equal` are all defined in terms of the first two.

¶1 For `ratio_less`, implementations may use other algorithms to avoid overflow; if it still overflows, the program is ill-formed. libc++ compares step by step via continued fractions, so `ratio_less_v<ratio<M - 1, M>, ratio<M, M - 1>>` (with `M = INTMAX_MAX`) correctly yields `true`, even though multiplying directly by the definition would have overflowed long before.

## SI prefixes [ratio.si]

`<ratio>` provides aliases for all 24 decimal SI prefixes, from `quecto` (10⁻³⁰) to `quetta` (10³⁰), including `ronto`, `quecto`, `ronna` and `quetta`, added to the SI in 2022.

¶1 Eight of them are special: `quecto`, `ronto`, `yocto`, `zepto`, `zetta`, `yotta`, `ronna` and `quetta` are declared only if both constants used in their definitions can be represented in `intmax_t`, and are not declared otherwise. The maximum value of a 64-bit `intmax_t` is about 9.2 × 10¹⁸, so 10²¹ and above do not fit, and these eight aliases do not exist on common platforms:

```cpp run title="ratio-si.cpp" error
#include <ratio>

std::exa*    e;     // OK: 10^18 fits
std::zepto*  z;     // error: no type named 'zepto' in namespace 'std'
std::quecto* q;     // error

int main() {}
```

Portable code cannot assume these names exist.

## Questions

!!! question "Question"
    What type is `std::ratio_add<std::ratio<1, 2>, std::ratio<1, 2>>`? Is it `std::ratio<4, 4>`?

<details markdown="1">
<summary>Answer</summary>

`X = 1*2 + 1*2 = 4` and `Y = 2*2 = 4`, so the result is `ratio<ratio<4, 4>::num, ratio<4, 4>::den>`, i.e. `ratio<1, 1>`, which is `ratio<1>`. It is not `ratio<4, 4>`: the results of the arithmetic aliases are always in canonical form ([ratio.arithmetic] paragraph 1), while `ratio<4, 4>` is a different type whose `::type` merely happens to be `ratio<1>` too.
</details>
