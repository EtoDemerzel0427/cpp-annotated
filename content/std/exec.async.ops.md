---
title: 异步操作
summary: std::execution 的地基——用标准语言定义执行资源、异步操作、三种完成处置、操作状态、环境、接收器、完成函数、异步生存期、发送器、调度器、完成调度器、完成签名，以及工厂/适配器/消费者三类发送器算法
status: done
papers: P2300R10
related: exec, exec.recv, exec.opstate, exec.snd, exec.sched, exec.cmplsig, intro.progress, basic.def.odr
tags: 标准库, 并发, std::execution, 生存期, UB
updated: 2026-10-18
---

[exec.async.ops] 只有 14 段，却是第 33 章的"定义章"：后面每一条规范都用这里的术语说话。读懂它，比读懂任何一个具体算法都重要。它和核心语言的关系类似 [[intro.execution]] 之于表达式求值：给一个运行期行为建立词汇。

这一节的核心是一个**状态机**：一个异步操作被**创建**（connect）、至多被**启动**一次（start）、启动后**恰好完成一次**（set_value / set_error / set_stopped 之一）。所有生存期规则、所有 UB，都围绕这三个时间点展开。

## 执行资源（¶1）

¶1 [[g:execution-resource|**执行资源**]]（execution resource）是管理一组执行代理（[[thread.req.lockable.general]] 中的 execution agent）、替调用者执行并行工作的程序实体。例 1 举了三个：当前活动线程、系统线程池、外部硬件加速器的 API。执行资源执行异步操作，并且有**有效/失效**两种状态。

"失效"这个状态是为后面的连锁规则准备的：执行资源失效时，指向它的调度器、从调度器得到的发送器、从这些发送器得到的操作状态都随之失效（¶10）。比如一个 `run_loop` 析构之后，从它得到的调度器就不能再用（[[exec.run.loop]]）。

## 异步操作（¶2）

¶2 [[g:asynchronous-operation|**异步操作**]]（asynchronous operation）是满足下列条件的一个独立程序执行单元：

- ¶2.1 **显式创建**；
- ¶2.2 **至多显式启动一次**；
- ¶2.3 一旦启动，**终将恰好完成一次**，完成时带一组（可能为空的）**结果数据**（result datums），处置（disposition）恰为以下三种之一：
    - ¶2.3.1 成功，即 **value 完成**：结果数据个数任意；
    - ¶2.3.2 失败，即 **error 完成**：恰好一个结果数据；
    - ¶2.3.3 取消，即 **stopped 完成**：没有结果数据。

    处置加结果数据合称[[g:async-result|**异步结果**]]（async result）。
- ¶2.4 可以在与启动它的执行资源**不同**的执行资源上完成；
- ¶2.5 可以创建并启动其他异步操作，称为[[g:child-operation|**子操作**]]（child operation）。子操作由父操作创建，**若被启动，必在父操作完成之前完成**。

注 1：异步操作可以**同步执行**——在 start 期间、在启动它的线程上就完成。`just(1)` 就是这样（[[exec.factories]]）。

把这几条和 `std::future` 对比，差别就清楚了：

| | `std::async` + `future` | 异步操作 |
|---|---|---|
| 何时开工 | 调用 `async` 时（`launch::async`） | 显式 `start` 时 |
| 结果形态 | 一个值或一个异常 | value（任意多个值）/ error（一个任意类型的错误）/ stopped |
| 取消 | 没有 | 一等公民：stopped 完成 |
| 嵌套 | 无约束，`future` 可被丢弃而工作继续 | 子操作必在父操作完成前完成 |

最后一行就是所谓**结构化并发**（structured concurrency）：父子操作的生存期像函数调用一样严格嵌套，所以子操作可以安全地引用父操作的状态。整个库所有"零分配"、"可以引用栈上对象"的承诺都来自这条规则。

