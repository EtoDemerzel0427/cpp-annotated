---
title: "Data-parallel types: std::simd"
summary: "C++26's <simd> provides two value types, vec and mask, in which one object represents a group of elements operated on together; implicit broadcast from scalar to vector accepts only value-preserving conversions; subscripting returns by value; element-wise operations keep the core language's UB; loads and stores come in unchecked and partial flavors; and the association order of floating-point reductions is unspecified."
updated: 2026-10-19
---

!!! tldr
    - `std::simd::vec<float>` is a group of `float`s whose number of elements (the width) is fixed at compile time, usually as many as fit in one vector register; `a + b` adds element by element.
    - A scalar broadcasts implicitly only when the conversion is value-preserving: `vec<float>` times `2.0f` works, times `2` or `2.0` does not compile.
    - `v[i]` returns by value, so you cannot assign to a single element; `a < b` returns a `mask`, which cannot go directly into an `if`; write `all_of` or `any_of`.
    - Element-wise operations evaluate the corresponding scalar expression for each element, so integer division by zero and signed overflow are still UB.
    - The default width varies with compiler options; when passing across translation units, state the width explicitly, as in `vec<float, 8>`.

!!! warning "Implementation status"
    Clang 23 + libc++ in our tests has no `<simd>` header. The examples on this page are written against the current draft and have not been compiled, so they carry no verdict markers. The existing TS version, `<experimental/simd>`, differs in both names and interface and cannot be compared directly.

## An example

```cpp title="simd-saxpy.cpp"
#include <cstddef>
#include <simd>
#include <span>
namespace ss = std::simd;

// y = a·x + y
void saxpy(float a, std::span<const float> x,
           std::span<float> y) {
  using V = ss::vec<float>;
  std::size_t i = 0;
  for (; i + V::size() <= x.size(); i += V::size()) {
    V vx = ss::unchecked_load<V>(x.subspan(i, V::size()));
    V vy = ss::unchecked_load<V>(y.subspan(i, V::size()));
    ss::unchecked_store(a * vx + vy, y.subspan(i, V::size()));
  }
  // a tail shorter than one vector: missing elements read as 0, only the remaining elements are written back
  V vx = ss::partial_load<V>(x.subspan(i));
  V vy = ss::partial_load<V>(y.subspan(i));
  ss::partial_store(a * vx + vy, y.subspan(i));
}
```

SIMD (single instruction, multiple data) means one instruction processes several data items at once. When relying on the compiler's auto-vectorization, whether a loop gets vectorized depends on whether the optimizer can prove it safe; `std::simd` writes "process this as vectors" into the type. Each operation in `a * vx + vy` is element-wise, and the compiler translates it into vector instructions.

The library derives from `std::experimental::simd` in version 2 of the Parallelism Technical Specification and was merged into C++26 {{c++26}} by [[P1928R15]]. Later in the C++26 cycle the types were renamed `basic_vec`, `vec`, `basic_mask` and `mask`, placed in namespace `std::simd`, and features such as complex elements, permute and gather/scatter were added.

## Basic notions ([simd.general])

¶2 The vectorizable types ([[g:vectorizable-type]]) are: all standard integer types, the character types, `float` and `double`; `std::float16_t`, `float32_t` and `float64_t` if the implementation defines them; and `complex<T>` where `T` is a vectorizable floating-point type. Neither `bool` nor `long double` is vectorizable (`bool` is not a standard integer type).

¶3–¶5 Specializations of `basic_vec` and `basic_mask` are either enabled or disabled, and the enabled ones are collectively called data-parallel types ([[g:data-parallel-type]]). A data-parallel type consists of some number of elements; the type of the elements is called the element type and their number the width, with indices from 0 to width − 1.

¶6 An element-wise operation applies some operation to the elements of one or more data-parallel objects one by one, with the applications unsequenced relative to each other.

¶7 For a mask `mask`, the indices i for which `mask[i]` is true are called the selected indices, and the corresponding elements the selected elements.

¶8 A conversion from an arithmetic type U to a vectorizable type T is value-preserving ([[g:value-preserving-conversion]]) if every value of U can be represented in T.

¶9 A program that explicitly or partially specializes any template in [simd] is ill-formed, no diagnostic required ({{ifndr}}).

## Width and ABI tags ([simd.expos.abi])

¶1 An ABI tag ([[g:simd-abi-tag]]) is a type indicating the size and binary representation of data-parallel objects. Together with the element type it determines the width. ¶2 Note 2 points out that the ABI tag is distinct from the selected instruction set; its role is to make data-parallel objects safe to pass across translation units (function calls, I/O).

Two exposition-only aliases determine the commonly used ABI tags:

- ¶4–¶5 *deduce-abi-t*<T, N>: when T is vectorizable and 0 < N ≤ some implementation-defined limit (no less than 64), it is the ABI tag that makes the width exactly N.
- ¶6 *native-abi*<T>: an implementation-defined tag that is the most efficient for the current target. Note 3 says that on targets with instruction set extensions, compiler options can change it.

So the size and layout of `vec<float>` (which uses *native-abi* by default) may change with compiler options. On x86-64, for instance, it may have 8 elements with AVX enabled and 4 otherwise. Two translation units compiled with different `-m` options exchanging `vec<float>` can easily disagree about the type's layout; use an explicit width such as `vec<float, 8>` across such boundaries.

## The main names ([simd.syn])

```cpp
template<class T, class Abi = native-abi<T>> class basic_vec;
template<class T, simd-size-type N = simd-size-v<T, native-abi<T>>>
  using vec = basic_vec<T, deduce-abi-t<T, N>>;
template<size_t Bytes, class Abi> class basic_mask;
template<class T, simd-size-type N = simd-size-v<T, native-abi<T>>>
  using mask = vec<T, N>::mask_type;
```

*simd-size-type* is a signed integer type used for both widths and indices ([simd.expos.defn]).

`basic_mask` is parameterized by the element size in bytes rather than the element type: `vec<float>` and `vec<int>` of the same width share the same mask type, so a mask obtained by comparing `float`s can be used directly to select `int` elements.

Namespace `std` brings in `min`, `max`, `minmax`, `clamp` and the mathematical functions from `std::simd` with using-declarations, so `std::sin(v)` works too.

[simd.traits] provides `alignment<T, U>::value` (the alignment needed when loading and storing with `flag_aligned`), `rebind_t<T, V>` (change the element type, keep the width) and `resize_t<N, V>` (change the width, keep the element type).

## basic_vec ([simd.class])

### Enabled and disabled ([simd.overview])

¶1 `basic_vec<T, Abi>` is enabled when T is vectorizable and Abi is *deduce-abi-t*<T, N> for some N ∈ [1, 64]; it is disabled when T is not vectorizable; otherwise, whether it is enabled is implementation-defined.

A disabled specialization has its default constructor, destructor, copy constructor and copy assignment deleted, and has only the three members `value_type`, `abi_type` and `mask_type`, so declaring a variable of it is a compile error.

Enabled specializations (¶1.4–¶1.8) are trivially copyable; default-initialization default-initializes each element (indeterminate values for `int`), and value-initialization value-initializes each element.

`size` is a `static constexpr integral_constant` data member, not a member function. `integral_constant` has an `operator()`, so `V::size()` still works, and the result is a constant expression.

### Broadcast construction accepts only value-preserving conversions ([simd.ctor] ¶1–¶3)

```cpp title="simd-broadcast.cpp"
#include <simd>
namespace ss = std::simd;

void f(ss::vec<float> v) {
  auto a = v * 2.0f;        // OK: float → float is value-preserving
  auto b = v * std::cw<2>;  // OK: the compile-time constant 2 is representable as float
  auto c = v * 2;           // error: int → float is not value-preserving
  auto d = v * 2.0;         // error: double → float is not value-preserving
}
```

The broadcast constructor `template<class U> constexpr basic_vec(U&& value) noexcept` copies a scalar into every element. It is not `explicit`, so the `2.0f` in `v * 2.0f` can be implicitly converted to `vec<float>`. But the constraints in ¶2 are strict: one of the following three must hold, with From being `remove_cvref_t<U>`:

- ¶2.1 U is convertible to `value_type`, and From is neither an arithmetic type nor satisfies *constexpr-wrapper-like*;
- ¶2.2 From is an arithmetic type, and the conversion from From to `value_type` is value-preserving;
- ¶2.3 From satisfies *constexpr-wrapper-like* (for example `std::cw<2>`, see [[const.wrap.class]]), its value has arithmetic type, and that value is representable in `value_type`.

`int` to `float` is not value-preserving, since not every `int` can be represented exactly as `float`, so `v * 2` does not compile. In scalar code, `x * 2` silently converting `int` to `float` is usually harmless; in SIMD code, an implicit integer-to-float or wide-to-narrow conversion often means lost precision or extra conversion instructions, and `std::simd` requires you to write them out.

### Other constructors

- Converting construction (¶4–¶6): `static_cast` element by element from another `basic_vec` of the same width. If the conversion is not value-preserving, or is an integer or floating-point rank reduction ([[conv.rank]]), this constructor is `explicit`.
- Generator construction (¶7–¶10): the i-th element is initialized with `gen(integral_constant<simd-size-type, i>())`. The index is passed as a compile-time constant, so the generator can use `if constexpr`. ¶10 specifies that `gen` is called exactly once for each i, in increasing order of i.
- Range construction (¶11–¶15): requires `r` to be a contiguous, sized range with `ranges::size(r)` a constant expression equal to `size()`. So only ranges with a statically known size, such as `std::array` and `span<T, N>`, can be used. The deduction guides in ¶16–¶17 make `basic_vec(std::array<float, 8>{…})` deduce `vec<float, 8>`.
- Complex construction (¶20–¶21): when the elements are `complex`, construction from a vector of real parts and a vector of imaginary parts.

