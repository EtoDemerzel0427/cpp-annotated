---
title: 模块指令
summary: 为什么 module 和 import 行要在预处理阶段识别；模块名不能来自宏；import 的三种形式里只有导入头文件单元会带来宏；以及从多个头文件单元导入的宏定义怎样判断是否有效、是否冲突。
status: done
covers: cpp.import
papers: P1103R3, P1703R1, P1857R3, P3034R1
related: cpp.pre, module.unit, module.import, module.global.frag, cpp.include, cpp.replace, lex.pptoken
tags: 预处理, 模块, 头文件单元
updated: 2026-10-19
---

!!! tldr
    - `export module m;` 和 `import x;` 既是声明，也是预处理指令。这样构建系统只需预处理，就能扫描出每个文件属于哪个模块、依赖哪些模块。
    - 模块名和分区名不能来自宏，名字之后必须紧跟 `;` 或 `[`，所以不展开宏也能读出模块名。
    - `import <vector>;` 这类导入头文件单元的写法会带来宏；`import m;` 导入命名模块，不带来任何宏。
    - 在模块单元的正文里，import 不能来自 `#include` 进来的文件。
    - 从几个头文件单元导入同名宏时，只有在使用或重定义这个宏时，才要求所有活跃的定义一致。

模块在语言层面是声明（[[module]]），但 `module` 行和 `import` 行同时也是预处理指令。原因是编译顺序：导入者编译时需要被导入模块已编译好的接口，所以构建系统要在编译之前先扫描每个文件，弄清它是哪个模块、导入了谁。如果这些信息要做完整的语法分析才能得到，就成了要先编译才知道怎么编译。

