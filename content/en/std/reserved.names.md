---
title: Reserved names
summary: "Names the standard library reserves for itself: after including a standard header you can't define library names as macros; the function signatures, object names and type names of the C library are reserved both globally and in std; literal suffixes not starting with an underscore are reserved for the standard; zombie names left by removed facilities remain reserved. Declaring these names in a reserved context is undefined behavior."
updated: 2026-10-19
---

!!! tldr
    - Once a translation unit includes any standard library header, it can't `#define` or `#undef` any name declared in any standard library header, such as `min`, `max`, `move` or `size`.
    - The function signatures, object names and type names of the C standard library are reserved both in the global namespace and in `std`, even if the corresponding header isn't included. Don't define your own global `abs(int)` or `size_t`.
    - User-defined literal suffixes must start with an underscore; those that don't are reserved for the standard, and those containing `__` are reserved for the implementation.
    - Names left behind by facilities removed from the standard (`auto_ptr`, `bind1st`, `<strstream>`…) are still reserved; they are called zombie names.
    - Declaring these names in a reserved context is undefined behavior, and compilers usually don't report it.

In [[lex.name]], the core language already reserves a set of [[g:reserved-identifier|identifiers]]: those containing a double underscore, those beginning with an underscore followed by an uppercase letter, and those beginning with an underscore in the global namespace. This subclause is the library-level supplement: ordinary names without underscores can also be reserved if they clash with the standard library.

## Three kinds of reserved names [reserved.names.general]

¶1 The standard library reserves three kinds of names: macros (¶1.1), global names (¶1.2), and names with external linkage (¶1.3).

¶2 If a program declares or defines a name in a context where it is reserved, other than as explicitly allowed by Clause 16, its behavior is undefined.

The following sections describe which names are reserved in which contexts.

## Library names can't be defined as macros [macro.names]

```cpp ub
#include <cstdio>
#define move(x) static_cast<decltype(x)&&>(x)   // UB: move is declared in <utility>
#define size 100                                 // UB: std::size is declared in <iterator> and others
#define min(a, b) ((a) < (b) ? (a) : (b))        // UB: min is declared in <algorithm>
#undef assert                                    // UB: assert is declared in <cassert>
int main() {}
```

!!! std
    A translation unit that includes a standard library header shall not `#define` or `#undef` names declared in any standard library header.

¶1 A translation unit that includes a standard library header shall not `#define` or `#undef` names declared in any standard library header.

There are two "any"s here. As soon as you include any standard header, even just `<cstdio>`, you can't define any name from any standard header as a macro, not just from the header you included. The example above includes only `<cstdio>`, and all four lines violate the rule.

