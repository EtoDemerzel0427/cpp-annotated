---
title: 发送器与协程
summary: 两个方向的桥——可等待体自动是发送器（is-awaitable、env-promise）；发送器经 as_awaitable 变成可等待体（sender-awaitable 把结果存进 variant，完成时恢复协程，stopped 交给承诺类型的 unhandled_stopped）；with_awaitable_senders 作为承诺类型基类让协程能 co_await 任何单值发送器
status: done
covers: exec.coro.util, exec.awaitable, exec.with.awaitable.senders
papers: P2300R10
related: dcl.fct.def.coroutine, expr.await, support.coroutine, exec.connect, exec.task, exec.queries, exec.snd.concepts
tags: 标准库, std::execution, 协程, co_await
updated: 2026-10-18
---

协程与发送器解决的是同一类问题：描述"等某件事做完再继续"。`std::execution` 在两个方向上把它们接起来：

| 方向 | 机制 | 位置 |
|---|---|---|
| 可等待体 → 发送器 | 发送器概念把可等待体识别为发送器；`connect` 用 *connect-awaitable* 协程包装 | [exec.awaitable]，[[exec.connect]] |
| 发送器 → 可等待体 | `as_awaitable(sndr, promise)` 返回一个 awaiter；`with_awaitable_senders` 让承诺类型的 `await_transform` 自动调用它 | [exec.as.awaitable]，[exec.with.awaitable.senders] |

在此基础上，[[exec.task]] 中的 `task<T>` 提供了一个开箱即用的协程类型。阅读本页前应熟悉 [[dcl.fct.def.coroutine]] 中的承诺类型、`await_transform`，以及 [[expr.await]] 中 *await-expression* 的求值步骤。

## 可等待体辅助设施（[exec.awaitable]）

¶1 发送器概念把可等待体识别为发送器。在 [exec] 中，[[g:exec-awaitable|**可等待体**]]（awaitable）是在给定上下文中可以作为 `co_await` 操作数的表达式。

¶2 ***GET-AWAITER*(c, p)**：把 `c` 作为协程中 *await-expression* 的操作数时，按 [[expr.await]] 所做的那一串变换（调用承诺类型的 `await_transform`、选取 `operator co_await`、隐式转换与实质化），得到的左值 *e*（awaiter）。`p` 是协程承诺对象的左值。注 1 列出了这些步骤。*GET-AWAITER*(c) 是在一个**没有** `await_transform` 的未指定空承诺类型 *none-such* 下做同样的事（`coroutine_handle<none-such>` 行为同 `coroutine_handle<void>`）。

¶3 *is-awaiter* 与 *is-awaitable*：

```cpp
template<class A, class... Promise>
concept is-awaiter = requires (A& a, coroutine_handle<Promise...> h) {
  a.await_ready() ? 1 : 0;
  { a.await_suspend(h) } -> await-suspend-result;
  a.await_resume();
};

template<class C, class... Promise>
concept is-awaitable = requires (C (*fc)() noexcept, Promise&... p) {
  { GET-AWAITER(fc(), p...) } -> is-awaiter<Promise...>;
};
```

*await-suspend-result*<T>：`T` 是 `void`、`bool` 或 `coroutine_handle` 的特化——正是 [[expr.await]] 允许的三种 `await_suspend` 返回类型。注意 *is-awaitable* 用一个返回 `C` 的函数指针来得到"`C` 类型的表达式"，以正确保留值类别。

¶4 *await-result-type*<C, Promise>：`decltype(GET-AWAITER(c, p).await_resume())`——`co_await c` 的结果类型。

¶5 *with-await-transform*<Derived>：提供两个 `await_transform` 重载：默认原样返回；若值 `t` 有成员 `t.as_awaitable(p)` 返回可等待体（*has-as-awaitable*），就调用它。这是"让对象自定义自己被 co_await 的方式"的钩子。

