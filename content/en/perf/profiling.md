---
title: Finding hot spots with a profiler
summary: "Find out where the time goes before optimizing: sampling vs instrumentation, building for profiling (-O2 -g, frame pointers, why -O0 profiles can't be trusted), sample, Instruments and dtrace on macOS, perf on Linux, reading call trees, flame graphs and inlined frames, what hardware counters add, and checking the gain with Amdahl's law after fixing a hot spot."
tags: performance, profiling, profiler, sample, perf, Instruments, flame graph, Amdahl's law
updated: 2026-10-19
group: Measurement
---

!!! tldr
    - A profiler answers where the time goes. A sampling profiler records the call stack at fixed intervals, with low overhead, and its results are statistical estimates; instrumentation inserts code at function entry and exit, giving exact counts, but changes the program being measured.
    - Profile a build close to the release build: `-O2` plus debug information. An `-O0` program has no inlining, and the top of its profile is a crowd of small functions that do not exist at all under `-O2`.
    - In a word-frequency program on our test machine, the suspected memory allocation barely appeared; 66% of samples landed on `std::map` lookups, more than half of them in `memcmp` comparing strings.
    - The profile gives each part's share p, and Amdahl's law gives the upper bound: even if that part took no time, the whole would be at most 1/(1−p) times faster. Measure again after the change; the next hot spot is usually somewhere else.
    - Hardware counters tell you whether a piece of code is slow because of cache misses or branch mispredictions. On macOS they are read through Instruments; on Linux, use `perf stat`.

All numbers in this section come from an Apple M2 Pro, macOS 26.5, Homebrew Clang 23.1.3 + libc++, arm64. This machine was heavily loaded while this was written (load average between 30 and 100 on 12 cores), so absolute times are slow and scattered. The text relies more on percentages in profiles and on ratios measured back to back in the same process; on another machine or with another compiler the numbers will change. Measurement methods are in [[perf/measuring]].

## A surprisingly slow program

The program below generates a text of 5 million words, counts how often each word appears, and prints the five most frequent. Each phase is wrapped in a timer object that prints the elapsed time when destroyed.

```cpp title="wordfreq.cpp" run ok
// wordfreq.cpp: count word frequencies, print the 5 most frequent words
#include <algorithm>
#include <cctype>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <map>
#include <sstream>
#include <string>
#include <vector>

struct ScopedTimer {                 // prints the elapsed time when destroyed
  const char* name;
  std::chrono::steady_clock::time_point t0 =
      std::chrono::steady_clock::now();
  ~ScopedTimer() {
    std::chrono::duration<double, std::milli> d =
        std::chrono::steady_clock::now() - t0;
    std::fprintf(stderr, "%-7s %8.1f ms\n", name, d.count());
  }
};

// synthetic text of about n words: a 50,000-word vocabulary, a few words very frequent
std::string make_corpus(std::size_t n) {
  std::vector<std::string> vocab;
  for (int i = 0; i < 50000; ++i)
    vocab.push_back("Word" + std::to_string(i * 7919 % 100003));
  std::string text;
  std::uint64_t s = 42;
  for (std::size_t i = 0; i < n; ++i) {
    s = s * 6364136223846793005u + 1442695040888963407u;
    double u = double(s >> 11) / double(1ull << 53);  // [0, 1)
    text += vocab[std::size_t(u * u * u * vocab.size())];
    text += (i % 12 == 11) ? ".\n" : " ";
  }
  return text;
}

using Counts = std::map<std::string, int>;

Counts count_words(const std::string& text) {
  Counts counts;
  std::istringstream in(text);
  std::string w;
  while (in >> w) {
    std::string clean;
    for (char c : w)
      if (std::isalnum(static_cast<unsigned char>(c)))
        clean += char(std::tolower(static_cast<unsigned char>(c)));
    if (!clean.empty()) ++counts[clean];
  }
  return counts;
}

int main() {
  std::string text;
  Counts counts;
  std::vector<std::pair<std::string, int>> top;
  { ScopedTimer t{"corpus"}; text = make_corpus(5'000'000); }
  { ScopedTimer t{"count"};  counts = count_words(text); }
  {
    ScopedTimer t{"top5"};
    top.assign(counts.begin(), counts.end());
    std::partial_sort(top.begin(), top.begin() + 5, top.end(),
        [](auto& a, auto& b) { return a.second > b.second; });
  }
  for (int i = 0; i < 5; ++i)
    std::printf("%-10s %d\n", top[i].first.c_str(), top[i].second);
}
```

