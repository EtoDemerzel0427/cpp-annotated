---
title: "Template metaprogramming: from accidental Turing completeness to static reflection"
summary: Templates were designed only for containers and algorithms, yet turned out by accident to be a compile-time language; from C++11 on, the language took over its uses one by one with constexpr, variadic templates, if constexpr, concepts and static reflection, and traces of the old techniques remain in the rules today.
tags: templates, metaprogramming, SFINAE, constexpr, concepts, reflection, history
updated: 2026-10-19
---

!!! tldr
    - Templates were designed only for writing generic code like `vector<T>`. Specialization, non-type parameters and recursive instantiation together turned out, by accident, to form a language that runs at compile time.
    - C++98 metaprogramming encoded everything as types: specializations served as branches, recursion as loops, `enum`s held results, and SFINAE plus `sizeof` detected properties of types.
    - From C++11 on, the language took over these uses one by one: `constexpr` functions compute values, variadic templates replace type lists, `if constexpr` replaces pairs of `enable_if`s, and concepts put requirements into interfaces.
    - Reflection did not follow the type-based Reflection TS; it switched to the value-based `std::meta::info`, because compile-time value computation had become powerful enough and is cheaper than instantiating types. C++26 adopted that design.
    - The `typename` and `template` disambiguators, two-phase lookup, the recommended minimum of 1024 levels of instantiation depth, and the still-unresolved friend injection problem are all traces this history left in today's rules.

The historical material on this page comes mainly from Stroustrup's two HOPL papers (HOPL III: *Evolving a language in and for the real world: C++ 1991–2006*; HOPL IV: *Thriving in a Crowded and Changing World: C++ 2006–2020*), WG21 papers, and articles by the people involved. Details of the rules themselves are in the clause pages and the topic page [[topics/compile-time-programming]].

## Templates were not designed as a language

Looking back, Stroustrup says that when he was designing templates, from about 1987, he wanted three things (HOPL IV §6.1):

- Generality, able to express uses the designer did not anticipate;
- Zero overhead compared with hand-written code; `vector` had to be able to compete with C arrays;
- Well-defined interfaces, with type checking and overloading of template arguments as good as for ordinary functions.

The first two were achieved, the third was not. HOPL IV's summary: C++ got Turing completeness, better-than-hand-written performance, and lousy interfaces. The first two made templates very popular and also made them a compile-time language; the third produced thirty years of unreadable error messages, and eventually led to C++20 concepts (see [[history/concepts]]).

## 1994: a compiler lists primes in its error messages

In 1994 Erwin Unruh of Siemens showed a standards committee meeting a program that did not compile. The compiler's error messages contained 2, 3, 5, 7, 11… in order; these primes had been computed by the compiler while instantiating templates (Unruh's personal web page; HOPL III §7.2.2; committee document N462).

The original program relied on a C++98 rule: any integral constant expression with value zero is a null pointer constant. Composite numbers made the initializer 0 and the conversion succeeded; primes made the initializer 1 and the conversion failed with an error. [[CWG903]] later restricted null pointer constants to integer literals with value zero, so the original reports an error for every number on today's compilers. Below is a rewrite under today's rules, with the same idea, except that only primes go down a path that must fail:

```cpp error title="unruh.cpp"
template <int i> struct D { D(void*); };            // can only be constructed from a pointer

template <int p, int i> struct is_prime {
    static constexpr bool value = (p % i) && is_prime<(i > 2 ? p : 0), i - 1>::value;
};
template <> struct is_prime<0, 0> { static constexpr bool value = true; };
template <> struct is_prime<0, 1> { static constexpr bool value = true; };

template <int n, bool prime> struct Report { static void f() {} };
template <int n> struct Report<n, true> {
    static void f() { D<n> d = 1; }                 // error: only primes instantiate this line
};

template <int n> struct Prime_print {
    Prime_print<n - 1> a;
    void f() { Report<n, is_prime<n, n - 1>::value>::f(); a.f(); }
};
template <> struct Prime_print<2> { void f() { Report<2, true>::f(); } };

int main() { Prime_print<20>{}.f(); }
```

