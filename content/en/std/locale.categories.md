---
title: Standard locale categories and facets
summary: "The standard facets of the six locale categories: ctype's character classification and the table-driven ctype<char> specialization, codecvt's encoding conversion, num_get/num_put parsing and formatting modeled on strtol/printf, numpunct, collate, time, monetary and messages."
updated: 2026-10-19
---

!!! tldr
    - Every standard facet forwards a public non-virtual member `f()` to a protected virtual function `do_f()`; to customize, override `do_f()`.
    - `istream >> int` is actually done by `num_get`: it picks a `strtol`-style conversion from the stream flags, collects characters one at a time, and then checks digit grouping; on overflow it stores the maximum or minimum value and sets `failbit`.
    - `ostream << int` is done by `num_put`: it takes what `printf` would output in the `"C"` locale, substitutes the locale's decimal point and thousands separator, pads to `width()`, and resets `width` to zero.
    - `ctype<char>` is a table-driven explicit specialization; swap in a different classification table and you change which characters `>>` treats as whitespace.
    - The string returned by `numpunct::grouping()` is used as an array of integers: `"\3"` means groups of 3 digits, and `"3"` means groups of 51.

## Common conventions [locale.categories.general]

Every standard facet has the same structure:

```cpp
template<class charT>
class numpunct : public locale::facet {
public:
  charT decimal_point() const;            // only does return do_decimal_point();
  static locale::id id;
protected:
  ~numpunct();                            // protected: can only be destroyed via a locale
  virtual charT do_decimal_point() const; // where the semantics are specified
};
```

Public members only forward; the semantics are specified on the protected virtual functions, and customization means deriving and overriding them (see [[localization]]). Most facets also have a `_byname` derived class that implements a region's rules by locale name. Below, when a member is mentioned, it refers to the semantics of the corresponding virtual function.

¶1 Facets responsible for formatting and parsing provide `put()` and `get()` members, used by iostreams' `<<` and `>>`. They take an `ios_base&`, read the format from its `flags()`, `precision()` and `width()`, and call its `getloc()` when they need other facets. Formatting facets pad to the width with the `fill` argument.

¶2 `put()` reports no errors; failure of the output iterator can be seen from the returned iterator (for example `ostreambuf_iterator::failed()`). `get()` takes an `ios_base::iostate&`, ignores its previous value, and sets `failbit` on a parse error.

¶3 Whether one virtual function calls another is unspecified ({{unspec}}). So if you override `num_get::do_get(…, long&)`, you cannot count on the other `do_get` overloads forwarding to it.

## The ctype category [category.ctype]

### `ctype<charT>`: character classification and conversion

[category.ctype.general] ¶1 `ctype_base::mask` is a bitmask type ([[bitmask.types]]) with elements `space`, `print`, `cntrl`, `upper`, `lower`, `alpha`, `digit`, `punct`, `xdigit` and `blank`, plus the combinations `alnum = alpha | digit` and `graph = alnum | punct`.

[locale.ctype.general] ¶1 `ctype<charT>` encapsulates the functionality of `<cctype>`, and istreams must use it to classify characters when parsing input. Its members ([locale.ctype.virtuals]):

- `is(m, c)` and the bulk version `is(low, high, vec)` classify characters; `scan_is` and `scan_not` find the first character that does or does not match `m` (¶1–¶6).
- `toupper` and `tolower` are one-to-one mappings that return the character unchanged when there is no counterpart (¶7–¶10).
- `widen(c)` applies "the simplest reasonable transformation" to a `char` to get a `charT` (¶11). Only characters of the basic character set ([[lex.charset]]) are required to transform uniquely, and the transformation must not add classifications to a character: `ctc.is(M, c) || !is(M, do_widen(c))` is always true.
- `narrow(c, dfault)` is the reverse transformation, returning `dfault` when no transformation is possible (¶13–¶14). For characters of the basic character set, `widen` followed by `narrow` returns the original character; for any digit character `c`, `do_narrow(c, dfault) - '0'` is its numeric value, which is exactly how `num_get` recovers values from wide-character digits.

A footnote explains that the parameter of `do_widen` is designed to receive the values of character literals: `widen('0')` converts `'0'` in the literal encoding to the corresponding character in the locale's encoding. This is where, inside the C++ library, the literal encoding meets the execution environment's encoding described in [[text]].

### `ctype<char>`: a table-driven implementation [facet.ctype.special]

