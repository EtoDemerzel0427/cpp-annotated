---
title: Class types as template parameters (P0732, P1907)
summary: How C++20 let class types and floating-point numbers become constant template parameters. The first design used the defaulted <=> to decide whether two arguments are the same; after a series of inconsistencies came to light it was replaced by member-wise structural types, and that choice is behind today's rules for fixed_string, -0.0 and private members.
tags: proposal, templates, constant template parameters, NTTP, structural types, fixed_string, C++20
group: Core language
updated: 2026-10-19
---

!!! tldr
    - In C++17 a constant template parameter could only be a scalar such as an integer, enumeration, pointer or reference. To use a string as a template argument you had to split it into a sequence of `char`s.
    - The hard part is not syntax but deciding whether `X<a>` and `X<b>` are the same type. Every translation unit must reach the same answer, and the answer must be encodable in a symbol name for the linker.
    - [[P0732R2]] answered this with compiler-generated comparison operators (first the defaulted `<=>`, later the defaulted `==`). [[P1907R1]] dropped the connection to comparison operators and switched to structural types compared member by member.
    - So today's rules are: all members must be public; a user-written `operator==` plays no part at all; `0.0` and `-0.0` are two different arguments; a string literal still cannot be the argument for a pointer parameter directly and must first be copied into a class object.

## The problem: strings can't get into templates

A template's **constant template parameter** ([[g:constant-template-parameter]], formerly called a non-type template parameter, or NTTP) accepts a value rather than a type. Up to C++17 that value could only be an integer, enumeration, pointer, pointer to member, lvalue reference or `std::nullptr_t`. To give a type a name, you had to split the name into characters:

```cpp run title="char-pack.cpp" std=c++17 ok
#include <cstdio>
// C++17: a string can only be split into a char pack
template<char... Cs> struct Name {
  static void print() {
    static constexpr char s[] = {Cs..., '\0'};
    std::puts(s);
  }
};
using Hello = Name<'h','e','l','l','o'>;
int main() { Hello::print(); }
```

This is hard to read and hard to produce by computation. Several earlier proposals wanted string literal operator templates to produce such `char` packs directly; the motivation section of [[P0732R2]] summarizes that the main objection was the time and memory compilers spend on long `char` packs. [[P0424R2]] took a different route and allowed strings as template parameters, but only with a string literal itself as the argument; a computed string still could not get into a template.

The more natural approach is to put the characters into a class object. Since C++11 a class object can be a constant expression, but it cannot be a template argument:

<div class="compare" markdown="1">

```cpp std=c++17 error
struct Point { int x, y; };

// C++17: error
template<Point P> struct At {};
At<Point{1, 2}> a;
```

```cpp std=c++20 ok
struct Point { int x, y; };

// OK since C++20
template<Point P> struct At {};
At<Point{1, 2}> a;
```

</div>

Compiling the left one with Clang 23 and `-std=c++17` reports `a non-type template parameter cannot have type 'Point' before C++20`. Arrays don't help either: a parameter written as `char s[6]` is adjusted to `char*` just like a function parameter ([[temp.param#15]]), and the value is a pointer again.

## The real difficulty: when are two arguments the same

