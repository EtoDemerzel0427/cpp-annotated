---
title: std::format and std::print (P0645, P2093, P2286)
summary: How C++20's std::format and C++23's std::print avoid the drawbacks of both printf and iostream: Python-style format strings, locale independence by default, extension by specializing formatter, and type erasure to control code size. Why compile-time checking of format strings is done with a consteval constructor and why that counted as a breaking change; how print handles Unicode on the Windows console; how ranges are output by default; and how runtime format strings evolved from vformat to dynamic_format.
tags: proposal, standard library, format, print, format strings, consteval, type erasure, Unicode, C++20, C++23
group: Library
updated: 2026-10-19
---

!!! tldr
    - `printf` does not check types and cannot be extended to user types; iostream is type-safe, but formatting state sticks to the stream, a sentence gets split across several `<<`, and arguments cannot be reordered. [[P0645R10]] gets the best of both with Python-style `{}` format strings and a specializable `formatter<T>`, and became C++20's `<format>`.
    - Errors in format strings were originally thrown at run time as `format_error`. [[P2216R3]] changed the type of the format string parameter to `basic_format_string` with a `consteval` constructor, turning the check into a call that must be a constant expression, so errors must be diagnosed at compile time. It applies to C++20 as a defect report, at the cost that old code using a variable as the format string no longer compiles.
    - Each `format` call is just a thin shell that packs the arguments into a type-erased `format_args`; there is only one copy of the actual formatting code. In libc++ that code is about 46 KB, and each additional call adds only a few hundred bytes.
    - C++23's `std::print` ([[P2093R14]]) writes directly to `stdout`. When the literal encoding is UTF-8 and the output is a terminal that can only display Unicode through a native Unicode API (the Windows console), it uses that API instead, avoiding mojibake.
    - [[P2286R8]] made ranges formattable by default: sequences print as `[1, 2]`, maps as `{"k": 1}`, and strings inside elements are quoted and escaped.

## Before C++20: two choices, neither good enough

Before C++20, printing a line of text with numbers in it meant using either C's `printf` or iostream. Each has its own class of problems.

A `printf` format specifier does two jobs at once: how to display, and what type the argument is. The only difference between `%d`, `%ld` and `%lld` is telling the function to read an `int`, a `long` or a `long long`, and by the C standard a wrong type is {{ub}}:

```cpp title="printf-types.cpp" run ub
#include <cstdint>
#include <cstdio>

int main() {
  long n = 1L << 40;
  std::int64_t id = 42;
  std::printf("%d\n", n);    // UB: %d requires int
  std::printf("%ld\n", id);  // on macOS int64_t is long long
}
```

Clang 23 gives a `-Wformat` warning for both lines. The second line is fine on Linux, where `int64_t` is `long`; the portable way is the `PRId64` macro from `<cinttypes>`. `printf` also cannot be extended: user types must be converted to strings first, and `std::string` needs `.c_str()`.

iostream solved the type problem with overloading, and `<<` can be overloaded for user types. But it made formatting options part of the stream's state:

```cpp title="sticky.cpp" run ok
#include <iostream>

int main() {
  std::cout << std::hex << 255 << '\n';  // ff
  std::cout << 255 << '\n';              // still ff
}
```

`std::hex` stays in effect until someone changes it back. Once a sentence is split across several `<<`, translators no longer get a complete sentence; word order differs between languages, and the order of a `<<` chain is fixed in the code and cannot be rearranged (the section on positional arguments in [[P0645R10]] mentions exactly this).

The two also have something in common: output is affected by the global locale. The program below sets the global locale to German, and both `printf` and `cout` print a comma as the decimal point:

```cpp title="locale.cpp" ok
#include <cstdio>
#include <format>
#include <iostream>
#include <locale>

int main() {
  std::locale de("de_DE.UTF-8");
  std::locale::global(de);   // a named locale also calls setlocale
  std::cout.imbue(de);
  std::printf("%.1f\n", 1234.5);                     // 1234,5
  std::cout << 1234.5 << '\n';                       // 1.234,5
  std::cout << std::format("{}", 1234.5) << '\n';    // 1234.5
  std::cout << std::format("{:L}", 1234.5) << '\n';  // 1.234,5
}
```