Clang 23 gives 8 errors of the form `no viable conversion from 'int' to 'D<19>'`, with 2, 19, 17, 13, 11, 7, 5 and 3 in the angle brackets.

The program shows that the template instantiation mechanism by itself can do non-trivial computation. HOPL III §7.2.2 records that Stroustrup and others found it impressive rather than frightening, since full generality was exactly the design goal of templates. In 2003 Todd Veldhuizen wrote a short paper giving a semi-formal proof that templates are Turing complete; HOPL III puts it more cautiously: ignoring compiler resource limits, the template instantiation mechanism is Turing complete.

## C++98: everything as types

C++98's compile-time language had only two kinds of data, types and integral constants. All computation had to go through the type system.

### Values, branches and loops

On the left below is the C++98 way: a class template specialization serves as the termination condition of the recursion, the result is stored in an `enum`, and the assertion relies on array lengths not being allowed to be negative. On the right is the C++14 way, also evaluated at compile time:

<div class="compare" markdown="1">

```cpp run ok std=c++98
template <unsigned N>
struct fact {
  enum { value = N * fact<N - 1>::value };
};
template <>
struct fact<0> { enum { value = 1 }; };

int a[fact<5>::value == 120 ? 1 : -1];
```

```cpp run ok
constexpr unsigned fact(unsigned n) {
  unsigned r = 1;
  for (; n > 1; --n) r *= n;
  return r;
}

static_assert(fact(5) == 120);
```

</div>

On the left, every value computed requires instantiating a class; `fact<5>` produces 6 classes. The compiler has to keep full class information for every instantiation, which is the root cause of compile times and memory use later getting out of hand.

A compile-time conditional branch is also a class template, and the result of the choice is a type:

```cpp run ok std=c++98 title="if_.cpp"
template <bool B, class X, class Y> struct if_ { typedef X type; };
template <class X, class Y> struct if_<false, X, Y> { typedef Y type; };

typedef if_<(sizeof(int) < 4), long, int>::type small_int;
int main() { small_int x = 0; return x; }
```

Veldhuizen's *Using C++ Template Metaprograms*, published in *C++ Report* in 1995, popularized this style. Today's `std::conditional` in the standard library ([[meta.trans.other]]) is `if_`.

### Traits: querying properties of types at compile time

The STL needed to ask at compile time what type an iterator points to. The early STL did this with overloading, which was unsystematic and error-prone. Nathan Myers's 1995 solution was a helper template that collects information about a type in one place, with partial specialization handling cases like pointers that have no member types (HOPL III §4.1.5).

```cpp run ok std=c++98 title="traits.cpp"
template <class Iter>
struct iterator_traits {                 // general case: ask the iterator itself
    typedef typename Iter::value_type value_type;
};
template <class T>
struct iterator_traits<T*> {             // pointers have no member types; a partial specialization fills in
    typedef T value_type;
};

template <class Iter>
typename iterator_traits<Iter>::value_type first(Iter it) { return *it; }

int main() { int a[] = {42}; return first(a) == 42 ? 0 : 1; }
```

Partial specialization itself was only added to C++ in 1995. Traits are the most successful legacy of this period: `std::iterator_traits` is still in use, and `<type_traits>` ([[meta]]) extends the technique to every property of types.

### Expression templates: a by-product of the zero-overhead goal

Implemented with ordinary operator overloading, `x = a + b + c` produces two temporary vectors and three loops. Expression templates make `operator+` not compute anything immediately, but return an object recording how to compute; at assignment, a single loop computes everything:

