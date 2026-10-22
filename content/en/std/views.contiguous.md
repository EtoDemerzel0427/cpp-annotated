---
title: "Contiguous access: span"
summary: "std::span is a pointer plus a length: how it allows only const-adding element conversions, when its constructors are explicit, how it is constructed from temporaries, how subviews and subscripts check bounds, why as_bytes is legal, and why it has no operator==."
updated: 2026-10-19
---

!!! tldr
    - `span<T>` is a pointer plus a length; the length of `span<T, N>` is the compile-time constant N, and implementations usually store just a pointer. It does not own its elements and dangles once the storage it views is freed or moved.
    - Element types may only gain const: `span<int>` can become `span<const int>`, but an array of `Derived` cannot become `span<Base>`.
    - A constructor is `explicit` only when it turns a run-time length into a static extent, for example `vector` to `span<int, 4>`; whether the lengths match is checked at run time by a hardened precondition.
    - `span<const T>` can be constructed from a temporary `vector`, which is convenient for passing arguments; stored in a variable it dangles. `span<T>` (non-const) refuses construction from temporaries.
    - Bounds checks for subscripts, `front`, `back` and subviews are hardened preconditions; C++26's `at()` throws `out_of_range` when out of bounds. `span` has no `operator==`.

## A pointer plus a length

```cpp run title="span-basics.cpp" ok
#include <cstdio>
#include <span>
#include <vector>

void print(std::span<const int> s) {           // one parameter instead of (const int* p, size_t n)
  for (int x : s) std::printf("%d ", x);
  std::puts("");
}

void fill4(std::span<int, 4> s) {              // the length is in the type: exactly 4 elements
  for (int& x : s) x = 7;
}

int main() {
  int raw[4] = {1, 2, 3, 4};
  std::vector<int> v{5, 6, 7};
  print(raw);
  print(v);
  print(std::span(v).first(2));                // subview: 5 6
  fill4(raw);                                  // OK: the array length is known to be 4 at compile time
  print(raw);
}
```

`std::span<T, Extent>` ({{c++20}}, [[P0122R7]]) gives a type name to the `(T* p, size_t n)` common in C interfaces. Compared with a raw pointer plus a length, it has three advantages:

- The length travels with the pointer, so it cannot be lost or mismatched as arguments are passed down through layers.
- The length can be a compile-time constant. The length of `span<int, 4>` is written into the type, the implementation need only store a pointer, and subviews of the wrong length are rejected at compile time.
- Element type conversions may only add const. Raw pointers allow `Base* p = derived_array;`, after which stepping by `sizeof(Base)` goes out of alignment; `span` blocks this at the type level.

The second template argument `Extent` is called the **extent**, the number of elements. Its default is `dynamic_extent`, meaning the length is determined only at run time. `dynamic_extent` is defined as `numeric_limits<size_t>::max()`, and `mdspan` uses the same constant ([[views]]). Below, a `span` whose `Extent` is `dynamic_extent` is said to have a dynamic extent, and the rest a static extent.

## Object model ([span.overview])

¶1 A `span` is a view over a contiguous sequence of objects, the storage of which is owned by some other object. The destructor of `span` does nothing, and the lifetime of the storage is the caller's responsibility.

¶2 All member functions of `span` have constant time complexity. That is why it cannot provide an element-by-element `operator==`; see below.

¶3 `span<ElementType, Extent>` is a trivially copyable type ([[g:trivially-copyable-type]], [[basic.types.general]]). The copy constructor and destructor are trivial, so under the common x86-64 and AArch64 ABIs a dynamic-extent `span` passed by value goes straight into two registers, as cheap as passing two raw arguments.

¶4 `ElementType` must be a complete object type that is not an abstract class:

- `span<void>`, `span<int&>` and `span<int()>` are all invalid; they are not object types. libc++ (Clang 23) fails to compile `span<int&>` outright.
- `span<int[3]>` is fine, since arrays are object types. `int m[2][3]` converts directly to `span<int[3]>`, each element being a row.

### A static extent stores only a pointer

The wording uses two exposition members, `data_` and `size_`. But they are exposition only; with a static extent `size()` always equals `Extent`, and the implementation need not store it:

