---
title: Other editorial conventions
summary: "The remaining conventions of library wording: exposition-only entities (such as decay-copy), customization point objects and algorithm function objects, enumerated and bitmask types, string terms such as ntbs, members that aren't written out, and what the freestanding annotations mean."
updated: 2026-10-19
---

!!! tldr
    - Hyphenated italic names in the standard (*decay-copy*, *synth-three-way*) and members commented "exposition only" are just tools for writing the specification: programs can't use them, and implementations don't have to provide them.
    - A customization point object (CPO) is a stateless function object that can be copied, passed to higher-order functions and used as a template argument; when the arguments don't meet its requirements it has no viable call operator, so `requires` can detect that.
    - The algorithms in `std::ranges` are algorithm function objects: ADL doesn't find them, and when unqualified lookup finds them, ADL is suppressed.
    - The underlying type of a bitmask type (such as `ios_base::iostate`) is unspecified; only the elements and operators given by the standard can be used.
    - The `// freestanding`, `// hosted` and `// freestanding-deleted` comments in synopses are normative and decide what a freestanding implementation must provide.

## Exposition-only entities [expos.only.entity]

### Hyphenated names (¶1)

When reading library wording you often see things like: `std::thread`'s constructor makes a *decay-copy* of its arguments, and `pair`'s `operator<=>` compares elements with *synth-three-way*. These names can't be found in any header.

¶1 Several entities declared in Clauses 17–33 and Annex D are [[g:exposition-only]]; their declarations are followed by a comment ending in *exposition only*. Such entities are tools for writing the specification: to describe semantics precisely in code, the standard needs some helper functions, helper concepts and helper members. Programs can't use them, and implementations don't have to provide anything with those names.

To avoid clashing with real names, the standard writes them in italics with hyphens. The hyphen guarantees they can't be valid C++ identifiers. Implementations usually have counterparts, but under reserved identifiers ([[lex.name]]), such as libc++'s `__boolean_testable`; code that depends on those names isn't portable.

### Four general exposition-only entities (¶2)

¶2 The following four entities are used throughout the library specification:

```cpp
namespace std {
  template<class T>
    requires convertible_to<T, decay_t<T>>
      constexpr decay_t<T> decay-copy(T&& v)          // exposition only
        noexcept(is_nothrow_convertible_v<T, decay_t<T>>)
      { return std::forward<T>(v); }

  constexpr auto synth-three-way = /* ... */;         // exposition only
  template<class T, class U = T>
  using synth-three-way-result = /* ... */;           // exposition only
  template<class T>
    concept constexpr-wrapper-like = /* ... */;       // exposition only
}
```

| Entity | Purpose | Where it is used |
|---|---|---|
| [[g:decay-copy\|*decay-copy*]](v) | Produces a decayed copy by value: arrays become pointers, references and cv-qualifiers are dropped | Copying arguments in `std::thread` and `std::async`; return values of the range access CPOs |
| *synth-three-way* | Synthesized three-way comparison: uses `<=>` if `T` and `U` support it, otherwise synthesizes a `weak_ordering` from two `<` | `operator<=>` of `pair`, `tuple`, `optional` and the containers |
| *synth-three-way-result* | The result type of the previous entry | As above |
| *constexpr-wrapper-like* | A type like `integral_constant`: convertible to `T::value`, with the value available at compile time | Deduction guides of `std::span`, `std::simd` |

Since C++23, *decay-copy* can mostly be written as `auto(x)` ([[expr.type.conv]]). There are subtle differences: *decay-copy* has a `convertible_to` constraint and copies through copy-initialization in a `return` statement, so an `explicit` copy constructor makes it unusable; `auto(x)` is direct-initialization.

C++20 replaced the six comparison operators of `pair`, `tuple` and others with a single `operator<=>`, but users' old types may define only `<`. The fallback branch of *synth-three-way* keeps these types comparable, with the result category `weak_ordering`:

```cpp run ok
#include <compare>
#include <type_traits>
#include <utility>
struct Old {   // only <
  int v;
  bool operator<(const Old& o) const { return v < o.v; }
};
int main() {
  std::pair<Old, int> a{{1}, 2}, b{{2}, 0};
  auto r = a <=> b;              // synthesized from <
  static_assert(std::is_same_v<decltype(r), std::weak_ordering>);
  return r < 0 ? 0 : 1;
}
```

¶3 An object `dst` is said to be decay-copied from a subexpression `src` if the type of `dst` is `decay_t<decltype((src))>`. The double parentheses in `decltype((src))` give the type of `src` as an expression (an lvalue yields an lvalue reference), which is then decayed. This phrasing is mainly used in the specification of `std::execution`, to describe how senders store copies of their arguments.

## Customization point objects and algorithm function objects

### Why customization point objects exist

The library often needs to call an operation users can customize, such as swapping two objects. The idiom in C++17 and earlier has two steps:

```cpp
using std::swap;
swap(a, b);   // unqualified call: ADL finds the user's swap, otherwise std::swap is used
```

Writing `std::swap(a, b)` bypasses the user's customization; writing only `swap(a, b)` and forgetting the `using` doesn't work for fundamental types such as `int`; and the library can't enforce any constraints at the call site. C++20 Ranges ([[P0896R4]]) wraps the two steps into a function object: `std::ranges::swap(a, b)` internally tries an ADL-found `swap`, a move-based swap and so on in a specified order, and users only need to write a qualified call.

### Properties of customization point objects [customization.point.object]

¶1 A [[g:customization-point-object]] (CPO) is a function object of literal class type that interacts with program-defined types while enforcing semantic requirements on that interaction.

¶2 The type of a CPO, ignoring cv-qualifiers, shall model `semiregular`, shall be a structural type ([[temp.param]]) and a trivially copyable type ([[class.prop]]), and all its constructors are non-throwing.

¶3 All instances of a specific CPO type are equal, and calling them with the same arguments has the same effects. ¶5 further says that after `auto p = o;`, `p(args...)`, `as_const(p)(args...)`, `std::move(p)(args...)` and `std::move(as_const(p))(args...)` are all equivalent to `o(args...)`.

These requirements make a CPO a stateless function name: it can be freely copied, stored and used as a constant template argument without changing its behavior.

```cpp run ok
#include <algorithm>
#include <functional>
#include <ranges>
#include <vector>
template<auto F> struct holder {};
holder<std::ranges::begin> h;          // structural type: usable as a template argument
int main() {
  std::vector<int> v{3, 1, 2};
  std::invoke(std::ranges::sort, v);   // can be passed to a higher-order function
  auto first = std::ranges::begin;     // a copy behaves the same
  return *first(v) == 1 ? 0 : 1;
}
```

The function template `std::sort` can't do any of this: it is an overload set, not an object, so `std::invoke(std::sort, ...)` can't deduce template arguments and is ill-formed; nor can it be a template argument.

¶4 Let the type of a CPO be `T`. When the argument types `Args...` meet the CPO's requirements, `T` shall model `invocable<..., Args...>` for all four forms `T&`, `const T&`, `T` and `const T`. When the arguments don't meet the requirements, `T` shall have no function call operator that participates in overload resolution.

The second half guarantees that CPOs are detectable. `std::ranges::begin(42)` doesn't cause a hard error somewhere inside the CPO; `std::invocable<decltype(std::ranges::begin), int>` is simply `false`. The `std::ranges::range` concept is defined in terms of `ranges::begin(t)` and relies on exactly this.

