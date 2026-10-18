---
title: 协程：从 Simula 到 C++20/26
summary: 协程在 C++ 里走过的路：早期 task 库被放弃，标准之外的宏技巧与 Boost 有栈协程，Microsoft 的 resumable functions 与有栈库提案之争，co_ 关键字的由来，Coroutines TS，C++20 前夕 Core Coroutines 与 TS 的对决，以及 C++23 的 std::generator 和 C++26 的 std::execution::task
status: draft
order: 40
since: c++20
papers: N3328, N3708, N4134, P0057R8, P0912R5, P1063R2, P1342R0, P1492R0, P1493R0, P2502R2, P3552R3
related: topics/coroutines, dcl.fct.def.coroutine, expr.await, expr.yield, support.coroutine, coroutine.handle, coro.generator, exec.task, exec.as.awaitable
tags: 协程, 沿革, Coroutines TS, co_await, 委员会
updated: 2026-10-18
---

C++20 协程的规则读起来有几处不太自然。为什么关键字是 `co_await`、`co_yield`、`co_return`，而不是其他语言里常见的 `await`、`yield`？为什么协程里不能写 `return`？为什么 [[dcl.fct.def.coroutine]] ¶9 说实现"可能需要"（may need to）为协程分配存储，而不是"必须"分配？为什么一个最简单的生成器也要先写几十行 promise 类型，标准库却直到 C++23 才给出 `std::generator`？

这些问题的答案大多不在条文里，而在 2012 年到 2019 年之间的提案和会议记录里。C++20 的协程是一个**无栈**（stackless）协程设计：挂起时只保存协程自己的那一帧，语言只规定一套把函数体改写成状态机的协议，具体的返回类型全部交给库。这个方向经过了与有栈协程库的竞争、关键字的反复、一份技术规范（TS）、以及 C++20 冻结前三次失败的合并投票才最终确定。本页按时间顺序讲这段历史，并在最后说明今天的哪些规则直接来自当年的哪个决定。

阅读前最好已经知道协程的三个角色（promise、awaiter、`coroutine_handle`）各管什么，可以先看 [[topics/coroutines]]。规则本身分布在 [[dcl.fct.def.coroutine]]、[[expr.await]]、[[expr.yield]]、[[stmt.return.coroutine]] 和 [[support.coroutine]] 中。

## 一个比 C++ 更早的想法

### Conway、Knuth 与 Simula

协程（coroutine）这个词出自 Melvin Conway。据 Knuth 在《计算机程序设计艺术》第 1 卷的历史注记，Conway 在 1958 年提出这个词，用于构造汇编程序；第一篇公开发表的论述是他 1963 年的论文 *Design of a Separable Transition-Diagram Compiler*（*Communications of the ACM* 6(7)）。Conway 的出发点是编译器的分遍：词法分析和语法分析如果写成两个互相调用的例程，就不必先把整个中间结果写到磁带上，而是一方产出一个单词、另一方立刻消费。Knuth 在同一卷 §1.4.2 把协程作为子程序的推广来讲：子程序总是从头进入、从尾退出，协程则可以在中途让出控制，下次从让出的地方继续。

Simula 67 把这个想法做成了语言机制。一个 Simula 对象可以用 `detach` 把控制交回给创建者，之后再被 `resume`，这是 Simula 做离散事件模拟的基础（见 Dahl、Myhrhaug、Nygaard 的 *SIMULA 67 Common Base Language*）。Stroustrup 在 HOPL III 中回忆，C with Classes 的基础是他在剑桥读博士（研究分布式系统）期间使用 BCPL 和 Simula 的经验；他希望新工具具有 Simula 组织程序的能力，包括某种形式的并发支持。

### 早期 C++ 的 task 库

C with Classes 的第一个重要的库就是协程库。Stroustrup 在 HOPL III 论文中回忆，最早的关键 C++ 库叫作 task system，"supported a coroutine style of programming"，在早期项目中对 C with Classes 的实用性至关重要。这个库的文档是 *A Set of C++ Classes for Co-routine Style Programming*，1985 年随 cfront 发布，据 HOPL IV 的参考文献注明，它最初在 1980 年于贝尔实验室内部发表。

HOPL IV（§1.1）解释了它后来为什么消失：task 库在当时的硬件上效率很高，Stroustrup 曾在 256KB 内存里跑 700 个任务的模拟；但它的实现依赖底层的栈切换，不容易移植到 Sun 的 SPARC 架构，因此 1989 年之后的大多数实现都不再支持它。C++98 没有协程。Stroustrup 在 HOPL IV 中的评价是："In 2020, coroutines are only just coming back."

值得注意的是，task 库是一个库，而不是语言特性。HOPL IV 说明，早期 C++ 的协程受 Simula 启发，却有意以库的形式提供，以便给多种表达并发的方式留下空间。三十年后，协程以语言特性的形式回到 C++，这个选择本身就是后面争论的核心之一。

## 标准之外的三十年

C++98 到 C++17 之间，需要协程的程序员只能靠语言之外的技巧。这些技巧大致分成两类，正好对应后来委员会里的两条路线。

### 用 switch 模拟：无栈的雏形

第一类技巧利用 `switch` 语句可以跳进循环体内部的特性（与 Duff's device 是同一个语法事实）。Simon Tatham 在 2000 年前后的文章 *Coroutines in C* 中给出了一组宏 `crBegin`、`crReturn`、`crFinish`：把恢复位置记在一个状态变量里，函数每次被调用时用 `switch` 跳回上次返回的地方。他提到 PuTTY 的 SSH 协议代码就用了这种写法。Adam Dunkels 等人的 protothreads（SenSys 2006 论文 *Protothreads: Simplifying Event-Driven Programming of Memory-Constrained Embedded Systems*）把同样的思路用于内存极小的嵌入式系统，每个 protothread 只占两个字节。

下面是这种技巧的 C++ 版本。它是完全合法的 C++，今天仍然可以编译：

