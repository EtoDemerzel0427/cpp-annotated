---
title: 从 pthreads 到 C++26：线程与内存模型
summary: C++ 怎样从一门不知道线程存在的语言，变成标准里有数据竞争定义、六种（后来是五种）内存序、jthread 与 hazard pointer 的语言：Boehm 2005 的论证、C++0x 内存模型工程、consume 的兴衰、async 阻塞析构之争，以及这些历史在今天 [intro.races] 措辞里留下的痕迹
status: draft
order: 20
since: c++11
papers: N2429, N2427, N2480, N2497, P0371R1, P0660R10, P1135R6, P2530R3, P2545R4, P3475R2
related: intro.multithread, intro.progress, atomics.order, thread, futures, thread.stoptoken, saferecl, depr.atomics, topics/undefined-behavior
tags: 内存模型, 并发, 原子操作, 数据竞争, 沿革
updated: 2026-10-18
---

今天的标准用 [[intro.multithread]] 一整节定义多线程程序的语义：什么叫两个求值冲突，什么叫 happens before，什么样的执行含有数据竞争，数据竞争为什么直接导致未定义行为。第一次读这一节的人常会疑惑：为什么要绕这么大一个圈子？为什么 `memory_order` 有 `relaxed`、`acquire`、`release` 这么多选项，而 `consume` 又被挪进了附录 D？为什么 `std::thread` 析构时线程还在跑就调用 `std::terminate`，而 `std::async` 返回的 future 析构时却会等？

这些规定几乎都能在过去二十年的文档里找到来由。本页按时间顺序讲这段历史：C++98 没有线程概念时程序员怎么写多线程代码，Hans Boehm 2005 年为什么论证线程不能只靠库实现，C++0x 内存模型怎样定下来，之后每一版标准在并发方面加了什么、改了什么。最后一节回到当前草案的 [[intro.races]]，逐段说明它的措辞和这段历史的对应关系。

阅读本页不需要先读懂 [[intro.multithread]]，但读完后再去读它会容易得多。涉及的术语：[[g:data-race|数据竞争]]、[[g:happens-before|happens before]]、[[g:synchronizes-with|synchronizes with]]、[[g:memory-location|内存位置]]。

## C++98：一台单线程的抽象机

C++98 和 C++03 描述程序语义的方式是一台抽象机（abstract machine）：程序的可观察行为由顺序点（sequence point）之间的求值顺序、对 volatile 对象的访问和 I/O 决定，实现只要保持可观察行为不变，就可以任意变换代码（今天的对应条款是 [[intro.abstract]] 与 [[intro.execution]]）。这套描述里没有第二个执行流。Scott Meyers 和 Andrei Alexandrescu 在 2004 年的文章里直接写道：“As languages, neither C nor C++ have threads.”（*C++ and the Perils of Double-Checked Locking*，Dr. Dobb's Journal，2004 年 7、8 月）。Boehm 在 2005 年的论文里也把当时问题的根源归结为语言规范根本不提线程（Boehm 2005，§3）。

这并不意味着当时没人写多线程 C++。恰恰相反，服务器、GUI 程序和操作系统组件大量使用线程，只是线程来自语言之外：POSIX 系统用 pthreads，Windows 用 Win32 线程 API，跨平台项目用 ACE 或 Boost.Thread 之类的封装库。语言标准对这些程序的行为不做任何承诺，正确性依赖线程库规范、编译器的实际做法和硬件手册三者之间的默契。

## pthreads 与 Win32 时代：库、屏障与编译器的默契

POSIX 线程规范对内存的要求只有一段话。按 Boehm 的转述，它要求应用程序保证：一个线程在修改某个内存位置时，其他线程不能读写这个位置；这种限制要通过一组会同步内存的函数来实现，`pthread_mutex_lock()`、`pthread_mutex_unlock()` 等都在名单上（Boehm 2005，§3 引用的 IEEE Std 1003.1 原文）。规范的理由说明还提到，形式化的内存模型被认为大多数程序员读不懂，所以选择了一条直观的规则。

在这条规则下，C/C++ 实现的通常做法是（Boehm 2005，§3）：

1. 同步函数内部包含硬件内存屏障（memory barrier），阻止处理器把内存操作重排到调用之外；
2. 编译器把 `pthread_mutex_lock()` 这类调用当成不透明的外部函数，假设它可能读写任何全局变量，因此不会把内存访问移过这次调用。

只要程序严格用互斥量保护所有共享数据，这套做法大体能工作。麻烦在于想绕过互斥量的代码，以及编译器优化碰巧破坏了上面的默契的情况。

### 双重检查锁定

最有名的例子是双重检查锁定（double-checked locking pattern，DCLP）。下面是当时常见的写法，属于历史代码，按今天的标准它含有数据竞争：

```cpp title="DCLP（2004 年前后的常见写法，历史代码）"
Singleton* Singleton::instance() {
    if (pInstance == 0) {                 // 第一次检查，不加锁
        Lock lock;                        // 某个平台的互斥锁封装
        if (pInstance == 0) {             // 第二次检查
            pInstance = new Singleton;
        }
    }
    return pInstance;
}
```

Meyers 和 Alexandrescu 的分析是：`pInstance = new Singleton;` 包含分配内存、构造对象、给指针赋值三步，编译器（或硬件）可以把赋值提到构造之前，因为在单线程语义下这样做不可观察。于是另一个线程可能在第一次检查时看到非空指针，拿到一个还没构造完的对象。他们逐一检查了临时变量、`volatile`、把代码拆进别的翻译单元等补救手段，结论是在标准 C++ 范围内没有可移植的修复办法，只能依靠平台提供的内存屏障（同上，Part I、Part II）。

当时可用的平台手段各不相同。GCC 4.1 的手册已经记载了 `__sync_*` 系列内建函数，并说明它们沿用 Intel Itanium 处理器专用 ABI 中的定义，多数是双向的完全屏障（GCC 4.1.2 手册，Atomic Builtins 一节）。MSVC 则给 `volatile` 赋予了额外语义：在 `/volatile:ms` 模式下（面向非 ARM 架构时的默认模式），volatile 写具有 release 语义，volatile 读具有 acquire 语义；微软文档同时说明依赖这一点的代码不可移植，ISO C++ 的 `volatile` 不应用于线程间通信（Microsoft Learn，*volatile (C++)*）。这种依赖编译器方言的状态，也是后来 C++ 的 `volatile` 与原子操作被严格区分开的背景之一。

## Boehm 2005：线程不能只靠库来实现

2005 年，HP 实验室的 Hans-J. Boehm 在 PLDI 上发表 *Threads Cannot Be Implemented As a Library*（PLDI 2005，261–268 页；同年较早的版本是 HP Labs 技术报告 HPL-2004-209）。论文的论点是：如果编译器按单线程语义设计，线程只是一个后加的库，那么无法保证生成代码的正确性。它在 C + pthreads 的背景下给出三类正确性问题和一类性能问题（§4、§5）。

第一类是定义上的循环。pthreads 说有数据竞争的程序不受保护，但一个程序有没有竞争，取决于语言给出的语义。论文的例子是两个线程分别执行 `if (x == 1) ++y;` 和 `if (y == 1) ++x;`，`x`、`y` 初值为 0。按顺序一致的理解，两个条件都不会成立，没有竞争；可如果编译器只需保持单线程正确性，它可以把第一句改写成 `++y; if (x != 1) --y;`，这样就凭空出现了竞争（§4.1）。Boehm 认为这一类在实践中少见，但说明必须由语言来定义内存模型，用户和编译器才能对什么是数据竞争达成一致。

