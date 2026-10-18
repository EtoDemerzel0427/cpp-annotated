---
title: 停止令牌
summary: 协作式取消的规范模型——停止状态、stoppable_token 等概念的语义要求、回调注册/注销的精确规则（回调在哪个线程执行、注销何时阻塞、能否在回调里销毁自己）、request_stop 与 stop_requested 之间的同步，以及 C++26 的 never_stop_token 与 inplace_stop_* 系列
status: done
covers: *
papers: P0660R10, P2300R10
related: thread.threads, thread.condition, intro.races, basic.life, exec
tags: 标准库, 并发, 取消, stop_token
updated: 2026-10-18
---

C++20 之前，标准库没有"让另一个线程停下来"的统一手段。`std::thread` 没有 `interrupt()`；每个项目都自己写一个 `atomic<bool> stop_flag`，再在条件变量等待处想办法把线程唤醒。[thread.stoptoken] 把这个模式标准化为三个角色：

- **停止源**（`stop_source`）：发出停止请求的一方；
- **停止令牌**（`stop_token`）：被取消的一方用来**轮询**"有没有人要求我停"；
- **停止回调**（`stop_callback`）：被取消的一方**注册**一个函数，停止请求一到就被调用（例如用来唤醒阻塞中的等待）。

三者通过一个共享的**停止状态**（[[g:stop-state]]，stop state）联系起来。这是**协作式**取消：没有任何东西会强行终止线程，被取消的代码必须自己检查令牌或注册回调。

本页覆盖 [thread.stoptoken] 的全部 10 个三级条款。重点在 [stoptoken.concepts]：C++26 起，`stop_token` 的语义要求被抽象为概念 `stoppable_token` 与仅说明用的 *stoppable-source*、*stoppable-callback-for*，具体类只是这些概念的模型。

## 导论（[thread.stoptoken.intro]）

¶1 本子条款描述的组件可以用来**异步地**请求某个操作及时停止执行，典型原因是结果已经不再需要。这样的请求称为**停止请求**（[[g:stop-request]]，stop request）。

¶2 概念 *stoppable-source*、`stoppable_token`、*stoppable-callback-for* 规定了对停止状态的共享访问的语法与语义。指向同一停止状态的这些对象互称**关联的**（associated）。

¶3 满足 `stoppable_token` 的对象可以传给某个操作，该操作可以

- ¶3.1 主动轮询令牌，检查是否有停止请求；或
- ¶3.2 注册一个回调，在停止请求发出时被调用。

通过停止源发出的停止请求对所有关联的令牌与停止源**可见**。**停止请求一旦发出就不能撤回**，之后的停止请求不起作用。

¶4 通过 *stoppable-callback-for* 注册的回调，在任一关联停止源**第一次**发出停止请求时被调用。

¶5 `stop_source`、`stop_token`、`stop_callback` 实现停止状态的**共享所有权**：最后一个所有者释放与停止状态关联的资源。这就是为什么 `stop_token` 可以比创建它的 `stop_source` 活得更久。

¶6 `inplace_stop_source` 是其停止状态的**唯一**所有者；`inplace_stop_token` 与 `inplace_stop_callback` 不参与所有权。注 1：它们用于所有令牌与回调的使用都确定嵌套在 `inplace_stop_source` 生命周期之内的场合。代价是不再有引用计数和堆分配——这正是 [[exec]]（发送者/接收者框架）需要的。

## 头文件概要（[thread.stoptoken.syn]）

`<stop_token>` 声明：三个概念（其中两个仅说明用）、`stop_token`、`stop_source`、`nostopstate_t`/`nostopstate`、`stop_callback`、`never_stop_token`、`inplace_stop_token`、`inplace_stop_source`、`inplace_stop_callback`，以及别名模板 `stop_callback_for_t<T, CallbackFn>`（即 `T::template callback_type<CallbackFn>`）——每种令牌类型通过成员别名模板 `callback_type` 告诉泛型代码"配套的回调类型是什么"。

## 概念与语义（[stoptoken.concepts]）

### stoppable-callback-for：注册与注销（¶1–¶3）

¶1 仅说明用的概念 *stoppable-callback-for*`<CallbackFn, Token, Initializer>` 检查回调类型与令牌是否配套：`CallbackFn` 可调用、可从 `Initializer` 构造，`stop_callback_for_t<Token, CallbackFn>`（记作 SCB）存在且可从 `(const Token&, Initializer)` 构造。