```cpp run title="switch_coroutine.cpp" ok
#include <cstdio>

// Tatham 式写法：用 switch 跳回上次返回的位置，状态存在对象里
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

这个例子已经包含了 C++20 无栈协程的全部要素：跨越挂起点存活的变量（`i`）必须放在一个对象里而不是栈上，挂起只是记下位置然后返回，恢复就是再调用一次、跳到记下的位置。区别在于，这里的状态对象要程序员手写，局部变量也不能随便声明（`switch` 跳过初始化会出错）；C++20 让编译器替你生成这个对象，也就是协程帧（[[g:coroutine-state]]）。

Christopher Kohlhoff 把这种技巧带进了 Asio。Boost 1.42（2010 年 2 月）的 Asio 新增了一个示例 HTTP Server 4，演示用宏实现的无栈协程；Boost 1.54（2013 年 7 月）的发布说明称，这个 `coroutine` 类和相关的宏从示例提升为 Asio 正式文档化的接口。按 Boost 文档，`asio::coroutine` 的空间开销只有一个 `int`，伪关键字 `reenter`、`yield`、`fork` 都是宏，`reenter` 用 `switch` 实现。下面是这种风格的示意（需要 Boost.Asio，未加判定）：

```cpp
// 历史写法：Asio 的无栈协程宏（<boost/asio/yield.hpp>），示意，未加判定
struct echo_session : boost::asio::coroutine {
    void operator()(boost::system::error_code ec = {}, std::size_t n = 0) {
        reenter (this) {
            for (;;) {
                yield socket_->async_read_some(boost::asio::buffer(*buf_), *this);
                yield boost::asio::async_write(*socket_, boost::asio::buffer(*buf_, n), *this);
            }
        }
    }
    std::shared_ptr<tcp::socket> socket_;
    std::shared_ptr<std::array<char, 1024>> buf_;
};
```

### 切换整个栈：Boost.Context 与 Boost.Coroutine

第二类技巧给每个协程分配一个独立的栈，挂起时用几条汇编指令保存寄存器、切换栈指针。这就是**有栈**（stackful）协程，也常叫 fiber。它的好处是协程可以在任意深的嵌套调用里挂起，被调用的函数不需要知道自己运行在协程中；代价是每个协程都要预留一块栈内存，并且切换依赖平台相关的代码。

Oliver Kowalke 把这条路线做成了 Boost 库：

- Boost 1.51（2012 年 8 月）加入 Boost.Context，提供底层的执行上下文切换；
- Boost 1.53（2013 年 2 月）加入 Boost.Coroutine；
- Boost 1.54 的 Asio 新增 `asio::spawn()`，发布说明称它是"基于 Boost.Coroutine 库"运行有栈协程的高层包装，让异步逻辑可以写成同步的样子；
- Boost 1.59（2015 年 8 月）加入面向 C++14 的 Boost.Coroutine2，Boost 1.62（2016 年 9 月）加入 Boost.Fiber，同一版本的发布说明把 Boost.Coroutine 标为弃用、建议改用 Coroutine2。

Boost.Coroutine2 的接口与后来提交给委员会的提案一脉相承：一对 `pull_type` / `push_type`，协程函数接收一个 `push_type&` 来产出值。下面是示意（需要 Boost，未加判定）：

```cpp
// 历史写法：Boost.Coroutine2 的非对称有栈协程，示意，未加判定
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

for (int v : fib) std::cout << v << ' ';   // pull_type 提供迭代器
```

## 两条路线进入委员会（2012–2014）

### Microsoft 的 resumable functions

据 HOPL IV（§9.3.2），C++20 协程的历史从 Niklas Gustafsson（Microsoft）2012 年的提案 [[N3328]] *Resumable Functions* 开始。它的动机是异步 I/O：与 [[N3327]] 中带 `.then()` 的 future 配合，用一个 `await` 运算符把回调链写回顺序代码。HOPL IV 指出它相当于当时 C# 正在引入的 async/await，并说"C++20 无栈协程的想法主要来自 F#"。

N3328 要求在函数上标注 `resumable`：

```cpp
// 历史写法：N3328（2012）的 resumable 函数，从未进入标准，未加判定
future<int> f(stream str) resumable
{
    shared_ptr<char> buf = ...;
    int count = await str.read(512, buf);
    return count + 11;
}
```

这一提案此后多次修订（[[N3564]]、[[N3650]]、[[N3722]]，作者加入了 Deon Brewis、Herb Sutter、Sana Mithani；以及 [[N3858]]、[[N3977]]）。

### Kowalke 与 Goodspeed 的有栈协程库

2013 年，Oliver Kowalke 和 Nat Goodspeed 提交了 [[N3708]] *A proposal to add coroutines to the C++ standard library*，基于 Boost.Coroutine，提议加入 `std::coroutine<T>::pull_type` 和 `push_type`。这份提案在开头就引用了 Conway 和 Knuth，并把有栈或无栈、对称或非对称列为协程的基本分类维度。2014 年的修订版 [[N3985]] 改名为 `asymmetric_coroutine` / `symmetric_coroutine`，同期的 [[N4024]] *Distinguishing coroutines and fibers* 区分了协程和 fiber 两个概念。

HOPL IV 这样概括两边的差异：await 设计是无栈、非对称、基于语言的；Boost 派生的设计用栈、有对称的控制原语、基于库。对无栈的定义是：协程只能在自己的函数体中挂起，不能在它调用的函数里挂起，所以挂起只需要保存一帧，而不是整个栈。HOPL IV 认为，就性能而言这是"a massive advantage"。

### 统一的尝试

两份提案在 2014 年 6 月的 Rapperswil 会议上同时出现在 SG1（并发组）。据 Nat Goodspeed 的 [[N4232]] *Stackful Coroutines and Stackless Resumable Functions*，SG1 要求作者们把两份提案放进同一个概念框架，尽可能统一。Goodspeed、Kowalke、Gustafsson 和 Torvald Riegel 在会上做了长时间讨论，Goodspeed 之后又与 Gor Nishanov 在 Redmond 继续讨论，N4232 就是这些讨论的结果。

HOPL IV 记录了随后几年里反复出现的三种思路：

1. 把协程状态和它的操作表示为一个 lambda，使协程自然地融入类型系统，不需要 await 式协程里的那些编译器魔术（Kohlhoff 的 [[N4244]] *Resumable Lambdas*、[[N4453]] *Resumable Expressions* 属于这一类）；
2. 为有栈和无栈协程，乃至线程和 fiber，提供一个公共接口（Kowalke 的 [[N4397]]、[[N4398]]，Riegel 的 [[P0073R0]]）；
3. 为生成器和管道这类最简单、最关键的用法争取最优的时间和空间性能，这要求无栈协程有编译器支持，接口也不能为照顾高级用法而妥协。

Stroustrup 在 HOPL IV 中写道，这三者不可兼得，他本人偏爱公共接口，"However, in the end the performance argument won out."

### Gor Nishanov 接手：N4134

2014 年 10 月，Gor Nishanov 和 Jim Radigan 提交了 [[N4134]] *Resumable Functions v.2*。这一版有几处决定了今天的形态：

- 去掉了 `resumable` 标注。N4134 的设计说明称，原设计依赖 `resumable` 关键字标注可恢复的函数，新提案改为依据函数体中是否出现挂起点来判断。今天 [[dcl.fct.def.coroutine]] ¶1 仍是这样定义协程的：函数体中出现 `co_return`、`co_await` 或 `co_yield`，它就是协程，声明上看不出来。
- 明确选择无栈实现。N4232 记录，N3858 同时考虑过有栈和无栈两种实现，而 N4134 的作者认为可扩展性的目标要求无栈实现。
- 引入了 promise 和 `coroutine_traits` 的概念模型，用 `await` 运算符、`yield` 语句和 `for await` 循环三种语法。
- 实现经验：Microsoft 的编译器原型。P0912R5 称，这类协程从 2014 年起就已在发布的编译器中可用。

```cpp
// 历史写法：N4134（2014）的 await / yield，从未进入标准，未加判定
generator<int> fib(int n) {
    int a = 0, b = 1;
    while (n-- > 0) {
        yield a;
        auto next = a + b;
        a = b;
        b = next;
    }
}

