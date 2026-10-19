---
title: 执行器的十年：从 executors 到 std::execution
summary: C++26 的 std::execution 为什么没有 executor，却有发送器、接收器、操作状态和调度器；早期执行器设计的缺陷怎样一步步塑造了今天的 [exec]，网络库又为什么因此没有进入标准。
status: draft
order: 30
papers: N3562, N4046, N4406, P0443R14, P1525R1, P2006R1, P2300R10, P2464R0, P2469R0, P3149R11, P2079R10, P3552R3
related: exec, exec.async.ops, exec.snd, exec.recv, exec.sched, exec.cmplsig, exec.snd.transform, exec.scope, exec.task, exec.par.scheduler, execpol, algorithms.parallel, topics/coroutines
tags: 沿革, 并发, 并行, std::execution, 网络
updated: 2026-10-19
---

!!! tldr
    - C++26 的 [[exec]] 没有 executor 概念：工作从调度器产生的发送器开始，用 `connect` 得到操作状态，`start` 启动，结果经接收器的三个完成函数之一交付。
    - 早期的执行器只做一件事：把一个 `void()` 闭包交给某处运行。提交之后，结果、错误和取消都没有标准的通道送回来，这是它最终被放弃的主要技术原因。
    - 发送器惰性、`connect`/`start` 分两步、操作状态不可移动，都是为了让异步操作的状态不必分配在堆上。
    - C++17 的执行策略只说明一次算法调用可以怎样并行，不说明在哪里运行，所以并行算法至今不能指定线程池。
    - Networking TS 建立在旧的执行器模型上，因异步模型之争没有进入 C++26。

## 问题：把工作交给别处运行，结果怎么回来

C++11 有了 `std::thread` 和 `std::async`，但没有线程池，也没有一个通用接口来表示把这段工作交给某个执行资源（线程池、事件循环、GPU）去运行。**执行器**（executor）就是为这个接口起的名字。

最早的执行器提案来自 Google（[[N3562]]，2013）。它的设计很直接：执行器是抽象基类，工作用 `std::function<void()>` 做类型擦除。

```cpp title="N3562 风格（历史提案，从未标准化；简化）"
class executor {
public:
  virtual ~executor();
  virtual void add(std::function<void()> closure) = 0;
};

thread_pool pool(4);
std::promise<int> p;
std::future<int> f = p.get_future();
pool.add([&p] { p.set_value(6 * 7); });
int v = f.get();
```

执行器只负责运行闭包。结果要靠用户自己用 `promise`/`future` 传出，闭包里抛出的异常要自己捕获，执行器决定不运行这段工作时也没有任何约定。对线程池上的粗粒度任务，一次虚函数调用和一次类型擦除的开销可以忽略，这个设计够用。

后面十年的争论，基本都围绕这段代码里缺的东西展开。

## 三种需求，三套设计（2013–2015）

除了 Google 的线程池接口，另外两类用户也需要执行器，而且需求差别很大。

**异步 I/O。** Christopher Kohlhoff 的 Asio（2005 年进入 Boost）里到处是异步操作的完成回调，每个回调都很小。他在 [[N4046]]（2014）中指出，虚接口和 `std::function` 让编译器无法内联多层叠加的回调，`std::function` 还要求可复制，排除了只能移动的函数对象。他的替代方案用一句话概括：

!!! history "N4046，§1"
    "An executor is to function execution as an allocator is to allocation."
    执行器应当是轻量的、基于模板的策略对象，就像分配器之于内存分配。

N4046 把**执行上下文**（线程池、事件循环本身）和执行器（指向上下文的轻量句柄）分开，并按是否允许在调用者的线程上立即执行，区分了 `dispatch`、`post`、`defer` 三种提交方式。

```cpp title="Asio / N4046 风格（历史提案，从未标准化）"
asio::io_context ctx;
auto ex = ctx.get_executor();      // 上下文的句柄
asio::post(ex, [] { /* ... */ });  // 不在调用者的栈上执行
```

