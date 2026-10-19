---
title: 程序执行
summary: 6.10 的导读：一个线程内的求值顺序、多线程之间的可见性、线程能否一直往前走、程序怎样启动和终止，以及把它们连在一起的几种先后关系。
status: done
papers: P0145R3, P0668R5, P0982R1, P3475R2
related: intro.execution, intro.multithread, intro.progress, basic.start, basic.contract, intro.abstract
tags: 导读, 求值顺序, 内存模型, 初始化
updated: 2026-10-19
---

!!! tldr
    - 6.10 规定[[intro.abstract|抽象机]]怎样运转，分四部分：单线程的求值顺序、多线程的数据竞争、前进保证、程序的启动与终止。
    - 单线程内的顺序用 sequenced before 描述；它加上线程间的同步边，得到 happens before。
    - 两类最常见的 UB 结构相同：同一线程内无序的冲突访问，以及不同线程间没有 happens before 的冲突访问（数据竞争）。
    - 静态变量的初始化顺序和析构顺序也用这套关系描述。

6.10 [basic.exec] 本身没有正文，只是四个子条款的容器：

| 小节 | 回答的问题 | 本站笔记 |
|---|---|---|
| 6.10.1 顺序执行 | 一个线程里，各个求值按什么顺序发生？`i = i++ + i` 为什么是 UB？ | [[intro.execution]] |
| 6.10.2.1–2 多线程与数据竞争 | 一个线程的写入什么时候对另一个线程可见？什么是数据竞争？ | [[intro.multithread]] |
| 6.10.2.3 前进保证 | 编译器为什么能删掉没有副作用的死循环？线程一定会往前走吗？ | [[intro.progress]] |
| 6.10.3 启动与终止 | `main` 之前和之后发生什么？静态变量按什么顺序初始化和析构？ | [[basic.start]] |

紧接着的 6.11 [[basic.contract]] 是 C++26 的契约断言，它的运行时语义也用这里定义的关系来描述，例如前置条件 sequenced before 函数体。

## 几种先后关系

```
sequenced before          同一线程内的先后（[intro.execution]/8）
synchronizes with         跨线程的同步边，由原子操作、互斥量、线程的创建与 join 提供（[intro.races]/6）
happens before            以上两者合在一起再取传递闭包（[intro.races]/7）
strongly happens before   happens before 中 seq_cst 全序必须尊重的那一部分（[intro.races]/8）
```

这几种关系把四个子条款连在一起：

- 单线程内，对同一内存位置的修改与另一次访问如果无序，行为未定义（[[intro.execution#10]]）。多线程间，两个冲突访问如果都没有 happens before 另一个，就是数据竞争，同样是 UB（[[intro.races#17]]）。前者看 sequenced before，后者看 happens before。
- 所有静态初始化 strongly happens before 任何动态初始化（[[basic.start.static#2]]）。同一翻译单元里有序初始化的变量，按定义的先后顺序初始化（[[basic.start.dynamic#3]]）。静态对象按构造顺序的逆序析构，这个顺序也用 strongly happens before 判断（[[basic.start.term#4]]）。
- 前进保证回答的是另一个问题：不管这些关系怎样排，一个线程是否一定会走到下一步。

## 阅读顺序

1. [[intro.execution]]：先弄清单线程的 sequenced before，以及 C++17 给哪些运算符规定了求值顺序。
2. [[intro.multithread]]：在 sequenced before 上加入同步，理解内存模型。可以配合 [[atomics.order]] 和 [[atomics.fences]]。
3. [[intro.progress]]：编译器为什么能删掉死循环，并行算法对线程有什么承诺。
4. [[basic.start]]：静态初始化顺序和终止顺序，工程上最容易出问题的部分。
5. [[basic.contract]]：C++26 契约的运行时语义。

!!! history "演进概览"
    - C++98/03 用顺序点（sequence point）描述单线程的求值顺序，标准里没有线程。启动和终止的规则已基本成型：同一翻译单元内按顺序初始化，不同翻译单元之间顺序未指定。
    - C++11 用 sequenced before 取代顺序点，加入线程、内存模型、数据竞争和前进保证，函数内静态变量的初始化成为线程安全的，并新增 `thread_local`。
    - C++17 给 `<<`、`=`、`[]` 等运算符规定了求值顺序（[[P0145R3]]）；并行算法带来了不同强度的前进保证；inline 变量引入了部分有序的初始化。
    - C++20 修订了 seq_cst 的语义，重新定义 strongly happens before（[[P0668R5]]），并削弱了 release sequence（[[P0982R1]]）；新增 `constinit`。
    - C++26 把 `memory_order::consume` 移出核心内存模型（[[P3475R2]]）；平凡的无限循环不再是 UB；新增契约断言。
