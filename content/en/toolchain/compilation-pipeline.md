---
title: From source to executable
summary: "The pipeline behind a single clang++ command: which subcommands the driver spawns, which phase of translation preprocessing, the AST, LLVM IR, assembly, object files and linking each correspond to, and how the header and module compilation models differ."
group: Toolchain
tags: toolchain, compilation pipeline, Clang, preprocessing, modules
updated: 2026-10-19
---

!!! tldr
    - `clang++` is a driver and doesn't compile anything itself: it assembles a `clang -cc1` compile command and a link command, and `-###` prints them.
    - In Clang, the standard's eight phases of translation ([[lex.phases]]) map roughly as follows: `-E` does phases 1–4, parsing and semantic analysis do phases 5–7, code generation produces the object file, and the linker does phase 8.
    - An object file is a translated translation unit: machine code, data, a symbol table and relocations. Translation units are connected only through symbol names.
    - The AST and LLVM IR spell out what the standard leaves invisible: implicit conversions, linkage, template instantiation, and optimization assumptions such as `nsw` and `mustprogress` that come from UB rules.
    - Headers are text, processed again in every translation unit; a module interface is compiled once, at the cost of an ordering between compilations.

!!! note "Test setup"
    Output is from Homebrew Clang 23.1.3 on macOS arm64. Where ELF/x86-64 output is needed, `--target=x86_64-linux-gnu` is added and we only compile without linking, since our test machine has no Linux linker or C runtime.

## Pipeline overview

The standard uses eight **phases of translation** ([[lex.phases]]) to describe how source files become a program. Footnote 7 says implementations need only behave as if the phases happened separately. Real compilers indeed don't consist of eight separate programs: one driver invokes two or three tools, and each tool merges several phases internally.

| Step | Command | Output | Phase of translation |
|---|---|---|---|
| Preprocessing | `clang++ -E` | `.ii` (preprocessed source) | Phases 1–4 |
| Parsing and semantic analysis | `-fsyntax-only`, `-Xclang -ast-dump` | AST, only in memory | The analysis part of phases 5–7 |
| Code generation | `-S -emit-llvm` | `.ll` (LLVM IR) | The translation part of phase 7 |
| Optimization and backend | `-S` | `.s` (assembly) | Phase 7 (implementation detail) |
| Assembly | `-c` | `.o` (object file) | The result of phase 7: a translated translation unit |
| Linking | `clang++ a.o b.o` | Executable or shared library | Phase 8 |

The first five steps happen within one **translation unit** (TU), which is a source file plus everything it `#include`s. Only the last step brings several TUs together. This is **separate compilation** ([[lex.separate]]): the compiler sees only one TU at a time, and function calls, global variables and vtables across TUs must wait for the linker to connect them by name.

That is why many rules in [[basic.link]] and [[basic.def.odr]] say no diagnostic is required (IFNDR): the evidence of a violation is spread across different TUs, which the compiler can't see together.

## The driver

`clang++` parses the command line, determines the target platform, finds the SDK and the standard library, and then assembles and runs the subcommands that do the actual work. `-###` prints these subcommands without running them:

```text
$ clang++ -std=c++2c -### hello.cpp -o hello
Homebrew clang version 23.1.3
Target: arm64-apple-darwin25.5.0
...
 "/opt/homebrew/Cellar/llvm/23.1.3_2/bin/clang-23" "-cc1" "-triple" "arm64-apple-macosx26.0.0"
   ... "-emit-obj" ... "-main-file-name" "hello.cpp" "-mrelocation-model" "pic" ...
   "-resource-dir" "/opt/homebrew/Cellar/llvm/23.1.3_2/lib/clang/23"
   "-isysroot" "/Library/Developer/CommandLineTools/SDKs/MacOSX26.sdk"
   "-internal-isystem" "/opt/homebrew/Cellar/llvm/23.1.3_2/bin/../include/c++/v1" ...
   "-std=c++2c" ... "-fcxx-exceptions" "-fexceptions" ...
   "-o" "/var/folders/.../T/hello-fc0c63.o" "-x" "c++" "hello.cpp"
 "/opt/homebrew/anaconda3/bin/ld" "-demangle" "-lto_library" ".../libLTO.dylib" "-no_deduplicate"
   "-dynamic" "-arch" "arm64" "-platform_version" "macos" "26.0.0" "26.5"
   "-syslibroot" "/Library/Developer/CommandLineTools/SDKs/MacOSX26.sdk"
   "-o" "hello" "/var/folders/.../T/hello-fc0c63.o" "-lc++" "-lSystem"
   ".../lib/clang/23/lib/darwin/libclang_rt.osx.a"
```

