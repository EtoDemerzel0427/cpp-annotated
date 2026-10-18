---
title: 执行器的十年：从 executors 到 std::execution
summary: 从 2012 年 Google 的执行器草案、Kohlhoff 基于 Asio 的模型、并行算法的执行策略，到 P0443 统一执行器的六年拉锯、发送器/接收器的批评，再到 P2300 std::execution 进入 C++26；以及网络库因此一再搁浅的经过
status: draft
order: 30
papers: N3562, N4046, N4406, P0443R14, P1393R0, P1525R1, P2006R1, P2300R10, P2464R0, P2469R0, P3149R11, P3552R3, P2079R10
related: exec, exec.async.ops, exec.snd, exec.recv, exec.sched, exec.cmplsig, exec.snd.transform, exec.scope, exec.task, exec.par.scheduler, execpol, algorithms.parallel, topics/coroutines
tags: 沿革, 并发, 并行, std::execution, 网络, 委员会
updated: 2026-10-18
---

C++26 的第 33 章 [[exec]] 读起来和标准库的其他部分很不一样：没有一个叫 `executor` 的概念，却有发送器、接收器、操作状态、调度器四个角色；每个接收器恰好有三个完成函数；发送器要在编译期声明自己的[[g:completion-signature|完成签名]]；算法的定制要经过一层叫 domain 的间接；启动工作后无人等待其结束的算法被删掉了，换成了必须挂在某个 scope 上的 `spawn`。这些设计都不是一开始就有的，几乎每一条都对应着委员会在 2012–2025 年间的一次争论。

这一页按时间顺序讲这段历史：执行器（executor）这个词怎样从三家各自的设计出发，被要求统一成 [[P0443R14]]；统一后的设计怎样因为错误处理和取消问题受到批评；发送器/接收器模型怎样从 P0443 的附属部分变成 [[P2300R10]] 的全部；以及依赖执行器的 Networking TS 为什么至今没有进入标准。读完之后再回到 [[exec]]，很多看似繁琐的规则就有了来由。

!!! note "关于出处与例子"
    本页的每个历史论断都给出 WG21 文档或会议报告作为出处。会议上的投票结果以委员会公开的投票汇总文档为准；会议之外流传的说法会标明来源。本页中 P2300 之前的代码都是历史上提案里的写法，从未进入标准，不标判定；`std::execution` 的代码依据当前草案写成，由于本机 libc++ 尚未提供发送器部分，同样不标判定。

## 一、三条起点（2012–2015）

### Google：作为线程池接口的执行器

最早进入 WG21 文档的执行器提案来自 Google：2012 年的 [[N3378]]（*A preliminary proposal for work executors*），以及 2013 年 3 月的修订版 [[N3562]]（*Executors and schedulers, revision 1*，Austern、Crowl、Carruth、Gustafsson 等）。它的模型很直接：执行器是一个抽象基类，提交工作的接口是虚函数，工作本身用 `std::function<void()>` 做类型擦除。

```cpp title="N3562 / N3785 风格（历史提案，从未标准化；简化）"
// 执行器是抽象基类，工作用 std::function 做类型擦除
class executor {
public:
  virtual ~executor();
  virtual void add(std::function<void()> closure) = 0;
};

class scheduled_executor : public executor {
public:
  virtual void add_at(const std::chrono::system_clock::time_point& abs_time,
                      std::function<void()> closure) = 0;
  virtual void add_after(const std::chrono::system_clock::duration& rel_time,
                         std::function<void()> closure) = 0;
};

class thread_pool : public scheduled_executor { /* ... */ };
```

这条路线后来又出了几个修订：[[N3731]]、[[N3785]]（revision 3）、[[N4143]]（revision 4）和 2015 年 4 月的 [[N4414]]（revision 5）。它关心的是粗粒度任务：把一个闭包交给线程池，开销主要在线程间传递上，一次虚函数调用和一次类型擦除可以忽略。

### Kohlhoff：执行器之于函数执行，如同分配器之于分配

Christopher Kohlhoff 从 2003 年开始开发 Asio，2005 年进入 Boost，2006 年起以 [[N2054]] 等文档向 TR2 提出网络库（Stroustrup，HOPL IV，§8.8.1）。网络库里到处是异步操作的完成回调，执行器问题对它来说不是可选的。

2014 年 5 月的 [[N4046]]（*Executors and Asynchronous Operations*）直接回应了 N3785。Kohlhoff 认为 N3785 的抽象基类和类型擦除让它不适合执行细粒度任务，尤其是异步操作的完成回调：在多层抽象叠加的异步组合里，编译器看不穿虚接口，无法内联；强制使用 `std::function` 还排除了只能移动的函数对象。他用一句话概括自己的替代方案：

!!! history "N4046，§1"
    "An executor is to function execution as an allocator is to allocation."
    即执行器是一个轻量的、基于模板的策略对象，就像分配器之于内存分配。

N4046 的执行器有三种提交方式，区别在于是否允许阻塞调用者：`dispatch`（允许在当前线程立即执行）、`post`（不得立即执行）、`defer`（不得立即执行，且提示这是当前工作的延续）。执行器和**执行上下文**（execution context）被区分开：线程池、事件循环是上下文，执行器只是指向上下文的轻量句柄，定时器之类的复杂设施属于上下文而不是执行器。异步操作的完成方式则由更早的 [[N3747]]（*A Universal Model for Asynchronous Operations*，2013）和 [[N4045]] 描述的完成令牌（completion token）机制决定：同一个 `async_read` 可以按调用者的选择返回 future、调用回调或者挂起协程。

```cpp title="Asio / N4046 风格（历史提案，从未标准化）"
// 执行器只是上下文的句柄；post 保证不在调用者的栈上执行 f
asio::io_context ctx;
auto ex = ctx.get_executor();
asio::post(ex, [] { /* ... */ });

// 异步操作的完成处理器带着一个关联执行器（associated executor）
socket.async_read_some(buffer, asio::bind_executor(strand, handler));
```

N4046 之后又有 [[N4242]]（2014 年 10 月）和 [[P0113R0]]（2015 年 9 月）两个修订。这个模型连同网络库一起演化成了后来的 Networking TS。

### NVIDIA：为并行算法服务的执行器

第三条线来自并行算法。2013 年 3 月，NVIDIA、Microsoft、Intel 的作者们提交了 [[N3554]]（*A Parallel Algorithms Library*），提议给标准算法加一个执行策略参数。这项工作成为 Parallelism TS，2015 年以 ISO/IEC TS 19570:2015 发布（工作草案见 [[N4507]]）。

执行策略只回答一个问题：这次调用允许以什么方式并行。它不回答工作在哪里运行。2015 年 4 月，Hoberock、Garland、Giroux 在 [[N4406]] 中写道，执行策略规定了可以创建什么并行工作，却没有回答这些工作应该在哪里执行，后者应该由执行器来控制。他们提议把执行器和策略组合起来：

