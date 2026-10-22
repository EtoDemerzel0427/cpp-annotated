---
title: Predefined macro names
summary: "The macros an implementation must predefine: __cplusplus, all the language feature-test macros, __FILE__ and __LINE__, __DATE__ and __TIME__, __STDC_HOSTED__ and more; conditionally-defined macros; and the rule that programs must not redefine them."
updated: 2026-10-19
---

!!! tldr
    - `__cplusplus` indicates the language version, with values like `202302L`. Compare with `>=`, not `==`.
    - The `__cpp_xxx` macros of Table 22 report language features one by one, with values giving the year and month of the feature's latest revision; detecting a specific feature is more reliable than inferring from the version number. The library feature macros `__cpp_lib_xxx` are in `<version>`.
    - `__FILE__` and `__LINE__` report the presumed location, are affected by `#line`, and are the only two predefined macros that change within a translation unit.
    - A program that `#define`s or `#undef`s any macro listed in this subclause, or `defined`, is ill-formed; the implementation's own predefined macros must use reserved names.

**Predefined macros** are macros the implementation has already defined before translation begins. They are the standard channel through which a program learns about the compilation environment at preprocessing time: which edition of the standard is in use, whether the implementation is hosted, which language features are supported, how much alignment `new` guarantees.

## __cplusplus: the language version (¶1.1)

```cpp run title="cplusplus.cpp" ok
#if __cplusplus >= 202302L
#  define CXX_VER 23
#elif __cplusplus >= 202002L
#  define CXX_VER 20
#else
#  define CXX_VER 17
#endif
static_assert(CXX_VER >= 17);
int main() {}
```

¶1.1 The current draft specifies `__cplusplus` as the integer literal `202603L`. Note 1 explains that future revisions will replace it with a greater value. The values over the years:

| Standard | `__cplusplus` |
|---|---|
| C++98 / C++03 | `199711L` |
| C++11 | `201103L` |
| C++14 | `201402L` |
| C++17 | `201703L` |
| C++20 | `202002L` |
| C++23 | `202302L` |
| Current working draft | `202603L` |

The value has the form `yyyymmL`, taken from the year and month the standard or draft was finalized. Before the next standard is officially published, compilers use a provisional value: in our tests Clang 23 defines it as `202400L` under `-std=c++2c`.

!!! pitfall "Compare with >=, not =="
    `#if __cplusplus == 201703L` no longer holds on a C++20 compiler; write `>=` instead. Better still, detect specific features with the feature-test macros below, since an implementation may support only some of a standard's features.

!!! impl "MSVC's __cplusplus"
    For compatibility with old code, MSVC by default defines `__cplusplus` as `199711L` regardless of which edition `/std:` selects, reporting the real value only with `/Zc:__cplusplus`. It separately provides `_MSVC_LANG` for the actual language version. This default behavior doesn't conform to the standard.

## Feature-test macros (¶1.2, Table 22)

```cpp run title="feature-test.cpp" ok
#if __cpp_if_consteval >= 202106L
constexpr int f(int x) {
  if consteval { return x; } else { return -x; }
}
#else
constexpr int f(int x) { return x; }
#endif
static_assert(f(1) == 1);
int main() {}
```

¶1.2 The macros listed in Table 22 must be defined as the corresponding integer literals in the table. Note 2 explains that future revisions may replace these values with greater ones.

These are called **feature-test macros**. Each macro's value is the year and month in which the proposal introducing or most recently changing the feature was adopted, so the same macro grows as the feature is extended. For example, `__cpp_constexpr` grew from `200704L` in C++11 all the way to the current `202406L`, updated each time the restrictions on `constexpr` were relaxed. Usage is always a `>=` comparison with some value.

