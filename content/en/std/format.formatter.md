---
title: Formatters and range formatting
summary: "The std::formatter customization point: the contract of its parse and format members, the formattable concept, the specializations the standard provides and disables, the ? escaped format, parse contexts and format contexts; how to write a correct custom formatter; C++26's nonlocking optimization switch; and C++23 range formatting."
updated: 2026-10-19
---

!!! tldr
    - The library uses `formatter<T, charT>` for each argument: `parse` reads the format spec and can run at compile time; `format` outputs the value according to the options read, at run time.
    - A custom formatter must meet three conditions: `parse` is `constexpr`, `format` is a `const` member, and `format` is a template over the context type. The easiest approach is to inherit from an existing formatter.
    - A `formatter<T>` without a specialization is disabled: it can be neither constructed nor copied, so `formattable<T, char>` yields `false` rather than a hard error.
    - `?` selects the escaped form: strings are quoted, control characters are written as `\u{...}`, and invalid code units as `\x{...}`. Elements of ranges and tuples use this form by default.
    - Ranges with formattable elements are formattable by default: sequences print as `[1, 2]`, maps as `{1: "x"}`, sets as `{1, 3}`; options such as `{:n}`, `{:s}` and `{::spec}` adjust this.

## A complete example

```cpp run title="custom-formatter.cpp" ok
#include <cassert>
#include <format>
#include <string_view>
#include <vector>

struct Point { int x, y; };

// custom syntax: optional 'p' (compact) or 'c' (with parentheses, the default)
template <>
struct std::formatter<Point> {
  char style = 'c';
  constexpr auto parse(std::format_parse_context& ctx) {
    auto it = ctx.begin();
    if (it != ctx.end() && (*it == 'p' || *it == 'c'))
      style = *it++;
    if (it != ctx.end() && *it != '}')
      throw std::format_error("invalid spec for Point");
    return it;
  }
  template <class FormatContext>
  auto format(const Point& p, FormatContext& ctx) const {
    if (style == 'p')
      return std::format_to(ctx.out(), "{} {}", p.x, p.y);
    return std::format_to(ctx.out(), "({}, {})", p.x, p.y);
  }
};

// format only reads the value and never re-enters print, so it can be declared nonlocking
template <>
constexpr bool std::enable_nonlocking_formatter_optimization<Point> = true;

enum class Color { red, green };

// inheritance: reuse all of string_view's format spec (fill, align, width, precision)
template <>
struct std::formatter<Color> : std::formatter<std::string_view> {
  template <class FormatContext>
  auto format(Color c, FormatContext& ctx) const {
    std::string_view name = c == Color::red ? "red" : "green";
    return std::formatter<std::string_view>::format(name, ctx);
  }
};

static_assert(std::formattable<Point, char>);
static_assert(std::formattable<Color, char>);

int main() {
  assert(std::format("{}", Point{1, 2}) == "(1, 2)");
  assert(std::format("{:p}", Point{1, 2}) == "1 2");
  assert(std::format("{:*^7}", Color::red) == "**red**");
  assert(std::format("{}", std::vector{Point{1, 2}, Point{3, 4}})
         == "[(1, 2), (3, 4)]");
  assert(std::format("{::p}", std::vector{Point{1, 2}}) == "[1 2]");  // element spec handed to Point
}
```

`std::formatter` is the customization point of the formatting library. For `std::format("{:p}", pt)`, the library first uses `formatter<Point>`'s `parse` to read the `p` after the colon and store the result in the formatter object, then calls `format` to write the value to the output.

The reason for this split: `parse` depends only on the format string and the type, so it can run at compile time and be used to check the format string ([[format.fmt.string]]); `format` depends on the value and can only run at run time. A program may explicitly or partially specialize `std::formatter` for types it defines ([[namespace.std]]).

Writing `std::format("{:z}", Point{1, 2})` is a compile-time error: `parse` executes a `throw` during constant evaluation, so the consteval construction of the format string fails. The sections below explain the rules behind each detail in this code.

## Formatter requirements ([formatter.requirements])

