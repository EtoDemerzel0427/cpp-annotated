---
title: C++ 标准化简史：从 Cfront 到 C++26
summary: C with Classes 与 Cfront、ARM、ANSI/ISO 委员会的成立、C++98 与 C++03、TR1、长达十三年的 C++0x 及其原因、2012 年起的三年火车模型、C++11 到 C++26 各版要点、WG21 的组织与一篇提案变成标准文本的流程，以及围绕安全的当前争论
status: draft
order: 5
papers: N2800, N3092, N3290, N1836, P1000R8, N3329, P2739R0, P2687R0, P3081R2, P3390R0, P3466R1, P3543R0, P3586R0, P2795R5, P3471R4, P2900R14, P3596R3
related: topics/how-to-read-the-standard, intro.scope, cpp.predefined, history/stl-and-early-library, history/modern-library, history/concepts, history/move-semantics, history/threads-and-memory-model, history/modules, history/coroutines, history/contracts, history/constexpr
tags: 沿革, 标准化, WG21, 委员会
updated: 2026-10-18
---

这一页是沿革栏目的总览。它按时间顺序讲 C++ 这门语言如何从一个人的研究项目变成一份 ISO 标准，标准的发布节奏为什么在 2012 年前后彻底改变，每一版标准带来了哪些主要变化，以及今天的标准委员会如何运作、在争论什么。

单个特性的来龙去脉，如概念、移动语义、内存模型、STL，各有专门的沿革页，本页只给出它们在整条时间线上的位置并链接过去。关于如何阅读标准文本、如何引用条文，见 [[topics/how-to-read-the-standard]]。

本页的史实主要来自 Stroustrup 的两篇 HOPL 论文（HOPL III：*Evolving a language in and for the real world: C++ 1991–2006*；HOPL IV：*Thriving in a Crowded and Changing World: C++ 2006–2020*）、Herb Sutter 维护的发布计划文档 [[P1000R8]]、Sutter 的会议报告，以及 WG21 文档本身。凡是当事人的回忆，都按原样标明出处。

## 一、C with Classes 与 Cfront（1979–1989）

HOPL III §2.5 给出了早期年表：

| 年份 | 事件 |
|---|---|
| 1979 | Stroustrup 在 Bell Labs 开始 C with Classes 的工作，同年有了第一批使用者 |
| 1983 | 第一个 C++ 实现投入使用 |
| 1984 | 定名 C++ |
| 1985 | Cfront 1.0，第一个商业版本；《The C++ Programming Language》第一版 |
| 1986 | 第一个商业 PC 移植（Cfront 1.1，Glockenspiel） |
| 1987 | 第一个 GNU C++ 版本 |
| 1988 | Oregon Software 和 Zortech 的 C++ 编译器 |
| 1989 | Cfront 2.0；ANSI C++ 委员会（J16）成立 |

Cfront 是一个把 C++ 翻译成 C 的编译器前端，这让 C++ 能借用任何平台上现成的 C 编译器，迅速移植到大量机器上。据 HOPL III §2，从 C with Classes 到 C++ 的转变中加入了虚函数、函数名与运算符重载、引用和 `const`；Cfront 2.0 又加入了多重继承、抽象类和类型安全链接。

HOPL III 还记录了一组用户数估计：从 1979 年 10 月的 1 人到 1991 年 10 月的约 40 万人，平均每 7.5 个月翻一番。Stroustrup 承认用户数很难统计，但说早期他与每一个发布编译器、库和书的人都有联系，因此对这些数字有相当把握。

这一时期没有标准，事实上的语言定义就是 Cfront 的行为加上 Stroustrup 的书。各家编译器陆续出现后，统一定义的需求就变得迫切。

## 二、ARM 与委员会的成立（1989–1991）

1990 年出版的 *The Annotated C++ Reference Manual*（Ellis 与 Stroustrup，常简称 ARM；HOPL III 的年表把它列在 1989 年）给出了当时最完整的语言定义，并附有大量解释设计理由的注释。HOPL III §3 说，ARM 与 1991 年出版的《The C++ Programming Language》第二版一起，在此后多年为 C++ 的实现和编程技术定下了标准。

标准化工作从美国开始。按 HOPL III 的年表：

- 1989 年，ANSI C++ 委员会（J16）在华盛顿特区成立；
- 1990 年，J16 第一次技术会议在新泽西州 Somerset 举行；同年在 Seattle 会议上接受了模板，在 Palo Alto 会议上接受了异常；
- 1991 年，ISO WG21 第一次会议在瑞典 Lund 举行。

HOPL III §3 说明，1991 年标准化工作正式转为 ISO 框架下的国际工作，但实际上没有什么不同，因为 1989 年的组织会议就已经有很多非美国参与者。此后 ANSI 委员会与 ISO 工作组一起开会。今天 isocpp.org 对 WG21 的介绍也说它成立于 1990–91 年。

HOPL III §3.3 记了一个在 Lund 会议后流行起来的故事：瑞典战舰 Vasa 号在建造过程中为了容纳更多雕像和火炮而反复改设计，结果在斯德哥尔摩港内航行不到一半就被一阵风吹翻沉没。委员会成员拿它提醒自己，不要把语言改成一艘装满特性却会倾覆的船。

## 三、C++98：第一份国际标准（1991–1998）

### 主要决定

HOPL III §3.2 列出了这一时期的几个重要表决：

