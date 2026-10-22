---
title: Object files, symbols and linking
summary: "What object files contain, how C++ linkage and the ODR turn into symbol binding, COMDAT groups and weak definitions, what undefined references and duplicate definitions are in the standard, which violations the linker silently accepts, and how static libraries, shared libraries and symbol visibility behave."
group: Toolchain
tags: toolchain, linking, symbols, ELF, Mach-O, ODR, shared libraries
updated: 2026-10-19
---

!!! tldr
    - An object file consists of sections, a symbol table and relocations. Names with external linkage become global symbols, names with internal linkage local symbols, and the linker matches across files using global symbols only.
    - Inline functions, template instantiations, inline variables and the vtables of classes without a key function have a copy in every TU that uses them, handed to the linker for deduplication as weak definitions or COMDAT groups.
    - Undefined references and duplicate definitions correspond to rules in [[basic.def.odr]] that require no diagnostic. The linker can report them only because they happen to be visible at the symbol level.
    - The linker compares only names, not contents or types. Inconsistent inline definitions, unreachable explicit specializations, and mismatched variable or return types all link without complaint and produce a wrong program.
    - Static libraries are extracted member by member; visibility and symbol interposition in shared libraries are mechanisms outside the standard, and they break the "one entity per program" model at library boundaries.

The standard never mentions symbols, object files or linkers. It uses **linkage** ([[basic.link]]) to describe whether a name can denote the same entity from other scopes and other TUs, and the ODR ([[basic.def.odr]]) to govern the number of definitions in the whole program. Both sets of rules are designed to make it possible to compile each TU separately into an object file and then stitch them together with a program that looks only at names.

Where object files come from is covered in [[toolchain/compilation-pipeline]]; how symbol names are encoded in [[toolchain/name-mangling]].

!!! note "Test setup"
    ELF output comes from `clang++ --target=x86_64-linux-gnu -c` (Homebrew Clang 23.1.3) and is inspected with `llvm-readelf`, `llvm-nm` and `llvm-objdump`. Our test machine can't link Linux programs, so anything about the run-time behavior of GNU ld, lld or the dynamic loader is marked as based on documentation. Mach-O output comes from native compilation, and link experiments use the system linker `/usr/bin/ld` (`ld-1266.8`), selected with `--ld-path=/usr/bin/ld`.

## What is in an object file

A relocatable object file (`.o`) mainly contains three things:

1. **Sections**: blocks of bytes with attributes, such as code, initialized data and read-only data;
2. **A symbol table**: which names this TU defines (in which section, at what offset) and which undefined names it refers to;
3. **Relocations**: records in the machine code or data saying "the address of some symbol goes here, to be filled in at link time".

The TU below covers most common cases:

```cpp title="sec.cpp"
int counter = 42;                 // initialized, nonzero
int zeroed;                       // zero-initialized
const int table[4] = {1, 2, 3, 4};
extern const int exported_k = 7;  // const with external linkage
static int hidden_count = 1;      // internal linkage
namespace { int anon_var = 2; }
static int bump() { return ++hidden_count + anon_var; }
inline int version() { return 3; }
template <class T> T twice(T x) { return x + x; }
extern int elsewhere;             // declared only
int get_elsewhere();
int api() { return counter + zeroed + table[2] + bump() + version()
                 + twice(1) + elsewhere + get_elsewhere(); }
```

### Sections