第二类是改写相邻数据。对于 `struct { int a:17; int b:15; } x;`，几乎没有机器能直接写 17 位，于是 `x.a = 42` 会被编译成读出整个字、改掉低 17 位、再整体写回。如果另一个线程恰好在读和写之间修改了 `x.b`，这次修改就会丢失，尽管两个线程访问的是不同的成员。更进一步，pthreads 只禁止对同一个内存位置的并发写，而内存位置这个词没有定义（POSIX 的澄清答复说它由实现定义）。论文指出，按这种读法，编译器把八个相邻 `char` 成员的多次赋值合并成一次 64 位写回也是允许的，甚至链接器排在一起的两个全局变量也可能互相覆盖（§4.2）。

第三类是寄存器提升。论文的例子是一个循环，只在 `mt` 为真时才加锁更新全局变量 `x`。编译器若根据剖析信息判断 `mt` 通常为假，就可能把 `x` 提升到寄存器里，在循环前读、循环后写回。变换后的代码会在不持锁的时候读写 `x`，多线程下完全错误，但它并没有违反 pthreads 的字面要求。Boehm 提到，他知道至少四个优化编译器（其中三个是产品级编译器）在某个时期做过这种变换（§4.3）。

性能方面，pthreads 只认可用互斥量保护一切共享数据这一种风格，排除了依赖原子操作和内存顺序的无锁算法。论文用并行埃拉托斯特尼筛法做了测量，说明在某些场景下不用锁的版本明显更快，而这类程序在 pthreads 规则下没有定义（§5、§6）。

这篇论文的结论直接决定了后来 C++ 内存模型的几个设计：语言必须自己定义线程语义；必须精确定义内存位置，限制编译器引入对其他内存位置的写；必须提供原子操作，让无锁算法有合法的写法。

## C++0x 内存模型工程（2004–2008）

### 起点：N1680 与 Java 的经验

在 Boehm 的论文发表之前，相关工作已经进入 WG21。2004 年 9 月的 Redmond 会议上，Andrei Alexandrescu、Hans Boehm、Kevlin Henney、Doug Lea、Bill Pugh 提交了 [[N1680]]（*Memory Model for multithreaded C++*）；同一次会议上，Pete Becker 提交了线程库提案 [[N1682]]。Stroustrup 在 HOPL IV 论文里评论说，这两份提案出现在同一次会议上恐怕不是巧合（HOPL IV，§4.1.2）。之后的 [[N1777]]（2005，问题清单）、[[N1876]]（2005 年 8 月状态更新）、[[N1942]]（2006，Boehm 的 strawman 提案）逐步把方案具体化。

作者名单里的 Pugh 和 Lea 是 Java 内存模型（JSR-133，2004 年随 Java 5 发布）的主要参与者。据 Stroustrup 回忆，委员会起初希望直接采用 Java 的模型，但 Intel 和 IBM 的代表指出，那样做会显著拖慢 JVM 本身（他转述的说法是至少两倍），于是 C++ 只能采用一个更复杂的模型（HOPL IV，§4.1.1）。另一个原因来自语言本身：Java 必须给有数据竞争的程序也规定语义，因为它要限制不可信代码造成的破坏；Boehm 2005 明确说 C/C++ 不需要这样做，有竞争的程序可以完全没有定义（§3）。这一点后来成为 C++ 模型的基石。

Stroustrup 在同一节里还记述了一场关于最底层同步原语的争论：Intel 一方的模型是 TSO 加少量原子操作，IBM PowerPC 一方是弱一致性加栅栏（fence）。他说 Paul McKenney 让他相信，IBM 有太多深埋在复杂算法里的基于栅栏的代码，无法转向 Intel 式的模型，最终 C++11 两者都支持（HOPL IV，§4.1.1）。这也是今天标准里同时有带内存序的原子操作和独立的 [[atomics.fences]] 的来由。

### 2006–2007：并发组与最终修订

2006 年起，并发工作从演化工作组中分出来，由 Boehm 主持一个专门小组，也就是后来的 SG1（HOPL IV，§4.1；同文介绍 WG21 组织结构时说 SG1 自 2006 年起活跃，大部分时间由 Boehm 主持）。这一阶段的主要文档有：

- Clark Nelson 与 Boehm 关于把顺序点改写为 sequenced before 关系的系列文档：[[N2052]]、[[N2171]]、[[N2300]]、[[N2334]]。单线程的求值顺序必须先用关系来表述，跨线程的 happens before 才能建立在它上面。这次改写后来也影响了 C++11 对求值顺序的整体表述（见 [[intro.execution]] 与 [[topics/order-of-evaluation]]）。
- Boehm 的 [[N2176]]（*Memory Model Rationales*）和 [[N2177]]（*Sequential Consistency for Atomics*），以及说明编译器后果的 [[N2338]]。
- Boehm 与 Lawrence Crowl 的原子类型提案系列：[[N2145]]、[[N2381]]、[[N2393]]，以及 Peter Dimov 的 [[N2195]] 等。
- IBM 的 [[N2153]]（Silvera、Wong、McKenney、Blainey）和 Herb Sutter 代表微软提出的 [[N2197]]（*Prism*）两个替代方案。

2007 年 10 月的 Kona 会议上，全体会议以 27 票赞成、0 票反对、0 票弃权，把 [[N2429]]（*Concurrency memory model (final revision)*）并入 C++0x 工作草案（Core Motion 4），同样以 27:0:0 并入原子库 [[N2427]]（*C++ Atomic Types and Operations*，Library Motion 6）。同一次会议还通过了一个范围决议：C++0x 的并发扩展包括内存模型、原子操作、线程、锁、条件变量和异步 future 值，不包括线程池、任务启动和读写锁（Timing Motion SP2，24:1:2）。以上均见会议纪要 [[N2453]]。

两个月后，Boehm 发表 [[N2480]]（*A Less Formal Explanation of the Proposed C++ Concurrency Memory Model*），用非形式的语言解释刚通过的模型。2008 年，Boehm 与 Sarita Adve 在 PLDI 上发表 *Foundations of the C++ Concurrency Memory Model*（PLDI 2008，68–78 页），系统阐述设计理由。

### 核心思想：无数据竞争则顺序一致

Boehm 与 Adve 的论文摘要概括了模型的出发点：和 Java 类似，对语言中一个明确界定的子集，没有数据竞争的程序获得顺序一致（sequentially consistent）的语义。这个思路常被称为 DRF-SC（data-race-free implies sequential consistency）。它把责任分成两半：

- 程序员负责不写数据竞争。只要所有共享数据都由互斥量或 `seq_cst` 原子操作保护，程序的行为就像所有线程的操作简单交错执行。
- 编译器和硬件可以继续做几乎所有单线程优化，因为一个程序如果能观察到这些优化，它就一定有数据竞争，而有数据竞争的程序行为未定义。