```cpp title="N4406 风格（历史提案，从未标准化）"
my_executor my_exec = ...;
std::sort(par.on(my_exec), data.begin(), data.end());   // 在用户指定的执行器上并行
```

NVIDIA 的执行器模型（[[P0058R1]]，*An Interface for Abstracting Execution*）以 `executor_traits` 为中心，重点是**批量执行**（bulk execution）：一次调用创建大量执行代理，这对 GPU 不可缺少；它还区分了返回 future 的异步执行和阻塞执行。

于是到 2015 年，WG21 手里有三套各有侧重的执行器：Google 的面向线程池和类型擦除，Kohlhoff 的面向细粒度异步操作，NVIDIA 的面向批量并行。据 Hoberock 在 [[P2033R0]]（*History of Executor Properties*）中的回顾，SG1 在 2015 年 10 月的 Kona 会议上给出的意见是 "Unify, please."

## 二、执行策略先行：C++17 并行算法（2016–2019）

执行器还在争论时，执行策略先进入了标准。2016 年 3 月的 Jacksonville 会议通过 [[P0024R2]]（*The Parallelism TS Should be Standardized*），把 Parallelism TS 并入 C++17。Herb Sutter 在会后的报告中把它列为这次会议并入 C++17 的几个分支之一，称其包含大多数 STL 算法的并行版本（Sutter，*Trip report: Winter ISO C++ standards meeting*，2016 年 3 月）。同一份报告也说，执行器如果能达成设计共识，自然会进入第二个 Concurrency TS。

C++17 的执行策略是 `seq`、`par`、`par_unseq` 三个对象，C++20 又通过 [[P1001R2]] 加入了 `unseq`。它们的规范语义在 [[execpol]] 和 [[algorithms.parallel]]：策略只是一张许可证，告诉实现可以怎样调度[[g:element-access-function|元素访问函数]]，以及因此对用户代码提出的要求（例如 `par_unseq` 下不得加锁）。

```cpp ok
#include <algorithm>
#include <execution>
#include <vector>

int main() {
  std::vector<int> v{3, 1, 2};
  std::sort(std::execution::par, v.begin(), v.end());       // 允许并行
  std::sort(std::execution::par_unseq, v.begin(), v.end()); // 允许并行 + 向量化
  return v.front() == 1 ? 0 : 1;
}
```

本机的 Clang 23 + libc++ 需要加 `-fexperimental-library` 才提供这几个策略对象；加上之后，上面的程序可以编译运行。

### 为什么执行策略不是执行器

执行策略和执行器常被混为一谈，两者的分工其实在 N4406 里就讲清楚了：策略描述允许以什么方式执行，属于算法的语义约束；执行器描述工作在哪里执行，属于资源的选择。C++17 只标准化了前者。`par.on(exec)` 这样的组合方式一直依赖执行器的设计，后来 Hoberock 的 [[P1019R2]]（*Integrating Executors with Parallel Algorithms*，2019）也没有被采纳。

所以 [[algorithms.parallel]] 里的并行算法至今没有办法指定线程池：`std::sort(std::execution::par, ...)` 在哪些线程上运行，完全由实现决定。执行器的设计换成发送器之后，这个问题换了一种问法，即怎样把执行策略和调度器结合起来，例如 [[P2500R2]]（*C++ parallel algorithms and P2300*）和 [[P3300R0]]（*C++ Asynchronous Parallel Algorithms*）。截至写作时，这两份提案都没有进入工作草案。当前草案中的 range 算法也有接受执行策略的重载（由 [[P3179R9]] 提出），但仍然没有调度器参数。

## 三、P0443：统一执行器（2016–2020）

### 从十五个执行函数到属性

按 SG1 的要求，三方的作者开始定期电话会议，一年后在 2016 年 11 月的 Issaquah 会议上提交了 [[P0443R0]]（*A Unified Executors Proposal for C++*，Hoberock、Garland、Kohlhoff、Mysen、Edwards）。P0443R0 自述要统一三种模型：Google 面向线程池的模型（N4414）、Kohlhoff 为 Networking TS 设计的模型（[[N4370]]）、NVIDIA 为 Parallelism TS 设计的模型（P0058）。

统一的办法是把三方的需求都放进来。据 P2033R0 的统计，R0 定义了七种执行器类别（`OneWayExecutor`、`NonBlockingOneWayExecutor`、`BulkTwoWayExecutor` 等），通过十五个定制点暴露执行函数，函数名本身编码了三个维度：是否阻塞、单向还是双向（是否返回 future）、单个还是批量。`execute`、`post`、`defer`、`async_execute`、`then_execute`、`bulk_then_execute`……再乘上可选的分配器参数，组合迅速膨胀。P2033R0 记录了 SG1 在 2017 年 2 月 Kona 会议上看到这张适配关系图时的反应："This picture looks terrifying."

2017 年 6 月，Kohlhoff、Hoberock、Mysen、Brown 在 [[P0688R0]]（*A Proposal to Simplify the Unified Executors Design*）中提出用**属性**（property）把这些维度从函数名里拿出来：执行函数只保留少数几个，阻塞性、方向、是否是延续等都变成可以向执行器要求的属性。P0443R2（2017 年 7 月）采纳了这一简化，同时把设计说明拆到 [[P0761R0]]（*Executors Design Document*）。

```cpp title="P0443R2 之后的属性写法（历史提案，从未标准化）"
// require：必须满足，否则编译失败；prefer：尽量满足
auto ex2 = execution::require(ex, execution::single, execution::oneway,
                              execution::never_blocking);
ex2.execute(f);

auto ex3 = execution::prefer(ex2, execution::continuation);
```

R3 又加入了 `query`，用来询问执行器当前的属性。据 P2033R0，SG1 在 2017 年 11 月的 Albuquerque 会议上表示 "P0443 is our preferred direction for executors."

属性机制后来被认为可以服务于执行器以外的对象（执行上下文、执行策略、分配器位置等），于是 P0443R10 按 LEWG 在 2018 年 11 月 San Diego 会议上的指示，把属性的定制机制移到命名空间 `std`，细节拆成单独的 [[P1393R0]]（*A General Property Customization Mechanism*，2019 年 1 月）。P1393 最终没有进入标准；P2300 明确不包含属性（见下文第五节）。今天 [[exec]] 里的查询对象和环境（[[exec.queryable]]、[[exec.env]]）可以看作这条线留下的痕迹：询问（query）保留了，要求（require/prefer）没有保留。

### C++20 的目标落空

