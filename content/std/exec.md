---
title: 执行控制库
summary: 第 33 章导读——std::execution（P2300）的发送器/接收器模型：发送器描述工作，connect 把它与接收器绑成操作状态，start 才真正开工；各页怎么读、本章用到的仅用于阐述的辅助设施
status: draft
covers: exec.general, execution.syn
papers: P2300R10
related: exec.async.ops, exec.snd, exec.sched, exec.recv, exec.opstate, intro.progress, execpol
tags: 标准库, 并发, std::execution, 导读
updated: 2026-10-18
---

第 33 章 [exec] 是 C++26 新增的**执行控制库**，头文件 `<execution>`，主体来自 [[P2300R10]]（`std::execution`）。它要解决的问题是：怎样用**一套通用接口**描述"在某个地方运行一段工作，完成后把结果交给下一段工作"，而且这套接口能同时服务线程池、GPU、事件循环、协程，并且做到零动态分配、可取消、错误可传播。{{c++26}}

`std::async`/`std::future` 做不到这些：`future` 一定有一个堆上的共享状态，`async` 一调用就开工，取消要自己想办法，`then` 式的链接在标准里从未落地。本章的回答是一个由四个概念组成的模型：

| 角色 | 概念 | 一句话 |
|---|---|---|
| 发送器 | `sender` | 对一段异步工作的**描述**；本身不执行任何东西 |
| 接收器 | `receiver` | 工作完成后的**后续**：`set_value` / `set_error` / `set_stopped` 三个入口 |
| 操作状态 | `operation_state` | `connect(sndr, rcvr)` 的结果，装着这次运行所需的一切；`start(op)` 才开工 |
| 调度器 | `scheduler` | 执行资源的句柄；`schedule(sch)` 给出"跑到那里去"的发送器 |

## 一个完整的生命周期

!!! note "关于本章的例子"
    截至写作时，本机的 Clang 23 + libc++ 还没有提供 `std::execution` 的发送器部分（`std::execution::just` 不存在），本地也没有安装参考实现。所以本章的例子都**未在本机验证**：按草案文字推演写成，没有 godbolt 按钮，也不标判定。

```cpp title="hello-sender.cpp"
#include <execution>
#include <print>
#include <utility>
namespace ex = std::execution;

int main() {
  ex::parallel_scheduler sch = ex::get_parallel_scheduler();

  ex::sender auto work = ex::schedule(sch)                      // 1. 描述：跳到线程池
                       | ex::then([] { return 6; })             //    然后算出 6
                       | ex::then([](int x) { return x * 7; }); //    然后乘 7

  // 2. 消费：sync_wait 在内部 connect + start，并阻塞当前线程直到完成
  auto [v] = std::this_thread::sync_wait(std::move(work)).value();
  std::println("{}", v);   // 42
}
```

拆开看，`sync_wait` 内部做的事（[[exec.sync.wait]]）正是整个模型的骨架：