```cpp run ok std=c++98 title="expression-templates.cpp"
#include <cstddef>

template <class L, class R>
struct Sum {                                     // represents l + r, not yet computed
    const L& l; const R& r;
    Sum(const L& l_, const R& r_) : l(l_), r(r_) {}
    double operator[](std::size_t i) const { return l[i] + r[i]; }
};

struct Vec {
    double d[3];
    double operator[](std::size_t i) const { return d[i]; }
    template <class E>
    Vec& operator=(const E& e) {                 // one loop computes the whole expression, no temporary Vec
        for (std::size_t i = 0; i < 3; ++i) d[i] = e[i];
        return *this;
    }
};

inline Sum<Vec, Vec> operator+(const Vec& a, const Vec& b) { return Sum<Vec, Vec>(a, b); }
template <class L, class R>
Sum<Sum<L, R>, Vec> operator+(const Sum<L, R>& a, const Vec& b) { return Sum<Sum<L, R>, Vec>(a, b); }

int main() {
    Vec a = {{1, 2, 3}}, b = {{4, 5, 6}}, c = {{7, 8, 9}}, x;
    x = a + b + c;                               // the type of a + b + c is Sum<Sum<Vec, Vec>, Vec>
    return x[2] == 18 ? 0 : 1;
}
```

Veldhuizen and Daveed Vandevoorde discovered this technique independently (HOPL III §7.2.2). It shows that metaprogramming is not just showing off: with the structure of the expression encoded in a type, the compiler can generate one fused loop for the whole expression. Linear algebra libraries such as Eigen still work this way.

### SFINAE: detection and overload switches

Template argument deduction has a rule: if substituting the deduced arguments into a function template's declaration produces an invalid type or expression, that candidate is silently removed from the overload set instead of causing an error ([[temp.deduct#8]]). The rule was originally only meant to keep unrelated templates from getting in the way of overload resolution, but people later used it as a compile-time switch. Vandevoorde and Josuttis named it SFINAE (Substitution Failure Is Not An Error) in *C++ Templates* (2002).

In C++98, detecting whether a type has a `size_type` member meant measuring the return type of an overloaded call with `sizeof`. In C++20 you can just write a requires expression:

<div class="compare" markdown="1">

```cpp run ok std=c++98
template <class T> struct has_size_type {
  typedef char yes[1];
  typedef char no[2];
  template <class U> static yes&
    test(typename U::size_type*);
  template <class U> static no& test(...);
  static const bool value =
    sizeof(test<T>(0)) == sizeof(yes);
};
```

```cpp run ok
template <class T>
concept has_size_type =
  requires { typename T::size_type; };
```

</div>

On the left, `sizeof` does not evaluate the call expression; it only computes the size of the return type. When `U::size_type` is invalid, the first `test` is removed by SFINAE, leaving only the version returning `no&`, and the two outcomes are told apart by array size.

What packaged SFINAE into a general tool was `enable_if`: when the condition is false it has no `type` member, so a return type written with it fails substitution. Järvi, Willcock, Hinnant and Lumsdaine published the technique in 2003, Boost.enable_if shipped with Boost 1.31 in 2004, and C++11 added it to the standard library.

### The cost

In the 2000s, books and libraries such as *Modern C++ Design* (Alexandrescu, 2001) and Boost.MPL (2003) systematized these techniques. HOPL IV §4.5.2 likens that decade to the Wild West of metaprogramming: error messages were atrocious, compile times were long, and it was easy to exhaust the compiler's memory and recursion depth. Stroustrup mentions having seen a few hundred lines of metaprogramming code take minutes to compile, and a simple error lead to thousands of lines of diagnostics (HOPL IV §10.5.2).

The root cause was still the third goal from the first section: a template's requirements on its arguments were only written in its implementation, so the compiler could only report deep inside an instantiation that some expression was invalid.

## C++11 to C++17: the language takes over

HOPL IV §4.5.2 divides C++11's support for metaprogramming into two lines: on the language side, `constexpr` functions, variadic templates, alias templates and `decltype`; on the library side, `<type_traits>` and `enable_if`. The common direction was that compile-time computation should no longer have to go through the type system.

### Variadic templates replace type lists

