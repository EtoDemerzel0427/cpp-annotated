---
title: Identifying text encodings
summary: "C++26's std::text_encoding identifies an encoding by the IANA Character Sets registry: a MIB number, a loosely compared name, and a list of aliases; literal() gives the literal encoding at compile time and environment() the environment's encoding at run time; it identifies encodings but does not convert."
updated: 2026-10-19
---

!!! tldr
    - `std::text_encoding` is a small value type: an IANA registration number (MIB) plus a name of at most 63 characters; it is trivially copyable and does not allocate.
    - Names are compared loosely by the rules of Unicode UTS #22, so `"UTF-8"`, `"utf8"` and `"u.t.f-008"` all correspond to `text_encoding::UTF8`.
    - `literal()` is `consteval` and returns the ordinary literal encoding; `environment()` returns the process environment's encoding at run time and is not affected by `setlocale`.
    - An unregistered name yields `id::other`; two `other`s compare by name, otherwise only the MIB is compared.
    - It only identifies encodings; the standard library still has no Unicode transcoding facility.

## Why it is needed

Before C++26, a program that wanted to know what encoding its string literals used, or what encoding the runtime environment used, had to rely on compiler macros and platform interfaces like `nl_langinfo(CODESET)` and `GetACP()`, and the names it got were all over the place: `UTF-8`, `utf8`, `65001`.

C++26's `<text_encoding>` ([[P1885R12]]) uses the IANA Character Sets registry as a uniform naming of encodings: each registered encoding has a MIB number (UTF-8 is 106), corresponding to an enumerator of the enumeration `text_encoding::id`. It offers three query points: `literal()` gives the ordinary literal encoding ([[lex.charset]]), `environment()` gives the execution environment's encoding ([[character.seq]]), and `std::locale::encoding()` gives a locale's encoding ([[locale.members#7]]). How these encodings differ is covered in [[text]].

```cpp run title="text-encoding.cpp" ok
#include <algorithm>
#include <cassert>
#include <cstring>
#include <ranges>
#include <string_view>
#include <text_encoding>

int main() {
    using te = std::text_encoding;

    constexpr te a("u.t.f-008");
    static_assert(a.mib() == te::UTF8);                       // loose matching
    static_assert(std::string_view(a.name()) == "u.t.f-008"); // the name is stored as given

    te b("x-my-enc"), c("X_MY_ENC");
    assert(b.mib() == te::other && b == c);               // both other: compared by name
    assert(b == te::other && !(b == te("x-other")));      // == other is not an equivalence relation

    te sjis(te::ShiftJIS);
    assert(sjis != te(te::Windows31J));                   // two non-interchangeable registered encodings
    assert(std::strcmp(sjis.aliases().front(), "Shift_JIS") == 0);  // front() is the primary name

    auto ascii = te(te::ASCII).aliases();
    assert(std::ranges::contains(ascii, std::string_view("ASCII")));  // alias required by the standard

    te u;                                                 // default construction
    assert(u.mib() == te::unknown && *u.name() == '\0');
}
```

## The shape of the class [text.encoding.overview]

```cpp
struct text_encoding {
  static constexpr size_t max_name_length = 63;
  enum class id : int_least32_t { /* see below */ };
  using enum id;                       // so you can write text_encoding::UTF8
  // ...
private:
  id   mib_ = id::unknown;                     // exposition only
  char name_[max_name_length + 1] = {0};       // exposition only
};
```

The exposition-only members show its implementation model: a MIB number plus an embedded name array, with no dynamic allocation. ¶2 specifies that it is a trivially copyable type ([[basic.types.general]]): it can be `memcpy`'d, placed in shared memory, or made a `constexpr` variable. `using enum id;` ([[enum.udecl]]) brings all the enumerators into class scope, so `text_encoding::UTF8` and `text_encoding::id::UTF8` are the same value.

## Registered encodings and aliases [text.encoding.general]

¶1 A **registered character encoding** ([[g:registered-character-encoding|registered character encoding]]) is a character encoding scheme in the IANA Character Sets registry. Note 1 points out that the registry calls them character sets, but they are actually encodings. The name the registry gives is the encoding's primary name.

¶2 The known registered encodings are all those in the registry except NATS-DANO (33) and NATS-DANO-ADD (34). These two have no enumerators, so the enumeration jumps straight from 32 to 35.

