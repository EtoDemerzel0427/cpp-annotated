---
title: C standard library
summary: "What C++ changed when it took in the C standard library: which headers are missing, which types and macros became keywords, and how NULL, strchr, longjmp, offsetof and malloc differ in C++."
updated: 2026-10-19
---

!!! tldr
    - C++ provides the C headers, but not `<stdnoreturn.h>` or `<threads.h>`; `<complex.h>` and `<tgmath.h>` merely include `<complex>` and `<cmath>`, without C's complex types or type-generic macros.
    - `wchar_t`, `char8_t`, `char16_t`, `char32_t` and alternative tokens such as `and` and `or` are keywords in C++, not typedefs or macros.
    - `NULL` is an implementation-defined null pointer constant and cannot be `((void*)0)`; functions such as `strchr` have a pair of `const` overloads and do not silently drop `const`.
    - A `longjmp` that skips non-trivial destructors is UB; `offsetof` is only guaranteed to support standard-layout classes; `malloc` and related functions implicitly create objects in the storage they return.

Most of the C standard library entered the C++ standard library unchanged, specified as "the same as the C standard library". This subclause collects the explicit modifications. It pairs with [[diff.iso]]: that one is about the language, this one about the library. Almost every modification has the same reason: some C library practices conflict with C++'s stricter type system and object model, such as returning pointers with `const` removed, defining character types as typedefs, or skipping all cleanup with `longjmp`.

## Headers {#diff.mods.to.headers}

¶1 For compatibility with the C standard library, the C++ standard library provides the C headers listed in [[support.c.headers]], such as `<stdio.h>`. They differ from versions such as `<cstdio>` in which namespace the names are declared in: `<cxxx>` guarantees declarations in `std`, `<xxx.h>` guarantees declarations in the global namespace, and either may also provide them in the other ([[library.c]]).

¶2 C's `<stdnoreturn.h>` and `<threads.h>` have no corresponding C++ headers, and they are not part of C++ themselves. The `noreturn` macro defined by `<stdnoreturn.h>` would break C++'s `[[noreturn]]` attribute; the functionality of `<threads.h>` is provided by `<thread>`, `<mutex>` and `<condition_variable>`.

¶3 The C headers `<complex.h>` and `<tgmath.h>` contain nothing from the C standard library; they only include other C++ headers: the former is equivalent to including `<complex>`, the latter to including `<cmath>` and `<complex>` ([[support.c.headers]]). C's `double _Complex`, the macro `I` and the type-generic macros do not exist in C++; C++ uses `std::complex<double>` and function overloading instead.

## Types and macros {#diff.mods.to.definitions}

### Character types are keywords {#diff.char16}

¶1 `char8_t`, `char16_t` and `char32_t` are distinct types in C++, not typedefs of existing integer types; they are keywords ([[lex.key]]), and `<cuchar>` does not define them as macros or type names. In C's `<uchar.h>`, `char16_t` is a typedef of `uint_least16_t` and the two cannot be told apart; C++ can overload functions and specialize templates on these types.

### `wchar_t` {#diff.wchar.t}

¶1 `wchar_t` is likewise a distinct type and a keyword, and none of `<cstddef>`, `<cstdlib>` and `<cwchar>` defines it as a macro or type name.

### `<iso646.h>` {#diff.header.iso646.h}

¶1 `and`, `and_eq`, `bitand`, `bitor`, `compl`, `not`, `not_eq`, `or`, `or_eq`, `xor` and `xor_eq` are keywords in C++, namely alternative tokens ([[lex.digraph]]), and `<iso646.h>` does not define them as macros. They are not identifiers, so they cannot be defined as macros: for `#define and &&` and even `#ifdef and`, Clang reports `C++ operator 'and' (aka '&&') used as a macro name`.

### The macro `NULL` {#diff.null}

```cpp impl
#include <cstddef>
void f(int);
void f(char*);
void g() { f(NULL); }   // Clang 23: the call is ambiguous
```

¶1 The macro `NULL` in `<clocale>`, `<cstddef>`, `<cstdio>`, `<cstdlib>`, `<cstring>`, `<ctime>` and `<cwchar>` is an implementation-defined null pointer constant in C++ ([[support.types]]). The definition common in C, `((void*)0)`, does not work in C++, because `void*` does not convert implicitly to other pointer types (see [[diff.iso]]).

So in C++ `NULL` may be `0`, `0L` or something built into the compiler, and which overload `f(NULL)` selects varies between implementations. Clang 23's `NULL` expands to `__null`, of type `long`, and the call above is ambiguous. This is exactly why C++11 introduced `nullptr`.

## Function declarations {#diff.mods.to.declarations}

```cpp error
#include <cstring>
const char* cs = "hello";
char* p = std::strchr(cs, 'l');        // error
const char* q = std::strchr(cs, 'l');  // OK
char buf[] = "abc";
char* r = std::strchr(buf, 'b');       // OK: the non-const version
```

