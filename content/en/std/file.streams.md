---
title: File-based streams
summary: "How <fstream>'s basic_filebuf reads and writes files modeled on C's FILE: how open modes map to fopen mode strings, the rules for closing, seeking, flushing and encoding conversion, and how ifstream, ofstream and fstream report failure."
updated: 2026-10-19
---

!!! tldr
    - A file stream's open mode has `ate` removed and is then looked up in a table to get an `fopen` mode string; so both `out` and `out | ate` truncate the file, and combinations not in the table simply fail to open.
    - `app` returns to the end of the file before every write; `ate` positions once, at open. C++23's `noreplace` corresponds to `"x"`: opening fails if the file already exists.
    - A failed open throws no exception, only setting `failbit`; a failed close during destruction is silently ignored, so if you care about the write result, call `close()` explicitly and check.
    - Reading and writing share one file position. On an `fstream`, seek before switching from writing to reading or from reading to writing.
    - C++26's `native_handle()` returns the platform handle (a file descriptor on POSIX), so system APIs can be called directly.

```cpp title="open-modes.cpp" run ok
#include <cstdio>
#include <fstream>
#include <iostream>
#include <iterator>
#include <string>

std::string slurp(const char* f) {
  std::ifstream in(f);
  return {std::istreambuf_iterator<char>(in), {}};
}

int main() {
  using std::ios_base;
  { std::ofstream("log.txt") << "line1\n"; }
  { std::ofstream out("log.txt", ios_base::ate); out << "line2\n"; }  // out|ate → "w": truncates first
  std::cout << slurp("log.txt");                                       // line2

  { std::ofstream out("log.txt", ios_base::app); out << "line3\n"; }  // "a": append
  std::cout << slurp("log.txt");                                       // two lines, line2 and line3
  std::remove("log.txt");
}
```

Many people assume `ate` means "continue writing from the end", only to find the second open wiped out `line1`. To see why, you need to know how file streams are built on top of C file I/O.

`<fstream>` provides `basic_filebuf` and three stream classes `basic_ifstream`, `basic_ofstream` and `basic_fstream`, plus `char` aliases such as `filebuf` and `ifstream` and `w`-prefixed `wchar_t` aliases ([fstream.syn] ¶1). `basic_filebuf` is a stream buffer (see [[stream.buffers]]), and each of the three stream classes holds a `basic_filebuf` member.

The standard does not invent a new file model for file streams; it refers to C's `FILE` throughout ([[c.files]]): opening is as if by `fopen`, positioning as if by `fseek` and `fsetpos`, flushing as if by `fflush`, closing as if by `fclose`. So C's rules about text and binary mode, switching between reading and writing, and file positioning apply to file streams too.

## Basic conventions of `basic_filebuf` [filebuf.general]

¶1 `basic_filebuf` associates both the input sequence and the output sequence with the same file. ¶2 The restrictions on reading and writing it are the same as for C's `FILE`. ¶3 In particular:

- ¶3.1 if the file is not open for reading, the input sequence cannot be read;
- ¶3.2 if the file is not open for writing, the output sequence cannot be written;
- ¶3.3 a joint file position is maintained for both the input sequence and the output sequence.

The last point differs from [[string.streams]]: a `stringbuf`'s read and write positions are independent, while beneath a `filebuf` there is only one file and only one read/write position. So `seekg` and `seekp` have the same effect on a file stream.

¶4 `basic_filebuf` behaves as described in this subclause only if `traits::pos_type` is `fpos<traits::state_type>`; otherwise the behavior is undefined. This always holds with the standard `char_traits`.

¶7 To convert between bytes in the file and characters in the stream, `basic_filebuf` uses the `codecvt<charT, char, state_type>` facet of the current locale, called `a_codecvt` below. For `char` streams, the standard `codecvt<char, char, mbstate_t>` performs no conversion ([[locale.codecvt]]). The note in [fstream.syn] ¶2 also explains that `basic_filebuf` treats a file as a source or sink of bytes; a file read or written by a wide-character stream holds multibyte character sequences.

## Opening [filebuf.members] ¶2–¶7

