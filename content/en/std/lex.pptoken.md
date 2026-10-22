---
title: Preprocessing tokens and tokens
summary: "How phase 3 splits characters into preprocessing tokens: maximal munch and its exceptions (raw strings, <::, [::), comments, header names, preprocessing numbers, operators and punctuators; and the tokens phase 6 converts them into."
updated: 2026-10-19
---

!!! tldr
    - Phase 3 always takes the longest sequence of characters that can form a preprocessing token, with no backtracking, so `x+++++y` is split as `x ++ ++ + y` and fails to compile.
    - The exceptions, in order: raw strings take priority; the `<` in `<::` is a token by itself; the `[` in `[::` and `[:>` is a token by itself (C++26). Header names are formed only in a few places such as after `#include`.
    - The grammar of preprocessing numbers (pp-numbers) is deliberately broad: `0xe+foo` and `1.2.3` are each one preprocessing number, and only in phase 6 are they rejected for not being valid literals.
    - `/* */` comments do not nest; a comment becomes one space in phase 3.
    - A lone `'` or `"`, or a character outside the basic character set, cannot be a preprocessing token by itself; otherwise the program is ill-formed.

## Splitting is greedy

```cpp title="munch.cpp" error
int f(int x, int y) {
  return x+++++y;    // split as x ++ ++ + y; x++ is a prvalue and cannot be incremented again
}
```

Split as `x ++ + ++ y` it would have been a valid expression, but the compiler does not split it that way. Phase 3 ([[lex.phases]]) scans characters from left to right, each time taking the longest sequence that can form a preprocessing token, and never goes back. This rule is called [[g:maximal-munch|maximal munch]], and most of this page is about it and its few exceptions.

First, what is it that gets split out?

## Kinds of preprocessing tokens ([[lex.pptoken]] ¶1)

```
preprocessing-token:
    header-name
    import-keyword
    module-keyword
    export-keyword
    identifier
    pp-number
    character-literal
    user-defined-character-literal
    string-literal
    user-defined-string-literal
    preprocessing-op-or-punc
    each non-whitespace character that cannot be one of the above
```

¶1 A [[g:preprocessing-token|preprocessing token]] is the minimal lexical element of translation phases 3 through 5. They are: header names, the three placeholder tokens produced by module directives, identifiers, preprocessing numbers, character literals and string literals (both including their user-defined forms), preprocessing operators and punctuators, and single non-whitespace characters that do not fall into any of the other categories.

The last category is a catch-all: with it, the preprocessor can carry any character, for example passing it to a macro and stringizing it, without rejecting it in phase 3. But the catch-all is restricted:

!!! std
    If a U+0027 apostrophe, a U+0022 quotation mark, or any character not in the basic character set matches the last category, the program is ill-formed.

