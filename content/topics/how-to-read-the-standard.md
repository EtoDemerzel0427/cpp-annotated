---
title: 如何阅读 C++ 标准
summary: 怎样在 C++ 标准里找到回答一个问题的条文、读懂它、准确地引用它，以及标准怎样随提案和缺陷报告变化。
status: done
order: 1
related: intro, intro.defs, intro.compliance, intro.structure, syntax
tags: 导读, 方法, 工具
updated: 2026-10-19
---

!!! tldr
    - 标准是写给编译器和标准库实现者的规格说明，不适合从头读到尾。带着一个具体问题去查，才读得进去。
    - 条款用方括号里的稳定名定位，如 `[basic.life]`；引用时写 `[basic.life]/8`，讨论旧版本时注明版本，因为段落号会变。
    - 只有正文、语法和 Annex D 有约束力。注、例子、脚注只帮助理解，不能单独作为论据。
    - shall 是要求，should 是建议，may 是允许，can 只陈述事实。斜体的词是在那里定义的术语，读规则之前先找定义。
    - 编译器的行为只是证据，不是结论。编译器之间、编译器与标准之间有分歧时，正是需要查标准的时候。

## 标准和草案

C++ 标准的正式名称是 ISO/IEC 14882，由 WG21（C++ 标准委员会）制定。ISO 发布的正式版本是收费的，但委员会的**工作草案**（working draft）公开，而且每个正式版本都有一份内容几乎相同的公开草案：

| 版本 | 最接近的公开草案 | `__cplusplus` |
|---|---|---|
| C++98、C++03 | — | `199711L` |
| C++11 | [[N3337]] | `201103L` |
| C++14 | [[N4140]] | `201402L` |
| C++17 | [[N4659]] | `201703L` |
| C++20 | [[N4861]] | `202002L` |
| C++23 | [[N4950]] | `202302L` |
| C++26 | 当前工作草案 | 当前草案规定为 `202603L`（[[cpp.predefined]]） |

想知道某条规则在 C++17 里怎么写，就去读 N4659。本站以 eel.is 上的当前工作草案为准。草案里已经有了附录 [[diff.cpp26]]（与 C++26 的差异），说明 C++26 已经定稿，草案开始积累下一版的修改。本站的 {{c++26}} 标记指 C++26 引入的特性。

标准的章节结构见 [[intro.structure]]：第 1–4 章是范围、术语和总则，第 5–15 章是核心语言（从词法 [[lex]] 到预处理 [[cpp]]），第 16–33 章是标准库，最后是附录 A–G（语法汇总、实现限制、版本差异、弃用特性、UB 汇总、IFNDR 汇总等）。

## 条款的地址

### 稳定名

每个条款都有一个写在方括号里的**稳定名**（stable name）：`[basic.life]`、`[dcl.init.list]`、`[over.match.best]`。章节号会随版本变化，`[basic.life]` 在 C++17 中是 6.8，在当前草案中是 6.8.4，稳定名则尽量不变。所以引用条款时总是用稳定名。

稳定名是分层的：`dcl.init` 是初始化，`dcl.init.list` 是其中的列表初始化，`dcl.init.aggr` 是聚合初始化。也有例外：条款搬家后有时保留旧名字，`[intro.execution]`、`[intro.races]` 现在在第 6 章 [[basic.exec]] 之下，名字仍以 `intro.` 开头。

### 段落号

每个条款里的段落从 1 开始编号，eel.is 把编号显示在页边。段落里的列表项编号为"段落号.项号"，嵌套列表继续加层：[[intro.compliance]] 中的 2.3.4 是第 2 段第 3 项的第 4 子项。注（Note）和例子（Example）属于它们所在的段落，在条款内另行编号为 Note 1、Example 2 等。

### 怎样引用

| 写法 | 含义 |
|---|---|
| `[basic.life]` | 整个条款 |
| `[basic.life]/8` 或 `[basic.life] p8` | 第 8 段 |
| `[basic.life]/8.1` | 第 8 段第 1 项 |
| `C++23 [basic.life]/8` 或 `N4950 [basic.life]/8` | 指定版本的第 8 段 |
| `[basic.life]/8, Note 5` | 第 8 段中的注 5 |