把这些行定义为指令，再加上一些限制，扫描器只需跑一遍预处理。Clang 的 `clang-scan-deps`、GCC 的 `-fdeps-format=p1689r5`、MSVC 的 `/scanDependencies` 都是这样工作的。一行文本什么时候被识别为这类指令，见 [[cpp.pre#2]]。

## 模块声明中的名字（¶1–¶3）

<div class="compare" markdown="1">

```cpp title="tu1.cppm" error
module;
#define DOT_BAR .bar
export module foo DOT_BAR;
// error: foo 后面是 . 而不是 ; 或 [
```

```cpp title="tu2.cppm" ok
module;
#define MOD_ATTR [[vendor::shiny]]
export module M MOD_ATTR ;
// OK：展开后 M 后面是 [
```

</div>

这是 ¶3 标准例 1 的简化版（原例把宏放在一个被包含的头文件里）。左边想用宏把模块名补全成 `foo.bar`。不展开宏的扫描器会认为模块名是 `foo`，编译器展开之后却是 `foo.bar`，两者不一致，所以被禁止。右边的宏只提供了一个属性，模块名 `M` 在扫描器和编译器看来是一样的，所以允许。

¶1 `module` 指令后面必须是模块名（`a.b.c` 这样用点分隔的标识符），可选的分区名（`:part`），然后是其他记号。模块名和分区名中的任何标识符都不得：

- 当前被定义为对象式宏；
- 在阶段 4 开始时后面紧跟 `(`。

第二条针对的是函数式宏。标准不管名字后面跟 `(` 时它是不是宏，一律禁止，这样扫描器不需要知道任何宏定义就能做出判断。

```cpp title="m3.cppm" error
module;
#define NAME foo
export module NAME;    // error: 模块名中的标识符是对象式宏
```

Clang 23 的诊断是 module name component 'NAME' cannot be a object-like macro。

¶2 处理这条指令时，`module` 和 `export` 记号被替换成 *module-keyword* 和 *export-keyword*。这两个是没有拼写的特殊记号（[[lex.pptoken#4]]），阶段 7 的文法靠它们识别模块声明（[[module.unit]]），所以一个名叫 `module` 的普通变量不会被误认为模块声明。注 1 说明，替换之后这一行就不再是指令，因此不会在阶段 4 结束时和其他指令一起被删除，而是作为声明留到阶段 7。

替换后，这一行的记号作为普通文本处理，也就是要做宏展开。注 2 指出模块名和分区名不可能被展开，因为 ¶1 已经保证其中没有宏，真正会展开的只有名字后面的部分，例如属性。处理完以后，模块名和分区名之后必须是 `;` 或 `[`。

### 指令能跨行吗

¶3 的例 2 到例 5 讨论换行：

```cpp
export module a
.b;                             // error: 模块名之后的记号不是 ; 或 [

export module M [[
attr1,
attr2 ]] ;                      // OK

export module M
[[ attr1,
attr2 ]] ;                      // OK

export module M; int
n;                              // OK
```

指令以换行结束（[[cpp.pre]]），属性为什么能写到下一行？因为按 ¶2，替换成特殊记号以后，这一行已经是普通文本，下一行作为普通文本接在后面，到阶段 7 拼成一个完整的声明。用于扫描的指令本身只到第一行的行尾，它只需要包含模块名。

- `export module a` 换行 `.b;`：指令里的模块名是 `a`，处理之后名字后面的第一个记号是下一行的 `.`，不是 `;` 或 `[`，所以非良构。如果允许，扫描器会认为模块名是 `a`，编译器却拼出 `a.b`。
- `export module M; int` 换行 `n;`：`;` 之后的 `int n;` 是一个普通的声明，合法。Clang 对同一行 `;` 之后的记号给出 extra tokens after semicolon in 'module' directive 警告。

`module;`（全局模块片段的开始）和 `module :private;`（私有模块片段的开始）也是由 [[cpp.pre#2]] 识别的指令。全局模块片段在阶段 4 开始时只能包含预处理指令（[[cpp.pre#5]]），详见 [[module.global.frag]] 和 [[module.private.frag]]。

## import 指令（[cpp.import] 第 1–3 段）

import 指令有三种形式：

```text
export(opt) import header-name pp-tokens(opt) ;          // ① import <vector>;  import "a.h";
export(opt) import header-name-tokens pp-tokens(opt) ;   // ② import HDR;（宏展开后是 "a.h" 或 <...>）
export(opt) import pp-tokens ;                           // ③ import foo;  import :part;
```

[[cpp.import]] 第 1 段：`import` 后面的记号像普通文本一样做宏展开。前两种形式导入头文件单元，它们有一个**宏导入点**（[[g:point-of-macro-import|point of macro import]]），位于这条指令结尾的换行之后，头文件单元中的宏从这里开始可见。第三种形式导入命名模块或分区，没有宏导入点，而且只在宏替换后前两种形式都不匹配时才考虑它。

| 导入什么 | 声明可见 | 宏可见 |
|---|---|---|
| 头文件单元：`import <vector>;`、`import "a.h";` | 是 | 是 |
| 命名模块：`import foo;` | 导出的声明 | 否 |
| 分区：`import :part;` | 是 | 否 |

命名模块不导出宏，这是模块设计的核心承诺之一：模块的接口是声明，不是文本。

第 3 段：三种形式中的 `import` 和 `export` 都被替换成 *import-keyword* 和 *export-keyword*，理由与模块声明相同，这一行不再是指令，留到阶段 7 成为导入声明。对第二种形式，还要按 `#include` 的规则（[[cpp.include#7]]）把记号拼成一个头文件名。注 3 说明，这保证预处理器和后续阶段对导入的是哪个头文件有一致的看法。

```cpp
#define HDR <vector>
import HDR;        // 第二种形式：展开为 < vector >，拼成头文件名 <vector>
```

### import 不能来自被包含的文件

第 2 段：处理模块单元正文时，如果一条 import 是由源文件包含产生的，程序非良构。这包括被包含的文件里写着 import，也包括 `#include` 被实现改写成 import 的情形（[[cpp.include#10]]）。

```cpp title="m.cppm"
export module m;
#include "imports_vector.h"   // 文件里有 import <vector>; 非良构
```

理由仍然是依赖扫描：模块单元正文中的 import 必须直接写在这个文件里，扫描器才能看见它们，不必追踪 `#include` 链，而 `#include` 找到哪个文件又取决于宏和搜索路径。另外，[[module.import#1]] 要求模块单元中的 import 出现在其他声明之前，从头文件里冒出来的 import 很难满足这一点。

这条限制只针对模块声明之后的正文。全局模块片段中的 `#include <vector>` 即使被实现改写成 import 也没有问题；正文中写 `#include <vector>`，是否出错取决于实现是否做了改写。在正文中需要标准库时，直接写 `import std;` 或 `import <vector>;`。

## 从头文件单元导入的宏（[cpp.import] 第 4–7 段）

只有 `#include` 时，判断宏 `X` 是否有定义很简单：从上往下读，看最后一次 `#define X` 或 `#undef X`。头文件单元打破了这个线性模型，同一个宏可能经由几个头文件单元带着不同的定义进来。标准为此定义了几个术语。

第 4 段：处理程序中各翻译单元时遇到的每条 `#define` 都产生一个独立的**宏定义**（[[g:macro-definition|macro definition]]）。注 4 说明预定义宏不是由 `#define` 引入的，并鼓励实现把用 `-D` 之类机制预定义的宏也这样看待。每个宏定义在每个翻译单元中至多有一个定义点和一个取消定义点：

- **定义点**（[[g:macro-point-of-definition|point of definition]]，第 4.1 项）：如果这条 `#define` 就在翻译单元 T 中，定义点就是它所在的位置；否则是 T 中第一个包含它的定义点的头文件单元的宏导入点，这时称这个宏是从头文件单元导入的。名字与关键字或 `module`、`import` 相同的宏不会以这种方式导入。
- **取消定义点**（[[g:point-of-undefinition|point of undefinition]]，第 4.2 项）：定义点之后第一条取消它的 `#undef`，或第一个包含它的取消定义点的头文件单元的宏导入点，取较早的一个。

排除关键字和 `module`、`import`，保证了一条指令是不是 import 不会因为导入了某个宏而改变，依赖扫描的结果也就不依赖于导入进来的宏。

第 5 段：如果一个宏定义在某个位置之前有定义点，且之前没有取消定义点，它在这个位置就是**活跃的**（[[g:active-macro-definition|active]]）。

第 6 段：如果一个宏将要被替换或重定义，而这个名字有多个活跃的宏定义，那么这些定义必须都是同一个宏的有效重定义，即替换列表相同等（[[cpp.replace.general#2]]）。注 5 说明，import 的先后顺序与某个定义是否活跃无关。

触发条件是将要被替换或重定义。仅仅导入两个冲突的定义并不违规，使用它或再定义它时才违规。

### 标准例子

第 7 段的例 1 把这些规则串在一起：

```cpp title="a.h"
#define X 123   // #1
#define Y 45    // #2
#define Z a     // #3
#undef X        // a.h 中 #1 的取消定义点
```

```cpp title="b.h"
import "a.h";   // b.h 中 #1、#2、#3 的定义点，也是 #1 的取消定义点
#define X 456   // OK：#1 不活跃，它的 #undef 也一起导入了
#define Y 6     // error: #2 活跃，45 和 6 不是有效重定义
```

```cpp title="c.h"
#define Y 45    // #4
#define Z c     // #5
```

```cpp title="d.h"
import "c.h";   // d.h 中 #4、#5 的定义点
```

```cpp title="e.h"
import "a.h";   // #1、#2、#3 的定义点，#1 的取消定义点
import "d.h";   // #4、#5 的定义点：d.h 中导入的宏也随之进入 e.h
int a = Y;      // OK：活跃的 #2 和 #4 都是 45，是有效重定义
int c = Z;      // error: 活跃的 #3（a）和 #5（c）不是有效重定义
```

```cpp title="f.cppm"
export module f;
export import "a.h";
int a = Y;      // OK：f 自己导入了 a.h，Y 可见
```

```cpp title="tu1.cpp" error
import f;
int x = Y;      // error: Y 既不是宏，也不是已声明的名字
```

最后一例最容易出错。`f` 用 `export import "a.h"` 重新导出了这个头文件单元，但重新导出的只是声明。`import f;` 是第三种形式，没有宏导入点，所以 `Y` 不可见。

!!! impl "Clang 23 实测"
    用 `-fmodule-header=user` 把 `a.h`、`c.h` 编译成头文件单元以后：

    - `import "a.h"; import "c.h"; int a = Y;` 编译通过，`X` 没有定义，`#undef` 随导入一并生效。
    - `int c = Z;` 只得到 ambiguous expansion of macro 'Z' 警告，然后选用其中一个定义继续编译。标准要求非良构，警告在形式上满足诊断要求，但选哪个定义不应依赖导入顺序，注 5 正是这个意思。
    - `import "a.h";` 之后 `#define Y 6` 只得到 `-Wmacro-redefined` 警告，与普通的宏重定义相同。
    - 模块 `f` 中 `export import "a.h";` 之后，`import f; int x = Y;` 报 use of undeclared identifier 'Y'，与标准一致。
    - 每次导入头文件单元，Clang 都给出 `-Wexperimental-header-units` 警告：头文件单元在 Clang 中仍是实验性功能。

## 历史与演进

!!! history
    - C++20 的模块合并提案 [[P1103R3]] 引入了头文件单元和宏的导入。随后 [[P1703R1]] 让头文件单元的 import 在预处理阶段就被识别，[[P1857R3]] 把 `module` 行和 `import` 行整体定义为指令，引入 *module-keyword*、*import-keyword* 这类没有拼写的特殊记号，并限制了指令的形状。这些修改的目标都是让依赖扫描只需预处理。
    - [[P3034R1]] 禁止模块名和分区名来自宏，并要求名字之后紧跟 `;` 或 `[`。此前 `export module MODNAME;`（`MODNAME` 是宏）是允许的，扫描器必须准确复现所有宏定义，包括命令行上的 `-D`，才能得到模块名。

## 常见误解

!!! pitfall "条件编译包住的 import"
    ```cpp
    export module m;
    #ifdef USE_FMT
    import fmt;
    #endif
    ```
    这是合法的，但依赖扫描的结果取决于 `USE_FMT`。扫描时必须使用与真正编译时相同的宏定义和命令行选项，否则依赖图就错了。所以 CMake 等构建系统总是用完整的编译命令去调用扫描器。

!!! pitfall "export import 头文件单元会把宏转发出去"
    不会。`export import "a.h";` 让导入模块的人看到 `a.h` 中的声明，但宏只能经由直接导入头文件单元得到。想让使用者拿到宏，他们必须自己写 `import "a.h";` 或 `#include "a.h"`。

## 思考题

!!! question "思考题 1"
    设 `ATTR` 是在全局模块片段中定义为 `[[vendor::shiny]]` 的宏。下面三种模块声明，哪些在预处理层面良构？
    ```cpp
    export module m ATTR;          // (a)
    export module m
    [[vendor::shiny]];             // (b)
    export module m.ATTR;          // (c)
    ```

<details markdown="1">
<summary>答案</summary>

- (a) 良构。模块名 `m` 不是宏，后面也不是 `(`；替换为特殊记号后，整行作为普通文本做宏展开，`ATTR` 变成 `[[vendor::shiny]]`，名字之后第一个记号是 `[`，满足 ¶2。
- (b) 良构。第一行是指令，模块名 `m` 后面是换行；替换后成为普通文本，下一行接在后面，名字之后第一个记号是 `[`。这就是 ¶3 例 4 的形状。
- (c) 非良构。按文法，`m.ATTR` 整个是模块名，其中的 `ATTR` 是对象式宏，违反 ¶1。

到阶段 7，(a) 和 (b) 都是带属性的模块声明，不认识的厂商属性按 [[dcl.attr.grammar]] 处理，Clang 给出 unknown attribute 警告后忽略它。
</details>

!!! question "思考题 2"
    在例子的 `e.h` 中，如果去掉 `int c = Z;`，换成 `#undef Z`，程序还有问题吗？
    ```cpp
    import "a.h";
    import "d.h";
    #undef Z
    ```

<details markdown="1">
<summary>答案</summary>

没有问题。第 6 段只在宏将要被替换或重定义时要求活跃定义一致，同时有两个冲突的活跃定义本身不违规。`#undef Z` 既不是替换也不是重定义；按第 4.2 项，它是 #3 和 #5 共同的取消定义点，之后 `Z` 没有任何活跃定义，可以自由地重新定义。
</details>

## 小结

!!! summary
    - 以 `module` 或 `import`（可带 `export`）开头、满足条件的行是预处理指令；处理时这些词被换成没有拼写的特殊记号，这一行重新变成普通文本，进入阶段 7 成为声明。
    - 模块名和分区名中不能有对象式宏，也不能后跟 `(`；名字之后必须是 `;` 或 `[`。
    - `import` 后的记号会做宏展开；导入头文件单元有宏导入点，导入命名模块或分区没有，所以命名模块不导出宏。
    - 模块单元的正文中，import 不能由 `#include` 产生。
    - 宏定义有定义点和取消定义点，随头文件单元一起导入；同名的多个活跃定义在使用或重定义时必须一致。
    - 这些限制的目的都是让依赖扫描只需预处理。
