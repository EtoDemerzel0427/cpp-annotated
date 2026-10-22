---
title: Input/output library
summary: "A guide to chapter 31: iostreams consist of a state layer, a formatting layer and a buffering layer; what each subclause and header covers; how they relate to <format>/<print>, <cstdio> and <filesystem>."
updated: 2026-10-19
---

!!! tldr
    - An iostream consists of three layers: `basic_streambuf` buffers and transports characters, `ios_base`/`basic_ios` hold state and formatting, and `basic_istream`/`basic_ostream` convert between values and characters.
    - Swap the stream buffer, and the same `ostream` writes to a string, a file or the terminal; the formatting state stays on the stream object.
    - The state bits record what has already happened. `eofbit` means some read ran into the end, so a read loop must use the extraction itself as its condition.
    - `std::format` and `std::print` replace the formatting layer; characters are still written through a stream buffer or a C `FILE*`.
    - `<filesystem>` is in this chapter too, but it deals with paths and directories and does not read or write file contents.

## Three layers

```cpp run ok
#include <iostream>
#include <sstream>

int main() {
  std::stringbuf sb;               // buffering layer: characters go into a string
  std::ostream out(&sb);           // formatting and state layers
  out << std::hex << 255;
  std::cout << sb.str() << '\n';   // ff

  out.rdbuf(std::cout.rdbuf());    // switch to stdout's buffer
  out << 255 << '\n';              // ff: hex is still set on out
}
```

`out` itself does not know where the characters end up. It turns 255 into the hexadecimal characters `ff` and hands them to the stream buffer it points to. Change the buffer and the destination changes, while the `hex` format flag stays on `out`.

A `cout << 42` passes through the three layers in turn:

```text
 user code:     cout << 42;          cin >> x;
                    │                    │
  ┌─────────────────┴────────────────────┴───────────────┐
  │ basic_ostream / basic_istream     [iostream.format]   │  value ↔ chars:
  │   operator<< / >>, put/write, get/read/getline        │  sentry, num_put/num_get
  ├───────────────────────────────────────────────────────┤
  │ basic_ios<charT,traits> : ios_base   [iostreams.base] │  state and format:
  │   rdstate()/exceptions()  flags()/width()/precision() │  iostate, fmtflags,
  │   fill()  tie()  getloc()  rdbuf() ─────────┐         │  locale, tie
  ├─────────────────────────────────────────────┼─────────┤
  │ basic_streambuf<charT,traits> [stream.buffers] ◀──┘   │  buffering/transport:
  │   get area, put area                                  │  underflow/overflow/sync
  │   derived: filebuf / stringbuf / spanbuf / syncbuf    │
  └───────────────────────────────────────────────────────┘
                    │
          file / FILE* / string / span / another streambuf
```

The **stream buffer** ([[g:stream-buffer]], a class derived from `basic_streambuf`) is the only layer that touches the outside: it decides where characters come from, where they go, and when they are transported. Write your own streambuf, and every existing `<<` and `>>` can write to a socket or a compressed file; see [[stream.buffers]].

`basic_ios` and its base class `ios_base` are just a bundle of state: the error state bits, the exception mask, the format flags, width, precision, fill character, `locale`, the `tie` pointer, and the pointer to the stream buffer. `basic_ios` is a virtual base class of both `basic_istream` and `basic_ostream`, so `basic_iostream`, which inherits from both, has only one copy of the state ([[iostream.objects]]). See [[iostreams.base]].

`basic_istream`/`basic_ostream` convert between values and characters. Numeric conversion is delegated to the `num_get`/`num_put` facets in the `locale`, which operate directly on the stream buffer ([[input.streams]], [[output.streams]]).

So a "stream" in the standard involves two kinds of objects, and the wording has to be read with that in mind: stream objects have state bits, stream buffers have buffer pointers. `cout.flush()` is a member of the stream object, and its effect is to call `rdbuf()->pubsync()`.

## Rules that run through the chapter

```cpp run ok
#include <iostream>
#include <sstream>

int main() {
  std::istringstream in("1 2 3\n");
  int x, n = 0;
  while (!in.eof()) {   // wrong loop condition
    in >> x;
    ++n;
  }
  std::cout << n << '\n';   // 4: the last extraction failed
}
```

After reading `3`, the stream stops in front of the newline and `eofbit` is not yet set, so the loop runs once more. That extraction skips the newline, runs into the end and fails; `x` is unchanged, but the counter is incremented anyway.

1. Once set, a state bit stays set until cleared, and it records what has already happened: `eofbit` means some input operation ran into the end of the sequence; it does not predict the next read. The correct form is `while (in >> x)`; see [[iostreams.base]].
2. Format flags also stay in effect: `std::hex`, `std::fixed` and `std::setfill` last until changed. The exception is width: most formatted output functions reset it to zero after using it ([[output.streams]]).
3. Every input and output function first constructs a **sentry** object ([[g:sentry]]). It checks the stream state, flushes the tied output stream, and for formatted input skips leading whitespace. The prompt written to `cout` before `cin >> x` is guaranteed to appear because the sentry flushes `cout`.
4. The standard stream objects are synchronized with C stdio by default, so output from `cout` and `printf` can be freely interleaved. `sync_with_stdio(false)` gives up this guarantee ([[iostream.objects]]).
5. Concurrent access to the same stream object or stream buffer from multiple threads is a data race. The exceptions are the standard stream objects while synchronized, and `osyncstream`, which is designed for this ([[iostreams.requirements]], [[syncstream]]).

