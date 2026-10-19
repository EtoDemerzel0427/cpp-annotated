---
title: 协程：从 Simula 到 C++20/26
summary: C++20 为什么选择无栈协程、为什么关键字带 co_ 前缀、为什么帧的分配只是"可能需要"，以及标准库的协程类型为什么到 C++23、C++26 才出现。
status: draft
order: 40
since: c++20
papers: N3328, N3708, N4134, P0071R0, P0973R0, P0981R0, P0913R1, P1063R0, P1342R0, P1492R0, P0912R5, P2502R2, P3552R3
related: topics/coroutines, dcl.fct.def.coroutine, expr.await, expr.yield, stmt.return.coroutine, support.coroutine, coroutine.handle, coro.generator, exec.task
tags: 协程, 沿革, Coroutines TS, co_await
updated: 2026-10-19
---

!!! tldr
    - C++20 协程是无栈的：挂起时只保存协程自己的那一帧。语言只规定怎样把函数体改写成状态机，返回类型完全交给库。
    - 有栈协程（独立的栈，可以在任意深的调用里挂起）和无栈协程在委员会里竞争了多年，最后性能论据胜出。
    - 关键字叫 `co_await`、`co_yield`、`co_return`，是因为 `yield` 在现有代码里是太常见的名字；协程里因此也不能写 `return`。
    - 标准只说实现可能需要为帧分配存储：能否省掉分配交给优化器，这是 2018 年与 Core Coroutines 之争的结论。
    - C++20 没有提供任何现成的协程类型；`std::generator` 到 C++23 才有，异步用的 `std::execution::task` 到 C++26 才有。

阅读本页前最好已经知道协程的三个角色（[[g:promise-type|promise 类型]]、awaiter、`coroutine_handle`）各管什么，可以先看 [[topics/coroutines]]。

## 协程是什么，早年的 C++ 为什么没有

普通函数总是从头进入、从尾退出。**协程**（coroutine）可以在中途让出控制，下次从让出的地方继续。这个词出自 Melvin Conway（1963 年的论文 *Design of a Separable Transition-Diagram Compiler*），他用它让编译器的词法分析和语法分析交替运行：一方产出一个单词，另一方立刻消费，不必先把中间结果全部写出来。Simula 67 把它做成了语言机制，对象可以 `detach` 交出控制，之后再被 `resume`。

C++ 一开始就有协程，不过是以库的形式。C with Classes 最早的重要库就是一个支持协程风格编程的 task 库，它在当时的硬件上很高效。但它靠底层的栈切换实现，难以移植到 SPARC 等新架构，1989 年之后多数实现不再提供它（HOPL IV §1.1）。C++98 因此没有协程。

这段早期历史已经包含了后来争论的两个核心问题：协程是库还是语言特性，以及挂起时要不要切换整个栈。

## 标准之外的两类技巧

C++98 到 C++17 之间，需要协程的程序员只能用语言之外的技巧。它们恰好对应后来委员会里的两条路线。

### 无栈：用 switch 跳回上次的位置

`switch` 的 `case` 标号可以出现在循环体内部（Duff's device 用的也是这一点）。把恢复位置记在一个状态变量里，每次调用用 `switch` 跳回去，就得到一个简陋的协程。Simon Tatham 的文章 *Coroutines in C* 把它包装成了宏，Boost.Asio 的 `asio::coroutine`（空间开销只有一个 `int`）也是这样实现的。下面是去掉宏之后的样子：

```cpp run title="switch_coroutine.cpp" ok
#include <cstdio>

// 用 switch 跳回上次返回的位置，状态存在对象里
struct Counter {
    int state = 0;
    int i = 0;
    // 每次调用产出下一个值；耗尽后返回 -1
    int next() {
        switch (state) {
        case 0:
            for (i = 0; i < 3; ++i) {
                state = 1;
                return i;          // 相当于 yield i
        case 1:;                   // 下次调用从这里继续
            }
        }
        state = 2;
        return -1;
    }
};

int main() {
    Counter c;
    for (int v; (v = c.next()) != -1;)
        std::printf("%d\n", v);    // 0 1 2
}
```