¶1 C's `strchr` takes a `const char*` and returns a `char*`, silently dropping `const`. C++'s `<cstring>` provides a pair of overloads each for `strchr`, `strpbrk`, `strrchr`, `strstr` and `memchr`: a `const` pointer in gives a `const` pointer out, a non-`const` pointer in gives a non-`const` pointer out ([[cstring.syn]]). Line 3 of the example is valid in C and an error in C++.

¶2 The same applies to `wcschr`, `wcspbrk`, `wcsrchr`, `wcsstr` and `wmemchr` in `<cwchar>` ([[cwchar.syn]]).

¶3 Besides the names in C's `<stddef.h>`, `<cstddef>` also declares `nullptr_t`, `byte`, `to_integer`, and the operators for `std::byte` in [[support.types.byteops]].

## Function behavior {#diff.mods.to.behavior}

### Program termination and `longjmp` {#diff.mods.to.behavior.general}

¶1 The behavior of `atexit`, `exit` and `abort` in `<cstdlib>` differs from C; see [[support.start.term]] for details. C knows nothing of destructors, and C++ has to specify how these functions relate to object destruction:

- `exit` first destroys the current thread's objects with thread storage duration, then destroys objects with static storage duration in reverse order of construction, interleaved with calls to functions registered with `atexit`. Objects with automatic storage duration are not destroyed; `exit` does not unwind the stack.
- `abort` runs no destructors and calls no functions registered with `atexit`.
- `atexit` introduces no data races; whether an `atexit` call that does not happen before the call to `exit` succeeds is unspecified.

```cpp run ub
#include <csetjmp>
#include <string>
std::jmp_buf env;
void g() { std::longjmp(env, 1); }
void f() {
  std::string s = "a long string that forces heap allocation";
  g();   // UB: longjmp skips the destructor of s
}
int main() { if (setjmp(env) == 0) f(); }
```

¶2 The behavior of `longjmp` is more restricted ([[csetjmp.syn]]). If replacing a `setjmp`/`longjmp` pair with `catch`/`throw` would invoke a non-trivial destructor of some object with automatic storage duration, the behavior of that pair is undefined. Calling `setjmp` or `longjmp` in a coroutine's suspension context is also UB. Running the example above with `-fsanitize=address` in our tests, LeakSanitizer reports a heap leak from `s`: its destructor never ran.

### `offsetof` {#diff.offsetof}

¶1 `offsetof` in `<cstddef>` is guaranteed to accept only some type arguments in C++: use with types other than standard-layout classes ([[g:standard-layout-class]]) is conditionally-supported ([[support.types.layout]]). Use with a static data member or a member function is undefined behavior. Clang supports `offsetof` on classes with virtual functions but warns `'offsetof' on non-standard-layout type`.

### Memory allocation functions {#diff.malloc}

```cpp run ok
#include <cstdlib>
int main() {
  int* p = static_cast<int*>(std::malloc(sizeof(int)));
  if (!p) return 1;
  *p = 1;         // OK: malloc implicitly created an int object
  int r = *p;
  std::free(p);
  return r - 1;
}
```

¶1 `aligned_alloc`, `calloc`, `malloc` and `realloc` have several additional rules in C++ ([[c.malloc]]):

- They do not allocate storage through `::operator new`, and `free` does not deallocate through `::operator delete`, so replacing the global allocation functions does not affect them.
- They implicitly create objects in the storage they return ([[g:implicitly-create-objects]], see [[intro.object]]) and return a pointer to a suitable created object. For `calloc` the objects are created before the storage is zeroed; for `realloc`, before the contents are copied.
- Calling `realloc` with a non-null pointer and size 0 is erroneous behavior, with implementation-defined effects (see [[diff.cpp23]]).

In C, memory returned by `malloc` acquires a type when it is written, so the program above is naturally valid. In C++ an object must be created before it can be accessed, and before C++20 no operation created an `int` in this storage, so strictly speaking `*p = 1` was UB. The implicit object creation introduced in C++20 ([[P0593R6]]) closed this hole.

## Summary

| Item | C | C++ |
|---|---|---|
| `<stdnoreturn.h>`, `<threads.h>` | present | absent |
| `<complex.h>`, `<tgmath.h>` | C complex numbers and type-generic macros | only include `<complex>` and `<cmath>` |
| `char16_t` and friends | typedefs | keywords, distinct types |
| `and` etc. from `<iso646.h>` | macros | keywords |
| `NULL` | often `((void*)0)` | implementation-defined null pointer constant |
| `strchr` etc. | `const char*` in, `char*` out | pairs of `const` overloads |
| `exit` | no destructors involved | destroys static and thread objects, does not unwind the stack |
| `longjmp` | can jump anywhere | UB if it skips non-trivial destructors |
| `offsetof` | any struct | conditionally-supported for non-standard-layout classes |
| `malloc` | returns storage | returns storage and implicitly creates objects |

<details class="fine" markdown="1"><summary>Remaining wording</summary>

¶1 [diff.library.general] says that this subclause summarizes the explicit differences in headers, definitions, declarations and behavior between the C standard library and the parts of the C++ standard library taken from C.

</details>