¶2–¶3 规定了它被**实现**（modeled）的条件。这是整页最关键的规则，逐项看：

¶3.1 SCB 必须可以从 `Token`、`Token&`、`const Token` 加 `Initializer` 构造。

¶3.2 每个 SCB 对象 `scb` 有一个关联的回调函数 `callback_fn`（类型为 `CallbackFn`）。用令牌 `t` 和初始化器 `init` 直接非列表初始化 `scb`，执行**可停止回调注册**（stoppable callback registration）：

- ¶3.2.1 若 `t.stop_possible()` 为 `true`：
    - ¶3.2.1.1 用 `init` 直接初始化 `callback_fn`；
    - ¶3.2.1.2 构造 `scb` 只能抛出初始化 `callback_fn` 时抛出的异常——注册本身不能失败；
    - ¶3.2.1.3 把调用 `std::forward<CallbackFn>(callback_fn)()` 注册到 `t` 的停止状态：
        - ¶3.2.1.3.1 若注册时 `t.stop_requested()` 为 `false`，就把它加入停止状态的回调列表，在停止请求发出时被求值；
        - ¶3.2.1.3.2 **否则**，在**执行 `scb` 构造函数的线程上立即求值**，且不加入列表。

  若回调被加入了列表，`scb` 就与该停止状态关联。注 1：若 `t.stop_possible()` 为 `false`，不要求初始化 `callback_fn`。

由此得到回调在**哪个线程**上执行的完整答案：

| 情况 | 回调在哪里执行 |
|---|---|
| 注册时尚未请求停止，之后某线程调用 `request_stop()` | **调用 `request_stop()` 的线程**，在 `request_stop()` 内部同步执行（¶12） |
| 注册时已经请求过停止 | **构造 `stop_callback` 的线程**，在构造函数内部立即执行 |
| 令牌 `stop_possible()` 为 `false` | 永远不执行 |

```cpp run title="callback-thread.cpp" ok
#include <cstdio>
#include <stop_token>
#include <thread>

int main() {
  std::stop_source src;
  auto main_id = std::this_thread::get_id();

  // 1. 先注册、后请求：回调在调用 request_stop 的线程上执行
  std::stop_callback cb1(src.get_token(), [&] {
    std::puts(std::this_thread::get_id() == main_id ? "cb1: main" : "cb1: worker");
  });
  std::thread t([&] { src.request_stop(); });
  t.join();

  // 2. 已经请求过停止，再注册：回调在构造 stop_callback 的线程上立即执行
  std::stop_callback cb2(src.get_token(), [&] {
    std::puts(std::this_thread::get_id() == main_id ? "cb2: main" : "cb2: worker");
  });
  std::printf("second request_stop returns %d\n", src.request_stop());
}
```

输出 `cb1: worker`、`cb2: main`、`second request_stop returns 0`。最后一行对应 ¶3："之后的停止请求不起作用"，`request_stop` 返回 `false`（¶12）。

¶3.3 销毁 `scb` 执行**可停止回调注销**（stoppable callback deregistration），按顺序：

- ¶3.3.1 若构造时没有注册回调，注销除了销毁（已构造的）`callback_fn` 外没有效果；
- ¶3.3.2 否则，把回调从停止状态中移除；
- ¶3.3.3 若 `callback_fn` **正在另一个线程上执行**，注销**阻塞**（[[defns.block]]），直到该调用返回，使得回调的返回 **strongly happens before** `callback_fn` 的销毁；
- ¶3.3.4 若 `callback_fn` 正在**当前线程**上执行（即回调里销毁了自己的 `stop_callback`），析构函数**不得**阻塞等待回调返回——否则就是自己等自己，必然死锁；
- ¶3.3.5 注销不得阻塞于同一停止状态上**其他**回调的完成；
- ¶3.3.6 注销销毁 `callback_fn`。

¶3.3.3 是 `stop_callback` 能安全使用的根本保证：析构函数返回后，你可以放心销毁回调引用的任何东西。

