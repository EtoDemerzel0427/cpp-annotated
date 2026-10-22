---
title: Expression templates
summary: "Evaluating a + b + c in one loop without temporary vectors: operators return lightweight objects that record the structure of the computation, and evaluation happens element by element on assignment. Constraining the operators with concepts, dealing with auto dangling and aliasing, and comparing with valarray, ranges' zip_transform, std::linalg and Eigen."
tags: expression templates, operator overloading, lazy evaluation, dangling, aliasing, idiom
updated: 2026-10-19
---

!!! tldr
    - With an `operator+` that returns by value, `x = a + b + c` creates a temporary vector and makes two passes. Expression templates make `+` return only a small object recording "left operand, right operand, operation", and assignment computes everything in one loop, element by element.
    - The structure of the expression is encoded in the type: `a + b * c` has type `Binary<plus, Vec, Binary<multiplies, Vec, Vec>>`. After inlining, this type tree becomes a single vectorized loop at -O2.
    - The operator templates must be constrained by a concept, preferably an opt-in one. A structural concept (has `operator[]` and `size()`) also pulls in `std::vector`.
    - Expression objects refer to their operands. `auto e = a + b + c;` leaves dangling references, because even the inner expression nodes are temporaries; writing `x = …` as one full-expression is safe.
    - For elementwise operations, `a = b + a` is fine, but matrix multiplication `a = a * b` reads elements that have already been written. The standard allows `valarray` to use expression templates (libc++ does), while C++26 `<linalg>` uses function calls and makes non-aliasing a precondition.

## One allocation per +

```cpp run title="naive.cpp" ok
#include <cstddef>
#include <cstdio>
#include <cstdlib>
#include <new>
#include <vector>

int allocs = 0;
void* operator new(std::size_t n) {
  ++allocs;
  if (void* p = std::malloc(n)) return p;
  throw std::bad_alloc();
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }

struct Vec {
  std::vector<double> d;
  explicit Vec(std::size_t n) : d(n) {}
  std::size_t size() const { return d.size(); }
  double& operator[](std::size_t i) { return d[i]; }
  double operator[](std::size_t i) const { return d[i]; }
};

Vec operator+(const Vec& a, const Vec& b) {
  Vec r(a.size());                       // one allocation per +
  for (std::size_t i = 0; i < a.size(); ++i)
    r[i] = a[i] + b[i];
  return r;
}

int main() {
  Vec a(1000), b(1000), c(1000), x(1000);
  allocs = 0;
  x = a + b + c;
  std::printf("allocations: %d\n", allocs);  // 2
}
```

`x = a + b + c` is evaluated as `(a + b) + c`. The first `+` allocates a temporary vector `t` and makes one pass; the second `+` allocates a result vector and makes another pass; finally the result is move-assigned to `x`. In our tests it prints 2 at both -O0 and -O2.

Besides the allocations, the intermediate result `t` is first written to memory and then read back by the next loop. If the vectors are larger than the cache, that write and read are extra memory traffic. The hand-written loop is a single line, `x[i] = a[i] + b[i] + c[i]`, with no allocation and one pass.

Adding an overload of `operator+` taking `Vec&&`, which reuses the buffer of the left temporary in place, brings the allocations down to one, but there are still two passes. To match the hand-written loop, `+` must not compute anything immediately.

## Building expression templates step by step

The idea of **expression templates** is that operators do not compute results; they return an object recording the operands and the kind of operation. That object can be indexed like a vector, and each element is computed only when it is accessed. The actual loop appears only once, at assignment.