段落号在版本之间经常变化，讨论旧版本的行为时一定要注明版本。eel.is 的网址与这种写法一一对应：`https://eel.is/c++draft/basic.life#8.1`。本站的 `[[basic.life#8]]` 渲染为 [[basic.life#8]]。

## 哪些文字有约束力

标准里的文字分两类：

- **规范性**（normative）文字构成要求，包括正文段落、语法产生式和唯一的规范性附录 Annex D（弃用特性）；
- **资料性**（informative）文字只帮助理解，不构成要求，包括注、例子、脚注、其余附录以及目录和索引。

所以不能只凭一条注或一个例子论证某件事合法或非法。注和例子本应与正文一致，两者冲突时以正文为准，而且这通常说明标准有缺陷，往往能找到对应的 CWG issue。

不过注和例子很有用：它们常常点出正文的推论，或者直接表明委员会的意图。下文查证的例子就靠一个标准例子确认了结论。

***Recommended practice*** 段落是规范性的，但用 should 表述，只是建议，不影响实现是否符合标准。

### shall、should、may、can

标准按 ISO 的起草规则使用这几个助动词：

| 词 | 含义 | 例 |
|---|---|---|
| shall / shall not | 要求 / 禁止 | "A program shall contain exactly one function called `main`"（[[basic.start.main]]） |
| should / should not | 建议 | "An implementation should issue a diagnostic"（[[intro.abstract]]） |
| may / need not | 允许 | "A conforming implementation may have extensions"（[[intro.compliance]]） |
| can / cannot | 能够、可能，只陈述事实 | 多见于注中 |

程序违反一条 shall 规则的后果由 [[intro.compliance]] 决定：默认是非良构，编译器必须给出诊断；规则注明 no diagnostic is required 时是 IFNDR（非良构，但不要求诊断，编译器可能毫无提示地编译通过）；规则本身说结果未定义时是 UB。各种行为分类见 [[intro.defs]]。

注里刻意用 can 而不用 may，因为注不能授予许可。在注里读到"实现可以……"，那只是在描述正文已经允许的事情。

## 斜体就是定义

正文中以*斜体*出现、紧跟着解释的词，就是在那里定义的术语。例如 [[basic.life#2]] 定义了 *lifetime* 和 *vacuous initialization*。之后每次出现这个词，都严格指这个定义，日常英语的含义不算数。

- 跨章节通用的术语集中定义在第 3 章 [[intro.defs]]；
- 多数核心术语就地定义：*odr-use* 在 [[basic.def.odr]]，*glvalue* 在 [[basic.lval]]，*core constant expression* 在 [[expr.const.core]]；
- 标准的索引列出每个术语的定义位置，eel.is 上也可以搜索。

object、entity、variable、name 在标准里都有精确且互不相同的含义。读到一个拿不准的词，先找它的定义，这是避免误读的第一步。

## 语法和库规范

语法产生式的记法见 [[syntax]]：斜体是非终结符，等宽字体是终结符，下标 opt 表示可选。符合语法只是第一步，离良构还远。

库函数的规范由若干要素组成，精确含义在 [[structure.specifications]] 中定义：

- *Constraints*：不满足时，这个函数不参与重载决议；
- *Mandates*：不满足时，程序非良构；
- *Preconditions*：违反时是 UB；
- *Hardened preconditions* {{c++26}}：在加固实现（hardened implementation）中，函数执行前以终止型语义检查这些条件，违反就终止程序；在非加固实现中违反是 UB；
- *Effects*、*Returns*、*Throws*、*Complexity* 等。

"*Effects*: Equivalent to: ..." 的确切含义也在 [[structure.specifications]] 里，读库条文前先读这一节。标为 exposition only 的成员和概念只为描述方便而设，实现不必真的提供（[[conventions]]）。

## 一次完整的查证：`unsigned char x = x;`

```cpp ub
unsigned char x = 12;
void f() {
  unsigned char x = x;   // 右边的 x 是哪个？这一行行为如何？
}
```

一个熟悉 C++26 的读者可能会想：内层的 `x` 还没初始化，读取未初始化的自动变量是错误行为（erroneous behavior，C++26 起有定义、但被标准认定为错误的行为）。按下面的步骤查证：

1. **右边的 `x` 指哪个？** [[basic.scope.pdecl#1]] 规定，声明符所声明的名字从完整的声明符之后就开始生效，也就是在初始化器之前。所以初始化器里的 `x` 已经是内层的 `x`，外层的被遮住了。
2. **这时内层 `x` 的生命周期开始了吗？** [[basic.life#2]]：对象的生命周期在它的初始化完成时开始。现在正处在它的初始化过程中，生命周期还没有开始。
3. **在生命周期开始之前读它会怎样？** [[basic.life#8]]：存储已经分配、生命周期还没开始时，通过指代该对象的 glvalue 访问它是 UB（[[basic.life#8.1]]）。初始化器对 `x` 做了左值到右值转换，这是一次访问（见 [[intro.defs]] 中 *access* 的定义）。
4. **有没有旁证？** [[basic.scope.pdecl]] 的例 1 正是这段代码，并写明第二个 `x` 的初始化有未定义行为，因为初始化器在它的生命周期之外访问了它。

结论是 UB，不是错误行为。错误行为适用于生命周期已经开始、只是值是错误值的对象（比如 `unsigned char y;` 之后读 `y`）；这里对象的生命周期根本还没开始。

查证的套路是：先确定名字指什么（名字查找），再确定对象处于什么状态（生命周期、值），然后找到规定这个操作的段落，最后用注和例子交叉验证。

编译器的行为只能作参考：本机 Clang 23 对上面这段代码在 `-Wall -Wextra` 下没有任何警告，只有在函数里接着使用 `x` 时，才给出 `-Wuninitialized`。

## 标准怎样变化

**提案。** 所有实质性修改都通过提案（paper）进入标准。提案编号形如 P2795R5：P 加四位数字是提案号，R 加数字是修订版本。早期文件和工作草案用 N 编号，如 N4950。提案经委员会的各个小组审议、全体投票通过后，由编辑合并进工作草案。本站的 `[[P2795]]`、`[[N4950]]` 链接到 wg21.link，那是委员会文档的短链接服务。

**Issue 与 DR。** 标准中的错误、含糊和矛盾通过 issue 处理。核心语言的叫 CWG issue，库的叫 LWG issue，各有一份公开列表，记录问题、讨论和状态。链接写作 `[[CWG2551]]`、`[[LWG3000]]`。如果一个 issue 的决议被当作对已发布标准的缺陷修正，就叫做**缺陷报告**（defect report，DR）。编译器通常把 DR 也应用到旧的语言模式，所以某些 C++23 的修改在 `-std=c++17` 下也生效。本站用 {{dr}} 标记这类变化。有些提案也以 DR 的身份通过，效果相同。

**编辑性修改。** 不改变技术含义的修改（措辞澄清、排版、调整章节）由编辑直接在 GitHub 的 cplusplus/draft 仓库中完成。章节号、段落号的变化很多来自这里，这也是要用稳定名引用的原因。

## 工具

| 工具 | 用途 |
|---|---|
| eel.is/c++draft | 当前工作草案的 HTML 版，按稳定名分页，可以直接链接到段落（`#8.1`）。本站的条文以此为准 |
| timsong-cpp.github.io/cppwp | 同样风格的 HTML 版，还提供旧版本（`/cppwp/n4950/`、`/cppwp/n4659/` 等），适合查旧标准 |
| github.com/cplusplus/draft | 草案的 LaTeX 源码，可以看每次修改的 diff，追溯某段措辞的来历 |
| wg21.link | 提案、N 文档、CWG/LWG issue 的短链接 |
| CWG / LWG issue 列表 | 查一条规则是否有已知缺陷，委员会的意图是什么 |
| cppreference.com | 非官方的参考网站，按特性组织，标明版本差异、DR 和编译器支持情况；适合作为入口，结论要回到标准条文上 |
| Compiler Explorer（godbolt.org） | 用多个编译器、多个版本快速验证；本站代码块的 godbolt 按钮直接打开它 |
| 编译器状态页 | Clang 的 C++ Status、GCC 的 C++ Standards Support、MSVC 的语言符合性表，查某个特性从哪个版本开始实现 |

三大编译器都有缺陷，都有尚未实现的特性，默认模式也都不完全符合标准（见 [[intro.compliance]] 中关于扩展的部分）。"Clang 接受了"或"GCC 报错了"只是证据，要结合条文才能下结论。

## 查标准的流程

1. **把问题问具体。** 把"这段代码对吗"拆成"这个名字查找到哪个声明""这里发生了什么转换""这次读取发生在生命周期之内吗"。
2. **找到条款。** 从 [[intro.structure]] 的结构图、本站目录、eel.is 的索引或 cppreference 的参见链接出发，找到最相关的稳定名。
3. **找到段落。** 先读条款开头的定义和总述，再定位到具体段落。注意列表项之间是"且"还是"或"。
4. **追定义。** 段落里的斜体术语和 `([xxx])` 形式的交叉引用，有必要就追过去，不要凭日常经验猜。
5. **看注和例子。** 它们常常直接回答问题，或者指出你忽略的推论。
6. **查附录。** Annex C（版本差异）、Annex F（UB 汇总）、Annex G（IFNDR 汇总）是很好的索引。
7. **查 issue。** 条文看起来矛盾或有缺漏时，搜 CWG/LWG issue 列表，看是否已有讨论。
8. **用编译器验证。** 换几个编译器和版本，开 `-pedantic-errors` 和 sanitizer。编译器之间有分歧，本身就说明问题不简单。
9. **写下结论和出处。** 用 `[stable.name]/N` 的形式，注明版本。

## 阅读路线

本站按标准的章节组织，但不必按章节顺序读。一条可行的路线：

1. **元语言**：本页，[[intro.defs]]（尤其是行为分类），[[intro.compliance]]（符合性、as-if 规则、可观察行为），[[syntax]]（语法记法）。
2. **程序怎样被翻译和组织**：[[lex.phases]]（翻译阶段），[[basic.def]] 与 [[basic.def.odr]]（声明、定义与 ODR），[[basic.scope]] 与 [[basic.lookup]]（作用域与名字查找），[[basic.link]]（链接）。
3. **对象模型**：[[basic.memobj]]、[[intro.object]]、[[basic.life]]（对象、存储、生命周期），[[basic.types]]（类型），[[basic.lval]] 与 [[conv]]（值类别与标准转换）。
4. **执行**：[[intro.execution]]（求值顺序），[[intro.multithread]]（内存模型与数据竞争），[[expr.const]]（常量求值）。
5. **按需深入**：[[dcl.init]]（初始化）、[[class]]（类）、[[over]]（重载）、[[temp]]（模板）、[[except]]（异常）、[[module]]（模块）、[[basic.contract]]（契约）。库部分先读 [[library]] 的描述方法，再按兴趣进入各章。
