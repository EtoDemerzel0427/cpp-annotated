---
title: Pairs
summary: "The full specification of std::pair: when constructors are explicit, why copy assignment is user-written (so pair is not trivially copyable), dangling reference members, const assignment and pair-like types, piecewise construction, comparisons, make_pair and tuple-like access."
updated: 2026-10-19
---

!!! tldr
    - `pair`'s copy assignment is user-written because it must support reference members and assign through the references; the price is that `pair<int, int>` is not trivially copyable and cannot be `memcpy`'d or `bit_cast`.
    - Whether each constructor is `explicit` follows the corresponding conversion of the elements: if the elements convert implicitly, `return {a, b};` compiles.
    - Since C++23, constructors that would bind a reference member to a temporary are defined as deleted, so `pair<const long&, int>(i, 2)` no longer dangles silently.
    - The `const` assignment operators exist for proxy references like those of `zip`, and are usable only when the elements themselves support `const` assignment (references, for example).
    - `make_pair` unwraps `reference_wrapper` into a reference; CTAD does not: the first member of `std::pair{std::ref(i), 1.0}` is a `reference_wrapper<int>`.

`std::pair<T1, T2>` has just two public data members, `first` and `second`, yet its wording runs to more than fifty paragraphs: ten constructors and twelve assignment operators, each with constraints, a conditional `explicit` or a deletion condition. The reason is that `pair` has to behave like two independent variables for arbitrary `T1` and `T2` (references, non-copyable types, types that can only be constructed explicitly, `const` types), while still allowing `return {a, b};` in generic code.

Library wording describes functions with a few fixed labels. If *Constraints* are not satisfied, the function does not participate in overload resolution; if *Mandates* are not satisfied, the program is ill-formed; if *Preconditions* are not satisfied, the behavior is undefined ([[structure.specifications]]).

## Assigning through references, at the cost of triviality

```cpp run title="pair_assign.cpp" ok
#include <utility>
#include <type_traits>
#include <cstdio>

struct Ref { int& r; };                       // an ordinary aggregate
static_assert(!std::is_copy_assignable_v<Ref>);                  // copy assignment is deleted
static_assert(std::is_copy_assignable_v<std::pair<int&, int>>);  // pair can be assigned

int main() {
  int a = 1, b = 2;
  std::pair<int&, int> p{a, 10}, q{b, 20};
  p = q;                  // assigns b's value to a; p.first still refers to a
  std::printf("a=%d b=%d same:%d\n", a, b, &p.first == &a);   // a=2 b=2 same:1
}
```

The core language specifies that the defaulted copy assignment operator of a class with a reference member is deleted ([[class.copy.assign]]), because a reference cannot be rebound. Yet the very purpose of `pair<T&, U&>` and of the `tuple<T&...>` produced by `std::tie` is to assign through the references: `p = q` assigns the value of the object referred to by `q.first` to the object referred to by `p.first`. That can only be written by hand as `first = p.first; second = p.second;`.

So in the class definition the copy and move constructors are `= default`, while the copy and move assignment operators are ordinarily declared functions. ¶20–¶22 specify that copy assignment assigns the members one by one, and that it is defined as deleted unless `is_copy_assignable_v<T1>` and `is_copy_assignable_v<T2>` are both true. `is_copy_assignable_v<int&>` is true (assigning to an `int&` assigns to the referenced `int`), so a reference member does not cause deletion; a `const int` member does.

### Consequences for triviality (¶3)

A **trivially copyable type** ([[g:trivially-copyable-class|trivially copyable]]) can be copied with `memcpy` and can be the source and destination of `std::bit_cast`. Per [[class.prop]], it requires every eligible copy and move assignment operator to be trivial. `pair`'s assignment operators are user-provided, so:

```cpp run title="pair_triviality.cpp" ok
#include <utility>
#include <type_traits>
using PI = std::pair<int, int>;
static_assert(std::is_trivially_copy_constructible_v<PI>);   // copy constructor = default
static_assert(std::is_trivially_destructible_v<PI>);         // guaranteed by ¶3
static_assert(!std::is_trivially_copy_assignable_v<PI>);     // copy assignment is user-written
static_assert(!std::is_trivially_copyable_v<PI>);            // not trivially copyable overall
int main() {}
```