```cpp run title="span-sizeof.cpp" ok
#include <cstdio>
#include <ranges>
#include <span>
#include <type_traits>

int main() {
  // libc++ (64-bit) prints: 16 8 8
  std::printf("%zu %zu %zu\n", sizeof(std::span<int>), sizeof(std::span<int, 4>),
              sizeof(std::span<int, 0>));

  static_assert(std::is_trivially_copyable_v<std::span<int>>);   // [span.overview] ¶3
  static_assert(std::ranges::view<std::span<int>>);
  static_assert(std::ranges::borrowed_range<std::span<int>>);
  static_assert(!std::equality_comparable<std::span<int>>);      // no operator==
}
```

The standard does not specify `sizeof`, but not paying storage for the length with a static extent is the design intent, and mainstream implementations all do it.

### Invalidation comes from outside (¶5)

¶5 Any operation that invalidates a pointer in the range `[s.data(), s.data() + s.size())` invalidates pointers, iterators and references to elements of `s`.

`span` itself has no modifying operations; all of its invalidation comes from the underlying storage. The most common case is a `vector` reallocating:

```cpp run title="span-invalidation.cpp" ub
#include <span>
#include <vector>

int main() {
  std::vector<int> v{1, 2, 3};
  std::span<int> s = v;
  v.push_back(4);       // if this reallocates, the storage s points to is freed
  return s[0];          // UB: the span does not know the vector has moved
}
```

In our tests AddressSanitizer reports heap-use-after-free. For which container operations invalidate pointers, see [[container.requirements]] and [[vector]]. The hardened check of `operator[]` compares only the index with `size()` and can do nothing about dangling, so this code is UB in a hardened implementation as well.

### Member types

- `element_type` is `ElementType` and may carry cv-qualifiers; `value_type` removes them. `span<const int>::value_type` is `int`; as with containers, `value_type` is the type you get when copying an element out.
- `size_type` is `size_t`, `difference_type` is `ptrdiff_t`, and `extent` is a static data member with the value `Extent`.
- `iterator` is implementation-defined, and `const_iterator` is `std::const_iterator<iterator>`. C++20's `span` had no `cbegin`: the iterators of a `const span` are still writable, and a `cbegin` returning a writable iterator would be misleading. It was added only after C++23 introduced `std::const_iterator` ([[P2278R4]]).

## Constructors ([span.cons])

First the overview. The last column applies only to static extents; for a dynamic-extent `span`, every constructor can be called implicitly.

| Constructor | Paragraphs | Key constraints | Hardened precondition | explicit with a static extent |
|---|---|---|---|---|
| `span()` | ¶1–¶2 | `Extent` is 0 or `dynamic_extent` | None | N/A |
| `span(It first, size_type count)` | ¶3–¶7 | `It` is a contiguous iterator; only const may be added | `count == extent` | Yes |
| `span(It first, End last)` | ¶8–¶12 | Same; `End` is a sized sentinel for `It` and not convertible to `size_t` | `last - first == extent` | Yes |
| Built-in array, `array<T, N>&`, `const array<T, N>&` | ¶13–¶15 | `N == extent` or dynamic; only const may be added | None | No |
| `span(R&& r)` | ¶16–¶20 | Contiguous and sized; a borrowed range or const elements; not a `span`, `array` or built-in array | `ranges::size(r) == extent` | Yes |
| `span(const span<U, N>&)` | ¶22–¶26 | Compatible extents; only const may be added | `s.size() == extent` | Only when the source is dynamic and the target static |

In library clauses, a function whose *Constraints* are not met does not participate in overload resolution; violating *Preconditions* is UB; violating *Hardened preconditions* terminates the program in a [[g:hardened-implementation|hardened implementation]] and is also UB in other implementations ([[structure.specifications]]).

### Default construction (¶1–¶2)

¶1 There is a default constructor only when `Extent` is `dynamic_extent` or 0. A `span<int, 4>` that promises exactly 4 elements cannot be conjured out of nothing. ¶2 The result of default construction satisfies `size() == 0 && data() == nullptr`.

### Only const may be added (¶3, ¶8, ¶13, ¶16, ¶22)

Every constructor has a constraint of the following form, where `U` is the source element type:

```cpp
is_convertible_v<U(*)[], element_type(*)[]>
```

