---
title: Strong types and phantom types
summary: "Using a class that wraps a single value to split quantities with the same representation but different meanings into different types: why typedef can't do it, the Strong<T, Tag> template and phantom tags, adding operations as needed, the conditions for zero overhead and the assembly, enum class as a strong integer, chrono::duration, std::byte and align_val_t in the standard library, unit conversions, and traps around implicit conversions, hashing and formatting."
tags: strong types, phantom types, enum class, chrono, zero overhead, idiom
updated: 2026-10-19
---

!!! tldr
    - `typedef` and `using` only give an existing type another name; when `AccountId` and `Cents` are both `int`, the compiler can't tell them apart. To get the compiler to check, you need to introduce new types.
    - `Strong<T, Tag>` is a class template with a single `T` member and an `explicit` constructor; `Tag` is just a class name that is never defined, used to make each specialization a different type. A parameter that acts only at the type level like this is called a phantom type.
    - Operations are added as needed: comparison through a defaulted `<=>`, addition, scaling and the like mixed in through CRTP skill bases. The bases must bring their own defaulted comparisons, or the derived class's defaulted `<=>` is defined as deleted.
    - As long as the class is trivially copyable, it is the same size as a bare `int`, generates exactly the same instructions at `-O2`, and is passed in registers by value; adding a user-provided destructor switches it to being passed through memory.
    - For integer IDs, `enum class Id : std::uint32_t {}` is the least-effort strong type: since C++17 you can write `Id{42}`, and it comes with comparisons and `std::hash`; but `std::format` doesn't know it, and a custom `Strong` likewise needs specializations of `std::hash` and `std::formatter`.

## Same representation, different meaning

```cpp run title="alias.cpp" ok
#include <cstdio>

using AccountId = int;
using Cents = int;

void transfer(AccountId from, AccountId to, Cents amount) {
  std::printf("%d -> %d: %d\n", from, to, amount);
}

int main() {
  AccountId alice = 17, bob = 42;
  Cents fee = 500;
  transfer(alice, bob, fee);   // as intended
  transfer(fee, alice, bob);   // arguments in the wrong order, still compiles
}
```

The second call treats the amount as the source account, the compiler gives no warning, and at run time it prints `500 -> 17: 42`. The program itself is well-formed; the logic is wrong. The three parameters are written with three different names, which looks like type checking but isn't.

