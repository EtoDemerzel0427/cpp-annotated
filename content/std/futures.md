---
title: future 与 async
summary: 怎样把一次计算的结果（值或异常）从一个线程交给另一个线程：共享状态的就绪、放弃与释放，promise、future、shared_future、packaged_task 的规则，async 的启动策略与延迟函数，以及 async 返回的 future 析构时为什么会阻塞。
status: done
covers: *
related: thread.threads, thread.req, syserr, intro.races, res.on.data.races, basic.start.term, exec
tags: 标准库, 并发, future, promise, async
updated: 2026-10-19
---

!!! tldr
    - 写端（`promise`、`packaged_task`、`async`）和读端（`future`、`shared_future`）共同引用一个共享状态。写端存入结果使它就绪，读端的 `get()` 等待并取出结果；存入之前的写入在 `get()` 返回后可见。
    - 写端没有存入结果就被销毁时，共享状态里会存入一个 `broken_promise` 错误，读端不会永远等下去。
    - `future::get()` 只能调用一次，之后 `valid()` 为假，再调用成员函数是 UB；需要多处读取时用 `shared_future`。
    - `async` 的默认策略允许实现选择延迟执行：函数要到第一次 `get()`/`wait()` 时才在调用者线程里运行。需要并发时显式传 `launch::async`。
    - `launch::async` 创建的共享状态，最后一个 future 析构时要等线程结束，所以丢弃 `async` 的返回值会让代码变成串行。

## 把结果交给另一个线程 [futures.overview]

```cpp run title="promise-basic.cpp" ok
#include <cstdio>
#include <future>
#include <stdexcept>
#include <thread>

int main() {
  std::promise<int> p;
  std::future<int> f = p.get_future();
  std::jthread t([&p] {
    try {
      throw std::runtime_error("disk full");
    } catch (...) {
      p.set_exception(std::current_exception());   // 异常也能传过去
    }
  });
  try {
    (void)f.get();                                  // 等待并重新抛出
  } catch (const std::exception& e) {
    std::printf("caught: %s\n", e.what());
  }
}
```

¶1 [futures] 描述的组件，让程序可以在一个线程里取回某个函数的结果，这个函数可以在同一线程或另一线程中运行，结果可以是值也可以是异常。注 1 补充，它们不只用于多线程程序。

不用这些组件，就要自己准备一个互斥量、一个条件变量、一个 `optional<T>` 和一个 `exception_ptr`。`<future>` 把它们打包成一个共享状态。

## 共享状态 [futures.state]

本节定义了整个 [futures] 用到的术语。

¶1 **共享状态**（[[g:shared-state|shared state]]）由一些状态信息和一个可能还没有求出的**结果**组成，结果是一个值（可以是 `void`）或一个异常。¶2 注 2 指出，结果也可以是用来计算结果的函数，`async` 的延迟策略就是这样。

¶3 **异步返回对象**（[[g:asynchronous-return-object|asynchronous return object]]）从共享状态读取结果，如 `future`。它的**等待函数**是可能阻塞以等待共享状态就绪的函数，如 `wait`、`get`。可能因超时提前返回的叫**定时等待函数**，如 `wait_for`，其余叫**非定时等待函数**。

¶4 **异步提供者**（[[g:asynchronous-provider|asynchronous provider]]）向共享状态提供结果，如 `promise` 和 `packaged_task`。

### 就绪（¶6、¶8）

¶8 共享状态只有在持有可取回的值或异常时才是**就绪**的。¶6 异步提供者**使共享状态就绪**，指先把它标记为就绪，再解除所有等待它就绪的执行代理的阻塞。

### 同步（¶9）

!!! std
    The storage of the result (whether normal or exceptional) into the shared state synchronizes with the successful return from a call to a waiting function on the shared state.

