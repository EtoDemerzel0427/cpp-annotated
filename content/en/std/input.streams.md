---
title: "Input streams: basic_istream"
summary: "How basic_istream reads: what the sentry prepares before each input, the rules and error states of formatted input (>>) and unformatted input (get, getline, read and so on), what you get when numeric parsing fails or overflows, and common traps such as eof loops, getline after >>, and reading uint8_t."
updated: 2026-10-19
---

!!! tldr
    - Every input first constructs a sentry: if the stream is not in a good state it adds `failbit` and gives up; otherwise it flushes the tied output stream (`cin` is tied to `cout`), and for formatted input it also skips leading whitespace.
    - Formatted input (`>>`) skips whitespace and parses according to the locale; failure bits are first recorded in a local error state and written back to the stream once at the end. Unformatted input (`get`, `getline`, `read` and so on) does not skip whitespace, and records how many characters it read in `gcount()`.
    - Numeric parsing is handed to `num_get`: malformed input gives 0, out-of-range input gives the type's maximum or minimum, and both set `failbit`.
    - A read loop should be `while (in >> x)`, not `while (!in.eof())`. Before calling `getline` after `>>`, use `std::ws` to eat the leftover newline.
    - A failed putback (`putback`, `unget`) sets `badbit`; `tellg` returns −1 when `eofbit` is already set, whereas `seekg` clears `eofbit` first.

## Why `while (!in.eof())` is wrong

```cpp title="eof-loop.cpp" run ok
#include <iostream>
#include <sstream>

int main() {
  std::istringstream a("1 2 3\n");
  int x, sum = 0, n = 0;
  while (!a.eof()) {           // wrong loop condition
    a >> x;
    sum += x; ++n;
  }
  std::cout << "wrong: n=" << n << " sum=" << sum << '\n';  // n=4 sum=9

  std::istringstream b("1 2 3\n");
  sum = n = 0;
  while (b >> x) { sum += x; ++n; }   // condition is the success of the extraction itself
  std::cout << "right: n=" << n << " sum=" << sum << '\n';  // n=3 sum=6
}
```

After `3` is read, a `'\n'` still follows. `num_get` stops parsing when it sees it and does not hit the end of the stream, so `eof()` is still false. The fourth `>>` first skips the `'\n'` and only then hits the end, so it sets `failbit` and `eofbit`, `x` stays 3, and the loop body adds 3 once more.

`eofbit` only says that some read hit the end of the stream; it cannot predict whether the next read will succeed. To see exactly what happens at each step, we first need to look at the preparation done before each input.

## The sentry: preparation before each input [istream.sentry]

The **sentry** is a nested class of `basic_istream` that performs the fixed steps before and after each input. Every input function begins by constructing a sentry object and then checks its conversion to `bool` to decide whether to go on reading.

```cpp
class basic_istream<charT, traits>::sentry {
  bool ok_;                       // exposition only
public:
  explicit sentry(basic_istream& is, bool noskipws = false);
  ~sentry();
  explicit operator bool() const { return ok_; }
  sentry(const sentry&) = delete;
  sentry& operator=(const sentry&) = delete;
};
```

¶2 The constructor does three things in order:

1. If `is.good()` is false, it calls `is.setstate(failbit)` and the preparation is over. That is, when the stream is already in any error state, even just with `eofbit` set, the next input adds `failbit`.
2. Otherwise, if `is.tie()` is non-null, it calls `is.tie()->flush()`. `cin` is tied to `cout` by default, so the prompt on screen is always output before input is read ([[iostream.objects]]). The flush may be skipped if the tied stream's put area is empty; an implementation may also defer it until data is actually needed from the device, that is, until `underflow()` is called.
3. If the parameter `noskipws` is false and the stream's `skipws` flag is set, it extracts and discards whitespace characters one by one. If it reaches the end of the stream, it calls `setstate(failbit | eofbit)`.

