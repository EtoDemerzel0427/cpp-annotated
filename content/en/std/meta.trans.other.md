---
title: Other transformations
summary: "Common transformations such as decay, enable_if and conditional; the algorithms behind common_type and common_reference; and underlying_type, invoke_result and unwrap_reference."
updated: 2026-10-19
---

!!! tldr
    - `decay_t<T>` simulates pass-by-value: it removes references, turns arrays and functions into pointers, then removes top-level cv; to remove only references and cv, use `remove_cvref_t`.
    - `conditional_t<B, T, F>` does not short-circuit; the types of both branches must be formable.
    - `common_type` first decays its arguments, then looks for user specializations, then uses the conditional operator to find a common type, folding pairwise from left to right for more arguments. It reproduces the conversion rules of the conditional operator and does not guarantee losslessness.
    - `common_reference` gives a reference type when possible; for example, the common reference of `int&` and `const int&` is `const int&`. The ranges library relies on it and `basic_common_reference` to handle proxy references such as those of `zip`.
    - `invoke_result` computes the result type of a call by *INVOKE*, replacing `result_of`, which C++20 removed.

[meta.trans.other] collects the transformations that do not belong to the five groups of cv, references, sign, arrays and pointers (paragraph 1). They are all transformation traits: the result is in the nested `type`, with a `_t` alias as well ([[meta.trans]]). Several of them have no `type` member when a condition is not met, which is why they can be used for SFINAE.

## Small everyday tools

### `decay` and `remove_cvref`

```cpp run title="decay.cpp" ok
#include <type_traits>
using namespace std;

static_assert(is_same_v<decay_t<const int&>, int>);
static_assert(is_same_v<decay_t<const int[3]>, const int*>);
static_assert(is_same_v<decay_t<int(int)>, int (*)(int)>);
static_assert(is_same_v<remove_cvref_t<const int(&)[3]>, int[3]>);

int main() {}
```

The rule of `decay<T>`: let `U` be `remove_reference_t<T>`; if `U` is an array, the result is `remove_extent_t<U>*`; if it is a function, the result is `add_pointer_t<U>`; otherwise the result is `remove_cv_t<U>`.

It simulates the type change when an argument is passed to a function by value (Note 1): the lvalue-to-rvalue, array-to-pointer and function-to-pointer conversions ([[conv.lval]], [[conv.array]], [[conv.func]]), plus removing cv from class types. `std::make_pair`, the constructor of `std::thread` and `std::bind` all use `decay_t` to decide what type of copy to store. When an array decays, the element's cv is kept, so `decay_t<const int[3]>` is `const int*`.

`remove_cvref<T>` {{c++20}} ([[P0550R2]]) does only `remove_cv_t<remove_reference_t<T>>` and leaves arrays and functions alone. Before it existed, people often used `decay_t` to strip references and cv, and got unexpected pointer types for array parameters.

### `type_identity` {{c++20}}

`type_identity<T>::type` is just `T` ([[P0887R1]]). Its use is to create a [[temp.deduct.type|non-deduced context]]: `type_identity_t<T>` is really `type_identity<T>::type`, and the `T` to the left of `::` does not take part in template argument deduction.

```cpp run title="type-identity.cpp" ok
#include <type_traits>

template<class T>
T add(T a, std::type_identity_t<T> b) { return a + b; }

int main() {
  double d = add(1.0, 2);  // T is deduced only from the first argument
  (void)d;
}
```

If the second parameter were also written as `T`, the two arguments would deduce `double` and `int` respectively, and deduction would fail. With `type_identity_t<T>`, `T` is deduced only from the first argument as `double`, and `2` is then implicitly converted to `double`.

### `enable_if`, `conditional`, `void_t`

`enable_if<B, T = void>` has `type` equal to `T` when `B` is true, and no `type` member otherwise. Referring to a nonexistent `type` during template argument deduction causes substitution failure, so the candidate is discarded rather than producing an error (SFINAE, [[temp.deduct]]). Since C++20, most such uses can be rewritten as `requires` clauses.