C++98 had no way for a template to accept arbitrarily many types. Libraries such as Loki represented type sequences with nested `Typelist<Head, Tail>`, and every operation was a set of recursive specializations. C++11's variadic templates ([[N2242]], rules in [[temp.variadic]]) turned type sequences into parameter packs built into the language:

<div class="compare" markdown="1">

```cpp run ok std=c++98
struct NullType {};
template <class H, class T>
struct Typelist { typedef H Head; typedef T Tail; };

template <class TL> struct Length;
template <> struct Length<NullType> {
  enum { value = 0 };
};
template <class H, class T>
struct Length<Typelist<H, T> > {
  enum { value = 1 + Length<T>::value };
};

typedef Typelist<int,
        Typelist<char,
        Typelist<double, NullType> > > L;
int check[Length<L>::value == 3 ? 1 : -1];
```

```cpp run ok
template <class... T> struct list {};

template <class L> struct length;
template <class... T>
struct length<list<T...>> {
  static constexpr auto value =
      sizeof...(T);
};

using L = list<int, char, double>;
static_assert(length<L>::value == 3, "");
```

</div>

Computing the length on the left instantiates 4 `Length` specializations; on the right, only 1. According to HOPL IV §4.3.2, Stroustrup at first found the notation of variadic templates obscure and too reliant on recursion, and was later persuaded by Douglas Gregor's measurements: compared with the alternatives of the time, variadic templates sometimes made compilation 20 times faster.

In his 2015 article *Simple C++11 metaprogramming*, Peter Dimov further pointed out that any variadic class template can be used directly as a type list, and any alias template directly as a metafunction (the alias templates introduced by [[N2258]] did away with `typename ...::type`). Transforming each element takes a single pack expansion, with no recursion:

```cpp run ok std=c++17 title="transform.cpp"
#include <tuple>
#include <type_traits>

template <template <class...> class F, class L>
struct transform_impl;
template <template <class...> class F,
          template <class...> class L, class... T>
struct transform_impl<F, L<T...>> {
    using type = L<F<T>...>;                 // one pack expansion, no recursion
};
template <template <class...> class F, class L>
using transform = typename transform_impl<F, L>::type;

static_assert(std::is_same_v<
    transform<std::add_pointer_t, std::tuple<int, char>>,
    std::tuple<int*, char*>>);
```

These primitives later became Boost.Mp11. The standard library added aliases in the same direction: C++14's `_t` aliases such as `std::remove_cv_t`, and C++17's `_v` variable templates such as `std::is_same_v`.

### decltype makes SFINAE work on expressions

C++03 SFINAE worked mainly on types, such as `typename U::size_type`. Detecting whether `x.size()` could be called required a long detour, and whether an error in an expression counted as a substitution failure was not clearly specified.

With C++11's `decltype` ([[N2343]]) and trailing return types, you can write `auto f(T& x) -> decltype(x.size())` directly: if the expression is invalid, substitution fails. This is usually called expression SFINAE. HOPL IV §4.5.1 notes that the SFINAE rules became more general in C++11, at the cost of compilers having to be able to cleanly back out of a failed substitution.

### void_t and the detection idiom

Each property to be detected still needed its own set of overloads. In [[N3911]], Walter Brown proposed adding an alias template that seems to do nothing, `template <class...> using void_t = void;`, which, combined with partial specialization, expresses one detection with one specialization:

```cpp run ok std=c++17 title="void_t.cpp"
#include <type_traits>
#include <utility>

template <class, class = void>
struct has_begin : std::false_type {};                    // default: doesn't have it

template <class T>
struct has_begin<T, std::void_t<decltype(std::declval<T&>().begin())>>
    : std::true_type {};                                  // matches when the expression is well-formed

struct Range { int* begin(); };
static_assert(has_begin<Range>::value);
static_assert(!has_begin<int>::value);

int main() {}
```

When the expression is well-formed, `void_t<...>` is just `void`, matching the primary template's default argument, and the partial specialization is selected; when it is ill-formed, substitution fails and the partial specialization is discarded.

