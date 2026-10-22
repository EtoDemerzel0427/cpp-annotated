---
title: Standard iostream objects and forward declarations
summary: "When cin, cout, cerr, clog and their wide versions are constructed, why they are never destroyed, their initial tie and unitbuf; what synchronization with stdio means and the cost of sync_with_stdio(false); the forward declarations in <iosfwd> and the inheritance of the stream classes."
updated: 2026-10-19
---

!!! tldr
    - The eight standard stream objects are constructed before `main` starts and are never destroyed, so `cout` can be used even in the destructors of static objects.
    - Including `<iostream>` behaves as if an `ios_base::Init` object were defined in that translation unit, so global objects defined after it in the same translation unit can always use `cout` during construction.
    - `cin` and `cerr` are both tied to `cout`, and `cerr` also has `unitbuf` set, so prompts and error messages appear in the right order.
    - The standard streams are synchronized with C stdio by default: they can be freely interleaved with `printf`, and concurrent use from multiple threads is not a data race. `sync_with_stdio(false)` gives up both guarantees and must be called before any input or output.
    - `<iosfwd>` contains only declarations; a header that only needs to mention `std::ostream&` can include just that.

## Can a global object's constructor use `cout`?

```cpp title="a.cpp" run ok
#include <iostream>        // as if a std::ios_base::Init object were defined here

struct Logger {
  Logger() { std::cout << "Logger ready\n"; }   // OK
} g;

int main() {}
```

`cout` is defined in some translation unit of the standard library; `g` is defined in the user's translation unit. The core language only guarantees that global variables within one translation unit are initialized in order of definition ([[basic.start.dynamic#3]]); dynamic initialization across translation units has no determined order. This is the **static initialization order fiasco** ([[g:static-initialization-order-fiasco]]). By that rule, `cout` might not exist yet when `g` is constructed.

[iostream.objects.overview] solves this with two rules.

¶3 The standard stream objects are constructed before or during the first construction of an object of type `ios_base::Init`, and in any case before the body of `main` begins execution ([[basic.start.main]]). They are not destroyed during program execution.

¶5 Including `<iostream>` in a translation unit behaves as if `<iostream>` defined an instance of `ios_base::Init` with static storage duration.

