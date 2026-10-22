---
title: Null-terminated sequence utilities
summary: "The functions of <cstring> are the same as C's <string.h>; C++ adds only four points: strtok and strerror may have data races, memcpy and memmove implicitly create objects, and strchr and friends have const-correct overloads."
updated: 2026-10-19
---

!!! tldr
    - The contents and meaning of `<cstring>` are the same as C23's `<string.h>`; the functions' preconditions and undefined behavior follow the C standard.
    - Overlapping source and destination in `memcpy` is undefined behavior; only `memmove` allows overlap. Pointer arguments must be valid even when the length is 0.
    - `strtok` and `strerror` are not guaranteed to be free of data races; `strtok` also modifies its input and drops empty fields.
    - Since C++20, `memcpy` and `memmove` implicitly create objects in the destination storage and return a pointer to the new object.
    - `strchr`, `strpbrk`, `strrchr`, `strstr` and `memchr` each have a pair of overloads: pass a `const char*` and you get a `const char*` back.

[c.strings] has a single subclause, [cstring.syn]: the synopsis of `<cstring>` plus four paragraphs. `<cctype>`, `<cwctype>`, `<cwchar>` and `<cuchar>` were also in this subclause in earlier standards; they have all moved to [[text.c.strings]] in Clause 28, because their behavior depends on locales and encodings.

## Same as C [cstring.syn]

```cpp run ub
#include <cstring>
#include <cstdio>

int main() {
  char buf[16] = "abcdefgh";
  std::memcpy(buf + 2, buf, 6);   // UB: source [0,6) overlaps destination [2,8); ASan reports memcpy-param-overlap
  std::puts(buf);
}
```

!!! std
    The contents and meaning of the header `<cstring>` are the same as the C standard library header `<string.h>`.

¶1 The C++ standard does not restate the specification of these functions, so each function's preconditions and undefined behavior come from the C standard. The C standard has a general rule for `<string.h>`: unless stated otherwise, pointer arguments to these functions must be valid, even when the length is 0; accessing beyond the end of an array is undefined behavior. This yields the most common kinds of {{ub}}.

**Overlap.** The C standard says the behavior is undefined when `memcpy`, `strcpy`, `strcat` or `strncpy` copies between overlapping objects; only `memmove` permits overlap. `memcpy` may move data in any order and at any width (vectorized, starting from the end), and with overlap the result depends on those details; `memmove` has to determine the direction first and costs a little more. The `copy` and `move` of `char_traits` ([[char.traits]]) keep this division.

**Null pointer with length 0.** `memcpy(nullptr, nullptr, 0)` is still {{ub}} in C23, because pointer arguments must be valid regardless of the length. Later C standard drafts relax this, but C++ currently references C23. A compiler can infer from `memcpy(p, q, n)` that `p` and `q` are non-null and delete later null checks. The `data()` of a default-constructed `std::string_view` is a null pointer ([[string.view]]), and passing it to `memcpy` together with `size()` falls right into this problem.

**No terminating null.** `strlen`, `strcpy`, `strcmp` and others require their arguments to be null-terminated byte strings ([[byte.strings]]); otherwise they read out of bounds. Two common sources are `string_view::data()` ([[string.view]]) and `strncpy`: when the source is at least `n` long, `strncpy` writes no null. It was designed for fixed-length fields, and when the source is shorter it pads the rest with nulls.

```cpp run ok
#include <cstring>
#include <cstdio>

int main() {
  char buf[4];
  std::strncpy(buf, "abcdef", sizeof buf);    // buf = {'a','b','c','d'}, no '\0'
  std::printf("%.*s\n", static_cast<int>(sizeof buf), buf);   // the length must be given explicitly
}
```

The first line of the synopsis, `#define __STDC_VERSION_STRING_H__ 202311L`, is the header version macro introduced by C23. New functions that came with C23:

- `memccpy(s1, s2, c, n)`: copies until the character `c` is met (inclusive) or `n` bytes are copied, returns the position in `s1` after `c`, or a null pointer if `c` was not found; suited to successive concatenation.
- `strdup`, `strndup`: return a copy allocated with `malloc`, to be released with `free`, not `delete[]`. They are not provided in freestanding implementations.
- `memset_explicit`: same semantics as `memset`, for clearing sensitive data; the C standard's intent is that it is not optimized away just because the written bytes are never read.

