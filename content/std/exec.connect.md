---
title: connect
summary: connect(sndr, rcvr) 先用接收器的环境对发送器做 transform_sender，再调用它的 connect 成员；对象只是可等待体时，用一个阐述用协程把它包成操作状态；connect 是否抛异常只能取决于环境类型。
status: draft
covers: exec.connect
papers: P2300R10
related: exec.async.ops, exec.snd, exec.snd.transform, exec.opstate, exec.recv, exec.as.awaitable, dcl.fct.def.coroutine, expr.await
tags: 标准库, std::execution, connect, 协程, IFNDR
updated: 2026-10-19
---

!!! tldr
    - `connect(sndr, rcvr)` 先调用 `transform_sender(sndr, get_env(rcvr))`，让执行 domain 有机会换掉算法的实现，再调用变换结果的 `connect` 成员。
    - 发送器在接收器的环境下必须有确定的完成签名，接收器必须接得住每一种完成，否则 `connect` 非良构。
    - 对两个环境类型相同的接收器，`connect` 的 noexcept 性必须一致，否则程序非良构，不要求诊断。
    - 没有 `connect` 成员的可等待体由一个协程包装，协程帧就是操作状态；完成前先挂起，因为接收器可能在完成时销毁它。

本页的 `std::execution` 例子没有经过编译验证：本机 Clang 23 附带的 libc++ 还没有实现发送器库。只用到协程语言特性的例子经过了本机 Clang 编译。

## connect 做了什么（¶1–2、¶6）

