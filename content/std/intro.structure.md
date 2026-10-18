---
title: 本文档的结构
summary: 标准的全局地图：第 5–15 章是语言，第 16–33 章和 Annex D 是库，其余附录各司其职；以及库条款统一的描述方式。
status: done
related: syntax, intro.compliance, library, topics/how-to-read-the-standard
tags: 总则, 导读
updated: 2026-10-17
---

[intro.structure] 相当于标准自带的阅读指南，用四段话勾勒出全书的结构。读懂它，就知道一个问题该去哪一部分找答案。

## 语言部分（¶1）

¶1 第 5 章 [[lex]] 到第 15 章 [[cpp]] 描述 C++ 编程语言。这部分描述包括按 [[syntax]] 所述形式给出的详细语法规范。为了方便，Annex A [[gram]] 重复了所有这些语法规范。

| 章 | stable name | 内容 |
|---|---|---|
| 5 | [[lex]] | 词法：翻译阶段、字符集、记号、字面量 |
| 6 | [[basic]] | 基础：声明与定义、ODR、作用域、名字查找、链接、对象模型、类型、程序执行、内存模型、契约断言 |
| 7 | [[expr]] | 表达式：值类别、转换、各运算符、常量求值 |
| 8 | [[stmt]] | 语句 |
| 9 | [[dcl]] | 声明：说明符、声明符、初始化、函数定义、结构化绑定、枚举、命名空间、属性 |
| 10 | [[module]] | 模块 |
| 11 | [[class]] | 类 |
| 12 | [[over]] | 重载 |
| 13 | [[temp]] | 模板 |
| 14 | [[except]] | 异常处理 |
| 15 | [[cpp]] | 预处理指令 |

注意，第 4 章总则（本章）和第 1–3 章不属于语言描述。[[intro.compliance]] ¶7 说独立实现要支持"第 5 章到第 15 章描述的全部语言"，指的就是这个范围。

Annex A 只是语法的汇总，而且 [[gram.general]] 明说它"不是对语言的精确陈述"。它接受的是合法 C++ 构造的超集，语法上合法但没有意义的构造，要靠歧义消解规则（[[stmt.ambig]]、[[dcl.spec]]、[[class.member.lookup]]）、访问控制和类型规则才能筛掉。所以**单靠语法永远无法判断一段代码是否良构**。

## 库部分（¶2）

¶2 第 17 章 [[support]] 到第 33 章 [[exec]] 以及 Annex D [[depr]]（合称**库条款**，*library clauses*）描述 C++ 标准库，包括构成标准库的实体和宏的详细描述，其形式由第 16 章 [[library]] 规定。

第 16 章库引言本身不定义任何库设施，而是规定如何读库条款，以及库与程序之间的契约：

- [[description]]：描述方法。包括每个库条款的结构（[[structure]]），即概要表、头文件概要（synopsis）、要求、详细规范；详细规范中的各个要素 *Constraints*、*Mandates*、*Constant When*、*Preconditions*、*Hardened preconditions*、*Effects*、*Synchronization*、*Postconditions*、*Result*、*Returns*、*Throws*、*Complexity*、*Remarks*、*Error conditions* 的确切含义（[[structure.specifications]]）；以及仅用于说明（exposition only）的成员、"see below"、"unspecified" 类型等约定（[[conventions]]）。
- [[requirements]]：库的整体要求。头文件清单、独立实现的子集（[[compliance]]）、程序使用库的规则（[[using]]）、保留名字（[[reserved.names]]）、对程序提供的函数与类型的要求（[[res.on.functions]]）、对实现的约束（[[conforming]]）。