## Subclauses and headers (¶1–¶2)

¶1 Chapter 31 describes the components C++ programs use for input and output. Table 135 in ¶2 lists the subclauses and the corresponding headers:

| Subclause | Contents | Header | Note on this site |
|---|---|---|---|
| [iostreams.requirements] | Restrictions on `charT` and `traits`, `streamoff`/`streamsize`, thread safety | | [[iostreams.requirements]] |
| [iostream.forward] | Forward declarations and aliases for all stream class templates | `<iosfwd>` | [[iostream.objects]] |
| [iostream.objects] | `cin`/`cout`/`cerr`/`clog` and the wide versions | `<iostream>` | [[iostream.objects]] |
| [iostreams.base] | `ios_base`, `basic_ios`, `fpos`, state bits, format flags | `<ios>` | [[iostreams.base]] |
| [stream.buffers] | `basic_streambuf` | `<streambuf>` | [[stream.buffers]] |
| [iostream.format] | Input and output streams, manipulators, `print` | `<istream>`, `<ostream>`, `<iomanip>`, `<print>` | [[iostream.format]], [[input.streams]], [[output.streams]] |
| [string.streams] | Streams backed by a `basic_string` | `<sstream>` | [[string.streams]] |
| [span.streams] | Streams backed by a `span<charT>` {{c++23}} | `<spanstream>` | [[span.streams]] |
| [file.streams] | File streams | `<fstream>` | [[file.streams]] |
| [syncstream] | Non-interleaved output across threads {{c++20}} | `<syncstream>` | [[syncstream]] |
| [filesystems] | Paths, directory iteration, file operations | `<filesystem>` | [[filesystems]] |
| [c.files] | C file functions | `<cstdio>`, `<cinttypes>` | [[c.files]] |

A few stream-related things are not in this chapter. Stream iterators such as `istream_iterator` and `istreambuf_iterator` are in [[stream.iterators]] in the iterators chapter; `std::format` and the format string syntax are in [[format]]; `locale`, `num_get`/`num_put` and `codecvt` are in the localization chapter, [[localization]].

## Relation to `<format>`/`<print>` and `<cstdio>`

C++20's `std::format` and C++23's `std::print` replace only the formatting layer of iostreams; characters still travel the old routes:

- `std::print(FILE*, ...)` ([[print.fun]]) writes directly to a C stream;
- `std::print(std::ostream&, ...)` ([[ostream.formatted.print]]) first produces a string with `vformat`, then writes it through the stream's sentry and stream buffer. The stream's `width` and `flags` do not affect the result; the stream's `locale` matters only when the format string uses the `L` option.

`<cstdio>` has the same contents as C's `<stdio.h>` ([[c.files]]). C++ adds only three things: the return from a function call that delivers data to the host environment to be written to a file is an observable checkpoint ([[intro.compliance]]); when the value read by `fscanf`'s `%p` corresponds to more than one pointer value, the result is an unspecified one of them; and calling `tmpnam` with a null pointer may cause a data race with other such calls.

## `<filesystem>`

[filesystems] has almost nothing in common with iostreams. It does not read or write file contents; it deals only with paths (operations on `path` are purely string operations) and with objects in the file system (directory iteration, status queries, copying, removal). The wording leans heavily on POSIX, every operation that can fail has two overloads, one throwing and one taking an `error_code&`, and file system races are specified to cause undefined behavior. Start reading at [[filesystems]].

## Summary

| To learn about | Read |
|---|---|
| The exact meaning of `eof`/`fail`/`bad`, the exception mask, format flags, `xalloc` | [[iostreams.base]] |
| Writing your own streambuf: the contracts of `underflow`/`overflow`/`sync` | [[stream.buffers]] |
| Step-by-step behavior of `>>`, `getline`, `read`, `ignore`, the sentry | [[input.streams]] |
| `<<`, width and fill, `endl` and flushing, `print(ostream&)` | [[output.streams]] |
| `setw`/`setprecision`/`quoted`/`put_time`, `std::print` | [[iostream.format]] |
| When `cout` is constructed, `sync_with_stdio` | [[iostream.objects]] |
| Writing to `cout` from multiple threads | [[iostreams.requirements]], [[syncstream]] |
| In-memory streams | [[string.streams]], [[span.streams]] |
| File streams, open modes, `native_handle` | [[file.streams]] |
| Paths, directory iteration, file operations | [[filesystems]] and its subpages |

<details class="fine" markdown="1"><summary>Remaining wording</summary>

The body text of ¶2 lists only up to file streams; it does not mention span streams, synchronized streams, file systems or the C library files. Table 135 is the complete list.

</details>
