---
title: Format strings
summary: "The syntax of std::format format strings: replacement fields and escapes, why automatic and manual numbering cannot be mixed; what each option of the standard format spec [[fill]align][sign][#][0][width][.precision][L][type] means; why width is measured in terminal columns; and which errors are found at compile time and which throw only at run time."
updated: 2026-10-19
---

!!! tldr
    - A format string consists of replacement fields `{arg-id:format-spec}`, the escapes `{{` and `}}`, and ordinary characters. Replacement fields either all omit their numbers or all spell them out, including fields nested in width and precision.
    - The format-spec after the colon is interpreted by the argument type's formatter, so whether a format string is valid depends on the argument types. Errors that depend only on the format string and the argument types are reported at compile time.
    - The options of the standard format spec come in a fixed order: fill and align, sign, `#`, `0`, width, precision, `L`, type.
    - Width is measured in terminal columns; CJK characters and most emoji count as 2. String precision also truncates by columns.
    - Without `L`, output is locale-independent; floating-point numbers default to the shortest form that reads back exactly.

The format string is `std::format`'s little language, in two layers. The outer syntax is specified uniformly by [format.string.general]: where the replacement fields are and how they are numbered. The part after the colon in each replacement field is interpreted by the formatter of the corresponding argument type. [format.string.std] specifies the one interpretation the standard library uses for arithmetic, character, string and pointer types, called *std-format-spec*. Chrono types have their own ([[time.format]]), and the format specs of ranges and tuples are covered in [[format.formatter]].

When `std::format("...", args...)` is called, the format string is fully checked at compile time ([[format.fmt.string]]). So what counts as a valid format string determines whether an error is a compile failure or a run-time exception.

## Outer syntax ([format.string.general])

### Replacement fields and escapes (¶1–¶3)

```cpp run title="indexing.cpp" ok
#include <cassert>
#include <format>

int main() {
  assert(std::format("{0}-{{", 8) == "8-{");
  assert(std::format("{1} to {0}", "a", "b") == "b to a");
  assert(std::format("{0}{0}{0}", "ha") == "hahaha");  // manual numbering can repeat
  assert(std::format("{}", 1, 2, 3) == "1");           // extra arguments are ignored
}
```

¶1 A format string consists of three kinds of components:

- **replacement fields** ([[g:replacement-field]]): `{`, an optional *arg-id*, an optional `:` plus *format-spec*, `}`;
- **escape sequences**: `{{` outputs `{` and `}}` outputs `}`;
- other characters, copied unchanged to the output.

So a lone `{` or `}` is invalid. An *arg-id* is `0` or a positive integer not beginning with 0, so `{01}` is invalid. The syntax of the *format-spec* is specified by the argument type's formatter; the only restriction is that it may not begin with `}`.

¶2 The *arg-id* says which argument to use. If there is no argument with that index, the string is not a format string for those arguments. The standard uses the phrase "is not a format string", and the consequence depends on where it is used: under compile-time checking the program is ill-formed ([[format.fmt.string]]), and the run-time `vformat` throws `format_error` ([[format.err.report]]).

### All automatic or all manual numbering (¶4)

¶4 If all *arg-id*s are omitted, 0, 1, 2, ... are used in order; this is **automatic indexing** ([[g:automatic-indexing]]). "All" includes fields nested inside a *format-spec*, such as the dynamic width in `{:{}}`.

!!! std
    If some *arg-id*s are omitted and some are present, the string is not a format string.

There may be more arguments than are referenced; the extra arguments are ignored, which is not an error. Manual numbering can refer to the same argument several times.

```cpp run title="mixing.cpp" error
#include <format>

int main() {
  auto s2 = std::format("{0} to {}", "a", "b");  // error: mixed
  auto s3 = std::format("{} {}", 1);             // error: not enough arguments
  auto s4 = std::format("{:{1}}", 1, 5);         // error: outer automatic, inner manual
  auto s5 = std::format("}");                    // error: lone }
}
```

Mixing like `s4`, hidden in a dynamic width, is easy to overlook. `{0:{}}` is mixing too. Write either `{:{}}` or `{0:{1}}`.

At run time the numbering state is kept by `basic_format_parse_context`: calling `next_arg_id()` when already in manual mode throws `format_error`, and so does calling `check_arg_id()` when already in automatic mode ([format.parse.ctx] ¶8–¶13; see [[format.formatter]]).

### The format-spec is determined by the type (¶5)

