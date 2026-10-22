---
title: C++ 标准化简史：从 Cfront 到 C++26
summary: C++ 怎样从一个翻译成 C 的编译器变成 ISO 标准，C++0x 为什么拖了十几年，三年一版的发布方式给今天的语言留下了什么，以及一篇提案怎样变成标准条文。
status: draft
order: 5
papers: P1000R8, N1836, N2800, P2739R0, P2687R0, P3081R2, P3390R0, P3543R0, P3586R0, P2795R5, P3471R4, P2900R14, P3596R3
related: topics/how-to-read-the-standard, intro.scope, cpp.predefined, history/stl-and-early-library, history/modern-library, history/concepts, history/move-semantics, history/threads-and-memory-model, history/modules, history/coroutines, history/contracts, history/constexpr
tags: 沿革, 标准化, WG21, 委员会
updated: 2026-10-19
video: bilibili=BV12ynC69EWS, youtube=18YW4QLPOgg
---

!!! tldr
    - C++ 最早靠 Cfront 翻译成 C 来实现。与 C 兼容是它最早、也最持久的设计约束，名字修饰和 `extern "C"` 都是这一约束的产物。
    - C++98 和 C++11 都是先选定特性、等特性就绪再发布，两次都比计划晚了好几年。C++0x 在撤出概念之后才得以完成。
    - 2012 年起改为每三年按时发布一版，没准备好的特性等下一班车。所以很多特性是分几版逐步补全的，代码里要靠 `-std=` 和特性测试宏区分。
    - 一篇提案先由演化组审查设计，再由措辞组审查条文，最后由全体会议表决。标准发布后的修正记为 CWG/LWG issue，其中的缺陷报告（DR）通常追溯适用于旧的语言模式。
    - 近年争论的中心是安全。C++26 采纳了错误行为、标准库加固和契约，profiles 还在 C++29 周期中讨论。

单个特性的来龙去脉（概念、移动语义、内存模型、STL 等）各有专门的沿革页，本页只讲它们在整条时间线上的位置。怎样阅读和引用标准文本见 [[topics/how-to-read-the-standard]]。

本页的史实主要来自 Stroustrup 的两篇 HOPL 论文（下文记为 HOPL III、HOPL IV，全名见文末）、委员会的发布计划文档 [[P1000R8]]、Herb Sutter 的会议报告，以及 WG21 文档本身。

## 没有标准的十年（1979–1989）

Stroustrup 1979 年在 Bell Labs 开始设计 C with Classes，1984 年定名 C++，1985 年发布第一个商业版本 Cfront 1.0（HOPL III §2.5）。Cfront 不直接生成机器码，而是把 C++ 翻译成 C，再交给目标平台现成的 C 编译器。这让 C++ 能迅速移植到几乎所有有 C 编译器的机器上。

这种实现方式也决定了 C++ 的很多性质。翻译出来的 C 代码要用 C 的链接器链接，而 C 的链接器只按名字匹配符号。Cfront 2.0（1989）加入类型安全链接时，采用的办法是把形参类型编码进符号名，这样不必修改现有的链接器就能区分重载函数（*The Design and Evolution of C++* 讨论类型安全链接的一节）。这就是今天的**名字修饰**（name mangling），见 [[toolchain/name-mangling]]。要和 C 代码互相调用时，则用 `extern "C"` 关掉修饰。

<div class="compare" markdown="1">

```cpp title="C++ 源码"
void f(int);
void f(double);
extern "C" void g(int);
```

```text title="Linux（Itanium ABI）上的符号名"
_Z1fi
_Z1fd
g
```

</div>

这一时期没有标准。事实上的语言定义就是 Cfront 的行为加上 Stroustrup 的书。1987 年起 GNU、Zortech 等编译器陆续出现，各家的行为需要一份共同的定义。

## ARM 与委员会（1989–1991）