!!! note "为什么 error 完成恰好一个数据、stopped 完成没有数据？"
    value 完成对应函数的"返回值"，多个返回值很自然（`when_all` 把各个子操作的值拼起来）。error 对应"抛出的异常"——永远只有一个对象，但类型不限于 `exception_ptr`，可以是 `error_code` 之类，不必付出异常的开销。stopped 表示"没有结果也没有错误，就是不做了"，它不是错误：调用者主动请求的取消不应该被当成失败处理。

## 操作状态、环境、接收器（¶3–5）

¶3 每个异步操作有关联的状态，称为[[g:operation-state|**操作状态**]]（operation state）。

¶4 异步操作有一个关联的[[g:execution-environment|**环境**]]（environment）：一个[[g:queryable-object|可查询对象]]（[[exec.queryable]]），表示操作的**调用者**的执行期属性——比如"调用者希望用哪个分配器"、"调用者的停止令牌是什么"、"调用者在哪个调度器上"。调用者指父操作，或者创建它的那个函数。

¶5 异步操作有一个关联的[[g:receiver|**接收器**]]（receiver）：三种完成处置的三个处理器的聚合——value 完成处理器、error 完成处理器、stopped 完成处理器。接收器自己也有一个环境。并且：

- 操作状态**拥有**操作的接收器；
- 异步操作的环境**等于**其接收器的环境。