### Subscripting returns by value ([simd.subscr])

¶1–¶3 `value_type operator[](simd-size-type i) const` has the precondition 0 ≤ i < `size()` and returns the value of the i-th element. It returns a value, not a reference, and there is no non-const version, so `v[0] = 1.0f;` does not compile.

A single element in a register has no address, and returning by reference would force the implementation to keep the whole vector in memory. To modify a single element, use `select`, generator construction, or a mask operation.

¶4 `operator[](const I& indices)` (with `I` an integer `vec`) is equivalent to `permute(*this, indices)`.

### Iterators ([simd.iterator])

`begin()` returns the exposition-only *simd-iterator*, and `end()` returns `default_sentinel`. The iterator's `operator*` returns by value. Its `iterator_concept` is `random_access_iterator_tag`, but its `iterator_category` is `input_iterator_tag`, because a C++17-style forward iterator requires `*it` to return a reference. It can be used with range `for` and with read-only algorithms.

## Element-wise operations ([simd.unary], [simd.nonmembers])

Unary operations (`++`, `--`, `!`, `~`, `+`, `-`), binary operations (`+ - * / % & | ^ << >>`), compound assignments and comparisons all follow the same pattern:

- *Constraints*: the corresponding scalar expression is valid; for example, a binary operation requires `requires (value_type a, value_type b) { a op b; }`;
- the result applies the operation to each element; comparisons return `mask_type`, and so does `!`.

The binary operations are `noexcept` hidden friends taking `const basic_vec&`, found only via argument-dependent lookup. Precisely because the parameters are `basic_vec` itself, scalar operands are converted through the broadcast constructor above. Shifts also have overloads of the form `v << n` (with n a *simd-size-type* scalar), shifting all elements by the same amount.