¶3–¶4 Whether a character is whitespace is decided by the `ctype` facet of the stream's current locale, as if by `use_facet<ctype<charT>>(is.getloc()).is(ctype.space, c)`.

¶5 After the preparation, `ok_` is true if `is.good()` is true, false otherwise. ¶6 The destructor has no effects; ¶7 `operator bool` returns `ok_`.

Step 3 explains a common observation: when only whitespace remains, `>>` sets both `eofbit` and `failbit`. The whitespace is eaten in the sentry, the end is hit, and parsing never even starts.

## Formatted input: `>>` [istream.formatted.reqmts]

The functions of `istream` fall into two groups ([istream.general] ¶3): [[g:formatted-input-function|formatted input functions]], also called **extractors**, and [[g:unformatted-input-function|unformatted input functions]]. Both obtain characters from the stream buffer via `rdbuf()->sbumpc()` or `rdbuf()->sgetc()` ([[stream.buffers]]).

¶1 Every formatted input function follows the same steps:

1. Create a **local error state** of type `iostate`, initially `goodbit`.
2. Construct a sentry with `noskipws = false`. If constructing the sentry throws or it converts to `false`, no read is attempted and the function returns.
3. Make a best effort to read the required input. If `sbumpc()` or `sgetc()` returns `eof()`, set `eofbit` in the local error state and stop reading.
4. If an exception is thrown during reading, set `badbit` in the local error state and write it into the stream; if `exceptions()` contains `badbit`, rethrow the exception, otherwise swallow it.
5. After reading, call `setstate` to write the local error state into the stream. This step may throw `ios_base::failure` according to `exceptions()`.

Accumulating the error bits and writing them back once at the end means at most one exception is thrown because of the state bits, and when it is thrown the stream's state is complete, for example `eofbit` and `failbit` are both visible.

`std::getline(istream&, string&)` and `operator>>(istream&, string&)` are not in this subclause but in [[string.io]]; they behave as an unformatted and a formatted input function respectively, following the rules here.

### Writing a custom extractor with a sentry

A custom `operator>>` that reads the stream buffer directly should construct a sentry itself; that gives it the same behavior as the standard extractors: skipping whitespace, flushing the tied stream, checking the state. The error bits are likewise written back once at the end:

```cpp title="hex-extractor.cpp" run ok
#include <cctype>
#include <iostream>
#include <sstream>

struct Hex { unsigned value = 0; };

std::istream& operator>>(std::istream& in, Hex& h) {
  std::istream::sentry s(in);            // skip whitespace, flush tie, check state
  if (!s) return in;
  std::ios_base::iostate err = std::ios_base::goodbit;   // local error state
  auto* sb = in.rdbuf();
  if (sb->sbumpc() != '0' || sb->sbumpc() != 'x')
    err |= std::ios_base::failbit;
  unsigned v = 0;
  int digits = 0;
  for (;;) {
    auto c = sb->sgetc();
    if (c == std::char_traits<char>::eof()) { err |= std::ios_base::eofbit; break; }
    if (!std::isxdigit(c)) break;
    v = v * 16 + (std::isdigit(c) ? c - '0' : std::tolower(c) - 'a' + 10);
    ++digits;
    sb->sbumpc();
  }
  if (digits == 0) err |= std::ios_base::failbit;
  else h.value = v;
  in.setstate(err);                      // written back once, may throw
  return in;
}

int main() {
  std::istringstream in("  0x1F 0xzz");
  Hex a, b;
  in >> a;
  std::cout << a.value << " ok=" << bool(in) << '\n';   // 31 ok=1
  in >> b;
  std::cout << "second ok=" << bool(in) << '\n';         // second ok=0
}
```

A simpler approach is usually to compose existing extractors, for example `in >> str` first and then parse `str`; the sentry is then the inner extractor's responsibility.

## Reading numbers [istream.formatted.arithmetic]

