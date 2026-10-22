---
title: String-based streams
summary: "How <sstream>'s basic_stringbuf uses one basic_string as both read buffer and write buffer, and the common traps in constructing istringstream, ostringstream and stringstream, extracting their content, seeking, and reusing them."
updated: 2026-10-19
---

!!! tldr
    - `basic_stringbuf` uses one `basic_string` as both read buffer and write buffer; characters written into a `stringstream` can be read back immediately.
    - An output stream constructed from an initial string overwrites from the beginning by default; to append at the end, add `ate` to the open mode.
    - `str()` makes a copy every time; since C++20, `view()` does not copy but can dangle, and `std::move(ss).str()` moves the whole buffer out.
    - `str(s)` only replaces the content and does not clear the stream's error state; to reuse a stream, also call `clear()`.
    - `pubseekoff(off, cur)` without `which` fails, because the read and write positions may differ.

```cpp run ok
#include <iostream>
#include <sstream>

int main() {
  std::stringstream ss;
  ss << "12 34";                  // write
  int a, b;
  ss >> a >> b;                   // characters just written can be read at once
  std::cout << a + b << '\n';     // 46
}
```

`<sstream>` provides four class templates ([sstream.syn] ¶1). `basic_stringbuf` is the stream buffer; `basic_istringstream`, `basic_ostringstream` and `basic_stringstream` each hold a `basic_stringbuf` member and handle reading, writing, and both, respectively. The familiar `stringstream`, `istringstream` and so on are aliases for their `char` specializations, and the `w`-prefixed ones are the `wchar_t` specializations.

The stream itself only formats; where the characters are stored is decided by the stream buffer (a class derived from `basic_streambuf`), see [[stream.buffers]]. A stream buffer manages characters with two areas and six pointers: the **get area** (read) is delimited by `eback()`, `gptr()` and `egptr()`, where `gptr()` is the next character to read; the **put area** (write) is delimited by `pbase()`, `pptr()` and `epptr()`, where `pptr()` is the next position to write. When an area is used up, the base class calls the virtual functions the derived class overrides: `underflow` (to supply more readable characters) or `overflow` (to make room for writing).

## One string, two areas [stringbuf.general]

¶1 `basic_stringbuf` associates both the input sequence and the output sequence with the same character sequence. That sequence can be initialized from a `basic_string` and retrieved as a `basic_string`.

¶2 For exposition, the standard gives it three exposition-only members; implementations need not actually be written this way:

- `mode`: the open mode. Containing `in` means readable; containing `out` means writable;
- `buf`: a `basic_string` holding the underlying character sequence;
- `init-buf-ptrs()`: after `buf` has been initialized, moved or assigned, resets the six pointers according to `mode`.

It overrides `underflow`, `pbackfail`, `overflow`, `setbuf`, `seekoff` and `seekpos`; the other virtual functions (`uflow`, `xsgetn`, `xsputn`, `sync` and so on) use the base class defaults.

### Initial pointer layout [stringbuf.members] ¶2–¶3

¶3 The state after `init-buf-ptrs()`:

- If `mode` contains `out`: `pbase()` points to the first character of `buf`, and `epptr() >= pbase() + buf.size()`. If it also contains `ate`, `pptr()` is at `buf.size()`, appending from the end; otherwise `pptr() == pbase()`, overwriting from the beginning.
- If `mode` contains `in`: the get area covers exactly the whole content of `buf`, with `gptr()` at the beginning.

```text
 std::stringstream ss("hello");          mode = in | out
 buf:      [ h  e  l  l  o  ·  ·  · ]    (· is unused capacity)
 get area:  eback=gptr            egptr
 put area:  pbase=pptr                  epptr (may exceed size)
```

### Overwriting and `ate`

The effect of `ate` is easiest to see on an output stream:

<div class="compare" markdown="1">

```cpp run ok
#include <iostream>
#include <sstream>
int main() {
  std::ostringstream a("XXXXXX");
  a << "ab";
  std::cout << a.str();  // abXXXX
}
```

```cpp run ok
#include <iostream>
#include <sstream>
int main() {
  using std::ios_base;
  std::ostringstream b("XXXXXX",
                       ios_base::ate);
  b << "ab";
  std::cout << b.str();  // XXXXXXab
}
```

</div>

The standard specifies no meaning for `app` on string streams; `init-buf-ptrs` looks only at `ate`. In our tests, libc++ treats `app` as `ate` at construction (`ostringstream("XXXX", app) << "ab"` gives `XXXXab`), but afterwards `seekp(0)` can still overwrite the beginning; it does not return to the end before every write the way a file does.

### The high mark [stringbuf.members] ¶1, ¶4