这已经是无栈协程的全部要素：跨越挂起点还要用的变量（`i`）必须放在对象里而不是栈上；挂起就是记下位置然后返回；恢复就是再调用一次、跳回记下的位置。区别在于这里的状态对象要手写，局部变量也不能随便声明（`switch` 不能跳过带初始化的声明）。C++20 让编译器生成这个对象，它就是[[g:coroutine-state|协程帧]]。

### 有栈：切换整个栈

另一类技巧给每个协程分配独立的栈，挂起时保存寄存器、切换栈指针。这就是**有栈**（stackful）协程，也常叫 fiber。它的好处是可以在任意深的嵌套调用里挂起，被调用的函数不需要知道自己运行在协程中；代价是每个协程都要预留一块栈，切换依赖平台相关的汇编代码。Boost.Context 和 Boost.Coroutine（2012–2013 年加入 Boost，后来又有 Coroutine2）是这条路线的代表：

```cpp
// Boost.Coroutine2 的有栈协程（示意，需要 Boost，未加判定）
using coro_t = boost::coroutines2::coroutine<int>;

coro_t::pull_type fib([](coro_t::push_type& sink) {
    int a = 0, b = 1;
    for (int i = 0; i < 8; ++i) {
        sink(a);                 // 挂起，把 a 交给消费者
        int next = a + b;
        a = b;
        b = next;
    }
});

for (int v : fib) std::cout << v << ' ';
```

注意 `sink(a)` 是一次普通的函数调用。它可以出现在 lambda 调用的任何深度的函数里，这是无栈协程做不到的。

## 两条路线进入委员会（2012–2014）

### 无栈的语言特性与有栈的库

两条路线几乎同时提交给了委员会。Microsoft 的 [[N3328]]（2012）提出 resumable functions：函数标上 `resumable`，在里面用 `await` 等待一个 future，把回调链写回顺序代码，相当于 C# 当时正在引入的 async/await。Kowalke 与 Goodspeed 的 [[N3708]]（2013）则提议把 Boost.Coroutine 作为标准库加入，不需要任何语言改动。

<div class="compare" markdown="1">

```cpp
// N3328（2012），未进入标准
future<int> f(stream str) resumable
{
    shared_ptr<char> buf = ...;
    int n = await str.read(512, buf);
    return n + 11;
}
```

```cpp
// C++20 的写法
task<int> f(stream str)
{
    shared_ptr<char> buf = ...;
    int n = co_await str.read(512, buf);
    co_return n + 11;
}
```

</div>

两者的差别可以概括为：await 设计是无栈的、基于语言的；Boost 设计是有栈的、基于库的。无栈协程只能在自己的函数体里挂起，不能在它调用的函数里挂起，所以挂起时只保存一帧。Stroustrup 认为，这在性能上是巨大的优势（HOPL IV §9.3.2）。

### 统一的尝试与性能论据

委员会的并发研究组要求两方放进同一个概念框架（[[N4232]] 记录了这次讨论）。此后几年反复出现三种思路（HOPL IV §9.3.2）：

1. 把协程表示成一种 lambda，让它自然地进入类型系统，不需要编译器在背后做太多事（如 [[N4244]] *Resumable Lambdas*）；
2. 给有栈协程、无栈协程乃至线程提供一个公共接口；
3. 为生成器、管道这类最简单、最常用的场景争取最优性能，这要求无栈协程有编译器支持，接口也不为照顾高级用法而妥协。

三者不可兼得。Stroustrup 本人偏爱公共接口，但最终性能论据胜出（HOPL IV §9.3.2）。

### 从标注到函数体决定

2014 年，Gor Nishanov 接手 Microsoft 的提案，写成 [[N4134]] *Resumable Functions v.2*。它明确选择无栈实现，引入了 promise 和 `coroutine_traits` 的模型，并去掉了 `resumable` 标注：一个函数是不是协程，只看函数体里有没有挂起点。