!!! std "[pairs.pair]/3"
    If `(is_trivially_destructible_v<T1> && is_trivially_destructible_v<T2>)` is `true`, then the destructor of `pair` is trivial.

¶3 When both members are trivially destructible, `pair`'s destructor must be trivial. `pair` declares no destructor, and the implicit destructor already behaves this way ([[class.dtor]]). Writing it into the wording forbids implementations from adding a user-provided destructor to `pair`, for instance for debugging purposes.

!!! lawyer "Could assignment be made conditionally trivial?"
    C++20 allows several declarations of the same special member function with requires-clauses, for example one that is `= default` when all elements are trivially assignable and a hand-written fallback. `optional` and `variant` use this technique to be conditionally trivial ([[class.copy.assign]]). The standard has never required this of `pair`, and implementations cannot do it on their own: trivial copyability affects how arguments are passed under the Itanium ABI, and changing it would break the ABI. libc++'s `__utility/pair.h` even still keeps the old ABI macro `_LIBCPP_DEPRECATED_ABI_DISABLE_PAIR_TRIVIAL_COPY_CTOR`, for compatibility with an even older layout in which not even the copy constructor was trivial.

!!! impl "How libc++ implements “defined as deleted unless …”"
    libc++ writes the parameter type of copy assignment as `__conditional_t<is_copy_assignable<first_type>::value && is_copy_assignable<second_type>::value, pair, __nat> const&`. When the condition is false the parameter type becomes the internal empty type `__nat`, so the function is no longer a copy assignment operator; since `pair` also has a user-declared move constructor, the implicitly declared copy assignment operator is defined as deleted ([[class.copy.assign]]), and the core language rule produces the effect the wording requires.

## Whether constructors are explicit (¶5–¶13)

<div class="compare" markdown="1">

```cpp ok
#include <utility>
#include <string>
std::pair<std::string, int> f() {
  return {"pi", 3};   // OK
}
```

```cpp error
#include <utility>
#include <vector>
std::pair<std::vector<int>, int> g() {
  return {3, 1};  // error: explicit
}
```

</div>

`return {...};` is copy-list-initialization, and it is ill-formed if an `explicit` constructor is selected ([[over.match.list]]). On the left, `const char*` converts implicitly to `std::string`, so the selected constructor is not `explicit`; on the right, `vector(size_t)` is `explicit`, so the corresponding `pair` constructor is `explicit` too, just as `std::vector<int> v = 3;` is invalid.

This is the rule shared by all the constructors: **whether a `pair` constructor is `explicit` follows whether the corresponding element conversion is implicit**. The wording expresses this with C++20's conditional `explicit` (`explicit(bool)`, [[class.conv.ctor]], [[P0892R2]]), writing each constructor as `explicit(see below)`.

| Constructor | Paragraphs | *Constraints* | `explicit` if and only if |
|---|---|---|---|
| `pair()` | ¶5–¶7 | both default-constructible | either is not implicitly default-constructible |
| `pair(const T1&, const T2&)` | ¶8–¶10 | both copy-constructible | for either, `const Ti&` is not implicitly convertible to `Ti` |
| `pair(U1&&, U2&&)` | ¶11–¶13 | `is_constructible_v<Ti, Ui>` | for either, `Ui` is not implicitly convertible to `Ti` |
| from `pair<U1, U2>` and pair-like | ¶14–¶17 | element-wise constructible; not a `subrange` | some element is not implicitly convertible |
| piecewise | ¶18–¶19 | none (*Mandates*: constructible) | never |

¶6–¶7 The default constructor value-initializes both members. Whether it is `explicit` depends on whether the elements are **implicitly default-constructible** ([[g:implicitly-default-constructible|implicitly default-constructible]]), that is, whether they can be copy-list-initialized from `{}`. Note 1 hints that this can be implemented by checking whether a `const T&` can be initialized with `{}`. If `E`'s default constructor is `explicit`, `std::pair<E, int> g() { return {}; }` is invalid, but `std::pair<E, int> e{};` is fine.

