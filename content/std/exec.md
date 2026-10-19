---
title: 执行控制库
summary: 第 33 章 std::execution 的导读：发送器描述工作，connect 把它和接收器绑成操作状态，start 才真正开始执行。
status: draft
covers: exec.general, execution.syn
papers: P2300R10
related: exec.async.ops, exec.snd, exec.sched, exec.recv, exec.opstate, intro.progress, execpol
tags: 标准库, 并发, std::execution, 导读
updated: 2026-10-19
---

!!! tldr
    - `std::execution`（C++26，头文件 `<execution>`）用一套接口描述在哪里运行一段工作、完成后把结果交给谁，适用于线程池、事件循环、GPU 和协程。
    - 发送器只是工作的描述；`connect` 把它和接收器组合成操作状态，`start` 之后工作才开始。
    - 每个启动的操作恰好以 `set_value`、`set_error`、`set_stopped` 之一完成一次。
    - 定制全部通过成员函数：`rcvr.set_value(...)`、`sndr.connect(r)`、`env.query(q)`；完成函数、`start`、查询都必须是 `noexcept` 的。
    - Clang 23 的 libc++ 还没有发送器部分，本章的例子都没有在本机编译过。

## 为什么需要一个新模型

`std::async` 加 `std::future` 能把工作放到别的线程上，但有几个做不到的地方：`future` 总要在堆上分配一个共享状态；`async` 一调用就开始执行，没法先描述、后启动；没有取消；标准里也没有 `then` 式的链接。

第 33 章用四个概念来回答这些问题 {{c++26}}，主体来自 [[P2300R10]]：

| 角色 | 概念 | 作用 |
|---|---|---|
| 发送器 | `sender` | 描述一段异步工作，自己不执行任何东西 |
| 接收器 | `receiver` | 工作完成后的后续，有 `set_value`、`set_error`、`set_stopped` 三个入口 |
| 操作状态 | `operation_state` | `connect(sndr, rcvr)` 的结果，装着这次运行需要的一切；`start(op)` 开始执行 |
| 调度器 | `scheduler` | 执行资源的句柄；`schedule(sch)` 给出一个转到该资源上运行的发送器 |

## 一个完整的生命周期

!!! note "关于本章的例子"
    Clang 23 的 libc++ 中，`<execution>` 只有执行策略，没有 `std::execution::just` 等发送器设施，本机也没有安装参考实现。本章的例子按草案写成，没有经过编译，不标判定。

```cpp title="hello-sender.cpp"
#include <execution>
#include <print>
#include <utility>
namespace ex = std::execution;

int main() {
  ex::parallel_scheduler sch = ex::get_parallel_scheduler();

  ex::sender auto work = ex::schedule(sch)                      // 跳到线程池
                       | ex::then([] { return 6; })             // 算出 6
                       | ex::then([](int x) { return x * 7; }); // 乘 7

  // sync_wait 在内部 connect 并 start，阻塞当前线程直到完成
  auto [v] = std::this_thread::sync_wait(std::move(work)).value();
  std::println("{}", v);   // 42
}
```

`sync_wait` 内部做的事（[[exec.sync.wait]]）就是整个模型的骨架：