P0443 在 2017–2018 年间几乎每次会议都有新修订（R2 到 R9）。2018 年 9 月，委员会在 Bellevue 专门开了两天执行器会议，据 Stroustrup 回忆，约 25 人参加，包括 NVIDIA、Facebook 和美国国家实验室的代表（HOPL IV，§9.4）。按那次会议上 SG1/LEWG 的意向投票，P0443R9 把依赖执行（future 和 `then_execute` 一类）拆到 [[P1244R0]]，P0443 本身只保留单向执行（P0443R9 修订记录）。

2018 年 11 月的 San Diego 会议后，Sutter 的报告还说执行器的初始设计有希望进入 C++20：设计已获批准，下次会议考虑把措辞并入（Sutter，*Trip report: Fall ISO C++ standards meeting (San Diego)*，2018 年 11 月）。但按 [[P1000R0]] 的日程，三个月后的 Kona 会议是 C++20 设计冻结、把提案送去措辞审查的最后一次会议，Sutter 在会后写道，曾希望执行器的一部分能赶上 C++20，但它们没有赶上，执行器和依赖它的网络库都改为 C++23 早期的目标（Sutter，Kona 会议报告，2019 年 2 月）。Stroustrup 在 HOPL IV（§8.8.1）里把执行器和网络库缺席 C++20 称为 "the best is the enemy of the good" 的例子。

Voutilainen 的 [[P0592R4]]（*To boldly suggest an overall plan for C++23*，2019 年 11 月）把执行器和网络库都列为 C++23 最优先的工作，其中写道 "We have been working on executors for quite a while, and in C++23, we should deliver."

## 四、发送器与接收器的批评（2018–2020）

### 另一种异步模型

与 P0443 并行，Facebook 的一组作者（Kirk Shoop、Eric Niebler、Lee Howes、Lewis Baker 等）在实践中形成了另一种模型。2018 年 4 月的 [[P1055R0]]（*A Modest Executor Proposal*，Shoop、Niebler、Howes）认为当时的执行器设计过于复杂，并且不是真正的统一：Networking TS 仍有自己的 `io_context`，并为异步机制设计了另一套逐调用参数化的方式。它提出一组以"延迟的"（deferred）计算为核心的概念层次，其中错误（error）、完成（done）、值（value）是可以组合的特性。[[P1053R1]]（*Future-proofing continuations for executors*，Howes、Niebler）则论证延续应该有独立的值通道和错误通道。

2018 年 10 月的 [[P1194R0]]（*The Compromise Executors Proposal: A lazy simplification of P0443*，Howes、Niebler、Shoop、Lelbach、Hollman）把这些想法压缩成对 P0443 的修改建议：把 P0443 中占位的 `Future` 概念换成**发送器**（sender），代表一段可能尚未提交的异步工作；把延续换成**接收器**（receiver），有值、错误、完成（done）三个通道；用一个返回 `void` 的 `submit(receiver)` 作为提交工作的唯一终点。11 月，Lewis Baker 的 [[P1341R0]]（*Unifying Asynchronous APIs in the Standard Library*）从协程的角度讨论了同一套抽象。

### Cologne 妥协：执行器之上加一层发送器

2019 年 6 月的 Cologne 会议之前，两方都发了论文。NVIDIA 方面的 [[P1658R0]]（*Suggestions for Consensus on Executors*，Hoberock、Lelbach）建议取消改变接口的属性、只保留一个执行器概念；Niebler 的 [[P1738R0]]（*The Executor Concept Hierarchy Needs a Single Root*）论证概念层次需要唯一的根；Niebler、Shoop、Baker、Howes 的 [[P1525R0]]（*One-Way execute is a Poor Basis Operation*）系统地批评了单向 `execute`。双方作者合写的 [[P1660R0]]（*A Compromise Executor Design Sketch*）开头就说，它要回应 NVIDIA 和 Facebook 对 P0443R10 的关切，为 SG1 和 LEWG 找一个各方都能接受的方向。

P1660 的方案是：去掉 `oneway`、`bulk_oneway` 这类改变接口的属性；执行器概念只要求一个急切提交工作的 `execute` 成员；另外引入**调度器**（scheduler）概念，它的 `schedule` 惰性地产生一个发送器；发送器、接收器及相关操作一并加入。P0443R11 的修订记录写明，这些改动是按 SG1 在 Cologne 会议上的指示，依照 P1658 和 P1660 做的，新增了 `sender`、`sender_to`、`typed_sender`、`scheduler` 几个概念。

从此 P0443 里有两套东西并存：执行器的 `execute(ex, f)`，以及调度器、发送器、接收器。两者之间靠定制点做适配，例如把执行器当作调度器使用。

### 零分配：connect 与 start

最初的发送器只有一个基本操作 `submit(sndr, rcvr)`。2020 年 1 月的 [[P2006R0]]（*Eliminating heap-allocations in sender/receiver with connect()/start() as basis operations*，Baker、Niebler、Shoop、Howes）指出，`submit` 在一般情况下需要把异步操作的状态分配在堆上，因为调用者无从得知需要多大的存储。改法是把它拆成两步：`connect(sndr, rcvr)` 返回一个不可移动的**操作状态**对象，由调用者决定放在哪里（通常在栈上或外层操作状态里）；`start(op)` 才真正启动工作。P0443R13（2020 年 3 月）采纳了这一改动。

这就是今天 [[exec.connect]] 和 [[exec.opstate]] 的来源。[[exec.async.ops]] 里关于操作状态生存期的那些规则（操作状态在异步操作完成前必须存活、完成后才能销毁），都是为这种零分配的嵌套布局服务的。

### P1525：单向 execute 不适合作为基本操作

2020 年 10 月，P1525 出了 R1，作者名单扩展到包括 Gašper Ažman、Corentin Jabot、Tomasz Kamiński、Zach Laine、Ville Voutilainen。它的摘要把论点归结为一句话：

!!! history "P1525R1，§1"
    "The scheduler concept is a more foundational abstraction than the executor concept."
    即调度器（产生发送器）比执行器（单向 `execute`）更基础。

P1525R1 给出的技术理由有三条：

1. **错误无法以可移植的方式传播**。`execute(ex, f)` 返回 `void`。提交时的错误也许能用异常报告，但提交之后、执行之前发生的错误（例如执行器延迟创建执行代理时失败，或者带截止时间的执行器撤销了超时未开始的工作）没有任何带内通道可以送达。各执行器的处理方式由实现定义，因此泛型代码无法对异步错误作出反应。论文还指出，用调度器可以实现 `execute`，反过来却不能保真地实现。
2. **取消信号无法传播**。如果执行器决定不执行已提交的工作，除了销毁函数对象之外，它没有办法通知这段工作。论文论证了为什么销毁不是表达取消的合适方式，并把接收器的 done 通道解释为既没有值、也没有异常的返回，与 `optional` 的空状态类比。
3. **一般情况下需要动态分配**。急切的单向 `execute` 要求每个异步任务的状态都分配在堆上，而发送器/接收器可以做到零分配调度。

