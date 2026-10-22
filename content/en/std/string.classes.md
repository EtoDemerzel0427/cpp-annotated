---
title: String classes
summary: "The parts of <string> beyond basic_string's members: type aliases, operator+, comparison, input and output, erase, stoi and to_string, hash, and the \"\"s literal."
updated: 2026-10-19
---

!!! tldr
    - `a + b + c + d` creates a new string only in the first step; every later `+` takes over the buffer of the temporary on its left and keeps appending.
    - Since C++26, `string + string_view` compiles directly; `"abc" + "def"` is still ill-formed, and `"abc" + 1` is pointer arithmetic.
    - `>>` skips leading whitespace and reads up to whitespace; `getline` does not skip whitespace, and extracts the newline without storing it. Mix the two and `getline` often reads an empty line.
    - The `stoi` family interprets strings like C's `strtol`: it skips leading whitespace, stops at a non-digit without reporting an error, and `stoul("-1")` does not throw.
    - Since C++26, `to_string(double)` is defined as `format("{}", val)`, and `to_string(0.1)` changes from `"0.100000"` to `"0.1"`.

The member functions of `basic_string` are covered in [[basic.string]]; this page covers the rest of `<string>`.

## The header <string> [string.classes.general]

[string.classes.general] ¶1 `<string>` defines the class template `basic_string` and five aliases:

| Alias | Type |
|---|---|
| `string` | `basic_string<char>` |
| `u8string` | `basic_string<char8_t>` (C++20) |
| `u16string` | `basic_string<char16_t>` |
| `u32string` | `basic_string<char32_t>` |
| `wstring` | `basic_string<wchar_t>` |

A few more points in [string.syn] are worth knowing:

- `namespace pmr` has a set of aliases with the same names that use `polymorphic_allocator<charT>`, such as `std::pmr::string`.
- `<string>` also declares the primary `char_traits` template and the five specializations ([[char.traits]]); these are provided in freestanding implementations too, but `basic_string` itself is not.
- `<string>` includes `<compare>` and `<initializer_list>`.
- The numeric conversion functions are provided only for `string` and `wstring`, not for `u8string`, `u16string` or `u32string`.
- The integer versions of `to_string` and `to_wstring` are `constexpr`; the floating-point versions are not.

## Concatenation [string.op.plus]

### Rvalue overloads reuse the buffer

```cpp run ok
#include <string>
#include <cstdio>
#include <cstdlib>
#include <new>

static int allocs = 0;
void* operator new(std::size_t n) {
  ++allocs;
  if (void* p = std::malloc(n)) return p;
  throw std::bad_alloc{};
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }

int main() {
  std::string a(30, 'a'), b(30, 'b'), c(30, 'c'), d(30, 'd');
  allocs = 0;
  std::string r = a + b + c + d;            // ((a + b) + c) + d
  std::printf("%d allocations\n", allocs);  // libc++ in our tests: 2
}
```

`a + b + c + d` parses left-associatively as `((a + b) + c) + d`. `a + b` produces a temporary string; after that, the left operand of every `+` is an rvalue, so the overload taking `basic_string&&` is selected: it appends directly to that temporary and then moves it out as the result. Only one buffer grows during the whole expression.

With libc++ in our tests there are two allocations in total: one for `a + b`, and one more growth when appending `c` runs out of capacity; the grown capacity is enough for `d`. Without the rvalue overloads, every `+` would allocate a new string.

The synopsis has 16 `operator+` overloads in all. In the table below, `S` is `basic_string<charT, traits, Allocator>` and `SV` is `type_identity_t<basic_string_view<charT, traits>>`:

| Left operand | Right operand | Effect |
|---|---|---|
| `const S&` | `const S&` or `const charT*` | ¶1 copy `lhs`, then append |
| `S&&` | `const S&` or `const charT*` | ¶2 `lhs.append(rhs); return std::move(lhs);` |
| `S&&` | `S&&` | ¶3 same, but both operands are left in valid but unspecified states |
| `const S&` or `const charT*` | `S&&` | ¶4 `rhs.insert(0, lhs); return std::move(rhs);` |
| `const charT*` | `const S&` | ¶5 copy `rhs`, insert at the front |
| `charT` | `const S&` or `S&&` | ¶6–¶7 insert one character at the front |
| `const S&` or `S&&` | `charT` | ¶8–¶9 `push_back` |
| `const S&` or `S&&` | `SV` | ¶10–¶11 append {{c++26}} |
| `SV` | `const S&` or `S&&` | ¶12–¶13 insert at the front {{c++26}} |

