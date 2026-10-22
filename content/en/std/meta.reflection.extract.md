---
title: Value extraction and code generation
summary: "Converting between reflections and ordinary values (extract, reflect_constant, reflect_object, reflect_function), getting new specializations by using reflections as template arguments (substitute), and generating a definition for an incomplete class during constant evaluation (define_aggregate)."
updated: 2026-10-19
---

!!! tldr
    - `extract<T>(r)` turns a reflection back into a value of type `T`. It does almost no conversion: the value's type must be the same as `T`, references may only add `const`, and otherwise `meta::exception` is thrown.
    - The result of `reflect_constant(v)` is exactly what you would get by using `v` as a constant template argument, so `v` must be of a structural type and is subject to all the restrictions on template arguments.
    - `substitute(^^Z, {args...})` uses reflections as template arguments to get the reflection of `Z<args...>`, which turns an ordinary parameter of a `consteval` function into a template argument.
    - `can_substitute` only checks for errors in the immediate context; errors that only show up when a function body is instantiated still make the program ill-formed.
    - `define_aggregate` generates a definition for a class that has never been complete; the members can only be public non-static data members and unnamed bit-fields.

!!! note "About the examples on this page"
    Clang 23 does not support C++26 reflection yet. The code on this page is written from the current draft and the standard's own examples, has not been compiled, and therefore carries no verdict. Most examples omit `#include <meta>` and `using namespace std::meta;`.

The functions in [[meta.reflection.queries]] read the program; the functions on this page convert between reflections and ordinary C++ values, and can also generate new program constructs:

| Direction | Functions | Subclause |
|---|---|---|
| Reflection → value | `extract<T>(r)` | [meta.reflection.extract] |
| Value → reflection | `reflect_constant`, `reflect_object`, `reflect_function` | [meta.reflection.result] |
| Reflections → reflection of a template specialization | `can_substitute`, `substitute` | [meta.reflection.substitute] |
| Reflections → class definition | `data_member_spec`, `define_aggregate` | [meta.reflection.define.aggregate] |

## Getting values from reflections: `extract` [meta.reflection.extract]

```cpp
constexpr int k = 42;
static_assert(extract<int>(^^k) == 42);                // types match
// extract<long>(^^k);                                 // throws meta::exception: int is not long
constexpr const int& rk = extract<const int&>(^^k);    // reference: adding const is allowed

struct S { int m; int f(int); };
constexpr auto pm = extract<int S::*>(^^S::m);          // member pointer
constexpr auto pf = extract<int (S::*)(int)>(^^S::f);  // member function pointer
```

A splice `[: r :]` ([[basic.splice]]) can also turn a reflection back into an expression, but `r` must be a constant expression. `extract` is an ordinary `consteval` function that can be applied to any `info` value during constant evaluation, such as a loop variable or an element of a `vector<info>`; the price is that the caller has to know the type `T` in advance.

¶1 `extract` is used to get a value out of a reflection when its type is known. ¶12 With `U` being `remove_cv_t<T>`, it is equivalent to the following dispatch:

```cpp
if constexpr (is_reference_type(^^T)) {
  return extract-ref<T>(r);
} else if (is_nonstatic_data_member(r) || is_function(r)) {
  return extract-member-or-function<U>(r);
} else {
  return extract-value<U>(constant_of(r));
}
```

All three paths accept only strictly matching types. A reflection carries the exact type of the value; if `extract` allowed arbitrary conversions, it would amount to unchecked type punning.

**References** (¶3–¶5). `r` must represent a variable or object of type `U`, and the result is a reference to that object. ¶5 requires `is_convertible_v<remove_reference_t<U>(*)[], remove_reference_t<T>(*)[]>` to be true. Comparing via pointers to arrays lets through only qualification conversions (adding `const`, `volatile`) and blocks conversions such as derived to base (Note 2). If `r` represents a variable, it must also be usable in constant expressions or have begun its lifetime during the current constant evaluation.

**Members and functions** (¶6–¶7). A non-static data member (which must not be a bit-field) gives a member pointer `X C::*`, and `T` must be similar to it ([[conv.qual]]) and convertible from it. An implicit object member function requires `T` to be exactly `F C::*`; a non-member function, static member function or explicit object member function requires `T` to be exactly `F*`.

**Values** (¶8–¶10). The value is first obtained with `constant_of`, then `static_cast<T>`. ¶10 allows only four cases: the value's type is the same as `T` without cv; both are pointers that are similar (or both function pointers) and convertible; the value is an array and `T` is a similar pointer to element; the value is a closure object and `T` is a function pointer it converts to.

Annotation values also take this path: `extract<int>(annotations_of(^^g)[0])`; see [[meta.reflection.queries]].

## Getting reflections from values [meta.reflection.result]

### `reflect_constant` (¶1–¶6)