论文还讨论了一个实际问题：P0443R14 允许把执行器透明地当作调度器使用，但这个适配在 `execute` 抛异常时会让接收器既收到 `set_error` 又收到 `set_done`，违反了每个操作恰好完成一次的约定。另外，值通道和错误通道分开，还允许两者在不同的地方编译和执行，例如值处理在 GPU 上、错误处理在主机上。

同月，Voutilainen 发表了 [[P2235R0]]（*Disentangling schedulers and executors*），从标题即可看出，它主张把调度器与执行器分开处理。2020 年下半年，LEWG 还分组审查了 P0443R13，留下了一系列审查报告，例如 [[P2183R0]]（属性）、[[P2202R0]]（发送器/接收器）、[[P2219R0]]（待解决问题清单）。

## 五、P2300：std::execution（2021–2024）

### 去掉执行器

2021 年 6 月，[[P2300R0]]（*std::execution*，Dominiak、Baker、Howes、Garland、Niebler、Lelbach）发表。它自述基于 P0443R14 的思想，但做了根本性的改动。P2300R10 §1.8 列出了与 P0443 的十一处差异，最重要的几条是：

- 执行器概念被删除，所有功能都建立在调度器和发送器之上（论文注明这是 SG1 的方向）；
- 不包含属性，属性留作委员会更熟悉之后的可能扩展；
- 发送器要声明自己会在哪个调度器上完成；
- 精确规定了用户代码在哪里执行，而 P0443 没有；
- 提供了一整套发送器算法（`then`、`let_value`、`when_all` 等），而 P0443 没有；
- 放弃无类型的发送器：原来的 `typed_sender` 改名为 `sender`，`sender_traits` 换成完成签名；
- 按 LEWG 的方向，不包含类型擦除设施，也不包含具体的线程池实现。

所以今天的 [[exec.sched]] 里只有 `scheduler`，没有 `executor`；[[exec.recv]] 里的接收器有三个完成函数，`set_done` 后来改名为 `set_stopped`（[[exec.set.stopped]]）；而完成签名（[[exec.cmplsig]]）是每个发送器的必备部分。

P2300 同时说明了它为什么不选用其他已有的异步抽象（§1.9）：future 需要共享状态、同步和类型擦除；协程的帧通常需要动态分配和间接调用，因此不适合作为所有标准异步设施的基础；回调本身足够高效，但缺少标准的回调形状，无法写泛型代码。

### 惰性与完成签名

P2300 选择了纯惰性的模型。论文 §4.10 说，纯惰性的模型足以支撑大多数算法，并解释了为什么移除急切的算法：急切执行带来一系列语义和性能问题，其中之一是析构函数的语义难以定义。如果一个已经开始运行的急切操作被丢弃，可选的处理方式只有把这种情况定为未定义行为，或者在析构函数里阻塞，两者都不令人满意。这就是 [[exec.adapt]] 禁止发送器适配器在 `connect` 与 `start` 之前产生可观察效果的来由。

完成签名要求所有发送器都声明自己完成时会发送哪些类型（§5.8），理由是高效地处理异步结果需要事先知道数据的类型。例如 `when_all` 要在操作状态里为每个子操作的结果预留存储，`sync_wait` 要知道返回什么类型的 `optional<tuple<...>>`。P2300 还扩展了 P0443 的 typed sender 设计，允许签名依赖于通过接收器较晚提供的信息（环境），这是 [[exec.snd]] 里 `sender_in<Sndr, Env>` 带环境参数的原因。

### 取消与环境

P1525 讨论的取消问题，由 Baker 的 [[P2175R0]]（*Composable cancellation for sender-based async operations*，2020 年 12 月）给出了具体方案：接收器通过环境提供一个停止令牌（stop token），发送器在需要时查询它。这依赖 C++20 已有的 `std::stop_token` 一族（[[thread.stoptoken]]），P2300 又增加了不分配内存的 `inplace_stop_token`。今天的 [[exec.get.stop.token]] 就是这条线的结果。

### 网络库的争论（2021）

P2300 发表的同时，网络库仍然在等执行器。Networking TS 早在 2018 年 4 月就以 ISO/IEC TS 19216:2018 发布（最后的工作草案见 [[N4771]]），它的执行器模型就是 Kohlhoff 的 Asio 模型。如果执行器换成了发送器，网络库要不要跟着改？2021 年秋季，这个问题在 LEWG 引发了一组论文：

- Kohlhoff 的 [[P2444R0]]（*The Asio asynchronous model*，2021 年 9 月）完整描述了 Asio 的异步模型；
- Voutilainen 的 [[P2464R0]]（*Ruminations on networking and executors*，2021 年 9 月）主张不按当时的设计标准化 Networking TS；
- Kohlhoff、Allsop、Falco、Hodges、Morgenstern 的 [[P2469R0]]（*Response to P2464: The Networking TS is baked, P2300 Sender/Receiver is not.*，2021 年 10 月）逐条反驳；
- Shoop 的 [[P2471R1]]（*NetTS, ASIO and Sender Library Design Comparison*）对比两种设计，Kohlhoff 等人又以 [[P2480R0]] 回应，称其需要更正和补充。

P2464 的核心论点是：P0443 的执行器不能报告失败。它写道 "A P0443 executor is not an executor. It's a work-submitter."，无法得知提交的工作是否成功、是否发生了错误。Networking TS 实际上假定执行器在提交和调用延续之间不会失败，但标准化的执行器抽象会有大量网络库之外的实现，它们不受这个假定约束；而且 TS 没有提供泛型地组合异步操作的方式。P2464 的最低建议是把 Networking TS 里的 P0443 执行器换成 P2300 的调度器，更进一步的建议是 C++23 不再推进 Networking TS，先完成发送器/接收器，再在其上建立网络库。

P2469 的立场相反。它认为执行器是任何异步模型都不可缺少的部分，缺少异步尾调用（原文 tail call）定制点的模型不适合 C++ 的许多应用领域；Asio 有基于完成令牌的成熟组合方式，经过多年生产使用；P2300 不是一个异步模型，而是在某个假定的异步模型之上组合异步操作的 DSL；Asio 的模型提供的功能是 P2300 的超集，P2300 的高层抽象可以而且应该建立在它之上。

LEWG 随后在 2021 年 10 月做了电子投票。投票题目见 [[P2452R0]]，结果和主席的解读见 [[P2453R0]]（*2021 October Library Evolution Poll Outcomes*）：

