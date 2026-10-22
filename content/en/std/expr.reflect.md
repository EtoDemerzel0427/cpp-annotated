---
title: The reflection operator ^^
summary: C++26's ^^ turns program constructs such as types, variables, functions, namespaces and templates into std::meta::info values; this page covers how it is parsed, what each kind of operand yields, which operands are ill-formed, and why reflection values must stay at compile time.
updated: 2026-10-19
---

!!! tldr
    - `^^x` produces a value of type `std::meta::info` representing the program construct `x`; `[: r :]` splices it back into code. In between, the `consteval` functions in `<meta>` query it.
    - Non-null reflection values can only exist at compile time: they can be stored in `constexpr` variables, used as template arguments, and used inside `consteval` functions, but cannot reach run time.
    - What follows `^^` is parsed by longest match, so `^^int && x` takes `&&` as part of the type; a `^^X` that designates a template cannot be directly followed by `<`.
    - The reflection of a type alias is the alias itself, not the type it refers to; for a template parameter, `^^T` is the actual type at instantiation.
    - Cannot be reflected: names found through a using-declaration, enclosing local variables across a lambda, `__func__`, constant template parameters.

## Reflection and splicing

{{c++26}} Static reflection ([[P2996R13]]) consists of a pair of inverse operations: `^^` turns a program construct into a value, and a splice `[: r :]` turns the value back into code ([[expr.prim.splice]], [[basic.splice]]). In between, the `consteval` functions provided by `<meta>`, such as `members_of`, `type_of` and `identifier_of`, query and transform reflection values ([[meta.reflection]]).

```cpp title="enum-to-string.cpp"
#include <meta>
#include <string_view>

template<typename E>
    requires std::is_enum_v<E>
constexpr std::string_view to_string(E value) {
    template for (constexpr auto e : std::define_static_array(std::meta::enumerators_of(^^E))) {
        if (value == [:e:])
            return std::meta::identifier_of(e);
    }
    return "<unnamed>";
}

enum class Color { red, green, blue };
static_assert(to_string(Color::green) == "green");
```

`^^E` gives the reflection of the enumeration type; `enumerators_of` lists its enumerators; `template for` ([[stmt.expand]]) expands one copy of the loop body for each enumerator; `[:e:]` splices the enumerator's reflection back into an expression like `Color::red`; `identifier_of` gets the name. Code like this used to require macros or external code generators.

The `std::vector` returned by `enumerators_of` can only exist during constant evaluation, so `std::define_static_array` converts it to an array with static storage duration that can serve as the range of the expansion statement. `to_string` itself is still an ordinary `constexpr` function template and can be called at run time.

!!! warning "The examples on this page have not been compiled"
    Clang 23 doesn't implement static reflection yet: there is no `<meta>` header and `^^` isn't recognized. All code on this page is analyzed against the text of the current draft, so it carries no verdict markers. Compiler Explorer has an experimental Clang branch implementing P2996 to experiment with, but its behavior may differ from the current draft's wording.

This page covers only `^^`: what its operand can be and what the result represents.

## Grammar

```text
reflect-expression:
    ^^ ::
    ^^ reflection-name
    ^^ type-id
    ^^ id-expression

reflection-name:
    nested-name-specifier-opt identifier
    nested-name-specifier template identifier
```

The four forms correspond, in order, to: the global namespace; constructs found by name lookup, such as namespaces, templates, concepts and type aliases; types; and entities in expressions, such as variables, functions, enumerators and data members.

`^^` is a single token ([[lex.operators]]). Early versions of P2996 used a single `^`, but Clang's blocks extension already uses `^` for block literals (`^{ ... }`), which would be ambiguous in Objective-C++; [[P3381R0]] compared several candidates and switched to `^^`.

## The result: a value that must stay at compile time (¶1)

