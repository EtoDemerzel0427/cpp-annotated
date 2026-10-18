---
title: 操作状态
summary: operation_state 概念只要求能 start 和析构；在异步生存期内销毁它是 UB；复制或移动标准库发送器的操作状态非良构；start(op) 只接受左值、必须 noexcept，且必须真的启动操作
status: done
covers: *
papers: P2300R10
related: exec.async.ops, exec.recv, exec.connect, exec.snd, class.copy.elision
tags: 标准库, std::execution, 生存期, UB
updated: 2026-10-18
---

操作状态是 `connect(sndr, rcvr)` 的结果，是一次异步操作在内存里的全部存在：接收器、发送器复制进来的数据、所有子操作的状态、排队用的链表指针，都在里面。[[exec.async.ops]] 已经给出了它的生存期规则；本节把它落实成 `operation_state` 概念和 `start` CPO。

操作状态这个设计是 `std::execution` 能做到**零动态分配**的关键：`future` 的共享状态必须在堆上，因为生产者和消费者各自持有它；而操作状态由**调用者**拥有，可以放在栈上、放在协程帧里、嵌在父操作状态里——只要它在异步生存期内不动、不死。

## operation_state 概念（[exec.opstate.general] ¶1）

```cpp
template<class O>
  concept operation_state =
    derived_from<typename O::operation_state_concept, operation_state_tag> &&
    requires (O& o) {
      start(o);
    };
```

只有两个要求：声明 `operation_state_concept` 标签，`start(o)` 对左值可调用。注意它**不要求**可移动、可复制，甚至不要求可析构（析构由下面的语义规则约束）。与 `sender`、`receiver` 不同，这里用的是 `O::operation_state_concept` 而不是 `remove_cvref_t<O>::...`——操作状态总是以对象类型本身被检查。