| 投票内容（概括） | 强烈赞成 / 赞成 / 中立 / 反对 / 强烈反对 | 结论 |
|---|---|---|
| Asio 模型（P2444）是网络、并行、GPU 等异步用例的良好基础 | 5 / 10 / 6 / 14 / 18 | 弱共识反对 |
| 发送器/接收器模型（P2300）是大多数异步用例的良好基础 | 24 / 16 / 3 / 6 / 3 | 共识赞成 |
| 停止把 Networking TS/Asio 的设计作为标准网络方案 | 13 / 13 / 8 / 6 / 10 | 无共识 |
| 标准网络库应建立在发送器/接收器之上 | 17 / 11 / 10 / 4 / 6 | 弱共识赞成 |
| 不带安全套接字（TLS/DTLS）的网络库可以发布 | 9 / 13 / 5 / 6 / 13 | 无共识 |

P2453R0 对这些结果作了限定：第一项并不否定 Asio 用于网络，许多意见认为它在网络领域是可行的，反对主要集中在并行和 GPU 场景；第二项不意味着 P2300 进入 C++23；Networking TS 没有被宣布终止，但它需要重新建立共识，而且进入 C++23 已经极不可能。文档还说，网络相关论文回到 LEWG 之前，必须充分处理安全问题和与发送器/接收器模型的关系。

### C++23 的投票与 C++26 的目标

2022 年 1 月，LEWG 就是否把 [[P2300R4]] 作为重点项目送交 LWG、目标 C++23 进行了电子投票。据 [[P2459R0]]（*2022 January Library Evolution Poll Outcomes*），结果是 23 / 14 / 0 / 6 / 11，没有达成共识。文档记录的反对理由主要是规模太大、时间太晚：在 C++23 周期的末尾加入如此新颖、仍在变化的大型提案，措辞审查恐怕来不及完成；多位反对者建议改为 C++26。赞成者中则有人称它是 C++23 能交付的最重要的东西。

此后 P2300 继续修订，作者名单加入了 Georgy Evtushenko、Lucian Radu Teodorescu。几次影响较大的修改是：

- **定制机制**。早期修订用 `tag_invoke`（[[P1895R0]]）实现定制；Voutilainen 的 [[P2855R1]]（*Member customization points for Senders and Receivers*）主张改用成员函数。P2300R9 的修订记录写明按 P2855R1 用成员函数取代了 `tag_invoke`。所以今天 `set_value(rcvr, vs...)` 等价于 `rcvr.set_value(vs...)`，见 [[exec]] 导读里的说明。
- **算法定制与 domain**。有些执行资源需要把 `then`、`bulk` 这类算法换成专门的实现，GPU 是最常举的例子（后文 P3826 用的就是这个例子）。Niebler 的 [[P2999R3]]（*Sender Algorithm Customization*）引入了基于 domain 的定制。P2300R10 的修订记录承认，P2999R3 的设计在并入时没有完全落实，详见 [[P3303R1]]（*Fixing Lazy Sender Algorithm Customization*）。
- **删除急切算法**。Shoop 和 Baker 的 [[P3187R1]]（*remove ensure_started and start_detached from P2300*）主张删除 `ensure_started` 和 `start_detached`，因为它们启动的工作无人负责等待，可能比它引用的对象活得更久。P2300R10 按此删除了这两个算法，以及 `execute`，替代品留给 async scope（见第六节）。
- **改名**。按 Niebler 的 [[P3175R3]]（*Reconsidering the std::execution::on algorithm*），`transfer` 改名为 `continues_on`，原来的 `on` 改名为 `starts_on`，新的 `on` 组合了两者（[[exec.on]]）。

2024 年 2 月的 [[P3109R0]]（*A plan for std::execution for C++26*，Baker、Niebler、Shoop、Teodorescu）把剩余工作分级：改为成员函数定制、删除 `ensure_started` 这类破坏性改动必须在发布前完成；async scope、协程任务类型、系统执行上下文则是让首个版本真正可用的配套设施。

据 Sutter 的东京会议报告（2024 年 3 月），P2300 此时已经获得 C++26 的设计批准；论文约 45,000 词，其中约 20,000 词是规范措辞，LWG 用了四分之一的会议时间完成了对全文的第一遍审查。

### St. Louis：进入 C++26

2024 年 6 月的 St. Louis 会议通过了 [[P2300R10]]，将其并入 C++26 工作草案。Sutter 在会后报告中写道，由于规模很大，LWG 的措辞审查花了额外的时间，审查中出现的问题又需要回到 LEWG 澄清和微调设计（Sutter，*Trip report: Summer ISO C++ standards meeting (St Louis, MO, USA)*，2024 年 7 月）。报告还引述了几个使用者的经验，包括 Voutilainen 用参考实现写的、与 C++20 协程和 Qt 进度条集成的并发 HTTPS 分块下载示例。

从 2012 年的 N3378 算起，执行器问题到这时才在标准里有了答案，前后十二年；而且答案里已经没有执行器这个概念。

## 六、C++26 定稿前的补充（2024–2026）

P2300 并入后，P3109 列出的配套设施陆续进入草案，原有设计也在国家成员体（NB）意见阶段继续修改。

### async scope：让急切启动的工作有人负责

Petersen、Wong 等人的 [[P3149R11]]（*async_scope — Creating scopes for non-sequential concurrency*）提供了 `counting_scope`、`simple_counting_scope`、`spawn`、`spawn_future`、`associate` 等设施：被急切启动的工作必须关联到某个 scope，scope 负责在结束前等待它们完成。Sutter 在 2025 年 6 月的 Sofia 会议报告中说，这让 RAII 风格可以用于非顺序、非基于栈的代码（Sutter，*Trip report: June 2025 ISO C++ standards meeting (Sofia, Bulgaria)*）。规则见 [[exec.scope]] 与 [[exec.spawn]]。

### parallel_scheduler：标准线程池

[[P2079R10]]（*Parallel Scheduler*，Teodorescu、Arutyunyan、Howes、Voss）同样在 Sofia 会议通过。这份提案的标题几经变化，反映了它的设计变化：R0（2020 年 1 月）叫 *Shared execution engine for executors*，R1 叫 *Parallel Executor*，2024 年的 R5 叫 *System execution context*，最后定名 *Parallel Scheduler*。Sutter 的报告称它提供了一个可移植地保证向前进展的标准异步执行上下文，也就是线程池的接口。它还允许替换后端（[[exec.parschedrepl]]）。规则见 [[exec.par.scheduler]]。

### 与协程的关系

协程和执行器的关系从一开始就纠缠在一起。2015–2016 年，Gor Nishanov 的 [[P0055R1]]（*On Interactions Between Coroutines and Networking Library*）和 Kohlhoff 的 [[P0286R0]]（*A networking library extension to support co_await-based coroutines*）讨论了协程与 Asio 风格的异步操作怎样配合。C++20 在 2019 年 2 月的 Kona 会议通过 [[P0912R5]] 并入了协程的语言机制，但没有提供任何协程类型；Baker 和 Nishanov 2018 年的 [[P1056R1]]（*Add lazy coroutine (coroutine task) type*）没有被采纳。

