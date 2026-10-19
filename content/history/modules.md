---
title: 模块的由来
summary: C++20 模块为什么不导出宏、为什么同时有全局模块片段和头文件单元、为什么 module 和 import 是预处理指令：这些规则分别来自十几年里几份互相竞争的设计，以及为构建工具做出的让步。
status: draft
since: c++20
order: 90
papers: N2073, N4465, P0273R1, P0947R1, P1103R3, P1857R3, P1779R3, P1815R2, P1689R5, P2412R0, P2465R3, P3034R1
related: module, module.unit, module.import, module.global.frag, module.reach, cpp.module, cpp.import, basic.link, std.modules, toolchain/modules-in-practice
tags: 模块, 沿革, 构建, 预处理
updated: 2026-10-19
---

!!! tldr
    - 模块要解决 `#include` 的三个问题：宏和声明在头文件之间互相干扰、同一实体在各翻译单元里的声明可能不一致、同样的头文本在每个翻译单元里重复解析。
    - 争论最久的是宏。C++20 的答案是分层：具名模块不导出宏，头文件单元导出宏，全局模块片段里仍可以 `#include`。
    - `module`、`import` 行是预处理指令，模块名不能来自宏，模块声明必须在文件开头。这些规则都是为了让构建工具不解析 C++ 就能找出依赖。
    - 具名模块里类内定义的成员函数不再隐式 inline，模块接口不能暴露内部链接的实体。两条规则都是为了让接口和实现真正分开。
    - 模块进入 C++20 之后采用缓慢，主要原因在工具链：编译顺序、不可分发的二进制接口、实验阶段的头文件单元。

规则本身见 [[module]]、[[module.unit]]、[[module.import]] 和预处理一侧的 [[cpp.module]]、[[cpp.import]]；编译器和 CMake 的实际用法见 [[toolchain/modules-in-practice]]。

## 文本包含出了什么问题

`#include` 是从 C 继承来的接口机制。预处理器把头文件的文本原样粘进当前翻译单元，编译器再把粘出来的整段文本当作源码解析一遍。Stroustrup 把它的问题归结为三条（HOPL IV §9.3.1）：

1. **缺乏隔离**。一个头文件里的代码，尤其是宏，可以改变后面另一个头文件的含义，所以 `#include` 的顺序有意义。
2. **分离编译不一致**。同一实体在两个翻译单元里的声明可能不同，编译器和链接器发现不了所有这类错误。[[basic.def.odr]] 里大量不要求诊断的规则就来源于此。
3. **编译慢**。一个 70 个字符的 Hello World 程序，经过 `#include <iostream>` 展开后，编译器要处理约 42 万个字符（HOPL IV §9.3.1）。模板、内联函数和 `constexpr` 函数越来越多地写在头文件里，这个问题逐年加重。

第一个问题最容易演示。宏在预处理阶段展开，不认识作用域，也不知道一段代码属于哪个库：

```cpp title="textual.cpp" error
#define value 0      // 某个先被包含的头文件定义的宏
// 下面相当于另一个库的头文件
struct Config {
    int value;       // error: 展开成 int 0;
};
```

模块切断了这条通道。模块接口单元里定义的宏不会进入导入者，[[cpp.import]] 只让头文件单元的导入带来宏。下面两个文件在本机 Clang 23 上编译运行通过，导入者里的 `#ifdef LIMIT` 不成立：

```cpp title="config.cppm" ok
export module config;
#define LIMIT 10                   // 只在本模块单元内有效
export constexpr int limit = LIMIT;
```

```cpp title="use.cpp" ok
import config;
#ifdef LIMIT
#error "宏不会跨过模块边界，这里不会触发"
#endif
int main() { return limit == 10 ? 0 : 1; }
```

## 第一次尝试：在语言里写模块（2005–2012）

第一份系统的模块提案来自 EDG 的 Daveed Vandevoorde，从 2005 年起修订了六版。第四版 [[N2073]] 写明了三个目标：显著缩短大型项目的构建时间，更好地分离接口和实现，为现有库提供过渡路径。这三个目标一直延续到 C++20。

