---
title: 预处理指令
summary: 第 15 章导读：预处理在翻译阶段 4 完成，只处理预处理记号；本章各节讲什么、按什么顺序读；近年加入的特性（__VA_OPT__、模块指令、特性检测、#elifdef、#warning、#embed）；原来的未定义行为大多已改为非良构。
status: done
related: lex.phases, lex.pptoken, cpp.pre, cpp.replace, cpp.cond, module, topics/how-to-read-the-standard
tags: 预处理, 导读
updated: 2026-10-19
---

!!! tldr
    - 预处理是翻译阶段 4：执行指令、展开宏、执行 `_Pragma`。它操作的是预处理记号，看不到关键字、类型和作用域。
    - 一行是不是指令，在阶段 4 开始时按词法就确定了，宏展开既造不出指令，也消不掉指令。
    - 本章最需要细读的是 [[cpp.pre]]（什么是指令）、[[cpp.replace]] 和 [[cpp.rescan]]（宏替换算法）、[[cpp.cond]]（`#if` 怎样求值）。
    - C++20 起，`import`、`module`、`export` 开头的某些行也是预处理指令，目的是让构建系统只靠预处理就能扫描出模块依赖。
    - 本章原来大量的未定义行为，在当前草案中大多改成了非良构或 IFNDR。

第 15 章 [cpp] 规定预处理器：条件编译、文件包含、资源嵌入、宏、模块指令、行控制、pragma 和预定义宏。它与 C 标准的预处理一节（C23 6.10）基本逐句对应，C 和 C++ 共享同一套预处理器。

## 预处理在翻译阶段中的位置

按 [[lex.phases]]，源文件依次经过 8 个翻译阶段，与本章有关的是前 7 个：

| 阶段 | 与本章的关系 |
|---|---|
| 1–2 | 解码源文件，拼接以 `\` 结尾的行。指令以拼接后的逻辑行为单位。 |
| 3 | 切分为预处理记号和空白，每个注释变成一个空格。紧跟在 `#include`、`#embed`、`import` 等之后的 `<...>` 被识别为 *header-name*（[[lex.pptoken]]）。 |
| 4 | 本章的全部内容：执行指令、展开宏、执行 `_Pragma`。`#include` 进来的文件递归地经过阶段 1–4。阶段结束时所有指令都已删除。 |
| 5–6 | 拼接相邻的字符串字面量；预处理记号转换为记号，关键字从这里才存在。 |
| 7 | 语法和语义分析。模块指令在这里成为声明。 |

预处理器的几条基本性质都可以从这张表推出来：

- 预处理器看不到关键字和类型。`#if sizeof(int) == 4` 不能工作；`#if new` 合法，结果为 0（[[cpp.cond]]）。
- 预处理器看不到注释。注释在阶段 3 已经是空格，宏也拼不出注释（[[cpp.concat]]）。
- 字符串拼接在预处理之后。`#include "a" "b"` 和 `_Pragma("a" "b")` 都不行（[[cpp.include]]、[[cpp.pragma.op]]）。
- 宏展开不能制造指令，一行是不是指令在阶段 4 开始时就已确定（[[cpp.pre]]）。

## 本章结构与阅读顺序

| 小节 | 内容 | 本站页面 |
|---|---|---|
| 15.1 | 总文法；什么是指令；有条件支持的指令；被跳过的组 | [[cpp.pre]] |
| 15.2 | `#if` 家族；`defined`、`__has_include`、`__has_embed`、`__has_cpp_attribute` | [[cpp.cond]] |
| 15.3 | `#include` 与头文件搜索 | [[cpp.include]] |
| 15.4 | {{c++26}} `#embed` 及其参数 | [[cpp.embed]] |
| 15.5–15.6 | 模块指令；导入头文件单元时的宏 | [[cpp.module]] |
| 15.7 | 宏的定义、实参替换、`__VA_ARGS__`、`__VA_OPT__`、`#`、`##` | [[cpp.replace]] |
| 15.7.5 | 重新扫描与递归抑制 | [[cpp.rescan]] |
| 15.8–15.11、15.13 | `#line`、`#error`、`#warning`、`#pragma`、空指令、`_Pragma` | [[cpp.line]] |
| 15.12 | 预定义宏、`__cplusplus`、特性测试宏 | [[cpp.predefined]] |

建议按下面的顺序读：

1. [[cpp.pre]]：哪些行是指令。C++20 之后，这不再只是以 `#` 开头的行。
2. [[cpp.replace]] 和 [[cpp.rescan]]：宏替换的完整算法。为什么字符串化一个宏的值要套两层宏，`__VA_OPT__` 解决了什么问题，宏为什么不能递归，答案都在这里。
3. [[cpp.cond]]：`#if` 的求值规则，未定义的标识符当作 0，运算在 `intmax_t` 中进行。
4. [[cpp.include]] 和 [[cpp.embed]]：两种把外部内容带进来的机制，搜索规则几乎相同。
5. [[cpp.module]]：模块为什么要改动预处理器。
6. [[cpp.line]]、[[cpp.predefined]]：查阅即可。