For ¶3, where both operands are rvalues, Note 1 says that if the two allocators are equal the implementation may move from either. For example, if the right one has more capacity, inserting at its front may be cheaper than appending to the left one. So the standard leaves both in valid but unspecified states, and you cannot assume the right operand was untouched.

### Concatenating with string_view {{c++26}}

```cpp run ok
#include <string>
#include <string_view>
#include <cassert>
using namespace std::literals;

int main() {
  std::string s = "hello";
  std::string r = s + " "sv + "world";   // C++26: string + string_view
  assert(r == "hello world");
}
```

¶10–¶13 were added by [[P2591R5]]. Before that, `str + sv` did not compile: there was no matching overload, and `string_view` does not implicitly convert to `string` (by the design of [[P0254R2]], see [[basic.string]]). You had to write `str + std::string(sv)`, with an extra allocation. libc++ in our tests already supports the new overloads.

¶14 The parameter on the view side is wrapped in `type_identity_t`, the same trick as the comparison operators of [[string.view]]: `charT`, `traits` and `Allocator` are deduced only from the `basic_string` side, and the other side can be any type implicitly convertible to `basic_string_view<charT, traits>`.

### Error-prone forms

- `"abc" + "def"` is ill-formed: both arrays decay to pointers, and pointers cannot be added ([[expr.add]]).
- `"abc" + 1` is valid and yields a pointer to `"bc"`, so `std::string s = "abc" + 1;` gives `"bc"`. Clang warns with `-Wstring-plus-int` by default.
- `s + 'a' + 'b'` is fine; `'a' + 'b' + s` computes `'a' + 'b'` first, giving the integer 195, then looks for `int + string`, where deduction of `charT` fails: ill-formed.
- There is still no `+` between two `std::string_view`s.

## Comparison and swap

[string.cmp] Since C++20 there are only two operator templates, `==` and `<=>`, each with a `(const S&, const S&)` and a `(const S&, const charT*)` version ([[P1614R2]]). `!=`, `<`, the reversed `const charT* == S` and so on all come from rewritten candidates ([[over.match.oper]]).

¶1 They are all equivalent to converting both sides to `basic_string_view` and comparing, so the semantics are entirely determined by [[string.view]] and [[char.traits]]: `<` on `std::string` compares characters as `unsigned char`, and the result type of `<=>` is `strong_ordering`. `S == S` is `noexcept`; `S == const charT*` is not, because the pointer must point to a null-terminated sequence, which is a precondition.

[string.special] ¶1 The non-member `swap` is equivalent to `lhs.swap(rhs)`. It is {{ub}} when the allocators are unequal and do not propagate (see [[basic.string]]).

## Input and output [string.io]

```cpp run ok
#include <sstream>
#include <string>
#include <cassert>

int main() {
  std::istringstream in("  hello world\nsecond line\n");
  std::string w, l;
  in >> w;               // "hello": skips leading whitespace, stops before the space
  std::getline(in, l);   // " world": continues after hello to the end of the line
  assert(w == "hello" && l == " world");
}
```

### operator>>

¶1–¶3 `>>` is a formatted input function ([[istream.formatted.reqmts]]); constructing the sentry skips leading whitespace by default. Once the sentry succeeds, it first erases `str`, then extracts characters one at a time and appends them, until any of the following happens:

- `n` characters have been stored, where `n` is `is.width()` if that is positive, otherwise `str.max_size()`;
- end-of-file occurs on the input;
- the next character `c` satisfies `isspace(c, is.getloc())`; that character is not extracted.

It then calls `is.width(0)`. If no characters were extracted, it sets `failbit`.

### getline

¶6–¶8 `getline(is, str, delim)` is an unformatted input function, but it does not affect `gcount()`. Constructing the sentry does not skip whitespace. It first erases `str`, then extracts characters, checking in this order (¶7 fixes the order):

1. end-of-file occurs on the input;
2. the next character equals `delim`; that character is extracted but not stored;
3. `str.max_size()` characters have been stored, in which case `failbit` is set.