| 年份 | 决定 | 会议地点 |
|---|---|---|
| 1993 | 接受 RTTI | Portland |
| 1993 | 接受命名空间 | Munich |
| 1994 | 以字符类型为模板参数的 `string` | San Diego |
| 1994 | STL | San Diego 介绍，Waterloo 并入草案 |
| 1996 | `export` 模板 | Stockholm |
| 1997 | 对完整标准的最终委员会表决 | Morristown |
| 1998 | ISO C++ 标准批准 | |

STL 的进入是这一时期影响最大的事件，也是最大的意外。Alex Stepanov 在 1994 年 3 月的 San Diego 会议上完整介绍了 STL，同年在 Waterloo 会议上，大幅压缩后的 STL 被并入标准草案。HOPL III §4.1 说，即使是这个缩减版所需的修订，也让标准推迟了一年多。详细经过见 [[history/stl-and-early-library]]。

### 为什么花了这么久

[[P1000R8]] 回顾说，C++98 原本预计在 1994 年左右发布，Stroustrup 当时说过如果到那时还发布不了就是失败；而在 1996 年，社区、实现者乃至委员会内部都有人严重怀疑它到底能不能发布。

HOPL III §3.1 描述了当时的工作方式：委员会成员是志愿者，多数代表愿意支付会费和差旅的公司；在 1997 年最终表决之前，委员会每年开三次为期一周的会议；1997/1998 年的最终投票，ANSI 是 43 比 0，ISO 是 22 比 0。Stroustrup 说他听说这样一致的结果并不常见。

1998 年批准的标准是 ISO/IEC 14882:1998，通称 C++98。

## 四、维护期：C++03 与 TR1（1998–2005）

### 进入维护模式

标准通过后，ISO 流程允许进入最长五年的维护模式。HOPL III §6 列出了委员会这样选择的原因：一些成员工作了十年已经疲惫；社区对新特性的理解远远落后；很多实现者在特性、库和工具上远远落后；没有让人感到紧迫的新想法；许多成员可用于标准化的时间和资金都不多；包括 Stroustrup 在内的许多成员认为 ISO 流程需要一个冷却期。

这一时期委员会主要处理缺陷报告（defect report）。HOPL III 说，从 1998 年到 2006 年，核心语言和库两个工作组各自处理了约 600 份缺陷报告。2003 年，这些修正以 Technical Corrigendum 1 的形式发布，合并后的标准是 ISO/IEC 14882:2003，通称 C++03。它几乎没有新特性，值初始化（value initialization）是少数例外之一。

HOPL III 还提到，2003 年英国国家委员会的成员说服 Wiley 出版了修订后标准的印刷版，此前公众能买到的只有 ISO 约 200 美元的纸本和 INCITS 约 18 美元的 PDF。

### 两份技术报告

维护期的主要产出是两份技术报告（Technical Report, TR）。

性能技术报告起因于日本几家嵌入式工具厂商提出的 Embedded C++ 子集，它去掉了多重继承、模板、异常、RTTI、新式转型和命名空间。据 HOPL III §6.1，委员会经过讨论，坚持不认可方言（即使是子集）的传统，转而写了一份分析各特性性能代价的报告。

库技术报告即 TR1。HOPL III §6.2 说，标准在 1997 年完成时，大家都清楚其中的库只是当时最急需、也已准备好的那一部分，散列表、正则表达式、目录操作、线程等都缺席。2001 年委员会开始编写库技术报告，2004 年以全票通过；它包含多态函数包装器、元组、数学特殊函数、类型特征、正则表达式、智能指针、随机数、散列表等。Matt Austern 编辑的草案见 [[N1745]] 和 [[N1836]]（2005 年），ISO 于 2007 年将其发布为 ISO/IEC TR 19768:2007。除数学特殊函数外，TR1 的内容后来都进入了 C++11（特殊函数到 C++17 才进入）。

TR1 的来历与内容详见 [[history/modern-library]]。它确立了一种做法：先以非规范性的技术报告发布、积累实现经验，再并入标准。2012 年以后的技术规范（TS）沿用了这一思路。

## 五、漫长的 C++0x（2002–2011）

### 开始

据 HOPL III §8，从 1997 年末到 2002 年，委员会刻意避免认真讨论语言扩展。Stroustrup 在 2000 年第一次用 C++0x 这个名字，2001 年起在委员会内外发表关于下一版方向的演讲。2003 年委员会重新开始考虑语言扩展，扩展工作组更名为演化工作组（Evolution Working Group）。

当时的设想是谨慎对待语言改动、强调兼容，把主要精力放在扩充标准库上。HOPL III 说，这个目标很难实现：委员会的资源一向不足，而人们对语言扩展更有热情，也更愿意为此花时间游说。

2005 年春天的 Lillehammer 会议上，在 Stroustrup 的推动下，委员会表决停止接受新提案；2006 年 10 月，又表决在 2007 年末提交草案，使 C++0x 成为 C++09（HOPL III §8.2）。

### 为什么拖到了 2011

HOPL IV §2.3 回顾说，2006 年委员会多数成员对一个特性丰富的 C++0x 抱有很高期望，计划 2007 年冻结特性，合理预期是 C++08 或 C++09。结果 C++0x 成了 C++11，于是有了 0x 其实是十六进制、C++0xB 就是 C++11 的玩笑。

当事人给出的原因大致有三类。

