---
title: Preamble
summary: "The overall grammar of preprocessing; when a line is a preprocessing directive (four cases, beginning with #, import, module or export); conditionally-supported directives; restrictions on the global module fragment; relaxed syntax in skipped groups; whitespace restrictions inside directives; tokens in directives aren't macro-expanded by default."
updated: 2026-10-19
---

!!! tldr
    - Whether a line is a preprocessing directive is decided lexically at the start of translation phase 4: the line begins with `#`, or with `import`, `module` or `export` followed by certain tokens. Macro expansion can't create directives.
    - `import<...>` or `module m;` at the start of a line is treated as a module-related directive, so old code with names `import` or `module` may suddenly fail to compile.
    - `#` followed by a non-standard name is a conditionally-supported directive, such as `#ident`; an implementation that doesn't support it must diagnose it.
    - In a group skipped by `#if 0`, any tokens can follow the directive name, but the whole section must still be splittable into preprocessing tokens.
    - Tokens in a directive aren't macro-expanded by default; the exceptions are `#if`, `#elif`, `import`, and the macro forms of `#include`, `#embed` and `#line`.

**Preprocessing** ([[g:preprocessing]]) means conditionally skipping parts of the source before translation, including other files, importing macros from header units, and replacing macros (¶1). It happens in translation phase 4, operating on the **preprocessing tokens** ([[g:preprocessing-token]]) split out in phase 3. The central question of this page is: which lines are **preprocessing directives** ([[g:preprocessing-directive]])?

## What counts as a preprocessing directive (¶2)

In C++17 and earlier the answer was simple: lines beginning with `#`. Since C++20 introduced modules, certain lines beginning with `import`, `module` or `export` are directives too. First, the standard's Example 1:

```cpp
#                       // directive
module ;                // directive
export module leftpad;  // directive
import <string>;        // directive
export import "squee";  // directive
import rightpad;        // directive
import :part;           // directive

module                  // not a directive
;                       // not a directive

export                  // not a directive
import                  // not a directive
foo;                    // not a directive

export                  // not a directive
import foo;             // directive (but ill-formed in phase 7)

import ::               // not a directive
import ->               // not a directive
```

¶2 specifies that a preprocessing directive is a sequence of preprocessing tokens satisfying the following. At the start of translation phase 4, its first token, the **directive-introducing token** ([[g:directive-introducing-token]]), is at the beginning of the source file or immediately follows whitespace containing a newline, that is, at the start of a line, and is one of these four:

- ¶2.1 `#`;
- ¶2.2 `import`, immediately followed on the same logical line by a *header-name*, `<`, an identifier or `:`;
- ¶2.3 `module`, immediately followed on the same logical line by an identifier, `:` or `;`;
- ¶2.4 `export`, immediately followed on the same logical line by one of the two forms above.

A directive ends at the end of the line: its last token is the first token in it that is immediately followed by whitespace containing a newline.

Back to Example 1. A `module` alone on a line is immediately followed by a newline, so it doesn't satisfy ¶2.3. In the second-to-last group, the `export` alone on its line isn't a directive, but the `import foo;` on the next line satisfies ¶2.2 by itself, so it is a directive. In phase 7, the dangling `export` followed by an import declaration is a syntax error. In `import ::` and `import ->`, the next token isn't in ¶2.2's list, so they aren't directives.

### Macro expansion can't create directives

Whether a line is a directive is judged by its state at the start of phase 4, and macro expansion happens after that. Example 3 under ¶8 shows this:

```cpp run title="empty-hash.cpp" error
#define EMPTY
EMPTY # include <cstdio>   // not a directive: at the start of phase 4 this line begins with EMPTY
int main() {}
```

After `EMPTY` expands, the line becomes `# include <cstdio>`, but it isn't executed; it goes on to phase 7 as ordinary tokens, where the `#` is a syntax error. Clang reports `expected unqualified-id`.

If macro expansion could create directives, deciding whether a line is a directive would require expanding macros first, while macro definitions depend on earlier directives: a circularity. So even if the result of macro expansion looks like a directive, it isn't processed as one ([[cpp.rescan#4]]). Macros can't create `#include` or `#define`, nor `#pragma`, which is exactly why the `_Pragma` operator exists ([[cpp.pragma.op]]).

### When import and module are directives

In phase 4, `import` and `module` are just ordinary identifiers, and `export` isn't a keyword yet either. ¶2.2 and ¶2.3 recognize them by being at the start of a line plus the next token, and these following tokens were chosen to affect old code that uses `import` and `module` as ordinary names as little as possible:

