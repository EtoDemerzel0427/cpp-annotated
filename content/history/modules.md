---
title: 模块：二十年的 #include 替代方案
summary: 从 2005 年 Vandevoorde 的第一份模块提案，到 Clang 的模块映射、微软主导的 Modules TS、Google 的 ATOM 提案，再到 2019 年 Kona 会议的合并（P1103）与 C++20 定稿前的一系列修补；构建系统问题（依赖扫描、P1689、SG15）、C++23 的 import std，以及模块至今采用缓慢的现状。
status: draft
since: c++20
order: 90
papers: N1778, N2073, N3347, N4047, N4465, P0142R0, P0273R1, P0947R1, P0986R0, P1103R3, P1427R0, P1689R5, P1857R3, P1779R3, P1815R2, P2412R0, P2465R3, P3034R1
related: module, module.unit, module.import, module.global.frag, module.reach, cpp.module, cpp.import, basic.link, std.modules, toolchain/modules-in-practice
tags: 模块, 沿革, 构建, 预处理
updated: 2026-10-18
---

`#include` 是 C++ 从 C 继承来的接口机制：预处理器把头文件的文本原样粘进当前翻译单元，编译器再把粘出来的整段文本当作源码解析一遍。这个机制简单、通用，但它把接口和宏、把一个头文件和它之前出现过的所有头文件绑在了一起，而且每个翻译单元都要从头重新解析一遍同样的文本。

用语言内的模块代替文本包含，这个想法在 C++ 委员会里至少讨论了二十年。第一份正式提案出现在 2005 年；C++20 在 2019 年 2 月才把模块投票并入工作草案；标准库模块 `import std;` 要等到 C++23；直到本文写作时（2026 年），主流构建系统对模块的支持仍在补齐。本页按时间顺序讲这段历史：每一步解决了什么问题，留下了什么分歧，后来又是怎样妥协的。

规则本身见 [[module]]、[[module.unit]]、[[module.import]] 与预处理一侧的 [[cpp.module]]、[[cpp.import]]；编译器和 CMake 的实际用法见 [[toolchain/modules-in-practice]]。

## 文本包含的代价

Stroustrup 在 HOPL IV 论文（*Thriving in a Crowded and Changing World: C++ 2006–2020*，§9.3.1）里把头文件的问题归结为三条：

1. **缺乏代码卫生**。一个头文件里的代码（尤其是宏）可以改变后面另一个头文件的含义，所以 `#include` 的顺序是有意义的。
2. **分离编译的不一致**。同一实体在两个翻译单元里的声明可能不一致，而编译器和链接器并不能发现所有这类错误（这就是 [[basic.def.odr]] 里大量 IFNDR 的来源）。
3. **编译时间过长**。从源码文本编译一个接口本来就慢，同一个接口在成百上千个翻译单元里反复编译就更慢。

他给了一个数字：一个只有 70 个字符的 Hello World 程序，经过 `#include <iostream>` 展开后，编译器要处理 419,909 个字符（HOPL IV §9.3.1）。随着内联函数、`constexpr` 函数和模板越来越多地写在头文件里，第三个问题逐年加重。Stroustrup 同时指出，这些问题在 *The Design and Evolution of C++*（1994）第 18 章就已经讨论过。

第一个问题可以用一个很小的例子说明。宏是在预处理阶段处理的，它既不认识作用域，也不知道某段代码属于哪个库：

```cpp title="textual.cpp" error
#define value 0          // 某个先被包含的头文件里定义了这个宏
// ↓ 下面相当于 #include 进来的另一个库的头文件
struct Config {
    int value;           // error: 被替换成 int 0;，不再是合法的成员声明
};
```

模块把这条通道切断了：模块接口单元里定义的宏不会进入导入者（[[cpp.import]] 只对头文件单元导入宏）。下面的例子在本机 Clang 23 上编译运行通过，导入者里的 `#ifdef LIMIT` 不成立：

```cpp title="config.cppm" ok
export module config;
#define LIMIT 10                       // 只在本模块单元内有效
export constexpr int limit = LIMIT;
```

```cpp title="use.cpp" ok
import config;
#ifdef LIMIT
#error "宏不会跨模块边界泄漏，所以这里不会触发"
#endif
int main() { return limit == 10 ? 0 : 1; }
```

## 2005–2012：Vandevoorde 的模块提案

第一份系统的 C++ 模块提案来自 EDG 的 Daveed Vandevoorde。[[N1778]]（2005 年 1 月）是第一版，[[N1964]]（2006 年 2 月）是第三版，[[N2073]]（2006 年 9 月）是第四版。N2073 在开头写明了三个首要目标：显著缩短大型项目的构建时间；更好地分离接口和实现；为现有库提供可行的过渡路径。

N2073 的语法和后来 C++20 的语法差别很大。模块定义用 `export 模块名 { ... }` 包起来，命名空间作用域的声明默认是私有的，用 `public:` 标签导出：

