---
title: 从源码到可执行文件
summary: clang++ 一条命令背后的流水线：驱动程序拆出哪些子命令，预处理、AST、LLVM IR、汇编、目标文件、链接各对应哪个翻译阶段，以及头文件与模块两种编译模型的差别。
status: draft
order: 10
related: lex.phases, lex.separate, basic.link, cpp.include, module.unit, module.import, toolchain/linking-and-symbols, toolchain/modules-in-practice
tags: 工具链, 编译流程, Clang, 预处理, 模块
updated: 2026-10-19
---

!!! tldr
    - `clang++` 是驱动程序，本身不编译：它拼出一条 `clang -cc1` 编译命令和一条链接命令，`-###` 可以把它们打印出来。
    - 标准的八个翻译阶段（[[lex.phases]]）在 Clang 里大致是：`-E` 做阶段 1–4，解析和语义分析做阶段 5–7，代码生成产出目标文件，链接器做阶段 8。
    - 目标文件就是翻译后的翻译单元：机器码、数据、符号表和重定位。不同翻译单元之间只靠符号名连接。
    - AST 和 LLVM IR 把标准里看不见的东西写了出来：隐式转换、链接、模板实例化，以及 `nsw`、`mustprogress` 这类由 UB 规则得来的优化前提。
    - 头文件是文本，每个翻译单元都要重新处理一遍；模块接口只编译一次，代价是编译之间有了先后顺序。

!!! note "实验环境"
    输出来自 macOS arm64 上的 Homebrew Clang 23.1.3。需要 ELF/x86-64 输出时加 `--target=x86_64-linux-gnu`，只编译不链接，因为本机没有 Linux 的链接器和 C 运行时。

## 流水线总览

标准用八个**翻译阶段**（phases of translation，[[lex.phases]]）描述源文件怎样变成程序。脚注 7 说明实现只需表现得如同分阶段进行。真实的编译器也确实没有八个独立的程序：一个驱动程序调起两三个工具，每个工具内部又把几个阶段合在一起做。

| 步骤 | 命令 | 产出 | 对应的翻译阶段 |
|---|---|---|---|
| 预处理 | `clang++ -E` | `.ii`（预处理后的源码） | 阶段 1–4 |
| 解析与语义分析 | `-fsyntax-only`、`-Xclang -ast-dump` | AST，只在内存里 | 阶段 5–7 的分析部分 |
| 代码生成 | `-S -emit-llvm` | `.ll`（LLVM IR） | 阶段 7 的翻译部分 |
| 优化与后端 | `-S` | `.s`（汇编） | 阶段 7（实现细节） |
| 汇编 | `-c` | `.o`（目标文件） | 阶段 7 的结果：翻译后的翻译单元 |
| 链接 | `clang++ a.o b.o` | 可执行文件或动态库 | 阶段 8 |

前五步都在一个**翻译单元**（translation unit，TU）之内进行，TU 就是一个源文件加上它 `#include` 的全部内容。只有最后一步才把多个 TU 放在一起。这就是**分离编译**（[[lex.separate]]）：编译器每次只看见一个 TU，跨 TU 的函数调用、全局变量和 vtable 都要等链接器按名字接起来。

[[basic.link]] 和 [[basic.def.odr]] 里有不少规则注明不要求诊断（IFNDR），原因就在这里：违反它们的证据分散在不同的 TU 里，编译器看不到。

## 驱动程序

`clang++` 解析命令行，确定目标平台，找到 SDK 和标准库，然后拼出并执行真正干活的子命令。`-###` 只打印这些子命令，不执行：

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

第一条子命令 `clang -cc1` 是编译器本体，包含前端、优化器、后端和内置汇编器。`-emit-obj` 表示它在一个进程里从 `.cpp` 直接走到 `.o`，中间结果不写到磁盘上。

第二条是链接器。驱动程序把临时的 `.o`、C++ 标准库（`-lc++`）、C 运行时（`-lSystem`）和编译器运行时（`libclang_rt.osx.a`）一起交给它。

!!! pitfall "用 -### 查环境问题"
    上面的链接器是 `/opt/homebrew/anaconda3/bin/ld`，即本机 `PATH` 里 Anaconda 带的一份旧 ld64（`ld -v` 报告 `ld64-530`），而不是系统的 `/usr/bin/ld`（`ld-1266.8`）。驱动程序按 `PATH` 查找 `ld`，于是悄悄用了它。链接行为和同事不一样时，先用 `-###` 看实际调用的是哪个工具；`--ld-path=/usr/bin/ld` 可以显式指定。本站链接相关页面的实验都用系统链接器。

换成 Linux 目标，驱动程序拼出的链接命令完全不同：