## 近年的变化

C++98 的预处理器几乎就是 C89 的预处理器。之后的变化主要有三个方向。

与 C 保持同步。C++11 吸收了 C99 的预处理改进（[[N1653]]）：可变参数宏、`_Pragma`、空的宏实参。C++23 同步了 C23 的 `#elifdef`、`#elifndef`（[[P2334R1]]）和 `#warning`（[[P2437R1]]），C++26 同步了 `#embed`（[[P1967R14]]）。

特性检测。C++17 加入 `__has_include`（[[P0061R1]]）；C++20 把 `__has_cpp_attribute` 和 `__cpp_xxx` 特性测试宏写进标准正文（[[P0941R2]]）；C++26 加入 `__has_embed`。

模块。C++20 让某些以 `import`、`module`、`export` 开头的行成为预处理指令（[[P1703R1]]、[[P1857R3]]），并规定导入头文件单元时怎样带入宏。C++26 禁止模块名来自宏展开（[[P3034R1]]）。这些改动的目的都是让构建系统只做预处理就能扫描出模块依赖。

此外，C++20 的 `__VA_OPT__`（[[P0306R4]]、[[P1042R1]]）解决了可变参数为空时多出一个逗号的问题。

| 版本 | 新增 |
|---|---|
| C++11 | 可变参数宏、`__VA_ARGS__`、`_Pragma`、空实参、`__STDC_HOSTED__`、`__STDCPP_THREADS__` |
| C++17 | `__has_include`、`__STDCPP_DEFAULT_NEW_ALIGNMENT__` |
| C++20 | `__VA_OPT__`、`__has_cpp_attribute`、特性测试宏、模块指令、头文件单元、`#include` 可翻译为 `import` |
| C++23 | `#elifdef`、`#elifndef`、`#warning`、扩展浮点类型的宏 |
| C++26 | `#embed`、`__has_embed`、`__STDC_EMBED_*__`、模块名不得来自宏 |

## 未定义行为改为非良构

预处理一节原来有很多未定义行为：`##` 拼出无效的记号，宏实参中出现指令，宏展开产生 `defined`，重定义预定义宏，`#line` 的行号超出范围。这些源于早年各家预处理器实现的分歧，标准化时只好都定为 UB。

预处理完全在编译期进行，这些违规都能被发现。C++23 之后的新措辞把它们几乎都改写了：

| 情形 | C++23 及以前 | 当前草案 |
|---|---|---|
| `##` 的结果不是有效的预处理记号 | UB | 非良构（[[cpp.concat#3]]） |
| `#` 的结果不是有效的字符串字面量 | UB | 非良构（[[cpp.stringize#2]]） |
| 宏实参中出现指令 | UB | 非良构（[[cpp.replace.general#14]]） |
| `#if` 中的宏展开产生 `defined` | UB | {{ifndr}}（[[cpp.cond#9]]） |
| `defined` 的写法不对 | UB | {{ifndr}}（[[cpp.cond#9]]） |
| 宏形式的 `#include` 拼不成 *header-name* | UB | {{ifndr}}（[[cpp.include#7]]） |
| `#line` 的行号超出 `[1, 2147483647]` | UB | 有条件支持（[[cpp.line#3]]） |
| `#define` 或 `#undef` 预定义宏 | UB | 非良构（[[cpp.predefined#4]]） |

保留为 IFNDR 的几处，是主流实现之间仍有分歧的地方。

非良构只要求诊断，警告也算。Clang 和 GCC 对上表的多数情形只给警告（如 `-Wexpansion-to-defined`、`-Wembedded-directive`、`-Wbuiltin-macro-redefined`），措辞里还写着 undefined behavior，那是旧标准的说法。

## 实现

!!! impl
    - GCC 的预处理器是 `libcpp`，集成在 `cc1plus` 里；`gcc -E` 只运行预处理。
    - Clang 的预处理与词法分析交织进行：语法分析器每次向预处理器要下一个记号，宏按需展开。每个记号都记录了展开位置和拼写位置，所以诊断能显示 expanded from macro 的完整链条。
    - MSVC 长期使用一个与标准有不少分歧的传统预处理器，`/Zc:preprocessor` 启用符合标准的新预处理器。
    - `clang-scan-deps` 只运行预处理来扫描模块依赖（[[cpp.module]]）。`mcpp`、Boost.Wave 是独立的预处理器实现，常用来检验边界情形。
