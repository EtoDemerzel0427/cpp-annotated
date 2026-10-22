---
title: User-defined literals
summary: 'How suffixed literals such as 10_km and "abc"s are rewritten into calls to literal operators: how the suffix is split off, how the operator is looked up, how integer and floating-point literals choose among three forms, the template form for string literals, and the rules for suffixes during concatenation.'
updated: 2026-10-19
---

!!! tldr
    - `10_km` is rewritten into a call to `operator""_km`; the operator is found by unqualified lookup, so using the standard library's `"abc"s` first requires `using namespace std::literals;`.
    - An integer literal prefers the version whose parameter is `unsigned long long`; only without it is one of the raw form `(const char*)` and the template form `template<char...>` chosen, and the two cannot both exist. Floating-point literals work the same way, preferring `long double`.
    - A string literal prefers an operator template that can take the whole string as a template argument (C++20); otherwise `(str, len)` is called.
    - A token that can also be taken as an ordinary literal is treated as one, so `12LL` is not a user-defined literal.
    - User suffixes must begin with an underscore; declare them as `operator""_x`, since the spaced form `operator"" _x` is deprecated.

A **user-defined literal** (UDL) is an integer, floating-point, character or string literal immediately followed by an identifier suffix (a **ud-suffix**), such as `10_km`, `"abc"s` or `1.5i`. Its meaning is determined by a function or function template named `operator""suffix`, called a **literal operator**.

This subclause specifies how a UDL is rewritten into a call to a literal operator. The rules for declaring literal operators are in [[over.literal]], and the reservation rules for suffixes are in [[usrlit.suffix]].

```cpp run title="udl-intro.cpp" ok
struct Meters { double v; };
constexpr Meters operator""_km(long double x) {
  return {static_cast<double>(x) * 1000};
}
constexpr Meters operator""_km(unsigned long long x) {
  return {static_cast<double>(x) * 1000};
}
static_assert((1.5_km).v == 1500 && (2_km).v == 2000);
int main() {}
```

## How a literal is split (¶1)

Grammatically, a UDL is the body of an ordinary literal followed by an identifier suffix. The body of an integer or floating-point UDL contains no built-in suffix: the body of `12_km` is `12`.

The first rule of ¶1: if a token matches both a user-defined literal and some other kind of literal, it is treated as the latter. Example 1 points out that `123_km` is a user-defined literal while `12LL` is an integer literal, even though `LL` is also an identifier in spelling. This guarantees that introducing UDLs does not change the meaning of any existing literal.

The second rule of ¶1: the body before the suffix is the longest sequence of characters that matches.

```cpp run title="udl-split.cpp" ok
template<char... C> constexpr int operator""_cnt() {
  return sizeof...(C);
}
static_assert(0x1F_cnt == 4);   // body 0x1F
static_assert(1.5e3_cnt == 5);  // body 1.5e3
static_assert(1'000_cnt == 5);  // the body includes the separator: 1 ' 0 0 0
int main() {}
```

Because the body is the digit part of an integer or floating-point literal and contains no built-in suffix, the body of `12LL_x` can only be `12`, with the suffix `LL_x`. That suffix does not begin with an underscore and is reserved; Clang 23 reports the error "invalid suffix 'LL_x' on integer constant". Built-in suffixes and user suffixes cannot be stacked.

During preprocessing, an integer or floating-point UDL is one preprocessing number ([[lex.ppnumber]]), and a character or string UDL is likewise one preprocessing token ([[lex.pptoken]]). The suffix is not a separate identifier token, so it is not subject to macro expansion.

## Looking up the literal operator (¶2)

¶2 A UDL is treated as a call to a literal operator or literal operator template. For a UDL with suffix X, unqualified lookup ([[basic.lookup.unqual]]) is first performed for the name `operator""X`, giving a set of declarations S. S shall not be empty.

Unqualified lookup means the literal operator must be visible at the point of use. The standard library's literal operators live in inline namespaces such as `std::literals::string_literals`, so you first write `using namespace std::literals;` or a more specific namespace. The arguments of the rewritten call are all built-in types or character pointers with no associated namespaces, so argument-dependent lookup does not help.

```cpp run title="udl-lookup.cpp" ok
#include <string>
#include <string_view>
int main() {
  // auto s0 = "abc"s;   // error: operator""s not found
  using namespace std::literals;
  auto s = "abc"s;       // std::string
  auto sv = "abc"sv;     // std::string_view
  return s.size() == sv.size() ? 0 : 1;
}
```

## Integer and floating-point UDLs (¶3–¶4)

Literal operators come in several forms, which [[over.literal]] names. One whose parameter is `const char*` is a **raw literal operator**, and it receives the source characters of the literal. A template of the form `template<char...>` is a **numeric literal operator template**, which receives the source characters as template arguments.

¶3 Let n be an integer UDL without its suffix. The form of the call is decided in this order:

1. If S contains a literal operator with parameter type `unsigned long long`, the call is `operator""X(nULL)`.
2. Otherwise, S shall contain a raw literal operator or a numeric literal operator template, but not both. For the raw operator the call is `operator""X("n")`; for the template it is `operator""X<'c1', 'c2', ..., 'ck'>()`, where c1…ck are the source characters of n. Note 1 explains that these characters can only be from the basic character set.

