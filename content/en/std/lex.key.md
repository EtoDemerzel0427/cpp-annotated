---
title: Keywords
summary: "The 82 spellings reserved as keywords (C++26 adds contract_assert), the three placeholder keywords of module directives, the exception for attribute tokens, and the word-form operators such as and and or that likewise cannot be used as names."
updated: 2026-10-19
---

!!! tldr
    - The 82 spellings listed in Table 5 are always keywords after phase 6 and cannot be used as any name; the only exception is attribute tokens, such as the `const` in `[[gnu::const]]`.
    - There are no keywords yet during preprocessing, so the `new` in `#if new` is just an identifier with value 0.
    - Keywords cannot be defined as macros; `#define private public` is ill-formed.
    - `override`, `final`, `pre` and `post` are not keywords but identifiers with special meaning; `and`, `or` and the like are not keywords either but operator tokens, and likewise cannot be used as names.

## From which phase keywords exist

```cpp run title="if-keyword.cpp" ok
#if int == 0 && new == 0     // during preprocessing int and new are just identifiers, with value 0
int ok = 1;
#endif
int main() { return ok - 1; }
```

In phases 3 to 5, keywords and identifiers are all identifier preprocessing tokens; only when they are converted into tokens in phase 6 do the spellings in Table 5 become [[g:keyword|keywords]] ([[lex.phases]]). So `int` and `new` in `#if` are replaced by 0 like any other identifier.

The grammar of [[lex.key]] is:

```
keyword:
    any identifier listed in Table 5
    import-keyword
    module-keyword
    export-keyword
```