**批量并行。** NVIDIA 等公司关心的是并行算法和 GPU：一次调用要创建成千上万个执行代理，所以需要**批量执行**（bulk execution）接口（[[P0058R1]]）。

到 2015 年，WG21 手里有三套各有侧重的执行器。负责并发的研究组 SG1 要求作者们把它们统一起来（Hoberock，[[P2033R0]]）。

## 执行策略先进了标准（C++17）

执行器还在争论时，并行算法先进入了 C++17（[[P0024R2]]）。它们接受一个**执行策略**参数：

```cpp run ok flags="-std=c++2c -fexperimental-library"
#include <algorithm>
#include <execution>
#include <vector>

int main() {
  std::vector<int> v{3, 1, 2};
  std::sort(std::execution::par, v.begin(), v.end());       // 允许并行
  std::sort(std::execution::par_unseq, v.begin(), v.end()); // 允许并行和向量化
  return v.front() == 1 ? 0 : 1;
}
```

本机 Clang 23 + libc++ 要加 `-fexperimental-library` 才提供这几个策略对象。

执行策略和执行器常被混为一谈，但两者回答的是不同的问题。策略是一张许可证，说明实现可以怎样调度[[g:element-access-function|元素访问函数]]，以及因此对用户代码提出什么要求，比如 `par_unseq` 下不得加锁（[[execpol]]、[[algorithms.parallel]]）。工作在哪些线程上运行，策略不管。NVIDIA 的作者在 [[N4406]] 中就指出，后者应当由执行器决定，并提议这样组合：

```cpp title="N4406 风格（历史提案，从未标准化）"
std::sort(par.on(my_exec), data.begin(), data.end());
```

这种组合依赖执行器的设计，所以一直没有进入标准。今天 `std::sort(std::execution::par, ...)` 在哪些线程上运行完全由实现决定。让并行算法接受调度器的提案（如 [[P2500R2]]）截至写作时仍未进入草案。

## P0443：把三套需求放进一个提案（2016–2020）

### 组合爆炸与属性

统一提案 [[P0443R0]]（2016）的办法是把三方的需求都放进来。据 [[P2033R0]] 的统计，R0 有七种执行器类别和十五个执行函数，函数名本身编码了三个维度：是否阻塞、是否返回 future、单个还是批量。`execute`、`post`、`defer`、`async_execute`、`then_execute`、`bulk_then_execute`……组合迅速膨胀。

后来的修订（[[P0688R0]]）把这些维度从函数名里拿出来，变成可以向执行器要求的**属性**（property）：

```cpp title="P0443R2 之后的属性写法（历史提案，从未标准化）"
// require：必须满足，否则编译失败；prefer：尽量满足
auto ex2 = execution::require(ex, execution::oneway,
                              execution::never_blocking);
ex2.execute(f);
auto ex3 = execution::prefer(ex2, execution::continuation);
```

属性机制最终没有进入标准。它在今天的 [[exec]] 里只留下了一半：可以通过环境查询（[[exec.queryable]]、[[exec.env]]）询问一个对象的性质，但没有 require/prefer 这种改变对象的操作。

### 错过 C++20

P0443 原本有望进入 C++20，最终没有赶上，依赖它的网络库也一起推迟。Stroustrup 把这件事称为 "the best is the enemy of the good" 的例子（HOPL IV，§8.8.1）。

## 单向 execute 为什么不行（2018–2020）

到 P0443 的最后几版，核心操作是单向的 `execute(ex, f)`：急切地提交一个 `void()` 函数对象，返回 `void`。另一组作者从实践出发批评了这个基础操作，系统的论证在 [[P1525R1]]（*One-Way execute is a Poor Basis Operation*）里。它的结论是：

!!! history "P1525R1，§1"
    "The scheduler concept is a more foundational abstraction than the executor concept."
    产生发送器的调度器比单向 `execute` 的执行器更基础。

P1525R1 给出了三条技术理由。

