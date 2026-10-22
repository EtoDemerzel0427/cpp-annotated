---
title: Stream iterators
summary: "istream_iterator and ostream_iterator do formatted reads and writes through >> and <<, while istreambuf_iterator and ostreambuf_iterator read and write a stream buffer character by character; they let algorithms work directly on input and output streams."
updated: 2026-10-19
---

!!! tldr
    - `istream_iterator<T>` reads with `>>`, reads the first value as soon as it is constructed, and becomes the end-of-stream iterator after a failed read; `==` compares only the bound stream pointers.
    - `ostream_iterator<T>` writes with `<<` and writes the delimiter after every element, so there is always a trailing delimiter.
    - `istreambuf_iterator<charT>` reads characters directly from the stream buffer without skipping whitespace; `*` does not consume a character, `++` does.
    - `ostreambuf_iterator<charT>` writes character by character; after a write fails it silently discards the following characters, which you can only find out through `failed()`.
    - `std::string s(std::istreambuf_iterator<char>(in), std::istreambuf_iterator<char>());` declares a function; use braces instead.

## Four class templates [stream.iterators.general]

¶1 To let algorithm templates work directly with input and output streams, the library provides several iterator-like class templates. Example 1 reads floating-point numbers from `cin` and prints the partial sums to `cout`, one per line:

```cpp
partial_sum(istream_iterator<double, char>(cin),
            istream_iterator<double, char>(),
            ostream_iterator<double, char>(cout, "\n"));
```

The four class templates split along two dimensions:

| | Formatted: through `>>` and `<<`, on `basic_istream` and `basic_ostream` | Unformatted: character by character, on `basic_streambuf` |
|---|---|---|
| Input | `istream_iterator<T>` | `istreambuf_iterator<charT>` |
| Output | `ostream_iterator<T>` | `ostreambuf_iterator<charT>` |

Most other adaptors in this clause must also be provided by freestanding implementations; the stream iterators are not ([[iterator.synopsis]]), because they depend on iostreams.

```cpp run title="stream_iters.cpp" ok
#include <algorithm>
#include <cassert>
#include <iterator>
#include <sstream>
#include <string>
#include <vector>

int main() {
  // istreambuf_iterator: reads every character as is, whitespace included
  std::istringstream in1("a b  c\n");
  std::string s{std::istreambuf_iterator<char>(in1),
                std::istreambuf_iterator<char>()};
  assert(s == "a b  c\n");

  // istream_iterator<char>: reads through operator>>, skipping whitespace
  std::istringstream in2("a b  c\n");
  std::string t{std::istream_iterator<char>(in2),
                std::istream_iterator<char>()};
  assert(t == "abc");

  // ostream_iterator: the delimiter is written after every element
  std::ostringstream os;
  std::vector<int> v{1, 2, 3};
  std::ranges::copy(v, std::ostream_iterator<int>(os, ", "));
  assert(os.str() == "1, 2, 3, ");

  // reads on construction; can be compared with default_sentinel
  std::istringstream in3("10 20");
  std::istream_iterator<int> it(in3);
  assert(*it == 10);
  ++it;
  ++it;                        // read fails; becomes the end-of-stream iterator
  assert(it == std::default_sentinel);
  assert(it == std::istream_iterator<int>());

  // ostreambuf_iterator
  std::ostringstream os2;
  auto r = std::ranges::copy(std::string("hi"),
                             std::ostreambuf_iterator<char>(os2));
  assert(os2.str() == "hi" && !r.out.failed());
}
```

## istream_iterator [istream.iterator]

[istream.iterator.general] ¶1 `istream_iterator` is an input iterator ([[input.iterators]]) that reads successive elements from the input stream it was bound to on construction.

```cpp
template<class T, class charT = char,
         class traits = char_traits<charT>,
         class Distance = ptrdiff_t>
class istream_iterator {
public:
  using iterator_category = input_iterator_tag;
  using value_type        = T;
  using difference_type   = Distance;
  using pointer           = const T*;
  using reference         = const T&;
  // ...
private:
  basic_istream<charT, traits>* in_stream;  // exposition only
  T value;                                  // exposition only
};
```

Inside it has just two things: a pointer to the stream and the most recently read value. ¶2 requires `T` to be default constructible, copy constructible and copy assignable.

### Reading on construction [istream.iterator.cons]

¶1–¶2 The default constructor and `istream_iterator(default_sentinel_t)` construct the **end-of-stream iterator**: `in_stream` is a null pointer. ¶3 If `T()` is a constant initializer, these two constructors are constexpr, so the end-of-stream iterator can be a compile-time constant.

¶4 `istream_iterator(istream_type& s)` stores `addressof(s)`, value-initializes `value`, and then calls `operator++()`. So the first value has already been read at construction.

¶5–¶7 The copy constructor copies both members, with an exception specification equivalent to `is_nothrow_copy_constructible_v<T>`; when `T` is trivially destructible, so is the destructor.

