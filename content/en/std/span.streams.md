---
title: Span-based streams
summary: "C++23's <spanstream> attaches a stream to a fixed-size buffer supplied by the caller: it does not allocate, own or grow, and fails when full; it replaces the removed <strstream>."
updated: 2026-10-19
---

!!! tldr
    - `ospanstream`, `ispanstream` and `spanstream` borrow a `std::span<char>` as their buffer and never allocate memory; the caller guarantees the buffer's lifetime.
    - Once the buffer is full, insertion fails and the stream enters an error state; it does not grow. Reading to the end sets `eofbit`.
    - In output mode, `span()` returns the part written so far, `[pbase(), pptr())`.
    - An `ispanstream` can be constructed directly from a read-only range such as a `string_view`; when constructed from a string literal, the trailing `'\0'` counts too.
    - As of this writing, libc++ in our tests does not provide `<spanstream>`. The buttons on this page's examples use GCC trunk.

```cpp title="ospanstream-fixed.cpp" cc=gsnapshot run
#include <iostream>
#include <span>
#include <spanstream>
#include <string_view>

int main() {
  char buf[16];
  std::ospanstream os(buf);                 // no allocation; at most 16 characters
  os << "id=" << 42 << " ok";
  std::span<char> written = os.span();      // the part written
  std::cout << std::string_view(written.data(), written.size())
            << " good=" << bool(os) << '\n';                    // id=42 ok good=1

  os << " and some more text";              // exceeds 16 characters
  std::cout << os.span().size() << " good=" << bool(os) << '\n';  // 16 good=0
}
```

`<spanstream>` mirrors [[string.streams]], providing `basic_spanbuf` and three stream classes `basic_ispanstream`, `basic_ospanstream` and `basic_spanstream`, plus `char` aliases such as `spanbuf` and `ispanstream` and `w`-prefixed `wchar_t` aliases. The difference is the underlying storage: a string stream owns a growable `basic_string`, while a span stream only borrows a `span<charT>` ([[views.span]]) given by the caller, of fixed size.

There are two typical uses. One is formatting output into an array on the stack where memory cannot be allocated (embedded systems, real-time code, signal handlers); the other is parsing an existing piece of memory (a network packet, a memory-mapped file) as an input stream without first copying it into a `std::string`.

!!! impl "The examples on this page were not run locally"
    libc++ (Clang 23) has no `<spanstream>` header, and the definition of `__cpp_lib_spanstream` in `<version>` is commented out. libstdc++ already provides the header. The examples on this page are written to the standard and carry no verdict; the godbolt button compiles and runs them with GCC trunk.

## A borrowed buffer [span.streams.overview]

¶1 These classes associate stream buffers with a `span`. The note in ¶1 points out two responsibilities that come with borrowing:

- the character sequence the span refers to must outlive the stream's use of it, which the user must ensure;
- multiple `basic_spanbuf` objects referring to overlapping character sequences, used from different threads with at least one of them writing, is a data race.

The second differs from string streams. Each string stream has its own buffer, so different stream objects never race; span streams are distinct stream objects too, but the underlying memory may be the same.

## `basic_spanbuf` [spanbuf]

### Data members [spanbuf.general]

¶1–¶2 `basic_spanbuf` derives from `basic_streambuf` and has two exposition-only members: the open mode `mode` (containing `in` means readable, `out` means writable), and `std::span<charT> buf`, referring to the underlying character sequence. It has no allocator template parameter, because it never allocates.

### Setting the buffer [spanbuf.members] ¶2–¶3, [spanbuf.cons] ¶1

¶2 `span(s)` sets `buf` to `s`, then sets up the six pointers according to `mode` (the pointers of the get and put areas, see [[stream.buffers]]). [spanbuf.cons] ¶1 The constructor `basic_spanbuf(s, which)` likewise records `which` first and then behaves as if calling `span(s)`.

¶3 The pointer layout is the same as `basic_stringbuf`'s `init-buf-ptrs`:

- with `out`: the put area covers all of `s`. With `ate`, `pptr()` is at the end, otherwise at the beginning;
- with `in`: the get area covers all of `s`, with `gptr()` at the beginning.

