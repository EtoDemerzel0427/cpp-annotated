---
title: Pack indexing (P2662)
summary: C++26 uses Ts...[N] and args...[N] to get the Nth type or element of a pack directly. How much compile time the earlier recursive templates, detours through tuple and inheritance-based deduction cost, why the syntaxes and library approaches the proposal compared lost out, why negative indices and deduction were excluded, and how unnamed T...[n] parameters change meaning as a result.
tags: pack indexing, variadic templates, pack expansion, template metaprogramming, compile time, proposal, C++26
group: C++26
updated: 2026-10-19
---

!!! tldr
    - Before C++26, getting the Nth type of a pack took tricks like recursive specialization, `std::tuple_element`, or inheritance plus deduction, and getting the Nth argument took recursive calls or packing into a `tuple` first. In our measurements, the recursive approach took 3 seconds to fetch every one of 256 types, while pack indexing took under 0.1 seconds.
    - [[P2662R3]] introduces `Ts...[N]` (giving a type) and `args...[N]` (giving an expression). The `...` shows a pack is involved, the `[]` shows it is a subscript; writing `P[i]` directly would clash with subscripting each array element.
    - The proposal did not adopt a library approach such as `std::nth_type`: library approaches need a number of instantiations that grows linearly with the index, need three separate spellings for types, values and templates, and offer no path to slicing.
    - The index must be in `[0, sizeof...(P))`; negative numbers do not count from the end. Pack indexing is a non-deduced context, and only the name of a pack can be indexed, not an arbitrary pattern.
    - The cost is one Annex C entry: in C++23 an unnamed function parameter pack `T... [1]` (a set of array parameters) is now parsed as pack indexing.

## How hard it is to get the Nth element