```cpp title="overflow-clamp.cpp" run ok
#include <iostream>
#include <sstream>

int main() {
  std::istringstream in("99999999999 abc");
  int x = 0, y = 5;
  in >> x;
  std::cout << x << ' ' << in.fail() << '\n';   // 2147483647 1
  in.clear();
  in >> y;
  std::cout << y << ' ' << in.fail() << '\n';   // 0 1
}
```

¶1 After the sentry, the extractors for `long`, `unsigned`, floating-point types, `bool`, `void*` and so on behave as if executing:

```cpp
using numget = num_get<charT, istreambuf_iterator<charT, traits>>;
use_facet<numget>(loc).get(*this, 0, *this, state, val);
```

where `loc` is the stream's locale and `state` is the local error state. The `istreambuf_iterator` constructed from the first argument bypasses `istream` and reads the stream buffer directly.

So how a number is parsed, when it fails, and what you get on failure are all decided by `num_get` ([[facet.num.get.virtuals]]):

- No usable character at all, for example reading `abc`: `val` is set to 0 and `failbit` is set.
- Out of range for the target type: `val` is set to the type's maximum or minimum, and `failbit` is set.
- A minus sign read into an unsigned type: `num_get` parses by the rules of `strtoull`, where the minus sign negates the result. In our tests, libc++ reads `"-1"` into an `unsigned` as `4294967295` without setting `failbit`.
- `bool`: without `boolalpha` only `0` and `1` are accepted; with `boolalpha` the `truename()` and `falsename()` of the locale's `numpunct` are accepted, by default `true` and `false`.

¶2–¶3 `num_get` has no overloads taking `short&` or `int&`, so these two extractors read into a `long` first and then check the range: if out of range, `failbit` is set and the result is the type's minimum or maximum.

¶4–¶6 {{c++23}} The extractors for extended floating-point types (such as `std::float16_t`, [[basic.fundamental]]) first read into a standard floating-point type no narrower than it, then check the range and convert. When the extended type is wider than `long double`, this extractor is conditionally-supported. Note 2 warns that two roundings may occur during conversion; when maximum precision is needed, use `from_chars` ([[charconv]]).

!!! pitfall "`std::uint8_t` reads a character"
    ```cpp title="uint8-read.cpp" run ok
    #include <cstdint>
    #include <iostream>
    #include <sstream>

    int main() {
      std::istringstream in("7");
      std::uint8_t c;
      in >> c;                        // reads the character '7'
      std::cout << int(c) << '\n';    // 55, not 7
    }
    ```

    `std::uint8_t` is usually an alias for `unsigned char`, and `>>` selects the overload that reads one character. The current draft moves the extractors for `signed char` and `unsigned char` to Annex D ([[depr.istream.extractors]]); this is post-C++23 wording {{deprecated}}, meant to let such code get diagnosed in the future. As of this writing, libc++ in our tests does not yet issue a deprecation warning for it. To read a number, read into an `int` first and convert.

## Other extractors [istream.extractors]

### Manipulators (¶1–¶6)

¶1–¶6 The three `operator>>` overloads taking function pointers are not formatted input functions: they construct no sentry and just call `pf(*this)`. So `in >> std::hex` takes effect even when the stream is in a failed state. The footnote's examples are `ws` and `dec`.

### Character arrays (¶7–¶11)

```cpp title="char-array.cpp" error
#include <iomanip>
#include <iostream>

int main() {
  char q[100];
  std::cin >> std::setw(20) >> q;   // OK
  char* p = new char[100];
  std::cin >> std::setw(20) >> p;   // error: no overload taking char* since C++20
}
```

¶7 The parameter of this extractor is an array reference `charT (&s)[N]`. If `width()` is greater than 0, at most `n = min(width(), N)` characters are stored (including the terminating null character), otherwise `n = N`. ¶8 Extraction continues until `n - 1` characters are stored, the end of the stream is reached, or the next character is whitespace. ¶9 Then a null character is stored and `width(0)` is called. ¶10 If no characters were extracted, `failbit` is set.

