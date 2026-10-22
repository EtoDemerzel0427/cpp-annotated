---
title: Modules in practice
summary: "How compilers implement C++20 modules: each compiler's BMI, Clang's two compilation modes and reduced BMIs, dependency scanning, CMake's CXX_MODULES file sets, the state of import std and header units, and how module attachment shows up in symbol names."
group: Toolchain
tags: modules, build
updated: 2026-10-19
---

!!! tldr
    - Compiling a module interface unit produces a BMI (a serialization of the compiler's internal representation) in addition to the object file. Importers read the BMI instead of reparsing the source.
    - A BMI is tied to the compiler version and key compile options, and can't be distributed as a library interface. Libraries ship the source of their module interfaces.
    - Importers can only be compiled after the BMI is generated, so the build system must first scan dependencies to work out which modules each file provides and requires. From CMake 3.28, `FILE_SET CXX_MODULES` with Ninja does this.
    - Module attachment shows up as `W<module-name>` in Itanium mangled names. Same-named entities in two modules have different symbols and don't collide; whether something is exported doesn't affect its symbol name.
    - Named modules plus `import std;` is currently the most mature combination; header units are still experimental in Clang and unsupported by CMake.

The standard describes modules purely semantically: a TU imports another set of TUs, and the imported declarations become reachable or visible ([[module.import]], [[module.reach]]). The standard doesn't mention files, compilation order or binary interface files; [[lex.phases]] only says it is implementation-defined whether the source of module units that are depended on must be available.

These semantics were designed around a particular implementation strategy: a module interface unit is translated once, producing a serialized compiler internal representation that importers read directly. That brings engineering problems the `#include` era didn't have: compilation order, dependency discovery and BMI compatibility.

!!! note "Test setup"
    Commands, output and numbers come from our test machine: Homebrew Clang 23.1 (libc++, macOS arm64), CMake 3.29, Ninja. The GCC and MSVC parts only describe mechanisms and weren't verified.

## BMIs

When compiling a module interface unit (including interface partitions) or an implementation partition, the compiler produces a **BMI** (Built Module Interface, also called a CMI, Compiled Module Interface) in addition to the object file. It is essentially a serialization of the compiler's AST, which importers read instead of reparsing the source.

| Compiler | BMI | Notes |
|---|---|---|
| Clang | `.pcm` files | Share a serialization format with Clang's precompiled headers; the compiler must be told explicitly where each `.pcm` is |
| GCC | `.gcm` files, by default under `gcm.cache/` in the current directory | Enabled with `-fmodules` (`-fmodules-ts` in older versions); a module mapper maps module names to file paths |
| MSVC | `.ifc` files | The IFC format has a public specification; interface units commonly use the `.ixx` extension |

BMIs aren't portable. They are tied to a specific compiler version and to compile options that affect semantics, such as the language standard version and whether exceptions are enabled. Library authors still distribute the source of their module interfaces, and users build BMIs with their own compiler and options.

Clang strictly checks that the configuration matches. Building `geo.pcm` with `-std=c++23` and then compiling an importer with `-std=c++20` and with `-fno-exceptions` respectively gave:

```text
error: C++23 was enabled in precompiled file '.../geo.pcm' but is currently disabled
error: exception handling was enabled in precompiled file '.../geo.pcm' but is currently disabled
error: precompiled file '.../geo.pcm' cannot be loaded due to a configuration mismatch with the current compilation [-Wmodule-file-config-mismatch]
```

Changing only the optimization level (such as `-O2`) doesn't affect using the BMI.

BMIs also impose an ordering constraint: an importer can only be compiled after the BMI of the imported module has been generated. Where all `.cpp` files could once be compiled fully in parallel, there is now a directed acyclic graph.

## How Clang compiles modules

### Two-phase

```bash
clang++ -std=c++23 --precompile geo.cppm -o geo.pcm      # phase 1: source → BMI
clang++ -std=c++23 -c geo.pcm -o geo.o                    # phase 2: BMI → object file
```

The first phase runs only the frontend, doing parsing and semantic analysis. As soon as the BMI is produced, importers that depend on it can start compiling without waiting for phase 2's code generation. Only frontend time is on the critical path of the build.

### One-phase

```bash
clang++ -std=c++23 -c geo.cppm -fmodule-output=geo.pcm -o geo.o
```

A single invocation produces both the object file and the BMI. This is how CMake drives Clang.

### Full BMIs and reduced BMIs

`--precompile` produces a **full BMI**, which keeps everything needed to generate object code, such as the bodies of non-inline functions. Importers don't actually need these. A **reduced BMI** keeps only what importers need, and applies the discarding rule of [[module.global.frag#3]]: declarations in the global module fragment that the module itself doesn't use (that aren't [[g:decl-reachable]]) are discarded, and importers can't see them.

Clang 23's behavior on our test machine:

- `-c x.cppm -fmodule-output=x.pcm` produces a reduced BMI by default, the same size as with an explicit `-fmodules-reduced-bmi`; with `-fno-modules-reduced-bmi` it produces the same full BMI as `--precompile`.
- For `geo.pcm` in the example below (with `#include <cmath>` in the global module fragment): the full BMI is about 920 KB and the reduced BMI about 365 KB.

They also differ semantically. In the standard's example in [[module.global.frag#5]], `use_g<int>()` should fail because `N::g` is discarded. With a full BMI Clang accepts it; with a reduced BMI Clang correctly reports an error:

<div class="compare" markdown="1">

```text
# --precompile (full BMI)
$ clang++ -fsyntax-only \
    -fmodule-file=M=M.pcm Mi.cpp
(passes)
```

```text
# -fmodule-output (reduced BMI)
$ clang++ -fsyntax-only \
    -fmodule-file=M=M.pcm Mi.cpp
error: use of undeclared identifier 'g'
```

</div>

In other words, the build mode changes Clang's verdict on whether the same program is well-formed. Code that relies on global module fragment declarations that should have been discarded may fail to compile under a different build mode.

### Telling the compiler where BMIs are

Clang doesn't look for BMIs automatically; they must be specified:

| Option | Meaning |
|---|---|
| `-fmodule-file=<module-name>=<path>` | The BMI path of a module or partition (such as `geo:shapes`) |
| `-fprebuilt-module-path=<dir>` | Look in the directory for `<module-name>.pcm`; partition `M:P` corresponds to `M-P.pcm` |
| `-fmodule-file=<path>` | The unnamed form, used for header unit BMIs |

The extension `.cppm` (or `.ccm`, `.cxxm`, `.c++m`) tells Clang this is a module interface unit; other extensions need `-x c++-module`.

## A complete example

A small module with an interface partition and an implementation unit, using `import std;`:

```cpp title="shapes.cppm"
export module geo:shapes;
export namespace geo {
  struct Circle { double r; };
  double area(const Circle& c);
}
```

```cpp title="geo.cppm"
module;
#include <cmath>
export module geo;
export import :shapes;
namespace geo {
  double pi() { return std::acos(-1.0); }   // module linkage: usable only within module geo
}
```

```cpp title="geo.cpp"
module geo;
namespace geo {
  double area(const Circle& c) { return pi() * c.r * c.r; }
}
```

```cpp title="main.cpp" ok
import std;
import geo;
int main() {
  geo::Circle c{2.0};
  std::println("area = {:.3f}", geo::area(c));
}
```

A two-phase build, run in dependency order:

```bash
LIBCXX=/opt/homebrew/opt/llvm/share/libc++/v1
# standard library module (built once per toolchain configuration)
clang++ -std=c++23 -Wno-reserved-module-identifier --precompile $LIBCXX/std.cppm -o std.pcm
# partitions first, then the primary interface
clang++ -std=c++23 --precompile shapes.cppm -o geo-shapes.pcm
clang++ -std=c++23 --precompile geo.cppm -fmodule-file=geo:shapes=geo-shapes.pcm -o geo.pcm
# BMI → object file
clang++ -std=c++23 -c geo-shapes.pcm -o geo-shapes.o
clang++ -std=c++23 -c geo.pcm -fmodule-file=geo:shapes=geo-shapes.pcm -o geo.o
clang++ -std=c++23 -c std.pcm -o std.o
# implementation unit and importer
clang++ -std=c++23 -c geo.cpp -fmodule-file=geo=geo.pcm -fmodule-file=geo:shapes=geo-shapes.pcm -o geo-impl.o
clang++ -std=c++23 -c main.cpp -fprebuilt-module-path=. -o main.o
# link
clang++ main.o geo.o geo-shapes.o geo-impl.o std.o -o app
./app          # output: area = 12.566
```

`std` is a reserved module name ([[module.unit#1]]), and Clang warns about `export module std;`, so building `std.pcm` needs `-Wno-reserved-module-identifier`. Building `std.pcm` took about 1 second on our test machine, producing about 37 MB.

When compiling `geo.pcm` in phase 2, the location of `geo:shapes` must still be given. A BMI records which modules it depends on, but not their paths. `main.cpp` uses `-fprebuilt-module-path=.`, so Clang finds `std.pcm` and `geo.pcm` itself, and then finds `geo-shapes.pcm` from the module name recorded in `geo.pcm`.

The one-phase build:

```bash
clang++ -std=c++23 -c shapes.cppm -fmodule-output=geo-shapes.pcm -o geo-shapes.o
clang++ -std=c++23 -c geo.cppm -fmodule-file=geo:shapes=geo-shapes.pcm -fmodule-output=geo.pcm -o geo.o
clang++ -std=c++23 -c geo.cpp -fprebuilt-module-path=. -o geo-impl.o
clang++ -std=c++23 -c main.cpp -fprebuilt-module-path=. -fmodule-file=std=std.pcm -o main.o
clang++ main.o geo.o geo-shapes.o geo-impl.o std.o -o app
```

One data point on compile time from our test machine: a program using `import std;` (vector, `ranges::sort`, `println`) and an equivalent program using `#include <vector>`, `<algorithm>`, `<print>`, each compiled three times (`-c -O0`), took about 0.30 s and about 0.53 s respectively. That doesn't yet count the amortization from building `std.pcm` only once. This isn't a rigorous benchmark.

## Module attachment in symbol names

[[basic.link#8]] says same-named entities attached to different modules are different entities; [[module.unit#7]] says which module a declaration is attached to. The Itanium C++ ABI (used by Clang and GCC on non-Windows platforms) encodes the module name into mangled names with a `W` prefix. The `nm` output for the example above (Mach-O symbols have an extra leading `_`):

```text
geo-impl.o:
                 U __ZN3geoW3geo2piEv
0000000000000000 T __ZN3geoW3geo4areaERKNS_S0_6CircleE
geo.o:
0000000000000018 S __ZGIW3geo
0000000000000000 T __ZN3geoW3geo2piEv
                 U _acos
geo-shapes.o:
0000000000000000 S __ZGIW3geoWP6shapes
```

In `_ZN3geoW3geo2piEv`, `N 3geo` is the namespace `geo`, `W3geo` is the module `geo`, followed by `2pi`. `llvm-cxxfilt` decodes it as `geo::pi@geo()`. The namespace and the module having the same name is a coincidence; they occupy different positions in the mangled name.

`geo::pi` isn't exported and has module linkage; `geo::area` is exported and has external linkage. Yet both carry `W3geo`: the mangled name reflects attachment, not linkage. An entity with module linkage is still a global `T` symbol in the object file; the linker doesn't know module linkage exists. Other modules don't accidentally link to it because the module name is in the mangled name.

`geo::area` is declared in the partition `:shapes`, yet its mangled name has no partition name. This is consistent with note 1 in [[module.unit#3]]: how a module is divided into units isn't visible outside the module. The partition name appears only in the symbol of the module initialization function: `_ZGIW3geoWP6shapes`, where `GI` denotes a module initialization function and `WP` a partition. `_ZGIW3geo` is module `geo`'s initialization function; importers' initialization code calls it first, to ensure the dynamic initialization of imported modules runs first.

Two more rules:

- Dotted module names are encoded segment by segment. `f()` in `export module a.b;` is mangled as `_ZW1aW1b1fv`.
- Declarations in an `extern "C++"` block are attached to the global module ([[module.unit#7]] ¶7.2.4), and their mangled names have no `W`. `extern "C++" int f3();` declared in module M is mangled as `_Z2f3v`, exactly as if declared in an ordinary header. This is used to keep the ABI unchanged during gradual migration.

### Same-named entities in two modules

```cpp title="A.cppm"
export module A;
export int f() { return 1; }
int helper() { return 10; }
export int a() { return helper(); }
```

```cpp title="B.cppm"
export module B;
export int f() { return 2; }
int helper() { return 20; }
export int b() { return helper(); }
```

```cpp title="ua.cpp"
import A;
int ua() { return f() + a(); }
```

```cpp title="ub.cpp"
import B;
int ub() { return f() + b(); }
```

```cpp title="main.cpp" ok
int ua(); int ub();
int main() { return ua() + ub(); }   // 1+10 + 2+20 = 33
```

On our test machine this links and returns 33. The two `helper`s are mangled as `_ZW1A6helperv` and `_ZW1B6helperv`, and the two `f`s as `_ZW1A1fv` and `_ZW1B1fv`. If they were all written in headers, this would be an ODR violation (IFNDR), and the linker might report duplicate symbols or silently pick one.

But a single TU can't `import A;` and `import B;` together. The two declarations of `f` correspond ([[basic.scope.scope]]) but are attached to different modules, so they are two conflicting entities ([[basic.link#10]] note 5). Clang 23 reports an error at the import, even without a call to `f()`:

```text
error: declaration 'f' attached to named module 'A' cannot be attached to other modules
```

### Member functions defined in the class are no longer implicitly inline

[[class.mfct#1]] says that member functions defined in the class definition are implicitly inline only if the class is attached to the global module. Observed with `nm -m`:

```text
W.o (export module W; export struct S { int get() {...} inline int iget() {...} };):
  (__TEXT,__text) external      __ZNW1W1S3getEv     ← strong definition
  (__TEXT,__text) weak external __ZNW1W1S4igetEv    ← explicitly inline, weak definition
g.o (struct G { int get() {...} }; in an ordinary TU):
  (__TEXT,__text) weak external __ZN1G3getEv        ← implicitly inline, weak definition
```

When a TU importing W calls `s.get()`, it generates an external reference to `__ZNW1W1S3getEv` rather than an inline expansion. So changing `get`'s body doesn't change W's ABI.

GCC uses the same `W`-prefixed module mangling on Itanium platforms (not verified on our test machine). MSVC uses its own mangling and linking scheme and records module attachment differently.

## Dependency scanning

With `#include`, the build system can start compiling without knowing the dependencies between files in advance. Header dependencies are reported by `-MD` after compilation and are used only for incremental builds. Modules change this: before compiling `main.cpp`, it must be known that it imports `geo` and that `geo.pcm` has been generated.

The solution is a **dependency scan** before compilation: just preprocess each source file and find which module it provides and which modules it requires. [[P1857R3]] made `module` and `import` lines preprocessing directives, partly so that scanning needs only preprocessing, not full C++ parsing. The format of the scan results is specified by WG21 document P1689, a kind of JSON. Clang outputs this format with `clang-scan-deps -format=p1689`, and GCC and MSVC have corresponding options (details not verified on our test machine).

```bash
clang-scan-deps -format=p1689 -- clang++ -std=c++23 -c geo.cppm -o geo.o
```

```json
{
  "revision": 0,
  "rules": [
    {
      "primary-output": "geo.o",
      "provides": [
        { "is-interface": true, "logical-name": "geo", "source-path": "geo.cppm" }
      ],
      "requires": [
        { "logical-name": "geo:shapes" }
      ]
    }
  ],
  "version": 1
}
```

The scan result for `main.cpp` has no `provides`, and its `requires` are `std` and `geo`. The build system collects all scan results, builds a mapping of "module name → source file providing it → BMI path", orders the compilations, and generates the corresponding `-fmodule-file=` arguments for each TU.

Errors that aren't visible when compiling one TU alone also surface here, such as a module with two primary interface units ([[module.unit#2]], IFNDR) or cyclic dependencies between modules ([[module.import#10]]).

## CMake

CMake 3.28 and later officially support C++20 named modules, requiring the Ninja or Visual Studio generators; the Makefile generators don't support them. Module interface sources go into a file set of type `CXX_MODULES`:

```cmake title="CMakeLists.txt"
cmake_minimum_required(VERSION 3.28)
project(greet LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_library(greet)
target_sources(greet
  PUBLIC
    FILE_SET CXX_MODULES FILES
      src/greet.cppm          # primary interface unit
      src/greet-fmt.cppm      # interface partition greet:fmt
  PRIVATE
    src/greet.cpp)            # implementation unit: an ordinary source file

add_executable(app src/main.cpp)
target_link_libraries(app PRIVATE greet)
```

Configured with `cmake -G Ninja -DCMAKE_CXX_COMPILER=/opt/homebrew/opt/llvm/bin/clang++` and built, `ninja -v` shows three steps:

1. Run `clang-scan-deps -format=p1689` on every source file (including `main.cpp` and the implementation unit `greet.cpp`), producing `.ddi` files;
2. `cmake -E cmake_ninja_dyndep` collects the `.ddi` files and generates Ninja's dynamic dependency (dyndep) files and a `.modmap` response file for each TU;
3. Compile in dependency order, each command referring to these arguments through `@xxx.o.modmap`. The modmap for `greet.cppm` is:

    ```text
    -x c++-module
    -fmodule-output=CMakeFiles/greet.dir/greet.pcm
    -fmodule-file=greet:fmt=CMakeFiles/greet.dir/greet-fmt.pcm
    ```

    So CMake uses Clang's one-phase compilation and therefore produces reduced BMIs by default.

The implementation unit (`module greet;`) isn't put in the `CXX_MODULES` file set; it is just an ordinary source file, though it is still scanned. A `PUBLIC` `CXX_MODULES` file set lets targets that depend on `greet` import it; since BMIs can't be reused across build configurations, what the library offers is the source of its module interfaces. When two source files both say `export module M;`, Ninja on our test machine reports `multiple rules generate CMakeFiles/dup.dir/M.pcm` and stops.

CMake 3.29 on our test machine can't build the standard library module automatically. Newer CMake versions support `import std;` as an experimental feature (the target property `CXX_MODULE_STD`, plus an experimental switch that changes with the version); for details, see the documentation of the version you use; not verified on our test machine. The manual approach is the commands above: build `std.pcm` from `std.cppm` yourself and add it to the compilation.

## The state of header units

The header units of [[module.import#5]] (`import <vector>;`, `import "config.h";`) are the least mature part of implementations.

Clang supports them: build a header unit's BMI with `-fmodule-header=user|system` together with `-xc++-header` or `-xc++-system-header`, then import it with the unnamed `-fmodule-file=<path>`. This works on our test machine, and importing macros works too, but every import warns "the implementation of header units is in an experimental phase". CMake 3.29's `CXX_MODULES` file sets handle only named modules and don't support header units.

The difficulty is in the build system. A header unit has its own independent macro environment ([[module.import#5]] note 2), and the same header may need different BMIs under different compile options. The standard says in ¶5.3 that it is unspecified whether `import "x.h"` in two TUs imports the same header unit, which leaves room for exactly this situation.

MSVC supports automatically translating `#include` of importable headers into `import`, an implementation-defined behavior allowed by [[cpp.include#10]].

For now, the safer approach is: use named modules plus `import std;` for your own code, and `#include` third-party headers in the global module fragment.

## How modules affect the ODR

Same-named entities attached to named modules are different entities with different mangled names. Two libraries both having a `detail::helper` is no longer a problem, provided both are written in named modules.

Entities of the global module are still shared. Declarations `#include`d in a global module fragment are attached to the global module, and the cross-TU ODR requirements are the same as in the header era; including the same header with different macro configurations in different modules is still IFNDR. The difference is that when these modules are imported together, the compiler compares the definitions as it merges the BMIs and has a chance to report an error. In our experiment, the same `struct Cfg` was `{ long v; }` in one module and `{ int v; }` in another; Clang 23 reported "reference to 'v' is ambiguous" when accessing member `v` and listed both versions, rather than silently picking one.

An inline function attached to a named module, if declared in some definition domain, must be defined in the same definition domain ([[dcl.inline#5]]); member functions defined in the class are no longer implicitly inline either. In most cases these functions have a single definition stored in the BMI, and the problem of "definitions in each TU must be token-for-token identical" largely disappears.

## Common problems

!!! pitfall "Distributing BMIs as a library interface"
    Not feasible. A BMI is tied to the compiler version and compile options. Distribute the module interface source (`.cppm`) and let users build it themselves.

!!! pitfall "Using a Makefile generator"
    CMake's Unix Makefiles generator doesn't support C++ modules; use Ninja or Visual Studio.

!!! pitfall "Importing an implementation partition in an interface unit"
    Clang warns `-Wimport-implementation-partition-unit-in-interface-unit` about this. An implementation partition isn't necessarily reachable for importers outside the module ([[module.reach#1]]), and Clang chooses not to treat it as reachable. If importers need its definitions, make it an interface partition.

## Summary

| Topic | Key points |
|---|---|
| BMIs | Clang's `.pcm`, GCC's `gcm.cache/*.gcm`, MSVC's `.ifc`; tied to compiler version and options, not distributable |
| How Clang compiles | Two-phase: `--precompile` then `-c x.pcm`, giving a full BMI; one-phase: `-fmodule-output`, which in Clang 23 gives a reduced BMI by default and applies the discarding rule |
| Finding BMIs | `-fmodule-file=name=path`, `-fprebuilt-module-path=dir` |
| Dependency scanning | P1689-format JSON; `clang-scan-deps -format=p1689` |
| CMake | From 3.28, `FILE_SET CXX_MODULES` plus Ninja; `import std;` is experimental in newer versions |
| Header units | Experimental support in Clang; not supported by CMake |
| Symbol mangling | `W<module-name>` marks attachment, `WP` marks a partition (only in initialization functions); declarations in `extern "C++"` have no `W`; exporting doesn't affect symbol names |