Build with `clang++ -std=c++2c -O2 -gdwarf-4 -fno-omit-frame-pointer wordfreq.cpp -o wordfreq` (the next section explains these options). Over several runs on our test machine, `corpus` took 70 to 110 ms, `count` 1.0 to 1.7 s, and `top5` only 1 to 3 ms. Nearly all the time is in `count_words`.

Three things in this function could be slow: reading word by word through `istringstream`, creating a new `std::string clean` for every word, and `std::map` lookup. The common intuition is that every word allocates memory, so allocation must be the most expensive. That guess is wrong; the profiler's answer follows below.

## Sampling and instrumentation

A **profiler** measures how a program's time is distributed across functions and source lines. There are two basic approaches.

**Sampling** interrupts the program at fixed intervals (say 1 ms), records the current call stack, and in the end counts how many samples each function and line appears in. A function in 30% of the samples is estimated to take 30% of the time. The program itself needs no changes, and overhead is usually a few percent. The price is that results are statistical estimates: for a part with share p among n samples, the standard error is about √(p(1−p)/n). With 1700 samples and p = 0.66 that is about 1.1 percentage points. A very short function that is called only occasionally might not get a single sample.

**Instrumentation** inserts timing or counting code at function entry and exit (or at code regions you choose). It gives exact call counts and misses no short functions. The price is that the inserted code takes time itself; the smaller and more frequently called the measured function, the less what you measure resembles the original program. The `ScopedTimer` above is hand-written instrumentation.

| | Sampling | Instrumentation |
|---|---|---|
| Program changes needed? | No, only debug information | Recompilation or code changes |
| Overhead | Small, depends on sample rate | Proportional to how often instrumentation points execute |
| Results | Estimates of time share | Exact counts and interval times |
| Good for | First step: where did the time go | Confirming the time of a section, counting calls |
| Tools on our test machine | `sample`, Instruments Time Profiler | Timers, `-finstrument-functions` |

Typically, use sampling first to find the rough location, then add timers there to confirm.

## Building for profiling

What a profile should measure is the machine code that will actually run, so the optimization level should match the release build, usually `-O2`. Two kinds of information also need to be added so the profiler can translate addresses back to source code.

### Debug information: `-g`

`-g` makes the compiler generate debug information (DWARF), recording the source file and line of each instruction, and which instructions were inlined from which function. It does not change the generated code; it only adds data alongside the executable. Without it, the profiler can report only function names (from the symbol table), not line numbers.

We hit a specific problem on our test machine. Homebrew Clang 23 generates DWARF 5 by default, which the system linker ld64-530 cannot read; linking prints `ld: warning: can't parse dwarf compilation unit info`, and afterwards `sample`'s output has no line numbers. With `-gdwarf-4` the line numbers are fine. This is caused by a toolchain version mismatch on our test machine and has nothing to do with C++.

### Frame pointers

When sampling, the profiler has to walk back up the call stack to find who called the current function. The simplest way relies on the **frame pointer**: each function's prologue saves the caller's frame pointer in its own stack frame, so the frames form a linked list. The compiler may skip this to free up a register.

```cpp title="fp.cpp"
void g(int);
void f(int x) { g(x); g(x + 1); }
```

Compiling these two lines with `-O2 -S` for three targets on our test machine:

| Target | Default | `-fno-omit-frame-pointer` |
|---|---|---|
| arm64 macOS | Builds the frame chain (`stp x29, x30` then `add x29, sp, #16`) | Same |
| aarch64 Linux (`--target=aarch64-linux-gnu`) | Builds the frame chain (`mov x29, sp`) | Same |
| x86-64 Linux (`--target=x86_64-linux-gnu`) | No `%rbp` | `pushq %rbp` then `movq %rsp, %rbp` |

Apple's arm64 ABI requires the frame pointer to be kept, so on our test machine this option doesn't change the code; it is added only to keep the build command portable. On x86-64 Linux, `-O2` omits the frame pointer by default, and when profiling with `perf` you either add `-fno-omit-frame-pointer` or switch to DWARF-based stack unwinding (see the `perf` section below). Whether system libraries keep frame pointers is up to the distribution; if the stack breaks inside a library, the call tree will be missing levels.

### Why `-O0` profiles can't be trusted

Compiling the same program at `-O0` and sampling, counting by source line, the `++counts[clean]` line takes 64%, about the same as at `-O2`. Counting by function looks completely different:

| Sorted by self time per function | `-O2` | `-O0` |
|---|---|---|
| First place | `_platform_memcmp`, about 47% | `std::basic_string::__get_pointer()`, about 14% |
| Share of `memcmp` | about 47% | about 5% |
| Functions with at least 5 samples | 13 | 78 |

`-O0` does no inlining, so every accessor of `std::string`, every layer of comparator adaptor in `std::map`, and every character fetch from `streambuf` is a real function call, each getting its own share of samples. Under `-O2`, `__get_pointer()` is inlined into one or two instructions and is not a function at all. Optimizing `__get_pointer` based on the `-O0` results would have no effect in a release build. The `-O0` program itself is also more than an order of magnitude slower (the `count` phase took 15 to 26 s under heavy load on our test machine, versus 1 to 2 s for `-O2` in the same period), and different parts slow down by different factors, so the shares can't be trusted either.

