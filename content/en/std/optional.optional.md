---
title: Class template optional
summary: "The full specification of the optional<T> primary template: the storage model, the constraints on each constructor, when the special members are trivial, the exception guarantees of assignment and emplace, the ways to access the value, the monadic operations and C++26 range support."
updated: 2026-10-19
---

!!! tldr
    - `optional<T>` stores a `T` and a has-value flag inside itself and does no heap allocation; having a value means the internal union member is active.
    - Whether `optional<T>` can be implicitly constructed from some type matches whether `T` can be implicitly converted from it; when `T` itself can be constructed from `optional<U>` (like `std::any`), the converting constructors step aside, with `bool` as the exception.
    - When `T` is trivially copyable, so is `optional<T>`: it can be `memcpy`'d and passed in registers.
    - When assignment or `swap` throws, `has_value()` is unchanged; after `emplace` throws, the optional is empty and the old value has already been destroyed.
    - `*o` and `o->` have hardened preconditions in C++26: a hardened implementation checks and terminates, otherwise it is UB; `value()` throws `bad_optional_access` when there is no value.

`optional<T>` represents a `T` that may not exist. For the overview, the comparison operators and `hash`, see [[optional]]; for C++26's reference partial specialization `optional<T&>`, see [[optional.optional.ref]].

## Storage: a union plus a flag [optional.optional.general]

```cpp run ok
#include <cassert>
#include <optional>
#include <string>

int main() {
  std::optional<std::string> o;      // empty
  assert(!o.has_value());
  o = "hi";                          // constructs a string inside o
  assert(o && *o == "hi");
}
```

The specification describes the storage with an exposition-only anonymous union:

```cpp
template<class T>
class optional {
  // …
private:
  union {
    remove_cv_t<T> val;       // exposition only
  };
};
```

¶1 An `optional<T>` is said to **contain a value** if and only if the member *val* is the active member of the union ([[class.union]]); *val* is called its **contained value**. The contained value is nested within ([[intro.object]]) the optional object, so its storage is inside the optional object, not on the heap.

The union's role here is to suppress automatic construction and destruction: union members are neither implicitly constructed nor implicitly destroyed. When to create a `T` in this storage and when to call `val.~T()` is decided entirely by optional's own member functions.

The type of *val* is `remove_cv_t<T>` rather than `T`. For `optional<const int>`, the storage holds an `int`, so when operations like `emplace` destroy the old value and construct a new one in the same storage, they do not run into [[basic.life]]'s restrictions on recreating an object in the storage of a const object. The public interface still returns in terms of `T`; users see `const int&`.

### Which types can go into an optional (¶2)

¶2 A type `X` is a **valid contained type** for optional ([[g:valid-contained-type]]) if it is an lvalue reference type or a complete non-array object type, and `remove_cvref_t<X>` is not `in_place_t` or `nullopt_t`. A program that instantiates `optional` with any other type is ill-formed, and the compiler must report an error.

| Type | Allowed in optional? | Reason |
|---|---|---|
| `void`, function types | no | not object types |
| `int[3]` | no | arrays cannot be copy-initialized or assigned, so the interface does not fit |
| `int&&` | no | rvalue references are excluded |
| `int&` | yes, since C++26 | handled by the partial specialization [[optional.optional.ref]] |
| `nullopt_t`, `in_place_t` | no | they are constructor tags; otherwise `optional<nullopt_t>(nullopt)` would be ambiguous |

In addition, an object type `T` must meet *Cpp17Destructible*. This is an ordinary library requirement; violating it is {{ub}} ([[res.on.functions]]), and the standard does not guarantee a diagnostic. libc++ checks the conditions above with a series of `static_assert`s inside the class, so in practice you always get a clear error.

## Constructors [optional.ctor]

### An empty optional (¶2–3)

`optional()` and `optional(nullopt_t)` are both `noexcept` and construct an object that does not contain a value.

¶3 These two constructors do not initialize the contained value. For every object type `T` they are constexpr constructors, even when `T` is not a literal type, because no constructor of `T` is called at all. So `constinit std::optional<std::mutex> m;` is always static initialization.

### Copy and move (¶4–12)

¶4 In copy construction, if `rhs` has a value, its own *val* is **direct-non-list-initialized** ([[g:direct-non-list-initialization]]) with `rhs.`*val*, that is, in the form `T val(rhs.val);`.

