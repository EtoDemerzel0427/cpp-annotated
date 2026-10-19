---
title: 本文档的结构
summary: 标准的全局地图：第 5–15 章是语言，第 16–33 章和 Annex D 是库，其余附录只是说明性的汇总；遇到一个问题该去哪一部分找答案。
status: done
related: syntax, intro.compliance, library, topics/how-to-read-the-standard
tags: 总则, 导读
updated: 2026-10-18
---

!!! tldr
    - 第 5–15 章描述语言，第 16–33 章和 Annex D 描述标准库。
    - 附录中只有 Annex D（弃用的特性）是规范性的。语法汇总、实现限制、兼容性差异、UB 和 IFNDR 汇总都只是说明性的，引用时要回到正文。
    - 想知道升级标准版本后代码为什么不能编译了、或者含义变了，查 Annex C。
    - 引用条款时用 stable name（如 `[basic.life]`），不用章节号，章节号在各版之间经常变。

## 遇到问题去哪里找

| 问题 | 去哪里 |
|---|---|
| 这段代码合法吗？是什么意思？ | 第 5–15 章，先看语法（[[syntax]]），再看相应条款的语义规则 |
| 这个库函数保证什么？ | 先在第 16 章 [[structure.specifications]] 弄清 *Preconditions*、*Effects* 等要素的含义，再读对应章节 |
| 为什么换了 `-std=` 之后代码变了？ | Annex C [[diff]]，按版本列出了会改变已有代码的变更 |
| 这种情况是不是 UB 或 IFNDR？ | Annex F [[ub]] 和 Annex G [[ifndr]] 是索引，结论要落到正文段落上 |

## 语言部分（¶1）

¶1 第 5 章 [[lex]] 到第 15 章 [[cpp]] 描述 C++ 语言，其中的语法按 [[syntax]] 所述的记法给出。为了方便，Annex A [[gram]] 把所有产生式重复汇总了一遍。

| 章 | 内容 |
|---|---|
| 5 [[lex]] | 词法：翻译阶段、字符集、记号、字面量 |
| 6 [[basic]] | 基础：声明与定义、ODR、作用域、名字查找、链接、对象模型、类型、程序执行、内存模型、契约断言 |
| 7 [[expr]] | 表达式：值类别、转换、各运算符、常量求值 |
| 8 [[stmt]] | 语句 |
| 9 [[dcl]] | 声明：说明符、声明符、初始化、函数定义、结构化绑定、枚举、命名空间、属性 |
| 10 [[module]] | 模块 |
| 11 [[class]] | 类 |
| 12 [[over]] | 重载 |
| 13 [[temp]] | 模板 |
| 14 [[except]] | 异常处理 |
| 15 [[cpp]] | 预处理 |

第 1–4 章不属于语言描述。[[intro.compliance]] 说独立实现要支持"第 5 章到第 15 章描述的全部语言"，指的就是上表这个范围。

## 库部分（¶2）

¶2 第 17 章 [[support]] 到第 33 章 [[exec]]，加上 Annex D [[depr]]，合称**库条款**（library clauses），描述标准库。它们的写法由第 16 章 [[library]] 规定。

第 16 章本身不定义任何库设施。它规定怎样读库条款：头文件概要（synopsis）怎么读，*Constraints*、*Mandates*、*Preconditions*、*Effects*、*Returns*、*Throws*、*Complexity* 等要素各是什么意思（[[structure.specifications]]）。它还规定程序与库之间的约定，例如哪些名字保留给实现（[[reserved.names]]）、程序能不能往 `namespace std` 里加东西（[[namespace.std]]）。

| 章 | 内容 |
|---|---|
| 17 [[support]] | 语言支持：`<cstddef>`、`<limits>`、`<new>`、`<exception>`、`<contracts>`、`<compare>`、`<coroutine>` 等 |
| 18 [[concepts]] | 概念 |
| 19 [[diagnostics]] | 异常类、`<system_error>`、`<stacktrace>`、`<debugging>` |
| 20 [[mem]] | 智能指针、分配器、`<memory_resource>` |
| 21 [[meta]] | 类型特征、`<ratio>`、反射 `<meta>` |
| 22 [[utilities]] | `pair`、`tuple`、`optional`、`variant`、`expected`、函数对象、`<bit>` 等 |
| 23 [[containers]] | 容器，以及 `span`、`mdspan` |
| 24 [[iterators]] | 迭代器 |
| 25 [[ranges]] | 范围 |
| 26 [[algorithms]] | 算法 |
| 27 [[strings]] | 字符串 |
| 28 [[text]] | `<charconv>`、本地化、`<format>`、正则表达式 |
| 29 [[numerics]] | 数值 |
| 30 [[time]] | 时间 |
| 31 [[input.output]] | 输入输出 |
| 32 [[thread]] | 并发 |
| 33 [[exec]] | 执行控制（`std::execution`） |

Annex D 列在库条款里，是因为弃用的特性仍然是标准的一部分，实现必须支持。弃用只表示它将来可能被移除，不建议再用。

## 附录（¶3–¶4）

¶3 Annex B 建议了实现在容量上的下限。

¶4 Annex C 概述 C++ 自首次发布以来的演进，详细说明 C++ 与 C 的区别；某些只为兼容而存在的特性放在 Annex D。

当前草案的全部附录如下，[intro.structure] 没有提到 E、F、G：

| 附录 | 性质 | 内容 |
|---|---|---|
| A [[gram]] | 说明性 | 语法汇总，接受的是合法代码的超集 |
| B [[implimits]] | 说明性 | 嵌套深度、模板递归深度等量的建议最小值 |
| C [[diff]] | 说明性 | 与 C 及与各个旧版本 C++ 的差异 |
| D [[depr]] | 规范性 | 弃用的特性 |
| E [[uaxid]] | 说明性 | 与 Unicode UAX #31（标识符）的符合情况 |
| F [[ub]] | 说明性 | 核心语言未定义行为汇总 |
| G [[ifndr]] | 说明性 | 非良构、不要求诊断的规则汇总 |

Annex C 的每一条都写明受影响的条款、变化、理由、对原有代码的影响，并附有例子。例如 [[diff.cpp23]] 列出的是 C++26 中会让 C++23 代码改变含义或变得非法的变更。

!!! history
    条文用 "Clause [support] through Clause [exec]" 这样的 stable name 区间指称范围，不写章节号，所以增删章节时 [intro.structure] 几乎不用改。第 33 章 [exec] 是 C++26 新增的；[mem]、[meta]、[text] 等章都是在历次修订中从更大的章节拆分或重组出来的。