```cpp run title="deregister-blocks.cpp" ok
#include <atomic>
#include <chrono>
#include <cstdio>
#include <functional>
#include <optional>
#include <stop_token>
#include <thread>
using namespace std::chrono_literals;

int main() {
  std::stop_source src;
  std::atomic<bool> entered{false};
  std::optional<std::stop_callback<std::function<void()>>> cb;
  int resource = 1;                                  // 回调要用的资源
  cb.emplace(src.get_token(), [&] {
    entered = true;
    std::this_thread::sleep_for(100ms);
    std::printf("callback uses resource = %d\n", resource);
  });
  std::jthread requester([&] { src.request_stop(); });   // 回调在 requester 线程上运行
  while (!entered) {}
  cb.reset();         // 注销：回调正在另一个线程执行，析构函数阻塞直到回调返回
  resource = 0;       // OK：回调的返回 strongly happens before 回调对象的销毁
  std::puts("deregistered");
}
```

输出总是先 `callback uses resource = 1` 再 `deregistered`，且 ThreadSanitizer 不报告竞争。

¶3.3.4 允许在回调里销毁自己：

```cpp run title="self-deregister.cpp" ok
#include <cstdio>
#include <functional>
#include <optional>
#include <stop_token>

int main() {
  std::stop_source src;
  std::optional<std::stop_callback<std::function<void()>>> cb;
  cb.emplace(src.get_token(), [&] {
    std::puts("in callback");
    cb.reset();       // 在回调内部注销自己：析构函数不等待（¶3.3.4）
    // 此后不得再访问 lambda 的捕获——它们随 callback_fn 一起被销毁了
    std::puts("after self-deregistration");
  });
  src.request_stop();
}
```

### stoppable_token 与 unstoppable_token（¶4–¶7）

¶4 `stoppable_token<Token>` 检查令牌的基本接口：成员别名模板 `callback_type` 存在；`stop_requested()`、`stop_possible()` 是 `noexcept` 且返回 `bool`；复制构造 `noexcept`；`copyable` 且 `equality_comparable`。`unstoppable_token` 额外要求 `!tok.stop_possible()` 是**常量表达式**且为 `true`——即"编译期就知道永远不会停"，泛型代码可以据此完全省掉取消逻辑。

¶5 满足 `stoppable_token` 的对象最多有一个关联的逻辑停止状态；没有停止状态的令牌称为**脱离的**（disengaged）。

¶6–¶7 语义要求（设 `t`、`u` 是引用同一停止状态的不同令牌，SP 是一次结果为 `false` 的 `t.stop_possible()` 求值，SR 是一次结果为 `true` 的 `t.stop_requested()` 求值）：

- ¶7.1 在 SP **之后发生**（happens after）的 `u.stop_possible()` 或 `u.stop_requested()` 求值都为 `false`——"不可能停"是单调的；
- ¶7.2 在 SR 之后发生的这两个求值都为 `true`——"已请求停止"是单调的；
- ¶7.3 对任何满足 *stoppable-callback-for* 的回调类型，该概念被实现（即上面的注册/注销规则成立）；
- ¶7.4 脱离的令牌，两个查询都为 `false`；
- ¶7.5 `t == u` 当且仅当它们引用同一停止状态或都脱离。

### stoppable-source（¶8–¶12）

¶8 仅说明用的 *stoppable-source*：可查询 `stop_requested`、`stop_possible`，是关联令牌的工厂（`get_token`），可以 `request_stop`，维护回调列表并在**第一次**停止请求时执行它们。

¶9–¶10 脱离的停止源两个查询都为 `false`，`get_token()` 返回脱离的令牌。

¶11 是本节的**同步规则**：

!!! std
    A call to `request_stop` that returns `true` synchronizes with a call to `stop_requested` on an associated `stoppable_token` or *stoppable-source* object that returns `true`. Registration of a callback synchronizes with the invocation of that callback.

    返回 `true` 的 `request_stop` 调用，与关联对象上返回 `true` 的 `stop_requested` 调用同步；回调的注册与该回调的调用同步。

此外，这些成员函数的并发调用**不引入数据竞争**。

第一句的实际意义：发出停止请求的线程在 `request_stop()` **之前**写入的数据（比如"取消原因"），对任何观察到 `stop_requested() == true` 的线程可见。第二句保证：构造 `stop_callback` 之前写入的、回调要用的数据，在回调（可能在另一个线程上）执行时可见。

注意第一句**不**覆盖返回 `false` 的 `request_stop`：第二次调用 `request_stop` 什么也不同步。

¶12 定义**停止请求操作**：若停止源脱离，`request_stop` 无效果，返回 `false`。否则：