```cpp
template<auto D> struct A { };
struct N { int x; };
struct K { char const* p; };

constexpr info r1 = reflect_constant(42);
static_assert(is_value(r1) && r1 == template_arguments_of(^^A<42>)[0]);

constexpr info r2 = reflect_constant(N{42});
static_assert(is_object(r2) && r2 == template_arguments_of(^^A<N{42}>)[0]);

constexpr info r3 = reflect_constant(K{nullptr});   // OK
constexpr info r4 = reflect_constant(K{"ebab"});    // error: the pointer points to a string literal
```

¶3 The standard defines `reflect_constant(v)` with an invented template `template<T P> struct TCls;`: ¶4 the result is `template_arguments_of(^^TCls<V>)[0]`, where `V` is the value of `v`. In other words, the result equals what you get by using `v` as a constant template argument: for class types the reflection of a template parameter object, for other types the reflection of a value (Note 1).

This also determines its restrictions. ¶1 `T` must be copy constructible and a cv-unqualified, non-reference **structural type** ([[g:structural-type]]), i.e. a type usable as a constant template parameter. ¶5 It throws if `TCls<V>` is invalid, which is what happens with `r4` above: the address of a string literal cannot be a template argument ([[temp.arg.nontype]]). The fix is to first get a character array usable as a template argument with `define_static_string("ebab")` (see [[meta.reflection]]).

### `reflect_object` and `reflect_function` (¶7–¶12)

```cpp
template<class T> consteval info reflect_object(T& expr);   // T must be an object type
template<class T> consteval info reflect_function(T& fn);   // T must be a function type
```

¶8 They return the reflection of the very object or function the argument refers to. ¶9 That object or function must be suitable as a constant template argument of type `T&`: objects with automatic storage duration and string literal objects, for example, are not.

The difference between `reflect_object(s)` and `reflect_constant(s)` is identity: the former represents the object `s` itself, the latter a template parameter object that is template-argument-equivalent to `s`, and the two are not equal (see the `constant_of` example in [[meta.reflection.queries]]).

## Using reflections as template arguments: `substitute` [meta.reflection.substitute]

```cpp
consteval info to_integral_constant(unsigned i) {
  return substitute(^^integral_constant, {^^unsigned, reflect_constant(i)});
}
constexpr info r = to_integral_constant(2);   // r represents integral_constant<unsigned, 2>
```

`i` is an ordinary parameter of a `consteval` function, not a constant expression, so `integral_constant<unsigned, i>` cannot be written directly. `reflect_constant(i)` turns its value into a reflection, and `substitute` then uses that reflection as a template argument. Before C++26, the same thing could only be done by detour, with `integer_sequence` and pack expansion or with recursive templates.

```cpp
template<class R>
concept reflection_range =
  ranges::input_range<R> &&
  same_as<ranges::range_value_t<R>, info> &&
  same_as<remove_cvref_t<ranges::range_reference_t<R>>, info>;

template<reflection_range R = initializer_list<info>>
  consteval bool can_substitute(info templ, R&& arguments);
template<reflection_range R = initializer_list<info>>
  consteval info substitute(info templ, R&& arguments);
```

A `reflection_range` is an input range whose element type is `info`; `vector<info>`, `span<const info>` and `initializer_list<info>` all qualify. The default template argument `initializer_list<info>` lets the brace form `substitute(^^X, {^^int, ^^char})` get through deduction.

¶1 Each argument reflection is spliced into a template argument according to its kind: a template as `template [: x :]`, a type as `typename [: x :]`, anything else as `([: x :])`. ¶3 `can_substitute` tells whether the resulting `Z<...>` is a valid *template-id* ([[temp.names]]) and is not a function whose type still contains an undeduced placeholder. ¶7 `substitute` returns `^^Z<...>`, and ¶8 throws if it is invalid. ¶4 Both throw if `templ` is not a template or some argument cannot be used as a template argument.

### Errors outside the immediate context

```cpp
template<class T> auto fn1();
static_assert(!can_substitute(^^fn1, {^^int}));
constexpr info r1 = substitute(^^fn1, {^^int});       // error: the return type of fn1<int> is not yet deduced

template<class T> auto fn2() {
  static_assert(^^T != ^^int);
  return 0;
}
constexpr bool r2 = can_substitute(^^fn2, {^^int});   // error: deducing the return type instantiates the body,
                                                      // and the static_assert in the body fails
```

¶5 As with SFINAE, only errors that occur in the **immediate context** ([[g:immediate-context]]) make `can_substitute` return `false`. If forming `Z<...>` fails outside the immediate context, for example while instantiating a function body or class template definition, the program is ill-formed (Notes 1 and 2). `fn1` has no definition, its return type cannot be deduced, `can_substitute` returns `false`, and `substitute` throws; `fn2` has a definition, deducing its return type requires instantiating the body, and the failing `static_assert` in the body is a hard error, so even `can_substitute` itself fails.

## Generating class definitions [meta.reflection.define.aggregate]