```cpp title="N2073 的语法（历史提案，未被采纳）"
// File_1.cpp:
export Lib {          // 模块定义头，必须在所有声明之前
  import std;
public:
  struct S {
    S() { std::cout << "S()\n"; }
  };
}
// File_2.cpp:
import Lib;
int main() { S s; }
```

N2073 已经明确提出：导入指令不受宏展开影响，宏也不能伸进模块内部。它还讨论了导出宏的可能，但认为这会迫使编译器整合预处理器，并带来依赖宏之间的种种细节问题（N2073 §6.4）。这个问题在十二年后成为 ATOM 提案与 Modules TS 之间的核心分歧之一。

此后还有 [[N2316]]（第五版，2007 年）和 [[N3347]]（第六版，2012 年 1 月）。据 Stroustrup 回忆，这段时间委员会的优先任务是完成 C++0x，Vandevoorde 基本上是独自推进，得到的只是 "little more than moral support"（HOPL IV §9.3.1）。

## Clang 的模块映射：不改头文件的路线

2012 年 11 月，Apple 的 Doug Gregor 在 LLVM 开发者大会上介绍了 Clang 的模块系统（HOPL IV 参考文献 Gregor 2012）。这套设计最初是为 C 和 Objective-C 做的，出发点与 Vandevoorde 的方案完全不同：它不要求修改头文件，而是在头文件旁边放一个模块映射文件（`module.modulemap`），用语言之外的描述说明哪些头文件组成一个模块：

```text title="module.modulemap（Clang 扩展，不是 C++ 语法）"
module MyLib {
  header "MyLib.h"
  export *
}
```

启用 `-fmodules` 后，Clang 会把对这些头文件的 `#include` 自动翻译成模块导入，头文件被单独编译一次，结果缓存起来供所有翻译单元复用，导入方的宏也不会影响被导入的头文件（Clang 文档 *Modules*）。Objective-C 另有 `@import` 语法。Clang 文档特别说明，这套 Clang 模块与后来的 C++20 标准模块在语义和命令行接口上都有很大差别。

这条路线有大规模部署经验。Google 的 Richard Smith、Chandler Carruth 和 David Jones 在 [[P0273R1]]（2016）里说，他们对模块提案的修改意见"based in part on user experience with the C++ modules implementation in Clang"；Apple 的工程师在 [[P0841R0]]（*Modules at scale*，2017）中也报告了 Clang 模块的大规模使用情况。这些经验让 Clang 阵营特别看重两件事：现有头文件（包括以宏为接口的库）必须能平滑地纳入模块体系；构建性能必须在大型代码库上得到验证。

## 微软的设计与 Modules TS（2014–2018）

2014 年，微软的 Gabriel Dos Reis、Mark Hall 和 Gor Nishanov 提交了 [[N4047]]（*A Module System for C++*），随后修订为 [[N4214]]（2014 年 10 月）、[[N4465]]（2015 年 4 月，Lenexa 会议）和 [[P0142R0]]（2016 年 2 月）；配套的标准措辞是 [[N4466]] 与 [[P0143R2]]。Stroustrup 说这份设计在精神上更接近 Vandevoorde 的方案，并且很大程度上建立在他与 Dos Reis 在 Texas A&M 大学所做的 C++ 源码图表示研究之上（HOPL IV §9.3.1）。

N4465 列出了四个基本目标：组件化（componentization）、与宏隔离、可扩展的构建、支持理解语义的开发工具。它的语法已经很接近今天的样子：

```cpp title="N4465 的语法（历史提案）"
module Alfa;              // 模块声明：之后的声明属于模块 Alfa
export namespace Alfa {
  struct S3 { /* ... */ };
}
```

N4465 明确规定模块不能导出宏，宏也不能影响模块接口；以宏为接口的库应继续使用头文件（N4465 §4.11）。

2015 年 12 月，微软在 Visual Studio 2015 Update 1 中以 `/experimental:module` 开关发布了这一设计的实验性实现。同一篇博客说，EWG 已在 2015 年秋季的 Kona 会议上同意把这份提案作为技术规范（TS）推进（Microsoft C++ Team Blog，2015-12-03）。

TS 的工作草案从 [[N4592]]（2016 年 5 月）开始，经过 [[N4610]]、[[N4637]]、[[N4681]]，在 2017 年 7 月的 Toronto 会议上被送交 PDTS 投票（Sutter，Toronto 2017 trip report）。处理完各国成员体的意见后，最终文本 [[N4720]] 于 2018 年 1 月底交给 ISO（Sutter，Jacksonville 2018 trip report），并以 ISO/IEC TS 21544:2018 *Extensions to C++ for Modules* 的名义于 2018 年 5 月出版。