## Data races in strtok and strerror

```cpp run ok
#include <cstring>
#include <cstdio>

int main() {
  char text[] = "a,b,,c";
  for (char* tok = std::strtok(text, ","); tok; tok = std::strtok(nullptr, ","))
    std::printf("[%s]", tok);                  // [a][b][c]: the empty field disappears
  std::printf("\n%zu\n", std::strlen(text));   // 1: text has been changed to "a\0b\0,c"
}
```

!!! std
    The functions `strerror` and `strtok` are not required to avoid data races.

¶2 The general rule ([[res.on.data.races]]) requires standard library functions to access objects only through their arguments, so library calls from different threads do not interfere. These two functions are exceptions:

- `strtok` remembers where it stopped with a hidden static pointer, and later calls passing `nullptr` continue from there. Two threads, even each splitting its own string, read and write this pointer at the same time, which is a data race and so {{ub}} ([[intro.multithread]]).
- `strerror` may return a pointer to an internal static buffer whose contents the next call (in any thread) may overwrite.

`strtok` also has two problems in a single thread, both visible in the example above: it modifies its input, replacing delimiters with null characters, so it cannot be used on literals; and it treats consecutive delimiters as one, so empty fields are dropped.

Alternatives: POSIX's `strtok_r` and C11 Annex K's `strtok_s` let the caller hold the state, but neither is in the C++ standard. The more natural approach in C++ is to split in a loop with `std::string_view`'s `find` and `substr`, or to use `std::views::split`; these do not modify the input and keep empty fields. Thread-safe replacements for `strerror` are `std::error_code(e, std::generic_category()).message()` ([[syserr]]) or POSIX's `strerror_r`.

## memcpy and memmove implicitly create objects

```cpp run ok
#include <cstring>
#include <cstdlib>
#include <cstdio>

struct Point { int x, y; };

int main() {
  Point src{1, 2};
  void* raw = std::malloc(sizeof(Point));
  Point* p = static_cast<Point*>(std::memcpy(raw, &src, sizeof src));
  std::printf("%d %d\n", p->x, p->y);   // OK: the new object is accessed through the pointer memcpy returned
  std::free(raw);
}
```

!!! std
    Each of these functions implicitly creates objects in the destination region of storage immediately prior to copying the sequence of characters to the destination.

¶3 Immediately before copying the characters, `memcpy` and `memmove` **implicitly create objects** ([[g:implicitly-create-objects]], [[intro.object]]) in the destination storage, and return a pointer to a suitable created object, or the value of the first argument if there is none. This wording was added in C++20 by [[P0593R6]].

In the C++17 object model there were no objects in storage returned by `malloc`; `memcpy` only copied bytes, and `p->x` accessed an object that did not exist, which, strictly speaking, was undefined behavior. [[P0593R6]] made storage-obtaining operations such as `malloc` and `operator new`, as well as `memcpy` and `memmove`, implicitly create objects. The latter matters especially when storage is reused: `memcpy` a `Point` into a buffer that used to hold an object of another type, and a `Point`'s lifetime begins there.

Some precise points:

- Only objects of implicit-lifetime types ([[g:implicit-lifetime-type]]) are created, and only those that would give the program defined behavior. For types with virtual functions or non-trivial constructors, `memcpy` creates no object. Whether the value of an existing object can be copied with `memcpy` is determined by trivial copyability ([[basic.types.general]]).
- The return value points directly at the new object, without needing `std::launder`. The example above uses the return value.
- These two functions are signal-safe ([[support.signal]]) and can be called from signal handlers. Other functions such as `memset` and `strlen` have no such guarantee.

Before C++20, `memcpy` was also the only portable way to do type punning, for example copying the bytes of a `float` into a `uint32_t`. Now `std::bit_cast` ([[bit]]) can be used.

## Const-correct search functions

C's `char* strchr(const char* s, int c);` takes a `const char*` and returns a `char*`, which lets you write to read-only memory. C++ splits each of `strchr`, `strpbrk`, `strrchr`, `strstr` and `memchr` into a pair of overloads: a const pointer in gives a const pointer out, and a non-const pointer in gives a non-const pointer out ([[library.c]] permits this kind of signature replacement). The note in ¶4 says the signatures differ but the behavior is the same as in C.

```cpp error
#include <cstring>
const char* s = "hello";
char* p = std::strchr(s, 'l');   // error: cannot initialize a char* with a const char*
```

