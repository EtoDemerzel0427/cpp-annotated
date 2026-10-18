---
title: 从源码到可执行文件
summary: clang++ 一条命令背后的流水线：驱动程序（driver）→ 预处理（-E）→ 前端 AST（-ast-dump）→ LLVM IR（-emit-llvm）→ 汇编（-S）→ 目标文件（-c）→ 链接；每一步对应 [lex.phases] 的哪个翻译阶段；用 -### 和 -v 看真实的子命令与头文件搜索路径；头文件与模块的编译模型对比
status: draft
order: 10
related: lex.phases, lex.separate, basic.link, cpp.include, module.unit, module.import, toolchain/linking-and-symbols, toolchain/modules-in-practice
tags: 工具链, 编译流程, Clang, 预处理, 模块
updated: 2026-10-18
---

标准用八个**翻译阶段**（[[lex.phases]]）描述"源文件如何变成程序"，并在脚注里声明：实现只需表现得"如同"（as if）分阶段进行，实际上可以把几个阶段合在一起做。真实编译器确实没有八个独立的程序，而是一个**驱动程序**（driver）调起若干**工具**（tool），每个工具内部又把多个阶段揉在一起。

本页把 `clang++ hello.cpp -o hello` 这条命令拆开，看每一步产出什么、对应标准的哪个阶段。本页所有输出来自本机 Homebrew Clang 23.1.3（macOS arm64）；需要 ELF/x86-64 输出时用 `--target=x86_64-linux-gnu`，只编译不链接（本机无法链接 Linux 程序）。

## 总览