Together: `#include <iostream>` appears before the definition of `g`, so the as-if `Init` object is in the same translation unit as `g` and defined earlier, hence initialized earlier ([[basic.start.dynamic#3.1.1]]); constructing `Init` guarantees that `cout` has been constructed.

`ios_base::Init` itself is simple ([[ios.init]]): its constructor constructs the eight objects if they have not been constructed yet; its destructor, if no other `Init` object is alive, flushes `cout`, `cerr`, `clog` and the three wide versions.

### A translation unit that does not include `<iostream>`

```cpp title="logger.cpp"
#include <iostream>
void log_line(const char* s) { std::cout << s << '\n'; }
```

```cpp title="early.cpp"
void log_line(const char*);

struct Early {
  Early() { log_line("too early?"); }   // no Init object in this TU:
} early;                                // the standard does not guarantee cout is constructed yet

int main() {}
```

`early.cpp` does not include `<iostream>`, so there is no determined initialization order between its global object `early` and the `Init` object in `logger.cpp`. If `early` is initialized first, `log_line` uses a `cout` that has not been constructed, and the behavior is undefined.

There are two fixes: include `<iostream>` in `early.cpp` too, or construct a local `std::ios_base::Init` object in `log_line` first; its constructor guarantees the eight objects are ready.

!!! impl "What implementations do"
    "As if an `Init` instance were defined" specifies only the effect. In our tests, libc++'s `<iostream>` contains just eight `extern` declarations and no `Init` object at all. The eight objects are constructed by the library's own implementation file, using a compiler extension for initialization priority so that they come before the dynamic initialization of user code; this also satisfies ¶4's recommendation to initialize early. libstdc++ used to define a `static ios_base::Init` object in `<iostream>`, so every translation unit that included it did one more construction; newer versions also initialize inside the library.

    So the `early.cpp` above prints normally with Clang 23 + libc++. That is an extra guarantee given by the implementation, not by the standard.

### Modules (¶5)

¶5 also specifies that, in a hosted implementation, each standard library module ([[std.modules]], such as `import std;`) behaves as if it contained an interface unit that defines an unexported `ios_base::Init` variable with ordered initialization. Note 1 explains the consequence: the definition of this variable appears, in the sense of [[basic.start.dynamic#2]], before any declaration following the point of importation. So global objects defined after `import std;` can likewise use `cout` during construction.

### Never destroyed (¶3)

The last sentence of ¶3 guarantees that the standard stream objects are not destroyed. A footnote explains the purpose: constructors and destructors of objects with static storage duration can use them to read `stdin` and write `stdout`/`stderr`.

Implementations usually construct these objects in static storage with placement new and never call their destructors. When the program terminates normally, the destructor of the last `Init` object flushes them; static objects destroyed after that can still write to `cout`, and `exit` also flushes all open C streams ([[basic.start.term]]). While synchronized, characters written to `cout` are already in `stdout` and are not lost.

## The eight objects and their initial state [iostream.syn]

```cpp
namespace std {
  extern istream cin;    extern wistream wcin;
  extern ostream cout;   extern wostream wcout;
  extern ostream cerr;   extern wostream wcerr;
  extern ostream clog;   extern wostream wclog;
}
```

`<iostream>` also includes `<ios>`, `<streambuf>`, `<istream>` and `<ostream>`, so `std::cout << 42` is always usable after including it.

| Object | Associated C stream | Initial `tie()` | Initial `unitbuf` | Purpose |
|---|---|---|---|---|
| `cin` / `wcin` | `stdin` | `&cout` / `&wcout` | No | Standard input |
| `cout` / `wcout` | `stdout` | null | No | Standard output |
| `cerr` / `wcerr` | `stderr` | `&cout` / `&wcout` | Yes | Error output, flushed after each output |
| `clog` / `wclog` | `stderr` | null | No | Log output, buffered |

The source is ¶1–¶6 of [narrow.stream.objects] and [wide.stream.objects]. The rest of the state is as set by `basic_ios::init`: format flags `skipws | dec`, precision 6, a space as the fill character, and so on; see [[iostreams.base]].

¶2 The dynamic type of the stream buffers associated with these objects is unspecified, but they behave as if they were `basic_filebuf<char>` or `basic_filebuf<wchar_t>`.

```cpp run ok
#include <iostream>

int main() {
  std::cout << std::boolalpha
            << (std::cin.tie() == &std::cout) << ' '        // true
            << (std::cerr.tie() == &std::cout) << ' '       // true
            << (std::clog.tie() == nullptr) << ' '          // true
            << bool(std::cerr.flags() & std::ios_base::unitbuf) << ' '   // true
            << bool(std::clog.flags() & std::ios_base::unitbuf) << '\n'; // false
}
```

Each of these initial values has a purpose.

`cin` is tied to `cout`: before every read from `cin`, the input sentry first flushes `cout` ([[istream.sentry#2]]). So in `cout << "name? "; cin >> name;` the prompt is always displayed before waiting for input. This is how the library carries out [[intro.abstract#8]]'s requirement that, for interactive devices, prompts appear before waiting.

`cerr` is tied to `cout` and also has `unitbuf` set; the two solve different problems. `tie` makes `cerr` flush `cout` before each output, so normal output buffered in `cout` appears first; `unitbuf` makes `cerr` flush itself at the end of each output operation, so the error message appears immediately. Without either one, the order on the terminal may be wrong.

`clog` also writes to `stderr` but is buffered, which suits large volumes of logging.

`cin.tie(nullptr)` turns off "flush `cout` before reading `cin`"; it has nothing to do with the stdio synchronization in the next section. Turn it off in an interactive program and the prompts may not appear.

## Synchronization with stdio [ios.members.static]

`sync_with_stdio` is declared as a static member of `ios_base` ([[iostreams.base]]), but it is meaningful only for these eight objects.

```cpp
static bool sync_with_stdio(bool sync = true);
```

¶3 A standard stream object `str` is **synchronized** with a C stream `f` ([[g:synchronized-standard-stream]]) if, for any sequence of characters, each of the following pairs of operations has the same effect: `fputc(f, c)` and `str.rdbuf()->sputc(c)`; `fgetc(f)` and `str.rdbuf()->sbumpc()`; `ungetc(c, f)` and `str.rdbuf()->sputbackc(c)`. A footnote says this means operations on the two sides can be freely mixed; in practice, synchronization usually means the standard stream object and stdio share a buffer.

¶1 If any input or output operation has occurred on the standard streams before the call, the effect is implementation-defined. Otherwise, calling it with `false` lets the standard streams operate independently of the C streams.

¶2 Returns whether they were synchronized before the call. The first call returns `true`, since synchronization is the default.

```cpp run impl
#include <cstdio>
#include <iostream>

int main() {
  std::ios_base::sync_with_stdio(false);   // must come before any input or output
  std::cout << "1 cout\n";
  std::printf("2 printf\n");
  std::cout << "3 cout\n";                 // the relative order of the three lines is no longer guaranteed
}
```

To share a buffer with `printf`, a synchronized standard stream often cannot have a buffer of its own, and every character goes through the locked `FILE*` interface. With synchronization off, the implementation can give `cout` an independent buffer. This is why the common competitive-programming incantation `std::ios::sync_with_stdio(false); std::cin.tie(nullptr);` speeds things up. It costs three things:

1. The order of output from `cout` and `printf` is no longer guaranteed;
2. The concurrency guarantee of ¶7 is lost: concurrent use of `cout` from multiple threads becomes a data race;
3. It must be called before any input or output, otherwise the effect is implementation-defined.

!!! impl "`sync_with_stdio(false)` has no visible effect on libc++"
    Running the example above with Clang 23 + libc++, the order is 1, 2, 3 whether output goes to a terminal or a pipe; writing 3 million integers takes essentially the same time with or without the call. libc++'s standard streams always read and write through `FILE*`, and `sync_with_stdio` only records and returns the state. libstdc++ switches the standard streams to streambufs with independent buffers once synchronization is off, and when output goes to a pipe the three lines of the example may appear in a different order from the code. Portable code cannot rely on either behavior.

## Concurrency and mixing wide and narrow (¶6–¶7)

¶7 Concurrent calls from multiple threads to the formatted and unformatted input and output functions of a synchronized standard stream object, or concurrent use of the standard C streams, do not result in a data race ([[intro.multithread]]). Note 2 warns that such unsynchronized concurrent use may interleave characters. The general rules for thread safety are in [[iostreams.requirements]].

!!! pitfall "Not a data race does not mean not interleaved"
    `std::cout << "a" << i << '\n';` is three independent output calls, and another thread can cut in between any two of them. When a whole line must come out atomically, build it into one string first and write it once, or use `std::osyncstream(std::cout) << ...` ([[syncstream]]), or use `std::println(...)`, which writes the whole line at once while holding the C stream's lock when writing to `stdout` ([[print.fun]]).

¶6 Mixing operations on corresponding wide and narrow streams (for example alternating `cout` and `wcout`, both of which write `stdout`) follows the same semantics as mixing wide and narrow operations on the same `FILE` in C. The C rule is that a `FILE` has an orientation, determined by its first wide-character or byte operation; performing the other kind of operation on it afterwards is undefined behavior (C23 7.23.2). So alternating `cout` and `wcout` to write `stdout` in the same program is not portable.

## `<iosfwd>` and the inheritance of the stream classes [iostream.forward]

### Forward declarations [iosfwd.syn]

`<iosfwd>` declares all the stream class templates of this chapter, `istreambuf_iterator`/`ostreambuf_iterator`, `fpos`, all the `char`/`wchar_t` aliases (`ostream`, `wifstream`, `spanbuf`, `osyncstream` and so on), and `streampos`, `wstreampos`, `u8streampos`, `u16streampos`, `u32streampos`. It defines no classes and is cheap to include. When a header only needs to mention `std::ostream&`, including it instead of `<ostream>` reduces compile-time dependencies:

```cpp title="widget.h" ok
#include <iosfwd>

struct Widget { int id; };
std::ostream& operator<<(std::ostream& os, const Widget& w);   // only a declaration is needed
```

### Inheritance [iostream.forward.overview]

```text
                    ios_base
                       │
              basic_ios<charT,traits>          ← virtual base class
             ╱(virtual)            ╲(virtual)
   basic_istream                  basic_ostream
   │  ╲                          ╱    │
   │   basic_iostream ──────────      │
   │      ├ basic_stringstream        ├ basic_ostringstream
   │      ├ basic_fstream             ├ basic_ofstream
   │      └ basic_spanstream          ├ basic_ospanstream
   ├ basic_istringstream              └ basic_osyncstream
   ├ basic_ifstream
   └ basic_ispanstream

   basic_streambuf<charT,traits>
      ├ basic_stringbuf   ├ basic_filebuf   ├ basic_syncbuf   └ basic_spanbuf
```

¶1 `basic_ios` is a virtual base class of `basic_istream`, `basic_ostream` and the class templates derived from them; `basic_iostream` derives from both `basic_istream` and `basic_ostream`. Because the base is virtual, `basic_iostream` has only one set of state bits and one `rdbuf()`.

A virtual base class is initialized by the most derived class ([[class.base.init]]), yet every intermediate class wants to set it up as well. So `basic_ios` provides a protected default constructor that initializes nothing, and each stream class calls `init()` itself ([[iostreams.base]]).

¶2–¶5 list the derivations of the stream buffers and streams shown above. `basic_osyncstream` derives only from `basic_ostream`; there is no input version.

¶8 Specializations of `fpos` represent file positions: `streampos` for `char` streams and `wstreampos` for `wchar_t` streams.

## Questions

!!! question "Question 1"
    The destructor of a static object writes to `std::cout` through a function in another translation unit; its own translation unit does not include `<iostream>`. Is this safe?

<details markdown="1">
<summary>Answer</summary>

It is safe. [[iostream.objects.overview#3]] specifies that the standard stream objects are not destroyed during program execution, so `cout` cannot be destroyed before this static object. Construction timing is not a problem either: static objects are destroyed after `main` returns, and ¶3 guarantees the eight objects were constructed before `main` started.
</details>

!!! question "Question 2"
    After `import std;`, is using `std::cout` in a global object's constructor guaranteed to work?

<details markdown="1">
<summary>Answer</summary>

Yes. [[iostream.objects.overview#5]] specifies that each standard library module behaves as if it contained an interface unit defining an unexported `ios_base::Init` variable with ordered initialization. A translation unit that imports it has an interface dependency on that interface unit, so by [[basic.start.dynamic#2]] the variable's definition appears before the global object definitions following the point of importation, and is therefore initialized before them ([[basic.start.dynamic#3]]).
</details>

## Summary

- The eight standard streams are constructed before `main` and never destroyed. Including `<iostream>` or `import std;` both behave as if an `Init` object were defined, guaranteeing that global objects defined afterwards can use them.
- `cin` and `cerr` are tied to `cout`; `cerr` has `unitbuf` set; `clog` writes to `stderr` with buffering.
- Synchronized with stdio by default: freely interleavable with `printf`, and concurrent use is not a data race, but characters may interleave.
- `sync_with_stdio(false)` must be called before any input or output; it trades these two guarantees for speed.
- `<iosfwd>` declares without defining; `basic_ios` is a virtual base class, so `basic_iostream` has only one copy of the stream state.

<details class="fine" markdown="1"><summary>Remaining wording</summary>

[iostream.objects.overview] ¶1: the type name `FILE` in this chapter refers to the `FILE` declared in `<cstdio>`.

¶4 *Recommended practice*: implementations should initialize these objects earlier than required, where possible.

¶5, the second half of Note 1: if a program does not refer to any of the standard stream objects, it cannot observe whether the definition of that `Init` variable exists.

[iosfwd.syn] ¶1: default template arguments (such as `traits = char_traits<charT>`) appear both in `<iosfwd>` and in the synopses of the respective headers, and including both must be well-formed. The core language does not allow specifying a default argument twice for the same template parameter in the same scope ([[temp.param]]), so implementations must work around this restriction somehow, for example by writing the default arguments only in one internal header. Users cannot do the same: redeclaring these templates in `std` is undefined behavior ([[namespace.std]]).

[iostream.forward.overview] ¶6 Note 1: for any of the class templates above, a program is ill-formed if `traits::char_type` is not the same type as `charT` (the rule itself is in [[char.traits]]). ¶7: the other aliases denote specializations for `char` or `wchar_t`. ¶9 Note 2: the synopsis appears to have a circular dependency: `streampos` uses `char_traits<char>::state_type`, while `char_traits<char>::pos_type` is `streampos`; implementations can break the cycle by substituting equivalent types.

</details>
