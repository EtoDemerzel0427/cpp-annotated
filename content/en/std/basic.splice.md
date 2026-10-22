---
title: Splice specifiers
summary: "The C++26 splice [: r :] turns a reflection value back into a program construct (a variable, type, template, namespace, value, …); this subclause specifies what it designates and when a < after [: r :] starts a template argument list."
updated: 2026-10-19
---

!!! tldr
    - `^^x` turns a construct of the program into a value of type `std::meta::info`; `[: r :]` goes the other way, turning that value back into a construct placed at some position in the source code.
    - The `r` in `[: r :]` must be a constant expression. Even in a `consteval` function, a function parameter does not qualify; to splice per argument, pass the reflection value as a template argument.
    - Splicing an alias yields the entity behind it: `[:^^I:]` is `int`.
    - A `<` after `[: r :]` is less-than by default; it starts a template argument list only if `template` or `typename` precedes, or the splice is in a position where only a type can appear.

## Reflection and splicing

{{c++26}} Static reflection ([[P2996R13]]) adds two operations to C++ that go in opposite directions:

- **Reflect**: `^^x` turns a construct such as a variable, function, type, template or namespace into a value of type `std::meta::info` ([[expr.reflect]]). The value can be passed around during constant evaluation, stored in containers, or queried with metafunctions like `std::meta::members_of`.
- **Splice**: `[: r :]` turns a constant `std::meta::info` value back into a construct, which appears at some position in the source code as an expression, type, template name, namespace name, or `X::` prefix.

```cpp
struct S { static constexpr int a = 1; using type = int; };

constexpr auto r = ^^S;               // reflect: r has type std::meta::info
constexpr int c = [:r:]::a;           // splice: [:r:] is S, c == 1
typename [:^^S::type:] *p = nullptr;  // splice a type: p is int*
```

In C++23 and earlier, there was no way to turn information about the program back into the program itself. Types could be passed back and forth as template arguments, but functions, members and namespaces could not; only macros could help. Without splicing, reflection could only be used to inspect, not to generate code.

!!! warning "Compiler support"
    At the time of writing, released versions of the major compilers (including Clang 23) do not support static reflection and have no `<meta>` header. Experimental implementations exist, for example an experimental branch based on Clang. The examples below are judged by the standard draft, were not compiled locally, and have no run button.

## Grammar

```text
splice-specifier:
    [: constant-expression :]

splice-specialization-specifier:
    splice-specifier < template-argument-list(opt) >
```

`[:` and `:]` are two new tokens ([[lex.operators]]), spelled this way to distinguish them from array subscripts `[ ]`, attributes `[[ ]]` and lambda introducers `[ ]`.

This subclause only defines these two grammar units and what they designate. Their specific uses in expressions, types and `X::` prefixes are specified by [[expr.prim.splice]], [[dcl.type.splice]], [[expr.prim.id.qual]] and [[temp.names]] respectively; there is a summary table near the end.

## What a splice designates (¶1)

¶1 The expression in `[: … :]` must be a **converted constant expression** ([[expr.const.const]]) of type `std::meta::info`, that is, an expression that can be evaluated at compile time after implicit conversion to `std::meta::info`. If the value represents a construct `X`, the splice-specifier **designates**:

- ¶1.1 the underlying entity of `X`, if `X` is an entity ([[basic.pre#8]]);
- ¶1.2 `X` itself otherwise.

Three points in this paragraph are worth expanding.

### It must be a constant expression

Splicing happens at compile time, and the compiler has to decide from it whether this piece of source is a variable, type or template, so the reflection value must be known at translation time.

```cpp
consteval int bad_splice(std::meta::info v) {
    return [:v:];          // error: v is a function parameter, not a constant expression
}

template<std::meta::info R>
consteval int good_splice() {
    return [:R:];          // OK: R is a template parameter; each specialization determines what [:R:] is
}
```

`bad_splice` is a `consteval` function, and every call happens at compile time, but its parameter is still not a constant expression within the function body. The body is analyzed once, and it cannot decide per argument whether `[:v:]` is a variable or an enumerator. Passing the reflection value as a template argument instantiates each specialization separately, which solves the problem.

### An alias splices back to its underlying entity

`^^I` (where `I` is an alias defined by `using I = int;`) represents the alias itself. An alias is an entity in its own right; reflection can tell `I` and `int` apart, and only `std::meta::dealias` turns it back into `int`. But when spliced back, by ¶1.1, `[:^^I:]` designates the underlying entity `int`. This is consistent with the rule for names: [[basic.pre#8]] says a name denotes the underlying entity of the entity it declares, and a splice behaves as if a name had been written.

### Non-entities can be spliced too

Besides entities, a reflection value can represent values (`std::meta::reflect_constant(42)`), objects, direct base class relationships, descriptions of non-static data members, annotations, and so on ([[basic.fundamental]]). By ¶1.2, splicing such a construct designates the construct itself. For example, [[expr.prim.splice]] specifies that splicing a value yields a prvalue computing that value, and splicing a direct base class relationship (D, B) yields an lvalue of type B.

Note 1 points out that if the constant expression is value-dependent (its value depends on template parameters), the splice-specifier is dependent ([[temp.dep.splice]]). What `[:R:]` designates in a template is only known at instantiation, so, as with dependent names, `typename` and `template` are needed for disambiguation.

## Splicing into a template specialization (¶2)

¶2 In `[: r :]<args>`, a `[: r :]` that does not depend on template parameters must designate a template (a class template, function template, variable template, alias template or concept). Together with the argument list it forms a specialization of that template, as if the reflection value were used as a template name.

## When `<` starts a template argument list (¶3)

¶3 Note 2 explains that a `<` after `[: r :]` starts a template argument list only in these two cases:

- it is preceded by the keyword `template` or `typename`;
- the splice appears in a **type-only context**, that is, a position where only a type can appear, such as the right side of an alias declaration `using A = …;` ([[temp.res.general]]).

Otherwise `<` is the less-than operator.

This is a new form of an old problem. What `[:r:]` designates may only be known at instantiation, or may require evaluating a constant expression first, while the parser has to decide on the spot what `<` means. The standard takes the same approach as for dependent names: by default it is less-than, and when a template argument list is needed the programmer writes `template` or `typename` (compare the rule for `t.template foo<int>()` in [[temp.res]]). In a type-only context only a type is possible, there is no ambiguity, and the keyword can be omitted.

Example 1 in the standard:

```cpp
constexpr int v = 1;
template<int V> struct TCls {
    static constexpr int s = V + 1;
};

using alias = [:^^TCls:]<([:^^v:])>;
    // OK: the right side of an alias declaration is a type-only context, so < starts a template argument list;
    //     the template argument ([:^^v:]) is a parenthesized splice expression
static_assert(alias::s == 2);

auto o1 = [:^^TCls:]<([:^^v:])>();            // error: this < is less-than
auto o2 = typename [:^^TCls:]<([:^^v:])>();   // OK: o2 is an object of type TCls<1>
```

On the `o1` line, `[:^^TCls:]` is in an expression position and `<` is taken as less-than, but a class template cannot be an operand of a comparison, so it is ill-formed.

A splice expression used as a template argument must be parenthesized: `TCls<[:^^v:]>` is wrong; write `TCls<([:^^v:])>` ([[expr.prim.splice#1]]). In a template argument position, an unparenthesized `[:^^v:]` could also be read as a type or template; the parentheses settle that it is an expression.

## Uses of splices in various places

| Form | Can designate | Specified in | Example |
|---|---|---|---|
| `[: r :]` (splice expression) | variables, functions, enumerators, values, non-static data members, structured bindings, … | [[expr.prim.splice]] | `int n = [:^^x:];` |
| `template [: r :]<...>` | function templates and their specializations | [[expr.prim.splice]] | `template [:^^f:]<int>(0)` |
| `typename [: r :]` | types, class templates, alias templates | [[dcl.type.splice]] | `typename [:^^int:] i = 0;` |
| `[: r :]::` | classes, namespaces, enumerations | [[expr.prim.id.qual]] | `[:^^S:]::a` |
| `namespace A = [: r :];` | namespaces | [[namespace.alias]] | |
| `using namespace [: r :];` | namespaces | [[namespace.udir]] | |
| template arguments | types, templates, values | [[temp.arg.general]] | `std::vector<typename [:t:]>` |

```cpp
struct S { static constexpr int a = 1; using type = int; };

constexpr int c = [:^^S:]::a;          // OK: [:^^S:]:: is an X:: prefix, not an expression
void fn() {
    typename [:^^S::type:] *p;         // OK: declares a variable of type int*
    [:^^S::type:] *q;                  // error: neither in a type-only context nor preceded by typename,
                                       //        so [:^^S::type:] is treated as an expression
}
using T = [:^^S::type:];               // OK: type-only context
```

## Relation to the ODR, linkage and access control

Splicing designates entities without going through names, so every rule in the standard that relied on "referring by name" was extended to cover splices:

- [[basic.def.odr#3]]: a splice expression, like an ordinary name expression, forms the potential results of an expression; [[basic.def.odr#5]]: a variable designated by a splice expression likewise counts as named and can be odr-used.
- [[basic.def.odr#16]]: in definitions of the same entity in several translation units, corresponding reflect expressions must compute equivalent values (¶16.12).
- [[basic.link#13]]: a declaration whose splice-specifier designates an entity counts as naming it. This affects whether translation-unit-local entities are exposed: a module interface cannot leak an entity with internal linkage through a splice.
- [[class.access.base#5]]: a member designated by a splice expression is always accessible. Whether a reflection of a private member can be obtained is guarded by the `access_context` parameter of the reflection query functions.

!!! impl
    - When the parser sees `[:`, it needs to know whether constant evaluation is required before going on. A splice that does not depend on template parameters is evaluated immediately during parsing; a dependent splice, like a dependent name, is deferred to instantiation.
    - Splicing involves no name lookup: `[:^^x:]` does not look up `x` again but uses the declaration or entity recorded in the reflection value directly, so it can designate a hidden declaration.
    - `std::meta::info` is a type that can only exist during constant evaluation and never appears at run time. But it can appear as a template argument in specializations, so corresponding name mangling rules are needed; that is work for the ABI specifications.

!!! history "History"
    The main static reflection proposal, [[P2996R13]], was merged into the C++26 working draft in 2025. In early revisions the reflection operator was spelled `^`; it was changed to `^^` because `^` conflicts with Clang's blocks extension (closure syntax in Objective-C and C/C++). C++23 and earlier had no splicing; the closest approaches were passing types as template arguments or pasting tokens with macros.

## Common misconceptions

!!! pitfall "A consteval function's parameters are constant expressions"
    `consteval void f(std::meta::info r) { [:r:]; }` is wrong. The right approach is to put the reflection value in a template parameter, `template<std::meta::info R> consteval void f() { [:R:]; }`, or to use an expansion statement `template for (constexpr auto m : …)` ([[stmt.expand]]), where the loop variable is a constant in each expansion.

!!! pitfall "`[:r:]<int>` is always a template specialization"
    In an expression, `<` is less-than by default. Write `template [:r:]<int>` or `typename [:r:]<int>`.

## Questions

!!! question "Question"
    Given `using I = int; constexpr auto r = ^^I;`, is `r == ^^int`? What type is `typename [:r:]`?

<details markdown="1">
<summary>Answer</summary>

`r == ^^int` is false. `^^I` represents the type alias `I` itself as an entity ([[basic.pre#8]] lists type aliases as entities, whose underlying entity is `int`), which is not the same reflection value as `^^int`; `std::meta::dealias(r) == ^^int` is true.

`typename [:r:]` is `int`, because by ¶1.1 a splice-specifier designates the underlying entity of an entity.
</details>
