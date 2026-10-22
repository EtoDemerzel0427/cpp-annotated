---
title: Organizing a project with CMake
summary: "Target-centric CMake: a library, an executable and tests; PRIVATE/PUBLIC/INTERFACE usage requirements; which compiler options the language standard and build type finally turn into; warnings, sanitizer presets, compile_commands.json; installing and exporting a library; building modules; and common anti-patterns."
group: Engineering practice
tags: toolchain, CMake, build, ODR, sanitizer, modules
updated: 2026-10-19
---

!!! tldr
    - CMake doesn't compile code; it generates build files (such as Ninja's `build.ninja`) containing compiler commands. Whether a piece of CMake is right is ultimately decided by the command lines it generates.
    - Settings are attached to targets, and PRIVATE / PUBLIC / INTERFACE says whether they affect only the target itself, the target and its consumers, or only its consumers. Macros, include paths and standard versions used in headers must be PUBLIC; otherwise the library and its consumers see two different classes, an ODR violation with no diagnostic required.
    - `target_compile_features(... cxx_std_NN)` declares a minimum standard and propagates it to consumers; `CMAKE_CXX_STANDARD` sets the project's default. `CMAKE_CXX_EXTENSIONS OFF` makes CMake generate `-std=c++NN` instead of `-std=gnu++NN`.
    - Warning options are a target's PRIVATE settings. Build-environment choices such as sanitizers, `-Werror` and the compiler path go into `CMakePresets.json`, not `CMakeLists.txt`.
    - Global `include_directories` and `add_definitions`, rewriting `CMAKE_CXX_FLAGS` in `CMakeLists.txt`, and collecting sources with `file(GLOB)` all make the build depend on directory layout or on the caller rather than on the relationships between targets.

The standard doesn't say how to build a program. It only says that a source file together with the headers it includes, minus the lines skipped by conditional compilation, forms a preprocessing translation unit ([[lex.separate#1]]); translation units can be translated separately and then linked into a program. Where headers are searched for, which language mode is used and which macros are defined are implementation-defined or decided by the command line ([[cpp.include#1]]).

These command-line options change the program in the standard's sense: `-D` decides which lines remain in the translation unit, and `-std=` decides the value of `__cplusplus` ([[cpp.predefined#1]]) and the whole set of language rules. So errors in build scripts often show up as language-level errors, most typically ODR violations. How the compiler driver splits one command into preprocessing, compilation and linking is covered in [[toolchain/compilation-pipeline]].

!!! note "Test setup"
    CMake 3.29.3, Ninja 1.12.1, Homebrew Clang 23.1.3 (libc++), clang-tidy 23.1.3, Apple M2 Pro. In command output, the source directory is written `<src>`, the SDK path `<sdk>`, the compiler path is shortened to `clang++`, the `-MD -MT … -MF …` arguments that generate dependency files are dropped, long commands are wrapped as needed, and other omissions are shown as `...`. The Anaconda installation on `PATH` on our test machine carries an old `ld` and `ar` (see [[toolchain/compilation-pipeline]]); it was removed from `PATH` for these experiments. MSVC options are only described, not verified.

## A small project

A word-counting library `tally`, a command-line program and a test:

```text
tally/
├── CMakeLists.txt
├── CMakePresets.json
├── cmake/tallyConfig.cmake.in
├── include/tally/tally.hpp      public header
├── src/tally.cpp                library implementation
├── src/split.hpp                library's private header
├── app/main.cpp                 command-line program
└── tests/tally_test.cpp         test
```

The public header only uses C++17's `string_view`:

```cpp title="include/tally/tally.hpp"
#pragma once
#include <cstddef>
#include <string>
#include <string_view>
#include <unordered_map>
#include <utility>
#include <vector>

namespace tally {

class Counter {
public:
  void add_text(std::string_view text);
  std::size_t count(std::string_view word) const;
  std::vector<std::pair<std::string, std::size_t>> top(std::size_t n) const;

private:
  std::unordered_map<std::string, std::size_t> counts_;
};

} // namespace tally
```

The implementation uses C++20's `std::ranges::sort`, and the command-line program uses C++23's `std::println`. The three files need different standard versions, which will matter below.

```cpp title="app/main.cpp"
#include <tally/tally.hpp>

#include <iostream>
#include <iterator>
#include <print>
#include <string>

int main() {
  std::string text(std::istreambuf_iterator<char>(std::cin), {});
  tally::Counter c;
  c.add_text(text);
  for (auto& [word, n] : c.top(3))
    std::println("{:>4} {}", n, word);
}
```

The first half of `CMakeLists.txt` (installation comes later):