¶1 A type `F` meets the ***BasicFormatter*** requirements if it is default constructible, copy constructible, copy assignable, swappable and destructible, and the expressions in Table 112 are valid: `g.parse(pc)`, and `f.format(u, fc)`, where `u` is an lvalue of `T` and `f` may be `const`.

¶2 The ***Formatter*** requirements add Table 113: `f.format(t, fc)` is also valid for values convertible to (possibly `const`) `T`, and `f.format(u, fc)` does not modify `u`. Formatters that meet only *BasicFormatter* are for types that can only be formatted as non-`const`, such as `ranges::filter_view`, whose `begin()` is not `const`. The C++20 defect fix [[P2418R2]] made such types formattable.

Table 112's contract for `parse`:

- ¶3.8 `pc.begin()` points to the start of the *format-spec*. If there is no *format-spec* or it is empty, `pc.begin() == pc.end()` or `*pc.begin() == '}'`.
- `parse` parses up to the first character that does not match. Unless the whole range was parsed or the unmatched character is `}`, it throws `format_error`.
- It stores the parsed result in `*this` and returns an iterator past the end of the parsed range, that is, an iterator pointing at `}`.

The output of `format` may depend only on: the value being formatted, `fc.locale()`, `fc.arg(n)` (for dynamic widths and the like), and the format spec seen by the last `parse`. A formatter should not read global state, or compile-time checking and run-time formatting could not be separated.

## The formattable concept ([format.formattable]) {{c++23}}

```cpp
template<class T, class Context,
         class Formatter = typename Context::template formatter_type<remove_const_t<T>>>
  concept formattable-with =
    semiregular<Formatter> &&
    requires(Formatter& f, const Formatter& cf, T&& t, Context fc,
             basic_format_parse_context<typename Context::char_type> pc) {
      { f.parse(pc) } -> same_as<typename decltype(pc)::iterator>;
      { cf.format(t, fc) } -> same_as<typename Context::iterator>;
    };

template<class T, class charT>
  concept formattable =
    formattable-with<remove_reference_t<T>, basic_format_context<fmt-iter-for<charT>, charT>>;
```

Three rules any formatter must follow can be read off this definition:

1. `format` must be a `const` member function, because the concept calls it through `const Formatter& cf`.
2. The formatter must be `semiregular`: default constructible and copyable.
3. `format` must accept `basic_format_context<fmt-iter-for<charT>, charT>`. ¶1 says *fmt-iter-for* is an unspecified output iterator type.

Rule 3 is the one most likely to cause trouble. A `format` that accepts only `std::format_context&` works for `std::format("{}", t)` but is not guaranteed to satisfy `formattable`. Formatters for composite types such as `vector<T>` and `optional<T>` require the element to satisfy `formattable`, so they cannot use it:

```cpp run title="non-generic-format.cpp" error
#include <format>
#include <vector>

struct P { int x; };
template <> struct std::formatter<P> {
  constexpr auto parse(std::format_parse_context& ctx) { return ctx.begin(); }
  auto format(P p, std::format_context& ctx) const {   // accepts only format_context
    return std::format_to(ctx.out(), "{}", p.x);
  }
};

int main() {
  (void)std::format("{}", P{1});                 // OK
  (void)std::format("{}", std::vector<P>{{1}});  // error: P does not satisfy formattable
}
```

In libc++, *fmt-iter-for* is `charT*`, which `format_context&` cannot bind to, so the second line fails to compile. Make `format` a template over the context type and the problem goes away.

¶2 For `T` and `charT` to model `formattable`, `formatter<remove_cvref_t<T>, charT>` must also meet the semantic requirements of *BasicFormatter*; when `remove_reference_t<T>` is `const`, it must also meet the *Formatter* requirements.

## Standard specializations ([format.formatter.spec])

### Enabled and disabled (¶2, ¶4–¶8)

Every `formatter` specialization is either **enabled** or **disabled**. ¶5 A `formatter<T, charT>` for which neither the library nor the user provides a specialization is disabled. ¶7 A disabled specialization is not default constructible, not copy or move constructible, and not copy or move assignable.

This makes formattability a type property that can be queried safely: `formattable` requires `semiregular<Formatter>`, which a disabled specialization does not satisfy, so the concept yields `false` with no hard error. libc++ does this by making the primary template inherit from a class whose special members are all `= delete`.