¶1 `connect` 把一个[[g:sender|发送器]]和一个[[g:receiver|接收器]]连接起来，得到一个[[g:operation-state|操作状态]]（[[exec.async.ops#9]]）。这是描述变成可运行实体的一步。

¶2 设 `new_sndr` 是 `transform_sender(sndr, get_env(rcvr))` 的结果。`transform_sender` 按发送器和接收器环境关联的执行 domain 改写发送器，比如把 `bulk` 换成 GPU 上的实现（[[exec.snd.transform]]）。

¶6 `connect(sndr, rcvr)` 等价于：

- ¶6.1 `new_sndr.connect(rcvr)`，如果它良构。结果类型必须满足 `operation_state`（*Mandates*）。
- ¶6.2 否则，*connect-awaitable*(new_sndr, rcvr)，见下文。

`rcvr` 只求值一次。另有两条 *Mandates*：

- ¶6.8 `sender_in<Sndr, env_of_t<Rcvr>>`：发送器在接收器的环境下能算出完成签名；
- ¶6.9 *receiver-of*<Rcvr, completion_signatures_of_t<Sndr, env_of_t<Rcvr>>>：接收器能接受每一种完成签名。

*Mandates* 不满足时程序非良构，而不是让 `connect` 退出重载决议。用户把发送器接到不匹配的接收器上时，看到的诊断就来自这两条。

为什么要在这里才做 `transform_sender`？选哪个实现取决于两件事：前驱在哪里完成（来自发送器的属性），以及操作在哪里启动（来自接收器的环境）。调用 `then(...)` 构造发送器时还不知道后者，只有到 connect 时两者才同时可得。

## connect 的 noexcept 只能取决于环境（¶6.3–6.7）

¶6 的后半段是一条非良构、不要求诊断（IFNDR）{{ifndr}} 的规则。如果存在另一个右值接收器 `rcvr2`，满足

- ¶6.3 `decltype(rcvr2)` 模型化 `receiver`；
- ¶6.4 `noexcept(rcvr2)` 为 true；
- ¶6.5 `get_env(rcvr2)` 与 `get_env(rcvr)` 类型相同；
- ¶6.6 `noexcept(connect(sndr, rcvr))` 为 true；
- ¶6.7 `noexcept(connect(sndr, rcvr2))` 良构且为 false，

程序就非良构，不要求诊断。换句话说，`connect` 是否可能抛异常只能由接收器的环境类型决定，不能随接收器本身的类型变化。¶6.4 排除了仅仅因为求值 `rcvr2` 本身会抛而不同的情形。

注 1 说明了动机：这样在只知道环境的地方，比如 `get_completion_signatures` 内部，也能判断 `connect` 会不会抛。`let_value` 正需要这一点：connect 回调返回的发送器时如果可能抛异常，它的签名里就要多一个 `set_error_t(exception_ptr)`，而计算签名时只知道环境，不知道最终的接收器类型（[[exec.let]]）。

## 可等待体当发送器：connect-awaitable（¶3–5）

按 [[exec.snd]] 的定义，任何可等待体（能在协程里 `co_await` 的对象）都自动满足 `sender`，已有的协程 task 类型不用修改就能当发送器用。这样的类型通常没有 `connect` 成员，于是走 ¶6.2：标准写了一个协程，把 `co_await x` 变成完成时调用 `set_value(rcvr, 结果)`，协程帧本身就充当操作状态。

### 操作状态就是协程（¶4）

```cpp
struct operation-state-task {
  using operation_state_concept = operation_state_tag;
  using promise_type = connect-awaitable-promise;
  explicit operation-state-task(coroutine_handle<> h) noexcept : coro(h) {}
  operation-state-task(operation-state-task&&) = delete;
  ~operation-state-task() { coro.destroy(); }
  void start() & noexcept { coro.resume(); }
private:
  coroutine_handle<> coro;
};
```

`start` 就是恢复协程，析构就是销毁协程帧，移动构造函数被删除。

### 承诺类型（¶3）

¶3 *connect-awaitable-promise* 是这个协程的承诺类型。几个成员决定了协程的行为：

- 构造函数的形参是 `(DS&, DR& rcvr)`，和协程的形参一致。按 [[dcl.fct.def.coroutine]]，承诺类型有能用协程形参调用的构造函数时就用它构造承诺对象，于是承诺对象直接拿到协程帧里那份接收器的引用。
- `initial_suspend` 返回 `suspend_always`：协程创建后立即挂起，直到 `start` 才恢复。
- `final_suspend`、`unhandled_exception`、`return_void` 都调用 `terminate()`。协程体保证不会走到这些路径，见下一节。
- `unhandled_stopped` 对接收器调用 `set_stopped`：被等待的发送器以取消结束时走这里（[[exec.as.awaitable]]）。
- `get_env` 返回接收器的环境，所以协程里 `co_await` 的发送器能看到外部环境。

### 协程体与 suspend-complete（¶5）

```cpp
operation-state-task connect-awaitable(DS sndr, DR rcvr) requires receiver-of<DR, Sigs> {
  exception_ptr ep;
  try {
    if constexpr (same_as<V, void>) {
      co_await std::move(sndr);
      co_await suspend-complete(set_value, std::move(rcvr));
    } else {
      co_await suspend-complete(set_value, std::move(rcvr), co_await std::move(sndr));
    }
  } catch(...) {
    ep = current_exception();
  }
  co_await suspend-complete(set_error, std::move(rcvr), std::move(ep));
}
```

`V` 是 `co_await sndr` 的结果类型，`Sigs` 是 `set_value_t(V)`（`V` 为 `void` 时是 `set_value_t()`）、`set_error_t(exception_ptr)`、`set_stopped_t()` 三种签名。

完成函数不是直接调用的，而是包在 *suspend-complete* 返回的等待体里：它的 `await_ready` 返回 false，于是协程先挂起，然后在 `await_suspend` 里调用 `set_value` 或 `set_error`。`await_resume` 标为 `unreachable()`，协程永远不会从这里恢复。

先挂起再完成，是因为 [[exec.async.ops#8]] 允许接收器在完成函数里销毁操作状态，也就是销毁这个协程帧。而 `destroy` 的前置条件是协程处于挂起状态（[[coroutine.handle.resumption#4]]）。下面的程序模拟了这个过程，在 AddressSanitizer 下运行没有报错：

```cpp run ok
#include <coroutine>
#include <cstdio>
#include <exception>

struct task {
  struct promise_type {
    task get_return_object() {
      return {std::coroutine_handle<promise_type>::from_promise(*this)};
    }
    std::suspend_always initial_suspend() noexcept { return {}; }
    std::suspend_always final_suspend() noexcept { std::terminate(); }
    void return_void() { std::terminate(); }
    void unhandled_exception() { std::terminate(); }
  };
  std::coroutine_handle<> h;
};

struct complete_then_destroy {
  bool await_ready() noexcept { return false; }
  void await_suspend(std::coroutine_handle<> h) noexcept {
    std::puts("set_value");   // 相当于调用接收器的完成函数
    h.destroy();              // OK：协程此时已挂起
  }
  [[noreturn]] void await_resume() noexcept { std::terminate(); }
};

task op() { co_await complete_then_destroy{}; }

int main() {
  task t = op();   // 惰性：initial_suspend 挂起
  t.h.resume();    // 相当于 start(op)
  std::puts("done");
}
```

*suspend-complete* 内的 lambda 按引用捕获实参 `as`。在 `co_await suspend-complete(set_value, std::move(rcvr), co_await std::move(sndr))` 中，内层 `co_await` 的结果是一个临时对象，它要到所在的完整表达式结束时才销毁。外层 `co_await` 挂起时这个完整表达式还没有结束，所以引用一直有效。

!!! lawyer "为什么 set_error 写在 try 块外面"
    `co_await` 不能出现在异常处理块（handler）里（[[expr.await#2]]），所以 `catch` 块只能先把异常存进 `ep`，离开之后再 `co_await suspend-complete(set_error, ...)`。如果 `try` 块正常执行，协程会在 `set_value` 那一处挂起并且永不恢复，因此不会走到最后一行。

## 思考题

!!! question "1. 一个 std::suspend_always 能被 connect 吗？"
    `std::suspend_always` 是可等待体。`sync_wait(std::suspend_always{})` 会发生什么？

<details markdown="1">
<summary>答案</summary>

它满足 `sender`，签名是 `set_value_t()`、`set_error_t(exception_ptr)`、`set_stopped_t()`。connect 走 *connect-awaitable*：协程 `co_await suspend_always{}` 挂起，而 `suspend_always::await_suspend` 什么也不做，没有任何人会恢复这个协程，操作永远不完成。`sync_wait` 驱动的 `run_loop` 一直等不到完成，`sync_wait` 永远阻塞。

类型上这完全合法，但违反了 [[exec.async.ops#2]] 启动后终将完成的要求。可等待体自动成为发送器，不代表每个可等待体都是有意义的发送器。
</details>

!!! question "2. connect 的 Mandates 和 sender-to 有什么区别？"
    阐述用概念 *sender-to*<Sndr, Rcvr>（[[exec.snd]]）已经包含了 `sender_in` 和 *receiver-of*。为什么 `connect` 还要单独写 *Mandates*？

<details markdown="1">
<summary>答案</summary>

*sender-to* 是概念，用在约束里时不满足只会让 `requires` 为 false 或让函数退出重载决议，不会报错。`connect` 的 *Mandates* 保证：只要有人直接写了 `connect(s, r)` 而两者不匹配，程序就非良构，实现必须给出诊断。
</details>