第一是按特性发布的模式。[[P1000R8]] 把 C++98 和 C++11 都归为先选定特性、等特性就绪再发布的模式：发现某个特性还需要时间，就推迟整个标准。它说，在 1994–1996 年和 2007–2009 年，委员会都真心以为再推迟一两次会议就能完成，结果每次都推迟了最多四年。HOPL IV §3.2 从另一个角度描述了同一机制：修订周期越长，错过冻结的特性等待的时间就越长，人们就越倾向于为某个"太重要不能等"的特性推迟标准。

第二是概念。C++0x 的概念设计 2008 年进入工作草案，2008 年 10 月的第一份委员会草案（CD，[[N2800]]）大量使用了它；2009 年 7 月 Frankfurt 会议上，委员会以压倒多数决定把它整体撤出。HOPL IV §6.2 说，此前的工作花去了三年时间并引起了大量争议。详见 [[history/concepts]]。

第三是规模。C++11 最终包含了大量语言和库特性。Stroustrup 在 HOPL IV §2.3 中说，他在 2006 年的 HOPL III 论文里列出 39 项提案，预测前 21 项会进入 C++0x，结果前 25 项中有 24 项进入了 C++11。内存模型与线程库这类全新领域的工作也需要时间（见 [[history/threads-and-memory-model]]）。

撤出概念之后，进度明显加快：2010 年 3 月发布最终委员会草案（FCD，[[N3092]]），2011 年 4 月发布最终国际标准草案（FDIS，[[N3290]]）。2011 年 8 月，Sutter 在博客上宣布 ISO 投票全票通过；标准以 ISO/IEC 14882:2011 发布，即 C++11。

### 一个兼容性的小例子

C++11 是 C++98 之后第一次大的语言修订，也带来了少量不兼容。下面两行代码，没有一个标准能同时接受：

```cpp run std=c++98 error
#include <vector>
int main() {
    auto int n = 0;                     // C++98：OK，auto 是存储类说明符（C++11 起不再允许）
    std::vector<std::vector<int>> v;    // error（C++98）：>> 被当作右移运算符，要写成 > >
    return n + static_cast<int>(v.size());
}
```

在 `-std=c++11` 下，情况正好反过来：`>>` 可以关闭两层模板实参列表（[[N1757]]），而 `auto` 作为存储类说明符被移除（[[N2546]]），腾出来给类型推导用（[[N1984]]）。Clang 对后者的诊断是 `'auto' storage class specifier is not permitted in C++11`。各版标准之间的不兼容修改列在标准的附录 C（[[diff]]）中。

## 六、三年一版的火车模型（2012 年起）

### 从选特性到选时间

C++11 之后，委员会改变了发布方式。HOPL IV §3.2 记录了经过：有几位成员希望缩短周期，召集人 Herb Sutter 建议采用火车模型（train model），即：

> "the train leaves at its scheduled time and anyone not on board will have to wait for the next scheduled departure" （HOPL IV §3.2 转述 Sutter 的建议）

关于间隔多长，有过长时间的讨论。Stroustrup 主张三年，理由是更长的间隔（例如五年）仍会受到"这个特性太重要，不能等"这一理由的冲击。委员会最终同意三年一版。

[[P1000R8]] 把两种发布方式并列：要么控制发布哪些特性，放弃对发布时间的控制；要么控制发布时间，放弃对特性集合的控制，两者不可兼得。2012 年以来采用后者：发现某个已并入草案的特性还不成熟，就把它撤出，等下一班车。P1000 举的例子是 C++11 撤出概念、C++20 撤出契约。对于为什么是三年，P1000 的回答是：

> "We find three years to be a good balance, and two years is the effective minimum in the ISO process." （[[P1000R8]]）

P1000 还引用 Fred Brooks《人月神话》中的 "Take no small slips"：既然三年后反正还有下一版，推迟一个特性的实际效果等于跳过一版，不值得为它推迟整个标准。

### 技术规范：特性分支

大型特性可能需要好几个三年周期。为此，委员会从 2012 年起把这类工作放在技术规范（Technical Specification, TS）里进行（isocpp.org 的标准化状态页），P1000 把它比作版本控制中的特性分支（feature branch）：实现者可以先按 TS 实现，用户可以试用，成熟之后再并入国际标准（IS）这条主干。

这一时期的 TS 包括文件系统、并行、并发、库基础、概念、范围、协程、模块、网络、事务内存、反射等。其中文件系统、并行算法、概念、范围、协程、模块先后以修改后的形式并入了 C++17 或 C++20，网络 TS 和事务内存 TS 没有并入；反射最终没有沿用 TS 的设计，而是以 [[P2996R13]] 进入 C++26。

### tick-tock 的说法

HOPL IV §3.2 记载，Sutter 当时还提议采用 Intel 的 tick-tock 模式，大版本与小版本交替，委员会也同意了；C++14 就是作为补全 C++11 的小版本交付的。但 [[P1000R8]] 后来明确否定了大小版本的说法：火车模型的意思只是发布准备好的东西，委员会无法预先决定哪一版是大版本。P1000 的解释是，小特性的开发周期较短，每版完成的数量相近；大特性的周期超过三年，哪一版恰好赶上几个大特性，那一版就显得大。

P1000 还提到，采用火车模型之后，编译器跟进新标准的速度明显加快，有时在标准发布的同一年就出现了多个完整实现；缺陷报告和对草案的意见也大幅减少。这是委员会对自身流程的评价。

## 七、各版标准要点

下表给出每一版的发布年份和 ISO 编号。C++11 起各版的年份是技术工作完成的年份，ISO 正式出版有时会晚一年，例如 C++23 的 ISO 编号是 14882:2024，2024 年 10 月出版。

