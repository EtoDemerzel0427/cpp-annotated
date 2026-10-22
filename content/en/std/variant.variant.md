---
title: Class template variant
summary: "Construction, destruction, assignment, emplace, swap and status queries of variant, including how converting construction picks a type, when a variant becomes valueless, and when the special members are trivial."
updated: 2026-10-19
---

!!! tldr
    - `variant<Ts...>` keeps its current value inside the object in a block of union storage plus an index; the standard does not allow the value to be put on the heap.
    - `variant<std::string, bool> v = "abc";` chooses `string`: converting construction performs overload resolution over the alternatives, after first removing candidates that would involve narrowing (since C++20).
    - If a type-changing `emplace` or assignment throws while constructing the new value, the variant may end up holding no value at all; then `valueless_by_exception()` is true and `index()` returns `variant_npos`.
    - When construction may throw but moving does not, assignment first constructs a temporary on the side, preserving the old value; `emplace` has no such protection.
    - When a given special member is trivial for every alternative, the variant's corresponding member is trivial too, so `variant<int, double>` is a trivially copyable type.

For access, comparison and hashing, see [[variant]]; for `std::visit`, see [[variant.visit]].

## A union plus an index

In memory, `variant<int, std::string>` looks roughly like this:

```cpp
struct variant_int_string {
  union { int i; std::string s; } storage;  // only one member is active at a time
  unsigned index;                           // 0, 1, or a special value meaning no value
};
```

The type parameters of a variant are called its **alternatives**. Everything the member functions do boils down to this: use the index to know which member of the union is alive, and when switching types, end the lifetime of the old member and begin the lifetime of the new one ([[basic.life]]).

The hard part is the switch. If the old value is destroyed first and then the new one constructed, and construction throws, there is nothing left in the union. The valueless state and the various branches in assignment discussed below all deal with this problem.

¶1 The standard writes this model in two sentences: at any moment a variant either holds a value of one of its alternative types or holds no value; when it holds a value, that value is called the **contained value**, and it is nested within the variant object ([[intro.object]]).

Being nested within the object means no heap allocation. Boost.Variant puts a backup on the heap when an exception occurs; `std::variant` is not allowed to do that, and this decides all the exception-safety trade-offs that follow.

### Requirements on the alternatives

¶2 Every alternative must meet *Cpp17Destructible* ([[utility.arg.requirements]]). Per the note below that table, array types and non-object types (references, `void`, functions) do not meet it, so `variant<int&>`, `variant<int[3]>` and `variant<void>` are all disallowed.

This is a requirement on the program and the standard does not require a diagnostic, but implementations all report an error directly. libc++ uses `static_assert` in the class body to give messages such as "variant can not have a reference type as an alternative".

¶3 A program that instantiates the definition of `variant<>` with no template arguments is ill-formed. Merely mentioning `variant<>` where a complete type is not needed is not an error.

## Construction ([variant.ctor])

¶1 Below, `T_i` denotes the `i`th type in `Types`.

### Default construction

¶2 Default construction looks only at the first alternative: the constraint is that `T_0` is default-constructible, and the effect is to value-initialize a `T_0`, after which `index() == 0`. Whether it is `constexpr` and whether it is `noexcept` also depend on the value-initialization of `T_0`.

When the first type cannot be default-constructed, the idiom is to put a `std::monostate` at the front ([[variant]]): `variant<std::monostate, Socket, File>` holds a `monostate` when default-constructed.

### Copy, move and triviality

¶7 Copy construction direct-initializes the same alternative from the source object's contained value; when the source is valueless, the new object is valueless too. Move construction (¶11) works the same way.

¶9 If any `T_i` is not copy-constructible, the copy constructor is defined as deleted. ¶10 The move constructor, on the other hand, is written as a constraint: it participates in overload resolution only when all `T_i` are move-constructible. This difference makes the variant behave like an ordinary class: when no move constructor is usable, `variant(std::move(x))` falls back to the copy constructor.

Paragraphs 9 and 13 also specify that when the copy (move) constructors of all `T_i` are trivial, the variant's copy (move) constructor is trivial too; [variant.dtor]/2 says the same for the destructor.