```cpp run title="udl-int.cpp" ok
#include <cstring>
#include <cassert>
constexpr unsigned long long operator""_u(unsigned long long v) {
  return v;
}
struct Raw { const char* s; };
Raw operator""_raw(const char* s) { return {s}; }
static_assert(42_u == 42 && 0x10_u == 16 && 0b11_u == 3);
int main() {
  assert(std::strcmp((123_raw).s, "123") == 0);
  assert(std::strcmp((1'000_raw).s, "1'000") == 0);  // it sees the source characters
  assert(std::strcmp((0x1p3_raw).s, "0x1p3") == 0);  // floating-point UDLs can use it too
}
```

The `unsigned long long` version receives a value already parsed by the compiler, with the base and digit separators already handled. Whenever it exists it is preferred, even if a raw version exists as well. The raw and template forms are only fallbacks, and they cannot both exist, or the call would be ambiguous.

The `nULL` formulation has a consequence: n followed by `ULL` must be a valid integer literal. When the value exceeds `unsigned long long`, `nULL` is ill-formed, and so is the whole UDL, even if you provided a raw version. To handle arbitrarily large numbers (as in a big-integer library), provide only the raw or template form.

```cpp title="udl-ambig.cpp" error
int operator""_y(const char*);
template<char...> int operator""_y();
int a = 42_y;   // error: a raw operator and a numeric template cannot coexist
unsigned long long operator""_z(unsigned long long);
int b = 18446744073709551616_z;   // error: nULL is out of range
```

¶4 The rules for floating-point UDLs are parallel, except that the preferred version's parameter is `long double`, and the call is `operator""X(fL)`, where f is the literal without its suffix.

The value is first converted to `long double`, which already loses precision where exact decimals are needed, as for fixed-point numbers and currency. The raw and template forms let a library parse the source characters itself, converting `0.1_dec` exactly to a decimal fixed-point value at compile time.

## String and character UDLs (¶5–¶6)

¶5 Let str be a string UDL without its suffix, and len the number of code units in str, excluding the terminating null character:

1. If S contains a literal operator template with a constant template parameter for which str is a well-formed template argument, the call is `operator""X<str>()`.
2. Otherwise the call is `operator""X(str, len)`.

```cpp run title="udl-string.cpp" ok
#include <cstddef>
template<std::size_t N> struct FixedString {
  char buf[N]{};
  constexpr FixedString(const char (&s)[N]) {
    for (std::size_t i = 0; i < N; ++i) buf[i] = s[i];
  }
};
template<FixedString S>
constexpr std::size_t operator""_fs() { return sizeof(S.buf); }
constexpr std::size_t operator""_len(const char*, std::size_t n) {
  return n;
}
static_assert("hello"_fs == 6);   // S is FixedString<6>{"hello"}
static_assert("abc"_len == 3);    // len excludes the null character
int main() {}
```

The first form was introduced in C++20 by [[P0732R2]], together with constant template parameters of class type. The whole string becomes a template argument, so it can be processed completely at compile time, for example to check a format string or compile a regular expression. The parameter must be of class type, because a string literal itself cannot be a template argument ([[lex.string]]); typically a fixed-length string class template constructible from a character array is used.

String UDLs have no raw form. The parameter types of `(str, len)` vary with the prefix: `u8"x"_len` needs `operator""_len(const char8_t*, std::size_t)`.

¶6 Let ch be a character UDL without its suffix. S shall contain a literal operator whose only parameter has the type of ch, and the call is `operator""X(ch)`.

```cpp run title="udl-char.cpp" ok
constexpr int operator""_ord(char c) { return c; }
constexpr char32_t operator""_c(char32_t c) { return c; }
static_assert('A'_ord == 'A' && U'x'_c == U'x');
int main() {}
```

¶7 The standard's Example 2 puts these cases together:

```cpp title="udl-example.cpp" error
#include <string>
#include <cstddef>
long double operator ""_w(long double);
std::string operator ""_w(const char16_t*, std::size_t);
unsigned operator ""_w(const char*);
int main() {
  1.2_w;      // calls operator ""_w(1.2L)
  u"one"_w;   // calls operator ""_w(u"one", 3)
  12_w;       // no unsigned long long version, calls operator ""_w("12")
  "two"_w;    // error: only a char16_t version exists, no applicable literal operator
}
```

## Concatenation (¶8–¶9)

¶8 In translation phase 5, adjacent string literals are concatenated, and user-defined string literals are treated as string literals for this step. The suffixes are removed first, and concatenation follows the rules of [[lex.string]]. If any user-defined string literals take part in the concatenation, they must all have the same suffix, and that suffix is applied to the result of the concatenation.

```cpp title="udl-concat.cpp" error
#include <cstddef>
constexpr std::size_t operator""_x(const wchar_t*, std::size_t n) { return n; }
constexpr std::size_t operator""_x(const char*, std::size_t n) { return n; }
static_assert(L"A" "B" "C"_x == 3);  // OK: equivalent to L"ABC"_x
static_assert("a" "b"_x == 2);       // OK: the suffix appears on only one piece
auto e = "P"_x "Q" "R"_y;            // error: two different suffixes
```