```text
$ clang++ -std=c++2c --target=x86_64-linux-gnu -O0 -c sec.cpp -o sec.o
$ llvm-readelf -S -W sec.o
  [Nr] Name              Type            Address          Off    Size   ES Flg Lk Inf Al
  [ 2] .text             PROGBITS        0000000000000000 000040 00008b 00  AX  0   0 16
  [ 3] .rela.text        RELA            0000000000000000 0003b0 0000f0 18   I 16   2  8
  [ 4] .group            GROUP           0000000000000000 0001d8 000008 04     16  14  4
  [ 5] .text._Z7versionv PROGBITS        0000000000000000 0000d0 00000b 00 AXG  0   0 16
  [ 6] .group            GROUP           0000000000000000 0001e0 000008 04     16  15  4
  [ 7] .text._Z5twiceIiET_S0_ PROGBITS   0000000000000000 0000e0 00000f 00 AXG  0   0 16
  [ 8] .data             PROGBITS        0000000000000000 0000f0 00000c 00  WA  0   0  4
  [ 9] .bss              NOBITS          0000000000000000 0000fc 000004 00  WA  0   0  4
  [10] .rodata           PROGBITS        0000000000000000 000100 000020 00   A  0   0 16
  ...
  [13] .eh_frame         X86_64_UNWIND   0000000000000000 000140 000098 00   A  0   0  8
  [16] .symtab           SYMTAB          0000000000000000 0001e8 0001c8 18      1  11  8
```

A natively compiled Mach-O object file uses a different set of names:

```text
$ clang++ -std=c++2c -O0 -c sec.cpp -o sec_macho.o && llvm-objdump -h sec_macho.o
Idx Name             Size     VMA              Type
  0 __text           000000d4 0000000000000000 TEXT
  1 __data           0000000c 00000000000000d4 DATA
  2 __common         00000004 0000000000000178 BSS
  3 __const          00000014 00000000000000e0 DATA
  4 __compact_unwind 00000080 00000000000000f8 DATA
```

| Content | ELF section | Mach-O (segment,section) | Entities in this example |
|---|---|---|---|
| Machine code | `.text`, `.text.<name>` | `__TEXT,__text` | `api`, `bump`; in ELF, `version` and `twice<int>` each have their own section |
| Initialized writable data | `.data` | `__DATA,__data` | `counter`, `hidden_count`, `anon_var`, 12 bytes in total |
| Zero-initialized data | `.bss` (takes no space in the file) | `__DATA,__common` | `zeroed` |
| Read-only data | `.rodata` | `__TEXT,__const` | `table`, `exported_k` |
| Unwind information | `.eh_frame` | `__LD,__compact_unwind` | Frame descriptions for each function |

The division into sections directly reflects static initialization ([[basic.start.static]]). Zero-initialized objects with static storage duration need no bytes in the file at all; the loader just allocates zeroed memory, which is `.bss`. The constant-initialized `counter = 42` has `42` written directly in `.data`, so it is already 42 when the program starts, without running any code. Only dynamically initialized variables need code to run at startup.

`.rela.text` is the relocation table for `.text`; every reference in `api` to `counter`, `elsewhere`, `get_elsewhere` and so on has a record there. `.group` is a COMDAT group, covered later.

### The symbol table

```text
$ llvm-readelf -s -W sec.o
   Num:    Value          Size Type    Bind   Vis       Ndx Name
     3: 0000000000000010    16 OBJECT  LOCAL  DEFAULT    10 _ZL5table
     4: 0000000000000070    27 FUNC    LOCAL  DEFAULT     2 _ZL4bumpv
     5: 0000000000000004     4 OBJECT  LOCAL  DEFAULT     8 _ZL12hidden_count
     6: 0000000000000008     4 OBJECT  LOCAL  DEFAULT     8 _ZN12_GLOBAL__N_18anon_varE
    11: 0000000000000000   106 FUNC    GLOBAL DEFAULT     2 _Z3apiv
    12: 0000000000000000     4 OBJECT  GLOBAL DEFAULT     8 counter
    13: 0000000000000000     4 OBJECT  GLOBAL DEFAULT     9 zeroed
    14: 0000000000000000    11 FUNC    WEAK   DEFAULT     5 _Z7versionv
    15: 0000000000000000    15 FUNC    WEAK   DEFAULT     7 _Z5twiceIiET_S0_
    16: 0000000000000000     0 NOTYPE  GLOBAL DEFAULT   UND elsewhere
    17: 0000000000000000     0 NOTYPE  GLOBAL DEFAULT   UND _Z13get_elsewherev
    18: 0000000000000000     4 OBJECT  GLOBAL DEFAULT    10 exported_k
```

