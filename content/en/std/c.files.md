---
title: "C library files: <cstdio> and <cinttypes>"
summary: "<cstdio> and <cinttypes> have the same contents as the corresponding C23 headers; C++ adds only a few rules: the return from a call that writes to a file is an observable checkpoint, how fscanf's %p picks a pointer, tmpnam(nullptr) may race, and the abs/div overloads when intmax_t is an extended integer type."
updated: 2026-10-19
---

!!! tldr
    - `<cstdio>` and `<cinttypes>` have the same contents as the C standard library's `<stdio.h>` and `<inttypes.h>`; the current draft is based on C23. C++ has no `gets`.
    - Since C++26, the return from a file-writing call that delivers data to the host environment is an observable checkpoint; data still sitting in a `FILE` buffer does not count as delivered.
    - A mismatch between a `printf`-family conversion specification and the argument type is UB; `std::print` checks the format at compile time and does not have this problem.
    - The `PRI`/`SCN` macros are defined only if the corresponding fixed-width type exists, and the `SCN` macros additionally require `scanf` to have a suitable length modifier.

## `<cstdio>` [cstdio.syn]

¶1 The contents and meaning of `<cstdio>` are the same as C's `<stdio.h>`. The wording refers to section 7.23 of ISO/IEC 9899:2024 (C23), so the synopsis includes C23's new `__STDC_VERSION_STDIO_H__` and `_PRINTF_NAN_LEN_MAX`.

The functions listed in the synopsis fall into file operations (`remove`, `rename`, `tmpfile`, `tmpnam`), file access (`fopen`, `fclose`, `fflush`, `setvbuf` and so on), formatted I/O (the `printf` and `scanf` families), character I/O, direct I/O (`fread`, `fwrite`), file positioning and error handling. A few points to note:

- There is no `gets`. It cannot prevent buffer overflow; C11 removed it, and C++14 followed.
- Wide-character I/O (`fwprintf`, `fgetwc` and so on) is in `<cwchar>`.
- `stdin`, `stdout` and `stderr` are macros, not variables in `std`; you cannot write `std::stdout`.

### The return from a file-writing call is an observable checkpoint (¶2) {{c++26}}

```cpp title="checkpoint.cpp" ub
#include <cstdio>
int main(int argc, char**) {
  std::fputs("before\n", stderr);  // stderr is unbuffered
  int* p = nullptr;
  if (argc > 0) return *p;         // UB: null pointer dereference
}
```