它的语法和今天很不一样。模块定义用 `export 模块名 { ... }` 包起来，声明默认私有，用 `public:` 标签导出：

<div class="compare" markdown="1">

```cpp title="N2073（未被采纳）"
export Lib {
  import std;
public:
  struct S { /* ... */ };
}
// 另一个文件
import Lib;
```

```cpp title="C++20"
export module Lib;
import std;
export struct S { /* ... */ };


// 另一个文件
import Lib;
```

</div>

N2073 已经规定导入不受宏影响、宏也伸不进模块内部。它讨论过导出宏，但认为这会迫使编译器整合预处理器（N2073 §6.4）。这个问题后来成了各方分歧的核心。当时委员会的精力集中在 C++0x 上，据 Stroustrup 回忆，这份提案得到的支持很有限（HOPL IV §9.3.1）。

## 两条路线：改语言，还是包装现有头文件

### Clang 的模块映射

2012 年，Clang 为 C 和 Objective-C 做了一套模块系统，出发点与 Vandevoorde 相反：不修改头文件，而在旁边放一个映射文件，用语言之外的描述说明哪些头文件组成一个模块：

```text title="module.modulemap（Clang 扩展，不是 C++ 语法）"
module MyLib {
  header "MyLib.h"
  export *
}
```

启用 `-fmodules` 后，Clang 把对这些头文件的 `#include` 自动换成模块导入。头文件只编译一次，结果缓存供所有翻译单元复用，导入方的宏也影响不到它（Clang 文档 *Modules*）。这套机制在 Google 和 Apple 有大规模部署经验（[[P0273R1]]、[[P0841R0]]）。它让 Clang 一方特别看重两件事：以宏为接口的现有头文件必须能平滑纳入模块，构建性能必须在大代码库上验证过。

### 微软的设计与 Modules TS

2014 年起，微软的 Gabriel Dos Reis 等人提出另一份设计，修订到 [[N4465]] 时，语法已经接近今天：

```cpp title="N4465 的语法（历史提案）"
module Alfa;            // 之后的声明属于模块 Alfa
export namespace Alfa {
  struct S3 { /* ... */ };
}
```

它的目标是组件化、与宏隔离、可扩展的构建和支持语义感知的工具。N4465 明确规定模块不导出宏，以宏为接口的库继续用头文件（N4465 §4.11）。这份设计以技术规范（TS）的形式推进，2018 年作为 ISO/IEC TS 21544 出版，通常称为 Modules TS。TS 阶段已经吸收了 Clang 一方的部分意见：模块声明必须是文件的第一个声明，接口可以拆成多个分区，实现单元与接口单元在语法上区分（P0273R1）。

### 分歧在宏

P0273 最核心的要求，即允许模块导出宏，没有进入 TS。双方的理由都是技术性的：

- 反对导出宏的一方认为，`import X; import Y;` 必须和 `import Y; import X;` 等价，任何东西都不能从一个模块隐式泄漏到另一个模块（HOPL IV §9.3.1）。
- 要求导出宏的一方指出，Qt、ICU、Google Test 乃至标准库本身（`NULL`、`offsetof`、特性测试宏）都把宏当作公开接口的一部分。模块如果表达不了这些接口，这些库就成了二等公民（P0273R1，"Exported macros" 一节）。

## ATOM 与合并方案

2018 年，Google 的 Richard Smith 提出了另一份完整设计 [[P0947R1]]（*Another take on Modules*，常称 ATOM）。它在优先级不要求不同的地方都沿用 TS，主要差别有四点：

- **遗留头文件单元**。`import "legacy.h";` 把一个现有头文件单独编译成一个合成模块，导入时只产生语义效果，不再做文本粘贴。在 TS 里，模块使用传统头文件只能靠 `#include`，宏泄漏和重复解析都还在。
- **模块声明必须在文件开头**，这样不用完整预处理就能知道一个文件是不是模块单元、依赖哪些模块。
- **`module` 和 `import` 是上下文关键字**，不破坏把这两个词用作标识符的现有代码。
- **导出宏与模块本身解耦**，宏的导出成为可以单独取舍的部分。

