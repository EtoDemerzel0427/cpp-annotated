---
title: "Multidimensional access: mdspan"
summary: "std::mdspan indexes a block of contiguous memory with a multidimensional shape: extents describe the shape, a layout mapping converts multidimensional indices to an offset, and an accessor turns the offset into an element reference; plus C++26's slicing function submdspan and the post-C++26 multidimensional copy/fill."
updated: 2026-10-19
---

!!! tldr
    - `mdspan` does not own memory. It consists of three parts: the shape `extents`, a layout mapping that converts multidimensional indices into a one-dimensional offset, and an accessor that turns the offset into an element reference. `m[i, j]` goes through these three steps in turn.
    - Each dimension of `extents` can be a compile-time constant (static) or a run-time value (dynamic), and only dynamic dimensions take storage. An `mdspan` of rank 0 has exactly one element.
    - The default layout `layout_right` is row-major, `layout_left` is column-major, and `layout_stride` allows arbitrary positive strides; C++26 adds two padded layouts.
    - A hardened implementation checks the indices of `m[i, j]` dimension by dimension, but no implementation can check whether the buffer you passed in is large enough.
    - C++26's `submdspan` takes subviews and preserves contiguous layouts where possible. libc++ in Clang 23 does not yet implement `submdspan`, the padded layouts or the multidimensional `copy`/`fill`.

## One block of memory, indexed with a multidimensional shape

```cpp run title="mdspan-basics.cpp" ok
#include <cstdio>
#include <mdspan>
#include <stdexcept>
#include <type_traits>
#include <vector>

int main() {
  std::vector<double> buf(12);
  std::mdspan m(buf.data(), 3, 4);   // 3 rows, 4 columns
  static_assert(std::is_same_v<decltype(m),
                std::mdspan<double, std::dextents<std::size_t, 2>>>);

  for (std::size_t i = 0; i < m.extent(0); ++i)
    for (std::size_t j = 0; j < m.extent(1); ++j)
      m[i, j] = 10.0 * i + j;        // C++23 multi-argument operator[]

  std::printf("%g %g\n", m[2, 3], buf[2 * 4 + 3]);   // 23 23

  try {
    (void)m.at(3, 0);                // C++26: out of bounds throws out_of_range
  } catch (const std::out_of_range&) {
    std::puts("at(3, 0) threw");
  }

  std::mdspan<double, std::extents<int, 3, 4>> fixed(buf.data());
  std::printf("%zu %zu\n", sizeof(m), sizeof(fixed));   // libc++: 24 8
}
```

Scientific computing, image processing and linear algebra often need this: the data sits in one flat block of memory but must be accessed with a two- or three-dimensional shape. Hand-written `a[i * ncols + j]` scatters the shape and strides over every index computation; `int a[3][4]` requires compile-time sizes; the data of `vector<vector<int>>` is not contiguous.

`std::mdspan` (C++23) is a multidimensional view over such a block of memory. Like `span`, it does not own the storage, and copying it copies only the pointer and the shape ([[views]]). `m[i, j]` computes the element in three steps:

```text
m[i, j, k]
  ├─ extents  : the shape. How long is each dimension? Which are known at compile time?
  ├─ mapping  : (i, j, k) → one-dimensional offset. Row-major? Column-major? Strided?
  └─ accessor : (data handle, offset) → element reference
```