```cpp run title="variant-triviality.cpp" ok
#include <string>
#include <type_traits>
#include <variant>

using V1 = std::variant<int, double, char>;
static_assert(std::is_trivially_copyable_v<V1>);
static_assert(std::is_trivially_destructible_v<V1>);

using V2 = std::variant<int, std::string>;
static_assert(!std::is_trivially_copyable_v<V2>);
static_assert(std::is_copy_constructible_v<V2>);

struct MoveOnly { MoveOnly(MoveOnly&&) = default; };
using V3 = std::variant<int, MoveOnly>;
static_assert(!std::is_copy_constructible_v<V3>);  // ¶9: deleted
static_assert(std::is_move_constructible_v<V3>);

int main() {}
```

Triviality has practical consequences: it determines whether a type is trivially copyable ([[g:trivially-copyable-type]]), which in turn determines whether it can be `memcpy`'d and passed in registers. The Itanium C++ ABI specifies that a type with a non-trivial copy constructor or destructor must be passed through memory when passed by value. The original C++17 specification had none of these triviality requirements; [[P0602R4]] added them.

!!! impl "How libraries implement conditional triviality"
    The C++17 language cannot directly express "this special member is `= default` under some condition and hand-written otherwise". Implementations can only use a chain of conditional base classes: each base layer chooses one of three partial specializations, `= default`, hand-written or `= delete`, based on type traits, and the outermost class's own special members are all `= default`, so triviality propagates up from the bases.

    C++20's [[P0848R3]] allows a class to declare several prospective special members with requires-clauses, with the constraints selecting the eligible one ([[g:eligible-special-member-function]]), so one can write directly:

    ```cpp
    ~variant() requires (std::is_trivially_destructible_v<Ts> && ...) = default;
    ~variant() { /* destroy according to the index */ }
    ```

    libc++ still uses the base-class ladder for compatibility with C++17 mode; see the implementation section below.

### Converting construction: which alternative to choose

`template<class T> variant(T&&)` accepts any argument and has to choose automatically which alternative will store it. The results of the following lines under the current standard were not all the same in C++17:

```cpp run title="p0608.cpp" ok
#include <cassert>
#include <string>
#include <variant>

int main() {
  std::variant<std::string, bool> a = "abc";
  assert(a.index() == 0);  // string; the original C++17 rule chose bool

  std::variant<std::string, bool> b = true;
  assert(b.index() == 1);  // a real bool still chooses bool

  std::variant<float, long> c = 0;
  assert(c.index() == 1);  // int→float is narrowing, so float is removed

  std::variant<int, long> d = 0u;  // unsigned→int is narrowing
  assert(d.index() == 1);          // on LP64, unsigned→long is not narrowing
}
```

¶14 The rule is as follows. For each alternative `T_i`, imagine a single-parameter function *FUN*(`T_i`) ([[g:imaginary-function-fun]]), then perform ordinary overload resolution ([[over.match.best]]) on the expression *FUN*(`std::forward<T>(t)`); the selected *FUN*(`T_j`) determines the type `T_j` of the contained value. But only a `T_i` that meets the following condition gets a corresponding *FUN*:

!!! std
    build an imaginary function *FUN*(`T_i`) for each alternative type `T_i` for which `T_i x[] = {std::forward<T>(t)};` is well-formed for some invented variable `x`.

`T_i x[] = {e};` is list-initialization of an array, with the element copy-initialized from `e`; if this needs a narrowing conversion ([[g:narrowing-conversion]]), the program is ill-formed ([[dcl.init.list]]). So the effect of this condition is that alternatives that would involve narrowing do not take part in overload resolution. Among the remaining candidates, implicit conversion sequences are still ranked as usual ([[over.ics.rank]]), and two equally good ones are ambiguous.

What is checked is `std::forward<T>(t)`, not the literal written at the call site. It is not a constant expression, so the exemption "a constant whose value can be represented exactly is not narrowing" does not apply: `int` to `float` always counts as narrowing, even if the argument is written as `0`.