Why not simply write `is_convertible_v<U*, element_type*>`? Because ordinary pointers allow derived-to-base conversion: a `Derived*` converts to `Base*`, but treating an array of `Derived` as an array of `Base` and stepping by `sizeof(Base)` is UB. Pointers to arrays allow only qualification conversions ([[conv.qual]]): `int(*)[]` converts to `const int(*)[]`, but `Derived(*)[]` does not convert to `Base(*)[]`. A note in the wording states the intent:

!!! std
    The intent is to allow only qualification conversions of the iterator reference type to `element_type`.

The note itself is not normative; the constraint's effect comes from the `is_convertible_v` expression.

### Iterator plus count, iterator plus sentinel (¶3–¶12)

¶4 and ¶9 give the preconditions: `[first, first + count)` or `[first, last)` is a valid range, and `It` models `contiguous_iterator` rather than merely satisfying it syntactically. Passing an iterator that satisfies the concept syntactically but is not actually contiguous is UB.

¶5 and ¶10 give the hardened preconditions: with a static extent, the length must equal `extent` exactly.

¶8.4 requires that `End` not be convertible to `size_t`. That way an integral second argument in `span(first, n)` is always taken as the length and never deduced as the sentinel type `End`; see Question 3 for why.

¶12 The `(It, End)` version throws whatever `last - first` throws. Subtraction on a user-defined iterator may throw, so this constructor is not `noexcept`.

### Built-in arrays and std::array (¶13–¶15)

¶13.1 requires `extent == dynamic_extent || N == extent`. When the length is wrong, the constructor does not participate in overload resolution, and no run-time check is needed. So these three constructors are never `explicit`.

¶14's Note 4 explains why the built-in array version is written `type_identity_t<element_type> (&arr)[N]`: `type_identity_t` puts the parameter in a non-deduced context, so class template argument deduction does not go through this constructor and deduction is left to dedicated deduction guides.

```cpp run title="span-extent-explicit.cpp" error
#include <array>
#include <span>
#include <vector>

int raw[4];
std::array<int, 4> arr;
std::vector<int> vec(4);

std::span<int, 4> a = raw;   // OK: the array constructor is not explicit
std::span<int, 4> b = arr;   // OK
std::span<int, 4> c{vec};    // OK: direct-initialization can call an explicit constructor
std::span<int, 4> d = vec;   // error: the range constructor is explicit(extent != dynamic_extent)
std::span<int, 3> e = raw;   // error: N == extent does not hold, so the constructor does not participate
std::span<int, 4> f;         // error: default construction requires Extent to be 0 or dynamic_extent
```

`vector` to `span<int, 4>` has to be explicit because the length of a `vector` is a run-time value, and the compiler cannot verify that it is exactly 4. Writing an `explicit` conversion means the caller vouches for the length; the actual check is left to the hardened precondition.

### Construction from a range (¶16–¶20)

This is the most general constructor and the easiest to get wrong. The constraints of ¶16:

- ¶16.1 `R` satisfies `ranges::contiguous_range` and `ranges::sized_range`. `deque` and `list` are not contiguous, and the iterators of `vector<bool>` are not contiguous iterators, so all of them are excluded.
- ¶16.2 Either `R` satisfies `ranges::borrowed_range` or `element_type` is const.
- ¶16.3–¶16.5 `R` is not a `span`, an `array` or a built-in array; those have dedicated constructors.
- ¶16.6 Only const may be added.

¶16.2 has to be read together with borrowed ranges. A **borrowed range** ([[g:borrowed-range]]) is a range whose iterators do not depend on the lifetime of the range object itself; `span` and `string_view` are, `vector` is not. `R&&` is a forwarding reference: passing an lvalue `vector<int>& v` deduces `R` as `vector<int>&`, and by the definition of `borrowed_range` in [[range.range]], lvalue reference types always satisfy it. So this constraint really restricts only rvalue arguments:

- `void f(span<const int>)` can accept `f(make_vector())`. The temporary lives until the end of the full-expression, so it is safe while `f` runs.
- Constructing a `span<int>` from a temporary `vector` is almost always a mistake; writing into an object about to be destroyed is pointless, so it is rejected outright.

```cpp run title="span-range-ctor.cpp" error
#include <span>
#include <vector>

std::vector<int> make();
void read(std::span<const int>);
void write(std::span<int>);

void f() {
  read(make());                   // OK: elements are const, so construction from an rvalue vector is allowed
  write(make());                  // error: an rvalue vector is not a borrowed range, and the elements are not const
  std::vector<bool> vb(8);
  read(std::span<const bool>(vb)); // error: vector<bool> is not a contiguous_range
}
```