P2300 本身就包含协程的桥梁：任何可等待（awaitable）类型自动是发送器；`as_awaitable` 把发送器变成可在协程中 `co_await` 的对象；`with_awaitable_senders` 让协程的 promise 类型支持直接 `co_await` 发送器（P2300R10 §4.15–4.16；[[exec.as.awaitable]]）。后者只把发送单一类型单一值的发送器识别为可等待，因为回调可以携带多个值或重载的签名，而 `co_await` 表达式只能有一个结果。

缺的是一个标准的协程任务类型。Kühl 和 Nadolski 的 [[P3552R3]]（*Add a Coroutine Task Type*，R0 的标题是 *Add a Coroutine Lazy Type*）提供了 `std::execution::task`，同样在 Sofia 会议通过；Sutter 的报告称它用于把协程与发送器/接收器整合起来。之后的讨论集中在 `task` 的细节上，例如 Müller 的 [[P3801R0]]（*Concerns about the design of std::execution::task*）和 Kühl 的 [[P3796R1]]（*Coroutine Task Issues*）。Kühl 的 [[P3941R4]]（*Scheduler Affinity*）回应了五条美国 NB 意见，规定 `task` 怎样回到启动它的调度器，并引入了 `get_start_scheduler` 查询；当前草案里对应的是 [[exec.affine]] 和 [[exec.get.start.scheduler]]。规则见 [[exec.task]]，协程的语言机制见 [[topics/coroutines]]。

!!! example "依据当前草案写成的协程与发送器混用（未在本机验证，不标判定）"
    ```cpp
    #include <execution>
    namespace ex = std::execution;

    ex::task<int> compute(ex::scheduler auto sch) {
      int a = co_await (ex::schedule(sch) | ex::then([] { return 20; }));
      int b = co_await (ex::just(22));
      co_return a + b;
    }

    int main() {
      auto sch = ex::get_parallel_scheduler();
      auto [v] = std::this_thread::sync_wait(compute(sch)).value();
      return v == 42 ? 0 : 1;
    }
    ```

### domain 的再修订

算法定制在 P2300 并入后又经历了两轮修改。Niebler 的 [[P3718R0]]（*Fixing Lazy Sender Algorithm Customization, Again*）和 [[P3826R5]]（*Fix Sender Algorithm Customization*）处理的问题是：许多发送器（例如 `just()`）在知道自己从哪里启动之前，无法知道自己在哪个 domain 上完成，于是在 `starts_on(gpu, just())` 之后的 `then` 可能选中 CPU 的实现。P3826 的 R0 曾建议把算法定制推迟到 C++29，后续修订改为在 C++26 内修复：查询发送器的完成 domain 时传入接收器的环境，增加 `get_completion_domain` 查询和 `indeterminate_domain`，并删除早期定制。据该文修订记录，R5 吸收了 2026 年 3 月 LWG 措辞审查的意见。当前草案中的 [[exec.get.compl.domain]]、[[exec.domain.indeterminate]] 与这一设计一致，规则见 [[exec.snd.transform]]。

### 其他修改

- 完成签名的计算方式由 Niebler 的 [[P3557R3]]（*High-Quality Sender Diagnostics with Constexpr Exceptions*）改为无实参的 `consteval` 函数模板 `get_completion_signatures<Sndr, Env...>()`，类型错误通过在常量求值中抛出异常报告（[[exec.getcomplsigs]]）。
- [[P3481R5]]（*std::execution::bulk() issues*）重新整理了 `bulk`，当前草案中有 `bulk`、`bulk_chunked`、`bulk_unchunked` 三个算法（[[exec.bulk]]）。
- Leahy 的 [[P3682R0]]（*Remove std::execution::split*）提议删除 `split`；当前草案中已经没有这个算法。
- Niebler 的 [[P3284R4]]（*write_env and unstoppable Sender Adaptors*）加入了 [[exec.write.env]] 和 [[exec.unstoppable]]。

以上修改分别在哪次会议通过，本页只在有会议报告佐证时给出（Sofia 的三项）；其余的以当前草案的内容为准。

## 七、[exec] 的形状从哪里来

### 同一件事的几代写法

同一件事，例如在线程池上算出一个整数、再把结果交给下一步，放在不同年代的提案里写，可以直观地看到接口重心的转移。下面前三段都是历史提案的写法，从未标准化，按各自论文的设计简化写成。

```cpp title="N3562 风格（2013，历史提案）"
// 执行器只接受 void() 闭包；结果怎么传出去，由用户自己安排
thread_pool pool(4);
std::promise<int> p;
std::future<int> f = p.get_future();
pool.add([&p] { p.set_value(6 * 7); });
int v = f.get();
```

这里执行器只负责运行一个闭包。结果要靠 `promise`/`future` 传出，错误要靠用户自己在闭包里捕获，取消没有任何约定。

```cpp title="Asio / Networking TS 风格（2014–2018，历史提案）"
// 执行器是上下文的句柄；结果通过完成处理器传递
asio::thread_pool pool(4);
asio::post(pool.get_executor(), [] {
  int v = 6 * 7;
  // 把 v 交给下一步：再 post 一个处理器，或通过完成令牌返回 future / 恢复协程
});
```

Asio 的执行器同样只提交 `void()` 工作，但异步操作有一套成熟的约定：完成处理器的第一个参数通常是 `error_code`，处理器带着关联执行器，结果的交付方式由完成令牌决定。

```cpp title="P0443R14 风格（2020，历史提案）"
// 执行器：急切提交；调度器：惰性产生发送器
execution::execute(ex, [] { /* 结果无处可去，错误由执行器按实现定义处理 */ });

auto s = execution::schedule(sch);            // 发送器
auto op = execution::connect(std::move(s), my_receiver{});
execution::start(op);                          // my_receiver 有 set_value / set_error / set_done
```

P0443 的最后一版里两套接口并存，这正是 P1525 和 P2235 批评的对象。

```cpp title="依据当前草案（C++26）；未在本机验证，不标判定"
#include <execution>
#include <exception>
#include <print>
namespace ex = std::execution;

struct print_receiver {
  using receiver_concept = ex::receiver_tag;
  void set_value(int v) && noexcept { std::println("value {}", v); }
  void set_error(std::exception_ptr) && noexcept { std::println("error"); }
  void set_stopped() && noexcept { std::println("stopped"); }
};

int main() {
  auto sch = ex::get_parallel_scheduler();
  auto work = ex::schedule(sch) | ex::then([] { return 6 * 7; });

  // 手工走一遍 connect / start；正常代码用 sync_wait 或 spawn 代劳
  auto op = ex::connect(std::move(work), print_receiver{});
  ex::start(op);
  // 这里必须等 op 完成后才能让它离开作用域，例子从略
}
```

