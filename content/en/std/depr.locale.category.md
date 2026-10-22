---
title: "Deprecated library features, part 2: localization, formatting, time, filesystem and iostreams (D.20–D.23, D.25–D.26)"
summary: "The text- and I/O-related deprecations in Annex D: the codecvt facets converting between UTF-16/32 and UTF-8, visit_format_arg, asctime and ctime, filesystem::u8path, path::string() returning std::string, and stream input and output of signed char and unsigned char."
updated: 2026-10-19
---

!!! tldr
    - What these deprecations have in common: the old interfaces don't say what encoding a `char` string holds, and the new interfaces make it clear through types (`char8_t`, `std::u8string`) or function names.
    - Facets such as `codecvt<char16_t, char, mbstate_t>` hard-wire `char` as UTF-8 and are deprecated; the standard library currently has no general replacement.
    - `std::uint8_t` is usually just `unsigned char`, and `std::cout << v` prints it as a character. That's why the `<<` and `>>` overloads for `signed char` and `unsigned char` were deprecated, while `std::format` has always treated them as integers.
    - `asctime` and `ctime` return a pointer to a shared static buffer and aren't guaranteed to be thread-safe; use `std::format` and `<chrono>` instead.
    - `u8path` is superseded by `path(std::u8string)`; `path::string()` without template arguments is also deprecated, so use `native_encoded_string()` or `display_string()` depending on the purpose.