¶5 If the *format-spec* does not conform to the format specification of the argument type, the string is not a format string. Example 3 lists three interpretations: arithmetic, pointer and string types use *std-format-spec*; chrono types use *chrono-format-spec*; user-specialized formatters are decided by their `parse` member.

So `"{:%H}"` is invalid for `int` and valid for `chrono::seconds`. Whether a given format string is valid depends on the argument types, which is why `format_string<Args...>` has to carry the argument types.

## The standard format spec ([format.string.std])

### Syntax (¶1)

```text
std-format-spec:  fill-and-align(opt) sign(opt) #(opt) 0(opt) width(opt) precision(opt) L(opt) type(opt)
fill-and-align:   fill(opt) align          align: < > ^
sign:             + - space
width:            positive integer | { arg-id(opt) }
precision:        . nonnegative integer | . { arg-id(opt) }
type:             a A b B c d e E f F g G o p P s x X ?
```

The order of the options is fixed. `{:+#}` is valid and `{:#+}` is not, because the sign must come before `#`. `{:5+}` is invalid too: `5` is taken as the width, and the `+` after it has nowhere to go.

Every component is optional, so `{:}` is valid and equivalent to `{}`.

### Width is measured in terminal columns (¶2, ¶9, ¶11–¶14)

¶2 The unit of width is the **field width unit** ([[g:field-width]]), that is, the number of columns needed to display on a terminal, not bytes and not code units. ¶2 also defines three quantities:

- **minimum field width**: the value of the width option, or 0 if there is none (¶9);
- **estimated field width**: how many columns the formatted result itself occupies;
- **padding width**: the greater of 0 and (minimum field width − estimated field width).

¶11 A width written as a positive integer is its decimal value. The width syntax is a positive integer, so the `0` in `{:0}` can only be parsed as the zero-padding option, not a width of 0.

¶12–¶13 For UTF-8, UTF-16 and UTF-32 sequences, the implementation should split the text into extended grapheme clusters per UAX #29 and add up the width of the first code point of each cluster. Code points with width 2 are: those whose East_Asian_Width is W or F (CJK ideographs, fullwidth characters), the Yijing hexagram symbols (U+4DC0–U+4DFF), and two emoji blocks (U+1F300–U+1F5FF, U+1F900–U+1F9FF); all other code points have width 1. ¶14 The width under other encodings is unspecified.

So `std::format("{:>4}", "中")` outputs two spaces followed by "中", not three spaces.

### Fill and align (¶3–¶4)

¶3 The **fill character** is the character given by the *fill* option, or a space if there is no *fill*. *fill* can be any single character other than `{` and `}`; under UTF encodings it is one Unicode scalar value, and may be an emoji. Note 3 explains how it is parsed: check whether the second character of the *std-format-spec* is an alignment symbol; if so, the first character is the fill. So in `{:5>3}`, `5` is the fill character, and `1` is formatted as `551`.

¶4 Table 104 specifies three alignments:

| Option | Meaning | Default for |
|---|---|---|
| `<` | left-align, adding n fill characters after | non-arithmetic, non-pointer types, and `charT` and `bool` (when no integer presentation type is given) |
| `>` | right-align, adding them before | arithmetic types (except `charT` and `bool`), pointers, or when an integer presentation type is given |
| `^` | center, adding ⌊n/2⌋ before and ⌈n/2⌉ after | — |

The n in the table is the padding width. Note 4 points out that the fill character always counts as width 1. Using a width-2 emoji as the fill character misaligns: the standard's example `format("{:🤡^6}", "x")` gives `🤡🤡x🤡🤡🤡`, which takes 11 columns on a terminal.

### Sign, `#` and `0` (¶5–¶8)

```cpp run title="sign-zero.cpp" ok
#include <cassert>
#include <format>
#include <limits>

int main() {
  assert(std::format("{:+06d}", 42) == "+00042");
  assert(std::format("{:#06x}", 0xa) == "0x000a");   // zeros go after the prefix
  assert(std::format("{:<06}", -42) == "-42   ");    // 0 has no effect with an alignment
  double inf = std::numeric_limits<double>::infinity();
  assert(std::format("{:06}", inf) == "   inf");     // inf is not zero-padded
  assert(std::format("{0:},{0:+},{0: }", 1) == "1,+1, 1");
}
```

¶5 The sign option is valid only for arithmetic types (except `charT` and `bool`), or when an integer presentation type is given. `+` adds `+` before non-negative numbers; `-`, the default, adds a sign only to negative numbers; a space adds a space before non-negative numbers. Negative numbers and negative zero already carry `-`. ¶6 The sign option applies to infinity and NaN too, so `{:+}` outputs `+inf` and `+nan`.