Up to C++23, as soon as an execution contained UB, the standard placed no requirements on the entire execution, not even guaranteeing that output before the UB appears. C++26 draws a line: the implementation must produce all the observable behavior up to the last **observable checkpoint** before the UB ([[intro.abstract#5]], [[intro.abstract#6]]).

¶2 specifies that the return from each function call that delivers data to the host environment to be written to a file is an observable checkpoint. In the example above `stderr` is unbuffered, and when `fputs` returns the data has already been handed to the operating system, so "before" must appear.

The key word is "delivers". Data written into the `FILE`'s own buffer and not yet flushed has not been delivered. When `stdout` is connected to a pipe or file it is usually fully buffered, so when `printf("before\n")` returns the data may still be in process memory, and later UB can still lose it. When you need the guarantee, call `fflush` or write to `stderr`. Note 4 in [[intro.abstract#8]] also points out that not all host environments make file contents accessible before the program terminates.

### Pointers read back with `%p` (¶3)

¶3 `fscanf`'s `%p` converts text back into a pointer. The same address may correspond to several pointer values; for example, the address one past the end of an array may numerically equal the address of another object right next to it ([[basic.compound]]). In that case the pointer obtained is an unspecified one of the candidate values that would give the program defined behavior; if there is none, the behavior is undefined.

The background to this rule: in C++'s object model a pointer is not just an address; it points to (or past) a particular object. A pointer reconstructed from text has to be assigned to some object.

### The data race in `tmpnam` (¶4)

¶4 When `tmpnam` is called with a null pointer, it writes the result into an internal static buffer, so it may introduce a data race with other calls to `tmpnam` with a null pointer ([[res.on.data.races]]).

`tmpnam` has a more fundamental problem too: between generating the name and creating the file, another process may create a file with the same name first. Use `tmpfile` instead, or create the file exclusively with `fopen(name, "wx")`, as in the example below.

### The `printf` family does not check types

```cpp title="printf-mismatch.cpp" ub
#include <cstdio>
int main() {
  long long n = 1LL << 40;
  std::printf("%d\n", n);  // UB: %d expects int
}
```

The C standard says that if an argument is not of the type the conversion specification requires, the behavior is undefined. When the format string is a literal, Clang gives a `-Wformat` warning, but the standard does not require a diagnostic. In our tests it printed `0`.

`std::print("{}\n", n)` checks the format string at compile time and deduces the argument types by templates, so there is no such UB ([[format]], [[print.fun]]). If you still use `printf`, use the `<cinttypes>` macros for fixed-width integers; if you need the length of the formatted result, call `snprintf(nullptr, 0, ...)` first:

```cpp run title="cstdio-portable.cpp" ok
#include <cinttypes>
#include <cstdio>
#include <memory>

int main() {
  std::int64_t big = 1234567890123;
  std::printf("%" PRId64 " %" PRIx64 "\n", big, big);
  // 1234567890123 11f71fb04cb

  int need = std::snprintf(nullptr, 0, "%d-%s", 42, "answer");  // 9
  auto buf = std::make_unique<char[]>(need + 1);
  std::snprintf(buf.get(), need + 1, "%d-%s", 42, "answer");
  std::puts(buf.get());                                         // 42-answer

  std::FILE* f = std::fopen("cf.tmp", "wx");  // "x": fails if it already exists
  std::printf("first: %s\n", f ? "ok" : "failed");   // ok
  if (f) std::fclose(f);
  std::FILE* g = std::fopen("cf.tmp", "wx");
  std::printf("second: %s\n", g ? "ok" : "failed");  // failed
  if (g) std::fclose(g);
  std::remove("cf.tmp");
}
```

### Relation to the rest of C++

- `cin`, `cout`, `cerr` and `clog` are associated with `stdin`, `stdout` and `stderr`, are synchronized with them by default, and can be interleaved with them ([[iostream.objects]]).
- The specification of `basic_filebuf` is written entirely in terms of `fopen`, `fseek`, `fflush`, `fclose` and so on ([[file.streams]]). The mapping from `openmode` to `fopen` mode strings is Table 146 in [[filebuf.members]]; C++23's `noreplace` corresponds to `"x"`.
- Concurrent use of the standard C streams (`stdin` and so on) by multiple threads does not result in a data race, but characters may interleave ([[iostream.objects.overview#7]]).
- A `FILE`'s orientation is fixed the first time it is used by a wide-character or narrow-character function, and the consequences of then mixing in the other kind are governed by the C standard; `cout` and `wcout` both write `stdout` and are subject to the same constraint ([[iostream.objects.overview#6]]).

## `<cinttypes>` [cinttypes.syn]

```cpp
#include <cstdint>
namespace std {
  using imaxdiv_t = see below;
  constexpr intmax_t imaxabs(intmax_t j);
  constexpr imaxdiv_t imaxdiv(intmax_t numer, intmax_t denom);
  intmax_t  strtoimax(const char* nptr, char** endptr, int base);
  uintmax_t strtoumax(const char* nptr, char** endptr, int base);
  intmax_t  wcstoimax(const wchar_t* nptr, wchar_t** endptr, int base);
  uintmax_t wcstoumax(const wchar_t* nptr, wchar_t** endptr, int base);
  constexpr intmax_t abs(intmax_t);              // optional, see below
  constexpr imaxdiv_t div(intmax_t, intmax_t);   // optional, see below
}
// macros: PRI{d,i,o,u,x,X,b,B}N, SCN{d,i,o,u,x,b}N and so on,
// where N is 8, 16, 32, 64, LEAST8, FAST8, …, MAX, PTR
```

¶1 The contents and meaning are the same as C's `<inttypes.h>`, with two changes:

- ¶1.1 it includes `<cstdint>` ([[cstdint.syn]]) instead of `<stdint.h>`;
- ¶1.2 if and only if `intmax_t` is an **extended integer type** (a signed integer type provided by the implementation, other than the five standard types `signed char` through `long long`, [[basic.fundamental]]), it adds `abs(intmax_t)` and `div(intmax_t, intmax_t)`, with the same semantics as `imaxabs` and `imaxdiv`.

Why "if and only if"? If `intmax_t` is `long long`, `<cstdlib>` already has `abs(long long)` and `div(long long, long long)`, and declaring them again would duplicate them. Only when `intmax_t` is wider than every standard integer type are these two overloads needed, so that `std::abs(x)` works for any integer type.

¶2 The conditions under which the macros are defined:

- each `PRI` macro is defined if and only if the corresponding type name in [[cstdint.syn]] exists; for example, no `int24_t` means no `PRId24`;
- each `SCN` macro requires not only that the type exist, but also that `fscanf` have a length modifier suitable for the type;
- the `PRIB` macros (the uppercase form of binary output, with a `0B` prefix under the `#` flag) are defined if and only if `fprintf` supports the `B` conversion specifier.

```cpp run title="pri-macros.cpp" ok
#include <cinttypes>
#include <cstdio>

int main() {
  std::uint32_t mask = 0xF0F0;
  std::printf("%08" PRIX32 "\n", mask);  // 0000F0F0
#ifdef PRIb32
  std::printf("%" PRIb32 "\n", mask);    // C23 binary output
#endif
}
```

In our tests (macOS libc), `PRIb32` is not defined, so the second line produces no output.

`strtoimax` and `strtoumax` belong to the `strtol` family and report errors through `errno` and `endptr`. In C++ code, `std::from_chars` ([[charconv]]) is preferable: it does not depend on the locale, does not set `errno`, and reports exactly where parsing stopped.

## Questions

!!! question "Question"
    A platform's `<cinttypes>` defines `PRId64` but not `SCNd64`. Does this conform to the standard?

<details markdown="1">
<summary>Answer</summary>

Yes, provided the platform's `fscanf` has no length modifier suitable for `int64_t` ([[cinttypes.syn#2]]). The needs of the two sides are asymmetric. Take `int8_t`: as a variadic argument it is promoted to `int`, so `printf` can output it with `%d`; but `scanf` must write the result into a 1-byte object and needs an exactly matching length modifier such as `hh` (which C89 did not have yet). That is why the `SCN` macros carry an extra condition.
</details>
