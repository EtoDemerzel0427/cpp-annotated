---
title: Alternative tokens
summary: "The digraphs <% %> <: :> %: %:%: and the word forms and, or, not, bitand, compl and so on are identical to the corresponding operators and punctuators in everything but spelling."
updated: 2026-10-19
---

!!! tldr
    - `<%` `%>` `<:` `:>` `%:` `%:%:` and the 11 words `and`, `or`, `not`, `bitand`, `compl` and so on are alternative spellings of certain operators and punctuators.
    - An alternative token is the same as its corresponding token in every respect of the language; only stringizing keeps the original spelling.
    - `and` is the token `&&`, so `int and r = 1;` declares an rvalue reference, and `compl X()` is a destructor.
    - The word forms are neither identifiers nor keywords; they cannot be used as variable names, nor defined as macros.

## Not only logical operations

```cpp run title="alt-everywhere.cpp" ok
struct X {
  X() = default;
  compl X() {}               // ~X(): destructor
  void f() bitand {}         // void f() &: lvalue-ref-qualified member function
  void g() and {}            // void g() &&: rvalue-ref-qualified
};
int x = 0;
int bitand r = x;            // int& r: lvalue reference
int and rr = 1;              // int&& rr: rvalue reference
int* p = bitand x;           // &x: address-of
bool b = not x or x not_eq 0;
int main() <%
  X{}.g();
  int a<:2:> = <%1, 2%>;
  return a<:0:> xor 1;       // 1 ^ 1 == 0
%>
```

All of this code is well-formed; Clang 23 compiles it with `-Wall -Wextra -pedantic` without any diagnostic. `and` does not mean the logical AND operation; it is the token `&&`, so `and` can be written wherever the grammar allows `&&`, including reference declarations and ref-qualifiers.

¶1 Alternative token representations ([[g:alternative-token|alternative tokens]]) are provided for some operators and punctuators. They were originally meant for keyboards and character sets lacking characters such as `{ } [ ] # | ^ ~` (for example, some national variants of ISO 646). Today almost nobody uses them because of their keyboard, but they are still part of the language.

Footnote 10 says the name digraph is not quite accurate, since `%:%:` has four characters and many ordinary tokens are themselves two characters; but by convention the alternative tokens that are not lexical keywords are called digraphs.

## Only the spelling differs (¶2)

!!! std
    In all respects of the language, each alternative token behaves the same, respectively, as its primary token, except for its spelling.

¶2 Each alternative token is the same as its corresponding **primary token** in every respect of the language, except for its spelling. The full correspondence is Table 3:

| Alternative | Primary | Alternative | Primary | Alternative | Primary |
|---|---|---|---|---|---|
| `<%` | `{` | `and` | `&&` | `and_eq` | `&=` |
| `%>` | `}` | `bitor` | `|` | `or_eq` | `|=` |
| `<:` | `[` | `or` | `||` | `xor_eq` | `^=` |
| `:>` | `]` | `xor` | `^` | `not` | `!` |
| `%:` | `#` | `compl` | `~` | `not_eq` | `!=` |
| `%:%:` | `##` | `bitand` | `&` | | |

Note 1 points out the only place where a difference can be seen: stringizing ([[cpp.stringize]]) keeps the spelling in the source, so `[` and `<:` stringize differently.

```cpp run title="stringize.cpp" ok
#define S(t) #t
static_assert(S(<:)[0] == '<');   // "<:"
static_assert(S([)[0] == '[');    // "["
static_assert(S(and)[0] == 'a');  // "and"
int main() {}
```

The same goes for `%:` and `%:%:`: `%:` can introduce a preprocessing directive at the start of a line and stringize in a macro definition; `%:%:` can paste tokens.

```cpp run title="percent-colon.cpp" ok
%:include <cstdio>
%:define CAT(a, b) a %:%: b
%:define STR(x) %:x
int main() { std::puts(STR(CAT(he, llo))); }   // prints CAT(he, llo): # does not expand its argument
```

## The word forms are not identifiers

[[lex.key#3]] says that `and`, `and_eq`, `bitand`, `bitor`, `compl`, `not`, `not_eq`, `or`, `or_eq`, `xor` and `xor_eq` are reserved and shall not be used otherwise. They are split as operators or punctuators already in phase 3 ([[lex.operators]]), not as identifiers. So:

- they cannot be used as any name, such as a variable or function name;
- they cannot be defined as macros. `#define` requires an identifier after it, and Note 1 in [[cpp.replace.general]] says that alternative tokens are not identifiers even when they consist only of letters and underscores;
- they can appear anywhere their primary tokens can; for example, `operator and` and `operator&&` are the same function name.

```cpp title="alt-macro.cpp" error
#define and &&     // error: and is not an identifier and cannot be a macro name
int not = 0;       // error: not is not an identifier
```

For the first line, Clang 23 reports C++ operator 'and' (aka '&&') used as a macro name.

Footnote 10 calls the word forms lexical keywords, and [[diff.header.iso646.h]] also says they are keywords in C++. But they are not in the table of keywords ([[lex.key]] Table 5); grammatically they belong to *operator-or-punctuator*. In effect, like keywords, they cannot be used as names.

## Relationship with C

In C, `and`, `or` and so on are macros defined by `<iso646.h>`; in C++ they are tokens, and `<iso646.h>` defines nothing. C++20 removed `<ciso646>`. That header used to be included as the smallest standard library header in order to get the library's version macros; that use is now taken over by `<version>`. The digraphs `<% %> <: :> %: %:%:` are tokens in C as well.

!!! impl
    GCC and Clang recognize the word forms in all standard modes. MSVC historically did not recognize `and`, `or` and so on by default, requiring `<iso646.h>` to get the macros, and handles them per the standard only in conformance mode. Cross-compiler code that uses them should check which mode MSVC is in.

## Trigraphs: a third spelling, now removed

C++14 and earlier also had 9 trigraphs, such as `??=`, `??/` and `??!`. They differ fundamentally from alternative tokens. Trigraphs were a pure character replacement in phase 1 that took effect inside string literals and comments too; alternative tokens are tokens of phase 3 and have no special meaning inside literals. The reach of trigraph replacement was too wide, turning `"what??!"` into `"what|"`, so C++17 removed it ([[N4086]], see [[lex.phases]]), while alternative tokens were kept.

## Common misconceptions

!!! pitfall "`and` can only be used for logical operations"
    `int and x = 1;` declares an rvalue reference. When `bitand` or `compl` shows up in an odd place in code, it is not necessarily a typo.

!!! pitfall "`<::` is always taken as `[:`"
    In C++03, `std::vector<::std::string>` was split as `vector [ :std::string >`, and had to be written `< ::std`. C++11 added the `<::` exception in [[lex.pptoken#5]], and writing it this way is now fine.

## Questions

!!! question "Question"
    Are `operator and` and `operator&&` the same function name? What about `S(and)` and `S(&&)` (where `S` is a stringizing macro)?

<details markdown="1">
<summary>Answer</summary>

`operator and` and `operator&&` are the same operator function name, because `and` and `&&` are the same token (¶2). Declaring `bool operator&&(X);` in a class and then defining `bool X::operator and(X) { ... }` outside the class is perfectly valid.

Stringizing keeps the spelling: `S(and)` is `"and"` and `S(&&)` is `"&&"`; they differ. This is exactly the one difference Note 1 to ¶2 points out.
</details>