The first subcommand, `clang -cc1`, is the compiler proper, containing the frontend, the optimizer, the backend and an integrated assembler. `-emit-obj` means it goes from `.cpp` straight to `.o` in one process, without writing intermediate results to disk.

The second is the linker. The driver hands it the temporary `.o`, the C++ standard library (`-lc++`), the C runtime (`-lSystem`) and the compiler runtime (`libclang_rt.osx.a`).

!!! pitfall "Use -### to diagnose environment problems"
    The linker above is `/opt/homebrew/anaconda3/bin/ld`, an old ld64 bundled with Anaconda on `PATH` on our test machine (`ld -v` reports `ld64-530`), not the system's `/usr/bin/ld` (`ld-1266.8`). The driver looks up `ld` on `PATH` and so silently used it. When linking behaves differently from a colleague's machine, first use `-###` to see which tool is actually invoked; `--ld-path=/usr/bin/ld` specifies one explicitly. The experiments on this site's linking pages all use the system linker.

With a Linux target, the link command the driver assembles is completely different:

```text
$ clang++ -std=c++2c --target=x86_64-linux-gnu -### hello.cpp -o hello
 ... "-cc1" "-triple" "x86_64-unknown-linux-gnu" "-emit-obj" ... "-pic-is-pie" ...
 "/opt/homebrew/anaconda3/bin/ld" "--hash-style=gnu" "--eh-frame-hdr" "-m" "elf_x86_64" "-pie"
   "-dynamic-linker" "/lib64/ld-linux-x86-64.so.2" "-o" "hello" "Scrt1.o" "crti.o" "crtbeginS.o"
   "-L/usr/lib" "/var/folders/.../T/hello-140e83.o" "-lstdc++" "-lm" "-lgcc_s" "-lgcc" "-lc"
   "-lgcc_s" "-lgcc" "crtendS.o" "crtn.o"
```

This command would fail on our test machine; we only look at what the driver intends to do. The `crt*.o` files together with the C library form the startup and shutdown scaffolding around `main`. The program entry point `_start` is in these files; dynamic initialization of global objects ([[basic.start.dynamic]]) runs through them before `main`; and after `main` returns, `exit` is called. The standard says a program starts at `main`, but the entry point the operating system sees is `_start`.

### Splitting up each step

Internally the driver represents a compilation as a graph of actions, which `-ccc-print-phases` prints:

```text
$ clang++ -std=c++2c -ccc-print-phases hello.cpp -o hello
               +- 0: input, "hello.cpp", c++
            +- 1: preprocessor, {0}, c++-cpp-output
         +- 2: compiler, {1}, ir
      +- 3: backend, {2}, assembler
   +- 4: assembler, {3}, object
+- 5: linker, {4}, image
6: bind-arch, "arm64", {5}, image
```

By default steps 1–4 run in a single `-cc1` process. With `-save-temps`, the driver splits each step into a separate command and keeps the intermediate files:

```text
$ clang++ -std=c++2c -save-temps hello.cpp -o hello && ls
hello  hello.bc  hello.ii  hello.o  hello.s
```

`-###` then shows four `-cc1` subcommands (`-E` producing `hello.ii`, `-emit-llvm-bc` producing `hello.bc`, `-S` producing `hello.s`, `-cc1as` producing `hello.o`) and one link command. The sections below look at each step's output in order.

## Preprocessing (phases 1–4)

```cpp title="hello.cpp"
#include <cstdio>
#define GREETING "Hello, " "world"
static int square(int x) { return x * x; }
int main() {
    std::printf("%s %d\n", GREETING, square(7));
}
```

`-E` does only preprocessing:

```text
$ clang++ -std=c++2c -E hello.cpp -o hello.ii && wc -l hello.ii
     743 hello.ii
$ tail -6 hello.ii
# 2 "hello.cpp" 2

static int square(int x) { return x * x; }
int main() {
    std::printf("%s %d\n", "Hello, " "world", square(7));
}
```