当前草案里只剩下最后一种：没有执行器，工作从 `schedule` 产生的发送器开始，用适配器组合，`connect` 得到操作状态，`start` 启动，结果通过接收器的三个完成函数之一交付。接收器类型用 `receiver_concept` 标签选择加入（[[exec.recv]]）；标签名 `receiver_tag` 与 [[P3940R0]]（*Rename concept tags for C++26: sender_t to sender_tag*）提议的改名一致，较早的资料里写作 `receiver_t`。例子最后一行的注释也说明了这个模型的代价：操作状态的生存期由调用者负责，这正是 [[exec.async.ops]] 和 [[exec.scope]] 花大量篇幅规定的内容。

### 对照表

把上面的历史与 [[exec]] 的条文对照，可以得到下面这张表。

| [exec] 中的设计 | 历史来源 | 对应条款 |
|---|---|---|
| 没有 `executor` 概念，只有 `scheduler` | P1525 论证调度器更基础；P2235；P2300 按 SG1 方向删除执行器 | [[exec.sched]] |
| 接收器有值、错误、停止三个完成函数，恰好调用一个 | P1053、P1194 的三通道；P1525 关于错误和取消的论证 | [[exec.recv]]、[[exec.async.ops]] |
| `connect` 返回操作状态，`start` 才启动 | P2006 为消除堆分配拆分 `submit` | [[exec.connect]]、[[exec.opstate]] |
| 发送器是惰性的，适配器在 `start` 前无可观察效果 | P1194 引入惰性；P2300 §4.10 拒绝急切模型 | [[exec.adapt]] |
| 发送器必须声明完成签名，且可依赖环境 | P2300 放弃无类型发送器；P3557 改为 `consteval` 计算 | [[exec.cmplsig]]、[[exec.getcomplsigs]] |
| 取消通过环境中的停止令牌传递 | P1525 的取消论证；P2175 | [[exec.get.stop.token]]、[[thread.stoptoken]] |
| 环境与查询，而没有 require/prefer | P0688、P1393 的属性机制只保留了 query 的一半 | [[exec.queryable]]、[[exec.env]] |
| 用成员函数而不是 `tag_invoke` 定制 | P1895 → P2855 | [[exec]] |
| domain 与 `transform_sender` | P2999、P3303、P3718、P3826 | [[exec.snd.transform]] |
| 没有 `start_detached`、`ensure_started`，改用 scope | P3187、P3149 | [[exec.scope]]、[[exec.spawn]] |
| `parallel_scheduler` 而不是 `static_thread_pool` | P0443 曾含 `static_thread_pool`，P2300 按 LEWG 方向不含线程池；P2079 | [[exec.par.scheduler]] |
| 协程桥梁与 `task` | P2300 的 `as_awaitable`、`with_awaitable_senders`；P3552；P3941 | [[exec.as.awaitable]]、[[exec.task]] |

另一方面，P0443 关心而 [exec] 没有完全接住的问题也很清楚：并行算法仍然只能接受执行策略，不能指定调度器；属性的 require/prefer 没有进入标准；网络库没有进入标准。

## 八、时间线

| 年份 | 事件 | 文档 |
|---|---|---|
| 2006 | Kohlhoff 向 TR2 提出基于 Asio 的网络库 | [[N2054]] |
| 2012 | Google 的初步执行器提案 | [[N3378]] |
| 2013 | Google 执行器修订版；NVIDIA 等提出并行算法库；Kohlhoff 的通用异步操作模型 | [[N3562]]、[[N3554]]、[[N3747]] |
| 2014 | Kohlhoff 提出基于模板的执行器，回应 N3785 | [[N4046]]、[[N4242]] |
| 2015 | Parallelism TS 发布；NVIDIA 主张并行算法需要执行器；SG1 在 Kona 要求统一 | [[N4507]]、[[N4406]]、[[P0058R1]]、[[P2033R0]] |
| 2016 | Parallelism TS 并入 C++17（Jacksonville）；P0443R0 发表（Issaquah） | [[P0024R2]]、[[P0443R0]] |
| 2017 | 属性简化；SG1 在 Albuquerque 确认 P0443 为首选方向 | [[P0688R0]]、[[P0761R0]] |
| 2018 | Networking TS 发布；Facebook 方面提出发送器/接收器；Bellevue 执行器专门会议 | [[N4771]]、[[P1055R0]]、[[P1194R0]]、[[P1244R0]] |
| 2019 | 属性机制独立成文；执行器未赶上 C++20（Kona）；Cologne 妥协加入调度器与发送器 | [[P1393R0]]、[[P1660R0]]、[[P1525R0]]、[[P0443R11]] |
| 2020 | `connect`/`start` 取代 `submit`；P0443 最后一版；P1525R1 | [[P2006R1]]、[[P0443R14]]、[[P1525R1]]、[[P2235R0]] |
| 2021 | P2300 发表；网络库争论；LEWG 投票支持发送器/接收器 | [[P2300R0]]、[[P2464R0]]、[[P2469R0]]、[[P2453R0]] |
| 2022 | 送交 C++23 的投票未达成共识 | [[P2459R0]] |
| 2023 | domain 定制；以发送器/接收器重写网络接口的提案 | [[P2999R3]]、[[P2762R2]] |
| 2024 | 成员函数定制；删除急切算法；St. Louis 会议并入 C++26 | [[P2855R1]]、[[P3187R1]]、[[P2300R10]] |
| 2025 | Sofia 会议通过 async scope、并行调度器、协程任务类型 | [[P3149R11]]、[[P2079R10]]、[[P3552R3]] |
| 2026 | C++26 定稿前修订算法定制与调度器亲和性 | [[P3826R5]]、[[P3941R4]] |

## 九、现状与未来

### C++26 之后仍未解决的部分

Sutter 在 2026 年 3 月 C++26 技术工作完成后的报告中，把 `std::execution` 列为 C++26 的四大特性之一，同时提醒它目前缺少好的文档，比大多数 C++ 特性更难上手。截至写作时，以下工作仍在进行，都只是提案，不代表委员会的结论：

