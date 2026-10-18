---
title: 总则
summary: 第 4 章导读：标准与实现之间的约定（符合性、抽象机、可观察行为），全书结构，以及语法记法。它是读懂其余所有条款的前提。
status: done
related: intro.scope, intro.refs, intro.defs, topics/how-to-read-the-standard
tags: 导读, 总则
updated: 2026-10-17
---

第 4 章总则（General principles）不规定任何具体的语言特性，它规定的是规则本身如何生效。如果把第 5 章往后的条文看作法律条文，第 4 章说明的就是违反了会怎样、由谁执行、怎样查找条文。第 1–3 章（[[intro.scope]]、[[intro.refs]]、[[intro.defs]]）是 ISO 文件的固定开头，内容上与第 4 章紧密相连，本站一并归在这里阅读。

## 本章有什么

| 条款 | 内容 | 为什么要读 |
|---|---|---|
| [[intro.compliance]]（含 [intro.compliance.general]、[intro.abstract]） | 实现的符合性；抽象机与可观察行为 | 解释 ill-formed / IFNDR / UB 对实现到底意味着什么；as-if 规则；C++26 的可观察检查点如何限制 UB 的"时间旅行"；hosted / freestanding / hardened 实现；扩展的边界 |
| [[intro.structure]] | 本文档的结构 | 全书地图：哪几章是语言、哪几章是库、各附录是什么性质 |
| [[syntax]] | 语法记法 | 读懂每一条语法产生式的前提 |

再配合第 3 章 [[intro.defs]] 中的行为分类（UB、unspecified、implementation-defined、erroneous ……）一起读，就掌握了 language lawyer 讨论问题所用的全部元语言。

## 核心思想

**1. 标准约束的是实现，不是程序。** [[intro.scope]] 第一句就说，本文档规定对 C++ 实现的要求。对程序的要求（"程序 shall……"）只是方便的写法，[[intro.compliance]] ¶2 把它们翻译回对实现的要求：没有违规的程序，实现必须正确执行；程序违反可诊断规则时，实现必须给出至少一条诊断；程序违反 NDR 规则时，实现不受任何约束。

**2. 诊断不等于拒绝。** 标准只要求至少一条诊断信息，而诊断信息的定义宽到警告也算。真正必须拒绝的只有 `#error`、失败的 `static_assert`，以及常量求值中以终止型语义违反的契约断言。这为编译器扩展留出了空间，也说明了能通过编译从来不能证明代码合法。

**3. 语义由抽象机定义，实现只需复现可观察行为。** C++ 的语义描述的是一台参数化的非确定抽象机：实现定义行为是它的参数，未指定行为带来非确定性，未定义行为标记的是标准没有要求的操作。只要[[g:observable-behavior|可观察行为]]（volatile 访问、交付给宿主环境的文件数据、交互设备上的提示顺序）与抽象机的某一条可能执行一致，实现就可以生成任何代码（[[g:as-if-rule|as-if 规则]]）。

**4. UB 的影响范围被可观察检查点限制** {{c++26}}。C++23 及之前，一旦某次执行包含 UB，标准对整次执行（甚至 UB 之前的部分）都不施加要求。C++26 引入了[[g:observable-checkpoint|可观察检查点]]与[[g:defined-prefix|定义前缀]]：如果更早的可观察行为与 UB 之间隔着检查点，这些行为必须如实产生。

## 阅读建议

- 初读时，先读 [[intro.defs]] 的"行为分类"部分，再读 [[intro.compliance]]。这两页是全站引用最多的页面。
- [[syntax]] 很短，但在读任何含有语法产生式的条款（几乎是第 5–15 章的全部）之前，最好先读一遍。
- [[intro.structure]] 和 [[topics/how-to-read-the-standard]] 一起读，建立全书的地图和阅读方法。
- [[intro.refs]]、[[intro.scope]] 可以快速浏览，遇到需要查 C 标准怎么规定的问题时再回来看。

!!! history "这一章的变迁"
    在 C++98 到 C++14 中，范围、规范性引用、术语定义、实现符合性、程序执行等都放在第 1 章 General 里。C++17 按 ISO 文件的统一结构把开头拆成了现在的第 1–4 章；后来程序执行（[[intro.execution]]）、多线程（[[intro.multithread]]）等内容移入第 6 章 [[basic.exec]]，第 4 章只剩下符合性、结构和语法记法这些真正属于总则的内容。各条款的 stable name（如 `[intro.execution]`）保持不变，所以今天有一些名为 `intro.*` 的条款位于第 6 章。