| 步骤 | 命令 | 产出 | 对应翻译阶段 |
|---|---|---|---|
| 预处理 | `clang++ -E` | `.ii`（预处理后的源码） | 阶段 1–4（[[lex.phases#1]] 1–4） |
| 语法与语义分析 | `clang++ -fsyntax-only`，`-Xclang -ast-dump` | AST（只在内存里） | 阶段 5–7 的"分析"部分 |
| 代码生成 | `clang++ -S -emit-llvm` | `.ll`（LLVM IR） | 阶段 7 的"翻译"部分 |
| 优化 + 后端 | `clang++ -S` | `.s`（汇编） | 阶段 7（实现细节） |
| 汇编 | `clang++ -c` | `.o`（目标文件） | 阶段 7 的终点："翻译后的 TU" |
| 链接 | `clang++ a.o b.o` | 可执行文件 / 动态库 | 阶段 8 |

前五步发生在**一个 TU** 之内；只有最后一步才把多个 TU 放在一起。这就是 C++ 的**分离编译**模型（[[lex.separate]]）：编译器每次只看到一个 TU，跨 TU 的一切——函数调用、全局变量、vtable——都要等链接器按名字接起来。[[basic.link]] 和 [[basic.def.odr]] 里那些"不要求诊断"的规则，根源都在这里。

## 驱动程序：`clang++` 本身不编译任何东西

`clang++` 是驱动程序：它解析命令行、决定目标平台、找到 SDK 和标准库，然后**拼出并执行**真正干活的子命令。`-###` 让它只打印这些子命令而不执行：

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

两条子命令：

1. **`clang -cc1`**：真正的编译器**前端 + 优化器 + 后端 + 内置汇编器**。`-emit-obj` 说明它一口气从 `.cpp` 走到 `.o`——预处理、解析、代码生成、汇编全在一个进程里完成，中间结果不落盘。
2. **链接器**：驱动程序把临时 `.o`、C++ 标准库（`-lc++`）、C 运行时（`-lSystem`）和编译器运行时（`libclang_rt.osx.a`）交给它。

!!! pitfall "-### 能揭穿环境问题"
    注意上面链接器的路径是 `/opt/homebrew/anaconda3/bin/ld`——本机 `PATH` 里 Anaconda 自带的一份旧 ld64（`ld -v` 报告 `ld64-530`），而不是系统的 `/usr/bin/ld`（`ld-1266.8`）。驱动程序按 `PATH` 找 `ld`，于是悄悄用了它。这类"为什么我的链接行为和同事不一样"的问题，`-###` 一眼就能看出来。可以用 `--ld-path=/usr/bin/ld` 显式指定。本站链接相关页面的实验均显式使用系统链接器。

同一源文件换成 Linux 目标，驱动程序拼出的链接命令完全不同——它要找 `Scrt1.o`、`crti.o`、`crtbeginS.o`，链接 `libstdc++` 和 `libgcc`：

```text
$ clang++ -std=c++2c --target=x86_64-linux-gnu -### hello.cpp -o hello
 ... "-cc1" "-triple" "x86_64-unknown-linux-gnu" "-emit-obj" ... "-pic-is-pie" ...
     "-mconstructor-aliases" ... "-faddrsig" ...
 "/opt/homebrew/anaconda3/bin/ld" "--hash-style=gnu" "--eh-frame-hdr" "-m" "elf_x86_64" "-pie"
   "-dynamic-linker" "/lib64/ld-linux-x86-64.so.2" "-o" "hello" "Scrt1.o" "crti.o" "crtbeginS.o"
   "-L/usr/lib" "/var/folders/.../T/hello-140e83.o" "-lstdc++" "-lm" "-lgcc_s" "-lgcc" "-lc"
   "-lgcc_s" "-lgcc" "crtendS.o" "crtn.o"
```

（这条命令在本机执行会失败——本机既没有 GNU 风格的 ELF 链接器，也没有 Linux 的 C 运行时文件。这里只看驱动程序**打算**做什么。）`crt*.o` 与 C 库一起构成 `main` 之前和之后的启动/终止框架：程序入口 `_start` 在它们里面，全局对象的动态初始化（[[basic.start.dynamic]]）在调用 `main` 之前经由这套框架执行，`main` 返回后再调用 `exit`。标准说"程序从 `main` 开始执行"，但从操作系统看，入口是 `_start`。

### 看清每一个阶段：`-ccc-print-phases` 与 `-save-temps`

驱动程序内部把编译建模为一张"动作图"：

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

默认情况下 1–4 合并在一个 `-cc1` 进程里。加 `-save-temps` 则强制每一步单独执行并保留中间文件：

```text
$ clang++ -std=c++2c -save-temps hello.cpp -o hello && ls
hello  hello.bc  hello.ii  hello.o  hello.s
```

此时 `-###` 会显示四条 `-cc1` 子命令（`-E` → `hello.ii`，`-emit-llvm-bc` → `hello.bc`，`-S` → `hello.s`，`-cc1as` → `hello.o`）和一条链接命令。下面逐步来看。

## 第一步：预处理（阶段 1–4）

```cpp title="hello.cpp"
#include <cstdio>
#define GREETING "Hello, " "world"
static int square(int x) { return x * x; }
int main() {
    std::printf("%s %d\n", GREETING, square(7));
}
```

`-E` 只做预处理，输出到标准输出（或 `-o`）：

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

几个值得注意的地方：

- 4 行的 `#include <cstdio>` 展开成了约 740 行。阶段 4 规定 `#include` 让被包含的文件**递归地经历阶段 1–4**（[[lex.phases#1]] 第 4 项、[[cpp.include]]），预处理后的结果就是一个 **TU**——标准称之为"预处理翻译单元"（[[lex.separate]]）。
- `# 2 "hello.cpp" 2` 这样的**行标记**（linemarker）不是 C++ 语法，而是给后续阶段报错定位用的；末尾的标志 `1`/`2` 表示进入/返回一个文件，`3` 表示系统头文件（系统头文件里的警告会被抑制）。`-P` 可以去掉它们。
- 宏已展开，指令已删除——阶段 4 的末尾"所有预处理指令被删除"。
- **但 `"Hello, " "world"` 仍然是两个字符串字面量**。相邻字符串字面量拼接是阶段 5，Clang 的 `-E` 不做它；拼接发生在解析阶段（Clang 在构造字符串字面量的 AST 节点时把相邻的字符串记号一起处理）。这是"实现只需如同分阶段"的一个直观例子：`-E` 的输出并不精确对应"阶段 4 结束时"或"阶段 6 结束时"的任何一个状态，它只是"预处理指令执行完毕"的文本表示。

一个 `#include <iostream>` 有多重？

```text
$ printf '#include <iostream>\nint main(){ std::cout << "hi\\n"; }\n' > io.cpp
$ clang++ -std=c++2c -E io.cpp | wc -lc
   51627 2279972
```

两行源码，预处理后约 5 万行、2.2 MB。`-H` 打印每一次头文件包含（按嵌套深度缩进）：本机对 `io.cpp` 共输出 759 条包含记录，涉及 597 个不同的头文件。**每个**包含 `<iostream>` 的 TU 都要把这些重新预处理、重新解析一遍——这是头文件模型最大的成本，也是模块（见下文）要解决的问题。

### 头文件搜索路径：`-v`

`#include <...>` 到底在哪找？[[cpp.include]] 说搜索方式"由实现定义"。`-v` 把它打印出来：

```text
$ clang++ -std=c++2c -fsyntax-only -v hello.cpp
...
ignoring nonexistent directory "/Library/Developer/CommandLineTools/SDKs/MacOSX26.sdk/usr/local/include"
ignoring nonexistent directory "/Library/Developer/CommandLineTools/SDKs/MacOSX26.sdk/Library/Frameworks"
#include "..." search starts here:
#include <...> search starts here:
 /opt/homebrew/Cellar/llvm/23.1.3_2/bin/../include/c++/v1
 /opt/homebrew/Cellar/llvm/23.1.3_2/lib/clang/23/include
 /Library/Developer/CommandLineTools/SDKs/MacOSX26.sdk/usr/include
 /Library/Developer/CommandLineTools/SDKs/MacOSX26.sdk/System/Library/Frameworks (framework directory)
 /Library/Developer/CommandLineTools/SDKs/MacOSX26.sdk/System/Library/SubFrameworks (framework directory)
End of search list.
```

顺序很重要：

1. **libc++ 的头文件**（`include/c++/v1`）最先——所以 `<cstdio>` 先找到 libc++ 的版本，它再 `#include <stdio.h>`。
2. **编译器自带的头文件**（`lib/clang/23/include`）：`<stddef.h>`、`<stdarg.h>`、各种 intrinsics 头文件，它们依赖编译器内部知识，必须与编译器版本匹配。
3. **系统 C 库头文件**（SDK 的 `usr/include`）。

`"..."` 形式先在当前文件所在目录找，再走 `-iquote`，然后回落到 `<...>` 的列表。`-I` 加入的目录排在系统目录之前，`-isystem` 加入的目录被当作系统头文件（警告被抑制）。

## 第二步：解析与语义分析（阶段 5–7 的前半）

`-fsyntax-only` 跑完预处理、解析和语义分析就停下，不生成代码。它是"这段代码是否良构"的最快检验——ill-formed 的程序在这一步就被拒绝（[[intro.compliance]]）。

`-Xclang -ast-dump` 把语义分析后的 **AST**（抽象语法树）打印出来。`-Xclang` 表示把下一个参数原样传给 `-cc1`：

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

AST 是阅读标准的好帮手，因为标准里许多"看不见"的东西在这里被显式化了：

- 根节点 `TranslationUnitDecl`——阶段 7 的"记号构成一个翻译单元"。前面还有一串编译器预声明的隐式类型（`__int128_t` 等）。
- **链接**：`square` 标注 `internal-linkage`，`api` 标注 `external-linkage`——正是 [[basic.link#3]] 与 [[basic.link#4]] 的结论。
- **值类别与隐式转换**：`DeclRefExpr ... lvalue` 说明 `x` 是左值；外面包一层 `ImplicitCastExpr <LValueToRValue>`——这就是左值到右值转换（[[conv.lval]]）。函数名 `square` 是 `int (int)` 类型的左值，经 `<FunctionToPointerDecay>` 变成函数指针再调用（[[conv.func]]、[[expr.call]]）。
- 函数**被使用**（`used`）的标记，大致对应 odr-use（[[basic.def.odr]]）。

阶段 7 还包括"进行所需的实例化"。`-ast-dump-filter` 只打印名字匹配的声明，看模板的实例化最方便：

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

模板定义里的 `x + x` 类型是 `<dependent type>`——在知道 `T` 之前无法分析（[[temp.dep]]）；隐式实例化（`implicit_instantiation`，[[temp.inst]]）出来的 `twice<int>` 是一棵独立的、完全确定类型的子树。**实例化是在 AST 层面复制并替换出新的声明**，之后它和普通函数没有区别，也会被单独生成代码。

## 第三步：生成 LLVM IR（阶段 7 的后半）

AST 经"代码生成"（CodeGen）变成 **LLVM IR**——一种与源语言无关、与目标机器基本无关的中间表示。`-S -emit-llvm` 以文本形式输出：

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

IR 是观察"标准语义如何变成优化前提"的最佳窗口：

| IR 中的标记 | 来自标准的哪条规则 |
|---|---|
| 名字变成 `_Z3apii`、`_ZL6squarei` | **名字修饰**，见 [[toolchain/name-mangling]]；`L` 表示内部链接 |
| `define internal` vs `define dso_local`（外部可见） | 内部链接 vs 外部链接（[[basic.link]]） |
| `add nsw` / `mul nsw`（no signed wrap） | 有符号整数溢出是 UB（[[expr.pre#4]]），所以编译器可以假定不溢出 |
| `mustprogress` | 前进保证（[[intro.progress]]）：没有副作用的无限循环可以被假定终止 |
| `noundef` | 读取不确定值是 UB / erroneous（[[basic.indet]]），所以实参被假定是"确定"的值 |
| `nounwind`（只在 `square` 上） | 编译器推断出它不会抛出异常 |

`-O0` 下每个形参都先 `store` 到栈上再 `load`——这正是抽象机"对象占据存储"的字面实现。打开优化后：

```text
$ clang++ -std=c++2c --target=x86_64-linux-gnu -S -emit-llvm -O2 sq.cpp -o -
define dso_local noundef range(i32 -2147483647, -2147483648) i32 @_Z3apii(i32 noundef %0) local_unnamed_addr #0 {
  %2 = mul nsw i32 %0, %0
  %3 = add nuw nsw i32 %2, 1
  ret i32 %3
}
```

`square` 被内联后**整个消失了**：它是内部链接的，其他 TU 不可能引用它，内联后就没有保留的理由。外部链接的 `api` 则必须保留，因为链接器可能要把别的 TU 中的调用接到它上面。（`-Rpass=inline` 可以让优化器报告这个决定：`remark: '_ZL6squarei' inlined into '_Z3apii' ...`。）还要注意 `add nuw nsw`：因为 `x * x` 带 `nsw`，优化器推出乘积非负，于是 `+1` 连无符号回绕也不会发生。**UB 规则在这里变成了实实在在的推理前提。**

## 第四步：汇编（-S）与目标文件（-c）

后端把 IR 选择成目标机器指令。`-S` 输出汇编：

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

`.globl` 声明这是全局符号——外部链接在汇编层的样子。`.cfi_*` 伪指令描述栈帧，供异常回溯和调试器使用（见 [[toolchain/exception-implementation]]）。

`-c` 再往前一步，由汇编器生成**目标文件**：

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

**目标文件就是标准所说的"翻译后的翻译单元"**（translated translation unit，[[lex.phases#1]] 第 7 项的注 4 与 [[lex.separate]]）：它包含机器码、数据、一张**符号表**（本 TU 定义了哪些名字、引用了哪些名字），以及**重定位**（"这里的地址要等链接时再填"）。"relocatable" 指的就是后者。符号、节、重定位的细节见 [[toolchain/linking-and-symbols]]。

## 第五步：链接（阶段 8）

[[lex.phases#1]] 第 8 项：翻译后的 TU 被组合起来，所有外部实体引用被解析，库组件被链接进来以满足未定义的引用，产出**程序映像**。链接器做的正是这件事：

- 把每个 `.o` 里的 `U`（未定义）符号与某个 `.o` 或库里的定义匹配；
- 合并 inline 函数、模板实例化、vtable 这类"允许多处定义"的实体（COMDAT / weak）；
- 按最终地址修正重定位；
- 对动态库，只记录"运行时去哪个库找"，真正的绑定推迟到加载时。

标准不认识"动态库"：在它的模型里，程序映像在执行前就完整了（另见 [[lex.phases]] 的阶段 8 一节）。这一步的错误（"未定义引用"、"重复定义"）大多对应 [[basic.def.odr]] 中"不要求诊断"的违规——它们之所以经常**能**被诊断，只是因为链接器恰好看得到。

## 头文件 vs 模块

（本节只做概览；BMI 的种类、依赖扫描与 CMake 集成见 [[toolchain/modules-in-practice]]。）

上面那个 `#include <iostream>` 的例子说明了头文件模型的问题：头文件是**文本**，每个 TU 都要对它重新执行阶段 1–7。C++20 的**模块**（[[module.unit]]）把这一步改成"编译一次、导入多次"：模块接口单元被编译成一个**二进制模块接口**（BMI，Clang 称为 `.pcm`），导入方直接读取已经分析好的声明。

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

（也可以用 `clang++ -std=c++2c -c m.cppm -fmodule-output -o m.o` 一步同时得到 `.o` 和 `.pcm`。不给 `-fmodule-file`，`use.cpp` 会报 `fatal error: module 'm' not found`——编译导入方之前，模块必须先被编译，这就是模块给构建系统带来的**依赖顺序**问题。）

几点与标准的对应：

- 模块接口单元**也是一个 TU**，它同样产出目标文件；BMI 只是额外的副产品。阶段 7 中"模块单元的源码是否需要可用"由实现定义（[[lex.phases#1]] 第 7 项），Clang 的选择是：需要 BMI，不需要源码。
- 符号名中的 `W1m` 表示该实体**附属于**（attached to）模块 `m`（[[basic.link#10]]、[[module.unit]]），详见 [[toolchain/name-mangling]]。导出与否不影响符号名——`helper` 虽未导出，仍是全局符号（模块链接）；"不可见"由编译器在名字查找层面保证，而不是靠链接器。
- `_ZGIW1m` 是模块的**初始化函数**：导入方在初始化自己的全局变量之前要先调用它（[[basic.start.dynamic]]）。

标准库模块 `import std;` {{c++23}} 也可以用：本机 libc++ 在 `share/libc++/v1/std.cppm` 提供了它的源码，需要先自行预编译。粗略对比（同一台机器，`-fsyntax-only`，三次取值）：`#include <print>` 版本用户态 CPU 时间约 0.29–0.31 s，`import std;` 版本约 0.12–0.13 s——而后者导入的是**整个**标准库。预编译 `std.pcm` 本身约 1 s，生成的文件约 37 MB，但这个成本由所有 TU 分摊。

!!! note "header unit"
    介于两者之间还有 **header unit**（`import <vector>;`，[[module.import]]）：把一个头文件当作模块来编译。它保留了宏的导出，所以能平滑迁移，但构建系统支持比命名模块更不成熟。本页未在本机演示。

## 小结

!!! summary
    - `clang++` 是驱动程序；真正编译的是 `clang -cc1`，链接的是系统链接器。`-###` 看子命令，`-v` 看搜索路径，`-ccc-print-phases`/`-save-temps` 看阶段划分。
    - `-E` ≈ 阶段 1–4（Clang 的 `-E` 不做阶段 5 的字符串拼接）；`-fsyntax-only` / `-ast-dump` ≈ 阶段 7 的分析；`-emit-llvm` / `-S` / `-c` 是阶段 7 的"翻译"；链接是阶段 8。
    - 目标文件 = 翻译后的 TU：代码 + 数据 + 符号表 + 重定位。跨 TU 的一切都靠**符号名**连接。
    - AST 把隐式转换、链接、实例化显式化；IR 把 UB 规则显式化为 `nsw`、`mustprogress`、`noundef` 等优化前提。
    - 头文件是文本，每个 TU 重复处理；模块编译一次产生 BMI，但引入了构建顺序依赖。