¶15 The following conditions are all constraints; if any of them is not met, this constructor disappears from the overload set, and `is_convertible_v<X, variant<...>>` honestly reports `false`:

- the argument type, with cv and references removed, is not the variant itself, nor a specialization of `in_place_type_t` or `in_place_index_t`;
- `is_constructible_v<T_j, T>` is true;
- overload resolution for *FUN* succeeds and is not ambiguous.

¶16 Once `T_j` is chosen, the contained value is direct-initialized with `std::forward<T>(t)`, without braces. *FUN* only chooses the type; the actual initialization does no narrowing check. This constructor is not `explicit`; `variant<int, std::string> v = "x";` uses it.

The narrowing filter also turns some code that used to compile into errors:

<div class="compare" markdown="1">

```cpp error
#include <string>
#include <variant>
// double→int is narrowing, so int is removed;
// double cannot implicitly convert to string either
std::variant<int, std::string> v
    = 3.14;  // error
```

```cpp error
#include <variant>
// int→float and int→double
// are both narrowing; no candidates
std::variant<float, double> w
    = 0;  // error
```

</div>

Under the C++17 rule, the left one would silently truncate `3.14` to `3` and store it in the `int`, and the right one would be ambiguous. The `variant<string, string> v("abc");` given in Note 2 of ¶15 is ill-formed in every version: the two *FUN*(`string`)s are equally good.

Whether `unsigned` to `long` is narrowing depends on whether `long` can represent all values of `unsigned`. On LP64 (Linux, macOS) `long` is 64 bits and `d` above chooses `long`; on LLP64 (Windows) `long` is only 32 bits, both candidates are removed, and the same line fails to compile.

!!! history "From C++17 to the current rule"
    C++17's [[P0088R3]] had only the *FUN* overload resolution and no narrowing filter, which led to two well-known problems: `variant<std::string, bool> v = "abc";` chose `bool`, because `const char*` to `bool` is a standard conversion, better than the user-defined conversion to `string`; and `variant<float, long> v = 0;` was ambiguous, because the two conversions have the same rank.

    C++20's [[P0608R3]] added the array-initialization filter, together with a special rule for `bool` at the time: the `bool` alternative was considered only when the argument itself was a `bool`. Later [[P1957R2]] made conversions from pointers and pointers to members to `bool` narrowing conversions in the core language, so the narrowing filter could block `const char*` to `bool`, and that special case was removed. ¶14 in the current draft has only the array-initialization condition left.

!!! lawyer "Overload resolution for *FUN* is exactly like for ordinary functions"
    The standard does not require implementations to actually declare these functions, only that the result be the same as overload resolution over such a set of functions. So all the details of overload resolution apply. For example, initializing a `variant<Base, Derived>` with a `MoreDerived` object chooses `Derived`: both candidates are derived-to-base conversions, and converting to the closer base is better ([[over.ics.rank]]).

### Specifying the alternative with `in_place`

¶20 Four more constructors use a tag to say directly which alternative to construct; all of them are `explicit`:

| Form | Constraints | After construction |
|---|---|---|
| `variant(in_place_type_t<T>, Args&&...)` (¶20–24) | `T` occurs exactly once in `Types`; `is_constructible_v<T, Args...>` | `holds_alternative<T>(*this)` |
| `variant(in_place_type_t<T>, initializer_list<U>, Args&&...)` (¶25–29) | as above, with `initializer_list<U>&` first | as above |
| `variant(in_place_index_t<I>, Args&&...)` (¶30–34) | `I < sizeof...(Types)`; `is_constructible_v<T_I, Args...>` | `index() == I` |
| `variant(in_place_index_t<I>, initializer_list<U>, Args&&...)` (¶35–39) | as above | `index() == I` |

They all perform direct-non-list-initialization and do not go through *FUN*, so `variant<int, std::string>(std::in_place_index<0>, 3.14)` is valid and stores `3`. When you really want narrowing or want to use an `explicit` constructor, `in_place` is the way to say so explicitly.

When the same type occurs twice, the alternatives can only be distinguished by index:

```cpp run title="duplicate-types.cpp" ok
#include <cassert>
#include <string>
#include <variant>

// the two strings represent a user name and an error message
using Result = std::variant<std::string, std::string>;

int main() {
  Result r(std::in_place_index<1>, "file not found");
  assert(r.index() == 1);
  r.emplace<0>("alice");  // emplace by index: OK
  assert(std::get<0>(r) == "alice");
  // r.emplace<std::string>("bob");  // error: string occurs twice
  // r = "bob";                      // error: FUN is ambiguous
}
```

## valueless: when a variant loses its value ([variant.status])

```cpp run title="valueless.cpp" ok
#include <cassert>
#include <variant>

struct S { operator int() { throw 42; } };

int main() {
  std::variant<float, int> v{12.f};
  try { v.emplace<1>(S()); } catch (int) {}
  assert(v.valueless_by_exception());
  assert(v.index() == std::variant_npos);
}
```

This is the example from Note 1 in paragraph 2 of [variant.status]. Both alternatives are trivial types, and the variant still loses its value: `emplace` first destroys the old `float`, then initializes the `int` with `S()` ([variant.mod]/7); the conversion function throws at that point, the old value is gone and the new one was never made.

¶1 `valueless_by_exception()` returns `true` when the variant does not hold a value. ¶3 `index()` then returns `variant_npos`, and otherwise returns the index of the contained value's alternative. Both are `constexpr noexcept`.

This design is called **never-quite-empty** ([[g:never-quite-empty]]): in normal use a variant always has a value, and it can lose its value only when an exception interrupts a change of type. Once it has lost its value, you can only assign to it again or `emplace`, destroy it, or query its state; `get` and `visit` throw `bad_variant_access`.

Why not guarantee it is never empty? The contained value must live inside the object, and there are only two ways to be never empty:

1. Double buffering: keep two copies of storage in the object, construct the new value in the other one and then switch, at the cost of doubling the size;
2. Construct the new value in a temporary first, then move it in without throwing: this requires the new type's move constructor not to throw, which cannot always be satisfied.

The standard's choice is not to insist, but to achieve it when it is cheap. The branch rules for assignment in the next section are designed this way.

### Which operations can make a variant lose its value

| Operation | Wording | When it loses its value |
|---|---|---|
| `emplace` | [variant.mod]/11, /18 | when initializing the new value throws, it may hold no value |
| converting assignment (type changes) | [variant.assign]/16.2 | when taking the direct-`emplace` branch and initialization throws, it may hold no value |
| copy assignment (type changes) | [variant.assign]/2.4, 2.5 | 2.4 is just `emplace`; 2.5 first copies into a temporary variant, then move-assigns |
| move assignment (type changes) | [variant.assign]/10.1 | when `T_j`'s move constructor throws, it definitely holds no value |
| `swap` (different indices) | [variant.swap]/5 | depends on the exception guarantee of the variant's move constructor |
| copying or moving a valueless variant | [variant.ctor]/7, /11 | the result is valueless too |

Assignment with the same index only calls `T_j`'s own assignment operator, and [variant.assign]/16.1 says explicitly that `valueless_by_exception()` is still `false` in that case.

The wording "may hold no value" leaves room for implementations: if an implementation knows that construction of some type cannot fail halfway, it can construct elsewhere first and then copy it in, so it never loses its value. libstdc++ does this for some types; libc++ does not. Its `emplace` always destroys first (setting the index to valueless at the same time), then constructs, and finally writes the index, so the example above really does lose its value on libc++.

## Assignment ([variant.assign])

The three kinds of assignment follow the same idea: with the same index, call the contained value's own assignment operator; with a different index the type must change, and as long as there is a final step that cannot throw, the work that may fail is moved before the destruction of the old value.

### Converting assignment

¶11 `template<class T> variant& operator=(T&&)` chooses `T_j` with exactly the same *FUN* rule as converting construction, including the narrowing filter. ¶12 The constraints are: `T` is not the variant itself, `T_j` can be both assigned and constructed from `T`, and overload resolution for *FUN* succeeds.

¶13 The effect has three cases:

- (13.1) `*this` already holds a `T_j`: assign `std::forward<T>(t)` directly to the contained value, without recreating the object;
- (13.2) constructing `T_j` from `T` does not throw, or `T_j`'s move constructor may throw: equivalent to `emplace<j>(std::forward<T>(t))`, constructing in place;
- (13.3) otherwise, i.e. construction may throw but moving does not: equivalent to `emplace<j>(T_j(std::forward<T>(t)))`, constructing a temporary first and then moving it in.

The temporary in 13.3 is constructed before the old value is destroyed, so if it throws the old value is still there. The second condition in 13.2 looks odd, but it is because constructing a temporary first would not help: the subsequent move could throw just as well.

```cpp run title="assign-strategy.cpp" ok
#include <cassert>
#include <variant>

struct Direct {  // move constructor may throw
  Direct(const char*) { throw 1; }
  Direct(Direct&&) noexcept(false) {}
  Direct& operator=(Direct&&) = default;
};
struct ViaTemp {  // move constructor does not throw
  ViaTemp(const char*) { throw 1; }
  ViaTemp(ViaTemp&&) noexcept {}
  ViaTemp& operator=(ViaTemp&&) = default;
};

int main() {
  std::variant<int, Direct> a = 42;
  try { a = "x"; } catch (int) {}  // 13.2: direct emplace
  assert(a.valueless_by_exception());

  std::variant<int, ViaTemp> b = 42;
  try { b = "x"; } catch (int) {}  // 13.3: temporary first
  assert(!b.valueless_by_exception());
  assert(std::get<int>(b) == 42);
}
```

Both types must be assignable from `const char*` to satisfy `is_assignable_v<T_j&, T>` in ¶12. Here this is achieved by implicitly constructing a temporary and then move-assigning it.

The most common case, `std::string`, takes 13.3: constructing from `const char*` may throw `bad_alloc`, while the move constructor does not throw. So with `variant<int, std::string> v = 1; v = "hello";`, if allocation fails, `v` still holds `1`. For common standard library types, converting assignment usually has the strong exception guarantee; what really tends to make a variant lose its value is `emplace` and types whose move constructor may throw.

¶16 The exception specification of converting assignment is `is_nothrow_assignable_v<T_j&, T> && is_nothrow_constructible_v<T_j, T>`.

### Copy assignment

¶2 Let `j = rhs.index()`:

- (2.1) neither side holds a value: do nothing;
- (2.2) `*this` holds a value and `rhs` does not: destroy `*this`'s value, so that it holds no value;
- (2.3) the indices are the same: call `T_j`'s copy assignment;
- (2.4) if `T_j`'s copy constructor does not throw, or `T_j`'s move constructor may throw: equivalent to `emplace<j>(GET<j>(rhs))`;
- (2.5) otherwise: equivalent to `operator=(variant(rhs))`, first copying into a temporary variant and then move-assigning.

The split between 2.4 and 2.5 corresponds exactly to 13.2 and 13.3 of converting assignment: the copy is completed before `*this` is touched, the subsequent move does not throw, and `*this` does not lose its value.

¶5 If any `T_i` is not both copy-constructible and copy-assignable, copy assignment is defined as deleted. When the copy constructors, copy assignments and destructors of all `T_i` are trivial, it is trivial. All three must be trivial because switching types requires destroying the old value and constructing a new one.

### Move assignment

¶7 Move assignment is constrained on all `T_i` being move-constructible and move-assignable. The first three cases parallel copy assignment; when the indices differ (8.4) it does `emplace<j>(GET<j>(std::move(rhs)))` directly, without a temporary-first branch (see Question 2 for why).

¶10 Its triviality condition is the same as for copy assignment, and its exception specification is the logical AND of `is_nothrow_move_constructible_v && is_nothrow_move_assignable_v` over all `T_i`. If `T_j`'s move constructor throws, the variant definitely holds no value (10.1); if the move assignment throws, the state of the contained value is determined by `T_j`, and `index()` is still `j` (10.2).

## emplace ([variant.mod])

