---
title: Compatibility features (Annex D)
summary: "What deprecated means precisely in the standard, and a complete table of every deprecated feature in Annex D of the current draft: when it was deprecated, the warnings from Clang 23 / libc++, and what to write instead."
updated: 2026-10-19
---

!!! tldr
    - A deprecated feature is still valid C++ that implementations must support; it only means the committee has listed it as a candidate for future removal.
    - Annex D is a normative annex. The rules for facilities like `std::rel_ops`, `std::iterator` and `is_pod` are written only here; the main text no longer has them.
    - The standard allows implementations to add `[[deprecated]]` to deprecated library names, which is where `-Wdeprecated-declarations` warnings come from; warnings for the core language part are added by compilers on their own.
    - When a feature is removed from Annex D, it is recorded as an incompatibility in Annex C; removed library names become zombie names, which programs must not use.
    - The table below lists every deprecated feature. For several of them Clang issues no warning at all, and the only way to find them is to search the code.

## What deprecated means [depr.general]

Under `-std=c++20`, if you write `[=]` and use a member in the lambda, Clang warns that implicit capture of `this` is deprecated, but the program still compiles and runs. Deprecation is a formal status in the standard, and its meaning is defined at the start of Annex D.

¶1 Annex D describes features that are specified for compatibility with existing implementations.

¶2 These features are all deprecated ([[g:deprecated]]), which the standard defines as follows:

!!! std
    Normative for the current revision of C++, but having been identified as a candidate for removal from future revisions.

The first half says deprecated features have normative force like any other. A conforming implementation must accept programs that use them and execute them with the specified semantics. The second half says they are only candidates for removal: the committee may remove one (`auto_ptr`, `register` and `throw()` were all removed this way), may keep it for a long time (`std::iterator` has been deprecated since C++17 and is still there), or may even undo part of a deprecation (compound assignment to `volatile`, see [[depr.volatile.type]]).

Unlike Annex C [[diff]], Annex D is normative; it is part of the standard proper. The rules for many deprecated features are written only here, for example the four operator templates of `std::rel_ops`, the `std::iterator` class template, and the definition of `is_pod`.

The last sentence of ¶2 allows implementations to add the `[[deprecated]]` attribute ([[dcl.attr]]) to the library names and entities described in Annex D. libc++ and libstdc++ do exactly that, so using deprecated library facilities gets you a `-Wdeprecated-declarations` warning. Deprecated core language features have no corresponding permission, but the standard only specifies when a diagnostic is required and never forbids implementations from issuing extra diagnostics for well-formed programs ([[intro.compliance]]), so compilers add warnings for them too.

!!! note "Deprecation doesn't change a program's validity"
    A program that uses deprecated features is still well-formed; if it fails to compile because of `-Werror`, that's the user's own choice. Only when a feature is removed from Annex D does a program using it become ill-formed, and that change is recorded as an incompatibility in Annex C, for example in the last section of [[diff.cpp23]].

## After removal: zombie names

When a library facility is removed from Annex D, its name doesn't thereby become free to use. [[zombie.names]] lists names that once appeared in the standard library and were later removed, such as `auto_ptr`, `bind1st`, `random_shuffle`, `strstream` and `codecvt_utf8`; these are called zombie names ([[g:zombie-name]]). They are reserved for previous standardization: a program can't declare its own `auto_ptr` in `std`, while an implementation may keep providing these facilities. So some standard libraries still provide removed facilities in newer language modes, and that doesn't violate the standard.

## The complete table

The table below lists every entry of Annex D in the current draft. The "Deprecated since" column gives a version only where it is certain, and "—" otherwise. The warning column is what Clang 23.1.3 + libc++ give under `-std=c++2c` in our tests; "None" means no diagnostic even with `-Wall -Wextra -Wdeprecated`. For some library features libc++ adds `[[deprecated]]` only in newer language modes; see the individual subpages for details.

### Core language ([[depr.local]] page)