!!! impl "How libc++ defines CPOs"
    ```cpp
    namespace ranges {
    namespace __begin { struct __fn { /* several constrained operator() */ }; }
    inline namespace __cpo {
      inline constexpr auto begin = __begin::__fn{};
    }
    }
    ```
    The extra inline namespace avoids name clashes. Some iterators in `std::ranges` declare `iter_move` and `iter_swap` as hidden friends, and those friend functions belong to `std::ranges`, where they would clash with variables of the same name in the same namespace. With the variables in `__cpo` the two no longer clash, and users writing `std::ranges::iter_move` still find it through the inline namespace. The CPO design first appeared in Eric Niebler's [[N4381]].

### Algorithm function objects [alg.func.obj]

¶1 An [[g:algorithm-function-object]] is a CPO that is specified as one or more overloaded function templates, whose name designates the object. In [alg.find] the standard writes out the signatures of `ranges::find` as function templates because that is clearest; what is actually provided is an object.

¶2 Let `S` be the corresponding set of function templates; then for any arguments, `o(args...)` is expression-equivalent ([[defns.expression.equivalent]]) to a call to the overload set `S`.

Note 1 points out two consequences: algorithm function objects are not found by ADL, because ADL finds only functions ([[basic.lookup.argdep]]); and when unqualified lookup finds one for use in a function call, what it finds is an object, not a function, so ADL is not performed.

```cpp run ok
#include <algorithm>
#include <ranges>
#include <vector>
int main() {
  using namespace std::ranges;
  std::vector<int> vec{1, 2, 3};
  auto it = find(begin(vec), end(vec), 2);  // calls std::ranges::find;
                                            // std::find isn't found via ADL
  return *it == 2 ? 0 : 1;
}
```

The associated namespace of `vec`'s iterators is `std`. If `ranges::find` were an ordinary function template, ADL would pull the unconstrained `std::find` into the candidate set, and it could be a better match for a pair of iterators. Algorithm function objects make such an accidental choice impossible.

!!! lawyer "Using both namespaces"
    After `using namespace std;` and `using namespace std::ranges;`, a call `find(v.begin(), v.end(), x)` has unqualified lookup find both the function template `std::find` and the variable `std::ranges::find`. A lookup result containing both a function and a variable makes the call ambiguous ([[basic.lookup]]); Clang 23 reports "reference to 'find' is ambiguous".

!!! history "From niebloids to CPOs"
    C++20 only specified that the algorithms in `std::ranges` are not found by ADL, suppress ADL when found by unqualified lookup, and can't have template arguments specified explicitly; it didn't require them to be objects. Every implementation wrote them as function objects, which the community called niebloids (after Eric Niebler). C++26's [[P3136R1]] formally specified them as CPOs, so they can also be copied, passed to higher-order functions and used as template arguments.

## Enumerated and bitmask types [type.descriptions]

### Enumerated types ([enumerated.types])

¶1 Several types in [[input.output]] and [[re]] are [[g:enumerated-type|enumerated types]], such as `std::ios_base::seekdir`. Each enumerated type may be implemented as an enumeration or as a synonym for an enumeration.

¶2–¶3 The standard describes it with an exposition-only form: `enum enumerated { V0, V1, ... };` plus a set of constants `C0`, `C1` and so on, called enumerated elements, whose values are all distinct. Portable code can rely only on the elements existing and being distinct, not on specific values, and can't assume it is an `enum class`.

### Bitmask types ([bitmask.types])

¶1 Several types in the library are [[g:bitmask-type|bitmask types]], such as `ios_base::iostate`, `ios_base::openmode`, `regex_constants::syntax_option_type`, `launch` and `filesystem::perms`. Each bitmask type can be implemented as an enumerated type that overloads certain operators, as an integer type, or as a `bitset`.

¶2 The standard describes its interface with an exposition-only enumeration plus a set of operators: `&`, `|`, `^`, `~`, and `&=`, `|=`, `^=`.

¶3 The bitmask elements `C0`, `C1` and so on have distinct, nonzero values occupying different bits: `Ci & Ci` is nonzero, and `Ci & Cj` is zero when `i ≠ j`. The value 0 represents an empty bitmask, in which no elements are set.

