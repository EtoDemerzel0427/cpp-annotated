---
title: "Namespace use: what may go into std"
summary: "Adding declarations to namespace std is UB, except for class template specializations that depend on program-defined types (hash, tuple_size, formatter…) and a few explicitly allowed variable template specializations; function templates and member functions can't be specialized, and deduction guides can't be written; except for addressable functions, taking the address of a standard library function is unspecified; posix and std followed by digits are reserved namespaces too."
updated: 2026-10-19
---

!!! tldr
    - Adding declarations or definitions to `std` or any namespace nested in it is undefined behavior, unless the standard says otherwise.
    - The main exception: you may write specializations of standard class templates (`std::hash`, `std::formatter`, `std::tuple_size`…), provided the specialization depends on a type you defined and meets the requirements of the original template.
    - You can't specialize standard library function templates (since C++20, `std::swap` included), member functions or most variable templates, nor write deduction guides for standard class templates. To customize `swap`, write an overload in your own namespace.
    - Except for a few addressable functions (`std::endl`, `std::hex` and so on), the behavior of taking the address of a standard library function is unspecified, and it may fail to compile. When you need a function object, wrap the call in a lambda.
    - Namespaces such as `posix`, `std2` and `std26` are also reserved for the standard.

## The general rule: don't add things to std ([namespace.std] ¶1)

```cpp ub
#include <ostream>
#include <vector>
namespace std {
  // UB: adds an operator<< for std::vector inside std
  template<class T>
  ostream& operator<<(ostream& os, const vector<T>& v) {
    for (const auto& x : v) os << x << ' ';
    return os;
  }
}
int main() {}
```

!!! std
    Unless otherwise specified, the behavior of a C++ program is undefined if it adds declarations or definitions to namespace `std` or to a namespace within namespace `std`.

¶1 Unless otherwise specified, a program that adds declarations or definitions to namespace `std` or to a namespace within `std` has undefined behavior. This applies equally to nested namespaces such as `std::ranges`, `std::chrono`, `std::pmr` and `std::meta`.

The rule is this strict so that standard library implementations can evolve freely. An implementation may add overloads to functions ([[global.functions]], [[member.functions]]), turn functions into function objects, and put the whole library in an inline namespace `std::__1`. Once users add declarations to `std`, they are tied to these implementation details: they may clash with internal entities of the same name, may silently change the result of overload resolution after an upgrade, and two libraries each adding their own copy would violate the ODR.

It is UB rather than ill-formed because the compiler can't tell which declarations come from standard library headers and which are written by users; both are ordinary C++ code.

The motivation for the example above is usually to make ADL find the operator. The only associated namespace of `std::vector<int>` is `std`, so an `operator<<` defined in the global namespace isn't found inside templates such as `std::ostream_iterator`. The right approach is to write a named function, wrap the vector in your own type, or use C++23's `std::print` / `std::format`, which support ranges directly.

## Allowed: specializing class templates for your own types (¶2)

¶2 Unless explicitly prohibited, a program may add a specialization of any standard library class template to `std`, provided that:

- ¶2.1 the declaration depends on at least one program-defined type; and
- ¶2.2 the specialization meets the standard library requirements for the original template.

Footnote 140 explains what this means for implementations: library code that instantiates other library templates must work correctly with any user specialization that meets the minimum requirements.

### What a program-defined type is

A **program-defined type** ([[g:program-defined-type]]) is a class type or enumeration type that is not part of the standard library and not defined by the implementation, as well as a closure type of a lambda in the program, or an instantiation of a program-defined specialization. "Depends on" doesn't require the outermost type to be a user type; appearing in a template argument is enough:

| Specialization | Program-defined type depended on | Allowed? |
|---|---|---|
| `std::hash<app::Id>` | `app::Id` | Allowed |
| `std::hash<app::Box<T>>` (partial specialization) | `app::Box<T>` | Allowed |
| `std::hash<std::vector<app::Id>>` | `app::Id` | Allowed |
| `std::hash<std::pair<int, int>>` | None | UB |

