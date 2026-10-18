---
title: future 与 async
summary: [futures] 精读——共享状态、异步提供者与异步返回对象、"就绪""放弃""释放"的精确定义与同步规则；promise、future、shared_future、packaged_task 的契约（valid() 为 false 时调用成员是 UB、get 只能调一次、shared_future::get 的引用与数据竞争）；async 的启动策略、延迟函数、"如同 join"与析构阻塞规则；libc++ 的默认策略与 thread_local 析构的偏差
status: done
covers: *
related: thread.threads, thread.req, syserr, intro.races, res.on.data.races, basic.start.term, exec
tags: 标准库, 并发, future, promise, async
updated: 2026-10-18
---

[futures.overview] ¶1：本子条款描述 C++ 程序可用来在一个线程中**取回**某个函数（在同一线程或另一线程中运行）的**结果**（值或异常）的组件。注 1：这些组件不限于多线程程序，在单线程程序中也可能有用。

`future` 解决的是"把一次计算的结果从一个线程送到另一个线程"——包括异常。没有它，你需要一个互斥量、一个条件变量、一个 `optional<T>` 和一个 `exception_ptr`。`<future>` 把这一切打包成一个**共享状态**，由"写端"（promise、packaged_task、async）和"读端"（future、shared_future）共同引用。

本页覆盖 [futures] 的全部子条款：概述、概要、错误处理、`future_error`、共享状态、`promise`、`future`、`shared_future`、`async`、`packaged_task`。

## 概要（[future.syn]）

`<future>` 声明：

- `enum class future_errc { broken_promise, future_already_retrieved, promise_already_satisfied, no_state }`，各值由实现定义；
- `enum class launch : unspecified { async, deferred, implementation-defined }`；
- `enum class future_status { ready, timeout, deferred }`；
- `is_error_code_enum<future_errc>` 特化、`make_error_code`、`make_error_condition`、`future_category`；
- `future_error`；`promise`、`future`、`shared_future` 各有主模板及 `R&`、`void` 两个特化；`packaged_task<R(ArgTypes...)>`；两个 `async` 重载。

¶1 `launch` 是位掩码类型（[[bitmask.types]]），元素为 `launch::async` 与 `launch::deferred`。注 1：实现可以提供额外的位来限制 `async()` 启动的函数的交互方式；也可以按 as-if 规则扩展第一个 `async` 重载的行为。¶2 `future_errc` 的枚举值互不相同且都不为零（零在 `error_code` 中表示"没有错误"）。

## 错误处理（[futures.errors]、[futures.future.error]）

[futures.errors]：¶1–¶2 `future_category()` 返回一个 `error_category` 派生类对象的引用，其 `name()` 返回 `"future"`。¶3–¶4 `make_error_code`/`make_error_condition` 用它构造 `error_code`/`error_condition`。

[futures.future.error]：`future_error` 派生自 `logic_error`；¶1 构造函数用 `make_error_code(e)` 初始化内部的 `error_code`；¶2 `code()` 返回它；¶3 `what()` 返回包含 `code().message()` 的 NTBS。

## 共享状态（[futures.state]）

这一节定义了本条款的全部术语：

¶1 本条款的许多类用某种状态来传递结果。这个**共享状态**（[[g:shared-state]]，shared state）由一些状态信息和一个（可能尚未求值的）**结果**组成，结果可以是一个（可能为 `void` 的）值或一个异常。注 1：future、promise、task 都引用这样的共享状态。¶2 注 2：结果可以是任何东西，包括用来计算结果的函数——`async` 的 `launch::deferred` 策略就是这样。

¶3 **异步返回对象**（[[g:asynchronous-return-object]]，asynchronous return object）是从共享状态**读取**结果的对象。异步返回对象的**等待函数**是可能阻塞以等待共享状态就绪的函数。若等待函数可能因超时在共享状态就绪前返回，它是**定时等待函数**，否则是**非定时等待函数**。

