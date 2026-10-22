---
title: "Stream buffers: basic_streambuf"
summary: "The layer of iostreams that actually moves characters: the input and output buffers are each described by three pointers; the public interface does only pointer arithmetic while the buffer suffices and calls virtual functions such as underflow and overflow only when it does not; and how to write a custom streambuf correctly."
updated: 2026-10-19
---

!!! tldr
    - `istream` and `ostream` only parse characters into values and format values into characters; where characters come from and go to is decided by the `basic_streambuf` they hold.
    - The input buffer (get area) and output buffer (put area) are each described by three pointers. When the buffer has data or room, reading or writing a character is just pointer arithmetic; virtual functions are called only when the buffer is exhausted.
    - A custom output streambuf overrides at least `overflow`, plus `sync` if it sets up a put area; a custom input streambuf overrides `underflow` and uses `setg` to put the data it read into the get area.
    - `underflow` returns the next character without consuming it; `overflow(c)` hands off the accumulated characters and then accepts `c`, and when `c` is `eof()` it only flushes. On success return `traits_type::not_eof(c)`.
    - The base class destructor does not flush, copying copies only pointers, and the positioning functions fail by default; derived classes must handle all of this themselves.

## A minimal streambuf

```cpp title="counting-buf.cpp" run ok
#include <iostream>
#include <streambuf>

struct counting_buf : std::streambuf {
  std::size_t count = 0, newlines = 0;
protected:
  int_type overflow(int_type c) override {
    if (!traits_type::eq_int_type(c, traits_type::eof())) {
      ++count;
      if (traits_type::to_char_type(c) == '\n') ++newlines;
    }
    return traits_type::not_eof(c);     // success: return a non-eof value
  }
};

int main() {
  counting_buf cb;
  std::ostream os(&cb);
  os << "pi = " << 3.14159 << '\n' << 42 << '\n';
  std::cout << cb.count << " chars, " << cb.newlines << " lines\n";
  // 16 chars, 2 lines
}
```

All the formatting of `os << 3.14159` (number to characters, precision, locale) happens in `ostream`, and the resulting characters are handed to `cb` one by one. `counting_buf` overrides just one virtual function, `overflow`, and gets an output target that works with every standard inserter.

This is the layering of iostreams: `basic_ostream` and `basic_istream` handle formatting, and the **stream buffer** handles where characters come from and go to. Files, strings, memory blocks and synchronized output each have a derived class: `basic_filebuf` in [[file.streams]], `basic_stringbuf` in [[string.streams]], `basic_spanbuf` in [[span.streams]], `basic_syncbuf` in [[syncstream]]. Once you understand the base class contract, the wording for these derived classes is just about how each one overrides the virtual functions.

The header `<streambuf>` declares `basic_streambuf` and the aliases `streambuf` and `wstreambuf` ([streambuf.syn]).

## Three pointers [streambuf.reqts]

¶2 Each `basic_streambuf` controls an input sequence and an output sequence. Each sequence is described by three pointers which, when non-null, all point into the same `charT` array. That array is the buffer, and at any moment it holds a segment of the external sequence:

- the **beginning pointer**: the lowest address of the array;
- the **next pointer**: the position of the next read or write;
- the **end pointer**: one past the last element of the array.

The three pointers of the input sequence are `eback()`, `gptr()` and `egptr()`, and the region they enclose is called the [[g:get-area|get area]]. The three pointers of the output sequence are `pbase()`, `pptr()` and `epptr()`, enclosing the [[g:put-area|put area]].

```text
 get area: eback()         gptr()                  egptr()
             │ read, can back up │    to be read         │
             ▼               ▼                         ▼
           [ a  b  c  d  e  f  g  h  i  j  k  l ]

 put area: pbase()           pptr()                epptr()
             │ written, not handed off │    free       │
             ▼                 ▼                       ▼
           [ H  e  l  l  o  ,  _  _  _  _  _  _  _ ]
```

¶3 Constraints that must hold at all times:

- ¶3.1 If the next pointer is non-null, the other two are also non-null and point into the same array; if the next pointer is null, all three are null.
- ¶3.2 In the output sequence, if `pptr() < epptr()`, a **write position** is available, and the next character can be stored directly at `*pptr()`.
- ¶3.3 In the input sequence, if `eback() < gptr()`, a **putback position** is available: `gptr()[-1]` has a defined value, and putting back a character means moving `gptr()` back.
- ¶3.4 In the input sequence, if `gptr() < egptr()`, a **read position** is available, and `*gptr()` is the next character to read.