¶7 `#` selects the **alternate form**. For integers, a base prefix is inserted after the sign; see Table 107 below. For floating-point numbers, finite values always output a decimal point; for `g` and `G`, trailing zeros are also kept.

¶8 The `0` option is valid for arithmetic types (except `charT` and `bool`) and pointers, or when an integer presentation type is given. It pads with `0` after the sign and base prefix, up to the padding width. When an alignment option is also given, `0` has no effect; nor does it when the value is infinity or NaN.

### Precision and dynamic width (¶10, ¶15–¶16)

```cpp run title="dynamic-width.cpp" ok
#include <cassert>
#include <format>

int main() {
  assert(std::format("{:>{}.{}f}", 3.14159, 10, 2) == "      3.14");  // all automatic numbering
  assert(std::format("{0:>{1}}", 7, 4) == "   7");                   // all manual numbering
  assert(std::format("{:.3}", "abcdef") == "abc");                   // string precision: truncation
  try {
    (void)std::format("{:{}}", 1, -3);   // negative width: known only at run time
  } catch (const std::format_error&) {
    return 0;
  }
  return 1;
}
```

¶15 Precision is valid only for floating-point and string types. For floating point, it is the precision used by the presentation type. For strings, it gives the longest prefix kept, one whose field width does not exceed the precision value. Giving a precision for integers, `bool`, characters or pointers is invalid.

String precision truncates by columns: `std::format("{:.1}", "中文")` yields an empty string, because "中" has width 2, which exceeds the precision 1.

¶10 When width or precision is written as `{arg-id(opt)}`, the value of the corresponding argument is used:

!!! std
    The option is valid only if the corresponding formatting argument is of standard signed or unsigned integer type. If its value is negative, an exception of type format_error is thrown.

There are two restrictions here, detected at different times:

1. The argument must be of a standard signed or unsigned integer type. `bool`, `char` and `double` are not allowed. This depends only on the type and can be checked at compile time; libc++ reports "Replacement argument isn't a standard signed or unsigned integer type".
2. A negative value throws `format_error`. This depends on the run-time value and can only be detected at run time.

### `L`: the locale-specific form (¶17)

¶17 The `L` option selects the **locale-specific form** and is valid only for arithmetic types. Integers get thousands separators per the locale's `numpunct`; floating-point numbers get thousands separators and the decimal point; `bool` outputs `truename` or `falsename`. When `L` is given, a call to `format` on that formatter is not a constant subexpression, because locales cannot be used at compile time.

Without `L`, the output is entirely independent of locale. This is the fundamental difference between `std::format` and `printf`, which is affected by `setlocale`.

### Presentation types (¶18–¶25)

```cpp run title="types.cpp" ok
#include <cassert>
#include <format>

int main() {
  assert(std::format("{0:b} {0:d} {0:o} {0:x}", 42) == "101010 42 52 2a");
  assert(std::format("{0:#x} {0:#X}", 42) == "0x2a 0X2A");
  assert(std::format("{:#o}", 0) == "0");          // octal 0 has no prefix
  assert(std::format("{:c}", 65) == "A");
  assert(std::format("{:d}", 'A') == "65");
  assert(std::format("{:6}", true) == "true  ");   // bool is left-aligned by default
  assert(std::format("{:d}", true) == "1");
  assert(std::format("{}", 0.1) == "0.1");         // shortest round trip
  assert(std::format("{:g}", 1234567.0) == "1.23457e+06");
  assert(std::format("{}", 1234567.0) == "1234567");
  assert(std::format("{}", nullptr) == "0x0");
  assert(std::format("{:?}", "a\tb") == "\"a\\tb\"");
}
```

¶20 The meaning of many presentation types is specified as if by calling `to_chars` ([[charconv]]) and copying the result to the output, transcoding first when `charT` is `wchar_t`. So `std::format` inherits the properties of `to_chars`: locale-independent, with floating-point numbers defaulting to the shortest round-trip form.

| Argument | Available types | Default |
|---|---|---|
| strings (Table 106) | `s`; `?` outputs the escaped form | `s` |
| integers (Table 107) | `b B c d o x X` | `d` |
| `charT` (Table 108) | `c`; `b B d o x X` (on the corresponding unsigned value); `?` | `c` |
| `bool` (Table 109) | `s`; `b B d o x X` (on the `unsigned char` value) | `s` |
| floating point (Table 110) | `a A e E f F g G` | see below |
| pointers, `nullptr_t` (Table 111) | `p P` | `p` |