¶9 成功设置共享状态结果的调用，与成功检测到由此产生的就绪状态的调用[[g:synchronizes-with|同步]]；结果（正常的或异常的）存入共享状态，与该共享状态上等待函数的成功返回同步。所以 `p.set_value(x)` 之前的所有写入，在 `f.get()` 返回后都可见。

¶10 有些函数（如 `promise::set_value_at_thread_exit`）把使共享状态就绪推迟到当前线程退出时，这时线程的每个 `thread_local` 对象的析构都排在使状态就绪之前。

¶11 对同一共享状态的结果的访问可能冲突（[[intro.races]]）。注 3 举例说，通过 `shared_future::get()` 返回的引用并发访问结果时，必须只读或另加同步。

### 放弃与释放（¶5、¶7）

¶7 异步提供者**放弃**（[[g:abandon-shared-state|abandon]]）共享状态的意思是：

- ¶7.1 如果状态还没有就绪，就存入一个错误条件为 `broken_promise` 的 `future_error` 异常，使它就绪；
- ¶7.2 然后释放共享状态。

`promise` 和 `packaged_task` 的析构函数都会放弃共享状态，所以写端忘记存入结果时，读端得到的是一个异常，而不是永远阻塞。

¶5 异步返回对象或异步提供者**释放**共享状态的意思是：

- ¶5.1 如果它持有最后一个引用，销毁共享状态；
- ¶5.2 放弃自己对共享状态的引用；
- ¶5.3 这些动作不会阻塞等待共享状态就绪，只有一个例外：共享状态由 `std::async` 创建、还没有就绪、而且这是最后一个引用时，可以阻塞。

¶5.3 是 `async` 返回的 future 析构时阻塞的出处之一，下文 `async` 一节会讲另一半。

## promise [futures.promise]

`promise` 是最基本的异步提供者，由程序手动存入值或异常。

```cpp run title="promise-broken.cpp" ok
#include <cstdio>
#include <future>

int main() {
  std::future<int> f;
  {
    std::promise<int> p;
    f = p.get_future();
  }                                   // ~promise 放弃共享状态，存入 broken_promise
  try {
    (void)f.get();
  } catch (const std::future_error& e) {
    std::puts(e.code() == std::future_errc::broken_promise ? "broken_promise" : "other");
  }
}
```

¶1 主模板的 `R` 必须是满足 *Cpp17Destructible* 的对象类型。¶2 另有 `promise<R&>` 和 `promise<void>` 两个特化。

¶3 `set_value`、`set_exception` 以及它们的 `_at_thread_exit` 版本，行为如同在更新 promise 时获取一个与它关联的互斥量。所以两个线程同时 `set_value` 不是数据竞争，后一个会抛异常。

¶4 构造函数创建共享状态。¶7 析构函数放弃共享状态。

¶13–¶15 `get_future()` 返回与 `*this` 共享状态的 `future<R>`。没有共享状态时抛 `no_state`；已经调用过 `get_future` 时抛 `future_already_retrieved`，一个 promise 只对应一个 `future`。¶12 它与 `set_value` 等调用之间不会产生数据竞争。

¶16–¶18 `set_value` 原子地存入值并使状态就绪。已经有结果时抛 `promise_already_satisfied`，没有共享状态时抛 `no_state`，复制或移动 `R` 时抛出的异常也会传出来。¶19–¶22 `set_exception(p)` 类似，前置条件是 `p` 不为空 {{ub}}。

¶23–¶29 `set_value_at_thread_exit` 和 `set_exception_at_thread_exit` 立即存入结果，但推迟到当前线程退出、所有 `thread_local` 对象析构之后才使状态就绪。

## future [futures.unique.future]

¶1 `future` 是不与其他异步返回对象共享状态的异步返回对象。默认构造的 `future` 没有共享状态。¶2 注 1 指出，`future` 的成员函数之间不同步，所以一个 `future` 对象只能由一个线程使用。

### get 只能调用一次（¶3、¶15–¶19）