¶3–¶4 Each known registered encoding corresponds to an enumerator of `id` and has a set of aliases. The alias set is a superset of the aliases listed by IANA, with the details implementation-defined ({{impl}}). The standard additionally requires only that the aliases of US-ASCII include `"ASCII"`, and guarantees that the primary names and aliases of different encodings are not equal under *comp-name* (see below), so looking up by name gives a unique result.

¶5 How a `text_encoding` object is determined to represent an encoding of the translation or execution environment is implementation-defined.

¶6 Whenever `mib()` is neither `unknown` nor `other`, two invariants hold: `name()` is non-empty (¶6.1); and `text_encoding(e.name()).mib() == e.mib()`, that is, the name maps back to the same MIB (¶6.2).

¶7 Implementations are recommended not to treat distinct registered encodings as interchangeable (Example 1: Shift_JIS and Windows-31J are two encodings), and not to use the name of a registered encoding to describe a similar but different unregistered encoding unless there is precedent on that implementation (Example 2: Big5, which historically differed greatly across platforms).

## Construction and access [text.encoding.members]

### Construction from a name (¶1–¶2)

```cpp
constexpr explicit text_encoding(string_view enc) noexcept;
```

¶1 Preconditions: `enc` is represented in the ordinary literal encoding and contains only characters of the basic character set ([[lex.charset]]); its length is at most 63; it contains no `'\0'`. Violating any of these is {{ub}}.

¶2 If the primary name or an alias of some known registered encoding compares equal to `enc` under *comp-name*, `mib_` takes that encoding's enumerator value; otherwise `mib_ == id::other`. Either way, `name_` stores a verbatim copy of `enc`, not the normalized primary name. So `text_encoding("u.t.f-008").name()` returns `"u.t.f-008"`, while `mib()` is `UTF8`.

### Construction from an `id` (¶3–¶4)

¶3 Precondition: `i` is the value of some enumerator; a value like `id{9999}` is {{ub}}. ¶4 Afterwards `mib_ == i`; if `i` is `unknown` or `other` the name is empty, otherwise `name()` is one of the encoding's aliases. The standard requires only `ranges::contains(aliases(), name())`, not that it be the primary name.

### `mib()`, `name()`, `aliases()` (¶5–¶10)

¶5–¶7 `mib()` returns `mib_`. `name()` returns `name_`, an [[g:ntbs]]; accessing elements outside `name()+[0, strlen(name())+1)` is {{ub}}: even though the underlying array is 64 bytes, you may not read past the terminating null.

¶8–¶10 `aliases()` returns an `aliases_view`. If `*this` represents a known registered encoding, its `front()` is the primary name, the range contains all the aliases, and there are no duplicates by `strcmp`; otherwise it is an empty range. Each element is a non-empty ntbs containing only characters of the basic character set, and the order of the aliases is unspecified (Note 1).

### `literal()` (¶11–¶12)

```cpp
static consteval text_encoding literal() noexcept;
```

¶11–¶12 Requires `CHAR_BIT == 8` and returns an object representing the ordinary literal encoding. It is a `consteval` immediate function, callable only during constant evaluation, because the literal encoding is a property fixed at translation time anyway.

!!! impl "How libc++ learns the literal encoding"
    libc++ reads the compiler's predefined macros: GCC's `__GNUC_EXECUTION_CHARSET_NAME`, or Clang's `__clang_literal_encoding__` (`"UTF-8"` with Clang 23 in our tests). If neither exists, it returns a default-constructed `text_encoding`, that is, `unknown`.

### `environment()` and `environment_is<i>()` (¶13–¶18)

¶13–¶14 Requires `CHAR_BIT == 8` and returns an object representing the execution environment's encoding; which one is implementation-defined. On POSIX implementations, it is the encoding associated with the POSIX locale denoted by the empty string `""`, that is, the one determined by the `LC_ALL`, `LC_CTYPE` and `LANG` environment variables.

!!! std
    This function is not affected by calls to setlocale.

¶15 Note 2: it is not affected by `setlocale`. ¶16 further recommends that the return value also not be affected by functions that modify the environment, such as POSIX `setenv`.

¶17–¶18 `environment_is<i>()` returns `environment() == i`. Taking the `id` as a template argument lets implementations provide fast paths for common encodings that skip table lookups.