| 通称 | ISO 编号 | 版次 | 公开草案 | `__cplusplus` |
|---|---|---|---|---|
| C++98 | ISO/IEC 14882:1998 | 第 1 版 | | `199711L` |
| C++03 | ISO/IEC 14882:2003 | 第 2 版 | | `199711L` |
| C++11 | ISO/IEC 14882:2011 | 第 3 版 | [[N3337]] | `201103L` |
| C++14 | ISO/IEC 14882:2014 | 第 4 版 | [[N4140]] | `201402L` |
| C++17 | ISO/IEC 14882:2017 | 第 5 版 | [[N4659]] | `201703L` |
| C++20 | ISO/IEC 14882:2020 | 第 6 版 | [[N4861]] | `202002L` |
| C++23 | ISO/IEC 14882:2024 | 第 7 版 | [[N4950]] | `202302L` |
| C++26 | （截至写作时本页未核实 ISO 出版信息） | | | 见下文 |

公开草案一栏是与正式标准内容几乎相同、可以免费获取的工作草案，常被当作该版标准引用。`__cplusplus` 的值在 [[cpp.predefined]] 中规定；当前工作草案写的是 `202603L`，并注明以后的修订会换成更大的值。本机 Clang 23 在 `-std=c++2c` 下给出的是 `202400L`：

```cpp run std=c++2c ok
#include <cstdio>
int main() { std::printf("%ld\n", __cplusplus); }   // Clang 23：202400
```

下面各节的表格列出每一版的主要特性。挑选标准参考了 Stroustrup 在 HOPL IV §1.1 中对各版的概括和 Sutter 的会议报告，不求完整；完整的特性清单见各版标准的附录 C 和 cppreference。

### C++11

| 特性 | 提案 | 相关页面 |
|---|---|---|
| 右值引用与移动语义 | [[N2118]] | [[history/move-semantics]]，[[basic.lval]] |
| 内存模型、原子操作 | [[N2429]]，[[N2427]] | [[history/threads-and-memory-model]]，[[intro.multithread]] |
| 线程库 | [[N2497]] | [[thread]] |
| lambda 表达式 | [[N2927]] | [[expr.prim.lambda]] |
| `auto` 类型推导 | [[N1984]] | [[dcl.spec.auto]]，[[topics/type-deduction]] |
| 变参模板 | [[N2242]] | [[temp.variadic]] |
| `constexpr` | [[N2235]] | [[history/constexpr]]，[[dcl.constexpr]] |
| 初始化列表与统一初始化 | [[N2672]] | [[dcl.init.list]] |
| 范围 `for` | [[N2930]] | [[stmt.ranged]] |
| `nullptr` | [[N2431]] | [[lex.nullptr]] |

库方面，TR1 的大部分内容（`shared_ptr`、`unordered_map`、`regex`、`tuple`、`function`、随机数等）连同新的 `unique_ptr` 一起进入了标准。C++11 之后标准库的演进见 [[history/modern-library]]。

### C++14

C++14 是 C++11 之后的第一班火车，主要是补全和放宽。

| 特性 | 提案 | 相关页面 |
|---|---|---|
| 泛型 lambda | [[N3649]] | [[expr.prim.lambda]] |
| 放宽 `constexpr` 函数的限制 | [[N3652]] | [[history/constexpr]] |
| 变量模板 | [[N3651]] | [[temp.pre]] |
| 普通函数的返回类型推导 | [[N3638]] | [[dcl.spec.auto]] |
| 广义 lambda 捕获（初始化捕获） | [[N3648]] | [[expr.prim.lambda.capture]] |
| 二进制字面量、数字分隔符 | [[N3472]]，[[N3781]] | [[lex.icon]] |
| `[[deprecated]]` | [[N3760]] | [[dcl.attr.deprecated]] |
| `std::make_unique` | [[N3656]] | [[unique.ptr]] |

### C++17

[[P1000R8]] 记载，2016 年 Jacksonville 会议是 C++17 的特性截止会议。Stroustrup 在全体会议上请求把概念纳入 C++17，没有获得共识；有人当场问他是否愿意为此把 C++17 推迟一年，他毫不犹豫地拒绝了。P1000 用这件事说明火车模型不会为任何人的特性等车。

| 特性 | 提案 | 相关页面 |
|---|---|---|
| 结构化绑定 | [[P0217R3]] | [[dcl.struct.bind]] |
| `if constexpr` | [[P0292R2]] | [[stmt.if]]，[[history/constexpr]] |
| 类模板实参推导（CTAD） | [[P0091R4]] | [[over.match.class.deduct]] |
| 折叠表达式 | [[N4295]] | [[expr.prim.fold]] |
| 保证的复制消除 | [[P0135R1]] | [[topics/special-members-and-elision]] |
| `inline` 变量 | [[P0386R2]] | [[dcl.inline]] |
| 表达式求值顺序的细化 | [[P0145R3]] | [[topics/order-of-evaluation]] |
| `optional`、`any`、`string_view` | [[P0220R1]] | [[optional]] |
| `variant` | [[P0088R3]] | [[variant]] |
| 文件系统库、并行算法 | [[P0218R1]]，[[P0024R2]] | [[filesystems]]，[[algorithms.parallel]] |

### C++20