¶4 **异步提供者**（[[g:asynchronous-provider]]，asynchronous provider）是向共享状态**提供**结果的对象。例 1：promise 与 task 是异步提供者。

¶5 异步返回对象或异步提供者**释放**（release）其共享状态，意思是：

- ¶5.1 若它持有对共享状态的**最后一个**引用，销毁共享状态；
- ¶5.2 放弃对共享状态的引用；
- ¶5.3 这些动作**不会**阻塞等待共享状态就绪——**除了**以下条件**全部**成立时**可以**阻塞：共享状态由 `std::async` 创建、共享状态尚未就绪、且这是最后一个引用。

¶5.3 就是著名的"`async` 返回的 `future` 析构时会阻塞"的出处。注意措辞是 *may block*，但结合 [futures.async] ¶4.1（下文），对于 `launch::async` 策略，实际效果是必须等待。

¶6 异步提供者**使共享状态就绪**（make ready），意思是：先把共享状态标记为就绪，再解除任何等待它就绪的执行代理的阻塞。

¶7 异步提供者**放弃**（abandon）共享状态，意思是：

- ¶7.1 首先，若状态尚未就绪：在其中存入一个错误条件为 `broken_promise` 的 `future_error` 异常对象，然后使其就绪；
- ¶7.2 然后释放共享状态。

¶8 共享状态**只有**在持有可供取回的值或异常时才是**就绪**的。等待共享状态就绪时，若创建该状态的类或函数有此规定，可能在等待线程上调用计算结果的代码（延迟函数）。

¶9 是本条款的**同步规则**：

!!! std
    Calls to functions that successfully set the stored result of a shared state synchronize with calls to functions successfully detecting the ready state resulting from that setting. The storage of the result (whether normal or exceptional) into the shared state synchronizes with the successful return from a call to a waiting function on the shared state.

    成功设置共享状态所存结果的函数调用，与成功检测到由此产生的就绪状态的函数调用同步。结果（无论正常还是异常）存入共享状态，与对该共享状态的等待函数调用的成功返回同步。

所以 `p.set_value(x)` 之前的所有写，对 `f.get()` 返回之后的代码可见。

¶10 某些函数（如 `promise::set_value_at_thread_exit`）把使共享状态就绪推迟到调用线程退出时。该线程每个线程存储期对象的析构都 sequenced before 使共享状态就绪。

¶11 对同一个共享状态的结果的访问可能**冲突**（[[intro.races]]）。注 3：这明确规定了共享状态的结果在引用该状态的对象中是可见的（在 [[res.on.data.races]] 意义下）。例如，通过 `shared_future::get()` 返回的引用进行的并发访问，必须只读，或者另外提供同步。

## promise（[futures.promise]）

promise 是最基本的异步提供者：手动设置值或异常。

- ¶1 主模板的 `R` 须为满足 *Cpp17Destructible* 的对象类型。¶2 有 `promise<R&>` 与 `promise<void>` 两个特化，仅 `set_value`、`set_value_at_thread_exit` 的形参类型不同。
- ¶3 `set_value`、`set_exception`、`set_value_at_thread_exit`、`set_exception_at_thread_exit` 的行为**如同它们在更新 promise 对象时获取一个与该 promise 关联的互斥量**。所以两个线程同时 `set_value` 不是数据竞争——其中一个会抛 `promise_already_satisfied`。
- ¶4 构造函数：创建共享状态；带 `allocator_arg_t` 的版本用给定的分配器分配。
- ¶5–¶6 移动构造：转移共享状态，`rhs` 不再有共享状态。
- ¶7 析构函数：**放弃**共享状态（¶7 of [futures.state]）。所以 promise 被销毁而没有设置结果时，future 那边会得到 `broken_promise`。
- ¶8–¶11 移动赋值、`swap`。
- ¶12–¶15 `get_future()`：¶12 *Synchronization*：对它的调用不与 `set_value` 等调用引入数据竞争（注 1：这些调用不需要彼此同步）。¶13 返回与 `*this` 共享状态的 `future<R>`。¶14–¶15 若没有共享状态，抛 `no_state`；**若已经对共享同一状态的 promise 调用过 `get_future`，抛 `future_already_retrieved`**——一个 promise 只能对应一个 `future`（需要多个读者时用 `shared_future`）。
- ¶16–¶18 `set_value`：原子地存入值并使状态就绪；已有结果时抛 `promise_already_satisfied`，无共享状态时抛 `no_state`；复制/移动 `R` 时抛出的异常也会传出。
- ¶19–¶22 `set_exception(exception_ptr p)`：*Preconditions* `p` 不为空 {{ub}}；其余同上。
- ¶23–¶29 `set_value_at_thread_exit`、`set_exception_at_thread_exit`：存入结果但**不立即**使其就绪，安排在当前线程退出、所有线程存储期对象析构之后再使其就绪。
- ¶30 非成员 `swap`。