¶17 turns the syntactic requirements of ¶16 into semantic ones (models) as preconditions; ¶18 is the length check for static extents; ¶19 initializes with `ranges::data(r)` and `ranges::size(r)`; ¶20 the constructor throws whatever those two calls throw.

### Copying and conversion between spans (¶21–¶27)

¶21, ¶27 Copy construction and copy assignment are both `= default`, `noexcept`, trivial operations; the result has the same pointer and length as the source.

¶22–¶26 are the converting constructor from `span<U, N>` to `span<T, M>`:

- ¶22.1 Compatible extents: either one is dynamic, or the two are equal. The constructor from `span<int, 4>` to `span<int, 3>` does not participate in overload resolution.
- ¶22.2 Only const may be added. `span<int>` can become `span<const int>`, not the other way round.
- ¶23 When the target has a static extent, the hardened precondition requires `s.size() == extent`.
- ¶26 The `explicit` condition is `extent != dynamic_extent && OtherExtent == dynamic_extent`. Only dynamic-to-static needs to be explicit; every other direction converts implicitly.

```cpp run title="span-conversions.cpp" error
#include <span>

struct Base { int x; };
struct Derived : Base { int y; };

int buf[4];
Derived d[3];
std::span<int>    dyn = buf;
std::span<int, 4> fix = buf;

std::span<const int> c1 = dyn;   // OK: int to const int is a qualification conversion
std::span<int>       a  = fix;   // OK: static to dynamic, implicit
std::span<int, 4>    b{dyn};     // OK: dynamic to static must be explicit; hardened precondition dyn.size() == 4
std::span<int>       c2 = c1;    // error: drops const
std::span<Base>      e  = d;     // error: Derived(*)[] does not convert to Base(*)[]
std::span<int, 4>    g  = dyn;   // error: dynamic to static is explicit
std::span<int, 3>    h{fix};     // error: the two static extents differ, so the constructor does not participate
```

### No initializer_list constructor

```cpp run title="span-init-list.cpp" error
#include <initializer_list>
#include <span>

void f(std::span<const int>);

void g() {
  std::initializer_list<int> il{1, 2, 3};
  f(il);          // OK: initializer_list is a contiguous, sized range with const elements
  f({1, 2, 3});   // error: the current draft has no initializer_list constructor
}
```

During the C++26 cycle, [[P2447R6]] added a `span(initializer_list<value_type>)` constructor to `span` so that `f({1, 2, 3})` would compile. The [span.cons] of the current draft no longer has this constructor, and [[version.syn]] has no corresponding feature-test macro either.

The constructor had two problems. First, in `span<const int> s = {1, 2, 3};` the backing array of the `initializer_list` is a temporary destroyed at the end of the statement ([[dcl.init.list]]); it is safe only as a function argument. Second, brace initialization prefers `initializer_list` constructors ([[over.match.list]]), so `span<const std::any> s{ptr, n}`, which used to call the pointer-plus-count constructor, would become a list of two `any`s.

An explicitly written `initializer_list` object can still be converted to `span<const int>` through the range constructor of ¶16, as with `f(il)` in the example.

## Deduction guides ([span.deduct])

| Arguments | Deduced type |
|---|---|
| `(It, EndOrSize)` | `span<remove_reference_t<iter_reference_t<It>>, maybe-static-ext<EndOrSize>>`; ¶1 requires `It` to be a contiguous iterator |
| `T (&)[N]` | `span<T, N>` |
| `array<T, N>&` | `span<T, N>` |
| `const array<T, N>&` | `span<const T, N>` |
| `R&&` | `span<remove_reference_t<range_reference_t<R>>>`, dynamic extent; ¶2 requires `R` to be a contiguous range |

*maybe-static-ext* is defined in [span.syn] and is exposition only. If a type `T` has, like `integral_constant`, a static member `T::value` of an integral type other than `bool`, then *maybe-static-ext*`<T>` is that value; otherwise it is `dynamic_extent`. So an ordinary integer as the second argument gives a dynamic extent, while a `std::integral_constant<size_t, 2>` or C++26's `std::cw<2uz>` gives the static extent 2.

Deduction from a range always gives a dynamic extent, even when the range's length is known at compile time. A `const array` deduces `span<const T, N>`: the const passes from the container to the elements.