- A lone `'` or `"` means a literal was not closed. In C++23 and earlier this was UB; [[P2621R2]] in C++26 made it ill-formed.
- A character outside the basic character set ([[lex.charset]]), such as `€`, must either be part of an identifier (when it has the XID properties, see [[lex.name]]) or appear in a literal or comment; otherwise the program is ill-formed.
- The characters of the basic character set with no syntactic use, `@`, `` ` `` and `$`, and a lone `\`, may exist as single-character preprocessing tokens as long as they disappear before phase 6, for example by being stringized:

```cpp run title="stray.cpp" ok
#define S(x) #x
const char* at = S(@);    // OK: @ is a basic character, a token by itself, stringized as "@"
const char* bt = S(`);    // OK: likewise
// const char* eu = S(€); // error: € is not in the basic character set
int main() { return at[0] == '@' && bt[0] == '`' ? 0 : 1; }
```

### Whitespace and comments (¶2, [[lex.comment]])

¶2 Preprocessing tokens can be separated by whitespace. Whitespace means comments, or the characters space, horizontal tab, new-line, vertical tab and form feed, or both. Note 1 says that in certain circumstances in phase 4, whitespace (or its absence) matters for more than separation, for example between the name of a function-like macro and the `(`. Whitespace can appear within a preprocessing token only as part of a header name or between the quotation characters of a literal.

[[lex.comment]] ¶1 specifies two kinds of comments. A comment starting with `/*` ends with `*/` and **does not nest**; a comment starting with `//` ends just before the next new-line, and the new-line itself is not part of the comment, so the new-line after a `//` comment still terminates a preprocessing directive. Note 1 says that `//`, `/*` and `*/` have no special meaning inside a `//` comment, and neither do `//` and `/*` inside a `/*` comment.

```cpp run title="comments.cpp" ok
/* outer /* this does not start a nested comment */
int a = 1;   // the */ on the previous line already ended the comment
// the /* here does not start anything
int b = 2;
int main() { return a + b - 3; }
```

Because comments do not nest, a `/* ... */` comment cannot comment out code that itself contains `/* */`, which is where the `#if 0 ... #endif` idiom comes from. A `//` inside a string literal is not a comment, because it has already been consumed as part of the literal when the literal was split off; likewise a `"` in a comment does not start a string.

A comment becomes one space in phase 3, so `a/**/b` is two tokens, and macros can neither produce comments nor swallow them ([[lex.phases]]).

### Conditions for conversion into tokens (¶3)

¶3 Each preprocessing token that is converted to a token must have the lexical form of a keyword, an identifier, a literal, a header name, or an operator or punctuator. So a preprocessing number that is not a valid literal (such as `1.2.3`), and an `@`, `` ` `` or `\` left over until phase 6, all make the program ill-formed.

### Placeholder tokens of module directives (¶4)

¶4 The *import-keyword* is produced by processing an `import` directive ([[cpp.import]]), the *module-keyword* by processing a `module` directive ([[cpp.module]]), and the *export-keyword* by the `export` in either directive. Note 2: none of them has an observable spelling.

C++20 modules require that a build system be able to scan out dependencies without fully compiling, so lines beginning with `import` or `module` (possibly preceded by `export`) are designed as preprocessing directives that the preprocessor recognizes, and it can also handle imported macros. Once recognized, the leading `import`, `module` and `export` are replaced by these invisible placeholder tokens. That way they are no longer directives, are not deleted at the end of phase 4 (Note 2 in [[cpp.import]]), and later phases can distinguish them from ordinary identifiers named `import` or `module`.

```cpp run title="module-ident.cpp" ok
class module {};
module *m2;              // not a module directive: module is followed by *
class import {};
::import *p = nullptr;   // import is not at the start of the line, so it is an ordinary identifier
int main() {}
```

This example is adapted from [[diff.cpp17.lex]]. Written as `module m1;` or `import j1;`, these would be a module declaration or an import declaration. For more discussion see the section on identifiers with special meaning in [[lex.name]].

## Maximal munch and its exceptions (¶5)

¶5 If the input has been parsed into preprocessing tokens up to a given character, the next preprocessing token is determined in the following order.

### Raw strings take priority (¶5.1)

¶5.1 If the next characters could be the prefix and initial double quote of a raw string literal, such as `R"`, the next preprocessing token shall be a raw string literal. Between the two double quotes of a raw string, the line splices made in phase 2 are reverted, before the delimiter and content are identified. The raw string literal is the **shortest** sequence of characters that matches the pattern `encoding-prefix(opt) R raw-string`.

Two things follow. First, even if `R` is a macro name it is not expanded, because splitting (phase 3) comes before macro expansion (phase 4). This is Example 1 in ¶6:

```cpp title="raw-macro.cpp" error
#define R "x"
const char* s = R"y";   // error: this is an ill-formed raw string, not "x" "y"
```

`R"y";` starts a raw string, and no `(` is found after the delimiter `y";`, so it is ill-formed. C++03 code that did `#define u8 "abc"` and then wrote `u8"def"` changed meaning in C++11 for the same reason ([[diff.cpp03.lex]]).

Second, the match is the shortest sequence: the raw string ends at the first "`)` + delimiter + `"`" and does not search further.

### The `<::` exception (¶5.2)

¶5.2 Otherwise, if the next three characters are `<::` and the subsequent character is neither `:` nor `>`, the `<` is treated as a preprocessing token by itself, and not as the first character of the alternative token `<:` (that is, `[`, see [[lex.digraph]]).

This rule was added in C++11 to fix code like this:

```cpp run title="angle-colon.cpp" ok
#include <vector>
#include <string>
std::vector<::std::string> v;   // in C++03 <: is [, giving vector[:std::string>
int main() {}
```

The two excluded cases are there so as not to break existing digraph spellings: `<::>` is still `<:` `:>` (that is, `[]`), and `<:::` is still `<:` `::` (that is, `[::`).

```cpp run title="angle-colon-2.cpp" ok
constexpr int n = 2;
int a<::> = {1, 2, 3};   // <: :>      i.e. int a[] = {1, 2, 3};
int b<:::n:>;            // <: :: n :> i.e. int b[::n];
struct T {};
template<class> struct V {};
V<::T> v;                // < :: T >
static_assert(sizeof a / sizeof a[0] == 3 && sizeof b / sizeof b[0] == 2);
int main() {}
```

### The `[::` and `[:>` exceptions (¶5.3) {{c++26}}

¶5.3 Otherwise, if the next three characters are `[::` and the subsequent character is not `:`, or if the next three characters are `[:>`, the `[` is treated as a preprocessing token by itself and not as the first character of the token `[:`.

C++26 static reflection ([[P2996R13]]) introduced the splice tokens `[:` and `:]`, as in `[:r:]`. Under maximal munch, `a[::n]` (a subscript with a globally qualified name) would split as `a [: :n]`, breaking a large amount of existing code. This exception preserves it:

- `a[::n]` splits as `a` `[` `::` `n` `]`;
- `int x[:>` splits as `int x` `[` `:>`; `:>` is the digraph for `]`, so the whole is `int x[]`;
- in `[:::x:]` the fourth character is `:`, so it still splits as `[:` `::` `x` `:]`, a splice of `::x`.

Note 3 says that `[:` and `:]` cannot be formed from digraphs, and `<::` does not become `[:`.

### Maximal munch (¶5.4)

¶5.4 Otherwise, the next preprocessing token is the longest sequence of characters that could constitute a preprocessing token, even if that would cause further lexical analysis to fail.

!!! std
    the next preprocessing token is the longest sequence of characters that could constitute a preprocessing token, even if that would cause further lexical analysis to fail

This makes the lexer a simple automaton that never backtracks, at the price of some counterintuitive results. The opening `x+++++y` is Example 3 in ¶8. Example 2 in ¶7 is:

```cpp title="pp-number-munch.cpp" error
#define foo 1
int g() { return 0xe+foo; }   // error: 0xe+foo is one preprocessing number, not 0xe + foo
```

In the grammar of preprocessing numbers, `e+` is an exponent part (see below), so all of `0xe+foo` is one preprocessing number. The macro `foo` is never seen, because it is not a separate identifier token. In phase 6 it is not a valid literal, and the program is ill-formed. Likewise, even if `E` is a macro name, `1E1` is always one preprocessing number.

`>>` is always split as one token. `vector<vector<int>>` compiles because a grammar rule in phase 7 treats the first non-nested `>>` in a template argument list as two `>` ([[temp.names]]); this is not a lexical exception:

```cpp run title="shift.cpp" ok
#include <vector>
template<int N> struct Y {};
std::vector<std::vector<int>> v;   // >> is split by the grammar rule
Y<(8>>1)> y1;                      // >> inside parentheses is still a right shift
// Y<8>>1> y2;                     // error: after splitting, the first > ends the argument list
int main() {}
```

### Two restrictions for header names (¶5.4.1, ¶5.4.2)

Maximal munch has two further restrictions:

- ¶5.4.1 Where a header name can be formed, a string literal is not formed. So in `#include "a\n.h"` the `\n` is not an escape sequence (though a `\` in a header name is conditionally-supported, see below).
- ¶5.4.2 A header name is formed only in three places: immediately after `include` or `embed` in an `#include` or `#embed` directive; after an `import` at the start of a logical source line; and immediately after `__has_include (` or `__has_embed (` in an `#if`, `#elif` or `#embed` directive. Immediately means on the same logical source line with no other preprocessing token in between.

The positions are restricted because in ordinary code `<` and `>` are comparison operators, and `a<b>c` cannot be treated as a header name. [[diff.cpp17.lex]] records one consequence of this rule:

```cpp title="import-header.cpp" error
template<typename> class import {};
import<int> f();     // error: after an import at the start of a line, <int> is split as a header name; this is an import directive
::import<int> g();   // OK: import is not at the start of the line
```

Clang 23 treats the second line as importing the header `<int>` and reports 'int' file not found. `#embed` and `__has_embed` were added in C++26.

## Header names ([[lex.header]])

```
header-name:
    < h-char-sequence >
    " q-char-sequence "
h-char:  any character except new-line and >
q-char:  any character except new-line and "
```

¶1 The sequences in both forms are mapped in an implementation-defined manner to headers or to external source file names ([[cpp.include]]). Note 1 says that header names appear only in `#include` directives, `__has_include` expressions, and after certain occurrences of `import`.

¶2 The appearance of `'`, `\`, `/*` or `//` in a header name, or of `"` in the `<...>` form, is conditionally-supported, with implementation-defined semantics. Note 2 says that something that looks like an escape sequence may result in an error, be interpreted as the corresponding character, or have a completely different meaning.

Each of these characters has its reason. `\` is the path separator on Windows; a header name is not a string literal, and the `\f` in `"dir\file.h"` is not a form feed, but the standard does not force every platform to accept backslash paths. `'` could be taken as the start of a character literal by old preprocessors. `//` and `/*` cause trouble for implementations that recognize comments first; for `#include <a//b>`, Clang 23 looks for a file named `a//b`. Portable code uses only `/`, which compilers on Windows also accept.

## Preprocessing numbers ([[lex.ppnumber]])

```
pp-number:
    digit
    . digit
    pp-number identifier-continue
    pp-number ' digit
    pp-number ' nondigit
    pp-number e sign
    pp-number E sign
    pp-number p sign
    pp-number P sign
    pp-number .
```

A [[g:pp-number|preprocessing number]] begins with a digit or with `.` followed by a digit, and may be followed by any number of identifier characters, `.`, `'` followed by a digit or letter, and `e+`, `e-`, `E+`, `E-`, `p+`, `p-`, `P+`, `P-`.

¶1 Preprocessing number tokens lexically include all integer literal and floating-point literal tokens. ¶2 A preprocessing number has no type or value; it acquires both after a successful conversion to an integer literal or floating-point literal.

The grammar is deliberately loose. The preprocessor does not need to know the exact grammar of literals, nor change as new suffixes appear: `123_km`, `1.0f16`, `0x1p-3` and `1'000'000uz` are each one preprocessing number. When a macro pastes numbers with `##`, intermediate results need not be valid literals either. The price is that some things that look like expressions get swallowed whole:

| Source | Split | Result |
|---|---|---|
| `1.2.3` | one preprocessing number | ill-formed in phase 6 |
| `0xe+1` | one preprocessing number | ill-formed; write `0xe + 1` |
| `1.e+5` | one preprocessing number | a valid floating-point literal |
| `1_km+2` | `1_km` `+` `2` | what precedes `+` is not `e` or `p`, so it is not absorbed |
| `1_e+2` | one preprocessing number | the trailing `e` of `_e` and the `+` form an exponent, the whole thing is swallowed, ill-formed |

!!! history "Two extensions of preprocessing numbers"
    C++14 added digit separators, and preprocessing numbers gained `' digit` and `' nondigit`. So for `M(1'2,3'4, 5)`, in C++11 `'2,3'` is a character literal and the macro receives only two arguments; in C++14 it receives three ([[diff.cpp11.lex]]). C++17 added hexadecimal floating-point literals, and preprocessing numbers gained `p sign` and `P sign`, so `0p+0` went from three tokens to one ([[diff.cpp14.lex]]).

!!! impl "Clang's deviation"
    Clang 23 absorbs `p+` and `p-` into a preprocessing number only when the number begins with `0x` or `0X`. In the example in [[diff.cpp14.lex]], `#define F(a) b ## a` with `int b0p = F(0p+0);`, `0p+0` is one preprocessing number under the standard, `b ## 0p+0` does not form a valid token, and the program is ill-formed; Clang instead splits `0p+0` into three tokens and accepts it.

## Operators and punctuators ([[lex.operators]])

¶1 Some preprocessing tokens are used in the syntax of the preprocessor; others are converted into operator and punctuator tokens:

```
preprocessing-operator: one of
  #   ##  %:  %:%:
operator-or-punctuator: one of
  {   }   [   ]   (   )   [:  :]
  <%  %>  <:  :>  ;   :   ...
  ?   ::  .   .*  ->  ->* ^^  ~
  !   +   -   *   /   %   ^   &   |
  =   +=  -=  *=  /=  %=  ^=  &=  |=
  ==  !=  <   >   <=  >=  <=> &&  ||
  <<  >>  <<= >>= ++  --  ,
  and or  xor not bitand  bitor  compl
  and_eq  or_eq  xor_eq  not_eq
```

Each operator or punctuator is converted into a single token in phase 6.

- `#`, `##` and their digraphs `%:`, `%:%:` are preprocessing operators only. If they survive to phase 6 (for example, appearing in ordinary code), they cannot be converted, and the program is ill-formed.
- `and`, `or` and the like are operator tokens, neither keywords nor identifiers ([[lex.digraph]], [[lex.key#3]]).
- The newer members are `<=>` (C++20), and `^^`, `[:`, `:]` for reflection (C++26).

Adding a new token changes the result of maximal munch and can break old code. The two examples below come from [[diff.cpp17.lex]] and [[diff.cpp23.lex]] respectively:

```cpp title="spaceship-break.cpp" error
namespace N {
  struct X {};
  bool operator<=(X, X);
  template<bool(X, X)> struct Y {};
  Y<operator<=> y;   // error since C++20: <=> is one token; in C++17 it was operator<= and >
}
```

```cpp title="reflect-break.cpp" error
struct C { int operator^(int); };
int operator^(int (C::*p)(int), C);
int i = &C::operator^^C{};   // error since C++26: ^^ is one token; in C++23 it was ^ ^
```

Clang 23 does not implement the `^^` token yet, so the second example compiles.

## Tokens ([[lex.token]])

```
token:
    identifier
    keyword
    literal
    header-name
    operator-or-punctuator
```

¶1 The text says there are six kinds of tokens: identifiers, keywords, literals, header names, operators, and other separators. The grammar has only five alternatives because operators and other separators (punctuators) are combined into one *operator-or-punctuator* in the grammar. Header names are tokens too: the header name in `import <vector>;` is kept until phase 7, for use by the grammar of [[module.import]].

The correspondence between preprocessing tokens and tokens in phase 6:

| Preprocessing token | Becomes after phase 6 |
|---|---|
| identifier | identifier or keyword ([[lex.key]]) |
| preprocessing number | integer literal, floating-point literal or user-defined literal; ill-formed if none of these |
| character or string literal | literal (adjacent strings were already concatenated in phase 5) |
| preprocessing operator or punctuator | operator or punctuator; `#` and `##` are ill-formed |
| header name | header name |
| placeholder token of a module directive | keyword (*import-keyword* etc. in the grammar of [[lex.key]]) |
| any other single character | ill-formed |

## Common misconceptions

!!! pitfall "The compiler splits according to intent"
    `a+++b` is `a++ + b`; `a+++++b` is always ill-formed; `a/ *p` is a division, while `a/*p` starts a comment. Separate complex expressions with spaces.

!!! pitfall "A macro right after a number is expanded"
    After `#define E 10`, `1E` does not expand `E`, and neither does `0x1e+E`. Where a letter immediately follows a number, macros are invisible.

## Questions

!!! question "Question 1"
    Into which preprocessing tokens is each line split? Which are well-formed in the end?

    ```cpp
    a = b---c;     // (1)
    a = b-- - -c;  // (2)
    p = q->*r;     // (3)
    x = y/**/z;    // (4)
    n = 1.0e-3_m;  // (5)
    ```

<details markdown="1">
<summary>Answer</summary>

1. `b -- - c`: maximal munch takes `--` first, leaving `-`. Well-formed, meaning `(b--) - c`.
2. `b -- - - c`: well-formed, meaning `(b--) - (-c)`.
3. `q ->* r`: `->*` is one three-character token, access through a pointer to member.
4. `y z`: the comment becomes a space, and `x = y z;` is a syntax error.
5. `1.0e-3_m` is one preprocessing number (`e-` is an exponent, `_m` are identifier characters); in phase 6 it becomes a user-defined floating-point literal, which needs a declared `operator""_m`.
</details>

!!! question "Question 2"
    Why does ¶5.3 exclude only the case where `[::` is followed by `:`, while ¶5.2 excludes both cases where `<::` is followed by `:` or `>`?

<details markdown="1">
<summary>Answer</summary>

¶5.2 has to preserve existing digraph spellings: `<::>` is `[]` and `<:::` is `[::`, and both require `<:` to be recognized as a digraph.

¶5.3 has to preserve a `[::` that does not mean a splice, that is, a globally qualified name in a subscript. But `[:::` must still split as `[:` `::`, because that is how a splice of a name beginning with `::` is written, so only the case where the fourth character is `:` can be excluded. `[:>` is listed separately for spellings like `x[:>`: `:>` is the digraph for `]`, so the whole is `x[]`; split as `[:` `>`, it would become the start of a splice.
</details>