¶7 `emplace<I>(args...)` first destroys the current value (if any), then direct-non-list-initializes a `T_I` with `args...` and returns a reference to the new value. If initialization throws, the variant may hold no value (paragraph 11).

¶1 `emplace<T>` requires `T` to occur exactly once in `Types` and then forwards to `emplace<I>`. Each has an `initializer_list` version (paragraphs 3 and 12).

A few details:

- An out-of-range index is *Mandates* (paragraph 5), a compile error outright; constructibility is *Constraints* (paragraph 6), and when not satisfied the function does not participate in overload resolution ([[structure.specifications]]).
- Even when the index does not change, `emplace` destroys and then constructs; it does not call the assignment operator. If you want assignment semantics for the same type, use `operator=`.
- `emplace` has no temporary-first protection; its semantics are in-place construction. When you need the protection, you can write `v.emplace<I>(T_I(args...))` yourself, which is exactly the expanded form of 13.3.

## swap ([variant.swap])

¶1 The member `swap` requires (*Mandates*) all `T_i` to be move-constructible, with the precondition (paragraph 2) that each `T_i` meets *Cpp17Swappable* ([[swappable.requirements]]).

¶3 The effect has three cases: if both are valueless, nothing happens; if the indices are the same, `swap(GET<i>(*this), GET<i>(rhs))` is called, which can find a user-defined `swap` via ADL; otherwise the values of the two are exchanged, types included.

The case where one side is valueless and the other holds a value falls into the third case: after the swap, the side that had a value becomes valueless and the other side gets the value.

```cpp run title="variant-swap.cpp" ok
#include <cassert>
#include <string>
#include <variant>

int main() {
  std::variant<int, std::string> a = 1, b = "two";
  a.swap(b);  // different indices: types are exchanged too
  assert(std::get<std::string>(a) == "two");
  assert(std::get<int>(b) == 1);

  std::variant<int, std::string> c = "three";
  a.swap(c);  // same index: calls string's swap
  assert(std::get<1>(a) == "three" && std::get<1>(c) == "two");
  static_assert(noexcept(a.swap(c)));
}
```

¶5 The exception specification is the logical AND of `is_nothrow_move_constructible_v && is_nothrow_swappable_v` over all `T_i`.

## variant in constant evaluation

All members are `constexpr`, including destruction, assignment and `emplace`. This relies on the core language allowing the active member of a union to change during constant evaluation ([[class.union]]). Originally only some members were `constexpr` in C++20; [[P2231R1]] completed the rest, and implementations treat it as a fix to C++20.

```cpp run title="variant-constexpr.cpp" ok
#include <variant>

constexpr int f() {
  std::variant<int, double> v = 1;
  v = 2.5;  // changes the active alternative
  v.emplace<0>(7);
  return std::get<0>(v) + int(v.index());
}
static_assert(f() == 7);
int main() {}
```

## The libc++ implementation

The following is based on libc++ 23's `<variant>` as used in our tests.

### Storage: a recursive union

```cpp
// simplified from __variant_detail::__union
template <_Trait _DestructibleTrait, size_t _Index, class _Tp, class... _Types>
union __union<_DestructibleTrait, _Index, _Tp, _Types...> {
  char __dummy;                    // the active member when valueless
  __alt<_Index, _Tp> __head;       // this alternative
  __union<_DestructibleTrait, _Index + 1, _Types...> __tail;  // the rest
};
```

The storage of `variant<A, B, C>` is nested like `union { A; union { B; union { C; }; }; }`. `get<I>` expands at compile time into a chain of member accesses like `.__tail.__tail.__head`, with no loop at run time. When valueless, the active member of the union is `__dummy`, and no alternative needs to be constructed.

### The type of the index

libc++ has an optimization that chooses `unsigned char` or `unsigned short` based on the number of alternatives, but it is controlled by the macro `_LIBCPP_ABI_VARIANT_INDEX_TYPE_OPTIMIZATION` and enabled only in ABI v2. In the default ABI v1 (including the macOS system library and Homebrew LLVM) the index is always `unsigned int` and cannot be changed, for ABI stability. In our tests, `sizeof(std::variant<char>) == 8` and `sizeof(std::variant<int, double>) == 16`.

