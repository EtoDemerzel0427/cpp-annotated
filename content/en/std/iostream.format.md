---
title: Formatting and manipulators
summary: "The exact effects of the parameterized manipulators in <iomanip> (setw, setprecision, setfill, setbase, setiosflags, resetiosflags, get_time, put_money, quoted and others), and how std::print and std::println write to C FILE* streams."
updated: 2026-10-19
---

!!! tldr
    - `out << std::setw(n)` behaves as if calling `out.width(n)`. The return types of the parameterized manipulators are unspecified; each one calls a setter on the stream and returns the stream itself.
    - These settings stay in effect, except width: an inserter resets it to zero after using it once. `setw` also works on string input, limiting the number of characters read.
    - `setbase` recognizes only 8, 10 and 16; any other value clears the base flags: output is decimal, and input detects the base from a `0x` or `0` prefix.
    - `quoted` adds quotes and escapes to a string, so a string containing spaces or quotes reads back unchanged after insertion; `setw` applies to the whole quoted result.
    - `std::print(FILE*, ...)` checks the format string at compile time, throws `system_error` on write failure, and writes in one go while holding the stream's lock; when the literal encoding is UTF-8, it uses the native Unicode API on a Windows console.

The standard's [iostream.format] specifies `basic_istream`, `basic_ostream`, all the manipulators, and `std::print`. This site splits it into three pages: this page covers the `<iomanip>` manipulators and the `print` that writes to `FILE*`; `basic_istream` is in [[input.streams]], and `basic_ostream`, `endl` and the `print` that writes to an `ostream` are in [[output.streams]]. Manipulators without parameters (`hex`, `fixed`, `boolalpha` and so on) are in [[iostreams.base]].

## Parameterized manipulators [std.manip]

```cpp title="setbase-zero.cpp" run ok
#include <iomanip>
#include <iostream>
#include <sstream>

int main() {
  std::istringstream in("0x1A 017 42");
  int a, b, c;
  in >> std::setbase(0) >> a >> b >> c;   // base detected from the prefix
  std::cout << a << ' ' << b << ' ' << c << '\n';  // 26 15 42
  std::cout << std::setbase(2) << 5 << '\n';       // 5: in decimal
}
```

Neither `setbase(0)` nor `setbase(2)` is an error. ¶4 specifies the effect of `setbase(base)` as if:

```cpp
str.setf(base ==  8 ? ios_base::oct :
         base == 10 ? ios_base::dec :
         base == 16 ? ios_base::hex :
         ios_base::fmtflags(0), ios_base::basefield);
```

So any value other than 8, 10 or 16 clears all the base flags in `basefield`. On output, a zero `basefield` means decimal. On input, with a zero `basefield`, `num_get` detects the base from the prefix like C's `strtol(s, end, 0)`: `0x` is hexadecimal and a leading `0` is octal ([[facet.num.get.virtuals]]). `resetiosflags(std::ios_base::basefield)` has the same effect.

### One pattern for six manipulators

¶1 Each of these `<iomanip>` functions returns an object `m` of unspecified type. `out << m` behaves as if calling some function `f(out, args)`, and the expression has the type and value of `out` itself; likewise for `in >> m`.

| Manipulator | What `f` does | For output | For input |
|---|---|---|---|
| `resetiosflags(mask)` | ¶2 `str.setf(fmtflags(0), mask)`, clearing the flags in `mask` | yes | yes |
| `setiosflags(mask)` | ¶3 `str.setf(mask)` | yes | yes |
| `setbase(base)` | ¶4 see above | yes | yes |
| `setfill(c)` | ¶5 `str.fill(c)`; the type of `c` must be the stream's character type | yes | no |
| `setprecision(n)` | ¶6 `str.precision(n)` | yes | yes |
| `setw(n)` | ¶7 `str.width(n)` | yes | yes |

A footnote gives the example that `cin >> resetiosflags(ios_base::skipws)` has the same effect as `cin >> noskipws`.