One line of `#include <cstdio>` expanded to about 740 lines. Phase 4 specifies that `#include` makes the included file go through phases 1–4 recursively ([[cpp.include]]). The standard calls a source file together with all the headers it includes a **preprocessing translation unit** ([[lex.separate]]).

Macros have been expanded and preprocessing directives deleted, which is exactly the state at the end of phase 4. Lines such as `# 2 "hello.cpp" 2` are called **linemarkers**; they aren't C++ syntax and serve only to make later diagnostics point back to the original file. The trailing flags `1` and `2` mean entering and returning to a file, and `3` means a system header, where warnings are suppressed. `-P` removes linemarkers.

Note that `"Hello, " "world"` is still two string literals. Concatenating adjacent string literals belongs to phase 5, and Clang merges them only when it builds the string literal node during parsing. So the output of `-E` is just the text after preprocessing directives have been executed, and doesn't correspond exactly to the state at the end of any phase, another example of implementations only having to behave as if the phases were separate.

### How big is one `#include <iostream>`?

```text
$ printf '#include <iostream>\nint main(){ std::cout << "hi\\n"; }\n' > io.cpp
$ clang++ -std=c++2c -E io.cpp | wc -lc
   51627 2279972
```

Two lines of source become about 50,000 lines and 2.2 MB after preprocessing. `-H` prints every header inclusion with its nesting depth; for `io.cpp` it printed about 760 entries in our tests. Every TU that includes `<iostream>` has to preprocess and parse all of this again. That is the biggest cost of the header model, and the problem modules set out to solve.

### Header search paths

[[cpp.include]] says that `#include <...>` searches in an implementation-defined way. `-v` prints Clang's search list:

```text
$ clang++ -std=c++2c -fsyntax-only -v hello.cpp
...
#include "..." search starts here:
#include <...> search starts here:
 /opt/homebrew/Cellar/llvm/23.1.3_2/bin/../include/c++/v1
 /opt/homebrew/Cellar/llvm/23.1.3_2/lib/clang/23/include
 /Library/Developer/CommandLineTools/SDKs/MacOSX26.sdk/usr/include
 /Library/Developer/CommandLineTools/SDKs/MacOSX26.sdk/System/Library/Frameworks (framework directory)
 /Library/Developer/CommandLineTools/SDKs/MacOSX26.sdk/System/Library/SubFrameworks (framework directory)
End of search list.
```

The order decides which file is found:

1. libc++'s headers (`include/c++/v1`) come first, so `<cstdio>` finds libc++'s version first, which in turn includes `<stdio.h>`.
2. The compiler's own headers (`lib/clang/23/include`), such as `<stddef.h>`, `<stdarg.h>` and the various intrinsics headers. They depend on compiler internals and must match the compiler version.
3. The system C library's headers (the SDK's `usr/include`).

The `"..."` form first searches the directory of the current file, then directories given with `-iquote`, and finally falls back to the `<...>` list. Directories added with `-I` come before the system directories; directories added with `-isystem` are treated as system headers, with their warnings suppressed.

## Parsing and semantic analysis (phases 5–7)

`-fsyntax-only` stops after preprocessing, parsing and semantic analysis, without generating code. It is the fastest way to check whether code is well-formed; ill-formed programs are rejected at this step ([[intro.compliance]]).

`-Xclang -ast-dump` prints the **AST** (abstract syntax tree) after semantic analysis. `-Xclang` means the next argument is passed to `-cc1` as is.

```cpp title="sq.cpp"
static int square(int x) { return x * x; }
int api(int y) { return square(y) + 1; }
```

