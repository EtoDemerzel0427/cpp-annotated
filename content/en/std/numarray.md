---
title: "Numeric arrays: valarray"
summary: "valarray and its four slice proxies: the no-aliasing promise and the preconditions it brings; implementations may return expression templates, so auto may dangle; unequal lengths, self-aliasing and repeated indices are UB; resize overwrites every element."
updated: 2026-10-19
---

!!! tldr
    - `valarray` is a one-dimensional array designed in C++98 for numeric computation, supporting element-wise operations, mathematical functions and slicing. The standard guarantees that elements of different arrays never overlap, and implementations can optimize on that basis assuming no aliasing.
    - Operations that return `valarray` may return a replacement type such as an expression template, so `auto e = a + b;` may hold dangling references to temporaries.
    - When assigning or compound-assigning from a slice proxy, the value of any element on the left must not depend on another element on the left, or it is UB; array-with-array operations require equal lengths.
    - The non-const `operator[]` returns proxy objects referring to the original array for slices, masks and index arrays; the const version returns a new `valarray`.
    - `resize` reassigns every element and does not keep the existing ones; `valarray(5, 3)` is three 5s.

## Element-wise operations and slices

```cpp run title="valarray-slices.cpp" ok
#include <cstdio>
#include <valarray>

int main() {
  std::valarray<double> a{1, 2, 3}, b{4, 5, 6};
  std::valarray<double> c = a * b + 1.0;   // {5, 11, 19}
  std::printf("%g %g\n", c.sum(), std::sqrt(c).max());

  std::valarray<char> v0("abcdefghijklmnop", 16);
  std::valarray<char> v1("ABCDE", 5);
  v0[std::slice(2, 5, 3)] = v1;    // positions 2, 5, 8, 11, 14
  for (char ch : v0) std::putchar(ch);   // abAdeBghCjkDmnEp
  std::putchar('\n');

  std::valarray<int> m{1, -2, 3, -4};
  m[m < 0] = 0;                    // mask assignment: {1, 0, 3, 0}
  for (int x : m) std::printf("%d ", x);
}
```

The operations of `valarray` are all element-wise: `a * b + 1.0` is computed once per index, and `sqrt(c)` takes the square root of each element. The slice `slice(2, 5, 3)` selects 5 elements starting at 2 with stride 3, and `m < 0` yields a `valarray<bool>` mask. The slice assignment in the middle is the example the standard gives in [valarray.sub] paragraph 3.

Footnote 227 explains the design intent: to solve the two problems of aliasing ambiguity and the proliferation of temporaries with a minimum of features, so that compilers can optimize it the way they optimize Fortran arrays. It is not used much today: no `push_back`, no allocator, and awkward with the standard algorithms. Multidimensional numeric computation now more commonly uses `mdspan` ([[views.multidim]]) with [[linalg]], and vectorization has [[simd]]. But its rules about aliasing show well how a library trades preconditions for room to optimize.

## The no-aliasing promise

¶2 [valarray.syn] says `valarray` is defined to be free of certain forms of aliasing, allowing operations on it to be optimized. The specific promise is in [valarray.access]:

- ¶3 `addressof(a[i + j]) == addressof(a[i]) + j`: elements are stored contiguously;
- ¶4 for any two arrays `a` and `b`, `addressof(a[i]) != addressof(b[j])`. A note makes explicit that this means there is no aliasing, which compilers can use for optimizations such as inlining, constant propagation and loop fusion.

The effect is like putting C's `restrict` on the storage of every `valarray`: seeing `a[i] = b[i] + c[i]`, the compiler may assume writing `a` does not change `b` or `c`, and vectorize.

¶4 also means a copy is a distinct array. Footnote 230 allows implementations to let arrays share storage, but such an implementation must copy on access, keeping each array conceptually distinct.

¶5 A reference returned by `operator[]` stays valid until `resize` is called or the array's lifetime ends. Per paragraph 1, the index must be less than `size()`, a hardened precondition ([[g:hardened-precondition]]) {{c++26}}: hardened implementations check it, and otherwise out-of-bounds access is UB.

## Expression templates and auto ([valarray.syn] ¶3–¶5)

¶3 Any function returning `valarray<T>` may return an object of another type instead, provided all const member functions of `valarray<T>` other than `begin` and `end` also apply to that type. Such a replacement type may add at most two levels of template nesting over the deepest argument type.

