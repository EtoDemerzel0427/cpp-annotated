---
title: Managing dependencies
summary: "How to bring third-party libraries into a C++ project: why there is no common package format and why compile options must match, how two versions of the same library in one program cause an ODR violation, how system packages, FetchContent, vcpkg, Conan, submodules and vendoring each work, and pinning versions, verifying hashes and choosing by project type."
group: Engineering practice
tags: toolchain, dependencies, package management, ODR, ABI, CMake, build
updated: 2026-10-19
---

!!! tldr
    - The standard only says a program is linked from translation units and library components; it doesn't say how libraries are packaged or found. Every package manager has made its own conventions in that gap.
    - A precompiled library can only be used with code compiled against the same standard library and the same ABI-relevant options. So C++ dependency management isn't just downloading the right version; it is also building it the right way.
    - Two versions of the same library in one program means two different definitions of the same inline function or class, an ODR violation with no diagnostic required. In our experiments the result depended on link order and optimization level: wrong values, a crash, or correct output by luck.
    - Building from source together (FetchContent, submodules, vendoring) makes consistent options easiest; vcpkg and Conan add version resolution and binary caching on top; system packages are the least effort, but the distribution decides versions and options.
    - Whichever you use, pin exact versions and verify the hashes of what you download.

## The standard doesn't know about packages

