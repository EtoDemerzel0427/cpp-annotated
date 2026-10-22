---
title: Build speed
summary: "How to measure and shorten C++ build times: -ftime-trace to see where the time goes, the split between frontend and backend, the cost of standard headers and template instantiation, and how much precompiled headers, import std, extern template, unity builds, parallel builds, compiler caches, linkers, debug info and LTO each save or cost."
group: Engineering practice
tags: toolchain, build, compile time, precompiled headers, modules, unity build, LTO
updated: 2026-10-19
---

!!! tldr
    - Measure before optimizing. Clang's `-ftime-trace` gives the time taken by every header, every template instantiation and every optimization pass in a translation unit. For an 18-line `std::format` program in our tests, the frontend takes about 2/3, and parsing `<format>` and instantiating `std::format` are the most expensive parts.
    - The cost of headers and template instantiation is multiplied by the number of translation units. Precompiled headers, `import std;` and `extern template` all make that work happen once; in our tests each cut the frontend work of a single translation unit roughly in half.
    - A unity build concatenates several `.cpp` files into one translation unit. In our tests it cut total CPU time for 48 files to about 1/4. The cost is that unnamed namespaces and `static` names collide, and overload resolution may silently change.
    - Parallel builds are limited by core count, memory and the serial link step. The choice of linker matters a lot: for the same set of object files on our test machine, the 2022 ld64 took 2.85 s and the new linker shipped with Xcode 0.28 s.
    - `-g` makes object files several times larger and cost 7% to 16% more compile CPU in our tests. Full LTO moves optimization into the serial link step, so changing one file re-optimizes the whole program; ThinLTO with a cache avoids that.

!!! note "Test setup"
    Apple M2 Pro (8 performance cores + 4 efficiency cores, 16 GB memory), macOS, Homebrew Clang 23.1 (libc++), CMake 3.29, Ninja 1.12, GNU Make 3.81. Other compile jobs were running on the machine during measurement (load average 50 to 100), so wall-clock times only show trends. For single compile commands we mainly report the **instruction count** given by `/usr/bin/time -l` (instructions retired, the number of instructions the CPU actually executed), which is almost unaffected by load; for commands involving several processes we report the sum of user and system CPU time. All numbers are local observations on this machine.