Before C++20 the parameter was `charT*`; the function could not know the buffer size and relied on `setw` to prevent overflow, so forgetting it meant a buffer overflow. Now `N` is deduced from the type and overflow is impossible; the price is that a `char*` can no longer be read with `>>` ([[diff.cpp17.input.output]]).

### A single character (¶12–¶13)

¶12 `in >> c` is a formatted input function, so it skips whitespace. If a character is available it is extracted and stored in `c`; otherwise `failbit` is set. To read the next character including whitespace, use `in.get(c)`, or apply `in >> std::noskipws` first.

### Reading into another stream buffer (¶14–¶16)

¶14 `in >> sb` (where `sb` is a `basic_streambuf*`) behaves as an unformatted input function. If `sb` is null, `failbit` is set. Otherwise characters are moved from `*this` into `sb`'s output sequence until the end of the stream, an insertion failure (the character is not extracted), or an exception (which is caught). ¶15 If no characters were inserted, `failbit` is set.

## Unformatted input [istream.unformatted]

### Common steps (¶1)

¶1 Unformatted input functions follow essentially the same steps as formatted input functions, with these differences:

- The sentry is constructed with `noskipws = true`, so whitespace is not skipped, but the stream state is still checked and the tied stream flushed.
- When the sentry fails, the extraction count is set to 0; functions that take a character array also store a null character in the first position of the array.
- If no exception occurs, the number of characters extracted is stored in a member, which is what `gcount()` returns.

¶2–¶3 `gcount()` returns the number of characters extracted by the last unformatted input member function, or `numeric_limits<streamsize>::max()` if that cannot be represented. Formatted input (`>>`) does not update it.

### `get` (¶4–¶17)

| Call | Behavior | Failure |
|---|---|---|
| `get()` | ¶4–¶5 extracts and returns one character; returns `eof()` if none is available | sets `failbit` if no character |
| `get(c)` | ¶6 extracts one character into `c` | same as above |
| `get(s, n, delim)` | ¶8–¶9 extracts and stores until `n - 1` are stored, the end of the stream is reached, or the next character is `delim` (not extracted); always appends a null character when `n > 0` | sets `failbit` if nothing was stored |
| `get(s, n)` | ¶11 i.e. `get(s, n, widen('\n'))` | |
| `get(sb, delim)` | ¶13–¶14 inserts characters into the stream buffer `sb`; same stop conditions, plus insertion failure and exceptions (caught, not rethrown) | sets `failbit` if nothing was inserted |
| `get(sb)` | ¶16 i.e. `get(sb, widen('\n'))` | |

The difference between `get(s, n)` and `getline(s, n)` is that `get` leaves the delimiter in the stream. When two consecutive `get(buf, n)` calls read two lines, the second immediately meets the `'\n'` left behind by the first, stores no characters, and so sets `failbit`.

### `getline` (¶18–¶24)

```cpp title="getline-array.cpp" run ok
#include <iostream>
#include <sstream>

int main() {
  std::istringstream in("abcd\nabcdefgh\n");
  char buf[5];
  in.getline(buf, sizeof buf);    // "abcd" is exactly 4 characters
  std::cout << buf << " gcount=" << in.gcount()
            << " fail=" << in.fail() << '\n';   // abcd gcount=5 fail=0
  in.getline(buf, sizeof buf);    // line too long: sets failbit after storing 4 characters
  std::cout << buf << " gcount=" << in.gcount()
            << " fail=" << in.fail() << '\n';   // abcd gcount=4 fail=1
}
```

¶18 `getline(s, n, delim)` extracts characters and stores them in `s`, checking the stop conditions in this order (¶19):

1. the end of the stream is reached;
2. the next character is `delim`: it is extracted but not stored, so it counts toward `gcount()`;
3. `n - 1` characters have been stored: `setstate(failbit)` is called.