The internal valueless marker is the all-ones value of the index type, which `index()` translates to `variant_npos` of type `size_t`.

### Special members: a ladder of conditional base classes

`variant` holds a member `__impl_` of type `__impl<Types...>`, and its own special members are all `= default`; whether they are trivial is decided by the type of this member. Below `__impl` is a chain of base classes: `__copy_assignment`, `__move_assignment`, `__copy_constructor`, `__move_constructor`, `__dtor`, with the bottom `__base` holding the recursive union and the index.

Each base layer chooses one of three partial specializations, `= default`, a hand-written implementation or `= delete`, based on a three-valued enumeration (trivially available, available, unavailable), taking the worst value among all alternatives. The copy assignment layer considers the triviality of both copy construction and copy assignment, which corresponds exactly to [variant.assign]/5. `variant` also privately inherits from `__sfinae_ctor_base` and `__sfinae_assign_base`, which are specifically responsible for the defined-as-deleted cases.

### Converting assignment and FUN

`__assign_alt` is almost a word-for-word translation of [variant.assign]/13:

```cpp
if (this->index() == _Ip) {
  __a.__value = std::forward<_Arg>(__arg);                  // 13.1
} else if constexpr (is_nothrow_constructible_v<_Tp, _Arg> ||
                     !is_nothrow_move_constructible_v<_Tp>) {
  this->__emplace<_Ip>(std::forward<_Arg>(__arg));          // 13.2
} else {
  this->__emplace<_Ip>(_Tp(std::forward<_Arg>(__arg)));     // 13.3
}
```

Copy assignment calls it too; then `_Arg` is `const T_j&`, and `is_nothrow_constructible_v<T_j, const T_j&>` is just whether the copy constructor does not throw, exactly reproducing 2.4 and 2.5.

*FUN* is implemented by generating an `__overload<T_i, i>` for each alternative and merging them into one overload set with `using _Bases::operator()...;`, the same trick as the overload pattern in [[variant.visit]]. The narrowing check is placed in the return type, removing the candidate via SFINAE on failure. libc++ performs this check only for arithmetic alternatives, because only conversions to arithmetic types (including `bool`) can be narrowing conversions.

### An extra guarantee for swap

When the indices differ, `swap` first moves one side into a temporary, then move-constructs crosswise, and finally moves back. The source has a piece of logic marked EXTENSION: if the move construction in the middle throws and the temporary can be moved without throwing, it is moved back, providing the strong exception guarantee. The standard only requires "depends on the exception guarantee of the move constructor"; this is something extra that libc++ provides.

## Common misconceptions

!!! pitfall "Thinking only special types can make a variant lose its value"
    The `variant<float, int>` in Note 1 shows that any variant can lose its value as long as initializing the new value can throw (for example in a conversion function, or while evaluating constructor arguments). This is especially true of `emplace`, which has no temporary-first path.

!!! pitfall "Thinking `emplace` and `=` treat the same type the same way"
    When `v` already holds a `T_j`, `v = x` calls `T_j::operator=` (13.1), preserving the object's identity and possibly reusing resources such as a `string`'s buffer. `v.emplace<j>(x)` always destroys and then constructs. For objects with identity, such as ones that have registered callbacks or hold a mutex, the two have completely different effects.

!!! pitfall "Thinking variant picks the type that looks most similar"
    *FUN* is overload resolution; it does not guess intentions. In `variant<std::string, std::string_view> v = "abc";`, `const char[4]` to either is a user-defined conversion, which is ambiguous, so compilation fails. When you need to be explicit, use `in_place_type`, or construct the target type first.

## Questions

!!! question "Question 1"
    Which case of [variant.assign]/13 does `std::variant<int, std::vector<int>> v = 1; v = std::vector<int>{1, 2, 3};` take? What about `v = {1, 2, 3};`?

<details markdown="1">
<summary>Answer</summary>

The first: *FUN* selects `vector<int>` (`vector` cannot convert to `int`). `v` currently holds an `int`, so it is not 13.1. Constructing a `vector<int>` from a `vector<int>` rvalue is move construction, which does not throw, so it takes 13.2 and does a direct `emplace`.