```cpp
struct Point;                                   // only declared
consteval {                                     // consteval block ([dcl.pre])
  define_aggregate(^^Point, {
    data_member_spec(^^int, {.name = "x"}),
    data_member_spec(^^int, {.name = "y"}),
  });
}
// from here on Point is as if struct Point { int x; int y; };
constexpr Point p{1, 2};
static_assert(p.x + p.y == 3);
```

This is the only interface in C++26 reflection that can generate new declarations: it injects a definition for an incomplete class during constant evaluation. The generated class can only have public non-static data members and unnamed bit-fields, i.e. it is an aggregate. Generating member functions, base classes, access control and constructors involves many unresolved design questions, and C++26 does not include it. Even so, combined with `nonstatic_data_members_of` it can already do a lot, such as converting an array of structs into a struct of arrays (AoS → SoA) or generating tuple types from fields.

### Describing a member: `data_member_spec` (¶1–¶6)

```cpp
struct data_member_options {
  struct name-type { /* constructible from string or u8string */ };
  optional<name-type> name;
  optional<int> alignment;
  optional<int> bit_width;
  bool no_unique_address = false;
  vector<info> annotations;
};
consteval info data_member_spec(info type, data_member_options options);
consteval bool is_data_member_spec(info r);
```

¶4 `data_member_spec` returns the reflection of a **data member description** ([[g:data-member-description]]). It is a six-tuple `(T, N, A, W, NUA, ANN)`: the type (with aliases stripped), the name, the alignment, the bit-field width, whether it is `[[no_unique_address]]`, and the values of the annotations; items not provided are written ⊥. Such reflections are mainly for `define_aggregate`, but can also be queried with `type_of`, `identifier_of`, `size_of` and so on (Note 2).

¶3 `name` can be given an ordinary string (`"x"`, `string_view`, `string`) or a UTF-8 string (`u8"x"`). ¶1 `data_member_options` is not a structural type, and its values can only exist during constant evaluation.

¶5 lists the rules a data member declaration would have to follow anyway; if they are not met, it throws:

- the type must be an object type or a reference type;
- the name must be a valid identifier token. Universal-character-names are not processed: `R"(\u03B1)"` is an invalid name and is not treated as `α` (Note 3);
- without a name, a bit width must be specified and there must be no annotations, i.e. only an unnamed bit-field is possible;
- when a bit width is specified, the type must be integral or enumeration, alignment and `no_unique_address` cannot also be specified, the width cannot be negative, a width of 0 cannot have a name, and the type of an unnamed bit-field cannot be cv-qualified;
- the alignment must be a valid alignment value, no smaller than the type's own alignment;
- each annotation must have a non-array object type, and taking its constant value must not throw.

### `define_aggregate` (¶7–¶11)

```cpp
template<reflection_range R = initializer_list<info>>
  consteval info define_aggregate(info class_type, R&& mdescrs);
```

¶8 The call is a constant expression only if:

1. `class_type` represents a cv-unqualified class type `C`;
2. `C` is incomplete from every point in the evaluation context;
3. every argument is a data member description whose type is a complete type;
4. named members have pairwise distinct names, unless the name is `_` ([[g:name-independent-declaration]]).

Condition 2 means the same class can be defined only once: on a second call it is already complete. `C` may be a specialization of a class template, in which case what is generated is an explicit specialization (Note 4).

¶9 The effect is to produce an **injected declaration** ([[g:injected-declaration]], [[expr.const.reflect]]) defining `C`:

- it is in the scope `C` belongs to, with its locus immediately following the core constant expression currently being evaluated. So within the same expression, `C` is still incomplete;
- each data member description corresponds to a public member: one without a name is an unnamed bit-field, one with a name is a non-static data member with that name; the bit width, `alignas`, `[[no_unique_address]]` and annotations are all set as described;
- members are declared in the order of `mdescrs`;
- the sequence of data member descriptions forms the characteristic sequence of the injected declaration, used for ODR checks across translation units ([[expr.const.reflect]]).

¶10 The return value is `class_type`. ¶11 If `C` is a specialization of a templated class that has not been instantiated, it is treated as an explicit specialization.

## Common misconceptions

!!! pitfall "Thinking `extract` performs arithmetic conversions"
    `extract<long>(^^some_int_constant)` throws; it does not convert `int` to `long`. When a conversion is needed, check the type with `type_of` first, or use a splice `[: r :]`: a splice gives an ordinary expression, and implicit conversions apply afterwards as usual.

!!! pitfall "Thinking `can_substitute` never errors"
    `can_substitute` only checks the immediate context. Function templates whose return type must be deduced and class templates whose instantiation triggers a `static_assert` can make `can_substitute` itself a hard error, as with `fn2` above.

!!! pitfall "Calling `define_aggregate` on a class that is already defined"
    Paragraph 8.2 requires `C` to be incomplete from every point in the evaluation context. Calling it on a class that already has a definition, or calling it twice for the same class, is not a constant expression, and the program does not compile.
