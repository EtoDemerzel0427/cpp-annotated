---
title: Iostreams requirements
summary: "Assumptions shared by every stream component in chapter 31: multiple threads accessing one stream is a data race (except synchronized standard streams); calling imbue from a callback is undefined behavior; streamoff and streamsize are signed integers; charT is guaranteed only for char and wchar_t."
updated: 2026-10-19
---

!!! tldr
    - Multiple threads using the same stream object, stream buffer or `FILE*` at the same time is a data race unless otherwise specified. The standard streams such as `cout` are an exception while synchronized with stdio, but the output characters may still interleave.
    - If one thread writes a value through a stream and another thread reads that value, the write synchronizes with the read, and the earlier memory modifications are visible to the reader.
    - Library functions never change a stream's locale on their own; calling `imbue` from a callback invoked by the library or from an overridden virtual function is undefined behavior.
    - `streamoff` (a file offset) and `streamsize` (a number of characters transferred) are both signed integer types; `-1` often serves as an error value in the stream interfaces.
    - The stream templates are guaranteed to work only for `char` and `wchar_t`; `basic_ostringstream<char16_t>` is unusable on libc++.

## Thread safety [iostreams.threadsafety]

### One stream cannot be used by multiple threads at once (¶1)

```cpp run ub
#include <sstream>
#include <thread>

int main() {
  std::ostringstream log;
  std::thread t1([&] { log << "from t1\n"; });   // UB: modifies the same stringbuf concurrently with t2
  std::thread t2([&] { log << "from t2\n"; });
  t1.join();
  t2.join();
}
```

`log << "..."` looks like it just appends a few characters, but it modifies the stream buffer's put area pointers, may reallocate the internal string, and also reads and writes the stream's `width`. Two threads doing this at once is a **data race** ([[intro.races]]): two threads access the same memory location in conflicting ways with no ordering between them. A data race is undefined behavior. Run with `-fsanitize=thread` in our tests, ThreadSanitizer reported a data race.

!!! std
    Concurrent access to a stream object, stream buffer object, or C Library stream by multiple threads may result in a data race unless otherwise specified.

¶1 Concurrent access by multiple threads to the same stream object, stream buffer object or C library stream (`FILE*`) may be a data race unless otherwise specified. This follows the same idea as the rule for containers ([[res.on.data.races]]): the library guarantees that different objects can be used by different threads at the same time; for the same object, the user must lock.

Even a "read-only" `in >> x` is no exception: it moves the get area pointer and modifies the state bits and the value of `gcount()`. Two threads each holding a different `ostream` that point to the same `filebuf` is likewise a data race, because the `<<` on both sides modify that `filebuf`.

There are two "otherwise specified" exceptions:

