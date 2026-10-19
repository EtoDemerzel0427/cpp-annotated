---
title: 从 pthreads 到 C++26：线程与内存模型
summary: C++ 怎样从一门不知道线程存在的语言，变成标准里定义了数据竞争和内存序的语言；为什么选择无数据竞争即顺序一致，consume 和凭空值为什么没能解决好，thread、async、jthread 的析构行为又是哪些争论的结果。
status: draft
order: 20
since: c++11
papers: N2429, N2427, N2480, N2802, N3451, N3679, N3786, P0371R1, P0660R10, P0668R5, P0982R1, P1135R6, P2530R3, P2545R4, P2809R3, P3475R2
related: intro.multithread, intro.races, intro.memory, intro.progress, atomics.order, thread, futures, thread.stoptoken, saferecl, depr.atomics.order, topics/undefined-behavior
tags: 内存模型, 并发, 原子操作, 数据竞争, 沿革
updated: 2026-10-19
---

!!! tldr
    - C++98 的抽象机只有一个执行流。多线程程序靠 pthreads 这类库，正确性取决于编译器把加锁函数当作不透明调用这一默契。
    - Boehm 2005 年论证这样不够：编译器的合法单线程变换会改写相邻数据、把共享变量提升到寄存器，所以语言必须自己定义内存位置和数据竞争。
    - C++11 的核心是无数据竞争即顺序一致：没有数据竞争的程序表现得像各线程简单交错执行，有数据竞争就是未定义行为。编译器因此保留了几乎所有单线程优化，`memory_order` 是留给专家的出口。
    - 有两个问题没能解决好：`memory_order_consume` 无法按规定实现，C++26 把它降为 `acquire` 的同义词；凭空值至今只能写成一条建议。
    - `~thread` 调用 `terminate`、`async` 返回的 future 析构时等待、`jthread` 只做协作式取消，各自对应一场关于接口安全的争论。

本页的主要依据是 Boehm 的两篇论文（*Threads Cannot Be Implemented As a Library*，PLDI 2005；与 Adve 合著的 *Foundations of the C++ Concurrency Memory Model*，PLDI 2008）、Stroustrup 的 HOPL IV 论文和 WG21 文档。用到的术语：[[g:data-race|数据竞争]]、[[g:happens-before|happens before]]、[[g:synchronizes-with|synchronizes with]]、[[g:memory-location|内存位置]]。规则本身见 [[intro.multithread]]。

## 一、C++98：标准里没有线程

C++98 用一台抽象机描述程序的语义（今天的 [[intro.abstract]]）：实现只要保持可观察行为不变，就可以任意变换代码。这台抽象机只有一个执行流。Meyers 和 Alexandrescu 在 2004 年说得很直接："As languages, neither C nor C++ have threads."（*C++ and the Perils of Double-Checked Locking*，Dr. Dobb's Journal）

多线程 C++ 程序当时很常见，只是线程来自语言之外：POSIX 系统用 pthreads，Windows 用 Win32 API。pthreads 对内存只有一条规则：一个线程修改某个内存位置时，其他线程不能读写它，这种互斥要通过 `pthread_mutex_lock` 等同步函数实现（Boehm 2005 §3）。

实现靠两件事兑现这条规则：同步函数内部含有硬件内存屏障，阻止处理器把内存操作重排到调用之外；编译器把这些函数当成不透明的外部调用，假设它们可能读写任何全局变量，所以不会把内存访问移过调用。只要所有共享数据都用互斥量保护，这套默契大体能工作。

### 双重检查锁定

麻烦出在想绕开互斥量的代码上。最有名的例子是双重检查锁定（double-checked locking），用来延迟创建单例：

<div class="compare" markdown="1">

```cpp
// 2004 年前后的常见写法（数据竞争）
Widget* p = nullptr;
Widget* get() {
  if (p == nullptr) {     // 不加锁读
    Lock lock;
    if (p == nullptr)
      p = new Widget;     // 加锁写
  }
  return p;
}
```

```cpp
// C++11 起：交给语言
Widget& get() {
  static Widget w;  // 并发首次进入
                    // 时由实现同步
  return w;
}
```

</div>

