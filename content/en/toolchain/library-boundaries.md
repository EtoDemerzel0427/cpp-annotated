---
title: "Library boundaries: static libraries, shared libraries and ABI"
summary: "What makes up the boundary of a C++ library: what static and shared libraries contain, controlling exported symbols with visibility, which changes break binary compatibility without changing any symbol name, why a C interface is the most stable boundary, how exceptions and RTTI cross shared libraries, who allocates and who frees, and how install names, sonames and inline namespaces manage versions."
group: Engineering practice
tags: toolchain, libraries, shared libraries, static libraries, ABI, visibility, symbols, versioning
updated: 2026-10-19
---

!!! tldr
    - A library's boundary is more than the declarations in its headers. The caller's binary also has the class sizes, virtual function slots, inline function bodies, default arguments and the identity of exception types baked in; all of these belong to the ABI.
    - A shared library exports every symbol with external linkage by default. Use `-fvisibility=hidden` plus an export macro to export only the public interface; our example went from 15 exported symbols to 4.
    - Many ABI-breaking changes alter no symbol names; linking and loading succeed, but the results are wrong. After swapping the declaration order of two virtual functions, the old program calling `width()` got the value of `height()` in our test.
    - The most stable boundary is a C interface: `extern "C"` functions, opaque handles, error codes, with the library responsible for allocation and deallocation. Exceptions, `std::` types and class layouts don't cross that line.
    - Versions are managed with three things: the shared library's install name or soname distinguishes incompatible major versions, inline namespaces turn incompatible changes into link or load errors, and the exported symbol table only grows and never changes.

A library's **boundary** is everything the caller's compiled code depends on. The declarations in the headers are only the visible part. When the caller is compiled, the compiler also writes the class sizes, member offsets, positions of virtual functions in the vtable, inline function bodies and default argument values directly into the caller's machine code. These binary-level conventions are collectively called the **ABI** (application binary interface). If the library changes version and the caller isn't recompiled, both sides must agree on all of them.