```cpp run title="et.cpp" ok
#include <cstddef>
#include <cstdio>
#include <functional>
#include <type_traits>
#include <vector>

namespace la {

template <class T>
constexpr bool enable_vec_expr = false;      // opt-in: not an expression by default

template <class E>
concept vec_expr = enable_vec_expr<std::remove_cvref_t<E>>;

class Vec {
  std::vector<double> d_;
public:
  explicit Vec(std::size_t n) : d_(n) {}
  std::size_t size() const { return d_.size(); }
  double& operator[](std::size_t i) { return d_[i]; }
  double operator[](std::size_t i) const { return d_[i]; }

  template <vec_expr E>
  Vec(const E& e) : d_(e.size()) { assign(e); }
  template <vec_expr E>
  Vec& operator=(const E& e) { assign(e); return *this; }

private:
  template <class E>
  void assign(const E& e) {                  // the only loop (assumes equal lengths)
    for (std::size_t i = 0; i < d_.size(); ++i)
      d_[i] = e[i];
  }
};

template <class Op, class L, class R>
struct Binary {                              // an l op r not yet computed
  const L& l;
  const R& r;
  std::size_t size() const { return l.size(); }
  double operator[](std::size_t i) const {
    return Op{}(l[i], r[i]);                 // compute only the element requested
  }
};

template <>
constexpr bool enable_vec_expr<Vec> = true;
template <class Op, class L, class R>
constexpr bool enable_vec_expr<Binary<Op, L, R>> = true;

template <vec_expr L, vec_expr R>
Binary<std::plus<>, L, R> operator+(const L& l, const R& r) {
  return {l, r};
}
template <vec_expr L, vec_expr R>
Binary<std::multiplies<>, L, R> operator*(const L& l, const R& r) {
  return {l, r};
}

} // namespace la

int main() {
  la::Vec a(3), b(3), c(3), x(3);
  for (std::size_t i = 0; i < 3; ++i) { a[i] = i; b[i] = 10 * i; c[i] = 100; }
  x = a + b * c;                             // one loop, no temporary Vec
  std::printf("%g %g %g\n", x[0], x[1], x[2]);  // 0 1001 2002
}
```

The program has three parts, explained one at a time below.

### Step 1: operators return a description

`Binary<Op, L, R>` is one node of the expression tree. It stores references to its two operands, and its `operator[]` performs the operation on the `i`-th element only when called. An operand can be a `Vec` or another `Binary`, so nodes nest.

`b * c` returns `Binary<multiplies<>, Vec, Vec>`, and `a + (b * c)` returns `Binary<plus<>, Vec, Binary<multiplies<>, Vec, Vec>>`. The shape of the expression is written entirely into the type: template argument deduction records each operand's type in `L` and `R`. The kind of operation is represented by an empty function object type `Op`, which the node does not store, so `sizeof` is just two references, 16 bytes in our tests.

### Step 2: assignment triggers the only loop

`Vec` has a constructor template and an assignment operator template that accept any expression, and both call `assign`. In `x = a + b * c`, the loop body of `assign` calls `e[i]` once for each `i`, `e[i]` recursively calls `operator[]` of its two children, and eventually `Vec::operator[]` reads the elements. All of these functions are tiny, and after inlining the loop body is `x[i] = a[i] + b[i] * c[i]`.