Details worth noting:

- `c` for an integer converts the value to `charT` for output; if the value is outside the range of `charT`, `format_error` is thrown at run time.
- The prefix for integer `o` is `0`, but only when the value is not 0.
- For floating-point `e`, `f` and `g` without a precision, the precision defaults to 6, as with `printf`. With neither type nor precision, it is equivalent to `to_chars(first, last, value)`, giving the shortest round-trip form. So `1234567.0` prints as `1234567` with `{}` and as `1.23457e+06` with `{:g}`.
- Lowercase presentation types output `inf` and `nan`; uppercase ones output `INF` and `NAN`.
- Pointers output `0x` followed by the hexadecimal of `reinterpret_cast<uintptr_t>(value)`, and `nullptr` outputs `0x0`. Only `void*`, `const void*` and `nullptr_t` have standard formatters; an `int*` must be converted to `void*` first.
- `?` (C++23) outputs the escaped form; the rules are in [format.string.escaped], covered in [[format.formatter]].

!!! impl "libc++'s floating-point output for `{}`"
    Under the current draft, `to_chars` without a format uses fixed notation when the absolute value is in [1e-4, 1e15) (for `double`), so `std::format("{}", 1e5)` should output `100000`. libc++ in our tests outputs `1e+05`, because its `to_chars` still chooses the shorter of fixed and scientific notation by the C++17 rule (see [[charconv]]).

## Which errors are found at compile time

Compile-time checking amounts to fully parsing the format string during constant evaluation and calling the corresponding formatter's `parse` for each replacement field. So errors that depend only on the format string and argument types are all found at compile time:

| Error | When found |
|---|---|
| unmatched `{` or `}`, out-of-range *arg-id*, mixed automatic and manual numbering | compile time |
| *format-spec* not matching the type (`{:d}` with a string, `{:.2}` with an integer, `{:%H}` with `int`) | compile time |
| dynamic width or precision argument not of a standard integer type | compile time ([format.parse.ctx] ¶15) |
| negative dynamic width or precision | run time, throws `format_error` |
| integer printed with `{:c}` outside the range of `charT` | run time, throws `format_error` |
| a user formatter's `parse` throws `format_error` | compile time (when `parse` is `constexpr`) |
| the format string is a run-time value (`vformat`, `dynamic_format`) | everything deferred to run time |

## Questions

!!! question "Question 1"
    Is `std::format("{:>}", 42)` valid? What is the result?

<details markdown="1">
<summary>Answer</summary>

Valid; the result is `"42"`. With an alignment but no width, the minimum field width is 0 (¶9), so the padding width is also 0 and the alignment has no effect. The standard's example `format("{:*<}", "12")` giving `"12"` is exactly this case.
</details>

!!! question "Question 2"
    Why is `std::format("{:{}}", 1, true)` rejected at compile time, while `std::format("{:{}}", 1, -1)` is not?

<details markdown="1">
<summary>Answer</summary>

¶10 requires the argument for a dynamic width to be of a standard signed or unsigned integer type. `bool` is an integral type but belongs to neither category ([[basic.fundamental]]). This condition depends only on the argument type and is checked during compile-time parsing by `check_dynamic_spec_integral`; [format.parse.ctx] ¶15 says that when the type does not match, the call is not a core constant expression, so the consteval construction of the format string fails. A negative value depends on the run-time value, so `format_error` can only be thrown when `format` runs.
</details>

## Summary

| Rule | Source |
|---|---|
| `{{` and `}}` are escapes; a lone `{` or `}` is invalid | ¶1 |
| numbering is either all automatic (including nested fields) or all manual | ¶4 |
| the meaning of a *format-spec* is decided by the argument type's formatter | ¶5 |
| fixed option order: fill and align, sign, `#`, `0`, width, precision, `L`, type | [format.string.std] ¶1 |
| width is in terminal columns; wide characters and most emoji count as 2 | ¶2, ¶13 |
| `0` has no effect with an alignment option; infinity and NaN are not zero-padded | ¶8 |
| dynamic width and precision arguments must be of standard integer types; negative values throw at run time | ¶10 |
| string precision truncates by columns | ¶15 |
| without `L`, locale-independent; with `L`, `format` is not a constant subexpression | ¶17 |
| default floating-point output is equivalent to `to_chars(value)`, the shortest round trip | ¶24 |