在 TS 阶段，设计已经吸收了一些 Clang 阵营的意见。P0273R1 记录了 EWG 在 2016 年 Jacksonville 会议上通过的三项修改：模块声明必须是源文件的第一个声明；允许把一个模块的接口拆成多个分区；模块实现单元与接口单元在语法上区分。不过 P0273 最核心的要求，即允许模块导出宏，没有进入 TS。

!!! note "两种立场"
    Stroustrup 把这场分歧概括为：Google 一方认为不能导出宏是 "fatal flaw"，Dos Reis 和他本人则认为不导出宏是模块化的根本要求（HOPL IV §9.3.1）。他引用自己 2018 年的文字说明理由，大意是 `import X; import Y;` 与 `import Y; import X;` 必须等价，任何东西都不能从一个模块隐式地泄漏到另一个模块。P0273 一方的理由是：Qt、MFC、ICU、部分 Boost 库、Google Test，以及标准库本身（`NULL`、`offsetof`、特性测试宏）都把宏作为公开接口的一部分，模块系统如果不能表达这些接口，就会把它们降为二等公民（P0273R1，"Exported macros" 一节）。

## ATOM：另一种取舍（2018）

TS 出版前后，有人提议把 Modules TS 直接并入 C++20。Stroustrup 记述说，这一提议在 2017 年和 2018 年两次被 Google 提出的不同设计所阻拦（HOPL IV §9.3.1）。这份不同的设计就是 Richard Smith 的 [[P0947R0]]（2018 年 2 月，*Another take on Modules*，常称 ATOM），修订版为 [[P0947R1]]（2018 年 3 月）。

P0947R1 开宗明义地说明了它与 TS 的关系：两者基于对目标的不同排序，凡是优先级不要求作出不同决定的地方，它都沿用 TS。它与 TS 的主要差异有：

- **遗留头文件单元**（legacy header unit）。`import "legacy-header.h";` 把一个现有头文件单独编译成一个合成的模块，导入时只产生语义效果，而不是文本效果。在 TS 中，模块里使用传统头文件只能靠文本包含，于是头文件之间的宏泄漏、重复解析问题都还在。
- **模块声明必须在文件开头**。这样不用完整预处理就能确定一个文件是不是模块单元、依赖哪些模块。
- **`module` 和 `import` 是上下文关键字**，避免破坏现有把这两个词用作标识符的代码。
- **宏的导出与模块本身解耦**。R1 中 `export import` 不再重新导出宏，导出宏的 `#export` 被标为可单独取舍的部分，其余设计不依赖它。

Smith 与 David Jones 随后在 [[P0986R0]]（2018 年 3 月，*Comparison of Modules Proposals*）中逐项对比了两份提案。2018 年 3 月的 Jacksonville 会议上，与会者同意先把一组核心模块功能纳入 C++20，其余为过渡头文件代码设计的部分（可能包括宏支持）继续留在 TS 的更新中处理（Sutter，Jacksonville 2018 trip report）。Dos Reis 与 Smith 随后联名提交了 [[P0983R0]]（*Plan of Record for Making C++ Modules Available in C++ Standards*，2018 年 4 月）和 [[P1087R0]]（*Modules for Standard C++*，2018 年 5 月）。

## 合并：P1103 与 Kona 2019

合并方案是 [[P1103R0]]（*Merging Modules*，2018 年 6 月，Smith 与 Dos Reis），之后由 Smith 修订到 [[P1103R3]]（2019 年 2 月）。Stroustrup 记述说，参与这次多年妥协的关键人物是 Smith 和 Dos Reis，GCC 的模块实现者 Nathan Sidwell 等人也有贡献；2018 年年中以后，讨论主要集中在保证各实现可移植所需要的技术细节上（HOPL IV §9.3.1）。2018 年 11 月的 San Diego 会议上，P1103 "for the first time had a unified design approved targeting C++20"（Sutter，San Diego 2018 trip report）。

P1103R3 第 3.4、3.5 节列出了合并方案相对两份前身的不兼容之处：

- 相对 TS：全局模块片段（[[module.global.frag]]）前必须写 `module;` 引导（来自 [[P0713R1]]）；一个模块拥有的实体的语义性质（例如类型是否完整）一律以模块接口单元末尾的状态为准，与导出声明出现的位置无关。
- 相对 ATOM：保留了 TS 的全局模块片段，这削弱了 ATOM 让工具不经预处理就能识别文件开头的目标，但不使用全局模块片段的代码仍能得到 ATOM 的好处；`export` 和 `module` 按 EWG 的意见作为关键字处理（后来 P1857 又把 `module`、`import` 改为只在特定位置识别的预处理指令，见下文）。

ATOM 的头文件单元进入了合并方案。头文件单元导入时会带来宏，[[cpp.import]] 中导入头文件单元会使其宏定义可见的规则就来源于此。下面这个例子在本机 Clang 23 上可以编译运行，但 Clang 会给出 "the implementation of header units is in an experimental phase" 的警告：