There is a subtlety in the rules here: whether unused arguments of an alias template take part in substitution was not clearly specified in C++11, and only [[CWG1558]] made clear that they must. So on some early compilers `void_t` had to be written differently to work. `void_t` went into C++17; `is_detected`, Brown's generalization of it in [[N4502]], only went into Library Fundamentals TS v2, because C++20 requires expressions offer a more direct way to write it.

### static if rejected, if constexpr accepted

In C++11, choosing between two implementations by type meant writing two `enable_if` overloads with mutually exclusive conditions. C++17's `if constexpr` ([[P0292R2]], rules in [[stmt.if]]) brought the dispatch back into the function body:

<div class="compare" markdown="1">

```cpp run ok std=c++11
#include <string>
#include <type_traits>

template <class T>
typename std::enable_if<
  std::is_arithmetic<T>::value,
  std::string>::type
describe(const T& x) {
  return std::to_string(x);
}
template <class T>
typename std::enable_if<
  !std::is_arithmetic<T>::value,
  std::string>::type
describe(const T& x) {
  return std::string(x);
}
```

```cpp run ok
#include <string>
#include <type_traits>

template <class T>
std::string describe(const T& x) {
  if constexpr (std::is_arithmetic_v<T>)
    return std::to_string(x);
  else
    return std::string(x);
}
```

</div>

`if constexpr` took a detour. In 2012 Sutter, Bright and Alexandrescu proposed in [[N3329]] introducing a `static if` modeled on D. It could appear at namespace and class scope and control whether a declaration exists:

```cpp title="static-if-sketch.cpp"
// a sketch following the idea of N3329; not valid C++
template <class T>
struct Holder {
    static if (std::is_integral<T>::value) {
        long value;       // whether the member exists depends on the condition
    } else {
        double value;
    }
};
```

Stroustrup, Dos Reis and Sutton opposed it in [[N3613]]. Their technical reasons: if whether a declaration exists depends on arbitrary compile-time conditions, code becomes hard to analyze; and it conflicted with concepts, then being designed. When Ville Voutilainen proposed it again in 2015, the scope was narrowed to statements inside function bodies, and it became `if constexpr`.

The trace this trade-off left: today, choosing a member's type by condition still uses `std::conditional_t`, enabling a member function by condition uses a C++20 requires clause, and C++ still has no syntax for adding or removing declarations, such as data members, by condition.

Fold expressions ([[expr.prim.fold]]), also added in C++17, removed another kind of recursion: `(xs + ... + 0)` sums a whole pack in one line, with no need for a recursive primary template plus a terminating overload.

## C++20: requirements in the interface

### Concepts

The history of concepts has its own page ([[history/concepts]]). For metaprogramming, concepts replaced most uses of `enable_if` and the detection idiom: constraints are written on the declaration, and when they are not satisfied the compiler can point out which requirement failed.

```cpp run ok std=c++20 title="concepts.cpp"
#include <cstddef>
#include <concepts>

template <class T>
concept Sized = requires(const T& x) {
    { x.size() } -> std::convertible_to<std::size_t>;
};

template <Sized T>                       // the constraint is on the interface, not hidden in the return type
std::size_t count(const T& x) { return x.size(); }

struct Box { std::size_t size() const { return 3; } };

int main() { return count(Box{}) == 3 ? 0 : 1; }
```

For a call `count(42)`, Clang 23 explains in turn: the candidate was ignored because its constraints were not satisfied; `int` does not satisfy `Sized`; `x.size()` is invalid because `const int` is not a class type. The rules for constraints are in [[temp.constr]].

### consteval and class-type template arguments

C++20 also has two changes closely related to metaprogramming:

- Every call to a `consteval` function ([[P1073R3]]) must be evaluated at compile time. P1073R3 says its direct impetus was reflection: reflection queries only make sense at compile time.
- Class types can be non-type template parameters ([[P0732R2]], later changed to the structural-type model by [[P1907R1]]). Before that, to use a string as a template argument, you had to break it into a variadic pack of characters.

