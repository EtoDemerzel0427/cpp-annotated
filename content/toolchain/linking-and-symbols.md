---
title: 目标文件、符号与链接
summary: 目标文件里有什么（节、符号表、重定位）；ELF 与 Mach-O 的节对照；符号绑定（GLOBAL/LOCAL/WEAK）与 C++ 链接的映射；inline、模板、vtable 的 vague linkage（linkonce_odr / COMDAT）；静态库的按成员提取与链接顺序；动态库与符号可见性；"重复定义""未定义引用"在标准中的含义；链接器默默接受的 ODR 违规实验；nm / c++filt / objdump 用法
status: draft
order: 20
related: basic.link, basic.def.odr, dcl.inline, dcl.link, temp.expl.spec, lex.phases, toolchain/compilation-pipeline, toolchain/name-mangling
tags: 工具链, 链接, 符号, ELF, Mach-O, ODR, 动态库
updated: 2026-10-18
---

[[basic.link]] 用"链接"（linkage）这个词描述**名字**能否在别的作用域、别的 TU 中指代同一实体；[[basic.def.odr]] 规定整个程序中定义的个数。标准从不提"符号"、"目标文件"或"链接器"——但这两条规则的设计完全是为了让"每个 TU 单独编译成目标文件，再由一个只看名字的程序拼起来"这件事成立。本页从目标文件的层面看这套机制：标准里的每个概念落到了哪个比特上，以及链接器能检查什么、不能检查什么。

前置阅读：[[toolchain/compilation-pipeline]]（目标文件从哪来）。符号名本身怎么编码见 [[toolchain/name-mangling]]。

本页的 ELF 输出来自 `clang++ --target=x86_64-linux-gnu -c`（Homebrew Clang 23.1.3），用 `llvm-readelf`/`llvm-nm`/`llvm-objdump` 检查——**本机无法链接 Linux 程序**，所以涉及 GNU ld / lld / 动态加载器的运行时行为都标明"据文档"。Mach-O 输出来自本机原生编译，链接实验用系统链接器 `/usr/bin/ld`（`ld-1266.8`），通过 `--ld-path=/usr/bin/ld` 指定。

## 目标文件里有什么

一个可重定位目标文件（`.o`）主要包含三样东西：

1. **节**（section）：一块块带属性的字节——代码、已初始化数据、只读数据……
2. **符号表**：本 TU **定义**了哪些名字（在哪个节、什么偏移），**引用**了哪些名字（未定义）。
3. **重定位**（relocation）：机器码或数据中"这里要填某个符号的地址，等链接时再说"的记录。

下面这个 TU 几乎覆盖了所有常见情形：

```cpp title="sec.cpp"
int counter = 42;                 // 已初始化、非零
int zeroed;                       // 零初始化
const int table[4] = {1, 2, 3, 4};
extern const int exported_k = 7;  // 外部链接的 const
static int hidden_count = 1;      // 内部链接
namespace { int anon_var = 2; }
static int bump() { return ++hidden_count + anon_var; }
inline int version() { return 3; }
template <class T> T twice(T x) { return x + x; }
extern int elsewhere;             // 只声明
int get_elsewhere();
int api() { return counter + zeroed + table[2] + bump() + version()
                 + twice(1) + elsewhere + get_elsewhere(); }
```

### 节：ELF 与 Mach-O 对照

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

```text
$ clang++ -std=c++2c -O0 -c sec.cpp -o sec_macho.o && llvm-objdump -h sec_macho.o
Idx Name             Size     VMA              Type
  0 __text           000000d4 0000000000000000 TEXT
  1 __data           0000000c 00000000000000d4 DATA
  2 __common         00000004 0000000000000178 BSS
  3 __const          00000014 00000000000000e0 DATA
  4 __compact_unwind 00000080 00000000000000f8 DATA
```

| 内容 | ELF 节 | Mach-O（段,节） | 本例中的实体 |
|---|---|---|---|
| 机器码 | `.text`（以及 `.text.<名字>`） | `__TEXT,__text` | `api`、`bump`；`version`、`twice<int>` 在 ELF 中各有独立的节 |
| 已初始化的可写数据 | `.data` | `__DATA,__data` | `counter`、`hidden_count`、`anon_var`（3 × 4 = 12 字节） |
| 零初始化的数据 | `.bss`（`NOBITS`：文件中不占空间） | `__DATA,__common`（zerofill） | `zeroed` |
| 只读数据 | `.rodata` | `__TEXT,__const` | `table`、`exported_k` |
| 回溯信息 | `.eh_frame` | `__LD,__compact_unwind`（链接后变成 `__TEXT,__unwind_info`） | 每个函数的 CFI |