¶1 lists the restrictions a stream buffer may impose: the input sequence may not be readable, the output sequence may not be writable, it may be associated with an external file, and it may restrict putback and changes of stream position. In other words, the `basic_streambuf` interface describes the upper bound of capabilities; derived classes implement only the parts they need, and the base class virtual functions return failure by default.

## The public interface: pointers first, virtual calls only when needed [streambuf.general]

`istream` and `ostream` call only the public members of `basic_streambuf`. None of these members is virtual; they first check whether a read or write position is available, operate on the pointers directly if so, and call the corresponding protected virtual function only if not.

| Public member | When the position is available | Otherwise calls |
|---|---|---|
| `sgetc()` | returns `*gptr()`, does not advance | `underflow()` |
| `sbumpc()` | returns `*gptr()`, increments `gptr()` | `uflow()` |
| `snextc()` | `sbumpc()` first, then `sgetc()` unless that was `eof()` | via the two above |
| `in_avail()` | returns `egptr() - gptr()` | `showmanyc()` |
| `sputbackc(c)` | decrements `gptr()` if `c == gptr()[-1]` | `pbackfail(c)` |
| `sungetc()` | decrements `gptr()` | `pbackfail()` |
| `sputc(c)` | stores at `*pptr()`, increments `pptr()` | `overflow(c)` |
| `sgetn(s, n)`, `sputn(s, n)` | always call `xsgetn`, `xsputn` | |
| `pubsync()`, `pubsetbuf`, `pubseekoff`, `pubseekpos`, `pubimbue` | always call `sync`, `setbuf`, `seekoff`, `seekpos`, `imbue` | |

`sgetc` peeks, `sbumpc` reads and consumes, and `snextc` skips the current character and peeks at the next ([[streambuf.pub.get]]).

Putting back the same character that was read can always be done within the buffer without a virtual call ([[streambuf.pub.pback]]). Putting back a different character is up to the derived class's `pbackfail`, which decides whether modifying the buffer is allowed; `basic_stringbuf` allows it only when opened in a writable mode.

Protected non-virtual members let derived classes manage the buffers: `eback`, `gptr`, `egptr`, `gbump` and `setg` manage the get area; `pbase`, `pptr`, `epptr`, `pbump` and `setp` manage the put area.

With this structure of public non-virtual functions calling protected virtual ones, most character reads and writes involve no virtual call, and derived classes need to step in only at buffer boundaries.

## Writing an output streambuf: `overflow` and `sync`

The `counting_buf` above sets up no put area, so `pptr()` is always null and every character goes through a virtual call to `overflow`. A real implementation should provide a buffer with `setp` so that most characters take the fast path of `sputc`. The following example converts characters to uppercase and forwards them to another streambuf:

```cpp title="upper-buf.cpp" run ok
#include <cctype>
#include <iostream>
#include <streambuf>

class upper_buf : public std::streambuf {
  std::streambuf* dest_;
  char buf_[8];

  bool drain() {                         // hand [pbase, pptr) to dest_
    for (char* p = pbase(); p != pptr(); ++p) {
      unsigned char u = static_cast<unsigned char>(*p);
      char up = static_cast<char>(std::toupper(u));
      if (dest_->sputc(up) == traits_type::eof()) return false;
    }
    setp(buf_, buf_ + sizeof buf_);      // all consumed: pptr back to pbase
    return true;
  }

protected:
  int_type overflow(int_type c) override {   // called by sputc when the put area is full
    if (!drain()) return traits_type::eof();
    if (!traits_type::eq_int_type(c, traits_type::eof())) {
      *pptr() = traits_type::to_char_type(c);
      pbump(1);
    }
    return traits_type::not_eof(c);
  }
  int sync() override {                      // flush() → pubsync() → sync()
    return drain() && dest_->pubsync() == 0 ? 0 : -1;
  }

public:
  explicit upper_buf(std::streambuf* d) : dest_(d) {
    setp(buf_, buf_ + sizeof buf_);
  }
  ~upper_buf() override { sync(); }      // the base class destructor does not flush
};

int main() {
  upper_buf ub(std::cout.rdbuf());
  std::ostream os(&ub);
  os << "hello, streambuf " << 42 << '\n';   // HELLO, STREAMBUF 42
  os.flush();
}
```

### The contract of `overflow` [streambuf.virt.put]

¶3 The **pending sequence** that `overflow(c)` deals with is the characters already written in the put area, `[pbase(), pptr())`, followed by `c` (not appended when `c` is `eof()`). Its job is to hand some initial portion of this sequence to the external sequence; this is called **consuming** it.

¶4 Every overriding version must obey:

- ¶4.2 Let `r` be the number of characters not consumed. If `r` is non-zero, `pptr() - pbase() == r` must hold, and the `r` characters starting at `pbase()` must be those remaining characters. If `r` is zero, either `pbase()` is set to null, or `pbase()` and `pptr()` are set equal. `upper_buf` uses `setp` to put `pptr()` back at the start, which is the latter case.
- ¶4.3 The function may fail if appending characters to the external sequence fails, or if it cannot establish the pointers according to the rules above.
- ¶4.1 What consuming a character does to the external sequence is specified by the standard for each of its own derived classes; for program-defined classes there is no requirement.

¶5 On failure, returns `eof()` or throws an exception; on success, returns any value other than `eof()`. A footnote suggests returning `c`, but `traits::not_eof(c)` when `c` is itself `eof()`; `traits_type::not_eof(c)` covers both cases at once. ¶6 The base class version just returns `eof()`. ¶7 `sputc` and `sputn` call it when the put area has no room.

A call with `c == eof()` means flush only, with no new character. `basic_filebuf::close()` uses `overflow(eof())` to write out the buffer.

### `sync` and `xsputn` [streambuf.virt.buffer]

¶7 `sync()` synchronizes the buffer with the external sequence: if `pbase()` is non-null, writes `[pbase(), pptr())` to the external sequence and may then reset the pointers. ¶8 Returns −1 on failure, where what counts as failure is up to the derived class; ¶9 the base class version returns 0. `ostream::flush()` calls it via `pubsync()` and sets `badbit` on the stream when it returns −1 ([[ostream.unformatted]]).