¶16–¶19 `get()` 先等到共享状态就绪，取出结果，然后释放共享状态。主模板返回移出来的值，`future<R&>` 返回存储的引用，`future<void>` 不返回值；存的是异常时就抛出它。¶17 之后 `valid()` 为假。

¶3 对 `valid() == false` 的 `future` 调用除析构函数、移动赋值、`share`、`valid` 以外的任何成员函数，结果未定义 {{ub}}。所以第二次 `get()` 是 UB。

```cpp title="future-get-twice.cpp" ub
#include <future>
int main() {
  std::promise<int> p;
  auto f = p.get_future();
  p.set_value(1);
  (void)f.get();
  (void)f.get();   // UB：valid() == false
}
```

¶3 的推荐做法是让实现检测这种情况，抛出 `no_state`。libc++ 没有这样做：这个程序在 Clang 23 + libc++ 上直接段错误，因为共享状态指针已经被置空了。

### 其余成员

- ¶10 析构函数释放共享状态，可能按 [futures.state] ¶5.3 阻塞。¶11 移动赋值先释放自己原来的共享状态。
- ¶13–¶14 `share()` 返回 `shared_future<R>(std::move(*this))`，之后 `valid()` 为假。
- ¶20 `valid()` 返回是否引用共享状态。¶21 `wait()` 阻塞到共享状态就绪。
- ¶22–¶27 `wait_for`、`wait_until`：共享状态里是延迟函数时什么也不做，返回 `future_status::deferred`；否则阻塞到就绪或超时，返回 `ready` 或 `timeout`。

## shared_future [futures.shared.future]

```cpp run title="shared-future.cpp" ok
#include <cstdio>
#include <future>
#include <thread>

int main() {
  std::promise<int> p;
  std::shared_future<int> sf = p.get_future().share();
  std::jthread a([sf] { std::printf("a: %d\n", sf.get()); });   // 每个线程一份副本
  std::jthread b([sf] { std::printf("b: %d\n", sf.get()); });
  p.set_value(7);
}
```

¶1 `shared_future` 可以与其他异步返回对象共享状态，它可以复制，通常由 `future::share()` 得到。

¶2 注 1 指出，`shared_future` 的成员函数之间不同步，但与共享状态同步。所以多个线程各自持有一份副本并调用 `get()` 是安全的；多个线程对同一个 `shared_future` 对象调用成员函数则没有保证，比如对它的复制赋值与 `get()` 并发就是数据竞争。上例的 lambda 按值捕获 `sf`，就是为了让每个线程有自己的副本。

¶3 与 `future` 一样，`valid()` 为假时调用除析构函数、移动赋值、复制赋值、`valid()` 以外的成员是 UB。

¶19–¶20 `get()` 不释放共享状态，可以调用多次。主模板返回指向共享状态中那个值的 `const R&`：

- ¶18 注 5 指出，对这个值对象的访问不同步，所以对 `R` 的操作可能引入数据竞争。多个线程读它没有问题；如果 `R` 有 `mutable` 成员，或者有人 `const_cast` 后修改它，就是数据竞争。
- ¶20.1 注 6 指出，共享状态销毁后再通过这个引用访问是 UB。不要把引用存到比返回它的 `shared_future` 活得更久的地方。

其余成员（¶6–¶16 的构造与赋值，¶22–¶29 的 `valid`、`wait`、`wait_for`、`wait_until`）与 `future` 对应。

## async [futures.async]

```cpp
template<class F, class... Args>
  future<invoke_result_t<decay_t<F>, decay_t<Args>...>> async(F&& f, Args&&... args);
template<class F, class... Args>
  future<invoke_result_t<decay_t<F>, decay_t<Args>...>> async(launch policy, F&& f, Args&&... args);
```

¶1 `async` 可能在新线程中启动一个函数，并通过一个与之共享状态的 `future` 提供函数的结果。¶2 `f` 和各参数的退化类型必须能从实参构造，而且能够调用。