1. **构造发送器**。`schedule(sch) | then(f) | then(g)` 只是把 `f`、`g`、`sch` 装进一个嵌套的对象里。[[exec.adapt.general#3]] 明确禁止适配器在 `connect` + `start` 之前产生除复制/移动实参以外的可观察效果——发送器是**惰性**的。
2. **connect**。`connect(work, rcvr)` 递归地把每一层发送器与"下一层的接收器"连起来，得到一个**操作状态**对象。这个对象通常就在调用者的栈上，里面嵌套着所有子操作的状态——这就是零分配的来源。
3. **start**。`start(op)` 启动最外层操作，它再启动子操作。线程池的线程执行 `f`，结果 6 通过 `set_value` 交给 `then(g)` 的接收器，算出 42，再 `set_value` 给 `sync_wait` 的接收器。
4. **完成**。三种完成恰好发生一次（[[exec.async.ops#8]]）。完成之后操作状态失效，`sync_wait` 才能让它离开作用域。

这四步对应本章最核心的一节 [[exec.async.ops]]：那里用标准语言定义了"异步操作"、"操作状态"、"异步生存期"等术语，后面所有条款都建立在它之上。

## 本章地图

本章（含 C++26 之后并入的修改）共 16 个二级条款。本站按主题分页：

| 主题 | 页面 | 内容 |
|---|---|---|
| 基础模型 | [[exec.async.ops]] | 异步操作、操作状态、接收器、发送器、调度器、完成签名的**定义** |
| 查询与环境 | [[exec.queryable]]、[[exec.queries]] | 可查询对象、`prop`/`env`；`get_stop_token`、`get_scheduler`、`get_completion_scheduler` 等全部查询 |
| 三个核心概念 | [[exec.sched]]、[[exec.recv]]、[[exec.opstate]] | `scheduler`、`receiver`、`operation_state` 概念与 `set_*`、`start` |
| 发送器 | [[exec.snd]] | `sender`/`sender_in` 概念，标准发送器的阐述用骨架（`make-sender`、`impls-for`） |
| 完成签名 | [[exec.cmplsig]] | `completion_signatures`、`get_completion_signatures`、依赖发送器 |
| 连接与定制 | [[exec.connect]]、[[exec.snd.transform]] | `connect`、可等待体当发送器；domain 与 `transform_sender` |
| 工厂 | [[exec.factories]] | `schedule`、`just`、`read_env` |
| 适配器 | [[exec.adapt]]、[[exec.on]]、[[exec.let]]、[[exec.bulk]]、[[exec.when.all]] | `then`、`write_env`；换调度器；`let_*`；`bulk`；`when_all` |
| 消费者 | [[exec.consumers]] | `sync_wait`、`sync_wait_with_variant` |
| 结构化并发 | [[exec.scope]]、[[exec.spawn]] | `counting_scope`；`associate`、`spawn`、`spawn_future` |
| 执行上下文 | [[exec.run.loop]]、[[exec.par.scheduler]] | `run_loop`；`parallel_scheduler` 与可替换后端 |
| 协程 | [[exec.as.awaitable]]、[[exec.task]] | 在协程里 `co_await` 发送器；`task<T>`、`affine`、`inline_scheduler`、`task_scheduler` |

建议阅读顺序：[[exec.async.ops]] → [[exec.recv]] / [[exec.opstate]] → [[exec.snd]] → [[exec.cmplsig]] → [[exec.connect]]，然后挑感兴趣的算法看。

## 概述（[exec.general]）

¶1–2 本章描述支持执行函数对象（[[function.objects]]）的组件。表 157 只列了四个子条款（调度器、接收器、操作状态、发送器），全部在 `<execution>` 里；这张表比本章实际内容少得多，不必当真。

¶3 表 158 把本章的[[g:customization-point-object|定制点对象]]（CPO）分成四类：

| 类别 | 作用 | 例子 |
|---|---|---|
| core | 核心功能，把组件连起来 | `connect`、`start` |
| completion functions | 发送器用来宣告完成（成功、出错、取消） | `set_value`、`set_error`、`set_stopped` |
| senders | 可定制的发送器算法 | 工厂 `schedule`、`just`、`read_env`；适配器 `continues_on`、`then`、`let_value`；消费者 `sync_wait` |
| queries | 查询对象的各种属性 | 通用查询 `get_allocator`、`get_stop_token`；环境查询 `get_scheduler`；调度器查询 `get_forward_progress_guarantee`；发送器属性查询 `get_completion_scheduler` |

!!! history "从 tag_invoke 到成员函数"
    P2300 的早期修订用 `tag_invoke` 实现定制：`tag_invoke(set_value, rcvr, v)` 这类自由函数。合入 C++26 的版本改成了**成员函数**：`set_value(rcvr, vs...)` 等价于 `rcvr.set_value(vs...)`，`connect(s, r)` 先找 `s.connect(r)`，查询 `q(env)` 等价于 `env.query(q)`。所以写自己的发送器/接收器时，只需提供普通成员函数，再声明 `sender_concept`/`receiver_concept` 等标签类型。

### 本章通用的阐述用实体（¶4–9）

本章大量使用**仅用于阐述**（exposition only）的宏和概念。它们不是你能调用的东西，只是规范用来缩短文字的速记。最常见的几个：

¶5 ***MANDATE-NOTHROW*(expr)**：等价于 `expr`，但 *Mandates* `noexcept(expr)` 为 true。几乎所有 CPO 都套了这一层：`set_value`、`start`、`get_env`、各种查询……**都必须是 noexcept 的**，否则程序非良构。这是整个库"完成路径不抛异常"设计的落点：错误要走 `set_error`，而不是从完成函数里抛出来。

¶6 ***movable-value*<T>**：`decay_t<T>` 可移动构造、可从 `T` 构造，且 `T` 不是数组。`just(ts...)`、`then(sndr, f)` 中的 `ts`、`f` 都要满足它——因为它们会被存进发送器。

¶7 ***MATCHING-SIG*(F1, F2)**：比较两个函数类型时把每个形参类型 `Args` 换成 `Args&&` 再比。于是 `set_value_t(int)` 与 `set_value_t(int&&)` 被视为同一签名（`int&&` 折叠后仍是 `int&&`），但与 `set_value_t(int&)` 不同。完成签名的"匹配"都用它（[[exec.async.ops#13]]）。

¶8 ***AS-EXCEPT-PTR*(err)**：把错误值变成 `exception_ptr`。已经是 `exception_ptr` 就原样返回（前置条件：非空）；是 `error_code` 就包成 `system_error`；否则 `make_exception_ptr(err)`。`sync_wait` 和协程集成（[[exec.as.awaitable]]）在需要"把错误抛出来"时用它。

¶9 ***AS-CONST*(expr)**：以 const 左值引用的形式访问 `expr`。查询总是通过它调用 `query`，所以 `query` 成员应该是 const 的。

## 头文件概要（[execution.syn]）

`<execution>` 同时容纳了 C++17 的执行策略（[[execpol]]）和本章的全部内容。几个值得注意的点：

- 查询对象分在两个命名空间：`forwarding_query`、`get_allocator`、`get_stop_token` 在 `std` 里（它们也被别的库组件用到），其余在 `std::execution` 里。
- `sync_wait`、`sync_wait_with_variant` 在 `std::this_thread` 里——它们阻塞**当前线程**，放在这里提醒你这一点。
- `read_env`、`write_env`、`unstoppable` 的类型是 *unspecified*，不像其他 CPO 那样有具名的 `xxx_t`。

¶1 ***variant-or-empty*<Ts...>**：`Ts` 非空时是去重后的 `variant<decay_t<Ts>...>`；为空时是一个**不能构造**的 *empty-variant* 类型（默认构造函数被删除）。这样"没有任何 value 完成"的发送器，其 `value_types_of_t` 仍是一个合法类型，只是不可能有值。

¶2–3 ***single-sender-value-type*<Sndr, Env...>** 与 ***single-sender***：如果发送器只有**一个** value 完成签名，它给出"那个值的类型"：只有一个数据时是 `decay_t<T>`，没有数据时是 `void`，多个数据时是 `tuple<decay_t<Ts>...>`；有多个 value 签名时非良构。`co_await` 一个发送器（[[exec.as.awaitable]]）和 `stopped_as_optional`（[[exec.adapt]]）都要求 *single-sender*。

¶4 ***valid-completion-signatures***：恰好是 `completion_signatures` 的特化。

## 实现现状

!!! impl "实现视角"
    - libc++（本机 Clang 23）截至写作时未提供 `std::execution::just` 等发送器设施；`<execution>` 里只有执行策略。
    - P2300 的作者们维护着参考实现 stdexec（NVIDIA），本章大部分设计先在那里落地；但它的接口与当前草案不一定逐字一致，用它验证例子时要留意差异。

## 历史与演进

!!! history
    - P2300 经过十余次修订，以 [[P2300R10]] 合入 C++26 工作草案。
    - 早期修订中的 `ensure_started`、`start_detached`、`split` 等"急切启动/共享结果"的算法，在当前草案中**不存在**。急切启动的需求改由 async scope 承担：`spawn`、`spawn_future` 必须挂在一个 scope 上（[[exec.spawn]]），这样每个被启动的操作都有人负责等待它结束。
    - `task`、`counting_scope`、`parallel_scheduler`、`get_completion_signatures` 改为 `consteval` 函数等，都是 P2300 合入之后、C++26 定稿前后的提案加进来的；domain 机制（[[exec.snd.transform]]）也经过了多轮重写。草案中个别措辞（如 `get_start_scheduler`、`indeterminate_domain`）是否已在 C++26 中，本站不作断言。

## 思考题

!!! question "1. 发送器可以被 connect 几次？"
    [[exec.async.ops#9]] 说发送器是"一个或多个异步操作的工厂"。那么同一个 `just(1)` 对象能 connect 两次吗？

<details markdown="1">
<summary>答案</summary>

取决于发送器类型和值类别。[[exec.snd.concepts#9]] 规定标准库的发送器总提供接受**右值**发送器的 `connect`；只有当发送器类型可复制构造时，才提供接受**左值**的 `connect`。`just(1)` 的类型可复制，所以左值 connect 可以做任意多次，每次得到一个独立的操作状态（`int` 被复制进去）。若把它 `std::move` 进 `connect`，之后它处于"已移动"状态，再用就是在用一个状态未指定的对象。一个只能移动的发送器（比如持有 `unique_ptr` 的 `just`）则只能 connect 一次。
</details>

!!! question "2. 为什么完成函数必须是 noexcept？"
    `set_value(rcvr, v)` 若抛异常，会发生什么问题？

<details markdown="1">
<summary>答案</summary>

完成操作执行时，被完成的那个异步操作已经结束了它的异步生存期（[[exec.async.ops#7]]），它的操作状态可能正在被销毁。此时如果从 `set_value` 抛出异常，异常会落到某个工作线程或者 `start` 的调用栈上，没有任何一方能把它转交给"应该知道的人"。所以规范用 *MANDATE-NOTHROW*（[exec.general] ¶5）强制完成函数 noexcept：接收器在 `set_value` 里遇到错误时，应该自己把它转成对下游的 `set_error`——`then` 的 *TRY-SET-VALUE*（[[exec.snd]]）就是这么做的。
</details>

## 小结

- 发送器是惰性的**描述**，`connect` 生成**操作状态**，`start` 开工，三种完成**恰好一次**。
- 所有定制都是成员函数：`rcvr.set_value(...)`、`sndr.connect(r)`、`env.query(q)`。
- 完成函数、`start`、`get_env`、查询都被强制 noexcept。
- 本章的规范大量使用阐述用实体；读条款时先确认每个斜体名字的定义在哪一节（[exec.general]、[[exec.snd]] 的 [exec.snd.expos]、[[exec.queries]] 的 [exec.queries.expos]）。
