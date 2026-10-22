---
title: Link-time and profile-guided optimization
summary: "Optimization at the build level: why the compiler cannot see function bodies in another translation unit, how full LTO and ThinLTO restore inlining and devirtualization at link time and what they cost to build, PGO's instrument–merge–use steps and the code layout it changes, sampling PGO and BOLT, how much -O3 and -mcpu actually change, and two pitfalls: LTO exposing ODR violations, and stale profile data."
tags: performance, LTO, ThinLTO, PGO, devirtualization, build, ODR, Clang
updated: 2026-10-19
group: Compiler
---

!!! tldr
    - When compiling one translation unit, the compiler sees only declarations of functions in other translation units, so calls to small functions across files can be neither inlined nor vectorized. On our test machine, summing 1M elements took 0.92 ns/element with the function body in another file, and 0.077 ns/element with `-flto`.
    - `-flto` merges the whole program into one module and optimizes it; `-flto=thin` only exchanges summaries and imports functions on demand, so it can run in parallel and cache incrementally. The cost falls on the link step: for an 80-file program on our test machine, link memory went from 60 MiB to 200–300 MiB.
    - LTO plus `-fwhole-program-vtables` can turn a virtual call with only one overrider into a direct call, but the class must also have hidden LTO visibility (for example with `-fvisibility=hidden`), otherwise nothing happens.
    - PGO has three steps: build instrumented and run, `llvm-profdata merge`, and rebuild with the profile. It changes inlining decisions, block layout and indirect calls; a CSV parsing loop became about 10% faster on our test machine. When the source changes, profile data goes stale; Clang warns and discards the data for mismatched functions.
    - All these optimizations are bound by the as-if rule and do not change the behavior of well-formed programs; but when a program has an ODR violation, LTO can turn an error the linker used to hide into a completely different result.