HOPL IV §3.2 记载，C++20 在 2019 年 2 月表决为特性完整，最终技术表决在 2020 年 2 月 Prague 会议上完成。按 [[P1000R8]] 的说法，概念的核心部分在 C++20 周期的第一次会议（2017 年 Toronto）就并入了草案，有争议的简写语法在 2018 年 San Diego 会议上通过；契约则在并入后又被撤出，留待以后。

| 特性 | 提案 | 相关页面 |
|---|---|---|
| 概念 | [[P0734R0]] | [[history/concepts]]，[[temp.constr]] |
| 模块 | [[P1103R3]] | [[history/modules]]，[[module]] |
| 协程 | [[P0912R5]] | [[history/coroutines]]，[[dcl.fct.def.coroutine]] |
| 范围库 | [[P0896R4]] | [[ranges]] |
| 三路比较 `<=>` | [[P0515R3]] | [[expr.spaceship]] |
| `consteval`、`constinit`、编译期动态分配 | [[P1073R3]]，[[P1143R2]]，[[P0784R7]] | [[history/constexpr]] |
| 类类型的非类型模板形参 | [[P0732R2]] | [[temp.param]] |
| 文本格式化 `std::format` | [[P0645R10]] | [[format]] |
| 日历与时区 | [[P0355R7]] | [[time]] |
| `std::span`、`std::jthread` | [[P0122R7]]，[[P0660R10]] | [[views.span]]，[[thread.jthread.class]] |

### C++23

C++23 的技术工作在 2023 年 2 月完成，ISO 编号是 14882:2024（INCITS 公告）。

| 特性 | 提案 | 相关页面 |
|---|---|---|
| 显式对象形参（deducing this） | [[P0847R7]] | [[dcl.fct]] |
| `if consteval` | [[P1938R3]] | [[stmt.if]]，[[history/constexpr]] |
| 多维下标运算符 | [[P2128R6]] | [[over.sub]] |
| `std::expected` | [[P0323R12]] | [[expected]] |
| `std::print` | [[P2093R14]] | [[print.fun]] |
| `std::mdspan` | [[P0009R18]] | [[views.multidim]] |
| 标准库模块 `std` 与 `std.compat` | [[P2465R3]] | [[history/modules]]，[[std.modules]] |
| `flat_map`、`views::zip` | [[P0429R9]]，[[P2321R2]] | [[flat.map]]，[[range.zip]] |
| `std::stacktrace` | [[P0881R7]] | [[stacktrace]] |
| `[[assume]]`、`std::unreachable` | [[P1774R8]]，[[P0627R6]] | [[dcl.attr.assume]] |

### C++26

C++26 的第一次会议是 2023 年 6 月的 Varna 会议（Sutter 的会议报告）。2025 年 6 月 Sofia 会议冻结特性，草案随后进行国家成员体意见投票；2025 年 11 月 Kona 会议上，委员会把已通过的平凡重定位（trivial relocatability，[[P2786R13]]）撤出 C++26，留待修正后进入 C++29（[[P3920R0]]）；2026 年 3 月 London Croydon 会议完成全部技术工作，进入 DIS 投票。Sutter 在 Croydon 会议报告中把反射、无需改代码的内存安全改进（错误行为与加固标准库）、契约和 `std::execution` 列为 C++26 最主要的四项特性。

| 特性 | 提案 | 相关页面 |
|---|---|---|
| 静态反射 | [[P2996R13]] | [[expr.reflect]]，[[history/template-metaprogramming]] |
| 契约（前置/后置条件、`contract_assert`） | [[P2900R14]] | [[history/contracts]]，[[basic.contract]] |
| `std::execution` | [[P2300R10]] | [[history/executors-to-execution]]，[[exec]] |
| 读取未初始化变量改为错误行为 | [[P2795R5]] | [[basic.indet]]，[[topics/undefined-behavior]] |
| 标准库加固 | [[P3471R4]] | [[library]] |
| `#embed` | [[P1967R14]] | [[cpp.embed]] |
| 包索引、`_` 占位符 | [[P2662R3]]，[[P2169R4]] | [[expr.prim.pack.index]] |
| 编译期异常、placement new | [[P3068R6]]，[[P2747R2]] | [[history/constexpr]] |
| `std::inplace_vector`、`std::hive` | [[P0843R14]]，[[P0447R28]] | [[inplace.vector]]，[[hive]] |
| `std::simd` | [[P1928R15]] | [[simd]] |

契约在 C++26 周期中一直有争议（经过详见 [[history/contracts]]）。Sutter 记录的两次全体表决是：2025 年 2 月 Hagenberg 会议通过契约提案时为 100 票赞成、14 票反对、12 票弃权；2026 年 3 月批准 C++26 进入 DIS 投票时为 114 票赞成、12 票反对、3 票弃权。他据此认为委员会仍然希望保留契约。

## 八、WG21 的组织

### 正式结构

WG21 的全称是 ISO/IEC JTC 1/SC 22/WG 21。按 HOPL IV §3.2，ISO 只要求三个正式职位：召集人（convener）主持工作组、安排会议、任命研究组，并对上级 ISO 机构负责；项目编辑（project editor）负责把委员会通过的修改落实到工作草案；秘书负责会议纪要。Herb Sutter 自 2002 年起担任召集人，2008–2009 年由 P. J. Plauger 担任（HOPL IV）；[[P1000R8]] 的修订记录显示，到 2026 年 4 月召集人已由 Guy Davidson 接任。

### 三个阶段、四个主工作组

isocpp.org 的委员会页面把一篇提案的处理分为三个阶段：