The suffix may appear on any one or several of the pieces, but they must not conflict. Example 3 in ¶9 is the first and last lines above.

## Declaring literal operators ([[over.literal]])

Writing UDLs requires these rules from Chapter 12:

- The parameter list of a literal operator can only be one of a fixed set: `const char*`, `unsigned long long int`, `long double`, `char`, `wchar_t`, `char8_t`, `char16_t`, `char32_t`, and the five forms `(const charT*, std::size_t)`, with no default arguments. There are only two kinds of templates: the numeric template `template<char...>`, and the string template with one constant template parameter of class type.
- A literal operator must belong to a namespace (it can be a friend) and cannot have C language linkage.
- Suffixes not beginning with an underscore are reserved for future standardization ([[usrlit.suffix]]); declaring a literal operator with one is IFNDR (ill-formed, but the compiler need not report it). Suffixes containing `__` are reserved for the implementation. The standard library's `s`, `sv`, `ms` and `i` do not begin with an underscore, which is exactly why they cannot clash with user code.

### The spaced form is deprecated {{deprecated}}

There are two ways to write the declaration of a literal operator:

<div class="compare" markdown="1">

```cpp
// deprecated: the string "" plus the identifier _x
double operator"" _x(long double);
```

```cpp
// recommended: one token ""_x
double operator""_x(long double);
```

</div>

The difference is not just whitespace. In the first form, `_x` is a separate identifier token and is subject to the reserved identifier rules of [[lex.name]], so `operator"" _Bq` uses the reserved identifier `_Bq` (underscore followed by an uppercase letter). In the second form, `_Bq` is not a separate token, and it is perfectly valid. To remove this unreasonable difference, the spaced form was deprecated ([[depr.lit]], via [[CWG2521]]). Clang 23 gives a `-Wdeprecated-literal-operator` warning for it.

## History and evolution

!!! history
    | Version | Change |
    |---|---|
    | C++11 | UDLs introduced ([[N2765]]): the three forms for integers and floating-point (parsed value, raw, `template<char...>`); the `(str, len)` form for strings; the character form |
    | C++14 | The first standard library UDLs: `s` (string); chrono's `h`, `min`, `s`, `ms`, `us`, `ns`; complex's `i`, `il`, `if` |
    | C++17 | `sv` (string_view) |
    | C++20 | String literal operator templates ([[P0732R2]]); the `char8_t` forms; chrono's `d` and `y` |
    | C++23 | The spaced `operator"" _x` deprecated |

## Common misconceptions

!!! pitfall "A macro such as PRId64 right after a string still expands"
    Since C++11, the `"%"PRId64` in `printf("%"PRId64"\n", v)` is a user-defined string literal with suffix `PRId64`, and the macro is not expanded ([[diff.cpp03.lex]]). Clang 23 reports "invalid suffix on literal; C++11 requires a space between literal and identifier". Put a space between the string and the macro name.

!!! pitfall "`-5_km` passes -5 to the literal operator"
    Literals have no minus sign; `-5_km` is `-(5_km)`, unary minus applied to the return value of the literal operator. If the return type does not support unary minus, it is an error.

## Questions

!!! question "Question 1"
    Given the declarations below, which function does each expression call?

    ```cpp
    int operator""_a(unsigned long long);
    int operator""_a(const char*);
    int operator""_a(long double);
    // (1) 0x1F_a   (2) 1e3_a   (3) 1'000_a   (4) 99999999999999999999_a
    ```

<details markdown="1">
<summary>Answer</summary>

1. `0x1F_a`: an integer UDL with an `unsigned long long` version available, so it calls `operator""_a(0x1FULL)`.
2. `1e3_a`: `1e3` has an exponent, so it is a floating-point UDL; a `long double` version exists, so it calls `operator""_a(1e3L)`.
3. `1'000_a`: an integer UDL, calling `operator""_a(1'000ULL)`, that is, 1000.
4. `99999999999999999999_a`: an integer UDL. Because an `unsigned long long` version exists, `99999999999999999999ULL` must be used, and that exceeds the range of `unsigned long long`, so it is ill-formed. The raw version exists but is not considered: only when there is no `unsigned long long` version does ¶3 reach its otherwise branch.
</details>

!!! question "Question 2"
    Why does ¶1 say that a token matching both is treated as an ordinary literal? Give an example that would go wrong without this rule.

<details markdown="1">
<summary>Answer</summary>

A suffix can be any identifier, and the built-in suffixes `u`, `l`, `ll`, `f` and `z` are all identifiers in spelling. Without this rule, `12u` could be either an integer literal with suffix `u` or a user-defined literal with suffix `u`. Preferring the ordinary literal guarantees that adding UDLs does not change the meaning of existing literals. The same consideration explains why suffixes not beginning with an underscore are reserved for the standard: built-in suffixes added later, such as C++23's `z`, cannot clash with users' literal operators.
</details>