| 章 | stable name | 内容 |
|---|---|---|
| 17 | [[support]] | 语言支持：`<cstddef>`、`<limits>`、`<new>`、`<typeinfo>`、`<exception>`、`<contracts>`、`<compare>`、`<coroutine>` … |
| 18 | [[concepts]] | 概念库 |
| 19 | [[diagnostics]] | 诊断：异常类、`<system_error>`、`<stacktrace>`、`<debugging>` |
| 20 | [[mem]] | 内存管理：智能指针、分配器、`<memory_resource>` |
| 21 | [[meta]] | 元编程：类型特征、`<ratio>`、反射 `<meta>` |
| 22 | [[utilities]] | 通用工具：`pair`、`tuple`、`optional`、`variant`、`expected`、函数对象、`<bit>` … |
| 23 | [[containers]] | 容器与视图（`span`、`mdspan`） |
| 24 | [[iterators]] | 迭代器 |
| 25 | [[ranges]] | 范围 |
| 26 | [[algorithms]] | 算法 |
| 27 | [[strings]] | 字符串 |
| 28 | [[text]] | 文本处理：`<charconv>`、本地化、`<text_encoding>`、`<format>`、正则表达式 |
| 29 | [[numerics]] | 数值 |
| 30 | [[time]] | 时间 |
| 31 | [[input.output]] | 输入输出 |
| 32 | [[thread]] | 并发支持 |
| 33 | [[exec]] | 执行控制（`std::execution`） |

Annex D 是唯一一个**规范性**的附录。被弃用的特性仍然是标准的一部分，实现必须支持（[[intro.compliance]] ¶2.1 把它与第 5–33 章并列）。弃用只表示这项特性将来可能被移除，不建议再用。

## 其余附录（¶3–¶4）

¶3 Annex B [[implimits]] 建议了符合标准的实现在容量上的下限。

¶4 Annex C [[diff]] 概述了 C++ 自首次发布以来的演进，并详细解释了 C++ 与 C 的区别。C++ 的某些特性仅为兼容目的而存在，Annex D [[depr]] 描述了这些特性。

Annex C 对 language lawyer 特别有用。它按版本列出了每次修订中会改变已有合法代码的含义、或使其变为非法的变更（例如 [[diff.cpp23]]、[[diff.cpp20]]……），每条都写明受影响的条款、变化、理由、对原有特性的影响，并附有例子。如果想知道为什么一段代码在 C++20 能编译、在 C++23 不行，先查这里。

当前草案中另有几份附录，[intro.structure] 尚未提及：

| 附录 | stable name | 性质 | 内容 |
|---|---|---|---|
| A | [[gram]] | 资料性 | 语法汇总 |
| B | [[implimits]] | 资料性 | 实现的容量建议值 |
| C | [[diff]] | 资料性 | 兼容性差异 |
| D | [[depr]] | **规范性** | 兼容性特性（弃用） |
| E | [[uaxid]] | 资料性 | 与 Unicode UAX #31（标识符）的符合情况 |
| F | [[ub]] | 资料性 | 核心语言未定义行为汇总 |
| G | [[ifndr]] | 资料性 | 非良构、不要求诊断的规则汇总 |

Annex F 和 Annex G 是较新加入的。它们只汇总散布在正文中的规则，每条都链接回正文并附上例子；它们本身不是规范依据，引用时应引用正文条款。

## 怎么用这张地图

- 想知道一段代码是否合法，去第 5–15 章，从语法（[[syntax]]、[[gram]]）开始，再看相应条款的语义规则。
- 想知道一个库函数保证什么，先去第 16 章弄清各规范要素的含义，再去对应章节读详细规范。
- 想知道升级标准版本后代码的行为为什么变了，去 Annex C。
- 想判断某种情况算不算 UB 或 IFNDR，Annex F、G 是很好的索引，但结论要落到正文段落上。

更完整的阅读方法见 [[topics/how-to-read-the-standard]]。

!!! history
    - 第 33 章 [exec]（执行控制库，`std::execution`）是 C++26 新增的。库条款的划分在历次修订中多次调整（例如 [mem]、[meta]、[text] 都是从更大的章节中拆分或重组出来的），同一条款在不同版本中的章节号经常不同，所以引用条款时请使用 stable name，而不是章节号。
    - 条文内部用 "Clause [support] through Clause [exec]" 这样的 stable name 区间来指称范围，而不写章节号，所以增删章节时 [intro.structure] 本身几乎不用改。