```cpp run title="promise-shared-future.cpp" ok
#include <cstdio>
#include <future>
#include <thread>

int main() {
  std::future<int> f;
  {
    std::promise<int> p;
    f = p.get_future();
  }                                   // ~promise：放弃共享状态，存入 broken_promise
  try {
    (void)f.get();
  } catch (const std::future_error& e) {
    std::puts(e.code() == std::future_errc::broken_promise ? "broken_promise" : "other");
  }

  std::promise<int> p2;
  std::shared_future<int> sf = p2.get_future().share();
  std::jthread a([sf] { std::printf("a: %d\n", sf.get()); });   // 每个线程持有自己的 shared_future 副本
  std::jthread b([sf] { std::printf("b: %d\n", sf.get()); });
  p2.set_value(7);
}
```

## future（[futures.unique.future]）

¶1 `future` 是**不与其他异步返回对象共享**其共享状态的异步返回对象类型。默认构造的 `future` 没有共享状态。有共享状态的 `future` 由异步提供者的函数或移动构造创建，与原来的异步提供者共享状态。

¶2 注 1：`future` 的成员函数**不与自身同步**，也不与 `shared_future` 的成员函数同步。即一个 `future` 对象只能由一个线程使用。

¶3 对 `valid() == false` 的 `future` 调用除析构函数、移动赋值、`share`、`valid` 以外的任何成员函数，**效果未定义** {{ub}}。注 2：移动一个 `valid() == false` 的 `future` 是合法的。*推荐做法*：实现应当检测这种情况并抛出错误条件为 `no_state` 的 `future_error`。

¶3 是本类最重要的一条：**`get()` 只能调用一次**。`get()` 之后 `valid()` 为 `false`（¶17），第二次调用是 UB。

```cpp title="future-get-twice.cpp" ub
#include <future>
int main() {
  std::promise<int> p;
  auto f = p.get_future();
  p.set_value(1);
  (void)f.get();
  (void)f.get();   // UB：valid() == false（¶3）
}
```

libc++ 没有采纳 ¶3 的推荐做法：这个程序在 Clang 23 + libc++ 上直接段错误（`future` 内部的共享状态指针已被置空），而不是抛出 `no_state`。

- ¶4–¶5 `R` 的要求与两个特化，同 promise。
- ¶6–¶9 默认构造、移动构造。
- ¶10 析构函数：**释放**共享状态（可能按 [futures.state] ¶5.3 阻塞），然后销毁 `*this`。
- ¶11–¶12 移动赋值：先释放自己的共享状态，再移动。
- ¶13–¶14 `share()`：返回 `shared_future<R>(std::move(*this))`，之后 `valid() == false`。
- ¶15–¶19 `get()`：`wait()` 直到共享状态就绪，取出值，然后**释放**共享状态；之后 `valid() == false`。主模板返回 `std::move(v)`（值被移出），`future<R&>` 返回存储的引用，`future<void>` 不返回值；存储的是异常时抛出它。
- ¶20 `valid()`：是否引用共享状态。
- ¶21 `wait()`：阻塞直到共享状态就绪。
- ¶22–¶27 `wait_for`、`wait_until`：**若共享状态含有延迟函数，什么也不做**，返回 `future_status::deferred`；否则阻塞到就绪或超时，返回 `ready` 或 `timeout`。

