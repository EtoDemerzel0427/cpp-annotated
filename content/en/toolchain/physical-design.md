---
title: "Physical design: headers and dependencies"
summary: "How to organize headers and source files so that a project both compiles and compiles fast: #include as textual replacement and its cost, include guards and #pragma once, self-contained headers, what forward declarations can and can't do, inline, static and unnamed namespaces in headers, explicit instantiation of templates, the dependency graph, cyclic dependencies and levelization, and modules as the way out."
group: Engineering practice
tags: toolchain, headers, forward declarations, ODR, compile time, dependencies
updated: 2026-10-19
---

!!! tldr
    - `#include` copies the whole file in verbatim, and every translation unit processes it from scratch. On our test machine one `#include <vector>` expands to about 24,000 lines and `<iostream>` to about 35,000, and that cost is multiplied by the number of translation units that include it.
    - Every header should be self-contained: it should compile on its own as the first line of a translation unit. Relying on declarations brought in incidentally by another header is a violation with no diagnostic required, and may fail to compile with a different standard version or library version.
    - A forward declaration makes users depend only on a name; it works for pointers, references and function declarations. Wherever the size, members or base classes are needed, the definition must be visible. Don't forward-declare things in `std`; use the library's own forward-declaration headers such as `<iosfwd>`.
    - Function and variable definitions in headers must be `inline` (or templates, or constexpr); otherwise they are duplicate definitions when several translation units are linked. `static` and unnamed namespaces give each translation unit its own copy, so data is duplicated and mutable state is no longer shared.
    - A template can leave only declarations in the header, with `extern template` plus an explicit instantiation in a `.cpp` concentrating instantiation in one place. In our experiment, the total compile time of 8 using translation units dropped to about a quarter.

!!! note "Test setup"
    Output and numbers come from our test machine: Apple M2 Pro, macOS, Homebrew Clang 23.1.3 + libc++, CMake 3.29, Ninja 1.12. Compile times are the process's user plus system CPU time, taking the minimum over several runs; the machine had other load at the same time, so the numbers are only for comparing orders of magnitude. include-what-you-use wasn't installed; we used LLVM's own `clang-include-cleaner`.

## `#include` is textual replacement

```cpp run title="ndebug.cpp" ok
#include <cassert>
void checked(int x) { assert(x > 0); }

#define NDEBUG
#include <cassert>
void unchecked([[maybe_unused]] int x) { assert(x > 0); }

int main() { unchecked(-1); checked(1); }
```

Including the same header twice gives two kinds of `assert`. At the first inclusion `NDEBUG` isn't defined and `assert` expands to a check; at the second, `NDEBUG` is defined and `assert` expands to nothing. The program exits normally; `unchecked(-1)` doesn't trigger the assertion.

