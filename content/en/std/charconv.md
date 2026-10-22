---
title: Primitive numeric conversions
summary: "to_chars and from_chars in <charconv>: locale-independent, non-throwing conversions between numbers and text that write into the caller's buffer, including the shortest round-trip guarantee for floating point and the three outcomes of from_chars."
updated: 2026-10-19
---

!!! tldr
    - `to_chars` and `from_chars` always work as in the `"C"` locale, never throw, never allocate, and write into a buffer the caller supplies; `to_chars` does not write a terminating `'\0'`.
    - Without a precision, floating-point `to_chars` outputs the shortest string that `from_chars` reads back exactly; for example, `0.1` prints as `"0.1"`.
    - `from_chars` does not skip leading whitespace, does not accept `+` or a `0x` prefix, and reads only the matching prefix; on failure or overflow it leaves the target variable unmodified.
    - The integer versions are `constexpr` since C++23; since C++26 both result types can be tested directly in an `if`.

## Why `<charconv>`

```cpp run title="roundtrip.cpp" ok
#include <cassert>
#include <charconv>
#include <string_view>

int main() {
    char buf[64];
    for (double v : {0.1, 1.0 / 3, 1e23, 5e-324}) {
        auto [end, ec] = std::to_chars(buf, buf + sizeof buf, v);
        assert(ec == std::errc{});
        double back = 0;
        auto r = std::from_chars(buf, end, back);
        assert(r && r.ptr == end && back == v);   // exact round trip on the same implementation
    }
    auto r = std::to_chars(buf, buf + sizeof buf, 0.1);
    assert(std::string_view(buf, r.ptr) == "0.1");  // shortest: not 0.10000000000000001
}
```

Before `<charconv>`, there were several ways to write a `double` as text and read it back, each with flaws: `printf("%.17g")` round-trips but is not short, turning `0.1` into `0.10000000000000001`; `printf`, `strtod` and iostreams are all affected by the locale, so in a German environment the decimal point becomes a comma; `to_string` allocates.

`to_chars`/`from_chars` (C++17, [[P0067R5]]) are the lowest-level conversion facilities in the standard library. They recognize only the `"C"` locale, report failure through the return value, and their interface involves no memory allocation. [[format]]'s default output for arithmetic types is also defined in terms of `to_chars` ([[format.string.std#20]]).

## Result types and `chars_format` [charconv.syn]

Both functions return a simple struct:

```cpp
struct to_chars_result {              // from_chars_result is the same, except ptr is const char*
  char* ptr;
  errc ec;
  friend bool operator==(const to_chars_result&, const to_chars_result&) = default;
  constexpr explicit operator bool() const noexcept { return ec == errc{}; }   // C++26
};
```

¶3 These two types have only the members listed above and no base classes. So they are aggregates and can be unpacked with a structured binding, `auto [p, ec] = ...`. C++26's [[P2497R0]] added `explicit operator bool`, so you can write `if (auto r = std::from_chars(...))`. It is `explicit`, so `bool ok = r;` is still ill-formed; it can be used only where the result is [[g:contextually-converted-to-bool|contextually converted to bool]], such as the condition of an `if`.

¶1 In the synopsis, *integer-type* means the implementation provides one overload each for `char` and every signed and unsigned integer type; *floating-point-type* means one for each cv-unqualified floating-point type, including extended floating-point types ([[basic.fundamental]]). `bool` is not among them; the synopsis explicitly declares `to_chars(char*, char*, bool, int = 10)` as deleted, to keep `bool` from silently selecting the `int` overload through integral promotion.

¶2 `chars_format` is a bitmask type ([[bitmask.types]]) with elements `scientific`, `fixed` and `hex`; the synopsis also defines `general = fixed | scientific`. When parsing, `from_chars` decides whether the exponent part must appear based on which bits are set (see below).

## Numbers to text: `to_chars` [charconv.to.chars]

### Success and failure (¶1)

¶1 On success, `ec` equals a value-initialized `errc`, that is `errc{}` (value 0, which is not any named enumerator), and `ptr` points one past the last character written. There is only one failure case: the buffer is too small, in which case `ec == errc::value_too_large`, `ptr == last`, and the contents of `[first, last)` are unspecified; it may be half written.

