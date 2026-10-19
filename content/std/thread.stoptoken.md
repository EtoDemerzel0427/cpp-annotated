---
title: 停止令牌
summary: 标准库的协作式取消：stop_source 发出停止请求，stop_token 供被取消的代码查询，stop_callback 在请求到来时运行；回调在哪个线程执行、析构何时阻塞、建立什么同步，以及 C++26 的 never_stop_token 和 inplace_stop_* 系列。
status: done
covers: *
papers: P0660R10, P2300R10
related: thread.threads, thread.condition, intro.races, basic.life, exec
tags: 标准库, 并发, 取消, stop_token
updated: 2026-10-19
---

!!! tldr
    - 取消是协作式的：停止请求只是设置一个标志，被取消的代码要自己查询 `stop_token` 或注册 `stop_callback`。
    - 回调在第一次停止请求时执行，在调用 `request_stop()` 的线程上同步运行；注册时已经请求过停止，就在构造 `stop_callback` 的线程上立即运行。
    - `stop_callback` 析构时，如果回调正在另一个线程上执行，析构函数会等它返回；回调内部销毁自己则不会等待。
    - 返回 `true` 的 `request_stop()` 与看到 `stop_requested() == true` 的查询同步，所以请求前写入的数据对观察到请求的线程可见。
    - `stop_token` 共享停止状态的所有权，可以比 `stop_source` 活得久；C++26 的 `inplace_stop_token` 不拥有状态，不能比它的停止源活得久。

## 三个角色 [thread.stoptoken.intro]

```cpp run title="cancel.cpp" ok
#include <chrono>
#include <cstdio>
#include <stop_token>
#include <thread>
using namespace std::chrono_literals;

void work(std::stop_token st) {
  int n = 0;
  while (!st.stop_requested()) {     // 轮询
    ++n;
    std::this_thread::sleep_for(1ms);
  }
  std::printf("stopped after %s\n", n > 0 ? "some work" : "no work");
}

int main() {
  std::stop_source src;
  std::stop_callback cb(src.get_token(), [] { std::puts("callback"); });
  std::thread t(work, src.get_token());
  std::this_thread::sleep_for(20ms);
  src.request_stop();                 // 先运行 cb，再返回
  t.join();
}
```

C++20 之前，让另一个线程停下来的常见做法是自己写一个 `atomic<bool>` 标志。[thread.stoptoken] 把这个模式标准化为三个类：

- `stop_source`（停止源）发出**停止请求**（[[g:stop-request]]，stop request）。停止请求的典型原因是操作的结果已经不再需要（¶1）。
- `stop_token`（停止令牌）交给被取消的代码，用来轮询是否有人请求了停止。
- `stop_callback`（停止回调）登记一个函数，停止请求到来时执行，常用来唤醒阻塞中的等待。

¶3 它们通过同一个**停止状态**（[[g:stop-state]]，stop state）联系起来，指向同一停止状态的对象互称**关联的**（associated，¶2）。通过停止源发出的请求，对所有关联的令牌和停止源可见。请求一旦发出就不能撤回，之后再请求没有效果。

这是协作式取消。没有任何机制会强行终止线程，被取消的代码必须自己检查令牌，或者注册回调。

!!! pitfall "停止请求不会让阻塞调用自动返回"
    线程阻塞在 `std::condition_variable::wait`、`read()` 系统调用或 `future::get()` 里时，停止请求不会唤醒它。标准库中原生支持停止令牌的只有 `condition_variable_any` 的可中断等待（[[thread.condition]]）。其他情况要自己注册 `stop_callback`，在回调里关闭 socket 或 `notify_all`。

## 回调在哪里执行 [stoptoken.concepts]

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

本机输出 `cb1: worker`、`cb2: main`、`second request_stop returns 0`。

### 注册（¶3.2）

C++26 起，这些规则写在 [stoptoken.concepts] 的仅说明用概念 *stoppable-callback-for* 里，`stop_callback` 和 `inplace_stop_callback` 都要满足它。设回调对象 `scb` 用令牌 `t` 和初始化器 `init` 构造，`callback_fn` 是它保存的函数对象。¶3.2 规定构造时执行一次**可停止回调注册**（stoppable callback registration）：