Because the delimiter is checked before the length, a line that exactly fills the buffer does not set `failbit`. A footnote notes this differs from the historical AT&T implementation. ¶20 `failbit` is set only if no characters were extracted, so an empty line does not set `failbit`, since the newline was extracted. ¶21 A null character is always appended when `n > 0`.

¶23 The standard's example reads line by line with `while (cin.getline(buf, size) || cin.gcount())`. The `|| cin.gcount()` lets a truncated long line (which set `failbit` but extracted characters) also enter the loop body, where `cin.clear(cin.rdstate() & ~ios_base::failbit)` clears `failbit` so the rest of the line can be read. `eof()` being true means the last line had no newline.

### `ignore` (¶25–¶28)

¶25 `ignore(n = 1, delim = eof())` extracts and discards characters until `n` have been extracted, the end of the stream is reached (setting `eofbit`), or `delim` is encountered (and extracted). If `n` equals `numeric_limits<streamsize>::max()`, the count is unlimited. If `delim` is `eof()`, only the first two conditions apply.

¶27–¶28 {{c++26}} adds `ignore(n, char_type delim)`, provided only for `char` streams, equivalent to `ignore(n, traits::to_int_type(delim))`.

The second parameter of the old signature is `int_type`. On platforms where `char` is signed, `'\xA1'` converted to `int` is −95, while a character from the stream passed through `to_int_type` gives 161; the two never compare equal, and `ignore` reads all the way to the end of the stream. The new overload fixes this ([[diff.cpp23.io]]):

```cpp title="ignore-char.cpp" run ok
#include <iostream>
#include <sstream>
#include <string>

int main() {
  std::istringstream in("\xF0\x9F\xA4\xA1 Clown Face");
  in.ignore(100, '\xA1');            // stops after '\xA1'
  std::string rest;
  std::getline(in, rest);
  std::cout << '[' << rest << "]\n"; // [ Clown Face]
}
```

Annex C also points out that a call whose second argument is neither `int` nor `char`, such as `in.ignore(100, -1L)`, is now ambiguous and hence ill-formed. libc++ in our tests already provides this overload and enables it in all language modes.

### `peek`, `read`, `readsome` (¶29–¶34)

¶29–¶30 `peek()` reads but does not extract the current character. If the stream is not in a good state it returns `eof()`, otherwise `rdbuf()->sgetc()`.

¶31 `read(s, n)` extracts characters and stores them in `s` until `n` have been stored or the end of the stream is reached. On reaching the end it calls `setstate(failbit | eofbit)`; that is, reading fewer than `n` counts as failure, and the number actually read is obtained with `gcount()`.

```cpp title="read-short.cpp" run ok
#include <iostream>
#include <sstream>

int main() {
  std::istringstream r("xyz");
  char out[8];
  r.read(out, 8);       // only 3 characters
  std::cout << "gcount=" << r.gcount() << " eof=" << r.eof()
            << " fail=" << r.fail() << '\n';   // gcount=3 eof=1 fail=1
}
```

¶33–¶34 `readsome(s, n)` reads only characters already in the buffer and never waits for the device. If `rdbuf()->in_avail()` is −1 it sets `eofbit` and extracts nothing; if 0 it extracts nothing; if greater than 0 it extracts `min(in_avail(), n)`. It returns the number extracted. For a stream buffer that keeps the default `showmanyc()`, it always returns 0 when the get area is empty ([[stream.buffers]]).

### `putback`, `unget`, `sync` (¶35–¶39)

¶35, ¶37 `putback(c)` and `unget()` first clear `eofbit`, then construct a sentry; if the stream is not in a good state they set `failbit` and return. Otherwise they call `rdbuf()->sputbackc(c)` or `sungetc()`, and if `rdbuf()` is null or those return `eof()`, they set `badbit`. Note that it is `badbit`, not `failbit`. They extract no characters, so `gcount()` is 0 afterwards.