| 阶段 | 小组 | 职责 |
|---|---|---|
| 1. 调研与孵化 | 各研究组（SG） | 在特定领域内发展提案 |
| 2. 设计与目标 | EWG（语言演化）、LEWG（库演化） | 审查设计，决定以 IS 还是 TS 为目标 |
| 3. 措辞与一致性 | CWG（核心语言措辞）、LWG（库措辞） | 撰写并审查标准措辞，保证与其余条文一致 |

SG17 和 SG18 分别是 EWG 和 LEWG 的孵化组，接收尚未成熟或两个演化组暂时没有余力处理的提案。此外还有方向组（Direction Group，DG），HOPL IV 说它成立于 2017 年，成员由召集人与各工作组主席协商任命，只在成员一致同意时才发表意见，其建议见 [[P0939R4]] 和后续的 [[P2000R5]]。isocpp.org 还列出了管理组（AG）和 ABI 审查组（ARG）。

### 研究组

截至 2026 年 1 月，isocpp.org 列出的研究组如下：

| 编号 | 领域 | 状态 |
|---|---|---|
| SG1 | 并发 | 活跃 |
| SG2 | 模块 | 休眠 |
| SG3 | 文件系统 | 休眠 |
| SG4 | 网络 | 活跃 |
| SG5 | 事务内存 | 休眠 |
| SG6 | 数值 | 活跃 |
| SG7 | 编译期编程（最初专注反射） | 活跃 |
| SG8 | 概念 | 休眠 |
| SG9 | 范围 | 活跃 |
| SG10 | 特性测试 | 活跃 |
| SG11 | 数据库 | 休眠 |
| SG12 | 未定义与未指定行为 | 休眠 |
| SG13 | 人机交互与 I/O | 休眠 |
| SG14 | 游戏开发与低延迟 | 活跃 |
| SG15 | 工具 | 活跃 |
| SG16 | Unicode | 活跃 |
| SG17 | EWG 孵化组 | 活跃 |
| SG18 | LEWG 孵化组 | 活跃 |
| SG19 | 机器学习 | 活跃 |
| SG20 | 教育 | 活跃 |
| SG21 | 契约 | 休眠 |
| SG22 | C/C++ 联络（与 WG14） | 活跃 |
| SG23 | 安全与安保（safety and security） | 活跃 |

研究组的兴衰反映了委员会关注点的变化。HOPL IV 说，研究组随兴趣而设立，完成工作、把提案交给工作组后就宣告结束；SG11 数据库组则因缺乏共识和足够的志愿者而解散。HOPL IV 还指出，SG1 自 2006 年起一直活跃，地位与工作组相近。

### 表决

HOPL IV §3.2 描述了表决方式：工作组和研究组内每位在场者一票；全体会议上每个出席的组织一票，同时统计各国家成员体的立场，两者都同意才算达成共识。共识不等于简单多数，召集人可能把 8 比 2 的结果判为没有共识，特别是当国家成员体负责人或几位资深成员强烈反对时。[[P1000R8]] 给出了通常的门槛：小组内大约 2 比 1，全体会议大约 3 比 1；对错过截止日期的提案，要求更强的共识（小组 3 比 1，全体会议 4 比 1，且赞成票过半）。

## 九、一篇提案如何变成标准文本

一项改动进入标准大致经过以下步骤（细节和术语见 [[topics/how-to-read-the-standard]]）：

1. **写成文档**。提案以 WG21 文档的形式提交。2015 年前后起，提案的编号形如 `P2996R13`：`P` 后面是提案号，`R` 后面是修订次数；更早的提案用 `N` 编号，每次修订换一个新号；今天的工作草案、会议纪要等仍用 `N` 编号。本站的 `[[P2996R13]]` 这类链接都通过 wg21.link 指向原文。
2. **研究组与演化组**。较大的提案先在相关研究组讨论，然后交给 EWG 或 LEWG 审查设计。HOPL IV 说，一个重要提案通常要经过好几次会议、几年时间和多次修订。
3. **措辞审查**。设计通过后，CWG 或 LWG 逐句审查措辞，保证新条文与标准其他部分一致。很多设计问题是在这一阶段才暴露的。
4. **全体会议表决**。通过措辞审查的提案在全体会议上表决，通过后由项目编辑并入工作草案。工作草案的源文件公开在 GitHub 的 cplusplus/draft 仓库中，每次会议后发布新的草案文档，如 [[N5032]]。
5. **投票与发布**。按 [[P1000R8]] 给出的 C++29 计划，特性冻结后发布委员会草案（CD）供各国家成员体投票并提出意见，委员会逐条处理意见之后完成技术工作，发出最终国际标准草案（DIS）投票，再由 ISO 出版。

标准发布之后的修改走缺陷报告途径：核心语言问题记为 CWG issue（如 [[CWG2551]]），库问题记为 LWG issue。部分修正以缺陷报告（DR）的形式通过，意味着它被视为对已发布标准的修正，编译器通常在所有语言模式下应用。

## 十、当前的争论：安全

2022 年以来，委员会讨论最多的议题是安全，特别是内存安全。这一节只陈述各方在文档中给出的立场和委员会的表决记录。

### 起因

2022 年 11 月，美国国家安全局（NSA）发布关于软件内存安全的指南，建议机构在可能时从 C/C++ 这类几乎不提供内在内存保护的语言转向内存安全语言。Stroustrup 在 [[P2739R0]] *A call to action: Think seriously about "safety"; then do something sensible about it* 中回应：这份指南把 C 和 C++ 归为一类，忽略了三十多年的进步；安全不止内存安全一种；他主张通过编程风格、支持库和静态分析的组合，在需要的地方获得有保证的类型与资源安全，并支持渐进采用。

