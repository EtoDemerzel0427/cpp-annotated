---
title: 模块指令
summary: 为什么 module/import 行是预处理指令：模块声明的名字不能来自宏、其后必须紧跟 ; 或 [；import 指令的三种形式、宏导入点、"宏定义"的定义点与取消点、活跃宏定义及其一致性要求——这些限制共同让构建系统只靠预处理就能扫描出模块依赖。
status: draft
covers: cpp.import
related: cpp.pre, module.unit, module.import, module.global.frag, cpp.include, cpp.replace, lex.pptoken
tags: 预处理, 模块, 头文件单元
updated: 2026-10-18
---

C++20 模块在语言层面（第 10 章 [[module]]）是声明：*module-declaration*、*module-import-declaration*。但它们**同时**也是预处理指令。本页覆盖两节：

- [[cpp.module]]：模块指令 `export(opt) module ...;`
- [[cpp.import]]：头文件单元导入 `export(opt) import ...;`，以及由此引出的"宏定义"新模型。

为什么要让它们在阶段 4 就被识别？一句话：**为了让构建系统能在编译之前知道编译顺序**。模块必须先于导入者编译（导入者需要它的 BMI，即编译后的模块接口），于是构建系统得先扫描每个源文件"我是哪个模块、我导入了谁"。如果这些信息要做完整的语法分析才能得到，就陷入了"要编译才知道怎么编译"的死循环。把它们做成预处理指令，并加上一系列限制，扫描器只需跑一遍预处理（Clang 的 `clang-scan-deps`、GCC 的 `-fdeps-format=p1689r5`、MSVC 的 `/scanDependencies` 都是这样做的）。

前置知识：什么样的行算指令（[[cpp.pre#2]]）；*import-keyword* 等特殊记号（[[lex.pptoken#4]]）；模块单元的结构（[[module.unit]]）。

## 模块指令（cpp.module）

### 文法与名字限制（[[cpp.module#1]]）

```text
pp-module:
    export(opt) module pp-tokens(opt) new-line
```

¶1：*pp-tokens*（若有）必须具有形式 *pp-module-name* *pp-module-partition*(opt) *pp-tokens*(opt)：

```text
pp-module-name:      pp-module-name-qualifier(opt) identifier       // a.b.c
pp-module-partition: : pp-module-name-qualifier(opt) identifier     // :part.x
```

关键限制：*pp-module-name* 和 *pp-module-partition* 中的**任何标识符**都不得

- 当前被定义为**对象式宏**，或
- 在阶段 4 开始时**后面紧跟 `(`**。

第二条看起来奇怪，其实是在禁止函数式宏：如果名字后面跟着 `(`，而它又恰好是函数式宏，就会被展开。标准干脆不论它是不是宏，一律禁止——这样扫描器不需要知道宏的定义就能判断。

```cpp title="m3.cppm" error
module;
#define NAME foo
export module NAME;    // error: 模块名中的标识符是对象式宏
```

Clang 23：`module name component 'NAME' cannot be a object-like macro`。

### 替换为特殊记号（[[cpp.module#2]]）

¶2：`module` 和（若有）`export` 预处理记号被替换为 *module-keyword* 和 *export-keyword* 预处理记号。

注 1 解释了这一步的意义：替换之后这一行**不再是指令**，所以不会在阶段 4 结束时被删除（指令在阶段 4 末尾会被删除，见 [[lex.phases]]），而是作为声明进入阶段 7。*module-keyword* 是没有可观察拼写的特殊记号（[[lex.pptoken#4]]），阶段 7 的文法（[[module.unit]]）用它而不是标识符 `module` 来识别模块声明——所以阶段 7 不会把一个普通的 `module` 变量名误认为模块声明。

替换后，构成指令的记号成为一个 *text-line*，像普通文本一样处理——即**做宏展开**。注 2：模块名和分区名不可能被宏展开（¶1 已经保证其中没有宏）。所以真正会被展开的只有名字**之后**的部分，例如属性。

处理完之后，模块名和可选的分区名之后必须是 `;` 或 `[` 预处理记号。

### 标准例子（[[cpp.module#3]]）

设可导入头文件 `"common.h"` 为：

```cpp title="common.h"
#define DOT_BAR .bar
#define MOD_ATTR [[vendor::shiny_module]]
```

```cpp title="tu1.cppm"
module;
#include "common.h"
export module foo DOT_BAR;      // error: 展开后 foo 之后是 . 而不是 ; 或 [
```

```cpp title="tu2.cppm"
module;
#include "common.h"
export module M MOD_ATTR ;      // OK：展开为 [[vendor::shiny_module]]，以 [ 开头
```

第一例的意图是用宏把模块名"补全"成 `foo.bar`——正是 ¶2 要禁止的：扫描器不展开宏时会以为模块名是 `foo`，编译器展开后却是 `foo.bar`，二者不一致。第二例中宏只贡献了属性，模块名 `M` 在扫描器眼中和编译器眼中相同，所以允许。

例 2–5 讨论换行：

```cpp
export module a
.b;                             // error: 模块名之后的记号不是 ; 或 [

export module M [[
attr1,
attr2 ]] ;                      // OK：指令可以跨行吗？见下文

export module M
[[ attr1,
attr2 ]] ;                      // OK

export module M; int
n;                              // OK
```

这里有个乍看矛盾的地方：指令以换行结束（[[cpp.pre#2]]），为什么属性能写到下一行？答案在 ¶2：替换为 *module-keyword* 之后，这些记号已经是 *text-line*，后续行作为普通文本接上去，到阶段 7 拼成一个完整的声明。**指令本身**（用于扫描的部分）仍然只到第一行行尾——它只需要包含模块名。所以：

- `export module a` 换行 `.b;`：指令里的模块名是 `a`，紧跟换行；处理后名字之后的第一个记号是下一行的 `.`，不是 `;` 或 `[`，非良构。不这样规定的话，扫描器会认为模块名是 `a`，编译器却拼出 `a.b`。
- `export module M; int` 换行 `n;`：同一行的 `int` 在 `;` 之后，属于后续声明，合法。Clang 对此给出 `extra tokens after semicolon in 'module' directive` 警告，但不拒绝。

### 全局模块片段与私有模块片段

[[cpp.pre]] 的 *module-file* 文法还包括 `module;`（全局模块片段的开始）和 `module :private;`（私有模块片段的开始），它们同样是由 ¶2.3 识别的指令（`module` 后跟 `;` 或 `:`）。全局模块片段里在阶段 4 开始时只能有指令（[[cpp.pre#5]]），详见 [[module.global.frag]]、[[module.private.frag]]。

## 头文件单元导入（cpp.import）

### 三种形式（[[cpp.import#1]]）

```text
pp-import:
    export(opt) import header-name pp-tokens(opt) ; new-line          // ① import <vector>;  import "a.h";
    export(opt) import header-name-tokens pp-tokens(opt) ; new-line   // ② import HDR;（宏展开后为 "a.h" 或 <...>）
    export(opt) import pp-tokens ; new-line                           // ③ import foo;  import :part;
```

¶1：`import` 之后的记号**像普通文本一样做宏展开**。前两种形式（导入头文件单元）有一个[[g:point-of-macro-import|宏导入点]]（*point of macro import*），位于终结该 *pp-import* 的换行**之后**——从那里开始，头文件单元的宏变为可见。第三种形式（导入命名模块或分区）**没有**宏导入点，并且仅当宏替换后前两种形式都不匹配时才考虑它。

注 1：前两种形式指示预处理器从头文件单元导入宏。换言之：

| 导入什么 | 声明可见 | 宏可见 |
|---|---|---|
| `import <vector>;` / `import "a.h";`（头文件单元） | 是 | **是** |
| `import foo;`（命名模块） | 是（导出的） | **否** |
| `import :part;`（分区） | 是 | **否** |

命名模块不导出宏，这是模块设计的核心承诺之一：模块的接口是**声明**，不是文本。

### 不能从被包含的文件中产生 import（[[cpp.import#2]]）

¶2：在处理 *module-file* 的 *group* 时，如果一个 *pp-import* 是由**源文件包含**产生的（包括 `#include` 被改写为 import 的情形，见 [[cpp.include#10]]），程序非良构。

```cpp title="m.cppm"
export module m;
#include "imports_vector.h"   // 该文件中有 import <vector>;  → 非良构
```

理由仍然是依赖扫描：模块单元正文中的 import 必须直接写在这个文件里，扫描器才能看见它们，而不必追踪 `#include` 链（`#include` 的目标可能取决于宏和搜索路径）。另外 [[module.import#1]] 要求模块单元中的 import 都出现在其他声明之前，从头文件里冒出来的 import 很难满足这一点。

### 替换为特殊记号（[[cpp.import#3]]）

¶3：三种形式中，`import` 和 `export` 记号被替换为 *import-keyword* 和 *export-keyword*。注 2：同 [[cpp.module#2]]，这样这一行就不再是指令，不会在阶段 4 末尾被删除，而是作为 *module-import-declaration* 进入阶段 7。

对第二种形式，还要按 `#include` 的规则（[[cpp.include#7]]）把 *header-name-tokens* 拼成一个 *header-name* 记号并替换之。注 3：这保证预处理器和后续阶段对"导入的是哪个头文件"有一致的看法。

```cpp
#define HDR <vector>
import HDR;        // ② 形式：宏展开为 < vector >，拼成 header-name <vector>
```

### 宏定义的新模型（[[cpp.import#4]]–¶6）

在只有 `#include` 的世界里，"宏 X 是否已定义"很简单：从上到下读一遍，看最后一次 `#define X`/`#undef X`。头文件单元打破了这个线性模型：同一个宏可能通过多个头文件单元以不同的定义被导入。于是标准引入了一套更精细的术语。

¶4：预处理程序中每个翻译单元时遇到的每个 `#define` 指令都产生一个独立的[[g:macro-definition|宏定义]]（*macro definition*）。注 4：预定义宏不是由 `#define` 引入的；鼓励实现把通过 `-D` 等机制预定义的宏也视为不是由 `#define` 引入的。

每个宏定义在每个翻译单元中至多有一个**定义点**和一个**取消定义点**：

- ¶4.1 [[g:macro-point-of-definition|定义点]]（*point of definition*）：
  - ¶4.1.1 若该 `#define` 就在翻译单元 T 中，定义点就是该指令所在处；
  - ¶4.1.2 否则，若宏名**不**与关键字、`module`、`import` 拼写相同，则定义点是 T 中第一个"包含该宏定义之定义点的头文件单元"的**宏导入点**。此时称该宏是从头文件单元**导入的**（*imported*）。
- ¶4.2 [[g:point-of-undefinition|取消定义点]]（*point of undefinition*）：定义点之后第一个对它的 `#undef`，或第一个"包含该宏定义之取消点的头文件单元"的宏导入点，取较早者。

¶4.1.2 排除关键字和 `module`/`import`：不能通过头文件单元导入一个叫 `import` 的宏来劫持后续的 import 指令——那会让依赖扫描重新依赖于宏的内容。

¶5：宏定义在某处[[g:active-macro-definition|活跃]]（*active*），当且仅当它在该翻译单元中有位于此处之前的定义点，且没有位于此处之前的取消定义点。

¶6：若一个宏将要被**替换或重定义**，而该宏名有多个活跃的宏定义，则这些活跃定义必须都是同一个宏的**有效重定义**（按 [[cpp.replace.general#2]] 的规则：替换列表相同等）。注 5：*pp-import* 的相对顺序与某个宏定义是否活跃无关。

注意 ¶6 的触发条件是"将要被替换或重定义"：仅仅**导入**两个冲突的定义并不违规，只有**使用**它（或再定义它）时才违规。这和函数重载中"有歧义的声明本身不违规，有歧义的调用才违规"是同一个思路。

### 标准例子逐行解读（[[cpp.import#7]]）

```cpp title="a.h"
#define X 123   // #1
#define Y 45    // #2
#define Z a     // #3
#undef X        // a.h 中 #1 的取消定义点
```

```cpp title="b.h"
import "a.h";   // b.h 中 #1、#2、#3 的定义点，以及 #1 的取消定义点
#define X 456   // OK：#1 不活跃（导入时连同它的 #undef 一起导入了）
#define Y 6     // error：#2 活跃，45 与 6 不是有效重定义
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
import "d.h";   // #4、#5 的定义点（传递导入：d.h 导入了 c.h，宏导入是可传递的）
int a = Y;      // OK：活跃的 #2 与 #4 都是 "45"，是有效重定义
int c = Z;      // error：活跃的 #3（a）与 #5（c）不是有效重定义
```

```cpp title="f.cppm"
export module f;
export import "a.h";
int a = Y;      // OK：f 自己导入了 a.h，Y 可见
```

```cpp title="tu1.cpp"
import f;
int x = Y;      // error：Y 既不是宏，也不是已声明的名字
```

最后一例最值得注意：`f` 用 `export import "a.h"` **重新导出**了头文件单元，但重新导出的只是**声明**；`import f;` 是第三种形式，没有宏导入点，所以 `Y` 不可见。

!!! impl "Clang 23 实测"
    用 `-fmodule-header=user` 编译 `a.h`、`c.h` 为头文件单元后：
    
    - `import "a.h"; import "c.h"; int a = Y;` 编译通过，`X` 未定义（导入时 `#undef` 一并生效）。
    - `int c = Z;` 只得到 `ambiguous expansion of macro 'Z'` **警告**，并选用了后导入的定义——标准要求非良构，警告在形式上满足"诊断"，但继续编译的结果依赖于导入顺序，而注 5 恰恰说顺序不应有意义。
    - `import "a.h"; #define Y 6` 只得到 `-Wmacro-redefined` 警告（与普通重定义一样）。
    - 模块 `f` 中 `export import "a.h";` 之后，`import f; int x = Y;` 报 `use of undeclared identifier 'Y'`，与标准一致。
    - Clang 对每个头文件单元导入都给出 `-Wexperimental-header-units` 警告：头文件单元在 Clang 中仍属实验性功能。

## 历史与演进

!!! history
    - **C++20**：模块合并（[[P1103R3]]）引入头文件单元与宏导入。[[P1703R1]] 让头文件单元的 import 在预处理阶段被识别；[[P1857R3]] 把 `module`/`import` 行整体定义为指令，并引入 *module-keyword*/*import-keyword* 这类无拼写的特殊记号，规定指令必须以行首关键字开始、模块名之后的形状受限——目标都是让依赖扫描只需预处理。
    - **C++26**：[[P3034R1]] 禁止模块声明中的模块名和分区名来自宏，并要求名字之后紧跟 `;` 或 `[`。在此之前 `export module MODNAME;`（`MODNAME` 为宏）是允许的，这使扫描器必须正确地复现所有宏定义（包括命令行 `-D`）才能得到模块名。

## 陷阱

!!! pitfall "条件编译包围的 import"
    ```cpp
    module;
    export module m;
    #ifdef USE_FMT
    import fmt;
    #endif
    ```
    这是合法的，但依赖扫描的结果取决于 `USE_FMT`——扫描时必须使用与真正编译时**相同**的宏定义和命令行选项，否则依赖图就错了。构建系统（CMake 等）因此总是用完整的编译命令行去调用扫描器。

!!! pitfall "全局模块片段里的 #include 被翻译成 import"
    全局模块片段中写 `#include <vector>`，若实现启用了 include 翻译（[[cpp.include#10]]），它会变成 `import <vector>;`。[[cpp.import#2]] 只约束 *module-file* 的 *group*（模块声明之后的正文），全局模块片段中的翻译不受此限。但在**模块正文**中写 `#include <vector>` 就可能因翻译成 import 而非良构——是否出错取决于实现是否对它做了 include 翻译。在模块正文中需要标准库时，直接写 `import std;` 或 `import <vector>;` 更稳妥。

## 思考题

!!! question "思考题 1"
    设 `ATTR` 是定义为 `[[vendor::shiny]]` 的宏。下面三个模块接口单元的开头，哪些在预处理层面良构？
    ```cpp
    export module m ATTR;          // (a)
    export module m
    [[vendor::shiny]];             // (b)
    export module m.ATTR;          // (c)
    ```

<details markdown="1">
<summary>展开查看答案与解析</summary>

- (a) 良构。模块名 `m` 不是宏、其后不是 `(`；替换为特殊记号后整行作为普通文本做宏展开，`ATTR` 变成 `[[vendor::shiny]]`，名字之后第一个记号是 `[`，满足 [[cpp.module#2]]。
- (b) 良构。第一行是指令（`module` 后跟标识符 `m`），模块名 `m` 紧跟换行；替换后成为 *text-line*，下一行作为普通文本接上，名字之后的第一个记号是 `[`。这正是标准例 4 的形状。
- (c) 非良构。按 *pp-module-name* 的文法，`m.ATTR` 整个是模块名，其中的标识符 `ATTR` 是对象式宏，违反 [[cpp.module#1]]。

到阶段 7，(a)(b) 是带属性的模块声明，未知的 vendor 属性按 [[dcl.attr.grammar]] 的规则处理（通常被忽略并警告）。
</details>

!!! question "思考题 2"
    为什么 [[cpp.import#4]] 不允许通过头文件单元导入名为 `import` 或 `module` 的宏，却允许在本翻译单元里直接 `#define import ...`？

<details markdown="1">
<summary>展开查看答案与解析</summary>

首先，"允许直接 `#define import`"本身就不对：`import` 和 `module` 列在表 4（具有特殊含义的标识符）中，[[cpp.replace.general#9]] 禁止翻译单元 `#define` 或 `#undef` 它们，以及所有关键字。

¶4.1.2 处理的是头文件单元**内部**定义了这样的宏（头文件单元本身是另一个翻译单元，它的 `#define import` 违反了它自己的规则，但即便如此）——导入方也不应受影响：导入方的定义点规则直接把它排除在外。这是双保险：保证"某行是不是 import 指令"不依赖于任何导入来的宏，从而依赖扫描结果稳定。
</details>

## 小结

!!! summary
    - `module`/`import`（可带 `export`）开头、满足后继记号条件的行是预处理指令；处理时 `module`/`import`/`export` 被换成无拼写的特殊记号，行本身变回普通文本进入阶段 7。
    - 模块名、分区名中不得有对象式宏，也不得后跟 `(`；名字之后必须是 `;` 或 `[`（C++26，[[P3034R1]]）。
    - `import` 后的记号会宏展开；头文件单元导入有**宏导入点**（行尾之后），命名模块/分区导入没有——**命名模块不导出宏**。
    - 模块正文中，不能由 `#include` 产生 import。
    - 宏定义有定义点/取消定义点，导入时随头文件单元一并带来；同名的多个活跃定义在**使用时**必须一致。
    - 这一切限制的目的：依赖扫描只需预处理，不需完整编译。