```cpp run title="span-ctad.cpp" ok
#include <array>
#include <span>
#include <type_traits>
#include <utility>
#include <vector>

int raw[4];
std::array<int, 3> arr;
const std::array<int, 3> carr{};
std::vector<int> vec(5);

std::span a = raw;                     // span<int, 4>
std::span b = arr;                     // span<int, 3>
std::span c = carr;                    // span<const int, 3>
std::span d = vec;                     // span<int>
std::span e{vec.data(), 2};            // span<int>: 2 is a plain int, so the extent is dynamic
std::span f{vec.data(), std::integral_constant<std::size_t, 2>{}};  // span<int, 2>
std::span g{raw + 0, std::cw<2uz>};    // span<int, 2>

static_assert(std::is_same_v<decltype(a), std::span<int, 4>>);
static_assert(std::is_same_v<decltype(b), std::span<int, 3>>);
static_assert(std::is_same_v<decltype(c), std::span<const int, 3>>);
static_assert(std::is_same_v<decltype(d), std::span<int>>);
static_assert(std::is_same_v<decltype(e), std::span<int>>);
static_assert(std::is_same_v<decltype(f), std::span<int, 2>>);
static_assert(std::is_same_v<decltype(g), std::span<int, 2>>);

int main() {}
```

## Subviews ([span.sub])

`first`, `last` and `subspan` each come in two versions: one with the length as a template argument and one with the length as a function argument.

| Function | Paragraphs | *Mandates* (compile time) | Hardened precondition (run time) | Extent of the result |
|---|---|---|---|---|
| `first<Count>()` | ¶1–¶3 | `Count <= Extent` | `Count <= size()` | `Count` |
| `last<Count>()` | ¶4–¶6 | `Count <= Extent` | `Count <= size()` | `Count` |
| `subspan<Offset, Count>()` | ¶7–¶10 | `Offset <= Extent`, and `Count` is dynamic or `Count <= Extent - Offset` | The same expressions with `Extent` replaced by `size()` | See ¶10 |
| `first(count)` | ¶11–¶12 | None | `count <= size()` | Dynamic |
| `last(count)` | ¶13–¶14 | None | `count <= size()` | Dynamic |
| `subspan(offset, count)` | ¶15–¶16 | None | `offset <= size()`, and `count` is dynamic or `count <= size() - offset` | Dynamic |

If a *Mandates* is not met, the program is ill-formed. With a static extent, `Extent` is the real length and out-of-bounds subviews are stopped at compile time. With a dynamic extent, `Extent` is the maximum value of `size_t`, the *Mandates* is almost always met, and out-of-bounds subviews can only be caught by the run-time hardening check.

¶10 The extent of the result of `subspan<Offset, Count>()`: `Count` if given; otherwise `Extent - Offset` if the source is static; otherwise dynamic. ¶8 writes `Count <= size() - Offset` rather than `Offset + Count <= size()`, because the latter gives the wrong answer when the addition overflows; checking `Offset <= size()` first makes the subtraction safe from overflow.

```cpp run title="span-subviews.cpp" ok
#include <span>
#include <type_traits>

int buf[8];
std::span<int, 8> s8 = buf;
std::span<int>    sd = buf;

// template versions: keep a static extent where possible
static_assert(std::is_same_v<decltype(s8.first<3>()),      std::span<int, 3>>);
static_assert(std::is_same_v<decltype(s8.subspan<2>()),    std::span<int, 6>>);
static_assert(std::is_same_v<decltype(s8.subspan<2, 3>()), std::span<int, 3>>);
static_assert(std::is_same_v<decltype(sd.subspan<2>()),    std::span<int>>);    // dynamic source and no Count given
static_assert(std::is_same_v<decltype(sd.subspan<2, 3>()), std::span<int, 3>>);
// function-argument versions: the result always has a dynamic extent
static_assert(std::is_same_v<decltype(s8.first(3)),        std::span<int>>);

int main() {}
```

```cpp run title="span-subview-mandates.cpp" error
#include <span>

int buf[8];
std::span<int, 8> s8 = buf;
std::span<int>    sd = buf;

auto a = s8.first<9>();       // error: Mandates: Count <= Extent
auto b = s8.subspan<6, 3>();  // error: Mandates: Count <= Extent - Offset
auto c = sd.first<9>();       // compiles (Extent is dynamic_extent); violates a hardened precondition at run time
```