```cpp run title="comma-whitespace.cpp" ok
#include <cassert>
#include <locale>
#include <sstream>
#include <vector>

// make >> treat commas as whitespace too
struct comma_ws : std::ctype<char> {
    static const mask* make_table() {
        static std::vector<mask> t(classic_table(), classic_table() + table_size);
        t[','] |= space;
        return t.data();
    }
    comma_ws() : std::ctype<char>(make_table()) {}
};

int main() {
    std::istringstream in("1,2, 3");
    in.imbue(std::locale(in.getloc(), new comma_ws));
    std::vector<int> v;
    for (int x; in >> x;) v.push_back(x);
    assert((v == std::vector{1, 2, 3}));
}
```

[facet.ctype.special.general] ¶1 The standard specifies an explicit specialization `ctype<char>` so that the `char` member functions can be inlined table lookups. A footnote explains that it is written into the standard rather than left as an implementation detail because it affects the interface for deriving from `ctype<char>`. It has no virtual functions like `do_is` or `do_scan_is`; classification is decided entirely by a `mask` table:

- Constructor `ctype(const mask* tab = nullptr, bool del = false, size_t refs = 0)`: if `tab` is null, `classic_table()` is used ([facet.ctype.char.members] ¶12); if `del` is true, the destructor does `delete[] table()` ([facet.ctype.char.dtor]).
- `is(m, c)` returns `table()[(unsigned char)c] & m` ([facet.ctype.char.members] ¶5). The character is converted to `unsigned char` first, so a negative `char` does not index out of bounds, unlike `<cctype>`'s `isalpha(int)`.
- `table_size` is implementation-defined and at least 256. For values `v >= table_size`, `table()[v]` is taken to be some implementation-specific value without actually accessing the array ([facet.ctype.char.members] ¶1).
- `classic_table()` returns the classification table of the `"C"` locale ([facet.ctype.char.statics]).

The example above is the standard technique: copy `classic_table()`, modify a few entries, and pass the new table to the base class constructor.

### `codecvt`: encoding conversion [locale.codecvt]

[locale.codecvt.general] ¶1–¶3 `codecvt<internT, externT, stateT>` converts between two encodings, with `stateT` determining which pair. Table 91 requires only two specializations: `codecvt<char, char, mbstate_t>` is a degenerate conversion that does nothing; `codecvt<wchar_t, char, mbstate_t>` converts between the implementation's narrow and wide character sets. The specializations for `char16_t` and `char32_t` are in Annex [[depr.locale.category]] and are deprecated ({{deprecated}}); C++26 also removed `codecvt_utf8` and the rest of the `<codecvt>` header (see [[text]]).

The core is `do_in` (external encoding to internal) and `do_out` (the reverse); see [locale.codecvt.virtuals]:

- ¶1 Preconditions: `from <= from_end && to <= to_end` is well-defined and true; `state` is initialized if at the beginning of a sequence, or else equal to the result of converting the preceding characters.
- ¶2–¶3 Reads at most `from_end - from` source elements and writes at most `to_end - to` destination elements, stopping at a character it cannot convert. `from_next` and `to_next` always point one past the last element successfully converted.
- ¶5 and Table 93 list the return values: `ok` (done), `partial` (not everything converted), `error` (encountered a character that cannot be converted), `noconv` (the two types are the same and no conversion is needed).

¶4 is a requirement for `basic_filebuf` ([[file.streams]]): for a codecvt used by a filebuf, if converting a whole run would return `ok`, then `do_out` given only one source character, or `do_in` given only one destination position, must also return `ok`. This lets a filebuf convert one internal character at a time. Note 1 adds that, because of `state`, it may return `ok` or `partial` with `from_next == from` and `to_next != to`, for example when only a shift sequence was output.

Other members: `do_unshift` outputs the characters needed to end the shift state (¶7–¶9); `do_encoding()` returns the number of external characters per internal character, with -1 meaning a state-dependent encoding and 0 meaning variable length (¶10); `do_always_noconv()`, `do_length()`, `do_max_length()` (¶11–¶15).

## The numeric category [category.numeric]

[category.numeric.general] ¶2 `num_get` and `num_put` read format flags from the `ios_base&` argument, and obtain `numpunct` (punctuation) and `ctype` (character classification) from the locale it is imbued with. ¶3 The numeric extraction and insertion operators of iostreams all go through these two facets.

### `num_get`: parsing in three stages [facet.num.get.virtuals]