!!! history
    In C++11 `pair`'s constructors were either all implicit or all `explicit`, and `return {a, b};` failed to compile in many reasonable situations. C++17 switched to conditional `explicit`, but the language had no `explicit(bool)` at the time, so implementers had to write a pair of overloads with mutually exclusive constraints for each constructor, one `explicit` and one not. C++20's `explicit(bool)` allowed a single declaration to express this, and the wording was rewritten into its current form.

### Braced arguments and default template arguments {{c++23}} (¶11–¶12)

The forwarding constructor is written `template<class U1 = T1, class U2 = T2> pair(U1&& x, U2&& y)`; the default template arguments were added in C++23 ([[P1951R1]]).

```cpp
std::pair<std::string, std::vector<int>> p{"a", {1, 2, 3}};
```

A braced list `{1, 2, 3}` cannot be used to deduce a template parameter. Before C++23, deduction of `U2` failed, the forwarding constructor was not viable, and the call fell back to `pair(const T1&, const T2&)`: first a temporary `vector` was constructed, then copied in. With the default argument, `U2` becomes `vector<int>`, the temporary is moved in, and one copy is saved.

### Forbidding dangling reference members {{c++23}} (¶13, ¶17)

```cpp error
#include <utility>
int main() {
  int i = 1;
  std::pair<const long&, int> p(i, 2);   // error: first would bind to a temporary long
}
```

The `int` lvalue `i` must first be converted to a temporary `long` before `first` can bind to it. The temporary is destroyed when construction ends, and `first` becomes a dangling reference. ¶13 and ¶17 specify that the constructor is defined as deleted whenever `reference_constructs_from_temporary_v<first_type, U1&&>` or the corresponding term for `second` is true ([[P2255R2]]).

Being defined as deleted rather than merely ill-formed has the benefit of being detectable: `is_constructible_v<pair<const long&, int>, int&, int>` is false, and generic code can steer around it.

!!! impl "libc++ 23 does not implement this yet"
    In libc++ 23 the feature-test macro `__cpp_lib_reference_from_temporary` is still commented out. The `is_constructible_v` above is true on libc++; the constructor has not been deleted. The actual construction still fails, thanks to a core language rule: binding a reference member to a temporary in a member initializer is ill-formed ([[class.base.init]]). Clang reports `reference member 'first' binds to a temporary object whose lifetime would be shorter than the lifetime of the constructed object`. The only difference is whether generic code can detect it without an error.

### Constructing from pair and pair-like (¶14–¶17)

¶14 defines *FWD*(u) as `static_cast<decltype(u)>(u)`: when the parameter is `pair<U1, U2>&` this yields an lvalue, when it is `&&` an rvalue. This lets one piece of wording describe four overloads: `pair<U1, U2>&`, `const&`, `&&` and `const&&`. The non-`const` lvalue and `const` rvalue overloads were added in C++23 for `ranges::zip` ([[P2321R2]]), for proxy scenarios such as element types that can only be constructed from non-`const` references.

¶15–¶16 The last overload, `template<pair-like P> pair(P&& p)`, was also added in C++23 ([[P2165R4]]). A **pair-like** type is a tuple-like type of size 2 ([[tuple.like]]): `array<T, 2>`, `complex`, `pair`, a two-element `tuple`, `ranges::subrange`. So `std::pair<long, long> s(arr);` can be constructed from a `std::array<int, 2>`. ¶15.1 excludes `subrange`, because `subrange` has its own conversion function to pair-like types ([[range.subrange]]), and having both paths would cause ambiguity.

### Piecewise construction (¶18–¶19, [pair.piecewise])

When an element type can be neither copied nor moved, or constructing it needs several arguments, `pair(U1&&, U2&&)` is helpless. The **piecewise construction** provided by ¶19 packs each element's constructor arguments into a separate `tuple` and constructs the members in place:

```cpp run title="piecewise.cpp" ok
#include <utility>
#include <tuple>
#include <mutex>
#include <string>
#include <cstdio>

struct Pinned {                         // neither copyable nor movable
  Pinned(int a, std::string b) : a(a), b(std::move(b)) {}
  Pinned(const Pinned&) = delete;
  int a; std::string b;
};

int main() {
  std::pair<Pinned, std::mutex> p(std::piecewise_construct,
                                  std::forward_as_tuple(1, "one"),
                                  std::forward_as_tuple());     // mutex default-constructed
  auto& [pin, mtx] = p;
  std::lock_guard lk(mtx);
  std::printf("%d %s\n", pin.a, pin.b.c_str());                 // 1 one
}
```

The requirement in ¶18 is *Mandates* rather than *Constraints*: this constructor has a dedicated tag type as its first parameter, so it cannot be confused with other overloads and need not be excluded during overload resolution. Note 2 points out that if a member is a reference and ends up bound to a temporary, the program is ill-formed ([[class.base.init]]).

[pair.piecewise] ¶1 specifies that `piecewise_construct_t` is an empty class used only as a tag to distinguish overloads; `piecewise_construct` is a constant object of it. Its default constructor is `explicit`, to prevent `{}` from being implicitly converted to the tag. The `emplace` of associative containers uses the same form to construct elements in place: `m.emplace(std::piecewise_construct, std::forward_as_tuple(k), std::forward_as_tuple(a, b))`.

## Two families of assignment (¶20–¶50)

There are two families of assignment operators, six in each, from the same sources: copy (¶20–¶25), from `const pair<U1, U2>&` (¶26–¶31), move (¶32–¶38), from `pair<U1, U2>&&` (¶39–¶41, ¶48–¶50), and from pair-like (¶42–¶47).

The ordinary family returns `pair&`. The exception specification of move assignment is the conjunction of `is_nothrow_move_assignable_v` for the two elements (¶35). Assignment from pair-like requires that `P` not be `pair` itself (¶42.1), to avoid conflicting with copy and move assignment.

The other family consists of `const` member functions returning `const pair&`, with constraints written as `is_assignable_v<const T1&, ...>`. Assigning to a `const` object looks unreasonable; these exist for **proxy references** ([[P2321R2]]). Dereferencing a `ranges::zip_view` iterator yields a prvalue `pair<T1&, T2&>` or `tuple<T&...>`, and the requirements for writable iterators ([[iterator.concept.writable]]) include the form `const_cast<const iter_reference_t<I>&&>(*it) = value`.

For `pair<int&, int&>`, the `const` qualifies the `pair` itself, not the referenced `int`s, so assigning through the references is still reasonable: `is_assignable_v<int& const&, int>` is just `is_assignable_v<int&, int>`, which is true. For `pair<int, int>`, `is_assignable_v<const int&, int>` is false, so the `const` assignment does not participate in overload resolution and does not accidentally allow modifying a `const` object.

## swap (¶51–¶54, [pairs.spec]/4–5)

The member `swap(pair&)` and `swap(const pair&) const` swap the elements one by one. The swappability requirement in ¶51 is *Mandates*, and the exception specification in ¶54 uses `is_nothrow_swappable_v` of the two elements (`const T1` and `const T2` for the `const` version).

The non-member `swap` ([pairs.spec] ¶4), on the other hand, has *Constraints*. When generic code determines whether a type can be swapped via `using std::swap; swap(a, b);` or `ranges::swap`, it calls the non-member version. Only because it drops out of overload resolution when the elements are not swappable can `is_swappable_v<pair<T1, T2>>` faithfully reflect the elements.

## Comparison and make_pair ([pairs.spec])

¶1–¶2 `operator==` requires `x.first == y.first` and `x.second == y.second` to be valid, with results that model *boolean-testable* (usable like `bool` in `&&` and `!`; see [[concept.booleantestable]]); it returns their `&&`, which short-circuits. The two sides can be different `pair` specializations. This constraint was added in C++26; previously `equality_comparable<pair<T, U>>` was true even when the elements were not comparable, and the error appeared only when the function body was instantiated.