¶4 Three terms are defined precisely: to **set** a value Y in an object X is to evaluate `X |= Y`; to **clear** Y is to evaluate `X &= ~Y`; Y **is set** in X if `X & Y` is nonzero.

```cpp run ok
#include <ios>
#include <sstream>
int main() {
  std::istringstream in("abc");
  int x;
  in >> x;                                    // extraction fails, failbit is set
  std::ios_base::iostate st = in.rdstate();
  bool failed = (st & std::ios_base::failbit) != 0;   // is set
  st &= ~std::ios_base::failbit;                      // clear
  return failed && st == std::ios_base::goodbit ? 0 : 1;
}
```

!!! pitfall "Relying on the underlying type of a bitmask"
    In libc++, `fmtflags`, `iostate` and `openmode` are all aliases for `unsigned int`, so `std::ios_base::openmode m = 0x10;` and `int i = std::ios_base::in;` both compile. That isn't necessarily so on a standard library that implements them as scoped enumerations. `std::launch` is specified as `enum class launch : unspecified` ([[future.syn]]); the result of its `|` is still a `launch` and doesn't implicitly convert to an integer.

## String terms [character.seq]

Library specifications often say that a function returns an ntbs, or require an argument to point to an ntbs. These terms are defined here:

- **character sequence**: an array of elements of type `char`, `unsigned char` or `signed char` (possibly cv-qualified), whose leading elements have defined content up to an element determined by some predicate; it can be designated by a pointer to its first element ([character.seq.general] ¶1.5).
- [[g:ntbs|**ntbs**]] (null-terminated byte string): a character sequence whose highest-addressed element with defined content is zero (the terminating null character), with no other element zero. Its length is the number of elements before the terminating null character; a static ntbs is an ntbs with static storage duration, and string literals are static ntbs's ([byte.strings]).
- [[g:ntmbs|**ntmbs**]] (null-terminated multibyte string): an ntbs consisting of valid multibyte characters, beginning and ending in the initial shift state. An ntbs containing only characters of the basic literal character set is also an ntmbs ([multibyte.strings]).