这正是今天 [[intro.races#17]] 的注 18 所说的内容。同时，模型修补了 Boehm 2005 指出的漏洞：[[intro.memory#3]] 精确定义了内存位置（一个非位域标量对象，或一串相邻的非零宽位域），并规定不同内存位置可以被不同线程同时访问而互不干扰。编译器从此不能再把对 `a` 的写实现成对 `a`、`b` 的整体写回，除非它们是同一串相邻位域：

```cpp run title="separate_locations.cpp" ok
#include <thread>

struct S {
    char a;
    char b;      // a 和 b 是不同的内存位置
    int  x : 5;
    int  y : 11; // x 和 y 是相邻位域，属于同一个内存位置
};

S s{};

int main() {
    std::thread t1([] { s.a = 1; });
    std::thread t2([] { s.b = 2; }); // OK: 与 t1 不冲突
    t1.join(); t2.join();
}
```

如果两个线程分别写 `s.x` 和 `s.y`，那就是对同一内存位置的冲突访问，构成数据竞争。这条边界在 [[intro.memory#4]] 的注里写得很清楚，它就是 Boehm 2005 §4.2 的位域例子在标准里的答案。

有了数据竞争的定义，DCLP 一类的写法在 C++11 下也有了明确的结论：用普通变量或 `volatile` 变量做标志，就是数据竞争，行为未定义。

```cpp run title="volatile_flag.cpp" ub
#include <thread>

int payload = 0;
volatile bool ready = false;     // volatile 不是同步操作

int main() {
    std::thread producer([] {
        payload = 42;
        ready = true;
    });
    std::thread consumer([] {
        while (!ready)
            ;
        int r = payload;         // UB: 与 payload = 42 构成数据竞争
        (void)r;
    });
    producer.join();
    consumer.join();
}
```

用 Clang 的 ThreadSanitizer 运行这个程序，会报告数据竞争。正确的写法见下一节。

### 形式化：剑桥小组与 N3196

N2429 之后，剑桥大学的 Mark Batty、Scott Owens、Susmit Sarkar、Peter Sewell、Tjark Weber 等人对模型做了数学化，发现并修正了草案中的若干问题，相关结果先后写入 [[N3132]]（*Mathematizing C++ Concurrency: The Post-Rapperswil Model*，2010）和由 McKenney、Batty、Nelson 等人联合提交的 [[N3196]]（*Omnibus Memory Model and Atomics Paper*，2010 年 11 月）。学术版本发表于 POPL 2011（*Mathematizing C++ Concurrency*）。Stroustrup 在 HOPL IV 中把这项工作列为 C++11 的重要组成部分，并提到 C11 也采纳了 C++ 的内存模型（§4.1.1）。

## 为什么有 memory_order

如果只追求 DRF-SC，标准只需提供顺序一致的原子操作。但 Boehm 2005 §5 已经说明，无锁算法的价值在于避免不必要的同步开销，而在 Power、ARM 这类弱序架构上，顺序一致的原子操作需要额外的屏障指令。C++11 因此提供了逐操作指定的内存序（[[atomics.order]]）：

- `seq_cst`：默认值，参与一个全局全序，保持 DRF-SC 的简单推理；
- `acquire` / `release` / `acq_rel`：在一对读写之间建立 synchronizes with 关系，足以实现消息传递和锁；
- `relaxed`：只保证单个对象上的原子性和一致性，不建立线程间顺序，用于计数器之类的场景；
- `consume`：比 acquire 更弱，只对数据依赖于读取结果的后续操作提供顺序（见下一节）。

代价是程序员一旦使用非 `seq_cst` 的内存序，就离开了 DRF-SC 的保护，必须按 happens before 关系推理。最常见的 release/acquire 消息传递如下：

```cpp run title="message_passing.cpp" ok
#include <atomic>
#include <cassert>
#include <thread>

int payload = 0;                 // 普通变量
std::atomic<bool> ready{false};

int main() {
    std::thread producer([] {
        payload = 42;                                   // (1)
        ready.store(true, std::memory_order_release);   // (2)
    });
    std::thread consumer([] {
        while (!ready.load(std::memory_order_acquire))  // (3)
            ;
        assert(payload == 42);                          // (4) OK
    });
    producer.join();
    consumer.join();
}
```

(1) sequenced before (2)，(2) synchronizes with 读到 `true` 的那次 (3)，(3) sequenced before (4)，所以 (1) happens before (4)，两次对 `payload` 的访问不构成数据竞争（[[intro.races#7]]、[[atomics.order#2]]）。

有了原子类型，DCLP 也终于有了可移植的写法。C++11 还通过 Crowl 的 [[N2660]]（*Dynamic Initialization and Destruction with Concurrency*）规定，块作用域静态变量的初始化在并发进入时由实现负责同步（今天的 [[stmt.dcl#3]]），这使得大多数单例根本不需要手写 DCLP：

```cpp run title="dclp_cpp11.cpp" ok
#include <atomic>
#include <mutex>
#include <thread>

struct Widget { int value = 42; };

std::atomic<Widget*> instance{nullptr};
std::mutex m;

Widget* get() {
    Widget* p = instance.load(std::memory_order_acquire);
    if (p == nullptr) {
        std::lock_guard<std::mutex> lock(m);
        p = instance.load(std::memory_order_relaxed);
        if (p == nullptr) {
            p = new Widget;
            instance.store(p, std::memory_order_release);
        }
    }
    return p;
}

Widget& get2() {
    static Widget w;   // C++11 起，并发首次进入时会等待初始化完成
    return w;
}

int main() {
    std::thread a([] { (void)get()->value; (void)get2().value; });
    std::thread b([] { (void)get()->value; (void)get2().value; });
    a.join(); b.join();
    delete instance.load();
}
```

## memory_order_consume 的兴衰

### 设计初衷

`consume` 来自 Paul McKenney 等人关于数据依赖顺序的提案：[[N2359]]、[[N2360]]（2007），后来合并修订为 [[N2492]]、[[N2556]]、[[N2664]]（McKenney、Boehm、Crowl，2008），以及引入函数注解的 [[N2493]]、[[N2782]]。它的动机是 Linux 内核中大量使用的 RCU：读者通过一个指针读取数据结构，在 Power、ARM 等架构上，只要后续访问在数据上依赖于这个指针，硬件就保证顺序，不需要屏障指令。`consume` 想把这种廉价的顺序暴露给 C++ 程序。

为此，C++11 的 [intro.races] 引入了 carries a dependency、dependency-ordered before、inter-thread happens before 等关系，happens before 的定义也随之变得复杂，并且失去了传递性，需要另外定义 simply happens before 等辅助关系。语言层面还加了 `[[carries_dependency]]` 属性和 `std::kill_dependency` 函数，用于在函数边界上传递或截断依赖链。

### 实现上的困难

问题在于，标准对依赖的定义是源代码层面的：一个值作为另一个求值的操作数就算依赖。而编译器优化会消除依赖，例如在 `p->a[x - x]` 中把下标折叠成常数。要按标准实现 `consume`，编译器必须在整个依赖链上跟踪这类关系，跨函数时还要依赖 `[[carries_dependency]]` 注解。Boehm 在 [[P3475R2]] 中总结说，所有现有编译器实际上都把 `consume` 当作 `acquire` 处理；困难来自实现复杂度、过于宽泛的依赖定义（要求频繁使用 `kill_dependency`），以及频繁需要的 `[[carries_dependency]]` 注解。

### C++17：暂时不鼓励

2016 年，Boehm 提出 [[P0371R0]]（*Temporarily deprecate memory_order_consume*）。按 P3475R2 的记述，SG1 不赞成这个方向；修订后的 [[P0371R1]]（*Temporarily discourage memory_order_consume*）在 2016 年 6 月的 Oulu 会议上通过（会议信息据 libc++ 的 C++17 状态页）。它没有改变语义，只在 [[atomics.order]] 加了一条注，建议优先使用 `memory_order_acquire`，说明实现无法提供比 acquire 更好的性能，并说规范修订正在考虑中（C++17 定稿草案 N4659 的 [atomics.order]/1.3 注）。

之后的十年里，McKenney 等人提出过多种替代方案，例如 [[P0098R1]]（*Towards Implementation and Use of memory_order_consume*）、[[P0190R4]]（*Proposal for New memory_order_consume Definition*）、[[P0462R1]]（*Marking memory_order_consume Dependency Chains*）、[[P0750R1]]（*Consume*），但委员会没有就任何一个达成共识（P3475R2，Rationale 第 1 点）。

### C++26：拔牙并弃用

2024 年，Boehm 提交 [[P3475R0]]（*Defang and deprecate memory_order::consume*）。按 P3475R2 的记述，R0 在 2024 年 11 月的 Wrocław 会议上获得 SG1 和 EWG 无异议通过；R2 列在 libc++ C++2c 状态页的 2025 年 2 月 Hagenberg 会议一栏。论文给出的理由有四点：问题已经存在约十年而没有替代方案；`consume` 显著增加了内存模型的复杂度，学术界的形式化工作往往直接忽略它，使研究成果难以转化回标准；主流架构已不太需要它，x86 上本来就没有收益，ARM 的硬件 acquire 读在常见场景下性能接近 relaxed 读，RISC-V 也在朝同一方向发展（Zalasr 扩展），仍能受益的主要是 Power 和 GPU；剩下的使用场景在实践中靠不可移植地、非常小心地滥用 `memory_order_relaxed` 解决。

P3475R2 的修改是：

- 删除 [intro.races] 中 carries a dependency、dependency-ordered before、inter-thread happens before 的定义，以及旧的 happens before 定义，把 simply happens before 改名为 happens before；
- 整个删除 `[[carries_dependency]]` 属性（论文认为不必弃用，残留的用法会被当作未知属性忽略）；
- 从 `memory_order` 枚举的正文定义中去掉 `consume`，给其余枚举量显式赋值以保持二进制兼容；
- 在附录 D 新增 [[depr.atomics.order]]：`memory_order::consume` 仍然存在，值为 1，凡是允许 `acquire` 的地方都允许它，含义与 `acquire` 相同；`kill_dependency(y)` 直接返回 `y`。

```cpp run title="consume_today.cpp" ok
#include <atomic>

struct Node { int v; };
std::atomic<Node*> head{nullptr};

int read() {
    Node* p = head.load(std::memory_order_consume); // 已弃用：与 acquire 同义
    return p ? p->v : 0;
}

int main() { return read(); }
```

这段代码在当前草案下良构，`consume` 读取就是一次 acquire 读取。截至写作时，本机 Clang 23（libc++）编译它不报弃用警告。

## 凭空出现的值

DRF-SC 之外还有一个至今没有完全解决的问题：relaxed 原子操作可能产生凭空出现的值（out-of-thin-air，OOTA）。经典例子是两个线程分别把对方写过的值拷贝回去：

```cpp title="OOTA 示意（改写自 [atomics.order] 注 5）"
// x、y 是 std::atomic<int>，初值都是 0
// 线程 1：
r1 = y.load(std::memory_order::relaxed);
x.store(r1, std::memory_order::relaxed);
// 线程 2：
r2 = x.load(std::memory_order::relaxed);
y.store(r2, std::memory_order::relaxed);
```

`r1 == r2 == 42` 这样的结果在直觉上不可能出现，因为 42 无从产生；但仅凭 happens before 和一致性规则，形式模型无法排除它，因为两次读取可以循环地互相为对方的写入提供理由。

C++11 的措辞（以 C++11 发布后的草案 N3337 为准）试图用规范性要求禁止这种结果：原子写只能写入由常量和程序输入经过有限步求值算出的值。Boehm 等人在 [[N3786]]（*Prohibiting "out of thin air" results in C++14*，2013）中指出，这条要求表述不当，而且可以理解为禁止了 ARM 和 Power 上 `relaxed` 的所有合理实现；他们承认在大约十年的尝试之后，仍不知道怎样精确地表述这项要求而不损害性能。于是 C++14 改成一条建议：实现应当保证不计算出循环依赖于自身计算的凭空值（C++14 定稿草案 N4140 的 [atomics.order]/9）。当前草案的 [[atomics.order#8]] 和 [[atomics.order#9]] 保留了这一措辞和两个例子。

这个问题的学术讨论一直在继续，WG21 文档中可以看到 [[N3710]]（*Specifying the absence of "out of thin air" results*）、McKenney 等人的 [[N4216]] 与 [[P0422R0]]（*Out-of-Thin-Air Execution is Vacuous*）、Boehm 的 [[P1217R2]]（*Out-of-thin-air, revisited, again*，2019）和 David Goldblatt 的 [[P1916R0]]（*There might not be an elegant OOTA fix*，2019）。截至当前草案，标准仍然只是建议，而不是规定。

## 线程库：从 Boost.Thread 到 std::thread

### 来源

据 Stroustrup 记述，第一份线程库提案是 Pete Becker（Dinkumware）2004 年的 [[N1682]]，它基于 Dinkumware 对 `boost::thread` 接口的实现（HOPL IV，§4.1.2）。Boost.Thread 本身最初由 William E. Kempf 设计实现；后来 Anthony Williams 对它做了大规模重写，Boost 文档说明这次重写刻意紧跟提交给标准委员会的提案，列出的文档包括 [[N2497]]、[[N2320]]、[[N2184]]、[[N2094]] 等（Boost.Thread 文档，Overview 与致谢部分）。

此后的标准化文档包括 Crowl 的 [[N1815]]（*ISO C++ Strategic Plan for Multithreading*）和 [[N1875]]、Becker 的修订版 [[N1907]]、Howard Hinnant 的 [[N2094]]（*Multithreading API for C++0X - A Layered Approach*）与 [[N2184]]、Dimov 的 [[N2090]] 与 [[N2178]]，最终汇总为 Hinnant、Dawes、Crowl、Garland、Williams 等人的 [[N2320]]、[[N2447]] 与 [[N2497]]（*Multi-threading Library for Standard C++ (Revision 1)*，2008 年 1 月）。Kona 会议纪要记录了 N2447 被指定编辑与审阅小组、转交项目编辑并入工作草案（Library Motion 14，25:1:1）；Boehm 的 C++ 内存模型主页把 N2497 列为已并入工作草案的线程库提案。互斥量与锁的设计理由见 Hinnant 的 [[N2406]]（*Mutex, Lock, Condition Variable Rationale*）。

Stroustrup 指出，这套库的类型安全接口在很大程度上依赖同期加入语言的可变参数模板和 lambda，例如 `std::thread` 的构造函数就是一个可变参数模板（HOPL IV，§4.1.2）。

### 取消之争

据 Stroustrup 记述，线程库最大的争议是线程取消（cancellation）。委员会中的 C++ 程序员几乎都希望有某种形式的取消；C 委员会（WG14）就此向 WG21 发出过正式意见表示反对，Stroustrup 说这是 WG14 唯一一次向 WG21 发出正式意见；管理 POSIX 的 Austin Group 的代表也认为取消既不必要也无法安全实现（HOPL IV，§4.1.2）。C++11 最终没有提供取消机制。这个空缺要到 C++20 的 stop token 才以协作式取消的形式补上（见下文）。

### ~thread 为什么调用 terminate

2008 年的草案曾规定，`std::thread` 析构时若仍 joinable 就自动 `detach()`。Boehm 在 [[N2802]]（*A plea to reconsider detach-on-destruction for thread objects*，2008 年 12 月）中指出，如果在创建线程和 join 之间抛出异常，被 detach 的线程可能继续写已经销毁的栈变量，造成难以调试的内存破坏。论文给出两个替代方案：析构时 `join()`，或析构时 `terminate()`；他写到多数反馈倾向后者。C++11 最终采用了 `terminate()`。当前草案 [[thread.thread.destr]] 的注仍然解释了这一选择：析构时隐式 detach 会导致难以调试的正确性问题，隐式 join 会导致只在抛异常时才出现的性能问题。

### thread_local

线程局部存储由 Crowl 的 [[N1966]]、[[N2147]]、[[N2659]]（*Thread-Local Storage*）提出，成为 C++11 的 `thread_local` 存储类说明符和线程存储期（[[dcl.stc]]、[[basic.stc.thread]]）。Williams 的 [[N3070]]（*Handling Detached Threads and thread_local Variables*，2010）处理了 detach 的线程与 `thread_local` 析构之间的交互。

## future 与 async：Kona 折中和阻塞析构之争

### Kona 折中

据 Stroustrup 回忆，委员会当时分成两派：一派基本上只想要类型更安全的 POSIX，另一派认为 POSIX 是 1970 年代的设计，需要更高层的设施。他和 Matt Austern 主张提供消息队列和线程池，但没有成功。2007 年 Kona 会议达成的折中是：C++0x 提供 promise、future，以及一个允许但不要求使用线程池的异步任务启动函数 `async()`。他称之为 Kona 折中，说它谁都不满意，也带来了一些技术问题（HOPL IV，§4.1.3）。

future 的设计经过 Dimov 的 [[N2096]]、[[N2185]]，Vollmann、Hinnant、Williams 的 [[N2627]]、[[N2671]]，以及 Williams 的 [[N2709]]（*Packaging Tasks for Asynchronous Execution*）。`std::async` 则由 Crowl 的 [[N2889]]、[[N2973]] 和 Sutter 的 [[N2901]]、[[N2970]] 两条线合并为 [[N2996]]（*A Simple Asynchronous Call*，Crowl 与 Sutter，2009 年 10 月）。N2996 已经规定：如果 future 是最后一个引用由 `async` 创建的线程的共享状态，它的析构函数如同对该线程执行 `join()`（[[N3058]] 是后续的清理修订）。

### 阻塞析构之争

这条规则让 `async` 返回的 future 与其他 future 行为不同：其他来源的 future 析构时从不阻塞，而这一种可能阻塞。2012 年，Sutter 在 [[N3451]]（*async and ~future*）中提出，这种差异让使用 future 的代码无法组合：拿到一个 future 的函数不知道它是否来自 `async`，也就不知道析构时会不会等待；不少用户以为写了并发代码，实际上每次调用都在原地等待。

此后的发展有文档可查：

- 2013 年 4 月 Bristol 会议前后，Sutter 提交 [[N3630]]（*async, ~future, and ~thread*）、[[N3636]]（*~thread should join*），修订为引入 `waiting_future` 类型的 [[N3637]]。据 Anthony Williams 的会议报告，这一提案在 SG1 讨论后，在全体会议上也被否决，原因是认为它对现有代码的破坏太大（Williams，*ACCU 2013 and the C++ Standards Meeting*，2013 年 5 月）。
- Boehm 在 [[N3679]]（*Async() future destructors must wait*，2013 年 5 月）中给出反方的技术理由：如果析构不等待，任务可能在它使用的数据被销毁之后继续运行；与普通的悬垂引用不同，这类错误由疏忽引发，一个意外的异常就可能触发，测试中难以发现，还可能被利用。
- 2013 年 9 月 Chicago 会议前，Sutter、Chandler Carruth、Niklas Gustafsson 提交 [[N3773]]（*async and ~future (Revision 4)*），同时提供两份措辞：改变 `~future` 的 [[N3776]]，以及弃用 `async` 的 [[N3777]]。Nicolai Josuttis 的 [[N3780]]（*Why Deprecating async() is the Worst of all Options*）反对弃用。isocpp.org 对 N3777 的说明是：该文没有在 Chicago 会议上通过。

结果是规则一直保留到今天。当前草案 [[futures.state#5]] 规定释放共享状态的操作不会为等待就绪而阻塞，唯一的例外是：共享状态由 `std::async` 创建、尚未就绪、且这是最后一个引用；[[futures.async]] 的注 2 也提醒，从 `async` 得到的 future 被移出局部作用域后，它的析构函数可能阻塞。Meyers 在 *Effective Modern C++*（2014）条款 38 中专门讨论了线程句柄析构行为的这种差异。

```cpp run title="async_blocks.cpp" ok
#include <chrono>
#include <future>
#include <iostream>
#include <thread>

using namespace std::chrono_literals;

int main() {
    auto t0 = std::chrono::steady_clock::now();
    {
        auto f = std::async(std::launch::async, [] { std::this_thread::sleep_for(200ms); });
    }   // f 的析构函数在这里等待任务结束
    auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now() - t0).count();
    std::cout << (ms >= 200 ? "blocked\n" : "did not block\n");
}
```

本机运行输出 `blocked`。

### then、执行器与 std::execution

为 future 增加续接（`.then()`）等组合操作的提案有 [[N3428]]、[[N3721]]、[[N3857]]、[[N3865]]，这些设施进入了 Concurrency TS（[[N4577]]，2016），但没有并入正式标准。更通用的异步模型转向了执行器（executors），从 [[N4045]]、[[P0443R14]] 一路演变为 [[P2300R10]]（`std::execution`）。libc++ 的 C++2c 状态页把 P2300 列在 2024 年 6 月 St. Louis 会议，即 C++26 的 [[exec]]。这段历史足够另写一页，这里不展开。

## C++14 与 C++17：读写锁、scoped_lock、并行算法

Kona 2007 的范围决议把读写锁排除在 C++11 之外。Hinnant、Vollmann、Boehm 的 [[N3659]]（*Shared locking in C++*）在 2013 年 4 月 Bristol 会议上通过（isocpp.org 的“New adopted paper”公告），当时的类名是 `shared_mutex`。由于这个类支持带超时的加锁，Gor Nishanov 与 Sutter 在 [[N3891]] 中提议把它改名为 `shared_timed_mutex`，为将来不带超时、可能更高效的版本留出名字。C++14 的定稿草案 N4140 中这个类名就是 `shared_timed_mutex`（[[thread.sharedtimedmutex.class]]）。不带超时的 `shared_mutex` 由 [[N4508]] 加入 C++17，libc++ 的状态页把它列在 2015 年 5 月 Lenexa 会议（[[thread.sharedmutex.class]]）。

C++17 的 `std::scoped_lock`（[[thread.lock.scoped]]）来自 Mike Spertus 的 [[P0156R2]]。提案最初是把 `lock_guard` 改成可变参数模板；P0156R2 说明，由于国家成员体意见 GB 61 和 FI 8 担心破坏 ABI，改为引入一个新名字。libc++ 状态页把它列在 2017 年 2 月 Kona 会议。

并行算法的源头是 Hoberock、Giroux、Grover、Sutter 等人的 [[N3554]]（*A Parallel Algorithms Library*，2013），先进入 Parallelism TS（[[N4507]]，2015），再由 [[P0024R2]]（*The Parallelism TS Should be Standardized*）在 2016 年 2 月 Jacksonville 会议并入 C++17（[[algorithms.parallel]]、[[execpol]]）。执行策略的名字由 [[P0336R1]] 定为今天的 `seq`、`par`、`par_unseq`。为了说明并行算法中的元素访问函数能指望什么样的进展，Torvald Riegel 的 [[P0296R2]]（*Forward progress guarantees: Base definitions*）给出了今天 [[intro.progress]] 中前进保证的基础定义；C++17 定稿草案 N4659 已包含 [intro.progress] 这一节。C++11 时期的前进保证则来自 Boehm 与 Pablo Halpern 的 [[N3209]]（*Progress guarantees for C++0x*）。

同样进入 C++17 的还有 [[P0154R1]] 的 `hardware_destructive_interference_size` 与 `hardware_constructive_interference_size`（[[hardware.interference]]），以及前面提到的 [[P0371R1]]。

关于可 join 的线程，据 Stroustrup 记述，Sutter 在 2012、2013 年提出过 joining thread，引起很多讨论但没有决定；2016 年 Ville Voutilainen 整理了问题并组织投票（[[P0206R1]]，*A joining thread*；反方意见见 Detlef Vollmann 的 [[P0379R0]]），投票结果大比例赞成，但进展又停了下来（HOPL IV，§9.4）。

## C++20：jthread、等待与同步原语

### jthread 与 stop_token

2017 年，Nicolai Josuttis 提交 [[P0660R0]]（*A Cooperatively Interruptible Joining Thread*）。这个提案把两件事放在一起：析构时自动 join 的线程，和协作式取消。经过十次修订，[[P0660R10]]（*Stop Token and Joining Thread*，Josuttis、Lewis Baker、Billy O'Neal、Sutter、Williams）在 2019 年 7 月 Cologne 会议上通过（libc++ C++20 状态页）。Stroustrup 记下了命名的变迁：`safe_thread`、`ithread`、`raii_thread`、`joining_thread`，最后定为 `jthread`（HOPL IV，§9.4）。随后 [[P1869R1]] 调整了 `condition_variable_any` 可中断等待函数的名字。

`std::jthread`（[[thread.jthread.class]]）析构时先请求停止，再 join。停止请求通过 [[thread.stoptoken]] 中的 `stop_source`、`stop_token`、`stop_callback` 传递，线程函数需要自己定期检查，这正是 Stroustrup 所说的协作式取消。它回避了 C++11 时期的取消之争：没有任何线程会被从外部强行终止。

```cpp run title="jthread_stop.cpp" ok
#include <chrono>
#include <iostream>
#include <stop_token>
#include <thread>

using namespace std::chrono_literals;

int main() {
    std::jthread worker([](std::stop_token st) {
        int n = 0;
        while (!st.stop_requested()) {
            ++n;
            std::this_thread::sleep_for(1ms);
        }
        std::cout << "stopped after " << (n > 0 ? "some" : "no") << " iterations\n";
    });
    std::this_thread::sleep_for(20ms);
}   // ~jthread: 先 request_stop()，再 join()
```

### 等待、信号量、闩与屏障

[[P1135R6]]（*The C++20 Synchronization Library*，Olsen、Giroux、Bastien、Vollmann、Lelbach）同样在 Cologne 会议通过。它把几份提案合并为一份：Olivier Giroux 的 [[P0514R4]]（*Efficient concurrent waiting for C++20*，原子等待与信号量）、[[P0666R2]]（*Revised Latches and Barriers for C++20*）、[[P0995R1]]（*Improving atomic_flag*）。加入的设施有：`atomic` 与 `atomic_flag` 的 `wait` / `notify_one` / `notify_all`（[[atomics.wait]]）、`atomic_flag::test`、无锁整数别名 `atomic_signed_lock_free` 与 `atomic_unsigned_lock_free`、`counting_semaphore` 与 `binary_semaphore`（[[thread.sema]]）、`latch`（[[thread.latch]]）和 `barrier`（[[thread.barrier]]）。`atomic_ref` 和 `atomic<shared_ptr>` 的等待操作由 [[P1643R1]] 和 [[P1644R0]] 补上。latch 和 barrier 早先已经在 Concurrency TS 中出现过（[[N4204]]、[[N4392]]）。

```cpp run title="sync20.cpp" ok
#include <atomic>
#include <barrier>
#include <latch>
#include <semaphore>
#include <thread>
#include <vector>

int main() {
    std::atomic<int> flag{0};
    std::latch done(3);
    std::counting_semaphore<2> slots(2);
    std::barrier sync(3);
    int data[3] = {};

    std::vector<std::jthread> ts;
    for (int i = 0; i < 3; ++i)
        ts.emplace_back([&, i] {
            flag.wait(0);                 // 阻塞，直到 flag 不再等于 0
            slots.acquire();              // 最多两个线程同时进入
            data[i] = i;
            slots.release();
            sync.arrive_and_wait();       // 三个线程在此汇合
            done.count_down();
        });
    flag.store(1);
    flag.notify_all();
    done.wait();
}
```

### atomic_ref 与 atomic&lt;shared_ptr&gt;

`std::atomic_ref`（[[atomics.ref.generic]]）让程序对一个普通对象临时施加原子访问，主要需求来自高性能计算：一个大数组在某个阶段只被单线程访问，在另一个阶段需要原子更新。它最初以 *Atomic View* 为名提出（[[P0019R0]]，Edwards、Boehm、Giroux、Reus，2015），[[P0019R8]] 在 2018 年 6 月 Rapperswil 会议通过（libc++ C++20 状态页）。

```cpp run title="atomic_ref.cpp" ok
#include <atomic>
#include <thread>

int counter = 0;   // 普通 int，没有声明为 atomic

int main() {
    auto work = [] {
        for (int i = 0; i < 1000; ++i)
            std::atomic_ref<int>(counter).fetch_add(1, std::memory_order_relaxed);
    };
    std::thread a(work), b(work);
    a.join(); b.join();
    return counter == 2000 ? 0 : 1;   // 两个线程都已 join，普通读取不构成数据竞争
}
```

`shared_ptr` 的原子访问在 C++11 中以一组自由函数提供（`atomic_load(const shared_ptr<T>*)` 等）。Sutter 在 [[N4058]]、[[N4162]]（*Atomic Smart Pointers*，2014）中提出原子智能指针类型，`atomic_shared_ptr` 先进入 Concurrency TS（[[N4577]]）。Alisdair Meredith 的 [[P0718R2]]（*Revising atomic_shared_ptr for C++20*）把它改为 `atomic<shared_ptr<T>>` 与 `atomic<weak_ptr<T>>` 两个偏特化，在 2017 年 11 月 Albuquerque 会议通过（[[util.smartptr.atomic]]）。C++20 的定稿草案 N4861 把旧的自由函数放进了附录 D（[depr.util.smartptr.shared.atomic]）；[[P2869R4]] 提议在 C++26 中删除它们，当前草案中已经没有这些函数。

### 内存模型的修补

C++20 还对内存模型本身做了两处修改，二者都列在 San Diego 会议（2018 年 11 月）的编辑报告 [[N4792]] 中，分别是 CWG 动议 2 和 3：

- [[P0668R5]]（*Revising the C++ memory model*，Boehm、Giroux、Vafeiadis）。它的早期修订指出，Power 和 ARM 上的现有实现方案并不符合当时对 `seq_cst` 的定义。C++17 已有 strongly happens before 一词，但在没有 consume 时它与 happens before 相同（N4659 的 [intro.races]/11）；P0668R5 把旧定义改名为 simply happens before，给 strongly happens before 换上今天的定义（[[intro.races#8]]，其中 synchronizes with 只在两端都是 `seq_cst` 操作时才计入），并据此重写了 `seq_cst` 全序 S 的约束（[[atomics.order#4]]）。
- [[P0982R1]]（*Weaken release sequences*）。release sequence 不再包括同一线程中后续的普通写，只包括原子读-改-写操作（今天的 [[intro.races#5]]）。

其他较小的改动包括 [[P0020R6]] 的浮点原子类型、[[P0528R3]] 关于 compare-exchange 与填充位的修正、[[P0883R2]] 对 `atomic` 默认初始化的修正。C++23 则通过 [[P0943R6]]（*Support C atomics in C++*）提供了 `<stdatomic.h>`，让 C 与 C++ 能共享使用 `_Atomic` 的头文件。

## C++26：安全回收、原子 min/max 与 consume 的终局

### hazard pointer 与 RCU

无锁数据结构的一个老问题是内存回收：一个线程把节点从链表上摘下后，什么时候可以 `delete` 它？其他线程可能仍在读这个节点。hazard pointer（Maged Michael，2004 年发表）和 RCU（McKenney 等人，用于 Linux 内核）是两种经典的延迟回收方案。

它们进入 WG21 的过程比较长。hazard pointer 的提案始于 [[P0233R0]]（Michael、Wong，2016），RCU 始于 [[P0279R0]]（McKenney，2016）与 [[P0461R0]]，二者曾合并为 [[P0566R5]] 的措辞，后来分别以 [[P1121R3]] 和 [[P1122R4]] 进入 Concurrency TS 2 的工作草案（[[N4895]]，2021）。2022 年，作者们提交 [[P2530R0]]（*Why Hazard Pointers should be in C++26*）和 [[P2545R0]]（*Why RCU Should be in C++26*），主张不等 TS 而直接进入 IS。libc++ 的 C++2c 状态页把 [[P2530R3]] 和 [[P2545R4]] 都列在 2023 年 6 月 Varna 会议。

P2530R3 说明，提议的 hazard pointer 接口是 TS2 接口的一个子集，参考实现在 Facebook 的 Folly 库中，自 2017 年起在生产环境大量使用。它省略了两部分：自定义域（custom domain）和全局清理函数 `hazard_pointer_clean_up`，即同步回收。理由是 Folly 的经验表明常见用法不需要它们，而且省略不妨碍将来再加。今天这两套设施位于 [[saferecl]]：`hazard_pointer_obj_base`、`hazard_pointer`、`make_hazard_pointer`（[[saferecl.hp]]）与 `rcu_obj_base`、`rcu_domain`、`rcu_synchronize`、`rcu_retire`（[[saferecl.rcu]]）。

### 原子操作的补充

C++26 给原子类型增加了若干操作：

- [[P0493R5]]（*Atomic maximum/minimum*）：`fetch_max` 与 `fetch_min`，libc++ 状态页列在 2024 年 3 月 Tokyo 会议。这个提案的 R0 早在 2016 年就已提交。
- [[P3008R6]]（*Atomic floating-point min/max*）与 [[P3111R8]]（*Atomic Reduction Operations*，即 `store_add`、`store_max` 等不返回旧值的归约操作），均列在 2025 年 6 月 Sofia 会议。
- [[P2835R7]]（`atomic_ref::address()`）与 [[P3323R1]]（`atomic` 和 `atomic_ref` 支持 cv 限定类型），均列在 2024 年 11 月 Wrocław 会议。

```cpp title="fetch_max.cpp（C++26）"
#include <atomic>
#include <thread>

std::atomic<int> high{0};

int main() {
    std::thread a([] { high.fetch_max(17); });
    std::thread b([] { high.fetch_max(42); });
    a.join(); b.join();
    return high.load() == 42 ? 0 : 1;
}
```

按当前草案这段代码良构，程序返回 0。截至写作时，本机的 Clang 23 + libc++ 尚未提供 `atomic<int>::fetch_max`，也没有 `<hazard_pointer>` 与 `<rcu>` 头文件，因此本页没有在本机验证这些 C++26 例子。

### consume 的终局与前进保证

前文已经讲过，[[P3475R2]] 在 C++26 中让 `consume` 等同于 `acquire` 并移入附录 D，[intro.races] 的 happens before 恢复为一个简单的传递闭包。

C++26 还通过 [[P2809R3]]（*Trivial infinite loops are not Undefined Behavior*）修改了 [[intro.progress#1]]：实现可以假设线程最终会做某些事，现在多了一项继续执行平凡无限循环（trivial infinite loop，见 [[stmt.iter.general]]）。这样 `while (true) {}` 这类循环不再因为前进假设而导致未定义行为。Clang 的 C++ 状态页把 P2809R3 列在 C++2c 一栏。

## 回到 [intro.races]：历史怎样留在今天的措辞里

把上面的历史和当前草案的 [[intro.races]] 对照，可以看出每一段从哪里来。

| 当前草案 | 内容 | 历史来源 |
|---|---|---|
| [[intro.memory#3]]、[[intro.memory#4]] | 内存位置的定义；不同内存位置可以被并发访问而互不干扰 | Boehm 2005 §4.2 的相邻数据改写问题；N2429 |
| [[intro.races#2]] | 冲突的定义：一个修改、另一个读写同一内存位置 | pthreads 关于不得在他人修改时读写的规则被形式化 |
| [[intro.races#3]] | 库定义的同步操作：acquire、release、fence；relaxed 原子不是同步操作 | pthreads 列出的同步内存函数；N2427 的原子库；HOPL IV 记述的栅栏之争 |
| [[intro.races#5]] | release sequence 只由原子读-改-写构成 | C++20 的 [[P0982R1]] |
| [[intro.races#7]] | happens before 是 sequenced before 与 synchronizes with 的传递闭包 | C++26 的 [[P3475R2]] 删去 consume 相关关系后的简化 |
| [[intro.races#8]] | strongly happens before 的现行定义 | C++20 的 [[P0668R5]] |
| [[intro.races#11]]–[[intro.races#14]] | 四条一致性要求 | C++11 起，N3196 等形式化工作的结果 |
| [[intro.races#17]] | 数据竞争的定义；数据竞争导致未定义行为；注 18 说明无竞争程序表现为顺序一致 | Boehm 与 Adve 的 DRF-SC 设计；Boehm 2005 §3 关于有竞争程序可以无定义的论证 |
| [[intro.races#18]] | 同一线程内对 `volatile std::sig_atomic_t` 的访问不构成数据竞争 | 与信号处理函数的兼容 |
| [[atomics.order#8]]、[[atomics.order#9]] | 不产生凭空值的建议 | C++14 的 [[N3786]]；OOTA 问题至今未解决 |
| [[depr.atomics.order]] | `consume` 与 `acquire` 同义 | [[P0371R1]] 与 [[P3475R2]] |

还有一处小痕迹：[[intro.races#3]] 的注 3（非规范性）仍然说 release 操作使之前的副作用对之后执行 consume 或 acquire 操作的线程可见。consume 已经与 acquire 同义，这句话的含义没有变，只是保留了旧的写法。

另外值得注意的是 [[intro.races#1]] 的注 1：这一节的大部分内容是为支持带显式可见性约束的原子操作而写的，但它也隐含地支持一种更简单的视角。这正是 Boehm 与 Adve 设计的两层结构：只用互斥量和 `seq_cst` 原子的程序员可以停留在顺序一致的世界里；使用较弱内存序的专家才需要处理 happens before 的全部细节。

## 时间线

| 年份 | 事件 | 文档 |
|---|---|---|
| 1998 | C++98 发布，标准描述单线程抽象机，没有线程概念 | ISO/IEC 14882:1998 |
| 2004 | Redmond 会议：第一份内存模型提案与第一份线程库提案 | [[N1680]]、[[N1682]] |
| 2004 | Meyers 与 Alexandrescu 分析 DCLP 在 C++ 中无法可移植实现 | Dr. Dobb's Journal，2004 年 7、8 月 |
| 2005 | Boehm 发表 *Threads Cannot Be Implemented As a Library* | PLDI 2005 |
| 2005–2006 | 内存模型问题清单、状态更新与 strawman 提案；线程 API 提案 | [[N1777]]、[[N1876]]、[[N1942]]、[[N1907]]、[[N2094]] |
| 2007 | Kona 会议：内存模型与原子库并入工作草案；Kona 折中确定 future 与 async | [[N2429]]、[[N2427]]、[[N2453]] |
| 2007 | Boehm 的非形式化说明 | [[N2480]] |
| 2008 | 线程库并入；consume 与依赖顺序；thread_local；Boehm 与 Adve 的 PLDI 论文 | [[N2497]]、[[N2664]]、[[N2782]]、[[N2659]] |
| 2008 | 提议把 ~thread 的 detach 改为 join 或 terminate | [[N2802]] |
| 2009 | std::async 定稿，future 析构可能阻塞 | [[N2996]] |
| 2010 | 剑桥小组的形式化与综合修订 | [[N3132]]、[[N3196]] |
| 2011 | C++11 发布 | — |
| 2012–2013 | async 与 ~future 之争：改变 ~future、弃用 async 的提案均未通过 | [[N3451]]、[[N3637]]、[[N3679]]、[[N3773]]、[[N3777]]、[[N3780]] |
| 2013 | 共享锁通过；OOTA 措辞改为建议 | [[N3659]]、[[N3786]] |
| 2014 | C++14 发布，`shared_timed_mutex` | [[N3891]] |
| 2015–2016 | Parallelism TS 与 Concurrency TS 发布 | [[N4507]]、[[N4577]] |
| 2016 | 并行算法并入 C++17；consume 暂时不鼓励使用 | [[P0024R2]]、[[P0371R1]] |
| 2015–2017 | `shared_mutex`、`scoped_lock` | [[N4508]]、[[P0156R2]] |
| 2017 | C++17 发布 | — |
| 2017–2018 | `atomic<shared_ptr>`、`atomic_ref`、内存模型修订 | [[P0718R2]]、[[P0019R8]]、[[P0668R5]]、[[P0982R1]] |
| 2019 | jthread 与 stop_token；C++20 同步库 | [[P0660R10]]、[[P1135R6]] |
| 2020 | C++20 发布 | — |
| 2023 | hazard pointer 与 RCU 进入 C++26 草案 | [[P2530R3]]、[[P2545R4]] |
| 2024 | 原子 min/max；std::execution；平凡无限循环不再是 UB | [[P0493R5]]、[[P2300R10]]、[[P2809R3]] |
| 2025 | consume 被拔牙并弃用；原子归约操作 | [[P3475R2]]、[[P3111R8]] |

## 现状与未来

以下工作在 WG21 文档中仍有新修订，截至写作时尚未进入标准草案。

- hazard pointer 的同步回收：[[P3427R9]]（*Hazard Pointer Synchronous Reclamation*，Michael、Wong、McKenney、de Wever，2026 年 9 月）对应 P2530R3 当初从 TS2 接口中省略的全局清理功能。
- 指针生命周期结束后的指针值：[[P1726R5]]（*Pointer lifetime-end zap*，信息性文档）与 [[P2414R12]]（*Pointer lifetime-end zap proposed solutions*，2026 年 6 月）讨论这样一个问题：指针所指对象的生命周期结束后，指针值变为无效，这与许多无锁算法（例如比较一个可能已失效的指针）的实际写法冲突。
- 字节粒度的原子 memcpy：[[P1478R8]]（*Byte-wise atomic memcpy*，Boehm）面向 seqlock 一类的算法。libc++ 的 C++23 状态页把它与 [[P2396R1]]（*Concurrency TS 2 fixes*）列在同一次会议（2022 年 11 月 Kona）下，后者是 Concurrency TS 2（[[N4953]]，2023）的修正；当前 IS 草案中没有对应的函数。
- 原子等待的超时版本等改进：[[P2643R2]]（*Improving C++ concurrency features*，2024）提出了这类扩展，当前草案的 [[atomics.wait]] 中还没有带超时的等待函数。
- OOTA：如前文所述，[[atomics.order#8]] 仍然只是建议，[[P1217R2]] 等文档讨论过可能的规范化方案，尚无结论。

此外，`memory_order::consume` 在附录 D 中仍然保留。P3475R2 说明，依赖顺序在 Linux 内核的 RCU 和部分 Android 核心代码中仍有重要用途，Power 和 GPU 仍可能从中受益；委员会今后是否会为它设计一个可实现的替代品，目前没有已提交的方案。

## 参考资料

WG21 文档以正文中的编号为准，构建时自动链接到 wg21.link。主要的非 WG21 来源：

- Hans-J. Boehm. *Threads Cannot Be Implemented As a Library*. PLDI 2005, pp. 261–268. 早期版本为 HP Labs 技术报告 HPL-2004-209。
- Hans-J. Boehm, Sarita V. Adve. *Foundations of the C++ Concurrency Memory Model*. PLDI 2008, pp. 68–78.
- Mark Batty, Scott Owens, Susmit Sarkar, Peter Sewell, Tjark Weber. *Mathematizing C++ Concurrency*. POPL 2011.
- Scott Meyers, Andrei Alexandrescu. *C++ and the Perils of Double-Checked Locking*, Part I 与 Part II. Dr. Dobb's Journal, 2004 年 7 月、8 月。
- Bjarne Stroustrup. *Thriving in a Crowded and Changing World: C++ 2006–2020*. Proc. ACM Program. Lang. 4, HOPL (2020)，§4.1（C++11 的并发支持）、§8.5（并行 STL）、§9.4（C++20 的并发）。
- Hans-J. Boehm. *Threads and memory model for C++*（个人主页 hboehm.info/c++mm，列出内存模型工作的文档与参与者）。
- Anthony Williams. *ACCU 2013 and the C++ Standards Meeting*. Just Software Solutions 博客，2013 年 5 月。
- isocpp.org 对 N3777 与 N3659 的公告（2013）。
- Boost.Thread 文档（Overview 与 Acknowledgments 部分）。
- GCC 4.1.2 手册，*Atomic Builtins*；Microsoft Learn，*volatile (C++)*。
- Scott Meyers. *Effective Modern C++*. O'Reilly, 2014，条款 38。
- 会议归属信息：libc++ 的 C++17、C++20、C++23、C++2c 状态页（LLVM 21.1.0 文档），Clang 的 C++ 支持状态页，WG21 会议纪要 [[N2453]] 与编辑报告 [[N4792]]。
- 历史版本标准措辞：C++11 后草案 N3337、C++14 定稿草案 N4140、C++17 定稿草案 N4659、C++20 定稿草案 N4861（timsong-cpp.github.io/cppwp）。