1. **错误无法传播。** 提交时的错误也许能用异常报告，但提交之后、执行之前发生的错误（比如执行器延迟创建线程时失败，或者带截止时间的执行器撤销了超时的工作）没有任何通道送回。各执行器怎样处理由实现决定，泛型代码无从应对。
2. **取消无法传播。** 执行器决定不运行已提交的工作时，除了销毁函数对象之外没有办法通知它，而销毁并不是表达取消的合适方式。
3. **需要动态分配。** 急切提交意味着每个异步任务的状态都要分配在堆上，因为调用者事先不知道需要多大的存储。

论文还指出，用调度器可以实现 `execute`，反过来却不能保真地实现。

<div class="compare" markdown="1">

```cpp title="P0443 的 execute（历史提案）"
// 返回 void
execution::execute(ex, [] {
  int v = 6 * 7;
  // v 交给谁？
  // 出错了告诉谁？
  // ex 不运行它，谁知道？
});
```

```cpp title="C++26 的接收器"
struct print_receiver {
  using receiver_concept =
      ex::receiver_tag;
  void set_value(int) && noexcept;
  void set_error(std::exception_ptr)
      && noexcept;
  void set_stopped() && noexcept;
};
```

</div>

右边就是今天的回答：工作完成时恰好调用接收器的三个完成函数之一，值、错误、停止各有一个通道（[[exec.recv]]、[[exec.async.ops]]）。这个三通道的接收器最早出现在 2018 年对 P0443 的修改建议 [[P1194R0]] 中，当时第三个通道叫 `set_done`，后来改名为 `set_stopped`（[[exec.set.stopped]]）。

## 发送器/接收器怎样回答这些问题

2021 年的 [[P2300R0]]（*std::execution*）在 P0443 的基础上做了根本性的改动：删除执行器概念，一切建立在调度器和发送器之上。2024 年，它的 R10 并入 C++26。今天 [[exec]] 的主要规则，几乎都能追溯到上一节的三条批评。

### 一段工作的完整流程

```cpp title="依据当前草案（C++26）；本机 libc++ 尚未提供发送器，不标判定"
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
  // op 必须活到操作完成；这里省略了等待
}
```

`schedule(sch)` 产生一个**发送器**（sender），它描述一段尚未开始的工作；`then` 把它包装成另一个发送器。到这里为止什么都没有运行。`connect` 把发送器和接收器结合成**操作状态**（operation state），`start` 才真正启动。

### 惰性：避免析构时的两难

P0443 的执行器是急切的，提交即开始。P2300 选择了纯惰性的模型，理由之一是析构函数（§4.10）：如果一个已经开始运行的急切操作被丢弃，只能把这种情况定为未定义行为，或者在析构函数里阻塞等待，两者都不令人满意。所以 [[exec.adapt]] 规定，发送器适配器在 `connect` 和 `start` 之前不得产生可观察效果。

### connect 与 start：不分配内存

最初的发送器只有一个基本操作 `submit(sndr, rcvr)`，它和急切的 `execute` 一样需要把状态放在堆上。[[P2006R1]] 把它拆成两步：`connect` 返回一个不可移动的操作状态对象，由调用者决定放在哪里（通常在栈上，或嵌在外层操作的状态里）；`start` 再启动工作。

这就是 [[exec.connect]] 和 [[exec.opstate]] 的来源。代价是生存期交给了调用者：上例最后一行的注释说的正是这件事，[[exec.async.ops]] 和 [[exec.scope]] 用大量篇幅规定操作状态必须活到何时。

### 完成签名：事先知道结果的类型

每个发送器都要声明自己会以哪些类型完成，这就是[[g:completion-signature|完成签名]]（[[exec.cmplsig]]）。理由是高效地处理结果需要事先知道类型：`when_all` 要在操作状态里为每个子操作的结果预留存储，`sync_wait` 要知道返回什么样的 `optional<tuple<...>>`。

完成签名还可以依赖接收器提供的环境，所以 [[exec.snd]] 里的概念写作 `sender_in<Sndr, Env>`。C++26 定稿前，计算方式又改成了无实参的 `consteval` 函数模板 `get_completion_signatures<Sndr, Env...>()`，类型错误通过常量求值中抛出的异常报告（[[P3557R3]]、[[exec.getcomplsigs]]）。