**Deprecated** features are still normative; they have just been identified as candidates for possible future removal, and implementations may add `[[deprecated]]` to these names ([[depr.general#2]]). The test environment for this page is Clang 23.1.3 with libc++.

## D.20 Deprecated locale category facets {#depr.locale.category}

```cpp
#include <locale>
using F = std::codecvt<char16_t, char, std::mbstate_t>;
auto& a = std::use_facet<F>(std::locale());  // deprecated
```

¶1–¶2 The `ctype` locale category additionally includes four `codecvt` facets and the corresponding four `codecvt_byname`s: `char16_t` and `char32_t`, each paired with `char` and with `char8_t`. A **facet** is the object in a locale responsible for one kind of functionality; here, character encoding conversion.

¶3 The two `char16_t` specializations convert between UTF-16 and UTF-8, and the two `char32_t` ones between UTF-32 and UTF-8.

`codecvt<char16_t, char, mbstate_t>` hard-wires the `char` sequence as UTF-8, which conflicts with `char` meaning the native encoding everywhere else. When C++20 introduced `char8_t`, it deprecated the two `char` versions in favor of `char8_t` versions ([[P0482R6]]). Later the `char8_t` versions were also judged not to belong in locales, and were deprecated too ([[LWG3767]]). The whole `codecvt` interface, based on `mbstate_t`, obtained from a locale, with clumsy error handling, isn't suitable for Unicode conversion. C++26 has removed the `<codecvt>` header ([[P2871R3]]).

libc++ issues `-Wdeprecated-declarations` warnings for both the `char` versions and the `char8_t` versions from `-std=c++20` on.

The standard library currently has no general Unicode encoding conversion facility. In practice, use a third-party library (ICU, simdutf and so on), or write the conversions between UTF-8, UTF-16 and UTF-32 yourself; they only involve bit operations.

## D.21 `visit_format_arg` {#depr.format}

```cpp
#include <format>
void f(std::format_args a) {
  std::visit_format_arg([](auto) {}, a.get(0));  // deprecated
  a.get(0).visit([](auto) {});                   // C++26
}
```

### D.21.1 `<format>` synopsis {#depr.format.syn}

¶1 `<format>` additionally declares the function template `visit_format_arg(Visitor&& vis, basic_format_arg<Context> arg)`.

### D.21.2 Formatting arguments {#depr.format.arg}

¶1 Its effect is equivalent to `return visit(std::forward<Visitor>(vis), arg.value_);`, where `value_` is the exposition-only `variant` member inside `basic_format_arg`.

C++26 added a member function `visit` to `basic_format_arg`, plus `visit<R>` which lets the return type be specified explicitly, consistent with the `std::variant::visit` member added at the same time ([[P2637R3]]). The free function `visit_format_arg` thereby became redundant.

libc++ warns under `-std=c++2c`; there's no warning under `-std=c++20`, where the member `visit` doesn't exist yet either.

## D.22 `asctime` and `ctime` {#depr.ctime}

```cpp
#include <ctime>
std::time_t t = 0;
char* s = std::ctime(&t);  // deprecated: s points into a shared static buffer
```

¶1 `<ctime>` additionally declares `char* asctime(const tm* timeptr);` and `char* ctime(const time_t* timer);`.

¶2 These functions are not required to avoid data races. Standard library functions are normally required to ensure that concurrent calls don't introduce data races ([[res.on.data.races]]); this explicitly exempts them from that guarantee.

They return a pointer to a static buffer, so multiple threads calling them at the same time overwrite each other's results; `asctime` also overflows that fixed-size buffer when the year has more than four digits. C23 deprecated them, and C++ accordingly moved them from `<ctime>` in the main text ([[ctime.syn]]) to here.

libc++ gives no warning for them. The replacement is `std::format("{:%c}", std::chrono::system_clock::now())` ([[time.format]]), or C's `strftime`.

## D.23 Deprecated filesystem facilities {#depr.filesystems}

### D.23.1 The factory function `u8path` {#depr.fs.path.factory}

```cpp
#include <filesystem>
auto p1 = std::filesystem::u8path("abc");  // deprecated
auto p2 = std::filesystem::path(u8"abc");  // replacement
```

¶1–¶2 `<filesystem>` additionally provides two function templates, `u8path(const Source&)` and `u8path(InputIterator, InputIterator)`, whose arguments must have value type `char` or `char8_t`. ¶3 The precondition is that the input is UTF-8 encoded.

¶4 How the return value is constructed depends on the platform: if `path::value_type` is `char` and the native narrow encoding is UTF-8, the `path` is constructed directly; if `value_type` is `wchar_t` and the wide encoding is UTF-16 (Windows), or `value_type` is `char16_t` or `char32_t`, the input is first converted to `path::string_type`; otherwise it is first converted to a `u32string`. ¶5 specifies that how the Unicode conversion is performed is unspecified.

In C++17 `std::string` had no way of expressing "this is UTF-8", so a dedicated factory function was used to state the encoding. C++20 has `char8_t` and `std::u8string`, and `path`'s constructors can recognize UTF-8 from the argument type. The note in ¶6 explains that the form in the example represents historical usage, and that passing a `std::u8string` directly to `path`'s constructor is now preferred.

libc++ warns from `-std=c++20` on. When what you have is a `std::string` holding UTF-8 (read from a network or a database, for example), you first have to convert it to a `char8_t` sequence: `std::u8string(s.begin(), s.end())`. This is a widely acknowledged inconvenience of the `char8_t` approach.

### D.23.2 Format observers returning `std::string` {#depr.fs.path.obs}

```cpp
#include <filesystem>
std::string s(const std::filesystem::path& p) {
  return p.string();  // deprecated
}
```

¶1 `path` additionally declares two non-template members, `std::string string() const;` and `std::string generic_string() const;`. ¶2 The former returns `native_encoded_string()`, and ¶3 the latter returns `generic_native_encoded_string()`.

The `path` of the main text ([[fs.class.path]]) gained `native_encoded_string()`, `display_string()` and their `generic_` versions, and the old non-template `string()` was moved here (see [[P2319R5]]). The main text still keeps the template version `string<EcharT, traits, Allocator>(const Allocator&)`, but its `EcharT` has no default and can't be deduced, so a call `p.string()` without template arguments calls exactly the deprecated non-template version here.

The name `string()` doesn't say what encoding it returns. On POSIX it returns the raw bytes, and a file name isn't necessarily valid UTF-8; on Windows it converts UTF-16 to the current code page, which can lose characters. The new interfaces are distinguished by purpose:

- `native_encoded_string()` converts to the native narrow encoding, for passing to the operating system or C APIs;
- `display_string()` equals `std::format("{}", path)`, for display; the result is suitable for passing to formatting and `print` functions.

libc++ doesn't implement the new interfaces yet, and `p.string()` produces no warning. To get a file name losslessly, use `p.native()` (of type `path::string_type`) or `p.u8string()`.

## D.25 and D.26 Stream input and output of `signed char` and `unsigned char`

```cpp run ok
#include <cstdint>
#include <format>
#include <iostream>
#include <sstream>
int main() {
  std::uint8_t v = 65;
  std::cout << v << '\n';                   // prints A, not 65
  std::cout << std::format("{}", v) << '\n';  // prints 65
  std::istringstream in("42");
  std::uint8_t n;
  in >> n;                                  // reads only the character '4'
  std::cout << int(n) << '\n';              // prints 52
}
```

On mainstream platforms `std::int8_t` and `std::uint8_t` are just aliases for `signed char` and `unsigned char`, and streams treat these two types as characters. A programmer who wants to output the number 65 gets the letter `A`; one who wants to read the number 42 reads the character `'4'`, that is, 52. The output of the example above on libc++ is exactly `A`, `65`, `52`. `std::format` has formatted these two types as integers from the start.

Deprecating these overloads prepares for changing their behavior or removing them in the future. Until then, code should make its intent clear: convert to `char` if you want a character, promote to `int` (`+c` or `int(c)`) if you want a number; when reading a number, read into an `int` first, check the range, and then convert.

### D.25 Extraction {#depr.istream.extractors}

¶1–¶3 `<istream>` additionally provides `operator>>` for `basic_istream<char, traits>` reading into `unsigned char&` and `signed char&`. It is a formatted input function that extracts one character and stores it in `c`; if no character is available it sets `failbit`.

¶4–¶9 Two more overloads read into `unsigned char (&)[N]` and `signed char (&)[N]`. Let `n` be the smaller of `width()` and `N` (or `N` if `width()` is not greater than 0). The function extracts characters until `n - 1` have been stored, end of file is reached, or a whitespace character is encountered, then stores a null byte and calls `width(0)`. If no characters were extracted, it sets `failbit`.

### D.26 Insertion {#depr.ostream.inserters}

¶1–¶3 `<ostream>` additionally provides `operator<<` for `basic_ostream<char, traits>` writing `signed char` and `unsigned char`, equivalent to `return out << static_cast<char>(c);`.

¶4–¶5 The `operator<<` overloads writing `const signed char*` and `const unsigned char*` are equivalent to `return out << reinterpret_cast<const char*>(s);`, that is, output as a null-terminated string.

libc++ hasn't marked these two groups of overloads as deprecated yet, and there's no warning even under `-Wdeprecated`.

## Summary

| Subclause | Feature | Instead | libc++ warning |
|---|---|---|---|
| D.20 | `codecvt<char16_t/char32_t, char/char8_t>` | A third-party library or hand-written conversion | Since C++20 |
| D.21 | `visit_format_arg` | `basic_format_arg::visit` | C++26 mode |
| D.22 | `asctime`, `ctime` | `std::format` with `<chrono>`, `strftime` | None |
| D.23.1 | `u8path` | `path(std::u8string)` | Since C++20 |
| D.23.2 | Non-template `path::string()`, `generic_string()` | `native_encoded_string()`, `display_string()` | None (new interfaces not implemented) |
| D.25, D.26 | `>>` and `<<` for `signed char` and `unsigned char` | Explicit conversion to `char` or `int` | None |