This line compiles in C. When code ported from C fails here, the right fix is to declare `p` as `const char*`, not to add a `const_cast`. The wide-character versions such as `wcschr` have the same overload pairs in `<cwchar>` ([[cwchar.syn#2]]).

## Multibyte conversion and mbstate_t

The conversion functions of `<cwchar>` and `<cuchar>` are not in this subclause, but they also handle null-terminated sequences and are directly related to the `state_type` of [[char.traits]], so here is a brief explanation; details are in [[text.c.strings]].

```cpp run ok
#include <cwchar>
#include <clocale>
#include <cstdio>

int main() {
  if (!std::setlocale(LC_ALL, "en_US.UTF-8")) return 1;
  const char* s = "\xE4\xB8\xAD";                      // UTF-8 encoding of U+4E2D, 3 bytes
  std::mbstate_t st{};
  wchar_t wc = 0;
  std::size_t r1 = std::mbrtowc(&wc, s, 2, &st);       // only 2 bytes given: returns (size_t)-2, meaning incomplete
  std::size_t r2 = std::mbrtowc(&wc, s + 2, 1, &st);   // the 3rd byte supplied: completes from the saved state
  std::printf("%d %zu U+%04X\n", r1 == static_cast<std::size_t>(-2), r2, static_cast<unsigned>(wc));
}
```

In our tests the output is `1 1 U+4E2D`. In a multibyte encoding like UTF-8, one character may consist of several `char`s, and a conversion function sees only one piece of input at a time, so it needs a conversion state object, `mbstate_t`, to remember how far it got into the previous character. That is `char_traits<char>::state_type`. A zero-initialized `mbstate_t` (`{}`) represents the initial state.

- The restartable versions with `r` in their names (`mbrtowc`, `mbrlen`, `wcrtomb`, `mbsrtowcs`, `wcsrtombs`, and `<cuchar>`'s `mbrtoc8`, `c8rtomb` and so on) take an `mbstate_t*` from the caller. [[c.mb.wcs#6]] says that if a null pointer is passed, the function uses an internal static state instead, and may then race with other such calls to the same function.
- `mbtowc`, `wctomb` and `mblen` always use internal state; [[c.mb.wcs#4]] says they may race with other calls to the same function, the same problem as `strtok`.
- The behavior of all these functions depends on `LC_CTYPE` of the current C locale.

## Questions

!!! question "Question 1"
    `std::memcpy(dst, sv.data(), sv.size())`, where `sv` is a default-constructed `std::string_view`. Is there undefined behavior?

<details markdown="1">
<summary>Answer</summary>

Under C23, which C++ currently references, yes. The `data()` of a default-constructed view is a null pointer ([[string.view.cons#1]]), and C's general rule for `<string.h>` requires pointer arguments to be valid even when the length is 0. ¶1 makes that rule apply directly to `std::memcpy`. The practical risk is that the compiler infers `sv.data()` is non-null and deletes later checks. The safe form is `if (!sv.empty()) std::memcpy(...)`, or use `sv.copy(dst, n)`, which does nothing for an empty view.
</details>

!!! question "Question 2"
    ¶3 says only that `memcpy` and `memmove` implicitly create objects. Is it valid to zero storage from `malloc` with `memset` and then use it as a trivial struct?

<details markdown="1">
<summary>Answer</summary>

Valid, but the object is not created by `memset`. `memset` has no implicit object creation semantics. Here the object is created by `malloc`: [[intro.object]] says operations such as `malloc`, `operator new`, and beginning the lifetime of an `unsigned char` or `std::byte` array implicitly create objects, and `memset` then merely writes bytes into that already existing trivial object.

If the storage is being reused and already holds an object of another type, `memset` does not change it into the new type. That takes placement new, `std::start_lifetime_as` ([[obj.lifetime]]), or a `memcpy` from an existing object of that type.
</details>

!!! question "Question 3"
    Two threads each call `strtok` on their own local buffers. Is there a problem?

<details markdown="1">
<summary>Answer</summary>

Yes. The state in which `strtok` records its last position is a static variable inside the function, unrelated to the arguments. Both threads read and write that same variable, which is a data race and so {{ub}}. Some C libraries keep this state in thread-local storage, which happens to make it safe, but the standard does not guarantee that (¶2).
</details>