### 取消：环境里的停止令牌

取消的方案来自 [[P2175R0]]：接收器通过环境提供一个停止令牌，发送器需要时查询它，发现停止请求后调用 `set_stopped`。这复用了 C++20 的 `std::stop_token` 一族（[[thread.stoptoken]]），P2300 又加了不分配内存的 `inplace_stop_token`。见 [[exec.get.stop.token]]。

## 并入前后的修改

P2300 从发表到 C++26 定稿又改了许多次。下面几处修改在今天的条文里留下了明显的痕迹。

**定制用成员函数。** 早期修订用 `tag_invoke` 实现定制点，后来按 [[P2855R1]] 改用成员函数。所以今天 `ex::set_value(rcvr, v)` 等价于调用 `rcvr.set_value(v)`，上面的接收器直接写成员函数即可。

**删除无人等待的算法。** `ensure_started` 和 `start_detached` 启动的工作没有人负责等待它结束，可能比它引用的对象活得更久（[[P3187R1]]）。它们被删除了，替代品是 async scope（[[P3149R11]]）：急切启动的工作必须用 `spawn` 关联到某个 scope，scope 在结束前等待所有工作完成。规则见 [[exec.scope]]、[[exec.spawn]]。

**标准线程池。** P2300 按库演进组的方向不包含线程池。后来的 [[P2079R10]] 补上了 `parallel_scheduler`，并允许替换它的后端（[[exec.par.scheduler]]、[[exec.parschedrepl]]）。

**算法定制与 domain。** GPU 这类执行资源需要把 `then`、`bulk` 等算法换成专门的实现，这通过 domain 选择（[[P2999R3]]）。一个难点是，`just()` 这样的发送器在知道自己从哪里启动之前，无法知道自己在哪个 domain 上完成，于是 `starts_on(gpu, just())` 之后的 `then` 可能选中 CPU 的实现。C++26 定稿前的 [[P3826R5]] 改为在查询完成 domain 时传入接收器的环境，引入了 `get_completion_domain` 和 `indeterminate_domain`（[[exec.get.compl.domain]]、[[exec.domain.indeterminate]]、[[exec.snd.transform]]）。

**与协程的桥梁。** 任何可等待类型自动是发送器；`as_awaitable` 让协程可以 `co_await` 一个发送器（[[exec.as.awaitable]]）。C++20 只有协程的语言机制，没有任何协程类型；C++26 通过 [[P3552R3]] 加入了 `std::execution::task`，[[P3941R4]] 又规定了 `task` 怎样回到启动它的调度器（[[exec.affine]]、[[exec.task]]）。

```cpp title="依据当前草案；本机 libc++ 尚未提供，不标判定"
#include <execution>
namespace ex = std::execution;

ex::task<int> compute(ex::scheduler auto sch) {
  int a = co_await (ex::schedule(sch) | ex::then([] { return 20; }));
  int b = co_await ex::just(22);
  co_return a + b;
}

int main() {
  auto sch = ex::get_parallel_scheduler();
  auto [v] = std::this_thread::sync_wait(compute(sch)).value();
  return v == 42 ? 0 : 1;
}
```

## 网络库为什么没有进来

Networking TS 在 2018 年发布，它的异步模型就是 Kohlhoff 的 Asio 模型，执行器是其中的核心。执行器换成发送器之后，网络库要不要跟着改？2021 年的两篇论文代表了两种立场。

[[P2464R0]]（Voutilainen）认为，P0443 式的执行器只是工作提交者，无法得知提交的工作是否成功、是否出错。Networking TS 假定执行器在提交和调用延续之间不会失败，但一个标准化的执行器抽象会有大量网络库之外的实现，不受这个假定约束。它建议先完成发送器/接收器，再在其上建立网络库。