In `#if`, undefined identifiers are replaced by 0 ([[cpp.cond#10]]). So on implementations that don't support `if consteval`, the `#if` above also correctly evaluates to false, without having to write `defined(...)` first.

The standard library's feature-test macros `__cpp_lib_xxx` aren't in this subclause; they are defined by library headers and, since C++20, collected in `<version>` ([[version.syn]]). Include `<version>` or the relevant header before testing library features; otherwise the macros aren't defined and are treated as 0 in `#if`.

Table 22 has 78 macros in all. The table below lists those whose values in Clang 23 (`-std=c++2c`) in our tests differ from the draft:

| Macro | Draft value | Clang 23 |
|---|---|---|
| `__cpp_concepts` | `202606L` | `202002` |
| `__cpp_consteval` | `202606L` | `202211L` |
| `__cpp_constexpr_exceptions` | `202411L` | not defined |
| `__cpp_constexpr_virtual_inheritance` | `202506L` | not defined |
| `__cpp_contracts` | `202606L` | not defined |
| `__cpp_deduction_guides` | `202207L` | `201703L` |
| `__cpp_designated_initializers` | `202606L` | `201707L` |
| `__cpp_expansion_statements` | `202506L` | not defined |
| `__cpp_impl_coroutine` | `202606L` | `201902L` |
| `__cpp_impl_reflection` | `202603L` | not defined |
| `__cpp_modules` | `201907L` | `1` |
| `__cpp_nontype_template_args` | `201911L` | `201411L` |
| `__cpp_pack_indexing` | `202606L` | `202311L` |
| `__cpp_pp_embed` | `202606L` | not defined |
| `__cpp_template_parameters` | `202502L` | not defined |
| `__cpp_trivial_union` | `202603L` | not defined |

Undefined macros correspond to features not yet implemented, such as reflection, contracts and expansion statements. `__cpp_pp_embed` is an exception: Clang already supports `#embed`, but treats it as an extension in C++ and doesn't support the standard `offset` parameter ([[cpp.embed]]). Smaller values mean only an early version of the feature is implemented; for example, `__cpp_deduction_guides` stopping at the C++17 value shows that C++20's extensions, such as class template argument deduction for alias templates, aren't fully implemented. The value of `__cpp_concepts` lacks the `L` suffix, and the value `1` of `__cpp_modules` isn't a year and month at all, indicating that Clang considers its module support incomplete.

Values like `202603L` and `202606L` in the draft mean those features were revised again after C++26 was finalized.

<details markdown="1"><summary>All 78 macros of Table 22</summary>

| Macro | Draft value | Clang 23 |
|---|---|---|
| `__cpp_aggregate_bases` | `201603L` | `201603L` |
| `__cpp_aggregate_nsdmi` | `201304L` | `201304L` |
| `__cpp_aggregate_paren_init` | `201902L` | `201902L` |
| `__cpp_alias_templates` | `200704L` | `200704L` |
| `__cpp_aligned_new` | `201606L` | `201606L` |
| `__cpp_attributes` | `200809L` | `200809L` |
| `__cpp_auto_cast` | `202110L` | `202110L` |
| `__cpp_binary_literals` | `201304L` | `201304L` |
| `__cpp_capture_star_this` | `201603L` | `201603L` |
| `__cpp_char8_t` | `202207L` | `202207L` |
| `__cpp_concepts` | `202606L` | `202002` |
| `__cpp_conditional_explicit` | `201806L` | `201806L` |
| `__cpp_consteval` | `202606L` | `202211L` |
| `__cpp_constexpr` | `202406L` | `202406L` |
| `__cpp_constexpr_dynamic_alloc` | `201907L` | `201907L` |
| `__cpp_constexpr_exceptions` | `202411L` | not defined |
| `__cpp_constexpr_in_decltype` | `201711L` | `201711L` |
| `__cpp_constexpr_virtual_inheritance` | `202506L` | not defined |
| `__cpp_constinit` | `201907L` | `201907L` |
| `__cpp_contracts` | `202606L` | not defined |
| `__cpp_decltype` | `200707L` | `200707L` |
| `__cpp_decltype_auto` | `201304L` | `201304L` |
| `__cpp_deduction_guides` | `202207L` | `201703L` |
| `__cpp_delegating_constructors` | `200604L` | `200604L` |
| `__cpp_deleted_function` | `202403L` | `202403L` |
| `__cpp_designated_initializers` | `202606L` | `201707L` |
| `__cpp_enumerator_attributes` | `201411L` | `201411L` |
| `__cpp_expansion_statements` | `202506L` | not defined |
| `__cpp_explicit_this_parameter` | `202110L` | `202110L` |
| `__cpp_fold_expressions` | `201603L` | `201603L` |
| `__cpp_generic_lambdas` | `201707L` | `201707L` |
| `__cpp_guaranteed_copy_elision` | `201606L` | `201606L` |
| `__cpp_hex_float` | `201603L` | `201603L` |
| `__cpp_if_consteval` | `202106L` | `202106L` |
| `__cpp_if_constexpr` | `201606L` | `201606L` |
| `__cpp_impl_coroutine` | `202606L` | `201902L` |
| `__cpp_impl_destroying_delete` | `201806L` | `201806L` |
| `__cpp_impl_reflection` | `202603L` | not defined |
| `__cpp_impl_three_way_comparison` | `201907L` | `201907L` |
| `__cpp_implicit_move` | `202207L` | `202207L` |
| `__cpp_inheriting_constructors` | `201511L` | `201511L` |
| `__cpp_init_captures` | `201803L` | `201803L` |
| `__cpp_initializer_lists` | `200806L` | `200806L` |
| `__cpp_inline_variables` | `201606L` | `201606L` |
| `__cpp_lambdas` | `200907L` | `200907L` |
| `__cpp_modules` | `201907L` | `1` |
| `__cpp_multidimensional_subscript` | `202211L` | `202211L` |
| `__cpp_named_character_escapes` | `202606L` | `202606L` |
| `__cpp_namespace_attributes` | `201411L` | `201411L` |
| `__cpp_noexcept_function_type` | `201510L` | `201510L` |
| `__cpp_nontype_template_args` | `201911L` | `201411L` |
| `__cpp_nontype_template_parameter_auto` | `201606L` | `201606L` |
| `__cpp_nsdmi` | `200809L` | `200809L` |
| `__cpp_pack_indexing` | `202606L` | `202311L` |
| `__cpp_placeholder_variables` | `202306L` | `202306L` |
| `__cpp_pp_embed` | `202606L` | not defined |
| `__cpp_range_based_for` | `202211L` | `202211L` |
| `__cpp_raw_strings` | `200710L` | `200710L` |
| `__cpp_ref_qualifiers` | `200710L` | `200710L` |
| `__cpp_return_type_deduction` | `201304L` | `201304L` |
| `__cpp_rvalue_references` | `200610L` | `200610L` |
| `__cpp_size_t_suffix` | `202011L` | `202011L` |
| `__cpp_sized_deallocation` | `201309L` | `201309L` |
| `__cpp_static_assert` | `202306L` | `202306L` |
| `__cpp_static_call_operator` | `202207L` | `202207L` |
| `__cpp_structured_bindings` | `202411L` | `202411L` |
| `__cpp_template_parameters` | `202502L` | not defined |
| `__cpp_template_template_args` | `201611L` | `201611L` |
| `__cpp_threadsafe_static_init` | `200806L` | `200806L` |
| `__cpp_trivial_union` | `202603L` | not defined |
| `__cpp_unicode_characters` | `200704L` | `200704L` |
| `__cpp_unicode_literals` | `200710L` | `200710L` |
| `__cpp_user_defined_literals` | `200809L` | `200809L` |
| `__cpp_using_enum` | `201907L` | `201907L` |
| `__cpp_variable_templates` | `201304L` | `201304L` |
| `__cpp_variadic_friend` | `202403L` | `202403L` |
| `__cpp_variadic_templates` | `200704L` | `200704L` |
| `__cpp_variadic_using` | `201611L` | `201611L` |
</details>

## __FILE__ and __LINE__: the current location (¶1.4, ¶1.5)

```cpp run title="unique-name.cpp" ok
#define CAT_(a, b) a##b
#define CAT(a, b) CAT_(a, b)
#define UNIQUE(name) CAT(name, __LINE__)
int UNIQUE(tmp) = 1;   // int tmp4 = 1;
int UNIQUE(tmp) = 2;   // int tmp5 = 2;
int main() { return tmp4 + tmp5 - 3; }
```

¶1.4 `__FILE__` is a string literal representing the **presumed name** of the current source file. ¶1.5 `__LINE__` is the integer literal `0` or a decimal integer literal representing the **presumed line number** of the current source line within the current source file. Both can be changed by `#line` (notes 3 and 4, [[cpp.line]]).

`__LINE__` contains no digit separators and no integer suffix. So it can safely be pasted into an identifier with `##`, like `tmp4` above, and can also be stringized. `CAT` must be written in two layers: operands of `##` aren't expanded first ([[cpp.concat#2]]), so a single layer would paste together `tmp__LINE__`.

¶3 Apart from `__FILE__` and `__LINE__`, the values of predefined macros remain constant throughout the translation unit. So even if translation spans midnight, `__DATE__` doesn't change.

When a function needs its caller's location, since C++20 `std::source_location::current()` ([[support.srcloc]]) is preferred. As a default argument it's evaluated at the call site, whereas `__LINE__` can only give the line where the macro is expanded.

## __DATE__ and __TIME__: the translation time (¶1.3, ¶1.9)

¶1.3 `__DATE__` is the date of translation of the source file, a string literal of the form `"Mmm dd yyyy"`. The month names are the same as those generated by `asctime`; when the day is less than 10, the first character of `dd` is a space, as in `"Jan  1 1970"`.

¶1.9 `__TIME__` is the time of translation, of the form `"hh:mm:ss"`. If the date or time isn't available, the implementation must supply an implementation-defined valid value.

!!! impl "Reproducible builds"
    These two macros make the output of every compilation different, breaking reproducible builds. GCC and Clang both support the environment variable `SOURCE_DATE_EPOCH`; when set, the two macros take the values corresponding to that timestamp. In our tests Clang 23 under `SOURCE_DATE_EPOCH=0` gives `"Jan  1 1970"` and `"00:00:00"`. `-Wdate-time` warns where they are used.

## Macros describing the implementation (¶1.6–¶1.8)

¶1.7 `__STDC_HOSTED__` is `1` in a hosted implementation and `0` in a freestanding one. A freestanding implementation can run without an operating system and is only required to provide a subset of the standard library ([[intro.compliance]]). In our tests Clang 23 defaults to 1 and gives 0 with `-ffreestanding`.

```cpp
#if __STDC_HOSTED__
#  include <iostream>   // a freestanding implementation isn't guaranteed to provide <iostream>
#endif
```

¶1.8 `__STDCPP_DEFAULT_NEW_ALIGNMENT__` is an integer literal of type `std::size_t` whose value is the alignment guaranteed by `operator new(std::size_t)` and `operator new[](std::size_t)`. Note 6 adds that for types with larger alignment requirements, `new` expressions call overloads such as `operator new(std::size_t, std::align_val_t)` ([[expr.new]]).

This macro was introduced with C++17's aligned `new` ([[P0035R4]]), and it gives the dividing line for over-alignment: for types whose alignment requirement exceeds this value, `new` goes through the `align_val_t` overloads. In our tests Clang 23 (arm64 macOS) defines it as `16UL`; the `UL` suffix makes its type `unsigned long`, which is `std::size_t` on this platform.

```cpp run title="new-align.cpp" ok
#include <cstddef>
#include <new>
struct alignas(64) CacheLine { char data[64]; };
int main() {
  // 64 is greater than __STDCPP_DEFAULT_NEW_ALIGNMENT__ (usually 16),
  // so new calls operator new(size_t, align_val_t)
  CacheLine* p = new CacheLine;
  bool ok = reinterpret_cast<std::size_t>(p) % 64 == 0;
  delete p;
  return ok ? 0 : 1;
}
```

¶1.6 {{c++26}} `__STDC_EMBED_NOT_FOUND__`, `__STDC_EMBED_FOUND__` and `__STDC_EMBED_EMPTY__` are `0`, `1` and `2` respectively. Note 5 explains that they are the possible values of a `__has_embed` expression ([[cpp.cond]]).

## Conditionally-defined macros (¶2)

¶2 The following macros are defined by the implementation depending on circumstances:

| Macro | Condition and value |
|---|---|
| `__STDCPP_FLOAT16_T__` | defined as 1 if and only if ISO/IEC 60559 binary16 is supported as an extended floating-point type, corresponding to `std::float16_t` |
| `__STDCPP_FLOAT32_T__` | likewise, binary32, corresponding to `std::float32_t` |
| `__STDCPP_FLOAT64_T__` | likewise, binary64, corresponding to `std::float64_t` |
| `__STDCPP_FLOAT128_T__` | likewise, binary128, corresponding to `std::float128_t` |
| `__STDCPP_BFLOAT16_T__` | defined as 1 if and only if an extended floating-point type with the properties of `std::bfloat16_t` is supported |
| `__STDC__` | whether it's defined, and its value, are implementation-defined |
| `__STDC_MB_MIGHT_NEQ_WC__` | defined as 1 to indicate that a member of the basic character set might have a code value in the `wchar_t` encoding that differs from its value as an ordinary character literal |
| `__STDC_VERSION__` | whether it's defined, and its value, are implementation-defined |
| `__STDC_ISO_10646__` | of the form `yyyymmL`; whether it's defined, and its value, are implementation-defined |
| `__STDCPP_THREADS__` | defined as 1 if and only if a program can have more than one thread of execution |

The five extended floating-point macros come from C++23's [[P1467R9]] (see [[basic.extended.fp]]). The condition is "if and only if", so a defined macro guarantees the compiler supports the corresponding type.

```cpp run title="float16.cpp" ok
#if defined(__STDCPP_FLOAT16_T__) && __has_include(<stdfloat>)
#  include <stdfloat>
using half = std::float16_t;
#else
using half = float;   // fallback
#endif
int main() { half h = 1; return static_cast<int>(h) - 1; }
```

The macro is predefined by the compiler, while the alias `std::float16_t` is provided by the library header `<stdfloat>`; the two may be out of sync, so both are checked here. In our tests Clang 23 defines none of these five macros, and the accompanying libc++ has no `<stdfloat>`.

In C, `__STDC__` indicates that the implementation conforms to the C standard; in C++, whether it exists and what its value is are implementation-defined. GCC and Clang define it as 1; MSVC doesn't define it by default. To distinguish C from C++, check `__cplusplus`.

In our tests with Clang 23 (arm64 macOS), `__STDCPP_THREADS__` and `__STDC__` are both 1, and `__STDC_VERSION__` and `__STDC_ISO_10646__` aren't defined. On Linux, `__STDC_ISO_10646__` is usually defined by `<stdc-predef.h>`, which glibc preincludes automatically.

## Must not be redefined (¶4)

```cpp title="redefine-predefined.cpp" error
#define __cplusplus 201103L    // error: a predefined macro of this subclause
#undef __FILE__                // error
#define __cpp_concepts 1       // error: feature-test macros belong to this subclause too
#define defined                // error: defined
```

¶4 If any predefined macro name listed in this subclause, or the identifier `defined`, appears in a `#define` or `#undef`, the program is ill-formed. In C++23 and earlier this was undefined behavior. In our tests Clang 23 gives only a `-Wbuiltin-macro-redefined` warning for the first three lines and an error for `#define defined`.

The second sentence of ¶4 requires the implementation's other predefined macros to begin with an underscore followed by an uppercase letter or with two underscores, that is, to fall within reserved identifiers ([[lex.name]]), so they can't clash with user names. GCC's predefined `linux` and `unix` in GNU modes don't conform to this, which is why GCC doesn't define them in strict modes such as `-std=c++20`.

## History

!!! history
    - C++98 had `__cplusplus` (`199711L`), `__DATE__`, `__FILE__`, `__LINE__` and `__TIME__`, with `__STDC__` implementation-defined. Early GCC long defined `__cplusplus` as 1, so version detection in old code isn't reliable.
    - C++11 added `__STDC_HOSTED__`, `__STDCPP_THREADS__`, and, in step with C99, `__STDC_MB_MIGHT_NEQ_WC__`, `__STDC_VERSION__` and `__STDC_ISO_10646__`.
    - C++17 added `__STDCPP_DEFAULT_NEW_ALIGNMENT__` ([[P0035R4]]).
    - C++20 moved the feature-test macros from the committee's non-normative document SD-6 into the normative text ([[P0941R2]]).
    - C++23 added the five extended floating-point macros ([[P1467R9]]).
    - C++26 added `__STDC_EMBED_*__` and `__cpp_pp_embed` ([[P1967R14]]).
    - Wording after C++23 changed redefining predefined macros from undefined behavior to ill-formed.

## Questions

!!! question "Question 1"
    Why are the values of feature-test macros years and months rather than just 0 and 1? Give an example where checking only `defined(__cpp_xxx)` goes wrong.

<details markdown="1">
<summary>Answer</summary>

Because the same feature gets extended several times, and year-month values let code tell which version it is. Take `__cpp_constexpr`: in C++11 it's `200704L`, when a `constexpr` function could only contain a single `return` statement; C++14 relaxed this, `201304L`; C++20 allows `constexpr` virtual functions, with a value of at least `201907L`.

If code depends on `constexpr` virtual functions and checks only `defined(__cpp_constexpr)`, the check is true even on a compiler that supports only C++11, and compilation fails. Write `#if __cpp_constexpr >= 201907L` instead.
</details>

!!! question "Question 2"
    `__LINE__` is specified as a decimal integer literal without digit separators or an integer suffix. If it could expand to `1'234` or `1234u`, which common idioms would break?

<details markdown="1">
<summary>Answer</summary>

The most direct is `##` pasting. `CAT(var_, __LINE__)` should give the identifier `var_1234`, while `var_1'234` can't be pasted into a valid preprocessing token at all.

Another is `#line __LINE__`: after macro replacement it must be a digit sequence ([[cpp.line#3]]), and neither `1'234` nor `1234u` matches. Fixing the form is what makes these idioms portable.
</details>