```text
$ clang++ -std=c++2c -fsyntax-only -Xclang -ast-dump sq.cpp
TranslationUnitDecl 0xa4cd3a008 <<invalid sloc>> <invalid sloc>
|-TypedefDecl ... implicit __int128_t '__int128'
...
|-FunctionDecl 0x7e4e813a0 <sq.cpp:1:1, col:42> col:12 used square 'int (int)' static internal-linkage
| |-ParmVarDecl 0x7e4e812b0 <col:19, col:23> col:23 used x 'int'
| `-CompoundStmt 0x7e4e81558 <col:26, col:42>
|   `-ReturnStmt 0x7e4e81548 <col:28, col:39>
|     `-BinaryOperator 0x7e4e81528 <col:35, col:39> 'int' '*'
|       |-ImplicitCastExpr 0x7e4e814f8 <col:35> 'int' <LValueToRValue>
|       | `-DeclRefExpr 0x7e4e814b8 <col:35> 'int' lvalue ParmVar 0x7e4e812b0 'x' 'int'
|       `-ImplicitCastExpr 0x7e4e81510 <col:39> 'int' <LValueToRValue>
|         `-DeclRefExpr 0x7e4e814d8 <col:39> 'int' lvalue ParmVar 0x7e4e812b0 'x' 'int'
`-FunctionDecl 0x7e4e81648 <line:2:1, col:40> col:5 api 'int (int)' external-linkage
  ...
      |-CallExpr 0x7e4e817e8 <col:25, col:33> 'int'
      | |-ImplicitCastExpr 0x7e4e817d0 <col:25> 'int (*)(int)' <FunctionToPointerDecay>
      | | `-DeclRefExpr 0x7e4e81778 <col:25> 'int (int)' lvalue Function 0x7e4e813a0 'square' 'int (int)'
```

Much of what the standard leaves implicit appears as explicit nodes in the AST, which makes it a good aid when reading the standard:

- The root node `TranslationUnitDecl` corresponds to phase 7's "the tokens constitute a translation unit". Before the user's declarations comes a series of implicit types the compiler predeclares, such as `__int128_t`.
- `square` is marked `internal-linkage` and `api` `external-linkage`, consistent with [[basic.link#3]] and [[basic.link#4]].
- `DeclRefExpr ... lvalue` says `x` is an lvalue, wrapped in an `ImplicitCastExpr <LValueToRValue>`: that is the lvalue-to-rvalue conversion ([[conv.lval]]). The function name `square` is an lvalue of type `int (int)`, which goes through `<FunctionToPointerDecay>` to become a function pointer before it is called ([[conv.func]], [[expr.call]]).
- The `used` mark on functions roughly corresponds to [[g:odr-use]] ([[basic.def.odr]]).

### Template instantiation

Phase 7 also includes the template instantiations needed for execution. `-ast-dump-filter` prints only declarations whose names match, which is the most convenient way to look at instantiations:

```cpp title="tpl.cpp"
template <class T> T twice(T x) { return x + x; }
int use() { return twice(21); }
```

```text
$ clang++ -std=c++2c -fsyntax-only -Xclang -ast-dump -Xclang -ast-dump-filter=twice tpl.cpp
Dumping twice:
FunctionTemplateDecl 0x9a2e81568 <tpl.cpp:1:1, col:49> col:22 twice external-linkage
|-TemplateTypeParmDecl 0x9a2e81298 <col:11, col:17> col:17 referenced class depth 0 index 0 T
|-FunctionDecl 0x9a2e814b8 <col:20, col:49> col:22 twice 'T (T)'
| ...
|     `-BinaryOperator 0x9a2e816d8 <col:42, col:46> '<dependent type>' '+'
`-FunctionDecl 0x9a2e81a58 <col:20, col:49> col:22 used twice 'int (int)' implicit_instantiation instantiated_from 0x9a2e814b8 external-linkage
  |-TemplateArgument type 'int'
  ...
      `-BinaryOperator 0x9a2e81cf8 <col:42, col:46> 'int' '+'
        |-ImplicitCastExpr 0x9a2e81cc8 <col:42> 'int' <LValueToRValue>
```

In the template definition, `x + x` has type `<dependent type>`: it can't be analyzed until `T` is known ([[temp.dep]]). The `twice<int>` produced by implicit instantiation ([[temp.inst]]) is a separate subtree in which every type is known. Instantiation means copying and substituting a new declaration in the AST; afterwards it is like an ordinary function, and code is generated for it separately too.

## Generating LLVM IR (phase 7)

Code generation turns the AST into **LLVM IR**, an intermediate representation independent of the source language and largely independent of the target machine. `-S -emit-llvm` outputs it as text:

```text
$ clang++ -std=c++2c --target=x86_64-linux-gnu -S -emit-llvm -O0 sq.cpp -o -
; ModuleID = 'sq.cpp'
source_filename = "sq.cpp"
target datalayout = "e-m:e-p270:32:32-p271:32:32-p272:64:64-i64:64-i128:128-f80:128-n8:16:32:64-S128"
target triple = "x86_64-unknown-linux-gnu"

; Function Attrs: mustprogress noinline optnone uwtable
define dso_local noundef i32 @_Z3apii(i32 noundef %0) #0 {
  %2 = alloca i32, align 4
  store i32 %0, ptr %2, align 4
  %3 = load i32, ptr %2, align 4
  %4 = call noundef i32 @_ZL6squarei(i32 noundef %3)
  %5 = add nsw i32 %4, 1
  ret i32 %5
}

; Function Attrs: mustprogress noinline nounwind optnone uwtable
define internal noundef i32 @_ZL6squarei(i32 noundef %0) #1 {
  ...
  %5 = mul nsw i32 %3, %4
  ret i32 %5
}
```

Many markers in the IR come straight from the standard's rules; here you can see semantic rules turn into optimization assumptions:

| Marker in the IR | Source |
|---|---|
| Names become `_Z3apii`, `_ZL6squarei` | Name mangling, see [[toolchain/name-mangling]]; `L` means internal linkage |
| `define internal` versus `define dso_local` | Internal versus external linkage ([[basic.link]]) |
| `add nsw`, `mul nsw` (no signed wrap) | A result outside the type's range of representable values is UB ([[expr.pre#4]]), so the compiler may assume signed arithmetic doesn't overflow |
| `mustprogress` | The forward progress guarantee ([[intro.progress]]): an infinite loop without side effects may be assumed to terminate |
| `noundef` | Reading an indeterminate value is UB or erroneous behavior ([[basic.indet]]), so arguments are assumed to be determinate values |
| `nounwind` (only on `square`) | The compiler inferred that it doesn't throw |

At `-O0` every parameter is first `store`d to the stack and then `load`ed back, a literal implementation of objects occupying storage in the abstract machine. With optimization on:

```text
$ clang++ -std=c++2c --target=x86_64-linux-gnu -S -emit-llvm -O2 sq.cpp -o -
define dso_local noundef range(i32 -2147483647, -2147483648) i32 @_Z3apii(i32 noundef %0) local_unnamed_addr #0 {
  %2 = mul nsw i32 %0, %0
  %3 = add nuw nsw i32 %2, 1
  ret i32 %3
}
```

After inlining, `square` disappears entirely. It has internal linkage, no other TU can refer to it, and once inlined there is no reason to keep it. `api`, with external linkage, must be kept, because the linker may need to connect calls in other TUs to it. `-Rpass=inline` makes the optimizer report this decision.

`+1` has gained `nuw`. Because `x * x` carries `nsw`, the optimizer deduces that the product is non-negative, so `+1` can't wrap as unsigned either. The rule that signed overflow is UB has become a premise of the reasoning here.

## Assembly and object files (the result of phase 7)

The backend translates IR into target machine instructions. `-S` outputs assembly:

```text
$ clang++ -std=c++2c --target=x86_64-linux-gnu -S -O2 sq.cpp -o -
	.text
	.globl	_Z3apii                         # -- Begin function _Z3apii
	.type	_Z3apii,@function