`conditional<B, T, F>` has `type` equal to `T` when `B` is true and `F` otherwise. It is an ordinary class template; both `T` and `F` must be formed before the choice is made, and there is no short-circuiting:

<div class="compare" markdown="1">

```cpp error
#include <type_traits>
using namespace std;

template<class T>
using S = conditional_t<is_integral_v<T>,
                        make_signed_t<T>, T>;
S<double>* p;  // error: make_signed<double>
```

```cpp ok
#include <type_traits>
using namespace std;

template<class T>
using S = typename conditional_t<
    is_integral_v<T>,
    make_signed<T>, type_identity<T>>::type;
S<double>* p;  // OK: double
```

</div>

On the left, with `T = double`, `make_signed_t<double>` must be formed first, which violates the *Mandates* of `make_signed`. On the right, the choice is first made between two class templates, and `::type` is taken only after the selection, so the unselected `make_signed<double>` is never instantiated.

`void_t` is defined in the synopsis of `<type_traits>` as `template<class...> using void_t = void;`. It maps any number of types to `void`, and is often used together with partial specialization to detect whether some expression is valid:

```cpp run title="void-t.cpp" ok
#include <type_traits>
#include <utility>
#include <vector>

template<class T, class = void>
struct has_size : std::false_type {};

template<class T>
struct has_size<T,
    std::void_t<decltype(std::declval<T&>().size())>>
    : std::true_type {};

static_assert( has_size<std::vector<int>>::value);
static_assert(!has_size<int>::value);

int main() {}
```

For `int`, the `decltype` expression in the partial specialization fails substitution, the partial specialization is discarded, and the primary template is selected. In C++20 the same detection can be written as the concept `requires (T& t) { t.size(); }`.

## `common_type`

`common_type<T...>` answers: what type represents values of these types when they are put together? It underlies concepts such as `std::common_with`, and `<chrono>` uses it to decide the result type of adding two different `duration`s.

```cpp run title="common-type.cpp" ok
#include <string>
#include <type_traits>
using namespace std;

struct B {};
struct D : B {};

static_assert(is_same_v<common_type_t<int, long>, long>);
static_assert(is_same_v<common_type_t<short, char>, int>);
static_assert(is_same_v<common_type_t<short, short>, short>);
static_assert(is_same_v<common_type_t<int, unsigned>, unsigned>);
static_assert(is_same_v<common_type_t<int&, const int&>, int>);
static_assert(is_same_v<common_type_t<void, void>, void>);
static_assert(is_same_v<common_type_t<B*, D*>, B*>);
static_assert(is_same_v<common_type_t<string, const char*>,
                        string>);
static_assert(is_same_v<common_type_t<char, unsigned char, float>,
                        float>);

int main() {}
```

All of these results come from the type of the conditional operator `false ? x : y` ([[expr.cond]]). Arithmetic types undergo the usual arithmetic conversions, so `int` and `long` give `long`, and `short` and `char` are first promoted to `int`; two pointers give the composite pointer type; `const char*` converts to `string` but not the other way round, so the result is `string`. The precise rules are in paragraph 4.

### Two helper notations

¶3 defines several exposition-only notations, two of which `common_type` uses:

- *CREF*`(A)` is `add_lvalue_reference_t<const remove_reference_t<A>>`, which for an ordinary type `A` is `const A&`.
- *COND-RES*`(X, Y)` is `decltype(false ? declval<X(&)()>()() : declval<Y(&)()>()())`.

The form of *COND-RES* looks convoluted. `declval<X(&)()>()` yields a function returning `X`, and calling it once gives an expression whose type is exactly `X`, with the value category corresponding to `X`: an lvalue if `X` is an lvalue reference, an xvalue if it is an rvalue reference, a prvalue if it is not a reference. Writing `declval<X>()` directly cannot produce a prvalue, because `declval` always returns a reference.

### The procedure

¶4 distinguishes cases by the number of arguments:

- (4.1) With no arguments, there is no `type`.
- (4.2) With one argument `T0`, the result equals `common_type_t<T0, T0>`. So `common_type_t<const int>` is `int`.
- (4.3) With two arguments `T1` and `T2`, let `D1` and `D2` be their `decay_t`; see the four steps below.
- (4.4) With three or more, first compute `C = common_type_t<T1, T2>`, then `common_type_t<C, R...>`, i.e. fold pairwise from left to right. If any step has no result, the whole has no `type`.

The two-argument case tries in order:

1. (4.3.1) If `T1` or `T2` differs from its decayed type, the result is `common_type_t<D1, D2>`. That is, decay first and recurse, so users only need to write specializations for decayed types.
2. (4.3.2) If there is a user specialization `common_type<D1, D2>`, it is used directly, and the next two steps do not apply (Note 4).
3. (4.3.3) Otherwise, if `decay_t<decltype(false ? declval<D1>() : declval<D2>())>` is a valid type, it is the result.
4. (4.3.4) Otherwise, if *COND-RES*`(`*CREF*`(D1),` *CREF*`(D2))` is a valid type, the result is its `decay_t`. That is, try the conditional operator again with `const D1&` and `const D2&`.

The `declval<D1>()` in step 3 is an xvalue. Some types can only be converted from a const lvalue and not from an rvalue; when step 3 fails for them, step 4 fills the gap:

```cpp run title="common-type-cref.cpp" ok
#include <type_traits>
#include <utility>

struct A {};
struct B {
  B(const A&);
  B(A&&) = delete;  // cannot convert from an rvalue A
};

template<class T, class U>
concept HasCond = requires {
  false ? std::declval<T>() : std::declval<U>();
};

static_assert(!HasCond<A, B>);                // step 3 fails
static_assert( HasCond<const A&, const B&>);  // step 4 succeeds
static_assert(std::is_same_v<std::common_type_t<A, B>, B>);

int main() {}
```

### User specializations

`common_type` is one of the exceptions to the no-specialization rule of [[type.traits]]. Paragraph 5 allows a program to specialize the two-argument `common_type<T1, T2>`, provided that:

1. `T1` and `T2` are both decayed types, i.e. `is_same_v<T1, decay_t<T1>>` is true. A specialization written for `const X&` would never be used, because step 1 decays first.
2. If the specialization provides `type`, it must be a cv-unqualified non-reference type to which both `T1` and `T2` are explicitly convertible.
3. `common_type_t<T1, T2>` must be the same as `common_type_t<T2, T1>`, so specializations usually come in pairs.

A program violating these conditions is ill-formed, no diagnostic required. Note 5 describes when such a specialization is needed: when the two types have only explicit conversions between them and the conditional operator cannot find a common type.

```cpp run title="common-type-spec.cpp" ok
#include <type_traits>

struct Meters { double v; };
struct Feet {
  double v;
  explicit operator Meters() const;
};

template<> struct std::common_type<Meters, Feet> {
  using type = Meters;
};
template<> struct std::common_type<Feet, Meters> {
  using type = Meters;
};

static_assert(std::is_same_v<
    std::common_type_t<const Meters&, Feet>, Meters>);

int main() {}
```

`common_type_t<const Meters&, Feet>` first decays to `common_type_t<Meters, Feet>`, then hits the specialization. The standard library does this itself: `<chrono>` specializes `common_type` for two `duration`s.

## `common_reference` {{c++20}}

`common_type` always decays, so its result is never a reference. The ranges library needs to answer another question: is there a reference type that can bind to both `int&` and `const int&`? The answer is `const int&`. `common_reference` ([[P0898R3]]) answers exactly this question, and underlies the concepts `std::common_reference_with` and `std::indirectly_readable`.