The reason is in [[dcl.typedef#1]]: a name declared by typedef is a **type alias** ([[g:type-alias|type alias]]) that refers to an existing type and introduces no new type. An alias declaration `using X = Y;` has the same semantics as typedef ([[dcl.typedef#2]]).

!!! std
    A *typedef-name* does not introduce a new type the way a class declaration or enum declaration does.

    A typedef-name doesn't introduce a new type the way a class or enumeration declaration does.

So `AccountId`, `Cents` and `int` are the same type, and neither overload resolution nor type checking can tell them apart. For the compiler to catch this kind of mistake, you need a declaration that introduces a new type: a class or an enumeration.

## The minimal strong type template

A **strong type** (also called a strong typedef) is a class that wraps a single value; it has the same representation as the wrapped type, but the two don't convert implicitly into each other. Written as a template, one definition can produce any number of such types:

```cpp run title="strong.cpp" error
#include <compare>

template <class T, class Tag>
class Strong {
  T value_;
public:
  constexpr explicit Strong(T v) : value_(v) {}
  constexpr const T& get() const { return value_; }
  friend constexpr auto operator<=>(const Strong&,
                                    const Strong&) = default;
};

using AccountId = Strong<int, struct AccountIdTag>;
using Cents     = Strong<int, struct CentsTag>;

void transfer(AccountId from, AccountId to, Cents amount);

void test() {
  AccountId alice{17}, bob{42};
  Cents fee{500};
  transfer(alice, bob, fee);   // OK
  transfer(fee, alice, bob);   // error: Cents does not convert to AccountId
  transfer(17, 42, 500);       // error: the constructor is explicit
  bool b = alice < bob;        // OK: defaulted <=>
  bool c = alice == fee;       // error: different types
}
```

The template has just three parts, each corresponding to a language rule.

- An `explicit` constructor doesn't take part in implicit conversions; it is used only in direct-initialization and explicit casts ([[class.conv.ctor#2]]). So `transfer(17, 42, 500)` finds no conversion from `int` to `AccountId`, while `AccountId{17}` works.
- A defaulted `operator<=>` compares subobjects one by one ([[class.compare.default#5]]), and if the class declares no `operator==`, a defaulted `==` is also implicitly declared ([[class.compare.default#4]]). So all six comparisons, `<`, `==` and the rest, are available, and only between values of the same `Strong` specialization.
- `get()` is the only way to the underlying value. Places that need the bare value (serialization, calling C interfaces) must spell it out explicitly, which is exactly what we want.

### Phantom tags

`AccountId` and `Cents` both have `int` as `T`; only the second template argument tells them apart. `struct AccountIdTag` is an **elaborated type specifier**: if looking up `AccountIdTag` at that point finds nothing, it declares a class of that name in the nearest enclosing namespace ([[dcl.type.elab#3]]). That class is never defined, so it is an incomplete type, and a type template argument may be an incomplete type anyway (note in [[temp.arg.type#2]]).

`Strong`'s implementation never uses `Tag`: it creates no `Tag` object and never takes its size, so it doesn't need it to be complete. A template parameter like this that appears only in the type and corresponds to no data is called a **phantom type**. Its sole purpose is to make `Strong<int, AccountIdTag>` and `Strong<int, CentsTag>` two different class template specializations.

Tags are identified only by name. Writing `Strong<int, struct Tag>` twice in the same namespace gives the same type, because the second lookup finds the `Tag` declared the first time. Each strong type should use its own dedicated tag name.

<details class="fine" markdown="1"><summary>Tags take part in ADL</summary>

When argument-dependent lookup (ADL) collects the associated entities of a class template specialization, it also collects those of the types of its template arguments ([[basic.lookup.argdep#3.3]]). If a tag is declared in namespace `bank`, an unqualified call with a `Strong<int, bank::AccountIdTag>` argument will also look for functions in `bank`. This is usually harmless, but putting tags in a namespace full of generic function templates can unexpectedly add candidate functions.
</details>

## Adding operations as needed

`Strong` provides only comparisons. Whether other operations are needed depends on what the quantity means: adding account IDs makes no sense, amounts can be added, an amount can be multiplied by a ratio, but not by another amount. The sensible approach is for each strong type to declare which operations it needs.

A common technique makes each operation a **skill** base class, passes the derived type to it with [[patterns/crtp|CRTP]], and inherits from them as needed, like a [[patterns/mixin|mixin]]:

```cpp run title="skills.cpp" ok
#include <compare>
#include <cstdio>
#include <type_traits>

template <class D> struct Addable {
  friend constexpr D operator+(D a, D b) {
    return D{a.get() + b.get()};
  }
  friend constexpr D& operator+=(D& a, D b) { return a = a + b; }
  friend constexpr auto operator<=>(const Addable&,
                                    const Addable&) = default;
};

template <class D> struct Scalable {
  template <class S>
    requires std::is_arithmetic_v<S>
  friend constexpr D operator*(D a, S k) { return D{a.get() * k}; }
  friend constexpr auto operator<=>(const Scalable&,
                                    const Scalable&) = default;
};

template <class T, class Tag, template <class> class... Skills>
class Strong : public Skills<Strong<T, Tag, Skills...>>... {
  T value_;
public:
  constexpr explicit Strong(T v) : value_(v) {}
  constexpr const T& get() const { return value_; }
  friend constexpr auto operator<=>(const Strong&,
                                    const Strong&) = default;
};

using AccountId = Strong<int, struct AccountIdTag>;
using Cents = Strong<long, struct CentsTag, Addable, Scalable>;

static_assert(sizeof(Cents) == sizeof(long));
static_assert(std::is_trivially_copyable_v<Cents>);

int main() {
  Cents a{250}, b{100};
  a += b;
  Cents c = a * 2;
  std::printf("%ld %d\n", c.get(), a < c);
  // AccountId{1} + AccountId{2};  // error: AccountId has no Addable
}
```

It prints `700 1`. The operators are all friend functions defined in the class (hidden friends), findable only through ADL, i.e. they take part in overload resolution only when `Cents` appears among the arguments, and don't pollute other types' candidate sets (see [[topics/name-lookup-and-customization]]). Neither `Cents{1} * Cents{2}` nor `AccountId{1} + AccountId{2}` finds a usable operator, and both fail to compile.

The defaulted `<=>` line in each skill is not decoration. A defaulted comparison compares element by element over the expanded list of subobjects, first the direct base class subobjects, then the members ([[class.compare.default#5]]). If any subobject's `<=>` is unusable, the defaulted `<=>` is defined as deleted ([[class.spaceship#2]]), and likewise `==` ([[class.eq#2]]). If the empty `Addable<D>` declared no comparison, `Cents`'s `<=>` and `==` would both be deleted, and Clang reports `overload resolution selected deleted operator '<=>'`. The alternative is to hand-write the comparisons in `Strong`, comparing only `value_`.

Whether an operation should be provided can be judged by the nature of the quantity:

| Quantity | Sensible operations | Operations it shouldn't have |
|---|---|---|
| Identifiers (IDs, handles) | `==`, hashing, perhaps `<` (for ordered containers) | any arithmetic |
| Amounts (money, lengths, durations) | `+`, `-`, multiplying and dividing by scalars, dividing two of the same to get a scalar | multiplying two of the same (the dimension changes) |
| Positions (instants, coordinates) | position minus position gives an amount; position plus or minus an amount | position plus position |

The last row is why `std::chrono` distinguishes `time_point` from `duration`: subtracting two instants gives a duration, while adding two instants makes no sense.

## Zero overhead: size, triviality and assembly

The value of a strong type lies in being no slower than the bare value. That promise has two preconditions: the object is the same size, and the class is trivially copyable. The `static_assert` above already verified the former: `Cents` has two empty bases, yet its size with Clang in our tests is still `sizeof(long)`, because the two empty bases are of different types and the empty base optimization makes them take no space (layout details in [[toolchain/object-layout-and-vtables]]).

!!! impl "MSVC and multiple empty bases"
    On x64, MSVC by default applies the empty base optimization only to the first empty base; each subsequent empty base takes at least one byte, so `Cents` grows. Adding `__declspec(empty_bases)` to `Strong` restores it. When using skill bases, it's worth putting a `static_assert(sizeof(...) == sizeof(T))` in the code.

For a **trivially copyable** class ([[g:trivially-copyable-class|trivially copyable]]), copying, moving and destruction run no user code ([[class.prop#1]]). `Strong`'s special members are all implicitly declared by the compiler, so it qualifies naturally. Compile it alongside a bare `long`:

```cpp run title="codegen.cpp" ok flags="-std=c++2c -O2"
template <class T, class Tag>
class Strong {
  T value_;
public:
  constexpr explicit Strong(T v) : value_(v) {}
  constexpr T get() const { return value_; }
};

template <class T, class Tag>
class Logged {                     // has one extra user-provided destructor
  T value_;
public:
  constexpr explicit Logged(T v) : value_(v) {}
  constexpr T get() const { return value_; }
  ~Logged() {}
};

using Cents  = Strong<long, struct CentsTag>;
using LCents = Logged<long, struct CentsTag>;

long  add_raw(long a, long b)       { return a + b; }
Cents add_strong(Cents a, Cents b)  { return Cents{a.get() + b.get()}; }
LCents add_logged(LCents a, LCents b) {
  return LCents{a.get() + b.get()};
}
```

The function bodies Clang 23 generates with `-O2 --target=x86_64-linux-gnu -masm=intel` (assembler directives removed):

```text
add_raw:                  add_strong:              add_logged:
  lea rax, [rdi + rsi]      lea rax, [rdi + rsi]     mov rax, rdi
  ret                       ret                      mov rcx, qword ptr [rdx]
                                                     add rcx, qword ptr [rsi]
                                                     mov qword ptr [rdi], rcx
                                                     ret
```

`add_strong` and `add_raw` are identical: the two arguments in `rdi` and `rsi`, the result in `rax`. In `add_logged`, each argument becomes an address (`rsi`, `rdx`), and the result is written into memory the caller passes via `rdi`. arm64 in our tests behaves the same way: the first two functions are both `add x0, x1, x0; ret`, and the third reads two values from the memory `x0` and `x1` point to, then writes to where `x8` points.

This dividing line comes from [[class.temporary#3]]. When an object is passed to or returned from a function by value, if the class has at least one eligible copy or move constructor, all of them trivial, and a trivial or deleted destructor, the implementation may create a temporary object to hold the parameter or return value, i.e. put it in a register and take it back out.

!!! std
    This latitude is granted to allow objects to be passed to or returned from functions in registers.

    This freedom is granted so that objects can be passed to and returned from functions in registers.

Note that this condition is slightly broader than trivially copyable: it ignores assignment operators. `Logged`, with just one extra destructor that does nothing, no longer meets the condition, and the Itanium C++ ABI says such classes are passed through memory (details and `[[clang::trivial_abi]]` on the [[class.temporary]] page). When adding destructors for logging or debug checks to a strong type, be aware that this changes the calling convention.

The difference at call sites disappears just the same. Write a summing loop with `Cents` from `skills.cpp` and compare it with a version summing a `long` array:

```cpp
long sum_raw(const long* p, std::size_t n) {
  long s = 0;
  for (std::size_t i = 0; i < n; ++i) s += p[i];
  return s;
}
Cents sum_strong(const Cents* p, std::size_t n) {
  Cents s{0};
  for (std::size_t i = 0; i < n; ++i) s += p[i];
  return s;
}
```

At `-O2` in our tests, the two functions generate identical instruction sequences (35 instructions on x86-64, both vectorized into `paddq`; 39 on arm64). `operator+=`, `operator+`, the constructor and `get()` are all inlined, leaving nothing behind.

## `enum class` as a strong integer

If the wrapped type is an integer and only comparisons and hashing are needed, there is a way that requires no class at all:

```cpp run title="enum-id.cpp" error
#include <cstdint>
#include <unordered_set>
#include <utility>

enum class UserId  : std::uint32_t {};
enum class OrderId : std::uint32_t {};

void cancel(UserId who, OrderId what);

void test(std::uint32_t raw) {
  UserId u{raw};                    // OK: direct-list-initialization
  OrderId o{7};                     // OK
  cancel(u, o);                     // OK
  cancel(o, u);                     // error: different types
  UserId v = raw;                   // error: no implicit conversion
  UserId w = {raw};                 // error: copy-list-initialization
  UserId x{-1};                     // error: narrowing
  auto n = std::to_underlying(u);   // std::uint32_t
  std::unordered_set<UserId> seen;  // OK: enums have std::hash
  bool lt = u < UserId{3};          // OK: built-in comparison within the same type
}
```

A scoped enumeration with no enumerators is a new integer type. Its underlying type is fixed, so every value of `std::uint32_t` is a valid value of it ([[dcl.enum#8]]), and there is no out-of-range problem.

`UserId u{raw}` compiles thanks to a list-initialization rule added in C++17 ([[dcl.init.list#3.8]]): if the target is an enumeration with a fixed underlying type, the initializer list has a single scalar element implicitly convertible to the underlying type, and it is direct-list-initialization, then the object is initialized to `T(v)`. Narrowing conversions are still ill-formed, so `UserId x{-1}` is rejected. The rule applies only to direct-list-initialization; neither `UserId w = {raw}` nor passing `{42}` to a `UserId` parameter works, so implicit conversion can't sneak back in through braces.

The underlying value is obtained with `std::to_underlying` (C++23) or `static_cast` ([[expr.static.cast#7]]). Comparisons are built in, and `std::hash` has an enabled specialization for every enumeration type ([[unord.hash#2]]), so `UserId` can be used directly as an `unordered_set` key.

<div class="compare" markdown="1">

```cpp
// class template: can have invariants and member functions
using UserId =
  Strong<std::uint32_t, struct UserTag>;
UserId u{42};
auto raw = u.get();
// std::hash must be specialized yourself
```

```cpp
// enum class: just a new integer type
enum class UserId : std::uint32_t {};

UserId u{42};
auto raw = std::to_underlying(u);
// std::hash is available out of the box
```

</div>

The limitations of `enum class` also stem from it not being a class: no member functions, no invariant checks at construction (such as an ID never being 0), and arithmetic can only be added one non-member operator overload at a time. Quantities whose representation isn't an integer (a length as a `double`, a name as a `std::string`) can only use a class template.

## Strong types in the standard library

### `std::chrono::duration`: the ratio is a phantom parameter

`duration<Rep, Period>` has a single data member of type `Rep` ([[time.duration]]). `Period` is a specialization of `std::ratio` giving how many seconds one tick is: `milliseconds` is `duration<an integer type, std::milli>`, with `std::milli` being `ratio<1, 1000>`. No `ratio` object is ever created; it takes part in compile-time computation only through its static members `num` and `den`, making it a phantom parameter with arithmetic.

```cpp run title="chrono.cpp" ok
#include <chrono>
#include <print>
#include <type_traits>
using namespace std::chrono;

static_assert(std::is_same_v<milliseconds::period, std::milli>);
static_assert(sizeof(milliseconds) == sizeof(milliseconds::rep));

int main() {
  milliseconds a = 2s;                         // OK: lossless
  // seconds b = 1500ms;                       // error: would truncate
  seconds c = duration_cast<seconds>(1500ms);  // explicit truncation: 1s
  auto d = 1s + 250ms;                         // milliseconds
  duration<double> e = 1500ms;                 // OK: floating-point representation
  std::println("{} {} {} {}", a, c, d, e);
}
```

It prints `2000ms 1s 1250ms 1.5s`. The constructor converting from another `duration` is not `explicit`, but it is constrained ([[time.duration.cons#3]]): the target has a floating-point representation, or the source period is an integer multiple of the target period. So seconds convert implicitly to milliseconds, but milliseconds don't convert to seconds; truncation must be explicit with `duration_cast`. This matches the idea of `Strong` on this page: lossless conversions can be implicit, conversions that might go wrong must be written out.

The constructor from a bare number is `explicit` ([[time.duration.cons#1]]), so `seconds s = 5;` doesn't compile.

### `std::byte`, `std::align_val_t`, and `size_t`, which is just an alias

```cpp run title="std-strong.cpp" ok
#include <cstddef>
#include <cstdio>
#include <new>

int main() {
  std::byte b{0x3f};
  b <<= 1;
  b |= std::byte{1};
  // b + 1;                       // error: byte has no arithmetic
  std::printf("%d\n", std::to_integer<int>(b));

  void* p = ::operator new(256, std::align_val_t{64});
  ::operator delete(p, std::align_val_t{64});
  // ::operator new(256, 64);     // error: 64 is not an align_val_t

  std::size_t s = -1;             // just an alias for an unsigned integer type
  std::ptrdiff_t d = s;           // converts implicitly in both directions
  std::printf("%zu %td\n", s, d);
}
```

`std::byte` is declared as `enum class byte : unsigned char {}` ([[support.types]]); it represents a byte of raw memory, not a number. The standard library provides only bitwise operations and shifts for it ([[support.types.byteops]]), no addition, subtraction, multiplication or division, and converting to an integer requires `std::to_integer`.

`std::align_val_t` is declared as `enum class align_val_t : size_t {}` ([[new.syn]]). The signature of the aligned allocation functions is `operator new(std::size_t, std::align_val_t)`. If the alignment were also a `std::size_t`, this signature would collide with a placement form `operator new(std::size_t, std::size_t)` that a program might define itself; as a distinct type, `new (64) T` cannot be mistaken for an aligned allocation.

`std::size_t` and `std::ptrdiff_t` are the counterexample: they are typedefs ([[support.types.layout]]), mere aliases of some integer type. In the example above, `-1` converts implicitly to the maximum value of `size_t` and then implicitly back to `ptrdiff_t` as `-1`, with no warnings under `-Wall -Wextra`. The standard library's type system won't help you check mixing of indices, lengths and differences.

## Units and dimensions

`duration`'s approach generalizes to any physical quantity: add another phantom parameter for the dimension, and use `std::ratio` for the unit's multiple of the base unit.

```cpp run title="units.cpp" ok
#include <compare>
#include <cstdio>
#include <ratio>

template <class Dim, class Rep, class Ratio>
class Quantity {
  Rep n_;
public:
  constexpr explicit Quantity(Rep n) : n_(n) {}

  // only lossless conversions: R2 is an integer multiple of Ratio
  template <class R2>
    requires (std::ratio_divide<R2, Ratio>::den == 1)
  constexpr Quantity(Quantity<Dim, Rep, R2> q)
      : n_(q.count() * std::ratio_divide<R2, Ratio>::num) {}

  constexpr Rep count() const { return n_; }

  friend constexpr Quantity operator+(Quantity a, Quantity b) {
    return Quantity{a.n_ + b.n_};
  }
  friend constexpr auto operator<=>(Quantity, Quantity) = default;
};

struct Length;   // dimension tags: declared, never defined
struct Mass;

template <class R> using Len = Quantity<Length, long, R>;
using Millimeters = Len<std::milli>;
using Meters      = Len<std::ratio<1>>;
using Kilometers  = Len<std::kilo>;
using Grams       = Quantity<Mass, long, std::ratio<1>>;

static_assert(sizeof(Kilometers) == sizeof(long));

int main() {
  Millimeters a = Kilometers{2};       // OK: 2'000'000 mm
  auto b = Kilometers{1} + Meters{5};  // Meters: km converted to m
  // Kilometers c = Meters{5};         // error: would lose precision
  // auto d = Meters{1} + Grams{1};    // error: different dimensions
  std::printf("%ld %ld %d\n", a.count(), b.count(),
              Kilometers{1} > Meters{999});
}
```

It prints `2000000 1005 1`. The result type of `Kilometers{1} + Meters{5}` is decided by overload resolution. ADL finds one hidden friend `operator+` in each of the two specializations: the `Kilometers` version needs `Meters` converted to `Kilometers`, but `ratio_divide<ratio<1>, kilo>` has denominator 1000, the constraint fails, and it is not viable; the `Meters` version only needs `Kilometers` converted to `Meters`, which is viable. So the result automatically lands in the finer unit, with no extra code for finding a common unit.

The converting constructor does a single multiplication, and `ratio_divide` is computed at compile time, so there is no extra run-time cost. A real units library also does dimensional algebra (length divided by time gives velocity), which requires representing dimensions as lists of exponents of base quantities; the idea is the same, just with more type computation, which belongs to [[topics/compile-time-programming]].

## Traps

### Implicit conversions sneak back in

```cpp run title="leaky.cpp" ok
#include <cstdio>

template <class T, class Tag>
class Leaky {
  T value_;
public:
  Leaky(T v) : value_(v) {}                // forgot explicit
  operator T() const { return value_; }    // converts back to T implicitly
};

using Meters  = Leaky<double, struct MetersTag>;
using Seconds = Leaky<double, struct SecondsTag>;

double speed(Meters d, Seconds t) { return d / t; }

int main() {
  Meters d = 100.0;
  Seconds t = 9.58;
  Meters total = d + t;            // compiles: both sides convert to double first
  double v = speed(9.58, 100.0);   // compiles: double -> Meters
  std::printf("%.2f %.4f\n", static_cast<double>(total), v);
}
```

Both are well-formed, printing `109.58 0.0958`, and both results are meaningless. The non-`explicit` constructor lets a bare `double` become any `Leaky`, and the implicit conversion function lets any `Leaky` turn back into a `double`, so `d + t` first converts both sides to `double`, adds them, and finally converts implicitly into `Meters`.

The language itself gives a little protection: at most one user-defined conversion is implicitly applied to a single value ([[class.conv.general#4]]), so a chain like `Seconds → double → Meters` in `speed(t, d)` doesn't work. But as soon as implicit conversion is allowed in either direction, mixing has a loophole. Always make constructors `explicit`; when the bare value is needed, use a named function `get()`, or at least make the conversion function `explicit` too.

### `explicit` constructors still accept narrowing

When `price` in `Cents(price)` is a `double`, `explicit Strong(long)` is still selected and the fractional part is silently truncated, with no warning under `-Wall -Wextra` in our tests (Clang gives `-Wliteral-conversion` only when the argument is a literal). Two remedies:

- Get into the habit of constructing with braces: `Cents{price}` requires a narrowing conversion and is ill-formed ([[dcl.init.list#3.7]]).
- Add a deleted constructor template to the class: `template <class U> Strong(U) = delete;`. When the argument type is exactly `T`, the non-template constructor is as good as the template, and the non-template wins; any other type matches the template exactly, selecting the deleted function and failing to compile. The cost is that even `Cents(299)` has to be written `Cents(299L)`.

### Hashing and formatting don't follow automatically

`std::hash` and `std::formatter` are disabled for types without specializations ([[unord.hash#2]], [[format.formatter.spec#5]]), so neither `std::unordered_map<AccountId, int>` nor `std::format("{}", id)` compiles. For `enum class`, `std::hash` is available out of the box, but `std::formatter` still isn't. A program may add specializations to `std` that depend on program-defined types ([[namespace.std#2]]), and one specialization can cover the whole template:

```cpp run title="hash-format.cpp" ok
#include <compare>
#include <cstdint>
#include <format>
#include <functional>
#include <print>
#include <unordered_map>
#include <utility>

template <class T, class Tag>
class Strong {
  T value_;
public:
  constexpr explicit Strong(T v) : value_(v) {}
  constexpr const T& get() const { return value_; }
  friend constexpr auto operator<=>(const Strong&,
                                    const Strong&) = default;
};

template <class T, class Tag>
struct std::hash<Strong<T, Tag>> {
  std::size_t operator()(const Strong<T, Tag>& s) const noexcept {
    return std::hash<T>{}(s.get());
  }
};

template <class T, class Tag, class CharT>
struct std::formatter<Strong<T, Tag>, CharT> : std::formatter<T, CharT> {
  auto format(const Strong<T, Tag>& s, auto& ctx) const {
    return std::formatter<T, CharT>::format(s.get(), ctx);
  }
};

enum class OrderId : std::uint32_t {};

template <class CharT>
struct std::formatter<OrderId, CharT>
    : std::formatter<std::uint32_t, CharT> {
  auto format(OrderId id, auto& ctx) const {
    return std::formatter<std::uint32_t, CharT>::format(
        std::to_underlying(id), ctx);
  }
};

using AccountId = Strong<int, struct AccountIdTag>;

int main() {
  std::unordered_map<AccountId, int> balance;
  balance[AccountId{17}] = 500;
  std::println("{:>6} -> {}", AccountId{17}, balance[AccountId{17}]);
  std::println("order #{:08x}", OrderId{0xbeef});
}
```

It prints `    17 -> 500` and `order #0000beef`. The `formatter` specializations inherit the underlying type's `formatter` and reuse its `parse`, so format specs like `{:>6}` and `{:08x}` work as usual. `unordered_map` also needs `==`, which comes from the `operator==` implicitly declared by the defaulted `<=>`.

These two specializations are partial specializations covering every `Strong<T, Tag>`. If some `T` itself has no `std::hash` or `std::formatter`, the corresponding `Strong` specialization fails only when used.

## When to use them

| Situation | Recommendation |
|---|---|
| A function has several parameters of the same type that are easy to mix up | strong types; or [[patterns/named-parameters\|named parameters]] |
| Integer IDs and handles that only need comparison and hashing | `enum class Id : integer-type {}` |
| Invariant checks, non-integer representations or member functions needed | the `Strong<T, Tag>` class template |
| Quantities with units or dimensions | a `duration`-style `Quantity<Dim, Rep, Ratio>`, or an existing units library |
| Time | use `std::chrono` directly; don't wrap your own |
| Local variables and intermediate values inside implementation details | not worth it; names and comments are enough |
| The underlying value needs to take part in all sorts of arithmetic | operations keep piling up until it's a bare value again; first confirm the quantity really has its own meaning |

## Questions

!!! question "1"
    Which of these four lines compile? `enum class Handle : std::uint32_t {}; void f(Handle);`, then `Handle a{42};`, `Handle b = {42};`, `f({42});`, `f(Handle{42});`.

<details markdown="1">
<summary>Answer</summary>

The first and fourth compile; the second and third are ill-formed. [[dcl.init.list#3.8]] applies only to direct-list-initialization: `Handle a{42}` and the functional cast `Handle{42}` are both direct-list-initialization; `Handle b = {42}` is copy-list-initialization, and `f({42})` initializes the parameter from a braced list, also copy-list-initialization, so the rule applies to neither. The example for this bullet in the standard lists the same four cases.
</details>

!!! question "2"
    For debugging, you add a destructor to `Strong` that checks invariants on destruction, enabled only in debug builds. What ABI difference will there be between `Strong` in release and debug builds?

<details markdown="1">
<summary>Answer</summary>

In debug builds the destructor is user-provided and no longer trivial, so the class fails the condition of [[class.temporary#3]], and under the Itanium ABI it is passed by address when passed by value (see the assembly of `add_logged` above); in release builds it is still passed in registers. `sizeof` is unchanged, but the calling convention differs. If object files from the two builds are linked together, the two sides disagree about functions taking `Strong` parameters, which is an ODR violation, no diagnostic required ([[basic.def.odr]]). Such conditional compilation belongs where it doesn't affect the class definition, such as assertions inside member functions.
</details>

!!! question "3"
    `std::chrono::milliseconds m = 2s;` compiles, `std::chrono::seconds s = 1500ms;` doesn't, yet `duration<double> d = 1500ms;` compiles. Do all three use the same constructor template? What distinguishes them?

<details markdown="1">
<summary>Answer</summary>

They all use the same non-`explicit` converting constructor template, `template<class Rep2, class Period2> duration(const duration<Rep2, Period2>&)`; the difference lies in its constraints ([[time.duration.cons#3]]): always satisfied when the target's `rep` is a floating-point type; otherwise `ratio_divide<Period2, period>::den` must be 1 and the source `Rep2` must not be floating-point. Seconds to milliseconds has ratio 1000/1, satisfied; milliseconds to seconds is 1/1000, not satisfied, so the candidate is removed and no other conversion is available; to `duration<double>` the target is floating-point, satisfied. The constraint removes truncating conversions from the implicit ones, leaving them to an explicit `duration_cast`.
</details>
