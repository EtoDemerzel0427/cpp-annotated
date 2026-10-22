---
title: Basic linear algebra algorithms
summary: "C++26's <linalg> represents vectors and matrices as mdspan and provides BLAS level 1/2/3 algorithms; transposition, conjugation and scaling are expressed through views that copy no data; static size mismatches are compile errors and dynamic ones are UB; floating-point results are not guaranteed to match a naive loop bit for bit."
updated: 2026-10-19
---

!!! tldr
    - `<linalg>` {{c++26}} is a C++ interface to BLAS: vectors and matrices are `mdspan`s, the element type is a template parameter, and algorithms can take an execution policy.
    - The `trans` and `alpha` parameters of BLAS become views such as `transposed(A)` and `scaled(alpha, x)`, which only change the layout or accessor and copy no data.
    - Multiplying two matrices whose static sizes do not match is a compile error (*Mandates*); a run-time size mismatch is UB (*Preconditions*).
    - Output parameters must not overlap other parameters unless the function explicitly allows aliasing (for example, in `C = E + A·B`, C may be E itself).
    - For floating-point types, implementations may reorder sums and use algorithms such as Strassen's, so results are not guaranteed to match a naive loop or another implementation bit for bit.

!!! warning "Implementation status"
    Clang 23 + libc++ in our tests has no `<linalg>` header, and `__cpp_lib_linalg` is commented out in libc++'s `<version>`. The examples on this page are written against the current draft and have not been compiled, so they carry no verdict markers.

## An example

```cpp title="linalg-views.cpp"
#include <linalg>
#include <mdspan>

namespace la = std::linalg;
using Mat = std::mdspan<double, std::dextents<int, 2>>;
using CMat = std::mdspan<const double, std::dextents<int, 2>>;

// C = 2·Aᵀ·B: no copy of A, and no trans or alpha parameters
void f(CMat A, CMat B, Mat C) {
  la::matrix_product(la::scaled(2.0, la::transposed(A)), B, C);
}
```

Traditional BLAS matrix multiplication is `xGEMM(transA, transB, alpha, A, B, beta, C)`: transposition and scaling are extra parameters. `<linalg>` ([[P1673R13]]) removes these parameters and turns them into transformations of the input `mdspan`s. Its aim is not to replace vendor-optimized BLAS libraries but to provide a type-safe generic front end: an implementation can forward to vendor BLAS for `double` with common layouts and use generic code otherwise.

An `mdspan` ([[views.multidim]]) has three parts: extents (the length of each dimension, either a compile-time constant or a run-time value), a layout mapping ([[g:layout-mapping]], mapping multidimensional indices to a one-dimensional offset), and an accessor policy ([[g:accessor-policy]], deciding how an element is obtained from an offset).

## Three views that copy no data

### scaled ([linalg.scaled])

`scaled(alpha, x)` returns a read-only `mdspan` whose i-th element reads as `alpha * x[i]`. It is implemented with a new accessor `scaled_accessor<ScalingFactor, NestedAccessor>` ([linalg.scaled.scaledaccessor]):

- ¶6 `access(p, i)` returns `scaling_factor() * NestedAccessor::element_type(nested_accessor().access(p, i))`;
- `reference` is the product type with `const` removed, that is, returned by value, so the result is not writable;
- ¶2 *Mandates*: the product type is valid, copy constructible and not a reference; `ScalingFactor` models `semiregular`; `NestedAccessor` meets the accessor requirements ([[mdspan.accessor.reqmts]]).

The order of multiplication is always `alpha * x`. As we will see below, multiplication of the element type is not necessarily commutative, so the order matters.

### conjugated ([linalg.conj])

`conjugated(a)` returns a read-only view whose elements are conjugated, using the accessor `conjugated_accessor`. [linalg.conj.conjugated] ¶1 specifies that the accessor of the return value is determined in this order:

- ¶1.1 if `a`'s accessor is already a `conjugated_accessor`, that layer is stripped, since conjugating twice gives the original;
- ¶1.2 otherwise, if the element type is an arithmetic type (real), `a`'s accessor is used as is;
- ¶1.3 otherwise, if a usable unqualified `conj` can be found for the elements, a `conjugated_accessor` layer is added;
- ¶1.4 otherwise it is used as is.

### transposed ([linalg.transp])

`transposed(a)` (*Mandates*: `a` is two-dimensional) swaps the two extents and chooses the returned layout per [linalg.transp.transposed] ¶3:

| Original layout | Layout after transposition |
|---|---|
| `layout_left` / `layout_right` | `layout_right` / `layout_left` |
| `layout_left_padded<P>` / `layout_right_padded<P>` | `layout_right_padded<P>` / `layout_left_padded<P>` |
| `layout_stride` | `layout_stride` (the two strides swapped) |
| `layout_blas_packed<upper, column-major>` | `layout_blas_packed<lower, row-major>` (and vice versa) |
| `layout_transpose<L>` | `L` |
| any other layout `L` | `layout_transpose<L>` |

For common layouts, the result of transposition is still a common layout, which implementations can recognize and forward to BLAS.

`conjugate_transposed(a)` ([linalg.conjtransposed] ¶2) is equivalent to `conjugated(transposed(a))`.

## Conventions for reading the algorithm specifications ([linalg.general])

¶1 When *Effects* says "computes R = E", E has its usual mathematical meaning, with xᵀ denoting the transpose and xᴴ the conjugate transpose. If R is a parameter with `Out` in its name, the result is written into its elements.

¶2–¶3 Row i of a matrix A is all A[i, k], and column j is all A[k, j]. The diagonal is A[i, i]; the upper triangle is the elements with i ≤ j and the lower triangle those with i ≥ j, both including the diagonal.

¶4 A function with a triangle tag parameter `t` accesses only the triangle specified by `t` of the parameter m immediately preceding `t`. When accessing m[i, j] outside that triangle:

- ¶4.1 functions whose names begin with `hermitian` use *conj-if-needed*(m[j, i]);
- ¶4.2 those beginning with `symmetric` use m[j, i];
- ¶4.3 those beginning with `triangular` use the additive identity (zero).

`hermitian` functions also take the real part of diagonal elements. Example 1 in the standard points out that non-zero values in the triangle that is not accessed do not violate a precondition.

¶5 For a function with a diagonal tag parameter `d`, if `d` specifies an implicit unit diagonal, the diagonal of m is not accessed and the diagonal elements are treated as the multiplicative identity, even if the element type itself has no multiplicative identity.

¶6 Calls to `abs`, `conj`, `imag` and `real` inside the algorithms are unqualified, so they find versions for user types via argument-dependent lookup.

¶7–¶8 Two `mdspan`s alias if their extents are the same and each index refers to the same element. Two `mdspan`s overlap ([[g:mdspan-overlap]]) if some pair of indices refers to the same element. Aliasing is a special case of overlap.

## Tag types ([linalg.tags])

Six empty tag types, each with an `inline constexpr` instance. Their default constructors are all `explicit`, to keep `{}` from accidentally being taken as a tag:

| Tag | Purpose |
|---|---|
| `column_major_t` / `row_major_t` | storage order of `layout_blas_packed` |
| `upper_triangle_t` / `lower_triangle_t` | which triangle is accessed |
| `implicit_unit_diagonal_t` / `explicit_diagonal_t` | whether the diagonal is accessed |

[linalg.algs.reqs] ¶1 constrains template parameters by name: one named `ExecutionPolicy` must be an execution policy, and overloads taking it are parallel algorithms ([[algorithms.parallel]]); `Real` must be a type for which `complex<Real>` can be instantiated; `Triangle` must be one of the two triangle tags; `DiagonalStorage` must be one of the two diagonal tags.

## Packed storage: layout_blas_packed ([linalg.layout.packed])

¶1–¶4 `layout_blas_packed<Triangle, StorageOrder>` is an `mdspan` layout mapping policy. It represents a square matrix storing only one triangle, with elements packed tightly, corresponding to the BLAS SP, HP and TP formats. `StorageOrder` decides whether it packs by column or by row. A 5×5 packed matrix stores only 15 elements.

¶5 *Mandates*: the two template arguments are a triangle tag and an order tag respectively; `Extents` is two-dimensional; at least one of the two static extents is dynamic, or the two are equal; when both are static, N(N+1) is representable in `index_type`. ¶6 The mapping type is trivially copyable and models `regular`.

This mapping is not unique: A[i, j] and A[j, i] map to the same storage location. So `is_always_unique()` is true only when the static extent is less than 2. This limits where it can be used: ordinary output parameters require `is_always_unique()`, so a packed matrix can only be the output of functions such as `symmetric_matrix_rank_1_update` that write only one triangle.

## Requirements on element types ([linalg.reqs])

### Linear algebra value types ([linalg.reqs.val])

¶1 The `value_type` of input and output `mdspan`s, and the template parameter `Scalar`, are called linear algebra value types ([[g:linear-algebra-value-type]]). ¶2 They must model the exposition-only concept *scalar*: satisfy `semiregular`, and be neither an `mdspan` nor an execution policy. ¶3 A value-initialized object must act as the additive identity.