[[P2469R0]]（Kohlhoff 等）的立场相反：Asio 的模型经过多年生产使用，有基于完成令牌的成熟组合方式；P2300 是在某个异步模型之上组合操作的 DSL，而不是异步模型本身，它应该建立在 Asio 的模型之上。

库演进组随后的投票（[[P2453R0]]）支持以发送器/接收器作为大多数异步用例的基础，标准网络库也应以它为基础；但对是否放弃 Networking TS 没有形成共识。网络库最终没有进入 C++26。以发送器重写网络接口的提案（如 [[P2762R2]]）截至写作时仍在进行。

## [exec] 的规则从哪里来

| [exec] 中的设计 | 要解决的问题 | 对应条款 |
|---|---|---|
| 没有 `executor`，只有 `scheduler` | 单向 `execute` 无法报告错误和取消（P1525） | [[exec.sched]] |
| 接收器有三个完成函数，恰好调用一个 | 值、错误、停止各需一个通道 | [[exec.recv]]、[[exec.async.ops]] |
| `connect` 返回操作状态，`start` 才启动 | 不在堆上分配异步状态（P2006） | [[exec.connect]]、[[exec.opstate]] |
| 适配器在 `start` 前无可观察效果 | 急切操作被丢弃时析构无法处理 | [[exec.adapt]] |
| 发送器声明完成签名，可依赖环境 | 组合算法要事先预留结果的存储 | [[exec.cmplsig]]、[[exec.getcomplsigs]] |
| 取消经环境中的停止令牌传递 | 取消需要一条带内通道 | [[exec.get.stop.token]] |
| 只有环境查询，没有 require/prefer | 属性机制只保留了查询的一半 | [[exec.queryable]]、[[exec.env]] |
| 用成员函数定制 | 取代 `tag_invoke` | [[exec]] |
| 没有 `start_detached`，改用 scope | 无人等待的工作可能悬垂 | [[exec.scope]]、[[exec.spawn]] |
| domain 与 `transform_sender` | 专用执行资源替换算法实现 | [[exec.snd.transform]] |

P0443 关心而 [exec] 没有接住的问题也很清楚：并行算法仍然只能接受执行策略，不能指定调度器；标准网络库的接口尚未确定。

## 时间线

| 年份 | 事件 |
|---|---|
| 2013–2014 | Google 的执行器（[[N3562]]）；Kohlhoff 基于模板的执行器（[[N4046]]） |
| 2015 | 并行算法需要执行器（[[N4406]]）；SG1 要求统一三套设计 |
| 2016 | 并行算法与执行策略并入 C++17；统一提案 [[P0443R0]] |
| 2017 | 用属性简化 P0443（[[P0688R0]]） |
| 2018 | Networking TS 发布；发送器/接收器的雏形（[[P1194R0]]） |
| 2019 | 执行器未赶上 C++20；P0443 加入调度器与发送器 |
| 2020 | `connect`/`start` 取代 `submit`（[[P2006R1]]）；P1525R1 |
| 2021 | [[P2300R0]] 删除执行器；网络库之争 |
| 2024 | [[P2300R10]] 并入 C++26 |
| 2025–2026 | async scope、`parallel_scheduler`、`task` 并入；定稿前修订 domain |

<details class="fine" markdown="1"><summary>其余出处</summary>

文中的 HOPL IV 指 Bjarne Stroustrup，*Thriving in a Crowded and Changing World: C++ 2006–2020*（2020），§8.8.1。并入时间依据 Herb Sutter 的会议报告（herbsutter.com，2016 年 3 月、2024 年 7 月、2025 年 6 月）。

Eric Niebler 的两篇博客对理解发送器的设计动机有帮助：[Structured Concurrency](https://ericniebler.com/2020/11/08/structured-concurrency/)（2020）和 [What are Senders Good For, Anyway?](https://ericniebler.com/2024/02/04/what-are-senders-good-for-anyway/)（2024）。

围绕 2021 年争论的不同看法至今仍在，2026 年还有若干信息论文重新回顾这段历史（如 [[P4094R1]]、[[P4099R1]]）。这些文档代表作者本人的观点。
</details>