The second does not call converting assignment at all. A braced initializer list has no type, so `template<class T> operator=(T&&)` cannot deduce `T` ([[temp.deduct.call]]). The remaining candidates are copy assignment and move assignment, which need to copy-list-initialize a variant from `{1, 2, 3}`. variant has no `initializer_list` constructor, so by [[over.match.list]] the three elements are treated as three arguments to match against all constructors: the converting constructor takes only one argument, and the `in_place` constructors require the first argument to be a tag and are `explicit`. There is no viable constructor, and Clang reports "no viable overloaded '='". The correct spellings are `v = std::vector{1, 2, 3};` or `v.emplace<1>({1, 2, 3});`.
</details>

!!! question "Question 2"
    Why does move assignment (8.4) have no temporary-first branch like copy assignment (2.5)?

<details markdown="1">
<summary>Answer</summary>

The point of constructing a temporary first is to move the operation that may throw before the destruction of the old value, and then finish with a move that does not throw. For move assignment, constructing the temporary is itself a move construction of `T_j`. If that may throw, moving the temporary in at the end may throw just as well, so nothing is gained; if it does not throw, a direct `emplace` does not throw either. In both cases the temporary is pointless, so the standard simply writes `emplace<j>(GET<j>(std::move(rhs)))` and specifies in 10.1 that the variant definitely holds no value if the move constructor throws.
</details>

!!! question "Question 3"
    Does `std::variant<bool, std::string> v = std::string_view("x");` compile?

<details markdown="1">
<summary>Answer</summary>

No, neither in C++17 nor under the current rule. There is no implicit conversion from `string_view` to `bool`, and to `string` there is only an `explicit` constructor, which copy-initialization cannot use. Neither *FUN*(`bool`) nor *FUN*(`string`) is viable, so the converting constructor is excluded by its constraints. This shows that *FUN* only considers implicit conversions; an `explicit` constructor is never selected by it. To store the value, write `v.emplace<1>(sv)` or `variant<bool, std::string>(std::in_place_index<1>, sv)`; these are direct-initialization and can use `explicit` constructors.
</details>

## Summary

| Member | Key points |
|---|---|
| default constructor | constrained on `T_0` being default-constructible; `index() == 0` |
| copy constructor | deleted if any is not copyable; trivial if all are trivial |
| move constructor | constrained on all being movable; trivial if all are trivial |
| converting constructor, converting assignment | *FUN* overload resolution, after removing candidates that would narrow; does not participate in overload resolution when ambiguous or there are no candidates |
| `in_place_type`, `in_place_index` | `explicit`, direct-initialization; `in_place_type<T>` requires `T` to occur only once |
| copy assignment, converting assignment | assign when the index is the same; temporary first when construction may throw but moving does not, otherwise direct `emplace` |
| move assignment | direct `emplace` when the indices differ; loses its value if move construction throws |
| `emplace` | destroy, then construct; may lose its value when it throws |
| `valueless_by_exception`, `index` | `index() == variant_npos` when valueless |
| `swap` | exchanges the contained values when the indices are the same, otherwise exchanges the types too |

<details class="fine" markdown="1"><summary>Remaining wording</summary>

[variant.variant.general]/4: a program that declares an explicit or partial specialization of `variant` is ill-formed, no diagnostic required. This is stricter than for standard library templates in general, which users may specialize when certain conditions are met ([[namespace.std]]).

The *Throws* elements of the constructors in [variant.ctor] (¶5, ¶8, ¶12, ¶18 and so on) all just say that any exception thrown by the initialization of the contained value is thrown; the *Postconditions* elements state the value of `index()` or `holds_alternative` after construction, which the text above already covers.

[variant.assign]/3, /9, /14 and /15 are the postcondition `index() == rhs.index()` of copy assignment and the statements that each assignment operator returns `*this`.

[variant.mod]/8–10 say that after `emplace`, `index() == I`, that it returns a reference to the new value, and that it throws any exception thrown by the initialization.

</details>