The standard says an `#include` directive is replaced by the entire contents of the named file ([[cpp.include#3]]), and the included file is again preprocessed recursively. A source file together with everything it includes directly and indirectly is called a **preprocessing translation unit** ([[g:preprocessing-translation-unit|preprocessing translation unit]], [[lex.separate#1]]). A header has no scope of its own and is never compiled on its own; its meaning depends entirely on where it is pasted and which macros were defined beforehand. `<cassert>` is a header the standard deliberately designed to take effect anew at each inclusion ([[using.headers#2]]); for other standard headers, including them several times has the same effect as including them once.

Preprocessor output, linemarkers and header search paths are covered in [[toolchain/compilation-pipeline]]. The concern here is how this model affects project organization.

### Processed again in every translation unit

The compiler looks at one translation unit (TU) at a time, and TUs share no parsing results. If 10 `.cpp` files include `<format>`, `<format>` is preprocessed, parsed and semantically analyzed 10 times. The table below measures, on our test machine, files containing just `#include <h>` and an empty `main`: lines are the non-blank lines of `clang++ -std=c++2c -E -P` output, files are the inclusion records listed by `-H`, and time is the CPU time of `-fsyntax-only` (no code generation).

| Header | Lines after preprocessing | Inclusion records (distinct files) | CPU time |
|---|---:|---:|---:|
| (none) | 1 | 0 | 33 ms |
| `<cstddef>` | 137 | 43 (36) | 34 ms |
| `<iosfwd>` | 254 | 45 (45) | 34 ms |
| `<utility>` | 4 026 | 195 (185) | 55 ms |
| `<string_view>` | 9 575 | 391 (337) | 85 ms |
| `<memory>` | 11 272 | 360 (317) | 92 ms |
| `<string>` | 13 958 | 457 (387) | 143 ms |
| `<map>` | 15 863 | 443 (376) | 117 ms |
| `<vector>` | 23 565 | 550 (449) | 156 ms |
| `<algorithm>` | 24 028 | 827 (600) | 166 ms |
| `<ranges>` | 23 710 | 601 (474) | 166 ms |
| `<format>` | 29 990 | 718 (565) | 256 ms |
| `<print>` | 30 120 | 720 (567) | 295 ms |
| `<iostream>` | 35 487 | 759 (597) | 342 ms |
| `<chrono>` | 40 958 | 809 (637) | 338 ms |

The 33 ms for the empty file is the overhead of starting the compiler itself. A TU that includes `<iostream>` has spent about 0.3 seconds of CPU time before its first line of its own code. With hundreds of TUs in a project, this is the bulk of full build time.

There are more inclusion records than distinct files because some files are entered more than once. For example, Clang's own `<stddef.h>` is designed to be included multiple times, providing a different subset each time depending on the `__need_*` macros the includer defines beforehand.

### Why `<vector>` is bigger than `<string>`

Attributing the preprocessor output to source files by linemarker and summing by libc++ subdirectory shows where the lines come from:

```text
$ printf '#include <vector>\n' > v.cpp
$ python3 attr.py v.cpp          # counts non-blank lines contributed by each file, using "# line file" linemarkers
total 23564
  3604  15.3% __format/
  2488  10.6% __algorithm/
  2341   9.9% string
  2084   8.8% __vector/
  1809   7.7% __iterator/
  1377   5.8% __type_traits/
  1050   4.5% __memory/
   935   4.0% (C/SDK headers)
   ...
```

`<vector>`'s own implementation (`__vector/`) is only 9%. The biggest piece is `__format/`, which comes from C++23's formatter for `vector<bool>::reference`: libc++'s `<vector>` includes `__vector/vector_bool_formatter.h` when `_LIBCPP_STD_VER >= 23`, which includes `__format/formatter.h`, which in turn pulls in `<string>`. Measuring the same file by standard version:

```text
$ for s in 17 20 23 2c; do echo "c++$s $(clang++ -std=c++$s -E -P v.cpp | grep -c .)"; done
c++17 12588
c++20 15719
c++23 23426
c++2c 23564
```

`<algorithm>` has a different structure. libc++ puts each algorithm in its own file under `__algorithm/`; that directory has 209 files on our test machine, `<algorithm>` includes them all, and they contribute 46% of the lines. `<vector>` uses only 39 of them.

```text
$ printf '#include <algorithm>\n' > al.cpp && python3 attr.py al.cpp
total 24027
 11081  46.1% __algorithm/
  1748   7.3% __iterator/
  1400   5.8% __type_traits/
  ...
```

These numbers are implementation details of libc++ 23; libstdc++ and MSVC STL split things differently. What is certain is that the standard only specifies which declarations each header must at least provide, and allows it to include other standard headers ([[res.on.headers#1]]), so the actual cost of standard library headers can only be measured, not derived from the standard.

## Preventing repeated inclusion

```text
point.h            shapes.h               main.cpp
struct Point {…};  #include "point.h"     #include "point.h"
                   struct Rect {…};       #include "shapes.h"
```

```text
$ clang++ -std=c++2c -fsyntax-only main.cpp
In file included from main.cpp:2:
In file included from ./shapes.h:1:
./point.h:1:8: error: redefinition of 'Point'
main.cpp:1:10: note: './point.h' included multiple times, additional include site here
```

`main.cpp` includes `point.h` through two paths, and after textual replacement the same class definition appears twice. Any definable entity may have only one definition in a TU ([[basic.def.odr#2]]), and this violation must be diagnosed. Headers including each other is the norm, so every header must be able to withstand repeated inclusion.

<div class="compare" markdown="1">

```cpp title="point.h (include guard)"
#ifndef GEO_POINT_H
#define GEO_POINT_H

struct Point { int x, y; };

#endif
```

```cpp title="point.h (#pragma once)"
#pragma once


struct Point { int x, y; };

```

</div>

On the left is an **include guard**: the first inclusion defines a macro, and on later inclusions `#ifndef` skips the whole file. It uses only standard conditional compilation and works everywhere. The macro name must be unique across the whole project and its dependencies; copy a header and forget to change the macro name, and the second file is silently skipped.

On the right, `#pragma once` isn't part of the standard. [[cpp.pragma#1]] only says the behavior of `#pragma` is implementation-defined and unrecognized pragmas are ignored. GCC, Clang and MSVC all support it, with the meaning that the same file is processed only once in a TU.

Where the two differ is in deciding what counts as the same file. An include guard goes by the macro name; `#pragma once` goes by the file itself. Our experiment:

```text
$ cp a/point.h b/point.h       # two #pragma once headers with identical content
$ printf '#include "a/point.h"\n#include "b/point.h"\n' > two.cpp
$ clang++ -std=c++2c -fsyntax-only two.cpp
./b/point.h:2:8: error: redefinition of 'Point'

$ ln -s a/point.h c_point.h    # a symlink to the same file
$ printf '#include "a/point.h"\n#include "c_point.h"\n' > sym.cpp
$ clang++ -std=c++2c -fsyntax-only sym.cpp && echo ok
ok
```

Clang recognizes the same file reached through a symlink or different search paths. Two copies with identical content are treated as two files. With an include guard and the same macro name, the second copy would be skipped. This situation usually arises when the same third-party library is brought in twice, which is itself a problem to fix; see [[toolchain/dependencies]].

There is no performance difference between the two. Clang and GCC both recognize the pattern of a whole file wrapped in `#ifndef`/`#endif`, remember the guard macro, and skip the file on later encounters without even opening and reading it. Compiling the include-guarded `main.cpp` above with `-H`, `point.h` is listed only once; the inclusion in `shapes.h` never entered the file.

!!! tip "Recommendation"
    Use `#pragma once` in new projects: one fewer name that has to be globally unique, and no errors from copying files. Use an include guard, with a macro name prefixed by project and path, when you need to support compilers that don't recognize it, or when the same header really does appear as copies in several locations.

## Self-contained headers

### Compiling by luck

```cpp run title="leak.cpp" ifndr
#include <vector>

std::string greet() { return "hi"; }    // no #include <string>

int main() {
  std::vector<int> v{1, 2};
  return greet().size() == v.size() ? 0 : 1;
}
```

Clang 23 + libc++ compiles this with `-std=c++23` or `-std=c++2c` without any diagnostic; with `-std=c++20` it reports:

```text
leak.cpp:3:13: error: implicit instantiation of undefined template 'std::basic_string<char>'
```

The reason is what we saw earlier: in C++23 mode `<vector>` indirectly includes `<string>` via the formatter, while in C++20 mode it only indirectly gets a forward declaration of `basic_string`. The standard allows standard headers to include other headers ([[res.on.headers#1]]) but doesn't require it; on the other hand, a TU must itself include a header before the first use of an entity declared in it, with no diagnostic required for violations ([[using.headers#3]]). A program relying on indirect inclusion compiles today and may fail after upgrading the compiler, switching standard libraries or changing `-std`.

`clang-include-cleaner` suggests headers to add or remove based on usage:

```text
$ clang-include-cleaner --print=changes leak.cpp -- -std=c++2c
+ <string>
```

### The same goes for your own headers

```cpp title="include/geo/label.h"
#pragma once
#include "geo/point.h"

struct Label {
  Point at;
  std::string text;   // relies on the includer having included <string> first
};
```

```cpp title="src/label.cpp"
#include <string>
#include "geo/label.h"
Label make() { return {{1, 2}, "origin"}; }
```

`label.cpp` compiles because it happens to include `<string>` first. Another file that includes `label.h` first gets `use of undeclared identifier 'std'`. Errors like this are often triggered long after the header was written, by someone else, somewhere else.

A header is **self-contained** if it compiles as the first line of a TU. The way to check is to generate, for each header, a TU containing only one `#include` line and compile it on its own. From CMake 3.24 this can be automated:

```cmake title="CMakeLists.txt"
add_library(geo src/label.cpp)
target_sources(geo PUBLIC FILE_SET HEADERS BASE_DIRS include
               FILES include/geo/point.h include/geo/label.h)
set_target_properties(geo PROPERTIES VERIFY_INTERFACE_HEADER_SETS ON)
```

```text
$ cmake --build build --target all_verify_interface_header_sets
FAILED: .../geo_verify_interface_header_sets/geo/label.h.cxx.o
In file included from .../geo_verify_interface_header_sets/geo/label.h.cxx:1:
.../include/geo/label.h:5:3: error: use of undeclared identifier 'std'
    5 |   std::string text;   // relies on the includer having included <string> first
      |   ^
```

CMake generates a `.cxx` file for each header in the header set, containing only `#include <geo/label.h>`, and compiles it without linking. CMake usage itself is covered in [[toolchain/cmake]].

!!! tip "Recommendation"
    Put `#include "foo.h"` on the first line of `foo.cpp`. Then every compile of `foo.cpp` also checks that `foo.h` is self-contained, with no extra build target needed. Headers and source files alike should include only what they use directly (include what you use), without relying on others to bring things in incidentally.

## Forward declarations

As soon as the header `car.h` mentions `Engine`, the most direct thing is `#include "engine.h"`. The cost is that every TU including `car.h` depends on `engine.h` and everything it includes, and when `engine.h` changes, they all recompile. If `car.h` only needs to know that `Engine` is a class, one line `class Engine;` is enough.

### What a forward declaration allows

<div class="compare" markdown="1">

```cpp title="Allowed" ok
class Engine;

class Car {
  Engine* engine_;
  Engine& spare_;
public:
  Car(Engine& e);
  Engine make_engine() const;
  void swap_engine(Engine e);
};
```

```cpp title="Not allowed" error
class Engine;

class Car {
  Engine engine_;  // error: member
};
struct Turbo : Engine {};  // error: base class
auto n = sizeof(Engine);   // error
int rpm(Engine& e) {
  return e.rpm();  // error: member access
}
```

</div>

`class Engine;` declares a class without giving its definition, so at that point `Engine` is an **incomplete type** ([[g:incomplete-type|incomplete type]]). The compiler knows it is a class, but not its size or members. Anywhere the size, layout or members are needed requires a complete type: defining an object or non-static member of the type, using it as a base class, `sizeof`, member access, defining or calling a function with a by-value parameter, and so on; the note in [[basic.def.odr#14]] gives the full list.

The size of a pointer or reference doesn't depend on the pointed-to type, so incomplete types can be used there. Parameter and return types in a function declaration can also be incomplete; completeness is required only for function definitions and calls ([[dcl.fct.def.general#2]]). That is why `make_engine` and `swap_engine` on the left are valid; TUs that call them need to see the definition of `Engine`.

A `unique_ptr<Impl>` member can also use an incomplete type, but destruction requires completeness, so the special member functions must be defined in the `.cpp`. The full technique is in [[patterns/pimpl]].

### Default arguments can only be written in one place

Function declarations and class template declarations in a forward-declaration header often appear in the same TU as the declarations in the full header:

```cpp title="defarg.cpp" error
// net_fwd.h
template <class T, class Alloc = void> class Buffer;
void send(const Buffer<char>& b, int flags = 0);

// net.h: writes the default arguments again
template <class T, class Alloc = void> class Buffer { };
void send(const Buffer<char>& b, int flags = 0);
```

```text
defarg.cpp:6:34: error: template parameter redefines default argument
defarg.cpp:7:38: error: redefinition of default argument
```

Default arguments and default template arguments are themselves definable items ([[basic.def.odr#1]]) and may be defined only once in a TU, even if both have the same value (the note in [[dcl.fct.default#4]]). So default arguments can only go in one header, usually the forward-declaration header, which the full header includes without repeating them.

### Don't forward-declare the standard library

```cpp title="fwd-string.cpp" ub
namespace std { class string; }        // declaring std::string yourself
void greet(const std::string& name);

#include <string>
int main() { greet("hi"); }
```

Adding declarations to `namespace std` is undefined behavior unless the standard specifically permits it ([[namespace.std#1]]). This isn't just a formality. `std::string` isn't a class at all but an alias for `basic_string<char>`, and libc++ puts all its entities in the inline namespace `std::__1`. Compiling on our test machine reports:

```text
.../c++/v1/stdexcept:86:30: error: reference to 'string' is ambiguous
fwd-string.cpp:1:23: note: candidate found by name lookup is 'std::string'
.../c++/v1/__fwd/string.h:45:7: note: candidate found by name lookup is 'std::__1::string'
```

Even rewritten as a template declaration of `basic_string`, the name lands in `std` rather than `std::__1`, and the default template arguments can't be written again. When you need forward declarations, use the headers the standard library provides itself. The most commonly used is `<iosfwd>` ([[iosfwd.syn]]), which declares stream types such as `basic_ostream` and `ostream`, as well as `char_traits` and `allocator`:

```cpp title="point.h"
#pragma once
#include <iosfwd>

struct Point { int x, y; };
std::ostream& operator<<(std::ostream& os, Point p);
```

```cpp title="point.cpp"
#include "point.h"
#include <ostream>

std::ostream& operator<<(std::ostream& os, Point p) {
  return os << '(' << p.x << ", " << p.y << ')';
}
```

On our test machine, `<iosfwd>` is 253 lines after preprocessing and about 36 ms with `-fsyntax-only`; `<ostream>` is 34,488 lines and about 320 ms. Every TU including `point.h` saves the difference, and only TUs that actually print a `Point` need to include `<ostream>` or `<iostream>`.

!!! tip "Recommendation"
    If your library has many types that others will forward-declare, provide a `foo_fwd.h` that collects the forward declarations and default template arguments. Users include it instead of writing `class Foo;` themselves. Then if the library author later turns some class into an alias of a template, users' code is unaffected.

## Definitions in headers and the ODR

```cpp title="util.h"
#pragma once
int clamp_pct(int v) {             // non-inline definition
  return v < 0 ? 0 : v > 100 ? 100 : v;
}
```

```text
$ clang++ -std=c++2c a.cpp main.cpp -o app      # both TUs include util.h
duplicate symbol 'clamp_pct(int)' in:
    /var/folders/.../a-c88075.o
    /var/folders/.../main-2e8c2c.o
ld: 1 duplicate symbol for architecture arm64
```

`#pragma once` only prevents repetition within one TU; it does nothing across TUs. The two TUs each get a definition of `clamp_pct`. A non-inline non-template function or variable may have only one definition in the whole program ([[basic.def.odr#16.1]]); violations require no diagnostic, and here the linker happened to notice.

Adding `inline` makes it valid. An **inline function** ([[g:inline-function|inline function]]) may be defined in several TUs, provided each definition consists of the same sequence of tokens and the names in it refer to the same entities ([[basic.def.odr#16.4]], [[basic.def.odr#16.5]]). It is still one entity with one address ([[dcl.inline#2]]). The compiler emits it as a weak definition, and the linker keeps one of the copies:

```text
$ nm -m a.o
0000000000000000 (__TEXT,__text) external __Z1av
0000000000000018 (__TEXT,__text) weak external __Z9clamp_pcti
```

The mechanics of weak definitions and COMDAT are in [[toolchain/linking-and-symbols]]. These definitions can safely go in headers:

| In a header | Why multiple TUs don't conflict |
|---|---|
| Class and enumeration definitions | At most one definition per TU, the same in every TU ([[basic.def.odr#16]]) |
| `inline` functions, member functions defined in the class | inline (member functions defined in the class are implicitly inline in the global module, note in [[dcl.inline#5]]) |
| `constexpr` functions, `consteval` functions | Implicitly inline |
| `inline` variables (C++17), `constexpr` static data members | inline |
| Templates | Templates and their instantiations may be defined in several TUs |
| `const`/`constexpr` variables at namespace scope | Internal linkage ([[basic.link#3.2]]), an independent object per TU |

The last row is different in kind from the others: rather than several definitions merged into one, there really are several entities. That is the subject of the next section.

### `static` and unnamed namespaces: one per TU

```cpp title="table.h"
#pragma once
static int hits = 0;
static int table[4096] = {1, 2, 3};
static int lookup(int i) { ++hits; return table[i & 4095]; }
```

`static` or an unnamed namespace ([[g:unnamed-namespace|unnamed namespace]]) gives a name **internal linkage** ([[g:internal-linkage|internal linkage]], [[basic.link#3]], [[basic.link#4]]): the name refers to this entity only within this TU. If the header is included by three TUs, there are three unrelated `hits`, three `table`s and three `lookup`s. Compiling with `-O2` three TUs that each call `lookup` once, after linking:

```text
$ ./app      # calls hits_1 three times, hits_2 and hits_3 once each, then prints the address of table in each of the three TUs
3 1 1
0x104210010 0x104214010 0x104218010
$ size -m app | grep __data
	Section __data: 49160
```

The first TU called it three times and the other two once each, and the counts don't affect each other; `table` has three addresses, and the `__data` section is 3 × 16 KiB plus 8 bytes. Replacing the three `static`s with `inline`:

```text
$ ./app2
3 4 5
0x104214014 0x104214014 0x104214014
$ size -m app2 | grep __data
	Section __data: 16396
```

Now the whole program has one `hits` and one `table`. Small read-only constants with internal linkage are mostly harmless: the optimizer usually folds them straight into the code, and unused copies are removed. Mutable state and large data are another matter: in `static`, each TU modifies its own copy, and the data is duplicated once per TU.

!!! pitfall "An inline function referring to an entity in an unnamed namespace"
    ```cpp title="table.h" ifndr
    #pragma once
    namespace {
    int hits = 0;                    // each TU has its own hits
    }
    inline int lookup() { return ++hits; }   // each TU's definition refers to a different hits
    ```

    `lookup` is an inline function whose definitions have the same tokens in every TU, but the `hits` in it refers to a different variable in each TU, violating [[basic.def.odr#16.5]]: the program is ill-formed, no diagnostic required. With two TUs each calling `lookup()` once and returning their own `hits`, the result on our test machine depends on optimization level and link order:

    | Build | Output |
    |---|---|
    | `-O0`, order `t1.cpp t2.cpp` | `1 0` |
    | `-O0`, order `t2.cpp t1.cpp` | `0 2` |
    | `-O2`, either order | `1 1` |

    At `-O0` there is no inlining, the linker keeps the `lookup` from the first object file, and both TUs increment that TU's `hits`. At `-O2` each TU inlines its own version. Neither the linker nor the compiler reports anything. clang-tidy's `misc-anonymous-namespace-in-header` check warns about unnamed namespaces in headers.

The standard calls such a declaration an **exposure** ([[basic.link#14]]): the body of an inline function mentions an entity with internal linkage. It is ill-formed in a module interface unit, and deprecated in other contexts such as headers ([[basic.link#17]]).

## Templates: where the definitions go

When a function template or a member function of a class template is implicitly instantiated in some TU, its definition must be reachable there, unless the specialization is explicitly instantiated elsewhere ([[temp.pre#10]]). So template definitions are usually written entirely in headers, and every TU that uses them instantiates them and generates code once more, to be merged by the linker at the end.

If a template is only ever used with a few sets of template arguments, its instantiation can be concentrated in one `.cpp`:

```cpp title="stats.h"
#pragma once
#include <string>
#include <vector>

template <class T>
class Stats {
  std::vector<T> xs_;
public:
  void add(T x) { xs_.push_back(x); }
  std::string report() const;     // defined in stats.cpp
};
extern template class Stats<double>;
```

```cpp title="stats.cpp"
#include "stats.h"
#include <algorithm>
#include <format>

template <class T>
std::string Stats<T>::report() const {
  auto v = xs_;
  std::ranges::sort(v);
  return std::format("n={} min={} median={} max={}",
                     v.size(), v.front(), v[v.size() / 2], v.back());
}
template class Stats<double>;      // explicit instantiation definition
```

`template class Stats<double>;` is an **explicit instantiation definition**, which generates code in `stats.cpp` for all defined members of `Stats<double>` ([[temp.explicit#10]]). The `extern template class Stats<double>;` in the header is an **explicit instantiation declaration** ([[g:explicit-instantiation-declaration|explicit instantiation declaration]], [[temp.explicit#2]]); it makes the members of `Stats<double>` declared specializations ([[temp.inst#1]]), so other TUs no longer implicitly instantiate them and keep only references to the symbols:

```text
$ llvm-nm -C u1.o | grep Stats
                 U Stats<double>::report() const
```

Inline members (such as `add`, defined in the class) are the exception: they are still instantiated where used so that they can be inlined, only no separate function body needs to be generated (note in [[temp.inst#5]]).

Measurements: 8 TUs each use `Stats<double>` and call `report()`, comparing three organizations. A has all definitions in the header; B1 leaves the header unchanged and just adds `extern template`; B2 is the version above, with only declarations in the header.

| | `-O0`, 8 TUs total | `-O2`, 8 TUs total | 8 object files total (`-O0`) | `stats.cpp` (`-O2`) |
|---|---:|---:|---:|---:|
| A, implicit instantiation | 4.88 s | 7.80 s | 2934 KiB | — |
| B1, `extern template`, definitions still in the header | 2.84 s | 3.51 s | 63 KiB | 0.96 s |
| B2, `extern template`, definitions moved to the `.cpp` | 1.33 s | 1.67 s | 63 KiB | 0.90 s |

What B1 saves is instantiation and code generation: the whole `std::format` machinery is no longer instantiated in every TU. It can't save parsing: the header still includes `<format>` and `<algorithm>`, and each TU still processes about 30,000 lines. B2 moves those two headers out as well, leaving each TU with only `<string>` and `<vector>`. Including `stats.cpp`'s own compile time, B2 totals about 2.6 s at `-O2`, versus 7.8 s for A.

There are two costs. First, `report()` can no longer be inlined into callers; at `-O2` every call is a real function call. Second, the template is only usable with the listed template arguments: if someone uses `Stats<int>`, the B2 version reports an undefined symbol at link time, and another explicit instantiation line must be added to `stats.cpp`. If an implicit instantiation in some TU needs a specialization that has only an explicit instantiation declaration, with no corresponding explicit instantiation definition in the program, the program is ill-formed, no diagnostic required ([[temp.explicit#12]]).

!!! tip "Recommendation"
    Measure before changing. Use `-ftime-trace` to find the templates whose instantiation costs the most (see [[toolchain/build-speed]]), and do this only for templates with a fixed set of arguments and expensive instantiation. Keep general-purpose library templates in headers.

## The dependency graph

### Seeing dependencies

`-H` prints each header entered to standard error, with its nesting depth shown as one dot per level. Below is a small project, keeping only the project's own headers:

```text
$ clang++ -std=c++2c -Isrc -fsyntax-only -H src/main.cpp 2>&1 | grep -v '/v1/\|^\.* /'
. src/feed/decoder.h
.. src/book/order_book.h
... src/core/ids.h
... src/core/price.h
```

These files plus `main.cpp` are 22 lines in total, and 29,395 lines after preprocessing. A few lines of Python turn the indentation of `-H` back into edges that Graphviz can draw:

```python title="hdeps.py"
# usage: clang++ -fsyntax-only -H ... 2>&1 | python3 hdeps.py main.cpp
import sys
stack = [sys.argv[1]]
edges = set()
for line in sys.stdin:
    if not line.startswith('.'): continue
    dots, path = line.rstrip('\n').split(' ', 1)
    del stack[len(dots):]
    edges.add((stack[-1], path))
    stack.append(path)
print('digraph deps {')
for a, b in sorted(edges):
    if '/v1/' not in b and not b.startswith('/'):   # only draw the project's own headers
        print(f'  "{a}" -> "{b}";')
print('}')
```

```text
$ clang++ -std=c++2c -Isrc -fsyntax-only -H src/main.cpp 2>&1 | python3 hdeps.py src/main.cpp
digraph deps {
  "src/book/order_book.h" -> "src/core/ids.h";
  "src/book/order_book.h" -> "src/core/price.h";
  "src/feed/decoder.h" -> "src/book/order_book.h";
  "src/main.cpp" -> "src/feed/decoder.h";
}
```

`-H` lists only files actually entered. Repeated inclusions skipped by an include guard or `#pragma once` don't appear, so each TU's graph has no duplicate edges.

### How the build system knows what to recompile

Build systems use a different set of options. `-MD` writes a Makefile-format `.d` file during compilation, listing every file the object file depends on; `-MMD` lists only user headers, omitting system headers:

```text
$ clang++ -std=c++2c -MMD -c a.cpp -o a.o && cat a.d
a.o: \
  /Library/Developer/CommandLineTools/SDKs/MacOSX26.sdk/SDKSettings.json \
  a.cpp customer.h order.h
```

Ninja builds generated by CMake add `-MD` by default, and Ninja stores the `.d` file in its own database after reading it. For `label.cpp` in the `geo` project above:

```text
$ ninja -C build -t deps CMakeFiles/geo.dir/src/label.cpp.o | head -1
CMakeFiles/geo.dir/src/label.cpp.o: #deps 395, deps mtime ... (VALID)
$ touch include/geo/point.h && ninja -C build -n geo
[1/2] Building CXX object CMakeFiles/geo.dir/src/label.cpp.o
[2/2] Linking CXX static library libgeo.a
```

A three-line `.cpp` depends on 395 files, and it must be recompiled if any of them changes. The wider a header's dependencies, the more recompilation a one-line change causes.

### Cyclic dependencies

```cpp title="order.h"
#pragma once
#include "customer.h"
struct Order {
  Customer* owner;
  double total;
};
```

```cpp title="customer.h"
#pragma once
#include "order.h"
#include <vector>
struct Customer {
  std::vector<Order> orders;
  double spent() const;
};
```

The two headers include each other. `#pragma once` stops the cycle on the second entry, with the result that whichever header is included first can't see the other's definition:

```text
$ clang++ -std=c++2c -fsyntax-only a.cpp      # a.cpp includes customer.h first
./order.h:4:3: error: unknown type name 'Customer'
$ clang++ -std=c++2c -fsyntax-only b.cpp      # b.cpp includes order.h first
./customer.h:5:15: error: use of undeclared identifier 'Order'
```

The location of the error changes with the inclusion order, a typical symptom of a cyclic dependency. clang-tidy's `misc-header-include-cycle` finds cycles directly:

```text
$ clang-tidy --checks='-*,misc-header-include-cycle' --header-filter='.*' b.cpp -- -std=c++2c
.../customer.h:2:10: warning: circular header file dependency detected while including 'order.h', please check the include path [misc-header-include-cycle]
```

`Order` only uses `Customer*`; replace `#include "customer.h"` in `order.h` with `struct Customer;`, and the dependency becomes the one-way `customer.h → order.h`, and both TUs compile.

### Levelization

Treat a `.h`/`.cpp` pair as a **component**, with edges between components given by inclusion. An acyclic dependency graph can be divided into levels: components depending on no other component in the project are at level 1, those depending only on level 1 at level 2, and so on. This practice is called **levelization**, from John Lakos's *Large-Scale C++ Software Design* (1996).

The benefits of levelization are concrete. Each level can be tested on its own, linking only lower-level components; a change to one component affects only the levels above it; and builds can be parallelized by level. Where there is a cycle, the components on it can only be compiled, tested and understood as a whole.

Common ways to break a cycle:

- When only pointers or references are used, switch to a forward declaration, as with `Order` above.
- Extract the part both sides need into a new, lower-level component.
- Reverse the direction in which higher levels depend on lower ones, for example by having the lower level notify the higher level through a callback or interface instead of calling it directly.

The direction of dependencies between libraries, and which headers count as the public interface, are covered in [[toolchain/library-boundaries]].

## Modules

All the problems above stem from headers being processed repeatedly as text: every TU reparses them, macros leak in, inclusion order can affect meaning, and indirect inclusion exposes names that shouldn't be exposed. C++20 named modules change the model at the language level: a module interface is compiled once and importers read the compiled result; macros don't cross `import`; names that aren't exported are invisible to importers; and ODR violations in modules must be diagnosed when the definition is reachable ([[basic.def.odr#16]]).

`import std;` imports the entire standard library at once; the comparison on our test machine is in [[toolchain/compilation-pipeline]]. BMIs, dependency scanning, CMake integration and current limitations are covered in [[toolchain/modules-in-practice]]. Modules don't hide class layout either, so they solve only half of the recompilation problem that pimpl addresses; see [[patterns/pimpl]].

## Questions

!!! question "1"
    A header has `const int kLimit = 100;` and `inline int limit() { return kLimit; }`, and is included by several TUs. Each TU's `kLimit` is a different object, so the name in `limit`'s definition refers to different entities. Is that an ODR violation? What if the body is changed to `return *&kLimit;`?

<details markdown="1">
<summary>Answer</summary>

The first form isn't. A const variable at namespace scope has internal linkage ([[basic.link#3.2]]), so each TU has its own `kLimit`. But [[basic.def.odr#16.5.1]] specifically allows a name in an inline definition to refer to a non-volatile const object with internal linkage, provided the type is the same everywhere, it is initialized with a constant expression, the value is the same, and it isn't odr-used in the definition. `return kLimit;` immediately applies the lvalue-to-rvalue conversion to it, which isn't an odr-use.

The second form takes the address of `kLimit`, which is an odr-use, so the exception no longer applies: the program is ill-formed, no diagnostic required. Writing it as `inline constexpr int kLimit = 100;` gives a single object, and both forms are fine.
</details>

!!! question "2"
    Does the header below compile? What about a TU including it that writes `void f() { Tree t; }`?

    ```cpp
    #include <vector>
    struct Node;
    struct Tree { std::vector<Node> kids; };
    ```

<details markdown="1">
<summary>Answer</summary>

The header itself does. [[vector.overview#4]] allows `vector` to be instantiated with an incomplete type, provided the allocator satisfies the completeness requirements (`std::allocator` does), but the element type must be complete before any member of the resulting `vector` specialization is referenced.

`Tree t;` needs `Tree`'s implicit default constructor and destructor, which are implicitly defined in this TU and refer to `vector<Node>`'s constructor and destructor. `Node` is still incomplete at that point, violating the library's requirement, so the behavior is undefined ([[res.on.functions#2]]). libc++ on our test machine reports `arithmetic on a pointer to an incomplete type 'Node'` when instantiating the `size()` used by `~vector`. The fix is to define `Tree`'s constructor and destructor in a `.cpp` after `Node` is complete, the same way pimpl handles it.
</details>

!!! question "3"
    `#pragma once` and include guards both prevent duplicate definitions within one TU. Why can neither prevent a header definition like `int clamp_pct(int)` from being duplicated at link time?

<details markdown="1">
<summary>Answer</summary>

Both only act within the preprocessing of a single TU. Every TU is preprocessed from scratch, and the state of macros and pragmas doesn't carry over from one TU to another, so every TU that includes the header gets a definition. The cross-TU rule is [[basic.def.odr#16.1]]: a non-inline non-template function may be defined only once in the whole program. The fix is to declare it `inline`, or move the definition into a `.cpp` and leave only a declaration in the header.
</details>

## Summary

| Problem | Remedy | Basis |
|---|---|---|
| Repeated inclusion within a TU | `#pragma once` or an include guard | [[basic.def.odr#2]], [[cpp.pragma#1]] |
| Relying on indirect inclusion | Every header self-contained, include what you use; compile each header on its own once to check | [[using.headers#3]], [[res.on.headers#1]] |
| Header dependencies too wide | Forward declarations when only pointers, references or function declarations are needed; `<iosfwd>` for stream types | [[basic.def.odr#14]], [[iosfwd.syn]] |
| Forward-declaring the standard library | Don't | [[namespace.std#1]] |
| Function and variable definitions in headers | `inline`, `constexpr` or templates | [[basic.def.odr#16]], [[dcl.inline#2]] |
| `static` and unnamed namespaces in headers | One per TU; don't use for mutable state, don't refer to from inline functions | [[basic.link#3]], [[basic.def.odr#16.5]] |
| Repeated instantiation of expensive templates | `extern template` + an explicit instantiation in one `.cpp`, after measuring | [[temp.explicit#2]], [[temp.pre#10]] |
| Cyclic dependencies | Forward declarations, extracting lower-level components; keep the dependency graph acyclic | — |
| The fundamental cost of textual inclusion | Named modules | [[toolchain/modules-in-practice]] |