`to_chars` does not write a terminating `'\0'`. `[first, last)` must be a valid range, otherwise the behavior is {{ub}}.

### Integers (¶4–¶6)

```cpp run title="to-chars-int.cpp" ok
#include <cassert>
#include <charconv>
#include <string_view>

constexpr std::string_view hex(unsigned v, char (&buf)[16]) {
    auto r = std::to_chars(buf, buf + 16, v, 16);
    return {buf, r.ptr};
}

int main() {
    char buf[16];
    assert(hex(255, buf) == "ff");                       // lowercase, no prefix
    auto r = std::to_chars(buf, buf + 3, 12345);         // buffer too small
    assert(r.ec == std::errc::value_too_large && r.ptr == buf + 3);
    static_assert([] { char b[16]; return hex(48879, b) == "beef"; }());   // usable in constant evaluation since C++23
}
```

¶4 The precondition is that `base` is between 2 and 36; violating it is {{ub}}.

¶5 The output has no redundant leading zeros; digits 10 to 35 are the lowercase letters `a` to `z`; negative numbers begin with `'-'`. There is no `+` sign and no prefix like `0x` or `0b`.

The integer overloads are `constexpr` since C++23 ([[P2291R3]]), which is why the example above can use them in a `static_assert`.

### Shortest round trip for floating point (¶2)

!!! std
    The functions that take a floating-point value but not a precision parameter ensure that the string representation consists of the smallest number of characters such that there is at least one digit before the radix point (if present) and parsing the representation using the corresponding `from_chars` function recovers `value` exactly.

¶2 Floating-point `to_chars` without a precision parameter gives three layers of guarantee:

1. Round trip: reading it back with the corresponding `from_chars` yields a value exactly equal to the original. Note 1 cautions that this is guaranteed only between `to_chars` and `from_chars` of the same implementation.
2. Shortest: among all representations that round-trip, the one with the fewest characters. There must be at least one digit before the radix point, so `.5` is not a candidate.
3. Ties: if several candidates are equally short, the one with the smallest difference from the value; if still tied, rounded according to `round_to_nearest` ([[round.style]]).

"Shortest" here is compared within the chosen format, which is determined by the rules in the next section or by the `fmt` argument. Mainstream implementations meet this guarantee with Ryu-style algorithms.

### Choosing the floating-point format (¶3, ¶7, ¶10, ¶13)

¶3 Overloads with a `chars_format` parameter choose a `printf` conversion specifier according to `fmt`: `fixed` corresponds to `%f`, `scientific` to `%e`, `hex` to `%a` (but without the `0x` prefix), and `general` to `%g`. All conversions are done in the style of `printf` in the `"C"` locale, so the decimal point is always `.`.

| Overload | Format | Precision |
|---|---|---|
| `to_chars(f, l, v)` (¶7) | chosen between `%f` and `%e` by magnitude | shortest round trip |
| `to_chars(f, l, v, fmt)` (¶10) | per `fmt` | shortest round trip (within that format) |
| `to_chars(f, l, v, fmt, precision)` (¶13) | per `fmt` | the given precision, as for `printf` |

¶7 The overload without `fmt` chooses by magnitude: `%f` if `|value|` is in `[l, u)`, otherwise `%e`. `l` is the smallest representable value not less than 10⁻⁴; `u` is the largest value not greater than `radix^(digits+1)`, rounded down to a power of 10. For `double`, `digits` is 53 and 2⁵⁴ is about 1.8×10¹⁶, so the interval is roughly `[1e-4, 1e16)`.