1990 年出版的 *The Annotated C++ Reference Manual*（Ellis 与 Stroustrup，简称 ARM）是当时最完整的语言定义，附有大量解释设计理由的注释。它成了标准化的起点（HOPL III §3）。

标准化先在美国开始：ANSI 的 C++ 委员会（J16）1989 年成立，1990 年接受了模板和异常。1991 年工作转为 ISO 框架下的国际工作组 WG21，此后两个组织一起开会（HOPL III §3）。今天的标准仍由 WG21 维护，全称 ISO/IEC JTC 1/SC 22/WG 21。

委员会成员当时流传一个故事：瑞典战舰 Vasa 号在建造中为了装下更多火炮和雕像反复加层，下水后不久就翻沉了（HOPL III §3.3）。他们用它提醒自己，语言不能为了容纳更多特性而失去平衡。这种担心在此后三十年的每一版标准里都会出现。

## C++98：先选特性，再等特性就绪

这一时期委员会接受的大特性有：模板和异常（1990）、RTTI 和命名空间（1993）、STL（1994）、`export` 模板（1996）（HOPL III §3.2）。它们的命运差别很大。

**STL** 是最大的意外。它在 1994 年才被提出，原计划那时标准已接近完成。委员会删掉了约三分之二的内容才接纳它，即使如此，把它写成标准条文也让标准推迟了一年多（HOPL III §4.1.2）。经过见 [[history/stl-and-early-library]]。

**`export` 模板**是一条死路。它允许把模板定义放在 `.cpp` 文件里，像普通函数那样分离编译。但实现难度极大，只有很少的编译器真正实现过。C++11 删除了这项功能，只保留关键字；C++20 又把这个关键字用于模块。附录 C 给出的理由是，对 C++03 中 `export` 的含义没有实现共识（[[diff.cpp03.temp]]）。模板定义今天仍然要放在头文件里，或者等模块来解决（[[history/modules]]）。

委员会也拒绝了另一个方向。1990 年代中期，几家日本嵌入式工具厂商提出了 Embedded C++，一个去掉多重继承、模板、异常、RTTI、命名空间的子集。委员会坚持不认可方言（包括子集）的传统，转而写了一份分析各特性性能代价的技术报告（HOPL III §6.1）。不分裂语言、让不用的特性不产生开销，这条原则此后一直沿用。

C++98 原本预计在 1994 年左右完成；到 1996 年，社区乃至委员会内部都有人怀疑它能否发布（[[P1000R8]]）。最终标准在 1998 年批准，即 ISO/IEC 14882:1998。

## C++03 与 TR1：维护期

标准发布后，委员会主动进入维护模式。HOPL III §6 列出的原因包括：成员已经工作了近十年；社区对新特性的理解和实现者的进度都远远落后；也没有让人感到紧迫的新想法。

这段时间主要处理**缺陷报告**（defect report），即对已发布标准中错误和矛盾的修正。1998 到 2006 年，核心语言和库两个工作组各处理了约 600 份（HOPL III §6）。2003 年这些修正汇总成 C++03，它几乎没有新特性，值初始化（[[dcl.init]]）是少数例外之一。

维护期的另一项产出是库技术报告 **TR1**（草案 [[N1836]]），它包含智能指针、`function`、`tuple`、类型特征、正则表达式、随机数、散列表等。**技术报告**不是标准，没有强制力，作用是先让实现者实现、用户试用。TR1 的内容后来几乎全部进入了 C++11（[[history/modern-library]]）。这种先发布、积累经验、再并入的做法，后来演变成了技术规范（TS）。

## C++0x 为什么拖到 2011

2003 年委员会重新开始考虑语言扩展，下一版标准暂称 C++0x。2006 年时的计划是 2007 年冻结特性，合理的预期是 C++08 或 C++09（HOPL IV §2.3）。结果它成了 C++11，于是有了 0x 是十六进制的玩笑。

当事人给出的原因主要有三个。

