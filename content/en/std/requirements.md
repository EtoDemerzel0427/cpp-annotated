---
title: "Library-wide requirements: contents, headers, modules and use"
summary: "Basic rules that apply to the whole standard library: library entities are all in std (possibly in an inline namespace), how names in library specifications are looked up, C++ headers versus C headers, import std and std.compat, the library subset of freestanding implementations, and where, in what order and with what linkage headers are used."
updated: 2026-10-19
---

!!! tldr
    - Library entities are all in `std`, but may be hidden in an unspecified inline namespace (in libc++ it is `std::__1`), so forward-declaring types in `std` yourself doesn't work.
    - Including `<cstdio>` guarantees only `std::printf`, and including `<stdio.h>` guarantees only `::printf`; whether the other half exists is unspecified.
    - `import std;` exports everything in `std`, but neither macros nor the global C names; for the latter, use `import std.compat;`.
    - A header may be included only outside of any declaration and before the first use of an entity it declares; names brought in indirectly through other headers aren't portable.
    - The language linkage of C library functions is implementation-defined, and the only reliable way to declare them is to include the corresponding header.

[[requirements]] holds the rules that apply to the whole standard library; this page covers the organization of the library ([organization]) and how programs use the library ([using]). Requirements on types, constraints on programs and constraints on implementations are in [[utility.requirements]], [[constraints]] and [[conforming]] respectively.

## Which namespace library entities are in [contents]

### Why forward-declaring a type in std fails (¶2)

```cpp ub
namespace std { template<class T, class A> class vector; }  // UB: adds a declaration to std
#include <vector>
std::vector<int> v;   // libc++: error: reference to 'vector' is ambiguous
int main() {}
```