!!! impl "libc++ still chooses the format by the C++17 rule"
    The original C++17 wording chose the shorter of `%f` and `%e`, preferring `%f` on a tie. The draft later changed to the magnitude rule above, but Clang 23 + libc++ in our tests still outputs by the old rule:

    | Value | What ¶7 specifies | libc++ output |
    |---|---|---|
    | `1e4` | `10000` | `10000` |
    | `1e5` | `100000` | `1e+05` |
    | `1e15` | `1000000000000000` | `1e+15` |
    | `1e-4` | `0.0001` | `1e-04` |

    This also affects `std::format("{}", 1e5)`: [[format.string.std#24]] says floating-point output without type or precision is equivalent to `to_chars(first, last, value)`, so libc++ outputs `1e+05`. When you need a stable format, write `chars_format::fixed` or `{:f}` explicitly.

## Text to numbers: `from_chars` [charconv.from.chars]

### Three outcomes (¶1)

¶1 `from_chars` matches a pattern at the start of `[first, last)`, with three possible outcomes:

| Case | `value` | `ptr` | `ec` |
|---|---|---|---|
| No characters match | unmodified | `first` | `errc::invalid_argument` |
| Match, but the value is out of the type's range | unmodified | first non-matching character (or `last`) | `errc::result_out_of_range` |
| Match, and the value is representable | set to the parsed result (rounded per `round_to_nearest`) | first non-matching character (or `last`) | `errc{}` |

There are several differences from `strtol`. `from_chars` does not skip leading whitespace; `" 42"` gives `invalid_argument` right away. It reads only the matching prefix: `"42abc"` successfully reads 42 with `ptr` pointing at `'a'`, so if the whole string must be a number you have to check `ptr == last` yourself. On failure `value` keeps its old value, whereas `strtol` returns 0 or `LONG_MAX`.

Note 1 adds that if the pattern allows an optional sign but no digits follow the sign (as in `"-"`), this counts as no characters matching.

### The integer pattern (¶3)

```cpp run title="from-chars-int.cpp" ok
#include <cassert>
#include <charconv>
#include <string_view>

int main() {
    auto parse = [](std::string_view s, auto& v, int base = 10) {
        return std::from_chars(s.data(), s.data() + s.size(), v, base);
    };
    int v = 7;
    auto r1 = parse("+12", v);
    assert(r1.ec == std::errc::invalid_argument && v == 7);    // '+' not accepted; v unchanged

    auto r2 = parse("99999999999 tail", v);
    assert(r2.ec == std::errc::result_out_of_range && v == 7); // out of range: v unchanged
    assert(*r2.ptr == ' ');                                    // but ptr still moved past all the digits

    auto r3 = parse("0x1f", v, 16);
    assert(r3 && v == 0 && *r3.ptr == 'x');                   // 0x not recognized: only "0" is read

    unsigned u = 5;
    auto r4 = parse("-1", u);
    assert(r4.ec == std::errc::invalid_argument && u == 5);    // unsigned types do not accept '-'
}
```

¶3 The integer pattern is the form `strtol` accepts in the `"C"` locale for the given base, tightened in three ways:

1. no `0b`/`0B` prefix for base 2, and no `0x`/`0X` prefix for base 16;
2. the only sign allowed is `'-'`; `'+'` is not accepted;
3. `'-'` is allowed only if `value` has a signed type. Parsing `"-1"` into `unsigned` gives `invalid_argument`, rather than wrapping to the maximum as `strtoul` does.

### The floating-point pattern (¶6)

```cpp run title="from-chars-fp.cpp" ok
#include <cassert>
#include <charconv>
#include <string_view>

int main() {
    double d = -1;
    auto parse = [&](std::string_view s, std::chars_format f = std::chars_format::general) {
        return std::from_chars(s.data(), s.data() + s.size(), d, f);
    };
    assert(parse("0x123", std::chars_format::hex) && d == 0);   // only "0" is read
    assert(parse("1ff", std::chars_format::hex) && d == 511);   // correct without 0x
    auto r = parse("1e5", std::chars_format::fixed);
    assert(r && d == 1 && *r.ptr == 'e');                       // fixed: the exponent is not consumed
    assert(parse("15", std::chars_format::scientific).ec == std::errc::invalid_argument);
    assert(parse("1e999").ec == std::errc::result_out_of_range);
}
```

¶6 The floating-point pattern is the form `strtod` accepts, with four modifications:

- ¶6.1 `'+'` may appear only in the exponent part;
- ¶6.2 if `fmt` has `scientific` set but not `fixed`, the exponent part is required;
- ¶6.3 if `fmt` has `fixed` set but not `scientific`, there may be no exponent part; parsing stops at an `e`;
- ¶6.4 if `fmt` is `hex`, the `0x` prefix is assumed to be already present. So if the string actually contains `0x`, only `0` is parsed and `x123` is left (Example 1 in the standard).

`inf` and `nan` are still accepted according to `strtod`'s rules. The last sentence of ¶6 says the result is one of the at most two floating-point values closest to the value the string represents; combined with `round_to_nearest` in ¶1, this is correct rounding in the IEEE sense.

!!! impl "libc++ support"
    - Floating-point `from_chars` is implemented only for `float` and `double`. The `long double` overload is declared deleted, and calling it reports `call to deleted function 'from_chars'`.
    - Because floating-point support is incomplete, libc++ does not define `__cpp_lib_to_chars`; `__cpp_lib_constexpr_charconv` is defined as `202207L`.
    - Floating-point `to_chars` and `from_chars` are implemented in the shared library and controlled by availability macros, so they are unavailable for older macOS deployment targets.

## History

!!! history
    - C++17: [[P0067R5]] introduced `<charconv>`, then located in [utilities].
    - C++23: [[P2291R3]] made integer `to_chars`/`from_chars` `constexpr`. The draft was later reorganized, and this subclause moved into Clause 28 [text].
    - C++26: [[P2497R0]] added `explicit operator bool` to both result types. In the draft the integer versions are marked freestanding and the floating-point versions freestanding-deleted, meaning a freestanding implementation may define them as deleted.

## Common misconceptions

!!! pitfall "Treating `to_chars` output as a C string"
    `to_chars` does not write `'\0'`. To print with `printf("%s", buf)`, you must first do `*r.ptr = '\0'`, and leave one extra byte in the buffer for it.

!!! pitfall "Checking `ec` but not `ptr`"
    `from_chars` parsing `"12abc"` succeeds. If the semantics require the whole string to be a number, you also need to check `r.ptr == last`.

!!! pitfall "Assuming the round-trip guarantee holds across platforms"
    Note 1 to ¶2 says round-tripping is guaranteed only between `to_chars` and `from_chars` of the same implementation. Different implementations may output different shortest strings, and on the format choice in ¶7 libc++ already disagrees with the draft. When a serialization protocol needs byte-for-byte consistency across platforms, specify `fmt` explicitly, and preferably the precision too.

## Questions

!!! question "Question 1"
    What does `std::to_chars(buf, end, -0.0)` output? What about `std::format("{:+}", -0.0)`?

<details markdown="1">
<summary>Answer</summary>

`to_chars` converts in `printf` style, which keeps the sign of negative zero, so it outputs `"-0"`.

Table 105 in [[format.string.std#5]] says the `+` option inserts `+` only before numbers that are non-negative and not negative zero; the `to_chars` output of negative numbers and negative zero already carries a sign and is left alone. So the result is `"-0"`, not `"+-0"`. libc++ in our tests agrees.
</details>

!!! question "Question 2"
    Why does `from_chars`, on overflow, leave `value` unchanged and still advance `ptr`, instead of writing `LONG_MAX` as `strtol` does?

<details markdown="1">
<summary>Answer</summary>

¶1 lets the caller distinguish three things: whether there were digits (`ptr == first`), where they end (`ptr`), and whether the value is representable (`ec`). With `ptr` advanced, a parser can skip the over-long number and keep scanning. With `value` unchanged, `strtol`'s ambiguity is avoided: `LONG_MAX` could be either an error marker or legitimate input.
</details>

## Summary

| Aspect | Rule |
|---|---|
| locale | always the `"C"` locale |
| exceptions | none thrown; errors reported through `errc` |
| `to_chars` failure | `value_too_large`, `ptr == last`, buffer contents unspecified |
| floating point, no precision | shortest round trip; ties go to the closest value, then round-to-nearest |
| floating point, no `fmt` | ¶7: `%f` in `[1e-4, u)`, otherwise `%e` (libc++ still uses the old shorter-of rule) |
| `from_chars` no match | `invalid_argument`, `ptr == first`, `value` unchanged |
| `from_chars` out of range | `result_out_of_range`, `ptr` past the matched part, `value` unchanged |
| integer pattern | no leading whitespace, no `+`, no `0x`/`0b`; unsigned types do not accept `-` |
| `hex` floating point | no `0x` when reading or writing |
| C++23 / C++26 | integer versions `constexpr`; result types have `explicit operator bool` |