1. **按特性发布**。[[P1000R8]] 把 C++98 和 C++11 都归为先选定特性、等它们就绪再发布的模式。发现某个特性还需要时间，整个标准就跟着推迟；1994–1996 年和 2007–2009 年，委员会每次都以为再推迟一两次会议就够了，结果每次都推迟了好几年。
2. **概念**。C++0x 的概念设计 2008 年进入工作草案，第一份委员会草案 [[N2800]] 大量使用了它。2009 年委员会决定把它整体撤出（HOPL IV §6.2），概念直到 C++20 才以另一种设计回来，见 [[history/concepts]]。
3. **规模**。内存模型、线程、右值引用、lambda、变参模板都是全新的工作（[[history/threads-and-memory-model]]、[[history/move-semantics]]）。Stroustrup 在 2006 年预测他列出的提案中前 21 项会进入 C++0x，结果前 25 项中有 24 项进入了 C++11（HOPL IV §2.3）。

撤出概念之后进度明显加快，2011 年标准获得批准。

C++11 也是 C++98 之后第一次大的语言修订，少量旧代码因此失效。下面两段代码都只在一个标准下合法：

<div class="compare" markdown="1">

```cpp run std=c++98 title="C++98 写法" ok
#include <vector>
int main() {
  auto int n = 0;  // auto 是存储类说明符
  std::vector<std::vector<int> > v;
  return n + (int)v.size();  // > > 要分开
}
```

```cpp run std=c++11 title="C++11 写法" ok
#include <vector>
int main() {
  auto n = 0;      // auto 表示类型推导
  std::vector<std::vector<int>> v;
  return n + (int)v.size();  // >> 可以连写
}
```

</div>

左边在 C++11 下非良构，因为 `auto` 改作类型推导（[[diff.cpp03.dcl.dcl]]）。本机 Clang 23 只给出一条警告 `'auto' storage class specifier is not permitted in C++11`，这仍然符合标准，因为一条诊断就够了（见 [[intro.compliance]]）。右边在 C++98 下非良构，`>>` 会被当作右移运算符。附录 C 的 [[diff.cpp03.temp]] 还给出了一个反向的例子：`X< Y< 1 >> 2 > >` 在 C++98 中是 `Y<(1>>2)>`，在 C++11 中则变成了错误。

## 火车模型：按时间发布（2012 年起）

C++11 之后，召集人 Herb Sutter 提议改用**火车模型**（train model）：火车按时刻表发车，没赶上的人等下一班（HOPL IV §3.2）。[[P1000R8]] 把两种发布方式并列：要么控制发布哪些特性、放弃对时间的控制，要么控制发布时间、放弃对特性集合的控制，两者不可兼得。委员会选择了后者，周期定为三年：

!!! std "P1000R8"
    "We find three years to be a good balance, and two years is the effective minimum in the ISO process."

Stroustrup 支持三年而不是五年，理由是更长的间隔仍然会招来这个特性太重要、不能等的推迟要求（HOPL IV §3.2）。火车模型下，推迟一个特性的代价只是让它晚三年，不值得为它推迟整个标准。C++20 周期里，已经并入草案的契约被撤出（[[history/contracts]]）；C++26 周期里，平凡重定位也在最后阶段被撤出，留待 C++29（[[P3920R0]]）。

### 技术规范：特性分支

需要好几个周期才能做成的大特性，放在**技术规范**（Technical Specification，TS）里开发。[[P1000R8]] 把它比作版本控制中的特性分支：实现者可以先实现，用户可以试用，成熟之后再并入国际标准这条主干。实现通常把 TS 的组件放在 `std::experimental` 命名空间里。

文件系统、并行算法、概念、范围、协程、模块都走过 TS，再以修改后的形式进入 C++17 或 C++20。网络 TS 和事务内存 TS 没有并入。反射没有沿用 TS 的设计，而是以 [[P2996R13]] 直接进入了 C++26。近年的提案更常直接以国际标准为目标。

### 对写代码的影响：特性分期到达