¶2 lists the enabled specializations each header provides (`charT` is `char` or `wchar_t`):

| Specialization | debug-enabled | constexpr-enabled |
|---|---|---|
| `formatter<char, char>`, `<char, wchar_t>`, `<wchar_t, wchar_t>` | yes | yes |
| strings: `charT*`, `const charT*`, `charT[N]`, `basic_string`, `basic_string_view` | yes | yes |
| all signed and unsigned integer types and `bool` | | yes |
| all cv-unqualified floating-point types | | |
| `nullptr_t` | | yes |
| `void*`, `const void*` | | |

- A **debug-enabled** specialization ([[g:debug-enabled-specialization]]) additionally provides a public, constexpr member `set_debug_format()`, whose effect is as if the format spec's type were `?`. The formatters for ranges and tuples rely on it to make elements output in escaped form by default.
- In a **constexpr-enabled** specialization ([[g:constexpr-enabled-specialization]]), the `format` member is declared `constexpr`. Floating-point types and `void*` are not among them, so the standard does not require floating-point numbers to be formattable at compile time. This is new wording after C++23.

¶4 `<format>` also provides a set of disabled specializations: `char` strings with `wchar_t` output, such as `formatter<const char*, wchar_t>`. Note 1 in ¶3 says that specializations requiring implicit multibyte-to-wide conversion are all disabled.

¶6 The specializations the library provides are enabled and meet the *Formatter* requirements unless otherwise specified. The example in ¶8 demonstrates the idiom of inheriting from an existing formatter, and shows that `std::format("{}", L"foo")` (a wide string with narrow output) and unspecialized user types are both errors.

### The nonlocking optimization ([format.formatter.locking]) {{c++26}}

```cpp
template<class T>
  constexpr bool enable_nonlocking_formatter_optimization = false;
```

This variable template serves `std::print` ([[print.fun]]). `print` has two implementation strategies:

- Lock the `FILE*` and format directly into the stream. No intermediate buffer is needed, so it is fast.
- Format the result into a temporary string first, then lock the stream and write it once.

The first strategy calls the user's `formatter::format` while holding the lock. If that prints to the same stream, it deadlocks; if it runs for a long time, it blocks output from other threads. [[P3107R5]] specifies that `print` takes the direct-write path only when `enable_nonlocking_formatter_optimization` is `true` for all argument types; otherwise it buffers first.

- [format.formatter.spec] ¶3: for every type the standard library provides a formatter for, this variable is specialized as `true`, unless otherwise specified.
- The specialization for range types is `false` ([[format]]), because the element formatter may be user-written; `pair` and `tuple` take the conjunction of the elements' values.
- [format.formatter.locking] ¶1: users may specialize it for cv-unqualified program-defined types; the specialization must be usable in constant expressions and have type `const bool`. Set it to `true` only if `format` never re-enters `print` and never blocks for long.

!!! impl
    libc++ in our tests declares this variable template and specializes it as `true` for the built-in formatters, but its `<print>` implementation does not use it yet; the two paths have not been separated.

## Escaped format ([format.string.escaped]) {{c++23}}

```cpp run title="escaped.cpp" ok
#include <cassert>
#include <format>
#include <string>

int main() {
  assert(std::format("[{:?}]", "h\tllo") == "[\"h\\tllo\"]");
  assert(std::format("[{:?}, {:?}]", '\'', '"') == "['\\'', '\"']");
  assert(std::format("{:?}", std::string("\0\x1b", 2)) == "\"\\u{0}\\u{1b}\"");
  assert(std::format("{:?}", "\xc3\x28") == "\"\\x{c3}(\"");   // invalid UTF-8
  assert(std::format("{:?}", "\u0301") == "\"\\u{301}\"");      // isolated combining mark
}
```

¶1 A character or string can be formatted in escaped form for debugging and logging; the result is called an **escaped string** ([[g:escaped-string]]). ¶2 The input is interpreted, and the output constructed, in the encoding *CE* associated with the character type:

1. Output `"`.
2. Split the input into pieces, each a character, a shift sequence, or a run of invalid code units, and process them in order:
    - Tab, newline, carriage return, `"` and `\` are output as `\t`, `\n`, `\r`, `\"` and `\\` (Table 114).
    - When *CE* is a UTF encoding and the character's General_Category is Separator (Z) or Other (C) and it is not a space, output `\u{hex}`. This covers control characters, non-printable characters, zero-width joiners and the like.
    - A character with the Grapheme_Extend=Yes property (a combining mark) that has no preceding character output unchanged to attach to is also output as `\u{...}`.
    - Under non-UTF encodings, an implementation-defined set of separator and non-printable characters is escaped likewise.
    - Other characters are output unchanged.
    - How shift sequences are handled is unspecified; invalid code units are output one by one as `\x{hex}`.
3. Output `"`.

¶3 The escaped form of a single character is enclosed in `'`; the character `'` is output as `\'`, and `"` is output unchanged.

The intent of the combining-mark rule: `"e\u0301"` (e plus a combining acute accent) is output unchanged as é; an isolated combining mark, such as one at the start or one following an escaped character, is escaped, so that it does not attach to a quote or backslash and cause misreading.

## Parse context ([format.parse.ctx])

`basic_format_parse_context<charT>` holds the range of the format string not yet parsed, the indexing mode (unknown, manual, automatic), the next automatic index, and the number of arguments `num_args_`. ¶2 A program that explicitly or partially specializes it is IFNDR: ill-formed, no diagnostic required.

| Member | Purpose |
|---|---|
| `begin()`, `end()` | start of the current *format-spec*, end of the whole format string |
| `advance_to(it)` | ¶6 precondition: `end()` is reachable from `it` |
| `next_arg_id()` | automatic indexing: takes the next index; throws `format_error` if already in manual mode (¶9); not a core constant expression if the index is not less than `num_args_` (¶10) |
| `check_arg_id(id)` | enters manual mode; throws if already in automatic mode (¶12); not a core constant expression if `id >= num_args_` (¶13) |
| `check_dynamic_spec<Ts...>(id)` {{c++26}} | if the type of argument `id` is not among `Ts...`, the call is not a core constant expression (¶14–¶15) |
| `check_dynamic_spec_integral`, `check_dynamic_spec_string` | shorthand forms of the previous row (¶16–¶17) |

A custom formatter that wants to support syntax referring to another argument, such as a dynamic width, must call `next_arg_id` or `check_arg_id`. They both maintain the no-mixing rule for numbering ([[format.string]]) and check at compile time that the index is in range. `check_dynamic_spec` further checks the type of the referenced argument at compile time, which is exactly what the standard formatters do for dynamic widths.

Note 1 in ¶3 points out that the public constructor initializes `num_args_` to 0, so calling `next_arg_id` and the like on a parse context the program constructs itself is never a core constant expression. The library internally uses a way of constructing it that passes the number of arguments.

!!! impl
    libc++'s `basic_format_parse_context` in our tests does not yet provide the `check_dynamic_spec` family of members.

## Format context ([format.context])

`basic_format_context<Out, charT>` holds the arguments and the output iterator:

- `arg(id)` (¶6) gets argument `id`, yielding an empty argument when out of range;
- `locale()` (¶7) returns the locale if the formatting function was given one, otherwise `std::locale()`, the global locale;
- `out()` (¶8) is equivalent to `return std::move(out_);`: the iterator is moved out, and after writing you must hand the new position back as the return value or call `advance_to`;
- `advance_to(it)` (¶9) is equivalent to `out_ = std::move(it);`.

¶3 `Out` must model `output_iterator<const charT&>`. ¶4 `format_context` is the specialization that appends to a `string`. ¶5 recommends that implementations provide only one such specialization per `charT`, wrapping targets like `string` and `vector` in a temporary buffer with a uniform interface, to avoid instantiating repeatedly for every output iterator type. libc++'s `format_context` is `basic_format_context<back_insert_iterator<__format::__output_buffer<char>>, char>`, a type that shows up in formatter-related diagnostics.

## Range formatting ([format.range]) {{c++23}}

