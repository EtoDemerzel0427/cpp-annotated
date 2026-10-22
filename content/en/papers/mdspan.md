---
title: mdspan (P0009)
summary: C++23's std::mdspan is a multidimensional view over a block of memory, made of three parts: shape, layout and accessor. The older idioms it replaces, the layout problem it inherited from Kokkos, why the shape is written as extents rather than an array type, why there are exactly two customization policies, why m[i, j] required a language change first, why it is not a range, and C++26's submdspan and padded layouts.
tags: mdspan, multidimensional arrays, views, layouts, accessors, multidimensional subscript, proposal, C++23
group: Library
updated: 2026-10-19
---

!!! tldr
    - Before C++23, a multidimensional array with run-time sizes could only be written as `vector<vector<T>>` (not contiguous, pointer chasing) or a pointer plus hand-written indexing (shape and strides by convention only). `std::mdspan` ([[P0009R18]]) packs the pointer, the shape and the indexing formula into a non-owning view.
    - The shape, `extents`, lets each dimension independently be a compile-time constant or a run-time value. Static dimensions take no storage, and the compiler can fold them into address computation: at `-O2`, taking the trace of a 4×4 matrix is 10 instructions, versus 82 for the fully dynamic version.
    - There are just two customization policies: the layout decides how indices become an offset, and the accessor decides how an offset becomes a reference to an element. The committee rejected a design with an arbitrary list of properties, in exchange for two allocator-like interfaces that can each be replaced.
    - `m[i, j]` depends on the language change [[P2128R6]]: an overloaded `operator[]` may take several parameters, at the cost of the comma expression `a[i, j]`, deprecated in C++20, becoming ill-formed in C++23 (Annex C).
    - `mdspan` has no iterators and is not a range. C++26 adds `submdspan` for taking subviews and padded layouts, neither of which libc++ implements yet.

## Without mdspan

For a function that handles a matrix whose size is only known at run time, C++20 has three common idioms:

```cpp title="before.cpp" run ok
#include <cstdio>
#include <vector>

// 1. built-in multidimensional array: every dimension except the first must be constant
void scale_fixed(double (*a)[4], int rows, double k) {
  for (int i = 0; i < rows; ++i)
    for (int j = 0; j < 4; ++j) a[i][j] *= k;
}

// 2. vector of vectors: each row allocated separately, access reads the row pointer first
void scale_nested(std::vector<std::vector<double>>& a, double k) {
  for (auto& row : a)
    for (double& x : row) x *= k;
}

// 3. pointer plus hand-written indexing: shape and strides by convention only
void scale_raw(double* a, int rows, int cols, int ld, double k) {
  for (int i = 0; i < rows; ++i)
    for (int j = 0; j < cols; ++j) a[i * ld + j] *= k;
}

int main() {
  double fixed[2][4] = {{1, 2, 3, 4}, {5, 6, 7, 8}};
  scale_fixed(fixed, 2, 2.0);

  std::vector<std::vector<double>> nested(2, std::vector<double>(3, 1.0));
  scale_nested(nested, 3.0);

  std::vector<double> flat(2 * 5, 1.0);   // 2 rows, 3 columns, each row takes 5 slots
  scale_raw(flat.data(), 2, 3, 5, 4.0);

  std::printf("%g %g %g %g\n", fixed[1][3], nested[1][2], flat[5], flat[8]);  // 16 3 4 1
}
```

The first hard-codes the number of columns in the type. C++ has no variable-length arrays, and `double a[rows][cols]` is ill-formed when `cols` is not a constant ([[dcl.array]]). In the second, each row is a separate allocation, so the data is not contiguous and cannot be handed as one block to numerical libraries written in C or Fortran. The third is the most common and the most fragile: the row count, column count and row stride `ld` are three loose integers, getting one wrong gives no diagnostic, and switching to column-major means changing every index expression.

The motivation section of [[P0009R18]] lists the drawbacks of each of these, and adds `valarray` with `gslice`: it can select from a one-dimensional `valarray` as if it were multidimensional data, but the result is not guaranteed to have `operator[]`, and there is no efficient way to get a single element.

The cost of accessing one element differs too. With Clang 23 (arm64) at `-O2`, `a[i][j]` on a `vector<vector<float>>` is three memory reads: the outer `vector`'s data pointer, row i's data pointer, and the element itself; `a[i * ld + j]` is one multiply-add instruction plus one read.