火车模型的一个直接后果是，一个特性往往先以最小可用的形式上车，再在后面几版逐步放宽。`constexpr` 函数是最典型的例子（[[history/constexpr]]）：C++11 只允许一条 `return` 语句，C++14 允许循环和局部变量，C++20 允许动态分配，C++26 又允许了更多操作。`return x;` 何时自动移动的规则也改了四次（[[history/move-semantics]]）。

因此，判断一段代码是否合法，不仅要问哪个标准，还要问哪一版。需要兼容多个版本的代码用**特性测试宏**来区分，它们列在 [[cpp.predefined]] 和 [[version.syn]] 中，值是该特性被并入草案的年月：

```cpp run ok
#include <cstdio>
int main() {
#if __cpp_constexpr >= 202306L
    std::puts("C++26 级别的 constexpr");
#elif __cpp_constexpr >= 201304L
    std::puts("至少 C++14 级别的 constexpr");
#else
    std::puts("C++11 级别的 constexpr");
#endif
}
// Clang 23：-std=c++11 输出第三行，c++14 到 c++23 输出第二行，c++2c 输出第一行
```

另一个后果和缺陷报告有关。标准发布后发现的问题按缺陷报告（DR）处理时，意味着它被视为对已发布标准的修正，编译器通常在所有语言模式下都应用。所以 `-std=c++17` 下的编译器行为，可能与 2017 年发布的文本不一致，而与修正后的规则一致。

## 各版标准一览

C++11 起，各版名称里的年份是技术工作完成的年份，ISO 正式出版有时晚一年：C++23 的编号是 14882:2024。公开草案是与正式标准内容几乎相同、可以免费获取的工作草案，常被当作该版标准引用。

| 通称 | ISO 编号 | 公开草案 | `__cplusplus` | 主要内容 |
|---|---|---|---|---|
| C++98 | 14882:1998 | | `199711L` | 模板、异常、命名空间、RTTI、STL、iostream |
| C++03 | 14882:2003 | | `199711L` | 缺陷修正；值初始化 |
| C++11 | 14882:2011 | [[N3337]] | `201103L` | 移动语义、内存模型与线程、lambda、`auto`、变参模板、`constexpr`、列表初始化、范围 `for`；TR1 并入 |
| C++14 | 14882:2014 | [[N4140]] | `201402L` | 泛型 lambda、放宽 `constexpr`、变量模板、返回类型推导、`make_unique` |
| C++17 | 14882:2017 | [[N4659]] | `201703L` | 结构化绑定、`if constexpr`、CTAD、折叠表达式、保证的复制消除、`optional`/`variant`/`string_view`、文件系统 |
| C++20 | 14882:2020 | [[N4861]] | `202002L` | 概念、模块、协程、范围库、`<=>`、`consteval`、`std::format` |
| C++23 | 14882:2024 | [[N4950]] | `202302L` | 显式对象形参、`if consteval`、`expected`、`print`、`mdspan`、`import std;` |
| C++26 | （出版中） | | 草案为 `202603L` | 静态反射、契约、`std::execution`、错误行为、标准库加固、`#embed` |

各特性的规则见对应条款页：[[dcl.struct.bind]]、[[stmt.if]]、[[over.match.class.deduct]]、[[temp.constr]]、[[module]]、[[dcl.fct.def.coroutine]]、[[expr.spaceship]]、[[expr.reflect]]、[[basic.contract]]、[[basic.indet]]、[[cpp.embed]] 等；完整的不兼容变化列表在附录 C（[[diff]]）。

`__cplusplus` 的值由 [[cpp.predefined]] 规定，当前工作草案写的是 `202603L`，并注明以后的修订会换成更大的值。编译器在新标准正式发布之前通常给一个过渡值：

```cpp run ok
#include <cstdio>
int main() { std::printf("%ld\n", __cplusplus); }
// Clang 23 -std=c++2c：202400
```