¶1 The unary `^^` is called the **reflection operator** ([[g:reflection-operator]]), and its result is a prvalue of type `std::meta::info`. A value of this type is called a **reflection** ([[basic.fundamental#17]]). The value-initialized `std::meta::info{}` is the unique **null reflection**, which represents no construct.

`^^` itself can appear anywhere, but a non-null reflection is a **consteval-only value** ([[expr.const.const#1]]). An object containing such a value is called an **immediate object**, and [[expr.const.const#3]] requires every immediate object to be one of:

- the object of a `constexpr` variable, or a subobject of one;
- a template parameter object, that is, the object created for a template argument;
- an object whose lifetime lies entirely within a single constant evaluation.

An expression that odr-uses such a variable must also be in an immediate function context, for example inside a `consteval` function body. So reflection values never reach run time:

```cpp title="reflect-consteval-only.cpp"
#include <meta>

template<std::meta::info R> struct C {};

constexpr std::meta::info r = ^^int;   // OK: constexpr variable
auto c = C<^^char>();                   // OK: template argument
auto d = ^^int;                         // error: the immediate object isn't a constexpr variable

consteval bool is_int(std::meta::info x) { return x == ^^int; }   // OK: immediate function context
static_assert(is_int(r));

std::meta::info null_r{};               // a null reflection isn't a consteval-only value
```

Under the current draft's wording, the null reflection in the last line isn't subject to these restrictions and can be stored in an ordinary variable.

Template code usually doesn't need `consteval` everywhere. A specialization of a `constexpr` function template that does something only allowed in an immediate function context is automatically escalated to an immediate function ([[expr.const.imm]]).

Note 1 says an implementation may use reflections to represent constructs the standard doesn't describe, such as compiler extensions. Conversely, [[basic.fundamental#18]] recommends against representing as reflections constructs that the standard does describe but that aren't on the list of reflectable ones, such as using-declarations, partial specializations, attributes, statements and expressions.

## Parsing: longest match (¶2–¶3)

¶3 A *reflect-expression* is parsed as the longest sequence of tokens that could syntactically form one. So the type after `^^` swallows as many declarator operators such as `&`, `&&`, `*` and `()` as it can. The standard's Example 1:

```cpp title="reflect-parse.cpp"
static_assert(std::meta::is_type(^^int()));   // OK: ^^ applies to the function type int()

template<bool> struct X {};
consteval bool operator<(std::meta::info, X<false>) { return false; }

consteval void g(std::meta::info r, X<false> xv) {
    r == ^^int && true;     // error: ^^ applies to int&&, and the following true doesn't fit
    r == ^^int & true;      // error: ^^ applies to int&
    r == (^^int) && true;   // OK
    r == ^^int &&&& true;   // error: int &&&& isn't a valid type-id
    ^^X < xv;               // error: ^^X designating a template followed by <
    (^^X) < xv;             // OK
    ^^X<true> < xv;         // OK: ^^X<true> is a specialization (a type), not a template
}
```

The `int &&&&` line shows that longest match doesn't backtrack: the parser takes `int &&&&`, finds it isn't a valid type, and reports an error; it doesn't go back and try `int&&` followed by `&& true`.

The second sentence of ¶3 says an unparenthesized *reflect-expression* that designates a template shall not be followed by `<`. Whether `^^X <` is followed by a template argument list or a less-than sign is hard for both readers and parsers to tell, so the standard simply requires parentheses instead of adding a disambiguation rule.

¶2 The component names of a *reflection-name* are the names in its *nested-name-specifier* and *identifier* ([[basic.lookup.qual]]). In the form `nested-name-specifier template identifier`, the last name must denote a template. This is how a member template is reflected in a dependent context: `^^T::template tmpl`.

## `^^::` (¶4)

¶4 `^^::` represents the global namespace. The global namespace has no name, and this is the only way to get it without name lookup.

```cpp title="reflect-global.cpp"
#include <meta>
static_assert(std::meta::is_namespace(^^::));
static_assert(std::meta::parent_of(^^std) == ^^::);
```

## Reflecting by name (¶5)

¶5 Whenever `^^reflection-name` can match, it is interpreted in that form: name lookup is performed for the *identifier*, and the result is determined by the first applicable rule.

| Item | Lookup finds | Result |
|---|---|---|
| ¶5.1 | a declaration that replaced a using-declarator | ill-formed |
| ¶5.2 | a namespace alias | that alias; the declarations found must be in the same target scope |
| ¶5.3 | a namespace | that namespace |
| ¶5.4 | a concept | that concept |
| ¶5.5 | a template | see below |
| ¶5.6 | a type alias | for a template parameter, the actual entity; otherwise the alias itself |
| ¶5.7 | a class or enumeration | that type |
| ¶5.8 | a member of an anonymous union | that member |
| ¶5.9 | anything else | treated as an *id-expression*, see ¶7 |

`int` is a keyword, not an *identifier*, so `^^int` can only be `^^type-id`. But `^^Y` (where `Y` is a typedef name) matches `^^reflection-name`, so it goes through ¶5.6 and gives the type alias, not through ¶6 to give the type.

### Type aliases and template parameters (¶5.6)

```cpp title="reflect-alias.cpp"
#include <meta>

template<typename T>
struct S {
    static constexpr std::meta::info r = ^^T;   // template parameter: the actual type
    using type = T;
};
static_assert(S<int>::r == ^^int);
static_assert(^^S<int>::type != ^^int);                        // the member alias isn't equal to int
static_assert(std::meta::dealias(^^S<int>::type) == ^^int);   // dealias strips the alias

typedef struct X {} Y;
typedef struct Z {} Z;
constexpr std::meta::info e = ^^Y;   // type alias Y
constexpr std::meta::info f = ^^Z;   // type alias Z, not class Z
```

¶5.6.1 If what is found is a template parameter `T`, the result is the underlying entity of `T`, that is, the type substituted at instantiation, so in `S<int>`, `^^T == ^^int`. ¶5.6.2 For any other type alias, the reflection is the alias itself; call `std::meta::dealias` when you need the underlying type.

The distinction exists because reflection is often used to generate diagnostics and serialization code: `identifier_of(^^Y)` should be `"Y"`, not `"X"`. The name of a template parameter, on the other hand, isn't what users want to see, so `^^T` should represent the actual type.

¶5.6.2 also requires all declarations found to be in the same target scope. The standard's Example 3:

```cpp title="reflect-alias-ambig.cpp"
#include <meta>
namespace A { using T = int; }
namespace B { using T = int; }
using namespace A;
using namespace B;
auto r = ^^T;   // error: found type aliases in two different scopes
```

In ordinary code `T x;` is valid, because two declarations denoting the same type aren't ambiguous ([[basic.lookup]]). But these are two different aliases, and `^^T` doesn't know which one to represent.

### Templates (¶5.5)

```cpp title="reflect-template.cpp"
#include <meta>
#include <vector>

template<class T> struct Box {
    static constexpr auto self = ^^Box;                   // injected-class-name: the specialization Box<T>
    static constexpr auto tmpl = ^^Box::template Box;     // with template: the class template Box
};
static_assert(Box<int>::self == ^^Box<int>);
static_assert(Box<int>::tmpl == ^^Box);

constexpr auto v = ^^std::vector;                         // class template
static_assert(std::meta::is_template(v));

template<class T> void f(T);
constexpr auto rf = ^^f;                                  // the only function template
```

- ¶5.5.1 Inside a class template, the class name finds the **injected-class-name** ([[class.pre]]), the class's name within its own scope. With the form `... template identifier` the result is the class template; otherwise it is the current specialization, consistent with `Box` meaning `Box<T>` inside the class template.
- ¶5.5.2 If an overload set is found, it must contain only declarations of a single function template, and the result is that template. Add a non-template overload `void f(int);` and `^^f` is ill-formed.
- ¶5.5.3 For a class template, variable template or alias template, the result is that template.

Note 2: lookup never finds partial or explicit specializations, so reflecting a template name always gives the primary template.

### Names found through a using-declaration (¶5.1)

The standard's Example 2:

```cpp title="reflect-using-decl.cpp"
#include <meta>
struct A { struct S {}; };
struct B : A { using A::S; };
constexpr std::meta::info r1 = ^^B::S;   // error: A::S was found through a using-declaration

struct C : virtual B { struct S {}; };
struct D : virtual B, C {};
D::S s;                                  // OK: by the class member lookup rules, D::S is C::S
constexpr std::meta::info r2 = ^^D::S;   // OK: C::S wasn't found through a using-declaration
```

A using-declaration isn't itself an entity and isn't represented as a reflection. If `^^B::S` silently returned the reflection of `A::S`, `identifier_of` and `parent_of` would give information about `A`, which wouldn't match the `B::S` written in the code. The standard chooses to reject it outright.

## Reflecting types (¶6)

```cpp title="reflect-type-id.cpp"
#include <meta>
#include <vector>

template<class T> using Vec = std::vector<T>;
constexpr auto a = ^^Vec<int>;                      // ¶6.2: type alias Vec<int>
static_assert(std::meta::is_type_alias(a));
static_assert(std::meta::dealias(a) == ^^std::vector<int>);

constexpr auto b = ^^const int*;                     // ¶6.3: type const int*
constexpr auto c = ^^int[3];                         // array type
constexpr auto d = ^^auto;                           // error: placeholder type (¶6.1)
```

¶6 For `^^type-id`:

- ¶6.1 A placeholder type, such as `auto` or `decltype(auto)`, is ill-formed. A placeholder isn't a type, and there is no initializer here to deduce from.
- ¶6.2 For a specialization of an alias template, such as `Vec<int>`, the result is the type alias named by that specialization.
- ¶6.3 Otherwise, the result is that type.

## Reflecting variables, functions and members (¶7)

```cpp title="reflect-id-expression.cpp"
#include <meta>

struct P { int x; int y; static int count; };
enum class Color { red, green };
int global = 0;

constexpr auto r1 = ^^global;          // variable
constexpr auto r2 = ^^P::x;            // non-static data member, no object needed
constexpr auto r3 = ^^P::count;        // static data member, fine even if undefined
constexpr auto r4 = ^^Color::red;      // enumerator
static_assert(std::meta::identifier_of(r2) == "x");
static_assert(std::meta::type_of(r2) == ^^int);
```

¶7.3 When the *id-expression* denotes a variable, structured binding, enumerator or non-static data member, the result represents that entity.

The last sentence of ¶7 says that the *id-expression* after `^^` is an **unevaluated operand** ([[expr.context]]). So `^^x` isn't an odr-use of `x`: a variable that is declared but not defined can be reflected, and it doesn't trigger a capture inside a lambda. Reflection is about the entity itself, not its value.

### Overload sets (¶7.2)

¶7.2 When the *id-expression* denotes an overload set, `&id-expression` treated as an unevaluated operand must be well-formed, that is, overload resolution ([[over.over]]) must select a unique function without a target type, and the result represents that function. In practice this requires the overload set to contain only one function, or a *template-id* that uniquely determines a specialization. The standard's Example 4:

```cpp title="reflect-overload.cpp"
#include <meta>
template<typename T> void fn() requires (^^T != ^^int);
template<typename T> void fn() requires (^^T == ^^int);
template<typename T> void fn() requires (sizeof(T) == sizeof(int));

constexpr std::meta::info a = ^^fn<char>;   // OK: only the first template's constraints are satisfied
constexpr std::meta::info b = ^^fn<int>;    // error: the last two templates' constraints are both satisfied, ambiguous
```

The selected function may be deleted. Reflection is often used to check whether a function is deleted (`std::meta::is_deleted`), which would be impossible without a reflection of it.

### What cannot be reflected (¶7.1, ¶7.4)

¶7.1 It is ill-formed if the *id-expression* denotes:

- ¶7.1.1 a variable declared by an init-capture, as in `[y = 1] { ^^y; }`;
- ¶7.1.2 the function-local predefined variable `__func__` ([[dcl.fct.def.general]]);
- ¶7.1.3 a parameter introduced by a *requires-expression*;
- ¶7.1.4 an enclosing local entity ([[basic.pre#9]]: a variable with automatic storage duration, a corresponding structured binding, `*this` and so on) with a lambda scope between it and the `^^`.

```cpp title="reflect-local-error.cpp"
#include <meta>
void f() {
    int x = 0;
    constexpr auto ok = ^^x;          // OK: local variable in the same function
    [] {
        constexpr auto r = ^^x;       // error: across a lambda scope (¶7.1.4)
    };
    [&x] {
        constexpr auto r = ^^x;       // error: same even when captured
    };
    [y = 1] {
        constexpr auto r = ^^y;       // error: init-capture (¶7.1.1)
    };
    constexpr auto g = ^^__func__;    // error: function-local predefined variable (¶7.1.2)
}
```

Should `^^x` inside a lambda represent the enclosing variable `x`, or the closure member created by capturing it? If it represented the enclosing variable, splicing it back would bypass the capture rules; if it represented the capture member, that entity wouldn't exist when there is no capture. The standard chooses to forbid it, captured or not. When needed, write `constexpr auto r = ^^x;` outside the lambda; `r` is a `constexpr` variable, and reading it inside the lambda doesn't require a capture.

¶7.4 Every other case is ill-formed. Note 3 points out that this includes a constant template parameter `^^N` and a pack-index-expression `^^ts...[0]`. A constant template parameter is just a value in an instantiation, not a variable; to get a reflection of the value, use `std::meta::reflect_constant(N)` ([[meta.reflection]]):

```cpp title="reflect-constant-param.cpp"
#include <meta>
template<int N>
consteval std::meta::info bad() { return ^^N; }   // error: constant template parameter
template<int N>
consteval std::meta::info good() { return std::meta::reflect_constant(N); }   // OK
```

!!! impl
    - `std::meta::info` is usually implemented as an opaque handle to an AST node inside the compiler (a declaration, a type, and so on), plus a tag indicating the kind.
    - Reflection values never reach run time, so they need no run-time object representation. But they can be template arguments (`C<^^int>`), so name mangling must distinguish `C<^^int>` from `C<^^char>`, and ABI specifications need new mangling forms for this.
    - `^^x` itself costs almost nothing: name lookup has already been done during parsing, and it just wraps the result as a value. The cost is in the subsequent queries (for example, `members_of` requires the class to be complete) and splices.

!!! history "From the Reflection TS to C++26"
    The Reflection TS used `reflexpr(T)` to produce a meta-object type, with queries done through type traits; template-based metaprogramming made that tedious to write and slow to compile, and that approach never made it into the standard. P2996 instead makes reflection produce values, and queries are ordinary `consteval` functions that can use loops, `std::vector` and algorithms. This relies on the growth in constant evaluation capabilities since C++20: `constexpr` dynamic allocation, `consteval`, and immediate function escalation. C++26 adds static reflection through [[P2996R13]], with expansion statements, annotations and so on as companion proposals.

## Common misconceptions

!!! pitfall "`^^int && x` is a logical AND of two operands"
    Longest match takes `&&` as part of the type. Add parentheses when comparing reflections: `(^^int) == r && cond`.

!!! pitfall "The reflection of an alias equals the type it refers to"
    `^^std::string != ^^std::basic_string<char>`; the former is the reflection of the type alias `std::string`. To check whether two are the same type, apply `std::meta::dealias` first.

## Questions

!!! question "Question 1"
    Given `using I = int;`, is `^^I == ^^int`? What about `std::meta::dealias(^^I) == ^^int`? In `template<class T> struct W { static constexpr auto r = ^^T; };`, is `W<I>::r == ^^int`?

<details markdown="1">
<summary>Answer</summary>

`^^I` represents the type alias `I` (¶5.6.2) and isn't equal to `^^int`. `dealias(^^I)` strips the alias and equals `^^int`.

In `W<I>::r`, `^^T` finds a template parameter, which by ¶5.6.1 represents the actual type. When the template argument `I` is substituted it is just the type `int`, and `W<I>` is `W<int>`, so `W<I>::r == ^^int` holds.
</details>

!!! question "Question 2"
    What are `constexpr auto a = ^^int();` and `constexpr auto b = ^^int{};`?

<details markdown="1">
<summary>Answer</summary>

`int()` can form a *type-id*, the type of a function returning `int` with no parameters, so by the longest match of ¶3, `a` is the reflection of that function type; it is the first line of the standard's Example 1.

`int{}` isn't a *type-id*; the longest sequence that can form a *reflect-expression* is `^^int`, and the remaining `{}` doesn't fit, so it is ill-formed. `^^` can't be applied to arbitrary expressions; to reflect the value 0, write `std::meta::reflect_constant(0)`.
</details>

## Summary

| Operand | Paragraph | Result or restriction |
|---|---|---|
| `^^::` | ¶4 | the global namespace |
| namespace, namespace alias, concept | ¶5.2–¶5.4 | the corresponding entity; an alias stays an alias |
| template name | ¶5.5 | the primary template; the injected-class-name defaults to the current specialization, with `template` it is the template |
| type alias | ¶5.6 | the alias itself; a template parameter gives the actual type |
| *type-id* | ¶6 | the type; an alias template specialization gives a type alias; placeholders are ill-formed |
| variable, structured binding, enumerator, non-static data member | ¶7.3 | that entity, not an odr-use |
| overload set | ¶7.2 | `&f` must select a unique function, which may be deleted |
| ill-formed | ¶5.1, ¶7.1, ¶7.4 | names found through a using-declaration; init-captures, `__func__`, requires parameters, local entities across a lambda; constant template parameters, pack indexing |
| parsing | ¶3 | longest match, no backtracking; must not be followed by `<` when designating a template |
| result | ¶1 | a `std::meta::info` prvalue; non-null reflections must stay at compile time |
