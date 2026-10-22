---
title: Identifiers
summary: "Which characters can make up an identifier (based on the Unicode XID properties, and it must be in NFC); why final, override, import, module, pre and post are not keywords; and which names are reserved for the implementation (containing a double underscore, underscore followed by an uppercase letter, a leading underscore at global scope)."
updated: 2026-10-19
---

!!! tldr
    - An identifier begins with a letter, `_`, or a character with the Unicode XID_Start property, and may be followed by digits and characters with the XID_Continue property. Chinese characters are allowed; emoji and `$` are not.
    - An identifier must be in Unicode NFC, otherwise the program is ill-formed; Clang 23 does not check this.
    - `final`, `override`, `import`, `module`, `pre` and `post` are identifiers with special meaning: they have a special meaning only in certain positions and can be used as ordinary names elsewhere, but they cannot be defined as macros.
    - Identifiers containing `__` or beginning with `_` followed by an uppercase letter are reserved to the implementation everywhere; identifiers beginning with `_` are reserved in the global namespace. Using them is IFNDR: the program is wrong, but the compiler need not report it.

## Which characters can make up an identifier

```cpp run title="unicode-ident.cpp" ok
int 变量 = 1;               // Chinese characters have the XID_Start property
double \u03C0 = 3.14159;    // π; the same when written with a universal-character-name
int naïve = 2;              // ï is a precomposed character U+00EF
int main() { return 变量 + naïve - 3; }
```

```cpp title="bad-ident.cpp" error
int 😀 = 1;      // error: emoji do not have the XID_Start property
int €uro = 3;    // error: € is a currency symbol, not a letter
int $x = 4;      // error per the standard: $ is not a letter and has no XID property
```

The grammar of [[lex.name]] is:

```
identifier:
    identifier-start
    identifier identifier-continue
identifier-start:
    nondigit
    an element of the translation character set with the Unicode property XID_Start
        or the Unicode property ID_Compat_Math_Start
identifier-continue:
    digit
    nondigit
    an element of the translation character set with the Unicode property XID_Continue
        or the Unicode property ID_Compat_Math_Continue
nondigit: one of  a–z  A–Z  _
digit: one of  0–9
```