### How algorithms may compute ([linalg.reqs.alg])

¶2 specifies, in the language of abstract algebra, what implementations may do:

- ¶2.1 Functions may create any number of objects of linear algebra value types, value-initialized or direct-initialized from existing objects.
- ¶2.2 The triangular solve algorithms (`trsv`, `trmm`, `trsm` and in-place `trsm`) have a `divide` parameter, or behave as if they had one. `divide(a, b)` is interpreted as a times the multiplicative inverse of b. They use only `*`, `*=`, `divide`, unary and binary `+ -`, `+=`, `-=` and `=`, and the sequence of operations gives the specified result even over a field whose multiplication is not commutative.
- ¶2.3 The other BLAS 1/2/3 functions use only `*`, `*=`, `+`, `+=` and `=`, and the sequence of operations gives the specified result even over a semiring whose multiplication is not commutative.
- ¶2.4 When there is an output `mdspan`, all terms and so on must be assignable to, and convertible to, the output's `value_type`.
- ¶2.5 Functions may reorder terms and partial sums arbitrarily. Note 1 stresses that the order of factors is not reordered, because multiplication is not necessarily commutative.

¶2.2 and ¶2.3 also list some requirements as preconditions: all terms, partial sums, factors, partial products preserving the order of factors, and assignments must be well-formed expressions.

Requiring only a semiring means element types can be matrix blocks, quaternions, intervals, or dual numbers for automatic differentiation, as long as they have `+` and `*` satisfying associativity and distributivity.

¶3 Note 3 greatly relaxes things for floating-point types: when all `value_type`s and `Scalar` are floating-point types, implementations may sum in any way that improves accuracy, may perform extra operations to improve performance or accuracy, and may use approximation algorithms, provided the complexity requirements are met and they are logarithmically stable (citing Demmel 2007). The note explicitly lists Strassen matrix multiplication as a permitted example.

So floating-point results of `<linalg>` are not guaranteed to match a naive loop bit for bit, nor to match bit for bit across implementations or execution policies.

## Helper rules ([linalg.helpers])

### How user types plug into abs and conj

Four exposition-only function objects decide how algorithms take the absolute value, conjugate, real part and imaginary part of elements:

- *abs-if-needed*(E): for unsigned integers, returns E directly; for other arithmetic types, `std::abs(E)`; otherwise the unqualified `abs(E)`, with lookup shielding the generic versions in `std`, so in effect it relies only on argument-dependent lookup to find the user's function.
- *conj-if-needed*, *real-if-needed*: for non-arithmetic types, call the unqualified version if one can be found, otherwise return E itself.
- *imag-if-needed*: likewise, but returns `T{}` when none is found, since the imaginary part of a real number is zero.

Each comes with the sentence: if the function selected by overload resolution does not return the absolute value (or conjugate, real part, imaginary part), the program is ill-formed, no diagnostic required ({{ifndr}}): the compiler need not report an error, and the program has no guarantees. This is the contract for user types plugging into `<linalg>`: the `abs` you provide must really be an absolute value.

### Parameter concepts ([linalg.helpers.concepts])

¶1 Algorithm signatures use a set of exposition-only concepts: *in-vector*, *in-matrix* and *in-object* are one-dimensional, two-dimensional, and one- or two-dimensional `mdspan`s respectively. The corresponding *out-* and *inout-* versions additionally require assignability through `reference` and `is_always_unique()` being true. *possibly-packed-out-matrix* relaxes the uniqueness requirement, allowing `layout_blas_packed`.

¶2 Accesses through *in-* parameters do not modify elements.

¶3 Unless explicitly permitted, no *out-* or *inout-* parameter may overlap any other `mdspan` parameter of the function. This is a precondition, and violating it is UB. The permitted exceptions are written in each function's *Remarks*, for example "z may alias x or y" for `add`, and "C may alias E" for `matrix_product(A, B, E, C)`. Note that what is permitted is aliasing (an identical view), not arbitrary overlap.

### Size checks: Mandates for static, Preconditions for dynamic

```cpp title="linalg-extents.cpp"
#include <linalg>
#include <mdspan>
using std::extents;

void f(std::mdspan<double, extents<int, 3, 4>> A,
       std::mdspan<double, extents<int, 5>> x,  // should be 4
       std::mdspan<double, extents<int, 3>> y) {
  // error: possibly-multipliable is false
  std::linalg::matrix_vector_product(A, x, y);
}
```