### 几种主要路线

- **Profiles**。Stroustrup 与 Dos Reis 的 [[P2687R0]] 和 Stroustrup 的 [[P3274R0]] 提出 profile 框架：用编译选项或代码注解请求某一组规则（如类型安全、边界安全）被强制执行。Sutter 的 [[P3081R2]] *Core safety profiles* 给出了一组具体的 profile，包括拒绝某些不安全的构造、在某些操作上隐式插入运行期检查等。2024 年 11 月 Wrocław 会议上，SG23 以 23:1:0 把 P3081 转交 EWG，EWG 以 44:4:3 同意为 C++26 推进它（Sutter 的会议报告）。
- **Safe C++**。Sean Baxter 与 Christian Mazakas 的 [[P3390R0]] 提出一个 C++ 的超集：引入安全上下文，在其中禁止产生未定义行为；用借用检查（borrow checking）在编译期发现释放后使用和迭代器失效；不能验证的操作必须显式标 `unsafe`；另配一个新的 `std2` 标准库。提案明确把目标保证定位为与 Rust 类似。在 Wrocław 会议上，SG23 对 profiles 与 Safe C++ 的优先次序投票，结果是 19:11:6:9（profiles : 两者 : 中立 : Safe C++）。
- **设计原则**。Sutter 的 [[P3466R1]] 提出未来 C++ 演化应遵守的若干原则，包括避免需要大量注解的设计。EWG 以 29:22:2 同意把这些原则写成常设文档。

### 对 profiles 的技术批评

[[P3543R0]]（Gill、Jabot、Lakos、Berne、Doumler）认为 P3081 的若干部分还不够成熟。它把 P3081 的内容分成几类：拒绝不安全构造的部分争议最小，但适用范围、豁免机制和规则粒度都需要更明确的规定；隐式插入运行期检查的部分会改变现有正确程序的语义，并且应与契约的设计协调，而不是另起炉灶。

Jabot 的 [[P3586R0]] 进一步认为，profiles 试图用同一个工具解决三类性质不同的问题（运行期检查、危险构造、基于控制流分析的内存安全），它们应分开考虑。他还指出，用属性来启用 profile 有问题，因为旧的工具链会忽略不认识的属性，而安全特性不应该是可忽略的。

### 结果

2025 年 2 月的 Hagenberg 会议没有把 profiles 纳入 C++26；EWG 鼓励就系统性处理未定义行为撰写一份白皮书（Sutter 的会议报告）。C++26 实际采纳的安全相关改动是：把读取未初始化局部变量从 UB 改为错误行为（[[P2795R5]]）、标准库加固（[[P3471R4]]，以契约机制为基础），以及契约本身（[[P2900R14]]）。Sutter 在 Croydon 会议报告中说，加固后的标准库已在 Google 部署，平均性能开销约 0.3%，修复了一千多个缺陷。

C++29 周期里，这条线仍在继续。按 Sutter 的会议报告：2026 年 3 月，SG23 在处理 Stroustrup 的类型安全 profile（[[P3984R0]]），它基于 Dos Reis 的通用框架（[[P3589R3]]）；2026 年 6 月 Brno 会议把列出全部 UB 与 IFNDR 情形的附录（[[P3596R3]]）并入了 C++29 草案，EWG 同意逐行审查系统处理 UB 的框架 [[P3100R8]]，SG23 决定编写一份 profiles 规范，它可能并入 C++29，也可能以白皮书形式发布。

## 时间线

| 年份 | 事件 | 出处 |
|---|---|---|
| 1979 | C with Classes 开始 | HOPL III §2.5 |
| 1984–1985 | 定名 C++；Cfront 1.0；TC++PL 第一版 | HOPL III §2.5 |
| 1989 | Cfront 2.0；ANSI J16 成立 | HOPL III §2.5 |
| 1990 | ARM 出版；J16 第一次技术会议；接受模板与异常 | HOPL III §2.5 |
| 1991 | WG21 第一次会议（Lund）；Cfront 3.0 支持模板 | HOPL III §2.5 |
| 1993 | 接受 RTTI、命名空间 | HOPL III §3.2 |
| 1994 | STL 并入草案（Waterloo） | HOPL III §4.1 |
| 1997 | 最终委员会表决（Morristown） | HOPL III §3.2 |
| 1998 | C++98（ISO/IEC 14882:1998） | HOPL III §3.2 |
| 2003 | C++03（TC1）；C++0x 工作开始 | HOPL III §3.2、§6 |
| 2004–2005 | 库技术报告通过；TR1 草案 [[N1836]] | HOPL III §6.2 |
| 2005 | Lillehammer 会议停止接受新提案 | HOPL III §8.2 |
| 2007 | TR1 以 ISO/IEC TR 19768:2007 发布 | cppreference |
| 2008 | C++0x 第一份委员会草案 [[N2800]] | [[N2800]] |
| 2009 | 概念撤出 C++0x（Frankfurt） | HOPL IV §6.2，[[history/concepts]] |
| 2011 | FDIS [[N3290]]；8 月 ISO 全票批准 C++11 | Sutter 博客，2011-08-12 |
| 2012 | 改为三年火车模型，大型特性放入 TS | [[P1000R8]]，HOPL IV §3.2 |
| 2014 | C++14 | HOPL IV §1.1 |
| 2016 | C++17 特性截止（Jacksonville） | [[P1000R8]] |
| 2017 | C++17；概念并入 C++20 草案（Toronto） | [[P1000R8]] |
| 2020 | C++20 技术工作完成（Prague） | HOPL IV §3.2 |
| 2022 | NSA 内存安全指南；[[P2739R0]] | [[P2739R0]] |
| 2023 | C++23 技术工作完成；C++26 第一次会议（Varna） | Sutter 会议报告 |
| 2024 | C++23 以 ISO/IEC 14882:2024 出版；profiles 与 Safe C++ 提案 | INCITS；Sutter 会议报告 |
| 2025 | 契约、加固（Hagenberg）；反射、特性冻结（Sofia）；撤出平凡重定位（Kona） | Sutter 会议报告；[[P3920R0]] |
| 2026 | C++26 技术工作完成（London Croydon）；C++29 第一次会议（Brno） | Sutter 会议报告；[[P1000R8]] |