`failbit` is also set only if no characters were extracted. The newline of an empty line `"\n"` is extracted, so `getline` succeeds and yields an empty string. The example above shows the usual problem with mixing `>>` and `getline`: `>>` does not extract the whitespace and newline after it, so the `getline` that follows reads the rest of that line.

`getline` also has overloads taking `basic_istream&&`, so `std::getline(std::istringstream(text), line)` works directly on a temporary stream. ¶10 The version without `delim` uses `is.widen('\n')` as the delimiter.

¶5 `operator<<` is equivalent to `os << basic_string_view<charT, traits>(str)`; it outputs by length, so embedded null characters are written too.

## erase and erase_if [string.erasure]

```cpp
template<class charT, class traits, class Allocator, class U = charT>
  constexpr size_type erase(basic_string<charT, traits, Allocator>& c, const U& value);
template<class charT, class traits, class Allocator, class Predicate>
  constexpr size_type erase_if(basic_string<charT, traits, Allocator>& c, Predicate pred);
```

¶1–¶2 Added in C++20 ([[P1209R0]]), the effect is the erase-remove idiom, returning the number of characters removed. Characters are compared by the `remove` algorithm, that is, with `operator==`, not `traits::eq`; for strings with custom traits the two may disagree.

The default template argument `charT` for `U` was added in C++26, so that braced arguments like `std::erase(s, {})` can be deduced. At the time of writing, libc++ in our tests did not yet implement this default argument, and `std::erase(s, {})` fails to compile.

## Numeric conversions [string.conversions]

### The stoi family

```cpp
int stoi(const string& str, size_t* idx = nullptr, int base = 10);
// stol, stoul, stoll and stoull have the same form
```

¶1 `stoi` and `stol` call `strtol(str.c_str(), ptr, base)`; the other three call `strtoul`, `strtoll` and `strtoull`. If `idx` is non-null, the index of the first unconverted character is stored there. ¶3 They throw `invalid_argument` if `strto*` reports that no conversion could be performed, and `out_of_range` if it sets `errno` to `ERANGE` or the result is outside the range of the return type.

The semantics come entirely from C's `strtol` family, and C's behavior is inherited along with them. Tested in our setup:

| Call | Result | Why |
|---|---|---|
| `stoi("  42abc", &idx)` | 42, `idx == 4` | skips leading whitespace; stops at a non-digit without error |
| `stoi("abc")` | throws `invalid_argument` | no conversion possible |
| `stoi("3000000000")` | throws `out_of_range` | representable in a 64-bit `long` but not in `int`; handled by the outside-the-return-type rule |
| `stoul("-1")` | `ULONG_MAX` | `strtoul` accepts a minus sign and negates the result as unsigned |
| `stoi("0x1f", nullptr, 16)` | 31 | base 16 accepts the `0x` prefix |
| `stoi("0x1f", nullptr, 0)` | 31 | base 0 determines the radix from the prefix |
| `stoi("1'000")` | 1 | digit separators are not recognized |

`strtol` depends on the current C locale for deciding what is whitespace, and it reads and writes `errno`. For a conversion that does not allocate, does not throw, is unaffected by locale, and reports precisely where it failed, use `std::from_chars` ([[charconv]]).

