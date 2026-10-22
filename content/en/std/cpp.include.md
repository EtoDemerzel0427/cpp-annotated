---
title: Source file inclusion
summary: "How the two forms of #include look for files, the rules for building a file name from macros, how simple the file names the standard guarantees to be portable are, and when #include may become import."
updated: 2026-10-19
---

!!! tldr
    - `#include` puts the entire contents of another file verbatim where the directive is; where and how to look is almost entirely up to the implementation.
    - `<...>` does a header search; `"..."` does a source file search first and falls back to a header search if that fails. That's the basis for the quoted form looking locally first.
    - `#include` can also be followed by macros, whose expansion must be a single string literal or `<...>`; adjacent string literals aren't concatenated.
    - The standard only guarantees that file names like `foo.h`, alphanumerics plus a single-letter extension, can be distinguished; directory separators and case aren't guaranteed.
    - For importable headers (such as the standard library's C++ headers), the implementation may replace `#include` with `import`.

`#include` is the oldest code-reuse mechanism in C and C++: replace this directive with the entire contents of another file. It is executed in translation phase 4 ([[lex.phases]]); the included file also goes through phases 1 to 4 and then forms a translation unit together with the file that includes it ([[lex.separate]]).

## Two forms, two searches (¶1–¶6)

Put a `myfile.h` in the current directory and test with Clang, without `-I.` on the command line:

```cpp
#if __has_include("myfile.h")    // 1: found in the includer's directory
#endif
#if __has_include(<myfile.h>)    // 0: the angle-bracket form looks only in -I, -isystem and system directories
#endif
```

The standard uses two terms to describe the lookup:

- ¶1 **[[g:header-search|Header search]]**: for a sequence of characters, search a sequence of places for a header uniquely identified by it. Which places and how headers are identified are implementation-defined.
- ¶2 **[[g:source-file-search|Source file search]]**: attempt to find a source file named by the sequence of characters, in an implementation-defined manner. If the implementation doesn't support such a search, or it fails, the result is that of a header search for the same sequence.

The difference in wording is deliberate: a header isn't necessarily a file. `<vector>` only needs to be identifiable, and an implementation could build it into the compiler; a source file is a real file.

¶3 `# include header-name` replaces the directive with the entire contents of the header or source file identified by the header name ([[lex.header]]). The two forms correspond to the two searches:

| Form | Search | Wording |
|---|---|---|
| `#include <h-char-sequence>` | header search | ¶4 |
| `#include "q-char-sequence"` | source file search, then header search if not found | ¶5, ¶2 |

¶6 If the header search fails, or the header or source file found can't be processed by the implementation (it's a directory, say), the program is ill-formed. Note 1 adds that even if it was only probed in `__has_include` ([[cpp.cond]]), finding it but being unable to process it is ill-formed.

```cpp run title="missing.cpp" error
#include <no/such/header.h>   // error: header search fails
int main() {}
```

Note 3 under ¶11 gives the portable usage: use `<>` for headers provided by the implementation and `""` for source files outside the implementation's control. "Implementation" here is meant broadly; POSIX's `<unistd.h>` counts too.

!!! impl "Search order in GCC, Clang and MSVC"
    These are the common conventions; consult each compiler's documentation for details:

    - `"..."`: first the includer's directory, then directories given by `-iquote`, then the same as `<...>`.
    - `<...>`: `-I` directories, `-isystem` directories, system directories, in that order.
    - For `"..."`, MSVC also walks up the include stack, searching the directory of each open includer.

    All of these are the implementation-defined behavior that ¶1 and ¶2 speak of; portable code shouldn't depend on the details.

## Building a file name from macros (¶7, ¶12)

The standard's Example 1 in ¶12 chooses a header by version number:

```cpp
#if VERSION == 1
    #define INCFILE  "vers1.h"
#elif VERSION == 2
    #define INCFILE  "vers2.h"  // and so on
#else
    #define INCFILE  "versN.h"
#endif
#include INCFILE
```

¶7 If `include` isn't followed by a header-name token, the tokens after it are macro-replaced just as in ordinary text. The result of replacement must have one of these two forms:

- a single string literal with no prefix;
- `<`, some tokens other than `>`, `>`.

The implementation then forms a header name from the spellings of these tokens and the whitespace between them, with whitespace handled in an implementation-defined way. If that succeeds, it's processed as in the direct form; if not, the program is ill-formed, no diagnostic required (IFNDR: the compiler may accept it, and the standard places no requirements on the whole program).

In practice, stringizing ([[cpp.stringize]]) is often used to build configuration-dependent paths:

