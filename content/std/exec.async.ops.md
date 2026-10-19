---
title: 异步操作
summary: std::execution 的基本术语：异步操作、操作状态、接收器、发送器、调度器、完成签名，以及异步生存期的规则。
status: draft
papers: P2300R10
related: exec, exec.recv, exec.opstate, exec.snd, exec.sched, exec.cmplsig, intro.progress, basic.def.odr
tags: 标准库, 并发, std::execution, 生存期, UB
updated: 2026-10-19
---

!!! tldr
    - 异步操作显式创建、至多启动一次，启动后恰好完成一次：value 完成（任意多个值）、error 完成（一个错误）或 stopped 完成（没有数据）。
    - 子操作若被启动，必须在父操作完成之前完成，这是结构化并发和零分配的基础。
    - 异步生存期从启动开始执行时开始，到完成操作开始执行时结束；在此期间销毁操作状态是未定义行为，完成之后再访问它也是。
    - 发送器是异步操作的工厂，调度器是发送器的工厂；接收器的环境描述调用者，发送器的属性描述发送器自己。
    - 完成签名只由发送器类型和环境类型决定，与接收器类型无关。

[exec.async.ops] 为第 33 章建立词汇，后面每一条规范都用这里的术语。它围绕一个简单的状态机：一个异步操作被创建（connect），至多被启动一次（start），启动后恰好完成一次（`set_value`、`set_error`、`set_stopped` 之一）。

本页的例子都没有经过编译：Clang 23 的 libc++ 还没有实现 `std::execution` 的发送器部分。

## 异步操作（¶2）

¶2 **异步操作**（[[g:asynchronous-operation|asynchronous operation]]）是一个独立的程序执行单元，它：

- ¶2.1 显式创建；
- ¶2.2 至多显式启动一次；
- ¶2.3 一旦启动，终将恰好完成一次。完成时带着一组（可能为空的）结果数据，处置（disposition）是以下三种之一：
    - ¶2.3.1 成功，称为 **value 完成**，结果数据个数任意；
    - ¶2.3.2 失败，称为 **error 完成**，恰有一个结果数据；
    - ¶2.3.3 取消，称为 **stopped 完成**，没有结果数据。

    处置和结果数据合称**异步结果**（[[g:async-result|async result]]）。
- ¶2.4 可以在与启动它的执行资源不同的执行资源上完成；
- ¶2.5 可以创建并启动其他异步操作，称为**子操作**（[[g:child-operation|child operation]]）。子操作若被启动，必须在父操作完成之前完成。

注 1 补充说，异步操作可以同步执行，也就是在 `start` 期间、在启动它的线程上就完成。`just(1)` 就是这样（[[exec.factories]]）。

和 `std::future` 对比，区别就清楚了：

| | `std::async` + `future` | 异步操作 |
|---|---|---|
| 何时开始 | 调用 `async` 时 | 显式 `start` 时 |
| 结果 | 一个值或一个异常 | 任意多个值、一个任意类型的错误，或取消 |
| 取消 | 没有 | stopped 完成 |
| 嵌套 | 丢弃 `future` 后工作可能继续 | 子操作必须在父操作完成前完成 |

最后一行叫**结构化并发**（structured concurrency）：父子操作的生存期像函数调用一样严格嵌套，所以子操作可以放心地引用父操作的状态。库中不需要堆分配、可以引用栈上对象的承诺都来自这条规则。

error 完成对应抛出的异常，永远只有一个对象，但类型不限于 `exception_ptr`，也可以是 `error_code`，不必付出异常的开销。stopped 完成表示既没有结果也没有错误，调用者主动请求的取消不应被当成失败处理。

## 执行资源（¶1）

¶1 **执行资源**（[[g:execution-resource|execution resource]]）是管理一组执行代理、替调用者执行并行工作的程序实体。例 1 举了当前线程、系统线程池和硬件加速器的 API。执行资源执行异步操作，并且有有效、失效两种状态。

失效状态是为调度器准备的：执行资源失效时，指向它的调度器、从这些调度器得到的发送器和操作状态都随之失效（¶10）。比如 `run_loop` 析构之后，从它得到的调度器就不能再用（[[exec.run.loop]]）。