Only two places in the standard relate to dependencies. Phase 8 of translation ([[lex.phases#1]]) says translated translation units (TUs) are combined, and library components are linked to satisfy external references to entities not defined in the current TU. Where `#include <x.h>` looks for headers is implementation-defined ([[cpp.include#1]]).

Beyond that, what a library is, where its headers and binaries live, which other libraries it depends on, and what options it was compiled with are none of the standard's business. Python has wheels and Rust has crates, package formats defined by the language itself. C++ has no such format, so several mutually incompatible conventions have appeared:

| Convention | How it describes a library | Used by |
|---|---|---|
| pkg-config `.pc` files | A set of compile and link arguments | Linux distributions, Homebrew, many C libraries |
| CMake package config files (`<name>Config.cmake`) | CMake imported targets, with header paths, library files, dependencies and compile requirements | Libraries built with CMake |
| vcpkg ports, Conan recipes | A script for building from source, plus version metadata | The respective package managers |

Our test machine has Homebrew's zstd installed, which provides both kinds of description. The `.pc` file is just a few lines of arguments:

```text
$ cat /opt/homebrew/lib/pkgconfig/libzstd.pc
prefix=/opt/homebrew/opt/zstd
exec_prefix=${prefix}
includedir=${prefix}/include
libdir=${exec_prefix}/lib

Name: zstd
Description: fast lossless compression algorithm library
URL: https://facebook.github.io/zstd/
Version: 1.5.7
Libs: -L${libdir} -lzstd
Libs.private:
Cflags: -I${includedir}
```

Under `/opt/homebrew/lib/cmake/zstd/` are CMake package config files defining imported targets such as `zstd::libzstd_shared` and `zstd::libzstd_static`. Neither description records which compiler, which standard library or what options the library was compiled with, which is exactly the information C++ needs most.

## Compile options are part of the interface

The binary of a precompiled C++ library is tied to many of the options it was compiled with. These binary-level conventions are collectively called the **ABI** (application binary interface): class layout, how functions pass arguments, how symbol names are mangled, how exceptions propagate. Mangled names are covered in [[toolchain/name-mangling]] and class layout in [[toolchain/object-layout-and-vtables]].

The ABI of a C library is relatively stable, and changing compile options generally has no effect. A C++ library's headers contain lots of inline functions and templates, which are instantiated in the consumer's TUs and mixed with the library's binary. Whenever the two sides understand the same type differently, things go wrong.

| Option or configuration | What happens when they differ |
|---|---|
| Standard library implementation (libc++ / libstdc++ / MSVC STL) | The layout and mangled names of types such as `std::string` all differ. libc++ puts its entities in `std::__1`, so mixing usually shows up as link errors |
| `-std=` | The library's headers may use `__cplusplus` to choose different members or type aliases, so the two sides see different class definitions |
| Exceptions and RTTI (`-fno-exceptions`, `-fno-rtti`) | An exception passing through frames without unwind information terminates the program; `dynamic_cast` and `typeid` can't find type information |
| Debug iterators | libstdc++'s `_GLIBCXX_DEBUG`, MSVC's `_ITERATOR_DEBUG_LEVEL` and libc++'s bounded-iterator ABI all change the layout of containers or iterators |
| Sanitizers | Some require the whole program to be built with them (such as TSan and MSan); otherwise they miss errors or report false positives |
| The library's own configuration macros | Members decided by `#ifdef` in the header: if the definitions differ between the two sides, they are two different classes |

We made two direct observations. First, libc++'s bounded iterators are an ABI configuration (macros such as `_LIBCPP_ABI_BOUNDED_ITERATORS_IN_VECTOR`; per libc++'s documentation, such ABI macros should be chosen uniformly when building libc++ itself, and we defined one by hand only to observe the layout). With it on, `sizeof(std::vector<int>::iterator)` goes from 8 bytes to 24; a hardening mode such as `_LIBCPP_HARDENING_MODE_DEBUG` doesn't change the layout, and it stays 8 bytes.

Second, a library compiled with default options throws an exception, which passes through an intermediate TU compiled with `-fno-exceptions` and is caught by a `catch (...)` in `main`. With everything compiled with default options, the output is `cleanup`, `caught`; with the intermediate TU switched to `-fno-exceptions`, the program terminates with `libc++abi: terminating due to uncaught exception`, and the local object is not destroyed. The mechanism is described in [[toolchain/exception-implementation]].

What each of these options means and how to avoid them at a library's interface is covered in [[toolchain/library-boundaries]]. For dependency management, the conclusion is a single rule: **all C++ code in one program, including all dependencies, should be built with the same compiler, the same standard library and the same set of ABI-relevant options.**

!!! impl "An example from our test machine"
    When building directly with Homebrew LLVM's clang++, the headers come from Homebrew's libc++, but `otool -L` shows the executable linking at run time against `/usr/lib/libc++.1.dylib`, the system's own libc++. The examples here all run fine, but the headers and the runtime library come from two different versions of libc++. As soon as the newer headers refer to a symbol the system library lacks, linking or loading fails.

## Two versions in one program

This most easily happens when a library is pulled in indirectly by several dependencies: `liba` bundles version 1.0 of `mini`, `libb` bundles version 2.0, and the application links both `liba` and `libb`. Here it is reduced to a minimum; `mini` is a header-only library, and version 2.0 adds a member to `Options`:

<div class="compare" markdown="1">

```cpp title="v1/mini/mini.hpp"
#pragma once
namespace mini {
struct Options {
  int level;
};
inline Options defaults() {
  return {1};
}
inline const char* version() {
  return "1.0";
}
}
```

```cpp title="v2/mini/mini.hpp"
#pragma once
namespace mini {
struct Options {
  int level;
  long cache[4];
};
inline Options defaults() {
  return {2, {64, 64, 64, 64}};
}
inline const char* version() {
  return "2.0";
}
}
```

</div>

`a.cpp` stands for `liba` and is compiled with `-Iv1`; `b.cpp` stands for `libb` and is compiled with `-Iv2`. Their sources differ only in names:

```cpp title="a.cpp"
#include <mini/mini.hpp>
#include <cstdio>
void use_a() {
  mini::Options o = mini::defaults();
  std::printf("a: built with 1.0, sees %s, level=%d\n",
              mini::version(), o.level);
}
```

```cpp title="b.cpp"
#include <mini/mini.hpp>
#include <cstdio>
void use_b() {
  mini::Options o = mini::defaults();
  std::printf("b: built with 2.0, sees %s, level=%d\n",
              mini::version(), o.level);
}
```

```cpp title="main.cpp" ifndr
void use_a();
void use_b();
int main() { use_a(); use_b(); }   // together with a.cpp and b.cpp: IFNDR
```

Each TU on its own is fine, and `-Wall -Wextra -pedantic` gives no warnings at all. The results on our test machine:

```text
$ clang++ -std=c++2c -O0 -Iv1 -c a.cpp
$ clang++ -std=c++2c -O0 -Iv2 -c b.cpp
$ clang++ -std=c++2c -O0 -c main.cpp
$ clang++ main.o a.o b.o -o app_ab && ./app_ab
a: built with 1.0, sees 1.0, level=1
b: built with 2.0, sees 1.0, level=73039476
$ clang++ main.o b.o a.o -o app_ba && ./app_ba
Bus error: 10
```

At `-O0` the inline functions aren't inlined, and every object file has a copy of `mini::defaults()` and `mini::version()`, which are weak definitions on Mach-O. The linker deduplicates by name only and keeps one copy (see [[toolchain/linking-and-symbols]]), but the two copies have different contents:

- With `a.o` first, `b` calls the 1.0 `defaults()`. Version 1.0 returns just an `int` in a register; `b` thinks it returns a 40-byte struct and reads a never-written value from its own stack.
- With `b.o` first, `a` calls version 2.0. Version 2.0 writes 40 bytes to an address supplied by the caller, but `a`, following the 1.0 convention, never supplied one, so it writes to a random address and the process gets SIGBUS.

Compiling `a.cpp` and `b.cpp` with `-O2` instead, both calls are inlined into their own TUs, the object files no longer contain `mini::` symbols, and the output becomes correct:

```text
a: built with 1.0, sees 1.0, level=1
b: built with 2.0, sees 2.0, level=2
```

Packaging the two TUs as static libraries and linking them, the system linker on our test machine picked the version from `a.o` whether we wrote `-la -lb` or `-lb -la`. The same source gives results depending on link order, how it is linked and the optimization level. Under AddressSanitizer, the crash report points at `mini::defaults()+0x70` with the stack `use_a → mini::defaults`, giving no hint that the problem lies in two versions of a header.

### What the standard says

`mini::Options`, `mini::defaults` and `mini::version` are all **definable items**, which may each have one definition in several TUs provided the definitions meet a series of requirements in [[basic.def.odr#16]], the first of which (¶16.4) is that they consist of the same sequence of tokens. Two versions of a header clearly don't.

!!! std
    if the definitions in different translation units do not satisfy the following requirements, the program is ill-formed; a diagnostic is required only if the definable item is attached to a named module …

So such a program is {{ifndr}}: invalid, but neither the compiler nor the linker is obliged to notice. All the seemingly random results above are permitted by this rule. If `mini` were a module and the earlier definition were reachable at the later one, the implementation would have to diagnose it; ordinary headers aren't covered.

### How to avoid it

The first and most fundamental rule: **each library may have only one version in a program**. That is why package managers do version resolution: they pick one version of each library across the whole dependency graph and build every library that depends on it against that version. A library that bundles a copy of a third-party library's source (vendoring, below) bypasses this resolution, so library authors shouldn't put their dependencies' source as is into their own public headers.

The second is something library authors can do: encode the version into symbol names. The usual tool is an **inline namespace** ([[g:inline-namespace]]). Members of an inline namespace can be used as if they were members of the enclosing namespace ([[namespace.def#6]]), but they belong to a different namespace and have different mangled names. libc++'s `std::__1` works this way.

```cpp title="v2/mini/mini.hpp (with a version namespace)" ok
#pragma once
namespace mini {
inline namespace v2 {
struct Options { int level; long cache[4]; };
inline Options defaults() { return {2, {64, 64, 64, 64}}; }
inline const char* version() { return "2.0"; }
}
}
```

With version 1.0 likewise wrapped in `inline namespace v1`, and without changing a single character of the consumers' source, the two versions become different entities, and the program no longer violates the ODR:

```text
$ llvm-nm a.o b.o | grep mini
0000000000000058 T __ZN4mini2v17versionEv
0000000000000040 T __ZN4mini2v18defaultsEv
0000000000000064 T __ZN4mini2v27versionEv
0000000000000040 T __ZN4mini2v28defaultsEv
$ ./app_ba
a: built with 1.0, sees 1.0, level=1
b: built with 2.0, sees 2.0, level=2
```

When types from the two versions really are passed between libraries, the error also moves from run time to link time. If `liba` defines `int level_of(const mini::Options&)` with 1.0, a caller compiled with 2.0 fails to link:

```text
Undefined symbols for architecture arm64:
  "level_of(mini::v2::Options const&)", referenced from:
      _main in nb2.o
```

This doesn't make the two versions interoperate; it only turns a silent error into a visible one.

## Header-only libraries and compiled libraries

| | Header-only | Needs compiling |
|---|---|---|
| How it is brought in | Add a header search path | Also link a `.a`, `.so`/`.dylib`/`.dll` |
| Options it is compiled with | The consumer's, compiled again in each TU | The options used when building the library, which must match the consumer's |
| Compile time | Paid by every TU that includes it | Paid once |
| ODR risk | Yes: it is all inline functions and templates; the previous section's example was header-only | Yes: the library's internal inline functions may differ from what the consumer sees |
| Typical examples | Most Boost libraries, nlohmann/json, Eigen | zstd, OpenSSL, Boost.Filesystem |

A header-only library avoids the problem of matching options, since it is always compiled with the consumer's options. But it doesn't avoid version conflicts: whenever two copies of the headers enter the same program, you are in the previous section's situation.

Some libraries offer both. fmt compiles as a library by default and becomes header-only when `FMT_HEADER_ONLY` is defined; spdlog can be used by including headers only, or compiled as a library (in which case `SPDLOG_COMPILED_LIB` is defined). When choosing, note that only one way can be used in a program; otherwise it is again two different definitions of the same entity.

## Ways to bring in a dependency

The commands below were run on our test machine: CMake 3.29.3, Ninja, Homebrew 7.0.9, git. vcpkg, Conan and pkg-config weren't installed, so for those only usage is described, without run results. CMake usage itself is covered in [[toolchain/cmake]].

### System package managers: brew, apt

Install with `brew install zstd` or `apt install libzstd-dev`, then find it in CMake:

```cmake
find_package(zstd 1.5 REQUIRED CONFIG)
target_link_libraries(app PRIVATE zstd::libzstd_shared)
```

Projects not using CMake can get the arguments from the `.pc` file above with `pkg-config --cflags --libs libzstd`.

The advantage is that nothing needs building. The disadvantage is that the distribution decides the version, and the options too. C++ libraries in Linux distributions are generally built with the distribution's default GCC and libstdc++, so if your project switches to Clang + libc++ you can't use them directly. Homebrew's libraries are built with Apple's toolchain, which is not the same standard library as the libc++ of Homebrew LLVM on our test machine (see the impl note above); zstd is a C library and so isn't affected.

What `find_package` finds isn't necessarily the copy you think. On the first configure on our test machine, CMake picked the zstd bundled with Anaconda:

```text
$ grep zstd_DIR build/CMakeCache.txt
zstd_DIR:PATH=/opt/homebrew/anaconda3/lib/cmake/zstd
$ ./build/app
fmt 120100; zstd header 1.5.5, runtime 1.5.5
```

The reason is that `/opt/homebrew/anaconda3/bin` comes before `/opt/homebrew/bin` on `PATH`, and CMake derives a prefix from each `bin` directory on `PATH` to search for package config files. Only after specifying the prefix explicitly do we get Homebrew's version:

```text
$ cmake -S . -B build2 -G Ninja -DCMAKE_PREFIX_PATH=/opt/homebrew
$ grep zstd_DIR build2/CMakeCache.txt
zstd_DIR:PATH=/opt/homebrew/lib/cmake/zstd
$ ./build2/app
fmt 120100; zstd header 1.5.7, runtime 1.5.7
```

When depending on system packages, the build log should show which path and version each dependency resolved to, and CI should pin its base image.

### Building from source together: add_subdirectory and FetchContent

Put the dependency's source next to the project and add it to the build with `add_subdirectory(third_party/fmt)`, and the dependency becomes an ordinary target in the project. `FetchContent` does the same thing, except that the source is downloaded at configure time:

```cmake title="CMakeLists.txt"
cmake_minimum_required(VERSION 3.24)
project(deps_demo LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

include(FetchContent)
FetchContent_Declare(fmt
  URL      https://github.com/fmtlib/fmt/releases/download/12.1.0/fmt-12.1.0.zip
  URL_HASH SHA256=695fd197fa5aff8fc67b5f2bbc110490a875cdf7a41686ac8512fb480fa8ada7
  FIND_PACKAGE_ARGS 12)
FetchContent_MakeAvailable(fmt)

find_package(zstd 1.5 REQUIRED CONFIG)

add_executable(app main.cpp)
target_link_libraries(app PRIVATE fmt::fmt zstd::libzstd_shared)
```

```cpp title="main.cpp" ok
#include <fmt/format.h>
#include <zstd.h>
int main() {
  fmt::print("fmt {}; zstd header {}, runtime {}\n",
             FMT_VERSION, ZSTD_VERSION_STRING, ZSTD_versionString());
}
```

`FIND_PACKAGE_ARGS` (CMake 3.24 and later) means try `find_package(fmt 12)` first and download only if that fails. fmt wasn't installed on our test machine, so it was downloaded:

```text
$ cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_PREFIX_PATH=/opt/homebrew
-- {fmt} version: 12.1.0
-- Configuring done (2.1s)
$ cmake --build build
[4/5] Linking CXX static library _deps/fmt-build/libfmt.a
[5/5] Linking CXX executable app
```

The benefit of building from source is clearest in Ninja's commands. fmt's source files and the project's own source files use the same compiler and the same options:

```text
$ ninja -C build -t commands | grep -E 'format.cc|main.cpp'
clang++ ... -O3 -DNDEBUG -std=gnu++23 ... -c _deps/fmt-src/src/format.cc
clang++ ... -O3 -DNDEBUG -std=gnu++23 ... -c main.cpp
```

The problems in the earlier table disappear automatically: add `-fsanitize=address` to the project or switch standard libraries, and fmt is rebuilt to match. The cost is that every developer and every fresh CI build has to compile all dependencies, which is slow for large ones (LLVM, all of Boost, gRPC).

Pinning the version is the consumer's responsibility. The `URL_HASH` above pins the download to one exact archive; with `GIT_REPOSITORY`, `GIT_TAG` should be a commit hash rather than a branch name, because branches move, and tags can be repointed too.

Even with the version pinned, a dependency can still break when the toolchain changes. We originally used fmt 11.1.4, whose `format.h` calls `malloc` and `free` without including `<cstdlib>`, having relied on other standard headers to include it indirectly. Clang 23's libc++ no longer includes it indirectly, so there is an error at the template definition:

```text
fmt/format.h:752:35: error: call to function 'free' that is neither visible in the
template definition nor found by argument-dependent lookup
```

This is the two-phase lookup rule ([[topics/two-phase-lookup]]): non-dependent names in a template definition are looked up at the point of definition. When upgrading the compiler and standard library, verify the dependencies too; fmt 12.1.0 compiles fine on our test machine.

### git submodule

A submodule records a particular commit of another repository in this repository:

```bash
git submodule add https://github.com/fmtlib/fmt.git third_party/fmt
git -C third_party/fmt checkout 12.1.0
git add third_party/fmt .gitmodules
```

This repository records fmt's commit hash, not the tag name, so the version is fixed. In CMake it is brought in with `add_subdirectory(third_party/fmt)`, with the same effect as FetchContent.

The problems with submodules are mainly in using them: cloning needs `--recurse-submodules`, and after switching branches you need `git submodule update`, or the submodule stays at the old commit. There is no version resolution between dependencies, so if two submodules each bring the same library, you are in the previous section's situation.

### Vendoring

**Vendoring** means copying a dependency's source directly into your own repository (often under `third_party/` or `vendor/`) and committing it as ordinary files. It needs no network, builds most reliably, and code review sees every line of change in the dependency.

The cost is that upgrades are manual, and it is very easy to tweak a few lines of the copied source in passing and never be able to merge back to upstream again. Keep a note file in the directory stating the upstream address, version or commit hash, license and local modifications.

### vcpkg

vcpkg is a source package manager maintained by Microsoft: each library corresponds to a port, a script for building it from source, which is built locally with the chosen configuration and installed. vcpkg wasn't installed on our test machine.

In **manifest mode**, the project root has a `vcpkg.json`:

```json title="vcpkg.json"
{
  "dependencies": [
    "fmt",
    { "name": "zstd", "version>=": "1.5.6" }
  ],
  "builtin-baseline": "<a commit hash of the vcpkg repository>",
  "overrides": [
    { "name": "fmt", "version": "11.0.2" }
  ]
}
```

`builtin-baseline` points at a commit of the vcpkg ports repository and decides the default version of each library. `version>=` gives a lower bound, and `overrides` forces a version. vcpkg picks only one version of each library: the lowest version that satisfies all lower bounds (the baseline itself is also a lower bound), so two versions never appear in one program.

Pass vcpkg's toolchain file when configuring CMake, and `find_package` finds the libraries vcpkg built:

```bash
cmake -S . -B build -DCMAKE_TOOLCHAIN_FILE="$VCPKG_ROOT/scripts/buildsystems/vcpkg.cmake"
```

A **triplet** describes the target platform and build style, such as `arm64-osx`, `x64-linux` or `x64-windows-static`. A custom triplet is a CMake file setting `VCPKG_TARGET_ARCHITECTURE`, `VCPKG_LIBRARY_LINKAGE` (static or dynamic), `VCPKG_CRT_LINKAGE`, `VCPKG_CXX_FLAGS` and so on; in effect it writes the options from the earlier table into one configuration, and every dependency is built according to it.

**Binary caching** is on by default. vcpkg computes a hash for each package, covering the port files, the triplet, the compiler version and the hashes of all dependencies, and rebuilds if any of them changes. The cache location is configured with the environment variable `VCPKG_BINARY_SOURCES` and can point at a local directory or storage shared by a team, which is how CI machines share build results.

### Conan

Conan is another cross-platform C/C++ package manager, with recipes written in Python; it too can build from source or download precompiled binaries. Conan wasn't installed on our test machine; the following describes Conan 2 usage.

```ini title="conanfile.txt"
[requires]
fmt/11.0.2
zstd/1.5.6

[generators]
CMakeDeps
CMakeToolchain

[layout]
cmake_layout
```

Conan describes the build configuration with a **profile**; `conan profile detect` generates a default profile from the local compiler:

```ini title="profile"
[settings]
os=Macos
arch=armv8
build_type=Release
compiler=apple-clang
compiler.version=17
compiler.libcxx=libc++
compiler.cppstd=20
```

The `settings` in a profile go into the package ID computed for each binary package. Change `compiler.libcxx` or `compiler.cppstd` and no matching precompiled package will be found; `--build=missing` builds it from source. This is how Conan handles consistent options: different options mean different binaries.

```bash
conan install . --output-folder=build --build=missing
conan lock create .                          # generates conan.lock
conan install . --lockfile=conan.lock ...    # later installs follow the lockfile
```

A **lockfile** records the exact version and recipe revision each package in the dependency graph resolved to. Version ranges (such as `fmt/[>=11 <12]`) let dependencies update automatically, and the lockfile makes the same commit resolve to the same result on any machine.

## Reproducibility: pinning versions

A reproducible build requires the same commit to get the same dependencies at any time on any machine. What each approach does:

| Approach | What is pinned | Where it is written |
|---|---|---|
| System packages | Distribution or image version | CI base image, Dockerfile; Homebrew can barely be pinned |
| FetchContent | `URL` + `URL_HASH`, or a commit hash in `GIT_TAG` | `CMakeLists.txt` |
| git submodule | Commit hash | The parent repository's tree object, recorded automatically |
| Vendoring | The source itself | Files in the repository |
| vcpkg | `builtin-baseline`, `overrides` | `vcpkg.json`, `vcpkg-configuration.json` |
| Conan | Lockfile | `conan.lock` |

Dependency versions are only half of it. The compiler version, standard library version and CMake version affect the result just as much; the fmt 11.1.4 example above only broke after the standard library changed. CI should pin toolchain versions and print them in the build log.

FetchContent has two more switches related to reproducibility: `FETCHCONTENT_FULLY_DISCONNECTED=ON` forbids network access at configure time and uses only existing sources; `FETCHCONTENT_SOURCE_DIR_<name>` makes one dependency use a local directory instead, which is handy for debugging a dependency without changing `CMakeLists.txt`.

## Supply chain: verifying what you download

Code fetched from the network is compiled and executed on your machine, and the build scripts are executed too. The basic line of defense is verifying hashes: record an exact hash and reject any download that doesn't match. Change one hex digit of the `URL_HASH` above, and CMake refuses to use the download:

```text
-- SHA256 hash of
    .../fmt-subbuild/fmt-populate-prefix/src/fmt-12.1.0.zip
  does not match expected value
    expected: '695ed197fa5aff8fc67b5f2bbc110490a875cdf7a41686ac8512fb480fa8ada7'
      actual: '695fd197fa5aff8fc67b5f2bbc110490a875cdf7a41686ac8512fb480fa8ada7'
-- Hash mismatch, removing...
CMake Error at .../FetchContent.cmake:1714 (message):
  Build step for fmt failed: 1
```

The corresponding mechanisms elsewhere: a git commit hash is itself a hash of the content; each vcpkg port records the SHA512 of its source archive in `portfile.cmake`; a Conan recipe revision is a hash of the recipe's content, which the lockfile pins too.

Other recommendations:

- Confirm the hash against a trusted source when the dependency is first introduced (for example against the hash published on the release page, or by reviewing the source yourself); after that it only guarantees the content hasn't changed.
- Review dependency upgrades like ordinary code changes, glancing at the changelog and the diff.
- In larger teams, host dependencies on an internal mirror or private repository (vcpkg custom registries, Conan private remotes), so builds don't depend on the availability of external sites.
- When a software bill of materials (SBOM) is needed, vcpkg generates an SPDX file for each installed package; with other approaches you have to compile the dependency list yourself.

## Licenses

Bringing in a dependency also brings in its license obligations. Permissive licenses such as MIT, BSD, Apache-2.0 and the Boost Software License generally only require keeping the copyright and license notices; LGPL has extra requirements for static linking (users must be able to replace the library), and GPL requires the whole program to be released under a compatible license. Dependencies of dependencies count too. List the licenses of all dependencies before distributing binaries, and consult legal counsel when in doubt.

## How to choose

These are recommendations, with the reasons in the columns; they aren't the only answers:

| Project type | Recommendation | Reason |
|---|---|---|
| Small tools, examples, coursework | FetchContent, with a pinned `URL_HASH` or commit hash | No extra tools needed; few dependencies, so building from source takes acceptable time |
| Open-source libraries | Declare dependencies only with `find_package` and let consumers decide how to provide them; test dependencies can use FetchContent | A library shouldn't choose versions for its consumers, still less bring dependency sources into public headers |
| Medium to large applications with many dependencies | vcpkg manifest mode or Conan, with locking and binary caching | Version resolution and caching are needed; maintaining dozens of FetchContent declarations by hand isn't practical |
| Large internal company codebases | Vendoring or a monorepo, with a uniform build system | Full control over toolchain and options; all code reviewed and built together |
| Software targeting a single Linux distribution | System packages | Maintained along with the distribution, which handles security updates |
| Embedded, cross-compilation | Vendoring, or custom vcpkg triplets / Conan profiles | Unusual options; precompiled packages usually don't apply |

The approaches can also be combined. A common pattern is to write the build scripts with `find_package`, and have vcpkg, Conan or `FetchContent`'s `FIND_PACKAGE_ARGS` provide those packages behind the scenes. Then switching dependency sources needs no change to `CMakeLists.txt`.

## Common misconceptions

!!! pitfall "Header-only means no version conflicts"
    Header-only only avoids mismatches between precompiled binaries and options. Two versions of the headers entering the same program is exactly the `mini` example above: an ODR violation, no diagnostic required.

!!! pitfall "If it links, the versions are fine"
    The linker only compares symbol names ([[toolchain/linking-and-symbols]]). Class layout, the contents of inline functions and members decided by macros aren't in symbol names.

!!! pitfall "Works in Release, crashes in Debug: must be a compiler bug"
    How an ODR violation shows up depends on inlining decisions. The `mini` example gives correct output at `-O2` and crashes at `-O0`. When you see something like this, first check whether there are two versions of the same library, or the same library built with different options.

## Questions

!!! question "1"
    `liba` and `libb` both copied the `mini` 1.0 headers into their own source trees, with identical contents, one under `liba/third_party/` and one under `libb/third_party/`. Does the program violate the ODR?

<details markdown="1">
<summary>Answer</summary>

No. [[basic.def.odr#16]] requires that each definition consist of the same sequence of tokens, that names look up to the same entities, and so on; it has nothing to do with where the headers are on disk. As long as the two files have the same content and the same environment when included (macros, earlier declarations), the requirements are met. The risk is that one side upgrades later and the other doesn't.
</details>

!!! question "2"
    Does compiling `mini` into a shared library `libmini.dylib` that exports only non-inline functions solve the problem of two coexisting versions?

<details markdown="1">
<summary>Answer</summary>

Only partly. How same-named non-inline functions from the two versions resolve depends on platform rules: ELF resolves in global search order by default, binding references to whichever copy is found first; Mach-O's two-level namespace records which shared library each reference comes from (according to the documentation). See the shared library section of [[toolchain/linking-and-symbols]]. The standard guarantees nothing here. The inline functions and class definitions in the headers are still compiled in the consumers' TUs, so the problem of differing layouts remains. The reliable approach is still one version per program, or making the two versions different entities with tools such as inline namespaces.
</details>

!!! question "3"
    A library is brought in with `FetchContent`, and the top level sets `CMAKE_CXX_STANDARD 23`. The library's own `CMakeLists.txt` says `set(CMAKE_CXX_STANDARD 17)`. Will the two sides' code be compiled with different `-std`? Why might that be a problem?

<details markdown="1">
<summary>Answer</summary>

Yes. `add_subdirectory` and `FetchContent_MakeAvailable` add the dependency as a subdirectory, and a `set` in the subdirectory only affects its own scope, so the dependency's sources are compiled as C++17 and the project's own as C++23. In the commands generated by CMake 3.29 on our test machine, the dependency's sources have no `-std=` at all, because C++17 is Clang 23's default (`gnu++17`). If the dependency's public headers have members or type aliases chosen by `__cplusplus`, the two sides see different definitions, which is the ODR violation discussed above. Checking `ninja -t commands` or `compile_commands.json` confirms the options each file actually uses.
</details>