## Observers and element access ([span.obs], [span.elem])

[span.obs] ¶1–¶3 `size()` returns *size_*, `size_bytes()` returns `size() * sizeof(element_type)`, and `empty()` is equivalent to `size() == 0`; all three are `noexcept`. A `span` must point to a sequence of objects that really exists, and the size of any object can be represented by `size_t`, so `size_bytes()` cannot overflow on a valid `span`.

[span.elem] is a focal point of C++26 standard library hardening:

| Member | Paragraphs | When out of bounds |
|---|---|---|
| `operator[](idx)` | ¶1–¶3 | Hardened precondition `idx < size()`; {{ub}} in a non-hardened implementation |
| `at(idx)` {{c++26}} | ¶4–¶5 | Throws `out_of_range`; this is specified behavior, not a precondition |
| `front()`, `back()` | ¶6–¶11 | Hardened precondition `!empty()` |
| `data()` | ¶12 | Always callable; returns *data_* |

`at()` was added by [[P2821R5]]. In C++20 `span` deliberately did not provide `at()`, on the grounds that a low-overhead view should not involve exceptions; later, interface consistency with the other contiguous containers was judged more important. A freestanding implementation (one without operating-system support) must also provide `span`, but the throwing `at()` is *freestanding-deleted* there.

¶3 says `operator[]` *Throws*: Nothing, yet the function is not marked `noexcept`. The standard library generally does not put `noexcept` on functions with preconditions, so that implementations or test frameworks can report precondition violations by throwing.

```cpp run title="span-hardening.cpp" flags="-std=c++2c -D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_DEBUG"
#include <cstdio>
#include <span>
#include <stdexcept>

int main() {
  int buf[4] = {1, 2, 3, 4};
  std::span<int> s = buf;
  try {
    (void)s.at(4);                        // C++26: out of bounds throws out_of_range
  } catch (const std::out_of_range&) {
    std::puts("at(4) threw out_of_range");
  }
  std::printf("%d\n", s[4]);              // violates a hardened precondition: terminates in a hardened implementation, UB otherwise
}
```

How libc++ (Clang 23) behaves:

- Without any macro, the Homebrew build of libc++ is unhardened by default, and `s[4]` silently reads out of bounds, printing a garbage value.
- With `-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_DEBUG`, it prints an assertion failure message for `__idx < size()` and then aborts.
- With `_LIBCPP_HARDENING_MODE_FAST`, the same check is done, but it terminates directly with a trap instruction and no message, for minimal overhead.

libc++ also checks in the `(It, count)` constructor that the pointer is non-null when `count != 0`. This goes beyond what the standard requires without contradicting it: violating a precondition is UB anyway, and the implementation may report it however it likes.

## Iterators ([span.iterators])

¶1 `iterator` models `contiguous_iterator` and meets the *Cpp17RandomAccessIterator* and constexpr iterator requirements. It need not be `T*`: libc++ uses a wrapper type, and with the bounded-iterator ABI option enabled it switches to a type with built-in bounds checking. Code should not assume the iterator is a pointer.

¶2 All requirements on container iterators in [[container.reqmts]] apply to `span::iterator` as well.

¶3–¶6 `begin()`, `end()`, `rbegin()` and `rend()` have the usual definitions, and `begin() == end()` for an empty `span`. These functions are all `const` and `noexcept`, and since the const of `span` is shallow, `begin()` on a `const span<int>` still returns a writable `iterator`.

[span.syn] specializes both `ranges::enable_view` and `ranges::enable_borrowed_range` to `true`, so `span` is both a `ranges::view` and a borrowed range. Calling a ranges algorithm on an rvalue `span` yields a usable iterator:

```cpp run title="span-borrowed.cpp" ok
#include <algorithm>
#include <span>
#include <type_traits>
#include <vector>

std::vector<int> v{1, 2, 3};

int main() {
  // rvalue span: a real iterator
  auto it = std::ranges::find(std::span(v), 2);
  static_assert(std::is_same_v<decltype(it), std::span<int>::iterator>);
  // rvalue vector: ranges::dangling
  auto it2 = std::ranges::find(std::vector<int>{1, 2, 3}, 2);
  static_assert(std::is_same_v<decltype(it2), std::ranges::dangling>);

  const std::span<int> s = v;
  s[0] = 42;            // OK: const applies to the span itself, not to the elements
  return *it + v[0] - 44;
}
```