```cpp run ok std=c++20 title="nttp.cpp"
#include <algorithm>
#include <cstddef>

template <std::size_t N>
struct fixed_string {
    char data[N]{};
    consteval fixed_string(const char (&s)[N]) { std::copy_n(s, N, data); }
};

template <fixed_string Name>                     // a template parameter of class type
struct field { static constexpr const char* name = Name.data; };

int main() {
    using id = field<"id">;
    return id::name[0] == 'i' ? 0 : 1;
}
```

[[P0784R7]] allowed `new` and `delete` in constant evaluation, so `std::vector` and `std::string` can be used at compile time (as long as the memory is freed before constant evaluation ends). This was a prerequisite for the later value-based reflection, for reasons explained in the next section.

## Reflection: from types to values

### Questions template metaprogramming couldn't answer

Templates can compute types, but cannot answer which members a class has or which enumerators an enumeration has. In 2013 WG21 formed SG7, the reflection study group. According to HOPL IV §9.6.2, everyone agreed at the time that what C++ needed was static reflection: traversing resident data structures at run time means large amounts of data, complex representations and run-time overhead.

### The first design: reflection results are types

The first design to take shape was by Matúš Chochlík and others ([[P0194R6]]), which became the basis of the Reflection TS (working draft [[N4766]], published in 2021 as ISO/IEC TS 23619). `reflexpr(X)` produces a meta-object type, and queries are done with traits-style templates. This is the same style as the metaprogramming of the previous sections.

From 2017, discussion in SG7 shifted towards a value-based design. In [[P0425R0]], Louis Dionne summarized that classic template metaprogramming is hard to use and does not scale; a better direction was `constexpr`-based metaprogramming plus value-based reflection, the first step being support for variable-size containers in constant expressions (later P0784). In [[P0598R0]], Vandevoorde proposed that reflection work through values rather than types, and [[P1240R0]] in 2018 gave a complete design: every reflection result is a value of a single type, `std::meta::info`, queried with `consteval` functions.

HOPL IV §9.6.2 lists the reasons for this shift: analyzing and generating code is essentially functional; `constexpr` computation had become strong enough to carry metaprogramming; and the data structures a compiler builds internally for functions are much smaller and much shorter-lived than those it builds for types, so less memory is used and compilation is faster. The third point targets exactly the kind of cost seen in the C++98 section, where `fact<5>` produces 6 classes.

Here is how the two designs get the name of the first enumerator of the same enumeration. Clang 23 supports neither, so neither has been compiled:

<div class="compare" markdown="1">

```cpp
// Reflection TS (N4766): results are types
namespace r = std::experimental::reflect;
using Es = r::get_enumerators_t<
    reflexpr(Color)>;
using E0 = r::get_element_t<0, Es>;
constexpr auto name = r::get_name_v<E0>;
```

```cpp
// C++26 (P2996): results are values
constexpr auto name =
  std::meta::identifier_of(
    std::meta::enumerators_of(
      ^^Color)[0]);
```

</div>

On the right, `enumerators_of` returns `std::vector<std::meta::info>`, and `[0]` is an ordinary subscript. On the left, every step instantiates a template.

The notation changed several times too. P1240R0 used the keyword `reflexpr`; [[P2320R0]] in 2021 switched to a unary `^` for reflection and `[: :]` to splice a reflection value back into code, one reason being that the notation should be as short as the `&` for taking an address; [[P3381R0]] in 2024 changed `^` to the new token `^^`, because `^` conflicted in parsing with the blocks extension Clang uses in Objective-C++.

### Static reflection in C++26

[[P2996R13]] *Reflection for C++26* is a subset of P1240's functionality; the paper says it starts with a smaller scope, with more powerful features to be added later. It went into C++26 together with papers such as expansion statements, `template for` ([[P1306R5]]), annotations, and `define_static_array` ([[P3491R3]]).

