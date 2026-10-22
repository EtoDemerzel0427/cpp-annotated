---
title: Testing, sanitizers and fuzzing
summary: "How to test C++ code so that UB and data races get caught: a minimal test framework, compile-time tests and compile-failure tests, what ASan, LSan, UBSan and TSan each catch, what they cost and which can't be combined, standard library hardening in tests, a CI build matrix, fuzzing with libFuzzer, property-based testing, coverage with llvm-cov, and the same tests giving different results at -O0 and -O2."
group: Engineering practice
tags: toolchain, testing, sanitizers, ASan, UBSan, TSan, fuzzing, coverage, hardening
updated: 2026-10-19
---

!!! tldr
    - Ordinary unit tests only check whether results are right. UB and data races often make a wrong program give the right results in tests, so tests must be run again in sanitizer builds; the sanitizer is what decides whether there is UB.
    - UBSan by default keeps running after a report, and the exit code is still 0. Tests need `-fno-sanitize-recover=undefined`; otherwise a UB report is just a log line nobody reads.
    - ASan and TSan can't go in the same build, and there is no MSan on macOS. CI needs at least three configurations: ASan+UBSan, TSan, and a plain `-O2`.
    - Hand-written test cases rarely think of malicious or malformed input. libFuzzer found, in under a second on our test machine, an out-of-bounds read that all unit tests and 100% line coverage had missed.
    - Compile-time tests (`static_assert` plus `constexpr`) and compile-failure tests (concepts plus `requires` expressions) stop some errors at compile time, but they have blind spots too.

!!! note "Test setup"
    Apple M2 Pro, macOS, Homebrew Clang 23.1.3 (libc++), CMake 3.29.3, Ninja 1.12.1. `/opt/homebrew/opt/llvm/bin` is at the front of `PATH` so that the sanitizer runtimes can find `llvm-symbolizer`; Anaconda's old `ld` was removed from `PATH` (see [[toolchain/compilation-pipeline]]). Debug info uses `-gdwarf-4`, for the reason given in [[topics/dangling-references]]. GoogleTest, Catch2 and doctest weren't installed, so the tests below use a few lines of our own code. Long call stacks in reports are trimmed.

## A parser and its tests

All experiments below revolve around a small function: it parses text such as `a=1;b=2` into key-value pairs, with a backslash escaping the next character.

```cpp title="kv.hpp"
#pragma once
#include <optional>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

using KV = std::vector<std::pair<std::string, std::string>>;

// "a=1;b=x\;y" -> {"a","1"}, {"b","x;y"}
std::optional<KV> parse_kv(std::string_view s);
```

```cpp title="kv.cpp"
#include "kv.hpp"

std::optional<KV> parse_kv(std::string_view s) {
  KV out;
  std::string key, val;
  std::string* cur = &key;
  for (std::size_t i = 0; i < s.size(); ++i) {
    char c = s[i];
    if (c == '\\') {              // escape: keep the next character as is
      cur->push_back(s[++i]);
      continue;
    }
    if (c == '=' && cur == &key) { cur = &val; continue; }
    if (c == ';') {
      if (cur != &val) return std::nullopt;
      out.emplace_back(std::move(key), std::move(val));
      key.clear(); val.clear(); cur = &key;
      continue;
    }
    cur->push_back(c);
  }
  if (cur == &val) out.emplace_back(std::move(key), std::move(val));
  else if (!key.empty()) return std::nullopt;
  return out;
}
```

This code has a bug: when the input ends with a single backslash, the index in `s[++i]` equals `s.size()`. We will see below which techniques find it and which don't.

### Tests without a framework

At its core, a test framework does only three things: check a condition, report the location on failure, and finally tell the build system whether it passed via the exit code. C++20's `std::source_location` means a macro is no longer needed to get the line number; the macro is used only to turn the expression into a string:

```cpp title="check.hpp"
#pragma once
#include <cstdio>
#include <source_location>

inline int g_failures = 0;

inline void check(bool ok, const char* expr,
                  std::source_location loc =
                      std::source_location::current()) {
  if (!ok) {
    ++g_failures;
    std::printf("%s:%u: CHECK failed: %s\n",
                loc.file_name(), loc.line(), expr);
  }
}
#define CHECK(...) check(static_cast<bool>(__VA_ARGS__), #__VA_ARGS__)
```

The default argument `std::source_location::current()` is evaluated at the call site, so the line reported is the one where `CHECK` is. The macro is variadic so that an expression containing a comma, such as `CHECK(f<a, b>())`, isn't split into two macro arguments.

```cpp title="kv_test.cpp"
#include "check.hpp"
#include "kv.hpp"

int main() {
  auto r = parse_kv("a=1;b=2");
  CHECK(r && r->size() == 2);
  CHECK((*r)[1] == KV::value_type{"b", "2"});

  auto e = parse_kv(R"(b=x\;y)");
  CHECK(e && (*e)[0].second == "x;y");

  CHECK(!parse_kv("novalue;"));
  CHECK(parse_kv("") && parse_kv("")->empty());
  CHECK(parse_kv("a=1")->size() == 2);       // a deliberately wrong test case

  std::printf("%s\n", g_failures ? "FAILED" : "OK");
  return g_failures != 0;
}
```

```text
$ clang++ -std=c++2c -Wall -Wextra -pedantic -g kv.cpp kv_test.cpp -o kv_test && ./kv_test
kv_test.cpp:14: CHECK failed: parse_kv("a=1")->size() == 2
FAILED
$ echo $?
1
```

CTest only looks at the exit code; nonzero counts as failure (how to hook it up is in [[toolchain/cmake]]). Remove the deliberately wrong line and the tests pass, while the out-of-bounds read is still in the code.