今天的 [[dcl.fct.def.coroutine#1]] 仍是这样定义的：函数体里出现 `co_await`、`co_yield` 或 `co_return`，它就是协程，声明上看不出来。调用者也不需要知道，因为协程和普通函数一样，返回一个普通类型的对象。

## 关键字为什么带 co_ 前缀

N4134 用的是 `await` 和 `yield`。可是把 `yield` 变成关键字会破坏大量代码：它在金融（收益率）、农业（产量）领域是常见的变量名和函数名。EWG 对此的回答是坚决不行（[[P0071R0]]）。

候选方案有好几种：软关键字（只在特定上下文里是关键字）、写成 `std` 中的函数、换一个生僻的词、加前缀。最后委员会选了 `co_` 前缀，三个关键字都换掉，包括 `return`。HOPL IV 解释，协程的结果要包装进调用者可以等待的对象（比如 future），`return` 在协程里的含义与普通函数不同，所以也要换一个词。

这个决定在今天的规则里留下了两个痕迹。第一，`yield` 和 `await` 至今是普通标识符，而 `co_await` 等从 C++20 起是关键字（[[lex.key]]，[[diff.cpp17.lex]] 记录了这一不兼容）：

<div class="compare" markdown="1">

```cpp run ok
double yield = 0.035;  // 收益率
int await(int x) { return x; }
int main() {
    return await(int(yield));
}
```

```cpp error
// C++17 合法，C++20 起不合法
int co_await = 0;  // error: 关键字
```

</div>

第二，协程里不能出现 `return` 语句（[[stmt.return.coroutine#1]]），即使它在一个被丢弃的 `if constexpr` 分支里。普通函数用 `return`，协程用 `co_return`，同一个函数体不能混用。

## 帧放在哪里：TS 与 Core Coroutines 之争

### 先做成技术规范

2016 年，委员会决定协程先以技术规范（TS，一种不进入正式标准、供实现试用的文档）的形式发布，2017 年出版为 Coroutines TS。之所以不直接进标准，一方面是许多人仍偏爱更通用的有栈协程，另一方面是有人希望找到兼顾两者的方案（HOPL IV §6.3）。到 2018 年，MSVC 和 Clang 都有了 TS 的实现。

### Google 的异议

2018 年，TS 准备并入 C++20 时，Google 的作者在评估是否在内部采用后提出了一系列问题（[[P0973R0]]）。其中最重要的是：帧通常要在堆上分配，这违反零开销原则；以 `const&` 传入的参数在挂起后可能悬垂；不能写 `return` 增加了迁移成本；`co_await` 这个名字偏向异步这一种用途。

他们特别关心一个 TS 作者较少讨论的场景：在禁用异常的环境里，用协程传播 `expected<T>` 一类返回值中的错误，代替宏。对这种用途，每次调用都可能发生的堆分配是不能接受的。

### 两种答案

TS 一方的回答是 HALO（Heap Allocation eLision Optimization，[[P0981R0]]）：在关键场景中，优化器能证明帧的生命周期不超出调用者，于是把它分配到调用者的帧里，堆分配就消失了。

Google 一方则提出了另一个设计 Core Coroutines（[[P1063R0]]）：把协程帧作为一个普通对象暴露出来，像 lambda 的闭包对象一样有类型、有 `sizeof`，调用者自己决定把它放在哪里，从类型系统上保证不分配。它还用一个运算符式的记号代替 `co_await`：

```cpp
// P1063R0（2018）提议的解包运算符，从未进入标准，未加判定
optional<string> f();
string s = [<-] f();
```

### 为什么 TS 赢了

关键在于帧的大小何时可知。协程帧本质上是一个栈帧，里面装着跨越挂起点存活的局部变量和临时量。它的大小要到优化器运行之后才确定：优化器可能删掉变量让它变小，也可能加入临时量让它变大（[[P1492R0]]、[[P1342R0]]）。

| | Core Coroutines（早拆分） | Coroutines TS（晚拆分） |
|---|---|---|
| 帧是什么 | 用户可见的类型，有 `sizeof` | 编译器私有，用 `coroutine_handle` 间接访问 |
| 帧的大小 | 前端在优化前就要确定，只能保守估计 | 优化后再计算，通常更小 |
| 不分配的保证 | 类型系统保证 | 没有保证，靠优化器 |
| 对编译器的影响 | 前端需要知道优化之后才有的信息 | 与现有编译器结构一致 |

所有主流优化编译器都依赖一个前提：函数的活动记录是实现私有的。让它成为一个早期就确定大小的完整类型，就得把优化器的信息倒流回前端，现有编译器做不到（[[P1492R0]]）。此外，三份竞争的提案都是无栈的，写法差别不大，而 TS 已有多年的生产使用和两个编译器的实现。2019 年 2 月，TS 基本原样并入 C++20（[[P0912R5]]），TS 里的 `for co_await` 循环没有并入。

## 今天的规则里留下了什么

| 今天的规则 | 来自哪个决定 | 条款 |
|---|---|---|
| 是否为协程只看函数体，声明上没有标记 | N4134 去掉 `resumable` | [[dcl.fct.def.coroutine#1]] |
| 关键字带 `co_` 前缀，`yield`、`await` 仍是普通标识符 | 不破坏把 `yield` 当名字的代码 | [[lex.key]] |
| 协程中不得出现 `return` | 协程的 return 语义不同 | [[stmt.return.coroutine#1]] |
| 帧的存储"可能需要"分配，分配函数先在 promise 类型中查找 | TS 的编译器私有帧 + HALO | [[dcl.fct.def.coroutine#9]] |
| 分配函数可以看到协程的参数 | 参数预览（[[P0914R1]]） | [[dcl.fct.def.coroutine#9]] |
| `await_suspend` 可以返回 `coroutine_handle` | 对称转移（[[P0913R1]]） | [[expr.await#5]] |
| 范围 `for` 没有 `co_await` 形式 | 合并时排除 | [[stmt.ranged]] |
| 协程不能是 constexpr 函数 | TS 不支持，至今未放开 | [[dcl.constexpr#3]] |

### 分配：may 而不是 shall

[[dcl.fct.def.coroutine#9]] 说实现可能需要（may need to）为协程分配额外的存储。这个 may 给了 HALO 省略分配的余地，但条文从不保证省略一定发生。P0973R0 指出的那一点在今天仍然成立：程序员无法在语言层面确认某次调用不分配。

作为补偿，条文给了库作者控制分配的手段：分配函数先在 promise 类型的作用域中查找，并且会先尝试把协程的参数一并传给它（第 9.1 项），这样调用者可以通过参数传入分配器；promise 类型如果提供 `get_return_object_on_allocation_failure`，分配就改用不抛异常的形式（[[dcl.fct.def.coroutine#10]]）。

### 对称转移

一个协程恢复另一个协程，最初只能在 `await_suspend` 里调用 `resume()`。每次这样做，调用链都在线程栈上加深一层，大量同步完成的 `co_await` 可能导致栈溢出。[[P0913R1]] 允许 `await_suspend` 返回一个 `coroutine_handle`，由实现去恢复它（[[expr.await#5]] 第 5.1.1 项）。实现可以把这一步做成尾调用，栈不再增长。

下面的最小 task 类型同时演示了这两点：promise 接管帧的分配，`final_suspend` 用对称转移把控制直接交回等待者。

```cpp run title="task_halo.cpp" ok
#include <coroutine>
#include <cstddef>
#include <cstdio>
#include <exception>
#include <new>
#include <utility>

struct task {
    struct promise_type {
        int value = 0;
        std::coroutine_handle<> continuation = std::noop_coroutine();

        // 帧的分配由 promise 接管（[dcl.fct.def.coroutine]/9）
        static void* operator new(std::size_t n) {
            std::printf("allocate frame: %zu bytes\n", n);
            return ::operator new(n);
        }
        static void operator delete(void* p, std::size_t n) {
            ::operator delete(p, n);
        }

        task get_return_object() {
            return task{std::coroutine_handle<promise_type>::from_promise(*this)};
        }
        std::suspend_always initial_suspend() noexcept { return {}; }  // 惰性启动
        auto final_suspend() noexcept {
            struct awaiter {
                bool await_ready() noexcept { return false; }
                // 对称转移：返回下一个要恢复的协程（[expr.await]/5.1.1）
                std::coroutine_handle<> await_suspend(
                    std::coroutine_handle<promise_type> h) noexcept {
                    return h.promise().continuation;
                }
                void await_resume() noexcept {}
            };
            return awaiter{};
        }
        void return_value(int v) { value = v; }
        void unhandled_exception() { std::terminate(); }
    };

    // task 自身也是可等待体：被 co_await 时记录续体并转去执行
    bool await_ready() const noexcept { return false; }
    std::coroutine_handle<> await_suspend(std::coroutine_handle<> caller) noexcept {
        h.promise().continuation = caller;
        return h;
    }
    int await_resume() { return h.promise().value; }

    explicit task(std::coroutine_handle<promise_type> h) : h(h) {}
    task(task&& o) noexcept : h(std::exchange(o.h, {})) {}
    ~task() { if (h) h.destroy(); }

    std::coroutine_handle<promise_type> h;
};

task answer() { co_return 42; }

task twice() {
    int x = co_await answer();
    co_return 2 * x;
}

int main() {
    task t = twice();
    t.h.resume();                                 // 启动外层协程
    std::printf("%d\n", t.h.promise().value);     // 84
}
```

!!! impl "HALO 的一次观察"
    本机 Clang 23 用 `-O0` 编译这个程序时打印两行 `allocate frame`（64 和 40 字节），用 `-O2` 编译时只打印一行：内层 `answer()` 的帧被并入了外层的帧，分配被省略了。帧的大小和是否省略都取决于实现和优化级别，标准不作保证，这正是 2018 年争论的焦点。

## 库来得很晚

C++20 只提供了 `<coroutine>` 里的底层设施（[[support.coroutine]]）：`coroutine_traits`、`coroutine_handle`、`noop_coroutine`、`suspend_always`、`suspend_never`。没有任何可以直接当返回类型用的协程类型，原因是来不及在 C++20 准备好（HOPL IV §9.3）。上面那几十行 `task`，C++20 的用户都得自己写，或者用 cppcoro、Folly 等第三方库。

这是 TS 设计取向的直接后果：语言只规定改写协议，返回类型交给库；而库的设计，尤其是调度、取消、分配器，需要另外的共识。

### C++23：std::generator

生成器先落地。[[P2502R2]] 的 `std::generator`（[[coro.generator]]）进入 C++23，它同时是一个范围视图，可以直接接范围适配器，还能用 `co_yield std::ranges::elements_of(...)` 递归地产出另一个生成器的元素。

```cpp run title="generator.cpp"
#include <generator>
#include <iostream>

std::generator<int> fibonacci() {
    int a = 0, b = 1;
    while (true) {
        co_yield a;
        int next = a + b;
        a = b;
        b = next;
    }
}

int main() {
    int n = 0;
    for (int v : fibonacci()) {
        if (++n > 8) break;
        std::cout << v << ' ';     // 0 1 1 2 3 5 8 13
    }
    std::cout << '\n';
}
```

本机 libc++ 还没有 `<generator>` 头文件，这个例子按标准编写，未经本地编译，因此不标判定。

### C++26：std::execution::task

异步用的 task 类型到 C++26 才有，并且绑定在 `std::execution` 的发送器/接收器模型上（[[P3552R3]]，[[exec.task]]）。它通过时仍有不少反对意见（[[P3801R0]]），包括迭代式代码可能栈溢出、参数生命周期出人意料等，和 2018 年 P0973R0 提出的问题一脉相承。

从 2012 年的 N3328 算起，异步协程用了十多年才在标准库中有第一个现成的返回类型。

## 仍在进行中的工作

2019 年以前反复出现的几个问题，在今天的提案里仍能找到：

- **有栈协程。** Kowalke 和 Goodspeed 的路线演化为 [[P0876R24]] *fiber_context*，提出一个不带调度器的最小栈切换 API，作为有栈协程和用户态线程的构件，目前仍在审查中。
- **constexpr 协程。** [[P3367R5]] 提议允许协程在常量求值中运行，因实现成本的顾虑，目标已从 C++26 改为 C++29。当前草案仍规定协程不是 constexpr-suitable 的函数（[[dcl.constexpr#3]]）。
- **帧分配。** 帧的分配不考虑 `std::align_val_t`，过对齐的帧可能对齐不正确；[[P2014R2]] 给出了修正方案，当前草案尚未采纳。[[P2477R3]] 提议让程序员显式控制 HALO，延续了 Core Coroutines 的关注点。
- **promise 协议的放宽。** C++20 规定 promise 类型不能同时有 `return_void` 和 `return_value`。[[P3950R0]] 取消了这一限制（据 [[P4282R1]]，该提案已被采纳），当前草案改为看 `p.return_void()` 的重载决议能否成功，来决定流出函数体末尾时的行为（[[stmt.return.coroutine#3]]）。

## 时间线

| 时间 | 事件 |
|---|---|
| 1963 | Conway 发表协程论文；1967 年 Simula 67 以 `detach`/`resume` 支持协程 |
| 1980 年代 | C with Classes 的 task 库；1989 年后因移植困难被多数实现放弃 |
| 2000–2013 | 标准之外：`switch` 宏技巧、Asio 无栈协程、Boost.Coroutine 有栈协程 |
| 2012–2013 | 无栈语言特性（[[N3328]]）与有栈库（[[N3708]]）两份提案 |
| 2014 | [[N4134]]：选择无栈，去掉 `resumable` 标注 |
| 2015 | 关键字定为 `co_await`、`co_yield`、`co_return`（[[P0071R0]]） |
| 2017 | Coroutines TS 出版 |
| 2018 | Google 的异议（[[P0973R0]]）、HALO（[[P0981R0]]）、Core Coroutines（[[P1063R0]]）；对称转移并入 TS |
| 2019-02 | TS 并入 C++20（[[P0912R5]]） |
| 2022 | `std::generator` 进入 C++23（[[P2502R2]]） |
| 2025 | `std::execution::task` 进入 C++26（[[P3552R3]]） |

## 参考资料

- Bjarne Stroustrup, *Thriving in a Crowded and Changing World: C++ 2006–2020*, HOPL IV (2020)：§1.1（task 库）、§6.3（TS 决定）、§9.3.2（协程）。
- Melvin E. Conway, *Design of a Separable Transition-Diagram Compiler*, CACM 6(7), 1963；Knuth, *The Art of Computer Programming* Vol. 1, §1.4.2。
- Simon Tatham, [*Coroutines in C*](https://www.chiark.greenend.org.uk/~sgtatham/coroutines.html)；Boost.Asio 文档，[`coroutine` 类](https://www.boost.org/doc/libs/1_86_0/doc/html/boost_asio/reference/coroutine.html)。
- 两条路线：[[N3328]]、[[N3708]]、[[N4232]]、[[N4134]]。
- 关键字：[[P0071R0]] *Coroutines: Keyword alternatives*。
- C++20 前的争论：[[P0973R0]]、[[P0981R0]]、[[P1063R0]]、[[P1342R0]]、[[P1492R0]]、[[P1493R0]]、[[P0912R5]]。
- Botond Ballo 关于 2018 年 Jacksonville、Rapperswil、San Diego 与 2019 年 Kona 会议的 trip report（botondballo.wordpress.com）。
- Lewis Baker, [*C++ Coroutines: Understanding operator co_await*](https://lewissbaker.github.io/2017/11/17/understanding-operator-co-await) 及同系列文章，是理解这套协议最常被引用的资料之一。
- 标准库：[[P2502R2]]、[[P3552R3]]、[[P3801R0]]。