The `Bind` column is the symbol's **binding**: `GLOBAL` takes part in cross-file matching, `LOCAL` is valid only within this file, and `WEAK` is a weak definition that may appear more than once. `UND` in `Ndx` means undefined: this TU refers to it, and it is defined elsewhere.

`nm` summarizes the same information in one letter, uppercase for global and lowercase for local:

```text
$ llvm-nm sec.o
                 U _Z13get_elsewherev
0000000000000000 T _Z3apiv
0000000000000000 W _Z5twiceIiET_S0_
0000000000000000 W _Z7versionv
0000000000000004 d _ZL12hidden_count
0000000000000070 t _ZL4bumpv
0000000000000010 r _ZL5table
0000000000000008 d _ZN12_GLOBAL__N_18anon_varE
0000000000000000 D counter
                 U elsewhere
0000000000000000 R exported_k
0000000000000000 B zeroed
```

| Letter | Meaning |
|---|---|
| `T`/`t` | Definition in a code section |
| `D`/`d` | Definition in an initialized data section |
| `B`/`b` | Definition in `.bss` |
| `R`/`r` | Definition in read-only data |
| `W` / `V` | Weak definition (function / object) |
| `U` | Undefined |

## How C++ linkage becomes symbols

Comparing the output above with [[basic.link]]:

| Case in C++ | The standard's conclusion | Symbol |
|---|---|---|
| Ordinary function `api()`, variable `counter` | External linkage ([[basic.link#4]]) | `GLOBAL` |
| `static` function or variable | Internal linkage ([[basic.link#3]]) | `LOCAL`, mangled name contains `L`: `_ZL4bumpv` |
| Entities in an unnamed namespace | Internal linkage ([[basic.link#4]]) | `LOCAL`, name contains `_GLOBAL__N_1` |
| Non-inline, non-`extern` `const` variable at namespace scope | Internal linkage ([[basic.link#3]]) | `LOCAL`: `_ZL5table` |
| `extern const int exported_k = 7;` | External linkage | `GLOBAL` |
| Inline functions, implicit instantiations of function templates | External linkage, may be defined in several TUs ([[basic.def.odr#16]]) | `WEAK`, in a COMDAT group |
| Declared but not defined | Defined in another TU | `UND` |

The linker ignores `LOCAL` symbols when matching; they serve only to show names in debuggers and disassembly. So each TU's own `static int bump()` doesn't interfere with the others at link time; that is how internal linkage is implemented.

The variable names `counter`, `zeroed` and `elsewhere` in the global namespace aren't mangled, just like C variable names. [[dcl.link#7]] says a variable with C language linkage and a variable of the same name declared at global scope are the same entity. At the symbol level they couldn't be told apart anyway.

### Entities allowed multiple definitions

`version()` is an inline function and `twice<int>` an implicitly instantiated template specialization. Every TU that uses them has a definition, which the ODR allows as long as the definitions are the same everywhere ([[basic.def.odr#16]]). The linker needs a mechanism to merge the copies into one without reporting duplicate definitions.

In LLVM IR, Clang marks them `linkonce_odr`:

```text
$ clang++ -std=c++2c --target=x86_64-linux-gnu -O0 -S -emit-llvm sec.cpp -o - | grep -E '^(@|define|declare|\$)'
$_Z7versionv = comdat any
$_Z5twiceIiET_S0_ = comdat any
@counter = dso_local global i32 42, align 4
@zeroed = dso_local global i32 0, align 4
@exported_k = dso_local constant i32 7, align 4
@_ZL5table = internal constant [4 x i32] [i32 1, i32 2, i32 3, i32 4], align 16
@elsewhere = external global i32, align 4
@_ZL12hidden_count = internal global i32 1, align 4
@_ZN12_GLOBAL__N_18anon_varE = internal global i32 2, align 4
define dso_local noundef i32 @_Z3apiv() #0 {
define internal noundef i32 @_ZL4bumpv() #1 {
define linkonce_odr dso_local noundef i32 @_Z7versionv() #1 comdat {
define linkonce_odr dso_local noundef i32 @_Z5twiceIiET_S0_(i32 noundef %0) #1 comdat {
declare noundef i32 @_Z13get_elsewherev() #2
```

The two halves of the name correspond exactly to the standard's meaning. linkonce means that only one of several copies is kept at link time, and it can be discarded if unused, so at `-O2`, once `version()` is inlined, it may not appear in the object file at all. odr means the compiler may assume all copies are equivalent, which is exactly the guarantee the ODR provides; the optimizer can therefore inline and reason based on the definition it sees in this TU.

In ELF this is implemented in two layers. The symbol is `WEAK`, and the section containing it goes into a **COMDAT group** whose signature is the symbol name:

```text
$ llvm-readelf -g sec.o
COMDAT group section [    4] `.group' [_Z7versionv] contains 1 sections:
   [Index]    Name
   [    5]   .text._Z7versionv

COMDAT group section [    6] `.group' [_Z5twiceIiET_S0_] contains 1 sections:
   [Index]    Name
   [    7]   .text._Z5twiceIiET_S0_
```

When the linker sees groups with the same signature, it keeps only the first and discards the rest wholesale, including the code and data in the groups. Mach-O has no COMDAT; the counterpart is a **weak definition**, which `nm -m` shows as `weak external`:

```text
$ nm -m sec_macho.o
00000000000000b8 (__TEXT,__text) weak external __Z5twiceIiET_S0_
00000000000000b0 (__TEXT,__text) weak external __Z7versionv
00000000000000d8 (__DATA,__data) non-external __ZL12hidden_count
0000000000000000 (__TEXT,__text) external __Z3apiv
...
```

!!! pitfall "macOS's nm shows weak definitions as T without -m"
    The `/usr/bin/nm` on our test machine (Apple's version) shows the weak definitions above as `T __Z7versionv`, just like ordinary external functions. To see weak definitions, use `nm -m`, or use `llvm-nm`, which shows `W`.

The Itanium C++ ABI calls these entities, generated in every TU that uses them and deduplicated by the linker, **vague linkage**. It covers more than inline functions:

```cpp title="vague.cpp"
struct Shape { virtual ~Shape() = default; virtual int area() const { return 0; } };
inline int inline_var = 5;
inline int& counter() { static int n = 0; return n; }
template <class T> struct Box { static inline T value{}; };
int use() { Shape s; return s.area() + inline_var + ++counter() + Box<int>::value; }
```

```text
$ clang++ -std=c++2c --target=x86_64-linux-gnu -O0 -c vague.cpp -o vague.o && llvm-nm -C vague.o
0000000000000000 T use()
0000000000000000 W counter()
0000000000000000 V Box<int>::value
0000000000000000 W Shape::Shape()
0000000000000000 W Shape::~Shape()
0000000000000000 W Shape::~Shape()
0000000000000000 W Shape::area() const
0000000000000000 V typeinfo for Shape
0000000000000000 V typeinfo name for Shape
0000000000000000 V vtable for Shape
                 U vtable for __cxxabiv1::__class_type_info
0000000000000000 V counter()::n
                 U operator delete(void*, unsigned long)
0000000000000000 V inline_var
```

Inline variables ([[dcl.inline]]), inline static data members of class templates, implicitly defined special member functions, and the vtable and typeinfo of a class without a key function are all `W` or `V`. The static local variable `counter()::n` in an inline function is among them too: all TUs must share the same `n`, otherwise `++counter()` would increment different objects in different TUs.

The two `Shape::~Shape()` are the complete object destructor and the deleting destructor, see [[toolchain/name-mangling]]; when a vtable has vague linkage is covered in [[toolchain/object-layout-and-vtables]].

## What the two link errors are in the standard

The experiments below use a few small files: `m.cpp` calls `helper()` and `missing(int)`; `x.cpp` defines a `helper()` returning 1, and `y.cpp` a `helper()` returning 2; `mi.cpp` defines `missing(int)`, returning its argument.

```cpp title="m.cpp"
int helper();
int missing(int);
int main() { return helper() + missing(3); }
```

### Undefined references

```text
$ clang++ --ld-path=/usr/bin/ld x.o m.o -o t
Undefined symbols for architecture arm64:
  "missing(int)", referenced from:
      _main in m.o
ld: symbol(s) not found for architecture arm64
clang++: error: linker command failed with exit code 1 (use -v to see invocation)
```

`__Z7missingi` in `m.o` is `U`, and no input has a definition. The corresponding standard rule is [[basic.def.odr#12]]: every function or variable that is odr-used in the program must have at least one definition, and a violation is {{ifndr}}. No diagnostic is required because the standard can't assume the implementation has a linker, still less that it can see all the code. In practice the linker can almost always report it. GNU ld's wording is ``undefined reference to `missing(int)'`` (according to documentation).

The same rule also explains when no definition is needed. A function that is declared but never odr-used, for example appearing only in `sizeof` or `decltype`, needs no definition. Virtual functions are different: a non-pure virtual function is always odr-used ([[basic.def.odr#8]]), because the vtable must hold its address, so [[class.virtual#12]] requires it to be defined or declared pure. When a key function's definition is forgotten, Apple ld on our test machine reports:

```text
Undefined symbols for architecture arm64:
  "vtable for W", referenced from:
      W::W() in vt-530b09.o
   NOTE: a missing vtable usually means the first non-inline virtual member function has no definition.
```

### Duplicate definitions

```text
$ clang++ --ld-path=/usr/bin/ld x.o y.o m.o mi.o -o t
duplicate symbol 'helper()' in:
    /private/var/folders/.../link/err/y.o
    /private/var/folders/.../link/err/x.o
ld: 1 duplicate symbols
clang++: error: linker command failed with exit code 1 (use -v to see invocation)
```

Two `GLOBAL` definitions with the same name, neither of them weak. The corresponding rule is [[basic.def.odr#16]]: a non-inline, non-template function or variable may not have more than one definition in the program, and a violation is likewise {{ifndr}}. GNU ld's wording is ``multiple definition of `helper()'`` (according to documentation).

Defining something twice in the same TU violates [[basic.def.odr#2]], which the compiler must diagnose. Across TUs it becomes IFNDR, because the compiler can't see other TUs. The linker can find two strong definitions because this violation happens to be visible at the symbol level. Once the definition is inline, the symbol becomes a weak definition and the linker can't see the problem anymore.

## Violations the linker can't see

The linker looks only at symbol names and bindings, and never compares contents, types or sizes. As long as a violation doesn't change a symbol name, it is invisible to the linker. The implementation-perspective section of [[basic.def.odr]] demonstrates the consequences of same-named inline functions with different definitions, and same-named classes with different layouts, in two TUs. Here are two other common cases.

### An explicit specialization visible in only some TUs

```cpp title="twice.h"
template <class T> T twice(T x) { return x + x; }
```

```cpp title="a.cpp" ifndr
#include "twice.h"
int from_a() { return twice(10); }      // implicitly instantiates twice<int>
```

```cpp title="b.cpp" ifndr
#include "twice.h"
template <> int twice<int>(int x) { return -x; }  // explicit specialization, visible only in b.cpp
int from_b() { return twice(10); }
```

`main` prints `from_a()` and `from_b()`:

```text
$ for O in -O0 -O2; do clang++ -std=c++2c $O a.cpp b.cpp main.cpp -o t && echo "$O: $(./t)"; done
-O0: -10 -10
-O2: 20 -10
$ nm -m a.o b.o | grep twice
0000000000000018 (__TEXT,__text) weak external __Z5twiceIiET_S0_      ← a.o: implicit instantiation
0000000000000000 (__TEXT,__text) external __Z5twiceIiET_S0_           ← b.o: explicit specialization
```

[[temp.expl.spec#7]] requires the declaration of an explicit specialization to be reachable at every use that would cause an implicit instantiation, otherwise {{ifndr}}. `a.cpp` violates this.

At the symbol level, an explicit specialization is an ordinary function and produces a strong definition; an implicit instantiation produces a weak definition. The linker's rule is that when there is a strong definition, all weak definitions give way, without an error, and regardless of link order (putting `b.cpp` first gives the same result). So at `-O0`, `from_a` calls b's specialization; at `-O2`, the call in `from_a` has already been inlined to the primary template a itself sees. Even `-Wall -Wextra` gives no warning.

### Symbol names don't include types

```cpp title="def.cpp" ifndr
double ratio() { return 2.5; }
long long big = 0x100000001;
```

```cpp title="use.cpp" ifndr
#include <cstdio>
int ratio();          // return type differs from the definition
extern int big;       // type differs from the definition
int main() { std::printf("%d %d\n", ratio(), big); }
```

```text
$ clang++ -std=c++2c -Wall -Wextra def.cpp use.cpp -o t && ./t
1 1
$ nm def.o use.o | grep -E 'ratio|big'
0000000000000000 T __Z5ratiov
0000000000000008 D _big
                 U __Z5ratiov
                 U _big
```

Itanium ABI mangled names include neither the return type of a non-template function nor the type of a variable ([[toolchain/name-mangling]]), so the symbol names on both sides are identical and linking succeeds. This violates [[basic.link#11]]: all declarations of the same entity must have the same type, and no diagnostic is required when the two declarations aren't reachable from each other.

In the output, `big` reads the low 4 bytes of `0x100000001`, which is 1 on a little-endian machine. `ratio()`'s `double` return value is placed in the floating-point register `d0` on arm64, but the caller reads the integer register `w0`, getting whatever was left there, unrelated to 2.5.

!!! tip "Prevention"
    Both problems have the same fix: write the declaration in only one header, and have the `.cpp` that defines it include that header too. The definition and the declaration then meet in the same TU, and any inconsistency becomes an error the compiler must diagnose. MSVC's mangled names include return types and variable types (see [[toolchain/name-mangling]]), so on MSVC these inconsistencies usually show up as link errors.

## Static libraries

A static library (`.a`) is just an archive of object files, plus an index of "which symbol is in which member":

```text
$ llvm-ar rcs libh.a x.o mi.o && llvm-ar t libh.a
x.o
mi.o
$ llvm-nm --print-armap libh.a | head -3
Archive map
__Z6helperv in x.o
__Z7missingi in mi.o
```

The linker treats `.o` files and static libraries differently. All `.o` files on the command line are linked in; a member of a static library is extracted only if it resolves a currently undefined symbol, and only as a whole member.

A member that isn't extracted may as well not exist. Below, `y.o` already defines `helper()`, and `x.o` in the library defines it too, yet there is no duplicate definition error:

```text
$ clang++ --ld-path=/usr/bin/ld m.o y.o libh.a -o t && ./t; echo rc=$?
rc=5
```

`helper()` comes from `y.o` and returns 2; `missing` comes from `mi.o` in the library and returns 3; `x.o` is never extracted. This mechanism is intentional. The standard allows programs to replace the global `operator new` and other replaceable functions ([[replacement.functions]]), and one way to implement that is to put the default versions in a library so that the user's definitions win by coming first.

Members are indivisible. Put `helper` and `missing` in the same member `xm.o`:

```text
$ clang++ --ld-path=/usr/bin/ld m.o y.o libxm.a -o t
duplicate symbol 'helper()' in:
    /private/var/folders/.../link/err/y.o
    /private/var/folders/.../link/err/libxm.a[2](xm.o)
ld: 1 duplicate symbols
```

`xm.o` was extracted for `missing`, and the `helper()` it brought along collides with `y.o`.

### Link order

Apple ld on our test machine doesn't care where a static library appears on the command line; with the library before `m.o`, it still finds `helper` and `missing`:

```text
$ clang++ --ld-path=/usr/bin/ld libh.a m.o -o t && ./t; echo rc=$?
rc=4
```

GNU ld's traditional behavior is different (according to documentation). It scans from left to right, and when processing a static library it only uses it to resolve the undefined symbols known at that moment, never going back. So `ld libh.a m.o` reports undefined references, because there are no undefined symbols yet when `libh.a` is processed. The Linux lore that "libraries go after the object files that use them" and "mutually dependent libraries must be listed twice or wrapped in `--start-group ... --end-group`" all comes from this. LLVM's lld on ELF uses an order-independent strategy similar to Apple ld's (according to lld's documentation).

All of this is outside the standard. Phase 8 ([[lex.phases#1]]) only says library components are linked to satisfy references to external entities, without specifying a search order.

## Shared libraries and symbol visibility

A shared library (`.so`, `.dylib`) is the product of a completed link. References within the library have been resolved, and only a table of exported symbols is exposed. By default every symbol with external linkage is exported:

```cpp title="lib.cpp"
#define API __attribute__((visibility("default")))
int internal_helper(int x) { return x * 2; }
API int public_api(int x) { return internal_helper(x) + 1; }
inline int inl() { return 7; }
API int use_inl() { return inl(); }
```

```text
$ clang++ -std=c++2c -O0 -shared lib.cpp -o libdef.dylib && nm -gU libdef.dylib
0000000000007f40 T __Z10public_apii
0000000000007f28 T __Z15internal_helperi
0000000000007f7c T __Z3inlv
0000000000007f68 T __Z7use_inlv
$ clang++ -std=c++2c -O0 -fvisibility=hidden -shared lib.cpp -o libhid.dylib && nm -gU libhid.dylib
0000000000007f64 T __Z10public_apii
0000000000007f8c T __Z7use_inlv
```

`-fvisibility=hidden` changes the default visibility to hidden, and only symbols explicitly marked `visibility("default")` are exported. In an ELF object file this shows in the symbol's `Vis` column:

```text
$ clang++ -std=c++2c --target=x86_64-linux-gnu -fPIC -fvisibility=hidden -O0 -c lib.cpp -o lib.elf.o
$ llvm-readelf -s -W lib.elf.o | grep FUNC
     4: 0000000000000000    14 FUNC    GLOBAL HIDDEN      2 _Z15internal_helperi
     5: 0000000000000010    28 FUNC    GLOBAL DEFAULT     2 _Z10public_apii
     6: 0000000000000030    11 FUNC    GLOBAL DEFAULT     2 _Z7use_inlv
     7: 0000000000000000    11 FUNC    WEAK   HIDDEN      5 _Z3inlv
```

A `GLOBAL HIDDEN` symbol is still global when this library is linked, so the library's `.o` files can refer to each other, but it doesn't appear in the library's export table. This amounts to a third kind of linkage that doesn't exist in the standard: narrower than external linkage, not crossing shared library boundaries; wider than internal linkage, crossing TUs. The benefits are a smaller export table, faster loading, more optimization opportunities, and no symbol clashes between libraries.

The compromise option `-fvisibility-inlines-hidden` hides only inline functions. Built with it on our test machine, `__Z3inlv` is no longer exported, while `__Z15internal_helperi` still is.

!!! warning "Visibility and the ODR"
    Hidden visibility gives each shared library its own copy of inline functions, inline variables and template static members. If they have state, such as a `static` local variable in an inline function or `Box<int>::value`, each library has its own. By the standard they should be the same object throughout the program; the standard doesn't know shared libraries exist, and here the implementation's behavior departs from the standard's model. Likewise, once typeinfo is hidden, `dynamic_cast` and `catch` across libraries may have to fall back to comparing types by name.

### Symbol interposition

An executable and a shared library it links each define a function with the same name:

```cpp title="l2.cpp (compiled into libl2.dylib)"
int helper() { return 1; }
int api() { return helper(); }
```

```cpp title="m2.cpp"
#include <cstdio>
int helper() { return 100; }
int api();
int main() { std::printf("%d %d\n", helper(), api()); }
```

```text
$ clang++ -O0 -shared l2.cpp -o libl2.dylib
$ clang++ --ld-path=/usr/bin/ld -O0 m2.cpp -L. -ll2 -o m2 && ./m2
100 1
```

Linking succeeds; same-named definitions in an executable and a shared library don't count as duplicate definitions. The library's `api()` calls the library's own `helper()`. macOS uses a two-level namespace, in which calls within a library to its own symbols are bound when the library is linked; disassembling `api` in `libl2.dylib` shows a direct `bl __Z6helperv`.

The default semantics on ELF platforms differ (according to documentation). Global symbols with default visibility in a shared library can be **interposed**: the loader resolves symbols in a global search order, the executable's `helper` comes first, so the library's `api()` would also call the one returning 100. For this reason, library code compiled with `-fPIC` goes through the PLT even when calling its own global functions:

```text
$ clang++ --target=x86_64-linux-gnu -fPIC -O0 -c l2.cpp -o t.o && llvm-objdump -dr --no-show-raw-insn t.o
      14:      	callq	0x19 <_Z3apiv+0x9>
		0000000000000015:  R_X86_64_PLT32	_Z6helperv-0x4
```

But at `-O2`, Clang 23 by default inlines `helper` directly into `api` (`movl $0x1, %eax`), not preserving the possibility of interposition; only with `-fsemantic-interposition` is the jump through the PLT kept.

By the standard, two definitions of `helper()` in one program already violate the ODR ([[basic.def.odr#16]]), so none of this behavior is constrained by the standard. Practices such as replacing `malloc` with `LD_PRELOAD` are built on symbol interposition.

## Tool quick reference

| Tool | Purpose | Common arguments |
|---|---|---|
| `nm`, `llvm-nm` | List symbols | `-C` demangle; `-g` globals only; `-U` (Apple) defined only; `-u` undefined only; `-m` (Apple) show weak/external; `--print-armap` show a static library's index |
| `c++filt`, `llvm-cxxfilt` | Demangle | Read from standard input; both handle the extra leading `_` of Mach-O symbols (`__Z5twiceIiET_S0_` → `int twice<int>(int)`) |
| `llvm-objdump` | Disassemble, inspect sections | `-d` disassemble; `-r` relocations; `-h` section headers; `-t` symbol table; `-C` demangle |
| `llvm-readelf` | ELF structure | `-S` sections; `-s` symbols; `-r` relocations; `-g` COMDAT groups |
| `otool`, `llvm-otool` | Mach-O structure | `-L` shared library dependencies; `-tV` disassemble |
| `llvm-ar` | Static libraries | `t` list members; `rcs` create |

## Summary

| C++ concept | In object files and the linker |
|---|---|
| External linkage | `GLOBAL` symbol |
| Internal linkage | `LOCAL` symbol, not used by the linker for matching |
| Inline functions, template instantiations, vtables without a key function | `WEAK` plus COMDAT group (Mach-O: weak definition); `linkonce_odr` in IR |
| Static initialization | Ready-made bytes in `.data`, `.bss` |
| Missing definition ([[basic.def.odr#12]]) | Undefined reference, usually reported by the linker |
| More than one definition ([[basic.def.odr#16]]) | Duplicate definition reported for two strong definitions; one picked silently when there are weak definitions |
| Inconsistent declared types ([[basic.link#11]]) | Same symbol name, invisible to the linker |
| Shared library boundaries | Visibility and symbol interposition, with no counterpart in the standard |