```cpp
#define STR_(x) #x
#define STR(x) STR_(x)
#define PLATFORM posix
#include STR(platform/PLATFORM/config.h)   // i.e. #include "platform/posix/config.h"
```

The angle-bracket form can also come from macros. The tokens between `<` and `>` are expanded first, then concatenated by spelling:

```cpp
#define X myfile
#define Y h
#define HDR <X.Y>
#include HDR          // expands to the five tokens < myfile . h >, combined into <myfile.h>
```

!!! pitfall "Don't leave spaces inside the angle brackets"
    After `#define SP < myfile.h >`, writing `#include SP` makes Clang look for a file named ` myfile.h ` (with leading and trailing spaces), with a `-Wnonportable-include-path` warning. Whitespace handling is implementation-defined, so don't leave spaces after `<` or before `>`.

Note 2 under ¶7 reminds us that adjacent string literals are concatenated only in phase 6, not here. An `#include` that expands to two string literals isn't a valid directive:

```cpp
#define TWO "dir/" "file.h"
#include TWO      // ill-formed: not a single string literal
```

This result doesn't have either of the two forms ¶7 requires, which violates an ordinary "shall" rule and must be diagnosed. Clang gives an extra-tokens warning and then looks for a file named `dir/`. It's IFNDR only when the form is right but no valid header name can be formed, for example a string literal `"a\"b"` produced by macro expansion, whose spelling contains `"`, which can't appear in a quoted header name.