XID_Start and XID_Continue are properties Unicode assigns to each character (Note 1: see UAX #44). Intuitively, XID_Start covers the letters of the world's scripts, including Chinese characters, Greek letters and Cyrillic letters; XID_Continue adds digits, combining marks, connector punctuation and so on. There are surprises too: the middle dot `·` (U+00B7) has the XID_Continue property, so `int a·b = 2;` declares a variable named `a·b`.

Note 2 says identifiers are case-sensitive. Note 3 says that Annex [[uaxid]] compares, item by item, the Unicode identifier specification UAX #31 with the rules of C++.

Although `$` was added to the basic character set in C++26 ([[lex.charset]]), it is not a *nondigit* and has no XID property, so per the standard it cannot appear in identifiers. GCC, Clang and MSVC all accept it as an extension; Clang gives a `-Wdollar-in-identifier-extension` warning under `-pedantic`.

### Mathematical notation {{c++26}}

Besides XID, the current draft adds the two properties ID_Compat_Math_Start and ID_Compat_Math_Continue, corresponding to the profile for mathematical notation in UAX #31 ([[uaxid.def.general]]). So `∂` (U+2202), `∇` (U+2207) and `∞` (U+221E) can be the first character of an identifier, and the subscript digit `₀` (U+2080) can appear inside an identifier:

```cpp run title="math-ident.cpp" ok
double ∂x = 0.1;
double x₀ = 1.0;
int main() { return ∂x < x₀ ? 0 : 1; }
```

In C++23 these characters cannot appear in identifiers. Clang 23 accepts the example above but warns mathematical notation character in an identifier is a Clang extension; its diagnostics still follow the C++23 rules.

## The NFC requirement (¶1)

!!! std
    The program is ill-formed if an *identifier* does not conform to Normalization Form C as specified in the Unicode Standard.

¶1 An identifier must conform to Unicode **Normalization Form C** (NFC), otherwise the program is ill-formed.

Text with the same appearance can have several encodings in Unicode. `é` can be the precomposed character U+00E9, or `e` followed by the combining acute accent U+0301. Without a normalization requirement, two identifiers that look exactly alike could be two different names. That hurts readability and also causes trouble for linking: different editors may save different bytes, so symbols fail to match ([[diff.cpp20.lex]] gives consistent linker behavior as the rationale).

The standard requires the input itself to be in NFC, rather than having the compiler normalize before comparing. The compiler only has to check, not rewrite, and identifiers with different bytes are always different identifiers.

```cpp title="nfc.cpp" error
int a\u0300 = 1;   // error: a + combining grave accent U+0300 is not NFC; the NFC form is U+00E0 à
int \u212B = 2;    // error: U+212B ANGSTROM SIGN normalizes to U+00C5, so it is not NFC itself
```

Clang 23 does not check NFC; the example above compiles with `-std=c++2c -pedantic` without any diagnostic. This deviates from the standard, since this rule requires a diagnostic. Do not count on the compiler to catch differences in normalization form; normalize to NFC in the editor or in CI instead.

Note 4 says that in phase 4, identifiers also include those preprocessing tokens that are differentiated as keywords only in phase 7. So `new` and `int` can appear in `#if`, where they are treated as ordinary identifiers and replaced by 0 ([[lex.phases]]).

!!! history "From a table of character ranges to UAX #31"
    C++11 through C++20 listed the characters allowed in identifiers in a table of code point ranges in an annex, with another table of characters that could not be the first character. That table was too permissive: many symbols, and even some invisible characters, were allowed. C++23 adopted [[P1949R7]], switching to XID_Start and XID_Continue and requiring NFC. [[diff.cpp20.lex]] records this incompatible change: some formerly valid identifiers, such as those containing emoji, became ill-formed.

## Identifiers with special meaning (¶2, ¶3)

```cpp run title="special-ident.cpp" ok
int final = 0, override = 1, import = 2, module = 3, pre = 4, post = 5;  // ordinary variables
struct Base { virtual void override() {} };      // a function named override
struct D final : Base {                          // final: a class property specifier
  void override() override final {}             // name override, followed by virt-specifiers
};
int main() { return final + override - 1; }
```

¶2 The identifiers in Table 4 have a special meaning when they appear in certain contexts; they are called [[g:identifier-with-special-meaning|identifiers with special meaning]]. When the grammar refers to them, it spells them out directly rather than going through the *identifier* production. Unless otherwise specified, any ambiguity as to whether a given identifier has a special meaning is resolved to interpret the token as a regular identifier.

| Identifier | Introduced | Where it has a special meaning |
|---|---|---|
| `final` | C++11 | class head ([[class.pre]]), the *virt-specifier* of a virtual function declaration ([[class.mem]]) |
| `override` | C++11 | the *virt-specifier* of a virtual function declaration |
| `import` | C++20 | module import declarations and import directives ([[module.import]], [[cpp.import]]) |
| `module` | C++20 | module declarations and module directives ([[module.unit]], [[cpp.module]]) |
| `pre` | C++26 | contract assertions on functions ([[dcl.contract.func]]) |
| `post` | C++26 | contract assertions on functions |

They are not keywords for the sake of compatibility. These words are often used as variable or function names in existing code, and making them keywords would break a great deal of code; the positions where they have a special meaning (after a declarator, after a class name, at the start of a line) are distinctive enough that context decides.

### Exceptions that favor the special meaning

¶2 says that in case of ambiguity the default is to interpret as an ordinary identifier, but in some places the standard specifies otherwise. [[class.pre#5]] says that when a class-key is followed by a class name, then the identifier `final`, then `:` or `{`, the `final` is interpreted as a class property specifier:

```cpp run title="final-ambiguity.cpp" ok
struct A;
struct A final {};        // defines struct A, rather than declaring a variable of type A named final
struct X {
  struct C { constexpr operator int() { return 5; } };
  struct B final : C {};  // defines nested class B, rather than declaring a bit-field named final with width C{}
};
int main() {}
```

`import` and `module` go further: an `import` or `module` (possibly preceded by `export`) at the start of a logical source line forms a preprocessing directive, whose meaning is settled already in phase 4 ([[lex.pptoken#4]]). Hence the incompatibility recorded in [[diff.cpp17.lex]]:

```cpp title="module-break.cpp" error
class module {};
module m1;          // since C++20 this is a module declaration, not a variable declaration
class import {};
import j1;          // since C++20 this is an import declaration
```

Note 5 in ¶3 says identifiers with special meaning cannot be used as macro names ([[cpp.replace.general]]). A `#define override` written for compatibility with old compilers is ill-formed under the current draft. Clang 23 gives a `-Wkeyword-macro` warning for it under `-pedantic`, and no diagnostic by default.

## Reserved identifiers (¶4)

¶4 Some identifiers that appear as a token or preprocessing token are reserved for use by C++ implementations and shall not be used otherwise; they are called [[g:reserved-identifier|reserved identifiers]]. A program that violates this rule is ill-formed, no diagnostic required ({{ifndr}}, [[ifndr.lex]]).

- ¶4.1 Each identifier that contains a double underscore `__` or begins with an underscore followed by an uppercase letter is reserved to the implementation for any use, except those specified by the standard itself, such as `__cplusplus`.
- ¶4.2 Each identifier that begins with an underscore is reserved to the implementation for use as a name in the global namespace.

| Identifier | Global namespace | Other scopes | Macro name | Basis |
|---|---|---|---|---|
| `__x`, `x__y`, `a__` | reserved | reserved | reserved | ¶4.1 |
| `_Foo` | reserved | reserved | reserved | ¶4.1 |
| `_foo` | reserved | usable | disputed, see below | ¶4.2 |
| `foo_` | usable | usable | usable | |

```cpp title="reserved.cpp" ifndr
int _z;                   // IFNDR: begins with _ in the global namespace
namespace N { int _z; }   // OK: not in the global namespace
int main() {
  int __x;                // IFNDR: contains __
  int _Y;                 // IFNDR: _ followed by an uppercase letter
  int x__y;               // IFNDR: contains __, not only at the start
}
```

The example is adapted from [[ifndr.lex]]. Clang provides a `-Wreserved-identifier` warning; it is not in `-Wall -Wextra` and has to be enabled separately.

Why is no diagnostic required? The implementation itself needs these names: `_Tp`, `__first` and `_M_impl` in standard library headers, compiler built-ins such as `__builtin_expect`, and all sorts of `_GLIBCXX_...` macros. The compiler must let headers use reserved names, and it is hard to tell reliably whether a name comes from a system header or from user code (macro expansion and nested `#include`s make that distinction unreliable). When users use a reserved name, the typical consequence is a clash with some macro or declaration of the implementation, producing baffling errors.

The qualifier "appear as a token" is precise. A `__x` in a string literal or a comment does not count. Nor does the suffix of a user-defined literal, because `""_Bq` is one token and `_Bq` does not appear as a token on its own. The example in [[over.literal]] is exactly this distinction:

```cpp title="udl-reserved.cpp" ifndr
double operator""_Bq(long double);    // OK: _Bq is not a separate token
double operator"" _Bq(long double);   // IFNDR: _Bq appears as an identifier token, _ followed by an uppercase letter
                                      // this spelling with a space is itself deprecated, see lex.ext
```

!!! lawyer "Macro names beginning with `_lowercase`"
    ¶4.2 only says identifiers beginning with `_` are reserved as names in the global namespace, and macro names belong to no namespace, so whether `#define _foo 1` violates ¶4 is disputed. The practical harm is the same: the implementation may declare `_foo` in the global namespace, and your macro will replace it. The safe practice is for no macro name to begin with an underscore.

[[lex.name]] specifies only language-level reservations. The standard library has its own set of reservation rules ([[reserved.names]]), covering the namespaces `std` and `posix`, names declared in standard library headers, attribute tokens, names removed from the standard library, literal suffixes not beginning with `_` ([[usrlit.suffix]]), and so on.

<details class="fine" markdown="1"><summary>Remaining wording</summary>

Footnote 11: on systems in which linkers cannot accept extended characters, an encoding of the universal-character-name can be used in forming valid external identifiers; C++ places no limit on the number of significant characters in external identifiers. In practice, GCC and Clang (Itanium ABI) use the UTF-8 bytes of the identifier directly in mangled names.

</details>

## Common misconceptions

!!! pitfall "Header guard macros using reserved names"
    `#ifndef _MY_HEADER_H_` and `#define __UTILS_H__` are common, but both are reserved identifiers: the first begins with an underscore followed by an uppercase letter, the second contains `__`. Change them to `MY_HEADER_H`.

!!! pitfall "Only a leading double underscore is reserved"
    A double underscore is reserved in any position, `x__y` included. Watch out for this too when pasting names with macros (`a ## __ ## b`).

!!! pitfall "Unicode identifiers are what you see"
    Identifiers that look the same but differ in normalization form, and identifiers that use different letters of the same shape (Latin `a` and Cyrillic `а`), are different names. The NFC requirement deals with the former (and compilers may not check it); the standard does nothing about the latter.

## Questions

!!! question "Question 1"
    Which of the following declarations violate [[lex.name#4]]?

    ```cpp
    namespace detail { int _impl; }           // (1)
    struct S { int _Size; };                  // (2)
    void f(int _) {}                          // (3)
    #define my__macro 1                       // (4)
    int operator""_Km(unsigned long long);    // (5)
    ```

<details markdown="1">
<summary>Answer</summary>

1. No: `_impl` is not in the global namespace.
2. Yes (IFNDR): `_Size` begins with an underscore followed by an uppercase letter, which is reserved in every scope, class members included.
3. No: a function parameter is not in the global namespace.
4. Yes: it contains `__`, which ¶4.1 reserves for any use, macro names included.
5. No: `""_Km` is one token, and `_Km` does not appear as a token on its own; literal suffixes beginning with `_` are exactly the ones left to users ([[usrlit.suffix]]).
</details>

!!! question "Question 2"
    Ambiguities about identifiers with special meaning default to the ordinary-identifier reading, so why does [[class.pre#5]] specifically give `final` in `struct A final {` its special meaning?

<details markdown="1">
<summary>Answer</summary>

Defaulting to an ordinary identifier is for compatibility: code that was valid before `final` was introduced should keep its meaning afterwards.

If `struct A final {}` and `struct B final : C {}` were read with ordinary identifiers, the former would be a variable `final` initialized with braces and the latter a bit-field `final` of width `C{}`; both need brace initialization. Brace initialization and `final` were both introduced in C++11; before that, neither form was valid at all, so there is no old code whose meaning would change. Favoring the special meaning here does not break compatibility, and it matches the common way of writing a `final` class.
</details>