`printf` changes too because [[locale.statics#1]] specifies that when the argument to `locale::global` has a name, `setlocale(LC_ALL, ...)` is also called to change the C locale. When writing text meant for machines, such as JSON or logs, this is exactly what you don't want. The program needs the `de_DE.UTF-8` locale to exist on the system, otherwise constructing the `std::locale` throws `runtime_error`; the output on macOS is as shown in the comments.

## The design space of P0645

[[P0645R10]] is based on Victor Zverovich's open-source library {fmt}. The questions it had to answer fall into five groups.

### What syntax for format strings

The paper considered two conservative routes. One was to keep `printf`'s `%` syntax and patch its problems, which the paper considered would break compatibility while being similar enough to `printf` to invite misuse. The other was Boost.Format's `format("%1%") % x`, which chains arguments with `operator%`; that became unnecessary once C++11 had variadic templates, and its syntax carries the same `printf` baggage.

The syntax finally adopted comes from the Python, .NET and Rust family: replacement fields are written in `{}`, with the format spec after a colon. Type information comes from the arguments themselves, and the format spec only controls display, so length modifiers like `h`, `l` and `ll` are no longer needed:

```cpp title="basics.cpp" run ok
#include <cassert>
#include <cstdint>
#include <format>

int main() {
  long n = 1L << 40;
  std::int64_t id = 42;
  assert(std::format("{} {}", n, id) == "1099511627776 42");
  assert(std::format("{:x} {}", 255, 255) == "ff 255");  // no lingering state
  assert(std::format("{0} of {1}", 3, 10) == "3 of 10");
  assert(std::format("{1} contains {0}", 3, 10) == "10 contains 3");
}
```

The last two lines use **positional arguments**: `{1}` refers to the second argument. A translation can reorder them without changing the code. Automatic numbering `{}` and manual numbering `{0}` cannot be mixed in the same format string ([[format.string.general#4]]). The full syntax of format strings is in [[format.string]].

### Locale: not used by default

P0645, following Python, made formatting locale-independent by default, with only a dedicated type specifier `n` producing numbers according to the locale. The reasons: high-throughput text (JSON, XML) does not need and should not depend on the locale, and not querying the locale is also faster.

`n` was replaced before C++20 shipped. [[P1892R1]] pointed out that `n` only gave one locale-specific representation and couldn't be combined with floating-point formats like `f` and `e`; it was changed into a modifier option that can be combined with any type specifier, for example `{:.2Lf}`. Uppercase `L` was chosen because, among other reasons, it has a literal connection to locale, it won't be confused with a digit in a monospace font the way a lowercase letter might, and it stands out, so the use of the locale is hard to miss. Today's rule is in [[format.string.std#17]]: the context's locale is used only when `L` is written, and `L` is only valid for arithmetic types.

### How to extend to user types

Users specialize `std::formatter<T>` for their types, providing two members: `parse` reads the format spec after the colon, and `format` outputs the value according to the options read. P0645 explicitly chose specialization rather than finding a free function via argument-dependent lookup ([[g:argument-dependent-lookup|ADL]]), as `swap` does. The paper gives two reasons: the arguments to `parse` don't include the object being formatted, so finding it via ADL would need a dummy parameter; and the ADL approach compiles more slowly.

Separating `parse` and `format` is what made compile-time checking possible later in the design: `parse` depends only on the format string and the type, while `format` depends on the value. The details of writing a formatter are in [[format.formatter]], and there is a complete example later on this page.

### Code size: type erasure

Templates accept any argument types, at the cost that every combination of argument types might instantiate a whole set of formatting code. P0645's approach is to have the variadic `format` do just one thing: pack the arguments into a **type-erased** ([[g:type-erasure|type erasure]], see [[patterns/type-erasure]]) `format_args`, then call a non-template `vformat`:

```cpp
template<class... Args>
string format(format_string<Args...> fmt, Args&&... args) {
  return vformat(fmt.get(), make_format_args(args...));
}
```

Each argument in `format_args` is normalized to one of a dozen or so basic types, and user types call their formatter indirectly through a function pointer ([[format.arguments]]). The paper deliberately made `vformat` and `format_args` public interfaces, so users writing their own logging functions can use the same technique, rather than treating them as implementation details.

Size of the executable's `__text` section with Clang 23 + libc++ at `-O2`:

| Program | 1 call | 21 calls | Added per call, approx. |
|---|---|---|---|
| `printf("line %s %d\n", ...)` | 48 B | 544 B | 25 B |
| `cout << ... << ...` | 1.1 KB | 2.9 KB | 93 B |
| `std::print("line {} {}\n", ...)` | 46.2 KB | 52.5 KB | 320 B |

The implementations of `printf` and iostream are both in the system's dynamic libraries, so they start very small. libc++'s formatting code is in headers and comes into the program in full on first use, about 46 KB; after that each additional call adds only a few hundred bytes for packing arguments, rather than instantiating another set of formatting logic. The format strings of these 21 calls are all different but the argument types are the same; the content of a format string does not go into the type, so it causes no new instantiations.

### Performance

In the benchmarks P0645 reports, {fmt} converts integers to strings about 30% faster than `sprintf`, and much faster than `ostringstream`. Our measurements (under high load, taking the minimum of 5 rounds) point in the same direction:

| Per call (`"{} {}"` with a string and an `int`) | Time |
|---|---|
| `snprintf` into a buffer | 57 ns |
| `ostringstream` | 112 ns |
| `std::format` returning a `string` | 48 ns |
| `std::format_to_n` into a buffer | 43 ns |

Adding a `{:.3f}` floating-point value, the four take about 180, 340, 115 and 92 ns respectively. These numbers only describe libc++ on this machine; different standard library implementations vary a lot.

## Compile-time checking of format strings (P2216)

C++20's original rule was that when the format string is invalid, `format` throws `format_error` at run time. `std::format("{:d}", "I am not a number")` compiles and only fails at run time. Yet the vast majority of format strings are literals, known at compile time. [[P2216R3]] surveyed 100 `printf` calls in one codebase: 98 had literal format strings, and the other 2 were literals wrapped in a gettext macro.

### The consteval constructor

P2216 introduced no new language feature for format strings; it only changed the type of `format`'s first parameter. Here is a minimal version of the same trick, which only checks that the number of `{}` equals the number of arguments:

```cpp title="consteval-trick.cpp" run error
#include <cstddef>
#include <stdexcept>
#include <string_view>
#include <type_traits>

template <class... Args> struct fmt_string {
  std::string_view s;
  template <class T>
  consteval fmt_string(const T& t) : s(t) {
    std::size_t n = 0;
    for (std::size_t i = 0; i + 1 < s.size(); ++i)
      if (s[i] == '{' && s[i + 1] == '}') ++n;
    if (n != sizeof...(Args))
      throw std::logic_error("count mismatch");
  }
};

template <class... Args>
void log(fmt_string<std::type_identity_t<Args>...>,
         const Args&...) {}

int main() {
  log("{} {}", 1, 2);  // OK
  log("{}", 1, 2);     // error: not a constant expression
}
```

What makes it work is a combination of three rules:

1. The constructor is `consteval`, i.e. an [[g:immediate-function|immediate function]]. Calling it outside an immediate function context is an [[g:immediate-invocation|immediate invocation]], and an immediate invocation must be a constant expression, otherwise the program is ill-formed ([[expr.const.imm]]).
2. The implicit conversion of a string literal to `fmt_string` calls this constructor, so the conversion must be done at compile time.
3. If constant evaluation reaches a `throw`, the evaluation is not a constant expression. If the format string is wrong, the constructor reaches the `throw`, the program is ill-formed, and the compiler must diagnose it.

`std::type_identity_t` keeps the first parameter out of template argument deduction, so `Args` is deduced only from the later arguments (Question 2 on the [[format]] page explains why this is necessary). Change `consteval` to `constexpr` and this program compiles, with the wrong line throwing an exception at run time: initializing a parameter does not require constant evaluation.

The standard library's version is `basic_format_string` in [[format.fmt.string]]. Its constructor doesn't write a `throw`; ¶3 specifies the result directly:

!!! std
    A call to this function is not a core constant expression ([expr.const.core]) unless there exist args of types `Args` such that *str* is a format string for args.

    As long as the format string is invalid for these argument types, the call is not a core constant expression, so the immediate invocation fails and the program is ill-formed.

libc++'s implementation parses the whole format string during constant evaluation, calling the corresponding formatter's `parse` for each replacement field. So format specs of user types are also checked at compile time, provided `parse` is `constexpr`:

```cpp title="celsius.cpp" run ok
#include <format>
#include <print>

struct Celsius { double v; };

template <>
struct std::formatter<Celsius> {
  bool fahrenheit = false;
  constexpr auto parse(std::format_parse_context& ctx) {
    auto it = ctx.begin();
    if (it != ctx.end() && *it == 'F') { fahrenheit = true; ++it; }
    if (it != ctx.end() && *it != '}')
      throw std::format_error("Celsius: only F is accepted");
    return it;
  }
  auto format(Celsius c, auto& ctx) const {
    return fahrenheit
      ? std::format_to(ctx.out(), "{}°F", c.v * 9 / 5 + 32)
      : std::format_to(ctx.out(), "{}°C", c.v);
  }
};

int main() {
  std::println("{} = {:F}", Celsius{100}, Celsius{100});  // 100°C = 212°F
  // std::println("{:K}", Celsius{0});  // error: parse throws during constant evaluation
}
```

Uncomment the last line and Clang 23 reports `call to consteval function ... is not a constant expression`, with a note pointing at the `throw` in `parse`.

### Approaches considered

P2216 compared two scopes: checking only string literals, or checking every format string known at compile time (including `constexpr` variables). The final wording takes the latter: the constructor accepts any constant convertible to `string_view`.

The paper also records a choice the committee made: an invalid format string is not ill-formed, no diagnostic required (IFNDR); the compiler must report an error. The phrasing of ¶3 achieves this: failed constant evaluation is ordinary ill-formedness.

The earlier P0645 had already discussed compile-time checking. It acknowledged that format strings could be parsed at compile time with `constexpr` functions, but C++17 could not offer a satisfying interface: getting a format string into compile time would require every format string to be a type, and requiring users to write, or generate with macros, a type for each format string was unacceptable. The paper pinned its hopes on proposals for compile-time strings (such as [[P0424R1]], based on user-defined literals). C++20's `consteval` provided another path: the constructor reads the contents of the format string at compile time without encoding it into a type, and users still write ordinary string literals.

### Why it was a breaking change

C++20's original `format` accepted a `string_view`, so using a run-time string as the format string was valid. After P2216 such code is ill-formed:

```cpp title="runtime-string.cpp" run error
#include <format>
#include <string>

std::string f(const std::string& fmt) {
  return std::format(fmt, 1);  // error: fmt is not a constant
}
```

Invalid format strings that used to throw at run time are now compile errors too. Annex C's [[diff.cpp20.utilities#1]] records both kinds of change, along with the other half of P2216: removing `format_args_t`, so that `vformat_to` no longer instantiates a separate copy of code for each output iterator type.

The committee still treated P2216 as a defect report against C++20. The paper's reasoning was that no standard library had implemented C++20 formatting yet, so very little existing code was affected. libc++ performs the compile-time check under `-std=c++20` as well.

## Format strings known only at run time

Format strings in translation files are only known at run time. After P2216, the way to handle them in C++20 and C++23 is to call the type-erased layer directly:

```cpp title="runtime-format.cpp" run ok
#include <cstdio>
#include <format>
#include <string>

std::string translate(const char* key) {  // a hypothetical translation table
  return std::string(key) == "found" ? "Found {} files, {} bytes in total" : key;
}

int main() {
  std::string fmt = translate("found");
  int files = 3, bytes = 1024;

  auto a = std::vformat(fmt, std::make_format_args(files, bytes));
  auto b = std::format(std::dynamic_format(fmt), files, bytes);  // C++26
  std::puts(a == b ? a.c_str() : "mismatch");

  try {
    (void)std::format(std::dynamic_format(translate("{:d}")), "x");
  } catch (const std::format_error& e) {
    std::puts(e.what());  // the error is deferred to run time
  }
}
```

`vformat` was meant as a low-level interface for people writing formatting functions, and using it directly has a trap. `make_format_args` only stores references to its arguments; the example [[P2905R2]] gives is:

```cpp
auto args = std::make_format_args(path.string());  // refers to a temporary string
std::string msg = std::vformat(str, args);         // the temporary has been destroyed
```

P2905 changed the parameters of `make_format_args` from forwarding references to lvalue references, so passing an rvalue is simply ill-formed; it applies to C++23 as a defect report. libc++ rejects `std::make_format_args(42)`, with a note saying `expects an lvalue`. So the example above must store the argument in a variable first.

[[P2918R2]] also provided a spelling aimed at users: `std::format(std::runtime_format(s), args...)`. `runtime_format` returns an exposition-only type for which `basic_format_string` has a non-`consteval` constructor; the check is deferred to run time and throws `format_error` on failure. This type cannot be copied and can only be passed directly to a formatting function.

After C++23, [[P3391R2]] made `std::format` usable during constant evaluation, so the name `runtime` became inaccurate: a format string using it might still be processed at compile time. [[P3953R3]] renamed it `std::dynamic_format`; as the paper puts it, the real distinction is not when formatting happens but how the format string is supplied and when it is checked. Since `runtime_format` was itself new in C++26, the rename did not affect any published standard. libc++ provides only `std::dynamic_format`.

## std::print (P2093)

With C++20's `std::format`, printing to a terminal still meant writing `std::cout << std::format(...)`: first constructing a temporary `string`, then handing it to iostream for another formatted output. [[P2093R14]] proposed `std::print` and `std::println`, which format and output in a single call.

### Where it writes

After surveying other languages, the paper had `print` write to C's `stdout` by default, with another overload taking a `FILE*`; the overload taking an `ostream&` lives in `<ostream>`, and the rest in a new header `<print>`, so that using `print` doesn't require including the heavy `<ostream>`. A member function form `std::cout.print(...)` was considered more awkward and not adopted. `print` does not add a newline automatically, consistent with `printf`; `println` is provided separately.

The wording of `println(FILE*, ...)` in [[print.fun]] (¶5) is straightforward: append `'\n'` to `fmt.get()` to form a new string, and pass it to `print` with `dynamic_format`. The resulting format string is no longer a constant, but the original format string has already been checked at compile time.

Measurements (output redirected to `/dev/null`, iostream/stdio synchronization turned off, minimum of 5 rounds):

| Per call | `"{} {}\n"` | Plus `{:.3f}` |
|---|---|---|
| `printf` | 78 ns | 200 ns |
| `cout <<` | 140 ns | 368 ns |
| `std::print` | 76 ns | 151 ns |

### Mojibake on the Windows console

The other half of P2093 is encoding. The Windows console interprets bytes according to a legacy code page (such as 437) by default, so even if a program is compiled with `/utf-8` and all its literals are UTF-8, Chinese text output through `cout` still comes out garbled. The paper's design:

1. If the ordinary literal encoding ([[g:literal-encoding|literal encoding]], i.e. the encoding of string literals in the program) is UTF-8, `print` calls `vprint_unicode`, otherwise `vprint_nonunicode` ([[print.fun#2]]). A UTF-8 literal encoding indicates that the program's author is writing text in UTF-8.
2. When `vprint_unicode` finds that the destination is a terminal that can only display Unicode through a native Unicode API, it flushes the stream first and then writes using that API ([[print.fun#10]]). A note says that on Windows this is `WriteConsoleW`. When output is redirected to a file or pipe, the bytes are written as-is, without conversion.
3. Invalid code units in the output give undefined behavior; ¶12 recommends that implementations that need to transcode replace them with U+FFFD.

The paper considered Java's approach: converting output to the current code page. It concluded that this loses characters that cannot be represented and adds conversion overhead, so it chose, like C, Go and Rust, to keep the original encoding and convert only at the terminal. The test machine is macOS, where the terminal already displays UTF-8, so the ¶10.1 branch is never taken and this part could not be verified.

### Follow-up: writing directly into the stream's buffer

C++23's wording specifies that `print` first formats into a temporary `string` and then writes it out. [[P3107R5]] pointed out that this rules out an implementation that, like `printf`, formats directly into the buffer while holding the stream's lock, which saves an allocation and was 42% to 72% faster in the paper's benchmarks.

The difficulty with writing directly is that the user's formatter runs while the stream is locked: if it takes some lock held by another thread, while that thread is waiting for the same stream, there is a deadlock. So P3107 makes this optimization opt-in: the variable template `enable_nonlocking_formatter_optimization<T>` defaults to `false` ([[format.formatter.locking#1]]), and is `true` for the formatters of standard types. Today's [[print.fun#2]] chooses on that basis: if every argument type has opted in, it calls `vprint_unicode`, which writes directly; otherwise it calls `vprint_unicode_buffered`, which formats into a `string` first. The paper chose a variable template rather than a member of the formatter because when one formatter inherits from another, the value of a variable template is not inherited along with it.

## Formatting ranges (P2286)

C++20's `std::format` could not print a `vector` directly. {fmt} had long supported it, but formatters for standard types can only be provided by the standard library: by [[namespace.std#2]], a specialization added by a program must depend on at least one program-defined type, which `formatter<std::vector<int>>` does not. [[P2286R8]] filled this gap:

```cpp title="ranges.cpp" run ok
#include <map>
#include <print>
#include <ranges>
#include <set>
#include <string>
#include <vector>

int main() {
  std::vector<int> v{1, 2, 3};
  std::vector<std::string> w{"a", "b c", "\t"};
  std::map<std::string, int> m{{"x", 1}, {"y", 2}};

  std::println("{}", v);               // [1, 2, 3]
  std::println("{::#x}", v);           // [0x1, 0x2, 0x3]
  std::println("{:n}", v);             // 1, 2, 3
  std::println("{}", w);               // ["a", "b c", "\t"]
  std::println("{}", m);               // {"x": 1, "y": 2}
  std::println("{}", std::set{3, 1});  // {1, 3}
  std::println("{}", v | std::views::transform(
                         [](int i) { return i * i; }));  // [1, 4, 9]
  std::println("{:?s}", std::vector{'h', 'i', '\n'});    // "hi\n"
}
```

The comments are libc++'s actual output. The main decisions in the paper:

- Brackets: `[]` for sequences, `()` for `pair` and `tuple`, `{k: v}` for maps, `{}` for sets, consistent with Python and {fmt}. The paper compared `{}` versus `[]` for sequences and `{}` versus `()` for tuples.
- Strings are quoted and escaped by default. `["a", "b c", "\t"]` shows each element's boundaries and any invisible characters; without quotes, a vector with one element `"a, b"` and a vector with two elements `"a"` and `"b"` would both print `[a, b]`. For this a new `?` type specifier was added (debug format, see [[format.string.escaped]]), and a container's formatter calls `set_debug_format()` on the element formatter when the element has no format spec.
- The element format spec goes after a second colon. In `{::#x}`, the first part applies to the whole range (fill, alignment, width, `n` to drop the brackets), and the second part, `#x`, is passed as-is to the element formatter. Writing an explicit empty element spec, `{::}`, turns off the quotes on strings.
- `pair` and `tuple` do not support per-element format specs. Earlier revisions tried, but any character can appear in a format string, so there was no reliable separator, and it was withdrawn.
- In the end the paper did not add a separate `format_join`; instead it made the class template `range_formatter` public, with `set_separator`, `set_brackets` and `underlying()`, and the formatters for maps and sets are built from it.

Whether a range is printed as a sequence, map, set or string is decided by the variable template `format_kind<R>` ([[format.range.fmtkind#2]]). ¶2.1 handles an edge case: the element type of `std::filesystem::path` is `path` again, so formatting it as a range would make the `formattable` check recurse infinitely, and such ranges are disabled. Details are in [[format.formatter]]; the design of ranges themselves is in [[topics/ranges-design]].

## Where the wording went

| Contents | Subclause | Source |
|---|---|---|
| Format string syntax, standard format specs, `L` | [[format.string]], [[format.string.std#17]] | P0645, P1892 |
| The consteval constructor of `basic_format_string` | [[format.fmt.string#3]] | P2216 |
| `dynamic_format` | [[format.fmt.string]], [[format.syn]] | P2918, P3953 |
| `make_format_args` accepts only lvalues | [[format.arg.store]] | P2905 |
| The `parse`/`format` contract of `formatter` | [[format.formatter]] | P0645 |
| Formatting ranges | [[format.range]] | P2286 |
| `print`, `println`, `vprint_unicode` | [[print.fun]], [[ostream.formatted.print]] | P2093, P3107 |
| Compatibility | [[diff.cpp20.utilities#1]] | P2216 |

Paragraph-by-paragraph explanations of the parts of the formatting library are in [[format]], [[format.string]] and [[format.formatter]]. Where `<format>` sits in the evolution of the standard library as a whole is in [[history/modern-library]].

## Compiler support

Status with Clang 23.1.3 + libc++:

| Feature | Result |
|---|---|
| `std::format`, custom formatters | Supported, `__cpp_lib_format` is `202110L` |
| Compile-time format string checking | Supported, also in effect under `-std=c++20` |
| `std::print`, `std::println` | Supported, `__cpp_lib_print` is `202207L` |
| Formatting ranges, `pair`/`tuple` | Supported, `__cpp_lib_format_ranges` is `202207L` |
| `make_format_args` rejecting rvalues | Supported, also in effect under `-std=c++23` |
| `std::dynamic_format` | Supported; no `std::runtime_format` |
| Calling `std::format` in constant expressions | Not supported (see [[format]]) |

`__cpp_lib_format` stops at `202110L`, older than what is actually implemented, so on libc++ this macro alone cannot tell you whether `dynamic_format` is available. GCC and MSVC were not tested.

## Questions

!!! question "1. Replacing consteval with constexpr"
    If the constructor of `basic_format_string` were only `constexpr` rather than `consteval`, what would happen with `std::format("{:d}", "x")`?

<details markdown="1">
<summary>Answer</summary>

The program would compile and throw `format_error` at run time. A `constexpr` function is merely allowed to be called during constant evaluation; initializing a function parameter with a string literal is not a context that requires constant evaluation, so the compiler would run the constructor at run time. `consteval` makes the call an immediate invocation, which [[expr.const.imm]] requires to be a constant expression, and that is what forces the check to compile time. Change `consteval` to `constexpr` in this page's `consteval-trick.cpp` and Clang 23 compiles it, with the wrong line throwing `logic_error` at run time.

</details>

!!! question "2. Quotes on strings"
    `std::println("{}", std::vector<std::string>{"a"})` prints `["a"]`. How do you get `[a]`? Why are quotes added by default?

<details markdown="1">
<summary>Answer</summary>

Write `std::println("{::}", v)`. What follows the second colon is the format spec for elements; writing an explicit empty spec means the container's formatter no longer calls `set_debug_format()` on the elements. Quotes are added by default to make the output unambiguous: elements may contain commas, spaces or newlines, and without quotes the element boundaries can't be seen ([[P2286R8]]).

</details>

!!! question "3. Why print looks at the literal encoding"
    `std::print` chooses `vprint_unicode` based on whether the ordinary literal encoding is UTF-8. Why not look at the run-time locale?

<details markdown="1">
<summary>Answer</summary>

Format strings are almost always literals, and the literal encoding describes the encoding of the text the program's author wrote, which is fixed at compile time. `std::format` itself is designed not to depend on the locale (when `L` is not written), and width estimation likewise follows a locale-independent encoding ([[format.string.std#12]]). Deciding by the run-time locale would make the same program interpret the same bytes differently in different environments. This is the reasoning [[P2093R14]] gives.

</details>
