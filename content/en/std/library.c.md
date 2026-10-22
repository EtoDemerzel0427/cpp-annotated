---
title: The C standard library
summary: "The C++ standard library includes the facilities of the C standard library, with signatures adjusted for type safety and semantics and preconditions (including the non-overlap requirement implied by restrict) taken from the C standard; during constant evaluation C functions follow the semantics of C Annex F, and raising any floating-point exception other than FE_INEXACT makes the call not a constant expression."
updated: 2026-10-19
---

!!! tldr
    - C library functions in C++ are adjusted for type safety: functions such as `strchr` have both a `const` and a non-`const` overload, and `abs` and the `<cmath>` functions have overloads for every arithmetic type.
    - The behavior and preconditions of these functions are those of the C standard, including the non-overlap requirement implied by `restrict` in the C signature. The requirement isn't visible in the C++ signature, but violating it is still UB.
    - Since C++26, functions such as `std::sqrt` can be called during constant evaluation. If a call raises a floating-point exception other than `FE_INEXACT` (such as `std::sqrt(-1.0)`), it isn't a constant expression.

How the C headers are organized (the difference between `<cstring>` and `<string.h>`) is covered in [[headers]]; the rules reserving names from the C library to the implementation are in [[extern.names]] and [[extern.types]]; whether C functions have C or C++ language linkage is in [[using.linkage]].

## Adjusted for type safety (¶1)

```cpp error
#include <cstring>
int main() {
  const char cs[] = "abc";
  char* p = std::strchr(cs, 'b');   // error: the strchr called here returns const char*,
                                    //        which can't initialize a char*
  return p != nullptr;
}
```

¶1 The C++ standard library also makes available the facilities of the C standard library, suitably adjusted to ensure static type safety.

The most typical adjustment is `const` correctness. C's `strchr` has the signature `char* strchr(const char* s, int c);`: you pass in a `const char*` and get back a `char*`, silently dropping the `const`. C has no overloading, so this is the only way to write it. C++'s [cstring.syn] replaces it with two overloads:

```cpp
const char* strchr(const char* s, int c);
      char* strchr(      char* s, int c);
```

`strpbrk`, `strrchr`, `strstr`, `memchr` and their counterparts in `<cwchar>` get the same treatment. So the program above compiles in C but is an error in C++.

The other kind of adjustment adds overloads for C++'s types. `abs` in `<cstdlib>` has overloads for `int`, `long` and `long long`; the math functions in `<cmath>` have overloads for every floating-point type, including extended floating-point types. To do the same in C you need different names such as `fabsf` and `fabsl`, or the type-generic macros of `<tgmath.h>`.

## Semantics taken from the C standard (¶2)

```cpp ub
#include <cstring>
int main() {
  char buf[8] = "abcdefg";
  std::memcpy(buf + 1, buf, 4);   // UB: source and destination overlap; use memmove
}
```

¶2 The descriptions of many library functions rely on the C standard library for the semantics of those functions. The signatures given in this document may differ from C, and there may be additional overloads, but unless stated otherwise the behavior and preconditions are the same as in C, including those implied by C's `restrict` qualifier.

C++ has no `restrict` keyword, so the signature of `std::memcpy` in C++ is `void* memcpy(void* s1, const void* s2, size_t n);`. In C both parameters are `restrict`, meaning the two regions of memory must not overlap. ¶2 carries this requirement into C++ as a precondition, and violating a precondition is UB ([[structure.specifications#3.4]]). The precondition can only be found in the C standard.

Running the program above with Clang 23 and `-fsanitize=address`, AddressSanitizer reports `memcpy-param-overlap`.

## C functions during constant evaluation (¶3)

```cpp
#include <cmath>
constexpr double a = std::sqrt(4.0);    // C++26: OK
constexpr double b = std::sqrt(2.0);    // C++26: OK, raises only FE_INEXACT
constexpr double c = std::sqrt(-1.0);   // error: raises FE_INVALID, not a constant expression
```

Since C++23, functions in `<cmath>` and `<cstdlib>` have gradually become `constexpr`: [[P0533R9]] in C++23 covered simpler functions such as `fabs`, `floor` and `fmod`, and [[P1383R2]] in C++26 extended this to `sin`, `sqrt`, `exp` and others. The difficulty is that math functions report errors by setting `errno` or raising floating-point exceptions, which are side effects that constant evaluation can't express.

¶3 A call to a C standard library function is a [[g:non-constant-library-call|non-constant library call]] ([[defns.nonconst.libcall]]) if it raises a floating-point exception other than `FE_INEXACT`. A non-constant library call makes the expression containing it not a core constant expression ([[expr.const]]).

The second sentence of ¶3 says that when a call to a C function is evaluated as a core constant expression, its semantics are those specified in Annex F of ISO/IEC 9899:2024, to the extent applicable to the floating-point types used by the parameters of the called function ([[basic.fundamental]]). Annex F is the part of the C standard that specifies floating-point behavior according to IEEE 754. Note 1 explains that it specifies when floating-point exceptions are raised and the behavior when NaN or infinity is passed. Note 2 gives an equivalent test: when `math_errhandling & MATH_ERRNO` is true, a call is a non-constant library call if it would set `errno`.

| Call | Floating-point exceptions raised | Result |
|---|---|---|
| `std::sqrt(4.0)` | None | A constant expression with value 2.0 |
| `std::sqrt(2.0)` | Only `FE_INEXACT` (the result is rounded) | Still a constant expression; rounding is normal for floating-point arithmetic and isn't an error |
| `std::sqrt(-1.0)` | `FE_INVALID` | A non-constant library call; ill-formed where a constant expression is required |
| `std::exp(1000.0)` | `FE_OVERFLOW` | Same as above |

The "to the extent applicable" restriction means that if an implementation's `long double` isn't an IEEE format, Annex F doesn't apply to the `long double` versions of the functions.

!!! warning "Compiler support"
    At the time of writing, Clang 23 with libc++ doesn't yet implement `constexpr` `<cmath>`, so the code block above carries no verdict. `constexpr double a = std::sqrt(4.0);` is rejected, and so is `std::fabs`, which C++23 already requires: these libc++ overloads aren't marked `constexpr`, and the `double` version comes straight from the C declaration in the macOS SDK.

## Implementation view

!!! impl "How libc++ provides the C functions"
    libc++'s `<cstring>` first includes C's `<string.h>` and then brings the global names into `std` with declarations like `using ::strlen _LIBCPP_USING_IF_EXISTS;`, which [[headers]] permits. `_LIBCPP_USING_IF_EXISTS` expands to Clang's `__attribute__((__using_if_exists__))`: when the underlying C library lacks a function, the using-declaration itself isn't an error; only an actual use of the name is.

    The two `strchr` overloads come from libc++'s own wrapper header `<string.h>`. When the underlying C library doesn't provide C++-style overloads, it defines the two overloads itself using `__builtin_strchr` and marks them `_LIBCPP_PREFERRED_OVERLOAD` so that they take precedence over the original C declaration.

    C functions are usually implemented by the system C library (glibc, Apple libc, the MSVC UCRT), which constant evaluation can't call. The compiler must compute them at compile time with built-ins such as `__builtin_sqrt`, and must also determine correctly whether a floating-point exception was raised. This is the main reason implementations of C++26's `constexpr <cmath>` lag behind.