All of these settings persist until changed again. The one exception is width: the inserters for strings, characters and numbers call `width(0)` after each use, so `setw` applies only to the next insertion ([[output.streams]]).

### `setw` works for input too

```cpp title="setw-input.cpp" run ok
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>

int main() {
  std::istringstream in("abcdefgh");
  std::string a, b;
  in >> std::setw(3) >> a >> b;     // setw applies only to the next extraction
  std::cout << a << ' ' << b << '\n';   // abc defgh
}
```

On an input stream, the width limits the maximum number of characters read into a `std::string` ([[string.io]]) or a character array ([[input.streams]]), and it is likewise reset to zero after one use.

### What an unspecified return type means

`auto m = std::setw(5);` is legal, but you cannot name the type of `m`, nor assume it combines with anything other than `<<` and `>>`. Implementations usually return a small struct holding the argument and overload `<<` and `>>` for it.

The struct for `setfill` is a template on the character type, so overload resolution simply fails when the character types do not match:

```cpp title="setfill-wide.cpp"
#include <iomanip>
#include <iostream>

int main() {
  std::wcout << std::setfill('*');   // error with libc++: '*' is a char
  std::wcout << std::setfill(L'*');  // OK
}
```

¶5 specifies the effect only when the type of `c` is the stream's `charT`; for the first line it specifies no behavior at all. With Clang 23 + libc++ it is rejected with "invalid operands"; writing `L'*'` is the portable form.

## Money and time [ext.manip]

```cpp title="get-put-time.cpp" run ok
#include <ctime>
#include <iomanip>
#include <iostream>
#include <sstream>

int main() {
  std::tm t{};
  std::istringstream in("2026-10-18 09:30");
  in >> std::get_time(&t, "%Y-%m-%d %H:%M");
  if (!in) { std::cout << "parse failed\n"; return 1; }
  std::cout << std::put_time(&t, "%d/%m/%Y %H:%M") << '\n';
  // 18/10/2026 09:30
}
```

¶1 These four manipulators parse and format monetary values and times. They hand all the work to the corresponding facets in the stream's locale ([[locale.categories]]) and read and write the stream buffer directly through `istreambuf_iterator` and `ostreambuf_iterator`.

| Manipulator | Precondition | Effect | On failure |
|---|---|---|---|
| `get_money(mon, intl)` | ¶2 `mon` is a `long double` or some `basic_string` | ¶3–¶4 as a formatted input function, calls `money_get::get` | sets the error bits reported by `get` |
| `put_money(mon, intl)` | ¶5 same as above | ¶6 as a formatted output function, calls `money_put::put` | sets `badbit` |
| `get_time(tmb, fmt)` | ¶7 `tmb` points to a valid `tm`, `fmt` is a null-terminated format string | ¶8 calls `time_get::get` | sets the error bits reported by `get` |
| `put_time(tmb, fmt)` | ¶9 same as above | ¶10 calls `time_put::put` | sets `badbit` |

When `intl` is true the international currency format is used (such as `USD `); when false, the local symbol (such as `$`). `fmt` is a `strftime`-style format string. For formatting times in new code, `<chrono>` with `std::format` ([[time]]) is preferable: they are type-safe and do not depend on `tm`.

## `quoted`: round-tripping strings [quoted.manip]

```cpp title="quoted-roundtrip.cpp" run ok
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>

int main() {
  std::string in = R"(say "hi" \ bye)";

  std::stringstream plain;
  plain << in;
  std::string w;
  plain >> w;
  std::cout << w << '\n';            // say: >> stops at whitespace

  std::stringstream ss;
  ss << std::quoted(in);
  std::cout << ss.str() << '\n';     // "say \"hi\" \\ bye"
  std::string out;
  ss >> std::quoted(out);
  std::cout << (out == in) << '\n';  // 1: restored unchanged
}
```

A plain `>>` stops at whitespace, so a string containing spaces is truncated when written to a stream and read back. The note in ¶1 explains that `quoted` is designed for exactly this round trip, for example reading and writing quoted fields in XML or CSV.

