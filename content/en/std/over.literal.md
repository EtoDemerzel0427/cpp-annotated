---
title: User-defined literals
summary: 'How literal operators are declared: the operator""_x syntax, reserved suffixes, namespace scope only, the thirteen permitted parameter lists, the numeric and string templates; beyond that they are ordinary functions.'
updated: 2026-10-19
---

!!! tldr
    - A literal operator is written `operator""_km`. The form with a space between `""` and the suffix is deprecated and can run into reserved identifiers.
    - User suffixes must begin with an underscore; suffixes not beginning with an underscore are reserved for the standard library, those containing `__` for the implementation, and using them is IFNDR.
    - Literal operators can be declared only at namespace scope. They can be friends, but a hidden friend defined only inside a class is never found by a literal.
    - The parameter list of a non-template version must be one of a fixed set of 13: integers use `unsigned long long`, floating-point uses `long double`, strings use a pointer plus a length.
    - There are only two template forms: `template<char...>` receives the spelling of a numeric literal, and since C++20 a constant template parameter of class type receives the whole string.

[[lex.ext]] covers the use side: how user-defined literals such as `12_km` and `"abc"_s` become calls such as `operator""_km(12ULL)`. This page covers the declaration side: what kind of function can be called `operator""_km`, and what parameters it can have.

```cpp run ok
#include <chrono>
#include <string>
namespace units {
  struct Km { long double v; };
  constexpr Km operator""_km(long double d) { return {d}; }
  constexpr Km operator""_km(unsigned long long n) { return {static_cast<long double>(n)}; }
}
int main() {
  using namespace std::literals;   // brings in the standard library's s, ms, etc.
  using namespace units;           // brings in _km
  auto s = "abc"s;
  auto d = 10ms;
  auto k = 1.5_km;                 // operator""_km(1.5L)
  auto n = 2_km;                   // operator""_km(2ULL)
  return (s.size() == 3 && d.count() == 10 && k.v == 1.5L && n.v == 2.0L) ? 0 : 1;
}
```

## Two ways to write the name (¶1)

A *literal-operator-id* has two forms:

```text
literal-operator-id:
    operator unevaluated-string identifier      // operator "" _km, deprecated
    operator user-defined-string-literal        // operator ""_km
```

The two differ only in whether there's whitespace between `""` and the suffix, but lexically they are completely different. The first is two tokens: an empty string `""` plus the identifier `_km`. The second is one token, the user-defined string literal `""_km` ([[lex.ext]]), where `_km` is its *ud-suffix*, not a separate identifier. Whitespace between `operator` and `""` doesn't matter.

¶1 specifies: the string must be empty; the second form can't have an encoding prefix (`u8""_x` won't do). The *ud-suffix* of the second form or the identifier of the first form is called the **[[g:literal-suffix-identifier|literal suffix identifier]]**. The first form is deprecated ([[depr.lit]]).

### Why the form with a space was deprecated

In the first form the suffix is a separate identifier, so it is subject to the reserved-identifier rules of [[lex.name]]: identifiers beginning with an underscore followed by an uppercase letter, such as `_Bq`, are reserved to the implementation everywhere.

```cpp
double operator""_Bq(long double);    // OK: _Bq is just a ud-suffix
double operator"" _Bq(long double);   // IFNDR: uses the reserved identifier _Bq, and this form is deprecated
```

The same suffix, one space apart: one is valid, the other IFNDR (ill-formed, no diagnostic required). C++23 deprecated the form with a space through [[CWG2521]]. So don't put a space between `""` and the suffix. Clang 23 gives only a `-Wdeprecated-literal-operator` warning for the second line and doesn't mention the reserved identifier.

### Reserved suffixes

The end of ¶1 says that some suffixes are reserved for future standardization ([[usrlit.suffix]]), and a declaration using them is IFNDR. There are two rules: suffixes that don't begin with an underscore are reserved for the standard library, which is why the standard library's `s`, `sv`, `ms` and `i` have no underscore and never clash with user code; suffixes containing a double underscore are reserved for the implementation.

