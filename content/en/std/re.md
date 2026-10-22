---
title: Regular expressions library
summary: "The pattern side of <regex>: basic_regex compiles a pattern into a state machine at run time; the six grammars (modified ECMAScript by default); the two sets of bitmask options; regex_error's error codes; and how regex_traits plugs in the locale. Matching works on code units, with no Unicode semantics."
updated: 2026-10-19
---

!!! tldr
    - Constructing a `std::regex` compiles the pattern at run time, which is expensive; construct once and reuse. An invalid pattern throws `regex_error`.
    - The default grammar is ECMAScript, which takes the first alternative that succeeds; the POSIX grammars take the leftmost-longest match. The same pattern can match different text under the two.
    - Every locale-dependent decision goes through the traits object, which records the global locale at the time the regex is constructed.
    - Matching works on code units: for a UTF-8 string, `.` matches one byte, with no Unicode semantics at all.
    - Mainstream implementations use backtracking, which is slow, and nested quantifiers can cause exponential backtracking.

`<regex>` is the regular expression library C++11 standardized from Boost.Regex. This page covers the pattern side: the parts of the library, the option constants, errors, traits, `basic_regex` and the grammar. The matching side, that is `sub_match`, `match_results`, `regex_match`, `regex_search`, `regex_replace` and the two iterators, is in [[re.alg]].

## An example

```cpp run title="regex-basics.cpp" ok
#include <cassert>
#include <regex>

int main() {
  std::cmatch m;
  std::regex ecma("Get|GetValue");                         // ECMAScript by default
  std::regex posix("Get|GetValue", std::regex::extended);  // POSIX ERE
  assert(std::regex_search("GetValue", m, ecma) && m[0] == "Get");
  assert(std::regex_search("GetValue", m, posix) && m[0] == "GetValue");

  // code units only: "中" in UTF-8 is 3 chars
  assert(!std::regex_match("中", std::regex(".")));
  assert( std::regex_match("中", std::regex("...")));

  std::regex r("a+", std::regex::icase | std::regex::nosubs);
  assert(r.mark_count() == 0 && std::regex_match("AaA", r));

  std::regex ml("^b", std::regex::ECMAScript | std::regex::multiline);
  assert(std::regex_search("a\nb", ml));                  // ^ matches at line starts
  assert(!std::regex_search("a\nb", std::regex("^b")));   // ^ matches only at the beginning

  try { std::regex bad("(ab"); assert(false); }
  catch (const std::regex_error& e) {
    assert(e.code() == std::regex_constants::error_paren);
  }
}
```

This code shows, in order, the main points of this page: the different alternation semantics of the two grammars, matching by code unit, the option bitmasks, and the exception thrown for an invalid pattern.

## Components ([re.general], [re.syn])

¶2 This clause describes a regular expression class template `basic_regex` and its traits, `match_results` for holding match results, a set of algorithms, and two iterators. ¶3 says that the ECMAScript Language Specification, Ecma-262, is referred to as ECMA-262 in this clause.

`basic_regex` can be instantiated with any char-like type, but the standard requires `regex_traits` to be usable only for `char` and `wchar_t`, so it provides only the aliases `regex` and `wregex`, with the corresponding `cmatch`, `smatch`, `wcmatch`, `wsmatch` and so on. `char8_t`, `char16_t` and `char32_t` are not supported.

The synopsis in [re.syn] has a set of deleted overloads: the versions of `regex_match` and `regex_search` taking an rvalue `basic_string` plus a `match_results&`, and the constructors of `regex_iterator` and `regex_token_iterator` taking an rvalue regex, are all `= delete`. They catch at compile time cases where results would refer to a temporary; see [[re.alg]].

## Option constants ([re.const])

The `std::regex_constants` namespace provides three types: `syntax_option_type` used at construction, `match_flag_type` used at match time, and the error code type `error_type`.

### syntax_option_type ([re.synopt])

This is an implementation-defined bitmask type ([[bitmask.types]]); `basic_regex` also provides these values as static members, such as `std::regex::icase`.

¶1 A valid value sets at most one grammar among `ECMAScript`, `basic`, `extended`, `awk`, `grep` and `egrep`; if none is set, the grammar is ECMAScript. Table 118 lists all the elements:

| Element | Effect |
|---|---|
| `icase` | ignore case |
| `nosubs` | treat no subexpression as marked; `match_results` stores no submatches |
| `optimize` | ask the engine to favor matching speed over construction speed; no other observable effect |
| `collate` | ranges of the form `[a-b]` are interpreted per the locale's collation |
| `ECMAScript` | the ECMA-262 grammar, as modified in [re.grammar] |
| `basic`, `extended` | POSIX basic and extended regular expressions |
| `awk`, `grep`, `egrep` | the grammars of POSIX awk, grep and grep -E |
| `multiline` | ECMAScript only: `^` and `$` also match at line starts and ends (since C++17) |

`optimize` is only a hint. In libc++'s `<regex>` in our tests, this flag is defined and used nowhere else.

ECMAScript uses backtracking semantics and chooses the first alternative that succeeds (leftmost-first); the POSIX grammars require leftmost-longest. So in the example at the top, `Get|GetValue` on `"GetValue"` matches `"Get"` under ECMAScript and `"GetValue"` under `extended`.

### match_flag_type ([re.matchflag])

Also an implementation-defined bitmask type, passed to the matching algorithms. ¶1 says that `match_default` and `format_default` are empty bitmasks. The more commonly used entries of Table 119:

- `match_not_bol`, `match_not_eol`: treat the start and end of `[first, last)` as not at a line start or end, needed when searching within a substring;
- `match_not_null` rejects empty matches; `match_continuous` accepts only matches starting at `first`;
- `match_prev_avail`: `--first` is a valid position, so `^` and `\b` can see the previous character. `regex_iterator` adds it automatically in subsequent searches;
- `format_sed`, `format_no_copy`, `format_first_only`: control `regex_replace` and `match_results::format`. The default replacement rules come from ECMAScript's `String.prototype.replace`: `$&`, `$1`, `` $` ``, `$'`, `$$`.

### error_type and regex_error ([re.err], [re.badexp])

`error_type` is an implementation-defined enumerated type ([[enumerated.types]]); Table 120 lists 13 values: `error_collate`, `error_ctype`, `error_escape`, `error_backref`, `error_brack`, `error_paren`, `error_brace`, `error_badbrace`, `error_range`, `error_space`, `error_badrepeat`, `error_complexity`, `error_stack`.

`regex_error` derives from `runtime_error`, and `code()` returns the error code passed at construction ([re.badexp]).

## basic_regex ([re.regex])

### Construction is compilation ([re.regex.general])

¶1–¶2 A `basic_regex` object is responsible for converting a character sequence into some internal representation. What that representation is and how the matching algorithms access it are not specified; Note 1 mentions that implementations usually declare the algorithms as friends. ¶3 The functions in this subclause report errors by throwing `regex_error`.

So `std::regex re(pattern);` is a run-time compilation: it parses the pattern and builds a finite state machine. In code that constructs a regex on every call, this is the main source of cost. Construct once and reuse, for example as a `static const std::regex`.

### Construction and assignment ([re.regex.construct], [re.regex.assign])

- A default-constructed object matches no character sequence.
- It can be constructed from a `const charT*`, a pointer plus length, a `basic_string`, an iterator range or an `initializer_list`. Afterwards `flags()` returns the options passed and `mark_count()` returns the number of marked subexpressions; an invalid pattern throws `regex_error`. The options default to `ECMAScript` throughout.
- [re.regex.assign] ¶10–¶13: `assign` compiles a new pattern. The postconditions in ¶11 hold only if no exception is thrown; on an exception `*this` is unchanged, the strong exception guarantee.

`mark_count()` and `flags()` are in [re.regex.operations]; `swap` is a constant-time operation.

## traits: the only gateway to the locale ([re.req], [re.traits])

[re.grammar] ¶2 says that `basic_regex` holds a default-constructed traits object internally, which the standard calls `traits_inst`. Members of `basic_regex` may not call any locale-dependent C or C++ API; all such decisions must go through members of `traits_inst`. [re.req] specifies the operations a traits class `X` must provide:

| Expression | Purpose | Paragraphs |
|---|---|---|
| `X::length(p)` | length of a null-terminated string | ¶10–¶12 |
| `v.translate(c)`, `v.translate_nocase(c)` | map equivalent characters to the same representative | ¶13–¶16 |
| `v.transform(F1, F2)`, `v.transform_primary(F1, F2)` | generate sort keys, for ranges in `collate` mode and for equivalence classes `[[=a=]]` | ¶17–¶20 |
| `v.lookup_collatename(F1, F2)` | resolve collating elements `[[.ch.]]` | ¶21–¶22 |
| `v.lookup_classname(F1, F2, icase)`, `v.isctype(c, cl)` | character classes `[[:alpha:]]`, `\d`, `\w` | ¶23–¶26 |
| `v.value(c, I)` | value of a digit character in base 8, 10 or 16 | ¶27–¶28 |
| `u.imbue(loc)`, `v.getloc()` | set and get the locale | ¶29–¶32 |

The standard's `regex_traits<charT>` implements these with locale facets: `translate` returns its argument unchanged ([re.traits] ¶4), `translate_nocase` uses `ctype::tolower` (¶5), `transform` uses `collate::transform` (¶6), and `isctype` maps the class name to a `ctype_base::mask` and queries `ctype` (¶11–¶12). ¶10 and Table 121 list the class names that must at least be recognized: `alnum`, `alpha`, `blank`, `cntrl`, `digit`, `d`, `graph`, `lower`, `print`, `punct`, `space`, `s`, `upper`, `w`, `xdigit`.

[re.traits] ¶17–¶18 says that if `imbue` has never been called, `getloc()` returns a copy of the global locale in effect when the traits object was constructed. So a `std::regex`'s character classification and case rules are fixed at construction, and later calls to `std::locale::global` do not affect regexes already constructed.

To change the locale, call `basic_regex::imbue`. Per [re.regex.locale] ¶1, after the call the regex matches no character sequence, and the pattern must be `assign`ed again.

## Grammar ([re.grammar])

¶1 For a regex constructed with `ECMAScript`, the grammar is that of ECMA-262, with the following modifications:

- ¶3–¶5: character classes gain the POSIX-style `[[:class:]]`, `[[.collating.]]` and `[[=equiv=]]`.
- ¶7–¶11: class names are resolved through `lookup_classname`, which must recognize at least the 15 listed above; `\d`, `\s` and `\w` are equivalent to `[[:digit:]]`, `[[:space:]]` and `[_[:alnum:]]` respectively. An invalid class name makes compilation throw `regex_error`.
- ¶12: if the value of `\uXXXX` is outside what `charT` can represent, `regex_error` is thrown. For `char`, the pattern `\u4E2D` is invalid. libc++ in our tests does not throw when constructing a `std::regex` from this pattern, contrary to the wording.
- ¶14: matching semantics follow ECMA-262, modified by match flags and traits. When comparing two characters, under `icase` the results of `translate_nocase` are compared, under `collate` the results of `translate`, otherwise `==` is used directly (¶14.1). In `collate` mode, a range `c1-c2` is compared using sort keys from `transform` (¶14.2).

¶14 also explains the code unit problem from the top of this page. The library has no notion of Unicode: it compares individual `charT`s. For a UTF-8 encoded `std::string`, `.` matches one byte, `\w` classifies each byte with `ctype<char>`, and `[à-ü]` is a byte range. When processing non-ASCII text, either accept byte semantics or switch to a Unicode-aware regex engine.

## Performance

!!! impl "Why std::regex is slow"
    The standard specifies no complexity, but its specification makes a high-performance implementation hard: ECMAScript semantics (including backreferences) require backtracking; character tests go through traits and the locale; `basic_regex` is a template whose internal representation becomes part of the ABI, so implementations can hardly rewrite it without breaking ABI. libc++ and libstdc++ both use backtracking implementations, and nested quantifiers such as `(a*)*c` cause exponential backtracking. libc++ in our tests throws `error_complexity` once an internal threshold is exceeded, one of the two errors [re.except] allows the matching algorithms to throw (see [[re.alg]]).

    For untrusted input or performance-sensitive work, consider RE2, PCRE2, Hyperscan or a compile-time regex library.

## Summary

| Point | Source |
|---|---|
| The default grammar is ECMAScript; the six grammars are mutually exclusive | [re.synopt] ¶1 |
| `optimize` is only a hint | Table 118 |
| Construction is compilation; an invalid pattern throws `regex_error` | [re.regex.general] ¶3 |
| traits is the only gateway to the locale and records the global locale at construction | [re.grammar] ¶2, [re.traits] ¶17 |
| Matching is by `charT` (code unit), with no Unicode semantics | [re.grammar] ¶12, ¶14 |