The effect of `xsputn(s, n)` ([[streambuf.virt.put#1]]) is as if by repeated calls to `sputc`, stopping when `n` characters have been written or a call to `sputc` would return `eof()`; it returns the number written. Whether it calls `overflow()` when the put area is full, or achieves the same effect some other way, is unspecified. In our tests, the libc++ base class version copies in bulk while the put area has room and calls `overflow(c)` for the next character once it is full.

`upper_buf` shows three key points:

1. After consuming all characters, `overflow` uses `setp` to put `pptr()` back at `pbase()`, satisfying item 4.2.
2. `sync` hands off the buffered content first, then flushes downstream; if either step fails it returns −1.
3. The destructor calls `sync()` itself, because `~basic_streambuf` does nothing. This must be in the derived class's destructor, while the derived part is still alive; leaving it to a base class further up is too late.

!!! lawyer "Formatted output uses only three virtual functions"
    [[ostream.general#3]] specifies that the output functions of `basic_ostream` shall not call any virtual member of `rdbuf()` other than `overflow()`, `xsputn()` and `sync()`. So a custom output streambuf works with every standard inserter as long as these three behave correctly (`xsputn` can be the base class version); `seekoff` is used only when the user calls `seekp` or `tellp`.

## Writing an input streambuf: `underflow`

```cpp title="gen-buf.cpp" run ok
#include <iostream>
#include <streambuf>
#include <string>

// each underflow generates one line "line N\n", 3 lines in total
class gen_buf : public std::streambuf {
  std::string cur_;
  int n_ = 0;
protected:
  int_type underflow() override {
    if (gptr() < egptr())                    // the get area still has characters
      return traits_type::to_int_type(*gptr());
    if (n_ == 3) return traits_type::eof();
    cur_ = "line " + std::to_string(++n_) + "\n";
    setg(cur_.data(), cur_.data(), cur_.data() + cur_.size());
    return traits_type::to_int_type(*gptr());  // return without consuming
  }
};

int main() {
  gen_buf gb;
  std::istream in(&gb);
  for (std::string s; std::getline(in, s); )
    std::cout << '[' << s << "]\n";
  std::cout << "eof=" << in.eof() << " fail=" << in.fail() << '\n';
  // [line 1] [line 2] [line 3] (one per line), then eof=1 fail=1
}
```

### The contract of `underflow` [streambuf.virt.get]

The wording first defines three sequences:

- ¶7 The [[g:pending-sequence|pending sequence]]: the characters in the get area not yet read, `[gptr(), egptr())`, followed by some (possibly empty) segment of characters read from the external sequence.
- ¶8 The **result character**: the first character of the pending sequence if it is non-empty, otherwise the next character that would be read from the external sequence.
- ¶9 The **backup sequence**: the characters already read, `[eback(), gptr())`.

¶10 `underflow` must set `gptr()` and `egptr()` so that, if the pending sequence is non-empty, `[gptr(), egptr())` is exactly the pending sequence; if it is empty, `gptr()` is null or equal to `egptr()`. ¶12 It returns the result character without advancing the read position past it; if the pending sequence is empty, it returns `eof()` to indicate failure. ¶13 The base class version returns `eof()`.

In other words, `underflow`'s job is to refill the get area and return the next character without consuming it. Paragraph 14 says the public members call it only when `gptr()` is null or `gptr() >= egptr()`.

¶11 places no constraints on the contents of `[eback(), gptr())`, but describes the usual backup condition: that range should match the end of the backup sequence. That is, when refilling it is best to keep the last few characters read, so that putback can happen within the buffer. `gen_buf` replaces the get area with a new line each time and does not meet this condition; the consequence shows up in the putback section below.

### `uflow`: usually no need to override

¶15 `uflow` has the same constraints as `underflow`, except that the result character must be moved from the pending sequence to the backup sequence, i.e. consumed. ¶16 The base class version calls `underflow()`; if that fails it returns `eof()`, otherwise it returns `*gptr()` and increments `gptr()`.

So as long as `underflow` sets up the get area correctly, there is no need to override `uflow`. Only an implementation that uses no get area and reads one character straight from the device each time must override it, because the base class version reads `*gptr()` after `underflow` returns.

### `showmanyc` and `xsgetn`

¶1 `showmanyc()` returns an estimate of the number of characters available, or −1. If it returns a positive value, `underflow()` will not return `eof()` until at least that many characters have been extracted; if it returns −1, calls to `underflow()` and `uflow()` will fail, and a footnote says the intent is that they fail immediately. ¶2 The base class version returns 0, meaning "don't know". A footnote specifically notes that the name is pronounced "es-how-many-see", not "show-manic". `in_avail()` and `istream::readsome` depend on it ([[input.streams]]).

¶4–¶5 `xsgetn(s, n)` behaves as if by repeated calls to `sbumpc()`, storing at most `n` characters into `s`, and returns the number actually stored. A footnote says derived classes can override it and `xsputn` to provide more efficient implementations, for example a file stream reading and writing directly, bypassing the get area, when the user's buffer is large enough.

## Putback: `pbackfail` [streambuf.virt.pback]

¶1 The pending sequence of `pbackfail(c)` is the same as for `underflow`, after an adjustment: if `c` is `eof()`, the input sequence is first backed up by one character; if `c` is not `eof()`, `c` is prepended. Whether the external sequence is actually backed up or modified is unspecified.

¶3–¶4 Returning `eof()` indicates failure; any other value indicates success. ¶5 The base class version returns `eof()`. ¶6 The public functions call it only when putback within the buffer is impossible: `gptr()` is null, `gptr() == eback()`, or `c` differs from `gptr()[-1]`.

The `gen_buf` from above shows where putback ends:

```cpp title="putback-boundary.cpp" run ok
#include <iostream>
#include <streambuf>
#include <string>

class gen_buf : public std::streambuf {        // same as the previous example
  std::string cur_;
  int n_ = 0;
protected:
  int_type underflow() override {
    if (gptr() < egptr())
      return traits_type::to_int_type(*gptr());
    if (n_ == 3) return traits_type::eof();
    cur_ = "line " + std::to_string(++n_) + "\n";
    setg(cur_.data(), cur_.data(), cur_.data() + cur_.size());
    return traits_type::to_int_type(*gptr());
  }
};

int main() {
  gen_buf gb;
  std::istream in(&gb);
  std::string s;
  std::getline(in, s);  // consumes "line 1\n", the get area is used up
  in.get();             // underflow loads "line 2\n", reads 'l'
  in.unget();           // gptr() > eback(): putback within the buffer
  std::cout << in.bad() << ' ';   // 0
  in.unget();           // gptr() == eback() → pbackfail() → eof
  std::cout << in.bad() << '\n';  // 1: istream::unget sets badbit
}
```

C's `ungetc` guarantees that at least one character can be pushed back; `basic_streambuf` makes no such guarantee. How much can be put back depends on how much of the backup sequence the derived class keeps in `underflow`.

## Other virtual functions

### `imbue` and `setbuf` [streambuf.virt.locales] [streambuf.virt.buffer]

`imbue(loc)` notifies the derived class when the locale changes; the base class version does nothing. Between calls, the derived class may cache results obtained from the locale and its facets. `basic_filebuf` overrides it to switch the `codecvt` used for character encoding conversion.

`setbuf(s, n)` influences buffering in a way defined separately by each derived class; the base class version does nothing and returns `this`. For example, calling `setbuf(0, 0)` on a `basic_filebuf` before any I/O makes the stream unbuffered, and `basic_spanbuf`'s `setbuf` replaces the underlying memory block.

### Positioning: fails by default

`seekoff` and `seekpos` in [streambuf.virt.buffer] change the stream position; the base class versions return `pos_type(off_type(-1))`, i.e. failure. So on a streambuf that overrides only `overflow`, `tellp()` always returns −1.

## Construction, copying and pointer operations

### Construction and destruction [streambuf.cons]

¶1 The default constructor sets all pointers to null and initializes `getloc()` to a copy of the global locale at the time of construction. The default constructor is protected; a footnote says the purpose is to ensure that only objects of derived classes can be constructed.

¶2 Once `getloc()` is initialized, results obtained from it can be cached until the next `imbue`.

¶3 The copy constructor and copy assignment ([[streambuf.assign]]) are both protected, and their postconditions are that the six pointers and `getloc()` equal those of `rhs`. This is a shallow copy: the new object's pointers point into `rhs`'s buffer. A derived class with its own buffer must call `setg` and `setp` again in its own copy or move operations, otherwise the two objects share the same memory. `swap` swaps all the data members.

¶4 The destructor has no effects and does not flush the buffer. Flushing is the derived class destructor's job; for example, `~basic_filebuf` calls `close()`.

### locale and pointer operations [streambuf.locales] [streambuf.get.area] [streambuf.put.area]

`pubimbue(loc)` calls `imbue(loc)` and returns the old locale. Calling `getloc()` inside `imbue` still gives the old value, so a derived class can compare the old and new locales in `imbue`.

`setg(gbeg, gnext, gend)` requires all three ranges to be valid, after which the three pointers equal the arguments. `setp(pbeg, pend)` has only two parameters, after which both `pbase()` and `pptr()` equal `pbeg`. That is, `setp` always puts the write position back at the start; to keep already-written content after resetting, call `pbump(n)` afterwards.

!!! pitfall "The parameter of `gbump` and `pbump` is `int`"
    When a buffer has more than `INT_MAX` characters, a single `pbump(n)` cannot advance to the end: converting `streamsize` to `int` truncates it. Derived classes handling very large buffers must call it in several steps. In our tests, libc++'s `xsgetn` implementation does exactly this, calling `gbump` in chunks capped at `INT_MAX`.

## Questions

!!! question "Question 1"
    A streambuf overrides only `underflow`, never calls `setg`, and each time reads one character straight from the device and returns it. What is wrong with this implementation?

<details markdown="1">
<summary>Answer</summary>

`underflow` must return the result character without consuming it, and make `[gptr(), egptr())` equal the pending sequence ([[streambuf.virt.get#10]]). Without a get area it cannot avoid consuming: the next `sgetc()` calls `underflow()` again and reads the next character from the device, so two consecutive `peek()` calls return different values.

Worse, the base class `uflow()` reads `*gptr()` and increments it after `underflow()` succeeds (paragraph 16), and at that point `gptr()` is a null pointer, which is {{ub}}. Such unbuffered implementations must also override `uflow`, and keep the read-but-not-consumed character in a one-character buffer in `underflow`.
</details>

!!! question "Question 2"
    What must `overflow(eof())` return to indicate success? What is wrong with a plain `return c;`?

<details markdown="1">
<summary>Answer</summary>

Any value other than `eof()` indicates success ([[streambuf.virt.put#5]]). When `c` is `eof()`, a plain `return c;` is taken by the caller as failure. The idiomatic `return traits_type::not_eof(c);` returns `c` unchanged when it is an ordinary character and some non-`eof` value when `c` is `eof()`.
</details>

!!! question "Question 3"
    Does `in_avail()` returning 0 mean the end of the stream has been reached?

<details markdown="1">
<summary>Answer</summary>

No. When no read position is available, `in_avail()` returns `showmanyc()`, and the base class `showmanyc()` returns 0, meaning "don't know" ([[streambuf.virt.get#2]]). Only −1 means subsequent reads will fail. So `readsome` reading 0 characters may just mean the buffer is momentarily empty.
</details>

## Summary

| Direction | Fast path (non-virtual) | Slow path (virtual) | Minimum a derived class overrides |
|---|---|---|---|
| Read | `sgetc`, `sbumpc` read `*gptr()` | `underflow` (peek), `uflow` (consume) | `underflow` with `setg`; add `uflow` if unbuffered |
| Putback | `sputbackc`, `sungetc` decrement `gptr()` | `pbackfail` | optional |
| Write | `sputc` writes `*pptr()` | `overflow` | `overflow`; also `sync` if `setp` is used |
| Bulk | | `xsgetn`, `xsputn` | optional, for performance |
| Positioning | | `seekoff`, `seekpos` (fail by default) | when `seekg` or `tellp` are needed |