所以"环境"不是一个独立传递的参数，而是挂在接收器上、顺着 connect 流向子操作的：父操作 connect 子发送器时传进去的接收器，带着父操作想给子操作看的环境（通常是父环境的转发版本，见 [[exec.adapt.general#3]]）。

## 完成函数与完成操作（¶6）

¶6 每种处置对应一个[[g:completion-function|**完成函数**]]（completion function）：一个[[g:customization-point-object|定制点对象]]，第一个实参是接收器，其余实参是结果数据。value 完成函数（`set_value`）用 value 结果数据调用接收器的 value 完成处理器；error、stopped 同理。

- 完成函数的无限定类型称为它的[[g:completion-tag|**完成标签**]]（completion tag）：`set_value_t`、`set_error_t`、`set_stopped_t`。
- 对完成函数的一次有效调用称为**完成操作**（completion operation）。

## 异步生存期（¶7–8）——本节最要紧的两段

¶7 异步操作的[[g:async-lifetime|**生存期**]]，又称**异步生存期**（async lifetime），**从它的启动操作开始执行时开始，到它的完成操作开始执行时结束**。

!!! std
    If the lifetime of an asynchronous operation's associated operation state ends before the lifetime of the asynchronous operation, the behavior is undefined.

即：在异步生存期内销毁操作状态 {{ub}}。再加两条：

- 完成操作执行之后，操作状态**失效**（invalid）；
- 访问失效操作状态的任何部分都是 {{ub}}。

¶8 进一步约束：

- 不得在启动操作**开始执行之前**执行完成操作（不能"还没 start 就完成"）；
- 启动操作开始执行之后，**恰好执行一个**完成操作；
- 操作状态的生存期可以在**完成操作执行期间**结束。

把 ¶7 和 ¶8 放在一起，就得到一张时间线：

```text
connect ──► [操作状态存在，但异步操作尚未开始]
start 开始 ──► 异步生存期开始 ── 操作状态必须活着 ──┐
                                                    │
完成操作开始（set_value/set_error/set_stopped）◄─────┘ 异步生存期结束
   │ 此后操作状态失效；完成函数内部可以销毁它
   ▼
```

注意异步生存期**在完成操作开始时就结束了**，而不是在完成操作返回时。这正是为了允许最后一条：接收器在 `set_value` 里可以销毁持有它的操作状态。很多真实场景需要这一点：

- `sync_wait` 的接收器在 `set_value` 里唤醒等待线程，等待线程随即让栈上的操作状态离开作用域——这可能在 `set_value` 还没返回时就发生；
- `spawn` 的状态对象在完成时 `delete` 自己（[[exec.spawn]]）。

反过来，这也给**实现者**定了规矩：调用完成函数之后，就**不能再碰** `this`（操作状态）的任何成员，因为它可能已经没了。

```cpp title="opstate-after-complete.cpp"
struct my_op {
  using operation_state_concept = std::execution::operation_state_tag;
  Rcvr rcvr;
  int  value;
  void start() & noexcept {
    std::execution::set_value(std::move(rcvr), value);
    value = 0;   // UB：完成操作已经执行，*this 已经失效（[exec.async.ops]/7）
  }
};
```

!!! pitfall "\"恰好一次\"是双向约束"
    ¶8 不只禁止完成两次，也禁止**一次都不完成**。一个被 start 了却永远不完成的操作违反了 ¶2.3 的"eventually completes"。对写算法的人来说，每一条代码路径——包括构造某个内部对象时抛出异常的路径——都必须以某个 `set_*` 结束。这就是为什么标准算法的阐述代码里到处是 `try { ... } catch (...) { set_error(std::move(rcvr), current_exception()); }`（见 [[exec.snd]] 的 *TRY-EVAL*）。

## 发送器（¶9）

¶9 [[g:sender|**发送器**]]（sender）是一个或多个异步操作的**工厂**。

- **连接**（connecting）发送器和接收器，创建一个异步操作。该操作的接收器等于用来创建它的接收器，环境等于该接收器的环境。
- **操作状态的生存期不依赖于发送器或接收器的生存期**。也就是说 connect 完成之后，原发送器和原接收器对象都可以销毁，操作状态必须自给自足（它拥有接收器的一份副本或移动后的对象，发送器里的数据也被复制或移动进来）。
- 发送器在"它与接收器连接、并且产生的异步操作被启动"时称为**被启动**。
- 发送器的异步结果就是它 connect 出来的异步操作的异步结果。发送器通过它产生的异步操作**发送**结果，接收器**接收**结果。
- 发送器也有有效/失效之分：父发送器失效时，它也失效。

"不依赖发送器的生存期"这条决定了实现方式：适配器在 connect 时必须把子发送器 **connect 进**自己的操作状态（而不是存一个指向子发送器的指针），父操作状态里嵌套着子操作状态。这也是 [[exec.snd]] 中 *basic-operation* 的结构：`inner-ops` 是一个装着所有子操作状态的 *product-type*。

## 调度器（¶10）

¶10 [[g:scheduler|**调度器**]]（scheduler）是对执行资源的抽象，提供统一的通用接口把工作调度到该资源上。它是**发送器的工厂**：这些发送器的异步操作在属于该执行资源的执行代理上执行 value 完成操作。

- 从调度器取得发送器的表达式称为 **schedule-expression**（即 `schedule(sch)`），结果称为[[g:schedule-sender|**调度发送器**]]（schedule sender）。
- 调度发送器的操作成功时执行一个**结果数据为空**的 value 完成：`set_value(rcvr)`。
- 多个调度器可以指向同一个执行资源。
- 执行资源失效时，调度器失效，从它得到的调度发送器、从这些发送器得到的操作状态也都失效。

换句话说，调度器不直接"执行一个函数"，而是给你一个"跳到那里去"的发送器：`schedule(sch) | then(f)` 才是"在 `sch` 上执行 `f`"。

## 完成调度器与发送器属性（¶11–12）

¶11 异步操作对每种处置有一个或多个关联的[[g:completion-scheduler|**完成调度器**]]（completion scheduler）：其执行资源被用来执行该处置的完成操作的调度器。value 完成调度器就是 value 完成操作可能在其上执行的调度器，error、stopped 同理。

¶12 发送器有一个关联的可查询对象，称为它的[[g:sender-attributes|**属性**]]（attributes），描述发送器及其产生的异步操作的各种特性。对每种处置，有一个查询对象从属性中读出对应的完成调度器（`get_completion_scheduler<set_value_t>` 等，[[exec.get.compl.sched]]）。

- 如果某个完成调度器查询良构，那么对该发送器创建的**任何**异步操作，这个处置的完成调度器都是**唯一**的——你不能报告"有时在 A 上完成、有时在 B 上完成"。
- 调度发送器**必须**有 value 完成调度器属性，且其值等于产生它的调度器。

!!! warning "两个都用 get_env 取得，但方向相反"
    接收器的**环境**描述"调用者那一侧"（自上而下流动）；发送器的**属性**描述"这个发送器自己"（自下而上流动）。二者都通过 `get_env` 取得（[[exec.get.env]] 注 1），都是可查询对象，但不要混用：问发送器的属性 `get_scheduler` 没有意义，问接收器的环境 `get_completion_scheduler` 也没有意义。

## 完成签名（¶13）

¶13 [[g:completion-signature|**完成签名**]]（completion signature）是描述一个完成操作的函数类型。异步操作有一个**有限的**可能完成签名集合，对应它**潜在求值**（[[basic.def.odr]] 意义上的 potentially evaluated）的那些完成操作。

精确的对应关系是：对完成函数 `set`、接收器 `rcvr`、实参包 `args`，完成操作 `c = set(rcvr, args...)` 的"实际签名"是 `F = decltype(auto(set))(decltype((args))...)`；签名 `Sig` 与 `c` 关联，当且仅当 *MATCHING-SIG*(Sig, F)（[[exec.general#7]]：形参统一加 `&&` 后比较）。

例：`set_value(std::move(rcvr), 42)` 的 `F` 是 `set_value_t(int)`（`decltype((42))` 是 `int`）；`int x; set_value(std::move(rcvr), x)` 的 `F` 是 `set_value_t(int&)`。前者与 `set_value_t(int)` 匹配，后者不匹配——`set_value_t(int)` 承诺的是"右值 int"，传左值得声明 `set_value_t(int&)`。

本段最后几句决定了整个类型计算的架构：

- **发送器类型 + 环境类型**共同决定完成签名集合；
- **接收器类型不影响**完成签名，只有接收器的**环境类型**影响；
- [[g:non-dependent-sender|**非依赖发送器**]]（non-dependent sender）：完成签名不依赖执行环境即可确定的发送器类型。

为什么要把接收器排除在外？因为发送器常常要在**还没有接收器**的时候就回答"我会怎么完成"：比如 `when_all` 要在构造时检查子发送器是不是只有一种 value 完成，`let_value` 要先知道前驱的值类型才能算出回调返回什么发送器。如果签名依赖接收器类型，就会出现"接收器的类型依赖签名、签名依赖接收器类型"的循环。环境则是可以提前知道的：`read_env(get_scheduler)` 的值类型取决于环境里的调度器类型，所以它是**依赖发送器**，需要环境才能回答。详见 [[exec.cmplsig]]。

## 三类发送器算法（¶14）

¶14 **发送器算法**是接受和/或返回发送器的函数，分三类：

- ¶14.1 **发送器工厂**（sender factory）：接受非发送器的实参，返回发送器。`schedule`、`just`、`read_env`（[[exec.factories]]）。
- ¶14.2 [[g:sender-adaptor|**发送器适配器**]]（sender adaptor）：由一个或多个**子发送器**和（可能为空的）其他实参构造并返回**父发送器**。父发送器创建的异步操作是子发送器所创建操作的**父操作**。`then`、`let_value`、`when_all`……（[[exec.adapt]]）。
- ¶14.3 **发送器消费者**（sender consumer）：接受一个或多个发送器和其他实参，**返回类型不是发送器**。`sync_wait`（[[exec.consumers]]）、`spawn`（[[exec.spawn]]）。

¶14.2 把"父发送器/子发送器"和 ¶2.5 的"父操作/子操作"对应起来：适配器嵌套的结构就是操作嵌套的结构，结构化并发的保证自然沿着表达式的嵌套结构成立。

## 陷阱 / 常见误解

!!! pitfall "\"操作状态可以移动\""
    ¶9 只说操作状态不依赖发送器与接收器的生存期，并没有说它可以移动。事实上 [[exec.opstate.general#3]] 规定：对标准库发送器 connect 出来的操作状态做复制或移动构造/赋值，程序**非良构**。异步操作启动后，别的线程可能持有指向操作状态内部的指针（比如线程池队列里挂着它），移动它等于让这些指针悬空。所以操作状态通常用保证复制消除（`auto op = connect(...)`）原地构造，或者用 `emplace-from`（[[exec.snd]]）塞进 `optional`/`variant`。

!!! pitfall "\"子操作完成了，父操作就可以不管它了\""
    ¶2.5 只要求子操作在父操作完成**之前**完成。父操作完成时，所有已启动的子操作都必须已经完成；没有"脱离父操作独自运行"的子操作。确实需要"发射后不管"的工作时，标准给的工具是把它关联到一个 async scope 上（[[exec.spawn]]），由 scope 的 `join` 来负责等待。

## 思考题

!!! question "1. 同步完成与生存期"
    `just(1)` 的操作在 `start(op)` 内部就调用了 `set_value`。按 ¶7，异步生存期在 `set_value` 开始时结束；那么在 `start` 返回之前，调用者能销毁 `op` 吗？

<details markdown="1">
<summary>答案</summary>

不能由 `start` 的**调用者**在 `start` 返回前销毁——调用者此时还在 `start` 里，根本没有机会。但**接收器**可以：如果接收器的 `set_value` 里销毁了 `op`（¶8 允许"操作状态的生存期可以在完成操作执行期间结束"），那么 `start` 的实现在调用 `set_value` 之后就不能再访问 `*this`。标准的 *just* 实现（[[exec.factories]]）的 `start` 恰好以 `set-cpo(std::move(rcvr), std::move(ts)...)` 结尾，之后什么都不做。另外，调用者在 `start(op)` 返回后、但不知道操作是否已完成时销毁 `op`，对异步完成的发送器是 UB（¶7）；只有确认完成操作已经开始执行后才能销毁。
</details>

!!! question "2. 签名里的引用"
    一个发送器在 start 中执行 `set_value(std::move(rcvr), s)`，其中 `s` 是操作状态里的 `std::string` 成员（左值）。它应当声明哪个完成签名？声明 `set_value_t(std::string)` 可以吗？

<details markdown="1">
<summary>答案</summary>

实际签名是 `set_value_t(std::string&)`。*MATCHING-SIG* 把 `set_value_t(std::string)` 变成 `set_value_t(std::string&&)` 再比较，与 `set_value_t(std::string&)` 不同，所以只声明 `set_value_t(std::string)` 违反 [[exec.getcomplsigs#5]]：潜在求值的完成操作必须有匹配的签名。要么声明 `set_value_t(std::string&)`，要么改成 `set_value(std::move(rcvr), std::move(s))`。后者更常见：操作马上就要完成，状态里的值没有必要保留。
</details>

## 小结

| 术语 | 要点 |
|---|---|
| 异步操作 | 显式创建、至多启动一次、启动后恰好完成一次；value / error / stopped |
| 子操作 | 若启动，必在父操作完成前完成（结构化并发） |
| 操作状态 | 拥有接收器；异步生存期内销毁它是 UB；完成后失效 |
| 异步生存期 | [start 开始执行, 完成操作开始执行) |
| 环境 | 接收器上的可查询对象，描述调用者 |
| 属性 | 发送器上的可查询对象，描述发送器自身（如完成调度器） |
| 完成签名 | 由发送器类型 + 环境类型决定，与接收器类型无关 |
| 发送器算法 | 工厂 / 适配器 / 消费者 |