¶2 若在异步操作的生存期内销毁 `operation_state` 对象，行为未定义 {{ub}}。这是 [[exec.async.ops#7]] 的重复，换成了针对对象的说法。

注 1：概念不对析构和 `start` 之外的任何操作施加要求，包括复制和移动。对模型化 `operation_state` 的类型的对象调用这类操作可能导致 UB。

¶3 对**标准库提供的**发送器 connect 产生的操作状态对象执行复制/移动构造或赋值，程序**非良构** {{ill-formed}}。

把 ¶2 的注和 ¶3 合起来看：

| 操作状态来源 | 复制/移动 |
|---|---|
| 标准库发送器 | 非良构（必须诊断；实践中这些类型删除了复制/移动构造） |
| 用户发送器 | 概念不管；即使类型允许移动，在操作启动后移动也很可能是 UB |

为什么要这么严？因为操作一旦启动，外部可能已经持有指向它内部的指针：`run_loop` 的队列里挂着它（[[exec.run.loop]]，`push-back(addressof(o))`），线程池的工作项指向它，子操作的接收器里存着指向父操作状态的指针（[[exec.snd]] 的 *basic-receiver* 存的就是 `basic-state*`）。移动之后这些指针全部悬空。

## 如何持有一个不可移动的对象

`connect` 返回 prvalue，借助 C++17 的保证复制消除（[[class.copy.elision]]），可以直接在目标位置构造：

```cpp title="hold-opstate.cpp"
namespace ex = std::execution;

auto op = ex::connect(std::move(sndr), rcvr);  // OK：prvalue 直接初始化 op，没有移动
ex::start(op);
```

需要把它放进 `optional` 或 `variant` 时（比如 `let_value` 要在运行时才 connect 第二个发送器），不能写 `opt.emplace(connect(...))`——`emplace` 会把 prvalue 物化成实参再移动。标准阐述代码用的技巧是 *emplace-from*（[[exec.snd]]）：传一个**可转换为**操作状态类型的对象，`optional` 内部做 `T(std::forward<Arg>(arg))` 时调用转换函数，转换函数返回 prvalue，于是又是保证复制消除：

```cpp title="emplace-from.cpp"
std::optional<op_t> opt;
opt.emplace(emplace_from{[&] { return ex::connect(std::move(sndr), rcvr); }});
```

## start（[exec.opstate.start]）

¶1 `start` 是一个 CPO，启动操作状态对象关联的异步操作（[[exec.async.ops]] 意义上的"启动"）。

- `start(op)` 在 `op` 是**右值**时非良构 {{ill-formed}}；
- 否则等价于 *MANDATE-NOTHROW*(op.start())，*Mandates*：类型为 `void`。

禁止右值的理由很直接：`start(connect(s, r))` 中的临时操作状态会在完整表达式结束时被销毁，而操作很可能还没完成——立即违反 [[exec.async.ops#7]]。把它在编译期拦下来，比留给运行期 UB 好得多。

必须 noexcept：`start` 不能以异常报告失败。启动过程中发生的错误（比如线程池的队列满了、分配失败）必须通过对接收器调用 `set_error` 来报告——这是 [[exec.async.ops#8]] "启动后恰好完成一次"的另一种体现：如果 `start` 能抛异常，就会出现"启动了但没有完成"的状态。

¶2 若 `op.start()` 并没有真的**启动**关联的异步操作，调用 `start(op)` 的行为未定义 {{ub}}。

这条把语义要求压在实现者身上：`start` 成员不能是空函数，不能"先记下来，等别人再调一次"。"启动"的含义来自 [[exec.async.ops#7]]：异步生存期从启动操作开始执行时开始——此后操作就必须最终完成。

!!! note "start 之后的 op 能做什么？"
    `start(op)` 之后，调用者对 `op` 能做的事只有一件：在确知完成操作已经开始执行之后销毁它。不能再次 `start`（[[exec.async.ops#2]]：至多启动一次），不能移动，不能读取内部成员（完成之后它已失效）。

## 陷阱

!!! pitfall "从函数返回操作状态"
    ```cpp title="return-opstate.cpp"
    auto make_op(auto sndr, auto rcvr) {
      return ex::connect(std::move(sndr), std::move(rcvr));   // OK：返回 prvalue，C++17 起无移动
    }
    auto make_op2(auto sndr, auto rcvr) {
      auto op = ex::connect(std::move(sndr), std::move(rcvr));
      return op;            // error（对标准库操作状态）：需要移动构造，被删除
    }
    ```
    第二种写法依赖 NRVO，而 NRVO 只是**允许**的复制消除，语言仍然要求移动构造函数可用（[[class.copy.elision]]）。操作状态的移动构造被删除，所以非良构。

!!! pitfall "在 vector 里存操作状态"
    `std::vector<op_t>` 扩容会移动元素，而 `op_t` 不可移动——`push_back`/`emplace_back` 都无法编译。需要一组操作状态时，用定长数组、`std::list`/`std::deque`（emplace 不移动已有元素），或者像 `when_all` 那样把它们放进一个 *product-type* 一次性构造（[[exec.snd]] 的 *connect-all*）。

## 思考题

!!! question "1. start 两次"
    `auto op = connect(just(1), rcvr); start(op); start(op);` 违反了哪条规则？是非良构还是 UB？

<details markdown="1">
<summary>答案</summary>

违反 [[exec.async.ops#2]]（至多启动一次）；第一次 `start` 内 `just` 已同步完成，操作状态失效，第二次 `start` 访问失效的操作状态，按 [[exec.async.ops#7]] 是 UB。编译期无法检查：两次调用都是对左值的合法 `start` 表达式。
</details>

!!! question "2. 为什么概念不要求可析构？"
    `operation_state` 没有像 `scheduler` 那样要求 `destructible`。这是疏漏吗？

<details markdown="1">
<summary>答案</summary>

概念只表达"能被启动"这一接口；析构的合法时机是由 [exec.opstate.general] ¶2 和 [[exec.async.ops#7]] 的生存期规则约束的语义问题，用概念表达不了"只能在某个时刻之后析构"。另外操作状态几乎总是作为局部变量或成员被**隐式**析构，`destructible` 对它来说并不提供有用的信息。实践中所有操作状态都有 noexcept 的析构函数。
</details>

## 小结

- `operation_state`：`operation_state_concept` 标签 + `start(o)` 对左值可调用。
- 异步生存期内销毁它是 UB；完成后它失效。
- 标准库的操作状态不可复制、不可移动（违反即非良构）；用保证复制消除或 *emplace-from* 原地构造。
- `start(op)`：拒绝右值；必须 noexcept；必须真的启动操作；失败要通过 `set_error` 报告。
