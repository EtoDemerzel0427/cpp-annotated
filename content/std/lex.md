---
title: 词法约定
summary: 第 5 章导读：源文件如何被切成预处理记号、再变成记号；字符集、标识符、关键字和各种字面量的词法形式与类型。
status: draft
related: lex.phases, lex.pptoken, lex.literal, cpp, topics/how-to-read-the-standard
tags: 词法, 导读
updated: 2026-10-17
---

第 5 章 [lex] 回答的问题是：一串字节怎样变成编译器能做语法分析的记号序列，每个记号又是什么。它是标准中最底层的一章，许多看似奇怪的现象都源于这里：`x+++++y` 为什么编译不过，`-2147483648` 为什么不是 `int`，`u8"..."` 为什么不能传给 `const char*`，`"\xA" "B"` 为什么不是 `"\xAB"`。

对 language lawyer 而言，本章有两个用处。

1. 阶段模型（[[lex.phases]]）是推理某条规则何时生效的基础。预处理（第 15 章 [[cpp]]）、模板实例化（[[temp.inst]]）、链接（[[basic.link]]）都挂在这条时间轴上。
2. 字面量的类型和值（[[lex.literal]]）决定了重载决议、模板实参推导和常量求值的输入。表达式那一章（[[expr.prim.literal]]）只说字面量的类型由第 5 章确定。

## 本章结构

| 小节 | 内容 | 本站页面 |
|---|---|---|
| 5.1 [[lex.separate]] | 源文件、预处理翻译单元、分别翻译 | [[lex.separate]] |
| 5.2 [[lex.phases]] | 8 个翻译阶段 | [[lex.phases]] |
| 5.3 [[lex.char]] | 翻译字符集、基本字符集、字面量编码、UCN | [[lex.char]] |
| 5.4 [[lex.comment]] | 注释 | [[lex.pptoken]] |
| 5.5 [[lex.pptoken]] | 预处理记号、最长匹配规则 | [[lex.pptoken]] |
| 5.6 [[lex.header]] | 头文件名 | [[lex.pptoken]] |
| 5.7 [[lex.ppnumber]] | 预处理数字 | [[lex.pptoken]] |
| 5.8 [[lex.operators]] | 运算符与标点 | [[lex.pptoken]] |
| 5.9 [[lex.digraph]] | 替代记号（双字符组、`and`/`or` …） | [[lex.digraph]] |
| 5.10 [[lex.token]] | 记号的六个种类 | [[lex.pptoken]] |
| 5.11 [[lex.name]] | 标识符、Unicode、保留标识符、特殊含义标识符 | [[lex.name]] |
| 5.12 [[lex.key]] | 关键字 | [[lex.key]] |
| 5.13 [[lex.literal]] | 字面量总览、布尔与指针字面量 | [[lex.literal]] |
| 5.13.2 [[lex.icon]] | 整数字面量 | [[lex.icon]] |
| 5.13.3 [[lex.ccon]] | 字符字面量、转义序列 | [[lex.ccon]] |
| 5.13.4 [[lex.fcon]] | 浮点字面量 | [[lex.fcon]] |
| 5.13.5–6 [[lex.string]] | 字符串字面量、原始字符串、拼接、不求值字符串 | [[lex.string]] |
| 5.13.9 [[lex.ext]] | 用户定义字面量 | [[lex.ext]] |

## 推荐阅读顺序

1. 先读 [[lex.phases]]，建立时间轴。
2. 再读 [[lex.char]]，弄清翻译字符集（源码里的字符是什么）与字面量编码（字面量在运行时是什么字节）是两回事，这是 C++23 字符集重构的核心。
3. 然后读 [[lex.pptoken]]，了解最长匹配原则及其三条例外。
4. 字面量各页可按需查阅；[[lex.icon]] 的类型表和 [[lex.string]] 的拼接规则最常被问到。

## 两套记号

本章最容易混淆的一点是存在两种记号。

| | 预处理记号（preprocessing token） | 记号（token） |
|---|---|---|
| 存在于 | 阶段 3–6 | 阶段 6 之后 |
| 种类 | header-name、import/module/export 占位记号、identifier、pp-number、字符/字符串字面量、预处理运算符或标点、"其他单个字符" | identifier、keyword、literal、header-name、operator-or-punctuator |
| 关键字 | 不存在，都是 identifier | 存在 |
| 数字 | pp-number，无类型无值 | integer-literal / floating-point-literal，有类型和值 |
| 定义于 | [[lex.pptoken]] | [[lex.token]] |

预处理器（第 15 章）只操作前者；语法（附录 A 的文法以及各章）只操作后者。

## 本章违规的后果分布

本章的违规大多是非良构（必须诊断），少数例外值得记住：

- 使用保留标识符（`__x`、`_Upper`、全局 `_lower`）：{{ifndr}}（[[lex.name#4]]）。
- 声明以保留字面量后缀（不以 `_` 开头）为名的字面量运算符：{{ifndr}}（[[over.literal#1]]）。
- 多字符字面量、条件转义序列（如 `'\q'`）、头文件名中的 `'`、`\`、`//`、`/*`：有条件支持（conditionally-supported），值或语义由实现定义。
- 修改字符串字面量对象：{{ub}}（[[lex.string#9]] 的注 5，规范依据是 [[dcl.type.cv]] 中修改 const 对象是 UB 的规定）。
- 同一字符串字面量的多次求值是否得到同一对象：{{unspec}}。

C++26 的 [[P2621R2]] 把本章原有的几处 UB（未闭合的 `'`/`"`、行拼接形成 UCN 等）改成了非良构或合法，所以当前草案的词法部分几乎不再有 UB。

## 版本速览

| 版本 | 本章的重要变化 |
|---|---|
| C++11 | 原始字符串、`u8`/`u`/`U` 前缀、`char16_t`/`char32_t`、用户定义字面量、`nullptr`、`long long`、`>>` 闭合模板（[[temp.names]]） |
| C++14 | 二进制字面量 `0b`、数字分隔符 `'` |
| C++17 | 删除三字符组、十六进制浮点字面量、`u8` 字符字面量 |
| C++20 | `char8_t`（`u8` 字面量类型改变）、`<=>`、`import`/`module` 的词法处理、新关键字 |
| C++23 | 字符集与编码重构、UTF-8 源文件、`\N{...}` 与分隔转义 `\x{...}`、`z`/`uz` 后缀、扩展浮点后缀、拼接前缀冲突非良构、标识符采用 UAX #31 |
| C++26 | 基本字符集加入 `$` `@` `` ` ``、不求值字符串、`^^` 与 `[:` `:]`、`contract_assert`/`pre`/`post`、`#embed` 的头文件名上下文、词法 UB 清理 |