¶3 If `open(s, mode)` finds the file already open, it returns a null pointer; a `filebuf` that is already open cannot be `open`ed again. Otherwise it opens the file named by `s` as if by calling `fopen`, with the second argument of `fopen` obtained by looking up **`mode & ~ios_base::ate`** in the table below. If `mode` is not one of the combinations in the table, the open fails.

| `in` | `out` | `trunc` | `app` | `noreplace` | `fopen` mode |
|:-:|:-:|:-:|:-:|:-:|:-:|
| | + | | | | `"w"` |
| | + | | | + | `"wx"` |
| | + | + | | | `"w"` |
| | + | + | | + | `"wx"` |
| | + | | + | | `"a"` |
| | | | + | | `"a"` |
| + | | | | | `"r"` |
| + | + | | | | `"r+"` |
| + | + | + | | | `"w+"` |
| + | + | + | | + | `"w+x"` |
| + | + | | + | | `"a+"` |
| + | | | + | | `"a+"` |

Each row may also add `binary`, which adds `b` to the mode string, e.g. `"wb"`, `"r+b"`, `"w+bx"`.

¶4 If the open succeeds and `mode` contains `ate`, it then positions to the end as if by `fseek(file, 0, SEEK_END)`. ¶5 If that positioning fails, the file is closed and a null pointer is returned. ¶6 On success, returns `this`.

Several rules can be read off this table:

1. `ate` takes no part in the lookup. `out | ate` looks up `out`, which maps to `"w"` and truncates the file. To open an existing file, start writing at the end, and still be able to `seekp` back and modify, use `in | out | ate`, which is `"r+"` followed by positioning to the end.
2. `out` alone truncates the file, the same as `out | trunc`. To keep the existing content you must add `app` or `in`.
3. `app` corresponds to C's `"a"`: it positions to the end before every write, and `seekp` cannot make a write happen in the middle. `ate` positions only once, at open.
4. `noreplace` {{c++23}} corresponds to C's `"x"`: opening fails if the file already exists. The check and the creation are one atomic operation, avoiding the race in which another process slips in between calling `exists()` and opening ([[filesystems]]).
5. Combinations not in the table fail to open, for example `in | trunc`, `out | app | trunc`, `trunc` alone, and `noreplace` combined with `app`.

```cpp title="open-modes-2.cpp" run ok
#include <cstdio>
#include <fstream>
#include <iostream>

int main() {
  using std::ios_base;
  { std::ofstream("data.txt") << "old\n"; }

  std::ifstream a("data.txt", ios_base::trunc);              // in|trunc: not in the table
  std::ofstream b("data.txt", ios_base::app | ios_base::trunc);
  std::cout << a.is_open() << b.is_open() << '\n';           // 00

  std::ofstream c("data.txt", ios_base::out | ios_base::noreplace);
  std::cout << c.is_open() << '\n';                          // 0: the file already exists

  { std::fstream f("data.txt", ios_base::in | ios_base::out | ios_base::ate);
    f << "new\n"; }                                          // "r+" then position to the end
  std::ifstream in("data.txt");
  std::cout << in.rdbuf();                                   // two lines, old and new
  std::remove("data.txt");
}
```

¶7 `open(const string&, mode)` and `open(const filesystem::path&, mode)` are equivalent to `open(s.c_str(), mode)`. For a `path`, `c_str()` returns a string in the native format with the native character type ([[fs.class.path]]), which is `const wchar_t*` on Windows. [fstream.syn] ¶3 specifies that the overloads taking `const filesystem::path::value_type*` are provided only on systems where `value_type` is not `char`; this is how files are opened with wide-character paths on Windows.

## Closing [filebuf.members] ¶8–¶10, [filebuf.cons] ¶5

¶8 `close()` returns a null pointer if the file is not open. Otherwise it does three things in order:

1. if there is a put area, calls `overflow(eof())` to write out the buffered characters;
2. if the last virtual function called (among `underflow`, `overflow`, `seekoff`, `seekpos`) was `overflow`, calls `a_codecvt.unshift` to obtain the termination sequence, writes it out, and calls `overflow(eof())` again;
3. regardless of whether earlier steps failed or threw, closes the file as if by `fclose(file)`.