## 现状与未来

截至 2026 年 10 月，C++26 已完成技术工作并进入 ISO 的批准与出版流程，委员会的工作重心是 C++29。按 [[P1000R8]] 的计划，2026 年 6 月 Brno 会议是 C++29 的第一次会议；2026 年 11 月 Búzios 会议到 2027 年中，优先处理影响面大的语言特性和 TS 合并；2028 年初 Kona 会议是送交措辞审查的最后期限；2029 年初完成技术工作并启动 DIS 投票。

可以预见的几条主线：

- 安全：UB 附录之后的逐条审查、profiles 规范、[[P3100R8]] 的 UB 处理框架、Sutter 在 [[P3436R1]] 中提出的默认消除与安全相关 UB 的策略（截至写作时仍是提案）；
- 契约的后续工作，例如 Brno 会议并入 C++29 草案的虚函数契约（[[P3097R3]]）；
- 反射的后续扩展，以及从 C++26 撤出的平凡重定位的重新设计；
- `std::execution` 之上的异步库与网络。

回看这四十多年，C++ 标准化的组织方式变了两次：1989–1991 年从一个人的设计变成委员会的共识过程；2012 年从按特性发布变成按时间发布。第二次变化的效果，委员会在 [[P1000R8]] 中给出了自己的评价：编译器实现得更快，草案质量更稳定。至于三年一版是否让语言增长得过快、委员会能否在安全议题上形成一致方向，各方的文档仍在持续发表，本页只能记录到写作时为止的状态。

## 参考资料

- Bjarne Stroustrup. *Evolving a language in and for the real world: C++ 1991–2006*. HOPL III, 2007. §2.5、§3、§4.1、§6、§8。
- Bjarne Stroustrup. *Thriving in a Crowded and Changing World: C++ 2006–2020*. HOPL IV, Proc. ACM Program. Lang. 4 (HOPL), 2020. §1、§2.3、§3.2、§6.2。
- Margaret A. Ellis, Bjarne Stroustrup. *The Annotated C++ Reference Manual*. Addison-Wesley, 1990.
- Herb Sutter, Guy Davidson. *(Proposed) C++ IS schedule*. [[P1000R8]], 2026.
- isocpp.org：*The Committee*（委员会结构与研究组列表，截至 2026 年 1 月）；*Current Status*。
- Matt Austern. *Draft Technical Report on C++ Library Extensions*. [[N1836]], 2005.
- Pete Becker. C++0x 委员会草案 [[N2800]]（2008）、最终委员会草案 [[N3092]]（2010）、FDIS [[N3290]]（2011）。
- Herb Sutter. *We have an international standard: C++0x is unanimously approved*. Sutter's Mill, 2011-08-12.
- Herb Sutter 的会议报告（Sutter's Mill）：Varna（2023-06）、Tokyo（2024-03）、St. Louis（2024-07）、Wrocław（2024-11）、Hagenberg（2025-02）、Sofia（2025-06）、Kona（2025-11）、London Croydon（2026-03-29）、Brno（2026-06-13）。
- Louis Dionne. *Wording for NB comment resolution on trivial relocation*. [[P3920R0]], 2025.
- Andreas Fertig. *Why is C++23 called 23?* 2024；INCITS 关于 INCITS/ISO/IEC 14882:2024 的公告。
- Bjarne Stroustrup. *A call to action: Think seriously about "safety"; then do something sensible about it*. [[P2739R0]], 2022.
- Bjarne Stroustrup, Gabriel Dos Reis. *Design Alternatives for Type-and-Resource Safe C++*. [[P2687R0]], 2022；Bjarne Stroustrup. *A framework for Profiles development*. [[P3274R0]], 2024.
- Herb Sutter. *Core safety profiles for C++26*. [[P3081R2]], 2025；*(Re)affirm design principles for future C++ evolution*. [[P3466R1]], 2024.
- Sean Baxter, Christian Mazakas. *Safe C++*. [[P3390R0]], 2024.
- Mungo Gill, Corentin Jabot, John Lakos, Joshua Berne, Timur Doumler. *Response to Core Safety Profiles (P3081)*. [[P3543R0]], 2024；Corentin Jabot. *The Plethora of Problems With Profiles*. [[P3586R0]], 2025.
- Joshua Berne, Timur Doumler, Jens Maurer, Shafik Yaghmour. *Undefined Behavior and IFNDR Annexes*. [[P3596R3]], 2026.