¶2.2 is just as binding. For example, a specialization of `std::hash` must meet *Cpp17Hash* ([[hash.requirements]]) and the requirements of [[unord.hash]]: default constructible, copyable, `operator()` returning `size_t`, and so on.

### Common customization points

```cpp run ok
#include <cstddef>
#include <format>
#include <functional>
#include <tuple>
#include <unordered_set>
#include <utility>

namespace app {
  struct Id {
    int v;
    bool operator==(const Id&) const = default;
  };
  struct Pair {
    int a; double b;
    template<std::size_t I> auto get() const {
      if constexpr (I == 0) return a; else return b;
    }
  };
}

template<> struct std::hash<app::Id> {
  std::size_t operator()(app::Id i) const noexcept {
    return std::hash<int>{}(i.v);
  }
};
// the tuple protocol for structured bindings
template<> struct std::tuple_size<app::Pair>
  : std::integral_constant<std::size_t, 2> {};
template<> struct std::tuple_element<0, app::Pair> { using type = int; };
template<> struct std::tuple_element<1, app::Pair> { using type = double; };
// customizing std::format
template<> struct std::formatter<app::Id> : std::formatter<int> {
  auto format(app::Id i, std::format_context& ctx) const {
    return std::formatter<int>::format(i.v, ctx);
  }
};

int main() {
  std::unordered_set<app::Id> s{{1}, {2}};
  auto [a, b] = app::Pair{1, 2.5};
  return s.size() == 2 && a == 1 && b == 2.5
      && std::format("{}", app::Id{42}) == "42" ? 0 : 1;
}
```

The form `template<> struct std::hash<app::Id>` declares the specialization directly with a qualified name ([[temp.expl.spec]]), without opening `namespace std { }`, so nothing else can slip in along with it.

Other class templates designed for users to specialize include `std::coroutine_traits`, `std::common_type`, `std::basic_common_reference`, `std::iterator_traits`, `std::numeric_limits`, `std::uses_allocator`, `std::is_error_code_enum`, `std::is_error_condition_enum`, `std::pointer_traits` and others.

### Class templates that explicitly prohibit specialization

The "unless explicitly prohibited" at the start of ¶2 isn't an empty phrase; quite a few class templates explicitly prohibit user specializations:

| Template | Source | Consequence |
|---|---|---|
| The type traits in [[type.traits]] (`is_integral`, `remove_cv`…) | [[meta.rqmts#4]] | UB, unless otherwise specified |
| `std::initializer_list` | [[support.initlist#2]] | Ill-formed |
| `std::allocator_traits` | [[allocator.requirements.general#3]], Note 1 | There are no user specializations |
| `range_adaptor_closure`, `generator`, `is_execution_policy`, `basic_format_arg`, `chrono::is_clock` | Their respective subclauses | UB |

The reason for prohibiting specializations of type traits is straightforward. Traits such as `is_trivially_copyable` correspond to language rules that users can't declare themselves; if `is_integral<MyInt>` could be specialized to `true`, library code relying on it would perform operations on `MyInt` that are valid only for integers.

libc++ has started diagnosing this kind of UB: it adds the `[[clang::no_specializations]]` attribute to type traits. The standard says UB, and an implementation refusing to compile is within what that allows.

```cpp error
#include <type_traits>
struct S {};
template<> struct std::is_integral<S> : std::true_type {};
// Clang 23 + libc++: error: 'is_integral' cannot be specialized:
//   Users are not allowed to specialize this standard library entity
int main() {}
```

## Variable templates: only explicitly allowed ones may be specialized (¶3)

¶3 The behavior of a program that declares an explicit or partial specialization of any standard library variable template is undefined, unless the specification of that variable template explicitly allows it. Note 1 explains that variable templates that allow specialization each specify the requirements on such specializations.

The variable templates that explicitly allow specialization are all switch-style customization points:

| Variable template | Purpose |
|---|---|
| `std::ranges::enable_borrowed_range<R>` | Declares that `R`'s iterators don't depend on the lifetime of the `R` object |
| `std::ranges::enable_view<V>` | Declares that `V` is a view |
| `std::ranges::disable_sized_range<R>` | Keeps `ranges::size` from using `R`'s `size()` |
| `std::disable_sized_sentinel_for<S, I>` | Declares that `S - I` isn't constant time |
| `std::format_kind<R>` | Specifies how a range is formatted (sequence, set, map…) |
| `std::enable_nonlocking_formatter_optimization<T>` | Allows `std::print` to use the non-locking optimization for `T` |

```cpp run ok
#include <ranges>
struct MyView : std::ranges::view_base {
  int* begin() const;
  int* end() const;
};
template<>
inline constexpr bool std::ranges::enable_borrowed_range<MyView> = true;   // explicitly allowed
int main() {}
```

The `_v` versions of traits such as `std::is_integral_v` and `std::tuple_size_v` can't be specialized. They are defined as the `::value` of the corresponding class template, and specializing the `_v` would make the two disagree.

## Function templates can't be specialized

<div class="compare" markdown="1">

```cpp ub
#include <utility>
namespace app { struct S {}; }
// UB since C++20: specializes a function template
template<>
void std::swap(app::S&, app::S&)
    noexcept {}
int main() {}
```

```cpp run ok
#include <utility>
namespace app {
  struct S { int v; };
  void swap(S& a, S& b) noexcept {
    std::swap(a.v, b.v);
  }
}
int main() {
  app::S a{1}, b{2};
  using std::swap;
  swap(a, b);   // ADL finds app::swap
  return a.v == 2 ? 0 : 1;
}
```

</div>

¶2 only allows specializing **class templates**. Specializing a function template (such as `std::swap`) adds a declaration to `std` and falls under the UB of ¶1. Clang 23 compiles the code on the left without any warning.

C++17 and earlier allowed specializing function templates like this; C++20 withdrew the permission through [[P0551R3]]. Function template specializations were never very useful: they don't take part in overload resolution and are considered only after the primary template has been selected; and for a class template `app::Box<T>` there is no partial specialization of a function template, only an overload, and overloads were never allowed in `std`.

The right way to customize is to provide an overload in the type's own namespace, as on the right, and have callers use the two-step (`using std::swap; swap(a, b);`) or `std::ranges::swap` so that ADL finds it ([[swappable.requirements]]).

## Members and deduction guides (¶4)

```cpp ub
#include <vector>
struct S {};
// UB: even though it depends on the program-defined type S
template<> constexpr void std::vector<S>::push_back(const S&) {}
int main() {}
```

¶4 The behavior of a program is undefined if it declares any of the following:

- ¶4.1 an explicit specialization of any member function of a standard library class template;
- ¶4.2 an explicit specialization of any member function template of a standard library class or class template;
- ¶4.3 an explicit or partial specialization of any member class template of a standard library class or class template;
- ¶4.4 a deduction guide for any standard library class template.

In principle you could specialize all of `std::vector<S>` under ¶2 (meeting all the requirements of `vector`), but not just one of its members. How many overloads a member function has and what their signatures are is up to the implementation ([[member.functions]]); the `push_back(const T&)` written in the standard isn't necessarily a separate function in the implementation.

libc++ rejects violations of ¶4.4 outright. `namespace std { vector(const char*) -> vector<string>; }` gives "deduction guide must be declared in the same scope as template 'std::vector'", because the real `vector` is in `std::__1` and a deduction guide must be in the same scope as its template ([[temp.deduct.guide]]).

## Explicit instantiation (¶5)

```cpp
#include <vector>
struct S {};
template class std::vector<S>;     // OK: depends on the program-defined type S
template class std::vector<int>;   // UB: doesn't depend on a program-defined type
```

¶5 A program may explicitly instantiate a class template defined in the standard library, under the same conditions as specialization: the declaration depends on the name of at least one program-defined type (¶5.1), and the instantiation meets the requirements of the original template (¶5.2).

`std::vector<int>` isn't allowed because the implementation may already provide that instantiation in the library binary. libstdc++ does exactly this for `basic_string<char>` and others, declaring them with `extern template` in the headers. A second instantiation by the user could violate the rule in [[temp.explicit]] that a specialization has at most one explicit instantiation definition.

Explicitly instantiating a whole class template instantiates all its member functions, including those that would otherwise never be used with `S`. ¶5.2 requires `S` to meet the requirements that allow all those members to be instantiated.

## Don't take the address of standard library functions (¶6)

```cpp error
#include <algorithm>
#include <cctype>
#include <locale>
#include <string>
int main() {
  std::string s = "abc";
  std::transform(s.begin(), s.end(), s.begin(), std::toupper);
  // error: no matching function for call to 'transform'
}
```

`int toupper(int)` from `<cctype>` and `template<class charT> charT toupper(charT, const locale&)` from `<locale>` form an overload set, so `transform`'s template argument can't be deduced. If only `<cctype>` is included, this code happens to compile, but the standard doesn't guarantee that either.

¶6 Let *F* denote a standard library function ([[global.functions]]), a standard library static member function, or an instantiation of a standard library function template. Unless *F* is designated an **addressable function** ([[g:addressable-function]]), the behavior of a program that explicitly or implicitly attempts to form a pointer to *F* is **unspecified (possibly ill-formed)**. Note 2 lists the means of forming a pointer: unary `&`, `std::addressof`, and the function-to-pointer conversion ([[conv.func]]). The same applies to forming a reference to *F* or a pointer to member designating a non-static standard library member function.

"Unspecified (possibly ill-formed)" is an unusual combination: the implementation may accept it and give a usable pointer, or it may refuse to compile. It isn't UB; the worst outcome is a compile error, never silent misbehavior. This rule took effect in C++20 ([[P0551R3]]), for the same reason as ¶1, to preserve these freedoms for implementations:

- adding overloads to functions and default arguments to member functions ([[global.functions#2]], [[member.functions#2]]), which would make `&std::f` ambiguous;
- adding `noexcept` to functions ([[res.on.exception.handling#5]]), which changes the type of the function pointer;
- implementing functions as function objects.

The portable way is to wrap it in a lambda, which also handles the possibility of `char` being negative:

```cpp run ok
#include <algorithm>
#include <cctype>
#include <string>
int main() {
  std::string s = "abc";
  std::ranges::transform(s, s.begin(), [](unsigned char c) {
    return static_cast<char>(std::toupper(c));
  });
  return s == "ABC" ? 0 : 1;
}
```

Equally non-portable are `std::function<double(double)> f = std::sqrt;`, `&std::vector<int>::push_back` and `std::bind(&std::string::size, _1)`. The fix is always a lambda.

### Addressable functions

Functions designated addressable can safely have their address taken. The current draft has two groups:

- iostream manipulators: the `ios_base` manipulators such as `boolalpha`, `hex` and `fixed` ([[std.ios.manip]]), and `endl`, `ends`, `flush`, `ws` and others ([[ostream.manip]], [[istream.manip]]). They are meant to be passed to `operator<<` as function pointers in the first place.
- {{c++26}} The functions in the reflection header `<meta>`, unless otherwise specified ([[meta.reflection]]).

```cpp run ok
#include <iostream>
#include <ostream>
int main() {
  std::ostream& (*pe)(std::ostream&) = std::endl;    // OK: addressable function
  std::ios_base& (*ph)(std::ios_base&) = &std::hex;  // OK: addressable function
  std::cout << ph << 255 << pe;                      // prints ff
}
```

## Reflecting standard library entities (¶7, ¶8){{c++26}}

C++26 static reflection ([[P2996R13]]) can enumerate and name entities in the standard library, exposing even more implementation detail than taking addresses. ¶7 and ¶8 extend the reasoning about taking addresses to reflection.

¶7 Let *F* denote a standard library function or function template. Unless *F* is an addressable function, it is unspecified whether and how a reflection value designating it can be formed. Whether the parameters of *F* have names (the result of `has_identifier`), and what those names are, are also unspecified. Parameter names in implementations are usually reserved identifiers such as `__x` and `_Tp`, and they change between versions. Note 3 adds that `std::meta::members_of` might not return standard library functions that the implementation handles through mechanisms outside the language.

¶8 For a standard library class, it is unspecified whether reflection values of its private members can be formed and what those members are named. [[objects.within.classes]] says the internal representation of library classes is unspecified, and ¶8 extends this to reflection.

## std can't be an inline namespace (¶9)

```cpp error
inline namespace std {}   // error: cannot declare the namespace 'std' to be inline
int main() {}
```

¶9 A translation unit shall not declare namespace `std` to be an inline namespace ([[namespace.def]]). This rule isn't marked "no diagnostic required", so a violation is ill-formed and the compiler must report it. If `std` could be an inline namespace of the global namespace, all its names would be visible globally and clash wholesale with the global names of the C library and with users' names.

## Namespace posix [namespace.posix]

¶1 The behavior of a program that adds declarations or definitions to namespace `posix` or a namespace within it is undefined, unless otherwise specified. `posix` is reserved for a future C++ binding of the POSIX standard (ISO/IEC/IEEE 9945). Your own POSIX wrappers should use a different name.

## Namespaces reserved for the future [namespace.future]

¶1 Top-level namespaces whose names start with `std` followed by one or more digits are reserved for future standardization; adding declarations or definitions to them is UB. Example 1 mentions that `std2` is reserved for future revisions of this standard.

| Namespace | Reserved? |
|---|---|
| `std2`, `std26`, `std0` | Reserved |
| `stdx`, `std_2`, `stdlib` | Not reserved: not std followed by digits |
| `app::std2` | Not reserved: not top-level |

## Common misconceptions

!!! pitfall "Specializing `std::hash<std::pair<int, int>>`"
    This specialization doesn't depend on a program-defined type, so it is UB. Write your own hash function object instead and pass it as a template argument to the unordered container: `std::unordered_map<std::pair<int, int>, V, PairHash>`.

!!! pitfall "Adding a helper function inside `namespace std { }` while you're there"
    `namespace std { template<> struct hash<app::Id> { ... }; }` is valid, just not recommended. But if you also define a `hash_combine` helper in the same block, that function is the UB of ¶1. Writing `template<> struct std::hash<app::Id>` avoids this.

## Questions

!!! question "Question 1"
    Is the following specialization valid?
    ```cpp
    namespace app { enum class Color { red, green }; }
    template<> struct std::hash<std::optional<app::Color>> { /* meets Cpp17Hash */ };
    ```

<details markdown="1">
<summary>Answer</summary>

It meets ¶2.1: the declaration depends on the program-defined type `app::Color`, and enumerations count. The standard already provides a partial specialization of `hash` for `std::optional<T>` ([[optional.hash]]); the user's explicit specialization is more specialized and will be selected, which is fine as far as the language goes. As long as it meets the requirements of ¶2.2, it is valid.

There is also a language-level trap: an explicit specialization must appear before the first use that would cause an implicit instantiation, otherwise the program is ill-formed, no diagnostic required ([[temp.expl.spec]]). If some translation unit uses `std::hash<std::optional<app::Color>>` first, it gets the standard's partial specialization. So such a specialization should immediately follow the definition of `app::Color`, in the same header.
</details>

!!! question "Question 2"
    What is the behavior of `auto f = &std::move<int&>;`? And of `auto g = &std::meta::is_class_type;`?

<details markdown="1">
<summary>Answer</summary>

`std::move<int&>` is an instantiation of a standard library function template and isn't an addressable function, so forming a pointer to it is unspecified (possibly ill-formed). In practice it usually compiles, but the standard doesn't guarantee it.

`std::meta::is_class_type` is a function in `<meta>`, which by [[meta.reflection]] ¶1 is an addressable function, so taking its address is allowed. However, it is a `consteval` function, and taking its address can only appear in an immediate function context ([[expr.const]]); that is a separate constraint at the language level.
</details>