_Z3apii:                                # @_Z3apii
	.cfi_startproc
# %bb.0:
	imull	%edi, %edi
	leal	1(%rdi), %eax
	retq
.Lfunc_end0:
	.size	_Z3apii, .Lfunc_end0-_Z3apii
	.cfi_endproc
```

`.globl` declares a global symbol, which is what external linkage looks like in assembly. The `.cfi_*` directives describe the layout of the stack frame, used by exception handling and debuggers to unwind the call stack (see [[toolchain/exception-implementation]]).

`-c` then has the assembler produce an object file:

```text
$ clang++ -std=c++2c --target=x86_64-linux-gnu -c -O2 sq.cpp -o sq.o
$ file sq.o
sq.o: ELF 64-bit LSB relocatable, x86-64, version 1 (SYSV), not stripped
$ llvm-nm sq.o
0000000000000000 T _Z3apii
$ llvm-objdump -d --no-show-raw-insn sq.o
0000000000000000 <_Z3apii>:
       0:      	imull	%edi, %edi
       3:      	leal	0x1(%rdi), %eax
       6:      	retq
```

The object file is what the standard calls a **translated translation unit** ([[lex.separate]]; note 4 in phase 7). It contains machine code and data, a **symbol table** recording which names this TU defines and which it refers to, and **relocation** records marking which addresses can only be filled in at link time. "relocatable" in the `file` output refers to the latter. Details of symbols, sections and relocations are in [[toolchain/linking-and-symbols]].

## Linking (phase 8)

Phase 8 ([[lex.phases#1]]) combines the translated TUs, resolves all references to external entities, links library components to satisfy undefined references, and finally produces a program image. That is exactly what the linker does:

- match each undefined (`U`) symbol in every `.o` with a definition in some `.o` or library;
- merge entities that may be defined in several TUs, such as inline functions, template instantiations and vtables (COMDAT groups in ELF, weak definitions in Mach-O);
- fix up relocations with the final addresses;
- for shared libraries, record only which library to look in at run time, deferring the actual binding to load time.

The standard has no concept of shared libraries; in its model the program image is complete before execution. The undefined references and duplicate definitions commonly seen at link time mostly correspond to violations in [[basic.def.odr]] that require no diagnostic. The linker can often report them only because these violations happen to be visible at the symbol level.

## Headers and modules

The `#include <iostream>` example shows the problem with the header model: headers are text, and every TU has to run phases 1–7 on them again. C++20 **modules** ([[module.unit]]) instead compile once and import many times. A module interface unit is compiled into a **BMI** (binary module interface, a `.pcm` file in Clang), and importers read the already-analyzed declarations from it directly.