- While the standard stream objects are synchronized with stdio (the default), concurrent calls to their formatted and unformatted input and output functions from multiple threads are not a data race ([[iostream.objects.overview#7]]). Characters may still interleave.
- `osyncstream` ([[syncstream]]): each thread uses its own `osyncstream` object, which at the end hands its whole content atomically to the shared stream buffer.

```cpp run ok
#include <iostream>
#include <thread>

int main() {
  // concurrent use of cout while synchronized is not a data race, but the lines may interleave
  std::thread t1([] { for (int i = 0; i < 3; ++i) std::cout << "aaaa" << i << '\n'; });
  std::thread t2([] { for (int i = 0; i < 3; ++i) std::cout << "bbbb" << i << '\n'; });
  t1.join();
  t2.join();
}
```

!!! impl "libc++ and ThreadSanitizer"
    Running the example above with `-fsanitize=thread` on Clang 23 + libc++, TSan reported data races inside `cout`: one where `fill()` lazily sets the fill character on its first call, and one at the `width(0)` executed after each output. According to the standard this program has no data race; the reports reflect that libc++ reads and writes these members without synchronization. Projects that run TSan in CI can lock around `cout`, switch to `osyncstream`, or add suppressions.

### Values passed through a stream establish synchronization (¶2)

¶2 If a library call in thread A writes a value to a stream, and thread B reads that value through another library call that does not cause a data race, then A's write **synchronizes with** B's read. By [[intro.races]], every memory modification A made before the write is visible to B after the read. Here the stream plays the same role as a mutex or an atomic variable.

The typical scenario is two threads communicating through a pipe or the same file, each end using its own stream object, so there is no data race. Reading the data the other side wrote means an ordering has been established between them. The synchronization guarantee that `osyncstream`'s `emit()` provides also rests on this.

## Restrictions on imbue [iostream.limits.imbue]

¶1 This paragraph makes two rules.

First, apart from `ios_base::imbue` and `basic_filebuf::pubimbue`, no function in this chapter calls `basic_ios::imbue` or `basic_streambuf::imbue`. In other words, a stream's locale changes only when the program explicitly asks for it; a `>>` or `<<` will not swap it out midway.

Second, if a user function called by a function in this chapter, or a virtual function the user overrides in a class derived from a class in this chapter, calls `imbue`, the behavior is undefined. Examples of the former are a callback registered with `register_callback` or a user facet called by `num_put`; an example of the latter is the `overflow` of a custom streambuf.

The reason is caching. [[streambuf.virt.locales#2]] allows a stream buffer to cache locale-dependent results between calls to `imbue`, and `basic_filebuf` also caches its `codecvt` facet for encoding conversion. Swapping the locale in the middle of a read or write leaves those caches inconsistent with the actual state.

`imbue` should be called before you start using the stream. This matters especially for file streams: if the file is not at its beginning and the old locale's encoding is state-dependent, `basic_filebuf::imbue` requires the old and new `codecvt` facets to be the same, otherwise a precondition is violated ([[filebuf.virtuals#20]]).

## `streamoff` and `streamsize` [stream.types]

```cpp run ok
#include <ios>
#include <type_traits>

static_assert(std::is_signed_v<std::streamoff>);
static_assert(std::is_signed_v<std::streamsize>);
static_assert(std::is_same_v<std::char_traits<char>::off_type, std::streamoff>);

int main() {}
```

¶1 `streamoff` is some signed basic integral type large enough to represent the maximum file size the operating system allows. It is the offset type of `seekoff`, and the distance type `fpos` converts to and from. A footnote says it is typically `long long`, which is what libc++ uses in our tests.

¶2 `streamsize` is also some signed basic integral type, representing the number of characters transferred in an I/O operation or the size of a buffer. `read`, `write`, `gcount()`, `width()` and `precision()` all use it. Where C uses `size_t` and POSIX uses `ssize_t`, this uses `streamsize`.

Both are signed because the stream interfaces commonly use `-1` to indicate an error: for example, `showmanyc()` returns `-1`, and `pos_type(off_type(-1))` indicates a failed positioning.

## Character types and positioning types [iostreams.limits.pos]

¶3 The template parameter `charT` in this chapter is `char`, `wchar_t`, or some other implementation-defined character container type ([[defns.character.container]]). `char8_t`, `char16_t` and `char32_t` are not guaranteed: `<iosfwd>` provides only position type aliases such as `u8streampos`, not a `u8ostream`.

With libc++ in our tests, `std::basic_ostringstream<char16_t> os;` compiles, but `os << u"abc";` does not. Inserting a string uses members such as `widen`, which depend on `ctype<char16_t>`; [[locale.categories]] does not require that specialization, and libc++ does not provide it.

¶1 Classes in this chapter parameterized on `charT` and `traits` are guaranteed to work as described only if `traits::pos_type` is `streampos` and `traits::off_type` is `streamoff`. With other types, unless otherwise stated, the behavior is implementation-defined.

¶2 This affects only those who write their own `traits`. Note 1 points out that every standard `char_traits` specialization ([[char.traits]]) has `mbstate_t` as `state_type`, `fpos<mbstate_t>` as `pos_type`, and `streamoff` as `off_type`. `basic_filebuf` is stricter: if `pos_type` is not `fpos<traits::state_type>`, the behavior is undefined ([[filebuf.general#4]]).

## Questions

!!! question "Question 1"
    What happens if a custom streambuf's `overflow` calls `this->pubimbue(loc)`? What about calling it in `main` before the stream has been used?

<details markdown="1">
<summary>Answer</summary>

`overflow` overrides a virtual function of a class in this chapter, and [[iostream.limits.imbue#1]] says calling `imbue` from such a function is undefined behavior. Calling it in `main` before using the stream is fine; that is what `pubimbue` is for.
</details>

!!! question "Question 2"
    Two threads each have a `std::ofstream` opened on the same file path, and each writes to it. Is this a data race?

<details markdown="1">
<summary>Answer</summary>

Not a data race in the sense of [[iostreams.threadsafety#1]]: the two stream objects and their respective `filebuf`s are all different objects. But the order and interleaving in which their data reaches the file is up to the operating system, and the contents may overwrite each other. That is a file-system-level issue on which the standard makes no guarantee.
</details>

## Summary

| Rule | Source | Consequence |
|---|---|---|
| Concurrent access to the same stream object, stream buffer or `FILE*` | [iostreams.threadsafety] ¶1 | Data race {{ub}}; synchronized standard streams excepted |
| Written through a stream and read by another thread | [iostreams.threadsafety] ¶2 | The write synchronizes with the read |
| Library functions do not call `imbue` on their own; `imbue` called from a callback or overridden virtual function | [iostream.limits.imbue] ¶1 | The latter is {{ub}} |
| `streamoff` and `streamsize` are signed integer types | [stream.types] | `-1` can serve as an error value |
| `pos_type`/`off_type` other than `streampos`/`streamoff` | [iostreams.limits.pos] ¶1 | {{impl}}; {{ub}} when used with `basic_filebuf` |