[linalg.helpers.mandates] defines *possibly-addable* and *possibly-multipliable*, which look only at static extents: if either side is `dynamic_extent` it passes, and if both are static values they must be equal. Algorithms use them to write *Mandates*, so in the example above multiplying a 3×4 matrix by a vector of length 5 is a compile error.

*addable* and *multipliable*, defined in [linalg.helpers.precond], check the run-time extents, and algorithms use them to write *Preconditions*. So a dynamic size mismatch is UB.

## The algorithms at a glance

[linalg.algs.blas1.complexity] specifies the complexity of BLAS 1 functions: the number of `mdspan` accesses and arithmetic operations is linear in the maximum, over all `mdspan` parameters, of the product of extents.

| Level | Function | BLAS equivalent | Key points |
|---|---|---|---|
| 1 | `setup_givens_rotation`, `apply_givens_rotation` | xLARTG, xROT | |
| 1 | `swap_elements` | xSWAP | |
| 1 | `scale(alpha, x)` | xSCAL | in place, x = αx |
| 1 | `copy(x, y)` | xCOPY | |
| 1 | `add(x, y, z)` | xAXPY | z = x + y; αx + y is written `add(scaled(alpha, x), y, z)`; z may alias x or y |
| 1 | `dot`, `dotc` | xDOT, xDOTU, xDOTC | `dotc(v1, v2)` is `dot(conjugated(v1), v2)` |
| 1 | `vector_two_norm` | xNRM2 | |
| 1 | `vector_abs_sum` | xASUM | |
| 1 | `vector_idx_abs_max` | IxAMAX | returns the maximum of `size_type` for an empty vector |
| 1 | `matrix_frob_norm`, `matrix_one_norm`, `matrix_inf_norm` | | matrix norms |
| 2 | `matrix_vector_product` | xGEMV | y = Ax, or z = y + Ax (z may alias y) |
| 2 | `symmetric_`, `hermitian_`, `triangular_matrix_vector_product` | xSYMV, xHEMV, xTRMV and others | read only the specified triangle |
| 2 | `triangular_matrix_vector_solve` | xTRSV, xTPSV | solves Ax = b; if there is no solution, x's elements are valid but their values unspecified |
| 2 | `matrix_rank_1_update`, `matrix_rank_1_update_c` | xGER, xGERU, xGERC | A = xyᵀ, or A = E + xyᵀ; the `_c` version uses xyᴴ |
| 2 | `symmetric_`, `hermitian_matrix_rank_1_update`, `…_rank_2_update` | xSYR, xHER, xSYR2, xHER2 | the output may be in packed layout |
| 3 | `matrix_product` | xGEMM | C = AB, or C = E + AB (C may alias E) |
| 3 | `symmetric_`, `hermitian_`, `triangular_matrix_product` | xSYMM, xHEMM, xTRMM | |
| 3 | `triangular_matrix_left_product`, `…_right_product` | xTRMM | in place |
| 3 | `symmetric_`, `hermitian_matrix_rank_k_update`, `…_rank_2k_update` | xSYRK, xHERK, xSYR2K, xHER2K | |
| 3 | `triangular_matrix_matrix_left_solve`, `…_right_solve` | xTRSM | both out-of-place and in-place versions |

In the current draft, the update functions each come in overwriting and updating overloads. For example, `matrix_rank_1_update(x, y, A)` computes A = xyᵀ, and `matrix_rank_1_update(x, y, E, A)` computes A = E + xyᵀ, where A may alias E. In BLAS a rank-1 update is always A += xyᵀ; the wording of `<linalg>` differs from that.

### The result type of dot ([linalg.algs.blas1.dot])

Without an initial value (¶9), the result type is the type of the product of the two element types, accumulating from `T{}`. With an initial value `init` (¶5–¶6), the result type is the type of `init`. ¶7 *Remarks* also specifies that if the element types and `Scalar` are all floating-point types or `complex`, and `Scalar` has greater precision, then the intermediate terms of the sum are computed with at least the precision of `Scalar`.

So `dot(v1, v2, 0.0L)` is the standard way to accumulate the dot product of `float` vectors in `long double`. The `init` of `vector_two_norm` serves the same purpose.

## Relation to valarray and simd

[[numarray]]'s `valarray` was also inspired by BLAS; `slice` is exactly BLAS-style strided access. But it binds data and operations into the same type; `<linalg>` provides only algorithms, with data borrowed through `mdspan`, so the storage is independent of the algorithm.

[[simd]] is a lower-level tool, which `<linalg>` implementations can use internally for vectorization.