```text
$ clang++ -std=c++2c --target=x86_64-linux-gnu -### hello.cpp -o hello
 ... "-cc1" "-triple" "x86_64-unknown-linux-gnu" "-emit-obj" ... "-pic-is-pie" ...
 "/opt/homebrew/anaconda3/bin/ld" "--hash-style=gnu" "--eh-frame-hdr" "-m" "elf_x86_64" "-pie"
   "-dynamic-linker" "/lib64/ld-linux-x86-64.so.2" "-o" "hello" "Scrt1.o" "crti.o" "crtbeginS.o"
   "-L/usr/lib" "/var/folders/.../T/hello-140e83.o" "-lstdc++" "-lm" "-lgcc_s" "-lgcc" "-lc"
   "-lgcc_s" "-lgcc" "crtendS.o" "crtn.o"
```

这条命令在本机执行会失败，这里只看驱动程序打算做什么。`crt*.o` 和 C 库一起构成 `main` 前后的启动与终止框架。程序入口 `_start` 在这些文件里；全局对象的动态初始化（[[basic.start.dynamic]]）经由它们在 `main` 之前执行；`main` 返回后再调用 `exit`。标准说程序从 `main` 开始，但操作系统看到的入口是 `_start`。

### 拆开每一步

驱动程序内部把一次编译表示为一张动作图，`-ccc-print-phases` 把它打印出来：

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

默认情况下 1–4 在同一个 `-cc1` 进程里完成。加上 `-save-temps`，驱动程序会把每一步拆成单独的命令并保留中间文件：

```text
$ clang++ -std=c++2c -save-temps hello.cpp -o hello && ls
hello  hello.bc  hello.ii  hello.o  hello.s
```

这时 `-###` 显示四条 `-cc1` 子命令（`-E` 产出 `hello.ii`，`-emit-llvm-bc` 产出 `hello.bc`，`-S` 产出 `hello.s`，`-cc1as` 产出 `hello.o`）和一条链接命令。下面按顺序看每一步的产物。

## 预处理（阶段 1–4）

```cpp title="hello.cpp"
#include <cstdio>
#define GREETING "Hello, " "world"
static int square(int x) { return x * x; }
int main() {
    std::printf("%s %d\n", GREETING, square(7));
}
```

`-E` 只做预处理：

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

一行 `#include <cstdio>` 展开成了约 740 行。阶段 4 规定 `#include` 让被包含的文件递归地经历阶段 1–4（[[cpp.include]]）。源文件连同它包含的全部头文件，标准称为**预处理翻译单元**（[[lex.separate]]）。

宏已经展开，预处理指令已经删除，这正是阶段 4 结束时的状态。`# 2 "hello.cpp" 2` 这样的行叫**行标记**（linemarker），不是 C++ 语法，只用来让后面的报错指回原始文件。末尾的标志 `1`、`2` 表示进入、返回一个文件，`3` 表示系统头文件，系统头文件里的警告会被抑制。`-P` 可以去掉行标记。

注意 `"Hello, " "world"` 仍然是两个字符串字面量。相邻字符串字面量的拼接属于阶段 5，Clang 在解析时构造字符串字面量节点才把它们合并。所以 `-E` 的输出只是预处理指令执行完毕后的文本，并不精确对应某个阶段结束时的状态，这也是实现只需如同分阶段进行的一个例子。

### 一个 `#include <iostream>` 有多大

```text
$ printf '#include <iostream>\nint main(){ std::cout << "hi\\n"; }\n' > io.cpp
$ clang++ -std=c++2c -E io.cpp | wc -lc
   51627 2279972
```

两行源码预处理后约 5 万行、2.2 MB。`-H` 把每一次头文件包含按嵌套深度打印出来，本机对 `io.cpp` 输出约 760 条记录。每个包含 `<iostream>` 的 TU 都要把这些内容重新预处理、重新解析一遍。这是头文件模型最大的成本，也是模块要解决的问题。

### 头文件搜索路径

[[cpp.include]] 规定 `#include <...>` 按实现定义的方式搜索。`-v` 把 Clang 的搜索列表打印出来：

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

顺序决定了找到的是哪个文件：

1. libc++ 的头文件（`include/c++/v1`）排在最前，所以 `<cstdio>` 先找到 libc++ 的版本，它再去包含 `<stdio.h>`。
2. 编译器自带的头文件（`lib/clang/23/include`），如 `<stddef.h>`、`<stdarg.h>` 和各种 intrinsics 头文件。它们依赖编译器内部知识，必须与编译器版本匹配。
3. 系统 C 库的头文件（SDK 的 `usr/include`）。

`"..."` 形式先在当前文件所在的目录找，再找 `-iquote` 指定的目录，最后回到 `<...>` 的列表。`-I` 加入的目录排在系统目录之前；`-isystem` 加入的目录按系统头文件对待，其中的警告被抑制。