With `mdspan`, the pointer, shape and indexing formula become one object, and all three cases are handled by one function template:

```cpp title="after.cpp" run ok
#include <array>
#include <cstdio>
#include <mdspan>
#include <vector>

// one function accepts a 2D view of any shape and any layout
template<class T, class E, class L, class A>
void scale(std::mdspan<T, E, L, A> a, T k) {
  for (typename E::index_type i = 0; i < a.extent(0); ++i)
    for (typename E::index_type j = 0; j < a.extent(1); ++j)
      a[i, j] *= k;
}

int main() {
  double buf[8] = {1, 2, 3, 4, 5, 6, 7, 8};
  scale(std::mdspan<double, std::extents<int, 2, 4>>(buf), 2.0);   // fully static

  std::vector<double> v(6, 1.0);
  scale(std::mdspan(v.data(), 2, 3), 3.0);                          // fully dynamic

  std::vector<double> flat(2 * 5, 1.0);   // 2 rows, 3 columns, row stride 5
  std::layout_stride::mapping m(std::dextents<int, 2>(2, 3), std::array{5, 1});
  scale(std::mdspan(flat.data(), m), 4.0);                          // strided

  std::printf("%g %g %g %g\n", buf[7], v[5], flat[5], flat[8]);   // 16 3 4 1
}
```

The four template parameters of `mdspan<T, Extents, LayoutPolicy, AccessorPolicy>` are the element type, the shape, the layout policy and the accessor policy; the last two default to row-major `layout_right` and `default_accessor<T>`, which simply dereferences a pointer. The rules for each part are covered in detail in [[views.multidim]]; this page covers only why they were designed this way.

## The starting point: data layouts that change with hardware

The design of `mdspan` comes from high-performance computing (HPC). Its predecessor is the multidimensional array `Kokkos::View` in the Kokkos library, which had long implemented multidimensional array references with replaceable layouts ([[P0331R0]]).

[[N4355]] puts the problem bluntly: the array layouts of scientific code often have to be rearranged for new hardware: for vector machines in the early years, later for multi-level caches, and today back and forth between array of structures and structure of arrays. With the layout hard-coded in index expressions, changing it means refactoring code, or maintaining several functionally identical copies with different layouts. The goal it proposes is **polymorphic layout**: the layout is a replaceable parameter, and changing it does not require changing the algorithm.

[[P0009R18]] illustrates this with a matrix-vector multiplication: the same parallel code is fast with row-major `layout_right` on a CPU, while on an NVIDIA GPU column-major `layout_left` is much faster, because adjacent threads access adjacent addresses and memory accesses can be coalesced. Only one template argument changes; the algorithm itself stays the same.

The same effect can be seen on a CPU. The function below always traverses with i outer and j inner, and only the layout policy changes:

```cpp title="layout-swap.cpp" run ok
#include <chrono>
#include <cstdio>
#include <mdspan>
#include <vector>

template<class Layout>
double row_sums(std::mdspan<const double, std::dextents<int, 2>, Layout> a,
                std::mdspan<double, std::dextents<int, 1>> y) {
  for (int i = 0; i < a.extent(0); ++i) {   // fixed loop order: i outer, j inner
    double s = 0;
    for (int j = 0; j < a.extent(1); ++j) s += a[i, j];
    y[i] = s;
  }
  return y[0];
}

template<class Layout>
void run(const char* name, const std::vector<double>& buf, int n) {
  std::vector<double> out(n);
  std::mdspan<const double, std::dextents<int, 2>, Layout> a(buf.data(), n, n);
  std::mdspan<double, std::dextents<int, 1>> y(out.data(), n);
  auto t0 = std::chrono::steady_clock::now();
  double r = 0;
  for (int k = 0; k < 10; ++k) r += row_sums(a, y);
  auto t1 = std::chrono::steady_clock::now();
  std::printf("%-13s %6.1f ms  (%g)\n", name,
      std::chrono::duration<double, std::milli>(t1 - t0).count() / 10, r);
}

int main() {
  const int n = 4096;                       // 4096 × 4096 doubles = 128 MiB
  std::vector<double> buf(std::size_t(n) * n, 1.0);
  run<std::layout_right>("layout_right", buf, n);
  run<std::layout_left>("layout_left", buf, n);
}
```