[[intro.abstract#1]] says an implementation only needs to emulate the abstract machine's [[g:observable-behavior]], not mirror its structure. This is usually called the [[g:as-if-rule]], and it lets the compiler collapse a dozen layers of function calls into one loop. The profiler sees the compiled machine code, so only profiling the machine code you will actually ship is meaningful. Inlining details are in [[perf/compiler-optimizations]].

## Sampling on macOS

### `sample`

`sample` is the command-line sampler that ships with macOS; it can attach to a running process without root. Below, the program runs in the background, and after 0.3 seconds (once the text has been generated) sampling starts for 2 seconds, once every 1 ms:

```text
$ ./wordfreq > /dev/null & sleep 0.3; sample $! 2 1 -mayDie -file s.txt
```

`-mayDie` makes `sample` read the symbol information up front in case the process exits early. The output has two parts. The first is the **call tree**. Below is an excerpt from one run on our test machine, with template names abbreviated and addresses removed:

```text
Call graph:
  1703 main  (in wordfreq) + 212  wordfreq.cpp:60
    1118 count_words(...)  (in wordfreq) + 420  wordfreq.cpp:50
    + 827 __tree<...>::__emplace_unique<...>::'lambda'  __tree:1079
    + ! 800 _platform_memcmp  (in libsystem_platform.dylib)
    + ! 27 DYLD-STUB$$memcmp  (in wordfreq)
    + 289 __tree<...>::__emplace_unique<...>::'lambda'  __tree:1079
    375 count_words(...)  (in wordfreq) + 224  wordfreq.cpp:45
    + 91 std::operator>><char>(basic_istream&, basic_string&)  istream:...
    ...
```

The number at the start of each line is the number of samples in this stack frame and below it. The same function appears on different lines for different return addresses, so `count_words` shows up several times, and the line number says which call in the function it is. Line 50, `++counts[clean]`, has 1118 of the 1703 samples (66%); line 45, `in >> w`, has 375 (22%); the per-character cleaning on lines 48 and 49 totals about 7%.

The second part is sorted by **self time**, that is, samples landing on the function's own instructions rather than in functions it calls:

```text
Sort by top of stack, same collapsed (when >= 5):
    _platform_memcmp  (in libsystem_platform.dylib)          800
    __tree<...>::__emplace_unique<...>::'lambda'  (in wordfreq)  292
    std::operator>><char>(basic_istream&, basic_string&)     243
    std::basic_string<char>::push_back(char)  (in libc++.1.dylib)  119
    count_words(...)  (in wordfreq)                          76
    std::basic_istream<char>::sentry::sentry(...)  (in libc++.1.dylib)  62
    ...
```

The conclusion is clear: `std::map` lookup takes the lion's share, and more than half of that is `memcmp` comparing two strings. Each word is at most 9 characters, less than the 22-character capacity of SSO in libc++ (the short string optimization, which stores short strings directly inside the `std::string` object), so `std::string clean` does not allocate, and `malloc` does not appear in the list at all. A lookup in a balanced tree of 50,000 keys makes about 16 comparisons, each one a library call to `memcmp`, plus a read of a tree node that may not be in cache.

`DYLD-STUB$$memcmp` is trampoline code passed through when calling a dynamic library function: the `bl` in the executable first jumps to this stub, which then jumps to the real `memcmp` in `libsystem_platform.dylib`. Dynamic linking details are in [[toolchain/linking-and-symbols]].

`sample` records each thread's call stack at that moment, so threads blocked in system calls or waiting for I/O or locks are counted too. This program is single-threaded and purely computational, so there is no difference.

### Instruments and `xctrace`

Instruments is the graphical profiler that comes with Xcode. Its Time Profiler template samples only while a thread is actually on the CPU, can filter by thread and time range, and shows the call tree as an expandable table. The command-line version is `xctrace`:

```text
$ xctrace record --template 'Time Profiler' --output wf.trace --launch -- ./wordfreq
```

The resulting `.trace` file is opened in Instruments. Our test machine has xctrace 16.0, which fails to load Instruments' device plugins on macOS 26.5, printing `Failed to look up symbolic reference ... is likely a reference to a missing weak symbol` and producing no readable trace. It appears to be a mismatch between the Xcode version and the OS, so this page has no Instruments output.

### dtrace

dtrace can be scripted to sample on arbitrary events; for example, `dtrace -n 'profile-997 /pid == $target/ { @[ustack()] = count(); }' -c ./wordfreq` samples the process 997 times a second and counts by user-space call stack. Our test machine has System Integrity Protection (SIP) enabled, and running it as an ordinary user reports `DTrace requires additional privileges`; it needs root, and some features remain unavailable under SIP. For everyday profiling, `sample` or Instruments is enough.

## On Linux: perf

The standard tool on Linux is `perf`, which reads the kernel's and CPU's performance counters directly. Our test machine runs macOS, so the commands below were not run here; we only describe what each does:

- `perf record -g ./wordfreq` samples on the CPU clock, and `-g` also records call stacks (unwinding via frame pointers). When the program has no frame pointers, use `perf record --call-graph dwarf` instead, which copies a chunk of stack memory into every sample and unwinds afterwards using DWARF debug information, at a much larger data volume.
- `perf report` reads the generated `perf.data` and interactively shows a table sorted by function. The default Children column is total time including called functions, the Self column is self time, and `--no-children` sorts by self time only.
- `perf annotate` maps samples onto individual assembly instructions, showing which instructions inside a function are hottest.
- `perf stat ./wordfreq` records no call stacks and only counts totals over the whole run; see the hardware counters section below.

## Reading call trees and flame graphs

### Total time and self time

Each node in the call tree has two numbers. **Total time** (or inclusive) counts samples in this function and in all functions it calls directly or indirectly; **self time** (or exclusive) counts only samples that stopped exactly on this function's own instructions. `main`'s total time is close to 100%, and its self time is almost 0.

Finding hot spots usually starts from total time and works downward: start at `main`, expand the child with the largest total time each time, until a node's total time consists mainly of self time, or is spread across many children. In the example above, the path is `main` → `count_words` line 50 → `__emplace_unique` → `memcmp`. Looking only at the self-time ranking is misleading: `memcmp` is first, but what should change is not `memcmp` but the line that calls it about 80 million times (5 million lookups, about 16 comparisons each).

### Flame graphs

A **flame graph** draws the same call tree as a picture: each stack frame is a horizontal bar whose width is proportional to its total time, with callees stacked on top of callers. The left-to-right order is usually by function name, not by time. Wide, flat tops are functions with large self time.

Drawing a flame graph first requires folding the samples into a format of one complete call stack plus a count per line, such as `main;count_words;__emplace_unique;memcmp 800`, which is then handed to a drawing tool. Brendan Gregg's FlameGraph scripts and tools like speedscope accept the output of `perf script`. It expresses the same data as the call tree; the only difference is that the overall shape is visible at a glance.

### Inlined frames

`sample` reports samples landing in a lambda inside `__emplace_unique`, but no such lambda was written in the source; the lookup and comparison code have all been inlined into it. The machine code has only one function, but the debug information records which level of inlined function each instruction came from. `atos -i` can expand these levels. Taking the address of the instruction that calls `memcmp`:

```text
$ atos -o wordfreq.dSYM/Contents/Resources/DWARF/wordfreq -l 0x1023cc000 -i 0x1023d2c2c
```

`-l` is the Load Address from the header of `sample`'s output. The result is 9 stack frames at the same address, from innermost to outermost (names abbreviated):

```text
std::char_traits<char>::compare                   char_traits.h:126
std::basic_string_view<char>::compare             string_view:483
std::operator<=>(basic_string_view, basic_string_view)   string_view:772
std::operator<=>(const string&, const string&)    string:3538
std::__default_three_way_comparator<string, string>      default_three_way_comparator.h:51
std::__lazy_synth_three_way_comparator<less<void>, ...>  lazy_synth_three_way_comparator.h:99
std::__lazy_synth_three_way_comparator<__map_value_compare<...>, ...>  map:708
std::__tree<...>::__find_equal<string>            __tree:1960
std::__tree<...>::__emplace_unique<...>::'lambda'  __tree:1079
```

At run time these 9 levels are just one `bl memcmp` and a few instructions around it. On Linux, `perf report --inline` and `llvm-symbolizer --inlining` do the same thing. Once expanded, the profile can be read according to the structure of the source, keeping in mind that these levels have no call overhead.

Conversely, some functions that look like they should be inlined are not. In the profile, `std::basic_string<char>::push_back(char)` carries `(in libc++.1.dylib)`, preceded by `DYLD-STUB$$`, meaning each `clean += c` is a function call across a dynamic library; the `bl` to `push_back` is also visible in the `-O2 -S` assembly. The reason is that libc++ uses an explicit instantiation declaration (`extern template`, [[temp.explicit#2]]) to instantiate a batch of `basic_string<char>` member functions in the shared library, and `push_back` is on the list. Per the note in [[temp.explicit#12]], such declarations have no other normative effect on inline functions, and whether to inline is entirely up to the compiler; this build on our test machine did not inline it.

## Hardware counters

Sampling tells you which line the time goes to, but not why it is slow. Of the 800 samples in `memcmp`, how many were comparing bytes, and how many were waiting for tree nodes to be read from memory? A sampling profiler can't tell them apart, because time spent waiting on a cache miss is charged to the instruction that issued the load.

CPUs contain **performance monitoring counters** that can count events such as cycles executed, instructions retired, cache misses at each level, and branch mispredictions. Two commonly used derived metrics are IPC (instructions per cycle) and cache misses per thousand instructions. Low IPC with many cache misses means the bottleneck is memory access and the data layout should change (see [[perf/memory-hierarchy]]); many branch mispredictions, see [[perf/branches]].

On Linux, `perf stat -e cycles,instructions,cache-misses,branch-misses ./wordfreq` gives these counts directly, and `perf record -e cache-misses` can even sample on miss events to find roughly which line the misses happen on. Available event names depend on the CPU model; `perf list` lists them.

On macOS, there is no command-line tool for ordinary users to read these counters. Instruments has a CPU Counters template (`xctrace list templates` lists it) for reading Apple silicon's counters. Instruments would not run on our test machine (see above), so this page gives no cache-miss data, and how much of the time in `memcmp` is spent waiting for memory remains an open question here.

## Instrumentation

### Scoped timers

`ScopedTimer` relies on destructors running automatically at the end of a scope (see [[patterns/raii|RAII]]), measuring a block's time with two calls to `steady_clock::now()`. [[time.clock.steady#1]] specifies that this clock's values never decrease as physical time advances and that it advances at a steady rate relative to real time, so it is unaffected by adjustments to the system time. Its overhead is two clock reads, over ten nanoseconds each on our test machine: negligible around a millisecond-scale section, but dominant inside a loop body that runs for only tens of nanoseconds. Clock precision and overhead are covered in [[perf/measuring]].

### `-finstrument-functions`

GCC and Clang's `-finstrument-functions` inserts calls to `__cyg_profile_func_enter` and `__cyg_profile_func_exit` at the entry and exit of every function, and you supply these two functions. The version below only counts:

```cpp title="hooks.cpp" ok
// hooks.cpp: callbacks for -finstrument-functions, counting calls only
#include <cstdio>
static unsigned long long calls = 0;
extern "C" {
__attribute__((no_instrument_function))
void __cyg_profile_func_enter(void*, void*) { ++calls; }
__attribute__((no_instrument_function))
void __cyg_profile_func_exit(void*, void*) {}
}
struct Report {
  __attribute__((no_instrument_function))
  ~Report() { std::fprintf(stderr, "instrumented calls: %llu\n", calls); }
} report;
```

`no_instrument_function` keeps the callbacks themselves from being instrumented, which would otherwise recurse infinitely. Compiling `hooks.cpp` without the instrumentation option and linking it with the instrumented `wordfreq.cpp`, one run under heavy load on our test machine gave:

| Build | Instrumented calls | `count` phase |
|---|---|---|
| Not instrumented (same period) | 0 | about 2.3 s |
| `-finstrument-functions` | 6 190 878 981 | 25.7 s |
| `-finstrument-functions-after-inlining` | 10 100 061 | 2.5 s |

Clang's `-finstrument-functions` instruments before inlining, so every small function in `std::string` and `std::map` that should have been inlined away gains two extra calls; the program becomes more than ten times slower, and what is being measured is a different program. `-finstrument-functions-after-inlining` instruments only functions that still exist after inlining, with 600 times fewer calls and much lower overhead. Even so, function-level instrumentation is only good for counting calls and call tracing, not for measuring time shares; that is sampling's job.

## Fix the hot spot, then measure again

### Amdahl's law

If the part of a program that takes fraction p of the time is sped up by a factor of s, and the rest is unchanged, the overall speedup is

S = 1 / ((1 − p) + p / s)

This is **Amdahl's law**. As s goes to infinity, the upper bound of S is 1 / (1 − p). The profile is what gives you p. `std::map` lookup takes 66% of `count_words`; even if lookup took no time at all, `count_words` would be at most 1 / 0.34 ≈ 2.9 times faster. The cleaning on line 49 takes only about 4%; optimizing it to zero gives at most 4%.

### Step one: replace `std::map`

Word counting does not need keys sorted, so changing `std::map` to `std::unordered_map` only requires changing the definition of `Counts`. A hash table lookup computes one hash and usually needs only one or two string comparisons, not a dozen or more.

To reduce noise, the numbers below come from another `main` for the same source: generate the text once, then run `count_words` 11 times in a row in the same process, taking the median and minimum. The result is checked (the number of keys must be 50000), so the as-if rule cannot delete the calls. The three versions were run alternately for six rounds; the minimums measured under lighter load were:

| Version | `count_words` minimum | Relative to v1 |
|---|---|---|
| v1: `std::map` + `istringstream` | 1065 ms | 1.00 |
| v2: `std::unordered_map` + `istringstream` | 596 ms | 1.79x |
| v3: `std::unordered_map` + hand-written tokenizer + `reserve` | 353 ms | 3.0x |

In the heavily loaded rounds all three slowed down, with v1's median reaching 4.2 s in the slowest round. By each round's minimum, the order v1 > v2 > v3 always held; by median, v2 was slower than v1 in one round, which is noise caused by load. Three more alternating rounds afterwards gave medians of 1090–1221, 605–744 and 366–395 ms respectively, with ratios consistent with the table. In an environment like this, differences under ten-odd percent are meaningless.

Checking v2 with Amdahl's law: the part of 1065 ms that is not lookup is about 0.34 × 1065 ≈ 362 ms. v2 measured 596 ms, meaning lookup dropped from about 703 ms to about 234 ms, about 3 times faster. Sampling v2, the lookup line takes 32%, about 190 ms of 596 ms, which roughly agrees with this estimate.

### Step two: the next hot spot

Fix one hot spot and the shares are redistributed. In v2's profile, first place went to the `in >> w` line at 45%; hash table lookup dropped to 32%; per-character cleaning took about 18%. `operator>>` constructs a `sentry` object for every word read, checking stream state, fetching the `ctype` facet from the locale and skipping whitespace; these fixed costs are too heavy for 9-byte words.

<div class="compare" markdown="1">

```cpp title="v1"
// using Counts = std::map<std::string, int>;
Counts count_words(const std::string& text) {
  Counts counts;
  std::istringstream in(text);
  std::string w;
  while (in >> w) {
    std::string clean;
    for (char c : w)
      if (std::isalnum(
            static_cast<unsigned char>(c)))
        clean += char(std::tolower(
            static_cast<unsigned char>(c)));
    if (!clean.empty()) ++counts[clean];
  }
  return counts;
}
```

```cpp title="v3"
// using Counts =
//   std::unordered_map<std::string, int>;
bool space(char c) {
  return std::isspace(
      static_cast<unsigned char>(c));
}
Counts count_words(const std::string& text) {
  Counts counts;
  counts.reserve(1 << 16);
  std::string clean;
  std::size_t i = 0, n = text.size();
  while (i < n) {
    while (i < n && space(text[i])) ++i;
    clean.clear();
    for (; i < n && !space(text[i]); ++i) {
      unsigned char c = text[i];
      if (std::isalnum(c))
        clean += char(std::tolower(c));
    }
    if (!clean.empty()) ++counts[clean];
  }
  return counts;
}
```

</div>

v3 tokenizes by scanning the original string directly, builds `clean` only once outside the loop, uses `clear()` to keep the existing capacity, and uses `reserve` to preallocate buckets, avoiding rehashing during insertion. v3 changes two things at once; strictly, you should change one thing at a time and measure each separately. Here the tokenizing line took 45% in v2, giving an Amdahl upper bound of about 1.8x, and the measured 596 → 353 ms is 1.69x, so most of the gain comes from tokenizing.

v3's profile: hash table lookup takes 51%, and the `clean += char(std::tolower(c))` line 28%, mostly function calls to `push_back` in libc++ and `tolower` in libc (see the inlined frames section above). Optimizing further means changing the data structure or avoiding character-by-character appends, which belongs to the [[perf/choosing-containers]] and [[perf/allocation]] pages.

### How much faster is the whole program?

`count_words` got 3 times faster, but the whole program did not. The text generation phase of 70 to 110 ms did not change; taking it as 80 ms, the total dropped from about 1145 ms to about 433 ms, which is 2.6x. This is the other face of Amdahl's law: the smaller the optimized part becomes, the larger the share of the unoptimized parts in total time. When to stop depends on whether the remaining time is still worth the effort, not on whether the profile still has a function in first place (it always does).

## Compile-time hot spots

A profiler measures the time a program spends running. When compilation itself is slow, what you need to find is which header or which template instantiation costs the most, and the tool is Clang's `-ftime-trace`: it writes a JSON file next to the object file (`x.json` for `-o x.o`), which can be opened with Chrome's `chrome://tracing` or speedscope, showing a flame graph as well. Analyzing and speeding up compilation is covered in [[toolchain/build-speed]].

## Pitfalls

!!! pitfall "Profiling a debug build"
    In profiles of `-O0` or `-Og` builds, the top entries are often accessors that would be inlined away in a release build. Profile at the same optimization level as the release, plus `-g`.

!!! pitfall "Looking only at self time"
    The functions with the largest self time are often low-level ones like `memcmp` and `malloc`. They are usually already fast; what should change is the code calling them too many times. Follow total time from the top down.

!!! pitfall "Profiling the wrong input"
    Hot spots depend on the input. Shrinking the vocabulary from 50,000 words to 50, the `++counts[clean]` line dropped from 66% to 26% in the profile on our test machine, and `in >> w` rose to 46%, taking first place. Profile with realistic data, and prepare several input sizes if needed.

!!! pitfall "Two changes, one measurement"
    Make two changes at once and you don't know where the gain came from; one may even have sped things up while the other slowed them down, cancelling out. Change one thing at a time, and profile again after each change.

## Questions

!!! question "1"
    A profile shows function `f` taking 20% of the time, and you make it 2 times faster. At most how much faster is the whole program? What if `f` took 80%?

<details markdown="1">
<summary>Answer</summary>

From S = 1 / ((1 − p) + p / s): with p = 0.2 and s = 2, S = 1 / (0.8 + 0.1) ≈ 1.11, only 11% faster; with p = 0.8, S = 1 / (0.2 + 0.4) ≈ 1.67. Making a function 2 times faster yields a gain that depends on how much it took to begin with.
</details>

!!! question "2"
    At `-O2`, 66% of `count_words`'s samples land on line 50. At `-O0`, the same line takes 64%. If per-line counts are about the same, why say `-O0` profiles can't be trusted?

<details markdown="1">
<summary>Answer</summary>

The per-line counts happened to be close this time, but there is no guarantee. At `-O0`, how much each part slows down depends on how many of its calls would otherwise have been inlined away, and there is no reason for those factors to be equal, so the shares may well change. By function, `-O0`'s first place is `__get_pointer`, which doesn't exist at all under `-O2`. The as-if rule ([[intro.abstract#1]]) allows the optimizer to change the program's structure drastically; only by profiling the machine code that actually runs can conclusions be applied to the release version.
</details>

!!! question "3"
    Profiling a program compiled with default `-O2` on x86-64 Linux using `perf record -g`, many functions in the call tree hang directly under the root with no visible callers. What might be the cause, and what do you do?

<details markdown="1">
<summary>Answer</summary>

`-g` makes `perf` unwind via frame pointers, and on x86-64 `-O2` omits the frame pointer by default (code compiled on our test machine with `--target=x86_64-linux-gnu -O2 -S` has no `%rbp` frame chain), so the chain is broken and callers cannot be found. Recompile with `-fno-omit-frame-pointer`, or switch to `perf record --call-graph dwarf`, which unwinds using debug information. System libraries may likewise lack frame pointers.
</details>

## Summary

| Question | Approach |
|---|---|
| Where does the time go? | Sample first: `sample` or Instruments on macOS, `perf record` on Linux |
| How to build | Release optimization level plus `-g`; add `-fno-omit-frame-pointer` when frame-pointer unwinding is needed; `-gdwarf-4` on our test machine |
| How to read results | Follow total time down from `main`; for low-level functions with large self time, look at who calls them |
| Inlined code | `atos -i` and `llvm-symbolizer --inlining` expand inlined frames, which have no call overhead |
| Why is it slow? | Hardware counters: `perf stat` on Linux, Instruments' CPU Counters on macOS |
| Confirming a section's time | Scoped timers; `-finstrument-functions-after-inlining` is only good for counting calls |
| After the change | Estimate the upper bound with Amdahl's law, measure again, profile again; the hot spot will move |