!!! lawyer "Clang and `#include EMPTY <X.Y>`"
    A header-name token is formed only immediately after `include` ([[lex.pptoken#5.4.2.1]]). So in `#include EMPTY <X.Y>` (where `EMPTY` is an empty macro), `<X.Y>` isn't a header name but the five tokens `<` `X` `.` `Y` `>`, and `X` and `Y` should be macro-expanded. Example 4 in [[cpp.embed.gen#14]] demonstrates the same rule for `#embed`. Tested, Clang 23 doesn't expand `X` and `Y` and looks for the literal `X.Y`, which disagrees with the draft. In practice almost nobody writes this.

## Portable file names (¶8)

¶8 An implementation must provide unique mappings for file names consisting of one or more letters, digits or underscores, followed by `.` and a single letter or underscore, with the first character not a digit. The implementation may ignore case distinctions.

In other words, the standard only guarantees that names like `foo.h` and `my_lib2.h` can be distinguished. None of the following are guaranteed, although all major implementations support them:

- directory separators, as in `#include "sys/types.h"`;
- multi-character extensions like `.hpp`, and file names without an extension (standard library headers like `<vector>` are guaranteed separately by [[headers]]);
- case: `"Foo.h"` and `"foo.h"` may be the same file.

!!! pitfall "Case"
    macOS's default file system and Windows are case-insensitive, so `#include "MyFile.h"` finds `myfile.h`; on Linux it doesn't. Clang gives a `-Wnonportable-include-path` warning in this situation, pointing out that the spelling doesn't match the file name on disk.

## Preventing multiple inclusion

The standard does nothing special when the same file is included twice; the second inclusion just pastes it again. If the file contains a class definition, there are two definitions in one translation unit, violating the ODR ([[basic.def.odr]]).

The in-standard solution is the include guard, implemented entirely with the mechanisms of [[cpp.cond]]:

```cpp title="widget.h"
#ifndef WIDGET_H
#define WIDGET_H
struct Widget { int x; };
#endif // WIDGET_H
```

Its drawbacks are that macro names may collide (two libraries both using `UTILS_H`) and that renaming is easy to forget after copying a file. Also, names beginning with a double underscore or an underscore plus an uppercase letter, such as `__WIDGET_H__` and `_WIDGET_H`, are reserved to the implementation ([[lex.name]]) and can't be used as guards.

`#pragma once` isn't in the standard. Per [[cpp.pragma]], it's an implementation-defined pragma, and an implementation that doesn't recognize it must ignore it, resulting in duplicate definitions; all major compilers do support it, though. The difficulty is deciding whether two inclusions are of the same file: the same file may be reached through symbolic links, hard links, different relative paths or different mount points of a network file system. The standard can't define what "the same file" is, which is the main reason it was never standardized.

!!! impl "The multiple-include optimization"
    GCC and Clang recognize the idiomatic form of include guards: the first non-comment content in the file is `#ifndef X`, the last is the matching `#endif`, and there's nothing else outside. The compiler remembers `X`, and on later `#include`s of the same file, it doesn't open it again as long as `X` is still defined. So on these two compilers, include guards perform as well as `#pragma once`. A single extra declaration outside the guard defeats the optimization.

## #include may become import (¶10)

¶10 If the header name identifies an **[[g:importable-header|importable header]]** ([[module.import]]), it is implementation-defined whether the `#include` is replaced by `import header-name;`. Importable headers include at least the standard library's C++ headers, but not C library headers such as `<cstdio>` and `<cassert>` ([[headers]]); the rest are implementation-defined.

After replacement, the header is compiled only once into a [[g:header-unit|header unit]], and each subsequent `#include` imports it. Macros defined in the header unit are still imported ([[cpp.import]]), so most code notices no difference. But there are two differences:

1. A header unit is translated independently and can't see macros the includer defined before the `#include`. Headers that depend on such configuration macros aren't suitable as importable headers; `<cassert>`, for example, depends on `NDEBUG`.
2. When processing a module unit (a file beginning with a `module` directive; see [[cpp.module]]), an import obtained by replacing an `#include` is ill-formed ([[cpp.import#2]]). This restriction applies to the body after the `module` directive, not to the global module fragment; to use such headers in the body, write `import` directly.

<details class="fine" markdown="1"><summary>Remaining wording</summary>

¶9 Included files can contain `#include`s of their own, with an implementation-defined limit on nesting depth. [[implimits]] recommends supporting at least 256 levels. A header that unconditionally includes itself quickly hits the limit; Clang reports `#include nested too deeply`.

</details>

## History

!!! history
    - The two forms and the macro form have existed since C++98. Portable file names originally guaranteed only letters; since C++11, in step with C99, digits are allowed (except as the first character).
    - C++17 added `__has_include` ([[P0061R1]]).
    - C++20 added importable headers with modules, and the permission to replace `#include` with `import` ([[P1103R3]]).
    - Wording after C++23 introduced the terms header search and source file search, rewriting ¶1–¶6; the case where the macro form can't form a header name changed from UB to IFNDR; and it was made explicit that finding a file but being unable to process it is ill-formed.

## Questions

!!! question "Question 1"
    Is the `#include` below portable?
    ```cpp
    #define LIB boost
    #define STR_(x) #x
    #define STR(x) STR_(x)
    #include STR(LIB/config.hpp)
    ```

<details markdown="1">
<summary>Answer</summary>

The result of preprocessing is well-defined. `include` isn't followed by a header name, so by ¶7 macro replacement happens: `STR`'s argument `LIB/config.hpp` is first fully expanded to `boost/config.hpp` ([[cpp.subst#1]]), substituted into `STR_`, and stringized by `#` into `"boost/config.hpp"` ([[cpp.stringize]]). That's a string literal forming a header name, and by ¶5 a source file search is done.

But the file name exceeds what ¶8 guarantees: it contains `/` and has a three-character extension. So whether the file can be found isn't portable, even though all major implementations handle it.

Another hazard is that words in the argument are macro-expanded. If somewhere there's a `#define config ...`, the path gets changed. `linux` is a macro predefined to 1 in GCC's GNU modes (such as `-std=gnu++20`), so `STR(linux/foo.h)` becomes `"1/foo.h"`.
</details>

!!! question "Question 2"
    If an implementation replaces `#include <vector>` with `import <vector>;`, does the behavior of the code below change?
    ```cpp
    #define _GLIBCXX_DEBUG 1
    #include <vector>
    ```

<details markdown="1">
<summary>Answer</summary>

It may. A header unit is translated independently, and when it's imported, macros the includer defined earlier don't affect its contents. So `_GLIBCXX_DEBUG` no longer switches `<vector>` to libstdc++'s debug implementation; what's imported is the version produced under the macro environment in effect when the header unit was compiled. This is one reason ¶10 makes the replacement implementation-defined; implementations usually require it to be enabled explicitly with a compiler option.
</details>

## Summary

!!! summary
    - `<...>` does a header search; `"..."` does a source file search, falling back to a header search. Places and methods are implementation-defined.
    - The expansion of the macro form must be a single string literal or `<...>`; failing to form a header name is IFNDR; whitespace inside angle brackets is handled in an implementation-defined way.
    - The standard only guarantees file names of the form `alphanumerics.single-letter`, possibly case-insensitive.
    - Include guards are the in-standard solution; `#pragma once` isn't standard, the difficulty being whether two paths refer to the same file.
    - For importable headers, the implementation may replace `#include` with `import`, in which case macros the includer defined earlier no longer affect the header's contents.