future<void> reader() {
    auto conn = await Tcp::Connect("127.0.0.1", 1337);
    // ...
}
```

此后的修订 [[N4286]]、[[N4402]] 和措辞草案 [[N4403]]、[[N4499]]（与 Daveed Vandevoorde 合著）逐步把这套设计写成标准措辞。

## 从 await 到 co_await（2015）

2015 年 5 月的 Lenexa 会议上，EWG 讨论了一个问题：能不能把 `yield` 这个标识符变成关键字？据 Nishanov 的 [[P0071R0]] *Coroutines: Keyword alternatives*，答案是"resounding no"。`yield` 在金融（收益率）、农业（产量）等领域的代码里是常见的变量名和函数名，把它变成关键字会破坏大量现有代码。HOPL IV 也记录了这一点。

于是 2015 年 9 月的措辞草案 [[P0057R0]] 暂时使用占位名 *await-keyword* 和 *yield-keyword*，编者注说明真正的关键字留待 Kona 会议决定。P0071R0 列出了几种候选：

- 软关键字（参见同期的 P0056R0 *Soft Keywords*），即在 `std` 命名空间中预定义、参与名字查找的特殊实体；
- 把 `await`、`yield` 做成 `std` 中的魔法函数，代价是每次都要加括号；
- 换词，例如复用已有的关键字 `export`，或者 `yield_expr` 这类在代码搜索中零命中的拼写；
- 加前缀 `co_` 或 `co`。P0071R0 指出，不带下划线的 `co` 前缀会让人误读，例如把 coyield 读成 coy-ield。

P0071R0 本身表示，如果关键字可以随意选择，作者会选 `await` 和 `yield`。最终 2015 年 11 月的 [[P0057R1]] 在关键字表中加入了 `co_await`、`co_yield` 和 `co_return`。

为什么连 `return` 也换成了 `co_return`？HOPL IV 的解释是：协程产生的结果需要包装在调用者可以等待的结构里（例如一个 future），因此协程中 return 语句的语义与普通 return 不同，一些人反对复用 `return`。EWG 因此为三个关键操作都引入了带前缀的关键字；把 `yield` 和 `await` 做成上下文相关关键字的方案也探讨过，但没有达成共识。HOPL IV 的评价是，这些关键字"aren't pretty"，后来成了反对 TS 协程的人的一个集结点。

这个决定在今天的标准里留下了两个直接后果。第一，`yield` 和 `await` 至今仍是普通标识符：

```cpp run title="identifiers.cpp" ok
// C++20 选择了 co_ 前缀，yield 和 await 仍可作普通标识符
double yield = 0.035;           // OK：金融代码中的收益率
int await(int x) { return x; }  // OK
int main() { return await(static_cast<int>(yield)); }
```

而 `co_await` 等三个词从 C++20 起是关键字（[[lex.key]]），在 C++17 中合法的同名标识符不再合法，[[diff.cpp17.lex]] 记录了这一不兼容：

```cpp error
int co_await = 0;   // error: C++20 起 co_await 是关键字
```

第二，[[stmt.return.coroutine]] ¶1 规定协程中不得出现 `return` 语句。普通函数用 `return`，协程用 `co_return`，两者不能混用。

## 进入技术规范（2015–2017）

到 2015 年底，委员会里对于协程该直接进入 C++17 还是先做成 TS 有不同意见。[[P0158R0]] *Coroutines belong in a TS*（2015 年 11 月，Jamie Allsop、Jonathan Wakely、Christopher Kohlhoff 等八人合著）主张先发布 TS。据 HOPL IV（§6.3），在 2016 年 2 月的 Jacksonville 会议上，协程被送往 TS。同一次会议也否决了把 Concepts TS 并入 C++17，HOPL IV 认为这些决定使 C++17 成了一个较小的版本。

HOPL IV 解释了为什么是 TS 而不是直接进入标准：Nishanov 的提案（被戏称为 Gor-routines）之所以获批，是因为它的实现在关键用例（管道和生成器）上表现出更好的性能；之所以只做成 TS，是因为许多人喜欢更通用但更慢的有栈协程，也有人仍希望找到兼顾两者的零开销综合方案。Stroustrup 本人认为在合理时间内不可能找到这样的综合，他引用了"The best is the enemy of the good."

TS 的工作文档依次是 [[P0057R8]]、[[N4628]]、[[N4649]]，问题清单是 [[P0664R0]] 及其后续修订。据 Herb Sutter 关于 2017 年 7 月 Toronto 会议的 trip report，委员会在这次会议上处理完投票意见，Coroutines TS 完成并送交出版（[[N4680]] 是送交出版的 TS 文本）。ISO 在 2017 年 11 月以 ISO/IEC TS 22277:2017 *C++ Extensions for Coroutines* 的编号出版。

此时已有两个公开实现。P0912R5 列出：MSVC 自 2015 版的更新（2016 年）起、Clang 自第 5 版（2017 年）起提供 TS 实现，EDG 前端在 2015 年有独立实现，GCC 的实现正在进行中。同一份文件提到 Lewis Baker 的开源库 cppcoro 使用了 TS 的大部分特性。Baker 在 2017 年起发表的系列文章（*C++ Coroutines: Understanding operator co_await* 等）后来成为理解这套协议最常被引用的资料之一。

## C++20 前夕的争论（2018–2019）

### Jacksonville 2018：合并提议与异议

2018 年 2 月，Nishanov 提交 [[P0912R0]] *Merge Coroutines TS into C++20 working draft*。同年 3 月的 Jacksonville 会议上，Google 的 Geoff Romer 和 James Dennett 提交了 [[P0973R0]] *Coroutines TS Use Cases and Design Issues*。他们在评估是否在 Google 的主代码库中采用 TS 后，列出了以下问题：

- 隐式的堆分配违反零开销原则；
- `const&` 参数在挂起后可能悬垂，很危险；
- 禁止 `return` 对用户不友好，也增加迁移成本；
- 库绑定接口庞大而不灵活；
- `co_await` 这个名字偏向异步这一种用例；
- `co_await` 嵌套使用时语法别扭；
- 不支持 `constexpr`。

P0973R0 特别强调了一个 TS 设计者较少讨论的用例：用协程传播 `expected<T>` 一类返回值中的错误，在不允许异常的环境里替代宏。对这个用例，每次调用都可能发生的堆分配是不可接受的。

Nishanov 随即发表 [[P0978R0]] 回应，Richard Smith 与 Nishanov 合写的 [[P0981R0]] *Halo: coroutine Heap Allocation eLision Optimization: the joint response* 说明，TS 协程的堆分配在绝大多数关键用例中可以被优化成栈上分配。据 Botond Ballo 关于这次会议的 trip report，EWG 给希望做重大设计修改的人一个期限：在下一次会议前提出具体方案。同一次会议上，EWG 接受了两项小改动：对称转移（[[P0913R1]] *Add symmetric coroutine control transfer*）和 promise 构造函数的参数预览（[[P0914R1]]），前者随后进入 TS 工作草案。

### Rapperswil 2018：Core Coroutines

2018 年 6 月的 Rapperswil 会议上，Romer、Dennett 和 Chandler Carruth 提交了 [[P1063R0]] *Core Coroutines*（副标题 *Making coroutines simpler, faster, and more general*）。它的核心主张是：TS 提供了一个抽象，却没有给程序员构造自己的抽象所需的原语，用来实现协程的原始对象和操作都藏在抽象边界之后。具体设计包括：

- 把协程帧作为语言中的一等对象暴露出来，类似 lambda 的闭包对象，调用者可以决定它放在哪里，从而在类型系统层面保证不发生堆分配；
- 用一个运算符式的记号 `[<-]` 代替 `co_await`，称为解包（unwrap）表达式，以避免偏向异步用例；
- 用较少的定制点代替 TS 中的一组库特质。

```cpp
// 历史写法：P1063R0（2018）提议的解包运算符，从未进入标准，未加判定
optional<string> f();
string s = [<-] f();

