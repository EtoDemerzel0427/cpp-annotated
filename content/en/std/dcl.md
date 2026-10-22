---
title: Declarations
summary: "A guide to Chapter 9: a declaration consists of specifiers, declarators and initializers; specifiers apply to the whole declaration, a declarator to one name; what each subclause covers."
updated: 2026-10-19
---

!!! tldr
    - An ordinary declaration has three parts: a specifier sequence, declarators and initializers. In `int* a, b;`, `b` is not a pointer, because `*` belongs to the declarator `*a`, not to the specifier `int`.
    - Specifiers (`static`, `constexpr`, `unsigned long`, and so on) apply to every name in the declaration; declarators (`*`, `&`, `[3]`, `(int)`) apply only to their own name.
    - A variable's type starts from the base type given by the type specifiers and is then wrapped layer by layer by the declarator; specifiers such as `static` and `inline` don't affect the type.
    - 9.1–9.6 are the general machinery of declarations (specifiers, declarators, initialization, function definitions); 9.7–9.13 are the special forms: structured bindings, enumerations, namespaces, `using`, `asm`, linkage specifications and attributes.

Chapter 6 ([[basic.pre]], [[basic.def]]) defines the concepts of name, entity, declaration and definition. Chapter 9 gives the concrete syntax of declarations, and the rules that derive from that syntax the type, storage duration, linkage, and whether something is inline or constexpr.

## The three parts of a declaration

```cpp run ok
#include <type_traits>
int* a, b;             // a is int*, b is int
typedef int* IP;
IP c, d;               // c and d are both int*: the pointer comes from the specifier IP
static_assert(std::is_same_v<decltype(b), int>);
static_assert(std::is_same_v<decltype(d), int*>);
int main() { }
```

The most common declaration is the *simple-declaration*, which has three parts ([[dcl.pre#4]]):

```text
[[attrs]]  static constexpr unsigned long   *const p = nullptr, a[3] = {};
└ attrs ┘  └──── decl-specifier-seq ────┘   └──── init-declarator-list ────┘
                                              declarators with their initializers, comma-separated
```

- **Specifiers** (*decl-specifier*, 9.2) apply to every name in the declaration, e.g. `static`, `constexpr` and the type specifier `unsigned long`.
- A **declarator** (*declarator*, [[g:declarator]], 9.3) applies to one name only: `*const` belongs only to `p`, `[3]` only to `a`.
- An **initializer** (*initializer*, 9.5) follows its own declarator.

The type is obtained in two steps: the type specifiers in the specifier sequence give a base type, and the declarator then wraps it layer by layer, from the name outward ([[dcl.meaning]]). In the example above, `p` is `unsigned long* const` and `a` is `const unsigned long[3]` (`constexpr` makes the object const). The parts of the specifier sequence that don't denote types, such as `static`, `inline` and `constexpr`, determine properties like storage duration and linkage and take no part in the wrapping structure of the type.

The order of specifiers is free: the grammar of *decl-specifier-seq* is just a sequence of any specifiers, so `int const static x = 0;` is valid; multi-word types such as `unsigned long` can also be interleaved with other specifiers, so `long static unsigned long y = 0;` is valid too ([[dcl.type.simple#4]]). Only one rule depends on order: when a type name appears in the specifier sequence, whether it counts as a specifier or as the name being declared ([[dcl.spec.general#3]]).

## Why specifiers and declarators are separate layers

This grammar is inherited from C, whose design principle is that declaration mirrors use: `int *p[3];` reads as "the expression `*p[i]` has type `int`". Declarator syntax is isomorphic to expression syntax, with the same precedence: the postfix `[]` and `()` bind tighter than the prefix `*`. This has three consequences:

1. When one declaration declares several names, the pointer, reference, array and function modifiers belong only to their own name;
2. Types such as pointers to functions and pointers to arrays need parentheses to change the binding, as in `int (*fp)(int);`;
3. The grammar produces many ambiguities, which [[stmt.ambig]] and [[dcl.ambig.res]] resolve on the principle that anything that can be read as a declaration is a declaration.

C++ added many specifiers to this machinery: `constexpr`, `consteval`, `constinit`, `inline`, `friend`, `explicit`, the placeholder types `auto` and `decltype(auto)`, template names used for CTAD, and so on. All of them go in the specifier sequence and apply to the whole declaration.

## The subclauses of this chapter

| Subclause | Contents | Page on this site |
|---|---|---|
| 9.1 | General declaration syntax; `static_assert`, `consteval` blocks, empty declarations, attribute declarations | [[dcl.pre]] |
| 9.2 | Specifiers: storage class, function specifiers, `typedef`, `friend`, `constexpr`/`consteval`, `constinit`, `inline`, the various type specifiers | [[dcl.spec]] and its subpages |
| 9.3 | Declarators: pointers, references, pointers to members, arrays, functions, default arguments; type names; ambiguity resolution | [[dcl.decl]] |
| 9.4 | {{c++26}} Function contract specifiers `pre` and `post` | [[dcl.contract]] |
| 9.5 | Initialization: default, value and zero initialization, aggregate initialization, reference binding, list-initialization | [[dcl.init]] |
| 9.6 | Function definitions: `= default`, `= delete`, coroutines | [[dcl.fct.def]] |
| 9.7 | Structured bindings | [[dcl.struct.bind]] |
| 9.8 | Enumerations and `using enum` | [[dcl.enum]], [[enum.udecl]] |
| 9.9 | Namespaces, unnamed namespaces, namespace aliases, using-directives | [[basic.namespace]] |
| 9.10 | The using-declaration | [[namespace.udecl]] |
| 9.11 | The `asm` declaration | [[dcl.asm]] |
| 9.12 | Linkage specifications `extern "C"` | [[dcl.link]] |
| 9.13 | Attributes | [[dcl.attr]] |

How the work is split with other chapters: a class definition is syntactically a type specifier, but its content is in Chapter 11, [[class]]; template declarations are in Chapter 13, [[temp]], and this chapter's placeholder type deduction ([[dcl.type.auto.deduct]]) borrows template argument deduction; `export` and `import` are in Chapter 10, [[module]]; when a variable is initialized (static or dynamic initialization) is in [[basic.start]], while 9.5 only specifies with what value and how it is initialized.

## Reading order

1. [[dcl.pre]]: the general declaration syntax and `static_assert`.
2. [[dcl.spec]], [[dcl.type]]: how specifiers combine, and when a type name is the name being declared.
3. Read [[dcl.stc]], [[dcl.inline]], [[dcl.constexpr]] and [[dcl.constinit]] as needed: they determine storage duration, linkage, ODR behavior, and whether variables and functions can be used in constant evaluation.
4. [[dcl.type.decltype]], [[dcl.spec.auto]], [[dcl.type.class.deduct]]: the three type deduction mechanisms.
5. [[dcl.decl]] and [[dcl.init]].