The standard gives only one model of the build process: a program consists of translation units that can be translated separately and then linked together (note 1 in [[lex.separate#1]]). Source files, translation units and translated translation units need not be stored as files, nor need there be a one-to-one correspondence between them and any external representation (note 2 in [[lex.separate#1]]). These two sentences leave implementations a lot of room: precompiled headers, BMIs, compiler caches and LTO are all optimizations made within that room. What each step does in detail is covered in [[toolchain/compilation-pipeline]].

## Where the time goes

A typical small translation unit:

```cpp title="app.cpp" run ok
#include <algorithm>
#include <format>
#include <map>
#include <string>
#include <vector>

struct Order { std::string sym; int qty; double px; };

std::string report(std::vector<Order> v) {
  std::ranges::sort(v, {}, &Order::px);
  std::map<std::string, int> pos;
  for (const auto& o : v) pos[o.sym] += o.qty;
  std::string out;
  for (const auto& [s, q] : pos)
    out += std::format("{:>6} {:>8}\n", s, q);
  return out;
}
```

`-ftime-trace` makes Clang write a `.json` with the same name next to the object file, in Chrome's trace event format; drag it into `chrome://tracing` or Perfetto to see a flame graph:

```text
$ clang++ -std=c++2c -O2 -c app.cpp -ftime-trace -o app.o
$ ls -l app.json
-rw-r--r--  1 weiran  wheel  375880 Oct 19 17:50 app.json
```

By default only events longer than 500 µs are recorded. `-ftime-trace-granularity=0` records every event; in our tests the JSON grew to 65 MB and that compile was about 40% slower, so it is rarely worth it.

ClangBuildAnalyzer can summarize many traces; it wasn't installed on our test machine. A single trace can be summarized in a few lines of Python: events whose names start with `Total ` are cumulative durations per event kind, and `Source` events are paired `b`/`e` (begin, end) records, where the outermost ones give the time for each directly included header. The results of this run:

| Event | Time | Notes |
|---|---:|---|
| ExecuteCompiler | 2007 ms | The whole compile |
| Frontend | 1346 ms | Preprocessing, parsing, semantic analysis, instantiation, IR generation |
| of which Source | 579 ms | Processing headers: `<format>` 324 ms, `<algorithm>` 197 ms, `<vector>` 33 ms, `<map>` 25 ms |
| of which PerformPendingInstantiations | 427 ms | Function templates instantiated together at the end of the translation unit |
| of which CheckConstraintSatisfaction | 501 ms | Checking concept constraints; overlaps the items above |
| Backend | 647 ms | Optimization (400 ms) and machine code generation (245 ms) |

Merging the `InstantiateFunction` events by template name, the most expensive are `std::format` (421 ms, including the instantiations it triggers) and `std::vformat_to` (368 ms); the 10 specializations of `std::__tree` add up to 155 ms. `<string>` doesn't appear in the header list because `<algorithm>` and `<format>` already include it indirectly, and the second inclusion is skipped by its include guard.

Two notes on reading this. First, the time of a nested event includes its children, so adding up rows is meaningless; only compare rows at the same level. Second, a trace describes one translation unit; the project's total time is each translation unit's time times the number of times it occurs. If a header is included by 300 `.cpp` files, you pay for it 300 times.

### Frontend and backend

`-fsyntax-only` runs only the frontend and generates no code. Comparing it with `-O0` and `-O2`, the difference is roughly the backend cost:

| Command | Instructions | CPU time |
|---|---:|---:|
| `-fsyntax-only` | 4.68 G | 0.56 s |
| `-c -O0` | 5.67 G | 0.66 s |
| `-c -O2` | 8.22 G | 1.07 s |

This translation unit is almost entirely frontend at `-O0`, while at `-O2` the backend is about 40%. Translation units with many headers and few function bodies lean toward the frontend; translation units where lots of template code is instantiated and then inlined lean toward the backend. Frontend cost is reduced by avoiding repeated parsing and instantiation, backend cost by reducing the amount of code to optimize and by choosing optimization levels. The tools differ, so look at the split first.

## The cost of headers

`#include` replaces the directive with the entire contents of the header ([[cpp.include#3]]). The replacement is textual, and the included content goes through every phase of translation along with the source file. Including one standard header at a time on our test machine, the line count of the `-E -P` output and the cost of `-fsyntax-only`:

| Header | Lines after preprocessing | Size | Instructions | CPU time |
|---|---:|---:|---:|---:|
| (empty file) | — | — | 0.34 G | 0.02 s |
| `<cstddef>` | 141 | 10 KB | 0.36 G | 0.03 s |
| `<memory>` | 11 333 | 704 KB | 0.87 G | 0.09 s |
| `<map>` | 15 943 | 970 KB | 1.07 G | 0.11 s |
| `<string>` | 14 041 | 853 KB | 1.10 G | 0.14 s |
| `<functional>` | 20 622 | 1.27 MB | 1.25 G | 0.13 s |
| `<algorithm>` | 24 193 | 1.38 MB | 1.38 G | 0.14 s |
| `<ranges>` | 23 845 | 1.46 MB | 1.45 G | 0.16 s |
| `<vector>` | 23 678 | 1.34 MB | 1.49 G | 0.16 s |
| `<format>` | 30 126 | 1.65 MB | 2.64 G | 0.27 s |
| `<regex>` | 35 207 | 1.93 MB | 2.67 G | 0.29 s |
| `<print>` | 30 258 | 1.66 MB | 2.76 G | 0.29 s |
| `<iostream>` | 35 635 | 1.96 MB | 3.24 G | 0.35 s |
| `<chrono>` | 41 123 | 2.31 MB | 3.28 G | 0.38 s |
| All 13 above together | 77 273 | 4.43 MB | 5.12 G | 0.68 s |

Line count and cost aren't proportional: `<format>` has only 27% more lines than `<vector>` but 77% more instructions, because it instantiates many templates and checks many constraints in the header itself. Including all 13 headers together costs only 60% more than the largest single one, because they share most of their internal headers.

This table gives a floor for a single translation unit: write `#include <chrono>` and that `.cpp` needs at least 0.38 s of CPU time. How to organize headers so that you include less and include it cheaply is covered in [[toolchain/physical-design]] and not repeated here.

## The cost of template instantiation

Every specialization of a template is a new declaration that the compiler copies and substitutes ([[temp.inst]]). Depending on how something is written, the same result may need orders of magnitude more specializations. The program below gets the `I`th element of a type pack in two ways: the classic recursive partial specialization, and C++26 pack indexing `Ts...[I]` ([[dcl.type.pack.index]], [[P2662R3]]).

```cpp title="meta.cpp" run ok
#include <cstddef>
#include <type_traits>
#include <utility>

#ifndef N
#define N 200
#endif

template <std::size_t> struct T {};

#ifdef RECURSIVE
template <std::size_t I, class... Ts> struct nth;
template <class H, class... Ts>
struct nth<0, H, Ts...> { using type = H; };
template <std::size_t I, class H, class... Ts>
struct nth<I, H, Ts...> : nth<I - 1, Ts...> {};
template <std::size_t I, class... Ts>
using nth_t = typename nth<I, Ts...>::type;
#else
template <std::size_t I, class... Ts>
using nth_t = Ts...[I];                  // C++26 pack indexing
#endif

template <class... Ts, std::size_t... I>
constexpr bool check(std::index_sequence<I...>) {
  return (std::is_same_v<nth_t<I, Ts...>, T<I>> && ...);
}
template <std::size_t... I>
constexpr bool all(std::index_sequence<I...> s) {
  return check<T<I>...>(s);
}
static_assert(all(std::make_index_sequence<N>{}));
```

The recursive version instantiates `I + 1` specializations of `nth` to compute `nth_t<I, ...>`, each carrying a copy of the remaining type list. Doing that for every `I` gives about N²/2 class specializations, with type lists of total length on the order of N³. Pack indexing lets the compiler take the `I`th element directly, without intermediate specializations.

| | N = 100 | N = 200 | N = 1000 |
|---|---:|---:|---:|
| Recursive partial specialization (`-DRECURSIVE`) | 2.64 G instructions, 176 MB | 15.4 G instructions, 829 MB | — |
| `Ts...[I]` | 0.64 G instructions, 64 MB | 0.73 G instructions, 68 MB | 3.34 G instructions, 198 MB |

Doubling N multiplies the recursive version's instruction count by about 5.8 and its memory by 4.7; the pack-indexing version at N = 1000 costs less than a quarter of the recursive version at N = 200. Recursion depth is also limited: the standard recommends that implementations support at least 1024 levels of recursively nested template instantiations ([[implimits#1.41]]), and infinitely recursive instantiation is UB ([[temp.inst#18]]).

In `-ftime-trace`, this kind of problem shows up as an `InstantiateClass` or `InstantiateFunction` event with a very deep tree of children. The usual fix is to replace hand-written recursion with facilities built into the compiler: pack indexing, fold expressions, `std::make_index_sequence` (implemented with a builtin in libc++), and `if constexpr` instead of specialization-based dispatch. The ideas are in [[topics/compile-time-programming]].

## Precompiled headers

Headers are processed again for every translation unit. A **precompiled header** (PCH) serializes the result of processing a set of headers to disk, and later compiles load it directly. The standard doesn't know PCHs exist; they are legal because the result must be the same as if those headers had really been included (note 2 in [[lex.separate#1]] allows translation units not to exist as text).

```text
$ cat pch.h
#pragma once
#include <algorithm>
#include <format>
#include <map>
#include <string>
#include <vector>
$ clang++ -std=c++2c -x c++-header pch.h -o pch.h.pch
$ clang++ -std=c++2c -O0 -include-pch pch.h.pch -c app.cpp -o app.o
```

`-include-pch` is equivalent to including `pch.h` before the first line of `app.cpp`; after that, `app.cpp`'s own `#include <format>` is no longer expanded because of the include guard. Measurements:

| | Instructions | CPU time |
|---|---:|---:|
| Generating `pch.h.pch` (14.7 MB) | 4.09 G | 0.45 s |
| `app.cpp`, `-O0`, without PCH | 5.69 G | 0.65 s |
| `app.cpp`, `-O0`, with PCH | 3.08 G | 0.31 s |

The remaining 3 G instructions are mostly instantiation and code generation for `std::format` and other templates in this translation unit, which a PCH can't save. Generating the PCH costs about as much as one compile that includes all the headers, so it only pays off when dozens of translation units in a project share it.

A PCH is tied to the compile options. Using a PCH generated with `-O0` for an `-O2` compile, Clang refuses outright:

```text
$ clang++ -std=c++2c -O2 -include-pch pch.h.pch -c app.cpp -o app.o
error: OptimizationLevel differs in precompiled file '/tmp/bs.UQgY/pch.h.pch' vs. current file
1 error generated.
```

A different language standard (`C++26 was enabled in precompiled file ... but is currently disabled`) or a different value for the same macro on the command line (`definition of macro 'X' differs between the precompiled file ... ('1') and the command line ('2')`) are errors too. Conversely, if the PCH was generated with `-DX=1` and used without `-DX`, Clang 23 doesn't complain and `X` is still defined. So each configuration needs its own PCH. Build systems usually handle this for you; in CMake it is `target_precompile_headers`, see [[toolchain/cmake]].

!!! pitfall "A PCH hides missing includes"
    A PCH is force-included at the top of every translation unit, so a `.cpp` that forgot to include `<map>` still compiles. Switch build configuration, turn off the PCH, or move the file to another project, and it fails to compile. Headers should be self-contained; see [[toolchain/physical-design]]. Keeping one build without PCH in continuous integration catches this kind of problem.

## `import std;`

The standard library module `std` ([[P2465R3]], C++23) is another way to do the work only once, and a standard one. libc++ provides the module interface source, which must first be precompiled into a BMI:

```text
$ clang++ -std=c++2c -Wno-reserved-module-identifier --precompile \
    /opt/homebrew/opt/llvm/share/libc++/v1/std.cppm -o std.pcm
$ clang++ -std=c++2c -O0 -fmodule-file=std=std.pcm -c app_mod.cpp -o app_mod.o
```

`app_mod.cpp` is `app.cpp` with its five `#include` lines replaced by `import std;`. Measurements:

| | `#include` five headers | `import std;` |
|---|---:|---:|
| Precompiling `std.pcm` (35.5 MB) | — | 9.79 G, 1.23 s |
| `-fsyntax-only` | 4.68 G | 1.99 G |
| `-c -O0` | 5.76 G | 3.01 G |
| `-c -O2` | 8.22 G | 5.46 G |

`import std;` imports the entire standard library, and the frontend work is still less than half that of including five headers, comparable to a PCH. The difference is that modules are part of the language: macros don't cross `import`, import order doesn't affect meaning, and there is no PCH-style hiding of missing includes. A BMI is likewise tied to the compiler version and key options. The kinds of BMI, dependency scanning and CMake integration are covered in [[toolchain/modules-in-practice]].

## `extern template`

If many translation units use the same class template specialization, each one instantiates, optimizes and generates code for its member functions, and in the end the linker keeps only one copy. An **explicit instantiation declaration** ([[g:explicit-instantiation-declaration|explicit instantiation declaration]]) `extern template class X<T>;` tells the compiler that there is an **explicit instantiation definition** of this specialization elsewhere, so this translation unit need not instantiate it ([[temp.explicit#2]]). How to write it, how to organize the `.cpp`, and the fact that it only works for the listed arguments are covered in [[toolchain/physical-design]].

What needs adding here is the case of inline members. Take a class template `Table<K>` with three member functions defined in the header, and 16 translation units that all use `Table<std::string>`. At `-O2`, before and after adding `extern template class Table<std::string>;`:

| | Single translation unit | CPU total, 16 translation units | `u01.o` |
|---|---:|---:|---:|
| Members are ordinary functions, no `extern template` | 8.13 G | 16.6 s | 106 KB |
| Members are ordinary functions, with `extern template` | 3.50 G | 6.1 s, plus 1.0 s for `table.cpp` | 2.9 KB |
| Members are inline, no `extern template` | 8.10 G | — | — |
| Members are inline, with `extern template` | 7.12 G | — | — |

When the member functions are inline (defined in the class, or explicitly marked `inline`), `extern template` saves almost no time. This is deliberate in the standard: an inline function that is the subject of an explicit instantiation declaration is still implicitly instantiated when odr-used, so that it can be inlined; only a separate function body need not be generated (note 3 in [[temp.inst#5]]). To save time, define the heavy members as non-inline.

The standard library does this too. libc++'s `<string>` has explicit instantiation declarations for most members of `basic_string<char>` and `basic_string<wchar_t>`, with the definitions in `libc++.dylib`, so translation units don't have to generate code for `std::string`'s members.

## Unity builds

A **unity build** (also called a jumbo build) compiles several `.cpp` files concatenated into one source file with `#include`. Common headers are processed only once, and templates instantiated only once. With `CMAKE_UNITY_BUILD` on, CMake generates one such file for every 8 source files:

```cpp title="unity_0_cxx.cxx"
/* generated by CMake */

/* NOLINTNEXTLINE(bugprone-suspicious-include) */
#include "/tmp/bs.UQgY/proj/src/main.cpp"

/* NOLINTNEXTLINE(bugprone-suspicious-include) */
#include "/tmp/bs.UQgY/proj/src/r00.cpp"
...
```

Our test project has 48 source files similar to `app.cpp` plus a `main.cpp`, built in Release (`-O3`) with `ninja -j12`:

| | Translation units compiled | CPU total | Wall clock | Rebuild after changing one `.cpp` |
|---|---:|---:|---:|---:|
| Normal build | 49 | 63.4 s | 16.1 s | 1.14 s CPU |
| Unity build | 7 | 14.8 s | 5.4 s | 1.99 s CPU |

CPU time for a full build drops to about 1/4. There are three costs. First, changing one file recompiles its whole group; in our tests incremental rebuilds became about 75% more expensive. Second, parallelism drops: 7 translation units can't fill 12 cores. Third, and most troublesome, translation unit boundaries change, and many C++ rules work per translation unit.

### Internal name collisions

Every source file has helper code like this:

```cpp title="r00.cpp (excerpt)"
namespace {
struct Row { std::string key; double val; };
std::string fmt_row(const Row& r) {
  return std::format("{:>8} {:10.3f}\n", r.key, r.val);
}
}  // namespace
```

Compiled separately this is entirely correct: names in an unnamed namespace have internal linkage ([[basic.link#4]]), and each translation unit's `Row` is a different entity. Concatenated, the build fails:

```text
In file included from .../Unity/unity_5_cxx.cxx:7:
/tmp/bs.UQgY/proj/src/r40.cpp:7:8: error: redefinition of 'Row'
    7 | struct Row { std::string key; double val; };
      |        ^
/tmp/bs.UQgY/proj/src/r39.cpp:7:8: note: previous definition is here
```

The reason is in [[namespace.unnamed#1]]: within a translation unit, the *unique* name of every unnamed namespace is replaced by the same identifier. When the unnamed namespaces of two files end up in the same translation unit, they are the same namespace, `Row` is defined twice, and the rule allowing at most one definition per translation unit is violated ([[basic.def.odr#2]]). The same goes for `static` functions and `static` variables.

This kind of collision at least produces an error. More dangerous is the case where there is no error but the meaning changes:

<div class="compare" markdown="1">

```cpp title="a.cpp"
#include <cstdio>
static void show(int) {
  std::puts("a.cpp: show(int)");
}
void fa() { show(1); }
```

```cpp title="b.cpp"
#include <cstdio>
static void show(long) {
  std::puts("b.cpp: show(long)");
}
void fb() { show(1); }
```

</div>

The two `show` functions have different signatures, so this is not a redefinition. Compiled separately, `fb` only sees `show(long)` and prints `b.cpp: show(long)`. In one translation unit, `show(1)` in `b.cpp` also sees `a.cpp`'s `show(int)`, overload resolution picks the exact match `show(int)`, and in our tests the output becomes two lines of `a.cpp: show(int)`. The program is still well-formed; the only clue is `-Wunused-function` reporting that `b.cpp`'s `show(long)` is unused. Macros, `using namespace` directives and file-scope `using` declarations have the same problem: they all leak from one file into the next.

### Remedies

CMake provides a few switches: set `SKIP_UNITY_BUILD_INCLUSION` on files that shouldn't be merged; or set `UNITY_BUILD_UNIQUE_ID`, and in a unity build CMake defines a macro with a different value for each file, which the source can use to add another level inside the unnamed namespace:

```cpp title="r00.cpp (rewritten)"
#ifndef UNITY_ID
#define UNITY_ID
#endif

namespace { namespace UNITY_ID {
struct Row { std::string key; double val; };
std::string fmt_row(const Row& r);
}}  // namespace

// uses are written UNITY_ID::Row, UNITY_ID::fmt_row
```

Uses must be qualified. If you take the shortcut of writing `using namespace UNITY_ID;` inside the unnamed namespace, all these using-directives end up in the same unnamed namespace after merging, and later files see every file's `fmt_row`. We verified this with a minimal two-file example: Clang reports `call to ... is ambiguous`.

One more observation from our tests: in CMake 3.29, a project that sets `CMAKE_CXX_STANDARD 26` gets module dependency scanning enabled by default, and source files that take part in scanning are not merged, so the unity build silently has no effect. You also need to set `CMAKE_CXX_SCAN_FOR_MODULES OFF` (CMake's `UNITY_BUILD` documentation states this limitation).

Recommendation: unity builds are suitable for full builds in continuous integration, with normal builds for day-to-day development; give internal helpers in new code names unlikely to collide, or wrap them in `UNITY_ID` from the start; and keep a non-unity build in continuous integration as well, confirming both pass with the same test results.

## Parallel builds

Separate translation is the basis of parallelism: translation units don't depend on each other (except with modules) and can be compiled at the same time ([[lex.separate]]). The same 49-file project, full build, `ninja -jN`:

| `-j` | Wall clock | CPU total |
|---:|---:|---:|
| 1 | 54.8 s | 51.8 s |
| 4 | 16.7 s | 55.5 s |
| 8 | 9.3 s | 54.9 s |
| 12 | 8.5 s | 57.6 s |

Scaling is close to linear up to 8 cores and gains little beyond that: the extra 4 are efficiency cores, and the machine had other load. Two more things limit parallelism. One is memory: each compiler process peaked at about 200 MB in our tests, and template-heavy translation units can reach several GB; with too large a `-j` the machine starts swapping and gets slower. Ninja's `pool` can limit the concurrency of heavy jobs separately. The other is linking, which runs serially after all compilation finishes and is discussed separately below.

Without `-j`, Ninja builds in parallel by default (14 jobs on our test machine) and Make builds serially; this is the most common difference between them. In a full build the work is all done by the compiler and the build tool's own overhead is negligible. The difference shows in a no-op build where no file changed: for this project, `make -j12` takes 0.14 s and `ninja` under 10 ms. It only matters for projects with thousands of files built hundreds of times a day. Which one CMake generates is chosen with `-G`; Ninja is recommended.

## Compiler caches

Neither ccache nor sccache was installed on our test machine, so this section only describes the mechanism, without local output.

A compiler cache wraps the compile command. It hashes the compiler version, command-line options and input contents together, and on a hit copies the previous `.o` without running the compiler. There are two ways to hash the input: preprocess and hash the preprocessed result (always correct, but you pay for preprocessing every time), or hash the source file and every header it depends on directly (ccache's direct mode, faster, relying on the header list the compiler reports). sccache can also keep the cache in remote storage, shared across machines and continuous integration jobs.

It helps when the same source is rebuilt from scratch repeatedly: switching branches and back, `make clean`, continuous integration starting from a clean directory every time. Day-to-day incremental builds only compile changed files anyway, so a cache helps little there.

Some things to watch for:

- Different absolute paths on the command line (including source paths that `-g` writes into debug info) give different hashes. The same code checked out in different directories needs path rewriting configured (ccache's `base_dir`, or Clang's `-fdebug-prefix-map`) to share a cache.
- PCHs and module BMIs are extra inputs that the cache tool must support specifically; otherwise the hit rate is very low, or nothing is cached at all. Check the documentation for the version you use.

## Linkers

After all compilation is done, the linker must process every object file at once. What the linker does (resolving symbols, merging weak definitions, relocation) is covered in [[toolchain/linking-and-symbols]]. It is an inherently serial step of the build, and often the slowest step of an incremental build: change one `.cpp`, compile one file, then relink the whole program.

Our test used 400 object files (93 MB total, about 400,000 symbols, each file also carrying weak definitions of 1000 inline function template specializations to be merged at link time), comparing the three Mach-O linkers available on our test machine:

| Linker | Wall clock | CPU |
|---|---:|---:|
| ld64-530 (the 2022 ld64, from another toolchain on PATH) | 2.85 s | 2.98 s |
| Xcode's ld64-957 (`-Wl,-ld_classic`, deprecated) | 0.54 s | 0.76 s |
| Xcode's new linker ld-1266 (Xcode's default) | 0.28 s | 0.83 s |

The new linker uses no less CPU time than the old ld64, but it is multithreaded, and its wall-clock time is half. LLVM's lld (`ld64.lld` for Mach-O) and mold weren't installed and weren't measured. Clang selects a linker with `-fuse-ld=lld` or `--ld-path=<path>`.

!!! pitfall "Which `ld` is Clang using?"
    On our test machine, Homebrew Clang by default used the first `ld` found on `PATH`, which turned out to be the ld64-530 bundled with Anaconda rather than Xcode's linker. It doesn't understand the DWARF 5 that Clang 23 generates: linking object files built with `-g` warns `can't parse dwarf compilation unit info` and writes no debug map, so `dsymutil` then reports `no debug symbols in executable` and the debugger can't find source lines. `clang++ -### x.o` shows the path of the linker actually invoked.

## Debug info

`-g` makes the compiler generate DWARF descriptions for every function, type and variable. It doesn't change the generated code, but it is a fair amount of extra work. `app.cpp` again:

| Options | `-O0` instructions | `-O0` object file | `-O2` instructions | `-O2` object file |
|---|---:|---:|---:|---:|
| None | 5.67 G | 405 KB | 8.22 G | 113 KB |
| `-gline-tables-only` | 5.86 G | 571 KB | 8.48 G | 339 KB |
| `-g` | 6.07 G | 1046 KB | 9.52 G | 891 KB |

`-O2 -g` takes 16% more instructions than `-O2`, and the object file is 7.9 times larger, mostly type descriptions for standard library templates. `-gline-tables-only` keeps only the mapping from addresses to source lines, enough for crash stacks and profilers to show file names and line numbers, but the debugger can't see local variables or types.

For the whole 49-file project, full `-O2` build:

| Options | CPU total | Object files total | Link | `dsymutil` |
|---|---:|---:|---:|---:|
| `-g0` | 59.8 s | 6.0 MB | 0.09 s | — |
| `-gline-tables-only` | 60.4 s | 18.0 MB | 0.08 s | 0.09 s, dSYM 3.6 MB |
| `-g` | 69.5 s | 45.2 MB | 0.09 s | 0.26 s, dSYM 9.3 MB |

On macOS the linker doesn't copy DWARF into the executable; it only records a debug map pointing at the individual `.o` files, so `-g` barely affects link time. When a standalone debug info bundle is needed, `dsymutil` collects them into a `.dSYM`. Linux ELF linkers copy all `.debug_*` sections into the output by default, so linking slows noticeably when debug info is large, which is why `-gsplit-dwarf` exists; we couldn't verify this on our test machine.

Recommendation: use `-g` for day-to-day development builds, so information is complete when you need to debug; for release builds that only need symbolized crash stacks, use `-gline-tables-only`; continuous integration jobs that only compile and run tests can omit debug info entirely.

## When LTO slows the build

**Link-time optimization** (LTO) makes the compiler store LLVM IR instead of machine code in each `.o`, and at link time optimizes the IR of the whole program together, which enables inlining across translation units. Its effect on run-time speed is covered in [[perf/lto-pgo]]. For build time, the same 49-file project, Xcode linker, `ninja -j12`:

| | Full build wall clock | Rebuild after changing one `.cpp` | Relink only |
|---|---:|---:|---:|
| No LTO | 10.0 s | 1.38 s | 0.17 s |
| `-flto=thin` | 11.8 s | 2.10 s (CPU 9.0 s) | 1.22 s (CPU 8.9 s) |
| `-flto=thin` + cache | — | 0.89 s | 0.12 s |
| `-flto` (full LTO) | 9.2 s | 3.02 s | 2.20 s |

Full builds differ little: optimization and code generation move from the compile phase to the link phase, with about the same total. The difference is in incremental builds. Full LTO merges all IR into one module and optimizes it serially, so changing one file re-optimizes the whole program; link time grows with program size and can reach minutes and several GB of memory for large projects. ThinLTO does only a summary analysis of the whole program and runs each module's backend in parallel, so its CPU time is far larger than its wall-clock time; but without a cache it too redoes every module each time.

With `-Wl,-cache_path_lto,<dir>` (`--thinlto-cache-dir=` for lld on ELF), ThinLTO re-optimizes only the affected modules, and in our tests incremental rebuilds were even faster than without LTO, because the compile phase only generates IR and no machine code.

Recommendation: don't enable LTO for day-to-day development builds; when release builds need LTO, use ThinLTO with a cache configured; use full LTO only when measurement shows it actually brings extra performance.

## Questions

!!! question "Unity builds and the ODR"
    Two `.cpp` files each define a `struct Row` in an unnamed namespace, with different members. Is the program well-formed when they are compiled separately? What is the basis for the error in a unity build? If both `Row`s are changed to ordinary namespace-scope `struct Row` (not in an unnamed namespace), what happens when compiled separately?

<details markdown="1">
<summary>Answer</summary>

Compiled separately, it is well-formed: an unnamed namespace has internal linkage ([[basic.link#4]]), and each translation unit's *unique* name is different ([[namespace.unnamed#1]]), so the two `Row`s are different entities. In a unity build they are in the same translation unit, where the *unique* of every unnamed namespace is the same identifier, so one entity is defined twice in one translation unit, violating [[basic.def.odr#2]], which must be diagnosed.

Without the unnamed namespace, the two `Row`s are the same class with external linkage, defined in different translation units but not consisting of the same sequence of tokens, violating [[basic.def.odr#16]], with no diagnostic required. The linker usually can't tell (a class by itself produces no symbols); the problem appears when both sides instantiate members of `std::vector<Row>`: only one copy of each same-named weak symbol is kept, and the other translation unit uses the wrong layout. A unity build actually turns this hidden ODR violation into a compile error.

</details>

!!! question "`extern template` and inline"
    Why does adding `extern template class X<int>;` to a class template whose members are all defined in the class save almost no compile time at `-O2`? What about `-O0`?

<details markdown="1">
<summary>Answer</summary>

Member functions defined in the class are inline. Note 3 in [[temp.inst#5]] says that an inline function, even if it is the subject of an explicit instantiation declaration, does not count as a declared specialization; it is still implicitly instantiated when odr-used so that it can be considered for inlining, and only a separate function body need not be generated. So the instantiation and optimization work is still there. In our tests `-O0` saved about 15% of instructions (5.74 G to 4.85 G) and `-O2` about 12% (8.10 G to 7.12 G), whereas non-inline members save 57%.

</details>

## Summary

| Technique | What it saves | Observed in our tests | Cost |
|---|---|---|---|
| `-ftime-trace` | — | Finds the most expensive headers and instantiations | None |
| Trimming includes | Parsing | One line of `<chrono>`: 0.38 s | Header cleanup, see [[toolchain/physical-design]] |
| Rewriting metaprograms | Instantiation | Pack indexing over 20 times faster than recursion | Needs a recent standard |
| Precompiled headers | Parsing | Frontend work roughly halved | Tied to options; hides missing includes |
| `import std;` | Parsing | Comparable to PCH | Build system must support modules |
| `extern template` | Instantiation and code generation | 16 TUs total from 16.6 s to 7.1 s | No effect on inline members; only for listed arguments |
| Unity build | Repeated parsing and instantiation | Full-build CPU about 1/4 | Internal name collisions; overloads silently change; slower incremental builds |
| Parallelism (Ninja) | Wall clock | Close to linear within 8 cores | Memory |
| Compiler cache | Repeated compiles | Not installed | Paths, PCH and modules need configuration |
| A faster linker | Linking | 2.85 s to 0.28 s | None |
| Less debug info | Backend and disk | `-g` adds 7% to 16% | Debugging experience |
| No LTO, or ThinLTO + cache | Link-time optimization | Full LTO incremental rebuilds over 2 times slower | Run-time performance |