¶6 *env-promise*<Env>：一个只用于类型计算的承诺类型（注 2：成员不必定义），派生自 *with-await-transform*，`get_env()` 返回 `const Env&`，有 `unhandled_stopped()`。发送器概念用 *is-awaitable*<Sndr, *env-promise*<env<>>> 判断"是否是可等待体"，[[exec.getcomplsigs]] 用 *env-promise*<Env> 计算可等待体在环境 `Env` 下的结果类型。

可等待体作为发送器时，签名固定为：

```cpp
completion_signatures<SET-VALUE-SIG(await-result-type<S, env-promise<Env>>),
                      set_error_t(exception_ptr),
                      set_stopped_t()>
```

`co_await` 的结果作 value；从 `co_await` 抛出的异常作 error；stopped 来自 *connect-awaitable-promise* 的 `unhandled_stopped`（[[exec.connect]]）。

## as_awaitable（[exec.as.awaitable]）

¶1 `as_awaitable` 把一个对象变成在特定协程中可等待的对象。阐述用实体：

```cpp
template<class Sndr, class Promise>
concept awaitable-sender =
  single-sender<Sndr, env_of_t<Promise>> &&
  sender-to<Sndr, typename sender-awaitable<Sndr, Promise>::awaitable-receiver> &&
  requires (Promise& p) {
    { p.unhandled_stopped() } -> convertible_to<coroutine_handle<>>;
  };
```

一个发送器要能被 `co_await`，需要：
- **恰好一种 value 签名**（*single-sender*，[[exec]] 中 [execution.syn] ¶3）——`co_await` 只能产生一个结果；
- 能连接到 *awaitable-receiver*；
- 承诺类型有 `unhandled_stopped()`，返回可转换为 `coroutine_handle<>` 的东西——用来处理 stopped 完成。

### sender-awaitable（¶2–6）

```cpp
template<class Sndr, class Promise>
class sender-awaitable {
  struct unit {};
  using value-type  = single-sender-value-type<Sndr, env_of_t<Promise>>;
  using result-type = conditional_t<is_void_v<value-type>, unit, value-type>;
  struct awaitable-receiver;

  variant<monostate, result-type, exception_ptr> result{};
  connect_result_t<Sndr, awaitable-receiver> state;

public:
  sender-awaitable(Sndr&& sndr, Promise& p);
  static constexpr bool await_ready() noexcept { return false; }
  void await_suspend(coroutine_handle<Promise>) noexcept { start(state); }
  value-type await_resume();
};
```

