---
title: C library algorithms
summary: "qsort and bsearch from <cstdlib>: one overload each for comparison functions with C and C++ linkage; qsort requires trivially copyable elements; the semantics follow the C standard; and exceptions thrown by the comparison function may propagate through them."
updated: 2026-10-19
---

!!! tldr
    - `qsort` and `bsearch` each have two overloads, taking `extern "C"` and `extern "C++"` comparison functions respectively, because language linkage is part of a function type.
    - `qsort` moves elements byte by byte, so it requires the elements to be of trivially copyable type; otherwise the behavior is undefined. `std::pair<int, int>` does not qualify either.
    - The rest of the semantics follow the C standard: `qsort` is not stable and has no complexity guarantee, and `bsearch` returns any one of several matches.
    - Exceptions thrown by the comparison function may propagate out through `qsort` and `bsearch`.
    - In C++ you should almost always use `std::sort` and `std::lower_bound` instead.

```cpp run title="qsort.cpp" ok
#include <cassert>
#include <cstdlib>

int cmp_int(const void* x, const void* y) {
    int l = *static_cast<const int*>(x);
    int r = *static_cast<const int*>(y);
    return (l > r) - (l < r);   // do not write l - r: it can overflow
}

int main() {
    int a[] = {3, 1, 2};
    std::qsort(a, 3, sizeof(int), cmp_int);
    assert(a[0] == 1 && a[2] == 3);

    int key = 2;
    auto* p = static_cast<int*>(
        std::bsearch(&key, a, 3, sizeof(int), cmp_int));
    assert(p == a + 1);
}
```

`cmp_int` is an ordinary C++ function with C++ language linkage, while the `qsort` in the C library expects a C function. This code compiles thanks to the first rule in [alg.c.library].

## Two kinds of comparison function types (¶1)

Note 1 of ¶1 says these functions are declared in `<cstdlib>`. In the synopsis each function has two overloads:

```cpp
void qsort(void* base, size_t nmemb, size_t size, c-compare-pred* compar);
void qsort(void* base, size_t nmemb, size_t size, compare-pred* compar);
// likewise for bsearch, with one set each for const and non-const base
```

The exposition-only *c-compare-pred* is the function type `int(const void*, const void*)` with `extern "C"` linkage, and *compare-pred* is the same function type with `extern "C++"` linkage; both are defined in [[cstdlib.syn]].

Two overloads are needed because, per [[dcl.link]], language linkage is part of a function type. A pointer to an `extern "C"` function and a pointer to an `extern "C++"` function are different types, and the calling conventions may differ too. With only the C-linkage version, you could not pass an ordinary C++ function directly, nor a function pointer converted from a captureless lambda. On mainstream implementations the two linkages use the same calling convention, and Clang and GCC do not even distinguish the two function types, but the standard specifies it this way for portability.

`bsearch` is also overloaded on whether `base` is const, returning `void*` and `const void*` respectively. C's `bsearch` takes a `const void*` but returns a `void*`, silently dropping const; the C++ overloads fix that.

## `qsort` requires trivially copyable elements (¶2)

!!! std
    *Preconditions*: For `qsort`, the objects in the array pointed to by `base` are of trivially copyable type.

`qsort` knows only that each element occupies `size` bytes, and it swaps elements by copying bytes. For a type that is not **trivially copyable** ([[g:trivially-copyable-type]], [[basic.types.general]]), copying bytes does not yield a valid object. For example, in a `std::string` with the small string optimization, an internal pointer may point into the object itself; after copying the bytes, the new object's pointer still points to the old location. Violating this is {{ub}}.

`bsearch` does not move elements, so it has no such requirement.

## Semantics from the C standard (¶3)

¶3 specifies that these functions have the semantics specified in the C standard library (ISO/IEC 9899:2024 7.24.6). So:

- the comparison function returns a negative, zero or positive value, and must give a consistent ordering of the array elements, otherwise the behavior is undefined;
- `qsort` is not stable and has no complexity requirement. The C standard does not specify O(N log N), and the q in the name does not mean quicksort must be used;
- `bsearch` requires the array to be sorted (strictly, partitioned) with respect to the key; with several matching elements, it returns any one of them.

!!! pitfall "`return l - r;`"
    A comparison function written the way common in C code, `return *(int*)x - *(int*)y;`, has signed overflow when `l = INT_MIN` and `r = 1`, which is {{ub}}, and the sign of the overflowed result may be wrong as well. Write `(l > r) - (l < r)` instead.

## The comparison function may throw (¶4)

¶4 *Throws*: any exception thrown by `compar`.

C standard library functions generally must not throw exceptions; ¶2 of [[res.on.exception.handling]] lists as an exception the case where a program-supplied function that throws is called, which is exactly the case for `qsort` and `bsearch`. This places a demand on implementations: even if `qsort` itself is written in C, C++ exceptions must be able to propagate from the comparison function through it, so the implementation must generate unwind information for that C code. In our tests (macOS libc with libc++abi), a `std::runtime_error` thrown by the comparison function can be caught normally outside the `qsort` call.

## Why use `std::sort` in C++

| | `qsort` | `std::sort` |
|---|---|---|
| Type safety | `void*`, ensured by the programmer | template, checked by the compiler |
| Element types | only trivially copyable types | any movable, swappable type |
| Complexity guarantee | none | O(N log N) |
| Can the comparison be inlined | called through a function pointer, hard to inline | function objects are usually inlined |
| `constexpr` | no | since C++20 |

The only advantages of `qsort` are code size (one implementation for all types) and interoperability with C interfaces.

## Questions

!!! question "Question"
    Is it valid to sort an array of `std::pair<int, int>` with `std::qsort`?

<details markdown="1">
<summary>Answer</summary>

No. The standard declares `pair`'s copy assignment operator as an ordinary member function rather than a defaulted one, so that it handles reference members correctly. It is therefore not trivial, `pair<int, int>` is not a trivially copyable type, and sorting it with `qsort` violates the precondition of ¶2, which is {{ub}}. With libc++ in our tests, `std::is_trivially_copyable_v<std::pair<int, int>>` is `false`. Use `std::sort` instead.
</details>