¶4–¶6 `stof`, `stod` and `stold` call `strtof`, `strtod` and `strtold`, and throw `out_of_range` when `errno == ERANGE`. That includes underflow: the C standard permits `strtod` to set `ERANGE` when the result is subnormal, and whether it does is up to the implementation. In our tests (macOS's C library), `std::stod("1e-310")` throws `out_of_range`, even though `1e-310` is representable as a subnormal `double`.

¶8–¶13 The versions taking `wstring` call wide-character functions such as `wcstol`, with the same rules.

### The semantic change of to_string {{c++26}}

¶7 In the current draft, `to_string(val)` returns `format("{}", val)`, and ¶14 `to_wstring` returns `format(L"{}", val)`. Before C++26, `to_string` was defined as if by `sprintf` with formats like `%d` and `%f`. Integer results are unchanged; floating-point results are completely different:

| Call | C++23 (`%f`) | C++26 (`format("{}")`) |
|---|---|---|
| `to_string(0.1)` | `"0.100000"` | `"0.1"` |
| `to_string(1e-7)` | `"0.000000"` | `"1e-07"` |
| `to_string(1e20)` | `"100000000000000000000.000000"` | `"1e+20"` |

The old `%f` always printed six decimal places, so very small numbers became `0.000000`, very large ones printed a long string of digits, and the decimal point character was affected by the global C locale. The new semantics ([[P2587R3]]) use `format`'s default format, the shortest representation that round-trips exactly ([[format.string.std]], [[charconv]]), and are locale-independent. Old code does not fail to compile because of this; only the output changes.

!!! impl "Implementation status"
    At the time of writing, libc++ in our tests (LLVM 23) did not yet implement [[P2587R3]]: `to_string(0.1)` returns `"0.100000"`, `to_string(1e-7)` returns `"0.000000"`, and `to_string(1e20)` returns `"100000000000000000000.000000"`. The integer `to_string` is not `constexpr` yet either; calling it in a constant expression is an error.

## Hashing [basic.string.hash]

The five `hash` partial specializations have the form `hash<basic_string<charT, char_traits<charT>, A>>` and are valid for any allocator `A`, so `std::pmr::string` can go straight into an `unordered_set`. ¶1 is the only normative requirement:

!!! std
    If `S` is one of these string types, `SV` is the corresponding string view type, and `s` is an object of type `S`, then `hash<S>()(s) == hash<SV>()(SV(s))`.

This equation makes it possible to look up an `unordered_map<string, V>` with a `string_view` without constructing a temporary `string`; see [[string.view]] for an example. A `basic_string` with custom traits has no standard `hash` specialization.

## The ""s literal [basic.string.literals]

```cpp run ok
#include <string>
#include <cassert>
using namespace std::literals;

int main() {
  std::string a = "a\0b";     // const char* construction: truncated at '\0'
  auto b = "a\0b"s;            // literal operator: length 3
  assert(a.size() == 1 && b.size() == 3);
}
```

¶1–¶5 `operator""s(const charT* str, size_t len)` returns `basic_string{str, len}` and lives in `std::literals::string_literals`. The length comes from the literal itself, so embedded nulls are kept.

The note in ¶6 says that the suffix `s` is also used by `chrono::duration` for seconds, but there is no conflict: the duration suffix applies to number literals and the string suffix to string literals, and the two literal operators have different parameter lists ([[over.literal]]).

`""s` produces a temporary `string`, so `std::string_view v = "abc"s;` dangles immediately; `std::string_view v = "abc";` or `"abc"sv` is what is safe ([[string.view]]).

## History

!!! history
    - C++11 added the `stoi` family and `to_string`; `to_string` was then defined in terms of `sprintf` formats.
    - C++20: the comparison operators became `==` and `<=>` ([[P1614R2]]); `erase` and `erase_if` were added ([[P1209R0]]); `u8string` was added.
    - C++26: direct concatenation of `string` and `string_view` ([[P2591R5]]); `to_string` redefined as `format("{}")` ([[P2587R3]]).

## Questions

!!! question "Question 1"
    In `std::string s = "x"; s = s + "y" + s;`, which overload does the second `+` select, and what is the result?

<details markdown="1">
<summary>Answer</summary>

`s + "y"` selects `(const S&, const charT*)` and produces the temporary string `"xy"`. The second `+` has that rvalue as its left operand and the lvalue `s` on the right, so it selects `(S&&, const S&)` (¶2), appends `s` to the temporary to get `"xyx"`, and that is move-assigned to `s`. The right operand `s` is only read during the append, so there is no problem.
</details>

!!! question "Question 2"
    A file contains `"42\nhello\n"`. First `in >> n;` reads an `int`, then `std::getline(in, line);`. What is `line`? How do you change it to read `"hello"`?

<details markdown="1">
<summary>Answer</summary>

`line` is an empty string. After reading `42`, `>>` stops before the newline; `getline` immediately meets the delimiter, extracts it without storing it, returns an empty string, and does not set `failbit` ([[string.io#6]]). You can call `in.ignore(std::numeric_limits<std::streamsize>::max(), '\n')` before `getline` to skip the rest of the line, or use `std::getline(in >> std::ws, line)` to skip whitespace.
</details>