```cpp run title="num-get.cpp" ok
#include <cassert>
#include <locale>
#include <sstream>
#include <string>

struct grouped : std::numpunct<char> {
protected:
    char do_thousands_sep() const override { return '\''; }
    std::string do_grouping() const override { return "\3"; }
};

int main() {
    int v = -1;
    std::istringstream a("1,234");                 // classic locale: ',' is not part of the number
    a >> v;
    assert(v == 1 && a.peek() == ',');

    std::locale loc(std::locale::classic(), new grouped);
    std::istringstream b("1'234'567");
    b.imbue(loc);
    b >> v;
    assert(v == 1234567 && b.eof() && !b.fail());

    std::istringstream c("12'34");                 // separator positions disagree with grouping
    c.imbue(loc);
    c >> v;
    assert(v == 1234 && c.fail());                 // the value is stored anyway, but failbit is set

    bool f = false;
    std::istringstream d("2");                     // without boolalpha only 0/1 are valid
    d >> f;
    assert(f == true && d.fail());

    int big = 7;
    std::istringstream e("99999999999");
    e >> big;
    assert(big == 2147483647 && e.fail());         // overflow: stores the maximum and sets failbit
}
```

¶2–¶3 `num_get::do_get` works in three stages:

1. **Determine the conversion specifier.** For integers, per Table 95: `%o` if `basefield == oct`, `%X` if `== hex`, `%i` if `basefield == 0` (detecting the base from a `0x` or `0` prefix), otherwise `%d` for signed types and `%u` for unsigned types. Floating point always uses `%g`, and `void*` uses `%p`.
2. **Collect characters one at a time.** Each `charT` read is looked up in the table obtained by `ctype::widen` of `"0123456789abcdefpxABCDEFPX+-"` and mapped back to the corresponding `char`; a character equal to `decimal_point()` is treated as `'.'`. A character equal to `thousands_sep()`, when `grouping()` is non-empty, has its position recorded and is discarded if no `'.'` has been collected yet; otherwise stage 2 ends. Any other character is collected if it could be the next character of input accepted by the specifier from step 1; otherwise collection stops. Example 1: for input `"0x1a.bp+07p"`, `%d` collects only `"0"`, `%i` collects `"0x1a"`, and `%g` collects `"0x1a.bp+07"`.
3. **Convert and store.** The collected characters are converted with `strtoll`, `strtoull`, `strtof`, `strtod` or `strtold`:

| Case | Stored in `val` | `err` |
|---|---|---|
| The conversion function does not convert the entire field | 0 | `failbit` |
| Signed integer, value too large (too small) | the largest (smallest) representable value | `failbit` |
| Unsigned integer, value not representable | the largest representable value | `failbit` |
| Otherwise | the converted result | unchanged |

¶4 Grouping is then checked: if the positions of the discarded separators disagree with `grouping()`, `failbit` is set, but the value has already been stored. ¶5 If stage 2 ended because end of input was reached, `eofbit` is also set.

¶6–¶8 The `bool` version: without `boolalpha` it parses as `long`, storing `false` for 0, `true` for 1, and `true` with `failbit` for any other value. With `boolalpha` it matches against `truename()` and `falsename()`, reading only until a unique match is determined.

`num_get`'s interface has no `int` or `short` overloads. `istream::operator>>(int&)` calls the `long` version first and then checks the range ([[istream.formatted.arithmetic]]). [category.numeric.general] ¶1 also allows implementations to delegate extraction of smaller types to larger ones.

!!! note "Compared with `from_chars`"
    On overflow, `num_get` writes the maximum or minimum value, while [[charconv]]'s `from_chars` leaves the target unmodified; `num_get` is affected by the locale's decimal point and grouping, while `from_chars` always uses the `"C"` locale. Don't mix the two sets of rules.

### `num_put`: formatting in four stages [facet.num.put.virtuals]

```cpp run title="num-put.cpp" ok
#include <cassert>
#include <iomanip>
#include <sstream>

int main() {
    std::ostringstream os;
    os << std::setw(6) << std::internal << -42 << '|' << 7;
    assert(os.str() == "-   42|7");      // padding goes after the sign; width is reset once used

    std::ostringstream h;
    h << std::showbase << std::hex << std::setw(8) << std::internal << std::setfill('0') << 255;
    assert(h.str() == "0x0000ff");       // internal: padding goes after 0x
}
```