```cpp run title="import-as-identifier.cpp" ok
int module = 1;            // the line begins with int: not a directive
int import = 2;
int f() {
  return module + import;  // not at the start of a line
}
int main() { return f() - 3; }
```

But as soon as the rule matches, ordinary code is treated as a directive:

<div class="compare" markdown="1">

```cpp error
template<class> struct import {};
import<int> x;
// error: 'int' file not found
```

```cpp error
using module = int;
module i;
// error: not a valid module declaration
```

</div>

On the left, `import` at the start of a line followed by `<` is an import directive, `<int>` is lexed as a *header-name* ([[lex.pptoken]]), and Clang really goes looking for a header named `int`. The right is Example 2 under ¶3: `module i;` satisfies ¶2.3 and is a directive, but it isn't at the start of the file and matches no directive grammar, so the whole file isn't a valid *preprocessing-file*. Clang reports `module declaration must occur at the start of the translation unit`.

The fix is to keep these names from appearing at the start of a line, or to qualify them, for example `::module i;`.

### A newline ends a directive, even in the middle of a macro invocation (note 1)

In ordinary text, a function-like macro invocation can span several lines. In a directive it can't; a newline always ends the directive:

```cpp error
#define F(x) x
#if F(1     // the directive ends here; F( has no matching )
)
#endif
```

Clang reports `unterminated function-like macro invocation`.

## The overall grammar

Before ¶2 comes the grammar of all of preprocessing. The top-level *preprocessing-file* is either an ordinary group of lines (*group*) or a module file:

```text
preprocessing-file:
    group(opt)
    module-file

module-file:
    line-directives(opt) pp-global-module-fragment(opt) pp-module group(opt) pp-private-module-fragment(opt)
```

A module file consists of, in order: optional `#line` directives, an optional global module fragment `module;`, a module directive `export(opt) module name;`, the body, and an optional private module fragment `module :private;`.

A *group* is made up of four kinds of part:

| Part | What it is | Example |
|---|---|---|
| *control-line* | an ordinary directive | `#include`, `#embed`, `#define`, `#undef`, `#line`, `#error`, `#warning`, `#pragma`, the null directive `#`, import directives |
| *if-section* | a conditional inclusion block | `#if`, `#ifdef`, `#ifndef` … `#elif` … `#else` … `#endif` |
| *text-line* | an ordinary source line | `int x = N;` |
| `#` *conditionally-supported-directive* | `#` followed by something that isn't a standard directive name | `#ident "v1"` |

Two details in the grammar are worth noting.

