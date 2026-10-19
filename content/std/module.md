---
title: 模块
summary: 第 10 章导读：C++20 模块为什么出现，它解决了 #include 模型的哪些问题，以及模块单元、分区、全局模块、附属、导出、导入、可达性等一整套词汇之间的关系。
status: done
since: c++20
papers: P1103R3, P1815R2, P2465R3
related: module.unit, module.interface, module.import, module.global.frag, module.private.frag, module.context, module.reach, basic.link, basic.def.odr, toolchain/modules-in-practice
tags: 导读, 模块
updated: 2026-10-17
---

第 10 章 [module] 是 C++20 加入的一整章，篇幅不长（七节），但它改写了 C++ 程序由多个翻译单元拼接而成的基本模型。读懂这一章需要同时理解两件事：模块是一种新的翻译单元组织方式（谁导入谁、谁能看见谁）；模块还改变了同一实体的判定（附属于哪个模块、链接是什么）。后者散落在 [[basic.link]]、[[basic.def.odr]]、[[basic.lookup]] 里，本章主要讲前者。

阅读前需要了解 [[lex.phases]]（翻译阶段、翻译单元的形成）、[[basic.link]]（四种链接、同一实体、TU-local 与暴露）和 [[basic.def.odr]]（ODR）。

## 为什么需要模块

`#include` 是 1970 年代的文本粘贴机制：预处理器把头文件的内容原样插入到当前位置，然后编译器把结果当作一个巨大的源文件处理。这个模型有三个根本问题，模块分别给出了回答。

### 问题一：宏与上下文泄漏