```cpp run title="ranges.cpp" ok
#include <cassert>
#include <format>
#include <map>
#include <set>
#include <string>
#include <vector>

int main() {
  assert(std::format("{}", std::vector{1, 2, 3}) == "[1, 2, 3]");
  assert(std::format("{::#x}", std::vector{10, 11}) == "[0xa, 0xb]");   // element spec
  assert(std::format("{:n}", std::vector{1, 2}) == "1, 2");            // brackets removed
  assert(std::format("{:*^11}", std::vector{1, 2}) == "**[1, 2]***");  // width applies to the whole
  assert(std::format("{}", std::vector<std::string>{"a", "b"}) == "[\"a\", \"b\"]");
  assert(std::format("{}", std::map<int, std::string>{{1, "x"}}) == "{1: \"x\"}");
  assert(std::format("{}", std::set{3, 1}) == "{1, 3}");
  assert(std::format("{}", std::vector{'h', 'i'}) == "['h', 'i']");
  assert(std::format("{:s}", std::vector{'h', 'i'}) == "hi");
  assert(std::format("{:?s}", std::vector{'h', '\n'}) == "\"h\\n\"");
  assert(std::format("{}", std::vector<std::vector<int>>{{1}, {2, 3}}) == "[[1], [2, 3]]");
}
```

[[P2286R8]] made every `input_range` with formattable elements formattable by default, and [[P2585R1]] improved the default formats: maps print as `{k: v}`, sets as `{a, b}`, and character sequences can print as strings. The range formatter is a constrained partial specialization:

```cpp
template<ranges::input_range R, class charT>
  requires (format_kind<R> != range_format::disabled) &&
           formattable<ranges::range_reference_t<R>, charT>
struct formatter<R, charT> : range-default-formatter<format_kind<R>, R, charT> { };
```

It dispatches to one of four exposition-only *range-default-formatter*s based on the value of `format_kind<R>`.

### format_kind: automatic classification ([format.range.fmtkind])

¶1 Instantiating the primary template of `format_kind` for a non-range type makes the program ill-formed. ¶2 For an `input_range`, the classification rules are:

1. ¶2.1 If the element type (with reference and cv removed) is `R` itself, it is `disabled`. Note 1 explains this avoids constraint recursion: `filesystem::path` is a range whose elements are `path`, and without this exclusion `formattable<path>` would require `formattable<path>`.
2. ¶2.2 Otherwise, if `R::key_type` names a type: `map` if `R::mapped_type` also names a type and the element is a `pair` or a two-element `tuple`, otherwise `set`.
3. ¶2.3 Otherwise `sequence`.

`string` and `debug_string` are never chosen automatically. `std::string` has its own formatter, more specialized than the range partial specialization; `vector<char>` prints as a sequence by default, `['h', 'i']`. ¶3 Users may specialize `format_kind` for their own range types, for example declaring a custom string class as `range_format::string`.

### range_formatter ([format.range.formatter])

¶2 The syntax of a range format spec is:

```text
range-format-spec:  range-fill-and-align(opt) width(opt) n(opt) range-type(opt) range-underlying-spec(opt)
range-type:         m | s | ?s
range-underlying-spec:  : format-spec        ← handed to the element's formatter
```

- The fill character may not be `{` or `}`, nor `:`, since `:` introduces the element's format spec.
- ¶5 `n` removes the outer brackets.
- ¶6 and Table 115 specify *range-type*: `m` requires the element to be a two-element `pair` or `tuple`, changes the brackets to `{}`, and prints each element as `k: v`; `s` and `?s` require the element type to be `charT` and print as a string or escaped string, in which case neither `n` nor an element spec may be given.
- ¶9 When there is no element spec, the *range-type* is not `s` or `?s`, and the element formatter has `set_debug_format()`, it is called. That is why `vector<string>` prints quoted by default: `["a", "b"]`.
- ¶11 The output is the opening bracket, the elements separated by the separator, and the closing bracket, by default `[`, `, ` and `]`, changeable with `set_brackets` and `set_separator`. Width and alignment apply to the output of the whole range.

### The four default formats ([format.range.fmtdef] through [format.range.fmtstr])