The standard has no concept of a library. Phase 8 of translation ([[lex.phases#1]]) only says that translation units (TUs) and library components are combined to form a program. Static libraries, shared libraries, visibility and version numbers are all mechanisms provided by implementations. So most of the rules on this page aren't standard rules, but behind each of them a standard rule is at work: the ODR ([[basic.def.odr]]), language linkage ([[dcl.link]]), exception matching ([[except.handle]]).

The basic behavior of object files, symbol tables and linkers is covered in [[toolchain/linking-and-symbols]], and the encoding of symbol names in [[toolchain/name-mangling]].

!!! note "Test setup"
    Apple M2 Pro, macOS 26.5, Homebrew Clang 23.1.3, with headers from Homebrew's libc++ and the system's `/usr/lib/libc++.1.dylib` linked at run time. The linker is the system's `ld-1266.8`, selected with `--ld-path=/usr/bin/ld` in the commands; `nm` and `otool` are also Apple's versions in `/usr/bin`. Our test machine has no GCC, no libstdc++ and no linker that can link ELF shared libraries, so everything about Linux is marked as based on documentation.

## What is in a static or shared library

Below is a small geometry library. The header declares the public interface, two `.cpp` files implement it, and `detail::cross` is an internal function:

```cpp title="geo.h"
#pragma once
#include <string>
#include <vector>

#if defined(GEO_BUILD)
#  define GEO_API __attribute__((visibility("default")))
#else
#  define GEO_API
#endif

namespace geo {
struct GEO_API Point { double x, y; };

class GEO_API Polygon {
public:
  void add(Point p);
  double area() const;
  std::string describe() const;
  std::size_t size() const { return pts_.size(); }   // inline
private:
  std::vector<Point> pts_;
};

template <class T> T sq(T v) { return v * v; }        // template
GEO_API double distance(Point a, Point b);
}
```

```cpp title="polygon.cpp"
#include "geo.h"
#include <cmath>
#include <cstdio>
namespace geo {
namespace detail {
double cross(Point a, Point b) { return a.x * b.y - a.y * b.x; }   // internal function
}
void Polygon::add(Point p) { pts_.push_back(p); }
double Polygon::area() const {
  double s = 0;
  for (std::size_t i = 0; i < pts_.size(); ++i)
    s += detail::cross(pts_[i], pts_[(i + 1) % pts_.size()]);
  return std::fabs(s) / 2;
}
std::string Polygon::describe() const {
  char buf[64];
  std::snprintf(buf, sizeof buf, "polygon(%zu), area %.1f", size(), area());
  return buf;
}
}
```

```cpp title="distance.cpp"
#include "geo.h"
#include <cmath>
namespace geo {
double distance(Point a, Point b) { return std::sqrt(sq(a.x - b.x) + sq(a.y - b.y)); }
}
```

```cpp title="app.cpp" ok
#include "geo.h"
#include <cstdio>
int main() {
  geo::Polygon p;
  p.add({0, 0}); p.add({4, 0}); p.add({4, 3});
  std::printf("%s, d=%.1f\n", p.describe().c_str(), geo::distance({0, 0}, {4, 3}));
}
```

### Static libraries

A **static library** (`.a`) is an archive of object files. At link time, the linker extracts the members it needs and copies their code into the executable (the extraction rules are in [[toolchain/linking-and-symbols]]):

```text
$ clang++ -std=c++2c -O2 -c polygon.cpp distance.cpp
$ llvm-ar rcs libgeo.a polygon.o distance.o && llvm-ar t libgeo.a
polygon.o
distance.o
$ clang++ -O2 app.cpp -L. -lgeo -o app_static && ./app_static
polygon(3), area 6.0, d=5.0
$ otool -L app_static
app_static:
	/usr/lib/libc++.1.dylib (compatibility version 1.0.0, current version 2100.43.0)
	/usr/lib/libSystem.B.dylib (compatibility version 1.0.0, current version 1356.0.0)
```

The executable no longer depends on `libgeo`; the library's code is already inside it. When the library is upgraded, the caller must relink to get the new code; conversely, an old executable never meets a new version of the library, and ABI problems only arise between the object files of a single link.

### Shared libraries

A **shared library** (`.dylib` on macOS, `.so` on Linux) is an already-linked image. The executable only records which library it uses and which symbols it takes from it, and the dynamic loader (`dyld` on macOS, `ld.so` on Linux) connects them at load time:

```text
$ clang++ -std=c++2c -O2 -DGEO_BUILD -fvisibility=hidden -shared polygon.cpp distance.cpp \
    -install_name @rpath/libgeo.dylib -o libgeo.dylib
$ clang++ -O2 app.cpp -L. -lgeo -Wl,-rpath,@loader_path -o app_dyn && ./app_dyn
polygon(3), area 6.0, d=5.0
$ otool -L app_dyn
app_dyn:
	@rpath/libgeo.dylib (compatibility version 0.0.0, current version 0.0.0)
	/usr/lib/libc++.1.dylib (compatibility version 1.0.0, current version 2100.43.0)
	/usr/lib/libSystem.B.dylib (compatibility version 1.0.0, current version 1356.0.0)
$ nm -u app_dyn | c++filt | grep geo
geo::Polygon::add(geo::Point)
geo::distance(geo::Point, geo::Point)
geo::Polygon::describe() const
```

`otool -L` lists the shared libraries the executable depends on; the `@rpath/libgeo.dylib` on the first line comes from the library's install name, discussed later under versioning. `nm -u` lists undefined symbols, that is, the three functions `app_dyn` will ask `libgeo` for at run time.

The library can be replaced on its own, without relinking the caller. That is the main purpose of shared libraries, and the source of ABI problems: the replacement library must satisfy every assumption the caller was compiled with.

| | Static library `.a` | Shared library `.dylib` / `.so` |
|---|---|---|
| Where the library's code lives | Copied into every image that uses it | One copy, shared at load time |
| Upgrading | The caller relinks | Replace the file, provided the ABI is compatible |
| Symbol visibility | Only affects exports once packaged into a shared library | Decides which symbols other images can use |
| Global state | One copy per image that links it | One copy |
| Where ABI errors appear | Between the object files of one link | Between the caller and any version of the library |

### One static library, two copies of state

The "one copy per image that links it" in the table is often overlooked. Below, `registry.cpp` is built as a static library and then linked into two separate shared libraries:

```cpp title="registry.cpp"
int& instance_count() { static int n = 0; return n; }
```

```cpp title="a.cpp (b.cpp just replaces a_register with b_register)"
int& instance_count();
__attribute__((visibility("default"))) int a_register() { return ++instance_count(); }
```

```cpp title="app.cpp" ifndr
#include <cstdio>
int a_register();
int b_register();
int main() {
  a_register(); a_register();
  std::printf("a sees %d, b sees %d\n", a_register(), b_register());
}
```

```text
$ clang++ -std=c++2c -O2 -c registry.cpp && llvm-ar rcs libregistry.a registry.o
$ clang++ -O2 -shared a.cpp libregistry.a -install_name @rpath/liba.dylib -o liba.dylib
$ clang++ -O2 -shared b.cpp libregistry.a -install_name @rpath/libb.dylib -o libb.dylib
$ clang++ -O2 app.cpp -L. -la -lb -Wl,-rpath,@executable_path -o app && ./app
a sees 3, b sees 1
```

Each shared library carries its own copy of `instance_count()` and of the static local variable `n` in it. On our test machine the result was the same whether `registry.cpp` was compiled with default visibility or with `-fvisibility=hidden`: macOS's two-level namespace binds each shared library to its own copy at build time (see [[toolchain/linking-and-symbols]]). On ELF platforms, symbols with default visibility can be interposed, and calls from the two libraries usually resolve to the same copy (according to documentation; not verified on our test machine).

By the standard, `instance_count` is a non-inline function with two definitions in the program, violating [[basic.def.odr#16]], which is {{ifndr}} (the program is invalid, but the implementation needn't diagnose it). The practical rule: a static library with global state may only be linked into one final image; if several shared libraries need to share it, it should itself be a shared library.

## What to export: symbol visibility

### Everything exported by default

Building a shared library without any options exports every symbol with external linkage, including internal functions, inline functions and template instantiations. `nm -gU` lists defined global symbols:

```text
$ clang++ -std=c++2c -O0 -shared polygon.cpp distance.cpp -o libgeo_def.dylib
$ nm -gU libgeo_def.dylib | c++filt | cut -c 20-
double geo::sq<double>(double)
geo::detail::cross(geo::Point, geo::Point)
geo::Polygon::add(geo::Point)
geo::distance(geo::Point, geo::Point)
geo::Polygon::area() const
geo::Polygon::size() const
geo::Polygon::describe() const
std::__1::allocation_result<...> std::__1::allocator_traits<...>::allocate_at_least[abi:nqe230103]<...>(...)
geo::Point& std::__1::vector<geo::Point, ...>::emplace_back[abi:nqe230103]<geo::Point const&>(geo::Point const&)
... (15 in total)
```

(The `std::` parts of the output are abbreviated for layout.)

`detail::cross` is exported: callers can declare and call it, it has become part of the ABI, and the library author can no longer change its signature freely. `Polygon::size()` and `sq<double>` are an inline function and a template from the header; at `-O0` they weren't inlined, each produced a weak definition, and those were exported too. There are also 8 member template instantiations of `std::vector<geo::Point>`, which come from libc++'s headers and which the library author never meant to provide.

These extra exports have three costs: callers may depend on what should be internal implementation; the dynamic loader has a bigger symbol table to process; and same-named weak definitions in different libraries get merged (there is an example later).

### `-fvisibility=hidden` plus an export macro

`-fvisibility=hidden` changes the default visibility to hidden, and `__attribute__((visibility("default")))` then explicitly marks the entities to export. It is usually wrapped in a macro that expands to the export attribute when building the library and to nothing when using it, which is the `GEO_API` at the top of `geo.h`:

```text
$ clang++ -std=c++2c -O0 -DGEO_BUILD -fvisibility=hidden -shared polygon.cpp distance.cpp -o h0.dylib
$ nm -gU h0.dylib | c++filt | cut -c 20-
geo::Polygon::add(geo::Point)
geo::distance(geo::Point, geo::Point)
geo::Polygon::area() const
geo::Polygon::size() const
geo::Polygon::describe() const
```

When `GEO_API` is on a class, all of its member functions, its vtable and its typeinfo are exported, so the inline `size()` is still there. Adding `-fvisibility-inlines-hidden` hides inline member functions as well:

| Build on our test machine | Exports at `-O0` | Exports at `-O2` |
|---|---|---|
| Default | 15 | 5 (`size`, `sq` and the `std::vector` instantiations were inlined away; `detail::cross` remains) |
| `-fvisibility-inlines-hidden` | 6 (`detail::cross` and `sq<double>` remain) | |
| `-fvisibility=hidden` + `GEO_API` | 5 | 4 |
| The previous row plus `-fvisibility-inlines-hidden` | 4 | 4 |

Two points are worth noting. First, the lower export count at `-O2` is only because functions were inlined, which changes with optimization level or compiler version; only visibility settings reliably decide what is exported. Second, `-fvisibility-inlines-hidden` doesn't affect instantiations of non-inline function templates, so `sq<double>` is still exported.

!!! tip "Recommended practice"
    Compile every TU of the library with `-fvisibility=hidden -fvisibility-inlines-hidden`, and mark the public interface one item at a time with the export macro. The export table is then an explicit list; adding an exported symbol requires a code change that is visible in review. CMake's `CXX_VISIBILITY_PRESET` and `GenerateExportHeader` exist for exactly this; see [[toolchain/cmake]].

The export macro is even more necessary on Windows. MSVC DLLs export nothing by default; exporting requires `__declspec(dllexport)`, and users should write `__declspec(dllimport)`, so the macro must expand to different things when building and when using the library (according to MSVC documentation).

You can also restrict exports at link time with a list, without changing the source. macOS's `ld` accepts `-exported_symbols_list`, a list of mangled names in which wildcards are allowed:

```text
$ cat exports.txt
__ZN3geo7Polygon*
__ZNK3geo7Polygon*
__ZN3geo8distance*
$ clang++ -std=c++2c -O0 -shared polygon.cpp distance.cpp -Wl,-exported_symbols_list,exports.txt -o le.dylib
$ nm -gU le.dylib | c++filt | cut -c 20-
geo::Polygon::add(geo::Point)
geo::distance(geo::Point, geo::Point)
geo::Polygon::area() const
geo::Polygon::size() const
geo::Polygon::describe() const
```

The corresponding mechanism in GNU ld and lld is the version script (`--version-script`), which can also attach version tags to symbols; glibc uses this to let old and new implementations of the same function coexist (according to documentation). The drawback of a list is that the compiler doesn't know which symbols will end up hidden and can't optimize accordingly; visibility attributes take effect at compile time.

### Visibility only matters at shared library boundaries

Symbols with hidden visibility are used as usual within a single link. Compiling the same library with `-fvisibility=hidden` and without defining `GEO_BUILD` (so nothing is exported), then packaging it as a static library, `app.cpp` still links:

```text
$ nm -m libh.a | c++filt | grep 'geo::distance'
0000000000000000 (__TEXT,__text) private external geo::distance(geo::Point, geo::Point)
$ clang++ -O2 app.cpp libh.a -o a2 && ./a2
polygon(3), area 6.0, d=5.0
$ nm -m a2 | c++filt | grep 'geo::distance'
0000000100000bbc (__TEXT,__text) non-external (was a private external) geo::distance(geo::Point, geo::Point)
```

`private external` is Mach-O's name for hidden visibility, which becomes `non-external` once linked into an image. Hidden visibility amounts to a third kind of linkage that doesn't exist in the standard: external linkage within one image, invisible outside it (see [[toolchain/linking-and-symbols]]).

## Which changes break the ABI

### A real binary break

An example of data member changes making object sizes disagree is in [[patterns/pimpl]]. Here is a subtler case: v2 of a library only reorders the declarations of two virtual functions.

<div class="compare" markdown="1">

```cpp title="v1/shape.h"
#pragma once
struct Shape {
  virtual ~Shape();
  virtual int width() const;
  virtual int height() const;
};
Shape* make_shape();
```

```cpp title="v2/shape.h"
#pragma once
struct Shape {
  virtual ~Shape();
  virtual int height() const;  // order swapped
  virtual int width() const;
};
Shape* make_shape();
```

</div>

```cpp title="shape.cpp (same in both versions)"
#include "shape.h"
Shape::~Shape() = default;
int Shape::width() const { return 20; }
int Shape::height() const { return 10; }
Shape* make_shape() { return new Shape; }
```

```cpp title="app.cpp" ifndr
#include <cstdio>
#include "shape.h"
int main() {
  Shape* s = make_shape();
  std::printf("width=%d height=%d\n", s->width(), s->height());
  delete s;
}
```

`app.cpp` is compiled against the v1 header and linked with the v1 library; then only `lib/libshape.dylib` is replaced with v2:

```text
$ ./app
width=20 height=10
$ rm lib/libshape.dylib && cp v2/libshape.dylib lib/
$ ./app
width=10 height=20
```

No error at all. Both versions of the library export exactly the same 9 symbols (`make_shape`, three destructor variants, `width`, `height`, the vtable, the typeinfo and the typeinfo name), and the dynamic loader found every symbol it wanted. The problem is in the caller's machine code:

```text
$ llvm-objdump -d --no-show-raw-insn app      # the two virtual calls in main, excerpt
ldr  x8, [x0]           ; load the vptr
ldr  x8, [x8, #0x10]    ; vtable slot 2: width in v1
blr  x8
...
ldr  x8, [x19]
ldr  x8, [x8, #0x18]    ; vtable slot 3: height in v1
blr  x8
```

A virtual call compiles to reading a vtable slot at a fixed offset (how slots are laid out is in [[toolchain/object-layout-and-vtables]]). In v2's vtable, offset `0x10` holds `height`, so the old program calling `width()` gets 10. If the two swapped virtual functions had different parameter types, the result wouldn't just be a wrong value; arguments would be passed with the wrong convention, usually crashing outright.

To the standard, `Shape` has two different definitions in this program, violating item 4 of [[basic.def.odr#16]] (each definition consists of the same sequence of tokens), which is {{ifndr}}. The linker and loader only compare symbol names, so they can't tell.

### Changing inline function bodies and default arguments

Another class of change doesn't break layout, but leaves callers using the old behavior:

<div class="compare" markdown="1">

```cpp title="v1/net.h"
#pragma once
inline int max_retries() { return 3; }
int connect(int timeout_ms = 1000);
int lib_max_retries();
```

```cpp title="v2/net.h"
#pragma once
inline int max_retries() { return 5; }
int connect(int timeout_ms = 5000);
int lib_max_retries();
```

</div>

```cpp title="net.cpp"
#include "net.h"
int connect(int timeout_ms) { return timeout_ms; }
int lib_max_retries() { return max_retries(); }
```

```cpp title="app.cpp"
#include <cstdio>
#include "net.h"
int main() {
  std::printf("timeout=%d retries app=%d lib=%d\n",
              connect(), max_retries(), lib_max_retries());
}
```

`app` is compiled against v1, and the v2 library is swapped in at run time. Results for several combinations of optimization levels on our test machine:

| `app` | Library | Output |
|---|---|---|
| `-O2`, v1 library | `-O2` | `timeout=1000 retries app=3 lib=3` |
| `-O2` | Replaced with v2, `-O2` | `timeout=1000 retries app=3 lib=5` |
| `-O0` | Replaced with v2, `-O2` | `timeout=1000 retries app=3 lib=5` |
| `-O0` | Replaced with v2, `-O0` | `timeout=1000 retries app=3 lib=3` |

Default arguments are evaluated at the call site ([[dcl.fct.default#1]], [[dcl.fct.default#9]]): `connect()` is compiled as `connect(1000)`, with the value in the caller's machine code. Switching the library to v2 can't change it. This breaks no rule: [[dcl.fct.default#4]] only requires an inline function to have the same default arguments in every TU, and a non-inline function may legitimately have different default arguments in different TUs. So changing a default is a change that is source-compatible but has no effect in binaries; old programs must be recompiled to get the new value.

The two definitions of `max_retries()` differ, violating [[basic.def.odr#16]], which is {{ifndr}}. The last row is the most telling: when both sides are `-O0`, both `app` and the library export a weak definition of `max_retries()`, `dyld` merges them into one at load time, and the call inside the library also uses the v1 version from `app`. The same kind of problem when one program links two versions of the same library is covered in [[toolchain/dependencies]].

### Classifying changes

The table classifies changes by whether callers need recompiling. "Compatible" means an old caller, not recompiled, behaves correctly with the new library.

| Change | Result | Reason |
|---|---|---|
| Adding a non-virtual, non-inline free or member function | Compatible | Only adds exported symbols |
| Adding an overload | Compatible | Different mangled name; the old symbol is still there |
| Changing the implementation of a non-inline function | Compatible | Only code inside the library changes |
| Removing or renaming an exported function, changing parameter types | Fails at load time | The mangled name changes and the old symbol can't be found |
| Changing the return type of a non-template function | Silent break | Mangled names don't include the return type ([[toolchain/name-mangling]]) |
| Adding, removing or reordering data members, changing member types | Silent break | Callers allocate and access objects with the old size and offsets; see [[patterns/pimpl]] |
| Adding, removing or reordering virtual functions, adding a base class | Silent break | vtable slots and base class offsets change |
| Appending a virtual function at the end | Breaks if callers derive from the class | The derived class's own vtable has no new slot |
| Changing the body of an inline function, template or `constexpr` function | Silent semantic break | The body is already compiled into the caller; see the previous section |
| Changing a default argument | Old callers keep the old value | Evaluated at the call site |
| Changing an enumeration's underlying type (`enum E : std::uint8_t` to `: int`) | Silent break | The layout of structs containing it changes; the mangled name has only the enumeration's name, not its underlying type |
| Making a function inline, or the reverse | When made inline, old callers may not find the symbol | Inline functions aren't guaranteed to produce an exported symbol |
| Changing the type of a `std::` member of an exported type, or switching standard libraries | Depends | See below |

The last few kinds are dangerous because they satisfy everything dynamic linking requires: the symbols are all there. Only tools that compare the ABIs of two versions can find them. On Linux, libabigail's `abidiff` and abi-compliance-checker are commonly used; they read debug info and report changes in type layout and vtables (according to documentation; not installed on our test machine).

### Standard library types are ABI too

When `std::string` or `std::vector` appear in a public interface, their layouts become part of the library's ABI, and they are decided by the standard library implementation, not by the library author.

libstdc++ is a typical example (according to libstdc++'s documentation on its dual ABI). C++11 forbade copy-on-write `std::string` and required `std::list::size()` to be constant-time, both of which change layout. Since GCC 5, the new implementations live in the inline namespace `std::__cxx11`, the old ones are kept, and the macro `_GLIBCXX_USE_CXX11_ABI` chooses between them. When code compiled with the two settings is mixed, functions involving `std::string` have different mangled names (`std::__cxx11::basic_string` versus `std::basic_string`), which shows up as undefined references at link time rather than memory errors at run time.

libc++ puts all its entities in `std::__1`, where the `1` is its ABI version number (mangling details in [[toolchain/name-mangling]]). In the output on our test machine, libc++'s internal functions also carry tags such as `[abi:nqe230103]`. According to the comments in libc++'s header `__configuration/attributes.h`, this tag encodes the library version, whether exceptions are enabled and the hardening mode; it is applied to functions marked `_LIBCPP_HIDE_FROM_ABI`, which aren't exported anyway, so that same-named internal functions compiled with different configurations aren't merged by the linker.

The layout of `std::` types is also affected by compile options, such as debug iterators and libc++'s bounded iterators; the table of these options is in [[toolchain/dependencies]].

!!! warning "Conclusion"
    Use `std::` types in a shared library's public interface only if the library and all its callers are built with the same compiler, the same standard library and the same options. If that can't be guaranteed, you need the C interface of the next section.

## The most stable boundary: a C interface

The C ABI is specified by each platform's calling convention documents and has stayed unchanged for years: function names aren't mangled, structs are laid out in field order, and there are no exceptions, virtual functions or templates. C++ connects to it through **language linkage**. [[dcl.link#3]] requires every implementation to support `extern "C"`, and the note in [[dcl.link#1]] says a language linkage may be associated with a particular form of names and a calling convention, which is the basis on which implementations generate C-style symbols.

### Opaque handles

```c title="geo_c.h"
#ifndef GEO_C_H
#define GEO_C_H
#include <stddef.h>
#ifdef __cplusplus
extern "C" {
#endif
#define GEO_EXPORT __attribute__((visibility("default")))

typedef struct geo_polygon geo_polygon;     /* opaque handle */
typedef enum { GEO_OK = 0, GEO_EINVAL = 1, GEO_ENOMEM = 2 } geo_status;

GEO_EXPORT geo_polygon* geo_polygon_create(void);
GEO_EXPORT void         geo_polygon_destroy(geo_polygon* p);
GEO_EXPORT geo_status   geo_polygon_add(geo_polygon* p, double x, double y);
GEO_EXPORT geo_status   geo_polygon_area(const geo_polygon* p, double* out);
GEO_EXPORT const char*  geo_last_error(void);

#ifdef __cplusplus
}
#endif
#endif
```

`geo_polygon` is only declared in the header, never defined; callers can only hold pointers to it and don't know its size or members. This is pimpl in C: the library can change `geo_polygon`'s contents at will without affecting callers' binaries.

The implementation is written in C++, and every exception is converted to an error code at the boundary:

```cpp title="geo_c.cpp"
#include "geo_c.h"
#include <cmath>
#include <new>
#include <stdexcept>
#include <string>
#include <vector>

struct geo_polygon {                          // only the library knows its definition
  std::vector<std::pair<double, double>> pts;
};

namespace {
thread_local std::string last_error;

template <class F> geo_status guard(F f) noexcept {   // exceptions don't cross the C boundary
  try { f(); return GEO_OK; }
  catch (const std::bad_alloc&)          { last_error = "out of memory"; return GEO_ENOMEM; }
  catch (const std::invalid_argument& e) { last_error = e.what(); return GEO_EINVAL; }
  catch (...)                            { last_error = "unknown"; return GEO_EINVAL; }
}
}

geo_polygon* geo_polygon_create(void) { return new (std::nothrow) geo_polygon; }
void geo_polygon_destroy(geo_polygon* p) { delete p; }

geo_status geo_polygon_add(geo_polygon* p, double x, double y) {
  return guard([&] {
    if (!p || !std::isfinite(x) || !std::isfinite(y))
      throw std::invalid_argument("bad point");
    p->pts.emplace_back(x, y);
  });
}

geo_status geo_polygon_area(const geo_polygon* p, double* out) {
  return guard([&] {
    if (!p || !out) throw std::invalid_argument("null argument");
    double s = 0;
    auto& v = p->pts;
    for (std::size_t i = 0; i < v.size(); ++i) {
      auto [x0, y0] = v[i];
      auto [x1, y1] = v[(i + 1) % v.size()];
      s += x0 * y1 - x1 * y0;
    }
    *out = std::fabs(s) / 2;
  });
}

const char* geo_last_error(void) { return last_error.c_str(); }
```

```c title="client.c"
#include <math.h>
#include <stdio.h>
#include "geo_c.h"
int main(void) {
  geo_polygon* p = geo_polygon_create();
  geo_polygon_add(p, 0, 0);
  geo_polygon_add(p, 4, 0);
  geo_polygon_add(p, 4, 3);
  double a;
  if (geo_polygon_area(p, &a) == GEO_OK) printf("area=%.1f\n", a);
  if (geo_polygon_add(p, NAN, 0) != GEO_OK) printf("error: %s\n", geo_last_error());
  geo_polygon_destroy(p);
}
```

```text
$ clang++ -std=c++2c -O2 -fvisibility=hidden -shared geo_c.cpp -install_name @rpath/libgeo_c.dylib -o libgeo_c.dylib
$ clang -std=c17 client.c -L. -lgeo_c -Wl,-rpath,@executable_path -o client && ./client
area=6.0
error: bad point
$ nm -gU libgeo_c.dylib
0000000000000ce0 T _geo_last_error
00000000000005f4 T _geo_polygon_add
0000000000000900 T _geo_polygon_area
0000000000000580 T _geo_polygon_create
00000000000005ac T _geo_polygon_destroy
$ otool -L client
client:
	@rpath/libgeo_c.dylib (compatibility version 0.0.0, current version 0.0.0)
	/usr/lib/libSystem.B.dylib (compatibility version 1.0.0, current version 1356.0.0)
```

The export table is exactly the 5 functions in the header, with only Mach-O's leading underscore added. `client` doesn't depend on libc++; `std::vector` and `std::string` exist only inside the library, which could even be rebuilt with a different standard library implementation.

### Design rules

- **Handles with paired create and destroy functions.** Callers never `sizeof` and never `free` the library's objects.
- **Exceptions don't cross the boundary.** The standard allows `extern "C"` functions to throw, but a C caller can't handle the exception, and when it passes through frames compiled from C code without unwind information, the program usually terminates outright (mechanism in [[toolchain/exception-implementation]]). Wrap each exported function in a `noexcept` `catch (...)` that converts to an error code.
- **Use only fixed-width scalars, pointers and C structs.** The size of an enumeration in C is implementation-defined; when a fixed size is needed, make the parameter type `int32_t` and use the enumerators only as constants.
- **Leave room for extension when passing structs.** A common approach is for the first field to hold the struct's size, with the library reading fields according to the size the caller passes; or don't expose the struct at all and provide only getters and setters.
- Callbacks take a `void*` user data argument so callers can pass their own state back, and callbacks themselves must not throw either.

### Restoring C++ usage on top of the C interface

A C interface is awkward to use, so a header-only C++ wrapper can be layered on top. This layer is compiled with the caller, using the same compiler and the same standard library as the caller, so using `std::unique_ptr` and exceptions here is safe:

```cpp title="geo.hpp"
#pragma once
#include <memory>
#include <stdexcept>
#include "geo_c.h"

namespace geo {
class Polygon {            // header only, compiled together with the caller
public:
  Polygon() : p_(geo_polygon_create()) {
    if (!p_) throw std::bad_alloc();
  }
  void add(double x, double y) { check(geo_polygon_add(p_.get(), x, y)); }
  double area() const {
    double a;
    check(geo_polygon_area(p_.get(), &a));
    return a;
  }
private:
  static void check(geo_status s) {
    if (s != GEO_OK) throw std::runtime_error(geo_last_error());
  }
  struct Deleter { void operator()(geo_polygon* p) const { geo_polygon_destroy(p); } };
  std::unique_ptr<geo_polygon, Deleter> p_;
};
}
```

Rewriting the logic of `client.c` with this wrapper gave the same output, with the `NAN` step becoming a `std::runtime_error` thrown on the caller's side. This structure, wide at both ends and narrow in the middle, is often called an hourglass interface: C++ implementation, C boundary, C++ wrapper. The cost is an extra level of indirection per call, and two layers of interface to maintain by hand.

## Exceptions and RTTI across shared libraries

If the interface really must pass C++ exceptions or polymorphic objects, you have to care about something the standard takes for granted but implementations find far from simple: type identity. `catch (const ParseError&)` catches an exception only if the exception object's type and the handler's type are the same ([[except.handle#3]]); `typeid(a) == typeid(b)` is true when both describe the same type ([[type.info#3]]). Implementations represent types with typeinfo objects, so the question becomes whether the library's `ParseError` typeinfo and the caller's are considered the same.

```cpp title="err.h"
#pragma once
#include <stdexcept>
#define FN_API __attribute__((visibility("default")))
#ifndef ERR_API
#  define ERR_API
#endif
struct ERR_API ParseError : std::runtime_error {   // no key function
  using std::runtime_error::runtime_error;
};
struct ERR_API Node { virtual ~Node() = default; };
struct ERR_API Leaf : Node { int v = 42; };
FN_API void parse(const char* s);
FN_API Node* make_node();
```

```cpp title="lib.cpp"
#include "err.h"
void parse(const char* s) { throw ParseError(s); }
Node* make_node() { return new Leaf; }
```

```cpp title="app.cpp"
#include <cstdio>
#include <typeinfo>
#include "err.h"
int main() {
  Node* n = make_node();
  std::printf("dynamic_cast: %s\n", dynamic_cast<Leaf*>(n) ? "ok" : "null");
  std::printf("typeid equal: %d\n", typeid(*n) == typeid(Leaf));
  try { parse("bad"); }
  catch (const ParseError& e) { std::printf("caught ParseError: %s\n", e.what()); }
  catch (const std::exception& e) { std::printf("caught std::exception: %s\n", e.what()); }
}
```

`app.cpp` is always compiled with default options; the library is built three ways:

| How the library is built | `dynamic_cast` | `typeid` equal | `catch` |
|---|---|---|---|
| Default visibility | ok | 1 | `ParseError` |
| `-fvisibility=hidden`, types without the export macro | ok | 0 | Falls through to `std::exception` |
| `-fvisibility=hidden`, `-DERR_API=__attribute__((visibility("default")))` | ok | 1 | `ParseError` |

The second row is the problem: the `ParseError` thrown in the library isn't caught by `catch (const ParseError&)`, and `typeid` also thinks `*n` isn't a `Leaf`.

The reason is explained in detail in libc++'s `typeinfo` header. None of the three types has a key function, so their typeinfo is generated separately in each image that uses them. Our test machine is Apple arm64, and on this platform libc++ does the following: typeinfo that would otherwise be generated as a weak definition with default visibility is instead hidden in each image, and the top bit of the name pointer in the typeinfo is set to 1, meaning there may be several copies, so comparison falls back to comparing name strings; that is why rows one and three succeed (`nm -m` shows the library's typeinfo as `was a private external` in all three builds). Types with hidden visibility are considered unique within an image and are compared only by address, so the two copies across images are two different types.

`dynamic_cast` succeeded in all three cases. It doesn't go through the comparison in the header; it calls `__dynamic_cast` in the runtime library libc++abi (visible with `nm -u app`), whose comparison strategy in the system runtime differs from `typeid`'s. That `typeid` and `catch` failed while `dynamic_cast` succeeded on our test machine is just one observation and can't be relied on.

On other platforms the rules differ again (according to each library's headers and documentation): libc++ on Linux compares only by address by default, relying on the dynamic loader to merge the default-visibility typeinfo from all images into one; libstdc++ compares name strings by default. In all these implementations, a type with hidden visibility may be treated as different types across images.

When the type has a key function, the problem moves forward to link time. Declare `ParseError`'s destructor as `~ParseError() override;` and define it in `lib.cpp`, and the typeinfo is generated only in the library; with the library built with `-fvisibility=hidden` and the type not exported, the caller fails to link:

```text
Undefined symbols for architecture arm64:
  "typeinfo for ParseError", referenced from:
      GCC_except_table0 in app-7e2265.o
ld: symbol(s) not found for architecture arm64
```

`GCC_except_table0` is `main`'s LSDA, in which the `catch` clause records the type to match (see [[toolchain/exception-implementation]]).

!!! tip "Recommended practice"
    For types that callers will `catch`, `dynamic_cast` or `typeid`, put the export macro on the class and give them a key function defined in a `.cpp` file of the library (usually the destructor), so that the vtable and typeinfo have a single strong definition in the library. Like C++ standard library types, these types are part of the ABI.

The standard doesn't know images exist. To it, there is only one `ParseError` type in the program, and the result in the second row doesn't conform to [[except.handle#3]]. This is where implementations depart from the standard model in order to support visibility.

## Who allocates, who frees

When a library returns a block of memory, how the caller frees it is also part of the ABI. Below, v1 of a library allocates with `new[]` and the caller frees with `delete[]`, which looks fine:

```cpp title="buf.h"
#pragma once
#define API __attribute__((visibility("default")))
API char* make_buffer(int n);
API void free_buffer(char* p);
```

<div class="compare" markdown="1">

```cpp title="buf_v1.cpp"
#include "buf.h"
char* make_buffer(int n) {
  return new char[n];
}
void free_buffer(char* p) {
  delete[] p;
}
```

```cpp title="buf_v2.cpp"
#include "buf.h"
#include <cstddef>
namespace {
alignas(16) char arena[1 << 16];
std::size_t used = 0;
}
char* make_buffer(int n) {  // now uses an arena
  char* p = arena + used;
  used += (n + 15) & ~15;
  return p;
}
void free_buffer(char*) {}
```

</div>

```cpp title="app.cpp"
#include <cstdio>
#include "buf.h"
int main(int argc, char**) {
  char* p = make_buffer(64);
  if (argc > 1) { delete[] p; std::puts("app delete[] done"); }
  else          { free_buffer(p); std::puts("free_buffer done"); }
}
```

```text
$ ./app; ./app x                     # v1
free_buffer done
app delete[] done
$ ./app; ./app x                     # switched to v2, app not recompiled
free_buffer done
Abort trap: 6
```

v2 only changed the library's internal implementation, not a single exported function, yet the caller that called `delete[]` itself crashed. By the standard, the operand of `delete[]` must come from a previous array new-expression, otherwise the behavior is undefined ([[expr.delete#2]]). Under v1 the caller happened to meet that condition, but that was an implementation detail of the library, not its interface.

How memory is allocated can change with the library's version, compile options or platform. On Windows, each DLL may link a different C runtime with its own heap, and memory `malloc`ed in one DLL being `free`d in another is a common cause of crashes (according to MSVC documentation). On macOS and Linux the whole process usually shares one `malloc`, so such errors tend to stay hidden until the library switches allocators.

The rule is simple: **whoever allocates frees**. The library provides paired create and destroy functions; a C++ interface can return a `std::unique_ptr<T, D>` whose deleter `D` calls the library's exported destroy function, like the `Deleter` in `geo.hpp` in the previous section.

!!! pitfall "Replacing operator new in a library affects the whole process"
    The most direct idea for making a library use its own allocator is to define `operator new[]` and `operator delete[]` in the library. Our experiment showed that even with the library built with `-fvisibility=hidden`, these two functions were still exported, because libc++'s headers declare them with default visibility; marking them hidden explicitly makes Clang report `visibility does not match previous declaration`. In an executable linking this library, `delete[]` was bound to the library's version (`nm -m` shows `(from libbuf)`). This is consistent with the standard: a replacement function replaces it for the whole program ([[dcl.fct.def.replace#1]]), and there is no such thing as an `operator new` that applies to one library only. A library that wants a private allocator should give it its own name.

## Versions: install name, compatibility version and soname

### macOS: install name

A shared library records an **install name** at build time; programs that link it copy the name verbatim into their dependency list, and at run time `dyld` looks up the library by it. Two version numbers are recorded as well: the current version is this file's version, and the compatibility version is the earliest version it is compatible with.

```text
$ clang++ -std=c++2c -O2 -fvisibility=hidden -shared geo_c.cpp -o lib/libgeo.1.2.0.dylib \
    -install_name @rpath/libgeo.1.dylib -compatibility_version 1.0.0 -current_version 1.2.0
$ ln -s libgeo.1.2.0.dylib lib/libgeo.1.dylib && ln -s libgeo.1.dylib lib/libgeo.dylib
$ otool -l lib/libgeo.1.2.0.dylib | grep -A5 LC_ID_DYLIB
          cmd LC_ID_DYLIB
      cmdsize 48
         name @rpath/libgeo.1.dylib (offset 24)
   time stamp 1 Wed Dec 31 18:00:01 1969
      current version 1.2.0
compatibility version 1.0.0
$ clang client.c -Llib -lgeo -Wl,-rpath,@executable_path/lib -o client
$ otool -L client | sed -n 2p
	@rpath/libgeo.1.dylib (compatibility version 1.0.0, current version 1.2.0)
```

Each of the three names has its purpose:

- `libgeo.dylib` is used only at link time; it is what `-lgeo` finds, and points at the version currently to be linked;
- `libgeo.1.dylib` is the install name, by which the program loads the library at run time. The `1` is the ABI's major version, increased only for incompatible changes;
- `libgeo.1.2.0.dylib` is the actual file.

`@rpath` means search the list of paths recorded by the program (`LC_RPATH`, written by `-Wl,-rpath,...`), and `@executable_path` and `@loader_path` are the directories of the executable and of the image initiating the load, respectively. This way the library and the program can be moved together without hard-coding absolute paths.

The compatibility version was meant for a check: the program records the library's compatibility version at link time, and `dyld` refuses to load a library whose current version is lower (according to Apple's documentation). In our experiment, `client` was linked against a library with compatibility version 1.3.0, a library with current version 1.2.0 was swapped in at run time, and `dyld` loaded and ran it without complaint. So this check shouldn't be relied on.

### Linux: soname

The ELF counterpart is the **soname** (according to documentation; not verified on our test machine). At build time, `-Wl,-soname,libgeo.so.1` writes the library's `DT_SONAME`; when a program links, it records it in its own `DT_NEEDED`, and at run time `ld.so` looks the library up by soname. The file layout is the same as on macOS: `libgeo.so` (the development symlink) → `libgeo.so.1` (the soname) → `libgeo.so.1.2.0` (the actual file). `readelf -d` shows these two fields, and `ldconfig` maintains the soname links.

The convention is the same on both platforms: **increase the major version when the ABI becomes incompatible**; libraries of the old and new major versions can be installed side by side, and old programs keep loading the old library. Compatible changes increase only the minor version, leaving the install name or soname unchanged.

## Numbering the ABI with inline namespaces

Install names and sonames govern the whole library. An inline namespace ([[g:inline-namespace]]) puts the version number into every symbol name: members of an inline namespace can be used as if they were members of the enclosing namespace ([[namespace.def#6]]), but their mangled names include the inline namespace's name.

<div class="compare" markdown="1">

```cpp title="v1/cfg.h"
#pragma once
namespace cfg {
inline namespace v1 {
struct Options { int threads; };
int run(const Options& o);
}
}
```

```cpp title="v2/cfg.h"
#pragma once
namespace cfg {
inline namespace v2 {   // layout changed
struct Options {
  long budget;
  int threads;
};
int run(const Options& o);
}
}
```

</div>

```cpp title="cfg.cpp"
#include "cfg.h"
int cfg::run(const Options& o) { return o.threads; }
```

```cpp title="app.cpp"
#include <cstdio>
#include "cfg.h"
int main() {
  cfg::Options o{};          // users write cfg::Options as usual
  o.threads = 8;
  std::printf("run -> %d\n", cfg::run(o));
}
```

`app` is compiled against v1, and then the v2 library is swapped in:

```text
$ nm -gU v1/libcfg.dylib v2/libcfg.dylib
0000000000000310 T __ZN3cfg2v13runERKNS0_7OptionsE
0000000000000310 T __ZN3cfg2v23runERKNS0_7OptionsE
$ ./app
run -> 8
$ rm lib/libcfg.dylib && cp v2/libcfg.dylib lib/ && ./app
dyld[97296]: Symbol not found: __ZN3cfg2v13runERKNS0_7OptionsE
  Referenced from: <D4C64185-...> .../app
  Expected in:     <3E3C62B2-...> .../lib/libcfg.dylib
Abort trap: 6
```

Without the inline namespace, this upgrade would have the library read `threads` with v2's layout and get a wrong value; with it, the same error is stopped at load time.

A library can also provide both versions at once: compile `cfg.cpp` twice, including the v1 and the v2 header respectively, and link both object files into the same shared library. A library built this way on our test machine exported both `cfg::v1::run` and `cfg::v2::run`; the old `app` ran correctly without recompiling, and newly compiled programs use v2. How inline namespaces turn an ODR violation into two distinct entities when a program links two versions of the same library is covered in [[toolchain/dependencies]].

!!! pitfall "Define with qualified names in implementation files"
    `cfg.cpp` was first written as `namespace cfg { int run(const Options& o) { ... } }`. The library built fine, but linking `app` reported `cfg::v1::run(cfg::v1::Options const&)` as undefined; what the library exported was `cfg::run(cfg::v1::Options const&)`. An unqualified declaration declares a new function in its enclosing namespace `cfg`; its target scope differs from that of `v1::run`, so it is an overload ([[dcl.meaning.general#3]]). Only when it is defined with the qualified name `int cfg::run(...)` does lookup consider the declarations in the inline namespace ([[basic.scope.scope#7]]) and match it to `v1::run`.

libc++'s `std::__1` is this mechanism. In the libc++ on our test machine, `__config_site` defines `_LIBCPP_ABI_VERSION 1` and `_LIBCPP_ABI_NAMESPACE __1`; `__configuration/abi.h` enables a batch of layout-changing changes when the ABI version is at least 2. Choosing a higher version when building libc++ also changes the inline namespace's name with the configuration, so old and new binaries can't be connected by mistake.

## Checklist

When designing a C++ library shipped as a shared library, check each item:

| Question | Recommendation |
|---|---|
| Which symbols are exported? | `-fvisibility=hidden -fvisibility-inlines-hidden`, with the export macro marking items one by one; check the export table with `nm -gU` before release |
| Do callers need to know the class size? | If not, use pimpl or an opaque handle |
| Are there virtual functions that will be extended later? | Freeze a public polymorphic interface once released; extend by adding new interface classes |
| Are there inline functions, templates or default arguments in headers that will change? | Move logic that will change into `.cpp` files; use overloads instead of default arguments |
| Are there `std::` types in the public interface? | Only if callers are sure to use the same standard library and options; otherwise use a C interface |
| Exception and polymorphic types | Export these types and give them key functions |
| Who frees memory? | The library provides destroy functions, or returns a `unique_ptr` with the library's deleter |
| Incompatible changes | Switch the inline namespace; increase the major version of the install name or soname |

## Questions

!!! question "1"
    A library's public class `Logger` has virtual functions, and its destructor is written in the header as `virtual ~Logger() = default;`. The library is built with `-fvisibility=hidden`, and `Logger` carries the export macro. A caller writes `struct MyLogger : Logger { ... };`. v2 appends a virtual function `flush()` at the end of `Logger`, which the library calls internally on `Logger&`s passed to it. What happens to the old caller?

<details markdown="1">
<summary>Answer</summary>

`MyLogger`'s vtable was generated by the caller from v1's definition and has only v1's slots, followed directly by any virtual functions `MyLogger` itself adds. The library reads the slot where `flush` would be according to v2's layout, and gets one of `MyLogger`'s virtual functions or memory past the end of the vtable; what it calls isn't `flush`. Appending a virtual function is only compatible if nobody derives from the class and the library doesn't call the new virtual function on objects from outside. By the standard, `Logger` has two different definitions in the program, violating [[basic.def.odr#16]], which is {{ifndr}}.
</details>

!!! question "2"
    Does changing the default of `int connect(int timeout_ms = 1000);` to 5000 break the ABI? What if `connect` is an inline function?

<details markdown="1">
<summary>Answer</summary>

It breaks neither symbols nor layout, but old callers won't get the new value without recompiling, because default arguments are evaluated at the call site ([[dcl.fct.default#1]]). A non-inline function having different default arguments in different TUs is legal; an inline function requires the accumulated default arguments to be the same in every TU, otherwise it is {{ifndr}} ([[dcl.fct.default#4]]). To let the library decide the default, use an overload instead: `int connect();` calls `connect(5000)` inside the library.
</details>

!!! question "3"
    A library is built with `-fvisibility=hidden` and exports only a C interface. Are the member functions of `std::vector<int>` it uses internally the same code as the member functions of `std::vector<int>` in the calling program? Does this violate the ODR?

<details markdown="1">
<summary>Answer</summary>

They aren't the same copy. Hidden visibility gives each image its own instantiations, which aren't merged across images. As long as both sides are compiled with the same version of the standard library headers and the same options, each copy of the definition consists of the same tokens and meets the requirements of [[basic.def.odr#16]]; multiple copies in themselves don't violate the ODR, and their behavior is equivalent. If the headers differ between the two sides (say the library was built with an older libc++), in the standard's model there are two different definitions; in practice, since no `std::` object crosses the C boundary, the two copies never touch each other and nothing goes wrong. This is exactly why a C interface can isolate standard library versions.
</details>
