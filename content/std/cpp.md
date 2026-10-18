---
title: 预处理指令
summary: 第 15 章导读：预处理在翻译阶段 3–4 中的位置，本章各节的分工与阅读顺序，近年的变化（__VA_OPT__、模块指令、__has_include/__has_cpp_attribute、#elifdef/#elifndef、#warning、#embed），以及本章 UB 大量改为非良构/IFNDR 的趋势。
status: draft
related: lex.phases, lex.pptoken, cpp.pre, cpp.replace, cpp.cond, module, topics/how-to-read-the-standard
tags: 预处理, 导读
updated: 2026-10-18
---

第 15 章 [cpp] 规定的是**预处理器**：条件编译、文件包含、资源嵌入、宏、模块指令、行控制、pragma 和预定义宏。它与 C 标准的预处理章节一脉相承，绝大部分文字可以逐句对应到 C 标准的第 6.10 节——这既是它的优点（C 与 C++ 共享同一个预处理器），也是它的特点：这一章在 C++ 标准中显得"格格不入"，没有类型、没有作用域、没有重载，只有**预处理记号**和**宏**。

## 预处理在翻译阶段中的位置

按 [[lex.phases]]，一个源文件经过 8 个翻译阶段：

| 阶段 | 与本章的关系 |
|---|---|
| 1–2 | 解码、行拼接。指令以**逻辑源行**为单位，正是因为阶段 2 已经把 `\`+换行拼掉了。 |
| 3 | 切分为预处理记号与空白，注释变成一个空格。*header-name* 在 `#include`/`#embed`/`import`/`__has_include`/`__has_embed` 之后被特殊识别（[[lex.pptoken#5]]）。 |
| **4** | **本章的全部内容**：执行指令、展开宏、执行 `_Pragma`；`#include` 的文件递归地经历阶段 1–4。阶段 4 结束时所有指令被删除。 |
| 5–6 | 字符串字面量拼接；预处理记号转换为记号——关键字从这里才存在。 |
| 7 | 语法与语义分析。被替换为 *module-keyword*/*import-keyword* 的模块指令在这里成为声明。 |

由此可以推出预处理器的几个基本性质，它们会在本章反复出现：

- **预处理器看不到关键字和类型**。`#if sizeof(int) == 4` 不能工作；`#if new` 合法且为 0（[[cpp.cond]]）。
- **预处理器看不到注释**。注释在阶段 3 已经是空格，宏无法生成注释（[[cpp.concat]]）。
- **字符串拼接在预处理之后**。`#include "a" "b"`、`_Pragma("a" "b")` 都不行（[[cpp.include]]、[[cpp.pragma.op]]）。
- **宏展开不能制造指令**。是不是指令在阶段 4 开始时就已确定（[[cpp.pre]]）。

## 本章结构

| 小节 | 内容 | 本站页面 |
|---|---|---|
| 15.1 [[cpp.pre]] | 总文法；什么是指令；条件支持的指令；跳过组；指令内空白 | [[cpp.pre]] |
| 15.2 [[cpp.cond]] | `#if` 家族；`defined`、`__has_include`、`__has_embed`、`__has_cpp_attribute` | [[cpp.cond]] |
| 15.3 [[cpp.include]] | `#include`；头文件搜索与源文件搜索；include 翻译 | [[cpp.include]] |
| 15.4 [[cpp.embed]] | `#embed` 及其五个参数 {{c++26}} | [[cpp.embed]] |
| 15.5 [[cpp.module]] | 模块指令 | [[cpp.module]] |
| 15.6 [[cpp.import]] | 头文件单元导入；宏的定义点与活跃性 | [[cpp.module]] |
| 15.7 [[cpp.replace]] | 宏的定义、实参替换、`__VA_ARGS__`/`__VA_OPT__`、`#`、`##`、作用域 | [[cpp.replace]] |
| 15.7.5 [[cpp.rescan]] | 重新扫描、"涂蓝"与递归抑制 | [[cpp.rescan]] |
| 15.8 [[cpp.line]] | `#line` | [[cpp.line]] |
| 15.9 [[cpp.error]] | `#error`、`#warning` | [[cpp.line]] |
| 15.10 [[cpp.pragma]] | `#pragma` | [[cpp.line]] |
| 15.11 [[cpp.null]] | 空指令 `#` | [[cpp.line]] |
| 15.12 [[cpp.predefined]] | 预定义宏、`__cplusplus`、特性测试宏表 | [[cpp.predefined]] |
| 15.13 [[cpp.pragma.op]] | `_Pragma` 运算符 | [[cpp.line]] |

## 推荐阅读顺序

1. [[cpp.pre]]：先弄清"哪些行是指令"。C++20 之后这不再是"以 `#` 开头的行"这么简单。
2. [[cpp.replace]] 与 [[cpp.rescan]]：宏替换的完整算法。这是本章最难、也最常被问到的部分——为什么需要两层宏才能字符串化宏的值、`__VA_OPT__` 解决了什么、宏为什么不能递归。
3. [[cpp.cond]]：`#if` 的求值模型——标识符变 0、在 `intmax_t` 中运算。
4. [[cpp.include]] 与 [[cpp.embed]]：两种"把外部内容拿进来"的机制，搜索模型几乎相同。
5. [[cpp.module]]：理解模块为什么要"侵入"预处理器——为了依赖扫描。
6. [[cpp.line]]、[[cpp.predefined]]：查阅型内容。

## 近年的变化

C++98 的预处理器几乎就是 C89 的预处理器。之后的演进可以分为三条线：

**与 C 同步。** C++11 一次性吸收了 C99 的预处理改进（[[N1653]]）：可变参数宏、`_Pragma`、空宏实参与 placemarker、`intmax_t` 算术。C++23 又同步了 C23 的 `#elifdef`/`#elifndef`（[[P2334R1]]）和 `#warning`（[[P2437R1]]）；C++26 同步了 `#embed`（[[P1967R14]]）。

**特性检测。** C++17 的 `__has_include`（[[P0061R1]]）；C++20 把 `__has_cpp_attribute` 和全部 `__cpp_xxx` 特性测试宏从 SD-6 写进标准正文（[[P0941R2]]）；C++26 的 `__has_embed`。

**模块。** C++20 让 `import`/`module`/`export` 开头的某些行成为预处理指令（[[P1703R1]]、[[P1857R3]]），引入头文件单元的宏导入和"活跃宏定义"的概念；C++26 禁止模块名来自宏（[[P3034R1]]）。目的都是让构建系统只做预处理就能扫描出模块依赖。

此外还有 C++20 的 `__VA_OPT__`（[[P0306R4]]、[[P1042R1]]）——终于以标准方式解决了可变参数宏的"多余逗号"问题。

| 版本 | 本章新增 |
|---|---|
| C++11 | 可变参数宏、`__VA_ARGS__`、`_Pragma`、空实参、`__STDC_HOSTED__`、`__STDCPP_THREADS__` |
| C++17 | `__has_include`、`__STDCPP_DEFAULT_NEW_ALIGNMENT__` |
| C++20 | `__VA_OPT__`、`__has_cpp_attribute`、特性测试宏入标准、模块指令、头文件单元、`#include` 可翻译为 `import` |
| C++23 | `#elifdef`、`#elifndef`、`#warning`、扩展浮点类型宏 |
| C++26 | `#embed`、`__has_embed`、`__STDC_EMBED_*__`；模块名不得来自宏 {{c++26}} |

## 本章的"惩罚"分布：UB 正在消失

传统上，预处理章节布满了未定义行为：`##` 拼出无效记号、宏实参中出现指令、宏展开产生 `defined`、重定义预定义宏、`#line` 超出范围、`#include` 拼不出合法的头文件名……这些都源于 1980 年代各家预处理器实现的分歧，标准化时只好全部定为 UB。

当前草案把它们**几乎全部**改写了：

| 情形 | C++23 及以前 | 当前草案 |
|---|---|---|
| `##` 结果不是合法预处理记号 | UB | 非良构（[[cpp.concat#3]]） |
| `#` 结果不是合法字符串字面量 | UB | 非良构（[[cpp.stringize#2]]） |
| 宏实参中有指令 | UB | 非良构（[[cpp.replace.general#14]]） |
| `#if` 中宏展开产生 `defined` | UB | {{ifndr}}（[[cpp.cond#9]]） |
| `defined` 形式不对 | UB | {{ifndr}}（[[cpp.cond#9]]） |
| 宏形式 `#include` 拼不成 header-name | UB | {{ifndr}}（[[cpp.include#7]]） |
| `#line` 数字超出 `[1, 2147483647]` | UB | 有条件支持（[[cpp.line#3]]） |
| `#define`/`#undef` 预定义宏 | UB | 非良构（[[cpp.predefined#4]]） |

这是"预处理不应有 UB"这一方向的努力结果：预处理在编译期完成，不存在"运行时才知道"的问题，所有违规都**可以**被诊断。保留 IFNDR 的两三处，是因为主流实现之间仍有分歧、而标准不愿强迫某一方改变。

需要注意的是，"非良构"只要求**诊断**，而**警告**也算诊断。Clang/GCC 对上表中的多数情形只给警告（如 `-Wexpansion-to-defined`、`-Wembedded-directive`、`-Wbuiltin-macro-redefined`），并且警告措辞里还在说 "undefined behavior"——那是旧标准的说法。

## 实现：一个预处理器长什么样

!!! impl
    - **GCC**：预处理器是 `libcpp`，与前端集成在 `cc1plus` 中；`gcc -E` 只运行它。
    - **Clang**：`Lexer` + `Preprocessor` 类，预处理与词法分析交织进行，Parser 每次向 Preprocessor 要下一个记号（"pull" 模型），所以宏展开是按需的、增量的。Clang 为每个记号保留了"展开位置"与"拼写位置"两种源位置，所以诊断能显示 "expanded from macro ..." 的完整链条。
    - **MSVC**：长期使用一个与标准有诸多分歧的"传统"预处理器；`/Zc:preprocessor`（VS 2019 起）启用新的、符合标准的预处理器。
    - **独立工具**：`clang-scan-deps` 只运行预处理来扫描依赖（[[cpp.module]]）；`mcpp`、`Boost.Wave` 是独立的符合标准的预处理器实现，常被用来检验边角情形。

## 小结

!!! summary
    - 预处理 = 翻译阶段 4：执行指令、展开宏、执行 `_Pragma`，操作对象是预处理记号，没有关键字与类型。
    - 本章的核心是 [[cpp.pre]]（什么是指令）、[[cpp.replace]]/[[cpp.rescan]]（宏替换算法）和 [[cpp.cond]]（`#if` 求值）。
    - 近年变化：`__VA_OPT__`、模块指令、特性检测（`__has_include`、`__has_cpp_attribute`、`__has_embed`、`__cpp_xxx`）、`#elifdef`/`#elifndef`、`#warning`、`#embed`。
    - 本章的 UB 正在被系统地改为非良构或 IFNDR。