1. **构造发送器**。`schedule(sch) | then(f) | then(g)` 只是把 `sch`、`f`、`g` 装进一个嵌套的对象。[[exec.adapt.general#3]] 规定，适配器在 `connect` 和 `start` 之前，除了复制、移动实参，不能产生可观察的效果。
2. **connect**。`connect(work, rcvr)` 逐层把发送器和下一层的接收器连起来，得到一个操作状态对象。它通常就在调用者的栈上，里面嵌套着所有子操作的状态，所以不需要堆分配。
3. **start**。`start(op)` 启动最外层操作，它再启动子操作。线程池的线程执行 `f`，结果 6 通过 `set_value` 交给 `then(g)` 的接收器，算出 42 后再交给 `sync_wait` 的接收器。
4. **完成**。每个操作恰好完成一次（[[exec.async.ops#8]]）。完成之后操作状态失效，`sync_wait` 才让它离开作用域。

这些步骤用到的术语（异步操作、操作状态、异步生存期等）都定义在 [[exec.async.ops]]，后面所有条款都建立在它之上。

## 本章地图

| 主题 | 页面 | 内容 |
|---|---|---|
| 基础模型 | [[exec.async.ops]] | 异步操作、操作状态、接收器、发送器、调度器、完成签名的定义 |
| 查询与环境 | [[exec.queryable]]、[[exec.queries]] | 可查询对象、`prop`、`env`；`get_stop_token`、`get_scheduler` 等查询 |
| 三个核心概念 | [[exec.sched]]、[[exec.recv]]、[[exec.opstate]] | `scheduler`、`receiver`、`operation_state`，以及 `set_*`、`start` |
| 发送器 | [[exec.snd]] | `sender`、`sender_in` 概念，标准发送器的阐述用骨架 |
| 完成签名 | [[exec.cmplsig]] | `completion_signatures`、`get_completion_signatures`、依赖发送器 |
| 连接与定制 | [[exec.connect]]、[[exec.snd.transform]] | `connect`、把可等待体当作发送器；domain 与 `transform_sender` |
| 工厂 | [[exec.factories]] | `schedule`、`just`、`read_env` |
| 适配器 | [[exec.adapt]]、[[exec.on]]、[[exec.let]]、[[exec.bulk]]、[[exec.when.all]] | `then`、`write_env`；切换调度器；`let_*`；`bulk`；`when_all` |
| 消费者 | [[exec.consumers]] | `sync_wait`、`sync_wait_with_variant` |
| 结构化并发 | [[exec.scope]]、[[exec.spawn]] | `counting_scope`；`associate`、`spawn`、`spawn_future` |
| 执行上下文 | [[exec.run.loop]]、[[exec.par.scheduler]] | `run_loop`；`parallel_scheduler` 与可替换后端 |
| 协程 | [[exec.as.awaitable]]、[[exec.task]] | 在协程里 `co_await` 发送器；`task<T>`、`affine` 等 |

建议的阅读顺序是 [[exec.async.ops]] → [[exec.recv]]、[[exec.opstate]] → [[exec.snd]] → [[exec.cmplsig]] → [[exec.connect]]，然后挑感兴趣的算法看。

## 定制方式：成员函数

[[exec.general#3]] 的表 158 把本章的[[g:customization-point-object|定制点对象]]（CPO，一种可以被用户类型定制行为的函数对象）分成四类：

| 类别 | 作用 | 例子 |
|---|---|---|
| 核心 | 把组件连起来 | `connect`、`start` |
| 完成函数 | 发送器用来宣告成功、出错或取消 | `set_value`、`set_error`、`set_stopped` |
| 发送器算法 | 可定制的工厂、适配器、消费者 | `just`、`then`、`continues_on`、`sync_wait` |
| 查询 | 查询对象的各种属性 | `get_stop_token`、`get_scheduler`、`get_completion_scheduler` |

用户类型参与定制的方式都是普通成员函数：`set_value(rcvr, vs...)` 调用 `rcvr.set_value(vs...)`，`connect(s, r)` 先找 `s.connect(r)`，查询 `q(env)` 调用 `env.query(q)`。另外，类型要声明一个标签（如 `using receiver_concept = receiver_tag;`）表示自己是接收器、发送器或调度器。

!!! history "从 tag_invoke 到成员函数"
    P2300 的早期修订用 `tag_invoke` 这类自由函数实现定制，写法是 `tag_invoke(set_value, rcvr, v)`。合入 C++26 的版本改成了成员函数，写自己的组件简单得多。

## 本章通用的阐述用实体

标准用一些仅用于阐述（exposition only）的宏和概念来缩短条文，它们不是可以调用的东西。读后面各页时最常遇到的是：

¶5 *MANDATE-NOTHROW*(expr) 等价于 `expr`，但要求 `noexcept(expr)` 为 `true`，否则程序非良构。几乎所有 CPO 都套了这一层：`set_value`、`start`、`get_env`、各种查询都必须不抛异常。整个库的设计是完成路径不抛异常，错误要通过 `set_error` 传递。

¶6 *movable-value*<T> 要求 `decay_t<T>` 可移动构造、可从 `T` 构造，且 `T` 不是数组。`just(ts...)` 的 `ts`、`then(sndr, f)` 的 `f` 都要满足它，因为它们会被存进发送器。

¶7 *MATCHING-SIG*(F1, F2) 比较两个函数类型时，先把每个形参类型 `A` 换成 `A&&`。所以 `set_value_t(int)` 和 `set_value_t(int&&)` 算同一个签名，和 `set_value_t(int&)` 不同。完成签名的匹配都用它（[[exec.async.ops#13]]）。

¶8 *AS-EXCEPT-PTR*(err) 把错误值变成 `exception_ptr`：已经是 `exception_ptr` 就原样返回（它不能为空），是 `error_code` 就包成 `system_error`，其他类型用 `make_exception_ptr`。`sync_wait` 和协程集成需要把错误抛出来时用它。

¶9 *AS-CONST*(expr) 以 const 左值引用访问 `expr`。查询总是通过它调用 `query`，所以 `query` 成员必须是 const 的。

## 头文件 &lt;execution&gt;

`<execution>`（[[execution.syn]]）同时容纳 C++17 的执行策略（[[execpol]]）和本章全部内容。值得注意的有三点：

- `forwarding_query`、`get_allocator`、`get_stop_token` 在命名空间 `std` 里，因为别的库组件也会用到它们；其余查询在 `std::execution` 里。
- `sync_wait`、`sync_wait_with_variant` 在 `std::this_thread` 里，提醒你它们会阻塞当前线程。
- `read_env`、`write_env`、`unstoppable` 的类型是未指定的，不像其他 CPO 那样有具名的 `xxx_t` 类型。

!!! history
    P2300 早期修订里的 `ensure_started`、`start_detached`、`split` 等立即启动或共享结果的算法，在当前草案中不存在。立即启动的需求改由 async scope 承担：`spawn`、`spawn_future` 必须挂在一个 scope 上（[[exec.spawn]]），这样每个启动的操作都有人负责等它结束。`task`、`counting_scope`、`parallel_scheduler` 等则是 P2300 合入之后由其他提案加入的。

!!! impl "实现现状"
    P2300 的作者们维护着参考实现 stdexec，本章大部分设计先在那里实现。它的接口与当前草案不一定逐字一致，用它验证例子时要留意差异。

<details class="fine" markdown="1"><summary>其余条文</summary>

- [[exec.general]] ¶1–2：本章描述支持执行函数对象的组件；表 157 只列出调度器、接收器、操作状态、发送器四个子条款，都在 `<execution>` 里。
- [[execution.syn]] ¶1：*variant-or-empty*<Ts...> 在 `Ts` 非空时是去重后的 `variant<decay_t<Ts>...>`，为空时是一个不能构造的类型。这样没有任何 value 完成的发送器，其 `value_types_of_t` 仍是合法类型。
- [[execution.syn]] ¶2–3：*single-sender-value-type* 与 *single-sender* 描述只有一个 value 完成签名的发送器：一个数据时是 `decay_t<T>`，没有数据时是 `void`，多个数据时是 `tuple<decay_t<Ts>...>`。`co_await` 一个发送器（[[exec.as.awaitable]]）要求 *single-sender*。
- [[execution.syn]] ¶4：*valid-completion-signatures* 指 `completion_signatures` 的特化。

</details>