### 启动策略（¶3）

¶3 第一个重载等价于以 `launch::async | launch::deferred` 调用第二个。第二个重载创建一个与返回的 `future` 关联的共享状态，此后的行为取决于 `policy`；满足多个条件时，实现可以任选一种：

- ¶3.1 设置了 `launch::async` 时，如同在一个由 `thread` 对象代表的新线程中调用 `invoke(auto(std::forward<F>(f)), auto(std::forward<Args>(args))...)`。参数的副本在调用 `async` 的线程里创建。返回值或传出的异常存入共享状态。这个 `thread` 对象存放在共享状态中。
- ¶3.2 设置了 `launch::deferred` 时，把 `f` 和参数的副本存入共享状态，它们构成一个**延迟函数**（[[g:deferred-function|deferred function]]）。对引用这个共享状态的异步返回对象第一次调用非定时等待函数时，在调用等待函数的线程里调用延迟函数，结果存入共享状态。一旦开始调用，函数就不再算延迟的。
- ¶3.3 `policy` 什么都没有设置，或者设置了标准和实现都没有规定的值，行为未定义 {{ub}}。

这一段有三个后果：

- 默认策略允许实现选择 `deferred`。那样函数根本不会并发执行，要等你调用 `get()` 或 `wait()` 时才在你的线程里同步运行。¶3.2 的推荐做法也说，在无法再有效利用并发时，实现应当推迟调用或推迟选择策略。
- 如同在新线程中，不等于一定创建新线程。实现可以复用线程，只要表现得像新线程，比如 `thread_local` 变量是全新的。
- 定时等待不会启动延迟函数。`wait_for`、`wait_until` 遇到延迟的共享状态时立即返回 `future_status::deferred`，不调用函数（[futures.unique.future] ¶22）。

¶8 标准的例子说明了第一点：

```cpp
int work1(int value);
int work2(int value);
int work(int value) {
  auto handle = std::async([=]{ return work2(value); });
  int tmp = work1(value);
  return tmp + handle.get();    // #1
}
```

注 3 指出，`#1` 处可能根本没有并发：默认策略可能选择 `deferred`，lambda 要到 `get()` 时才调用，`work1` 和 `work2` 在同一个线程里先后执行。需要保证并发时，显式传入 `launch::async`。

### 同步与析构时的阻塞（¶4）

¶4 `async` 的调用与 `f` 的调用同步；`f` 的完成排在共享状态就绪之前。注 1 指出，不论选择哪种策略、future 是否被移到别的线程，这些都成立；但 `f` 也可能根本不被调用（延迟且从未被等待），这时它的完成永远不会发生。

如果实现选择了 `launch::async` 策略：

- ¶4.1 对共享这个状态的异步返回对象调用等待函数时，必须阻塞到关联线程结束，如同被 join，或者超时；
- ¶4.2 关联线程的结束，与第一个成功检测到共享状态就绪的函数的返回，或最后一个释放共享状态的函数的返回同步，取先发生的那个。

¶4.1 和 [futures.state] ¶5.3 合起来，就是 `async` 返回的 future 析构时阻塞的规则：最后一个引用 `launch::async` 共享状态的 `future` 析构时，如果线程还没结束，析构函数会等它。这让 `async` 不会留下无人管理的线程，但也带来一个陷阱：

```cpp run title="async-blocking-dtor.cpp" ok
#include <chrono>
#include <cstdio>
#include <future>
#include <thread>
using namespace std::chrono;

int main() {
  auto t0 = steady_clock::now();
  (void)std::async(std::launch::async, [] { std::this_thread::sleep_for(200ms); });  // 临时 future 在分号处析构并等待
  (void)std::async(std::launch::async, [] { std::this_thread::sleep_for(200ms); });  // 所以两次调用是串行的
  auto ms = duration_cast<milliseconds>(steady_clock::now() - t0).count();
  std::printf("%lld ms\n", static_cast<long long>(ms));   // 约 400 ms，而不是 200 ms
}
```

