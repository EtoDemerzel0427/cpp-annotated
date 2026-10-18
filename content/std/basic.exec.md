---
title: 程序执行
summary: 6.10 导读：单线程的求值顺序、多线程内存模型、前进保证、程序的启动与终止如何拼成"一个 C++ 程序如何运行"的完整图景
status: draft
related: intro.execution, intro.multithread, intro.progress, basic.start, basic.contract, intro.abstract
tags: 导读, 求值顺序, 内存模型, 初始化
updated: 2026-10-17
---

[[intro.abstract]] 说 C++ 程序的语义由一台**抽象机**定义；6.10 [basic.exec] 则规定这台抽象机**如何运转**：一个线程内的求值按什么顺序发生，多个线程如何互相看到对方的写入，线程是否一定会往前走，以及程序从哪里开始、到哪里结束。

这四个主题共用一套"关系"词汇，后一个建立在前一个之上：

| 小节 | 主题 | 核心概念 | 本站笔记 |
|---|---|---|---|
| 6.10.1 | 顺序执行 | 完整表达式、值计算与副作用、**sequenced before**、无序冲突即 UB | [[intro.execution]] |
| 6.10.2.1–2 | 多线程与数据竞争 | 冲突、修改顺序、synchronizes with、**happens before**、strongly happens before、数据竞争即 UB | [[intro.multithread]] |
| 6.10.2.3 | 前进保证 | 无副作用死循环是 UB（平凡无限循环除外）、执行步骤、并发/并行/弱并行保证 | [[intro.progress]] |
| 6.10.3 | 启动与终止 | `main`、静态/动态初始化及其顺序、`exit` 与析构顺序 | [[basic.start]] |

紧随其后的 6.11 [[basic.contract]]（契约断言）是 C++26 新增的一节，它大量使用这里定义的关系（"前置条件 sequenced before 函数体"、"可观察检查点 happens before 断言求值"），所以放在一起读最自然。

## 关系的层次

```
sequenced before            —— 单线程内（[intro.execution]/8）
   ∪ synchronizes with      —— 跨线程的同步边（[intro.races]/6，由 [atomics]、[thread] 提供）
   ⇒ happens before         —— 二者并集的传递闭包（[intro.races]/7）
   ⊇ strongly happens before —— seq_cst 全序必须尊重的那部分（[intro.races]/8）
```

- **未定义行为的两大来源**都在这里：单线程内对同一内存位置的**无序**冲突访问（[[intro.execution#10]]），以及跨线程**没有 happens before** 的冲突访问（[[intro.races#17]]）。二者结构完全平行：前者用 sequenced before 判断，后者用 happens before 判断。
- **初始化与终止的顺序**也用这套词汇描述：所有静态初始化 strongly happens before 任何动态初始化（[[basic.start.static#2]]）；同一 TU 中有序变量的初始化 sequenced before 后面的变量（[[basic.start.dynamic#3]]）；析构顺序由"视同构造"之间的 strongly happens before 关系决定（[[basic.start.term#4]]）。
- **前进保证**则回答另一个维度的问题：关系图之外，线程是否一定会"走到"下一步？

## 推荐阅读顺序

1. [[intro.execution]]：先把单线程的 sequenced before 弄清楚——这是最常被问到的"`i = i++ + 1` 是不是 UB"一类问题的出处，也是 C++17 求值顺序改动的落点。
2. [[intro.multithread]]：在 sequenced before 之上加入同步，读懂内存模型；配合 [[atomics.order]] 与 [[atomics.fences]]。
3. [[intro.progress]]：理解编译器为什么能删掉死循环，以及并行算法与 `std::execution` 对线程的承诺。
4. [[basic.start]]：静态初始化顺序问题与终止顺序——工程上最容易踩到的部分。
5. [[basic.contract]]：C++26 契约的运行时语义。

## 历史脉络

!!! history "演进概览"
    - **C++98/03**：只有单线程的"顺序点"模型；启动/终止规则已基本成型（同一 TU 内按序、跨 TU 未指定）。
    - **C++11**：顺序点被 sequenced before 取代；加入线程、内存模型、数据竞争、前进假设、线程安全的局部静态初始化、`thread_local`。
    - **C++17**：P0145 为若干运算符规定求值顺序；并行算法带来三级前进保证；inline 变量带来"部分有序"初始化。
    - **C++20**：修订 seq_cst 语义（strongly happens before）、削弱 release sequence；`constinit`；模块参与初始化顺序。
    - **C++26**：`memory_order::consume` 退出核心内存模型；平凡无限循环不再是 UB；契约断言（6.11）。