Below is the enum-to-string example from P2996, slightly rewritten. Clang 23 has no `<meta>` header, so this code has not been compiled and has no verdict; GCC 16.1 can be used to try it with `-std=c++26 -freflection` (GCC 16.1 release notes).

```cpp title="enum-to-string.cpp"
#include <meta>
#include <string_view>
#include <type_traits>

template <class E>
    requires std::is_enum_v<E>
constexpr std::string_view enum_to_string(E value) {
    template for (constexpr std::meta::info e :
                  std::define_static_array(std::meta::enumerators_of(^^E))) {
        if (value == [:e:])                       // splice the reflection value back into an expression
            return std::meta::identifier_of(e);
    }
    return "<unnamed>";
}

enum class Color { red, green, blue };
static_assert(enum_to_string(Color::green) == "green");
```

Every piece corresponds to a part of the history above: `^^E` is a value, not a type; `enumerators_of` is a `consteval` function returning a compile-time `std::vector`; a `std::vector` cannot cross the boundary of constant evaluation into run time, so `define_static_array` turns it into a static array; `template for` instantiates the loop body with a different constant for each iteration, replacing the old recursive templates or `index_sequence` plus fold expressions. The rules are in [[expr.reflect]], [[stmt.expand]] and [[meta.reflection]].

## Traces in today's rules

### The typename and template disambiguators

Names in a template definition are looked up in two phases: names that don't depend on template parameters are bound at the point of definition, and dependent names are deferred to instantiation ([[temp.res]]; topic page [[topics/two-phase-lookup]]). This requires the compiler to be able to parse the definition when it sees it, so programmers must mark dependent names as types or templates:

```cpp run ok title="keywords.cpp"
template <class T>
struct Holder {
    using value_type = typename T::value_type;   // a dependent name is not a type by default; write typename
};

template <class Tuple>
int first(Tuple& t) {
    return t.template get<0>();                   // < after a dependent name is less-than by default; write template
}

struct P { template <int I> int get() { return I + 1; } };

int main() { P p; return first(p) == 1 ? 0 : 1; }
```

Remove the `template` in `first`, and Clang 23 reports a missing `template` keyword. C++20's [[P0634R3]] made `typename` optional in several contexts where only a type is possible, but the `template` disambiguator is still required.

### Two-phase lookup

The consequences of two-phase lookup are often surprising: a non-dependent overload declared after the template definition is not visible to the template.

```cpp run ok title="two-phase.cpp"
void g(double) {}

template <class T>
void f(T) {
    g(1);          // non-dependent call: looked up at the definition, only g(double) is visible
}

void g(int) {}     // this better match comes too late

int main() { f(0); }   // calls g(double)
```

Not all compilers implemented this model for a long time. MSVC used to record template bodies as token sequences and only parse them at instantiation, and only began supporting two-phase lookup under `/permissive-` in Visual Studio 2017 15.3 (Andrew Pardoe, *Two-phase name lookup support comes to MSVC*, Microsoft C++ Team Blog, 2017). So old code may behave differently on different compilers.

### Friend injection and stateful metaprogramming

Template metaprogramming should in principle be purely functional: evaluate the same expression twice, and you should get the same result. In 2015 Filip Roséen showed a way to break this. A friend function defined in a class template only counts as defined once the class is instantiated, and whether a function has been defined can be observed at compile time:

```cpp title="friend-injection.cpp"
template <int N>
struct flag {
    friend constexpr auto adl(flag<N>);                  // declaration only; return type to be deduced
};

template <int N>
struct setter {
    friend constexpr auto adl(flag<N>) { return true; }  // defined only when setter<N> is instantiated
};

template <int N = 0, auto = [] {}>
consteval int next() {
    if constexpr (requires { adl(flag<N>{}); })          // before the definition the return type can't be deduced, so the expression is ill-formed
        return next<N + 1>();
    else
        return (void)setter<N>{}, N;
}

static_assert(next() == 0);
static_assert(next() == 1);   // a textually identical expression, a different result
static_assert(next() == 2);
```