### Retrieving what was written [spanbuf.members] ¶1

¶1 When `mode` contains `out`, `span()` returns `span<charT>(pbase(), pptr())`, i.e. the part written so far; otherwise it returns all of `buf`. A note says that when an owning copy is needed, convert the result to a `basic_string`.

This differs from string streams in one respect. `basic_stringbuf::view()` ends at the high mark (the farthest position ever written), while `basic_spanbuf::span()` ends at the current `pptr()`. After seeking back with `seekp`, `span()` gets shorter, while `view()` does not.

### Full and exhausted [spanbuf.virtuals] ¶1

`basic_spanbuf` overrides only `setbuf`, `seekoff` and `seekpos`. The note in ¶1 explains why: with a fixed-size buffer, `overflow`, `underflow` and `pbackfail` cannot provide useful behavior. So these three use the base class defaults, which always return `eof()`:

- When the buffer is full, `sputc` finds no write position and calls `overflow()`, gets `eof()`, and the inserter reports failure accordingly. The arithmetic inserters, `put` and `write` are specified to set `badbit` in this case ([[output.streams]]), and the string inserters also set `badbit` in the major implementations. The buffer does not grow.
- On reaching the end of the span, `underflow()` returns `eof()` and the extraction sets `eofbit`.
- When putting back a character different from the last one read, `pbackfail()` returns `eof()` and `putback` sets `badbit`.

After the buffer fills up, the characters written earlier are still in it, but the stream is in a failed state and later insertions have no effect. If you need truncation without failure, `std::format_to_n` ([[format]]) is a better fit.

### Seeking [spanbuf.virtuals] ¶2–¶8

The rules are largely the same as `seekoff` in [[string.streams]]:

¶2 If `which` contains `in`, the input sequence is positioned; if it contains `out`, the output sequence. ¶3 If `which` contains both `in` and `out` and `way` is `cur`, it fails, because the current positions of the two sequences may differ.

¶4 If the next pointer is null and the new offset is not 0, it fails. Otherwise the starting point `baseoff` is computed: 0 for `beg`; the current offset for `cur`; and for `end`, two cases:

- ¶4.3.1 `mode` contains `out` but not `in`: `pptr() - pbase()`, the end of the written content;
- ¶4.3.2 otherwise: `buf.size()`, the end of the whole span.

¶5 If `baseoff + off` overflows, is negative, or is greater than `buf.size()`, it fails; otherwise the next pointer is set to `baseoff + off`. ¶6 On failure it returns `pos_type(off_type(-1))`; on success, the new position.

¶7 `seekpos(sp, which)` is equivalent to `seekoff(off_type(sp), beg, which)`. ¶8 `setbuf(s, n)` is equivalent to `span(std::span<charT>(s, n))`, then returns `this`.

### Moving [spanbuf.cons] ¶2–¶3, [spanbuf.assign]

¶2–¶3 After move construction, the new object's six pointers have exactly the values `rhs` had. The buffer belongs to neither side, so it is correct for both objects to point to the same external memory. Whether `rhs.buf` is empty after the move is implementation-defined.

[spanbuf.assign] ¶1 Move assignment is equivalent to move-constructing a temporary from `rhs` and then `swap`ping with it. ¶2 `swap` swaps the base class, `mode` and `buf`.

## The three stream classes [ispanstream], [ospanstream], [spanstream]

| Class | Base class | Mode passed to `sb` | Return type of `span()` |
|---|---|---|---|
| `basic_ispanstream` | `basic_istream` | `which \| in` | `span<const charT>` |
| `basic_ospanstream` | `basic_ostream` | `which \| out` | `span<charT>` |
| `basic_spanstream` | `basic_iostream` | `which` (default `out \| in`) | `span<charT>` |

All three hold an exposition-only `basic_spanbuf sb`. The move constructor moves the base class and `sb` first, then calls `set_rdbuf(addressof(sb))`; `swap` swaps the base class and `sb`; `rdbuf()` is `const noexcept` and returns a `basic_spanbuf*` obtained by `const_cast`.