The assignment operator template does not replace copy assignment. For `x = y` (with `y` a `Vec`), both are exact matches, and a non-template function is preferred over a function template specialization ([[over.match.best#2.4]]), so the implicitly declared copy assignment is still used.

### Step 3: constrain the operators with a concept

Both parameter types of `operator+` are deduced. Without a constraint it accepts any type. The library below omits the constraint, and the user code has a using-directive:

```cpp run title="hijack.cpp" error
#include <cstddef>

namespace la {
template <class L, class R>
struct Sum {
  const L& l;
  const R& r;
  double operator[](std::size_t i) const { return l[i] + r[i]; }
};
template <class L, class R>               // unconstrained
Sum<L, R> operator+(const L& l, const R& r) { return {l, r}; }
}

using namespace la;
enum Color { red, green, blue };

int main() {
  int n = green + 1;                       // error: Sum<Color, int> cannot be converted to int
  return n;
}
```

`green + 1` has an operand of enumeration type, so overload resolution is performed ([[over.match.oper#2]]). The candidates include the built-in `operator+(int, int)`, which needs an integral promotion from `Color` to `int`; `la::operator+` deduces `L = Color` and `R = int` with exact matches for both arguments, so the template wins. Clang 23 reports `no viable conversion from 'Sum<Color, int>' to 'int'`.

With the constraint, `Color` does not satisfy `vec_expr`, the template is not viable ([[over.match.viable#3]]), and the built-in operator works as usual. How the constraint is written matters:

- A structural check, e.g. requiring `e[i]` convertible to `double` and `e.size()` to exist, is also satisfied by `std::vector<double>`. In our tests, under the using-directive, `auto w = v + v;` (with `v` a `std::vector<double>`) compiles and yields a `Sum<vector, vector>`, which is probably not what the user wanted.
- Opt-in, as in `et.cpp`, uses a variable template `enable_vec_expr` that defaults to `false`, and only the library's own types are explicitly specialized to `true`. The standard library's `ranges::enable_view` and `enable_borrowed_range` follow the same design (see [[topics/ranges-design]]).

Even without a using-directive, `la::operator+` is found by argument-dependent lookup ([[basic.lookup.argdep]]) whenever one operand's type is associated with namespace `la`, such as a `la::Vec`. The constraint is the only thing preventing false matches. How concepts are written and checked is covered in [[topics/concepts]].

## The language rules that make it work

1. **Operators are function calls.** When an operand has class type, `a + b` is rewritten as `operator+(a, b)` for overload resolution ([[over.match.oper#2]]), and the candidates include member, non-member and built-in operators ([[over.match.oper#3]]). All expression templates need is a function whose return type can be customized.
2. **Deduction records the structure in the type.** Each level of `operator+` deduces `L` and `R` from its arguments, so nested expressions become nested template specializations. The types are fully known at compile time, so every `operator[]` is a direct call that can be inlined, with no virtual functions or function pointers.
3. **Temporary nodes live until the end of the full-expression.** `a + b + c` first creates a temporary `Binary<plus, Vec, Vec>`, to which the reference member of the outer node binds. Temporaries are destroyed as the last step of evaluating the full-expression that contains them ([[class.temporary#4]]), and binding to a reference parameter of a function does not extend their lifetime ([[class.temporary#6.10]]). So `x = a + b + c;` is safe: the whole tree is destroyed after the assignment loop finishes. The `auto` trap below is the other side of this rule.

!!! std
    Temporary objects are destroyed as the last step in evaluating the full-expression that (lexically) contains the point where they were created.

    A temporary is destroyed as the last step of evaluating the full-expression that contains it ([[class.temporary#4]]).

## Costs, measured

### Run time

These are observed timings in our tests (Apple M-series, Clang 23, -O2) for computing `x = a + b + c + d`, in nanoseconds per element. "reuse" is the version with an extra `Vec&&` overload of `operator+` that reuses the left operand's buffer:

| n | return by value | reuse | expression templates | allocations per assignment |
|---|---|---|---|---|
| 1 000 | 0.70 | 0.45 | 0.22 | 3 / 1 / 0 |
| 100 000 | 0.76 | 0.69 | 0.38 | 3 / 1 / 0 |
| 10 000 000 | 1.4–1.8 | 0.97 | 0.55–0.58 | 3 / 1 / 0 |

When the vectors fit in cache, the gap comes mostly from the number of loops and the allocations; when they are much larger than the cache, it comes from writing back and re-reading intermediate results. These numbers describe only our test machine; a different machine, element type or expression length will change them.

### Generated code

Put `x = a + b + c` in a function of its own and look at the arm64 assembly from `-O2 -S`: there are no function calls, and the `Binary` objects are gone entirely. The function first performs a run-time overlap check (the compiler does not know whether `x`'s buffer overlaps `a`, `b` or `c`); if there is no overlap it enters the vectorized main loop, handling 8 `double`s per iteration:

```text
LBB0_8:
	ldp	q0, q1, [x14, #-32]      ; 4 doubles of a
	ldp	q2, q3, [x14], #64       ; 4 more
	ldp	q4, q5, [x15, #-32]      ; b
	ldp	q6, q7, [x15], #64
	fadd.2d	v0, v0, v4
	...                          ; 8 fadd.2d in total: add b first, then c
	stp	q0, q1, [x16, #-32]      ; store into x
	stp	q2, q3, [x16], #64
	subs	x0, x0, #8
	b.ne	LBB0_8
```

If they overlap, it falls back to a scalar elementwise loop (`ldr d0` / `fadd d0` / `str d0`). This is the same shape of code a hand-written `for` loop produces. The catch is that all of it depends on inlining: at -O0 every `operator[]` is a real call.

### Compile time and debug builds

Every differently shaped expression is a new type, each instantiating its own `operator[]`, `size()` and `assign`. Compiling `x = v[0] + v[1] + … + v[N-1]` to an object file, we observed:

| N | functions defined at -O0 | longest mangled name (characters) | -O0 object file | -O2 compile time |
|---|---|---|---|---|
| 8 | 25 | 175 | 6.5 KB | 0.25 s |
| 64 | 137 | 905 | 86 KB | 0.27 s |
| 256 | 521 | 3 401 | 978 KB | 0.80 s |

The same expression written with a by-value `operator+` gives an -O0 object file of only 21–46 KB, and the number of functions does not grow with N. It actually compiles more slowly at -O2, though (3.98 s at N = 256), because the optimizer has to deal with 255 inlined loops. So the compile-time cost of expression templates falls mainly on debug builds, symbol tables and debug info; in this toy implementation it does not show up as -O2 compile time. A real library has dozens of node types and many overloads, and parsing and instantiating its headers is a cost in itself.

### Error messages

`x = a + b * c + 1.0` is an error in `et.cpp`, because `double` is not an expression. With the constraint, Clang reports `invalid operands to binary expression` at the line the user wrote, and the last few notes point out `'double' does not satisfy 'vec_expr'`; but it also lists every non-matching `operator+` candidate (including a dozen or so from `<string>`), 67 lines in all in our tests.

Without the constraint, `operator+` accepts everything, and the error is deferred until `Binary<…, double>::operator[]` is instantiated in the loop of `assign`: `subscripted value is not an array, pointer, or vector`, located in the library header, followed by a chain of `in instantiation of …` notes, each with the full nested type name. This time it is only 14 lines, but the longer the expression, the longer the type names, and the reader has to dig the offending line out of the instantiation stack.

## Traps

### auto keeps a dangling tree

```cpp ub
// continuing the la namespace from et.cpp
int main() {
  la::Vec a(3), b(3), c(3);
  auto e = a + b + c;      // Binary<plus, Binary<plus, Vec, Vec>, Vec>
  la::Vec x = e;           // UB: the inner node referenced by e.l has been destroyed
}
```

`a`, `b` and `c` are all still alive, but the inner node produced by `a + b` is a temporary, destroyed at the end of the first declaration ([[class.temporary#4]]). The outer node deduced by `auto` still holds a reference to it. Run with `-fsanitize=address` in our tests, it reports `stack-use-after-scope` in `Binary<plus, Vec, Vec>::size()`. There is no warning at compile time.

There are two levels of improvement:

<div class="compare" markdown="1">

```cpp
template <class Op, class L, class R>
struct Binary {
  const L& l;  // nodes by reference too
  const R& r;
  // ...
};
```

```cpp
template <class E>
using stored_t = std::conditional_t<
    std::is_same_v<E, Vec>, const E&, E>;

template <class Op, class L, class R>
struct Binary {
  stored_t<L> l;  // leaves by reference, nodes by value
  stored_t<R> r;
  // ...
};
```

</div>

The right side stores inner nodes by value and keeps references only to leaves like `Vec`. Nodes are small, and copying them does not touch the elements. With this change the program above runs cleanly under ASan in our tests, the -O2 code for `x = a + b + c` is still the same vectorized loop, and `sizeof(a + b + c)` goes from 16 to 24 bytes. libc++'s `valarray` splits it the same way (see the next section).

But when a leaf itself is a temporary, storing nodes by value does not help:

```cpp ub
la::Vec make() { return la::Vec(3); }

int main() {
  la::Vec a(3);
  auto e = a + make();     // e.r refers to a temporary Vec
  la::Vec x = e;           // UB
}
```

ASan reports `stack-use-after-scope` here too. Add `[[clang::lifetimebound]]` to the parameters of `operator+`, and Clang gives a `-Wdangling` warning for both examples (`temporary whose address is used as value of local variable 'e' will be destroyed at the end of the full-expression`), while `x = a + b + c;` and `la::Vec y = a + b + c;` are unaffected. This is a Clang extension, not a standard attribute; its use is described in [[topics/dangling-references]].

!!! pitfall "auto changes the type"
    With an expression template library, `auto` deduces not a vector but an expression object that refers to the operands. Even without dangling, its value follows the operands: `auto e = a + b;`, then modify `a`, and reading `e[0]` afterwards gives the modified result. When you want the result, spell out the type: `la::Vec e = a + b;`.

### Aliasing: fine elementwise, not for matrix multiplication

`a = b + a` writes back into `a` itself. For each `i`, the expression template loop first reads `b[i]` and `a[i]` and then writes `a[i]`; the `i`-th result depends only on the `i`-th elements, and nothing is read again after being written, so the result is correct. Whenever each output element depends only on input elements at the same index, computing in place is fine.

Matrix multiplication does not meet that condition:

```cpp run title="matmul-alias.cpp" ok
#include <cstddef>
#include <cstdio>
#include <vector>

struct Mat {
  std::size_t n;
  std::vector<double> d;
  Mat(std::size_t n, std::vector<double> v) : n(n), d(v) {}
  double& operator()(std::size_t i, std::size_t j) { return d[i * n + j]; }
  double operator()(std::size_t i, std::size_t j) const { return d[i * n + j]; }
  template <class E>
  Mat& operator=(const E& e) {           // writes back element by element
    for (std::size_t i = 0; i < n; ++i)
      for (std::size_t j = 0; j < n; ++j)
        (*this)(i, j) = e(i, j);
    return *this;
  }
};

struct Prod {                            // an l * r not yet computed
  const Mat& l;
  const Mat& r;
  double operator()(std::size_t i, std::size_t j) const {
    double s = 0;
    for (std::size_t k = 0; k < l.n; ++k) s += l(i, k) * r(k, j);
    return s;
  }
};
inline Prod operator*(const Mat& l, const Mat& r) { return {l, r}; }

int main() {
  Mat a(2, {1, 2, 3, 4});
  Mat b(2, {0, 1, 1, 0});                // swaps the two columns
  a = a * b;                             // expected 2 1 4 3
  std::printf("%g %g %g %g\n", a(0, 0), a(0, 1), a(1, 0), a(1, 1));
}
```

The program prints `2 2 4 4`. Element `(0, 1)` of the result reads all of row 0 of `a`, but `(0, 0)` has already been overwritten with 2. This is not undefined behavior; every step is well defined. The algorithm is simply wrong.

The fix is to evaluate the product into a temporary matrix first and then assign it to the left side. Multiplication is O(n³), so one extra O(n²) copy is negligible. Eigen does exactly this: matrix products are evaluated into a temporary by default, and when the user can guarantee there is no overlap, `c.noalias() = a * b` skips it. C++26 `<linalg>` instead makes non-overlap a precondition: an output argument must not overlap any other argument unless the function explicitly allows it ([[linalg.helpers.concepts#3]]); `add` allows its output to alias an input ([[linalg.algs.blas1.add#6]]), `matrix_product(A, B, C)` does not.

## Expression templates in the standard library: valarray

The synopsis declares `std::valarray`'s operators as returning `valarray<T>`, but [[valarray.syn#3]] leaves implementations an opening:

!!! std
    Any function returning a `valarray<T>` is permitted to return an object of another type, provided all the const member functions of `valarray<T>` other than `begin` and `end` are also applicable to this type.

    Any function returning `valarray<T>` may instead return another type, as long as the const member functions of `valarray<T>` other than `begin` and `end` also work on it ([[valarray.syn#3]]).

The same paragraph limits such a replacement type to at most two additional levels of template nesting over the deepest argument type; ¶4–¶5 require the implementation to provide every function that takes a `valarray` for the replacement type as well, and allow it to be used to construct or be assigned to `valarray` and the four slice proxies. This is a permission, not a requirement: an implementation may perfectly well return a plain `valarray<T>`.

libc++ in our tests uses this permission:

```cpp run title="valarray-type.cpp"
#include <cstdio>
#include <valarray>

template <class T>
void show() { std::puts(__PRETTY_FUNCTION__); }  // GCC/Clang extension

int main() {
  std::valarray<double> a(1.0, 4), b(2.0, 4), c(3.0, 4);
  auto e = a + b + c;
  show<decltype(e)>();
  std::valarray<double> x = e;             // computed only here
  std::printf("%zu %g\n", sizeof(e), x[0]);
}
```

Output in our tests (line breaks added for layout):

```text
void show() [T = std::__val_expr<std::_BinaryOp<std::plus<double>,
    std::__val_expr<std::_BinaryOp<std::plus<double>,
        std::valarray<double>, std::valarray<double>>>,
    std::valarray<double>>>]
40 6
```

The structure is the same as in `et.cpp`: `a + b` is a `_BinaryOp` node, wrapped in a `__val_expr`, which is exactly the two levels of nesting ¶3 allows. Reading libc++'s `<valarray>` shows that the general `_BinaryOp` stores subexpressions by value, while the partial specialization where both operands are `valarray` stores `const valarray<T>&`: the leaves-by-reference, nodes-by-value split from the right side of the previous section. So `auto e = make() + make();` dangles on libc++; see [[numarray]] for an example.

Since whether a replacement type is used is up to the implementation, code that depends on it is not portable. The most common case is a range-based for over the result of an operation; see Question 2.

## Modern alternatives

### ranges: views::zip_transform {{c++23}}

C++23's `views::zip_transform` takes a callable and several ranges and produces a view whose M-th element is the result of applying the callable to the M-th elements of the ranges ([[range.zip.transform.overview#1]]); it was added by [[P2321R2]]. Views are lazy already:

```cpp run title="zip-transform.cpp" ok
#include <cstdio>
#include <ranges>
#include <vector>

int main() {
  std::vector<double> a{1, 2, 3}, b{10, 20, 30}, c{100, 200, 300};
  auto sum3 = [](double x, double y, double z) { return x + y + z; };
  auto e = std::views::zip_transform(sum3, a, b, c);  // lazy: nothing computed yet
  std::vector<double> x(e.begin(), e.end());          // one loop
  std::printf("%g %g %g\n", x[0], x[1], x[2]);        // 111 222 333
}
```

At -O2 in our tests, `std::ranges::copy(views::zip_transform(…, a, b, c), x.begin())` also compiles to a vectorized loop with 8 `fadd.2d` per iteration and no function calls. It differs from hand-written expression templates in a few ways:

- The operation is written in a lambda rather than as `a + b + c`. No operators are overloaded, so there is no hijacking problem.
- With unequal lengths it takes the shortest, without an error.
- When an rvalue container is passed in, `views::all` moves it into an `owning_view` ([[range.all.general#2]]), so iterating `e` after `auto e = views::zip_transform(std::plus{}, make(1), make(2));` is safe; ASan reported nothing in our tests. With lvalues the view still only refers to them, and destroying the original container first still dangles.

### std::linalg {{c++26}}

`<linalg>` is a C++ interface to BLAS, with vectors and matrices represented as `mdspan` ([[linalg.overview#1]]). It overloads no operators; each operation is a function call, with the output passed as an argument:

```cpp
namespace la = std::linalg;
la::add(x, y, z);                          // z = x + y
la::add(la::scaled(2.0, x), y, z);         // z = 2x + y
la::matrix_product(A, B, C);               // C = AB; C must not overlap A or B
```

`scaled` and `transposed` return an `mdspan` with a different accessor or layout, and the scaling factor is applied only when an element is accessed. This part shares the idea of expression templates: don't copy the data, compute when it is used. libc++ in our tests has no `<linalg>` header, so the code above has not been compile-tested and carries no verdict. See [[linalg]] for details.

### Eigen

Eigen is the most widely used linear algebra library built on expression templates in C++. The code below is not part of standard C++ and only illustrates the design:

```cpp
Eigen::VectorXd a(n), b(n), c(n), x(n);
x = a + b + c;              // one fused loop
Eigen::MatrixXd A(n, n), B(n, n), C(n, n);
C = A * B;                  // evaluated into a temporary first, handling aliasing
C.noalias() = A * B;        // user guarantees no overlap; written directly into C
auto e = a + b;             // an expression object, not a vector
```

Its choices match the analysis above: subexpressions stored by value, matrices by reference; elementwise operations fused into one loop, matrix products evaluated into a temporary by default; the documentation specifically warns against using `auto` with expressions and suggests `.eval()` when needed. Eigen's expression types share their interface through a CRTP base; that technique is described in [[patterns/crtp]].

| | hand-written expression templates | `valarray` | `views::zip_transform` | `<linalg>` |
|---|---|---|---|---|
| Syntax | `x = a + b * c` | `x = a + b * c` | lambda + view | function calls |
| Fused into one loop | yes | up to the implementation | yes | one operation per call |
| Risk with `auto` | dangling | depends on the implementation | rvalues are held; lvalues can still dangle | n/a |
| Aliasing | handle it yourself | precondition ([[numarray]]) | handle it yourself | precondition |
| libc++ in our tests | available | available, uses expression templates | available | missing |

## When to use them

| Situation | Recommendation |
|---|---|
| One-off elementwise computations | a hand-written loop or `views::zip_transform`; no need for operator overloading |
| The public interface of a numerics library, where users write many `a + b * c` formulas | expression templates, or just use a mature library such as Eigen |
| Operations with cross-index dependencies (products, convolutions, assigning a transpose) | evaluate into a temporary first, or make non-overlap a precondition as `<linalg>` does |
| User code uses `auto` a lot | expression templates dangle easily; consider `[[clang::lifetimebound]]` on the interface, or provide an explicit `.eval()` |
| Debug build size and speed matter | expression templates are expensive at -O0; weigh that before using them |
| The shape of the expression is known only at run time | expression templates cannot do this; the shape must be fixed at compile time |

## Questions

!!! question "1"
    In `et.cpp`, are the results of `x = x + x;` and `x = a + x * x;` correct? If you add a node `Shift<E>` to `la` whose `operator[](i)` returns `e[i + 1]` (0 for the last element), what about `x = shift(x);`?

<details markdown="1">
<summary>Answer</summary>

The first two are correct: each `x[i]` depends only on `x[i]` at the same index, and the assignment loop has read every value it needs before writing `x[i]`.

`x = shift(x)` also happens to be correct, because writing `x[i]` reads `x[i + 1]`, which has not been overwritten yet. But a shift in the other direction (`operator[](i)` returns `e[i - 1]`, 0 for element 0) goes wrong: after `x[0]` is written, computing `x[1]` reads the new `x[0]`, and so on, so every element ends up 0. Whenever an output element depends on inputs at other indices, you have to analyze the loop direction case by case; the safest approach is to evaluate into a temporary first.
</details>

!!! question "2"
    The code below fails to compile with libc++ in our tests, reporting `no viable 'begin' function available`. Is this a libc++ bug?

    ```cpp
    std::valarray<double> a(1.0, 3), b(2.0, 3);
    for (double v : a + b) std::printf("%g\n", v);
    ```

<details markdown="1">
<summary>Answer</summary>

No. A range-based for needs `begin` and `end`, and these are provided only for `valarray<T>` itself: as member functions in the current draft ([[valarray.range]], new wording after C++23), and as the older non-member `std::begin` and `std::end` overloads in libc++ in our tests. [[valarray.syn#3]] allows `a + b` to return another type and explicitly excludes `begin` and `end` from the members the replacement type must support. libc++ returns `__val_expr<…>`, which has neither a member `begin` nor a usable non-member overload. On an implementation that returns `valarray<double>` the code compiles, so it is not portable. Writing `for (double v : std::valarray<double>(a + b))` works on every implementation.
</details>

!!! question "3"
    What is the risk of changing `Vec::assign` in `et.cpp` to loop up to `e.size()` instead of `d_.size()`? How does the standard `valarray` handle unequal lengths?

<details markdown="1">
<summary>Answer</summary>

`Binary::size()` returns only the length of the left operand. If the left side is longer than the right, `e[i]` reads the right operand out of bounds; if the destination is shorter than the expression, `d_[i]` writes out of bounds. Both are UB. `et.cpp`'s `assign`, which loops over the destination length, only moves the problem elsewhere; a real library either checks the lengths or makes equal lengths a precondition. `valarray` chose the latter: operations and assignments between two arrays require equal lengths, otherwise the behavior is undefined (see [[numarray]]).
</details>