!!! note "Test frameworks"
    GoogleTest, Catch2 and doctest add to this mechanism: test registration (no need to call tests by hand from `main`), filtering by name, fixtures, parameterization, printing both sides' values on failure, and JUnit XML output for CI to display. They can be installed with Homebrew or pulled in with CMake's `FetchContent` (see [[toolchain/dependencies]]). They weren't installed on our test machine, so their output isn't shown here. Which one you choose makes no difference to what follows: sanitizers, fuzzing and coverage all act on compile options and the runtime, independent of how assertions are written.

## Compile-time tests

### `static_assert` and `constexpr`

Turn `parse_kv` into a `constexpr` function defined in a header (`kvc.hpp`, with the body unchanged and just `constexpr` added in front), and the tests can run at compile time. Since C++20, `std::string` and `std::vector` can allocate memory during constant evaluation, provided the allocation is freed before evaluation ends.

```cpp title="kvc_test.cpp"
#include "kvc.hpp"
static_assert(parse_kv("a=1;b=2")->size() == 2);
static_assert(parse_kv(R"(b=x\;y)")->at(0).second == "x;y");
static_assert(!parse_kv("novalue;"));
int main() {}
```

The condition of a `static_assert` must be a constant expression; if its value is false the declaration fails and the program is ill-formed ([[dcl.pre#13]]), and the implementation must reject it ([[intro.compliance.general#2]] ¶2.5). More useful is another rule: if core-language UB occurs during constant evaluation, the expression isn't a constant expression ([[expr.const.core#2]]), so compile-time tests also check for signed overflow, out-of-bounds accesses, use of objects outside their lifetime and so on along the executed path. An example of this is in [[topics/undefined-behavior]].

Add the trailing-backslash case, and the result depends on whether the standard library has hardening enabled:

```cpp
static_assert(parse_kv(R"(a=1\)")->at(0).second == "1");
```

```text
$ clang++ -std=c++2c kvc_test.cpp
error: static assertion failed due to requirement 'parse_kv("a=1\\")->at(0).second == "1"'

$ clang++ -std=c++2c -D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_FAST kvc_test.cpp
error: static assertion expression is not an integral constant expression
.../c++/v1/string_view:417:12: note: subexpression not valid in a constant expression
  417 |     return _LIBCPP_ASSERT_VALID_ELEMENT_ACCESS(__pos < size(), "string_view[] index out of bounds"), __data_[__pos];
./kvc.hpp:19:22: note: in call to 's.operator[](4)'
```

In the first compile, Clang executed the out-of-bounds `s[4]` and read the `'\0'` at the end of the literal, so `second` was the two-character `"1\0"`, and the assertion failed merely because the value was wrong. At the core-language level this read wasn't out of bounds, since the array `"a=1\\"` really does have 5 elements; what was violated is the precondition `pos < size()` of `string_view::operator[]` ([[string.view.access#1]]). Whether library UB is diagnosed during constant evaluation is unspecified ([[expr.const.core#4]]), and Clang didn't diagnose it here. With hardening enabled, the precondition becomes a check inside the library, constant evaluation fails when it hits it, and the diagnostic points straight at `s[++i]`.

!!! pitfall "Compile-time tests only cover the arguments they run"
    What a `static_assert` proves is that, for these few inputs, on this execution path, there is no core-language UB. It doesn't check other inputs; an `if consteval` branch may take completely different code at run time; and operations such as `reinterpret_cast` and `memcpy` can't appear in constant evaluation at all. It is a set of unit tests that run early, not a proof.

### Compile-failure tests

The correctness of some interfaces lies in rejecting wrong usage: lengths in different units can't be added, and a `double` can't implicitly become `Meters`. Properties like these are checked with **compile-failure tests**: asserting that some expression doesn't compile. A concept plus a `requires` expression can do this:

```cpp run title="units.cpp" ok
#include <type_traits>

struct Meters  { double v; };
struct Seconds { double v; };

constexpr Meters operator+(Meters a, Meters b) { return {a.v + b.v}; }

template <class T, class U>
concept addable = requires(T a, U b) { a + b; };

static_assert(addable<Meters, Meters>);
static_assert(!addable<Meters, Seconds>);       // different units can't be added
static_assert(!addable<Meters, double>);        // nor can a bare double
static_assert(!std::is_convertible_v<double, Meters>);
static_assert((Meters{1} + Meters{2}).v == 3);

int main() {}
```

When substituting template arguments into a `requires` expression produces an invalid expression in the [[g:immediate-context|immediate context]], the `requires` expression's value is `false`, and the program doesn't become ill-formed ([[expr.prim.req#5]]). So `!addable<Meters, Seconds>` is a compile-failure test that itself compiles.

Two forms that look equivalent give different results:

<div class="compare" markdown="1">

```cpp ok
template <class T, class U>
concept addable =
  requires(T a, U b) { a + b; };

static_assert(!addable<Meters, Seconds>);
```

```cpp error
// not in a template: an error outright
static_assert(!requires(Meters m,
                        Seconds s) {
  m + s;
});
```

</div>

Note 1 in [[expr.prim.req#5]] explains the right-hand case: when a `requires` expression doesn't appear in the declaration of a templated entity, an invalid expression in it makes the program ill-formed. Clang reports `invalid operands to binary expression ('Meters' and 'Seconds')` for the right side. Only through template parameter substitution is the failure absorbed into `false`.

The second trap is the boundary of the immediate context. When the function under test has an `auto` return type, deciding whether a call is valid requires instantiating the function body first to deduce the return type, and errors in the function body aren't in the immediate context ([[dcl.spec.auto.general#15]], [[temp.deduct.general#8]]):

<div class="compare" markdown="1">

```cpp error
template <class T>
auto scale(Meters m, T k) {
  return Meters{m.v * k};
}
template <class T>
concept scalable = requires(
    Meters m, T k) { scale(m, k); };

static_assert(!scalable<const char*>);
// hard error: double * const char* in the body
```

```cpp ok
template <class T>
  requires requires(double d, T k) {
    d * k;
  }
Meters scale(Meters m, T k) {
  return Meters{m.v * k};
}
template <class T>
concept scalable = requires(
    Meters m, T k) { scale(m, k); };

static_assert(!scalable<const char*>);
```

</div>

On the left Clang reports `invalid operands to binary expression ('double' and 'const char *')`, with the note chain pointing to `in instantiation of function template specialization 'scale<const char *>'`. What compile-failure tests can test is only the constraints an interface spells out in its declaration. That is also exactly their value: if such a test can't be written, the interface hasn't put its requirements in its signature, and callers can only learn about them from error messages deep inside the function body (see [[topics/concepts]], [[toolchain/reading-compiler-errors]]).

When you need to check that some code really fails to compile somewhere outside constraints (for example, that a particular `static_assert` fires), concepts can't help; the only way is to invoke the compiler from a test script and expect a nonzero exit code.

## Sanitizers: making UB show up in tests

A **sanitizer** is a combination of compiler instrumentation and a runtime library: the compiler inserts checking code around every memory access, arithmetic operation or synchronization operation, the corresponding runtime library is linked in, and a report is printed when a violating operation runs. They are dynamic tools and only see paths that actually execute. A table of what each tool detects is in [[topics/undefined-behavior]]; the focus here is how to use them in tests and where each one's blind spots are.

### ASan: out-of-bounds accesses and use after free

**AddressSanitizer** (ASan, `-fsanitize=address`) places inaccessible redzones around every heap block, stack variable and global variable, marks memory inaccessible after it is freed, and consults a shadow table before every read and write.

Running the parser under it, with three inputs that each end in a backslash:

```cpp title="trail.cpp" ub
#include "kv.hpp"
#include <cstdio>
#include <string>
int main() {
  auto a = parse_kv(R"(a=1\)");                  // the literal is followed by '\0'
  std::printf("literal: %zu\n", a->at(0).second.size());
  std::string s = R"(a=1\)";
  auto b = parse_kv(s);                          // std::string is followed by '\0' too
  std::printf("string:  %zu\n", b->at(0).second.size());
  auto* p = new char[4]{'a', '=', '1', '\\'};    // exactly 4 bytes
  auto c = parse_kv({p, 4});
  std::printf("heap:    %zu\n", c->at(0).second.size());
  delete[] p;
}
```

```text
$ clang++ -std=c++2c -g -gdwarf-4 -fsanitize=address,undefined kv.cpp trail.cpp && ./a.out
literal: 2
string:  2
==47934==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x6020000000d4 ...
SUMMARY: AddressSanitizer: heap-buffer-overflow kv.cpp:10 in parse_kv(...)
```

The first two calls both executed UB, yet ASan reported nothing: both the string literal and the `std::string` buffer have a `'\0'` at the end, so `s[4]` read valid memory that just doesn't belong to this `string_view`. ASan only knows which bytes are accessible, not where a `string_view` ends. Only when the buffer ends exactly at 4 bytes does the read land in a redzone.

Inputs in unit tests are almost all literals and `std::string`s, so even with the whole test suite running under ASan, this bug wouldn't show up. Standard library hardening and fuzzing, below, attack the problem from two directions. How to read an ASan report part by part is covered in [[toolchain/debugging]].

!!! impl "Checks ASan leaves off by default on macOS"
    On our test machine, ASan by default doesn't do leak detection, doesn't detect stack-use-after-return, and doesn't detect `new[]`/`delete` mismatches. For tests you can set `ASAN_OPTIONS=detect_leaks=1:detect_stack_use_after_return=1:alloc_dealloc_mismatch=1` across the board. Examples of the three are in [[topics/ownership-and-smart-pointers]] and [[topics/dangling-references]].

### LSan: leaks

LeakSanitizer is linked in along with ASan; at process exit it scans all still-reachable memory and reports unreachable heap blocks. A leak isn't UB, but it is just as fatal in a long-running service. On macOS it must be enabled explicitly:

```text
$ clang++ -std=c++2c -g -gdwarf-4 -fsanitize=address leak.cpp -o leak
$ ./leak; echo $?
0
$ ASAN_OPTIONS=detect_leaks=1 ./leak; echo $?
==51030==ERROR: LeakSanitizer: detected memory leaks

Indirect leak of 40 byte(s) in 1 object(s) allocated from:
    #0 0x000104e1145c in _Znwm+0x6c (libclang_rt.asan_osx_dynamic.dylib:arm64+0x6545c)
    ...
SUMMARY: AddressSanitizer: 80 byte(s) leaked in 2 allocation(s).
1
```

`leak.cpp` is two nodes holding `shared_ptr`s to each other; the full analysis is in [[topics/ownership-and-smart-pointers]]. With the default settings the exit code is 0, and CI notices nothing.

### UBSan: core-language UB

**UndefinedBehaviorSanitizer** (UBSan, `-fsanitize=undefined`) inserts checks before operations that may have UB. `-fsanitize=undefined` is an umbrella for a group of checks; `-###` shows the list it expands to in Clang 23:

```text
$ clang++ -fsanitize=undefined -### -c x.cpp 2>&1 | tr ' ' '\n' | grep -- -fsanitize=
"-fsanitize=alignment,array-bounds,bool,builtin,enum,float-cast-overflow,function,
  integer-divide-by-zero,nonnull-attribute,null,pointer-overflow,return,
  returns-nonnull-attribute,shift-base,shift-exponent,signed-integer-overflow,
  unreachable,vla-bound"
```

They all correspond to operations the standard specifies as UB; for example, `signed-integer-overflow` corresponds to an arithmetic result that isn't representable ([[expr.pre#4]]). This list doesn't include `vptr` (accessing members with the wrong dynamic type), which must be written separately as `-fsanitize=vptr`; an example is in [[topics/casts]]. Checks such as `unsigned-integer-overflow` and `implicit-conversion` aren't included, because unsigned wraparound and implicit truncation are well-defined; they are in `-fsanitize=integer`, useful for finding logic errors but reporting a great deal in legitimate hashing and random-number code.

UBSan's default behavior is unfriendly to tests:

```cpp run title="hash.cpp" ub
#include <cstdio>
#include <string_view>

int hash(std::string_view s) {
  int h = 0;
  for (char c : s) h = h * 31 + c;   // signed overflow
  return h;
}

int main() {
  std::printf("%d\n", hash("ab"));
  std::printf("%d\n", hash("hello, world"));
}
```

```text
$ clang++ -std=c++2c -g -gdwarf-4 -fsanitize=undefined hash.cpp -o h && ./h; echo $?
3105
hash.cpp:6:26: runtime error: signed integer overflow: 99162322 * 31 cannot be represented in type 'int'
SUMMARY: UndefinedBehaviorSanitizer: undefined-behavior hash.cpp:6:26
-640608884
0
```

After the report the program keeps running, the exit code is 0, and the test shows as passed. Most UBSan checks are recoverable by default (the `-fsanitize-recover=` in the `-###` output lists them; only `return` and `unreachable` aren't there). Test builds should add `-fno-sanitize-recover=undefined`:

```text
$ clang++ -std=c++2c -g -gdwarf-4 -fsanitize=undefined -fno-sanitize-recover=undefined hash.cpp -o h && ./h; echo $?
3105
hash.cpp:6:26: runtime error: signed integer overflow: 99162322 * 31 cannot be represented in type 'int'
SUMMARY: UndefinedBehaviorSanitizer: undefined-behavior hash.cpp:6:26
134
```

The run-time option `UBSAN_OPTIONS=halt_on_error=1` gave the same result on our test machine (exit code 134) without recompiling, but it depends on the environment variable being passed correctly into the test process. Writing the behavior into the compile options is more reliable. Also, UBSan reports each source location only once, so fixing one may surface the next.

### TSan: data races

When two threads access the same memory location, at least one of the accesses is a write, at least one isn't atomic, and there is no happens-before relation between them, that is a [[g:data-race|data race]], and the behavior is undefined ([[intro.races#17]]). **ThreadSanitizer** (TSan, `-fsanitize=thread`) records the thread and a vector clock for every access, and reports when two accesses lack synchronization between them.

```cpp run title="race.cpp" ub
#include <cstdio>
#include <thread>

struct Stats {
  long parsed = 0;               // should be std::atomic<long>
  void on_parse() { ++parsed; }
};

int main() {
  Stats st;
  auto work = [&] { for (int i = 0; i < 1000; ++i) st.on_parse(); };
  std::thread t1(work), t2(work);
  t1.join(); t2.join();
  std::printf("%ld\n", st.parsed);
}
```

```text
$ clang++ -std=c++2c -O2 race.cpp && for i in 1 2 3 4 5; do ./a.out; done
2000
2000
2000
2000
2000
$ clang++ -std=c++2c -g -gdwarf-4 -O1 -fsanitize=thread race.cpp && ./a.out
==================
WARNING: ThreadSanitizer: data race (pid=50051)
  Write of size 8 at 0x00016bae2ac8 by thread T2:
    #0 Stats::on_parse() race.cpp:6 (race_tsan:arm64+0x1000008cc)
    #1 main::$_0::operator()() const race.cpp:11 (race_tsan:arm64+0x1000008cc)
    ...
  Previous write of size 8 at 0x00016bae2ac8 by thread T1:
    #0 Stats::on_parse() race.cpp:6 (race_tsan:arm64+0x1000008cc)
    ...
  Location is stack of main thread.
  ...
SUMMARY: ThreadSanitizer: data race race.cpp:6 in Stats::on_parse()
==================
2000
ThreadSanitizer: reported 1 warnings
```

Without TSan, all five runs print the correct 2000, and the test would pass. TSan doesn't rely on the race actually producing a wrong result; it reports whenever two accesses lack synchronization, so one run is enough. The process's exit code is nonzero when it reports (134 on our test machine). TSan can only check interleavings that execute, and can do nothing about code paths that never ran concurrently; the memory model itself is covered in [[topics/memory-model]].

### MSan: unavailable on our test machine

MemorySanitizer (`-fsanitize=memory`) tracks whether every bit is initialized, and reports branches and output that depend on uninitialized values. It supports only a few platforms such as Linux; Clang 23 on our test machine reports `unsupported option '-fsanitize=memory' for target 'arm64-apple-darwin25.5.0'`. It also requires all code (including the standard library) to be compiled with MSan instrumentation, otherwise it gives false positives, so it is usually run only in Linux CI with a specially built libc++.

On macOS there are two partial substitutes:

- Warnings in `-Wall` such as `-Wsometimes-uninitialized` find some uninitialized reads along paths.
- `-ftrivial-auto-var-init=pattern` makes uninitialized local variables start with a fixed byte pattern. On our test machine, a function missing an `else` branch returned garbage values that differed from run to run, such as `0xeca77660`, in a default build, and consistently returned `0xaaaaaaaa` with this option. It doesn't report errors, but it makes tests that depend on uninitialized values fail consistently rather than occasionally.

C++26 changed reading an uninitialized automatic variable from UB to erroneous behavior ([[basic.indet#2]], [[P2795R5]]), where the variable's initial bytes are an implementation-determined **erroneous value** ([[basic.indet#1]]). The `pattern` option is one such implementation choice. At the time of writing, Clang still treats such reads as UB by default; see [[topics/undefined-behavior]].

### Overhead

Below are results on our test machine for the same benchmark program (calling `parse_kv` 400 times on an input of 20,000 key-value pairs, about 500,000 bytes) under different builds, all with `-O2 -g`. The machine was running other jobs at the same time; each configuration was run 3 times, and the timings vary a lot, so they are only good for orders of magnitude:

| Build | Time (ms, 3 runs) | Relative to plain `-O2` | Max resident memory |
|---|---|---|---|
| Plain `-O2` | 355–516 | 1× | 10 MB |
| `-O0` (no sanitizer) | 3111–3193 | about 7× | 10 MB |
| libc++ hardening EXTENSIVE | 288–574 | about 1× | 10 MB |
| Coverage instrumentation | 427–604 | about 1.1× | 10 MB |
| UBSan | 743–1046 | about 2× | 12 MB |
| ASan | 1036–1448 | about 2.5× | 275 MB |
| ASan + UBSan | 1474–1854 | about 3.5× | 275 MB |
| TSan (single-threaded) | 7983–12173 | about 20–30× | 44 MB |

Some observations:

- ASan's memory overhead is far larger than its time overhead. Shadow memory, redzones, and putting freed memory in quarantine to delay reuse made resident memory grow more than twentyfold.
- This benchmark keeps allocating small strings, and TSan must record every access even in a single-threaded program, so its overhead is the largest.
- `-O0` is slower than any of the sanitizer builds at `-O2`. Compiling sanitizer builds with `-O1` or `-O2` is common practice: it is faster, and it runs tests under optimization close to that of the release (see below).

### Which can be combined

Results with Clang 23:

| Combination | Result |
|---|---|
| ASan + UBSan | OK |
| TSan + UBSan | OK |
| ASan + TSan | `'-fsanitize=address' not allowed with '-fsanitize=thread'` |
| ASan + TySan | `'-fsanitize=type' not allowed with '-fsanitize=address'` |
| fuzzer + ASan / UBSan / TSan | OK |
| MSan | Not supported on our test machine |

ASan, TSan and MSan each take over memory allocation and address-space layout, and their shadow memory mappings conflict, so each needs a build of its own. UBSan's checks are local and need no shadow memory, so it can go with any of them. The practical conclusion: one ASan+UBSan build and one TSan build, each running the full test suite.

## Standard library hardening: turning library UB into test failures

The earlier `parse_kv(R"(a=1\)")` violates the precondition of `string_view::operator[]`. C++26 marks preconditions like this as **hardened preconditions**: in a hardened implementation they are checked with a terminating semantic before the function is called, and a violation is a contract violation rather than UB ([[structure.specifications#3]] ¶3.5, [[intro.compliance.general#8]], [[P3471]]). libc++ selects the level of checking with `_LIBCPP_HARDENING_MODE`; what each level means is covered in [[topics/undefined-behavior]].

The same `trail.cpp`, without sanitizers, just changing the hardening level:

```text
$ clang++ -std=c++2c -g -D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_FAST kv.cpp trail.cpp && ./a.out; echo $?
133
$ clang++ -std=c++2c -g -D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_DEBUG kv.cpp trail.cpp && ./a.out; echo $?
string_view:417: libc++ Hardening assertion __pos < size() failed: string_view[] index out of bounds
134
```

The literal case ASan missed terminates the program on the very first call under hardening. The reason is that hardening checks `string_view`'s own bounds, whereas ASan checks the bounds of the underlying memory. The two complement each other: hardening only covers the standard library's interfaces and can do nothing about raw pointers or your own containers; ASan covers every memory access but can't see logical bounds.

The hardened precondition of `std::string::operator[]` is `pos <= size()` ([[string.access#1]]), allowing the trailing `'\0'` to be read; `string_view`'s is `pos < size()`. The standard adds a note at `string_view` specifically pointing out that the latter is stricter. A refactoring that changes a parameter from `const std::string&` to `std::string_view` can turn a previously valid `s[s.size()]` into UB, and hardening catches it in tests.

The overhead of hardening was not measurable in the benchmark above, so enabling the DEBUG level in all test builds is recommended, and the FAST level is worth considering for release builds. Hardening and sanitizers can be enabled together.

## Organizing builds in CI

How presets are written, and why `CMAKE_CXX_FLAGS` belongs in presets, is covered in [[toolchain/cmake]]. Only the test-related configurations are listed here:

```json title="CMakePresets.json (excerpt)"
{ "name": "asan-ubsan", "inherits": "base",
  "cacheVariables": { "CMAKE_CXX_FLAGS":
    "-fsanitize=address,undefined -fno-sanitize-recover=undefined -fno-omit-frame-pointer -gdwarf-4" } },
{ "name": "tsan", "inherits": "base",
  "cacheVariables": { "CMAKE_CXX_FLAGS": "-fsanitize=thread -gdwarf-4" } },
{ "name": "hardened-o2", "inherits": "base",
  "cacheVariables": { "CMAKE_BUILD_TYPE": "RelWithDebInfo", "CMAKE_CXX_FLAGS":
    "-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_DEBUG" } },
{ "name": "coverage", "inherits": "base",
  "cacheVariables": { "CMAKE_CXX_FLAGS":
    "-fprofile-instr-generate -fcoverage-mapping" } },
{ "name": "fuzz", "inherits": "base",
  "cacheVariables": { "KV_FUZZ": "ON", "CMAKE_CXX_FLAGS":
    "-fsanitize=fuzzer-no-link,address,undefined -gdwarf-4" } }
```

In the test presets, set `"environment": { "ASAN_OPTIONS": "detect_leaks=1" }` for the ASan build. On our test machine, with Homebrew Clang 23 specified in the `base` preset, these five presets were configured and built, and `ctest --preset asan-ubsan` passed.

| Configuration | What it catches | Suggested frequency |
|---|---|---|
| Debug + ASan + UBSan, non-recoverable | Memory errors, core-language UB, leaks | Every commit |
| TSan | Data races | Every commit (if there is multithreaded code) |
| `-O2` + libc++ hardening DEBUG | Library preconditions; UB that only shows up after optimization | Every commit |
| Coverage | Which code isn't tested | Every commit, or daily |
| Short fuzzing run (fixed count) | Malformed input | Every commit |
| Long fuzzing run | Deeper paths | Daily or continuously |
| Linux + MSan (if feasible) | Uninitialized reads | Daily |

Linking sanitizers into uninstrumented code doesn't mean the job is done. ASan's reports only cover instrumented code; out-of-bounds reads in a precompiled third-party library won't be found, and TSan may treat synchronization it can't see as missing and report false positives. Dependencies are best built from source with the same options as the project (see [[toolchain/dependencies]]).

## Fuzzing

**Fuzzing** has a program automatically generate large numbers of inputs to exercise the code under test. libFuzzer is LLVM's own coverage-guided fuzzing engine: the compiler inserts coverage counters with `-fsanitize=fuzzer`, and for each input it generates, the engine watches whether it reached new branches; if so, it keeps the input in the corpus as a starting point for later mutations. Combined with ASan and UBSan, UB triggered by any input becomes a crash.

Homebrew Clang 23 on our test machine comes with libFuzzer's runtime (`libclang_rt.fuzzer_osx.a`), so `-fsanitize=fuzzer` can be used directly. Xcode's Apple Clang 21 accepts the option, but linking reports that `libclang_rt.fuzzer_osx.a` can't be found.

### The target function

A **fuzz target** is a C function with a fixed signature, which the engine calls repeatedly:

```cpp title="kv_fuzz.cpp"
#include "kv.hpp"
#include <cstddef>
#include <cstdint>

extern "C" int LLVMFuzzerTestOneInput(const std::uint8_t* data,
                                      std::size_t size) {
  std::string_view s(reinterpret_cast<const char*>(data), size);
  (void)parse_kv(s);
  return 0;
}
```

`-fsanitize=fuzzer` also provides `main`. The engine puts each input in a heap block of exactly `size` bytes, which is just the condition ASan needs: going one byte past the end lands in a redzone.

```text
$ clang++ -std=c++2c -g -gdwarf-4 -O1 -fsanitize=fuzzer,address,undefined kv.cpp kv_fuzz.cpp -o kv_fuzz
$ mkdir corpus && ./kv_fuzz corpus
INFO: Seed: 2604735966
#2      INITED cov: 34 ft: 34 corp: 1/1b exec/s: 0 rss: 34Mb
#3      NEW    cov: 35 ft: 41 corp: 2/3b lim: 4 exec/s: 0 rss: 34Mb L: 2/2 MS: 1 CrossOver-
...
#124    NEW    cov: 86 ft: 124 corp: 5/13b lim: 4 exec/s: 0 rss: 38Mb L: 3/4 MS: 2 ChangeBinInt-InsertByte-
...
#1143   NEW    cov: 94 ft: 137 corp: 12/42b lim: 6 exec/s: 0 rss: 38Mb L: 6/6 MS: 1 CopyPart-
==38537==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x60200000a512 ...
READ of size 1 at 0x60200000a512 thread T0
    #0 ... in parse_kv(std::__1::basic_string_view<char, std::__1::char_traits<char>>) kv.cpp:10
    #1 ... in LLVMFuzzerTestOneInput kv_fuzz.cpp:8
    ...
0x60200000a512 is located 0 bytes after 2-byte region [0x60200000a510,0x60200000a512)
...
SUMMARY: AddressSanitizer: heap-buffer-overflow kv.cpp:10 in parse_kv(...)
0x87,0x5c,
artifact_prefix='./'; Test unit written to ./crash-e580f7707522eeeb678ce70c71887f8915079557
```

The `#N` at the start of each line is the number of inputs executed, and `cov` the number of edges covered. Starting from an empty corpus, the engine found a crash after a little over a thousand inputs: the two bytes `0x87 0x5c`, the second of which is a backslash. The crashing input was written to a `crash-` file. Running again with 5 other random seeds on our test machine found the same bug after 288 to 2853 executions, each in under a second; in 4 of them the crashing input was a single backslash `0x5c`.

### Reproduce, fix, prevent regression

Pass the crash file as an argument to the target program to execute just that one input:

```text
$ ./kv_fuzz crash-08534f33c201a45017b502e90a800f1b708ebcb3
Running: crash-08534f33c201a45017b502e90a800f1b708ebcb3
==47330==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x602000000191 ...
    #0 0x000100bc155c in parse_kv(...) kv.cpp:10
```

The fix is to check, when escaping, whether another character follows:

```cpp
if (c == '\\') {
  if (++i == s.size()) return std::nullopt;   // a lone trailing backslash
  cur->push_back(s[i]);
  continue;
}
```

After the fix, we let the engine run for 30 seconds on our test machine: about 2.68 million inputs (about 87,000 per second on average), with no further crashes, and the number of edges covered settled at 133.

Crashing inputs should be kept. One way is to add a unit test case (`CHECK(!parse_kv("\\"))`); another is to put the crash file in a corpus directory in the repository and, in CI, run `./kv_fuzz corpus_dir -runs=0` to replay the corpus only, without generating new inputs. Running this way on a directory containing just the one crash file reported heap-buffer-overflow immediately before the fix.

### Putting it into CTest

Long fuzzing runs don't suit every commit, but a smoke test with a fixed number of runs is cheap:

```cmake
option(KV_FUZZ "Build libFuzzer targets" OFF)
if(KV_FUZZ)
  add_executable(kv_fuzz tests/kv_fuzz.cpp)
  target_link_libraries(kv_fuzz PRIVATE kv)
  target_link_options(kv_fuzz PRIVATE -fsanitize=fuzzer)
  add_test(NAME kv_fuzz_smoke
           COMMAND kv_fuzz -runs=20000 -seed=1)
endif()
```

In the `fuzz` preset above, the compile options use `-fsanitize=fuzzer-no-link`: every target gets coverage counters, but only the fuzz target links libFuzzer's `main`, and ordinary unit tests keep their own `main`. Running `ctest --preset fuzz` before the fix on our test machine, the unit tests passed and `kv_fuzz_smoke` reported the same heap-buffer-overflow at 0.81 seconds and failed. Fixing `-seed` makes CI results reproducible.

!!! tip "A few tips for writing fuzz targets"
    - Targets should be fast, have no global state, and not depend on time or random numbers; otherwise crashes can't be reproduced.
    - Besides checking for crashes, a target can check properties, for example serializing the result again after a successful parse, parsing it again, and asserting the two results are the same with `__builtin_trap()`.
    - When the input format has structure, give some valid samples as the initial corpus, or supply a keyword dictionary with `-dict=`, so the engine reaches deep paths faster.

## Property-based testing

**Property-based testing** doesn't write specific inputs and expected outputs; it writes a property that should hold for all inputs, and has the program generate many random inputs to check it. It is close to fuzzing; the differences are that inputs are generated according to the structure of a type (here a list of key-value pairs, not a byte string) and that it checks semantic properties rather than just not crashing. In C++, libraries such as RapidCheck provide generators and automatic shrinking of failing cases; it wasn't installed on our test machine, and a minimal version can be written with the standard library's `<random>`.

The most natural property of a parser: serializing and then parsing gives back the original value.

```cpp title="prop.cpp" ok
#include "kv.hpp"
#include <cstdio>
#include <random>

std::string to_kv(const KV& kv) {
  std::string out;
  auto put = [&](const std::string& s) {
    for (char c : s) {
      if (c == ';' || c == '\\') out += '\\';
      out += c;
    }
  };
  for (std::size_t i = 0; i < kv.size(); ++i) {
    if (i) out += ';';
    put(kv[i].first); out += '='; put(kv[i].second);
  }
  return out;
}

std::string random_string(std::mt19937& g) {
  static constexpr char alphabet[] = "ab=;\\";   // biased toward special characters
  std::uniform_int_distribution<int> len(0, 4), ch(0, 4);
  std::string s(len(g), ' ');
  for (char& c : s) c = alphabet[ch(g)];
  return s;
}

int main() {
  std::string shortest;
  int failures = 0;
  std::mt19937 g(12345);                        // fixed seed: failures are reproducible
  for (int iter = 0; iter < 10000; ++iter) {
    KV kv(std::uniform_int_distribution<int>(0, 3)(g));
    for (auto& [k, v] : kv) { k = random_string(g); v = random_string(g); }
    std::string text = to_kv(kv);
    if (parse_kv(text) != kv) {                 // property: parsing inverts serialization
      if (shortest.empty() || text.size() < shortest.size()) shortest = text;
      ++failures;
    }
  }
  if (failures) {
    std::printf("%d of 10000 failed; shortest: %s\n", failures, shortest.c_str());
    return 1;
  }
  std::puts("10000 cases OK");
}
```

```text
$ clang++ -std=c++2c -g -gdwarf-4 -fsanitize=address,undefined kv.cpp prop.cpp && ./a.out
3847 of 10000 failed; shortest: ==
```

The shortest failing case is `==`: a pair whose key is `=` and whose value is empty. Serialization doesn't escape `=`, and the parser takes the first `=` as the separator, giving an empty key and a value of `=`. This bug is in `to_kv`; it isn't UB, and neither sanitizers nor fuzzing would report it. After escaping `=` in `put` as well, all 10,000 cases pass.

Recording the shortest failing case is the simplest way of shrinking. The alphabet deliberately contains only special characters; otherwise random strings would rarely hit the boundaries. The design of the generator decides what such tests can find.

## Coverage

Clang's source-based coverage has two steps: compile with `-fprofile-instr-generate -fcoverage-mapping`, and the program writes counts to a `.profraw` file when it runs; then merge with `llvm-profdata` and generate a report with `llvm-cov`.

```text
$ clang++ -std=c++2c -O0 -fprofile-instr-generate -fcoverage-mapping kv.cpp kv_test.cpp -o kv_cov
$ LLVM_PROFILE_FILE=kv.profraw ./kv_cov
$ llvm-profdata merge -sparse kv.profraw -o kv.profdata
$ llvm-cov report ./kv_cov -instr-profile=kv.profdata kv.cpp
Filename  Regions  Missed Regions   Cover  Functions ...  Lines  Missed Lines    Cover  Branches  Missed Branches   Cover
kv.cpp         25               1  96.00%          1 ...     23             0  100.00%        16                2  87.50%
```

`llvm-cov show` gives execution counts line by line, and `-show-branches=count` adds the true and false counts of each condition (excerpt):

```text
    9|     23|    if (c == '\\') {              // escape: keep the next character as is
  ------------------
  |  Branch (9:9): [True: 1, False: 22]
  ------------------
   10|      1|      cur->push_back(s[++i]);
   11|      1|      continue;
   12|      1|    }
   13|     22|    if (c == '=' && cur == &key) { cur = &val; continue; }
  ------------------
  |  Branch (13:9): [True: 4, False: 18]
  |  Branch (13:21): [True: 4, False: 0]
  ------------------
   ...
   23|      2|  else if (!key.empty()) return std::nullopt;
  ------------------
  |  Branch (23:12): [True: 0, False: 2]
  ------------------
```

Line coverage is 100%, the line with the out-of-bounds read executed once, and the bug still went unnoticed. Coverage answers which code executed, not with which values: line 10 only executed when the backslash was followed by another character. The two uncovered branches are useful hints, though: no test has a value containing `=` (`13:21` false), and none ends with a key and no `=` (`23:12` true).

So coverage is good for finding untested code, not for proving tests are sufficient. 100% coverage plus sanitizers still needs boundary values, fuzzing and property tests to cover the input space. Coverage instrumentation has low run-time overhead (about 1.1× in the table above) and can be kept separate from sanitizers as its own CI configuration.

## The same tests at -O0 and -O2

Running tests only at `-O0` misses a class of errors: code relying on UB happens to behave like the hardware without optimization, and after optimization the compiler exploits the UB to rewrite it.

```cpp run title="sat.cpp" ub
#include <climits>
#include <cstdio>

int sat_add(int a, int b) {
  int r = a + b;                 // compute first, then check for wraparound
  if (b > 0 && r < a) return INT_MAX;
  if (b < 0 && r > a) return INT_MIN;
  return r;
}

int main() {
  bool ok = sat_add(INT_MAX, 1) == INT_MAX
         && sat_add(INT_MIN, -1) == INT_MIN;
  std::puts(ok ? "PASS" : "FAIL");
}
```

| Build | Output |
|---|---|
| `-O0` | PASS |
| `-O1`, `-O2` | FAIL |
| `-O0 -fsanitize=undefined` | Reports `signed integer overflow: 2147483647 + 1`, then PASS |
| `-O2 -fsanitize=undefined` | Reports the same overflow, then PASS |

Overflow in `a + b` is UB ([[expr.pre#4]]), so the compiler may assume it doesn't happen; under that assumption `b > 0 && a + b < a` is always false. On our test machine, `-O2` compiles the whole function to a single `add w0, w1, w0`, with both checks gone.

The last two rows show something else: with UBSan instrumentation, the test passes again at `-O2`, because the checking code prevented this optimization. A sanitizer build and a release build are two different programs. So CI needs a configuration without sanitizers, with only optimization and hardening, which is closest to the program actually released.

The correct approach is not to let the overflow happen: C++26's `std::saturating_add` ([[numeric.sat]], [[P0543R3]]) is already provided by libc++ on our test machine; alternatively, use the compiler builtin `__builtin_add_overflow`, which `-O2` compiles to an `adds` that sets the overflow flag plus one `csel` on our test machine. More arithmetic traps are covered in [[topics/arithmetic]].

## Questions

!!! question "Question 1"
    All of a project's unit tests pass under an ASan+UBSan build, with 100% coverage. Does that show there are no out-of-bounds reads in the program?

<details markdown="1">
<summary>Answer</summary>

No. `parse_kv` on this page is a counterexample: the line with the out-of-bounds read was executed, but the tests' inputs were all literals or `std::string`s, so the out-of-bounds read hit the `'\0'` at the end of the buffer, which ASan considers accessible memory. What is violated is the precondition `pos < size()` of `string_view::operator[]` ([[string.view.access#1]]), which is library UB that only standard library hardening can check. Coverage only says code executed, not with which values.
</details>

!!! question "Question 2"
    Why does the compile-failure test below itself fail to compile? How should it be changed?

    ```cpp
    struct Celsius { double v; };
    static_assert(!requires(Celsius c) { c * 2.0; });
    ```

<details markdown="1">
<summary>Answer</summary>

The `requires` expression isn't in the declaration of a templated entity, so an invalid expression in it makes the program ill-formed outright (note 1 in [[expr.prim.req#5]]). Only through template parameter substitution is a substitution failure absorbed into `false`. The fix is to define a concept first, for example `template <class T> concept scalable_by_double = requires(T t) { t * 2.0; };`, then write `static_assert(!scalable_by_double<Celsius>);`.
</details>

!!! question "Question 3"
    CI already has an ASan+UBSan build. Why also run a separate TSan build, and an `-O2` build without sanitizers?

<details markdown="1">
<summary>Answer</summary>

ASan and TSan can't be linked into the same program, and data races ([[intro.races#17]]) can only be detected by TSan, so TSan needs its own build. The `-O2` build without sanitizers is needed because instrumentation changes optimization: `sat_add` on this page fails its test at `-O2`, while the `-O2` build with UBSan passes. What is released is the program without sanitizers, and testing needs to cover it too.
</details>

## Summary

| Technique | Finds | Blind spots |
|---|---|---|
| Unit tests | Wrong results for given inputs | When UB makes a wrong program give right results |
| `static_assert` + `constexpr` | Core-language UB on the tested paths (at compile time) | Other inputs; library UB isn't guaranteed to be diagnosed |
| Concepts + `requires` | Usage the interface should reject | Errors in function bodies, outside the immediate context |
| ASan (+LSan) | Out-of-bounds accesses, use after free, leaks (macOS needs `detect_leaks=1`) | Logical overruns that stay within valid memory |
| UBSan | Overflow, shifts, null pointers, misalignment, etc. | Recoverable by default; needs `-fno-sanitize-recover` |
| TSan | Data races | Can't be used with ASan; only sees interleavings that execute |
| MSan | Uninitialized reads | Not supported on macOS |
| libc++ hardening | Standard library preconditions | Raw pointers and custom containers |
| libFuzzer | Crashes and UB caused by malformed input | Needs a target that can be called quickly and repeatedly |
| Property tests | Semantic errors (such as non-invertible serialization) | Inputs the generator never produces |
| Coverage | Code that never executed | Code executed without covering the values |
| `-O2` without sanitizers | UB that only shows up after optimization | Doesn't report the cause, only shows up as wrong results |
