---
title: Normative references
summary: "Where the rules the C++ standard does not write out, but must follow, come from: the C standard library from C23, floating point from IEEE 754, std::regex's default grammar from ECMAScript, the filesystem from POSIX, and characters from Unicode."
updated: 2026-10-18
---

!!! tldr
    - The C++ standard library is built on the standard library of C23 (ISO/IEC 9899:2024). The meaning of headers like `<cstdio>` and `<cmath>` is specified by the C standard, and its undefined behavior comes along with it.
    - Floating-point arithmetic refers to ISO/IEC 60559, that is, IEEE 754. But C++ does not require `float` and `double` to use it; query `numeric_limits<T>::is_iec559`.
    - The default grammar of `std::regex` is ECMAScript 3rd edition from 1999; the filesystem library and the POSIX-style regex grammars follow POSIX.
    - Which characters identifiers may use and how `std::format` estimates width follow Unicode 15.1; an implementation may also use a newer version.

## Where the rules for printf are written

```cpp run ub
#include <cstdio>
int main() {
  long n = 42;
  std::printf("%d\n", n);   // UB: %d requires int, the argument is long
}
```

You will not find the meaning of `%d` in the C++ standard. [[cstdio.syn]] only says that the contents and meaning of `<cstdio>` are the same as those of the C standard library header `<stdio.h>`, so everything the C standard says about `printf` becomes part of C++. The C standard says a mismatch between format and argument type is undefined behavior, so this C++ code is too. Clang 23 gives a `-Wformat` warning for it.

¶1 [intro.refs] lists exactly such documents. The text refers to them in such a way that some or all of their content becomes requirements of this document.

!!! std
    The following documents are referred to in the text in such a way that some or all of their content constitutes requirements of this document.

## Which documents are referenced

| Reference | What it means for a C++ programmer |
|---|---|
| ISO/IEC 9899:2024 (C23) | The semantics of the C standard library headers (`<cstdio>`, `<cmath>`, `<cstring>` and so on); the many "See also: ISO/IEC 9899:2024" notes in the library clauses point to it |
| ISO/IEC 60559:2020 (IEEE 754) | `numeric_limits::is_iec559`; the formats of extended floating-point types such as `std::float32_t` and `std::float64_t` ([[basic.extended.fp]]) |
| ISO/IEC/IEEE 9945 (POSIX, Issue 7 with two corrigenda) | The semantics of the filesystem library ([[fs.conform.9945]]); the basic, extended, awk, grep and egrep grammars of `std::regex`; the error codes of `std::errc` |
| ECMA-262 3rd edition (1999, ECMAScript) | The default grammar of `std::regex`, with modifications ([[re.grammar]]) |
| Unicode 15.1 | The character set, identifier syntax (Annex E [[uaxid]]), literal encodings, and `std::format`'s width estimation |
| ISO 8601-1:2019 | Date representation and week-based years in `<chrono>` formatting ([[time.format]]) |

The program below uses one item from each:

```cpp run ok
#include <chrono>
#include <cstdio>
#include <format>
#include <limits>
#include <regex>
int main() {
  // ISO/IEC 60559 (IEEE 754): whether double uses it is reported by the implementation
  std::printf("%d\n", std::numeric_limits<double>::is_iec559);   // 1

  // ISO 8601: %F is the calendar date; %G-W%V-%u is the week-based year, week number and weekday
  // prints 2027-01-01 = 2026-W53-5
  using namespace std::chrono;
  sys_days d = 2027y / January / 1;
  std::puts(std::format("{:%F} = {:%G-W%V-%u}", d, d).c_str());

  // ECMAScript 3rd edition: the default grammar supports lookahead assertions
  std::printf("%d\n", std::regex_search("ab", std::regex("a(?=b)")));  // 1

  // POSIX: the same pattern is not a valid extended regular expression (ERE)
  try { std::regex("a(?=b)", std::regex::extended); }
  catch (const std::regex_error&) { std::puts("not valid POSIX ERE"); }
}
```

With Clang 23 and libc++ the output matches the comments. 1 January 2027 is a Friday, and under the ISO 8601 rules it belongs to week 53 of 2026; that is the difference between a week-based year and a calendar year.

## Relationship with the C standard library

C++ references the C standard mainly for its standard library (Clause 7 of the C standard). C's language rules do not apply to C++: only the parts the text actually uses are referenced. And those parts are further modified by C++ ([[library.c]], [[diff.library]]). For example, C's `strchr` takes `const char*` and returns `char*`, while C++'s `<cstring>` provides two const-correct overloads ([[cstring.syn]]); C's `<tgmath.h>` macros are replaced by function overloads in C++.

The version of the C standard referenced advances along with C++: C++98/03 referenced C90, C++11/14 referenced C99, C++17 referenced C11, C++20 and C++23 referenced C17, and the current draft references C23. Each upgrade brings a batch of C library changes into C++.

!!! pitfall "std::regex is JavaScript's regex"
    It is based on ECMAScript 3rd edition from 1999, with modifications. Things JavaScript added later, such as named capture groups, lookbehind assertions and the `u` flag, are not supported by `std::regex`.

<details class="fine" markdown="1"><summary>Remaining wording</summary>

- A dated reference (such as ISO/IEC 9899:2024) applies only to the edition cited; an undated reference applies to the latest edition, including all amendments. C++ dates almost all of its references to substantive technical documents, so that a new edition of C or POSIX does not change the requirements of C++ without C++ knowing. Unicode is referenced by a specific version, but [[intro.compliance]] ¶10 allows implementations to use a later version.
- ISO/IEC 2382 (information technology vocabulary) and ISO 80000-2:2019 (mathematical signs) provide basic terminology and mathematical notation; [[intro.defs]] incorporates their definitions into the standard's vocabulary.
- The footnotes on POSIX and ECMAScript are trademark notices.
- The Bibliography at the end of the draft lists the past C++ standards, the IANA time zone database and so on; these are only references and do not constitute requirements.

</details>