```cpp title="header_unit.cpp" ok
import <climits>;               // 头文件单元：与具名模块不同，宏会随之导入
static_assert(INT_MAX > 0);     // INT_MAX 是宏
int main() {}
```

!!! history "工具链的疑虑"
    合并方案定型的同时，一批熟悉构建系统的委员会成员提出了担忧。[[P1427R0]]（*Concerns about module toolability*，2018 年 11 月，Bindels、Craig、Downey、Rivera、Honermann、Jabot、Kelly）认为模块给构建工具带来的问题还没有被充分理解；Rene Rivera 的 [[P1441R0]]（*Are modules fast?*，2019 年 1 月）担心导入依赖会降低并行编译的程度；Apple 的 [[P1482R0]]（*Modules Feedback*，2019 年 2 月）也提出了实现反馈。Stroustrup 记述说，这些早期印象后来被证明过于悲观：Rivera 在修订版 [[P1441R1]] 中更新了结论，build2 已经支持模块，微软和 Google 报告了良好的构建结果，Sidwell 报告自己只用两周业余时间就让 GNU make 支持了模块（[[P1602R0]]）；Dos Reis、Sidwell、Smith、Vandevoorde 四位实现者在 2019 年 2 月 14 日发出联合说明 *Modules are ready*（HOPL IV §9.3.1）。

2019 年 2 月的 Kona 会议上，P1103R3 以 46 票赞成、6 票反对并入 C++20 工作草案，所有实现者都投了赞成票（HOPL IV §9.3.1）。Sutter 在会议报告中说，这是约 35 年来 C++ 第一次加入一种让用户定义具名封装边界的新特性，此前的三种是变量、函数和类（Sutter，Kona 2019 trip report）。

## 合并方案的各个部分从哪里来

P1103R3 第 2 节逐项说明了合并后的设计。把它和前面几份提案对照，可以看出今天 [[module]] 一章里的每个概念大致来自哪里：

| C++20 概念 | 来源 | 条款 |
|---|---|---|
| `export module M;` / `module M;`，模块接口单元与实现单元 | 微软设计（N4465）与 Modules TS | [[module.unit]] |
| 模块分区 `M:part` | P0273（2016 年 Jacksonville 会议获 EWG 支持）、ATOM | [[module.unit]] |
| 全局模块片段 `module; #include ...` | Modules TS，`module;` 引导来自 P0713R1 | [[module.global.frag]] |
| 头文件单元 `import <h>;`、`import "h";` | ATOM 的遗留头文件单元 | [[module.import]]、[[cpp.import]] |
| 把 `#include` 翻译为头文件单元导入 | ATOM；Clang 模块映射的做法 | [[cpp.include]] |
| 可见性（visibility）与可达性（reachability）分离 | P1103 合并时的统一表述 | [[module.reach]] |
| 不导出宏（具名模块） | Vandevoorde、微软设计、Modules TS | [[cpp.import]] |

合并方案对非模块代码的处理值得多看一眼，因为它正是两种立场的交汇点：

- **全局模块片段**里只能出现预处理指令，但这些指令可以 `#include` 进声明。这些声明不属于模块；如果模块单元没有（传递地）引用它们，它们就被丢弃，对导入者既不可见也不可达（P1103R3 §2.3.1）。这条规则后来发展为 [[module.global.frag]] 中 decl-reachable 的定义，目的是防止一个模块的接口被它私下包含的头文件撑大。
- **头文件单元**把一个头文件当作源文件单独处理，抽取其接口，并把预处理该头文件所定义的宏保存下来供导入者使用。用 `export import "h";` 重新导出头文件单元时，宏不会随之导出；只有直接的头文件导入语法才导入宏（P1103R3 §2.3.2）。
- **非模块代码也可以导入模块**，而且导入可以出现在任何位置。这允许一个库自下而上地模块化：先把实现改写为模块，再让原来的头文件用模块接口来定义（P1103R3 §2.3.4）。
- 对全局模块片段和头文件单元中的声明，P1103R3 只要求它们在可见时可达，而在仅被传递导入时是否可达则不作规定，理由是严格执行这一点会给某些实现带来很高的成本（P1103R3 §2.3.3）。这就是今天 [[module.reach]] 中若干 unspecified 规定的由来。

下面是一个使用全局模块片段的最小例子，在本机 Clang 23 上编译运行通过：

```cpp title="foo.cppm" ok
module;
#include <cstddef>                 // 全局模块片段：模块声明之前只能有预处理指令
export module foo;
export std::size_t count() { return 42; }
```

## C++20 定稿前的修补（2019–2020）

Kona 2019 之后到 C++20 定稿之间，模块又经历了一系列修补。它们大多来自实现经验和国家成员体（NB）意见，后来都成了今天条文的一部分。