两份设计经 Smith 和 Dos Reis 合并为 [[P1103R3]]（*Merging Modules*），2019 年并入 C++20。合并方案对宏的问题给出了分层的回答，今天 [[module]] 一章里的几种单元就是这样来的：

| 你写的 | 宏会不会进入导入者 | 主要来源 | 条款 |
|---|---|---|---|
| `export module M;` 具名模块 | 不会 | N2073、N4465、Modules TS | [[module.unit]] |
| `module M:part;` 模块分区 | 不会 | P0273、ATOM | [[module.unit]] |
| `module;` 后面 `#include`（全局模块片段） | 只在本单元内 | Modules TS | [[module.global.frag]] |
| `import <h>;` 头文件单元 | 会 | ATOM | [[module.import]]、[[cpp.import]] |
| `#include` 被实现换成头文件单元导入 | 会 | ATOM、Clang 模块映射 | [[cpp.include]] |

头文件单元导入会带来宏，这是对 P0273 一方的回应。下面的例子需要先把 `<climits>` 预编译成头文件单元，本机 Clang 23 编译运行通过，但每次导入都会警告头文件单元仍在实验阶段：

```cpp title="header_unit.cpp" ok
import <climits>;            // 头文件单元：宏随之导入
static_assert(INT_MAX > 0);  // INT_MAX 是宏
int main() {}
```

### 全局模块片段：模块里怎么用老头文件

全局模块片段是 TS 留下的另一条路。`module;` 之后、模块声明之前只能出现预处理指令，但这些指令可以 `#include` 进声明：

```cpp title="foo.cppm" ok
module;
#include <cstddef>    // 全局模块片段：只能有预处理指令
export module foo;
export std::size_t count() { return 42; }
```

这些声明属于全局模块而不属于 `foo`。如果模块单元没有用到它们，它们就被丢弃，对导入者既不可见也不可达（P1103R3 §2.3.1）。这条规则后来发展成 [[module.global.frag]] 里 decl-reachable 的定义，目的是不让一个模块私下包含的头文件撑大它的接口。

合并方案还有一处有意留白。对全局模块片段和头文件单元中的声明，它只要求可见时可达，仅被间接导入时是否可达不作规定，理由是严格执行会让某些实现付出很高的代价（P1103R3 §2.3.3）。[[module.reach]] 里几条 unspecified 的规定就是这处妥协的痕迹。

## 为构建工具让路

头文件时代，各个 `.cpp` 可以独立、并行地编译。模块打破了这一点：导入一个模块之前，必须先编译它的接口单元，得到**二进制模块接口**（BMI，编译器对模块接口的缓存格式）；而要知道一个文件导入了什么，又得先读它。于是构建系统必须在编译之前做一次依赖扫描，再按依赖图排顺序。[[P1300R0]]（*Remember the FORTRAN*）用 Fortran 90 模块的经验提醒过委员会这一点。

扫描要快，最好只做预处理、不解析 C++。这个要求在语言里留下了几条规则。

### module 和 import 是预处理指令（P1857）

ATOM 时期的上下文关键字还不够。早先的修补把行首任何 `import` 都当关键字，会破坏 `import -> doImport();` 这样的代码。[[P1857R3]] 把 `module`、`import` 行变成真正的预处理指令，并精确规定它们何时被识别（[[cpp.module]]、[[cpp.import]]）。从此扫描器只需预处理，就能知道一个文件提供和需要哪些模块。

### 模块名不能是宏（P3034）

同样的理由，后来又补上一条：模块名的组成部分不能来自宏展开。[[P3034R1]] 在 2024 年作为缺陷报告（DR，追溯适用于旧标准的修正）通过，本机 Clang 23 已经实现：

```cpp title="macro_name.cppm" error
#define NAME foo
export module NAME;   // error: 模块名不能是对象式宏
```

### 标准之外的部分