`p = new Widget` 包括分配、构造、给指针赋值三步。在单线程语义下，把赋值提到构造之前是不可观察的，编译器和硬件都可以这样做。于是另一个线程可能看到非空的 `p`，拿到一个还没构造完的对象。Meyers 和 Alexandrescu 逐一检查了 `volatile`、临时变量等补救手段，结论是在标准 C++ 中无法可移植地修复它。

右边是 C++11 的解法：块作用域静态变量的初始化在并发进入时由实现负责同步（[[N2660]]，今天的 [[stmt.dcl#3]]）。

当时各家编译器各有补救。GCC 提供 `__sync_*` 内建函数；MSVC 给 `volatile` 加了 acquire/release 语义，微软的文档也说明依赖这一点的代码不可移植（Microsoft Learn，*volatile (C++)*）。这种方言状态是 C++11 严格区分 `volatile` 与原子操作的背景之一。

## 二、线程不能只靠库实现

2005 年，HP 实验室的 Hans Boehm 发表 *Threads Cannot Be Implemented As a Library*。论点是：如果编译器按单线程语义设计，线程只是后加的库，生成的代码就无法保证正确。他举出了三类问题（§4）。

### 编译器会改写相邻的数据

```cpp
struct { int a : 17; int b : 15; } x;
// 线程 1：x.a = 42;
// 线程 2：x.b = 7;
```

几乎没有机器能直接写 17 位，所以 `x.a = 42` 会被编译成读出整个字、改掉低 17 位、再整体写回。如果线程 2 恰好在读和写之间修改了 `x.b`，这次修改就丢了，尽管两个线程写的是不同的成员。

pthreads 只禁止并发修改同一个内存位置，而内存位置没有定义。按最宽的读法，编译器把八个相邻 `char` 成员的赋值合并成一次 64 位写回也算合法，甚至两个恰好相邻的全局变量也可能互相覆盖（§4.2）。

### 编译器会把共享变量提升到寄存器

下面左边的循环只在 `mt` 为真时才加锁更新全局变量 `x`。编译器如果判断 `mt` 通常为假，就可能把 `x` 提升到寄存器里，在循环前读、循环后写回（§4.3）：

<div class="compare" markdown="1">

```cpp
// 源码
for (...) {
  if (mt) lock();
  x = f(x);
  if (mt) unlock();
}
```

```cpp
// 编译器变换后（示意）
r = x;
for (...) {
  if (mt) { x = r; lock(); r = x; }
  r = f(r);
  if (mt) { x = r; unlock(); r = x; }
}
x = r;   // 不持锁时写 x
```

</div>

变换后的代码在不持锁时读写 `x`，多线程下完全错误，却没有违反 pthreads 的字面要求。Boehm 说他知道至少四个优化编译器在某个时期做过这种变换。

### 什么算数据竞争，要由语言来定义

第三类问题是定义上的循环：pthreads 说有数据竞争的程序没有保证，但程序有没有竞争又取决于语言给出的语义。两个线程分别执行 `if (x == 1) ++y;` 和 `if (y == 1) ++x;`，初值都是 0，按直觉两个条件都不成立，没有竞争。可如果编译器只需保持单线程正确性，它可以把第一句改成 `++y; if (x != 1) --y;`，竞争就凭空出现了（§4.1）。

此外，pthreads 只认可用互斥量保护一切这一种风格，无锁算法在它的规则下没有定义（§5）。

这篇论文直接决定了 C++11 的几项设计：语言必须自己定义线程的语义；必须精确定义内存位置，禁止编译器写入程序没有写的位置；必须提供原子操作，让无锁算法有合法的写法。

## 三、C++11 的答案：无数据竞争即顺序一致

### 为什么不照搬 Java

2004 年提交给 WG21 的第一份内存模型提案 [[N1680]]，作者中有 Bill Pugh 和 Doug Lea，他们刚参与完 Java 内存模型。C++ 最终没有照搬 Java，原因有两个。

一是代价。据 Stroustrup 回忆，Intel 和 IBM 的代表指出，Java 的模型会显著拖慢 JVM 本身（HOPL IV §4.1.1）。二是目标不同。Java 必须给有数据竞争的程序也规定语义，因为它要限制不可信代码造成的破坏；C++ 没有这个需要，有竞争的程序可以完全没有定义（Boehm 2005 §3）。后一点成了 C++ 模型的基石。

### DRF-SC

2007 年并入 C++0x 草案的 [[N2429]] 采用的思路，Boehm 与 Adve 在 PLDI 2008 的论文中概括为：没有数据竞争的程序获得顺序一致的语义。这常被称为 DRF-SC（data-race-free implies sequential consistency）。它把责任分成两半：

- 程序员负责不写数据竞争。只要所有共享数据都由互斥量或 `seq_cst` 原子操作保护，程序的行为就像所有线程的操作简单交错执行。
- 编译器和硬件可以继续做几乎所有单线程优化。一个程序如果能观察到这些优化，它一定有数据竞争，而有数据竞争的程序行为未定义。

这正是今天 [[intro.races#17]] 注 18 的内容。同一段把数据竞争定义为：两个可能并发的冲突操作，至少一个不是原子操作，并且谁也不 happens before 谁。

### 内存位置：给编译器划的线

Boehm 的相邻数据问题由 [[intro.memory#3]] 回答。**内存位置**是一个非位域的标量对象，或者一串相邻的非零宽位域。不同的内存位置可以被不同线程同时访问，编译器不能再把对 `a` 的写实现成对 `a`、`b` 的整体写回：

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

两个线程分别写 `s.x` 和 `s.y` 仍然是数据竞争（[[intro.memory#4]] 的注）。这是一个取舍：硬件不能单独写几个比特，标准就把相邻位域算作一个位置，由程序员负责同步；其余情况由编译器负责不越界写入。

### volatile 不是同步

有了数据竞争的定义，用普通变量或 `volatile` 变量做标志的老写法就有了明确的结论：

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

用 Clang 的 ThreadSanitizer（`-fsanitize=thread`）运行，会报告数据竞争。正确的写法见下一节。

N2429 之后，剑桥大学的 Batty、Owens、Sarkar、Sewell、Weber 等人把模型数学化，发现并修正了草案中的若干问题（[[N3132]]、[[N3196]]；*Mathematizing C++ Concurrency*，POPL 2011）。C11 也采用了同一个模型（HOPL IV §4.1.1）。

## 四、为什么有这么多 memory_order

如果只要 DRF-SC，标准只需提供顺序一致的原子操作。但在 Power、ARM 这类弱序架构上，顺序一致需要额外的屏障指令，而无锁算法的意义正在于省掉不必要的同步。

委员会里还有一场关于最底层原语的争论：Intel 一方的模型是 TSO 加少量原子操作，IBM 一方是弱一致性加栅栏（fence）。据 Stroustrup 回忆，IBM 有大量基于栅栏的代码深埋在复杂算法里，无法转向 Intel 式的模型，最终 C++11 两者都支持（HOPL IV §4.1.1）。今天标准里同时有带内存序的原子操作和独立的栅栏（[[atomics.fences]]），来由就在这里。

于是 C++11 允许逐个操作指定内存序（[[atomics.order]]）：

| 内存序 | 保证 | 典型用途 |
|---|---|---|
| `seq_cst`（默认） | 参与一个全局全序，保持 DRF-SC | 不想推理内存序时 |
| `acquire` / `release` / `acq_rel` | 读到 release 写的 acquire 读与之同步 | 消息传递、锁 |
| `relaxed` | 只保证单个对象上的原子性和一致性 | 计数器 |
| `consume` | 原意是只对依赖于读取结果的操作排序；C++26 起等同 `acquire` | 见下一节 |

代价是一旦使用非 `seq_cst` 的内存序，就离开了 DRF-SC 的保护，必须按 happens before 推理。最常见的 release/acquire 消息传递如下：

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

[[intro.races#1]] 的注 1 说，这一节大部分内容是为带显式可见性约束的原子操作写的，但它也隐含地支持一种更简单的视角。这就是 Boehm 与 Adve 的两层设计：只用互斥量和 `seq_cst` 的程序员停留在顺序一致的世界里，使用较弱内存序的人才需要处理 happens before 的全部细节。

## 五、两个没解决好的问题

### memory_order_consume

`consume` 的动机是 Linux 内核大量使用的 RCU：读者通过一个指针读取数据结构，在 Power、ARM 上，只要后续访问在数据上依赖于这个指针，硬件就保证顺序，不需要屏障指令。Paul McKenney 等人的提案（[[N2664]] 等）想把这种廉价的顺序带进 C++。

为此，C++11 的 [intro.races] 引入了 carries a dependency、dependency-ordered before、inter-thread happens before 等关系，happens before 的定义随之变得复杂，还失去了传递性。语言层面加了 `[[carries_dependency]]` 属性和 `std::kill_dependency`，用来在函数边界上传递或截断依赖链。

问题在于标准按源代码定义依赖：一个值作为另一个求值的操作数就算依赖。编译器优化却会消除依赖，例如把 `p->a[x - x]` 的下标折叠成常数。要按标准实现 `consume`，编译器必须在整条依赖链上抑制这类优化。结果所有编译器都把 `consume` 当作 `acquire` 处理（[[P3475R2]]）。

C++17 通过 [[P0371R1]] 在 [[atomics.order]] 加了一条注，暂时不鼓励使用 `consume`。之后十年里有多份替代方案，没有一份达成共识。C++26 的 [[P3475R2]] 最终承认了现实：

<div class="compare" markdown="1">

```text
C++11–C++23 的 happens before：
  A sequenced before B，或
  A inter-thread happens before B
inter-thread happens before 又由
  synchronizes with、
  dependency-ordered before 等
  递归定义；没有传递性，
  C++20 起另需 simply happens
  before 等辅助关系
```

```text
C++26 的 happens before：
  A sequenced before B，或
  A synchronizes with B，或
  A happens before X 且
  X happens before B
（就是一个传递闭包）
```

</div>

P3475R2 删除了依赖相关的关系和 `[[carries_dependency]]` 属性，把 `consume` 从 `memory_order` 的正文中移到附录 D 的 [[depr.atomics.order]]：它仍然存在，值仍是 1，含义与 `acquire` 相同；`kill_dependency(y)` 直接返回 `y`。

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

截至写作时，本机 Clang 23（libc++）编译这段代码不给弃用警告。P3475R2 给出的理由也说明了硬件的变化：x86 上 `consume` 本来就没有收益，ARM 的 acquire 读在常见场景下已接近 relaxed 读，仍能受益的主要是 Power 和 GPU。

[[intro.races#3]] 的注 3 至今还写着 release 操作使之前的副作用对执行 consume 或 acquire 操作的线程可见。consume 已与 acquire 同义，这句话的意思没变，只是保留了旧写法。

### 凭空出现的值

relaxed 原子操作还有一个至今没有完全解决的问题：凭空出现的值（out-of-thin-air，OOTA）。下面的例子改写自 [[atomics.order#8]] 的注：

```cpp title="oota.cpp"
// x、y 是 std::atomic<int>，初值都是 0
// 线程 1：
r1 = y.load(std::memory_order::relaxed);
x.store(r1, std::memory_order::relaxed);
// 线程 2：
r2 = x.load(std::memory_order::relaxed);
y.store(r2, std::memory_order::relaxed);
```

直觉上 `r1 == r2 == 42` 不可能出现，因为 42 无从产生。但仅凭 happens before 和一致性规则，形式模型排除不了它：两次读取可以循环地为对方的写入提供理由。

C++11 曾用一条规范性要求禁止这种结果。Boehm 等人在 [[N3786]] 中指出这条要求表述不当，按字面理解会禁止 ARM 和 Power 上 `relaxed` 的所有合理实现，而经过约十年的尝试，仍没有人知道怎样精确表述它而不损害性能。C++14 于是把它改成了建议，也就是今天 [[atomics.order#8]] 的 should：实现应当保证不计算出循环依赖于自身的凭空值。此后 WG21 中仍有讨论（如 [[P1217R2]]），没有结论。

## 六、线程库：接口里的几场争论

C++11 的线程库源自 Boost.Thread，第一份提案是 2004 年的 [[N1682]]，最终版本是 [[N2497]]。Stroustrup 指出，`std::thread` 的构造函数是一个变参模板，它的类型安全接口在很大程度上依赖同期加入的变参模板和 lambda（HOPL IV §4.1.2）。

### 没有取消

据 Stroustrup 记述，线程库最大的争议是取消（cancellation）。委员会中的 C++ 程序员几乎都想要某种形式的取消，但 C 委员会（WG14）和 POSIX 的代表认为取消既不必要，也无法安全地实现（HOPL IV §4.1.2）。C++11 最终没有提供取消。这个空缺到 C++20 才以协作式取消的形式补上，见本节最后。

### ~thread 为什么调用 terminate

2008 年的草案规定，`std::thread` 析构时如果线程还没被 join，就自动 `detach()`。Boehm 在 [[N2802]] 中指出了问题：

```cpp title="detach-hazard.cpp"
void f() {
    int local = 0;
    std::thread t([&] { local = 1; });
    may_throw();   // 抛异常时 t 还没被 join
    t.join();
}
```

`may_throw()` 抛出异常时，`t` 在栈展开中被析构。如果析构时 detach，线程会继续写已经销毁的 `local`，造成难以调试的内存破坏。N2802 给出两个替代方案：析构时 `join()`，或析构时 `terminate()`。C++11 选了后者。[[thread.thread.destr]] 的注至今解释着这个选择：隐式 detach 会导致难以调试的正确性问题，隐式 join 会导致只在抛异常时出现的性能问题，两者都只在异常路径上暴露。

### async 的 future 为什么析构时等待

据 Stroustrup 回忆，委员会当时分成两派：一派基本上只想要类型更安全的 POSIX，另一派想要消息队列、线程池这类更高层的设施。2007 年达成的折中是：C++0x 提供 promise、future，以及一个允许但不要求使用线程池的 `async()`。他说这个折中谁都不满意（HOPL IV §4.1.3）。

`async` 的规则（[[N2996]]）规定，如果 future 是最后一个引用 `async` 所建共享状态的对象，它的析构函数要等待任务结束。于是 `async` 返回的 future 和其他 future 行为不同：

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

2012 年 Sutter 在 [[N3451]] 中提出，这种差异让 future 无法组合：拿到一个 future 的函数不知道它是否来自 `async`，也就不知道析构时会不会等待。Boehm 在 [[N3679]] 中给出反方理由：如果不等待，任务可能在它引用的数据被销毁之后继续运行，这和上面 detach 的问题一样，一个意外的异常就能触发，测试中很难发现。改变 `~future` 和弃用 `async` 的提案（[[N3776]]、[[N3777]]）都没有通过。

规则因此保留至今：[[futures.state#5]] 规定释放共享状态不会为等待就绪而阻塞，唯一的例外就是 `async` 创建的、尚未就绪的、最后一个引用。

### jthread：协作式取消

2017 年 Nicolai Josuttis 提出的 [[P0660R10]] 把两件拖了很久的事放在一起：析构时自动 join 的线程，和协作式取消。`std::jthread`（[[thread.jthread.class]]）析构时先请求停止，再 join。停止请求通过 [[thread.stoptoken]] 中的 `stop_token` 传递，线程函数要自己定期检查，没有任何线程会被从外部强行终止，这就绕开了 C++11 时期的取消之争。

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

## 七、之后的补充

C++11 之后的并发特性大多是在既定模型上补设施。其中几项的形态能用历史解释：

- **读写锁的名字。** 2013 年通过的读写锁原名 `shared_mutex`，因为它支持带超时的加锁，[[N3891]] 提议改名为 `shared_timed_mutex`，把短名字留给将来不带超时、可能更高效的版本。所以 C++14 只有 `shared_timed_mutex`，`shared_mutex` 到 C++17 才出现（[[thread.sharedmutex.class]]）。
- **scoped_lock 是新名字。** [[P0156R2]] 最初想把 `lock_guard` 改成变参模板，因为担心破坏 ABI，改为引入新名字 `std::scoped_lock`（[[thread.lock.scoped]]）。
- **前进保证。** C++17 的并行算法需要说明元素访问函数能指望什么样的调度，[[P0296R2]] 为此给出了 [[intro.progress]] 中前进保证的基础定义。
- **C++20 的同步库。** [[P1135R6]] 加入了原子等待（[[atomics.wait]]）、信号量、`latch` 和 `barrier`；`std::atomic_ref`（[[atomics.ref.generic]]）让普通对象可以临时按原子方式访问；`atomic<shared_ptr<T>>` 取代了 C++11 的 `atomic_load(const shared_ptr<T>*)` 等自由函数，后者已从当前草案中删除。
- **C++20 的模型修补。** [[P0668R5]] 发现 Power 和 ARM 上的常用实现方案并不满足当时对 `seq_cst` 的定义，于是重新定义了 strongly happens before（[[intro.races#8]]），其中 synchronizes with 只有在两端都是 `seq_cst` 操作时才计入。[[P0982R1]] 把 release sequence 缩小到只含原子读-改-写操作（[[intro.races#5]]）。
- **C++26 的安全回收。** 无锁数据结构把节点摘下后，什么时候能 `delete` 它？hazard pointer 和 RCU 是两种经典答案，C++26 通过 [[P2530R3]] 和 [[P2545R4]] 加入了二者（[[saferecl]]）。hazard pointer 的接口是 Concurrency TS 2 版本的子集，P2530R3 说明 Folly 库的生产经验表明常见用法不需要被省略的部分。
- **平凡无限循环。** [[intro.progress#1]] 允许实现假设每个线程最终会终止、做 I/O、访问 volatile 或做原子操作等。C++26 的 [[P2809R3]] 在这份清单里加上了继续执行平凡无限循环（[[stmt.iter.general]]），`while (true) {}` 不再因前进假设而成为未定义行为。

C++26 还加入了 `fetch_max`、`fetch_min` 等原子操作（[[P0493R5]]）。截至写作时，本机 Clang 23 + libc++ 还没有提供它们，也没有 `<hazard_pointer>` 和 `<rcu>` 头文件。

## 今天 [intro.races] 里的历史

| 当前草案 | 内容 | 来源 |
|---|---|---|
| [[intro.memory#3]]、[[intro.memory#4]] | 内存位置；不同位置可以并发访问 | Boehm 2005 的相邻数据问题 |
| [[intro.races#2]] | 冲突：一个修改，另一个读写同一内存位置 | pthreads 规则的形式化 |
| [[intro.races#3]] | 同步操作：acquire、release、栅栏；relaxed 不是同步操作 | 原子库 [[N2427]]；TSO 与栅栏之争 |
| [[intro.races#5]] | release sequence 只由读-改-写构成 | C++20 的 [[P0982R1]] |
| [[intro.races#7]] | happens before 是传递闭包 | C++26 删除 consume 后的简化 |
| [[intro.races#8]] | strongly happens before | C++20 的 [[P0668R5]] |
| [[intro.races#17]] | 数据竞争导致 UB；注 18 说明 DRF-SC | Boehm 与 Adve 的设计 |
| [[intro.races#18]] | 同一线程内对 `volatile std::sig_atomic_t` 的访问不构成数据竞争 | 与信号处理函数兼容 |
| [[atomics.order#8]] | 不产生凭空值的建议 | C++14 的 [[N3786]] |
| [[depr.atomics.order]] | `consume` 与 `acquire` 同义 | [[P3475R2]] |

## 仍在进行的工作

- 指针所指对象的生命周期结束后，指针值变为无效。许多无锁算法会比较一个可能已失效的指针，这与标准冲突，[[P2414R12]] 讨论了解决方案。
- seqlock 一类算法需要字节粒度的原子拷贝，[[P1478R8]] 提出了按字节原子拷贝的函数，目前不在 IS 草案中。
- hazard pointer 当初省略的同步回收由 [[P3427R9]] 补充。
- 凭空值仍然只是建议；`consume` 留在附录 D 中，目前没有已提交的替代设计。

## 参考资料

- Hans-J. Boehm，*Threads Cannot Be Implemented As a Library*，PLDI 2005。
- Hans-J. Boehm、Sarita V. Adve，*Foundations of the C++ Concurrency Memory Model*，PLDI 2008。
- Mark Batty 等，*Mathematizing C++ Concurrency*，POPL 2011。
- Scott Meyers、Andrei Alexandrescu，*C++ and the Perils of Double-Checked Locking*，Dr. Dobb's Journal，2004。
- Bjarne Stroustrup，*Thriving in a Crowded and Changing World: C++ 2006–2020*，HOPL IV，2020（§4.1 C++11 的并发支持，§9.4 C++20 的并发）。
- Microsoft Learn，*volatile (C++)*。