¶3 `operator<=>` compares `first` first and returns if they are unequal; otherwise it compares `second`. The *synth-three-way* it uses (with the same semantics as the core language's [[g:synthesized-three-way-comparison|synthesized three-way comparison]]) synthesizes a `weak_ordering` from `<` and `==` when the element type has no `<=>`. Types written before C++20 can still be compared when placed in a `pair`:

```cpp run title="pair_spaceship.cpp" ok
#include <utility>
#include <compare>
#include <type_traits>

struct Legacy {                     // an old type with only == and <
  int v;
  bool operator==(const Legacy&) const = default;
  constexpr bool operator<(const Legacy& o) const { return v < o.v; }
};

using P = std::pair<int, Legacy>;
static_assert(std::is_same_v<decltype(P{} <=> P{}), std::weak_ordering>);
static_assert(P{1, {2}} < P{1, {3}});
static_assert(std::is_same_v<decltype(std::pair{1, 2.0} <=> std::pair{1, 2.0}),
                             std::partial_ordering>);
int main() {}
```

`<`, `<=`, `>`, `>=` and `!=` are obtained from `<=>` and `==` through the rewritten candidates of [[over.match.oper]]. The six separate comparison operator templates from before C++20 have all been removed.

¶6 `make_pair(x, y)` returns `pair<unwrap_ref_decay_t<T1>, unwrap_ref_decay_t<T2>>`. `unwrap_ref_decay_t` first applies `decay` (arrays become pointers, cv and references are removed) and then unwraps `reference_wrapper<X>` into `X&`. The deduction guide used by CTAD, `pair(T1, T2) -> pair<T1, T2>`, takes its parameters by value and only decays:

<div class="compare" markdown="1">

```cpp ok
#include <utility>
#include <functional>
int i = 0;
auto r = std::make_pair(std::ref(i), 1.0);
// pair<int&, double>
```

```cpp ok
#include <utility>
#include <functional>
int i = 0;
std::pair r{std::ref(i), 1.0};
// pair<reference_wrapper<int>, double>
```

</div>

With C++17's CTAD, this unwrapping is the main remaining use of `make_pair`.

## Tuple-like access ([pair.astuple])

`pair` implements the tuple-like protocol ([[tuple]]):

- `tuple_size<pair<T1, T2>>` is derived from `integral_constant<size_t, 2>`;
- `tuple_element<I, pair<T1, T2>>::type` is `T1` when `I` is 0 and `T2` otherwise, requiring `I < 2` (¶1–¶2);
- `get<I>(p)` has four overloads, `&`, `const&`, `&&` and `const&&`, returning a reference to `first` or `second` (¶3–¶4);
- `get<T>(p)`, which gets by type, requires `T1` and `T2` to be different types (¶5–¶8).

A structured binding `auto [k, v] = p;` therefore uses the tuple-like protocol and calls `get<0>` and `get<1>` on the hidden variable ([[dcl.struct.bind]]). Since `pair`'s members are all public, binding to data members would give the same result even without the protocol.

```cpp run title="pair_get_type.cpp" error
#include <utility>
int main() {
  std::pair<int, int> p{1, 2};
  return std::get<int>(p);        // error: T1 and T2 are the same
}
```

!!! lawyer "The Mandates on get-by-type is actually redundant"
    The two groups of `get<T>` are declared as `template<class T1, class T2> T1& get(pair<T1, T2>&)` and `template<class T2, class T1> T2& get(pair<T1, T2>&)`. Calling `get<int>` on a `pair<int, int>`, both templates deduce successfully, the signatures are identical, and partial ordering cannot pick one either ([[temp.func.order]]), so overload resolution is ambiguous by itself. libc++ reports exactly `call to 'get' is ambiguous`. The *Mandates* just spells out that this is an error, which helps implementations give better diagnostics.

## As a constant template argument (¶4)

¶4 When `T` and `U` are both [[g:structural-type|structural types]] (types that can be used for constant template parameters, [[temp.param]]), so is `pair<T, U>`; two `pair` values are template-argument-equivalent if and only if their `first`s and their `second`s are respectively equivalent.

```cpp ok
#include <utility>
template<std::pair<int, char> P>
constexpr int tag = P.first + P.second;
static_assert(tag<{1, 'a'}> == 98);
```

`pair`'s members are all public and non-`mutable`, so it already meets the conditions under the core language rules. This paragraph turns that into a requirement on implementations, forbidding them from adding private members.

## Interaction with common_type and common_reference

`<utility>` specializes `common_type` (element-wise `common_type`) and `basic_common_reference` (element-wise `common_reference`) for `pair`; see [[utility]]. These were added in C++23 for `zip` ([[P2321R2]]): for `zip_view`'s iterators to satisfy `indirectly_readable`, `pair<int&, int&>` (the reference type) and `pair<int, int>` (the value type) must have a common reference type. `tuple` has the same specializations; see [[tuple]].

<details class="fine" markdown="1"><summary>Remaining wording</summary>

[pairs.general] ¶1 says the library provides `pair`, `make_pair`, and templates that allow `pair` to be accessed like a `tuple`.

[pairs.pair] ¶1 The member functions do not throw exceptions unless one of the element-wise operations they call throws.

¶2 The defaulted copy and move constructors are constexpr functions if and only if all the required element-wise initializations would be constexpr-suitable ([[dcl.constexpr]]).

The example in [pairs.spec] ¶7 says `make_pair(5, 3.1415926)` can be used instead of `pair<int, double>(5, 3.1415926)`.

¶49 in the current draft reads "Assigns `std::forward<U1>(p.first)` to `first` and `std::forward<U2>(u.second)` to `second`"; `u.second` should be `p.second`. ¶40 is missing a "to". These are editorial errors that do not affect the meaning.

</details>

## Common misconceptions

!!! pitfall "pair<int, int> can be memcpy'd"
    `std::is_trivially_copyable_v<std::pair<int, int>>` is false. It is not a valid object for `memcpy`, nor a valid source or destination for `std::bit_cast`. If you need a trivially copyable two-element tuple, write your own aggregate `struct`.

!!! pitfall "Writing const std::pair<K, V>& when iterating a map"
    `map<K, V>::value_type` is `pair<const K, V>`. `for (const std::pair<K, V>& kv : m)` creates a temporary `pair<K, V>` for each element via the converting constructor, which costs a copy and also makes saved references prone to dangling. Use `const auto&` or a structured binding.

!!! pitfall "const assignment lets a const pair be modified"
    The `const` assignment operators participate in overload resolution only when the element types themselves support `const` assignment (references, proxy types). A `const std::pair<int, int>` still cannot be assigned.

## Questions

!!! question "Question 1"
    Why can `pair`'s copy constructor be `= default` while its copy assignment operator cannot?

<details markdown="1">
<summary>Answer</summary>

A defaulted copy constructor initializes this object's reference members from the source object's reference members, that is, binds them to the same objects, which is valid and correct semantics; reference members do not cause copy construction to be deleted ([[class.copy.ctor]]). A defaulted copy assignment cannot rebind references, and the core language specifies that the defaulted copy assignment of a class with reference members is deleted ([[class.copy.assign]]). `pair<T&, U&>` needs assignment through the references, which can only be written by hand. As a consequence, `pair` is never a trivially copyable type ([[class.prop]]).
</details>

!!! question "Question 2"
    Which constructor does `std::pair<std::string, std::string> f() { return {"a", "b"}; }` select? Is there a difference between C++11 and C++23?

<details markdown="1">
<summary>Answer</summary>

There are two candidates. `pair(const T1&, const T2&)` must first convert the two string literals to temporary `std::string`s, which is a user-defined conversion. `pair(U1&&, U2&&)` deduces `U1 = U2 = const char(&)[2]`, and the arguments bind directly to the references, which is an exact match ([[over.ics.ref]]), so the forwarding constructor is selected. `const char(&)[2]` converts implicitly to `string`, so it is not `explicit`.

C++11 and C++23 give the same result. C++23's default template arguments only matter when an argument is a braced list that cannot be deduced.
</details>