C++26 的技术工作在 2026 年 3 月完成，进入 ISO 的最终投票与出版流程。Sutter 在当次会议报告中把反射、无需改代码的内存安全改进（错误行为与标准库加固）、契约和 `std::execution` 列为它最主要的四项特性。

## 一篇提案怎样变成标准条文

本站经常引用 `P2996R13`、`N4950`、`CWG2551` 这样的编号，它们都是 WG21 流程的产物。

提案以 WG21 文档的形式提交。2015 年前后起，提案编号形如 `P2996R13`：`P` 后面是提案号，`R` 后面是修订次数。更早的提案用 `N` 编号，每次修订换一个新号；工作草案和会议纪要至今仍用 `N` 编号，如 [[N5032]]。本站的这类链接都经 wg21.link 指向原文。

isocpp.org 把一篇提案的处理分为三个阶段：

| 阶段 | 小组 | 做什么 |
|---|---|---|
| 调研 | 各研究组（SG），如 SG1 并发、SG7 反射、SG23 安全 | 在专门领域内发展提案 |
| 设计 | EWG（语言演化）、LEWG（库演化） | 审查设计，决定进入国际标准还是 TS |
| 措辞 | CWG（核心语言）、LWG（库） | 逐句审查条文，保证与标准其余部分一致 |

通过措辞审查的提案在全体会议上表决，通过后由项目编辑并入工作草案。工作草案的源文件公开在 GitHub 的 cplusplus/draft 仓库。一个重要提案通常要经过好几次会议、几年时间和多次修订（HOPL IV §3.2）；很多设计问题直到措辞阶段才暴露出来。委员会以共识而不是简单多数做决定，通常的门槛在小组内约 2 比 1、全体会议约 3 比 1（[[P1000R8]]）。

每个三年周期的末尾，特性冻结后的草案先作为委员会草案（CD）交给各国家成员体投票、提意见；委员会处理完意见后，发出国际标准草案（DIS）投票，再由 ISO 出版（[[P1000R8]]）。

标准发布之后的问题记为 issue：核心语言的叫 CWG issue（如 [[CWG2551]]），库的叫 LWG issue。其中按缺陷报告处理的修正，就是上一节说的追溯适用的 DR，本站用 {{dr}} 标记。

<details class="fine" markdown="1">
<summary>其余细节：委员会的其他小组</summary>

ISO 只要求三个正式职位：召集人、项目编辑和秘书（HOPL IV §3.2）。Herb Sutter 自 2002 年起长期担任召集人；[[P1000R8]] 的修订记录显示，到 2026 年召集人已由 Guy Davidson 接任。

SG17 和 SG18 分别是 EWG 和 LEWG 的孵化组。方向组（Direction Group）2017 年成立，只在成员一致同意时发表意见，其建议见 [[P2000R5]]。研究组随兴趣设立，完成工作后就进入休眠；截至 2026 年初，SG2 模块、SG8 概念、SG21 契约等已经休眠，SG1 并发、SG7 编译期编程、SG23 安全仍然活跃（isocpp.org 委员会页面）。

</details>

## 安全之争（2022 年起）

2022 年 11 月，美国国家安全局（NSA）发布软件内存安全指南，建议在可能时从 C/C++ 转向内存安全语言。Stroustrup 在 [[P2739R0]] 中回应：这份指南把 C 和 C++ 归为一类，忽略了几十年的进步；安全不只有内存安全一种；他主张用编程风格、支持库和静态分析的组合，在需要的地方获得有保证的类型与资源安全，并允许渐进采用。

此后委员会里出现了几条路线：

- **Profiles**。[[P2687R0]] 和 Sutter 的 [[P3081R2]] 提出用编译选项或注解请求一组规则（如类型安全、边界安全）被强制执行：拒绝某些不安全的构造，或在某些操作上隐式插入运行期检查。
- **Safe C++**。[[P3390R0]] 提出 C++ 的一个超集：安全上下文里禁止未定义行为，用借用检查在编译期发现释放后使用和迭代器失效，不能验证的操作必须标 `unsafe`，另配一个新的标准库。目标是与 Rust 类似的保证。
- **不改代码就生效的改进**。把一部分未定义行为改为定义好的行为或可检查的契约违反。

