---
title: Mathematical constants
summary: "<numbers> provides 13 constants such as π, e and √2 as constexpr variable templates, giving the nearest representable value for each floating-point type; programs may specialize them for their own types, but instantiating the primary template with a non-floating-point type is ill-formed."
updated: 2026-10-19
---

!!! tldr
    - Since C++20, `std::numbers::pi` is a `constexpr double` whose value is exactly the `double` nearest to π; `pi_v<float>` is the `float` nearest to π.
    - Each constant comes in three forms: the variable template `pi_v<T>`, its partial specialization for floating-point types, and the `double` shorthand `pi`.
    - Programs may specialize `pi_v<T>` for types they define (fixed-point, intervals, multiprecision), so generic code can always write `pi_v<T>`.
    - Uses like `pi_v<int>` instantiate the primary template; the program is ill-formed and the compiler must report an error, rather than silently truncating π to 3.

## Usage

```cpp run title="numbers.cpp" ok
#include <cstdio>
#include <numbers>

int main() {
  static_assert(std::numbers::pi == std::numbers::pi_v<double>);
  constexpr float pf = std::numbers::pi_v<float>;         // the nearest float
  constexpr double area = std::numbers::pi * 2.0 * 2.0;   // usable at compile time
  std::printf("%.9g %.17g\n", pf, area);                  // 3.14159274 12.566370614359172
}
```

Before C++20, to use π you had to use POSIX's `M_PI` (not part of standard C or standard C++, and MSVC also requires defining `_USE_MATH_DEFINES` first), copy a literal by hand, or compute `4 * std::atan(1.0)` at run time. `<numbers>` ([[P0631R8]]) provides a portable, compile-time-usable replacement with guaranteed precision.

## The 13 constants ([numbers.syn])

All names are in namespace `std::numbers`. Taking π as an example, each constant has three layers of declarations:

```cpp
template<class T> constexpr T pi_v = unspecified;              // primary template
template<floating_point T> constexpr T pi_v<T> = see below;    // partial specialization for floating-point types
inline constexpr double pi = pi_v<double>;                     // double shorthand
```

| Name | Value | Name | Value |
|---|---|---|---|
| `e` | e | `ln10` | ln 10 |
| `log2e` | log₂ e | `sqrt2` | √2 |
| `log10e` | log₁₀ e | `sqrt3` | √3 |
| `pi` | π | `inv_sqrt3` | 1/√3 |
| `inv_pi` | 1/π | `egamma` | the Euler–Mascheroni constant γ |
| `inv_sqrtpi` | 1/√π | `phi` | the golden ratio (1 + √5)/2 |
| `ln2` | ln 2 | | |

The partial specialization is constrained by `floating_point<T>` ([[concepts.arithmetic]]). This concept also holds for cv-qualified floating-point types, so `pi_v<const double>` works too; extended floating-point types the implementation supports ([[basic.extended.fp]]) are automatically included as well.

## Precision guarantee ([math.constants])

¶1 The partial specializations provided by the standard library are initialized with the nearest representable values of the respective constants.

So `pi_v<float>` is the result of rounding the true π to `float` once. It is not the same as `static_cast<float>(pi_v<double>)`: rounding to `double` first and then to `float` is double rounding, which in rare cases differs from rounding once.

Compared with `4 * std::atan(1.0)`: the accuracy of `atan` is not constrained by the standard, and in libc++ in our tests it cannot be used in constant expressions. In our tests the two have the same bit pattern (both `0x1.921fb54442d18p+1`), but that is the platform math library being good, not a promise of the standard.

## Specializing for your own types (¶2)

¶2 Following the general rules of [[namespace.std]], a program may partially or explicitly specialize these variable templates, provided the specialization depends on a program-defined type.

This way, libraries for interval arithmetic, fixed-point numbers and the like can provide `pi_v<MyType>`, and generic code written once as `pi_v<T>` works for both built-in and user-defined types:

```cpp run title="numbers-specialize.cpp" ok
#include <numbers>

struct Interval { double lo, hi; };   // bracket the true value with two doubles

template<>
inline constexpr Interval std::numbers::pi_v<Interval>{
    3.141592653589793, 3.1415926535897936};

template<class T>
constexpr T area(T r) { return std::numbers::pi_v<T> * r * r; }

int main() {
  constexpr Interval p = std::numbers::pi_v<Interval>;
  static_assert(p.lo < p.hi);
  static_assert(area(1.0) == std::numbers::pi);
}
```

Writing a specialization for a type that is not program-defined, such as `int` or `double`, or for a standard library type such as `std::complex<double>`, is not permitted, and the behavior is undefined.

## The primary template cannot be instantiated (¶3)

¶3 A program that instantiates a primary template of a mathematical constant variable template is ill-formed.

The primary template's initializer is written as *unspecified* precisely because it should never be used. Evaluating `pi_v<T>` for a type that is neither a floating-point type nor user-specialized requires the compiler to give a diagnostic:

```cpp title="numbers-int.cpp" error
#include <numbers>

auto x = std::numbers::pi_v<int>;   // error: instantiates the primary template
```

libc++ in our tests implements this rule with a `static_assert` that depends on `T`, and the error message quotes this paragraph directly.

!!! lawyer "Naming without instantiating"
    ¶3 concerns only instantiation. A variable template specialization is implicitly instantiated only when its definition is needed ([[temp.inst]]), and appearing in `decltype` needs only the declaration. So `using T = decltype(std::numbers::pi_v<int>);` is well-formed, and `T` is `const int` (the variable is declared `constexpr`, hence the `const`). libc++ in our tests does not reject it, consistent with the standard. Only actually reading its value instantiates the definition and triggers the diagnostic.