`.bss` 是**静态初始化**（[[basic.start.static]]）的直接产物：零初始化的静态存储期对象不需要在文件里存任何字节，加载器分配一块清零的内存即可。常量初始化的 `counter = 42` 则把 `42` 直接写在 `.data` 里——程序启动时它"已经"是 42，不需要执行任何代码。只有**动态初始化**的变量才需要启动时运行的构造代码。

`.rela.text` 是 `.text` 的重定位表：`api` 里对 `counter`、`elsewhere`、`get_elsewhere` 等的每一处引用都对应一条记录。`.group` 节是 COMDAT 组，下文专门讲。

### 符号表与绑定

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

`nm` 用一个字母概括同样的信息（大写 = 全局，小写 = 局部）：

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

| `nm` 字母 | 含义 |
|---|---|
| `T`/`t` | 代码节中的定义（全局/局部） |
| `D`/`d` | 已初始化数据节 |
| `B`/`b` | `.bss` |
| `R`/`r` | 只读数据 |
| `W` | 弱定义（函数等） |
| `V` | 弱定义（对象） |
| `U` | 未定义：本 TU 引用、但定义在别处 |

## C++ 的链接如何映射为符号

把上面的输出与 [[basic.link]] 对照：

| C++ 中的情形 | 标准的结论 | 符号 |
|---|---|---|
| 普通函数 `api()`、变量 `counter` | 外部链接（[[basic.link#4]]） | `GLOBAL`（`T`/`D`/`B`） |
| `static` 函数/变量 | 内部链接（[[basic.link#3]]） | `LOCAL`（`t`/`d`），修饰名带 `L`：`_ZL4bumpv` |
| 无名命名空间中的实体 | 内部链接（[[basic.link#4]]） | `LOCAL`，名字含 `_GLOBAL__N_1` |
| 命名空间作用域的 `const` 非 inline、非 `extern` 变量 | 内部链接（[[basic.link#3]]） | `LOCAL`：`_ZL5table` |
| `extern const int exported_k = 7;` | 外部链接 | `GLOBAL`（`R`） |
| inline 函数、函数模板的实例化 | 外部链接，**允许多处定义**（[[basic.def.odr#16]]） | `WEAK`，放在 COMDAT 组 |
| 只声明不定义 | —— | `UND`（`U`） |

**LOCAL 符号对链接器"不存在"**：它们只用于调试和反汇编时显示名字，不参与跨文件的匹配。两个 TU 各自的 `static int bump()` 在链接时互不干扰——这就是内部链接的实现。

注意 `counter`、`zeroed`、`elsewhere` 这些**全局命名空间中的变量名不加修饰**。这与 C 的变量同名，所以 [[dcl.link#7]] 规定：C 语言链接的变量与全局作用域的同名变量声明的是**同一实体**——在符号层面它们本来就无法区分。

### vague linkage：inline、模板、vtable 的共同归宿

`version()` 是 inline 函数，`twice<int>` 是隐式实例化的模板特化。它们会出现在**每个**使用它们的 TU 中，ODR 允许这样（只要定义处处相同，[[basic.def.odr#16]]）。链接器需要一种机制把多份合并成一份，又不报"重复定义"。

在 LLVM IR 层，Clang 给它们 `linkonce_odr` 链接属性：

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

`linkonce_odr` 的字面意思就是标准的意思：

- **linkonce**：链接时多份只保留一份；没人用就可以丢掉（所以 `-O2` 下内联后 `version()` 可能完全不出现在目标文件里）。
- **odr**：编译器可以假定**所有副本等价**——这正是 ODR 给出的保证，也让优化器可以基于本 TU 看到的定义做内联和推理。

落到 ELF 上是两层：符号是 `WEAK`，所在的节放进一个以符号名为签名的 **COMDAT 组**：

```text
$ llvm-readelf -g sec.o
COMDAT group section [    4] `.group' [_Z7versionv] contains 1 sections:
   [Index]    Name
   [    5]   .text._Z7versionv

COMDAT group section [    6] `.group' [_Z5twiceIiET_S0_] contains 1 sections:
   [Index]    Name
   [    7]   .text._Z5twiceIiET_S0_
```

链接器看到同签名的组只保留第一个，整组丢弃其余的（包括其中的代码和数据），而不仅仅是选一个符号。Mach-O 没有 COMDAT，对应物是 **weak definition**（`nm -m` 显示 `weak external`）：

```text
$ nm -m sec_macho.o
00000000000000b8 (__TEXT,__text) weak external __Z5twiceIiET_S0_
00000000000000b0 (__TEXT,__text) weak external __Z7versionv
00000000000000d8 (__DATA,__data) non-external __ZL12hidden_count
0000000000000000 (__TEXT,__text) external __Z3apiv
...
```

!!! pitfall "macOS 的 nm 不加 -m 时把弱定义显示为 T"
    本机 `/usr/bin/nm`（Apple 版）对上面的弱定义输出 `T __Z7versionv`，看起来和普通外部函数一样；要看 weak 必须用 `nm -m`，或者改用 `llvm-nm`（显示 `W`）。

Itanium C++ ABI 把这一类"每个用到的 TU 都发射一份、靠链接器去重"的实体统称为 **vague linkage**。完整清单比 inline 函数长：

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

inline 变量（[[dcl.inline]]）、静态数据成员模板、inline 函数里的静态局部变量 `counter()::n`（所有 TU 必须共享**同一个** `n`，否则 `++counter()` 在不同 TU 中会加到不同的对象上）、隐式定义的特殊成员函数、以及**没有 key function 的类**的 vtable 和 typeinfo，全都是 `W`/`V`。（两个 `Shape::~Shape()` 分别是"完整对象析构函数"和"删除析构函数"，见 [[toolchain/name-mangling]]；vtable 何时是 vague linkage 见 [[toolchain/object-layout-and-vtables]]。）

## 两种链接错误，在标准里是什么

### "未定义引用"

```cpp title="m.cpp"
int helper();
int missing(int);
int main() { return helper() + missing(3); }
```

```text
$ clang++ --ld-path=/usr/bin/ld x.o m.o -o t
Undefined symbols for architecture arm64:
  "missing(int)", referenced from:
      _main in m.o
ld: symbol(s) not found for architecture arm64
clang++: error: linker command failed with exit code 1 (use -v to see invocation)
```

`m.o` 中 `__Z7missingi` 是 `U`，所有输入里都找不到定义。标准的说法是 [[basic.def.odr#12]]：每个被 odr-use 的函数或变量在程序中**至少**有一个定义，违反时 {{ifndr}}。"不要求诊断"是因为标准不能假定实现有链接器、更不能假定它能看到全部代码；实际上链接器几乎总能报出来。GNU ld 的措辞是 ``undefined reference to `missing(int)'``（据文档，本机未验证）。

两种"看起来未定义、其实没事"的情形也来自同一条规则：只**声明**、从不 odr-use 的函数不需要定义（例如只出现在 `sizeof` 或 `decltype` 里）；以及 [[class.virtual#12]]——虚函数必须定义或声明为纯虚，因为非纯虚的虚函数**总是**被 odr-use（[[basic.def.odr#8]]），vtable 里要放它的地址。忘了定义 key function 时的报错长这样（本机 Apple ld）：

```text
Undefined symbols for architecture arm64:
  "vtable for W", referenced from:
      W::W() in vt-530b09.o
   NOTE: a missing vtable usually means the first non-inline virtual member function has no definition.
```

### "重复定义"

```text
$ cat x.cpp y.cpp
int helper() { return 1; }
int helper() { return 2; }
$ clang++ --ld-path=/usr/bin/ld x.o y.o m.o mi.o -o t
duplicate symbol 'helper()' in:
    /private/var/folders/.../link/err/y.o
    /private/var/folders/.../link/err/x.o
ld: 1 duplicate symbols
clang++: error: linker command failed with exit code 1 (use -v to see invocation)
```

两个 `GLOBAL`（非弱）定义同名。对应 [[basic.def.odr#16]]：非 inline 的函数和变量在程序中**至多**一个定义——同样是 {{ifndr}}。GNU ld 的措辞是 ``multiple definition of `helper()'; x.o:...: first defined here``（据文档，本机未验证）。

对比一下：同一个 TU 里定义两次是 [[basic.def.odr#2]] 的违规，编译器**必须**诊断；跨 TU 时规则变成 IFNDR，因为编译器看不到别的 TU。链接器能抓住"两个强定义"，是因为这种违规恰好在符号层面可见——一旦定义是 inline 的（`WEAK`），它就看不见了。

## 链接器默默接受的违规

链接器只看**符号名**和**绑定**，从不比较内容、类型或大小。凡是违规不改变符号名的，它都看不见。[[basic.def.odr]] 的实现视角一节已经演示了"两个 TU 中同名 inline 函数定义不同"与"同名类布局不同"的后果；这里补充另外两种同样常见的情形。

### 强定义压过弱定义：显式特化只在部分 TU 中可见

```cpp title="twice.h"
template <class T> T twice(T x) { return x + x; }
```

```cpp title="a.cpp" ifndr
#include "twice.h"
int from_a() { return twice(10); }      // 隐式实例化 twice<int>
```

```cpp title="b.cpp" ifndr
#include "twice.h"
template <> int twice<int>(int x) { return -x; }  // 显式特化，只有 b.cpp 看得到
int from_b() { return twice(10); }
```

`main` 打印 `from_a()` 与 `from_b()`：

```text
$ for O in -O0 -O2; do clang++ -std=c++2c $O a.cpp b.cpp main.cpp -o t && echo "$O: $(./t)"; done
-O0: -10 -10
-O2: 20 -10
$ nm -m a.o b.o | grep twice
0000000000000018 (__TEXT,__text) weak external __Z5twiceIiET_S0_      ← a.o：隐式实例化
0000000000000000 (__TEXT,__text) external __Z5twiceIiET_S0_           ← b.o：显式特化
```

[[temp.expl.spec#7]] 要求：显式特化的声明必须在每个会引发隐式实例化的使用点之前可达，否则 {{ifndr}}。`a.cpp` 违反了它。在符号层面，**显式特化不是模板的"一份实例化"，而是一个普通函数**——它是强定义（`T`），隐式实例化是弱定义（`W`）。链接器的规则是"强定义存在时弱定义全部让路"，**不报错、与链接顺序无关**（`b.cpp a.cpp` 的顺序结果相同）。于是 `-O0` 时 `from_a` 调用的是 b 的特化；`-O2` 时 `from_a` 里的调用被内联成了 a 自己看到的主模板。加 `-Wall -Wextra` 也没有任何警告。

### 符号名不含类型：变量和返回类型

```cpp title="def.cpp" ifndr
double ratio() { return 2.5; }
long long big = 0x100000001;
```

```cpp title="use.cpp" ifndr
#include <cstdio>
int ratio();          // 返回类型与定义不同
extern int big;       // 类型与定义不同
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

Itanium ABI 的修饰名**不包含**非模板函数的返回类型，也**不包含**变量的类型（[[toolchain/name-mangling]]）。所以两边的符号名完全一致，链接成功。这违反了 [[basic.link#11]]：同一实体的所有声明必须有相同的类型——不同 TU 中的声明互不可达时 {{ifndr}}。运行结果：`big` 读到了 `0x100000001` 的低 4 字节（小端机器上是 1）；`ratio()` 的 `double` 返回值在 arm64 上放在浮点寄存器 `d0`，调用方却从整数寄存器 `w0` 读——读到的是一个与 2.5 毫无关系的残留值。

!!! tip "预防"
    这两类问题都有同一个解法：**声明只写在一个头文件里，定义它的 .cpp 也包含这个头文件**。这样定义与声明在同一个 TU 中相遇，不一致就变成了编译器必须诊断的错误。MSVC 的修饰名包含返回类型和变量类型（见 [[toolchain/name-mangling]] 末尾），因此这类不一致在 MSVC 上通常表现为链接错误。

## 静态库：按成员提取

静态库（`.a`）只是目标文件的**归档**，外加一张"哪个符号在哪个成员里"的索引：

```text
$ llvm-ar rcs libh.a x.o mi.o && llvm-ar t libh.a
x.o
mi.o
$ llvm-nm --print-armap libh.a | head -3
Archive map
__Z6helperv in x.o
__Z7missingi in mi.o
```

链接器对静态库的处理和对 `.o` 不同：`.o` 全部链接进来；静态库中的成员只有在**能解决某个当前未定义的符号**时才被提取，而且以**整个成员**为单位。这带来两个后果。

**后果一：没被提取的成员等于不存在。** 下面 `y.o` 已经定义了 `helper()`，库里的 `x.o` 也定义了 `helper()`，却不报重复定义：

```text
$ clang++ --ld-path=/usr/bin/ld m.o y.o libh.a -o t && ./t; echo rc=$?
rc=5
```

`helper()` 来自 `y.o`（返回 2），`missing` 来自库中的 `mi.o`（返回 3）；`x.o` 从未被提取。这是**有意为之**的机制：标准允许程序替换全局 `operator new` 等可替换函数（[[replacement.functions]]），实现方式之一就是标准库把默认版本放在库里，用户的定义先到先得。

**后果二：成员是不可分割的。** 把 `helper` 和 `missing` 放进同一个成员 `xm.o`：

```text
$ clang++ --ld-path=/usr/bin/ld m.o y.o libxm.a -o t
duplicate symbol 'helper()' in:
    /private/var/folders/.../link/err/y.o
    /private/var/folders/.../link/err/libxm.a[2](xm.o)
ld: 1 duplicate symbols
```

为了 `missing` 提取了 `xm.o`，它顺带带进来的 `helper()` 就与 `y.o` 冲突了。

### 链接顺序

本机 Apple ld 不在乎静态库在命令行上的位置：

```text
$ clang++ --ld-path=/usr/bin/ld libh.a m.o -o t && ./t; echo rc=$?
rc=4
```

库写在 `m.o` **之前**也能找到 `helper` 和 `missing`。**GNU ld 的传统行为不同**（据文档，本机未验证）：它从左到右扫描，处理一个静态库时只用它解决**此刻已知**的未定义符号，之后不再回头。于是 `ld libh.a m.o` 会报 `undefined reference`——处理 `libh.a` 时还没有任何未定义符号。这就是 Linux 上"库要写在使用它的目标文件之后"、"互相依赖的库要写两遍或用 `--start-group ... --end-group`"这些经验规则的来源。LLVM 的 lld 在 ELF 上采用与 Apple ld 类似的、不依赖顺序的策略（据 lld 文档）。

这一切都在标准之外：[[lex.phases#1]] 第 8 项只说"链接库组件以满足对外部实体的引用"，没有规定搜索顺序。

## 动态库与符号可见性

动态库（`.so`/`.dylib`）是**链接过的**产物：库内部的引用已经解决，对外只暴露一张**导出符号表**。默认情况下，所有外部链接的符号都导出：

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

`-fvisibility=hidden` 把默认可见性改为隐藏，只有显式标注 `visibility("default")` 的符号被导出。在 ELF 目标文件中，这体现为符号的 `Vis` 一栏：

```text
$ clang++ -std=c++2c --target=x86_64-linux-gnu -fPIC -fvisibility=hidden -O0 -c lib.cpp -o lib.elf.o
$ llvm-readelf -s -W lib.elf.o | grep FUNC
     4: 0000000000000000    14 FUNC    GLOBAL HIDDEN      2 _Z15internal_helperi
     5: 0000000000000010    28 FUNC    GLOBAL DEFAULT     2 _Z10public_apii
     6: 0000000000000030    11 FUNC    GLOBAL DEFAULT     2 _Z7use_inlv
     7: 0000000000000000    11 FUNC    WEAK   HIDDEN      5 _Z3inlv
```

`GLOBAL HIDDEN`：在链接**这个库**时它仍是全局符号（库内的多个 `.o` 之间可以互相引用），但不会出现在库的导出表里。这是标准里不存在的第三种"链接"：比外部链接窄（不跨动态库边界），比内部链接宽（跨 TU）。好处是更小的导出表、更快的加载、更多的优化机会，以及避免不同库之间的符号冲突。还有一个折中选项 `-fvisibility-inlines-hidden` 只隐藏 inline 函数（本机：`__Z3inlv` 不再导出，`__Z15internal_helperi` 仍导出）。

!!! warning "可见性与 ODR"
    隐藏可见性会让每个动态库各自拥有一份 inline 函数、inline 变量、模板静态成员……如果它们有状态（例如 inline 函数里的 `static` 局部变量、`Box<int>::value`），**每个库会各有一个**。按标准，整个程序里它们应该是同一个对象——标准不知道动态库的存在，这里实现的行为已经偏离了标准模型。同理，typeinfo 被隐藏后，跨库的 `dynamic_cast` 和 `catch` 可能需要退回到按名字比较类型。

### 符号插入（interposition）

一个经典的平台差异：可执行文件和它链接的动态库**各定义了一个同名函数**。

```cpp title="l2.cpp（编译成 libl2.dylib）"
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

链接成功（可执行文件与动态库中的同名定义不被当作"重复定义"），并且库里的 `api()` 调用的是**库自己的** `helper()`。macOS 采用"二级命名空间"（two-level namespace），库内对自身符号的调用在链接库时就已经绑定（反汇编 `libl2.dylib` 中的 `api` 可以看到直接的 `bl __Z6helperv`）。

ELF 平台的默认语义不同（据文档，本机无法运行验证）：动态库中默认可见的全局符号可以被**插入**（interpose）——加载器按全局搜索顺序解析，可执行文件中的 `helper` 排在前面，于是库里的 `api()` 也会调用到返回 100 的那个。为此，`-fPIC` 编译的库代码对自己的全局函数也经 PLT 调用。在本机生成的 ELF 目标文件中可以看到这一点：

```text
$ clang++ --target=x86_64-linux-gnu -fPIC -O0 -c l2.cpp -o t.o && llvm-objdump -dr --no-show-raw-insn t.o
      14:      	callq	0x19 <_Z3apiv+0x9>
		0000000000000015:  R_X86_64_PLT32	_Z6helperv-0x4
```

但在 `-O2` 下，本机 Clang 23 默认直接把 `helper` 内联进 `api`（`movl $0x1, %eax`），即**不**为插入保留可能；加 `-fsemantic-interposition` 后才保留 `R_X86_64_PLT32 _Z6helperv` 的跳转。按标准，同一程序中两个 `helper()` 的定义本身就违反 ODR（[[basic.def.odr#16]]），所以这些行为都不是标准能约束的——但 `LD_PRELOAD` 替换 `malloc` 这类工程技巧正是建立在插入机制之上。

## 工具速查

| 工具 | 用途 | 常用参数 |
|---|---|---|
| `nm` / `llvm-nm` | 列符号 | `-C` 反修饰；`-g` 只列全局；`-U`（Apple）只列已定义；`-u` 只列未定义；`-m`（Apple）显示 weak/external；`--print-armap` 看静态库索引 |
| `c++filt` / `llvm-cxxfilt` | 反修饰 | 从标准输入读；Mach-O 符号带额外的前导 `_`，两者都能自动处理（`__Z5twiceIiET_S0_` → `int twice<int>(int)`） |
| `llvm-objdump` | 反汇编与节 | `-d` 反汇编；`-r` 重定位；`-h` 节头；`-t` 符号表；`-C` 反修饰 |
| `llvm-readelf` | ELF 结构 | `-S` 节；`-s` 符号；`-r` 重定位；`-g` COMDAT 组 |
| `otool` / `llvm-otool` | Mach-O 结构 | `-L` 依赖的动态库；`-tV` 反汇编 |
| `llvm-ar` | 静态库 | `t` 列成员；`rcs` 创建 |

## 小结

!!! summary
    - 目标文件 = 节 + 符号表 + 重定位。`.data`/`.bss`/`.rodata` 的划分直接反映静态初始化与 const。
    - 外部链接 → `GLOBAL`；内部链接 → `LOCAL`（链接器不匹配）；inline/模板/无 key function 的 vtable → `WEAK` + COMDAT（Mach-O：weak definition），IR 中为 `linkonce_odr`。
    - "未定义引用"对应 [[basic.def.odr#12]]，"重复定义"对应 [[basic.def.odr#16]]——都是 IFNDR，链接器能报出来只是因为恰好看得见。
    - 链接器只比较名字：inline 定义不同、显式特化不可达、返回类型或变量类型不一致，都能顺利链接并产生错误的程序。
    - 静态库按成员提取，未提取的成员不参与冲突检查；GNU ld 对顺序敏感，Apple ld 不敏感。
    - 可见性（`-fvisibility=hidden`）与符号插入是标准之外的维度，会让"程序中只有一个实体"的标准模型在动态库边界上失效。