| Subclause | Feature | Deprecated since | Clang 23 warning | Instead |
|---|---|---|---|---|
| D.2 [depr.local] | A declaration of a non-TU-local entity that is an exposure, e.g. a function with external linkage returning a type from an unnamed namespace | C++20 | None | Move the exposed entity out of the unnamed namespace, or give the declaration internal linkage |
| D.3 [depr.capture.this] | `[=]` implicitly capturing `*this` by reference | C++20 | `-Wdeprecated-this-capture` (on by default) | `[=, this]` or `[=, *this]` |
| D.4 [depr.volatile.type] | `++`/`--` on `volatile` objects, using the result of an assignment to `volatile`, `volatile` parameters and return types, `volatile` structured bindings | C++20 | `-Wdeprecated-volatile` (on by default) | Explicit read, modify, write; remove `volatile` from parameter and return types |
| D.5 [depr.ellipsis.comma] | An ellipsis without a preceding comma: `void f(int...)` | C++26 | `-Wdeprecated-missing-comma-variadic-parameter` (on by default in C++26 mode) | `void f(int, ...)` |
| D.6 [depr.impldec] | Implicit definition of the copy constructor or copy assignment operator when there is a user-declared destructor or copy operation | C++11 | `-Wdeprecated-copy` (`-Wextra`); the destructor case needs `-Wdeprecated` | Explicit `= default`, or follow the rule of three/five/zero |
| D.7 [depr.static.constexpr] | Redundantly redeclaring a `static constexpr` data member outside the class | C++17 | `-Wdeprecated-redundant-constexpr-static-def` (`-Wdeprecated`) | Delete the out-of-class declaration |
| D.8 [depr.lit] | `operator "" _x`: whitespace between the quotes and the suffix | C++23 | `-Wdeprecated-literal-operator` (on by default) | `operator""_x` |
| D.9 [depr.template.template] | Writing `template` before a qualified name of a class template or alias template that isn't followed by a template argument list | — | None | Drop `template` for non-dependent names; for dependent names there's currently no alternative on Clang |

### Library: numerics, C compatibility, type traits and utilities ([[depr.numeric.limits.has.denorm]] page)

| Subclause | Feature | Deprecated since | Clang 23 / libc++ warning | Instead |
|---|---|---|---|---|
| D.10 [depr.numeric.limits.has.denorm] | `numeric_limits::has_denorm`, `has_denorm_loss`, `float_denorm_style` | C++23 | `-Wdeprecated-declarations` (since C++23) | `numeric_limits<T>::denorm_min()`, or `*_TRUE_MIN` in `<cfloat>` |
| D.11 [depr.c.macros] | `FLT_HAS_SUBNORM` etc., `DECIMAL_DIG`, `INFINITY`/`NAN` obtained via `<cmath>`, `__bool_true_false_are_defined` | — | None | `*_DECIMAL_DIG`; get `INFINITY`/`NAN` from `<cfloat>` |
| D.12 [depr.cerrno] | `ENODATA`, `ENOSR`, `ENOSTR`, `ETIME` and the corresponding `errc` enumerators | — | None for the macros; `-Wdeprecated-declarations` for the `errc` enumerators | These are STREAMS error codes that POSIX has removed |
| D.13 [depr.meta.types] | `is_trivial`, `is_pod`, `aligned_storage`, `aligned_union` | `is_pod` C++20; `aligned_*` C++23; `is_trivial` C++26 | `-Wdeprecated-declarations` (each from the corresponding mode) | `is_trivially_copyable` plus `is_trivially_default_constructible`; `is_standard_layout`; `alignas(A) std::byte buf[N]` |
| D.14 [depr.relops] | `std::rel_ops` | C++20 | `-Wdeprecated-declarations` (since C++20) | `operator<=>` and `operator==` |
| D.15 [depr.tuple] | `tuple_size<volatile T>`, `tuple_element<I, volatile T>` etc. | C++20 | None | Apply `remove_volatile_t` first |
| D.16 [depr.variant] | `variant_size<volatile T>`, `variant_alternative<I, volatile T>` etc. | C++20 | None | Same as above |
| D.17 [depr.vector.bool.swap] | The static member `vector<bool>::swap(reference, reference)` | — | None | `swap(v[i], v[j])` |
| D.18 [depr.iterator] | The `std::iterator` base class template | C++17 | `-Wdeprecated-declarations` (since C++17) | Write out the five member type aliases directly |
| D.19 [depr.move.iter.elem] | `move_iterator::operator->` | C++20 | `-Wdeprecated-declarations` (since C++20) | `(*it).member` or `it.base()->member` |

### Library: localization, formatting, time, filesystem, iostreams ([[depr.locale.category]] page)