- 判断停止状态是否已收到停止请求，若没有就发出——"判断与发出必须**原子地**进行，如同一个读-改-写操作（[[intro.races]]）"，所以多个线程同时 `request_stop()`，恰好一个返回 `true`；
- 若这次发出了请求，就**同步地**执行停止状态里登记的回调；
- 回调以异常退出，调用 `std::terminate`——这里没有其他选择，因为 `request_stop` 是 `noexcept` 的；
- 注 2：回调的执行**顺序不受约束**；
- 返回 `true` 当且仅当这次调用发出了请求；
- 调用之后，`stop_possible()` 为 `false` 或 `stop_requested()` 为 `true`；
- 注 3：停止请求包括通知所有在**可中断等待**中临时注册的 `condition_variable_any`（[[thread.condition]]）。

## stop_token（[stoptoken]）

[stoptoken.general] ¶1：`stop_token` 实现 `stoppable_token`，与其关联的 `stop_source` 及所有与它相等的 `stop_token` **共享**停止状态的所有权。类定义里的仅说明用成员是 `shared_ptr<unspecified> stop-state`；¶2：它为空时令牌脱离。`callback_type<F>` 是 `stop_callback<F>`。

[stoptoken.mem]：

- ¶1 `swap` 交换停止状态指针；
- ¶2 `stop_requested()`：停止状态已收到停止请求时为 `true`；
- ¶3 `stop_possible()`：令牌脱离，**或**"没有发出过停止请求**且**已没有关联的 `stop_source`"时为 `false`，否则为 `true`。

¶3.2 意味着 `stop_possible()` 的值会随 `stop_source` 的销毁而变化：所有停止源都销毁了、又从没请求过停止，那就永远不会有人请求了。

```cpp run title="stop-possible.cpp" ok
#include <cassert>
#include <stop_token>

int main() {
  std::stop_token tok;
  assert(!tok.stop_possible());                 // 默认构造：脱离
  {
    std::stop_source src;
    tok = src.get_token();
    assert(tok.stop_possible() && !tok.stop_requested());
  }                                             // 最后一个 stop_source 销毁，且从未请求停止
  assert(!tok.stop_possible());                 // ¶3.2
  {
    std::stop_source src;
    tok = src.get_token();
    src.request_stop();
  }
  assert(tok.stop_possible() && tok.stop_requested());   // 已请求过：仍"可能"（且已经）停止
}
```

## stop_source（[stopsource]）

[stopsource.general]：类似地持有 `shared_ptr<unspecified> stop-state`；¶2 它实现 *stoppable-source*、`copyable`、`equality_comparable`、`swappable`。复制 `stop_source` 得到的是**同一个**停止状态的另一个所有者，不是新的停止状态。

[stopsource.cons]：

- 默认构造函数 ¶1–¶3：**分配一个新的停止状态**，之后 `stop_possible()` 为 `true`；分配失败抛 `bad_alloc`。所以 `stop_source` 的默认构造函数**不是** `noexcept`。
- `explicit stop_source(nostopstate_t) noexcept`：构造一个脱离的停止源，不分配。需要"稍后再决定"或作为成员占位时用它。

[stopsource.mem]：`get_token()`（¶2：脱离时返回脱离令牌）、`stop_possible()`（¶3：就是"有没有停止状态"）、`stop_requested()`（¶4）、`request_stop()`（¶5：执行停止请求操作）。

## stop_callback（[stopcallback]）

[stopcallback.general] ¶1 给出类定义：不可复制、不可移动（因为它的地址登记在停止状态的回调列表里）；有推导指引 `stop_callback(stop_token, CallbackFn) -> stop_callback<CallbackFn>`。

- ¶2 *Mandates*：`CallbackFn` 满足 `invocable` 与 `destructible`；
- ¶3 对任何使 *stoppable-callback-for*`<CallbackFn, stop_token, Initializer>` 被满足的 `Initializer`，该概念被实现——也就是说 ¶3.2、¶3.3 的注册/注销规则对 `stop_callback` 成立。

[stopcallback.cons]：

- ¶1–¶2 构造函数（接受 `const stop_token&` 或 `stop_token&&`）：用 `init` 初始化 `callback-fn`，执行注册；若回调登记到了停止状态，`*this` 获得该停止状态的共享所有权。`noexcept` 与否取决于 `CallbackFn` 从 `Initializer` 的构造是否 `noexcept`。
- ¶3 析构函数：执行注销，释放所有权。

