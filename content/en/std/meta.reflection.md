---
title: Reflection
summary: "An overview of the C++26 static reflection library <meta>: std::meta::info and the groups of functions, the general rules, the define_static_* functions that promote compile-time data to static storage, the meta::exception error model, and the operators enumeration."
updated: 2026-10-19
---

!!! tldr
    - The reflection operator `^^` turns a program construct (a type, variable, function, namespace, ...) into a value of type `std::meta::info`; the `consteval` functions in `<meta>` query and transform that value; a splice `[: r :]` turns the value back into a program construct.
    - `info` is a scalar type that can be copied, compared and used as a template argument, but only at compile time.
    - Memory allocated during constant evaluation must be released before the evaluation ends, so the `vector` returned by `members_of` cannot leave compile time. `define_static_array` and `define_static_string` copy the data into static storage, and the result can be used outside compile time.
    - When a precondition is not met, reflection functions throw `std::meta::exception`, which can be caught during constant evaluation; if it is not caught, compilation fails with the error message in the diagnostic.
    - The results of reflection functions returning `string_view` are all terminated by `'\0'` and can be used directly as C strings.

!!! warning "The examples on this page have not been verified"
    Clang 23 with libc++ does not yet support C++26 static reflection: there is no `^^` operator and no `<meta>` header. The code on this page and in [[meta.reflection.queries]], [[meta.reflection.extract]] and [[meta.reflection.traits]] is written from the current draft and the standard's own examples, has not been compiled, and therefore carries no verdict.

## An example: enumerator to string

```cpp
#include <meta>
#include <string_view>

template<class E>
  requires std::is_enum_v<E>
constexpr std::string_view to_string(E value) {
  template for (constexpr auto e :
      std::define_static_array(std::meta::enumerators_of(^^E))) {
    if (value == [: e :])
      return std::meta::identifier_of(e);
  }
  return "<unnamed>";
}
```

This function uses all three stages of reflection:

1. `^^E` is the reflection operator ([[expr.reflect]]), giving a value of type `std::meta::info` that represents the enumeration type `E`.
2. `enumerators_of` and `identifier_of` are library functions in `<meta>`, giving all the enumerators of an enumeration and the name of one enumerator, respectively.
3. `[: e :]` is a splice ([[basic.splice]], [[expr.prim.splice]]), turning the reflection `e` back into the enumerator it represents, which can be compared with `value`.

`enumerators_of` returns `std::vector<info>`, and the memory a `vector` allocates during constant evaluation must be released before the evaluation ends, so it cannot be what an expansion statement ([[stmt.expand]]) iterates over. `define_static_array` copies it into an array with static storage and returns a `span` referring to it. This is the most common idiom when using `<meta>`; the principle is explained in the section on promoting to static storage below.

## `std::meta::info`

```cpp
namespace std::meta {
  using info = decltype(^^::);
}
```

