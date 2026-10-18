---
title: 序言
summary: 预处理指令的总文法；什么样的一行才算"指令"（# / import / module / export 四种引导记号）；条件支持的指令；跳过组中的宽松语法；指令内的空白限制；指令内的记号默认不做宏展开。
status: draft
related: lex.phases, lex.pptoken, cpp.cond, cpp.replace, cpp.module, cpp.import, module.unit
tags: 预处理, 文法, 模块
updated: 2026-10-18
---

[[cpp.pre]] 是第 15 章的"总则"：它给出整个预处理文法（*preprocessing-file*），并回答一个看似简单、其实暗藏玄机的问题——**哪些行是[[g:preprocessing-directive|预处理指令]]？**

在 C++17 之前，答案只有一句话："以 `#` 开头的行"。C++20 引入模块之后，`import`、`module`、`export` 开头的某些行也成了指令，于是这一节被重写成一个相当精细的判定规则。理解它，才能理解为什么 `import<int> x;` 会去找一个叫 `int` 的头文件，以及为什么构建系统可以只靠"轻量预处理"就扫描出模块依赖。

前置知识：翻译阶段 3 产生预处理记号、阶段 4 执行指令（[[lex.phases]]）；*header-name* 何时被识别（[[lex.pptoken#5]]）。

## 总文法速览

预处理文法的顶层是：

```text
preprocessing-file:
    group(opt)
    module-file

module-file:
    line-directives(opt) pp-global-module-fragment(opt) pp-module group(opt) pp-private-module-fragment(opt)
```

也就是说，一个预处理翻译单元要么是普通的"一组行"（*group*），要么是一个**模块文件**：可选的 `#line` 指令、可选的全局模块片段 `module;`、一条模块指令 `export(opt) module 名字 ...;`、正文，以及可选的私有模块片段 `module :private;`。

*group* 由四种 *group-part* 组成：

| group-part | 是什么 | 例 |
|---|---|---|
| *control-line* | 普通指令 | `#include`、`#embed`、`#define`、`#undef`、`#line`、`#error`、`#warning`、`#pragma`、空指令 `#`、以及 *pp-import* |
| *if-section* | 条件编译块 | `#if`/`#ifdef`/`#ifndef` … `#elif`/`#elifdef`/`#elifndef` … `#else` … `#endif` |
| *text-line* | 普通源码行 | `int x = N;` |
| `#` *conditionally-supported-directive* | `#` 后跟一个**不是**标准指令名的东西 | `#ident "v1"`、`#assert` |

几处值得注意的细节：

- `#define` 的四种形式中，函数式宏要求宏名后紧跟 *lparen*——"**前面没有空白**的 `(`"。所以 `#define F (x) [x]` 定义的是对象式宏，替换列表是 `(x) [x]`。
- *pp-tokens* 是"一个或多个预处理记号"，所以 `#error` 和 `#pragma` 后面可以什么都没有（`opt`），而 `#include` 后面必须有东西。
- *embed-parameter-seq* 和 *pp-balanced-token-seq* 也定义在这里：后者是"括号、方括号、花括号都配平"的记号序列，供 `#embed` 参数和 `__has_embed` 使用（[[cpp.embed]]）。

```cpp run title="lparen.cpp" ok
#define F (x) [x]   // 对象式宏：F 后有空格
#define G(x) [x]    // 函数式宏
// F(1)  展开为  (x) [x](1)
// G (2) 展开为  [2]      —— 调用时宏名与 ( 之间可以有空白
int main() {}
```

!!! note "调用处可以有空白，定义处不行"
    *lparen* 只约束**定义**。调用函数式宏时，宏名之后"下一个预处理记号是 `(`"即可，中间的空白甚至换行都无所谓（[[cpp.replace.general#13]]）。

## 预处理是什么（¶1）

¶1 列出[[g:preprocessing|预处理]]的四种能力：有条件地处理或跳过源码片段、包含其他源文件、**从头文件单元导入宏**、宏替换。之所以叫"预"处理，是因为**概念上**它们发生在"翻译结果翻译单元"之前。

"从头文件单元导入宏"是 C++20 加进来的第四项：`import "foo.h";` 不仅导入声明，还会把 `foo.h` 末尾处于定义状态的宏带进来（[[cpp.import]]）。这是模块体系中唯一一种跨翻译单元传递宏的方式——命名模块（`import foo;`）**不导出宏**。

## 什么算预处理指令（¶2）

¶2 是全节核心。一个预处理指令是满足下列约束的预处理记号序列：

**在翻译阶段 4 开始时**，序列的第一个记号——称为[[g:directive-introducing-token|指令引导记号]]（*directive-introducing token*）——要么是源文件的第一个字符（前面可以有不含换行的空白），要么紧跟在**含换行的空白**之后；并且它是：

- ¶2.1 一个 `#` 预处理记号；或
- ¶2.2 一个 `import` 预处理记号，**同一逻辑行**上紧跟 *header-name*、`<`、*identifier* 或 `:`；或
- ¶2.3 一个 `module` 预处理记号，同一逻辑行上紧跟 *identifier*、`:` 或 `;`；或
- ¶2.4 一个 `export` 预处理记号，同一逻辑行上紧跟上面两种形式之一。

序列的**最后一个**记号是其中第一个"后面紧跟含换行空白"的记号——即指令在行尾结束。

!!! std
    At the start of translation phase 4, the first preprocessing token in the sequence, referred to as a directive-introducing token, begins with the first character in the source file ... or follows whitespace containing at least one new-line character

    "在阶段 4 开始时"、"位于行首"——这两个条件是**纯词法**的：判断一行是不是指令，不需要做宏展开，也不需要知道任何声明。

### 为什么强调"阶段 4 开始时"

因为宏展开发生在阶段 4 **之中**。如果宏展开能"造出"指令，那么判断某行是不是指令就得先做宏展开，而宏展开又依赖之前的指令——循环依赖。¶8 的例子正是这一点：

```cpp run title="empty-hash.cpp" error
#define EMPTY
EMPTY # include <cstdio>   // 不是指令：阶段 4 开始时这一行以 EMPTY 开头
int main() {}
```

展开后这一行变成 `# include <cstdio>` 出现在普通文本里——它不会被执行，而是作为普通记号流进入阶段 7，那里的 `#` 是语法错误。Clang 报 `expected unqualified-id`。

同理，宏展开的结果"不会作为预处理指令处理，即使它看起来像一个"（[[cpp.rescan#4]]）。宏造不出 `#include`、`#define`，也造不出 `#pragma`——后者正是 `_Pragma` 运算符存在的理由（[[cpp.pragma.op]]）。

### `import`/`module`/`export` 何时是指令

`import`、`module`、`export` 在阶段 4 都只是普通的 *identifier* 预处理记号（`export` 例外：它是关键字，但在阶段 4 还没有"关键字"的概念）。¶2.2–¶2.4 用"行首 + 后继记号"来识别它们：

| 行首 | 下一个记号 | 是指令吗 | 理由 |
|---|---|---|---|
| `import` | *header-name*、`<`、标识符、`:` | 是 | ¶2.2 |
| `import` | `::`、`->`、`(`、`=` … | 否 | 后继不在列表里 |
| `import` | 换行 | 否 | 必须在**同一逻辑行** |
| `module` | 标识符、`:`、`;` | 是 | ¶2.3 |
| `module` | 换行 | 否 | 同上 |
| `export` | `import …`/`module …`（且其本身满足上面条件） | 是 | ¶2.4 |
| `export` | 换行，下一行 `import foo;` | 第二行是指令 | 第二行的 `import` 自己就在行首 |

标准的例 1 把这些情形都列了一遍，其中最后两组最有教育意义：

```cpp
export                  // 不是指令
import foo;             // 是指令（但在阶段 7 非良构：export 与 import 被拆开了）

import ::               // 不是指令
import ->               // 不是指令
```

第一组里，`export` 单独一行不是指令（它后面紧跟换行）；而下一行的 `import foo;` **自己**满足 ¶2.2，所以是指令。到了阶段 7，`export` 成了一个悬空的关键字，后面跟着一个 *module-import-declaration*，语法错误。

规则中的后继记号集合是精心挑选的，目的是让旧代码中 `import`/`module` 作为普通标识符的用法尽量不受影响：

```cpp run title="import-as-identifier.cpp" ok
int module = 1;          // 行首是 int，不是指令
int import = 2;
int f() {
  return module + import;   // OK：不在行首
}
int main() { return f() - 3; }
```

但是只要撞上规则，就会被当成指令，哪怕程序员的本意是普通代码：

```cpp run title="import-template.cpp" error
template<class> struct import {};
import<int> x;   // error: 行首 import 后跟 <，这是一条 import 指令，<int> 被当成 header-name
int main() {}
```

Clang 报 `'int' file not found`——它确实去找名为 `int` 的头文件了。这正是 [[lex.pptoken#5.4.2.2]] 的推论：行首 `import` 之后的 `<...>` 会被词法分析为 *header-name*。

!!! pitfall "旧代码迁移"
    名为 `import` 或 `module` 的变量、函数、类型，只要出现在行首且后面跟着标识符、`<`、`:`、`;` 之一，就会被劫持成指令。最常见的事故是 `module m;`（声明一个类型为 `module` 的变量 `m`）——见下面的例 2。修复办法很简单：换行位置或加限定，如 `::module m;`。

### 指令以换行结束，即使在宏调用中间（注 1）

注 1：换行结束预处理指令，**即使**换行出现在本来会构成函数式宏调用的位置。

```cpp
#define F(x) x
#if F(1     // 指令在这里结束；F( 没有配对的 )，非良构
)
#endif
```

这和普通文本形成对比：在普通文本中，函数式宏调用可以跨越多行（[[cpp.replace.general#13]] 说调用内部的换行"被视为普通空白"）。

## text-line 与条件支持的指令（¶3）

¶3 第一句：一个预处理记号序列只有在**不以指令引导记号开头**时才是 *text-line*。这条规则把"不是 *text-line*"和"不是合法的 *control-line*"之间的缝隙堵死了。例 2：

```cpp
using module = int;
module i;               // 既不是 text-line，也不是 control-line
int foo() {
  return i;
}
```

第 2 行以 `module` + 标识符开头，满足 ¶2.3，所以它**是**指令序列，因而不可能是 *text-line*；但它又不匹配任何指令文法（不在 *module-file* 的开头位置），于是整个文件不是合法的 *preprocessing-file*，即非良构。Clang 报 `module declaration must occur at the start of the translation unit`。

¶3 第二句定义[[g:conditionally-supported-directive|条件支持的指令]]（*conditionally-supported-directive*）：`#` 后跟的记号序列不以任何标准指令名开头。它是有条件支持的，语义由实现定义（[[intro.compliance]] 中"有条件支持"意味着：不支持的实现必须给出诊断）。

```cpp run title="cond-directive.cpp" impl
#ident "build 42"   // GCC、Clang 都支持：把字符串写进目标文件的注释段
int main() {}
```

GCC 还支持 `#assert`、`#unassert`、`#include_next`、`#import`（后两者 Clang 也支持）。Clang 不支持 `#assert`，遇到它报 `invalid preprocessing directive`——这就是"不支持则诊断"。

脚注 118 补充：条件支持的指令**无论实现是否支持**都是预处理指令。这对 [[cpp.replace.general#14]] 很重要：宏调用的实参中出现"本来会作为指令"的行是非良构的，`#ident` 这类行也算。

## #embed 参数名不能是宏（¶4）

如果 `#embed` 的 *pp-tokens*（宏替换**之前**）中出现标识符 `limit`、`prefix`、`suffix` 或 `if_empty`，而它恰好被定义为宏，程序非良构。原因：`#embed` 的参数部分要做宏展开（[[cpp.embed.gen#8]]），如果参数名本身被替换，参数就无从识别。与其让 `#define limit 1` 静悄悄地改变 `#embed` 的含义，不如直接报错。[[cpp.cond#9]] 对 `__has_embed` 有同样的规定。

```cpp title="embed-macro-param.cpp" error
#define limit 1
const unsigned char d[] = {
#embed "data.bin" limit(2)   // error: limit 是宏
};
```

Clang 23 在这里报的是 `expected identifier`（宏展开后参数名变成了 `1`），结论相同。

!!! lawyer "offset 不在列表里"
    当前草案 ¶4 和 [[cpp.cond#9]] 列出的名字只有 `limit`、`prefix`、`suffix`、`if_empty`，**没有** `offset`，尽管 `offset` 已是标准参数（[[cpp.embed.param.offset]]）。这看起来是 `offset` 加入时漏改的措辞；按字面读，`#define offset 2` 之后再写 `#embed ... offset(1)` 并不触发 ¶4，而是参数展开成 `2(1)`，不符合 *embed-parameter-seq*，由 [[cpp.embed.gen#8]] 判非良构——结论一样，只是理由不同。

带前缀的参数（*embed-prefixed-parameter*，形如 `vendor::name(...)`）是有条件支持的、实现定义的。Clang 的 `clang::offset(n)` 就是这一类（Clang 23 尚未支持标准的 `offset`）。

## 全局模块片段里只能有指令（¶5）

¶5：在阶段 4 **开始时**，*pp-global-module-fragment*（`module;` 与模块声明之间的部分）的 *group* 中既不能有 *text-line*，也不能有 *pp-import*。

```cpp title="gmf.cppm"
module;
#include <cstdio>        // OK：#include 是 control-line
#define NDEBUG           // OK
int helper();            // error: GMF 中出现 text-line
export module m;
```

注意"阶段 4 开始时"：`#include` 引入的头文件内容当然有大量声明，但那是 `#include` 执行**之后**的事。¶5 约束的是**你直接写在 GMF 里的东西**。目的是让 GMF 只做一件事——用 `#include` 把传统头文件带进来——让构建工具能够不做完整解析就理解它。

!!! impl "实现现状"
    Clang 23 对 GMF 中直接写出的声明（如上例的 `int helper();`）**不给诊断**，即使加 `-pedantic`。这不符合 ¶5 的"shall"。

## 被跳过的组：语法放宽（¶6）

¶6：在被跳过的组（[[cpp.cond#13]]）中，指令名与换行之间可以是**任何**预处理记号序列。

被跳过的组里，预处理器只关心指令名，以追踪 `#if` 的嵌套层次；其余一律忽略。于是下面这些在被跳过的组中全部合法：

```cpp run title="skipped.cpp" ok
#if 0
#  foo bar baz                   // 不是任何标准指令：不要紧
#  if this is (not an expression // 不求值，只计嵌套层数
#  endif trailing junk           // 跳过组中的 #endif 后可跟任意记号
#  include <no/such/file>        // 不执行
#  error not triggered           // 不执行
#  define F(                     // 不检查
#endif
int main() {}
```

但"任意预处理记号序列"仍然要求**能被切分为预处理记号**：阶段 3 对整个文件一视同仁，跳过组也不例外。所以未闭合的 `/*` 注释在跳过组里也是非良构的；按 [[lex.pptoken#2]]，落入"其他单个字符"类的孤立 `'` 或 `"` 也是非良构的。

!!! lawyer "Clang 对跳过组的词法宽容"
    Clang 23 在被跳过的组中遇到孤立的 `'`（例如 `#if 0` 里写 `don't`）**不报任何诊断**。按草案这本应非良构。这是实践中广为依赖的宽容：大量代码用 `#if 0` 注释掉英文散文。

## 指令内只允许空格和水平制表（¶7）

¶7：从指令引导记号之后到终结换行之前，预处理记号之间出现的空白只能是 U+0020 空格和 U+0009 水平制表（包括阶段 3 中替换注释而来的空格，以及"可能由其他空白替换而来"的空格）。

括号里的话是关键：阶段 3 中"除换行外的非空空白序列是保留还是替换为一个空格"是**未指定**的（[[lex.phases#1]]）。所以 `#define\vA 1`（垂直制表）是否违反 ¶7 取决于实现在阶段 3 是否已经把 `\v` 换成了空格。Clang 23 接受它且不告警，可以理解为它在阶段 3 做了替换。

注释可以出现在指令中（脚注 116），因为注释在阶段 3 已经变成空格：

```cpp run title="comment-in-directive.cpp" ok
#define N /* 注释变成空格 */ 3
#if N == 3 // 行尾注释同样
#endif /* 甚至 #endif 后面 */
int main() { return N - 3; }
```

## 指令中的记号默认不展开（¶8）

¶8：预处理指令中的预处理记号**不做宏展开**，除非另有规定。规定了要展开的有：

| 指令 | 是否宏展开 | 出处 |
|---|---|---|
| `#if` / `#elif` | 是（`defined` 的操作数除外） | [[cpp.cond#9]] |
| `#ifdef` / `#ifndef` / `#elifdef` / `#elifndef` | 否：直接检查标识符 | [[cpp.cond#12]] |
| `#include` | 仅当不匹配 `<...>`/`"..."` 形式时 | [[cpp.include#7]] |
| `#embed` | 参数部分总是展开；资源名仅在不匹配直接形式时 | [[cpp.embed.gen#8]]、[[cpp.embed.gen#14]] |
| `#line` | 仅当不匹配直接形式时 | [[cpp.line#5]] |
| `import`（*pp-import*） | 是 | [[cpp.import#1]] |
| `module`（*pp-module*） | 模块名部分**不能**展开，其余部分展开 | [[cpp.module#2]] |
| `#define` / `#undef` | 否 | — |
| `#error` / `#warning` | 否 | — |
| `#pragma` | 否（实现可以对特定 pragma 自行展开） | [[cpp.pragma]] |

`#define` 不展开意味着宏名本身不会被替换：

```cpp run title="define-no-expand.cpp" ok
#define A B
#define A B      // 重定义 A，而不是定义 B——宏名 A 不被展开
#undef A         // 同理，取消的是 A
int main() {}
```

此外 [[cpp.replace.general#10]] 规定：在可以开始指令的位置，`#` 后面的标识符不受宏替换——所以 `#define include` 不会让 `#include` 失效（虽然定义一个叫 `include` 的宏本身是合法的）。

## 历史与演进

!!! history
    - **C++98**：指令就是"以 `#` 开头（前面可有空白）的行"，文法与 C89 基本一致。
    - **C++11**：与 C99 预处理器同步（[[N1653]]）：可变参数宏、`_Pragma`、空宏实参。
    - **C++20**：模块。`import`/`module`/`export` 开头的行成为指令，并引入 *module-file* 文法（[[P1703R1]] 让头文件单元导入在预处理时被识别；[[P1857R3]] 把这套"指令化"推广到模块声明，目的是让依赖扫描只需预处理）。
    - **C++23**：`#elifdef`/`#elifndef`（[[P2334R1]]）、`#warning`（[[P2437R1]]）。
    - **C++26**：`#embed` 及其参数文法（[[P1967R14]]）{{c++26}}。原先散落在本章的若干 UB 被改写为非良构或 IFNDR。

### 为什么要把 import/module 变成"指令"

C++20 早期的模块设计里，`import` 只是一个普通声明，在阶段 7 才被处理。问题是：`import "foo.h";` 会**导入宏**，而这些宏又会影响后续行的预处理——于是不完整编译就无法知道一个文件依赖哪些模块，构建系统也就没法在编译前排出编译顺序。[[P1703R1]] 和 [[P1857R3]] 的方案是：让这些行在阶段 4 就被识别，并用¶2 中纯词法的规则限定它们的形状——只要做一次（相对便宜的）预处理，就能扫描出全部依赖。这也是 [[cpp.module#1]] 禁止模块名由宏生成的原因。

## 陷阱

!!! pitfall "宏实参中的 #if"
    ```cpp
    printf("%d\n", MAX(a,
    #ifdef BIG
        1000
    #else
        10
    #endif
    ));
    ```
    如果 `printf` 或 `MAX` 是宏，这段代码非良构（[[cpp.replace.general#14]]；C++23 及以前是 UB）。很多 C 标准库把 `printf`、`memcpy` 等实现为宏，于是这段代码"有时能编过有时不能"。Clang 对此给 `-Wembedded-directive` 警告。

!!! pitfall "行首 import 劫持"
    `import<T>`、`import :: foo`、`module m;` 三者中只有 `import ::` 是安全的（`::` 不在 ¶2.2 的后继列表里）。

## 思考题

!!! question "思考题 1"
    下面两行哪一行是预处理指令？到阶段 7 会怎样？
    ```cpp
    export module
    m;
    ```

<details markdown="1">
<summary>展开查看答案与解析</summary>

两行都**不是**指令。第一行：`export` 后面紧跟 `module`，但 `module` 后面在同一逻辑行上没有标识符、`:`、`;`（紧跟换行），所以 `module` 不满足 ¶2.3，`export` 也就不满足 ¶2.4。第二行以标识符 `m` 开头，是 *text-line*。

于是这两行作为普通记号进入后续阶段。`module` 没有被替换为 *module-keyword*（[[cpp.module#2]]），阶段 7 看到的是普通标识符 `module`——不可能构成模块声明，结果是语法错误。教训：模块声明的 `module` 和名字必须写在同一行。
</details>

!!! question "思考题 2"
    为什么 `#define EMPTY` 后的 `EMPTY #define X 1` 不定义 `X`，但 `#define D defined(A)` 后的 `#if D` 却"能工作"（至少在 Clang 上）？两者有何本质区别？

<details markdown="1">
<summary>展开查看答案与解析</summary>

第一种是"宏造指令"：判定指令发生在阶段 4 开始时（¶2），宏展开在其后，所以永远造不出指令。这是规则的**定义性**后果，各实现必然一致。

第二种是 `#if` 表达式内部的宏展开产生了 `defined` 记号。这被 [[cpp.cond#9]] 判为 IFNDR（C++23 及以前是 UB）。它"能工作"只是因为实现选择了某种行为（Clang 照常求值，同时给 `-Wexpansion-to-defined` 警告），标准并不保证。
</details>

## 小结

!!! summary
    - 预处理指令 = 阶段 4 开始时位于行首的**指令引导记号**开启、到行尾结束的记号序列。引导记号有四种：`#`、满足条件的 `import`、`module`、`export`。
    - 判定是纯词法的：宏展开**不能**制造或消灭指令。
    - `import`/`module` 的识别看"同一逻辑行上的下一个记号"；`import<...>` 会劫持模板名 `import`。
    - `#` 后跟非标准名字是**条件支持的指令**，不支持就必须诊断。
    - 全局模块片段（阶段 4 开始时）只能有指令。
    - 被跳过的组中，指令只看到指令名为止，其余随意——但词法上仍需能切成预处理记号。
    - 指令内的空白只能是空格和水平制表；指令内的记号默认不展开，`#if`/`#elif`、`#include`/`#embed`/`#line` 的宏形式、`import` 是例外。