```cpp
float operator""E(const char*);           // IFNDR: doesn't begin with an underscore
int   operator""__x(unsigned long long);  // IFNDR: contains __
```

The standard requires no diagnostic; Clang 23 warns `no literal will invoke this operator` for both. For `""E` it also issues a diagnostic that is an error by default, `-Wreserved-user-defined-literal`: before C++11, `"..."E` could be a string followed by a macro name, so Clang requires a space between the string and the identifier.

## Namespace scope only (¶2)

¶2 A declaration whose declarator-id is a *literal-operator-id* must declare a function or function template that belongs to a namespace (it may be a friend), or an explicit instantiation or explicit specialization of a function template. A function so declared is a **[[g:literal-operator|literal operator]]**; a function template is a **[[g:literal-operator-template|literal operator template]]**.

A literal `12_km` has no object on which to call a member function, so a literal operator can't be a class member:

```cpp error
struct S {
  int operator""_x(unsigned long long);   // error: must be at namespace scope
};
```

It can be a friend, but user-defined literals use only unqualified lookup ([[lex.ext#2]]), with no argument-dependent lookup (ADL), and the literal itself has no class-type argument for ADL to use anyway. So a hidden friend defined only inside a class is never found:

```cpp error
struct S {
  friend int operator""_x(unsigned long long) { return 1; }   // a valid declaration, but a hidden friend
};
int a = 2_x;   // error: unqualified lookup can't find operator""_x
```

The convention is to put literal operators in a dedicated namespace that users bring in with `using namespace`, like `units` at the top of this page and the standard library's `std::literals`.

## Permitted parameter lists (¶3–¶4)

¶3 The parameter list of a literal operator must be equivalent to one of the following 13:

| Parameter list | Used for | Call form |
|---|---|---|
| `const char*` | raw spelling of integer and floating-point literals | `operator""X("123")` |
| `unsigned long long int` | integer literals | `operator""X(123ULL)` |
| `long double` | floating-point literals | `operator""X(1.5L)` |
| `char`, `wchar_t`, `char8_t`, `char16_t`, `char32_t` | character literals | `operator""X('a')` |
| `const char*, std::size_t`, and the corresponding versions for `wchar_t`, `char8_t`, `char16_t`, `char32_t` | string literals | `operator""X("abc", 3)` |

If any parameter has a default argument, the program is ill-formed.

Equivalent means the spelling can differ as long as the types are the same: the top-level `const` of `const char* const` is adjusted away, and `std::size_t` can be written as its underlying type. But the types must be exactly these. The integer version can't be `int` and the floating-point version can't be `double`: the operator always receives the argument in the largest type that can hold any value, and range checking is the operator's own job.

```cpp
#include <cstddef>
int operator""_a(int);                      // error: the integer version must be unsigned long long
double operator""_miles(double);            // error: the floating-point version must be long double
int operator""_d(unsigned long long = 0);   // error: can't have a default argument
int operator""_y(const char*, std::size_t, int);   // error: not in the list
```

Default arguments are forbidden because [[lex.ext]] chooses how to call based entirely on the shape of the parameter list. `(const char*, std::size_t = 0)` could serve as both the raw version and the string version, which would defeat the classification.

¶4 A literal operator with a single `const char*` parameter is called a **[[g:raw-literal-operator|raw literal operator]]**. It receives the uninterpreted spelling of an integer or floating-point literal, so it can handle literals beyond the range of any built-in type:

```cpp run ok
constexpr unsigned long long operator""_ndigits(const char* s) {
  unsigned long long n = 0;
  for (; *s; ++s) if (*s != '\'') ++n;
  return n;
}
static_assert(1234567890123456789012345_ndigits == 25);   // too big for unsigned long long; the raw spelling is unaffected
int main() {}
```

Raw literal operators aren't used for string literals; `"abc"_x` needs a `(const char*, std::size_t)` version or a string literal operator template.

## Two kinds of template (¶5)

¶5 There are only two kinds of literal operator template, and both must have an empty function parameter list, with all information passed through template arguments:

- **[[g:numeric-literal-operator-template|Numeric literal operator template]]**: the template parameter list has a single constant template parameter pack whose element type is `char`, that is, `template<char...>`. `101_bin` calls `operator""_bin<'1', '0', '1'>()`.
- **[[g:string-literal-operator-template|String literal operator template]]** {{c++20}}: the template parameter list has a single constant template parameter of class type. When a string literal can be a template argument for that parameter, `"..."_x` calls `operator""_x<"...">()`.

```cpp run ok
#include <cstddef>
template<char... Cs>
constexpr int operator""_bin() {   // numeric literal operator template
  int v = 0;
  ((v = v * 2 + (Cs - '0')), ...);
  return v;
}
static_assert(101_bin == 5);

template<std::size_t N>
struct FixedString {
  char s[N];
  constexpr FixedString(const char (&a)[N]) {
    for (std::size_t i = 0; i < N; ++i) s[i] = a[i];
  }
};
template<FixedString F>
constexpr std::size_t operator""_len() { return sizeof(F.s) - 1; }   // string literal operator template
static_assert("hello"_len == 5);
int main() {}
```

The string template makes the contents of the string a compile-time constant, so format strings, units and so on can be parsed at compile time. It relies on C++20 allowing class types as constant template parameters ([[P0732R2]], [[temp.arg.nontype]]). Before that, GCC and Clang provided an extension of the form `template<class T, T...>`; the standard didn't adopt it, and Clang still issues a `-Wgnu-string-literal-operator-template` warning for it.

```cpp
template<char...> int operator""_j(const char*);   // error: a template's function parameter list must be empty
template<int N> int operator""_n();                // error: neither char... nor a class-type parameter
```

A numeric template can't be used for string literals, and vice versa:

```cpp error
template<char...> int operator""_t();
int a = "abc"_t;   // error: a string literal needs a (const char*, size_t) version or a string template
```

## Remaining rules (¶6–¶8)

¶6 Literal operators and literal operator templates can't have C language linkage ([[dcl.link]]); C has no such names. `extern "C" void operator""_m(long double);` is ill-formed.

Note 1 under ¶7 points out that apart from the restrictions above, literal operators are ordinary namespace-scope functions and function templates: they are looked up like ordinary functions, follow the same overload resolution rules, can be `inline`, `constexpr` or `consteval`, can have internal, module or external linkage, can be called explicitly, and can have their address taken.

```cpp run ok
namespace {
  constexpr int operator""_k(unsigned long long v) { return int(v) * 1000; }   // internal linkage
}
int main() {
  static_assert(3_k == 3000);
  auto p = &operator""_k;    // taking the address: int(*)(unsigned long long)
  int v = operator""_k(4);   // explicit call: 4 is an int, converted to unsigned long long by the ordinary rules
  return p(1) + v - 5000;
}
```

An explicit call doesn't go through the rewriting of [[lex.ext]]; `operator""_k(4)` is just an ordinary function call.

Literal operators are often written `consteval`, so that invalid literals are rejected at compile time:

```cpp run ok
consteval unsigned char operator""_u8(unsigned long long v) {
  if (v > 255) throw "out of range";   // throwing during constant evaluation: the call isn't a constant expression
  return static_cast<unsigned char>(v);
}
int main() {
  auto x = 200_u8;
  // auto y = 300_u8;   // error: not a constant expression
  return x == 200 ? 0 : 1;
}
```

The example in ¶8 sums up the rules above:

| Declaration | Verdict | Reason |
|---|---|---|
| `void operator ""_km(long double);` | OK | whitespace after `operator` doesn't matter |
| `string operator "" _i18n(const char*, std::size_t);` | OK, deprecated | the form with a space |
| `template <char...> double operator ""_π();` | OK | the suffix may use a universal character name (the standard writes `_\u03C0`) |
| `float operator ""_e(const char*);` | OK | raw literal operator |
| `float operator ""E(const char*);` | IFNDR | the suffix doesn't begin with an underscore |
| `double operator""_Bq(long double);` | OK | `_Bq` isn't an identifier token |
| `double operator"" _Bq(long double);` | IFNDR | uses the reserved identifier `_Bq` |
| `float operator " "B(const char*);` | ill-formed | the string isn't empty |
| `string operator ""5X(const char*, std::size_t);` | ill-formed | `5X` isn't a valid suffix |
| `double operator ""_miles(double);` | ill-formed | the parameter list isn't in ¶3 |
| `template <char...> int operator ""_j(const char*);` | ill-formed | a template's function parameter list must be empty |
| `extern "C" void operator ""_m(long double);` | ill-formed | C language linkage |

!!! impl
    - The Itanium C++ ABI mangles literal operators with `li` plus the suffix name; for example, `operator""_km(long double)` mangles to `_Zli3_kme`.
    - Clang's diagnostics are fairly clear, such as `invalid literal operator parameter type 'double', did you mean 'long double'?`, `literal operator 'operator""_x' must be in a namespace or global scope`, and `literal operator must have C++ linkage`.
    - A numeric template generates one specialization per distinct spelling; even `1_x` and `01_x` differ. Heavy use increases compile time and the number of symbols; there's usually no runtime cost, because the operators are generally `constexpr` or `consteval` and inlined.

## History

!!! history
    - C++11's [[N2765]] introduced user-defined literals: five kinds of literal operator (raw, integer, floating-point, character, string) and the numeric literal operator template.
    - The C++14 standard library began providing literal suffixes (`s` for `std::string`, `h`, `min`, `ms` in `<chrono>`, `i` in `<complex>`, etc.), all in inline namespaces of `std::literals`.
    - C++20's [[P0732R2]] allowed class types as constant template parameters and added the string literal operator template on that basis; [[P0482R6]] added `char8_t`, adding two more parameter lists accordingly.
    - C++23's [[CWG2521]] deprecated the form with a space and clarified its relationship with reserved identifiers.

## Common misconceptions

!!! pitfall "`-5_km` passes -5 to the operator"
    The minus sign isn't part of the literal. `-5_km` applies unary `-` to the result of `5_km`, so the return type needs to support unary `-`.

!!! pitfall "Using `int` or `double` as the parameter works too"
    The integer version can only be `unsigned long long` and the floating-point version only `long double`. When you need a narrower type, check the range in the function, preferably as `consteval`.

## Questions

!!! question "1. With both `int operator\"\"_x(unsigned long long)` and `int operator\"\"_x(const char*)` declared, which does each of `12_x` and `1.5_x` call?"

<details markdown="1">
<summary>Answer</summary>

`12_x` calls the `unsigned long long` version. [[lex.ext#3]] first checks whether there's a literal operator with an `unsigned long long` parameter, and if so uses it; the raw version doesn't take part in any comparison. `1.5_x` is a floating-point literal with no `long double` version, so the raw literal operator is used, calling `operator""_x("1.5")`. This choice is made by [[lex.ext]] in a fixed order, not by the conversion-sequence ranking of [[over.match]].
</details>

!!! question "2. Which is valid: `int operator\"\"_s(const wchar_t*, unsigned long);` or `int operator\"\"_s(const wchar_t*, unsigned);`?"

<details markdown="1">
<summary>Answer</summary>

It depends on the implementation. ¶3 requires the parameter list to be equivalent to `const wchar_t*, std::size_t`, and `std::size_t` is an alias for some implementation-defined unsigned integer type. On 64-bit Linux and macOS (LP64) it's `unsigned long`, so the first declaration is valid and the second ill-formed; on other platforms it may be the other way round. Portable code should write `std::size_t` directly.
</details>