Why such a blanket rule? Because the standard allows a C++ standard header to include other standard headers ([[res.on.headers#1]]). In some implementation `<cstdio>` might indirectly include `<algorithm>`, and the standard doesn't want the validity of a program to depend on such implementation details.

### min and max from `<windows.h>`

The most common violation comes from Windows' `<windows.h>`, which defines `min` and `max` as function-like macros. A function-like macro is expanded only when its name is immediately followed by a left parenthesis, so wrapping the function name in parentheses avoids it:

<div class="compare" markdown="1">

```cpp error
#define min(a, b) ((a) < (b) ? (a) : (b))
#include <algorithm>
int main() {
  return std::min(1, 2);
  // expands to std::((1) < (2) ...)
  // error: expected unqualified-id
}
```

```cpp run ok
#define min(a, b) ((a) < (b) ? (a) : (b))
#include <algorithm>
int main() {
  int x = (std::min)(1, 2);
  // min isn't followed by (, so the macro isn't expanded
  return x == 1 ? 0 : 1;
}
```

</div>

Defining the `min` macro already violates [macro.names] on both sides; the right-hand form only makes the code compile in such an environment. A better fix is to define `NOMINMAX` before including `<windows.h>`, so that it doesn't define these two macros.

!!! impl "libc++'s self-protection"
    In its internal headers, libc++ saves the most common macros `min`, `max`, `refresh`, `move` and `erase` (the last three come from the curses library) with `#pragma push_macro`, `#undef`s them, and restores them at the end of the header (`<__undef_macros>`). This ensures that `#include <algorithm>` itself isn't broken, but `std::min(...)` in user code will still be macro-expanded.

!!! note "Defining keywords as macros"
    `#define private public` violates a different rule. [[cpp.replace.general#9]] is a core language rule: no translation unit may define a keyword, an identifier with special meaning such as `final` / `override`, or an attribute token as a macro, regardless of whether a standard header is included. This rule requires a diagnostic, and Clang 23 gives the warning `-Wkeyword-macro`. Conversely, standard library headers themselves must not define keywords as macros ([[headers#8]]).

## Names and signatures from the C library [extern.names]

```cpp ub
// no headers included
int abs(int x) { return x < 0 ? -x : x; }   // UB: the C library function signature abs(int) is reserved
double atof(const char*) { return 0; }      // UB: likewise
int main() { return abs(-1); }
```

Clang 23 compiles this code without any warnings, and it runs fine. But at link time it may collide with the C library's `abs` as a duplicate definition, or the linker may select it and replace calls to `abs` inside the library; the compiler may also treat `abs` as a built-in and never call your definition at all. All these consequences depend on the toolchain, so the standard makes it UB.

¶1 Each name declared as an object with external linkage in a header is reserved to the implementation to designate that library object, both in `std` and in the global namespace. Footnote 141 gives `errno` from `<cerrno>` as an example.

¶2 Each global function signature declared with external linkage in a header is reserved to the implementation to designate that function. Footnote 142 gives `setjmp(jmp_buf)` from `<csetjmp>` and `va_end(va_list)` from `<cstdarg>` as examples.

¶3 Each name from the C standard library declared with external linkage is reserved to the implementation for use as a name with `extern "C"` linkage, both in `std` and in the global namespace.

¶4 Each function signature from the C standard library declared with external linkage is reserved to the implementation for use as a function signature with both `extern "C"` and `extern "C++"` linkage, or as a name of namespace scope in the global namespace. Footnote 143 explains that the signatures in `<cuchar>`, `<cwchar>` and `<cwctype>` are always reserved.

Whether something is reserved depends on the name (or signature) together with the namespace it is in:

| Declaration | Violation? |
|---|---|
| A global `int abs(int)`, `int errno;` | Violation |
| A global `static int abs(int)` | Violation: ¶4 reserves names in the global namespace, regardless of linkage |
| `namespace app { int abs(int); }`, a class member `abs`, a local variable `abs` | No violation |
| A global `int abs(MyType)` | No violation: different signature |
| A global `ssize_t read(int, void*, size_t)` | Not protected by the C++ standard, but clashes with the system function on POSIX systems |

## Types from the C library [extern.types]

```cpp run ok
#include <cstddef>
#include <stddef.h>
#include <type_traits>
static_assert(std::is_same_v<::size_t, std::size_t>);
static_assert(std::is_same_v<::ptrdiff_t, std::ptrdiff_t>);
int main() {}
```

¶1 For each type `T` from the C standard library, `::T` and `std::T` are reserved to the implementation, and when both are declared they shall be the same type.

This guarantees that code mixing `<stddef.h>` and `<cstddef>` never ends up with two different `size_t`s. For programs, it means you can't declare your own global `size_t`, `FILE`, `tm`, `div_t` and so on. The `typedef unsigned int size_t;` common in old code is UB.

## Literal suffixes [usrlit.suffix]

```cpp run ok
unsigned long long operator""_km(unsigned long long v) { return v * 1000; }
int main() { return 3_km == 3000 ? 0 : 1; }
```

¶1 Literal suffix identifiers ([[over.literal]]) that don't start with an underscore are reserved for future standardization; those containing a double underscore `__` are reserved for use by C++ implementations.

The standard library's own suffixes all lack underscores: `s`, `sv`, `h`, `min`, `ms`, `us`, `ns`, `y`, `d`, `i`, `il`, `if` and so on. User suffixes must start with an underscore. Clang 23 warns about `operator"" km` (no underscore): such a suffix is reserved, and no literal will ever invoke this operator. Without the space, `operator""km` is an outright error.

There is one more detail. When written `operator"" _Km`, with a space between the quotes and the suffix, `_Km` is a separate identifier beginning with an underscore followed by an uppercase letter, which is a reserved identifier under [[lex.name]]; this form with a space is also deprecated in C++23. When written `operator""_Km`, `_Km` is part of the ud-suffix and isn't subject to that restriction. The simplest course is to always use the form without a space and with an underscore followed by a lowercase letter.

## Zombie names [zombie.names]

When a standard library facility is removed, its name isn't immediately returned to users. Implementations may still provide it as an extension or in older standard modes for compatibility with old code, and users defining their own things with these names would clash with it. These names are called **zombie names** ([[g:zombie-name]]).

¶1 The names in Table 38 are reserved in namespace `std` for previous standardization:

| Category | Names (selection) | Origin |
|---|---|---|
| Smart pointers | `auto_ptr`, `auto_ptr_ref` | Deprecated in C++11, removed in C++17 |
| Function adaptors | `unary_function`, `binary_function`, `bind1st`, `bind2nd`, `ptr_fun`, `mem_fun`, `not1`, `not2`… | The C++98 adaptors |
| Algorithms | `random_shuffle` | Deprecated in C++14, removed in C++17 |
| Exceptions | `unexpected_handler`, `set_unexpected`, `get_unexpected`, `uncaught_exception` | Dynamic exception specifications and their supporting facilities |
| Garbage collection support | `declare_reachable`, `undeclare_reachable`, `get_pointer_safety`, `pointer_safety` and others | Introduced in C++11, removed in C++23 |
| Temporary buffers | `get_temporary_buffer`, `return_temporary_buffer`, `raw_storage_iterator` | |
| Type traits | `is_literal_type`, `is_literal_type_v`, `result_of`, `result_of_t` | |
| Encoding conversion | `wstring_convert`, `wbuffer_convert`, `codecvt_utf8`, `codecvt_utf16`, `codecvt_utf8_utf16`, `codecvt_mode` and others | `<codecvt>` |
| Character array streams | `strstream`, `istrstream`, `ostrstream`, `strstreambuf` | `<strstream>` |
| C functions | `gets` | Removed in C11 |

¶2 The names in Table 39 are reserved as members, and portable code may not use them as names of object-like macros: `argument_type`, `first_argument_type`, `second_argument_type`, `io_state`, `open_mode`, `seek_dir`, `op`, `preferred`, `strict`.

¶3 The names in Table 40 are reserved as member functions, and portable code may not use them as names of function-like macros: `converted`, `freeze`, `from_bytes`, `pcount`, `stossc`, `to_bytes`.

¶4 The header names in Table 41 are reserved for previous standardization: `<ccomplex>`, `<ciso646>`, `<codecvt>`, `<cstdalign>`, `<cstdbool>`, `<ctgmath>`, `<strstream>`.

Even member names are reserved because implementations may still provide these old members. libc++'s `<ios>` still has `typedef iostate io_state;` in C++14 and earlier modes. If a user writes `#define io_state 1` and then includes `<ios>` in C++14 mode, that line is rewritten by the macro into invalid code. The `op` in Table 39 comes from a member of `binder1st`, and `preferred` and `strict` come from the removed `pointer_safety` enumeration.

libc++ still ships all the headers in Table 41, and including them under `-std=c++2c` produces no diagnostic, but the removed contents are no longer provided: `std::codecvt_utf8` gives "no member named 'codecvt_utf8' in namespace 'std'". Nor can users write their own header named `codecvt` and put it on the standard include path; that is the UB of [[alt.headers]].

## Questions

!!! question "Question 1"
    The following program includes only `<cstdio>`. Does it violate [macro.names]?
    ```cpp
    #include <cstdio>
    #define emplace_back push_back
    int main() {}
    ```

<details markdown="1">
<summary>Answer</summary>

Yes. `emplace_back` is declared in headers such as `<vector>`, `<deque>` and `<list>`; although this translation unit doesn't include them, [macro.names] speaks of names declared in any standard library header. The behavior is undefined ([reserved.names.general] ¶2).
</details>

!!! question "Question 2"
    Is it valid to define `int app::printf(const char*, ...)` in your own namespace? What about a global `static int printf(const char*, ...)`?

<details markdown="1">
<summary>Answer</summary>

`app::printf` is valid: [extern.names] only reserves names and signatures in `std` and the global namespace.

A global `static int printf(const char*, ...)` isn't valid: ¶4 reserves the function signatures of the C library as names in the global namespace, regardless of linkage. If `<stdio.h>` is also included, it additionally conflicts with the existing declaration (same signature, different linkage), and compilation fails outright.
</details>