future<string> g();
string s2 = [<-] g();
```

P1063R0 的非目标一节明确说，它只处理无栈协程，支持委员会把有栈和无栈协程分开推进的决定。

据 Ballo 的 Rapperswil trip report，EWG 的顾虑主要在于：协程帧的类型由编译器生成，要跨翻译单元传递就得做类型擦除，很可能还要动态分配，而 TS 把这一擦除留给编译器，可以在更多场合省掉分配；对协程对象取 `sizeof` 要求前端就知道帧的大小，而 TS 只要求在优化阶段知道；此外，P1063 还依赖尾调用、惰性参数等新的语言特性。EWG 鼓励继续开发 Core Coroutines，但认为它不应阻挡 TS 合并。合并动议在全体会议上没有达成共识。

### San Diego 2018：统一方案

2018 年 11 月的 San Diego 会议前后，出现了几份试图调和两方的文件：

- [[P1241R0]] *In support of merging coroutines into C++20*（Lee Howes、Eric Niebler、Lewis Baker）；
- [[P1342R0]] *Unifying Coroutines TS and Core Coroutines*（Lewis Baker）；
- [[P1362R0]] *Incremental Approach: Coroutine TS + Core Coroutines*（Gor Nishanov）；
- [[P1329R0]] *On the Coroutines TS*（Mihail Mihaylov、Vassil Vassilev），HOPL IV 记录这是保加利亚国家成员体对 TS 设计的反对意见，两位作者之后又提出了 [[P1430R0]] *First-class symmetric coroutines in C++*。

P1342R0 把两方的取舍讲得很清楚。如果协程帧是类型系统中的一个类型，帧的大小在编译早期就已知，可以放在栈上或嵌入其他对象，保证不分配；但这个大小必须在内联、死代码消除等优化之前确定，编译器只能保守估计，帧往往偏大。如果帧由编译器做类型擦除和堆分配，大小和布局可以在优化之后才计算，帧更小，编译器还能把嵌套协程的帧内联进调用者的帧；代价是程序员无法保证某一次调用一定不分配。P1342R0 的结论是：Core Coroutines 瞄准前一组取舍，TS 瞄准后一组，理想的设计应该两者都支持，让库作者按用例选择。它建议原样合并 TS，并说明将来可以根据 `coroutine_traits` 中是否存在 `promise_type` 来选择 TS 式或 Core 式的变换，从而以不破坏兼容的方式加入 Core Coroutines 的能力。

据 Ballo 的 San Diego trip report，P1342 在会议期间才首次分发，委员会没有足够时间消化。合并动议在 EWG 以微弱多数通过，在全体会议上以微弱差距被否决。Ballo 写道，下一次会议 Kona 是 TS 并入 C++20 的最后期限。

### Kona 2019：合并

在 2019 年 2 月的 Kona 会议之前，EWG 主席 Ville Voutilainen 请三份仍在推进的提案（TS、Core Coroutines、保加利亚的对称协程）的作者合写两份评估文件（HOPL IV）：

- [[P1493R0]] *Coroutines: Use-cases and Trade-offs*（Romer、Nishanov、Baker、Mihailov）；
- [[P1492R0]] *Coroutines: Language and Implementation Impact*（Richard Smith、Vandevoorde、Romer、Nishanov、Nathan Sidwell、Iain Sandoe、Baker）。

P1492R0 用"早拆分"（early split）和"晚拆分"（late split）来描述两种实现策略的区别：协程函数在编译流水线的哪个阶段被拆成状态机。它指出，所有已知的现代优化编译器都强烈依赖活动记录对实现私有这一前提；一旦把活动记录的一部分暴露为用户可见的完整类型，语言就期望它的大小和布局在编译早期就已确定，以便给出 `sizeof` 和 `alignof`。

HOPL IV 认为，最终说服委员会的是这一点：要让表示协程状态的 lambda 与其他 lambda 一样，它的大小必须在编译的第一阶段就已知；而无栈协程的状态本质上是一个栈帧，它的大小要到优化器运行之后才知道，优化器既可能删掉变量而缩小它，也可能加入临时量而增大它，信息无法从优化器流回前端。HOPL IV 还指出，三份提案都是无栈的，都有大量定制点，关键用例的写法差别不大；TS 的优势是四年的生产使用经验，以及在 Microsoft 和 Clang 两个编译器中的实现。

据 Ballo 的 Kona trip report，EWG 用了一整天讨论设计；Baker 的 [[P1477R0]] *Coroutines TS Simplifications* 和 Kohlhoff 的 [[P1471R0]] *The trouble with coroutine_traits* 都没有被采纳，理由是不加修改的 TS 有实现经验、共识更大。合并提案 [[P0912R5]] 最终在全体会议上通过。HOPL IV 给出的票数是 48 比 4；Ballo 的描述是大约 10 比 1，并且指出此前三次会议都尝试过合并，后两次在全体会议投票中失败。Herb Sutter 的 Kona trip report 提到，其他协程提案的作者对通过的设计提出了反馈，预计将来会吸收他们的一些编程能力。

P0912R5 的合并说明列出了把 TS 文本 [[N4775]] 并入工作草案时的修改：去掉 `std::experimental`，头文件从 `<experimental/coroutine>` 改为 `<coroutine>`；不并入 TS 对 [[stmt.iter]] 和 [[stmt.ranged]] 的修改，也就是 TS 中的 `for co_await` 循环没有进入 C++20；同时并入 TS 问题清单中几个问题的解决方案，例如规定表达式 `co_await p.final_suspend()` 不得是潜在抛出的。

Stroustrup 在 HOPL IV 中对整个过程的回顾是：C++20 协程与 Gustafsson 2012 年的提案非常相似，探索替代方案是好的，但是否真的需要七年值得反思；他认为如果早期能系统地回顾设计选择、实现技术和文献，2019 年 2 月得出的结论也许在 2014 年就能得出。他也写道，没有 Nishanov 在 Microsoft 和 Clang 两个实现上的工作，就不会有 C++20 协程。

## 今天的规则里留下了什么

下表把前面讲到的决定与当前草案的条文对应起来。

| 今天的规则 | 来自哪个决定 | 条款 |
|---|---|---|
| 函数是否为协程只看函数体，声明上没有标记 | N4134 去掉 `resumable` 标注 | [[dcl.fct.def.coroutine]] ¶1 |
| 关键字是 `co_await`、`co_yield`、`co_return`；`yield`、`await` 仍是普通标识符 | 2015 年 Lenexa / Kona 的关键字讨论，P0071R0 | [[lex.key]]、[[diff.cpp17.lex]] |
| 协程中不得出现 `return` | 反对复用 `return`（HOPL IV） | [[stmt.return.coroutine]] ¶1 |
| 帧存储可能需要分配，分配函数先在 promise 类型中查找 | TS 的编译器类型擦除 + 堆分配模型，P0981R0 的 HALO 论证 | [[dcl.fct.def.coroutine]] ¶9–12 |
| 分配函数可以看到协程的参数 | 参数预览，P0914R1 | [[dcl.fct.def.coroutine]] ¶9.1 |
| `await_suspend` 可以返回 `coroutine_handle`，直接恢复另一个协程 | 对称转移，P0913R1 | [[expr.await]] ¶5.1.1 |
| 行为由 promise 与 awaiter 的成员函数定制 | TS 的库绑定模型（P0973R0 批评的"庞大的库绑定"） | [[dcl.fct.def.coroutine]] ¶3–5、[[expr.await]] ¶3 |
| 范围 `for` 没有 `co_await` 形式 | P0912R5 合并时排除 | [[stmt.ranged]] |
| 协程不能是 `constexpr` 函数 | TS 不支持（P0973R0 列为问题之一） | [[dcl.constexpr]] ¶3 |

### 帧的分配与 HALO

Core Coroutines 之争的焦点是帧的分配，今天的条文正好体现了 TS 一方的模型。[[dcl.fct.def.coroutine]] ¶9 说"An implementation may need to allocate additional storage for a coroutine"，这个 may 给了编译器省略分配的余地，也就是 P0981R0 所说的 HALO。条文没有任何地方保证分配一定会被省略，这正是 P0973R0 和 P1342R0 都指出的那一点：程序员无法在语言层面确认某次调用不分配。

同时，条文给了库作者控制分配的手段：分配函数先在 promise 类型的作用域中查找（¶9），并且会先尝试把协程的参数一并传给它（¶9.1，即参数预览），这样库可以让调用者通过参数传入一个分配器或内存池；如果 promise 类型提供 `get_return_object_on_allocation_failure`，分配就改用不抛异常的形式，失败时返回一个表示失败的对象（¶10）。

下面的例子同时演示了 promise 接管分配和对称转移：

```cpp run title="task_halo.cpp" ok
#include <coroutine>
#include <cstddef>
#include <cstdio>
#include <exception>
#include <new>
#include <utility>