¶4–¶5 An implementation that introduces replacement types must provide, for every function taking `const valarray<T>&`, a version taking the replacement type, and must allow constructing a `valarray` from a replacement type and assigning one to a `valarray` and to the four proxies.

This rule opens the door to **expression templates**: `a + b * c` is not computed immediately; instead it returns a lightweight object recording the structure of the operation, and only when assigned to a `valarray` is it evaluated element by element in a single loop, eliminating intermediate temporary arrays. libc++ implements it this way.

The problem is that such objects hold their operands by reference:

```cpp run title="valarray-auto.cpp" ub
#include <valarray>

std::valarray<int> make(int k) { return std::valarray<int>(k, 3); }

int main() {
  auto e = make(1) + make(2);   // libc++: e refers to two temporary arrays
  return e[0];                  // UB: the temporary arrays are already destroyed
}
```

The two temporary arrays are destroyed at the end of the full-expression ([[class.temporary]]), while the expression object deduced by `auto` is still alive. Run with `-fsanitize=address` in our tests, this reports stack-use-after-scope. The standard allows replacement types to refer to their operands, so the dangling is the program's problem.

Even when the operands are not temporaries, the result can be surprising: after `auto e = w + w; w[0] = 99;`, reading `e[0]` gives 198 in our tests, the value after the modification. The remedy is to write the result type explicitly, `std::valarray<int> e = …;`, so that it is evaluated on the spot.

## Construction and assignment ([valarray.cons], [valarray.assign])

<div class="compare" markdown="1">

```cpp ok
#include <valarray>
// value first, count second: {5, 5, 5}
std::valarray<int> a(5, 3);
```

```cpp ok
#include <valarray>
// list-initialization: {5, 3}
std::valarray<int> b{5, 3};
```

</div>

The constructors are: default construction (length 0); `explicit valarray(size_t n)`, n value-initialized elements; `valarray(const T& v, size_t n)`, with argument order the reverse of `vector(n, v)`; `valarray(const T* p, size_t n)`, requiring `[p, p + n)` to be a valid range; copy and move; `initializer_list`; and converting constructors from the four proxies. `T` must be a numeric type ([[numeric.requirements]]).

¶1–¶3 Copy assignment first adjusts the length if it differs, then assigns. ¶8 `operator=(const T&)` assigns the scalar to every element.

¶10 Assignment from the four proxies has two preconditions: the length the proxy refers to equals `size()`; and the value of any element on the left does not depend on the value of another element on the left. The second is the flip side of the no-aliasing promise; it lets implementations assign in any order, even in parallel. When the right side refers through a proxy to other elements of the left side itself, the result depends on the order of assignment:

```cpp run title="valarray-self-alias.cpp" ub
#include <cstdio>
#include <valarray>

int main() {
  std::valarray<int> v{1, 2, 3, 4};
  // UB: the new value of v[0] depends on v[3], ...
  v = v[std::valarray<std::size_t>{3, 2, 1, 0}];
  for (int x : v) std::printf("%d ", x);   // in our tests: 4 3 3 4
}
```

To reverse in place, make a copy first: `v = std::valarray<int>(v[idx]);`.

## Subset operations and proxy classes

¶1 [valarray.sub] `operator[]` has four pairs of overloads, taking `slice`, `gslice`, `valarray<bool>` (a mask) and `valarray<size_t>` (an index array). The const versions copy the selected elements and return a new `valarray`; the non-const versions return the proxy objects `slice_array<T>`, `gslice_array<T>`, `mask_array<T>` and `indirect_array<T>`, which refer to elements of the original array.

The four proxies have exactly the same structure: the default constructor is deleted, so they can only be created by `operator[]` or copied from an existing proxy; they have `operator=(const valarray<T>&)`, ten compound assignments, and an `operator=(const T&)` that assigns a scalar to all selected elements. These assignment operators are all const members, because the proxy itself does not change; the array it refers to does.

**`slice(start, length, stride)`** ([class.slice]) describes a sequence of `length` indices starting at `start` and taking every `stride`th one, the same as a BLAS slice. `slice(3, 8, 2)` selects 3, 5, 7, …, 17.