These terms are referenced throughout the library. `std::exception::what()` returns an implementation-defined ntbs; reflection's `std::meta::identifier_of` and contracts' `contract_violation::comment()` return an ntmbs. The *Effects* of `std::string(const char* s)` are equivalent to `basic_string(s, traits::length(s), a)`, and by [[structure.specifications#4]] the preconditions of `traits::length(s)` carry over, which in effect requires `s` to point to an ntbs.

[character.seq.general] ¶1 also sets out some locale-related conventions. The encoding of the execution character set is determined by the locale and can be unrelated to the encoding of literals in the source code (Note 1). The decimal-point character also varies with the locale, so `std::strtod("1,5", ...)` may parse as 1.5 in a German locale; `std::from_chars` isn't affected by the locale ([[charconv]]).

## Members not written out

¶1 ([functions.within.classes]) For brevity, the library clauses don't write out copy and move constructors, assignment operators and non-virtual destructors whose semantics are the same as the defaulted versions. Whether the implementation provides explicit definitions for them is unspecified.

So a synopsis that doesn't show a copy constructor doesn't mean the class has no copy constructor. And because whether they are explicitly defined is unspecified, whether these members are trivial isn't guaranteed, consistent with [[library.class.props]]: unless otherwise specified, it is unspecified whether a library class is trivially copyable.

¶1–¶3 ([objects.within.classes]) The library clauses don't specify the representation of classes, and implementations may add any static or non-static members as needed. To specify semantics, some subclauses give representative private member declarations, likewise commented exposition only, such as `streambuf* sb;      // exposition only`. An implementation may use any technique with the same observable behavior.

Exposition-only private members can't be accessed by programs and aren't guaranteed to exist; `sizeof(std::optional<int>)` need not equal `sizeof(bool) + sizeof(int)` plus padding. A few classes have normative non-private data members that aren't exposition only, such as `first` and `second` of `std::pair`, and the `protected` member `current` of `std::reverse_iterator`; derived classes can rely on them.

## Freestanding items [freestanding.item]

A **freestanding implementation** is an implementation that can run without an operating system and need provide only a subset of the standard library ([[intro.compliance]], [[compliance]]). Since C++23 ([[P1642R11]] and other papers), this subset is no longer divided by whole headers but marked declaration by declaration in the synopses.

### What a freestanding item is (¶1–¶2, ¶4–¶6)

¶1 A [[g:freestanding-item|**freestanding item**]] is a declaration, entity or macro that both freestanding and hosted implementations are required to provide. ¶2 Unless otherwise specified, the requirements on freestanding items for a freestanding implementation are the same as for a hosted implementation, except that not all of their members need be provided.

¶4 A declaration in a synopsis is a freestanding item if it is followed by a comment that includes *freestanding* (¶4.1) or *freestanding-deleted* (¶4.2); or if the header synopsis begins with a comment that includes *freestanding* and the declaration isn't followed by a comment that includes *hosted* (¶4.3). Note 2 points out that this means lookup for the same name can give different results on hosted and freestanding implementations.

¶5 The freestanding property propagates: entities introduced by a freestanding item declaration, members of a freestanding item, enumerators, deduction guides, friends, enclosing namespaces, and entities denoted by a freestanding item alias are all freestanding items too, as long as their introducing declaration isn't marked *hosted*. So `std::array` is a freestanding item, and by default so are its members and deduction guides. ¶6 has the same rule for macros, for example `#define NULL see below      // freestanding`.

### freestanding-deleted (¶3)

¶3 A function whose declaration is followed by a comment that includes *freestanding-deleted* is a [[g:freestanding-deleted-function]]. On a freestanding implementation, it is implementation-defined whether such a function is deleted ([[dcl.fct.def.delete]]) or has the same requirements as on a hosted implementation.

Note 1 explains why it is deleted rather than omitted: a deleted definition prevents overload resolution from silently changing its result when a program is moved from a freestanding implementation to a hosted one.

<div class="compare" markdown="1">

```cpp error
int    mag(int);
double mag(double) = delete;
double d = -2.5;
auto r = mag(d);   // error: selects the deleted function
```

```cpp ok
int mag(int);
// mag(double) omitted
double d = -2.5;
auto r = mag(d);   // silently converts to int
```

</div>

On the right, with the `double` version omitted, the call silently selects `mag(int)` and gets -2; on a hosted implementation that provides `mag(double)`, the same code gets -2.5. On the left, it is declared deleted, so it still participates in overload resolution and is selected, and compilation fails on the freestanding implementation, exposing the problem on the spot.

The standard's Example 1 is `double abs(double j);  // freestanding-deleted`. Example 4 is `std::array`: `operator[]` is freestanding, while `at()`, which throws `out_of_range`, is marked *freestanding-deleted*, because a freestanding implementation may not support exceptions, yet `at` mustn't silently disappear.

```cpp
template<class T, size_t N> struct array;               // partially freestanding
template<class T, size_t N>
struct array {
  constexpr reference       operator[](size_type n);
  constexpr const_reference operator[](size_type n) const;
  constexpr reference       at(size_type n);            // freestanding-deleted
  constexpr const_reference at(size_type n) const;      // freestanding-deleted
};
```

¶7 Note 3 describes some writing conventions that carry no additional normative requirements: `// all freestanding` at the start of a header means it contains no hosted items and no freestanding deleted functions; `// mostly freestanding` means it contains at least one; `// partially freestanding` after a class means the class has at least one hosted member or freestanding deleted function. The partially freestanding class mechanism comes from [[P2407R5]].

## Common misconceptions

!!! pitfall "Trying to use exposition-only names"
    Seeing *decay-copy* or *boolean-testable* in the standard or on cppreference and assuming you can write `std::decay_copy(x)`. These names don't exist; when you need them, use public facilities such as `auto(x)` and `std::convertible_to`, or write your own.

!!! pitfall "Treating a CPO as an ordinary function"
    A CPO is an object, so ADL can't find it and you can't add overloads for it (adding declarations to `std::ranges` is UB anyway; see [[namespace.std]]). To customize it, use the route it specifies: a member `begin()`, a non-member `begin` found by ADL, `enable_borrowed_range` and so on, rather than specializing it.

## Questions

!!! question "Question 1"
    Why does the standard require a CPO's type to be structural and trivially copyable, and all its instances to be equal? If an implementation gave `std::ranges::begin` an `int` state member, what would break?

<details markdown="1">
<summary>Answer</summary>

Being a structural type ([[temp.param]]) lets a CPO be a constant template argument, as in `holder<std::ranges::begin>`. Being trivially copyable guarantees that copying has no side effects. All instances being equal with the same effects (¶3), together with ¶5's requirement that `p(args...)` be equivalent to `o(args...)` after `auto p = o;`, guarantees that a CPO is a stateless name.

With a state member, different instances could behave differently, and `holder<o1>` and `holder<o2>` could become different types. That violates ¶2–¶3, and such an implementation doesn't conform.
</details>

!!! question "Question 2"
    A freestanding implementation provides `<cmath>` and implements `double abs(double)` as a deleted function. What happens with the following code on this implementation?

    ```cpp
    #include <cmath>
    int f() { return std::abs(-2.5) > 2 ? 1 : 0; }
    ```

<details markdown="1">
<summary>Answer</summary>

`abs(double)` is an exact match in overload resolution and is selected; it is a deleted function, so the program is ill-formed ([[dcl.fct.def.delete]]) and the compiler must report an error. This is exactly the purpose of Note 1 in ¶3: if `abs(double)` simply didn't exist, the call would fall to the remaining integer versions and either truncate silently or be ambiguous because several integer versions are equally good; in the former case the program would give different results on the two implementations.
</details>

<details class="fine" markdown="1"><summary>Remaining wording</summary>

[conventions.general] ¶1: this subclause describes several editorial conventions used to describe implementation-defined types and member functions in the library specification.

[type.descriptions.general] ¶1: the Requirements subclauses may describe names that are used to specify constraints on template arguments; a footnote lists *Cpp17EqualityComparable*, *Cpp17CopyConstructible*, *Cpp17InputIterator* and others. The library clauses use these names to describe the types a program may supply when instantiating library templates. For example, [[algorithms.requirements]] says that the argument for a template parameter named `ForwardIterator` must meet *Cpp17ForwardIterator*. Such a requirement is only a textual convention, not a real constraint like `template<forward_iterator I>`, and a violation is UB ([[res.on.functions#2.3]]). ¶2: some types in [[input.output]] are used to describe implementation-defined types; they are based on other types but with added constraints.

The remaining items of [character.seq.general] ¶1: locale-specific properties can be changed during execution by `setlocale` or by changing a locale object (¶1.1); the execution character set and execution wide-character set are supersets of the basic literal character set ([[lex.charset]]), and each element of the execution wide-character set is represented by a single `wchar_t` code unit (¶1.2); letter means any of the 52 uppercase and lowercase Latin letters of the basic character set (¶1.3); *STATICALLY-WIDEN*<charT>("...") is `"..."` when `charT` is `char` and `L"..."` when it is `wchar_t`, and the specifications of `<format>` and `<chrono>` use it to write the narrow and wide versions of the same string (¶1.6).

[byte.strings] ¶2–¶3: the length of an ntbs is the number of elements before the terminating null character, and an empty ntbs has length zero; the value of an ntbs is the sequence of element values up to and including the terminating null character. [multibyte.strings] ¶1: a multibyte character is one or more bytes representing a character of the execution character set; ¶3: a static ntmbs is an ntmbs with static storage duration.

</details>