对 profiles 的主要技术批评来自 [[P3543R0]] 和 [[P3586R0]]：隐式插入运行期检查会改变现有正确程序的语义，应当与契约协调；用属性启用 profile 有问题，因为旧工具链会忽略不认识的属性，而安全特性不应该是可忽略的。委员会的优先次序投票偏向 profiles，但它没有进入 C++26（Sutter 的会议报告）。

C++26 实际采纳的是第三条路线：

- 读取未初始化的局部变量从未定义行为改为**错误行为**（erroneous behavior），读到的是实现选定的一个错误值，实现可以诊断（[[P2795R5]]，见 [[basic.indet]]）；
- 标准库**加固**：越界下标等一部分前置条件违反变成契约违反，可以让程序终止而不是继续读写越界内存（[[P3471R4]]）。Sutter 报告说它已在 Google 部署，平均性能开销约 0.3%；
- 契约本身（[[P2900R14]]，见 [[history/contracts]]）。

这条线在 C++29 周期里继续：列出全部未定义行为和 IFNDR 情形的附录（[[P3596R3]]）已经并入 C++29 草案，profiles 的规范仍在编写，可能并入标准，也可能以白皮书形式发布（Sutter 的会议报告，2026 年 6 月）。

## 时间线

| 年份 | 事件 |
|---|---|
| 1979 | C with Classes 开始 |
| 1985 | Cfront 1.0；《The C++ Programming Language》第一版 |
| 1989–1991 | Cfront 2.0；ANSI J16 成立；ARM 出版；ISO WG21 成立 |
| 1994 | STL 并入草案 |
| 1998 | C++98 |
| 2003 | C++03；C++0x 工作开始 |
| 2007 | TR1 发布 |
| 2009 | 概念撤出 C++0x |
| 2011 | C++11 |
| 2012 | 改为三年火车模型，大特性放进 TS |
| 2014、2017、2020 | C++14、C++17、C++20 |
| 2023 | C++23 技术工作完成（2024 年出版） |
| 2026 | C++26 技术工作完成；C++29 周期开始 |

按 [[P1000R8]] 的计划，C++29 的技术工作在 2029 年初完成。可以预见的主线有：安全（UB 附录之后的逐条审查、profiles）、契约与反射的后续扩展、从 C++26 撤出的平凡重定位的重新设计，以及建立在 `std::execution` 之上的异步与网络库。

## 参考资料

- Bjarne Stroustrup. *Evolving a language in and for the real world: C++ 1991–2006*. HOPL III, 2007.
- Bjarne Stroustrup. *Thriving in a Crowded and Changing World: C++ 2006–2020*. HOPL IV, 2020.
- Bjarne Stroustrup. *The Design and Evolution of C++*. Addison-Wesley, 1994.
- Margaret A. Ellis, Bjarne Stroustrup. *The Annotated C++ Reference Manual*. Addison-Wesley, 1990.
- Herb Sutter, Guy Davidson. *(Proposed) C++ IS schedule*. [[P1000R8]].
- isocpp.org：*The Committee*；*Current Status*。
- Herb Sutter 的会议报告（Sutter's Mill），2023–2026 年各次会议。
- Bjarne Stroustrup. *A call to action: Think seriously about "safety"; then do something sensible about it*. [[P2739R0]], 2022.
- Herb Sutter. *Core safety profiles for C++26*. [[P3081R2]]；Sean Baxter, Christian Mazakas. *Safe C++*. [[P3390R0]]。
- Mungo Gill 等. *Response to Core Safety Profiles (P3081)*. [[P3543R0]]；Corentin Jabot. *The Plethora of Problems With Profiles*. [[P3586R0]]。