Each set of template arguments corresponds to one specialization. If `At<Point{1, 2}>` appears in two translation units, it must be the same type, with only one copy of its static members and member functions. The standard decides whether two *template-id*s are the same in [[temp.type#1]], and for constant arguments it requires the two values to be **template-argument-equivalent** ([[g:template-argument-equivalent]], ¶1.3).

For scalars this is easy: integers are the same if their values are equal, pointers are the same if they point to the same object. In implementations, the compiler encodes the argument value into the mangled symbol name, and the linker merges identical specializations by comparing symbol names.

Class types have no ready-made notion of sameness. Section 4 of [[P0732R2]] states the problem as an invariant: for `template<auto> int i;`, we want `&i<a> == &i<b>` if and only if `a == b`. C++17's scalar arguments mostly satisfy it. For class types, the paper lists three paths:

| Option | Approach | Cost |
|---|---|---|
| Give up the invariant | Compare member by member, ignoring the class's own `==` | Type identity and the equality the user sees may disagree |
| Call the user's `==` | Both compiler and linker evaluate the user-written comparison | The user's comparison must be verified as consistent; the linker can't do that |
| Only accept classes with member-wise equality | Require the class's comparison to be compiler-generated | Needs a language mechanism to guarantee it |

P0732R2 chose the third. The second is infeasible because the linker only sees symbol names and can only compare encoded values. A user's `operator==` might not be an equivalence relation, might differ between translation units, or might be declared only after the first use, while the identity of a template specialization must be consistent across the whole program, or else it is an ODR violation ([[basic.def.odr]]).

## P0732R2: the defaulted `<=>` as a guarantee

C++20 introduced, at the same time, the three-way comparison operator `<=>` that can be `= default`ed ([[class.compare]]). P0732R2 borrowed it: if a class and all its members and bases have an in-class defaulted `<=>` whose result type is `strong_ordering` or `strong_equality`, the type is said to have **strong structural equality** and can be the type of a constant parameter. This guarantees three things: the class has a comparison operator, every translation unit sees the same comparison, and that comparison is member-wise.

The conceptual model the paper gives is that a parameter of class type is equivalent to one constant parameter for each base and each member (each element, for arrays). `template<pair<int,int> x>` is roughly `template<int first, int second>`.

<div class="compare" markdown="1">

```cpp ok
// What P0732R2 required
#include <compare>
struct Point {
  int x, y;
  auto operator<=>(const Point&)
      const = default;
};
template<Point P> struct At {};
At<{1, 2}> a;
```

```cpp ok
// Today: no comparison operator needed
struct Plain { int x, y; };

template<Plain P> struct At2 {};
At2<{1, 2}> b;
```

</div>

Both compile with Clang 23 today; the extra `<=>` on the left is harmless but no longer needed. The same paper also settled several design points that remain to this day:

- A parameter of class type is, inside the template, an lvalue of type `const T` designating a **template parameter object** ([[g:template-parameter-object]]) with static storage duration. Each distinct value has exactly one such object in the whole program, so you can take its address and call its `const` member functions (today's [[temp.param#13]]).
- The parameter type can be written as just a class template name, with class template argument deduction determining the concrete type; `template<fixed_string S>` together with a deduction guide lets you write `A<"hello">` ([[temp.param#11]], ¶11.3).
- A new **string literal operator template** ([[g:string-literal-operator-template]]): a literal operator template whose parameter is a single constant parameter of class type; `"hello"_udl` is treated as `operator""_udl<"hello">()` ([[over.literal#5]], [[lex.ext#5]]). This absorbs the syntax of P0424R2, with the parameter changed to a class type.
- A class with a reference member cannot be a parameter type. The reason is that references have two kinds of equality: `==` compares the referenced values, while template arguments compare the identity of the referenced objects.

Later, [[P1185R2]] separated the defaulted `<=>` from the defaulted `==`, and strong structural equality was changed to require an in-class defaulted `==`. P0732's idea stayed the same: type identity is guaranteed through compiler-generated comparison operators.

## Where the guarantee breaks

After P0732 went into the C++20 draft, [[P1837R0]] argued for withdrawing it entirely, and [[P1907R0]] systematically catalogued the inconsistencies. They all came from the same premise: equality and identity are two different things, and in C++17 they already were.

The first example is enumerations. Enumerations have strong structural equality, but the user can overload `operator==` for them anywhere. The code below is already valid in C++17: `==` says the two enumerators are equal, while the template treats them as two arguments:

```cpp run title="enum-eq.cpp" ok
#include <type_traits>
enum E { ONE, TWO };
constexpr bool operator==(E, E) { return true; }
static_assert(ONE == TWO);

template<E> struct X {};
static_assert(!std::is_same_v<X<ONE>, X<TWO>>);
int main() {}
```

P1837R0 points out that under P0732's wording it is unclear how a class with an `E` member and a defaulted `==` should compare: should the defaulted `==` call this user-written `operator==(E, E)`? What if it is declared only after the class definition?

P1907R0 divides the inconsistencies into two kinds:

- **Kind (A)**: the result of `x == y` at run time disagrees with `std::is_same_v<A<x>, A<y>>`.
- **Kind (B)**: a value behaves differently as a template argument directly than as a class member passed as part of a class object.

It went through the existing types one by one:

| Type | As a direct argument | As a class member | Inconsistency |
|---|---|---|---|
| Reference | Compares identity of the referenced object | Classes with reference members not allowed | (A), (B) |
| Pointer to member | For a union, `&U::x` and `&U::y` are different arguments, but `==` is true ([[expr.eq#5]], ¶5.5) | Compared with `==` | (A), (B) |
| Floating point | [[P1714R1]] proposed bitwise comparison | Floating-point `<=>` is only `partial_ordering`, no strong structural equality | (A), (B) |
| Types with a user `==` | Enumerations allowed | Classes not allowed | (A) |

The floating-point row deserves more detail. P1714R1 wanted to support interfaces like `template<double Exp> double pow(double)` and proposed comparing floating-point arguments by value representation, so `A<+0.0>` and `A<-0.0>` are two types while `+0.0 == -0.0` is true. Yet under P0732's model `double` could not appear as a class member, because it would never have strong structural equality. P1714R1 itself mentions having considered splitting a floating-point number into three integers (sign, exponent, mantissa) and then applying P0732's rules, but that cannot distinguish `+0.0` from `-0.0`, and infinities and NaN are hard to handle too.

P1907R0 proposes two ways out: either separate template-argument equality from `operator==` entirely and use the top-level argument rules for class members too, accepting more kind (A) inconsistencies; or forbid more types as class members. It recommends the former, on the grounds that kind (A) inconsistencies had existed for years with references and pointers to members, while kind (B) could be eliminated entirely this way.

## P1907R1: structural types

[[P1907R1]] rewrote the rules in this direction, and it is what C++20 shipped with. The term strong structural equality was removed, and the type of a constant parameter became a **structural type** ([[g:structural-type]]):

!!! std
    a literal class type with the following properties: all base classes and non-static data members are public and non-mutable and the types of all base classes and non-static data members are structural types […]

    ([[temp.param#12]], ¶12.3) A structural type is a scalar type, an lvalue reference type, or a literal class whose bases and members are all public, non-mutable, and themselves of structural type (or arrays thereof).

There is no comparison operator anywhere in this definition. Sameness is instead decided by template-argument-equivalence, defined case by case in [[temp.type#2]]: integers have the same value, floating-point values are identical, pointers have the same value, references refer to the same object, pointers to members refer to the same member, and for class types the corresponding direct subobjects and reference members are equivalent. Class members and top-level arguments use the same rules, so kind (B) inconsistencies are gone.

Each group of assertions below corresponds to one row of the table above; `==` and type identity part ways:

```cpp run title="equivalence.cpp" ok
#include <type_traits>

// a user-written == plays no part
struct Mod10 {
  int v;
  constexpr bool operator==(const Mod10& o) const {
    return v % 10 == o.v % 10;
  }
};
template<Mod10 M> struct T {};
static_assert(Mod10{3} == Mod10{13});
static_assert(!std::is_same_v<T<Mod10{3}>, T<Mod10{13}>>);

// still a valid parameter type with == deleted
struct NoEq {
  int v;
  bool operator==(const NoEq&) const = delete;
};
template<NoEq N> struct U {};
static_assert(std::is_same_v<U<NoEq{1}>, U<NoEq{1}>>);

// reference members are now allowed; identity is compared
int a = 1, b = 1;
struct Ref { const int& r; };
template<Ref R> struct V {};
static_assert(!std::is_same_v<V<Ref{a}>, V<Ref{b}>>);
static_assert(std::is_same_v<V<Ref{a}>, V<Ref{a}>>);

// pointer to member as a class member: same rule as at top level
union Un { int x; int y; };
template<int Un::*p> struct W {};
struct PM { int Un::*p; };
template<PM p> struct W2 {};
static_assert(!std::is_same_v<W<&Un::x>, W<&Un::y>>);
static_assert(!std::is_same_v<W2<PM{&Un::x}>, W2<PM{&Un::y}>>);

int main() {}
```

!!! impl "Clang and `==` on union member pointers"
    By [[expr.eq#5]] (¶5.5), `&Un::x == &Un::y` is true. Clang 23 gets 1 at run time but evaluates it as false during constant evaluation, so `static_assert(&Un::x == &Un::y)` fails. That is why the example above does not include this assertion. This is a Clang deviation and has nothing to do with template arguments.

### Why everything must be public

The rules no longer need a comparison operator; the price is that the compiler must be able to see and encode every member of the class. P1907R1 chose to accept only classes whose members are all public; a type with private members is rejected, even if its constructor is `constexpr`:

```cpp title="private.cpp" error
#include <string_view>
class Version {
  int major_, minor_;
public:
  constexpr Version(int a, int b) : major_(a), minor_(b) {}
  constexpr int major() const { return major_; }
};
template<Version V> struct Api {};          // error: has private members
template<std::string_view S> struct Tag {}; // error: libc++'s members are private
```

Clang 23 reports the error at the parameter declaration, with the note `'Version' is not a structural type because it has a non-static data member that is not public`.

The paper itself gives no rationale for the public requirement. Its role can be seen from the problem it solves: type identity is determined by the values of all members. If some members are not visible, the class author may treat them as implementation details (for example an unused tail of a buffer) and consider two values equal, while the compiler treats them as different specializations. Requiring all members to be public at least indicates that member-wise comparison is semantics the class author openly accepts. The later [[P3380R1]] analyzes this problem in detail with a small string class; see below.

### Pointers may now point to subobjects

P1907R1 also changed the list of restrictions in [[temp.arg.nontype]]. In C++17, pointer and reference arguments could not refer to subobjects. The new rules removed that item and instead forbid referring to temporaries, string literals, results of `typeid`, `__func__`, and subobjects of these (today's [[temp.arg.nontype#6]]). `P<&arr[1]>` and `P<&s.m>` are valid from then on; see the corresponding section of [[temp.arg]] for examples.

## Floating point: `-0.0` and NaN

The first item in the definition of structural type is scalars, and floating-point numbers are scalars, so `double` became a valid parameter type along the way, and can appear in class members too. Equivalence requires floating-point values to be identical, not `==`:

```cpp run title="double-nttp.cpp" ok
#include <cmath>
#include <cstdio>
#include <limits>
#include <type_traits>

template<double Exp>
double power(double base) {
  if constexpr (Exp == 2.0)      return base * base;
  else if constexpr (Exp == 0.5) return std::sqrt(base);
  else                           return std::pow(base, Exp);
}

template<double D> struct F {
  static constexpr double value = D;
};
static_assert(0.0 == -0.0);
static_assert(!std::is_same_v<F<0.0>, F<-0.0>>);   // two specializations
static_assert(std::is_same_v<F<0.5>, F<1.0 / 2>>); // same value, same one

constexpr double qnan = std::numeric_limits<double>::quiet_NaN();
static_assert(!(qnan == qnan));
static_assert(std::is_same_v<F<qnan>, F<qnan>>);   // same specialization

struct Scale { double factor; };
template<Scale S> struct G {};
static_assert(!std::is_same_v<G<Scale{0.0}>, G<Scale{-0.0}>>);

int main() {
  std::printf("%g %g %g\n", power<2.0>(3), power<0.5>(9), power<3.0>(2));
  std::printf("%g %g\n", 1 / F<0.0>::value, 1 / F<-0.0>::value);
}
```

Clang 23 prints `9 3 8` and `inf -inf`. Distinguishing `0.0` from `-0.0` is intentional: the two can be told apart at run time (`1 / -0.0` is negative infinity), and P1714R1 chose comparison by representation for this reason. Conversely, `NaN != NaN`, but the same NaN used as an argument still gives the same specialization.

If you write an explicit specialization for `0.0`, `F<-0.0>` will not use it. P1714R1 acknowledges this consequence in its own section on drawbacks.

!!! impl "Symbol names for floating-point arguments"
    Clang 23 mangles `f<0.0>()` and `f<-0.0>()` as `_Z1fILd0000000000000000EEiv` and `_Z1fILd8000000000000000EEiv` respectively. The Itanium ABI encodes the bit pattern of the `double` directly; the two zeros differ in the sign bit, so naturally they are two symbols.

## String literals still can't be used directly

C++20 solved the problem of getting strings into templates, but by copying them into class objects. A pointer parameter, or a pointer member of a class, still cannot point to a string literal ([[temp.arg.nontype#6]], ¶6.2), because whether two identical literals are the same object is unspecified, and across translation units they usually aren't:

<div class="compare" markdown="1">

```cpp error
struct str_ref {
  const char* p;
  constexpr str_ref(const char* s)
    : p(s) {}
};
template<str_ref S> struct Tag {};

Tag<"price"> t;  // error
```

```cpp ok
struct str_ref {
  const char* p;
  constexpr str_ref(const char* s)
    : p(s) {}
};
template<str_ref S> struct Tag {};

static constexpr char name[] = "price";
Tag<name> t;     // OK: named array
```

</div>

For the left side Clang 23 reports `pointer to subobject of string literal is not allowed in a template argument`. What works is copying the characters into a member array, which is exactly the `fixed_string` P0732R2 envisioned:

```cpp run title="fixed-string.cpp" ok
#include <cstddef>
#include <cstdio>
#include <type_traits>

template<std::size_t N>
struct fixed_string {
  char data[N]{};
  constexpr fixed_string(const char (&s)[N]) {
    for (std::size_t i = 0; i < N; ++i) data[i] = s[i];
  }
  constexpr std::size_t size() const { return N - 1; }
};

template<fixed_string Name>      // class template argument deduction finds N
struct Field {
  static void print() { std::printf("%s (%zu)\n", Name.data, Name.size()); }
};

// string literal operator template
template<fixed_string S>
constexpr auto operator""_f() { return Field<S>{}; }

// a string computed at compile time works as an argument too
constexpr fixed_string<4> make() {
  fixed_string<4> s("abc");
  s.data[0] = 'x';
  return s;
}

int main() {
  Field<"price">::print();
  decltype("qty"_f)::print();
  Field<make()>::print();
  static_assert(std::is_same_v<Field<"id">, decltype("id"_f)>);
}
```

Clang 23 prints `price (5)`, `qty (3)`, `xbc (3)`, and `-std=c++20` passes as well. The constructor of `fixed_string` only uses the literal as an argument; the template parameter object stores the character values. `Field<make()>` uses a value computed by a function, which neither `char` packs nor P0424R2 could do.

A template parameter object exists only once in the whole program. Put `template<fixed_string S> const void* where() { return &S; }` in a header and take `where<"hi">()` in each of two translation units; in our test, comparing the results after linking gives 1 (the same address). The symbol for this object in the object file is `_ZTAXtl12fixed_stringILm3EEtlA3_cLc104ELc105EEEE`, which `c++filt` shows as `template parameter object for fixed_string<3ul>{"hi"}`: after the class name come `'h'` (104) and `'i'` (105), encoded element by element, which is exactly P0732R2's member-wise model.

## Later changes

After C++20, the rules changed in a few places, and several directions remain unfinished.

**Initialization details**. P0732R2 and P1907R1 only said the argument is converted to the type of the parameter; they did not say how the template parameter object of class type is constructed from the argument. [[P2308R1]] filled this in: first a temporary `constexpr T v = A;` is initialized with the argument (called the candidate initializer), then the template parameter object is copy-initialized from a candidate initializer equivalent to it; the result of the copy must be equivalent to `v`, otherwise the program is ill-formed ([[temp.arg.nontype#3]], [[temp.arg.nontype#4]]). This rules out types whose copy constructor changes the value; see [[temp.arg]] for an example.

**Renaming**. The current draft renames non-type template parameters to **constant template parameters** throughout ([[temp.param#2]], ¶2.2); this is an editorial change. [[P2841R7]] builds on it and adds concept template parameters and variable template template parameters; its revision history states that its wording has been rewritten in terms of the new name.

**Making more types usable**. The members of `std::string_view`, `std::optional` and `std::tuple` are private, so to this day they cannot be parameter types. [[P2484R0]] proposed letting a type provide a conversion that represents itself as a value of some structural type. [[P3380R1]] restates the problem as three steps, serialization, normalization and deserialization, and uses a `SmallString` to show why serialization alone is not enough: if two strings with the same contents but different buffer tails were treated as the same argument, code that depends on the tail contents would get two different results, an ODR violation. P3380R1 also proposes using normalization to let string literals be arguments. As of the current draft, neither proposal has been merged.

**Annex C**. C++20's [[diff.cpp17]] has no entries related to these two proposals: they only make previously ill-formed programs well-formed.

## Compiler support

| Feature | Paper | Clang |
|---|---|---|
| Constant parameters of class type | P0732R2 | Since Clang 12 |
| Structural types, floating point, pointers to subobjects | P1907R1 | Since Clang 18, partial |

The versions in the table come from Clang's C++ support status page, which notes that the parts of P1907R1 concerning references to objects declared inside templates and their subobjects are not yet fully supported. Every example on this page passes or is rejected with Clang 23 as marked.

The feature-test macro `__cpp_nontype_template_args` has been `201911L` since C++20, and the current draft still has that value ([[cpp.predefined]]). Clang 23 still reports `201411L` (the C++17 value) under `-std=c++2c`, consistent with the partial support above; portable code should not use this macro to tell whether Clang supports class-type parameters.

## Summary

| Question | P0732R2's answer | After P1907R1 (today) |
|---|---|---|
| Which classes can be parameter types | Literal classes with an in-class defaulted `<=>` (later `==`) | Structural types: all members public, non-mutable, of structural type |
| When two arguments are the same | By the result of the defaulted comparison operator | By subobject-wise comparison per [[temp.type#2]], unrelated to `==` |
| Floating point | Not allowed | Allowed, compared by identical value; `0.0` and `-0.0` differ |
| Reference members | Not allowed | Allowed, comparing identity of the referenced objects |
| Pointers to subobjects | Not allowed | Allowed |
| String literals | Only usable to construct class objects | Unchanged |

Named template arguments are a common use of this feature: write a set of options as an aggregate and pass it to the template with designated initializers; see the section on default policies and named template arguments in [[patterns/policy-based-design|policy-based design]].

## Questions

!!! question "Question 1"
    Are the two types below the same? Would the answer change if `operator==` compared `abs(v)` instead?

    ```cpp
    struct S { int v; bool operator==(const S&) const = default; };
    template<S s> struct X {};
    using A = X<S{-1}>;
    using B = X<S{1}>;
    ```

<details markdown="1">
<summary>Answer</summary>

They are different, and changing `operator==` does not change that. `S` is a structural type ([[temp.param#12]]); the only direct subobject `v` of the two arguments is `-1` and `1` respectively, integers with different values, so they are not template-argument-equivalent ([[temp.type#2]], ¶2.1, ¶2.12). The equivalence check never calls `operator==`.
</details>

!!! question "Question 2"
    Why does `template<std::array<char, 6> s> struct T {};` compile with Clang 23 while `template<std::string_view s> struct U {};` does not? Does the standard guarantee the former is portable?

<details markdown="1">
<summary>Answer</summary>

`std::array` is an aggregate whose only member, in implementations, is a public array, which satisfies the requirements for a structural type. Implementations of `std::string_view` make the pointer and length private members, which violates ¶12.3.1. The standard only specifies the interfaces of library types and does not say, type by type, whether they are structural, so whether the former can be a parameter type depends on the implementation; see the note about standard library types in [[temp.param]]. Even if `string_view` could be one, pointing it at a string literal would be rejected by [[temp.arg.nontype#6]].
</details>
