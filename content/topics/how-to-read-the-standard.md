---
title: 如何阅读 C++ 标准
summary: 一份实用指南：标准的组织方式、stable name 与段落号、规范性与资料性文字、shall/should/may/can、如何引用条文、草案与正式标准的关系、提案和 CWG issue 如何改变标准、常用工具，以及本站的推荐阅读顺序。
status: done
order: 1
related: intro, intro.defs, intro.compliance, intro.structure, syntax
tags: 导读, 方法, 工具
updated: 2026-10-17
---

C++ 标准有两千多页，而且不是为"学习 C++"写的——它是写给编译器和标准库实现者的规格说明。从第一页逐页读到最后一页既不现实，也没有必要。

这一页讲的是**怎样带着问题查标准、怎样读懂查到的条文、怎样准确地引用它**。

## 一、标准是什么、在哪里

**C++ 标准**的正式名称是 ISO/IEC 14882《Programming languages — C++》，由 ISO/IEC JTC 1/SC 22/WG 21（简称 **WG21**，即 C++ 标准委员会）制定。

ISO 发布的正式版本是收费的；但委员会的**工作草案**（working draft）是公开的，而且每个正式版本都有一份内容几乎相同的公开草案。

| 版本 | ISO 编号 | 最接近的公开草案 | `__cplusplus` |
|---|---|---|---|
| C++98 | 14882:1998 | — | `199711L` |
| C++03 | 14882:2003 | — | `199711L` |
| C++11 | 14882:2011 | [[N3337]] | `201103L` |
| C++14 | 14882:2014 | [[N4140]] | `201402L` |
| C++17 | 14882:2017 | [[N4659]] | `201703L` |
| C++20 | 14882:2020 | [[N4861]] | `202002L` |
| C++23 | — | [[N4950]] | `202302L` |
| C++26 | — | 当前工作草案 | 当前草案规定为 `202603L`（[[cpp.predefined]]） |

表中的 N 编号是业界习惯引用的"与正式版仅有编辑性差异"的草案（有的是正式版发布后的第一份工作草案，含少量编辑性修正）。本站以 **eel.is 上的当前工作草案**为准，它对应 GitHub 仓库 cplusplus/draft 的最新提交。

!!! note "当前草案已在 C++26 之后"
    本站构建时抓取的草案中已经有了 Annex C 的 [[diff.cpp26]]（"C++ 与 ISO C++ 2026"），说明 C++26 已经定稿，工作草案开始积累下一版本的变更。本站在标注 {{c++26}} 时指的是 C++26 引入的特性；对 C++26 之后才加入的少数规则，会在正文中单独说明。

## 二、全书的组织

详见 [[intro.structure]]。概括地说：

- **第 1–4 章**：范围、规范性引用、术语定义、总则（[[intro]]）。
- **第 5–15 章**：**核心语言**（core language），从词法 [[lex]] 到预处理 [[cpp]]。
- **第 16–33 章**：**标准库**（library），第 16 章 [[library]] 规定库条款的阅读方法。
- **附录 A–G**：语法汇总、实现限制、兼容性差异、弃用特性（唯一规范性的附录）、UAX #31、UB 汇总、IFNDR 汇总。

核心语言部分由委员会的 **CWG**（Core Working Group）负责措辞，库部分由 **LWG**（Library Working Group）负责。这个分工也反映在 issue 列表上：核心语言的问题叫 CWG issue，库的问题叫 LWG issue。

## 三、条款的地址：stable name 与段落号

### stable name

每个条款都有一个**稳定名**（stable name），写在方括号里：`[basic.life]`、`[dcl.init.list]`、`[over.match.best]`。

章节号会随版本变化（[basic.life] 在 C++17 的 N4659 中是 6.8，在当前草案中是 6.8.4），stable name 则尽量保持不变。**引用条文时永远用 stable name**，不要用章节号。

stable name 是层级式的：`dcl.init` 是"初始化"，`dcl.init.list` 是其中的"列表初始化"，`dcl.init.aggr` 是"聚合初始化"。从名字往往就能猜到条款在哪。

也有例外：条款在版本间移动时，名字有时保持历史形态。`[intro.execution]`、`[intro.races]` 今天在第 6 章 [[basic.exec]] 之下，但名字仍以 `intro.` 开头，因为它们最初在引言章里。

### 段落号

每个条款中的段落从 1 开始编号（eel.is 上显示在左侧页边）。段落里的列表项编号为"段落号.项号"，嵌套列表继续加层：[[intro.compliance]] 中的 ¶2.3.4 就是第 2 段第 3 项的第 4 子项。

注（Note）和例子（Example）**属于**它们所在的段落，不单独编号，而是在条款内依次编号为"Note 1"、"Example 2"等。