## shared_future（[futures.shared.future]）

¶1 `shared_future` 是**可以**与其他异步返回对象共享其共享状态的异步返回对象类型。它由 `future` 转换而来，可复制。

¶2 注 1：`shared_future` 的成员函数**不与自身同步**，但**与共享状态同步**。这意味着：多个线程**各自持有一个副本**调用 `get()` 是安全的；多个线程对**同一个** `shared_future` 对象调用成员函数则不保证（同一对象上的复制赋值与 `get` 并发就是数据竞争）。上面的例子中每个 lambda 按值捕获 `sf`，正是为此。

¶3 与 `future` 相同的规则：`valid() == false` 时调用除析构、移动赋值、复制赋值、`valid()` 以外的成员是 UB；推荐抛 `no_state`。

- ¶8–¶11 复制构造（引用同一共享状态）、从 `future&&` 与 `shared_future&&` 的移动构造。
- ¶12–¶16 析构与赋值：释放共享状态。
- ¶17–¶21 `get()`：**不释放共享状态**，可以多次调用。主模板返回 `const R&`。¶18 注 5：对共享状态中值对象的访问是**不同步的**，所以对 `R` 的操作可能引入数据竞争。¶20.1 注 6：共享状态被销毁后再通过该引用访问是 UB；不要把引用存到比返回它的 `shared_future` 活得更久的地方。
- ¶22–¶29 `valid`、`wait`、`wait_for`、`wait_until`，同 `future`。

¶18 的含义：`get()` 返回的是共享状态里**同一个对象**的 `const` 引用。多个线程读取它没问题；但若 `R` 有 `mutable` 成员，或有人 `const_cast` 后修改，就是数据竞争。

## async（[futures.async]）

¶1 函数模板 `async` 提供一种机制，**可能**在新线程中启动函数，并在与之共享共享状态的 `future` 对象中提供函数的结果。

```cpp
template<class F, class... Args>
  future<invoke_result_t<decay_t<F>, decay_t<Args>...>> async(F&& f, Args&&... args);
template<class F, class... Args>
  future<invoke_result_t<decay_t<F>, decay_t<Args>...>> async(launch policy, F&& f, Args&&... args);
```

¶2 *Mandates*：`decay_t<F>` 与各 `decay_t<Args>` 可从对应实参构造，且 `is_invocable_v<decay_t<F>, decay_t<Args>...>`。

### 启动策略（¶3）

¶3 第一个重载等价于以 `launch::async | launch::deferred` 调用第二个。第二个重载创建一个与返回的 `future` 关联的共享状态，其后的行为取决于 `policy`（若满足多个条件，实现可以选择任一对应策略）：

- ¶3.1 **`launch::async`**：调用 `invoke(auto(std::forward<F>(f)), auto(std::forward<Args>(args))...)`，**如同在一个由 `thread` 对象表示的新执行线程中**，`auto` 产生的值在调用 `async` 的线程中物化。返回值作为结果存入共享状态；传播出的异常作为异常结果存入。**`thread` 对象存放在共享状态中**，影响所有引用该状态的异步返回对象的行为。
- ¶3.2 **`launch::deferred`**：把 `auto(std::forward<F>(f))` 与 `auto(std::forward<Args>(args))...` 存入共享状态，它们构成一个**延迟函数**（[[g:deferred-function]]，deferred function）。调用延迟函数即求值 `invoke(std::move(g), std::move(xyz))`。结果或异常存入共享状态。函数完成之前状态不会就绪。**对引用该共享状态的异步返回对象第一次调用非定时等待函数时，在调用等待函数的线程中调用延迟函数。** 一旦 `invoke` 的求值开始，函数就不再被视为"延迟的"。*推荐做法*：若此策略与其他策略同时指定（如默认的 `async | deferred`），在不能再有效利用更多并发时，实现应当推迟调用或推迟策略的选择。
- ¶3.3 若 `policy` 中没有设置任何值，或设置了既非本文件也非实现规定的值，行为未定义 {{ub}}。