A **pack** ([[g:pack|pack]]) is an entity such as a template parameter pack or function parameter pack that holds zero or more elements, and the name of a pack may only appear in a **pack expansion** ([[g:pack-expansion|pack expansion]]), such as `f(args...)` ([[temp.variadic#5]], [[temp.variadic#8]]). When C++11 introduced variadic templates, there were only two things you could do with a pack: expand it as a whole, and get its length with `sizeof...`. Subscripting, the most basic sequence operation, was not among them.

So getting the Nth type meant taking a detour. Here are three common ways:

```cpp title="before.cpp" run ok
#include <cstddef>
#include <tuple>
#include <type_traits>
#include <utility>

// ① recursion: peel off one at a time
template <std::size_t I, class T0, class... Ts>
struct nth { using type = typename nth<I - 1, Ts...>::type; };
template <class T0, class... Ts>
struct nth<0, T0, Ts...> { using type = T0; };

// ② go through tuple
template <std::size_t I, class... Ts>
using nth_tuple = std::tuple_element_t<I, std::tuple<Ts...>>;

// ③ inheritance plus deduction: one expansion produces N indexed base classes
template <std::size_t I, class T> struct leaf {};
template <class Seq, class... Ts> struct leaves;
template <std::size_t... I, class... Ts>
struct leaves<std::index_sequence<I...>, Ts...> : leaf<I, Ts>... {};
template <std::size_t I, class T> T pick(leaf<I, T>);   // declared only
template <std::size_t I, class... Ts>
using nth_inherit = decltype(pick<I>(
    leaves<std::index_sequence_for<Ts...>, Ts...>{}));

static_assert(std::is_same_v<nth<2, int, char, double>::type, double>);
static_assert(std::is_same_v<nth_tuple<2, int, char, double>, double>);
static_assert(std::is_same_v<nth_inherit<2, int, char, double>, double>);
int main() {}
```

① is the approach [[P2662R3]] cites; most standard library implementations hide a similar metafunction internally. `nth<5, …>` instantiates `nth<5>`, `nth<4>`, …, `nth<0>`, 6 specializations in all, and `nth<6, …>` can reuse none of them, because the argument list differs at every level. Fetching every element of a pack of length N takes N(N+1)/2 specializations in total, each carrying an argument list of length O(N).

② hands the problem to the standard library, which has to solve it somehow itself. In libc++, `tuple_element<I, tuple<Ts...>>` and `variant_alternative` both call Clang's builtin template `__type_pack_element<I, Ts...>` directly, so the cost depends on the implementation. ③ uses a single pack expansion to generate N base classes `leaf<0, T0>`, `leaf<1, T1>`, …, and then lets function template argument deduction find, through the derived-to-base conversion, the unique one matching `leaf<I, T>`; `T` is the answer. It doesn't recurse, but each lookup performs one deduction across N base classes.

Getting the Nth argument is the same. Without pack indexing you either recurse, or pack the arguments into a `tuple` with `std::forward_as_tuple` first and then use `std::get`:

```cpp title="values.cpp" run ok
#include <cstddef>
#include <cstdio>
#include <tuple>
#include <utility>

template <std::size_t I, class T0, class... Ts>
constexpr decltype(auto) nth_value(T0&& t0, Ts&&... ts) {
  if constexpr (I == 0) return std::forward<T0>(t0);
  else return nth_value<I - 1>(std::forward<Ts>(ts)...);
}

template <std::size_t I, class... Ts>
constexpr decltype(auto) nth_tuple(Ts&&... ts) {
  return std::get<I>(std::forward_as_tuple(std::forward<Ts>(ts)...));
}

template <std::size_t I, class... Ts>             // C++26
constexpr decltype(auto) nth_index(Ts&&... ts) {
  return std::forward<Ts...[I]>(ts...[I]);
}

int main() {
  int a = 0, b = 1, c = 2, d = 3, e = 4, f = 5;
  std::printf("%d %d %d\n", nth_value<5>(a, b, c, d, e, f),
              nth_tuple<5>(a, b, c, d, e, f),
              nth_index<5>(a, b, c, d, e, f));    // 5 5 5
}
```

The proposal points out that library approaches generate lots of symbols and small functions in unoptimized builds. Compiling with Clang 23 at `-O0`, calling only one of the functions at a time, and counting the functions defined in the object file with `llvm-nm` (excluding `main`): the recursive version generates 6 functions, `nth_value<0>` through `nth_value<5>`; the `tuple` version generates 14, including the `tuple` constructor, 6 `__tuple_leaf` constructors and `get`; the pack indexing version has just one, `nth_index<5>`.

### Measurements

The measurement below builds a pack `E<0>, E<1>, …, E<N-1>` (`E` being an empty class template with an `int` parameter), fetches every element with `list<at<I, Ts...>...>` and compares the result with the original sequence, so it performs N lookups in all. `at` is implemented with each of the approaches above, plus the builtin `__type_pack_element` and C++26's `Ts...[I]`. The table gives the shortest wall-clock time of three runs of Clang 23 (arm64 macOS) with `-fsyntax-only`, in seconds; the baseline is a version that does no lookup and writes `E<I>` directly.

| N | Baseline | ① Recursion | ③ Inheritance deduction | `void*` trick | `__type_pack_element` | `Ts...[I]` |
|---|---|---|---|---|---|---|
| 128 | 0.07 | 0.33 | 0.09 | 0.09 | 0.07 | 0.06 |
| 256 | 0.07 | 3.06 | 0.15 | 0.15 | 0.07 | 0.08 |
| 512 | 0.09 | 128–264 | 0.39 | 0.39 | 0.12 | 0.11 |
| 1024 | 0.16 | Not measured | 1.48 | 1.51 | 0.28 | 0.24 |
| 2048 | 0.49 | Not measured | 6.10 | 6.25 | 0.89 | 0.75 |

The `void*` trick is another non-recursive approach: for index I, generate a function template `template<class T> T f(V0, …, V(I-1), T*, ...)` whose first I parameters are all `const void*`, pass in `static_cast<Ts*>(nullptr)...`, and the (I+1)th argument deduces `T`.

Counting class template specializations with `-Xclang -print-stats` at N = 128, the recursive approach has 8256 more than the baseline, exactly 128 × 129 / 2; inheritance deduction has 131 more; the `void*` trick has 256 more, plus 128 function templates with ever longer parameter lists; `__type_pack_element` and `Ts...[I]` add none at all. The recursive approach's resident memory at N = 256 is about 1 GB. At N = 512 it was compiled only twice, separately, taking 264 and 128 seconds; the latter was measured with `/usr/bin/time -l`, with 79 seconds of system time and peak memory use of about 7 GB. The time grows far faster than the number of instantiations; most of it goes to memory.

These numbers only describe one machine; another compiler or version would differ. The trend is clear: recursion grows as N², inheritance deduction and the `void*` trick scan the whole pack on each lookup, which is also N² overall but with a much smaller constant; the builtin and pack indexing take close to constant time per lookup.

## The design space

### Candidate syntaxes

[[P2662R3]]'s syntax `name-of-a-pack ... [constant-expression]` comes from [[P1858R2]], and the Circle compiler had long implemented the same notation. In R1, at the Evolution group's request, the other candidates were compared one by one:

| Candidate | Source | Why it lost |
|---|---|---|
| `pack.[N]` | [[N4235]] | A single dot means member access in C++; [[P1858R2]] also wanted to keep `tuple.[N]` for subscripting tuple-like objects |
| `pack<N>`, `pack...<N>` | | The vast majority of languages use `[]` for subscripting and slicing; pack indexing often appears in code full of angle brackets, so more angle brackets aren't any clearer |
| `std::nth_type<N, pack...>`, `std::nth_value<N>(pack...)` | Existing library practice; [[N3761]] proposed `type_at<>` | See the next section |
| `packexpr(pack, N)` | [[P1803R0]] | Needs a name that makes sense for every kind of pack and that nobody has used, and it must be a globally reserved keyword, since it could appear wherever types and expressions can; slicing would need yet another name |
| `[N]pack` | [[P0535R0]] | May need lookahead to distinguish from a lambda; there is no reason for it other than that the position happens to be free |
| Pack objects, `pack![N]` | [[P2671R0]] | Only works for expressions; whether slicing yields a pack object or a pack is unclear, so notations like `ts![1:]~...` have to be invented too |

The author's conclusion: any of the syntaxes would be better than the status quo, but `...[N]` is the most natural extension of the existing grammar. `...` has always marked packs in C++, so readers can see at a glance where packs are involved; reserving syntax with a `...` suffix for pack-related features keeps a design space open for future pack operations. The main objection was too many dots; the author acknowledges that code manipulating packs heavily is indeed full of dots, but considers it still readable.

### Why not just write P[i]

The most direct spelling is `Ts[N]`, but the pack's elements may themselves be arrays or types with `operator[]`, and then there are four different operations, all useful: get the Nth array, subscript each array, subscript one array with a pack of indices, and subscript two packs of equal length pairwise. Whether the `...` goes before or after the `[` distinguishes exactly the first two:

```cpp title="arrays.cpp" run ok
#include <cstdio>

void print(auto... xs) { ((std::printf("%d ", xs)), ...); std::puts(""); }

template <class... A>
void demo(A&... arr) {
  print(arr...[1][0]);          // element 0 of array 1: one value
  print(arr[0]...);             // element 0 of each array: a list of values
  auto& second = arr...[1];     // array 1 itself
  std::printf("%zu\n", sizeof second / sizeof second[0]);
}

int main() {
  int a[2] = {1, 2}, b[3] = {10, 20, 30}, c[1] = {100};
  demo(a, b, c);   // prints 10 / 1 10 100 / 3
}
```

### Why not a library

The advantage of a library approach is that the language stays unchanged. The proposal lists four drawbacks:

1. Types and values need two separate spellings, and template packs a third name and a third syntax.
2. The recursion depth is O(index), and instantiations for different indices cannot be reused: `nth_type<5, …>` and `nth_type<6, …>` together take 11 instantiations. The measurements in the previous section show exactly this problem.
3. Packs are not first-class objects or types, so a library metafunction cannot return an unexpanded pack, and library approaches have no path to slicing.
4. They don't work for the universal template parameters proposed by [[P1985R1]].

Compilers can provide builtins to reduce the cost; Clang's `__type_pack_element` is an example, and libc++'s `tuple_element` is implemented with it. The proposal's answer is that the standard cannot guarantee every implementation does this, and even if a library template calls a builtin internally, that layer of template still has to be instantiated once. More fundamentally, such a builtin already is pack indexing provided by the compiler, just under a reserved identifier and only for types. Standardizing it as syntax is what lets types, expressions and, in future, template names share one notation.

### Writing it with reflection

The pack objects of [[P2671R0]] can be modelled with reflection, and [[P2662R3]] acknowledges that pack indexing is equivalent to reflecting a pack into a sequence of values, taking one out by index and splicing it back. With C++26 static reflection ([[P2996R13]], see [[papers/reflection]]), getting a type looks roughly like:

```cpp
#include <array>
#include <cstddef>
#include <meta>

template <std::size_t I, class... Ts>
using at = typename [: std::array{^^Ts...}[I] :];
```

Clang 23 does not support reflection (`__cpp_impl_reflection` is not defined), so this code could not be verified and carries no verdict. The author's view: the compiler either really constructs a constant-evaluated array and then splices, which is slower than pack indexing, or recognizes the whole thing as a pack indexing operation, in which case it is just a different spelling.

### Negative indices

In [[P1858R2]]'s slicing, `Ts...[:-1]` means dropping the last element, and Circle also supports indexing from the end with negative numbers. [[P2662R3]] did not adopt this, on the grounds that negative numbers often come from computation errors:

```cpp
// returns the index of the first type in Pack convertible to Needle, or -1 if none
template <class Needle, class... Pack>
constexpr int find_convertible = /* … */;

// if not found, T silently becomes the last type
using T = Types...[find_convertible<Foo, Types...>];
```

If `-1` meant the last element, this error would become a wrong type instead of a compile error. Dedicated syntax such as C#'s `^1` or D's `$ - 1` could be added later; the proposal had no usage experience with it, so it was left out for now.

Today's rules: the index is a converted constant expression of type `std::size_t` ([[expr.const.const]]), and converted constant expressions do not allow narrowing conversions; converting `-1` to `std::size_t` is narrowing, so it is ill-formed. Out-of-range indices and indexing an empty pack are ill-formed too:

```cpp title="bad-index.cpp" error
template <class... T> struct S { using A = T...[3]; };
using X = S<int, int>::A;      // error: index 3 out of range, the pack has only 2 elements

template <class... T> void neg() { using A = T...[-1]; }   // error: -1 narrows to std::size_t
template <class... T> void none() { using A = T...[0]; }
template void none<>();        // error: an empty pack can't be indexed
```

### Can it be deduced

Can `template<class... T> void f(T...[0]);` deduce `T` from `f(0)`? The proposal's answer is no: pack indexing is always a non-deduced context. During review, an example came up where deduction would be possible:

```cpp title="nondeduced.cpp" run ok
#include <cstdio>
#include <tuple>

template <class... T>
void f(T...[0] x, std::tuple<T...>) {
  std::printf("%u\n", x);
}

int main() {
  f(-1, std::tuple(5u, 1));   // T... is deduced from the tuple as unsigned, int
}
```

Under the proposal's rules, `T...` is deduced only from the second argument, `T...[0]` is `unsigned`, and `-1` is converted to 4294967295. If deduction from the first argument were allowed, it would give `int`, conflicting with the `unsigned` deduced from the tuple, and fail. The proposal asked the Evolution group specifically to take a position, because specifying it as non-deduced first and relaxing it later would change the meaning of existing code like this.

The difficulty with allowing deduction is the length of the pack. For `template<class... T> int f(T...[0], int);` called as `f(0, 1)`, `T` having one element or two both make sense; deducing a single element only makes sense when the pack's length comes from somewhere else, and by then the whole pack has usually already been deduced. The proposal found no use case worth that complexity, and noted that it would also affect the partial ordering rules.

This rule is in [[temp.deduct.type#5.2]]. For a call like `g(0)` with only the pack index, `T` deduces as an empty pack, and then `T...[0]` is out of range and substitution fails.

### Index names only, not patterns

In `args...[0]`, only an identifier naming a pack may come before the `...`. The proposal discussed a more general form:

```cpp
g(std::forward<T...[0]>(t...[0]));   // the adopted form
g(std::forward<T>(t)...[0]);         // not proposed, not implemented
```

The latter first builds an arbitrarily complex pattern and then keeps only one element after expansion; the compiler might have to instantiate many unused expressions, and substitution failures could occur in them. Taking the element first and building the expression around it is clearer to read and easier for the compiler. This is listed as a direction to explore in the future.

## The final design and wording

!!! std
    *pack-index-specifier*: *typedef-name* `...` `[` *constant-expression* `]` ([[dcl.type.pack.index]])

    *pack-index-expression*: *id-expression* `...` `[` *constant-expression* `]` ([[expr.prim.pack.index]])

The rules for the two forms are parallel: what precedes `...` must be an identifier naming a pack (¶1), the index is a converted constant expression of type `std::size_t` whose value is in `[0, sizeof...(P))` (¶2), and the whole construct is itself a pack expansion, so no `...` follows it (¶3). The semantics are given only in [[temp.variadic]]: on instantiation, a pack index expression is the *id-expression* corresponding to the Kth element, and a pack index type is the Kth *typedef-name* ([[temp.variadic#11]], [[temp.variadic#12]]).

This way of defining it guarantees that a pack index expression behaves exactly like writing out that element directly. The proposal specifically requires `decltype(pack...[0])` to match `decltype(id-expression)`: without parentheses it gives the declared type, with parentheses it gives a reference according to the value category (the example in [[dcl.type.decltype#1]]).

```cpp title="basic.cpp" run ok
#include <cstdio>
#include <type_traits>

template <typename... T>
constexpr auto first_plus_last(T... values) -> T...[0] {
  return T...[0](values...[0] + values...[sizeof...(values) - 1]);
}

template <class... Ts>
void show(Ts&&... args) {
  static_assert(std::is_same_v<decltype(args...[0]), Ts...[0]&&>);
  static_assert(std::is_same_v<decltype((args...[0])),
                               std::remove_reference_t<Ts...[0]>&>);
  std::printf("%d\n", args...[0]);
}

int main() {
  static_assert(first_plus_last(1, 2, 10) == 11);
  int x = 7;
  show(x, 1.0, 'c');   // 7
}
```

A pack index type is a **computed-type-specifier**, alongside `decltype`, so it can appear wherever `decltype` can: as a base-specifier, a nested-name-specifier, or the type name in an explicit destructor call (see [[dcl.type]], [[class.derived]]):

```cpp title="contexts.cpp" run ok
#include <cstdio>
#include <new>
#include <string>

struct A { static constexpr int id = 1; void hi() const { std::puts("A"); } };
struct B { static constexpr int id = 2; };

template <class... Ts>
struct D : Ts...[0] {                              // base class
  static constexpr int first_id = Ts...[0]::id;    // nested-name-specifier
};

template <class... Ts>
void destroy_first(void* p) {
  static_cast<Ts...[0]*>(p)->~Ts...[0]();          // explicit destructor call
}

int main() {
  D<A, B> d;
  d.hi();                                          // A
  static_assert(D<B, A>::first_id == 2);
  alignas(std::string) unsigned char buf[sizeof(std::string)];
  ::new (buf) std::string(100, 'x');
  destroy_first<std::string, int>(buf);
}
```

The wording changes, organized by location in the current draft (see each subclause's page for explanations):

| Subclause | Change |
|---|---|
| [[expr.prim.pack.index]] | New pack index expression; the grammar of *id-expression* gains this alternative ([[expr.prim.id]]) |
| [[dcl.type.pack.index]] | New pack index specifier; together with `decltype` it forms the computed-type-specifiers ([[dcl.type]]) |
| [[temp.variadic#6]] | Pack expansion contexts gain ¶6.14 and ¶6.15 |
| [[temp.variadic#11]], [[temp.variadic#12]] | The result of instantiating a pack index |
| [[temp.type#5]] | When dependent pack index types are the same type |
| [[temp.dep.type#10]] | A pack index type is a dependent type (¶10.12) |
| [[temp.dep.expr]] | A pack index expression is type-dependent when its *id-expression* is type-dependent |
| [[temp.deduct.type#5]] | Pack indexing is a non-deduced context (¶5.2) |
| [[diff.cpp23.dcl.dcl#2]] | Unnamed `T...[n]` parameters change meaning |

The feature-test macro is `__cpp_pack_indexing` ([[cpp.predefined]]). P2662R3 specifies the date of the proposal's adoption as its value, and Clang 23 defines it as `202311L`; [[P3670R4]], discussed below, requires it to be updated to the date of its own adoption, and the value in the current draft is `202606L`.

## Consequences

### Annex C: unnamed array parameter packs

In C++23, `T... [1]` is already a valid function parameter declaration: an unnamed function parameter pack, each parameter of which has type array of `T`, immediately adjusted to a pointer. In C++26 the same tokens are parsed as pack indexing:

<div class="compare" markdown="1">

```cpp
// C++23: two parameters int*, double*
template <typename... T>
void f(T... [1]);

f<int, double>(nullptr, nullptr);
// OK
```

```cpp
// C++26: one parameter, of type T...[1]
template <typename... T>
void f(T... [1]);

f<int, double>(nullptr, nullptr);
// error
f<int, double>(1.0);   // OK
```

</div>

Naming the parameter keeps the original meaning: in `void g(T... ptr[1]);`, the `...` is followed by a name, so it can only be a pack expansion, with the same meaning in both standards ([[diff.cpp23.dcl.dcl#2]]). [[P1858R2]] found only 11 such uses in a code search, all in compiler test suites; P2662R3 adds that GCC and MSVC never implemented this syntax, and it has not appeared outside compiler tests. That is why the author considered this incompatibility acceptable.

Clang 23 parses it by the new rules even under `-std=c++23` and `-std=c++20`: it gives two warnings, `-Wc++26-extensions` and `-Wpre-c++26-compat`, and then rejects the call on the left. By the C++23 standard the left side is well-formed, so this is a place where Clang deviates from the standard in older modes. Clang also accepts pack indexing as an extension in C++23 mode and defines `__cpp_pack_indexing`. [[diff.cpp23]] has an explanation of the same entry.

### Later fixes and extensions

| Number | Contents | Status |
|---|---|---|
| [[CWG2858]] | A declarative nested-name-specifier (the `X::` in `X::f` when defining a member outside the class) cannot use pack indexing; the wording changes from *decltype-specifier* to *computed-type-specifier* | CD7 |
| [[CWG3027]] | Two dependent pack index types being the same also requires them to index the same parameter pack ([[temp.type#5.1]]) | DR, merged into the current draft |
| [[CWG3191]] | The rules for reference collapsing and for ignoring cv-qualifiers on references ([[dcl.ref#1]], [[dcl.ref#7]]) don't mention pack indexing and splicing | Tentatively ready; current draft not yet changed |
| [[P1061R10]] | Structured bindings can introduce packs, and these packs can be indexed too | C++26 |
| [[P3670R4]] | Pack-index template names, `TT...[0]<T>`, subscripting a template template parameter pack | Merged into the working draft after C++26 |

CWG3191 is about `T...[0]&&` needing to collapse to `int&` when `T...[0]` is `int&`. The proposed fix adds *computed-type-specifier* to [[dcl.ref#7]], whose letter currently lists only *typedef-name* and *decltype-specifier*. Clang 23 already collapses according to the fixed rule, and `const T...[0]` also gives `int&` when `T...[0]` is `int&`.

The future directions section of [[P2662R3]] says indexing template template parameter packs would wait until the proposals for concept template parameters and variable template parameters were settled. [[P3670R4]] filled in this part, with wording in [[temp.names]], [[temp.variadic#13]] and [[temp.type#6]]; its author states that it has no implementation yet. Indexing from the end, slicing, and indexing arbitrary expressions remain only possible evolutions listed in the proposal.

```cpp title="sb-pack.cpp" run ok
#include <cstdio>

struct P { int a; double b; char c; };

template <class T>
void last_member(const T& t) {
  auto& [...ms] = t;                                  // structured binding pack
  std::printf("%c %zu\n", ms...[sizeof...(ms) - 1],   // last member
              sizeof...(ms));
}

int main() { last_member(P{1, 2.0, 'z'}); }           // z 3
```

### Compiler support

Clang 23 implements pack indexing for types and expressions, with `__cpp_pack_indexing` defined as `202311L`; structured binding packs can be indexed too. All the examples above behave as the standard says, except for the Annex C behavior in C++23 mode described above. Clang 23 does not yet support the pack-index template names of [[P3670R4]]; `TT...[0]<T>` gives a syntax error. libc++ already uses `_Indices...[_Ip]` in `std::get(integer_sequence)` in C++26 mode. Other compilers were not verified for this page; the author of [[P3670R4]] says GCC has also implemented P2662R3.

## Questions

!!! question "Question 1"
    What are the function types of `f<int>` and `f<int, double>` below? What happens if you take their addresses?
    ```cpp
    template <typename... T> void f(T... [1]);
    ```

<details markdown="1">
<summary>Answer</summary>

In C++26, `T... [1]` is the pack index `T...[1]`. The type of `f<int, double>` is `void(double)`. For `f<int>`, the index 1 is out of range during substitution ([[dcl.type.pack.index#2]]), which is a substitution failure, so `&f<int>` finds no usable specialization and is ill-formed. Clang 23 reports for `decltype(f<int>)` that it cannot resolve the reference to the overloaded function.

In C++23, the two are `void(int*)` and `void(int*, double*)` respectively.
</details>

!!! question "Question 2"
    Why is `template<class... Ts> void g(Ts... ts) { auto x = (ts + 1)...[0]; }` ill-formed? How should it be rewritten?

<details markdown="1">
<summary>Answer</summary>

Only an identifier naming a pack may precede the `...` of a *pack-index-expression* ([[expr.prim.pack.index#1]]), and `(ts + 1)` is not an identifier; also, `ts` then appears in an expression that is not expanded, violating [[temp.variadic#8]]. Take the element first and then operate on it: `ts...[0] + 1`. The proposal lists indexing arbitrary patterns as a possible future direction, without proposing it.
</details>

## Summary

| Decision | Choice | Reason |
|---|---|---|
| Core language or library | Core language | Library approaches instantiate O(index) times, need three spellings for types, values and templates, and can't slice |
| Syntax | `pack...[N]` | Reuses `...` to mark packs and `[]` for subscripting; distinguished from `pack[N]...` |
| Index range | `0 ≤ N < sizeof...(pack)`, out of range is ill-formed | Negative indices easily mask computation errors; indexing from the end is left to dedicated syntax |
| Deduction | Non-deduced context | Partial deduction would need the pack's length first; relaxing it later would change existing code |
| What can be indexed | Only the name of a pack | Avoids instantiating unused expressions; arbitrary patterns are left for future evolution |
| Compatibility | Unnamed `T... [n]` changes meaning | A code search found such uses only in compiler tests |

The whole progression of variadic templates from recursion to pack expansion, fold expressions and pack indexing is in [[history/template-metaprogramming]]; the rules for pack expansion themselves are in [[temp.variadic]].
