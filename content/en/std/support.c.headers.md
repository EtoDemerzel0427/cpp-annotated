---
title: C headers
summary: "In C++, <name.h> headers such as <stdio.h> exist only for interoperability with C; they put names in the global namespace, while <cname> guarantees the names are in std; a few headers such as <complex.h>, <tgmath.h> and <iso646.h> have special rules."
updated: 2026-10-19
---

!!! tldr
    - `<name.h>` headers such as `<stdio.h>` are provided only for interoperability with C; code that doesn't also need to be valid C should use `<cname>` headers such as `<cstdio>`.
    - `<cname>` guarantees the names are in `std`, and `<name.h>` guarantees they are in the global namespace; the other side is only possible in either case.
    - C++-specific `std::byte`, `std::lerp` and the mathematical special functions aren't put into the global namespace by `<name.h>`.
    - `<iso646.h>` is empty; `<complex.h>` and `<tgmath.h>` just include the corresponding C++ headers and put no names in the global namespace.

For each C standard library header `<name.h>`, C++ provides a corresponding `<cname>`, for example `<cstdio>` for `<stdio.h>` ([[headers]], [[library.c]]). This subclause specifies what the original `<name.h>` form means in C++.

## For interoperability only [support.c.headers.general]

¶1 For compatibility with the C standard library, the C++ standard library provides the **C headers** ([[g:c-headers]]) listed in Table 47: `<assert.h>`, `<complex.h>`, `<ctype.h>`, `<errno.h>`, `<fenv.h>`, `<float.h>`, `<inttypes.h>`, `<iso646.h>`, `<limits.h>`, `<locale.h>`, `<math.h>`, `<setjmp.h>`, `<signal.h>`, `<stdalign.h>`, `<stdarg.h>`, `<stdatomic.h>`, `<stdbit.h>`, `<stdbool.h>`, `<stdckdint.h>`, `<stddef.h>`, `<stdint.h>`, `<stdio.h>`, `<stdlib.h>`, `<string.h>`, `<tgmath.h>`, `<time.h>`, `<uchar.h>`, `<wchar.h>`, `<wctype.h>`.

!!! std
    The intended use of these headers is for interoperability only.

These headers are intended for interoperability only: a C++ source file needs to include them if it must also be compilable as C. Source files that aren't intended to also be valid C shouldn't use any of the C headers.

Example 1 is a header that is both valid C++ and valid C:

```cpp
#include <uchar.h>      // C needs it for char8_t; in C++ char8_t is a keyword
#include <stddef.h>     // size_t
#ifdef __cplusplus      // see [cpp.predefined]
extern "C"              // see [dcl.link]
#endif
void f(char8_t s[], size_t n);
```

Compiled as C++, it declares a function with C language linkage; compiled as C, it is just an ordinary function prototype. Note 1 says pure C++ code doesn't need the C headers: they either have no effect (such as `<stdbool.h>` and `<stdalign.h>`), or the corresponding `<cname>` provides the same facilities and guarantees they are defined in `std`.

!!! history
    From C++98 to C++20, the `<name.h>` forms were listed in Annex D as deprecated. C++23's [[P2340R1]] moved them back into this subclause of the main text, undeprecated them, and stated that they exist only for interoperability. This acknowledged reality: headers shared with C have to use `<name.h>`, and these headers will in practice never be removed.

## Where the names go [support.c.headers.other]

```cpp run title="c-headers.cpp" ok
#include <stdlib.h>
#include <cstddef>
#include <stddef.h>

int main() {
  void* p = malloc(4);   // <stdlib.h>: the global name is guaranteed
  free(p);
  std::size_t n = 1;     // <cstddef>: the name in std is guaranteed
  ::size_t m = 2;        // <stddef.h>: the global name is guaranteed
  return n + m == 3 ? 0 : 1;
}
```

¶1 Except for a few special headers (see the next section), every `<name.h>` behaves as if each name placed in namespace `std` by the corresponding `<cname>` is also placed in the global namespace. Whether these names are first declared in `std` and brought into the global namespace with using-declarations, or the other way round, is unspecified.

Four kinds of names are excepted; they are C++-specific, and `<name.h>` doesn't put them in the global namespace:

- the mathematical special functions, such as `std::assoc_laguerre` ([[sf.cmath]]);
- the overloads of `std::lerp` ([[c.math.lerp]]);
- the declaration of `std::byte` ([[cstddef.syn]]);
- the functions operating on `std::byte` ([[support.types.byteops]]).

```cpp error
#include <stddef.h>
#include <cstddef>
::byte b{};   // error: <stddef.h> doesn't put std::byte in the global namespace
```

¶2 Example 1 summarizes the guarantees in both directions:

| Header | Guaranteed | Possible |
|---|---|---|
| `<cstdlib>` | Names in `std` | Also in the global namespace |
| `<stdlib.h>` | Names in the global namespace | Also in `std` |

So writing `::malloc` after including only `<cstdlib>`, or `std::malloc` after including only `<stdlib.h>`, isn't portable. Both compile on mainstream implementations, because libc++'s and libstdc++'s `<cname>` are implemented by including `<name.h>`, but the standard doesn't guarantee it.

## A few special headers

| Header | Specification in C++ | Notes |
|---|---|---|
| `<complex.h>` ([complex.h.syn]) | As if it simply includes `<complex>`; names that `<complex>` places in `std` don't appear in the global namespace | C's `_Complex` and C++'s `std::complex<T>` are different mechanisms |
| `<tgmath.h>` ([tgmath.h.syn]) | As if it includes `<cmath>` and `<complex>`; names aren't put in the global namespace | What C does with type-generic macros, `<cmath>` and `<complex>` already provide with sufficient overloads |
| `<iso646.h>` ([iso646.h.syn]) | Empty | `and`, `or`, `not`, `xor`, `bitand` and so on are keywords in C++ ([[lex.key]]) |
| `<stdalign.h>` ([stdalign.h.syn]) | Same contents as C's `<stdalign.h>` | In C23 `alignas` and `alignof` are already keywords, so this header has almost no contents left |
| `<stdbool.h>` ([stdbool.h.syn]) | Same contents as C's `<stdbool.h>` | In C23 and C++, `bool`, `true` and `false` are all keywords |
| `<stdatomic.h>`, `<stdbit.h>`, `<stdckdint.h>` | Specified by their own subclauses | See [[stdatomic.h.syn]], [[stdbit.h.syn]], [[stdckdint.h.syn]] |