标准不涉及文件、BMI 或编译顺序，[[lex.phases]] 只说被依赖的模块单元的源码是否需要可用由实现定义。所以其余问题在标准之外，由工具研究组 SG15 协调。最有用的成果是 [[P1689R5]]，一种描述"这个文件提供哪个模块、需要哪些模块"的 JSON 格式。它不属于标准，但 Clang（`clang-scan-deps`）、GCC 和 MSVC 都能输出，CMake 的模块支持就建立在它之上。CMake 从 3.28 起正式支持具名模块，只适用于 Ninja 和 Visual Studio 生成器，头文件单元在任何生成器下都不支持（Kitware 博客；CMake 手册 *cmake-cxxmodules(7)*）。

## 让接口和实现真正分开

模块的第二个目标是分离接口和实现：只改函数体时，导入者不必重新编译。C++20 定稿前的两份修补落实了这一点。

### 类内定义的成员函数不再隐式 inline（P1779）

传统头文件里，类内定义的成员函数隐式 inline，函数体就是接口的一部分。[[P1779R3]] 改为：只有附属于全局模块的成员函数才这样（[[class.mfct#1]]）。下面的模块用本机 Clang 23 编译后，`area` 作为强定义出现在模块的目标文件里，符号名带模块附属标记 `Square@shapes::area() const`：

<div class="compare" markdown="1">

```cpp title="shape.h（头文件）"
struct Square {
  int side;
  // 隐式 inline：每个包含者
  // 都看得到、可能内联函数体
  int area() const
  { return side * side; }
};
```

```cpp title="shapes.cppm（具名模块）"
export module shapes;
export struct Square {
  int side;
  // 不是隐式 inline：函数体
  // 只在模块的目标文件里
  int area() const
  { return side * side; }
};
```

</div>

### 接口不能暴露内部链接的实体（P1815）

如果导出的 inline 函数调用了 `static` 函数，导入者就看到了一个只属于模块内部的东西。[[P1815R2]] 引入 TU-local 实体和[[g:exposure|暴露]]的概念（[[basic.link#14]]–[[basic.link#16]]），并规定模块接口单元里这样的暴露非良构（[[basic.link#17]]）：

```cpp title="tu_local.cppm" error
export module tu;
static int helper() { return 1; }             // 内部链接：TU-local
export inline int api() { return helper(); }  // error: 暴露了 helper
```

本机 Clang 23 对此只给出 `-WTU-local-entity-exposure` 警告，没有报错。按 [[basic.link#17]] 这个程序非良构，所以 Clang 的行为满足至少一条诊断的要求，但它仍然生成了 BMI。

## import std（C++23）

C++20 有了模块，却没有模块形式的标准库，只能把标准库头文件当头文件单元导入。按库的领域拆成 `std.core`、`std.io` 等多个模块的方案（[[P0581R1]]）推迟了。[[P2412R0]] 建议 C++23 先提供一个包含整个标准库的模块，并给出了 MSVC 上的测量：Hello World 用 `#include <iostream>` 编译约 0.87 秒，用 `import std;` 约 0.08 秒。导入一个比 `<iostream>` 大得多的模块反而快了约 10 倍，因为模块只需加载一次已编译好的接口。

最终的 [[P2465R3]] 提供两个模块（[[std.modules]]）：

- `import std;` 导入命名空间 `std` 中的全部标准库内容，以及 `::operator new` 等；
- `import std.compat;` 在此之上再提供 C 头文件在全局命名空间中的名字，如 `::fopen`。

拆成两个模块，是为了借机摆脱 `<cstdio>` 是否也声明 `::printf` 这个历史包袱，同时不让现有代码迁移太难（P2465R3，"Rationale" 一节）。下面的程序在本机先用 libc++ 自带的 `std.cppm` 构建出 BMI，再编译运行，输出 `Hello, modules`：

```cpp title="hello.cpp" ok
import std;
int main() { std::println("Hello, {}", "modules"); }
```

## 为什么采用得慢

模块进入标准已有七年多，在多数项目里仍不是默认选择。原因主要在实现和工具链：

- **编译器**。微软文档称 Visual Studio 2019 16.10 起模块功能完整；CMake 文档列出的最低版本是 MSVC 工具集 14.34、Clang 16 和 GCC 14。GCC 16 的发布说明仍称模块支持是实验性的，需要 `-fmodules` 开启。
- **头文件单元**。这是合并方案里实现最弱的部分：本机 Clang 23 每次导入都给出实验性警告，CMake 不支持它。
- **BMI 不可分发**。各编译器的 BMI 格式互不兼容，还和编译器版本、编译选项绑定。库只能分发模块接口的源码，由使用者自己构建。
- **生态惯性**。多数库仍要支持没有模块的编译器，只能在头文件之外另提供一个模块包装。

具体用法和现状见 [[toolchain/modules-in-practice]]。

## 常见误解

!!! pitfall "C++20 模块就是 Modules TS"
    不是。C++20 模块来自 P1103 对 Modules TS 和 ATOM 的合并，之后又改过多次。TS 下合法的一些代码在 C++20 中不再合法，例如全局模块片段现在必须以 `module;` 开头（P1103R3 §3.4）。头文件单元、预处理指令形式的 `module`/`import`、TU-local 实体也都不在 TS 里。

!!! pitfall "import <vector>; 与 #include <vector> 等价"
    不完全等价。头文件单元被当作独立的源文件处理，导入之前定义的宏影响不到它（[[module.import]]）；`#include` 则在当前的宏环境中做文本替换。两者都会带来该头文件定义的宏。实现可以把可导入头文件的 `#include` 换成头文件单元导入（[[cpp.include]]），但这是实现定义的。

!!! pitfall "用了模块就不会有 ODR 问题"
    模块减少了违反 ODR 的机会：具名模块中声明的实体附属于该模块（[[module.unit]]），两个模块各自定义的同名非导出函数是不同的实体。但全局模块片段和头文件单元里的声明仍属于全局模块，照样受 [[basic.def.odr]] 约束。

## 时间线

| 年份 | 事件 | 文献 |
|---|---|---|
| 2005–2012 | Vandevoorde 的模块提案，六版 | [[N2073]] |
| 2012 | Clang 模块映射 | Clang 文档 |
| 2014–2018 | 微软的设计，成为 Modules TS | [[N4465]] |
| 2016 | Google 依据 Clang 部署经验要求导出宏等修改 | [[P0273R1]] |
| 2018 | ATOM | [[P0947R1]] |
| 2019 | 合并方案进入 C++20 | [[P1103R3]] |
| 2019–2020 | 依赖扫描、成员函数 ABI 隔离、TU-local 实体 | [[P1857R3]]、[[P1779R3]]、[[P1815R2]] |
| 2022 | `import std` 与 `import std.compat` 进入 C++23 | [[P2465R3]] |
| 2023 | CMake 3.28 正式支持具名模块 | Kitware 博客 |
| 2024 | 模块名不能是宏（DR） | [[P3034R1]] |

## 参考资料

- Bjarne Stroustrup. *Thriving in a Crowded and Changing World: C++ 2006–2020*. HOPL IV (2020)，§9.3.1 *Modules*。
- Daveed Vandevoorde. *Modules in C++*，[[N2073]]。
- Gabriel Dos Reis, Mark Hall, Gor Nishanov. *A Module System for C++*，[[N4465]]。
- Richard Smith, Chandler Carruth, David Jones. *Proposed modules changes from implementation and deployment experience*，[[P0273R1]]。
- Richard Smith. *Another take on Modules*，[[P0947R1]]；Richard Smith, Gabriel Dos Reis. *Merging Modules*，[[P1103R3]]。
- Michael Spencer. *Modules Dependency Discovery*，[[P1857R3]]；*Module Declarations Shouldn't be Macros*，[[P3034R1]]。
- Davis Herring. *ABI isolation for member functions*，[[P1779R3]]；*Translation-unit-local entities*，[[P1815R2]]。
- Ben Boeckel, Brad King. *Format for describing dependencies of source files*，[[P1689R5]]。
- Bjarne Stroustrup. *Minimal module support for the standard library*，[[P2412R0]]；Stephan T. Lavavej et al. *Standard Library Modules std and std.compat*，[[P2465R3]]。
- Clang 文档 *Modules*；Kitware，*import CMake; the Experiment is Over!*；CMake 手册 *cmake-cxxmodules(7)*；GCC 16 发布说明。