## Views of object representation ([span.objectrep])

¶1–¶2 `as_bytes(s)` is equivalent to

```cpp
return R{reinterpret_cast<const byte*>(s.data()), s.size_bytes()};
```

¶3–¶4 `as_writable_bytes(s)` is analogous, with result `span<byte>`. Both reject volatile elements, and `as_writable_bytes` also rejects const elements. The extent of the result is `sizeof(ElementType) * Extent`, so a static extent stays static after conversion to bytes.

```cpp run title="span-as-bytes.cpp" ok
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <span>
#include <type_traits>

struct Pixel { std::uint8_t r, g, b, a; };

int main() {
  Pixel img[2] = {{1, 2, 3, 4}, {5, 6, 7, 8}};
  std::span<Pixel, 2> px = img;

  auto ro = std::as_bytes(px);              // span<const byte, 8>: the static extent converted to bytes
  static_assert(std::is_same_v<decltype(ro), std::span<const std::byte, 8>>);
  for (std::byte b : ro) std::printf("%d ", std::to_integer<int>(b));
  std::puts("");

  auto rw = std::as_writable_bytes(px);     // span<byte, 8>
  rw[0] = std::byte{42};                    // modifies the object representation of a Pixel through a byte glvalue
  std::printf("%d\n", img[0].r);            // 42
}
```

The legitimacy of these two functions comes from the core language:

1. The **object representation** of an object of type `T` is the sequence of `sizeof(T)` `unsigned char` objects starting at it ([[basic.types.general]], [[g:object-representation]]). Array elements have no gaps between them, so a whole `span<T>` covers exactly `size_bytes()` contiguous bytes.
2. Accessing the stored value of any object through a glvalue of type `std::byte` is allowed ([[basic.lval#11]], [[g:type-accessible]]) and does not violate strict aliasing.
3. `reinterpret_cast`ing an object pointer to `const byte*` is a valid pointer conversion ([[expr.reinterpret.cast]]).

Volatile is excluded because the elements of `span<const byte>` are not volatile. If the conversion were allowed, volatile accesses would silently become ordinary accesses and lose their volatile semantics.

```cpp run title="span-as-bytes-error.cpp" error
#include <span>

const int ci[2] = {};
volatile int vi[2];
auto a = std::as_writable_bytes(std::span(ci));  // error: elements are const
auto b = std::as_bytes(std::span(vi));           // error: elements are volatile
```

!!! warning "There is no function from bytes to objects"
    The standard provides only views from objects to bytes; there is no function turning a `span<byte>` into a `span<T>`. To use a received run of bytes as `T` objects, you need to create objects in that storage: with `std::start_lifetime_as_array` ([[obj.lifetime]]), or by `memcpy` into a real `T` object. Doing `reinterpret_cast<T*>(bytes.data())` directly and then accessing it is {{ub}}, since there is no `T` object there, unless implicit object creation happens to have created one ([[intro.object]]).

## Why there is no operator==

`span` in early C++20 drafts had element-wise `==` and `<`, later removed by [[P1085R2]]. `span` has two reasonable but mutually contradictory equality semantics:

- Compare elements: consistent with `vector` and `string_view`. But this is not constant time, contradicting ¶2. And since the const of `span` is shallow and its elements writable, modifying an element after copying a `span` changes the original `span` as well, which is not value semantics.
- Compare pointer and length: consistent with its identity as just a pointer plus a length, but two arrays with the same contents would compare unequal, the opposite of `string_view`.

In the end the choice was to provide neither and let callers state their intent: compare contents with `std::ranges::equal(a, b)`; compare identity with `a.data() == b.data() && a.size() == b.size()`.

## Common misconceptions

!!! pitfall "Constructing a span from a temporary and storing it in a variable"
    ¶16.2 allows a `span` with const elements to be constructed from an rvalue range for safe situations like function arguments. Stored in a variable, it dangles:

```cpp run title="span-dangling.cpp" ub
#include <span>
#include <vector>

std::vector<int> make() { return {1, 2, 3}; }

int main() {
  std::span<const int> s = make();  // compiles: the elements are const, which the constraint allows
  return s[0];                      // UB: the temporary vector was destroyed at the end of the statement
}
```

Clang 23 warns about this line by default with `-Wdangling-gsl`: Clang knows that standard library types like `vector` and `span` are owners and non-owning pointer classes respectively, and can spot the pattern of a pointer class constructed from a temporary owner. `std::span<const int, 3> s = std::array{1, 2, 3};` is the same mistake, and AddressSanitizer reports stack-use-after-scope. For the lifetime rules of temporaries, see [[class.temporary]].

!!! pitfall "A static-extent span truncates or pads"
    `span<int, 4>{v.data(), n}` and `span<int, 4>{v}` both require the run-time length to be exactly 4 (¶5, ¶18); they neither truncate nor pad. If you only require at least 4 elements, write `span<int>(v).first<4>()`; `first<4>()` only requires `4 <= size()`.

!!! pitfall "const span<T> is read-only"
    `const` qualifies the `span` object, that is, the pointer and length; the elements are writable all the same. For read-only access write `span<const T>`. A parameter written as `const span<T>&` is neither read-only nor faster; passing `span<const T>` by value is the right way.

## History

!!! history
    - C++20: `span` enters the standard ([[P0122R7]]). Changes before finalization: the comparison operators were removed by [[P1085R2]], the length type changed from the signed `index_type` to `size_t`, and `cbegin` and friends were removed.
    - C++23: `span` is required to be trivially copyable; `cbegin` and friends return, with `const_iterator` defined as `std::const_iterator<iterator>` ([[P2278R4]]).
    - C++26: `at()` added ([[P2821R5]]); the deduction guides support integral constant wrappers such as `std::cw<N>` through *maybe-static-ext*; the length checks of subscripts, `front`, `back`, subviews and static-extent construction become hardened preconditions. An `initializer_list` constructor ([[P2447R6]]) was added at one point but no longer exists in the current draft.

## Questions

!!! question "Question 1: which of these calls compile?"
    ```cpp
    std::vector<int> v(4);
    void f(std::span<int, 4>);
    f(v);
    f(std::span<int, 4>(v));
    f(std::span(v).first<4>());
    ```

<details markdown="1">
<summary>Answer</summary>

- `f(v)` is ill-formed. Initializing the parameter is copy-initialization, which needs an implicit conversion, and the range constructor is `explicit` with a static extent.
- `f(std::span<int, 4>(v))` works. A functional cast is direct-initialization and can call an `explicit` constructor; at run time the hardened precondition of ¶18 checks `v.size() == 4`.
- `f(std::span(v).first<4>())` works. Deduction gives `span<int>`, `first<4>()` returns `span<int, 4>` ([span.sub] ¶3), and at run time `4 <= size()` is checked. It is looser than the previous line: it works even if `v` has 10 elements.

</details>

!!! question "Question 2: which rvalue ranges can construct a `span<int>`?"
    `span<const int>` can be constructed from an rvalue `std::vector<int>`, `span<int>` cannot. Which rvalue ranges can construct a `span<int>`?

<details markdown="1">
<summary>Answer</summary>

Any rvalue that is contiguous, sized and a borrowed range (¶16.2). Examples in the standard library are `std::ranges::subrange<int*>` and `std::ranges::ref_view<std::vector<int>>`. `std::ranges::owning_view<std::vector<int>>` does not qualify: it owns the underlying `vector` and is not a borrowed range. An rvalue `span<int>` is excluded from the range constructor by ¶16.3, but it uses the copy constructor or the converting constructor of ¶22 instead, so it works too. For a custom contiguous view to join this group, specialize `ranges::enable_borrowed_range` ([[range.range#6]]).

</details>

!!! question "Question 3: why does `span(It, End)` need ¶8.4?"
    `span(It, End)` has a constraint that `End` is not convertible to `size_t`. Why does `span(It, size_type)` not need a symmetric constraint?

<details markdown="1">
<summary>Answer</summary>

When the second argument is an integer, both constructors may be viable: `(It, size_type)` through an integral conversion, and `(It, End)` by deducing the integer type as `End`. If some iterator type happened to accept an integer as a sized sentinel, the call would choose the template version, because a deduced exact match beats one requiring a conversion. ¶8.4 removes any `End` convertible to `size_t` from consideration, so an integral second argument always means the length. The reverse direction needs no constraint, because `size_type` is a fixed type that never matches an iterator sentinel.

</details>