// 一个最小的惰性 task：演示今天的规则里留下的几个设计点
struct task {
    struct promise_type {
        int value = 0;
        std::coroutine_handle<> continuation = std::noop_coroutine();

        // 帧的分配可由 promise 接管（[dcl.fct.def.coroutine]¶9）
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
                // 对称转移：返回下一个要恢复的协程（[expr.await]¶5.1.1）
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

!!! impl "一次观察"
    在本站的验证环境（Clang 23）中，这个程序用 `-O0` 编译时打印两行 `allocate frame`，用 `-O2` 编译时只打印一行：内层 `answer()` 的帧被并入了外层协程的帧，分配被省略了。帧的字节数和是否省略都取决于实现和优化级别，标准不作保证，这正是 2018 年争论的那一点。

对称转移（P0913R1）解决的是另一个问题。如果 `await_suspend` 只能返回 `void` 或 `bool`，一个协程恢复另一个协程只能在 `await_suspend` 内部调用 `resume()`，调用链会在线程栈上不断加深，大量同步完成的 `co_await` 可能导致栈溢出。允许返回 `coroutine_handle` 之后，[[expr.await]] ¶5.1.1 规定由实现去恢复返回的那个协程，实现可以把它做成尾调用，栈不再增长。上例中 `final_suspend` 返回 `continuation`，就是把控制直接交回等待者。详细机制见 [[topics/coroutines]]。

## 库的缺位与补齐（2019–2025）

C++20 只提供了 `<coroutine>` 头文件中的底层设施（[[support.coroutine]]）：`coroutine_traits`、`coroutine_handle`、`noop_coroutine`、`suspend_always` 和 `suspend_never`。没有任何可以直接拿来当返回类型的协程类型。HOPL IV（§9.3）承认这一点："C++20 doesn't have standard library support for modules and coroutines"，原因是来不及在 C++20 按时准备好。

这期间库层面的尝试包括：Baker 与 Nishanov 的 [[P1056R1]] *Add lazy coroutine (coroutine task) type*，Nishanov 的 [[P1681R0]] *Revisiting allocator model for coroutine lazy/task/generator*，Casey Carter 的 [[P2506R0]] *std::lazy*。这些提案都没有进入标准。实践中，程序员使用 cppcoro、Folly 等第三方库，或者自己编写 promise 类型。

### C++23：std::generator

生成器先落地。Corentin Jabot 与 Lewis Baker 的 [[P2168R3]] *generator: A Synchronous Coroutine Generator Compatible With Ranges* 是起点，Casey Carter 在此基础上写了 [[P2502R2]] *std::generator: Synchronous Coroutine Generator for Ranges*。据 Timur Doumler 在 JetBrains 博客上关于 2022 年 7 月线上全体会议的报告，P2502R2 在这次会议上通过，进入 C++23（[[coro.generator]]）。`std::generator` 同时是一个视图，可以直接接上范围适配器；它还支持用 `co_yield std::ranges::elements_of(...)` 递归地产出另一个生成器的元素。

这样，Stroustrup 在 HOPL IV 中用来演示 C++20 协程的那个斐波那契例子，到 C++23 才能只用标准库写出来：

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

!!! impl "实现现状"
    截至写作时，本站验证环境（Clang 23 + libc++）没有 `<generator>` 头文件，上面的例子按标准编写，未经本地编译，因此没有标注判定。

### C++26：std::execution::task

异步用的 task 类型等到了 C++26，并且与 std::execution（[[P2300R10]]）的发送器/接收器模型绑定在一起。Dietmar Kühl 与 Maikel Nadolski 的 [[P3552R0]] 最初题为 *Add a Coroutine Lazy Type*，从 R1 起改为 *Add a Coroutine Task Type*。据 Herb Sutter 关于 2025 年 6 月 Sofia 会议的 trip report，[[P3552R3]] 在这次会议上通过，加入 C++26，提供一个把协程与 C++26 的发送器/接收器异步模型集成起来的 task 类型（[[exec.task]]）。

这一决定本身也有争议。Jonathan Müller 在会后的 [[P3801R0]] *Concerns about the design of std::execution::task* 中记录，P3552 在 2025 年 2 月 Hagenberg 会议的 C++26 特性冻结期限之前没有被转交 LWG，此后在 LEWG 的两次电话会议中转交；Sofia 全体会议在有反对意见的情况下以 77 票赞成、11 票反对、29 票弃权通过。P3801R0 列出的技术顾虑包括：迭代式代码可能栈溢出、参数生命周期出人意料、缺乏对悬垂引用的保护，以及 `co_yield with_error(x)` 的写法别扭等。Kühl 的 [[P3796R1]] *Coroutine Task Issues* 汇总了 task 通过后各方提出的问题并给出处理建议，其中一部分涉及调度器亲和所用的 `affine_on`。他随后的 [[P3941R4]] *Scheduler Affinity* 针对 C++26 投票阶段国家成员体对 `affine_on` 的意见提出修改，包括改名、改用 `get_start_scheduler` 等。当前草案中的 [[exec.affine]] 与 `start_scheduler_type` 的措辞与该文件的方向一致；本页未能从会议记录中核实它在哪一次会议通过。

从 2012 年的 N3328 算起，异步协程直到 C++26 才在标准库中有了第一个现成的返回类型。这也说明了 2015 年以来 TS 的设计取向：语言只规定改写协议，返回类型完全交给库，而库的设计（尤其是调度、取消、分配器）需要单独的共识。

## 时间线

| 年份 | 事件 | 文献 |
|---|---|---|
| 1958 / 1963 | Conway 提出"协程"一词；1963 年在 CACM 发表论文 | Conway 1963 |
| 1967 | Simula 67 以 `detach` / `resume` 支持协程式对象 | *SIMULA 67 Common Base Language* |
| 1980 / 1985 | Stroustrup 的 task 库（内部发表于 1980 年，随 cfront 发布于 1985 年） | Stroustrup 1985；HOPL III、IV |
| 约 1989 年后 | task 库因移植困难不再被多数实现支持；C++98 无协程 | HOPL IV §1.1 |
| 2000 前后 | Tatham *Coroutines in C*，基于 `switch` 的宏 | Tatham |
| 2006 | protothreads（SenSys 2006） | Dunkels 等 |
| 2010 | Asio 的无栈协程示例（Boost 1.42） | Boost 1.42 发布说明 |
| 2012 | Boost.Context（1.51）；Gustafsson 提出 resumable functions | [[N3328]] |
| 2013 | Boost.Coroutine（1.53）；Asio 的 `spawn` 与文档化的协程宏（1.54）；Kowalke 与 Goodspeed 的有栈协程库提案 | [[N3708]] |
| 2014 | Rapperswil 会议要求统一两条路线；Goodspeed 的分析；Nishanov 与 Radigan 的 v.2 | [[N3985]]、[[N4232]]、[[N4134]] |
| 2015 | Lenexa 会议否决 `yield` 作关键字；Kona 会议后的措辞改用 `co_await` / `co_yield` / `co_return` | [[P0071R0]]、[[P0057R0]]、[[P0057R1]] |
| 2016 | Jacksonville 会议决定协程走 TS | [[P0158R0]]；HOPL IV §6.3 |
| 2017 | Toronto 会议完成 TS；11 月出版 ISO/IEC TS 22277:2017 | [[N4680]] |
| 2018-03 | Jacksonville：提议合并；Google 提出异议；HALO 论证；接受对称转移与参数预览 | [[P0912R0]]、[[P0973R0]]、[[P0978R0]]、[[P0981R0]]、[[P0913R1]]、[[P0914R1]] |
| 2018-06 | Rapperswil：Core Coroutines；合并动议在全体会议未达成共识 | [[P1063R0]] |
| 2018-11 | San Diego：统一方案出现；合并动议在全体会议以微弱差距失败 | [[P1241R0]]、[[P1342R0]]、[[P1362R0]]、[[P1329R0]] |
| 2019-02 | Kona：两份评估文件；TS 并入 C++20 工作草案 | [[P1492R0]]、[[P1493R0]]、[[P0912R5]] |
| 2020 | C++20 发布，含协程语言特性与 `<coroutine>`，不含协程类型 | [[N4861]]（C++20 最终工作草案） |
| 2022-07 | `std::generator` 进入 C++23 | [[P2502R2]] |
| 2025-06 | Sofia：`std::execution::task` 进入 C++26 | [[P3552R3]]、[[P3801R0]] |
| 2025–2026 | task 问题清单与调度器亲和的修改 | [[P3796R1]]、[[P3941R4]] |

## 现状与未来

以下只列有文献记录、仍在进行中的工作。它们的结局在写作时都尚未确定。

### 有栈协程：fiber_context

有栈协程并没有消失。Kowalke 与 Goodspeed 的有栈路线从 N3708、N3985 一路演化为 [[P0099R1]]、[[P0534R3]]，再到 [[P0876R0]] *fibers without scheduler*。最新的 [[P0876R24]] *fiber_context - fibers without scheduler*（2026 年 7 月）提出一个不带调度器的最小栈切换 API，作为有栈协程和用户态线程的构件，受众已是 CWG 与 LWG。反对意见见 David Chisnall 与 Matthew Taylor 的 [[P3620R0]] *Concerns with the proposed addition of fibers to C++26*，P0876R24 中有专门一节回应。与之相关，Goodspeed 曾提出 [[P3346R0]] *thread_local means fiber-specific*；据 P0876R24，SG1 在 Wrocław 会议上否决了这一修改。

### constexpr 协程

Hana Dusíková 的 [[P3367R5]] *constexpr coroutines* 提议允许协程在常量求值中运行。该文件的时间线记录，2024 年 11 月 Wrocław 会议上 EWG 和 LEWG 曾同意把它转交 C++26，但 CWG 中有实现者对实现所需的资源表示担忧；R5（2026 年 6 月）的目标已改为 C++29。当前草案的 [[dcl.constexpr]] ¶3 仍规定协程不是 constexpr-suitable 的函数。相关讨论还有 Vandevoorde 的 [[P3590R0]] *Constexpr Coroutines Burdens* 和 Dusíková 的 [[P3449R1]] *constexpr std::generator*。

### 帧分配的对齐与省略

C++20 投票阶段美国国家成员体的意见指出，协程帧的分配不考虑 `std::align_val_t` 重载，过对齐的帧可能对齐不正确。Baker 与 Nishanov 的 [[P2014R2]] 给出的解决方案以 C++26 为目标，但当前草案的 [[dcl.fct.def.coroutine]] ¶9 仍未加入对齐参数。另外，Chuanqi Xu 的 [[P2477R3]] *Allow programmers to control coroutine elision* 提议让程序员显式控制 HALO，这一方向与 2018 年 Core Coroutines 的关注点一脉相承，目前没有进入标准。

### promise 协议的放宽

C++20 的 [dcl.fct.def.coroutine] ¶6 规定，如果在 promise 类型中同时找到 `return_void` 和 `return_value`，程序非良构。Robert Leahy 的 [[P3950R0]] *return_value & return_void Are Not Mutually Exclusive* 提议取消这一限制。当前草案已没有这一条，[[stmt.return.coroutine]] ¶3 改为以 `p.return_void()` 的重载决议是否成功来决定流出函数体末尾的行为。据 Leahy 的 [[P4282R1]] *Away From co_yield For std::execution::task*，P3950 已被采纳，P4282R1 据此提议 `std::execution::task` 改用 `co_return` 而不是 `co_yield` 来表达错误完成，回应了 P3801R0 中关于 `co_yield with_error` 的批评。

### 协程与网络 I/O

2026 年的几次邮件中，Vinnie Falco 等人提交了一批文件（如 [[P4003R3]] *Ask: A Minimal Coroutine Execution Model*、[[P4007R3]] *Info: Open Issues in `std::execution::task`*、[[P4127R0]] *Info: The Coroutine Frame Allocator Timing Problem*），讨论以协程为中心的网络 I/O。P4003R3 的摘要请委员会推进其中的 IoAwaitable 协议，作为标准的协程执行模型，它只提供三件事：执行器亲和、停止令牌的传播、帧分配器的传递。标题以 Info 开头的是信息性文件。这些文件是否会改变 std::execution 与协程的关系，目前没有定论。

回头看，2019 年 Kona 会议之前反复出现的几个问题（分配能否保证省略、参数生命周期、`co_yield` 是否被挪作他用、有栈协程是否应当另设设施）在 2025 年之后的文件中仍然能找到。C++20 的决定是先交付一套有实现经验的无栈机制，把其余问题留给以后不破坏兼容的扩展；这些扩展目前还在进行中。

## 参考资料

### WG21 文件

按出现顺序排列，链接由 wg21.link 提供。

- [[N3328]] Niklas Gustafsson, *Resumable Functions*, 2012
- [[N3327]] Niklas Gustafsson, Artur Laksberg, *A Standard Programmatic Interface for Asynchronous Operations*, 2012
- [[N3564]]、[[N3650]]、[[N3722]]、[[N3858]]、[[N3977]] *Resumable Functions* 的各次修订，2013–2014
- [[N3708]] Oliver Kowalke, Nat Goodspeed, *A proposal to add coroutines to the C++ standard library*, 2013
- [[N3985]] 同上 Revision 1，2014；[[N4024]] *Distinguishing coroutines and fibers*, 2014
- [[N4232]] Nat Goodspeed, *Stackful Coroutines and Stackless Resumable Functions*, 2014
- [[N4244]] Christopher Kohlhoff, *Resumable Lambdas*, 2014；[[N4453]] *Resumable Expressions*, 2015
- [[N4397]]、[[N4398]] Oliver Kowalke, 2015；[[P0073R0]] Torvald Riegel, *On unifying the coroutines and resumable functions proposals*, 2015
- [[N4134]] Gor Nishanov, Jim Radigan, *Resumable Functions v.2*, 2014；[[N4286]]、[[N4402]]、[[N4403]]、[[N4499]]
- [[P0057R0]]、[[P0057R1]]、[[P0057R8]] Coroutines 措辞 / TS 工作草案，2015–2018
- [[P0071R0]] Gor Nishanov, *Coroutines: Keyword alternatives*, 2015
- [[P0158R0]] Jamie Allsop 等, *Couroutines belong in a TS*, 2015
- [[N4628]]、[[N4649]]、[[N4680]]、[[N4775]] Coroutines TS 工作草案与出版文本；ISO/IEC TS 22277:2017
- [[P0664R0]] Gor Nishanov, *Coroutines TS Issues*, 2017（后续修订至 P0664R8）
- [[P0912R0]]、[[P0912R5]] Gor Nishanov, *Merge Coroutines TS into C++20 working draft*, 2018–2019
- [[P0973R0]] Geoff Romer, James Dennett, *Coroutines TS Use Cases and Design Issues*, 2018
- [[P0978R0]] Gor Nishanov, 对 P0973R0 的回应, 2018
- [[P0981R0]] Richard Smith, Gor Nishanov, *Halo: coroutine Heap Allocation eLision Optimization: the joint response*, 2018
- [[P0913R1]] Gor Nishanov, *Add symmetric coroutine control transfer*, 2018
- [[P0914R1]] Gor Nishanov, *Add parameter preview to coroutine promise constructor*, 2018
- [[P1063R0]]、[[P1063R2]] Geoff Romer, James Dennett, Chandler Carruth, *Core Coroutines*, 2018–2019
- [[P1241R0]] Lee Howes, Eric Niebler, Lewis Baker, *In support of merging coroutines into C++20*, 2018
- [[P1342R0]] Lewis Baker, *Unifying Coroutines TS and Core Coroutines*, 2018
- [[P1362R0]] Gor Nishanov, *Incremental Approach: Coroutine TS + Core Coroutines*, 2018
- [[P1329R0]] Mihail Mihaylov, Vassil Vassilev, *On the Coroutines TS*, 2018；[[P1430R0]] *First-class symmetric coroutines in C++*, 2019
- [[P1477R0]] Lewis Baker, *Coroutines TS Simplifications*, 2019；[[P1471R0]] Christopher Kohlhoff, *The trouble with coroutine_traits*, 2019
- [[P1492R0]] Richard Smith 等, *Coroutines: Language and Implementation Impact*, 2019
- [[P1493R0]] Geoffrey Romer 等, *Coroutines: Use-cases and Trade-offs*, 2019
- [[P1056R1]] Lewis Baker, Gor Nishanov, *Add lazy coroutine (coroutine task) type*, 2018；[[P1681R0]]；[[P2506R0]]
- [[P2168R3]] Corentin Jabot, Lewis Baker, *generator: A Synchronous Coroutine Generator Compatible With Ranges*, 2021
- [[P2502R2]] Casey Carter, *std::generator: Synchronous Coroutine Generator for Ranges*, 2022
- [[P2300R10]] Eric Niebler 等, *`std::execution`*, 2024
- [[P3552R0]]、[[P3552R3]] Dietmar Kühl, Maikel Nadolski, *Add a Coroutine Task Type*, 2025
- [[P3801R0]] Jonathan Müller, *Concerns about the design of std::execution::task*, 2025
- [[P3796R1]] Dietmar Kühl, *Coroutine Task Issues*, 2025；[[P3941R4]] *Scheduler Affinity*, 2026
- [[P0099R1]]、[[P0534R3]]、[[P0876R0]]、[[P0876R24]] Oliver Kowalke（部分与 Nat Goodspeed 合著）, 有栈上下文切换 / `fiber_context`, 2016–2026
- [[P3620R0]] David Chisnall, Matthew Taylor, *Concerns with the proposed addition of fibers to C++26*, 2025；[[P3346R0]] Nat Goodspeed, 2024
- [[P3367R5]] Hana Dusíková, *constexpr coroutines*, 2026；[[P3590R0]]；[[P3449R1]]
- [[P2014R2]] Lewis Baker, Gor Nishanov, 协程帧的对齐分配, 2023；[[P2477R3]] Chuanqi Xu, *Allow programmers to control coroutine elision*, 2022
- [[P3950R0]] Robert Leahy, *return_value & return_void Are Not Mutually Exclusive*, 2025；[[P4282R1]] *Away From co_yield For std::execution::task*, 2026
- [[P4003R3]]、[[P4007R3]]、[[P4127R0]] Vinnie Falco 等, 2026
- [[N4861]] C++20 最终工作草案（用于核对 C++20 时的 [dcl.fct.def.coroutine] ¶6）

### 论文与书籍

- Melvin E. Conway, *Design of a Separable Transition-Diagram Compiler*, Communications of the ACM 6(7), 1963
- Donald E. Knuth, *The Art of Computer Programming*, Vol. 1, §1.4.2 及该章历史注记
- Ole-Johan Dahl, Bjørn Myhrhaug, Kristen Nygaard, *SIMULA 67 Common Base Language*, Norwegian Computing Center
- Bjarne Stroustrup, *A Set of C++ Classes for Co-routine Style Programming*, AT&T C++ Translator Release Notes, 1985
- Bjarne Stroustrup, *Evolving a language in and for the real world: C++ 1991–2006*, HOPL III, 2007
- Bjarne Stroustrup, *Thriving in a Crowded and Changing World: C++ 2006–2020*, HOPL IV, 2020（§1.1、§6.3、§9.3.2）
- Adam Dunkels, Oliver Schmidt, Thiemo Voigt, Muneeb Ali, *Protothreads: Simplifying Event-Driven Programming of Memory-Constrained Embedded Systems*, SenSys 2006

### 文章、trip report 与文档

- Simon Tatham, [*Coroutines in C*](https://www.chiark.greenend.org.uk/~sgtatham/coroutines.html)
- Boost 发布说明：[1.42](https://www.boost.org/releases/1.42.0/)、[1.51](https://www.boost.org/releases/1.51.0/)、[1.53](https://www.boost.org/releases/1.53.0/)、[1.54](https://www.boost.org/releases/1.54.0/)、[1.59](https://www.boost.org/releases/1.59.0/)、[1.62](https://www.boost.org/releases/1.62.0/)
- Boost.Asio 文档，[`coroutine` 类](https://www.boost.org/doc/libs/1_86_0/doc/html/boost_asio/reference/coroutine.html)
- Herb Sutter, [Trip report: Summer ISO C++ standards meeting (Toronto)](https://herbsutter.com/2017/07/15/trip-report-summer-iso-c-standards-meeting-toronto/), 2017
- Botond Ballo, [Trip Report: C++ Standards Meeting in Jacksonville, March 2018](https://botondballo.wordpress.com/2018/03/28/trip-report-c-standards-meeting-in-jacksonville-march-2018/)
- Botond Ballo, [Trip Report: C++ Standards Meeting in Rapperswil, June 2018](https://botondballo.wordpress.com/2018/06/20/trip-report-c-standards-meeting-in-rapperswil-june-2018/)
- Botond Ballo, [Trip Report: C++ Standards Meeting in San Diego, November 2018](https://botondballo.wordpress.com/2018/11/30/trip-report-c-standards-meeting-in-san-diego-november-2018/)
- Botond Ballo, [Trip Report: C++ Standards Meeting in Kona, February 2019](https://botondballo.wordpress.com/2019/03/20/trip-report-c-standards-meeting-in-kona-february-2019/)
- Herb Sutter, [Trip report: Winter ISO C++ standards meeting (Kona)](https://herbsutter.com/2019/02/23/trip-report-winter-iso-c-standards-meeting-kona/), 2019
- Timur Doumler, [July 2022 ISO C++ committee virtual meeting report](https://blog.jetbrains.com/clion/2022/07/july-2022-iso-cpp/), JetBrains CLion 博客
- Herb Sutter, [Trip report: June 2025 ISO C++ standards meeting (Sofia, Bulgaria)](https://herbsutter.com/2025/06/21/trip-report-june-2025-iso-c-standards-meeting-sofia-bulgaria/)
- Lewis Baker, [*C++ Coroutines: Understanding operator co_await*](https://lewissbaker.github.io/2017/11/17/understanding-operator-co-await) 及同系列文章