### Output (¶2)

¶2 `out << quoted(s, delim, escape)` is a formatted output function. `delim` defaults to `"` and `escape` to `\`. It first forms a character sequence `seq`:

1. one `delim`;
2. each character of `s`, preceded by an `escape` if the character equals `escape` or `delim`;
3. one `delim`.

Then the whole `seq` is padded according to the stream's width, and `width(0)` is called. So `setw` applies to the whole result after quoting and escaping. All three overloads, taking `const charT*`, `const basic_string&` and `basic_string_view`, can be used for output.

### Input (¶3)

¶3 Only the overload taking a non-const `basic_string&` can be used for input. `in >> quoted(s, delim, escape)` first extracts one character with `in >> c`; this step skips leading whitespace as usual.

- ¶3.1.1 If that character is `delim`: `skipws` is temporarily turned off and `s` is cleared; characters are extracted one by one and appended to `s` until an unescaped `delim` is reached or the stream fails; an `escape` is discarded and the next character appended as is; finally the closing `delim` is discarded and `skipws` restored.
- ¶3.1.2 Otherwise it is equivalent to `in >> s`: unquoted input is read as an ordinary string.

`std::filesystem::path`'s `<<` and `>>` are defined in terms of `quoted` ([[fs.class.path]]), which is why `std::cout << path` prints a quoted path.

## `print` and `println` to C streams [print.fun]

```cpp title="print-file.cpp" run ok
#include <cstdio>
#include <print>