¶2 specifies four stages, and ¶5 gives the details:

1. **Determine a `printf` conversion specifier**, giving the characters `printf(spec, val)` would output in the `"C"` locale. For integers, per Table 97: `%o` for `oct`, `%x` or `%X` for `hex`. For floating point, per Table 98: `%f` for `fixed`, `%e` for `scientific`, `%a` when both are set, otherwise `%g`. Table 100 adds modifiers: `showpos` corresponds to `+`, and `showbase` for integers and `showpoint` for floating point correspond to `#`. For floating point, `precision()` is used as the precision when `floatfield` is not `fixed | scientific`.
2. **Substitute the locale's punctuation.** Characters other than the decimal point are converted with `ctype::widen`; `thousands_sep()` is inserted according to `numpunct::grouping()`; the decimal point is replaced by `decimal_point()`.
3. **Pad.** Table 101 determines where padding goes: after for `left`, before for `right`, and after the sign or `0x` for `internal`. If the length is less than `width()`, it is padded with `fill`, and then `str.width(0)` is called. That is why `setw` applies only to the next output.
4. **Output**, doing `*out++ = c` for each character.

¶6 The `bool` version: without `boolalpha` it outputs as `int`, otherwise `truename()` or `falsename()`.

### `numpunct`: numeric punctuation [facet.numpunct]

[locale.numpunct.general] ¶1 The `numpunct<char>` and `numpunct<wchar_t>` required by Table 91 provide the formats of the `"C"` locale. ¶2 gives the format of integers and floating-point numbers as a grammar, and specifies that when parsing, if the digit portion contains no thousands separators, no grouping constraint is applied.

[facet.numpunct.virtuals] ¶1–¶2 `do_decimal_point` returns `'.'` by default, and `do_thousands_sep` returns `','`.

¶3–¶4 `do_grouping` returns a `string`, but it is used as an array of integers: `vec[i]` is the number of digits in group `i`, counting from the right; past the end, the last group repeats; `vec[i] <= 0` or equal to `CHAR_MAX` means that group is unlimited. By default it returns an empty string, meaning no grouping. A footnote specifically warns that `"\003"` means groups of 3 digits, while `"3"` has the value 51, the encoding of the character `'3'`, and would presumably be read as groups of 51.

¶5–¶6 `do_truename` and `do_falsename` return `"true"` and `"false"` by default.

## The collate category [category.collate]

[locale.collate.general] ¶1 `collate<charT>` provides string collation comparison and hashing; `locale::operator()` is implemented with it.

[locale.collate.virtuals]:

- ¶1 `do_compare` returns 1, -1 or 0. The specializations required by Table 91 do a lexicographical comparison ([[alg.lex.comparison]]), which in the `"C"` locale means comparing by code unit.
- ¶2 `do_transform` returns a sort key: comparing two sort keys lexicographically gives the same result as calling `do_compare` on the original strings. A footnote says it suits the case where one string is compared against many, and corresponds to C's `strxfrm`.
- ¶3–¶4 Strings that `do_compare` considers equal must hash the same; it is recommended that unequal strings collide with probability close to `1.0/numeric_limits<unsigned long>::max()`.

`collate_byname` implements a language's collation rules by locale name. The actual effect depends on the platform C library's `strcoll` and `wcscoll`, so the same locale name can sort differently on different platforms.

## The time category [category.time]

`time_get` parses a character sequence into a `tm`, and `time_put` formats a `tm` as a character sequence; both work with `strftime`/`strptime`-style conversion specifications. The iostream-level wrappers are the manipulators `std::get_time` and `std::put_time`.

- `time_get` provides `date_order()` (`no_order`, `dmy`, `mdy`, `ymd`, `ydm`), `get_time`, `get_date`, `get_weekday`, `get_monthname`, `get_year`, and `get(s, end, f, err, t, fmt, fmtend)`, which parses according to a format string. [locale.time.get.general] ¶2 sets `eofbit` when the end is reached mid-parse. [locale.time.get.virtuals] ¶9 Whether two-digit years are accepted, and which century they belong to, is implementation-defined; ¶15 whether intermediate state is kept across multiple `do_get` calls so that fields can be combined is unspecified.
- `time_put::put` processes the conversion specifications in the format string one by one ([locale.time.put.members] ¶1); `do_put` outputs according to `strftime`'s rules ([locale.time.put.virtuals] ¶1), and it is recommended that the modifiers `E` and `O` be interpreted as in POSIX (¶3).