¶39 `sync()` does not affect `gcount()`. If `rdbuf()` is null it returns −1; otherwise it calls `rdbuf()->pubsync()`, and if that returns −1 it sets `badbit` and returns −1, otherwise it returns 0. For an input stream, what `sync` actually does is up to the stream buffer; for `basic_filebuf`, for example, the effect is implementation-defined ([[file.streams]]).

### `tellg`, `seekg` (¶40–¶45)

¶40–¶41 `tellg()` does not affect `gcount()`. After constructing the sentry, if `fail()` is true it returns `pos_type(-1)`, otherwise `rdbuf()->pubseekoff(0, cur, in)`.

¶42–¶45 `seekg(pos)` and `seekg(off, dir)` first clear `eofbit`; after constructing the sentry, if `fail()` is false they call `rdbuf()->pubseekpos(pos, in)` or `pubseekoff(off, dir, in)`, setting `failbit` on failure.

`seekg` clears `eofbit` first and `tellg` does not; this asymmetry is easy to trip over. Calling `tellg()` with `eofbit` set, the sentry sees the stream is not good, adds `failbit`, and so it returns −1:

```cpp title="tellg-at-eof.cpp" run ok
#include <iostream>
#include <sstream>
#include <string>

int main() {
  std::istringstream in("hello");
  std::string s;
  in >> s;                          // succeeds but hits the end: eofbit
  std::cout << in.fail() << ' ';    // 0
  std::cout << in.tellg() << ' ';   // -1: the sentry added failbit
  std::cout << in.fail() << '\n';   // 1
  in.clear();
  in.seekg(0);
  in >> s;
  std::cout << s << '\n';           // hello
}
```

## `ws`: skipping whitespace [istream.manip]

```cpp title="getline-after-extract.cpp" run ok
#include <iostream>
#include <sstream>
#include <string>

int main() {
  std::istringstream in("42\nAlice Smith\n");
  int age;
  std::string name;
  in >> age;
  std::getline(in, name);              // reads the empty rest of the line after 42
  std::cout << '[' << name << "]\n";   // []

  std::istringstream in2("42\nAlice Smith\n");
  in2 >> age;
  std::getline(in2 >> std::ws, name);  // eat whitespace first
  std::cout << '[' << name << "]\n";   // [Alice Smith]
}
```

After reading `42`, `>>` stops in front of the newline, and the `getline` that follows reads the empty string before that newline.

¶2 `ws` behaves as an unformatted input function, except that it does not affect `gcount()`. After constructing the sentry, it extracts the next character as long as it is whitespace, using the same criterion as the sentry. If it stops because there are no more characters, it sets only `eofbit`, not `failbit`. Compare `>>`: hitting the end while skipping whitespace sets both bits. ¶1 `ws` is a designated addressable function; a program may take its address.

## After a read fails

Once `failbit` is set, the sentry of every input operation fails immediately, and the stream appears stuck. To recover from bad input, first `clear()`, then discard the characters that caused the failure:

```cpp title="recover.cpp" run ok
#include <iostream>
#include <limits>
#include <sstream>

int main() {
  std::istringstream in("12 abc 34\n56");
  int x, sum = 0;
  while (true) {
    if (in >> x) { sum += x; continue; }
    if (in.eof()) break;                // really done
    in.clear();                         // clear failbit
    in.ignore(std::numeric_limits<std::streamsize>::max(), ' ');  // drop the bad word
  }
  std::cout << sum << '\n';   // 102
}
```

## Rvalue stream extraction [istream.rvalue]

```cpp
template<class Istream, class T>
  Istream&& operator>>(Istream&& is, T&& x);
```

¶1 Constraints: `is >> std::forward<T>(x)` is well-formed, and `Istream` is publicly and unambiguously derived from `ios_base`. ¶2 The effect is to execute `is >> std::forward<T>(x)` and then return `std::move(is)`.