!!! impl "libc++ does not follow the recommendation in ¶16"
    libc++ reconstructs the POSIX locale from `""` and queries its encoding on every call to `environment()`. In our tests, it prints `US-ASCII` at program startup; after `setlocale(LC_ALL, "en_US.UTF-8")` it is still `US-ASCII`, consistent with Note 2; after `setenv("LC_ALL", "en_US.UTF-8", 1)` it becomes `UTF-8`. ¶16 is only a recommendation, so this is not non-conforming, but portable code should rely on neither behavior. On macOS, `environment()` needs the LLVM 23 libc++ shared library (see [[text]] for the availability annotations).

### *comp-name*: loose name comparison (¶19)

¶19 Two names are equal if and only if they are the same after ignoring, from left to right:

1. all characters that are neither letters nor digits (¶19.1);
2. case (¶19.2);
3. any sequence of `0`s not immediately following a numeric prefix, where a numeric prefix is a digit 1 to 9, optionally followed by non-alphanumeric characters (¶19.3).

Note 3 says this is the Charset Alias Matching algorithm of UTS #22. Rule 3 removes leading zeros: in `utf-008`, the `00` is preceded by `-` and before that by the letter `f`, which do not form a numeric prefix, so they are ignored, giving `utf8`; in `utf-80`, the `0` follows the digit `8` and is kept, giving `utf80`. Example 1 in the standard:

| a | b | Result |
|---|---|---|
| `"UTF-8"` | `"utf8"` | true |
| `"u.t.f-008"` | `"utf8"` | true |
| `"ut8"` | `"utf8"` | false |
| `"utf-80"` | `"utf8"` | false |

## Comparison [text.encoding.cmp]

¶1 When two `text_encoding`s are compared, if both are `other` their names are compared with *comp-name*; otherwise only the MIBs are compared. So two unregistered encodings named `"x-my-enc"` and `"X_MY_ENC"` are equal, and `text_encoding("utf8") == text_encoding(text_encoding::UTF8)` is also true despite the different names.

¶2–¶3 Comparison with an `id` compares only the MIB. ¶3 points out that when `i == id::other` this operator is not an equivalence relation: `a == other` and `b == other` both being true does not imply `a == b`, since the names may differ.

## `aliases_view`, the `id` enumeration, and hashing

[text.encoding.aliases] ¶1–¶3 `aliases_view` is a copyable `view` that is a `random_access_range` and a `borrowed_range`. The alias strings live in a static table, so iterators remain valid after the view is destroyed. Note 1 points out that it is not required to be a `common_range` or default constructible. Its value type and reference type are both `const char*`; its iterators are constexpr iterators, so aliases can be traversed in constant expressions.

[text.encoding.id] The underlying type of `id` is `int_least32_t`. `other = 1` and `unknown = 2`; the other enumerator values are the IANA MIB numbers, such as `ASCII = 3`, `UTF8 = 106`, `GB18030 = 114` and `UTF16 = 1015`. Note 1 explains the naming rule: take the alias in the registry that begins with `cs` and drop the prefix; the exceptions are `csUnicode`, which corresponds to `UCS2`, and `csIBBM904` (a misspelling in the registry), which corresponds to `IBM904`.

[text.encoding.hash] ¶1 `hash<text_encoding>` is enabled ([[unord.hash]]), so `text_encoding` can be used directly as a key in unordered containers.

## Common misconceptions

!!! pitfall "Assuming an alias is recognized on every implementation"
    The alias set is an implementation-defined superset, and apart from `"ASCII"` the standard requires no extra aliases. A name recognized as a registered encoding on implementation A may yield only `other` on implementation B. When exchanging encoding information across platforms, pass the MIB number (`std::to_underlying(e.mib())`) or the primary name (`aliases().front()`).

!!! pitfall "Assuming `name()` returns the canonical name"
    When constructed from a name, `name()` stores the given string verbatim. Use `aliases().front()` when you need the canonical primary name.

## Summary

| Interface | When evaluated | Question answered |
|---|---|---|
| `text_encoding::literal()` | `consteval` | What encoding do ordinary literals use? ([[lex.charset]]) |
| `text_encoding::environment()` | run time | What encoding does the process environment use? (On POSIX, the `""` locale; not affected by `setlocale`) |
| `std::locale::encoding()` | run time | What encoding does this `std::locale` object use? ([[locale.members]]) |
| `text_encoding(string_view)` | `constexpr` | Which registered encoding does this name correspond to? `other` if unregistered |