- ¶3.2.1 如果 `t.stop_possible()` 为 `true`，先用 `init` 直接初始化 `callback_fn`。构造函数只能抛出这次初始化抛出的异常，注册本身不能失败（¶3.2.1.2）。
- ¶3.2.1.3.1 如果注册时还没有停止请求，就把 `std::forward<CallbackFn>(callback_fn)()` 这次调用加入停止状态的回调列表，等停止请求时执行。
- ¶3.2.1.3.2 否则在执行构造函数的线程上立即调用它，不加入列表。
- 注 1：如果 `t.stop_possible()` 为 `false`，标准不要求初始化 `callback_fn`。

[[thread.stoptoken.intro#4]] 规定，回调只在任一关联停止源第一次发出停止请求时执行。¶12 规定，发出请求的那次 `request_stop()` 在返回之前，在自己的线程上同步执行列表里的所有回调。注 2 说明这些回调的执行顺序不受约束。合起来：

| 情况 | 回调在哪里执行 |
|---|---|
| 注册时尚未请求停止 | 之后第一次调用 `request_stop()` 的线程，在 `request_stop()` 内部 |
| 注册时已经请求过停止 | 构造 `stop_callback` 的线程，在构造函数内部 |
| `t.stop_possible()` 为 `false` | 永远不执行 |

回调是以 `std::forward<CallbackFn>(callback_fn)()` 调用的。`CallbackFn` 不是引用类型时，回调作为右值被调用，所以只提供 `operator() &&` 的函数对象也可以用。

!!! pitfall "回调抛异常会直接 terminate"
    ¶12 规定回调在 `request_stop` 中以异常退出时调用 `std::terminate`，因为 `request_stop` 是 `noexcept` 的。注册时立即执行的情形没有单独规定，但 ¶3.2.1.2 只允许构造函数抛出初始化 `callback_fn` 时的异常。libc++ 把回调的调用包在一个 `noexcept` 函数里，两种情形下都是 `std::terminate`。

### 注销（¶3.3）

¶3.3 销毁 `scb` 执行**可停止回调注销**（stoppable callback deregistration），按顺序：

- ¶3.3.1 构造时没有注册回调的，除了销毁已构造的 `callback_fn` 之外没有其他效果；
- ¶3.3.2 否则把回调从停止状态中移除；
- ¶3.3.3 如果 `callback_fn` 正在另一个线程上执行，注销阻塞（[[defns.block]]）到这次调用返回，使回调的返回 strongly happens before `callback_fn` 的销毁；
- ¶3.3.4 如果 `callback_fn` 正在当前线程上执行，也就是回调里销毁了自己的 `stop_callback`，析构函数不得等待回调返回，否则就是自己等自己；
- ¶3.3.5 注销不得等待同一停止状态上其他回调执行完毕；
- ¶3.3.6 最后销毁 `callback_fn`。

¶3.3.3 让 `stop_callback` 可以安全使用：析构函数返回之后，回调引用的东西都可以销毁了。

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
  cb.reset();         // 回调正在另一个线程执行：析构函数阻塞到它返回
  resource = 0;       // OK：回调的返回 strongly happens before 回调对象的销毁
  std::puts("deregistered");
}
```

本机总是先输出 `callback uses resource = 1` 再输出 `deregistered`，ThreadSanitizer 不报告数据竞争。

按 ¶3.3.4，回调可以在内部销毁自己：

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
    cb.reset();       // 在回调内部注销自己：析构函数不等待
    // 此后不得再访问 lambda 的捕获，它们随 callback_fn 一起被销毁了
    std::puts("after self-deregistration");
  });
  src.request_stop();
}
```

!!! pitfall "回调里不要去拿请求者可能持有的锁"
    回调在请求线程上、在 `request_stop()` 内部执行。线程 A 持有互斥量 `m` 调用 `request_stop()`，而某个回调也要锁 `m`，就会死锁。反过来，线程 B 持有 `m` 去销毁一个正在 A 上执行、且要锁 `m` 的回调，B 按 ¶3.3.3 等回调返回，回调等 `m`，同样死锁。回调应当短小，通常只调用 `cv.notify_all()` 或设置一个原子标志。

## 同步与原子性（¶11–¶12）

!!! std
    A call to `request_stop` that returns `true` synchronizes with a call to `stop_requested` on an associated `stoppable_token` or *stoppable-source* object that returns `true`. Registration of a callback synchronizes with the invocation of that callback.

¶11 返回 `true` 的 `request_stop`，与关联对象上返回 `true` 的 `stop_requested` 同步；回调的注册与该回调的调用同步。此外，这些成员函数的并发调用不会引入数据竞争。

第一句的意思是，发出请求的线程在 `request_stop()` 之前写入的数据，例如取消原因，对任何看到 `stop_requested() == true` 的线程可见。第二句的意思是，构造 `stop_callback` 之前写入的、回调要用的数据，在回调执行时可见，即使回调在另一个线程上运行。返回 `false` 的 `request_stop` 不在第一句之内，它什么也不同步。

¶12 规定**停止请求操作**：停止源没有停止状态时，`request_stop` 没有效果并返回 `false`。否则，判断是否已收到请求、没有就发出请求，这两步必须如同一个读-改-写操作那样原子地进行（[[intro.races]]），所以多个线程同时 `request_stop()`，恰好一个返回 `true`。之后同步执行回调（见上文），返回值表示这次调用是否发出了请求。注 3：停止请求还包括通知所有在可中断等待中临时登记的 `condition_variable_any`（[[thread.condition]]）。

## stop_token、stop_source、stop_callback

[[thread.stoptoken.intro#5]] 规定这三者实现停止状态的共享所有权，最后一个所有者释放停止状态。

**stop_token**（[stoptoken]）内部是一个 `shared_ptr` 指向停止状态，为空时令牌是**脱离的**（disengaged）。`callback_type<F>` 是 `stop_callback<F>`。[stoptoken.mem] ¶3 规定 `stop_possible()` 在两种情况下为 `false`：令牌脱离；或者从没有发出过停止请求，而且已经没有关联的 `stop_source`。后一种情况下再也不会有人请求停止了。

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
  assert(!tok.stop_possible());
  {
    std::stop_source src;
    tok = src.get_token();
    src.request_stop();
  }
  assert(tok.stop_possible() && tok.stop_requested());   // 已经请求过停止
}
```

**stop_source**（[stopsource]）也持有一个 `shared_ptr`。复制 `stop_source` 得到同一个停止状态的另一个所有者，而不是新的停止状态。默认构造函数分配一个新的停止状态，分配失败抛 `bad_alloc`，所以它不是 `noexcept`（[stopsource.cons] ¶1–¶3）。`stop_source(nostopstate)` 构造一个脱离的停止源，不分配内存，适合作为稍后再赋值的成员。

**stop_callback**（[stopcallback]）不可复制也不可移动，因为它的地址登记在停止状态的回调列表里。推导指引 `stop_callback(stop_token, CallbackFn) -> stop_callback<CallbackFn>` 让 `std::stop_callback cb(tok, lambda);` 可以省略模板实参。[stopcallback.general] ¶2 要求 `CallbackFn` 满足 `invocable` 和 `destructible`。构造函数在注册成功时获得停止状态的共享所有权，析构函数注销回调并释放所有权（[stopcallback.cons]）。

## C++26：never_stop_token 与 inplace_stop_* {{c++26}}

### 概念 stoppable_token

C++26 为 [[exec]]（发送者/接收者框架）把停止令牌的接口抽象成了概念。[[stoptoken.concepts#4]] 中的 `stoppable_token<Token>` 要求：有成员别名模板 `callback_type`；`stop_requested()`、`stop_possible()` 是 `noexcept` 且返回 `bool`；复制构造不抛异常；类型 `copyable` 且 `equality_comparable`。别名 `stop_callback_for_t<T, F>` 就是 `T::template callback_type<F>`，泛型代码用它找到与令牌配套的回调类型。

`unstoppable_token` 还要求 `!tok.stop_possible()` 是值为 `true` 的常量表达式。泛型代码检测到它，就可以在编译期去掉全部取消逻辑。

### never_stop_token

`never_stop_token`（[[stoptoken.never#1]]）满足 `unstoppable_token`：两个查询都是返回 `false` 的 `static constexpr` 函数，它的 `callback_type` 是一个什么都不做的类型，构造时直接丢弃初始化器。

### inplace_stop_source 系列

[[thread.stoptoken.intro#6]] 规定 `inplace_stop_source` 是其停止状态的唯一所有者，`inplace_stop_token` 和 `inplace_stop_callback` 不参与所有权。注 1 说明它们用于令牌和回调的所有使用都嵌套在停止源生命周期之内的场合。换来的是没有引用计数，也没有堆分配。

| | `stop_source` 系列 | `inplace_stop_source` 系列 |
|---|---|---|
| 停止状态在哪里 | 堆上，引用计数 | `inplace_stop_source` 对象内部 |
| 停止源能否复制、移动 | 可以复制 | 都不可以 |
| 令牌里存的是 | `shared_ptr` | `const inplace_stop_source*` |
| 停止源默认构造 | 可能抛 `bad_alloc` | `constexpr`、`noexcept` |
| 令牌活得比停止源久 | 没有问题 | 之后再查询有问题，见下文 |

[stoptoken.inplace.mem] 的两条注说明了令牌比停止源活得久时的后果：

- [[stoptoken.inplace.mem#3]] 注 1：除非 `stop_requested()` 的调用 strongly happens before 关联 `inplace_stop_source` 析构函数的开始，否则行为未定义（[[basic.life]]），因为它要访问停止源对象。
- [[stoptoken.inplace.mem#5]] 注 2：`stop_possible()` 只比较指针是否为空，不访问停止源，只要求调用发生在停止源的存储期结束之前；否则行为由实现定义。原因是存储期结束后指针成为无效指针值，除间接访问和传给释放函数之外，对它的其他使用由实现定义（[[basic.stc.general]]）。

!!! impl "libc++ 尚未提供"
    截至 Clang 23 自带的 libc++，`<stop_token>` 里没有 `never_stop_token`、`inplace_stop_token`、`inplace_stop_source`、`inplace_stop_callback`，也没有 `stoppable_token` 概念，`__cpp_lib_senders` 未定义。本节内容未经本地编译验证。

## 实现视角

!!! impl "libc++ 的停止状态（`<__stop_token/stop_state.h>`）"
    - 停止状态是一个侵入式引用计数对象，含两个 `atomic<uint32_t>`。一个是引用计数，另一个把三样东西打包在一起：最低位表示已请求停止，下一位是回调列表的锁，其余位是 `stop_source` 的个数（`stop_token::stop_possible` 要用）。本机 `sizeof(std::stop_token)` 为 8。
    - 回调列表是侵入式双向链表，节点就是 `stop_callback` 对象本身，所以 `stop_callback` 不可移动。
    - `request_stop` 用一次 `acq_rel` 的 CAS 同时设置已请求位和锁位。release 一半对应 ¶11 第一句，与 `stop_requested` 中的 acquire 读配对；acquire 一半对应第二句，让回调看到注册时写入的数据。
    - 执行每个回调之前先解锁列表，其他线程这时注销别的回调不必等待（¶3.3.5）。实现记录了发出请求的线程。注销时如果回调可能正在执行、而当前线程不是请求线程，就在节点里的一个 `atomic<bool>` 上 `wait`，等请求线程执行完回调后设置它并 `notify_all`，这就是 ¶3.3.3 的阻塞；如果是同一线程，就只做标记，不等待（¶3.3.4）。

## 思考题

!!! question "1. 两个线程同时对同一个 `stop_source` 调用 `request_stop()`，回调执行几次？在哪个线程？"

<details markdown="1">
<summary>答案</summary>

每个回调恰好执行一次。¶12 要求判断并发出请求如同一个原子读-改-写，所以恰好一个调用返回 `true`，回调在那个线程上同步执行。另一个调用返回 `false`，它可能在回调还没执行完时就返回了：返回 `false` 的 `request_stop` 不等待回调，也不建立同步（¶11 只说返回 `true` 的调用）。
</details>

!!! question "2. `stop_callback` 的构造函数和析构函数都可能阻塞吗？"

<details markdown="1">
<summary>答案</summary>

析构函数可能阻塞：按 ¶3.3.3，回调正在另一个线程上执行时要等它返回。构造函数的规格里没有阻塞的说法，但如果注册时已经请求了停止，回调会在构造函数里同步执行（¶3.2.1.3.2），构造函数的耗时就包含回调的执行时间。
</details>

!!! question "3. 为什么停止源析构之后调用 `inplace_stop_token::stop_possible()` 是实现定义，而 `stop_requested()` 是未定义？"

<details markdown="1">
<summary>答案</summary>

`stop_possible()` 规定为返回 `stop-source != nullptr`（[stoptoken.inplace.mem] ¶4），只比较指针，不访问它指向的对象，所以与对象的生命周期无关。存储期结束之后，指针值成为无效指针值，对它的比较由实现定义（[[basic.stc.general]]）。`stop_requested()` 则要通过指针调用停止源的成员函数，在对象生命周期之外访问它是未定义行为（[[basic.life]]）。
</details>