¶1 The standard uses the **high mark** for the position just past the last initialized character in the buffer. Characters become initialized in three ways: by being written to the stream, by constructing from a `basic_string`, and by calling `str(s)`. When `str(s)` is called, all earlier characters revert to uninitialized, except those overwritten by the new string.

¶4 is a note: for efficiency, `basic_stringbuf` may write directly into the space of `buf` between `size()` and `capacity()`, temporarily breaking `basic_string`'s invariants. So `buf.size()` does not necessarily reflect how far writing has gone, and the high mark is needed to record it. Every operation that retrieves the string ends at the high mark and guarantees that the returned string satisfies the invariants.

The high mark only grows. Seeking back and writing does not make the content shorter:

```cpp run ok
#include <iostream>
#include <sstream>

int main() {
  std::ostringstream os;
  os << "hello";
  os.seekp(0);
  os << "J";
  std::cout << os.str() << '\n';             // Jello: length is still 5
  os.seekp(0, std::ios_base::end);
  std::cout << os.tellp() << '\n';           // 5: end refers to the high mark
}
```

## Retrieving and replacing the content [stringbuf.members] ¶5–¶19

| Member | Effect |
|---|---|
| `str() const &` | ¶6 returns a copy of `view()` |
| `str(const SAlloc& sa) const` {{c++20}} | ¶7–¶8 same, but the copy uses allocator `sa` |
| `str() &&` {{c++20}} | ¶9–¶10 moves the underlying string out; afterwards `buf` is empty and the pointers are reset for an empty string |
| `view() const noexcept` {{c++20}} | ¶11–¶12 returns a `string_view` to the underlying characters, without copying |
| `str(s)` | ¶14–¶17 `buf = s` (or moves `s`), then calls `init-buf-ptrs()` |
| `str(const T& t)` {{c++26}} | ¶18–¶19 available when `t` converts to `basic_string_view`; assigns via the `string_view` |
| `get_allocator()` | ¶5 returns `buf`'s allocator |

¶12 The range `view()` returns depends on the mode: with `out`, it is `[pbase(), high mark)`; otherwise with `in`, it is `[eback(), egptr())`; with neither, it is empty.

¶13 is a note: using the `string_view` returned by `view()` after the underlying character sequence has been destroyed or invalidated is undefined behavior (unless the result was empty). Further writes may cause reallocation, which also counts as invalidation:

```cpp title="view-dangling.cpp" ub
#include <iostream>
#include <sstream>
#include <string>
#include <string_view>

int main() {
  std::ostringstream os;
  os << std::string(40, 'a');
  std::string_view v = os.view();
  os << std::string(1000, 'x');      // reallocates; the underlying array is freed
  std::cout << v[0] << '\n';         // UB: v points to freed memory
}
```

In our tests, ASan reports heap-use-after-free on the last line. If the initial content is short, the characters may live in the string object's internal small buffer (SSO), and ASan sees no free, but the program is UB just the same.

So each of the three ways of retrieving has its use: for a quick look use `view()`, and finish with it before the next write; to take the result away use `std::move(os).str()`, which does not copy; `str()` copies every time, and calling it repeatedly in a loop costs O(n²).

## Readable as soon as written [stringbuf.virtuals] ¶1, ¶5–¶8

¶5 When the put area is full, `sputc` calls `overflow(c)`. If a write position can be made available, `overflow` writes `c` and returns `c`; if `c` is `eof()` there is no character to write, and it returns a non-`eof()` value to indicate success. ¶6 On failure it returns `eof()`. ¶7 Each call may change the number of available write positions.

¶8 A write position can be made available only if `mode` contains `out`. This is done by reallocating (or allocating for the first time) an array that holds the current content plus at least one write position. If `mode` also contains `in`, `overflow` also advances `egptr()` past the newly written character.

¶1 `underflow()` returns `*gptr()` if a character is available to read, otherwise `eof()`. Any initialized character in the buffer counts as part of the input sequence.

Together these explain the opening example: when the `stringstream` writes, `overflow` advances `egptr()`, so the characters just written enter the get area.

## Putting characters back [stringbuf.virtuals] ¶2–¶4

`putback(c)` puts a character back in front of the current read position. If `c` is exactly the character last read, the base class just decrements `gptr()`; otherwise it calls `pbackfail(c)`.

¶2 `pbackfail(c)` can succeed in three ways:

1. `c` is not `eof()`, there is a position before, and `c` equals `gptr()[-1]`: decrement `gptr()` and return `c`;
2. `c` is not `eof()`, there is a position before, and `mode` contains `out`: store `c` at `*--gptr()` and return `c`;
3. `c` is `eof()` and there is a position before: decrement `gptr()` and return `not_eof(c)`.

¶3 If none applies, it returns `eof()` to indicate failure. ¶4 If more than one way is possible, which one is chosen is unspecified. The second way modifies the buffer, so only a writable stringbuf can put back a different character:

<div class="compare" markdown="1">