几个要点：

- **默认策略允许实现选择 `deferred`**。那样的话函数根本不会并发执行，直到你调用 `get()`/`wait()`——在你的线程里同步执行。例 1 的注 3 正是这个提醒。
- **"如同在新线程中"**不等于"一定创建新线程"：实现可以用线程池，只要表现得如同新线程（例如 `thread_local` 变量是新的）。
- **定时等待不会触发延迟函数**：`wait_for`/`wait_until` 对延迟状态立即返回 `future_status::deferred`，不调用函数（[futures.unique.future] ¶22）。

### 同步（¶4）

¶4 *Synchronization*：`async` 的调用与 `f` 的调用同步。`f` 的完成 sequenced before 共享状态就绪。注 1：无论策略如何，即使对应的 `future` 被移到另一个线程，这些规则都适用；但 `f` 可能**根本不被调用**（延迟且从未等待），此时它的完成永远不会发生。

若实现选择 `launch::async` 策略：

- ¶4.1 对共享该状态的异步返回对象调用等待函数，**必须阻塞直到关联线程完成，如同被 join**，或者超时；
- ¶4.2 关联线程的完成，与"第一个成功检测到共享状态就绪的函数的返回"或"最后一个释放共享状态的函数的返回"（以先发生者为准）同步。

¶4.1 与 [futures.state] ¶5.3 合起来，就是"**`async` 返回的 future 的析构函数阻塞**"规则：最后一个引用 `async`（`launch::async`）共享状态的 `future` 析构时，若线程未完成，析构函数等待它，如同 join。这让 `async` 不会产生"孤儿线程"，但也带来著名的陷阱：

```cpp run title="async-blocking-dtor.cpp" ok
#include <chrono>
#include <cstdio>
#include <future>
#include <thread>
using namespace std::chrono;

int main() {
  auto t0 = steady_clock::now();
  (void)std::async(std::launch::async, [] { std::this_thread::sleep_for(200ms); });  // 临时 future 在分号处析构：阻塞
  (void)std::async(std::launch::async, [] { std::this_thread::sleep_for(200ms); });  // 所以两次调用是串行的
  auto ms = duration_cast<milliseconds>(steady_clock::now() - t0).count();
  std::printf("two discarded asyncs: %lld ms\n", static_cast<long long>(ms));   // 约 400 ms，而不是 200 ms
}
```

`std::async(...)` 的返回值是一个临时 `future`，在完整表达式结束时析构，析构函数等待线程完成。所以"火了就不管"（fire-and-forget）用 `async` 写出来是串行的。libc++ 把 `async` 标为 `[[nodiscard]]`，丢弃返回值会得到警告，上例用 `(void)` 显式忽略。

¶5 *Returns*：引用本次调用创建的共享状态的 `future<invoke_result_t<decay_t<F>, decay_t<Args>...>>`。注 2：若从 `async` 获得的 `future` 被移出局部作用域，该 `future` 的析构函数可能阻塞等待共享状态就绪。

¶6–¶7 *Throws*：`policy == launch::async` 且无法启动新线程时抛 `system_error`（`resource_unavailable_try_again`）；内部数据结构内存不足时抛 `bad_alloc`。注意只有**纯** `launch::async` 才要求抛：默认策略下无法开线程时，实现可以退回 `deferred`。

¶8 例 1：

```cpp
int work1(int value);
int work2(int value);
int work(int value) {
  auto handle = std::async([=]{ return work2(value); });
  int tmp = work1(value);
  return tmp + handle.get();    // #1
}
```