C++20 `<chrono>` formatting ([[time.format]]) follows the `std::format` route and uses the locale only with the `L` option.

## The monetary category [category.monetary]

[category.monetary.general] ¶1 The monetary category has `money_get`, `money_put` and `moneypunct<charT, Intl>`, where `Intl` selects local or international format (such as `$` versus `USD `).

[locale.moneypunct.general] ¶1–¶2 `moneypunct` provides `curr_symbol`, `positive_sign`, `negative_sign`, `frac_digits`, and `pos_format` and `neg_format`. A format is a `pattern` of four components: `symbol`, `sign` and `value` each appear once, and the fourth is `space` or `none`.

[locale.money.get.virtuals]:

- ¶1 `money_get::do_get` always parses with the `neg_format()` pattern. The result is an integer in the smallest currency unit; Example 1: in a US locale, `$1,056.23` gives `105623`, or the digit string `"105623"`.
- ¶2 Without `showbase`, the currency symbol is optional.
- ¶3 The first character of the sign string is matched at the `sign` position, and the remaining characters are required after all other components. Example 2 uses `"()"` for negative numbers, so the closing parenthesis in `"(100 L)"` must come last.

[locale.money.put.virtuals] ¶1 `money_put` outputs using `neg_format` or `pos_format` depending on the sign of the value, and calls `str.width(0)` afterwards; ¶3 the currency symbol is output only if `showbase` is set.

## The messages category [category.messages]

`messages<charT>` is an abstraction over message catalogs (such as POSIX `catgets`): `open(name, loc)` yields a `catalog`, returning a negative value on failure; `get(cat, set, msgid, dfault)` retrieves a message, returning `dfault` if not found; `close(cat)` releases resources.

How names map to catalogs, and how `(set, msgid)` maps to messages, are both implementation-defined ([locale.messages.virtuals] ¶1, ¶5). Calling `get` or `close` on a `catalog` that has not been opened or has already been closed violates a precondition (¶4, ¶6). In practice few people use it; gettext-style solutions are more common.

<details class="fine" markdown="1"><summary>Remaining wording</summary>

The `Members` subclauses of each facet ([locale.ctype.members], [facet.num.get.members], [facet.numpunct.members], [locale.collate.members], [locale.time.get.members], [locale.money.get.members], [locale.messages.members] and so on) only specify that the public members return the result of the corresponding `do_` virtual function.

The `_byname` subclauses ([locale.ctype.byname], [locale.codecvt.byname], [locale.numpunct.byname], [locale.collate.byname], [locale.time.get.byname], [locale.time.put.byname], [locale.moneypunct.byname], [locale.messages.byname]) only give class definitions; their semantics are specified uniformly by [locale.facet] ¶5.

[facet.ctype.char.virtuals] ¶1 The virtual functions of `ctype<char>` such as `do_toupper` are described the same as the same-named functions in the general template.

[locale.ctype.general] ¶2 `ctype<char>` and `ctype<wchar_t>` implement classification appropriate to the native character set.

</details>

## Common misconceptions

!!! pitfall "Overriding one `do_get` overload, and it has no effect"
    `num_get` has no `int` or `short` overloads; `istream::operator>>(int&)` calls the `long` version. And [locale.categories.general] ¶3 says whether one virtual function calls another is unspecified. When customizing `num_get`, override all the relevant overloads.

!!! pitfall "Assuming `ctype<wchar_t>::toupper` does full Unicode case conversion"
    `ctype`'s case conversion is one-to-one per character. One-to-many or language-dependent mappings, such as `ß` to `SS` or Turkish `i` to `İ`, cannot be expressed.

## Summary

| Category | Main facets | One thing to remember |
|---|---|---|
| ctype | `ctype`, `codecvt` | `ctype<char>` is a table-driven explicit specialization; filebuf requires codecvt to convert one character at a time |
| numeric | `num_get`, `num_put`, `numpunct` | parsing is `strtol` plus a grouping check, storing extreme values on overflow; `grouping` is an array of integers |
| collate | `collate` | lexicographical by default; `transform` produces sort keys |
| time | `time_get`, `time_put` | `strftime`/`strptime` style; whether multiple `do_get` calls combine is unspecified |
| monetary | `money_get`, `money_put`, `moneypunct` | parsing always uses `neg_format`; results are in the smallest currency unit |
| messages | `messages` | all mappings are implementation-defined |