| Subclause | Feature | Deprecated since | Clang 23 / libc++ warning | Instead |
|---|---|---|---|---|
| D.20 [depr.locale.category] | `codecvt<char16_t, char>`, `codecvt<char32_t, char>` and their `char8_t` versions, and likewise for `codecvt_byname` | The `char` versions C++20 | `-Wdeprecated-declarations` (since C++20) | A third-party Unicode library |
| D.21 [depr.format] | `visit_format_arg` | C++26 | `-Wdeprecated-declarations` (C++26 mode) | The member function `basic_format_arg::visit` |
| D.22 [depr.ctime] | `asctime`, `ctime` | — | None | `std::format("{:%c}", tp)`, `strftime` |
| D.23.1 [depr.fs.path.factory] | `filesystem::u8path` | C++20 | `-Wdeprecated-declarations` (since C++20) | `path(std::u8string_view)` or `path(u8"…")` |
| D.23.2 [depr.fs.path.obs] | `path::string()` and `generic_string()` returning `std::string` | — | None | `native_encoded_string()`, `display_string()` and their `generic_` versions ([[fs.class.path]]) |
| D.25 [depr.istream.extractors] | Extraction into `signed char`, `unsigned char` and arrays of them | — | None | Read into `char`, then convert |
| D.26 [depr.ostream.inserters] | Insertion of `signed char`, `unsigned char` and pointers to them | — | None | `static_cast<char>(c)`; use `+c` to output it as a number |

### Library: atomic operations ([[depr.atomics]] page)

| Subclause | Feature | Deprecated since | Clang 23 / libc++ warning | Instead |
|---|---|---|---|---|
| D.24.2 [depr.atomics.volatile] | Member functions on a `volatile atomic<T>` that isn't lock-free | C++20 | None | Drop `volatile`, or check `is_always_lock_free` |
| D.24.3 [depr.atomics.nonmembers] | `atomic_init` | C++20 | `-Wdeprecated-declarations` (since C++20) | Initialize at construction, or `store(v, memory_order::relaxed)` |
| D.24.4 [depr.atomics.types.operations] | `ATOMIC_VAR_INIT` | C++20 | `-Wdeprecated-pragma` (since C++20) | `std::atomic<int> v{5};` |
| D.24.5 [depr.atomics.order] | `memory_order::consume`, `memory_order_consume`, `kill_dependency` | C++26 | None | `memory_order::acquire`; delete `kill_dependency` |

## Cleaning up deprecated usage

With Clang, `-Wdeprecated` turns on most of the checks for the core language part, and `-Wdeprecated-declarations` for the library part is on by default. The items marked "None" in the table can't be caught by the compiler; the only way is to search the code.

The earlier something was deprecated, the closer it usually is to removal. Only three items deprecated in C++17 or earlier have still not been removed: implicit copy operations (C++11), redeclaring `static constexpr` members outside the class (C++17), and `std::iterator` (C++17). The first two affect too much code to be likely to be removed soon.

The replacements were mostly already available in the same version that deprecated the feature, and code changed to use them stays compatible with older standards. The exception is `[=, this]`: it is ill-formed in C++17 (Clang accepts it as an extension with a warning). When you need to support both C++17 and C++20, write an explicit list without a capture default, such as `[this, &x]`.

## Deprecated features that have been removed

The following features were once in Annex D; their removal is recorded in the corresponding sections of Annex C:

| Removed in | Features | Recorded in |
|---|---|---|
| C++17 | `register`, `++` on `bool`, dynamic exception specifications, trigraphs, `auto_ptr`, `bind1st`/`bind2nd`, `ptr_fun`, `mem_fun`, `random_shuffle`, `unary_function`/`binary_function`, old iostreams members | [[diff.cpp14]] |
| C++20 | `throw()`, `uncaught_exception`, the adaptable function interfaces such as `not1`, the redundant members of `allocator`, `raw_storage_iterator`, temporary buffers, `shared_ptr::unique`, `is_literal_type`, `result_of`, empty C headers such as `<ccomplex>` | [[diff.cpp17]] |
| C++23 | Comma expressions in subscripts (repurposed for multidimensional subscripts) | [[diff.cpp20]] |
| C++26 | Mixed arithmetic between enumerations and floating-point types or other enumerations, array comparisons, `allocator::is_always_equal`, the atomic free functions for `shared_ptr`, `string::reserve()`, `<codecvt>`, `<strstream>`, `wstring_convert`/`wbuffer_convert` | [[diff.cpp23]] |