```cmake title="CMakeLists.txt"
cmake_minimum_required(VERSION 3.28)
project(tally VERSION 0.1.0 LANGUAGES CXX)

include(GNUInstallDirs)

set(CMAKE_CXX_EXTENSIONS OFF)        # -std=c++NN, not -std=gnu++NN
set(CMAKE_CXX_SCAN_FOR_MODULES OFF)  # no module sources, no dependency scanning

# ---- library ----
add_library(tally src/tally.cpp)
add_library(tally::tally ALIAS tally)

target_compile_features(tally
  PUBLIC  cxx_std_17      # the header uses string_view: consumers need at least C++17
  PRIVATE cxx_std_20)     # the implementation uses std::ranges::sort

target_include_directories(tally
  PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}>
  PRIVATE
    src)

# warnings are this target's own settings, not passed to consumers
set(gcc_like "$<COMPILE_LANG_AND_ID:CXX,GNU,Clang,AppleClang>")
set(msvc     "$<COMPILE_LANG_AND_ID:CXX,MSVC>")
target_compile_options(tally PRIVATE
  "$<${gcc_like}:-Wall;-Wextra;-Wpedantic;-Wconversion>"
  "$<${msvc}:/W4;/permissive->")

# ---- executable ----
add_executable(tally-cli app/main.cpp)
target_compile_features(tally-cli PRIVATE cxx_std_23)   # std::println
target_link_libraries(tally-cli PRIVATE tally::tally)

# ---- tests ----
include(CTest)
if(BUILD_TESTING)
  add_executable(tally_test tests/tally_test.cpp)
  target_link_libraries(tally_test PRIVATE tally::tally)
  add_test(NAME tally_test COMMAND tally_test)
endif()
```

CMake works in two steps. The **configure** step runs `CMakeLists.txt` and generates build files in the build directory; the build step has Ninja run the commands in those files. `-v` makes Ninja print every command:

```text
$ cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Debug \
        -DCMAKE_CXX_COMPILER=/opt/homebrew/opt/llvm/bin/clang++
$ cmake --build build -v
[1/6] clang++ -I<src>/include -g -std=c++17 -arch arm64 -isysroot <sdk>
        -o CMakeFiles/tally_test.dir/tests/tally_test.cpp.o -c <src>/tests/tally_test.cpp
[2/6] clang++ -I<src>/include -I<src>/src -g -std=c++20 -arch arm64 -isysroot <sdk>
        -Wall -Wextra -Wpedantic -Wconversion
        -o CMakeFiles/tally.dir/src/tally.cpp.o -c <src>/src/tally.cpp
[3/6] ar qc libtally.a CMakeFiles/tally.dir/src/tally.cpp.o && llvm-ranlib libtally.a
[4/6] clang++ -g ... CMakeFiles/tally_test.dir/tests/tally_test.cpp.o -o tally_test libtally.a
[5/6] clang++ -I<src>/include -g -std=c++23 -arch arm64 -isysroot <sdk>
        -o CMakeFiles/tally-cli.dir/app/main.cpp.o -c <src>/app/main.cpp
[6/6] clang++ -g ... CMakeFiles/tally-cli.dir/app/main.cpp.o -o tally-cli libtally.a
$ ctest --test-dir build
1/1 Test #1: tally_test .......................   Passed    0.38 sec
$ printf 'the cat and the hat\nthe end, the cat\n' | ./build/tally-cli
   4 the
   2 cat
   1 and
```

The whole page can be read against this output. Three TUs in the same project got three different `-std=` options; only `tally.cpp` can see the `src/` directory, and only it has warning options. The sections below explain where each of these differences comes from.

!!! pitfall "The compiler is fixed at the first configure"
    Without `CMAKE_CXX_COMPILER`, CMake on our test machine picked `/usr/bin/c++`, that is Xcode's AppleClang 21, not the Homebrew Clang on `PATH`. The compiler is written to the cache at the first configure; changing it later requires `cmake --fresh` or deleting the build directory and configuring again.

## Targets and usage requirements

A **target** is CMake's basic unit: `add_library` and `add_executable` each create one. Compile options, include paths, macro definitions and the language standard are set on targets, not on directories or global variables.

Every setting carries a keyword saying whom it applies to. Settings on the target itself are build requirements; settings that must be passed on to consumers (targets that depend on it through `target_link_libraries`) are **usage requirements**:

| Keyword | When compiling this target | When compiling consumers | Typical contents |
|---|---|---|---|
| `PRIVATE` | Applies | Doesn't apply | Private header directories for the implementation, warning options, dependencies used only in `.cpp` files |
| `PUBLIC` | Applies | Applies | Public header directories, macros tested in headers, the minimum standard required by headers |
| `INTERFACE` | Doesn't apply | Applies | All settings of a header-only library (`add_library(x INTERFACE)`) |

They can be matched one by one in the output above:

- `include/` is PUBLIC, so the command lines for `tally_test.cpp` and `main.cpp` also have `-I<src>/include`; `src/` is PRIVATE and only appears on the command line for `tally.cpp`. Consumers therefore can't `#include "split.hpp"`.
- `cxx_std_17` is PUBLIC. `tally_test` has no standard requirement of its own, so it gets `-std=c++17`; `tally-cli` requires C++23 itself, and the higher one wins. `cxx_std_20` is PRIVATE and only affects the library itself.
- The warning options are PRIVATE and don't appear on consumers' command lines.

Dependencies themselves also come in three kinds. `target_link_libraries(a PUBLIC b)` means a's headers use b, and targets linking a also get b's usage requirements; `PRIVATE` means only a's `.cpp` files use b. Usage requirements propagate layer by layer along PUBLIC and INTERFACE dependencies; that is the dependency graph between targets.