- **网络**。2021 年的投票之后，网络库的方向转向发送器/接收器。Kühl 的 [[P2762R2]]（*Sender/Receiver Interface For Networking*）以发送器改写 Networking TS 的接口；Rodgers 的 [[P3185R0]] 和 Rodgers、Kühl 的 [[P3482R1]]（*Design for C++ networking based on IETF TAPS*）提出以 IETF TAPS 为基础、默认安全连接的设计。据 Sutter 的 2023 年 11 月 Kona 会议报告，当时已不清楚网络库能否赶上 C++26；它最终没有进入 C++26。2026 年，Falco 发表了一组回顾与呼吁性质的信息论文，例如 [[P4099R1]]（*Info: The Twenty-One Year Networking Arc*）和 [[P4048R0]]（*Info: Networking for C++29: A Call to Action*）。
- **并行算法与调度器**。[[P2500R2]] 和 [[P3300R0]] 讨论怎样让并行算法接受调度器、怎样提供返回发送器的异步并行算法。
- **协程任务类型**。[[P4007R3]]（*Info: Open Issues in std::execution::task*）等文档在整理 `task` 的遗留问题；也有论文讨论发送器与协程的组合成本和互操作，例如 [[P2583R4]]（*Info: Symmetric Transfer and Sender Composition*）。
- **其他扩展**。例如 Vollmann 的 [[P3669R4]]（*Non-Blocking Support for std::execution*）、Williams 的 [[P3296R6]]（*let_async_scope*）、[[P4320R1]]（*std::execution::sequence*）。

### 仍有争议的问题

围绕 2021 年那场争论的不同看法并没有消失。P2469 的作者们认为 Asio 的执行器提供了 P2300 所缺的尾调用定制点，发送器应该建立在这样的异步模型之上；P2464 和 P1525 的作者们认为不能报告错误和取消的执行器不适合作为泛型基础。2026 年的一些信息论文（例如 [[P4094R1]]、[[P4096R1]]、[[P4097R1]]）对 P0443 的统一、P2464 和 P2453 的投票重新作了回顾和评述。这些文档代表作者本人的观点；本页不评价哪一方正确，只指出：今天的 [exec] 采纳的是 P2300 的模型，而 C++ 标准网络库的接口尚未确定。

## 参考资料

**WG21 文档**（按主题）

- Google 执行器：[[N3378]]、[[N3562]]、[[N3731]]、[[N3785]]、[[N4143]]、[[N4414]]
- Kohlhoff / Asio：[[N2054]]、[[N3747]]、[[N4045]]、[[N4046]]、[[N4242]]、[[N4370]]、[[P0113R0]]、[[P2444R0]]
- 并行算法与执行策略：[[N3554]]、[[N4406]]、[[N4507]]、[[P0024R2]]、[[P0058R1]]、[[P1001R2]]、[[P1019R2]]、[[P2500R2]]、[[P3179R9]]、[[P3300R0]]
- 统一执行器与属性：[[P0443R0]]、[[P0443R11]]、[[P0443R14]]、[[P0688R0]]、[[P0761R0]]、[[P1244R0]]、[[P1393R0]]、[[P1658R0]]、[[P1660R0]]、[[P2033R0]]、[[P2183R0]]、[[P2202R0]]、[[P2219R0]]
- 发送器/接收器的批评：[[P1053R1]]、[[P1055R0]]、[[P1194R0]]、[[P1341R0]]、[[P1525R0]]、[[P1525R1]]、[[P1738R0]]、[[P2006R0]]、[[P2006R1]]、[[P2175R0]]、[[P2235R0]]
- P2300 及其修改：[[P2300R0]]、[[P2300R4]]、[[P2300R10]]、[[P1895R0]]、[[P2855R1]]、[[P2999R3]]、[[P3109R0]]、[[P3175R3]]、[[P3187R1]]、[[P3303R1]]
- 网络库争论与投票：[[P2452R0]]、[[P2453R0]]、[[P2459R0]]、[[P2464R0]]、[[P2469R0]]、[[P2471R1]]、[[P2480R0]]、[[P0592R4]]
- C++26 的补充：[[P2079R10]]、[[P3149R11]]、[[P3552R3]]、[[P3557R3]]、[[P3481R5]]、[[P3682R0]]、[[P3284R4]]、[[P3718R0]]、[[P3826R5]]、[[P3941R4]]、[[P3801R0]]、[[P3796R1]]
- 协程：[[P0055R1]]、[[P0286R0]]、[[P0912R5]]、[[P1056R1]]
- 进行中：[[P2762R2]]、[[P3185R0]]、[[P3482R1]]、[[P3669R4]]、[[P3296R6]]、[[P4320R1]]、[[P4007R3]]、[[P2583R4]]、[[P4048R0]]、[[P4094R1]]、[[P4096R1]]、[[P4097R1]]、[[P4099R1]]

**会议报告与其他**

- Herb Sutter，[Trip report: Winter ISO C++ standards meeting](https://herbsutter.com/2016/03/11/trip-report-winter-iso-c-standards-meeting/)（Jacksonville，2016 年 3 月）
- Herb Sutter，[Trip report: Fall ISO C++ standards meeting (San Diego)](https://herbsutter.com/2018/11/13/trip-report-fall-iso-c-standards-meeting-san-diego/)（2018 年 11 月）
- Herb Sutter，Kona 会议报告（2019 年 2 月），见 [herbsutter.com 2019 年 2 月归档](https://herbsutter.com/2019/02/)
- Herb Sutter，[Trip report: Autumn ISO C++ standards meeting (Kona, HI, USA)](https://herbsutter.com/2023/11/11/trip-report-autumn-iso-c-standards-meeting-kona-hi-usa/)（2023 年 11 月）
- Herb Sutter，[Trip report: Winter ISO C++ standards meeting (Tokyo, Japan)](https://herbsutter.com/2024/03/22/trip-report-winter-iso-c-standards-meeting-tokyo-japan/)（2024 年 3 月）
- Herb Sutter，[Trip report: Summer ISO C++ standards meeting (St Louis, MO, USA)](https://herbsutter.com/2024/07/02/trip-report-summer-iso-c-standards-meeting-st-louis-mo-usa/)（2024 年 7 月）
- Herb Sutter，[Trip report: June 2025 ISO C++ standards meeting (Sofia, Bulgaria)](https://herbsutter.com/2025/06/21/trip-report-june-2025-iso-c-standards-meeting-sofia-bulgaria/)（2025 年 6 月）
- Herb Sutter，London Croydon 会议报告（2026 年 3 月），见 [herbsutter.com 2026 年 3 月归档](https://herbsutter.com/2026/03/)
- Bjarne Stroustrup，*Thriving in a Crowded and Changing World: C++ 2006–2020*，HOPL IV（2020），§8.5、§8.8.1、§9.4
- Eric Niebler，[Structured Concurrency](https://ericniebler.com/2020/11/08/structured-concurrency/)（2020 年 11 月）
- Eric Niebler，[What are Senders Good For, Anyway?](https://ericniebler.com/2024/02/04/what-are-senders-good-for-anyway/)（2024 年 2 月）
- ISO/IEC TS 19570:2015（Parallelism TS）；ISO/IEC TS 19216:2018（Networking TS）