awaiter 对象本身就容纳了**操作状态**和**结果存储**。awaiter 是 *await-expression* 求值过程中的临时对象，活在协程帧里，在协程挂起期间一直存在——于是操作状态"在异步生存期内不动、不死"的要求（[[exec.async.ops#7]]）自然满足，而且不需要任何堆分配（协程帧本身的分配除外）。

¶5 构造：`state` 以 `connect(std::forward<Sndr>(sndr), awaitable-receiver{addressof(result), coroutine_handle<Promise>::from_promise(p)})` 初始化——connect 在**构造 awaiter 时**发生，`start` 在 `await_suspend` 中发生（协程已挂起之后）。

¶4 *awaitable-receiver* 的行为：

- ¶4.1 `set_value(rcvr, vs...)`：把值放进 `result` 的第 1 个备选（构造抛异常则放 `current_exception()`），然后**恢复协程** `continuation.resume()`。*Mandates*：`result-type` 可由 `vs...` 构造。
- ¶4.2 `set_error(rcvr, err)`：把 *AS-EXCEPT-PTR*(err) 放进第 2 个备选，恢复协程。
- ¶4.3 `set_stopped(rcvr)`：调用 `continuation.promise().unhandled_stopped()`，把返回的句柄转成 `coroutine_handle<>` 后 `resume()`——**不**恢复当前协程。
- ¶4.4 环境：对转发查询 `tag`，`get_env(crcvr).query(tag, as...)` 等价于 `tag(get_env(as_const(promise)), as...)`——发送器看到的环境就是**协程承诺对象的环境**。

*MAKE-NOEXCEPT*(expr) 把调用包进一个 noexcept lambda：`resume()` 若抛出异常，直接 `terminate`。

¶6 `await_resume()`：`result` 是异常则 `rethrow_exception`；否则返回值（`void` 时什么也不返回）。所以 error 完成在协程里表现为 `co_await` **抛出异常**。

!!! note "stopped 不是异常"
    ¶4.3 是这套设计里最特别的一点：发送器以 stopped 完成时，被挂起的协程**永远不会被恢复**。控制转给承诺类型的 `unhandled_stopped()`，由它决定接下来恢复谁——通常是"调用者的" `unhandled_stopped`，一路向上传播，直到某个能处理取消的地方（比如 *connect-awaitable-promise* 对接收器调用 `set_stopped`）。这相当于一个**不能被 `catch` 的**"取消异常"，沿着协程调用链传播，而沿途协程的帧由各自的拥有者销毁。[exec.with.awaitable.senders] ¶1 正是这样描述的："as if an uncatchable 'stopped' exception were thrown"。

### as_awaitable 的选择顺序（¶7–8）

¶7 `as_awaitable(expr, p)`（`p` 必须是左值，否则非良构；`expr` 与 `p` 的求值顺序不确定）依次取：

- ¶7.1 `expr.as_awaitable(p)`，若良构（*Mandates*：结果是可等待体）——对象自定义；
- ¶7.2 `adapt-for-await-completion(transform_sender(expr, get_env(p))).as_awaitable(p)`，若良构、`expr` 在承诺类型环境下是 `sender_in` 且有 *single-sender-value-type*——变换后的发送器自定义；
- ¶7.3 `(void(p), expr)`，若 `expr` 本身已经是该承诺类型下的 awaiter（*GET-AWAITER*(expr) 满足 *is-awaiter*<Promise>）——已经是可等待体，原样返回；
- ¶7.4 *sender-awaitable*{adapt-for-await-completion(transform_sender(expr, get_env(p))), p}，若是单值发送器——通用路径；
- ¶7.5 否则 `(void(p), expr)`——什么也不做，交给 `co_await` 的普通规则（多半会报错）。

¶8 *adapt-for-await-completion*(s)：若 `get_await_completion_adaptor(get_env(s))(s)` 良构就用它（[[exec.get.await.adapt]]），否则 `s`。

注意 ¶7.3 排在 ¶7.4 前面：一个**既是** awaiter **又是**发送器的类型（比如某些 task 实现），`as_awaitable` 优先把它当 awaiter 用，保留其原生的协程语义，而不是绕道 connect。

## with_awaitable_senders（[exec.with.awaitable.senders]）

¶1 作为协程承诺类型的**基类**，使发送器在该协程中可以被 `co_await`。并且提供 `unhandled_stopped` 的默认实现：发送器以 `set_stopped` 完成时，相当于从 *await-expression* 抛出一个不可捕获的"stopped 异常"。注 1：协程不会被恢复，调用者的承诺类型的 `unhandled_stopped` 被调用。

```cpp
template<class-type Promise>
struct with_awaitable_senders {
  template<class OtherPromise>
    requires (!same_as<OtherPromise, void>)
  void set_continuation(coroutine_handle<OtherPromise> h) noexcept;

  coroutine_handle<> continuation() const noexcept { return continuation; }
  coroutine_handle<> unhandled_stopped() noexcept { return stopped-handler(continuation.address()); }

  template<class Value>
  see below await_transform(Value&& value);

private:
  [[noreturn]] static coroutine_handle<> default-unhandled-stopped(void*) noexcept { terminate(); }
  coroutine_handle<> continuation{};
  coroutine_handle<> (*stopped-handler)(void*) noexcept = &default-unhandled-stopped;
};
```

- **CRTP**：`Promise` 是派生的承诺类型，`await_transform` 里要把 `*this` 转成 `Promise&` 传给 `as_awaitable`。
- ¶2 `set_continuation(h)`：记住"调用者"协程 `h`。若 `OtherPromise` 有 `unhandled_stopped()`，`stopped-handler` 设为一个函数：从地址还原 `coroutine_handle<OtherPromise>`，调用其承诺对象的 `unhandled_stopped()`——**向调用者传播取消**；否则设为默认的 `terminate()`。用函数指针 + `void*` 是一种手工的类型擦除：`with_awaitable_senders<Promise>` 不必知道调用者的承诺类型。
- `unhandled_stopped()`：调用 `stopped-handler`。
- ¶3 `await_transform(value)`：`return as_awaitable(std::forward<Value>(value), static_cast<Promise&>(*this));`——协程体内**每个** `co_await x` 都先经过 `as_awaitable`。

```cpp title="with-awaitable-senders.cpp"
namespace ex = std::execution;

struct my_task {
  struct promise_type : ex::with_awaitable_senders<promise_type> {
    my_task get_return_object();
    std::suspend_always initial_suspend() noexcept { return {}; }
    auto final_suspend() noexcept { /* 恢复 continuation() */ }
    void return_value(int);
    void unhandled_exception();
  };
  // ...
};

my_task f(ex::scheduler auto sch) {
  co_await ex::schedule(sch);                                  // 发送器：转到 sch 上继续
  int v = co_await (ex::just(20) | ex::then([](int x) { return x + 1; }));
  co_return v;
}
```

!!! pitfall "没有调用 set_continuation 时被取消"
    `stopped-handler` 的初值是 `default-unhandled-stopped`，即 `terminate()`。如果协程的拥有者没有用 `set_continuation` 注册一个能处理取消的调用者，那么任何一个在该协程中被 `co_await` 的发送器以 stopped 完成，都会导致 `std::terminate`。自己写 task 类型时，必须在启动协程前设置好 continuation。

## 思考题

!!! question "1. co_await 一个有两种 value 签名的发送器"
    `co_await s`，`s` 的签名是 `set_value_t(int)`、`set_value_t(std::string)`。在继承 `with_awaitable_senders` 的协程里会怎样？

<details markdown="1">
<summary>答案</summary>

`await_transform` 调用 `as_awaitable(s, p)`。¶7.2、¶7.4 都要求 *single-sender-value-type* 良构，而有两种 value 签名时它非良构（[execution.syn] ¶2.4），所以这两条都不适用；`s` 也不是 awaiter（¶7.3）；于是走 ¶7.5，返回 `s` 本身。接着 `co_await` 对 `s` 寻找 `operator co_await` 或 awaiter 成员，找不到，程序非良构。解决办法是先 `into_variant`：`co_await into_variant(s)` 得到 `variant<tuple<int>, tuple<std::string>>`。
</details>

!!! question "2. 结果为什么存进 variant 而不是直接传给协程？"
    *awaitable-receiver* 的 `set_value` 为什么要先把值放进 `result`，再 `resume()`，而不是在 `set_value` 里直接让协程拿到值？

<details markdown="1">
<summary>答案</summary>

协程恢复后通过 `await_resume()` 取得 `co_await` 的结果——这是 [[expr.await]] 固定的协议，没有别的通道。所以值必须先存在某个 `await_resume` 能读到的地方，也就是 awaiter 自己的成员 `result`。另外，`set_value` 的实参可能引用发送器操作状态内部的数据；`resume()` 之后协程会继续运行，可能很快结束 *await-expression*、销毁 awaiter（连同其中的操作状态），把值先复制进 `result` 才能保证 `await_resume` 读到的是有效数据。
</details>

## 小结

- 可等待体自动是发送器：签名为 `set_value_t(await 结果)`、`set_error_t(exception_ptr)`、`set_stopped_t()`。
- `as_awaitable(sndr, p)`：自定义优先；已是 awaiter 则原样；单值发送器包成 *sender-awaitable*（awaiter 内含操作状态与结果）。
- value → `await_resume` 返回；error → `await_resume` 重新抛出；stopped → 不恢复协程，调用 `promise.unhandled_stopped()`。
- 发送器在协程中看到的环境 = 承诺对象的 `get_env()`。
- `with_awaitable_senders<P>`：CRTP 基类，`await_transform` 统一调用 `as_awaitable`；`set_continuation` 设置取消的传播目标，默认 `terminate`。