注 3：#1 处可能**没有**并发，因为 `async` 用的是默认策略，可能选 `launch::deferred`；那样 lambda 直到 `get()` 才被调用，`work1` 与 `work2` 在同一线程执行。需要保证并发时，显式传 `launch::async`。

!!! impl "libc++ 的 async"
    - **默认策略总是选 `async`**：`async(launch::async | launch::deferred, ...)` 先尝试创建新线程；只有在创建线程抛出异常时，才退回 `deferred`（纯 `launch::async` 则重新抛出）。所以在 libc++ 上，默认策略的 `async` 实际上总是并发的——但这是实现的选择，不是标准的保证。
    - 每次 `launch::async` 都创建一个**新的** `std::thread` 并立即 `detach`；共享状态的引用计数降为零时（`__on_zero_shared`），先 `wait()` 等待状态就绪，再销毁。

!!! impl "libc++ 没有做到“如同 join”"
    libc++ 等待的是**共享状态就绪**，而不是**线程完成**：线程函数的结果一存入共享状态，`get()` 和析构函数就可以返回，而那个已 detach 的线程此时可能还在析构它的 `thread_local` 对象。下面的程序在 libc++ 上打印 `0`，按 ¶4.1 的字面要求应当打印 `1`：

    ```cpp run title="async-thread-local.cpp" ok
    #include <atomic>
    #include <chrono>
    #include <cstdio>
    #include <future>
    #include <thread>

    std::atomic<bool> tl_destroyed{false};
    struct TL {
      ~TL() {
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
        tl_destroyed = true;
      }
    };
    thread_local TL tl;

    int main() {
      auto f = std::async(std::launch::async, [] { (void)&tl; return 1; });
      (void)f.get();   // ¶4.1：阻塞到关联线程完成"如同被 join"，thread_local 的析构应已完成
      std::printf("%d\n", tl_destroyed.load());
    }
    ```

    实际影响：依赖 `async` 线程中 `thread_local` 对象析构副作用（如刷新线程局部的日志缓冲区）的代码，在 `get()` 返回后不能假定这些副作用已经发生。

## packaged_task（[futures.task]）

### 总述（[futures.task.general]）

¶1 `packaged_task` 包装一个函数或可调用对象，使其返回值在被调用时存入一个 future。¶2 调用 `packaged_task` 对象时，调用其存储的任务，并把结果（正常或异常）存入共享状态；共享该状态的 future 随后可以取回结果。

它是"异步提供者 + 可调用对象"：常用于把任务交给线程池——池只需要知道"调用它"，结果自动送到 future。类模板只对函数类型 `R(ArgTypes...)` 有定义；只可移动。

### 成员（[futures.task.members]）

- ¶1 默认构造：没有共享状态，没有存储的任务。
- ¶2 `packaged_task(F&& f)`：等价于 `packaged_task(allocator_arg, allocator<int>(), std::forward<F>(f))`。
- ¶3–¶7 `packaged_task(allocator_arg_t, const Allocator& a, F&& f)`：*Constraints* `remove_cvref_t<F>` 不是本 `packaged_task` 类型；*Mandates* `is_invocable_r_v<R, decay_t<F>&, ArgTypes...>`；用 `a` 重新绑定的分配器为共享状态分配存储，并把它的副本存入共享状态（`reset()` 会用到）。
- ¶8–¶9 推导指引 `packaged_task(F) -> packaged_task<R(A...)>`：从 `&F::operator()` 的类型推导，支持显式对象形参与静态 `operator()`。
- ¶10–¶13 移动构造与移动赋值。
- ¶14 析构函数：**放弃**共享状态——任务从未被调用就销毁，future 得到 `broken_promise`。
- ¶15–¶16 `swap`。¶17 `valid()`：是否有共享状态。
- ¶18–¶21 `get_future()`：同 promise，只能调用一次。
- ¶22–¶24 `operator()(ArgTypes... args)`：如同 *INVOKE*`<R>(f, args...)`；存入返回值或异常；使共享状态就绪，解除等待者的阻塞。没有共享状态或任务已被调用过时抛 `future_error`（`no_state`、`promise_already_satisfied`）。
- ¶25–¶27 `make_ready_at_thread_exit(args...)`：调用任务、存入结果，但推迟到线程退出时才使状态就绪。
- ¶28–¶29 `reset()`：若 `!valid()` 抛 `no_state`；否则等价于 `*this = packaged_task(allocator_arg, a, std::move(f));`——用同一个任务和分配器**构造一个新的共享状态**，旧状态被放弃（注 2）。之后需要重新 `get_future()`。

