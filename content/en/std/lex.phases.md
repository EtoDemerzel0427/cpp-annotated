---
title: Phases of translation
summary: "A source file becomes a program through 8 conceptual phases: decoding, line splicing, splitting into preprocessing tokens, preprocessing, string concatenation, conversion into tokens, analysis and instantiation, and linking. The order of the phases explains many lexical and preprocessing phenomena."
updated: 2026-10-19
---

!!! tldr
    - Translation has 8 phases. An implementation only has to behave as if it performed them in order, and may in fact merge them; what the phases fix is what comes first and what the next step sees.
    - Line splicing (phase 2) happens before comments are recognized (phase 3), so a backslash at the end of a `//` comment swallows the next line.
    - Comments become one space in phase 3 and macros are expanded in phase 4, so a macro can neither create a comment nor see one.
    - String concatenation (phase 5) comes after macro expansion, and keywords appear only in phase 6, so `"a" MACRO "b"` concatenates and `#if new` has the value 0.
    - Template instantiation and constant evaluation belong to phase 7; with C++26 reflection, side effects of constant evaluation also affect later analysis.

## A problem caused by a backslash

```cpp run title="comment-splice.cpp" ok
int main() {
  int x = 1; // this line ends with a backslash \
  x = 2;
  return x;   // returns 1: x = 2; became part of the comment
}
```