```cpp run ok
#include <iostream>
#include <sstream>
int main() {
  std::istringstream in("abc");
  in.get();
  in.putback('z');        // fails
  std::cout << in.bad();  // 1
}
```

```cpp run ok
#include <iostream>
#include <sstream>
#include <string>
int main() {
  std::stringstream s("abc");
  s.get();
  s.putback('z');         // succeeds
  std::string r;
  s >> r;
  std::cout << r;         // zbc
}
```

</div>

On the left, the `istringstream`'s mode is just `in`, so neither of the first two ways applies; `pbackfail` returns `eof()` and `putback` sets `badbit`. On the right, the `stringstream`'s mode contains `out`, and the second way writes `'z'` into the buffer.

## Seeking [stringbuf.virtuals] ¶9–¶14

`seekoff(off, way, which)` is the virtual function behind `seekg`, `seekp`, `tellg` and `tellp`. `which` says which sequence to position, and `way` is the starting point: `beg` (the beginning), `cur` (the current position) or `end` (the end).

¶9 Which sequence is positioned is decided by this table:

| Condition | Result |
|---|---|
| `which` contains only `in` | position the input sequence |
| `which` contains only `out` | position the output sequence |
| `which` contains both `in` and `out`, and `way` is `beg` or `end` | position both sequences |
| otherwise | fail |

The last row covers `which` being `in | out` with `way` being `cur`. The read and write positions may differ, so "relative to the current position" cannot be determined, and it simply fails.

¶10 For each sequence to be positioned, the starting offset `newoff` is computed first: 0 for `beg`; for `cur`, the next pointer minus the beginning pointer (`gptr() - eback()` or `pptr() - pbase()`); for `end`, the high mark minus the beginning pointer. If the next pointer is null and `newoff` is not 0, it fails.

¶11 If `newoff + off` is negative or would point to an uninitialized character, positioning fails; otherwise the next pointer is set to `newoff + off`. ¶12 On success it returns the new position, on failure `pos_type(off_type(-1))`. The wording reuses the name `newoff` here, but it actually means the offset after positioning: with libc++ in our tests, `pubseekoff(1, cur, in)` starting from offset 2 returns 3.

¶13–¶14 `seekpos(sp, which)` is equivalent to `seekoff(off_type(sp), beg, which)`.

```cpp title="stringbuf-seek.cpp" run ok
#include <iostream>
#include <sstream>

int main() {
  std::stringstream s("abc");
  auto* sb = s.rdbuf();
  std::cout << sb->pubseekoff(0, std::ios_base::cur) << '\n';  // -1: in|out with cur
  std::cout << s.tellg() << ' ' << s.tellp() << '\n';         // 0 0
}
```

`tellg()` passes `in` as `which`, and `tellp()` passes `out` ([[input.streams]], [[output.streams]]); each positions only one sequence, so both work. You run into this rule only by calling `pubseekoff` directly with the default `which`.

## Construction [stringbuf.cons]

| Constructor | Effect |
|---|---|
| `basic_stringbuf()` | delegates to `basic_stringbuf(in \| out)` |
| `explicit basic_stringbuf(which)` | ¶1–¶2 empty content; whether the six pointers are initialized to null is implementation-defined |
| `basic_stringbuf(const string& s, which = in \| out)` | ¶3 copies `s` into `buf`, then calls `init-buf-ptrs()` |
| `basic_stringbuf(string&& s, which = in \| out)` {{c++20}} | ¶6 moves `s` into `buf`, without copying |
| overloads with an allocator, or with a string of a different allocator type | ¶4–¶5, ¶7–¶9 |
| `basic_stringbuf(const T& t, which, a)` and similar {{c++26}} | ¶10–¶12 available when `t` converts to `basic_string_view`; converts to `string_view` first, then initializes `buf` |

The C++26 `string_view` overloads mean `std::istringstream in(sv);` no longer needs `std::string(sv)` first. But `buf` still copies the characters; to avoid copying, see [[span.streams]].

¶13–¶14 The move constructor moves `rhs`'s content over. Whether the pointers in the new object have `rhs`'s old values is implementation-defined, but the offsets of the read and write positions are the same as before the move, and the pointers do not share a buffer with `rhs`; `rhs` becomes empty but still usable. Move assignment ([stringbuf.assign] ¶1) has the same result as move construction.

## The three stream classes [istringstream], [ostringstream], [stringstream]

The three classes have the same structure: they derive from `basic_istream`, `basic_ostream` and `basic_iostream` respectively, hold an exposition-only member `basic_stringbuf sb`, and have constructors corresponding one-to-one to those of `basic_stringbuf`. The mode actually passed to `sb` at construction is:

| Class | Default `which` | Mode passed to `sb` |
|---|---|---|
| `basic_istringstream` | `in` | `which \| in` |
| `basic_ostringstream` | `out` | `which \| out` |
| `basic_stringstream` | `out \| in` | `which` |

So an `istringstream` can always read and an `ostringstream` can always write; the `which` passed in can only add modes, such as `ate`.

All other members forward to `sb`:

- `rdbuf()` is a `const` member function returning a `basic_stringbuf*` obtained by `const_cast` ([istringstream.members] ¶1 and so on). It hides `basic_ios::rdbuf()`, and there is no setter overload `rdbuf(sb)`, so calling `ss.rdbuf(other)` through the derived class does not compile.
- `str()`, `view()` and `str(s)` are equivalent to calling the function of the same name on `rdbuf()`.
- The move constructor moves the base class and `sb` first, then calls `set_rdbuf(addressof(sb))` so the base class points to its own `sb` ([istringstream.cons] ¶11 and so on). `swap` swaps the base class and `sb`.

## Reusing a stream

```cpp title="reuse.cpp" run ok
#include <iostream>
#include <sstream>

int main() {
  std::stringstream c;
  c << "first";
  int n;
  c >> n;                        // read fails: failbit
  c.str("");                     // only replaces the content
  c << "second";                 // the stream is still failed; nothing is written
  std::cout << '[' << c.str() << "] fail=" << c.fail() << '\n';  // [] fail=1
  c.clear();
  c << "second";
  std::cout << '[' << c.str() << "]\n";                          // [second]
}
```

`str(s)` resets only the `basic_stringbuf`'s buffer and pointers; the state bits on the stream object (`failbit`, `eofbit`) belong to `basic_ios` and are unaffected. While the state bits are non-zero, formatted input and output fail right at the start. Format flags (`hex`, `precision` and so on) are likewise retained. To reuse a stream, call `str("")` and then `clear()`, or just construct a new one.

## Common misconceptions

!!! pitfall "After `ostringstream os(\"prefix\");`, what you write is appended"
    It is not; writing overwrites from the beginning. To append, add `std::ios_base::ate` at construction.

!!! pitfall "`flush()` or `std::endl` makes a string stream do something"
    `basic_stringbuf` does not override `sync`, and the base class version does nothing. Characters are in the buffer as soon as they are written; `endl` just writes one more `'\n'`.

!!! pitfall "A string stream is the simplest choice for converting a single number"
    It is simple to write, but each time it constructs a stream and queries the locale. `std::from_chars` and `std::to_chars` ([[charconv]]) do not depend on the locale, do not allocate, and report where an error occurred; for formatted output there is `std::format` ([[format]]). The strength of string streams is reusing the `operator<<` and `operator>>` a type already has.

## Questions

!!! question "Question 1"
    What does this program output?
    ```cpp
    std::ostringstream os;
    os << "abcdef";
    os.seekp(2);
    std::cout << os.view() << ' ' << os.str().size();
    ```

<details markdown="1">
<summary>Answer</summary>

`abcdef 6`. `seekp(2)` only moves `pptr()`; the high mark is still at 6. In a mode containing `out`, `view()` returns `[pbase(), high mark)` ([[stringbuf.members#12]]), and `str()` is a copy of it. Compare [[span.streams]]: `ospanstream::span()` returns `[pbase(), pptr())`, so after the same operations the length is 2.
</details>

!!! question "Question 2"
    After `std::stringstream ss("abc"); ss.seekg(0, std::ios_base::end);`, what is `ss.tellp()`?

<details markdown="1">
<summary>Answer</summary>

0. `seekg` passes `in` as `which` and positions only the input sequence ([[stringbuf.virtuals#9]]); `pptr()` is still at the beginning. A `stringbuf`'s read and write positions are independent, unlike [[file.streams]], where the two sequences share a single file position.
</details>

<details class="fine" markdown="1"><summary>Remaining wording</summary>

[sstream.syn] declares the four class templates, their non-member `swap`, and the aliases `stringbuf`, `istringstream`, `ostringstream`, `stringstream` and the corresponding `w`-prefixed ones. ¶1 says these classes associate stream buffers with objects of `basic_string`.

[stringbuf.assign] ¶3–¶5: `swap` requires the two objects' allocators to be equal or `propagate_on_container_swap` to be true; it is `noexcept` if and only if `propagate_on_container_swap` or `is_always_equal` is true. This is the same rule as for containers ([[container.reqmts]]). ¶6 The non-member `swap` is equivalent to `x.swap(y)`.

[stringbuf.virtuals] ¶15–¶16: the effect of `setbuf(s, n)` is implementation-defined, except that `setbuf(0, 0)` has no effect; returns `this`.

[istringstream.swap], [ostringstream.swap], [stringstream.swap]: the member `swap` swaps the base class first, then `sb`; the non-member `swap` is equivalent to `x.swap(y)`.

</details>