The last three are placeholder tokens produced when the preprocessor handles `import` and `module` directives; they have no spelling ([[lex.pptoken#4]], [[cpp.import]], [[cpp.module]]). With them, the grammar can distinguish an `import` that begins a module directive from an ordinary identifier named `import`. `export` is also an ordinary keyword in Table 5; *export-keyword* refers specifically to the `export` that begins a module directive.

## The keywords in Table 5 (¶1)

¶1 The identifiers in Table 5 are reserved for use as keywords, that is, they are unconditionally treated as keywords in phases 6 and 7, except in an *attribute-token*. Note 1: the `register` keyword is unused but is reserved for future use.

The current draft has 82 keywords:

```
alignas      alignof      asm          auto         bool         break
case         catch        char         char8_t      char16_t     char32_t
class        co_await     co_return    co_yield     concept      const
const_cast   consteval    constexpr    constinit    continue     contract_assert
decltype     default      delete       do           double       dynamic_cast
else         enum         explicit     export       extern       false
float        for          friend       goto         if           inline
int          long         mutable      namespace    new          noexcept
nullptr      operator     private      protected    public       register
reinterpret_cast          requires     return       short        signed
sizeof       static       static_assert             static_cast  struct
switch       template     this         thread_local throw        true
try          typedef      typeid       typename     union        unsigned
using        virtual      void         volatile     wchar_t      while
```

The following are not in the table, but are often taken for keywords:

| Spelling | What it actually is |
|---|---|
| `override`, `final`, `import`, `module`, `pre`, `post` | identifiers with special meaning ([[lex.name#2]]) |
| `and`, `or`, `not`, `bitand`, `compl`, etc. | alternative tokens, which are operators and punctuators ([[lex.digraph]], ¶3) |
| `main` | an ordinary identifier with dedicated rules ([[basic.start.main]]) |
| `std` | an ordinary identifier, subject to the standard library's reservation rules |
| `size_t`, `nullptr_t`, `int8_t` | type aliases in the standard library |
| `restrict`, `_Bool`, `_Atomic`, `typeof` | C keywords, absent from C++ |
| `__restrict`, `__attribute__`, `__declspec` | implementation extensions, using reserved identifiers ([[lex.name#4]]) |

### Keywords cannot be used as names

Being unconditionally treated as keywords means keywords cannot be used as names even in positions where no ambiguity would arise:

```cpp title="keyword-as-name.cpp" error
struct S { int class; };      // error: class is a keyword
int contract_assert = 0;      // error (C++26): contract_assert is a keyword
void f(int new);              // error
```

Clang 23 does not yet recognize `contract_assert` as a keyword, so the second line compiles; that is a matter of implementation progress. Identifiers with special meaning are different: outside their particular positions they are ordinary identifiers.

### Exception: attribute tokens

Keywords in an attribute token are not treated as keywords, for example the `const` in `gnu::const`. [[dcl.attr.grammar]] further specifies that a keyword or alternative token in an attribute token that satisfies the syntactic requirements of an identifier is considered an identifier.

```cpp run title="attr-keyword.cpp" ok
[[gnu::const]] int square(int x);      // const is an identifier here
[[gnu::noreturn]] void die();
int main() {}
```

The names of vendor attributes often come from existing compiler extensions, many of which share names with keywords; and the position of an attribute name is unambiguous, so this is allowed.

### `register`: unused but reserved

C++11 deprecated the `register` storage class specifier and C++17 removed it, so `register int x;` has been ill-formed since. But `register` is still in the keyword table, so it can be given a new meaning in the future without breaking existing code. `auto` (repurposed for type deduction in C++11) and `export` (exported templates removed in C++11, reused for modules in C++20) both went down this path.

```cpp title="register.cpp" error
void f() {
  register int x = 0;   // error (since C++17): register is no longer a storage class specifier
}
```

## Keywords cannot be defined as macros (¶2)

Note 2 in ¶2 says keywords cannot be used as macro names ([[cpp.replace.general]]).

```cpp title="keyword-macro.cpp" error
#define private public    // error: the macro name is the same as a keyword
class A { private: int secret = 1; };
int peek(A& a) { return a.secret; }
```

The normative basis is [[cpp.replace.general#9]]: a translation unit shall not `#define` or `#undef` macro names lexically identical to keywords, to identifiers with special meaning, or to standard attribute names, except that `likely` and `unlikely` may be defined as function-like macros. In C++23 this rule was in the library clause [[macro.names]]; the current draft moved it to the preprocessing clause, where it is an ordinary rule whose violation must be diagnosed. Clang 23 gives a `-Wkeyword-macro` warning only under `-pedantic`; in the default mode it gives no diagnostic and compiles the code anyway.

`#define private public` used to be a common trick for test code to reach private members. Its problem is not just bypassing access control: the class definition this translation unit sees has a different token sequence from the other translation units, violating the ODR ([[basic.def.odr]]); and before C++23 the relative order in memory of members with different access control was unspecified, so replacing `private` with `public` could actually change the layout of the class. More generally, redefining keywords makes the behavior of standard library headers unpredictable.

## Word-form operators are reserved too (¶3)

¶3 The alternative representations of certain operators and punctuators in Table 6 ([[lex.digraph]]) are likewise reserved and shall not be used otherwise:

```
and     and_eq    bitand    bitor    compl    not
not_eq  or        or_eq     xor      xor_eq
```

They are not in Table 5 and are not keywords but operator or punctuator tokens; in effect, though, like keywords, they cannot be used as names.

## History and evolution

!!! history
    | Version | Keywords added |
    |---|---|
    | C++98 | The base set, including `export`, `register` and `auto` with their old meanings |
    | C++11 | `alignas` `alignof` `char16_t` `char32_t` `constexpr` `decltype` `noexcept` `nullptr` `static_assert` `thread_local` ([[diff.cpp03.lex]]) |
    | C++20 | `char8_t` `concept` `consteval` `constinit` `co_await` `co_yield` `co_return` `requires` ([[diff.cpp17.lex]]) |
    | C++26 | `contract_assert` ([[diff.cpp23.lex]]; for contracts see [[P2900R14]]) |

    Keywords whose meaning changed without being removed: `auto` (from a storage class specifier to type deduction in C++11), `export` (exported templates removed in C++11, used for modules in C++20), `register` (storage class specifier removed in C++17, spelling kept).

    The assertion statement is not called `assert` because `assert` is a macro in `<cassert>` and cannot become a keyword.

## Common misconceptions

!!! pitfall "Variable names in C code"
    C code often uses `new`, `class`, `template`, `this`, `delete` and `private` as variable names or struct member names, and such code fails to compile as C++ ([[diff.lex]]). C headers meant to be used from C++ must avoid these names.

!!! pitfall "`override` is a keyword and `and` is an ordinary name"
    It is exactly the opposite. `int override = 0;` is perfectly valid, while `struct S { int and; };` is ill-formed.

## Questions

!!! question "Question"
    Why do C++26 contracts make the assertion statement the keyword `contract_assert`, but the preconditions and postconditions the identifiers with special meaning `pre` and `post`?

<details markdown="1">
<summary>Answer</summary>

`pre` and `post` appear after a function declarator, as in `int f(int x) pre(x > 0);`. Only a few things could appear in that position before, such as `override`, `final`, `noexcept`, `requires`, `= 0` and `{`, so context is enough to recognize them; they can be identifiers with special meaning without breaking existing variables named `pre` or `post`.

An assertion statement appears in statement position, where `name(expr);` is already a valid function call statement, so context cannot tell them apart and only a keyword will do. To avoid clashing with existing code and with the `assert` macro from `<cassert>`, a spelling unlikely to be used as a name was chosen: `contract_assert`.
</details>