[futures.task.nonmembers] ¶1：非成员 `swap`。

```cpp run title="packaged-task.cpp" ok
#include <cstdio>
#include <future>
#include <thread>

int main() {
  std::packaged_task task([](int a, int b) { return a * b; });   // 推导为 packaged_task<int(int, int)>
  std::future<int> f = task.get_future();
  std::jthread worker(std::move(task), 6, 7);    // 在另一个线程里调用
  std::printf("%d\n", f.get());                  // 42
}
```

## 陷阱

!!! pitfall "对延迟的 future 轮询 wait_for 会死循环"
    ```cpp
    auto f = std::async(work);                    // 默认策略：可能是 deferred
    while (f.wait_for(0s) != std::future_status::ready) {   // deferred 时永远返回 deferred
      do_other_things();
    }
    ```
    定时等待不会启动延迟函数。检查 `future_status::deferred`，或者显式使用 `launch::async`。

!!! pitfall "future::get 只能调用一次"
    第二次调用是 UB（¶3）。需要多处读取时，`share()` 成 `shared_future`。

!!! pitfall "shared_future::get 返回的引用不能长期持有"
    引用指向共享状态内部；最后一个 `shared_future` 析构后共享状态被销毁，引用悬空。

!!! pitfall "以为 async 一定开新线程"
    默认策略可以是 `deferred`，`thread_local` 与"在另一个线程里"的假设都可能落空。libc++ 恰好总是开新线程，在其他实现上可能不是。

## 思考题

!!! question "1. `promise<int> p; auto f = p.get_future(); p.set_value(1); p.set_value(2);` 会怎样？"

<details markdown="1">
<summary>答案</summary>

第二次 `set_value` 抛出 `future_error`，错误条件 `promise_already_satisfied`（[futures.promise] ¶17–¶18）。这是有定义的错误，不是 UB。共享状态中的值仍是 1。
</details>

!!! question "2. 一个 `launch::deferred` 的 `future` 被 `share()` 成 `shared_future`，三个线程同时 `get()`，延迟函数执行几次？在哪个线程？"

<details markdown="1">
<summary>答案</summary>

一次。[futures.async] ¶3.2："第一次"调用非定时等待函数的线程调用延迟函数；"一旦 `invoke` 的求值开始，函数就不再被视为延迟的"，其他线程的 `get()` 就只是等待它就绪。哪个线程是"第一个"未指定。
</details>

## 小结

| 角色 | 类型 | 关键规则 |
|---|---|---|
| 异步提供者 | `promise`、`packaged_task`、（`async` 内部） | 析构时**放弃**：未就绪则存入 `broken_promise` |
| 异步返回对象 | `future`（独占）、`shared_future`（共享） | `valid() == false` 时调用成员是 UB；`future::get` 只能一次 |
| 同步 | 设置结果 sync-with 成功检测到就绪 | [futures.state] ¶9 |
| `async(launch::async)` | 如同在新线程中运行 | 最后一个 future 析构时阻塞，如同 join |
| `async(launch::deferred)` | 延迟函数 | 第一次非定时等待时在等待线程中执行；定时等待返回 `deferred` |
| 默认策略 | `async | deferred` | 由实现选择；libc++ 总是 `async` |