## 操作状态、环境、接收器（¶3–5）

¶3 每个异步操作有一份关联的状态，称为**操作状态**（[[g:operation-state|operation state]]）。

¶4 异步操作有一个关联的**环境**（[[g:execution-environment|environment]]）。它是一个[[g:queryable-object|可查询对象]]（[[exec.queryable]]，可以按键查询的只读集合），描述调用者的执行期属性，比如调用者希望用哪个分配器、它的停止令牌是什么、它在哪个调度器上运行。调用者指父操作或创建该操作的函数。

¶5 异步操作还有一个关联的**接收器**（[[g:receiver|receiver]]），它聚合了三个处理器，分别处理 value、error、stopped 三种完成。接收器有自己的环境。操作状态拥有接收器，异步操作的环境就是其接收器的环境。

所以环境不是一个单独传递的参数，而是挂在接收器上，随着 connect 流向子操作。父操作 connect 子发送器时传入的接收器，带着父操作想让子操作看到的环境，通常是父环境的转发版本（[[exec.adapt.general#3]]）。

## 完成函数（¶6）

¶6 每种处置对应一个**完成函数**（[[g:completion-function|completion function]]）。它是一个定制点对象，第一个实参是接收器，其余实参是结果数据：`set_value`、`set_error`、`set_stopped`。

完成函数的无限定类型叫它的**完成标签**（[[g:completion-tag|completion tag]]），即 `set_value_t`、`set_error_t`、`set_stopped_t`。对完成函数的一次有效调用叫**完成操作**（completion operation）。

## 异步生存期（¶7–8）

```cpp title="opstate-after-complete.cpp"
struct my_op {
  using operation_state_concept = std::execution::operation_state_tag;
  Rcvr rcvr;
  int  value;
  void start() & noexcept {
    std::execution::set_value(std::move(rcvr), value);
    value = 0;   // UB：完成操作已经执行，*this 已失效
  }
};
```

`set_value` 执行之后，`*this` 可能已经被销毁了，比如接收器在 `set_value` 里唤醒了等待线程，等待线程随即让栈上的操作状态离开作用域。所以完成之后再写 `value` 是未定义行为。

¶7 异步操作的**生存期**，又称**异步生存期**（[[g:async-lifetime|async lifetime]]），从它的启动操作开始执行时开始，到它的完成操作开始执行时结束。

!!! std
    If the lifetime of an asynchronous operation's associated operation state ends before the lifetime of the asynchronous operation, the behavior is undefined.

换句话说，在异步生存期内销毁操作状态是 {{ub}}。执行完成操作之后，操作状态就失效了，访问失效操作状态的任何部分也是 {{ub}}。

¶8 进一步规定：完成操作不能在启动操作开始执行之前发生；启动之后，恰好执行一个完成操作；操作状态的生存期可以在完成操作执行期间结束。

```text
connect ──► 操作状态存在，异步操作尚未开始
start 开始 ──► 异步生存期开始，操作状态必须一直存在
完成操作开始 ──► 异步生存期结束；此后操作状态失效，完成函数内部可以销毁它
```

异步生存期在完成操作开始时就结束，而不是在它返回时。这正是为了允许接收器在 `set_value` 里销毁持有它的操作状态。`sync_wait` 唤醒等待线程、`spawn` 的状态对象在完成时删除自己（[[exec.spawn]]），都依赖这一点。

对实现者来说，规则反过来就是：调用完成函数之后，不能再访问操作状态的任何成员。

!!! pitfall "恰好一次是双向约束"
    ¶8 不只禁止完成两次，也禁止一次都不完成。写算法时，每条代码路径（包括构造内部对象时抛出异常的路径）都必须以某个 `set_*` 结束。所以标准算法的阐述代码里常见 `try { ... } catch (...) { set_error(std::move(rcvr), current_exception()); }`，见 [[exec.snd]] 的 *TRY-EVAL*。

## 发送器（¶9）

¶9 **发送器**（[[g:sender|sender]]）是一个或多个异步操作的工厂。把发送器和接收器**连接**（connect）起来，就创建了一个异步操作，它的接收器就是传入的接收器，环境就是该接收器的环境。

!!! std
    The lifetime of an asynchronous operation's associated operation state does not depend on the lifetimes of either the sender or the receiver from which it was created.

connect 完成后，原来的发送器和接收器对象都可以销毁，操作状态必须自给自足。因此适配器在 connect 时要把子发送器 connect 进自己的操作状态，而不是保存指向子发送器的指针，父操作状态里嵌套着子操作状态。[[exec.snd]] 中 *basic-operation* 的结构就是这样。

本段的其余定义：发送器连接到接收器、且产生的操作被启动时，称发送器**被启动**；发送器的异步结果就是它产生的操作的异步结果；父发送器失效时，发送器也失效。

## 调度器（¶10）

¶10 **调度器**（[[g:scheduler|scheduler]]）是执行资源的抽象，提供把工作调度到该资源上的统一接口。它是发送器的工厂：这些发送器产生的操作在该执行资源的执行代理上执行 value 完成。

从调度器取得发送器的表达式（即 `schedule(sch)`）叫 **schedule-expression**，结果叫**调度发送器**（[[g:schedule-sender|schedule sender]]）。调度发送器成功时执行一个不带数据的 value 完成，即 `set_value(rcvr)`。多个调度器可以指向同一个执行资源。

调度器不直接执行函数，而是给你一个转到该资源上的发送器。在 `sch` 上执行 `f` 要写成 `schedule(sch) | then(f)`。

## 完成调度器与属性（¶11–12）

¶11 异步操作对每种处置都有一个或多个**完成调度器**（[[g:completion-scheduler|completion scheduler]]）：该处置的完成操作在其执行资源上执行。

¶12 发送器有一个关联的可查询对象，称为它的**属性**（[[g:sender-attributes|attributes]]），描述发送器及其产生的操作的特性。对每种处置，有一个查询对象从属性中读出完成调度器，例如 `get_completion_scheduler<set_value_t>`（[[exec.get.compl.sched]]）。

如果某个完成调度器查询良构，那么对该发送器创建的任何操作，这个处置的完成调度器都是唯一的。调度发送器必须有 value 完成调度器属性，其值等于产生它的调度器。

!!! warning "环境和属性方向相反"
    接收器的环境描述调用者一侧，从上往下流；发送器的属性描述发送器自己，从下往上流。两者都用 `get_env` 取得（[[exec.get.env]]），都是可查询对象，但不要混用：问发送器属性 `get_scheduler`、问接收器环境 `get_completion_scheduler` 都没有意义。

## 完成签名（¶13）

¶13 **完成签名**（[[g:completion-signature|completion signature]]）是描述一个完成操作的函数类型。异步操作的可能完成签名构成一个有限集合，对应它可能执行（在 [[basic.def.odr]] 的潜在求值意义上）的那些完成操作。

精确的对应关系是：完成操作 `set(rcvr, args...)` 的实际签名是 `F = decltype(auto(set))(decltype((args))...)`，签名 `Sig` 与它关联，当且仅当 *MATCHING-SIG*(Sig, F) 为 `true`。*MATCHING-SIG*（[[exec.general#7]]）把每个形参类型加上 `&&` 后再比较。

例如 `set_value(std::move(rcvr), 42)` 的实际签名是 `set_value_t(int)`，与声明的 `set_value_t(int)` 匹配。`int x; set_value(std::move(rcvr), x)` 的实际签名是 `set_value_t(int&)`，不匹配 `set_value_t(int)`，因为后者承诺的是右值 `int`，传左值要声明 `set_value_t(int&)`。

本段最后几句决定了类型计算的架构：发送器类型加环境类型决定完成签名集合，接收器类型本身不起作用，只有接收器的环境类型起作用。完成签名不依赖环境就能确定的发送器类型叫**非依赖发送器**（[[g:non-dependent-sender|non-dependent sender]]）。

为什么把接收器排除在外？因为发送器常常要在还没有接收器时就回答自己会怎样完成。`when_all` 要检查每个子发送器至多有一种 value 完成，`let_value` 要先知道前驱的值类型才能算出后继发送器的类型。如果签名依赖接收器类型，就会形成循环。环境则可以提前知道，比如 `read_env(get_scheduler)` 的值类型取决于环境里的调度器类型，它是依赖发送器。详见 [[exec.cmplsig]]。

## 三类发送器算法（¶14）

¶14 接受或返回发送器的函数叫发送器算法，分三类：

- ¶14.1 **发送器工厂**（sender factory）：接受非发送器实参，返回发送器，如 `schedule`、`just`、`read_env`（[[exec.factories]]）。
- ¶14.2 **发送器适配器**（[[g:sender-adaptor|sender adaptor]]）：由一个或多个子发送器和其他实参构造并返回父发送器，如 `then`、`let_value`、`when_all`（[[exec.adapt]]）。父发送器创建的操作是子发送器所创建操作的父操作。
- ¶14.3 **发送器消费者**（sender consumer）：接受发送器，返回类型不是发送器，如 `sync_wait`（[[exec.consumers]]）、`spawn`（[[exec.spawn]]）。

¶14.2 把父子发送器和 ¶2.5 的父子操作对应起来：适配器表达式怎样嵌套，操作就怎样嵌套，结构化并发的保证随之成立。

## 常见误解

!!! pitfall "操作状态可以移动"
    ¶9 只说操作状态不依赖发送器和接收器的生存期，没有说它可以移动。[[exec.opstate.general#3]] 规定，复制或移动由标准库发送器 connect 出来的操作状态，程序非良构。操作启动后，别的线程可能持有指向它内部的指针（比如线程池队列），移动它会让这些指针悬空。所以操作状态通常靠保证的复制消除原地构造：`auto op = connect(...)`。

!!! pitfall "子操作可以脱离父操作运行"
    ¶2.5 要求已启动的子操作在父操作完成之前完成，没有脱离父操作独自运行的子操作。确实需要启动后不管的工作时，标准的做法是把它关联到一个 async scope 上（[[exec.spawn]]），由 scope 的 `join` 负责等待。

## 思考题

!!! question "1. 同步完成与生存期"
    `just(1)` 的操作在 `start(op)` 内部就调用了 `set_value`。`start` 的实现在调用 `set_value` 之后还能访问 `*this` 吗？

<details markdown="1">
<summary>答案</summary>

不能。¶8 允许操作状态的生存期在完成操作执行期间结束，接收器的 `set_value` 里完全可能销毁 `op`。所以 `start` 调用完成函数之后不能再访问 `*this`。标准的 *just* 实现（[[exec.factories]]）的 `start` 以 `set-cpo(std::move(rcvr), std::move(ts)...)` 结尾，之后什么都不做。

对调用者来说，在 `start(op)` 返回后、还不知道操作是否已完成时销毁 `op`，对异步完成的发送器是 UB（¶7）。只有确认完成操作已经开始执行之后，才能销毁它。
</details>

!!! question "2. 签名里的引用"
    一个发送器在 `start` 中执行 `set_value(std::move(rcvr), s)`，`s` 是操作状态里的 `std::string` 成员。只声明 `set_value_t(std::string)` 可以吗？

<details markdown="1">
<summary>答案</summary>

不可以。`s` 是左值，实际签名是 `set_value_t(std::string&)`。*MATCHING-SIG* 把 `set_value_t(std::string)` 看作 `set_value_t(std::string&&)`，与之不同，违反了 [[exec.getcomplsigs#5]]：可能执行的完成操作必须有匹配的签名。

要么声明 `set_value_t(std::string&)`，要么改成 `set_value(std::move(rcvr), std::move(s))`。后者更常见，因为操作马上就完成了，状态里的值没必要保留。
</details>

## 小结

| 术语 | 要点 |
|---|---|
| 异步操作 | 显式创建、至多启动一次、启动后恰好完成一次 |
| 子操作 | 若启动，必在父操作完成前完成 |
| 操作状态 | 拥有接收器；异步生存期内销毁它是 UB；完成后失效 |
| 异步生存期 | 从 start 开始执行，到完成操作开始执行 |
| 环境 | 接收器上的可查询对象，描述调用者 |
| 属性 | 发送器上的可查询对象，描述发送器自身 |
| 完成签名 | 由发送器类型和环境类型决定，与接收器类型无关 |
| 发送器算法 | 工厂、适配器、消费者 |