Clang 23 accepts this code. [[CWG2118]] *Stateful metaprogramming via friend injection* takes the view that this technique should be ill-formed, and CWG agrees with that direction, but has not settled on wording to prohibit it. As of the last update of this page the issue is still unresolved, so the code has no verdict: the standard does not explicitly forbid it, and code relying on it may stop working at any time.

C++26 reflection handles compile-time side effects differently. Calls that produce injected declarations, such as `define_aggregate`, are only allowed in consteval blocks; which declarations a query can see is determined by specified evaluation contexts, not by the timing of instantiation ([[expr.const.reflect]]).

### Implementation limits

Annex [[implimits]] recommends supporting at least 1024 levels of recursively nested template instantiation and at least 512 levels of recursive `constexpr` function calls. These are only recommended minimums; a deeply recursive metaprogram passing on one compiler and failing on another is conforming. [[temp.inst]] also says the result of infinitely recursive instantiation is undefined. One reason designs since C++11 generally use pack expansion, fold expressions and `template for` instead of recursion is that their instantiation depth is constant.

## Old techniques and today's replacements

| Purpose | C++98 technique | Today's way |
|---|---|---|
| Computing a value | Recursive specializations, result in an `enum` | `constexpr` / `consteval` functions (C++11/14/20) |
| Compile-time assertions | Arrays whose length may be negative | `static_assert` (C++11) |
| Type sequences | Nested `Typelist` plus recursion | Parameter packs, pack expansion, pack indexing (C++11/26) |
| Choosing an implementation by condition | Pairs of `enable_if` overloads | `if constexpr` (C++17), concepts (C++20) |
| Detecting properties of types | `sizeof` plus overloads | `void_t` (C++17), requires expressions (C++20) |
| Reductions such as summing a pack | Recursive primary template plus terminating overload | Fold expressions (C++17) |
| Using a string as a template argument | A variadic pack of characters | Non-type template parameters of class type (C++20) |
| Listing members, enumerators | Impossible | Static reflection (C++26) |

HOPL IV §10.5.2's view is that when you need a value, a function is the best way to compute it, even at compile time; traditional template metaprogramming is best left to computing new types.

## Work still in progress

C++26 reflection is mainly for reading program structure, and what it can generate is limited, for example completing a class's definition with `define_aggregate`. More general code generation is still at the proposal stage, for example [[P3294R2]], which describes code to be injected with token sequences. [[P2758R5]] proposes letting compile-time code emit custom diagnostics, which ties back to the story at the start of this page: in 1994 Unruh could only output his computation's results through error messages. At the time of writing, none of these proposals has been adopted.

## References

- Bjarne Stroustrup, *Evolving a language in and for the real world: C++ 1991–2006*, HOPL III, 2007 (§4.1.5 traits, §7.2.2 template metaprogramming).
- Bjarne Stroustrup, *Thriving in a Crowded and Changing World: C++ 2006–2020*, HOPL IV, 2020 (§4.3.2 variadic templates, §4.5 SFINAE and metaprogramming, §6.1 design goals of templates, §9.6.2 static reflection, §10.5.2 metaprogramming).
- Erwin Unruh, *Primzahlen* personal web page (erwin-unruh.de), including the original 1994 program; committee document N462 (1994).
- Todd Veldhuizen, *Using C++ Template Metaprograms*, C++ Report, 1995; *C++ Templates are Turing Complete*, 2003.
- Nathan C. Myers, *Traits: a new and useful template technique*, C++ Report, 1995.
- Daveed Vandevoorde, Nicolai M. Josuttis, *C++ Templates: The Complete Guide*, 2002.
- Peter Dimov, *Simple C++11 metaprogramming*, 2015 (included in the Boost.Mp11 documentation).
- Andrew Pardoe, *Two-phase name lookup support comes to MSVC*, Microsoft C++ Team Blog, 2017.
- GCC 16.1 release notes, 2026.
- Core language issues: [[CWG903]], [[CWG1558]], [[CWG2118]].