```cpp title="m.cppm"
export module m;
export int answer() { return 42; }
int helper() { return 1; }
```

```cpp title="use.cpp"
import m;
int main() { return answer() - 42; }
```

```text
$ clang++ -std=c++2c --precompile m.cppm -o m.pcm         # interface → BMI
$ clang++ -std=c++2c -c m.pcm -o m.o                       # BMI → object file (function bodies in the module)
$ clang++ -std=c++2c -fmodule-file=m=m.pcm -c use.cpp -o use.o
$ clang++ m.o use.o -o app && ./app; echo rc=$?
rc=0
$ nm m.o
0000000000000010 S __ZGIW1m
0000000000000008 T __ZW1m6answerv
0000000000000000 T __ZW1m6helperv
...
```

Without `-fmodule-file`, compiling `use.cpp` fails with `fatal error: module 'm' not found`. The module must be compiled before its importers, which gives the build system a compilation-order problem. `clang++ -std=c++2c -c m.cppm -fmodule-output -o m.o` produces both the `.o` and the `.pcm` in one step.

These points map onto the standard:

- A module interface unit is also a TU and also produces an object file; the BMI is an extra product. Phase 7 says it is implementation-defined whether the source of module units that are depended on must be available. Clang's choice is to require the BMI, not the source.
- `W1m` in the symbol names means the entity is **attached to** module `m` ([[basic.link#10]], [[module.unit]]); the encoding is described in [[toolchain/name-mangling]]. `helper` isn't exported, but it is a global `T` symbol all the same. Exporting doesn't affect symbol names; importers not seeing it is guaranteed by the compiler's name lookup and has nothing to do with the linker.
- `_ZGIW1m` is the module's initialization function. Importers call it before initializing their own global variables ([[basic.start.dynamic]]).

The standard library module `import std;` {{c++23}} works too. The libc++ on our test machine ships its source at `share/libc++/v1/std.cppm`, which you must precompile into `std.pcm` yourself; that took about 1 second and produced a file of about 37 MB. In a rough comparison with `-fsyntax-only`, the `#include <print>` version took about 0.3 s of user CPU time and the `import std;` version about 0.12 s, even though the latter imports the entire standard library.

Between the two there are **header units** (`import <vector>;`, [[module.import]]): a header compiled as a module. They still export macros, which makes migration smooth, but build-system support is less mature than for named modules. The kinds of BMI, dependency scanning and CMake integration are covered in [[toolchain/modules-in-practice]].

## Summary

| To see | Use |
|---|---|
| The subcommands the driver actually runs | `-###` |
| Header search paths | `-v` |
| Phases and intermediate files | `-ccc-print-phases`, `-save-temps` |
| Preprocessing output (phases 1–4) | `-E` (without phase 5's string concatenation) |
| Only checking well-formedness | `-fsyntax-only` |
| Implicit conversions, linkage, instantiation | `-Xclang -ast-dump` |
| Optimization assumptions derived from UB rules | `-S -emit-llvm` |
| Symbol table and machine code | `-c`, then `llvm-nm`, `llvm-objdump` |