Member `>>` (reading `int` and so on) could always be called on a temporary, but the `>>` for `std::string` and `char` are non-member functions whose first parameter is an lvalue reference, which cannot bind to a temporary. This overload makes `std::istringstream("abc") >> s` compile too. It returns `Istream&&` rather than `basic_istream&`, preserving the derived type, so since C++20 you can call `istringstream`'s own members directly on the result.

## Construction and `basic_iostream`

[istream.cons] ¶1–¶2 `basic_istream(sb)` initializes the base class with `basic_ios::init(sb)`, after which `gcount() == 0`. ¶4 The destructor performs no operations on `rdbuf()`.

¶3 The move constructor, and the move assignment and `swap` in [istream.assign], are all protected; they move or swap the `basic_ios` state and `gcount()`, but do not touch the stream buffer. `basic_istream` holds only a pointer to the stream buffer; the buffer is owned by derived classes such as `ifstream` and `istringstream`, which provide the public move operations and call `set_rdbuf` in them ([[iostreams.base]]).

[iostreamclass] `basic_iostream` derives from both `basic_istream` and `basic_ostream`, which share the same stream buffer. [iostream.cons] ¶1–¶2 The constructor initializes both base classes with the same `sb`, after which `rdbuf() == sb` and `gcount() == 0`. `basic_ios` is a virtual base class, so there is only one. [iostream.dest] The destructor likewise performs no operations on `rdbuf()`.

## Questions

!!! question "Question 1"
    The input is two spaces. For `int x`, what is the stream state after `in >> x`? What about `in.get()` instead? And `in >> std::ws`?

<details markdown="1">
<summary>Answer</summary>

`in >> x`: the sentry skips both spaces, hits the end of the stream, and sets `failbit | eofbit` ([[istream.sentry#2]]); `x` is unchanged.

`in.get()`: the sentry is constructed with `noskipws = true` and does not skip whitespace; it reads the first space and returns `' '`, and the stream state is still good.

`in >> std::ws`: after eating both spaces there are no more characters, so it sets only `eofbit`, not `failbit` ([[istream.manip#2]]), and `operator bool` is still true.
</details>

!!! question "Question 2"
    When fewer than `n` bytes remain at the end of a file, what does `while (in.read(buf, n)) process(buf, n);` do?

<details markdown="1">
<summary>Answer</summary>

It drops the last chunk of data. When `read` cannot read a full `n`, it calls `setstate(failbit | eofbit)` ([[istream.unformatted#31]]), the loop condition becomes false, and the last few bytes already read into `buf` are never processed. It can be rewritten as `while (in.read(buf, n) || in.gcount()) process(buf, in.gcount());`, the same idea as the standard's `getline` example.
</details>

!!! question "Question 3"
    Which bit does a failed `in.putback('x')` set? Is `if (in)` true or false afterwards?

<details markdown="1">
<summary>Answer</summary>

It sets `badbit` ([[istream.unformatted#35]]), not `failbit`, which means the expected input was not obtained. `fail()` is true when either `badbit` or `failbit` is set, so `if (in)` is false. To keep using the stream, `clear()` it first.
</details>

## Summary

| Category | sentry's `noskipws` | Skips whitespace | Updates `gcount` | Typical failure |
|---|---|---|---|---|
| Formatted `>>` (numbers, characters, arrays) | `false` | yes (with `skipws`) | no | malformed or out of range: `failbit`; only whitespace left: `failbit` and `eofbit` |
| Manipulator `>>` | not constructed | no | no | |
| `get`, `getline`, `read`, `ignore` | `true` | no | yes | nothing obtained: `failbit`; `read` falls short: `failbit` and `eofbit` |
| `putback`, `unget` | `true`, clears `eofbit` first | no | set to 0 | putback fails: `badbit` |
| `tellg` | `true`, does not clear `eofbit` | no | unaffected | stream not good: adds `failbit`, returns −1 |
| `seekg` | `true`, clears `eofbit` first | no | unaffected | positioning fails: `failbit` |
| `ws` | `true` | yes | unaffected | at the end only `eofbit` is set |