All numbers are observations on our test machine (Apple M2 Pro, macOS, Homebrew Clang 23.1, libc++, arm64). The machine was heavily loaded during measurement, so absolute values are only indicative; relative comparisons within one table come from alternating runs, taking the minimum over several rounds. Results may differ on another machine or compiler version. The timing harness is [[perf/measuring#harness|bench.hpp]]: each sample lasts at least about 1 ms, warm-up samples are discarded, the median of 31 samples is reported, and `bench::do_not_optimize` uses an empty inline asm statement to make the optimizer believe the result was read.

## A small function in another file

```cpp title="scale.h"
#pragma once
int scale(int x);
```

```cpp title="scale.cpp" ok
#include "scale.h"
int scale(int x) { return x * 3 + 1; }
```

```cpp title="main.cpp" ok
#include "bench.hpp"
#include "scale.h"
#include <cstdio>
#include <vector>

[[gnu::noinline]] long sum(const std::vector<int>& v) {
  long s = 0;
  for (int x : v) s += scale(x);   // scale is defined in another translation unit
  return s;
}

int main() {
  bench::prefer_performance_cores();
  std::vector<int> v(1 << 20);
  for (int i = 0; i < (int)v.size(); ++i) v[i] = i & 1023;
  auto s = bench::run("sum", [&] { long r = sum(v); bench::do_not_optimize(r); });
  std::printf("%.3f ns/elem\n", s.median / v.size());
}
```

```bash
clang++ -std=c++2c -O2 -c scale.cpp -o scale.o
clang++ -std=c++2c -O2 -c main.cpp  -o main.o
clang++ main.o scale.o -o nolto
```

The loop in `sum` does a `bl _scale` for every element (all assembly on this page is taken from `llvm-objdump -d` output, with addresses replaced by labels and some lines omitted):

```asm
LBB0_2:
  ldr   w0, [x20], #0x4      ; load v[i] as the argument
  bl    _scale               ; a real function call
  add   x19, x19, w0, sxtw
  cmp   x20, x21
  b.ne  LBB0_2
```

When compiling `main.cpp`, the compiler knows only the declaration of `scale`. It does not know whether `scale` reads or writes globals or throws, so it has no choice but to call it, and the loop cannot be vectorized. Measured on our test machine: 0.92 ns/element.

### Why the compiler can't see it

A **translation unit** (TU) is a source file together with everything it `#include`s ([[lex.separate#1]]). Translation phase 7 analyzes each TU separately and translates it into a **translated translation unit**, usually a `.o` file; only phase 8 combines them and resolves references to external entities ([[lex.phases#1]]). Traditional toolchains follow this order strictly: the compiler generates machine code in phase 7, and the linker in phase 8 only concatenates machine code and fills in addresses, without optimizing further. How the phases map onto real tools is in [[toolchain/compilation-pipeline]].

The standard does not require implementations to really separate the phases. A footnote in [[lex.phases]] says implementations need only behave as if the phases occur in order, and may in fact merge them. The more general basis is the [[g:as-if-rule]]: an implementation only needs to emulate the [[g:observable-behavior]] of the abstract machine ([[intro.abstract#1]]). Moving the body of `scale` into `sum` changes no observable behavior, so cross-TU inlining is allowed; the problem is only that in a traditional toolchain, by the time this could be done, the function body is gone.

There are two ways to let the call site see the function body:

- Write the definition as an [[g:inline-function]] in the header. Every TU has an identical copy of the definition, which [[basic.def.odr#16]] permits. Details like inlining thresholds are in [[perf/compiler-optimizations]].
- Keep it in the `.cpp` and use **link-time optimization** (LTO) instead, postponing optimization until the whole program is visible.

## Turning on LTO

```bash
clang++ -std=c++2c -O2 -flto -c scale.cpp -o scale.o
clang++ -std=c++2c -O2 -flto -c main.cpp  -o main.o
clang++ -flto main.o scale.o -o full      # the link step needs -flto too
```

With `-flto`, the `.o` no longer holds machine code but LLVM's intermediate representation (bitcode); `file main.o` reports `LLVM bitcode, wrapper`. Real machine code generation is postponed to link time: when the linker meets bitcode, it hands it to LLVM's LTO library, which merges all the modules and runs optimization and code generation again.

On macOS, `clang++` invokes the system `ld` and passes it Homebrew LLVM's own `libLTO.dylib` via `-lto_library`. `clang++ -flto x.o -###` shows the linker actually invoked and this argument. Our test machine also has another, older `ld` in PATH, and `-###` shows the driver prefers the one found in PATH, so all commands on this page were run with `PATH=/opt/homebrew/opt/llvm/bin:/usr/bin:/bin`, using the system `ld` (ld-1266.8). Homebrew's `llvm` package does not include lld, and `-fuse-ld=lld` reports invalid linker name on our test machine; on Linux, lld or gold with the LLVM plugin is common.

The result: there is no call left in `sum`, and the loop is vectorized, processing 16 elements per iteration:

```asm
LBB_vec:
  ldp    q17, q18, [x8, #-0x20]
  ldp    q19, q20, [x8], #0x40
  movi.4s v21, #0x1
  mla.4s v21, v17, v1          ; x * 3 + 1, in groups of 4
  ...
  saddw2.2d v3, v3, v21        ; widen to 64 bits and accumulate
  saddw.2d  v2, v2, v21
  ...
  subs   x13, x13, #0x10
  b.ne   LBB_vec
```

`llvm-nm` shows two more changes. `_scale` has disappeared from the final executable, since its only use has been inlined. `sum` has changed from a global symbol `T` to a local symbol `t`, and its parameter has changed from `const vector&` to the two pointers `begin` and `end` passed directly. When linking an executable, LTO knows nobody outside will call these functions except via `main`, so it **internalizes** them and can rewrite their signatures freely.

| Build | ns/element |
|---|---|
| No LTO | 0.92 |
| `-flto` | 0.077 |
| `-flto=thin` | 0.077 |

The 12x difference comes mainly from vectorization, not from the call instructions saved.

!!! note "LTO only covers the bitcode taking part in the link"
    LTO's scope is all object files provided as bitcode in this one link, including static library members compiled with `-flto`. Dynamic libraries (including the system's libc++.dylib) and object files not compiled with `-flto` are outside it, and calls across them remain ordinary calls. This is also the point made on the [[patterns/pimpl]] page: LTO can do nothing for calls across a shared library boundary.

### Full LTO and ThinLTO

**Full LTO** (`-flto` or `-flto=full`) links all modules into one giant module at link time, then optimizes it as if compiling one huge TU. It sees everything, but this step is essentially serial, and memory use grows with the size of the whole program.

**ThinLTO** (`-flto=thin`) attaches a **summary** to each module at compile time: which functions it defines, how big they are, whom they call. At link time it first reads only the summaries for global analysis (who calls whom, which symbols can be internalized); then each module goes into its own independent backend, which **imports** the bodies of small called functions from other modules as needed, then optimizes and generates code. These backends can run in parallel and can be cached.

| | Full LTO | ThinLTO |
|---|---|---|
| IR at link time | All modules merged into one | Each module handled separately, importing functions per the summaries |
| Parallelism | Optimization essentially serial | Backends in parallel |
| Incremental builds | Change one file, reoptimize the whole program | With a cache, only affected modules are redone |
| Precision of cross-module analysis | Highest | Depends on summaries, usually close |

In the `scale` example above, both generate the same loop.

### Build cost

To look at build cost, a script generated an 80-source-file program: each file defines a function that processes records using `std::format`, `std::sort`, `std::map` and `std::unordered_map`, and calls the function in the next file. Compilation ran in parallel with `xargs -P 8`; each mode was measured twice, with `/usr/bin/time -l` recording the link's CPU time and maximum resident memory. Many other processes were running on the machine during measurement and wall time fluctuated a lot, so the table lists only the more stable CPU time and memory.

| Mode | Compile CPU time (user+sys) | Link CPU time (user) | Link max memory | Executable |
|---|---|---|---|---|
| No LTO | 104–105 s | 0.09–0.10 s | 60 MiB | 1159 KiB |
| `-flto` | 87–95 s | 5.3 s | 261–305 MiB | 957 KiB |
| `-flto=thin` | 82 s | 16–17 s | 206–227 MiB | 1003 KiB |

A few observations:

- With LTO, the compile phase actually takes less time, because each file no longer generates machine code. The saved work moves to the link step together with the optimization work.
- Linking goes from under 0.1 seconds to several seconds, and memory grows 3–5 times. The bigger the program, the bigger the gap; in large projects the full-LTO link is often the slowest and most memory-hungry step of the build.
- ThinLTO's link CPU time exceeds full LTO's, because every backend reoptimizes its own functions and the imported ones; but the work is spread across threads. In the first measurement, under lower load, wall time was 7.3 s for full LTO and 3.2 s for ThinLTO.
- Both kinds of LTO make the program smaller; cross-module inlining and dead code removal eliminate duplicate template instances and unused functions.

ThinLTO's cache matters most for everyday incremental builds. macOS `ld` takes the cache directory via `-Wl,-cache_path_lto,dir`:

```bash
clang++ -flto=thin -Wl,-cache_path_lto,cache o/*.o -o app   # first time: user 17.7 s
# modify one source file and recompile only it
clang++ -flto=thin -Wl,-cache_path_lto,cache o/*.o -o app   # with cache: user 0.40 s
clang++ -flto=thin o/*.o -o app2                            # without cache: user 17.2 s
```

Full LTO has no such incremental mechanism; changing one file means reoptimizing the whole program. A common practice is to use no LTO or only ThinLTO for day-to-day development, and full LTO together with PGO for release builds.

## Whole-program devirtualization

```cpp title="op.h"
#pragma once
struct Op {
  virtual ~Op() = default;
  virtual int apply(int x) const = 0;
};
Op* make_op();   // defined in op.cpp
```

```cpp title="op.cpp" ok
#include "op.h"
struct Scale final : Op {
  int apply(int x) const override { return x * 3 + 1; }
};
[[gnu::noinline]] Op* make_op() { return new Scale; }
```

```cpp title="main.cpp" ok
#include "bench.hpp"
#include "op.h"
#include <cstdio>
#include <vector>

[[gnu::noinline]] long run(const Op& op, const std::vector<int>& v) {
  long s = 0;
  for (int x : v) s += op.apply(x);   // virtual call
  return s;
}

int main() {
  bench::prefer_performance_cores();
  std::vector<int> v(1 << 20);
  for (int i = 0; i < (int)v.size(); ++i) v[i] = i & 1023;
  Op* op = make_op();
  auto s = bench::run("run", [&] { long r = run(*op, v); bench::do_not_optimize(r); });
  std::printf("%.3f ns/elem\n", s.median / v.size());
  delete op;
}
```

`op.apply(x)` in `run` is a [[g:virtual-function-call]]: load the vtable pointer from the object, load the function address from the vtable, then call indirectly (the vtable layout is in [[toolchain/object-layout-and-vtables]]). `make_op` is deliberately not inlined, so even with LTO, `run` cannot see the object's dynamic type.

In the whole program, `Op::apply` has only one overrider, `Scale::apply`. If the compiler can confirm this, `op.apply(x)` can only call `Scale::apply`, and can become a direct call and then be inlined. Clang's **whole-program devirtualization** does exactly this; the flag is `-fwhole-program-vtables`, which requires LTO at the same time, otherwise it reports `invalid argument '-fwhole-program-vtables' only allowed with '-flto'`.

| Build (all `-O2`) | Loop in `run` | ns/element |
|---|---|---|
| No LTO | `blr x8` (indirect call) | 0.92 |
| `-flto` | Indirect call | 0.92 |
| `-flto -fvisibility=hidden` | Indirect call | 0.92 |
| `-flto -fwhole-program-vtables` | Indirect call | 0.92 |
| `-flto -fwhole-program-vtables -fvisibility=hidden` | Inlined and vectorized, no call | 0.077 |
| `-flto=thin -fwhole-program-vtables -fvisibility=hidden` | Same | 0.078 |

Only the last two rows take effect. The reason for the fourth row is **LTO visibility**: devirtualization requires seeing all derived classes of a class, and a class with default visibility might be derived from in a dynamic library loaded later with `dlopen`, whose overriders are not in this link. Clang therefore only does whole-program devirtualization for classes with hidden LTO visibility. `-fvisibility=hidden` is the simplest way; classes that need to be exported can be marked individually with `__attribute__((visibility("default")))`, or `[[clang::lto_visibility_public]]` can declare their LTO visibility public. Symbol visibility itself is covered in [[toolchain/linking-and-symbols]].

Removing `final` from `Scale` gives the same result: what matters here is that the whole program has only one overrider, not `final`. `final` only helps call sites whose static type is `Scale`; see the devirtualization section in [[perf/compiler-optimizations]].

This transformation is likewise permitted by the as-if rule. The standard only says a virtual call calls the final overrider in the object's dynamic type ([[expr.call#2]]; final overrider is defined in [[class.virtual#2]]), not how to find it. The standard's program model has no dynamic libraries either; to it, the program is complete before execution. `-fvisibility=hidden` plus `-fwhole-program-vtables` is effectively a guarantee you give the compiler: there are no derived classes outside this link. If some plugin really does derive from a class with hidden visibility, the devirtualized code calls the wrong function directly; this is outside the standard, and the compiler will not report it.

## Profile-guided optimization

How much to inline, which branch to put on the fall-through path, which value a `switch` compares first: normally the compiler can only guess with static heuristics. **Profile-guided optimization** (PGO) first runs the program on representative input, recording how many times each function and each branch actually executed, and then hands these counts to the compiler. The [[perf/branches]] page covers its relationship with `[[likely]]` from the angle of branch weights; here we look at the full workflow and its effect on inlining and code layout.

### The three steps

```bash
# 1. build instrumented and run on representative input
clang++ -std=c++2c -O2 -fprofile-instr-generate csv.cpp -o cinstr
LLVM_PROFILE_FILE=csv-%p.profraw ./cinstr 1

# 2. merge the raw profiles
llvm-profdata merge -o csv.profdata csv-*.profraw

# 3. rebuild with the profile
clang++ -std=c++2c -O2 -fprofile-instr-use=csv.profdata csv.cpp -o cpgo
```

`llvm-profdata` ships in Homebrew's `llvm` package in the same directory as `clang++`, and the versions must match: the `.profraw` format changes with LLVM versions. `%p` in `LLVM_PROFILE_FILE` is replaced by the process ID, so multiple runs and processes each write their own file, and `merge` adds them together. The instrumented build runs slower; for this example on our test machine it was about 2.2 and 4 times slower than the normal build in two measurements (under different load).

`llvm-profdata show --all-functions --counts csv.profdata` shows the counts. In the example below, `parse_field` was called 32 793 216 times, and the three branches that throw all have count 0.

### Example: a parsing loop

```cpp title="csv.cpp" ok
#include "bench.hpp"
#include <cstdio>
#include <cstdlib>
#include <stdexcept>
#include <string>

// parse an integer field ending in a comma or newline. The error-handling branches are long but almost never run
int parse_field(const char*& p, const char* e, long line) {
  bool neg = false;
  if (p < e && *p == '-') { neg = true; ++p; }
  if (p == e || *p < '0' || *p > '9') {
    std::string msg = "line " + std::to_string(line) + ": expected digit, got '";
    msg += (p == e ? std::string("EOF") : std::string(1, *p));
    msg += "' near \"" + std::string(p, std::min<std::size_t>(e - p, 16)) + "\"";
    throw std::runtime_error(msg);
  }
  long v = 0;
  while (p < e && *p >= '0' && *p <= '9') {
    v = v * 10 + (*p - '0');
    if (v > 2147483647L) {
      std::string msg = "line " + std::to_string(line) + ": overflow";
      throw std::out_of_range(msg);
    }
    ++p;
  }
  if (p < e && *p != ',' && *p != '\n') {
    std::string msg = "line " + std::to_string(line) + ": bad separator '" + std::string(1, *p) + "'";
    throw std::runtime_error(msg);
  }
  if (p < e) ++p;
  return neg ? -int(v) : int(v);
}

[[gnu::noinline]] long sum_csv(const std::string& s) {
  const char* p = s.data();
  const char* e = p + s.size();
  long total = 0, line = 1;
  while (p < e) {
    bool eol = false;
    int v = parse_field(p, e, line);
    if (p[-1] == '\n') eol = true;
    total += v;
    line += eol;
  }
  return total;
}

int main(int argc, char** argv) {
  std::srand(argc > 1 ? std::atoi(argv[1]) : 1);   // different seeds for training and measuring
  std::string s;
  while (s.size() < (8u << 20)) {
    for (int k = 0; k < 8; ++k) {
      if (std::rand() % 4 == 0) s += '-';
      s += std::to_string(std::rand() % 100000);
      s += k == 7 ? '\n' : ',';
    }
  }
  bench::prefer_performance_cores();
  auto st = bench::run("sum_csv", [&] { long r = sum_csv(s); bench::do_not_optimize(r); });
  std::printf("%.3f ns/byte\n", st.median / s.size());
}
```

Training on data generated with seed 1 and measuring on data generated with seed 2. Alternating runs over several rounds on our test machine, taking the minimum of the per-round medians:

| Build | ns/byte (range over several measurements) |
|---|---|
| `-O2` | 1.21–1.30 |
| `-O2` + PGO | 1.11–1.16 |

The PGO build is about 10% faster. To rule out accidental effects of code alignment, separate builds were also made with each of `-falign-loops=16/32/64` and `-falign-functions=64`: the normal build ranged 1.21–1.25 and the PGO build 1.105–1.115; the gap did not disappear with alignment.

### What it changed

Without a profile, `parse_field`, carrying three sections of string-building and exception-throwing code, has over 400 instructions, more than the inlining threshold. `sum_csv` can only call it, and since `p` is passed by reference, `parse_field` has to write `p` back to memory for every character it reads:

```asm
; -O2: the digit loop in parse_field
LBB1_digit:
  ldrb  w13, [x8]
  sub   w14, w13, #0x30
  cmp   w14, #0x9
  b.hi  LBB1_sep
  mul   x10, x10, x11
  add   x10, x10, w14, uxtb
  cmp   x10, x12
  b.ge  LBB1_overflow
  add   x8, x8, #0x1
  str   x8, [x0]           ; store p back to the caller's variable on every character
  cmp   x8, x1
  b.ne  LBB1_digit
```

The profile tells the compiler that this call site ran over thirty million times, while the three error branches were never taken. Clang uses a much higher inlining threshold for hot call sites, so it inlines `parse_field` into `sum_csv` (`sum_csv` goes from 44 instructions to 405). `p` stays in a register, saving a store per character. The error-handling code is laid out after the loop, and the hot path is a contiguous fall-through sequence:

```asm
; PGO: the hot loop after inlining (excerpt)
LBB0_field:
  ldrb  w13, [x14], #0x1   ; read the first character
  cmp   w13, #0x2d         ; is it '-'?
  ...
LBB0_digit:
  mul   x14, x14, x11
  add   x14, x14, w16, uxtb
  cmp   x14, x12
  b.ge  LBB0_overflow      ; cold: jump to the end of the function
  cmp   x21, x20
  b.eq  LBB0_done_field
  ldrb  w15, [x21], #0x1
  sub   w16, w15, #0x30
  cmp   w16, #0x9
  b.ls  LBB0_digit         ; hot: stay in the loop
  cmp   w15, #0x2c
  b.eq  LBB0_next          ; comma
  cmp   w15, #0xa
  b.eq  LBB0_next          ; newline
  b     LBB0_bad_sep       ; cold: jump to the end of the function
  ...
LBB0_expected_digit:        ; cold code: build the error message and throw
  bl    _strlen
  ...
```

These changes are the main sources of PGO's gains:

- Inlining: hot call sites are inlined more aggressively, cold ones hardly at all, so total code size does not necessarily grow.
- Block layout: the more frequently executed successor goes in the fall-through position, cold code moves to the end of the function, and hot code is more compact in the instruction cache.
- Register allocation and loop optimization: knowing which path is hot, the cost of spilling to the stack is placed on the cold path.
- `switch` and indirect calls: common values and targets can be compared separately; see below.

PGO cannot make an inherently unpredictable branch predictable. We wrote a lexer classifying random text, and it ran at about 3 ns/byte both before and after PGO; nearly all the time went into mispredictions, and no code layout could help. Branch prediction itself is covered in [[perf/branches]].

### Indirect call promotion

```cpp title="disp.cpp (excerpt)"
using Handler = void (*)(State&, const Event&);
Handler table[4] = {on_add, on_max, on_reset, on_error};

[[gnu::noinline]] State process(const std::vector<Event>& evs) {
  State s;
  for (const Event& e : evs) {
    if (e.kind >= 4) [[unlikely]] { ++s.errors; continue; }
    table[e.kind](s, e);   // indirect call; 90% of events call on_add
  }
  return s;
}
```

PGO can record which targets each indirect call site actually called, then **promote** the most common target into a comparison plus a direct call:

```asm
; process after IR-instrumentation PGO (excerpt)
  ldr   x8, [x22, x8, lsl #3]   ; load the function pointer from table
  cmp   x8, x23                 ; x23 = address of on_add
  b.ne  LBB_indirect            ; not on_add: still blr x8
  ldrsw x8, [x20, #0x4]         ; it is: on_add's body has been inlined
  ldr   x9, [x19]
  add   x8, x9, x8
  ...
```

Recording call targets is called **value profiling**. Clang 23's `-fprofile-instr-generate` does not do value profiling by default: `llvm-profdata show --ic-targets` shows `Indirect Call Site Count: 0` for this call site, and the code after PGO is still `blr x8`; only with `-mllvm -enable-value-profiling` does it record them. Switching to `-fprofile-generate` / `-fprofile-use` gets them: it shows counts for the four targets, with `on_add` at 89.99%.

| Build | ns/event |
|---|---|
| `-O2` | 1.96–2.12 |
| Front-end instrumentation PGO (`-fprofile-instr-*`) | 1.97–2.01 |
| IR instrumentation PGO (`-fprofile-*`) | 1.69–1.70 |

The two kinds of instrumentation differ in when the counters are inserted. `-fprofile-instr-generate` instruments in the Clang front end following the source structure; the same mechanism is used for code coverage (`-fcoverage-mapping`), and counts map to source regions. `-fprofile-generate` instruments LLVM IR after some optimization has already been done, with fewer counters. Profiles from both are processed with `llvm-profdata merge`. Devirtualization of virtual calls can also use the same value profiling for speculative promotion.

### Stale profile data

Continuing to use old profile data after modifying the source is common. Change the separator check in `parse_field` to also accept `'\r'`:

```cpp
if (p < e && *p != ',' && *p != '\n' && *p != '\r') {
```

and compile with the original `csv.profdata`:

```text
warning: profile data may be out of date: of 10 functions, 1 has mismatched data that will be ignored [-Wprofile-instr-out-of-date]
```

Front-end instrumentation profiles record, per function, a hash computed from its control-flow structure. When a function's branch structure changes, the hash no longer matches, and Clang discards all counts for that function while using the other functions' data as usual. As a result, `parse_field` is no longer inlined, and `sum_csv` goes back to 44 instructions and one call. On our test machine the timing this time was close to the PGO build; the reason was not fully analyzed (the modified source itself was a few percent faster than the original without PGO), so all we can say for certain is that code generation reverted.

There is a more insidious kind of stale profile: the code has not changed, but the workload has, and the profile no longer describes real execution. The [[perf/branches]] page measured PGO slowing the program down when trained on the opposite distribution. In practice:

- Make the training run part of the build, updating the profile together with the source;
- Watch for mismatched and unprofiled functions with `-Wprofile-instr-out-of-date` (on by default) and `-Wprofile-instr-unprofiled`;
- Take training input from real workloads, covering the main usage scenarios.

### Sampling PGO and BOLT

Instrumented PGO needs a dedicated instrumented build and a set of training inputs. Two other kinds of tools collect data directly from normally built programs. Our test machine runs macOS, where neither tool can run, so this section only describes how they work, without measurements.

**Sampling PGO** (AutoFDO) samples a normal optimized build in production using hardware performance counters; on Linux this is usually `perf record` with branch records (Intel's LBR, SPE or BRBE on Arm, etc.), followed by a tool such as `create_llvm_prof` that maps addresses back to source lines via debug information. The resulting profile is passed to Clang with `-fprofile-sample-use=`. It has no instrumentation overhead and its data comes from real workloads, but it is less precise than instrumented counts and depends on debug information to map addresses back to source.

**BOLT** (`llvm-bolt`) is a post-link optimizer: it reads an already linked binary together with profile data collected by `perf`, rearranges functions and blocks, and writes out a new binary. It works on the final machine code and can see things the compiler cannot, such as function order across all object files and static libraries. BOLT supports only the ELF format (Linux), usually requires relocations to be kept at link time (`-Wl,--emit-relocs`), and does not support macOS's Mach-O. It is often stacked with LTO and PGO: the compiler makes decisions like inlining first, and BOLT then adjusts the layout.

## `-O3` vs `-O2`

`-O3` turns on some more aggressive transformations on top of `-O2` (such as a higher inlining threshold). Compiling the two programs above at each level and comparing the instructions in `__text` and the run times:

| Program | `-O2` instructions | `-O3` instructions | `-O2` ns | `-O3` ns |
|---|---|---|---|---|
| `csv.cpp` | 1039 | 1243 | 1.26 | 1.24 |
| `disp.cpp` | 474 | 523 | 1.98 | 1.98 |

`-O3` does generate different code, but run times are within measurement error. In `csv.cpp`, `-O3` still does not inline `parse_field`: it only raises the threshold a bit by fixed rules, while PGO decides by actual hotness. Which level is faster can only be measured for the specific program, not inferred from the level number; `-O3` generates bigger code, and large programs sensitive to the instruction cache are sometimes slower with it. Which optimizations each level enables is in [[perf/compiler-optimizations]].

## `-march=native` and `-mcpu`

These options decide which instructions the compiler may use and which microarchitecture to tune for. `clang++ -### ...` shows the arguments the driver actually passes to the front end:

| Option | `-target-cpu` | Architecture version | `-tune-cpu` |
|---|---|---|---|
| None | `apple-m1` | v8.4a | `apple-m5` |
| `-mcpu=native` | `apple-m2` | v8.6a | not given (follows `apple-m2`) |
| `-march=native` | `apple-m2` | v8.6a | `apple-m5` |
| `-mcpu=apple-m2` | `apple-a15` | v8.6a | not given |

On Apple platforms the default target is already the M1, so NEON, dot product (`sdot`) and FMA are available directly. The M2 adds only a few extensions such as BF16 and `i8mm`. `csv.cpp`, `disp.cpp`, an `int8` dot product and a `float` `y += a * x` loop generate exactly the same code under the default, `-mcpu=apple-m2` and `-mcpu=native` (disassembly identical character for character). On our test machine these options have no measurable effect on ordinary code.

x86-64 is different. On Linux the default target for `x86_64` is the original x86-64 baseline, which only guarantees SSE2. Cross-compiling the same `y[i] += a * x[i]` loop (`--target=x86_64-linux-gnu -O2 -S`):

| Option | Key instructions in the loop | `float`s per instruction |
|---|---|---|
| Default | `mulps` + `addps`, `xmm` | 4 |
| `-march=x86-64-v3` | `vfmadd213ps`, `ymm` | 8 |
| `-march=x86-64-v4` | `vfmadd213ps`, `ymm` | 8 |
| `-march=znver4` | `vfmadd213ps`, `zmm` | 16 |

`x86-64-v4` includes AVX-512, but for the generic v4 target Clang still prefers 256-bit vectors, and uses 512-bit only when tuning for `znver4`. More on how vectorization relates to the target instruction set is in [[perf/vectorization]].

These options have two consequences to watch out for.

First, the resulting program runs only on CPUs that support those instructions. A program compiled with `-march=native` and taken to an older machine may terminate with an illegal instruction when it reaches some new instruction. Programs distributed to others should specify an explicit target, such as `-march=x86-64-v3`, not `native`.

Second, floating-point results may change with the target. In the table above, the default target has no FMA instruction, so multiply and add round separately; `x86-64-v3` uses a single `vfmadd` that rounds only once. [[expr.pre#6]] allows floating-point expressions to be represented with greater precision than their type requires, and Clang's default `-ffp-contract=on` uses this to fuse multiply-add into FMA within a single expression. So the same source with a different `-march` may differ in the last bit; when bit-for-bit reproducibility is needed, use `-ffp-contract=off`.

## LTO exposes ODR violations

```cpp title="cfg.h"
#pragma once
struct Config {
  int retries;
#ifdef WITH_TIMEOUT
  int timeout_ms;
#endif
};
inline Config default_config{3
#ifdef WITH_TIMEOUT
  , 500
#endif
};
```

```cpp title="a.cpp" ifndr
#define WITH_TIMEOUT
#include "cfg.h"
int timeout() { return default_config.timeout_ms; }
```

```cpp title="b.cpp"
#include "cfg.h"
int retries() { return default_config.retries; }
```

```cpp title="main.cpp"
#include <cstdio>
int timeout();
int retries();
int main() { std::printf("%d %d\n", retries(), timeout()); }
```

The definitions of `Config` and of the [[g:inline-variable]] `default_config` in the two TUs consist of different tokens, violating [[basic.def.odr#16]] (¶16.4 requires every definition to consist of the same sequence of tokens). The program is ill-formed, no diagnostic required ([[g:ifndr|IFNDR]]), and no outcome violates the standard. The actual result on our test machine depends on how it is built and on link order:

| Build | Link order `a.o b.o` | Link order `b.o a.o` |
|---|---|---|
| `-O0` | `3 500` | `3 0` |
| `-O2` | `3 500` | `3 0` |
| `-O2 -flto=thin` | `3 500` | `3 0` |
| `-O2 -flto` | `3 500` | `3 -327417768` |

Without LTO, `default_config` is a weak definition, and the linker keeps the first one in order, comparing neither size nor contents ([[toolchain/linking-and-symbols]]). With `b.o` first, the 4-byte version is kept, and `timeout()` reads the 4 bytes after that object, which happen to be 0. The program just looks like it is missing a configuration item. ASan reports nothing for this out-of-bounds read either.

With full LTO, LTO likewise keeps a single definition, but then it optimizes the whole program. It finds that `default_config` is never written, so it folds `retries()` into the constant 3; `timeout()` reads a location outside a 4-byte object, which to LTO is an out-of-bounds access with undefined result, so it prepares no value at all for the second argument. The final `main` is reduced to:

```asm
_main:
  ...
  mov  w8, #0x3          ; retries() folded to 3
  str  x8, [sp]          ; the second variadic argument's slot is never written
  ...
  bl   _printf
```

`default_config`, `retries` and `timeout` have all vanished from the executable, and the second number is whatever was left on the stack. An error the linker hid without LTO becomes completely different behavior under LTO.

The usual sources of this kind of problem: the same header seeing different macros in different TUs (`NDEBUG`, feature switches, library configuration like `_LIBCPP_*`), structs with the same name written separately in two `.cpp` files, or linking the same library compiled with different options. When a program's behavior suddenly changes after turning on LTO, check these places before suspecting the compiler. GCC's `-flto` together with `-Wodr` can find some type mismatches (we had no GCC on our test machine and did not verify this); Clang has no corresponding cross-TU check for traditional header-based builds; see [[std/ifndr]].

## Questions

!!! question "1"
    If `scale` is rewritten as `inline int scale(int x) { return x * 3 + 1; }` in the header, without LTO, how does `sum` perform? What does this require with respect to the ODR?

<details markdown="1">
<summary>Answer</summary>

`main.cpp` includes the function body, so when compiling `sum` it can be inlined and vectorized, and the result should match the LTO version. The cost is that every TU including the header compiles it. Inline functions may be defined in multiple TUs, but by [[basic.def.odr#16]] the definitions must consist of the same tokens and the names must refer to the same entities; otherwise the program is ill-formed, no diagnostic required. As long as the header is not affected by different macros, this holds naturally.
</details>

!!! question "2"
    An application puts its core logic in its own dynamic library `libcore.dylib`, and both the main program and the library are compiled with `-flto`. Can calls from the main program to small functions in `libcore` be inlined? What about whole-program devirtualization of an abstract class defined in `libcore`?

<details markdown="1">
<summary>Answer</summary>

Neither can cross the dynamic library boundary. LTO's scope is one link; the main program and `libcore.dylib` are two separate links, and when linking the main program all that is visible is the symbols the dynamic library exports, with no function bodies. Devirtualization likewise: if a class in `libcore` is to be used by the main program, it must itself have default visibility, so its LTO visibility is public and `-fwhole-program-vtables` will not touch it; even if it were forcibly declared hidden, the main program could define new derived classes, and the premise of devirtualization would not hold. When you need inlining across the boundary, put the hot functions in headers, or switch to static linking.
</details>

!!! question "3"
    The same program is built with `-O2 -flto -fprofile-instr-use=x.profdata`. The profile was collected on an instrumented build without LTO. Can it be used?

<details markdown="1">
<summary>Answer</summary>

Yes. On our test machine, building `csv.cpp` with `-flto` using the `csv.profdata` collected without LTO gives no warning, and `parse_field` is inlined as before. Front-end instrumentation counts are recorded by function name and the function's control-flow hash, independent of later optimization and of whether LTO is enabled; Clang attaches the counts to branches when translating source into IR. At LTO link time, these branch weights and function hotness travel with the bitcode into cross-module inlining and layout decisions. A common release build is exactly: instrumented build, training, then an LTO plus PGO build. As long as the source has not changed, the profile does not go stale; if the source has changed, handle it per the warning above.
</details>

## Summary

| Technique | What it solves | How to enable | Cost and prerequisites |
|---|---|---|---|
| inline functions in headers | Cross-TU inlining | Put the definition in the header | Compile time; ODR requires identical definitions everywhere |
| Full LTO | Cross-TU inlining, internalization, dead code removal | `-flto` for both compile and link | Slow, memory-hungry link; not incremental |
| ThinLTO | Same, scalable | `-flto=thin`, `-Wl,-cache_path_lto,dir` | More link CPU time, but parallel and cacheable |
| Whole-program devirtualization | Virtual calls with only one overrider | LTO + `-fwhole-program-vtables` + hidden LTO visibility | Guarantee there are no derived classes outside the link |
| Instrumented PGO | Inlining, layout and indirect calls decided by actual hotness | `-fprofile-instr-generate` → run → `llvm-profdata merge` → `-fprofile-instr-use` | Training workflow; data goes stale when source or workload changes |
| Sampling PGO, BOLT | Optimization from production data | `-fprofile-sample-use`, `llvm-bolt` | Linux/ELF; needs hardware sampling support |
| `-O3` | More aggressive fixed rules | `-O3` | Not necessarily faster; measure |
| `-march`/`-mcpu` | New instructions, wider vectors | `-march=x86-64-v3` etc. | Program runs only on supporting CPUs; floating-point results may change |