Across several runs (Apple Silicon, Clang 23, `-O2`), `layout_right` takes about 16–20 ms per round and `layout_left` about 65–110 ms. The former's inner loop reads adjacent elements; the latter jumps 32 KiB on every step. The reasons and more systematic measurements are in [[perf/memory-hierarchy]]. The same block of memory represents mutually transposed matrices under the two layouts; the data in this example is all 1, so the results are the same.

## The design space

### A view, not a container

`mdspan` does not allocate or free memory, and copying it only copies the pointer and the shape, just like `span` ([[views.contiguous]]). An owning multidimensional array has its own proposal, `mdarray` ([[P1684R5]]), which has not entered the standard to this day.

[[P0009R18]] gives two reasons for doing the view first. First, in parallel computing multiple threads access different parts of the same array, and allocation and deallocation are synchronization points, so a view is the basic way for parallel code to express which elements it accesses. Second, data has often already been allocated by another language: C, Fortran and Python's NumPy all need to be viewable as multidimensional arrays without copying.

### How to write the shape

Early proposals wanted to write the shape as an array type, with `int[3][][5]` meaning the second dimension is only known at run time:

```cpp
// the syntax P0332 envisioned (not C++)
using tensor = mdspan<double[][][], layout_left>;
// today's syntax
using tensor = mdspan<double, dextents<size_t, 3>, layout_left>;
```

This requires relaxing the language's restrictions on array types: `T[][]` is ill-formed today, and only the first dimension can be omitted. This part was split off into a separate language proposal, [[P0332R2]], which acknowledged that previous versions had not answered the questions raised by the Evolution Working Group (EWG), and it was ultimately not accepted.