[[mdspan.mdspan.members#4]] writes `operator[]` in a single line:

```cpp
return acc_.access(ptr_, map_(static_cast<index_type>(std::move(indices))...));
```

The last two template parameters of `mdspan<T, Extents, LayoutPolicy, AccessorPolicy>` default to `layout_right` and `default_accessor<T>`. In the example, the two run-time lengths make `m` store a pointer plus two `size_t`s, 24 bytes in all; the shape of `fixed` is in its type, so it stores only a pointer.

!!! impl "Implementation status in libc++ (the libc++ shipped with Clang 23, used to verify the examples below)"
    | Facility | Status |
    |---|---|
    | `extents`, `dextents`, `dims`, `layout_left`/`right`/`stride`, `default_accessor`, `mdspan` (including multi-argument `operator[]` and CTAD) | Implemented |
    | `aligned_accessor`, `mdspan::at`, deducing static extents via `std::cw<N>` | Implemented |
    | `layout_left_padded`, `layout_right_padded` | Not implemented |
    | `submdspan`, `full_extent`, `extent_slice`, `range_slice`, `canonical_slices`, `subextents` | Not implemented |
    | Multidimensional `copy`, `fill` | Not implemented |

    Code blocks that use unimplemented facilities carry no verdict and serve only to illustrate what the standard specifies.

## Shape: `extents` [mdspan.extents]

### Multidimensional index space [mdspan.overview]

[[mdspan.overview#1]] defines a few basic terms. A **multidimensional index space** ([[g:multidimensional-index-space]]) is a Cartesian product of half-open integer intervals `[Lᵢ, Uᵢ)`. The number of intervals is its **rank**. Its **size** is the product of `Uᵢ − Lᵢ` over all dimensions; for rank 0 the size is 1, consistent with the convention that an empty product is 1.

[[mdspan.overview#3]] calls a pack of integers a **multidimensional index** in the space if its length equals the rank and the ith value lies in the ith interval. Every later rule about out-of-bounds access is phrased as "such and such is not a multidimensional index". The space represented by `extents` always has lower bound 0; the interval of dimension r is `[0, Dᵣ)` ([[mdspan.extents.overview#4]]).

So an `mdspan` of rank 0 is not empty: it has exactly one element, accessed with an empty index list `m[]`, which amounts to a view of a single object:

```cpp run title="rank0.cpp" ok
#include <cstdio>
#include <mdspan>

int main() {
  int x = 7;
  std::mdspan<int, std::extents<int>> d(&x);   // rank 0: exactly one element
  d[] = 3;                                       // empty index list
  std::printf("%d %u\n", x, unsigned(d.size())); // 3 1
}
```

### Static and dynamic dimensions

Each template argument of `extents<IndexType, Extents...>` is either a concrete length, called a **static extent** ([[g:static-extent]]), or `dynamic_extent`, called a **dynamic extent** ([[g:dynamic-extent]]), whose value is stored in the object at run time. Only dynamic extents take storage; an all-static `extents` is an empty class.

```cpp run title="extents.cpp" ok
#include <cstdio>
#include <mdspan>
#include <type_traits>

using E = std::extents<int, 3, std::dynamic_extent, 4>;   // the middle dimension is dynamic

int main() {
  static_assert(E::rank() == 3 && E::rank_dynamic() == 1);
  static_assert(E::static_extent(1) == std::dynamic_extent);

  E e1(5);         // give only the dynamic extents
  E e2(3, 5, 4);   // give all extents: values at static positions must match (precondition)
  std::printf("%d %d\n", e1.extent(1), int(e1 == e2));   // 5 1

  // only dynamic extents take storage; libc++ prints 1 4
  std::printf("%zu %zu\n", sizeof(std::extents<int, 3, 4>), sizeof(E));

  static_assert(std::is_same_v<std::dextents<int, 2>,
      std::extents<int, std::dynamic_extent, std::dynamic_extent>>);
  static_assert(std::is_same_v<std::dims<2>, std::dextents<std::size_t, 2>>);
}
```

[[mdspan.extents.overview#1]] requires `IndexType` to be a signed or unsigned integer type, with every static extent representable in it. Every specialization of `extents` models `regular` and is trivially copyable (¶2).

`extents` has three integer member types: `index_type` (which is `IndexType`, used for indices, `extent(r)` and the results of mappings), `size_type` (`make_unsigned_t<index_type>`, used for `mdspan::size()`), and `rank_type` (`size_t`, used to number dimensions).

`index_type` is often chosen to be `int` rather than `size_t`. Signed overflow is UB, so the compiler can assume `i * stride + j` does not overflow and vectorize and strength-reduce more aggressively, which matters especially in GPU code.

### Construction and conversion [mdspan.extents.cons]

`extents` can be constructed from a pack of integers, a `span`/`array`, or another `extents`. Note 1 of [[mdspan.extents.cons#6]] describes the two ways of giving an integer pack: only the dynamic extents (exactly the values to be stored), or all extents. In the latter case, the values at static positions must match the template arguments; this is a precondition that the compiler does not check. All given values must be non-negative and representable by `index_type`.

When converting from another `extents`, the ranks must be equal, and corresponding dimensions must either have equal static values or have at least one side dynamic (¶1). [[mdspan.extents.cons#4]] makes the conversion `explicit` in the following two cases:

```cpp
(((Extents != dynamic_extent) && (OtherExtents == dynamic_extent)) || ... ) ||
(numeric_limits<index_type>::max() < numeric_limits<OtherIndexType>::max())
```

The first half says that going from dynamic to static needs the programmer to vouch for the length, as with `span`; the second half says that a narrower range of `index_type` needs vouching too. So converting from `extents<size_t, ...>` to `extents<int, ...>` must be explicit even when the shapes are identical. This rule propagates all the way to conversions of mappings and of `mdspan`.

The deduction guide `extents(Integrals...)` deduces `extents<size_t, ...>` (¶12–¶13). Ordinary integers deduce dynamic extents, while integral constant wrappers like `std::cw<4uz>` deduce static extents.

### Observers and aliases

- `static_extent(i)` returns the ith template argument (possibly `dynamic_extent`), and `extent(i)` returns the actual length of dimension i ([[mdspan.extents.obs]]).
- Two `extents` are equal if and only if their ranks are equal and every dimension has the same length, regardless of static or dynamic and regardless of `index_type` ([[mdspan.extents.cmp]]).
- `dextents<IndexType, Rank>` is an all-dynamic `extents`; C++26's `dims<Rank, IndexType = size_t>` is the same thing with the parameters reversed and a default for `IndexType`.

## Layout mappings: from multidimensional indices to offsets [mdspan.layout]

### What a mapping must satisfy [mdspan.layout.reqmts]

A **layout mapping** ([[g:layout-mapping]]) is an object `m` for which `m(i, j, ...)` converts a multidimensional index into a one-dimensional offset. [[mdspan.layout.reqmts#1]] requires it to be copyable and equality comparable, with non-throwing move and swap, and to provide:

| Expression | Meaning |
|---|---|
| `m.extents()` | The shape |
| `m(i...)` | The offset, non-negative; converting the indices to `index_type` first does not change the result |
| `m.required_span_size()` | 0 if the size is 0, otherwise the largest offset plus 1 |
| `m.is_unique()` | Different indices map to different offsets |
| `m.is_exhaustive()` | Every offset in `[0, required_span_size())` has some index mapping to it |
| `m.is_strided()` | Each dimension has a fixed stride `sᵣ`: one step along dimension r increases the offset by `sᵣ` |
| `m.stride(r)` | Precondition `is_strided()`; returns `sᵣ` |
| `M::is_always_unique()` and the other two | Constant expressions; may be `true` only if the property holds for every object of the type |

`required_span_size()` is not the number of elements but the minimum length of the underlying storage. In layouts with gaps it is larger than `size()`; in layouts that let several indices refer to the same element it may be smaller than `size()`.

All three properties are one-way guarantees. [[mdspan.layout.reqmts#14]], ¶16 and ¶18 are all written as "returns `true` only if…", and Notes 1, 2 and 4 say explicitly that they may return `false` even when the condition holds, because for some layouts determining it exactly is too costly. Generic code can rely only on `true`; `false` just means "unknown".

These three properties decide which optimizations are possible: with unique, parallel writes do not conflict, and the multidimensional `copy` requires the target to be `is_unique()`; with exhaustive, the whole storage can be treated as a one-dimensional array; with strided, the data can be handed to BLAS interfaces that take stride parameters.

### Policies and mappings [mdspan.layout.policy.reqmts]

The template parameter of `mdspan` is a **layout mapping policy**, not the mapping itself. A policy `MP` is a mapping factory: for any specialization `E` of `extents`, `MP::mapping<E>` is a mapping meeting the requirements above, whose `layout_type` is `MP` and whose `extents_type` is `E`. That way the same layout can be applied to any shape. All five standard policies are trivially copyable, trivially default constructible empty structs ([[mdspan.layout.policy.overview]]).

Taking rank 2, shape `R × C` and index `(i, j)` as an example:

| Policy | Offset | unique / exhaustive / strided |
|---|---|---|
| `layout_right` | `i * C + j` (row-major, the C convention) | Always / always / always |
| `layout_left` | `i + j * R` (column-major, the Fortran convention) | Always / always / always |
| `layout_stride` | `i * s₀ + j * s₁` | Always / depends on the strides / always |
| `layout_right_padded<P>` {{c++26}} | `i * S + j`, with row stride `S >= C` | Always / when `S == C` / always |
| `layout_left_padded<P>` {{c++26}} | `i + j * S`, with column stride `S >= R` | Always / when `S == R` / always |

```cpp run title="layout-mappings.cpp" ok
#include <array>
#include <cstdio>
#include <mdspan>

int main() {
  using E = std::extents<int, 2, 3>;
  std::layout_right::mapping<E> r(E{});
  std::layout_left::mapping<E>  l(E{});
  std::printf("right: %d %d,%d\n", r(1, 1), r.stride(0), r.stride(1));  // 4 3,1
  std::printf("left : %d %d,%d\n", l(1, 1), l.stride(0), l.stride(1));  // 3 1,2

  // every other element: unique and strided, but not exhaustive
  std::layout_stride::mapping<std::extents<int, 3>> every_other(
      std::extents<int, 3>{}, std::array{2});
  std::printf("%d %d\n", int(every_other.is_exhaustive()),
              every_other.required_span_size());   // 0 5
}
```

### `layout_left` and `layout_right`

The two are completely symmetric. Taking `layout_left` as the example ([[mdspan.layout.left]]): the leftmost dimension has stride 1, and each dimension to the right has a stride equal to the product of the lengths of the dimensions to its left. When everything is static, the size of the whole space must be representable by `index_type`, or it is rejected at compile time ([[mdspan.layout.left.overview#4]]).

Conversions between mappings must guarantee that the same index yields the same offset:

- converting from another `layout_left::mapping` is `explicit` exactly when the `extents` conversion is;
- converting from `layout_right::mapping` is allowed only when rank ≤ 1 ([[mdspan.layout.left.cons#6]]), because in one dimension row-major and column-major are the same mapping;
- converting from `layout_stride::mapping` has the precondition that the strides are exactly the column-major strides, and is `explicit` except for rank 0 (¶16).

```cpp run title="layout-conversions.cpp" ok
#include <mdspan>
#include <type_traits>

using E1 = std::extents<int, 4>;
using E2 = std::extents<int, 2, 3>;
using L1 = std::layout_left::mapping<E1>;
using R1 = std::layout_right::mapping<E1>;
using L2 = std::layout_left::mapping<E2>;
using R2 = std::layout_right::mapping<E2>;
using S2 = std::layout_stride::mapping<E2>;

static_assert(std::is_convertible_v<R1, L1>);       // rank 1: convertible either way
static_assert(!std::is_constructible_v<L2, R2>);    // rank 2: not allowed
static_assert(std::is_convertible_v<L2, S2>);       // left → stride: implicit
static_assert(std::is_constructible_v<L2, S2>);     // stride → left:
static_assert(!std::is_convertible_v<S2, L2>);      //   explicit only

int main() {}
```

### `layout_stride` [mdspan.layout.stride]

The strides of `layout_stride` are given by the user. The precondition of [[mdspan.layout.stride.cons#4]] is strong: every stride must be greater than 0, and there must be a permutation of the dimensions such that, in that order, each dimension's stride is at least the previous dimension's stride times the previous dimension's length. Note 1 says this condition guarantees that `is_unique()` is true.

So `layout_stride` cannot express layouts where several indices refer to the same element, nor broadcasting with stride 0 or reversal with negative strides; those need custom mappings. It can be constructed from any mapping that is always unique and always strided, user-defined mappings included (¶6), provided the source mapping maps the all-zero index to offset 0 (¶7.4). `is_exhaustive()` checks at run time whether the strides form exactly a dense arrangement under some ordering of the dimensions ([[mdspan.layout.stride.obs#6]]).

### Padded layouts {{c++26}}

Rows of a matrix often have padding at the end, for example so that each row starts on a 64-byte boundary, or because the matrix is a sub-block of a larger matrix. `layout_right_padded<PaddingValue>` is the same as `layout_right` except that the row stride `stride(rank() − 2)` may be larger than the length of the last dimension; `layout_left_padded` symmetrically relaxes the column stride `stride(1)` ([[P2642R6]]).

The stride is rounded up to a multiple of `PaddingValue`. For example, the column stride of `layout_left_padded<4>::mapping<extents<int, 5, 3>>` is the smallest multiple of 4 not less than 5, namely 8; the strides of the two dimensions are 1 and 8, and `required_span_size()` is `(5−1)·1 + (3−1)·8 + 1 = 21`. When the stride is known at compile time, [[mdspan.layout.leftpad.expo#2]] recommends that implementations not store it. Such a mapping is exhaustive only when the stride exactly equals the length of that dimension.

As we will see later, the most natural layout for a submatrix sliced out of a row-major matrix is `layout_right_padded`. libc++ does not implement these two layouts yet, so this section has no runnable example.

## Accessors: from offset to element [mdspan.accessor]

An **accessor policy** ([[g:accessor-policy]]) specifies how to obtain a reference to an element from a data handle and an offset ([[mdspan.accessor.general#1]]). If the access function yields a valid reference for every `i` in `[0, N)`, then `[0, N)` is called an **accessible range** of that handle and accessor (¶2). The preconditions of all `mdspan` constructors are phrased in these terms.

The data handle `data_handle_type` need not be a pointer, nor even dereferenceable (¶3 Note 1); it could be a GPU device pointer, a handle to remote memory, or the index of a compressed block. [[mdspan.accessor.reqmts]] requires an accessor to provide:

| Member | Requirement |
|---|---|
| `element_type` | A complete object type that is not an abstract class |
| `data_handle_type` | Copyable, with non-throwing move and swap |
| `reference` | Has a common reference with `element_type&`; may be a proxy, such as `atomic_ref<T>` |
| `offset_policy` | Another accessor type, constructible from this accessor, with the same element type |
| `a.access(p, i)` | Returns a `reference` |
| `a.offset(p, i)` | Returns a handle `q` such that accessing element `j` of `q` with `offset_policy` is the same as accessing element `i + j` of `p` |

`offset_policy` exists for slicing: taking a subview moves the data handle forward, and after the move some original properties (such as alignment) may no longer hold, so a different accessor type is allowed.

### `default_accessor`

The simplest accessor: the handle is `ElementType*`, `access(p, i)` is just `p[i]`, and `offset(p, i)` is just `p + i` ([[mdspan.accessor.default.members]]). `[0, n)` is an accessible range if and only if `[p, p + n)` is a valid range.

Its converting constructor allows only qualification conversions: it is available only if `OtherElementType(*)[]` is convertible to `element_type(*)[]` ([[mdspan.accessor.default.members#1]]). So `mdspan<int>` converts implicitly to `mdspan<const int>`, but `mdspan<Derived>` does not convert to `mdspan<Base>`. `ElementType` cannot be an array type; multiple dimensions are the job of `extents`.

### `aligned_accessor` {{c++26}}

`aligned_accessor<ElementType, ByteAlignment>` ([[P2897R7]]) promises the compiler that the data handle is aligned to `ByteAlignment` bytes:

- `ByteAlignment` must be a power of 2 and no less than `alignof(ElementType)`;
- besides `[p, p + n)` being valid, an accessible range also requires `is_sufficiently_aligned<ByteAlignment>(p)` to be true when `n > 0` ([[mdspan.accessor.aligned.overview#5]], [[ptr.align]]);
- `access(p, i)` is equivalent to `assume_aligned<ByteAlignment>(p)[i]`, handing the alignment assumption directly to the optimizer so it can emit aligned SIMD loads;
- `offset_policy` is `default_accessor`, because `p + i` is in general no longer aligned.

The conversion directions reflect who bears the burden of the promise: from `aligned_accessor` to `default_accessor` is implicit, since dropping a promise is always safe; from `default_accessor` to `aligned_accessor` is `explicit`, since making a promise out of thin air must be written out; a larger alignment converts implicitly to a smaller one.

```cpp run title="aligned-accessor.cpp" ok
#include <cstdio>
#include <mdspan>
#include <memory>
#include <type_traits>

using Aligned = std::aligned_accessor<float, 16>;
using V4 = std::mdspan<float, std::extents<int, 4>,
                       std::layout_right, Aligned>;

float sum4(V4 x) { return x[0] + x[1] + x[2] + x[3]; }

int main() {
  alignas(16) float buf[8] = {1, 2, 3, 4, 5, 6, 7, 8};
  std::mdspan<float, std::extents<int, 4>> plain(buf);

  if (std::is_sufficiently_aligned<16>(plain.data_handle())) {
    // default_accessor → aligned_accessor must be explicit
    V4 a(plain.data_handle(), plain.mapping(), Aligned{});
    std::printf("%g\n", sum4(a));   // 10
  }
  static_assert(std::is_same_v<Aligned::offset_policy,
                               std::default_accessor<float>>);
  static_assert(!std::is_convertible_v<std::default_accessor<float>, Aligned>);
  static_assert(std::is_convertible_v<Aligned, std::default_accessor<float>>);
}
```

If `buf` is not actually aligned but an `mdspan` using `aligned_accessor` is constructed anyway, the constructor's precondition about the accessible range is violated and the behavior is undefined. When the assumption of `assume_aligned` does not hold, the aligned load instructions the optimizer emits may crash the program outright.

## `mdspan` itself [mdspan.mdspan]

### Type requirements ([[mdspan.mdspan.overview]])

`mdspan` has just three exposition members: the accessor `acc_`, the mapping `map_` and the data handle `ptr_`. `ElementType` must be a complete object type that is neither an abstract class nor an array, and the same as the accessor's `element_type` (¶2). Every specialization is copyable; when the accessor, mapping and handle are all trivially copyable, so is the `mdspan` (¶5).

### Construction and type deduction

All constructors share one precondition: `[0, map_.required_span_size())` is an accessible range of `ptr_` and `acc_`. `mdspan` cannot check this, and passing a buffer that is too small is {{ub}} (see the section on common misconceptions).

- Default construction requires `rank_dynamic() > 0` ([[mdspan.mdspan.cons#1]]). A default-constructed pointer is null, and the only accessible range of a null pointer is `[0, 0)`, so `required_span_size()` must be 0; that can be guaranteed only when there is a dynamic extent (value-initialized to 0). An all-static `mdspan` therefore has no default constructor.
- `(p, exts...)` accepts `rank()` or `rank_dynamic()` lengths and is always `explicit`; `(p, span or array)` is `explicit` when the count differs from `rank_dynamic()`.
- `(p, extents)`, `(p, mapping)` and `(p, mapping, accessor)`. Only the last can pass in an accessor that is not default constructed.
- Conversion from another `mdspan`: if the conversion of the mapping or accessor is `explicit`, so is this conversion (¶24). A hardened implementation checks that each static dimension matches the actual length of the source (¶22).

The commonly used deduction guides:

| Arguments | Deduced type |
|---|---|
| One-dimensional C array | `mdspan<T, extents<size_t, N>>`, static extent |
| Raw pointer | `mdspan<T, extents<size_t>>`, rank 0 |
| `(T*, integers...)` | Ordinary integers deduce dynamic extents, `std::cw<N>` deduces static extents |
| `(T*, span<I, N>)` or `(T*, array<I, N>)` | `mdspan<T, dextents<size_t, N>>` |
| `(T*, extents)` or `(T*, mapping)` | Keeps the `extents`, or takes the mapping's `extents_type` and `layout_type` |

```cpp run title="mdspan-ctad-conversions.cpp" ok
#include <array>
#include <mdspan>
#include <type_traits>
#include <utility>

int buf[12];
std::mdspan a(buf, std::cw<3uz>, std::cw<4uz>);   // static extents
static_assert(std::is_same_v<decltype(a),
              std::mdspan<int, std::extents<std::size_t, 3, 4>>>);
std::mdspan b(buf, std::array{3, 4});              // dynamic extents
static_assert(std::is_same_v<decltype(b), std::mdspan<int, std::dims<2>>>);
std::mdspan c(buf);                                // C array: rank 1
static_assert(std::is_same_v<decltype(c),
              std::mdspan<int, std::extents<std::size_t, 12>>>);
int* p = buf;
std::mdspan d(p);                                  // raw pointer: rank 0
static_assert(decltype(d)::rank() == 0);

// int → const int, static → dynamic: implicit
std::mdspan<const int, std::dims<2>> ro1 = a;
// index_type narrowing from size_t to int: must be explicit
std::mdspan<const int, std::dextents<int, 2>> ro2{a};

static_assert(!std::is_default_constructible_v<
              std::mdspan<int, std::extents<int, 3>>>);
static_assert(std::is_default_constructible_v<std::mdspan<int, std::dims<1>>>);
static_assert(std::is_trivially_copyable_v<std::mdspan<int, std::dims<2>>>);

int main() {}
```

The `ro2` line is the most surprising: the shapes are fully compatible and the elements only gain const, yet the conversion must be explicit. The reason is that `extents<size_t, …>` to `extents<int, …>` narrows the range of values ([[mdspan.extents.cons#4]]), which propagates to `mdspan` through `explicit(!is_convertible_v<OtherExtents, extents_type>)` on `layout_right::mapping`. CTAD from integers deduces `size_t` as the index type, while hand-written function parameters often use `int`; this is the non-implicit conversion `mdspan` users run into most often.

Note the difference between arrays and pointers: in `std::mdspan m(buf)`, if `buf` is an `int[12]`, rank 1 with length 12 is deduced; if it is an `int*`, rank 0 is deduced.

### Subscripting [mdspan.mdspan.members]

`operator[]` takes exactly `rank()` indices (¶1). ¶3 gives a hardened precondition: the indices must be a multidimensional index in `extents()`, that is, each dimension must be in range on its own. Note 1 points out that this implies the final offset is less than `required_span_size()`, but not conversely.

The multi-argument `operator[]` relies on a C++23 syntax change: the brackets may contain a comma-separated list, passed to an overloaded `operator[]` ([[expr.sub]], [[over.sub]], [[P2128R6]]). The built-in subscript still accepts only a single expression. C++20 first deprecated comma expressions in subscripts, `a[i, j]`, and C++23 then gave the syntax over to multi-argument subscripts.

A `span` or `array` can also be passed as the index, with the same effect as expanding it and calling with the elements (¶5–¶6). C++26's `at()` throws `out_of_range` when the indices are not a multidimensional index (¶7–¶12). `size()` returns the unsigned `size_type` (¶13–¶14), and `empty()` is true when the size is 0.

```cpp run title="mdspan-subscript-errors.cpp" error
#include <mdspan>

int buf[12];
std::mdspan<int, std::dims<2>> m(buf, 3, 4);
int x = m[1][2];                                   // error: no single-argument operator[]
int y = m[1, 2];                                   // OK
std::mdspan<int, std::extents<int, 3, 4>> s1 = m;  // error: dynamic → static must be explicit
std::mdspan<int, std::extents<int, 3, 4>> s2{m};   // OK: a hardened implementation checks the lengths
```

### Same memory, different views

Changing the layout changes the interpretation without moving a single byte of data:

```cpp run title="mdspan-views.cpp" ok
#include <array>
#include <cstdio>
#include <mdspan>

int main() {
  int buf[6] = {0, 1, 2, 3, 4, 5};
  std::mdspan<int, std::extents<int, 2, 3>> a(buf);   // 2×3 row-major
  // the same memory viewed as 3×2 column-major: exactly the transpose of a
  std::mdspan<int, std::extents<int, 3, 2>, std::layout_left> t(buf);
  for (int i = 0; i < 2; ++i)
    for (int j = 0; j < 3; ++j)
      if (a[i, j] != t[j, i]) return 1;

  // only column 1: length 2, stride 3, starting at offset 1
  using L = std::layout_stride::mapping<std::extents<int, 2>>;
  std::mdspan col(buf + 1, L(std::extents<int, 2>{}, std::array{3}));
  std::printf("%d %d %d\n", col[0], col[1],
              int(col.is_exhaustive()));   // 1 4 0
}
```

## Taking subviews: `submdspan` {{c++26}} [mdspan.sub]

`submdspan(m, slices...)` takes one **slice specifier** per dimension and returns a new `mdspan` that views only part of the elements of the original. It was added to C++26 by [[P2630R4]], and the slice types and helper functions were later reworked (the feature-test macro `__cpp_lib_submdspan` is now 202603L). The following describes the current draft; libc++ implements none of the facilities in this section yet.

According to the current draft, the results of the following lines are as the comments say:

```cpp
double buf[24];
std::mdspan m(buf, 4, 6);          // 4×6, layout_right

auto row = std::submdspan(m, 2, std::full_extent);
// rank 1, length 6, layout_right
auto col = std::submdspan(m, std::full_extent, 3);
// rank 1, length 4, layout_stride, stride 6
auto blk = std::submdspan(m, std::pair{1, 3}, std::pair{2, 5});
// 2×3, layout_right_padded<dynamic_extent>, row stride 6
auto odd = std::submdspan(m, std::full_extent,
                          std::extent_slice{1, 3, 2});
// 4×3, columns 1, 3 and 5, layout_stride
```

### Kinds of slices [mdspan.sub.overview]

[[mdspan.sub.overview#2]] lists the types usable as slices:

| Slice | Meaning | This dimension in the result |
|---|---|---|
| Convertible to `full_extent_t`, i.e. `std::full_extent` | The whole dimension | Kept, length unchanged |
| An integer convertible to `IndexType` | Fixes the index in this dimension | Disappears; rank decreases by 1 |
| `extent_slice{offset, extent, stride}` | Takes `extent` elements starting at `offset`, with stride `stride` | Kept, with length `extent` |
| `range_slice{first, last, stride}` | Takes elements in `[first, last)` with the given stride | Kept |
| A type that a structured binding can split into two integers, such as `pair{a, b}` | `[a, b)` | Kept, with length `b − a` |

A slice that makes a dimension disappear is a **collapsing slice** (¶5). A whole dimension and an `extent_slice` whose stride is the compile-time constant 1 are **unit-stride slices** (¶6); they decide whether the result can keep a contiguous layout.

!!! warning "The `extent` of `extent_slice` is the number of elements selected"
    `extent_slice{.offset = 1, .extent = 4, .stride = 3}` and `range_slice{.first = 1, .last = 11, .stride = 3}` both select indices 1, 4, 7 and 10 ([[mdspan.sub.range.slices#3]] Note 1). The `extent` of `extent_slice` is the length of the result, 4, not the length of the original interval. In P2630's `strided_slice`, which has the same fields, `extent` meant the length of the original interval; take special care when migrating from older material.

### Canonicalization

`submdspan` first converts every slice to one of three **canonical forms**: `full_extent_t`, an index (`IndexType` or `constant_wrapper<v>`), or an `extent_slice` whose fields are all canonical indices ([[mdspan.sub.overview#4]]). `pair` and `range_slice` are both converted to `extent_slice`, with element count `1 + (span − 1) / stride` ([[mdspan.sub.helpers#7]]).

Compile-time constants are preserved in this step: `std::cw<N>` canonicalizes to `cw<IndexType(N)>`, not to a plain integer. After canonicalization, if the `extent` of an `extent_slice` is a `constant_wrapper`, that dimension of the result has a static extent; a whole dimension keeps its original static extent; everything else is dynamic ([[mdspan.sub.extents#5]]). The public `canonical_slices` and `subextents` return the canonicalized slices and the shape of the result respectively.

Each slice must lie within the range of its dimension, and when more than one element is selected the stride must be positive. Violating this is an ordinary precondition violation ([[mdspan.sub.sub#6]]) with undefined behavior, not a hardened precondition.

### Which layout the result uses

`submdspan` itself does not know how to slice an arbitrary layout. It hands the canonical slices to `submdspan_mapping(src.mapping(), slices...)`, a name looked up only by ADL ([[mdspan.sub.map.sliceable#2]], [[basic.lookup.argdep]]). The standard layouts provide it as hidden friends, and custom layouts can provide it too. The return value `submdspan_mapping_result{mapping, offset}` gives the new mapping and the starting offset, from which [[mdspan.sub.sub#7]] constructs the result:

```cpp
auto sub_map_result = submdspan_mapping(src.mapping(), slices...);
return mdspan(src.accessor().offset(src.data_handle(), sub_map_result.offset),
              sub_map_result.mapping,
              typename AccessorPolicy::offset_policy(src.accessor()));
```

Note the last argument: the accessor of the result is the original accessor's `offset_policy`. For `aligned_accessor`, slicing turns it back into `default_accessor`.

Taking `layout_right` as the example, the layout of the result is chosen in the following order ([[mdspan.sub.map.right#1]]):

1. If the original rank is 0, return it as is; if the result's rank is 0, use `layout_right`.
2. If, among the dimensions of the result, the last few are whole dimensions, the one before them is a unit-stride slice, and all earlier ones are collapsed indices: still `layout_right`. `row` in the example is like this.
3. If the last dimension is a unit-stride slice and the other conditions of (1.4) are met: `layout_right_padded`, with the row stride taken from the original mapping. Both dimensions of `blk` in the example are unit-stride slices, but the second is not a whole dimension, so it gets a padded layout with row stride 6.
4. Otherwise `layout_stride`. The last dimension of `col` and of `odd` in the example is not a unit-stride slice, so both land here.

`layout_left` mirrors this, slicing a `layout_stride` always gives `layout_stride`, and the two padded layouts have their own rules. The intent of these rules is to keep a contiguous layout whenever contiguity can be proven, thereby preserving compile-time properties like `is_always_exhaustive()` so that downstream code can stay on fast paths. Without `layout_right_padded`, `blk` would have to degrade to `layout_stride` and lose the information that each row is contiguous.

## Multidimensional `copy` and `fill` {{c++29}} [mdspan.copy]

Drafts after C++26 add `mdspan` versions of `std::copy(src, dst)` and `std::fill(dst, value)` to `<mdspan>`, each with overloads taking an execution policy (`__cpp_lib_mdspan_copy` is 202606L):

- `copy` requires both sides to be `mdspan`s, `Dst::reference` to be assignable from `Src::reference`, and the two `extents` to be compatible ([[mdspan.copy#1]]);
- the preconditions are `dst.is_unique()` and that the source and destination elements do not overlap (¶2); the hardened precondition is that the two `extents()` are equal (¶3);
- the effect is element-wise assignment, with no traversal order specified. That is precisely why the target must be unique and the two sides must not overlap: the implementation can choose the fastest traversal order for the two layouts, or even vectorize.

These differ in arity from `std::copy(first, last, out)` and `std::fill(first, last, value)` in `<algorithm>`, and both are constrained, so they do not interfere with each other. libc++ does not implement them yet.

## Common misconceptions

!!! pitfall "Hardening mode will catch a buffer that is too small"
    Constructing an `mdspan` requires `[0, required_span_size())` to be an accessible range, but no implementation can know how much storage lies behind a raw pointer.

```cpp run title="mdspan-too-small.cpp" ub
#include <mdspan>

int main() {
  int buf[6]{};
  std::mdspan m(buf, 3, 4);   // UB: requires [0, 12) to be accessible, but buf has only 6 elements
  return m[2, 3];             // accesses buf[11]
}
```

Run under ASan in our tests, this reports stack-buffer-overflow; libc++'s debug hardening mode reports nothing, because `(2, 3)` really is a valid multidimensional index in a 3×4 shape.

!!! pitfall "If the offset is inside the buffer, everything is fine"
    Conversely, on a 3×4 row-major `mdspan`, `m[0, 4]` computes offset 4, which is inside the buffer, so ASan sees no problem. But `(0, 4)` is not a multidimensional index, violating the hardened precondition of `operator[]`. Checking indices dimension by dimension, instead of just the final offset, is exactly what catches this kind of mistake.

```cpp run title="mdspan-hardening.cpp" flags="-std=c++2c -D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_DEBUG"
#include <cstdio>
#include <mdspan>

int main() {
  int buf[12]{};
  std::mdspan<int, std::dims<2>> m(buf, 3, 4);
  std::printf("%d\n", m[0, 4]);   // offset 4 is inside buf, but (0, 4) is out of bounds
}
```

libc++'s debug mode in our tests reports `mdspan: operator[] out of bounds access` and terminates, and fast mode terminates with a trap instruction; without hardening the program prints 0, which is {{ub}} with no warning at all.

!!! pitfall "`m[i][j]` is the same as `m[i, j]`"
    `mdspan` has no single-argument `operator[]` returning a subview (at rank 1, `m[i]` returns the element directly), so subscripts cannot be chained. Take care too when adding `operator[]` to your own multidimensional containers: C++20 parses `a[i, j]` as the comma expression `a[(i, j)]` (deprecated), and only from C++23 is it an `operator[]` with two arguments, so the same line of code means different things in different language modes.

!!! pitfall "`layout_stride` can express broadcasting or reversal"
    [[mdspan.layout.stride.cons#4]] requires every stride to be greater than 0 and the mapping to be unique. Broadcasting with stride 0 and reversal with negative strides both need custom layout mappings.

## History

| Version | Change |
|---|---|
| C++23 | `mdspan`, `extents`, `dextents`, `layout_left`/`right`/`stride`, `default_accessor` ([[P0009R18]]); the accompanying multi-argument subscript operator ([[P2128R6]]) |
| C++26 | `submdspan` ([[P2630R4]]); `layout_left_padded`/`layout_right_padded` ([[P2642R6]]); `aligned_accessor` ([[P2897R7]]); `dims`; `mdspan::at`; deducing static extents via integral constant wrappers; the index check of `operator[]` and the length check of the converting constructor become hardened preconditions |
| Later revisions | Slice types changed to `extent_slice`/`range_slice`, canonicalization split into `canonical_slices`/`subextents`; multidimensional `copy`/`fill` added after C++26 |

## Questions

!!! question "Question 1"
    Why can't `layout_left::mapping<extents<int, 3, 4>>` and `layout_right::mapping<extents<int, 3, 4>>` be converted into each other, while those of `extents<int, 4>` can? If you really need to treat a row-major matrix as column-major, what should you do?

<details markdown="1">
<summary>Answer</summary>

Conversions between mappings must guarantee that the same index yields the same offset. With rank ≤ 1, both layouts are `m(i) = i`, so [[mdspan.layout.left.cons#6]] allows the conversion only when `rank() <= 1`. With rank 2, `(i, j)` has different offsets under the two layouts, and a conversion would see different elements, so none is provided.

To treat a row-major `R × C` matrix as column-major, construct a new view with the extents swapped: `mdspan<T, extents<int, C, R>, layout_left>(ptr)`, which is exactly the transpose of the original matrix (see `mdspan-views.cpp` above).
</details>

!!! question "Question 2"
    Why can neither `mdspan<int, extents<int, 3>>` nor `mdspan<int, extents<int, 0>>` be default constructed?

<details markdown="1">
<summary>Answer</summary>

The constraint of [[mdspan.mdspan.cons#1]] is `rank_dynamic() > 0`, and both have 0. For `extents<int, 3>`, the reason is the precondition of ¶2: `[0, 3)` cannot be an accessible range of a null pointer. For `extents<int, 0>`, `required_span_size()` is 0 and the precondition could in fact be met, but the constraint does not distinguish whether some dimension happens to be 0; it uniformly excludes the all-static case. Constraints are checked at compile time, and the simpler the rule, the less room for implementations to diverge.
</details>

!!! question "Question 3"
    For an `mdspan` using `aligned_accessor<float, 64>`, what is the accessor type of `submdspan(m, std::full_extent)`? Why doesn't the standard let it stay `aligned_accessor`?

<details markdown="1">
<summary>Answer</summary>

The accessor of the result is `AccessorPolicy::offset_policy` ([[mdspan.sub.sub#7]]), and the `offset_policy` of `aligned_accessor` is `default_accessor<float>`. Even if this particular slice happens to have offset 0, the type cannot know that at compile time; in general the offset is a run-time value, and `p + offset` is no longer guaranteed to be 64-byte aligned. When the caller can confirm the alignment, it can check with `is_sufficiently_aligned<64>` first and then explicitly construct an `aligned_accessor` again, the same way as in `aligned-accessor.cpp` above.
</details>

<details class="fine" markdown="1"><summary>Remaining wording</summary>

[[mdspan.syn]]: `<mdspan>` is marked mostly freestanding, so freestanding implementations must also provide most of it. `mdspan` is partially freestanding: the throwing `at` is marked freestanding-deleted.

[[mdspan.extents.expo]] defines several exposition-only helpers: *dynamic-index*`(i)` is the number of dynamic extents among the first i dimensions, used to find where the value of dimension r is stored; *dynamic-index-inv* is its inverse; *fwd-prod-of-extents*`(i)` is the product of the lengths of the first i dimensions, i.e. the stride of `layout_left`; *rev-prod-of-extents*`(i)` is the product of the lengths of the dimensions after i, i.e. the stride of `layout_right`; *index-cast* returns integers unchanged and `static_cast`s other types to `index_type`.

[[mdspan.layout.general]] introduces the notation used in the requirements (`M`, `m`, `i`, `j`, `r`, and the integer pack `dr` that is 1 at position r and 0 elsewhere), and defines *LEAST-MULTIPLE-AT-LEAST*`(x, y)`: `y` if `x` is 0, otherwise the least multiple of `x` not less than `y`. The padded layouts use it to compute the stride.

[[mdspan.layout.stride.expo]] defines *REQUIRED-SPAN-SIZE* (1 for rank 0, 0 if the size is 0, otherwise `1 + Σ (extent(r) − 1) * stride(r)`), *OFFSET* (the offset of the all-zero index) and the exposition-only concept *layout-mapping-alike*. The `operator==` of `layout_stride` can compare against any always-strided mapping: equal shapes, *OFFSET* 0, and equal strides in every dimension ([[mdspan.layout.stride.obs#9]]).

[[mdspan.sub.map.sliceable]] specifies the requirements on sliceable mappings: for valid slices, the shape of the resulting mapping equals `subextents(...)`, and the offset of every index in the result plus `offset` equals the original mapping's value at the corresponding original index; a call with non-canonical slice types must be ill-formed. [[mdspan.sub.map.common#8]] specifies that the starting offset is the mapping's value at the lower bounds of all slices; when some dimension's lower bound equals that dimension's length (an empty slice), `required_span_size()` is used instead, to avoid evaluating at an out-of-bounds index.

The helper defined in ¶7–¶10 of [[mdspan.sub.helpers]] is called *canonical-range-slice*, but ¶12 calls it as *canonical-slice-range*. The two are obviously the same function; this is an editorial inconsistency that does not affect the semantics.

</details>