### Operations [istream.iterator.ops]

¶1–¶4 `*it` returns `value` and `it->` returns `addressof(value)`, both with the precondition that `in_stream` is non-null. What is returned is a reference to a member inside the iterator; after the iterator is incremented or destroyed, the referent changes or the reference dangles. [[iterator.requirements.general#15]] allows iterators below forward to do this.

¶5–¶7 `++it` is equivalent to:

```cpp
if (!(*in_stream >> value)) in_stream = nullptr;
```

Any failed read, including reaching end of file and a format mismatch, turns the iterator into the end-of-stream iterator. Postfix `++` is declared `= default`, which copies, does the prefix increment, and returns the copy ([[over.inc.default]]).

¶8 `x == y` returns `x.in_stream == y.in_stream`, comparing only the stream pointers, not the values read. ¶9 `i == default_sentinel` returns `!i.in_stream`.

So two end-of-stream iterators are equal; two iterators bound to the same stream that have not reached the end are also equal, even if their `value`s differ; iterators bound to different streams are not equal. The only comparison an algorithm needs to make on stream iterators is whether the end has been reached, and these semantics suffice for that.

## ostream_iterator [ostream.iterator]

[ostream.iterator.general] ¶1 `ostream_iterator` writes successive elements with `<<` to the output stream it was bound to on construction. If a `charT*` was given on construction, that **delimiter string** is written after each `T` is written.

```cpp
template<class T, class charT = char,
         class traits = char_traits<charT>>
class ostream_iterator {
public:
  using iterator_category = output_iterator_tag;
  using value_type        = void;
  using difference_type   = ptrdiff_t;
  using pointer           = void;
  using reference         = void;
  ostream_iterator(ostream_type& s);
  ostream_iterator(ostream_type& s, const charT* delimiter);
  ostream_iterator& operator=(const T& value);
  ostream_iterator& operator*();
  ostream_iterator& operator++();
  ostream_iterator& operator++(int);
private:
  basic_ostream<charT, traits>* out_stream;  // exposition only
  const charT* delim;                        // exposition only
};
```

[ostream.iterator.cons.des] ¶1–¶2 The constructors only store the address of the stream and the pointer to the delimiter string, so the delimiter string must stay alive as long as the iterator is used.

[ostream.iterator.ops] ¶1 Assignment does the equivalent of:

```cpp
*out_stream << value;
if (delim) *out_stream << delim;
return *this;
```

¶2–¶3 `operator*` and `operator++` both return `*this`, so `*it++ = x` ends up just calling the assignment. Insert iterators are designed the same way ([[insert.iterators]]).

The assignment operator's parameter is `const T&`, so writing a `double` to an `ostream_iterator<int>` converts it to `int` first. `difference_type` is `ptrdiff_t`, so it models `output_iterator` and can be passed to `ranges::copy`.

The delimiter is written after every element, so `1, 2, 3, ` always ends with an extra delimiter. If all you want is to print a container, C++23's `std::print("{}", v)` or `views::join_with` is a better fit.

## istreambuf_iterator [istreambuf.iterator]

[istreambuf.iterator.general] ¶1 `istreambuf_iterator` reads successive characters from the stream buffer it was bound to on construction. `operator*` accesses the current character and `operator++` advances to the next one. At the end of the stream, that is, when `sgetc()` returns `traits::eof()`, the iterator becomes equal to the end-of-stream iterator. The default constructor and `istreambuf_iterator(nullptr)` both construct the end-of-stream iterator.

The end of ¶1 also requires every specialization to have a trivial copy constructor, a constexpr default constructor and a trivial destructor. It is effectively a wrapped `streambuf*` that can be copied freely, like a pointer.

```cpp
template<class charT, class traits = char_traits<charT>>
class istreambuf_iterator {
public:
  using iterator_category = input_iterator_tag;
  using value_type        = charT;
  using difference_type   = traits::off_type;
  using pointer           = unspecified;
  using reference         = charT;   // not a reference
  // ...
  charT operator*() const;
  istreambuf_iterator& operator++();
  proxy operator++(int);
  bool equal(const istreambuf_iterator& b) const;
private:
  streambuf_type* sbuf_;             // exposition only
};
```

It does no formatting: it calls the stream buffer's `sgetc()` and `sbumpc()` directly, skips no whitespace, does no locale-dependent number parsing, and does not set the stream's state bits. That is why it is much faster than `istream_iterator<char>` and keeps whitespace. `reference` is `charT` by value, so it does not meet the forward iterator requirements.

¶2 Calling `operator*` on the end-of-stream iterator is {{ub}}.

### Construction and operations

[istreambuf.iterator.cons] ¶1 `sbuf_` is a null pointer if and only if the iterator is the end-of-stream iterator. ¶2–¶5 It can be constructed from `default_sentinel_t`, `istream&` (taking `s.rdbuf()`), `streambuf*` and *`proxy`*.

[istreambuf.iterator.ops] ¶1 `*it` returns `sbuf_->sgetc()` and does not consume the character. ¶2–¶3 `++it` acts as `sbuf_->sbumpc()`; this is the step that consumes the character.

¶4 Postfix `++` returns *`proxy`*`(sbuf_->sbumpc(), sbuf_)`. [istreambuf.iterator.proxy] ¶1 *`proxy`* is an exposition-only class whose member `keep_` holds the character from before the increment, and whose `operator*` returns it, so `*it++` gets the character from before the increment. Implementations need not provide a class named `proxy`, as long as the behavior is equivalent.

¶5 `a.equal(b)` returns `true` if and only if both iterators are at end-of-stream or neither is, regardless of which stream buffer they use. ¶6 `a == b` is just `a.equal(b)`. ¶7 Comparing with `default_sentinel` is `equal` against the end-of-stream iterator.

This is coarser than `istream_iterator`'s `==`: two `istreambuf_iterator`s reading different files that have not reached their ends are also equal. Determining whether the end of the stream has been reached requires calling `sgetc()`, so the comparison itself can trigger an underlying read.

## ostreambuf_iterator [ostreambuf.iterator]

[ostreambuf.iterator.general] ¶1 `ostreambuf_iterator` writes successive characters to the output stream it was bound to on construction.

- [ostreambuf.iter.cons] ¶1–¶4 When constructed from an `ostream&`, the precondition is that `s.rdbuf()` is non-null; when constructed from a `streambuf*`, the precondition is that the pointer is non-null.
- [ostreambuf.iter.ops] ¶1–¶2 `it = c`: if `failed()` is `false`, calls `sbuf_->sputc(c)`; otherwise does nothing.
- ¶3–¶4 `operator*` and `operator++` return `*this`.
- ¶5 `failed()` is `true` if `sputc()` returned `traits::eof()` in any earlier assignment.

Once a write has failed, all subsequent characters are silently discarded. Checking `failed()` after writing is the only way to find out the write failed.

## Pitfall: declaring a function

```cpp run title="vexing.cpp"
#include <iterator>
#include <sstream>
#include <string>

int main() {
  std::istringstream in("hello");
  std::string s(std::istreambuf_iterator<char>(in),
                std::istreambuf_iterator<char>());
  (void)s;   // s is a function name; nothing is read
}
```

This code is well-formed, but `s` is not a string; it is a function declaration. The first parameter is named `in` with type `istreambuf_iterator<char>`, wrapped in an extra pair of parentheses; the second parameter is unnamed, with the type "function taking no arguments and returning `istreambuf_iterator<char>`" (adjusted to a function pointer). Clang 23 warns `parentheses were disambiguated as a function declaration [-Wvexing-parse]`.

Per [[dcl.ambig.res]], a statement that can be interpreted either as a declaration or as an expression is treated as a declaration. Any one of these fixes works:

- use braces: `std::string s{std::istreambuf_iterator<char>(in), std::istreambuf_iterator<char>()};`, as in the full example above;
- add another pair of parentheses around the first argument: `std::string s((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());`;
- name the iterators first: `std::istreambuf_iterator<char> b(in), e; std::string s(b, e);`.

## Common misconceptions

!!! pitfall "Constructing an `istream_iterator` doesn't read"
    It reads the first value on construction. Creating an `istream_iterator` without using it still consumes input, and in an interactive program it blocks waiting for input. Combined with `counted_iterator` or `views::take`, it also reads one value too many ([[iterators.counted]]).

!!! pitfall "Reading text with `istream_iterator<char>`"
    It reads through `>>`, which skips all whitespace. To read characters as they are, use `istreambuf_iterator<char>`, or set `std::noskipws` on the stream first.

## Questions

!!! question "Question 1"
    Given the input `"12 abc 34"`, what does `std::istream_iterator<int> b(in); std::vector<int> v(b, {});` produce? What state is the stream in?

<details markdown="1">
<summary>Answer</summary>

`v` is `{12}`. Reading `12` succeeds; reading `abc`, `>>` fails and sets `failbit`, the iterator becomes the end-of-stream iterator, and construction stops there. `34` is never read, and the stream is in a failed state; to keep reading you must first `clear()` it and skip the bad data. `{}` works because both constructor parameters are the same template parameter, whose type is deduced from the first argument, so `{}` value-initializes an end-of-stream iterator.
</details>

!!! question "Question 2"
    After `std::istringstream in("abc");`, given `auto a = std::istreambuf_iterator<char>(in); auto b = a; ++a;`, what is `*b`?

<details markdown="1">
<summary>Answer</summary>

`'b'`. `a` and `b` are just two copies of the same `streambuf*`; neither has its own position. `++a` makes the stream buffer consume `'a'`, after which `*b` calls `sgetc()` and sees the stream buffer's current character `'b'`. That is what single-pass input iterator means: incrementing one copy changes the others too.
</details>