头文件的含义依赖于包含它之前定义了哪些宏，头文件中定义的宏又会泄漏给包含者。`#define min(a,b) ...` 能让 `std::min` 无法使用；`#include` 的顺序能改变程序的含义；同一个头文件在两个 TU 中可以因为宏不同而得到不同的记号序列，这正是 ODR 违规（[[basic.def.odr#16]]）最常见的来源。

模块切断了这条通道：

- 导入具名模块不会带入任何宏（[[module.import#5]] Note 4、[[module.import#7]] Note 6）。模块内部 `#define` 的东西只在那个模块单元内有效。
- 导入者在 `import` 之前定义的宏也影响不到模块。模块单元是独立翻译的，导入的是它已经翻译好的结果（概念上是第 7 阶段的记号序列，实现上是二进制模块接口文件），而不是它的源文本。

```cpp title="counter.cppm"
module;
#include <cstddef>
export module counter;
#define COUNTER_MAX 100            // 只在本 TU 中有效
export class Counter {
  std::size_t n = 0;
public:
  bool tick() { return ++n < COUNTER_MAX; }
  std::size_t value() const { return n; }
};
```

```cpp title="main.cpp" ok
#define value oops                 // 不会影响 counter 模块中的 value
import counter;
#undef value
#ifdef COUNTER_MAX
#  error "macro leaked"            // 不会触发：具名模块不导出宏
#endif
int main() {
  Counter c;
  while (c.tick()) {}
  return c.value() == 100 ? 0 : 1;
}
```

需要宏的场合（例如配置开关、`assert`）仍然可以用 `#include`，或者用头文件单元（`import "config.h";`），它是唯一会带入宏的导入（[[cpp.import]]）。

### 问题二：重复解析，构建吞吐量差

一个包含 `<vector>`、`<string>`、`<algorithm>` 的 `.cpp` 文件，编译器要重新解析几万行标准库代码；一个项目有一千个 `.cpp`，就重复一千遍。预编译头（PCH）缓解了这个问题，但它要求所有 TU 共享同一段前缀，语义上也仍是文本包含。

模块接口单元**只翻译一次**，产出一个二进制模块接口（BMI，Clang 叫 `.pcm`，GCC 叫 `.gcm`，MSVC 叫 `.ifc`），导入者直接读取这个序列化的 AST。标准本身不提 BMI，只说导入使被导入 TU 中的声明可达和可见；但模块的语义（不受导入者的宏影响、与导入顺序无关）正是为了让这种实现成为可能而设计的。实测数据见 [[toolchain/modules-in-practice]]。

### 问题三：ODR 与名字的归属

在头文件模型下，如果两个库都定义了 `detail::helper()`，链接时要么符号冲突，要么更糟：链接器悄悄选一个，属于 IFNDR。所有命名空间作用域的非 `static` 名字都挤在同一个全局空间里。

模块引入了**附属**（attachment）：每个声明附属于某个模块（[[module.unit#7]]），附属于不同模块的同名实体是不同的实体（[[basic.link#8]] 的 ¶8.3）。模块中未导出的名字具有模块链接，外界无法指代它。实现上，Clang/GCC 在符号名中编码模块名（Itanium ABI 的 `W` 修饰，如 `_ZW1M6helperv`），所以在链接器看来，两个模块的同名 `helper` 也是两个符号。

!!! note "模块不是什么"
    - 模块不是命名空间。`export module foo;` 不会创建 `foo::` 作用域，名字仍然放在你写的命名空间里。模块管的是可见性与所有权，命名空间管的是名字的作用域，两者正交。
    - 模块也不是封装或访问控制机制。未导出的声明对导入者不可见（名字查找找不到），但仍然可能可达（类型定义、默认实参等语义属性仍然起作用，见 [[module.reach]]）。
    - 模块不规定文件名、目录结构或构建方式。`.cppm`/`.ixx`/`.mpp` 等扩展名是各工具链的约定。

## 本章地图

| 节 | 条款 | 回答的问题 |
|---|---|---|
| 10.1 | [[module.unit]] | 什么是模块单元；接口单元/实现单元/分区的区别；模块名的保留规则；管辖范围（purview）；全局模块；声明附属于哪个模块 |
| 10.2 | [[module.interface]] | `export` 能用在哪里；什么样的声明能被导出；导出的重声明规则；导出与链接的关系 |
| 10.3 | [[module.import]] | `import` 导入哪些 TU；分区导入、头文件单元；`export import` 的传递性；接口依赖与禁止循环 |
| 10.4 | [[module.global.frag]] | `module;` 之后的全局模块片段用来做什么；decl-reachable 与被丢弃的声明 |
| 10.5 | [[module.private.frag]] | `module :private;`：单文件模块如何把实现细节藏起来 |
| 10.6 | [[module.context]] | 模板跨模块实例化时到哪里查找，即实例化语境 |
| 10.7 | [[module.reach]] | 可达的 TU、可达的声明；可达与可见的区别；语义属性如何累积 |

## 词汇总览

模块章节的术语密度很高，下面把它们串起来。

### 模块单元的种类

一个 TU 如果含有 *module-declaration*（`export module M;` 或 `module M;` 等），就是**模块单元**，否则是普通 TU（属于全局模块）。模块单元按两个维度分类：

| | 无分区名 | 有分区名 `:P` |
|---|---|---|
| 接口单元（`export module …`） | 主模块接口单元（primary module interface unit）：每个模块恰好一个 | 接口分区：主接口单元必须直接或间接地 `export import` 它 |
| 实现单元（`module …`） | 普通实现单元：隐式导入主接口单元，不能被导入 | 实现分区：本模块的其他单元可以 `import` 它，不对外 |

```cpp title="geo.cppm（主模块接口单元）"
export module geo;
export import :shapes;     // 接口分区，必须被主接口（直接或间接）导出
export double area_sum();
```

```cpp title="geo-shapes.cppm（接口分区）"
export module geo:shapes;
export struct Circle { double r; };
```

```cpp title="geo-detail.cppm（实现分区）"
module geo:detail;
constexpr double pi = 3.14159265358979;
```

```cpp title="geo.cpp（实现单元）"
module geo;                // 隐式 import geo;
import :detail;            // 实现分区：只在模块内部导入
double area_sum() { return pi * Circle{1}.r * Circle{1}.r; }
```

### 模块与全局模块

- [[g:named-module|具名模块]]（named module）：所有同名模块单元的集合。
- [[g:global-module|全局模块]]（global module）：所有非模块 TU，加上所有模块单元的全局模块片段（`module;` 与 `export module M;` 之间的部分），以及所有头文件单元的内容（它们附属于全局模块）。全局模块没有名字，也没有接口单元。
- [[g:attached|附属]]（attached）：每个声明附属于一个模块。一般规则是声明出现在哪个模块的管辖范围内，就附属于哪个模块；例外是命名空间、类型别名、`extern "C++"`/`extern "C"` 块中的声明等，它们附属于全局模块（[[module.unit#7]]）。附属决定了同一实体的判定和符号修饰。

### 导出、导入、可见、可达

这一组是整章最容易混淆的概念：

| 概念 | 含义 | 由谁决定 | 影响什么 |
|---|---|---|---|
| 导出（exported） | 声明在 *export-declaration* 中（或在头文件单元中） | [[module.interface]] | 导入者的名字查找能否找到它；链接（导出的名字永远不具有模块链接） |
| 导入（imports） | `import` 使当前 TU 导入一组 TU，可能传递 | [[module.import]] | 哪些 TU 的导出声明可以被查找到 |
| 可见（visible）| 不是标准正式术语，指名字查找能找到。正式表述是声明先于（precedes）程序点 | [[basic.lookup#2]] | 能否写出这个名字 |
| 可达（reachable） | 声明的语义属性（定义、完整性、默认实参……）在某点生效 | [[module.reach]] | 能否使用它的性质（如 `sizeof`、成员访问） |

一个经典的例子：模块导出类型别名 `export using Y = X;`，`X` 本身未导出。导入者写 `X x;` 会失败（`X` 不可见），写 `Y y;` 却能成功（`X` 的定义可达）。详见 [[module.reach#6]]。

```text
            导入 (import)
  当前 TU ─────────────────▶ 被导入的 TU 集合（含 export import 传递的）
     │                              │
     │  名字查找：只看"导出的"声明   │  可达性：看被导入 TU 中的所有声明
     ▼                              ▼    （未丢弃、不在私有片段中）
   可见  ⊂  可达  ⊂  （必然可达 ∪ 实现可选择的额外可达 TU）
```

### 两种特殊片段

```cpp title="一个完整的模块接口单元的形状"
module;                   // ┐ 全局模块片段：只能有预处理指令（#include 等）
#include <cstdio>         // ┘ 其中的声明附属于全局模块；未被使用的会被"丢弃"
export module hello;      // ┐
export void greet();      // │ 模块管辖范围（purview）
                          // │
module :private;          // │ ┐ 私有模块片段：只在主接口单元中、且模块只有这一个单元时可用
void greet() { std::puts("hi"); }  // ┘ 对导入者不可达
```

## 本章与其他章节的关系

模块的规则有很多分布在本章以外，按主题整理如下：

| 主题 | 位置 |
|---|---|
| 模块链接、附属与同一实体 | [[basic.link#4]]、[[basic.link#8]]、[[basic.link#10]] |
| TU-local 实体与暴露 | [[basic.link#14]]–[[basic.link#18]] |
| inline 函数在模块中必须在同一定义域中定义 | [[dcl.inline#5]]、[[basic.def.odr]] |
| 类内定义的成员函数在具名模块中不再隐式 inline | [[class.mfct#1]] |
| 名字查找中“先于”的定义 | [[basic.lookup#2]] |
| ADL 找到被导出但不可见的函数 | [[basic.lookup.argdep#4]] |
| 实例化点 | [[temp.point]] |
| `module`/`import`/`export` 作为预处理指令 | [[cpp.module]]、[[cpp.import]]、[[cpp.pre]] |
| 标准库模块 `std` 与 `std.compat` | [[std.modules]] |

## 历史与演进

!!! history "从 Modules TS 到 C++26"
    - 模块的设计讨论持续了十多年，Clang modules（基于 module map 的头文件模块）和 MSVC 的早期实现都是先行者。Modules TS 于 2018 年发布。
    - C++20：[[P1103R3]]（"Merging Modules"）把 Modules TS 与 Clang 方面的 ATOM 提案合并进标准，引入全局模块片段、分区、头文件单元、宏的导入规则等。之后的一系列提案修补了细节：[[P1815R2]] 引入 TU-local 与暴露；[[P1779R3]] 规定具名模块中类内定义的成员函数不再隐式 inline；[[P1857R3]] 把 `module`/`import` 改造成构建系统可以低成本扫描的预处理指令。
    - C++23：[[P2465R3]] 引入标准库模块 `std` 和 `std.compat`。[[P2615R1]]（"Meaningful exports"）作为缺陷报告收紧了 `export` 能修饰的声明（如禁止导出偏特化）。
    - C++26：模块声明中不得用宏展开出模块名（[[cpp.module]]）。

## 小结

| 要点 | 说明 |
|---|---|
| 模块单元 | 含 *module-declaration* 的 TU；分接口/实现 × 有无分区四种 |
| 全局模块 | 所有非模块 TU + 所有全局模块片段 + 头文件单元 |
| 附属 | 决定同一实体与符号；一般随管辖范围，命名空间/别名/语言链接块例外 |
| 导出 | 让导入者的名字查找能找到；导出的名字不会有模块链接 |
| 导入 | 不带宏（头文件单元除外）；`export import` 传递 |
| 可见 vs 可达 | 能写出名字 vs 能用到它的定义/语义属性 |
| 两个片段 | 全局模块片段收容 `#include`；私有模块片段隐藏单文件模块的实现 |