The library side therefore uses a class template `extents<IndexType, size_t... Extents>` for the shape: each template argument is either a concrete length, a **static extent** ([[g:static-extent|static extent]]), or `dynamic_extent`, a **dynamic extent** ([[g:dynamic-extent|dynamic extent]]) whose value is stored in the object ([[mdspan.extents.overview#3]]). It needs no language change; the cost is verbosity.

[[N4355]] also pointed out a problem with another proposal of the time, `array_view`: its template parameter `N` meant the number of dimensions, while the `N` of `std::array<T, N>` is a length, so the same letter meant opposite things; and a strided view was yet another class, `strided_array_view`. `extents` puts the length of every dimension into the template arguments, with the rank given by the number of arguments; striding is just one kind of layout, needing no separate class.

### What static extents buy

The fundamental reason for allowing static extents is performance ([[P0009R18]] §2.5): when the compiler knows the length it can unroll loops and precompute offsets, and not storing that dimension saves registers and stack space. Many problems are naturally mixed: the number of particles is only known at run time, but each particle always has 3 coordinates.

```cpp title="particles.cpp" run ok
#include <cstdio>
#include <mdspan>
#include <vector>

// n particles × 3 coordinates: the particle count is known only at run time, 3 is the dimension of space
using Positions = std::mdspan<double, std::extents<int, std::dynamic_extent, 3>>;

double norm2(Positions p, int k) {
  double s = 0;
  for (int d = 0; d < p.extent(1); ++d) s += p[k, d] * p[k, d];   // the inner loop count is the constant 3
  return s;
}

int main() {
  int n = 1000;
  std::vector<double> buf(n * 3, 1.0);
  Positions p(buf.data(), n);                  // only the dynamic dimension is given
  static_assert(Positions::rank() == 2 && Positions::rank_dynamic() == 1);
  std::printf("%g %zu\n", norm2(p, 42), sizeof p);   // 3 16 (libc++, arm64)
}
```

At `-O2`, `norm2` compiles to 9 instructions: `k * 3` is computed with one shift-and-add, the 3 multiply-adds are fully unrolled, and the run-time particle count is never even read.

Making both dimensions static or both dynamic shows the difference more clearly. The two functions below differ only in the type of the shape:

```cpp title="static-vs-dynamic.cpp" ok
#include <mdspan>

using Static  = std::mdspan<const float, std::extents<int, 4, 4>>;
using Dynamic = std::mdspan<const float, std::dextents<int, 2>>;

float trace_s(Static m) {
  float s = 0;
  for (int i = 0; i < m.extent(0); ++i) s += m[i, i];
  return s;
}
float trace_d(Dynamic m) {
  float s = 0;
  for (int i = 0; i < m.extent(0); ++i) s += m[i, i];
  return s;
}
float at_s(Static m, int i, int j) { return m[i, j]; }
float at_d(Dynamic m, int i, int j) { return m[i, j]; }
```

Results with Clang 23 (arm64, `-O2`):

| Function | Instructions | Contents |
|---|---|---|
| `trace_s` | 10 | Four loads with offsets 0, 20, 40, 60 bytes encoded directly in the instructions, no loop |
| `trace_d` | 82 | Length checks, overflow checks, a 4-way unrolled main loop plus a tail loop for the remainder |
| `at_s` | 2 | `add w8, w2, w1, lsl #2` computes `i * 4 + j`, then one load |
| `at_d` | 3 | Take the column count from an argument register, `madd`, then load |

`at_d` generates essentially the same code as the hand-written `a[i * ld + j]`, so a fully dynamic `mdspan` has no extra overhead; static extents are a gain on top of that. `Static` stores only a pointer (8 bytes), and `Dynamic` stores a pointer and two `int`s (16 bytes); both are passed in registers. How to read this assembly is covered in [[perf/reading-assembly]].

### Customization points: a property list or two policies

The predecessor of `mdspan` was called `array_ref`, customized through a variadic property list: `array_ref<T, Properties...>`, with layout, access mode and so on all stuffed in as properties. LEWG's early reviews asked the proposal to explain how users would add properties, and pointed out that the standard library had no precedent for such a variadic property list. The atomic access proposed by [[P0860R1]] was also initially envisioned as one such property.

The Library Evolution Working Group (LEWG) finally compared two forms and chose the second (revision history of [[P0009R18]], R6):

```cpp
basic_mdspan<T, Extents, Properties...>        // arbitrary property list: rejected
basic_mdspan<T, Extents, Mapper, Accessor>     // two concepts, like Allocator: adopted
```

The division of labor between the two policies: the **layout policy** decides how a multidimensional index is converted to a one-dimensional offset, and the **accessor policy** ([[g:accessor-policy|accessor policy]]) decides how to get a reference to an element from a data handle and an offset. `m[i, j]` is just computing the offset and then accessing; [[mdspan.mdspan.members#4]] writes it in one line:

```cpp
return acc_.access(ptr_, map_(static_cast<index_type>(std::move(indices))...));
```

This is classic policy-based design ([[patterns/policy-based-design]]): each policy is a type with a fixed interface, the host class template combines them, and the two dimensions can be replaced independently. In the same review, LEWG also made clear it did not want to add an accessor parameter to the one-dimensional `span`.

A layout policy is not itself a mapping. `LayoutPolicy::mapping<E>` is the mapping for a particular `extents` type `E` ([[mdspan.layout.policy.reqmts#1]]), so the same layout can be applied to any shape, and `layout_right` itself is just an empty struct.

### What layouts can express

The standard provides three layouts: row-major `layout_right` (the C convention), column-major `layout_left` (the Fortran convention), and `layout_stride`, with an arbitrary stride per dimension. The custom layouts [[P0009R18]] mentions include tiled layouts (a matrix made of small matrices, improving locality and vectorization), space-filling curves, and **non-unique** layouts, where several indices refer to the same element.

A symmetric matrix is the classic example of a non-unique layout: `A[i, j]` and `A[j, i]` are the same element, so storing half is enough. Below is a complete custom layout that meets all the requirements of [[mdspan.layout.reqmts]]:

```cpp title="symmetric.cpp" run ok
#include <cstdio>
#include <mdspan>
#include <utility>

// symmetric matrix: only the upper triangle is stored; (i, j) and (j, i) refer to the same element
struct layout_symmetric {
  template<class Extents>
  struct mapping {
    static_assert(Extents::rank() == 2);
    using extents_type = Extents;
    using index_type   = typename Extents::index_type;
    using rank_type    = typename Extents::rank_type;
    using layout_type  = layout_symmetric;

    extents_type ext_;
    mapping() = default;
    constexpr mapping(const extents_type& e) : ext_(e) {}

    constexpr const extents_type& extents() const noexcept { return ext_; }
    constexpr index_type operator()(index_type i, index_type j) const noexcept {
      if (i > j) std::swap(i, j);
      index_type n = ext_.extent(0);
      return i * n - i * (i - 1) / 2 + (j - i);   // upper triangle packed by rows
    }
    constexpr index_type required_span_size() const noexcept {
      index_type n = ext_.extent(0);
      return n * (n + 1) / 2;
    }
    static constexpr bool is_always_unique()     noexcept { return false; }
    static constexpr bool is_always_exhaustive() noexcept { return true; }
    static constexpr bool is_always_strided()    noexcept { return false; }
    constexpr bool is_unique()     const noexcept { return ext_.extent(0) <= 1; }
    constexpr bool is_exhaustive() const noexcept { return true; }
    constexpr bool is_strided()    const noexcept { return false; }
    constexpr index_type stride(rank_type) const noexcept { return 0; }  // precondition is_strided() doesn't hold, so never validly called
    friend constexpr bool operator==(const mapping&, const mapping&) = default;
  };
};

int main() {
  double packed[6] = {1, 2, 3, 4, 5, 6};          // a 3×3 symmetric matrix needs only 6 elements
  using E = std::extents<int, 3, 3>;
  std::mdspan<double, E, layout_symmetric> s(packed, E{});
  std::printf("%g %g %d\n", s[0, 2], s[2, 0], s.mapping().required_span_size());  // 3 3 6
  s[2, 1] = 50;                                     // also changes s[1, 2]
  std::printf("%g\n", s[1, 2]);                     // 50
}
```

The three properties such as `is_unique()` are promises to generic algorithms: when unique, parallel writes to different indices do not conflict; when exhaustive, the whole storage can be treated as a one-dimensional array; when strided, it can be passed to BLAS interfaces that take stride arguments. They only mean something when they return `true`; `false` means unknown (Note 1 in [[mdspan.layout.reqmts#14]]).

### What accessors can express

[[P0009R18]] §2.7 explains why access needs to be customizable: besides ordinary reads and writes, hardware has atomic access and non-temporal (cache-bypassing) reads and writes; C's `restrict` expresses that an array does not alias other arrays, and `volatile` limits optimization; heterogeneous systems have GPU memory the CPU cannot access directly, or global shared memory that needs special operations to access. None of these change the indexing formula; they only change how the element is touched once the offset is known.

So the accessor requirements are deliberately loose. The data handle `data_handle_type` need not be `element_type*`, and need not even be dereferenceable (Note 1 in [[mdspan.accessor.general#3]]); `reference` need not be `element_type&`, only have a common reference type with it ([[mdspan.accessor.reqmts#4]]). This makes proxy references possible. The accessor below returns an `atomic_ref` on every access, letting several threads safely accumulate into the same ordinary `int` array, which is exactly the atomic accessor [[P0860R1]] envisioned:

```cpp title="atomic-accessor.cpp" run ok
#include <atomic>
#include <cstdio>
#include <mdspan>
#include <thread>
#include <vector>

// every access goes through atomic_ref; the elements are still plain ints
template<class T>
struct atomic_accessor {
  using element_type     = T;
  using data_handle_type = T*;
  using reference        = std::atomic_ref<T>;
  using offset_policy    = atomic_accessor;

  constexpr reference access(T* p, std::size_t i) const noexcept {
    return reference(p[i]);
  }
  constexpr T* offset(T* p, std::size_t i) const noexcept { return p + i; }
};

int main() {
  std::vector<int> buf(4 * 4, 0);
  using E = std::extents<int, 4, 4>;
  std::mdspan<int, E> plain(buf.data());
  std::mdspan<int, E, std::layout_right, atomic_accessor<int>> hist(buf.data());

  std::vector<std::jthread> ts;
  for (int t = 0; t < 4; ++t)
    ts.emplace_back([=] {
      for (int k = 0; k < 100000; ++k)
        hist[k % 4, (k / 4) % 4].fetch_add(1, std::memory_order_relaxed);
    });
  ts.clear();                                  // wait for all threads to finish

  std::printf("%d %d\n", plain[0, 0], plain[3, 3]);   // 25000 25000
}
```

Running with `-fsanitize=thread` reports no data race. Replace `hist` with `plain` and the same code has a data race, which is undefined behavior. The only accessors the standard library itself provides are `default_accessor` and C++26's `aligned_accessor` ([[P2897R7]]), which tells the compiler how many bytes the pointer is aligned to.

### Subscripting: from `m(i, j)` to `m[i, j]`

For many years in committee, `mdspan` accessed elements with the function call operator: `m(i, j)`. The reason is simple: before C++20 an overloaded `operator[]` could only have one parameter, and `m[i, j]` evaluated the comma expression `(i, j)` and then subscripted.

[[P2128R6]] compared three idioms library authors used at the time to get around this limitation:

| Idiom | Who uses it | Problem the proposal points out |
|---|---|---|
| `a(i, j, k)` | Fortran, Matlab, Eigen, Kokkos, and `mdspan` at the time | `[]` for one dimension, `()` for several: two kinds of punctuation for the same operation; a type with `operator()` may be mistaken for a callable, and generic code that passes arguments in the wrong order still compiles |
| `a[i][j][k]` | C arrays of arrays, `vector<vector<T>>` | `a[i]` must be a proxy object, and the call depth to access one element grows with the rank, hindering inlining; it also implies row-major order, each row allocated separately, and rows of possibly different lengths |
| `a[{i, j, k}]` | C++ AMP | An index object has to be constructed and then taken apart; no other language does this |

The proposal's conclusion was to let `operator[]`, like `operator()`, accept any number of arguments (including zero). Several approaches where the compiler rewrites the expression were discussed and abandoned, such as rewriting `a[x][y][z]` as `a.operator[](x, y, z)`. That would change the meaning of a common idiom: `a[x]` in `a[x][y]` might no longer be a valid subexpression; code like `files["home", user]["section", "key"]` that deliberately chains two multi-argument subscripts would be wrongly merged; and overload resolution would have to rank a single multi-argument overload against a chain of single-argument overloads.

This path was viable because [[P1161R3]] had already deprecated unparenthesized comma expressions in subscripts in C++20, and surveys showed this usage was extremely rare. P2128 made it ill-formed in C++23, giving the syntax over to multidimensional subscripting. Built-in arrays are unaffected; their subscript still accepts only one expression:

```cpp title="comma-subscript.cpp" error
struct Grid {
  int d[12];
  int& operator[](int i, int j) { return d[i * 4 + j]; }   // allowed since C++23
};
int main() {
  int arr[3] = {};
  Grid g{};
  g[1, 2] = 7;        // OK: g.operator[](1, 2)
  arr[1, 2] = 7;      // error: built-in subscript accepts one expression (a deprecated comma expression in C++20)
  arr[(1, 2)] = 7;    // OK: with parentheses it is still a comma expression
}
```

Under `-std=c++2c`, Clang 23 reports "built-in subscript operator for type 'int[3]' expects exactly one argument" for `arr[1, 2]`; under `-std=c++20` the definition of `Grid` itself is rejected, and `arr[1, 2]` only gets a deprecation warning.

P2128 did not also give built-in arrays a multidimensional meaning, on the grounds that code valid (though deprecated) in C++20 should become ill-formed in C++23 rather than silently change meaning; whether `arr[1, 2]` should mean something else was left for later discussion. From R13 on, P0009 switched its access operator to `operator[]`.

This is an example of a library need driving a language change: without P2128, the standard's multidimensional array could only use `m(i, j)`.

### Why it is not a range

`mdspan` has no `begin()` or `end()`:

```cpp
static_assert(!std::ranges::range<std::mdspan<int, std::dextents<int, 2>>>);
```

The early `array_ref` had member `begin()`/`end()`. In review, LEWG's support for them was weak, and it did not want this proposal to provide functions producing ranges, preferring a separate proposal dedicated to multidimensional iteration. R3 therefore removed iterator support (revision history of [[P0009R18]]). That follow-up proposal did not enter the standard.

Below are some difficulties that can be seen from the design itself; this is analysis, not text from the proposal:

- What to traverse. Traversing by index and traversing by storage are not the same thing for a general layout. The symmetric matrix above has 9 indices and 6 elements, so traversing by index visits off-diagonal elements twice; the storage of a `layout_stride` may have gaps that do not belong to the view.
- In what order. Traversing indices in lexicographic order is, under `layout_left`, exactly the slow strided access measured in the previous section; traversing in storage order requires the layout to be exhaustive.
- Cost. An iterator has to hold a multidimensional index, and each `++` has to carry dimension by dimension, which adds branches compared with nested loops and is harder to vectorize.

The algorithms in the current draft that can process an `mdspan` as a whole are the multidimensional `copy` and `fill` added after C++26, which take an `mdspan` directly rather than a range ([[mdspan.syn]]). Traversing elements is still done with nested loops.

### Names, aliases and index types

The final interface is the result of several rounds of simplification:

- From R6 on, the full class template was called `basic_mdspan<T, Extents, Layout, Accessor>`, with a convenience alias `mdspan<T, size_t... Extents>`. [[P2299R3]] pointed out that with class template argument deduction and an alias for a fully dynamic shape, this distinction was unnecessary: remove the alias, rename `basic_mdspan` to `mdspan`, and add deduction guides and `dextents<Rank>`. It was merged into P0009 in R13, which is why today you can write `std::mdspan m(p, rows, cols)` directly.
- The type of lengths and indices changed from `ptrdiff_t` to `size_t` (R11, for consistency with `span`), and then, through [[P2553R1]], to `IndexType`, the first template parameter of `extents` (merged in R17). The signedness and width of the index type affect performance; `int` overflow is undefined behavior, which lets compilers optimize more aggressively.
- After the index type parameter was added, `dextents<size_t, 3>` got longer again. [[P2389R2]] initially wanted to remove the parameter; LEWG did not agree to a breaking change, and in the end C++26 added `dims<Rank, IndexType = size_t>` alongside ([[mdspan.extents.dims]]).

One direct consequence of the index type parameter is the conversion rules: converting from `extents<size_t, ...>` to `extents<int, ...>` must be explicit even when the shape is the same, because the range of values narrows ([[mdspan.extents.cons#4]]). `std::mdspan(p, n)` deduces a `size_t` index, and passing it to a function whose parameter type is `dextents<int, 1>` fails to compile, which is why `layout-swap.cpp` above writes out the type of `y` explicitly.

## Wording

!!! std
    The class template `extents` represents a multidimensional index space of rank equal to `sizeof...(Extents)`. ([[mdspan.extents.overview]])

    `extents` represents a multidimensional index space whose rank is the number of template arguments. Throughout [views], "extents" and "multidimensional index space" are synonyms.

P0009R18 adds the header `<mdspan>`, placed under [views] in clause 23 (containers library), alongside `span`. Organized by location in the current draft:

| Subclause | Contents |
|---|---|
| [[mdspan.overview]] | Definitions of multidimensional index space, rank and multidimensional index |
| [[mdspan.extents]] | `extents`, `dextents`; C++26's `dims` |
| [[mdspan.layout]] | Layout mapping requirements ([[mdspan.layout.reqmts]]), layout policy requirements ([[mdspan.layout.policy.reqmts]]), `layout_left`/`layout_right`/`layout_stride`; C++26's two padded layouts |
| [[mdspan.accessor]] | Accessor policy requirements, `default_accessor`; C++26's `aligned_accessor` |
| [[mdspan.mdspan]] | `mdspan` itself, constructors, deduction guides, `operator[]` |
| [[mdspan.sub]] | C++26's `submdspan` |
| [[expr.sub#1]], [[over.sub#1]] | P2128: the brackets may contain a comma-separated list, passed to `operator[]`; the built-in subscript still accepts only one expression ([[expr.sub#2]]) |
| [[diff.cpp20.expr#2]] | Annex C: the meaning of commas in subscripts changed |

Feature-test macros: `__cpp_lib_mdspan` is `202406L` in the current draft, which is also what libc++ reports; `__cpp_multidimensional_subscript` is `202211L` ([[cpp.predefined]]).

## Consequences

### What broke

`<mdspan>` is a new header, and the library itself does not affect old code. The only incompatibility comes from P2128: in C++20 `arr[1, 2]` is equivalent to `arr[(1, 2)]` (deprecated); from C++23 it either calls a multi-parameter `operator[]` or is ill-formed ([[diff.cpp20.expr#2]]).

### C++26 follow-ups

`submdspan` was originally part of P0009 and was split off so that `mdspan` could make C++23 ([[P0009R18]] §2.8). It was added back in C++26 by [[P2630R4]], with two extensions: slices can be compile-time values, so the resulting shape can keep static extents; and custom layouts can take part in slicing.

The customization mechanism of the second is worth a look. `submdspan` itself doesn't know how to slice an arbitrary layout; it hands the original mapping and the slices to a function named `submdspan_mapping`, found only by argument-dependent lookup (ADL, [[g:argument-dependent-lookup]]) ([[mdspan.sub.map.sliceable#2]]). P2630 compared plain ADL, customization point objects and `tag_invoke`, and chose the simplest, plain ADL, reasoning that the name is distinctive enough, that only the few people writing custom layouts implement it, and that it has no default implementation, so failing to find it is a compile error. It was also not added to the layout policy requirements, because not every layout can efficiently support every slice.

[[P2642R6]] added `layout_left_padded` and `layout_right_padded`: contiguous in one dimension, with the distance between adjacent rows (or columns) allowed to exceed the row length, corresponding to BLAS's "leading dimension". Compared with `layout_stride` it has two advantages: the type guarantees that one dimension has stride 1, so only one stride needs to be stored; and taking a contiguous submatrix of such a matrix gives the same kind of layout again, which LAPACK-style blocked algorithms rely on. The proposal also considered a `layout_stride` whose strides could all be compile-time constants, and judged it too complex: at higher ranks, most strides depend on run-time lengths anyway.

The specific rules for slicing, the choice of result layout, and later rewrites of the slice types are in the submdspan section of [[views.multidim]].

### Compiler support

The libc++ shipped with Clang 23 implements `mdspan`, `extents`, `dextents`, `dims`, the three basic layouts, `default_accessor` and `aligned_accessor`, and multi-parameter `operator[]`. `submdspan`, `full_extent` and the two padded layouts are not implemented yet, and `__cpp_lib_submdspan` is not defined. All examples above with verdicts compiled with `-std=c++2c -Wall -Wextra -pedantic` (with `comma-subscript.cpp` rejected as expected); the runnable examples were run under ASan/UBSan, and `atomic-accessor.cpp` under TSan.

## Questions

!!! question "1. Why does this code fail to compile?"
    ```cpp
    void f(std::mdspan<double, std::dextents<int, 2>> a);
    std::vector<double> v(12);
    f(std::mdspan(v.data(), 3, 4));
    ```

<details markdown="1">
<summary>Answer</summary>

By the deduction guide, `std::mdspan(v.data(), 3, 4)` gives `mdspan<double, extents<size_t, dynamic_extent, dynamic_extent>>` (the deduction guides in [[mdspan.mdspan.overview]]). The conversion from `extents<size_t, ...>` to `extents<int, ...>` is `explicit` because the maximum value of `int` is less than that of `size_t` ([[mdspan.extents.cons#4]]), and that `explicit` propagates all the way to `mdspan`'s converting constructor, so it cannot be used to copy-initialize the parameter. Writing `f(std::mdspan<double, std::dextents<int, 2>>(v.data(), 3, 4))` works.
</details>

!!! question "2. Can the symmetric matrix layout be expressed with `layout_stride`? With a custom layout, what do parallel writes need to watch out for?"

<details markdown="1">
<summary>Answer</summary>

No. The mapping of `layout_stride` is `Σ iᵣ × sᵣ` and is required to be unique ([[mdspan.layout.stride.cons]]), while the symmetric layout maps `(i, j)` and `(j, i)` to the same offset, so by definition it is not unique.

When a custom layout's `is_unique()` returns `false`, generic code cannot assume different indices correspond to different elements. Two threads writing `s[1, 2]` and `s[2, 1]` respectively are writing the same object, and without synchronization that is a data race. Either traverse only the upper triangle, or switch to an atomic accessor like the `atomic_accessor` above.
</details>

!!! question "3. In C++23, what is `int arr[3]; arr[1, 2];`? What about `std::vector<int> v(3); v[1, 2];`?"

<details markdown="1">
<summary>Answer</summary>

Both are ill-formed. The built-in subscript requires exactly one assignment-expression inside the brackets ([[expr.sub#2]]). `vector`'s `operator[]` has only one parameter, and `v[1, 2]` is interpreted by [[over.sub#1]] as `v.operator[](1, 2)`, for which there is no viable overload. In C++20 both are equivalent to subscripting with `2`, just deprecated; Annex C records the change ([[diff.cpp20.expr#2]]). To keep the old meaning, write `arr[(1, 2)]`.
</details>