`add_library(tally::tally ALIAS tally)` defines a namespaced alias, the same name that `find_package` yields after installation. When consumers write `tally::tally`, a typo is an error at configure time; when they write `tally`, a nonexistent target name is treated as the linker argument `-ltally` and only fails at link time.

### What happens when usage requirements are wrong

Suppose the library offers an optional statistics feature controlled by a macro switch, and the switch affects the class's members:

```cpp title="include/tally/tally.hpp (excerpt)"
class Counter {
  // ...
private:
  std::unordered_map<std::string, std::size_t> counts_;
#ifdef TALLY_STATS
  std::size_t words_seen_ = 0;
#endif
};
```

```cmake
target_compile_definitions(tally PRIVATE TALLY_STATS)   # wrong: should be PUBLIC
```

`TALLY_STATS` is defined when `tally.cpp` is compiled, and not when `tally_test.cpp` is. The `Counter` in the two translation units consists of different token sequences: on our test machine `sizeof(Counter)` is 48 on the library side and 40 on the test side.

[[basic.def.odr#16]] requires a class defined in several translation units to consist of the same sequence of tokens (¶16.4); a violation makes the program ill-formed, no diagnostic required {{ifndr}}. The practical result is that the test allocates only 40 bytes on the stack, while the library's `add_text` reads and writes `words_seen_` at offset 40, which no longer belongs to the object. An ASan build reports it immediately:

```text
==91378==ERROR: AddressSanitizer: stack-buffer-overflow on address 0x00016f85a528
READ of size 8 at 0x00016f85a528 thread T0
    #0 in tally::Counter::add_text(...) tally.cpp:13
    #1 in main tally_test.cpp:17
  This frame has 5 object(s):
    [32, 72) 'c' (line 16) <== Memory access at offset 72 overflows this variable
```

Built as RelWithDebInfo without sanitizers, the same program passed its test in our runs, and the command-line program's output was correct as well. Errors like this can lie dormant for a long time. After changing it to `PUBLIC`, `-DTALLY_STATS` appears on the test's command line and the problem goes away.

The rule is simple: macros tested by `#if` in headers, paths `#include`d by headers, and language features used by headers are all PUBLIC. The case of the same library built twice with different options is covered in [[toolchain/dependencies]].

## Setting the language standard

CMake has two ways to set the standard, with different meanings:

- `target_compile_features(t PUBLIC cxx_std_20)` declares that the target needs at least C++20. It is a usage requirement, can propagate to consumers, and is written into the exported package configuration.
- The `CMAKE_CXX_STANDARD` variable (or the target property `CXX_STANDARD`) sets a default standard for targets created afterwards. It doesn't propagate to consumers.

When both are present, CMake takes the highest version that satisfies all requirements. Trying each setting on an empty target on our test machine, the generated options are (compiler: Homebrew Clang 23):

| Setting | Generated option |
|---|---|
| Nothing set | None; the compiler default is used (`gnu++17` for Clang 23, with `__cplusplus` = `201703L`; `201402L` for AppleClang 21) |
| `CMAKE_CXX_STANDARD 23` | `-std=gnu++23` |
| `CMAKE_CXX_STANDARD 23` plus `CMAKE_CXX_EXTENSIONS OFF` | `-std=c++23` |
| `cxx_std_20` | `-std=gnu++20` |
| `CMAKE_CXX_STANDARD 17`, `EXTENSIONS OFF`, plus `cxx_std_20` | `-std=c++20` |
| `CMAKE_CXX_STANDARD 26`, `EXTENSIONS OFF`, plus `cxx_std_20` | `-std=c++26` |
| `cxx_std_17` (already met by the compiler default) | None |

The last row shows that when the minimum requirement is already met by the compiler's default mode, CMake adds no option. The compiler then uses its own default mode, GNU extensions included. If `CMAKE_CXX_EXTENSIONS OFF` is set, CMake adds `-std=c++17` to turn the extensions off, which is where the `tally_test` command line above came from (this is the behavior of policy CMP0128, from CMake 3.22).

`CMAKE_CXX_STANDARD_REQUIRED ON` makes CMake fail when the compiler doesn't support the version, instead of silently falling back to a lower one. It isn't needed when only `target_compile_features` is used; compile features are hard requirements in themselves.

### C++26

CMake 3.29's Clang module already knows the C++26 option, and `CMAKE_CXX_STANDARD 26` generates `-std=c++26`. But `cxx_std_26` can't be used; configuring fails:

```text
CMake Error at CMakeLists.txt:14 (target_compile_features):
  target_compile_features The compiler feature "cxx_std_26" is not known to
  CXX compiler

  "Clang"

  version 23.1.3.
```

So with this combination of versions, C++26 can only be requested through `CMAKE_CXX_STANDARD`, and C++26 can't be declared as a requirement passed on to consumers. Whether newer CMake versions support it is for the documentation of the version you use to say. Also, under `-std=c++26` Clang 23 defines `__cplusplus` as `202400L`, not the `202603L` in the current draft's [[cpp.predefined#1]], because its C++26 support is not yet final.

### Why turn off extensions

`gnu++NN` modes enable compiler extensions. [[intro.compliance.general#11]] allows implementations to have extensions provided they don't alter the behavior of any well-formed program. GNU mode doesn't meet that condition:

```cpp title="typeof.cpp" run ok
int typeof = 1;   // typeof is not a C++ keyword
int main() { return typeof - 1; }
```

This program is well-formed and compiles normally with `-std=c++23`. With `-std=gnu++23`, Clang treats `typeof` as a GNU keyword and reports `expected expression`. The predefined macros differ too: on our test machine `-std=c++23` defines `__STRICT_ANSI__` and `gnu++23` doesn't, and the latter adds two macros describing `__int128`. Some library headers choose different code paths based on `__STRICT_ANSI__`.

Setting `CMAKE_CXX_EXTENSIONS OFF` is recommended, to write portable code in standard mode. When an extension really is needed, enable it separately on the target that uses it.

!!! note "Several standard versions in one program"
    The project above compiles the library as C++20 and the test as C++17, then links them together. The standard has no such concept; to it, each `-std=` is a different implementation. libc++ and libstdc++ both try hard to let code compiled in different version modes be linked together, and doing this day to day is fine; but if a header changes a class's members based on `__cplusplus`, you get an ODR violation like the one in the previous section. The least troublesome approach is to unify the version with `CMAKE_CXX_STANDARD` in the top-level project, and have libraries declare only their minimum with `target_compile_features`.

## Build types

A **build type** is a preset group of optimization and debugging options. Single-configuration generators (Ninja, Makefile) pick one at configure time with `CMAKE_BUILD_TYPE`. The defaults with Clang on our test machine:

| `CMAKE_BUILD_TYPE` | Options added |
|---|---|
| `Debug` | `-g` |
| `Release` | `-O3 -DNDEBUG` |
| `RelWithDebInfo` | `-O2 -g -DNDEBUG` |
| `MinSizeRel` | `-Os -DNDEBUG` |
| Empty (the default) | None, i.e. `-O0` with no debug info |

An empty build type is rarely what you want; always give one explicitly in presets.

The effect of `-DNDEBUG` is specified by the standard: if `NDEBUG` is defined when `<cassert>` is included, `assert` expands to `((void)0)` ([[assertions.assert#1]]) and the condition isn't evaluated at all. So in a Release build, code with side effects must not be put inside `assert`.

`NDEBUG` also affects the ODR. If an inline function in a header uses `assert`, its token sequence after macro expansion differs between a TU with `NDEBUG` defined and one without, which also violates [[basic.def.odr#16]]. Within a single CMake build, all targets share one build type, so this mixture doesn't occur; it can occur when an installed library built as Release is linked with a program built as Debug.

### Multi-configuration generators

`Ninja Multi-Config` (and Visual Studio, Xcode) generate several configurations in one build directory, chosen at build time:

```text
$ cmake -S . -B bmc -G "Ninja Multi-Config"
$ cmake --build bmc --config Release -v
[2/6] clang++ -DCMAKE_INTDIR=\"Release\" -I<src>/include -I<src>/src -O3 -DNDEBUG
        -std=c++20 ... -o CMakeFiles/tally.dir/Release/src/tally.cpp.o -c <src>/src/tally.cpp
$ cmake --build bmc --config Debug
$ ls bmc/Debug bmc/Release
bmc/Debug:   libtally.a  tally-cli  tally_test
bmc/Release: libtally.a  tally-cli  tally_test
$ ctest --test-dir bmc -C Release
```

With a multi-configuration generator, the configure step doesn't yet know which configuration will be built, and `CMAKE_BUILD_TYPE` is empty. So a test such as `if(CMAKE_BUILD_TYPE STREQUAL "Debug")` is never true there. To vary settings by configuration, use the generator expression `$<CONFIG:Debug>`, which is correct with both kinds of generator.

## Generator expressions

A **generator expression** is an expression of the form `$<...>` that is not evaluated when `CMakeLists.txt` runs, but when build files are generated, separately for each target and each configuration. At that point the compiler, the configuration and the target's final properties are all known.

The warning settings above are an example:

```cmake
set(gcc_like "$<COMPILE_LANG_AND_ID:CXX,GNU,Clang,AppleClang>")
target_compile_options(tally PRIVATE
  "$<${gcc_like}:-Wall;-Wextra;-Wpedantic;-Wconversion>"
  "$<${msvc}:/W4;/permissive->")
```

`$<condition:value>` yields the value when the condition is 1, and an empty string otherwise. Multiple options in the value are separated by semicolons, and the whole expression is quoted so that spaces don't split it into several arguments. Commonly used ones:

| Expression | Meaning |
|---|---|
| `$<CXX_COMPILER_ID:Clang,AppleClang>` | Whether the compiler is one of these |
| `$<COMPILE_LANG_AND_ID:CXX,MSVC>` | A C++ source file is being compiled and the compiler is MSVC; more accurate than the previous one when the target mixes in C sources |
| `$<CONFIG:Debug>` | Whether the current configuration is Debug |
| `$<BUILD_INTERFACE:...>` / `$<INSTALL_INTERFACE:...>` | Used in the build tree / after installation; see below |
| `$<IF:condition,true-value,false-value>` | Choose one of two |

For example, enabling libc++'s hardening mode only in Debug:

```cmake
target_compile_definitions(tally PRIVATE
  $<$<CONFIG:Debug>:_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_DEBUG>)
```

## Warnings belong to targets

Put warning options on the target, as PRIVATE. There are three reasons:

1. Warnings are the project's own code-quality requirements and shouldn't be imposed on consumers. Consumers of the library may use a different compiler version, and the extra warnings of a newer version shouldn't break their build.
2. Third-party code (dependencies brought in with `add_subdirectory`) shouldn't be subjected to your warning level. Global settings can't achieve that.
3. Different targets can have different levels, for example a temporarily relaxed level for legacy code.

When a consumer includes `tally.hpp`, the code in the header is compiled with the consumer's warning options. For an installed library, CMake passes the imported target's include directories to the compiler with `-isystem` (visible in the output further below), and the compiler doesn't report warnings in system headers.

`-Werror` should even less be hard-coded in `CMakeLists.txt`. Since CMake 3.24 there is the variable `CMAKE_COMPILE_WARNING_AS_ERROR` (which initializes the target property `COMPILE_WARNING_AS_ERROR`), so whoever builds decides whether to enable it, for example only in CI. With it on, every compile command on our test machine gained `-Werror`; passing `--compile-no-warning-as-error` at configure time ignores it.

## Presets: CMakePresets.json

A sanitizer build needs a generator, a build directory, a build type and a string of options. Write them in documentation for everyone to type by hand, and sooner or later someone types them wrong. **Presets** store them in a `CMakePresets.json` in the repository:

```json title="CMakePresets.json"
{
  "version": 6,
  "configurePresets": [
    {
      "name": "base",
      "hidden": true,
      "generator": "Ninja",
      "binaryDir": "${sourceDir}/build/${presetName}",
      "cacheVariables": { "CMAKE_EXPORT_COMPILE_COMMANDS": "ON" }
    },
    {
      "name": "debug",
      "inherits": "base",
      "cacheVariables": { "CMAKE_BUILD_TYPE": "Debug" }
    },
    {
      "name": "release",
      "inherits": "base",
      "cacheVariables": { "CMAKE_BUILD_TYPE": "RelWithDebInfo" }
    },
    {
      "name": "asan",
      "inherits": "base",
      "cacheVariables": {
        "CMAKE_BUILD_TYPE": "Debug",
        "CMAKE_CXX_FLAGS": "-fsanitize=address,undefined -fno-omit-frame-pointer"
      }
    },
    {
      "name": "tsan",
      "inherits": "base",
      "cacheVariables": {
        "CMAKE_BUILD_TYPE": "Debug",
        "CMAKE_CXX_FLAGS": "-fsanitize=thread"
      }
    },
    {
      "name": "ci",
      "inherits": "base",
      "cacheVariables": {
        "CMAKE_BUILD_TYPE": "RelWithDebInfo",
        "CMAKE_COMPILE_WARNING_AS_ERROR": "ON"
      }
    }
  ],
  "buildPresets": [
    { "name": "debug", "configurePreset": "debug" },
    { "name": "asan",  "configurePreset": "asan" },
    { "name": "tsan",  "configurePreset": "tsan" },
    { "name": "ci",    "configurePreset": "ci" }
  ],
  "testPresets": [
    {
      "name": "asan",
      "configurePreset": "asan",
      "output": { "outputOnFailure": true },
      "environment": { "UBSAN_OPTIONS": "print_stacktrace=1:halt_on_error=1" }
    }
  ]
}
```

```text
$ cmake --preset asan
$ cmake --build --preset asan
$ ctest --preset asan
```

Some notes:

- Sanitizers are passed in through the cache variable `CMAKE_CXX_FLAGS`. This variable is meant for whoever builds; CMake puts it into both compile and link commands. On our test machine the `asan` preset's link command is `c++ -fsanitize=address,undefined -fno-omit-frame-pointer -g ... -o tally_test libtally.a`. Sanitizers must appear at link time as well, so that the corresponding runtime libraries are linked in.
- ASan and TSan can't be used together (Clang reports `'-fsanitize=address' not allowed with '-fsanitize=thread'`), so they are two presets with two build directories.
- UBSan continues running after a report by default; `halt_on_error=1` makes the test fail at the first error.
- The shared `CMakePresets.json` is committed to the repository; personal settings (such as the compiler path) go in `CMakeUserPresets.json`, which can inherit from the shared presets and is usually added to `.gitignore`.

```json title="CMakeUserPresets.json"
{
  "version": 6,
  "configurePresets": [
    {
      "name": "my-asan",
      "inherits": "asan",
      "cacheVariables": { "CMAKE_CXX_COMPILER": "/opt/homebrew/opt/llvm/bin/clang++" }
    }
  ],
  "buildPresets": [ { "name": "my-asan", "configurePreset": "my-asan" } ],
  "testPresets": [ { "name": "my-asan", "inherits": "asan", "configurePreset": "my-asan" } ]
}
```

!!! impl "On our test machine: one preset, two compilers"
    The shared `asan` preset doesn't specify a compiler, and on our test machine it picked AppleClang. We first set `ASAN_OPTIONS=detect_leaks=1` in the test preset, and the test failed outright with `AddressSanitizer: detect_leaks is not supported on this platform.`. Built with Homebrew Clang 23 instead (the `my-asan` above), the same option worked, and a deliberately leaking program was reported as `LeakSanitizer: detected memory leaks`. On macOS, whether leak detection is available depends on which toolchain's sanitizer runtime is used.

## compile_commands.json

Tools such as clangd and clang-tidy need to parse source files the way the compiler does, so they must know each file's compile options: include paths, macros, standard version. `CMAKE_EXPORT_COMPILE_COMMANDS ON` (already on in the `base` preset above) makes CMake write a `compile_commands.json` in the build directory, with one entry per TU. It only works with the Makefile and Ninja generators.

```json
{
  "directory": "<src>/build/debug",
  "command": "/opt/homebrew/opt/llvm/bin/clang++ -I<src>/include -I<src>/src -g -std=c++20 -arch arm64 -isysroot <sdk> -Wall -Wextra -Wpedantic -Wconversion -o CMakeFiles/tally.dir/src/tally.cpp.o -c <src>/src/tally.cpp",
  "file": "<src>/src/tally.cpp",
  "output": "CMakeFiles/tally.dir/src/tally.cpp.o"
}
```

Without it, tools can only guess:

```text
$ clang-tidy --checks='-*,bugprone-*,performance-*' tally/src/tally.cpp
Error while trying to load a compilation database:
Could not auto-detect compilation database for file "tally/src/tally.cpp"
...
Running without flags.
<src>/src/tally.cpp:1:10: error: 'tally/tally.hpp' file not found [clang-diagnostic-error]
$ clang-tidy -p build/debug --checks='-*,bugprone-*,performance-*' src/tally.cpp
(no diagnostics)
```

`-p` points at the directory containing `compile_commands.json`. clangd looks for this file in the source file's directory and its parents, and also in `build/` subdirectories of those. With a layout such as `build/<preset-name>`, you can create a symlink to it in the source root, or specify it in clangd's configuration file `.clangd` with `CompileFlags: CompilationDatabase: build/debug`.

CMake can also run clang-tidy as it compiles each file: with `CMAKE_CXX_CLANG_TIDY` set (for example `-DCMAKE_CXX_CLANG_TIDY="clang-tidy;--checks=-*,bugprone-*"`), every generated compile command is wrapped in `cmake -E __run_co_compile --tidy=...`. Choosing checks is covered in [[toolchain/static-analysis]].

## Installing and exporting

For other projects to use the library, you need to install the headers and library files, and export a CMake file describing the target, so that consumers can get the `tally::tally` target and all its usage requirements back with `find_package`:

```cmake title="CMakeLists.txt (continued)"
include(CMakePackageConfigHelpers)

install(TARGETS tally EXPORT tallyTargets)
install(DIRECTORY include/ DESTINATION ${CMAKE_INSTALL_INCLUDEDIR})
install(EXPORT tallyTargets
  NAMESPACE tally::
  DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/tally)

configure_package_config_file(cmake/tallyConfig.cmake.in
  ${CMAKE_CURRENT_BINARY_DIR}/tallyConfig.cmake
  INSTALL_DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/tally)
write_basic_package_version_file(
  ${CMAKE_CURRENT_BINARY_DIR}/tallyConfigVersion.cmake
  COMPATIBILITY SameMajorVersion)
install(FILES
  ${CMAKE_CURRENT_BINARY_DIR}/tallyConfig.cmake
  ${CMAKE_CURRENT_BINARY_DIR}/tallyConfigVersion.cmake
  DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/tally)
```

```cmake title="cmake/tallyConfig.cmake.in"
@PACKAGE_INIT@
include("${CMAKE_CURRENT_LIST_DIR}/tallyTargets.cmake")
check_required_components(tally)
```

After installation, the generated `tallyTargets.cmake` records exactly the PUBLIC part of the settings; the PRIVATE `src/`, `cxx_std_20` and warning options don't appear:

```cmake
add_library(tally::tally STATIC IMPORTED)

set_target_properties(tally::tally PROPERTIES
  INTERFACE_COMPILE_FEATURES "cxx_std_17"
  INTERFACE_INCLUDE_DIRECTORIES "${_IMPORT_PREFIX}/include"
)
```

The include directory differs between the build tree and the installed location, which is why it was given separately with `$<BUILD_INTERFACE:...>` and `$<INSTALL_INTERFACE:...>`. Only the latter is kept on export, with the path relative to the install prefix.

The consumer's `CMakeLists.txt`:

```cmake title="consumer/CMakeLists.txt"
cmake_minimum_required(VERSION 3.28)
project(consumer LANGUAGES CXX)
set(CMAKE_CXX_SCAN_FOR_MODULES OFF)

find_package(tally 0.1 CONFIG REQUIRED)

add_executable(wordfreq main.cpp)
target_compile_options(wordfreq PRIVATE -Wall -Wextra -Wconversion)
target_link_libraries(wordfreq PRIVATE tally::tally)
```

```text
$ cmake --install build/release --prefix ../prefix
$ cmake -S . -B b -G Ninja -DCMAKE_PREFIX_PATH=<dir>/prefix
$ cmake --build b -v
[1/2] clang++ -isystem <dir>/prefix/include -arch arm64 -isysroot <sdk>
        -Wall -Wextra -Wconversion -o CMakeFiles/wordfreq.dir/main.cpp.o -c <dir>/consumer/main.cpp
[2/2] clang++ ... CMakeFiles/wordfreq.dir/main.cpp.o -o wordfreq <dir>/prefix/lib/libtally.a
```

The include directory appears with `-isystem`; this consumer didn't turn off extensions, and `cxx_std_17` is met by Clang's default mode, so there is no `-std=` on the command line. Where dependencies come from and how to pin versions is covered in [[toolchain/dependencies]]; symbol visibility and ABI stability for shared libraries in [[toolchain/library-boundaries]].

## Modules

The build mechanics of modules (BMIs, dependency scanning, `FILE_SET CXX_MODULES`, the `.modmap` CMake generates) are covered in [[toolchain/modules-in-practice]]. Three things related to project organization are added here.

### Scanning happens even without modules

`cmake_minimum_required(VERSION 3.28)` enables policy CMP0155: for targets whose standard is C++20 or higher, CMake by default runs `clang-scan-deps` on every source file even if there are no module sources, in case they `import` something. Removing `set(CMAKE_CXX_SCAN_FOR_MODULES OFF)` from this project, the Debug build went from 6 steps to 12: one extra scan per TU and one extra `cmake_ninja_dyndep` per target. If a project doesn't use modules, turn scanning off.

### Installing a module interface

Add a module interface to `tally` that exports the class from the header:

```cpp title="src/tally.cppm"
module;
#include <tally/tally.hpp>
export module tally;
export namespace tally {
  using tally::Counter;
}
```

```cmake
target_sources(tally PUBLIC
  FILE_SET CXX_MODULES BASE_DIRS src FILES src/tally.cppm)

install(TARGETS tally EXPORT tallyTargets
  FILE_SET CXX_MODULES DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}/tally/modules)
install(EXPORT tallyTargets
  NAMESPACE tally::
  CXX_MODULES_DIRECTORY cxx-modules
  DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/tally)
```

What gets installed is the interface source `tally.cppm`, not a BMI. The export file gains a property mapping the module name to the source file:

```cmake
set_property(TARGET "tally::tally"
  PROPERTY IMPORTED_CXX_MODULES_RELEASE
    "tally=${_IMPORT_PREFIX}/include/tally/modules/tally.cppm"
)
```

When the consumer does `import tally;`, CMake creates an internal target in the consumer's build directory (named `tally__tally@synth_…` on our test machine) and recompiles the interface with the consumer's compiler to get a BMI. This matches the reason BMIs can't be distributed.

### BMI options must match

The options this internal target is compiled with determine whether the BMI can be imported. What we saw: the library exports a requirement of `cxx_std_20`, the consumer sets its own target to C++23 (whether with `CMAKE_CXX_STANDARD 23` or `cxx_std_23`), the internal target still compiles the interface with `-std=c++20`, and the import fails:

```text
error: C++23 was disabled in precompiled file 'CMakeFiles/tally__tally@synth_15c5226b978c.dir/d239af2f2b1f.bmi' but is currently enabled
error: precompiled file '...' cannot be loaded due to a configuration mismatch with the current compilation [-Wmodule-file-config-mismatch]
```

With the consumer changed to C++20, the build succeeded and ran correctly. This is behavior observed with CMake 3.29 and Clang 23; the conclusion is that, for now, a library exporting modules and its consumers had better agree on the same standard version.

## Common anti-patterns

| Pattern | Problem | Use instead |
|---|---|---|
| `include_directories(...)`, `add_definitions(...)`, `add_compile_options(...)` | Applies to every target in the current directory and below, including third-party code brought in with `add_subdirectory`; not a usage requirement, not passed to consumers, not exported | `target_include_directories`, `target_compile_definitions`, `target_compile_options`, with explicit keywords |
| `set(CMAKE_CXX_FLAGS ...)` in `CMakeLists.txt` | Overrides options passed in by whoever builds; applies to all targets; not exported | What the project needs goes on targets; the builder's choices go in presets |
| `file(GLOB SRCS src/*.cpp)` | New files don't trigger reconfiguration, and the build silently misses files | List source files explicitly |
| `target_link_libraries(app tally)` without a keyword | The old signature; its propagation rules differ from the keyword form, and the two forms can't be mixed on the same target | Always write `PRIVATE` / `PUBLIC` / `INTERFACE` |
| `if(CMAKE_BUILD_TYPE STREQUAL "Debug")` | `CMAKE_BUILD_TYPE` is empty with multi-configuration generators | `$<CONFIG:Debug>` |
| Writing `-std=c++20` directly in options | Conflicts with the `-std=` CMake generates; the last one wins | `target_compile_features` or `CMAKE_CXX_STANDARD` |

The last two kinds of problem can be seen directly. The `CMakeLists.txt` below sets `CMAKE_CXX_FLAGS` in the project, while whoever builds passes `-DCMAKE_CXX_FLAGS=-fsanitize=address` on the command line:

```cmake
set(CMAKE_CXX_FLAGS "-Wall -std=c++17")
add_executable(g src/main.cpp src/helper.cpp)
target_compile_features(g PRIVATE cxx_std_20)
```

```text
[2/3] c++ -Wall -std=c++17 -std=gnu++20 -arch arm64 -isysroot <sdk> ... -c <src>/src/main.cpp
```

The ordinary variable defined by `set` hides the cache variable of the same name, and the `-fsanitize=address` the builder asked for vanishes without any notice. There are two `-std=` options on the command line, and the later `gnu++20` wins.

The problem with `file(GLOB)`:

```text
$ echo 'int helper() { return 1; }' > src/helper.cpp
$ cmake --build b
ninja: no work to do.
```

`file(GLOB)` is evaluated only once, at configure time, and new files are only picked up at the next reconfigure. With `CONFIGURE_DEPENDS` added, every build on our test machine first ran a `Re-checking globbed directories...` step, and on detecting a change printed `-- GLOB mismatch!` and reconfigured. CMake's documentation notes that this option isn't reliable with every generator, and every build pays for the check. Listing source files explicitly has another benefit: code review shows which translation unit was added.

## Questions

!!! question "1"
    `tally`'s header is unchanged; only `tally.cpp` adds `#include <fmt/format.h>` and calls fmt. Which keyword should `target_link_libraries(tally ??? fmt::fmt)` use? What if the header later also adds `#include <fmt/format.h>`?

<details markdown="1">
<summary>Answer</summary>

When only the `.cpp` uses it, use `PRIVATE`: consumers don't need fmt's include path when compiling, so they shouldn't see it. `tally` is a static library, though, so linking consumers still needs fmt's library file; CMake automatically records PRIVATE link dependencies in the export file as `$<LINK_ONLY:...>`, passing on linking but not compile settings.

Once the header includes it too, change it to `PUBLIC`. Otherwise consumers' TUs can't find `<fmt/format.h>`; the more insidious case is a consumer that happens to find a different version of the fmt headers elsewhere, not the one the library was compiled with, which is a violation of [[basic.def.odr#16]].
</details>

!!! question "2"
    A library's header uses `#if __cplusplus >= 202002L` to decide whether to give a class a `std::span` member. The library is built with `target_compile_features(lib PUBLIC cxx_std_17)`, and the project's `CMAKE_CXX_STANDARD` is 20. Is there a problem?

<details markdown="1">
<summary>Answer</summary>

Not within a single CMake build: `CMAKE_CXX_STANDARD 20` is the default for all targets, so both the library and its consumers are compiled as C++20, and `cxx_std_17` is only a floor.

The problem arises once the library is built and installed separately. The library is compiled as C++17 and a consumer as C++20; `__cplusplus` differs between the two sides, so the class definitions differ, an ODR violation with no diagnostic required ([[basic.def.odr#16]]). CMake only propagates minimum requirements and can't require consumers to use the same version as the library. A header shouldn't make a class's layout depend on `__cplusplus`; if it must, the only option is to document that the library and its consumers must be built with the same standard version.
</details>

!!! question "3"
    Why is putting sanitizer options in a preset's `CMAKE_CXX_FLAGS` reasonable, while `set(CMAKE_CXX_FLAGS ...)` in `CMakeLists.txt` is an anti-pattern?

<details markdown="1">
<summary>Answer</summary>

`CMAKE_CXX_FLAGS` is a cache variable, an interface meant for whoever builds: for the same source, one person wants an ASan build, another a TSan build, another a plain build. That is a choice of build environment, not a property of the project. A preset merely records the builder's choice.

`set`ting an ordinary variable of the same name in `CMakeLists.txt` means the project decides for the builder, and it hides the value the builder passed in; that is how `-fsanitize=address` vanished in the experiment above. Options the project itself really needs should be set on targets.
</details>

## Summary

| Topic | Key points |
|---|---|
| Targets and usage requirements | PRIVATE only for the target, INTERFACE only for consumers, PUBLIC for both; everything a header depends on is PUBLIC |
| The cost of getting it wrong | With a header macro set PRIVATE, the library and its consumers see different class definitions, IFNDR; ASan reports `stack-buffer-overflow`, and without sanitizers the test passes as usual |
| Language standard | `cxx_std_NN` is a propagated floor, `CMAKE_CXX_STANDARD` a default; `CMAKE_CXX_EXTENSIONS OFF` gives `-std=c++NN`; CMake 3.29 doesn't know `cxx_std_26`, while `CMAKE_CXX_STANDARD 26` works |
| Build types | Debug `-g`, Release `-O3 -DNDEBUG`, RelWithDebInfo `-O2 -g -DNDEBUG`; the empty type has neither optimization nor debug info; use `$<CONFIG:...>` with multi-configuration generators |
| Warnings | A target's PRIVATE options; leave `-Werror` to `CMAKE_COMPILE_WARNING_AS_ERROR` |
| Presets | Generator, build directory, build type and sanitizers go in `CMakePresets.json`; personal settings in `CMakeUserPresets.json` |
| Tools | `CMAKE_EXPORT_COMPILE_COMMANDS ON`; point clang-tidy at the build directory with `-p` |
| Installation | `install(TARGETS … EXPORT)` plus `install(EXPORT … NAMESPACE)`, and consumers use `find_package(… CONFIG)`; only usage requirements are exported |
| Modules | C++20 targets are scanned by default, turn it off if you don't use modules; the interface source is installed and consumers rebuild the BMI, so standard versions must match |
