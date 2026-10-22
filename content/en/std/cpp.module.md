---
title: Module directives
summary: "Why module and import lines must be recognized at preprocessing time; module names can't come from macros; of the three forms of import, only importing a header unit brings in macros; and how macro definitions imported from several header units are judged active and conflicting."
updated: 2026-10-19
---

!!! tldr
    - `export module m;` and `import x;` are both declarations and preprocessing directives. That way a build system only needs to preprocess to scan which module each file belongs to and which modules it depends on.
    - Module names and partition names can't come from macros, and the name must be followed immediately by `;` or `[`, so the module name can be read without expanding macros.
    - Forms that import a header unit, such as `import <vector>;`, bring in macros; `import m;` imports a named module and brings in no macros.
    - In the body of a module unit, an import can't come from a file brought in by `#include`.
    - When macros with the same name are imported from several header units, all the active definitions are required to agree only when the macro is used or redefined.

At the language level, modules are declarations ([[module]]), but `module` lines and `import` lines are also preprocessing directives. The reason is compilation order: compiling an importer needs the already-compiled interface of the imported module, so the build system has to scan every file before compiling to learn which module it is and whom it imports. If that information required full parsing, you'd have to compile to know how to compile.

By defining these lines as directives, with some restrictions, a scanner only needs one preprocessing pass. Clang's `clang-scan-deps`, GCC's `-fdeps-format=p1689r5` and MSVC's `/scanDependencies` all work this way. When a line of text is recognized as such a directive is covered in [[cpp.pre#2]].

## Names in module declarations (¶1–¶3)

<div class="compare" markdown="1">

```cpp title="tu1.cppm" error
module;
#define DOT_BAR .bar
export module foo DOT_BAR;
// error: foo is followed by . rather than ; or [
```

```cpp title="tu2.cppm" ok
module;
#define MOD_ATTR [[vendor::shiny]]
export module M MOD_ATTR ;
// OK: after expansion M is followed by [
```

</div>

This is a simplified version of the standard's Example 1 in ¶3 (the original puts the macros in an included header). The left tries to complete the module name to `foo.bar` with a macro. A scanner that doesn't expand macros would see the module name as `foo`, while the compiler, after expansion, sees `foo.bar`; the two disagree, so it's forbidden. The macro on the right only supplies an attribute, and the module name `M` looks the same to scanner and compiler, so it's allowed.

¶1 A `module` directive must be followed by a module name (dot-separated identifiers like `a.b.c`), an optional partition name (`:part`), and then other tokens. No identifier in the module name or partition name shall:

- be currently defined as an object-like macro;
- be followed by `(` at the start of phase 4.

The second targets function-like macros. The standard doesn't care whether a name followed by `(` is a macro; it forbids it outright, so a scanner can decide without knowing any macro definitions.

```cpp title="m3.cppm" error
module;
#define NAME foo
export module NAME;    // error: an identifier in the module name is an object-like macro
```

Clang 23's diagnostic is module name component 'NAME' cannot be a object-like macro.