**`gslice`** ([class.gslice]) is a generalized slice: defined by a start s, a set of lengths lⱼ and an equal number of strides dⱼ, it maps a multidimensional index (i₀, i₁, …) to s + Σ iⱼ·dⱼ, with the last index varying fastest. It simulates a multidimensional array with a one-dimensional `valarray`, much like `layout_stride` ([[views.multidim]]). Per [class.gslice.overview] paragraphs 4–6, a generalized slice may be degenerate, meaning the same index appears more than once, for example when all the strides are 1. Using a degenerate slice with the non-const `operator[](const gslice&)` is UB, because assigning through it would write the same element several times.

**`mask_array`** selects the elements where the mask is true. **`indirect_array`** selects elements in the order of the index array. [indirect.array.assign] ¶2 and [indirect.array.comp.assign] ¶2 say that assignment or compound assignment is UB when the same element appears more than once in the index array. In the standard's example in paragraph 3, 4 appears twice in the indices `{2, 3, 1, 4, 4}`.

## Other operations

### Compound assignment ([valarray.cassign])

Compound assignment with an array requires (paragraph 2) `size() == v.size()`, and, like proxy assignment, that elements on the left do not depend on each other. Unlike copy assignment, `a += b` does not adjust the length; differing lengths are UB. Compound assignment with a scalar has no length requirement.

### Binary operations and comparison ([valarray.binary], [valarray.comparison])

Array with array, array with scalar, scalar with array; array with array requires equal lengths. Comparisons return `valarray<bool>`, so `a == b` does not test whether two arrays are equal; it is a mask of element-wise comparisons. To get a single `bool`, you can write `(a == b).min()`, provided the arrays are non-empty.

### Mathematical functions ([valarray.transcend])

`abs`, `exp`, `sqrt`, `pow`, `atan2` and so on. *Mandates* requires a unique function of the same name applicable to `T` via unqualified lookup, so they find mathematical functions for user types through ADL.

### Member functions ([valarray.members])



| Member | Key points |
|---|---|
| `sum` | requires `size() > 0`; accumulates with `+=` in an unspecified order, so floating-point results may vary by implementation |
| `min`, `max` | require `size() > 0`; compare with `operator<` |
| `shift(n)` | returns a new array shifted left by n (right if n is negative), filling vacated positions with `T()` |
| `cshift(n)` | circular shift |
| `apply(f)` | returns a new array with `f` applied element-wise |
| `resize(sz, c = T())` | changes the length, then assigns `c` to every element; invalidates all pointers and references |

!!! pitfall "resize does not keep existing elements"
    After `std::valarray<int> r{1, 2, 3}; r.resize(5);`, `r` is `{0, 0, 0, 0, 0}`, not `{1, 2, 3, 0, 0}`. Paragraph 16 of [valarray.members] says it changes the length and then assigns the value of the second argument to each element. This is entirely different from `vector::resize`.

### Iterators ([valarray.range])

In the current draft, `valarray` has member types `iterator` and `const_iterator` and member functions `begin()` and `end()`; the iterators model `contiguous_iterator` and are valid until `resize` or the end of the array's lifetime. This is new wording after C++23; before that there were only the non-member `std::begin(v)` and `std::end(v)`, with unspecified return types. libc++ in our tests still has the old form: `std::begin(v)` works, `v.begin()` does not compile.

<details class="fine" markdown="1"><summary>Remaining wording</summary>

[valarray.syn] ¶1 lists the five class templates, two classes and series of function templates the header defines. Paragraph 6: these functions may throw `bad_alloc` when resources are insufficient, but are not required to. Footnote 226 relates the limit on template nesting depth to the recommendation on template recursion depth in [implimits].

[valarray.unary]: unary `+ - ~ !` require the operator to be applicable to `T` and to return `T` (`bool` for `!`) or something unambiguously convertible to it.

[valarray.cassign] ¶5, ¶9: an array appearing on the left side of a compound assignment does not invalidate references or pointers to its elements.

[valarray.members]: `swap` is constant time and `noexcept`; `size` is constant time.

[cons.slice] ¶1, [gslice.cons] ¶1: a default-constructed `slice` is equivalent to `slice(0, 0, 0)`; it exists so that arrays of slices can be declared. `slice` supports `==`.

</details>