注意回调是以 `std::forward<CallbackFn>(callback_fn)()` 调用的：`CallbackFn` 是非引用类型时，回调作为**右值**被调用，所以只有 `operator() &&` 的函数对象也能用。

## never_stop_token（[stoptoken.never]） {{c++26}}

¶1 `never_stop_token` 实现 `unstoppable_token`：两个查询都是 `static constexpr` 且返回 `false`；它的 `callback_type` 是一个什么都不做的类型，构造函数直接丢弃初始化器。泛型异步代码（[[exec]]）可以用 `unstoppable_token<decltype(tok)>` 在编译期判断"根本不需要取消支持"，从而零开销。

## inplace_stop_token / inplace_stop_source / inplace_stop_callback {{c++26}}

这三个类（[stoptoken.inplace]、[stopsource.inplace]、[stopcallback.inplace]）与 `stop_*` 的语义相同，区别全在所有权：

| | `stop_source` 系列 | `inplace_stop_source` 系列 |
|---|---|---|
| 停止状态存放在 | 堆上，引用计数 | `inplace_stop_source` 对象**内部** |
| 停止源可复制/移动 | 可复制 | 都不可以（地址就是身份） |
| 令牌持有 | `shared_ptr` | 一个 `const inplace_stop_source*` |
| 停止源默认构造 | 可能抛 `bad_alloc` | `constexpr`、`noexcept` |
| `stop_possible()` | 取决于状态 | 停止源上是 `static constexpr` 的 `true`；令牌上是"指针非空" |
| 令牌活得比停止源久 | 安全 | **UB** |

[stoptoken.inplace.mem] 的两个注把最后一行说清楚了：

- ¶3 注 1：按 [[basic.life]]，除非 `stop_requested()` 的调用 **strongly happens before** 关联 `inplace_stop_source` 析构函数的开始，否则行为未定义 {{ub}}；
- ¶5 注 2：按 [[basic.stc.general]]，`stop_possible()` 只看指针是否为空，不解引用，所以只要求在停止源的**存储期**结束之前调用；否则其行为由实现定义 {{impl}}（使用无效指针值，见 [[basic.compound]]）。

[stopsource.inplace.mem] ¶3–¶4：`request_stop()` 执行停止请求操作，之后 `stop_requested()` 为 `true`。`inplace_stop_callback`（[stopcallback.inplace]）¶2 同样声明 *stoppable-callback-for* 被实现。

!!! impl "libc++ 尚未提供"
    截至 Clang 23 自带的 libc++，`<stop_token>` 里没有 `never_stop_token`、`inplace_stop_token`、`inplace_stop_source`、`inplace_stop_callback`，也没有 `stoppable_token` 概念（`__cpp_lib_senders` 未定义）。本节内容未经本地编译验证。

## 实现视角

!!! impl "libc++ 的停止状态（`<__stop_token/stop_state.h>`）"
    - 停止状态是一个侵入式引用计数对象，含两个 `atomic<uint32_t>`：一个是引用计数（`stop_token` + `stop_source` + 已登记的 `stop_callback`），另一个把三样东西打包在一起——bit 0 "已请求停止"、bit 1 "回调列表上锁"、其余位是 `stop_source` 的计数（用于 `stop_token::stop_possible`）。所以 `sizeof(std::stop_token) == sizeof(std::stop_source) == 8`。
    - 回调列表是侵入式双向链表，节点就是 `stop_callback` 对象本身，因此 `stop_callback` 不可移动。
    - `request_stop` 用一次 `acq_rel` 的 CAS 同时设置"已请求"和"上锁"两个位：release 半边对应 ¶11 第一句（与 `stop_requested` 里的 acquire load 配对），acquire 半边对应第二句（看到注册时写入的数据）。
    - 执行每个回调前会**先解锁列表**，使其他线程此时注销别的回调不必等待（¶3.3.5）。它记录发出请求的线程 id：注销时若发现回调可能正在执行，且当前线程不是请求线程，就在回调节点里的一个 `atomic<bool>` 上 `wait`，等请求线程执行完回调后 `store(true, release)` + `notify_all`——这就是 ¶3.3.3 的阻塞；若是同一线程（在回调里销毁自己），则只设置一个标志告诉请求线程"这个节点已经没了"，不阻塞（¶3.3.4）。