```cpp run title="common-reference.cpp" ok
#include <type_traits>
#include <vector>
using namespace std;

struct B {};
struct D : B {};
using VBRef = vector<bool>::reference;

static_assert(is_same_v<common_reference_t<int&, const int&>,
                        const int&>);
static_assert(is_same_v<common_reference_t<int&&, int&>,
                        const int&>);
static_assert(is_same_v<common_reference_t<int&&, int&&>, int&&>);
static_assert(is_same_v<common_reference_t<B&, D&>, B&>);
static_assert(is_same_v<common_reference_t<int&, long&>, long>);
static_assert(is_same_v<common_reference_t<int>, int>);
static_assert(is_same_v<common_reference_t<VBRef, bool&>, bool>);

int main() {}
```

### *COMMON-REF*

¶3 first defines *COMMON-REF*`(A, B)` between two reference types. Two more notations are needed: *COPYCV*`(FROM, TO)` adds the top-level cv of `FROM` to `TO`; *XREF*`(A)` is an alias template that adds `A`'s cv and reference qualifiers to its argument. Let `X` and `Y` be `A` and `B` with references removed:

| Case | *COMMON-REF*`(A, B)` |
|---|---|
| (3.5) Both lvalue references | *COND-RES*`(`*COPYCV*`(X, Y)&,` *COPYCV*`(Y, X)&)`, required to exist and be a reference type |
| (3.6) Both rvalue references | Let `C` be `remove_reference_t<COMMON-REF(X&, Y&)>&&`; if both `A` and `B` convert to `C`, the result is `C` |
| (3.7) `A` an rvalue reference, `B` an lvalue reference | Let `D` be *COMMON-REF*`(const X&, Y&)`; if `A` converts to `D`, the result is `D` |
| (3.8) `A` an lvalue reference, `B` an rvalue reference | *COMMON-REF*`(B, A)` |
| (3.9) Otherwise | Ill-formed |

For two lvalue references, the cv of both sides is merged first (`int&` and `const int&` both become `const int&`), then it checks whether the conditional operator yields an lvalue. For one lvalue reference and one rvalue reference, `const X&` is used instead, since it can bind rvalues too.

### The procedure

¶6 specifies: with no arguments there is no `type`; with one argument the result is that argument itself, not decayed, which differs from `common_type`; with three or more it folds from left to right just like `common_type`. With two arguments `T1` and `T2` it tries in order:

1. (6.3.1) If both are references, *COMMON-REF*`(T1, T2)` is well-formed, and both `T1*` and `T2*` convert to the pointer type of the result, use it.
2. (6.3.2) Otherwise, if `basic_common_reference<remove_cvref_t<T1>, remove_cvref_t<T2>, XREF(T1), XREF(T2)>::type` is well-formed, use it. This is the customization point left for users.
3. (6.3.3) Otherwise, if *COND-RES*`(T1, T2)` is well-formed, use it.
4. (6.3.4) Otherwise, if `common_type_t<T1, T2>` is well-formed, use it.
5. If none works, there is no `type`.

Take `common_reference_t<int&, long&>` as an example. Step 1 computes *COND-RES*`(int&, long&)` per (3.5): two lvalues of different types undergo the usual arithmetic conversions and yield a `long` prvalue, which is not a reference type, so *COMMON-REF* is ill-formed. Step 2 finds no specialization. In step 3, *COND-RES*`(int&, long&)` is `long`, and that is the result. `const long&` is not a candidate at any step, and `int&` cannot bind directly to a `long` object, only to a temporary produced by conversion, so it would not count as a common reference.

### `basic_common_reference`

The primary template of `basic_common_reference<T, U, TQual, UQual>` has no `type`. Paragraph 7 allows programs to partially specialize it, the other exception to the no-specialization rule. The conditions are similar to those for `common_type`: `T` and `U` are decayed types; if there is a `type`, both `TQual<T>` and `UQual<U>` must convert to it; swapping `(T, U)` gives the same result. Violating these conditions likewise requires no diagnostic.

`TQual` and `UQual` are exactly *XREF*`(T1)` and *XREF*`(T2)`; through them a specialization learns what cv and reference the original arguments carried. The standard library provides such partial specializations for `pair`, `tuple` and `reference_wrapper`. The reference type of `views::zip` is `tuple<int&, int&>` and its value type is `tuple<int, int>`; only because a common reference of the two can be computed does `zip`'s iterator satisfy `std::indirectly_readable`:

```cpp run title="zip-common-ref.cpp" ok
#include <ranges>
#include <tuple>
#include <type_traits>
#include <vector>
using namespace std;

using V = vector<int>;
using Zip = decltype(views::zip(declval<V&>(), declval<V&>()));
using Ref = ranges::range_reference_t<Zip>;

static_assert(is_same_v<Ref, tuple<int&, int&>>);
static_assert(is_same_v<
    common_reference_t<Ref&&, tuple<int, int>&>, Ref>);

int main() {}
```

## `underlying_type`

If `T` is an enumeration type, `underlying_type<T>::type` is its underlying type ([[dcl.enum]]); otherwise there is no `type`. Before C++20 using it on a non-enumeration type was undefined behavior; now it can be used for SFINAE.

The *Mandates* requires that `T` is not an incomplete enumeration type, i.e. an enumeration whose underlying type is not yet determined. An enumeration without a fixed underlying type is incomplete before the closing brace of its definition; an opaque declaration with a fixed underlying type, `enum Fwd : int;`, is already enough.

```cpp run title="underlying-type.cpp" ok
#include <type_traits>

enum Fwd : int;  // opaque declaration, underlying type already determined
static_assert(std::is_same_v<std::underlying_type_t<Fwd>, int>);

template<class T>
concept HasUT = requires { typename std::underlying_type<T>::type; };
static_assert(!HasUT<int>);  // not an enumeration: no type

int main() {}
```

## `invoke_result` and `apply_result`

`invoke_result<Fn, ArgTypes...>` {{c++17}}: if *INVOKE*`(declval<Fn>(), declval<ArgTypes>()...)` ([[func.require]]) is well-formed as an unevaluated operand, `type` is the `decltype` of that expression; otherwise there is no `type`. As with `is_invocable` in [[meta.rel]], access checking is performed in an unrelated context and only the immediate context is considered; errors outside the immediate context (for example, while instantiating some function body) make the program ill-formed (Note 2). Each type must be a complete type, `void`, or an array of unknown bound (*Preconditions*).

It replaces `result_of<F(Args...)>`, deprecated in C++17 and removed in C++20. `result_of` borrowed the function type `F(Args...)` to represent a call, which put `F` in the return type position, so it could not be a function or array type; `Args` were also adjusted like function parameters, with arrays and functions turned into pointers and top-level cv dropped.

The example in ¶8 covers the various forms of *INVOKE*:

```cpp run title="invoke-result.cpp" ok
#include <memory>
#include <type_traits>
using namespace std;

using PF1 = bool  (&)();
using PF2 = short (*)(long);

struct S {
  operator PF2() const;
  double operator()(char, int&);
  void fn(long) const;
  char data;
};

using PMF = void (S::*)(long) const;
using PMD = char S::*;

static_assert(is_same_v<invoke_result_t<S, int>, short>);
static_assert(is_same_v<invoke_result_t<S&, unsigned char, int&>,
                        double>);
static_assert(is_same_v<invoke_result_t<PF1>, bool>);
static_assert(is_same_v<invoke_result_t<PMF, unique_ptr<S>, int>,
                        void>);
static_assert(is_same_v<invoke_result_t<PMD, S>, char&&>);
static_assert(is_same_v<invoke_result_t<PMD, const S*>, const char&>);

int main() {}
```

The first line deserves a closer look. `declval<int>()` is not an lvalue and cannot bind to the `int&` parameter of `operator()`, so `operator()` is not viable. `S` can also be converted to a function pointer through `operator PF2() const`; such a conversion function forms a surrogate call function in a call expression ([[over.call.object]]), and what is finally called is `short(*)(long)`, so the result type is `short`.

The second-to-last line: accessing a data member through an rvalue object gives an xvalue, so the type is `char&&`.

