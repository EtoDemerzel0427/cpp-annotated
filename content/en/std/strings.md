---
title: Strings library
summary: "A guide to Clause 27: what the clause means by a character (char-like type), why both string and string_view take a traits parameter, what each of the four subclauses covers, and how the three string representations divide the work."
updated: 2026-10-19
---

!!! tldr
    - The characters of this clause are char-like types: any non-array, trivially copyable, standard-layout, trivially default constructible type, not just character types like `char`.
    - How characters compare, how they are copied, and how long a string is are decided by a traits class; the standard provides `char_traits` for only five character types.
    - The clause has four parts: character traits, `string_view`, `string`, and the C null-terminated string functions. Encodings and locales are not here; they are in Clause 28.
    - Three representations: a C-style string gets its length from `'\0'`; a `string_view` does not own its storage and is not guaranteed to end in `'\0'`; a `string` owns its storage and is guaranteed to end in `'\0'`.

## What a character is (¶1)

```cpp run title="char_like.cpp" ok
#include <cstdint>
#include <type_traits>

struct Glyph { std::uint16_t code; std::uint8_t attr; };

// Glyph meets all four conditions of a char-like type
static_assert(std::is_trivially_copyable_v<Glyph>);
static_assert(std::is_standard_layout_v<Glyph>);
static_assert(std::is_trivially_default_constructible_v<Glyph>);
static_assert(!std::is_array_v<Glyph>);

int main() {}
```

!!! std
    This Clause describes components for manipulating sequences of any non-array trivially copyable standard-layout type `T` where `is_trivially_default_constructible_v<T>` is true. Such types are called *char-like types*.

¶1 The element type this clause deals with must meet four conditions at once: not an array, trivially copyable, standard-layout ([[basic.types.general]]), and trivially default constructible. A type that does is a **char-like type** ([[g:char-like-type]]); its objects are char-like objects, or simply characters. `Glyph` above is a char-like type.

Each condition has a purpose:

| Condition | Purpose |
|---|---|
| Trivially copyable | `basic_string` moves elements with `traits::copy` and `traits::move`, usually just `memcpy` and `memmove`, without calling copy constructors |
| Trivially default constructible | Reserving capacity only needs to allocate storage, not run constructors one by one; the value-initialized `charT()` serves as the terminating null character |
| Standard-layout | The memory layout is C-compatible, so `data()` can be handed to C interfaces |
| Not an array | Elements must be passable, returnable and assignable by value, as in `push_back(charT)` and `traits::assign(r, d)`; arrays cannot do that |

This set is much wider than the core language's **character types** ([[g:character-type]]), of which there are only seven: `char`, `signed char`, `unsigned char`, `char8_t`, `char16_t`, `char32_t`, `wchar_t`.

To go into a `basic_string`, though, a type also needs a matching traits class that describes the character semantics: how to compare for equality, how to compute a length, what value represents end-of-file ([[char.traits]]). The standard provides `char_traits` specializations only for the five types `char`, `char8_t`, `char16_t`, `char32_t`, `wchar_t`; the primary `char_traits` template is only declared. So `std::basic_string<unsigned char>` fails to compile with libc++ in our tests, with the error `implicit instantiation of undefined template 'std::char_traits<unsigned char>'`.

[char.traits.general] uses a different term: **character container type** ([[defns.character.container]]), meaning the character type that a traits class describes. The two terms refer to the same set of types in practice; one names them by what can go into a string, the other by whom the traits serve.

## The four subclauses (¶2)

| Subclause | Header | Contents | Notes on this site |
|---|---|---|---|
| [char.traits] | `<string>` | The character traits requirements and the five `char_traits` specializations | [[char.traits]] |
| [string.view] | `<string_view>` | `basic_string_view`, a read-only view that does not own storage | [[string.view]] |
| [string.classes] | `<string>` | `basic_string`, which owns its storage, plus non-member functions, numeric conversions, hashing, literals | [[string.classes]], [[basic.string]] |
| [c.strings] | `<cstring>` | C's `memcpy`, `strlen`, `strtok` and so on | [[c.strings]] |

`<cwchar>`, `<cuchar>`, `<cctype>` and `<cwctype>` are not in this clause. They involve multibyte encodings and locales, and live in [[text.c.strings]] in Clause 28. Clause 28 also contains `<locale>`, `<format>`, `<charconv>` and `<text_encoding>`. This clause is only about managing a sequence of characters, not about what text those characters encode.

## Three string representations

| | Owns storage | Ends in `'\0'` | Where the length comes from | Typical source |
|---|---|---|---|---|
| Null-terminated byte string ([[g:ntbs]], [[byte.strings]]) | Not necessarily | Yes, by definition | Linear scan with `strlen` | String literals, C interfaces |
| `basic_string_view` | No | Not guaranteed | Stored length | Any contiguous character sequence |
| `basic_string` | Yes | Yes ([[basic.string.general#3]]) | Stored length | Itself |

Most of the pitfalls in this clause follow from this table:

- passing a `string_view`'s `data()` to a C interface that expects a null-terminated string, when there may be no `'\0'` at the end ([[string.view]]);
- pointing a `string_view` at a temporary `string`, which leaves the view dangling once the `string` is destroyed, because the view does not own the storage ([[string.view]]);
- continuing to use an old `c_str()` pointer after the `string` grows, when the storage may have been replaced (the invalidation rules in [[basic.string]]);
- using `memcpy` on overlapping ranges; the C functions check nothing ([[c.strings]]).

Reading this clause also relies on these core language rules: temporary object lifetime ([[class.temporary]]), which causes most `string_view` dangling problems; string literals ([[lex.string]]) and user-defined literals ([[over.literal]]), since `"abc"`, `"abc"s` and `"abc"sv` all have different types; and implicit object creation ([[intro.object]]), on which the semantics of `memcpy` in C++ depend.

## Main changes by version

| Version | Change |
|---|---|
| C++11 | Copy-on-write `basic_string` forbidden: the data race rules and the requirement that `operator[]` not invalidate iterators effectively rule out reference-counted implementations; `char16_t` and `char32_t` specializations; `to_string`, `stoi` |
| C++17 | `basic_string_view` ([[P0254R2]] integrates it with `basic_string`); `char_traits` members become `constexpr` ([[P0426R1]]) |
| C++20 | `char8_t` and `u8string` ([[P0482R6]]); `constexpr` `basic_string` ([[P0980R1]]); `starts_with`, `ends_with` ([[P0457R2]]); `<=>` ([[P1614R2]]) |
| C++23 | `contains` ([[P1679R3]]); `resize_and_overwrite` ([[P1072R10]]); construction from `nullptr` forbidden ([[P2166R1]]); the range constructor of `string_view` ([[P1989R2]], later made `explicit` by [[P2499R0]]); `substr() &&` ([[P2438R2]]) |
| C++26 | Direct concatenation of `string` and `string_view` ([[P2591R5]]); `to_string` defined in terms of `format("{}")` ([[P2587R3]]); the preconditions of `operator[]`, `front`, `back` and others become hardened preconditions ([[P3471R4]]) |

The current draft also has some post-C++23 additions: `subview`, which returns a `string_view` ([[P3044R2]]), and `memset_explicit`, `strdup` and others added to `<cstring>` along with C23.
