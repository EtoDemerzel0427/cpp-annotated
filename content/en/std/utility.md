---
title: Utility components
summary: "The small functions in <utility>: move, forward, forward_like, move_if_noexcept, swap, exchange, as_const, declval, the safe integer comparisons cmp_less and friends, to_underlying, unreachable and observable_checkpoint. Most are one or two lines long; their job is to give a name to a language rule."
updated: 2026-10-19
---

!!! tldr
    - `std::move` and `std::forward` are both just a `static_cast` and move nothing themselves; `std::move` on a `const` object results in a copy.
    - `std::forward<T>(x)` needs the template argument written explicitly; it relies on reference collapsing to turn the `T` deduced for a forwarding reference back into the argument's original value category.
    - To swap two values in generic code, either write `using std::swap;` followed by an unqualified call `swap(a, b)`, or use `std::ranges::swap`. Writing `std::swap(a, b)` directly bypasses the type's own `swap`.
    - `std::cmp_less(-1, 0u)` is true, while the built-in `-1 < 0u` is false; `cmp_*` does not accept `char` or `bool`.
    - Calling `std::unreachable()` is undefined behavior; its purpose is to tell the optimizer the path does not exist. `std::declval` may only appear in unevaluated operands, otherwise compilation fails.

Almost every function in [utility] is one or two lines long; `std::move` is a single `static_cast`. Their value lies in giving a name to a language rule that is awkward to write directly: `move` means using an lvalue as an rvalue, `forward` means restoring a value category from the deduction result, `declval` means conjuring an expression of some type in an unevaluated operand, `cmp_less` means integer comparison in the mathematical sense, and `unreachable` means this point cannot be reached.

For the {{c++26}} `constant_wrapper` in [utility], see [[const.wrap.class]].

¶1 [utility.syn] says that `<utility>` contains basic function and class templates used throughout the rest of the library. The whole header is freestanding, so it can be used in environments without an operating system.

## `move`: treating an lvalue as an rvalue [forward]

```cpp run title="move.cpp" ok
#include <string>
#include <utility>
#include <cstdio>

int main() {
  std::string a = "hello";
  std::string b = std::move(a);      // selects the move constructor
  const std::string c = "world";
  std::string d = std::move(c);      // const std::string&& can only bind to the copy constructor's parameter
  std::printf("[%s] [%s]\n", b.c_str(), c.c_str());   // [hello] [world]
}
```

```cpp
template<class T> constexpr remove_reference_t<T>&& move(T&& t) noexcept;
```

¶10 `std::move(t)` returns `static_cast<remove_reference_t<T>&&>(t)`, that is, it converts the argument to an xvalue. What actually moves resources is the move constructor or move assignment operator subsequently selected by overload resolution; `std::move` merely makes them selectable.

Two often-overlooked consequences follow:

- `std::move` applied to a `const` object yields `const T&&`, which cannot bind to the `T&&` parameter of the move constructor, so overload resolution selects the copy constructor. In the example above, `d` is copied and `c` is left intact.
- `return std::move(local);` is usually worse than `return local;`. The latter allows the compiler to elide the copy (NRVO, [[class.copy.elision]]), and even without elision `local`, as an implicitly movable entity ([[g:implicitly-movable-entity]]), is treated as an rvalue first; the former makes the return expression no longer a name, which actually prevents elision.

¶1 The functions in this subclause are signal-safe and can be called from signal handlers ([[support.signal]]).

## `forward`: restoring the argument's value category

### Forwarding references and reference collapsing

```cpp
template<class T>
void wrapper(T&& x) {
  target(std::forward<T>(x));   // forwards an lvalue if the argument was an lvalue, an rvalue if it was an rvalue
}
```

`std::forward` depends on two core language rules:

1. **Forwarding references** ([[g:forwarding-reference]], [[temp.deduct.call#3]]): when a function template parameter is written `T&&` and `T` is a cv-unqualified type template parameter of that same function template, an lvalue argument makes `T` deduce as the lvalue reference type `A&`, and an rvalue argument makes `T` deduce as `A`.
2. **Reference collapsing** ([[g:reference-collapsing]], [[dcl.ref#7]]): when a reference to a reference is formed through a template parameter or a type alias, the result is an lvalue reference if either one is `&`; only `&& &&` yields an rvalue reference.

So in `wrapper`, `T` records the argument's original value category. But `x` is a named variable, and as an expression it is always an lvalue ([[basic.lval]]). The job of `std::forward<T>(x)` is to restore the value category according to `T`.

### Definition (¶2–¶4)

```cpp
template<class T> constexpr T&& forward(remove_reference_t<T>& t) noexcept;
template<class T> constexpr T&& forward(remove_reference_t<T>&& t) noexcept;
```

¶3 Both overloads return `static_cast<T&&>(t)`. Applying reference collapsing:

| `T` | `T&&` after collapsing | Value category of `forward<T>(x)` |
|---|---|---|
| `A&` (argument was an lvalue) | `A&` | lvalue |
| `A` (argument was an rvalue) | `A&&` | xvalue |
| `A&&` (specified explicitly) | `A&&` | xvalue |

The `T` in the parameter type `remove_reference_t<T>&` is in a non-deduced context ([[temp.deduct.type]]), so the template argument of `forward` must be written explicitly, and `std::forward(x)` does not compile. This is intentional: if deduction were allowed, `T` would be deduced from the lvalue `x`, and the original value category information would already be lost.

The second overload accepts rvalues and is used to forward an expression that is itself an rvalue. ¶2 requires that its `T` not be an lvalue reference type (*Mandates*), because forwarding an rvalue as an lvalue is almost certainly a mistake and yields an lvalue reference to a temporary:

```cpp run title="forward_mandates.cpp" error
#include <utility>
int main() {
  int i = 0;
  (void)std::forward<int&>(std::move(i));   // error: forwarding an rvalue as an lvalue violates Mandates
}
```

libc++ implements this requirement with a `static_assert`, and the diagnostic is "cannot forward an rvalue as an lvalue".

¶4 The standard's example shows the effect of perfect forwarding: in `factory<A>(2, 1.414)`, `A1` is deduced as `int` and `2` is forwarded as an rvalue to `A(int&, const double&)`, so binding fails; in `factory<A>(i, 1.414)`, `A1` is deduced as `int&` and `i` is forwarded as an lvalue, so binding succeeds.

### `forward_like`: forwarding with another object's value category {{c++23}} (¶5–¶9)

```cpp run title="forward_like.cpp" ok
#include <utility>
#include <type_traits>
#include <string>

struct Holder {
  std::string name;
  template<class Self>
  auto&& get(this Self&& self) { return std::forward_like<Self>(self.name); }
};

int main() {
  Holder h{"abc"};
  const Holder ch{"xyz"};
  static_assert(std::is_same_v<decltype(h.get()), std::string&>);
  static_assert(std::is_same_v<decltype(std::move(h).get()), std::string&&>);
  static_assert(std::is_same_v<decltype(ch.get()), const std::string&>);
  static_assert(std::is_same_v<decltype(std::move(ch).get()), const std::string&&>);
  std::string s = std::move(h).get();   // move-constructed from h.name
  return s == "abc" ? 0 : 1;
}
```

`forward` answers whether this thing was originally an lvalue or an rvalue. Another common need is: given an object `self`, forward one of its members, or something it owns through a pointer, with `self`'s value category and constness. Member access `std::forward<Self>(self).m` handles direct members, but anything reached through a pointer indirection (`*self.ptr`, `(*container)[i]`) loses this information. `forward_like<T>(x)` ([[P2445R1]]) solves exactly this problem.

¶6 The result type is determined by two rules: if `T` is const, the result gets `const`; whether the result is an lvalue reference or an rvalue reference is decided entirely by `T`, and what kind of reference `x` originally was plays no role. ¶7 The return value is `x` `static_cast` to that type. ¶5 `T` must be a referenceable type ([[g:referenceable-type]]); `forward_like<void>` is ill-formed.

It pairs naturally with C++23 explicit object parameters ([[dcl.fct]]): `Self` records the cv-qualification and value category of the object it was called on exactly, and `forward_like<Self>` passes them on to the member. The standard's example in ¶9 shows precisely the case where the member is a pointer and the elements live in a container: `std::move(a)[0]` yields `string&&`, and `as_const(a)[1]` yields `const string&`, which cannot bind to a non-const `string&`.

### `move_if_noexcept` (¶12)

```cpp
template<class T> constexpr conditional_t<
    !is_nothrow_move_constructible_v<T> && is_copy_constructible_v<T>, const T&, T&&>
  move_if_noexcept(T& x) noexcept;
```

¶12 It returns `std::move(x)`, but with a conditional return type: if `T`'s move constructor may throw and `T` is copyable, it returns `const T&`, so the caller copies; otherwise it returns `T&&`.

```cpp run title="move_if_noexcept.cpp" ok
#include <utility>
#include <type_traits>

struct ThrowingMove {
  ThrowingMove() = default;
  ThrowingMove(const ThrowingMove&) {}
  ThrowingMove(ThrowingMove&&) {}            // no noexcept
};
struct NoexceptMove {
  NoexceptMove() = default;
  NoexceptMove(const NoexceptMove&) {}
  NoexceptMove(NoexceptMove&&) noexcept {}
};
struct MoveOnly {
  MoveOnly() = default;
  MoveOnly(MoveOnly&&) {}                    // may throw, but not copyable
};

ThrowingMove a; NoexceptMove b; MoveOnly c;
static_assert(std::is_same_v<decltype(std::move_if_noexcept(a)), const ThrowingMove&>);
static_assert(std::is_same_v<decltype(std::move_if_noexcept(b)), NoexceptMove&&>);
static_assert(std::is_same_v<decltype(std::move_if_noexcept(c)), MoveOnly&&>);
int main() {}
```

It serves the strong exception guarantee. When `std::vector` grows, it has to relocate the old elements to the new buffer. If it used a move constructor that may throw and an exception occurred halfway, the elements in the old buffer would already have been moved from and could not be rolled back; copying does not damage the original elements. So `vector` relocates elements with `move_if_noexcept`, and this is why move constructors should be declared `noexcept`. Move-only types that cannot be copied have no choice: `T&&` is returned, and the strong guarantee degrades to the basic guarantee.

## `swap`: exchanging two values [utility.swap]

### The two-step and `ranges::swap`

```cpp run title="swap_two_step.cpp" ok
#include <utility>
#include <concepts>
#include <cstdio>

namespace lib {
  struct Widget {
    int* p;
    friend void swap(Widget& a, Widget& b) noexcept {   // custom swap: only swaps the pointer
      std::puts("lib::swap");
      std::swap(a.p, b.p);
    }
  };
}

template<class T>
void generic_swap(T& a, T& b) {
  using std::swap;   // step 1: bring in std::swap as a fallback
  swap(a, b);        // step 2: unqualified call, ADL can find lib::swap
}

int main() {
  int x = 1, y = 2;
  lib::Widget a{&x}, b{&y};
  std::swap(a, b);           // qualified call: uses only std::swap (three moves), prints nothing
  generic_swap(a, b);        // prints lib::swap
  std::ranges::swap(a, b);   // prints lib::swap
  int arr1[2]{1, 2}, arr2[2]{3, 4};
  generic_swap(arr1, arr2);  // array overload: swaps element by element
  std::printf("%d %d\n", *a.p, arr1[0]);   // 2 3
}
```

`std::swap(a, b)` is a qualified call: it finds only the template in `std` and cannot see an efficient `swap` the user wrote for their own type. The traditional idiom in generic code is the **std::swap two-step** ([[g:swap-two-step]]): first `using std::swap;`, then an unqualified call `swap(a, b)`. Argument-dependent lookup ([[g:argument-dependent-lookup]]) can find `lib::swap`; when it finds nothing, `std::swap` is the fallback. When both are viable, the non-template `lib::swap` beats the template `std::swap`. [[swappable.requirements]] defines swappable as exactly this: calling `swap(t, u)` in such a context is valid and has the right semantics.

The two-step is easy to forget and easy to get wrong. C++20's `std::ranges::swap` ([[concept.swappable]]) is a **customization point object** ([[g:customization-point-object]]): a function object that does the ADL-only lookup for you internally and, when that finds nothing, falls back to element-wise swapping or three moves. `std::swap` itself was not changed into such an object, because existing code takes its address and specifies its template arguments explicitly, and the change would break those uses.

### The primary template (¶1–¶4)

```cpp
template<class T>
  constexpr void swap(T& a, T& b) noexcept(see below);
```

This is a typical example of how the elements of a library specification divide the work (see [[structure.specifications]]):

- ¶1 *Constraints*: `is_move_constructible_v<T>` and `is_move_assignable_v<T>` are both true. If not, this template does not participate in overload resolution, so `is_swappable_v<T>` can honestly yield `false` instead of a hard error occurring inside the function body.
- ¶2 *Preconditions*: `T` meets *Cpp17MoveConstructible* and *Cpp17MoveAssignable*. These are semantic requirements the compiler cannot check, for example that after move construction the new object's value equals the source's original value. Violating them is undefined behavior.
- ¶3 *Effects*: exchanges the values of `a` and `b`. The standard does not specify how; implementations usually do three moves.
- ¶4 The exception specification is equivalent to `is_nothrow_move_constructible_v<T> && is_nothrow_move_assignable_v<T>`.

### The array overload (¶5–¶7)

```cpp
template<class T, size_t N>
  constexpr void swap(T (&a)[N], T (&b)[N]) noexcept(is_nothrow_swappable_v<T>);
```

¶5 It requires `is_swappable_v<T>`; ¶6 each pair `a[i]`, `b[i]` must be swappable; ¶7 the effect is as if by `swap_ranges(a, a + N, b)`. The exception specification uses `is_nothrow_swappable_v<T>` because the elements are swapped one by one and the element type may have its own `swap`.

## `exchange`: take the old value out, put a new value in [utility.exchange]

```cpp
template<class T, class U = T>
  constexpr T exchange(T& obj, U&& new_val) noexcept(see below);
```

¶1 The effect is equivalent to first moving `obj` out into `old_val`, then assigning the forwarded `new_val` to `obj`, and finally returning `old_val`. ¶2 The exception specification is `is_nothrow_move_constructible_v<T> && is_nothrow_assignable_v<T&, U>`.

The default template argument of `U` is `T`, so `std::exchange(v, {})` also works: a braced list cannot deduce a template parameter, and with the default argument `{}` is treated as `T&&`.

Its most common use is in move operations, taking a pointer and nulling the source in a single line:

```cpp run title="exchange.cpp" ok
#include <utility>
#include <cstdio>

class Buffer {
  int* data_ = nullptr;
public:
  explicit Buffer(int n) : data_(new int[n]{}) {}
  Buffer(Buffer&& o) noexcept : data_(std::exchange(o.data_, nullptr)) {}
  Buffer& operator=(Buffer&& o) noexcept {
    delete[] std::exchange(data_, std::exchange(o.data_, nullptr));
    return *this;
  }
  ~Buffer() { delete[] data_; }
  bool empty() const { return data_ == nullptr; }
};

int main() {
  Buffer a(4);
  Buffer b = std::move(a);
  Buffer c(2);
  c = std::move(b);
  std::printf("%d %d %d\n", a.empty(), b.empty(), c.empty());   // 1 1 0
}
```

## `as_const` [utility.as.const]

```cpp
template<class T> constexpr add_const_t<T>& as_const(T& t) noexcept;
template<class T> void as_const(const T&&) = delete;
```

¶1 `as_const(t)` returns `t` with its type changed to a const lvalue reference. It is easier to write than `const_cast<const T&>(x)` and cannot be misread as casting away const. A common use is forcing the const overload to be selected, for example to keep a copy-on-write container from copying its data because of non-const access.

The second declaration is a deleted rvalue overload. A non-const rvalue cannot bind to `T&` in the first place; but for a const rvalue, such as a call to a function returning `const X`, `T` is deduced as `const X` ([[temp.deduct.call]]), `const X&` can bind to the rvalue, and `as_const` would return a reference to a temporary. The deleted `as_const(const T&&)` is a better match for all rvalues and closes this hole:

```cpp run title="as_const_rvalue.cpp" error
#include <utility>
#include <string>
std::string make();
int main() {
  std::string s = "x";
  const std::string& r = std::as_const(s);   // OK
  auto&& bad = std::as_const(make());         // error: selects the deleted as_const(const T&&)
  (void)r; (void)bad;
}
```

## `declval`: for unevaluated operands only [declval]

```cpp
template<class T> add_rvalue_reference_t<T> declval() noexcept;    // as unevaluated operand
```

¶1 The operands of `decltype`, `sizeof`, `noexcept` and `requires` are **unevaluated operands** ([[g:unevaluated-operand]]): the expressions in them are only type-checked and never executed. In these places you often need an expression of type `T`, but `T` may have no default constructor, may be an abstract class, or may even be incomplete, so you cannot write `T()`. `declval<T>()` provides such an expression unconditionally.

```cpp run title="declval.cpp" error
#include <utility>
#include <type_traits>
struct NoDefault { NoDefault(int); int f() const; };

using R = decltype(std::declval<const NoDefault&>().f());   // OK: unevaluated operand
static_assert(std::is_same_v<R, int>);
struct Incomplete;
using X = decltype(std::declval<Incomplete>());             // OK: T may be incomplete (¶3)

int main() {
  auto x = std::declval<int>();   // error: declval is odr-used
  (void)x;
}
```

!!! std
    *Mandates*: This function is not odr-used ([basic.def.odr]).

¶2 As soon as `declval` is odr-used ([[g:odr-use]]), that is, it appears in a potentially-evaluated expression, the program is ill-formed and the compiler must report an error. `declval` is only a tool for writing types and should never be called.

Choosing `add_rvalue_reference_t<T>` rather than `T` as the return type has two benefits:

1. ¶3 `T` can be an incomplete type, an abstract class, an array or a function type, none of which can be a function's return type;
2. `declval<T>()` is an xvalue, `declval<T&>()` is an lvalue and `declval<const T&>()` is a const lvalue, so you can say precisely which value category and cv-qualification the expression should have.

`add_rvalue_reference_t<T>` is used instead of writing `T&&` directly because it returns `T` unchanged for non-referenceable types like `void`: `declval<void>()` is a valid `void` expression, whereas `void&&` is invalid.

!!! impl "How libc++ checks for odr-use"
    libc++'s `declval` has a body containing a `static_assert` whose condition depends on `_Tp`, such as `!__is_same(_Tp, _Tp)`; it is evaluated only when the function body is instantiated. A function template definition is implicitly instantiated only when it is odr-used ([[temp.inst]]), and uses in unevaluated operands do not trigger instantiation, so the assertion fails only on a violation. The return type is computed with two overloads of `__declval<T>(0)`, with the same effect as `add_rvalue_reference_t<T>`.

¶4 The standard's example `decltype(static_cast<To>(declval<From>())) convert(From&&);` shows `declval` working together with SFINAE ([[g:sfinae]]): when the expression in the return type is invalid, `convert` is removed from the set of candidate functions.

## Integer comparison [utility.intcmp]

```cpp run title="intcmp.cpp" ok
#include <utility>
#include <cstdint>

static_assert(!(-1 < 0u));                      // built-in <: -1 is first converted to UINT_MAX
static_assert(std::cmp_less(-1, 0u));           // comparison in the mathematical sense
static_assert(short{-1} < (unsigned short)0);   // both sides are promoted to int first; correct result

static_assert(!std::cmp_equal(-1, UINT32_MAX));
static_assert(std::in_range<std::uint8_t>(255));
static_assert(!std::in_range<std::uint8_t>(256));
static_assert(!std::in_range<unsigned>(-1));
int main() {}
```

The built-in comparison operators first apply the usual arithmetic conversions ([[g:usual-arithmetic-conversions]], [[expr.arith.conv]]) to both operands. When one operand is signed and the other unsigned, and the unsigned type's rank is not lower than the signed type's, the signed operand is converted to the unsigned type, and `-1` becomes `UINT_MAX`. The third line shows that the problem does not always occur: `short` and `unsigned short` are both promoted to `int` first. Whether it goes wrong depends on the widths of the specific types, which makes it hard to spot by eye. When such comparisons are done on variables, Clang's `-Wsign-compare` (included in `-Wextra`) warns; the constant expressions above produce no warning.

¶2 `cmp_equal` is defined as follows: when both sides have the same signedness, use `==` directly, since the conversion does not change the mathematical value; when the signed side is less than 0, they are necessarily unequal; otherwise, convert the signed side to the corresponding unsigned type and compare. ¶5 `cmp_less` has the same structure; when the signed side is less than 0, it is necessarily smaller. ¶3 and ¶6–¶8 define the other four functions in terms of these two; for example, `cmp_greater(t, u)` is `cmp_less(u, t)`. ¶10 `in_range<R>(t)` determines whether `t` lies within the range of values of `R`, that is, whether converting it to `R` preserves the value.

¶1, ¶4 and ¶9 require all types to be signed or unsigned integer types (*Mandates*, [[basic.fundamental]]). ¶11 Note 1 points out that `byte`, `char`, `char8_t`, `char16_t`, `char32_t`, `wchar_t` and `bool` cannot be used: they are integral types, but not signed or unsigned integer types.

```cpp run title="intcmp_char.cpp" error
#include <utility>
int main() {
  bool b1 = std::cmp_less('a', 98);    // error: char is not a signed or unsigned integer type
  bool b2 = std::cmp_equal(true, 1);   // error: likewise for bool
  (void)b1; (void)b2;
}
```

!!! impl "libc++ implements Mandates as constraints"
    The standard says *Mandates*, but libc++ expresses the requirement as a concept on the template parameter, so the diagnostic is "no matching function". The difference is that constraints can be detected: write `requires (T t) { std::cmp_less(t, 1); }` in a template, and libc++ yields `false` for `T = char`, whereas according to the standard the call should be a hard error. Portable code should not rely on this difference.

## `to_underlying` [utility.underlying]

```cpp run title="to_underlying.cpp" ok
#include <utility>
#include <cstdint>
#include <cstdio>
#include <type_traits>

enum class Color : std::uint8_t { red = 1, green = 2 };

int main() {
  auto v = std::to_underlying(Color::green);
  static_assert(std::is_same_v<decltype(v), std::uint8_t>);
  std::printf("%d\n", v);   // 2 (uint8_t is promoted to int as a variadic argument)
}
```

¶1 `to_underlying(e)` returns `static_cast<underlying_type_t<T>>(e)` ([[P1682R3]]). It just gives a name to a common idiom, but it has one practical advantage: the type is always right. A hand-written `static_cast<int>(e)` silently truncates once someone changes the enumeration's underlying type ([[g:underlying-type]], [[dcl.enum]]) from `int` to `std::uint64_t`; `to_underlying` does not.

The standard gives it no constraints. When called with a non-enumeration type, `underlying_type_t<T>` is not a valid type and substitution into the return type fails, so in practice it is SFINAE-friendly.

## Explicit UB and observable checkpoints [utility.undefined]

### `unreachable` (¶1–¶2)

```cpp
[[noreturn]] void unreachable();
```

!!! std
    *Preconditions*: `false` is `true`.

¶1 This precondition can never be satisfied, so calling `unreachable` has undefined behavior (Note 1). The standard did not invent a new mechanism for it; it borrows the general rule that violating a precondition is undefined behavior ([[structure.specifications]]). Its effect corresponds to GCC's and Clang's `__builtin_unreachable()` and MSVC's `__assume(false)` ([[P0627R6]]).

```cpp run title="unreachable.cpp" ub
#include <utility>
#include <cstdio>

int decode(int tag) {
  switch (tag) {
  case 0: return 10;
  case 1: return 20;
  default: std::unreachable();   // asserts that callers never pass other values
  }
}

int main(int argc, char**) {
  std::printf("%d\n", decode(argc - 1));   // run without arguments, argc == 1, gives 10
  std::printf("%d\n", decode(argc + 5));   // UB: reaches unreachable
}
```

It tells the optimizer that control flow does not reach this point. With Clang 23 at `-O0 -fsanitize=undefined`, UBSan reports "execution reached an unreachable program point" and terminates; at `-O2` the second line printed 20: the optimizer concluded that `tag` could only be 0 or 1 and reduced the `switch` to a single comparison.

`unreachable()` and `[[assume(expr)]]` ([[dcl.attr.assume]]) give the optimizer similar information, and `if (!cond) std::unreachable();` has an effect similar to `[[assume(cond)]];`, but there are three differences:

- The expression in `[[assume]]` is not evaluated, so its side effects do not happen; the `cond` in `if (!cond)` is evaluated.
- `[[assume]]` is an attribute and states that a condition holds; `unreachable()` is a call to a `[[noreturn]]` function and states that this path does not exist, so it can be placed somewhere like `default:`.
- Ignoring `[[assume]]` does not change the program's meaning, and the compiler is free not to use its information.

Both are unchecked promises, and the programmer bears the consequences when they are wrong. For a checkable version, write C++26's `contract_assert(cond);` ([[basic.contract]]) or `assert`.

### `observable_checkpoint` {{c++26}} (¶3)

```cpp
void observable_checkpoint() noexcept;
```

¶3 It establishes an **observable checkpoint** ([[g:observable-checkpoint]], [[intro.abstract]]). C++26 specifies that when undefined behavior occurs during execution, only the behavior after the last checkpoint is unconstrained; observable behavior that has already happened before it must be produced faithfully. Calling `std::observable_checkpoint()` before a piece of code that may have undefined behavior, for example after writing a log entry, guarantees that the log entry will not be optimized away because of the later undefined behavior. It is the exact counterpart of `unreachable`: one creates undefined behavior, the other limits how far undefined behavior reaches.

## Other contents of `<utility>` [utility.syn]

The synopsis also declares or includes the following, specified elsewhere:

- `#include <compare>` and `#include <initializer_list>`, so including just `<utility>` is enough to use `std::strong_ordering` and `std::initializer_list`;
- `integer_sequence`, `index_sequence`, `make_index_sequence` etc. ([[intseq]]), as well as the `tuple_size`, `tuple_element` and `get` that make a structured binding pack such as `auto [...is] = std::make_index_sequence<N>{};` work;
- `pair` with its comparisons, `swap`, `make_pair` and tuple-like access ([[pairs]]);
- the tag types `piecewise_construct_t`, `in_place_t`, `in_place_type_t<T>` and `in_place_index_t<I>`, which constructors use to distinguish different ways of construction. Their default constructors are all `explicit`, to prevent `{}` from accidentally being taken as a tag;
- `monostate` with its comparisons and `hash<monostate>` ([[variant.monostate]]).

!!! history "std::rel_ops"
    C++98's `<utility>` provided `std::rel_ops`: once you had written `==` and `<`, `using namespace std::rel_ops;` gave you `!=`, `>`, `<=` and `>=`. They are unconstrained templates that match every type, and once brought in they interfere with overload resolution. C++20's rewritten candidates ([[over.match.oper]]) rewrite `a != b` into `!(a == b)` automatically, and a single `<=>` operator yields all four relational operators, so `rel_ops` was deprecated and moved to Annex [[depr.relops]]. It is still in the standard and implementations must provide it; libc++ (in our tests) issues a `-Wdeprecated-declarations` warning when its operators are used.

## Common misconceptions

!!! pitfall "Thinking `declval` can be used in an `if constexpr` condition"
    The condition of `if constexpr` is a constant expression that gets evaluated; it is not an unevaluated operand. Calling `declval` there is an odr-use too, and the program is ill-formed. When needed, wrap it in `decltype`, `sizeof` or `requires`.

!!! pitfall "Calling `forward` or `move` on the same object twice"
    After the first time, the object may already have been moved from and be in a valid but unspecified state ([[g:valid-but-unspecified-state]]). In perfect forwarding, each parameter should be passed to `std::forward` only once.

!!! pitfall "Using `unreachable` as an assertion"
    In release builds it reports nothing; it only lets the optimizer make more aggressive assumptions. If you need an error during debugging, use `assert` or `contract_assert`.

## Questions

!!! question "Question 1"
    The `wrapper` below wants to perfectly forward its argument to `g`. Is there a problem with writing `std::forward<T&&>`?
    ```cpp
    template<class T> void wrapper(T&& x) { g(std::forward<T&&>(x)); }
    ```

<details markdown="1">
<summary>Answer</summary>

The result is correct; the spelling is just redundant. For an lvalue argument `T = A&`, `T&&` collapses to `A&`, and `forward<A&>(x)` returns `A&`; for an rvalue argument `T = A`, `T&&` is `A&&`, and `forward<A&&>(x)` returns `A&&`, the same as `forward<A>(x)`. By the reference collapsing rule in [[dcl.ref#7]], the two spellings are equivalent for forwarding references. The idiomatic form is `std::forward<T>(x)`; for an `auto&&` variable, write `std::forward<decltype(x)>(x)`, which works on the same principle.
</details>

!!! question "Question 2"
    Can `std::cmp_less(x, y)` and the built-in `x < y` give different results in the following three cases? `int x, long long y`; `unsigned x, long long y`; `unsigned long long x, long long y`.

<details markdown="1">
<summary>Answer</summary>

The first cannot: both sides are signed, and the first branch of paragraph 5 is simply `t < u`. The second cannot either on platforms where `long long` is wider than `unsigned` (almost all of them): the usual arithmetic conversions convert `unsigned` to `long long`, and the mathematical value is unchanged. The third can: both have the same rank, so the `long long` operand is converted to `unsigned long long`. For example, with `y = -1` it becomes `ULLONG_MAX`, and the built-in `x < y` is true for every `x` except `ULLONG_MAX`, while `cmp_less(x, -1)` is always false. The rule is in [[expr.arith.conv#1]].
</details>

!!! question "Question 3"
    Why is the return type of `declval` written `add_rvalue_reference_t<T>` rather than `T&&`?

<details markdown="1">
<summary>Answer</summary>

`T` may be `void` (or cv-qualified `void`), or a function type with cv- or ref-qualifiers, such as `int() const`. None of these are referenceable types ([[g:referenceable-type]]), and writing `T&&` would cause a substitution failure. `add_rvalue_reference_t<T>` returns `T` unchanged for non-referenceable types, so `decltype(declval<void>())` is valid and can appear in metaprogramming. For referenceable types, the two spellings are identical.
</details>