!!! lawyer "Element-wise operations inherit the core language's UB"
    [simd.binary] ¶3 says the result "is initialized with the results of applying op to lhs and rhs element-wise", that is, the scalar expression `a op b` is evaluated for each element. So the core language rules apply element by element: some element of a `vec<int>` divided by zero, signed overflow, or a shift count not less than the bit width are all UB ([[expr.pre#4]], [[expr.mul]], [[expr.shift]]), even though the hardware's vector instructions have defined behavior for these cases.

    Conversely, `a + b` on `vec<std::int8_t>` has no UB: the scalar expression is computed as `int` after integral promotion, and the result initializes an `int8_t` element, a conversion defined modulo 2⁸ ([[conv.integral]]).

### select

`select(c, a, b)` in [simd.alg] ¶9–¶10 is the SIMD version of the conditional operator:

- when `c` is a `bool`, it is equivalent to `c ? a : b`;
- when `c` is a mask, the i-th element of the result is `c[i] ? a[i] : b[i]`, implemented by calling the exposition-only *simd-select-impl* ([simd.cond]). ¶10 specifically says it is found via argument-dependent lookup, noting that this is contrary to the general rule of [[contents]].

## Loads and stores ([simd.loadstore], [simd.flags])

There are two sets of functions for moving data between memory and vectors:

| | When the range is shorter than `V::size()` |
|---|---|
| `unchecked_load` / `unchecked_store` | the precondition in ¶3 requires `ranges::size(r) ≥ V::size()`, and a shortfall is UB; if the length is a constant expression, ¶2 makes it a *Mandates*, and a shortfall is a compile error |
| `partial_load` / `partial_store` | read or write only the first `ranges::size(r)` elements; when loading, the other elements are `T()`; when storing, the other positions are not written |

Both have masked overloads (processing only the selected elements), and both accept three forms: a range, an iterator plus count, and an iterator plus sentinel. The main loop of the example at the top uses `unchecked_*` because the length is known to be sufficient; the tail shorter than one vector uses `partial_*`, at the cost of a few more comparisons.

`flags<…>` in [simd.flags] is a set of type-level options combined with `|`:

- `flag_default`: no extra assumptions;
- `flag_convert`: allows non-value-preserving element type conversions, such as loading from a `double` array into `vec<float>`. Without it, a non-value-preserving conversion violates *Mandates*;
- `flag_aligned`: asserts that the pointer is aligned to `alignment_v<V, U>`; this is a precondition, and misalignment is UB;
- `flag_overaligned<N>`: asserts alignment to N, which must be a power of 2.

The gather/scatter functions in [simd.permute.memory] access memory through an index vector: `unchecked_gather_from(r, indices)` and `partial_gather_from` gather elements from a range, and `unchecked_scatter_to` and `partial_scatter_to` scatter them back. The `partial_*` versions neither read nor write the elements corresponding to out-of-range indices.

## Reductions ([simd.reductions], [simd.mask.reductions])

`reduce(x, op = plus<>{})` reduces all elements to a single value:

- ¶1 `op` must model *reduction-binary-operation*: callable on `vec<T, 1>`, and (per [simd.expos.defn] ¶8) a commutative element-wise operation;
- ¶3 the result is a *GENERALIZED_SUM* ([[numerics.defns]], [[g:generalized-sum]]), with elements associated in an unspecified way. So floating-point reductions are not guaranteed to equal sequential accumulation, nor to match across implementations or widths.

The masked `reduce(x, mask, op, identity)` reduces only the selected elements and returns `identity` if none are selected. ¶5 `identity` has a default when `op` is `plus<>`, `multiplies<>` or a bitwise operation; for other operations it must be given explicitly. `reduce_min` and `reduce_max` require `T` to model `totally_ordered`.

Reductions on masks are `all_of`, `any_of`, `none_of`, `reduce_count`, and `reduce_min_index` and `reduce_max_index` (returning the smallest and largest index that is true). The last two have the precondition `any_of(k)`; calling them when all elements are false is UB.

All these functions have overloads accepting `bool` or scalars, so the same generic code works for both scalars and vectors.

## Permutation, composition and mathematical functions

- Static permute ([simd.permute.static]): `permute(v, idxmap)`, where `idxmap(i)` must be a constant expression giving which source element the i-th result element comes from; it may also return `zero_element` (set to zero) or `uninit_element` (unspecified value). The result width may differ from the source.
- Dynamic permute ([simd.permute.dynamic]): `permute(v, indices)`, with indices given by a run-time integer vector.
- compress / expand ([simd.permute.mask]): move the selected elements compactly to the front, or spread them out again; these correspond to the AVX-512 instructions of the same names.
- chunk / cat ([simd.creation]): split a wide vector into several narrower ones, or concatenate several vectors.
- `iota<V>`: a constant whose elements are 0, 1, 2, ….

[simd.math] provides overloads of almost all `<cmath>` functions ([[c.math]]) for floating-point `vec`s, with return types deduced by *deduced-vec-t*, so `vec`s can be mixed with types implicitly convertible to them. [simd.bit] provides `popcount`, `countl_zero`, `rotl`, `byteswap` and others from `<bit>` ([[bit]]) for unsigned integer `vec`s. [simd.complex.math] provides `real`, `imag`, `abs`, `arg`, `norm`, `conj`, `proj`, `polar` and the transcendental functions for complex elements.

## basic_mask ([simd.mask.class])

```cpp title="simd-mask.cpp"
#include <simd>
namespace ss = std::simd;

bool all_less(ss::vec<float> a, ss::vec<float> b) {
  // if (a < b) ...           // error: a mask cannot convert to bool
  return ss::all_of(a < b);   // or any_of(a < b)
}
```

`a < b` returns a group of comparison results. Converting it to a single `bool` has two reasonable meanings, all true or any true, and the standard does not choose for you, so `basic_mask` has no conversion to `bool`.

- The enabling rule ([simd.mask.overview] ¶1) is like that of `basic_vec`, but by byte size: it can be enabled only if some vectorizable type has `sizeof` equal to Bytes. Enabled specializations are trivially copyable.
- Construction ([simd.mask.ctor]): broadcast from `bool` (`explicit`, and the argument must be exactly `bool`); explicit conversion from another mask of the same width; generator construction (the generator must return `bool`); construction from `bitset<size()>`; explicit construction from an unsigned integer (taking the first M elements bit by bit, the rest false).
- Subscripting likewise returns `bool` by value.
- Unary operations ([simd.mask.unary]): `!` returns a mask. `+`, `-` and `~` apply the operation to each element's `bool` value and return a `vec` whose element type is *integer-from*<Bytes> (the signed integer of size Bytes); for example, in `-m` the true elements are −1. If there is no vectorizable signed integer type of that size, these three operators are deleted.
- Conversions ([simd.mask.conv]): convertible to `basic_vec<U, A>` of the same width (`explicit` when `sizeof(U)` is not Bytes), plus `to_bitset()` and `to_ullong()`. The precondition of `to_ullong()` is that the elements beyond the number of bits in `unsigned long long` are all false.
- The binary `&&`, `||`, `&`, `|`, `^` and their compound assignments are all element-wise. `&&` and `||` do not short-circuit either, since both operands are already evaluated before the call. The six comparison operators are likewise element-wise and return masks.