`std::async(...)` 返回的临时 `future` 在完整表达式结束时析构，析构函数等待线程结束。所以用 `async` 写启动后不管的代码，结果是串行执行。libc++ 把 `async` 标为 `[[nodiscard]]`，丢弃返回值会得到警告，上例用 `(void)` 显式忽略。¶5 注 2 也提醒，从 `async` 得到的 `future` 被移出局部作用域后，它的析构函数同样可能阻塞。

¶6–¶7 `policy` 恰好是 `launch::async` 而无法启动新线程时，抛 `system_error`（`resource_unavailable_try_again`）；内部数据结构分配失败时抛 `bad_alloc`。只有纯 `launch::async` 才要求抛出：默认策略下实现可以改用 `deferred`。

!!! impl "libc++ 的 async"
    默认策略下，libc++ 总是先尝试创建新线程，只有创建线程抛出异常时才改用 `deferred`。所以在 libc++ 上默认策略的 `async` 实际总是并发的，但这是实现的选择，不是标准的保证。

    每次 `launch::async` 都会创建一个新的 `std::thread` 并立即 `detach`。共享状态的引用计数降为零时，先等待状态就绪，再销毁它。

!!! impl "libc++ 没有做到如同 join"
    libc++ 等待的是共享状态就绪，而不是线程结束。结果一存入共享状态，`get()` 和析构函数就可以返回，而那个已 detach 的线程可能还在析构它的 `thread_local` 对象。下面的程序在 libc++ 上打印 `0`，按 ¶4.1 应当打印 `1`：

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
      (void)f.get();   // 按 ¶4.1，线程应已如同被 join，thread_local 已析构
      std::printf("%d\n", tl_destroyed.load());
    }
    ```

    所以在 libc++ 上，`get()` 返回后不能假定 `async` 线程中 `thread_local` 对象析构的副作用（如刷新线程局部的日志缓冲区）已经发生。

## packaged_task [futures.task]

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

[futures.task.general] ¶1 `packaged_task` 包装一个函数或可调用对象，被调用时把返回值存入一个 future。¶2 调用它时，它调用存储的任务，把结果（正常的或异常的）存入共享状态。

它是可调用对象与异步提供者的结合，常用来把任务交给线程池：池只管调用它，结果自动送到 future。它只可移动，只对函数类型 `R(ArgTypes...)` 有定义。

[futures.task.members] 的要点：

- ¶1 默认构造的对象没有共享状态，也没有任务。¶2–¶7 从可调用对象 `f` 构造时，要求 `f` 能以 `ArgTypes...` 调用且结果可转换为 `R`；带分配器的版本用它分配共享状态。
- ¶8–¶9 推导指引从 `&F::operator()` 的类型推导出 `packaged_task<R(A...)>`，所以上例不用写模板实参。
- ¶14 析构函数放弃共享状态：任务从未被调用就销毁时，future 得到 `broken_promise`。
- ¶18–¶21 `get_future()` 与 promise 的一样，只能调用一次。
- ¶22–¶24 `operator()(args...)` 如同 *INVOKE*`<R>(f, args...)`，存入返回值或异常并使共享状态就绪。没有共享状态时抛 `no_state`，任务已经调用过时抛 `promise_already_satisfied`。
- ¶25–¶27 `make_ready_at_thread_exit(args...)` 立即调用任务、存入结果，但推迟到线程退出时才使状态就绪。
- ¶28–¶29 `reset()` 在 `!valid()` 时抛 `no_state`，否则用同一个任务和分配器构造新的共享状态，旧状态被放弃（注 2）。之后要重新调用 `get_future()`。

## 常见误解

!!! pitfall "对 async 的 future 轮询 wait_for 总会等到 ready"
    ```cpp
    auto f = std::async(work);                    // 默认策略：可能是 deferred
    while (f.wait_for(0s) != std::future_status::ready) {   // deferred 时永远返回 deferred
      do_other_things();
    }
    ```
    定时等待不会启动延迟函数，这个循环可能永远不结束。应当检查 `future_status::deferred`，或者显式使用 `launch::async`。

!!! pitfall "future::get 可以调用多次"
    第二次调用是 UB（¶3）。需要在多处读取时，用 `share()` 换成 `shared_future`。

!!! pitfall "shared_future::get 返回的引用可以长期持有"
    引用指向共享状态内部。最后一个 `shared_future` 析构后共享状态被销毁，引用就悬空了。

!!! pitfall "async 一定会开新线程"
    默认策略可以是 `deferred`，这时 `thread_local` 变量和在另一个线程里运行的假设都不成立。libc++ 恰好总是开新线程，其他实现不一定。

## 思考题

!!! question "思考题 1"
    `promise<int> p; auto f = p.get_future(); p.set_value(1); p.set_value(2);` 会怎样？

<details markdown="1">
<summary>答案</summary>

第二次 `set_value` 抛出 `future_error`，错误条件是 `promise_already_satisfied`（[futures.promise] ¶17–¶18）。这是有定义的错误，不是 UB。共享状态里的值仍然是 1。
</details>

!!! question "思考题 2"
    一个 `launch::deferred` 的 `future` 被 `share()` 成 `shared_future`，三个线程各持一份副本同时调用 `get()`。延迟函数运行几次？在哪个线程？

<details markdown="1">
<summary>答案</summary>

一次。按 [futures.async] ¶3.2，第一次调用非定时等待函数的线程调用延迟函数；调用一旦开始，函数就不再算延迟的，其他线程的 `get()` 只是等待它就绪。哪个线程是第一个未指定。
</details>

## 小结

| 角色 | 类型 | 要点 |
|---|---|---|
| 异步提供者 | `promise`、`packaged_task`、`async` 内部 | 析构时放弃共享状态，未就绪则存入 `broken_promise` |
| 异步返回对象 | `future`（独占）、`shared_future`（共享） | `valid()` 为假时调用成员是 UB；`future::get` 只能调用一次 |
| 同步 | 存入结果与等待函数的成功返回同步 | [futures.state] ¶9 |
| `async(launch::async)` | 如同在新线程中运行 | 最后一个 future 析构时等待线程结束 |
| `async(launch::deferred)` | 延迟函数 | 第一次非定时等待时在等待线程里运行；定时等待返回 `deferred` |
| 默认策略 | `async \| deferred` | 由实现选择；libc++ 总是选 `async` |

<details class="fine" markdown="1"><summary>其余条文</summary>

[future.syn] `<future>` 声明了 `future_errc`（`broken_promise`、`future_already_retrieved`、`promise_already_satisfied`、`no_state`）、位掩码类型 `launch`（`async`、`deferred` 以及实现定义的位）、`future_status`（`ready`、`timeout`、`deferred`），以及本页讲到的各个类模板和 `async`。¶1 注 1 允许实现提供额外的 `launch` 位。¶2 `future_errc` 的各枚举值互不相同且都不为零，因为零在 `error_code` 中表示没有错误。

[futures.errors] ¶1–¶2 `future_category()` 返回一个 `error_category` 派生类对象的引用，它的 `name()` 返回 `"future"`。¶3–¶4 `make_error_code`、`make_error_condition` 用它构造 `error_code`、`error_condition`。

[futures.future.error] `future_error` 派生自 `logic_error`。¶1 构造函数用 `make_error_code(e)` 初始化内部的 `error_code`，¶2 `code()` 返回它，¶3 `what()` 返回包含 `code().message()` 的字符串。

[futures.task.nonmembers] ¶1 与 [futures.promise] ¶30 是非成员 `swap`。

</details>