## 陷阱

!!! pitfall "回调里不要去拿发出请求者可能持有的锁"
    回调在 `request_stop()` 内部、在请求线程上同步执行。若线程 A 持有互斥量 `m` 调用 `request_stop()`，而某个回调也要锁 `m`，就死锁了。反过来，若线程 B 持有 `m` 去销毁一个正在 A 上执行、且要锁 `m` 的回调，B 会在 ¶3.3.3 处阻塞等待回调，回调等待 `m`——同样死锁。回调应当短小、不加锁或只加专用的锁，典型做法是只调用 `cv.notify_all()` 或设置一个原子标志。

!!! pitfall "回调抛异常会直接 terminate"
    ¶12：在 `request_stop` 中执行的回调以异常退出时调用 `std::terminate`。注册时立即执行的情况（¶3.2.1.3.2）没有单独规定，但 ¶3.2.1.2 只允许构造函数抛出**初始化** `callback_fn` 时的异常，回调本身的异常不得传出构造函数。libc++ 把回调的调用包在一个 `noexcept` 函数里，所以两种情况下都是 `std::terminate`。

!!! pitfall "stop_token 不会让阻塞调用自动返回"
    `stop_token` 只是一个标志。线程阻塞在 `std::condition_variable::wait`、`read()` 系统调用、`future::get()` 里时，发出停止请求**不会**唤醒它。标准库中只有 `condition_variable_any` 的可中断等待（[[thread.condition]]）原生支持停止令牌；其他地方需要你自己注册 `stop_callback` 去打断阻塞（例如关闭 socket、`notify_all`）。

## 思考题

!!! question "1. 两个线程同时对同一个 `stop_source` 调用 `request_stop()`，回调会执行几次？在哪个线程？"

<details markdown="1">
<summary>答案</summary>

每个回调恰好执行一次。¶12 要求"判断并发出请求"如同一个原子读-改-写，所以恰好一个调用返回 `true`，回调在**那个**线程上同步执行。另一个调用返回 `false`，且注意：它可能在回调还没执行完时就返回了——返回 `false` 的 `request_stop` 不等待回调，也不建立任何同步（¶11 只说返回 `true` 的调用）。
</details>

!!! question "2. `stop_callback` 的构造函数和析构函数都可能阻塞吗？"

<details markdown="1">
<summary>答案</summary>

析构函数可能阻塞：¶3.3.3，回调正在另一个线程上执行时，要等它返回。构造函数的规范没有"阻塞"的措辞，但若注册时已请求停止，回调会在构造函数里**同步执行**（¶3.2.1.3.2），所以构造函数的耗时包含回调的执行时间；实现为了操作回调列表也可能短暂地自旋等待列表锁。
</details>

!!! question "3. 为什么 `inplace_stop_token::stop_possible()` 在停止源析构后调用是实现定义而不是 UB？"

<details markdown="1">
<summary>答案</summary>

`stop_possible()` 被规定为返回 `stop-source != nullptr`（[stoptoken.inplace.mem] ¶4），只是把指针与空指针比较，并不访问它指向的对象，所以不触及 [[basic.life]] 的"在生命周期外访问对象"。但停止源存储期结束后，指针值成为**无效指针值**，而按 [[basic.stc.general]]，除了间接访问和传给释放函数之外，对无效指针值的其他使用（包括比较）是实现定义的。存储期结束之前、生命周期结束之后调用则完全有定义。
</details>

## 小结

| 问题 | 答案 | 出处 |
|---|---|---|
| 回调在哪个线程执行？ | 已请求停止：构造 `stop_callback` 的线程；否则：发出请求的线程 | ¶3.2.1.3 |
| 回调执行几次？ | 最多一次；只在**第一次**停止请求时 | ¶4、¶12 |
| `request_stop` 建立什么同步？ | 返回 `true` 的调用 sync-with 返回 `true` 的 `stop_requested`；注册 sync-with 调用 | ¶11 |
| 析构 `stop_callback` 会等回调吗？ | 回调在别的线程执行时会等；在本线程（回调内自毁）时不等 | ¶3.3.3–¶3.3.4 |
| 回调抛异常？ | `std::terminate` | ¶12 |
| 令牌能比停止源活得久吗？ | `stop_token` 可以（共享所有权）；`inplace_stop_token` 不行 | ¶5–¶6 |