¶2 When this directive is processed, the `module` and `export` tokens are replaced by *module-keyword* and *export-keyword*. These two are special tokens with no spelling ([[lex.pptoken#4]]), by which the phase 7 grammar recognizes module declarations ([[module.unit]]), so an ordinary variable named `module` won't be mistaken for a module declaration. Note 1 explains that after replacement the line is no longer a directive, so it isn't deleted with the other directives at the end of phase 4 but stays until phase 7 as a declaration.

After replacement, the tokens of the line are processed as ordinary text, which means they are macro-expanded. Note 2 points out that the module name and partition name can't be expanded, since ¶1 already guarantees they contain no macros; what actually expands is only the part after the name, such as attributes. After processing, the module name and partition name must be followed by `;` or `[`.

### Can the directive span lines?

Examples 2 to 5 in ¶3 discuss newlines:

```cpp
export module a
.b;                             // error: the token after the module name isn't ; or [

export module M [[
attr1,
attr2 ]] ;                      // OK

export module M
[[ attr1,
attr2 ]] ;                      // OK

export module M; int
n;                              // OK
```

A directive ends at a newline ([[cpp.pre]]), so how can the attribute be on the next line? Because by ¶2, after replacement by special tokens the line is already ordinary text, and the next line continues it as ordinary text, combining into a complete declaration in phase 7. The directive used for scanning extends only to the end of the first line; it only needs to contain the module name.

- `export module a` newline `.b;`: the module name in the directive is `a`; after processing, the first token after the name is the `.` on the next line, not `;` or `[`, so it's ill-formed. If allowed, the scanner would see the module name as `a` while the compiler assembled `a.b`.
- `export module M; int` newline `n;`: the `int n;` after the `;` is an ordinary declaration, which is valid. Clang gives an extra tokens after semicolon in 'module' directive warning for tokens after the `;` on the same line.

`module;` (the start of the global module fragment) and `module :private;` (the start of the private module fragment) are also directives recognized by [[cpp.pre#2]]. At the start of phase 4, the global module fragment may contain only preprocessing directives ([[cpp.pre#5]]); see [[module.global.frag]] and [[module.private.frag]] for details.

## Import directives ([cpp.import] paragraphs 1–3)

Import directives have three forms:

```text
export(opt) import header-name pp-tokens(opt) ;          // ① import <vector>;  import "a.h";
export(opt) import header-name-tokens pp-tokens(opt) ;   // ② import HDR; (after macro expansion, "a.h" or <...>)
export(opt) import pp-tokens ;                           // ③ import foo;  import :part;
```

Paragraph 1 of [[cpp.import]]: the tokens after `import` are macro-expanded like ordinary text. The first two forms import header units and have a **[[g:point-of-macro-import|point of macro import]]**, located after the newline ending the directive, from which the header unit's macros become visible. The third form imports a named module or partition, has no point of macro import, and is considered only if, after macro replacement, neither of the first two forms matches.

| What's imported | Declarations visible | Macros visible |
|---|---|---|
| Header unit: `import <vector>;`, `import "a.h";` | yes | yes |
| Named module: `import foo;` | exported declarations | no |
| Partition: `import :part;` | yes | no |

Named modules don't export macros; this is one of the core promises of the module design: a module's interface is declarations, not text.

Paragraph 3: in all three forms, `import` and `export` are replaced by *import-keyword* and *export-keyword*, for the same reason as module declarations: the line is no longer a directive and stays until phase 7 to become an import declaration. For the second form, the tokens must also be combined into a header name by the rules of `#include` ([[cpp.include#7]]). Note 3 explains that this ensures the preprocessor and later phases agree on which header is imported.

```cpp
#define HDR <vector>
import HDR;        // second form: expands to < vector >, combined into the header name <vector>
```

### Imports can't come from included files

Paragraph 2: when processing the body of a module unit, if an import is produced by source file inclusion, the program is ill-formed. This covers both an import written in the included file and an `#include` that the implementation rewrites as an import ([[cpp.include#10]]).

```cpp title="m.cppm"
export module m;
#include "imports_vector.h"   // the file contains import <vector>; ill-formed
```

The reason is again dependency scanning: imports in the body of a module unit must be written directly in that file so the scanner can see them without following `#include` chains, and which file an `#include` finds depends on macros and search paths. Also, [[module.import#1]] requires imports in a module unit to come before other declarations, which imports popping out of a header can hardly satisfy.

This restriction applies only to the body after the module declaration. An `#include <vector>` in the global module fragment is fine even if the implementation rewrites it as an import; whether an `#include <vector>` in the body is an error depends on whether the implementation does the rewrite. When you need the standard library in the body, write `import std;` or `import <vector>;` directly.

## Macros imported from header units ([cpp.import] paragraphs 4–7)

With only `#include`, deciding whether macro `X` is defined is simple: read from top to bottom and look at the last `#define X` or `#undef X`. Header units break this linear model: the same macro may come in through several header units with different definitions. The standard defines several terms for this.

Paragraph 4: each `#define` encountered while processing the translation units of the program yields a distinct **[[g:macro-definition|macro definition]]**. Note 4 explains that predefined macros aren't introduced by `#define`, and encourages implementations to treat macros predefined by mechanisms such as `-D` the same way. Each macro definition has at most one point of definition and one point of undefinition in each translation unit:

- **[[g:macro-point-of-definition|Point of definition]]** (item 4.1): if the `#define` is in translation unit T, its point of definition is where it occurs; otherwise it is the point of macro import of the first header unit in T that contains its point of definition, and the macro is then said to be imported from the header unit. Macros whose names are the same as keywords, `module` or `import` aren't imported this way.
- **[[g:point-of-undefinition|Point of undefinition]]** (item 4.2): the first `#undef` undefining it after its point of definition, or the point of macro import of the first header unit containing its point of undefinition, whichever comes first.

Excluding keywords and `module` and `import` ensures that whether a directive is an import can't change because some macro was imported, so the results of dependency scanning don't depend on imported macros.

Paragraph 5: a macro definition is **[[g:active-macro-definition|active]]** at a location if it has a point of definition before that location and no point of undefinition before it.

Paragraph 6: if a macro would be replaced or redefined, and the name has multiple active macro definitions, those definitions must all be valid redefinitions of the same macro, that is, with identical replacement lists and so on ([[cpp.replace.general#2]]). Note 5 explains that the order of imports doesn't matter for whether a definition is active.

The trigger is "would be replaced or redefined". Merely importing two conflicting definitions isn't a violation; using it or defining it again is.

### The standard's example

Example 1 in paragraph 7 ties these rules together:

```cpp title="a.h"
#define X 123   // #1
#define Y 45    // #2
#define Z a     // #3
#undef X        // point of undefinition of #1 in a.h
```

```cpp title="b.h"
import "a.h";   // point of definition of #1, #2, #3 in b.h, and point of undefinition of #1
#define X 456   // OK: #1 isn't active; its #undef was imported along with it
#define Y 6     // error: #2 is active, and 45 and 6 aren't valid redefinitions
```

```cpp title="c.h"
#define Y 45    // #4
#define Z c     // #5
```

```cpp title="d.h"
import "c.h";   // point of definition of #4, #5 in d.h
```

```cpp title="e.h"
import "a.h";   // point of definition of #1, #2, #3; point of undefinition of #1
import "d.h";   // point of definition of #4, #5: macros imported in d.h come into e.h too
int a = Y;      // OK: the active #2 and #4 are both 45, valid redefinitions
int c = Z;      // error: the active #3 (a) and #5 (c) aren't valid redefinitions
```

```cpp title="f.cppm"
export module f;
export import "a.h";
int a = Y;      // OK: f itself imported a.h, so Y is visible
```

```cpp title="tu1.cpp" error
import f;
int x = Y;      // error: Y is neither a macro nor a declared name
```

The last case is the easiest to get wrong. `f` re-exports the header unit with `export import "a.h"`, but what's re-exported is only declarations. `import f;` is the third form with no point of macro import, so `Y` isn't visible.

!!! impl "Tested with Clang 23"
    After compiling `a.h` and `c.h` into header units with `-fmodule-header=user`:

    - `import "a.h"; import "c.h"; int a = Y;` compiles, and `X` isn't defined; the `#undef` takes effect along with the import.
    - `int c = Z;` gets only an ambiguous expansion of macro 'Z' warning, then picks one of the definitions and carries on. The standard requires it to be ill-formed; the warning formally satisfies the diagnostic requirement, but which definition is picked shouldn't depend on import order, which is exactly what note 5 means.
    - `#define Y 6` after `import "a.h";` gets only a `-Wmacro-redefined` warning, the same as an ordinary macro redefinition.
    - After `export import "a.h";` in module `f`, `import f; int x = Y;` reports use of undeclared identifier 'Y', agreeing with the standard.
    - Every import of a header unit gets a `-Wexperimental-header-units` warning from Clang: header units are still an experimental feature in Clang.

## History

!!! history
    - C++20's merged modules proposal [[P1103R3]] introduced header units and macro imports. Then [[P1703R1]] made imports of header units recognizable at preprocessing time, and [[P1857R3]] defined `module` and `import` lines as directives wholesale, introducing spelling-less special tokens such as *module-keyword* and *import-keyword*, and restricting the shape of the directives. The goal of all these changes was to make dependency scanning require only preprocessing.
    - [[P3034R1]] forbade module and partition names from coming from macros, and required the name to be followed immediately by `;` or `[`. Before that, `export module MODNAME;` (with `MODNAME` a macro) was allowed, and a scanner had to reproduce all macro definitions exactly, including `-D` on the command line, to get the module name.

## Common misconceptions

!!! pitfall "Imports wrapped in conditional compilation"
    ```cpp
    export module m;
    #ifdef USE_FMT
    import fmt;
    #endif
    ```
    This is valid, but the result of dependency scanning depends on `USE_FMT`. Scanning must use the same macro definitions and command-line options as the real compilation, or the dependency graph is wrong. That's why build systems such as CMake always invoke the scanner with the full compile command.

!!! pitfall "export import of a header unit forwards its macros"
    It doesn't. `export import "a.h";` lets importers of the module see the declarations in `a.h`, but macros can only be obtained by importing the header unit directly. If you want users to get the macros, they have to write `import "a.h";` or `#include "a.h"` themselves.

## Questions

!!! question "Question 1"
    Let `ATTR` be a macro defined as `[[vendor::shiny]]` in the global module fragment. Which of these three module declarations are well-formed at the preprocessing level?
    ```cpp
    export module m ATTR;          // (a)
    export module m
    [[vendor::shiny]];             // (b)
    export module m.ATTR;          // (c)
    ```

<details markdown="1">
<summary>Answer</summary>

- (a) Well-formed. The module name `m` isn't a macro and isn't followed by `(`; after replacement by special tokens, the whole line is macro-expanded as ordinary text, `ATTR` becomes `[[vendor::shiny]]`, and the first token after the name is `[`, satisfying ¶2.
- (b) Well-formed. The first line is a directive whose module name `m` is followed by a newline; after replacement it becomes ordinary text, the next line continues it, and the first token after the name is `[`. This is the shape of Example 4 in ¶3.
- (c) Ill-formed. By the grammar, all of `m.ATTR` is the module name, and the `ATTR` in it is an object-like macro, violating ¶1.

In phase 7, (a) and (b) are both module declarations with attributes; unknown vendor attributes are handled per [[dcl.attr.grammar]], and Clang gives an unknown attribute warning and ignores it.
</details>

!!! question "Question 2"
    In the example's `e.h`, if `int c = Z;` is removed and replaced by `#undef Z`, is there still a problem?
    ```cpp
    import "a.h";
    import "d.h";
    #undef Z
    ```

<details markdown="1">
<summary>Answer</summary>

No problem. Paragraph 6 requires active definitions to agree only when the macro would be replaced or redefined; having two conflicting active definitions at the same time isn't itself a violation. `#undef Z` is neither a replacement nor a redefinition; by item 4.2 it's the point of undefinition of both #3 and #5, after which `Z` has no active definition and can be freely redefined.
</details>

## Summary

!!! summary
    - Lines beginning with `module` or `import` (optionally with `export`) that meet the conditions are preprocessing directives; when processed, these words are replaced by spelling-less special tokens, the line becomes ordinary text again, and it reaches phase 7 as a declaration.
    - Module and partition names can't contain object-like macros or be followed by `(`; the name must be followed by `;` or `[`.
    - The tokens after `import` are macro-expanded; importing a header unit has a point of macro import, importing a named module or partition doesn't, so named modules don't export macros.
    - In the body of a module unit, an import can't be produced by `#include`.
    - Macro definitions have points of definition and undefinition, imported along with header units; multiple active definitions of the same name must agree when used or redefined.
    - The purpose of all these restrictions is to make dependency scanning require only preprocessing.