A function-like macro definition requires the macro name to be immediately followed by an *lparen*, a `(` with no whitespace before it. So `#define F (x) [x]` defines an object-like macro whose replacement list is `(x) [x]`. This constrains only the definition; when invoking a function-like macro, whitespace and even newlines may appear between the macro name and the `(` ([[cpp.replace.general#13]]).

```cpp run title="lparen.cpp" ok
#define F (x) [x]   // object-like macro: space after F
#define G(x) [x]    // function-like macro
// F(1)  expands to  (x) [x](1)
// G (2) expands to  [2]
int main() {}
```

A *pp-balanced-token-seq* is a token sequence in which parentheses, brackets and braces are all balanced, used by the parameters of `#embed` and by `__has_embed` ([[cpp.embed]]).

## text-line and conditionally-supported directives (¶3)

The first sentence of ¶3 specifies that a sequence of preprocessing tokens is a *text-line* only if it doesn't begin with a directive-introducing token. That's what excludes `module i;` above: it begins with a directive-introducing token, so it can't be an ordinary text line, and it isn't a valid directive either, so the file is ill-formed.

The second sentence of ¶3 defines a **conditionally-supported directive** ([[g:conditionally-supported-directive]]): the tokens after `#` don't begin with any standard directive name. Its semantics are implementation-defined; conditionally-supported means an implementation that doesn't support it must issue a diagnostic ([[intro.compliance]]).

```cpp run title="cond-directive.cpp" impl
#ident "build 42"   // supported by both GCC and Clang: writes the string into the object file
int main() {}
```

Clang supports `#ident` (warning that it's an extension under `-pedantic`), but not GCC's `#assert`, for which it reports `invalid preprocessing directive`; that's the "diagnose if unsupported" requirement.

Whether or not the implementation supports it, a conditionally-supported directive counts as a preprocessing directive. This matters for [[cpp.replace.general#14]]: a line in a macro argument that would otherwise act as a directive is ill-formed, and lines like `#ident` count too.

## `#embed` parameter names can't be macros (¶4)

¶4 If the tokens of `#embed`, before macro replacement, contain the identifier `limit`, `prefix`, `suffix` or `if_empty` and that identifier is defined as a macro, the program is ill-formed. The parameter part of `#embed` is macro-expanded ([[cpp.embed]]), and once a parameter name is replaced it can no longer be recognized. Rather than letting `#define limit 1` silently change the meaning of `#embed`, it's simply an error. [[cpp.cond#9]] has the same rule for `__has_embed`.

```cpp title="embed-macro-param.cpp" error
#define limit 1
const unsigned char d[] = {
#embed "data.bin" limit(2)   // error: limit is a macro
};
```

Clang 23 reports `expected identifier` here, because the parameter name has already expanded to `1`; same conclusion. Under `-std=c++2c -pedantic`, Clang also warns `#embed is a Clang extension`.

!!! lawyer "offset isn't in the list"
    Neither ¶4 nor [[cpp.cond#9]] lists `offset`, even though it's also a standard parameter ([[cpp.embed.param.offset]]). Read literally, after `#define offset 2`, writing `offset(1)` doesn't trigger ¶4; the parameter expands to `2(1)`, which doesn't match the parameter grammar, so it's still ill-formed, just for a different reason. It looks like this place was missed when `offset` was added. In our tests Clang 23 doesn't know the standard `offset` yet and reports `unknown embed preprocessor parameter 'offset'`.

The second sentence of ¶4: prefixed parameters (*embed-prefixed-parameter*, of the form `vendor::name(...)`) are conditionally-supported with implementation-defined semantics, such as Clang's `clang::offset(n)`.

## Only directives in the global module fragment (¶5)

¶5 At the start of phase 4, the global module fragment (the part between `module;` and the module declaration) can contain neither *text-line*s nor import directives.

```cpp title="gmf.cppm" error
module;
#include <cstdio>        // OK: #include is a directive
#define NDEBUG           // OK
int helper();            // error: a text-line in the global module fragment
export module m;
```

Headers brought in by `#include` of course contain lots of declarations, but that's after `#include` is executed; ¶5 only constrains what is written directly in the global module fragment. The purpose of the global module fragment is to bring in traditional headers with `#include`, so that build tools can understand it without full parsing.

!!! impl "Clang doesn't check this"
    In our tests Clang 23 gives no diagnostic for `int helper();` written directly in the global module fragment, even with `-pedantic`. This doesn't conform to ¶5.

## Relaxed syntax in skipped groups (¶6)

¶6 In a group skipped by `#if` ([[cpp.cond]]), any sequence of preprocessing tokens can appear between the directive name and the newline. Here the preprocessor only needs to look at directive names to track the nesting of `#if`:

```cpp run title="skipped.cpp" ok
#if 0
#  foo bar baz                   // not a standard directive: doesn't matter
#  if this is (not an expression // not evaluated; only nesting is counted
#  endif trailing junk           // #endif in a skipped group can be followed by any tokens
#  include <no/such/file>        // not executed
#  error not triggered           // not executed
#  define F(                     // not checked
#endif
int main() {}
```

But the arbitrary token sequence must still be splittable into preprocessing tokens; phase 3 treats skipped groups the same as everything else. So an unclosed `/*` is ill-formed even in a skipped group, and by [[lex.pptoken#2]] so is a lone `'` or `"`.

!!! impl "Clang is lenient with lone quotes"
    In our tests Clang 23 gives no diagnostic for a lone `'` in a skipped group (such as the English word `don't` inside `#if 0`). Per the draft this is ill-formed. Lots of code relies on this leniency to comment out large blocks of English with `#if 0`.

## Whitespace inside directives (¶7)

¶7 From after the directive-introducing token up to the terminating newline, only spaces and horizontal tabs may appear between tokens, including spaces that replaced comments in phase 3 and spaces that may have replaced other whitespace.

The parenthetical is the key. In phase 3, whether each nonempty sequence of whitespace other than newlines is kept or replaced by one space is unspecified ([[lex.phases]]). So whether a vertical tab between `#define` and the macro name violates ¶7 depends on whether the implementation replaced it with a space in phase 3. In our tests Clang 23 accepts it without a warning.

Comments can appear in directives, because by phase 3 they have become spaces:

```cpp run title="comment-in-directive.cpp" ok
#define N /* the comment becomes a space */ 3
#if N == 3 // same for a line comment
#endif /* even after #endif */
int main() { return N - 3; }
```

## Tokens in directives aren't expanded by default (¶8)

¶8 Preprocessing tokens in a directive aren't subject to macro expansion unless otherwise stated. The cases specified to expand are:

| Directive | Macro-expanded? | Source |
|---|---|---|
| `#if`, `#elif` | yes, except the operand of `defined` | [[cpp.cond#9]] |
| `#ifdef`, `#ifndef`, `#elifdef`, `#elifndef` | no, the identifier is checked directly | [[cpp.cond]] |
| `#include` | only when not of the `<...>` or `"..."` form | [[cpp.include#7]] |
| `#embed` | the parameter part is expanded; the resource name only when not in the direct form | [[cpp.embed]] |
| `#line` | only when not in the direct form | [[cpp.line]] |
| `import` directives | yes | [[cpp.import]] |
| `module` directives | the module name isn't expanded; the rest is | [[cpp.module]] |
| `#define`, `#undef`, `#error`, `#warning` | no | |
| `#pragma` | no; implementations may expand particular pragmas themselves | [[cpp.pragma]] |

`#define` doesn't expand, so the macro name itself is never replaced:

```cpp run title="define-no-expand.cpp" ok
#define A B
#define A B      // redefines A, not B: the macro name A isn't expanded
#undef A         // likewise undefines A
int main() {}
```

Also, where a directive could begin, an identifier after `#` isn't subject to macro replacement ([[cpp.replace.general#10]]), so defining a macro named `include` doesn't break `#include`.

## History

!!! history
    - C++98: a directive was a line beginning with `#` (possibly preceded by whitespace), with a grammar essentially the same as C89's.
    - C++11: caught up with the C99 preprocessor ([[N1653]]), adding variadic macros, `_Pragma` and empty macro arguments.
    - C++20: modules. Lines beginning with `import`, `module` or `export` became directives, and the *module-file* grammar was introduced ([[P1703R1]], [[P1857R3]]).
    - C++23: `#elifdef`, `#elifndef` ([[P2334R1]]) and `#warning` ([[P2437R1]]).
    - C++26: `#embed` and its parameter grammar ([[P1967R14]]). Much of the UB scattered through this chapter became ill-formed or IFNDR.

In the early C++20 design, `import` was just an ordinary declaration processed in phase 7. The problem was that `import "foo.h";` imports macros, which then affect the preprocessing of subsequent lines. Without partially compiling a file, there was no way to know which modules it depends on, so build systems couldn't work out an order before compilation. [[P1703R1]] and [[P1857R3]] made these lines recognizable in phase 4 and restricted their shape with the purely lexical rules of ¶2, so a relatively cheap preprocessing pass can scan out all dependencies. [[cpp.module]]'s ban on module names coming from macro expansion has the same motivation.

## Common misconceptions

!!! pitfall "You can write #if inside macro arguments"
    ```cpp
    printf("%d\n", MAX(a,
    #ifdef BIG
        1000
    #else
        10
    #endif
    ));
    ```
    If `printf` or `MAX` is a function-like macro, this code is ill-formed ([[cpp.replace.general#14]]; UB in C++23 and earlier). Some C standard libraries implement `printf` and `memcpy` as macros, so this code compiles on some platforms and not others. Clang gives only a `-Wembedded-directive` warning for it.

## Questions

!!! question "Question 1"
    Which of the two lines below is a preprocessing directive? What happens in phase 7?
    ```cpp
    export module
    m;
    ```

<details markdown="1">
<summary>Answer</summary>

Neither line is a directive. The `module` on the first line has no identifier, `:` or `;` after it on the same logical line, so it doesn't satisfy ¶2.3, and so `export` doesn't satisfy ¶2.4 either. The second line begins with the identifier `m` and is a *text-line*.

Both lines go on to later phases as ordinary tokens. `module` isn't replaced by the module keyword ([[cpp.module]]), so phase 7 sees only ordinary identifiers, which don't form a module declaration, and the result is a syntax error. The `module` of a module declaration and its name must be on the same line.
</details>

!!! question "Question 2"
    After `#define EMPTY`, `EMPTY #define X 1` doesn't define `X`. Yet after `#define D defined(A)`, `#if D` works on Clang. What's the essential difference?

<details markdown="1">
<summary>Answer</summary>

The first is using a macro to create a directive. Whether something is a directive is decided at the start of phase 4 (¶2), and macro expansion comes after that, so directives can never be created this way. That follows from the rule itself and is the same in every implementation.

The second is macro expansion in a `#if` expression producing `defined`, which [[cpp.cond#9]] makes IFNDR (UB in C++23 and earlier). It works only because Clang chooses to evaluate it as usual while issuing a `-Wexpansion-to-defined` warning; the standard guarantees nothing.
</details>