### Constructing an `ispanstream` from a read-only range [ispanstream.cons] ¶3–¶4

```cpp
template<class ROS> explicit basic_ispanstream(ROS&& s);
```

¶3 This constructor requires `ROS` to be a `borrowed_range` that is convertible to `span<const charT>` but not to `span<charT>`. ¶4 It first constructs a `span<const charT> sp`, then removes the `const` with `const_cast` and hands it to `basic_spanbuf`.

Removing the `const` is safe: the mode of an `ispanstream` does not contain `out`, so there is no write position, and `pbackfail` does not modify the buffer. Requiring `borrowed_range` rejects a temporary `std::string`, whose characters are destroyed once the constructor returns. The member function `span(ROS&&)` ([ispanstream.members] ¶4–¶5) has the same constraints and effect.

The note in [ispanstream.general] ¶1 warns that when constructing from a string literal, the trailing `'\0'` is also part of the underlying sequence. A literal has type `const char[N]`, and `N` includes the terminator.

```cpp title="ispanstream-literal.cpp" cc=gsnapshot run
#include <iostream>
#include <spanstream>
#include <string>
#include <string_view>

int main() {
  int x;
  std::ispanstream a("42");                  // underlying is {'4','2','\0'}
  a >> x;
  std::cout << x << " eof=" << a.eof() << '\n';   // 42 eof=0: stops before '\0'

  std::ispanstream b(std::string_view("42")); // no terminator
  b >> x;
  std::cout << x << " eof=" << b.eof() << '\n';   // 42 eof=1

  // std::ispanstream c(std::string("42"));   // error: a temporary string is not a borrowed_range
}
```

## History

!!! history "Replacing `<strstream>`"
    C++98's `<strstream>` (`istrstream`, `ostrstream`, `strstream`, `strstreambuf`) also worked on `char*` buffers, but the same class could either borrow the caller's buffer or allocate dynamically on its own. With dynamic allocation, `str()` froze the buffer, and the caller had to remember `freeze(false)` or leak memory. It was deprecated from the very first standard.

    C++23 added `<spanstream>` as the replacement, doing only the borrowing. The current draft has removed `<strstream>` ([[diff.cpp23]]) {{removed:C++26}}; implementations may continue to provide it per [[zombie.names]].

## Questions

!!! question "Question 1"
    After `char buf[64]; std::spanstream ss(buf); ss << "abc"; ss.seekp(0, std::ios_base::end);`, what is `ss.tellp()`? What about with `std::ospanstream`?

<details markdown="1">
<summary>Answer</summary>

The mode of `spanstream` is `out | in`, so by ¶4.3.2 of [[spanbuf.virtuals#4]] the starting point for `end` is `buf.size()`, and `tellp()` is 64. The mode of `ospanstream` is just `out`, so by ¶4.3.1 the starting point is `pptr() - pbase()`, and the result is 3. The former takes "the end" to be the end of the buffer, which may hold characters never written; the latter takes it to be the end of the written content.
</details>

!!! question "Question 2"
    Two threads, each with its own `ospanstream`, write the first 32 and last 32 characters of the same `char buf[64]`. Is there a data race?

<details markdown="1">
<summary>Answer</summary>

No. Data races are determined per memory location ([[intro.races]]), and the characters the two streams write do not overlap; the note in [[span.streams.overview]] is about overlapping sequences. Each stream's put area is confined to its own half at construction and stops at `epptr()` when full, so it never writes past into the other half.
</details>

<details class="fine" markdown="1"><summary>Remaining wording</summary>

[spanstream.syn] declares the four class templates (whose only template parameters are `charT` and `traits`), their non-member `swap`s, and the aliases `spanbuf`, `ispanstream`, `ospanstream`, `spanstream` and the `w`-prefixed ones.

[spanbuf.assign] ¶3 and ¶2 of each stream class's [*.swap]: the non-member `swap` is equivalent to `x.swap(y)`.

In [spanstream.cons], the default argument in the constructor declaration is written `ios_base::out | ios_bas::in`; `ios_bas` is an editorial typo, and the class synopsis's `ios_base::out | ios_base::in` is what is meant.

</details>