`info` is defined as the type of `^^::` (the reflection of the global namespace). It is a fundamental type and a scalar type ([[basic.fundamental#17]]). Values of `info` are called [[g:reflection|reflections]]; there is a unique null reflection, and every other reflection represents a program construct: a type, variable, function, namespace, template, enumerator, base class relationship, and so on.

Being a scalar type, an `info` value can be copied, compared with `==`, and used as a constant template argument. But it is a [[g:consteval-only-value|consteval-only value]] that can exist only at compile time and cannot flow into run-time code.

## Function groups

The synopsis of `<meta>` ([meta.syn]) groups the functions by subclause. This site splits them across four pages:

| Subclause | Representative functions | Purpose | Page |
|---|---|---|---|
| [meta.string.literal] | `is_string_literal` | Whether a pointer points into a string literal | This page |
| [meta.define.static] | `define_static_string`, `define_static_array`, `define_static_object` | Promoting compile-time data to static storage | This page |
| [meta.reflection.exception] | `meta::exception` | Error reporting for reflection functions | This page |
| [meta.reflection.operators] | `operators`, `operator_of`, `symbol_of` | Identifying operator functions | This page |
| [meta.reflection.names] | `identifier_of`, `display_string_of`, `source_location_of` | Names and locations | [[meta.reflection.queries]] |
| [meta.reflection.queries] | `type_of`, `parent_of`, `dealias`, `is_*`, `has_*` | Queries on a single reflection | [[meta.reflection.queries]] |
| [meta.reflection.scope] | `current_function`, `current_class` | Where a call occurs | [[meta.reflection.queries]] |
| [meta.reflection.access.context] etc. | `access_context`, `is_accessible` | Access control | [[meta.reflection.queries]] |
| [meta.reflection.member.queries] | `members_of`, `bases_of`, `enumerators_of` | Listing members | [[meta.reflection.queries]] |
| [meta.reflection.layout] | `offset_of`, `size_of`, `alignment_of` | Layout | [[meta.reflection.queries]] |
| [meta.reflection.annotation] | `annotations_of` | Reading annotations `[[=...]]` | [[meta.reflection.queries]] |
| [meta.reflection.extract] | `extract<T>` | Getting values back from reflections | [[meta.reflection.extract]] |
| [meta.reflection.substitute] | `can_substitute`, `substitute` | Using reflections as template arguments | [[meta.reflection.extract]] |
| [meta.reflection.result] | `reflect_constant`, `reflect_object` | Getting reflections from values | [[meta.reflection.extract]] |
| [meta.reflection.define.aggregate] | `data_member_spec`, `define_aggregate` | Generating class definitions | [[meta.reflection.extract]] |
| [meta.reflection.traits] | `is_trivially_copyable_type`, `remove_cvref` | Reflection versions of `<type_traits>` | [[meta.reflection.traits]] |

## General rules

The five paragraphs of [meta.syn] apply to every function in `<meta>`.

¶1 Unless otherwise specified, these functions and function template specializations are addressable functions ([[namespace.std]]), so their addresses can be taken, for example to pass `std::meta::is_public` as a predicate to an algorithm. The functions in [meta.reflection.scope] and `access_context::current` are the explicitly specified exceptions, because their results depend on where the call appears.

¶2 When these functions throw `meta::exception`, the exception's `from()` is a reflection representing the function that threw it, and `where()` is the source location of the call to that function.

¶3 Passing a reflection that represents a construct not specified by the standard to a function in `std::meta` has implementation-defined behavior. `info` can represent implementation-specific constructs (Note 1). Note 2 points out a side effect: the results of many functions depend on whether a class type is complete, so whenever `dealias(r)` represents a class template specialization with a reachable definition, that specialization is implicitly instantiated. For example, `size_of(^^X<int>)` instantiates `X<int>`.

¶4 For functions returning `string_view` or `u8string_view`, the result `V` satisfies `V.data()[V.size()] == '\0'`. These characters are [[g:potentially-non-unique-object|potentially non-unique]] objects with static storage duration, usable in constant expressions, but a pointer to them cannot be the argument of a constant template parameter of pointer type ([[temp.arg.nontype]]). So `identifier_of(r).data()` can be used directly as a C string.

¶5 Writing `^^E` in this clause for a reflection representing the source construct `E` is only a notational convention.

## Promoting to static storage

¶1 ([meta.define.static]): the functions in this subclause promote compile-time storage into static storage.

Memory allocated with `new` during constant evaluation, including the buffers of `std::vector` and `std::string`, must be released before that evaluation ends; this is called a [[g:transient-allocation|transient allocation]] ([[expr.const]]). So `constexpr std::vector<info> v = members_of(...);` is ill-formed, and the `vector` returned by a reflection function cannot be carried out of constant evaluation directly.

The solution is to copy the data into a [[g:template-parameter-object|template parameter object]]. Template parameter objects already have static storage duration and are usable in constant expressions, which is exactly what is needed.

```cpp
#include <meta>
#include <string>

consteval const char* make_name(int n) {
  std::string s = "field_";  // transient allocation
  s += static_cast<char>('0' + n);
  return std::define_static_string(s);
}
constexpr const char* name = make_name(3);  // "field_3"
static_assert(!std::is_string_literal(name));
```

`s`'s buffer is released before `make_name` returns; the pointer returned by `define_static_string` points to a template parameter object with the same contents, so it can be stored in a `constexpr` variable.

### The five functions

| Function | Result |
|---|---|
| `meta::reflect_constant_string(r)` | A reflection representing a template parameter object `const CharT[N+1]`, with `CharT()` appended |
| `meta::reflect_constant_array(r)` | A reflection representing a template parameter object `const T[N]`; for an empty range, `const array<T, 0>` |
| `define_static_string(r)` | A `const CharT*` pointing to the string object above |
| `define_static_array(r)` | A `span<const T, N>` or `span<const T>` referring to the array above |
| `define_static_object(t)` | A `const remove_cvref_t<T>*` pointing to a static object equivalent to `t` |

`reflect_constant_*` return reflections, which can be passed on to other reflection functions or spliced; `define_static_*` return ordinary pointers or `span`s that can be used directly in code that does not involve reflection. The latter are all defined in terms of the former plus `meta::extract`.

`reflect_constant_string` (paragraphs 2–7) requires the element type `CharT` to be a character type (*Mandates*). If `r` refers to a string literal object, the copy excludes its terminating null character, so the result does not contain two `'\0'`. The result object is potentially non-unique: two calls with the same contents may or may not yield the same object (Note 1).

`reflect_constant_array` (paragraphs 8–14) requires the element type `T` (the type with all array dimensions removed) to be a [[g:structural-type|structural type]], to satisfy `copy_constructible`, and to be constructible from the range's reference type. Each element is first `static_cast<T>` and then passed to `reflect_constant`, recursing for elements that are themselves arrays; the `I`-th element of the result array is template-argument-equivalent ([[temp.type]]) to the object represented by the `I`-th reflection. Exceptions thrown by range operations propagate as usual; if some `reflect_constant` would exit via an exception, `meta::exception` is thrown (paragraph 13).

`define_static_string` (paragraph 15) is equivalent to `meta::extract<const range_value_t<R>*>(meta::reflect_constant_string(r))`.

`define_static_array` (paragraphs 16–17) constructs a `span` from the result of `reflect_constant_array`. If `ranges::size(r)` is a constant expression, the extent of the `span` is fixed at that value; otherwise it is `dynamic_extent`.

`define_static_object` (paragraphs 18–19) uses `reflect_constant` for class types and unions, `reflect_constant_array` for arrays, and for other types borrows `define_static_array` on a one-element `span`. For class types, the result is the address of the template parameter object that is template-argument-equivalent to `t` (Note 3).

### `is_string_literal`

```cpp
consteval bool is_string_literal(const char* p);  // plus wchar_t, char8_t, char16_t and char32_t versions
```

[meta.string.literal] paragraph 1: if `p` points to an [[expr.const.core|unspecified object]], returns `false`; otherwise, if `p` points to a subobject of a string literal object ([[lex.string]]), returns `true`; otherwise returns `false`.

The address of a string literal cannot be a constant template argument ([[temp.arg.nontype]]), but a template parameter object produced by `define_static_string` can. With `is_string_literal`, `consteval` code can tell these two kinds of pointer apart, for example to diagnose when given a string literal, or to convert it once with `define_static_string` first.

## `meta::exception`

```cpp
namespace std::meta {
  class exception : public std::exception {
  public:
    consteval exception(u8string_view what, info from,
        source_location where = source_location::current()) noexcept;
    consteval exception(string_view what, info from,
        source_location where = source_location::current()) noexcept;
    constexpr const char* what() const noexcept override;
    consteval u8string_view u8what() const noexcept;
    consteval info from() const noexcept;
    consteval source_location where() const noexcept;
    // copy and move construction and assignment are all defaulted
  };
}
```

¶1: reflection functions report errors by throwing `meta::exception`.

C++26 allows throwing and catching exceptions during constant evaluation ([[P3068R6]]), and this design depends on it. The specification of `<meta>` is full of "*Throws*: `meta::exception` unless …", meaning that an unmet precondition throws an exception rather than being undefined behavior or ill-formed. Callers can catch it in a `consteval` function; if the exception escapes the constant evaluation, the evaluation is not a constant expression and the compiler reports an error.

```cpp
#include <meta>

consteval bool safe_has_parent(std::meta::info r) {
  try {
    (void)std::meta::parent_of(r);
    return true;
  } catch (const std::meta::exception& e) {
    // e.from() == ^^std::meta::parent_of
    // e.where() is the location of the call above
    return false;
  }
}
static_assert(!safe_has_parent(^^::));  // the global namespace has no parent
```

`parent_of` throws `meta::exception` when `has_parent(r)` is false ([[meta.reflection.queries]]), which is exactly the case for the global namespace.

The error message can be given in the ordinary literal encoding or in UTF-8, and each constructor stores a copy (paragraphs 2–4). When constructed from a `u8string_view`, if the message can be represented in the ordinary literal encoding, a transcoded copy is also stored for `what()`; otherwise that copy is empty. When constructed from a `string_view`, the constructor has a *Constant When* condition: the call is a constant expression only if the message can be encoded in UTF-8.

The *Constant When* condition of `what()` (paragraphs 5–6) is that the ordinary-encoding copy is not empty. That is, if the message can only be represented in UTF-8, calling `what()` during constant evaluation is not a constant expression, and `u8what()` should be used instead. `u8what()`, `from()` and `where()` return the corresponding stored values (paragraphs 7–9).

## Representing operators

```cpp
enum class operators { /* op_new, op_delete, ..., op_comma */ };
using enum operators;
consteval operators operator_of(info r);
consteval string_view symbol_of(operators op);
consteval u8string_view u8symbol_of(operators op);
```

An operator function such as `operator+=` has no identifier; `has_identifier` in [[meta.reflection.queries]] returns `false` for it, and `identifier_of` is of no use. This group of interfaces exists specifically to identify operator functions.

¶1: each enumerator of the enumeration `operators` corresponds to an overloadable operator, 44 in total, with distinct values (Table 63). The names spell out how the symbols are read in English, for example `op_plus` (`+`), `op_plus_equals` (`+=`), `op_equals_equals` (`==`), `op_spaceship` (`<=>`), `op_parentheses` (`()`), `op_square_brackets` (`[]`), `op_arrow_star` (`->*`), `op_array_new` (`new[]`), `op_co_await` (`co_await`).

¶2–3: `operator_of(r)` returns the enumerator corresponding to the name of the operator function or operator function template represented by `r`. If `r` does not represent an operator function or operator function template, it throws `meta::exception`.

¶4–5: `symbol_of(op)` and `u8symbol_of(op)` return the operator's symbol, such as `"+="`, in the ordinary literal encoding and UTF-8 respectively. If the value of `op` does not correspond to any enumerator, for example `static_cast<operators>(-1)`, they throw `meta::exception`.

## Design choice: reflections are values, not types

The earlier Reflection TS used a type-based design: each reflection was a distinct type, queried with type traits in the style of `<type_traits>`, but every query instantiated templates, which was expensive to compile and hard to process with loops. [[P2996R13]], which made it into C++26, switched to a value-based design: all reflections are values of the single type `info`, queries are ordinary `consteval` functions, and reflections can be stored in a `vector` and processed with loops and algorithms. Annotations ([[P3394R4]]), `define_static_*`, `meta::exception` and others were added by other proposals in the same period.

## Quick reference

| Topic | Key points |
|---|---|
| `info` | `decltype(^^::)`; a scalar type, comparable, usable only at compile time |
| General rules | Functions are addressable; exceptions carry `from()` and `where()`; string results are `'\0'`-terminated with static storage duration |
| `define_static_*` | Copy transiently allocated data into template parameter objects to get static storage |
| `is_string_literal` | Tells string literals apart from other character arrays |
| `meta::exception` | Thrown when a precondition is not met; can be caught during constant evaluation |
| `operators` | 44 overloadable operators; `operator_of`, `symbol_of` |