## 解析与语义分析（阶段 5–7）

`-fsyntax-only` 做完预处理、解析和语义分析就停下，不生成代码。它是检查一段代码是否良构的最快方法，非良构的程序在这一步就被拒绝（[[intro.compliance]]）。

`-Xclang -ast-dump` 把语义分析之后的 **AST**（抽象语法树）打印出来。`-Xclang` 表示把下一个参数原样传给 `-cc1`。

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

标准里许多隐含的东西在 AST 里都是显式的节点，所以它是读标准时很好的辅助工具：

- 根节点 `TranslationUnitDecl` 对应阶段 7 的"记号构成一个翻译单元"。它前面还有一串编译器预先声明的隐式类型，如 `__int128_t`。
- `square` 标着 `internal-linkage`，`api` 标着 `external-linkage`，与 [[basic.link#3]]、[[basic.link#4]] 的结论一致。
- `DeclRefExpr ... lvalue` 说明 `x` 是左值，外面包着一层 `ImplicitCastExpr <LValueToRValue>`，这就是左值到右值转换（[[conv.lval]]）。函数名 `square` 是 `int (int)` 类型的左值，经过 `<FunctionToPointerDecay>` 变成函数指针后才被调用（[[conv.func]]、[[expr.call]]）。
- 函数上的 `used` 标记大致对应 [[g:odr-use]]（[[basic.def.odr]]）。

### 模板实例化

阶段 7 还包括执行所需的模板实例化。`-ast-dump-filter` 只打印名字匹配的声明，用来看实例化最方便：

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

模板定义里 `x + x` 的类型是 `<dependent type>`：在知道 `T` 之前无法分析（[[temp.dep]]）。隐式实例化（[[temp.inst]]）得到的 `twice<int>` 是另一棵子树，其中所有类型都已确定。实例化就是在 AST 上复制并替换出一个新的声明，之后它和普通函数一样，也会单独生成代码。

## 生成 LLVM IR（阶段 7）

代码生成把 AST 变成 **LLVM IR**，一种与源语言无关、与目标机器基本无关的中间表示。`-S -emit-llvm` 以文本形式输出：

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

IR 里的许多标记直接来自标准的规则，在这里可以看到语义规则怎样变成优化前提：

| IR 中的标记 | 来源 |
|---|---|
| 名字变成 `_Z3apii`、`_ZL6squarei` | 名字修饰，见 [[toolchain/name-mangling]]；`L` 表示内部链接 |
| `define internal` 与 `define dso_local` | 内部链接与外部链接（[[basic.link]]） |
| `add nsw`、`mul nsw`（no signed wrap） | 算术结果超出类型的表示范围是 UB（[[expr.pre#4]]），所以编译器可以假定有符号运算不溢出 |
| `mustprogress` | 前进保证（[[intro.progress]]）：没有副作用的无限循环可以被假定会终止 |
| `noundef` | 读取不确定值是 UB 或错误行为（[[basic.indet]]），所以实参被假定是确定的值 |
| `nounwind`（只在 `square` 上） | 编译器推断出它不会抛出异常 |

`-O0` 下每个形参都先 `store` 到栈上再 `load` 回来，这是抽象机里对象占据存储的字面实现。打开优化后：

```text
$ clang++ -std=c++2c --target=x86_64-linux-gnu -S -emit-llvm -O2 sq.cpp -o -
define dso_local noundef range(i32 -2147483647, -2147483648) i32 @_Z3apii(i32 noundef %0) local_unnamed_addr #0 {
  %2 = mul nsw i32 %0, %0
  %3 = add nuw nsw i32 %2, 1
  ret i32 %3
}
```

`square` 被内联之后整个消失了。它是内部链接的，别的 TU 不可能引用它，内联后就没有理由保留。外部链接的 `api` 必须保留，因为链接器可能要把其他 TU 中的调用接到它上面。`-Rpass=inline` 可以让优化器报告这个决定。

`+1` 上多出了 `nuw`。因为 `x * x` 带 `nsw`，优化器推出乘积非负，于是 `+1` 也不会发生无符号回绕。有符号溢出是 UB 这条规则，在这里成了推理的前提。

## 汇编与目标文件（阶段 7 的结果）

后端把 IR 翻译成目标机器的指令。`-S` 输出汇编：

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

`.globl` 声明一个全局符号，这是外部链接在汇编里的样子。`.cfi_*` 伪指令描述栈帧的布局，供异常处理和调试器回溯调用栈使用（见 [[toolchain/exception-implementation]]）。

`-c` 再由汇编器生成目标文件：

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

目标文件就是标准所说的**翻译后的翻译单元**（translated translation unit，[[lex.separate]]；阶段 7 的注 4）。它包含机器码和数据，一张**符号表**，记录本 TU 定义了哪些名字、引用了哪些名字，以及**重定位**记录，标出哪些地址要等链接时才能填上。`file` 输出里的 relocatable 指的就是后者。符号、节和重定位的细节见 [[toolchain/linking-and-symbols]]。

## 链接（阶段 8）

阶段 8（[[lex.phases#1]]）把翻译后的 TU 组合起来，解析所有对外部实体的引用，链接库组件以满足未定义的引用，最后产出程序映像。链接器做的正是这些事：

- 把每个 `.o` 中未定义（`U`）的符号与某个 `.o` 或库中的定义对应起来；
- 合并 inline 函数、模板实例化、vtable 这类允许在多个 TU 中定义的实体（ELF 的 COMDAT 组，Mach-O 的弱定义）；
- 按最终地址修正重定位；
- 对动态库只记录运行时到哪个库去找，真正的绑定推迟到加载时。

标准没有动态库的概念，在它的模型里程序映像在执行前就已经完整了。链接时常见的未定义引用和重复定义，大多对应 [[basic.def.odr]] 中不要求诊断的违规。链接器之所以经常能报出来，只是因为这些违规恰好在符号层面可见。

## 头文件与模块

`#include <iostream>` 的例子说明了头文件模型的问题：头文件是文本，每个 TU 都要对它重新执行阶段 1–7。C++20 的**模块**（[[module.unit]]）改为编译一次、导入多次。模块接口单元被编译成一个 **BMI**（二进制模块接口，Clang 里是 `.pcm` 文件），导入方直接读取其中已经分析好的声明。

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
$ clang++ -std=c++2c --precompile m.cppm -o m.pcm         # 接口 → BMI
$ clang++ -std=c++2c -c m.pcm -o m.o                       # BMI → 目标文件（模块里的函数体）
$ clang++ -std=c++2c -fmodule-file=m=m.pcm -c use.cpp -o use.o
$ clang++ m.o use.o -o app && ./app; echo rc=$?
rc=0
$ nm m.o
0000000000000010 S __ZGIW1m
0000000000000008 T __ZW1m6answerv
0000000000000000 T __ZW1m6helperv
...
```

不给 `-fmodule-file`，编译 `use.cpp` 会报 `fatal error: module 'm' not found`。编译导入方之前，模块必须已经编译好，这给构建系统带来了编译顺序的问题。`clang++ -std=c++2c -c m.cppm -fmodule-output -o m.o` 可以一步同时得到 `.o` 和 `.pcm`。

这几点可以和标准对应起来：

- 模块接口单元也是一个 TU，同样产出目标文件，BMI 是额外的产物。阶段 7 规定，被依赖的模块单元的源码是否必须可用由实现定义。Clang 的选择是需要 BMI，不需要源码。
- 符号名中的 `W1m` 表示实体**附属于**（attached to）模块 `m`（[[basic.link#10]]、[[module.unit]]），编码细节见 [[toolchain/name-mangling]]。`helper` 没有导出，却同样是全局符号 `T`。导出与否不影响符号名，导入方看不到它是由编译器的名字查找保证的，与链接器无关。
- `_ZGIW1m` 是模块的初始化函数。导入方在初始化自己的全局变量之前先调用它（[[basic.start.dynamic]]）。

标准库模块 `import std;` {{c++23}} 也能用。本机 libc++ 在 `share/libc++/v1/std.cppm` 提供了它的源码，要先自行预编译成 `std.pcm`，耗时约 1 秒，文件约 37 MB。用 `-fsyntax-only` 粗略比较，`#include <print>` 版本的用户态 CPU 时间约 0.3 s，`import std;` 版本约 0.12 s，而后者导入的是整个标准库。

在两者之间还有**头文件单元**（header unit，`import <vector>;`，[[module.import]]）：把一个头文件当作模块来编译。它仍然导出宏，所以迁移平滑，但构建系统的支持不如具名模块成熟。BMI 的种类、依赖扫描和 CMake 集成见 [[toolchain/modules-in-practice]]。

## 小结

| 想看什么 | 用什么 |
|---|---|
| 驱动程序实际执行的子命令 | `-###` |
| 头文件搜索路径 | `-v` |
| 阶段划分与中间文件 | `-ccc-print-phases`、`-save-temps` |
| 预处理结果（阶段 1–4） | `-E`（不做阶段 5 的字符串拼接） |
| 只检查是否良构 | `-fsyntax-only` |
| 隐式转换、链接、实例化 | `-Xclang -ast-dump` |
| UB 规则变成的优化前提 | `-S -emit-llvm` |
| 符号表与机器码 | `-c`，然后 `llvm-nm`、`llvm-objdump` |