**Cologne，2019 年 7 月。** EWG 批准了一组被视为缺陷修复的论文（[[P1018R4]]）：[[P1766R1]]（*Mitigating minor modules maladies*，限制仅为链接目的而命名的无名类，并规定不同翻译单元中的默认实参不一致为 IFNDR）、[[P1811R0]]（放宽重定义限制：即使导入的模块或头文件单元已经提供了某个实体的定义，翻译单元里仍可以再出现该实体的一个定义，减少传统头文件被多次引入时的冲突）、[[P1703R1]]（头文件单元的 `import` 必须独占一行）以及 [[P1502R1]]（规定标准库哪些头文件可作为头文件单元导入，见 [[headers]]）。Red Hat 的 Jason Merrill 在其 Cologne 核心语言报告中逐条介绍了这些修改。

**Belfast，2019 年 11 月。** [[P1874R1]] 规定了模块中非局部变量动态初始化的顺序，解决了 NB 意见 US 082（编辑报告 [[N4843]]）。

**Prague，2020 年 2 月。** C++20 的最后一次会议又通过了三份较大的修改（编辑报告 [[N4859]]）：

- [[P1857R3]]（*Modules Dependency Discovery*，Michael Spencer）。P1703 只处理了 `import`，而且处理得过宽，把行首任何 `import` 都当作关键字，会破坏 `import -> doImport();` 这样的代码。P1857 把 `module`、`import` 行变成真正的预处理指令，并精确规定它们何时被识别（见 [[cpp.module]]、[[cpp.import]]）。这样构建工具只需做预处理，不必解析 C++，就能找出一个文件提供和需要哪些模块。这一篇论文解决了 11 条 NB 意见。
- [[P1779R3]]（*ABI isolation for member functions*，Davis Herring）。在具名模块中，类定义内定义的成员函数不再隐式 `inline`（[[class.mfct#1]] 只对附属于全局模块的成员函数规定隐式 inline）。这样修改函数体不会改变模块的接口，导入者也不必重新编译。
- [[P1815R2]]（*Translation-unit-local entities*，Davis Herring）。引入 TU-local 实体与 [[g:exposure]] 的概念（[[basic.link#14]]–[[basic.link#17]]），禁止模块接口通过内联函数等途径暴露内部链接的实体。

P1779 的效果可以从符号表上看到。下面的模块在本机用 Clang 23 编译后，`area` 作为强定义出现在模块的目标文件中，符号名带有模块附属标记（`Square@shapes::area() const`）：

```cpp title="shapes.cppm" ok
export module shapes;
export struct Square {
    int side;
    int area() const { return side * side; }  // 具名模块中：不是隐式 inline
};
```

P1815 的规则则让下面的接口非良构。值得注意的是，本机 Clang 23 只给出 `-WTU-local-entity-exposure` 警告而没有报错；按 [[basic.link#17]]，这在模块接口中是非良构的：

```cpp title="tu_local.cppm" error
export module tu;
static int helper() { return 1; }               // 内部链接：TU-local
export inline int api() { return helper(); }    // error: 暴露了 TU-local 实体 helper
```

**C++23 之后的一处补丁。** 2024 年 3 月的 Tokyo 会议把 [[P3034R1]]（*Module Declarations Shouldn't be Macros*，Spencer）作为缺陷报告（DR）接受（编辑报告 [[N4982]]）：模块名的各个组成部分不能是宏。理由与 P1857 相同，依赖扫描不应该依赖宏展开的结果。本机 Clang 23 已实现：

```cpp title="macro_name.cppm" error
#define NAME foo
export module NAME;   // error: 模块名的组成部分不能是对象式宏
```

## 构建系统：模块带来的新问题

头文件时代，翻译单元之间没有编译顺序：每个 `.cpp` 都可以独立、并行地编译。模块打破了这一点。导入一个模块之前，必须先编译它的接口单元，得到二进制模块接口（BMI）；而要知道一个源文件导入了哪些模块，又要先读它。于是构建系统必须在编译之前先做一次依赖发现，再按依赖图安排编译顺序。Fortran 90 的模块早就有同样的问题，[[P1300R0]]（*Remember the FORTRAN*，2018）就用 Fortran 的经验提醒委员会这一点。

C++ 标准本身不涉及文件、BMI 或编译顺序，[[lex.phases]] 只说被依赖的模块单元和头文件单元的源码是否需要可用由实现定义。因此这些问题主要在标准之外解决，承担协调工作的是工具研究组 SG15。据 SG15 邮件列表档案，该组由 Titus Winters 主持，2018 年前后开始活跃，2019 年初已有专门讨论模块与工具交互的电话会议。

这一时期的主要成果有：

| 文档 | 内容 |
|---|---|
| [[P1184R2]]（Sidwell） | *A Module Mapper*：编译器与构建系统之间的一个协议，编译器在需要某个 BMI 时向构建系统询问。GCC 的实现采用了这一思路 |
| [[P1689R5]]（Ben Boeckel、Brad King，Kitware） | *Format for describing dependencies of source files*：一种 JSON 格式，描述一个源文件提供哪个模块、需要哪些模块。它不是标准的一部分，但 Clang（`clang-scan-deps`）、GCC 和 MSVC 都能输出这种格式，CMake 以此为基础实现模块支持 |
| [[P1857R3]] | 语言一侧的配合：让依赖扫描只需预处理 |
| [[P1688R0]]、[[P2656R4]]、[[P2717R6]] | 先是生态系统技术报告的设想，后来改为生态系统国际标准（*C++ Ecosystem International Standard*）与工具自省提案；P2656 与 P2717 在 2024 年 12 月以 WITHDRAWN 的标题撤回 |
| [[P2473R1]]、[[P2577R2]]、[[P2581R2]]（Daniel Ruoso，Bloomberg） | 如何发布预编译的模块库：已安装的库如何描述自己的模块，BMI 在什么条件下可以在不同编译之间复用 |

CMake 的进展是一个具体的刻度。Kitware 在 2023 年的博文 *import CMake; the Experiment is Over!* 中宣布，CMake 3.28 正式支持 C++20 具名模块，不再需要实验开关，并感谢 SG15 以及 Visual Studio、Clang、GCC 三方开发者的协调。按当前 CMake 文档，模块支持依赖 P1689 格式的扫描结果，只适用于 Ninja 和 Visual Studio 生成器；头文件单元在所有生成器下都不受支持。

## import std：标准库模块（C++23）

C++20 有了模块，却没有模块形式的标准库。更早的 [[P0581R1]]（*Standard Library Modules*，2018）提议把标准库划分为 `std.core`、`std.io` 等若干模块，但 Stroustrup 记述说，这一较大的重组不得不推迟到 C++23（HOPL IV §9.3.1）。C++20 只提供了标准库头文件的头文件单元（P1502）。

2021 年 7 月，Stroustrup 的 [[P2412R0]]（*Minimal module support for the standard library*）建议先让一个包含整个标准库的模块 `std` 进入 C++23，细粒度划分的讨论推后。他给出了在 MSVC 上的测量：Hello World 程序用 `#include <iostream>` 编译约 0.87 秒，用 `import std;` 约 0.08 秒；使用 9 个常见头文件的程序分别约为 2.20 秒和 0.44 秒（P2412R0 第 5 页）。也就是说，导入一个比 `<iostream>` 大得多的模块反而快了约 10 倍。

随后的 [[P2465R3]]（Lavavej、Dos Reis、Stroustrup、Wakely）给出了正式措辞，提供两个具名模块：

- `import std;` 导入 C++ 头文件和 C 包装头文件（如 `<cstdio>`）在命名空间 `std` 中的全部内容，以及 `<new>` 中的 `::operator new` 等；
- `import std.compat;` 在此之上再提供 C 包装头文件在全局命名空间中的对应名字（如 `::fopen`）。

拆成两个模块是为了同时照顾两种意见：一方希望借模块的机会彻底摆脱"`<cmeow>` 是否也声明 `::meow`"这个历史包袱，另一方担心不提供全局名字会让现有代码难以迁移（P2465R3，"Rationale" 一节）。这篇论文在 2022 年 7 月的线上全会上并入 C++23 工作草案（编辑报告 [[N4918]]）。规则见 [[std.modules]]。

下面的程序在本机先用 libc++ 自带的 `std.cppm` 构建出 `std.pcm`，再编译运行，输出 `Hello, modules`：

```cpp title="hello.cpp" ok
import std;
int main() { std::println("Hello, {}", "modules"); }
```

各家实现的时间点：微软文档称自 Visual Studio 2022 17.5 起，以模块方式导入标准库已经标准化并完整实现；GCC 15 的发布说明在 libstdc++ 部分列出了 `std` 与 `std.compat` 模块（也可用于 C++20）；CMake 的 `import std` 支持长期处于实验开关之后，CMake 4.5（截至写作时处于候选发布阶段）的发布说明称它对所有启用模块扫描的 C++20 及以后代码可用。

## 采用缓慢：截至 2026 年的状况

从 Kona 2019 算起，模块已经进入标准七年多，但在多数项目里仍不是默认选择。原因主要不在语言规则，而在实现和工具链：

- **编译器**。微软文档称 Visual Studio 2019 16.10 起 C++20 模块功能完整。CMake 文档列出的最低版本是 MSVC 工具集 14.34、Clang 16 和 GCC 14。不过 GCC 16 的发布说明仍写道 "C++20 modules support is still experimental and must be enabled by -fmodules"。
- **头文件单元**。头文件单元是 ATOM 留下的过渡机制，也是实现最弱的部分：本机 Clang 23 每次导入都会给出实验性警告，CMake 不支持任何生成器下的头文件单元。MSVC 支持把可导入头文件的 `#include` 自动翻译为导入（[[cpp.include]] 允许的实现定义行为）。
- **BMI 不可分发**。各编译器的 BMI 格式互不兼容，并且与编译器版本、编译选项绑定，库只能分发模块接口的源码，由使用者自己构建 BMI（P2581 讨论的正是 BMI 在什么条件下可以复用）。
- **生态惯性**。现有的库大多同时要支持没有模块的旧编译器，往往只能在头文件之外另提供一个模块包装。

这些问题的现状和具体用法见 [[toolchain/modules-in-practice]]。

## 常见误解

!!! pitfall "C++20 模块就是 Modules TS"
    不是。C++20 模块来自 P1103 对 Modules TS 与 ATOM 的合并，并在 2019–2020 年又经过多次修改。按 P1103R3 §3.4，TS 下合法的一些代码在 C++20 中不再合法或含义改变，例如全局模块片段必须以 `module;` 开头；头文件单元、`module`/`import` 作为预处理指令（P1857）、TU-local 实体（P1815）等也都不在 TS 中。据 IEC 网上商店的记录，ISO/IEC TS 21544:2018 已于 2021 年 9 月撤销。

!!! pitfall "import <vector>; 与 #include <vector> 等价"
    不完全等价。头文件单元是把头文件当作独立的源文件处理的，导入之前定义的宏不会影响它（P1103R3 §2.3.2；[[module.import]]）；而 `#include` 是在当前的宏环境中做文本替换。两者都会带来该头文件定义的宏。实现可以把可导入头文件的 `#include` 翻译成头文件单元导入（[[cpp.include]]），但这是实现定义的。

!!! pitfall "用了模块就不会有 ODR 问题"
    模块减少了 ODR 违反的机会：具名模块中声明的实体附属于该模块（[[module.unit]]），两个具名模块各自定义的同名非导出函数是不同的实体，在 Itanium ABI 下的修饰名也不同（见 [[toolchain/modules-in-practice]]）。但全局模块片段和头文件单元中的声明仍属于全局模块，仍要遵守 [[basic.def.odr]] 的要求；P1811 放宽重定义限制，也说明这类重复在模块世界里依然存在。

## 时间线

| 时间 | 事件 | 出处 |
|---|---|---|
| 1994 | *The Design and Evolution of C++* 第 18 章讨论预处理器与头文件的问题 | D&E；HOPL IV §9.3.1 |
| 2005-01 | Vandevoorde 提交第一版模块提案 | [[N1778]] |
| 2006-09 | 第四版，确定构建时间、接口分离、过渡路径三个目标 | [[N2073]] |
| 2012-01 | Vandevoorde 第六版 | [[N3347]] |
| 2012-11 | Doug Gregor 在 LLVM 开发者大会介绍 Clang 模块 | HOPL IV 参考文献 |
| 2014-05 | 微软 Dos Reis、Hall、Nishanov 提交模块设计 | [[N4047]] |
| 2015-04 | Lenexa 会议，修订版提出四个目标 | [[N4465]] |
| 2015 秋 | Kona 会议 EWG 同意以 TS 推进 | Microsoft C++ 博客 |
| 2015-12 | VS 2015 Update 1 提供 `/experimental:module` | Microsoft C++ 博客 |
| 2016 | Google 根据 Clang 部署经验提出修改，部分被 EWG 接受 | [[P0273R1]] |
| 2016-05 | Modules TS 第一份工作草案 | [[N4592]] |
| 2017-07 | Toronto 会议，Modules TS 送交 PDTS 投票 | Sutter，Toronto 2017 |
| 2018-01 | Modules TS 定稿交给 ISO | [[N4720]]；Sutter，Jacksonville 2018 |
| 2018-02/03 | Google 提出 ATOM；两份提案的对比 | [[P0947R1]]、[[P0986R0]] |
| 2018-05 | ISO/IEC TS 21544:2018 出版 | ISO |
| 2018-06 | 合并提案第一版 | [[P1103R0]] |
| 2018-11 | San Diego 会议批准统一设计；工具链疑虑 | Sutter，San Diego 2018；[[P1427R0]] |
| 2019-02 | Kona 会议，P1103R3 以 46 比 6 并入 C++20 | HOPL IV §9.3.1；[[P1103R3]] |
| 2019-07 | Cologne 会议，一组缺陷修复与标准库头文件单元 | [[P1018R4]] |
| 2019-11 | Belfast 会议，模块中的初始化顺序 | [[P1874R1]]、[[N4843]] |
| 2020-02 | Prague 会议，依赖发现、成员函数 ABI 隔离、TU-local 实体 | [[P1857R3]]、[[P1779R3]]、[[P1815R2]]、[[N4859]] |
| 2021-07 | Stroustrup 建议 C++23 先提供 `import std` | [[P2412R0]] |
| 2022-06 | P1689 依赖格式第五版 | [[P1689R5]] |
| 2022-07 | `std` 与 `std.compat` 并入 C++23 | [[P2465R3]]、[[N4918]] |
| 2023 | CMake 3.28 正式支持具名模块 | Kitware 博客 |
| 2024-03 | 模块名不能是宏（DR） | [[P3034R1]]、[[N4982]] |
| 2024-12 | 生态系统国际标准与工具自省提案撤回 | [[P2656R4]]、[[P2717R6]] |
| 2026 | GCC 16 仍把模块列为实验特性；CMake 4.5 候选版放开 `import std` | GCC 16 发布说明；CMake 4.5 发布说明 |

## 现状与未来

回头看，模块的二十年里有两条线索一直没有断。第一条是宏：Vandevoorde 和微软的设计都以与宏隔离为目标，Clang 阵营则要求能纳入以宏为接口的现有头文件。C++20 的答案是分层：具名模块不导出宏，头文件单元导出宏，全局模块片段里仍可以 `#include`。第二条是构建：模块在语言上可以写得很干净，但它给构建系统引入了编译顺序，这部分工作被放在标准之外，由 SG15、编译器和 CMake 等工具在 2019 年之后逐步补齐。

从当前草案看，语言一侧的模块规则自 C++20 以来变化不大，主要是缺陷修复（如 P3034）以及与新特性（例如反射在 [[basic.link#19]] 例子中涉及的暴露规则）的衔接。仍在进行中的工作大多在标准之外：头文件单元的实现、BMI 的复用与分发、构建系统对 `import std` 的默认支持，以及大型代码库从头文件迁移的经验积累。

## 参考资料

- Bjarne Stroustrup. *Thriving in a Crowded and Changing World: C++ 2006–2020*. Proc. ACM Program. Lang. 4, HOPL (2020)，§9.3.1 *Modules*。
- Daveed Vandevoorde. *Modules in C++*：[[N1778]]（2005）、[[N1964]]（2006）、[[N2073]]（2006）、[[N2316]]（2007）、[[N3347]]（2012）。
- Gabriel Dos Reis, Mark Hall, Gor Nishanov. *A Module System for C++*：[[N4047]]、[[N4214]]、[[N4465]]；Dos Reis，[[P0142R0]]、[[N4466]]、[[P0143R2]]。
- Modules TS 工作草案：[[N4592]]、[[N4610]]、[[N4637]]、[[N4681]]、[[N4720]]；ISO/IEC TS 21544:2018。
- Richard Smith, Chandler Carruth, David Jones. *Proposed modules changes from implementation and deployment experience*，[[P0273R1]]。
- Bruno Cardoso Lopes, Adrian Prantl, Duncan P. N. Exon Smith. *Modules at scale*，[[P0841R0]]。
- Richard Smith. *Another take on Modules*，[[P0947R0]]、[[P0947R1]]；Smith, Jones，*Comparison of Modules Proposals*，[[P0986R0]]。
- Gabriel Dos Reis, Richard Smith. [[P0983R0]]、[[P1087R0]]；Richard Smith (et al.). *Merging Modules*，[[P1103R0]]–[[P1103R3]]。
- 工具链相关：[[P1300R0]]、[[P1427R0]]、[[P1441R0]]、[[P1441R1]]、[[P1482R0]]、[[P1602R0]]、[[P1184R2]]、[[P1689R5]]、[[P1688R0]]、[[P2656R4]]、[[P2717R6]]、[[P2473R1]]、[[P2577R2]]、[[P2581R2]]。
- C++20 定稿前的修补：[[P1018R4]]（EWG 状态报告，Cologne 2019）、[[P1766R1]]、[[P1811R0]]、[[P1703R1]]、[[P1502R1]]、[[P1874R1]]、[[P1857R3]]、[[P1779R3]]、[[P1815R2]]；编辑报告 [[N4843]]、[[N4859]]。
- 标准库模块：[[P0581R1]]、[[P2412R0]]、[[P2465R3]]；编辑报告 [[N4918]]。
- [[P3034R1]]；编辑报告 [[N4982]]。
- Herb Sutter 的会议报告（herbsutter.com）：Toronto 2017（2017-07）、Jacksonville 2018（2018-04）、San Diego 2018（2018-11）、Kona 2019（2019-02）。
- Jason Merrill. *Report from the July 2019 ISO C++ meeting (core language)*，Red Hat Developer，2019-09-03。
- Gabriel Dos Reis, Andrew Pardoe. *C++ Modules in VS 2015 Update 1*，Microsoft C++ Team Blog，2015-12-03；Microsoft Learn，*Overview of modules in C++* 与 *Import the C++ standard library using modules*。
- Clang 文档：*Modules*（clang.llvm.org/docs/Modules.html）。
- Kitware. *import CMake; the Experiment is Over!*（kitware.com）；CMake 手册 *cmake-cxxmodules(7)*；CMake 4.5 发布说明。
- GCC 15、GCC 16 发布说明（gcc.gnu.org/gcc-15/changes.html、gcc-16/changes.html）。