The program returns 1. The backslash at the end of the line joins the next line onto it, and after joining, `x = 2;` lies inside the `//` comment. Clang 23 gives a `-Wcomment` warning (multi-line // comment).

The reason is the order of translation the standard specifies: physical lines are first joined into logical lines, and only then are comments recognized. [[lex.phases]] describes the whole process from source file to program image in 8 phases.

¶1 The phases specify the precedence among the syntax rules of translation. Footnote 7 explains that an implementation only needs to behave as if the phases occur in order; in practice several phases can be folded together. Clang's lexer, for example, decodes, splices lines and splits tokens in a single pass. So "before" and "after" below are semantic: the result of one phase determines what the next phase sees.

| Phase | Input → output | What it does | Typical consequence |
|---|---|---|---|
| 1 | bytes → characters | Decoding (UTF-8 must be supported); CR LF and CR become new-line | Line-ending style does not affect the program |
| 2 | characters → logical source lines | Delete the BOM; delete backslash + new-line | A `\` at the end of a `//` comment swallows the next line |
| 3 | characters → preprocessing tokens and whitespace | Split tokens; a comment becomes one space | Macros cannot create comments; maximal munch |
| 4 | preprocessing tokens → preprocessing tokens | Execute directives, expand macros; `#include`d files go through phases 1–4 recursively | A comment cannot span files |
| 5 | preprocessing tokens → preprocessing tokens | Concatenate adjacent string literals | `"a" MACRO "b"` concatenates |
| 6 | preprocessing tokens → tokens | Convert into keywords, identifiers, literals, etc. | Keywords exist only from here on |
| 7 | tokens → translated TU | Syntactic and semantic analysis, instantiation, constant evaluation | A failed instantiation makes the program ill-formed |
| 8 | several TUs → program image | Resolve external references, link libraries | Linking |

## Phase 1: reading the source file (¶1.1)

¶1.1 An implementation shall support input files that are a sequence of UTF-8 code units (UTF-8 files), and may also support other, implementation-defined kinds of input files. If it supports other kinds, it shall provide a means, independent of the file's content, to designate a file as a UTF-8 file. Note 1 makes the point that recognizing the byte order mark (BOM, U+FEFF) alone is not sufficient. In other words, the compiler needs a switch such as a command-line option; it cannot rely on guessing.

This requirement comes from [[P2295R6]] in C++23. Before that, the mapping from source file to characters was entirely implementation-defined; the same source with comments in Chinese could be read by MSVC, without a BOM, in the system code page and come out garbled.

A UTF-8 file must be a well-formed UTF-8 sequence, otherwise the program is ill-formed. Each Unicode scalar value obtained by decoding is mapped to an element of the [[g:translation-character-set|translation character set]] ([[lex.charset]]); other kinds of files are mapped in an implementation-defined manner.

The same step also normalizes line endings: CR LF and a lone CR are each replaced by one new-line character, so files in Windows (CRLF) and old Mac (CR) style behave the same. This is directly visible in a raw string:

```cpp run title="crlf.cpp" ok
#include <cstring>
// whether this file is saved with LF or CRLF, the line break in s is a single '\n'
const char* s = R"(line1
line2)";
int main() { return std::strlen(s) == 11 ? 0 : 1; }
```

!!! impl
    GCC treats source files as UTF-8 by default; another encoding can be specified with `-finput-charset=`. Clang accepts only UTF-8 (with or without a BOM). MSVC, without a BOM, interprets the file in the current code page; `/source-charset:utf-8` or `/utf-8` is exactly the content-independent switch ¶1.1 requires.

### Trigraphs

In C++14 and earlier, phase 1 also replaced the 9 trigraphs with single characters, for example `??=` with `#` and `??/` with `\`. Trigraphs almost only ever appear by accident:

```cpp run title="trigraph.cpp" std=c++14 flags="-std=c++14" impl
#include <cstdio>
int main() {
  // will this print????/
  std::puts("yes");
}
```

In C++14, `??/` is a backslash, phase 2 joins the next line into the comment, and the `puts` disappears. Compiled with Clang 23 and `-std=c++14`, it prints nothing and reports multi-line // comment under `-Wall`; compiled with `-std=c++17` it prints `yes`.

C++17 removed trigraphs ([[N4086]]). [[diff.cpp14.lex]] explains that an implementation may still keep them as part of its implementation-defined input mapping, but must not replace them inside raw strings.

## Phase 2: line splicing (¶1.2)

¶1.2 First the BOM at the start of the file, if any, is deleted. Then each sequence of a backslash, some whitespace characters other than new-line, and a new-line is deleted, splicing physical source lines into [[g:logical-source-line|logical source lines]]. Only the last backslash on any physical source line is eligible to be part of such a splice.

Allowing whitespace between the backslash and the new-line is a C++23 change ([[P2223R2]]). Before it, GCC tolerated trailing whitespace while Clang and MSVC did not, so the same code meant different things on different compilers. Trailing whitespace is invisible to the eye, and the standard chose GCC's behavior, under which it does not affect the result.

```cpp run title="splice.cpp" ok
#include <cstring>
int main() {
  const char* q = "a\   
b";   // 3 spaces after the backslash on the previous line: spliced anyway since C++23, q is "ab"
  return std::strcmp(q, "ab");
}
```

Clang 23 splices as the standard says and also gives a `-Wbackslash-newline-escape` warning.

Splicing happens before comments are recognized in phase 3, which is how the opening example goes wrong. It is especially easy to run into when drawing ASCII diagrams in comments, or when a comment ends with a Windows path such as `C:\dir\`.

Note 2 says that line splicing can form a universal-character-name ([[lex.universal.char]], written like `\u0041`):

```cpp run title="ucn-splice.cpp" ok
const char32_t* s = U"\u00\
41";                 // after splicing this is U"\u0041", i.e. U"A"
int main() { return s[0] == U'A' ? 0 : 1; }
```

In C++23 and earlier this case was UB; [[P2621R2]] in C++26 made it valid.

A non-empty source file that does not end in a new-line after splicing is treated as if a new-line were appended. In C++03 this case was UB. The current rule guarantees that an `#include`d file whose last line has no new-line does not run into the next line of the including file.

Phase 2 has one exception: between the two quotes of a raw string literal, the splices made in phase 2 are reverted ([[lex.pptoken#5]]). So a backslash followed by a new-line written in a raw string is kept as is.

## Phase 3: splitting into preprocessing tokens (¶1.3)

¶1.3 The source file is decomposed into [[g:preprocessing-token|preprocessing tokens]] ([[lex.pptoken]]) and whitespace (including comments):

- A source file shall not end in a partial preprocessing token or a partial comment. Footnote 9's examples are a header name missing its closing `"` or `>`, and an unterminated `/*`.
- Each comment is replaced by one space character (U+0020); new-line characters are retained.
- Whether a nonempty sequence of whitespace characters other than new-line is retained or replaced by one space is unspecified. This only affects how `-E` output looks; stringizing (`#`) normalizes whitespace itself, so no portable program can depend on it.
- While preprocessing tokens are being formed, universal-character-names are recognized and replaced by the characters they designate, except inside character literals, string literals, raw strings and header names.
- How the source is split depends on context. For example, after `#include`, `<` can begin a header name ([[lex.header]]).

Universal-character-names inside literals are not replaced here because they must wait until the literal is evaluated, and be handled by the literal's encoding rules ([[lex.string#10]]). In a raw string, `\u0041` is not a universal-character-name at all, just 6 ordinary characters. Not replacing them in header names avoids misreading paths that contain `\u`, as in `#include "C:\users\..."`.

### Macros cannot create comments

Comments have already become spaces in phase 3, so when macros are expanded in phase 4, a macro can neither see a comment nor create one:

```cpp title="no-comment-macro.cpp" error
#define CAT(a, b) a##b
CAT(/, /) this is not a comment   // error: the resulting // is not a preprocessing token
```

The result of `##` must be a valid preprocessing token, and `//` is not a preprocessing token of any kind, only the start of a comment. The current draft makes this case ill-formed ([[cpp.concat]]); in C++23 and earlier it was UB. Clang 23 reports pasting formed '//', an invalid preprocessing token.

Likewise, `a/**/b` is two tokens, `a` and `b`.

## Phase 4: preprocessing (¶1.4)

¶1.4 The source file is analyzed as a *preprocessing-file* ([[cpp.pre]]): preprocessing directives are executed, macros are expanded ([[cpp.replace]]), and `_Pragma` operator expressions are executed ([[cpp.pragma.op]]). An `#include` directive causes the included file to be processed from phase 1 through phase 4, recursively. Finally all preprocessing directives are deleted; from then on, whitespace separating preprocessing tokens is no longer significant.

Several things follow from this.

Each included file goes through phases 1–3 on its own. Each file has its own encoding determination and BOM, and a comment left open in one file cannot be closed in another (see Question 3).

There are no keywords yet in phase 4. Note 4 in [[lex.name]] says that the identifiers in phase 4 include tokens that will only be distinguished as keywords in phase 7. So in `#if`, every identifier and keyword other than `true` and `false` is replaced by 0 ([[cpp.cond]]):

```cpp run title="if-keyword.cpp" ok
#if new == 0 && true && !false   // new is just an identifier here, with value 0
int ok = 1;
#endif
int main() { return ok - 1; }
```

Within phase 4, whitespace is still significant. `#define F(x) ...` defines a function-like macro, while `#define F (x) ...` defines an object-like macro ([[cpp.replace]]). After phase 4, `a  +  b` and `a+b` are no longer different.

## Phase 5: string concatenation (¶1.5)

¶1.5 Two or more adjacent string literal preprocessing tokens are first given a common encoding prefix as described in [[lex.string]], and then concatenated into one.

Concatenation comes after macro expansion, so strings produced by macros take part in it:

```cpp run title="concat.cpp" ok
#define GREETING "Hello, "
const char* s = GREETING "world";             // "Hello, world"
static_assert(sizeof(GREETING "world") == 13);
int main() {}
```

Conversely, `#include` has already been handled in phase 4, before any concatenation, so `#include "dir/" "file.h"` does not become `"dir/file.h"` (Note 2 in [[cpp.include]]).

For the details of concatenation, such as why `"\xA" "B"` does not combine into `"\xAB"`, how conflicting prefixes are handled, and how suffixes of user-defined literals are handled, see [[lex.string#7]], [[lex.string#8]] and [[lex.ext#8]].

## Phase 6: conversion into tokens (¶1.6)

¶1.6 Each preprocessing token is converted into a token ([[lex.token]]). This step does several things that were not done before:

- keywords are distinguished from identifiers ([[lex.key]]);
- preprocessing numbers (pp-numbers) become integer or floating-point literals. One that is neither (for example `0xe+foo` or `1..2`) makes the program ill-formed ([[lex.pptoken#3]]);
- literals now have a type and a value. Before this, preprocessing numbers have no type and no value ([[lex.ppnumber#2]]);
- a single character that cannot be converted into a token, such as a leftover `` ` `` or `$` in the source, makes the program ill-formed.

## Phase 7: analysis, translation and instantiation (¶1.7)

¶1.7 The tokens constitute a **translation unit**, which is syntactically and semantically analyzed and translated as a *translation-unit* ([[basic.link]]). Besides parsing, this phase includes the following.

Note 3 points out that analysis occasionally replaces a token by a sequence of other tokens. The most common case is the rule in [[temp.names]]: the first non-nested `>>` in a template argument list is treated as two `>`. This is not a lexical exception; lexically `>>` is still one token ([[lex.pptoken#5]]), and it is the parser that splits it.

Whether the source of the module units and header units the current TU depends on ([[module.unit]], [[module.import]]) must be available is implementation-defined. Note 4 says that TUs communicate through names with external or module linkage, and through data files.

The required instantiations, including explicit instantiations ([[temp.explicit]]), are performed along with the analysis. The context in which an instantiation takes place is determined by its point of instantiation ([[temp.point]]). Note 6 gives an example: the point of instantiation of a specialization of a constexpr function template might be at the end of the TU, but its use in certain constant expressions requires it to be instantiated earlier ([[temp.inst]]). If any instantiation fails, the program is ill-formed.

### Side effects of constant evaluation {{c++26}}

During analysis, every manifestly constant-evaluated expression is evaluated ([[expr.const.defns]]). Their values affect the types and reflection values used in the program, and so affect parsing itself.

C++26 static reflection ([[P2996R13]]) allows constant evaluation to have side effects. For example, `std::meta::define_aggregate`, evaluated in a `consteval` block, completes the definition of a class. So the standard has to say which side effects have already happened when analyzing some point P in the program.

¶1.7's answer: the side effects of evaluating an expression E as a full-expression are considered complete at P if and only if

- ¶1.7.1 E is the expression corresponding to a `consteval` block declaration ([[dcl.pre]]), and
- ¶1.7.2 that `consteval` block (or the template definition from which it is instantiated) is reachable from P ([[module.reach]]); or P is in a complete-class context of some classes, and the block is reachable from the point immediately following the class definition of the outermost of those classes.

The second branch is for complete-class contexts ([[class.mem.general]]): a member function body, though written in the middle of the class, is analyzed as if after the class definition ends. Below is Example 2 from the standard. Clang 23 does not support reflection yet, so this code was analyzed against the standard and not verified by compiling it.

```cpp
#include <meta>
class S {
  class Incomplete;
  class Inner {
    void fn() {
      /* p1 */ Incomplete i;   // OK: p1 is in a complete-class context of S
    }
  } /* p2 */ ;
  consteval {
    std::meta::define_aggregate(^^Incomplete, {});
  }
} /* p3 */ ;
```

At p1, `Incomplete` is already a complete type: the call to `define_aggregate` is in a `consteval` block, p1 is in a complete-class context of `S`, and the block is reachable from p3 (after the definition of `S`). Declaring `Incomplete i;` at p2 would not work, because p2 is not in a complete-class context.

## Phase 8: linking (¶1.8)

¶1.8 The translated TUs are combined, and all references to external entities are resolved ([[basic.link]]); library components are linked to satisfy references to entities not defined in the current translation. All output is collected into a **program image**, which contains the information needed for execution in its execution environment.

The standard says nothing about object files, static libraries or shared libraries; these are implementation details (Note 2 in [[lex.separate]]). Nor does the standard's model have dynamic linking: the program image is complete before execution.

## Consequences of the order of the phases

| Phenomenon | Reason |
|---|---|
| Macros cannot create comments | Comments are removed in phase 3; macros are expanded in phase 4 |
| A `\` at the end of a `//` comment swallows the next line | Splicing (phase 2) comes before comments are recognized (phase 3) |
| Backslash + new-line is kept inside a raw string | Phase 2 splices are reverted inside raw strings |
| `#include "a" "b"` does not concatenate | `#include` is handled in phase 4, concatenation is phase 5 |
| `"x" MACRO "y"` concatenates | Macro expansion (phase 4) comes before concatenation (phase 5) |
| `#if new` has the value 0 | Keywords appear only in phase 6 |
| After `#define R "x"`, `R"y"` is not `"x" "y"` | Phase 3 splits off the raw string first, see [[lex.pptoken#6]] |
| `0xe+foo` fails to compile | Phase 3 produces one preprocessing number, which fails to convert in phase 6 |
| `vector<vector<int>>` can be written | A grammar rule in phase 7 splits `>>` into two `>` |

!!! history "From 9 phases to 8"
    C++20 had 9 phases: phase 5 mapped the characters in literals to the execution character set, 6 concatenated strings, 7 converted into tokens and analyzed, 8 instantiated, and 9 linked. The C++23 character set rework ([[P2314R4]]) moved encoding into the semantics of the literals themselves ([[lex.charset]], [[lex.string]]), and phase 5 became determining the common encoding prefix, but there were still 9 phases. Changes after C++23 merged determining the prefix and concatenation into phase 5, made conversion into tokens its own phase 6, and folded instantiation into phase 7, giving the current 8 phases. Many sources still use the old numbering, for example "phase 6 is string concatenation", so check the version when reading.

## Common misconceptions

!!! pitfall "Compilers really make 8 passes"
    The phases are a conceptual model. The step where comments become spaces is, in a real compiler, just skipping the comment and noting that there was whitespace there. The phase model is for deriving results, not a description of the compiler's internal flow; neither the location of diagnostics nor the format of `-E` output is constrained by it.

!!! pitfall "Content inside `#if 0` is not lexed"
    Skipped sections must still be split into preprocessing tokens. Under [[lex.pptoken#1]], a lone `'` in an `#if 0` block also makes the program ill-formed. Clang 23 gives no diagnostic for such characters in skipped sections, but that cannot be relied on. An English remark such as `don't` inside `#if 0` should be turned into a comment instead.

## Questions

!!! question "Question 1"
    What does the following program return?

    ```cpp
    #define STR(x) #x
    #define XSTR(x) STR(x)
    int main() {
      const char* s = XSTR(a/**/b);
      return s[1] == ' ';
    }
    ```

<details markdown="1">
<summary>Answer</summary>

It returns 1. Phase 3 replaces the comment with one space, so the macro argument is two tokens, `a` and `b`, with whitespace between them. In stringizing, whitespace between tokens becomes one space ([[cpp.stringize]]), so the result is `"a b"`, and `s[1] == ' '`.
</details>

!!! question "Question 2"
    Why does C++26 need to specify, in phase 7, when the side effects of constant evaluation are complete, while C++20's `constexpr` and `consteval` did not?

<details markdown="1">
<summary>Answer</summary>

Constant evaluation in C++20 only computes a value, at most causing template instantiations, and the context of an instantiation is already governed by the point-of-instantiation rules. C++26 reflection metafunctions (such as `define_aggregate`) can modify the program itself, for example completing the definition of a class. Then whether a class is complete at some point in the program depends on which `consteval` blocks have already been evaluated. The standard must give an answer that does not depend on the compiler's internal order, so it specifies it in terms of reachability and complete-class contexts.
</details>

!!! question "Question 3"
    a.h contains `/* begin` (with no new-line), and b.h contains `end */`. main.cpp does `#include "a.h"` and then `#include "b.h"`. Is the program well-formed?

<details markdown="1">
<summary>Answer</summary>

It is ill-formed. `#include` makes a.h go through phases 1–4 on its own, and phase 3 requires that a source file not end in a partial comment (¶1.3); a.h ends in an unterminated `/*`. A comment cannot span files.
</details>