`apply_result<Fn, Tuple>` is post-C++23 wording. If `Tuple` satisfies *tuple-like* and *INVOKE*`(declval<Fn>(), ELEMS-OF(Tuple)...)` is well-formed, `type` is the `decltype` of that expression. *ELEMS-OF* expands a tuple via `get<0>`, `get<1>`, ...; its definition is in [[meta.rel#3]]. libc++ (with Clang 23) does not provide `apply_result` yet.

## `unwrap_reference` and `unwrap_ref_decay` {{c++20}}

`unwrap_reference<T>` gives `X&` if `T` is `reference_wrapper<X>`, and `T` otherwise. It does not decay first, so `unwrap_reference_t<const reference_wrapper<int>>` is still `const reference_wrapper<int>`.

`unwrap_ref_decay<T>` is `unwrap_reference_t<decay_t<T>>`; it describes the element types of `std::make_pair` and `std::make_tuple`: arguments decay as if passed by value, but arguments wrapped with `std::ref` become references.

¶2: these two templates and their `_t` aliases are also available when `<functional>` is included, because they are closely tied to `reference_wrapper`.

!!! impl "libc++'s `common_type`"
    Clang provides a builtin template `__builtin_common_type`, which libc++ uses directly when available. The builtin takes several callback templates: one for recursive queries (so that user specializations can be found), one for wrapping the result, and one representing "no `type`". Without the builtin, libc++ falls back to a pure template implementation whose comments correspond item by item to the subparagraphs of paragraph 4.

## Pitfalls

!!! pitfall "`common_type` does not guarantee losslessness"
    `common_type_t<int, unsigned>` is `unsigned`, so negative numbers become large positive ones; `common_type_t<long long, double>` is `double`, so large integers lose precision. It reproduces the usual arithmetic conversions of the conditional operator; it is not a type guaranteed to hold both without loss.

## Questions

!!! question "Question 1"
    What are `std::common_type_t<int[3], int*>` and `std::common_type_t<int(), int(*)()>`?

<details markdown="1">
<summary>Answer</summary>

Both decay first in step 1: `decay_t<int[3]>` is `int*`, and `decay_t<int()>` is `int(*)()`. So they reduce to `common_type_t<int*, int*>` and `common_type_t<int(*)(), int(*)()>`, giving `int*` and `int(*)()` respectively.
</details>

!!! question "Question 2"
    Why is `common_reference_t<int&&, int&>` `const int&` rather than `int&`?

<details markdown="1">
<summary>Answer</summary>

By (3.8), *COMMON-REF*`(int&&, int&)` reduces to the case of (3.7): let `D` be *COMMON-REF*`(const int&, int&)`. By (3.5), after merging cv both sides are `const int&`, and the conditional operator gives a `const int` lvalue, so `D` is `const int&`. `int&&` converts to `const int&`, so the result is `const int&`.

`int&` does not work, because an rvalue cannot bind to a non-const lvalue reference.
</details>

## Quick reference

| Template | `type` | When there is no `type` |
|---|---|---|
| `type_identity<T>` {{c++20}} | `T` | |
| `remove_cvref<T>` {{c++20}} | `remove_cv_t<remove_reference_t<T>>` | |
| `decay<T>` | The type after pass-by-value | |
| `enable_if<B, T>` | `T` | `B` is false |
| `conditional<B, T, F>` | `B ? T : F` | |
| `common_type<T...>` | See paragraph 4 | No common type |
| `basic_common_reference<T, U, TQ, UQ>` | None in the primary template; for user partial specialization | By default |
| `common_reference<T...>` {{c++20}} | See paragraph 6 | No common reference |
| `underlying_type<T>` | The underlying type of the enumeration | `T` is not an enumeration |
| `invoke_result<Fn, Args...>` {{c++17}} | The type of the *INVOKE* expression | The expression is ill-formed |
| `apply_result<Fn, Tuple>` | The type of *INVOKE* after expanding the tuple | Not tuple-like, or the expression is ill-formed |
| `unwrap_reference<T>` {{c++20}} | `reference_wrapper<X>` becomes `X&`, otherwise `T` | |
| `unwrap_ref_decay<T>` {{c++20}} | `unwrap_reference_t<decay_t<T>>` | |