¶7 If `is_copy_constructible_v<T>` is false, the copy constructor is defined as deleted; if `T` is trivially copy-constructible, it is trivial.

¶8 The move constructor is specified differently, using *Constraints*: when `is_move_constructible_v<T>` is false, it does not participate in overload resolution. A deleted function still participates in overload resolution and only causes an error when selected; a function whose *Constraints* are not met is not a candidate at all ([[structure.specifications]]). So when `T` is not movable but is copyable, an rvalue optional falls back to the copy constructor, consistent with how the core language treats a class without a move constructor ([[class.copy.ctor]]).

¶9 After a move, `rhs.has_value()` is unchanged: the moved-from optional still has a value, only that value is in a moved-from state. ¶12 The move constructor's `noexcept` is equivalent to `is_nothrow_move_constructible_v<T>`, and it is trivial when `T` is trivially move-constructible.

### `in_place` construction (¶13–22)

`optional(in_place_t, Args&&...)` and the version with an `initializer_list` construct *val* directly from the given arguments, so they can construct non-movable types. They are always `explicit`. ¶17 and ¶22 specify that if the constructor of `T` selected for the initialization is constexpr, so is this constructor.

```cpp
std::optional<std::mutex> m(std::in_place);          // constructs the mutex inside the optional
std::optional<std::vector<int>> v(std::in_place, {1, 2, 3});
```

### Constructing from a value (¶23–27)

This is the most commonly used constructor; `std::optional<std::string> s = "abc";` uses it:

```cpp
template<class U = remove_cv_t<T>>
  constexpr explicit(see below) optional(U&& v);
```

¶27 The condition in `explicit` is equivalent to `!is_convertible_v<U, T>`. In other words, if `T` can be implicitly converted from `U`, `optional<T>` can be implicitly constructed from `U`; if the corresponding constructor of `T` is explicit, so is this one.

```cpp run error
#include <optional>
#include <string>
#include <vector>

std::optional<std::string> s = "abc";       // OK
std::optional<std::vector<int>> v1{3};      // OK: direct-initialization
std::optional<std::vector<int>> v2 = 3;     // error: vector(size_t) is explicit
int main() {}
```

¶23 It has four constraints:

- ¶23.1 `is_constructible_v<T, U>`;
- ¶23.2 `remove_cvref_t<U>` is not `in_place_t`; otherwise it would steal calls like `optional(in_place)`;
- ¶23.3 `remove_cvref_t<U>` is not this optional type itself; otherwise a non-const lvalue `optional&` would match `U&&` better than `const optional&` and steal copy construction;
- ¶23.4 if `T` is cv `bool`, `remove_cvref_t<U>` is not a specialization of `optional`.

The reason for ¶23.4 is that `bool` can be direct-initialized from `optional<int>` through `explicit operator bool`, so `is_constructible_v<bool, optional<int>>` is true. Without this rule, `std::optional<bool> b{std::optional<int>{}}` would produce an optional containing `false`, whereas people expect an empty optional to convert to an empty optional.

The default template argument `U = remove_cv_t<T>` is for when the argument is a braced list and `U` cannot be deduced, for example `std::optional<const Foo> o({1, 2});`. The parameter type is then `Foo&&`: `{1, 2}` first constructs a temporary `Foo`, and *val* is move-constructed from it. If the default were `T`, the parameter type would be `const Foo&&`, which only allows copying. libc++ 23 (in our tests) still writes this constructor as `_Up = _Tp`, so the line above calls `Foo`'s copy constructor.

### Converting from another optional (¶1, ¶28–37)

```cpp
template<class U> constexpr explicit(see below) optional(const optional<U>& rhs);
template<class U> constexpr explicit(see below) optional(optional<U>&& rhs);
```

These two constructors convert value-wise: if `rhs` is empty the result is empty, otherwise *val* is constructed from `*rhs`. ¶30 and ¶35 specify that `rhs.has_value()` is unchanged; the `explicit` conditions in ¶32 and ¶37 are `!is_convertible_v<const U&, T>` and `!is_convertible_v<U, T>` respectively.

The difficulty is that some `T`s can themselves be constructed from the whole `optional<U>`, the classic example being `std::any`:

```cpp run ok
#include <any>
#include <cassert>
#include <optional>

int main() {
  std::optional<int> empty;

  std::optional<std::any> a = empty;
  assert(a.has_value());             // an any holding an empty optional<int>
  assert(a->type() == typeid(std::optional<int>));

  std::optional<bool> b = empty;     // bool is the exception: empty stays empty
  assert(!b.has_value());

  std::optional<long> c = std::optional<int>(42);
  assert(c && *c == 42);             // the ordinary case: value-wise conversion
}
```

Constructing `optional<any>` from `optional<int>` has two plausible semantics: value-wise conversion, or putting the whole `optional<int>` into the `any`. The standard chose the latter, on the grounds of staying consistent with `T` itself: `std::any x = empty;` already puts the `optional<int>` inside.

¶1 To this end the standard defines an exposition-only variable template *converts-from-any-cvref*`<T, W>`: whether `T` can be constructed from, or implicitly converted from, any of `W&`, `W`, `const W&` and `const W`. ¶28.2 and ¶33.2 specify that if `T` is not cv `bool`, *converts-from-any-cvref*`<T, optional<U>>` must be false. So with `T = std::any` the converting constructors do not participate in overload resolution, and what remains, `optional(U&&)`, hands the whole `optional<int>` to `any`.

`bool` is the exception because `bool` being initializable from `optional<U>` is just a side effect of `explicit operator bool`; nobody wants has-value-or-not turned into a `bool` value. Together with ¶23.4, constructing `optional<bool>` from `optional<U>` only ever goes through value-wise conversion. [[expected.expected]] also borrows *converts-from-any-cvref*.

!!! impl "libc++: two overloads instead of explicit(bool)"
    libc++'s `<optional>` still has to support C++17, and `explicit(bool)` only exists since C++20. So each of these conditionally explicit constructors is written as two overloads, one implicit and one `explicit`, enabled by mutually exclusive `enable_if` conditions. Among them, `__check_constructible_from_opt` is *converts-from-any-cvref*. `optional(U&&)` also carries a `noexcept` the standard does not require; library implementations may strengthen the exception specification of non-virtual functions ([[res.on.exception.handling]]).

## When the special members are trivial

```cpp run ok
#include <optional>
#include <string>
#include <type_traits>

static_assert(std::is_trivially_copyable_v<std::optional<int>>);
static_assert(!std::is_trivially_copyable_v<std::optional<std::string>>);
int main() {}
```

A class is **trivially copyable** ([[g:trivially-copyable-class]]) if and only if it has at least one eligible copy or move operation, all eligible copy and move operations are trivial, and its destructor is trivial and not deleted ([[class.prop]]). Trivially copyable types can be copied with `memcpy` and used with `std::bit_cast` and `std::atomic`. Under the Itanium C++ ABI, they can also be passed and returned in registers: a function returning `optional<int>` generates the same code as one returning `struct { int v; bool b; }`.

The standard spreads the triviality conditions of the special members across various *Remarks*:

| Special member | Trivial when | Source |
|---|---|---|
| copy constructor | `T` is trivially copy-constructible | [[optional.ctor#7]] |
| move constructor | `T` is trivially move-constructible | [[optional.ctor#12]] |
| destructor | `T` is trivially destructible | [[optional.dtor#2]] |
| copy assignment | `T` is trivially copy-constructible, trivially copy-assignable and trivially destructible | [[optional.assign#7]] |
| move assignment | `T` is trivially move-constructible, trivially move-assignable and trivially destructible | [[optional.assign#13]] |

The assignment conditions include trivial destructibility because, when `rhs` is empty, assignment has to destroy `*this`'s value, and a trivial assignment would not call the destructor. Taken together, the five rules mean that a trivially copyable `T` makes `optional<T>` trivially copyable. The original C++17 specification lacked these guarantees; [[P0602]] added them.

[optional.dtor] itself has only two paragraphs. ¶1 If `T` is not trivially destructible and `*this` has a value, the destructor calls *val*`.T::~T()`; ¶2 when `T` is trivially destructible, this destructor is trivial.

### How to make a class template's special members conditionally trivial

With `T = std::string`, the destructor must be written as `if (engaged) val.~T();`; with `T = int`, it must be trivial. But a user-provided function is never trivial, even with an empty body.

C++20's [[P0848]] solved this. A class can declare several prospective destructors with different constraints ([[g:prospective-destructor]], see [[class.dtor]]), as well as several copy and move constructors; when the class is complete, the one whose constraints are satisfied and which is most constrained becomes the **eligible** special member ([[g:eligible-special-member-function]], see [[special]]), and triviality only looks at the eligible one:

```cpp run ok
#include <memory>
#include <string>
#include <type_traits>

template<class T>
class Opt {
  union { T val; };
  bool engaged = false;
public:
  constexpr Opt() noexcept {}
  constexpr Opt(const T& v) : val(v), engaged(true) {}

  // two prospective destructors; the constraints decide which one is used
  constexpr ~Opt()
    requires std::is_trivially_destructible_v<T>
    = default;
  constexpr ~Opt() { if (engaged) val.~T(); }

  // two copy constructors: a trivial version and a hand-written version
  Opt(const Opt&)
    requires std::is_trivially_copy_constructible_v<T>
    = default;
  constexpr Opt(const Opt& o) : engaged(o.engaged) {
    if (engaged)
      std::construct_at(std::addressof(val), o.val);
  }
  Opt& operator=(const Opt&) = delete;  // assignment works the same way; omitted
};

static_assert(std::is_trivially_destructible_v<Opt<int>>);
static_assert(std::is_trivially_copy_constructible_v<Opt<int>>);
static_assert(!std::is_trivially_destructible_v<Opt<std::string>>);

int main() {
  Opt<std::string> a(std::string(100, 'x'));
  Opt<std::string> b = a;
}
```

With `T = int` both destructors satisfy their constraints, and the constrained one is more constrained and is selected; with `T = std::string` only the unconstrained one is satisfied.

!!! impl "libc++: a ladder of base classes"
    C++17 had no constrained special members, so the only option was dispatching through base classes. libc++'s `optional<T>` still uses this approach today (it also has to serve C++17 mode, and changing the inheritance structure would affect the ABI): each layer of an inheritance chain is responsible for one kind of special member and uses a `bool` template parameter to choose between a trivial `= default` version and a hand-written version, for example `__optional_destruct_base<T, is_trivially_destructible<T>>`, `__optional_copy_base`, `__optional_copy_assign_base` and so on. `optional<T>`'s own special members are all `= default`, and whether they are trivial is decided by the base classes. The later `<expected>` uses the C++20 constrained style directly.

    This approach has a corner-case defect. By the standard's rules, `optional<const int>` should be trivially copyable: copy assignment is deleted and so not eligible, and all the remaining eligible operations are trivial. But libc++ 23 (in our tests) gives `is_trivially_copyable_v<std::optional<const int>>` as false, because some base class is not trivially copyable: the layer responsible for copy assignment chose the hand-written version because `const int` is not trivially copy-assignable, while the base class that actually deletes assignment is further out, so the middle layer leaves behind an eligible, non-trivial copy assignment.

## Assignment [optional.assign]

### Copy assignment and move assignment (¶1–13)

¶1 `o = nullopt` destroys the value if there is one and otherwise does nothing, equivalent to `reset()`.

The effects of copy and move assignment are specified by a 2×2 table (Table 67 in ¶4, Table 68 in ¶9):

| | `*this` has a value | `*this` has no value |
|---|---|---|
| `rhs` has a value | assigns `rhs.`*val* to *val* | direct-non-list-initializes *val* with `rhs.`*val* |
| `rhs` has no value | destroys it by calling *val*`.T::~T()` | no effect |

When both sides have values, `T`'s assignment operator is called rather than destroying and then constructing; this preserves `T`'s own assignment semantics, such as `std::vector` reusing existing capacity on assignment.

¶7 and ¶13 specify the exception guarantee: if an exception is thrown, the result of `this->has_value()` is unchanged. An optional never loses a value or gains an extra one because of an exception; what state the value itself is in is determined by the exception guarantees of `T`'s constructor or assignment operator.

¶7 Copy assignment is defined as deleted unless `T` is both copy-constructible and copy-assignable, since either operation in the table may be needed. ¶8 Move assignment uses *Constraints*, and ¶12 its `noexcept` is equivalent to `is_nothrow_move_assignable_v<T> && is_nothrow_move_constructible_v<T>`.

### Assigning from a value, and `o = {}` (¶14–18)

```cpp
template<class U = remove_cv_t<T>> constexpr optional& operator=(U&& v);
```

¶15 If there is a value, `v` is assigned to *val*; otherwise *val* is constructed from `v`. Among the constraints of ¶14, ¶14.1, ¶14.3 and ¶14.4 are straightforward: `U` is not this optional type, `T` can be constructed from `U`, and `T&` can be assigned from `U`.

¶14.2 requires `conjunction_v<is_scalar<T>, is_same<T, decay_t<U>>>` to be false, and it exists specifically for `o = {}`:

```cpp run ok
#include <cassert>
#include <optional>
#include <string>

int main() {
  std::optional<int> i = 5;
  i = {};                     // reset
  assert(!i);

  std::optional<std::string> s = "hello";
  s = {};                     // also a reset
  assert(!s);
}
```

`{}` cannot deduce `U`, so `U` takes the default `remove_cv_t<T>`. If `T` is a scalar like `int`, getting `0` from `{}` for `operator=(int&&)` takes only a standard conversion, which is better than the user-defined conversion needed by `operator=(optional&&)`, and `i = {}` would store 0. ¶14.2 removes this candidate. When `T` is not a scalar, both candidates need user-defined conversions and neither is better; [[over.match.best]] prefers a non-template over a template, so `operator=(optional&&)` wins and the result is again a reset.

### Assigning from another optional (¶19–28)

The constraints are more numerous than for the corresponding constructors. Besides `T` being constructible and assignable from `*rhs` and *converts-from-any-cvref*`<T, optional<U>>` being false, ¶19.4–¶19.7 also require that `T&` not be assignable from any of the four cv/reference forms of `optional<U>`. The reasoning is the same as for construction: when `T` itself can accept a whole `optional<U>` (for example `std::any`), this operator steps aside in favor of `operator=(U&&)`. There is no `bool` exception here, because `bool` cannot be assigned from `optional<U>`. The effects are in Tables 69 and 70, with the same structure as copy assignment.

### `emplace` (¶29–40)

```cpp
template<class... Args> constexpr T& emplace(Args&&... args);
```

¶30 `emplace` first does `*this = nullopt`, then constructs *val* directly from the arguments; ¶32 it returns a reference to *val*, so you can write `auto& x = o.emplace(...)`.

¶34 If `T`'s constructor throws, `*this` does not contain a value, and the previous value (if any) has already been destroyed. This is only the basic guarantee: the point of `emplace` is in-place construction, which does not allow the old and new values to coexist. When you need the strong guarantee, construct a `T` first and then do `o = std::move(t)`. By contrast, the `emplace` of [[expected.expected]] requires construction to be `noexcept`, to maintain its invariant of always holding a value.

## swap [optional.swap]

¶1 `swap` requires `is_move_constructible_v<T>`; this is *Mandates*, and violating it is ill-formed. ¶2 also requires `T` to meet *Cpp17Swappable* ([[swappable.requirements]]). The effects are in Table 71:

- if both sides have values, `swap(val, rhs.val)` is called, with this `swap` found by argument-dependent lookup;
- if only one side has a value, the value is move-constructed into the other side and then the original is destroyed;
- if neither side has a value, nothing happens.

¶5 The `noexcept` is equivalent to `is_nothrow_move_constructible_v<T> && is_nothrow_swappable_v<T>`. ¶6 If an exception is thrown, `has_value()` is unchanged on both sides.

## Accessing the value [optional.observe]

### `*` and `->`: hardened preconditions (¶1–8)

```cpp
constexpr T& operator*() & noexcept;         // also const&, &&, const&& versions
constexpr T* operator->() noexcept;          // also a const version
```

¶1, ¶4 and ¶7 specify that they all have the **hardened precondition** `has_value()`. Per [[structure.specifications]], in a **hardened implementation** ([[g:hardened-implementation]]; whether it is enabled is implementation-defined), the condition is checked before the call, and a violation is handled as a contract violation with terminating semantics; in a non-hardened implementation, violating it is {{ub}}.

```cpp
#include <cstdio>
#include <optional>

int main() {
  std::optional<int> o;
  try {
    (void)o.value();          // throws bad_optional_access
  } catch (const std::bad_optional_access&) {
    std::puts("caught");
  }
  int x = *o;                 // violates a hardened precondition
  std::printf("%d\n", x);
}
```

In our tests with libc++ 23 compiled by default (non-hardened), the program prints a meaningless value and exits normally. With `-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_FAST`, the program traps (SIGTRAP) at `*o`; with `_LIBCPP_HARDENING_MODE_DEBUG`, it first prints a message saying `operator*` was applied to an empty optional and then terminates. This is part of C++26 standard library hardening ([[P3471]]).

¶2 `operator->` returns `addressof(val)` rather than `&val`, in case `T` overloads unary `&`. ¶8 The rvalue version of `*` returns `std::move(val)`, of type `T&&`.

!!! ub "`*` on an rvalue optional produces a dangling reference"
    ```cpp
    std::optional<std::string> make();
    const std::string& s = *make();   // the reference binds to the inside of the temporary optional
    std::puts(s.c_str());             // UB: the temporary optional has been destroyed
    ```
    `*make()` is a function call returning `std::string&&`, not a direct binding to a temporary object, so it does not extend the lifetime of the temporary optional ([[class.temporary]]). The rvalue overload of `value()` is the same. Catch it by value (`std::string s = *make();`), or store the optional in a variable first.

### `has_value`, `operator bool`, `value()` (¶9–14)

¶9–12 `has_value()` and `operator bool` both return whether there is a value. `operator bool` is `explicit`, so `if (o)` and `!o` are allowed but `int n = o;` is not ([[g:contextually-converted-to-bool]]).

¶13 The effect of `value()` is equivalent to:

```cpp
return has_value() ? val : throw bad_optional_access();
```

`value()` has no preconditions, and its behavior is always defined. In a freestanding implementation (one without operating system support) it is deleted, marked *freestanding-deleted* in the synopsis. The division of labor: `*o` is for places where you are sure there is a value, with no checking overhead (checking plus termination once hardened); `value()` is for places where you want an exception when there is no value, to be handled by a higher layer.

### `value_or` (¶15–18)

```cpp
template<class U = remove_cv_t<T>> constexpr T value_or(U&& v) const &;
template<class U = remove_cv_t<T>> constexpr T value_or(U&& v) &&;
```

¶16 The effect is equivalent to `has_value() ? val : static_cast<T>(std::forward<U>(v))`. ¶15 requires `T` to be copy-constructible and `U&&` to be implicitly convertible to `T`; the rvalue version (¶17) requires `T` to be move-constructible. These are *Mandates*: violating them is a hard error, not a substitution failure.

`value_or` returns `T` by value and makes a copy even when the optional has a value; for large objects you can write `o ? *o : fallback` instead. The default argument `U = remove_cv_t<T>` makes `o.value_or({})` work: `{}` cannot be deduced, so the parameter type is `T&&`, value-initialized from `{}`.

## Monadic operations [optional.monadic] {{c++23}}

```cpp run ok
#include <cassert>
#include <optional>
#include <type_traits>

struct Pinned {               // neither copyable nor movable
  int v;
  explicit Pinned(int x) : v(x) {}
  Pinned(Pinned&&) = delete;
};

struct Point { int x, y; };

int main() {
  // and_then: f returns an optional itself, for a next step that may fail
  auto half = [](int i) -> std::optional<int> {
    if (i % 2) return std::nullopt;
    return i / 2;
  };
  assert(std::optional(8).and_then(half).and_then(half) == 2);
  assert(!std::optional(6).and_then(half).and_then(half));

  // transform: the result is constructed directly in the new optional; no movability required
  std::optional<int> o = 21;
  auto p = o.transform([](int i) { return Pinned(i * 2); });
  assert(p->v == 42);

  // C++26: f returns an lvalue reference, the result is optional<int&>
  std::optional<Point> pt = Point{1, 2};
  auto rx = pt.transform([](Point& q) -> int& { return q.x; });
  static_assert(std::is_same_v<decltype(rx), std::optional<int&>>);
  *rx = 100;
  assert(pt->x == 100);

  // or_else: f takes no arguments and returns an optional of the same type
  auto r = std::optional<int>{}.or_else(
      [] { return std::optional<int>(-1); });
  assert(r == -1);
}
```

[[P0798]] added three member functions so that a chain of computations that may fail need not be written as deeply nested `if`s. `and_then` and `transform` each have four overloads, `&`, `const&`, `&&` and `const&&`, differing only in which value category *val* is handed to `f` with; `or_else` has just two, `const&` and `&&`.

### `and_then` (¶1–6)

¶1 Let `U` be `invoke_result_t<F, decltype((val))>`. ¶2 requires `remove_cvref_t<U>` to be a specialization of `optional` (*Mandates*). ¶3 If there is a value it returns `invoke(std::forward<F>(f), val)`, otherwise an empty `remove_cvref_t<U>`. The value type of the result can differ from the original optional's.

### `transform` (¶7–12)

¶7 Let `U` be `remove_cv_t<invoke_result_t<F, decltype((val))>>`. ¶8 requires `U` to be a valid contained type and the declaration `U u(invoke(std::forward<F>(f), val));` to be well-formed. Note 1 says that `U` is not required to be movable.

¶9 If there is a value, it returns an `optional<U>` whose contained value is direct-non-list-initialized with `invoke(std::forward<F>(f), val)`. The standard does not say this is equivalent to `return optional<U>(in_place, invoke(...));`, because then the prvalue returned by `invoke` would first have to bind to the reference parameter of the `in_place` constructor, being materialized as a temporary object, and *val* would be move-constructed from it, requiring `U` to be movable. With the current wording, the prvalue directly initializes the target object ([[dcl.init.general]]), so even the non-movable `Pinned` in the example above can be the result.

!!! impl "How libc++ achieves direct initialization"
    Once the prvalue of a function call is passed through a function parameter, it is materialized, so an ordinary constructor interface cannot achieve direct initialization. libc++ adds a private tag constructor to `optional` that passes `f` and the arguments all the way down to the storage base class, where the member initializer is written `__val_(std::invoke(std::forward<_Fp>(__f), ...))`, so the prvalue directly initializes `__val_`. `<expected>` uses the same trick.

Since C++26, lvalue references are also valid contained types, so when `f` returns `int&`, `U = int&` and the result is `optional<int&>` (as in the example above). In C++23 this violated *Mandates* and was a hard error. An `f` returning `void`, an array, `nullopt_t` or an rvalue reference still violates *Mandates*.

### `or_else` (¶13–18)

¶13 requires `F` to model `invocable` (callable with no arguments) and `T` to model `copy_constructible` (`move_constructible` for the rvalue version, ¶16); these are *Constraints*. ¶14 requires the return type of `f()`, with cv and references removed, to be exactly this `optional<T>`; this is *Mandates*. ¶15 If there is a value it returns a copy of `*this`, otherwise `f()`.

Because some of `or_else`'s conditions are *Constraints*, `requires { o.or_else(g); }` can give `false` for a `g` that cannot be called with no arguments; but `and_then` and `transform` have only *Mandates*, so a wrong return type can only produce a hard error. The monadic operations are therefore not suitable for substitution-failure-style detection.

## Range support [optional.iterators] {{c++26}}

```cpp
#include <cstdio>
#include <optional>
#include <ranges>

int main() {
  std::optional<int> o = 7;
  for (int& v : o) v *= 6;          // 0 or 1 iterations
  std::printf("%d\n", *o);

  std::optional<int> e;
  for (int v : e) std::printf("never %d\n", v);
  static_assert(std::ranges::contiguous_range<std::optional<int>>);
  static_assert(std::ranges::view<std::optional<int>>);
  std::printf("%zu %zu\n", std::ranges::size(o), std::ranges::size(e));
}
```

Since C++26, `optional<T>` is a range containing at most one element ([[P3168]]). ¶1 `iterator` and `const_iterator` are implementation-defined types that model `contiguous_iterator`, with value type `remove_cv_t<T>` and reference types `T&` and `const T&` respectively. ¶2 All the requirements on container iterators apply as well.

¶4 If there is a value, `begin()` points to the contained value; otherwise it is the past-the-end iterator. ¶5 `end()` returns `begin() + has_value()`, adding the `bool` as 0 or 1. ¶3 Any operation that initializes or destroys the contained value invalidates all iterators into this optional.

In [[optional]], `enable_view<optional<T>>` is true, so an optional can be put straight into a pipeline, for example `opt | std::views::transform(f)`. The difference from `views::single` is that it can be empty and can be modified in place.

libc++ 23 (in our tests) puts this part behind an experimental switch: the example above only compiles with `-fexperimental-library`, and outputs `42` and `1 0`; without it, `for (int& v : o)` cannot find `begin`. That is why the example carries no verdict tag.

## Modifiers and constexpr [optional.mod]

¶1 `reset()` calls *val*`.T::~T()` if there is a value and otherwise does nothing; ¶2 afterwards the optional does not contain a value. It is `noexcept`.

Every member function of `optional<T>` is declared `constexpr`; whether it can actually be used in constant evaluation depends on the operations of `T` it calls. Implementations use `std::construct_at` and `std::destroy_at` ([[specialized.construct]]) to construct and destroy in the storage, and these are valid in constant evaluation:

```cpp run ok
#include <optional>
#include <string>

constexpr std::size_t f() {
  std::optional<std::string> s;
  s.emplace("constexpr");
  s = std::nullopt;
  s = "again";
  return s->size();
}
static_assert(f() == 5);

constexpr std::optional<int> g = 42;
static_assert(*g == 42 && g.value_or(0) == 42);
int main() {}
```

Dereferencing an empty optional during constant evaluation would read an inactive member of the union, which is core-language UB, so such an expression is not a constant expression ([[expr.const]]) and the compiler must report an error.

## Common misconceptions

!!! pitfall "A moved-from optional is empty"
    After `auto b = std::move(a);`, `a.has_value()` is unchanged (¶9). `a` holds a `T` in a moved-from state, not an empty optional. To empty it, call `a.reset()` explicitly.

!!! pitfall "`optional<T>` can replace a nullable pointer parameter"
    `optional<T>` owns and embeds its value; copying the optional copies the value. `f(std::optional<BigObject>)` copies the large object on every call. Use `const BigObject*` there, or C++26's `optional<const BigObject&>` ([[optional.optional.ref]]).

!!! pitfall "`optional<double>` is only one byte bigger than `double`"
    With the extra `bool` plus alignment padding, `sizeof(optional<double>)` is usually 16. Storing `optional<T>` in a large array can double the memory; consider sentinel values or a separate bitmap.

## Questions

!!! question "Question 1"
    After `std::optional<std::any> a = std::optional<int>{};`, what is `a.has_value()`? What if `std::any` is replaced with `bool`? Which constraints decide these two results?

<details markdown="1">
<summary>Answer</summary>

`optional<any>` has a value. `std::any` can be constructed from any form of `optional<int>`, so *converts-from-any-cvref*`<any, optional<int>>` is true, and ¶28.2 and ¶33.2 keep both converting constructors out of overload resolution. What remains is `optional(U&&)` with `U = optional<int>`; ¶23.3 only excludes `optional<any>` itself, so *val* is initialized to an `any` holding an empty `optional<int>`.

`optional<bool>` has no value. ¶28.2 does not apply to cv `bool`, so the converting constructors are viable; ¶23.4 in turn excludes `optional(U&&)`. So the conversion is value-wise, and empty becomes empty.
</details>

!!! question "Question 2"
    If the *Returns* of `transform` said it is equivalent to `return optional<U>(in_place, invoke(std::forward<F>(f), val));`, what kind of `f` would stop working?

<details markdown="1">
<summary>Answer</summary>

An `f` returning a non-movable type, such as a class holding a `std::mutex`, or a class like `Pinned` with a deleted move constructor. The parameters of the `in_place` constructor are forwarding references; when the prvalue of `invoke(...)` binds to one, it is materialized as a temporary object, and *val* is then move-constructed from that temporary. The current wording requires *val* to be initialized directly with `invoke(...)`, so the prvalue constructs the target object directly, and Note 1 makes it explicit that `U` need not be movable.
</details>

!!! question "Question 3"
    Is `optional<unique_ptr<int>>` trivially copyable?

<details markdown="1">
<summary>Answer</summary>

No. `unique_ptr`'s move constructor and destructor are not trivial, so by [[optional.ctor#12]] and [[optional.dtor#2]] the move constructor and destructor of `optional<unique_ptr<int>>` are not trivial either, and trivial copyability requires a trivial destructor.
</details>