int main() {
  std::print("{} {}\n", "to", "stdout");
  std::println(stderr, "error code {:#x}", 255);   // error code 0xff
  std::println();                                   // outputs only a newline
  std::println("{:>6.2f}|{:<4}|{:^5}|", 3.14159, 'x', true);
  //   3.14|x   |true |
}
```

`<print>` depends only on C's `FILE*`; it does not need iostreams. The format string syntax is the same as for `std::format` ([[format.string]]).

### How the functions relate

- ¶1, ¶3, ¶4 The versions without a `FILE*` all write to `stdout`.
- ¶5 `println(stream, fmt, args...)` is equivalent to appending a `'\n'` to the format string and calling `print`, so the newline is output together with the content. ¶6 `println(stream)` outputs just a newline.
- ¶2 `print(stream, fmt, args...)` calls the `vprint_unicode` family if the ordinary literal encoding ([[lex.charset]]) is UTF-8, and the `vprint_nonunicode` family otherwise.

¶2 contains one more choice: let `locksafe` be the conjunction of `enable_nonlocking_formatter_optimization` over all argument types. If `locksafe` is true, it calls `vprint_unicode(stream, ...)` directly; otherwise it calls `vprint_unicode_buffered`.

¶8 `vprint_unicode_buffered` first `vformat`s into a `string` without holding the lock, then hands that string to `vprint_unicode` to write out. The two paths exist because `vprint_unicode` formats while holding the stream's lock. If some argument's `formatter` is slow, or itself writes to the same stream, formatting under the lock can slow other threads down or even deadlock. `enable_nonlocking_formatter_optimization` defaults to `false` for user types, so user types take the format-first-then-lock path by default ([[format.formatter]]). ¶14 `vprint_nonunicode_buffered` is analogous.

### `vprint_unicode` and the Windows console (¶9–¶12)

¶9 The precondition is that `stream` points to a C stream open for output.

¶10 The function locks `stream`, then formats `args` according to `fmt` into `out`:

- ¶10.1 If `stream` refers to a terminal that is capable of displaying Unicode only via a native Unicode API, it flushes `stream` and then writes `out` using the native API. If `out` contains invalid code units, the behavior is undefined {{ub}}. After writing, it establishes an [[g:observable-checkpoint|observable checkpoint]] ([[intro.abstract]]) {{c++26}}.
- ¶10.2 Otherwise it writes `out` to `stream` unchanged.

The function unconditionally unlocks on exit. Note 1 explains that on Windows the native Unicode API is `WriteConsoleW`, and the way to determine whether it refers to a terminal is that `GetConsoleMode(_get_osfhandle(_fileno(stream)), ...)` returns non-zero.

On POSIX systems a terminal is just a byte stream; UTF-8 bytes written directly display correctly, and the two paths do not differ. The Windows console, however, interprets bytes according to the current code page; if the code page is not UTF-8, writing UTF-8 bytes directly shows garbage. `vprint_unicode` detects the console and writes UTF-16 with `WriteConsoleW` instead, so `std::print("你好\n")` displays correctly on such a console, where `printf` and `cout` do not.

¶11 Exceptions thrown by `vformat` propagate as usual ([[format.err.report]]); failure to write to the terminal or stream throws `system_error`; `bad_alloc` may also be thrown. ¶12 recommends that implementations replace invalid code units with U+FFFD when transcoding.

¶15–¶17 `vprint_nonunicode(stream, ...)` writes the formatted result to `stream` while holding the lock, without detecting terminals or transcoding. The exception specification is the same.

### Differences from `printf` and `cout`

- Error reporting: `print` throws `system_error` when a write fails; `printf` returns a negative value, and `cout` sets `badbit`.
- Format checking: `print`'s format string is checked at compile time ([[format]]); a mismatch between `printf`'s format and arguments is {{ub}}, detectable only through compiler warnings.
- Atomicity: `print(stdout, ...)` writes the whole result while holding the stream's lock, so output from other threads through the same `FILE*` cannot land in the middle; `cout << a << b` is several independent calls.
- Mixing with `cout`: `print` writes to `stdout`. In the default synchronized state its output is ordered consistently with `cout`'s; after `sync_with_stdio(false)` the order is not guaranteed ([[iostream.objects]]).

!!! impl "The state of libc++"
    libc++ (Clang 23) provides `std::print` and `std::println`, but `__cpp_lib_print` is still `202207L`, while the current draft says `202406L`. `<print>` has no `vprint_unicode_buffered` or `vprint_nonunicode_buffered`, meaning the `locksafe` dispatch is not implemented yet. On non-Windows platforms its `vprint_unicode` writes bytes directly.

## The headers at a glance [istream.syn] [ostream.syn] [iomanip.syn] [print.syn]

- `<istream>` declares `basic_istream` (aliases `istream`, `wistream`), `basic_iostream` (`iostream`, `wiostream`), the manipulator `ws`, and rvalue stream extraction; see [[input.streams]].
- `<ostream>` declares `basic_ostream` (`ostream`, `wostream`), the manipulators `endl`, `ends`, `flush`, the `emit_on_flush`, `noemit_on_flush` and `flush_emit` that serve [[syncstream]], rvalue stream insertion, and the `print`, `println`, `vprint_unicode` and `vprint_nonunicode` that accept only `ostream&` (i.e. `char` streams); see [[output.streams]].
- `<iomanip>` declares all the parameterized manipulators covered on this page, all with unspecified return types.
- `<print>` declares the `print` and `println` that write to `FILE*`, and the six `vprint_*` functions.

## Questions

!!! question "Question 1"
    How many characters does `std::cout << std::setw(10) << std::quoted("a b");` output? Do the quotes count toward the width?

<details markdown="1">
<summary>Answer</summary>

10. [[quoted.manip#2]] specifies that the complete sequence `seq`, including the two quotes and any escape characters, is formed first, here `"a b"`, 5 characters, and then the whole `seq` is padded to the width. So the output is 5 spaces followed by `"a b"`.
</details>

!!! question "Question 2"
    After `std::istringstream("  \"x y\" z") >> std::quoted(s)`, what is `s`? What is left in the stream?

<details markdown="1">
<summary>Answer</summary>

`s` is `x y`, and ` z` is left in the stream. The first character is extracted with `operator>>(istream&, char&)`, a formatted input function that skips leading whitespace first, yielding `"`. So it enters quoted mode, reads up to an unescaped `"`, and discards it ([[quoted.manip#3]]).
</details>