| `format_kind` | Behavior | Example |
|---|---|---|
| `sequence` | handed straight to `range_formatter` | `[1, 2, 3]` |
| `map` | [format.range.fmtmap] ¶1 requires the element to be a two-element `pair` or `tuple`; brackets `{}`, element brackets removed, the separator inside elements changed to `: ` | `{1: "x"}` |
| `set` | brackets changed to `{}` | `{1, 3}` |
| `string`, `debug_string` | [format.range.fmtstr] ¶1 requires the element type to be exactly `charT`; copied to a `basic_string<charT>` first and formatted as a string; `debug_string` also calls `set_debug_format()` | `hi`, `"hi"` |

The purpose of the exposition-only *fmt-maybe-const* in [[format]] is: if `const R` is also a range with formattable elements, format it as `const R&`, otherwise as `R&`. That way views that can only be iterated as non-`const` can be formatted too.

Formatting of the container adaptors `stack`, `queue` and `priority_queue` is covered in [[container.adaptors.format]].

## Common misconceptions

!!! pitfall "Forgetting const on format"
    `formattable` calls `format` through `const Formatter&`. With libc++ in our tests, when `format` is not a `const` member, even the simplest `std::format("{}", t)` fails to compile. If you need mutable state you can use a `mutable` member, but that usually signals a design problem.

!!! pitfall "parse is not constexpr"
    Compile-time checking calls `parse` during constant evaluation. If `parse` is not `constexpr`, every `std::format("...", t)` fails to compile, and you are left with `vformat` or `dynamic_format`.

!!! pitfall "Not returning the new iterator after writing output by hand"
    `out()` moves the iterator out. When writing output by hand, write `auto it = ctx.out(); *it++ = 'x'; return it;`, so that the returned iterator is the new position.

!!! pitfall "Turning on the nonlocking optimization carelessly"
    If `format` internally calls `std::print` on the same stream, or does slow I/O, setting `enable_nonlocking_formatter_optimization` to `true` causes deadlock or long lock holding on libraries that implement the direct-write path.

## Questions

!!! question "Question 1"
    The `range_reference_t` of `vector<bool>` is `vector<bool>::reference`, not `bool`. Why does `std::format("{}", std::vector<bool>{true, false})` still compile?

<details markdown="1">
<summary>Answer</summary>

The range partial specialization requires `formattable<range_reference_t<R>, charT>`, and `vector<bool>::reference` is a proxy class. [[vector.bool]] provides a dedicated formatter partial specialization for this proxy type, delegating to `formatter<bool>` internally. Without it, `format_kind` would give `sequence`, but the `formattable` constraint would not be satisfied and the range partial specialization would not be selected. In our tests the output is `[true, false]`.
</details>

!!! question "Question 2"
    Does `std::format("{}", std::filesystem::path("a/b"))` print `[a, b]`?

<details markdown="1">
<summary>Answer</summary>

It does not go through range formatting. The element type of `path` is `path` itself, so per [format.range.fmtkind] ¶2.1, `format_kind<path>` is `disabled`. C++26 provides a dedicated formatter for `path` ([fs.path.fmtr]) that prints the path string. On implementations that do not provide this formatter, `path` is not formattable; with libc++ in our tests, `std::formattable<std::filesystem::path, char>` is `false`.
</details>

## Summary

| Topic | Rule |
|---|---|
| The two members | `parse` reads and stores options and can run at compile time; `format` outputs at run time |
| `formattable` | requires the formatter to be `semiregular`, `format` to be `const`, and acceptance of a context with an unspecified iterator type |
| Disabled specializations | no usable special members; `formattable` yields `false` |
| debug-enabled | has `set_debug_format()`; ranges and tuples call it on elements automatically |
| constexpr-enabled | integers, `bool`, characters, strings, `nullptr_t`; not floating point or `void*` |
| Escape `?` | adds quotes; control and non-printable characters as `\u{..}`, invalid code units as `\x{..}` |
| Parse context | `next_arg_id` and `check_arg_id` maintain the numbering rules; `check_dynamic_spec` checks types at compile time |
| Nonlocking optimization | `false` by default; `true` for standard types; `false` for ranges; users may specialize |
| Ranges | `format_kind` classifies into map, set, sequence; `{:n}`, `{:m}`, `{:s}`, `{:?s}`, `{::element-spec}` |