Adding declarations to `std` is undefined behavior in itself ([[namespace.std#1]]), and on libc++ it also makes compilation fail outright. The reason is in ¶2.

¶2 All library entities except `operator new` and `operator delete` are defined within the namespace `std` or namespaces nested within `std`. It is unspecified whether names declared in a specific namespace are declared directly in that namespace or in an inline namespace inside it. A footnote explains that this gives implementations a way to support multiple configurations of the library using inline namespaces.

In practice, implementations use it like this:

| Implementation | Inline namespace | Purpose |
|---|---|---|
| libc++ | `std::__1` (`_LIBCPP_ABI_NAMESPACE`, defined in `__config_site` in the installation we tested) | ABI versioning: a future incompatible ABI can switch to `__2`, and old and new binaries can be linked into the same program |
| libstdc++ | `std::__cxx11` (only for a few components such as `basic_string` and `list`) | The dual ABI since C++11: symbol names of the new `std::string` (no longer copy-on-write) carry `__cxx11` to distinguish them from the old ABI |

So the real name of `std::vector<int>` in libc++ is `std::__1::vector<int, std::__1::allocator<int>>`, which is what you see in linker errors and symbol names. In the program above, the `std::vector` declared by hand and the real `std::__1::vector` are two different templates, both visible to name lookup, hence the ambiguity. To forward-declare iostream types you can use `<iosfwd>`; for other types you have to include the corresponding header.

### How names in library specifications are looked up (¶3)

¶3 In Clauses 17–33 and Annex D, the meaning of an unqualified name appearing in the specification of a declaration D is determined as if by unqualified name lookup ([[basic.lookup.unqual]]) in the context of D. Note 1 stresses that argument-dependent lookup (ADL) is not performed. Qualified names are likewise determined by qualified lookup at D. Example 1: the `is_array_v` mentioned in the specification of `std::to_array` is `::std::is_array_v`.

So when a specification says "*Effects*: Equivalent to: `return move(x);`", that `move` is `std::move`, and it won't be replaced via ADL just because the namespace of `x`'s type also has a `move`. Implementations must ensure this, which is why standard library source code writes `std::move(...)` and `std::forward<...>(...)` everywhere ([[global.functions#4]] restates this from the implementation's side).

There are a few exceptions:

- Note 2: operators in expressions aren't subject to this restriction ([[over.match.oper]]); see [[global.functions]].
- The meaning of `swap` is determined in the overload resolution context for swappable values ([[swappable.requirements]]), i.e. the two-step `using std::swap;` followed by an unqualified call `swap(a, b)`.
- `make_error_code`, `make_error_condition`, `from_stream` and `submdspan_mapping` are determined by ADL. They are customization points of the library: users define `make_error_code` for their own error enumerations, and `std::error_code`'s constructor finds it via ADL; they define `submdspan_mapping` for their own `mdspan` layouts, and `from_stream` for their own time types.

## Headers [headers]

### Two kinds of headers (¶1–¶3)

¶1 Each element of the library is declared or defined in some **header**. A footnote points out that a header is not necessarily a source file, and the name between `<` and `>` is not necessarily a valid file name ([[cpp.include]]); it is just that in practice every implementation uses files.

¶2 The C++ library headers are listed in Table 24; the current draft has 94 of them, from `<algorithm>` to `<version>`, including the newer `<contracts>`, `<meta>`, `<simd>`, `<hive>` and `<inplace_vector>`.

¶3 The facilities of the C standard library are provided by another 21 headers in Table 25: `<cassert>`, `<cctype>`, `<cerrno>`, `<cfenv>`, `<cfloat>`, `<cinttypes>`, `<climits>`, `<clocale>`, `<cmath>`, `<csetjmp>`, `<csignal>`, `<cstdarg>`, `<cstddef>`, `<cstdint>`, `<cstdio>`, `<cstdlib>`, `<cstring>`, `<ctime>`, `<cuchar>`, `<cwchar>`, `<cwctype>`. A footnote explains that `<stdnoreturn.h>` and `<threads.h>` intentionally have no C++ counterparts; C++ has `[[noreturn]]` and `<thread>`. The former `<ccomplex>`, `<cstdbool>` and others have been removed, and their names are reserved as [[zombie.names]].

### `<cname>` versus `<name.h>` (¶5, ¶9)

```cpp run ok
#include <cstdio>
int main() {
  std::printf("std\n");     // guaranteed to be available
  ::printf("global\n");     // available in all three major implementations, but not guaranteed by the standard
}
```

¶5 The contents of `<cname>` are the same as the corresponding C standard library `<name.h>`, but the declarations (except for names defined as macros in C) are within namespace `std`. It is unspecified whether these names are first declared in the global namespace and then brought into `std` by *using-declarations* ([[namespace.udecl]]).

¶9 The effect of including the `<name.h>` form is described in [support.c.headers]: the names are all in the global namespace. A footnote recommends the `<cname>` form unless a program needs strict compatibility with C. Taken together, the portable rule is:

| Header included | Guaranteed available | Availability unspecified |
|---|---|---|
| `<cstdio>` | `std::printf` | `::printf` |
| `<stdio.h>` | `::printf` | `std::printf` |

libc++ takes the approach ¶5 allows: `<cstring>` first includes C's `<string.h>`, putting the names in the global namespace, and then writes `using ::strlen _LIBCPP_USING_IF_EXISTS;` to bring them into `std`. So in libc++, `::strlen` and `std::strlen` are the same function. This is also the background of [[extern.types]]'s requirement that `::T` and `std::T` be the same type.

### Macros must be macros, functions must be functions (¶6–¶8)

¶6 Names defined as macros in C shall be defined as macros in C++ too, even if C grants license to implement them as functions. Note 2 lists `assert`, `offsetof`, `setjmp`, `va_arg`, `va_end` and `va_start`.

¶7 Names defined as functions in C shall be defined as functions in C++. C allows `<ctype.h>` to provide, in addition to the function prototype, a masking macro of the same name, such as `#define isdigit(c) (...)`; in C++ this would break `std::isdigit` (macros know nothing of namespaces), taking the address, and overloading, so it is prohibited. A footnote says that the only way to get the same inline effect is to provide inline function definitions. Whether you may take the address of `isdigit` is a separate question ([[namespace.std#6]]).

¶8 Identifiers that are keywords or operators in C++ shall not be defined as macros in standard library headers. C uses `<iso646.h>` to define `and`, `or`, `not` and so on as macros, whereas in C++ they are already alternative tokens ([[lex.digraph]]). A footnote says that including `<iso646.h>` has no effect.

### Importable headers (¶4)

¶4 The headers in Table 24 (for a freestanding implementation, the part it provides) are collectively called the [[g:importable-library-header|importable C++ library headers]], and can be imported as header units with an import declaration ([[module.import]]):

```cpp
import <vector>;                // imports the <vector> header unit
std::vector<int> vi;            // OK
```

The C facility headers of Table 25 aren't among them, so `import <cstdio>;` isn't guaranteed to work. These headers depend heavily on macros (`assert` changes with `NDEBUG`, and `errno` is itself a macro) and aren't suitable as header units.

### The `_s` functions of Annex K (¶10–¶11)

¶10 Annex K of the C standard defines a set of bounds-checking functions with an `_s` suffix, such as `memcpy_s`, `strcpy_s` and `fopen_s`; most take one more parameter than the unsuffixed version, giving the size of the result array. Whether these names are declared in the global namespace after including any C++ header is implementation-defined, and none of them are in `std`. Table 26 in ¶11 lists these names; they are also subject to [[macro.names]], so programs may not define them as macros.

In practice, MSVC's UCRT provides these functions (with meanings not entirely the same as Annex K), and glibc doesn't. So `std::memcpy_s` is always wrong, and `::memcpy_s` isn't portable.

## Rules for including headers [using.headers]

¶1 A program uses entities of the library through `#include` directives ([[cpp.include]]) or import declarations ([[module.import]]).

### Order and repeated inclusion (¶2)

¶2 A translation unit may include library headers in any order ([[lex.separate]]), and each header may be included more than once with the same effect as including it once. The exceptions are `<cassert>` and `<assert.h>`: the effect of each inclusion depends on the definition of `NDEBUG` at that point, as in C.

```cpp run ok
#define NDEBUG
#include <cassert>
void f() { assert(false); }      // assertion disabled
#undef NDEBUG
#include <cassert>               // redefines assert according to the current NDEBUG
void g(int x) { assert(x > 0); } // assertion enabled
int main() { f(); g(1); }
```

"Any order" is a requirement on the implementation: standard headers must not depend on the order of inclusion ([[res.on.headers#2]] restates this from the implementation's side).

### Placement and timing (¶3)

¶3 A header shall be included only outside of any declaration or definition; in a module unit, only in the global module fragment. And it shall be included, or the corresponding header unit imported, before the first reference in the translation unit to any entity declared in that header. A program that violates these rules is ill-formed, no diagnostic required ({{ifndr}}).

```cpp ifndr
namespace N {
#include <vector>    // IFNDR: a standard header included inside a declaration
}
int main() {}
```

Although no diagnostic is required, such code in practice almost always fails to compile, because the declarations in the header end up in the wrong namespace. libc++ (with Clang 23) reports "'operator new' cannot be declared inside a namespace".

More insidious is using before including:

```cpp ifndr
#include <string>
std::size_t n = std::strlen("abc");  // IFNDR: used before <cstring> is included
#include <cstring>
int main() {}
```

With libc++ in our tests, `<string>` indirectly brings in the declaration of `strlen`, and this code compiles. With another standard library, or a newer version of the same library with fewer indirect inclusions, it may fail to compile.

## Standard library modules [std.modules]

¶1–¶2 The standard library provides two named modules. The module **`std`** exports the declarations in namespace `std` provided by the importable C++ library headers (Table 24) and the C facility headers (Table 25), and also exports the global `operator new` and `operator delete` provided by `<new>`.

¶3 The module **`std.compat`** exports everything in `std`, plus the global namespace declarations corresponding to the declarations in `std` from the headers of Table 25 (except those explicitly excluded by [support.c.headers.other]), and the declarations provided by `<stdbit.h>` and `<stdckdint.h>`.

¶6 *Recommended practice*: implementations should not export other declarations from these two modules. Note 2 reminds us that, like all named modules, they don't export macros ([[module.import]]), such as `assert`, `errno`, `offsetof` and `va_arg`.

```cpp
import std;
int main() {
  std::vector<int> v{1, 2, 3};
  std::println("{}", v);                 // OK
  ::operator delete(::operator new(1));  // OK: std also exports the global operator new/delete
  // ::printf("x");                      // error: global C names are exported only by std.compat
  // assert(v.size() == 3);              // error: modules don't export macros
}
```

Verified with Clang 23 after precompiling libc++'s bundled `std.cppm`: this code prints `[1, 2, 3]`. Uncommenting the `::printf` line, Clang reports "missing '#include <_printf.h>'; 'printf' must be declared before it is used"; uncommenting the `assert` line gives "use of undeclared identifier 'assert'". When you need `assert`, just `#include <cassert>` after `import std;`.

This mixing is safe because ¶5 says that a declaration in the library denotes the same entity whether it was made reachable by including a header, importing a header unit, or importing a module. The `std::vector` from `#include <vector>` and from `import std;` is the same template, with no ODR violation. ¶4 says that it is unspecified to which module a declaration in the library is attached; Note 1 adds that conforming implementations ensure that mixing `#include` and `import` doesn't result in conflicting attachments ([[basic.link]]). For engineering practice see [[toolchain/modules-in-practice]].

!!! history
    When C++20 introduced modules, the standard library promised only importable headers (`import <vector>;`), with no named modules. C++23 added `std` and `std.compat` through [[P2465R3]].

## The freestanding library [compliance]

¶1 Implementations are either hosted or freestanding ([[intro.compliance]]), and which kind is implementation-defined. A freestanding implementation can run in an environment without an operating system, as is common in kernel and embedded development.

¶2 A freestanding implementation provides an implementation-defined set of headers, which includes at least the headers in Table 27. In the current draft Table 27 is already quite long: language-support headers such as `<cstddef>`, `<limits>`, `<new>`, `<exception>`, `<contracts>` and `<coroutine>`; utilities such as `<memory>`, `<utility>`, `<tuple>`, `<optional>`, `<variant>`, `<expected>` and `<functional>`; containers and views `<array>`, `<inplace_vector>`, `<span>` and `<mdspan>`; and `<iterator>`, `<ranges>`, `<algorithm>`, `<string_view>`, `<string>`, `<charconv>`, `<random>`, `<cmath>`, `<atomic>` and more.

¶3 For each header in Table 27, a freestanding implementation provides at least the freestanding items ([[freestanding.item]]) declared in it. A header being in the table doesn't mean everything in it must be provided: `<string>` is in the table, but `std::basic_string`, which needs dynamic memory allocation, isn't a freestanding item; what is freestanding is `char_traits` and a few other parts. Which items are freestanding has to be read off the synopsis annotations one by one.

¶4 The [[g:hosted-library-facilities|hosted library facilities]] are the part of the library a hosted implementation must provide and a freestanding implementation need not. A freestanding implementation may provide an implementation-defined subset of them (possibly empty), and whatever it provides has the same requirements as on a hosted implementation.

¶5 A freestanding implementation may also provide deleted definitions ([[dcl.fct.def.delete]]) for some namespace-scope functions of the hosted library facilities. Note 1 explains that this prevents overload resolution from silently changing its result when a program is moved from a freestanding implementation to a hosted one, on the same principle as *freestanding-deleted* in [[conventions]].

With Clang, `-ffreestanding` makes `__STDC_HOSTED__` 0, but this only changes the compiler's assumptions; libc++ isn't trimmed down to the Table 27 subset as a result.

## Linkage [using.linkage]

¶1 Entities in the C++ standard library have external linkage. Unless otherwise specified, objects and functions have the default `extern "C++"` language linkage ([[dcl.link]]).

¶2 Whether a name from the C standard library declared with external linkage has `extern "C"` or `extern "C++"` linkage is implementation-defined; the standard recommends `extern "C++"`. A footnote says that the only reliable way to declare an object or function from the C standard library is to include the header that declares it, even though section 7.1.4 of the C standard lets C programs declare library functions themselves.

```cpp
extern "C" int printf(const char*, ...);   // not portable: neither the language linkage nor the signature
int main() { printf("hi\n"); }             // is guaranteed to match the library's declaration
```

In C, declaring a standard library function yourself is valid as long as the signature is correct. In C++, the language linkage of `printf` is implementation-defined, so your own declaration may not match the real one, and these names and signatures are also reserved to the implementation ([[extern.names]]). In practice all three major implementations use `extern "C"`, but the standard doesn't guarantee it.

¶3 Objects and functions defined in the library and required by a program are included in the program prior to program startup.

## Questions

!!! question "Question 1"
    The following code compiles on both libc++ and libstdc++. Is it portable?

    ```cpp
    #include <iostream>
    int main() { std::string s = "hello"; std::cout << s.size(); }
    ```

<details markdown="1">
<summary>Answer</summary>

It isn't portable. `std::string` is declared in `<string>`, which the code doesn't include. [[res.on.headers#1]] allows C++ headers to include other C++ headers, and both implementations' `<iostream>` happen to provide `std::string` indirectly, but the standard only requires `<iostream>` to provide the contents of its synopsis and of `<ios>`, `<streambuf>`, `<istream>` and `<ostream>`, which it includes, and none of these has `std::string`. By [using.headers] ¶3, the program must include `<string>` before using `std::string`, otherwise it is IFNDR. An implementation may reduce its indirect inclusions at any time, and then this code will fail to compile.
</details>

!!! question "Question 2"
    After `import std;`, can you use `std::size_t`? What about `::size_t`? And `offsetof`?

<details markdown="1">
<summary>Answer</summary>

`std::size_t` can be used: it is a declaration provided in `std` by `<cstddef>` (Table 25), and ¶2 says the module `std` exports it.

`::size_t` isn't guaranteed: global C names are exported by `std.compat` (¶3.1), and `std` additionally exports only the global `operator new` and `operator delete`.

`offsetof` can't be used: it is a macro ([headers] ¶6), and modules don't export macros (¶6 Note 2). When you need it, `#include <cstddef>`.
</details>

<details class="fine" markdown="1"><summary>Remaining wording</summary>

[requirements.general] ¶1: [requirements] specifies requirements that apply to the entire standard library, and Clauses 17–33 and Annex D specify the requirements of individual entities. ¶2: requirements specified in terms of interactions between threads don't apply to programs having only a single thread of execution. ¶3: the five parts of [requirements] are [organization] (the contents and organization of the library), [using] (how programs use the library), [[utility.requirements]] (requirements on types and functions), [[constraints]] (constraints on programs) and [[conforming]] (constraints on implementations).

[organization.general] ¶1: [contents] describes the entities and macros the library provides, [headers] lists the headers, and [compliance] specifies the requirements on freestanding implementations.

[contents] ¶1: unless otherwise specified, the library provides definitions for the entities and macros described in the header synopses. A footnote to ¶2 also explains that the C standard library headers ([support.c.headers]) define names in the global namespace too, and the C++ headers for C facilities may also do so.

The full list of Table 24 in [headers] ¶2: `<algorithm>` `<any>` `<array>` `<atomic>` `<barrier>` `<bit>` `<bitset>` `<charconv>` `<chrono>` `<compare>` `<complex>` `<concepts>` `<condition_variable>` `<contracts>` `<coroutine>` `<debugging>` `<deque>` `<exception>` `<execution>` `<expected>` `<filesystem>` `<flat_map>` `<flat_set>` `<format>` `<forward_list>` `<fstream>` `<functional>` `<future>` `<generator>` `<hazard_pointer>` `<hive>` `<initializer_list>` `<inplace_vector>` `<iomanip>` `<ios>` `<iosfwd>` `<iostream>` `<istream>` `<iterator>` `<latch>` `<limits>` `<linalg>` `<list>` `<locale>` `<map>` `<mdspan>` `<memory>` `<memory_resource>` `<meta>` `<mutex>` `<new>` `<numbers>` `<numeric>` `<optional>` `<ostream>` `<print>` `<queue>` `<random>` `<ranges>` `<ratio>` `<rcu>` `<regex>` `<scoped_allocator>` `<semaphore>` `<set>` `<shared_mutex>` `<simd>` `<source_location>` `<span>` `<spanstream>` `<sstream>` `<stack>` `<stacktrace>` `<stdexcept>` `<stdfloat>` `<stop_token>` `<streambuf>` `<string>` `<string_view>` `<syncstream>` `<system_error>` `<text_encoding>` `<thread>` `<tuple>` `<type_traits>` `<typeindex>` `<typeinfo>` `<unordered_map>` `<unordered_set>` `<utility>` `<valarray>` `<variant>` `<vector>` `<version>`

[std.modules] ¶4 *Recommended practice*: implementations should ensure that the module attachment of declarations doesn't hinder future evolution or splitting of the standard library modules.

[using.overview] ¶1: [using.headers] describes effects during translation phase 4 (preprocessing), and [using.linkage] effects during phase 8 (linking); see [[lex.phases]].

[using.linkage] ¶4: see also replacement functions ([[replacement.functions]]) and run-time changes to handler functions ([[handler.functions]]).

</details>