The termination (unshift) sequence is for state-dependent encodings: some multibyte encodings require a sequence returning to the initial shift state to be written at the end of the file, otherwise the file content is incomplete.

If any step (including `fclose`) fails, `close()` returns a null pointer; if a step threw an exception, it is rethrown after the file is closed. ¶9–¶10 Afterwards `is_open()` is false; on success it returns `this`.

[filebuf.cons] ¶5 The destructor calls `close()`. Exceptions that occur during destruction (including in `close()`) are caught and not rethrown, and nobody checks the null pointer `close()` returns. So failures to write or close during destruction are silently ignored. If you care whether the write succeeded, call `close()` explicitly before leaving the scope, then check the stream state.

## Seek before switching between reading and writing

```cpp title="fstream-rw.cpp" run ok
#include <cstdio>
#include <fstream>
#include <iostream>
#include <string>

int main() {
  { std::ofstream("rw.txt") << "0123456789"; }
  std::fstream f("rw.txt", std::ios_base::in | std::ios_base::out);  // "r+"
  f << "AB";                     // writes positions 0 and 1
  f.seekg(0);                    // switching from writing to reading: seek first
  std::string s;
  f >> s;
  std::cout << s << '\n';        // AB23456789
  std::remove("rw.txt");
}
```

[[filebuf.general#2]] brings in C's rules. C says that for a file opened in update mode, output shall not be directly followed by input without an intervening `fflush` or positioning call, and input shall not be directly followed by output without an intervening positioning call (unless the input reached end-of-file). For an `fstream` this means: after writing, `seekg` before reading; after reading, `seekp` before writing.

## Seeking [filebuf.virtuals] ¶13–¶18

¶13 `seekoff(off, way, which)` first takes `width = a_codecvt.encoding()`, the number of bytes per character; variable-length or state-dependent encodings return 0 or −1. If the file is not open, or `off != 0 && width <= 0`, positioning fails. That is, with a variable-length encoding only positioning with offset 0 is possible.

Otherwise, if the position is to be moved and the last operation was output (¶15: the last virtual operation was `overflow`, or the put area is not empty), the output is written out first, followed by the termination sequence. Then it behaves as if calling `fseek`: the offset is `width * off` when `width > 0`, otherwise 0; `beg`, `cur` and `end` correspond to `SEEK_SET`, `SEEK_CUR` and `SEEK_END`. The parameter `which` has no effect, since there is only one file position.

¶14 On success it returns the new position; on failure, `pos_type(off_type(-1))`.

¶16 `seekpos(sp, which)` sets the file position to `sp` as if by `fsetpos`; if the open mode contains `out`, output and the termination sequence are written out first, and if it contains `in`, the input sequence is updated afterwards. ¶17 If `sp` was not obtained by a previous successful call to `seekoff` or `seekpos` on the same file, the effects are undefined. The result of `tellg()` comes from `seekoff(0, cur, in)`, so saving `tellg()` and later calling `seekg(pos)` is safe.

## Buffering and flushing [filebuf.virtuals] ¶10–¶12, ¶19

¶10 Before writing to the file, `overflow(c)` converts the characters in the put area with `a_codecvt.out`: if conversion fails, it fails; if no conversion is needed (`noconv`), the original characters are written directly; if only part was converted (`partial`), the converted part is written and the rest is repeated. After writing, C++26 specifies that it establishes an observable checkpoint ([[intro.abstract#5]]) {{c++26}}: earlier output cannot be optimized away because of later undefined behavior. ¶11 On success it returns `not_eof(c)`; it always fails if the file is not open.

¶12 If `setbuf(0, 0)` is called on a stream before any I/O has occurred on it, the stream becomes unbuffered: `pbase()` and `pptr()` always return null, and output should appear in the file as soon as possible. Otherwise the effect of `setbuf` is implementation-defined {{impl}}.

¶19 If there is a put area, `sync()` calls `overflow` to write out the characters and then behaves as if by `fflush(file)`; if there is a get area, the effect is implementation-defined. `flush()` and `std::endl` ultimately call this.

## Native handles [file.native], [filebuf.members] ¶11–¶12 {{c++26}}

[file.native] ¶2 `native_handle_type` represents a platform-specific native file handle; it is trivially copyable and models `semiregular`. The note gives examples: on POSIX systems it is `int` (a file descriptor), on Windows it is `HANDLE`.

¶11–¶12 The precondition of `native_handle()` is that the file is open; it returns the associated handle. [filebuf.general] ¶6 specifies that the handle becomes invalid after `close()` or destruction. The handle still belongs to the `filebuf`; do not call `close(2)` on it.

```cpp title="native-handle.cpp" run ok
#include <cstdio>
#include <fstream>
#include <iostream>
#include <iterator>
#include <string>
#include <sys/stat.h>      // POSIX: fstat

int main() {
  { std::ofstream("demo.txt") << "hello\nworld\n"; }
  std::ifstream in("demo.txt", std::ios_base::binary);
  struct stat st;
  if (in.is_open() && fstat(in.native_handle(), &st) == 0) {
    std::string all{std::istreambuf_iterator<char>(in), {}};
    std::cout << "size=" << st.st_size << " read=" << all.size() << '\n';  // size=12 read=12
  }
  std::remove("demo.txt");
}
```

With the handle, platform APIs such as `fstat`, `flock` and `fsync` can be used without giving up iostreams. Each of the three stream classes also has `native_handle()`, equivalent to `rdbuf()->native_handle()`.

## The three stream classes [ifstream], [ofstream], [fstream]

The three classes have the same structure: they derive from `basic_istream`, `basic_ostream` and `basic_iostream` respectively, and hold an exposition-only `basic_filebuf sb`. The mode actually passed to `sb` at construction and `open` is:

| Class | Default `mode` | Mode passed to `sb.open` |
|---|---|---|
| `basic_ifstream` | `in` | `mode \| in` |
| `basic_ofstream` | `out` | `mode \| out` |
| `basic_fstream` | `in \| out` | `mode` |

The following uses `basic_ifstream` as the example; the other two classes have the same paragraph numbers.

### Construction [ifstream.cons]

¶2 After construction, `basic_ifstream(const char* s, mode = in)` calls `rdbuf()->open(s, mode | in)`, and calls `setstate(failbit)` if that returns a null pointer. The constructor does not report a failed open with an exception; you must check `is_open()` or the stream state yourself:

```cpp title="open-failure.cpp" run ok
#include <fstream>
#include <iostream>

int main() {
  std::ifstream missing("no-such-file.txt");
  std::cout << missing.is_open() << missing.fail() << '\n';  // 01
  int x = 0;
  missing >> x;                     // the stream has failed; nothing is read
  std::cout << missing.fail() << x << '\n';                  // 10
}
```

¶3 The version taking `const string&` is equivalent to passing `s.c_str()`. ¶4–¶5 The version taking a `filesystem::path` is written as a constrained template `template<class T> explicit basic_ifstream(const T& s, mode)`, constrained by `is_same_v<T, filesystem::path>`. Template argument deduction does not consider implicit conversions, so it participates in overload resolution only when the argument's type is exactly `path`. `path` can be implicitly constructed from all sorts of string types, and writing it this way ensures that passing a string never selects it via an implicit conversion. The member `open`, by contrast, takes `const filesystem::path&` directly.

¶6 The move constructor moves the base class and `sb` first, then calls `set_rdbuf(addressof(sb))`.

### Members [ifstream.members]

- `rdbuf()` returns a `basic_filebuf*` obtained by `const_cast`; `is_open()` returns `rdbuf()->is_open()`.
- ¶4 `open(s, mode)` calls `rdbuf()->open(s, mode | in)`. On success it calls `clear()`; on failure, `setstate(failbit)`.
- ¶6 `close()` calls `rdbuf()->close()`, and calls `setstate(failbit)` if that returns a null pointer.

A successful `open` calls `clear()`. If the same stream object first opens a nonexistent file (failing, setting `failbit`) and then successfully opens another file, the state is cleared. Standards before C++11 did not clear the state, which is why old code often has `f.clear(); f.open(...)`.

The standard does not specify how the reason for a failed open is reported. `fopen` usually sets `errno`, but the standard does not guarantee it. When reliable error information is needed, check first with the `error_code` functions in [[fs.op.funcs]], or call `exceptions(failbit)` so the stream throws, and look at `ios_base::failure::code()`; per [[ios.failure#2]], implementations should give the specific reason there.

## Common misconceptions

!!! pitfall "`std::ios_base::ate` means append"
    `ate` moves the position to the end only once, at open, and `out | ate` truncates the file first. To append, use `app`; to keep the content and be able to overwrite anywhere, use `in | out` (adding `ate` if needed).

!!! pitfall "A successful `flush()` means the data is on disk"
    `sync()` only behaves as if by `fflush`, handing the data to the operating system. To make sure it reaches the disk, use `native_handle()` to call a platform API such as `fsync`.

## Questions

!!! question "Question 1"
    After `std::ofstream f("out.txt"); f << data;` the disk fills up. How can the program find out that the write failed?

<details markdown="1">
<summary>Answer</summary>

The data first goes into the `filebuf`'s buffer; the actual file write happens in `overflow`, `sync` or `close`. When the buffer is full, `overflow` fails and the inserter sets `badbit`; but the last batch of data is not written until `close()` runs during destruction, and the destructor does not report failure ([[filebuf.cons#5]]). So call `f.close()` explicitly before leaving the scope and check `f.fail()`, or `f.flush()` first and check `f.bad()`.
</details>

!!! question "Question 2"
    In a UTF-8 locale, does `seekg(10, std::ios_base::beg)` on a `std::wifstream` succeed?

<details markdown="1">
<summary>Answer</summary>

No. UTF-8 is a variable-length encoding, `a_codecvt.encoding()` returns 0, and [[filebuf.virtuals#13]] specifies that in this case any `seekoff` with a non-zero offset fails. The reliable approach is to record the position with `tellg()` and later `seekg(pos)`. In the default "C" locale, `codecvt<wchar_t, char, mbstate_t>` usually uses one byte per character (`width == 1`), in which case it can succeed, with the offset counted in bytes.
</details>

<details class="fine" markdown="1"><summary>Remaining wording</summary>

[file.native] ¶1: several classes in this subclause have a member type `native_handle_type`.

[filebuf.general] ¶5: every open file has a native handle of type `native_handle_type`, obtainable via `native_handle()`.

[filebuf.cons] ¶1–¶2: after default construction, `is_open()` is false. ¶3–¶4: after move construction, `*this` refers to the file `rhs` referred to, and `rhs` no longer refers to any file; each has its own buffer; whether the pointers keep `rhs`'s values is implementation-defined, but the offsets of the read and write positions are the same as before the move.

[filebuf.assign] ¶1: move assignment first calls `close()`, then move-assigns from `rhs`, with the result as if move-constructed from `rhs`. ¶3–¶4: `swap` exchanges the state of the two.

[filebuf.members] ¶1: `is_open()` returns true if the most recent `open` succeeded and `close` has not been called since.

[filebuf.virtuals] ¶1–¶2: `showmanyc()` behaves the same as the base class; an implementation that can determine how many more characters can be read may override it. ¶3–¶4: `underflow()` and `uflow()` behave as if reading bytes from the file first and then converting with `a_codecvt.in`; the implementation must be able to determine the file position corresponding to each converted character. ¶5–¶9: the three ways of `pbackfail` are similar to [[string.streams]], but it does not write characters back to the file directly; it always fails if the file is not open.

[filebuf.virtuals] ¶20–¶22: the precondition of `imbue(loc)` is that if the file is not at its beginning and the current encoding is state-dependent, the new locale's `codecvt` facet must be the same as the current one; afterwards, characters inserted and extracted are converted according to `loc`, which may require the implementation to reconvert characters already converted. In practice, call `imbue` before opening the file.

[ifstream.swap] and the like: the member `swap` swaps the base class and `sb`; the non-member `swap` is equivalent to `x.swap(y)`.

</details>