### 怎么引用

| 写法 | 含义 |
|---|---|
| `[basic.life]` | 整个条款 |
| `[basic.life]/8` 或 `[basic.life] p8` | 第 8 段 |
| `[basic.life]/8.1` | 第 8 段第 1 项 |
| `N4950 [basic.life]/8` 或 `C++23 [basic.life]/8` | 指定版本（段落号在版本间会变！） |
| `[basic.life]/8, Note 5` | 某段中的注 |

段落号在不同版本之间经常变化，所以讨论历史行为时一定要注明版本。eel.is 的 URL 直接对应这种写法：`https://eel.is/c++draft/basic.life#8.1`。本站的链接语法也一样：`[[basic.life#8]]` 渲染为 [[basic.life#8]]。

## 四、规范性与资料性文字

标准里的文字分两种效力：

- **规范性**（normative）：构成要求。正文段落、语法产生式、规范性附录（Annex D）。
- **资料性**（informative）：帮助理解，**不构成要求**。包括：
    - 注（`[Note: ... — end note]`）；
    - 例子（`[Example: ... — end example]`）；
    - 脚注；
    - 资料性附录（A、B、C、E、F、G）；
    - 目录、索引、参考文献。

这条区分对 language lawyer 至关重要：**不能只凭注或例子论证一件事是否合法**。注和例子应该与规范性文字一致；如果两者冲突，以规范性文字为准，而这种冲突通常意味着标准有缺陷（往往会有一个对应的 CWG issue）。

但注和例子很有价值：它们往往指出了规范性文字的推论，或者给出了委员会意图的直接证据。下面第八节的例子就是一例。

还有一类介于两者之间的是 ***Recommended practice*** 段落：它们是规范性的，但用 "should" 表述，只是建议，不影响符合性。

## 五、助动词：shall / should / may / can

标准遵循 ISO 的起草规则（ISO/IEC Directives, Part 2），每个助动词有确定含义：

| 词 | 含义 | 例 |
|---|---|---|
| **shall** / shall not | 要求 / 禁止 | "A program shall contain exactly one function called `main`"（[[basic.start.main]]） |
| **should** / should not | 建议 | "An implementation should issue a diagnostic"（[[intro.abstract]]） |
| **may** / need not | 允许 | "A conforming implementation may have extensions"（[[intro.compliance]]） |
| **can** / cannot | 能力、可能性（陈述事实） | 多见于注："An implementation can express such a condition via ..." |

对程序说 "shall" 时，违反的后果由 [[intro.compliance]] 决定：

1. 默认是可诊断的 ill-formed（实现必须给出至少一条诊断信息）；
2. 若注明 "no diagnostic is required"，则是 IFNDR；
3. 若规则本身说结果是 UB，则是 UB。

见 [[intro.defs]] 中的行为分类。

在注里，标准刻意用 "can" 而不是 "may"，因为注不能授予许可——如果你在注里看到"实现可以……"，那只是在描述规范性文字已经允许的事情。

## 六、术语：斜体就是定义

标准正文中以*斜体*出现、紧跟着解释的词，就是在**那里定义**的术语。例如 [[basic.life]] ¶2 中的 *lifetime*、*vacuous initialization*。之后每次出现这个词，都严格指这个定义——日常英语的含义不算数。

- 跨章节通用的术语集中定义在第 3 章 [[intro.defs]]，带 ⟨领域⟩ 限定。
- 大多数核心术语是就地定义的：*odr-use*（[[basic.def.odr]]）、*glvalue*（[[basic.lval]]）、*core constant expression*（[[expr.const.core]]）等。
- 标准的索引（Index）列出每个术语的定义位置，eel.is 上也可以搜索。

读到一个关键词不确定含义时，**先找它的定义**，这是避免误读的第一步。"object"、"entity"、"variable"、"name" 在标准里都有精确且互不相同的含义，不能混用。

## 七、语法与库规范的读法

- **语法产生式**：斜体非终结符、等宽终结符、下标 opt 表示可选。见 [[syntax]]。语法只是第一道筛子：符合语法远不等于良构。
- **库规范**：每个函数的规范由若干要素组成，精确含义见 [[structure.specifications]]：
    - *Constraints*：不满足则不参与重载决议；
    - *Mandates*：不满足则非良构；
    - *Preconditions*：违反则 UB；
    - *Hardened preconditions* {{c++26}}；
    - *Effects*、*Returns*、*Throws*、*Complexity* 等。

  "*Effects*: Equivalent to: ..." 的含义也在 [[structure.specifications]] 中定义，读库条文前务必先读这一节。
- **exposition only**：库规范里标为"exposition only"的成员和概念只是为了描述方便，实现不必真的提供（[[conventions]]）。

## 八、一次完整的查证：`unsigned char x = x;`

问题：

```cpp ub
unsigned char x = 12;
void f() {
  unsigned char x = x;   // 右边的 x 是哪个？这一行行为如何？
}
```

一个 C++26 读者可能这样想："内层的 `x` 还没初始化，读取未初始化的自动变量是错误行为（EB）。"让我们查证。

1. **右边的 `x` 指哪个？** 查名字的作用域：[[basic.scope.pdecl]] ¶1 规定，一个声明符所声明的名字，其声明点（*locus*）紧跟在完整的声明符之后、初始化器之前。所以初始化器里的 `x` 已经是**内层**的 `x`，外层的 `x` 被遮蔽了。
2. **此时内层 `x` 的生命周期开始了吗？** [[basic.life]] ¶2：对象的生命周期在其初始化完成时开始。现在正处在它的初始化当中，生命周期**尚未开始**。
3. **在生命周期开始前读它会怎样？** [[basic.life]] ¶8：在对象生命周期开始之前（存储已分配），用指代它的 glvalue 去**访问**该对象，行为未定义（¶8.1）。初始化器对 `x` 做左值到右值转换，这是一次访问（[[intro.defs]] 中 *access* 的定义）。
4. **有没有旁证？** [[basic.scope.pdecl]] 的例 1 正是这段代码，并明确写道：第二个 `x` 的初始化具有未定义行为，因为初始化器在其生命周期之外访问了它。

结论：这是 **UB**，而不是 EB。EB 适用于"生命周期已经开始（例如经过 vacuous initialization）、但值是错误值"的对象；而这里对象的生命周期根本还没开始。

这个过程展示了查标准的基本套路：**先确定名字指什么（查找）→ 再确定对象处于什么状态（生命周期、值）→ 然后找到规定这一操作的段落 → 用注和例子交叉验证。**

编译器的行为可以作为参考，但不是依据：本机 Clang 23 在 `-Wall -Wextra` 下对这段代码**没有任何警告**（把类型换成 `int` 才会给出 `-Wuninitialized` 警告）。

## 九、标准是怎样变化的

### 提案（paper）

所有实质性变化都通过**提案**进入标准。提案编号形如 **P2795R5**：P 加四位数字是提案号，R 加数字是修订版本。早期和官方文件使用 **N** 编号（如工作草案 N4950）。

提案通常经过研究小组（SG）→ 演进组（EWG 语言 / LEWG 库）→ 措辞组（CWG / LWG）→ 全体会议（plenary）投票，被采纳后由项目编辑合并进工作草案。

- 本站的链接语法 `[[P2795]]`、`[[N4950]]` 会指向 `wg21.link`，那是委员会文档的短链接服务：`https://wg21.link/p2795` 跳到最新修订版，`https://wg21.link/p2795r5` 跳到指定版本。
- 委员会每隔一段时间发布一期"mailing"，汇总新提案，存放在 open-std.org 的 WG21 文档目录下。

### Issue 与缺陷报告（DR）

标准中的错误、含糊、矛盾之处，通过 **issue** 处理：

- **CWG issue**（核心语言）和 **LWG issue**（库）各有一份公开列表，记录问题、讨论和状态（open、drafting、review、ready、DR、NAD 等）。链接形如 `[[CWG2551]]`、`[[LWG3000]]`。
- 一个 issue 的决议若被视为对已发布标准的**缺陷修正**，就称为 **DR**（defect report）。实践中，编译器通常把 DR 回溯应用到相关的旧语言模式——所以某些"C++23 的修改"在 `-std=c++17` 下也会生效。本站用 {{dr}} 标记这类变化。
- 有些提案也以 DR 的身份被采纳（例如修正 C++20 设计缺陷的提案），效果相同。

### 编辑性修改

不改变技术含义的修改（措辞澄清、排版、重组章节）由项目编辑直接在 GitHub 的 cplusplus/draft 仓库中完成。章节号、段落号的变化很多来自这里——这也是为什么要用 stable name。

## 十、工具

| 工具 | 用途 |
|---|---|
| **eel.is/c++draft** | 当前工作草案的 HTML 版，按 stable name 分页，段落可直接链接（`#8.1`）。本站所有条文以此为准 |
| **timsong-cpp.github.io/cppwp** | 同样风格的 HTML 版，同时提供历史版本（`/cppwp/n4950/`、`/cppwp/n4861/`、`/cppwp/n4659/` 等），适合查旧标准 |
| **github.com/cplusplus/draft** | 草案的 LaTeX 源码；可以看每次修改的 diff、搜索全文、追溯某段措辞的来历 |
| **wg21.link** | 提案、N 文档、CWG/LWG issue 的短链接 |
| **CWG / LWG issue 列表** | 查某条规则是否有已知缺陷、委员会的意图是什么 |
| **cppreference.com** | 非规范性的参考网站，按特性组织，标明版本差异，常附 DR 列表和编译器支持情况；适合作为入口，但结论应回到标准条文上 |
| **Compiler Explorer（godbolt.org）** | 用多个编译器和版本快速验证；本站代码块的 "godbolt ↗" 按钮直接打开 |
| 编译器状态页 | Clang 的 C++ Status、GCC 的 C++ Standards Support、MSVC 的语言符合性表，用来确认某个特性在哪个版本实现 |

!!! warning "编译器不是权威"
    三大编译器都有 bug、都有尚未实现的特性、都有非符合的默认模式（见 [[intro.compliance]] 中关于扩展的部分）。"Clang 接受了"或"GCC 报错了"只是证据，不是结论。当编译器之间、或编译器与标准之间出现分歧时，正是需要查标准的时候。

## 十一、一套实用的阅读流程

1. **明确问题**：把模糊的"这段代码对吗"拆成具体问题："这个名字查找到哪个声明？""这里发生了什么转换？""这次读取发生在生命周期内吗？"
2. **找到条款**：从 [[intro.structure]] 的地图、本站目录、eel.is 的索引或 cppreference 的"参见"出发，找到最相关的 stable name。
3. **找到段落**：读整个条款的开头（定义与总述），再定位到具体段落。注意列表项之间是"且"还是"或"。
4. **追定义**：段落中的每个斜体术语、每个交叉引用 `([xxx])`，必要时都追过去，不要凭日常经验猜测含义。
5. **看注和例子**：它们往往直接回答你的问题，或者揭示你忽略的推论。
6. **查附录**：Annex C（版本差异）、Annex F（UB 汇总）、Annex G（IFNDR 汇总）是很好的索引。
7. **查 issue**：如果条文看起来矛盾或缺失，搜 CWG/LWG issue 列表，看是否已有讨论。
8. **用编译器验证**：多个编译器、多个版本、开 `-pedantic-errors` 和 sanitizer。分歧本身就是信息。
9. **写下结论和出处**：用 `[stable.name]/N` 的形式，注明版本。

## 十二、本站推荐的阅读顺序

本站按标准章节组织，但阅读时不必按章节顺序。建议的路线：

**第一阶段：元语言**

1. 本页。
2. [[intro.defs]] —— 尤其是行为分类。
3. [[intro.compliance]] —— 符合性、as-if 规则、可观察行为。
4. [[syntax]] —— 语法记法。

**第二阶段：程序是怎样被翻译和组织的**

5. [[lex.phases]] —— 翻译阶段：从源文件到程序。
6. [[basic.def]]、[[basic.def.odr]] —— 声明、定义与 ODR。
7. [[basic.scope]]、[[basic.lookup]] —— 作用域与名字查找。
8. [[basic.link]] —— 链接。

**第三阶段：对象模型**

9. [[basic.memobj]]、[[intro.object]]、[[basic.life]] —— 对象、存储、生命周期。
10. [[basic.types]] —— 类型。
11. [[basic.lval]]、[[conv]] —— 值类别与标准转换。

**第四阶段：执行**

12. [[intro.execution]] —— 求值顺序（sequenced-before）。
13. [[intro.multithread]] —— 内存模型与数据竞争。
14. [[expr.const]] —— 常量求值。

**第五阶段：按需深入**

[[dcl.init]]（初始化）、[[class]]（类）、[[over]]（重载）、[[temp]]（模板）、[[except]]（异常）、[[module]]（模块）、[[basic.contract]]（契约）……以及库部分，先读 [[library]] 的描述方法，再按兴趣进入各章。

!!! summary
    - 用 stable name 而不是章节号定位条款；引用时写 `[stable.name]/段落`，讨论历史时注明版本（N 编号或 C++XX）。
    - 规范性文字是依据；注、例子、脚注、资料性附录只是帮助理解（但常常是最好的旁证）。
    - shall = 要求，should = 建议，may = 允许，can = 可能性。违反对程序的 shall 默认是可诊断的 ill-formed。
    - 斜体词是定义；先查定义再读规则。
    - 标准通过提案（P 编号）、CWG/LWG issue 和编辑性修改变化；DR 通常被编译器回溯应用到旧语言模式。
    - eel.is（当前草案）、timsong cppwp（历史版本）、wg21.link、cplusplus/draft、cppreference、Compiler Explorer 是主要工具；编译器只是证据，不是权威。
